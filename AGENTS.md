# Repository implementation rules

`docs/MASTER_PLAN.md` is the architecture baseline. Work in bounded tickets and keep
`docs/IMPLEMENTATION_STATUS.md` current. Use synthetic records only unless a future,
reviewed ticket explicitly authorizes another source.

- Centralize authorization for every private route and job. A client-supplied tenant,
  subject, or role is never authority.
- Set PostgreSQL tenant and subject context transaction-locally. Every private data
  path needs same-tenant/cross-subject and cross-tenant negative tests.
- Keep rules deterministic. Missing or unsupported semantics return `UNKNOWN`.
- Never log bodies, tokens, histories, grades, student identifiers, or course codes.
- Add migrations for schema changes and document compatibility/rollback.
- Report commands actually run and checks that could not run.
- Human approval is required for production, live-source rights, academic semantics,
  privacy exceptions, privileged-access policy, and restricted connectors.

