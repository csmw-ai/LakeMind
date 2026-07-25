from __future__ import annotations
from datetime import datetime, timezone
import ulid
from ..db import execute, execute_one


def _ulid(prefix: str) -> str:
    return f"{prefix}_{str(ulid.new())}"


def enqueue(event_type: str, aggregate_id: str, aggregate_type: str,
            payload: dict, correlation_id: str | None = None) -> str:
    event_id = _ulid("evt")
    execute(
        "INSERT INTO outbox (event_id, event_type, aggregate_id, aggregate_type, payload, correlation_id) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (event_id, event_type, aggregate_id, aggregate_type, payload, correlation_id),
    )
    return event_id


_handlers: dict[str, callable] = {}


def register_handler(event_type: str, handler: callable) -> None:
    _handlers[event_type] = handler


def process_batch(batch_size: int = 10) -> int:
    rows = execute(
        "SELECT * FROM outbox WHERE status = 'PENDING' AND (next_retry_at IS NULL OR next_retry_at <= %s) "
        "ORDER BY created_at ASC LIMIT %s FOR UPDATE SKIP LOCKED",
        (datetime.now(timezone.utc), batch_size),
    )
    if not rows:
        return 0
    count = 0
    for row in rows:
        execute(
            "UPDATE outbox SET status = 'PROCESSING' WHERE event_id = %s AND status = 'PENDING'",
            (row["event_id"],),
        )
        handler = _handlers.get(row["event_type"])
        if handler is None:
            for prefix, h in _handlers.items():
                if row["event_type"].startswith(prefix):
                    handler = h
                    break
        if handler is None:
            execute(
                "UPDATE outbox SET status = 'FAILED', retry_count = retry_count, processed_at = %s WHERE event_id = %s",
                (datetime.now(timezone.utc), row["event_id"]),
            )
            count += 1
            continue
        try:
            handler(row["payload"])
            execute(
                "UPDATE outbox SET status = 'DONE', processed_at = %s WHERE event_id = %s",
                (datetime.now(timezone.utc), row["event_id"]),
            )
            count += 1
        except Exception as exc:
            retry_count = row["retry_count"] + 1
            if retry_count >= row["max_retries"]:
                execute(
                    "UPDATE outbox SET status = 'FAILED', retry_count = %s WHERE event_id = %s",
                    (retry_count, row["event_id"]),
                )
            else:
                import math
                delay = math.pow(2, retry_count)
                execute(
                    "UPDATE outbox SET status = 'PENDING', retry_count = %s, next_retry_at = %s WHERE event_id = %s",
                    (retry_count, datetime.now(timezone.utc).timestamp() + delay, row["event_id"]),
                )
    return count


def get_pending_count() -> int:
    row = execute_one("SELECT count(*) as total FROM outbox WHERE status = 'PENDING'")
    return row["total"] if row else 0


def register_default_handlers() -> None:
    from ..services.event_service import EventService

    def _emit_asset(payload):
        EventService.emit(
            event_type=payload.get("event_type", "asset.changed"),
            scope_type="TENANT",
            scope_id=payload.get("tenant_id"),
            resource_type="asset",
            resource_id=payload.get("asset_id"),
            payload=payload,
        )

    def _emit_knowledge(payload):
        EventService.emit(
            event_type=payload.get("event_type", "knowledge.changed"),
            scope_type="TENANT",
            scope_id=payload.get("tenant_id"),
            resource_type="knowledge",
            resource_id=payload.get("knowledge_id"),
            payload=payload,
        )

    def _emit_job(payload):
        EventService.emit(
            event_type=payload.get("event_type", "job.status_changed"),
            scope_type="TENANT",
            scope_id=payload.get("tenant_id"),
            resource_type="job",
            resource_id=payload.get("job_id"),
            payload=payload,
        )

    def _emit_model(payload):
        EventService.emit(
            event_type=payload.get("event_type", "model.deployment_changed"),
            scope_type="PLATFORM",
            scope_id=None,
            resource_type="model",
            resource_id=payload.get("model_id"),
            payload=payload,
        )

    def _emit_config(payload):
        EventService.emit(
            event_type=payload.get("event_type", "config.activated"),
            scope_type="PLATFORM",
            scope_id=None,
            resource_type="config",
            resource_id=payload.get("revision_id"),
            payload=payload,
        )

    def _emit_operation(payload):
        EventService.emit(
            event_type=payload.get("event_type", "operation.status_changed"),
            scope_type="TENANT",
            scope_id=payload.get("tenant_id"),
            resource_type="operation",
            resource_id=payload.get("operation_id"),
            payload=payload,
        )

    for prefix, handler in (
        ("asset.", _emit_asset),
        ("knowledge.", _emit_knowledge),
        ("job.", _emit_job),
        ("model.", _emit_model),
        ("config.", _emit_config),
        ("operation.", _emit_operation),
    ):
        register_handler(prefix, handler)
