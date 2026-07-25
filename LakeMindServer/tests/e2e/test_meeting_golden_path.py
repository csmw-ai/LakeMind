"""WP8-T02: Meeting Agent Golden Path — 14 step standard chain.

Requires a running LakeMind server on 127.0.0.1:10823 with:
- PostgreSQL, SeaweedFS, Ray, ModelServing all healthy
- A valid tenant token and pre-loaded ASR skill
"""
import pytest
import httpx
import time

CONTROL_PLANE = "http://127.0.0.1:10823"

try:
    _health = httpx.get(f"{CONTROL_PLANE}/api/v1/health", timeout=3.0)
    _SERVER_UP = _health.status_code == 200
except Exception:
    _SERVER_UP = False

skip_if_no_server = pytest.mark.skipif(not _SERVER_UP, reason="LakeMind server not running on :10823")


@pytest.fixture
def client():
    return httpx.Client(
        base_url=CONTROL_PLANE,
        headers={"Authorization": "Bearer test-token-tenant-a"},
        timeout=60.0,
    )


def _wait_for_job(client, job_id, terminal_states=None, timeout=120):
    terminal_states = terminal_states or {"SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT", "LOST"}
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/v1/jobs/{job_id}")
        if r.status_code == 200:
            status = r.json().get("status", "")
            if status in terminal_states:
                return r.json()
        time.sleep(2)
    return None


@skip_if_no_server
def test_01_health_check(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.2.0"


@skip_if_no_server
def test_02_list_assets(client):
    r = client.get("/api/v1/assets")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data or "results" in data or isinstance(data, list)


@skip_if_no_server
def test_03_list_skills(client):
    r = client.get("/api/v1/skills")
    assert r.status_code == 200
    data = r.json()
    items = data.get("items", data) if isinstance(data, dict) else data
    assert isinstance(items, list)


@skip_if_no_server
def test_04_submit_job(client):
    payload = {
        "skill_ref": "asr-transcribe",
        "inputs": {"audio_uri": "s3://test/sample.wav"},
    }
    r = client.post("/api/v1/jobs", json=payload)
    assert r.status_code in (200, 201, 202)
    data = r.json()
    assert "job_id" in data or "id" in data


@skip_if_no_server
def test_05_list_jobs(client):
    r = client.get("/api/v1/jobs")
    assert r.status_code == 200
    data = r.json()
    items = data.get("items", data) if isinstance(data, dict) else data
    assert isinstance(items, list)


@skip_if_no_server
def test_06_job_detail(client):
    r = client.get("/api/v1/jobs")
    assert r.status_code == 200
    data = r.json()
    items = data.get("items", data) if isinstance(data, dict) else data
    if not items:
        pytest.skip("No jobs available")
    job_id = items[0].get("job_id", items[0].get("id"))
    r2 = client.get(f"/api/v1/jobs/{job_id}")
    assert r2.status_code == 200


@skip_if_no_server
def test_07_job_timeline(client):
    r = client.get("/api/v1/jobs")
    assert r.status_code == 200
    data = r.json()
    items = data.get("items", data) if isinstance(data, dict) else data
    if not items:
        pytest.skip("No jobs available")
    job_id = items[0].get("job_id", items[0].get("id"))
    r2 = client.get(f"/api/v1/jobs/{job_id}/timeline")
    assert r2.status_code == 200
    events = r2.json()
    assert isinstance(events, list)


@skip_if_no_server
def test_08_job_attempts(client):
    r = client.get("/api/v1/jobs")
    assert r.status_code == 200
    data = r.json()
    items = data.get("items", data) if isinstance(data, dict) else data
    if not items:
        pytest.skip("No jobs available")
    job_id = items[0].get("job_id", items[0].get("id"))
    r2 = client.get(f"/api/v1/jobs/{job_id}/attempts")
    assert r2.status_code == 200


@skip_if_no_server
def test_09_job_logs(client):
    r = client.get("/api/v1/jobs")
    assert r.status_code == 200
    data = r.json()
    items = data.get("items", data) if isinstance(data, dict) else data
    if not items:
        pytest.skip("No jobs available")
    job_id = items[0].get("job_id", items[0].get("id"))
    r2 = client.get(f"/api/v1/jobs/{job_id}/logs")
    assert r2.status_code == 200


@skip_if_no_server
def test_10_memory_list(client):
    r = client.get("/api/v1/memories")
    assert r.status_code == 200


@skip_if_no_server
def test_11_knowledge_list(client):
    r = client.get("/api/v1/knowledge")
    assert r.status_code == 200


@skip_if_no_server
def test_12_search(client):
    payload = {"query": "meeting summary", "top_k": 5}
    r = client.post("/api/v1/search", json=payload)
    assert r.status_code in (200, 404)


@skip_if_no_server
def test_13_observability(client):
    r = client.get("/api/v1/observability")
    assert r.status_code == 200


@skip_if_no_server
def test_14_events_list(client):
    r = client.get("/api/v1/events")
    assert r.status_code == 200
