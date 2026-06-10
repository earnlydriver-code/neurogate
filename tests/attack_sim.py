"""App maliciosa: los tres ataques que NeuroGate debe detener, como tests pytest."""

from __future__ import annotations

import pytest


class MaliciousApp:
    """Se registra con permisos mínimos y luego intenta excederlos."""

    def __init__(self, app_id: str = "evil_app") -> None:
        # TODO (Paso 9)
        raise NotImplementedError("Se implementa en el Paso 9")


@pytest.mark.skip(reason="Se implementa en el Paso 9")
def test_raw_signal_theft_is_blocked() -> None:
    """Pedir RAW_SIGNAL sin permiso -> bloqueado y auditado."""
    raise NotImplementedError


@pytest.mark.skip(reason="Se implementa en el Paso 9")
def test_burst_access_triggers_anomaly_alert() -> None:
    """Ráfaga de solicitudes -> el detector de anomalías alerta."""
    raise NotImplementedError


@pytest.mark.skip(reason="Se implementa en el Paso 9")
def test_command_injection_is_rejected_and_logged() -> None:
    """Inyectar comandos -> rechazado y registrado en auditoría."""
    raise NotImplementedError
