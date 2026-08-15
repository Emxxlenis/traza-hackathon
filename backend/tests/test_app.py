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


def test_health() -> None:
    client = TestClient(app_main.app)
    assert TestClient(app_main.app).get("/health").json() == {"status": "ok"}
    assert client.get("/health").status_code == 200
