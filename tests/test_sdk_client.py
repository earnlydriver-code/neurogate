"""Tests del SDK de cliente (neurogate-client).

Cubre la ruta REST/auth con un TestClient inyectado (rápido y sin red) y la ruta
WebSocket (stream de intenciones) contra un servidor uvicorn real en un hilo.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# El SDK vive en sdk/ (paquete distribuible aparte); lo ponemos en el path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sdk"))

from neurogate_client import NeuroGateClient, NeuroGateError  # noqa: E402
from neurogate.config import Settings  # noqa: E402
from neurogate.service import DEMO_CLIENTS, build_demo_app  # noqa: E402


def _settings(tmp_path):
    return Settings(jwt_secret="sdk-test-secret-largo-y-distinto-de-32+",
                    master_key="sdk-test-master-key-distinta",
                    audit_private_key_path=str(tmp_path / "priv.pem"),
                    audit_public_key_path=str(tmp_path / "pub.pem"))


# --- ruta REST/auth con TestClient inyectado ---

def test_sdk_auth_and_confirmed_text(tmp_path):
    app = build_demo_app(settings=_settings(tmp_path),
                         audit_path=tmp_path / "a.jsonl", background_loop=False)
    with TestClient(app) as tc:
        secret = DEMO_CLIENTS["messaging_app"][0]
        client = NeuroGateClient("http://test", "messaging_app", secret, http_client=tc)
        assert client.authenticate()  # token no vacío
        data = client.get_confirmed_text()
        assert data["data_type"] == "confirmed_text" and data["encrypted"] is True


def test_sdk_scope_error_is_raised(tmp_path):
    app = build_demo_app(settings=_settings(tmp_path),
                         audit_path=tmp_path / "a.jsonl", background_loop=False)
    with TestClient(app) as tc:
        secret = DEMO_CLIENTS["cursor_app"][0]  # solo read:intent
        client = NeuroGateClient("http://test", "cursor_app", secret, http_client=tc)
        with pytest.raises(NeuroGateError) as e:
            client.get_confirmed_text()  # no tiene el scope -> 403
        assert e.value.status_code == 403


def test_sdk_admin_state(tmp_path):
    app = build_demo_app(settings=_settings(tmp_path),
                         audit_path=tmp_path / "a.jsonl", background_loop=False)
    with TestClient(app) as tc:
        secret = DEMO_CLIENTS["dashboard_admin"][0]
        admin = NeuroGateClient("http://test", "dashboard_admin", secret, http_client=tc)
        state = admin.get_state()
        assert "counters" in state and "app_status" in state and "audit_ok" in state


# --- ruta WebSocket contra un uvicorn real (integración) ---

@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    import uvicorn

    tmp = tmp_path_factory.mktemp("sdk_live")
    settings = Settings(jwt_secret="sdk-live-secret-largo-y-distinto-32+",
                        master_key="sdk-live-master-key",
                        audit_private_key_path=str(tmp / "priv.pem"),
                        audit_public_key_path=str(tmp / "pub.pem"))
    app = build_demo_app(settings=settings, audit_path=tmp / "a.jsonl",
                         background_loop=True)
    config = uvicorn.Config(app, host="127.0.0.1", port=8099, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):  # esperar a que arranque (hasta ~10 s)
        if server.started:
            break
        time.sleep(0.1)
    if not server.started:
        server.should_exit = True
        pytest.skip("el servidor uvicorn no arrancó a tiempo")
    yield "http://127.0.0.1:8099"
    server.should_exit = True
    thread.join(timeout=5)


def test_sdk_stream_intents(live_server):
    secret = DEMO_CLIENTS["cursor_app"][0]
    client = NeuroGateClient(live_server, "cursor_app", secret)
    try:
        messages = list(client.stream_intents(max_messages=3))
    finally:
        client.close()
    assert len(messages) == 3
    assert all("intent" in m and m.get("encrypted") for m in messages)
