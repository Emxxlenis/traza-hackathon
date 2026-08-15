import type { CaseFile } from "../types/caseFile";

interface DisambiguationViewProps {
  caseFile: CaseFile;
  onSelect: (candidateId: string) => void;
  onCancel: () => void;
}

/** Screen (b): shown when status === "needs_disambiguation". Picking a candidate continues the investigation. */
export function DisambiguationView({ caseFile, onSelect, onCancel }: DisambiguationViewProps) {
  const candidates = caseFile.candidates ?? [];

  return (
    <section className="disambiguation">
      <p className="case-question-label">Tu pregunta</p>
      <h2 className="case-question">{caseFile.question}</h2>

      <p className="disambiguation-intro">
        Encontramos {candidates.length} entidades con nombres similares. Elige a cuál te refieres
        para continuar la investigación:
      </p>

      <ul className="candidate-list">
        {candidates.map((candidate) => (
          <li key={candidate.id}>
            <button type="button" className="candidate-card" onClick={() => onSelect(candidate.id)}>
              <span className="candidate-name">{candidate.name}</span>
              {candidate.detail && <span className="candidate-detail">{candidate.detail}</span>}
            </button>
          </li>
        ))}
      </ul>

      <button type="button" className="btn-secondary" onClick={onCancel}>
        Cambiar la pregunta
      </button>
    </section>
  );
}
