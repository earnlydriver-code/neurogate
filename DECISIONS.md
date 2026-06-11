# DECISIONS.md — Decisiones de diseño (v1, corrida autónoma Pasos 2–10)

Decisiones tomadas sin consultar, por ser la opción más simple compatible con
`SPEC.md`. Si alguna contradijera el spec o afectara la v2, me habría detenido.

---

## D1 — Python 3.10.6 en lugar de 3.11+
- **Contexto:** el spec pide Python 3.11+, pero la máquina tiene 3.10.6.
- **Decisión:** usar 3.10.6. Todo el código se escribe compatible con 3.10
  (uso de `from __future__ import annotations` para anotaciones modernas como
  `set[X]` y `X | None`).
- **Justificación:** no afecta la lógica ni los contratos; instalar otro Python
  sería fricción innecesaria. La v2 podrá fijar 3.11+ si hace falta.

---
