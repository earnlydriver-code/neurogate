"""Tests del generador de informe de cumplimiento (MVP)."""

from __future__ import annotations

import json

import compliance_report as cr
from neurogate.signed_audit import (SignedAuditEvent, SignedAuditLog,
                                     generate_keypair)


def _make_log(tmp_path):
    """Crea un log firmado con eventos variados y devuelve (ruta, clave pública)."""
    private, public = generate_keypair()
    path = tmp_path / "audit.jsonl"
    log = SignedAuditLog(path, private)
    log.append(SignedAuditEvent("cursor_app", "read:intent", "allow", "autorizado", 1000.0))
    log.append(SignedAuditEvent("cursor_app", "read:confirmed_text", "deny",
                                "scope insuficiente", 1001.0))
    log.append(SignedAuditEvent("evil_app", "read:intent", "quarantine", "anomalía: flood", 1002.0))
    log.append(SignedAuditEvent("msg_app", "read:raw_signal", "approve",
                                "aprobado por el usuario", 1003.0))
    return path, public


def test_report_on_intact_log(tmp_path):
    path, public = _make_log(tmp_path)
    report = cr.build_report(path, public, org="Lab X")
    assert report["integrity"]["ok"] is True
    assert report["summary"]["total_events"] == 4
    bd = report["summary"]["by_decision"]
    assert bd == {"allow": 1, "deny": 1, "quarantine": 1, "approve": 1}
    # Cada decisión presente tiene su mapeo legal.
    assert set(report["legal_mapping"]) == {"allow", "deny", "quarantine", "approve"}
    assert report["last_hash"]


def test_report_detects_tampering(tmp_path):
    path, public = _make_log(tmp_path)
    rows = path.read_text(encoding="utf-8").splitlines()
    rec = json.loads(rows[2])
    rec["event"]["decision"] = "allow"  # el atacante intenta blanquear una cuarentena
    rows[2] = json.dumps(rec, ensure_ascii=False)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    report = cr.build_report(path, public)
    assert report["integrity"]["ok"] is False
    assert report["integrity"]["first_bad_line"] == 3


def test_renderers_produce_output(tmp_path):
    path, public = _make_log(tmp_path)
    report = cr.build_report(path, public, org="Lab X")
    text = cr.render_text(report)
    assert "INFORME DE CUMPLIMIENTO" in text and "INTEGRO" in text
    html = cr.render_html(report)
    assert "<html" in html and "Lab X" in html
    data = json.loads(cr.render_json(report))
    assert data["summary"]["total_events"] == 4


def test_per_app_aggregation(tmp_path):
    path, public = _make_log(tmp_path)
    report = cr.build_report(path, public)
    by_app = report["summary"]["by_app"]
    assert by_app["cursor_app"]["allow"] == 1
    assert by_app["cursor_app"]["deny"] == 1
    assert "read:intent" in by_app["cursor_app"]["scopes"]
