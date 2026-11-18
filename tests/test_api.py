import pytest
from fastapi.testclient import TestClient

from ups.api.app import create_app
from ups.api.settings import Settings


@pytest.fixture
def client():
    return TestClient(create_app(Settings(rate_limit_per_minute=0)))


def new_run(client, sid="website-redesign"):
    r = client.post("/api/runs", json={"scenarioId": sid})
    assert r.status_code == 201
    return r.json()


def play_to_end(client, run_id):
    while True:
        s = client.post(f"/api/runs/{run_id}/advance", json={"untilNextEvent": True}).json()
        if s["status"] == "complete":
            return s
        pd = s["pendingDecision"]
        if pd:
            s = client.post(f"/api/runs/{run_id}/decisions", json={
                "eventId": pd["eventId"], "decisionId": pd["decisionId"], "optionId": pd["options"][0]["id"]}).json()
            if s["status"] == "complete":
                return s


def test_scenarios_listed_without_spoilers(client):
    items = client.get("/api/scenarios").json()["scenarios"]
    assert len(items) >= 3
    info = client.get(f"/api/scenarios/{items[0]['id']}").json()
    assert info["assumptions"] and "events" not in info and "decisions" not in info


def test_meta_has_disclaimer_and_retention(client):
    m = client.get("/api/meta").json()
    assert "not a forecast" in m["disclaimer"] and m["retention"]["runExpiresAfterMinutes"] == 120


def test_one_scenario_runs_end_to_end(client):
    run = new_run(client)
    rid = run["runId"]
    assert run["day"] == 0 and len(run["measures"]) == 4
    s = client.post(f"/api/runs/{rid}/advance", json={"days": 30}).json()
    assert s["status"] == "awaitingDecision" and s["day"] == 3          # stopped at the first event
    pd = s["pendingDecision"]
    assert len(pd["options"]) >= 2 and all("effects" not in o for o in pd["options"])
    before = {m["id"]: m["value"] for m in s["measures"]}
    s = client.post(f"/api/runs/{rid}/decisions", json={"eventId": pd["eventId"], "decisionId": pd["decisionId"], "optionId": "negotiate"}).json()
    after = {m["id"]: m["value"] for m in s["measures"]}
    assert before != after and s["status"] == "running"                  # measures changed
    final = play_to_end(client, rid)
    assert final["status"] == "complete"
    summary = client.get(f"/api/runs/{rid}/summary").json()
    assert summary["final"] and summary["rating"]
    hist = client.get(f"/api/runs/{rid}/history").json()["entries"]
    assert any(e["type"] == "decision" for e in hist)
    frames = client.get(f"/api/runs/{rid}/replay").json()["frames"]
    assert len(frames) == len(hist) + 1


def test_reset_mid_run(client):
    rid = new_run(client)["runId"]
    client.post(f"/api/runs/{rid}/advance", json={"days": 5})
    s = client.post(f"/api/runs/{rid}/reset").json()
    assert s["day"] == 0 and s["resetCount"] == 1 and s["historyLength"] == 0


def test_double_submit_returns_409(client):
    rid = new_run(client)["runId"]
    pd = client.post(f"/api/runs/{rid}/advance", json={"days": 30}).json()["pendingDecision"]
    body = {"eventId": pd["eventId"], "decisionId": pd["decisionId"], "optionId": pd["options"][0]["id"]}
    assert client.post(f"/api/runs/{rid}/decisions", json=body).status_code == 200
    r = client.post(f"/api/runs/{rid}/decisions", json=body)
    assert r.status_code == 409 and r.json()["error"]["code"] in ("no_decision_pending", "decision_mismatch")


def test_advance_blocked_by_pending_decision(client):
    rid = new_run(client)["runId"]
    client.post(f"/api/runs/{rid}/advance", json={"days": 30})
    r = client.post(f"/api/runs/{rid}/advance", json={"days": 1})
    assert r.status_code == 409 and r.json()["error"]["code"] == "decision_pending"


def test_invalid_option_400(client):
    rid = new_run(client)["runId"]
    pd = client.post(f"/api/runs/{rid}/advance", json={"days": 30}).json()["pendingDecision"]
    r = client.post(f"/api/runs/{rid}/decisions", json={"eventId": pd["eventId"], "decisionId": pd["decisionId"], "optionId": "bogus"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_option"


def test_advance_after_complete_409(client):
    rid = new_run(client)["runId"]
    play_to_end(client, rid)
    r = client.post(f"/api/runs/{rid}/advance", json={"days": 1})
    assert r.status_code == 409 and r.json()["error"]["code"] == "run_complete"


@pytest.mark.parametrize("body", [{"days": 0}, {"days": 9999}, {"days": "x"}, {"extra": 1}, {"days": 1.5}])
def test_bad_advance_bodies_422(client, body):
    rid = new_run(client)["runId"]
    r = client.post(f"/api/runs/{rid}/advance", json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


def test_malformed_json_422(client):
    rid = new_run(client)["runId"]
    r = client.post(f"/api/runs/{rid}/advance", content="{oops", headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_unknown_scenario_and_run(client):
    assert client.post("/api/runs", json={"scenarioId": "nope"}).status_code == 404
    assert client.post("/api/runs", json={"scenarioId": "../etc"}).status_code == 422
    assert client.get("/api/runs/" + "0" * 32).status_code == 404
    assert client.get("/api/runs/not-a-run-id").status_code == 422


def test_delete_run(client):
    rid = new_run(client)["runId"]
    assert client.delete(f"/api/runs/{rid}").status_code == 204
    assert client.get(f"/api/runs/{rid}").status_code == 404


def test_runs_are_isolated(client):
    a, b = new_run(client)["runId"], new_run(client)["runId"]
    client.post(f"/api/runs/{a}/advance", json={"days": 2})
    assert client.get(f"/api/runs/{b}").json()["day"] == 0


def test_run_expires_after_ttl():
    now = [0.0]
    c = TestClient(create_app(Settings(rate_limit_per_minute=0, run_ttl_minutes=10), clock=lambda: now[0]))
    rid = new_run(c)["runId"]
    now[0] = 9 * 60
    assert c.get(f"/api/runs/{rid}").status_code == 200       # activity refreshes expiry
    now[0] = 9 * 60 + 11 * 60
    assert c.get(f"/api/runs/{rid}").status_code == 404


def test_max_runs_evicts_least_recently_used():
    now = [0.0]
    c = TestClient(create_app(Settings(rate_limit_per_minute=0, max_runs=2), clock=lambda: now[0]))
    ids = []
    for _ in range(3):
        now[0] += 1
        ids.append(new_run(c)["runId"])
    assert c.get(f"/api/runs/{ids[0]}").status_code == 404
    assert c.get(f"/api/runs/{ids[2]}").status_code == 200


def test_access_token_required_when_configured():
    c = TestClient(create_app(Settings(rate_limit_per_minute=0, access_token="s3cret")))
    assert c.get("/api/scenarios").status_code == 401
    assert c.get("/api/scenarios", headers={"X-Access-Token": "wrong"}).status_code == 401
    assert c.get("/api/scenarios", headers={"X-Access-Token": "s3cret"}).status_code == 200
    assert c.get("/api/health").status_code == 200
    assert c.get("/").status_code == 200                      # the page itself loads, then asks for the token


def test_rate_limit():
    now = [0.0]
    c = TestClient(create_app(Settings(rate_limit_per_minute=3), clock=lambda: now[0]))
    codes = [c.get("/api/scenarios").status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    now[0] = 61
    assert c.get("/api/scenarios").status_code == 200


def test_oversized_body_rejected(client):
    r = client.post("/api/runs", content="x" * 20_000, headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_security_headers_and_client_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Training simulator, not a forecast" in r.text
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/api/scenarios").headers["cache-control"] == "no-store"


def test_client_has_no_inline_script_or_style():
    html = open("client/index.html", encoding="utf-8").read()
    assert "<script>" not in html and "<style" not in html and ' style="' not in html
