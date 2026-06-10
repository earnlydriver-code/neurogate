"""El villano de la demo: una app maliciosa que intenta robar datos neuronales.

Simula los tres ataques que NeuroGate debe detener, y los convierte en
pruebas pytest que demuestran que las defensas funcionan:

    1. Pedir señal cruda sin permiso       -> consent debe bloquear.
    2. Leer a un ritmo anómalo (ráfaga)    -> anomaly debe alertar.
    3. Intentar inyectar comandos          -> el gateway debe rechazar y registrar.

Y en todos los casos: el intento queda escrito en el log de auditoría.
"""

from __future__ import annotations

import pytest


class MaliciousApp:
    """App atacante: se registra con permisos mínimos y luego intenta de más."""

    def __init__(self, app_id: str = "evil_app") -> None:
        # TODO (Paso 9): registrarse en el gateway con permisos mínimos
        # (solo CONFIRMED_TEXT) para luego intentar excederlos.
        raise NotImplementedError("Se implementa en el Paso 9")


@pytest.mark.skip(reason="Se implementa en el Paso 9")
def test_raw_signal_theft_is_blocked() -> None:
    """Ataque 1: pedir RAW_SIGNAL sin permiso -> bloqueado y auditado."""
    raise NotImplementedError


@pytest.mark.skip(reason="Se implementa en el Paso 9")
def test_burst_access_triggers_anomaly_alert() -> None:
    """Ataque 2: ráfaga de solicitudes -> el detector de anomalías alerta."""
    raise NotImplementedError


@pytest.mark.skip(reason="Se implementa en el Paso 9")
def test_command_injection_is_rejected_and_logged() -> None:
    """Ataque 3: inyectar comandos -> rechazado y registrado en auditoría."""
    raise NotImplementedError
