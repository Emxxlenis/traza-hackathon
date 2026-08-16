import { useRef, useState } from "react";
import { Check, Loader2 } from "lucide-react";
import type { CaseFile } from "./types/caseFile";
import {
  api,
  investigateStream,
  isStreamFallback,
  USE_MOCK,
  type StreamProgressEvent,
} from "./api/client";
import { sourceLabel } from "./lib/plainLanguage";
import { TestDataBanner } from "./components/TestDataBanner";
import { QuestionInput } from "./components/QuestionInput";
import { DisambiguationView } from "./components/DisambiguationView";
import { CaseFileView } from "./components/CaseFileView";

/** Un paso real recibido por streaming (una consulta a fuente del agente). */
interface LiveStep {
  step: number;
  source: string;
  status: "start" | "ok" | "error";
}

type View =
  | { screen: "ask" }
  | { screen: "loading"; message: string }
  | { screen: "live"; question: string; steps: LiveStep[]; assembling: boolean }
  | { screen: "disambiguation"; caseFile: CaseFile }
  | { screen: "case"; caseFile: CaseFile }
  | { screen: "error"; message: string; retry: () => void };

/** Espejo de LoopConfig.max_steps del backend: el límite REAL de consultas
 * a fuentes por investigación. Nunca inventamos un total menor. */
const MAX_STEPS = 8;

/** Muestra el mensaje del backend cuando es legible (p. ej. límite de cuota con
 * minutos de espera); cae al texto genérico ante errores técnicos de red. */
function friendlyError(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message && !/fetch|network|load failed/i.test(err.message)) {
    return err.message;
  }
  return fallback;
}

/** Aplica un evento de progreso del stream al estado de la vista en vivo. */
function applyProgress(view: View, event: StreamProgressEvent): View {
  if (view.screen !== "live") return view;
  if (event.type === "phase") {
    return { ...view, assembling: true };
  }
  const existing = view.steps.some((s) => s.step === event.step);
  const steps = existing
    ? view.steps.map((s) =>
        s.step === event.step ? { ...s, source: event.source, status: event.status } : s,
      )
    : [...view.steps, { step: event.step, source: event.source, status: event.status }];
  return { ...view, steps };
}

export default function App() {
  const [view, setView] = useState<View>({ screen: "ask" });
  // Pregunta de la investigación activa: necesaria para reanudar por streaming
  // tras la desambiguación (la vista solo entrega el candidate_id).
  const questionRef = useRef<string | null>(null);

  function showCase(caseFile: CaseFile) {
    if (caseFile.status === "needs_disambiguation") {
      setView({ screen: "disambiguation", caseFile });
    } else {
      setView({ screen: "case", caseFile });
    }
  }

  function handleProgress(event: StreamProgressEvent) {
    setView((prev) => applyProgress(prev, event));
  }

  /** Camino clásico (POST /investigate): también es el fallback del streaming. */
  function runClassicInvestigation(question: string) {
    setView({ screen: "loading", message: "Consultando fuentes oficiales…" });
    api
      .investigate(question)
      .then(showCase)
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

  function runInvestigation(question: string) {
    questionRef.current = question;
    if (USE_MOCK) {
      // En modo mock no hay streaming: el mock actual tal cual.
      runClassicInvestigation(question);
      return;
    }
    setView({ screen: "live", question, steps: [], assembling: false });
    investigateStream(question, undefined, handleProgress)
      .then(showCase)
      .catch((err: unknown) => {
        if (isStreamFallback(err)) {
          // El streaming cayó: mismo resultado por el POST clásico; el usuario
          // solo pierde el progreso en vivo.
          runClassicInvestigation(question);
          return;
        }
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

  function runClassicResolve(candidateId: string) {
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

  function resolveCandidate(candidateId: string) {
    const question = questionRef.current;
    if (USE_MOCK || question === null) {
      runClassicResolve(candidateId);
      return;
    }
    setView({ screen: "live", question, steps: [], assembling: false });
    investigateStream(question, candidateId, handleProgress)
      .then((caseFile) => setView({ screen: "case", caseFile }))
      .catch((err: unknown) => {
        if (isStreamFallback(err)) {
          runClassicResolve(candidateId);
          return;
        }
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

  const liveCurrentStep =
    view.screen === "live" && view.steps.length > 0
      ? Math.max(...view.steps.map((s) => s.step))
      : 0;

  return (
    <div className="app">
      <TestDataBanner />
      <header className="app-header">
        <h1 className="app-title">TRAZA</h1>
        <p className="app-tagline">Tú traes la pregunta. TRAZA hace la investigación.</p>
      </header>

      <main className="app-main">
        {view.screen === "ask" && <QuestionInput onSubmit={runInvestigation} />}

        {/* Fallback (comportamiento de hoy): spinner clásico con sus textos. */}
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

        {/* Progreso EN VIVO: solo eventos reales recibidos por streaming. */}
        {view.screen === "live" && (
          <div className="live-loading" role="status" aria-live="polite">
            <h2 className="live-title">TRAZA está investigando</h2>
            <p className="live-question">{view.question}</p>

            <ul className="live-steps">
              {view.steps.length === 0 && !view.assembling && (
                <li className="live-step">
                  <Loader2 size={16} className="live-icon live-icon-active live-spin" aria-hidden="true" />
                  <span className="live-step-label">Iniciando la investigación…</span>
                </li>
              )}
              {view.steps.map((s) => {
                const { label } = sourceLabel(s.source);
                return (
                  <li key={s.step} className="live-step">
                    {s.status === "start" ? (
                      <Loader2 size={16} className="live-icon live-icon-active live-spin" aria-hidden="true" />
                    ) : (
                      <Check
                        size={16}
                        className={`live-icon ${s.status === "ok" ? "live-icon-done" : "live-icon-muted"}`}
                        aria-hidden="true"
                      />
                    )}
                    <span className="live-step-label">{label}</span>
                    <span className={`live-step-state${s.status === "error" ? " is-muted" : ""}`}>
                      {s.status === "start"
                        ? "consultando…"
                        : s.status === "ok"
                          ? "respondió"
                          : "no respondió"}
                    </span>
                  </li>
                );
              })}
              {view.assembling && (
                <li className="live-step">
                  <Loader2 size={16} className="live-icon live-icon-active live-spin" aria-hidden="true" />
                  <span className="live-step-label">Construyendo expediente…</span>
                </li>
              )}
            </ul>

            {liveCurrentStep > 0 && (
              <p className="live-counter">
                Paso {liveCurrentStep} de máximo {MAX_STEPS}
              </p>
            )}
            <p className="live-note">
              TRAZA no sigue una ruta fija. Decide qué consultar según lo que encuentra.
            </p>
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
