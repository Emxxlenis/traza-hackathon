/**
 * TypeScript mirror of contract v0 — Case File (expediente).
 * Source of truth: docs/contracts/case-file.v0.md
 *
 * The contract is PROVISIONAL. Do not change shapes here unilaterally:
 * any mismatch with the UI's needs must be reported to the orchestrator
 * as a proposal, never edited into the contract.
 */

/** Expediente status. `partial` means a source failed and the case file degrades gracefully. */
export type CaseStatus = "complete" | "needs_disambiguation" | "partial";

/**
 * Status of a consulted source. The contract only shows "ok"; "error" is the
 * assumed value for failed sources backing `status: "partial"` (flagged to the
 * orchestrator as a question on the contract).
 */
export type SourceStatus = "ok" | "error";

/** An entity involved in the investigation (all fixture entities are fictitious). */
export interface Entity {
  /** e.g. "co:nit:900000001" or "co:entidad:ENT-001" — final form pending real captures. */
  id: string;
  name: string;
  /** e.g. "investigada", "contratante". */
  role: string;
}

/** A source that was consulted while building the case file. */
export interface SourceConsulted {
  /** e.g. "croma:rues:entity-by-nit". */
  source: string;
  /** ISO 8601 timestamp of the consultation. */
  at: string;
  status: SourceStatus;
}

/** Evidence stated directly by an official source ("HECHO" in the UI). */
export interface DirectEvidence {
  claim: string;
  type: "direct";
  /** Source identifier, e.g. "croma:rues:entity-by-nit". */
  source: string;
  /** Exact id/field of the source response — final form pending real captures. */
  raw_reference: string;
}

/** Evidence calculated from sources, with a visible calculation chain ("INFERENCIA" in the UI). */
/** One mechanically re-executable step of a derived calculation (contract v0.1). */
export interface CalculationStep {
  /** Closed registry: "sum" | "subtract" | "multiply" | "divide" | "round". */
  operation: string;
  /** Numeric literals or "$k" references to a previous step's output. */
  inputs: (number | string)[];
  output: number;
}

export interface DerivedEvidence {
  claim: string;
  type: "derived";
  /** Human-readable calculation chain, e.g. "12 / 17". */
  calculation: string;
  /** Structured, re-executable chain (contract v0.1). Optional until backend integration. */
  calculation_steps?: CalculationStep[];
  /** Source identifiers backing the calculation. */
  sources: string[];
}

export type Evidence = DirectEvidence | DerivedEvidence;

/**
 * A finding. Everything asserted in `narrative` must be backed by the
 * objects in `evidence[]` — never free paraphrase without an object behind it.
 */
export interface Finding {
  id: string;
  title: string;
  narrative: string;
  evidence: Evidence[];
}

/**
 * A candidate entity offered when `status === "needs_disambiguation"`.
 * The contract says candidates are "a list of possible entities" but does not
 * pin the shape; `detail` is a UI-side optional hint (proposed to the
 * orchestrator as a contract addition, not contract-mandated).
 */
export interface Candidate {
  id: string;
  name: string;
  /** Short distinguishing text (e.g. NIT, city, registry status). Fixed in contract v0.1. */
  detail?: string;
}

/** The full case file (expediente) returned by the backend. */
export interface CaseFile {
  question: string;
  status: CaseStatus;
  entities: Entity[];
  sources_consulted: SourceConsulted[];
  /** Empty when `status === "needs_disambiguation"` (candidates replace findings). */
  findings: Finding[];
  /** Present instead of findings when `status === "needs_disambiguation"`. */
  candidates?: Candidate[];
  /** "Qué no sabemos" — always part of a complete/partial expediente. */
  unknowns: string[];
  /** "Siguientes pasos" — always part of a complete/partial expediente. */
  next_steps: string[];
}
