"""Tests del modo confirmación del servicio (Fase E): cola pendiente + approve/deny.

Un scope sensible (read:raw_signal, en modo clínico) exige aprobación explícita.
La primera solicitud sin aprobación encola un pendiente (403); el admin lo aprueba
desde /admin/approve y la siguiente entrega sale; o lo deniega y el pendiente se va.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from neurogate.config import Settings
from neurogate.service import create_app

_SECRET = "test-secret-please-change-32-bytes-minimum-xx"


@pytest.fixture()
def client(tmp_path):
    """Servicio en modo clínico con una app que tiene read:raw_signal (scope sensible)."""
    settings = Settings(
        jwt_secret=_SECRET, seed=0, master_key="test-master-key-fase-e",
        clinical_mode=True,
        audit_private_key_path=str(tmp_path / "priv.pem"),
        audit_public_key_path=str(tmp_path / "pub.pem"))
    app = create_app(settings=settings, audit_path=tmp_path / "audit.jsonl",
                     background_loop=False, prime_anomaly=False)
    state = app.state.service
    state.register_client("clinic_app", "pw-clinic", ["read:raw_signal"])
    state.register_client("admin_app", "pw-admin", ["admin"])
    state.tick()
    with TestClient(app) as c:
        c.state = state  # type: ignore[attr-defined]
        yield c


def _token(client, cid, secret):
    return client.post("/auth/token",
                       json={"client_id": cid, "client_secret": secret}).json()["access_token"]


def _bearer(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_sensitive_request_without_approval_queues_pending(client):
    """Pedir un scope sensible sin aprobación da 403 y deja un pendiente en /admin/state."""
    tok = _token(client, "clinic_app", "pw-clinic")
    # WS de raw_signal no existe; raw_signal se sirve por el pipeline. Forzamos el
    # pipeline directamente a través del estado para reflejar el flujo real.
    state = client.state  # type: ignore[attr-defined]
    from neurogate.auth import TokenClaims
    claims = TokenClaims("clinic_app", ["read:raw_signal"], "j", 9_999_999_999)
    with pytest.raises(Exception):
        state.serve(claims, "read:raw_signal")  # sin aprobar -> 403 + pendiente

    atok = _token(client, "admin_app", "pw-admin")
    pending = client.get("/admin/state", headers=_bearer(atok)).json()["pending"]
    assert any(p["client_id"] == "clinic_app" and p["scope"] == "read:raw_signal"
               for p in pending)


def test_approve_lets_the_next_delivery_through(client):
    state = client.state  # type: ignore[attr-defined]
    from neurogate.auth import TokenClaims
    claims = TokenClaims("clinic_app", ["read:raw_signal"], "j", 9_999_999_999)
    with pytest.raises(Exception):
        state.serve(claims, "read:raw_signal")

    atok = _token(client, "admin_app", "pw-admin")
    r = client.post("/admin/approve",
                    json={"client_id": "clinic_app", "scope": "read:raw_signal"},
                    headers=_bearer(atok))
    assert r.status_code == 200 and r.json()["approved"] is True

    # Tras aprobar, la entrega sale y el pendiente desaparece.
    payload = state.serve(claims, "read:raw_signal")
    assert payload  # sobre cifrado
    pending = client.get("/admin/state", headers=_bearer(atok)).json()["pending"]
    assert not pending


def test_deny_removes_the_pending(client):
    state = client.state  # type: ignore[attr-defined]
    from neurogate.auth import TokenClaims
    claims = TokenClaims("clinic_app", ["read:raw_signal"], "j", 9_999_999_999)
    with pytest.raises(Exception):
        state.serve(claims, "read:raw_signal")

    atok = _token(client, "admin_app", "pw-admin")
    r = client.post("/admin/deny",
                    json={"client_id": "clinic_app", "scope": "read:raw_signal"},
                    headers=_bearer(atok))
    assert r.status_code == 200 and r.json()["denied"] is True
    pending = client.get("/admin/state", headers=_bearer(atok)).json()["pending"]
    assert not pending


def test_approve_requires_admin_scope(client):
    tok = _token(client, "clinic_app", "pw-clinic")  # no admin
    r = client.post("/admin/approve",
                    json={"client_id": "clinic_app", "scope": "read:raw_signal"},
                    headers=_bearer(tok))
    assert r.status_code == 403


def test_approve_nonexistent_pending_is_false(client):
    atok = _token(client, "admin_app", "pw-admin")
    r = client.post("/admin/approve",
                    json={"client_id": "clinic_app", "scope": "read:raw_signal"},
                    headers=_bearer(atok))
    assert r.status_code == 200 and r.json()["approved"] is False
