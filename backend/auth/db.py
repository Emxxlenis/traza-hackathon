"""Conexión a la base de datos de cuentas.

Motor agnóstico a propósito: `DATABASE_URL` decide el backend real.
- Sin variable (dev/tests): SQLite local, cero setup.
- Producción: Postgres administrado (Neon/Render). El disco de Render free es
  EFÍMERO — SQLite ahí perdería todas las cuentas en cada redeploy y en cada
  arranque tras el spin-down, así que producción exige Postgres.

Es la única pieza que conoce el motor; el resto del paquete habla SQLAlchemy.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import dotenv_values
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./traza-auth.db"

# Parámetros de conexión que asyncpg NO acepta en la URL (los emite el
# connection string que copias de Neon). Se traducen a connect_args.
_PG_URL_ONLY_PARAMS = {"sslmode", "channel_binding", "options"}


class Base(DeclarativeBase):
    """Base declarativa de las tablas de cuentas."""


def normalize_database_url(raw: str) -> tuple[str, dict]:
    """Devuelve (url_para_sqlalchemy, connect_args).

    Acepta tal cual el connection string que dan Neon/Render/Supabase
    (`postgresql://…?sslmode=require`) y lo traduce al driver async:
    esquema `postgresql+asyncpg`, sin los parámetros que asyncpg rechaza.
    """
    parts = urlsplit(raw)
    scheme = parts.scheme
    connect_args: dict = {}

    if scheme in {"postgres", "postgresql"} or scheme.startswith("postgresql+"):
        if "+" not in scheme:
            scheme = "postgresql+asyncpg"
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
        kept = [(k, v) for k, v in query if k.lower() not in _PG_URL_ONLY_PARAMS]
        dropped = {k.lower(): v for k, v in query if k.lower() in _PG_URL_ONLY_PARAMS}
        # Neon exige TLS; asyncpg lo pide por connect_args, no por la URL.
        if dropped.get("sslmode", "").lower() not in {"", "disable", "allow"}:
            connect_args["ssl"] = True
        parts = parts._replace(scheme=scheme, query=urlencode(kept))
        return urlunsplit(parts), connect_args

    if scheme == "sqlite":
        # Reemplazo textual del esquema, NO urlunsplit: en sqlite:///ruta el
        # netloc es vacío y el round-trip lo colapsa a sqlite:/ruta.
        return "sqlite+aiosqlite" + raw[len("sqlite") :], connect_args

    return raw, connect_args


def database_url() -> str:
    """URL de la base: variable de entorno, si no el .env de la raíz, si no SQLite.

    El .env también cuenta porque es donde el proyecto pone su configuración
    local (igual que las claves de Croma); si solo mirara os.environ, poner
    DATABASE_URL ahí caería a SQLite sin avisar.
    """
    from_env = os.environ.get("DATABASE_URL")
    if from_env:
        return from_env
    return _url_from_env_file() or DEFAULT_DATABASE_URL


# Raíz del repo: db.py vive en backend/auth/, subimos dos niveles.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
_env_file_url: str | None = None
_env_file_read = False


def _url_from_env_file() -> str | None:
    """DATABASE_URL del .env de la raíz. Se lee una vez: el archivo no cambia
    en caliente y esto lo consulta cada /health."""
    global _env_file_url, _env_file_read
    if not _env_file_read:
        _env_file_read = True
        _env_file_url = dotenv_values(_ENV_FILE).get("DATABASE_URL") or None
    return _env_file_url


def is_persistent() -> bool:
    """False cuando las cuentas viven en SQLite (efímero en Render free)."""
    return not database_url().startswith("sqlite")


def check_production_storage() -> None:
    """Aborta el arranque si un despliegue real quedaría con cuentas efímeras.

    Render define RENDER=true en sus instancias y redespliega solo con cada
    push. Sin este freno, olvidar DATABASE_URL publicaría un sitio donde la
    gente crea cuentas que desaparecen al primer reinicio — y nadie se entera
    hasta que un usuario no puede volver a entrar. Fallar aquí hace que Render
    conserve el despliegue anterior, que sí funciona.
    """
    if os.environ.get("RENDER") and not is_persistent():
        raise RuntimeError(
            "DATABASE_URL no está definida: las cuentas quedarían en SQLite y se borrarían "
            "en cada redeploy y en cada arranque tras el spin-down. Configura una base "
            "Postgres (Neon/Render) antes de desplegar con cuentas activas."
        )


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Motor perezoso: los tests pueden apuntar DATABASE_URL antes del primer uso."""
    global _engine, _sessionmaker
    if _engine is None:
        url, connect_args = normalize_database_url(database_url())
        _engine = create_async_engine(url, connect_args=connect_args, pool_pre_ping=True)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def dispose_engine() -> None:
    """Cierra el pool y olvida el motor (shutdown y aislamiento entre tests)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def init_db() -> None:
    """Crea las tablas si faltan. Idempotente: dos tablas, sin migraciones."""
    from auth import models  # noqa: F401  (registra las tablas en Base.metadata)

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncIterator[AsyncSession]:
    """Dependency de FastAPI: una sesión de base de datos por request."""
    async with get_sessionmaker()() as session:
        yield session
