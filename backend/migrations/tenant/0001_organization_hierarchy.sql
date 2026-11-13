-- MOD-004 PLT-01-R02/R03 tenant track: the organization hierarchy spine, tenant-isolated.
--
-- Every table here carries the same four protections, and the combination is what isolation
-- rests on -- no single one of them is sufficient:
--
--   1. `tenant_id uuid NOT NULL` with a tenant-leading primary key, so a row cannot exist
--      outside a tenant and every index scan starts from one.
--   2. ENABLE plus FORCE ROW LEVEL SECURITY. FORCE matters: without it the table owner reads
--      every row, and the owner is the migrator role the application could be misconfigured to
--      connect as.
--   3. A policy whose predicate reads `app.tenant_id` with `current_setting(..., true)`. When
--      the setting is absent that call returns NULL, `NULLIF(NULL, '')` is NULL, and
--      `tenant_id = NULL` is NULL rather than true -- so an unset context selects no rows and
--      inserts nothing. Isolation fails closed, which is the property `0002_isolation.sql`
--      under backend/tests/sql proves rather than assumes.
--   4. Composite foreign keys that carry `tenant_id` into every parent reference. A child whose
--      parent belongs to another tenant is rejected by the database, not by application code,
--      so hierarchy containment holds even against a bug in the service layer.
--
-- The context is set with `SET LOCAL` inside a transaction (see backend/app/db.py), never at
-- session level: a pooled connection handed to the next request must not carry the previous
-- request's tenant.
--
-- Scope: organization, legal entity, brand and location. PLT-01-R02 also names department and
-- cost centre; nothing reads them yet, so they are not created here. They follow this exact
-- pattern when a module needs them.

CREATE TABLE plt01.organizations (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    organization_id uuid NOT NULL DEFAULT gen_random_uuid(),
    legal_name text NOT NULL,
    country_code text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, organization_id),
    CONSTRAINT organizations_country_code_shape CHECK (country_code ~ '^[A-Z]{2}$')
);
ALTER TABLE plt01.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.organizations FORCE ROW LEVEL SECURITY;
CREATE POLICY organizations_tenant ON plt01.organizations
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE plt01.legal_entities (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    legal_entity_id uuid NOT NULL DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    registered_name text NOT NULL,
    tax_number text,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, legal_entity_id),
    FOREIGN KEY (tenant_id, organization_id)
        REFERENCES plt01.organizations (tenant_id, organization_id)
);
ALTER TABLE plt01.legal_entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.legal_entities FORCE ROW LEVEL SECURITY;
CREATE POLICY legal_entities_tenant ON plt01.legal_entities
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE plt01.brands (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    brand_id uuid NOT NULL DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    brand_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, brand_id),
    FOREIGN KEY (tenant_id, organization_id)
        REFERENCES plt01.organizations (tenant_id, organization_id),
    UNIQUE (tenant_id, organization_id, brand_name)
);
ALTER TABLE plt01.brands ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.brands FORCE ROW LEVEL SECURITY;
CREATE POLICY brands_tenant ON plt01.brands
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE plt01.locations (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    location_id uuid NOT NULL DEFAULT gen_random_uuid(),
    brand_id uuid NOT NULL,
    location_name text NOT NULL,
    timezone text NOT NULL,
    opened_on date,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, location_id),
    FOREIGN KEY (tenant_id, brand_id) REFERENCES plt01.brands (tenant_id, brand_id)
);
ALTER TABLE plt01.locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.locations FORCE ROW LEVEL SECURITY;
CREATE POLICY locations_tenant ON plt01.locations
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- D6.2: neither runtime role gets TRUNCATE or REFERENCES, and `veyro_cp_app` additionally gets
-- no DELETE -- removal in a tenant-facing request path goes through the worker, which runs
-- under its own reviewed code path.
GRANT SELECT, INSERT, UPDATE ON plt01.organizations TO veyro_cp_app;
GRANT SELECT, INSERT, UPDATE ON plt01.legal_entities TO veyro_cp_app;
GRANT SELECT, INSERT, UPDATE ON plt01.brands TO veyro_cp_app;
GRANT SELECT, INSERT, UPDATE ON plt01.locations TO veyro_cp_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON plt01.organizations TO veyro_cp_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON plt01.legal_entities TO veyro_cp_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON plt01.brands TO veyro_cp_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON plt01.locations TO veyro_cp_worker;
