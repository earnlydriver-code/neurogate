"""La vitrina: panel web en vivo con Streamlit.

La cara visible de NeuroGate, pensada para que una persona no técnica
entienda el valor en menos de un minuto. Mostrará:

    - la señal cerebral latiendo en tiempo real,
    - el semáforo de apps (quién tiene acceso a qué),
    - el flujo de cada solicitud atravesando las defensas,
    - el contador de amenazas bloqueadas,
    - y el botón "Simular ataque" que lanza la app maliciosa en vivo.

Se ejecutará con:  streamlit run neurogate/dashboard.py
Se despliega en Streamlit Cloud para obtener la URL pública (Paso 11).
"""

from __future__ import annotations


def main() -> None:
    """Construye y refresca el panel Streamlit sobre el Gateway."""
    # TODO (Paso 10): layout del panel (gráfica de señal, semáforo de apps,
    # feed de solicitudes, contador de bloqueos, botón de ataque) alimentado
    # por Gateway.get_live_state().
    raise NotImplementedError("Se implementa en el Paso 10")


if __name__ == "__main__":
    main()
