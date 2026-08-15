import type { Evidence } from "../types/caseFile";

interface EvidenceItemProps {
  evidence: Evidence;
}

/**
 * One evidence object inside a finding.
 * - direct  → badge "HECHO" + source + raw reference.
 * - derived → badge "INFERENCIA" + visible calculation chain + expandable sources.
 */
export function EvidenceItem({ evidence }: EvidenceItemProps) {
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
            <code>{evidence.source}</code>
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
          <details className="evidence-sources">
            <summary>Fuentes del cálculo ({evidence.sources.length})</summary>
            <ul>
              {evidence.sources.map((source) => (
                <li key={source}>
                  <code>{source}</code>
                </li>
              ))}
            </ul>
          </details>
        </div>
      )}
    </li>
  );
}
