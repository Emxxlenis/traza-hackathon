"""Tests del Evidence Layer.

Todos los datos son SINTÉTICOS y claramente ficticios (los mismos nombres de
ejemplo del contrato v0). Nunca poner empresas ni entidades reales aquí.
"""

from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from evidence.models import (
    CalculationStep,
    Candidate,
    CaseFile,
    DerivedEvidence,
    DirectEvidence,
    Entity,
    Evidence,
    Finding,
    SourceConsulted,
)
from evidence.verify import verify_derived

# ---------------------------------------------------------------------------
# Fixtures sintéticas
# ---------------------------------------------------------------------------


def make_direct(**overrides) -> DirectEvidence:
    base = {
        "claim": "Empresa Ejemplo S.A.S. está registrada como activa",
        "source": "croma:rues:entity-by-nit",
        "raw_reference": "<id o campo exacto de la respuesta — forma final pendiente de capturas reales>",
    }
    base.update(overrides)
    return DirectEvidence(**base)


def make_steps() -> list[CalculationStep]:
    """Cadena correcta: 12 / 17 -> *100 -> round(_, 1) = 70.6."""
    return [
        CalculationStep(operation="divide", inputs=[12, 17], output=0.7058823529411765),
        CalculationStep(operation="multiply", inputs=["$0", 100], output=70.58823529411765),
        CalculationStep(operation="round", inputs=["$1", 1], output=70.6),
    ]


def make_derived(**overrides) -> DerivedEvidence:
    base = {
        "claim": "El 70.6% de los contratos de Empresa Ejemplo provienen de Entidad Ficticia",
        "calculation": "12 / 17",
        "calculation_steps": make_steps(),
        "sources": ["croma:secop:contract:123", "croma:secop:contract:456"],
    }
    base.update(overrides)
    return DerivedEvidence(**base)


def make_case_file(**overrides) -> CaseFile:
    base = {
        "question": "¿Por qué Empresa Ejemplo S.A.S. concentra tantos contratos con la Entidad Ficticia?",
        "status": "complete",
        "entities": [
            Entity(id="co:nit:900000001", name="Empresa Ejemplo S.A.S.", role="investigada"),
            Entity(id="co:entidad:ENT-001", name="Entidad Ficticia de Ejemplo", role="contratante"),
        ],
        "sources_consulted": [
            SourceConsulted(
                source="croma:rues:entity-by-nit",
                at=datetime(2026, 8, 14, 20, 0, 0, tzinfo=UTC),
                status="ok",
            ),
            SourceConsulted(
                source="croma:secop:contracts-by-provider",
                at=datetime(2026, 8, 14, 20, 1, 0, tzinfo=UTC),
                status="ok",
            ),
        ],
        "findings": [
            Finding(
                id="f1",
                title="Concentración de contratos en una sola entidad contratante",
                narrative=(
                    "Texto corto legible; TODO lo afirmado aquí debe estar respaldado "
                    "por los objetos de evidence[] — nunca paráfrasis libre sin objeto detrás."
                ),
                evidence=[make_direct(), make_derived()],
            )
        ],
        "unknowns": ["La evidencia no permite concluir X — se declara explícitamente."],
        "next_steps": ["Qué valdría la pena investigar después."],
    }
    base.update(overrides)
    return CaseFile(**base)


# JSON del contrato v0, verbatim de docs/contracts/case-file.v0.md.
# Entidades ficticias, como exige el propio contrato.
CONTRACT_V0_EXAMPLE = {
    "question": "¿Por qué Empresa Ejemplo S.A.S. concentra tantos contratos con la Entidad Ficticia?",
    "status": "complete",
    "entities": [
        {"id": "co:nit:900000001", "name": "Empresa Ejemplo S.A.S.", "role": "investigada"},
        {"id": "co:entidad:ENT-001", "name": "Entidad Ficticia de Ejemplo", "role": "contratante"},
    ],
    "sources_consulted": [
        {"source": "croma:rues:entity-by-nit", "at": "2026-08-14T20:00:00Z", "status": "ok"},
        {"source": "croma:secop:contracts-by-provider", "at": "2026-08-14T20:01:00Z", "status": "ok"},
    ],
    "findings": [
        {
            "id": "f1",
            "title": "Concentración de contratos en una sola entidad contratante",
            "narrative": (
                "Texto corto legible; TODO lo afirmado aquí debe estar respaldado "
                "por los objetos de evidence[] — nunca paráfrasis libre sin objeto detrás."
            ),
            "evidence": [
                {
                    "claim": "Empresa Ejemplo S.A.S. está registrada como activa",
                    "type": "direct",
                    "source": "croma:rues:entity-by-nit",
                    "raw_reference": "<id o campo exacto de la respuesta — forma final pendiente de capturas reales>",
                },
                {
                    "claim": "El 70.6% de los contratos de Empresa Ejemplo provienen de Entidad Ficticia",
                    "type": "derived",
                    "calculation": "12 / 17",
                    "sources": ["croma:secop:contract:123", "croma:secop:contract:456"],
                },
            ],
        }
    ],
    "unknowns": ["La evidencia no permite concluir X — se declara explícitamente."],
    "next_steps": ["Qué valdría la pena investigar después."],
}


# ---------------------------------------------------------------------------
# SourceRef
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ref",
    [
        "croma:rues:entity-by-nit",
        "croma:secop:contracts-by-provider",
        "croma:secop:contract:123",
        "croma:secop:contract:CO-2026.001",
    ],
)
def test_source_ref_valid(ref):
    assert make_direct(source=ref).source == ref


@pytest.mark.parametrize(
    "ref",
    [
        "secop:contract:123",  # sin prefijo croma
        "croma:secop",  # falta el endpoint/tipo
        "croma::contract",  # segmento vacío
        "croma:secop:contract:123:extra",  # demasiados segmentos
        "no es una referencia",
        "",
    ],
)
def test_source_ref_invalid(ref):
    with pytest.raises(ValidationError):
        make_direct(source=ref)


# ---------------------------------------------------------------------------
# DirectEvidence
# ---------------------------------------------------------------------------


def test_direct_evidence_valid():
    ev = make_direct()
    assert ev.type == "direct"
    assert ev.raw_reference


def test_direct_evidence_rejects_wrong_type():
    with pytest.raises(ValidationError):
        make_direct(type="derived")


def test_direct_evidence_rejects_empty_raw_reference():
    with pytest.raises(ValidationError):
        make_direct(raw_reference="")


def test_direct_evidence_rejects_extra_fields():
    # Ningún campo tipo score/veredicto puede colarse en la evidencia.
    with pytest.raises(ValidationError):
        make_direct(risk_score=0.9)


# ---------------------------------------------------------------------------
# DerivedEvidence
# ---------------------------------------------------------------------------


def test_derived_evidence_valid():
    ev = make_derived()
    assert ev.type == "derived"
    assert len(ev.calculation_steps) == 3
    assert len(ev.sources) == 2


def test_derived_evidence_rejects_empty_sources():
    with pytest.raises(ValidationError):
        make_derived(sources=[])


def test_derived_evidence_rejects_empty_steps():
    with pytest.raises(ValidationError):
        make_derived(calculation_steps=[])


# ---------------------------------------------------------------------------
# Finding — sin evidencia es IMPOSIBLE
# ---------------------------------------------------------------------------


def test_finding_valid():
    finding = Finding(
        id="f1",
        title="Título ficticio",
        narrative="Narrativa ficticia respaldada por evidencia.",
        evidence=[make_direct()],
    )
    assert len(finding.evidence) == 1


def test_finding_without_evidence_is_impossible():
    with pytest.raises(ValidationError):
        Finding(id="f1", title="t", narrative="n", evidence=[])


def test_finding_missing_evidence_field_is_impossible():
    with pytest.raises(ValidationError):
        Finding(id="f1", title="t", narrative="n")


def test_hypothesis_type_is_impossible():
    # No existe 'hypothesis' en el MVP: la unión discriminada lo rechaza.
    with pytest.raises(ValidationError):
        TypeAdapter(Evidence).validate_python(
            {
                "claim": "afirmación especulativa",
                "type": "hypothesis",
                "source": "croma:rues:entity-by-nit",
                "raw_reference": "x",
            }
        )


# ---------------------------------------------------------------------------
# verify_derived
# ---------------------------------------------------------------------------


def test_verify_accepts_correct_chain():
    result = verify_derived(make_derived())
    assert result.valid
    assert result.errors == []
    assert result.recomputed_output == pytest.approx(70.6)
    assert result.declared_output == pytest.approx(70.6)


def test_verify_rejects_final_output_mismatch():
    steps = make_steps()
    steps[-1] = CalculationStep(operation="round", inputs=["$1", 1], output=99.9)
    result = verify_derived(make_derived(calculation_steps=steps))
    assert not result.valid
    assert any("no coincide" in e for e in result.errors)
    # El recomputado sigue siendo el correcto; el declarado es el falso.
    assert result.recomputed_output == pytest.approx(70.6)
    assert result.declared_output == pytest.approx(99.9)


def test_verify_rejects_intermediate_output_mismatch():
    steps = make_steps()
    steps[0] = CalculationStep(operation="divide", inputs=[12, 17], output=0.5)
    result = verify_derived(make_derived(calculation_steps=steps))
    assert not result.valid
    assert any("paso 0" in e for e in result.errors)


def test_verify_rejects_unknown_operation():
    steps = [CalculationStep(operation="magia", inputs=[1, 2], output=3)]
    result = verify_derived(make_derived(calculation_steps=steps))
    assert not result.valid
    assert any("operación desconocida" in e for e in result.errors)


def test_verify_rejects_forward_and_self_references():
    steps = [
        CalculationStep(operation="sum", inputs=["$0", 1], output=1),  # a sí mismo
        CalculationStep(operation="sum", inputs=["$5", 1], output=1),  # hacia adelante
    ]
    result = verify_derived(make_derived(calculation_steps=steps))
    assert not result.valid
    assert sum("no apunta a un paso anterior" in e for e in result.errors) == 2


def test_verify_rejects_malformed_reference():
    steps = [CalculationStep(operation="sum", inputs=["$abc"], output=1)]
    result = verify_derived(make_derived(calculation_steps=steps))
    assert not result.valid
    assert any("no es un número ni una referencia" in e for e in result.errors)


def test_verify_rejects_division_by_zero():
    steps = [CalculationStep(operation="divide", inputs=[1, 0], output=0)]
    result = verify_derived(make_derived(calculation_steps=steps))
    assert not result.valid
    assert any("división por cero" in e for e in result.errors)


def test_verify_rejects_bad_arity():
    steps = [CalculationStep(operation="divide", inputs=[1, 2, 3], output=0.5)]
    result = verify_derived(make_derived(calculation_steps=steps))
    assert not result.valid
    assert any("exactamente 2 inputs" in e for e in result.errors)


def test_verify_reference_resolves_against_recomputed_value():
    # El paso 0 declara un output falso; el paso 1 debe resolver $0 contra el
    # valor RECOMPUTADO (6), no el declarado (100). Así un output falso no
    # contamina la cadena y ambos errores se reportan.
    steps = [
        CalculationStep(operation="sum", inputs=[2, 4], output=100),
        CalculationStep(operation="multiply", inputs=["$0", 10], output=60),
    ]
    result = verify_derived(make_derived(calculation_steps=steps))
    assert not result.valid
    assert any("paso 0" in e for e in result.errors)
    # El paso 1 NO genera error: 6 * 10 = 60 coincide con su declaración.
    assert not any("paso 1" in e for e in result.errors)


# ---------------------------------------------------------------------------
# CaseFile — contrato v0
# ---------------------------------------------------------------------------


def test_case_file_serializes_to_contract_v0():
    dumped = make_case_file().to_contract_dict()

    # `calculation_steps` es la ÚNICA adición propuesta al contrato v0
    # (ver docs/evidence-layer.md); se separa antes de comparar verbatim.
    derived = dumped["findings"][0]["evidence"][1]
    steps = derived.pop("calculation_steps")
    assert steps, "la cadena re-ejecutable debe existir y no estar vacía"

    assert dumped == CONTRACT_V0_EXAMPLE


def test_case_file_round_trip():
    case = make_case_file()
    reloaded = CaseFile.model_validate_json(case.to_contract_json())
    assert reloaded == case


def test_case_file_candidates_only_with_needs_disambiguation():
    with pytest.raises(ValidationError):
        make_case_file(candidates=[Candidate(id="co:nit:900000002", name="Otra Empresa Ficticia")])


def test_case_file_needs_disambiguation_requires_candidates():
    with pytest.raises(ValidationError):
        make_case_file(status="needs_disambiguation", findings=[])


def test_case_file_needs_disambiguation_excludes_findings():
    with pytest.raises(ValidationError):
        make_case_file(
            status="needs_disambiguation",
            candidates=[Candidate(id="co:nit:900000002", name="Otra Empresa Ficticia")],
        )


def test_case_file_needs_disambiguation_valid_and_serializes_candidates():
    case = make_case_file(
        status="needs_disambiguation",
        findings=[],
        candidates=[
            Candidate(id="co:nit:900000002", name="Empresa Homónima Ficticia S.A.S."),
            Candidate(
                id="co:nit:900000003",
                name="Empresa Homónima Ficticia Ltda.",
                detail="Registrada en otra ciudad ficticia",
            ),
        ],
    )
    dumped = case.to_contract_dict()
    assert dumped["status"] == "needs_disambiguation"
    assert len(dumped["candidates"]) == 2
    assert dumped["findings"] == []


def test_case_file_omits_candidates_key_when_not_disambiguating():
    dumped = make_case_file().to_contract_dict()
    assert "candidates" not in dumped


def test_case_file_rejects_unknown_status():
    with pytest.raises(ValidationError):
        make_case_file(status="verdict")


def test_case_file_rejects_extra_fields():
    # Un score de riesgo global es imposible de colar en el expediente.
    with pytest.raises(ValidationError):
        make_case_file(risk_score=0.87)
