"""E2E test fixtures — skip gracefully when server is not running."""
import pytest
import httpx

CONTROL_PLANE = "http://127.0.0.1:10823"


def _server_available() -> bool:
    try:
        r = httpx.get(f"{CONTROL_PLANE}/api/v1/health", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


SERVER_AVAILABLE = _server_available()

skip_if_no_server = pytest.mark.skipif(
    not SERVER_AVAILABLE,
    reason="LakeMind server not running on :10823",
)


@pytest.fixture
def tenant_a_client():
    return httpx.Client(
        base_url=CONTROL_PLANE,
        headers={"Authorization": "Bearer test-token-tenant-a"},
        timeout=30.0,
    )


@pytest.fixture
def tenant_b_client():
    return httpx.Client(
        base_url=CONTROL_PLANE,
        headers={"Authorization": "Bearer test-token-tenant-b"},
        timeout=30.0,
    )


@pytest.fixture
def admin_client():
    return httpx.Client(
        base_url=CONTROL_PLANE,
        headers={"Authorization": "Bearer ljLH3bvzIFjG4r3zeCP6AsHsGEnbmAQY_Hi3dW7du5o"},
        timeout=30.0,
    )
