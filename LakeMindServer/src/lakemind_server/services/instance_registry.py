from __future__ import annotations
from datetime import datetime, timezone
import ulid
from ..db import execute, execute_one


def _ulid(prefix: str) -> str:
    return f"{prefix}_{str(ulid.new())}"


class InstanceRegistry:

    @staticmethod
    def register(service_type: str, version: str, endpoint: str,
                 capabilities: list[str] | None = None) -> dict:
        instance_id = _ulid("ins")
        execute(
            "INSERT INTO instance_registry (instance_id, service_type, version, endpoint, capabilities, health_status) "
            "VALUES (%s, %s, %s, %s, %s, 'unknown')",
            (instance_id, service_type, version, endpoint, capabilities or []),
        )
        return {"instance_id": instance_id, "service_type": service_type, "endpoint": endpoint}

    @staticmethod
    def heartbeat(instance_id: str, health_status: str = "healthy",
                  active_revision_id: str | None = None) -> None:
        execute(
            "UPDATE instance_registry SET last_heartbeat = %s, health_status = %s, active_revision_id = COALESCE(%s, active_revision_id) "
            "WHERE instance_id = %s",
            (datetime.now(timezone.utc), health_status, active_revision_id, instance_id),
        )

    @staticmethod
    def list_instances(service_type: str | None = None) -> list[dict]:
        query = "SELECT * FROM instance_registry"
        params = None
        if service_type:
            query += " WHERE service_type = %s"
            params = (service_type,)
        query += " ORDER BY service_type, started_at DESC"
        return execute(query, params)

    @staticmethod
    def get_instance(instance_id: str) -> dict | None:
        return execute_one("SELECT * FROM instance_registry WHERE instance_id = %s", (instance_id,))

    @staticmethod
    def check_stale(timeout_seconds: int = 30) -> list[dict]:
        return execute(
            "UPDATE instance_registry SET health_status = 'unhealthy' "
            "WHERE last_heartbeat IS NOT NULL AND last_heartbeat < NOW() - INTERVAL '%s seconds' "
            "AND health_status = 'healthy' RETURNING instance_id, service_type",
            (timeout_seconds,),
        )
