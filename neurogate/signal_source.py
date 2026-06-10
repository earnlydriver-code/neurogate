"""Cerebro simulado: genera señal sintética tipo EEG en bloques."""

from __future__ import annotations

import numpy as np


class SignalSource:
    """Fuente de señal EEG simulada, entregada en bloques como un stream."""

    def __init__(self, sampling_rate: int = 250, chunk_size: int = 250) -> None:
        # TODO (Paso 2): guardar parámetros y estado para señal continua entre bloques.
        raise NotImplementedError("Se implementa en el Paso 2")

    def get_chunk(self) -> np.ndarray:
        """Devuelve el siguiente bloque de señal (array 1-D de chunk_size muestras)."""
        # TODO (Paso 2): mezclar bandas alfa/beta + ruido gaussiano.
        raise NotImplementedError("Se implementa en el Paso 2")


# TODO (Paso 2): demo `python -m neurogate.signal_source` con gráfica matplotlib.
