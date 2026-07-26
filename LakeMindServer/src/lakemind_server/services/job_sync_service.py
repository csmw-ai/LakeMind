from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from ..db import execute, execute_one
from .job_state_machine import can_transition

logger = logging.getLogger(__name__)

_RAY_STATUS_MAP = {
    "PENDING": "QUEUED",
    "QUEUED": "QUEUED",
    "RUNNING": "RUNNING",
    "SUCCEEDED": "SUCCEEDED",
    "FAILED": "FAILED",
    "STOPPED": "CANCELLED",
}


class JobSyncService:

    def __init__(self, backend=None) -> None:
        self._backend = backend

    def _write_event(self, job_id: str, event_type: str, attempt_id: str | None = None,
                     old_status: str | None = None, new_status: str | None = None,
                     payload: dict | None = None) -> None:
        import json as _json
        seq_row = execute_one(
            "SELECT COALESCE(max(event_seq), 0) + 1 AS next_seq FROM job_events WHERE job_id = %s",
            (job_id,),
        )
        seq = seq_row["next_seq"] if seq_row else 1
        event_payload = payload or {}
        if old_status or new_status:
            event_payload = {**event_payload, "old_status": old_status, "new_status": new_status}
        execute(
            "INSERT INTO job_events (id, job_id, attempt_id, event_type, event_seq, payload) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (f"jev_{job_id}_{seq}", job_id, attempt_id, event_type, seq, _json.dumps(event_payload)),
        )

    def sync_all(self) -> dict:
        synced = 0
        lost = 0

        attempts = execute(
            "SELECT a.*, j.status AS job_status FROM job_attempts a "
            "JOIN job_runs j ON a.job_id = j.job_id "
            "WHERE a.status IN ('QUEUED', 'RUNNING') AND a.ray_job_id IS NOT NULL"
        )

        for attempt in attempts:
            try:
                ray_status = self._backend.get_status(attempt["ray_job_id"])
                mapped = _RAY_STATUS_MAP.get(ray_status, "UNKNOWN")

                if mapped == "UNKNOWN":
                    logger.warning("Unknown Ray status %s for attempt %s", ray_status, attempt["attempt_id"])

                if mapped != attempt["status"] and mapped != "UNKNOWN":
                    self._update_attempt_status(attempt, mapped)
                    synced += 1

                if mapped in ("SUCCEEDED", "FAILED", "CANCELLED"):
                    if mapped == "SUCCEEDED":
                        self._collect_result(attempt)
                    self._finalize_job(attempt["job_id"], mapped)
                elif mapped == "RUNNING" and attempt["job_status"] != "RUNNING":
                    execute(
                        "UPDATE job_runs SET status = 'RUNNING', updated_at = now() WHERE job_id = %s AND status IN ('QUEUED','SUBMITTED')",
                        (attempt["job_id"],),
                    )
                elif mapped == "QUEUED" and attempt["job_status"] == "RUNNING":
                    execute(
                        "UPDATE job_runs SET status = 'QUEUED', updated_at = now() WHERE job_id = %s",
                        (attempt["job_id"],),
                    )

            except Exception as e:
                logger.warning("Lost detection for attempt %s: %s", attempt["attempt_id"], e)
                self._mark_lost(attempt)
                lost += 1

        return {"synced": synced, "lost": lost}

    def cleanup_zombies(self) -> dict:
        cancelled = 0
        attempts = execute(
            "SELECT a.* FROM job_attempts a "
            "WHERE a.status IN ('TIMED_OUT', 'LOST') AND a.ray_job_id IS NOT NULL"
        )
        for attempt in attempts:
            try:
                ray_status = self._backend.get_status(attempt["ray_job_id"])
                mapped = _RAY_STATUS_MAP.get(ray_status, "UNKNOWN")
                if mapped in ("RUNNING", "QUEUED"):
                    self._backend.cancel(attempt["ray_job_id"])
                    cancelled += 1
                    logger.info("Cancelled zombie Ray job %s for attempt %s", attempt["ray_job_id"], attempt["attempt_id"])
            except Exception as e:
                logger.warning("Zombie cleanup for attempt %s failed: %s", attempt["attempt_id"], e)
        return {"cancelled_zombies": cancelled}

    def recover_on_startup(self) -> dict:
        recovered = 0
        lost = 0

        jobs = execute(
            "SELECT * FROM job_runs WHERE status IN ('QUEUED', 'RUNNING', 'CANCELLING')"
        )

        for job in jobs:
            attempt = execute_one(
                "SELECT * FROM job_attempts WHERE job_id = %s AND status IN ('QUEUED','RUNNING') ORDER BY attempt_number DESC LIMIT 1",
                (job["job_id"],),
            )
            if not attempt:
                execute(
                    "UPDATE job_runs SET status = 'LOST', updated_at = now(), finished_at = now() WHERE job_id = %s",
                    (job["job_id"],),
                )
                lost += 1
                continue

            if not attempt["ray_job_id"]:
                execute(
                    "UPDATE job_runs SET status = 'LOST', updated_at = now(), finished_at = now() WHERE job_id = %s",
                    (job["job_id"],),
                )
                lost += 1
                continue

            try:
                ray_status = self._backend.get_status(attempt["ray_job_id"])
                mapped = _RAY_STATUS_MAP.get(ray_status, "UNKNOWN")

                if job["status"] == "CANCELLING":
                    execute(
                        "UPDATE job_runs SET status = 'CANCELLED', updated_at = now(), finished_at = now() WHERE job_id = %s",
                        (job["job_id"],),
                    )
                    execute(
                        "UPDATE job_attempts SET status = 'CANCELLED', finished_at = now() WHERE attempt_id = %s",
                        (attempt["attempt_id"],),
                    )
                    recovered += 1
                elif mapped in ("SUCCEEDED", "FAILED", "CANCELLED"):
                    self._update_attempt_status(attempt, mapped)
                    self._finalize_job(job["job_id"], mapped)
                    recovered += 1
                elif mapped == "RUNNING":
                    execute(
                        "UPDATE job_runs SET status = 'RUNNING', updated_at = now() WHERE job_id = %s",
                        (job["job_id"],),
                    )
                    execute(
                        "UPDATE job_attempts SET status = 'RUNNING', started_at = COALESCE(started_at, now()) WHERE attempt_id = %s",
                        (attempt["attempt_id"],),
                    )
                    recovered += 1

            except Exception:
                self._mark_lost(attempt)
                execute(
                    "UPDATE job_runs SET status = 'LOST', updated_at = now(), finished_at = now() WHERE job_id = %s",
                    (job["job_id"],),
                )
                lost += 1

        return {"recovered": recovered, "lost": lost}

    def check_timeouts(self) -> dict:
        timed_out = 0
        jobs = execute(
            "SELECT j.*, a.attempt_id, a.ray_job_id, a.started_at FROM job_runs j "
            "JOIN job_attempts a ON j.job_id = a.job_id "
            "WHERE j.status = 'RUNNING' AND a.status = 'RUNNING' AND a.started_at IS NOT NULL"
        )

        now = datetime.now(timezone.utc)
        for job in jobs:
            resource_final = job["resource_final"]
            if isinstance(resource_final, str):
                resource_final = json.loads(resource_final)
            timeout = resource_final.get("timeout_seconds", 3600)
            started = job["started_at"]
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            elapsed = (now - started).total_seconds()
            if elapsed > timeout:
                if job.get("ray_job_id"):
                    try:
                        self._backend.cancel(job["ray_job_id"])
                    except Exception as e:
                        logger.warning("Failed to cancel Ray job %s on timeout: %s", job["ray_job_id"], e)
                execute(
                    "UPDATE job_attempts SET status = 'TIMED_OUT', finished_at = now() WHERE attempt_id = %s",
                    (job["attempt_id"],),
                )
                execute(
                    "UPDATE job_runs SET status = 'TIMED_OUT', updated_at = now(), finished_at = now() WHERE job_id = %s",
                    (job["job_id"],),
                )
                self._write_event(job["job_id"], "timed_out", attempt_id=job["attempt_id"],
                                  old_status="RUNNING", new_status="TIMED_OUT",
                                  payload={"elapsed_seconds": elapsed, "timeout_seconds": timeout})
                timed_out += 1

        return {"timed_out": timed_out}

    def _update_attempt_status(self, attempt: dict, new_status: str) -> None:
        execute(
            "UPDATE job_attempts SET status = %s, finished_at = CASE WHEN %s IN ('SUCCEEDED','FAILED','CANCELLED') THEN now() ELSE finished_at END WHERE attempt_id = %s",
            (new_status, new_status, attempt["attempt_id"]),
        )

    def _collect_result(self, attempt: dict) -> None:
        try:
            result = self._backend.get_result(attempt["ray_job_id"])
            import json as _json
            execute(
                "INSERT INTO job_artifacts (artifact_id, job_id, attempt_id, artifact_type, uri, metadata) "
                "VALUES (%s, %s, %s, 'result', %s, %s) ON CONFLICT DO NOTHING",
                (f"art_{attempt['attempt_id']}", attempt["job_id"], attempt["attempt_id"],
                 result.get("ray_job_id", ""), _json.dumps(result)),
            )
            self._write_event(attempt["job_id"], "artifact_created", attempt_id=attempt["attempt_id"],
                              payload={"artifact_type": "result"})
        except Exception as e:
            logger.warning("Failed to collect result for attempt %s: %s", attempt["attempt_id"], e)

    def _finalize_job(self, job_id: str, status: str) -> None:
        if can_transition("RUNNING", status):
            execute(
                "UPDATE job_runs SET status = %s, updated_at = now(), finished_at = now() WHERE job_id = %s AND status IN ('RUNNING','QUEUED')",
                (status, job_id),
            )
            self._write_event(job_id, status.lower(), old_status="RUNNING", new_status=status)

    def _mark_lost(self, attempt: dict) -> None:
        if attempt.get("ray_job_id"):
            try:
                self._backend.cancel(attempt["ray_job_id"])
            except Exception as e:
                logger.warning("Failed to cancel Ray job %s on lost: %s", attempt["ray_job_id"], e)
        execute(
            "UPDATE job_attempts SET status = 'LOST', finished_at = now() WHERE attempt_id = %s",
            (attempt["attempt_id"],),
        )
        execute(
            "UPDATE job_runs SET status = 'LOST', updated_at = now(), finished_at = now() WHERE job_id = %s AND status IN ('RUNNING','QUEUED')",
            (attempt["job_id"],),
        )
        self._write_event(attempt["job_id"], "lost", attempt_id=attempt["attempt_id"],
                          old_status="RUNNING", new_status="LOST")
