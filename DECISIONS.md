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

## D2 — Detector de anomalías híbrido (iForest + regla de novedad)
- **Contexto:** el spec pide Isolation Forest detectando, entre otras cosas,
  "leer algo que nunca antes pidió". Un Isolation Forest no puede aislar un
  feature que fue constante en entrenamiento (la columna de un tipo nunca visto
  es siempre 0 → no hay split posible), así que por sí solo no detecta tipos
  nuevos.
- **Decisión:** híbrido. El Isolation Forest vigila las features continuas
  (intervalo entre accesos y franja horaria); una regla de novedad por conjunto
  marca como anómalo cualquier tipo de dato que esa app nunca pidió en
  entrenamiento.
- **Justificación:** cumple el comportamiento que pide el spec (ráfagas y tipos
  nunca pedidos disparan alerta) de forma robusta y honesta. El Isolation Forest
  sigue siendo el núcleo, como pide el spec. No afecta contratos ni la v2 (la
  v2 enriquece las features de telemetría, pero la idea híbrida se conserva).

---
