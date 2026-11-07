-- Legitimate: an append-only history table granted only SELECT and INSERT, and the approved
-- transaction-local forms of the tenant-context setting.
CREATE TABLE plt01.brand_appearance_history (
    tenant_id uuid NOT NULL,
    brand_id uuid NOT NULL,
    version integer NOT NULL,
    PRIMARY KEY (tenant_id, brand_id, version),
    FOREIGN KEY (tenant_id) REFERENCES plt01_platform.tenants (tenant_id)
);
ALTER TABLE plt01.brand_appearance_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.brand_appearance_history FORCE ROW LEVEL SECURITY;
CREATE POLICY brand_appearance_history_tenant ON plt01.brand_appearance_history
    FOR ALL TO veyro_cp_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
GRANT SELECT, INSERT ON plt01.brand_appearance_history TO veyro_cp_app;
SET LOCAL app.tenant_id = '00000000-0000-4000-8000-000000000001';
SELECT set_config('app.tenant_id', '00000000-0000-4000-8000-000000000001', true);
