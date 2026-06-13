"""SDK de cliente de NeuroGate.

Integra una app con el gateway NeuroGate en pocas líneas: pedir token, consumir
los scopes autorizados (intenciones por WebSocket, texto confirmado por REST) y,
para administradores, leer el estado y gestionar tokens/cuarentenas.
"""

from neurogate_client.client import NeuroGateClient, NeuroGateError

__all__ = ["NeuroGateClient", "NeuroGateError"]
__version__ = "0.1.0"
