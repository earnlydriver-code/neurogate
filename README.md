# NeuroGate 🧠🛡️

[![CI](https://github.com/earnlydriver-code/neurogate/actions/workflows/ci.yml/badge.svg)](https://github.com/earnlydriver-code/neurogate/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)

**Un "antivirus neuronal": la capa de seguridad entre un cerebro y las apps
que quieren leerlo.**

🔴 **Demo en vivo:** [neurogate.streamlit.app](https://neurogate.streamlit.app/) — pulsa "Simular ataque"
📝 **Bitácora del proceso:** [earnlydriver-code.github.io/neurogate](https://earnlydriver-code.github.io/neurogate/)

NeuroGate es un prototipo educativo en Python que demuestra cómo proteger
datos neuronales. Se sienta entre una señal cerebral **simulada** (tipo EEG) y
las aplicaciones que quieren consumirla, y decide en tiempo real qué
información puede salir y hacia quién — bloqueando y registrando todo lo
sospechoso.

> ⚠️ **Disclaimer**: esto es un prototipo de **simulación educativa**, no un
> dispositivo médico. No hay hardware: la señal cerebral es sintética
> (generada por software) o proviene de datasets públicos de EEG.

## Cómo funciona

```
Cerebro simulado ──señal──▶ Decoder ──intención──▶ ┌─────────────────────┐
                                                   │       GATEWAY       │
App cliente ──── solicitud de datos ────────────▶  │ 1. Consent  ¿permiso?│
             ◀── dato cifrado o RECHAZO ────────   │ 2. Anomaly  ¿normal? │
                                                   │ 3. Crypto   cifrar   │
                                                   │ 4. Audit    registrar│
                                                   └──────────┬──────────┘
                                                        Dashboard en vivo
```

Cada solicitud de una app pasa por cuatro defensas:

1. **Consentimiento** (`consent.py`) — cada app solo recibe el tipo de dato
   que tiene autorizado. Señal cruda del cerebro: casi nunca.
2. **Detección de anomalías** (`anomaly.py`) — un Isolation Forest vigila el
   comportamiento; un patrón de acceso raro dispara alerta aunque el permiso
   exista.
3. **Cifrado** (`crypto_layer.py`) — todo lo que sale va cifrado con AES, con
   clave propia por app.
4. **Auditoría** (`audit.py`) — cada evento queda en un log encadenado con
   hashes, imposible de alterar silenciosamente.

La señal nace en `signal_source.py` (cerebro simulado), se interpreta en
`decoder.py` (intenciones: mover cursor, escribir, nada), y `gateway.py` une
todo el flujo. `dashboard.py` lo muestra en vivo, con un botón de **"simular
ataque"** para ver las defensas en acción. `tests/attack_sim.py` es la app
maliciosa que intenta robar datos para probar que todo funciona.

## Estructura del proyecto

```
neurogate/
├── signal_source.py   # Cerebro simulado: genera señal tipo EEG en bloques
├── decoder.py         # Traduce señal a intenciones (ML, scikit-learn)
├── consent.py         # Filtro de permisos por app y tipo de dato
├── anomaly.py         # Detector de accesos anómalos (Isolation Forest)
├── crypto_layer.py    # Cifrado AES de los datos que salen
├── audit.py           # Log auditable encadenado con hashes
├── gateway.py         # Orquesta el flujo completo
└── dashboard.py       # Panel web en vivo (Streamlit)
tests/
└── attack_sim.py      # App maliciosa para probar las defensas
```

La visión completa, los contratos entre módulos y el roadmap están en
[`SPEC.md`](SPEC.md).

## Dos versiones

El proyecto se construye en dos etapas secuenciales:

- **v1 — educativa** ([`SPEC.md`](SPEC.md)): demuestra el concepto completo en
  un solo proceso, con señal simulada. Roadmap de 11 pasos. Es la base.
- **v2 — oficial/técnica** ([`SPEC-V2.md`](SPEC-V2.md)): convierte la v1 en un
  servicio real (BrainFlow, MNE, FastAPI + JWT, TLS, log firmado), agnóstico
  al fabricante del dispositivo y listo para hardware BCI real. Roadmap de 5
  fases. **Solo arranca cuando la v1 está completa hasta el Paso 9 y aprobada.**

La meta final: un middleware funcional, listo para activarse cuando salgan los
BCI de consumo (Neuralink y similares) y proteger los datos neuronales desde el
primer momento.

## Estado actual

**v1 COMPLETA — 11 de 11 pasos.** Los ocho módulos implementados, demo pública
en [neurogate.streamlit.app](https://neurogate.streamlit.app/) y bitácora del
proceso en el [blog](https://earnlydriver-code.github.io/neurogate/).

**v2 en curso** (servicio real; ver `SPEC-V2.md`):

- **Fase A — Señal real:** `signal_source.py` sobre BrainFlow (placa sintética,
  hardware-ready) + `DatasetSource` (dataset público local) + `LslSource`
  (**Lab Streaming Layer**, el estándar research: acopla cientos de dispositivos
  EEG sin tocar el resto), conmutables por configuración (`make_source`).
- **Fase B — Decoder real:** decodificador de *motor imagery* entrenado offline
  sobre **BCI Competition IV 2a** (9 sujetos, 22 canales EEG, 4 clases:
  mano izquierda / mano derecha / pies / lengua). Pipeline **MNE (filtro
  8–30 Hz) → CSP → LDA**. Convive al lado del decoder v1, sin romperlo.
- **Fase C — Gateway como servicio:** FastAPI con JWT, scopes y revocación en
  caliente; dos apps cliente de ejemplo (`examples/`) que se conectan por red.
- **Fase D — Hardening:** cifrado por app (HKDF + AESGCM + rotación + anti-replay),
  log firmado Ed25519 (`verify_audit.py`), anomalías sobre telemetría real y suite
  de 8 ataques en `pytest` + demo en vivo (`demo_attack.py`).
- **Fase E — Demo de inversión:** dashboard que es **un cliente más del servicio**
  (`neurogate/dashboard_service.py`): se autentica y lee `GET /admin/state` por
  red. Material de despliegue (`Dockerfile`, `docker-compose.yml`, `docs/DEPLOY.md`)
  y arranque local con `run_demo_e.py`.

### Demo de la Fase E (servicio real + dashboard)

```powershell
# Terminal 1 — gateway con los clientes de demo registrados
python run_demo_e.py                       # http://127.0.0.1:8077

# Terminal 2 — dashboard apuntando al gateway (cliente admin por red)
streamlit run neurogate/dashboard_service.py
```

El despliegue (Docker, TLS, Streamlit Cloud) y el guion de demo de 1 minuto están
en [`docs/DEPLOY.md`](docs/DEPLOY.md).

### SDK de cliente y informe de cumplimiento

- **SDK `neurogate-client`** (`sdk/`): integra una app con el gateway en tres
  líneas (`pip install ./sdk`). Pide token y consume scopes (intenciones por
  WebSocket, texto por REST); incluye helpers de administración.
- **Informe de cumplimiento** (`compliance_report.py`): a partir del log firmado
  emite un informe verificable (texto/HTML/JSON) que cruza cada decisión con el
  requisito regulatorio que evidencia. Es la prueba auditable de consentimiento
  que un comité de ética o un regulador exige.

```powershell
python compliance_report.py audit_service.jsonl keys/audit_ed25519_public.pem --html informe.html
```

### Accuracy del decoder real (Fase B, honesta)

Validación cruzada k-fold (k=5) sobre la sesión de entreno de cada sujeto, y
evaluación held-out entrenando en la sesión T y probando en la sesión E:

| Métrica | Resultado (9 sujetos) |
|---|---|
| CV k-fold (media) | **63.4% ± 14.6%** |
| Held-out T→E (media) | **61.5% ± 13.7%** |
| Mejores sujetos (A03, A08) | ~80% |
| Peor sujeto (A05) | ~38% |

Azar = 25% (4 clases). En *motor imagery* de 4 clases, 60–80% por sujeto es lo
normal; la variabilidad entre sujetos es esperada y está documentada sin inflar.

**Regenerar el modelo** (no se versiona; pesa poco y se reproduce):

```powershell
python train_decoder.py            # valida los 9 sujetos + entrena y serializa
python train_decoder.py --demo     # reproduce la sesión E de un sujeto en vivo
```

El modelo se guarda en `models/mi_decoder.joblib` (ignorado por git). En runtime
lo carga `neurogate/mi_decoder.py`. Camino de carga del dataset: lectura directa
de los `.mat` con `scipy.io.loadmat` (offline, copia local).

## Cómo ejecutarlo

```powershell
# 1. Instalar dependencias
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Demo completa por terminal (flujo end-to-end)
python -m neurogate.gateway

# 3. Probar las defensas contra la app maliciosa
pytest

# 4. Panel visual (o usa la demo pública)
streamlit run neurogate/dashboard.py
```

Cada módulo tiene además su demo propia: `python -m neurogate.<modulo>`.
