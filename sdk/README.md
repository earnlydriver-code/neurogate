# neurogate-client

SDK de cliente para el gateway **NeuroGate**. Integra una app con el gateway en
pocas líneas: pide token, consume los scopes autorizados y, como admin, gestiona
el servicio.

## Instalación

```bash
pip install ./sdk        # desde el repo (editable: pip install -e ./sdk)
```

## Uso

Consumir intenciones decodificadas (scope `read:intent`):

```python
from neurogate_client import NeuroGateClient

client = NeuroGateClient("http://127.0.0.1:8077", "cursor_app", "cursor-secret-please-change")
for msg in client.stream_intents(max_messages=10):
    print(msg["intent"])        # idle / move_cursor / type_text ...
```

Texto confirmado (scope `read:confirmed_text`):

```python
data = NeuroGateClient(url, "messaging_app", secret).get_confirmed_text()
```

Administración (scope `admin`):

```python
admin = NeuroGateClient(url, "dashboard_admin", secret)
print(admin.get_state())        # apps, contadores, integridad del log
admin.release("messaging_app")  # sacar de cuarentena
```

El SDK cachea el token y reintenta una vez si caduca. La señal viaja cifrada por
la red. Levanta el gateway de demo con `python run_demo_e.py`.
