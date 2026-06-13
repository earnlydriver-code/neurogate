# Changelog — NeuroGate

Formato basado en [Keep a Changelog](https://keepachangelog.com/es/).
Prototipo experimental; versiones no semánticas todavía.

## [Sin publicar] — extras de producto

- **SDK `neurogate-client`** (`sdk/`): integración de apps cliente en pocas líneas
  (auth + token cacheado, intenciones por WebSocket, datos por REST, admin).
- **`LslSource`**: fuente de señal sobre Lab Streaming Layer (acopla cientos de
  dispositivos EEG research), conmutable por `make_source`.
- **Informe de cumplimiento** (`compliance_report.py`): informe firmado y
  verificable que cruza cada evento con el requisito regulatorio (texto/HTML/JSON).
- **Hardening de seguridad** (revisión): secretos placeholder nunca usados, append
  del log atómico (resistente a concurrencia), anti-replay con poda de nonces,
  `verify_token` devuelve 401 (no 500), toda rama de `serve` auditada.
- Formalización: `LICENSE` (propietaria), `SECURITY.md`, `pyproject.toml`, este changelog.

## v2 — Servicio real (Fases A–E)

- **Fase A — Señal real**: `BrainFlowSource` (hardware-ready) + `DatasetSource`
  (EDF de PhysioNet), conmutables por configuración.
- **Fase B — Decoder real**: motor imagery sobre BCI Competition IV 2a
  (MNE + CSP + LDA); CV media 63.4% (honesta). `train_decoder.py`.
- **Fase C — Gateway como servicio**: FastAPI + JWT/scopes/revocación + 2 apps
  cliente de ejemplo.
- **Fase D — Hardening**: cifrado por app (HKDF + AES-GCM + rotación + anti-replay),
  log firmado Ed25519 + `verify_audit.py`, anomalías sobre telemetría real, TLS,
  suite de 8 ataques bloqueados y auditados.
- **Fase E — Dashboard + despliegue**: dashboard cliente del servicio,
  `Dockerfile`/`docker-compose.yml`, `docs/DEPLOY.md`, `run_demo_e.py`.

## v1 — Prototipo educativo (Pasos 1–11)

- Concepto completo en un proceso con señal simulada: `signal_source`, `decoder`,
  `consent`, `anomaly`, `crypto_layer`, `audit`, `gateway`, dashboard, suite de
  ataques. Demo pública en Streamlit Cloud.
