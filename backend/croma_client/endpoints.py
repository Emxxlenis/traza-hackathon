"""Rutas de la API de Croma — VERIFICADAS contra capturas reales.

Las 6 rutas de este módulo existen y responden (capturas del 14/15-ago-2026;
ver docs/croma-schema.md, la fuente de verdad del esquema). Todas se invocan
con method=POST y body JSON — GET devuelve 405.

Siguen NO VERIFICADOS los detalles listados en docs/croma-schema.md: cómo se
pide la página 2+, el formato de los filtros from_date/to_date, X-API-Key como
auth alternativo y rate limits.

DESCARTADA: la ruta /co/secop/process/v1 que aparecía en docs internos NO
existe tal como la usábamos; las rutas SECOP reales son las dos registradas
abajo.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EndpointSpec:
    """Descriptor de un endpoint verificado.

    Atributos:
        name: nombre corto usado por el CLI de captura y los métodos convenience.
        path: ruta VERIFICADA (existe y responde; se invoca con POST + body JSON).
        source: etiqueta de provenance para el Evidence Layer, ej. "croma:rues:entity-by-nit".
    """

    name: str
    path: str
    source: str


# VERIFIED (POST): búsqueda RUES por nombre. Body: {"name": str}.
RUES_ENTITIES_BY_NAME = "/co/rues/entities-by-name/v1"
# VERIFIED (POST): entidad RUES por NIT (sin puntos, sin DV). Body: {"document_number": str}.
RUES_ENTITY_BY_NIT = "/co/rues/entity-by-nit/v1"
# VERIFIED (POST): procesos por entidad contratante. Body: {"document_number": str} + filtros
# opcionales (formato de fechas NO VERIFICADO).
SECOP_PROCESSES_BY_ENTITY = "/co/secop/processes-by-entity/v1"
# VERIFIED (POST): contratos por proveedor. Body: {"document_number": str} + filtros
# opcionales (formato de fechas NO VERIFICADO).
SECOP_CONTRACTS_BY_PROVIDER = "/co/secop/contracts-by-provider/v1"
# VERIFIED (POST): antecedentes disciplinarios. document_type acepta "CC" (default) y "NIT".
PROCURADURIA_DISCIPLINARY_RECORDS = "/co/procuraduria/disciplinary-records/v1"
# VERIFIED (POST): antecedentes fiscales. document_type SOLO persona (CC|CE|TI|PA|PEP|PPT).
CONTRALORIA_FISCAL_RECORDS = "/co/contraloria/fiscal-records/v1"

# Registro de endpoints por nombre corto. Todas las rutas VERIFICADAS, method=POST.
ENDPOINTS: dict[str, EndpointSpec] = {
    spec.name: spec
    for spec in (
        EndpointSpec("entities-by-name", RUES_ENTITIES_BY_NAME, "croma:rues:entities-by-name"),
        EndpointSpec("entity-by-nit", RUES_ENTITY_BY_NIT, "croma:rues:entity-by-nit"),
        EndpointSpec(
            "processes-by-entity", SECOP_PROCESSES_BY_ENTITY, "croma:secop:processes-by-entity"
        ),
        EndpointSpec(
            "contracts-by-provider",
            SECOP_CONTRACTS_BY_PROVIDER,
            "croma:secop:contracts-by-provider",
        ),
        EndpointSpec(
            "disciplinary-records",
            PROCURADURIA_DISCIPLINARY_RECORDS,
            "croma:procuraduria:disciplinary-records",
        ),
        EndpointSpec(
            "fiscal-records", CONTRALORIA_FISCAL_RECORDS, "croma:contraloria:fiscal-records"
        ),
    )
}


def resolve_endpoint(name_or_path: str) -> EndpointSpec:
    """Resuelve un nombre corto o una ruta a su EndpointSpec.

    Acepta el nombre corto del registro ("entity-by-nit"), una ruta registrada
    ("/co/rues/entity-by-nit/v1") o una ruta arbitraria que empiece por "/"
    (para explorar rutas aún no registradas).
    """
    if name_or_path in ENDPOINTS:
        return ENDPOINTS[name_or_path]
    for spec in ENDPOINTS.values():
        if spec.path == name_or_path:
            return spec
    if name_or_path.startswith("/"):
        slug = name_or_path.strip("/").replace("/", ":")
        return EndpointSpec(name=name_or_path, path=name_or_path, source=f"croma:{slug}")
    known = ", ".join(sorted(ENDPOINTS))
    raise ValueError(f"Endpoint desconocido: {name_or_path!r}. Disponibles: {known}")
