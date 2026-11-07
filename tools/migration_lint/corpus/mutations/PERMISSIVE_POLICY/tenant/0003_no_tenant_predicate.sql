-- Same violation, written as a predicate on the wrong column.
CREATE POLICY brand_appearance_tenant ON plt01.brand_appearance
    FOR ALL TO veyro_cp_app USING (brand_id IS NOT NULL);
