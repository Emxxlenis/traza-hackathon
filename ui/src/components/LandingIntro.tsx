// Documentación compacta de la landing, DEBAJO del cuadro de pregunta:
// el producto va primero, el manual después (queda bajo el fold a propósito).
// COPY CONGELADO: estas cadenas son verbatim del brief — no reformular,
// no "mejorar" redacción. Cada literal vive en una sola línea a propósito
// para que un diff textual contra el brief sea trivial.

const HOW_TITLE = "¿Cómo funciona?";

const STEPS = [
  {
    title: "1. Haz una pregunta",
    text: "No necesitas saber dónde buscar.",
  },
  {
    title: "2. TRAZA investiga",
    text: "Consulta fuentes oficiales del Estado colombiano y conecta la información relevante.",
  },
  {
    title: "3. Revisa la evidencia",
    text: "Cada hallazgo muestra la fuente exacta de donde salió.",
  },
] as const;

const SCOPE_LINE = "TRAZA no decide quién es culpable. Te ayuda a entender qué dicen los datos oficiales — y cada hallazgo incluye la fuente que puedes revisar.";

const NOTES_SUMMARY = "¿Qué debo tener en cuenta antes de investigar?";

// El punto de los tiempos ("Puede tardar entre 15 segundos y 2 minutos…")
// se mudó al estado de carga en App.tsx — no lo re-agregues aquí.
const NOTES = [
  "Los datos vienen de fuentes públicas oficiales vía Croma, no de internet en general.",
  "La forma en que escribas la pregunta cambia qué tan a fondo investiga el agente — entre más específica, mejor.",
  "Si una empresa aparece «sin resultados», no significa que no exista — puede que la fuente no tenga registro, y el expediente lo va a explicar.",
] as const;

/** Documentación de la landing: cómo funciona (3 pasos), alcance y advertencias. */
export function LandingIntro() {
  return (
    <div className="landing-intro">
      <h2 className="how-title">{HOW_TITLE}</h2>

      <div className="how-steps">
        {STEPS.map(({ title, text }) => (
          <article key={title} className="how-step">
            <h3 className="how-step-title">{title}</h3>
            <p className="how-step-text">{text}</p>
          </article>
        ))}
      </div>

      <p className="landing-scope">{SCOPE_LINE}</p>

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
