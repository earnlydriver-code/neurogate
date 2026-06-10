"""Filtro de consentimiento: cada app solo recibe el tipo de dato autorizado."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class DataType(Enum):
    """Tipos de dato neuronal, de más a menos sensible."""

    RAW_SIGNAL = "raw_signal"
    INTENT = "intent"
    CONFIRMED_TEXT = "confirmed_text"


@dataclass(frozen=True)
class AccessRequest:
    """Solicitud de datos de una app; viaja por todas las defensas."""

    app_id: str
    data_type: DataType
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class Decision:
    """Veredicto del filtro: permitido o no, y por qué."""

    allowed: bool
    reason: str


class ConsentFilter:
    """Registro de apps y permisos; decide cada solicitud."""

    def __init__(self, confirmation_mode: bool = False) -> None:
        # confirmation_mode: si True, nada sale sin aprobación explícita del usuario.
        # TODO (Paso 4)
        raise NotImplementedError("Se implementa en el Paso 4")

    def register_app(self, app_id: str, allowed_types: set[DataType]) -> None:
        """Da de alta una app con sus tipos de dato permitidos."""
        # TODO (Paso 4)
        raise NotImplementedError("Se implementa en el Paso 4")

    def check(self, request: AccessRequest) -> Decision:
        """Decide si la solicitud está autorizada."""
        # TODO (Paso 4): app no registrada o tipo fuera de permisos -> denegada.
        raise NotImplementedError("Se implementa en el Paso 4")


# TODO (Paso 4): demo `python -m neurogate.consent`: app legítima pasa, intrusa no.
