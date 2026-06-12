"""Tests de las fuentes v2 (Fase A): BrainFlowSource, DatasetSource, make_source."""

from __future__ import annotations

import numpy as np
import pytest

# Si faltan las libs, se omiten estos tests sin romper la suite.
pytest.importorskip("brainflow")
pytest.importorskip("mne")

from neurogate.signal_source import (BrainFlowSource, DatasetSource,
                                     SignalSource, make_source)


def test_brainflow_chunk_is_1d_nonempty():
    """BrainFlowSource.get_chunk() es ndarray 1-D no vacío (contrato v1)."""
    with BrainFlowSource(chunk_size=64) as src:
        chunk = src.get_chunk()
    assert isinstance(chunk, np.ndarray)
    assert chunk.ndim == 1
    assert chunk.size > 0


def test_brainflow_exposes_metadata():
    """Expone sampling_rate>0 y al menos un canal EEG con nombre."""
    with BrainFlowSource(chunk_size=64) as src:
        assert src.sampling_rate > 0
        assert len(src.eeg_channels) > 0
        assert len(src.channel_names) > 0


def test_brainflow_chunk_2d_is_2d():
    """get_chunk_2d() es 2-D con (canales, muestras)."""
    with BrainFlowSource(chunk_size=64) as src:
        chunk2d = src.get_chunk_2d()
    assert chunk2d.ndim == 2
    assert chunk2d.shape[0] == len(src.eeg_channels)


def test_dataset_chunk_is_1d_from_local_edf():
    """DatasetSource.get_chunk() es ndarray 1-D leyendo el EDF local."""
    with DatasetSource(chunk_size=160) as src:
        chunk = src.get_chunk()
        assert isinstance(chunk, np.ndarray)
        assert chunk.ndim == 1
        assert chunk.size == 160
        assert src.sampling_rate > 0
        assert len(src.channel_names) > 0
        assert src.get_chunk_2d().ndim == 2


def test_make_source_respects_env(monkeypatch):
    """make_source respeta la env var NEUROGATE_SIGNAL_SOURCE."""
    monkeypatch.setenv("NEUROGATE_SIGNAL_SOURCE", "dataset")
    src = make_source(chunk_size=160)
    try:
        assert isinstance(src, DatasetSource)
    finally:
        src.close()

    monkeypatch.setenv("NEUROGATE_SIGNAL_SOURCE", "simulated")
    assert isinstance(make_source(), SignalSource)

    # Argumento explícito tiene prioridad sobre la env var.
    monkeypatch.setenv("NEUROGATE_SIGNAL_SOURCE", "dataset")
    assert isinstance(make_source("simulated"), SignalSource)


def test_make_source_unknown_raises():
    with pytest.raises(ValueError):
        make_source("telepathy")
