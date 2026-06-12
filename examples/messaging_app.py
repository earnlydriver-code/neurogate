"""App cliente de ejemplo: mensajería (scope read:confirmed_text, vía REST).

Proceso independiente que se autentica contra el gateway y solicita texto
confirmado por el usuario. Representa una app de mensajería que solo puede leer
lo que el usuario confirmó explícitamente. No tiene permiso para intenciones ni
señal cruda; pedirlos le da 403.

Uso:
    python -m examples.messaging_app                 # contra http://127.0.0.1:8000
    python -m examples.messaging_app --url ... --n 3
"""

from __future__ import annotations

import argparse
import asyncio

import httpx

CLIENT_ID = "messaging_app"
CLIENT_SECRET = "messaging-secret-please-change"  # demo; en real saldría del entorno
SCOPES = ["read:confirmed_text"]


async def get_token(client: httpx.AsyncClient) -> str:
    """Pide un JWT al gateway con client credentials."""
    resp = await client.post("/auth/token", json={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scopes": SCOPES,
    })
    resp.raise_for_status()
    data = resp.json()
    print(f"[messaging_app] token obtenido, scopes={data['scopes']}")
    return data["access_token"]


async def fetch_confirmed_text(client: httpx.AsyncClient, token: str, n: int) -> int:
    """Pide n veces el texto confirmado; devuelve cuántas entregas recibió."""
    headers = {"Authorization": f"Bearer {token}"}
    ok = 0
    for i in range(n):
        resp = await client.get("/data/confirmed_text", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            ok += 1
            print(f"[messaging_app] entrega {i + 1}: confirmed_text "
                  f"(cifrado, {len(data['payload_b64'])} chars b64)")
        else:
            print(f"[messaging_app] entrega {i + 1} denegada: "
                  f"{resp.status_code} {resp.json().get('detail')}")
        await asyncio.sleep(0.3)
    return ok


async def main(base_url: str, n: int) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        token = await get_token(client)
        delivered = await fetch_confirmed_text(client, token, n)
        print(f"[messaging_app] total entregas recibidas: {delivered}/{n}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cliente messaging_app (read:confirmed_text)")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--n", type=int, default=3, help="número de entregas a pedir")
    args = parser.parse_args()
    asyncio.run(main(args.url, args.n))
