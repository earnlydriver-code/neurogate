"""Autenticación del servicio (Fase C): clientes, JWT por scopes y revocación.

Cada app cliente se registra con ``client_id`` + ``client_secret`` (el secreto se
guarda hasheado, nunca en claro). ``POST /auth/token`` (client credentials) emite
un JWT firmado con: ``client_id``, ``scopes``, ``exp`` (expiración) y ``jti`` (id
de token). La verificación comprueba firma + expiración y consulta una lista de
revocación en CADA request, de modo que revocar un ``jti`` corta el acceso al
instante.

Los scopes mapean a los ``DataType`` de la v1 (``consent.py``), que se reutiliza
sin tocar.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

import jwt
from passlib.context import CryptContext

from neurogate.consent import DataType

# pbkdf2_sha256: hashing robusto sin dependencias nativas (no requiere bcrypt).
_pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# Scopes del servicio y su mapeo a los DataType de la v1. Los scopes sin dato
# asociado (read:stats, admin) mapean a None: no entregan señal neuronal.
SCOPE_TO_DATATYPE: dict[str, DataType | None] = {
    "read:intent": DataType.INTENT,
    "read:confirmed_text": DataType.CONFIRMED_TEXT,
    "read:raw_signal": DataType.RAW_SIGNAL,  # solo en modo clínico
    "read:stats": None,
    "admin": None,
}

# Scope sensible que solo se concede en "modo clínico" (desactivado por defecto).
CLINICAL_SCOPE = "read:raw_signal"


class AuthError(Exception):
    """Error de autenticación con un código HTTP asociado (401/403)."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class TokenClaims:
    """Contenido verificado de un JWT."""

    client_id: str
    scopes: list[str]
    jti: str
    exp: int


@dataclass
class Client:
    """Una app registrada: su id, el hash de su secreto y sus scopes concedidos."""

    client_id: str
    secret_hash: str
    scopes: list[str] = field(default_factory=list)


def scopes_to_datatypes(scopes: list[str]) -> set[DataType]:
    """Traduce una lista de scopes a los DataType de la v1 que conceden."""
    out: set[DataType] = set()
    for s in scopes:
        dtype = SCOPE_TO_DATATYPE.get(s)
        if dtype is not None:
            out.add(dtype)
    return out


class AuthManager:
    """Registro de clientes + emisión/verificación de JWT + revocación en caliente."""

    def __init__(self, jwt_secret: str, algorithm: str = "HS256",
                 token_expire_minutes: int = 30, clinical_mode: bool = False) -> None:
        self._jwt_secret = jwt_secret
        self._algorithm = algorithm
        self._token_expire_seconds = token_expire_minutes * 60
        self.clinical_mode = clinical_mode
        self._clients: dict[str, Client] = {}
        self._revoked: set[str] = set()  # jti revocados (lista de revocación)

    # --- registro de clientes ---

    def register_client(self, client_id: str, client_secret: str,
                        scopes: list[str]) -> None:
        """Da de alta una app: guarda el secreto hasheado y sus scopes concedidos.

        El scope clínico read:raw_signal solo se concede si clinical_mode está activo.
        """
        granted = []
        for s in scopes:
            if s not in SCOPE_TO_DATATYPE:
                raise ValueError(f"scope desconocido: {s}")
            if s == CLINICAL_SCOPE and not self.clinical_mode:
                continue  # se ignora silenciosamente: el modo clínico está apagado
            granted.append(s)
        self._clients[client_id] = Client(client_id, _pwd.hash(client_secret), granted)

    def client_scopes(self, client_id: str) -> list[str]:
        """Scopes concedidos a un cliente (vacío si no existe)."""
        c = self._clients.get(client_id)
        return list(c.scopes) if c else []

    @property
    def clients(self) -> list[str]:
        return list(self._clients)

    # --- emisión de tokens (client credentials) ---

    def issue_token(self, client_id: str, client_secret: str,
                    scopes: list[str] | None = None) -> tuple[str, TokenClaims]:
        """Verifica credenciales y emite un JWT firmado. Lanza AuthError si fallan.

        Si se piden scopes, deben ser un subconjunto de los concedidos al cliente;
        si no se piden, se emiten todos los concedidos.
        """
        client = self._clients.get(client_id)
        if client is None or not _pwd.verify(client_secret, client.secret_hash):
            raise AuthError(401, "credenciales inválidas")
        if scopes is None:
            granted = list(client.scopes)
        else:
            extra = set(scopes) - set(client.scopes)
            if extra:
                raise AuthError(403, f"scopes no concedidos: {sorted(extra)}")
            granted = list(scopes)

        now = int(time.time())
        jti = uuid.uuid4().hex
        payload = {
            "client_id": client_id,
            "scopes": granted,
            "iat": now,
            "exp": now + self._token_expire_seconds,
            "jti": jti,
        }
        token = jwt.encode(payload, self._jwt_secret, algorithm=self._algorithm)
        claims = TokenClaims(client_id, granted, jti, payload["exp"])
        return token, claims

    # --- verificación + revocación ---

    def verify_token(self, token: str) -> TokenClaims:
        """Verifica firma + expiración y consulta la lista de revocación.

        Lanza AuthError(401) si el token está expirado, forjado o revocado.
        """
        try:
            payload = jwt.decode(token, self._jwt_secret, algorithms=[self._algorithm])
        except jwt.ExpiredSignatureError:
            raise AuthError(401, "token expirado")
        except jwt.InvalidTokenError:
            raise AuthError(401, "token inválido o firma incorrecta")

        jti = payload.get("jti", "")
        if jti in self._revoked:
            raise AuthError(401, "token revocado")
        return TokenClaims(payload["client_id"], payload.get("scopes", []),
                           jti, payload["exp"])

    def revoke(self, jti: str) -> None:
        """Revoca un token por su jti: cualquier request con ese jti queda bloqueada."""
        self._revoked.add(jti)

    def is_revoked(self, jti: str) -> bool:
        return jti in self._revoked
