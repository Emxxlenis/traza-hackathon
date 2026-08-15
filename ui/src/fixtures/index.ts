import type { CaseFile, Candidate } from "../types/caseFile";
import { completeCase } from "./completeCase";
import { disambiguationCase } from "./disambiguationCase";

export { completeCase, disambiguationCase };

/**
 * Mock-only helper: builds the case file that "continues" the investigation
 * after the user picks a candidate, so the demo flow stays coherent
 * (the resolved expediente talks about the chosen fictitious entity).
 * The real backend will do this server-side from the candidate id.
 */
export function buildResolvedCase(candidate: Candidate): CaseFile {
  const nit = candidate.id.replace("co:nit:", "");
  return {
    ...completeCase,
    question: `${disambiguationCase.question} (candidato elegido: ${candidate.name})`,
    entities: [
      { id: candidate.id, name: candidate.name, role: "investigada" },
      { id: "co:entidad:ENT-001", name: "Entidad Ficticia de Ejemplo", role: "contratante" },
    ],
    findings: completeCase.findings.map((finding) => ({
      ...finding,
      narrative: finding.narrative.replaceAll("Empresa Ejemplo S.A.S.", candidate.name),
      evidence: finding.evidence.map((ev) => ({
        ...ev,
        claim: ev.claim.replaceAll("Empresa Ejemplo S.A.S.", candidate.name),
      })),
    })),
    unknowns: completeCase.unknowns.map((u) =>
      u.replaceAll("Empresa Ejemplo S.A.S.", `${candidate.name} (NIT ${nit})`),
    ),
  };
}
