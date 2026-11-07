-- Legitimate: a tenant table in a schema other than plt01, fully protected. The tenant track now
-- treats any non-platform table as a tenant table, so this must pass on its protections rather
-- than on its schema name -- and an unprotected one in the same schema must fail, which an
-- earlier revision let through entirely.
CREATE TABLE plt01_v2.brand_appearance (
    tenant_id uuid NOT NULL,
    brand_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, brand_id),
    FOREIGN KEY (tenant_id) REFERENCES plt01_platform.tenants (tenant_id)
);
ALTER TABLE plt01_v2.brand_appearance ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01_v2.brand_appearance FORCE ROW LEVEL SECURITY;
CREATE POLICY brand_appearance_tenant ON plt01_v2.brand_appearance
    FOR ALL TO veyro_cp_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
