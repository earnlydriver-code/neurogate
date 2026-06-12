"""Genera un certificado TLS autofirmado de desarrollo (Fase D).

Crea un par clave/cert para servir el gateway sobre HTTPS/WSS en local. NO usar
en producción: ahí va un certificado emitido por una CA real (Let's Encrypt, ACM,
etc.). El cert y la clave se escriben en ``certs/`` (ignorado por git).

Uso:
    python scripts/gen_cert.py
    # luego arrancar uvicorn con TLS:
    uvicorn neurogate.service:app --ssl-certfile certs/dev_cert.pem \\
        --ssl-keyfile certs/dev_key.pem

Para un certificado real en despliegue: obtén cert+clave de tu CA y apunta
NEUROGATE_TLS_CERTFILE / NEUROGATE_TLS_KEYFILE (o las flags de uvicorn) a ellos.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def generate_self_signed(cert_path: Path, key_path: Path,
                         common_name: str = "localhost",
                         days_valid: int = 365) -> None:
    """Genera clave RSA + certificado X.509 autofirmado y los guarda en PEM."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "NeuroGate (dev)"),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=days_valid))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(common_name),
                                         x509.DNSName("127.0.0.1")]),
            critical=False)
        .sign(key, hashes.SHA256())
    )

    cert_path.parent.mkdir(parents=True, exist_ok=True)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))


def main() -> None:
    """Genera el cert de desarrollo por defecto en certs/."""
    root = Path(__file__).resolve().parent.parent
    cert_path = root / "certs" / "dev_cert.pem"
    key_path = root / "certs" / "dev_key.pem"
    generate_self_signed(cert_path, key_path)
    print(f"Certificado autofirmado generado:\n  cert: {cert_path}\n  key : {key_path}")
    print("\nArrancar el gateway con TLS:")
    print("  uvicorn neurogate.service:app --ssl-certfile certs/dev_cert.pem "
          "--ssl-keyfile certs/dev_key.pem")


if __name__ == "__main__":
    main()
