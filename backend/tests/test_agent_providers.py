"""Tests de la capa de proveedor LLM: conversión de formatos y settings.

Sin red: se prueban las funciones puras de traducción interno<->OpenAI y la
carga de settings desde variables de entorno (extra='ignore').
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.providers import (
    LLMSettings,
    OpenAIProvider,
    _normalize_completion,
    _parse_arguments,
    _to_openai_messages,
    _to_openai_tools,
    build_provider,
)


def test_to_openai_messages_serializes_tool_calls_and_results():
    internal = [
        {"role": "system", "content": "sistema"},
        {"role": "user", "content": "pregunta"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call-1", "name": "rues_entity_by_nit",
                 "arguments": {"document_number": "900000011"}}
            ],
        },
        {"role": "tool", "tool_call_id": "call-1", "name": "rues_entity_by_nit",
         "content": "{\"found\": true}"},
    ]
    converted = _to_openai_messages(internal)
    assert converted[0] == {"role": "system", "content": "sistema"}
    assistant = converted[2]
    assert assistant["tool_calls"][0]["type"] == "function"
    assert assistant["tool_calls"][0]["function"]["name"] == "rues_entity_by_nit"
    # arguments viaja como string JSON, exactamente como exige Chat Completions.
    assert assistant["tool_calls"][0]["function"]["arguments"] == (
        '{"document_number": "900000011"}'
    )
    tool_message = converted[3]
    assert tool_message == {"role": "tool", "tool_call_id": "call-1",
                            "content": "{\"found\": true}"}


def test_to_openai_tools_wraps_function_schema():
    tools = _to_openai_tools(
        [{"name": "t", "description": "d", "parameters": {"type": "object"}}]
    )
    assert tools == [
        {"type": "function",
         "function": {"name": "t", "description": "d", "parameters": {"type": "object"}}}
    ]


def test_normalize_completion_parses_tool_calls_and_usage():
    completion = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="call-9",
                            function=SimpleNamespace(
                                name="secop_contracts_by_provider",
                                arguments='{"document_number": "900000011"}',
                            ),
                        )
                    ],
                )
            )
        ],
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20, total_tokens=120),
    )
    response = _normalize_completion(completion)
    assert response.content is None
    assert response.tool_calls[0].name == "secop_contracts_by_provider"
    assert response.tool_calls[0].arguments == {"document_number": "900000011"}
    assert response.usage == {"prompt_tokens": 100, "completion_tokens": 20,
                              "total_tokens": 120}


def test_parse_arguments_tolerates_garbage():
    assert _parse_arguments(None) == {}
    assert _parse_arguments("") == {}
    assert _parse_arguments("{no es json") == {}
    assert _parse_arguments('["lista", "no", "dict"]') == {}
    assert _parse_arguments('{"a": 1}') == {"a": 1}


def test_llm_settings_read_env_and_ignore_extras(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "modelo-de-prueba")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-ficticia")
    # Variables ajenas (Croma) no deben romper la carga: extra="ignore".
    monkeypatch.setenv("CROMA_API_KEY", "otra-clave")
    settings = LLMSettings(_env_file=None)
    assert settings.llm_model == "modelo-de-prueba"
    assert settings.llm_temperature == 0.0  # default de demo


def test_build_provider_returns_openai_and_rejects_unknown():
    settings = LLMSettings(
        llm_provider="openai",
        llm_model="modelo-x",
        openai_api_key="sk-test",
        _env_file=None,
    )
    provider = build_provider(settings)
    assert isinstance(provider, OpenAIProvider)
    assert provider.temperature == 0.0

    unknown = LLMSettings(
        llm_provider="acme-llm",
        llm_model="modelo-x",
        openai_api_key="sk-test",
        _env_file=None,
    )
    with pytest.raises(RuntimeError, match="acme-llm"):
        build_provider(unknown)
