"""Tests de regresión de la revisión de código (hallazgos 1-4).

Escritos ANTES de los arreglos: deben fallar contra el código revisado y
quedar en verde tras los fixes.
"""

from __future__ import annotations

from neurogate.consent import AccessRequest, DataType
from neurogate.gateway import build_demo_gateway


def _gw(tmp_path):
    return build_demo_gateway(audit_path=tmp_path / "audit.jsonl")


def test_f1_long_pause_is_not_anomalous(tmp_path):
    """Hallazgo 1: una pausa larga (ritmo humano) jamás es ataque."""
    gw = _gw(tmp_path)
    assert gw.handle_request(AccessRequest("cursor_app", DataType.INTENT, 2_000_000.0)).allowed
    # 30 s después (usuario clicando a ritmo humano) debe seguir permitido.
    r = gw.handle_request(AccessRequest("cursor_app", DataType.INTENT, 2_000_030.0))
    assert r.allowed, f"pausa larga marcada como ataque: {r.reason}"
    assert gw.app_status["cursor_app"] == "ok"


def test_f2_new_app_with_permission_is_not_blocked(tmp_path):
    """Hallazgo 2: app legítima registrada tras el baseline no debe quedar inutilizada."""
    gw = _gw(tmp_path)
    gw.register_app("new_legit_app", {DataType.INTENT})
    r = gw.handle_request(AccessRequest("new_legit_app", DataType.INTENT, 2_000_000.0))
    assert r.allowed, f"app nueva con permiso bloqueada: {r.reason}"


def test_f3_quarantine_blocks_and_survives_reregistration(tmp_path):
    """Hallazgo 3: la cuarentena bloquea de verdad y solo se sale por acción explícita."""
    gw = _gw(tmp_path)
    t = 2_000_000.0
    for _ in range(15):  # ráfaga -> cuarentena
        t += 0.02
        gw.handle_request(AccessRequest("cursor_app", DataType.INTENT, t))
    assert gw.app_status["cursor_app"] == "quarantine"

    # En cuarentena, incluso a ritmo normal, todo se rechaza (y se audita).
    before = gw.counters["blocked"]
    r = gw.handle_request(AccessRequest("cursor_app", DataType.INTENT, t + 1.0))
    assert not r.allowed, "app en cuarentena recibió datos"
    assert gw.counters["blocked"] == before + 1  # el rechazo quedó auditado

    # Re-registrarse NO limpia la cuarentena.
    gw.register_app("cursor_app", {DataType.INTENT})
    assert gw.app_status["cursor_app"] == "quarantine"

    # Salida solo explícita.
    gw.release_quarantine("cursor_app")
    assert gw.app_status["cursor_app"] == "ok"
    assert gw.handle_request(AccessRequest("cursor_app", DataType.INTENT, t + 3.0)).allowed


def test_f4_each_dashboard_session_gets_own_audit_file():
    """Hallazgo 4: cada sesión del dashboard usa su propio archivo de auditoría."""
    from neurogate import dashboard

    p1 = dashboard.new_session_audit_path()
    p2 = dashboard.new_session_audit_path()
    assert p1 != p2  # dos sesiones jamás comparten archivo
