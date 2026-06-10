"""Registro auditable: log JSONL donde cada entrada lleva el hash de la anterior.

Alterar o borrar una línea rompe la cadena y verify_chain() lo detecta.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class AuditEvent:
    """Un evento auditable: el rastro de una solicitud."""

    app_id: str
    data_type: str
    allowed: bool
    reason: str
    timestamp: float = field(default_factory=time.time)


class AuditLog:
    """Log append-only encadenado con SHA-256."""

    def __init__(self, path: Path) -> None:
        # TODO (Paso 7): abrir/crear el archivo y recuperar el último hash.
        raise NotImplementedError("Se implementa en el Paso 7")

    def append(self, event: AuditEvent) -> None:
        """Añade un evento encadenado al hash anterior."""
        # TODO (Paso 7)
        raise NotImplementedError("Se implementa en el Paso 7")

    def verify_chain(self) -> bool:
        """True si la cadena está íntegra; False si alguien alteró el log."""
        # TODO (Paso 7)
        raise NotImplementedError("Se implementa en el Paso 7")


# TODO (Paso 7): demo `python -m neurogate.audit`: alterar una línea rompe la verificación.
