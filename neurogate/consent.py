"""El filtro de consentimiento: cada app solo recibe lo que tiene autorizado.

La pieza estrella del sistema. Mantiene el registro de apps y sus permisos
por TIPO de dato, y aprueba o rechaza cada solicitud antes de que nada salga.
Una app de mensajes quizá solo puede recibir texto que el usuario confirmó;
jamás la señal cruda del cerebro.

Incluye el "modo confirmación": cuando está activo, nada sale sin la
aprobación explícita del usuario, aunque el permiso exista.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class DataType(Enum):
    """Los tipos de dato neuronal que una app puede solicitar.

    Ordenados de más sensible a menos sensible.
    """

    RAW_SIGNAL = "raw_signal"          # señal cruda del cerebro (máxima sensibilidad)
    INTENT = "intent"                  # intención decodificada (mover, escribir, nada)
    CONFIRMED_TEXT = "confirmed_text"  # texto que el usuario aprobó explícitamente


@dataclass(frozen=True)
class AccessRequest:
    """Una solicitud de datos hecha por una app al gateway.

    Es el objeto que viaja por todas las defensas: consent la autoriza,
    anomaly la puntúa y audit la registra.
    """

    app_id: str
    data_type: DataType
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class Decision:
    """El veredicto del filtro de consentimiento sobre una solicitud."""

    allowed: bool
    reason: str  # siempre explicamos el porqué: alimenta el log de auditoría


class ConsentFilter:
    """Registro de apps y sus permisos; decide cada solicitud."""

    def __init__(self, confirmation_mode: bool = False) -> None:
        """Args:
            confirmation_mode: si True, toda entrega requiere además la
                aprobación explícita del usuario.
        """
        # TODO (Paso 4): inicializar el registro de apps (dict app_id ->
        # conjunto de DataType permitidos) y el estado del modo confirmación.
        raise NotImplementedError("Se implementa en el Paso 4")

    def register_app(self, app_id: str, allowed_types: set[DataType]) -> None:
        """Da de alta una app con los tipos de dato que puede recibir."""
        # TODO (Paso 4): guardar los permisos de la app.
        raise NotImplementedError("Se implementa en el Paso 4")

    def check(self, request: AccessRequest) -> Decision:
        """Decide si una solicitud está autorizada.

        Reglas: app no registrada -> denegada; tipo de dato fuera de sus
        permisos -> denegada; modo confirmación activo sin aprobación del
        usuario -> denegada. Solo si todo pasa, se permite.
        """
        # TODO (Paso 4): aplicar las reglas y devolver Decision con motivo.
        raise NotImplementedError("Se implementa en el Paso 4")


# TODO (Paso 4): demo ejecutable `python -m neurogate.consent`: una app
# legítima recibe solo lo suyo y una app sin permiso es rechazada.
