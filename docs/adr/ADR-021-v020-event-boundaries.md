# ADR-021: v0.2.0 Event Boundaries

> Status: Accepted  
> Date: 2026-07-22  
> Branch: v0.2.0-hardening

## Context

Event/outbox infrastructure existed but was never started. `process_batch` had no running loop, no handlers were registered, and events with no handler were silently marked DONE.

## Decision

Four distinct event responsibilities, no overlap:

| Table | Responsibility |
|-------|---------------|
| `outbox` | Transactional outbox — pending business events written in same TX as business state |
| `event_stream` | Client-readable persistent platform events (SSE source) |
| `job_events` | Job detail timeline (per-job event log) |
| `audit_logs` | Security and admin audit trail |

**OutboxLoop** runs every 1s in FastAPI lifespan, calls `process_batch`. Default handlers registered for `asset.*`, `knowledge.*`, `job.*`, `model.*`, `config.*`, `operation.*` — each emits to `event_stream` via `EventService.emit`.

Events with no matching handler are marked **FAILED**, not DONE.

## Consequences

- Business services write to `outbox` in-transaction; OutboxLoop drains asynchronously.
- SSE clients read `event_stream` only.
- No Kafka, no distributed event bus in v0.2.0.
- Handler failures retry with exponential backoff, then DEAD.
