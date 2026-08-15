"""Cliente async de transporte para la API de Croma.

Responsabilidad ÚNICA: llevar y traer bytes con reintentos y errores tipados.
CERO parsing de payloads de negocio — las respuestas viajan opacas dentro de
RawResponse. (Única lectura del body: ante un 4xx se intenta extraer
``error.message`` / ``error.param`` para enriquecer el diagnóstico de la
excepción; eso es transporte de diagnóstico, no parsing de negocio.)

Transporte VERIFICADO contra capturas reales (ver docs/croma-schema.md):
  - Todos los endpoints son POST con body JSON (GET devuelve 405).
  - Errores 4xx: ``{"error": {type, code, message, param, details}}``.

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
    CromaMethodNotAllowed,
    CromaNotFound,
    CromaRateLimited,
    CromaUnavailable,
)

DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_BASE_SECONDS = 0.5


def _auth_headers(settings: CromaSettings) -> dict[str, str]:
    """Construye el header de auth según el scheme configurado.

    VERIFICADO: ``Authorization: Bearer <key>`` funciona contra la API real.
    ``X-API-Key`` NO está probado; se mantiene como alternativa configurable.
    """
    if settings.auth_scheme == "x-api-key":
        return {"X-API-Key": settings.api_key}
    return {"Authorization": f"Bearer {settings.api_key}"}


def _error_detail(response: httpx.Response) -> str:
    """Extrae ``error.message``/``error.param`` de un body de error 4xx.

    Formato de error VERIFICADO: ``{"error": {type, code, message, param,
    details}}`` — los 400 de Croma son informativos (nombran el param
    faltante/inválido). Esto es transporte de diagnóstico, no parsing de datos
    de negocio. Si el body no es JSON o no tiene esa forma, devuelve "" y el
    mensaje base de la excepción queda intacto.
    """
    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError):
        return ""
    if not isinstance(payload, dict):
        return ""
    error = payload.get("error")
    if not isinstance(error, dict):
        return ""
    fragments: list[str] = []
    message = error.get("message")
    if isinstance(message, str) and message.strip():
        fragments.append(message.strip())
    param = error.get("param")
    if isinstance(param, str) and param.strip():
        fragments.append(f"(param: {param.strip()})")
    if not fragments:
        return ""
    return " Croma dice: " + " ".join(fragments)


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

    async def call(self, endpoint: str, body: dict[str, Any]) -> RawResponse:
        """POST genérico contra un endpoint (nombre corto del registro o ruta).

        VERIFICADO: todos los endpoints de Croma son POST con body JSON (GET
        devuelve 405). Devuelve un RawResponse con el payload OPACO. Lanza
        excepciones tipadas según el resultado (ver croma_client.exceptions).
        """
        spec = resolve_endpoint(endpoint)
        response: httpx.Response | None = None
        last_network_error: httpx.TransportError | None = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._client.post(spec.path, json=body)
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
        """Mapea códigos HTTP de error a excepciones tipadas.

        En 4xx intenta enriquecer el mensaje con ``error.message``/``error.param``
        del body (formato de error VERIFICADO); si el body no coopera, el mensaje
        base queda igual que siempre.
        """
        status = response.status_code
        url = str(response.request.url)
        detail = _error_detail(response) if 400 <= status < 500 else ""
        if status in (401, 403):
            raise CromaAuthError(
                f"Auth rechazada por Croma ({status}) en {spec.name}. Revisa CROMA_API_KEY "
                f"(Bearer es el scheme VERIFICADO).{detail}",
                status_code=status,
                endpoint=spec.name,
                url=url,
            )
        if status == 404:
            raise CromaNotFound(
                f"404 en {spec.name} ({spec.path}). La ruta registrada está VERIFICADA; "
                f"un 404 sugiere ruta mal escrita o no registrada — 'sin datos' llega "
                f"como 200 con found: false.{detail}",
                status_code=status,
                endpoint=spec.name,
                url=url,
            )
        if status == 405:
            raise CromaMethodNotAllowed(
                f"405 Method Not Allowed en {spec.name}: la API de Croma solo acepta "
                f"POST con body JSON (VERIFICADO — GET devuelve 405).{detail}",
                status_code=status,
                endpoint=spec.name,
                url=url,
            )
        if status == 429:
            raise CromaRateLimited(
                f"Rate limit de Croma alcanzado (429) en {spec.name}.{detail}",
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
                f"Croma respondió {status} en {spec.name}.{detail}",
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
            # La API verificada responde JSON; si algún día llega otra cosa la
            # preservamos verbatim en vez de perderla. Clave reservada nuestra,
            # no estructura de Croma.
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

    # --- Métodos convenience: arman el body de la petición con las firmas
    # VERIFICADAS (ver docs/croma-schema.md) y delegan en call().
    # JAMÁS parsean la respuesta: el payload sigue opaco en RawResponse. ---

    async def entities_by_name(self, name: str) -> RawResponse:
        """RUES: búsqueda de entidades por nombre. Body: {"name": name}."""
        return await self.call("entities-by-name", {"name": name})

    async def entity_by_nit(self, document_number: str) -> RawResponse:
        """RUES: entidad por NIT. Body: {"document_number": document_number}.

        Args:
            document_number: NIT sin puntos y SIN dígito de verificación.
        """
        return await self.call("entity-by-nit", {"document_number": document_number})

    async def contracts_by_provider(self, document_number: str, **filters: Any) -> RawResponse:
        """SECOP: contratos por proveedor. Body: document_number + filtros.

        Args:
            document_number: documento/NIT del proveedor.
            **filters: filtros opcionales pass-through al body (from_date,
                to_date, entity_nit). Se envían tal cual, SIN validar: el
                formato que acepta la API es NO VERIFICADO.
        """
        return await self.call(
            "contracts-by-provider", {"document_number": document_number, **filters}
        )

    async def processes_by_entity(self, document_number: str, **filters: Any) -> RawResponse:
        """SECOP: procesos por entidad contratante. Body: document_number + filtros.

        Ojo (verificado): los procesos son el lado de la convocatoria y no traen
        adjudicatario/proveedor; la relación proveedor-entidad se ve desde
        contracts_by_provider.

        Args:
            document_number: NIT de la entidad contratante.
            **filters: filtros opcionales pass-through al body (from_date,
                to_date). Se envían tal cual, SIN validar: formato NO VERIFICADO.
        """
        return await self.call(
            "processes-by-entity", {"document_number": document_number, **filters}
        )

    async def disciplinary_records(
        self, document_number: str, document_type: str = "CC"
    ) -> RawResponse:
        """Procuraduría: antecedentes disciplinarios.

        Args:
            document_number: documento de la persona o NIT de la empresa.
            document_type: "CC" por defecto; acepta también "NIT" (VERIFICADO).
        """
        return await self.call(
            "disciplinary-records",
            {"document_number": document_number, "document_type": document_type},
        )

    async def fiscal_records(
        self, document_number: str, document_type: str = "CC"
    ) -> RawResponse:
        """Contraloría: antecedentes fiscales.

        Args:
            document_number: documento de la PERSONA consultada.
            document_type: SOLO tipos de persona — CC|CE|TI|PA|PEP|PPT. NO existe
                NIT en esta fuente: los antecedentes fiscales se consultan sobre
                la persona (p. ej. el representante legal obtenido de
                related_parties en RUES), no sobre la empresa.
        """
        return await self.call(
            "fiscal-records",
            {"document_number": document_number, "document_type": document_type},
        )
