import type { SourceConsulted } from "../types/caseFile";
import { sourceLabel } from "../lib/plainLanguage";
import { sourceIcon } from "../lib/sourceIcons";

interface InvestigationTimelineProps {
  sources: SourceConsulted[];
}

function formatTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit", hour12: false });
}

/**
 * "Ruta de la investigación": the agent's consultation route as a stepper, in
 * the real chronological order of sources_consulted (already sorted). The
 * point is to show the sequence was DECIDED step by step, not fixed upfront.
 * Horizontal with a connector line; collapses to vertical on narrow screens.
 * The technical id stays reachable via title= on each step.
 */
export function InvestigationTimeline({ sources }: InvestigationTimelineProps) {
  return (
    <section className="case-section timeline-section">
      <h3 className="section-title">Ruta de la investigación</h3>
      <p className="timeline-subtitle">
        Cada paso lo decidió el agente según lo que encontró en el anterior.
      </p>
      {sources.length === 0 ? (
        <p className="empty-note">No se registraron consultas.</p>
      ) : (
        <ol className="timeline">
          {sources.map((s, index) => {
            const { label, technical } = sourceLabel(s.source);
            const Icon = sourceIcon(s.source);
            // sourceLabel builds labels as "NOMBRE — detalle"; split only for
            // visual hierarchy — the full label text is always rendered.
            const [name, ...rest] = label.split(" — ");
            const detail = rest.join(" — ");
            const ok = s.status === "ok";
            return (
              <li
                key={`${s.source}-${s.at}-${index}`}
                className={ok ? "timeline-step" : "timeline-step timeline-step-silent"}
                title={technical}
              >
                <span className="timeline-icon" aria-hidden="true">
                  <Icon size={18} strokeWidth={1.9} />
                </span>
                <div className="timeline-info">
                  <span className="timeline-meta">
                    Paso {index + 1} · {formatTime(s.at)}
                  </span>
                  <span className="timeline-name">{name}</span>
                  {detail && <span className="timeline-detail">{detail}</span>}
                  <span className={ok ? "timeline-status" : "timeline-status timeline-status-silent"}>
                    {ok ? "respondió" : "no respondió"}
                  </span>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
