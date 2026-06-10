"""Detector de anomalías: alerta ante patrones de acceso raros (Isolation Forest)."""

from __future__ import annotations

from dataclasses import dataclass

from neurogate.consent import AccessRequest


@dataclass(frozen=True)
class AnomalyResult:
    """Veredicto del detector sobre una solicitud."""

    is_anomalous: bool
    score: float  # más negativo = más raro (convención de IsolationForest)
    reason: str


class AnomalyDetector:
    """Aprende el patrón normal de accesos y puntúa cada solicitud."""

    def __init__(self) -> None:
        # TODO (Paso 5): IsolationForest + historial de accesos.
        raise NotImplementedError("Se implementa en el Paso 5")

    def fit(self, history: list[AccessRequest]) -> None:
        """Entrena con un historial de accesos normales."""
        # TODO (Paso 5): features = frecuencia, hora, tipo de dato.
        raise NotImplementedError("Se implementa en el Paso 5")

    def score(self, request: AccessRequest) -> AnomalyResult:
        """¿Encaja en el patrón normal o es raro?"""
        # TODO (Paso 5)
        raise NotImplementedError("Se implementa en el Paso 5")


# TODO (Paso 5): demo `python -m neurogate.anomaly`: una ráfaga dispara la alerta.
