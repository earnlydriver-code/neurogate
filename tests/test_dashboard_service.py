"""Tests del dashboard de la Fase E: funciones puras + ServiceClient por ASGI.

No se testea el render de Streamlit (necesitaría navegador). Se testea la lógica
de datos: las transformaciones puras del estado y el cliente HTTP del servicio,
hablando con la app real vía httpx.ASGITransport (sin red ni navegador).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from neurogate.config import Settings
from neurogate.dashboard_service import (ADMIN_ID, ADMIN_SECRET, ServiceClient,
                                         app_rows, run_live_attack,
                                         status_icon, summarize_state)
from neurogate.service import build_demo_app

_SECRET = "test-secret-please-change-32-bytes-minimum-xx"


# --- funciones puras ---

def test_status_icon_maps_states():
    assert status_icon("ok") == "🟢"
    assert status_icon("quarantine") == "🟡"
    assert status_icon("blocked") == "🔴"
    assert status_icon("desconocido") == "⚪"


def test_summarize_state_counts():
    state = {
        "latest_intent": "move_cursor",
        "counters": {"requests": 10, "allowed": 7, "blocked": 3},
        "app_status": {"a": "ok", "b": "quarantine", "c": "ok"},
        "pending": [{"client_id": "a", "scope": "read:raw_signal", "reason": "x"}],
        "audit_ok": True,
    }
    s = summarize_state(state)
    assert s["latest_intent"] == "move_cursor"
    assert s["requests"] == 10 and s["allowed"] == 7 and s["blocked"] == 3
    assert s["apps_total"] == 3 and s["apps_ok"] == 2 and s["apps_quarantine"] == 1
    assert s["pending_count"] == 1 and s["audit_ok"] is True


def test_summarize_state_handles_empty():
    s = summarize_state({})
    assert s["requests"] == 0 and s["apps_total"] == 0 and s["audit_ok"] is False


def test_app_rows_sorted_with_scopes():
    state = {
        "app_status": {"b_app": "quarantine", "a_app": "ok"},
        "scopes": {"a_app": ["read:intent"], "b_app": ["read:confirmed_text"]},
    }
    rows = app_rows(state)
    assert [r["app_id"] for r in rows] == ["a_app", "b_app"]
    assert rows[0]["icon"] == "🟢" and rows[1]["icon"] == "🟡"
    assert rows[0]["scopes"] == ["read:intent"]


# --- ServiceClient contra la app real (ASGI, sin red) ---

@pytest.fixture()
def svc_client(tmp_path):
    """Cliente del dashboard apuntando a la app de demo vía ASGITransport."""
    settings = Settings(
        jwt_secret=_SECRET, seed=0, master_key="test-master-key-fase-e",
        anomaly_baseline_requests=20, anomaly_rate_spike_factor=10.0,
        audit_private_key_path=str(tmp_path / "priv.pem"),
        audit_public_key_path=str(tmp_path / "pub.pem"))
    app = build_demo_app(settings=settings, audit_path=tmp_path / "audit.jsonl",
                         background_loop=False)
    # Inyectamos un TestClient (es un httpx.Client) como transporte: sin red real.
    with TestClient(app) as http_client:
        client = ServiceClient("http://test", admin_id=ADMIN_ID,
                               admin_secret=ADMIN_SECRET, http_client=http_client)
        yield client


def test_client_authenticates_and_reads_state(svc_client):
    state = svc_client.get_state()
    assert "counters" in state and "app_status" in state
    # Los clientes de demo aparecen en el estado.
    assert "cursor_app" in state["app_status"]
    assert state["audit_ok"] is True


def test_client_state_includes_scopes(svc_client):
    state = svc_client.get_state()
    assert state["scopes"]["cursor_app"] == ["read:intent"]


def test_run_live_attack_blocks_and_quarantines(svc_client):
    result = run_live_attack(svc_client)
    # El ataque narra varios bloqueos y deja la app atacada en cuarentena.
    assert any("BLOQUEADO" in ln for ln in result["lines"])
    assert result["quarantined"] is True
    state = svc_client.get_state()
    assert state["app_status"][result["attacked"]] == "quarantine"
    assert state["audit_ok"] is True  # todo el ataque quedó auditado e íntegro


def test_release_clears_quarantine(svc_client):
    result = run_live_attack(svc_client)
    attacked = result["attacked"]
    assert svc_client.get_state()["app_status"][attacked] == "quarantine"
    svc_client.release(attacked)
    assert svc_client.get_state()["app_status"][attacked] == "ok"
