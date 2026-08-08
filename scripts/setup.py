#!/usr/bin/env python3
"""LakeMind setup — generate .env with auto-generated secrets.

Usage:
    python scripts/setup.py

Prompts:
    1. LLM API Key (MAAS_API_KEY)

Then prints the commands to start LakeMind.
"""
import base64
import secrets
import sys
from pathlib import Path


def main():
    repo = Path(__file__).resolve().parent.parent
    example = repo / ".env.example"
    env = repo / ".env"

    if not example.exists():
        print(f"ERROR: {example} not found")
        sys.exit(1)

    if env.exists():
        print(f".env already exists. Delete it first if you want to regenerate.")
        sys.exit(1)

    content = example.read_text(encoding="utf-8")

    master_key = base64.b64encode(secrets.token_bytes(32)).decode()
    server_key = secrets.token_hex(32)
    content = content.replace("<run: openssl rand -base64 32>", master_key)
    content = content.replace("<run: openssl rand -hex 32>", server_key)

    print()
    print("  LakeMind Setup")
    print("  ==============")
    print()
    maas_key = input("  Enter your LLM API Key: ").strip()
    if not maas_key:
        print("  ERROR: API Key is required.")
        sys.exit(1)
    content = content.replace("MAAS_API_KEY=<your-llm-api-key>", f"MAAS_API_KEY={maas_key}")

    env.write_text(content, encoding="utf-8")
    print()
    print(f"  [OK] .env generated")
    print(f"       LAKEMIND_MASTER_KEY = {master_key[:16]}...")
    print(f"       SERVER_API_KEY      = {server_key[:16]}...")
    print(f"       MAAS_API_KEY        = {maas_key[:8]}...")
    print()
    print("  Next steps:")
    print("    docker compose --env-file .env pull")
    print("    docker compose --env-file .env up -d")
    print("    docker compose --env-file .env -f examples/meeting-agent/docker-compose.yml up -d")
    print("    python scripts/health.py")
    print()


if __name__ == "__main__":
    main()
