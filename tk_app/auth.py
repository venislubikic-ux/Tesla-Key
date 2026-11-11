"""Tesla OAuth 2.0 (Fleet API third-party tokens) — authorization code flow with PKCE.

The user signs in on auth.tesla.com in their own browser; Tesla redirects back to a
loopback HTTP server started by this app (e.g. http://localhost:8765/callback).
The password is never seen by TK.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from .config import AppConfig
from .secure_store import SecureStore

AUTHORIZE_URL = "https://auth.tesla.com/oauth2/v3/authorize"
TOKEN_URL = "https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token"
SCOPES = "openid offline_access user_data vehicle_device_data vehicle_cmds vehicle_charging_cmds"
HTTP_TIMEOUT = 20


class AuthError(Exception):
    pass


class AuthCancelled(AuthError):
    pass


class ReauthRequired(AuthError):
    """Refresh token rejected / missing — the user must sign in again."""


_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>TK</title>
<style>body{{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
background:#000;color:#fff;font-family:'Segoe UI',system-ui,sans-serif}}
.c{{text-align:center}}h1{{font-weight:300;letter-spacing:.5em;font-size:56px;margin:0 0 8px}}
p{{color:#8a8a8a;letter-spacing:.08em}}</style></head>
<body><div class="c"><h1>TK</h1><p>{msg}</p></div></body></html>"""


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode("ascii")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge.rstrip(b"=").decode("ascii")


class _CallbackServer(HTTPServer):
    expected_path: str = "/callback"
    result: dict | None = None


class _CallbackHandler(BaseHTTPRequestHandler):
    server: _CallbackServer

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != self.server.expected_path:
            self.send_response(404)
            self.end_headers()
            return
        params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        self.server.result = params
        ok = "code" in params and "error" not in params
        msg = ("Авторизация завершена. Можно вернуться в приложение TK."
               if ok else "Авторизация не выполнена. Вернитесь в приложение TK.")
        body = _PAGE.format(msg=msg).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence console logging
        pass


class BrowserLogin:
    """Runs the full browser sign-in. Call run() from a worker thread; cancel() from any thread."""

    def __init__(self, config: AppConfig, client_secret: str):
        self.config = config
        self.client_secret = client_secret
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self, timeout: float = 300) -> dict:
        redirect = urlparse(self.config.redirect_uri)
        if redirect.scheme != "http" or redirect.hostname not in ("localhost", "127.0.0.1"):
            raise AuthError("Redirect URI должен быть локальным, например http://localhost:8765/callback")
        port = redirect.port or 80

        try:
            server = _CallbackServer(("127.0.0.1", port), _CallbackHandler)
        except OSError as exc:
            raise AuthError(f"Порт {port} занят. Укажите другой порт в Redirect URI "
                            f"(и добавьте его в настройках приложения на developer.tesla.com).") from exc
        server.expected_path = redirect.path or "/"
        server.timeout = 0.5

        state = secrets.token_urlsafe(24)
        verifier, challenge = _pkce_pair()
        url = AUTHORIZE_URL + "?" + urlencode({
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "scope": SCOPES,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "prompt_missing_scopes": "true",
        })

        try:
            if not webbrowser.open(url):
                raise AuthError("Не удалось открыть браузер.")
            deadline = time.monotonic() + timeout
            while server.result is None:
                if self._cancel.is_set():
                    raise AuthCancelled("Вход отменён.")
                if time.monotonic() > deadline:
                    raise AuthError("Время ожидания авторизации истекло.")
                server.handle_request()
        finally:
            server.server_close()

        params = server.result
        if params.get("state") != state:
            raise AuthError("Ответ авторизации не прошёл проверку (state). Попробуйте ещё раз.")
        if "error" in params:
            desc = params.get("error_description") or params["error"]
            raise AuthError(f"Tesla отклонила авторизацию: {desc}")
        code = params.get("code")
        if not code:
            raise AuthError("Tesla не вернула код авторизации.")
        return self._exchange(code, verifier)

    def _exchange(self, code: str, verifier: str) -> dict:
        data = {
            "grant_type": "authorization_code",
            "client_id": self.config.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": self.config.redirect_uri,
            "audience": self.config.fleet_base_url,
            "scope": SCOPES,
        }
        try:
            r = requests.post(TOKEN_URL, data=data, timeout=HTTP_TIMEOUT)
        except requests.RequestException as exc:
            raise AuthError(f"Нет связи с сервером авторизации Tesla: {exc}") from exc
        if r.status_code != 200:
            raise AuthError(f"Не удалось получить токен ({r.status_code}): {_err_text(r)}")
        return normalize_tokens(r.json())


def normalize_tokens(payload: dict, previous: dict | None = None) -> dict:
    tokens = {
        "access_token": payload["access_token"],
        # Tesla rotates refresh tokens — always keep the newest one
        "refresh_token": payload.get("refresh_token") or (previous or {}).get("refresh_token"),
        "expires_at": time.time() + int(payload.get("expires_in", 28800)),
        "scope": payload.get("scope", ""),
    }
    if not tokens["refresh_token"]:
        raise AuthError("Tesla не выдала refresh token (нужен scope offline_access).")
    return tokens


def _err_text(r: requests.Response) -> str:
    try:
        j = r.json()
        return j.get("error_description") or j.get("error") or r.text[:300]
    except ValueError:
        return r.text[:300]


class TokenManager:
    """Thread-safe access-token provider with automatic refresh and persistence."""

    def __init__(self, store: SecureStore, config: AppConfig):
        self.store = store
        self.config = config
        self._lock = threading.Lock()
        self._tokens: dict | None = store.load_tokens()

    @property
    def is_authenticated(self) -> bool:
        return bool(self._tokens and self._tokens.get("refresh_token"))

    def set_tokens(self, tokens: dict) -> None:
        with self._lock:
            self._tokens = tokens
            self.store.save_tokens(tokens)

    def clear(self) -> None:
        with self._lock:
            self._tokens = None
            self.store.clear_tokens()

    def access_token(self) -> str:
        with self._lock:
            if not self._tokens:
                raise ReauthRequired("Автомобиль не подключён.")
            if time.time() > self._tokens.get("expires_at", 0) - 120:
                self._refresh_locked()
            return self._tokens["access_token"]

    def force_refresh(self) -> None:
        with self._lock:
            self._refresh_locked()

    def _refresh_locked(self) -> None:
        if not self._tokens or not self._tokens.get("refresh_token"):
            raise ReauthRequired("Требуется повторный вход в аккаунт Tesla.")
        data = {
            "grant_type": "refresh_token",
            "client_id": self.config.client_id,
            "refresh_token": self._tokens["refresh_token"],
        }
        try:
            r = requests.post(TOKEN_URL, data=data, timeout=HTTP_TIMEOUT)
        except requests.RequestException as exc:
            raise AuthError(f"Нет связи с сервером авторизации Tesla: {exc}") from exc
        if r.status_code in (400, 401, 403):
            self._tokens = None
            self.store.clear_tokens()
            raise ReauthRequired("Сессия Tesla истекла или доступ был отозван. Подключите автомобиль снова.")
        if r.status_code != 200:
            raise AuthError(f"Ошибка обновления токена ({r.status_code}): {_err_text(r)}")
        self._tokens = normalize_tokens(r.json(), previous=self._tokens)
        self.store.save_tokens(self._tokens)
