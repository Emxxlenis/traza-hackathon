import { useState } from "react";
import { USE_MOCK } from "../api/client";
import { LandingIntro } from "./LandingIntro";

// COPY CONGELADO: estas cadenas son verbatim del brief — no reformular,
// no "mejorar" redacción. Cada literal vive en una sola línea a propósito
// para que un diff textual contra el brief sea trivial.

const INVITE_HEADING = "¿Hay algo sobre una empresa o sus contratos públicos que quieras entender?";

const INVITE_SUB = "No necesitas saber dónde buscar. Puedes escribir el nombre de la empresa, su NIT o simplemente contarlo con tus palabras.";

const TEXTAREA_LABEL = "Pregunta de investigación";

const TEXTAREA_PLACEHOLDER = "Ej.: Quiero saber por qué esta empresa recibe tantos contratos del Distrito de Cali.";

const INTENTS_TITLE = "¿No sabes por dónde empezar?";

// En modo real los intents cargan preguntas reales y útiles (empresa con datos
// públicos verificados); las ficticias solo existen en modo mock/fixtures y
// conservan los ejemplos actuales con esta misma presentación.
const INTENTS = USE_MOCK
  ? [
      {
        emoji: "🏢",
        title: "Investigar una empresa",
        question: "¿Qué contratos públicos tiene Distribuidora Andina?",
      },
      {
        emoji: "💰",
        title: "Entender sus contratos",
        question:
          "¿Por qué Empresa Ejemplo S.A.S. concentra tantos contratos con la Entidad Ficticia de Ejemplo?",
      },
      {
        emoji: "👤",
        title: "Seguir una relación",
        question: "¿Cómo ha crecido el valor contratado por Empresa Ejemplo S.A.S. desde 2022?",
      },
    ]
  : [
      {
        emoji: "🏢",
        title: "Investigar una empresa",
        question: "¿Qué contratos públicos ha recibido la empresa con NIT 901145160?",
      },
      {
        emoji: "💰",
        title: "Entender sus contratos",
        question: "¿En qué entidades se concentra la contratación de la empresa con NIT 901145160? Investiga y documenta.",
      },
      {
        emoji: "👤",
        title: "Seguir una relación",
        question: "¿Quién aparece como representante legal de la empresa con NIT 901145160 y qué antecedentes públicos tiene?",
      },
    ];

interface QuestionInputProps {
  onSubmit: (question: string) => void;
}

/** Screen (a): el producto primero (invitación + textarea + intents);
 * la documentación compacta va DEBAJO del fold, en LandingIntro. */
export function QuestionInput({ onSubmit }: QuestionInputProps) {
  const [question, setQuestion] = useState("");
  const trimmed = question.trim();

  function submit() {
    if (trimmed.length > 0) {
      onSubmit(trimmed);
    }
  }

  return (
    <section className="ask">
      <h2 className="ask-heading">{INVITE_HEADING}</h2>
      <p className="ask-sub">{INVITE_SUB}</p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <label htmlFor="question-input" className="sr-only">
          {TEXTAREA_LABEL}
        </label>
        <textarea
          id="question-input"
          className="ask-textarea"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder={TEXTAREA_PLACEHOLDER}
          rows={4}
          maxLength={1000}
          autoFocus
        />
        <div className="ask-actions">
          <span className="ask-hint">Ctrl + Enter para enviar</span>
          <button type="submit" className="btn-primary" disabled={trimmed.length === 0}>
            Investigar
          </button>
        </div>
      </form>

      <div className="intents">
        <p className="intents-title">{INTENTS_TITLE}</p>
        <ul className="intent-list">
          {INTENTS.map(({ emoji, title, question: intentQuestion }) => (
            <li key={title}>
              {/* Carga la pregunta en el textarea, NUNCA dispara la investigación:
                  cada investigación real consume cupo de rate limit y tokens. */}
              <button
                type="button"
                className="intent-chip"
                onClick={() => setQuestion(intentQuestion)}
              >
                <span className="intent-emoji" aria-hidden="true">
                  {emoji}
                </span>
                <span className="intent-body">
                  <span className="intent-title">{title}</span>
                  <span className="intent-question">{intentQuestion}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      <hr className="landing-separator" />

      <LandingIntro />
    </section>
  );
}
