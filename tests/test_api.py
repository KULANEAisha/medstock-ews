"""API tests. The LLM is stubbed, so no API key or network is needed."""
import pytest
from fastapi.testclient import TestClient

from medstock import api, llm


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    api._hits.clear()
    monkeypatch.setattr(api, "RATE_LIMIT", 3)


def _fake_ok(question, **kw):
    return {"question": question, "answer": "F10 and F16", "model": "stub", "error": None, "cached": False,
            "tool_calls": [{"tool": "get_at_risk_facilities", "args": {"commodity": "amoxicillin"}, "result": {"big": 1}}]}


def test_health():
    with TestClient(api.app) as c:
        assert c.get("/health").json()["status"] == "ok"


def test_ask_ok_hides_raw_tool_results(monkeypatch):
    monkeypatch.setattr(llm, "ask", _fake_ok)
    with TestClient(api.app) as c:
        r = c.post("/ask", json={"question": "Which facilities are at risk?"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "F10 and F16"
    assert body["tools_called"] == [{"tool": "get_at_risk_facilities", "args": {"commodity": "amoxicillin"}}]
    assert "result" not in str(body["tools_called"])


def test_llm_error_returns_502_without_leaking_details(monkeypatch):
    monkeypatch.setattr(llm, "ask", lambda q, **kw: {"question": q, "answer": "", "tool_calls": [], "model": "stub",
                                                     "error": "RuntimeError: secret-key-abc"})
    with TestClient(api.app) as c:
        r = c.post("/ask", json={"question": "anything here"})
    assert r.status_code == 502
    assert "secret" not in r.text


def test_validation():
    with TestClient(api.app) as c:
        assert c.post("/ask", json={"question": ""}).status_code == 422
        assert c.post("/ask", json={"question": "x" * 501}).status_code == 422
        assert c.post("/ask", json={}).status_code == 422


def test_rate_limit(monkeypatch):
    monkeypatch.setattr(llm, "ask", _fake_ok)
    with TestClient(api.app) as c:
        codes = [c.post("/ask", json={"question": "hello there"}).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]


def test_cors_allows_configured_origin():
    with TestClient(api.app) as c:
        r = c.options("/ask", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
                                       "Access-Control-Request-Headers": "content-type"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_overview_matches_tools():
    from medstock.tools import get_at_risk_facilities
    with TestClient(api.app) as c:
        body = c.get("/overview").json()
    assert len(body["facilities"]) == 24 and len(body["commodities"]) == 4
    risk = {f["id"] for f in body["facilities"] if f["cells"].get("amoxicillin_dt", {}).get("status") == "STOCKOUT_RISK"}
    truth = {f["facility_id"] for f in get_at_risk_facilities("amoxicillin")["facilities"]}
    assert risk == truth
    assert body["counts"]["amoxicillin_dt"]["STOCKOUT_RISK"] == len(truth)
    cell = next(f for f in body["facilities"] if f["id"] == "F10")["cells"]["amoxicillin_dt"]
    assert len(cell["history"]) == 6 and cell["stock"] == 316
