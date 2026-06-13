# Imagen del gateway NeuroGate (servicio FastAPI + uvicorn).
#
# Construye una imagen que sirve el servicio de la Fase E con los clientes de demo
# registrados. En un despliegue real se cambiaría el arranque para registrar las
# apps cliente de cada cliente y se inyectarían los secretos por entorno (ver
# variables NEUROGATE_* en .env.example), nunca dentro de la imagen.
#
# Construir:   docker build -t neurogate-gateway .
# Ejecutar:    docker run -p 8077:8077 --env-file .env neurogate-gateway

FROM python:3.12-slim

# No escribir .pyc y volcar logs sin buffer (mejor para contenedores).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencias del sistema mínimas para compilar ruedas científicas si hiciera falta.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias primero (capa cacheable).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código del proyecto.
COPY neurogate/ neurogate/
COPY examples/ examples/
COPY run_demo_e.py verify_audit.py ./

# El servicio escucha en 8077 (configurable al arrancar).
EXPOSE 8077

# Arranca el gateway de demo con los clientes registrados, accesible desde fuera
# del contenedor. Para TLS real, montar certs y añadir --ssl-* (ver docs/DEPLOY.md).
CMD ["python", "run_demo_e.py", "--host", "0.0.0.0", "--port", "8077"]
