"""Tests de autenticación (Fase C): emisión, verificación y revocación de JWT."""

from __future__ import annotations

import time

import jwt
import pytest

from neurogate.auth import (CLINICAL_SCOPE, AuthError, AuthManager,
                            scopes_to_datatypes)
from neurogate.consent import DataType

# Secreto de prueba de >=32 bytes (evita el warning de longitud de PyJWT).
_SECRET = "test-secret-please-change-32-bytes-minimum-xx"


def _auth(clinical: bool = False) -> AuthManager:
    a = AuthManager(_SECRET, clinical_mode=clinical)
    a.register_client("cursor_app", "pw", ["read:intent"])
    a.register_client("admin_app", "pw-admin", ["admin", "read:stats"])
    return a


def test_issue_and_verify_token():
    a = _auth()
    token, claims = a.issue_token("cursor_app", "pw")
    assert claims.scopes == ["read:intent"]
    verified = a.verify_token(token)
    assert verified.client_id == "cursor_app"
    assert verified.jti == claims.jti


def test_wrong_secret_is_401():
    a = _auth()
    with pytest.raises(AuthError) as exc:
        a.issue_token("cursor_app", "WRONG")
    assert exc.value.status_code == 401


def test_requesting_ungranted_scope_is_403():
    a = _auth()
    with pytest.raises(AuthError) as exc:
        a.issue_token("cursor_app", "pw", scopes=["admin"])
    assert exc.value.status_code == 403


def test_forged_token_is_401():
    a = _auth()
    forged = jwt.encode({"client_id": "cursor_app", "scopes": ["admin"],
                         "jti": "x", "exp": int(time.time()) + 100},
                        "OTHER-SECRET", algorithm="HS256")
    with pytest.raises(AuthError) as exc:
        a.verify_token(forged)
    assert exc.value.status_code == 401


def test_expired_token_is_401():
    a = _auth()
    expired = jwt.encode({"client_id": "cursor_app", "scopes": ["read:intent"],
                          "jti": "x", "exp": int(time.time()) - 10},
                         _SECRET, algorithm="HS256")
    with pytest.raises(AuthError) as exc:
        a.verify_token(expired)
    assert exc.value.status_code == 401


def test_revoked_token_is_blocked():
    a = _auth()
    token, claims = a.issue_token("cursor_app", "pw")
    assert a.verify_token(token).client_id == "cursor_app"  # válido al principio
    a.revoke(claims.jti)
    with pytest.raises(AuthError) as exc:
        a.verify_token(token)
    assert exc.value.status_code == 401


def test_clinical_scope_ignored_when_mode_off():
    a = AuthManager(_SECRET, clinical_mode=False)
    a.register_client("clinic", "pw", ["read:intent", CLINICAL_SCOPE])
    assert CLINICAL_SCOPE not in a.client_scopes("clinic")


def test_clinical_scope_granted_when_mode_on():
    a = AuthManager(_SECRET, clinical_mode=True)
    a.register_client("clinic", "pw", ["read:intent", CLINICAL_SCOPE])
    assert CLINICAL_SCOPE in a.client_scopes("clinic")


def test_scopes_to_datatypes_mapping():
    dtypes = scopes_to_datatypes(["read:intent", "read:confirmed_text", "admin"])
    assert dtypes == {DataType.INTENT, DataType.CONFIRMED_TEXT}  # admin no aporta dato
