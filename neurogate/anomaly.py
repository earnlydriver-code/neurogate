"""Detector de anomalías: alerta ante patrones de acceso raros (Isolation Forest).

Aunque una app tenga permiso, su comportamiento puede delatarla: pedir datos a
un ritmo inusual o de un tipo que nunca antes pidió. Aprende el patrón normal y
puntúa cada solicitud nueva.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from sklearn.ensemble import IsolationForest

from neurogate.consent import AccessRequest, DataType

# Intervalo (s) que asumimos para la primera solicitud de una app sin historial.
_DEFAULT_INTERVAL = 5.0


@dataclass(frozen=True)
class AnomalyResult:
    """Veredicto del detector sobre una solicitud."""

    is_anomalous: bool
    score: float  # más negativo = más raro (convención de IsolationForest)
    reason: str


class AnomalyDetector:
    """Detector híbrido de accesos anómalos.

    - Lo continuo (ritmo e franja horaria) lo vigila un Isolation Forest.
    - Lo categórico (tipos de dato) por novedad: un tipo que esa app nunca pidió
      en entrenamiento es anómalo de inmediato (el iForest no puede aislar un
      feature que fue constante en entrenamiento).
    """

    def __init__(self, contamination: float = 0.02, seed: int = 0) -> None:
        self._model = IsolationForest(contamination=contamination, random_state=seed)
        self._last_ts: dict[str, float] = {}          # último acceso por app -> intervalo
        self._seen_types: dict[str, set[DataType]] = {}  # tipos vistos por app
        self._trained = False

    def _continuous_features(self, request: AccessRequest, update: bool = True) -> list[float]:
        """Features continuas para el iForest: intervalo desde el último acceso y hora."""
        last = self._last_ts.get(request.app_id)
        interval = (request.timestamp - last) if last is not None else _DEFAULT_INTERVAL
        hour = time.localtime(request.timestamp).tm_hour
        if update:
            self._last_ts[request.app_id] = request.timestamp
        return [interval, float(hour)]

    def fit(self, history: list[AccessRequest]) -> None:
        """Entrena con un historial de accesos normales (en orden cronológico)."""
        X = []
        for r in history:
            X.append(self._continuous_features(r))
            self._seen_types.setdefault(r.app_id, set()).add(r.data_type)
        self._model.fit(X)
        self._trained = True

    def score(self, request: AccessRequest) -> AnomalyResult:
        """¿La solicitud encaja en el patrón normal o es rara?"""
        if not self._trained:
            raise RuntimeError("El detector no está entrenado: llama a fit() primero")
        feats = self._continuous_features(request)
        # Regla de novedad: tipo que esta app nunca pidió en entrenamiento.
        if request.data_type not in self._seen_types.get(request.app_id, set()):
            return AnomalyResult(True, -1.0,
                                 f"tipo nunca pedido por esta app: {request.data_type.value}")
        is_anom = self._model.predict([feats])[0] == -1
        raw = float(self._model.decision_function([feats])[0])
        reason = (f"patrón anómalo (intervalo={feats[0]:.2f}s)" if is_anom
                  else "comportamiento normal")
        return AnomalyResult(is_anom, raw, reason)


def _demo() -> None:
    """Entrena con accesos normales y detecta una ráfaga y un tipo nunca pedido."""
    from pathlib import Path

    import numpy as np

    demos = Path(__file__).resolve().parent.parent / "demos"
    demos.mkdir(exist_ok=True)

    rng = np.random.default_rng(0)
    base = 1_000_000.0  # timestamp base ficticio y determinista
    # Normal: solicitudes cada ~1 s (con jitter), casi siempre INTENT.
    history, t = [], base
    for _ in range(300):
        t += max(0.3, rng.normal(1.0, 0.2))
        dtype = DataType.INTENT if rng.random() < 0.85 else DataType.CONFIRMED_TEXT
        history.append(AccessRequest("app", dtype, t))

    det = AnomalyDetector()
    det.fit(history)

    lines = []
    # Caso 1: acceso normal (~1 s después del último).
    t += 1.0
    res = det.score(AccessRequest("app", DataType.INTENT, t))
    lines.append(f"[{'ALERTA' if res.is_anomalous else 'OK'}] acceso normal      -> {res.reason}")

    # Caso 2: ráfaga (muchas solicitudes muy juntas).
    burst_flagged = 0
    for i in range(10):
        t += 0.02
        res = det.score(AccessRequest("app", DataType.INTENT, t))
        burst_flagged += res.is_anomalous
    lines.append(f"[{'ALERTA' if burst_flagged else 'OK'}] rafaga de 10 accesos -> {burst_flagged}/10 marcados anomalos")

    # Caso 3: tipo de dato nunca pedido antes (RAW_SIGNAL).
    t += 1.0
    res = det.score(AccessRequest("app", DataType.RAW_SIGNAL, t))
    lines.append(f"[{'ALERTA' if res.is_anomalous else 'OK'}] tipo nunca pedido   -> {res.reason}")

    report = "Paso 5 — anomaly\n" + "=" * 55 + "\n" + "\n".join(lines) + "\n"
    (demos / "step5_anomaly.txt").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    _demo()
