-- Mutation: the primary key does not lead with tenant_id, so every tenant-scoped read scans.
CREATE TABLE plt01.brand_appearance (
    tenant_id uuid NOT NULL,
    brand_id uuid NOT NULL,
    PRIMARY KEY (brand_id, tenant_id),
    FOREIGN KEY (tenant_id) REFERENCES plt01_platform.tenants (tenant_id)
);
ALTER TABLE plt01.brand_appearance ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.brand_appearance FORCE ROW LEVEL SECURITY;
CREATE POLICY brand_appearance_tenant ON plt01.brand_appearance
    FOR ALL TO veyro_cp_app USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
