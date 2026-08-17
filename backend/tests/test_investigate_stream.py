"""Tests del streaming de progreso: callback on_event del loop y POST /investigate/stream.

Dos capas, ambas SIN red:

  - Loop (run_investigation + on_event): eventos observables en orden real
    (start/ok|error por consulta, phase al ensamblar) y el invariante de que
    un callback roto JAMÁS tumba la investigación.
  - Endpoint (/investigate/stream con agent.api.investigate mockeado): NDJSON
    parseable línea a línea, steps ANTES del result, error legible, cabeceras
    anti-buffering, ping por inactividad y rate limit compartido (429).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
import app.ratelimit as rl
from agent.loop import run_investigation
from croma_client.exceptions import CromaUnavailable
from evidence.models import CaseFile
from tests.test_agent_loop import (
    QUESTION,
    FakeCromaClient,
    FakeProvider,
    finalize_response,
    resp_tool,
)
from tests.test_agent_reducers import (
    CC_REP_LEGAL,
    NIT_EJEMPLO,
    contracts_payload,
    rues_by_nit_payload,
)

# /investigate/stream exige cuenta; el sujeto aquí es el NDJSON, no el login
# (ver conftest.bypass_auth y test_auth.py).
pytestmark = pytest.mark.usefixtures("bypass_auth")

# ---------------------------------------------------------------------------
# Capa loop: eventos observables y callback roto
# ---------------------------------------------------------------------------


def _happy_script() -> FakeProvider:
    return FakeProvider(
        [
            resp_tool("rues_entity_by_nit", document_number=NIT_EJEMPLO),
            resp_tool("secop_contracts_by_provider", document_number=NIT_EJEMPLO),
            finalize_response(
                findings=[{"title": "t", "narrative": "n", "evidence_ids": ["ev1"]}]
            ),
        ]
    )


def _happy_croma() -> FakeCromaClient:
    return FakeCromaClient(
        {
            "entity_by_nit": rues_by_nit_payload(),
            "contracts_by_provider": contracts_payload(),
        }
    )


async def test_loop_emits_observable_events_in_real_order() -> None:
    """start/ok por cada consulta con el número de paso REAL, y phase al final."""
    events: list[dict[str, Any]] = []
    case = await run_investigation(
        QUESTION, provider=_happy_script(), croma=_happy_croma(), on_event=events.append
    )

    assert case.status == "complete"
    assert events == [
        {"type": "step", "source": "croma:rues:entity-by-nit", "status": "start", "step": 1},
        {"type": "step", "source": "croma:rues:entity-by-nit", "status": "ok", "step": 1},
        {
            "type": "step",
            "source": "croma:secop:contracts-by-provider",
            "status": "start",
            "step": 2,
        },
        {
            "type": "step",
            "source": "croma:secop:contracts-by-provider",
            "status": "ok",
            "step": 2,
        },
        {"type": "phase", "label": "Construyendo expediente"},
    ]


async def test_failed_source_emits_error_event_and_investigation_continues() -> None:
    events: list[dict[str, Any]] = []
    provider = FakeProvider(
        [
            resp_tool("rues_entity_by_nit", document_number=NIT_EJEMPLO),
            resp_tool("contraloria_fiscal_records", document_number=CC_REP_LEGAL),
            finalize_response(
                findings=[{"title": "t", "narrative": "n", "evidence_ids": ["ev1"]}]
            ),
        ]
    )
    croma = FakeCromaClient(
        {
            "entity_by_nit": rues_by_nit_payload(),
            "fiscal_records": CromaUnavailable("timeout simulado", endpoint="fiscal-records"),
        }
    )
    case = await run_investigation(QUESTION, provider=provider, croma=croma,
                                   on_event=events.append)

    assert case.status == "partial"
    assert {
        "type": "step",
        "source": "croma:contraloria:fiscal-records",
        "status": "error",
        "step": 2,
    } in events
    # La fuente caída no interrumpe el flujo de eventos: la fase final llega igual.
    assert events[-1] == {"type": "phase", "label": "Construyendo expediente"}


async def test_broken_on_event_callback_never_breaks_investigation() -> None:
    """El callback lanza SIEMPRE; la investigación termina idéntica igual."""
    calls = {"n": 0}

    def broken(_event: dict[str, Any]) -> None:
        calls["n"] += 1
        raise RuntimeError("callback roto a propósito")

    case = await run_investigation(
        QUESTION, provider=_happy_script(), croma=_happy_croma(), on_event=broken
    )

    assert calls["n"] == 5  # se intentó emitir todos los eventos, pese a fallar todos
    assert case.status == "complete"
    assert len(case.findings) == 1
    assert [s.status for s in case.sources_consulted] == ["ok", "ok"]


async def test_no_callback_behaves_exactly_as_before() -> None:
    """Sin on_event (CLI y POST clásico) el loop no cambia en nada."""
    case = await run_investigation(QUESTION, provider=_happy_script(), croma=_happy_croma())
    assert case.status == "complete"
    assert len(case.findings) == 1


# ---------------------------------------------------------------------------
# Capa endpoint: /investigate/stream (agent.api.investigate mockeado)
# ---------------------------------------------------------------------------


def _fake_case_file() -> CaseFile:
    return CaseFile(
        question="¿Qué contratos tiene Empresa Ejemplo S.A.S.?",
        status="partial",
        entities=[],
        sources_consulted=[],
        findings=[],
        unknowns=["Sin fuentes consultadas: expediente de prueba."],
        next_steps=[],
    )


def _fake_streaming_investigate(monkeypatch) -> dict[str, Any]:
    """Mockea agent.api.investigate emitiendo dos steps + phase antes del case."""
    captured: dict[str, Any] = {}

    async def fake_investigate(
        question: str, candidate_id: str | None = None, *, on_event=None, **_: object
    ):
        captured["question"] = question
        captured["candidate_id"] = candidate_id
        if on_event is not None:  # el POST clásico llega sin callback
            on_event({"type": "step", "source": "croma:rues:entity-by-nit",
                      "status": "start", "step": 1})
            await asyncio.sleep(0)  # cede el control: los eventos fluyen EN VIVO
            on_event({"type": "step", "source": "croma:rues:entity-by-nit",
                      "status": "ok", "step": 1})
            on_event({"type": "phase", "label": "Construyendo expediente"})
        return _fake_case_file()

    monkeypatch.setattr(app_main, "investigate", fake_investigate)
    return captured


def _stream_lines(client: TestClient, body: dict, headers: dict | None = None):
    """POST al stream y devuelve (response, líneas NDJSON ya parseadas)."""
    with client.stream(
        "POST", "/investigate/stream", json=body, headers=headers or {}
    ) as resp:
        raw_lines = [line for line in resp.iter_lines() if line.strip()]
    parsed = [json.loads(line) for line in raw_lines]
    return resp, parsed


def test_stream_endpoint_emits_steps_then_result_as_ndjson(monkeypatch) -> None:
    rl.reset()
    captured = _fake_streaming_investigate(monkeypatch)
    client = TestClient(app_main.app)

    resp, events = _stream_lines(
        client, {"question": "hola", "candidate_id": "c1"}, {"x-forwarded-for": "10.7.7.1"}
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-ndjson")
    assert resp.headers["x-accel-buffering"] == "no"
    assert resp.headers["cache-control"] == "no-cache"

    # Orden: todos los steps/phase ANTES del result, que cierra el stream.
    assert [e["type"] for e in events] == ["step", "step", "phase", "result"]
    assert events[0]["status"] == "start" and events[0]["step"] == 1
    assert events[1]["status"] == "ok"
    assert events[2]["label"] == "Construyendo expediente"

    # El result trae el MISMO contrato que el POST clásico.
    case = events[-1]["case_file"]
    assert case["status"] == "partial"
    assert "candidates" not in case  # exclude_none del contrato
    assert captured == {"question": "hola", "candidate_id": "c1"}
    rl.reset()


def test_stream_endpoint_reports_failure_as_readable_error_line(monkeypatch) -> None:
    rl.reset()

    async def exploding_investigate(*_args: object, **_kwargs: object):
        raise RuntimeError("proveedor caído (simulado)")

    monkeypatch.setattr(app_main, "investigate", exploding_investigate)
    client = TestClient(app_main.app)

    resp, events = _stream_lines(
        client, {"question": "hola"}, {"x-forwarded-for": "10.7.7.2"}
    )

    assert resp.status_code == 200  # el fallo viaja DENTRO del stream
    assert events == [{"type": "error", "detail": app_main.STREAM_ERROR_DETAIL}]
    assert "reintentar" in events[0]["detail"]
    rl.reset()


def test_stream_endpoint_pings_when_idle(monkeypatch) -> None:
    rl.reset()
    monkeypatch.setattr(app_main, "PING_INTERVAL_SECONDS", 0.02)

    async def slow_investigate(
        question: str, candidate_id: str | None = None, *, on_event=None, **_: object
    ):
        await asyncio.sleep(0.15)
        return _fake_case_file()

    monkeypatch.setattr(app_main, "investigate", slow_investigate)
    client = TestClient(app_main.app)

    _resp, events = _stream_lines(client, {"question": "hola"}, {"x-forwarded-for": "10.7.7.3"})

    assert any(e == {"type": "ping"} for e in events)
    assert events[-1]["type"] == "result"
    rl.reset()


def test_stream_endpoint_shares_rate_limit_quota(monkeypatch) -> None:
    """Una investigación = un cupo, streaming o no: misma dependency, mismo 429."""
    rl.reset()
    monkeypatch.setattr(rl, "PER_IP_PER_HOUR", 2)
    _fake_streaming_investigate(monkeypatch)
    client = TestClient(app_main.app)
    headers = {"x-forwarded-for": "10.7.7.4"}

    assert _stream_lines(client, {"question": "hola"}, headers)[0].status_code == 200
    # El clásico y el stream comparten contadores: este consume el segundo cupo.
    assert (
        client.post("/investigate", json={"question": "hola"}, headers=headers).status_code
        == 200
    )

    resp = client.post("/investigate/stream", json={"question": "hola"}, headers=headers)
    assert resp.status_code == 429
    assert "investigaciones por hora" in resp.json()["detail"]
    rl.reset()


def test_stream_endpoint_validates_like_classic() -> None:
    client = TestClient(app_main.app)
    assert client.post("/investigate/stream", json={}).status_code == 422
    assert (
        client.post("/investigate/stream", json={"question": "   \n  "}).status_code == 422
    )


def test_classic_route_never_passes_a_callback(monkeypatch) -> None:
    """El POST /investigate clásico queda intacto: jamás pasa on_event."""
    rl.reset()
    captured: dict[str, Any] = {}

    async def fake_investigate(question: str, candidate_id: str | None = None, **kwargs: object):
        captured["kwargs"] = kwargs
        return _fake_case_file()

    monkeypatch.setattr(app_main, "investigate", fake_investigate)
    client = TestClient(app_main.app)

    resp = client.post(
        "/investigate", json={"question": "hola"}, headers={"x-forwarded-for": "10.7.7.5"}
    )
    assert resp.status_code == 200
    assert "on_event" not in captured["kwargs"]
    rl.reset()
