"""El vigilante de comportamiento: detecta accesos anómalos.

Aunque una app tenga permiso, su COMPORTAMIENTO puede delatarla: pedir datos
a un ritmo inusual, a horas raras, o de tipos que nunca antes pidió. Este
módulo aprende el patrón normal de accesos y dispara alertas ante lo raro,
usando un Isolation Forest (scikit-learn).

Es la segunda línea de defensa: consent revisa el permiso (la regla),
anomaly revisa la conducta (el patrón).
"""

from __future__ import annotations

from dataclasses import dataclass

from neurogate.consent import AccessRequest


@dataclass(frozen=True)
class AnomalyResult:
    """El veredicto del detector sobre una solicitud."""

    is_anomalous: bool
    score: float  # cuanto más negativo, más raro (convención de IsolationForest)
    reason: str


class AnomalyDetector:
    """Aprende el patrón normal de accesos y puntúa cada solicitud nueva."""

    def __init__(self) -> None:
        # TODO (Paso 5): crear el IsolationForest y el historial de accesos.
        raise NotImplementedError("Se implementa en el Paso 5")

    def fit(self, history: list[AccessRequest]) -> None:
        """Entrena el detector con un historial de accesos normales.

        Convierte cada solicitud en features de comportamiento (frecuencia
        de acceso, hora del día, tipo de dato) y ajusta el modelo.
        """
        # TODO (Paso 5): extraer features del historial y entrenar.
        raise NotImplementedError("Se implementa en el Paso 5")

    def score(self, request: AccessRequest) -> AnomalyResult:
        """Puntúa una solicitud: ¿encaja en el patrón normal o es rara?"""
        # TODO (Paso 5): extraer features de la solicitud, puntuar con el
        # modelo y devolver el veredicto con motivo legible.
        raise NotImplementedError("Se implementa en el Paso 5")


# TODO (Paso 5): demo ejecutable `python -m neurogate.anomaly`: un patrón de
# acceso anómalo (ráfaga de solicitudes) dispara la alerta en terminal.
