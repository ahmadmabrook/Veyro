-- Legitimate: REVOKE from PUBLIC is the safe pattern, a REVOKE-only default-privilege entry is
-- explicitly allowed by D5 bullet 2, the column-level REFERENCES grant to the migrator is D6.1
-- item 4's single permitted exception, and EXECUTE here is a privilege name, not dynamic SQL.
REVOKE CONNECT, TEMPORARY ON DATABASE veyro_cp FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA plt01_api REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
GRANT CONNECT ON DATABASE veyro_cp TO veyro_cp_app;
GRANT USAGE ON SCHEMA plt01_platform TO veyro_cp_migrator;
GRANT REFERENCES (tenant_id) ON plt01_platform.tenants TO veyro_cp_migrator;
