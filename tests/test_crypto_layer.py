"""Tests del cifrado por app (Paso 6)."""

from __future__ import annotations

import pytest
from cryptography.fernet import InvalidToken

from neurogate.crypto_layer import CryptoLayer


def test_roundtrip_same_app():
    c = CryptoLayer()
    c.register_app("app")
    token = c.encrypt_for("app", b"secreto")
    assert c.decrypt("app", token) == b"secreto"


def test_ciphertext_differs_from_plaintext():
    c = CryptoLayer()
    c.register_app("app")
    assert c.encrypt_for("app", b"hola mundo") != b"hola mundo"


def test_other_app_cannot_decrypt():
    c = CryptoLayer()
    c.register_app("a")
    c.register_app("b")
    token = c.encrypt_for("a", b"secreto")
    with pytest.raises(InvalidToken):
        c.decrypt("b", token)


def test_unregistered_app_raises():
    with pytest.raises(KeyError):
        CryptoLayer().encrypt_for("ghost", b"x")
