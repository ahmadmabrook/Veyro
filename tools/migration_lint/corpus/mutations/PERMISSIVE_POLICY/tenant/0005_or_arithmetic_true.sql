-- Same violation with the constant written arithmetically. An existential word-`true` test passed
-- this while rejecting ADR-0002 D3's own prescribed predicate, which is why the check reads the
-- body as a conjunction instead.
CREATE POLICY brand_appearance_tenant ON plt01.brand_appearance
    FOR ALL TO veyro_cp_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid OR 1=1);
