"""NAV-007 atomic catalog publication and last-good recovery.

Revision ID: 0004_publication_promotion
Revises: 0003_import_key_aliases
"""

from alembic import op

revision = "0004_publication_promotion"
down_revision = "0003_import_key_aliases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE source_snapshots
          ADD CONSTRAINT source_snapshots_tenant_id_unique UNIQUE (tenant_id, id);

        CREATE TABLE catalog_publications (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants(id),
          snapshot_id uuid NOT NULL,
          source_import_id uuid,
          bundle_version text NOT NULL,
          state text NOT NULL CHECK (state IN ('approved','published','superseded')),
          approved_by_hash text NOT NULL,
          reason_code text NOT NULL CHECK (reason_code = 'synthetic_review_complete'),
          approved_at timestamptz NOT NULL DEFAULT now(),
          published_at timestamptz,
          superseded_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          trace_id text NOT NULL,
          UNIQUE (tenant_id, id),
          UNIQUE (tenant_id, snapshot_id),
          FOREIGN KEY (tenant_id, snapshot_id)
            REFERENCES source_snapshots(tenant_id, id),
          FOREIGN KEY (tenant_id, source_import_id)
            REFERENCES source_imports(tenant_id, id)
        );

        CREATE TABLE active_catalog_publications (
          tenant_id uuid PRIMARY KEY REFERENCES tenants(id),
          publication_id uuid NOT NULL,
          generation integer NOT NULL CHECK (generation > 0),
          updated_at timestamptz NOT NULL DEFAULT now(),
          FOREIGN KEY (tenant_id, publication_id)
            REFERENCES catalog_publications(tenant_id, id)
        );

        ALTER TABLE course_versions
          ADD COLUMN publication_id uuid,
          ADD CONSTRAINT course_versions_publication_fk
            FOREIGN KEY (tenant_id, publication_id)
              REFERENCES catalog_publications(tenant_id, id),
          ADD CONSTRAINT course_versions_snapshot_unique
            UNIQUE (tenant_id, course_id, snapshot_id);

        -- Preserve the already seeded synthetic catalog as the initial last-good
        -- publication when upgrading an existing local database.
        INSERT INTO catalog_publications
          (id, tenant_id, snapshot_id, source_import_id, bundle_version, state,
           approved_by_hash, reason_code, approved_at, published_at, trace_id)
        SELECT gen_random_uuid(), s.tenant_id, s.id, s.import_id, s.bundle_version,
               'published', 'migration:synthetic-seed', 'synthetic_review_complete',
               s.fetched_at, s.fetched_at, 'migration-0004'
        FROM source_snapshots s
        WHERE EXISTS (SELECT 1 FROM course_versions cv WHERE cv.snapshot_id = s.id)
        ON CONFLICT (tenant_id, snapshot_id) DO NOTHING;

        UPDATE course_versions cv
        SET publication_id = p.id
        FROM catalog_publications p
        WHERE p.tenant_id = cv.tenant_id AND p.snapshot_id = cv.snapshot_id
          AND cv.publication_id IS NULL;

        INSERT INTO active_catalog_publications (tenant_id, publication_id, generation)
        SELECT DISTINCT ON (p.tenant_id) p.tenant_id, p.id, 1
        FROM catalog_publications p
        JOIN source_snapshots s ON s.tenant_id = p.tenant_id AND s.id = p.snapshot_id
        ORDER BY p.tenant_id, s.fetched_at DESC, p.id
        ON CONFLICT (tenant_id) DO NOTHING;

        UPDATE catalog_publications p
        SET state = 'superseded', superseded_at = now()
        WHERE p.state = 'published'
          AND NOT EXISTS (
            SELECT 1 FROM active_catalog_publications a
            WHERE a.tenant_id = p.tenant_id AND a.publication_id = p.id
          );

        GRANT SELECT, INSERT, UPDATE ON catalog_publications TO navigator_app;
        GRANT SELECT, INSERT, UPDATE ON active_catalog_publications TO navigator_app;
        GRANT INSERT, UPDATE ON courses, course_versions TO navigator_app;

        ALTER TABLE catalog_publications ENABLE ROW LEVEL SECURITY;
        ALTER TABLE catalog_publications FORCE ROW LEVEL SECURITY;
        CREATE POLICY catalog_publications_tenant_policy ON catalog_publications
          USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
          WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);

        ALTER TABLE active_catalog_publications ENABLE ROW LEVEL SECURITY;
        ALTER TABLE active_catalog_publications FORCE ROW LEVEL SECURITY;
        CREATE POLICY active_catalog_publications_tenant_policy ON active_catalog_publications
          USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
          WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);

        ALTER TABLE courses ENABLE ROW LEVEL SECURITY;
        ALTER TABLE courses FORCE ROW LEVEL SECURITY;
        CREATE POLICY courses_tenant_policy ON courses
          USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
          WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);

        ALTER TABLE course_versions ENABLE ROW LEVEL SECURITY;
        ALTER TABLE course_versions FORCE ROW LEVEL SECURITY;
        CREATE POLICY course_versions_tenant_policy ON course_versions
          USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
          WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE course_versions DISABLE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS course_versions_tenant_policy ON course_versions;
        ALTER TABLE courses DISABLE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS courses_tenant_policy ON courses;
        REVOKE INSERT, UPDATE ON courses, course_versions FROM navigator_app;
        DROP TABLE IF EXISTS active_catalog_publications;
        ALTER TABLE course_versions
          DROP CONSTRAINT IF EXISTS course_versions_snapshot_unique,
          DROP CONSTRAINT IF EXISTS course_versions_publication_fk,
          DROP COLUMN IF EXISTS publication_id;
        DROP TABLE IF EXISTS catalog_publications;
        ALTER TABLE source_snapshots
          DROP CONSTRAINT IF EXISTS source_snapshots_tenant_id_unique;
        """
    )
