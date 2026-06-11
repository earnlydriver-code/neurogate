# NeuroGate 🧠🛡️

**Un "antivirus neuronal": la capa de seguridad entre un cerebro y las apps
que quieren leerlo.**

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

**v1 — Paso 1 de 11 (cimientos).** La estructura y los esqueletos existen; la
lógica se construye una capa a la vez (ver roadmap en `SPEC.md`).

## Cómo se ejecutará (cuando esté listo)

```powershell
# 1. Instalar dependencias
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Correr la demo completa por terminal (a partir del Paso 8)
python -m neurogate.gateway

# 3. Probar las defensas contra la app maliciosa (a partir del Paso 9)
pytest

# 4. Abrir el panel visual (a partir del Paso 10)
streamlit run neurogate/dashboard.py
```
