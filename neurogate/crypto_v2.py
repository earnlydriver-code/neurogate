"""Cifrado serio por app (Fase D): HKDF + AESGCM, rotación versionada y anti-replay.

Mejora la ``CryptoLayer`` de la v1 (Fernet con clave aleatoria por app) con:

- **Clave derivada por app con HKDF** a partir de una *master key* del entorno
  (``NEUROGATE_MASTER_KEY``) + el ``client_id``. La master key nunca está en el
  código; las claves por app no se almacenan, se derivan bajo demanda.
- **Rotación versionada**: cada rotación incrementa una versión global; la clave
  por app se deriva de (master_key, client_id, versión). El sobre del mensaje
  lleva su versión, así un mensaje cifrado antes de rotar sigue descifrándose
  mientras la versión anterior siga en la ventana de retención.
- **Anti-replay**: cada sobre lleva ``nonce`` (12 bytes, único por mensaje) y
  ``timestamp``. Al descifrar se rechazan nonces ya vistos o timestamps fuera de
  la ventana configurada.

Construye AL LADO de ``crypto_layer.py`` (v1 intacta); el servicio v2 usa esta.
"""

from __future__ import annotations

import os
import struct
import time
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# Tamaño del nonce de AES-GCM (96 bits es el recomendado).
_NONCE_LEN = 12
# Longitud de la clave derivada (AES-256).
_KEY_LEN = 32
# Cabecera binaria del sobre: versión (uint32) + timestamp (double) + nonce.
_HEADER = struct.Struct(">Id")  # big-endian: uint32 + float64


class ReplayError(Exception):
    """El mensaje es un replay: nonce repetido o timestamp fuera de ventana."""


class DecryptError(Exception):
    """No se pudo descifrar: clave equivocada, versión caducada o sobre alterado."""


@dataclass(frozen=True)
class Envelope:
    """Sobre cifrado autodescriptivo: versión de clave + timestamp + nonce + ciphertext."""

    version: int
    timestamp: float
    nonce: bytes
    ciphertext: bytes  # incluye el tag de autenticación de AES-GCM

    def to_bytes(self) -> bytes:
        """Serializa el sobre a bytes (lo que viaja por la red)."""
        return _HEADER.pack(self.version, self.timestamp) + self.nonce + self.ciphertext

    @classmethod
    def from_bytes(cls, raw: bytes) -> "Envelope":
        """Reconstruye un sobre desde bytes."""
        head = _HEADER.size
        version, timestamp = _HEADER.unpack(raw[:head])
        nonce = raw[head:head + _NONCE_LEN]
        ciphertext = raw[head + _NONCE_LEN:]
        return cls(version, timestamp, nonce, ciphertext)


def load_master_key() -> bytes:
    """Lee la master key del entorno (``NEUROGATE_MASTER_KEY``).

    Debe ser una cadena no vacía. En producción real iría en un KMS. Lanzar si
    falta evita arrancar el servicio con una clave por defecto insegura.
    """
    raw = os.environ.get("NEUROGATE_MASTER_KEY", "").strip()
    if not raw:
        raise RuntimeError(
            "NEUROGATE_MASTER_KEY no está definida: el cifrado v2 la exige")
    return raw.encode("utf-8")


class CryptoLayerV2:
    """Cifrado por app con clave derivada (HKDF), rotación versionada y anti-replay."""

    def __init__(self, master_key: bytes | None = None, *,
                 replay_window_seconds: float = 30.0,
                 retained_versions: int = 1) -> None:
        # master_key explícita (tests) o desde el entorno.
        self._master_key = master_key if master_key is not None else load_master_key()
        self._version = 0  # versión actual de clave (sube con rotate())
        self._replay_window = replay_window_seconds
        # Cuántas versiones anteriores se aceptan al descifrar durante la rotación.
        self._retained_versions = retained_versions
        self._apps: set[str] = set()
        # Anti-replay: nonce consumido -> instante en que se vio. Se podan los que
        # salen de la ventana (un replay viejo ya lo rechaza el chequeo de timestamp),
        # de modo que el conjunto no crece sin límite en un servicio de larga vida.
        self._seen_nonces: dict[bytes, float] = {}

    @property
    def version(self) -> int:
        """Versión de clave actual (la que usan los mensajes nuevos)."""
        return self._version

    def register_app(self, app_id: str) -> None:
        """Da de alta una app. No guarda clave: se deriva por HKDF cuando hace falta."""
        self._apps.add(app_id)

    def rotate(self) -> int:
        """Rota las claves: sube la versión global. Devuelve la nueva versión.

        Los mensajes nuevos usan la versión nueva; los ya emitidos siguen
        descifrándose mientras su versión esté dentro de la ventana retenida.
        """
        self._version += 1
        return self._version

    def _derive_key(self, app_id: str, version: int) -> bytes:
        """Deriva la clave AES de una app para una versión concreta (HKDF-SHA256).

        El ``info`` ata la clave a la app y a la versión: cambiar cualquiera da
        una clave distinta, así una app no puede descifrar lo de otra.
        """
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=_KEY_LEN,
            salt=None,
            info=f"neurogate:{app_id}:v{version}".encode("utf-8"),
        )
        return hkdf.derive(self._master_key)

    def encrypt_for(self, app_id: str, data: bytes,
                    timestamp: float | None = None) -> bytes:
        """Cifra un dato para una app y devuelve el sobre serializado.

        Usa la versión de clave actual. Añade nonce aleatorio y timestamp para
        protección anti-replay en el lado del receptor (el propio servicio).
        """
        if app_id not in self._apps:
            raise KeyError(f"app '{app_id}' sin clave registrada")
        ts = timestamp if timestamp is not None else time.time()
        key = self._derive_key(app_id, self._version)
        nonce = os.urandom(_NONCE_LEN)
        # AAD = cabecera (versión+timestamp): autentica el sobre, no solo el dato.
        aad = _HEADER.pack(self._version, ts)
        ciphertext = AESGCM(key).encrypt(nonce, data, aad)
        return Envelope(self._version, ts, nonce, ciphertext).to_bytes()

    def decrypt(self, app_id: str, raw: bytes, *,
                now: float | None = None, check_replay: bool = True) -> bytes:
        """Descifra un sobre con la clave de la app; aplica anti-replay.

        - Prueba la versión del sobre y, si toca, versiones anteriores dentro de
          la ventana retenida (descifra durante la rotación sin cortar servicio).
        - Rechaza nonces ya vistos o timestamps fuera de la ventana (replay).
        """
        if app_id not in self._apps:
            raise KeyError(f"app '{app_id}' sin clave registrada")
        env = Envelope.from_bytes(raw)

        if check_replay:
            current = now if now is not None else time.time()
            self._prune_nonces(current)
            if abs(current - env.timestamp) > self._replay_window:
                raise ReplayError("timestamp fuera de la ventana anti-replay")
            if env.nonce in self._seen_nonces:
                raise ReplayError("nonce repetido (replay detectado)")

        aad = _HEADER.pack(env.version, env.timestamp)
        plaintext = self._try_decrypt(app_id, env, aad)

        if check_replay:
            self._seen_nonces[env.nonce] = current
        return plaintext

    def _prune_nonces(self, now: float) -> None:
        """Olvida nonces fuera de la ventana anti-replay (un replay viejo ya lo
        rechaza el chequeo de timestamp), acotando la memoria del detector."""
        horizon = now - self._replay_window
        stale = [n for n, ts in self._seen_nonces.items() if ts < horizon]
        for n in stale:
            del self._seen_nonces[n]

    def _try_decrypt(self, app_id: str, env: Envelope, aad: bytes) -> bytes:
        """Intenta descifrar con la versión del sobre y versiones retenidas."""
        oldest = max(0, self._version - self._retained_versions)
        # Solo aceptamos la versión del sobre si sigue dentro de la ventana.
        if env.version < oldest or env.version > self._version:
            raise DecryptError(
                f"versión de clave {env.version} fuera de la ventana retenida")
        key = self._derive_key(app_id, env.version)
        try:
            return AESGCM(key).decrypt(env.nonce, env.ciphertext, aad)
        except InvalidTag:
            raise DecryptError("no se pudo descifrar (clave o sobre inválidos)")


def _demo() -> None:
    """A cifra y descifra lo suyo; B (otra clave) no; rotación OK; replay rechazado."""
    from pathlib import Path

    demos = Path(__file__).resolve().parent.parent / "demos"
    demos.mkdir(exist_ok=True)

    crypto = CryptoLayerV2(master_key=b"demo-master-key-no-usar-en-produccion")
    crypto.register_app("app_A")
    crypto.register_app("app_B")

    secret = b"intencion: move_cursor"
    sobre = crypto.encrypt_for("app_A", secret)

    lines = [
        f"dato original          : {secret.decode()}",
        f"sobre cifrado (bytes)  : {sobre[:32].hex()}... ({len(sobre)} bytes)",
        f"app_A descifra         : {crypto.decrypt('app_A', sobre, check_replay=False).decode()}",
    ]
    try:
        crypto.decrypt("app_B", sobre, check_replay=False)
        lines.append("app_B descifra         : (FALLO DE SEGURIDAD: lo descifró)")
    except DecryptError:
        lines.append("app_B intenta descifrar: BLOQUEADO (clave derivada distinta)")

    # Rotación: un sobre viejo aún se descifra (versión retenida).
    crypto.rotate()
    lines.append(f"tras rotar a v{crypto.version}          : sobre viejo (v0) sigue legible -> "
                 f"{crypto.decrypt('app_A', sobre, check_replay=False).decode()}")

    # Replay: reenviar el mismo sobre (con anti-replay) se rechaza.
    fresh = crypto.encrypt_for("app_A", secret)
    crypto.decrypt("app_A", fresh)  # primera vez: OK
    try:
        crypto.decrypt("app_A", fresh)  # segunda vez: replay
        lines.append("replay                 : (FALLO: aceptó el reenvío)")
    except ReplayError:
        lines.append("replay del mismo sobre : BLOQUEADO (nonce ya visto)")

    report = "Fase D — crypto_v2 (HKDF + AESGCM + rotación + anti-replay)\n" + \
             "=" * 60 + "\n" + "\n".join(lines) + "\n"
    (demos / "phaseD_crypto.txt").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    _demo()
