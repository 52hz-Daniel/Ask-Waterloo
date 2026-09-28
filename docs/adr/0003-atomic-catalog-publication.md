# ADR 0003: Atomic synthetic catalog publication

- Status: accepted for NAV-007 local engineering
- Date: 2026-09-28
- Ticket: NAV-007

## Context

NAV-006 deliberately stops at immutable receipt, normalization, and quarantine. A
validated candidate must not affect student-facing catalog state until an authorized
review action, and a failed promotion must leave the last-good catalog intact. The
Waterloo access spike has not approved any live source or academic rule semantics.

## Decision

Represent each review decision as a tenant-scoped `catalog_publication` and represent
the current catalog with exactly one `active_catalog_publication` pointer per tenant.
Approval is permitted only for a completely valid synthetic staged snapshot. Publish
materializes every staged course version, supersedes the previous publication,
switches the pointer, and writes audit/outbox evidence in one PostgreSQL transaction.
An advisory transaction lock serializes pointer changes within a tenant.

Retain superseded publications and their immutable course versions. Rollback may only
target a retained superseded publication with materialized versions; it atomically
repoints the active row and increments its generation. Tenant RLS is forced on the
new tables and on canonical course/version writes.

No live adapter can enter this path. Review reason codes and authorization are
synthetic local controls, not institutional academic approval.

## Consequences

An import, an approved candidate, a materialized publication, and the active catalog
are now distinct states. Readers can bind a future request to one publication ID and
avoid mixed-version results. Failed materialization rolls back course inserts,
version inserts, pointer changes, audit, and outbox writes together.

Historical versions consume storage and need a future retention policy. The first
implementation publishes course metadata only; rule publication, diff thresholds,
academic benchmarks, and operations UI remain later work. The migration backfills
existing synthetic seed versions as the initial publication. Downgrade is intended
only for disposable local environments because it removes publication history.
