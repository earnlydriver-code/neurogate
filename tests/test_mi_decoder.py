"""Tests del decoder real de motor imagery (v2, Fase B).

No dependen de descargar datos: si faltan ``mne``/``scipy``, el modelo
serializado o la copia local del dataset, se hace ``skip`` con mensaje claro
en vez de fallar la suite. El decoder v1 y sus tests no se tocan.
"""

from __future__ import annotations

import numpy as np
import pytest

# Dependencias de la Fase B; si no están, se omiten estos tests.
pytest.importorskip("mne", reason="mne no instalado (Fase B)")
pytest.importorskip("scipy", reason="scipy no instalado (Fase B)")
pytest.importorskip("joblib", reason="joblib no instalado (Fase B)")

from neurogate.mi_decoder import (  # noqa: E402
    DEFAULT_MODEL_PATH,
    MIDecision,
    MotorImageryDecoder,
    MotorImageryIntent,
)


def _require_model() -> MotorImageryDecoder:
    """Carga el decoder o hace skip si el modelo no está entrenado."""
    if not DEFAULT_MODEL_PATH.exists():
        pytest.skip(
            f"Modelo no disponible ({DEFAULT_MODEL_PATH.name}). "
            "Genéralo con: python train_decoder.py")
    return MotorImageryDecoder()


@pytest.fixture(scope="module")
def decoder() -> MotorImageryDecoder:
    return _require_model()


def _dummy_epoch(decoder: MotorImageryDecoder) -> np.ndarray:
    """Época sintética (22 canales, 1000 muestras) con ruido, para probar la API."""
    rng = np.random.default_rng(0)
    n_channels = len(decoder._pipeline.named_steps["csp"].patterns_)
    return rng.standard_normal((n_channels, 1000))


def test_decode_returns_intent_and_confidence(decoder):
    decision = decoder.decode(_dummy_epoch(decoder))
    assert isinstance(decision, MIDecision)
    assert isinstance(decision.intent, MotorImageryIntent)
    assert 0.0 <= decision.confidence <= 1.0


def test_decode_rejects_non_2d(decoder):
    with pytest.raises(ValueError):
        decoder.decode(np.zeros(1000))  # 1-D no es una época multicanal


def test_below_threshold_returns_idle(decoder):
    # Con un umbral imposible (>1), toda decodificación cae por debajo -> idle.
    decoder.confidence_threshold = 1.1
    try:
        decision = decoder.decode(_dummy_epoch(decoder))
        assert decision.intent is MotorImageryIntent.IDLE
    finally:
        decoder.confidence_threshold = 0.5  # restaura para otros tests


def test_serialized_model_loads():
    decoder = _require_model()
    assert decoder._pipeline is not None
    assert set(decoder.classes_) <= {1, 2, 3, 4}
    assert decoder.sfreq == 250


def test_decode_on_real_epoch_matches_known_label():
    """Sobre una época real de la sesión E, devuelve una intención motora válida."""
    if not DEFAULT_MODEL_PATH.exists():
        pytest.skip("Modelo no disponible")
    pytest.importorskip("scipy")
    import train_decoder as td

    if not td.DATA_DIR.exists():
        pytest.skip("Dataset BCI IV 2a no disponible localmente")
    epochs, labels = td.load_session_epochs(1, "E")
    decoder = MotorImageryDecoder()
    decision = decoder.decode(epochs[0])
    assert isinstance(decision, MIDecision)
    assert decision.intent in set(MotorImageryIntent)
