-- Legitimate: a view over no table at all, a view over a set-returning function, and a policy
-- written with ADR-0002 D3's prescribed predicate verbatim. The last is the one that matters:
-- an earlier revision of PERMISSIVE_POLICY rejected D3's own predicate, because the `true` in it
-- is current_setting's missing_ok argument -- the thing that produces D3's fail-closed contract --
-- and the whole corpus had quietly adopted a different predicate to get past it.
CREATE TABLE plt01.brand_appearance (
    tenant_id uuid NOT NULL,
    brand_id uuid NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    PRIMARY KEY (tenant_id, brand_id),
    FOREIGN KEY (tenant_id) REFERENCES plt01_platform.tenants (tenant_id)
);
ALTER TABLE plt01.brand_appearance ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.brand_appearance FORCE ROW LEVEL SECURITY;
CREATE POLICY brand_appearance_tenant ON plt01.brand_appearance
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE VIEW plt01.probe WITH (security_invoker = true) AS SELECT g AS n FROM generate_series(1, 3) g;
CREATE VIEW plt01.one WITH (security_invoker = true) AS SELECT 1 AS n;
