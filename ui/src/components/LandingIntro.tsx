import { FileSearch, Scale, Users } from "lucide-react";

// Contenido estático de la landing, ARRIBA del cuadro de pregunta.
// COPY CONGELADO: estas cadenas son verbatim del brief — no reformular,
// no "mejorar" redacción. Cada literal vive en una sola línea a propósito
// para que un diff textual contra el brief sea trivial.

const GOAL =
  "TRAZA busca en fuentes oficiales del Estado colombiano y te muestra la evidencia, con la fuente exacta de cada dato — sin emitir veredictos.";

const CARDS = [
  {
    Icon: Users,
    title: "¿Para quién es esto?",
    text: "Periodistas, veedurías ciudadanas, investigadores independientes, y cualquier persona con una pregunta sobre contratación pública en Colombia.",
  },
  {
    Icon: FileSearch,
    title: "¿Qué puede investigar?",
    text: "Empresas colombianas registradas en RUES: sus contratos públicos (SECOP), antecedentes disciplinarios (Procuraduría) y fiscales (Contraloría).",
  },
  {
    Icon: Scale,
    title: "¿Qué NO hace?",
    text: "No determina si algo es corrupto ni asigna puntajes de riesgo. Muestra hechos con su fuente y separa lo que la evidencia sí permite concluir de lo que no.",
  },
] as const;

const NOTES_SUMMARY = "¿Qué debo tener en cuenta antes de investigar?";

const NOTES = [
  "Los datos vienen de fuentes públicas oficiales vía Croma, no de internet en general.",
  "La forma en que escribas la pregunta cambia qué tan a fondo investiga el agente — entre más específica, mejor.",
  "Puede tardar entre 15 segundos y 2 minutos según la complejidad.",
  "Si una empresa aparece «sin resultados», no significa que no exista — puede que la fuente no tenga registro, y el expediente lo va a explicar.",
] as const;

/** Intro de la landing: objetivo, audiencia/alcance/límites y advertencias. */
export function LandingIntro() {
  return (
    <div className="landing-intro">
      <p className="landing-goal">{GOAL}</p>

      <div className="landing-cards">
        {CARDS.map(({ Icon, title, text }) => (
          <article key={title} className="landing-card">
            <h3 className="landing-card-title">
              <Icon size={17} aria-hidden="true" />
              {title}
            </h3>
            <p className="landing-card-text">{text}</p>
          </article>
        ))}
      </div>

      {/* Mismo patrón visual que la leyenda del expediente (.legend) */}
      <details className="legend landing-legend">
        <summary>{NOTES_SUMMARY}</summary>
        <ul className="landing-legend-list">
          {NOTES.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      </details>
    </div>
  );
}
