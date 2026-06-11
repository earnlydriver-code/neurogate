"""Tests de integración del gateway (Paso 8)."""

from __future__ import annotations

from neurogate.consent import AccessRequest, DataType
from neurogate.crypto_layer import CryptoLayer  # noqa: F401  (documenta el stack)
from neurogate.gateway import build_demo_gateway


def _gw(tmp_path):
    return build_demo_gateway(audit_path=tmp_path / "audit.jsonl")


def test_legit_request_returns_encrypted_payload(tmp_path):
    gw = _gw(tmp_path)
    gw.tick()
    resp = gw.handle_request(AccessRequest("cursor_app", DataType.INTENT, 2_000_000.0))
    assert resp.allowed and resp.payload is not None


def test_unpermitted_type_is_blocked(tmp_path):
    gw = _gw(tmp_path)
    resp = gw.handle_request(AccessRequest("cursor_app", DataType.RAW_SIGNAL, 2_000_000.0))
    assert not resp.allowed and resp.payload is None


def test_burst_is_quarantined(tmp_path):
    gw = _gw(tmp_path)
    t, blocked = 2_000_000.0, 0
    for _ in range(15):
        t += 0.02
        blocked += not gw.handle_request(AccessRequest("cursor_app", DataType.INTENT, t)).allowed
    assert blocked >= 10
    assert gw.app_status["cursor_app"] == "quarantine"


def test_everything_is_audited_and_chain_intact(tmp_path):
    gw = _gw(tmp_path)
    gw.handle_request(AccessRequest("cursor_app", DataType.INTENT, 2_000_000.0))
    gw.handle_request(AccessRequest("cursor_app", DataType.RAW_SIGNAL, 2_000_001.0))
    assert gw.counters["requests"] == 2
    assert gw.audit.verify_chain()
