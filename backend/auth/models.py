"""Tablas de cuentas: usuarios y sesiones activas.

Se guarda lo mínimo para saber quién investiga: email, hash de contraseña y
sesiones vigentes. Ni nombre, ni IP, ni historial de investigaciones — el
producto sigue sin persistir expedientes.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth.db import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Normalizado a minúsculas antes de escribir: el índice único es la
    # garantía de "un email = una cuenta" (SQLite y Postgres comparan
    # case-sensitive, así que la normalización no puede quedar en la consulta).
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    sessions: Mapped[list[Session]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Session(Base):
    """Sesión activa. Se guarda el HASH del token, nunca el token mismo.

    Un volcado de esta tabla no permite suplantar a nadie, igual que con las
    contraseñas. Token opaco (no JWT) para que cerrar sesión sea real:
    borrar la fila revoca el acceso en el acto.
    """

    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")
