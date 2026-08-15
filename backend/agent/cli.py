"""CLI de smoke test del agente: python -m agent.cli "pregunta" [--candidate ID] [--json].

Imprime el expediente legible por humanos (o el JSON del contrato v0 con
--json) por stdout, y las métricas de la corrida (pasos, tokens, tiempo) por
stderr para no ensuciar el JSON.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from agent.api import investigate
from croma_client.exceptions import CromaConfigError
from evidence.models import CaseFile


def _print_human(case: CaseFile) -> None:
    print(f"PREGUNTA : {case.question}")
    print(f"ESTADO   : {case.status}")
    if case.candidates:
        print("\nCANDIDATOS (elige uno y reanuda con --candidate <id>):")
        for candidate in case.candidates:
            detail = f" — {candidate.detail}" if candidate.detail else ""
            print(f"  · {candidate.id}: {candidate.name}{detail}")
    if case.entities:
        print("\nENTIDADES:")
        for entity in case.entities:
            print(f"  · [{entity.role}] {entity.name} ({entity.id})")
    print("\nFUENTES CONSULTADAS:")
    for source in case.sources_consulted:
        print(f"  · {source.status.upper():5s} {source.source} @ {source.at.isoformat()}")
    if case.findings:
        print("\nHALLAZGOS:")
        for finding in case.findings:
            print(f"\n  [{finding.id}] {finding.title}")
            print(f"      {finding.narrative}")
            for evidence in finding.evidence:
                if evidence.type == "direct":
                    print(f"      - (direct)  {evidence.claim}")
                    print(f"                  fuente: {evidence.source} → {evidence.raw_reference}")
                else:
                    print(f"      - (derived) {evidence.claim}")
                    print(f"                  cálculo: {evidence.calculation} "
                          f"[{len(evidence.calculation_steps)} pasos verificados]")
    if case.unknowns:
        print("\nLO QUE NO SE SABE:")
        for unknown in case.unknowns:
            print(f"  · {unknown}")
    if case.next_steps:
        print("\nPRÓXIMOS PASOS SUGERIDOS:")
        for step in case.next_steps:
            print(f"  · {step}")


async def _run(args: argparse.Namespace) -> int:
    trace: dict = {}
    started = time.monotonic()
    try:
        case = await investigate(args.question, candidate_id=args.candidate, trace=trace)
    except CromaConfigError as exc:
        print(f"Configuración de Croma inválida: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"Configuración del LLM inválida: {exc}", file=sys.stderr)
        return 2
    elapsed = time.monotonic() - started

    if args.json:
        print(case.to_contract_json())
    else:
        _print_human(case)

    usage = trace.get("usage", {})
    print(
        f"\n[trace] estado={trace.get('final_status')} "
        f"llm_calls={trace.get('llm_calls')} pasos={trace.get('steps_used')} "
        f"evidencias={trace.get('evidence_count')} raws={trace.get('raw_count')} "
        f"tokens={usage.get('total_tokens')} "
        f"(prompt={usage.get('prompt_tokens')}, completion={usage.get('completion_tokens')}) "
        f"tiempo={elapsed:.1f}s",
        file=sys.stderr,
    )
    for tool_call in trace.get("tool_calls", []):
        print(f"[trace] tool {tool_call['status']:>18s}  {tool_call['tool']} "
              f"{tool_call['args']}", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m agent.cli",
        description="Corre una investigación TRAZA de punta a punta (Croma + LLM reales).",
    )
    parser.add_argument("question", help="Pregunta de investigación en lenguaje natural.")
    parser.add_argument(
        "--candidate",
        default=None,
        help="candidate_id elegido para reanudar tras needs_disambiguation.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Imprime el expediente como JSON del contrato v0 (stdout limpio).",
    )
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
