"""Cerebro simulado: genera señal sintética tipo EEG en bloques.

Cada "intención" tiene una firma espectral distinta (qué bandas de frecuencia
dominan), para que el decoder pueda distinguirlas a partir de la señal.
"""

from __future__ import annotations

import numpy as np

# Intenciones que el cerebro simulado puede "pensar" (strings, no el Enum del
# decoder, para evitar import circular). Coinciden con Intent.value del decoder.
INTENTS = ("idle", "move_cursor", "type_text")

# Frecuencia representativa de cada banda EEG (Hz).
_BAND_HZ = {"theta": 6.0, "alpha": 10.0, "beta": 20.0}

# Firma espectral por intención: amplitud (microvoltios) de cada banda.
# - idle: alfa dominante (cerebro relajado).
# - move_cursor: beta dominante (actividad motora).
# - type_text: theta + beta (concentración + actividad).
_SIGNATURES = {
    "idle": {"theta": 5.0, "alpha": 25.0, "beta": 5.0},
    "move_cursor": {"theta": 5.0, "alpha": 8.0, "beta": 22.0},
    "type_text": {"theta": 18.0, "alpha": 8.0, "beta": 16.0},
}

_NOISE_UV = 5.0  # desviación del ruido gaussiano de fondo


def _synthesize(intent_label: str, n: int, sampling_rate: int,
                sample_offset: float, rng: np.random.Generator) -> np.ndarray:
    """Sintetiza n muestras para una intención, con offset de fase para continuidad."""
    if intent_label not in _SIGNATURES:
        raise ValueError(f"Intención desconocida: {intent_label}")
    t = (sample_offset + np.arange(n)) / sampling_rate
    signal = np.zeros(n)
    for band, freq in _BAND_HZ.items():
        signal += _SIGNATURES[intent_label][band] * np.sin(2 * np.pi * freq * t)
    signal += rng.normal(0.0, _NOISE_UV, n)
    return signal


class SignalSource:
    """Fuente de señal EEG simulada, entregada en bloques como un stream."""

    def __init__(self, sampling_rate: int = 250, chunk_size: int = 250,
                 seed: int | None = None) -> None:
        self.sampling_rate = sampling_rate
        self.chunk_size = chunk_size
        self._rng = np.random.default_rng(seed)
        self._sample_index = 0  # avanza para mantener fase continua entre bloques
        self._intent = "idle"   # "estado mental" actual del cerebro simulado

    def set_intent(self, intent_label: str) -> None:
        """Cambia la intención que el cerebro está 'pensando' (el decoder no la ve)."""
        if intent_label not in _SIGNATURES:
            raise ValueError(f"Intención desconocida: {intent_label}")
        self._intent = intent_label

    def get_chunk(self) -> np.ndarray:
        """Devuelve el siguiente bloque del stream (array 1-D de chunk_size muestras)."""
        chunk = _synthesize(self._intent, self.chunk_size, self.sampling_rate,
                            self._sample_index, self._rng)
        self._sample_index += self.chunk_size
        return chunk

    def sample(self, intent_label: str, n_samples: int | None = None) -> np.ndarray:
        """Bloque etiquetado independiente para entrenar el decoder (no toca el stream)."""
        n = n_samples or self.chunk_size
        offset = self._rng.uniform(0, 10_000)  # fase aleatoria -> variedad
        return _synthesize(intent_label, n, self.sampling_rate, offset, self._rng)


def _demo() -> None:
    """Grafica ~2 s de señal por cada intención y guarda PNG + resumen en demos/."""
    from pathlib import Path

    import matplotlib
    matplotlib.use("Agg")  # backend sin ventana, para guardar a archivo
    import matplotlib.pyplot as plt

    demos = Path(__file__).resolve().parent.parent / "demos"
    demos.mkdir(exist_ok=True)

    src = SignalSource(seed=42)
    fig, axes = plt.subplots(len(INTENTS), 1, figsize=(10, 7), sharex=True)
    lines = []
    for ax, intent in zip(axes, INTENTS):
        chunk = src.sample(intent, n_samples=500)  # 2 s a 250 Hz
        t = np.arange(chunk.size) / src.sampling_rate
        ax.plot(t, chunk, linewidth=0.8)
        ax.set_title(f"Intención: {intent}", loc="left", fontsize=10)
        ax.set_ylabel("µV")
        lines.append(f"{intent:12s} -> media={chunk.mean():6.2f}  "
                     f"std={chunk.std():6.2f}  pico={np.abs(chunk).max():6.2f}")
    axes[-1].set_xlabel("tiempo (s)")
    fig.suptitle("NeuroGate · Señal EEG simulada por intención (Paso 2)")
    fig.tight_layout()
    png = demos / "step2_signal.png"
    fig.savefig(png, dpi=110)

    report = "Paso 2 — signal_source\n" + "=" * 40 + "\n" + "\n".join(lines) + "\n"
    (demos / "step2_signal.txt").write_text(report, encoding="utf-8")
    print(report)
    print(f"Gráfica guardada en {png}")


if __name__ == "__main__":
    _demo()
