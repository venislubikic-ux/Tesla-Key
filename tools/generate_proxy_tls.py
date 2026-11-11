"""Create a self-signed TLS certificate for the local tesla-http-proxy (localhost only).

  tls-key.pem / tls-cert.pem  -> pass to tesla-http-proxy (-tls-key / -cert)
  In TK settings, set "Сертификат прокси" to tls-cert.pem so TK trusts the proxy.

Usage:  python tools/generate_proxy_tls.py [output_dir]
"""
import datetime as dt
import ipaddress
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "keys")
    out.mkdir(parents=True, exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName([
            x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, key_agreement=True,
                                     content_commitment=False, key_encipherment=False, data_encipherment=False,
                                     crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
        .sign(key, hashes.SHA256())
    )
    (out / "tls-key.pem").write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (out / "tls-cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print(f"Готово: {out / 'tls-key.pem'}, {out / 'tls-cert.pem'}")


if __name__ == "__main__":
    main()
