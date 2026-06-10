"""Decoder: clasifica bloques de señal en intenciones (ML con scikit-learn)."""

from __future__ import annotations

from enum import Enum

import numpy as np


class Intent(Enum):
    """Intenciones que el decoder sabe reconocer."""

    MOVE_CURSOR = "move_cursor"
    TYPE_TEXT = "type_text"
    IDLE = "idle"


class Decoder:
    """Clasificador señal -> intención."""

    def __init__(self) -> None:
        # TODO (Paso 3): crear el modelo (algo simple, p. ej. regresión logística).
        raise NotImplementedError("Se implementa en el Paso 3")

    def train(self) -> None:
        """Entrena con señal sintética etiquetada por intención."""
        # TODO (Paso 3)
        raise NotImplementedError("Se implementa en el Paso 3")

    def decode(self, chunk: np.ndarray) -> Intent:
        """Clasifica un bloque de señal en una intención."""
        # TODO (Paso 3): features de frecuencia -> predicción.
        raise NotImplementedError("Se implementa en el Paso 3")


# TODO (Paso 3): demo `python -m neurogate.decoder` imprimiendo intenciones.
