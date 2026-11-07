-- D2.1 is [SRC]: every tenant-owned table has `tenant_id UUID NOT NULL`. A text column changes
-- the policy comparison semantics; the name alone was not enough.
CREATE TABLE plt01.brand_appearance (
    tenant_id text NOT NULL,
    brand_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, brand_id)
);
ALTER TABLE plt01.brand_appearance ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.brand_appearance FORCE ROW LEVEL SECURITY;
CREATE POLICY brand_appearance_tenant ON plt01.brand_appearance
    FOR ALL TO veyro_cp_app
    USING (tenant_id = current_setting('app.tenant_id', false));
