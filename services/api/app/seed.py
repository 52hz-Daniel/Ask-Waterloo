import json

from sqlalchemy import create_engine, text

from app.config import settings
from app.ids import (
    COURSE_A100,
    COURSE_A300,
    COURSE_B100,
    INSTITUTION_A,
    INSTITUTION_B,
    RULE_A300,
    SNAPSHOT_A,
    SNAPSHOT_B,
    SUBJECT_A1,
    SUBJECT_A2,
    SUBJECT_B1,
    SUBJECT_B2,
    TENANT_A,
    TENANT_B,
)


def seed() -> None:
    engine = create_engine(settings.migration_database_url)
    with engine.begin() as connection:
        params = {
            "ia": INSTITUTION_A, "ib": INSTITUTION_B, "ta": TENANT_A, "tb": TENANT_B,
            "a1": SUBJECT_A1, "a2": SUBJECT_A2, "b1": SUBJECT_B1, "b2": SUBJECT_B2,
            "sa": SNAPSHOT_A, "sb": SNAPSHOT_B, "ca100": COURSE_A100,
            "ca300": COURSE_A300, "cb100": COURSE_B100,
        }
        statements = [
            """INSERT INTO institutions (id, slug, display_name) VALUES
                (:ia, 'synthetic-alpha', 'Synthetic University Alpha'),
                (:ib, 'synthetic-beta', 'Synthetic University Beta')
                ON CONFLICT DO NOTHING""",
            """INSERT INTO tenants (id, institution_id, slug) VALUES
                (:ta, :ia, 'alpha-local'), (:tb, :ib, 'beta-local')
                ON CONFLICT DO NOTHING""",
            """INSERT INTO subjects (id, tenant_id, external_ref_hash) VALUES
                (:a1, :ta, 'synthetic-a1'), (:a2, :ta, 'synthetic-a2'),
                (:b1, :tb, 'synthetic-b1'), (:b2, :tb, 'synthetic-b2')
                ON CONFLICT DO NOTHING""",
            """INSERT INTO memberships (tenant_id, subject_id, actor_ref_hash, role) VALUES
                (:ta, :a1, encode(digest('synthetic-actor-v1:student-a1','sha256'),'hex'), 'student'),
                (:ta, :a2, encode(digest('synthetic-actor-v1:student-a2','sha256'),'hex'), 'student'),
                (:tb, :b1, encode(digest('synthetic-actor-v1:student-b1','sha256'),'hex'), 'student'),
                (:tb, :b2, encode(digest('synthetic-actor-v1:student-b2','sha256'),'hex'), 'student'),
                (:ta, NULL, encode(digest('synthetic-actor-v1:admin-a','sha256'),'hex'), 'admin'),
                (:tb, NULL, encode(digest('synthetic-actor-v1:admin-b','sha256'),'hex'), 'admin')
                ON CONFLICT DO NOTHING""",
            """INSERT INTO source_snapshots
                  (id, tenant_id, bundle_version, fetched_at, effective_from, content_hash,
                   provenance_kind) VALUES
                (:sa, :ta, 'synthetic-alpha-v1', now(), DATE '2026-09-01',
                 'fixture-alpha-sha256', 'synthetic'),
                (:sb, :tb, 'synthetic-beta-v1', now(), DATE '2026-09-01',
                 'fixture-beta-sha256', 'synthetic') ON CONFLICT DO NOTHING""",
            """INSERT INTO courses (id, tenant_id, synthetic_code) VALUES
                (:ca100, :ta, 'SYN 100'), (:ca300, :ta, 'SYN 300'),
                (:cb100, :tb, 'SYN 100') ON CONFLICT DO NOTHING""",
            """INSERT INTO course_versions
                  (id, tenant_id, course_id, snapshot_id, title, units, valid_from)
                VALUES
                ('51000000-0000-0000-0000-000000000001', :ta, :ca100, :sa,
                 'Synthetic Foundations', 0.50, DATE '2026-09-01'),
                ('51000000-0000-0000-0000-000000000002', :ta, :ca300, :sa,
                 'Synthetic Advanced Topics', 0.50, DATE '2026-09-01'),
                ('51000000-0000-0000-0000-000000000003', :tb, :cb100, :sb,
                 'Independent Synthetic Foundations', 0.50, DATE '2026-09-01')
                ON CONFLICT DO NOTHING""",
            """INSERT INTO catalog_publications
                  (id, tenant_id, snapshot_id, bundle_version, state, approved_by_hash,
                   reason_code, approved_at, published_at, trace_id) VALUES
                ('81000000-0000-0000-0000-000000000001', :ta, :sa,
                 'synthetic-alpha-v1', 'published', 'seed:synthetic-admin',
                 'synthetic_review_complete', now(), now(), 'seed-synthetic'),
                ('81000000-0000-0000-0000-000000000002', :tb, :sb,
                 'synthetic-beta-v1', 'published', 'seed:synthetic-admin',
                 'synthetic_review_complete', now(), now(), 'seed-synthetic')
                ON CONFLICT (tenant_id, snapshot_id) DO NOTHING""",
            """UPDATE course_versions cv SET publication_id = p.id
                FROM catalog_publications p
                WHERE p.tenant_id = cv.tenant_id AND p.snapshot_id = cv.snapshot_id
                  AND cv.publication_id IS NULL""",
            """INSERT INTO active_catalog_publications
                  (tenant_id, publication_id, generation)
                SELECT p.tenant_id, p.id, 1 FROM catalog_publications p
                WHERE p.snapshot_id IN (:sa, :sb)
                ON CONFLICT (tenant_id) DO NOTHING""",
        ]
        for statement in statements:
            connection.execute(text(statement), params)
        connection.execute(
            text(
                """INSERT INTO rule_sets
                (id, tenant_id, course_id, snapshot_id, ast, parser_version,
                 review_status, valid_from)
                VALUES (:id, :tenant, :course, :snapshot, CAST(:ast AS jsonb),
                        'fixture-v1', 'synthetic_unreviewed', DATE '2026-09-01')
                ON CONFLICT DO NOTHING"""
            ),
            {
                "id": RULE_A300,
                "tenant": TENANT_A,
                "course": COURSE_A300,
                "snapshot": SNAPSHOT_A,
                "ast": json.dumps(
                    {
                        "type": "all_of",
                        "children": [
                            {"type": "course_completed", "course_id": str(COURSE_A100)},
                            {"type": "synthetic_advisor_permission"},
                        ],
                    }
                ),
            },
        )
        connection.execute(
            text(
                """INSERT INTO course_attempts
                (id, tenant_id, subject_id, course_id, state, evidence_origin) VALUES
                ('70000000-0000-0000-0000-000000000001', :ta, :a1, :ca,
                 'completed', 'synthetic'),
                ('70000000-0000-0000-0000-000000000002', :ta, :a2, :ca,
                 'in_progress', 'synthetic'),
                ('70000000-0000-0000-0000-000000000003', :tb, :b1, :cb,
                 'completed', 'synthetic') ON CONFLICT DO NOTHING"""
            ),
            {"ta": TENANT_A, "tb": TENANT_B, "a1": SUBJECT_A1, "a2": SUBJECT_A2,
             "b1": SUBJECT_B1, "ca": COURSE_A100, "cb": COURSE_B100},
        )


if __name__ == "__main__":
    seed()
