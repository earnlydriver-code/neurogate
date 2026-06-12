"""Gateway como servicio (Fase C): el orquestador v1 expuesto por FastAPI.

Migra el orquestador en-proceso de la v1 a un servicio FastAPI con autenticación
JWT por scopes y revocación en caliente. El bucle señal→decoder corre como tarea
de fondo (lifespan) y mantiene en memoria la última intención decodificada para
servir los streams.

Reutiliza los bloques de la v1 SIN reescribirlos: ``AuditLog``, ``CryptoLayer``,
``AnomalyDetector``, ``ConsentFilter``/``DataType``, ``SignalSource`` y ``Decoder``.
Todo el flujo de defensas (consent → anomaly → crypto → audit) es el mismo de la
v1, ahora detrás de la red.
"""

from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from neurogate.anomaly import AnomalyDetector
from neurogate.audit import AuditEvent, AuditLog
from neurogate.auth import AuthError, AuthManager, TokenClaims, scopes_to_datatypes
from neurogate.config import Settings, get_settings
from neurogate.consent import AccessRequest, ConsentFilter, DataType
from neurogate.crypto_layer import CryptoLayer
from neurogate.decoder import Decoder, Intent
from neurogate.gateway import _trained_decoder  # decoder v1 entrenado y cacheado
from neurogate.signal_source import SignalSource

# Texto de ejemplo que el usuario habría confirmado (placeholder, heredado de v1).
_CONFIRMED_TEXT = b"<texto confirmado por el usuario>"

# Intervalo (s) entre ticks del bucle de fondo señal→decoder.
_TICK_SECONDS = 0.2


@dataclass
class ServiceState:
    """Estado vivo del servicio: defensas v1 + bucle de señal + auth."""

    auth: AuthManager
    consent: ConsentFilter
    anomaly: AnomalyDetector
    crypto: CryptoLayer
    audit: AuditLog
    signal: SignalSource
    decoder: Decoder
    settings: Settings
    latest_intent: Intent = Intent.IDLE
    counters: dict = None  # type: ignore[assignment]
    app_status: dict = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.counters is None:
            self.counters = {"requests": 0, "allowed": 0, "blocked": 0}
        if self.app_status is None:
            self.app_status = {}

    # --- bucle de señal (reutiliza signal v1 + decoder v1) ---

    def tick(self) -> Intent:
        """Avanza un bloque: lee señal y decodifica la intención actual."""
        chunk = self.signal.get_chunk()
        self.latest_intent = self.decoder.decode(chunk)
        return self.latest_intent

    # --- registro de clientes (auth + consent + crypto + anomaly) ---

    def register_client(self, client_id: str, client_secret: str,
                        scopes: list[str]) -> None:
        """Da de alta una app en todas las capas: auth, consent, crypto y anomaly."""
        self.auth.register_client(client_id, client_secret, scopes)
        granted_scopes = self.auth.client_scopes(client_id)
        dtypes = scopes_to_datatypes(granted_scopes)
        self.consent.register_app(client_id, dtypes)
        self.crypto.register_app(client_id)
        self.anomaly.warm_up(client_id, dtypes)
        self.app_status.setdefault(client_id, "ok")

    def prime_anomaly(self, n_per_app: int = 200, seed: int = 0) -> None:
        """Baseline de accesos normales por app (mismo método que el Gateway v1)."""
        import numpy as np

        rng = np.random.default_rng(seed)
        t, history = 1_000_000.0, []
        for _ in range(n_per_app):
            for app_id in self.consent.registered_apps:
                t += max(0.3, rng.normal(1.0, 0.3))
                for dtype in self.consent.permissions_of(app_id):
                    history.append(AccessRequest(app_id, dtype, t))
        if history:
            self.anomaly.fit(history)
            self.anomaly.clear_timing()

    def release_quarantine(self, app_id: str) -> None:
        """Saca una app de cuarentena (acción explícita)."""
        if self.app_status.get(app_id) == "quarantine":
            self.app_status[app_id] = "ok"

    # --- payload por tipo (igual que el Gateway v1) ---

    def _payload_for(self, data_type: DataType) -> bytes:
        if data_type is DataType.INTENT:
            return self.latest_intent.value.encode()
        if data_type is DataType.CONFIRMED_TEXT:
            return _CONFIRMED_TEXT
        if data_type is DataType.RAW_SIGNAL:
            return self.signal.get_chunk().astype("float32").tobytes()
        return b""

    # --- el pipeline de defensas v1, por red ---

    def serve(self, claims: TokenClaims, scope: str) -> bytes:
        """Pipeline completo para una entrega: scope→consent→anomaly→crypto→audit.

        Devuelve el payload cifrado o lanza AuthError. TODA rama (allow/deny/
        quarantine) pasa por audit.append(), sin excepciones.
        """
        client_id = claims.client_id
        dtype = self._datatype_for_scope(claims, scope)  # 403 si el scope no aplica
        request = AccessRequest(client_id, dtype)
        self.counters["requests"] += 1

        # 0. Cuarentena: una app en cuarentena no recibe nada (y se audita).
        if self.app_status.get(client_id) == "quarantine":
            self._block(request, "app en cuarentena")
            raise AuthError(403, "app en cuarentena")

        # 1. Consentimiento (sin consumir la aprobación todavía).
        decision = self.consent.check(request, consume=False)
        if not decision.allowed:
            self._block(request, decision.reason)
            raise AuthError(403, decision.reason)

        # 2. Anomalías (si hay baseline entrenado).
        if self.anomaly.is_trained:
            result = self.anomaly.score(request)
            if result.is_anomalous:
                self.app_status[client_id] = "quarantine"
                self._block(request, f"anomalía: {result.reason}")
                raise AuthError(403, f"anomalía: {result.reason}")

        # 3. Cifrado + 4. Auditoría (permitido). Recién aquí se gasta la aprobación.
        if self.consent.requires_confirmation(dtype):
            self.consent.consume_approval(client_id, dtype)
        payload = self.crypto.encrypt_for(client_id, self._payload_for(dtype))
        self.counters["allowed"] += 1
        self.audit.append(AuditEvent(client_id, dtype.value, True, "autorizado"))
        return payload

    def _datatype_for_scope(self, claims: TokenClaims, scope: str) -> DataType:
        """Comprueba que el token tiene el scope y lo mapea a su DataType.

        Falta de scope → 403 + evento de auditoría (escalada de scopes bloqueada).
        """
        from neurogate.auth import SCOPE_TO_DATATYPE

        if scope not in claims.scopes:
            # Escalada de scopes: se audita aunque el dato nunca llegue al pipeline.
            self.counters["requests"] += 1
            self._block(AccessRequest(claims.client_id, DataType.INTENT),
                        f"scope insuficiente: falta {scope}")
            raise AuthError(403, f"scope insuficiente: falta {scope}")
        dtype = SCOPE_TO_DATATYPE.get(scope)
        if dtype is None:
            raise AuthError(403, f"el scope {scope} no entrega datos neuronales")
        return dtype

    def _block(self, request: AccessRequest, reason: str) -> None:
        """Registra el bloqueo en auditoría (sin entregar nada)."""
        self.counters["blocked"] += 1
        self.audit.append(AuditEvent(request.app_id, request.data_type.value,
                                     False, reason, request.timestamp))

    def live_state(self) -> dict:
        """Snapshot del estado en vivo para el dashboard / admin."""
        return {
            "latest_intent": self.latest_intent.value,
            "counters": dict(self.counters),
            "app_status": dict(self.app_status),
            "clients": self.auth.clients,
            "audit_ok": self.audit.verify_chain(),
        }


# --- modelos de request/response de la API ---

class TokenRequest(BaseModel):
    """Cuerpo de POST /auth/token (client credentials)."""

    client_id: str
    client_secret: str
    scopes: list[str] | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    scopes: list[str]
    jti: str
    expires_at: int


class RevokeRequest(BaseModel):
    """Cuerpo de POST /admin/revoke."""

    jti: str


def build_state(settings: Settings, audit_path: Path | str) -> ServiceState:
    """Construye el estado del servicio reutilizando los bloques v1.

    Para la Fase C usa la combinación más simple y robusta: SignalSource v1 +
    Decoder v1 (deterministas). Cambiar a BrainFlow + decoder MI sería un cambio
    de configuración futuro (Fase D+); aquí NO se cablea.
    """
    seed = settings.seed
    state = ServiceState(
        auth=AuthManager(settings.jwt_secret, settings.jwt_algorithm,
                         settings.token_expire_minutes, settings.clinical_mode),
        consent=ConsentFilter(),
        anomaly=AnomalyDetector(seed=seed),
        crypto=CryptoLayer(),
        audit=AuditLog(audit_path),
        signal=SignalSource(seed=seed),
        decoder=_trained_decoder(seed),
        settings=settings,
    )
    return state


def create_app(settings: Settings | None = None,
               audit_path: Path | str = "audit_service.jsonl",
               background_loop: bool = True,
               prime_anomaly: bool = True) -> FastAPI:
    """Crea la app FastAPI. Los tests inyectan settings de prueba y desactivan el bucle."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Bucle de fondo señal→decoder: mantiene la última intención en memoria.
        task = None
        if background_loop:
            task = asyncio.create_task(_signal_loop(app.state.service))
        yield
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app = FastAPI(title="NeuroGate Gateway (Fase C)", lifespan=lifespan)
    state = build_state(settings, audit_path)
    if prime_anomaly:
        state.prime_anomaly(seed=settings.seed)
    app.state.service = state

    _register_routes(app)
    return app


async def _signal_loop(state: ServiceState) -> None:
    """Tarea de fondo: cicla la intención simulada y avanza señal→decoder.

    Cambiar la intención cada pocos ticks hace que el stream muestre intenciones
    variadas (idle/move_cursor/type_text), reproduciendo el flujo v1. En Fase D+
    el set_intent simulado se sustituye por la fuente BrainFlow real.
    """
    from neurogate.signal_source import INTENTS

    i, ticks = 0, 0
    while True:
        if ticks % 5 == 0:
            state.signal.set_intent(INTENTS[i % len(INTENTS)])
            i += 1
        state.tick()
        ticks += 1
        await asyncio.sleep(_TICK_SECONDS)


# --- endpoints (cierran sobre el ServiceState de la app) ---

def _register_routes(app: FastAPI) -> None:
    """Registra los endpoints, cerrando sobre el ServiceState de esta app."""

    def current_state() -> ServiceState:
        return app.state.service

    def claims_from_header(authorization: str | None = Header(default=None)) -> TokenClaims:
        """Verifica el Bearer token y devuelve sus claims; 401 si falla."""
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="falta el token Bearer")
        token = authorization.split(" ", 1)[1].strip()
        try:
            return current_state().auth.verify_token(token)
        except AuthError as e:
            raise HTTPException(status_code=e.status_code, detail=e.detail)

    def require_scope(scope: str):
        """Dependencia: exige que el token tenga un scope concreto (admin, stats...)."""

        def _dep(claims: TokenClaims = Depends(claims_from_header)) -> TokenClaims:
            if scope not in claims.scopes:
                raise HTTPException(status_code=403, detail=f"scope insuficiente: falta {scope}")
            return claims

        return _dep

    @app.post("/auth/token", response_model=TokenResponse)
    def issue_token(body: TokenRequest) -> TokenResponse:
        """Emite un JWT a una app registrada (client credentials)."""
        state = current_state()
        try:
            token, claims = state.auth.issue_token(body.client_id, body.client_secret,
                                                   body.scopes)
        except AuthError as e:
            raise HTTPException(status_code=e.status_code, detail=e.detail)
        return TokenResponse(access_token=token, scopes=claims.scopes,
                             jti=claims.jti, expires_at=claims.exp)

    @app.get("/data/confirmed_text")
    def confirmed_text(claims: TokenClaims = Depends(claims_from_header)) -> dict:
        """Entrega texto confirmado (requiere read:confirmed_text)."""
        state = current_state()
        try:
            payload = state.serve(claims, "read:confirmed_text")
        except AuthError as e:
            raise HTTPException(status_code=e.status_code, detail=e.detail)
        return {"data_type": "confirmed_text",
                "payload_b64": base64.b64encode(payload).decode(),
                "encrypted": True}

    @app.get("/admin/state")
    def admin_state(claims: TokenClaims = Depends(require_scope("admin"))) -> dict:
        """Estado en vivo del servicio (apps, contadores, alertas). Requiere admin."""
        return current_state().live_state()

    @app.post("/admin/revoke")
    def admin_revoke(body: RevokeRequest,
                     claims: TokenClaims = Depends(require_scope("admin"))) -> dict:
        """Revoca un token por jti: corta su acceso al instante. Requiere admin."""
        current_state().auth.revoke(body.jti)
        return {"revoked": body.jti}

    @app.websocket("/stream/intents")
    async def stream_intents(websocket: WebSocket) -> None:
        """Stream de intenciones decodificadas (requiere read:intent).

        El token se pasa como query param ``token`` (los navegadores no envían
        headers en el handshake WS). Se reverifica en cada mensaje, de modo que
        revocar el token corta el stream al instante.
        """
        state = current_state()
        token = websocket.query_params.get("token", "")
        try:
            claims = state.auth.verify_token(token)
        except AuthError as e:
            await websocket.close(code=4401, reason=e.detail)
            return
        if "read:intent" not in claims.scopes:
            await websocket.close(code=4403, reason="scope insuficiente: falta read:intent")
            return

        await websocket.accept()
        try:
            while True:
                # Reverificar token + pipeline en cada entrega (revocación en caliente).
                try:
                    claims = state.auth.verify_token(token)
                    payload = state.serve(claims, "read:intent")
                except AuthError as e:
                    await websocket.send_json({"error": e.detail})
                    await websocket.close(code=4401 if e.status_code == 401 else 4403,
                                          reason=e.detail)
                    return
                await websocket.send_json({
                    "data_type": "intent",
                    "intent": state.latest_intent.value,
                    "payload_b64": base64.b64encode(payload).decode(),
                    "encrypted": True,
                })
                await asyncio.sleep(_TICK_SECONDS)
        except WebSocketDisconnect:
            return


# App por defecto para `uvicorn neurogate.service:app`. Los tests crean la suya
# con create_app(settings_de_prueba).
app = create_app()
