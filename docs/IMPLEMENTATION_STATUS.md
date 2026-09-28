# Implementation status

Last updated: 2026-09-28. This ledger distinguishes code from external approval.

| ID | State | Evidence | Gap / next action |
|---|---|---|---|
| NAV-001 | Implemented, not externally approved | Decision register and ADR 0001 | Resolve P0 source, identity, hosting, privacy, budget decisions with named humans |
| NAV-002 | Implemented and locally tested | Compose, Dockerfiles, Make targets, README, successful image builds | Validate fresh-host instructions continuously |
| NAV-003 | Implemented with synthetic subset | Migration, Pydantic contracts, seed fixtures, contract/rule tests | Add reviewed AST/schema breadth in NAV-008 |
| NAV-004 | Implemented and locally tested | Central principal resolution, `SET LOCAL`, forced RLS, API and direct-DB isolation tests | Replace synthetic auth only after OIDC decision |
| NAV-005 | Implemented and locally tested | Safe JSON telemetry, durable audit/outbox, trace propagation, sentinel test | Add approved collector/backend and external durable queue later |
| NAV-006 | Implemented and locally tested | Migrations 0002/0003, synthetic schema/fixtures, admin receipt/status API, staging/quarantine/import tests | Waterloo staging remains disabled pending credentials, contract completion, and rights |
| NAV-007 | Implemented and locally tested for synthetic metadata | Migration 0004, approval/publish/active/rollback API, atomic-failure and recovery tests, ADR 0003 | Rule publication, diff thresholds, academic benchmark, and production steward approval remain P2 work |
| NAV-008+ | Not started as roadmap tickets | — | Explicitly outside this slice |

## NAV-001–NAV-005 acceptance recheck

Checked before NAV-006 on 2026-09-27. Each ticket's local acceptance condition is
covered, with these limitations carried forward rather than treated as production
evidence:

| ID | Acceptance recheck | Remaining gap |
|---|---|---|
| NAV-001 | Technology, source rights, region, identity and scope have role owners and explicit status | No named human has approved the unresolved P0 decisions |
| NAV-002 | Documented Compose bootstrap uses only synthetic records and built successfully | Hosted CI has not run; fresh-host portability beyond this machine is unverified |
| NAV-003 | Synthetic course/rule/profile contracts validate and version/effective-date fields exist | Canonical schema is intentionally a narrow fixture subset |
| NAV-004 | Two-tenant/two-subject API and direct PostgreSQL positive/negative tests pass | Authentication is synthetic; RLS is defense in depth against query mistakes, not a compromised app role that can forge GUC context |
| NAV-005 | Correlation survives API/database/outbox/worker; privileged audit and sentinel tests pass | No OpenTelemetry collector/backend, external broker, or append-only audit export is configured |

## NAV-006 acceptance evidence

- Valid synthetic envelopes create immutable raw import evidence, a versioned
  snapshot and normalized staging candidates with record-level provenance.
- Malformed documents, partial records, duplicate source record IDs and conflicting
  bundle versions are durably quarantined.
- Identical deliveries are content-deduplicated and all supplied idempotency keys are
  bound to the original import; key reuse with different content returns `409`.
- Negative tests compare published course/version rows before and after every failed
  import. They remain byte-for-byte equivalent.
- Import, audit evidence and outbox notification commit in one transaction. The
  importer has no publication-table write path.

## P0 Waterloo access investigation

- The official v3 Swagger contract was retrieved successfully and hashed. A live
  unauthenticated `Subjects` request returned `401` because `X-API-KEY` was missing.
  No key is present, so authenticated dataset retrieval remains unvalidated.
- A disabled transport and mapper cover only documented v3 Course fields. Tests use
  synthetic schema-shaped values. The mapper preserves raw requirements prose and
  blocks promotion for missing credits/effective dates, unreviewed semantics, and
  unresolved source permission.
- Public Calendar UI metadata/course fields were observable, but its backing service
  is not treated as a supported integration contract. No live response is committed.
- Current reuse, caching, attribution, and redistribution permission could not be
  established. Details, evidence URLs, mapping gaps, and human next actions are in
  `docs/WATERLOO_DATA_ACCESS_SPIKE.md`.

## NAV-007 acceptance evidence

- An authorized synthetic review creates an approved publication without changing
  the active catalog. Cross-tenant access returns the same not-found boundary.
- Publish materializes the complete staged bundle, supersedes the previous version,
  advances one tenant-scoped active pointer, and records audit/outbox evidence in one
  transaction. A tenant advisory transaction lock serializes pointer changes.
- Course versions carry both snapshot and publication identity; the integration test
  proves every version in the promoted bundle has the expected pair.
- A deliberately corrupted normalized unit causes database materialization to fail.
  The test proves both the active pointer and the canonical catalog fingerprint are
  unchanged after the transaction rolls back.
- Rollback selects a retained, materialized superseded publication, restores it as
  active, and increments the active generation without deleting history.

## Verification record

The latest `make verify` completed successfully on 2026-09-28 using Docker Desktop
29.7.2 and Docker Compose 5.4.0:

- All service images built; Alembic upgraded through `0004_publication_promotion`; the
  synthetic seed completed.
- Ruff: passed.
- mypy strict mode: no issues in 16 source files.
- pytest: 29 passed in 0.71 seconds; one upstream Starlette/AnyIO deprecation warning.
- ESLint: passed.
- TypeScript `tsc --noEmit`: passed.
- Next.js 16.3.6 production build: passed (static page plus assessment route).
- The prior dependency check remains current because the frontend lockfile did not
  change: `npm audit --audit-level=high` reported 0 vulnerabilities.
- Refreshed API/worker containers started; `/health` returned `200` and OpenAPI lists
  both NAV-006 source-import routes.

No authenticated Waterloo dataset access, supported Calendar API, source-use
permission, production identity, cloud deployment, external queue or telemetry
backend, or real academic semantics have been validated. This evidence is local
engineering evidence, not approval or a production control attestation.
