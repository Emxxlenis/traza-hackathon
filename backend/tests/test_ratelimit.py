"""Tests del rate limiting de /investigate (ventana deslizante en memoria)."""

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
import app.ratelimit as rl
from evidence.models import CaseFile

# /investigate exige cuenta; estos tests no son sobre eso (ver conftest.bypass_auth).
pytestmark = pytest.mark.usefixtures("bypass_auth")



@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    rl.reset()
    monkeypatch.setattr(rl, "PER_IP_PER_HOUR", 2)
    monkeypatch.setattr(rl, "GLOBAL_PER_HOUR", 3)

    async def fake_investigate(question: str, candidate_id: str | None = None, **_: object):
        return CaseFile(
            question=question,
            status="partial",
            entities=[],
            sources_consulted=[],
            findings=[],
            unknowns=["expediente de prueba"],
            next_steps=[],
        )

    monkeypatch.setattr(app_main, "investigate", fake_investigate)
    yield
    rl.reset()


def _post(client: TestClient, ip: str | None = None):
    headers = {"x-forwarded-for": ip} if ip else {}
    return client.post("/investigate", json={"question": "prueba"}, headers=headers)


def test_per_ip_limit_returns_429_with_detail() -> None:
    client = TestClient(app_main.app)
    assert _post(client, "10.0.0.1").status_code == 200
    assert _post(client, "10.0.0.1").status_code == 200
    resp = _post(client, "10.0.0.1")
    assert resp.status_code == 429
    assert "investigaciones por hora" in resp.json()["detail"]


def test_different_ips_have_independent_quotas() -> None:
    client = TestClient(app_main.app)
    assert _post(client, "10.0.0.1").status_code == 200
    assert _post(client, "10.0.0.1").status_code == 200
    assert _post(client, "10.0.0.2").status_code == 200


def test_global_limit_caps_across_ips() -> None:
    client = TestClient(app_main.app)
    assert _post(client, "10.0.0.1").status_code == 200
    assert _post(client, "10.0.0.2").status_code == 200
    assert _post(client, "10.0.0.3").status_code == 200
    resp = _post(client, "10.0.0.4")
    assert resp.status_code == 429
    assert "límite global" in resp.json()["detail"]


def test_window_slides(monkeypatch) -> None:
    client = TestClient(app_main.app)
    t = {"now": 1000.0}
    monkeypatch.setattr(rl.time, "monotonic", lambda: t["now"])
    assert _post(client, "10.0.0.9").status_code == 200
    assert _post(client, "10.0.0.9").status_code == 200
    assert _post(client, "10.0.0.9").status_code == 429
    t["now"] += 3601.0
    assert _post(client, "10.0.0.9").status_code == 200


def test_limit_zero_returns_429_not_500(monkeypatch) -> None:
    monkeypatch.setattr(rl, "PER_IP_PER_HOUR", 0)
    client = TestClient(app_main.app)
    resp = _post(client, "10.9.9.9")
    assert resp.status_code == 429
    assert "investigaciones por hora" in resp.json()["detail"]


def test_xff_first_hop_wins() -> None:
    client = TestClient(app_main.app)
    assert _post(client, "1.1.1.1, 9.9.9.9").status_code == 200
    assert _post(client, "1.1.1.1, 8.8.8.8").status_code == 200
    assert _post(client, "1.1.1.1, 7.7.7.7").status_code == 429
