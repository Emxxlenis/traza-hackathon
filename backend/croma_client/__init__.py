"""Capa de transporte del cliente REST de Croma (Pista A).

Solo transporte: settings, rutas candidatas (UNVERIFIED), cliente async con
reintentos, excepciones tipadas y envelope de provenance. Nada aquí interpreta
la estructura de los payloads de Croma.
"""

from croma_client.client import CromaClient
from croma_client.config import CromaSettings, load_settings
from croma_client.endpoints import ENDPOINTS, EndpointSpec, resolve_endpoint
from croma_client.envelope import RawResponse
from croma_client.exceptions import (
    CromaAPIError,
    CromaAuthError,
    CromaConfigError,
    CromaError,
    CromaNotFound,
    CromaRateLimited,
    CromaUnavailable,
)

__all__ = [
    "ENDPOINTS",
    "CromaAPIError",
    "CromaAuthError",
    "CromaClient",
    "CromaConfigError",
    "CromaError",
    "CromaNotFound",
    "CromaRateLimited",
    "CromaSettings",
    "CromaUnavailable",
    "EndpointSpec",
    "RawResponse",
    "load_settings",
    "resolve_endpoint",
]
