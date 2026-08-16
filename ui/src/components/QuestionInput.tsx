import { useState } from "react";
import { Building2, FileText, UserSearch } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { USE_MOCK } from "../api/client";
import { LandingIntro } from "./LandingIntro";

// COPY CONGELADO: estas cadenas son verbatim del brief — no reformular,
// no "mejorar" redacción. Cada literal vive en una sola línea a propósito
// para que un diff textual contra el brief sea trivial.
// Excepción: INVITE_EXPLAINER se agregó después del brief (a pedido) para que
// se entienda qué hace TRAZA sin leer la documentación de abajo.

const INVITE_HEADING = "¿Hay algo sobre una empresa o sus contratos públicos que quieras entender?";

const INVITE_SUB = "No necesitas saber dónde buscar. Puedes escribir el nombre de la empresa, su NIT o simplemente contarlo con tus palabras.";

const INVITE_EXPLAINER = "TRAZA va a los registros oficiales del Estado y busca por ti: quién es la empresa, qué contratos públicos ha recibido, de qué entidades y por cuánta plata. Con eso arma un informe donde cada dato dice de dónde salió, con el enlace para que lo compruebes tú mismo.";

const TEXTAREA_LABEL = "Pregunta de investigación";

const TEXTAREA_PLACEHOLDER = "Ej.: Quiero saber por qué esta empresa recibe tantos contratos del Distrito de Cali.";

const INTENTS_TITLE = "¿No sabes por dónde empezar?";

// En modo real los intents cargan preguntas reales y útiles (empresa con datos
// públicos verificados); las ficticias solo existen en modo mock/fixtures y
// conservan los ejemplos actuales con esta misma presentación.
const INTENTS: { icon: LucideIcon; title: string; question: string }[] = USE_MOCK
  ? [
      {
        icon: Building2,
        title: "Investigar una empresa",
        question: "¿Qué contratos públicos tiene Distribuidora Andina?",
      },
      {
        icon: FileText,
        title: "Entender sus contratos",
        question:
          "¿Por qué Empresa Ejemplo S.A.S. concentra tantos contratos con la Entidad Ficticia de Ejemplo?",
      },
      {
        icon: UserSearch,
        title: "Seguir una relación",
        question: "¿Cómo ha crecido el valor contratado por Empresa Ejemplo S.A.S. desde 2022?",
      },
    ]
  : [
      {
        icon: Building2,
        title: "Investigar una empresa",
        question: "¿Qué contratos públicos ha recibido la empresa con NIT 901145160?",
      },
      {
        icon: FileText,
        title: "Entender sus contratos",
        question: "¿En qué entidades se concentra la contratación de la empresa con NIT 901145160? Investiga y documenta.",
      },
      {
        icon: UserSearch,
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
      <p className="ask-explainer">{INVITE_EXPLAINER}</p>

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
          {INTENTS.map(({ icon: Icon, title, question: intentQuestion }) => (
            <li key={title}>
              {/* Carga la pregunta en el textarea, NUNCA dispara la investigación:
                  cada investigación real consume cupo de rate limit y tokens. */}
              <button
                type="button"
                className="intent-chip"
                onClick={() => setQuestion(intentQuestion)}
              >
                <span className="intent-icon" aria-hidden="true">
                  <Icon size={18} strokeWidth={1.9} />
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
