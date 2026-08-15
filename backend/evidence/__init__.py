"""Evidence Layer de TRAZA — modelos y verificación mecánica.

ESTADO: PROVISIONAL — pendiente de validar contra capturas reales de Croma.
Ver docs/evidence-layer.md para decisiones de diseño y preguntas abiertas.
"""

from evidence.models import (
    CalculationStep,
    Candidate,
    CaseFile,
    CaseStatus,
    DerivedEvidence,
    DirectEvidence,
    Entity,
    Evidence,
    Finding,
    SourceConsulted,
    SourceRef,
)
from evidence.verify import OPERATIONS, VerificationResult, verify_derived

__all__ = [
    "OPERATIONS",
    "CalculationStep",
    "Candidate",
    "CaseFile",
    "CaseStatus",
    "DerivedEvidence",
    "DirectEvidence",
    "Entity",
    "Evidence",
    "Finding",
    "SourceConsulted",
    "SourceRef",
    "VerificationResult",
    "verify_derived",
]
