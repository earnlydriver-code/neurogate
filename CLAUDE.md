# CLAUDE.md — Reglas de trabajo para NeuroGate

## Qué es este proyecto

NeuroGate es un prototipo educativo en Python: una capa de seguridad
("antivirus neuronal") entre una señal cerebral simulada y las apps que
quieren consumirla — permisos por app, detección de anomalías, cifrado AES y
log auditable encadenado. **La fuente de verdad es `SPEC.md`**: visión,
arquitectura, contratos entre módulos y el roadmap de 11 pasos.

> Prototipo de simulación educativa. No es un dispositivo médico. No hay hardware.

## Estado

**Paso actual: 1 de 11 (cimientos) — completado, pendiente de aprobación para el Paso 2.**

(Actualizar esta línea al completar cada paso.)

## Regla de oro: una capa a la vez

- Implementar **solo el paso actual** del roadmap de `SPEC.md`. No adelantar
  módulos futuros, aunque sea "fácil" hacerlo.
- Cada paso termina con: una demo ejecutable, un commit con mensaje
  descriptivo, y mostrar el resultado al autor **para su aprobación antes de
  pasar al siguiente paso**.
- Los esqueletos definen los contratos entre módulos (firmas en `SPEC.md`
  sección 4). Respetarlos; si un contrato debe cambiar, actualizar `SPEC.md`
  primero.

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
- Stack fijo: Python 3.11+, numpy, scipy, scikit-learn, cryptography,
  matplotlib, streamlit, pytest. No añadir dependencias sin acordarlo.

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
