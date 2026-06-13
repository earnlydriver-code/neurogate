"""Dashboard de la Fase E: un cliente HTTP más del servicio NeuroGate real.

A diferencia del dashboard v1 (``dashboard.py``, en el mismo proceso que el
gateway), este panel **consume el servicio por red**: se autentica con un token
de scope ``admin`` y lee ``GET /admin/state`` periódicamente. Así el dashboard es
un cliente como cualquier otro, y todo lo que muestra son datos reales del
servicio.

Se ejecuta con:
    streamlit run neurogate/dashboard_service.py

URL del servicio configurable por la barra lateral o la variable de entorno
``NEUROGATE_SERVICE_URL`` (por defecto ``http://127.0.0.1:8077``).

La lógica de datos (cliente HTTP + transformaciones) vive en funciones/clases
puras, testeables sin navegador; ``main()`` solo dibuja la interfaz Streamlit.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx

# Permite ejecutar `streamlit run neurogate/dashboard_service.py` desde la raíz.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from neurogate.service import DEMO_CLIENTS  # noqa: E402

DEFAULT_URL = os.environ.get("NEUROGATE_SERVICE_URL", "http://127.0.0.1:8077")

# Credenciales del admin del dashboard (compartidas con run_demo_e.py).
ADMIN_ID = "dashboard_admin"
ADMIN_SECRET = DEMO_CLIENTS[ADMIN_ID][0]

_STATUS_ICON = {"ok": "🟢", "quarantine": "🟡", "blocked": "🔴"}


# --- cliente HTTP del servicio (lógica pura, testeable) ---

class ServiceClient:
    """Cliente HTTP del servicio NeuroGate: autenticación admin + endpoints admin.

    Encapsula el token y todas las llamadas que el dashboard necesita. No depende
    de Streamlit, de modo que se puede testear con un TestClient/servicio real.
    """

    def __init__(self, base_url: str, admin_id: str = ADMIN_ID,
                 admin_secret: str = ADMIN_SECRET, timeout: float = 5.0,
                 http_client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.admin_id = admin_id
        self.admin_secret = admin_secret
        # http_client permite inyectar un TestClient en tests (sin red real); en
        # producción se crea un cliente HTTP normal contra la URL del servicio.
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(base_url=self.base_url,
                                                   timeout=timeout)
        self._token: str | None = None

    def close(self) -> None:
        # Solo cerramos el cliente si lo creamos nosotros (no un TestClient inyectado).
        if self._owns_client:
            self._client.close()

    # --- autenticación ---

    def authenticate(self) -> str:
        """Obtiene (y cachea) un token admin. Lanza httpx.HTTPStatusError si falla."""
        resp = self._client.post("/auth/token", json={
            "client_id": self.admin_id, "client_secret": self.admin_secret})
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        return self._token

    def _auth_headers(self) -> dict:
        if self._token is None:
            self.authenticate()
        return {"Authorization": f"Bearer {self._token}"}

    def _admin_get(self, path: str) -> httpx.Response:
        """GET admin con reintento único si el token caducó (401)."""
        resp = self._client.get(path, headers=self._auth_headers())
        if resp.status_code == 401:
            self.authenticate()
            resp = self._client.get(path, headers=self._auth_headers())
        return resp

    def _admin_post(self, path: str, body: dict) -> httpx.Response:
        resp = self._client.post(path, json=body, headers=self._auth_headers())
        if resp.status_code == 401:
            self.authenticate()
            resp = self._client.post(path, json=body, headers=self._auth_headers())
        return resp

    # --- estado y acciones de operador ---

    def get_state(self) -> dict:
        """Lee el estado en vivo del servicio (GET /admin/state)."""
        resp = self._admin_get("/admin/state")
        resp.raise_for_status()
        return resp.json()

    def revoke(self, jti: str) -> dict:
        return self._admin_post("/admin/revoke", {"jti": jti}).json()

    def release(self, client_id: str) -> dict:
        return self._admin_post("/admin/release", {"client_id": client_id}).json()

    def approve(self, client_id: str, scope: str) -> dict:
        return self._admin_post("/admin/approve",
                                {"client_id": client_id, "scope": scope}).json()

    def deny(self, client_id: str, scope: str) -> dict:
        return self._admin_post("/admin/deny",
                                {"client_id": client_id, "scope": scope}).json()

    # --- token de una app cliente (para lanzar ataques en vivo) ---

    def app_token(self, client_id: str, secret: str,
                  scopes: list[str] | None = None) -> httpx.Response:
        """Pide un token para una app cliente (devuelve la respuesta cruda)."""
        body = {"client_id": client_id, "client_secret": secret}
        if scopes is not None:
            body["scopes"] = scopes
        return self._client.post("/auth/token", json=body)

    def get(self, path: str, token: str) -> httpx.Response:
        return self._client.get(path, headers={"Authorization": f"Bearer {token}"})

    def post(self, path: str, token: str, body: dict) -> httpx.Response:
        return self._client.post(path, json=body,
                                 headers={"Authorization": f"Bearer {token}"})


# --- transformaciones puras del estado (testeables sin Streamlit) ---

def status_icon(status: str) -> str:
    """Icono de semáforo para un estado de app."""
    return _STATUS_ICON.get(status, "⚪")


def summarize_state(state: dict) -> dict:
    """Resume el estado para las tarjetas del dashboard (totales legibles).

    Devuelve un dict plano: intención, contadores, nº de apps por estado, nº de
    bloqueos (amenazas frenadas) y si el log está íntegro.
    """
    counters = state.get("counters", {})
    app_status = state.get("app_status", {})
    by_status = {"ok": 0, "quarantine": 0, "blocked": 0}
    for status in app_status.values():
        by_status[status] = by_status.get(status, 0) + 1
    return {
        "latest_intent": state.get("latest_intent", "idle"),
        "requests": counters.get("requests", 0),
        "allowed": counters.get("allowed", 0),
        "blocked": counters.get("blocked", 0),
        "apps_total": len(app_status),
        "apps_ok": by_status.get("ok", 0),
        "apps_quarantine": by_status.get("quarantine", 0),
        "apps_blocked": by_status.get("blocked", 0),
        "audit_ok": state.get("audit_ok", False),
        "pending_count": len(state.get("pending", [])),
    }


def app_rows(state: dict) -> list[dict]:
    """Filas del semáforo de apps: id, estado, icono y scopes concedidos."""
    app_status = state.get("app_status", {})
    scopes = state.get("scopes", {})
    rows = []
    for app_id, status in sorted(app_status.items()):
        rows.append({
            "app_id": app_id,
            "status": status,
            "icon": status_icon(status),
            "scopes": scopes.get(app_id, []),
        })
    return rows


# --- ataque en vivo contra el servicio real (lógica pura) ---

def run_live_attack(client: ServiceClient) -> dict:
    """Lanza ataques HTTP reales contra el servicio y devuelve el resultado narrado.

    Reproduce, contra el servicio en vivo, los ataques de ``demo_attack.py``:
    escalada de scopes, token forjado, replay de un sobre y un flood que lleva a
    la app atacada a cuarentena. Devuelve los bloqueos para mostrarlos y deja el
    semáforo de la app atacada reflejando la cuarentena.
    """
    import jwt

    lines: list[str] = []
    cur_secret = DEMO_CLIENTS["cursor_app"][0]

    # 1. Escalada de scopes: cursor_app (read:intent) pide confirmed_text -> 403.
    ctok = client.app_token("cursor_app", cur_secret).json()["access_token"]
    esc = client.get("/data/confirmed_text", ctok).status_code
    lines.append(f"Escalada de scopes (read:intent → confirmed_text): {esc} "
                 f"{'BLOQUEADO ✅' if esc == 403 else 'FALLO ❌'}")

    # 2. Token forjado: JWT firmado con otra clave -> 401.
    forged = jwt.encode({"client_id": "cursor_app", "scopes": ["admin"], "jti": "forged",
                         "exp": int(time.time()) + 100}, "CLAVE-FALSA", algorithm="HS256")
    fg = client.get("/admin/state", forged).status_code
    lines.append(f"Token forjado (firma falsa): {fg} "
                 f"{'BLOQUEADO ✅' if fg == 401 else 'FALLO ❌'}")

    # 3. Replay: reader_app captura un sobre y lo reenvía dos veces -> 2º falla.
    rsecret = DEMO_CLIENTS["reader_app"][0]
    rtok = client.app_token("reader_app", rsecret).json()["access_token"]
    sobre = client.get("/data/confirmed_text", rtok).json().get("payload_b64")
    replay_blocked = False
    if sobre:
        client.post("/data/echo", rtok, {"payload_b64": sobre})
        r2 = client.post("/data/echo", rtok, {"payload_b64": sobre})
        replay_blocked = r2.status_code == 403
    lines.append(f"Replay del mismo sobre cifrado: "
                 f"{'BLOQUEADO ✅' if replay_blocked else 'FALLO ❌'}")

    # 4. Flood: messaging_app (con scope read:confirmed_text, así que las peticiones
    # llegan a la etapa de anomalía) martillea el endpoint -> cuarentena por tasa.
    attacked = "messaging_app"
    msecret = DEMO_CLIENTS[attacked][0]
    mtok = client.app_token(attacked, msecret).json()["access_token"]
    flood_n = 30
    blocked = 0
    for _ in range(flood_n):
        r = client.get("/data/confirmed_text", mtok)
        if r.status_code == 403:
            blocked += 1
    lines.append(f"Flood ({attacked}, ráfaga de {flood_n} peticiones): {blocked} frenadas")

    # Estado tras el ataque: ¿quedó la app atacada en cuarentena?
    state = client.get_state()
    final = state.get("app_status", {}).get(attacked, "?")
    quarantined = final == "quarantine"
    lines.append(f"Estado de {attacked} tras el ataque: {status_icon(final)} {final}")

    return {"lines": lines, "attacked": attacked, "quarantined": quarantined,
            "state": state}


# --- render Streamlit (no se testea; solo dibuja) ---

def _get_client(url: str) -> "ServiceClient":
    import streamlit as st

    if st.session_state.get("client_url") != url or "svc_client" not in st.session_state:
        old = st.session_state.get("svc_client")
        if old is not None:
            old.close()
        st.session_state.svc_client = ServiceClient(url)
        st.session_state.client_url = url
    return st.session_state.svc_client


def main() -> None:  # pragma: no cover - render de Streamlit
    import streamlit as st

    st.set_page_config(page_title="NeuroGate · servicio", page_icon="🧠", layout="wide")
    st.title("🧠🛡️ NeuroGate — panel del servicio real (v2, Fase E)")
    st.caption("Prototipo experimental, no es un dispositivo médico. La señal es "
               "simulada / de datasets públicos. Este panel es un cliente más del "
               "servicio: se autentica y lee el estado por red.")

    with st.sidebar:
        st.header("Conexión")
        url = st.text_input("URL del servicio", value=DEFAULT_URL)
        auto = st.checkbox("Auto-refrescar (2 s)", value=True)
        st.divider()
        st.header("Acciones")
        do_attack = st.button("🔴 Simular ataque", type="primary",
                              use_container_width=True)

    client = _get_client(url)

    # Conexión con el servicio: si falla, lo decimos con claridad.
    try:
        if do_attack:
            st.session_state.attack = run_live_attack(client)
        state = client.get_state()
    except (httpx.HTTPError, httpx.HTTPStatusError) as e:
        st.error(f"No se puede contactar el servicio en {url}. "
                 f"Arráncalo con `python run_demo_e.py`. Detalle: {e}")
        st.stop()

    summary = summarize_state(state)

    # --- Fila 1: intención + integridad del log ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Intención decodificada", summary["latest_intent"])
    c2.metric("Peticiones", summary["requests"])
    c3.metric("Amenazas bloqueadas 🛡️", summary["blocked"])
    c4.metric("Permitidas", summary["allowed"])

    # --- Verificación de integridad del log con un clic ---
    st.subheader("Integridad del log auditado")
    colv1, colv2 = st.columns([1, 3])
    with colv1:
        check = st.button("🔎 Verificar log", use_container_width=True)
    with colv2:
        if check or auto:
            if summary["audit_ok"]:
                st.success("Log de auditoría ÍNTEGRO ✅ — la cadena firmada (Ed25519) "
                           "es válida.")
            else:
                st.error("Log ALTERADO ❌ — la verificación de la cadena falló.")

    # --- Semáforo de apps ---
    st.subheader("Apps y su estado (semáforo)")
    rows = app_rows(state)
    if rows:
        for row in rows:
            scopes = ", ".join(row["scopes"]) or "—"
            cols = st.columns([1, 4])
            cols[0].write(f"{row['icon']} **{row['status']}**")
            cols[1].write(f"**{row['app_id']}** · scopes: {scopes}")
            if row["status"] == "quarantine":
                if cols[1].button(f"Liberar {row['app_id']}", key=f"rel_{row['app_id']}"):
                    client.release(row["app_id"])
                    st.rerun()
    else:
        st.info("No hay apps registradas todavía.")

    # --- Panel de modo confirmación ---
    st.subheader("Modo confirmación — entregas pendientes")
    pending = state.get("pending", [])
    if pending:
        for p in pending:
            cols = st.columns([3, 1, 1])
            cols[0].write(f"**{p['client_id']}** pide `{p['scope']}` — {p['reason']}")
            if cols[1].button("Aprobar", key=f"ap_{p['client_id']}_{p['scope']}"):
                client.approve(p["client_id"], p["scope"])
                st.rerun()
            if cols[2].button("Denegar", key=f"dn_{p['client_id']}_{p['scope']}"):
                client.deny(p["client_id"], p["scope"])
                st.rerun()
    else:
        st.info("No hay entregas pendientes de confirmación. Los scopes sensibles "
                "(p. ej. señal cruda) aparecerían aquí para aprobar/denegar.")

    # --- Resultado del último ataque ---
    st.subheader("Último ataque simulado")
    attack = st.session_state.get("attack")
    if attack:
        for line in attack["lines"]:
            st.write("• " + line)
        if attack["quarantined"]:
            st.warning(f"La app atacada ({attack['attacked']}) quedó en CUARENTENA 🟡 "
                       "— el semáforo de arriba lo refleja.")
    else:
        st.info("Pulsa **Simular ataque** en la barra lateral para lanzar ataques "
                "reales contra el servicio y ver cómo los frena.")

    # Auto-refresco: vuelve a dibujar tras 2 s leyendo de nuevo el estado.
    if auto and not do_attack:
        time.sleep(2)
        st.rerun()


if __name__ == "__main__":
    main()
