# ADR-022: v0.2.0 API Deprecation — Single Job Interface

> Status: Accepted  
> Date: 2026-07-22  
> Branch: v0.2.0-hardening

## Context

Two job APIs coexisted: `/api/v1/compute/jobs` (v1, tightly coupled to `ray_jobs` and Ray engines) and `/api/v1/jobs` (v2, `JobService`-based). The v1 router had different semantics (raw func submit, skill package download, ray_jobs CRUD). Both were registered simultaneously.

## Decision

**Delete v1 entirely.** No compatibility layer, no sunset period, no dual-write.

- `/api/v1/compute/jobs` router **removed**.
- Old `jobs.py` (v1 router) **deleted**; `jobs_v2.py` **renamed** to `jobs.py`.
- `ray_jobs` table **dropped** (migration 011).
- Metadata plugin `ray_jobs` CRUD methods **removed**.
- MCP `server_client.py` job methods migrated to `/api/v1/jobs`.
- `verify_full.py` migrated to `/api/v1/jobs`.

## Rationale

Before 1.0.0, LakeMind has no external API consumers. Maintaining two interfaces is pure technical debt with zero compatibility value. Per §18 of the hardening plan, V1/V2 coexistence is prohibited.

## Consequences

- One Job API: `POST/GET /api/v1/jobs`.
- Code identifiers: `jobs.py`, `JobService`, `JobRun`, `JobAttempt` — no `v2` suffix.
- `JobService` obtained from `app.state.job_service` (lifespan-initialized), not module-level global.
- Future API changes before 1.0.0 follow the same pattern: migrate all callers, delete old, single migration.
