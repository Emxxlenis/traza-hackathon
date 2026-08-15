"""Tests del EvidenceStore: refs estables y verify_derived como puerta dura.

Sin red; valores ficticios.
"""

from __future__ import annotations

import json

import pytest

from agent.store import EvidenceStore
from croma_client.envelope import RawResponse
from evidence.models import CalculationStep, DerivedEvidence


def make_raw(source: str = "croma:rues:entity-by-nit", payload: dict | None = None) -> RawResponse:
    payload = payload if payload is not None else {"data": {"found": True}}
    return RawResponse(
        source=source,
        endpoint="/fake",
        url="https://croma.test/fake",
        status_code=200,
        fetched_at="2026-08-14T00:00:00+00:00",
        payload=payload,
        body_text=json.dumps(payload),
    )


def test_ingest_raw_assigns_stable_sequential_refs():
    store = EvidenceStore()
    ref1 = store.ingest_raw(make_raw("croma:rues:entity-by-nit"))
    ref2 = store.ingest_raw(make_raw("croma:secop:contracts-by-provider"))
    assert ref1 == "croma:rues:entity-by-nit:1"
    assert ref2 == "croma:secop:contracts-by-provider:2"
    assert store.raw_by_ref(ref1).source == "croma:rues:entity-by-nit"
    assert store.has_ref(ref1) and store.has_ref(ref2)
    assert not store.has_ref("croma:rues:entity-by-nit:99")


def test_register_contract_ref_uses_real_contract_id():
    store = EvidenceStore()
    raw_ref = store.ingest_raw(make_raw("croma:secop:contracts-by-provider"))
    ref = store.register_contract_ref("CO1.PCCNTR.999001", raw_ref)
    assert ref == "croma:secop:contract:CO1.PCCNTR.999001"
    assert store.has_ref(ref)
    # El ref del contrato resuelve al raw padre.
    assert store.raw_by_ref(ref) is store.raw_by_ref(raw_ref)
    # Un raw padre desconocido se rechaza.
    assert store.register_contract_ref("CO1.PCCNTR.999002", "croma:secop:nada:9") is None
    # Un id vacío o basura que no forma SourceRef válido se rechaza.
    assert store.register_contract_ref("", raw_ref) is None


def test_add_direct_requires_existing_ref():
    store = EvidenceStore()
    assert store.add_direct("claim", "croma:rues:entity-by-nit:1", "data.found") is None
    ref = store.ingest_raw(make_raw())
    evidence_id = store.add_direct("Empresa Ejemplo activa", ref, "data.entity.status")
    assert evidence_id == "ev1"
    assert store.get("ev1").source == ref
    assert store.get("ev404") is None


def test_add_derived_accepts_valid_chain():
    store = EvidenceStore()
    ref = store.ingest_raw(make_raw("croma:secop:contracts-by-provider"))
    contract_ref = store.register_contract_ref("CO1.PCCNTR.999001", ref)
    evidence_id = store.add_derived(
        claim="El 60% de los contratos (3 de 5)",
        calculation="3 / 5 * 100",
        steps=[
            CalculationStep(operation="divide", inputs=[3, 5], output=0.6),
            CalculationStep(operation="multiply", inputs=["$0", 100], output=60.0),
            CalculationStep(operation="round", inputs=["$1", 1], output=60.0),
        ],
        sources=[ref, contract_ref],
    )
    assert evidence_id == "ev1"
    derived = store.get(evidence_id)
    assert isinstance(derived, DerivedEvidence)
    assert derived.sources == [ref, contract_ref]


def test_add_derived_rejects_broken_chain_with_log(caplog: pytest.LogCaptureFixture):
    """Cadena rota (output declarado falso) => NO entra al store, con warning."""
    store = EvidenceStore()
    ref = store.ingest_raw(make_raw("croma:secop:contracts-by-provider"))
    with caplog.at_level("WARNING", logger="traza.agent.store"):
        evidence_id = store.add_derived(
            claim="porcentaje amañado",
            calculation="3 / 5",
            steps=[CalculationStep(operation="divide", inputs=[3, 5], output=0.9)],
            sources=[ref],
        )
    assert evidence_id is None
    assert store.evidence_count == 0
    assert "verify_derived" in caplog.text


def test_add_derived_rejects_unknown_sources_and_operations():
    store = EvidenceStore()
    ref = store.ingest_raw(make_raw("croma:secop:contracts-by-provider"))
    # Fuente que no está en el store.
    assert (
        store.add_derived(
            claim="x",
            calculation="1+1",
            steps=[CalculationStep(operation="sum", inputs=[1, 1], output=2.0)],
            sources=["croma:secop:contract:CO1.PCCNTR.999999"],
        )
        is None
    )
    # Operación fuera del registro cerrado.
    assert (
        store.add_derived(
            claim="x",
            calculation="exp(1)",
            steps=[CalculationStep(operation="exponential", inputs=[1], output=2.71)],
            sources=[ref],
        )
        is None
    )
    assert store.evidence_count == 0
