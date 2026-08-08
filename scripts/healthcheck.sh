#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
FAIL_COUNT=0

echo "=== Containers ==="
docker compose --env-file .env ps 2>/dev/null || { echo "  [FAIL] compose not started"; FAIL_COUNT=$((FAIL_COUNT+1)); }

echo ""
echo "=== Server API ==="
HEALTH=$(curl -sf http://localhost:10823/api/v1/system/health 2>/dev/null)
if [ -n "$HEALTH" ]; then
    echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH"
else
    echo "  [FAIL] Server API unreachable"; FAIL_COUNT=$((FAIL_COUNT+1))
fi

echo ""
echo "=== MCP Health ==="
for port in 8401 8402 8403; do
    if curl -sf "http://localhost:$port/health" >/dev/null 2>&1; then
        echo "  MCP :$port -- OK"
    else
        echo "  MCP :$port -- FAIL"; FAIL_COUNT=$((FAIL_COUNT+1))
    fi
done

echo ""
echo "=== Ray Serve ==="
RAY_OUTPUT=$(docker exec lakemind-ray-head python3 -c "
import ray; ray.init(address='auto', ignore_reinit_error=True, log_to_driver=False)
from ray import serve
s = serve.status()
if not s.applications:
    print('  [WARN] No Serve application running')
for n, a in s.applications.items():
    print(f'  {n}: {a.status.name}')
" 2>/dev/null || echo "  [FAIL] Ray unreachable")
echo "$RAY_OUTPUT"
echo "$RAY_OUTPUT" | grep -q "RUNNING" || FAIL_COUNT=$((FAIL_COUNT+1))

echo ""
echo "=== ControlCenter ==="
curl -sf http://localhost:3000/health >/dev/null 2>&1 && echo "  OK" || { echo "  FAIL"; FAIL_COUNT=$((FAIL_COUNT+1)); }

echo ""
echo "=== ModelServing ==="
curl -sf http://localhost:10824/health/ready >/dev/null 2>&1 && echo "  OK" || { echo "  FAIL"; FAIL_COUNT=$((FAIL_COUNT+1)); }

echo ""
echo "=== Meeting Agent ==="
if curl -sf http://localhost:9100/api/health >/dev/null 2>&1; then
    echo "  OK"
elif curl -sf http://localhost:9100 >/dev/null 2>&1; then
    echo "  OK (web UI)"
else
    echo "  FAIL"; FAIL_COUNT=$((FAIL_COUNT+1))
fi

echo ""
if [ "$FAIL_COUNT" -eq 0 ]; then
    echo "All checks passed."
else
    echo "$FAIL_COUNT check(s) failed."
fi
exit "$FAIL_COUNT"
