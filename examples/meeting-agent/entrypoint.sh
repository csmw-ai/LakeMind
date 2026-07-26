#!/bin/sh
set -e

echo "=== Meeting Agent v0.2.0 starting ==="

echo "[1/3] Seeding model profiles..."
python scripts/seed_models.py || echo "WARNING: seed_models failed, continuing..."

echo "[2/3] Publishing skill..."
python scripts/publish_skill.py || echo "WARNING: publish_skill failed, continuing..."

echo "[3/3] Starting backend..."
cd backend
exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-9100}
