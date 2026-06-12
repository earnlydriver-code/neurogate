"""CLI de verificación del log auditado firmado (Fase D).

Recibe un log JSONL firmado y la clave pública Ed25519, y dictamina si está
ÍNTEGRO o ALTERADO, señalando la primera entrada corrupta. Un tercero puede
verificar el log sin acceso al sistema, solo con la clave pública.

Uso:
    python verify_audit.py <log.jsonl> <public_key.pem>
    python verify_audit.py audit_service.jsonl keys/audit_ed25519_public.pem

Código de salida: 0 si íntegro, 1 si alterado o error.
"""

from __future__ import annotations

import sys
from pathlib import Path

from neurogate.signed_audit import load_public_key, verify_log


def main(argv: list[str]) -> int:
    """Verifica el log con la clave pública. Devuelve el código de salida."""
    if len(argv) != 3:
        print("uso: python verify_audit.py <log.jsonl> <public_key.pem>")
        return 2

    log_path = Path(argv[1])
    key_path = Path(argv[2])
    if not log_path.exists():
        print(f"ERROR: no existe el log: {log_path}")
        return 1
    if not key_path.exists():
        print(f"ERROR: no existe la clave pública: {key_path}")
        return 1

    public_key = load_public_key(key_path.read_bytes())
    ok, bad_line, reason = verify_log(log_path, public_key)

    n_lines = sum(1 for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip())
    print(f"Log: {log_path}  ({n_lines} entradas)")
    print(f"Clave pública: {key_path}")
    if ok:
        print(f"RESULTADO: ÍNTEGRO — la cadena y todas las firmas son válidas ({reason}).")
        return 0
    print(f"RESULTADO: ALTERADO — primera entrada corrupta en la línea {bad_line}: {reason}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
