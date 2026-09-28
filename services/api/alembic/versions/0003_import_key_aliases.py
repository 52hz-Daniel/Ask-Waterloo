"""Bind replay keys when identical content is deduplicated.

Revision ID: 0003_import_key_aliases
Revises: 0002_source_staging
"""

from alembic import op

revision = "0003_import_key_aliases"
down_revision = "0002_source_staging"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE source_import_keys (
          tenant_id uuid NOT NULL,
          source_key text NOT NULL,
          idempotency_key text NOT NULL,
          content_hash text NOT NULL,
          import_id uuid NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (tenant_id, source_key, idempotency_key),
          FOREIGN KEY (tenant_id, import_id) REFERENCES source_imports(tenant_id, id)
        );
        GRANT SELECT, INSERT ON source_import_keys TO navigator_app;
        ALTER TABLE source_import_keys ENABLE ROW LEVEL SECURITY;
        ALTER TABLE source_import_keys FORCE ROW LEVEL SECURITY;
        CREATE POLICY source_import_keys_tenant_policy ON source_import_keys
          USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
          WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS source_import_keys")

