"""Filtro de consentimiento: cada app solo recibe el tipo de dato autorizado.

La pieza estrella. Mantiene el registro de apps y sus permisos por tipo de
dato, y aprueba o rechaza cada solicitud. Los tipos sensibles exigen siempre
aprobación explícita del usuario; en "modo confirmación", la exige todo tipo
(nada sale sin aprobación, spec v1 §4).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class DataType(Enum):
    """Tipos de dato neuronal, de más a menos sensible."""

    RAW_SIGNAL = "raw_signal"
    INTENT = "intent"
    CONFIRMED_TEXT = "confirmed_text"


# Tipos que SIEMPRE exigen aprobación explícita del usuario, haya o no
# modo confirmación. En modo confirmación, TODO tipo la exige (spec v1 §4).
SENSITIVE_TYPES = frozenset({DataType.RAW_SIGNAL})


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
        # confirmation_mode: si True, NADA sale sin aprobación explícita del
        # usuario (todo tipo). Los SENSITIVE_TYPES la exigen siempre.
        self.confirmation_mode = confirmation_mode
        self._permissions: dict[str, set[DataType]] = {}
        self._approvals: set[tuple[str, DataType]] = set()  # aprobaciones de un uso

    def register_app(self, app_id: str, allowed_types: set[DataType]) -> None:
        """Da de alta una app con sus tipos de dato permitidos."""
        self._permissions[app_id] = set(allowed_types)

    def permissions_of(self, app_id: str) -> set[DataType]:
        """Tipos permitidos a una app (vacío si no está registrada)."""
        return set(self._permissions.get(app_id, set()))

    @property
    def registered_apps(self) -> list[str]:
        return list(self._permissions)

    def approve_once(self, app_id: str, data_type: DataType) -> None:
        """El usuario autoriza una entrega puntual de un tipo sensible."""
        self._approvals.add((app_id, data_type))

    def requires_confirmation(self, data_type: DataType) -> bool:
        """¿Este tipo necesita aprobación explícita? Sensibles: siempre.
        En modo confirmación: todos (nada sale sin aprobación, spec v1 §4)."""
        return self.confirmation_mode or data_type in SENSITIVE_TYPES

    def consume_approval(self, app_id: str, data_type: DataType) -> None:
        """Gasta la aprobación de un uso (llamar solo cuando el dato sí se entrega)."""
        self._approvals.discard((app_id, data_type))

    def check(self, request: AccessRequest, consume: bool = True) -> Decision:
        """Decide si la solicitud está autorizada.

        Con consume=False solo verifica; el gateway consume la aprobación al
        final del pipeline, para no gastarla si otra defensa bloquea después.
        """
        app_id, dtype = request.app_id, request.data_type
        if app_id not in self._permissions:
            return Decision(False, f"app '{app_id}' no registrada")
        if dtype not in self._permissions[app_id]:
            return Decision(False, f"app '{app_id}' sin permiso para {dtype.value}")
        if self.requires_confirmation(dtype):
            key = (app_id, dtype)
            if key not in self._approvals:
                return Decision(False, f"requiere confirmación del usuario para {dtype.value}")
            if consume:
                self._approvals.discard(key)  # la aprobación es de un solo uso
        return Decision(True, "autorizado")


def _demo() -> None:
    """Una app legítima recibe solo lo suyo; una intrusa y una no registrada, no."""
    from pathlib import Path

    demos = Path(__file__).resolve().parent.parent / "demos"
    demos.mkdir(exist_ok=True)

    consent = ConsentFilter()
    consent.register_app("messaging_app", {DataType.CONFIRMED_TEXT})
    consent.register_app("cursor_app", {DataType.INTENT})

    pruebas = [
        ("messaging_app", DataType.CONFIRMED_TEXT),  # autorizado
        ("messaging_app", DataType.RAW_SIGNAL),      # sin permiso -> denegado
        ("cursor_app", DataType.INTENT),             # autorizado
        ("cursor_app", DataType.RAW_SIGNAL),         # sin permiso -> denegado
        ("unknown_app", DataType.INTENT),            # no registrada -> denegado
    ]
    lines = []
    for app_id, dtype in pruebas:
        d = consent.check(AccessRequest(app_id, dtype))
        mark = "PERMITIDO" if d.allowed else "BLOQUEADO"
        lines.append(f"[{mark}] {app_id:14s} pide {dtype.value:14s} -> {d.reason}")

    report = "Paso 4 — consent\n" + "=" * 50 + "\n" + "\n".join(lines) + "\n"
    (demos / "step4_consent.txt").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    _demo()
