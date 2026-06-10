"""El cerebro simulado: genera señal sintética tipo EEG en bloques.

Este módulo imita lo que un sensor leería de un cerebro real. Produce una
onda eléctrica continua con bandas de frecuencia realistas (alfa ~10 Hz,
beta ~20 Hz...) mezcladas con ruido, entregada en bloques (chunks) para que
el resto del sistema la consuma como si fuera un stream en vivo.

Diseño clave: la interfaz `SignalSource` es agnóstica al origen. En el futuro
podrá cargar datos reales de un dataset público de EEG sin que el decoder ni
el gateway cambien una sola línea.
"""

from __future__ import annotations

import numpy as np


class SignalSource:
    """Fuente de señal cerebral simulada.

    Genera bloques de señal tipo EEG bajo demanda. Cada llamada a
    `get_chunk()` devuelve el siguiente bloque del stream, como si
    leyéramos de un sensor en tiempo real.
    """

    def __init__(self, sampling_rate: int = 250, chunk_size: int = 250) -> None:
        """Configura la fuente.

        Args:
            sampling_rate: muestras por segundo (250 Hz es típico en EEG).
            chunk_size: muestras por bloque (250 = un segundo de señal).
        """
        # TODO (Paso 2): guardar parámetros e inicializar el estado interno
        # (fase de las ondas, generador de ruido) para que la señal sea
        # continua entre bloques consecutivos.
        raise NotImplementedError("Se implementa en el Paso 2")

    def get_chunk(self) -> np.ndarray:
        """Devuelve el siguiente bloque de señal.

        Returns:
            Array 1-D de `chunk_size` muestras (float), en microvoltios
            simulados.
        """
        # TODO (Paso 2): sintetizar el bloque mezclando bandas alfa/beta con
        # ruido gaussiano; mantener continuidad de fase entre llamadas.
        raise NotImplementedError("Se implementa en el Paso 2")


# TODO (Paso 2): demo ejecutable `python -m neurogate.signal_source` que
# grafica unos segundos de señal con matplotlib (criterio de "hecho" del paso).
