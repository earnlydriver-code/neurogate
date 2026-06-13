"""Cliente HTTP/WebSocket del gateway NeuroGate.

Tres líneas para integrar una app cliente:

    from neurogate_client import NeuroGateClient

    client = NeuroGateClient("http://127.0.0.1:8077", "cursor_app", "secret")
    for msg in client.stream_intents(max_messages=10):
        print(msg["intent"])

El cliente gestiona el token (lo pide y lo cachea), reintenta una vez si caduca, y
expone los endpoints del gateway. La señal viaja cifrada por la red; descifrarla
requiere la clave de la app (entrega de claves fuera del alcance de este SDK).
"""

from __future__ import annotations

import json
from typing import Iterator

import httpx


class NeuroGateError(Exception):
    """Error devuelto por el gateway (con su código HTTP)."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class NeuroGateClient:
    """Cliente del gateway NeuroGate: autenticación por credenciales + endpoints."""

    def __init__(self, base_url: str, client_id: str, client_secret: str, *,
                 timeout: float = 10.0, http_client: "httpx.Client | None" = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        # http_client inyectable (p. ej. un TestClient) para pruebas sin red.
        self._owns_client = http_client is None
        self._http = http_client or httpx.Client(base_url=self.base_url, timeout=timeout)
        self._token: str | None = None

    # --- autenticación ---

    def authenticate(self, scopes: list[str] | None = None) -> str:
        """Pide (y cachea) un token. ``scopes`` opcional: subconjunto de los concedidos."""
        body = {"client_id": self.client_id, "client_secret": self.client_secret}
        if scopes is not None:
            body["scopes"] = scopes
        resp = self._http.post("/auth/token", json=body)
        if resp.status_code != 200:
            raise NeuroGateError(resp.status_code, _detail(resp))
        self._token = resp.json()["access_token"]
        return self._token

    @property
    def token(self) -> str:
        """Token actual; lo pide si aún no hay."""
        if self._token is None:
            self.authenticate()
        return self._token  # type: ignore[return-value]

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def _get(self, path: str) -> httpx.Response:
        """GET con reintento único si el token caducó (401)."""
        resp = self._http.get(path, headers=self._auth_headers())
        if resp.status_code == 401:
            self.authenticate()
            resp = self._http.get(path, headers=self._auth_headers())
        return resp

    def _post(self, path: str, body: dict) -> httpx.Response:
        resp = self._http.post(path, json=body, headers=self._auth_headers())
        if resp.status_code == 401:
            self.authenticate()
            resp = self._http.post(path, json=body, headers=self._auth_headers())
        return resp

    # --- datos (scopes de app) ---

    def get_confirmed_text(self) -> dict:
        """Pide el texto confirmado (requiere scope read:confirmed_text)."""
        return _json_or_raise(self._get("/data/confirmed_text"))

    def echo(self, payload_b64: str) -> dict:
        """Reenvía un sobre cifrado para descifrarlo (demuestra el anti-replay)."""
        return _json_or_raise(self._post("/data/echo", {"payload_b64": payload_b64}))

    def stream_intents(self, max_messages: int | None = None) -> Iterator[dict]:
        """Itera las intenciones decodificadas por WebSocket (requiere read:intent).

        Cada mensaje es un dict con ``intent`` y ``payload_b64`` (cifrado). Si el
        gateway corta el stream (token revocado, scope insuficiente), lanza
        NeuroGateError.
        """
        from websockets.sync.client import connect

        ws_url = self._ws_base() + f"/stream/intents?token={self.token}"
        with connect(ws_url) as ws:
            count = 0
            while max_messages is None or count < max_messages:
                data = json.loads(ws.recv())
                if "error" in data:
                    raise NeuroGateError(403, data["error"])
                yield data
                count += 1

    # --- administración (scope admin) ---

    def get_state(self) -> dict:
        """Estado en vivo del servicio (requiere scope admin)."""
        return _json_or_raise(self._get("/admin/state"))

    def revoke(self, jti: str) -> dict:
        """Revoca un token por su jti (requiere admin)."""
        return _json_or_raise(self._post("/admin/revoke", {"jti": jti}))

    def release(self, client_id: str) -> dict:
        """Saca una app de cuarentena (requiere admin)."""
        return _json_or_raise(self._post("/admin/release", {"client_id": client_id}))

    def approve(self, client_id: str, scope: str) -> dict:
        """Aprueba una entrega pendiente de confirmación (requiere admin)."""
        return _json_or_raise(self._post("/admin/approve",
                                         {"client_id": client_id, "scope": scope}))

    def deny(self, client_id: str, scope: str) -> dict:
        """Deniega una entrega pendiente de confirmación (requiere admin)."""
        return _json_or_raise(self._post("/admin/deny",
                                         {"client_id": client_id, "scope": scope}))

    # --- utilidades ---

    def _ws_base(self) -> str:
        """URL base para WebSocket (ws:// o wss:// según el esquema HTTP)."""
        if self.base_url.startswith("https://"):
            return "wss://" + self.base_url[len("https://"):]
        if self.base_url.startswith("http://"):
            return "ws://" + self.base_url[len("http://"):]
        return self.base_url

    def close(self) -> None:
        """Cierra el cliente HTTP (si lo creó este objeto)."""
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> "NeuroGateClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _detail(resp: httpx.Response) -> str:
    """Extrae el motivo de error de una respuesta del gateway."""
    try:
        return resp.json().get("detail", resp.text)
    except Exception:
        return resp.text


def _json_or_raise(resp: httpx.Response) -> dict:
    """Devuelve el JSON o lanza NeuroGateError si el gateway respondió error."""
    if resp.status_code >= 400:
        raise NeuroGateError(resp.status_code, _detail(resp))
    return resp.json()
