"""Loop del agente investigador de TRAZA.

Filosofía: "no acusamos, investigamos". El LLM decide dinámicamente qué fuente
consultar según lo encontrado; el CÓDIGO garantiza los invariantes:

  - Límites operacionales reales (max_steps / max_entities / max_depth) con
    contadores en código — no instrucciones al modelo. Agotados => expediente
    "partial" que lo declara.
  - Fuente que falla (CromaError) => sources_consulted con status="error" y la
    investigación continúa; nunca crash.
  - Desambiguación: >1 candidato en entities-by-name => CaseFile
    needs_disambiguation con candidates[]; investigate(question, candidate_id)
    reanuda filtrando al elegido.
  - Gate de evidencia: los hallazgos del LLM solo pueden citar ids de
    evidencia fabricada por los reducers/store; refs inexistentes se descartan
    con warning y todo derived se re-verifica (verify_derived) al ensamblar.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agent.providers import LLMProvider, LLMResponse
from agent.reducers import Reduction, filter_candidates, reduce_tool_result
from agent.store import EvidenceStore
from agent.tools import (
    ALL_TOOLS,
    FINALIZE_TOOL,
    TOOLS_BY_NAME,
    ToolSpec,
    llm_tool_defs,
)
from croma_client.exceptions import CromaError
from evidence.models import (
    Candidate,
    CaseFile,
    DerivedEvidence,
    Entity,
    Finding,
    SourceConsulted,
)
from evidence.verify import verify_derived

logger = logging.getLogger("traza.agent.loop")

# Máximo de refs de contrato adjuntados como sources de un derived (el raw ref
# siempre va primero y cubre el payload completo; los contract refs son los
# enlaces navegables). Decisión de diseño para que el expediente no explote.
MAX_CONTRACT_SOURCES = 20

SYSTEM_PROMPT = """Eres el agente investigador de TRAZA. Investigas empresas colombianas en \
contratación pública usando exclusivamente fuentes oficiales vía Croma (RUES, SECOP, \
Procuraduría, Contraloría).

FILOSOFÍA — no acusamos, investigamos:
- Documentas lo que las fuentes dicen, con evidencia trazable. Jamás emites acusaciones, \
scores de riesgo, probabilidades ni veredictos.
- Lo que la evidencia no permite establecer se declara explícitamente en unknowns.
- Los números que reportas vienen calculados en código (los resúmenes de las herramientas); \
nunca hagas aritmética propia en un hallazgo.

CÓMO INVESTIGAR (decide la siguiente fuente según lo que encontraste, no una secuencia fija):
- Con NIT: empieza por rues_entity_by_nit (identidad, estado de matrícula y related_parties \
con el representante legal y su cédula).
- Sin NIT: rues_entities_by_name; si hay varios candidatos el sistema pausa para que el \
usuario elija — no adivines entre homónimos.
- secop_contracts_by_provider muestra con qué entidades estatales contrata y la concentración \
por entidad (calculada en código).
- procuraduria_disciplinary_records acepta empresa (NIT) o persona (CC).
- contraloria_fiscal_records SOLO acepta persona: úsala con la cédula del representante legal \
obtenida de RUES.
- secop_processes_by_entity es la convocatoria de una entidad contratante: no trae \
adjudicatario; úsala solo para dimensionar una entidad que ya apareció.

LÍMITES (los aplica el sistema, no dependen de ti): máximo 8 consultas a fuentes, 10 \
entidades distintas, profundidad 3 en la cadena de referencias. Si un resultado trae \
"aviso_limite" o una consulta es RECHAZADA, no insistas: finaliza con lo que haya.

FUENTES QUE FALLAN: si una consulta devuelve ERROR, la fuente quedó registrada como fallida; \
continúa con las demás y declara el hueco en unknowns.

RESULTADOS VACÍOS (0 contratos, found=false, búsqueda sin coincidencias):
- Un resultado vacío es un RESULTADO legítimo, no un fallo: la fuente SÍ respondió. \
Repórtalo como hallazgo citando su evidencia directa (ej. «SECOP no registra contratos \
para el NIT X»). Distingue siempre: fuente que respondió vacío (hecho, va en findings) \
vs fuente que devolvió ERROR (hueco, va en unknowns).
- En unknowns declara lo que el vacío NO permite concluir: un cero en SECOP no demuestra \
que la empresa nunca haya contratado con el Estado (la cobertura tiene límites; pueden \
existir contratos antiguos, bajo otra identificación o en otros sistemas), y un \
found=false en RUES no demuestra que la empresa no exista.
- En next_steps sugiere verificaciones útiles: confirmar el NIT (sin dígito de \
verificación), buscar por razón social, o consultar SECOP/RUES directamente en la web.
- Jamás uses lenguaje de fallo («no se pudo», «error», «sin éxito») en el narrative de un \
hallazgo cuando la fuente respondió con cero resultados.

EVIDENCIA Y CIERRE:
- Cada resultado trae "evidencia_disponible" con ids (ev1, ev2, ...). Son la ÚNICA evidencia \
citable.
- Cuando la evidencia sea suficiente para responder la pregunta (o no queden consultas \
útiles), llama finalize_case_file: hallazgos con title, narrative y evidence_ids; lo no \
establecido va en unknowns; lo que valdría la pena investigar después va en next_steps.
- Un hallazgo cuyo narrative afirme algo sin evidencia citada será descartado por el sistema.
Responde siempre en español."""

NUDGE_MESSAGE = (
    "Recuerda: para cerrar la investigación debes llamar a la herramienta "
    "finalize_case_file con los hallazgos estructurados (evidence_ids del store), "
    "unknowns y next_steps. No entregues el expediente como texto libre."
)

LIMITS_EXHAUSTED_MESSAGE = (
    "Límites operacionales agotados. Llama a finalize_case_file AHORA con la "
    "evidencia disponible; declara en unknowns lo que quedó sin consultar."
)


@dataclass(frozen=True, slots=True)
class LoopConfig:
    """Límites operacionales reales del loop (enforced en código)."""

    max_steps: int = 8
    max_entities: int = 10
    max_depth: int = 3
    # Vueltas máximas de LLM (guardia anti-bucle; > max_steps para dejar
    # espacio a nudges y al cierre forzado).
    max_llm_rounds: int = 14
    # Cuántas veces se le recuerda al modelo que debe usar finalize_case_file.
    max_nudges: int = 2


@dataclass
class _State:
    """Estado mutable de una investigación en curso."""

    config: LoopConfig
    question: str = ""
    store: EvidenceStore = field(default_factory=EvidenceStore)
    sources_consulted: list[SourceConsulted] = field(default_factory=list)
    steps_used: int = 0
    entities_seen: set[str] = field(default_factory=set)
    entity_depths: dict[str, int] = field(default_factory=dict)
    degraded: bool = False
    limit_notes: list[str] = field(default_factory=list)
    steps_exhausted: bool = False
    tool_log: list[dict[str, Any]] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(UTC)


def _entity_key(tool: ToolSpec, args: dict[str, Any]) -> str:
    """Clave de entidad para los contadores: documento, o el nombre buscado."""
    if "document_number" in args:
        return str(args["document_number"]).strip()
    return "name:" + str(args.get("name", "")).strip().lower()


def _call_args(tool: ToolSpec, arguments: dict[str, Any]) -> dict[str, Any] | str:
    """Extrae y valida los argumentos declarados en el schema de la tool.

    Devuelve el dict de kwargs para el CromaClient, o un mensaje de error si
    falta un requerido. Ignora argumentos no declarados (el LLM a veces
    inventa filtros).
    """
    properties = tool.parameters.get("properties", {})
    required = tool.parameters.get("required", [])
    args: dict[str, Any] = {}
    for key in properties:
        if key in arguments and arguments[key] is not None:
            args[key] = str(arguments[key]).strip()
    missing = [key for key in required if not args.get(key)]
    if missing:
        return f"ERROR: falta el parámetro requerido {missing} para {tool.name}."
    return args


async def run_investigation(
    question: str,
    candidate_id: str | None = None,
    *,
    provider: LLMProvider,
    croma: Any,
    config: LoopConfig | None = None,
    trace: dict[str, Any] | None = None,
) -> CaseFile:
    """Corre el loop completo del agente y devuelve un CaseFile validado.

    Args:
        question: pregunta de investigación en lenguaje natural.
        candidate_id: entidad elegida para reanudar tras needs_disambiguation.
        provider: implementación de LLMProvider (nunca se importa openai aquí).
        croma: cliente Croma (o fake en tests) con los métodos convenience.
        config: límites operacionales; por defecto los del producto.
        trace: dict opcional que el loop rellena con métricas (tokens, pasos).
    """
    config = config or LoopConfig()
    state = _State(config=config, question=question)
    usage_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    llm_calls = 0

    user_content = f"Pregunta de investigación: {question}"
    if candidate_id:
        user_content += (
            f"\n\nEl usuario ya desambiguó: continúa con la entidad candidate_id={candidate_id}."
            " Si la búsqueda por nombre devuelve varios candidatos, el sistema filtrará al"
            " elegido automáticamente."
        )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    draft: dict[str, Any] | None = None
    nudges = 0
    finalize_only = False

    for _ in range(config.max_llm_rounds):
        if finalize_only:
            specs: tuple[ToolSpec, ...] = (FINALIZE_TOOL,)
            tool_choice: str | None = FINALIZE_TOOL.name
        else:
            specs = ALL_TOOLS
            tool_choice = None

        response: LLMResponse = await provider.complete(
            messages, llm_tool_defs(specs), tool_choice=tool_choice
        )
        llm_calls += 1
        if response.usage:
            for key in usage_total:
                usage_total[key] += response.usage.get(key, 0)

        if not response.tool_calls:
            # Texto libre sin finalize: se recuerda el protocolo (máx. N veces).
            messages.append({"role": "assistant", "content": response.content or ""})
            nudges += 1
            if nudges > config.max_nudges:
                logger.warning("el modelo no llamó finalize_case_file tras %d avisos", nudges)
                break
            messages.append({"role": "user", "content": NUDGE_MESSAGE})
            continue

        messages.append(
            {
                "role": "assistant",
                "content": response.content,
                "tool_calls": [
                    {"id": call.id, "name": call.name, "arguments": call.arguments}
                    for call in response.tool_calls
                ],
            }
        )

        for call in response.tool_calls:
            if call.name == FINALIZE_TOOL.name:
                draft = call.arguments
                break
            result = await _execute_source_call(call.name, call.arguments, state, croma,
                                                candidate_id)
            if isinstance(result, CaseFile):
                _fill_trace(trace, state, usage_total, llm_calls, "needs_disambiguation")
                return result
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.name,
                    "content": result,
                }
            )
        if draft is not None:
            break
        if state.steps_exhausted and not finalize_only:
            finalize_only = True
            messages.append({"role": "user", "content": LIMITS_EXHAUSTED_MESSAGE})

    case = assemble_case_file(
        question=question,
        draft=draft,
        store=state.store,
        sources_consulted=state.sources_consulted,
        degraded=state.degraded,
        limit_notes=state.limit_notes,
    )
    _fill_trace(trace, state, usage_total, llm_calls, case.status)
    return case


async def _execute_source_call(
    tool_name: str,
    arguments: dict[str, Any],
    state: _State,
    croma: Any,
    candidate_id: str | None,
) -> str | CaseFile:
    """Ejecuta (o rechaza) una tool call de fuente. Los límites viven AQUÍ.

    Devuelve el texto del mensaje de tool para el LLM, o un CaseFile
    needs_disambiguation si la búsqueda por nombre trajo varios candidatos.
    """
    config = state.config
    spec = TOOLS_BY_NAME.get(tool_name)
    if spec is None or spec.client_method is None:
        return f"ERROR: herramienta desconocida {tool_name!r}. Usa solo las declaradas."

    args = _call_args(spec, arguments)
    if isinstance(args, str):
        state.tool_log.append({"tool": tool_name, "args": arguments, "status": "invalid"})
        return args

    # --- Enforcement real de límites (contadores en código) ---
    if state.steps_used >= config.max_steps:
        state.steps_exhausted = True
        _note_limit(state, f"max_steps={config.max_steps} (consultas a fuentes) agotado")
        state.tool_log.append({"tool": tool_name, "args": args, "status": "refused:max_steps"})
        return (
            f"RECHAZADO: límite max_steps={config.max_steps} agotado; no se ejecutó la "
            "consulta. Llama a finalize_case_file con la evidencia disponible."
        )

    key = _entity_key(spec, args)
    depth = state.entity_depths.get(key, 1)
    if depth > config.max_depth:
        _note_limit(
            state,
            f"max_depth={config.max_depth} alcanzado: no se siguió la referencia a {key}",
        )
        state.tool_log.append({"tool": tool_name, "args": args, "status": "refused:max_depth"})
        return (
            f"RECHAZADO: {key} está a profundidad {depth} en la cadena de referencias y el "
            f"límite es {config.max_depth}. No sigas esta rama; finaliza con lo disponible."
        )

    if key not in state.entities_seen and len(state.entities_seen) >= config.max_entities:
        _note_limit(
            state,
            f"max_entities={config.max_entities} alcanzado: no se consultó {key}",
        )
        state.tool_log.append({"tool": tool_name, "args": args, "status": "refused:max_entities"})
        return (
            f"RECHAZADO: límite de {config.max_entities} entidades distintas alcanzado; no se "
            "consultó esta entidad. Finaliza con la evidencia disponible."
        )

    state.entities_seen.add(key)
    state.entity_depths.setdefault(key, depth)
    state.steps_used += 1

    # --- Llamada real; una fuente que falla NUNCA tumba la investigación ---
    try:
        raw = await getattr(croma, spec.client_method)(**args)
    except CromaError as exc:
        state.degraded = True
        state.sources_consulted.append(
            SourceConsulted(source=spec.source_label, at=_now(), status="error")
        )
        state.tool_log.append({"tool": tool_name, "args": args, "status": "error"})
        logger.warning("fuente %s falló: %s", spec.source_label, exc)
        _maybe_exhaust_steps(state)
        return (
            f"ERROR: la fuente {spec.source_label} no respondió "
            f"({type(exc).__name__}). Quedó registrada como fallida; continúa la "
            "investigación con las demás fuentes y declara el hueco en unknowns."
        )

    state.sources_consulted.append(
        SourceConsulted(source=spec.source_label, at=_now(), status="ok")
    )
    state.tool_log.append({"tool": tool_name, "args": args, "status": "ok"})

    ref = state.store.ingest_raw(raw)
    reduction = reduce_tool_result(tool_name, raw.payload, args)

    # --- Desambiguación: decisión del CÓDIGO, no del modelo ---
    if reduction.candidates is not None and len(reduction.candidates) > 1:
        filtered = filter_candidates(reduction, candidate_id) if candidate_id else None
        if filtered is None:
            return _disambiguation_case(state, reduction.candidates)
        reduction = filtered

    summary = _materialize_evidence(state, reduction, ref, depth)
    _maybe_exhaust_steps(state, summary)
    return json.dumps(summary, ensure_ascii=False, default=str)


def _maybe_exhaust_steps(state: _State, summary: dict[str, Any] | None = None) -> None:
    """Marca el agotamiento de pasos y lo avisa dentro del propio resultado."""
    if state.steps_used >= state.config.max_steps and not state.steps_exhausted:
        state.steps_exhausted = True
        _note_limit(state, f"max_steps={state.config.max_steps} (consultas a fuentes) agotado")
        if summary is not None:
            summary["aviso_limite"] = (
                "Última consulta permitida (max_steps agotado). Llama a "
                "finalize_case_file con la evidencia disponible."
            )


def _note_limit(state: _State, note: str) -> None:
    full = f"Límite operacional: {note}. El expediente se cierra como partial."
    if full not in state.limit_notes:
        state.limit_notes.append(full)


def _materialize_evidence(
    state: _State, reduction: Reduction, ref: str, depth: int
) -> dict[str, Any]:
    """Fabrica la evidencia propuesta por el reducer y arma el summary final."""
    store = state.store
    contract_refs: dict[str, str] = {}
    for contract_id in reduction.contract_ids:
        contract_ref = store.register_contract_ref(contract_id, ref)
        if contract_ref:
            contract_refs[contract_id] = contract_ref

    available: list[dict[str, str]] = []
    for direct in reduction.direct:
        evidence_id = store.add_direct(direct.claim, ref, direct.raw_reference)
        if evidence_id:
            available.append({"id": evidence_id, "claim": direct.claim})
    for derived in reduction.derived:
        sources = [ref] + [
            contract_refs[cid]
            for cid in derived.contract_ids[:MAX_CONTRACT_SOURCES]
            if cid in contract_refs
        ]
        evidence_id = store.add_derived(
            derived.claim, derived.calculation, derived.steps, sources
        )
        if evidence_id:
            available.append({"id": evidence_id, "claim": derived.claim})
        # add_derived ya deja log del rechazo; el LLM simplemente no ve el id.

    for discovered in reduction.discovered:
        state.entity_depths.setdefault(discovered.document, depth + 1)

    summary = dict(reduction.summary)
    summary["evidencia_disponible"] = available
    return summary


def _disambiguation_case(state: _State, candidates: list[Candidate]) -> CaseFile:
    """CaseFile needs_disambiguation: candidates[] en lugar de findings."""
    return CaseFile(
        question=state.question,
        status="needs_disambiguation",
        entities=[],
        sources_consulted=list(state.sources_consulted),
        findings=[],
        unknowns=[],
        next_steps=[
            "Reanudar con investigate(question, candidate_id=<id del candidato elegido>)."
        ],
        candidates=candidates,
    )


def assemble_case_file(
    *,
    question: str,
    draft: dict[str, Any] | None,
    store: EvidenceStore,
    sources_consulted: list[SourceConsulted],
    degraded: bool,
    limit_notes: list[str],
) -> CaseFile:
    """Ensambla el CaseFile validado desde el borrador estructurado del LLM.

    Gate de evidencia: cada evidence_id se resuelve contra el store; los
    inexistentes se descartan con warning y todo derived se RE-verifica con
    verify_derived (defensa en profundidad: el store ya verificó al fabricar).
    Un hallazgo que se queda sin evidencia válida se descarta entero.
    """
    findings: list[Finding] = []
    entities: list[Entity] = []
    unknowns: list[str] = []
    next_steps: list[str] = []

    if draft:
        for item in draft.get("findings") or []:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            narrative = str(item.get("narrative") or "").strip()
            if not title or not narrative:
                logger.warning("hallazgo sin title/narrative descartado: %r", item)
                continue
            evidence = []
            for evidence_id in item.get("evidence_ids") or []:
                resolved = store.get(str(evidence_id))
                if resolved is None:
                    logger.warning(
                        "hallazgo %r cita evidencia inexistente %r; ref descartada",
                        title,
                        evidence_id,
                    )
                    continue
                if isinstance(resolved, DerivedEvidence):
                    verification = verify_derived(resolved)
                    if not verification.valid:
                        logger.warning(
                            "derived %r no re-verifica al ensamblar (%s); descartada",
                            evidence_id,
                            verification.errors,
                        )
                        continue
                evidence.append(resolved)
            if not evidence:
                logger.warning("hallazgo %r descartado: sin evidencia válida", title)
                continue
            findings.append(
                Finding(
                    id=f"f{len(findings) + 1}",
                    title=title,
                    narrative=narrative,
                    evidence=evidence,
                )
            )

        seen_entity_ids: set[str] = set()
        for item in draft.get("entities") or []:
            if not isinstance(item, dict):
                continue
            entity_id = str(item.get("id") or "").strip()
            name = str(item.get("name") or "").strip()
            role = str(item.get("role") or "").strip() or "mencionada"
            if not entity_id or not name or entity_id in seen_entity_ids:
                continue
            seen_entity_ids.add(entity_id)
            entities.append(Entity(id=entity_id, name=name, role=role))

        unknowns = [str(u).strip() for u in draft.get("unknowns") or [] if str(u).strip()]
        next_steps = [str(s).strip() for s in draft.get("next_steps") or [] if str(s).strip()]
    else:
        unknowns.append(
            "El modelo no entregó un borrador estructurado; el expediente solo contiene "
            "las fuentes consultadas y la evidencia queda en el store."
        )

    if degraded:
        note = (
            "Al menos una fuente falló durante la investigación (ver sources_consulted "
            "con status=error); el expediente es parcial."
        )
        if note not in unknowns:
            unknowns.append(note)
    for note in limit_notes:
        if note not in unknowns:
            unknowns.append(note)

    status = "partial" if (degraded or limit_notes or draft is None) else "complete"

    return CaseFile(
        question=question,
        status=status,
        entities=entities,
        sources_consulted=list(sources_consulted),
        findings=findings,
        unknowns=unknowns,
        next_steps=next_steps,
    )


def _fill_trace(
    trace: dict[str, Any] | None,
    state: _State,
    usage: dict[str, int],
    llm_calls: int,
    status: str,
) -> None:
    if trace is None:
        return
    trace.update(
        {
            "llm_calls": llm_calls,
            "usage": dict(usage),
            "steps_used": state.steps_used,
            "entities_seen": sorted(state.entities_seen),
            "tool_calls": list(state.tool_log),
            "evidence_count": state.store.evidence_count,
            "raw_count": state.store.raw_count,
            "final_status": status,
        }
    )
