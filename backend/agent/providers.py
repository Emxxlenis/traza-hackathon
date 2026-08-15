"""Interfaz de proveedor LLM para el loop del agente investigador.

El loop NUNCA importa ``openai`` directamente: habla con el protocolo
``LLMProvider``, que normaliza mensajes y tool calls a un formato interno
simple y JSON-serializable.

Formato interno de mensajes:
  - ``{"role": "system" | "user", "content": str}``
  - ``{"role": "assistant", "content": str | None,
      "tool_calls": [{"id": str, "name": str, "arguments": dict}]}``
    (``tool_calls`` es opcional)
  - ``{"role": "tool", "tool_call_id": str, "name": str, "content": str}``

Formato interno de tools: ``{"name": str, "description": str, "parameters":
dict}`` con ``parameters`` como JSON Schema. Cada proveedor concreto traduce a
su formato nativo.

Decisión de diseño — Chat Completions, no Responses API: ``OpenAIProvider``
usa ``client.chat.completions.create`` con ``tools`` estándar. Motivos: (1) es
la superficie de tool-calling más estable del SDK instalado (openai 3.x la
soporta íntegramente), (2) su formato de mensajes mapea 1:1 con nuestro
formato interno (``assistant.tool_calls`` / ``role="tool"``), y (3) no
necesitamos nada exclusivo de Responses (estado en servidor, built-in tools).

``temperature=0`` por defecto (consistencia de demo). Compatibilidad
adaptativa con modelos de razonamiento (verificado contra gpt-5.6-terra el
14-ago-2026): algunos rechazan ``temperature != 1`` con un 400, y otros
rechazan function tools en /v1/chat/completions salvo que se envíe
``reasoning_effort='none'``. En ambos casos el proveedor ajusta el parámetro,
reintenta y recuerda la decisión para el resto de la sesión — sin atarse a un
modelo concreto.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from openai import AsyncOpenAI, BadRequestError
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("traza.agent.providers")

# Raíz del repo: providers.py vive en backend/agent/, subimos dos niveles.
REPO_ROOT: Path = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE: Path = REPO_ROOT / ".env"


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Tool call normalizada al formato interno (arguments ya parseados a dict)."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Respuesta normalizada del proveedor.

    Atributos:
        content: texto libre del asistente (None si solo hubo tool calls).
        tool_calls: tool calls normalizadas (tupla vacía si no hubo).
        usage: contadores de tokens si el proveedor los reporta
            (prompt_tokens / completion_tokens / total_tokens).
    """

    content: str | None
    tool_calls: tuple[ToolCall, ...] = ()
    usage: dict[str, int] | None = None


class LLMProvider(Protocol):
    """Protocolo que el loop consume. Cualquier proveedor debe implementarlo."""

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        tool_choice: str | None = None,
    ) -> LLMResponse:
        """Completa la conversación; ``tool_choice`` fuerza una tool por nombre."""
        ...


class LLMSettings(BaseSettings):
    """Settings del LLM leídos del .env de la raíz (extra='ignore': el .env
    también trae las variables de Croma)."""

    model_config = SettingsConfigDict(env_file=DEFAULT_ENV_FILE, extra="ignore")

    llm_provider: str = "openai"
    llm_model: str
    openai_api_key: str
    llm_temperature: float = 0.0


# --- Conversión formato interno <-> OpenAI Chat Completions ---


def _to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Traduce mensajes internos al formato de Chat Completions."""
    converted: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "assistant" and message.get("tool_calls"):
            converted.append(
                {
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": json.dumps(
                                    call.get("arguments", {}), ensure_ascii=False
                                ),
                            },
                        }
                        for call in message["tool_calls"]
                    ],
                }
            )
        elif role == "tool":
            converted.append(
                {
                    "role": "tool",
                    "tool_call_id": message["tool_call_id"],
                    "content": message.get("content", ""),
                }
            )
        else:
            converted.append({"role": role, "content": message.get("content", "")})
    return converted


def _to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Traduce definiciones internas de tools al formato de Chat Completions."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
            },
        }
        for tool in tools
    ]


def _parse_arguments(raw: str | None) -> dict[str, Any]:
    """Parsea los arguments JSON de una tool call; ante basura devuelve {}."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        logger.warning("arguments de tool call no parseables: %r", raw[:200])
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_completion(completion: Any) -> LLMResponse:
    """Normaliza una ChatCompletion de OpenAI al formato interno."""
    message = completion.choices[0].message
    tool_calls: list[ToolCall] = []
    for call in message.tool_calls or []:
        tool_calls.append(
            ToolCall(
                id=call.id,
                name=call.function.name,
                arguments=_parse_arguments(call.function.arguments),
            )
        )
    usage: dict[str, int] | None = None
    raw_usage = getattr(completion, "usage", None)
    if raw_usage is not None:
        usage = {
            "prompt_tokens": getattr(raw_usage, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(raw_usage, "completion_tokens", 0) or 0,
            "total_tokens": getattr(raw_usage, "total_tokens", 0) or 0,
        }
    return LLMResponse(
        content=message.content,
        tool_calls=tuple(tool_calls),
        usage=usage,
    )


@dataclass
class OpenAIProvider:
    """Proveedor OpenAI vía Chat Completions con tool-calling estándar."""

    model: str
    api_key: str
    temperature: float = 0.0
    _client: AsyncOpenAI = field(init=False, repr=False)
    _use_temperature: bool = field(default=True, init=False, repr=False)
    _force_no_reasoning: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = AsyncOpenAI(api_key=self.api_key)

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        tool_choice: str | None = None,
    ) -> LLMResponse:
        """Una vuelta de Chat Completions; normaliza la respuesta al formato interno."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": _to_openai_messages(messages),
        }
        if tools:
            kwargs["tools"] = _to_openai_tools(tools)
        if tool_choice is not None:
            kwargs["tool_choice"] = {"type": "function", "function": {"name": tool_choice}}
        if self._use_temperature:
            kwargs["temperature"] = self.temperature
        if self._force_no_reasoning:
            kwargs["reasoning_effort"] = "none"

        # Compatibilidad adaptativa: hasta 2 ajustes de parámetros ante 400s
        # conocidos de modelos de razonamiento (ver docstring del módulo).
        for _ in range(3):
            try:
                completion = await self._client.chat.completions.create(**kwargs)
                break
            except BadRequestError as exc:
                detail = str(exc).lower()
                if self._use_temperature and "temperature" in detail:
                    logger.warning(
                        "el modelo %s rechazó temperature=%s; se reintenta sin el parámetro",
                        self.model,
                        self.temperature,
                    )
                    self._use_temperature = False
                    kwargs.pop("temperature", None)
                    continue
                if not self._force_no_reasoning and "reasoning_effort" in detail:
                    # Verificado con gpt-5.6-terra: function tools en
                    # /v1/chat/completions exigen reasoning_effort='none'.
                    logger.warning(
                        "el modelo %s exige reasoning_effort='none' para usar tools; "
                        "se reintenta con ese parámetro",
                        self.model,
                    )
                    self._force_no_reasoning = True
                    kwargs["reasoning_effort"] = "none"
                    continue
                raise
        return _normalize_completion(completion)


def build_provider(settings: LLMSettings | None = None) -> LLMProvider:
    """Fabrica el proveedor según LLM_PROVIDER del .env de la raíz."""
    settings = settings if settings is not None else LLMSettings()
    provider_name = settings.llm_provider.strip().lower()
    if provider_name != "openai":
        raise RuntimeError(
            f"LLM_PROVIDER={settings.llm_provider!r} no soportado: el MVP solo "
            "implementa 'openai' (interfaz LLMProvider lista para otros)."
        )
    return OpenAIProvider(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        temperature=settings.llm_temperature,
    )
