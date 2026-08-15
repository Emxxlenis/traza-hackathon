import type { CaseFile } from "../types/caseFile";

/**
 * Fixture: disambiguation case — three FICTITIOUS candidates with similar names.
 * Pending integration against real Croma data.
 */
export const disambiguationCase: CaseFile = {
  question: "¿Qué contratos públicos tiene Distribuidora Andina?",
  status: "needs_disambiguation",
  entities: [],
  sources_consulted: [
    { source: "croma:rues:search-by-name", at: "2026-08-14T20:00:00Z", status: "ok" },
  ],
  findings: [],
  candidates: [
    {
      id: "co:nit:900000002",
      name: "Distribuidora Andina S.A.S.",
      detail: "NIT 900000002 · Bogotá D.C. · matrícula activa",
    },
    {
      id: "co:nit:900000003",
      name: "Distribuidora Andina del Caribe S.A.S.",
      detail: "NIT 900000003 · Barranquilla · matrícula activa",
    },
    {
      id: "co:nit:900000004",
      name: "Distribuidora Andina y Cía. Ltda.",
      detail: "NIT 900000004 · Medellín · matrícula cancelada en 2021",
    },
  ],
  unknowns: [],
  next_steps: [],
};
