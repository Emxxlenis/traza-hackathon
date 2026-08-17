"""Fixtures compartidas.

`bypass_auth` existe porque /investigate quedó detrás de una cuenta: los tests
de rate limiting, streaming y wiring HTTP no son sobre autenticación y no
deberían montar una base de datos para seguir probando lo suyo. Los tests que
SÍ prueban el login (test_auth.py) no la usan: ahí el gate es el sujeto.
"""

from __future__ import annotations

import pytest

import app.main as app_main
from auth.api import require_user
from auth.models import User


@pytest.fixture
def bypass_auth():
    """Hace pasar los endpoints protegidos como si hubiera sesión abierta."""
    fake = User(id="test-user", email="tester@ejemplo.co", password_hash="x")
    app_main.app.dependency_overrides[require_user] = lambda: fake
    yield fake
    app_main.app.dependency_overrides.pop(require_user, None)
