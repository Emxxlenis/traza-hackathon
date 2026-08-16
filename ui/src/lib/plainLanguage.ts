/**
 * Plain-language layer: pure helpers that translate the structured parts of a
 * CaseFile (contract v0.1) into short, neutral, descriptive es-CO sentences.
 *
 * These helpers rely ONLY on the structural patterns the backend reducers
 * always emit (never on fragile regexes over free text):
 * - Percentage chain: [...optional sum steps...] → divide(a, b) →
 *   multiply("$k", 100) → round("$k", 1). The claim contains "%" plus
 *   "contratos" (share by count) or "valor" (share by value).
 * - Sum chain: a single sum([...]) → total (amounts in pesos).
 *
 * Tone is non-negotiable: descriptive, never accusatory.
 */

import type { CalculationStep, CaseFile, DerivedEvidence, Entity } from "../types/caseFile";

/* ------------------------------------------------------------------ */
/* Formatting (es-CO: "." thousands, "," decimals)                     */
/* ------------------------------------------------------------------ */

const amountFormatter = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 });

function formatAmount(n: number): string {
  return amountFormatter.format(n);
}

/** "79" → "79,0" — one decimal, comma separator. */
function formatPct(n: number): string {
  return n.toFixed(1).replace(".", ",");
}

/* ------------------------------------------------------------------ */
/* Structural helpers over calculation_steps                           */
/* ------------------------------------------------------------------ */

/** Resolves a step input: numeric literal, or "$k" reference to steps[k].output. */
function resolveInput(input: number | string, steps: CalculationStep[]): number | null {
  if (typeof input === "number") return input;
  const ref = /^\$(\d+)$/.exec(input);
  if (!ref) return null;
  const step = steps[Number(ref[1])];
  return step ? step.output : null;
}

interface PercentageChain {
  /** Numerator of the dividing step (already resolved). */
  a: number;
  /** Denominator of the dividing step (already resolved). */
  b: number;
  /** Final rounded percentage (output of the round step). */
  pct: number;
}

/**
 * Matches the reducer percentage pattern: any number of leading `sum` steps,
 * then divide → multiply(·, 100) → round. Anything else (e.g. a growth
 * calculation with `subtract`) is NOT a percentage share and returns null.
 */
function matchPercentageChain(steps: CalculationStep[] | undefined): PercentageChain | null {
  if (!steps || steps.length < 3) return null;
  const n = steps.length;
  const divide = steps[n - 3];
  const multiply = steps[n - 2];
  const round = steps[n - 1];
  if (divide.operation !== "divide" || multiply.operation !== "multiply" || round.operation !== "round") {
    return null;
  }
  // Leading steps (if any) may only be sums feeding the division.
  for (let i = 0; i < n - 3; i++) {
    if (steps[i].operation !== "sum") return null;
  }
  // multiply must scale the divide output by 100; round must take the multiply output.
  if (!multiply.inputs.includes(`$${n - 3}`) || !multiply.inputs.includes(100)) return null;
  if (round.inputs[0] !== `$${n - 2}`) return null;

  const a = resolveInput(divide.inputs[0], steps);
  const b = resolveInput(divide.inputs[1], steps);
  if (a === null || b === null) return null;
  return { a, b, pct: round.output };
}

type PercentageKind = "value" | "count";

interface ClassifiedPercentage {
  chain: PercentageChain;
  kind: PercentageKind;
}

/**
 * Classifies a percentage chain as share-by-value or share-by-count.
 * Structure first (value chains carry leading `sum` steps over peso amounts;
 * count chains are the pure 3-step divide of two literal counts); the claim
 * keywords "contratos"/"valor" only break the tie for pure 3-step chains.
 * Word order matters below: a count claim may mention "valor" incidentally
 * ("la mayor por valor..."), so "contratos" wins for pure count-shaped chains.
 */
function classifyPercentage(ev: DerivedEvidence): ClassifiedPercentage | null {
  const steps = ev.calculation_steps;
  const chain = matchPercentageChain(steps);
  if (!chain || !steps) return null;
  if (steps.length > 3) return { chain, kind: "value" }; // leading sums ⇒ summed peso amounts
  if (ev.claim.includes("contratos")) return { chain, kind: "count" };
  if (ev.claim.includes("valor")) return { chain, kind: "value" };
  return null; // percentage of an unknown unit — leave untranslated
}

function finalOutput(ev: DerivedEvidence): number {
  const steps = ev.calculation_steps;
  return steps && steps.length > 0 ? steps[steps.length - 1].output : Number.NEGATIVE_INFINITY;
}

function endsInRound(ev: DerivedEvidence): boolean {
  const steps = ev.calculation_steps;
  return !!steps && steps.length > 0 && steps[steps.length - 1].operation === "round";
}

/* ------------------------------------------------------------------ */
/* 1. Plain summary of the whole case file                             */
/* ------------------------------------------------------------------ */

const collapseSpaces = (s: string) => s.replace(/\s+/g, " ").trim();

/**
 * Defensive rewrite for counterpart names emitted by older backends, where a
 * shared-NIT group without a common name prefix was labeled
 * "NIT <nit> (N dependencias)". Rewritten as prose ("la entidad con NIT n,
 * que agrupa k dependencias bajo un mismo NIT") so the summary sentence never
 * repeats the same identifier twice. Current backends never produce such
 * names (the label falls back to the top dependency's name instead).
 */
function readableCounterpartName(name: string): string {
  const nit = /^NIT (\d+)/.exec(name.trim());
  if (!nit) return name;
  const deps = /\((\d+) dependencias?\)/.exec(name);
  const base = `la entidad con NIT ${nit[1]}`;
  return deps ? `${base}, que agrupa ${deps[1]} dependencias bajo un mismo NIT` : base;
}

/** Structural match: the contratante whose name is INCLUDED in the claim text. */
function findContraparteInClaim(entities: Entity[], claim: string): Entity | null {
  const normalizedClaim = collapseSpaces(claim);
  for (const entity of entities) {
    if (entity.role !== "contratante") continue;
    if (claim.includes(entity.name)) return entity;
    if (normalizedClaim.includes(collapseSpaces(entity.name))) return entity;
  }
  return null;
}

/**
 * One-sentence plain-language summary of the case file, or null when the
 * expediente has no percentage-share evidence to summarize (empty or
 * disambiguation case files already communicate well on their own).
 */
export function plainSummary(caseFile: CaseFile): string | null {
  if (caseFile.status === "needs_disambiguation") return null;

  const candidates: DerivedEvidence[] = [];
  for (const finding of caseFile.findings) {
    for (const ev of finding.evidence) {
      if (ev.type === "derived" && endsInRound(ev)) candidates.push(ev);
    }
  }
  if (candidates.length === 0) return null;

  // Prefer the largest share by value; fall back to the largest share by count.
  const byValue = candidates.filter((ev) => ev.claim.includes("valor"));
  const pool = byValue.length > 0 ? byValue : candidates.filter((ev) => ev.claim.includes("contratos"));
  if (pool.length === 0) return null;
  const chosen = pool.reduce((best, ev) => (finalOutput(ev) > finalOutput(best) ? ev : best));

  const investigada = caseFile.entities.find((e) => e.role === "investigada") ?? null;
  const contraparte = findContraparteInClaim(caseFile.entities, chosen.claim);

  // Without an identifiable pair of parties, the claim itself is already readable.
  if (!investigada || !contraparte) return `En resumen: ${chosen.claim}`;

  const classified = classifyPercentage(chosen);
  if (!classified) return `En resumen: ${chosen.claim}`;

  const contraparteName = readableCounterpartName(contraparte.name);

  if (classified.kind === "value") {
    const pct = formatPct(classified.chain.pct);
    return `En resumen: de cada $100 que ${investigada.name} ha recibido en contratación pública, $${pct} provinieron de ${contraparteName}.`;
  }

  const { a, b } = classified.chain;
  return `En resumen: ${formatAmount(a)} de los ${formatAmount(b)} contratos públicos de ${investigada.name} fueron con ${contraparteName}.`;
}

/* ------------------------------------------------------------------ */
/* 2. Readable source names                                            */
/* ------------------------------------------------------------------ */

export interface SourceLabel {
  /** Human-readable name of the source. */
  label: string;
  /** The technical id, always preserved (shown as secondary text). */
  technical: string;
}

const SOURCE_LABELS: ReadonlyArray<readonly [string, string]> = [
  ["croma:rues:entity-by-nit", "RUES — Registro Único Empresarial (consulta por NIT)"],
  ["croma:rues:entities-by-name", "RUES — Registro Único Empresarial (búsqueda por nombre)"],
  ["croma:secop:contracts-by-provider", "SECOP — Contratos por proveedor"],
  ["croma:secop:processes-by-entity", "SECOP — Procesos por entidad contratante"],
  ["croma:procuraduria:disciplinary-records", "Procuraduría — Antecedentes disciplinarios"],
  ["croma:contraloria:fiscal-records", "Contraloría — Antecedentes fiscales"],
];

const CONTRACT_PREFIX = "croma:secop:contract:";

/** Maps a technical source id to a readable label; the id itself never disappears. */
export function sourceLabel(id: string): SourceLabel {
  for (const [prefix, label] of SOURCE_LABELS) {
    if (id === prefix || id.startsWith(`${prefix}:`)) return { label, technical: id };
  }
  if (id.startsWith(CONTRACT_PREFIX)) {
    return { label: `Contrato SECOP ${id.slice(CONTRACT_PREFIX.length)}`, technical: id };
  }
  return { label: id, technical: id };
}

/* ------------------------------------------------------------------ */
/* 3. Plain-language translation of a derived calculation              */
/* ------------------------------------------------------------------ */

/**
 * Translates a derived evidence's calculation chain into one plain sentence.
 * Only the two reducer patterns are translated; any other chain returns null
 * (the raw calculation and steps remain visible either way).
 */
export function plainCalculation(ev: DerivedEvidence): string | null {
  const steps = ev.calculation_steps;
  if (!steps || steps.length === 0) return null;

  if (steps.length === 1 && steps[0].operation === "sum") {
    return `Es decir: la suma de los ${steps[0].inputs.length} valores listados.`;
  }

  const classified = classifyPercentage(ev);
  if (classified) {
    const { a, b, pct } = classified.chain;
    const unit = classified.kind === "value" ? "pesos contratados" : "contratos";
    return `Es decir: ${formatAmount(a)} de ${formatAmount(b)} ${unit} — el ${formatPct(pct)}%.`;
  }

  return null;
}
