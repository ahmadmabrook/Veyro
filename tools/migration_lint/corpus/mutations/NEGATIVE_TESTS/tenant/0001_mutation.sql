-- Mutation: a fully protected tenant table that no runtime-role negative test names.
CREATE TABLE plt01.unwitnessed (
    tenant_id uuid NOT NULL,
    payload text NOT NULL,
    PRIMARY KEY (tenant_id, payload),
    FOREIGN KEY (tenant_id) REFERENCES plt01_platform.tenants (tenant_id)
);
ALTER TABLE plt01.unwitnessed ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.unwitnessed FORCE ROW LEVEL SECURITY;
CREATE POLICY unwitnessed_tenant ON plt01.unwitnessed
    FOR ALL TO veyro_cp_app USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
