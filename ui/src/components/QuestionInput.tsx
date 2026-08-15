import { useState } from "react";

const EXAMPLE_QUESTIONS = [
  "¿Por qué Empresa Ejemplo S.A.S. concentra tantos contratos con la Entidad Ficticia de Ejemplo?",
  "¿Qué contratos públicos tiene Distribuidora Andina?",
  "¿Cómo ha crecido el valor contratado por Empresa Ejemplo S.A.S. desde 2022?",
];

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
        <p className="examples-label">Ejemplos (con entidades ficticias):</p>
        <ul className="examples-list">
          {EXAMPLE_QUESTIONS.map((example) => (
            <li key={example}>
              <button type="button" className="example-chip" onClick={() => onSubmit(example)}>
                {example}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
