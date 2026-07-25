from __future__ import annotations
import os
import asyncio
import json
import logging
import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from steward_service import StewardService

logger = logging.getLogger(__name__)
app = FastAPI(title="LakeMind Steward", version="2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_steward = StewardService()

_CONTROL_PLANE = os.environ.get("LAKEMIND_CONTROL_PLANE", "http://lakemind-server:10823")
_STEWARD_TOKEN = os.environ.get("LAKEMIND_STEWARD_TOKEN", "")
_MODEL_SERVING = os.environ.get("LAKEMIND_MODEL_SERVING", "http://lakemind-model-serving:10824")
_MODEL_SERVING_KEY = os.environ.get("MODELSERVING_API_KEY", "lakemind-modelserving-key")
_LLM_MODEL = os.environ.get("STEWARD_LLM_MODEL", "deepseek-v4-flash")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "steward"}


@app.get("/inspection")
async def get_inspection():
    return await _steward.inspect()


@app.get("/inspection/last")
async def get_last_inspection():
    return _steward.get_last_inspection() or {"message": "no_inspection_yet"}


@app.post("/suggest")
async def suggest_action(request: Request):
    body = await request.json()
    return await _steward.suggest_action(body)


async def _fetch_context() -> str:
    headers = {"Authorization": f"Bearer {_STEWARD_TOKEN}"}
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            client.get(f"{_CONTROL_PLANE}/api/v1/jobs", params={"status": "FAILED", "page_size": "10"}, headers=headers, timeout=10.0),
            client.get(f"{_CONTROL_PLANE}/api/v1/jobs", params={"status": "RUNNING", "page_size": "1"}, headers=headers, timeout=10.0),
            client.get(f"{_CONTROL_PLANE}/api/v1/jobs", params={"status": "SUCCEEDED", "page_size": "1"}, headers=headers, timeout=10.0),
            client.get(f"{_CONTROL_PLANE}/api/v1/jobs", params={"page_size": "1"}, headers=headers, timeout=10.0),
            client.get(f"{_CONTROL_PLANE}/api/v1/instances", headers=headers, timeout=5.0),
            client.get(f"{_CONTROL_PLANE}/api/v1/observability/metrics", params={"name": "cpu.usage"}, headers=headers, timeout=5.0),
            client.get(f"{_CONTROL_PLANE}/api/v1/observability/metrics", params={"name": "memory.usage"}, headers=headers, timeout=5.0),
            return_exceptions=True,
        )

    parts: list[str] = []

    def _safe(idx):
        r = results[idx]
        if isinstance(r, Exception) or r.status_code != 200:
            return None
        try:
            return r.json()
        except Exception:
            return None

    failed = _safe(0)
    running = _safe(1)
    succeeded = _safe(2)
    total = _safe(3)
    instances = _safe(4)
    cpu = _safe(5)
    mem = _safe(6)

    parts.append("## 平台实时数据")
    if total:
        parts.append(f"- 累计任务: {total.get('total', 0)}")
    if succeeded:
        parts.append(f"- 已完成: {succeeded.get('total', 0)}")
    if failed:
        parts.append(f"- 失败: {failed.get('total', 0)}")
        items = failed.get("items", [])
        if items:
            parts.append("  最近失败任务:")
            for j in items[:5]:
                parts.append(f"    - {j.get('job_id')} ({j.get('job_name', '?')}) 创建于 {j.get('created_at', '?')}")
    if running:
        parts.append(f"- 运行中: {running.get('total', 0)}")

    if instances:
        if isinstance(instances, dict):
            inst_list = instances.get("items", [])
        else:
            inst_list = instances if isinstance(instances, list) else []
        unhealthy = [i for i in inst_list if isinstance(i, dict) and i.get("health_status") not in ("healthy",)]
        parts.append(f"- 服务实例: 共 {len(inst_list)} 个, 不健康 {len(unhealthy)} 个")
        for i in unhealthy:
            parts.append(f"    - {i.get('instance_id', '?')} 状态={i.get('health_status', '?')}")

    if cpu and cpu.get("items"):
        parts.append(f"- CPU 使用率: {cpu['items'][0].get('value', '?')}%")
    if mem and mem.get("items"):
        parts.append(f"- 内存使用率: {mem['items'][0].get('value', '?')}%")

    return "\n".join(parts)


async def _llm_chat(message: str, context: str) -> str:
    system_prompt = (
        "你是 LakeMind Steward，LakeMind 认知资产存取平台的运维助手。\n\n"
        "职责：回答平台健康、任务状态、服务状态相关问题；帮助调查失败任务；建议运维操作。\n"
        "要求：用中文回答；简洁、具体、有数据支撑；如果数据不足，说明需要什么信息。\n\n"
        f"{context}"
    )

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_MODEL_SERVING}/v1/chat/completions",
            headers={"Authorization": f"Bearer {_MODEL_SERVING_KEY}", "Content-Type": "application/json"},
            json={
                "model": _LLM_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ],
                "max_tokens": 800,
                "temperature": 0.3,
            },
            timeout=30.0,
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        logger.error("LLM call failed: %s %s", resp.status_code, resp.text[:200])
        return f"LLM 调用失败 (HTTP {resp.status_code})"


@app.post("/chat")
async def chat(request: Request):
    body = await request.json()
    message = body.get("message", "")

    if not message.strip():
        return {"response": "请输入您的问题。"}

    context = await _fetch_context()

    try:
        response_text = await _llm_chat(message, context)
    except Exception as e:
        logger.exception("Chat failed")
        response_text = f"处理失败: {e}"

    return {"response": response_text}
