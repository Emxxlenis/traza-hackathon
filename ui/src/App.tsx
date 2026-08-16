import { useState } from "react";
import type { CaseFile } from "./types/caseFile";
import { api, USE_MOCK } from "./api/client";
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

/** Muestra el mensaje del backend cuando es legible (p. ej. límite de cuota con
 * minutos de espera); cae al texto genérico ante errores técnicos de red. */
function friendlyError(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message && !/fetch|network|load failed/i.test(err.message)) {
    return err.message;
  }
  return fallback;
}

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
      .catch((err: unknown) => {
        setView({
          screen: "error",
          message: friendlyError(
            err,
            "No pudimos completar la investigación en este momento. Tu pregunta no se perdió: puedes reintentar.",
          ),
          retry: () => runInvestigation(question),
        });
      });
  }

  function resolveCandidate(candidateId: string) {
    setView({ screen: "loading", message: "Continuando la investigación con la entidad elegida…" });
    api
      .resolveDisambiguation(candidateId)
      .then((caseFile) => setView({ screen: "case", caseFile }))
      .catch((err: unknown) => {
        setView({
          screen: "error",
          message: friendlyError(
            err,
            "No pudimos continuar la investigación con esa entidad. Puedes reintentar.",
          ),
          retry: () => resolveCandidate(candidateId),
        });
      });
  }

  return (
    <div className="app">
      <TestDataBanner />
      <header className="app-header">
        <h1 className="app-title">TRAZA</h1>
        <p className="app-tagline">Tú traes la pregunta. TRAZA hace la investigación.</p>
      </header>

      <main className="app-main">
        {view.screen === "ask" && <QuestionInput onSubmit={runInvestigation} />}

        {view.screen === "loading" && (
          <div className="loading" role="status" aria-live="polite">
            <div className="loading-dots" aria-hidden="true">
              <span /><span /><span />
            </div>
            <p>{view.message}</p>
            {/* COPY CONGELADO (verbatim del brief): línea de expectativa de tiempo. */}
            <p className="loading-time">Investigación en curso · normalmente tarda menos de 2 minutos.</p>
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
        {USE_MOCK
          ? "Interfaz de demostración construida sobre fixtures — pendiente de integrar contra datos reales de Croma. "
          : "Datos: fuentes oficiales vía Croma. "}
        TRAZA muestra evidencia; no emite veredictos ni puntajes de riesgo.
      </footer>
    </div>
  );
}
