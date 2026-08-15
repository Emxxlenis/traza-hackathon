import { useState } from "react";
import type { CaseFile } from "./types/caseFile";
import { api } from "./api/client";
import { TestDataBanner } from "./components/TestDataBanner";
import { QuestionInput } from "./components/QuestionInput";
import { DisambiguationView } from "./components/DisambiguationView";
import { CaseFileView } from "./components/CaseFileView";

type View =
  | { screen: "ask" }
  | { screen: "loading"; message: string }
  | { screen: "disambiguation"; caseFile: CaseFile }
  | { screen: "case"; caseFile: CaseFile }
  | { screen: "error"; message: string; retry: () => void };

export default function App() {
  const [view, setView] = useState<View>({ screen: "ask" });

  function runInvestigation(question: string) {
    setView({ screen: "loading", message: "Consultando fuentes oficiales…" });
    api
      .investigate(question)
      .then((caseFile) => {
        if (caseFile.status === "needs_disambiguation") {
          setView({ screen: "disambiguation", caseFile });
        } else {
          setView({ screen: "case", caseFile });
        }
      })
      .catch(() => {
        setView({
          screen: "error",
          message:
            "No pudimos completar la investigación en este momento. Tu pregunta no se perdió: puedes reintentar.",
          retry: () => runInvestigation(question),
        });
      });
  }

  function resolveCandidate(candidateId: string) {
    setView({ screen: "loading", message: "Continuando la investigación con la entidad elegida…" });
    api
      .resolveDisambiguation(candidateId)
      .then((caseFile) => setView({ screen: "case", caseFile }))
      .catch(() => {
        setView({
          screen: "error",
          message: "No pudimos continuar la investigación con esa entidad. Puedes reintentar.",
          retry: () => resolveCandidate(candidateId),
        });
      });
  }

  return (
    <div className="app">
      <TestDataBanner />
      <header className="app-header">
        <h1 className="app-title">TRAZA</h1>
        <p className="app-tagline">
          Expedientes de investigación sobre contratación pública, con la evidencia a la vista.
        </p>
      </header>

      <main className="app-main">
        {view.screen === "ask" && <QuestionInput onSubmit={runInvestigation} />}

        {view.screen === "loading" && (
          <div className="loading" role="status">
            <div className="loading-dots" aria-hidden="true">
              <span /><span /><span />
            </div>
            <p>{view.message}</p>
          </div>
        )}

        {view.screen === "disambiguation" && (
          <DisambiguationView
            caseFile={view.caseFile}
            onSelect={resolveCandidate}
            onCancel={() => setView({ screen: "ask" })}
          />
        )}

        {view.screen === "case" && (
          <CaseFileView caseFile={view.caseFile} onNewInvestigation={() => setView({ screen: "ask" })} />
        )}

        {view.screen === "error" && (
          <div className="error-card" role="alert">
            <h2>Algo no salió bien</h2>
            <p>{view.message}</p>
            <div className="error-actions">
              <button type="button" className="btn-primary" onClick={view.retry}>
                Reintentar
              </button>
              <button type="button" className="btn-secondary" onClick={() => setView({ screen: "ask" })}>
                Empezar de nuevo
              </button>
            </div>
          </div>
        )}
      </main>

      <footer className="app-footer">
        Interfaz de demostración construida sobre fixtures — pendiente de integrar contra datos
        reales de Croma. TRAZA muestra evidencia; no emite veredictos ni puntajes de riesgo.
      </footer>
    </div>
  );
}
