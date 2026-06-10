# NeuroGate — Especificación del proyecto

> **Fuente de verdad del proyecto.** Todos los pasos de implementación apuntan
> a la visión descrita aquí. Si una decisión de código contradice este
> documento, este documento gana (o se actualiza primero, con acuerdo del autor).

---

## 1. Visión y meta

NeuroGate es un **guardia de seguridad para datos neuronales**: una capa de
software que se sienta entre un cerebro (simulado) y las aplicaciones que
quieren consumir su señal, y decide en tiempo real **qué información puede
salir y hacia quién**, bloqueando y registrando todo lo sospechoso.

Cuando esté terminado, cualquier persona podrá abrir una página web, ver una
señal cerebral simulada fluyendo, ver apps pidiendo acceso a ella, presionar
un botón de "ataque", y ver con sus propios ojos cómo el sistema detiene el
robo de datos neuronales. **Un sistema real y funcional, envuelto en una
demostración que cualquiera entiende en menos de un minuto.**

## 2. Qué NO es (disclaimer)

- **No es un dispositivo médico** ni pretende serlo. Es un prototipo educativo
  de simulación, sin certificación de ningún tipo.
- **No hay hardware.** No se conecta a ningún sensor real. La señal cerebral
  es 100% sintética (generada con numpy/scipy) o proviene de datasets públicos
  de EEG con fines educativos.
- **No es criptografía de producción.** Usa primitivas estándar correctamente,
  pero el manejo de claves está simplificado para fines de demostración.

## 3. El flujo en tiempo de ejecución

Este bucle ocurre muchas veces por segundo cuando el sistema está encendido:

```
┌─────────────┐   bloque    ┌─────────┐   intención   ┌──────────────────┐
│ Cerebro     │────señal───▶│ Decoder │──────────────▶│                  │
│ simulado    │   (EEG)     └─────────┘               │     GATEWAY      │
└─────────────┘                                       │                  │
                                                      │  ┌────────────┐  │
┌─────────────┐  solicitud                            │  │ Consent    │  │ 1. ¿Tiene permiso?
│ App cliente │────────────────────────────────────▶  │  │ Anomaly    │  │ 2. ¿Comportamiento normal?
│ (legítima o │                                       │  │ Crypto     │  │ 3. Cifrar lo que sale
│  maliciosa) │◀───dato cifrado o RECHAZO────────────  │  │ Audit      │  │ 4. Registrar todo
└─────────────┘                                       │  └────────────┘  │
                                                      └────────┬─────────┘
                                                               │ estado en vivo
                                                          ┌────▼─────┐
                                                          │ Dashboard │
                                                          └──────────┘
```

Paso a paso:

1. **Señal**: el cerebro simulado (`signal_source`) genera un bloque de señal
   tipo EEG — una onda con su ritmo y su ruido, como leería un sensor real.
2. **Decodificación**: el `decoder` clasifica ese bloque en una intención:
   `move_cursor`, `type_text` o `idle`. Traduce electricidad en significado.
3. **Solicitud**: una app pide un dato (señal cruda, intención, o texto
   confirmado). Antes de entregarlo:
4. **Consentimiento** (`consent`): ¿esta app tiene autorización para recibir
   ese tipo de dato? Si pide algo fuera de su permiso, se rechaza aquí mismo.
5. **Anomalías** (`anomaly`): en paralelo, ¿la app pide a un ritmo normal, a
   una hora normal, datos que suele pedir? Si el patrón se sale de lo normal,
   se levanta alerta **aunque el permiso técnicamente exista**.
6. **Cifrado** (`crypto_layer`): si todo está en orden, el dato sale cifrado.
   Solo la app autorizada, con su clave, puede descifrarlo.
7. **Auditoría** (`audit`): todo queda escrito — qué app, qué pidió, a qué
   hora, si se permitió o bloqueó, y por qué. Encadenado con hashes para que
   nadie pueda borrar o alterar el historial sin que se note.
8. **Panel** (`dashboard`): todo lo anterior se ve en vivo: la señal latiendo,
   las apps con su semáforo, el flujo de cada solicitud, y el contador de
   amenazas bloqueadas.

## 4. Arquitectura de módulos

Convención de idioma: **identificadores en inglés, docstrings/comentarios en
español** (ver `CLAUDE.md`).

### `neurogate/signal_source.py` — el cerebro simulado
- **Hace**: genera continuamente señal sintética tipo EEG en bloques (numpy),
  mezclando bandas de frecuencia realistas (alfa, beta…) con ruido.
- **Contrato**: `SignalSource.get_chunk() -> np.ndarray` (bloque de muestras).
- **Futuro**: podrá cargar datos reales de un dataset público de EEG detrás de
  la misma interfaz, sin que el resto del sistema cambie.

### `neurogate/decoder.py` — de electricidad a significado
- **Hace**: recibe bloques y los clasifica en intenciones usando un modelo
  simple de scikit-learn entrenado sobre la señal sintética.
- **Contrato**: `Decoder.decode(chunk: np.ndarray) -> Intent`, donde `Intent`
  es uno de `MOVE_CURSOR`, `TYPE_TEXT`, `IDLE`.

### `neurogate/consent.py` — el filtro de permisos (pieza estrella)
- **Hace**: mantiene el registro de apps y sus permisos por **tipo de dato**
  (`RAW_SIGNAL`, `INTENT`, `CONFIRMED_TEXT`). Aprueba o rechaza cada solicitud.
  Una app de mensajes quizá solo puede recibir texto que el usuario confirmó;
  **jamás** la señal cruda del cerebro.
- **Incluye**: "modo confirmación" — nada sale sin aprobación explícita del
  usuario.
- **Contrato**: `ConsentFilter.check(app_id: str, data_type: DataType) -> Decision`
  (permitido/denegado + motivo).

### `neurogate/anomaly.py` — el vigilante de comportamiento
- **Hace**: aprende el patrón normal de accesos (frecuencia, hora, tipo de
  dato pedido) y dispara alertas ante comportamientos raros, usando un
  **Isolation Forest** de scikit-learn.
- **Contrato**: `AnomalyDetector.score(request: AccessRequest) -> AnomalyResult`
  (normal/anómalo + score).

### `neurogate/crypto_layer.py` — el blindaje
- **Hace**: cifra cada dato que sale con AES (Fernet, de `cryptography`),
  dando a **cada app su propia clave**. Interceptarlo en tránsito no sirve.
- **Contrato**: `CryptoLayer.encrypt_for(app_id, data) -> bytes` /
  `CryptoLayer.decrypt(app_id, token) -> data`.

### `neurogate/audit.py` — la memoria inalterable
- **Hace**: escribe cada evento en un log JSONL append-only donde cada entrada
  incluye el hash SHA-256 de la anterior. Alterar o borrar una línea rompe la
  cadena y se detecta en verificación.
- **Contrato**: `AuditLog.append(event: AuditEvent) -> None` /
  `AuditLog.verify_chain() -> bool`.

### `neurogate/gateway.py` — el director de orquesta
- **Hace**: conecta todos los módulos anteriores en el flujo completo
  (sección 3) y expone el estado en vivo que consume el dashboard.
- **Contrato**: `Gateway.handle_request(request: AccessRequest) -> GatewayResponse`.

### `neurogate/dashboard.py` — la vitrina (Streamlit)
- **Hace**: panel web con la señal en vivo, el semáforo de apps, el flujo de
  solicitudes por las capas, el contador de amenazas bloqueadas y el botón
  **"Simular ataque"**.
- **Se ejecuta con**: `streamlit run neurogate/dashboard.py`.

### `tests/attack_sim.py` — el villano de la demo
- **Hace**: simula una app maliciosa que (1) pide señal cruda sin permiso,
  (2) lee a un ritmo anómalo, y (3) intenta inyectar comandos. Demuestra,
  vía pytest, que las tres defensas funcionan y todo queda registrado.

## 5. Los 11 pasos (roadmap)

Cada paso produce algo **demostrable por sí solo**. No se avanza al siguiente
sin la aprobación del autor sobre el paso actual.

| Paso | Qué se construye | Criterio de "hecho" |
|------|------------------|---------------------|
| 1 | Cimientos: estructura, esqueletos, requirements, README, git | El paquete importa; primer commit hecho; estructura aprobada |
| 2 | `signal_source.py` | Señal sintética visible en una gráfica de matplotlib |
| 3 | `decoder.py` | Intenciones impresas en terminal a partir de la señal |
| 4 | `consent.py` | App legítima recibe solo lo suyo; app sin permiso, rechazada |
| 5 | `anomaly.py` | Un patrón de acceso anómalo dispara alerta en demo de terminal |
| 6 | `crypto_layer.py` | Dato cifrado solo descifrable con la clave correcta |
| 7 | `audit.py` | Log encadenado; alterar una línea rompe `verify_chain()` |
| 8 | `gateway.py` | Flujo completo end-to-end demostrable por terminal |
| 9 | `tests/attack_sim.py` | Los 3 ataques bloqueados y registrados (pytest en verde) |
| 10 | `dashboard.py` | Demo visual local funcionando con Streamlit |
| 11 | Despliegue | URL pública en Streamlit Cloud, lista para mostrar a inversores |

Al terminar el **Paso 9** el sistema central está completo y demostrable por
terminal. Al terminar el **Paso 11** la demo está lista para un inversor.

## 6. Criterios de "perfecto" (definición de terminado)

El proyecto está terminado cuando se cumplen estas seis cosas, en orden:

1. La señal fluye.
2. El decodificador la interpreta.
3. Una app legítima recibe **solo** lo que le corresponde.
4. Una app maliciosa es **bloqueada y registrada**.
5. Todo viaja **cifrado**.
6. Cualquier persona no técnica entiende el valor viendo la demo en
   **menos de un minuto**.

Ni antes, ni después.

## 7. Stack técnico

- Python 3.11+
- `numpy`, `scipy` — generación y procesamiento de señal
- `scikit-learn` — decoder e Isolation Forest
- `cryptography` — cifrado AES (Fernet)
- `matplotlib` — gráficas en demos de terminal
- `streamlit` — dashboard web y despliegue (Streamlit Cloud)
- `pytest` — pruebas y simulación de ataque
