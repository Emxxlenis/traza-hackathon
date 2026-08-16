import { ExternalLink } from "lucide-react";
import type { CalculationStep, Evidence } from "../types/caseFile";
import {
  CONTRACT_PREFIX,
  humanCalculation,
  plainCalculation,
  sourceLabel,
} from "../lib/plainLanguage";
import { SourceRef } from "./SourceRef";

interface EvidenceItemProps {
  evidence: Evidence;
  /** Contract v0.3 map SourceRef → official URL; absent on older case files. */
  sourceUrls?: Record<string, string>;
}

/**
 * "$i = operation(inputs) → output". Steps reference previous outputs as "$k"
 * (contract v0.1), so each line is labeled with its own "$i" to make the
 * chain mechanically traceable by eye.
 */
function formatStep(step: CalculationStep, index: number): string {
  return `$${index} = ${step.operation}(${step.inputs.join(", ")}) → ${step.output}`;
}

/** External link to the official source (contract v0.3); always a new tab. */
function OfficialLink({ href, label }: { href: string; label: string }) {
  return (
    <a className="source-link" href={href} target="_blank" rel="noopener noreferrer">
      <ExternalLink size={14} aria-hidden="true" />
      {label}
    </a>
  );
}

/**
 * One evidence object, in two reading layers:
 * - Layer 1 (always visible, human): badge HECHO/INFERENCIA + claim, the
 *   plain-language calculation line for derived evidence, and ONE readable
 *   source line without technical ids.
 * - Layer 2 (audit, <details> closed by default): opens with the human
 *   "Cómo lo calculamos" block (structural sentence + arithmetic) and the
 *   calculation sources (with official links when the case file carries
 *   source_urls); EVERYTHING technical — raw calculation, $k steps, full
 *   source ids, raw_reference — moves inside "Ver detalle técnico". Nothing
 *   is dropped; it only moves down a layer.
 */
export function EvidenceItem({ evidence, sourceUrls }: EvidenceItemProps) {
  const plainCalc = evidence.type === "derived" ? plainCalculation(evidence) : null;
  const humanCalc = evidence.type === "derived" ? humanCalculation(evidence) : null;

  // Human source line (level 1): readable label only, never the technical id.
  const primarySource = evidence.type === "direct" ? evidence.source : evidence.sources[0];
  const humanSource = primarySource ? sourceLabel(primarySource).label : null;
  const extraSources = evidence.type === "derived" ? Math.max(evidence.sources.length - 1, 0) : 0;
  const directUrl = evidence.type === "direct" ? sourceUrls?.[evidence.source] : undefined;

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

      <div className="evidence-body">
        {plainCalc && <p className="plain-calc">{plainCalc}</p>}

        {humanSource && (
          <p className="evidence-source-human">
            Fuente oficial: {humanSource}
            {extraSources > 0 &&
              ` · y ${extraSources} ${extraSources === 1 ? "fuente más" : "fuentes más"}`}
          </p>
        )}

        <details className="evidence-audit">
          <summary>¿Cómo se obtuvo este hallazgo?</summary>
          <div className="evidence-audit-body">
            {evidence.type === "direct" ? (
              <details className="tech-detail">
                <summary>Ver detalle técnico</summary>
                <div className="tech-detail-body">
                  <p className="evidence-source">
                    <span className="evidence-field-label">Fuente:</span>{" "}
                    <SourceRef id={evidence.source} />
                    {directUrl && (
                      <>
                        {" "}
                        <OfficialLink href={directUrl} label="Ver fuente oficial" />
                      </>
                    )}
                  </p>
                  <p className="evidence-raw">
                    <span className="evidence-field-label">Referencia:</span>{" "}
                    <code>{evidence.raw_reference}</code>
                  </p>
                </div>
              </details>
            ) : (
              <>
                {humanCalc && (
                  <div className="human-calc">
                    <p className="evidence-field-label">Cómo lo calculamos</p>
                    <p className="human-calc-sentence">{humanCalc.sentence}</p>
                    <p className="human-calc-formula">{humanCalc.formula}</p>
                  </div>
                )}

                <details className="tech-detail">
                  <summary>Ver detalle técnico</summary>
                  <div className="tech-detail-body">
                    <p className="evidence-field-label">Cálculo:</p>
                    <pre className="calculation">{evidence.calculation}</pre>
                    {evidence.calculation_steps && evidence.calculation_steps.length > 0 && (
                      <div className="calculation-steps">
                        <p className="evidence-field-label">
                          Pasos del cálculo ({evidence.calculation_steps.length})
                        </p>
                        <ol className="calculation-step-list">
                          {evidence.calculation_steps.map((step, i) => (
                            <li key={i}>
                              <code>{formatStep(step, i)}</code>
                            </li>
                          ))}
                        </ol>
                      </div>
                    )}
                  </div>
                </details>

                <details className="evidence-sources">
                  <summary>Fuentes del cálculo ({evidence.sources.length})</summary>
                  <ul>
                    {evidence.sources.map((source) => {
                      // "Ver contrato" only on real contract refs (the v0.3
                      // map should not carry anything else, but stay strict).
                      const url = source.startsWith(CONTRACT_PREFIX)
                        ? sourceUrls?.[source]
                        : undefined;
                      return (
                        <li key={source}>
                          <SourceRef id={source} />
                          {url && (
                            <>
                              {" "}
                              <OfficialLink href={url} label="Ver contrato" />
                            </>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </details>
              </>
            )}
          </div>
        </details>
      </div>
    </li>
  );
}
