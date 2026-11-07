-- Unqualified, which the track rules read as this track's own schema. The previous rule needed
-- the literal string plt01 in the statement and missed this.
CREATE TABLE brand_theme (
    tenant_id uuid NOT NULL,
    PRIMARY KEY (tenant_id)
);
ALTER TABLE brand_theme ENABLE ROW LEVEL SECURITY;
ALTER TABLE brand_theme FORCE ROW LEVEL SECURITY;
CREATE POLICY brand_theme_tenant ON brand_theme
    FOR ALL TO veyro_cp_app USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
