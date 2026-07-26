"""
setup_tenant.py — 创建 opencode 租户 + 签发 Token + 提示配置 AssetMCP

用法:
    python scripts/setup_tenant.py
"""

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from opencode_lakemind.connector import LakeMindConnector


async def main():
    conn = LakeMindConnector()
    try:
        print("=== Create Tenant ===")
        try:
            r = await conn.create_tenant("opencode", "OpenCode AI Agent", "opencode AI coding agent")
            print(f"  [OK] {r}")
        except Exception as e:
            print(f"  [SKIP] may already exist: {e}")

        print("\n=== Issue Token ===")
        try:
            r = await conn.issue_token("opencode", "opencode-agent", ["asset:read", "asset:write"])
            print(f"  [OK] token: {r['token']}")
            print(f"\n  Add to LakeMindMCP/LakeMindAssetMCP/config/config.yaml:")
            print(f'    - token: "{r["token"]}"')
            print(f'      agent_id: "opencode-agent"')
            print(f'      tenant_id: "opencode"')
            print(f'      scopes: ["asset"]')
            print(f"\n  Then restart AssetMCP: docker restart lakemind-asset-mcp")
        except Exception as e:
            print(f"  [SKIP] may already exist: {e}")

        print("\n=== Platform Health ===")
        try:
            r = await conn.platform_health()
            print(f"  {json.dumps(r, indent=2, ensure_ascii=False)}")
        except Exception as e:
            print(f"  [FAIL] {e}")

        print("\n=== MCP Tools ===")
        try:
            tools = await conn.list_mcp_tools()
            for name, tool_list in tools.items():
                print(f"  {name}: {len(tool_list)} tools")
        except Exception as e:
            print(f"  [FAIL] {e}")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
