"""Rate limiting simple en memoria para /investigate.

Ventana deslizante de una hora, por IP y global. En memoria a propósito:
un solo worker de uvicorn en el MVP; persistencia/Redis es roadmap.
Los límites se leen de env al importar: RATE_LIMIT_PER_IP_HOUR (default 10)
y RATE_LIMIT_GLOBAL_HOUR (default 40).
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque

from fastapi import HTTPException, Request

WINDOW_SECONDS = 3600.0
PER_IP_PER_HOUR = int(os.environ.get("RATE_LIMIT_PER_IP_HOUR", "10"))
GLOBAL_PER_HOUR = int(os.environ.get("RATE_LIMIT_GLOBAL_HOUR", "40"))
# Intentos de registro/login por IP y por hora. Es la defensa contra fuerza
# bruta de contraseñas: Argon2 encarece cada intento, esto acota cuántos hay.
AUTH_ATTEMPTS_PER_IP_HOUR = int(os.environ.get("AUTH_ATTEMPTS_PER_IP_HOUR", "20"))

_lock = threading.Lock()
_per_ip: dict[str, deque[float]] = {}
_global: deque[float] = deque()
_auth_per_ip: dict[str, deque[float]] = {}


def reset() -> None:
    """Limpia el estado (solo tests)."""
    with _lock:
        _per_ip.clear()
        _global.clear()
        _auth_per_ip.clear()


def client_ip(request: Request) -> str:
    """IP del cliente, honrando X-Forwarded-For (primer salto) tras el túnel/proxy."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _prune(dq: deque[float], now: float) -> None:
    while dq and now - dq[0] > WINDOW_SECONDS:
        dq.popleft()


def _minutes_until_slot(dq: deque[float], now: float) -> int:
    if not dq:  # límite configurado en 0: no hay slot que esperar, pero no crashear
        return 60
    return max(1, int((WINDOW_SECONDS - (now - dq[0])) // 60) + 1)


def check_rate_limit(request: Request) -> None:
    """Dependency de FastAPI: lanza 429 si la IP o el global agotaron la hora."""
    now = time.monotonic()
    ip = client_ip(request)
    with _lock:
        _prune(_global, now)
        dq = _per_ip.setdefault(ip, deque())
        _prune(dq, now)
        if len(_global) >= GLOBAL_PER_HOUR:
            raise HTTPException(
                status_code=429,
                detail=(
                    "TRAZA alcanzó su límite global de investigaciones por hora "
                    f"(protección de costos del MVP). Intenta de nuevo en ~{_minutes_until_slot(_global, now)} min."
                ),
            )
        if len(dq) >= PER_IP_PER_HOUR:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Esta conexión alcanzó el límite de {PER_IP_PER_HOUR} investigaciones por hora. "
                    f"Intenta de nuevo en ~{_minutes_until_slot(dq, now)} min."
                ),
            )
        dq.append(now)
        _global.append(now)


def check_auth_rate_limit(request: Request) -> None:
    """Dependency de /auth/register y /auth/login: 429 tras demasiados intentos.

    Cuenta intentos, no éxitos: un atacante probando contraseñas gasta el cupo
    aunque falle siempre (que es justo el caso que interesa frenar).
    """
    now = time.monotonic()
    ip = client_ip(request)
    with _lock:
        dq = _auth_per_ip.setdefault(ip, deque())
        _prune(dq, now)
        if len(dq) >= AUTH_ATTEMPTS_PER_IP_HOUR:
            raise HTTPException(
                status_code=429,
                detail=(
                    "Demasiados intentos de inicio de sesión desde esta conexión. "
                    f"Intenta de nuevo en ~{_minutes_until_slot(dq, now)} min."
                ),
            )
        dq.append(now)
