#!/bin/sh
set -e

echo "=== Meeting Agent v0.2.0 starting ==="

retry() {
    _max=$1
    _delay=$2
    shift 2
    _i=1
    while true; do
        if "$@"; then return 0; fi
        if [ "$_i" -ge "$_max" ]; then
            echo "  [FAILED] after $_max attempts: $*"
            return 1
        fi
        echo "  [retry $_i/$_max] waiting ${_delay}s..."
        sleep "$_delay"
        _i=$((_i + 1))
    done
}

echo "[1/3] Seeding model profiles..."
retry 5 5 python scripts/seed_models.py || echo "  [WARN] seed_models failed — LLM profiles may be missing"

echo "[2/3] Publishing skill..."
retry 5 5 python scripts/publish_skill.py || echo "  [WARN] publish_skill failed — ASR jobs will fail until skill is uploaded"

echo "[3/3] Starting backend..."
cd backend
exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-9100}
