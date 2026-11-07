-- A disjunct that is neither the word true nor arithmetic: any OR can widen, so all are refused.
CREATE POLICY brand_appearance_tenant ON plt01.brand_appearance
    FOR ALL TO veyro_cp_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
           OR current_setting('app.is_admin', true)::boolean);
