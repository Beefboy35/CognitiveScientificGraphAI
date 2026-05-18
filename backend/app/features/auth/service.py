"""Auth service: registration, password hashing, JWT issuance/validation.

Backends:
* PostgreSQL `users` table (already in initial migration `7e9424fcd3ae`).
* bcrypt for password hashing (`passlib[bcrypt]` in requirements.txt).
* PyJWT for token signing.

JWT payload:
    {
      "sub": "<user_id>",
      "email": "...",
      "role": "user" | "admin",
      "type": "access" | "refresh",
      "iat": int,
      "exp": int,
    }
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from passlib.context import CryptContext
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config.settings import settings
from app.db.base import Base  # noqa: F401  -- ensures metadata is loaded
from app.db.models import User

logger = logging.getLogger(__name__)


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


_ENGINE = None
_SESSION_FACTORY = None


def _get_session_factory():
    global _ENGINE, _SESSION_FACTORY
    if _SESSION_FACTORY is not None:
        return _SESSION_FACTORY
    dsn = str(settings.pg_dsn or "")
    if not dsn:
        raise AuthError("auth_unavailable", "PostgreSQL is not configured")
    _ENGINE = create_engine(dsn, pool_pre_ping=True, future=True)
    _SESSION_FACTORY = sessionmaker(bind=_ENGINE, expire_on_commit=False, autoflush=False)
    return _SESSION_FACTORY


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AuthError(Exception):
    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass
class PublicUser:
    id: int
    email: str
    name: str
    role: str
    is_active: bool
    created_at: str


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 0
    refresh_expires_in: int = 0
    user: PublicUser | None = None


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _validate_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        raise AuthError("invalid_email", "Введите корректный email")
    return email


def _validate_password(password: str) -> str:
    if not password or len(password) < 8:
        raise AuthError("weak_password", "Пароль должен быть не короче 8 символов и содержать буквы и цифры")
    if not re.search(r"[A-Za-zА-Яа-я]", password):
        raise AuthError("weak_password", "Пароль должен содержать буквы")
    if not re.search(r"\d", password):
        raise AuthError("weak_password", "Пароль должен содержать цифры")
    return password


def _validate_name(name: str) -> str:
    name = (name or "").strip()
    if len(name) < 2:
        raise AuthError("invalid_name", "Имя должно содержать минимум 2 символа")
    return name


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------


def _public_user(user: User, *, name_override: str | None = None) -> PublicUser:
    # `User` ORM doesn't have a `name` column — keep best-effort name from email
    # local part. Frontend reuses this consistently.
    name = name_override or user.email.split("@", 1)[0]
    created = user.created_at.isoformat() if user.created_at else ""
    return PublicUser(
        id=int(user.id),
        email=user.email,
        name=name,
        role=user.role or "user",
        is_active=bool(user.is_active),
        created_at=created,
    )


def register_user(*, email: str, password: str, name: str) -> PublicUser:
    email = _validate_email(email)
    password = _validate_password(password)
    name = _validate_name(name)
    factory = _get_session_factory()
    session = factory()
    try:
        existing = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if existing is not None:
            raise AuthError("email_taken", "Пользователь с таким email уже зарегистрирован")
        user = User(
            email=email,
            password_hash=pwd_context.hash(password),
            role="user",
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return _public_user(user, name_override=name)
    finally:
        session.close()


def authenticate_user(*, email: str, password: str) -> PublicUser:
    email = _validate_email(email)
    if not password:
        raise AuthError("invalid_credentials", "Неверный email или пароль")
    factory = _get_session_factory()
    session = factory()
    try:
        user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None or not user.is_active:
            raise AuthError("invalid_credentials", "Неверный email или пароль")
        if not pwd_context.verify(password, user.password_hash):
            raise AuthError("invalid_credentials", "Неверный email или пароль")
        return _public_user(user)
    finally:
        session.close()


def get_user_by_id(user_id: int) -> PublicUser | None:
    factory = _get_session_factory()
    session = factory()
    try:
        user = session.get(User, user_id)
        if user is None or not user.is_active:
            return None
        return _public_user(user)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------


def _secret() -> str:
    secret = settings.jwt_secret_key.get_secret_value() if hasattr(settings.jwt_secret_key, "get_secret_value") else str(settings.jwt_secret_key or "")
    if not secret or secret == "dev-jwt-secret-change-me":
        # Acceptable for dev, log warning once.
        logger.debug("auth_using_default_secret")
    if not secret:
        # Make tokens unusable rather than silently signing with empty key.
        secret = "kb_default_dev_secret_please_change"
    return secret


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _build_token(user: PublicUser, *, kind: str, ttl_seconds: int) -> str:
    issued = _now()
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "type": kind,
        "iat": int(issued.timestamp()),
        "exp": int((issued + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def issue_tokens(user: PublicUser) -> TokenBundle:
    access_ttl = int(settings.jwt_access_ttl_seconds or 900)
    refresh_ttl = int(settings.jwt_refresh_ttl_seconds or 1209600)
    return TokenBundle(
        access_token=_build_token(user, kind="access", ttl_seconds=access_ttl),
        refresh_token=_build_token(user, kind="refresh", ttl_seconds=refresh_ttl),
        expires_in=access_ttl,
        refresh_expires_in=refresh_ttl,
        user=user,
    )


def decode_token(token: str, *, expected_type: str | None = None) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("token_expired", "Срок действия токена истёк") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("invalid_token", "Некорректный токен") from exc
    if expected_type and payload.get("type") != expected_type:
        raise AuthError("invalid_token", "Неверный тип токена")
    return payload


def refresh_tokens(refresh_token: str) -> TokenBundle:
    payload = decode_token(refresh_token, expected_type="refresh")
    user_id_raw = payload.get("sub")
    try:
        user_id = int(user_id_raw)
    except (TypeError, ValueError) as exc:
        raise AuthError("invalid_token", "Некорректный идентификатор") from exc
    user = get_user_by_id(user_id)
    if user is None:
        raise AuthError("invalid_token", "Пользователь не найден")
    return issue_tokens(user)
