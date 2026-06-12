"""Demo de cierre de la Fase C: el gateway como servicio + dos apps externas.

Arranca el servicio FastAPI (uvicorn en un subproceso) con los clientes de los
ejemplos dados de alta, y lanza las dos apps cliente (``cursor_app`` y
``messaging_app``) en PROCESOS SEPARADOS. Cada una se autentica y consume su
stream según su scope, reproduciendo el flujo v1 extremo a extremo pero por red.

Guarda la narración en ``demos/phaseC_service.txt`` (artefacto NUEVO; no toca
los de v1/A/B).

Uso:
    python -m demos.phaseC_demo
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

HOST = "127.0.0.1"
PORT = 8077  # puerto de demo, distinto del 8000 por defecto
BASE_URL = f"http://{HOST}:{PORT}"
ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


def _wait_until_up(timeout: float = 25.0) -> bool:
    """Espera a que el servicio responda (sondea /docs)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            httpx.get(f"{BASE_URL}/docs", timeout=1.0)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def _run_client(module: str, n: int) -> str:
    """Lanza una app cliente en un proceso separado y devuelve su salida."""
    proc = subprocess.run(
        [PYTHON, "-m", module, "--url", BASE_URL, "--n", str(n)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=60,
    )
    return proc.stdout + (proc.stderr if proc.returncode else "")


def main() -> None:
    demos = ROOT / "demos"
    demos.mkdir(exist_ok=True)
    audit_path = demos / "phaseC_service_audit.jsonl"
    audit_path.unlink(missing_ok=True)

    # Entorno del servicio: secreto de demo (>=32 bytes) y log dedicado.
    env = dict(os.environ)
    env["NEUROGATE_JWT_SECRET"] = "demo-phase-c-secret-32-bytes-minimum-abcdef"
    env["NEUROGATE_AUDIT_PATH"] = str(audit_path)

    # Arranca uvicorn en un subproceso (HTTP de desarrollo; TLS llega en Fase D).
    # --factory: uvicorn llama a build_demo_app() en el worker (no al importar).
    server = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "--factory", "demos.phaseC_demo:build_demo_app",
         "--host", HOST, "--port", str(PORT), "--log-level", "warning"],
        cwd=str(ROOT), env=env,
    )
    lines: list[str] = []
    try:
        if not _wait_until_up():
            raise RuntimeError("el servicio no arrancó a tiempo")
        lines.append(f"Servicio NeuroGate arriba en {BASE_URL} (HTTP de desarrollo)")
        lines.append("")

        lines.append("--- app 1: cursor_app (scope read:intent, WebSocket) ---")
        lines.append(_run_client("examples.cursor_app", n=5).rstrip())
        lines.append("")
        lines.append("--- app 2: messaging_app (scope read:confirmed_text, REST) ---")
        lines.append(_run_client("examples.messaging_app", n=3).rstrip())
        lines.append("")

        # Estado en vivo vía /admin/state (token admin).
        with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
            atok = client.post("/auth/token", json={
                "client_id": "admin_app",
                "client_secret": "admin-secret-please-change",
            }).json()["access_token"]
            state = client.get("/admin/state",
                               headers={"Authorization": f"Bearer {atok}"}).json()
        lines.append("--- estado del servicio (/admin/state) ---")
        lines.append(f"clientes registrados : {state['clients']}")
        lines.append(f"intención más reciente: {state['latest_intent']}")
        lines.append(f"contadores           : {state['counters']}")
        lines.append(f"estado apps          : {state['app_status']}")
        lines.append(f"integridad del log   : {'INTEGRO' if state['audit_ok'] else 'ALTERADO'}")
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()

    report = ("Fase C — gateway como servicio (flujo extremo a extremo por red)\n"
              + "=" * 64 + "\n" + "\n".join(lines) + "\n")
    out = demos / "phaseC_service.txt"
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"Artefacto guardado en {out}")


# --- factory para uvicorn: la app con los clientes de los ejemplos dados de alta ---

def build_demo_app():
    """Crea la app FastAPI con los tres clientes de la demo registrados.

    uvicorn la invoca con --factory (en el worker, no al importar el módulo).
    """
    from neurogate.config import Settings
    from neurogate.service import create_app

    settings = Settings()  # lee NEUROGATE_* del entorno (incluido el secreto de demo)
    audit_path = os.environ.get("NEUROGATE_AUDIT_PATH", "audit_service.jsonl")
    app = create_app(settings=settings, audit_path=audit_path,
                     background_loop=True, prime_anomaly=True)
    state = app.state.service
    state.register_client("cursor_app", "cursor-secret-please-change",
                          ["read:intent"])
    state.register_client("messaging_app", "messaging-secret-please-change",
                          ["read:confirmed_text"])
    state.register_client("admin_app", "admin-secret-please-change",
                          ["admin", "read:stats"])
    return app


if __name__ == "__main__":
    main()
