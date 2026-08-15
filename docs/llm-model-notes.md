# Notas del modelo LLM (gpt-5.6-terra vía chat.completions)

Verificado contra la API real de OpenAI el 15-ago-2026 (probes en vivo, 6 combinaciones):

| Llamada | reasoning_effort | Resultado |
|---|---|---|
| Sin tools | omitido / `high` / `none` | OK (todos) |
| Con function tools | omitido / `high` | **400** — "Function tools with reasoning_effort are not supported for gpt-5.6-terra in /v1/chat/completions" |
| Con function tools | `none` | OK |

Implicaciones para TRAZA:

- La restricción aplica SOLO a llamadas con function tools. El proveedor (`agent/providers.py`)
  maneja esto con fallback adaptativo — no requiere configuración manual.
- **Palanca disponible, no aplicada:** el paso de síntesis/finalize podría hacerse como llamada
  SIN tools (structured output) con `reasoning_effort` alto, si los ensayos del caso demo
  mostraran síntesis pobre. Verificado con smoke dirigido (15-ago) que NO hace falta hoy: con
  `effort='none'` el agente ejecutó el salto profundo — de la pregunta por una empresa, extrajo
  el representante legal de RUES `related_parties` y decidió por su cuenta consultarlo en
  Procuraduría y Contraloría (fuente solo-persona), sin que la pregunta mencionara personas.
  Se documenta para no re-descubrirla bajo presión el día de la demo.
- Migrar a la Responses API también levantaría la restricción (mensaje de error de OpenAI la
  sugiere); no se hace en el MVP — el costo de re-testear el loop no se justifica.
