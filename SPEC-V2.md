# SPEC-V2 — NeuroGate (Versión Oficial / Técnica)

> **Fuente de verdad para la v2.** Este documento extiende y sustituye a `SPEC.md` (v1 educativa) como guía de implementación una vez completados los Pasos 1–9 de la v1. La v1 no se descarta: es la base sobre la que se construye. Los contratos entre módulos definidos en v1 se mantienen; lo que cambia son las implementaciones detrás de esos contratos.

---

## 0. Prerrequisito

**No iniciar la v2 hasta que la v1 esté completa hasta el Paso 9** (sistema central demostrable por terminal, con `tests/attack_sim.py` pasando). La v1 en simulación es el criterio de verdad: cada fase de la v2 debe reproducir el mismo comportamiento de seguridad que la v1, pero sobre componentes reales.

---

## 1. Visión

NeuroGate v2 es un **middleware de seguridad y cumplimiento para datos neuronales, agnóstico al fabricante del dispositivo**. Se instala entre cualquier fuente de señal cerebral (hardware BCI real o simulado) y las aplicaciones que la consumen, y garantiza:

1. Que ninguna app recibe datos neuronales sin autorización explícita, granular y revocable.
2. Que todo acceso queda registrado en un log auditable, encadenado y firmado, verificable por terceros.
3. Que comportamientos anómalos de acceso se detectan y bloquean aunque exista permiso formal.
4. Que todo dato en tránsito viaja cifrado.

**Diferencia clave con la v1:** la v1 demuestra el concepto en un solo proceso con señal inventada. La v2 es un **servicio real**: las apps son procesos externos que se conectan por red, se autentican con tokens, y la señal proviene de una pipeline de adquisición estándar de la industria (BrainFlow), compatible con hardware físico sin cambiar código.

**Posicionamiento de producto:** capa de cumplimiento regulatorio para neurotecnología. No competimos con los fabricantes (Emotiv, OpenBCI, Muse); les damos —y damos a los desarrolladores de apps— la pieza que la regulación les va a exigir.

---

## 2. Qué NO es (sin cambios respecto a v1)

- No es un dispositivo médico ni software de diagnóstico.
- No procesa datos de pacientes reales. Los datos reales que se usan son **datasets públicos anonimizados** (BCI Competition IV, PhysioNet) y señal de placas sintéticas o de hardware de consumo operado voluntariamente por el desarrollador.
- Disclaimer educativo/experimental visible en README, dashboard y documentación.

---

## 3. Mapeo regulatorio (el porqué del producto)

Cada módulo responde a un requisito regulatorio concreto. Este mapeo debe mantenerse actualizado en la documentación y es el esqueleto del pitch:

| Módulo | Requisito regulatorio que satisface |
|---|---|
| `consent.py` (scopes OAuth2, tokens revocables, modo confirmación) | Consentimiento informado, granular, específico y revocable para datos neuronales (leyes de privacidad de datos neuronales tipo Colorado/California 2024; principios de neuroderechos tipo Chile 2021) |
| `audit.py` (log encadenado + firmado) | Trazabilidad, accountability, evidencia de cumplimiento auditable por terceros |
| `crypto_layer.py` (TLS + claves por app + rotación) | Seguridad de datos sensibles / categoría datos de salud |
| `anomaly.py` (detección de abuso post-permiso) | Deber de protección activa, minimización del daño |
| `gateway.py` (mediación de todo acceso) | Principio de minimización de datos: cada app recibe solo lo estrictamente autorizado |

**Nota para el pitch:** la regulación de datos neuronales avanza en una sola dirección (más estricta). NeuroGate vende la capa que convierte "cumplir" en instalar un middleware en vez de construir todo esto desde cero.

---

## 4. Arquitectura v2

```
┌─────────────────────┐
│  FUENTE DE SEÑAL     │   BrainFlow (Synthetic Board ↔ hardware real
│  signal_source.py    │   con el MISMO código) o dataset público
└────────┬────────────┘
         │ chunks de señal (numpy, formato BrainFlow)
         ▼
┌─────────────────────┐
│  DECODER             │   MNE-Python: filtrado, épocas, CSP +
│  decoder.py          │   clasificador entrenado en BCI Competition IV 2a
└────────┬────────────┘
         │ Intent {move_left, move_right, idle, ...} + confianza
         ▼
┌──────────────────────────────────────────────────┐
│  GATEWAY (servicio FastAPI)                       │
│  gateway.py                                       │
│                                                   │
│   request de app ──► auth (JWT + scopes)          │
│                  ──► consent.py  (¿scope válido?) │
│                  ──► anomaly.py  (¿patrón normal?)│
│                  ──► crypto_layer.py (cifrar)     │
│                  ──► audit.py    (registrar TODO) │
│                  ──► respuesta o bloqueo          │
└────────┬─────────────────────────┬───────────────┘
         │ WebSocket/REST (TLS)    │ estado en vivo
         ▼                         ▼
┌─────────────────┐      ┌──────────────────┐
│  APPS EXTERNAS   │      │  DASHBOARD        │
│  (procesos       │      │  dashboard.py     │
│  independientes) │      │  (Streamlit)      │
└─────────────────┘      └──────────────────┘
```

Cambio arquitectónico central respecto a v1: **las apps dejan de ser objetos en el mismo proceso y pasan a ser clientes de red autenticados.** El gateway es el único punto de entrada a los datos neuronales.

---

## 5. Especificación por módulo

### 5.1 `signal_source.py` — adquisición vía BrainFlow

- Reescribir sobre la API de BrainFlow (`brainflow` en requirements).
- Por defecto usa `BoardIds.SYNTHETIC_BOARD`. El ID de placa es **configurable** (variable de entorno / config), de modo que conectar un OpenBCI Ganglion o un Muse sea cambiar un parámetro, cero cambios de código.
- Mantener la interfaz v1: `SignalSource.get_chunk() -> np.ndarray`. Internamente añade: metadatos de canales, frecuencia de muestreo real de la placa, timestamps.
- Modo alternativo `DatasetSource`: reproduce un dataset público (BCI Competition IV 2a vía MOABB o descarga directa) como si fuera streaming en vivo, a velocidad real. Misma interfaz.
- **Criterio de hecho:** la misma pipeline corre con (a) placa sintética y (b) dataset real, conmutando por config; demo que grafica ambas señales.

### 5.2 `decoder.py` — decodificación real con MNE

- Pipeline MNE-Python: filtro banda (8–30 Hz para motor imagery), segmentación en épocas, extracción CSP (Common Spatial Patterns), clasificador (LDA o SVM lineal de scikit-learn).
- Entrenamiento offline sobre BCI Competition IV 2a (motor imagery: mano izquierda / mano derecha / pies / lengua). Script de entrenamiento separado (`train_decoder.py`) que guarda el modelo serializado.
- En runtime, `Decoder.decode(chunk) -> Intent` carga el modelo entrenado y clasifica. `Intent` ahora incluye `confidence: float`; por debajo de un umbral configurable, devuelve `idle`.
- **Reportar accuracy honestamente** en la documentación (validación cruzada por sujeto). No inflar: en motor imagery 4 clases, 60–80% según sujeto es lo normal y es suficiente para la demo.
- **Criterio de hecho:** accuracy de validación documentada; demo en terminal que reproduce el dataset y muestra intenciones decodificadas con su confianza.

### 5.3 `consent.py` — consentimiento modelo OAuth2

- Cada app se **registra** y recibe `client_id` + `client_secret`.
- Las apps obtienen **tokens JWT** con: `client_id`, lista de `scopes`, expiración (`exp`), `jti` (ID de token para revocación).
- Scopes definidos: `read:intent`, `read:confirmed_text`, `read:raw_signal` (este último solo concedible en "modo clínico", desactivado por defecto), `read:stats`.
- **Revocación en caliente:** lista de revocación consultada en cada request; revocar un token corta el acceso inmediatamente.
- **Modo confirmación** (heredado de v1, ahora sobre red): para scopes sensibles, cada entrega requiere aprobación explícita del usuario en el dashboard antes de salir.
- Librerías: `pyjwt` (o `python-jose`), `passlib` para secretos.
- **Criterio de hecho:** app con token válido y scope correcto recibe datos; token expirado → 401; scope insuficiente → 403 + evento de auditoría; token revocado → bloqueado al instante.

### 5.4 `anomaly.py` — detección sobre telemetría real

- Mismo Isolation Forest de v1, pero las features ahora son **telemetría real del gateway**: requests/minuto por app, distribución de scopes solicitados, hora del día, tamaño de payload, ratio de errores 4xx, novedad del endpoint.
- Fase de *baseline learning* configurable (aprende el patrón normal durante N minutos/requests) y luego modo vigilancia.
- Ante anomalía: el gateway pasa la app a estado `quarantine` (bloqueo temporal + alerta en dashboard + evento de auditoría), reversible manualmente.
- **Criterio de hecho:** un cliente que de pronto multiplica ×20 su tasa de requests o pide un scope que jamás usó entra en cuarentena automáticamente, con todo registrado.

### 5.5 `crypto_layer.py` — transporte y claves serias

- **TLS en el transporte:** el gateway FastAPI sirve sobre HTTPS/WSS (certificado autofirmado en desarrollo; documentar cómo usar uno real en despliegue).
- **Cifrado de payload por app** (defensa en profundidad, además de TLS): clave simétrica derivada por app (HKDF a partir de una master key + `client_id`), rotación de claves programada (rotar cada N horas o bajo comando), versionado de clave en cada mensaje para descifrar correctamente durante la rotación.
- Master key fuera del código: variable de entorno / archivo `.env` (en `.gitignore`). Documentar que en producción real iría en un KMS.
- **Criterio de hecho:** sniffear el tráfico (demo con un script) muestra solo bytes cifrados; una app no puede descifrar mensajes de otra; la rotación no interrumpe el servicio.

### 5.6 `audit.py` — log encadenado y firmado

- Se mantiene la cadena de hashes SHA-256 de v1 (cada entrada incluye el hash de la anterior).
- **Nuevo:** cada entrada se **firma** con una clave privada Ed25519 del gateway (`cryptography`). Se publica la clave pública, de modo que un tercero puede verificar (a) integridad de la cadena y (b) autenticidad del emisor, sin acceso al sistema.
- Herramienta CLI `verify_audit.py`: recibe el log + clave pública y dictamina íntegro/alterado, señalando la primera entrada corrupta.
- Formato JSONL append-only. Campos mínimos: timestamp, `client_id`, scope solicitado, decisión (allow/deny/quarantine), motivo, hash previo, firma.
- **Criterio de hecho:** alterar un carácter de cualquier línea hace fallar la verificación externa; la demo lo muestra.

### 5.7 `gateway.py` — el servicio FastAPI

- Migrar de orquestador en-proceso a **servicio FastAPI** (`fastapi`, `uvicorn`, `websockets` en requirements).
- Endpoints mínimos:
  - `POST /auth/token` — emite JWT a apps registradas (client credentials).
  - `WS /stream/intents` — stream de intenciones decodificadas (requiere `read:intent`).
  - `GET /data/confirmed_text` — datos bajo modo confirmación (requiere `read:confirmed_text`).
  - `GET /admin/state` — estado en vivo para el dashboard (apps, semáforos, contadores, alertas). Protegido con scope `admin`.
  - `POST /admin/revoke` — revocación de tokens.
- **Flujo por request:** autenticación JWT → `consent.check(scopes)` → `anomaly.observe(telemetría)` → si todo pasa: `crypto.encrypt(payload)` → respuesta. **Toda decisión, en cualquier rama, pasa por `audit.append()`. Sin excepciones.**
- El loop señal→decoder corre como tarea de fondo del servicio; el estado decodificado más reciente se mantiene en memoria para servir a los streams.
- **Criterio de hecho:** dos apps de ejemplo (scripts cliente independientes en `examples/`) corren en procesos separados, se autentican, y reciben streams simultáneos según sus scopes; todo el flujo v1 reproducido extremo a extremo, ahora por red.

### 5.8 `tests/attack_sim.py` — suite de ataques ampliada

Mantener los 3 ataques de v1 (señal cruda sin permiso, lectura a ritmo anómalo, inyección de comandos) y añadir, ahora que hay red y tokens:

1. **Token robado:** reutilizar un token revocado → debe fallar.
2. **Replay attack:** reenviar una request/mensaje capturado → debe fallar (nonce/timestamp en mensajes cifrados).
3. **Escalada de scopes:** app con `read:intent` intenta `read:raw_signal` → 403 + auditoría.
4. **Token forjado:** JWT firmado con clave incorrecta → 401.
5. **Flood:** ráfaga masiva de requests → cuarentena por anomalía.

Todo como suite `pytest` automatizada + script de demo visual (`demo_attack.py`) que lanza los ataques en vivo contra el gateway con narración en terminal.

- **Criterio de hecho:** `pytest` verde con los 8 ataques bloqueados y cada bloqueo presente en el log auditado.

### 5.9 `dashboard.py` — demo apuntando al servicio real

- Streamlit se mantiene, pero ya no comparte proceso con el gateway: **consume `GET /admin/state`** (y un WS si hace falta) como un cliente más, con su token de scope `admin`.
- Vistas: señal en vivo, semáforo de apps (verde/amarillo-cuarentena/rojo-bloqueada), feed de solicitudes en tiempo real, contador de amenazas bloqueadas, botón **"Simular ataque"** que dispara `demo_attack.py` contra el gateway y se ve el bloqueo en vivo, panel de modo confirmación (aprobar/denegar entregas pendientes), verificación de integridad del log con un clic.
- **Criterio de hecho:** una persona no técnica entiende qué hace NeuroGate viendo el dashboard menos de 1 minuto (criterio heredado de v1, intacto).

---

## 6. Fases de implementación de la v2

Regla de oro heredada de v1: **una fase a la vez, cada fase termina en algo demostrable + commit + aprobación del usuario antes de seguir.**

| Fase | Contenido | Demo de cierre |
|---|---|---|
| **A — Señal real** | `signal_source.py` sobre BrainFlow (Synthetic Board) + `DatasetSource` con dataset público | Misma pipeline v1 corriendo con ambas fuentes, conmutables por config |
| **B — Decoder real** | MNE + CSP + clasificador entrenado en BCI Competition IV 2a; `train_decoder.py`; accuracy documentada | Dataset reproducido en vivo → intenciones reales decodificadas en terminal |
| **C — Gateway como servicio** | FastAPI + JWT/scopes + revocación + dos apps cliente de ejemplo | Dos procesos externos autenticados recibiendo streams según permisos |
| **D — Hardening** | TLS, cifrado por app con rotación, log firmado Ed25519 + `verify_audit.py`, anomalías sobre telemetría real, suite de 8 ataques | `pytest` verde; demo de ataques en vivo, todos bloqueados y auditados |
| **E — Demo de inversión** | Dashboard contra el gateway real; despliegue (gateway en un VPS/contenedor + dashboard en Streamlit Cloud); opcional: hardware físico (OpenBCI Ganglion / Muse 2) | URL pública + guion de demo de 1 minuto; si hay hardware: "mi cerebro en vivo, protegido" |

Las fases A y B son independientes entre sí (pueden invertirse). C depende de A o B (necesita algo que servir). D depende de C. E depende de D.

---

## 7. Stack v2 (acumulado)

- Python 3.11+
- Adquisición: `brainflow`
- Neuro/ML: `mne`, `moabb` (datasets), `numpy`, `scipy`, `scikit-learn`
- Servicio: `fastapi`, `uvicorn[standard]`, `websockets`, `httpx` (clientes/tests)
- Seguridad: `cryptography`, `pyjwt`, `passlib`
- UI: `streamlit`, `matplotlib`, `plotly`
- Tests: `pytest`, `pytest-asyncio`
- Config: `pydantic-settings`, `.env` (en `.gitignore`)

Convención de idioma sin cambios: **identificadores en inglés, docstrings/comentarios/docs en español.** Código legible antes que clever: sigue siendo material de estudio además de producto.

---

## 8. Criterios de "perfecto" de la v2

Heredan y extienden los 6 de la v1. La v2 está terminada cuando, **sobre el servicio real y por red**:

1. La señal fluye desde BrainFlow (sintética o dataset, conmutable; hardware-ready).
2. El decoder interpreta intenciones reales con accuracy documentada.
3. Una app legítima, autenticada con token y scopes, recibe exactamente lo autorizado y nada más.
4. Los 8 ataques de la suite son bloqueados, auditados, y reproducibles con `pytest` y en demo visual.
5. Todo el tráfico viaja cifrado (TLS + payload), las claves rotan, y nadie descifra lo ajeno.
6. El log es verificable por un tercero externo con `verify_audit.py` y la clave pública.
7. Una persona no técnica entiende el valor viendo la demo en menos de 1 minuto.
8. El mapeo módulo→requisito regulatorio está documentado y al día (es el pitch).

---

## 9. Notas para Claude Code

- `SPEC.md` (v1) sigue siendo válido como referencia histórica de los contratos; ante conflicto en la v2, **manda este documento**.
- Mantener en `CLAUDE.md` la línea de estado, ahora con formato: `Fase actual: v2-A` (etc.), actualizada al cerrar cada fase.
- No adelantar fases. No introducir dependencias de una fase futura "porque ya estamos aquí".
- Cada fase cierra con: demo ejecutable + tests en verde + commit descriptivo + mostrar resultado al usuario y esperar aprobación.
- Secretos jamás en el repo: `.env` en `.gitignore` desde el primer commit de la fase C.
- El proyecto vive en OneDrive (`C:\Users\liber\OneDrive\Desktop\Neurogate`); si la sincronización da problemas con `.git/` o con el venv al crecer el proyecto, proponer al usuario moverlo fuera de OneDrive — no bloquea, pero conviene resolverlo antes de la fase C.
