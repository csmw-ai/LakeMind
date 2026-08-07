#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
cd "$REPO_DIR"

# ─── 颜色 ───
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
step() { echo -e "\n${GREEN}=== $1 ===${NC}"; }

# ─── 1. 前置检查 ───
step "1/6 前置检查"
command -v docker >/dev/null 2>&1 || fail "Docker 未安装。请先安装 Docker: https://docs.docker.com/get-docker/"
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 未安装"
ok "Docker + Compose 已就绪"

# ─── 2. .env 检查 ───
step "2/6 环境配置"
if [ ! -f .env ]; then
    python3 scripts/init_env.py
    fail "请编辑 .env 填入 MAAS_API_KEY 后重新运行本脚本"
fi
grep -q 'MAAS_API_KEY=<' .env 2>/dev/null && fail "请在 .env 中填入 MAAS_API_KEY（你的 LLM API Key）"
ok ".env 已配置"

# ─── 3. 模型检查 ───
step "3/6 模型检查"
ASR_MODEL="LakeMindModelServing/data/asr-models/asr/sensevoice-small"
EMBED_CACHE="LakeMindModelServing/data/fastembed_cache"
if [ -d "$ASR_MODEL" ] && [ -d "$EMBED_CACHE" ]; then
    ok "模型已存在，跳过下载"
else
    warn "模型未找到，需要下载（约 1GB，首次约 5-10 分钟）"
    if [ "${1:-}" = "--skip-models" ]; then
        warn "跳过模型下载（--skip-models）"
    else
        pip3 install modelscope fastembed 2>/dev/null || fail "无法安装 modelscope/fastembed，请检查 Python 环境"
        python3 scripts/download_models.py || fail "模型下载失败"
        ok "模型下载完成"
    fi
fi

# ─── 4. 拉取镜像 ───
step "4/6 拉取镜像（GHCR 公开镜像，无需登录）"
docker compose --env-file .env pull 2>&1 || warn "部分镜像拉取失败，尝试继续"
ok "镜像就绪"

# ─── 5. 启动 ───
step "5/6 启动 LakeMind"
docker compose --env-file .env up -d --no-build
ok "容器已启动"

# ─── 6. 等待健康 ───
step "6/6 等待健康检查"
echo "等待所有服务就绪（最多 180 秒）..."
for i in $(seq 1 36); do
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
        ok "所有容器健康"
        break
    fi
    printf "  [%2d/36] 等待: %s\r" "$i" "$(echo $UNHEALTHY | tr '\n' ' ')"
    sleep 5
done

# ─── 验证 ───
echo ""
HEALTH=$(curl -sf http://localhost:10823/api/v1/system/health 2>/dev/null) && ok "Server API 健康" || warn "Server API 未就绪"

echo ""
echo "════════════════════════════════════════"
echo -e "${GREEN}LakeMind 部署完成！${NC}"
echo "════════════════════════════════════════"
echo "  ControlCenter:  http://localhost:3000"
echo "  Server API:     http://localhost:10823"
echo "  ModelServing:   http://localhost:10824"
echo "  AssetMCP:       http://localhost:8401"
echo "  DataMCP:        http://localhost:8402"
echo "  AdminMCP:       http://localhost:8403"
echo "════════════════════════════════════════"
echo ""
echo "验证: ./scripts/healthcheck.sh"
echo "停止: docker compose --env-file .env down"
