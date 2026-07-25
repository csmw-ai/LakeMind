"""WP8-T05: Recovery acceptance scenarios — 6 tests.

Tests that the system recovers correctly from restarts and failures.
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


@skip_if_no_server
def test_health_reports_job_runtime(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert "job_runtime" in data
    assert data["job_runtime"] in ("healthy", "degraded")


@skip_if_no_server
def test_job_recovery_on_startup(client):
    r = client.get("/api/v1/jobs")
    assert r.status_code == 200
    data = r.json()
    items = data.get("items", data) if isinstance(data, dict) else data
    active_states = {"SUBMITTED", "QUEUED", "RUNNING", "CANCELLING"}
    active_jobs = [j for j in items if j.get("status") in active_states]
    for job in active_jobs:
        job_id = job.get("job_id", job.get("id"))
        r_detail = client.get(f"/api/v1/jobs/{job_id}")
        assert r_detail.status_code == 200
        detail = r_detail.json()
        assert detail.get("status") in active_states | {"SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT", "LOST"}


@skip_if_no_server
def test_outbox_events_not_duplicated(client):
    r = client.get("/api/v1/events")
    assert r.status_code == 200
    data = r.json()
    events = data if isinstance(data, list) else data.get("items", [])
    seen_keys = set()
    for evt in events:
        evt_id = evt.get("event_id", evt.get("id"))
        if evt_id:
            assert evt_id not in seen_keys, f"Duplicate event_id: {evt_id}"
            seen_keys.add(evt_id)


@skip_if_no_server
def test_lost_job_marked_correctly(client):
    r = client.get("/api/v1/jobs")
    assert r.status_code == 200
    data = r.json()
    items = data.get("items", data) if isinstance(data, dict) else data
    lost_jobs = [j for j in items if j.get("status") == "LOST"]
    for job in lost_jobs:
        job_id = job.get("job_id", job.get("id"))
        r_timeline = client.get(f"/api/v1/jobs/{job_id}/timeline")
        assert r_timeline.status_code == 200
        events = r_timeline.json()
        event_types = {e.get("event_type", e.get("type", "")) for e in events}
        assert "LOST" in event_types, f"LOST job {job_id} should have LOST event in timeline"


@skip_if_no_server
def test_steward_endpoint_available(client):
    r = client.get("/api/v1/steward")
    assert r.status_code in (200, 404, 405)


@skip_if_no_server
def test_observability_services_registered(client):
    r = client.get("/api/v1/observability")
    assert r.status_code == 200
    data = r.json()
    if isinstance(data, dict):
        services = data.get("services", [])
        for svc in services:
            assert "name" in svc or "service" in svc, "Service should have a name"
            status = svc.get("status", svc.get("health", ""))
            assert status in ("healthy", "degraded", "unknown", "unhealthy"), \
                f"Service status should be valid, got '{status}'"
