"""Cliente async de transporte para la API de Croma.

Responsabilidad ÚNICA: llevar y traer bytes con reintentos y errores tipados.
CERO parsing de payloads — las respuestas viajan opacas dentro de RawResponse.

Política de reintentos:
  - Se reintenta SOLO en timeouts, errores de red y 5xx (máximo 3 intentos).
  - Nunca se reintenta un 4xx (auth, not found, rate limit, etc.).
  - Backoff exponencial: backoff_base * 2**(intento - 1) segundos.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Self

import httpx

from croma_client.config import CromaSettings, load_settings
from croma_client.endpoints import EndpointSpec, resolve_endpoint
from croma_client.envelope import RawResponse
from croma_client.exceptions import (
    CromaAPIError,
    CromaAuthError,
    CromaNotFound,
    CromaRateLimited,
    CromaUnavailable,
)

DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_BASE_SECONDS = 0.5


def _auth_headers(settings: CromaSettings) -> dict[str, str]:
    """Construye el header de auth según el scheme configurado.

    UNVERIFIED: no sabemos el mecanismo real de auth de Croma; ambos schemes
    son candidatos hasta que el humano lo confirme con la plataforma.
    """
    if settings.auth_scheme == "x-api-key":
        return {"X-API-Key": settings.api_key}
    return {"Authorization": f"Bearer {settings.api_key}"}


class CromaClient:
    """Cliente HTTP async sobre httpx.AsyncClient, con reintentos y errores tipados."""

    def __init__(
        self,
        settings: CromaSettings | None = None,
        *,
        timeout: float | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        backoff_base: float = DEFAULT_BACKOFF_BASE_SECONDS,
    ) -> None:
        """Crea el cliente.

        Args:
            settings: settings ya cargados; si es None se leen del .env de la raíz
                (lanza CromaConfigError con mensaje accionable si faltan valores).
            timeout: timeout total por petición en segundos (default: settings, 15s).
            max_attempts: intentos totales ante timeout/red/5xx (default 3).
            backoff_base: base del backoff exponencial en segundos (0 en tests).
        """
        self._settings = settings if settings is not None else load_settings()
        self._timeout = timeout if timeout is not None else self._settings.timeout_seconds
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base
        self._client = httpx.AsyncClient(
            base_url=self._settings.base_url,
            timeout=self._timeout,
            headers=_auth_headers(self._settings),
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Cierra el pool de conexiones subyacente."""
        await self._client.aclose()

    async def get(self, endpoint: str, params: dict[str, Any] | None = None) -> RawResponse:
        """GET genérico contra un endpoint (nombre corto del registro o ruta).

        Devuelve un RawResponse con el payload OPACO. Lanza excepciones tipadas
        según el resultado (ver croma_client.exceptions).
        """
        spec = resolve_endpoint(endpoint)
        response: httpx.Response | None = None
        last_network_error: httpx.TransportError | None = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._client.get(spec.path, params=params)
            except httpx.TransportError as exc:  # incluye timeouts (httpx.TimeoutException)
                last_network_error = exc
                response = None
                if attempt < self._max_attempts:
                    await asyncio.sleep(self._backoff_base * 2 ** (attempt - 1))
                    continue
                break
            if response.status_code >= 500:
                # 5xx: reintentable hasta agotar intentos.
                if attempt < self._max_attempts:
                    await asyncio.sleep(self._backoff_base * 2 ** (attempt - 1))
                    continue
                break
            # Cualquier otro código (2xx/3xx/4xx) corta el loop: nunca se reintenta.
            break

        if response is None:
            raise CromaUnavailable(
                f"Croma inalcanzable tras {self._max_attempts} intentos "
                f"({type(last_network_error).__name__}: {last_network_error}).",
                endpoint=spec.name,
            ) from last_network_error

        self._raise_for_status(response, spec)
        return self._build_envelope(response, spec)

    def _raise_for_status(self, response: httpx.Response, spec: EndpointSpec) -> None:
        """Mapea códigos HTTP de error a excepciones tipadas. Sin tocar el payload."""
        status = response.status_code
        url = str(response.request.url)
        if status in (401, 403):
            raise CromaAuthError(
                f"Auth rechazada por Croma ({status}) en {spec.name}. Revisa CROMA_API_KEY "
                "y CROMA_AUTH_SCHEME (el scheme real es UNVERIFIED: prueba el otro).",
                status_code=status,
                endpoint=spec.name,
                url=url,
            )
        if status == 404:
            raise CromaNotFound(
                f"404 en {spec.name} ({spec.path}). Ojo: la ruta es UNVERIFIED — puede "
                "ser ruta incorrecta y no un recurso inexistente.",
                status_code=status,
                endpoint=spec.name,
                url=url,
            )
        if status == 429:
            raise CromaRateLimited(
                f"Rate limit de Croma alcanzado (429) en {spec.name}.",
                status_code=status,
                endpoint=spec.name,
                url=url,
            )
        if status >= 500:
            raise CromaUnavailable(
                f"Croma respondió {status} en {spec.name} tras {self._max_attempts} intentos.",
                status_code=status,
                endpoint=spec.name,
                url=url,
            )
        if status >= 400:
            raise CromaAPIError(
                f"Croma respondió {status} en {spec.name}.",
                status_code=status,
                endpoint=spec.name,
                url=url,
            )

    @staticmethod
    def _build_envelope(response: httpx.Response, spec: EndpointSpec) -> RawResponse:
        """Empaqueta la respuesta como provenance, sin interpretar el payload."""
        body_text = response.text
        try:
            payload: dict[str, Any] | list[Any] = response.json()
        except (json.JSONDecodeError, ValueError):
            # UNVERIFIED: asumimos JSON, pero si llega otra cosa la preservamos
            # verbatim en vez de perderla. Clave reservada, no estructura de Croma.
            payload = {"_non_json_body": body_text}
        return RawResponse(
            source=spec.source,
            endpoint=spec.path,
            url=str(response.request.url),
            status_code=response.status_code,
            fetched_at=datetime.now(UTC).isoformat(),
            payload=payload,
            body_text=body_text,
        )

    # --- Métodos convenience: solo delegan, jamás tocan el payload. ---
    # Los nombres reales de los parámetros de query son UNVERIFIED, por eso
    # todos aceptan un dict de params tal cual.

    async def entities_by_name(self, params: dict[str, Any] | None = None) -> RawResponse:
        """RUES: entidades por nombre (ruta UNVERIFIED)."""
        return await self.get("entities-by-name", params)

    async def entity_by_nit(self, params: dict[str, Any] | None = None) -> RawResponse:
        """RUES: entidad por NIT (ruta UNVERIFIED)."""
        return await self.get("entity-by-nit", params)

    async def processes_by_entity(self, params: dict[str, Any] | None = None) -> RawResponse:
        """SECOP: procesos por entidad (ruta UNVERIFIED, docs internos discrepan)."""
        return await self.get("processes-by-entity", params)

    async def contracts_by_provider(self, params: dict[str, Any] | None = None) -> RawResponse:
        """SECOP: contratos por proveedor (ruta UNVERIFIED, docs internos discrepan)."""
        return await self.get("contracts-by-provider", params)

    async def disciplinary_records(self, params: dict[str, Any] | None = None) -> RawResponse:
        """Procuraduría: antecedentes disciplinarios (ruta UNVERIFIED)."""
        return await self.get("disciplinary-records", params)

    async def fiscal_records(self, params: dict[str, Any] | None = None) -> RawResponse:
        """Contraloría: antecedentes fiscales (ruta UNVERIFIED)."""
        return await self.get("fiscal-records", params)
