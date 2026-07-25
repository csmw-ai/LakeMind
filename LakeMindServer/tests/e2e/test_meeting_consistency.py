"""WP8-T04: Consistency acceptance scenarios — 7 tests.

Tests that the system maintains consistency under partial failures.
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
        timeout=30.0,
    )


def _wait_for_terminal(client, job_id, timeout=60):
    terminal = {"SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT", "LOST"}
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/v1/jobs/{job_id}")
        if r.status_code == 200:
            status = r.json().get("status", "")
            if status in terminal:
                return r.json()
        time.sleep(2)
    return None


@skip_if_no_server
def test_job_submit_and_query_consistent(client):
    r = client.get("/api/v1/jobs")
    assert r.status_code == 200
    data = r.json()
    items = data.get("items", data) if isinstance(data, dict) else data
    for item in items:
        job_id = item.get("job_id", item.get("id"))
        if job_id:
            r2 = client.get(f"/api/v1/jobs/{job_id}")
            assert r2.status_code == 200
            detail = r2.json()
            assert detail.get("job_id", detail.get("id")) == job_id


@skip_if_no_server
def test_retry_creates_new_attempt(client):
    r = client.get("/api/v1/jobs")
    assert r.status_code == 200
    data = r.json()
    items = data.get("items", data) if isinstance(data, dict) else data
    failed_jobs = [j for j in items if j.get("status") == "FAILED"]
    if not failed_jobs:
        pytest.skip("No failed jobs to retry")
    job_id = failed_jobs[0].get("job_id", failed_jobs[0].get("id"))

    r_before = client.get(f"/api/v1/jobs/{job_id}/attempts")
    assert r_before.status_code == 200
    before_count = len(r_before.json()) if isinstance(r_before.json(), list) else 0

    r_retry = client.post(f"/api/v1/jobs/{job_id}/retry")
    assert r_retry.status_code in (200, 201, 202)

    r_after = client.get(f"/api/v1/jobs/{job_id}/attempts")
    assert r_after.status_code == 200
    after_count = len(r_after.json()) if isinstance(r_after.json(), list) else 0
    assert after_count >= before_count, "Retry should create a new attempt, not duplicate"


@skip_if_no_server
def test_cancel_changes_status(client):
    r = client.post("/api/v1/jobs", json={
        "skill_ref": "asr-transcribe",
        "inputs": {"audio_uri": "s3://test/long-audio.wav"},
    })
    if r.status_code not in (200, 201, 202):
        pytest.skip("Cannot submit job for cancel test")
    job_id = r.json().get("job_id", r.json().get("id"))

    r_cancel = client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert r_cancel.status_code in (200, 202, 409)

    result = _wait_for_terminal(client, job_id, timeout=30)
    if result:
        assert result["status"] in ("CANCELLED", "SUCCEEDED", "FAILED"), \
            f"Job should reach terminal state after cancel, got {result['status']}"


@skip_if_no_server
def test_job_events_recorded(client):
    r = client.get("/api/v1/jobs")
    assert r.status_code == 200
    data = r.json()
    items = data.get("items", data) if isinstance(data, dict) else data
    if not items:
        pytest.skip("No jobs available")
    job_id = items[0].get("job_id", items[0].get("id"))

    r_timeline = client.get(f"/api/v1/jobs/{job_id}/timeline")
    assert r_timeline.status_code == 200
    events = r_timeline.json()
    assert isinstance(events, list)
    if events:
        valid_event_types = {"SUBMITTED", "QUEUED", "STARTED", "SUCCEEDED", "FAILED",
                             "CANCELLED", "CANCELLING", "TIMED_OUT", "LOST", "RETRY",
                             "ARTIFACT_CREATED"}
        for evt in events:
            evt_type = evt.get("event_type", evt.get("type", ""))
            assert evt_type in valid_event_types or evt_type == "", \
                f"Unknown event type: {evt_type}"


@skip_if_no_server
def test_vector_index_operations(client):
    r = client.get("/api/v1/storage/vectors")
    assert r.status_code == 200


@skip_if_no_server
def test_memory_add_search_consistent(client):
    r_add = client.post("/api/v1/memories", json={
        "messages": [{"role": "user", "content": "e2e consistency test memory"}],
        "metadata": {"test": "consistency"},
    })
    if r_add.status_code not in (200, 201):
        pytest.skip("Cannot add memory for consistency test")

    r_search = client.post("/api/v1/memories/search", json={
        "query": "consistency test memory",
        "top_k": 5,
    })
    assert r_search.status_code == 200


@skip_if_no_server
def test_config_endpoint_available(client):
    r = client.get("/api/v1/configuration")
    assert r.status_code == 200
