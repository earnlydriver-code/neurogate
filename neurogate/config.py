"""Configuración del servicio (Fase C): secretos y parámetros desde el entorno.

Usa pydantic-settings + un archivo .env (que NO se versiona). El secreto de
firma JWT y cualquier master key salen del entorno, nunca del código.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Ajustes del servicio NeuroGate, leídos de variables de entorno / .env."""

    model_config = SettingsConfigDict(
        env_prefix="NEUROGATE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Secreto para firmar los JWT (HS256). En producción iría en un KMS.
    jwt_secret: str = "dev-insecure-change-me"
    # Algoritmo de firma del JWT.
    jwt_algorithm: str = "HS256"
    # Minutos de validez de un token emitido.
    token_expire_minutes: int = 30
    # Habilitar el scope clínico read:raw_signal (desactivado por defecto).
    clinical_mode: bool = False
    # Semilla determinista para señal + decoder del bucle de fondo.
    seed: int = 0

    # --- Fase D (hardening) ---
    # Master key del cifrado por app (HKDF). NUNCA en código; en producción, KMS.
    master_key: str = "dev-insecure-master-key-change-me"
    # Ventana anti-replay (s): timestamps fuera de ella se rechazan.
    replay_window_seconds: float = 30.0
    # Cada cuántos requests del servicio rotar las claves de cifrado (0 = no rotar).
    key_rotation_every: int = 0
    # Versiones de clave anteriores que se siguen aceptando durante la rotación.
    retained_key_versions: int = 1
    # Ruta de la clave privada Ed25519 del log firmado (PEM). Va por archivo ignorado.
    audit_private_key_path: str = "keys/audit_ed25519_private.pem"
    # Ruta de la clave pública Ed25519 (se puede versionar/regenerar).
    audit_public_key_path: str = "keys/audit_ed25519_public.pem"
    # Requests por app a aprender antes de pasar a vigilancia (telemetría).
    anomaly_baseline_requests: int = 30
    # Factor de pico de tasa que dispara cuarentena (×N sobre la tasa típica).
    anomaly_rate_spike_factor: float = 10.0
    # Ventana deslizante (s) para medir la tasa de peticiones por app.
    anomaly_rate_window_seconds: float = 1.0
    # Mínimo de peticiones en la ventana para considerar flood (evita falsos
    # positivos con 2-3 peticiones legítimas muy seguidas).
    anomaly_min_flood_burst: int = 5
    # Rutas del certificado/clave TLS para servir HTTPS/WSS (uvicorn los usa).
    tls_certfile: str = "certs/dev_cert.pem"
    tls_keyfile: str = "certs/dev_key.pem"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Devuelve los ajustes (cacheados). Los tests inyectan los suyos por fixture."""
    return Settings()
