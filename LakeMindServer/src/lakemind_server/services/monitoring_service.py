from __future__ import annotations
import asyncio
import logging
import os
import psutil
from datetime import datetime, timezone
from ..db import execute, execute_one
from ..services.instance_registry import InstanceRegistry
from ..services.metrics_service import MetricsService

logger = logging.getLogger("lakemind.monitoring")

_KNOWN_SERVICES = [
    {"service_type": "server-api", "version": "2.0.0", "endpoint": "http://lakemind-server-api:10823", "capabilities": ["rest-api"]},
    {"service_type": "asset-mcp", "version": "2.0.0", "endpoint": "http://lakemind-asset-mcp:8401", "capabilities": ["knowledge", "memory", "skills", "ontology"]},
    {"service_type": "data-mcp", "version": "2.0.0", "endpoint": "http://lakemind-data-mcp:8402", "capabilities": ["s3", "sql", "ray-jobs"]},
    {"service_type": "admin-mcp", "version": "2.0.0", "endpoint": "http://lakemind-admin-mcp:8403", "capabilities": ["users", "tenants", "health"]},
    {"service_type": "model-serving", "version": "2.0.0", "endpoint": "http://lakemind-model-serving:10824", "capabilities": ["llm", "embedding", "asr"]},
    {"service_type": "ray", "version": "2.41.0", "endpoint": "http://lakemind-ray-head:8265", "capabilities": ["distributed-compute"]},
    {"service_type": "control-center", "version": "2.1.0", "endpoint": "http://lakemind-control-center:3000", "capabilities": ["ui", "bff", "steward"]},
    {"service_type": "meeting-agent", "version": "0.2.0", "endpoint": "http://meeting-agent:9100", "capabilities": ["meeting-pipeline"]},
]

_INSTANCE_IDS: dict[str, str] = {}


def _probe_health(endpoint: str, timeout: float = 3.0) -> str:
    import httpx
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{endpoint}/health")
            return "healthy" if resp.status_code < 500 else "unhealthy"
    except Exception:
        return "unhealthy"


def register_all_services() -> None:
    for svc in _KNOWN_SERVICES:
        try:
            existing = execute_one(
                "SELECT instance_id FROM instance_registry WHERE service_type = %s AND endpoint = %s",
                (svc["service_type"], svc["endpoint"]),
            )
            if existing:
                _INSTANCE_IDS[svc["service_type"]] = existing["instance_id"]
            else:
                result = InstanceRegistry.register(
                    service_type=svc["service_type"],
                    version=svc["version"],
                    endpoint=svc["endpoint"],
                    capabilities=svc["capabilities"],
                )
                _INSTANCE_IDS[svc["service_type"]] = result["instance_id"]
        except Exception as e:
            logger.warning("Failed to register service %s: %s", svc["service_type"], e)


def collect_metrics() -> None:
    now = datetime.now(timezone.utc)
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        MetricsService.write("cpu.usage", cpu, scope_type="PLATFORM", observed_at=now)
    except Exception:
        pass
    try:
        mem = psutil.virtual_memory()
        MetricsService.write("memory.usage", mem.percent, scope_type="PLATFORM", observed_at=now)
    except Exception:
        pass
    try:
        disk = psutil.disk_usage("/")
        MetricsService.write("storage.usage", disk.percent, scope_type="PLATFORM", observed_at=now)
    except Exception:
        pass
    try:
        row = execute_one("SELECT COUNT(*) AS cnt FROM job_runs WHERE status IN ('QUEUED','RUNNING')")
        queue_depth = row["cnt"] if row else 0
        MetricsService.write("job.queue_depth", float(queue_depth), scope_type="PLATFORM", observed_at=now)
    except Exception:
        pass
    try:
        total = 0
        healthy = 0
        instances = InstanceRegistry.list_instances()
        for inst in instances:
            total += 1
            if inst.get("health_status") == "healthy":
                healthy += 1
        health_pct = (healthy / total * 100) if total > 0 else 0
        MetricsService.write("service.health", health_pct, scope_type="PLATFORM", observed_at=now)
    except Exception:
        pass
    for svc in _KNOWN_SERVICES:
        inst_id = _INSTANCE_IDS.get(svc["service_type"])
        if not inst_id:
            continue
        status = _probe_health(svc["endpoint"])
        try:
            InstanceRegistry.heartbeat(inst_id, status)
        except Exception:
            pass


async def monitoring_loop(interval: int = 30) -> None:
    register_all_services()
    logger.info("Monitoring service started, registered %d services", len(_INSTANCE_IDS))
    while True:
        try:
            collect_metrics()
        except Exception as e:
            logger.warning("Metrics collection error: %s", e)
        await asyncio.sleep(interval)


def start_monitoring(app) -> None:
    @app.on_event("startup")
    async def _start():
        asyncio.create_task(monitoring_loop())
