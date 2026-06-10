"""Gateway: une todo el flujo. Pipeline por solicitud:

    1. consent  ¿tiene permiso?
    2. anomaly  ¿comportamiento normal?
    3. crypto   cifrar lo que sale
    4. audit    registrar todo, pase lo que pase
"""

from __future__ import annotations

from dataclasses import dataclass

from neurogate.consent import AccessRequest


@dataclass(frozen=True)
class GatewayResponse:
    """Lo que recibe una app tras su solicitud."""

    allowed: bool
    payload: bytes | None  # dato cifrado si se permitió; None si se bloqueó
    reason: str


class Gateway:
    """Orquesta señal, decoder y las cuatro defensas."""

    def __init__(self) -> None:
        # TODO (Paso 8): instanciar y cablear todos los módulos.
        raise NotImplementedError("Se implementa en el Paso 8")

    def handle_request(self, request: AccessRequest) -> GatewayResponse:
        """Procesa una solicitud por todo el pipeline de defensas."""
        # TODO (Paso 8)
        raise NotImplementedError("Se implementa en el Paso 8")

    def get_live_state(self) -> dict:
        """Snapshot del estado en vivo para el dashboard."""
        # TODO (Paso 8)
        raise NotImplementedError("Se implementa en el Paso 8")


# TODO (Paso 8): demo `python -m neurogate.gateway`: flujo completo en terminal.
