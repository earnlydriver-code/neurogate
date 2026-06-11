"""Tests del detector de anomalías (Paso 5)."""

from __future__ import annotations

import numpy as np
import pytest

from neurogate.anomaly import AnomalyDetector
from neurogate.consent import AccessRequest, DataType


def _trained_detector():
    rng = np.random.default_rng(0)
    base, t, history = 1_000_000.0, 1_000_000.0, []
    for _ in range(300):
        t += max(0.3, rng.normal(1.0, 0.2))
        history.append(AccessRequest("app", DataType.INTENT, t))
    det = AnomalyDetector()
    det.fit(history)
    return det, t


def test_normal_access_is_not_flagged():
    det, t = _trained_detector()
    assert not det.score(AccessRequest("app", DataType.INTENT, t + 1.0)).is_anomalous


def test_burst_is_flagged():
    det, t = _trained_detector()
    flagged = 0
    for _ in range(10):
        t += 0.02
        flagged += det.score(AccessRequest("app", DataType.INTENT, t)).is_anomalous
    assert flagged >= 8  # casi toda la ráfaga debe marcarse


def test_never_seen_type_is_flagged():
    det, t = _trained_detector()
    res = det.score(AccessRequest("app", DataType.RAW_SIGNAL, t + 1.0))
    assert res.is_anomalous and "nunca pedido" in res.reason


def test_score_before_fit_raises():
    with pytest.raises(RuntimeError):
        AnomalyDetector().score(AccessRequest("app", DataType.INTENT, 0.0))
