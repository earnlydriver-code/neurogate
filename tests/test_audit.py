"""Tests del registro auditable encadenado (Paso 7)."""

from __future__ import annotations

import json

from neurogate.audit import AuditEvent, AuditLog


def _write_three(path):
    log = AuditLog(path)
    log.append(AuditEvent("a", "intent", True, "ok", 1.0))
    log.append(AuditEvent("b", "raw_signal", False, "sin permiso", 2.0))
    log.append(AuditEvent("c", "confirmed_text", True, "ok", 3.0))
    return log


def test_valid_chain_verifies(tmp_path):
    log = _write_three(tmp_path / "audit.jsonl")
    assert log.verify_chain()


def test_tampering_breaks_chain(tmp_path):
    p = tmp_path / "audit.jsonl"
    _write_three(p)
    rows = p.read_text(encoding="utf-8").splitlines()
    rec = json.loads(rows[1])
    rec["event"]["allowed"] = True  # alteramos un evento
    rows[1] = json.dumps(rec)
    p.write_text("\n".join(rows) + "\n", encoding="utf-8")
    assert not AuditLog(p).verify_chain()


def test_deleting_a_line_breaks_chain(tmp_path):
    p = tmp_path / "audit.jsonl"
    _write_three(p)
    rows = p.read_text(encoding="utf-8").splitlines()
    del rows[1]  # borramos una entrada
    p.write_text("\n".join(rows) + "\n", encoding="utf-8")
    assert not AuditLog(p).verify_chain()


def test_chain_continues_across_reopen(tmp_path):
    p = tmp_path / "audit.jsonl"
    _write_three(p)
    AuditLog(p).append(AuditEvent("d", "intent", True, "ok", 4.0))  # reabrir y seguir
    assert AuditLog(p).verify_chain()
