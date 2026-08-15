# Contrato v0.1 — Case File (expediente)

**Changelog v0.1 (14-ago, decidido por el orquestador tras propuestas convergentes de las Pistas C y D):**

1. `derived` gana `calculation_steps`: lista de pasos `{operation, inputs, output}` re-ejecutable
   mecánicamente (operaciones del registro cerrado: `sum|subtract|multiply|divide|round`; inputs
   son literales numéricos o refs `"$k"` al output de un paso anterior). `calculation` se mantiene
   como expresión legible para humanos; la garantía de reproducibilidad vive en los steps.
2. `candidates[]` queda fijado como `{id, name, detail?}` — `detail` es el texto corto que
   distingue homónimos (NIT, ciudad, estado de matrícula).
3. `sources_consulted[].status` ∈ `ok | error` (timeout se reporta como `error`).
4. Continuación tras desambiguar: `POST /investigate` acepta `candidate_id` opcional y devuelve un
   `CaseFile` completo. (Aplica a la capa app/Pista B al integrarse.)

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
          "calculation_steps": [
            { "operation": "divide", "inputs": [12, 17], "output": 0.7058823529411765 },
            { "operation": "multiply", "inputs": ["$0", 100], "output": 70.58823529411765 },
            { "operation": "round", "inputs": ["$1", 1], "output": 70.6 }
          ],
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
