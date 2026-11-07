-- Corpus baseline, platform track (run as veyro_cp_bootstrap). Must lint clean.
-- D6: platform_scope tables get no RLS and no policy; the boundary is schema, ownership and the
-- closed function allowlist.
CREATE SCHEMA plt01_platform AUTHORIZATION veyro_cp_platform;
CREATE SCHEMA plt01_api AUTHORIZATION veyro_cp_platform;

REVOKE CONNECT, TEMPORARY ON DATABASE veyro_cp FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA plt01_api REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

GRANT CONNECT ON DATABASE veyro_cp TO veyro_cp_app;

CREATE TABLE plt01_platform.tenants (
    tenant_id uuid NOT NULL PRIMARY KEY,
    external_key text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

GRANT USAGE ON SCHEMA plt01_platform TO veyro_cp_migrator;
GRANT REFERENCES (tenant_id) ON plt01_platform.tenants TO veyro_cp_migrator;
