"""Tests de los reducers deterministas del agente.

TODOS los fixtures usan valores FICTICIOS (empresas "Ejemplo S.A.S.", NITs
9000000xx, contract_ids inventados con formato real CO1.PCCNTR.9990xx).
PROHIBIDO copiar datos reales aquí. Sin red.

Los builders de payloads replican la FORMA verificada de las respuestas de
Croma (docs/croma-schema.md) y se reutilizan desde test_agent_loop.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent.reducers import (
    DerivedProposal,
    filter_candidates,
    reduce_contracts_by_provider,
    reduce_disciplinary_records,
    reduce_entities_by_name,
    reduce_entity_by_nit,
    reduce_fiscal_records,
    reduce_processes_by_entity,
    reduce_tool_result,
)
from evidence.models import DerivedEvidence
from evidence.verify import verify_derived


def assert_proposal_verifies(proposal: DerivedProposal) -> None:
    """Toda proposal derivada debe recomputar EXACTAMENTE en verify_derived."""
    evidence = DerivedEvidence(
        claim=proposal.claim,
        calculation=proposal.calculation,
        calculation_steps=list(proposal.steps),
        sources=["croma:secop:contracts-by-provider:1"],
    )
    result = verify_derived(evidence)
    assert result.valid, f"{proposal.claim}: {result.errors}"

# --- Builders de payloads con forma real y valores ficticios ---

NIT_EJEMPLO = "900000011"
NIT_EJEMPLO_2 = "900000022"
CC_REP_LEGAL = "10000001"  # cédula ficticia del representante legal


def make_contract(
    contract_id: str,
    entity: str,
    entity_nit: str,
    value: float,
    sign_date: str | None,
    obj: str = "Suministro de servicios de ejemplo para pruebas",
) -> dict[str, Any]:
    return {
        "contract_id": contract_id,
        "reference": f"REF-{contract_id[-6:]}",
        "entity": entity,
        "entity_nit": entity_nit,
        "provider": "Empresa Ejemplo S.A.S.",
        "provider_document": NIT_EJEMPLO,
        "provider_document_type": "NIT",
        "legal_rep_name": "Persona Ejemplo Uno",
        "legal_rep_document": None,
        "status": "Ejecutado",
        "contract_type": "Suministro",
        "modality": "Contratación directa",
        "object": obj,
        "value": value,
        "invoiced_value": value,
        "paid_value": value,
        "sign_date": sign_date,
        "start_date": sign_date,
        "end_date": None,
        "duration": None,
        "supervisor": None,
        "funding_origin": "Recursos propios",
        "sector": "Ejemplo",
        "url": f"https://secop.example/proceso/{contract_id}",
    }


def contracts_payload(capped: bool = False) -> dict[str, Any]:
    """5 contratos ficticios: 3 con Entidad Uno (60%), 2 con Entidad Dos."""
    contracts = [
        make_contract("CO1.PCCNTR.999001", "Entidad Ficticia Uno", "800000001",
                      100_000_000.0, "2023-01-15"),
        make_contract("CO1.PCCNTR.999002", "Entidad Ficticia Uno", "800000001",
                      200_000_000.0, "2024-03-01"),
        make_contract("CO1.PCCNTR.999003", "Entidad Ficticia Uno", "800000001",
                      300_000_000.0, "2025-06-30"),
        make_contract("CO1.PCCNTR.999004", "Entidad Ficticia Dos", "800000002",
                      50_000_000.0, "2022-05-10"),
        make_contract("CO1.PCCNTR.999005", "Entidad Ficticia Dos", "800000002",
                      50_000_000.0, "2023-11-20"),
    ]
    total = 855 if capped else len(contracts)
    return {
        "data": {
            "document_number": NIT_EJEMPLO,
            "entity_nit": None,
            "from_date": None,
            "to_date": None,
            "count": len(contracts),
            "capped": capped,
            "contracts": contracts,
            "pagination": {"total": total, "page_size": 500,
                           "total_pages": 2 if capped else 1, "page": 1},
        }
    }


def empty_contracts_payload(document: str = NIT_EJEMPLO) -> dict[str, Any]:
    """SECOP responde OK pero sin contratos: expediente vacío legítimo."""
    return {
        "data": {
            "document_number": document,
            "entity_nit": None,
            "from_date": None,
            "to_date": None,
            "count": 0,
            "capped": False,
            "contracts": [],
            "pagination": {"total": 0, "page_size": 500, "total_pages": 0, "page": 1},
        }
    }


def rues_by_nit_payload(found: bool = True) -> dict[str, Any]:
    if not found:
        return {"data": {"found": False, "document_number": "900000099"}}
    return {
        "data": {
            "found": True,
            "document_number": NIT_EJEMPLO,
            "entity": {
                "registry_id": "999999",
                "nit": NIT_EJEMPLO,
                "verification_digit": "7",
                "secondary_identification": f"0000{NIT_EJEMPLO}0",
                "name": "Empresa Ejemplo S.A.S.",
                "chamber_code": "01",
                "chamber_name": "CAMARA DE COMERCIO DE EJEMPLO",
                "registration_number": "01234567",
                "registration_status": "ACTIVA",
                "legal_organization": "SOCIEDAD POR ACCIONES SIMPLIFICADA",
                "society_type": "SOCIEDAD COMERCIAL",
                "registration_date": "2015-02-20",
                "last_renewal_date": "2026-03-15",
                "last_renewed_year": "2026",
                "cancellation_date": None,
                "primary_activity": {
                    "code": "4290",
                    "description": "Construcción de otras obras de ingeniería civil",
                },
                "certificates_sale_url": "https://rues.example/certificados",
            },
            "financials": [{"year": "2025", "total_assets": 1_000_000}],
            "renewals": [{"year": "2026", "renewal_date": "2026-03-15"}],
            "related_parties": [
                {
                    "document_number": CC_REP_LEGAL,
                    "name": "Persona Ejemplo Uno",
                    "role": "Representante Legal - Principal",
                },
                {
                    "document_number": "10000002",
                    "name": "Persona Ejemplo Dos",
                    "role": "Suplente del Representante Legal",
                },
            ],
            "notices": [],
        }
    }


def entities_by_name_payload(n: int = 2) -> dict[str, Any]:
    names = ["Empresa Ejemplo S.A.S.", "Ejemplo del Caribe S.A.S.", "Ejemplo Andino Ltda."]
    nits = [NIT_EJEMPLO, NIT_EJEMPLO_2, "900000033"]
    entities = []
    for i in range(n):
        entities.append(
            {
                "registry_id": f"88880{i}",
                "nit": None,
                "verification_digit": None,
                "name": names[i],
                "chamber_code": "01",
                "chamber_name": "CAMARA DE COMERCIO DE EJEMPLO",
                "registration_number": f"0200000{i}",
                "registration_status": "ACTIVA" if i == 0 else "CANCELADA",
                "legal_organization": "SOCIEDAD POR ACCIONES SIMPLIFICADA",
                "last_renewed_year": "2026",
                "category": "SOCIEDAD",
                "detail": {
                    "registry_id": f"88880{i}",
                    "nit": nits[i],
                    "secondary_identification": f"0000{nits[i]}0",
                    "name": names[i],
                },
            }
        )
    return {
        "data": {
            "query": "ejemplo",
            "capped": False,
            "entities": entities,
            "pagination": {"total": n, "page_size": 10, "total_pages": 1, "page": 1},
        }
    }


def procuraduria_payload(document_type: str = "NIT") -> dict[str, Any]:
    return {
        "data": {
            "found": True,
            "document_type": document_type,
            "document_type_label": "Nit" if document_type == "NIT" else "Cédula de Ciudadanía",
            "document_number": NIT_EJEMPLO if document_type == "NIT" else CC_REP_LEGAL,
            "full_name": None,
            "has_records": False,
            "status": "SIN ANTECEDENTES (ficticio)",
            "message": "El documento consultado no registra antecedentes (dato de prueba).",
            "records": [],
            "checked_at": None,
        }
    }


def contraloria_payload() -> dict[str, Any]:
    return {
        "data": {
            "found": True,
            "document_type": "CC",
            "document_type_label": "Cédula de Ciudadanía",
            "document_number": CC_REP_LEGAL,
            "is_fiscal_responsible": False,
            "verification_code": "FICT-0000001",
            "certified_at": "2026-08-14T00:00:00Z",
            "status": "NO REPORTADO (ficticio)",
            "message": "Certificado de prueba con datos ficticios.",
        }
    }


def processes_payload() -> dict[str, Any]:
    return {
        "data": {
            "document_number": "800000001",
            "from_date": None,
            "to_date": None,
            "count": 2,
            "capped": False,
            "processes": [
                {
                    "notice_uid": "NU-0001",
                    "process_id": "PE-0001",
                    "reference": "LP-001",
                    "name": "Proceso ficticio de obra menor",
                    "entity": "Entidad Ficticia Uno",
                    "entity_nit": "800000001",
                    "modality": "Licitación pública",
                    "contract_type": "Obra",
                    "base_price": 900_000_000.0,
                    "phase": "Adjudicado",
                    "procedure_status": "Cerrado",
                    "published_date": "2025-01-01",
                    "url": "https://secop.example/proceso/PE-0001",
                },
                {
                    "notice_uid": "NU-0002",
                    "process_id": "PE-0002",
                    "reference": "LP-002",
                    "name": "Proceso ficticio de suministro",
                    "entity": "Entidad Ficticia Uno",
                    "entity_nit": "800000001",
                    "modality": "Selección abreviada",
                    "contract_type": "Suministro",
                    "base_price": 100_000_000.0,
                    "phase": "Publicado",
                    "procedure_status": "Abierto",
                    "published_date": "2026-02-02",
                    "url": "https://secop.example/proceso/PE-0002",
                },
            ],
            "pagination": {"total": 2, "page_size": 500, "total_pages": 1, "page": 1},
        }
    }


# --- SECOP contratos: agregados en código ---


def test_contracts_reducer_aggregates_by_entity():
    reduction = reduce_contracts_by_provider(
        contracts_payload(), {"document_number": NIT_EJEMPLO}
    )
    summary = reduction.summary
    assert summary["contratos_recuperados"] == 5
    assert summary["total_reportado"] == 5
    assert summary["capped"] is False
    assert summary["rango_fechas"] == {"desde": "2022-05-10", "hasta": "2025-06-30"}

    top = summary["entidades"][0]
    assert top["entidad"] == "Entidad Ficticia Uno"
    assert top["contratos"] == 3
    assert top["valor_total"] == 600_000_000.0
    assert top["pct_contratos"] == 60.0
    assert summary["entidades"][1]["contratos"] == 2

    # top-5 por valor: el mayor primero, con objeto truncado y url.
    top_contract = summary["top_contratos"][0]
    assert top_contract["contract_id"] == "CO1.PCCNTR.999003"
    assert top_contract["valor"] == 300_000_000.0
    assert top_contract["url"].startswith("https://secop.example/")

    # Los 5 contract_ids reales quedan disponibles para refs.
    assert len(reduction.contract_ids) == 5
    # Entidades contratantes descubiertas (para profundidad).
    assert {d.document for d in reduction.discovered} == {"800000001", "800000002"}


def test_contracts_reducer_calculation_steps_pass_verify_derived():
    """Toda inferencia numérica nace en código: cada derived debe recomputar."""
    reduction = reduce_contracts_by_provider(
        contracts_payload(), {"document_number": NIT_EJEMPLO}
    )
    assert len(reduction.derived) == 3  # pct contratos, suma valor, pct valor
    for proposal in reduction.derived:
        evidence = DerivedEvidence(
            claim=proposal.claim,
            calculation=proposal.calculation,
            calculation_steps=list(proposal.steps),
            sources=["croma:secop:contracts-by-provider:1"],
        )
        result = verify_derived(evidence)
        assert result.valid, f"{proposal.claim}: {result.errors}"

    pct = reduction.derived[0]
    assert pct.steps[-1].output == 60.0
    share = reduction.derived[2]
    assert share.steps[-1].output == 85.7  # 600M / 700M * 100 redondeado


def test_contracts_reducer_capped_sample_is_declared():
    reduction = reduce_contracts_by_provider(
        contracts_payload(capped=True), {"document_number": NIT_EJEMPLO}
    )
    assert reduction.summary["capped"] is True
    assert reduction.summary["total_reportado"] == 855
    assert "capada" in reduction.summary["nota"]
    assert all("muestra capada" in p.claim for p in reduction.derived)


def test_contracts_reducer_empty_payload():
    reduction = reduce_contracts_by_provider(
        empty_contracts_payload(), {"document_number": NIT_EJEMPLO}
    )
    assert reduction.summary["contratos_recuperados"] == 0
    assert reduction.summary["entidades"] == []
    assert reduction.summary["rango_fechas"] is None
    assert reduction.derived == []
    assert len(reduction.direct) == 1  # el conteo literal sí es evidencia directa

    # El cero se afirma como HECHO (no como fallo) con su raw_reference.
    zero = reduction.direct[0]
    assert zero.claim == (
        f"SECOP no registra contratos para el proveedor {NIT_EJEMPLO}; total reportado: 0"
    )
    assert zero.raw_reference == "data.count"
    # La nota guía al LLM: resultado legítimo + qué NO permite concluir.
    nota = reduction.summary["nota"]
    assert "no un error" in nota
    assert "No permite concluir" in nota
    # Sin contratos no hay entidades descubiertas ni refs de contrato.
    assert reduction.discovered == []
    assert reduction.contract_ids == []


# --- SECOP contratos: NIT compartido por varias dependencias ---

NIT_DISTRITO = "800000010"  # NIT ficticio compartido por 3 dependencias
DEP_TECNOLOGIA = "DISTRITO FICTICIO DE EJEMPLO - DEPARTAMENTO DE TECNOLOGIA FICTICIA"
DEP_PRUEBAS = "DISTRITO FICTICIO DE EJEMPLO - SECRETARIA DE PRUEBAS"
DEP_CULTURA = "DISTRITO FICTICIO DE EJEMPLO - SECRETARIA DE CULTURA FICTICIA"
# Variante con espacios dobles, como los trae la fuente real.
DEP_PRUEBAS_ESPACIOS = "DISTRITO FICTICIO  DE EJEMPLO - SECRETARIA DE PRUEBAS"


def shared_nit_payload(reverse: bool = False) -> dict[str, Any]:
    """4 contratos bajo un NIT compartido (3 dependencias) + 1 de otra entidad.

    Totales diseñados para porcentajes exactos: grupo 1.000M de 1.250M (80%),
    dependencia top 700M (56%) con 1 contrato de 5 (20%).
    """
    contracts = [
        make_contract("CO1.PCCNTR.999101", DEP_PRUEBAS, NIT_DISTRITO,
                      100_000_000.0, "2023-02-01"),
        make_contract("CO1.PCCNTR.999102", DEP_PRUEBAS_ESPACIOS, NIT_DISTRITO,
                      150_000_000.0, "2023-08-15"),
        make_contract("CO1.PCCNTR.999103", DEP_TECNOLOGIA, NIT_DISTRITO,
                      700_000_000.0, "2024-04-10"),
        make_contract("CO1.PCCNTR.999104", DEP_CULTURA, NIT_DISTRITO,
                      50_000_000.0, "2025-01-20"),
        make_contract("CO1.PCCNTR.999105", "Entidad Ficticia Dos", "800000002",
                      250_000_000.0, "2025-03-05"),
    ]
    if reverse:
        contracts = list(reversed(contracts))
    return {
        "data": {
            "document_number": NIT_EJEMPLO,
            "entity_nit": None,
            "from_date": None,
            "to_date": None,
            "count": len(contracts),
            "capped": False,
            "contracts": contracts,
            "pagination": {"total": len(contracts), "page_size": 500,
                           "total_pages": 1, "page": 1},
        }
    }


def test_shared_nit_group_label_is_common_prefix_and_deterministic():
    """El grupo por NIT con >1 nombre se etiqueta por prefijo común normalizado."""
    reduction = reduce_contracts_by_provider(shared_nit_payload(), {})
    top = reduction.summary["entidades"][0]
    assert top["nit"] == NIT_DISTRITO
    assert top["contratos"] == 4
    assert top["valor_total"] == 1_000_000_000.0
    # 3 dependencias (la variante con espacios dobles se fusiona con la limpia).
    assert top["entidad"] == "DISTRITO FICTICIO DE EJEMPLO (3 dependencias)"
    # La otra entidad (un solo nombre) conserva su etiqueta simple.
    assert reduction.summary["entidades"][1]["entidad"] == "Entidad Ficticia Dos"

    # Determinismo: el orden de los contratos en el payload no cambia nada.
    reversed_reduction = reduce_contracts_by_provider(shared_nit_payload(reverse=True), {})
    assert reversed_reduction.summary["entidades"] == reduction.summary["entidades"]
    assert [p.claim for p in reversed_reduction.derived] == [p.claim for p in reduction.derived]


def test_shared_nit_group_breakdown_by_dependency():
    """Desglose por nombre en el grupo top: conteo, valor y % del total general."""
    reduction = reduce_contracts_by_provider(shared_nit_payload(), {})
    deps = reduction.summary["entidades"][0]["dependencias"]
    assert [d["dependencia"] for d in deps] == [DEP_TECNOLOGIA, DEP_PRUEBAS, DEP_CULTURA]
    # Los nombres mostrados están normalizados: nunca espacios dobles.
    assert all("  " not in d["dependencia"] for d in deps)
    assert [d["contratos"] for d in deps] == [1, 2, 1]
    assert [d["valor_total"] for d in deps] == [700_000_000.0, 250_000_000.0, 50_000_000.0]
    # % sobre el TOTAL GENERAL (1.250M), no sobre el total del grupo.
    assert [d["pct_valor_total"] for d in deps] == [56.0, 20.0, 4.0]
    # El grupo de un solo nombre NO lleva desglose.
    assert "dependencias" not in reduction.summary["entidades"][1]


def test_shared_nit_top_dependency_gets_verifiable_proposals():
    """La dependencia top por valor emite sus propios % verificables."""
    reduction = reduce_contracts_by_provider(shared_nit_payload(), {})
    # 3 del grupo top + 2 de la dependencia top (grupo multi-nombre).
    assert len(reduction.derived) == 5
    for proposal in reduction.derived:
        assert_proposal_verifies(proposal)

    dep_count, dep_value = reduction.derived[3], reduction.derived[4]
    assert DEP_TECNOLOGIA in dep_count.claim
    assert "dependencia" in dep_count.claim
    assert dep_count.steps[-1].output == 20.0  # 1 de 5 contratos
    assert dep_value.steps[-1].output == 56.0  # 700M de 1.250M
    # Sources: SOLO los contratos de esa dependencia.
    assert dep_count.contract_ids == ("CO1.PCCNTR.999103",)
    assert dep_value.contract_ids == ("CO1.PCCNTR.999103",)
    # Las proposals del grupo siguen respaldadas por los 4 contratos del NIT.
    assert len(reduction.derived[0].contract_ids) == 4


def test_shared_nit_without_common_prefix_labels_by_nit():
    """Sin prefijo común razonable, la etiqueta cae a 'NIT <nit> (N dependencias)'."""
    contracts = [
        make_contract("CO1.PCCNTR.999201", "GOBFICTICIO - HACIENDA", "800000020",
                      300_000_000.0, "2024-01-01"),
        make_contract("CO1.PCCNTR.999202", "Departamento Ficticio de Asuntos Varios",
                      "800000020", 100_000_000.0, "2024-06-01"),
    ]
    payload = {"data": {"document_number": NIT_EJEMPLO, "count": 2, "capped": False,
                        "contracts": contracts, "pagination": {"total": 2}}}
    reduction = reduce_contracts_by_provider(payload, {})
    top = reduction.summary["entidades"][0]
    assert top["entidad"] == "NIT 800000020 (2 dependencias)"
    assert [d["dependencia"] for d in top["dependencias"]] == [
        "GOBFICTICIO - HACIENDA",
        "Departamento Ficticio de Asuntos Varios",
    ]


def test_shared_nit_breakdown_caps_at_top5_plus_otras():
    """Con >6 dependencias el desglose muestra top-5 por valor + fila 'otras'."""
    deps_names = ["SECRETARIA ALFA", "SECRETARIA BETA", "DEPTO GAMMA", "DEPTO DELTA",
                  "SECRETARIA EPSILON", "DEPTO ZETA", "SECRETARIA OMEGA"]
    contracts = [
        make_contract(f"CO1.PCCNTR.99930{i}", f"ENTIDAD COMPARTIDA FICTICIA - {name}",
                      "800000030", value, "2024-01-01")
        for i, (name, value) in enumerate(zip(
            deps_names,
            [700_000_000.0, 600_000_000.0, 500_000_000.0, 400_000_000.0,
             300_000_000.0, 200_000_000.0, 100_000_000.0],
        ))
    ]
    payload = {"data": {"document_number": NIT_EJEMPLO, "count": 7, "capped": False,
                        "contracts": contracts, "pagination": {"total": 7}}}
    reduction = reduce_contracts_by_provider(payload, {})
    top = reduction.summary["entidades"][0]
    assert top["entidad"] == "ENTIDAD COMPARTIDA FICTICIA (7 dependencias)"
    deps = top["dependencias"]
    assert len(deps) == 6  # top-5 + "otras"
    assert deps[0]["valor_total"] == 700_000_000.0
    otras = deps[-1]
    assert otras["dependencia"] == "otras (2 dependencias)"
    assert otras["contratos"] == 2
    assert otras["valor_total"] == 300_000_000.0
    assert otras["pct_valor_total"] == 10.7  # 300M / 2.800M


# --- SECOP contratos: captura real (integración local, sin fixtures copiados) ---

RAW_CAPTURE = (
    Path(__file__).resolve().parents[2]
    / "data" / "raw" / "secop-contracts-by-provider-20260815T024044Z.raw.json"
)


@pytest.mark.skipif(
    not RAW_CAPTURE.exists(),
    reason="captura real de SECOP no disponible en este repo (data/raw)",
)
def test_contracts_reducer_real_capture_shared_nit_group():
    """Criterio de aceptación con la captura real: NIT 890399011 (6 dependencias).

    Los números esperados fueron verificados a mano por el orquestador; aquí solo
    se comprueba que el reducer los reproduce. La captura NO se copia a fixtures.
    """
    payload = json.loads(RAW_CAPTURE.read_text())
    reduction = reduce_contracts_by_provider(payload, {})
    summary = reduction.summary

    assert summary["contratos_recuperados"] == 47
    top = summary["entidades"][0]
    assert top["nit"] == "890399011"
    assert top["contratos"] == 12
    assert top["valor_total"] == 10_945_807_495.00
    assert top["entidad"].startswith("SANTIAGO DE CALI DISTRITO ESPECIAL")
    assert top["entidad"].endswith("(6 dependencias)")
    assert "  " not in top["entidad"]

    deps = top["dependencias"]
    assert len(deps) == 6  # ≤6 nombres: se listan todas, sin fila "otras"
    top_dep = deps[0]
    assert "TECNOLOGIAS DE LA INFORMACION" in top_dep["dependencia"]
    assert top_dep["contratos"] == 5
    assert top_dep["valor_total"] == 10_307_843_150.00

    # 3 proposals del grupo + 2 de la dependencia top; todas recomputables.
    assert len(reduction.derived) == 5
    for proposal in reduction.derived:
        assert_proposal_verifies(proposal)

    # Números exactos, leídos de los outputs de la cadena (pre-redondeo a 1
    # decimal del claim): 12/47, 10.945.807.495/13.855.327.090,32, 5/47, etc.
    group_pct_count = reduction.derived[0]
    assert group_pct_count.steps[0].inputs == [12, 47]
    assert round(group_pct_count.steps[1].output, 4) == 25.5319

    group_pct_value = reduction.derived[2]
    assert group_pct_value.steps[0].output == 10_945_807_495.00
    assert group_pct_value.steps[1].output == 13_855_327_090.32
    assert round(group_pct_value.steps[3].output, 4) == 79.0007

    dep_pct_count = reduction.derived[3]
    assert dep_pct_count.steps[0].inputs == [5, 47]
    assert round(dep_pct_count.steps[1].output, 4) == 10.6383

    dep_pct_value = reduction.derived[4]
    assert dep_pct_value.steps[0].output == 10_307_843_150.00
    assert dep_pct_value.steps[1].output == 13_855_327_090.32
    assert round(dep_pct_value.steps[3].output, 4) == 74.3962

    # Sources de las proposals de la dependencia: SOLO sus contract-refs.
    contracts = payload["data"]["contracts"]
    dep_ids = {
        str(c["contract_id"])
        for c in contracts
        if str(c.get("entity_nit")) == "890399011"
        and "TECNOLOGIAS DE LA INFORMACION" in " ".join(str(c.get("entity") or "").split())
    }
    assert len(dep_ids) == 5
    assert set(dep_pct_count.contract_ids) == dep_ids
    assert set(dep_pct_value.contract_ids) == dep_ids


# --- RUES ---


def test_rues_by_nit_reducer_identity_and_related_parties():
    reduction = reduce_entity_by_nit(rues_by_nit_payload(), {"document_number": NIT_EJEMPLO})
    identity = reduction.summary["identidad"]
    assert identity["nombre"] == "Empresa Ejemplo S.A.S."
    assert identity["estado_matricula"] == "ACTIVA"
    assert len(reduction.summary["related_parties"]) == 2

    claims = [p.claim for p in reduction.direct]
    assert any("matrícula ACTIVA" in c for c in claims)
    assert any("Representante Legal - Principal" in c for c in claims)
    # El puente empresa -> persona queda descubierto para la cadena.
    assert {d.document for d in reduction.discovered} == {CC_REP_LEGAL, "10000002"}


def test_rues_by_nit_reducer_not_found_is_normal():
    reduction = reduce_entity_by_nit(
        rues_by_nit_payload(found=False), {"document_number": "900000099"}
    )
    assert reduction.summary["found"] is False
    assert len(reduction.direct) == 1
    assert "found=false" in reduction.direct[0].claim
    assert reduction.discovered == []


def test_entities_by_name_reducer_builds_candidates():
    reduction = reduce_entities_by_name(entities_by_name_payload(2), {"name": "ejemplo"})
    assert reduction.candidates is not None
    assert [c.id for c in reduction.candidates] == [
        f"co:nit:{NIT_EJEMPLO}",
        f"co:nit:{NIT_EJEMPLO_2}",
    ]
    assert "ACTIVA" in reduction.candidates[0].detail
    assert "CANCELADA" in reduction.candidates[1].detail
    # Con >1 candidato el reducer NO propone evidencia: el loop pausará.
    assert reduction.direct == []


def test_entities_by_name_reducer_empty_is_result_not_error():
    """0 coincidencias: hecho afirmable como direct, con nota de resultado legítimo."""
    reduction = reduce_entities_by_name(
        entities_by_name_payload(0), {"name": "Empresa Zutano Inexistente XYZ"}
    )
    assert reduction.candidates == []
    assert reduction.summary["total_candidatos"] == 0
    assert len(reduction.direct) == 1
    assert "no devuelve entidades" in reduction.direct[0].claim
    assert reduction.direct[0].raw_reference == "data.entities"
    nota = reduction.summary["nota"]
    assert "no un error" in nota
    assert "No permite concluir" in nota
    assert reduction.discovered == []


def test_entities_by_name_reducer_single_candidate_proceeds():
    reduction = reduce_entities_by_name(entities_by_name_payload(1), {"name": "ejemplo"})
    assert len(reduction.candidates) == 1
    assert len(reduction.direct) == 1
    assert "única entidad" in reduction.direct[0].claim
    assert reduction.discovered[0].document == NIT_EJEMPLO


def test_filter_candidates_selects_and_rejects():
    reduction = reduce_entities_by_name(entities_by_name_payload(2), {"name": "ejemplo"})
    chosen = filter_candidates(reduction, f"co:nit:{NIT_EJEMPLO_2}")
    assert chosen is not None
    assert [c.id for c in chosen.candidates] == [f"co:nit:{NIT_EJEMPLO_2}"]
    assert "seleccionó" in chosen.direct[0].claim
    # También acepta el NIT pelado.
    assert filter_candidates(reduction, NIT_EJEMPLO) is not None
    # Y devuelve None si nada coincide (el loop volverá a pausar).
    assert filter_candidates(reduction, "co:nit:999999999") is None


def _entity_variant(
    name: str,
    *,
    top_nit=None,
    detail_nit=None,
    secondary=None,
    registry="40000009999",
    status="CANCELADA",
):
    """Entity de by-name con las variantes reales de dónde (no) viene el NIT."""
    return {
        "registry_id": registry,
        "nit": top_nit,
        "name": name,
        "registration_status": status,
        "chamber_name": "BOGOTA",
        "registration_number": "6555",
        "detail": {
            "nit": detail_nit,
            "secondary_identification": secondary,
            "registry_id": registry,
        },
    }


def _by_name_payload(entities: list[dict]) -> dict:
    return {"data": {"query": "prueba", "capped": False, "entities": entities}}


def test_candidate_nit_normalized_from_padded_detail():
    """RUES zero-padea el NIT en detail; el candidate_id debe ir SIN padding."""
    reduction = reduce_entities_by_name(
        _by_name_payload(
            [
                _entity_variant("CI FICTICIA PESQUERA", detail_nit="00000900037999"),
                _entity_variant("OTRA FICTICIA", top_nit="00000901126999", registry="222"),
            ]
        ),
        {"name": "prueba"},
    )
    assert reduction.candidates[0].id == "co:nit:900037999"
    assert reduction.candidates[1].id == "co:nit:901126999"
    assert "NIT 900037999" in reduction.candidates[0].detail


def test_candidate_without_any_nit_uses_registry_and_declares_limitation():
    """Registro sin NIT en ningún campo: id de matrícula y, al elegirlo, la
    reanudación declara la limitación de fuente en vez de consultar con ese id."""
    reduction = reduce_entities_by_name(
        _by_name_payload(
            [
                _entity_variant("AGENCIA FICTICIA ANTIGUA", registry="40000006999"),
                _entity_variant("FICTICIA CON NIT", top_nit="901126999", registry="333"),
            ]
        ),
        {"name": "prueba"},
    )
    assert reduction.candidates[0].id == "co:rues:40000006999"

    chosen = filter_candidates(reduction, "co:rues:40000006999")
    assert chosen is not None
    claims = [p.claim for p in chosen.direct]
    assert any("no expone un NIT" in c for c in claims)
    assert "limitación de la fuente" in chosen.summary["nota"]
    assert "NO intentes consultar" in chosen.summary["nota"]
    assert chosen.discovered == []


def test_single_candidate_without_nit_gets_limitation_note():
    reduction = reduce_entities_by_name(
        _by_name_payload([_entity_variant("UNICA SIN NIT", registry="40000006999")]),
        {"name": "prueba"},
    )
    assert len(reduction.candidates) == 1
    assert reduction.discovered == []
    assert "limitación" in reduction.summary["nota"]


# --- Procuraduría / Contraloría / procesos ---


def test_disciplinary_reducer_reports_literal_status():
    reduction = reduce_disciplinary_records(
        procuraduria_payload("NIT"), {"document_number": NIT_EJEMPLO, "document_type": "NIT"}
    )
    assert reduction.summary["has_records"] is False
    assert "SIN ANTECEDENTES" in reduction.direct[0].claim
    assert "has_records=False" in reduction.direct[0].claim


def test_fiscal_reducer_includes_verification_code():
    reduction = reduce_fiscal_records(contraloria_payload(), {"document_number": CC_REP_LEGAL})
    assert reduction.summary["is_fiscal_responsible"] is False
    assert reduction.summary["verification_code"] == "FICT-0000001"
    assert "FICT-0000001" in reduction.direct[0].claim


def test_processes_reducer_warns_no_awardee():
    reduction = reduce_processes_by_entity(processes_payload(), {"document_number": "800000001"})
    assert "NO traen adjudicatario" in reduction.summary["nota"]
    top = reduction.summary["top_procesos_por_valor"]
    assert top[0]["base_price"] == 900_000_000.0
    assert reduction.derived == []


def test_reduce_tool_result_dispatch_and_unknown_tool():
    reduction = reduce_tool_result(
        "secop_contracts_by_provider", contracts_payload(), {"document_number": NIT_EJEMPLO}
    )
    assert reduction.summary["fuente"] == "secop:contracts-by-provider"
    try:
        reduce_tool_result("tool_inexistente", {}, {})
    except KeyError as exc:
        assert "tool_inexistente" in str(exc)
    else:
        raise AssertionError("esperaba KeyError para tool sin reducer")
