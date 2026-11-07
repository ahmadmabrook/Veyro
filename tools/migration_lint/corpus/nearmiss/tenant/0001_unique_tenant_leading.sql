-- Legitimate: a UNIQUE constraint creates a tenant-leading index just as a primary key does, and
-- D15.10 item 2's own proposed schema uses `UNIQUE (tenant_id, brand_id)`.
CREATE TABLE plt01.brand_appearance (
    tenant_id uuid NOT NULL,
    brand_id uuid NOT NULL,
    accent_color text NOT NULL,
    UNIQUE (tenant_id, brand_id),
    FOREIGN KEY (tenant_id) REFERENCES plt01_platform.tenants (tenant_id)
);
ALTER TABLE plt01.brand_appearance ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.brand_appearance FORCE ROW LEVEL SECURITY;
CREATE POLICY brand_appearance_tenant ON plt01.brand_appearance
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
