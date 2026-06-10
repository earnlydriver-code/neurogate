"""La memoria inalterable: registro auditable encadenado con hashes.

Cada evento del sistema (qué app, qué pidió, a qué hora, si se permitió o
bloqueó, y por qué) se escribe en un log JSONL append-only. Cada entrada
incluye el hash SHA-256 de la entrada anterior: alterar o borrar una línea
rompe la cadena, y la verificación lo detecta. Como una mini-blockchain de
un solo escritor.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class AuditEvent:
    """Un evento auditable: el rastro de una solicitud por el gateway."""

    app_id: str
    data_type: str        # DataType.value de la solicitud
    allowed: bool         # ¿se entregó el dato o se bloqueó?
    reason: str           # el porqué (viene de consent/anomaly)
    timestamp: float = field(default_factory=time.time)


class AuditLog:
    """Log JSONL append-only con encadenado de hashes SHA-256."""

    def __init__(self, path: Path) -> None:
        """Args:
            path: archivo .jsonl donde se persiste el log.
        """
        # TODO (Paso 7): abrir/crear el archivo y recuperar el hash de la
        # última entrada para continuar la cadena entre ejecuciones.
        raise NotImplementedError("Se implementa en el Paso 7")

    def append(self, event: AuditEvent) -> None:
        """Añade un evento al log, encadenado al hash de la entrada anterior."""
        # TODO (Paso 7): serializar el evento + prev_hash, calcular su
        # SHA-256 y escribir la línea JSONL.
        raise NotImplementedError("Se implementa en el Paso 7")

    def verify_chain(self) -> bool:
        """Recorre el log completo y verifica que la cadena de hashes es íntegra.

        Returns:
            True si nadie alteró nada; False si alguna línea fue modificada
            o eliminada.
        """
        # TODO (Paso 7): releer el archivo, recalcular hashes y comparar.
        raise NotImplementedError("Se implementa en el Paso 7")


# TODO (Paso 7): demo ejecutable `python -m neurogate.audit`: escribe eventos,
# verifica OK; altera una línea a mano y la verificación falla (criterio del paso).
