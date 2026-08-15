# Evidence Layer — diseño (Pista C)

**ESTADO: PROVISIONAL — pendiente de validar contra capturas reales de Croma.**
Las formas finales de `source` (SourceRef) y `raw_reference` se ajustarán a los datos
reales, no al revés. Nada de este documento congela la forma de las respuestas de Croma:
donde el diseño necesita tocar datos crudos, la referencia es **opaca**.

Código: `backend/evidence/models.py`, `backend/evidence/verify.py`.
Tests: `backend/tests/test_evidence.py` (datos sintéticos, entidades ficticias).
Contrato compartido con UI: `docs/contracts/case-file.v0.md` (v0 — solo el orquestador lo cambia).

## Principio rector

Cada hallazgo del expediente se construye **únicamente** desde objetos de evidencia:

- `direct` — lo dice literalmente una respuesta de Croma.
- `derived` — calculado desde una o más respuestas, con cadena de cálculo
  **reproducible mecánicamente**.

No existe `hypothesis` en el MVP. Nunca hay score de riesgo, probabilidad de corrupción
ni veredicto — y el diseño lo hace estructuralmente imposible, no solo desaconsejado:

| Regla de producto | Garantía estructural |
| --- | --- |
| Solo dos tipos de evidencia | Unión discriminada por `type` (`direct \| derived`); cualquier otro valor es `ValidationError`. |
| Un hallazgo sin evidencia no existe | `Finding.evidence` con `min_length=1`; construir sin evidencia lanza `ValidationError`. |
| Nada de scores/veredictos colados | `extra="forbid"` en todos los modelos: un campo `risk_score` (o cualquier otro) rompe la validación. |
| "Derivado" implica reproducible | `verify_derived` re-ejecuta la cadena; el pipeline solo acepta `derived` que pase verify. |
| Un derived sin fuentes no existe | `DerivedEvidence.sources` con `min_length=1`. |

## Decisiones tomadas

### 1. `SourceRef`: string con convención, validación laxa

Convención provisional: `croma:<fuente>:<endpoint-o-tipo>[:<id>]`
(ej. `croma:rues:entity-by-nit`, `croma:secop:contract:123`).

Se valida con una regex deliberadamente laxa (`SOURCE_REF_PATTERN` en `models.py`): fija
el prefijo `croma:` y la estructura de 3–4 segmentos, nada más. No es un modelo
estructurado a propósito: convertirlo en objeto (fuente, endpoint, id tipados) antes de
ver datos reales sería inventar la API de Croma.

### 2. `raw_reference`: string opaco

Un `direct` apunta al lugar exacto de la respuesta cruda que respalda el claim. Hoy es un
`str` no vacío sin más estructura. Cuando existan capturas reales se decidirá si es un id
de registro, un JSON Pointer, un par (captura, campo), etc. El Evidence Layer no le impone
forma para no tener que deshacerla.

### 3. `calculation` (legible) + `calculation_steps` (re-ejecutable)

Un `derived` lleva las dos representaciones:

- `calculation`: expresión legible para humanos (ej. `"12 / 17"`). **No se re-ejecuta.**
- `calculation_steps`: lista de pasos `{operation, inputs, output}` con valores concretos.
  Es la representación que `verify_derived` re-ejecuta mecánicamente.

Los inputs de un paso son números literales o referencias `"$k"` al output del paso `k`
(0-based, siempre un paso *anterior*). Ejemplo — "el 70.6% de los contratos":

```json
[
  { "operation": "divide",   "inputs": [12, 17],     "output": 0.7058823529411765 },
  { "operation": "multiply", "inputs": ["$0", 100],  "output": 70.58823529411765 },
  { "operation": "round",    "inputs": ["$1", 1],    "output": 70.6 }
]
```

El registro de operaciones es **cerrado y pequeño** (`OPERATIONS` en `verify.py`):
`sum`, `subtract`, `multiply`, `divide`, `round`. Es deliberado: cada operación nueva
amplía lo que un `derived` puede afirmar y debe recomputarse sin ambigüedad. Sin `eval`,
sin expresiones libres.

### 4. `verify_derived` es la puerta del expediente

`verify_derived(evidence) -> VerificationResult` re-ejecuta la cadena y exige:

1. `sources` no vacía (defensa en profundidad; el modelo ya lo impide).
2. Toda operación pertenece al registro cerrado.
3. Toda referencia `"$k"` apunta a un paso anterior que sí pudo recomputarse
   (nada de referencias hacia adelante, a sí mismo, ni sintaxis inválida).
4. El output declarado de **cada** paso coincide con el recomputado
   (`math.isclose`, tolerancia 1e-9), incluido el final.

Detalle importante: las referencias `"$k"` resuelven contra el valor **recomputado**, no
el declarado — un output declarado falso no contamina el resto de la cadena y todos los
errores se reportan de una vez. La operación `operation` desconocida, la división por
cero y la aridad incorrecta son errores de verificación (cadena rechazada), no
excepciones.

El contrato de uso para el pipeline (Pista de agente): **ningún `derived` entra al
CaseFile final sin `verify_derived(...).valid == True`.** La correspondencia semántica
entre `narrative` y evidencia (que el texto no afirme más que los objetos) queda a cargo
del pipeline; el Evidence Layer garantiza la parte estructural.

### 5. Errores de construcción vs. errores de verificación

- **Construcción** (`ValidationError`): forma imposible — evidencia sin fuentes, finding
  sin evidencia, tipo distinto de `direct`/`derived`, campos extra.
- **Verificación** (`VerificationResult.valid == False` con `errors[]`): forma válida
  pero cadena rota — output que no cuadra, operación desconocida, referencia colgante.

La sintaxis de las referencias `"$k"` se valida en verify (no en el modelo) a propósito:
una cadena rota debe ser un resultado *rechazable e inspeccionable*, no una excepción a
mitad de la construcción.

### 6. `CaseFile` e invariante de `candidates`

`status ∈ {complete, needs_disambiguation, partial}`. Invariante validado en el modelo:

- `needs_disambiguation` ⇒ `candidates[]` no vacía **y** `findings` vacía
  (el contrato dice "candidates en lugar de findings").
- cualquier otro status ⇒ `candidates` ausente.

`CaseFile.to_contract_dict()` / `.to_contract_json()` serializan a la forma exacta del
contrato v0 (`exclude_none` omite la clave `candidates` cuando no aplica, y los datetime
UTC salen como `...Z`).

### 7. Cosas que el diseño **no** hace todavía (a propósito)

- No modela las respuestas de Croma (eso es de `croma_client`, y depende de capturas).
- No parsea `calculation` legible ni intenta derivar los steps desde ella.
- No tiene operación `count`: hoy los conteos entran como literales en el primer paso y
  su procedencia la cubren las `sources`. Ver preguntas abiertas.

## Propuestas de cambio al contrato v0 (para el orquestador — NO aplicadas)

1. **Añadir `calculation_steps` a la evidencia `derived`.** El ejemplo del contrato solo
   trae `calculation` y `sources`; con eso la cadena es legible pero no re-ejecutable
   mecánicamente, que es la garantía central del spec. Es una adición retrocompatible
   (campo nuevo; la UI puede ignorarlo o usarlo para render de la cadena). Los modelos ya
   la serializan; el test de contrato la separa explícitamente antes de comparar verbatim.
2. **Definir la forma de `candidates[]`.** El contrato la menciona pero no la especifica.
   Provisional en código: `{id, name, detail?}`.
3. **Definir el vocabulario de `sources_consulted[].status`.** El contrato solo
   ejemplifica `"ok"`. Provisional en código: `{ok, error}`. ¿Hace falta `timeout` o
   `partial` como estados propios?
4. ~~(No es del contrato): el layout plano de `backend/` hacía fallar `pip install -e .`
   con setuptools.~~ Resuelto durante el hackathon por otra pista añadiendo
   `[tool.setuptools] packages = [...]` a `pyproject.toml`; el install editable ya
   funciona y el Evidence Layer está instalado con `pip install -e ".[dev]"`.

## Preguntas abiertas — SOLO las capturas reales las responden

**SourceRef / identidad de registros**

- ¿Qué identifica unívocamente un contrato en SECOP vía Croma? ¿Un id propio de Croma, el
  número de proceso SECOP, la pareja (entidad, número)? ¿Es estable entre consultas?
- ¿Los nombres de fuente/endpoint que expone Croma coinciden con los que asumimos
  (`rues`, `secop`, `entity-by-nit`, ...) o tienen su propia nomenclatura?
- ¿Hay ids con caracteres fuera de `[A-Za-z0-9._-]` (dos puntos, espacios, tildes)? La
  regex laxa habría que ajustarla.

**raw_reference**

- ¿Cómo se referencia un campo dentro de una respuesta RUES? ¿Las respuestas son JSON
  navegable (→ JSON Pointer), texto plano, o registros con id propio?
- ¿Una "respuesta de Croma" es un objeto único o una página de resultados? Si es página,
  `raw_reference` necesita (captura, índice, campo).
- ¿Croma devuelve algo re-consultable (id de request, URL) que permita auditar el
  `direct` después, o hay que persistir la captura cruda en `data/raw/`?

**Cadena de cálculo**

- ¿Necesitamos una operación `count` de primera clase? Depende de si Croma devuelve
  listas enumerables (contar = operación sobre la captura) o agregados ya calculados
  (el conteo es un `direct` y el literal del primer paso debería citarlo). Posible
  evolución: que los inputs literales puedan citar el `raw_reference` del que salen.
- ¿Montos en COP con qué precisión llegan? ¿Hace falta aritmética decimal (evitar float)
  para sumas de dinero grandes?

**Expediente**

- ¿Qué metadatos reales existen para `sources_consulted` (latencia, versión del dataset,
  fecha de corte de RUES/SECOP)? La fecha de corte importa: "activa" según RUES es
  "activa a fecha X".
- ¿Qué campos trae Croma para desambiguar homónimos (municipio, estado, fecha de
  matrícula)? Eso fija la forma final de `candidates[]`.
- ¿Los NIT llegan con dígito de verificación? Afecta la convención `co:nit:<nit>` de
  `Entity.id`.
