"""Hash de contraseñas con Argon2id.

Parámetros explícitos (m=19 MiB, t=2, p=1): el mínimo que recomienda OWASP
para Argon2id y que cabe en una instancia chica. Los defaults de la librería
(64 MiB, p=4) tumbarían un contenedor de 512 MB con logins concurrentes.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

_hasher = PasswordHasher(time_cost=2, memory_cost=19_456, parallelism=1)

# Hash de descarte: verificar contra él cuando el email no existe cuesta lo
# mismo que verificar uno real, así el tiempo de respuesta no delata qué
# correos están registrados.
_DUMMY_HASH = _hasher.hash("contraseña-que-no-existe")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """True si la contraseña corresponde. Con hash None, quema el mismo tiempo."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password)
    except Argon2Error:
        return False
