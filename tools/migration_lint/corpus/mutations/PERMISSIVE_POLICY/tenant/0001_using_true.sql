-- Mutation: a policy that ticks every D5-listed box and isolates nothing.
CREATE POLICY brand_appearance_tenant ON plt01.brand_appearance
    FOR ALL TO veyro_cp_app USING (true) WITH CHECK (true);
