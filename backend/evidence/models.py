"""Modelos del Evidence Layer de TRAZA.

ESTADO: PROVISIONAL — pendiente de validar contra capturas reales de la API de
Croma. Las formas finales de `SourceRef` y `raw_reference` se ajustarán a los
datos reales, no al revés; hoy se modelan como strings opacos con validación laxa.

Regla de producto (restricción dura):
- Cada hallazgo (`Finding`) se construye ÚNICAMENTE desde objetos de evidencia.
- Existen EXACTAMENTE dos tipos: `direct` y `derived`. No existe `hypothesis`
  en el MVP, ni scores de riesgo, probabilidades ni veredictos.
- Un `Finding` sin evidencia es imposible de construir (validación estructural).
- La cadena de cálculo de un `derived` debe ser re-ejecutable mecánicamente
  (ver `evidence.verify.verify_derived`).

La serialización JSON sigue el contrato compartido con la pista de UI:
docs/contracts/case-file.v0.md. Única adición propuesta al contrato:
`calculation_steps` dentro de la evidencia `derived` (ver docs/evidence-layer.md).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

# ---------------------------------------------------------------------------
# SourceRef
# ---------------------------------------------------------------------------

# Convención PROVISIONAL: "croma:<fuente>:<endpoint-o-tipo>[:<id>]"
# Ejemplos válidos:
#   croma:rues:entity-by-nit
#   croma:secop:contracts-by-provider
#   croma:secop:contract:123
# Regex deliberadamente laxa: solo fija el prefijo "croma:" y la estructura de
# segmentos. La forma final (qué identifica unívocamente un contrato, cómo se
# nombra un endpoint) depende de capturas reales de Croma.
SOURCE_REF_PATTERN = (
    r"^croma:[a-z0-9][a-z0-9_-]*:[a-z0-9][a-z0-9_-]*(:[A-Za-z0-9][A-Za-z0-9._-]*)?$"
)

SourceRef = Annotated[
    str,
    Field(
        pattern=SOURCE_REF_PATTERN,
        description=(
            "Referencia opaca a una fuente consultada vía Croma. "
            "Convención provisional: croma:<fuente>:<endpoint-o-tipo>[:<id>]"
        ),
    ),
]


# ---------------------------------------------------------------------------
# Evidencia
# ---------------------------------------------------------------------------


class DirectEvidence(BaseModel):
    """Evidencia directa: lo dice literalmente una respuesta de Croma.

    `raw_reference` es un string OPACO (id o campo exacto dentro de la
    respuesta cruda). Su forma final se definirá con capturas reales; el
    Evidence Layer no le impone estructura, solo que exista y no esté vacío.
    """

    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=1)
    type: Literal["direct"] = "direct"
    source: SourceRef
    raw_reference: str = Field(
        min_length=1,
        description="Id o campo exacto en la respuesta cruda — forma final pendiente.",
    )


# Input de un paso de cálculo: un número literal, o una referencia "$k" al
# output del paso k (0-based, siempre un paso ANTERIOR). La sintaxis de la
# referencia se verifica en verify.verify_derived, no aquí, para que una
# cadena rota sea un resultado de verificación (rechazable) y no un error de
# construcción.
StepInput = float | int | str


class CalculationStep(BaseModel):
    """Un paso atómico de una cadena de cálculo re-ejecutable.

    `operation` pertenece a un conjunto cerrado de operaciones deterministas
    (registro en `evidence.verify.OPERATIONS`). `inputs` son valores concretos
    o referencias "$k" a outputs de pasos anteriores. `output` es el valor que
    el paso declara producir; verify_derived lo recomputa y exige coincidencia.
    """

    model_config = ConfigDict(extra="forbid")

    operation: str = Field(min_length=1)
    inputs: list[StepInput] = Field(min_length=1)
    output: float


class DerivedEvidence(BaseModel):
    """Evidencia derivada: calculada desde una o más respuestas de Croma.

    `calculation` es la expresión legible para humanos (ej. "12 / 17"); NO se
    re-ejecuta. La garantía de reproducibilidad mecánica está en
    `calculation_steps`, que verify_derived re-ejecuta paso a paso.

    NOTA de contrato: `calculation_steps` es una adición propuesta al contrato
    v0 (el ejemplo del contrato solo muestra `calculation` y `sources`).
    """

    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=1)
    type: Literal["derived"] = "derived"
    calculation: str = Field(min_length=1)
    calculation_steps: list[CalculationStep] = Field(min_length=1)
    sources: list[SourceRef] = Field(min_length=1)


# Unión discriminada: cualquier otro valor de `type` (p. ej. "hypothesis") es
# imposible de construir.
Evidence = Annotated[DirectEvidence | DerivedEvidence, Field(discriminator="type")]


# ---------------------------------------------------------------------------
# Expediente (contrato v0)
# ---------------------------------------------------------------------------


class Finding(BaseModel):
    """Hallazgo del expediente. Sin evidencia es IMPOSIBLE de construir.

    Todo lo afirmado en `narrative` debe estar respaldado por los objetos de
    `evidence` — nunca paráfrasis libre del modelo sin objeto detrás. Esa
    correspondencia semántica la garantiza el pipeline; aquí se garantiza la
    parte estructural: evidence nunca vacía y solo tipos direct/derived.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    narrative: str = Field(min_length=1)
    evidence: list[Evidence] = Field(min_length=1)


class Entity(BaseModel):
    """Entidad involucrada en la investigación (siempre ficticia en fixtures).

    Convención provisional de id: "co:nit:<nit>" o "co:entidad:<código>" —
    forma final pendiente de capturas reales (RUES/SECOP).
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    role: str = Field(min_length=1)


class SourceConsulted(BaseModel):
    """Registro de una consulta a Croma (para trazabilidad del expediente)."""

    model_config = ConfigDict(extra="forbid")

    source: SourceRef
    at: AwareDatetime
    # El contrato v0 solo ejemplifica "ok"; asumimos {ok, error} y lo marcamos
    # como pregunta abierta (¿hay estados intermedios: timeout, parcial...?).
    status: Literal["ok", "error"]


class Candidate(BaseModel):
    """Entidad candidata cuando la pregunta es ambigua (needs_disambiguation).

    El contrato v0 no fija la forma de candidates[]; esta es provisional:
    id + nombre + detalle opcional para que el usuario pueda distinguir.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    detail: str | None = None


CaseStatus = Literal["complete", "needs_disambiguation", "partial"]


class CaseFile(BaseModel):
    """Expediente completo — serializa al contrato v0 (case-file.v0.md).

    Invariantes:
    - status = needs_disambiguation  =>  candidates[] no vacía y findings vacía
      (el contrato dice "candidates en lugar de findings").
    - cualquier otro status          =>  candidates ausente (None).
    - `candidates` y `scope_note` se omiten del JSON cuando son None (usar
      to_contract_dict / to_contract_json, que aplican exclude_none).
    """

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    status: CaseStatus
    entities: list[Entity]
    sources_consulted: list[SourceConsulted]
    findings: list[Finding]
    unknowns: list[str]
    next_steps: list[str]
    # Contrato v0.2: rol asumido para la entidad investigada (proveedor de
    # contratos vs entidad contratante) cuando puede ser ambiguo. Se genera EN
    # CÓDIGO al ensamblar el expediente — nunca la redacta el LLM. Ausente
    # (None + exclude_none) cuando no se consultó SECOP para la investigada.
    scope_note: str | None = None
    # Contrato v0.3: mapa SourceRef de contrato ("croma:secop:contract:<id>")
    # → URL oficial en SECOP, capturada del payload crudo. Se puebla EN CÓDIGO
    # al ensamblar, SOLO para contratos citados en sources de alguna evidencia
    # del expediente. Ausente (None + exclude_none) cuando no hay contratos
    # citados o la fuente no trae url.
    source_urls: dict[str, str] | None = None
    candidates: list[Candidate] | None = None

    @model_validator(mode="after")
    def _candidates_iff_disambiguation(self) -> CaseFile:
        if self.status == "needs_disambiguation":
            if not self.candidates:
                raise ValueError(
                    "status=needs_disambiguation exige candidates[] no vacía"
                )
            if self.findings:
                raise ValueError(
                    "con needs_disambiguation el expediente lleva candidates[] "
                    "en lugar de findings[]"
                )
        elif self.candidates is not None:
            raise ValueError(
                "candidates[] solo existe cuando status=needs_disambiguation"
            )
        return self

    def to_contract_dict(self) -> dict:
        """Serializa a la forma JSON del contrato v0 (dict).

        exclude_none omite `candidates` cuando no aplica, exactamente como en
        el contrato. Los `derived` incluyen `calculation_steps` (adición
        propuesta al contrato v0).
        """
        return self.model_dump(mode="json", exclude_none=True)

    def to_contract_json(self, indent: int = 2) -> str:
        """Serializa a la forma JSON del contrato v0 (string)."""
        return self.model_dump_json(exclude_none=True, indent=indent)
