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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Devuelve los ajustes (cacheados). Los tests inyectan los suyos por fixture."""
    return Settings()
