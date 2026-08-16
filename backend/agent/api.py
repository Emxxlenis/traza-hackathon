"""Entrada pública del agente investigador (sin FastAPI: el orquestador la monta).

Contrato con la capa app:

    case = await investigate("¿Qué contratos tiene ...?")
    if case.status == "needs_disambiguation":
        case = await investigate(question, candidate_id=elegido.id)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent.loop import LoopConfig, run_investigation
from agent.providers import build_provider
from croma_client import CromaClient
from evidence.models import CaseFile


async def investigate(
    question: str,
    candidate_id: str | None = None,
    *,
    config: LoopConfig | None = None,
    trace: dict[str, Any] | None = None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> CaseFile:
    """Investiga la pregunta y devuelve el expediente (CaseFile) validado.

    Args:
        question: pregunta de investigación en lenguaje natural.
        candidate_id: id del candidato elegido para reanudar tras una
            respuesta needs_disambiguation.
        config: límites operacionales (default: los del producto).
        trace: dict opcional que se rellena con métricas (tokens, pasos) —
            lo usa el CLI; el orquestador puede ignorarlo.
        on_event: callback sync opcional de progreso (eventos observables del
            loop: consultas a fuentes y fase de ensamblado). Lo usa el endpoint
            de streaming; el CLI y el POST clásico no lo pasan y nada cambia.
    """
    provider = build_provider()
    async with CromaClient() as croma:
        return await run_investigation(
            question,
            candidate_id=candidate_id,
            provider=provider,
            croma=croma,
            config=config,
            trace=trace,
            on_event=on_event,
        )
