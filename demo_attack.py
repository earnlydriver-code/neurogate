"""Demo visual de la suite de ataques contra el servicio NeuroGate (Fase D).

Lanza en vivo los 8 ataques que NeuroGate debe frenar y narra en terminal qué
pasó con cada uno, demostrando que todos quedan bloqueados y auditados en el log
firmado. Al final verifica el log con la clave pública (íntegro) y muestra que
alterar un solo carácter lo delata.

Los 3 ataques clásicos de la v1 corren contra el ``Gateway`` en-proceso
(``tests/attack_sim.py``); los 5 nuevos corren contra el SERVICIO FastAPI por red
(con ``TestClient``). Cada bloqueo pasa por el log Ed25519.

Uso:
    python demo_attack.py
"""

from __future__ import annotations

import base64
import tempfile
import time
from pathlib import Path

import jwt
from fastapi.testclient import TestClient

from neurogate.auth import TokenClaims
from neurogate.config import Settings
from neurogate.service import create_app
from neurogate.signed_audit import load_public_key, verify_log
from tests.attack_sim import simulate_attack
from neurogate.gateway import build_demo_gateway

_SECRET = "demo-secret-largo-y-aleatorio-de-32-bytes-minimo-xx"


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _token(client: TestClient, cid: str, secret: str) -> dict:
    return client.post("/auth/token",
                       json={"client_id": cid, "client_secret": secret}).json()


def _build_service(tmp: Path):
    """Crea el servicio de demo con clientes registrados y baseline aprendido."""
    settings = Settings(
        jwt_secret=_SECRET, seed=0, master_key="demo-master-key-fase-d",
        replay_window_seconds=30.0,
        anomaly_baseline_requests=20, anomaly_rate_spike_factor=10.0,
        audit_private_key_path=str(tmp / "priv.pem"),
        audit_public_key_path=str(tmp / "pub.pem"))
    app = create_app(settings=settings, audit_path=tmp / "audit.jsonl",
                     background_loop=False, prime_anomaly=False)
    state = app.state.service
    state.register_client("cursor_app", "pw-cursor", ["read:intent"])
    state.register_client("messaging_app", "pw-msg", ["read:confirmed_text"])
    state.register_client("reader_app", "pw-reader", ["read:confirmed_text"])
    state.register_client("admin_app", "pw-admin", ["admin"])
    state.prime_anomaly()  # aprende telemetría normal y entra en vigilancia
    state.tick()
    return app, state, tmp / "audit.jsonl", tmp / "pub.pem"


def _run_service_attacks(lines: list[str]) -> None:
    """Lanza los 5 ataques contra el servicio FastAPI y narra cada bloqueo."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        app, state, audit_path, pub_path = _build_service(tmp)

        with TestClient(app) as client:
            # Ataque 4 (token robado/revocado): se revoca y se reutiliza.
            issued = _token(client, "messaging_app", "pw-msg")
            tok, jti = issued["access_token"], issued["jti"]
            ok_before = client.get("/data/confirmed_text", headers=_bearer(tok)).status_code
            atok = _token(client, "admin_app", "pw-admin")["access_token"]
            client.post("/admin/revoke", json={"jti": jti}, headers=_bearer(atok))
            revoked = client.get("/data/confirmed_text", headers=_bearer(tok)).status_code
            lines.append(f"  [4] Token revocado reutilizado: antes {ok_before} OK -> "
                         f"tras revocar {revoked} (esperado 401)  "
                         f"{'BLOQUEADO' if revoked == 401 else 'FALLO'}")

            # Ataque 5 (replay): capturar un sobre cifrado y reenviarlo. Usa una
            # app dedicada (reader_app) para no encadenar dos lecturas a la misma.
            rtok = _token(client, "reader_app", "pw-reader")["access_token"]
            sobre = client.get("/data/confirmed_text",
                               headers=_bearer(rtok)).json()["payload_b64"]
            r1 = client.post("/data/echo", json={"payload_b64": sobre}, headers=_bearer(rtok))
            r2 = client.post("/data/echo", json={"payload_b64": sobre}, headers=_bearer(rtok))
            lines.append(f"  [5] Replay del mismo sobre: 1er envío {r1.status_code} OK -> "
                         f"reenvío {r2.status_code} (esperado 403)  "
                         f"{'BLOQUEADO' if r2.status_code == 403 else 'FALLO'}")

            # Ataque 6 (escalada de scopes): cursor_app (read:intent) pide texto.
            ctok = _token(client, "cursor_app", "pw-cursor")["access_token"]
            esc = client.get("/data/confirmed_text", headers=_bearer(ctok)).status_code
            lines.append(f"  [6] Escalada de scopes (read:intent -> confirmed_text): "
                         f"{esc} (esperado 403)  {'BLOQUEADO' if esc == 403 else 'FALLO'}")

            # Ataque 7 (token forjado): JWT firmado con otra clave.
            forged = jwt.encode(
                {"client_id": "cursor_app", "scopes": ["admin"], "jti": "forged",
                 "exp": int(time.time()) + 100}, "OTRA-CLAVE", algorithm="HS256")
            fg = client.get("/admin/state", headers=_bearer(forged)).status_code
            lines.append(f"  [7] Token forjado (firma incorrecta): {fg} (esperado 401)  "
                         f"{'BLOQUEADO' if fg == 401 else 'FALLO'}")

        # Ataque 8 (flood): ráfaga directa por el pipeline -> cuarentena.
        claims = TokenClaims("cursor_app", ["read:intent"], "j", int(time.time()) + 100)
        blocked = 0
        for _ in range(30):
            try:
                state.serve(claims, "read:intent")
            except Exception:
                blocked += 1
        quarantined = state.app_status["cursor_app"] == "quarantine"
        lines.append(f"  [8] Flood (30 peticiones): {blocked} frenadas, estado "
                     f"'{state.app_status['cursor_app']}'  "
                     f"{'CUARENTENA' if quarantined else 'FALLO'}")

        # Verificación final: el log firmado quedó íntegro y delata alteraciones.
        public = load_public_key(pub_path.read_bytes())
        ok, bad, reason = verify_log(audit_path, public)
        n = sum(1 for ln in audit_path.read_text(encoding="utf-8").splitlines() if ln.strip())
        lines.append("")
        lines.append(f"  Log firmado: {n} entradas -> "
                     f"{'ÍNTEGRO' if ok else f'ALTERADO (línea {bad})'} ({reason})")

        # Alteramos un carácter y reverificamos: debe fallar.
        rows = audit_path.read_text(encoding="utf-8").splitlines()
        target = next(i for i, r in enumerate(rows) if '"deny"' in r)
        rows[target] = rows[target].replace('"deny"', '"allow"', 1)
        audit_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        ok2, bad2, reason2 = verify_log(audit_path, public)
        lines.append(f"  Tras alterar 1 entrada (deny->allow): "
                     f"{'ÍNTEGRO (FALLO)' if ok2 else f'ALTERADO detectado en línea {bad2}'} "
                     f"({reason2})")


def main() -> None:
    """Ejecuta los 8 ataques narrados y guarda el artefacto de la demo."""
    demos = Path(__file__).resolve().parent / "demos"
    demos.mkdir(exist_ok=True)

    lines = ["NeuroGate · Fase D — suite de ataques en vivo",
             "=" * 60,
             "",
             "Ataques clásicos v1 (contra el Gateway en-proceso):"]

    # Los 3 ataques v1 reutilizando el narrador existente.
    with tempfile.TemporaryDirectory() as d:
        gw = build_demo_gateway(audit_path=Path(d) / "audit.jsonl")
        for i, msg in enumerate(simulate_attack(gw), start=1):
            lines.append(f"  [{i}] {msg}")

    lines.append("")
    lines.append("Ataques nuevos v2 (contra el servicio FastAPI, por red):")
    _run_service_attacks(lines)

    report = "\n".join(lines) + "\n"
    (demos / "phaseD_attacks.txt").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
