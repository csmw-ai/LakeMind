"""WP8-T03: Security acceptance scenarios — 6 tests.

Requires a running LakeMind server with at least two tenant tokens configured.
"""
import pytest
import httpx

CONTROL_PLANE = "http://127.0.0.1:10823"

try:
    _health = httpx.get(f"{CONTROL_PLANE}/api/v1/health", timeout=3.0)
    _SERVER_UP = _health.status_code == 200
except Exception:
    _SERVER_UP = False

skip_if_no_server = pytest.mark.skipif(not _SERVER_UP, reason="LakeMind server not running on :10823")


@skip_if_no_server
def test_cross_tenant_isolation(tenant_a_client, tenant_b_client):
    r_a = tenant_a_client.post("/api/v1/assets", json={
        "name": "e2e-isolation-test",
        "asset_type": "raw_input",
        "content": "tenant-a-secret-data",
    })
    if r_a.status_code not in (200, 201):
        pytest.skip("Cannot create asset for isolation test")
    data = r_a.json()
    asset_id = data.get("asset_id", data.get("id"))

    r_b = tenant_b_client.get(f"/api/v1/assets/{asset_id}")
    assert r_b.status_code in (403, 404), f"Tenant B should not access tenant A's asset, got {r_b.status_code}"


@skip_if_no_server
def test_forged_header_rejected():
    client = httpx.Client(
        base_url=CONTROL_PLANE,
        headers={"Authorization": "Bearer forged-invalid-token-xyz"},
        timeout=10.0,
    )
    r = client.get("/api/v1/assets")
    assert r.status_code in (401, 403), f"Forged token should be rejected, got {r.status_code}"


@skip_if_no_server
def test_unauthorized_skill_rejected(tenant_a_client):
    r = tenant_a_client.post("/api/v1/jobs", json={
        "skill_ref": "nonexistent-skill-xyz",
        "inputs": {},
    })
    assert r.status_code in (400, 404, 422), f"Nonexistent skill should be rejected, got {r.status_code}"


@skip_if_no_server
def test_no_auth_returns_401():
    client = httpx.Client(base_url=CONTROL_PLANE, timeout=10.0)
    r = client.get("/api/v1/assets")
    assert r.status_code in (401, 403), f"Missing auth should be rejected, got {r.status_code}"


@skip_if_no_server
def test_secret_not_leaked_in_response(tenant_a_client):
    r = tenant_a_client.get("/api/v1/secrets")
    if r.status_code != 200:
        pytest.skip("No secrets endpoint or no access")
    data = r.json()
    items = data if isinstance(data, list) else data.get("items", [])
    for item in items:
        for key, val in item.items():
            if isinstance(val, str) and val.startswith("enc:"):
                pytest.fail(f"Encrypted secret value leaked in response field '{key}'")


@skip_if_no_server
def test_ray_dashboard_not_exposed():
    try:
        r = httpx.get("http://127.0.0.1:8265", timeout=3.0)
        assert r.status_code in (401, 403, 404), f"Ray dashboard should not be publicly accessible, got {r.status_code}"
    except httpx.ConnectError:
        pass
    except httpx.TimeoutException:
        pass
