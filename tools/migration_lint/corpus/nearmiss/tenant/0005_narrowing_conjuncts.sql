-- Legitimate: a tenant predicate narrowed by further conjuncts, including a boolean column
-- compared against true and a nested OR. An AND can only narrow, and an OR inside a conjunct's
-- own parentheses cannot widen the whole predicate, so neither is a finding.
CREATE TABLE plt01.brand_appearance (
    tenant_id uuid NOT NULL,
    brand_id uuid NOT NULL,
    kind text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    PRIMARY KEY (tenant_id, brand_id),
    FOREIGN KEY (tenant_id) REFERENCES plt01_platform.tenants (tenant_id)
);
ALTER TABLE plt01.brand_appearance ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.brand_appearance FORCE ROW LEVEL SECURITY;
CREATE POLICY brand_appearance_tenant ON plt01.brand_appearance
    FOR ALL TO veyro_cp_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
           AND is_active = true
           AND (kind = 'primary' OR kind = 'secondary'));
GRANT SELECT, INSERT, UPDATE ON plt01.brand_appearance TO veyro_cp_app;
