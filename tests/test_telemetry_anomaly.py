"""Tests del detector sobre telemetría real (Fase D): baseline, flood, scope novel.

El detector afinado distingue un **flood sostenido** (muchas peticiones en la
ventana) de una **ráfaga corta legítima** (2-3 peticiones muy seguidas): solo el
primero entra en anomalía. Ese contraste es el corazón de estos tests.
"""

from __future__ import annotations

from neurogate.telemetry_anomaly import TelemetryAnomalyDetector, TelemetryRecord


def _trained(rate_spike_factor: float = 10.0):
    """Detector con un baseline normal aprendido (~1 req/s, read:intent)."""
    det = TelemetryAnomalyDetector(baseline_requests=40,
                                   rate_spike_factor=rate_spike_factor,
                                   min_flood_burst=5)
    det.warm_up("cursor_app", {"read:intent"})
    t = 1_000_000.0
    for _ in range(40):
        t += 1.0
        det.observe(TelemetryRecord("cursor_app", "read:intent", t, payload_size=16),
                    learning=True)
    det.finalize_baseline()
    det.clear_timing()  # no arrastrar el reloj simulado del baseline
    return det, t


def test_normal_request_is_not_anomalous():
    det, t = _trained()
    t += 1.0
    r = det.observe(TelemetryRecord("cursor_app", "read:intent", t, payload_size=16))
    assert not r.is_anomalous


def test_short_legit_burst_is_not_flagged():
    """Refinamiento: 3 peticiones legítimas muy seguidas NO son un flood."""
    det, t = _trained()
    flagged = 0
    for _ in range(3):
        t += 0.01  # muy seguidas, pero solo 3: ráfaga corta, no sostenida
        flagged += det.observe(
            TelemetryRecord("cursor_app", "read:intent", t, payload_size=16)).is_anomalous
    assert flagged == 0


def test_sustained_flood_triggers_anomaly():
    """Un flood sostenido (muchas peticiones en la ventana) sí entra en anomalía."""
    det, t = _trained()
    flagged = 0
    for _ in range(40):
        t += 0.02  # ~50 req/s sostenido durante ~0.8 s
        r = det.observe(TelemetryRecord("cursor_app", "read:intent", t, payload_size=16))
        flagged += r.is_anomalous
    assert flagged >= 15  # la mayor parte del flood, marcada


def test_never_used_scope_is_anomalous():
    """Pedir un scope que la app nunca usó es anomalía inmediata."""
    det, t = _trained()
    t += 5.0
    r = det.observe(TelemetryRecord("cursor_app", "read:raw_signal", t, payload_size=4096))
    assert r.is_anomalous and "scope" in r.reason


def test_baseline_phase_does_not_flag():
    """Durante el baseline (antes de finalize) nada se marca como anómalo."""
    det = TelemetryAnomalyDetector(baseline_requests=5)
    det.warm_up("app", {"read:intent"})
    t = 0.0
    flagged = 0
    for _ in range(5):
        t += 0.001  # ráfaga, pero estamos en baseline
        flagged += det.observe(TelemetryRecord("app", "read:intent", t)).is_anomalous
    assert flagged == 0


def test_finalize_without_baseline_raises():
    det = TelemetryAnomalyDetector()
    try:
        det.finalize_baseline()
        assert False, "debería lanzar sin baseline"
    except RuntimeError:
        pass
