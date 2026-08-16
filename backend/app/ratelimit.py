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

_lock = threading.Lock()
_per_ip: dict[str, deque[float]] = {}
_global: deque[float] = deque()


def reset() -> None:
    """Limpia el estado (solo tests)."""
    with _lock:
        _per_ip.clear()
        _global.clear()


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
