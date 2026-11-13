-- MOD-004 PLT-01-R03 tenant-isolation negative tests.
--
-- Run against a database with the three migrations applied. Every check must FAIL CLOSED: the
-- script raises and aborts on the first violation, so a silent pass is not possible. These are
-- the live-catalog half that tools/migration_lint/migration_lint.py explicitly cannot provide --
-- it reads SQL text and never connects.
--
--   docker exec -i veyro-pg psql -v ON_ERROR_STOP=1 -U postgres -d veyro < backend/tests/sql/isolation.sql
--
-- Roles under test: veyro_cp_app (tenant-facing) and veyro_cp_migrator (table owner, exercised
-- so that FORCE ROW LEVEL SECURITY is proved rather than assumed).

\set ON_ERROR_STOP on
\set tenant_a '11111111-1111-4111-8111-111111111111'
\set tenant_b '22222222-2222-4222-8222-222222222222'
\set actor    '33333333-3333-4333-8333-333333333333'

-- ---------------------------------------------------------------- seed (platform plane)
BEGIN;
SET LOCAL ROLE veyro_cp_platform;
INSERT INTO plt01_platform.tenants (tenant_id, external_key, display_name, status, region)
VALUES (:'tenant_a', 'acme-fitness', 'Acme Fitness', 'active', 'eu-west'),
       (:'tenant_b', 'rival-gyms',   'Rival Gyms',   'active', 'eu-west');
INSERT INTO plt01_platform.tenant_lifecycle_history
    (tenant_id, from_status, to_status, command, actor_id, correlation_id)
VALUES (:'tenant_a', NULL, 'provisioned', 'ProvisionTenant', :'actor', :'actor'),
       (:'tenant_b', NULL, 'provisioned', 'ProvisionTenant', :'actor', :'actor');
COMMIT;

-- Seed tenant rows through the tenant-facing role, each inside its own tenant context. There is
-- no other way in: the migrator owns these tables but no policy names it, so with FORCE RLS it
-- is denied by default and cannot seed them.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
INSERT INTO plt01.organizations (tenant_id, organization_id, legal_name, country_code)
VALUES (:'tenant_a', 'aaaaaaaa-0000-4000-8000-000000000001', 'Acme Fitness ehf', 'IS');
INSERT INTO plt01.brands (tenant_id, brand_id, organization_id, brand_name)
VALUES (:'tenant_a', 'aaaaaaaa-0000-4000-8000-000000000002',
        'aaaaaaaa-0000-4000-8000-000000000001', 'Acme City');
INSERT INTO plt01.legal_entities (tenant_id, legal_entity_id, organization_id, registered_name, tax_number)
VALUES (:'tenant_a', 'aaaaaaaa-0000-4000-8000-000000000003',
        'aaaaaaaa-0000-4000-8000-000000000001', 'Acme Fitness ehf', 'IS-5503'),
       (:'tenant_a', 'aaaaaaaa-0000-4000-8000-000000000004',
        'aaaaaaaa-0000-4000-8000-000000000001', 'Acme Holdings ehf', 'IS-5504');
INSERT INTO plt01.locations (tenant_id, brand_id, location_name, timezone)
VALUES (:'tenant_a', 'aaaaaaaa-0000-4000-8000-000000000002', 'Acme Laugavegur', 'Atlantic/Reykjavik');
COMMIT;

BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
INSERT INTO plt01.organizations (tenant_id, organization_id, legal_name, country_code)
VALUES (:'tenant_b', 'bbbbbbbb-0000-4000-8000-000000000001', 'Rival Gyms ehf', 'IS');
COMMIT;

-- ---------------------------------------------------------------- 1. own rows are visible
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    IF (SELECT count(*) FROM plt01.organizations) <> 1 THEN
        RAISE EXCEPTION 'CHECK 1 FAILED: tenant A sees % of its own organizations, expected 1',
            (SELECT count(*) FROM plt01.organizations);
    END IF;
END $$;
COMMIT;

-- ---------------------------------------------------------------- 2. no cross-tenant read
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM plt01.organizations
               WHERE tenant_id = '11111111-1111-4111-8111-111111111111') THEN
        RAISE EXCEPTION 'CHECK 2 FAILED: tenant B read tenant A rows';
    END IF;
    IF (SELECT count(*) FROM plt01.brands) <> 0 THEN
        RAISE EXCEPTION 'CHECK 2 FAILED: tenant B sees % brands, expected 0',
            (SELECT count(*) FROM plt01.brands);
    END IF;
END $$;
COMMIT;

-- ---------------------------------------------------------------- 3. unset context reads nothing
-- The central fail-closed property. current_setting('app.tenant_id', true) is NULL when unset,
-- so the predicate is NULL, not true, and the scan returns no rows.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
DO $$
BEGIN
    IF (SELECT count(*) FROM plt01.organizations) <> 0 THEN
        RAISE EXCEPTION 'CHECK 3 FAILED: unset tenant context read % rows -- isolation fails OPEN',
            (SELECT count(*) FROM plt01.organizations);
    END IF;
END $$;
COMMIT;

-- ---------------------------------------------------------------- 4. unset context cannot write
BEGIN;
SET LOCAL ROLE veyro_cp_app;
DO $$
BEGIN
    BEGIN
        INSERT INTO plt01.organizations (tenant_id, legal_name, country_code)
        VALUES ('11111111-1111-4111-8111-111111111111', 'smuggled', 'IS');
        RAISE EXCEPTION 'CHECK 4 FAILED: insert succeeded with no tenant context';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 5. no cross-tenant write
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    BEGIN
        INSERT INTO plt01.organizations (tenant_id, legal_name, country_code)
        VALUES ('22222222-2222-4222-8222-222222222222', 'planted', 'IS');
        RAISE EXCEPTION 'CHECK 5 FAILED: tenant A wrote a row owned by tenant B';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 6. no cross-tenant UPDATE escape
-- USING hides the row, so the UPDATE matches nothing; WITH CHECK separately bars relabelling a
-- row into another tenant. Both are asserted.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
DECLARE touched integer;
BEGIN
    UPDATE plt01.organizations SET legal_name = 'hijacked'
    WHERE tenant_id = '22222222-2222-4222-8222-222222222222';
    GET DIAGNOSTICS touched = ROW_COUNT;
    IF touched <> 0 THEN
        RAISE EXCEPTION 'CHECK 6 FAILED: tenant A updated % of tenant B rows', touched;
    END IF;
    BEGIN
        UPDATE plt01.organizations
        SET tenant_id = '22222222-2222-4222-8222-222222222222';
        RAISE EXCEPTION 'CHECK 6 FAILED: a row was relabelled into another tenant';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 7. composite FK blocks cross-tenant parents
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    BEGIN
        INSERT INTO plt01.brands (tenant_id, organization_id, brand_name)
        VALUES ('11111111-1111-4111-8111-111111111111',
                'bbbbbbbb-0000-4000-8000-000000000001', 'stolen parent');
        RAISE EXCEPTION 'CHECK 7 FAILED: a brand was parented to another tenant''s organization';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 8. FORCE RLS binds the owner
-- Without FORCE, the table owner reads every row regardless of policy. The migrator owns these
-- tables and no policy names it, so it must see nothing at all.
BEGIN;
SET LOCAL ROLE veyro_cp_migrator;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    IF (SELECT count(*) FROM plt01.organizations) <> 0 THEN
        RAISE EXCEPTION 'CHECK 8 FAILED: the table owner read % rows -- FORCE RLS is not binding',
            (SELECT count(*) FROM plt01.organizations);
    END IF;
END $$;
COMMIT;

-- ---------------------------------------------------------------- 9. app role cannot reach the registry
BEGIN;
SET LOCAL ROLE veyro_cp_app;
DO $$
BEGIN
    BEGIN
        PERFORM count(*) FROM plt01_platform.tenants;
        RAISE EXCEPTION 'CHECK 9 FAILED: the tenant-facing role enumerated the tenant registry';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 10. app role holds no DELETE
-- Asserted twice, and deliberately. The behavioural half targets `locations`, which has no
-- child table: an earlier revision deleted from `organizations`, where a foreign key from
-- `brands` refused the delete first, so the check passed while saying nothing about privilege.
-- The catalogue half is the one that cannot be satisfied by accident.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    IF has_table_privilege('veyro_cp_app', 'plt01.organizations', 'DELETE')
       OR has_table_privilege('veyro_cp_app', 'plt01.locations', 'DELETE') THEN
        RAISE EXCEPTION 'CHECK 10 FAILED: the tenant-facing role holds DELETE';
    END IF;
    IF has_table_privilege('veyro_cp_app', 'plt01.organizations', 'TRUNCATE')
       OR has_table_privilege('veyro_cp_app', 'plt01.organizations', 'REFERENCES')
       OR has_table_privilege('veyro_cp_worker', 'plt01.organizations', 'TRUNCATE')
       OR has_table_privilege('veyro_cp_worker', 'plt01.organizations', 'REFERENCES') THEN
        RAISE EXCEPTION 'CHECK 10 FAILED: a runtime role holds TRUNCATE or REFERENCES';
    END IF;
    BEGIN
        DELETE FROM plt01.locations;
        RAISE EXCEPTION 'CHECK 10 FAILED: the tenant-facing role deleted tenant rows';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 11. context is transaction-local
-- A pooled connection must not carry the previous request's tenant. SET LOCAL is discarded at
-- COMMIT, so the next transaction on the same session starts with no context and reads nothing.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
COMMIT;
BEGIN;
SET LOCAL ROLE veyro_cp_app;
DO $$
BEGIN
    IF current_setting('app.tenant_id', true) NOT IN ('') IS TRUE THEN
        RAISE EXCEPTION 'CHECK 11 FAILED: tenant context survived the transaction as %',
            current_setting('app.tenant_id', true);
    END IF;
    IF (SELECT count(*) FROM plt01.organizations) <> 0 THEN
        RAISE EXCEPTION 'CHECK 11 FAILED: a reused session still reads the previous tenant';
    END IF;
END $$;
COMMIT;

-- ---------------------------------------------------------------- 12. lifecycle history is append-only
BEGIN;
SET LOCAL ROLE veyro_cp_platform;
DO $$
BEGIN
    BEGIN
        UPDATE plt01_platform.tenant_lifecycle_history SET to_status = 'rewritten';
        RAISE EXCEPTION 'CHECK 12 FAILED: lifecycle history was updated';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        DELETE FROM plt01_platform.tenant_lifecycle_history;
        RAISE EXCEPTION 'CHECK 12 FAILED: lifecycle history was deleted';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 13. legal entities isolate too
-- Every tenant table carries the same protections, so every tenant table is asserted. Covering
-- only the tables a reviewer happens to think of is how a gap survives: the project's own
-- migration lint refused this file until this check existed.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
BEGIN
    IF (SELECT count(*) FROM plt01.legal_entities) <> 0 THEN
        RAISE EXCEPTION 'CHECK 13 FAILED: tenant B sees % legal entities, expected 0',
            (SELECT count(*) FROM plt01.legal_entities);
    END IF;
    IF (SELECT count(*) FROM plt01.locations) <> 0 THEN
        RAISE EXCEPTION 'CHECK 13 FAILED: tenant B sees % locations, expected 0',
            (SELECT count(*) FROM plt01.locations);
    END IF;
    BEGIN
        INSERT INTO plt01.legal_entities (tenant_id, organization_id, registered_name)
        VALUES ('22222222-2222-4222-8222-222222222222',
                'aaaaaaaa-0000-4000-8000-000000000001', 'parented across tenants');
        RAISE EXCEPTION 'CHECK 13 FAILED: a legal entity was parented across tenants';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
        WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    IF (SELECT count(*) FROM plt01.legal_entities) <> 2 THEN
        RAISE EXCEPTION 'CHECK 13 FAILED: tenant A sees % of its 2 legal entities',
            (SELECT count(*) FROM plt01.legal_entities);
    END IF;
END $$;
COMMIT;

\echo 'tenant isolation: 13/13 checks passed'
