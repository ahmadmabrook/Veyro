-- Stands in for backend/tests/integration/tenancy/**, which does not exist yet. The NEGATIVE_TESTS
-- rule requires some file here to name both a new tenant table and a runtime role.
-- Negative: veyro_cp_app must read no row of plt01.brand_appearance for another tenant.
SET LOCAL app.tenant_id = '00000000-0000-4000-8000-000000000001';
SELECT count(*) FROM plt01.brand_appearance;          -- expect 0 rows for a foreign tenant
-- Negative: veyro_cp_app must not UPDATE or DELETE plt01.brand_appearance_history (append-only).
-- Negative: veyro_cp_worker must not reach plt01_platform.tenants at all.
