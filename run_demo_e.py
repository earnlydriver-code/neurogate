"""Arranque local de la demo de la Fase E: el servicio NeuroGate listo para el dashboard.

Levanta el servicio FastAPI con los clientes de demo ya registrados (apps cliente
+ admin del dashboard) y el detector de anomalías en vigilancia. Una vez en marcha,
el dashboard (``streamlit run neurogate/dashboard_service.py``) se conecta como un
cliente admin más.

Uso:
    python run_demo_e.py                 # sirve en http://127.0.0.1:8077
    python run_demo_e.py --port 9000
    python run_demo_e.py --host 0.0.0.0  # accesible en red local

Luego, en otra terminal:
    streamlit run neurogate/dashboard_service.py

El servicio usa la configuración de .env / variables de entorno (ver .env.example).
Para la demo bastan los valores por defecto.
"""

from __future__ import annotations

import argparse

import uvicorn

from neurogate.config import get_settings
from neurogate.service import build_demo_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Servicio NeuroGate para la demo de la Fase E")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8077)
    parser.add_argument("--audit", default="audit_service.jsonl",
                        help="ruta del log auditado firmado")
    args = parser.parse_args()

    app = build_demo_app(settings=get_settings(), audit_path=args.audit,
                         background_loop=True)
    print(f"NeuroGate · servicio de demo (Fase E) en http://{args.host}:{args.port}")
    print("Conecta el dashboard:  streamlit run neurogate/dashboard_service.py")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
