// Documentación compacta de la landing, DEBAJO del cuadro de pregunta:
// el producto va primero, el manual después (queda bajo el fold a propósito).
// COPY CONGELADO: estas cadenas son verbatim del brief — no reformular,
// no "mejorar" redacción. Cada literal vive en una sola línea a propósito
// para que un diff textual contra el brief sea trivial.

// Educación del espacio de preguntas: título pequeño + preguntas reales,
// ANTES de "¿Cómo funciona?". Solo enseñan el rango de lo posible; no cargan
// el textarea (eso lo hacen los intents del cuadro de pregunta).
// Las dos preguntas EJECUTADAS de punta a punta contra producción (caso demo,
// NIT 901145160): la 1ª se corrió 5 veces con ruta y números idénticos; la 2ª
// activa la ruta exhaustiva y suele cerrar `partial` declarando el límite
// operacional — juntas muestran que el wording controla la profundidad.
// No agregar preguntas no ensayadas, y no repetir aquí las de INTENTS
// (QuestionInput) — quedan duplicadas literales en la misma pantalla.
const ASK_EXAMPLES_TITLE = "Puedes preguntar cosas como:";

const ASK_EXAMPLES = [
  "¿Por qué la empresa con NIT 901145160 concentra sus contratos públicos en el Distrito de Cali? Investiga y documenta.",
  "Investiga a fondo a la empresa con NIT 901145160 en la contratación pública colombiana: quiero un expediente completo, incluyendo cualquier antecedente relevante que encuentres.",
] as const;

const ASK_EXAMPLES_NOTE = "Las dos son sobre la misma empresa de ejemplo y las dos funcionan: la primera responde una pregunta puntual, la segunda pide todo lo que se pueda encontrar. Copia cualquiera y cámbiale el NIT — o escribe el nombre de la empresa que te interese.";

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
      <div className="ask-examples">
        <h2 className="ask-examples-title">{ASK_EXAMPLES_TITLE}</h2>
        <ul className="ask-examples-list">
          {ASK_EXAMPLES.map((question) => (
            <li key={question}>{question}</li>
          ))}
        </ul>
        <p className="ask-examples-note">{ASK_EXAMPLES_NOTE}</p>
      </div>

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
