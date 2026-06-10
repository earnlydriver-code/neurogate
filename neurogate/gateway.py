"""El director de orquesta: une todos los módulos en el flujo completo.

El gateway es el único punto por donde los datos neuronales salen hacia las
apps. Por cada solicitud ejecuta el pipeline de defensas, en este orden:

    1. consent  -> ¿la app tiene permiso para este tipo de dato?
    2. anomaly  -> ¿su comportamiento es normal?
    3. crypto   -> si pasa, el dato sale cifrado con la clave de la app
    4. audit    -> pase lo que pase, el evento queda registrado

Además expone el estado en vivo (señal actual, última intención, contadores
de solicitudes y bloqueos) que el dashboard consume para pintarse.
"""

from __future__ import annotations

from dataclasses import dataclass

from neurogate.consent import AccessRequest


@dataclass(frozen=True)
class GatewayResponse:
    """Lo que recibe una app tras su solicitud."""

    allowed: bool
    payload: bytes | None  # el dato cifrado si se permitió; None si se bloqueó
    reason: str            # el porqué, para la demo y la auditoría


class Gateway:
    """Orquesta señal, decoder y las cuatro defensas."""

    def __init__(self) -> None:
        # TODO (Paso 8): instanciar SignalSource, Decoder, ConsentFilter,
        # AnomalyDetector, CryptoLayer y AuditLog, y cablearlos.
        raise NotImplementedError("Se implementa en el Paso 8")

    def handle_request(self, request: AccessRequest) -> GatewayResponse:
        """Procesa una solicitud de app por todo el pipeline de defensas."""
        # TODO (Paso 8): consent.check -> anomaly.score -> crypto.encrypt_for
        # -> audit.append, devolviendo el veredicto con su motivo.
        raise NotImplementedError("Se implementa en el Paso 8")

    def get_live_state(self) -> dict:
        """Estado en vivo para el dashboard (señal, intención, contadores)."""
        # TODO (Paso 8): devolver un snapshot serializable del estado.
        raise NotImplementedError("Se implementa en el Paso 8")


# TODO (Paso 8): demo ejecutable `python -m neurogate.gateway`: el bucle
# completo en terminal — señal -> intención -> solicitudes de una app legítima
# y una maliciosa -> veredictos y log (criterio de "hecho" del paso).
