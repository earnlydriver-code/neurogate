"""Tests del filtro de consentimiento (Paso 4)."""

from __future__ import annotations

from neurogate.consent import AccessRequest, ConsentFilter, DataType


def _consent():
    c = ConsentFilter()
    c.register_app("good_app", {DataType.INTENT})
    return c


def test_allowed_type_passes():
    d = _consent().check(AccessRequest("good_app", DataType.INTENT))
    assert d.allowed


def test_unpermitted_type_blocked():
    d = _consent().check(AccessRequest("good_app", DataType.RAW_SIGNAL))
    assert not d.allowed and "sin permiso" in d.reason


def test_unregistered_app_blocked():
    d = _consent().check(AccessRequest("ghost", DataType.INTENT))
    assert not d.allowed and "no registrada" in d.reason


def test_confirmation_mode_requires_approval():
    c = ConsentFilter(confirmation_mode=True)
    c.register_app("clinic", {DataType.RAW_SIGNAL})
    req = AccessRequest("clinic", DataType.RAW_SIGNAL)
    assert not c.check(req).allowed          # sin aprobación -> bloqueado
    c.approve_once("clinic", DataType.RAW_SIGNAL)
    assert c.check(req).allowed              # aprobado una vez -> pasa
    assert not c.check(req).allowed          # la aprobación ya se consumió


def test_sensitive_type_requires_approval_even_without_confirmation_mode():
    # RAW_SIGNAL exige aprobación SIEMPRE, aunque el modo confirmación esté apagado.
    c = ConsentFilter(confirmation_mode=False)
    c.register_app("clinic", {DataType.RAW_SIGNAL})
    req = AccessRequest("clinic", DataType.RAW_SIGNAL)
    assert not c.check(req).allowed
    c.approve_once("clinic", DataType.RAW_SIGNAL)
    assert c.check(req).allowed


def test_confirmation_mode_covers_every_type():
    # En modo confirmación, nada sale sin aprobación: ni siquiera INTENT.
    c = ConsentFilter(confirmation_mode=True)
    c.register_app("cursor", {DataType.INTENT})
    req = AccessRequest("cursor", DataType.INTENT)
    assert not c.check(req).allowed
    c.approve_once("cursor", DataType.INTENT)
    assert c.check(req).allowed
