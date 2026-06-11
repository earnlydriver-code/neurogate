"""Panel web en vivo (Streamlit): señal, semáforo de apps, bloqueos y botón de ataque.

Se ejecuta con:  streamlit run neurogate/dashboard.py

Muestra el sistema NeuroGate funcionando: la señal cerebral simulada, qué apps
tienen acceso a qué, los contadores de peticiones permitidas/bloqueadas, la
integridad del log de auditoría, y un botón para lanzar un ataque en vivo y ver
cómo las defensas lo frenan.
"""

from __future__ import annotations

import sys
import tempfile
import uuid
from pathlib import Path

import numpy as np
import streamlit as st

# Permite ejecutar `streamlit run neurogate/dashboard.py` desde la raíz del repo.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from neurogate.consent import AccessRequest, DataType  # noqa: E402
from neurogate.gateway import build_demo_gateway  # noqa: E402
from neurogate.signal_source import INTENTS  # noqa: E402
from tests.attack_sim import simulate_attack  # noqa: E402

_STATUS_ICON = {"ok": "🟢", "quarantine": "🟡", "blocked": "🔴"}


def new_session_audit_path() -> Path:
    """Archivo de auditoría único por sesión: nadie pisa el log de otra."""
    return Path(tempfile.gettempdir()) / f"neurogate_audit_{uuid.uuid4().hex}.jsonl"


def _get_gateway(reset: bool = False):
    """Gateway persistente en la sesión (se reconstruye al reiniciar)."""
    if reset or "gateway" not in st.session_state:
        old = st.session_state.get("audit_path")
        if old is not None:
            Path(old).unlink(missing_ok=True)  # limpia solo el archivo propio
        path = new_session_audit_path()
        st.session_state.audit_path = path
        st.session_state.gateway = build_demo_gateway(audit_path=path)
        st.session_state.narration = []
    return st.session_state.gateway


def main() -> None:
    st.set_page_config(page_title="NeuroGate", page_icon="🧠", layout="wide")
    gw = _get_gateway()

    st.title("🧠🛡️ NeuroGate — antivirus neuronal (demo v1)")
    st.caption("Prototipo educativo. Señal cerebral simulada, no es un dispositivo médico.")

    # --- Barra lateral: controles ---
    with st.sidebar:
        st.header("Controles")
        intent = st.selectbox("¿Qué está 'pensando' el cerebro?", INTENTS, index=1)
        gw.signal.set_intent(intent)

        if st.button("➡️ Avanzar señal y decodificar", use_container_width=True):
            gw.tick()

        if st.button("✅ Enviar tráfico legítimo", use_container_width=True):
            gw.tick()
            gw.handle_request(AccessRequest("cursor_app", DataType.INTENT))
            gw.handle_request(AccessRequest("messaging_app", DataType.CONFIRMED_TEXT))

        if st.button("🔴 Simular ataque", type="primary", use_container_width=True):
            st.session_state.narration = simulate_attack(gw)

        if st.button("🔄 Reiniciar demo", use_container_width=True):
            _get_gateway(reset=True)
            st.rerun()

    # Avanza un bloque en cada refresco para que la señal se vea viva.
    gw.tick()
    state = gw.get_live_state()

    # --- Fila 1: señal + intención ---
    col_sig, col_int = st.columns([3, 1])
    with col_sig:
        st.subheader("Señal cerebral en vivo")
        if state["signal"]:
            st.line_chart(np.array(state["signal"]), height=220)
    with col_int:
        st.subheader("Intención")
        st.metric("decodificada ahora", state["latest_intent"])

    # --- Fila 2: contadores ---
    st.subheader("Tráfico y defensas")
    c = state["counters"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Peticiones", c["requests"])
    m2.metric("Permitidas", c["allowed"])
    m3.metric("Bloqueadas 🛡️", c["blocked"])
    m4.metric("Log de auditoría", "ÍNTEGRO ✅" if state["audit_ok"] else "ALTERADO ❌")

    # --- Fila 3: semáforo de apps + narración del ataque ---
    col_apps, col_attack = st.columns(2)
    with col_apps:
        st.subheader("Apps y su estado")
        if state["app_status"]:
            for app_id, status in state["app_status"].items():
                perms = ", ".join(d.value for d in gw.consent.permissions_of(app_id)) or "—"
                label = app_id if len(app_id) < 30 else app_id[:27] + "…"
                st.write(f"{_STATUS_ICON.get(status, '⚪')} **{label}** "
                         f"· permisos: {perms} · {status}")
        else:
            st.write("No hay apps registradas.")
    with col_attack:
        st.subheader("Último ataque simulado")
        if st.session_state.get("narration"):
            for line in st.session_state.narration:
                st.write("• " + line)
        else:
            st.info("Pulsa **Simular ataque** en la barra lateral para verlo en vivo.")


if __name__ == "__main__":
    main()
