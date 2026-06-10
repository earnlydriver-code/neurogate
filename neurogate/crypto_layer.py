"""El blindaje: cifra todo dato que sale del gateway.

Cada dato aprobado se cifra con AES (Fernet, de la librería `cryptography`)
antes de entregarse. Cada app tiene SU PROPIA clave: interceptar el tráfico
de una app no sirve para leer el de otra, y nadie sin clave lee nada.

Nota educativa: Fernet = AES-128-CBC + HMAC, una receta estándar y segura.
El manejo de claves está simplificado para la demo (en producción habría
rotación, almacenamiento seguro, etc.).
"""

from __future__ import annotations


class CryptoLayer:
    """Cifrado por app de los datos que salen del gateway."""

    def __init__(self) -> None:
        # TODO (Paso 6): inicializar el almacén de claves (dict app_id -> clave).
        raise NotImplementedError("Se implementa en el Paso 6")

    def register_app(self, app_id: str) -> bytes:
        """Genera la clave propia de una app y la devuelve.

        Returns:
            La clave Fernet de la app (la app la necesita para descifrar).
        """
        # TODO (Paso 6): generar clave Fernet y guardarla en el almacén.
        raise NotImplementedError("Se implementa en el Paso 6")

    def encrypt_for(self, app_id: str, data: bytes) -> bytes:
        """Cifra un dato con la clave de la app destinataria."""
        # TODO (Paso 6): cifrar con la Fernet de esa app; error claro si la
        # app no tiene clave registrada.
        raise NotImplementedError("Se implementa en el Paso 6")

    def decrypt(self, app_id: str, token: bytes) -> bytes:
        """Descifra un token con la clave de la app (lado receptor de la demo)."""
        # TODO (Paso 6): descifrar; una clave equivocada debe fallar
        # ruidosamente (InvalidToken), eso ES la demo de seguridad.
        raise NotImplementedError("Se implementa en el Paso 6")


# TODO (Paso 6): demo ejecutable `python -m neurogate.crypto_layer`: un dato
# se cifra para la app A; la app A lo lee, la app B (clave incorrecta) no.
