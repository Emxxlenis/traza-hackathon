"""Rutas candidatas de la API de Croma.

TODAS las rutas de este módulo son UNVERIFIED: no existen todavía capturas
reales de la API. Los documentos internos del spec ADEMÁS discrepan entre sí
(p. ej. /co/secop/process/v1 vs /co/secop/processes-by-entity/v1 vs
/co/secop/contracts-by-provider/v1). Ninguna ruta se da por buena hasta que el
humano capture respuestas reales con scripts/capture.py.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EndpointSpec:
    """Descriptor de un endpoint candidato.

    Atributos:
        name: nombre corto usado por el CLI de captura y los métodos convenience.
        path: ruta candidata (UNVERIFIED hasta capturas reales).
        source: etiqueta de provenance para el Evidence Layer, ej. "croma:rues:entity-by-nit".
    """

    name: str
    path: str
    source: str


# UNVERIFIED: búsqueda de entidades RUES por nombre.
RUES_ENTITIES_BY_NAME = "/co/rues/entities-by-name/v1"
# UNVERIFIED: entidad RUES por NIT.
RUES_ENTITY_BY_NIT = "/co/rues/entity-by-nit/v1"
# UNVERIFIED: los docs internos discrepan (/co/secop/process/v1 también aparece).
SECOP_PROCESSES_BY_ENTITY = "/co/secop/processes-by-entity/v1"
# UNVERIFIED: los docs internos discrepan (/co/secop/process/v1 también aparece).
SECOP_CONTRACTS_BY_PROVIDER = "/co/secop/contracts-by-provider/v1"
# UNVERIFIED: antecedentes disciplinarios (Procuraduría).
PROCURADURIA_DISCIPLINARY_RECORDS = "/co/procuraduria/disciplinary-records/v1"
# UNVERIFIED: antecedentes fiscales (Contraloría).
CONTRALORIA_FISCAL_RECORDS = "/co/contraloria/fiscal-records/v1"

# Registro de endpoints por nombre corto. Todas las rutas son UNVERIFIED.
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
    (para explorar rutas alternativas cuando lleguen las capturas reales).
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
