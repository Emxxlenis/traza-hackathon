"""Tests de la capa de transporte del cliente Croma.

Todo va contra mocks respx: nada aquí asume la estructura real de los payloads
de Croma (los cuerpos de los mocks son inventados por el propio test y solo se
verifican como passthrough opaco).
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from croma_client import (
    CromaAPIError,
    CromaAuthError,
    CromaClient,
    CromaConfigError,
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


# --- Auth headers (el scheme real es UNVERIFIED; probamos ambos candidatos) ---


@respx.mock
async def test_bearer_scheme_sends_authorization_header() -> None:
    route = respx.get(f"{BASE_URL}{RUES_ENTITY_BY_NIT}").mock(
        return_value=httpx.Response(200, json={})
    )
    async with make_client("bearer") as client:
        await client.entity_by_nit({"nit": "900123456"})

    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer test-key-123"
    assert "X-API-Key" not in request.headers


@respx.mock
async def test_x_api_key_scheme_sends_x_api_key_header() -> None:
    route = respx.get(f"{BASE_URL}{RUES_ENTITY_BY_NIT}").mock(
        return_value=httpx.Response(200, json={})
    )
    async with make_client("x-api-key") as client:
        await client.entity_by_nit({"nit": "900123456"})

    request = route.calls.last.request
    assert request.headers["X-API-Key"] == "test-key-123"
    assert "Authorization" not in request.headers


# --- Reintentos ---


@respx.mock
async def test_retries_on_5xx_then_succeeds() -> None:
    """500 → 500 → 200: debe reintentar y devolver la respuesta final."""
    route = respx.get(f"{BASE_URL}{RUES_ENTITY_BY_NIT}").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(500),
            httpx.Response(200, json={"cualquier": "cosa"}),
        ]
    )
    async with make_client() as client:
        raw = await client.get("entity-by-nit", {"nit": "1"})

    assert route.call_count == 3
    assert raw.status_code == 200
    # Passthrough opaco: el payload sale tal cual entró al mock, sin interpretar.
    assert raw.payload == {"cualquier": "cosa"}


@respx.mock
async def test_5xx_exhausts_retries_and_raises_unavailable() -> None:
    route = respx.get(f"{BASE_URL}{RUES_ENTITY_BY_NIT}").mock(
        return_value=httpx.Response(503)
    )
    async with make_client() as client:
        with pytest.raises(CromaUnavailable) as excinfo:
            await client.get("entity-by-nit", {"nit": "1"})

    assert route.call_count == 3  # máximo de intentos, ni uno más
    assert excinfo.value.status_code == 503


@respx.mock
async def test_network_errors_exhaust_retries_and_raise_unavailable() -> None:
    route = respx.get(f"{BASE_URL}{RUES_ENTITY_BY_NIT}").mock(
        side_effect=httpx.ConnectError("conexión rechazada")
    )
    async with make_client() as client:
        with pytest.raises(CromaUnavailable) as excinfo:
            await client.get("entity-by-nit", {"nit": "1"})

    assert route.call_count == 3
    assert excinfo.value.status_code is None  # nunca hubo respuesta HTTP


@respx.mock
async def test_404_is_never_retried() -> None:
    route = respx.get(f"{BASE_URL}{RUES_ENTITY_BY_NIT}").mock(
        return_value=httpx.Response(404)
    )
    async with make_client() as client:
        with pytest.raises(CromaNotFound):
            await client.get("entity-by-nit", {"nit": "1"})

    assert route.call_count == 1  # los 4xx jamás se reintentan


# --- Mapeo de excepciones ---


@pytest.mark.parametrize(
    ("status", "exc_type"),
    [
        (401, CromaAuthError),
        (403, CromaAuthError),
        (404, CromaNotFound),
        (429, CromaRateLimited),
        (422, CromaAPIError),  # 4xx genérico: error tipado, sin reintentos
    ],
)
@respx.mock
async def test_status_codes_map_to_typed_exceptions(status: int, exc_type: type) -> None:
    route = respx.get(f"{BASE_URL}{RUES_ENTITY_BY_NIT}").mock(
        return_value=httpx.Response(status)
    )
    async with make_client() as client:
        with pytest.raises(exc_type) as excinfo:
            await client.get("entity-by-nit", {"nit": "1"})

    assert route.call_count == 1
    assert excinfo.value.status_code == status
    assert excinfo.value.endpoint == "entity-by-nit"


# --- Envelope de provenance ---


@respx.mock
async def test_envelope_carries_provenance_without_touching_payload() -> None:
    respx.get(f"{BASE_URL}{RUES_ENTITY_BY_NIT}").mock(
        return_value=httpx.Response(200, json=["a", "b"])  # lista también es válida
    )
    async with make_client() as client:
        raw = await client.entity_by_nit({"nit": "900123456"})

    assert raw.source == "croma:rues:entity-by-nit"
    assert raw.endpoint == RUES_ENTITY_BY_NIT
    assert raw.url.startswith(f"{BASE_URL}{RUES_ENTITY_BY_NIT}")
    assert "nit=900123456" in raw.url
    assert raw.status_code == 200
    assert raw.fetched_at.endswith("+00:00") or raw.fetched_at.endswith("Z")  # UTC ISO
    assert raw.payload == ["a", "b"]  # passthrough opaco definido por este mock


@respx.mock
async def test_convenience_methods_delegate_to_registered_paths() -> None:
    """Cada método convenience pega a su ruta candidata, sin transformar nada."""
    from croma_client import ENDPOINTS

    async with make_client() as client:
        for name, method in [
            ("entities-by-name", client.entities_by_name),
            ("entity-by-nit", client.entity_by_nit),
            ("processes-by-entity", client.processes_by_entity),
            ("contracts-by-provider", client.contracts_by_provider),
            ("disciplinary-records", client.disciplinary_records),
            ("fiscal-records", client.fiscal_records),
        ]:
            route = respx.get(f"{BASE_URL}{ENDPOINTS[name].path}").mock(
                return_value=httpx.Response(200, json={})
            )
            raw = await method({"q": "x"})
            assert route.called
            assert raw.source == ENDPOINTS[name].source
