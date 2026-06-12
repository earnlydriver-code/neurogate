"""Tests del cifrado v2 (Fase D): HKDF por app, rotación versionada, anti-replay."""

from __future__ import annotations

import time

import pytest

from neurogate.crypto_v2 import CryptoLayerV2, DecryptError, ReplayError

_MASTER = b"clave-maestra-de-prueba-no-usar-en-produccion"


def _crypto(**kw) -> CryptoLayerV2:
    c = CryptoLayerV2(master_key=_MASTER, **kw)
    c.register_app("app_A")
    c.register_app("app_B")
    return c


def test_roundtrip_same_app():
    c = _crypto()
    env = c.encrypt_for("app_A", b"intencion: move_cursor")
    assert c.decrypt("app_A", env) == b"intencion: move_cursor"


def test_other_app_cannot_decrypt():
    """Una app no puede descifrar lo de otra (clave derivada distinta por HKDF)."""
    c = _crypto()
    env = c.encrypt_for("app_A", b"secreto", timestamp=time.time())
    with pytest.raises(DecryptError):
        c.decrypt("app_B", env, check_replay=False)


def test_unregistered_app_raises():
    c = _crypto()
    with pytest.raises(KeyError):
        c.encrypt_for("desconocida", b"x")


def test_rotation_keeps_old_messages_readable():
    """Tras rotar, un mensaje de la versión anterior aún se descifra (no corta servicio)."""
    c = _crypto(retained_versions=1)
    old = c.encrypt_for("app_A", b"viejo", timestamp=time.time())
    assert c.version == 0
    c.rotate()
    assert c.version == 1
    # El sobre viejo (v0) sigue dentro de la ventana retenida.
    assert c.decrypt("app_A", old, check_replay=False) == b"viejo"
    # Un mensaje nuevo usa la versión nueva.
    new = c.encrypt_for("app_A", b"nuevo", timestamp=time.time())
    assert c.decrypt("app_A", new, check_replay=False) == b"nuevo"


def test_rotation_drops_versions_outside_window():
    """Una versión más vieja que la ventana retenida ya no se acepta."""
    c = _crypto(retained_versions=1)
    old = c.encrypt_for("app_A", b"muy viejo", timestamp=time.time())
    c.rotate()
    c.rotate()  # ahora v2; v0 queda fuera de la ventana (solo v1 y v2)
    with pytest.raises(DecryptError):
        c.decrypt("app_A", old, check_replay=False)


def test_replay_same_envelope_is_rejected():
    """Reenviar el mismo sobre (nonce repetido) se rechaza."""
    c = _crypto()
    env = c.encrypt_for("app_A", b"hola")
    assert c.decrypt("app_A", env) == b"hola"  # primera vez OK
    with pytest.raises(ReplayError):
        c.decrypt("app_A", env)  # replay


def test_replay_timestamp_outside_window_is_rejected():
    """Un sobre con timestamp fuera de la ventana anti-replay se rechaza."""
    c = _crypto(replay_window_seconds=5.0)
    stale = c.encrypt_for("app_A", b"viejo", timestamp=time.time() - 100.0)
    with pytest.raises(ReplayError):
        c.decrypt("app_A", stale)


def test_tampered_ciphertext_fails():
    """Alterar el ciphertext rompe el tag de AES-GCM."""
    c = _crypto()
    env = bytearray(c.encrypt_for("app_A", b"hola", timestamp=time.time()))
    env[-1] ^= 0x01  # corrompe el último byte (tag)
    with pytest.raises(DecryptError):
        c.decrypt("app_A", bytes(env), check_replay=False)
