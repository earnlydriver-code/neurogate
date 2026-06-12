"""App cliente de ejemplo: control de cursor (scope read:intent, vía WebSocket).

Proceso independiente que se autentica contra el gateway y consume el stream de
intenciones decodificadas. Representa una app que mueve un cursor con el
"pensamiento". Solo tiene permiso para INTENT; cualquier otro dato le es denegado.

Uso:
    python -m examples.cursor_app                 # contra http://127.0.0.1:8000
    python -m examples.cursor_app --url ... --n 5
"""

from __future__ import annotations

import argparse
import asyncio
import json

import httpx
import websockets

CLIENT_ID = "cursor_app"
CLIENT_SECRET = "cursor-secret-please-change"  # demo; en real saldría del entorno
SCOPES = ["read:intent"]


async def get_token(base_url: str) -> str:
    """Pide un JWT al gateway con client credentials."""
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        resp = await client.post("/auth/token", json={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scopes": SCOPES,
        })
        resp.raise_for_status()
        data = resp.json()
        print(f"[cursor_app] token obtenido, scopes={data['scopes']}")
        return data["access_token"]


async def stream_intents(base_url: str, token: str, n: int) -> list[str]:
    """Abre el WebSocket de intenciones y consume n mensajes."""
    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
    uri = f"{ws_url}/stream/intents?token={token}"
    received: list[str] = []
    async with websockets.connect(uri) as ws:
        for _ in range(n):
            msg = json.loads(await ws.recv())
            if "error" in msg:
                print(f"[cursor_app] bloqueado: {msg['error']}")
                break
            received.append(msg["intent"])
            print(f"[cursor_app] intención recibida: {msg['intent']} "
                  f"(payload cifrado, {len(msg['payload_b64'])} chars b64)")
    return received


async def main(base_url: str, n: int) -> None:
    token = await get_token(base_url)
    await stream_intents(base_url, token, n)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cliente cursor_app (read:intent)")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--n", type=int, default=5, help="número de intenciones a recibir")
    args = parser.parse_args()
    asyncio.run(main(args.url, args.n))
