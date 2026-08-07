#!/usr/bin/env python3
"""LakeMind .env 初始化 — 自动生成密钥，跨平台（不依赖 openssl）。"""
import base64
import secrets
import sys
from pathlib import Path


def main():
    repo = Path(__file__).resolve().parent.parent
    example = repo / ".env.example"
    env = repo / ".env"

    if env.exists():
        overwrite = input(f"{env} 已存在，覆盖？[y/N] ")
        if overwrite.lower() != "y":
            print("已取消。")
            return

    content = example.read_text(encoding="utf-8")

    master_key = base64.b64encode(secrets.token_bytes(32)).decode()
    api_key = secrets.token_hex(32)

    content = content.replace(
        "<run: openssl rand -base64 32>", master_key
    ).replace(
        "<run: openssl rand -hex 32>", api_key
    )

    env.write_text(content, encoding="utf-8")
    print(f"\n已生成 {env}")
    print(f"  LAKEMIND_MASTER_KEY = {master_key[:16]}...")
    print(f"  SERVER_API_KEY      = {api_key[:16]}...")
    print(f"\n下一步：编辑 .env 填入 MAAS_API_KEY（你的 LLM API Key），然后运行：")
    print(f"  ./scripts/deploy.sh    (Linux/Mac)")
    print(f"  .\\scripts\\deploy.ps1  (Windows)")


if __name__ == "__main__":
    main()
