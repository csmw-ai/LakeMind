"""Drop legacy ray_jobs table — Job runtime fact source is job_runs/job_attempts

Revision ID: 011
Revises: 010
Create Date: 2026-07-22
"""
from __future__ import annotations
from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_ray_jobs_tenant")
    op.execute("DROP INDEX IF EXISTS idx_ray_jobs_task")
    op.execute("DROP TABLE IF EXISTS ray_jobs")


def downgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS ray_jobs ("
        "job_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, agent_id TEXT NOT NULL, "
        "skill_uri TEXT NOT NULL, job_name TEXT NOT NULL, entrypoint TEXT, "
        "params JSONB DEFAULT '{}', task_id TEXT, status TEXT DEFAULT 'submitted', "
        "ray_job_id TEXT, result_uri TEXT, created_at TIMESTAMPTZ DEFAULT now(), "
        "completed_at TIMESTAMPTZ)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_ray_jobs_tenant ON ray_jobs (tenant_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ray_jobs_task ON ray_jobs (tenant_id, task_id)")
