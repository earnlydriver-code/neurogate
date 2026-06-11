# CLAUDE.md — Reglas de trabajo para NeuroGate

## Qué es este proyecto

NeuroGate es un "antivirus neuronal": una capa de seguridad entre una señal
cerebral y las apps que quieren consumirla — permisos por app, detección de
anomalías, cifrado y log auditable encadenado. La meta final es un middleware
funcional, listo para activarse cuando salgan los BCI de consumo (Neuralink y
similares) y proteger los datos neuronales desde el primer momento.

El proyecto se construye en **dos versiones secuenciales**:

- **v1 (educativa) — `SPEC.md`**: demuestra el concepto completo en un solo
  proceso, con señal simulada. Roadmap de 11 pasos. Es la base y el criterio
  de verdad.
- **v2 (oficial/técnica) — `SPEC-V2.md`**: convierte la v1 en un servicio real
  (BrainFlow para señal, MNE para decoder, FastAPI + JWT para el gateway,
  TLS + firma Ed25519). Roadmap de 5 fases (A–E).

> Prototipo experimental. No es un dispositivo médico. La señal es simulada o
> de datasets públicos anonimizados; no se usan datos de pacientes reales.

## Estado

**Versión actual: v1 — Paso 6 de 11 (crypto_layer) completado.**

(Actualizar esta línea al cerrar cada paso/fase. Formato v2: `v2 — Fase A`.)

## Orden de versiones (regla dura)

- **No se inicia la v2** hasta que la v1 esté completa **hasta el Paso 9**
  (sistema central demostrable por terminal, `tests/attack_sim.py` en verde) y
  **aprobada por el autor**. Los Pasos 10–11 de la v1 (dashboard y despliegue)
  pueden hacerse o posponerse según convenga, pero el salto a v2 exige el
  Paso 9 cerrado y aprobado.
- En la v1 manda `SPEC.md`. En la v2 manda `SPEC-V2.md`; ante conflicto entre
  ambos durante la v2, gana `SPEC-V2.md`. Los contratos entre módulos
  (firmas) definidos en v1 se conservan en v2; cambian las implementaciones.

## Regla de oro: una capa a la vez

- Implementar **solo el paso/fase actual** del roadmap vigente. No adelantar
  módulos ni dependencias futuras, aunque sea "fácil" hacerlo.
- Cada paso/fase termina con: una demo ejecutable, un commit con mensaje
  descriptivo, y mostrar el resultado al autor **para su aprobación antes de
  continuar**.
- Los esqueletos definen los contratos entre módulos. Respetarlos; si un
  contrato debe cambiar, actualizar el spec correspondiente primero.

## Convenciones

- **Idioma**: identificadores (funciones, clases, variables) en **inglés**;
  docstrings, comentarios, README y documentación en **español**.
- **Legibilidad primero**: este código es también material de estudio.
  Claridad antes que cleverness.
- **Comentarios sencillos y cortos**: docstrings de 1-2 líneas, comentarios
  solo donde el código no se explica solo. Nada extenso salvo que el código
  realmente lo necesite.
- Funciones no implementadas: `raise NotImplementedError`, nunca `pass`
  silencioso.
- Stack v1: Python 3.11+, numpy, scipy, scikit-learn, cryptography,
  matplotlib, streamlit, pytest. La v2 añade su propio stack (BrainFlow, MNE,
  FastAPI, etc.; ver `SPEC-V2.md` §7), pero **solo al llegar a cada fase**. No
  añadir dependencias sin acordarlo.

## Comandos

```powershell
# Instalar dependencias (a partir del Paso 2, dentro de un venv)
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Correr las pruebas
pytest

# Dashboard (a partir del Paso 10)
streamlit run neurogate/dashboard.py
```

Cada módulo tendrá además una demo propia ejecutable
(`python -m neurogate.<modulo>`) que se documenta en el README al
implementarse.
