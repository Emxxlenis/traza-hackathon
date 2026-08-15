import type { CalculationStep, Evidence } from "../types/caseFile";
import { plainCalculation } from "../lib/plainLanguage";
import { SourceRef } from "./SourceRef";

interface EvidenceItemProps {
  evidence: Evidence;
}

/**
 * "$i = operation(inputs) → output". Steps reference previous outputs as "$k"
 * (contract v0.1), so each line is labeled with its own "$i" to make the
 * chain mechanically traceable by eye.
 */
function formatStep(step: CalculationStep, index: number): string {
  return `$${index} = ${step.operation}(${step.inputs.join(", ")}) → ${step.output}`;
}

/**
 * One evidence object inside a finding.
 * - direct  → badge "HECHO" + source + raw reference.
 * - derived → badge "INFERENCIA" + visible calculation chain + expandable sources.
 */
export function EvidenceItem({ evidence }: EvidenceItemProps) {
  const plainCalc = evidence.type === "derived" ? plainCalculation(evidence) : null;
  return (
    <li className={`evidence evidence-${evidence.type}`}>
      <div className="evidence-head">
        {evidence.type === "direct" ? (
          <span className="badge badge-direct" title="Lo dice la fuente oficial">
            HECHO
          </span>
        ) : (
          <span className="badge badge-derived" title="Calculado a partir de fuentes">
            INFERENCIA
          </span>
        )}
        <p className="evidence-claim">{evidence.claim}</p>
      </div>

      {evidence.type === "direct" ? (
        <div className="evidence-body">
          <p className="evidence-source">
            <span className="evidence-field-label">Fuente:</span>{" "}
            <SourceRef id={evidence.source} />
          </p>
          <p className="evidence-raw">
            <span className="evidence-field-label">Referencia:</span>{" "}
            <code>{evidence.raw_reference}</code>
          </p>
        </div>
      ) : (
        <div className="evidence-body">
          <p className="evidence-field-label">Cálculo:</p>
          <pre className="calculation">{evidence.calculation}</pre>
          {plainCalc && <p className="plain-calc">{plainCalc}</p>}
          {evidence.calculation_steps && evidence.calculation_steps.length > 0 && (
            <details className="calculation-steps">
              <summary>Pasos del cálculo ({evidence.calculation_steps.length})</summary>
              <ol className="calculation-step-list">
                {evidence.calculation_steps.map((step, i) => (
                  <li key={i}>
                    <code>{formatStep(step, i)}</code>
                  </li>
                ))}
              </ol>
            </details>
          )}
          <details className="evidence-sources">
            <summary>Fuentes del cálculo ({evidence.sources.length})</summary>
            <ul>
              {evidence.sources.map((source) => (
                <li key={source}>
                  <SourceRef id={source} />
                </li>
              ))}
            </ul>
          </details>
        </div>
      )}
    </li>
  );
}
