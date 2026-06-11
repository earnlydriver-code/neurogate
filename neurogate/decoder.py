"""Decoder: clasifica bloques de señal en intenciones (ML con scikit-learn).

Extrae la potencia por banda de frecuencia (theta/alpha/beta) de cada bloque y
clasifica con una regresión logística entrenada sobre la señal sintética.
"""

from __future__ import annotations

from enum import Enum

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from neurogate.signal_source import INTENTS, SignalSource

# Rango de cada banda EEG (Hz) usado como feature.
_BANDS = {"theta": (4, 8), "alpha": (8, 13), "beta": (13, 30)}


class Intent(Enum):
    """Intenciones que el decoder sabe reconocer."""

    MOVE_CURSOR = "move_cursor"
    TYPE_TEXT = "type_text"
    IDLE = "idle"


def _features(chunk: np.ndarray, sampling_rate: int) -> list[float]:
    """Potencia (en log) de cada banda de frecuencia del bloque."""
    freqs = np.fft.rfftfreq(chunk.size, 1.0 / sampling_rate)
    psd = np.abs(np.fft.rfft(chunk)) ** 2
    powers = [psd[(freqs >= lo) & (freqs < hi)].sum() for lo, hi in _BANDS.values()]
    return list(np.log1p(powers))


class Decoder:
    """Clasificador señal -> intención."""

    def __init__(self, sampling_rate: int = 250) -> None:
        self.sampling_rate = sampling_rate
        self._model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
        self._trained = False

    def train(self, n_per_class: int = 200, seed: int = 0) -> None:
        """Entrena con señal sintética etiquetada (n_per_class bloques por intención)."""
        src = SignalSource(sampling_rate=self.sampling_rate, seed=seed)
        X, y = [], []
        for intent in INTENTS:
            for _ in range(n_per_class):
                X.append(_features(src.sample(intent), self.sampling_rate))
                y.append(intent)
        self._model.fit(X, y)
        self._trained = True

    def decode(self, chunk: np.ndarray) -> Intent:
        """Clasifica un bloque de señal en una intención."""
        if not self._trained:
            raise RuntimeError("El decoder no está entrenado: llama a train() primero")
        label = self._model.predict([_features(chunk, self.sampling_rate)])[0]
        return Intent(label)


def _demo() -> None:
    """Entrena, decodifica un stream con intenciones cambiantes y mide accuracy."""
    from pathlib import Path

    demos = Path(__file__).resolve().parent.parent / "demos"
    demos.mkdir(exist_ok=True)

    decoder = Decoder()
    decoder.train()

    src = SignalSource(seed=123)
    plan = ["idle", "move_cursor", "type_text", "idle", "type_text", "move_cursor"]
    lines, correct = [], 0
    for true_intent in plan:
        src.set_intent(true_intent)
        predicted = decoder.decode(src.get_chunk()).value
        ok = predicted == true_intent
        correct += ok
        lines.append(f"cerebro pensó {true_intent:12s} -> decoder dijo "
                     f"{predicted:12s}  {'OK' if ok else 'FALLO'}")

    acc = correct / len(plan)
    report = ("Paso 3 — decoder\n" + "=" * 40 + "\n" + "\n".join(lines)
              + f"\n\nAccuracy en esta corrida: {acc:.0%} ({correct}/{len(plan)})\n")
    (demos / "step3_decoder.txt").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    _demo()
