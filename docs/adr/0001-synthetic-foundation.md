# ADR 0001: Synthetic foundation architecture

- Status: accepted for local engineering; production review required
- Date: 2026-09-27
- Tickets: NAV-001–NAV-005

## Context

The first slice must prove tenancy, subject ownership, deterministic uncertainty,
database enforcement, trace continuity, and durable evidence without relying on
Waterloo systems or real student facts.

## Decision

Use a small monorepo with a Next.js/TypeScript display layer, FastAPI orchestration,
a pure Python rule evaluator, and PostgreSQL 16. Migrations run under a distinct
owner credential; the API uses a non-owner `NOBYPASSRLS` role. Trusted server code
sets `app.tenant_id` and `app.subject_id` with `SET LOCAL` inside every transaction.

Authentication is a synthetic token-to-principal map enabled only by an explicit
local setting. Assessment writes an evaluation and transactional outbox event. A
worker claims that event and retains trace context. Structured operational logs use
an allowlist and hashes/bounded enums rather than student facts. Audit records store
actor pseudonyms and action/object classes, never histories or grades.

The rule package supports `course_completed` for the proof and returns structured
`UNKNOWN` for every unimplemented rule type. It does not infer academic eligibility.

## Alternatives considered

- SQLite was rejected because it cannot demonstrate PostgreSQL RLS or transaction-
  local context.
- A client-provided tenant header was rejected because requested context is not
  authority.
- Session-scoped database variables were rejected because pooled connections could
  leak authorization context.
- A message broker was deferred: the transactional outbox and resumable worker
  boundary are proven first; a production queue adapter remains a later decision.

## Consequences and limitations

Docker is required for the integration evidence. The runtime role can technically
set custom PostgreSQL GUCs, so RLS is defense in depth rather than protection from a
fully compromised API. Production identity, external queue semantics, managed
telemetry export, source permission, cloud region/SKUs, and academic review remain
unvalidated. Migration rollback is `alembic downgrade base` and is destructive; it
is suitable only for this empty local fixture database, not a production rollback.

