"""EvidenceStore: refs estables a respuestas crudas + fábrica de evidencia.

Responsabilidades:
  1. Guardar cada ``RawResponse`` bajo un ref estable
     ``croma:<fuente>:<endpoint>:<n>`` (n = orden de ingestión, 1-based).
  2. Registrar refs por contrato real (``croma:secop:contract:<contract_id>``)
     apuntando al raw que los contiene.
  3. Fabricar ``DirectEvidence``/``DerivedEvidence`` referenciando esos refs.
     TODO derived pasa por ``verify_derived`` ANTES de aceptarse: si la cadena
     no recomputa, se rechaza con log y NUNCA entra al expediente.

Los ids de evidencia ("ev1", "ev2", ...) son los que el LLM ve en
``evidencia_disponible`` y los únicos que puede citar en sus hallazgos.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import ValidationError

from croma_client.envelope import RawResponse
from evidence.models import (
    SOURCE_REF_PATTERN,
    CalculationStep,
    DerivedEvidence,
    DirectEvidence,
)
from evidence.verify import verify_derived

logger = logging.getLogger("traza.agent.store")

_SOURCE_REF_RE = re.compile(SOURCE_REF_PATTERN)
# Caracteres válidos en el segmento final de un SourceRef (id).
_REF_ID_CLEAN_RE = re.compile(r"[^A-Za-z0-9._-]+")

Evidence = DirectEvidence | DerivedEvidence


class EvidenceStore:
    """Almacén de raws + evidencia fabricada, con verify_derived como puerta."""

    def __init__(self) -> None:
        self._raw: dict[str, RawResponse] = {}
        self._contract_refs: dict[str, str] = {}  # ref de contrato -> ref del raw padre
        self._contract_urls: dict[str, str] = {}  # ref de contrato -> url oficial (v0.3)
        self._evidence: dict[str, Evidence] = {}
        self._raw_count = 0
        self._evidence_count = 0

    # --- Raws y refs ---

    def ingest_raw(self, raw: RawResponse) -> str:
        """Guarda un RawResponse y devuelve su ref estable croma:...:<n>."""
        self._raw_count += 1
        ref = f"{raw.source}:{self._raw_count}"
        self._raw[ref] = raw
        return ref

    def register_contract_ref(
        self, contract_id: str, raw_ref: str, url: str | None = None
    ) -> str | None:
        """Registra el ref real de un contrato (croma:secop:contract:<id>).

        ``url`` es la URL oficial del contrato en la fuente (contrato v0.3);
        se acumula para que el ensamblado construya ``CaseFile.source_urls``.
        Devuelve None (con log) si el id no puede formar un SourceRef válido o
        si el raw padre no existe.
        """
        if raw_ref not in self._raw:
            logger.warning("contract ref rechazado: raw padre desconocido %r", raw_ref)
            return None
        cleaned = _REF_ID_CLEAN_RE.sub("-", str(contract_id)).strip("-._")
        ref = f"croma:secop:contract:{cleaned}" if cleaned else ""
        if not ref or not _SOURCE_REF_RE.match(ref):
            logger.warning("contract_id %r no forma un SourceRef válido; se omite", contract_id)
            return None
        self._contract_refs[ref] = raw_ref
        if url:
            self._contract_urls[ref] = url
        return ref

    def contract_url(self, ref: str) -> str | None:
        """URL oficial registrada para un ref de contrato, si la fuente la trajo."""
        return self._contract_urls.get(ref)

    def has_ref(self, ref: str) -> bool:
        """True si el ref apunta a un raw ingerido o a un contrato registrado."""
        return ref in self._raw or ref in self._contract_refs

    def raw_by_ref(self, ref: str) -> RawResponse | None:
        """Resuelve un ref (raw o contrato) al RawResponse que lo respalda."""
        if ref in self._raw:
            return self._raw[ref]
        parent = self._contract_refs.get(ref)
        return self._raw.get(parent) if parent else None

    # --- Fábrica de evidencia ---

    def _next_evidence_id(self) -> str:
        self._evidence_count += 1
        return f"ev{self._evidence_count}"

    def add_direct(self, claim: str, source: str, raw_reference: str) -> str | None:
        """Fabrica DirectEvidence sobre un ref existente; devuelve su id."""
        if not self.has_ref(source):
            logger.warning("direct rechazada: ref inexistente %r (claim: %s)", source, claim)
            return None
        try:
            evidence = DirectEvidence(claim=claim, source=source, raw_reference=raw_reference)
        except ValidationError as exc:
            logger.warning("direct rechazada por validación: %s", exc)
            return None
        evidence_id = self._next_evidence_id()
        self._evidence[evidence_id] = evidence
        return evidence_id

    def add_derived(
        self,
        claim: str,
        calculation: str,
        steps: list[CalculationStep] | tuple[CalculationStep, ...],
        sources: list[str],
    ) -> str | None:
        """Fabrica DerivedEvidence. Puerta dura: verify_derived debe pasar.

        Rechaza (con log, devolviendo None) si alguna fuente no está en el
        store, si el modelo no valida, o si la cadena de cálculo no recomputa.
        """
        unknown = [s for s in sources if not self.has_ref(s)]
        if unknown:
            logger.warning("derived rechazada: refs inexistentes %s (claim: %s)", unknown, claim)
            return None
        try:
            evidence = DerivedEvidence(
                claim=claim,
                calculation=calculation,
                calculation_steps=list(steps),
                sources=list(sources),
            )
        except ValidationError as exc:
            logger.warning("derived rechazada por validación: %s", exc)
            return None
        result = verify_derived(evidence)
        if not result.valid:
            logger.warning(
                "derived rechazada por verify_derived (claim: %s): %s", claim, result.errors
            )
            return None
        evidence_id = self._next_evidence_id()
        self._evidence[evidence_id] = evidence
        return evidence_id

    # --- Lectura ---

    def get(self, evidence_id: str) -> Evidence | None:
        """Evidencia por id ("ev3"), o None si el LLM citó algo inexistente."""
        return self._evidence.get(evidence_id)

    def evidence_ids(self) -> list[str]:
        return list(self._evidence)

    def catalog(self) -> list[dict[str, Any]]:
        """Listado id+claim de toda la evidencia fabricada (para depuración)."""
        return [{"id": eid, "claim": ev.claim} for eid, ev in self._evidence.items()]

    @property
    def raw_count(self) -> int:
        return self._raw_count

    @property
    def evidence_count(self) -> int:
        return len(self._evidence)
