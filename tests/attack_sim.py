"""App maliciosa: los tres ataques que NeuroGate debe detener, como tests pytest.

También expone simulate_attack(gateway) para el botón "Simular ataque" del
dashboard (Paso 10): lanza los ataques contra un gateway en vivo y narra qué
pasó.
"""

from __future__ import annotations

import json
import time

from neurogate.consent import AccessRequest, DataType
from neurogate.gateway import Gateway, GatewayResponse, build_demo_gateway


class MaliciousApp:
    """Se registra con permisos mínimos y luego intenta excederlos."""

    def __init__(self, gateway: Gateway, app_id: str = "evil_app") -> None:
        self.gateway = gateway
        self.app_id = app_id
        gateway.register_app(app_id, {DataType.CONFIRMED_TEXT})  # solo lo mínimo

    def request(self, data_type: DataType, timestamp: float | None = None) -> GatewayResponse:
        ts = timestamp if timestamp is not None else time.time()
        return self.gateway.handle_request(AccessRequest(self.app_id, data_type, ts))


# --------------------------- Tests de ataque ---------------------------

def test_raw_signal_theft_is_blocked(tmp_path):
    """Ataque 1: pedir RAW_SIGNAL sin permiso -> bloqueado y auditado."""
    gw = build_demo_gateway(audit_path=tmp_path / "audit.jsonl")
    evil = MaliciousApp(gw)
    resp = evil.request(DataType.RAW_SIGNAL, timestamp=1.0)
    assert not resp.allowed and resp.payload is None
    assert gw.counters["blocked"] == 1
    assert gw.audit.verify_chain()


def test_burst_access_triggers_anomaly_alert(tmp_path):
    """Ataque 2: ráfaga de solicitudes -> el detector de anomalías la frena."""
    gw = build_demo_gateway(audit_path=tmp_path / "audit.jsonl")
    evil = MaliciousApp(gw)
    t, blocked = 1.0, 0
    for _ in range(20):
        t += 0.02
        blocked += not evil.request(DataType.CONFIRMED_TEXT, timestamp=t).allowed
    assert blocked >= 12  # la mayor parte de la ráfaga, frenada
    assert gw.app_status[evil.app_id] == "quarantine"


def test_command_injection_is_rejected_and_logged(tmp_path):
    """Ataque 3: inyectar contenido para forjar el log -> inerte, y registrado."""
    audit_path = tmp_path / "audit.jsonl"
    gw = build_demo_gateway(audit_path=audit_path)
    # app_id con una entrada de log falsa embebida (intento de inyección).
    forged = json.dumps({"event": {"app_id": "x", "data_type": "raw_signal",
                                    "allowed": True, "reason": "forged", "timestamp": 0.0},
                         "prev_hash": "0" * 64, "hash": "deadbeef"})
    evil_id = "evil\n" + forged
    gw.register_app(evil_id, {DataType.CONFIRMED_TEXT})
    resp = gw.handle_request(AccessRequest(evil_id, DataType.RAW_SIGNAL, 1.0))

    assert not resp.allowed                       # bloqueado por permiso
    assert gw.audit.verify_chain()                # la cadena sigue íntegra
    # Cada línea del log es exactamente un registro JSON: no se coló una línea forjada.
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event"]["allowed"] is False


# --------------------- Reutilizable por el dashboard ---------------------

def simulate_attack(gateway: Gateway, app_id: str = "evil_app") -> list[str]:
    """Lanza los ataques contra un gateway en vivo y narra el resultado."""
    narration = []
    evil = MaliciousApp(gateway, app_id=app_id)

    r = evil.request(DataType.RAW_SIGNAL)
    narration.append(f"Ataque 1 (robo de señal cruda): "
                     f"{'BLOQUEADO' if not r.allowed else 'PASÓ (fallo)'} — {r.reason}")

    t, blocked = time.time(), 0
    for _ in range(20):
        t += 0.02
        blocked += not evil.request(DataType.CONFIRMED_TEXT, timestamp=t).allowed
    narration.append(f"Ataque 2 (ráfaga de 20 peticiones): {blocked}/20 frenadas; "
                     f"estado de la app: {gateway.app_status.get(app_id)}")

    narration.append(f"Log de auditoría tras los ataques: "
                     f"{'ÍNTEGRO' if gateway.audit.verify_chain() else 'ALTERADO'}")
    return narration
