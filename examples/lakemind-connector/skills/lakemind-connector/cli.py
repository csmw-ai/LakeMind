"""
lakemind-connector Skill — CLI 入口

Agent 检索到本 Skill 后，在自身运行时执行此代码。

用法:
    python cli.py ingest                 # 入库知识 + 记忆
    python cli.py search <query>         # 语义检索知识
    python cli.py scan                   # 浏览全部概念
    python cli.py memories               # 列出记忆
    python cli.py remember <text>        # 存入新记忆
    python cli.py verify                 # 验证入库结果
    python cli.py tools                  # 列出 MCP 工具
    python cli.py health                 # 平台健康检查 (含 Ray)
    python cli.py jobs [status]          # 列出 Ray jobs
    python cli.py job-status <job_id>    # 查询 job 状态
    python cli.py asr <audio_file>       # ASR 语音识别
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys

from connector import LakeMindConnector
from cognition import KNOWLEDGE_BASE, KNOWLEDGE_CONCEPTS, MEMORY_MESSAGES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("lakemind-connector")


def _header(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


async def cmd_ingest(conn: LakeMindConnector):
    _header("Ingest Knowledge")
    concepts = []
    for i, c in enumerate(KNOWLEDGE_CONCEPTS, 1):
        concepts.append({
            "frontmatter": {"type": c["type"], "title": c["title"], "tags": c["tags"]},
            "body": c["body"],
        })
        print(f"  prepared {i}/{len(KNOWLEDGE_CONCEPTS)}: {c['title'][:50]}...")

    try:
        count = await conn.store_knowledge(KNOWLEDGE_BASE, concepts)
        print(f"  [OK] stored {count} concepts -> kb_{KNOWLEDGE_BASE}")
    except Exception as e:
        print(f"  [FAIL] {e}")

    _header("Ingest Memories")
    for i, msg in enumerate(MEMORY_MESSAGES, 1):
        try:
            await conn.add_memory(
                messages=[msg],
                metadata={"source": "lakemind-connector-skill", "session": "lakemind-building"},
            )
            print(f"  [OK] memory {i}/{len(MEMORY_MESSAGES)}")
        except Exception as e:
            print(f"  [FAIL] memory {i}: {e}")

    await cmd_verify(conn)


async def cmd_search(conn: LakeMindConnector, query: str):
    _header(f"Search: {query}")
    try:
        hits = await conn.search_knowledge(query, KNOWLEDGE_BASE, top_k=5)
    except Exception as e:
        print(f"  [FAIL] {e}")
        return
    print(f"  hits: {len(hits)}")
    for h in hits:
        title = h.get("title", "")
        dist = h.get("_distance", 0)
        ctype = h.get("type", "")
        print(f"    [distance={dist:.4f}] ({ctype}) {title[:60]}")


async def cmd_scan(conn: LakeMindConnector):
    _header(f"Scan: kb_{KNOWLEDGE_BASE}")
    try:
        rows = await conn.scan_knowledge(KNOWLEDGE_BASE, limit=100)
    except Exception as e:
        print(f"  [FAIL] {e}")
        return
    print(f"  total: {len(rows)}")
    for r in rows:
        print(f"    [{r.get('type', '')}] {r.get('title', '')}")


async def cmd_memories(conn: LakeMindConnector):
    _header("Memories")
    try:
        r = await conn.list_memory(page=1, page_size=20)
    except Exception as e:
        print(f"  [FAIL] {e}")
        return
    items = r.get("results", r.get("items", []))
    print(f"  total: {r.get('count', r.get('total', len(items)))}")
    for m in items:
        mid = m.get("id", m.get("memory_id", "?"))
        content = m.get("memory", m.get("content", m.get("text", "")))
        print(f"    [{mid[:8]}] {content[:80] if content else '(empty)'}")


async def cmd_remember(conn: LakeMindConnector, text: str):
    _header("Remember")
    try:
        await conn.add_memory(
            messages=[{"role": "user", "content": text}],
            metadata={"source": "lakemind-connector-skill", "type": "interactive"},
        )
        print(f"  [OK] stored: {text[:60]}...")
    except Exception as e:
        print(f"  [FAIL] {e}")


async def cmd_search_memory(conn: LakeMindConnector, query: str):
    _header(f"Search Memory: {query}")
    try:
        r = await conn.search_memory(query, top_k=5)
    except Exception as e:
        print(f"  [FAIL] {e}")
        return
    results = r.get("results", [])
    print(f"  hits: {len(results)}")
    for m in results:
        score = m.get("score", 0)
        mem = m.get("memory", "")[:60]
        print(f"    [score={score:.4f}] {mem}")


async def cmd_verify(conn: LakeMindConnector):
    _header("Verification: Knowledge Search")
    for q in ["opencode AI agent", "LakeMind MCP", "meeting agent", "FunASR", "LanceDB"]:
        await cmd_search(conn, q)

    _header("Verification: Memory Search")
    for q in ["verification", "meeting agent", "ASR debugging", "opencode tenant"]:
        await cmd_search_memory(conn, q)

    _header("Knowledge Base Status")
    try:
        kbs = await conn.list_knowledge_bases()
        print(f"  knowledge bases: {kbs}")
        info = await conn.describe_knowledge(KNOWLEDGE_BASE)
        print(f"  kb_{KNOWLEDGE_BASE}: concept_count={info.get('concept_count', '?')}")
    except Exception as e:
        print(f"  [FAIL] {e}")
    await cmd_memories(conn)


async def cmd_tools(conn: LakeMindConnector):
    _header("MCP Tools")
    try:
        tools = await conn.list_mcp_tools()
        for name, tool_list in tools.items():
            print(f"  {name}: {len(tool_list)} tools")
            for t in tool_list:
                print(f"    - {t}")
    except Exception as e:
        print(f"  [FAIL] {e}")


async def cmd_health(conn: LakeMindConnector):
    _header("Platform Health")
    try:
        r = await conn.check_health()
        print(f"  {json.dumps(r, indent=2, ensure_ascii=False)}")
    except Exception as e:
        print(f"  [FAIL] {e}")


async def cmd_jobs(conn: LakeMindConnector, status: str = ""):
    _header(f"Ray Jobs{f' (status={status})' if status else ''}")
    try:
        r = await conn.list_jobs(status=status)
        jobs = r.get("jobs", r.get("results", []))
        print(f"  total: {len(jobs)}")
        for j in jobs[:20]:
            jid = j.get("job_id", "?")
            s = j.get("status", "?")
            name = j.get("job_name", j.get("entrypoint", "?"))
            print(f"    [{jid[:12]}] {s:12s} {name[:50]}")
    except Exception as e:
        print(f"  [FAIL] {e}")


async def cmd_job_status(conn: LakeMindConnector, job_id: str):
    _header(f"Job Status: {job_id}")
    try:
        r = await conn.get_job_status(job_id)
        print(f"  {json.dumps(r, indent=2, ensure_ascii=False)}")
    except Exception as e:
        print(f"  [FAIL] {e}")


async def cmd_asr(conn: LakeMindConnector, audio_file: str):
    _header(f"ASR: {audio_file}")
    try:
        with open(audio_file, "rb") as f:
            audio = f.read()
        result = await conn.asr(audio)
        raw_text = result.get("text", "")
        clean_text = LakeMindConnector.clean_asr_text(raw_text)
        print(f"  raw: {raw_text[:100]}")
        print(f"  clean: {clean_text[:100]}")
    except Exception as e:
        print(f"  [FAIL] {e}")


COMMANDS = {
    "ingest": cmd_ingest,
    "search": cmd_search,
    "scan": cmd_scan,
    "memories": cmd_memories,
    "remember": cmd_remember,
    "search-memory": cmd_search_memory,
    "verify": cmd_verify,
    "tools": cmd_tools,
    "health": cmd_health,
    "jobs": cmd_jobs,
    "job-status": cmd_job_status,
    "asr": cmd_asr,
}


async def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "ingest"
    handler = COMMANDS.get(cmd)
    if not handler:
        print(f"Available: {', '.join(COMMANDS.keys())}")
        sys.exit(1)

    conn = LakeMindConnector()
    try:
        await handler(conn, *sys.argv[2:])
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
