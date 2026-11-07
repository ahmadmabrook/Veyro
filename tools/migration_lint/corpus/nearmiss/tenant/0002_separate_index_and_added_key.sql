-- Legitimate: the tenant-leading index arrives as a separate CREATE INDEX, and a later ALTER adds
-- a constraint alongside other clauses. `_paren_body` used to read the FIRST paren group, so
-- `ADD COLUMN fee numeric(10,2), ADD PRIMARY KEY (tenant_id, id)` was read as the column (10,2).
CREATE TABLE plt01.brand_appearance (
    tenant_id uuid NOT NULL,
    brand_id uuid NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES plt01_platform.tenants (tenant_id)
);
CREATE INDEX brand_appearance_tenant_idx ON plt01.brand_appearance (tenant_id, brand_id);
ALTER TABLE plt01.brand_appearance ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.brand_appearance FORCE ROW LEVEL SECURITY;
ALTER TABLE plt01.brand_appearance ADD COLUMN fee numeric(10,2), ADD PRIMARY KEY (tenant_id, brand_id);
CREATE POLICY brand_appearance_tenant ON plt01.brand_appearance
    FOR ALL TO veyro_cp_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
