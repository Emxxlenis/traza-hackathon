"""Definiciones de las tools del agente investigador.

Cada tool mapea 1:1 a un método convenience del ``CromaClient`` verificado
(``client_method``). Las descripciones están escritas para el LLM: dicen
CUÁNDO usar cada fuente e incorporan lo aprendido del esquema real de Croma
(docs/croma-schema.md) — p. ej. que Contraloría solo acepta documentos de
persona, o que processes-by-entity no trae adjudicatario.

``finalize_case_file`` no consulta ninguna fuente: es el canal por el que el
LLM entrega el borrador ESTRUCTURADO del expediente (hallazgos que citan
evidencia del store por id). No cuenta contra max_steps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Descriptor de una tool expuesta al LLM.

    Atributos:
        name: nombre de la función que ve el LLM.
        description: cuándo usarla (en español; es lo que decide al modelo).
        parameters: JSON Schema de los argumentos.
        client_method: método del CromaClient a invocar (None para finalize).
        source_label: SourceRef de nivel endpoint para sources_consulted.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    client_method: str | None
    source_label: str | None


def _doc_param(description: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"document_number": {"type": "string", "description": description}},
        "required": ["document_number"],
        "additionalProperties": False,
    }


RUES_ENTITIES_BY_NAME = ToolSpec(
    name="rues_entities_by_name",
    description=(
        "Busca empresas en el RUES por NOMBRE (razón social). Úsala SOLO cuando la "
        "pregunta no trae NIT: es el punto de entrada para resolver un nombre a su NIT. "
        "Devuelve candidatos con NIT, estado de matrícula (ACTIVA/CANCELADA) y cámara de "
        "comercio. Si hay varios candidatos el sistema pausa la investigación para que el "
        "usuario elija — nunca adivines entre homónimos."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Razón social o fragmento del nombre."}
        },
        "required": ["name"],
        "additionalProperties": False,
    },
    client_method="entities_by_name",
    source_label="croma:rues:entities-by-name",
)

RUES_ENTITY_BY_NIT = ToolSpec(
    name="rues_entity_by_nit",
    description=(
        "Identidad registral de una empresa por NIT (sin puntos y SIN dígito de "
        "verificación). Primer paso estándar de la investigación: devuelve estado de "
        "matrícula, actividad CIIU, fechas y — clave — related_parties con el "
        "REPRESENTANTE LEGAL y su cédula (document_number), que es el puente hacia "
        "Procuraduría y Contraloría. found=false es una respuesta normal (p. ej. "
        "matrículas canceladas pueden no estar en el índice por NIT), no un error."
    ),
    parameters=_doc_param("NIT de la empresa, sin puntos y sin dígito de verificación."),
    client_method="entity_by_nit",
    source_label="croma:rues:entity-by-nit",
)

SECOP_CONTRACTS_BY_PROVIDER = ToolSpec(
    name="secop_contracts_by_provider",
    description=(
        "Contratos públicos adjudicados a un PROVEEDOR (empresa por NIT o persona por "
        "documento) en SECOP. Úsala para ver con qué entidades estatales contrata y por "
        "cuánto: el resumen trae la concentración por entidad contratante ya calculada en "
        "código (conteo, suma de valores, porcentajes) y el top de contratos por valor. "
        "Respuestas grandes llegan capadas (capped=true, máximo 500 contratos por página); "
        "el resumen lo declara. La relación proveedor-entidad SOLO se ve aquí, no en "
        "secop_processes_by_entity."
    ),
    parameters=_doc_param("NIT o documento del proveedor investigado."),
    client_method="contracts_by_provider",
    source_label="croma:secop:contracts-by-provider",
)

SECOP_PROCESSES_BY_ENTITY = ToolSpec(
    name="secop_processes_by_entity",
    description=(
        "Procesos de contratación PUBLICADOS por una entidad estatal (se consulta con el "
        "NIT de la entidad CONTRATANTE, no del proveedor). Es el lado de la convocatoria: "
        "NO trae adjudicatario ni proveedor, así que no sirve para saber quién ganó. Úsala "
        "solo para dimensionar la actividad contractual de una entidad contratante que ya "
        "apareció concentrando contratos del proveedor investigado."
    ),
    parameters=_doc_param("NIT de la entidad estatal contratante."),
    client_method="processes_by_entity",
    source_label="croma:secop:processes-by-entity",
)

PROCURADURIA_DISCIPLINARY_RECORDS = ToolSpec(
    name="procuraduria_disciplinary_records",
    description=(
        "Antecedentes disciplinarios en la Procuraduría. Acepta EMPRESA "
        "(document_type='NIT') o PERSONA (document_type='CC', el default). Úsala con el "
        "NIT de la empresa investigada y/o con la cédula del representante legal obtenida "
        "de related_parties en RUES. found, has_records y status son texto literal de la "
        "fuente: repórtalos tal cual, sin interpretarlos como veredicto."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_number": {
                "type": "string",
                "description": "NIT de la empresa o cédula de la persona.",
            },
            "document_type": {
                "type": "string",
                "enum": ["CC", "NIT"],
                "description": "CC para persona (default), NIT para empresa.",
            },
        },
        "required": ["document_number"],
        "additionalProperties": False,
    },
    client_method="disciplinary_records",
    source_label="croma:procuraduria:disciplinary-records",
)

CONTRALORIA_FISCAL_RECORDS = ToolSpec(
    name="contraloria_fiscal_records",
    description=(
        "Antecedentes fiscales en la Contraloría. SOLO acepta documentos de PERSONA "
        "(CC|CE|TI|PA|PEP|PPT) — NO existe NIT en esta fuente. Úsala con la CÉDULA del "
        "representante legal obtenida de related_parties en RUES, nunca con el NIT de la "
        "empresa. Devuelve is_fiscal_responsible y un código de verificación del "
        "certificado (evidencia trazable)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_number": {
                "type": "string",
                "description": "Cédula (u otro documento de persona) del consultado.",
            },
            "document_type": {
                "type": "string",
                "enum": ["CC", "CE", "TI", "PA", "PEP", "PPT"],
                "description": "Tipo de documento de PERSONA. Default CC.",
            },
        },
        "required": ["document_number"],
        "additionalProperties": False,
    },
    client_method="fiscal_records",
    source_label="croma:contraloria:fiscal-records",
)

FINALIZE_TOOL = ToolSpec(
    name="finalize_case_file",
    description=(
        "Cierra la investigación y entrega el borrador estructurado del expediente. "
        "Llámala cuando la evidencia reunida responda la pregunta, cuando no queden "
        "consultas útiles o cuando el sistema lo indique por límites. Cada hallazgo debe "
        "citar SOLO ids de 'evidencia_disponible' vistos en los resultados de las "
        "herramientas; lo que no esté respaldado por evidencia va en unknowns, nunca en un "
        "hallazgo. Sin acusaciones, scores ni veredictos."
    ),
    parameters={
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "description": "Entidades de la investigación (id tipo co:nit:<nit>).",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "role": {
                            "type": "string",
                            "description": "investigada | contratante | representante legal | ...",
                        },
                    },
                    "required": ["id", "name", "role"],
                    "additionalProperties": False,
                },
            },
            "findings": {
                "type": "array",
                "description": "Hallazgos respaldados por evidencia del store.",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "narrative": {
                            "type": "string",
                            "description": (
                                "Texto corto legible; TODO lo afirmado debe estar en la "
                                "evidencia citada."
                            ),
                        },
                        "evidence_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Ids de 'evidencia_disponible' que respaldan.",
                        },
                    },
                    "required": ["title", "narrative", "evidence_ids"],
                    "additionalProperties": False,
                },
            },
            "unknowns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Qué NO se pudo establecer con la evidencia disponible.",
            },
            "next_steps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Qué valdría la pena investigar después.",
            },
        },
        "required": ["entities", "findings", "unknowns", "next_steps"],
        "additionalProperties": False,
    },
    client_method=None,
    source_label=None,
)

SOURCE_TOOLS: tuple[ToolSpec, ...] = (
    RUES_ENTITIES_BY_NAME,
    RUES_ENTITY_BY_NIT,
    SECOP_CONTRACTS_BY_PROVIDER,
    SECOP_PROCESSES_BY_ENTITY,
    PROCURADURIA_DISCIPLINARY_RECORDS,
    CONTRALORIA_FISCAL_RECORDS,
)

ALL_TOOLS: tuple[ToolSpec, ...] = SOURCE_TOOLS + (FINALIZE_TOOL,)

TOOLS_BY_NAME: dict[str, ToolSpec] = {spec.name: spec for spec in ALL_TOOLS}


def llm_tool_defs(specs: tuple[ToolSpec, ...] | list[ToolSpec]) -> list[dict[str, Any]]:
    """Serializa ToolSpecs al formato interno que consume LLMProvider."""
    return [
        {"name": spec.name, "description": spec.description, "parameters": spec.parameters}
        for spec in specs
    ]
