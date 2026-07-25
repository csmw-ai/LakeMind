from __future__ import annotations
from datetime import datetime, timezone, timedelta
import json
import ulid
from ..db import execute, execute_one
from .audit_service import AuditService


def _ulid(prefix: str) -> str:
    return f"{prefix}_{str(ulid.new())}"


class ReconciliationService:

    @staticmethod
    def scan_assets() -> list[dict]:
        drifts: list[dict] = []

        rows = execute(
            "SELECT a.asset_id, a.status, a.tenant_id FROM assets a "
            "WHERE a.status IN ('READY', 'DEGRADED', 'DELETING') AND a.deleted_at IS NULL"
        )
        for asset in rows:
            bindings = execute(
                "SELECT binding_id, binding_type, status, is_required FROM asset_bindings "
                "WHERE asset_id = %s AND status != 'DELETED'",
                (asset["asset_id"],),
            )

            if asset["status"] == "READY":
                for b in bindings:
                    if b["is_required"] and b["status"] != "READY":
                        drifts.append(ReconciliationService._record_drift(
                            "asset_binding", asset["asset_id"], "binding_missing",
                            {"binding_id": b["binding_id"], "binding_type": b["binding_type"]},
                        ))

            if asset["status"] == "DELETING":
                age = datetime.now(timezone.utc)
                if bindings:
                    drifts.append(ReconciliationService._record_drift(
                        "asset_binding", asset["asset_id"], "stale_deleting",
                        {"remaining_bindings": len(bindings)},
                    ))

        return drifts

    @staticmethod
    def scan_jobs() -> list[dict]:
        drifts: list[dict] = []
        now = datetime.now(timezone.utc)
        stale_threshold = now - timedelta(minutes=30)

        running_jobs = execute(
            "SELECT job_id, tenant_id, status, updated_at, created_at FROM job_runs "
            "WHERE status IN ('RUNNING', 'CANCELLING')"
        )
        for job in running_jobs:
            if job["updated_at"] < stale_threshold:
                drift_type = "stale_cancelling" if job["status"] == "CANCELLING" else "job_timeout_drift"
                drifts.append(ReconciliationService._record_drift(
                    "job_runtime", job["job_id"], drift_type,
                    {"status": job["status"], "last_updated": job["updated_at"].isoformat() if job["updated_at"] else None},
                ))

        active_ray_jobs = execute(
            "SELECT job_id, ray_job_id, status FROM job_attempts "
            "WHERE status IN ('RUNNING', 'QUEUED') AND ray_job_id IS NOT NULL"
        )
        if active_ray_jobs:
            try:
                import os
                from ray.job_submission import JobSubmissionClient
                dashboard_url = os.environ.get("LAKEMIND_RAY_DASHBOARD", "http://ray-head:8265")
                client = JobSubmissionClient(dashboard_url)
                ray_dashboard_jobs = {j["submission_id"] for j in client.list_jobs()}
                for rj in active_ray_jobs:
                    if rj["ray_job_id"] not in ray_dashboard_jobs:
                        drifts.append(ReconciliationService._record_drift(
                            "job_runtime", rj["job_id"], "orphaned_job",
                            {"ray_job_id": rj["ray_job_id"], "status": rj["status"]},
                        ))
            except Exception:
                pass

        return drifts

    @staticmethod
    def scan_all() -> dict:
        asset_drifts = ReconciliationService.scan_assets()
        job_drifts = ReconciliationService.scan_jobs()
        config_drifts = ReconciliationService.scan_config()
        all_drifts = asset_drifts + job_drifts + config_drifts
        return {
            "total": len(all_drifts),
            "assets": len(asset_drifts),
            "jobs": len(job_drifts),
            "config": len(config_drifts),
            "drifts": all_drifts,
        }

    @staticmethod
    def scan_config() -> list[dict]:
        rows = execute(
            "SELECT i.instance_id, i.service_type, i.active_revision_id, i.health_status "
            "FROM instance_registry i WHERE i.health_status = 'healthy'"
        )
        drifts = []
        for inst in rows:
            active_rev = execute_one(
                "SELECT revision_id FROM config_revisions WHERE is_active = TRUE "
                "ORDER BY activated_at DESC LIMIT 1"
            )
            if active_rev and inst["active_revision_id"] and active_rev["revision_id"] != inst["active_revision_id"]:
                drifts.append(ReconciliationService._record_drift(
                    "config_revision", inst["instance_id"], "config_not_converged",
                    {"desired": active_rev["revision_id"], "active": inst["active_revision_id"]},
                ))
        return drifts

    @staticmethod
    def get_drifts(category: str | None = None, page: int = 1, page_size: int = 50) -> dict:
        query = "SELECT * FROM reconciler_state WHERE resolved_at IS NULL"
        params = None
        if category:
            query += " AND scan_category = %s"
            params = (category,)
        query += " ORDER BY detected_at DESC"
        items = execute(query, params)
        total = len(items)
        offset = (page - 1) * page_size
        return {"items": items[offset:offset + page_size], "total": total, "page": page, "page_size": page_size}

    @staticmethod
    def _record_drift(category: str, resource_id: str, drift_type: str, details: dict) -> dict:
        execute(
            "INSERT INTO reconciler_state (scan_category, resource_id, drift_type, drift_details) "
            "VALUES (%s, %s, %s, %s)",
            (category, resource_id, drift_type, json.dumps(details)),
        )
        return {"resource_id": resource_id, "drift_type": drift_type, "category": category}
