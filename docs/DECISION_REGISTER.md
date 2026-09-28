# Decision register

Last updated: 2026-09-28. “Selected for local slice” is not production approval.

| Decision | Local-slice position | Owner / gate | Status |
|---|---|---|---|
| Initial scope | Synthetic two-tenant catalog, history, assessment, audit/outbox | Product + engineering / P1 | Implemented locally |
| Waterloo Open Data access | v3 contract and authentication behavior observed; no key is available, so no authenticated dataset was retrieved | Founder + Open Data owner / P0–P2 | Partially investigated; credential and source-owner confirmation required |
| Waterloo Calendar source rights | Public Calendar UI fields were observed, but its backing endpoint is not a supported contract and reuse/caching/redistribution are unconfirmed | Founder + Calendar/Kuali owner / P0–P2 | Unresolved blocker for live ingestion |
| Waterloo field mapping | Provisional disabled v3 mapper preserves identity/text and blocks publication because credits, effective dates, rights, and academic review are missing | Engineering + data steward / P0–P2 | Implemented as investigation code; not enabled |
| Catalog publication | Tenant active-pointer model with atomic synthetic promotion and retained-version rollback | Engineering + data steward / NAV-007 | Implemented locally; production human workflow unapproved |
| Academic rule coverage | One deliberately unsupported synthetic clause proves fail-safe `UNKNOWN` | Academic reviewer / P2 | Unreviewed; not production semantics |
| Runtime/framework versions | Node 22, Next.js 16.3.6, Python 3.12, FastAPI, PostgreSQL 16; exact packages locked by manifests | Engineering / P0 | Provisional; npm advisory check performed locally; broader maintenance/security review outstanding |
| Hosting/region/quotas | Docker Compose only; proposed Azure Canadian mapping not provisioned | Engineering + privacy + budget / before cloud | Unresolved |
| Identity provider | Synthetic server-side token map; production OIDC provider not chosen | Engineering + privacy/security / before accounts | Unresolved |
| Retention/deletion | No production collection; policy and schedules require privacy owner | Privacy owner / before collection | Unresolved |
| Production spend/support | No production resources or support promise | Founder/operator / before production | Unresolved |
| Private grades/SIS | Excluded and disabled | University owners / P7 | Out of scope |
| AI/chat | Excluded | Product/privacy / future phase | Out of scope |
