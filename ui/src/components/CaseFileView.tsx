import type { CaseFile } from "../types/caseFile";
import { plainSummary } from "../lib/plainLanguage";
import { EvidenceItem } from "./EvidenceItem";
import { SourceRef } from "./SourceRef";

interface CaseFileViewProps {
  caseFile: CaseFile;
  onNewInvestigation: () => void;
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("es-CO", { dateStyle: "medium", timeStyle: "short" });
}

/** Screen (c): the expediente. Findings as an expandable hierarchical list; unknowns and next steps always visible. */
export function CaseFileView({ caseFile, onNewInvestigation }: CaseFileViewProps) {
  const summary = plainSummary(caseFile);
  return (
    <article className="case-file">
      <header className="case-header">
        <p className="case-question-label">Pregunta investigada</p>
        <h2 className="case-question">{caseFile.question}</h2>
        {caseFile.status === "partial" && (
          <p className="partial-notice">
            Expediente parcial: alguna de las fuentes no respondió. Se muestra lo que sí se pudo
            consultar y se declara lo que falta en «Qué no sabemos».
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

      <section className="case-section">
        <h3 className="section-title">Fuentes consultadas</h3>
        <ul className="source-list">
          {caseFile.sources_consulted.map((s) => (
            <li key={`${s.source}-${s.at}`} className="source-row">
              <SourceRef id={s.source} />
              <span className="source-meta">
                {formatTimestamp(s.at)} ·{" "}
                {s.status === "ok" ? "respondió" : "no respondió"}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="case-section">
        <h3 className="section-title">Hallazgos</h3>
        {caseFile.findings.length === 0 ? (
          <p className="empty-note">Este expediente no contiene hallazgos.</p>
        ) : (
          <div className="finding-list">
            {caseFile.findings.map((finding, index) => (
              <details key={finding.id} className="finding" open={index === 0}>
                <summary className="finding-summary">
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
                      <EvidenceItem key={`${finding.id}-${i}`} evidence={evidence} />
                    ))}
                  </ul>
                </div>
              </details>
            ))}
          </div>
        )}
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

      <footer className="case-footer">
        <button type="button" className="btn-primary" onClick={onNewInvestigation}>
          Nueva investigación
        </button>
      </footer>
    </article>
  );
}
