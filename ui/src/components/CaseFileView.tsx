import { FileDown, Info } from "lucide-react";
import type { CaseFile, SourceConsulted } from "../types/caseFile";
import { plainSummary, sourceLabel } from "../lib/plainLanguage";
import { printCaseFile } from "../lib/print";
import { EvidenceItem } from "./EvidenceItem";
import { InvestigationTimeline } from "./InvestigationTimeline";

interface CaseFileViewProps {
  caseFile: CaseFile;
  onNewInvestigation: () => void;
}

/** Short institution names for the "¿De dónde sale?" checklist. */
const INSTITUTION_NAMES: Record<string, string> = {
  rues: "RUES",
  secop: "SECOP",
  procuraduria: "Procuraduría",
  contraloria: "Contraloría",
};

/** "croma:secop:contracts-by-provider" → "SECOP"; unknown ids fall back to the readable label. */
function institutionName(sourceId: string): string {
  const segments = sourceId.split(":");
  if (segments[0] === "croma" && segments[1] && INSTITUTION_NAMES[segments[1]]) {
    return INSTITUTION_NAMES[segments[1]];
  }
  return sourceLabel(sourceId).label.split(" — ")[0];
}

interface SourceCheck {
  name: string;
  /** Consultations answered / total for this institution; per-step detail lives in the timeline. */
  okCount: number;
  total: number;
}

/** One line per unique institution consulted, in first-consultation order. */
function uniqueInstitutions(sources: SourceConsulted[]): SourceCheck[] {
  const byName = new Map<string, SourceCheck>();
  for (const s of sources) {
    const name = institutionName(s.source);
    const entry = byName.get(name) ?? { name, okCount: 0, total: 0 };
    entry.total += 1;
    if (s.status === "ok") entry.okCount += 1;
    byName.set(name, entry);
  }
  return [...byName.values()];
}

/**
 * Screen (c): the expediente, in two reading layers. The human layer reads
 * top-to-bottom: question → summary → entities → numbered findings → where
 * the data comes from → unknowns → next steps. The technical layer (full
 * timeline, ids, calculations) lives inside closed <details> — nothing is
 * removed, it only stops being the first level of reading.
 */
/**
 * True when some derived evidence in the case file claims a contractual
 * concentration ("concentra", case-insensitive) — the trigger for the sober
 * interpretive line under the plain summary.
 */
function hasConcentrationClaim(caseFile: CaseFile): boolean {
  return caseFile.findings.some((finding) =>
    finding.evidence.some(
      (ev) => ev.type === "derived" && ev.claim.toLowerCase().includes("concentra"),
    ),
  );
}

// Interpretive caveat (verbatim copy): concentration is shown, never explained.
const CONCENTRATION_CAVEAT =
  "Esto demuestra concentración contractual, pero no explica por sí solo por qué fueron adjudicados esos contratos.";

export function CaseFileView({ caseFile, onNewInvestigation }: CaseFileViewProps) {
  const summary = plainSummary(caseFile);
  const showCaveat = hasConcentrationClaim(caseFile);
  const institutions = uniqueInstitutions(caseFile.sources_consulted);
  // Fecha de generación del INFORME (presentación): se calcula al renderizar.
  // Las fechas probatorias son las de las fuentes consultadas, en el cuerpo.
  const generatedAt = new Date().toLocaleString("es-CO", {
    dateStyle: "long",
    timeStyle: "short",
  });
  return (
    <article className="case-file">
      {/* Membrete solo-impresión: reemplaza al header de la app en el papel. */}
      <div className="print-header">
        <p className="print-wordmark">TRAZA</p>
        <p className="print-doc-type">Expediente de investigación</p>
        <p className="print-question">{caseFile.question}</p>
        <p className="print-meta">
          Generado el {generatedAt} · {window.location.origin}
        </p>
      </div>

      <header className="case-header">
        <p className="case-question-label">Pregunta investigada</p>
        <h2 className="case-question">{caseFile.question}</h2>
        {caseFile.status === "partial" && (
          <p className="partial-notice">
            <Info size={16} aria-hidden="true" />
            <span>
              Expediente parcial: alguna de las fuentes no respondió. Se muestra lo que sí se pudo
              consultar y se declara lo que falta en «Qué no sabemos».
            </span>
          </p>
        )}
      </header>

      <details className="legend">
        <summary>¿Cómo leer este expediente?</summary>
        <p>
          <strong>HECHO</strong> es algo que una fuente oficial dice literalmente (siempre con la
          fuente citada). <strong>INFERENCIA</strong> es un dato calculado a partir de esas fuentes
          — el cálculo completo está visible y puede verificarse.{" "}
          <strong>Qué no sabemos</strong> enumera lo que la evidencia no permite concluir: TRAZA
          muestra evidencia, no emite veredictos.
        </p>
      </details>

      {summary && <p className="plain-summary">{summary}</p>}
      {showCaveat && <p className="summary-caveat">{CONCENTRATION_CAVEAT}</p>}

      <section className="case-section">
        <h3 className="section-title">Entidades</h3>
        {caseFile.entities.length === 0 ? (
          <p className="empty-note">No se identificaron entidades.</p>
        ) : (
          <ul className="entity-list">
            {caseFile.entities.map((entity) => (
              <li key={entity.id} className="entity-chip">
                <span className="entity-name">{entity.name}</span>
                <span className="entity-meta">
                  {entity.role} · <code>{entity.id}</code>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {caseFile.scope_note && <p className="scope-note">{caseFile.scope_note}</p>}

      <section className="case-section">
        <h3 className="section-title">Hallazgos</h3>
        {caseFile.findings.length === 0 ? (
          <p className="empty-note">Este expediente no contiene hallazgos.</p>
        ) : (
          <div className="finding-list">
            {caseFile.findings.map((finding, index) => (
              <details key={finding.id} className="finding" open={index === 0}>
                <summary className="finding-summary">
                  <span className="finding-number">{String(index + 1).padStart(2, "0")}</span>
                  <span className="finding-title">{finding.title}</span>
                  <span className="finding-count">
                    {finding.evidence.length}{" "}
                    {finding.evidence.length === 1 ? "evidencia" : "evidencias"}
                  </span>
                </summary>
                <div className="finding-body">
                  <p className="finding-narrative">{finding.narrative}</p>
                  <ul className="evidence-list">
                    {finding.evidence.map((evidence, i) => (
                      <EvidenceItem
                        key={`${finding.id}-${i}`}
                        evidence={evidence}
                        sourceUrls={caseFile.source_urls}
                      />
                    ))}
                  </ul>
                </div>
              </details>
            ))}
          </div>
        )}
      </section>

      <section className="case-section">
        <h3 className="section-title">¿De dónde sale?</h3>
        {institutions.length === 0 ? (
          <p className="empty-note">No se registraron consultas.</p>
        ) : (
          <ul className="source-checklist">
            {institutions.map(({ name, okCount, total }) => {
              const ok = okCount > 0;
              const silent = total - okCount;
              return (
                <li key={name} className="source-check">
                  <span className="source-check-name">{name}</span>
                  <span className={ok ? "source-check-status" : "source-check-status source-check-silent"}>
                    {ok ? "✓ respondió" : "— no respondió"}
                  </span>
                  {ok && silent > 0 && (
                    <span className="source-check-note">
                      ({silent === 1 ? "una consulta no respondió" : `${silent} consultas no respondieron`})
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        <details className="route-details">
          <summary>Ver ruta de la investigación</summary>
          <InvestigationTimeline sources={caseFile.sources_consulted} />
        </details>
      </section>

      <section className="case-section unknowns">
        <h3 className="section-title">Qué no sabemos</h3>
        {caseFile.unknowns.length === 0 ? (
          <p className="empty-note">No se declararon límites de la evidencia (revisar con el equipo).</p>
        ) : (
          <ul className="plain-list">
            {caseFile.unknowns.map((u) => (
              <li key={u}>{u}</li>
            ))}
          </ul>
        )}
      </section>

      <section className="case-section next-steps">
        <h3 className="section-title">Siguientes pasos</h3>
        {caseFile.next_steps.length === 0 ? (
          <p className="empty-note">Sin pasos sugeridos.</p>
        ) : (
          <ul className="plain-list">
            {caseFile.next_steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        )}
      </section>

      <footer className="case-footer case-actions">
        <button type="button" className="btn-primary" onClick={onNewInvestigation}>
          Nueva investigación
        </button>
        <button type="button" className="btn-secondary btn-with-icon" onClick={printCaseFile}>
          <FileDown size={16} aria-hidden="true" />
          Descargar informe (PDF)
        </button>
      </footer>

      {/* Pie solo-impresión: sustento documental del informe. */}
      <p className="print-footer">
        Este informe fue generado automáticamente por TRAZA a partir de fuentes oficiales del
        Estado colombiano consultadas vía Croma. Cada hallazgo conserva su fuente verificable; los
        documentos originales de cada contrato están disponibles en los enlaces oficiales de SECOP
        incluidos en este informe. TRAZA no emite veredictos ni puntajes de riesgo.
      </p>
    </article>
  );
}
