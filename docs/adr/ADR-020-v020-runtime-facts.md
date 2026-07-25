# ADR-020: v0.2.0 Runtime Fact Sources

> Status: Accepted  
> Date: 2026-07-22  
> Branch: v0.2.0-hardening

## Context

v0.2.0 had two parallel job fact sources: `ray_jobs` (v1 compute API) and `job_runs`/`job_attempts` (v2 formal API). `submit()` wrote `job_runs` but `list_jobs()` read `ray_jobs`, causing list/detail inconsistency. Log queries referenced a nonexistent `jobs` table.

## Decision

Freeze a single set of runtime fact tables:

| Table | Purpose |
|-------|---------|
| `job_runs` | Job run lifecycle (submit → terminal) |
| `job_attempts` | Per-attempt execution records |
| `job_artifacts` | Results and output artifacts |
| `job_events` | Job timeline events |

`ray_jobs` is **dropped** (migration 011). All runtime code, metrics, and tests reference only the formal tables.

## Consequences

- One query path for job list/detail/status.
- Migration 011 is destructive (DROP TABLE ray_jobs).
- `JobSyncService` is the single status reconciliation loop.
- `JobService.list_jobs()` queries `job_runs` with SQL-level tenant filtering and LIMIT/OFFSET pagination.
