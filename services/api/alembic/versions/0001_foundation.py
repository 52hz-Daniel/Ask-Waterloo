"""NAV-003 through NAV-005 foundation schema and policies."""

from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        """
        CREATE TABLE institutions (
          id uuid PRIMARY KEY, slug text UNIQUE NOT NULL, display_name text NOT NULL
        );
        CREATE TABLE tenants (
          id uuid PRIMARY KEY, institution_id uuid NOT NULL REFERENCES institutions(id),
          slug text UNIQUE NOT NULL
        );
        CREATE TABLE subjects (
          id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id),
          external_ref_hash text NOT NULL,
          UNIQUE (tenant_id, id), UNIQUE (tenant_id, external_ref_hash)
        );
        CREATE TABLE memberships (
          tenant_id uuid NOT NULL REFERENCES tenants(id), subject_id uuid,
          actor_ref_hash text NOT NULL, role text NOT NULL CHECK (role IN ('student','admin')),
          PRIMARY KEY (tenant_id, actor_ref_hash),
          FOREIGN KEY (tenant_id, subject_id) REFERENCES subjects(tenant_id, id),
          CHECK ((role = 'student' AND subject_id IS NOT NULL) OR role = 'admin')
        );
        CREATE TABLE source_snapshots (
          id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id),
          bundle_version text NOT NULL, fetched_at timestamptz NOT NULL,
          effective_from date NOT NULL, content_hash text NOT NULL,
          provenance_kind text NOT NULL CHECK (provenance_kind = 'synthetic'),
          UNIQUE (tenant_id, bundle_version)
        );
        CREATE TABLE courses (
          id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id),
          synthetic_code text NOT NULL, UNIQUE (tenant_id, synthetic_code),
          UNIQUE (tenant_id, id)
        );
        CREATE TABLE course_versions (
          id uuid PRIMARY KEY, tenant_id uuid NOT NULL, course_id uuid NOT NULL,
          snapshot_id uuid NOT NULL REFERENCES source_snapshots(id), title text NOT NULL,
          units numeric(5,2) NOT NULL, valid_from date NOT NULL, valid_to date,
          FOREIGN KEY (tenant_id, course_id) REFERENCES courses(tenant_id, id)
        );
        CREATE TABLE rule_sets (
          id uuid PRIMARY KEY, tenant_id uuid NOT NULL, course_id uuid NOT NULL,
          snapshot_id uuid NOT NULL REFERENCES source_snapshots(id), ast jsonb NOT NULL,
          parser_version text NOT NULL, review_status text NOT NULL,
          valid_from date NOT NULL, valid_to date,
          FOREIGN KEY (tenant_id, course_id) REFERENCES courses(tenant_id, id)
        );
        CREATE TABLE course_attempts (
          id uuid PRIMARY KEY, tenant_id uuid NOT NULL, subject_id uuid NOT NULL,
          course_id uuid NOT NULL, state text NOT NULL CHECK (state IN ('completed','in_progress')),
          evidence_origin text NOT NULL CHECK (evidence_origin = 'synthetic'),
          recorded_at timestamptz NOT NULL DEFAULT now(),
          FOREIGN KEY (tenant_id, subject_id) REFERENCES subjects(tenant_id, id),
          FOREIGN KEY (tenant_id, course_id) REFERENCES courses(tenant_id, id)
        );
        CREATE TABLE evaluations (
          id uuid PRIMARY KEY, tenant_id uuid NOT NULL, subject_id uuid NOT NULL,
          course_id uuid NOT NULL, result jsonb NOT NULL, profile_version integer NOT NULL,
          snapshot_bundle text NOT NULL, engine_version text NOT NULL,
          trace_id text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
          FOREIGN KEY (tenant_id, subject_id) REFERENCES subjects(tenant_id, id),
          FOREIGN KEY (tenant_id, course_id) REFERENCES courses(tenant_id, id)
        );
        CREATE TABLE audit_events (
          id uuid PRIMARY KEY, tenant_id uuid NOT NULL, actor_ref_hash text NOT NULL,
          action text NOT NULL, object_type text NOT NULL, outcome text NOT NULL,
          trace_id text NOT NULL, occurred_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE outbox_events (
          id uuid PRIMARY KEY, tenant_id uuid NOT NULL, event_type text NOT NULL,
          aggregate_type text NOT NULL, aggregate_id uuid NOT NULL,
          trace_id text NOT NULL, payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(), processed_at timestamptz,
          attempts integer NOT NULL DEFAULT 0
        );

        GRANT USAGE ON SCHEMA public TO navigator_app;
        GRANT SELECT ON institutions, tenants, memberships, source_snapshots, courses,
          course_versions, rule_sets TO navigator_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON course_attempts TO navigator_app;
        GRANT SELECT, INSERT ON evaluations, audit_events TO navigator_app;
        GRANT SELECT, INSERT, UPDATE ON outbox_events TO navigator_app;

        ALTER TABLE course_attempts ENABLE ROW LEVEL SECURITY;
        ALTER TABLE course_attempts FORCE ROW LEVEL SECURITY;
        CREATE POLICY attempts_subject_policy ON course_attempts
          USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
             AND subject_id = nullif(current_setting('app.subject_id', true), '')::uuid)
          WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
             AND subject_id = nullif(current_setting('app.subject_id', true), '')::uuid);

        ALTER TABLE evaluations ENABLE ROW LEVEL SECURITY;
        ALTER TABLE evaluations FORCE ROW LEVEL SECURITY;
        CREATE POLICY evaluations_subject_policy ON evaluations
          USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
             AND subject_id = nullif(current_setting('app.subject_id', true), '')::uuid)
          WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
             AND subject_id = nullif(current_setting('app.subject_id', true), '')::uuid);

        ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
        ALTER TABLE audit_events FORCE ROW LEVEL SECURITY;
        CREATE POLICY audit_tenant_insert ON audit_events FOR INSERT
          WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
        CREATE POLICY audit_tenant_select ON audit_events FOR SELECT
          USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);

        ALTER TABLE outbox_events ENABLE ROW LEVEL SECURITY;
        ALTER TABLE outbox_events FORCE ROW LEVEL SECURITY;
        CREATE POLICY outbox_tenant_policy ON outbox_events
          USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
          WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS outbox_events, audit_events, evaluations, course_attempts,
          rule_sets, course_versions, courses, source_snapshots, memberships, subjects,
          tenants, institutions CASCADE;
        """
    )

