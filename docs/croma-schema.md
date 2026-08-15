# Croma API — esquema verificado contra capturas reales

**Capturado el 14/15-ago-2026** con llamadas en vivo (payloads completos en `data/raw/`, fuera de
git). Este doc describe SOLO estructura — sin datos personales de terceros. Lo no probado se marca
NO VERIFICADO.

## Transporte (verificado)

- Base URL: `https://api.croma.run`
- **Todos los endpoints son `POST` con body JSON** (GET devuelve 405).
- Auth: `Authorization: Bearer <key>` — funciona; `X-API-Key` NO probado.
- Éxito: `{"data": {...}}` · Error: `{"error": {type, code, message, param, details.issues[]}}`
  — los 400 son informativos (nombran el param faltante/inválido y las opciones válidas).
- Paginación estándar: `{total, page_size, total_pages, page}` + `capped: bool` al nivel de data.
  `page_size` observado: 10 (RUES by-name), 500 (SECOP). Cómo pedir página N: NO VERIFICADO
  (presumiblemente `page` en el body).

## RUES

### `/co/rues/entities-by-name/v1` — body: `{"name": str}`
`data`: `query`, `capped`, `entities[]`, `pagination`.
`entities[]`: `registry_id`, `nit` (a veces null en el nivel superior), `verification_digit`,
`name`, `chamber_code/name`, `registration_number`, `registration_status` (`ACTIVA|CANCELADA`),
`legal_organization`, `last_renewed_year`, `category`, y `detail{...}` con el registro completo:
`nit` **zero-padded a 14 dígitos** en `secondary_identification`, fechas de
matrícula/renovación/cancelación, `primary_activity{code, description}` (CIIU), dirección/contacto
(frecuentemente null), `certificates_sale_url`.

### `/co/rues/entity-by-nit/v1` — body: `{"document_number": str}` (NIT sin puntos, sin DV)
`data`: `found: bool`, `document_number`, `entity{...}` (mismo shape que `detail` de arriba),
`financials[]`, `renewals[]`, `related_parties[]`, `notices[]`.
- `related_parties[]`: `{document_number, name, role}` — **aquí sale el representante legal**
  (ej. rol "Representante Legal - Principal"). Es el puente empresa → persona para
  Procuraduría/Contraloría.
- ⚠️ Observado (1 caso): un registro con `registration_status: CANCELADA` que by-name SÍ devuelve
  responde `found: false` aquí (probado sin padding, con padding y con DV). Hipótesis: el índice
  por NIT solo cubre matrículas activas. NO GENERALIZADO — verificar con más casos.
- `found: false` es respuesta 200 normal, no error.

## SECOP

### `/co/secop/contracts-by-provider/v1` — body: `{"document_number": str}` + filtros `from_date`, `to_date`, `entity_nit` (aparecen en el echo de data; formato NO VERIFICADO)
`data`: `document_number`, `entity_nit`, `from_date`, `to_date`, `count`, `capped`, `contracts[]`,
`pagination`. Observado: 855 totales → `count: 500`, `capped: true` (una página).
`contracts[]` (~50 campos): `contract_id` (**estable, ej. formato `CO1.PCCNTR.<n>` — ideal para
SourceRef**), `reference`, `entity`, `entity_nit`, `provider`, `provider_document`,
`provider_document_type`, `legal_rep_name/document`, `status`, `contract_type`, `modality`,
`object` (texto del objeto contractual), `value`, `invoiced_value`, `paid_value`, fechas
(`sign_date`, `start_date`, `end_date`), `duration`, `supervisor`, `funding_origin`, `sector`,
`url` (**link al proceso en SECOP oficial — evidencia trazable**).

### `/co/secop/processes-by-entity/v1` — body: `{"document_number": str}` (NIT de la entidad contratante)
`data`: `document_number`, `from_date`, `to_date`, `count`, `capped`, `processes[]`, `pagination`.
`processes[]`: `notice_uid`, `process_id`, `reference`, `name`, `entity`, `entity_nit`, `modality`,
`contract_type`, `base_price`, `phase`, `procedure_status`, `published_date`, `url`.
- ⚠️ Los procesos son el lado de la CONVOCATORIA: **no traen adjudicatario/proveedor**. La relación
  proveedor↔entidad solo se ve desde `contracts-by-provider`.

## Procuraduría

### `/co/procuraduria/disciplinary-records/v1` — body: `{"document_number": str, "document_type"?: str}`
`document_type` default `"CC"`; acepta `"NIT"` (label "Nit"). `data`: `found`, `document_type`,
`document_type_label`, `document_number`, `full_name`, `has_records`, `status` (texto literal de
la fuente), `message`, `records[]`, `checked_at`. Shape de `records[]` con antecedentes reales:
NO VERIFICADO (controles dieron sin antecedentes).

## Contraloría

### `/co/contraloria/fiscal-records/v1` — body: `{"document_number": str, "document_type"?: str}`
- ⚠️ `document_type` SOLO acepta tipos de PERSONA: `CC|CE|TI|PA|PEP|PPT` — **no hay NIT**. Los
  antecedentes fiscales se consultan sobre la persona (el representante legal desde
  `related_parties` de RUES), no sobre la empresa.
- `data`: `found`, `document_type`, `document_type_label`, `document_number`,
  `is_fiscal_responsible: bool`, `verification_code` (**código de certificado verificable —
  evidencia trazable**), `certified_at`, y más campos (ver captura).

## Identidad entre fuentes

- Persona/empresa: `document_number` como string en las 4 fuentes. RUES por NIT: sin DV, sin
  puntos. En payloads RUES el NIT aparece zero-padded a 14 en `secondary_identification`.
- Contrato: `contract_id` de SECOP. Proceso: `notice_uid`/`process_id`.
- `url` presente en contratos y procesos → fuente oficial navegable.

## Pendiente de verificar

- Cómo se pide la página 2+ (`page` en body?). Comportamiento de `from_date`/`to_date`.
- `X-API-Key` como auth alternativo. Rate limits (ningún 429 observado).
- `records[]` de Procuraduría con antecedentes reales; shape completo de fiscal-records.
- Si `entity-by-nit` cubre o no matrículas canceladas (1 solo caso observado).
