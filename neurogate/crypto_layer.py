"""Cifrado de salida: AES (Fernet) con clave propia por app."""

from __future__ import annotations


class CryptoLayer:
    """Cifra lo que sale del gateway; cada app tiene su propia clave."""

    def __init__(self) -> None:
        # TODO (Paso 6): almacén de claves (app_id -> clave Fernet).
        raise NotImplementedError("Se implementa en el Paso 6")

    def register_app(self, app_id: str) -> bytes:
        """Genera y devuelve la clave de una app."""
        # TODO (Paso 6)
        raise NotImplementedError("Se implementa en el Paso 6")

    def encrypt_for(self, app_id: str, data: bytes) -> bytes:
        """Cifra un dato con la clave de la app destinataria."""
        # TODO (Paso 6)
        raise NotImplementedError("Se implementa en el Paso 6")

    def decrypt(self, app_id: str, token: bytes) -> bytes:
        """Descifra un token; clave equivocada debe fallar (InvalidToken)."""
        # TODO (Paso 6)
        raise NotImplementedError("Se implementa en el Paso 6")


# TODO (Paso 6): demo `python -m neurogate.crypto_layer`: app A lee, app B no puede.
