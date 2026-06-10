"""El decodificador: traduce electricidad en significado.

Recibe bloques de señal de `signal_source` y los clasifica en intenciones
usando un modelo simple de machine learning (scikit-learn) entrenado sobre
la señal sintética: "esta persona quiere mover el cursor", "quiere escribir",
o "no quiere nada ahora".
"""

from __future__ import annotations

from enum import Enum

import numpy as np


class Intent(Enum):
    """Las intenciones que el decoder sabe reconocer en la señal."""

    MOVE_CURSOR = "move_cursor"
    TYPE_TEXT = "type_text"
    IDLE = "idle"


class Decoder:
    """Clasificador de bloques de señal en intenciones."""

    def __init__(self) -> None:
        # TODO (Paso 3): crear el modelo de scikit-learn (algo simple y
        # legible, p. ej. regresión logística sobre features de frecuencia).
        raise NotImplementedError("Se implementa en el Paso 3")

    def train(self) -> None:
        """Entrena el modelo con señal sintética etiquetada.

        Genera ejemplos de cada intención con `SignalSource` (cada intención
        tendrá una firma de frecuencia distinta) y ajusta el clasificador.
        """
        # TODO (Paso 3): generar dataset sintético etiquetado y entrenar.
        raise NotImplementedError("Se implementa en el Paso 3")

    def decode(self, chunk: np.ndarray) -> Intent:
        """Clasifica un bloque de señal en una intención.

        Args:
            chunk: bloque 1-D de señal, como lo entrega `SignalSource.get_chunk()`.

        Returns:
            La intención detectada en ese bloque.
        """
        # TODO (Paso 3): extraer features (potencia por banda de frecuencia)
        # y predecir con el modelo entrenado.
        raise NotImplementedError("Se implementa en el Paso 3")


# TODO (Paso 3): demo ejecutable `python -m neurogate.decoder` que toma señal
# en vivo y va imprimiendo las intenciones detectadas en la terminal.
