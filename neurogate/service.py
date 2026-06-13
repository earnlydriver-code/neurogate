"""Gateway como servicio (Fase C + hardening Fase D): orquestador v1 sobre FastAPI.

Migra el orquestador en-proceso de la v1 a un servicio FastAPI con autenticación
JWT por scopes y revocación en caliente. El bucle señal→decoder corre como tarea
de fondo (lifespan) y mantiene en memoria la última intención decodificada.

**Fase D (hardening)** sustituye, en el SERVICIO, los bloques de demo de la v1 por
sus versiones serias (la v1 sigue intacta para su propio gateway/tests):

- cifrado por app con ``CryptoLayerV2`` (HKDF + AESGCM + rotación versionada +
  anti-replay),
- log firmado ``SignedAuditLog`` (cadena SHA-256 + firma Ed25519),
- anomalías sobre telemetría real con ``TelemetryAnomalyDetector``.

Todo el flujo de defensas (scope → consent → anomalía → crypto → audit) se conserva;
cambian las implementaciones detrás de cada contrato.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import secrets
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from neurogate.auth import AuthError, AuthManager, TokenClaims, scopes_to_datatypes
from neurogate.config import Settings, get_settings
from neurogate.consent import AccessRequest, ConsentFilter, DataType
from neurogate.crypto_v2 import CryptoLayerV2, DecryptError, ReplayError
from neurogate.decoder import Decoder, Intent
from neurogate.gateway import _trained_decoder  # decoder v1 entrenado y cacheado
from neurogate.signal_source import SignalSource
from neurogate.signed_audit import (SignedAuditEvent, SignedAuditLog,
                                     load_private_key)
from neurogate.telemetry_anomaly import TelemetryAnomalyDetector, TelemetryRecord

# Texto de ejemplo que el usuario habría confirmado (placeholder, heredado de v1).
_CONFIRMED_TEXT = b"<texto confirmado por el usuario>"

# Intervalo (s) entre ticks del bucle de fondo señal→decoder.
_TICK_SECONDS = 0.2

_log = logging.getLogger("neurogate.service")

# Valores placeholder de config.py: si el servicio los recibe, NO se usan tal cual
# (serían públicos del repo); se sustituyen por un secreto aleatorio efímero.
_PLACEHOLDER_JWT = "dev-insecure-change-me"
_PLACEHOLDER_MASTER = "dev-insecure-master-key-change-me"


def _resolve_secret(value: str, placeholder: str, env_name: str) -> str:
    """Devuelve el secreto, o uno aleatorio efímero si llega el placeholder del repo.

    Cierra el riesgo de arrancar firmando JWT / derivando claves con un secreto
    público del repositorio. Para persistencia o despliegue multi-instancia hay que
    definir la variable de entorno correspondiente.
    """
    if value == placeholder:
        _log.warning(
            "%s no configurada: se usa un secreto aleatorio efímero para este "
            "proceso. Define %s (ver .env.example) para persistencia/multi-instancia.",
            env_name, env_name)
        return secrets.token_urlsafe(48)
    return value


def _ensure_audit_key(settings: Settings) -> object:
    """Carga la clave privada Ed25519 del log; la genera si no existe (dev).

    En producción la clave privada se provee por archivo ignorado / KMS. Para
    desarrollo y tests, si no hay archivo se genera un par y se guarda la pública.
    """
    from neurogate.signed_audit import (generate_keypair, private_key_to_pem,
                                         public_key_to_pem)

    priv_path = Path(settings.audit_private_key_path)
    if priv_path.exists():
        return load_private_key(priv_path.read_bytes())
    # No hay clave: generamos un par de desarrollo y persistimos ambas.
    private, public = generate_keypair()
    priv_path.parent.mkdir(parents=True, exist_ok=True)
    priv_path.write_bytes(private_key_to_pem(private))
    Path(settings.audit_public_key_path).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.audit_public_key_path).write_bytes(public_key_to_pem(public))
    return private


@dataclass
class ServiceState:
    """Estado vivo del servicio: defensas (v2) + bucle de señal + auth."""

    auth: AuthManager
    consent: ConsentFilter
    anomaly: TelemetryAnomalyDetector
    crypto: CryptoLayerV2
    audit: SignedAuditLog
    signal: SignalSource
    decoder: Decoder
    settings: Settings
    latest_intent: Intent = Intent.IDLE
    counters: dict = None  # type: ignore[assignment]
    app_status: dict = None  # type: ignore[assignment]
    pending: dict = None  # type: ignore[assignment]
    _requests_since_rotation: int = field(default=0, init=False)
    # Protege el estado compartido (log encadenado, contadores, cripto, pendientes)
    # entre el bucle de fondo, el WebSocket y los endpoints síncronos (threadpool).
    _lock: "threading.RLock" = field(default_factory=threading.RLock, init=False,
                                     repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.counters is None:
            self.counters = {"requests": 0, "allowed": 0, "blocked": 0}
        if self.app_status is None:
            self.app_status = {}
        if self.pending is None:
            # Entregas en espera de confirmación del usuario: (client_id, scope) -> motivo.
            self.pending = {}

    # --- bucle de señal (reutiliza signal v1 + decoder v1) ---

    def tick(self) -> Intent:
        """Avanza un bloque: lee señal y decodifica la intención actual."""
        with self._lock:
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
        # La telemetría siembra los scopes que la app puede pedir legítimamente.
        self.anomaly.warm_up(client_id, set(granted_scopes))
        self.app_status.setdefault(client_id, "ok")

    def prime_anomaly(self, n_per_app: int = 40, seed: int = 0) -> None:
        """Aprende un baseline de telemetría normal por app y cierra la fase.

        Genera N requests por app a ritmo normal (~1/s) con sus scopes legítimos,
        y luego entrena el Isolation Forest (modo vigilancia activo).
        """
        import numpy as np

        if not self.consent.registered_apps:
            return  # sin clientes no hay baseline que aprender (igual que la v1)
        rng = np.random.default_rng(seed)
        t = 1_000_000.0
        baseline = max(n_per_app, self.settings.anomaly_baseline_requests)
        for _ in range(baseline):
            for client_id in self.consent.registered_apps:
                t += max(0.5, rng.normal(1.0, 0.2))
                for scope in self.auth.client_scopes(client_id):
                    self.anomaly.observe(
                        TelemetryRecord(client_id, scope, t, payload_size=16),
                        learning=True)
        self.anomaly.finalize_baseline()
        self.anomaly.clear_timing()  # el baseline simulado no debe arrastrar timing a lo real

    def release_quarantine(self, app_id: str) -> None:
        """Saca una app de cuarentena (acción explícita)."""
        with self._lock:
            if self.app_status.get(app_id) == "quarantine":
                self.app_status[app_id] = "ok"

    # --- modo confirmación: cola de entregas pendientes de aprobación ---

    def approve_pending(self, client_id: str, scope: str) -> bool:
        """El operador aprueba una entrega pendiente; la app podrá recibirla una vez.

        Mapea el scope a su DataType y registra la aprobación de un solo uso en el
        ConsentFilter. Devuelve True si había un pendiente que aprobar.
        """
        from neurogate.auth import SCOPE_TO_DATATYPE

        with self._lock:
            if (client_id, scope) not in self.pending:
                return False
            dtype = SCOPE_TO_DATATYPE.get(scope)
            if dtype is not None:
                self.consent.approve_once(client_id, dtype)
            del self.pending[(client_id, scope)]
            self.audit.append(SignedAuditEvent(client_id, scope, "approve",
                                               "entrega aprobada por el usuario"))
            return True

    def deny_pending(self, client_id: str, scope: str) -> bool:
        """El operador deniega una entrega pendiente. Devuelve True si existía."""
        with self._lock:
            if (client_id, scope) not in self.pending:
                return False
            del self.pending[(client_id, scope)]
            self.audit.append(SignedAuditEvent(client_id, scope, "deny",
                                               "entrega denegada por el usuario"))
            return True

    # --- payload por tipo (igual que el Gateway v1) ---

    def _payload_for(self, data_type: DataType) -> bytes:
        if data_type is DataType.INTENT:
            return self.latest_intent.value.encode()
        if data_type is DataType.CONFIRMED_TEXT:
            return _CONFIRMED_TEXT
        if data_type is DataType.RAW_SIGNAL:
            return self.signal.get_chunk().astype("float32").tobytes()
        return b""

    # --- el pipeline de defensas, por red ---

    def serve(self, claims: TokenClaims, scope: str) -> bytes:
        """Pipeline completo para una entrega: scope→consent→anomalía→crypto→audit.

        Devuelve el sobre cifrado (CryptoLayerV2) o lanza AuthError. TODA rama
        (allow/deny/quarantine) pasa por el log firmado, sin excepciones.
        """
        with self._lock:
            client_id = claims.client_id
            dtype = self._datatype_for_scope(claims, scope)  # 403 si el scope no aplica
            request = AccessRequest(client_id, dtype)
            self.counters["requests"] += 1

            # 0. Cuarentena: una app en cuarentena no recibe nada (y se audita).
            if self.app_status.get(client_id) == "quarantine":
                self._block(client_id, scope, "quarantine", "app en cuarentena")
                raise AuthError(403, "app en cuarentena")

            # 1. Consentimiento (sin consumir la aprobación todavía).
            decision = self.consent.check(request, consume=False)
            if not decision.allowed:
                # Si falla solo por falta de confirmación, encolamos un pendiente para
                # que el operador lo apruebe/deniegue desde el dashboard (modo confirmación).
                if self.consent.requires_confirmation(dtype) and "confirmación" in decision.reason:
                    self.pending[(client_id, scope)] = decision.reason
                self._block(client_id, scope, "deny", decision.reason)
                raise AuthError(403, decision.reason)

            # 2. Anomalías sobre telemetría real (si hay baseline entrenado).
            if self.anomaly.is_trained:
                result = self.anomaly.observe(
                    TelemetryRecord(client_id, scope, request.timestamp,
                                    payload_size=len(self._payload_for(dtype))))
                if result.is_anomalous:
                    self.app_status[client_id] = "quarantine"
                    self._block(client_id, scope, "quarantine", f"anomalía: {result.reason}")
                    raise AuthError(403, f"anomalía: {result.reason}")

            # 3. Cifrado + 4. Auditoría (permitido). Recién aquí se gasta la aprobación.
            if self.consent.requires_confirmation(dtype):
                self.consent.consume_approval(client_id, dtype)
                self.pending.pop((client_id, scope), None)  # ya entregado: limpia el pendiente
            payload = self.crypto.encrypt_for(client_id, self._payload_for(dtype))
            self._maybe_rotate()
            self.counters["allowed"] += 1
            self.audit.append(SignedAuditEvent(client_id, scope, "allow", "autorizado"))
            return payload

    def _maybe_rotate(self) -> None:
        """Rota las claves de cifrado cada N requests servidos (si está configurado)."""
        every = self.settings.key_rotation_every
        if every <= 0:
            return
        self._requests_since_rotation += 1
        if self._requests_since_rotation >= every:
            self.crypto.rotate()
            self._requests_since_rotation = 0

    def _datatype_for_scope(self, claims: TokenClaims, scope: str) -> DataType:
        """Comprueba que el token tiene el scope y lo mapea a su DataType.

        Falta de scope → 403 + evento de auditoría (escalada de scopes bloqueada).
        """
        from neurogate.auth import SCOPE_TO_DATATYPE

        if scope not in claims.scopes:
            # Escalada de scopes: se audita aunque el dato nunca llegue al pipeline.
            self.counters["requests"] += 1
            self._block(claims.client_id, scope, "deny",
                        f"scope insuficiente: falta {scope}")
            raise AuthError(403, f"scope insuficiente: falta {scope}")
        dtype = SCOPE_TO_DATATYPE.get(scope)
        if dtype is None:
            # Scope sin dato neuronal (p. ej. read:stats/admin) pedido a serve():
            # también se audita, para no dejar ninguna decisión fuera del log.
            self.counters["requests"] += 1
            self._block(claims.client_id, scope, "deny",
                        f"el scope {scope} no entrega datos neuronales")
            raise AuthError(403, f"el scope {scope} no entrega datos neuronales")
        return dtype

    def _block(self, client_id: str, scope: str, decision: str, reason: str) -> None:
        """Registra el bloqueo en el log firmado (sin entregar nada)."""
        self.counters["blocked"] += 1
        self.audit.append(SignedAuditEvent(client_id, scope, decision, reason))

    def decrypt_envelope(self, claims: TokenClaims, raw: bytes) -> bytes:
        """Descifra un sobre que la app reenvía; aplica anti-replay.

        Sirve para demostrar el anti-replay extremo a extremo: reenviar un sobre
        ya consumido (replay) se rechaza con ReplayError. Toda decisión se audita.
        """
        client_id = claims.client_id
        with self._lock:
            try:
                plaintext = self.crypto.decrypt(client_id, raw)
            except ReplayError as e:
                self._block(client_id, "decrypt", "deny", f"replay: {e}")
                raise AuthError(403, f"replay rechazado: {e}")
            except (DecryptError, KeyError) as e:
                self._block(client_id, "decrypt", "deny", f"descifrado inválido: {e}")
                raise AuthError(400, f"sobre inválido: {e}")
            return plaintext

    def live_state(self) -> dict:
        """Snapshot del estado en vivo para el dashboard / admin."""
        with self._lock:
            return {
                "latest_intent": self.latest_intent.value,
                "counters": dict(self.counters),
                "app_status": dict(self.app_status),
                "clients": self.auth.clients,
                "scopes": {cid: self.auth.client_scopes(cid) for cid in self.auth.clients},
                "key_version": self.crypto.version,
                "audit_ok": self.audit.verify_chain(),
                # Entregas en espera de confirmación, como lista serializable.
                "pending": [{"client_id": cid, "scope": scope, "reason": reason}
                            for (cid, scope), reason in self.pending.items()],
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


class ReleaseRequest(BaseModel):
    """Cuerpo de POST /admin/release: saca una app de cuarentena."""

    client_id: str


class PendingRequest(BaseModel):
    """Cuerpo de POST /admin/approve y /admin/deny (modo confirmación)."""

    client_id: str
    scope: str


class DecryptRequest(BaseModel):
    """Cuerpo de POST /data/echo: un sobre cifrado (base64) que la app reenvía."""

    payload_b64: str


def build_state(settings: Settings, audit_path: Path | str) -> ServiceState:
    """Construye el estado del servicio con los bloques de la Fase D.

    Señal v1 + Decoder v1 (deterministas) para el bucle; cifrado, log y anomalías
    en sus versiones serias (crypto_v2, signed_audit, telemetry_anomaly).
    """
    seed = settings.seed
    # Nunca firmar JWT ni derivar claves con el secreto placeholder del repo.
    jwt_secret = _resolve_secret(settings.jwt_secret, _PLACEHOLDER_JWT,
                                 "NEUROGATE_JWT_SECRET")
    master_key = _resolve_secret(settings.master_key, _PLACEHOLDER_MASTER,
                                 "NEUROGATE_MASTER_KEY")
    private_key = _ensure_audit_key(settings)
    state = ServiceState(
        auth=AuthManager(jwt_secret, settings.jwt_algorithm,
                         settings.token_expire_minutes, settings.clinical_mode),
        consent=ConsentFilter(),
        anomaly=TelemetryAnomalyDetector(
            baseline_requests=settings.anomaly_baseline_requests,
            rate_spike_factor=settings.anomaly_rate_spike_factor,
            rate_window_seconds=settings.anomaly_rate_window_seconds,
            min_flood_burst=settings.anomaly_min_flood_burst, seed=seed),
        crypto=CryptoLayerV2(
            master_key=master_key.encode("utf-8"),
            replay_window_seconds=settings.replay_window_seconds,
            retained_versions=settings.retained_key_versions),
        audit=SignedAuditLog(audit_path, private_key),
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

    app = FastAPI(title="NeuroGate Gateway (Fase D)", lifespan=lifespan)
    state = build_state(settings, audit_path)
    if prime_anomaly:
        state.prime_anomaly(seed=settings.seed)
    app.state.service = state

    _register_routes(app)
    return app


# Clientes de demo para la Fase E: el dashboard y run_demo_e.py comparten estas
# credenciales (en una instalación real cada app traería las suyas por entorno).
DEMO_CLIENTS = {
    "cursor_app": ("cursor-secret-please-change", ["read:intent"]),
    "messaging_app": ("messaging-secret-please-change", ["read:confirmed_text"]),
    "reader_app": ("reader-secret-please-change", ["read:confirmed_text"]),
    "dashboard_admin": ("dashboard-admin-secret-change", ["admin", "read:stats"]),
}


def build_demo_app(settings: Settings | None = None,
                   audit_path: Path | str = "audit_service.jsonl",
                   background_loop: bool = True) -> FastAPI:
    """Crea la app con los clientes de demo ya registrados y el baseline aprendido.

    La usan el arranque local (``run_demo_e.py``) y el dashboard de la Fase E para
    tener un servicio listo: apps cliente dadas de alta, admin para el dashboard y
    detector de anomalías en vigilancia.
    """
    app = create_app(settings=settings, audit_path=audit_path,
                     background_loop=background_loop, prime_anomaly=False)
    state = app.state.service
    for client_id, (secret, scopes) in DEMO_CLIENTS.items():
        state.register_client(client_id, secret, scopes)
    state.prime_anomaly(seed=state.settings.seed)  # baseline normal -> vigilancia
    state.tick()  # una intención en memoria desde el arranque
    return app


async def _signal_loop(state: ServiceState) -> None:
    """Tarea de fondo: cicla la intención simulada y avanza señal→decoder."""
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

    @app.post("/data/echo")
    def echo_decrypt(body: DecryptRequest,
                     claims: TokenClaims = Depends(claims_from_header)) -> dict:
        """Recibe un sobre cifrado y lo descifra (demuestra anti-replay).

        Reenviar el mismo sobre dos veces (replay) se rechaza en la segunda.
        """
        state = current_state()
        try:
            raw = base64.b64decode(body.payload_b64)
            plaintext = state.decrypt_envelope(claims, raw)
        except AuthError as e:
            raise HTTPException(status_code=e.status_code, detail=e.detail)
        return {"ok": True, "length": len(plaintext)}

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

    @app.post("/admin/release")
    def admin_release(body: ReleaseRequest,
                      claims: TokenClaims = Depends(require_scope("admin"))) -> dict:
        """Saca una app de cuarentena (acción manual del operador). Requiere admin."""
        current_state().release_quarantine(body.client_id)
        return {"released": body.client_id}

    @app.post("/admin/approve")
    def admin_approve(body: PendingRequest,
                      claims: TokenClaims = Depends(require_scope("admin"))) -> dict:
        """Aprueba una entrega pendiente de confirmación (modo confirmación). Requiere admin."""
        approved = current_state().approve_pending(body.client_id, body.scope)
        return {"approved": approved, "client_id": body.client_id, "scope": body.scope}

    @app.post("/admin/deny")
    def admin_deny(body: PendingRequest,
                   claims: TokenClaims = Depends(require_scope("admin"))) -> dict:
        """Deniega una entrega pendiente de confirmación. Requiere admin."""
        denied = current_state().deny_pending(body.client_id, body.scope)
        return {"denied": denied, "client_id": body.client_id, "scope": body.scope}

    @app.websocket("/stream/intents")
    async def stream_intents(websocket: WebSocket) -> None:
        """Stream de intenciones decodificadas (requiere read:intent).

        El token se pasa como query param ``token``. Se reverifica en cada mensaje,
        de modo que revocar el token corta el stream al instante.
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
