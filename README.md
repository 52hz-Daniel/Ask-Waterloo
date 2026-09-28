# Academic Navigator — synthetic foundation slice

This repository implements NAV-001 through NAV-007 plus the minimum synthetic
catalog and rule path needed to exercise the architecture. It is a Tier A local
engineering artifact. It has **not** validated Waterloo data access, source rights,
academic rules, institutional identity, or production deployment.

## Prerequisites

- Docker with Compose
- Node 22 and Python 3.12 only if running services outside containers

## Run locally

```sh
cp .env.example .env
make bootstrap
make dev
```

Then open <http://localhost:3000>. The API is at <http://localhost:8000>.
Synthetic bearer identities are documented in `.env.example`; they are deliberately
accepted only when `AUTH_MODE=synthetic`.

## Verify

```sh
make verify
```

The verification suite starts an isolated PostgreSQL container, applies Alembic
migrations, seeds two tenants with two subjects each, and runs API/DB/rules,
authorization, audit/outbox, and telemetry-redaction tests.

Useful commands: `make test`, `make test-integration`, `make seed-demo`, and
`make down`. No command contacts Waterloo or uses real student data.

## Synthetic source pipeline

NAV-006 adds an administrator-only `POST /v1/admin/source-imports` receipt endpoint
and `GET /v1/admin/source-imports/{id}` status endpoint. Inputs must identify the
`synthetic_catalog_v1` contract and provide an idempotency key. Raw JSON, hashes,
parser version, per-record provenance and validation outcomes are retained in
tenant-scoped staging tables. Invalid input is quarantined; this endpoint cannot
publish or modify catalog courses. Example fixtures live in `tests/fixtures/source/`.

## Synthetic publication pipeline

NAV-007 adds tenant-scoped approval, atomic publication, an explicit active catalog
pointer, and rollback to retained last-good versions. Only normalized
`synthetic_catalog_v1` snapshots can enter this path. Promotion materialization,
pointer changes, audit evidence, and outbox events share one database transaction.

## Waterloo access investigation

A disabled v3 transport/field mapper now reflects the official OpenAPI course schema,
but it has no ingestion or publication path. No API key or live Waterloo response is
stored. Credits, effective dates, source-use permission, and academic interpretation
remain explicit blockers. See `docs/WATERLOO_DATA_ACCESS_SPIKE.md` for actual access
results and the next human/source-owner gates.
