---
layout: post
title: "Así nace NeuroGate: un antivirus para el cerebro"
date: 2026-06-10
description: "Qué es NeuroGate, por qué lo construyo, y cómo quedó la primera versión funcionando — con demo en vivo para que la rompas tú mismo."
---

Los implantes y diademas que leen señales del cerebro están dejando de ser
ciencia ficción: Neuralink ya implanta en humanos y hay diademas EEG de
consumo por menos de lo que cuesta un teléfono. Pero hay una pregunta que casi
nadie está construyendo: cuando una app pueda leer tu cerebro, **¿quién decide
qué sale de ahí, hacia quién, y quién deja constancia de cada acceso?**
NeuroGate es mi intento de respuesta: la capa de seguridad que se sienta entre
la señal cerebral y las apps que quieren consumirla.

> 🔴 **[Prueba la demo en vivo](https://neurogate.streamlit.app/)** — pulsa
> "Simular ataque" y mira cómo se bloquea en tiempo real. El código completo
> está en [GitHub](https://github.com/earnlydriver-code/neurogate).

## El problema

Tus datos neuronales son los datos más íntimos que existen: no es lo que
escribiste, es lo que *ibas a hacer antes de hacerlo*. Cuando los BCI de
consumo despeguen, las apps van a pedir esa señal igual que hoy piden tu
ubicación o tu micrófono. Y hoy no existe el equivalente a "permisos de
Android" para el cerebro: ni permisos granulares, ni detección de abuso, ni
un registro de accesos que nadie pueda borrar. La regulación ya empezó a
moverse (Chile 2021, Colorado y California 2024), pero el software que haría
cumplir esas reglas no está. Ese hueco es NeuroGate.

## Qué construí

Una primera versión completa y funcional, en simulación: un "guardia de
seguridad" por el que pasa toda solicitud de datos neuronales. Cada app
recibe **solo el tipo de dato que tiene autorizado**, un detector de
anomalías vigila su comportamiento, todo lo que sale viaja cifrado, y cada
decisión queda escrita en un registro encadenado imposible de alterar en
silencio.

![Dashboard de NeuroGate]({{ '/assets/img/dashboard.png' | relative_url }})

Eso de la imagen es el panel en vivo: la señal cerebral simulada latiendo,
la intención decodificada, los contadores de peticiones permitidas y
bloqueadas, el semáforo de apps y el resultado del último ataque simulado.
No es un mockup — [puedes usarlo ahora mismo](https://neurogate.streamlit.app/).

## Cómo funciona por dentro

El sistema es un bucle que corre muchas veces por segundo, con cuatro
defensas en fila:

1. **Señal** — un cerebro simulado genera ondas tipo EEG (cada "intención"
   tiene una firma de frecuencias distinta, como en un EEG real).
2. **Decoder** — un clasificador de machine learning traduce la electricidad
   en significado: *mover el cursor*, *escribir*, o *nada*.
3. **Consentimiento** — ¿esta app tiene permiso para este tipo de dato? Una
   app de mensajes puede recibir texto confirmado; la señal cruda del
   cerebro, jamás. Los datos sensibles exigen además aprobación explícita.
4. **Anomalías** — aunque el permiso exista, un Isolation Forest vigila el
   comportamiento: una ráfaga de peticiones a ritmo de máquina manda la app
   a cuarentena.
5. **Cifrado** — lo que sale va cifrado con AES, con una clave distinta por
   app: interceptar el tráfico de una no sirve para leer el de otra.
6. **Auditoría** — cada decisión (permitida o bloqueada, y por qué) se escribe
   en un log donde cada entrada lleva el hash SHA-256 de la anterior. Alterar
   o borrar una línea rompe la cadena y se detecta al instante.

Todo en Python legible (scikit-learn, cryptography, Streamlit), pensado
también como material de estudio. Hay 34 tests automatizados cubriendo cada
capa.

## El ataque (y el bloqueo)

La parte divertida. En el panel hay un botón rojo que lanza una app maliciosa
real contra el sistema, con tres jugadas clásicas:

- **Robo de señal cruda**: se registra con permisos mínimos y pide la señal
  del cerebro directamente → bloqueada por el filtro de consentimiento, con
  el motivo escrito en el log.
- **Ráfaga**: pide datos 20 veces en menos de un segundo → el detector de
  anomalías la manda a cuarentena, y en cuarentena no recibe ni lo que tiene
  permitido.
- **Falsificar el registro**: intenta inyectar una entrada falsa en el log de
  auditoría para borrar su rastro → la cadena de hashes la delata.

Los tres ataques también corren como tests (`pytest`) en cada cambio del
código: si alguna defensa se rompe, me entero antes que el atacante.

## Qué sigue

Esta v1 demuestra el concepto completo con señal simulada. La v2 — ya
especificada en el repo — lo convierte en un servicio real: señal vía
BrainFlow (compatible con hardware EEG físico), decoder entrenado con
datasets públicos de EEG reales, gateway por red con tokens y scopes, y log
firmado verificable por terceros. La meta: que cuando los BCI de consumo
lleguen, esta capa exista y esté lista desde el día uno.

Si te interesa el tema — o crees que puedes romper la demo — el
[código está abierto](https://github.com/earnlydriver-code/neurogate) y este
blog irá documentando cada capa.

---

*NeuroGate es un prototipo educativo en simulación; no es un dispositivo
médico y la señal no proviene de ninguna persona. Lo construyo porque creo
que la tecnología que toca mentes debe nacer con la protección puesta, no
ponérsela después.*
