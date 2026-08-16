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

// "??" y no "||": VITE_API_URL="" es válido y significa mismo origen (producción single-origin).
const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

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
      // El backend responde {detail} legible (p. ej. límite de investigaciones por hora).
      let detail = "";
      try {
        detail = ((await res.json()) as { detail?: string }).detail ?? "";
      } catch {
        /* cuerpo no-JSON: mensaje genérico */
      }
      throw new Error(detail || `Backend respondió HTTP ${res.status}`);
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

/* ------------------------------------------------------------------------ */
/* Streaming: POST /investigate/stream (NDJSON de progreso EN VIVO).         */
/* El POST clásico de arriba queda intacto como fallback.                    */
/* ------------------------------------------------------------------------ */

/** Un paso REAL del loop del agente (consulta a una fuente oficial). */
export interface StreamStepEvent {
  type: "step";
  /** Id técnico de la fuente, p. ej. "croma:rues:entity-by-nit". */
  source: string;
  /** start = consultando; ok = respondió; error = no respondió. */
  status: "start" | "ok" | "error";
  /** Número de paso real (contador de max_steps del backend). */
  step: number;
}

/** Fase no-consulta del loop (hoy: "Construyendo expediente"). */
export interface StreamPhaseEvent {
  type: "phase";
  label: string;
}

export type StreamProgressEvent = StreamStepEvent | StreamPhaseEvent;

/**
 * Fallo del TRANSPORTE del streaming (fetch, red, parse, timeout, backend sin
 * el endpoint). Marcado como recuperable: el caller debe caer al POST clásico
 * — el usuario solo pierde el progreso en vivo, nunca la investigación.
 * Un {"type":"error"} del backend NO es de esta clase: ahí la investigación
 * misma falló y reintentarla por el canal clásico no la salvaría.
 */
export class StreamFallbackError extends Error {
  readonly recoverable = true as const;

  constructor(message: string) {
    super(message);
    this.name = "StreamFallbackError";
  }
}

export function isStreamFallback(err: unknown): err is StreamFallbackError {
  return err instanceof StreamFallbackError;
}

interface StreamResultLine {
  type: "result";
  case_file: CaseFile;
}

interface StreamErrorLine {
  type: "error";
  detail?: string;
}

type StreamLine =
  | StreamProgressEvent
  | StreamResultLine
  | StreamErrorLine
  | { type: "ping" };

/**
 * Investiga por streaming: resuelve con el MISMO CaseFile del contrato v0.1 e
 * invoca `onProgress` con cada evento real recibido. Cualquier fallo del
 * transporte lanza StreamFallbackError (ver arriba). No usar en modo mock.
 */
export async function investigateStream(
  question: string,
  candidateId: string | undefined,
  onProgress: (event: StreamProgressEvent) => void,
): Promise<CaseFile> {
  // Mantiene el estado del flujo de desambiguación compartido con el fallback
  // clásico (api.resolveDisambiguation reutiliza la misma pregunta).
  lastQuestion = question;

  const body: InvestigateRequestBody = { question };
  if (candidateId) body.candidate_id = candidateId;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let res: Response;
  try {
    res = await fetch(`${API_URL}/investigate/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(timeoutId);
    throw new StreamFallbackError(
      err instanceof DOMException && err.name === "AbortError"
        ? `El streaming superó el tiempo máximo (${REQUEST_TIMEOUT_MS / 1000}s)`
        : "No se pudo abrir el canal de streaming",
    );
  }

  try {
    // CUALQUIER estado no-ok (404 sin endpoint, 429, 5xx de proxy...) cae al
    // POST clásico, que ya sabe producir el mensaje legible correspondiente.
    if (!res.ok || !res.body) {
      throw new StreamFallbackError(`El backend de streaming respondió HTTP ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    const handleLine = (line: string): CaseFile | null => {
      const trimmed = line.trim();
      if (!trimmed) return null;
      let event: StreamLine;
      try {
        event = JSON.parse(trimmed) as StreamLine;
      } catch {
        throw new StreamFallbackError("Línea NDJSON no parseable en el stream");
      }
      switch (event.type) {
        case "step":
        case "phase":
          onProgress(event);
          return null;
        case "ping":
          return null; // keep-alive para proxies; no es progreso
        case "result":
          if (!event.case_file) {
            throw new StreamFallbackError("El stream cerró con un result sin case_file");
          }
          return event.case_file;
        case "error":
          // La INVESTIGACIÓN falló (no el transporte): error normal, sin fallback.
          throw new Error(
            event.detail || "No pudimos completar la investigación en este momento.",
          );
        default:
          return null; // evento desconocido de un backend más nuevo: se ignora
      }
    };

    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let newlineIndex = buffer.indexOf("\n");
        while (newlineIndex !== -1) {
          const line = buffer.slice(0, newlineIndex);
          buffer = buffer.slice(newlineIndex + 1);
          const caseFile = handleLine(line);
          if (caseFile) {
            reader.cancel().catch(() => undefined);
            return caseFile;
          }
          newlineIndex = buffer.indexOf("\n");
        }
      }
      // Última línea sin salto final, por si el backend cerrara sin "\n".
      const caseFile = handleLine(buffer + decoder.decode());
      if (caseFile) return caseFile;
    } catch (err) {
      if (err instanceof StreamFallbackError) throw err;
      if (err instanceof DOMException && err.name === "AbortError") {
        throw new StreamFallbackError(
          `El streaming superó el tiempo máximo (${REQUEST_TIMEOUT_MS / 1000}s)`,
        );
      }
      // Fallos de red/lectura (TypeError y afines) son de transporte → fallback.
      if (err instanceof TypeError || err instanceof DOMException) {
        throw new StreamFallbackError("Fallo de red leyendo el stream");
      }
      // Queda el error deliberado de investigación ({"type":"error"}): normal.
      if (err instanceof Error) throw err;
      throw new StreamFallbackError("Fallo desconocido leyendo el stream");
    }

    // El stream terminó sin línea result ni error: transporte roto.
    throw new StreamFallbackError("El stream terminó sin resultado");
  } finally {
    clearTimeout(timeoutId);
  }
}
