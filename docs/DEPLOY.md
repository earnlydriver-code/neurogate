---
layout: default
title: Despliegue (Fase E)
---

# Despliegue de NeuroGate v2 (Fase E)

> Prototipo experimental, no es un dispositivo médico. La señal es simulada o de
> datasets públicos anonimizados.

NeuroGate v2 se despliega en dos piezas que hablan **por red**:

1. **Gateway** (`neurogate/service.py`): servicio FastAPI con JWT, scopes,
   cifrado por app, log firmado y detección de anomalías. Es el único punto de
   acceso a los datos neuronales.
2. **Dashboard** (`neurogate/dashboard_service.py`): panel Streamlit que es **un
   cliente admin más** del gateway. Se autentica con `POST /auth/token` y lee
   `GET /admin/state` periódicamente. No comparte proceso con el gateway.

```
┌────────────────────┐      HTTP(S) + token admin     ┌────────────────────┐
│  Dashboard          │ ─────────────────────────────▶ │  Gateway (FastAPI) │
│  Streamlit Cloud    │   GET /admin/state, acciones    │  VPS / contenedor  │
│  dashboard_service  │ ◀───────────────────────────── │  service.py        │
└────────────────────┘        estado en vivo           └────────────────────┘
```

---

## 1. Demo en local (servicio + dashboard juntos)

Lo más rápido. Dos terminales, mismo equipo:

```powershell
# Terminal 1 — gateway con los clientes de demo registrados
python run_demo_e.py                      # http://127.0.0.1:8077

# Terminal 2 — dashboard apuntando al gateway
streamlit run neurogate/dashboard_service.py
```

El dashboard usa por defecto `http://127.0.0.1:8077` (configurable en la barra
lateral o con la variable de entorno `NEUROGATE_SERVICE_URL`). Abre el navegador
en la URL que imprime Streamlit (normalmente `http://localhost:8501`).

---

## 2. Gateway containerizado (Docker)

```powershell
# Copia las variables de entorno y rellénalas (secretos largos y aleatorios)
copy .env.example .env

# Opción A: docker compose (recomendado)
docker compose up --build                 # gateway en http://localhost:8077

# Opción B: docker a pelo
docker build -t neurogate-gateway .
docker run -p 8077:8077 --env-file .env neurogate-gateway
```

Variables de entorno (todas con prefijo `NEUROGATE_`, ver `.env.example`):

| Variable | Para qué |
|---|---|
| `NEUROGATE_JWT_SECRET` | Firma de los JWT (HS256). Largo y aleatorio (>=32 bytes). |
| `NEUROGATE_MASTER_KEY` | Master key del cifrado por app (HKDF). En producción, KMS. |
| `NEUROGATE_TOKEN_EXPIRE_MINUTES` | Validez de cada token. |
| `NEUROGATE_CLINICAL_MODE` | Habilita el scope sensible `read:raw_signal`. |
| `NEUROGATE_REPLAY_WINDOW_SECONDS` | Ventana anti-replay de los sobres cifrados. |
| `NEUROGATE_KEY_ROTATION_EVERY` | Cada cuántos requests rotar las claves (0 = no). |
| `NEUROGATE_ANOMALY_*` | Baseline, factor de pico y ventana de la detección de anomalías. |
| `NEUROGATE_AUDIT_PRIVATE_KEY_PATH` / `_PUBLIC_KEY_PATH` | Claves Ed25519 del log firmado. La privada va por archivo ignorado/KMS; la pública se publica. |
| `NEUROGATE_TLS_CERTFILE` / `_KEYFILE` | Cert y clave TLS para servir HTTPS/WSS. |

**Secretos:** nunca dentro de la imagen ni en el repo. Se inyectan por `.env`
(ignorado) o por el gestor de secretos del proveedor.

---

## 3. TLS (HTTPS/WSS)

Para desarrollo, genera un certificado autofirmado y arranca uvicorn con él:

```powershell
python scripts/gen_cert.py                # crea certs/dev_cert.pem y certs/dev_key.pem
uvicorn neurogate.service:app --host 0.0.0.0 --port 8077 `
        --ssl-certfile certs/dev_cert.pem --ssl-keyfile certs/dev_key.pem
```

En producción, usa un certificado real (Let's Encrypt) o termina el TLS en un
proxy inverso (Caddy/Nginx/Traefik) delante del gateway. El dashboard apuntaría
entonces a `https://tu-dominio` y los WebSockets a `wss://`.

---

## 4. Dashboard en Streamlit Cloud

> No desplegamos de verdad aquí (no hay credenciales): este es el material y los
> pasos.

1. El gateway debe estar accesible públicamente (VPS o contenedor con IP/dominio
   público y, idealmente, TLS). Anota su URL, p. ej. `https://gateway.tu-dominio`.
2. En [share.streamlit.io](https://share.streamlit.io) conecta el repo de GitHub
   y elige como entrypoint `neurogate/dashboard_service.py`.
3. En **Settings → Secrets / Environment** del despliegue, define:
   ```
   NEUROGATE_SERVICE_URL = "https://gateway.tu-dominio"
   ```
   El dashboard lee esa variable como URL por defecto del servicio.
4. El admin del dashboard usa las credenciales `dashboard_admin` (ver
   `DEMO_CLIENTS` en `neurogate/service.py`). En un despliegue real, esas
   credenciales saldrían de secretos del entorno, no del código.

El dashboard v1 (`neurogate/dashboard.py`, en-proceso) sigue siendo el de la demo
pública actual en [neurogate.streamlit.app](https://neurogate.streamlit.app). El
de la Fase E es el **cliente del servicio real**: requiere un gateway accesible.

---

## 5. Verificar el log auditado (tercero externo)

Cualquiera puede verificar la integridad del log firmado con solo la clave pública:

```powershell
python verify_audit.py audit_service.jsonl keys/audit_ed25519_public.pem
```

Devuelve ÍNTEGRO (cadena + firmas Ed25519 válidas) o ALTERADO con la primera
línea corrupta. El dashboard expone esta verificación con un clic ("Verificar
log").

---

## 6. Guion de demo de 1 minuto

Objetivo: que alguien no técnico entienda el valor de NeuroGate en menos de un
minuto.

1. **(0:00) Contexto.** "Esto se sienta entre un cerebro y las apps que quieren
   leerlo. Decide qué dato sale y hacia quién." Señala la intención decodificada
   en vivo y el semáforo de apps (todas 🟢).
2. **(0:15) Permisos.** "Cada app solo recibe lo que tiene autorizado: la app de
   cursor ve intenciones, la de mensajería solo texto confirmado." Señala los
   scopes de cada app.
3. **(0:30) Ataque.** Pulsa **Simular ataque**. Aparecen los bloqueos: escalada
   de scopes, token falso, replay, y un flood. La app atacada pasa a
   **cuarentena 🟡** en el semáforo, en vivo.
4. **(0:45) Pruebas.** "Todo queda registrado en un log firmado que un tercero
   puede verificar." Pulsa **Verificar log** → ÍNTEGRO ✅. El contador de
   "amenazas bloqueadas" ha subido.
5. **(0:55) Cierre.** "Cuando salgan los BCI de consumo, esta es la capa que
   convierte cumplir la regulación en instalar un middleware en vez de
   construirlo todo desde cero."
