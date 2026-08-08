#!/usr/bin/env python3
"""LakeMind health check — verify all services are running.

Usage:
    python scripts/health.py

Checks:
    1. All containers healthy
    2. Server API engines (10)
    3. MCP endpoints (3)
    4. Ray Serve apps (asr + embedding)
    5. ControlCenter, ModelServing, Meeting Agent

Exit 0 = all pass, exit 1 = some fail.
"""
import subprocess
import sys
import urllib.request
import json


GREEN = "\033[0;32m"
RED = "\033[0;31m"
NC = "\033[0m"
fails = 0


def ok(msg):
    print(f"  {GREEN}[OK]{NC} {msg}")


def fail(msg):
    global fails
    fails += 1
    print(f"  {RED}[FAIL]{NC} {msg}")


def http_get(url, timeout=5):
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode()
    except Exception:
        return None


def docker_exec(container, cmd):
    try:
        r = subprocess.run(
            ["docker", "exec", container, "python", "-c", cmd],
            capture_output=True, text=True, timeout=30
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def check_containers():
    print("=== Containers ===")
    r = subprocess.run(
        ["docker", "compose", "--env-file", ".env", "ps", "--format", "json"],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        fail("docker compose ps failed")
        return
    names = []
    unhealthy = []
    for line in r.stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            c = json.loads(line)
            names.append(c["Name"])
            if c.get("State") == "running" and c.get("Health") != "healthy":
                unhealthy.append(c["Name"])
        except json.JSONDecodeError:
            pass
    if not names:
        fail("No containers running")
        return
    if unhealthy:
        fail(f"Unhealthy: {', '.join(unhealthy)}")
    else:
        ok(f"{len(names)} containers healthy")


def check_engines():
    print("\n=== Server API ===")
    resp = http_get("http://localhost:10823/api/v1/system/health")
    if not resp:
        fail("Server API unreachable")
        return
    try:
        data = json.loads(resp)
        true_count = sum(1 for v in data.values() if v is True)
        if true_count == len(data):
            ok(f"{true_count}/{len(data)} engines online")
        else:
            fail(f"{true_count}/{len(data)} engines online")
    except json.JSONDecodeError:
        fail(f"Bad response: {resp[:100]}")


def check_mcp():
    print("\n=== MCP ===")
    for port in (8401, 8402, 8403):
        if http_get(f"http://localhost:{port}/health"):
            ok(f"MCP :{port}")
        else:
            fail(f"MCP :{port}")


def check_ray_serve():
    print("\n=== Ray Serve ===")
    output = docker_exec("lakemind-ray-head", """
import ray; ray.init(address='auto', ignore_reinit_error=True, log_to_driver=False)
from ray import serve
s = serve.status()
for n, a in sorted(s.applications.items()):
    print(f'{n}: {a.status.name}')
""")
    if not output:
        fail("Ray unreachable")
        return
    for line in output.strip().split("\n"):
        if "RUNNING" in line:
            ok(line)
        else:
            fail(line)


def check_url(name, url):
    if http_get(url):
        ok(name)
    else:
        fail(name)


def main():
    check_containers()
    check_engines()
    check_mcp()
    check_ray_serve()
    print("\n=== Services ===")
    check_url("ControlCenter  :3000", "http://localhost:3000/health")
    check_url("ModelServing   :10824", "http://localhost:10824/health/ready")
    check_url("Meeting Agent  :9100", "http://localhost:9100/api/health")

    print()
    if fails == 0:
        print(f"{GREEN}All checks passed.{NC}")
    else:
        print(f"{RED}{fails} check(s) failed.{NC}")
    sys.exit(fails)


if __name__ == "__main__":
    main()
