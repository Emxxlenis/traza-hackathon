"""Excepciones tipadas del cliente Croma.

Jerarquía plana y explícita para que las capas superiores (agente / Evidence
Layer) puedan decidir por tipo sin inspeccionar strings.
"""

from __future__ import annotations


class CromaError(Exception):
    """Base de todas las excepciones del cliente Croma."""


class CromaConfigError(CromaError):
    """Configuración faltante o inválida (.env incompleto, scheme desconocido, etc.)."""


class CromaAPIError(CromaError):
    """Error devuelto por la API de Croma (o fallo de transporte agotados los reintentos).

    Atributos:
        status_code: código HTTP si hubo respuesta, None si fue error de red.
        endpoint: nombre lógico del endpoint invocado.
        url: URL final de la petición (si se conoce).
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        endpoint: str | None = None,
        url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.endpoint = endpoint
        self.url = url


class CromaAuthError(CromaAPIError):
    """401/403 — API key inválida, ausente o sin permisos. Nunca se reintenta."""


class CromaNotFound(CromaAPIError):
    """404 — recurso o ruta inexistente. Nunca se reintenta.

    OJO: con rutas UNVERIFIED un 404 puede significar "la ruta candidata no es
    la real", no necesariamente "la entidad no existe".
    """


class CromaRateLimited(CromaAPIError):
    """429 — límite de tasa alcanzado. No se reintenta automáticamente."""


class CromaUnavailable(CromaAPIError):
    """5xx o error de red/timeout tras agotar los reintentos."""
