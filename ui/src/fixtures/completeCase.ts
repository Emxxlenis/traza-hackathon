import type { CaseFile } from "../types/caseFile";

/**
 * Fixture: complete case file.
 * ALL entities are FICTITIOUS (NIT range 9000000xx reserved for fixtures).
 * Pending integration against real Croma data.
 */
export const completeCase: CaseFile = {
  question:
    "¿Por qué Empresa Ejemplo S.A.S. concentra tantos contratos con la Entidad Ficticia de Ejemplo?",
  status: "complete",
  entities: [
    { id: "co:nit:900000001", name: "Empresa Ejemplo S.A.S.", role: "investigada" },
    { id: "co:entidad:ENT-001", name: "Entidad Ficticia de Ejemplo", role: "contratante" },
  ],
  sources_consulted: [
    { source: "croma:rues:entity-by-nit", at: "2026-08-14T20:00:00Z", status: "ok" },
    { source: "croma:secop:contracts-by-provider", at: "2026-08-14T20:01:00Z", status: "ok" },
  ],
  findings: [
    {
      id: "f1",
      title: "Concentración de contratos en una sola entidad contratante",
      narrative:
        "De los 17 contratos públicos registrados a nombre de Empresa Ejemplo S.A.S., 12 fueron suscritos con la Entidad Ficticia de Ejemplo. La empresa figura activa en el registro mercantil.",
      evidence: [
        {
          claim: "Empresa Ejemplo S.A.S. está registrada como activa en el registro mercantil",
          type: "direct",
          source: "croma:rues:entity-by-nit",
          raw_reference: "rues.matricula.estado = 'ACTIVA' (respuesta simulada — forma final pendiente)",
        },
        {
          claim:
            "El 70,6 % de los contratos de Empresa Ejemplo S.A.S. provienen de la Entidad Ficticia de Ejemplo",
          type: "derived",
          calculation: "12 contratos con ENT-001 / 17 contratos totales = 0,706 → 70,6 %",
          // Percentage-by-count chain, exactly as the backend reducers emit it.
          calculation_steps: [
            { operation: "divide", inputs: [12, 17], output: 0.7058823529411765 },
            { operation: "multiply", inputs: ["$0", 100], output: 70.58823529411765 },
            { operation: "round", inputs: ["$1", 1], output: 70.6 },
          ],
          sources: [
            "croma:secop:contract:FIC-2023-0101",
            "croma:secop:contract:FIC-2023-0145",
            "croma:secop:contract:FIC-2024-0012",
            "croma:secop:contracts-by-provider",
          ],
        },
      ],
    },
    {
      id: "f2",
      title: "Crecimiento del valor contratado entre 2023 y 2024",
      narrative:
        "El valor total contratado por Empresa Ejemplo S.A.S. pasó de $890 millones en 2023 a $2.140 millones en 2024, un aumento del 140 %. La empresa fue matriculada en 2022.",
      evidence: [
        {
          claim: "Empresa Ejemplo S.A.S. fue matriculada el 15 de marzo de 2022",
          type: "direct",
          source: "croma:rues:entity-by-nit",
          raw_reference: "rues.matricula.fecha = '2022-03-15' (respuesta simulada — forma final pendiente)",
        },
        {
          claim: "El valor contratado creció 140 % entre 2023 y 2024",
          type: "derived",
          calculation:
            "($2.140M en 2024 − $890M en 2023) / $890M = 1,404 → +140,4 %",
          // Growth calculation: NOT one of the two reducer share patterns
          // (percentage chain / sum chain) — the UI shows the raw steps but
          // adds no plain-language translation for it.
          calculation_steps: [
            { operation: "subtract", inputs: [2140000000, 890000000], output: 1250000000 },
            { operation: "divide", inputs: ["$0", 890000000], output: 1.404494382022472 },
            { operation: "multiply", inputs: ["$1", 100], output: 140.4494382022472 },
          ],
          sources: [
            "croma:secop:contract:FIC-2023-0101",
            "croma:secop:contract:FIC-2024-0012",
            "croma:secop:contracts-by-provider",
          ],
        },
      ],
    },
  ],
  unknowns: [
    "No sabemos bajo qué modalidad se adjudicaron los 12 contratos (licitación, contratación directa u otra): la fuente consultada no incluye ese campo.",
    "No sabemos si existen vínculos societarios entre Empresa Ejemplo S.A.S. y funcionarios de la Entidad Ficticia de Ejemplo: no se consultó composición accionaria.",
    "La evidencia describe una concentración de contratos; no permite concluir que esa concentración sea irregular.",
  ],
  next_steps: [
    "Consultar la modalidad de adjudicación de cada contrato en SECOP II.",
    "Revisar la composición accionaria y los representantes legales en RUES.",
    "Comparar la concentración con la de otros proveedores de la misma entidad contratante para tener línea base.",
  ],
};
