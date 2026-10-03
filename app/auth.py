import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.config import BASE_DIR


DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = Path(os.getenv("AUTH_DB_PATH", DATA_DIR / "comiccraft.sqlite3"))
PASSWORD_ITERATIONS = 600_000


class SignedSessionMiddleware:
    def __init__(
        self,
        app,
        secret_key: str,
        cookie_name: str = "comiccraft_session",
        max_age: int = 60 * 60 * 24 * 14,
        secure: bool = False,
    ):
        self.app = app
        self.secret_key = secret_key.encode("utf-8")
        self.cookie_name = cookie_name
        self.max_age = max_age
        self.secure = secure

    def _decode_session(self, token: str) -> dict:
        try:
            encoded_data, issued_at, signature = token.split(".", 2)
            signed_value = f"{encoded_data}.{issued_at}"
            expected_signature = hmac.new(
                self.secret_key, signed_value.encode("ascii"), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(signature, expected_signature):
                return {}
            timestamp = int(issued_at)
            now = int(time.time())
            if timestamp > now or now - timestamp > self.max_age:
                return {}
            padded_data = encoded_data + "=" * (-len(encoded_data) % 4)
            session = json.loads(base64.urlsafe_b64decode(padded_data))
            return session if isinstance(session, dict) else {}
        except (ValueError, TypeError, json.JSONDecodeError):
            return {}

    def _encode_session(self, session: dict) -> str:
        encoded_data = base64.urlsafe_b64encode(
            json.dumps(session, separators=(",", ":")).encode("utf-8")
        ).rstrip(b"=").decode("ascii")
        issued_at = str(int(time.time()))
        signed_value = f"{encoded_data}.{issued_at}"
        signature = hmac.new(
            self.secret_key, signed_value.encode("ascii"), hashlib.sha256
        ).hexdigest()
        return f"{signed_value}.{signature}"

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        cookie_header = next(
            (value.decode("latin-1") for key, value in scope["headers"] if key == b"cookie"),
            "",
        )
        cookies = SimpleCookie()
        try:
            cookies.load(cookie_header)
        except Exception:
            cookies = SimpleCookie()
        cookie = cookies.get(self.cookie_name)
        token = cookie.value if cookie else ""
        session = self._decode_session(token) if token and len(token) <= 4096 else {}
        original_session = dict(session)
        scope["session"] = session

        async def send_with_session(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if session:
                    value = (
                        f"{self.cookie_name}={self._encode_session(session)}; Path=/; "
                        f"Max-Age={self.max_age}; HttpOnly; SameSite=Lax"
                    )
                    if self.secure:
                        value += "; Secure"
                    headers.append((b"set-cookie", value.encode("ascii")))
                elif original_session or token:
                    value = (
                        f"{self.cookie_name}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
                    )
                    if self.secure:
                        value += "; Secure"
                    headers.append((b"set-cookie", value.encode("ascii")))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_session)


def get_session_secret() -> str:
    configured_secret = os.getenv("SESSION_SECRET", "").strip()
    if configured_secret:
        return configured_secret

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    secret_path = DATA_DIR / ".session_secret"
    if not secret_path.exists():
        try:
            with secret_path.open("x", encoding="ascii") as secret_file:
                secret_file.write(secrets.token_urlsafe(48))
        except FileExistsError:
            pass
    return secret_path.read_text(encoding="ascii").strip()


def initialize_auth_database() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DATABASE_PATH, timeout=10) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def create_user(email: str, password: str) -> int:
    normalized_email = email.strip().casefold()
    password_hash = _hash_password(password)
    with sqlite3.connect(DATABASE_PATH, timeout=10) as connection:
        cursor = connection.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (normalized_email, password_hash),
        )
        return int(cursor.lastrowid)


def authenticate_user(email: str, password: str) -> dict | None:
    normalized_email = email.strip().casefold()
    with sqlite3.connect(DATABASE_PATH, timeout=10) as connection:
        connection.row_factory = sqlite3.Row
        user = connection.execute(
            "SELECT id, email, password_hash FROM users WHERE email = ?",
            (normalized_email,),
        ).fetchone()

    if user is None:
        _hash_password(password, salt=b"comiccraft-dummy")
        return None

    try:
        algorithm, iterations, salt_hex, expected_hex = user["password_hash"].split("$")
        if algorithm != "pbkdf2_sha256" or int(iterations) != PASSWORD_ITERATIONS:
            return None
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        ).hex()
    except (ValueError, TypeError):
        return None

    if not hmac.compare_digest(candidate, expected_hex):
        return None
    return {"id": int(user["id"]), "email": str(user["email"])}


def get_user(user_id: int) -> dict | None:
    with sqlite3.connect(DATABASE_PATH, timeout=10) as connection:
        connection.row_factory = sqlite3.Row
        user = connection.execute(
            "SELECT id, email FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if user is None:
        return None
    return {"id": int(user["id"]), "email": str(user["email"])}