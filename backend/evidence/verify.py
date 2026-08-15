"""Verificación mecánica de evidencia derivada.

`verify_derived` re-ejecuta la cadena `calculation_steps` de un
`DerivedEvidence` y comprueba que:

1. `sources` no está vacía (defensa en profundidad: el modelo ya lo impide).
2. Toda operación pertenece al registro cerrado `OPERATIONS`.
3. Todo input es un número literal o una referencia "$k" a un paso ANTERIOR
   que sí pudo recomputarse (nada de referencias hacia adelante ni a sí mismo).
4. El output declarado de CADA paso coincide con el recomputado (tolerancia
   numérica `math.isclose`), incluido el output final.

Esta función es la garantía estructural de "reproducible mecánicamente": el
expediente final solo acepta evidencia `derived` que pase verify_derived.
La expresión legible `calculation` NO se re-ejecuta — es solo para humanos.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence

from pydantic import BaseModel, ConfigDict, Field

from evidence.models import DerivedEvidence

# Referencia al output de un paso anterior: "$0", "$1", ...
_STEP_REF = re.compile(r"^\$(\d+)$")


def _op_sum(values: Sequence[float]) -> float:
    return math.fsum(values)


def _op_subtract(values: Sequence[float]) -> float:
    a, b = values
    return a - b


def _op_multiply(values: Sequence[float]) -> float:
    result = 1.0
    for v in values:
        result *= v
    return result


def _op_divide(values: Sequence[float]) -> float:
    a, b = values
    if b == 0:
        raise ZeroDivisionError("división por cero")
    return a / b


def _op_round(values: Sequence[float]) -> float:
    value, ndigits = values
    if ndigits != int(ndigits):
        raise ValueError("round exige un número entero de dígitos")
    return round(value, int(ndigits))


# Registro cerrado de operaciones deterministas. Mantenerlo pequeño es
# deliberado: cada operación nueva amplía lo que un `derived` puede afirmar,
# y debe poder recomputarse sin ambigüedad.
OPERATIONS: dict[str, Callable[[Sequence[float]], float]] = {
    "sum": _op_sum,
    "subtract": _op_subtract,
    "multiply": _op_multiply,
    "divide": _op_divide,
    "round": _op_round,
}

# Operaciones con aridad exacta (las demás aceptan 1 o más inputs).
_EXACT_ARITY: dict[str, int] = {
    "subtract": 2,
    "divide": 2,
    "round": 2,
}


class VerificationResult(BaseModel):
    """Resultado de re-ejecutar la cadena de cálculo de un derived."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    errors: list[str] = Field(default_factory=list)
    declared_output: float | None = None
    recomputed_output: float | None = None


def verify_derived(
    evidence: DerivedEvidence,
    *,
    rel_tol: float = 1e-9,
    abs_tol: float = 1e-9,
) -> VerificationResult:
    """Re-ejecuta calculation_steps y verifica la coherencia de la cadena.

    Devuelve VerificationResult con valid=True solo si la cadena completa se
    recomputa sin errores y cada output declarado coincide con el recomputado.
    """
    errors: list[str] = []

    # Defensa en profundidad: el modelo ya exige sources y steps no vacíos,
    # pero verify es la puerta final del expediente y no confía en nadie.
    if not evidence.sources:
        errors.append("sources vacía: un derived exige al menos una fuente")
    if not evidence.calculation_steps:
        errors.append("calculation_steps vacía: no hay cadena que re-ejecutar")

    # outputs[i] = output RECOMPUTADO del paso i, o None si el paso falló.
    # Las referencias "$k" resuelven contra el valor recomputado (no el
    # declarado) para que un output declarado falso no contamine la cadena.
    outputs: list[float | None] = []

    for i, step in enumerate(evidence.calculation_steps):
        operation = OPERATIONS.get(step.operation)
        if operation is None:
            errors.append(
                f"paso {i}: operación desconocida '{step.operation}' "
                f"(válidas: {sorted(OPERATIONS)})"
            )
            outputs.append(None)
            continue

        resolved: list[float] = []
        resolvable = True
        for raw in step.inputs:
            if isinstance(raw, str):
                match = _STEP_REF.match(raw)
                if match is None:
                    errors.append(
                        f"paso {i}: input '{raw}' no es un número ni una "
                        "referencia '$k' a un paso anterior"
                    )
                    resolvable = False
                    continue
                k = int(match.group(1))
                if k >= i:
                    errors.append(
                        f"paso {i}: referencia '$'{k} no apunta a un paso anterior"
                    )
                    resolvable = False
                    continue
                if outputs[k] is None:
                    errors.append(
                        f"paso {i}: referencia '$'{k} apunta a un paso que no "
                        "pudo recomputarse"
                    )
                    resolvable = False
                    continue
                resolved.append(outputs[k])
            else:
                resolved.append(float(raw))

        if not resolvable:
            outputs.append(None)
            continue

        expected_arity = _EXACT_ARITY.get(step.operation)
        if expected_arity is not None and len(resolved) != expected_arity:
            errors.append(
                f"paso {i}: '{step.operation}' exige exactamente "
                f"{expected_arity} inputs, recibió {len(resolved)}"
            )
            outputs.append(None)
            continue

        try:
            recomputed = operation(resolved)
        except (ZeroDivisionError, ValueError) as exc:
            errors.append(f"paso {i}: {exc}")
            outputs.append(None)
            continue

        # Se guarda el valor recomputado aunque no coincida con el declarado,
        # para poder seguir la cadena y reportar todos los errores de una vez.
        outputs.append(recomputed)
        if not math.isclose(recomputed, step.output, rel_tol=rel_tol, abs_tol=abs_tol):
            errors.append(
                f"paso {i}: output declarado {step.output} no coincide con el "
                f"recomputado {recomputed}"
            )

    declared = (
        float(evidence.calculation_steps[-1].output)
        if evidence.calculation_steps
        else None
    )
    recomputed_final = outputs[-1] if outputs else None

    return VerificationResult(
        valid=not errors and recomputed_final is not None,
        errors=errors,
        declared_output=declared,
        recomputed_output=recomputed_final,
    )
