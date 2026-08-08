#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
cd "$REPO_DIR"

# ─── colors ───
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
step() { echo -e "\n${GREEN}=== $1 ===${NC}"; }

# ─── 1. Prerequisites ───
step "1/7 Prerequisites"
command -v docker >/dev/null 2>&1 || fail "Docker not installed. Install Docker first."
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 not installed"
ok "Docker + Compose ready"

# ─── 2. .env check ───
step "2/7 Environment config"
if [ ! -f .env ]; then
    python3 scripts/init_env.py
    fail "Edit .env to fill MAAS_API_KEY, then re-run this script"
fi
grep -q 'MAAS_API_KEY=<' .env 2>/dev/null && fail "Please fill MAAS_API_KEY in .env"
ok ".env configured"

# ─── 3. Model check ───
step "3/7 Model check"
ASR_MODEL="LakeMindModelServing/data/asr-models/asr/sensevoice-small"
EMBED_CACHE="LakeMindModelServing/data/fastembed_cache"
if [ -d "$ASR_MODEL" ] && [ -d "$EMBED_CACHE" ]; then
    ok "Models exist, skip download"
else
    if [ "${1:-}" = "--skip-models" ]; then
        warn "Skip model download"
    else
        warn "Models not found, downloading (~1GB, 5-10 min)..."
        pip3 install modelscope fastembed 2>/dev/null || fail "Cannot install modelscope/fastembed"
        python3 scripts/download_models.py || fail "Model download failed"
        ok "Models downloaded"
    fi
fi

# ─── 4. Pull images ───
step "4/7 Pull images (GHCR public, no login needed)"
echo "  Pulling LakeMind images..."
docker compose --env-file .env pull 2>&1 || warn "Some images failed to pull"
echo "  Pulling meeting-agent image..."
docker compose --env-file .env -f examples/meeting-agent/docker-compose.yml pull 2>&1 || warn "meeting-agent image failed to pull"
ok "Images ready"

# ─── 5. Start LakeMind ───
step "5/7 Start LakeMind"
docker compose --env-file .env up -d --no-build
ok "LakeMind containers started"

# ─── 6. Start meeting-agent ───
step "6/7 Start meeting-agent"
docker compose --env-file .env -f examples/meeting-agent/docker-compose.yml up -d --no-build
ok "meeting-agent started"

# ─── 7. Wait for health ───
step "7/7 Wait for health"
echo "Waiting for all containers (up to 300s)..."
for i in $(seq 1 60); do
    UNHEALTHY=$(docker compose --env-file .env ps --format json 2>/dev/null | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        c = json.loads(line)
        if c.get('Health', 'healthy') != 'healthy' and c.get('State') == 'running':
            print(c['Name'])
    except: pass
" 2>/dev/null)
    if [ -z "$UNHEALTHY" ]; then
        ok "All LakeMind containers healthy"
        break
    fi
    printf "  [%2d/60] waiting: %s\r" "$i" "$(echo $UNHEALTHY | tr '\n' ' ')"
    sleep 5
done

# Wait for Ray Serve apps
echo ""
echo "Waiting for Ray Serve apps (up to 180s)..."
for i in $(seq 1 36); do
    RAY_STATUS=$(docker exec lakemind-ray-head python3 -c "
import ray; ray.init(address='auto', ignore_reinit_error=True, log_to_driver=False)
from ray import serve
s = serve.status()
apps = {n: a.status.name for n, a in s.applications.items()}
print(' '.join(f'{k}={v}' for k, v in apps.items()))
" 2>/dev/null || echo "")
    if echo "$RAY_STATUS" | grep -q "asr-app=RUNNING" && echo "$RAY_STATUS" | grep -q "embedding-app=RUNNING"; then
        ok "Ray Serve apps ready (asr + embedding)"
        break
    fi
    printf "  [%2d/36] %s\r" "$i" "$RAY_STATUS"
    sleep 5
done

# Verify Server API
echo ""
HEALTH=$(curl -sf http://localhost:10823/api/v1/system/health 2>/dev/null) && ok "Server API healthy" || warn "Server API not ready"

echo ""
echo "==================================="
echo -e "${GREEN}LakeMind deployed!${NC}"
echo "==================================="
echo "  Meeting Agent:  http://localhost:9100"
echo "  ControlCenter:  http://localhost:3000"
echo "  Server API:     http://localhost:10823"
echo "  ModelServing:   http://localhost:10824"
echo "  AssetMCP:       http://localhost:8401"
echo "  DataMCP:        http://localhost:8402"
echo "  AdminMCP:       http://localhost:8403"
echo "==================================="
echo ""
echo "Verify: ./scripts/healthcheck.sh"
echo "Stop:   docker compose --env-file .env down && docker compose --env-file .env -f examples/meeting-agent/docker-compose.yml down"
