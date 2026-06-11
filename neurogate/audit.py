"""Registro auditable: log JSONL donde cada entrada lleva el hash de la anterior.

Cada entrada encadena el hash SHA-256 de la previa. Alterar o borrar una línea
rompe la cadena y verify_chain() lo detecta. Como una mini-blockchain de un solo
escritor.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Hash inicial de la cadena (no hay entrada previa a la primera).
_GENESIS = "0" * 64


@dataclass(frozen=True)
class AuditEvent:
    """Un evento auditable: el rastro de una solicitud."""

    app_id: str
    data_type: str
    allowed: bool
    reason: str
    timestamp: float = field(default_factory=time.time)


def _entry_hash(prev_hash: str, event_dict: dict) -> str:
    """SHA-256 del hash previo + el contenido del evento (orden estable)."""
    payload = prev_hash + json.dumps(event_dict, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuditLog:
    """Log append-only encadenado con SHA-256."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._last_hash = self._recover_last_hash()

    def _recover_last_hash(self) -> str:
        """Recupera el hash de la última entrada para continuar la cadena."""
        if not self.path.exists():
            return _GENESIS
        last = _GENESIS
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                last = json.loads(line)["hash"]
        return last

    def append(self, event: AuditEvent) -> None:
        """Añade un evento encadenado al hash anterior."""
        event_dict = asdict(event)
        h = _entry_hash(self._last_hash, event_dict)
        record = {"event": event_dict, "prev_hash": self._last_hash, "hash": h}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._last_hash = h

    def verify_chain(self) -> bool:
        """True si la cadena está íntegra; False si alguien alteró el log."""
        if not self.path.exists():
            return True
        prev = _GENESIS
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec["prev_hash"] != prev:
                return False
            if _entry_hash(prev, rec["event"]) != rec["hash"]:
                return False
            prev = rec["hash"]
        return True


def _demo() -> None:
    """Escribe eventos, verifica OK, altera una línea y la verificación falla."""
    demos = Path(__file__).resolve().parent.parent / "demos"
    demos.mkdir(exist_ok=True)
    log_path = demos / "step7_audit_sample.jsonl"
    log_path.unlink(missing_ok=True)

    log = AuditLog(log_path)
    log.append(AuditEvent("cursor_app", "intent", True, "autorizado", 1_000_000.0))
    log.append(AuditEvent("evil_app", "raw_signal", False, "sin permiso", 1_000_001.0))
    log.append(AuditEvent("messaging_app", "confirmed_text", True, "autorizado", 1_000_002.0))

    lines = [f"3 eventos escritos en {log_path.name}",
             f"verificacion tras escribir: {'INTEGRO' if log.verify_chain() else 'ALTERADO'}"]

    # Alteramos a mano la segunda línea (cambiamos 'False' a 'True' en el permiso).
    rows = log_path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(rows[1])
    tampered["event"]["allowed"] = True  # el atacante intenta borrar su bloqueo
    rows[1] = json.dumps(tampered, ensure_ascii=False)
    log_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    fresh = AuditLog(log_path)
    lines.append(f"tras alterar 1 linea a mano: "
                 f"{'INTEGRO (FALLO)' if fresh.verify_chain() else 'ALTERADO (detectado)'}")

    report = "Paso 7 — audit\n" + "=" * 55 + "\n" + "\n".join(lines) + "\n"
    (demos / "step7_audit.txt").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    _demo()
