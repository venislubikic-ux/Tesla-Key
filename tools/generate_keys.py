"""Generate the partner key pair required by Tesla (EC NIST P-256 / prime256v1).

  private-key.pem                      -> keep secret; used ONLY by tesla-http-proxy to sign commands
  com.tesla.3p.public-key.pem          -> publish at
        https://<your-domain>/.well-known/appspecific/com.tesla.3p.public-key.pem

Usage:  python tools/generate_keys.py [output_dir]
"""
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "keys")
    out.mkdir(parents=True, exist_ok=True)
    priv_path = out / "private-key.pem"
    if priv_path.exists():
        sys.exit(f"{priv_path} уже существует — не перезаписываю (иначе ключ в автомобилях станет недействительным).")

    key = ec.generate_private_key(ec.SECP256R1())
    priv_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()))
    (out / "com.tesla.3p.public-key.pem").write_bytes(key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    print(f"Готово:\n  {priv_path}  (секрет!)\n  {out / 'com.tesla.3p.public-key.pem'}  (опубликовать на домене)")


if __name__ == "__main__":
    main()
