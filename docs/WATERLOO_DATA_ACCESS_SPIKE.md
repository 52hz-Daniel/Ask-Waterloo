# Waterloo data-access spike

- Investigation date: 2026-09-28
- Scope: public course/catalog sources only; no student records
- Status: partially validated, blocked from live ingestion and publication

This is engineering evidence, not source-owner permission, legal advice, or academic
approval. No API credential or live Waterloo response is stored in this repository.

## Access evidence

| Check | Actual result | Conclusion |
|---|---|---|
| `GET https://openapi.data.uwaterloo.ca/swagger/v1/swagger.json` | `200`; 112,016 bytes; SHA-256 `c3813b5f17cacdd8d10c8b949a0d32f974fa2b3ea535caabfd33734eab9a776d` | The v3 machine-readable contract is publicly reachable. |
| `GET https://openapi.data.uwaterloo.ca/v3/Subjects` without a key | `401`; response identifies the missing `X-API-KEY` header | The data API is live, but anonymous data retrieval does not work. |
| `WATERLOO_API_KEY` in the test environment | Not set | No authenticated v3 data request was possible. |
| Public 2026–2027 Undergraduate Calendar UI | `200`; its public client returned catalog metadata, schema, search results, and course detail | Calendar fields are observable, but the UI backend is not documented as a supported integration API. |

The official [getting-started guide](https://uwaterloo.atlassian.net/wiki/spaces/UWAPI/pages/34025641600/Getting%2BStarted%2B-%2BOpenAPI)
says each data request requires `X-API-KEY`. Registration requires a real email,
project name/URI, and confirmation. Automated registration was deliberately not
performed because selecting an identity and making that external commitment needs
the project owner. A key must be supplied through a secret/environment mechanism,
never committed.

## Contract and mapping findings

The [live v3 documentation](https://openapi.data.uwaterloo.ca/api-docs/index.html)
documents term, subject, course, and class-schedule endpoints. The inspected `Course`
schema exposes these relevant fields:

| Waterloo v3 field | Candidate field | Finding |
|---|---|---|
| `termCode`, `courseId`, `courseOfferNumber` | source record identity | Use the three-part identity; `courseId` is explicitly not unique across terms. |
| `subjectCode`, `catalogNumber` | display code | Direct mapping after validation and normalization. |
| `title`, `description` | title, description | Direct nullable/text mapping. |
| `termName` | source term label | Preserve as provenance/display metadata. |
| `requirementsDescription` | raw requirements text | Preserve exactly for later review; do not parse into an eligibility rule yet. |
| — | credits/units | Missing from the inspected v3 `Course` schema; publication blocker. |
| — | calendar effective range | Missing from the inspected v3 `Course` schema; publication blocker. |

`app.adapters.waterloo_open_data` implements the documented request path and this
mapping as a disabled candidate boundary. Its tests use synthetic values shaped like
the official schema. It cannot write `source_imports`, staging, canonical catalog, or
publication tables. Every mapped candidate carries explicit blockers for credits,
effective dates, academic review, and source-use approval.

The public Calendar UI exposed credits, effective dates, and separate prerequisite,
corequisite, and antirequisite renderings for an observed course. Those values were
HTML presentation text, not a documented rule AST. The UI host and requests are
therefore discovery evidence only; they are not configured as an application source
and no response was copied into fixtures.

## Accuracy findings

Waterloo's official [requisites guidance](https://uwaterloo.ca/academic-calendar-curriculum-management-resources/curriculum-management/requisites)
confirms that requirements can involve courses, minimum grades, averages, programs,
plans, academic levels, milestones, free-form conditions, corequisites, and
antirequisites. Cross-listed offerings may differ. This is broader than the current
synthetic evaluator and makes raw-text interpretation unsafe without designated
academic review.

The [Kuali CM overview](https://uwaterloo.ca/academic-calendar-curriculum-management-resources/kuali-cm)
describes versioned records, effective periods, revisions, and workflow statuses.
That supports the need for version/effective-date provenance but does not establish
an API contract. The current Calendar publication is identified by Waterloo as the
[2026–2027 Undergraduate Studies Academic Calendar](https://uwaterloo.ca/academic-calendar-curriculum-management-resources/news/2026-2027-undergraduate-studies-academic-calendar-published),
effective for the stated academic year.

No observed Waterloo requirement has been added as a rule test. Academic examples
must be reviewed and expected outcomes independently approved before they can become
benchmark or publication evidence.

## Permitted-use finding

Permitted reuse remains unresolved:

- The current Open Data portal says the API provides authoritative datasets and
  directs support questions to its [official contact channels](https://uwaterloo.ca/api/contact-us).
- Archived v2 documentation points to a Waterloo Open Data License, but that license
  URL currently returns `404`; it is not sufficient evidence for v3 or Calendar use.
- Waterloo's general [copyright notice](https://uwaterloo.ca/copyright) applies when
  more specific permission is absent.

Before enabling either source, the source owner must confirm in writing the permitted
source, authentication method, request limits, caching/retention, attribution,
modification/normalization, and redistribution/display terms. Public visibility alone
is not treated as permission to ingest and republish.

## Next evidence gates

1. Project owner registers or obtains a v3 key and supplies it securely. Run bounded
   `Terms`, `Courses`, and `ClassSchedules` requests; save only hashes, status,
   timestamps, schema diffs, and approved minimal samples.
2. Open a Waterloo Open Data support request asking whether v3 course data covers the
   Calendar use case and which current license/terms apply.
3. Ask the Calendar/Kuali source owner for a supported export/API and explicit reuse,
   caching, and attribution terms. Do not depend on the observed UI backend.
4. Reconcile credits and effective dates across permitted sources, then update the
   adapter contract and run schema/quarantine tests before enabling staging.
5. Have a designated academic reviewer select representative requisite examples and
   approve expected AST/outcomes. Unsupported forms must continue to return
   structured `UNKNOWN`.
