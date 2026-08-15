import type { CaseFile } from "../types/caseFile";
import { buildResolvedCase, completeCase, disambiguationCase } from "../fixtures";

/**
 * Backend contract for the UI. Components depend ONLY on this interface —
 * swapping the mock for the real FastAPI backend means providing another
 * implementation below and changing the `api` export. No component changes.
 */
export interface TrazaApi {
  /** POST /investigate — turns a natural-language question into a case file. */
  investigate(question: string): Promise<CaseFile>;
  /** Continues an investigation after the user picks a disambiguation candidate. */
  resolveDisambiguation(candidateId: string): Promise<CaseFile>;
}

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

/*
 * Real implementation sketch (enable when the FastAPI backend exists):
 *
 * const httpApi: TrazaApi = {
 *   async investigate(question) {
 *     const res = await fetch(`${import.meta.env.VITE_API_URL}/investigate`, {
 *       method: "POST",
 *       headers: { "Content-Type": "application/json" },
 *       body: JSON.stringify({ question }),
 *     });
 *     if (!res.ok) throw new Error(`HTTP ${res.status}`);
 *     return (await res.json()) as CaseFile;
 *   },
 *   async resolveDisambiguation(candidateId) { ... },
 * };
 */

/** Single swap point: change this export to move off fixtures. */
export const api: TrazaApi = mockApi;
