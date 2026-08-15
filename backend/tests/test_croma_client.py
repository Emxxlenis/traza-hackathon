"""Tests de la capa de transporte del cliente Croma.

Todo va contra mocks respx: nada aquí asume la estructura real de los payloads
de negocio de Croma (los cuerpos de los mocks los inventa el propio test y solo
se verifican como passthrough opaco). La única estructura que sí probamos es la
VERIFICADA de transporte: POST + body JSON y el envelope de error
{"error": {message, param, ...}} de los 4xx (ver docs/croma-schema.md).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from croma_client import (
    CromaAPIError,
    CromaAuthError,
    CromaClient,
    CromaConfigError,
    CromaMethodNotAllowed,
    CromaNotFound,
    CromaRateLimited,
    CromaSettings,
    CromaUnavailable,
    load_settings,
)
from croma_client.endpoints import RUES_ENTITY_BY_NIT

BASE_URL = "https://croma.test"


def make_settings(auth_scheme: str = "bearer") -> CromaSettings:
    """Settings de test explícitos, sin depender del .env real."""
    return CromaSettings(
        api_key="test-key-123",
        base_url=BASE_URL,
        auth_scheme=auth_scheme,  # type: ignore[arg-type]
        _env_file=None,
    )


def make_client(auth_scheme: str = "bearer") -> CromaClient:
    """Cliente de test con backoff nulo para que los reintentos no duerman."""
    return CromaClient(make_settings(auth_scheme), backoff_base=0.0)


def request_body(route: respx.Route) -> dict | list:
    """Decodifica el body JSON de la última petición capturada por la ruta."""
    return json.loads(route.calls.last.request.content)


# --- Configuración ---


def test_missing_base_url_raises_actionable_config_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Sin CROMA_BASE_URL el error debe ser claro y accionable (no un stacktrace críptico)."""
    for var in ("CROMA_API_KEY", "CROMA_BASE_URL", "CROMA_AUTH_SCHEME"):
        monkeypatch.delenv(var, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("CROMA_API_KEY=algo\n", encoding="utf-8")

    with pytest.raises(CromaConfigError) as excinfo:
        load_settings(env_file=env_file)

    message = str(excinfo.value)
    assert "CROMA_BASE_URL" in message
    assert ".env" in message  # debe decir cómo arreglarlo


def test_blank_base_url_is_treated_as_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """CROMA_BASE_URL= (vacío, como en .env.example recién copiado) también falla claro."""
    for var in ("CROMA_API_KEY", "CROMA_BASE_URL", "CROMA_AUTH_SCHEME"):
        monkeypatch.delenv(var, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("CROMA_API_KEY=algo\nCROMA_BASE_URL=\n", encoding="utf-8")

    with pytest.raises(CromaConfigError) as excinfo:
        load_settings(env_file=env_file)
    assert "CROMA_BASE_URL" in str(excinfo.value)


# --- Auth headers (Bearer VERIFICADO; X-API-Key se mantiene como alternativa) ---


@respx.mock
async def test_bearer_scheme_sends_authorization_header() -> None:
    route = respx.post(f"{BASE_URL}{RUES_ENTITY_BY_NIT}").mock(
        return_value=httpx.Response(200, json={})
    )
    async with make_client("bearer") as client:
        await client.entity_by_nit("900123456")

    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer test-key-123"
    assert "X-API-Key" not in request.headers


@respx.mock
async def test_x_api_key_scheme_sends_x_api_key_header() -> None:
    route = respx.post(f"{BASE_URL}{RUES_ENTITY_BY_NIT}").mock(
        return_value=httpx.Response(200, json={})
    )
    async with make_client("x-api-key") as client:
        await client.entity_by_nit("900123456")

    request = route.calls.last.request
    assert request.headers["X-API-Key"] == "test-key-123"
    assert "Authorization" not in request.headers


# --- Reintentos ---


@respx.mock
async def test_retries_on_5xx_then_succeeds() -> None:
    """500 → 500 → 200: debe reintentar y devolver la respuesta final."""
    route = respx.post(f"{BASE_URL}{RUES_ENTITY_BY_NIT}").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(500),
            httpx.Response(200, json={"cualquier": "cosa"}),
        ]
    )
    async with make_client() as client:
        raw = await client.call("entity-by-nit", {"document_number": "1"})

    assert route.call_count == 3
    assert raw.status_code == 200
    # Passthrough opaco: el payload sale tal cual entró al mock, sin interpretar.
    assert raw.payload == {"cualquier": "cosa"}


@respx.mock
async def test_5xx_exhausts_retries_and_raises_unavailable() -> None:
    route = respx.post(f"{BASE_URL}{RUES_ENTITY_BY_NIT}").mock(
        return_value=httpx.Response(503)
    )
    async with make_client() as client:
        with pytest.raises(CromaUnavailable) as excinfo:
            await client.call("entity-by-nit", {"document_number": "1"})

    assert route.call_count == 3  # máximo de intentos, ni uno más
    assert excinfo.value.status_code == 503


@respx.mock
async def test_network_errors_exhaust_retries_and_raise_unavailable() -> None:
    route = respx.post(f"{BASE_URL}{RUES_ENTITY_BY_NIT}").mock(
        side_effect=httpx.ConnectError("conexión rechazada")
    )
    async with make_client() as client:
        with pytest.raises(CromaUnavailable) as excinfo:
            await client.call("entity-by-nit", {"document_number": "1"})

    assert route.call_count == 3
    assert excinfo.value.status_code is None  # nunca hubo respuesta HTTP


@respx.mock
async def test_404_is_never_retried() -> None:
    route = respx.post(f"{BASE_URL}{RUES_ENTITY_BY_NIT}").mock(
        return_value=httpx.Response(404)
    )
    async with make_client() as client:
        with pytest.raises(CromaNotFound):
            await client.call("entity-by-nit", {"document_number": "1"})

    assert route.call_count == 1  # los 4xx jamás se reintentan


# --- Mapeo de excepciones ---


@pytest.mark.parametrize(
    ("status", "exc_type"),
    [
        (401, CromaAuthError),
        (403, CromaAuthError),
        (404, CromaNotFound),
        (405, CromaMethodNotAllowed),  # VERIFICADO: la señal de "método equivocado"
        (429, CromaRateLimited),
        (422, CromaAPIError),  # 4xx genérico: error tipado, sin reintentos
    ],
)
@respx.mock
async def test_status_codes_map_to_typed_exceptions(status: int, exc_type: type) -> None:
    route = respx.post(f"{BASE_URL}{RUES_ENTITY_BY_NIT}").mock(
        return_value=httpx.Response(status)
    )
    async with make_client() as client:
        with pytest.raises(exc_type) as excinfo:
            await client.call("entity-by-nit", {"document_number": "1"})

    assert route.call_count == 1
    assert excinfo.value.status_code == status
    assert excinfo.value.endpoint == "entity-by-nit"


@respx.mock
async def test_405_message_says_the_api_is_post_only() -> None:
    """El 405 ya nos pasó una vez: el mensaje debe decir claramente 'usa POST'."""
    respx.post(f"{BASE_URL}{RUES_ENTITY_BY_NIT}").mock(return_value=httpx.Response(405))
    async with make_client() as client:
        with pytest.raises(CromaMethodNotAllowed) as excinfo:
            await client.call("entity-by-nit", {"document_number": "1"})

    message = str(excinfo.value)
    assert "405" in message
    assert "POST" in message
    assert isinstance(excinfo.value, CromaAPIError)  # sigue dentro de la jerarquía


# --- Enriquecimiento de diagnóstico en 4xx (formato de error VERIFICADO) ---


@respx.mock
async def test_400_extracts_error_message_and_param() -> None:
    """Un 400 con {"error": {message, param}} enriquece el mensaje de la excepción."""
    respx.post(f"{BASE_URL}{RUES_ENTITY_BY_NIT}").mock(
        return_value=httpx.Response(
            400,
            json={
                "error": {
                    "type": "invalid_request_error",
                    "code": "parameter_invalid",
                    "message": "document_type must be one of CC, CE, TI, PA, PEP, PPT",
                    "param": "document_type",
                    "details": {"issues": []},
                }
            },
        )
    )
    async with make_client() as client:
        with pytest.raises(CromaAPIError) as excinfo:
            await client.call("entity-by-nit", {"document_number": "1"})

    message = str(excinfo.value)
    assert "document_type must be one of CC, CE, TI, PA, PEP, PPT" in message
    assert "param: document_type" in message
    assert excinfo.value.status_code == 400


@respx.mock
async def test_400_with_non_json_body_falls_back_to_base_message() -> None:
    """Body no-JSON en un 4xx: no debe romper, cae al mensaje base de siempre."""
    respx.post(f"{BASE_URL}{RUES_ENTITY_BY_NIT}").mock(
        return_value=httpx.Response(400, text="<html>bad request</html>")
    )
    async with make_client() as client:
        with pytest.raises(CromaAPIError) as excinfo:
            await client.call("entity-by-nit", {"document_number": "1"})

    assert "400" in str(excinfo.value)
    assert excinfo.value.endpoint == "entity-by-nit"


@respx.mock
async def test_400_with_unexpected_error_shape_falls_back_gracefully() -> None:
    """JSON sin la forma {"error": {...}} tampoco rompe el mapeo de excepciones."""
    respx.post(f"{BASE_URL}{RUES_ENTITY_BY_NIT}").mock(
        return_value=httpx.Response(400, json={"error": "algo salió mal"})
    )
    async with make_client() as client:
        with pytest.raises(CromaAPIError) as excinfo:
            await client.call("entity-by-nit", {"document_number": "1"})

    assert "400" in str(excinfo.value)
    assert excinfo.value.status_code == 400


# --- Envelope de provenance ---


@respx.mock
async def test_envelope_carries_provenance_without_touching_payload() -> None:
    route = respx.post(f"{BASE_URL}{RUES_ENTITY_BY_NIT}").mock(
        return_value=httpx.Response(200, json=["a", "b"])  # lista también es válida
    )
    async with make_client() as client:
        raw = await client.entity_by_nit("900123456")

    request = route.calls.last.request
    assert request.method == "POST"
    assert request_body(route) == {"document_number": "900123456"}
    assert raw.source == "croma:rues:entity-by-nit"
    assert raw.endpoint == RUES_ENTITY_BY_NIT
    assert raw.url == f"{BASE_URL}{RUES_ENTITY_BY_NIT}"
    assert raw.status_code == 200
    assert raw.fetched_at.endswith("+00:00") or raw.fetched_at.endswith("Z")  # UTC ISO
    assert raw.payload == ["a", "b"]  # passthrough opaco definido por este mock


# --- Métodos convenience: arman el body VERIFICADO, jamás parsean la respuesta ---


@respx.mock
async def test_convenience_methods_build_verified_bodies() -> None:
    """Cada convenience pega a su ruta con POST y arma exactamente el body verificado."""
    from croma_client import ENDPOINTS

    cases = [
        (
            "entities-by-name",
            lambda c: c.entities_by_name("ACME SAS"),
            {"name": "ACME SAS"},
        ),
        (
            "entity-by-nit",
            lambda c: c.entity_by_nit("900123456"),
            {"document_number": "900123456"},
        ),
        (
            # Los filtros van pass-through SIN validar (formato NO VERIFICADO).
            "contracts-by-provider",
            lambda c: c.contracts_by_provider(
                "900123456", from_date="2020-01-01", entity_nit="800100200"
            ),
            {
                "document_number": "900123456",
                "from_date": "2020-01-01",
                "entity_nit": "800100200",
            },
        ),
        (
            "processes-by-entity",
            lambda c: c.processes_by_entity("899999999", to_date="2025-12-31"),
            {"document_number": "899999999", "to_date": "2025-12-31"},
        ),
        (
            # document_type acepta también "NIT" en Procuraduría (VERIFICADO).
            "disciplinary-records",
            lambda c: c.disciplinary_records("900123456", document_type="NIT"),
            {"document_number": "900123456", "document_type": "NIT"},
        ),
        (
            # Contraloría: default "CC"; solo tipos de persona (no existe NIT).
            "fiscal-records",
            lambda c: c.fiscal_records("1032456789"),
            {"document_number": "1032456789", "document_type": "CC"},
        ),
    ]
    async with make_client() as client:
        for name, invoke, expected_body in cases:
            route = respx.post(f"{BASE_URL}{ENDPOINTS[name].path}").mock(
                return_value=httpx.Response(200, json={})
            )
            raw = await invoke(client)
            assert route.called, name
            assert request_body(route) == expected_body, name
            assert raw.source == ENDPOINTS[name].source
