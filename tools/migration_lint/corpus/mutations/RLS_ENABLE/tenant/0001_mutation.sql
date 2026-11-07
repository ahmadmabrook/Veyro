-- Mutation: ENABLE ROW LEVEL SECURITY is missing.
CREATE TABLE plt01.brand_appearance (
    tenant_id uuid NOT NULL,
    brand_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, brand_id),
    FOREIGN KEY (tenant_id) REFERENCES plt01_platform.tenants (tenant_id)
);
ALTER TABLE plt01.brand_appearance FORCE ROW LEVEL SECURITY;
CREATE POLICY brand_appearance_tenant ON plt01.brand_appearance
    FOR ALL TO veyro_cp_app USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
