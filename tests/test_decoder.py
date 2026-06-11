"""Tests del decoder (Paso 3)."""

from __future__ import annotations

import numpy as np
import pytest

from neurogate.decoder import Decoder, Intent
from neurogate.signal_source import INTENTS, SignalSource


@pytest.fixture(scope="module")
def trained_decoder():
    dec = Decoder()
    dec.train()
    return dec


def test_decode_returns_intent(trained_decoder):
    src = SignalSource(seed=7)
    assert isinstance(trained_decoder.decode(src.get_chunk()), Intent)


def test_accuracy_on_held_out_signal(trained_decoder):
    # Con firmas espectrales tan separadas, esperamos accuracy alta (>90%).
    src = SignalSource(seed=999)
    correct = sum(trained_decoder.decode(src.sample(i)).value == i
                  for i in INTENTS for _ in range(30))
    assert correct / (len(INTENTS) * 30) > 0.9


def test_decode_before_train_raises():
    with pytest.raises(RuntimeError):
        Decoder().decode(np.zeros(250))
