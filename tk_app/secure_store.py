"""Secure storage for secrets.

* A random Fernet (AES-128-CBC + HMAC-SHA256) master key lives in the OS credential
  store via `keyring` — on Windows this is Windows Credential Manager, protected by
  the user's Windows account (DPAPI).
* OAuth tokens are encrypted with that key and written to %APPDATA%\\TK\\tokens.bin.
  (Tesla JWTs are too large for a single Credential Manager entry, hence the split.)
* The developer-app client secret is short and is stored directly in keyring.

The Tesla account password never reaches this application at all: login happens
on auth.tesla.com in the user's browser.
"""
from __future__ import annotations

import json
from pathlib import Path

import keyring
from cryptography.fernet import Fernet, InvalidToken
from keyring.errors import KeyringError, PasswordDeleteError

from .config import data_dir

SERVICE = "TK-TeslaKey"
_MASTER_KEY = "master-key"
_CLIENT_SECRET = "client-secret"


class SecureStoreError(Exception):
    pass


class SecureStore:
    def __init__(self, directory: Path | None = None):
        self._path = (directory or data_dir()) / "tokens.bin"

    # ---- master key -------------------------------------------------------
    def _fernet(self, create: bool) -> Fernet | None:
        try:
            key = keyring.get_password(SERVICE, _MASTER_KEY)
            if not key:
                if not create:
                    return None
                key = Fernet.generate_key().decode("ascii")
                keyring.set_password(SERVICE, _MASTER_KEY, key)
            return Fernet(key.encode("ascii"))
        except KeyringError as exc:
            raise SecureStoreError(f"Системное хранилище учётных данных недоступно: {exc}") from exc

    # ---- tokens -----------------------------------------------------------
    def save_tokens(self, tokens: dict) -> None:
        fernet = self._fernet(create=True)
        blob = fernet.encrypt(json.dumps(tokens).encode("utf-8"))
        tmp = self._path.with_suffix(".tmp")
        tmp.write_bytes(blob)
        tmp.replace(self._path)

    def load_tokens(self) -> dict | None:
        if not self._path.exists():
            return None
        fernet = self._fernet(create=False)
        if fernet is None:
            return None
        try:
            return json.loads(fernet.decrypt(self._path.read_bytes()).decode("utf-8"))
        except (InvalidToken, ValueError, OSError):
            # Tampered or from another Windows user — treat as logged out
            return None

    def clear_tokens(self) -> None:
        try:
            if self._path.exists():
                # Overwrite before deleting so the ciphertext isn't trivially recoverable
                self._path.write_bytes(b"\0" * self._path.stat().st_size)
                self._path.unlink()
        except OSError:
            pass
        try:
            keyring.delete_password(SERVICE, _MASTER_KEY)
        except (PasswordDeleteError, KeyringError):
            pass

    # ---- client secret ----------------------------------------------------
    def save_client_secret(self, secret: str) -> None:
        try:
            if secret:
                keyring.set_password(SERVICE, _CLIENT_SECRET, secret)
            else:
                keyring.delete_password(SERVICE, _CLIENT_SECRET)
        except PasswordDeleteError:
            pass
        except KeyringError as exc:
            raise SecureStoreError(str(exc)) from exc

    def load_client_secret(self) -> str:
        try:
            return keyring.get_password(SERVICE, _CLIENT_SECRET) or ""
        except KeyringError:
            return ""
