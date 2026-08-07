#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "=== 容器状态 ==="
docker compose --env-file .env ps 2>/dev/null || echo "  compose 未启动"

echo ""
echo "=== Server API 引擎 ==="
HEALTH=$(curl -sf http://localhost:10823/api/v1/system/health 2>/dev/null)
if [ -n "$HEALTH" ]; then
    echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH"
else
    echo "  [FAIL] Server API 不可达"
fi

echo ""
echo "=== MCP 健康 ==="
for port in 8401 8402 8403; do
    if curl -sf "http://localhost:$port/health" >/dev/null 2>&1; then
        echo "  MCP :$port — OK"
    else
        echo "  MCP :$port — FAIL"
    fi
done

echo ""
echo "=== Ray Serve ==="
docker exec lakemind-ray-head python3 -c "
import ray; ray.init(address='auto', ignore_reinit_error=True)
from ray import serve
s = serve.status()
if not s.applications:
    print('  [WARN] 无 Serve application 运行中')
for n, a in s.applications.items():
    print(f'  {n}: {a.status.name}')
" 2>/dev/null || echo "  [FAIL] Ray 不可达"

echo ""
echo "=== ControlCenter ==="
curl -sf http://localhost:3000/health >/dev/null 2>&1 && echo "  OK" || echo "  FAIL"

echo ""
echo "=== ModelServing ==="
curl -sf http://localhost:10824/health/ready >/dev/null 2>&1 && echo "  OK" || echo "  FAIL"
