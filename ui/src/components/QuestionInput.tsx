import { useState } from "react";
import { USE_MOCK } from "../api/client";
import { LandingIntro } from "./LandingIntro";

// En modo real los ejemplos son preguntas reales y útiles (empresas con datos
// públicos verificados); las ficticias solo existen en modo mock/fixtures.
const EXAMPLE_QUESTIONS = USE_MOCK
  ? [
      "¿Por qué Empresa Ejemplo S.A.S. concentra tantos contratos con la Entidad Ficticia de Ejemplo?",
      "¿Qué contratos públicos tiene Distribuidora Andina?",
      "¿Cómo ha crecido el valor contratado por Empresa Ejemplo S.A.S. desde 2022?",
    ]
  : [
      "¿Por qué la empresa con NIT 901145160 concentra sus contratos públicos en el Distrito de Cali? Investiga y documenta.",
      "¿Qué contratos públicos tiene la empresa con NIT 899999068 y en qué entidades se concentran?",
      "Investiga la contratación pública de la empresa Distribuidora Andina",
    ];

const EXAMPLES_LABEL = USE_MOCK
  ? "Ejemplos (con entidades ficticias):"
  : "Ejemplos — haz clic para cargar la pregunta y revísala antes de investigar:";

interface QuestionInputProps {
  onSubmit: (question: string) => void;
}

/** Screen (a): natural-language question input with clickable examples. */
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
      <LandingIntro />

      <h2 className="ask-heading">Convierte una pregunta en un expediente de investigación</h2>
      <p className="ask-sub">
        Escribe una pregunta sobre una empresa colombiana y contratación pública. TRAZA consulta
        fuentes oficiales y arma un expediente con la evidencia de cada hallazgo.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <textarea
          className="ask-textarea"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="¿Qué quieres investigar?"
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

      <div className="examples">
        <p className="examples-label">{EXAMPLES_LABEL}</p>
        <ul className="examples-list">
          {EXAMPLE_QUESTIONS.map((example) => (
            <li key={example}>
              {/* Carga la pregunta en el textarea, NUNCA dispara la investigación:
                  cada investigación real consume cupo de rate limit y tokens. */}
              <button
                type="button"
                className="example-chip"
                onClick={() => setQuestion(example)}
              >
                {example}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
