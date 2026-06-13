# Política de seguridad — NeuroGate

NeuroGate es una capa de seguridad y cumplimiento para datos neuronales. La
seguridad es el producto, así que la tratamos en serio y con honestidad sobre su
estado.

## Reportar una vulnerabilidad

Por favor **no abras un issue público** para vulnerabilidades. Escribe a
`security@TU-DOMINIO` (sustituye por el contacto real antes de publicar) con:

- descripción y pasos de reproducción,
- impacto estimado,
- versión / commit afectado.

Objetivo de primera respuesta: 72 horas. Divulgación coordinada: acordamos una
fecha tras disponer de un arreglo.

## Postura de seguridad (lo que YA hace)

- **Autenticación**: JWT por cliente con scopes, expiración (`exp`), id de token
  (`jti`) y **lista de revocación** consultada en cada request (corte inmediato).
- **Autorización mínima**: cada app recibe solo el scope autorizado; el scope de
  señal cruda (`read:raw_signal`) está cerrado salvo modo clínico explícito.
- **Cifrado por app**: clave derivada con HKDF (master key + `client_id` +
  versión) y AES-256-GCM (AEAD); **rotación versionada** y **anti-replay** por
  nonce + ventana temporal (con poda).
- **Auditoría verificable por terceros**: log JSONL encadenado (SHA-256) y
  **firmado por entrada (Ed25519)**; `verify_audit.py` valida integridad y
  autenticidad solo con la clave pública. El append es atómico (resistente a
  concurrencia). Toda decisión (allow/deny/quarantine/approve) queda registrada.
- **Detección de abuso**: Isolation Forest sobre telemetría real con ventana
  deslizante; flood o scope nunca usado → cuarentena automática y auditada.
- **Transporte**: el servicio puede servir HTTPS/WSS (TLS); cert de desarrollo en
  `scripts/gen_cert.py`.
- **Secretos fuera del código**: por entorno (`.env`, ver `.env.example`). Si se
  arranca con el secreto placeholder del repo, se sustituye por uno aleatorio
  efímero para no firmar/derivar nunca con un secreto público.
- **Suite de 8 ataques** automatizada (`pytest`) + demo en vivo (`demo_attack.py`).

## Lo que NO está hecho todavía (honestidad para el comprador)

- **No es un dispositivo médico** ni software clínico (uso educativo/experimental;
  señal simulada o de datasets públicos anonimizados).
- **Gestión de claves de producción (KMS)**: la master key va por entorno; falta
  integración con KMS/Vault para un despliegue serio.
- **Multi-tenant**: el estado es de un solo proceso; aislar log/claves por tenant
  está pendiente.
- **Auditoría de seguridad externa (pentest)**: la suite de ataques es propia; aún
  no hay revisión de un tercero independiente.
- **Validación con hardware físico** y **benchmark de latencia/escala** pendientes.
- JWT sin validación de `aud`/`iss` (suficiente para un gateway único; revisar para
  despliegues multi-servicio).

## Alcance

Aplica al código de este repositorio (gateway, módulos `neurogate/`, SDK `sdk/`,
herramientas `verify_audit.py` / `compliance_report.py`). No cubre despliegues de
terceros ni configuraciones que ignoren `.env.example`.
