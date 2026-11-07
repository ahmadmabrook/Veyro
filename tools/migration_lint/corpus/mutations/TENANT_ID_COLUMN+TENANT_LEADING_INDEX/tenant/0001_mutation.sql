-- Mutation: the new tenant table carries no tenant_id column, so it also has no
-- tenant_id-leading key. Both are declared.
-- The policy below restricts by tenant_id deliberately: an earlier revision of this fixture used
-- `USING (true)`, which made the corpus record a permissive policy as expected clean behaviour.
CREATE TABLE plt01.brand_appearance (
    brand_id uuid NOT NULL,
    accent_color text NOT NULL,
    PRIMARY KEY (brand_id),
    FOREIGN KEY (tenant_id) REFERENCES plt01_platform.tenants (tenant_id)
);
ALTER TABLE plt01.brand_appearance ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.brand_appearance FORCE ROW LEVEL SECURITY;
CREATE POLICY brand_appearance_tenant ON plt01.brand_appearance
    FOR ALL TO veyro_cp_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
