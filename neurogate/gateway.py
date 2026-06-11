"""Gateway: une todo el flujo. Pipeline por solicitud:

    1. consent  ¿tiene permiso?
    2. anomaly  ¿comportamiento normal?
    3. crypto   cifrar lo que sale
    4. audit    registrar todo, pase lo que pase
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from neurogate.anomaly import AnomalyDetector
from neurogate.audit import AuditEvent, AuditLog
from neurogate.consent import AccessRequest, ConsentFilter, DataType
from neurogate.crypto_layer import CryptoLayer
from neurogate.decoder import Decoder, Intent
from neurogate.signal_source import SignalSource

# Texto de ejemplo que el usuario habría confirmado (placeholder de v1).
_CONFIRMED_TEXT = b"<texto confirmado por el usuario>"


@lru_cache(maxsize=4)
def _trained_decoder(seed: int) -> Decoder:
    """Decoder entrenado y cacheado: mismo seed -> mismo modelo, sin reentrenar.

    Tras train() el decoder solo predice (no muta), así que compartirlo entre
    gateways es seguro y ahorra ~2 s por construcción (tests, reinicios de demo).
    """
    decoder = Decoder()
    decoder.train(seed=seed)
    return decoder


@dataclass(frozen=True)
class GatewayResponse:
    """Lo que recibe una app tras su solicitud."""

    allowed: bool
    payload: bytes | None  # dato cifrado si se permitió; None si se bloqueó
    reason: str


class Gateway:
    """Orquesta señal, decoder y las cuatro defensas."""

    def __init__(self, audit_path: Path | str = "audit_log.jsonl", seed: int = 0) -> None:
        self.signal = SignalSource(seed=seed)
        self.decoder = _trained_decoder(seed)
        self.consent = ConsentFilter()
        self.anomaly = AnomalyDetector(seed=seed)
        self.crypto = CryptoLayer()
        self.audit = AuditLog(audit_path)
        self._latest_intent = Intent.IDLE
        self._latest_chunk: np.ndarray | None = None
        self.counters = {"requests": 0, "allowed": 0, "blocked": 0}
        self.app_status: dict[str, str] = {}  # app_id -> "ok" | "quarantine"

    # --- registro y preparación ---

    def register_app(self, app_id: str, allowed_types: set[DataType]) -> bytes:
        """Registra una app en consent y crypto; devuelve su clave de cifrado."""
        self.consent.register_app(app_id, allowed_types)
        key = self.crypto.register_app(app_id)
        # Siembra sus tipos permitidos como vistos (no cae en la regla de novedad).
        self.anomaly.warm_up(app_id, allowed_types)
        # No toca el estado de un app_id ya existente: re-registrarse no limpia cuarentenas.
        self.app_status.setdefault(app_id, "ok")
        return key

    def release_quarantine(self, app_id: str) -> None:
        """Salida de cuarentena solo por esta acción explícita."""
        if self.app_status.get(app_id) == "quarantine":
            self.app_status[app_id] = "ok"

    def prime_anomaly(self, n_per_app: int = 200, seed: int = 0) -> None:
        """Construye un baseline de accesos normales para cada app y entrena el detector."""
        rng = np.random.default_rng(seed)
        t, history = 1_000_000.0, []
        for _ in range(n_per_app):
            for app_id in self.consent.registered_apps:
                t += max(0.3, rng.normal(1.0, 0.3))
                for dtype in self.consent.permissions_of(app_id):
                    history.append(AccessRequest(app_id, dtype, t))
        self.anomaly.fit(history)
        self.anomaly.clear_timing()  # el baseline no debe arrastrar timing a lo real

    # --- bucle de señal ---

    def tick(self) -> Intent:
        """Avanza un bloque: lee señal y decodifica la intención actual."""
        self._latest_chunk = self.signal.get_chunk()
        self._latest_intent = self.decoder.decode(self._latest_chunk)
        return self._latest_intent

    def _payload_for(self, data_type: DataType) -> bytes:
        """El dato en claro que correspondería a cada tipo (antes de cifrar)."""
        if data_type is DataType.INTENT:
            return self._latest_intent.value.encode()
        if data_type is DataType.CONFIRMED_TEXT:
            return _CONFIRMED_TEXT
        if data_type is DataType.RAW_SIGNAL:
            chunk = self._latest_chunk if self._latest_chunk is not None else self.signal.get_chunk()
            return chunk.astype("float32").tobytes()
        return b""

    # --- el pipeline de defensas ---

    def handle_request(self, request: AccessRequest) -> GatewayResponse:
        """Procesa una solicitud por todo el pipeline de defensas."""
        self.counters["requests"] += 1

        # 0. Cuarentena: una app en cuarentena no recibe nada (y todo se audita).
        if self.app_status.get(request.app_id) == "quarantine":
            return self._block(request, "app en cuarentena")

        # 1. Consentimiento (sin consumir la aprobación todavía).
        decision = self.consent.check(request, consume=False)
        if not decision.allowed:
            return self._block(request, decision.reason)

        # 2. Anomalías (si hay baseline entrenado).
        if self.anomaly.is_trained:
            result = self.anomaly.score(request)
            if result.is_anomalous:
                self.app_status[request.app_id] = "quarantine"
                return self._block(request, f"anomalía: {result.reason}")

        # 3. Cifrado + 4. Auditoría (permitido). Recién aquí se gasta la
        # aprobación de un uso: el dato sí va a salir.
        if self.consent.requires_confirmation(request.data_type):
            self.consent.consume_approval(request.app_id, request.data_type)
        payload = self.crypto.encrypt_for(request.app_id, self._payload_for(request.data_type))
        self.counters["allowed"] += 1
        self.audit.append(AuditEvent(request.app_id, request.data_type.value,
                                     True, "autorizado", request.timestamp))
        return GatewayResponse(True, payload, "autorizado")

    def _block(self, request: AccessRequest, reason: str) -> GatewayResponse:
        """Registra el bloqueo en auditoría y devuelve respuesta denegada."""
        self.counters["blocked"] += 1
        self.audit.append(AuditEvent(request.app_id, request.data_type.value,
                                     False, reason, request.timestamp))
        return GatewayResponse(False, None, reason)

    def get_live_state(self) -> dict:
        """Snapshot del estado en vivo para el dashboard."""
        chunk = self._latest_chunk
        return {
            "latest_intent": self._latest_intent.value,
            "signal": chunk.tolist() if chunk is not None else [],
            "counters": dict(self.counters),
            "app_status": dict(self.app_status),
            "audit_ok": self.audit.verify_chain(),
        }


def build_demo_gateway(audit_path: Path | str = "audit_log.jsonl", seed: int = 0) -> Gateway:
    """Gateway listo para demo: apps legítimas registradas y baseline entrenado."""
    gw = Gateway(audit_path=audit_path, seed=seed)
    gw.register_app("cursor_app", {DataType.INTENT})
    gw.register_app("messaging_app", {DataType.CONFIRMED_TEXT})
    gw.prime_anomaly(seed=seed)
    return gw


def _demo() -> None:
    """Flujo completo en terminal: señal -> intención -> apps legítima y maliciosa."""
    demos = Path(__file__).resolve().parent.parent / "demos"
    demos.mkdir(exist_ok=True)
    audit_path = demos / "step8_gateway_audit.jsonl"
    audit_path.unlink(missing_ok=True)

    gw = build_demo_gateway(audit_path=audit_path)
    gw.register_app("evil_app", {DataType.CONFIRMED_TEXT})  # permisos mínimos

    lines = []
    # Unos ticks de señal -> intención.
    for _ in range(3):
        gw.signal.set_intent("move_cursor")
        lines.append(f"señal -> intención decodificada: {gw.tick().value}")
    lines.append("")

    base = 2_000_000.0
    pruebas = [
        ("cursor_app", DataType.INTENT, "app legítima pide intención"),
        ("messaging_app", DataType.CONFIRMED_TEXT, "app legítima pide texto"),
        ("evil_app", DataType.RAW_SIGNAL, "maliciosa pide señal cruda (sin permiso)"),
    ]
    for i, (app, dtype, desc) in enumerate(pruebas):
        resp = gw.handle_request(AccessRequest(app, dtype, base + i))
        estado = "PERMITIDO" if resp.allowed else "BLOQUEADO"
        extra = f"{len(resp.payload)} bytes cifrados" if resp.payload else resp.reason
        lines.append(f"[{estado}] {desc:42s} -> {extra}")

    # Ataque de ráfaga: la app maliciosa inunda de peticiones (anomalía).
    flagged = 0
    t = base + 100.0
    for _ in range(15):
        t += 0.02
        r = gw.handle_request(AccessRequest("evil_app", DataType.CONFIRMED_TEXT, t))
        flagged += (not r.allowed)
    lines.append(f"[{'BLOQUEADO' if flagged else 'PERMITIDO'}] ráfaga de 15 peticiones "
                 f"de evil_app{'':16s} -> {flagged}/15 frenadas por anomalía")

    lines.append("")
    lines.append(f"contadores: {gw.counters}")
    lines.append(f"estado apps: {gw.app_status}")
    lines.append(f"integridad del log de auditoría: "
                 f"{'INTEGRO' if gw.audit.verify_chain() else 'ALTERADO'}")

    report = "Paso 8 — gateway (flujo completo)\n" + "=" * 60 + "\n" + "\n".join(lines) + "\n"
    (demos / "step8_gateway.txt").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    _demo()
