"""Configuración del cliente Croma vía pydantic-settings.

Lee el ``.env`` de la raíz del repo. CROMA_BASE_URL NO tiene valor por defecto
a propósito: no asumimos la URL real de la API hasta verla en la plataforma.

UNVERIFIED: el mecanismo de autenticación real de Croma no está confirmado.
Soportamos dos schemes candidatos vía CROMA_AUTH_SCHEME:
  - "bearer"    -> header ``Authorization: Bearer <key>`` (default)
  - "x-api-key" -> header ``X-API-Key: <key>``
Hasta tener capturas reales, cualquiera de los dos puede ser el correcto.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from croma_client.exceptions import CromaConfigError

# Raíz del repo: config.py vive en backend/croma_client/, subimos dos niveles.
REPO_ROOT: Path = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE: Path = REPO_ROOT / ".env"

_MISSING_HINT = (
    "Copia .env.example a .env en la raíz del repo y completa los valores. "
    "La API key se obtiene en platform.usecroma.com; la base URL se toma de la "
    "plataforma (no la asumimos por defecto)."
)


class CromaSettings(BaseSettings):
    """Settings del cliente Croma, con prefijo CROMA_ en variables de entorno."""

    model_config = SettingsConfigDict(
        env_file=DEFAULT_ENV_FILE,
        env_prefix="CROMA_",
        extra="ignore",  # el .env de la raíz también trae variables del LLM (Pista B)
    )

    api_key: str
    base_url: str  # sin default a propósito: la URL real es UNVERIFIED
    # UNVERIFIED: scheme de auth real desconocido; ver docstring del módulo.
    auth_scheme: Literal["bearer", "x-api-key"] = "bearer"
    timeout_seconds: float = 15.0

    @field_validator("api_key", "base_url")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        """Trata cadena vacía (típico de un .env recién copiado) como faltante."""
        if not value.strip():
            raise ValueError("no puede estar vacío")
        return value.strip()

    @field_validator("base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        """Normaliza la base URL para poder concatenar rutas sin dobles barras."""
        return value.rstrip("/")


def load_settings(env_file: str | Path | None = None) -> CromaSettings:
    """Carga settings y convierte errores de validación en CromaConfigError accionable.

    Args:
        env_file: ruta alternativa al .env (útil en tests). Por defecto, el de la raíz.
    """
    try:
        return CromaSettings(_env_file=env_file if env_file is not None else DEFAULT_ENV_FILE)
    except ValidationError as exc:
        missing = ", ".join(
            f"CROMA_{str(err['loc'][0]).upper()}" for err in exc.errors() if err.get("loc")
        )
        raise CromaConfigError(
            f"Configuración de Croma incompleta o inválida ({missing or 'ver detalle'}). "
            f"{_MISSING_HINT}"
        ) from exc
