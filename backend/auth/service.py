"""Reglas de cuentas: registrar, autenticar, abrir y cerrar sesión.

Sin efectos HTTP: la capa de API traduce estos resultados a respuestas y
cookies. Los errores son excepciones tipadas para que el endpoint elija el
mensaje que ve el usuario.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets
import uuid

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.models import Session, User, utcnow
from auth.passwords import hash_password, verify_password

SESSION_TTL = dt.timedelta(days=30)
MIN_PASSWORD_LENGTH = 8


class EmailAlreadyRegistered(Exception):
    """Ese correo ya tiene cuenta."""


class InvalidCredentials(Exception):
    """Email inexistente o contraseña incorrecta (indistinguibles a propósito)."""


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def register_user(db: AsyncSession, email: str, password: str) -> User:
    """Crea la cuenta. La unicidad la garantiza el índice, no una consulta previa.

    Consultar-y-luego-insertar tiene una carrera entre ambos pasos; dos
    registros simultáneos del mismo correo la ganarían los dos.
    """
    user = User(
        id=str(uuid.uuid4()),
        email=normalize_email(email),
        password_hash=hash_password(password),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise EmailAlreadyRegistered from exc
    return user


async def authenticate(db: AsyncSession, email: str, password: str) -> User:
    """Devuelve el usuario si las credenciales son válidas."""
    result = await db.execute(select(User).where(User.email == normalize_email(email)))
    user = result.scalar_one_or_none()
    # Se verifica SIEMPRE, incluso sin usuario: responder rápido cuando el
    # correo no existe convertiría el login en un detector de cuentas.
    ok = verify_password(user.password_hash if user else None, password)
    if not user or not ok:
        raise InvalidCredentials
    return user


async def open_session(db: AsyncSession, user: User) -> str:
    """Abre sesión y devuelve el token en claro (solo aquí existe sin hashear)."""
    token = secrets.token_urlsafe(32)
    db.add(
        Session(
            token_hash=_token_hash(token),
            user_id=user.id,
            expires_at=utcnow() + SESSION_TTL,
        )
    )
    await db.commit()
    return token


async def user_for_token(db: AsyncSession, token: str) -> User | None:
    """Usuario dueño de la sesión, o None si el token no existe o venció."""
    result = await db.execute(
        select(Session).where(Session.token_hash == _token_hash(token))
    )
    session = result.scalar_one_or_none()
    if session is None:
        return None
    expires_at = session.expires_at
    if expires_at.tzinfo is None:  # SQLite devuelve naive; se asume UTC
        expires_at = expires_at.replace(tzinfo=dt.UTC)
    if expires_at <= utcnow():
        await close_session(db, token)
        return None
    return await db.get(User, session.user_id)


async def close_session(db: AsyncSession, token: str) -> None:
    """Revoca la sesión. Idempotente: cerrar dos veces no es error."""
    await db.execute(delete(Session).where(Session.token_hash == _token_hash(token)))
    await db.commit()
