"""Envelope de provenance para respuestas crudas de Croma.

RawResponse es SOLO provenance para el Evidence Layer: transporta el payload
tal cual llegó, sin interpretarlo. Aquí no hay parsing ni modelos tipados de
la respuesta — el payload es opaco POR POLÍTICA de esta capa (la estructura
verificada está documentada en docs/croma-schema.md, pero interpretarla es
responsabilidad de capas superiores).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RawResponse:
    """Respuesta cruda de Croma con metadatos de procedencia.

    Atributos:
        source: etiqueta de provenance, ej. "croma:rues:entity-by-nit".
        endpoint: ruta invocada (VERIFICADA; se llama con POST + body JSON).
        url: URL final de la petición.
        status_code: código HTTP de la respuesta.
        fetched_at: instante de la captura en UTC, formato ISO 8601.
        payload: cuerpo decodificado como dict/list OPACO — esta capa no asume
            su estructura interna (ver docs/croma-schema.md para el esquema).
        body_text: cuerpo verbatim (texto exacto recibido), para que
            scripts/capture.py pueda guardar la respuesta byte-a-byte.
    """

    source: str
    endpoint: str
    url: str
    status_code: int
    fetched_at: str
    payload: dict[str, Any] | list[Any]
    body_text: str

    def to_dict(self) -> dict[str, Any]:
        """Serializa el envelope completo (útil para persistencia/depuración)."""
        return asdict(self)
