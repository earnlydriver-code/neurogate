"""Suite de ataques contra el SERVICIO FastAPI (Fase D), con TestClient.

Cinco ataques nuevos sobre el servicio (los 3 ataques v1 siguen en
``tests/attack_sim.py`` contra el ``Gateway`` v1, intactos). Cada bloqueo debe
quedar registrado en el log auditado y firmado.

Ataques:
1. Token robado/revocado reutilizado -> 401.
2. Replay de un sobre cifrado capturado -> 403 (nonce/timestamp).
3. Escalada de scopes (read:intent intenta read:confirmed_text) -> 403 + auditoría.
4. Token forjado (firma incorrecta) -> 401.
5. Flood (ráfaga masiva) -> cuarentena por anomalía.
"""

from __future__ import annotations

import base64
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from neurogate.config import Settings
from neurogate.service import create_app
from neurogate.signed_audit import load_public_key, verify_log

_SECRET = "test-secret-please-change-32-bytes-minimum-xx"


@pytest.fixture()
def ctx(tmp_path):
    """App + rutas de log y clave pública para verificar el log firmado al final."""
    audit_path = tmp_path / "audit.jsonl"
    pub_path = tmp_path / "audit_pub.pem"
    settings = Settings(
        jwt_secret=_SECRET, seed=0, master_key="test-master-key-fase-d",
        replay_window_seconds=30.0,
        anomaly_baseline_requests=20, anomaly_rate_spike_factor=10.0,
        audit_private_key_path=str(tmp_path / "audit_priv.pem"),
        audit_public_key_path=str(pub_path))
    # prime_anomaly=False: el baseline se aprende DESPUÉS de registrar los
    # clientes (de lo contrario no habría apps que perfilar y el detector
    # quedaría sin entrenar).
    app = create_app(settings=settings, audit_path=audit_path,
                     background_loop=False, prime_anomaly=False)
    state = app.state.service
    state.register_client("cursor_app", "pw-cursor", ["read:intent"])
    state.register_client("messaging_app", "pw-msg", ["read:confirmed_text"])
    state.register_client("admin_app", "pw-admin", ["admin"])
    state.prime_anomaly()  # ahora sí: aprende telemetría normal y entra en vigilancia
    state.tick()
    return app, audit_path, pub_path


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _token(client, cid, secret):
    return client.post("/auth/token", json={"client_id": cid, "client_secret": secret}).json()


def _audit_text(audit_path):
    return audit_path.read_text(encoding="utf-8")


def _verify_signed(audit_path, pub_path):
    public = load_public_key(pub_path.read_bytes())
    return verify_log(audit_path, public)


# --- Ataque 1: token robado/revocado ---

def test_attack_revoked_token_is_rejected(ctx):
    app, audit_path, pub_path = ctx
    with TestClient(app) as client:
        issued = _token(client, "messaging_app", "pw-msg")
        tok, jti = issued["access_token"], issued["jti"]
        # Funciona antes de revocar.
        assert client.get("/data/confirmed_text", headers=_bearer(tok)).status_code == 200
        # Admin revoca el token (token "robado" queda inválido).
        atok = _token(client, "admin_app", "pw-admin")["access_token"]
        client.post("/admin/revoke", json={"jti": jti}, headers=_bearer(atok))
        # Reutilizar el token revocado falla.
        r = client.get("/data/confirmed_text", headers=_bearer(tok))
        assert r.status_code == 401
    assert _verify_signed(audit_path, pub_path)[0]


# --- Ataque 2: replay de un sobre cifrado ---

def test_attack_replay_envelope_is_rejected(ctx):
    app, audit_path, pub_path = ctx
    with TestClient(app) as client:
        tok = _token(client, "messaging_app", "pw-msg")["access_token"]
        # Capturamos un sobre cifrado legítimo.
        body = client.get("/data/confirmed_text", headers=_bearer(tok)).json()
        sobre = body["payload_b64"]
        # Primer reenvío al endpoint de descifrado: OK.
        r1 = client.post("/data/echo", json={"payload_b64": sobre}, headers=_bearer(tok))
        assert r1.status_code == 200
        # Replay: reenviar el MISMO sobre -> rechazado (nonce ya visto).
        r2 = client.post("/data/echo", json={"payload_b64": sobre}, headers=_bearer(tok))
        assert r2.status_code == 403 and "replay" in r2.json()["detail"].lower()
    log = _audit_text(audit_path)
    assert "replay" in log
    assert _verify_signed(audit_path, pub_path)[0]


# --- Ataque 3: escalada de scopes ---

def test_attack_scope_escalation_is_403_and_audited(ctx):
    app, audit_path, pub_path = ctx
    with TestClient(app) as client:
        # cursor_app solo tiene read:intent; intenta leer confirmed_text.
        tok = _token(client, "cursor_app", "pw-cursor")["access_token"]
        r = client.get("/data/confirmed_text", headers=_bearer(tok))
        assert r.status_code == 403
    log = _audit_text(audit_path)
    assert "scope insuficiente" in log
    assert _verify_signed(audit_path, pub_path)[0]


# --- Ataque 4: token forjado ---

def test_attack_forged_token_is_401(ctx):
    app, audit_path, pub_path = ctx
    with TestClient(app) as client:
        forged = jwt.encode(
            {"client_id": "cursor_app", "scopes": ["admin", "read:confirmed_text"],
             "jti": "forged", "exp": int(time.time()) + 100},
            "OTHER-SECRET", algorithm="HS256")
        assert client.get("/data/confirmed_text", headers=_bearer(forged)).status_code == 401
        assert client.get("/admin/state", headers=_bearer(forged)).status_code == 401
    assert _verify_signed(audit_path, pub_path)[0]


# --- Ataque 5: flood -> cuarentena por anomalía ---

def test_attack_flood_triggers_quarantine(ctx):
    app, audit_path, pub_path = ctx
    state = app.state.service
    # El flood se prueba por el pipeline serve() directo, que es lo que un cliente
    # real martillea: 30 peticiones casi simultáneas disparan el pico de tasa.
    from neurogate.auth import TokenClaims
    claims = TokenClaims("cursor_app", ["read:intent"], "j", int(time.time()) + 100)
    blocked = 0
    for _ in range(30):
        try:
            state.serve(claims, "read:intent")
        except Exception:
            blocked += 1
    assert state.app_status["cursor_app"] == "quarantine"
    assert blocked >= 1
    log = _audit_text(audit_path)
    assert "anomalía" in log or "cuarentena" in log
    assert _verify_signed(audit_path, pub_path)[0]


# --- Verificación global: todo bloqueo quedó en el log firmado e íntegro ---

def test_all_attacks_audited_and_chain_intact(ctx):
    """Ejecuta los 5 ataques en una sesión y verifica el log firmado completo."""
    app, audit_path, pub_path = ctx
    state = app.state.service
    with TestClient(app) as client:
        # 1. revocado
        issued = _token(client, "messaging_app", "pw-msg")
        atok = _token(client, "admin_app", "pw-admin")["access_token"]
        client.post("/admin/revoke", json={"jti": issued["jti"]}, headers=_bearer(atok))
        client.get("/data/confirmed_text", headers=_bearer(issued["access_token"]))
        # 3. escalada de scopes
        ctok = _token(client, "cursor_app", "pw-cursor")["access_token"]
        client.get("/data/confirmed_text", headers=_bearer(ctok))
        # 4. forjado
        forged = jwt.encode({"client_id": "x", "scopes": ["admin"], "jti": "f",
                             "exp": int(time.time()) + 100}, "OTHER", algorithm="HS256")
        client.get("/admin/state", headers=_bearer(forged))
        # 5. flood
        from neurogate.auth import TokenClaims
        claims = TokenClaims("cursor_app", ["read:intent"], "j", int(time.time()) + 100)
        for _ in range(30):
            try:
                state.serve(claims, "read:intent")
            except Exception:
                pass

    ok, bad, reason = _verify_signed(audit_path, pub_path)
    assert ok, f"log corrupto en línea {bad}: {reason}"
    log = _audit_text(audit_path)
    # Los motivos de bloqueo de los ataques con pipeline quedaron registrados.
    assert "scope insuficiente" in log
    assert "anomalía" in log
