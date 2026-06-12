"""Decoder real de motor imagery (v2, Fase B).

Decodificador entrenado offline sobre BCI Competition IV 2a con un pipeline
MNE + CSP + clasificador lineal. Vive AL LADO del ``Decoder``/``Intent`` de la
v1 (que el gateway v1 sigue usando); no lo sustituye.

- Entrada de ``decode()``: una época multicanal ``np.ndarray`` de forma
  (canales, muestras), coherente con ``get_chunk_2d()`` de la Fase A.
- Salida: ``MIDecision`` con ``.intent`` (clase motora) y ``.confidence``.
  Por debajo de un umbral configurable devuelve ``idle``.

El modelo entrenado lo genera ``train_decoder.py`` y se serializa con joblib.
En runtime esta clase lo carga; no entrena nada.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np

# Banda de paso para motor imagery (ritmos mu/beta).
BAND_HZ = (8.0, 30.0)

# Frecuencia de muestreo del dataset BCI IV 2a.
DEFAULT_SFREQ = 250

# Ruta por defecto del modelo serializado (lo genera train_decoder.py).
DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parent.parent / "models" / "mi_decoder.joblib"
)

# Umbral de confianza por defecto: por debajo, la intención se reporta como idle.
DEFAULT_CONFIDENCE_THRESHOLD = 0.5


class MotorImageryIntent(Enum):
    """Intenciones motoras de BCI Competition IV 2a, más idle."""

    LEFT_HAND = "left_hand"
    RIGHT_HAND = "right_hand"
    FEET = "feet"
    TONGUE = "tongue"
    IDLE = "idle"


# Mapeo de la etiqueta numérica del dataset (1..4) a la intención motora.
LABEL_TO_INTENT = {
    1: MotorImageryIntent.LEFT_HAND,
    2: MotorImageryIntent.RIGHT_HAND,
    3: MotorImageryIntent.FEET,
    4: MotorImageryIntent.TONGUE,
}


@dataclass(frozen=True)
class MIDecision:
    """Resultado de decodificar una época: intención + confianza."""

    intent: MotorImageryIntent
    confidence: float


def bandpass_filter(epoch: np.ndarray, sfreq: int = DEFAULT_SFREQ,
                    band: tuple[float, float] = BAND_HZ) -> np.ndarray:
    """Filtra una época (canales, muestras) a la banda mu/beta con MNE."""
    import mne

    mne.set_log_level("WARNING")  # silencia el ruido de logging de MNE
    data = np.asarray(epoch, dtype=np.float64)
    return mne.filter.filter_data(data, sfreq, band[0], band[1], verbose=False)


class MotorImageryDecoder:
    """Decodificador real de motor imagery: carga el modelo y clasifica épocas."""

    def __init__(self, model_path: str | Path | None = None,
                 sfreq: int = DEFAULT_SFREQ,
                 confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD) -> None:
        import joblib

        self.model_path = Path(model_path) if model_path else DEFAULT_MODEL_PATH
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Modelo no encontrado: {self.model_path}. "
                "Genéralo con: python train_decoder.py")
        bundle = joblib.load(self.model_path)
        # bundle: dict con el pipeline sklearn (CSP+clasificador) y metadatos.
        self._pipeline = bundle["pipeline"]
        self.sfreq = bundle.get("sfreq", sfreq)
        self.band = tuple(bundle.get("band", BAND_HZ))
        self.classes_ = list(self._pipeline.classes_)
        self.confidence_threshold = confidence_threshold

    def decode(self, epoch: np.ndarray) -> MIDecision:
        """Clasifica una época (canales, muestras) en una intención + confianza."""
        epoch = np.asarray(epoch, dtype=np.float64)
        if epoch.ndim != 2:
            raise ValueError(
                f"La época debe ser 2-D (canales, muestras); recibido {epoch.shape}")
        filtered = bandpass_filter(epoch, self.sfreq, self.band)
        # El pipeline CSP de MNE espera lotes de forma (n_epocas, canales, muestras).
        batch = filtered[np.newaxis, :, :]
        proba = self._pipeline.predict_proba(batch)[0]
        best = int(np.argmax(proba))
        confidence = float(proba[best])
        label = self.classes_[best]
        if confidence < self.confidence_threshold:
            return MIDecision(MotorImageryIntent.IDLE, confidence)
        return MIDecision(LABEL_TO_INTENT[int(label)], confidence)


def _demo() -> None:
    """Reproduce la sesión E de un sujeto y decodifica épocas reales vs etiqueta."""
    # Import perezoso: la lógica de carga del dataset vive en train_decoder.py.
    import importlib.util
    import sys

    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "train_decoder", root / "train_decoder.py")
    train_decoder = importlib.util.module_from_spec(spec)
    sys.modules["train_decoder"] = train_decoder
    spec.loader.exec_module(train_decoder)

    train_decoder.run_demo(subject=1)


if __name__ == "__main__":
    _demo()
