# Contrato v0 — Case File (expediente)

**Estado: PROVISIONAL.** Derivado del spec del Evidence Layer (objetos `direct`/`derived`), no de
respuestas reales de Croma. Las formas de `source`, `raw_reference` y los IDs de entidad se
ajustarán cuando existan capturas reales. Cualquier cambio a este contrato pasa por el
orquestador — las Pistas C y D no lo modifican unilateralmente.

Los nombres de campo y valores de ejemplo usan entidades **ficticias**. Nunca poner datos de
empresas reales en fixtures.

```json
{
  "question": "¿Por qué Empresa Ejemplo S.A.S. concentra tantos contratos con la Entidad Ficticia?",
  "status": "complete",
  "entities": [
    { "id": "co:nit:900000001", "name": "Empresa Ejemplo S.A.S.", "role": "investigada" },
    { "id": "co:entidad:ENT-001", "name": "Entidad Ficticia de Ejemplo", "role": "contratante" }
  ],
  "sources_consulted": [
    { "source": "croma:rues:entity-by-nit", "at": "2026-08-14T20:00:00Z", "status": "ok" },
    { "source": "croma:secop:contracts-by-provider", "at": "2026-08-14T20:01:00Z", "status": "ok" }
  ],
  "findings": [
    {
      "id": "f1",
      "title": "Concentración de contratos en una sola entidad contratante",
      "narrative": "Texto corto legible; TODO lo afirmado aquí debe estar respaldado por los objetos de evidence[] — nunca paráfrasis libre sin objeto detrás.",
      "evidence": [
        {
          "claim": "Empresa Ejemplo S.A.S. está registrada como activa",
          "type": "direct",
          "source": "croma:rues:entity-by-nit",
          "raw_reference": "<id o campo exacto de la respuesta — forma final pendiente de capturas reales>"
        },
        {
          "claim": "El 70.6% de los contratos de Empresa Ejemplo provienen de Entidad Ficticia",
          "type": "derived",
          "calculation": "12 / 17",
          "sources": ["croma:secop:contract:123", "croma:secop:contract:456"]
        }
      ]
    }
  ],
  "unknowns": [
    "La evidencia no permite concluir X — se declara explícitamente."
  ],
  "next_steps": [
    "Qué valdría la pena investigar después."
  ]
}
```

Notas de diseño:

- `status` ∈ `complete | needs_disambiguation | partial` (si una fuente falló, el expediente se
  degrada con gracia y lo dice).
- Cuando `status = needs_disambiguation`, el expediente incluye `candidates[]` (lista de entidades
  posibles) en lugar de `findings`.
- Los dos tipos de evidencia son EXACTAMENTE los del spec: `direct` y `derived`. No existe
  `hypothesis` en el MVP. Nunca hay score de riesgo ni veredicto.
