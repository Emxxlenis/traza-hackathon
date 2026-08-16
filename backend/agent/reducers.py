"""Reducers deterministas: del payload crudo de Croma al resumen que ve el LLM.

Regla dura: el LLM NUNCA ve el payload crudo (SECOP puede devolver ~1MB con
500 contratos). Cada tool result pasa por un reducer determinista que produce:

1. ``summary``: dict compacto y JSON-serializable para el mensaje de tool.
2. Propuestas de evidencia ``direct``/``derived`` listas para que el
   EvidenceStore las fabrique. Los agregados numéricos vienen con
   ``calculation_steps`` (operaciones del registro cerrado de
   ``evidence.verify``) computados EN CÓDIGO — ninguna inferencia numérica
   nace de la aritmética del LLM.
3. ``discovered``: entidades nuevas halladas (representante legal, entidades
   contratantes) para el tracking de profundidad del loop.

Los reducers son funciones puras payload -> Reduction: no tocan red, ni el
store, ni el LLM. Réplica exacta de las operaciones de ``evidence.verify``
(fsum para sum, acumulador 1.0 para multiply) para que verify_derived
recompute EXACTAMENTE los mismos outputs declarados.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from evidence.models import CalculationStep, Candidate

# Cuántas entidades contratantes se muestran al LLM en el agregado.
TOP_ENTITIES_IN_SUMMARY = 8
# Cuántos contratos van en el top por valor.
TOP_CONTRACTS = 5
# Truncado del objeto contractual en el resumen.
OBJECT_TRUNCATE_AT = 120
# Máximo de related_parties propuestos como evidencia directa.
MAX_RELATED_PARTY_EVIDENCE = 10
# Desglose por dependencia dentro del grupo top: todas si son ≤6, top-5 + "otras" si son más.
MAX_DEPENDENCIES_IN_SUMMARY = 6
TOP_DEPENDENCIES_IN_SUMMARY = 5
# Un prefijo común de nombres más corto que esto no etiqueta el grupo (se usa
# la dependencia top por valor + "y {k} dependencias más").
MIN_COMMON_PREFIX_CHARS = 10
# Tokens separadores que no cierran un prefijo común ("SANTIAGO DE CALI ... -").
_PREFIX_SEPARATOR_TOKENS = frozenset({"-", "–", "—", "/", ",", ":", "·"})


@dataclass(frozen=True, slots=True)
class DirectProposal:
    """Propuesta de DirectEvidence; el store le pone el SourceRef del raw."""

    claim: str
    raw_reference: str


@dataclass(frozen=True, slots=True)
class DerivedProposal:
    """Propuesta de DerivedEvidence con la cadena de cálculo ya computada.

    ``contract_ids`` son los contratos que respaldan el agregado; el caller
    los convierte en SourceRefs (croma:secop:contract:<id>).
    """

    claim: str
    calculation: str
    steps: tuple[CalculationStep, ...]
    contract_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DiscoveredEntity:
    """Entidad nueva hallada en una respuesta (para tracking de profundidad)."""

    document: str
    label: str


@dataclass(slots=True)
class Reduction:
    """Resultado de reducir un payload: resumen + propuestas de evidencia."""

    summary: dict[str, Any]
    direct: list[DirectProposal] = field(default_factory=list)
    derived: list[DerivedProposal] = field(default_factory=list)
    discovered: list[DiscoveredEntity] = field(default_factory=list)
    candidates: list[Candidate] | None = None
    contract_ids: list[str] = field(default_factory=list)
    # URL oficial por contrato (contrato v0.3): {contract_id: url} capturado
    # del payload crudo; los contratos sin url simplemente no aparecen.
    contract_urls: dict[str, str] = field(default_factory=dict)


def _data(payload: Any) -> dict[str, Any]:
    """Extrae el envelope {"data": {...}} verificado; tolera formas raras."""
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            return data
        return payload
    return {}


def _truncate(text: Any, limit: int = OBJECT_TRUNCATE_AT) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _normalize_name(name: Any) -> str:
    """Colapsa espacios múltiples y bordes: la fuente trae 'CALI  DISTRITO' y 'CALI DISTRITO'."""
    return " ".join(str(name or "").split())


def _common_name_prefix(names: list[str]) -> str:
    """Prefijo común POR TOKENS de nombres ya normalizados, sin separadores colgantes."""
    token_lists = [name.split(" ") for name in names]
    prefix_tokens: list[str] = []
    for tokens in zip(*token_lists):
        if any(token != tokens[0] for token in tokens[1:]):
            break
        prefix_tokens.append(tokens[0])
    while prefix_tokens and prefix_tokens[-1] in _PREFIX_SEPARATOR_TOKENS:
        prefix_tokens.pop()
    return " ".join(prefix_tokens)


def _group_label(by_name: dict[str, dict[str, Any]]) -> str:
    """Etiqueta determinista de un grupo por NIT.

    En Colombia las dependencias de un distrito comparten NIT (ej. 6 secretarías
    de Cali bajo 890399011): con >1 nombre normalizado distinto, la etiqueta es
    el prefijo común si es significativo ("SANTIAGO DE CALI DISTRITO ESPECIAL
    (6 dependencias)"), o el nombre de la dependencia TOP POR VALOR +
    "y {k} dependencias más". El fallback NUNCA usa el NIT como nombre: el
    label entra en claims que ya anexan "(NIT ...)" y quedaría el identificador
    duplicado sin ningún nombre legible.
    """
    names = sorted(by_name)
    if len(names) == 1:
        return names[0]
    prefix = _common_name_prefix(names)
    if len(prefix) >= MIN_COMMON_PREFIX_CHARS:
        return f"{prefix} ({len(names)} dependencias)"
    top_name = _ranked_dependencies(by_name)[0][0]
    rest = len(names) - 1
    return f"{top_name} y {rest} {'dependencia más' if rest == 1 else 'dependencias más'}"


def _label_with_nit(label: str, nit: str) -> str:
    """Anexa "(NIT <nit>)" al label salvo que ya lo contenga (guard anti-duplicado).

    Con el fallback de ``_group_label`` esto no debería ocurrir; queda como
    defensa para que un claim jamás repita el mismo identificador.
    """
    if not nit or f"NIT {nit}" in label:
        return label
    return f"{label} (NIT {nit})"


# --- Réplicas exactas de las operaciones de evidence.verify ---


def _mul(values: list[float]) -> float:
    result = 1.0
    for value in values:
        result *= value
    return result


def _percentage_steps(part: float, whole: float) -> tuple[list[CalculationStep], float]:
    """Pasos part/whole*100 redondeado a 1 decimal; outputs replican verify."""
    quotient = part / whole
    scaled = _mul([quotient, 100.0])
    rounded = round(scaled, 1)
    steps = [
        CalculationStep(operation="divide", inputs=[part, whole], output=quotient),
        CalculationStep(operation="multiply", inputs=["$0", 100], output=scaled),
        CalculationStep(operation="round", inputs=["$1", 1], output=rounded),
    ]
    return steps, rounded


# --- SECOP: contratos por proveedor ---


def _ranked_dependencies(by_name: dict[str, dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    """Dependencias de un grupo ordenadas por valor desc; empates por nombre (determinista)."""
    return sorted(by_name.items(), key=lambda item: (-math.fsum(item[1]["values"]), item[0]))


def _dependency_breakdown(
    by_name: dict[str, dict[str, Any]], total_sum: float
) -> list[dict[str, Any]]:
    """Desglose por dependencia: conteo, suma de value y % sobre el TOTAL GENERAL.

    Todas si son ≤ MAX_DEPENDENCIES_IN_SUMMARY; si son más, top-5 por valor
    más una fila agregada "otras".
    """

    def _pct(value_sum: float) -> float:
        return round((value_sum / total_sum) * 100, 1) if total_sum else 0.0

    rows = [
        (name, sub["count"], math.fsum(sub["values"]))
        for name, sub in _ranked_dependencies(by_name)
    ]
    shown = rows if len(rows) <= MAX_DEPENDENCIES_IN_SUMMARY else rows[:TOP_DEPENDENCIES_IN_SUMMARY]
    breakdown = [
        {
            "dependencia": name,
            "contratos": count,
            "valor_total": value_sum,
            "pct_valor_total": _pct(value_sum),
        }
        for name, count, value_sum in shown
    ]
    rest = rows[len(shown):]
    if rest:
        rest_sum = math.fsum(value_sum for _, _, value_sum in rest)
        breakdown.append(
            {
                "dependencia": f"otras ({len(rest)} dependencias)",
                "contratos": sum(count for _, count, _ in rest),
                "valor_total": rest_sum,
                "pct_valor_total": _pct(rest_sum),
            }
        )
    return breakdown


def reduce_contracts_by_provider(payload: Any, args: dict[str, Any]) -> Reduction:
    """Agrega contratos por entidad contratante EN CÓDIGO y arma el top-5.

    El % de concentración usa como denominador los contratos RECUPERADOS (si
    capped=true la muestra es parcial y el resumen y los claims lo declaran).

    La agrupación es por ``entity_nit``: las dependencias de un distrito
    comparten NIT, así que un grupo con >1 nombre normalizado se etiqueta por
    prefijo común + "(N dependencias)" (o dependencia top por valor + "y {k}
    dependencias más"), el grupo top expone su desglose por dependencia y la
    dependencia top por valor recibe sus propias proposals derivadas.
    """
    data = _data(payload)
    contracts = [c for c in data.get("contracts") or [] if isinstance(c, dict)]
    document = str(data.get("document_number") or args.get("document_number") or "")
    capped = bool(data.get("capped"))
    pagination = data.get("pagination") if isinstance(data.get("pagination"), dict) else {}
    total_reported = pagination.get("total") or data.get("count") or len(contracts)
    n = len(contracts)

    contract_ids = [str(c.get("contract_id")) for c in contracts if c.get("contract_id")]
    # URL oficial por contrato (contrato v0.3): solo los que traen url en el crudo.
    contract_urls = {
        str(c["contract_id"]): str(c["url"])
        for c in contracts
        if c.get("contract_id") and c.get("url")
    }

    # Agregado por entidad contratante (conteo, suma de value) — en código.
    # La clave es entity_nit: en Colombia las dependencias de un distrito
    # comparten NIT, así que cada grupo trackea sus nombres (normalizados) por
    # separado en "by_name" para etiquetar y desglosar sin mentir.
    groups: dict[str, dict[str, Any]] = {}
    all_values: list[float] = []
    dates: list[str] = []
    for contract in contracts:
        value = float(contract.get("value") or 0)
        all_values.append(value)
        key = str(contract.get("entity_nit") or contract.get("entity") or "desconocida")
        group = groups.setdefault(
            key,
            {
                "entity": "",  # se etiqueta tras agrupar (puede haber >1 nombre por NIT)
                "nit": str(contract.get("entity_nit") or ""),
                "count": 0,
                "values": [],
                "contract_ids": [],
                "by_name": {},
            },
        )
        group["count"] += 1
        group["values"].append(value)
        name = _normalize_name(contract.get("entity")) or "—"
        sub = group["by_name"].setdefault(name, {"count": 0, "values": [], "contract_ids": []})
        sub["count"] += 1
        sub["values"].append(value)
        if contract.get("contract_id"):
            group["contract_ids"].append(str(contract["contract_id"]))
            sub["contract_ids"].append(str(contract["contract_id"]))
        date = contract.get("sign_date") or contract.get("start_date")
        if date:
            dates.append(str(date))

    for group in groups.values():
        group["entity"] = _group_label(group["by_name"])

    total_sum = math.fsum(all_values)
    ranked = sorted(groups.values(), key=lambda g: (-g["count"], -math.fsum(g["values"])))

    entities_summary: list[dict[str, Any]] = []
    for rank, group in enumerate(ranked[:TOP_ENTITIES_IN_SUMMARY]):
        value_sum = math.fsum(group["values"])
        pct = round((group["count"] / n) * 100, 1) if n else 0.0
        entry: dict[str, Any] = {
            "entidad": group["entity"],
            "nit": group["nit"],
            "contratos": group["count"],
            "valor_total": value_sum,
            "pct_contratos": pct,
        }
        # Desglose por dependencia SOLO en el grupo top multi-nombre: el LLM ve
        # quién concentra realmente el valor dentro del NIT compartido.
        if rank == 0 and len(group["by_name"]) > 1:
            entry["dependencias"] = _dependency_breakdown(group["by_name"], total_sum)
        entities_summary.append(entry)

    top_contracts = sorted(contracts, key=lambda c: float(c.get("value") or 0), reverse=True)
    top_summary = [
        {
            "contract_id": str(c.get("contract_id") or ""),
            "entidad": _normalize_name(c.get("entity")),
            "valor": float(c.get("value") or 0),
            "objeto": _truncate(c.get("object")),
            "url": str(c.get("url") or ""),
        }
        for c in top_contracts[:TOP_CONTRACTS]
    ]

    summary: dict[str, Any] = {
        "fuente": "secop:contracts-by-provider",
        "documento_proveedor": document,
        "total_reportado": total_reported,
        "contratos_recuperados": n,
        "capped": capped,
        "rango_fechas": {"desde": min(dates), "hasta": max(dates)} if dates else None,
        "entidades": entities_summary,
        "top_contratos": top_summary,
    }
    if capped:
        summary["nota"] = (
            "Muestra capada: los agregados cubren solo los contratos recuperados "
            f"({n} de {total_reported})."
        )
    elif not contracts:
        summary["nota"] = (
            "0 contratos es un RESULTADO (la fuente respondió), no un error: repórtalo "
            "como hecho. No permite concluir que la empresa nunca haya contratado con el "
            "Estado: la cobertura de SECOP/Croma tiene límites y pueden existir contratos "
            "antiguos, bajo otra identificación o en otros sistemas; decláralo en unknowns."
        )

    reduction = Reduction(
        summary=summary, contract_ids=contract_ids, contract_urls=contract_urls
    )

    sample_note = " (muestra capada)" if capped else ""
    if contracts:
        count_claim = (
            f"SECOP devuelve {n} contratos para el proveedor {document} "
            f"(total reportado: {total_reported}{sample_note})"
        )
    else:
        count_claim = (
            f"SECOP no registra contratos para el proveedor {document}; "
            f"total reportado: {total_reported}"
        )
    reduction.direct.append(
        DirectProposal(claim=count_claim, raw_reference="data.count")
    )

    if ranked and n:
        top = ranked[0]
        top_values = [float(v) for v in top["values"]]
        top_ids = tuple(top["contract_ids"])
        entity_label = _label_with_nit(top["entity"], top["nit"])

        pct_steps, pct = _percentage_steps(top["count"], n)
        reduction.derived.append(
            DerivedProposal(
                claim=(
                    f"El {pct}% de los contratos recuperados ({top['count']} de {n}) "
                    f"corresponde a la entidad {entity_label}{sample_note}"
                ),
                calculation=f"{top['count']} / {n} * 100",
                steps=tuple(pct_steps),
                contract_ids=top_ids,
            )
        )

        entity_sum = math.fsum(top_values)
        reduction.derived.append(
            DerivedProposal(
                claim=(
                    f"Los {top['count']} contratos con {entity_label} suman "
                    f"{entity_sum:,.0f} en valor contratado{sample_note}"
                ),
                calculation=f"suma de los valores de {top['count']} contratos",
                steps=(
                    CalculationStep(operation="sum", inputs=list(top_values), output=entity_sum),
                ),
                contract_ids=top_ids,
            )
        )

        if total_sum > 0:
            quotient = entity_sum / total_sum
            scaled = _mul([quotient, 100.0])
            rounded = round(scaled, 1)
            reduction.derived.append(
                DerivedProposal(
                    claim=(
                        f"La entidad {entity_label} concentra el {rounded}% del valor "
                        f"total de los contratos recuperados{sample_note}"
                    ),
                    calculation=f"{entity_sum} / {total_sum} * 100",
                    steps=(
                        CalculationStep(
                            operation="sum", inputs=list(top_values), output=entity_sum
                        ),
                        CalculationStep(
                            operation="sum", inputs=list(all_values), output=total_sum
                        ),
                        CalculationStep(
                            operation="divide", inputs=["$0", "$1"], output=quotient
                        ),
                        CalculationStep(
                            operation="multiply", inputs=["$2", 100], output=scaled
                        ),
                        CalculationStep(operation="round", inputs=["$3", 1], output=rounded),
                    ),
                    contract_ids=top_ids,
                )
            )

        # Grupo top multi-nombre (NIT compartido por dependencias): proposals
        # equivalentes para la dependencia top por valor, respaldadas SOLO por
        # los contratos de esa dependencia.
        if len(top["by_name"]) > 1:
            dep_name, dep = _ranked_dependencies(top["by_name"])[0]
            dep_values = [float(v) for v in dep["values"]]
            dep_ids = tuple(dep["contract_ids"])
            dep_label = _label_with_nit(dep_name, top["nit"])

            dep_pct_steps, dep_pct = _percentage_steps(dep["count"], n)
            # El grupo se menciona por su label pelado: la dependencia ya lleva
            # "(NIT ...)" y ambos comparten NIT — anexarlo dos veces duplicaría
            # el identificador dentro del mismo claim.
            reduction.derived.append(
                DerivedProposal(
                    claim=(
                        f"El {dep_pct}% de los contratos recuperados ({dep['count']} de {n}) "
                        f"corresponde a la dependencia {dep_label}, la mayor por valor dentro "
                        f"del grupo {top['entity']}{sample_note}"
                    ),
                    calculation=f"{dep['count']} / {n} * 100",
                    steps=tuple(dep_pct_steps),
                    contract_ids=dep_ids,
                )
            )

            if total_sum > 0:
                dep_sum = math.fsum(dep_values)
                dep_quotient = dep_sum / total_sum
                dep_scaled = _mul([dep_quotient, 100.0])
                dep_rounded = round(dep_scaled, 1)
                reduction.derived.append(
                    DerivedProposal(
                        claim=(
                            f"La dependencia {dep_label} concentra el {dep_rounded}% del "
                            f"valor total de los contratos recuperados{sample_note}"
                        ),
                        calculation=f"{dep_sum} / {total_sum} * 100",
                        steps=(
                            CalculationStep(
                                operation="sum", inputs=list(dep_values), output=dep_sum
                            ),
                            CalculationStep(
                                operation="sum", inputs=list(all_values), output=total_sum
                            ),
                            CalculationStep(
                                operation="divide", inputs=["$0", "$1"], output=dep_quotient
                            ),
                            CalculationStep(
                                operation="multiply", inputs=["$2", 100], output=dep_scaled
                            ),
                            CalculationStep(
                                operation="round", inputs=["$3", 1], output=dep_rounded
                            ),
                        ),
                        contract_ids=dep_ids,
                    )
                )

    # Entidades contratantes descubiertas: candidatas a profundidad +1.
    for group in ranked:
        if group["nit"]:
            reduction.discovered.append(
                DiscoveredEntity(document=group["nit"], label=f"entidad contratante {group['entity']}")
            )
    return reduction


# --- RUES ---


def reduce_entity_by_nit(payload: Any, args: dict[str, Any]) -> Reduction:
    """Identidad + estado + related_parties (puente al representante legal)."""
    data = _data(payload)
    document = str(data.get("document_number") or args.get("document_number") or "")
    found = bool(data.get("found"))
    if not found:
        summary = {
            "fuente": "rues:entity-by-nit",
            "found": False,
            "document_number": document,
            "nota": (
                "found=false es respuesta normal (posible matrícula cancelada fuera del "
                "índice por NIT), no un error: repórtalo como hecho. No permite concluir "
                "que la empresa no exista ni que el NIT sea inválido; decláralo en "
                "unknowns. Puedes intentar rues_entities_by_name si conoces la razón social."
            ),
        }
        reduction = Reduction(summary=summary)
        reduction.direct.append(
            DirectProposal(
                claim=f"RUES no devuelve registro para el NIT {document} (found=false)",
                raw_reference="data.found",
            )
        )
        return reduction

    entity = data.get("entity") if isinstance(data.get("entity"), dict) else {}
    name = str(entity.get("name") or "—")
    nit = str(entity.get("nit") or document)
    status = str(entity.get("registration_status") or "desconocido")
    primary = entity.get("primary_activity") if isinstance(entity.get("primary_activity"), dict) else {}
    related = [p for p in data.get("related_parties") or [] if isinstance(p, dict)]

    summary = {
        "fuente": "rues:entity-by-nit",
        "found": True,
        "identidad": {
            "nombre": name,
            "nit": nit,
            "dv": entity.get("verification_digit"),
            "estado_matricula": status,
            "organizacion_juridica": entity.get("legal_organization"),
            "fecha_matricula": entity.get("registration_date"),
            "fecha_cancelacion": entity.get("cancellation_date"),
            "ultima_renovacion": entity.get("last_renewal_date"),
            "camara": entity.get("chamber_name"),
            "actividad_principal": {
                "ciiu": primary.get("code"),
                "descripcion": primary.get("description"),
            },
        },
        "related_parties": [
            {
                "document_number": str(p.get("document_number") or ""),
                "name": p.get("name"),
                "role": p.get("role"),
            }
            for p in related
        ],
        "financials_disponibles": len(data.get("financials") or []),
        "renovaciones_registradas": len(data.get("renewals") or []),
    }

    reduction = Reduction(summary=summary)
    reduction.direct.append(
        DirectProposal(
            claim=f"«{name}» (NIT {nit}) figura en RUES con matrícula {status}",
            raw_reference="data.entity.registration_status",
        )
    )
    for i, party in enumerate(related[:MAX_RELATED_PARTY_EVIDENCE]):
        p_doc = str(party.get("document_number") or "")
        p_name = str(party.get("name") or "—")
        p_role = str(party.get("role") or "vinculado")
        reduction.direct.append(
            DirectProposal(
                claim=f"«{p_name}» (documento {p_doc}) figura como {p_role} de «{name}»",
                raw_reference=f"data.related_parties[{i}]",
            )
        )
        if p_doc:
            reduction.discovered.append(DiscoveredEntity(document=p_doc, label=p_role))
    return reduction


def _candidate_from_entity(entity: dict[str, Any]) -> Candidate:
    """Construye un Candidate {id, name, detail} desde un entity de by-name."""
    detail_obj = entity.get("detail") if isinstance(entity.get("detail"), dict) else {}
    # El NIT puede venir en cualquiera de los tres campos y RUES lo zero-padea a 14
    # dígitos en algunos ("00000901126453"); entity-by-nit solo resuelve SIN padding,
    # así que se normaliza SIEMPRE antes de fijarlo en el candidate_id.
    nit_raw = (
        entity.get("nit")
        or detail_obj.get("nit")
        or detail_obj.get("secondary_identification")
    )
    nit = (str(nit_raw).strip().lstrip("0") or None) if nit_raw else None
    registry_id = entity.get("registry_id") or detail_obj.get("registry_id") or "sin-registro"
    candidate_id = f"co:nit:{nit}" if nit else f"co:rues:{registry_id}"

    parts = []
    if nit:
        parts.append(f"NIT {nit}")
    if entity.get("registration_status"):
        parts.append(str(entity["registration_status"]))
    if entity.get("chamber_name"):
        parts.append(str(entity["chamber_name"]))
    if entity.get("registration_number"):
        parts.append(f"matrícula {entity['registration_number']}")
    return Candidate(
        id=candidate_id,
        name=str(entity.get("name") or "—"),
        detail=" · ".join(parts) or None,
    )


def reduce_entities_by_name(payload: Any, args: dict[str, Any]) -> Reduction:
    """Búsqueda por nombre: produce candidates[] para la desambiguación.

    Con >1 candidato el loop pausa (needs_disambiguation) o filtra con
    candidate_id; con exactamente 1 este reducer ya propone la evidencia y la
    entidad descubierta.
    """
    data = _data(payload)
    query = str(data.get("query") or args.get("name") or "")
    entities = [e for e in data.get("entities") or [] if isinstance(e, dict)]
    candidates = [_candidate_from_entity(e) for e in entities]

    summary: dict[str, Any] = {
        "fuente": "rues:entities-by-name",
        "query": query,
        "total_candidatos": len(candidates),
        "capped": bool(data.get("capped")),
        "candidatos": [
            {"id": c.id, "name": c.name, "detail": c.detail} for c in candidates
        ],
    }
    reduction = Reduction(summary=summary, candidates=candidates)

    if not candidates:
        summary["nota"] = (
            "0 coincidencias es un RESULTADO (la fuente respondió), no un error: repórtalo "
            "como hecho. No permite concluir que la empresa no exista: la razón social "
            "registrada puede diferir del nombre buscado; decláralo en unknowns y sugiere "
            "variantes del nombre o aportar el NIT en next_steps."
        )
        reduction.direct.append(
            DirectProposal(
                claim=f"La búsqueda RUES por nombre «{query}» no devuelve entidades",
                raw_reference="data.entities",
            )
        )
    elif len(candidates) == 1:
        chosen = candidates[0]
        reduction.direct.append(
            DirectProposal(
                claim=(
                    f"La búsqueda RUES por nombre «{query}» devuelve una única entidad: "
                    f"«{chosen.name}» ({chosen.detail or chosen.id})"
                ),
                raw_reference="data.entities[0]",
            )
        )
        nit = _nit_from_candidate_id(chosen.id)
        if nit:
            reduction.discovered.append(
                DiscoveredEntity(document=nit, label=f"entidad {chosen.name}")
            )
        else:
            summary["nota"] = (
                "La única entidad encontrada NO tiene NIT recuperable en RUES (limitación "
                "de la fuente, frecuente en matrículas antiguas o canceladas). NO consultes "
                "otras fuentes con el id de matrícula: requieren NIT/cédula. Declara la "
                "limitación como hecho y sugiere en next_steps cómo obtener el NIT."
            )
    return reduction


def _nit_from_candidate_id(candidate_id: str) -> str | None:
    if candidate_id.startswith("co:nit:"):
        return candidate_id.removeprefix("co:nit:") or None
    return None


def filter_candidates(reduction: Reduction, candidate_id: str) -> Reduction | None:
    """Filtra una Reduction de by-name al candidato elegido por el usuario.

    Acepta el id completo ("co:nit:900000011") o el NIT/registro pelado.
    Devuelve None si ningún candidato coincide (el loop volverá a pausar).
    """
    if not reduction.candidates:
        return None
    wanted = candidate_id.strip()
    wanted_tail = wanted.split(":")[-1]
    chosen_index: int | None = None
    for i, candidate in enumerate(reduction.candidates):
        if candidate.id == wanted or candidate.id.split(":")[-1] == wanted_tail:
            chosen_index = i
            break
    if chosen_index is None:
        return None

    chosen = reduction.candidates[chosen_index]
    total = len(reduction.candidates)
    query = str(reduction.summary.get("query") or "")
    filtered = Reduction(
        summary={
            "fuente": "rues:entities-by-name",
            "query": query,
            "total_candidatos": total,
            "candidato_elegido": {"id": chosen.id, "name": chosen.name, "detail": chosen.detail},
            "nota": "Entidad seleccionada por el usuario tras la desambiguación.",
        },
        candidates=[chosen],
    )
    filtered.direct.append(
        DirectProposal(
            claim=(
                f"Entre {total} candidatos RUES para «{query}», el usuario seleccionó "
                f"«{chosen.name}» ({chosen.detail or chosen.id})"
            ),
            raw_reference=f"data.entities[{chosen_index}]",
        )
    )
    nit = _nit_from_candidate_id(chosen.id)
    if nit:
        filtered.discovered.append(DiscoveredEntity(document=nit, label=f"entidad {chosen.name}"))
    else:
        # Limitación real de la fuente: RUES no publica NIT para algunos registros
        # (típicamente matrículas antiguas o canceladas). Se declara como hecho y se
        # corta la cadena por documento — NUNCA consultar fuentes con el id de matrícula.
        filtered.direct.append(
            DirectProposal(
                claim=(
                    f"RUES no expone un NIT para «{chosen.name}» "
                    f"({chosen.detail or 'sin detalle'}): el registro no lo publica"
                ),
                raw_reference=f"data.entities[{chosen_index}]",
            )
        )
        filtered.summary["nota"] = (
            "La entidad elegida NO tiene NIT recuperable en RUES: es una limitación de la "
            "fuente (frecuente en matrículas antiguas o canceladas), no un error tuyo ni "
            "del sistema. NO intentes consultar SECOP/Procuraduría/Contraloría con el id "
            "de matrícula — esas fuentes requieren un documento (NIT/cédula) que no "
            "tenemos. Declara la limitación como hecho, explica en unknowns qué no se "
            "puede continuar sin el NIT, y sugiere en next_steps cómo obtenerlo "
            "(certificado de cámara de comercio, que el usuario lo aporte). Cierra el "
            "expediente con lo que sí hay."
        )
    return filtered


# --- SECOP: procesos por entidad contratante ---


def reduce_processes_by_entity(payload: Any, args: dict[str, Any]) -> Reduction:
    """Procesos publicados por una entidad. Recordatorio: SIN adjudicatario."""
    data = _data(payload)
    processes = [p for p in data.get("processes") or [] if isinstance(p, dict)]
    document = str(data.get("document_number") or args.get("document_number") or "")
    capped = bool(data.get("capped"))
    pagination = data.get("pagination") if isinstance(data.get("pagination"), dict) else {}
    total_reported = pagination.get("total") or data.get("count") or len(processes)

    top = sorted(processes, key=lambda p: float(p.get("base_price") or 0), reverse=True)
    summary = {
        "fuente": "secop:processes-by-entity",
        "nit_entidad": document,
        "total_reportado": total_reported,
        "procesos_recuperados": len(processes),
        "capped": capped,
        "top_procesos_por_valor": [
            {
                "process_id": str(p.get("process_id") or p.get("notice_uid") or ""),
                "nombre": _truncate(p.get("name")),
                "base_price": float(p.get("base_price") or 0),
                "fase": p.get("phase"),
                "url": str(p.get("url") or ""),
            }
            for p in top[:TOP_CONTRACTS]
        ],
        "nota": (
            "Los procesos son la convocatoria: NO traen adjudicatario/proveedor. La "
            "relación proveedor-entidad solo se ve en secop_contracts_by_provider."
        ),
    }
    sample_note = " (muestra capada)" if capped else ""
    reduction = Reduction(summary=summary)
    reduction.direct.append(
        DirectProposal(
            claim=(
                f"La entidad {document} registra {total_reported} procesos de contratación "
                f"publicados en SECOP{sample_note}"
            ),
            raw_reference="data.count",
        )
    )
    return reduction


# --- Procuraduría ---


def reduce_disciplinary_records(payload: Any, args: dict[str, Any]) -> Reduction:
    """Antecedentes disciplinarios: se reporta el texto literal de la fuente."""
    data = _data(payload)
    document = str(data.get("document_number") or args.get("document_number") or "")
    label = str(data.get("document_type_label") or data.get("document_type") or "documento")
    has_records = data.get("has_records")
    status = str(data.get("status") or "")
    records = data.get("records") or []
    full_name = data.get("full_name")

    summary = {
        "fuente": "procuraduria:disciplinary-records",
        "found": bool(data.get("found")),
        "document_type": label,
        "document_number": document,
        "full_name": full_name,
        "has_records": has_records,
        "status_literal": status,
        "message": data.get("message"),
        "records_count": len(records) if isinstance(records, list) else None,
    }
    who = f"{label} {document}" + (f" ({full_name})" if full_name else "")
    reduction = Reduction(summary=summary)
    reduction.direct.append(
        DirectProposal(
            claim=(
                f"Procuraduría responde para {who}: has_records={has_records}; "
                f"estado literal de la fuente: «{status}»"
            ),
            raw_reference="data.has_records",
        )
    )
    return reduction


# --- Contraloría ---


def reduce_fiscal_records(payload: Any, args: dict[str, Any]) -> Reduction:
    """Antecedentes fiscales (solo persona): certificado con código verificable."""
    data = _data(payload)
    document = str(data.get("document_number") or args.get("document_number") or "")
    label = str(data.get("document_type_label") or data.get("document_type") or "documento")
    responsible = data.get("is_fiscal_responsible")
    code = data.get("verification_code")

    summary = {
        "fuente": "contraloria:fiscal-records",
        "found": bool(data.get("found")),
        "document_type": label,
        "document_number": document,
        "is_fiscal_responsible": responsible,
        "verification_code": code,
        "certified_at": data.get("certified_at"),
        "status_literal": data.get("status"),
        "message": data.get("message"),
    }
    code_note = f"; certificado verificable {code}" if code else ""
    reduction = Reduction(summary=summary)
    reduction.direct.append(
        DirectProposal(
            claim=(
                f"Contraloría responde para {label} {document}: "
                f"is_fiscal_responsible={responsible}{code_note}"
            ),
            raw_reference="data.is_fiscal_responsible",
        )
    )
    return reduction


# Dispatch por nombre de tool (ver agent.tools).
REDUCERS = {
    "rues_entities_by_name": reduce_entities_by_name,
    "rues_entity_by_nit": reduce_entity_by_nit,
    "secop_contracts_by_provider": reduce_contracts_by_provider,
    "secop_processes_by_entity": reduce_processes_by_entity,
    "procuraduria_disciplinary_records": reduce_disciplinary_records,
    "contraloria_fiscal_records": reduce_fiscal_records,
}


def reduce_tool_result(tool_name: str, payload: Any, args: dict[str, Any]) -> Reduction:
    """Aplica el reducer registrado para la tool; falla ruidoso si no existe."""
    reducer = REDUCERS.get(tool_name)
    if reducer is None:
        raise KeyError(f"No hay reducer registrado para la tool {tool_name!r}")
    return reducer(payload, args)
