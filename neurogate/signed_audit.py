"""Log auditable firmado (Fase D): cadena SHA-256 de la v1 + firma Ed25519.

Extiende ``audit.py`` (v1) manteniendo la cadena de hashes encadenada y AÑADIENDO
una firma Ed25519 por entrada con la clave privada del gateway. Un tercero, con
solo la **clave pública**, puede verificar (a) integridad de la cadena y (b)
autenticidad del emisor, sin acceso al sistema.

La clave privada va por entorno/archivo ignorado, NUNCA al repo. La pública sí se
puede publicar/versionar. Formato JSONL append-only; cada línea es un registro
con ``event`` (timestamp, client_id, scope, decisión, motivo), ``prev_hash``,
``hash`` y ``signature``.

Construye AL LADO de ``audit.py`` (v1 intacta); el servicio v2 usa esta.
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey)

# Hash inicial de la cadena (no hay entrada previa a la primera).
_GENESIS = "0" * 64


@dataclass(frozen=True)
class SignedAuditEvent:
    """Un evento auditable firmado: el rastro de una decisión del gateway.

    ``decision`` es allow/deny/quarantine; ``scope`` es el scope solicitado.
    """

    client_id: str
    scope: str
    decision: str  # "allow" | "deny" | "quarantine"
    reason: str
    timestamp: float = field(default_factory=time.time)


def _entry_hash(prev_hash: str, event_dict: dict) -> str:
    """SHA-256 del hash previo + el contenido del evento (orden estable)."""
    payload = prev_hash + json.dumps(event_dict, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def generate_keypair() -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    """Genera un par de claves Ed25519 nuevo (privada, pública)."""
    private = Ed25519PrivateKey.generate()
    return private, private.public_key()


def private_key_to_pem(private: Ed25519PrivateKey) -> bytes:
    """Serializa la clave privada a PEM (PKCS8, sin cifrar). Va por archivo ignorado."""
    from cryptography.hazmat.primitives import serialization

    return private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def public_key_to_pem(public: Ed25519PublicKey) -> bytes:
    """Serializa la clave pública a PEM. Se puede publicar/versionar."""
    from cryptography.hazmat.primitives import serialization

    return public.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def load_private_key(pem: bytes) -> Ed25519PrivateKey:
    """Carga una clave privada Ed25519 desde PEM."""
    from cryptography.hazmat.primitives import serialization

    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("el PEM no contiene una clave privada Ed25519")
    return key


def load_public_key(pem: bytes) -> Ed25519PublicKey:
    """Carga una clave pública Ed25519 desde PEM."""
    from cryptography.hazmat.primitives import serialization

    key = serialization.load_pem_public_key(pem)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("el PEM no contiene una clave pública Ed25519")
    return key


class SignedAuditLog:
    """Log append-only encadenado (SHA-256) y firmado por entrada (Ed25519)."""

    def __init__(self, path: Path | str, private_key: Ed25519PrivateKey) -> None:
        self.path = Path(path)
        self._private = private_key
        self._last_hash = self._recover_last_hash()
        # El append (leer-firmar-escribir _last_hash) debe ser atómico: sin esto,
        # dos escrituras concurrentes compartirían prev_hash y romperían la cadena.
        self._lock = threading.Lock()

    def _recover_last_hash(self) -> str:
        """Recupera el hash de la última entrada para continuar la cadena."""
        if not self.path.exists():
            return _GENESIS
        last = _GENESIS
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                last = json.loads(line)["hash"]
        return last

    def append(self, event: SignedAuditEvent) -> None:
        """Añade un evento encadenado al hash anterior y firmado con Ed25519.

        La firma cubre el hash de la entrada (que ya incluye prev_hash + evento):
        alterar cualquier campo invalida el hash y, por tanto, la firma.
        """
        with self._lock:
            event_dict = asdict(event)
            h = _entry_hash(self._last_hash, event_dict)
            signature = self._private.sign(h.encode("utf-8"))
            record = {
                "event": event_dict,
                "prev_hash": self._last_hash,
                "hash": h,
                "signature": base64.b64encode(signature).decode("ascii"),
            }
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._last_hash = h

    def verify_chain(self) -> bool:
        """True si la cadena y todas las firmas son válidas (atajo de verify_log)."""
        public = self._private.public_key()
        return verify_log(self.path, public)[0]


def verify_log(path: Path | str, public_key: Ed25519PublicKey) -> tuple[bool, int | None, str]:
    """Verifica un log firmado con la clave pública dada.

    Devuelve ``(ok, primera_línea_corrupta, motivo)``. ``ok`` False si la cadena
    está rota o una firma no valida; ``primera_línea_corrupta`` es el número de
    línea (1-based) del primer problema, o None si todo está íntegro.
    """
    path = Path(path)
    if not path.exists():
        return True, None, "log inexistente (vacío)"

    prev = _GENESIS
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            return False, i, "línea no es JSON válido"

        # 1. Encadenado: prev_hash debe enlazar y el hash debe recomputar igual.
        if rec.get("prev_hash") != prev:
            return False, i, "prev_hash no enlaza con la entrada anterior"
        if _entry_hash(prev, rec["event"]) != rec.get("hash"):
            return False, i, "hash recomputado no coincide (contenido alterado)"

        # 2. Firma Ed25519 sobre el hash de la entrada.
        try:
            signature = base64.b64decode(rec["signature"])
            public_key.verify(signature, rec["hash"].encode("utf-8"))
        except (KeyError, ValueError):
            return False, i, "firma ausente o malformada"
        except InvalidSignature:
            return False, i, "firma Ed25519 inválida"

        prev = rec["hash"]
    return True, None, "íntegro"


def _demo() -> None:
    """Escribe eventos firmados, verifica OK, altera una línea y la verificación falla."""
    demos = Path(__file__).resolve().parent.parent / "demos"
    demos.mkdir(exist_ok=True)
    log_path = demos / "phaseD_signed_audit_sample.jsonl"
    log_path.unlink(missing_ok=True)

    private, public = generate_keypair()
    log = SignedAuditLog(log_path, private)
    log.append(SignedAuditEvent("cursor_app", "read:intent", "allow", "autorizado", 1_000_000.0))
    log.append(SignedAuditEvent("evil_app", "read:raw_signal", "deny", "sin permiso", 1_000_001.0))
    log.append(SignedAuditEvent("flood_app", "read:intent", "quarantine", "anomalía", 1_000_002.0))

    ok, bad, reason = verify_log(log_path, public)
    lines = [f"3 eventos firmados escritos en {log_path.name}",
             f"verificación tras escribir: {'ÍNTEGRO' if ok else f'ALTERADO (línea {bad})'} — {reason}"]

    # Alteramos a mano la segunda línea (el atacante intenta borrar su bloqueo).
    rows = log_path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(rows[1])
    tampered["event"]["decision"] = "allow"
    rows[1] = json.dumps(tampered, ensure_ascii=False)
    log_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    ok2, bad2, reason2 = verify_log(log_path, public)
    lines.append(f"tras alterar 1 carácter de la línea 2: "
                 f"{'ÍNTEGRO (FALLO)' if ok2 else f'ALTERADO (detectado en línea {bad2})'} — {reason2}")

    report = "Fase D — signed_audit (cadena SHA-256 + firma Ed25519)\n" + \
             "=" * 60 + "\n" + "\n".join(lines) + "\n"
    (demos / "phaseD_signed_audit.txt").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    _demo()
