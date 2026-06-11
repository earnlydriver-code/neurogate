"""Tests del cerebro simulado (Paso 2)."""

from __future__ import annotations

import numpy as np
import pytest

from neurogate.signal_source import INTENTS, SignalSource


def test_chunk_shape_and_type():
    src = SignalSource(chunk_size=250, seed=1)
    chunk = src.get_chunk()
    assert isinstance(chunk, np.ndarray)
    assert chunk.shape == (250,)


def test_stream_advances_phase():
    # Dos bloques seguidos no deben ser idénticos (avanza la fase + ruido).
    src = SignalSource(seed=1)
    assert not np.array_equal(src.get_chunk(), src.get_chunk())


def test_intents_have_distinct_spectra():
    # Cada intención domina una banda distinta -> potencias claramente diferentes.
    src = SignalSource(seed=1)
    powers = {i: np.var(src.sample(i, 1000)) for i in INTENTS}
    assert len(set(round(p) for p in powers.values())) == len(INTENTS)


def test_unknown_intent_raises():
    with pytest.raises(ValueError):
        SignalSource().set_intent("telekinesis")
