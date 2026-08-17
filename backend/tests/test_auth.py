"""Tests de cuentas: registro, sesión y el gate de /investigate.

Aquí el sujeto ES el login, así que no se usa `bypass_auth`: cada test monta
una base SQLite temporal y habla por HTTP como lo haría el navegador.
El TestClient se usa como context manager a propósito — así corre el lifespan
de la app, que es quien crea las tablas y suelta el pool al terminar.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
import app.ratelimit as rl
from auth import db as auth_db
from auth import service
from auth.api import COOKIE_NAME
from auth.db import check_production_storage, normalize_database_url
from evidence.models import CaseFile

EMAIL = "persona@ejemplo.co"
PASSWORD = "contrasena-larga-1"


@pytest.fixture(autouse=True)
def _temp_database(tmp_path, monkeypatch):
    """Cuentas en una base propia por test; nada se hereda entre tests.

    También apunta el .env de respaldo a un archivo inexistente: si no, un
    DATABASE_URL en el .env de quien desarrolla cambiaría el resultado de los
    tests según su máquina.
    """
    monkeypatch.setattr(auth_db, "_ENV_FILE", tmp_path / "sin.env")
    monkeypatch.setattr(auth_db, "_env_file_read", False)
    monkeypatch.setattr(auth_db, "_env_file_url", None)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path/'auth.db'}")
    rl.reset()
    yield
    rl.reset()


@pytest.fixture
def fake_investigation(monkeypatch):
    """Evita el LLM y Croma: estos tests miran el gate, no la investigación."""

    async def fake_investigate(question: str, candidate_id: str | None = None, **_: object):
        return CaseFile(
            question=question,
            status="partial",
            entities=[],
            sources_consulted=[],
            findings=[],
            unknowns=["expediente de prueba"],
            next_steps=[],
        )

    monkeypatch.setattr(app_main, "investigate", fake_investigate)


def _register(client: TestClient, email: str = EMAIL, password: str = PASSWORD):
    return client.post("/auth/register", json={"email": email, "password": password})


def _login(client: TestClient, email: str = EMAIL, password: str = PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


# --- registro ---------------------------------------------------------------


def test_register_creates_account_and_opens_session() -> None:
    with TestClient(app_main.app) as client:
        resp = _register(client)
        assert resp.status_code == 201
        assert resp.json() == {"email": EMAIL}
        assert COOKIE_NAME in resp.cookies
        # La sesión queda abierta: registrarse no obliga a loguearse aparte.
        assert client.get("/auth/me").json() == {"email": EMAIL}


def test_session_cookie_is_httponly_and_not_readable_by_scripts() -> None:
    with TestClient(app_main.app) as client:
        resp = _register(client)
        set_cookie = resp.headers["set-cookie"].lower()
        assert "httponly" in set_cookie
        assert "samesite=lax" in set_cookie


def test_register_rejects_duplicate_email_ignoring_case() -> None:
    with TestClient(app_main.app) as client:
        assert _register(client).status_code == 201
        resp = _register(client, email=EMAIL.upper())
        assert resp.status_code == 409
        assert "ya tiene una cuenta" in resp.json()["detail"]


def test_register_rejects_short_password_and_invalid_email() -> None:
    with TestClient(app_main.app) as client:
        assert _register(client, password="corta").status_code == 422
        assert _register(client, email="no-es-un-correo").status_code == 422


# --- login ------------------------------------------------------------------


def test_login_with_valid_credentials_opens_session() -> None:
    with TestClient(app_main.app) as client:
        _register(client)
        client.post("/auth/logout")
        assert _login(client).status_code == 200
        assert client.get("/auth/me").json() == {"email": EMAIL}


def test_login_failures_do_not_reveal_whether_the_email_exists() -> None:
    with TestClient(app_main.app) as client:
        _register(client)
        client.post("/auth/logout")
        wrong_password = _login(client, password="otra-contrasena")
        unknown_email = _login(client, email="nadie@ejemplo.co")
        assert wrong_password.status_code == unknown_email.status_code == 401
        # Mismo texto en ambos: si difirieran, el login sería un detector de cuentas.
        assert wrong_password.json()["detail"] == unknown_email.json()["detail"]


def test_login_is_case_insensitive_on_email() -> None:
    with TestClient(app_main.app) as client:
        _register(client)
        client.post("/auth/logout")
        assert _login(client, email=EMAIL.upper()).status_code == 200


def test_too_many_attempts_from_one_ip_get_429(monkeypatch) -> None:
    monkeypatch.setattr(rl, "AUTH_ATTEMPTS_PER_IP_HOUR", 2)
    with TestClient(app_main.app) as client:
        assert _login(client, password="mala-contrasena").status_code == 401
        assert _login(client, password="mala-contrasena").status_code == 401
        blocked = _login(client, password="mala-contrasena")
        assert blocked.status_code == 429
        assert "Demasiados intentos" in blocked.json()["detail"]


# --- sesión -----------------------------------------------------------------


def test_logout_revokes_the_session() -> None:
    with TestClient(app_main.app) as client:
        _register(client)
        assert client.post("/auth/logout").status_code == 204
        assert client.get("/auth/me").status_code == 401
        # La cookie vieja tampoco sirve: la fila se borró del servidor.
        client.cookies.set(COOKIE_NAME, "cualquier-cosa")
        assert client.get("/auth/me").status_code == 401


def test_expired_session_stops_working(monkeypatch) -> None:
    monkeypatch.setattr(service, "SESSION_TTL", dt.timedelta(seconds=-1))
    with TestClient(app_main.app) as client:
        _register(client)
        assert client.get("/auth/me").status_code == 401


def test_unknown_token_is_rejected() -> None:
    with TestClient(app_main.app) as client:
        client.cookies.set(COOKIE_NAME, "token-inventado")
        assert client.get("/auth/me").status_code == 401


# --- el gate sobre /investigate --------------------------------------------


def test_investigate_requires_an_account(fake_investigation) -> None:
    with TestClient(app_main.app) as client:
        resp = client.post("/investigate", json={"question": "prueba"})
        assert resp.status_code == 401
        assert "iniciar sesión" in resp.json()["detail"]


def test_investigate_stream_requires_an_account(fake_investigation) -> None:
    with TestClient(app_main.app) as client:
        assert client.post("/investigate/stream", json={"question": "prueba"}).status_code == 401


def test_investigate_works_once_logged_in(fake_investigation) -> None:
    with TestClient(app_main.app) as client:
        _register(client)
        resp = client.post("/investigate", json={"question": "prueba"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "partial"


def test_rejected_requests_do_not_burn_investigation_quota(
    fake_investigation, monkeypatch
) -> None:
    """Sin cuenta no se gasta cupo: si no, cualquiera agotaría la cuota global."""
    monkeypatch.setattr(rl, "PER_IP_PER_HOUR", 1)
    monkeypatch.setattr(rl, "GLOBAL_PER_HOUR", 1)
    with TestClient(app_main.app) as client:
        for _ in range(3):
            assert client.post("/investigate", json={"question": "prueba"}).status_code == 401
        _register(client)
        assert client.post("/investigate", json={"question": "prueba"}).status_code == 200


def test_health_reports_that_accounts_are_required() -> None:
    with TestClient(app_main.app) as client:
        body = client.get("/health").json()
        assert body["auth_required"] is True
        # SQLite en los tests: la señal de "esto no sobrevive un redeploy".
        assert body["accounts_persistent"] is False


# --- URL de base de datos ---------------------------------------------------


def test_deploying_without_a_real_database_aborts_the_startup(monkeypatch) -> None:
    """Con cuentas efímeras es mejor no arrancar: Render conserva el despliegue previo."""
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        check_production_storage()


def test_deploying_with_postgres_is_allowed(monkeypatch) -> None:
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host/db")
    check_production_storage()  # no levanta


def test_sqlite_is_fine_outside_render(monkeypatch) -> None:
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    check_production_storage()  # desarrollo local: sin freno


def test_neon_connection_string_is_translated_to_the_async_driver() -> None:
    """El string que se copia de Neon trae parámetros que asyncpg rechaza."""
    url, connect_args = normalize_database_url(
        "postgresql://u:p@ep-x.neon.tech/traza?sslmode=require&channel_binding=require"
    )
    assert url.startswith("postgresql+asyncpg://")
    assert "sslmode" not in url and "channel_binding" not in url
    assert connect_args == {"ssl": True}


def test_postgres_scheme_alias_is_accepted() -> None:
    url, _ = normalize_database_url("postgres://u:p@host/db")
    assert url.startswith("postgresql+asyncpg://")


def test_sqlite_url_keeps_working_without_extras() -> None:
    url, connect_args = normalize_database_url("sqlite:///./traza-auth.db")
    assert url == "sqlite+aiosqlite:///./traza-auth.db"
    assert connect_args == {}
