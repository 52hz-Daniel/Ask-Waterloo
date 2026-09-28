# ADR 0002: Fixture source receipt and staging boundary

- Status: accepted for NAV-006 local engineering
- Date: 2026-09-27
- Ticket: NAV-006

## Context

Course data must be retained and validated before it can affect student-facing
catalog state. Waterloo API registration, reuse rights, endpoint coverage, schemas,
request limits, and caching permission remain unresolved Phase P0 dependencies.

## Decision

Implement a source-neutral receipt/staging boundary using only the explicitly named
`synthetic_catalog_v1` fixture source. Store the canonical raw JSON and SHA-256 hash
in `source_imports`, create a versioned `source_snapshot` only when the envelope has
valid version/effective-date fields, and store every supplied record in
`staging_courses` with its ordinal, raw value, record hash, normalized candidate,
validation state, and bounded error codes.

Duplicate request keys with identical payloads and identical payloads under a new
key return the original import without new side effects. Reusing a request key for
different content is a conflict. Invalid envelopes or records are durably
quarantined. Import completion, audit evidence, and an outbox event commit in the
same transaction. The importer has no code path that writes `courses`,
`course_versions`, `rule_sets`, or an active publication pointer.

## Consequences

This proves receipt, normalization, quarantine, provenance and idempotency without
claiming publication. NAV-007 must implement reviewed promotion/rollback separately.
A future permitted adapter can produce the same raw envelope only after its actual
source contract is verified; this ADR does not define or validate Waterloo fields.

The migration is additive. Downgrade removes staging/import evidence and the new
snapshot metadata, so it is appropriate only for disposable local environments.

