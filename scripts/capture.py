#!/usr/bin/env python3
"""CLI de captura de respuestas reales de Croma.

Todos los endpoints verificados son POST con body JSON (ver docs/croma-schema.md);
cada ``--param clave=valor`` se convierte en un campo del body. El cuerpo de la
respuesta se guarda VERBATIM (byte-a-byte) en data/raw/, junto con un sidecar
.meta.json de provenance que registra método, body enviado y status HTTP. El
resumen impreso se limita a status, tamaño y claves de primer nivel — nunca
inspeccionamos más profundo.

Uso:
    python scripts/capture.py --list
    python scripts/capture.py entity-by-nit --param document_number=900123456
    python scripts/capture.py entities-by-name --param name="ACME SAS"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
# El paquete croma_client vive bajo backend/ y este script corre desde la raíz.
sys.path.insert(0, str(REPO_ROOT / "backend"))

from croma_client import ENDPOINTS, CromaClient, CromaError, RawResponse

RAW_DIR = REPO_ROOT / "data" / "raw"


def list_endpoints() -> None:
    """Imprime los endpoints disponibles (rutas VERIFICADAS, method=POST)."""
    print("Endpoints disponibles (rutas VERIFICADAS; todas POST con body JSON):\n")
    width = max(len(name) for name in ENDPOINTS)
    for name, spec in sorted(ENDPOINTS.items()):
        print(f"  {name:<{width}}  POST {spec.path}")
    print(
        "\nEjemplo: python scripts/capture.py entity-by-nit --param document_number=900123456"
    )


def parse_body(pairs: list[str]) -> dict[str, str]:
    """Convierte pares clave=valor de --param en el body JSON de la petición."""
    body: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            raise SystemExit(f"--param inválido: {pair!r} (formato esperado: clave=valor)")
        body[key] = value
    return body


def save_capture(raw: RawResponse, endpoint_name: str, body: dict[str, str]) -> Path:
    """Guarda el cuerpo VERBATIM en data/raw/ y un sidecar .meta.json de provenance."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    # source es "croma:<fuente>:<endpoint>"; usamos la fuente para el nombre de archivo.
    parts = raw.source.split(":")
    fuente = parts[1] if len(parts) > 1 else "croma"
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = RAW_DIR / f"{fuente}-{endpoint_name}-{timestamp}.raw.json"
    path.write_text(raw.body_text, encoding="utf-8")

    meta = {
        "source": raw.source,
        "endpoint": raw.endpoint,
        "url": raw.url,
        "method": "POST",
        "body": body,
        "status_code": raw.status_code,
        "fetched_at": raw.fetched_at,
    }
    path.with_suffix(".meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


def print_summary(raw: RawResponse, path: Path) -> None:
    """Resumen mínimo: status, tamaño y claves de primer nivel. Nada más profundo."""
    print(f"Guardado: {path}")
    print(f"  status : {raw.status_code}")
    print(f"  tamaño : {len(raw.body_text.encode('utf-8'))} bytes")
    payload: Any = raw.payload
    if isinstance(payload, dict):
        print(f"  claves de primer nivel: {sorted(payload.keys())}")
    elif isinstance(payload, list):
        print(f"  payload: lista con {len(payload)} elementos")


async def run_capture(endpoint_name: str, body: dict[str, str]) -> int:
    """Llama el endpoint vía CromaClient (POST + body JSON) y persiste la captura."""
    try:
        async with CromaClient() as client:
            raw = await client.call(endpoint_name, body)
    except CromaError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    path = save_capture(raw, endpoint_name, body)
    print_summary(raw, path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Captura respuestas crudas de Croma en data/raw/ (verbatim)."
    )
    parser.add_argument(
        "endpoint",
        nargs="?",
        help="nombre del endpoint (ver --list) o ruta que empiece por '/'",
    )
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="CLAVE=VALOR",
        help="campo del body JSON de la petición; repetible",
    )
    parser.add_argument(
        "--list", action="store_true", help="lista endpoints disponibles (POST, verificados)"
    )
    args = parser.parse_args()

    if args.list:
        list_endpoints()
        return 0
    if not args.endpoint:
        parser.error("falta el endpoint (o usa --list para ver los disponibles)")
    if args.endpoint not in ENDPOINTS and not args.endpoint.startswith("/"):
        print(f"Endpoint desconocido: {args.endpoint!r}\n", file=sys.stderr)
        list_endpoints()
        return 2
    return asyncio.run(run_capture(args.endpoint, parse_body(args.param)))


if __name__ == "__main__":
    raise SystemExit(main())
