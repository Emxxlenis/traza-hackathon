"""Tests del wiring HTTP: /investigate delega en agent.api y serializa el contrato."""

from fastapi.testclient import TestClient

import app.main as app_main
from evidence.models import CaseFile


def _fake_case_file() -> CaseFile:
    return CaseFile(
        question="¿Qué contratos tiene Empresa Ejemplo S.A.S.?",
        status="partial",
        entities=[],
        sources_consulted=[],
        findings=[],
        unknowns=["Sin fuentes consultadas: expediente de prueba."],
        next_steps=[],
    )


def test_investigate_route_delegates_and_serializes(monkeypatch) -> None:
    captured: dict = {}

    async def fake_investigate(question: str, candidate_id: str | None = None, **_: object):
        captured["question"] = question
        captured["candidate_id"] = candidate_id
        return _fake_case_file()

    monkeypatch.setattr(app_main, "investigate", fake_investigate)
    client = TestClient(app_main.app)

    resp = client.post("/investigate", json={"question": "hola", "candidate_id": "c1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "partial"
    assert "candidates" not in body  # exclude_none del contrato
    assert captured == {"question": "hola", "candidate_id": "c1"}


def test_investigate_route_requires_question() -> None:
    client = TestClient(app_main.app)
    resp = client.post("/investigate", json={})
    assert resp.status_code == 422


def test_investigate_rejects_blank_and_oversized_questions() -> None:
    client = TestClient(app_main.app)
    assert client.post("/investigate", json={"question": "   \n\t  "}).status_code == 422
    assert client.post("/investigate", json={"question": "x" * 1001}).status_code == 422
    assert client.post("/investigate", json={"question": "ok", "candidate_id": "c" * 201}).status_code == 422


def test_health_exposes_nonsecret_operational_config() -> None:
    client = TestClient(app_main.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert isinstance(body["rate_limit_per_ip_hour"], int)
    assert isinstance(body["rate_limit_global_hour"], int)
