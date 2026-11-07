-- Mutation: TRUNCATE to a runtime role. TRUNCATE ignores RLS, so this empties every tenant.
GRANT TRUNCATE ON plt01.brand_appearance TO veyro_cp_app;
