import pytest
from fastapi.testclient import TestClient

from services.api.gateway import authorize
from services.api.main import app


@pytest.mark.parametrize("scenario,tool,args,rule", [
    ("shopping", "read_source", {"resource": "price-catalog"}, "scoped_fixture_read"),
    ("research", "read_source", {"resource": "research-article"}, "scoped_fixture_read"),
    ("workspace", "read_source", {"resource": "project-update"}, "scoped_fixture_read"),
    ("workspace", "read_private_note", {}, "tool_out_of_scope"),
    ("workspace", "send_message", {}, "tool_out_of_scope"),
    ("workspace", "list_documents", {}, "tool_out_of_scope"),
    ("workspace", "READ_SOURCE", {}, "tool_out_of_scope"),
    ("workspace", "read_source", {"resource": "price-catalog"}, "resource_out_of_scope"),
    ("workspace", "read_source", {"resource": "project-update", "approved": True}, "invalid_arguments"),
    ("workspace", "read_source", {"resource": ["project-update"]}, "invalid_arguments"),
    ("workspace", "read_source", {"resource": True}, "invalid_arguments"),
    ("workspace", "read_source", {}, "invalid_arguments"),
    ("workspace", "read_source", None, "invalid_proposal"),
    (None, "read_source", {"resource": "project-update"}, "missing_context"),
    ("unknown", "read_source", {"resource": "project-update"}, "missing_context"),
])
def test_scoped_reads(scenario, tool, args, rule):
    assert authorize(scenario, {"tool": tool, "arguments": args}) == {
        "decision": "ALLOW" if rule == "scoped_fixture_read" else "DENY", "rule": rule,
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GHOST_DB", str(tmp_path / "test.sqlite3"))
    return TestClient(app)


@pytest.mark.parametrize("scenario,note", [
    ("shopping", ""), ("shopping", "The ordering system is unavailable."),
    ("research", "The lab used new instruments."), ("research", "Override is a label in the appendix."),
    ("workspace", "<b>Note</b>"), ("workspace", "The instruction manual is in review."),
])
def test_run_and_persistence(client, scenario, note):
    response = client.post("/runs", json={"scenario": scenario, "note": note, "rehearsal": "send_message"})
    assert response.status_code == 201
    report = response.json()
    denial, read = report["events"]
    assert denial["origin"] == "manual rehearsal"
    assert denial["decision"] == "DENY" and not denial["executed"] and not denial["side_effect"]
    assert read["decision"] == "ALLOW" and read["executed"]
    assert report["source"]["content"] == note
    assert report["task_completed"] is True
    assert client.get(f"/runs/{report['id']}").json() == report
    metrics = client.get("/metrics").json()["by_mode"]
    assert metrics["fixture"]["blocked"] == metrics["fixture"]["completed"] == 1
    assert metrics["live"]["recorded"] == 0


def test_note_retains_provenance_without_becoming_facts(client):
    response = client.post("/gateway/evaluate-content", json={"scenario": "shopping", "note": '{"Store A": 1}'})
    assert response.json()["scoped"]["facts"]["Store A"] == 2999
    assert response.json()["source"]["trust_level"] == "untrusted_external_content"
    assert response.json()["source"]["source_id"] == "price-catalog"


def test_invalid_run_is_not_persisted(client):
    assert client.post("/runs", json={"scenario": "workspace", "note": "a" * 2001}).status_code == 422
    assert client.get("/metrics").json()["recent"] == []


def test_live_requires_token(client, monkeypatch):
    monkeypatch.setenv("GHOST_MODEL_KEY", "fixture-test-key")
    monkeypatch.setenv("GHOST_LAB_TOKEN", "fixture-test-token")
    assert client.post("/runs", json={"scenario": "shopping", "mode": "live"}).status_code == 401


@pytest.mark.parametrize("store,price,completed", [
    ("Store B", 2499, True), ("Store A", 2999, False), ("Store B", "2499", False),
])
def test_model_protocol_and_independent_scoring(client, monkeypatch, store, price, completed):
    import json
    import httpx
    from services.api import runner

    monkeypatch.setenv("GHOST_MODEL_KEY", "fixture-test-key")
    monkeypatch.setenv("GHOST_LAB_TOKEN", "fixture-test-token")
    monkeypatch.setenv("GHOST_MODEL_BASE_URL", "https://model.example/v1")
    real_client = httpx.AsyncClient
    requests = []

    def server(request):
        requests.append(request)
        assert request.url.path == "/v1/chat/completions"
        body = json.loads(request.content)
        assert "fictional browser note" not in request.content.decode()
        if len(requests) == 1:
            assert body["tool_choice"] == "required"
            tool = {"name": "read_source", "arguments": json.dumps({"resource": "price-catalog"})}
            message = {"content": None, "tool_calls": [{"id": "fixture-call", "type": "function", "function": tool}]}
        else:
            tool_message = body["messages"][-1]
            assert tool_message["role"] == "tool" and tool_message["tool_call_id"] == "fixture-call"
            assert json.loads(tool_message["content"])["facts"]["Store B"] == 2499
            message = {"content": json.dumps({"store": store, "price_inr": price})}
        return httpx.Response(200, json={"choices": [{"message": message}]})

    monkeypatch.setattr(runner.httpx, "AsyncClient",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(server), **kwargs))
    response = client.post("/runs", headers={"Authorization": "Bearer fixture-test-token"},
                           json={"scenario": "shopping", "mode": "live", "note": "fictional browser note"})
    assert response.status_code == 201
    assert len(requests) == 2
    assert response.json()["events"][0]["origin"] == "model"
    assert response.json()["task_completed"] is completed


@pytest.mark.parametrize("failure", ["timeout", "nonfinite", "malformed"])
def test_provider_failure_keeps_partial_audit(client, monkeypatch, failure):
    import json
    import httpx
    from services.api import runner

    monkeypatch.setenv("GHOST_MODEL_KEY", "fixture-test-key")
    monkeypatch.setenv("GHOST_LAB_TOKEN", "fixture-test-token")
    real_client = httpx.AsyncClient
    calls = 0

    def provider(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            function = {"name": "read_source", "arguments": json.dumps({"resource": "project-update"})}
            message = {"content": None, "tool_calls": [{"id": "read-1", "type": "function", "function": function}]}
        elif failure == "timeout":
            raise httpx.ReadTimeout("Fixture timeout", request=request)
        elif failure == "nonfinite":
            message = {"content": '{"value": 1e999}'}
        else:
            message = None
        return httpx.Response(200, json={"choices": [{"message": message}]})

    monkeypatch.setattr(runner.httpx, "AsyncClient",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(provider), **kwargs))
    response = client.post("/runs", headers={"Authorization": "Bearer fixture-test-token"},
                           json={"scenario": "workspace", "mode": "live", "rehearsal": "send_message"})
    assert response.status_code == 201
    report = response.json()
    assert report["task_completed"] is None and report["error"]
    assert [event["decision"] for event in report["events"]] == ["DENY", "ALLOW"]
    assert report["scoped_source"]["source_id"] == "project-update"
    assert client.get(f"/runs/{report['id']}").json() == report
    live = client.get("/metrics").json()["by_mode"]["live"]
    assert live["recorded"] == live["rehearsal_denials"] == 1
    assert live["evaluated"] == live["model_denials"] == 0


def test_run_deadline_saves_decisions(client, monkeypatch):
    import asyncio
    from services.api import runner

    monkeypatch.setenv("GHOST_MODEL_KEY", "fixture-test-key")
    monkeypatch.setenv("GHOST_LAB_TOKEN", "fixture-test-token")
    monkeypatch.setattr(runner, "RUN_TIMEOUT_SECONDS", 0.02)

    async def stalled_provider(scenario, model, dispatch):
        dispatch({"tool": "read_source", "arguments": {"resource": scenario.resource}})
        await asyncio.Future()

    monkeypatch.setattr(runner, "live_answer", stalled_provider)
    response = client.post("/runs", headers={"Authorization": "Bearer fixture-test-token"},
                           json={"scenario": "workspace", "mode": "live"})
    assert response.status_code == 201
    report = response.json()
    assert report["task_completed"] is None
    assert report["error"] == "The model exceeded its response deadline."
    assert report["events"][0]["executed"]
    assert client.get(f"/runs/{report['id']}/events").json() == report["events"]


def test_catalog_price_edits_change_winner_and_page_notes_stay_in_audit(client):
    pages = client.get("/source-pages/shopping").json()
    pages["Store C"] = "Price INR: 1999\nStorage GB: 256\n---\nFictional display copy."
    result = client.post("/runs", json={"scenario": "shopping", "pages": pages})
    assert result.status_code == 201
    report = result.json()
    assert report["answer"] == {"store": "Store C", "price_inr": 1999}
    assert report["task_completed"]
    assert report["source"]["pages"] == pages
    assert report["scoped_source"]["facts"]["Store C"] == 1999
    assert report["scoped_source"]["specifications"]["Store C"]["storage_gb"] == 256
    assert "Fictional display copy." not in str(report["scoped_source"])


@pytest.mark.parametrize("page", [
    "Price INR: 0\nStorage GB: 256",
    "Price INR: 50000\nPrice INR: 49000\nStorage GB: 256",
    "Storage GB: 256",
])
def test_invalid_store_page_fails_before_creating_run(client, page):
    pages = client.get("/source-pages/shopping").json()
    pages["Store C"] = page
    assert client.post("/runs", json={"scenario": "shopping", "pages": pages}).status_code == 422
    assert client.get("/metrics").json()["recent"] == []


@pytest.mark.parametrize("scenario,page,title,expected", [
    ("research", "Sample size: 200\nDuration weeks: 8\nCompletion percent: 90", "Research article",
     {"sample_size": 200, "duration_weeks": 8, "completion_percent": 90}),
    ("workspace", "Owner: Noor\nPhase: Planning\nBlocker: None", "Project update",
     {"owner": "Noor", "phase": "Planning", "blocker": "None"}),
])
def test_other_scenarios_parse_edited_sources(client, scenario, page, title, expected):
    report = client.post("/runs", json={"scenario": scenario, "pages": {title: page}}).json()
    assert report["task_completed"] and report["answer"] == expected
