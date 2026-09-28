-- Migration credentials own schema objects. The runtime role is intentionally
-- non-owner and has neither SUPERUSER nor BYPASSRLS.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'navigator_app') THEN
    CREATE ROLE navigator_app LOGIN PASSWORD 'local_app_only'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
END $$;
GRANT CONNECT ON DATABASE navigator TO navigator_app;

