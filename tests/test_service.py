"""Tests del servicio FastAPI (Fase C): endpoints, scopes, revocación, auditoría."""

from __future__ import annotations

import time

import jwt
import pytest
from fastapi.testclient import TestClient

from neurogate.config import Settings
from neurogate.service import create_app

# Secreto de prueba de >=32 bytes (evita el warning de longitud de PyJWT).
_SECRET = "test-secret-please-change-32-bytes-minimum-xx"


@pytest.fixture()
def app(tmp_path):
    """App de prueba: secreto por fixture, sin bucle de fondo, con clientes dados de alta."""
    settings = Settings(
        jwt_secret=_SECRET, seed=0, master_key="test-master-key-fase-d",
        audit_private_key_path=str(tmp_path / "audit_priv.pem"),
        audit_public_key_path=str(tmp_path / "audit_pub.pem"))
    app = create_app(settings=settings, audit_path=tmp_path / "audit.jsonl",
                     background_loop=False, prime_anomaly=True)
    state = app.state.service
    state.register_client("cursor_app", "pw-cursor", ["read:intent"])
    state.register_client("messaging_app", "pw-msg", ["read:confirmed_text"])
    state.register_client("admin_app", "pw-admin", ["admin", "read:stats"])
    state.tick()  # una intención en memoria para servir
    return app


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


def _token(client, client_id, secret, scopes=None):
    body = {"client_id": client_id, "client_secret": secret}
    if scopes is not None:
        body["scopes"] = scopes
    r = client.post("/auth/token", json=body)
    return r


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


# --- emisión de tokens ---

def test_token_issued_to_registered_client(client):
    r = _token(client, "cursor_app", "pw-cursor")
    assert r.status_code == 200
    assert r.json()["scopes"] == ["read:intent"]


def test_token_wrong_secret_is_401(client):
    r = _token(client, "cursor_app", "WRONG")
    assert r.status_code == 401


# --- scope correcto -> 200 + datos ---

def test_confirmed_text_with_correct_scope_returns_data(client):
    tok = _token(client, "messaging_app", "pw-msg").json()["access_token"]
    r = client.get("/data/confirmed_text", headers=_bearer(tok))
    assert r.status_code == 200
    body = r.json()
    assert body["data_type"] == "confirmed_text" and body["encrypted"] is True
    assert body["payload_b64"]


# --- scope insuficiente -> 403 + evento en auditoría ---

def test_insufficient_scope_is_403_and_audited(app, client):
    tok = _token(client, "cursor_app", "pw-cursor").json()["access_token"]
    r = client.get("/data/confirmed_text", headers=_bearer(tok))
    assert r.status_code == 403
    # El bloqueo quedó registrado en el log encadenado.
    state = app.state.service
    assert state.counters["blocked"] >= 1
    assert state.audit.verify_chain()
    log_text = state.audit.path.read_text(encoding="utf-8")
    assert "scope insuficiente" in log_text or "sin permiso" in log_text


# --- token expirado -> 401 ---

def test_expired_token_is_401(client):
    expired = jwt.encode(
        {"client_id": "cursor_app", "scopes": ["read:confirmed_text"],
         "jti": "x", "exp": int(time.time()) - 10},
        _SECRET, algorithm="HS256")
    r = client.get("/data/confirmed_text", headers=_bearer(expired))
    assert r.status_code == 401


# --- token forjado (firma incorrecta) -> 401 ---

def test_forged_token_is_401(client):
    forged = jwt.encode(
        {"client_id": "cursor_app", "scopes": ["admin"],
         "jti": "x", "exp": int(time.time()) + 100},
        "OTHER-SECRET", algorithm="HS256")
    r = client.get("/admin/state", headers=_bearer(forged))
    assert r.status_code == 401


# --- token revocado -> bloqueado al instante ---

def test_revoked_token_is_blocked_immediately(client):
    issued = _token(client, "messaging_app", "pw-msg").json()
    tok, jti = issued["access_token"], issued["jti"]
    # Antes de revocar: funciona.
    assert client.get("/data/confirmed_text", headers=_bearer(tok)).status_code == 200
    # Admin revoca el jti.
    atok = _token(client, "admin_app", "pw-admin").json()["access_token"]
    rr = client.post("/admin/revoke", json={"jti": jti}, headers=_bearer(atok))
    assert rr.status_code == 200
    # Tras revocar: bloqueado al instante.
    assert client.get("/data/confirmed_text", headers=_bearer(tok)).status_code == 401


# --- admin protegido por scope ---

def test_admin_state_requires_admin_scope(client):
    tok = _token(client, "cursor_app", "pw-cursor").json()["access_token"]
    assert client.get("/admin/state", headers=_bearer(tok)).status_code == 403
    atok = _token(client, "admin_app", "pw-admin").json()["access_token"]
    assert client.get("/admin/state", headers=_bearer(atok)).status_code == 200


def test_missing_token_is_401(client):
    assert client.get("/data/confirmed_text").status_code == 401


# --- WebSocket de intenciones ---

def test_ws_intents_with_scope_streams(client):
    tok = _token(client, "cursor_app", "pw-cursor").json()["access_token"]
    with client.websocket_connect(f"/stream/intents?token={tok}") as ws:
        msg = ws.receive_json()
        assert msg["data_type"] == "intent" and msg["encrypted"] is True


def test_ws_intents_without_scope_is_rejected(client):
    tok = _token(client, "messaging_app", "pw-msg").json()["access_token"]
    with pytest.raises(Exception):
        with client.websocket_connect(f"/stream/intents?token={tok}") as ws:
            ws.receive_json()
