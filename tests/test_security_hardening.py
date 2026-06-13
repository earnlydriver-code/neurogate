"""Tests de los arreglos de seguridad post-revisión (Fase D+).

Fijan como regresión los 5 hallazgos de las revisiones de QA y código:
1. No se firma/verifica con el secreto placeholder del repo (se randomiza).
2. Un JWT bien firmado pero sin client_id/exp -> 401 (no 500).
3. La rama scope→None de serve() también se audita.
4. El conjunto anti-replay (nonces) se poda y no crece sin límite.
5. El log encadenado resiste escrituras concurrentes (append atómico).
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import jwt
import pytest
from fastapi.testclient import TestClient

from neurogate.auth import AuthError, AuthManager, TokenClaims
from neurogate.config import Settings
from neurogate.crypto_v2 import CryptoLayerV2
from neurogate.service import build_state, create_app

_REAL_SECRET = "un-secreto-de-prueba-suficientemente-largo-32+"


def _settings(tmp_path, **kw):
    """Settings de prueba con claves Ed25519 en tmp (aisladas del repo)."""
    base = dict(audit_private_key_path=str(tmp_path / "priv.pem"),
                audit_public_key_path=str(tmp_path / "pub.pem"),
                master_key="master-de-prueba-larga-y-distinta")
    base.update(kw)
    return Settings(**base)


# --- 1. Secreto placeholder no se usa para firmar/verificar ---

def test_placeholder_secret_is_not_used(tmp_path):
    # Settings() deja el jwt_secret en el placeholder del repo; build_state debe
    # sustituirlo por uno aleatorio, así un token forjado con el placeholder falla.
    settings = _settings(tmp_path)  # jwt_secret queda en el default placeholder
    app = create_app(settings=settings, audit_path=tmp_path / "a.jsonl",
                     background_loop=False, prime_anomaly=False)
    forged = jwt.encode({"client_id": "x", "scopes": ["admin"], "jti": "f",
                         "exp": int(time.time()) + 100},
                        "dev-insecure-change-me", algorithm="HS256")
    with TestClient(app) as client:
        r = client.get("/admin/state", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


# --- 2. JWT sin client_id/exp -> 401, no 500 ---

def test_jwt_without_claims_is_401():
    auth = AuthManager(_REAL_SECRET)
    token = jwt.encode({"scopes": ["admin"]}, _REAL_SECRET, algorithm="HS256")
    with pytest.raises(AuthError) as e:
        auth.verify_token(token)
    assert e.value.status_code == 401


# --- 3. Rama scope→None de serve() también audita ---

def test_serve_none_scope_is_audited(tmp_path):
    settings = _settings(tmp_path, jwt_secret=_REAL_SECRET)
    app = create_app(settings=settings, audit_path=tmp_path / "a.jsonl",
                     background_loop=False, prime_anomaly=False)
    state = app.state.service
    state.register_client("statsapp", "pw", ["read:stats"])
    claims = TokenClaims("statsapp", ["read:stats"], "j", int(time.time()) + 100)
    before = state.counters["blocked"]
    with pytest.raises(AuthError) as e:
        state.serve(claims, "read:stats")  # read:stats no entrega dato neuronal
    assert e.value.status_code == 403
    assert state.counters["blocked"] == before + 1  # quedó auditado como bloqueo
    assert state.audit.verify_chain()


# --- 4. Anti-replay: los nonces se podan fuera de la ventana ---

def test_nonce_set_is_pruned():
    crypto = CryptoLayerV2(master_key=b"k" * 16, replay_window_seconds=1.0)
    crypto.register_app("app")
    # Sobre con timestamp 100; se descifra "ahora=100" -> nonce recordado.
    env1 = crypto.encrypt_for("app", b"hola", timestamp=100.0)
    crypto.decrypt("app", env1, now=100.0)
    assert len(crypto._seen_nonces) == 1
    # Otro sobre mucho después: al descifrar se podan los nonces fuera de ventana.
    env2 = crypto.encrypt_for("app", b"hola", timestamp=200.0)
    crypto.decrypt("app", env2, now=200.0)
    assert len(crypto._seen_nonces) == 1  # el viejo se olvidó, no crece sin límite


# --- 5. El log encadenado resiste escrituras concurrentes ---

def test_audit_chain_intact_under_concurrency(tmp_path):
    settings = _settings(tmp_path, jwt_secret=_REAL_SECRET)
    state = build_state(settings, tmp_path / "a.jsonl")
    state.register_client("c", "pw", ["read:confirmed_text"])
    claims = TokenClaims("c", ["read:confirmed_text"], "j", int(time.time()) + 100)

    n = 50

    def hit():
        state.serve(claims, "read:confirmed_text")

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(lambda _: hit(), range(n)))

    # Sin el append atómico, dos escrituras compartirían prev_hash y romperían la
    # cadena; con el lock, queda íntegra y todas las entregas se contaron.
    assert state.audit.verify_chain()
    assert state.counters["allowed"] == n
