import type { CaseFile } from "../types/caseFile";
import { buildResolvedCase, completeCase, disambiguationCase } from "../fixtures";

/**
 * Backend contract for the UI. Components depend ONLY on this interface —
 * the mock and the real FastAPI backend are interchangeable implementations
 * selected below by environment. No component changes.
 */
export interface TrazaApi {
  /** POST /investigate — turns a natural-language question into a case file. */
  investigate(question: string): Promise<CaseFile>;
  /** Continues an investigation after the user picks a disambiguation candidate. */
  resolveDisambiguation(candidateId: string): Promise<CaseFile>;
}

/**
 * `VITE_USE_MOCK === '1'` → fixtures (demo mode, test-data banner visible).
 * Default → real backend over HTTP.
 */
export const USE_MOCK = import.meta.env.VITE_USE_MOCK === "1";

const MOCK_DELAY_MS = 900;

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Mock implementation backed by fixtures. Heuristics (mock-only, for demo):
 * - Questions mentioning "Distribuidora Andina" hit the ambiguous-name path.
 * - Questions starting with "!error" simulate a backend failure (to demo
 *   graceful degradation).
 * - Anything else returns the complete fixture case.
 */
const mockApi: TrazaApi = {
  async investigate(question: string): Promise<CaseFile> {
    await delay(MOCK_DELAY_MS);
    if (question.trim().toLowerCase().startsWith("!error")) {
      throw new Error("Simulated backend failure");
    }
    if (question.toLowerCase().includes("distribuidora andina")) {
      return { ...disambiguationCase, question };
    }
    return { ...completeCase, question };
  },

  async resolveDisambiguation(candidateId: string): Promise<CaseFile> {
    await delay(MOCK_DELAY_MS);
    const candidate = disambiguationCase.candidates?.find((c) => c.id === candidateId);
    if (!candidate) {
      throw new Error(`Unknown candidate: ${candidateId}`);
    }
    return buildResolvedCase(candidate);
  },
};

/* ------------------------------------------------------------------------ */
/* Real implementation: FastAPI backend, POST /investigate (contract v0.1).  */
/* ------------------------------------------------------------------------ */

const API_URL: string = import.meta.env.VITE_API_URL || "http://localhost:8000";

/** Real investigations take 60–100s; give the backend ample room before giving up. */
const REQUEST_TIMEOUT_MS = 180_000;

interface InvestigateRequestBody {
  question: string;
  candidate_id?: string;
}

async function postInvestigate(body: InvestigateRequestBody): Promise<CaseFile> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_URL}/investigate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!res.ok) {
      throw new Error(`Backend respondió HTTP ${res.status}`);
    }
    return (await res.json()) as CaseFile;
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error(`La investigación superó el tiempo máximo (${REQUEST_TIMEOUT_MS / 1000}s)`);
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Disambiguation travels through the same endpoint: the client re-sends the
 * SAME question plus the chosen `candidate_id`. The question is kept here as
 * client-side state because the UI's disambiguation flow only hands us the
 * candidate id.
 */
let lastQuestion: string | null = null;

const httpApi: TrazaApi = {
  async investigate(question: string): Promise<CaseFile> {
    lastQuestion = question;
    return postInvestigate({ question });
  },

  async resolveDisambiguation(candidateId: string): Promise<CaseFile> {
    if (lastQuestion === null) {
      throw new Error("No hay una pregunta activa para continuar la investigación");
    }
    return postInvestigate({ question: lastQuestion, candidate_id: candidateId });
  },
};

/** Single swap point, driven by environment (see USE_MOCK above). */
export const api: TrazaApi = USE_MOCK ? mockApi : httpApi;
