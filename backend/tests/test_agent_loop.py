"""Tests del loop del agente: TODO mockeado, sin red y con valores ficticios.

FakeProvider sigue un guion de LLMResponses; FakeCromaClient devuelve payloads
con la forma real de Croma pero datos inventados (ver test_agent_reducers).
Aquí se prueban los invariantes que viven en CÓDIGO:

  - límites max_steps / max_entities / max_depth enforced con contadores;
  - desambiguación con >1 candidato y reanudación con candidate_id;
  - degradación cuando una fuente lanza CromaUnavailable;
  - gate de evidencia (refs inexistentes descartados, derived re-verificado).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from agent.loop import LoopConfig, assemble_case_file, run_investigation
from agent.providers import LLMResponse, ToolCall
from agent.store import EvidenceStore
from croma_client.envelope import RawResponse
from croma_client.exceptions import CromaUnavailable
from evidence.models import CalculationStep, DerivedEvidence
from tests.test_agent_reducers import (
    CC_REP_LEGAL,
    NIT_EJEMPLO,
    contracts_payload,
    contraloria_payload,
    empty_contracts_payload,
    entities_by_name_payload,
    processes_payload,
    procuraduria_payload,
    rues_by_nit_payload,
)

QUESTION = "¿Qué contratos públicos tiene Empresa Ejemplo S.A.S. y dónde se concentran?"

_CALL_COUNTER = {"n": 0}


def tool_call(tool_name: str, /, **arguments: Any) -> ToolCall:
    _CALL_COUNTER["n"] += 1
    return ToolCall(id=f"call-{_CALL_COUNTER['n']}", name=tool_name, arguments=arguments)


def resp_tool(tool_name: str, /, **arguments: Any) -> LLMResponse:
    return LLMResponse(content=None, tool_calls=(tool_call(tool_name, **arguments),))


def finalize_response(
    findings: list[dict] | None = None,
    entities: list[dict] | None = None,
    unknowns: list[str] | None = None,
    next_steps: list[str] | None = None,
) -> LLMResponse:
    return LLMResponse(
        content=None,
        tool_calls=(
            tool_call(
                "finalize_case_file",
                entities=entities or [],
                findings=findings or [],
                unknowns=unknowns or [],
                next_steps=next_steps or [],
            ),
        ),
    )


class FakeProvider:
    """Proveedor LLM con guion fijo. Registra cada llamada para asserts."""

    def __init__(self, script: list[LLMResponse]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        tool_choice: str | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {
                "n_messages": len(messages),
                "tools": [tool["name"] for tool in tools],
                "tool_choice": tool_choice,
            }
        )
        if not self.script:
            raise AssertionError("guion del FakeProvider agotado: el loop pidió otra vuelta")
        return self.script.pop(0)


_METHOD_SOURCES = {
    "entities_by_name": "croma:rues:entities-by-name",
    "entity_by_nit": "croma:rues:entity-by-nit",
    "contracts_by_provider": "croma:secop:contracts-by-provider",
    "processes_by_entity": "croma:secop:processes-by-entity",
    "disciplinary_records": "croma:procuraduria:disciplinary-records",
    "fiscal_records": "croma:contraloria:fiscal-records",
}


class FakeCromaClient:
    """Cliente Croma de guion: payloads ficticios o excepciones por método."""

    def __init__(self, script: dict[str, Any]) -> None:
        self.script = script
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def _call(self, method: str, kwargs: dict[str, Any]) -> RawResponse:
        self.calls.append((method, kwargs))
        entry = self.script.get(method)
        if isinstance(entry, list):
            entry = entry.pop(0)
        if isinstance(entry, Exception):
            raise entry
        if callable(entry):
            entry = entry(**kwargs)
        if entry is None:
            raise AssertionError(f"FakeCromaClient sin guion para {method!r}")
        return RawResponse(
            source=_METHOD_SOURCES[method],
            endpoint=f"/fake/{method}",
            url=f"https://croma.test/{method}",
            status_code=200,
            fetched_at="2026-08-14T00:00:00+00:00",
            payload=entry,
            body_text=json.dumps(entry),
        )

    async def entities_by_name(self, name: str) -> RawResponse:
        return await self._call("entities_by_name", {"name": name})

    async def entity_by_nit(self, document_number: str) -> RawResponse:
        return await self._call("entity_by_nit", {"document_number": document_number})

    async def contracts_by_provider(self, document_number: str, **filters: Any) -> RawResponse:
        return await self._call("contracts_by_provider", {"document_number": document_number})

    async def processes_by_entity(self, document_number: str, **filters: Any) -> RawResponse:
        return await self._call("processes_by_entity", {"document_number": document_number})

    async def disciplinary_records(
        self, document_number: str, document_type: str = "CC"
    ) -> RawResponse:
        return await self._call(
            "disciplinary_records",
            {"document_number": document_number, "document_type": document_type},
        )

    async def fiscal_records(
        self, document_number: str, document_type: str = "CC"
    ) -> RawResponse:
        return await self._call(
            "fiscal_records",
            {"document_number": document_number, "document_type": document_type},
        )


# --- Camino feliz: RUES -> SECOP -> finalize con evidencia real ---


async def test_happy_path_produces_complete_case_file():
    provider = FakeProvider(
        [
            resp_tool("rues_entity_by_nit", document_number=NIT_EJEMPLO),
            resp_tool("secop_contracts_by_provider", document_number=NIT_EJEMPLO),
            finalize_response(
                findings=[
                    {
                        "title": "Identidad y concentración de contratos",
                        "narrative": "La empresa está activa y concentra contratos en una entidad.",
                        # ev1-ev3: RUES (estado + 2 related parties); ev4: conteo SECOP;
                        # ev5: concentración por conteo (derived).
                        "evidence_ids": ["ev1", "ev2", "ev4", "ev5"],
                    }
                ],
                entities=[
                    {"id": f"co:nit:{NIT_EJEMPLO}", "name": "Empresa Ejemplo S.A.S.",
                     "role": "investigada"},
                    {"id": "co:nit:800000001", "name": "Entidad Ficticia Uno",
                     "role": "contratante"},
                ],
                unknowns=["No se consultaron antecedentes del representante legal."],
                next_steps=["Consultar Contraloría con la cédula del representante legal."],
            ),
        ]
    )
    croma = FakeCromaClient(
        {
            "entity_by_nit": rues_by_nit_payload(),
            "contracts_by_provider": contracts_payload(),
        }
    )
    trace: dict[str, Any] = {}
    case = await run_investigation(
        QUESTION, provider=provider, croma=croma, trace=trace
    )

    assert case.status == "complete"
    assert [s.status for s in case.sources_consulted] == ["ok", "ok"]
    assert [s.source for s in case.sources_consulted] == [
        "croma:rues:entity-by-nit",
        "croma:secop:contracts-by-provider",
    ]
    assert len(case.findings) == 1
    finding = case.findings[0]
    assert len(finding.evidence) == 4
    types = {e.type for e in finding.evidence}
    assert types == {"direct", "derived"}
    derived = next(e for e in finding.evidence if e.type == "derived")
    # La evidencia derivada referencia contratos reales por id.
    assert any(s.startswith("croma:secop:contract:CO1.PCCNTR.") for s in derived.sources)
    assert {e.role for e in case.entities} == {"investigada", "contratante"}
    # Serializa al contrato v0 sin candidates.
    contract_dict = case.to_contract_dict()
    assert "candidates" not in contract_dict
    assert contract_dict["findings"][0]["evidence"][-1]["calculation_steps"]
    assert trace["steps_used"] == 2
    assert trace["llm_calls"] == 3


# --- Expediente vacío: la fuente responde con cero resultados (NO es error) ---


async def test_empty_secop_result_is_complete_and_asserted_as_fact():
    """Empresa real en RUES pero sin contratos en SECOP: expediente complete
    con el cero afirmado como evidencia directa, jamás como fallo."""
    provider = FakeProvider(
        [
            resp_tool("rues_entity_by_nit", document_number=NIT_EJEMPLO),
            resp_tool("secop_contracts_by_provider", document_number=NIT_EJEMPLO),
            finalize_response(
                findings=[
                    {"title": "Identidad registral", "narrative": "Empresa activa en RUES.",
                     "evidence_ids": ["ev1"]},
                    {"title": "Sin contratos registrados en SECOP",
                     "narrative": "SECOP no registra contratos para el NIT consultado.",
                     # ev1-ev3: RUES (estado + 2 related parties); ev4: cero de SECOP.
                     "evidence_ids": ["ev4"]},
                ],
                unknowns=[
                    (
                        "El cero de SECOP no permite concluir que la empresa nunca haya "
                        "contratado con el Estado (límites de cobertura de la fuente)."
                    )
                ],
                next_steps=["Verificar variantes del NIT y consultar SECOP web directamente."],
            ),
        ]
    )
    croma = FakeCromaClient(
        {
            "entity_by_nit": rues_by_nit_payload(),
            "contracts_by_provider": empty_contracts_payload(),
        }
    )
    case = await run_investigation(QUESTION, provider=provider, croma=croma)

    # Las fuentes respondieron: el vacío es un resultado, NO degrada a partial.
    assert case.status == "complete"
    assert [s.status for s in case.sources_consulted] == ["ok", "ok"]
    zero = case.findings[1].evidence[0]
    assert zero.type == "direct"
    assert zero.claim == (
        f"SECOP no registra contratos para el proveedor {NIT_EJEMPLO}; total reportado: 0"
    )
    assert zero.source.startswith("croma:secop:contracts-by-provider")
    assert zero.raw_reference == "data.count"
    assert any("no permite concluir" in u.lower() for u in case.unknowns)


async def test_nit_unresolved_in_rues_with_zero_contracts_is_complete():
    """NIT que no resuelve en RUES (found=false) y SECOP con 0 contratos:
    ambos hechos entran como evidencia directa y el expediente cierra complete."""
    provider = FakeProvider(
        [
            resp_tool("rues_entity_by_nit", document_number="900000099"),
            resp_tool("secop_contracts_by_provider", document_number="900000099"),
            finalize_response(
                findings=[
                    {"title": "RUES sin registro para el NIT",
                     "narrative": "RUES no devuelve registro para el NIT consultado "
                                  "(found=false).",
                     "evidence_ids": ["ev1"]},
                    {"title": "Sin contratos registrados en SECOP",
                     "narrative": "SECOP no registra contratos para el NIT consultado.",
                     "evidence_ids": ["ev2"]},
                ],
                unknowns=[
                    (
                        "found=false no permite concluir que la empresa no exista ni que "
                        "el NIT sea inválido."
                    )
                ],
                next_steps=[
                    (
                        "Verificar el NIT (sin dígito de verificación) y buscar por "
                        "razón social en RUES."
                    )
                ],
            ),
        ]
    )
    croma = FakeCromaClient(
        {
            "entity_by_nit": rues_by_nit_payload(found=False),
            "contracts_by_provider": empty_contracts_payload("900000099"),
        }
    )
    case = await run_investigation(QUESTION, provider=provider, croma=croma)

    assert case.status == "complete"
    assert [s.status for s in case.sources_consulted] == ["ok", "ok"]
    assert len(case.findings) == 2
    assert "found=false" in case.findings[0].evidence[0].claim
    assert "no registra contratos" in case.findings[1].evidence[0].claim


async def test_name_search_without_matches_finalizes_without_pause():
    """Búsqueda por nombre sin coincidencias: 0 candidatos NO dispara
    needs_disambiguation ni bucles; el hecho entra como direct y cierra complete."""
    provider = FakeProvider(
        [
            resp_tool("rues_entities_by_name", name="Empresa Zutano Inexistente XYZ"),
            finalize_response(
                findings=[
                    {"title": "Sin coincidencias registrales por nombre",
                     "narrative": "La búsqueda RUES por el nombre consultado no devuelve "
                                  "entidades.",
                     "evidence_ids": ["ev1"]},
                ],
                unknowns=["El nombre buscado puede diferir de la razón social registrada."],
                next_steps=["Aportar el NIT o intentar variantes del nombre."],
            ),
        ]
    )
    croma = FakeCromaClient({"entities_by_name": entities_by_name_payload(0)})
    case = await run_investigation(QUESTION, provider=provider, croma=croma)

    assert case.status == "complete"
    assert case.candidates is None
    assert [s.status for s in case.sources_consulted] == ["ok"]
    assert len(case.findings) == 1
    assert "no devuelve entidades" in case.findings[0].evidence[0].claim


# --- Límites operacionales enforced en código ---


async def test_max_steps_enforced_no_ninth_call():
    """Al paso 9 NO hay llamada 9 a Croma, aunque el modelo insista."""
    script = [
        resp_tool(
            "procuraduria_disciplinary_records",
            document_number=NIT_EJEMPLO,
            document_type="NIT",
        )
        for _ in range(9)  # el modelo intenta 9 consultas
    ]
    script.append(
        finalize_response(
            findings=[
                {"title": "Consulta repetida", "narrative": "Antecedentes consultados.",
                 "evidence_ids": ["ev1"]}
            ]
        )
    )
    provider = FakeProvider(script)
    croma = FakeCromaClient({"disciplinary_records": procuraduria_payload("NIT")})

    case = await run_investigation(QUESTION, provider=provider, croma=croma)

    assert len(croma.calls) == 8  # nunca hay novena llamada
    assert case.status == "partial"
    assert any("max_steps=8" in u for u in case.unknowns)
    # Tras agotar los pasos, al modelo solo se le ofrece finalize (forzado).
    assert provider.calls[-1]["tools"] == ["finalize_case_file"]
    assert provider.calls[-1]["tool_choice"] == "finalize_case_file"
    # La investigación degradada igual entrega hallazgos con evidencia.
    assert len(case.findings) == 1


async def test_max_entities_enforced():
    config = LoopConfig(max_entities=2)
    provider = FakeProvider(
        [
            resp_tool("procuraduria_disciplinary_records",
                      document_number="900000011", document_type="NIT"),
            resp_tool("procuraduria_disciplinary_records",
                      document_number="900000022", document_type="NIT"),
            resp_tool("procuraduria_disciplinary_records",
                      document_number="900000033", document_type="NIT"),
            finalize_response(
                findings=[{"title": "t", "narrative": "n", "evidence_ids": ["ev1"]}]
            ),
        ]
    )
    croma = FakeCromaClient({"disciplinary_records": procuraduria_payload("NIT")})
    case = await run_investigation(QUESTION, provider=provider, croma=croma, config=config)

    assert len(croma.calls) == 2  # la tercera entidad nunca se consulta
    assert case.status == "partial"
    assert any("max_entities=2" in u for u in case.unknowns)


async def test_max_depth_enforced_on_discovered_chain():
    """El representante legal descubierto en RUES queda a profundidad 2."""
    config = LoopConfig(max_depth=1)
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
            "fiscal_records": contraloria_payload(),
        }
    )
    case = await run_investigation(QUESTION, provider=provider, croma=croma, config=config)

    assert [method for method, _ in croma.calls] == ["entity_by_nit"]  # nunca sigue la rama
    assert case.status == "partial"
    assert any("max_depth=1" in u for u in case.unknowns)


# --- Desambiguación ---


async def test_multiple_candidates_pause_with_needs_disambiguation():
    provider = FakeProvider([resp_tool("rues_entities_by_name", name="ejemplo")])
    croma = FakeCromaClient({"entities_by_name": entities_by_name_payload(2)})

    case = await run_investigation(QUESTION, provider=provider, croma=croma)

    assert case.status == "needs_disambiguation"
    assert case.findings == []
    assert [c.id for c in case.candidates] == ["co:nit:900000011", "co:nit:900000022"]
    assert all(c.detail for c in case.candidates)
    # La consulta sí quedó registrada como ok: la fuente respondió.
    assert [s.status for s in case.sources_consulted] == ["ok"]
    assert len(provider.calls) == 1  # el loop paró y espera al usuario
    contract_dict = case.to_contract_dict()
    assert len(contract_dict["candidates"]) == 2


async def test_candidate_id_resumes_past_disambiguation():
    provider = FakeProvider(
        [
            resp_tool("rues_entities_by_name", name="ejemplo"),
            finalize_response(
                findings=[
                    {"title": "Entidad seleccionada", "narrative": "Se continuó con la elegida.",
                     "evidence_ids": ["ev1"]}
                ]
            ),
        ]
    )
    croma = FakeCromaClient({"entities_by_name": entities_by_name_payload(2)})

    case = await run_investigation(
        QUESTION, candidate_id=f"co:nit:{NIT_EJEMPLO}", provider=provider, croma=croma
    )

    assert case.status == "complete"
    assert case.candidates is None
    assert len(case.findings) == 1
    assert "seleccionó" in case.findings[0].evidence[0].claim


# --- Degradación: una fuente cae, la investigación sigue ---


async def test_source_failure_degrades_to_partial_and_continues():
    provider = FakeProvider(
        [
            resp_tool("rues_entity_by_nit", document_number=NIT_EJEMPLO),
            resp_tool("contraloria_fiscal_records", document_number=CC_REP_LEGAL),
            finalize_response(
                findings=[
                    {"title": "Identidad registral", "narrative": "Empresa activa en RUES.",
                     "evidence_ids": ["ev1"]}
                ],
                unknowns=["Contraloría no respondió."],
            ),
        ]
    )
    croma = FakeCromaClient(
        {
            "entity_by_nit": rues_by_nit_payload(),
            "fiscal_records": CromaUnavailable("timeout simulado", endpoint="fiscal-records"),
        }
    )

    case = await run_investigation(QUESTION, provider=provider, croma=croma)

    assert case.status == "partial"
    by_source = {s.source: s.status for s in case.sources_consulted}
    assert by_source["croma:rues:entity-by-nit"] == "ok"
    assert by_source["croma:contraloria:fiscal-records"] == "error"
    # La investigación NO crasheó: hay hallazgo con la evidencia que sí hubo.
    assert len(case.findings) == 1
    assert any("status=error" in u for u in case.unknowns)


# --- Gate de evidencia ---


async def test_finding_citing_nonexistent_evidence_is_discarded(
    caplog: pytest.LogCaptureFixture,
):
    provider = FakeProvider(
        [
            resp_tool("rues_entity_by_nit", document_number=NIT_EJEMPLO),
            finalize_response(
                findings=[
                    {"title": "Con evidencia real", "narrative": "Cita una ref válida.",
                     "evidence_ids": ["ev1", "ev999"]},
                    {"title": "Inventado", "narrative": "Solo cita refs inexistentes.",
                     "evidence_ids": ["ev777"]},
                ]
            ),
        ]
    )
    croma = FakeCromaClient({"entity_by_nit": rues_by_nit_payload()})

    with caplog.at_level("WARNING", logger="traza.agent.loop"):
        case = await run_investigation(QUESTION, provider=provider, croma=croma)

    assert len(case.findings) == 1
    assert case.findings[0].title == "Con evidencia real"
    assert len(case.findings[0].evidence) == 1  # ev999 descartada
    assert "ev999" in caplog.text and "ev777" in caplog.text


def test_tampered_derived_is_rejected_at_assembly(caplog: pytest.LogCaptureFixture):
    """Defensa en profundidad: un derived con cadena rota inyectado en el
    store NO entra al expediente aunque el LLM lo cite."""
    store = EvidenceStore()
    ref = store.ingest_raw(
        RawResponse(
            source="croma:secop:contracts-by-provider",
            endpoint="/fake",
            url="https://croma.test/fake",
            status_code=200,
            fetched_at="2026-08-14T00:00:00+00:00",
            payload={"data": {}},
            body_text="{}",
        )
    )
    tampered = DerivedEvidence(
        claim="cálculo amañado",
        calculation="1 / 2",
        calculation_steps=[CalculationStep(operation="divide", inputs=[1, 2], output=0.9)],
        sources=[ref],
    )
    store._evidence["evX"] = tampered  # inyección directa, saltándose add_derived

    with caplog.at_level("WARNING", logger="traza.agent.loop"):
        case = assemble_case_file(
            question=QUESTION,
            draft={
                "findings": [
                    {"title": "t", "narrative": "n", "evidence_ids": ["evX"]}
                ],
                "entities": [],
                "unknowns": [],
                "next_steps": [],
            },
            store=store,
            sources_consulted=[],
            degraded=False,
            limit_notes=[],
        )

    assert case.findings == []
    assert "no re-verifica" in caplog.text


# --- Protocolo de cierre ---


async def test_text_only_response_gets_nudged_to_finalize():
    provider = FakeProvider(
        [
            LLMResponse(content="Voy a resumir en texto libre.", tool_calls=()),
            finalize_response(unknowns=["Sin consultas ejecutadas."]),
        ]
    )
    croma = FakeCromaClient({})
    case = await run_investigation(QUESTION, provider=provider, croma=croma)

    assert len(provider.calls) == 2
    assert case.status == "complete"
    assert case.findings == []


# --- scope_note (contrato v0.2): rol asumido para la investigada ---


def processes_payload_for(document: str) -> dict[str, Any]:
    """processes_payload con el document_number del data ajustado al consultado."""
    payload = processes_payload()
    payload["data"]["document_number"] = document
    return payload


PROVIDER_NOTE = (
    "Esta investigación trata a Empresa Ejemplo S.A.S. como proveedor de "
    "contratos públicos (no como entidad contratante)."
)
CONTRACTING_NOTE = (
    "Esta investigación trata a Empresa Ejemplo S.A.S. como entidad contratante "
    "(no como proveedor)."
)
BOTH_NOTE = (
    "Esta investigación examina a Empresa Ejemplo S.A.S. en ambos roles: como "
    "proveedor de contratos públicos y como entidad contratante."
)


async def test_scope_note_provider_role_only():
    provider = FakeProvider(
        [
            resp_tool("rues_entity_by_nit", document_number=NIT_EJEMPLO),
            resp_tool("secop_contracts_by_provider", document_number=NIT_EJEMPLO),
            finalize_response(
                findings=[{"title": "t", "narrative": "n", "evidence_ids": ["ev1"]}]
            ),
        ]
    )
    croma = FakeCromaClient(
        {
            "entity_by_nit": rues_by_nit_payload(),
            "contracts_by_provider": contracts_payload(),
        }
    )
    case = await run_investigation(QUESTION, provider=provider, croma=croma)

    assert case.scope_note == PROVIDER_NOTE
    assert case.to_contract_dict()["scope_note"] == PROVIDER_NOTE


async def test_scope_note_contracting_entity_role_only():
    provider = FakeProvider(
        [
            resp_tool("rues_entity_by_nit", document_number=NIT_EJEMPLO),
            resp_tool("secop_processes_by_entity", document_number=NIT_EJEMPLO),
            finalize_response(
                findings=[{"title": "t", "narrative": "n", "evidence_ids": ["ev1"]}]
            ),
        ]
    )
    croma = FakeCromaClient(
        {
            "entity_by_nit": rues_by_nit_payload(),
            "processes_by_entity": processes_payload_for(NIT_EJEMPLO),
        }
    )
    case = await run_investigation(QUESTION, provider=provider, croma=croma)

    assert case.scope_note == CONTRACTING_NOTE


async def test_scope_note_both_roles():
    provider = FakeProvider(
        [
            resp_tool("rues_entity_by_nit", document_number=NIT_EJEMPLO),
            resp_tool("secop_contracts_by_provider", document_number=NIT_EJEMPLO),
            resp_tool("secop_processes_by_entity", document_number=NIT_EJEMPLO),
            finalize_response(
                findings=[{"title": "t", "narrative": "n", "evidence_ids": ["ev1"]}]
            ),
        ]
    )
    croma = FakeCromaClient(
        {
            "entity_by_nit": rues_by_nit_payload(),
            "contracts_by_provider": contracts_payload(),
            "processes_by_entity": processes_payload_for(NIT_EJEMPLO),
        }
    )
    case = await run_investigation(QUESTION, provider=provider, croma=croma)

    assert case.scope_note == BOTH_NOTE


async def test_scope_note_absent_without_secop_for_investigated():
    """Sin consultas SECOP para la investigada: scope_note = None y AUSENTE del JSON."""
    provider = FakeProvider(
        [
            resp_tool("rues_entity_by_nit", document_number=NIT_EJEMPLO),
            resp_tool("procuraduria_disciplinary_records",
                      document_number=NIT_EJEMPLO, document_type="NIT"),
            finalize_response(
                findings=[{"title": "t", "narrative": "n", "evidence_ids": ["ev1"]}]
            ),
        ]
    )
    croma = FakeCromaClient(
        {
            "entity_by_nit": rues_by_nit_payload(),
            "disciplinary_records": procuraduria_payload("NIT"),
        }
    )
    case = await run_investigation(QUESTION, provider=provider, croma=croma)

    assert case.scope_note is None
    assert "scope_note" not in case.to_contract_dict()


async def test_scope_note_ignores_processes_of_other_entities():
    """processes_by_entity con el NIT de OTRA entidad (una contratante descubierta
    en los contratos) NO dispara el rol de entidad contratante."""
    provider = FakeProvider(
        [
            resp_tool("rues_entity_by_nit", document_number=NIT_EJEMPLO),
            resp_tool("secop_contracts_by_provider", document_number=NIT_EJEMPLO),
            resp_tool("secop_processes_by_entity", document_number="800000001"),
            finalize_response(
                findings=[{"title": "t", "narrative": "n", "evidence_ids": ["ev1"]}]
            ),
        ]
    )
    croma = FakeCromaClient(
        {
            "entity_by_nit": rues_by_nit_payload(),
            "contracts_by_provider": contracts_payload(),
            "processes_by_entity": processes_payload_for("800000001"),
        }
    )
    case = await run_investigation(QUESTION, provider=provider, croma=croma)

    assert case.scope_note == PROVIDER_NOTE  # solo proveedor: la otra entidad no cuenta


async def test_scope_note_name_falls_back_to_nit_without_rues():
    """Sin RUES no hay razón social: la plantilla usa 'la entidad con NIT <doc>'."""
    provider = FakeProvider(
        [
            resp_tool("secop_contracts_by_provider", document_number=NIT_EJEMPLO),
            finalize_response(
                findings=[{"title": "t", "narrative": "n", "evidence_ids": ["ev1"]}]
            ),
        ]
    )
    croma = FakeCromaClient({"contracts_by_provider": contracts_payload()})
    case = await run_investigation(QUESTION, provider=provider, croma=croma)

    assert case.scope_note == (
        f"Esta investigación trata a la entidad con NIT {NIT_EJEMPLO} como "
        "proveedor de contratos públicos (no como entidad contratante)."
    )


# --- source_urls (contrato v0.3): links oficiales de contratos citados ---


async def test_source_urls_filtered_to_cited_contract_refs():
    """v0.3: source_urls contiene SOLO los contratos citados en sources de la
    evidencia del expediente (no los 5 registrados en el store), con la url
    oficial capturada del payload crudo."""
    provider = FakeProvider(
        [
            resp_tool("rues_entity_by_nit", document_number=NIT_EJEMPLO),
            resp_tool("secop_contracts_by_provider", document_number=NIT_EJEMPLO),
            finalize_response(
                findings=[
                    {
                        "title": "Concentración por conteo",
                        "narrative": "La entidad top concentra los contratos.",
                        # ev5: derived pct por conteo, respaldada por los 3
                        # contratos de Entidad Ficticia Uno.
                        "evidence_ids": ["ev5"],
                    }
                ]
            ),
        ]
    )
    croma = FakeCromaClient(
        {
            "entity_by_nit": rues_by_nit_payload(),
            "contracts_by_provider": contracts_payload(),
        }
    )
    case = await run_investigation(QUESTION, provider=provider, croma=croma)

    cited = {
        f"croma:secop:contract:CO1.PCCNTR.99900{i}" for i in (1, 2, 3)
    }
    assert case.source_urls is not None
    assert set(case.source_urls) == cited  # 999004/999005 registrados pero NO citados
    for ref, url in case.source_urls.items():
        contract_id = ref.removeprefix("croma:secop:contract:")
        assert url == f"https://secop.example/proceso/{contract_id}"
    # El JSON del contrato lleva la clave tal cual.
    assert case.to_contract_dict()["source_urls"] == case.source_urls


async def test_source_urls_absent_without_cited_contracts():
    """Expediente sin contratos citados (solo evidencia RUES): source_urls es
    None y la clave se OMITE del JSON (exclude_none, como candidates)."""
    provider = FakeProvider(
        [
            resp_tool("rues_entity_by_nit", document_number=NIT_EJEMPLO),
            finalize_response(
                findings=[
                    {"title": "Identidad registral", "narrative": "Empresa activa en RUES.",
                     "evidence_ids": ["ev1"]}
                ]
            ),
        ]
    )
    croma = FakeCromaClient({"entity_by_nit": rues_by_nit_payload()})
    case = await run_investigation(QUESTION, provider=provider, croma=croma)

    assert case.source_urls is None
    assert "source_urls" not in case.to_contract_dict()


async def test_source_urls_absent_with_zero_contracts_result():
    """SECOP responde 0 contratos: el cero entra como hecho pero no hay refs de
    contrato, así que el JSON no lleva source_urls."""
    provider = FakeProvider(
        [
            resp_tool("secop_contracts_by_provider", document_number=NIT_EJEMPLO),
            finalize_response(
                findings=[
                    {"title": "Sin contratos en SECOP", "narrative": "Cero registros.",
                     "evidence_ids": ["ev1"]}
                ]
            ),
        ]
    )
    croma = FakeCromaClient({"contracts_by_provider": empty_contracts_payload()})
    case = await run_investigation(QUESTION, provider=provider, croma=croma)

    assert case.source_urls is None
    assert "source_urls" not in case.to_contract_dict()


async def test_model_never_finalizing_yields_partial_fallback():
    provider = FakeProvider(
        [
            LLMResponse(content="bla", tool_calls=()),
            LLMResponse(content="bla", tool_calls=()),
            LLMResponse(content="bla", tool_calls=()),
        ]
    )
    croma = FakeCromaClient({})
    case = await run_investigation(QUESTION, provider=provider, croma=croma)

    assert case.status == "partial"
    assert any("borrador estructurado" in u for u in case.unknowns)
    assert case.findings == []
