"""Tests del log firmado (Fase D): cadena SHA-256 + firma Ed25519 + verify_log."""

from __future__ import annotations

import json

from neurogate.signed_audit import (SignedAuditEvent, SignedAuditLog,
                                     generate_keypair, load_public_key,
                                     private_key_to_pem, public_key_to_pem,
                                     verify_log)


def _log(tmp_path):
    private, public = generate_keypair()
    log = SignedAuditLog(tmp_path / "audit.jsonl", private)
    log.append(SignedAuditEvent("cursor_app", "read:intent", "allow", "autorizado", 1.0))
    log.append(SignedAuditEvent("evil_app", "read:raw_signal", "deny", "sin permiso", 2.0))
    log.append(SignedAuditEvent("flood_app", "read:intent", "quarantine", "anomalía", 3.0))
    return log, public


def test_valid_log_verifies(tmp_path):
    log, public = _log(tmp_path)
    ok, bad, _ = verify_log(log.path, public)
    assert ok and bad is None
    assert log.verify_chain()


def test_tampering_a_field_breaks_verification(tmp_path):
    """Alterar un carácter de cualquier línea hace fallar la verificación."""
    log, public = _log(tmp_path)
    rows = log.path.read_text(encoding="utf-8").splitlines()
    rec = json.loads(rows[1])
    rec["event"]["decision"] = "allow"  # el atacante borra su bloqueo
    rows[1] = json.dumps(rec, ensure_ascii=False)
    log.path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    ok, bad, _ = verify_log(log.path, public)
    assert not ok and bad == 2  # primera línea corrupta señalada


def test_tampering_signature_breaks_verification(tmp_path):
    """Cambiar la firma (sin tocar el contenido) también falla."""
    log, public = _log(tmp_path)
    rows = log.path.read_text(encoding="utf-8").splitlines()
    rec = json.loads(rows[0])
    # Invertir un carácter de la firma base64.
    sig = rec["signature"]
    rec["signature"] = ("A" if sig[0] != "A" else "B") + sig[1:]
    rows[0] = json.dumps(rec, ensure_ascii=False)
    log.path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    ok, bad, _ = verify_log(log.path, public)
    assert not ok and bad == 1


def test_wrong_public_key_fails(tmp_path):
    """Verificar con otra clave pública falla (autenticidad del emisor)."""
    log, _ = _log(tmp_path)
    _, other_public = generate_keypair()
    ok, bad, _ = verify_log(log.path, other_public)
    assert not ok and bad == 1


def test_chain_continues_across_reopen(tmp_path):
    """Reabrir el log continúa la cadena sin romperla."""
    private, public = generate_keypair()
    p = tmp_path / "audit.jsonl"
    SignedAuditLog(p, private).append(
        SignedAuditEvent("a", "read:intent", "allow", "ok", 1.0))
    SignedAuditLog(p, private).append(
        SignedAuditEvent("b", "read:intent", "allow", "ok", 2.0))
    ok, bad, _ = verify_log(p, public)
    assert ok and bad is None


def test_pem_roundtrip(tmp_path):
    """Las claves PEM se serializan y recargan correctamente."""
    private, public = generate_keypair()
    pub_pem = public_key_to_pem(public)
    reloaded = load_public_key(pub_pem)
    # Firmar con la privada y verificar con la pública recargada.
    sig = private.sign(b"mensaje")
    reloaded.verify(sig, b"mensaje")  # no lanza -> OK
    assert b"PRIVATE KEY" in private_key_to_pem(private)
