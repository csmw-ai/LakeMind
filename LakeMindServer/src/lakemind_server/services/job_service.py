from __future__ import annotations
import json
from datetime import datetime, timezone
import ulid
from ..db import execute, execute_one
from ..security.context import SecurityContext
from ..security.secret_injection import resolve_job_secrets
from .skill_service import SkillService
from .audit_service import AuditService
from .job_state_machine import can_transition, transition, is_terminal
from ..plugins.compute.distributed.execution_backend import ExecutionBackend


def _ulid(prefix: str) -> str:
    return f"{prefix}_{str(ulid.new())}"


_DEFAULT_RESOURCES = {"cpu": 1, "memory_gb": 1, "timeout_seconds": 3600}
_TENANT_LIMITS = {"cpu": 16, "memory_gb": 32, "max_concurrent": 30}


class JobService:

    def __init__(self, backend: ExecutionBackend | None = None) -> None:
        self._backend = backend

    def _write_event(self, job_id: str, event_type: str, attempt_id: str | None = None,
                     old_status: str | None = None, new_status: str | None = None,
                     payload: dict | None = None) -> None:
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
            (_ulid("jev"), job_id, attempt_id, event_type, seq, json.dumps(event_payload)),
        )

    def submit(
        self,
        ctx: SecurityContext,
        skill_ref: str,
        inputs: dict,
        params: dict | None = None,
        model_profile: str | None = None,
        resource_overrides: dict | None = None,
        idempotency_key: str | None = None,
        job_name: str | None = None,
    ) -> dict:
        if idempotency_key:
            existing = execute_one(
                "SELECT * FROM job_runs WHERE tenant_id = %s AND idempotency_key = %s",
                (ctx.tenant_id, idempotency_key),
            )
            if existing:
                return existing

        _ref = skill_ref.replace("lake://skills/", "")
        if skill_ref.startswith("s3://"):
            import re
            fname = skill_ref.rsplit("/", 1)[-1]
            m = re.match(r"^(.+?)-v(\d+\.\d+\.\d+)\.zip$", fname)
            if m:
                _name, _ver = m.group(1), m.group(2)
            else:
                _name, _ver = fname.replace(".zip", ""), "latest"
        elif "@" in _ref:
            _name, _ver = _ref.rsplit("@", 1)
        else:
            _name, _ver = _ref, "latest"
        skill = SkillService.get_skill(ctx, _name, _ver)
        if not skill and _ver != "latest":
            skill = SkillService.get_skill(ctx, _name, "latest")
        if not skill:
            raise ValueError("SKILL_NOT_FOUND")

        if skill.get("publish_status") != "PUBLISHED":
            raise ValueError("SKILL_NOT_PUBLISHED")
        if skill.get("revoked_at") is not None:
            raise ValueError("SKILL_REVOKED")

        resource_final = self._resolve_resources(
            skill.get("default_resources", _DEFAULT_RESOURCES),
            resource_overrides or {},
        )

        running_count = execute_one(
            "SELECT count(*) AS c FROM job_runs WHERE tenant_id = %s AND status = 'RUNNING'",
            (ctx.tenant_id,),
        )
        if running_count and running_count["c"] >= _TENANT_LIMITS["max_concurrent"]:
            raise ValueError("JOB_CONCURRENCY_LIMIT")

        secret_refs = skill.get("secret_refs", [])
        resolved_secrets = resolve_job_secrets(skill.get("manifest", {}), ctx, f"job:{skill.get('name', 'unknown')}") if secret_refs else {}

        model_binding = None
        if model_profile:
            model_binding = {"profile": model_profile}

        config_rev = execute_one(
            "SELECT revision_id FROM config_revisions WHERE is_active = TRUE ORDER BY activated_at DESC LIMIT 1"
        )

        job_id = _ulid("job")
        execute(
            """
            INSERT INTO job_runs
                (job_id, tenant_id, skill_asset_id, skill_version, skill_checksum,
                 initiator_id, inputs, params, model_binding, secret_refs,
                 resource_final, status, config_revision_id, idempotency_key)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'SUBMITTED', %s, %s)
            """,
            (
                job_id, ctx.tenant_id, skill["asset_id"], skill["version"],
                skill.get("code_checksum", skill.get("checksum", "")), ctx.principal_id,
                json.dumps(inputs), json.dumps(params or {}),
                json.dumps(model_binding) if model_binding else None,
                json.dumps(secret_refs), json.dumps(resource_final),
                config_rev["revision_id"] if config_rev else None,
                idempotency_key,
            ),
        )
        self._write_event(job_id, "submitted", payload={"skill_ref": skill_ref})

        attempt_id = _ulid("atm")
        execute(
            """
            INSERT INTO job_attempts (attempt_id, job_id, attempt_number, status)
            VALUES (%s, %s, 1, 'QUEUED')
            """,
            (attempt_id, job_id),
        )

        execute(
            "UPDATE job_runs SET status = 'QUEUED', updated_at = now() WHERE job_id = %s",
            (job_id,),
        )
        self._write_event(job_id, "queued", attempt_id=attempt_id, old_status="SUBMITTED", new_status="QUEUED")

        if self._backend:
            try:
                pkg_uri = skill.get("package_uri", "") or skill.get("source_uri", "") or skill_ref
                ep = skill.get("entry_point", "main.py")
                if job_name and ep == "jobs":
                    ep = f"jobs/{job_name}/main.py"
                ray_job_id = self._backend.submit(
                    job_id=job_id,
                    skill_package_uri=pkg_uri,
                    entry_point=ep,
                    inputs=inputs,
                    params=params or {},
                    resources=resource_final,
                    secrets=resolved_secrets,
                    model_binding=model_binding,
                )
                execute(
                    "UPDATE job_attempts SET ray_job_id = %s, status = 'RUNNING', started_at = now() WHERE attempt_id = %s",
                    (ray_job_id, attempt_id),
                )
                execute(
                    "UPDATE job_runs SET status = 'RUNNING', updated_at = now() WHERE job_id = %s",
                    (job_id,),
                )
                self._write_event(job_id, "started", attempt_id=attempt_id, old_status="QUEUED", new_status="RUNNING",
                                  payload={"ray_job_id": ray_job_id})
            except Exception as e:
                execute(
                    "UPDATE job_attempts SET status = 'FAILED', error_message = %s, finished_at = now() WHERE attempt_id = %s",
                    (str(e), attempt_id),
                )
                execute(
                    "UPDATE job_runs SET status = 'FAILED', updated_at = now(), finished_at = now() WHERE job_id = %s",
                    (job_id,),
                )
                self._write_event(job_id, "failed", attempt_id=attempt_id, old_status="QUEUED", new_status="FAILED",
                                  payload={"error": str(e)})

        AuditService.record(
            event_type="job.submit", principal_id=ctx.principal_id, tenant_id=ctx.tenant_id,
            resource_id=job_id, action="job.submit",
            details={"skill_ref": skill_ref, "attempt_id": attempt_id},
        )

        return self.get_job(ctx, job_id)

    def get_job(self, ctx: SecurityContext, job_id: str) -> dict:
        row = execute_one("SELECT * FROM job_runs WHERE job_id = %s", (job_id,))
        if not row:
            raise ValueError("JOB_NOT_FOUND")
        if row["tenant_id"] != ctx.tenant_id and not ctx.is_platform_admin:
            raise ValueError("PERMISSION_DENIED")
        return row

    def list_jobs(
        self,
        ctx: SecurityContext,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        _status_aliases = {
            "completed": "SUCCEEDED", "failed": "FAILED",
            "running": "RUNNING", "submitted": "QUEUED",
            "cancelled": "CANCELLED",
        }
        where: list[str] = []
        params: list = []
        if not ctx.is_platform_admin:
            where.append("tenant_id = %s")
            params.append(ctx.tenant_id)
        if status:
            formal = _status_aliases.get(status, status.upper())
            where.append("status = %s")
            params.append(formal)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        count_row = execute_one(f"SELECT count(*) AS c FROM job_runs{clause}", tuple(params))
        total = count_row["c"] if count_row else 0
        offset = (page - 1) * page_size
        rows = execute(
            f"SELECT job_id, tenant_id, initiator_id, skill_asset_id, skill_version, "
            f"status, created_at, updated_at, finished_at, model_binding, resource_final "
            f"FROM job_runs{clause} ORDER BY created_at DESC LIMIT %s OFFSET %s",
            tuple(params) + (page_size, offset),
        )
        return {"items": rows, "total": total, "page": page, "page_size": page_size}

    def cancel(self, ctx: SecurityContext, job_id: str) -> dict:
        job = self.get_job(ctx, job_id)
        if not can_transition(job["status"], "CANCELLING") and not can_transition(job["status"], "CANCELLED"):
            raise ValueError(f"INVALID_TRANSITION: {job['status']} -> CANCELLED")

        if can_transition(job["status"], "CANCELLING"):
            execute(
                "UPDATE job_runs SET status = 'CANCELLING', updated_at = now() WHERE job_id = %s",
                (job_id,),
            )
            self._write_event(job_id, "cancelling", old_status=job["status"], new_status="CANCELLING")

            if self._backend:
                attempt = execute_one(
                    "SELECT ray_job_id FROM job_attempts WHERE job_id = %s AND status IN ('QUEUED','RUNNING') ORDER BY attempt_number DESC LIMIT 1",
                    (job_id,),
                )
                if attempt and attempt["ray_job_id"]:
                    try:
                        self._backend.cancel(attempt["ray_job_id"])
                    except Exception:
                        pass

        execute(
            "UPDATE job_runs SET status = 'CANCELLED', updated_at = now(), finished_at = now() WHERE job_id = %s",
            (job_id,),
        )
        execute(
            "UPDATE job_attempts SET status = 'CANCELLED', finished_at = now() WHERE job_id = %s AND status IN ('QUEUED','RUNNING')",
            (job_id,),
        )
        self._write_event(job_id, "cancelled", old_status="CANCELLING", new_status="CANCELLED")

        AuditService.record(ctx, action="job.cancel", resource_type="job_run", resource_id=job_id)
        return self.get_job(ctx, job_id)

    def retry(self, ctx: SecurityContext, job_id: str) -> dict:
        job = self.get_job(ctx, job_id)
        if job["status"] not in ("FAILED", "TIMED_OUT", "LOST"):
            raise ValueError("JOB_NOT_RETRYABLE")

        last_attempt = execute_one(
            "SELECT max(attempt_number) AS max_num FROM job_attempts WHERE job_id = %s",
            (job_id,),
        )
        next_num = (last_attempt["max_num"] or 0) + 1

        attempt_id = _ulid("atm")
        execute(
            "INSERT INTO job_attempts (attempt_id, job_id, attempt_number, status) VALUES (%s, %s, %s, 'QUEUED')",
            (attempt_id, job_id, next_num),
        )
        execute(
            "UPDATE job_runs SET status = 'QUEUED', updated_at = now(), finished_at = NULL WHERE job_id = %s",
            (job_id,),
        )
        self._write_event(job_id, "retried", attempt_id=attempt_id, old_status=job["status"], new_status="QUEUED",
                          payload={"attempt_number": next_num})

        if self._backend:
            skill = execute_one("SELECT * FROM assets WHERE asset_id = %s", (job["skill_asset_id"],))
            skill_package_uri = (skill.get("package_uri", "") or skill.get("source_uri", "")) if skill else ""
            entry_point = skill.get("entry_point", "main.py") if skill else "main.py"
            secret_refs = json.loads(job["secret_refs"]) if job.get("secret_refs") and isinstance(job["secret_refs"], str) else (job.get("secret_refs") or [])
            resolved_secrets = resolve_job_secrets(skill.get("manifest", {}) if skill else {}, ctx, f"job:{job.get('skill_asset_id', 'unknown')}") if secret_refs else {}
            try:
                ray_job_id = self._backend.submit(
                    job_id=job_id,
                    skill_package_uri=skill_package_uri,
                    entry_point=entry_point,
                    inputs=job["inputs"] if isinstance(job["inputs"], dict) else json.loads(job["inputs"]),
                    params=job["params"] if isinstance(job["params"], dict) else json.loads(job["params"]),
                    resources=job["resource_final"] if isinstance(job["resource_final"], dict) else json.loads(job["resource_final"]),
                    secrets=resolved_secrets,
                    model_binding=job["model_binding"] if isinstance(job["model_binding"], dict) else (json.loads(job["model_binding"]) if job["model_binding"] else None),
                )
                execute(
                    "UPDATE job_attempts SET ray_job_id = %s, status = 'RUNNING', started_at = now() WHERE attempt_id = %s",
                    (ray_job_id, attempt_id),
                )
                execute(
                    "UPDATE job_runs SET status = 'RUNNING', updated_at = now() WHERE job_id = %s",
                    (job_id,),
                )
                self._write_event(job_id, "started", attempt_id=attempt_id, old_status="QUEUED", new_status="RUNNING",
                                  payload={"ray_job_id": ray_job_id})
            except Exception as e:
                execute(
                    "UPDATE job_attempts SET status = 'FAILED', error_message = %s, finished_at = now() WHERE attempt_id = %s",
                    (str(e), attempt_id),
                )
                self._write_event(job_id, "failed", attempt_id=attempt_id, old_status="QUEUED", new_status="FAILED",
                                  payload={"error": str(e)})

        AuditService.record(ctx, action="job.retry", resource_type="job_run", resource_id=job_id)
        return self.get_job(ctx, job_id)

    def get_result(self, ctx: SecurityContext, job_id: str) -> dict:
        job = self.get_job(ctx, job_id)
        artifacts = execute(
            "SELECT * FROM job_artifacts WHERE job_id = %s ORDER BY created_at DESC",
            (job_id,),
        )
        result_artifact = None
        for a in artifacts:
            if a["artifact_type"] == "result":
                result_artifact = a
                break
        return {
            "job_id": job_id,
            "status": job["status"],
            "artifacts": artifacts,
            "result": result_artifact,
        }

    def get_attempts(self, ctx: SecurityContext, job_id: str) -> list[dict]:
        self.get_job(ctx, job_id)
        return execute(
            "SELECT * FROM job_attempts WHERE job_id = %s ORDER BY attempt_number",
            (job_id,),
        )

    def _resolve_resources(self, skill_default: dict, overrides: dict) -> dict:
        final = {}
        for key in ("cpu", "memory_gb", "timeout_seconds"):
            default_val = skill_default.get(key, _DEFAULT_RESOURCES[key])
            override_val = overrides.get(key)
            tenant_limit = _TENANT_LIMITS.get(key, float("inf"))

            if override_val is not None:
                final[key] = min(override_val, tenant_limit)
            else:
                final[key] = min(default_val, tenant_limit)

            if final[key] > tenant_limit:
                raise ValueError(f"JOB_RESOURCE_DENIED: {key}")

        return final
