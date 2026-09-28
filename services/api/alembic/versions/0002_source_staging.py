"""NAV-006 versioned source receipt, staging, and quarantine.

Revision ID: 0002_source_staging
Revises: 0001_foundation
"""

from alembic import op

revision = "0002_source_staging"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE source_imports (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants(id),
          source_key text NOT NULL CHECK (source_key = 'synthetic_catalog_v1'),
          idempotency_key text NOT NULL,
          content_hash text NOT NULL,
          raw_payload jsonb NOT NULL,
          parser_version text NOT NULL,
          state text NOT NULL CHECK (state IN ('received','normalized','quarantined')),
          error_codes text[] NOT NULL DEFAULT '{}',
          received_at timestamptz NOT NULL DEFAULT now(),
          completed_at timestamptz,
          trace_id text NOT NULL,
          UNIQUE (tenant_id, source_key, idempotency_key),
          UNIQUE (tenant_id, source_key, content_hash),
          UNIQUE (tenant_id, id)
        );

        ALTER TABLE source_snapshots
          ADD COLUMN import_id uuid,
          ADD COLUMN source_key text,
          ADD COLUMN parser_version text,
          ADD COLUMN validation_status text NOT NULL DEFAULT 'published'
            CHECK (validation_status IN ('normalized','quarantined','published')),
          ADD CONSTRAINT source_snapshots_import_fk
            FOREIGN KEY (tenant_id, import_id) REFERENCES source_imports(tenant_id, id),
          ADD CONSTRAINT source_snapshots_import_unique UNIQUE (tenant_id, import_id);

        CREATE TABLE staging_courses (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL,
          import_id uuid NOT NULL,
          snapshot_id uuid,
          ordinal integer NOT NULL CHECK (ordinal >= 0),
          source_record_id text,
          source_url text,
          content_hash text NOT NULL,
          raw_record jsonb NOT NULL,
          normalized_record jsonb,
          validation_status text NOT NULL CHECK (validation_status IN ('valid','quarantined')),
          error_codes text[] NOT NULL DEFAULT '{}',
          FOREIGN KEY (tenant_id, import_id) REFERENCES source_imports(tenant_id, id),
          FOREIGN KEY (snapshot_id) REFERENCES source_snapshots(id),
          UNIQUE (import_id, ordinal)
        );

        CREATE INDEX staging_courses_import_idx ON staging_courses (tenant_id, import_id);

        GRANT SELECT, INSERT, UPDATE ON source_imports TO navigator_app;
        GRANT SELECT, INSERT, UPDATE ON source_snapshots TO navigator_app;
        GRANT SELECT, INSERT, UPDATE ON staging_courses TO navigator_app;

        ALTER TABLE source_imports ENABLE ROW LEVEL SECURITY;
        ALTER TABLE source_imports FORCE ROW LEVEL SECURITY;
        CREATE POLICY source_imports_tenant_policy ON source_imports
          USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
          WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);

        ALTER TABLE staging_courses ENABLE ROW LEVEL SECURITY;
        ALTER TABLE staging_courses FORCE ROW LEVEL SECURITY;
        CREATE POLICY staging_courses_tenant_policy ON staging_courses
          USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
          WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);

        ALTER TABLE source_snapshots ENABLE ROW LEVEL SECURITY;
        ALTER TABLE source_snapshots FORCE ROW LEVEL SECURITY;
        CREATE POLICY source_snapshots_tenant_policy ON source_snapshots
          USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
          WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS staging_courses;
        REVOKE INSERT, UPDATE ON source_snapshots FROM navigator_app;
        ALTER TABLE source_snapshots DISABLE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS source_snapshots_tenant_policy ON source_snapshots;
        ALTER TABLE source_snapshots
          DROP CONSTRAINT IF EXISTS source_snapshots_import_unique,
          DROP CONSTRAINT IF EXISTS source_snapshots_import_fk,
          DROP COLUMN IF EXISTS validation_status,
          DROP COLUMN IF EXISTS parser_version,
          DROP COLUMN IF EXISTS source_key,
          DROP COLUMN IF EXISTS import_id;
        DROP TABLE IF EXISTS source_imports;
        """
    )
