"""Cifrado de salida: AES (Fernet) con clave propia por app.

Cada dato aprobado se cifra antes de entregarse. Cada app tiene su propia clave:
interceptar el tráfico de una app no sirve para leer el de otra.

Nota: Fernet = AES-128-CBC + HMAC. El manejo de claves está simplificado para
la demo (en producción habría rotación y almacenamiento seguro; eso llega en v2).
"""

from __future__ import annotations

from cryptography.fernet import Fernet


class CryptoLayer:
    """Cifra lo que sale del gateway; cada app tiene su propia clave."""

    def __init__(self) -> None:
        self._keys: dict[str, bytes] = {}        # app_id -> clave (para el lado app)
        self._ciphers: dict[str, Fernet] = {}    # app_id -> cifrador

    def register_app(self, app_id: str) -> bytes:
        """Genera y devuelve la clave de una app."""
        key = Fernet.generate_key()
        self._keys[app_id] = key
        self._ciphers[app_id] = Fernet(key)
        return key

    def encrypt_for(self, app_id: str, data: bytes) -> bytes:
        """Cifra un dato con la clave de la app destinataria."""
        cipher = self._ciphers.get(app_id)
        if cipher is None:
            raise KeyError(f"app '{app_id}' sin clave registrada")
        return cipher.encrypt(data)

    def decrypt(self, app_id: str, token: bytes) -> bytes:
        """Descifra un token con la clave de la app; clave equivocada falla (InvalidToken)."""
        cipher = self._ciphers.get(app_id)
        if cipher is None:
            raise KeyError(f"app '{app_id}' sin clave registrada")
        return cipher.decrypt(token)


def _demo() -> None:
    """Cifra un dato para la app A; A lo lee, B (clave distinta) no puede."""
    from pathlib import Path

    from cryptography.fernet import InvalidToken

    demos = Path(__file__).resolve().parent.parent / "demos"
    demos.mkdir(exist_ok=True)

    crypto = CryptoLayer()
    crypto.register_app("app_A")
    crypto.register_app("app_B")

    secret = b"intencion: move_cursor"
    token = crypto.encrypt_for("app_A", secret)

    lines = [
        f"dato original          : {secret.decode()}",
        f"cifrado (ilegible)     : {token[:48].decode(errors='replace')}...",
        f"app_A descifra         : {crypto.decrypt('app_A', token).decode()}",
    ]
    try:
        crypto.decrypt("app_B", token)
        lines.append("app_B descifra         : (FALLO DE SEGURIDAD: lo descifró)")
    except InvalidToken:
        lines.append("app_B intenta descifrar: BLOQUEADO (clave incorrecta, InvalidToken)")

    report = "Paso 6 — crypto_layer\n" + "=" * 55 + "\n" + "\n".join(lines) + "\n"
    (demos / "step6_crypto.txt").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    _demo()
