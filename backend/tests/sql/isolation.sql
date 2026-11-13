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

-- ================================================================ MOD-005 PLT-02 (cfg_* tables)
-- The configuration and flag tables repeat PLT-01's protections, so they get the same
-- interrogation rather than being trusted to have copied it correctly. Two of them are
-- additionally insert-only in the privilege layer; checks 19 and 20 are what make that a fact
-- about the database rather than a claim in a migration comment.

-- ---------------------------------------------------------------- seed (tenant plane, MOD-005)
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
INSERT INTO plt01.cfg_definitions
    (tenant_id, definition_id, config_key, value_type, default_value, owner_module)
VALUES (:'tenant_a', 'cccccccc-0000-4000-8000-000000000001',
        'checkin.grace_minutes', 'integer', '15'::jsonb, 'MOD-005');
INSERT INTO plt01.cfg_values
    (tenant_id, definition_id, scope_type, value, version, published_by, correlation_id)
VALUES (:'tenant_a', 'cccccccc-0000-4000-8000-000000000001', 'tenant',
        '20'::jsonb, 1, :'actor', :'actor');
INSERT INTO plt01.cfg_flags (tenant_id, flag_id, flag_key, enabled, default_variant)
VALUES (:'tenant_a', 'cccccccc-0000-4000-8000-000000000002', 'pay.new_provider', true, 'off');
INSERT INTO plt01.cfg_flag_rules (tenant_id, flag_id, priority, match, rollout_bp, variant)
VALUES (:'tenant_a', 'cccccccc-0000-4000-8000-000000000002', 1, '{}'::jsonb, 5000, 'on');
INSERT INTO plt01.cfg_experiments (tenant_id, experiment_id, experiment_key, status, salt)
VALUES (:'tenant_a', 'cccccccc-0000-4000-8000-000000000003',
        'checkout.copy', 'running', 'seed-salt');
INSERT INTO plt01.cfg_variants (tenant_id, experiment_id, variant_key, weight)
VALUES (:'tenant_a', 'cccccccc-0000-4000-8000-000000000003', 'control', 1),
       (:'tenant_a', 'cccccccc-0000-4000-8000-000000000003', 'treatment', 1);
INSERT INTO plt01.cfg_exposures (tenant_id, experiment_id, subject_id, variant_key)
VALUES (:'tenant_a', 'cccccccc-0000-4000-8000-000000000003', 'member-1', 'control');
COMMIT;

-- ---------------------------------------------------------------- 14. cfg tables isolate
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['cfg_definitions', 'cfg_values', 'cfg_flags', 'cfg_flag_rules',
                               'cfg_experiments', 'cfg_variants', 'cfg_exposures'] LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 14 FAILED: tenant B sees % rows in plt01.%', seen, tbl;
        END IF;
    END LOOP;
END $$;
ROLLBACK;

BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    IF (SELECT count(*) FROM plt01.cfg_definitions) <> 1
       OR (SELECT count(*) FROM plt01.cfg_flags) <> 1
       OR (SELECT count(*) FROM plt01.cfg_exposures) <> 1 THEN
        RAISE EXCEPTION 'CHECK 14 FAILED: tenant A cannot see its own configuration rows';
    END IF;
END $$;
COMMIT;

-- ---------------------------------------------------------------- 15. unset context, cfg tables
-- The same fail-closed property as check 3, asserted on the new tables. A policy copied with a
-- typo in the GUC name would still read as correct and would still return every row here.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['cfg_definitions', 'cfg_values', 'cfg_flags', 'cfg_flag_rules',
                               'cfg_experiments', 'cfg_variants', 'cfg_exposures'] LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION
                'CHECK 15 FAILED: unset context read % rows from plt01.% -- fails OPEN', seen, tbl;
        END IF;
    END LOOP;
    BEGIN
        INSERT INTO plt01.cfg_flags (tenant_id, flag_key)
        VALUES ('11111111-1111-4111-8111-111111111111', 'written.without_context');
        RAISE EXCEPTION 'CHECK 15 FAILED: insert into cfg_flags succeeded with no context';
    EXCEPTION
        WHEN check_violation THEN NULL;
        WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 16. cross-tenant parents
-- Every composite foreign key is exercised from the wrong tenant. Containment must be the
-- database's answer, not the service's.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
BEGIN
    BEGIN
        INSERT INTO plt01.cfg_values
            (tenant_id, definition_id, scope_type, value, version, published_by, correlation_id)
        VALUES ('22222222-2222-4222-8222-222222222222',
                'cccccccc-0000-4000-8000-000000000001', 'tenant', '99'::jsonb, 1,
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 16 FAILED: a value was attached to another tenant''s definition';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.cfg_flag_rules (tenant_id, flag_id, priority, variant)
        VALUES ('22222222-2222-4222-8222-222222222222',
                'cccccccc-0000-4000-8000-000000000002', 1, 'on');
        RAISE EXCEPTION 'CHECK 16 FAILED: a rule was attached to another tenant''s flag';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.cfg_variants (tenant_id, experiment_id, variant_key, weight)
        VALUES ('22222222-2222-4222-8222-222222222222',
                'cccccccc-0000-4000-8000-000000000003', 'stolen', 1);
        RAISE EXCEPTION 'CHECK 16 FAILED: a variant was attached to another tenant''s experiment';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.cfg_exposures (tenant_id, experiment_id, subject_id, variant_key)
        VALUES ('22222222-2222-4222-8222-222222222222',
                'cccccccc-0000-4000-8000-000000000003', 'member-9', 'control');
        RAISE EXCEPTION 'CHECK 16 FAILED: an exposure was recorded against another tenant''s experiment';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 17. FORCE RLS binds the owner
BEGIN;
SET LOCAL ROLE veyro_cp_migrator;
DO $$
DECLARE
    forced boolean;
BEGIN
    IF (SELECT count(*) FROM plt01.cfg_flags) <> 0 THEN
        RAISE EXCEPTION 'CHECK 17 FAILED: the table owner read % cfg_flags rows',
            (SELECT count(*) FROM plt01.cfg_flags);
    END IF;
    -- relkind 'r' only: pg_class also holds this schema's indexes, and an index never carries
    -- row security, so matching on the name alone reports every table as unprotected.
    FOR forced IN
        SELECT relforcerowsecurity FROM pg_class
        WHERE relnamespace = 'plt01'::regnamespace AND relkind = 'r' AND relname LIKE 'cfg\_%'
    LOOP
        IF NOT forced THEN
            RAISE EXCEPTION 'CHECK 17 FAILED: a cfg_ table does not FORCE row level security';
        END IF;
    END LOOP;
    IF (SELECT count(*) FROM pg_class
        WHERE relnamespace = 'plt01'::regnamespace AND relkind = 'r' AND relname LIKE 'cfg\_%'
          AND relrowsecurity AND relforcerowsecurity) <> 7 THEN
        RAISE EXCEPTION 'CHECK 17 FAILED: expected 7 cfg_ tables with RLS enabled and forced, got %',
            (SELECT count(*) FROM pg_class
             WHERE relnamespace = 'plt01'::regnamespace AND relkind = 'r'
               AND relname LIKE 'cfg\_%' AND relrowsecurity AND relforcerowsecurity);
    END IF;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 18. the CHECKs actually bite
-- A constraint nobody tests is a comment. These three carry product meaning: a kill switch
-- without a reason, a scope that names the wrong target, and a rollout outside 0-100%.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    BEGIN
        UPDATE plt01.cfg_flags SET kill_switch_engaged = true
        WHERE flag_id = 'cccccccc-0000-4000-8000-000000000002';
        RAISE EXCEPTION 'CHECK 18 FAILED: a kill switch was engaged with no reason';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
END $$;
ROLLBACK;

BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    BEGIN
        INSERT INTO plt01.cfg_values
            (tenant_id, definition_id, scope_type, brand_id, value, version,
             published_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111',
                'cccccccc-0000-4000-8000-000000000001', 'tenant',
                'aaaaaaaa-0000-4000-8000-000000000002', '1'::jsonb, 9,
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 18 FAILED: a tenant-scoped value carried a brand target';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.cfg_flag_rules (tenant_id, flag_id, priority, rollout_bp, variant)
        VALUES ('11111111-1111-4111-8111-111111111111',
                'cccccccc-0000-4000-8000-000000000002', 9, 10001, 'on');
        RAISE EXCEPTION 'CHECK 18 FAILED: a rollout above 100%% was accepted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 19. cfg_values is append-only
-- Published configuration is history. The privilege is asserted directly rather than inferred
-- from a failed statement, because a statement can fail for the wrong reason -- that mistake was
-- already made once in this file, at check 10, and caught by mutation testing.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    IF has_table_privilege('veyro_cp_app', 'plt01.cfg_values', 'UPDATE')
       OR has_table_privilege('veyro_cp_app', 'plt01.cfg_values', 'DELETE')
       OR has_table_privilege('veyro_cp_worker', 'plt01.cfg_values', 'UPDATE')
       OR has_table_privilege('veyro_cp_worker', 'plt01.cfg_values', 'DELETE') THEN
        RAISE EXCEPTION 'CHECK 19 FAILED: a runtime role can rewrite published configuration';
    END IF;
    IF NOT has_table_privilege('veyro_cp_app', 'plt01.cfg_values', 'INSERT') THEN
        RAISE EXCEPTION 'CHECK 19 FAILED: configuration cannot be published at all';
    END IF;
    BEGIN
        UPDATE plt01.cfg_values SET value = '0'::jsonb;
        RAISE EXCEPTION 'CHECK 19 FAILED: a published value was rewritten';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 20. cfg_exposures append-only
-- What a subject was shown cannot be revised after the fact, or an experiment's result can be
-- edited into whatever the reader wanted.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    IF has_table_privilege('veyro_cp_app', 'plt01.cfg_exposures', 'UPDATE')
       OR has_table_privilege('veyro_cp_app', 'plt01.cfg_exposures', 'DELETE')
       OR has_table_privilege('veyro_cp_worker', 'plt01.cfg_exposures', 'UPDATE')
       OR has_table_privilege('veyro_cp_worker', 'plt01.cfg_exposures', 'DELETE') THEN
        RAISE EXCEPTION 'CHECK 20 FAILED: a runtime role can rewrite recorded exposures';
    END IF;
    BEGIN
        UPDATE plt01.cfg_exposures SET variant_key = 'treatment';
        RAISE EXCEPTION 'CHECK 20 FAILED: a recorded exposure was rewritten';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.cfg_exposures (tenant_id, experiment_id, subject_id, variant_key)
        VALUES ('11111111-1111-4111-8111-111111111111',
                'cccccccc-0000-4000-8000-000000000003', 'member-1', 'treatment');
        RAISE EXCEPTION 'CHECK 20 FAILED: a subject was exposed twice to one experiment';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;
END $$;
ROLLBACK;

-- ================================================================ MOD-015 PLT-03 (bil_* tables)
-- Nine more tenant tables, five of them the billing ledger. The ledger tables get the same
-- interrogation as every other table plus a direct assertion that no runtime role can revise
-- them, because "financial correctness" is not a property anyone can read off a schema.

-- ---------------------------------------------------------------- seed (tenant plane, MOD-015)
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
INSERT INTO plt01.bil_subscriptions
    (tenant_id, subscription_id, plan_code, plan_version, terms, status, currency,
     billing_interval, period_start, period_end, started_on)
VALUES (:'tenant_a', 'dddddddd-0000-4000-8000-000000000001', 'growth', 1,
        '{"base_price_minor": 29900}'::jsonb, 'active', 'EUR', 'monthly',
        DATE '2026-11-01', DATE '2026-12-01', DATE '2026-11-01');
INSERT INTO plt01.bil_subscription_changes
    (tenant_id, subscription_id, change_kind, to_plan_code, to_plan_version, to_status,
     effective_on, actor_id, correlation_id)
VALUES (:'tenant_a', 'dddddddd-0000-4000-8000-000000000001', 'start', 'growth', 1, 'active',
        DATE '2026-11-01', :'actor', :'actor');
INSERT INTO plt01.bil_entitlements
    (tenant_id, subscription_id, feature_code, limit_value)
VALUES (:'tenant_a', 'dddddddd-0000-4000-8000-000000000001', 'locations', 5);
INSERT INTO plt01.bil_usage_meters (tenant_id, meter_id, meter_code, unit)
VALUES (:'tenant_a', 'dddddddd-0000-4000-8000-000000000002', 'messaging.sms', 'message');
INSERT INTO plt01.bil_usage_records
    (tenant_id, record_id, meter_id, idempotency_key, quantity, occurred_at,
     actor_id, correlation_id)
VALUES (:'tenant_a', 'dddddddd-0000-4000-8000-000000000003',
        'dddddddd-0000-4000-8000-000000000002', 'seed-key-1', 120,
        TIMESTAMPTZ '2026-11-05 10:00:00+00', :'actor', :'actor');
INSERT INTO plt01.bil_quotas (tenant_id, meter_id, period, limit_quantity, overage_allowed)
VALUES (:'tenant_a', 'dddddddd-0000-4000-8000-000000000002', 'billing_period', 1000, true);
INSERT INTO plt01.bil_invoices
    (tenant_id, invoice_id, invoice_number, subscription_id, currency, period_start, period_end,
     subtotal_minor, tax_minor, total_minor, correlation_id)
VALUES (:'tenant_a', 'dddddddd-0000-4000-8000-000000000004', 'INV-SEED-1',
        'dddddddd-0000-4000-8000-000000000001', 'EUR', DATE '2026-11-01', DATE '2026-12-01',
        29900, 7176, 37076, :'actor');
INSERT INTO plt01.bil_invoice_lines
    (tenant_id, invoice_id, line_no, kind, description, quantity, unit_price_minor, amount_minor)
VALUES (:'tenant_a', 'dddddddd-0000-4000-8000-000000000004', 1, 'base', 'Growth monthly',
        1, 29900, 29900);
INSERT INTO plt01.bil_credit_notes
    (tenant_id, credit_note_number, invoice_id, amount_minor, reason, actor_id, correlation_id)
VALUES (:'tenant_a', 'CN-SEED-1', 'dddddddd-0000-4000-8000-000000000004', 1000,
        'goodwill', :'actor', :'actor');
COMMIT;

-- ---------------------------------------------------------------- 21. bil tables isolate
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['bil_subscriptions', 'bil_subscription_changes',
                               'bil_entitlements', 'bil_usage_meters', 'bil_usage_records',
                               'bil_quotas', 'bil_invoices', 'bil_invoice_lines',
                               'bil_credit_notes'] LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 21 FAILED: tenant B sees % rows in plt01.%', seen, tbl;
        END IF;
    END LOOP;
END $$;
ROLLBACK;

BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    IF (SELECT count(*) FROM plt01.bil_invoices) <> 1
       OR (SELECT count(*) FROM plt01.bil_usage_records) <> 1
       OR (SELECT count(*) FROM plt01.bil_subscriptions) <> 1 THEN
        RAISE EXCEPTION 'CHECK 21 FAILED: tenant A cannot see its own billing rows';
    END IF;
END $$;
COMMIT;

-- ---------------------------------------------------------------- 22. fail closed, and FORCE
BEGIN;
SET LOCAL ROLE veyro_cp_app;
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['bil_subscriptions', 'bil_subscription_changes',
                               'bil_entitlements', 'bil_usage_meters', 'bil_usage_records',
                               'bil_quotas', 'bil_invoices', 'bil_invoice_lines',
                               'bil_credit_notes'] LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION
                'CHECK 22 FAILED: unset context read % rows from plt01.% -- fails OPEN', seen, tbl;
        END IF;
    END LOOP;
END $$;
ROLLBACK;

BEGIN;
SET LOCAL ROLE veyro_cp_migrator;
DO $$
BEGIN
    IF (SELECT count(*) FROM plt01.bil_invoices) <> 0 THEN
        RAISE EXCEPTION 'CHECK 22 FAILED: the table owner read % invoices',
            (SELECT count(*) FROM plt01.bil_invoices);
    END IF;
    IF (SELECT count(*) FROM pg_class
        WHERE relnamespace = 'plt01'::regnamespace AND relkind = 'r' AND relname LIKE 'bil\_%'
          AND relrowsecurity AND relforcerowsecurity) <> 9 THEN
        RAISE EXCEPTION 'CHECK 22 FAILED: expected 9 bil_ tables with RLS enabled and forced, got %',
            (SELECT count(*) FROM pg_class
             WHERE relnamespace = 'plt01'::regnamespace AND relkind = 'r'
               AND relname LIKE 'bil\_%' AND relrowsecurity AND relforcerowsecurity);
    END IF;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 23. cross-tenant parents
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
BEGIN
    BEGIN
        INSERT INTO plt01.bil_entitlements (tenant_id, subscription_id, feature_code, limit_value)
        VALUES ('22222222-2222-4222-8222-222222222222',
                'dddddddd-0000-4000-8000-000000000001', 'locations', 99);
        RAISE EXCEPTION 'CHECK 23 FAILED: an entitlement was attached across tenants';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.bil_usage_records
            (tenant_id, meter_id, idempotency_key, quantity, occurred_at, actor_id,
             correlation_id)
        VALUES ('22222222-2222-4222-8222-222222222222',
                'dddddddd-0000-4000-8000-000000000002', 'intruder', 1, now(),
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 23 FAILED: usage was recorded against another tenant''s meter';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.bil_invoice_lines
            (tenant_id, invoice_id, line_no, kind, description, quantity, unit_price_minor,
             amount_minor)
        VALUES ('22222222-2222-4222-8222-222222222222',
                'dddddddd-0000-4000-8000-000000000004', 9, 'base', 'stolen line', 1, 1, 1);
        RAISE EXCEPTION 'CHECK 23 FAILED: a line was added to another tenant''s invoice';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.bil_credit_notes
            (tenant_id, credit_note_number, invoice_id, amount_minor, reason, actor_id,
             correlation_id)
        VALUES ('22222222-2222-4222-8222-222222222222', 'CN-X',
                'dddddddd-0000-4000-8000-000000000004', 100, 'not mine',
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 23 FAILED: another tenant''s invoice was credited';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 24. the metering control
-- PLT-03's stated control is that metering records are idempotent, attributable and auditable.
-- Each word is asserted separately, because each is carried by a different mechanism.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    IF has_table_privilege('veyro_cp_app', 'plt01.bil_usage_records', 'UPDATE')
       OR has_table_privilege('veyro_cp_app', 'plt01.bil_usage_records', 'DELETE')
       OR has_table_privilege('veyro_cp_worker', 'plt01.bil_usage_records', 'UPDATE')
       OR has_table_privilege('veyro_cp_worker', 'plt01.bil_usage_records', 'DELETE')
       OR has_table_privilege('veyro_cp_app', 'plt01.bil_subscription_changes', 'UPDATE')
       OR has_table_privilege('veyro_cp_worker', 'plt01.bil_subscription_changes', 'DELETE') THEN
        RAISE EXCEPTION 'CHECK 24 FAILED: a runtime role can revise metering or change history';
    END IF;
    BEGIN
        UPDATE plt01.bil_usage_records SET quantity = 0;
        RAISE EXCEPTION 'CHECK 24 FAILED: a recorded quantity was rewritten';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.bil_usage_records
            (tenant_id, meter_id, idempotency_key, quantity, occurred_at, actor_id,
             correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111',
                'dddddddd-0000-4000-8000-000000000002', 'seed-key-1', 500, now(),
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 24 FAILED: a replayed idempotency key double-counted usage';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.bil_usage_records
            (tenant_id, meter_id, idempotency_key, quantity, occurred_at, actor_id,
             correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111',
                'dddddddd-0000-4000-8000-000000000002', 'negative-original', -5, now(),
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 24 FAILED: a negative quantity was recorded without correcting anything';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 25. the invoice ledger
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    IF has_table_privilege('veyro_cp_app', 'plt01.bil_invoices', 'UPDATE')
       OR has_table_privilege('veyro_cp_app', 'plt01.bil_invoices', 'DELETE')
       OR has_table_privilege('veyro_cp_worker', 'plt01.bil_invoices', 'UPDATE')
       OR has_table_privilege('veyro_cp_worker', 'plt01.bil_invoices', 'DELETE')
       OR has_table_privilege('veyro_cp_app', 'plt01.bil_invoice_lines', 'UPDATE')
       OR has_table_privilege('veyro_cp_worker', 'plt01.bil_invoice_lines', 'DELETE') THEN
        RAISE EXCEPTION 'CHECK 25 FAILED: a runtime role can rewrite an issued invoice';
    END IF;
    BEGIN
        UPDATE plt01.bil_invoices SET total_minor = 0;
        RAISE EXCEPTION 'CHECK 25 FAILED: an issued invoice total was rewritten';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    -- The arithmetic the database can check for itself must actually refuse bad arithmetic.
    BEGIN
        INSERT INTO plt01.bil_invoices
            (tenant_id, invoice_number, subscription_id, currency, period_start, period_end,
             subtotal_minor, tax_minor, total_minor, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'INV-BAD-TOTAL',
                'dddddddd-0000-4000-8000-000000000001', 'EUR', DATE '2026-12-01',
                DATE '2027-01-01', 10000, 2400, 99999,
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 25 FAILED: an invoice whose total is not subtotal plus tax was stored';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.bil_invoice_lines
            (tenant_id, invoice_id, line_no, kind, description, quantity, unit_price_minor,
             amount_minor)
        VALUES ('11111111-1111-4111-8111-111111111111',
                'dddddddd-0000-4000-8000-000000000004', 9, 'base', 'does not multiply out',
                3, 100, 250);
        RAISE EXCEPTION 'CHECK 25 FAILED: a line whose amount is not quantity times price was stored';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 26. credits, and one live sub
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    IF has_table_privilege('veyro_cp_app', 'plt01.bil_credit_notes', 'UPDATE')
       OR has_table_privilege('veyro_cp_app', 'plt01.bil_credit_notes', 'DELETE')
       OR has_table_privilege('veyro_cp_worker', 'plt01.bil_credit_notes', 'UPDATE')
       OR has_table_privilege('veyro_cp_worker', 'plt01.bil_credit_notes', 'DELETE') THEN
        RAISE EXCEPTION 'CHECK 26 FAILED: a runtime role can rewrite a credit note';
    END IF;
    BEGIN
        UPDATE plt01.bil_credit_notes SET amount_minor = 1;
        RAISE EXCEPTION 'CHECK 26 FAILED: a credit note was rewritten';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    -- A tenant on two live subscriptions would be billed twice, and no later code could decide
    -- which one was real.
    BEGIN
        INSERT INTO plt01.bil_subscriptions
            (tenant_id, plan_code, plan_version, terms, status, currency, billing_interval,
             period_start, period_end, started_on)
        VALUES ('11111111-1111-4111-8111-111111111111', 'scale', 1, '{}'::jsonb, 'active',
                'EUR', 'monthly', DATE '2026-11-01', DATE '2026-12-01', DATE '2026-11-01');
        RAISE EXCEPTION 'CHECK 26 FAILED: a tenant was given a second live subscription';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.bil_quotas
            (tenant_id, meter_id, period, limit_quantity, overage_allowed, hard_stop)
        VALUES ('11111111-1111-4111-8111-111111111111',
                'dddddddd-0000-4000-8000-000000000002', 'day', 10, true, true);
        RAISE EXCEPTION 'CHECK 26 FAILED: a quota both allowed overage and hard-stopped';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
END $$;
ROLLBACK;

-- ================================================================ MOD-007 IAM-01 (iam schema)
-- The identity plane is a different schema and a different role. Two properties have to hold and
-- both are asserted directly: tenants cannot see each other inside `iam` (check 28), and the
-- control plane and the identity plane cannot see each other at all (check 27). The second is
-- the reason the schema exists -- a mistake in a configuration or billing query must not be able
-- to read a credential hash.

-- ---------------------------------------------------------------- seed (identity plane)
BEGIN;
SET LOCAL ROLE veyro_iam_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
INSERT INTO iam.identities
    (tenant_id, identity_id, person_id, email_normalized, display_name)
VALUES (:'tenant_a', 'eeeeeeee-0000-4000-8000-000000000002',
        'eeeeeeee-0000-4000-8000-000000000001', 'staff@acme.test', 'Acme Staff');
INSERT INTO iam.credentials
    (tenant_id, credential_id, identity_id, kind, algorithm, salt, secret_hash)
VALUES (:'tenant_a', 'eeeeeeee-0000-4000-8000-000000000003',
        'eeeeeeee-0000-4000-8000-000000000002', 'password', 'scrypt',
        decode(repeat('ab', 16), 'hex'), decode(repeat('cd', 32), 'hex'));
INSERT INTO iam.devices (tenant_id, device_id, identity_id, fingerprint)
VALUES (:'tenant_a', 'eeeeeeee-0000-4000-8000-000000000004',
        'eeeeeeee-0000-4000-8000-000000000002', 'device-fingerprint-1');
INSERT INTO iam.sessions
    (tenant_id, session_id, identity_id, device_id, token_hash, expires_at)
VALUES (:'tenant_a', 'eeeeeeee-0000-4000-8000-000000000005',
        'eeeeeeee-0000-4000-8000-000000000002', 'eeeeeeee-0000-4000-8000-000000000004',
        decode(repeat('01', 32), 'hex'), now() + interval '1 hour');
INSERT INTO iam.passkeys
    (tenant_id, passkey_id, identity_id, webauthn_credential_id, public_key)
VALUES (:'tenant_a', 'eeeeeeee-0000-4000-8000-000000000006',
        'eeeeeeee-0000-4000-8000-000000000002',
        decode(repeat('02', 16), 'hex'), decode(repeat('03', 32), 'hex'));
INSERT INTO iam.challenges
    (tenant_id, identity_id, kind, nonce_hash, expires_at)
VALUES (:'tenant_a', 'eeeeeeee-0000-4000-8000-000000000002', 'step_up',
        decode(repeat('04', 32), 'hex'), now() + interval '5 minutes');
INSERT INTO iam.auth_events (tenant_id, identity_id, kind, outcome, correlation_id)
VALUES (:'tenant_a', 'eeeeeeee-0000-4000-8000-000000000002',
        'identity.created', 'succeeded', :'actor');
COMMIT;

-- ---------------------------------------------------------------- 27. the two planes are apart
BEGIN;
SET LOCAL ROLE veyro_cp_migrator;
DO $$
DECLARE
    tbl text;
BEGIN
    -- Neither direction may hold schema USAGE on the other's schema. Without USAGE no table
    -- privilege in that schema can be exercised, whatever else was granted by accident.
    IF has_schema_privilege('veyro_cp_app', 'iam', 'USAGE')
       OR has_schema_privilege('veyro_cp_worker', 'iam', 'USAGE')
       OR has_schema_privilege('veyro_cp_platform', 'iam', 'USAGE') THEN
        RAISE EXCEPTION 'CHECK 27 FAILED: a control-plane role can reach the iam schema';
    END IF;
    IF has_schema_privilege('veyro_iam_app', 'plt01', 'USAGE')
       OR has_schema_privilege('veyro_iam_app', 'plt01_platform', 'USAGE') THEN
        RAISE EXCEPTION 'CHECK 27 FAILED: the identity role can reach a control-plane schema';
    END IF;

    FOREACH tbl IN ARRAY ARRAY['identities', 'credentials', 'passkeys', 'devices', 'sessions',
                               'challenges', 'auth_events'] LOOP
        IF has_table_privilege('veyro_cp_app', 'iam.' || tbl, 'SELECT')
           OR has_table_privilege('veyro_cp_worker', 'iam.' || tbl, 'SELECT') THEN
            RAISE EXCEPTION 'CHECK 27 FAILED: a control-plane role holds SELECT on iam.%', tbl;
        END IF;
    END LOOP;
    FOREACH tbl IN ARRAY ARRAY['organizations', 'cfg_flags', 'bil_invoices'] LOOP
        IF has_table_privilege('veyro_iam_app', 'plt01.' || tbl, 'SELECT') THEN
            RAISE EXCEPTION 'CHECK 27 FAILED: the identity role holds SELECT on plt01.%', tbl;
        END IF;
    END LOOP;
    IF has_table_privilege('veyro_iam_app', 'plt01_platform.tenants', 'SELECT') THEN
        RAISE EXCEPTION 'CHECK 27 FAILED: the identity role can enumerate the tenant registry';
    END IF;

    -- No membership edge touching any veyro role, in either direction. One would hand a role
    -- every privilege of the other and make every assertion above decorative.
    IF (SELECT count(*) FROM pg_auth_members am
        JOIN pg_roles r ON r.oid = am.roleid
        JOIN pg_roles m ON m.oid = am.member
        WHERE r.rolname LIKE 'veyro\_%' OR m.rolname LIKE 'veyro\_%') <> 0 THEN
        RAISE EXCEPTION 'CHECK 27 FAILED: a veyro role is a member of another role';
    END IF;

    IF (SELECT count(*) FROM pg_roles
        WHERE rolname = 'veyro_iam_app'
          AND (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb)) <> 0 THEN
        RAISE EXCEPTION 'CHECK 27 FAILED: the identity role carries a superuser-like attribute';
    END IF;
END $$;
ROLLBACK;

-- The same boundary, exercised rather than read off the catalogue.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    BEGIN
        PERFORM count(*) FROM iam.credentials;
        RAISE EXCEPTION 'CHECK 27 FAILED: the control-plane role read iam.credentials';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

BEGIN;
SET LOCAL ROLE veyro_iam_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    BEGIN
        PERFORM count(*) FROM plt01.organizations;
        RAISE EXCEPTION 'CHECK 27 FAILED: the identity role read plt01.organizations';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 28. iam isolates by tenant
BEGIN;
SET LOCAL ROLE veyro_iam_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['identities', 'credentials', 'passkeys', 'devices', 'sessions',
                               'challenges', 'auth_events'] LOOP
        EXECUTE format('SELECT count(*) FROM iam.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 28 FAILED: tenant B sees % rows in iam.%', seen, tbl;
        END IF;
    END LOOP;
    BEGIN
        INSERT INTO iam.credentials
            (tenant_id, identity_id, kind, algorithm, salt, secret_hash)
        VALUES ('22222222-2222-4222-8222-222222222222',
                'eeeeeeee-0000-4000-8000-000000000002', 'password', 'scrypt',
                decode(repeat('ab', 16), 'hex'), decode(repeat('cd', 32), 'hex'));
        RAISE EXCEPTION 'CHECK 28 FAILED: a credential was attached to another tenant''s identity';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
END $$;
ROLLBACK;

BEGIN;
SET LOCAL ROLE veyro_iam_app;
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['identities', 'credentials', 'passkeys', 'devices', 'sessions',
                               'challenges', 'auth_events'] LOOP
        EXECUTE format('SELECT count(*) FROM iam.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION
                'CHECK 28 FAILED: unset context read % rows from iam.% -- fails OPEN', seen, tbl;
        END IF;
    END LOOP;
END $$;
ROLLBACK;

BEGIN;
SET LOCAL ROLE veyro_cp_migrator;
DO $$
BEGIN
    IF (SELECT count(*) FROM iam.credentials) <> 0 THEN
        RAISE EXCEPTION 'CHECK 28 FAILED: the table owner read % credentials',
            (SELECT count(*) FROM iam.credentials);
    END IF;
    -- Every table in the schema, not a counted subset. A fixed expected count has to be edited
    -- whenever a module adds a table, and the edit is exactly the moment an unprotected one
    -- would slip through; asking for zero unprotected tables needs no maintenance and catches
    -- the next one automatically.
    IF (SELECT count(*) FROM pg_class
        WHERE relnamespace = 'iam'::regnamespace AND relkind = 'r'
          AND NOT (relrowsecurity AND relforcerowsecurity)) <> 0 THEN
        RAISE EXCEPTION 'CHECK 28 FAILED: iam tables without forced RLS: %',
            (SELECT string_agg(relname, ', ') FROM pg_class
             WHERE relnamespace = 'iam'::regnamespace AND relkind = 'r'
               AND NOT (relrowsecurity AND relforcerowsecurity));
    END IF;
    IF (SELECT count(*) FROM pg_class
        WHERE relnamespace = 'iam'::regnamespace AND relkind = 'r') < 7 THEN
        RAISE EXCEPTION 'CHECK 28 FAILED: the iam schema is missing tables, so the sweep above proved nothing';
    END IF;
    -- Every iam table must be owned by the migrator. One owned by a superuser would ignore
    -- FORCE entirely, and the `RESET ROLE` in the platform migration makes that a live risk.
    IF (SELECT count(*) FROM pg_class
        WHERE relnamespace = 'iam'::regnamespace AND relkind = 'r'
          AND pg_get_userbyid(relowner) <> 'veyro_cp_migrator') <> 0 THEN
        RAISE EXCEPTION 'CHECK 28 FAILED: an iam table is not owned by the migrator';
    END IF;
END $$;
ROLLBACK;

BEGIN;
SET LOCAL ROLE veyro_iam_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    IF (SELECT count(*) FROM iam.identities) <> 1
       OR (SELECT count(*) FROM iam.credentials) <> 1
       OR (SELECT count(*) FROM iam.sessions) <> 1 THEN
        RAISE EXCEPTION 'CHECK 28 FAILED: tenant A cannot see its own identity rows';
    END IF;
END $$;
COMMIT;

-- ---------------------------------------------------------------- 29. the credential controls
BEGIN;
SET LOCAL ROLE veyro_iam_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    -- The audit trail cannot be edited or erased by the role that writes it.
    IF has_table_privilege('veyro_iam_app', 'iam.auth_events', 'UPDATE')
       OR has_table_privilege('veyro_iam_app', 'iam.auth_events', 'DELETE') THEN
        RAISE EXCEPTION 'CHECK 29 FAILED: the identity role can revise the authentication log';
    END IF;
    BEGIN
        UPDATE iam.auth_events SET outcome = 'succeeded';
        RAISE EXCEPTION 'CHECK 29 FAILED: an authentication event was rewritten';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;

    -- No role may delete an identity, a credential or a session: revocation is a status change
    -- that leaves evidence, and a DELETE would leave none.
    IF has_table_privilege('veyro_iam_app', 'iam.identities', 'DELETE')
       OR has_table_privilege('veyro_iam_app', 'iam.credentials', 'DELETE')
       OR has_table_privilege('veyro_iam_app', 'iam.sessions', 'DELETE')
       OR has_table_privilege('veyro_iam_app', 'iam.passkeys', 'TRUNCATE')
       OR has_table_privilege('veyro_iam_app', 'iam.credentials', 'REFERENCES') THEN
        RAISE EXCEPTION 'CHECK 29 FAILED: the identity role holds DELETE, TRUNCATE or REFERENCES';
    END IF;

    -- One active password per identity.
    BEGIN
        INSERT INTO iam.credentials
            (tenant_id, identity_id, kind, algorithm, salt, secret_hash)
        VALUES ('11111111-1111-4111-8111-111111111111',
                'eeeeeeee-0000-4000-8000-000000000002', 'password', 'scrypt',
                decode(repeat('ef', 16), 'hex'), decode(repeat('12', 32), 'hex'));
        RAISE EXCEPTION 'CHECK 29 FAILED: a second active password was accepted';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;

    -- A truncated hash or salt cannot be stored as if it were real.
    BEGIN
        INSERT INTO iam.credentials
            (tenant_id, identity_id, kind, algorithm, salt, secret_hash)
        VALUES ('11111111-1111-4111-8111-111111111111',
                'eeeeeeee-0000-4000-8000-000000000002', 'recovery_code', 'scrypt',
                decode('00', 'hex'), decode(repeat('12', 32), 'hex'));
        RAISE EXCEPTION 'CHECK 29 FAILED: a one-byte salt was accepted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A session token digest is exactly 32 bytes, and no two sessions share one.
    BEGIN
        INSERT INTO iam.sessions (tenant_id, identity_id, token_hash, expires_at)
        VALUES ('11111111-1111-4111-8111-111111111111',
                'eeeeeeee-0000-4000-8000-000000000002', decode('0011', 'hex'),
                now() + interval '1 hour');
        RAISE EXCEPTION 'CHECK 29 FAILED: a short session token digest was accepted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO iam.sessions (tenant_id, identity_id, token_hash, expires_at)
        VALUES ('11111111-1111-4111-8111-111111111111',
                'eeeeeeee-0000-4000-8000-000000000002', decode(repeat('01', 32), 'hex'),
                now() + interval '1 hour');
        RAISE EXCEPTION 'CHECK 29 FAILED: two sessions shared one token digest';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;

    -- A session cannot be rotated twice: the second use of a rotated token is the stolen-token
    -- signal the service acts on, and it must be impossible to record it as ordinary.
    INSERT INTO iam.sessions (tenant_id, identity_id, token_hash, expires_at, rotated_from)
    VALUES ('11111111-1111-4111-8111-111111111111',
            'eeeeeeee-0000-4000-8000-000000000002', decode(repeat('05', 32), 'hex'),
            now() + interval '1 hour', 'eeeeeeee-0000-4000-8000-000000000005');
    BEGIN
        INSERT INTO iam.sessions (tenant_id, identity_id, token_hash, expires_at, rotated_from)
        VALUES ('11111111-1111-4111-8111-111111111111',
                'eeeeeeee-0000-4000-8000-000000000002', decode(repeat('06', 32), 'hex'),
                now() + interval '1 hour', 'eeeeeeee-0000-4000-8000-000000000005');
        RAISE EXCEPTION 'CHECK 29 FAILED: one session was rotated twice';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;

    -- An assurance level outside 1..3 has no meaning, so no code could act on it correctly.
    BEGIN
        INSERT INTO iam.sessions (tenant_id, identity_id, token_hash, expires_at, aal)
        VALUES ('11111111-1111-4111-8111-111111111111',
                'eeeeeeee-0000-4000-8000-000000000002', decode(repeat('07', 32), 'hex'),
                now() + interval '1 hour', 9);
        RAISE EXCEPTION 'CHECK 29 FAILED: an out-of-range assurance level was accepted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
END $$;
ROLLBACK;

-- ================================================================ MOD-008 IAM-03 (authz, audit)
-- Eleven more tables in `iam`. Check 28's sweep already covers their row-level security, so what
-- is added here is what is specific to authorization: that the tables isolate and cannot be
-- parented across tenants (30), that the audit log is append-only **and** that its hash chain
-- detects tampering by somebody who can reach the database directly (31), and that the schema
-- cannot express the things default deny and separation of duties forbid (32).

-- ---------------------------------------------------------------- seed (authorization)
BEGIN;
SET LOCAL ROLE veyro_iam_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
INSERT INTO iam.roles (tenant_id, role_id, role_key, display_name)
VALUES (:'tenant_a', 'ffffffff-0000-4000-8000-000000000001', 'front_desk', 'Front Desk');
INSERT INTO iam.role_permissions (tenant_id, role_id, permission)
VALUES (:'tenant_a', 'ffffffff-0000-4000-8000-000000000001', 'member.profile.read');
INSERT INTO iam.role_assignments
    (tenant_id, assignment_id, identity_id, role_id, scope_type, brand_id, granted_by)
VALUES (:'tenant_a', 'ffffffff-0000-4000-8000-000000000002',
        'eeeeeeee-0000-4000-8000-000000000002', 'ffffffff-0000-4000-8000-000000000001',
        'brand', 'aaaaaaaa-0000-4000-8000-000000000002',
        'eeeeeeee-0000-4000-8000-000000000002');
INSERT INTO iam.policies (tenant_id, policy_id, policy_key, effect, action, masked_fields)
VALUES (:'tenant_a', 'ffffffff-0000-4000-8000-000000000003', 'mask_health', 'mask',
        'member.profile.read', ARRAY['health_notes']);
INSERT INTO iam.approval_requests
    (tenant_id, request_id, action, resource_type, requested_by, required_approvals,
     separation_of_duties, required_permissions, expires_at)
VALUES (:'tenant_a', 'ffffffff-0000-4000-8000-000000000004', 'billing.refund.issue', 'invoice',
        'eeeeeeee-0000-4000-8000-000000000002', 2, true, ARRAY['billing.refund.approve'],
        now() + interval '1 day');
INSERT INTO iam.approval_decisions (tenant_id, request_id, decided_by, decision)
VALUES (:'tenant_a', 'ffffffff-0000-4000-8000-000000000004',
        'eeeeeeee-0000-4000-8000-000000000002', 'approved');

-- A short, valid chain. The digests here are fixed test values: check 31 verifies the **link**
-- between entries, which holds whatever produced them, and `app.authorization.audit` is what
-- recomputes each digest from its own payload.
INSERT INTO iam.audit_chain_heads (tenant_id, sequence, head_hash)
VALUES (:'tenant_a', 3, decode(repeat('c3', 32), 'hex'));
INSERT INTO iam.audit_events
    (tenant_id, sequence, category, action, outcome, correlation_id, prev_hash, entry_hash)
VALUES (:'tenant_a', 1, 'access', 'role.assigned', 'recorded', :'actor',
        decode(repeat('00', 32), 'hex'), decode(repeat('c1', 32), 'hex')),
       (:'tenant_a', 2, 'data_access', 'member.profile.read', 'allowed', :'actor',
        decode(repeat('c1', 32), 'hex'), decode(repeat('c2', 32), 'hex')),
       (:'tenant_a', 3, 'finance', 'billing.refund.issue', 'denied', :'actor',
        decode(repeat('c2', 32), 'hex'), decode(repeat('c3', 32), 'hex'));
COMMIT;

-- ---------------------------------------------------------------- 30. authorization isolates
BEGIN;
SET LOCAL ROLE veyro_iam_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['roles', 'role_permissions', 'role_assignments', 'policies',
                               'approval_policies', 'approval_requests', 'approval_decisions',
                               'audit_events', 'audit_chain_heads', 'access_reviews',
                               'access_review_items'] LOOP
        EXECUTE format('SELECT count(*) FROM iam.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 30 FAILED: tenant B sees % rows in iam.%', seen, tbl;
        END IF;
    END LOOP;

    BEGIN
        INSERT INTO iam.role_permissions (tenant_id, role_id, permission)
        VALUES ('22222222-2222-4222-8222-222222222222',
                'ffffffff-0000-4000-8000-000000000001', 'member.profile.write');
        RAISE EXCEPTION 'CHECK 30 FAILED: a permission was added to another tenant''s role';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO iam.approval_decisions (tenant_id, request_id, decided_by, decision)
        VALUES ('22222222-2222-4222-8222-222222222222',
                'ffffffff-0000-4000-8000-000000000004',
                'eeeeeeee-0000-4000-8000-000000000002', 'approved');
        RAISE EXCEPTION 'CHECK 30 FAILED: another tenant''s approval was decided';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
END $$;
ROLLBACK;

BEGIN;
SET LOCAL ROLE veyro_iam_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    IF (SELECT count(*) FROM iam.roles) <> 1
       OR (SELECT count(*) FROM iam.audit_events) <> 3 THEN
        RAISE EXCEPTION 'CHECK 30 FAILED: tenant A cannot see its own authorization rows';
    END IF;
END $$;
COMMIT;

-- ---------------------------------------------------------------- 31. the audit chain
-- Append-only is a privilege. Integrity is the chain, and the chain is what still says something
-- when the attacker can reach the database directly -- it cannot stop them, but it stops them
-- doing it quietly.
BEGIN;
SET LOCAL ROLE veyro_iam_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    IF has_table_privilege('veyro_iam_app', 'iam.audit_events', 'UPDATE')
       OR has_table_privilege('veyro_iam_app', 'iam.audit_events', 'DELETE')
       OR has_table_privilege('veyro_iam_app', 'iam.audit_events', 'TRUNCATE')
       OR has_table_privilege('veyro_iam_app', 'iam.approval_decisions', 'UPDATE')
       OR has_table_privilege('veyro_iam_app', 'iam.approval_decisions', 'DELETE') THEN
        RAISE EXCEPTION 'CHECK 31 FAILED: a runtime role can revise the audit log or a decision';
    END IF;
    BEGIN
        UPDATE iam.audit_events SET outcome = 'allowed';
        RAISE EXCEPTION 'CHECK 31 FAILED: an audit entry was rewritten';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;

    -- The chain walk itself lives in `audit_chain.sql`, which runs after this file so that a
    -- tamper applied to the seeded rows has something to tamper with. `MUTATE` is applied before
    -- the seed, so a DELETE expressed there would hit an empty table and prove nothing -- which
    -- it silently did until the mutation test caught it.
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 32. what the schema forbids
-- Default deny and separation of duties are claims about what cannot be expressed, so they are
-- tested by trying to express them.
BEGIN;
SET LOCAL ROLE veyro_iam_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    -- No wildcard permission. A role that could hold `billing.*` would be least privilege in
    -- name only.
    BEGIN
        INSERT INTO iam.role_permissions (tenant_id, role_id, permission)
        VALUES ('11111111-1111-4111-8111-111111111111',
                'ffffffff-0000-4000-8000-000000000001', 'billing.*');
        RAISE EXCEPTION 'CHECK 32 FAILED: a wildcard permission was accepted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- One decision per approver per request: "two approvals" must mean two people.
    BEGIN
        INSERT INTO iam.approval_decisions (tenant_id, request_id, decided_by, decision)
        VALUES ('11111111-1111-4111-8111-111111111111',
                'ffffffff-0000-4000-8000-000000000004',
                'eeeeeeee-0000-4000-8000-000000000002', 'rejected');
        RAISE EXCEPTION 'CHECK 32 FAILED: one approver decided the same request twice';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;

    -- A scope that names no target is a scope that means everything.
    BEGIN
        INSERT INTO iam.role_assignments
            (tenant_id, identity_id, role_id, scope_type, granted_by)
        VALUES ('11111111-1111-4111-8111-111111111111',
                'eeeeeeee-0000-4000-8000-000000000002',
                'ffffffff-0000-4000-8000-000000000001', 'brand',
                'eeeeeeee-0000-4000-8000-000000000002');
        RAISE EXCEPTION 'CHECK 32 FAILED: a brand-scoped assignment named no brand';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A mask policy that masks nothing cannot be read off its own columns.
    BEGIN
        INSERT INTO iam.policies (tenant_id, policy_key, effect, action)
        VALUES ('11111111-1111-4111-8111-111111111111', 'empty_mask', 'mask',
                'member.profile.read');
        RAISE EXCEPTION 'CHECK 32 FAILED: a mask policy with no masked fields was accepted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- An approval policy requiring zero approvals is an approval policy that approves nothing.
    BEGIN
        INSERT INTO iam.approval_policies
            (tenant_id, action, required_permission, required_approvals)
        VALUES ('11111111-1111-4111-8111-111111111111', 'billing.refund.issue',
                'billing.refund.approve', 0);
        RAISE EXCEPTION 'CHECK 32 FAILED: an approval policy required zero approvals';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- seed (tenant plane, MOD-009)
-- `subject_id` is a bare uuid by design: identities live in `iam`, which veyro_cp_app cannot
-- reach, so there is no foreign key available to carry the tenant into. That makes RLS the only
-- thing standing between one tenant's consent evidence and another's, which is why checks 33
-- and 34 test these tables directly rather than resting on the parent-chain argument that
-- covers the `cfg_` and `bil_` children.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
INSERT INTO plt01.sec_processing_purposes
    (tenant_id, purpose_id, purpose_code, description, lawful_basis, controller_role,
     data_classes, registered_by, correlation_id)
VALUES (:'tenant_a', '99999999-0000-4000-8000-000000000001', 'member.training',
        'Deliver training sessions', 'contract', 'processor',
        ARRAY['confidential'], :'actor', :'actor');
INSERT INTO plt01.sec_consent_definitions
    (tenant_id, definition_id, consent_type, purpose_id, withdrawable, defined_by,
     correlation_id)
VALUES (:'tenant_a', '99999999-0000-4000-8000-000000000002', 'waiver',
        '99999999-0000-4000-8000-000000000001', false, :'actor', :'actor');
INSERT INTO plt01.sec_consent_versions
    (tenant_id, consent_version_id, definition_id, version, language, document_ref,
     document_hash, effective_from, published_by, correlation_id)
VALUES (:'tenant_a', '99999999-0000-4000-8000-000000000003',
        '99999999-0000-4000-8000-000000000002', 1, 'en', 'waiver/v1',
        '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
        TIMESTAMPTZ '2026-11-01 00:00:00+00', :'actor', :'actor');
INSERT INTO plt01.sec_consent_definitions
    (tenant_id, definition_id, consent_type, purpose_id, withdrawable, defined_by,
     correlation_id)
VALUES (:'tenant_a', '99999999-0000-4000-8000-00000000000b', 'marketing',
        '99999999-0000-4000-8000-000000000001', true, :'actor', :'actor');
INSERT INTO plt01.sec_consent_versions
    (tenant_id, consent_version_id, definition_id, version, language, document_ref,
     document_hash, effective_from, published_by, correlation_id)
VALUES (:'tenant_a', '99999999-0000-4000-8000-00000000000c',
        '99999999-0000-4000-8000-00000000000b', 1, 'en', 'marketing/v1',
        'fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210',
        TIMESTAMPTZ '2026-11-01 00:00:00+00', :'actor', :'actor');
INSERT INTO plt01.sec_consent_records
    (tenant_id, record_id, subject_id, definition_id, consent_version_id, action, signed_at,
     source, locale, correlation_id)
VALUES (:'tenant_a', '99999999-0000-4000-8000-000000000004',
        '99999999-0000-4000-8000-00000000000a',
        '99999999-0000-4000-8000-000000000002', '99999999-0000-4000-8000-000000000003',
        'granted', TIMESTAMPTZ '2026-11-02 09:00:00+00', 'member_app', 'en-GB', :'actor');
INSERT INTO plt01.sec_retention_policies
    (tenant_id, policy_id, resource_type, data_class, retention_days, legal_basis, region,
     set_by, correlation_id)
VALUES (:'tenant_a', '99999999-0000-4000-8000-000000000005', 'consent_record', 'confidential',
        3650, 'PDPL No. 24 of 2023 art. 4', 'eu-west', :'actor', :'actor');
INSERT INTO plt01.sec_legal_holds
    (tenant_id, hold_id, subject_id, resource_type, reason, reference, placed_by, correlation_id)
VALUES (:'tenant_a', '99999999-0000-4000-8000-000000000006',
        '99999999-0000-4000-8000-00000000000a', 'consent_record',
        'injury claim under investigation', 'CASE-2026-11', :'actor', :'actor');
INSERT INTO plt01.sec_dsar_requests
    (tenant_id, request_id, subject_id, request_type, status, received_at, due_at,
     opened_by, correlation_id)
VALUES (:'tenant_a', '99999999-0000-4000-8000-000000000007',
        '99999999-0000-4000-8000-00000000000a', 'deletion', 'received',
        TIMESTAMPTZ '2026-11-10 08:00:00+00', TIMESTAMPTZ '2026-12-10 08:00:00+00',
        :'actor', :'actor');
INSERT INTO plt01.sec_dsar_actions
    (tenant_id, action_id, request_id, store, target, mechanism, outcome, rows_affected,
     evidence_hash)
VALUES (:'tenant_a', '99999999-0000-4000-8000-000000000008',
        '99999999-0000-4000-8000-000000000007', 'postgresql', 'iam.identities.identity_id',
        'anonymize', 'done', 1,
        '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef');
INSERT INTO plt01.sec_incidents
    (tenant_id, incident_id, severity, category, summary, detected_at,
     personal_data_involved, recorded_by, correlation_id)
VALUES (:'tenant_a', '99999999-0000-4000-8000-000000000009', 'low', 'access_anomaly',
        'Repeated failed logins from one address', TIMESTAMPTZ '2026-11-08 22:00:00+00',
        'unknown', :'actor', :'actor');
COMMIT;

BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
INSERT INTO plt01.sec_processing_purposes
    (tenant_id, purpose_id, purpose_code, description, lawful_basis, controller_role,
     data_classes, registered_by, correlation_id)
VALUES (:'tenant_b', '88888888-0000-4000-8000-000000000001', 'security.audit',
        'Detect and investigate abuse', 'legitimate_interest', 'controller',
        ARRAY['restricted'], :'actor', :'actor');
COMMIT;

-- ---------------------------------------------------------------- 33. sec tables isolate
-- The same sweep the other two tracks get. Tenant B holds one purpose of its own, so a
-- predicate that leaked would show up as a count above the expected one rather than as the
-- zero that an empty table would give anyway.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['sec_consent_definitions', 'sec_consent_versions',
                               'sec_consent_records', 'sec_retention_policies',
                               'sec_legal_holds', 'sec_dsar_requests', 'sec_dsar_actions',
                               'sec_incidents']
    LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 33 FAILED: tenant B sees % rows of tenant A in %', seen, tbl;
        END IF;
    END LOOP;
    IF (SELECT count(*) FROM plt01.sec_processing_purposes) <> 1 THEN
        RAISE EXCEPTION 'CHECK 33 FAILED: tenant B sees % purposes, expected its own 1',
            (SELECT count(*) FROM plt01.sec_processing_purposes);
    END IF;
    IF EXISTS (SELECT 1 FROM plt01.sec_processing_purposes
               WHERE purpose_code = 'member.training') THEN
        RAISE EXCEPTION 'CHECK 33 FAILED: tenant B read tenant A''s processing purpose';
    END IF;
END $$;
COMMIT;

BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    -- All nine, not the four this once covered. A table whose positive case nobody asserts
    -- could return zero for the wrong reason and only the negative sweep would notice, which
    -- is the direction that reads as a pass.
    IF (SELECT count(*) FROM plt01.sec_processing_purposes) <> 1
       OR (SELECT count(*) FROM plt01.sec_consent_definitions) <> 2
       OR (SELECT count(*) FROM plt01.sec_consent_versions) <> 2
       OR (SELECT count(*) FROM plt01.sec_consent_records) <> 1
       OR (SELECT count(*) FROM plt01.sec_retention_policies) <> 1
       OR (SELECT count(*) FROM plt01.sec_legal_holds) <> 1
       OR (SELECT count(*) FROM plt01.sec_dsar_requests) <> 1
       OR (SELECT count(*) FROM plt01.sec_dsar_actions) <> 1
       OR (SELECT count(*) FROM plt01.sec_incidents) <> 1 THEN
        RAISE EXCEPTION 'CHECK 33 FAILED: tenant A cannot see its own privacy rows';
    END IF;
END $$;
COMMIT;

-- The migrator owns these tables and no policy names it, so FORCE RLS denies it by default.
-- Asserted here rather than assumed: without FORCE, the owner reads every tenant at once, and
-- the owner is the role the application could be misconfigured to connect as.
--
-- **Swept from the catalogue, not named table by table.** The first version of this check probed
-- two tables behaviourally and `ALTER TABLE plt01.sec_legal_holds NO FORCE ROW LEVEL SECURITY`
-- left the suite reporting every check passed while the migrator read every tenant's legal
-- holds. Checks 17, 22 and 28 already got this right and MOD-009 regressed; a per-table list has
-- to be edited whenever a module adds a table, and that edit is exactly the moment an
-- unprotected one slips through. The count guard stops the sweep passing vacuously.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
DECLARE
    unprotected text;
    total bigint;
BEGIN
    SELECT string_agg(relname, ', '), count(*) FILTER (WHERE true)
    INTO unprotected, total
    FROM pg_class
    WHERE relnamespace = 'plt01'::regnamespace AND relkind = 'r' AND relname LIKE 'sec\_%'
      AND NOT (relrowsecurity AND relforcerowsecurity);
    IF unprotected IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 33 FAILED: sec_ tables without ENABLE and FORCE RLS: %',
            unprotected;
    END IF;
    IF (SELECT count(*) FROM pg_class
        WHERE relnamespace = 'plt01'::regnamespace AND relkind = 'r'
          AND relname LIKE 'sec\_%') < 9 THEN
        RAISE EXCEPTION 'CHECK 33 FAILED: fewer than 9 sec_ tables, so the sweep proved nothing';
    END IF;
    -- A table owned by a superuser ignores FORCE entirely, so the sweep above would be reading
    -- a flag that does not bind.
    IF (SELECT count(*) FROM pg_class
        WHERE relnamespace = 'plt01'::regnamespace AND relkind = 'r' AND relname LIKE 'sec\_%'
          AND pg_get_userbyid(relowner) <> 'veyro_cp_migrator') <> 0 THEN
        RAISE EXCEPTION 'CHECK 33 FAILED: a sec_ table is not owned by the migrator';
    END IF;
END $$;
COMMIT;

-- And behaviourally, because a catalogue flag is a claim about behaviour: the owner reads
-- nothing even with a tenant context set.
BEGIN;
SET LOCAL ROLE veyro_cp_migrator;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['sec_processing_purposes', 'sec_consent_definitions',
                               'sec_consent_versions', 'sec_consent_records',
                               'sec_retention_policies', 'sec_legal_holds',
                               'sec_dsar_requests', 'sec_dsar_actions', 'sec_incidents']
    LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 33 FAILED: the table owner read % rows of %, so FORCE RLS is off',
                seen, tbl;
        END IF;
    END LOOP;
END $$;
COMMIT;

-- ---------------------------------------------------------------- 34. fail closed, sec tables
-- With no context the predicate is NULL, so reads return nothing and writes are refused. This
-- is the property the whole module rests on: consent evidence and a legal hold are exactly the
-- rows a bug in some unrelated query must never surface.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['sec_processing_purposes', 'sec_consent_definitions',
                               'sec_consent_versions', 'sec_consent_records',
                               'sec_retention_policies', 'sec_legal_holds',
                               'sec_dsar_requests', 'sec_dsar_actions', 'sec_incidents']
    LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 34 FAILED: % returned % rows with no tenant context',
                tbl, seen;
        END IF;
    END LOOP;

    BEGIN
        INSERT INTO plt01.sec_incidents
            (tenant_id, severity, category, summary, detected_at, personal_data_involved,
             recorded_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'critical', 'breach', 'no context',
                now(), 'yes', '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 34 FAILED: an incident was recorded with no tenant context';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;

    BEGIN
        INSERT INTO plt01.sec_legal_holds
            (tenant_id, reason, reference, placed_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'no context', 'X',
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 34 FAILED: a legal hold was placed with no tenant context';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

-- **WITH CHECK, swept.** The behavioural case below exercises one table. That is not enough:
-- replacing `sec_consent_records`'s policy with `WITH CHECK (true)` left the suite green while
-- tenant B could plant a forged *withdrawal* of consent into tenant A's ledger -- and because
-- the table is insert-only by privilege, tenant A could never remove it. That is the one
-- combination in this module where a write-side isolation failure is unrecoverable rather than
-- merely wrong, and it was the one case the suite did not cover.
--
-- Every policy's WITH CHECK must exist and must say exactly what its USING says. A policy with
-- a USING predicate and no WITH CHECK silently reuses USING for reads but permits any insert.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
DECLARE
    broken text;
BEGIN
    SELECT string_agg(tablename || ' (' || policyname || ')', ', ') INTO broken
    FROM pg_policies
    WHERE schemaname = 'plt01' AND tablename LIKE 'sec\_%'
      AND (with_check IS NULL OR with_check IS DISTINCT FROM qual);
    IF broken IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 34 FAILED: WITH CHECK missing or weaker than USING on: %', broken;
    END IF;
    IF (SELECT count(*) FROM pg_policies
        WHERE schemaname = 'plt01' AND tablename LIKE 'sec\_%') < 9 THEN
        RAISE EXCEPTION 'CHECK 34 FAILED: fewer than 9 sec_ policies, so the sweep proved nothing';
    END IF;
    -- The predicate itself, not merely that the two halves agree: a policy whose USING and
    -- WITH CHECK are both `true` would pass the comparison above.
    IF (SELECT count(*) FROM pg_policies
        WHERE schemaname = 'plt01' AND tablename LIKE 'sec\_%'
          AND qual NOT LIKE '%current_setting(''app.tenant_id''%') <> 0 THEN
        RAISE EXCEPTION 'CHECK 34 FAILED: a sec_ policy does not read app.tenant_id';
    END IF;
END $$;
COMMIT;

-- A write aimed at another tenant while holding a context is refused by WITH CHECK, not merely
-- hidden by USING. Kept behavioural as well as structural: the sweep above reads the catalogue's
-- idea of the policy, and this proves the database acts on it.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
BEGIN
    BEGIN
        INSERT INTO plt01.sec_incidents
            (tenant_id, severity, category, summary, detected_at, personal_data_involved,
             recorded_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'critical', 'breach',
                'planted by another tenant', now(), 'yes',
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 34 FAILED: tenant B wrote an incident into tenant A';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 35. cross-tenant parents
-- Every reference inside this module is composite and carries `tenant_id`, so a row that names
-- another tenant's parent is refused by the database rather than by the service. A consent
-- record pointing at another tenant's published document would otherwise be a way to attribute
-- an agreement to a text its signer never saw.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
BEGIN
    BEGIN
        INSERT INTO plt01.sec_consent_definitions
            (tenant_id, consent_type, purpose_id, defined_by, correlation_id)
        VALUES ('22222222-2222-4222-8222-222222222222', 'marketing',
                '99999999-0000-4000-8000-000000000001',
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 35 FAILED: a consent definition cited another tenant''s purpose';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO plt01.sec_dsar_actions
            (tenant_id, request_id, store, target, mechanism, outcome, rows_affected,
             evidence_hash)
        VALUES ('22222222-2222-4222-8222-222222222222',
                '99999999-0000-4000-8000-000000000007', 'postgresql', 'plt01.organizations',
                'delete', 'done', 1,
                '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef');
        RAISE EXCEPTION 'CHECK 35 FAILED: evidence was filed against another tenant''s request';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
END $$;
ROLLBACK;

-- The same within one tenant: a consent record must cite a version of the definition it names.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    BEGIN
        INSERT INTO plt01.sec_consent_records
            (tenant_id, subject_id, definition_id, consent_version_id, action, signed_at,
             source, locale, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111',
                '99999999-0000-4000-8000-00000000000a',
                '99999999-0000-4000-8000-000000000002',
                '99999999-0000-4000-8000-0000000000ff', 'granted', now(), 'web', 'en',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 35 FAILED: consent was recorded against a version that does not exist';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;

    -- The harder case, and the one a plain pair of foreign keys does not refuse: a version that
    -- *exists* but belongs to a different definition. Both ids are real here -- the waiver
    -- definition and the marketing document -- so two independent references would accept it,
    -- and the row would say a member agreed to a waiver while carrying the hash and reference
    -- of the marketing text. Insert-only, so nobody could correct it. The reference is a triple
    -- for this reason.
    BEGIN
        INSERT INTO plt01.sec_consent_records
            (tenant_id, subject_id, definition_id, consent_version_id, action, signed_at,
             source, locale, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111',
                '99999999-0000-4000-8000-00000000000a',
                '99999999-0000-4000-8000-000000000002',
                '99999999-0000-4000-8000-00000000000c', 'granted', now(), 'web', 'en',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 35 FAILED: a waiver consent cited the marketing document';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 36. evidence is insert-only
-- Four tables here answer questions asked later, by somebody auditing the party that holds
-- them: what was consented to, what document said so, what a deletion job actually did, and
-- what happened during an incident. Each is worthless if the holder can revise it, so the
-- append-only property is a privilege rather than a convention, and it is asserted from the
-- catalogue as well as exercised -- a statement can fail for the wrong reason, which this file
-- learned at check 10.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
DECLARE
    tbl text;
    role_name text;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['sec_consent_definitions', 'sec_consent_versions',
                               'sec_consent_records', 'sec_dsar_actions', 'sec_incidents']
    LOOP
        FOREACH role_name IN ARRAY ARRAY['veyro_cp_app', 'veyro_cp_worker']
        LOOP
            IF has_table_privilege(role_name, 'plt01.' || tbl, 'UPDATE')
               OR has_table_privilege(role_name, 'plt01.' || tbl, 'DELETE') THEN
                RAISE EXCEPTION 'CHECK 36 FAILED: % can revise %', role_name, tbl;
            END IF;
        END LOOP;
    END LOOP;

    -- No runtime role holds DELETE, TRUNCATE or REFERENCES anywhere in this module. DELETE is
    -- the one that matters most: a retention job that could delete a legal hold could delete
    -- the evidence that deletion was suspended.
    FOREACH tbl IN ARRAY ARRAY['sec_processing_purposes', 'sec_consent_definitions',
                               'sec_consent_versions', 'sec_consent_records',
                               'sec_retention_policies', 'sec_legal_holds',
                               'sec_dsar_requests', 'sec_dsar_actions', 'sec_incidents']
    LOOP
        FOREACH role_name IN ARRAY ARRAY['veyro_cp_app', 'veyro_cp_worker']
        LOOP
            IF has_table_privilege(role_name, 'plt01.' || tbl, 'DELETE')
               OR has_table_privilege(role_name, 'plt01.' || tbl, 'TRUNCATE')
               OR has_table_privilege(role_name, 'plt01.' || tbl, 'REFERENCES') THEN
                RAISE EXCEPTION 'CHECK 36 FAILED: % holds DELETE, TRUNCATE or REFERENCES on %',
                    role_name, tbl;
            END IF;
        END LOOP;
    END LOOP;

    BEGIN
        UPDATE plt01.sec_consent_records SET action = 'withdrawn';
        RAISE EXCEPTION 'CHECK 36 FAILED: a consent record was rewritten';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;

    BEGIN
        DELETE FROM plt01.sec_legal_holds;
        RAISE EXCEPTION 'CHECK 36 FAILED: a legal hold was deleted';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

-- The mutable registries move on named columns only. A table-level UPDATE here would let the
-- lawful basis a consent was collected under change after the fact, or a retention period
-- already applied be shortened, or a deletion request become an access request.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    IF NOT has_column_privilege('veyro_cp_app', 'plt01.sec_processing_purposes',
                                'retired_by', 'UPDATE')
       OR NOT has_column_privilege('veyro_cp_app', 'plt01.sec_legal_holds',
                                   'released_by', 'UPDATE')
       OR NOT has_column_privilege('veyro_cp_app', 'plt01.sec_processing_purposes',
                                   'retired_at', 'UPDATE')
       OR NOT has_column_privilege('veyro_cp_app', 'plt01.sec_retention_policies',
                                   'retired_at', 'UPDATE')
       OR NOT has_column_privilege('veyro_cp_app', 'plt01.sec_legal_holds',
                                   'released_at', 'UPDATE')
       OR NOT has_column_privilege('veyro_cp_app', 'plt01.sec_dsar_requests',
                                   'status', 'UPDATE') THEN
        RAISE EXCEPTION 'CHECK 36 FAILED: a retirement or state column cannot be written';
    END IF;
    IF has_column_privilege('veyro_cp_app', 'plt01.sec_processing_purposes',
                            'lawful_basis', 'UPDATE')
       OR has_column_privilege('veyro_cp_app', 'plt01.sec_retention_policies',
                               'retention_days', 'UPDATE')
       OR has_column_privilege('veyro_cp_app', 'plt01.sec_legal_holds', 'reason', 'UPDATE')
       OR has_column_privilege('veyro_cp_app', 'plt01.sec_dsar_requests',
                               'subject_id', 'UPDATE')
       OR has_column_privilege('veyro_cp_app', 'plt01.sec_dsar_requests',
                               'request_type', 'UPDATE')
       OR has_column_privilege('veyro_cp_app', 'plt01.sec_dsar_requests',
                               'due_at', 'UPDATE') THEN
        RAISE EXCEPTION 'CHECK 36 FAILED: a column that fixes the terms of a record is writable';
    END IF;

    BEGIN
        UPDATE plt01.sec_retention_policies SET retention_days = 1;
        RAISE EXCEPTION 'CHECK 36 FAILED: a retention period was shortened in place';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;

    BEGIN
        UPDATE plt01.sec_dsar_requests SET request_type = 'access';
        RAISE EXCEPTION 'CHECK 36 FAILED: a deletion request became an access request';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 37. the CHECKs actually bite
-- Each of these encodes a decision that would otherwise live only in a comment: which lawful
-- bases exist, which consent kinds exist, that a guardian is somebody else, that a refusal and
-- a release carry their reasons, and that a completed request has a completion time.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    -- The six bases are Jordan PDPL's, not GDPR's. "legitimate_interests" plural is GDPR's
    -- spelling and is exactly the kind of near-miss that would otherwise be accepted.
    BEGIN
        INSERT INTO plt01.sec_processing_purposes
            (tenant_id, purpose_code, description, lawful_basis, controller_role,
             data_classes, registered_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'member.marketing', 'Send offers',
                'legitimate_interests', 'controller', ARRAY['internal'],
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 37 FAILED: an unlisted lawful basis was accepted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A purpose with no data classes names nothing, so no retention policy and no export can
    -- find it.
    BEGIN
        INSERT INTO plt01.sec_processing_purposes
            (tenant_id, purpose_code, description, lawful_basis, controller_role,
             data_classes, registered_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'member.unclassed', 'Nothing',
                'consent', 'controller', ARRAY[]::text[],
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 37 FAILED: a purpose covering no data class was accepted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- An invented consent kind would be collected under a name no retention policy and no DSAR
    -- export knows about.
    BEGIN
        INSERT INTO plt01.sec_consent_definitions
            (tenant_id, consent_type, purpose_id, defined_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'facial_recognition',
                '99999999-0000-4000-8000-000000000001',
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 37 FAILED: an invented consent kind was accepted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A guardian who is the subject reads as a valid minor's consent and is not one.
    BEGIN
        INSERT INTO plt01.sec_consent_records
            (tenant_id, subject_id, definition_id, consent_version_id, action, signed_at,
             source, guardian_subject_id, locale, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111',
                '99999999-0000-4000-8000-00000000000a',
                '99999999-0000-4000-8000-000000000002',
                '99999999-0000-4000-8000-000000000003', 'granted', now(), 'staff_entry',
                '99999999-0000-4000-8000-00000000000a', 'en',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 37 FAILED: a subject consented as their own guardian';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A refusal is a decision the subject can appeal, so the reason is in the row.
    BEGIN
        INSERT INTO plt01.sec_dsar_requests
            (tenant_id, subject_id, request_type, status, received_at, due_at,
             opened_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111',
                '99999999-0000-4000-8000-00000000000a', 'access', 'refused', now(),
                now() + interval '30 days', '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 37 FAILED: a request was refused with no reason';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- "Completed" and a completion time are one fact written twice; they cannot disagree.
    BEGIN
        INSERT INTO plt01.sec_dsar_requests
            (tenant_id, subject_id, request_type, status, received_at, due_at,
             opened_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111',
                '99999999-0000-4000-8000-00000000000a', 'access', 'completed', now(),
                now() + interval '30 days', '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 37 FAILED: a request was completed with no completion time';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A release with no reason is indistinguishable from a mistake, and this row is the
    -- evidence somebody will be asked about.
    BEGIN
        UPDATE plt01.sec_legal_holds SET released_at = now()
        WHERE hold_id = '99999999-0000-4000-8000-000000000006';
        RAISE EXCEPTION 'CHECK 37 FAILED: a legal hold was released with no reason';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- An unbounded retention period is written as no policy, not as a very large number.
    BEGIN
        INSERT INTO plt01.sec_retention_policies
            (tenant_id, resource_type, data_class, retention_days, legal_basis, region,
             set_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'session_log', 'internal', -1,
                'none', 'eu-west', '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 37 FAILED: a negative retention period was accepted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A data class outside the four of TSD section 21.2 would carry no classification rule.
    BEGIN
        INSERT INTO plt01.sec_retention_policies
            (tenant_id, resource_type, data_class, retention_days, legal_basis, region,
             set_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'session_log', 'top_secret', 30,
                'none', 'eu-west', '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 37 FAILED: an unknown data class was accepted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 38. evidence stays answerable
-- Four controls an independent review asked for, each closing a way the record of a decision
-- could be rewritten or left with nobody's name on it.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    -- Releasing a hold un-blocks destruction of preserved evidence. It is the one act in this
    -- module with no audit row anywhere else -- `veyro_cp_app` holds nothing in `iam`, so
    -- MOD-008's chain is out of reach -- which makes the row itself the only record of who.
    BEGIN
        UPDATE plt01.sec_legal_holds
        SET released_at = now(), release_reason = 'anonymous'
        WHERE hold_id = '99999999-0000-4000-8000-000000000006';
        RAISE EXCEPTION 'CHECK 38 FAILED: a hold was released with nobody''s name on it';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- Retiring a purpose withdraws the stated justification for processing. Registering one
    -- records an actor; retiring one must too.
    BEGIN
        UPDATE plt01.sec_processing_purposes SET retired_at = now()
        WHERE purpose_id = '99999999-0000-4000-8000-000000000001';
        RAISE EXCEPTION 'CHECK 38 FAILED: a purpose was retired with nobody''s name on it';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A data class outside the four of TSD section 21.2 names a classification no rule exists
    -- for. The empty-array case is at check 37; this is the element case, which the first
    -- version of the constraint admitted.
    BEGIN
        INSERT INTO plt01.sec_processing_purposes
            (tenant_id, purpose_code, description, lawful_basis, controller_role,
             data_classes, registered_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'member.odd', 'Odd',
                'consent', 'controller', ARRAY['top_secret'],
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 38 FAILED: a purpose named an unknown data class';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- The live-policy index is unique on (resource_type, region), so free text defeats it: three
    -- spellings of one resource are three live policies and whichever is read first wins.
    BEGIN
        INSERT INTO plt01.sec_retention_policies
            (tenant_id, resource_type, data_class, retention_days, legal_basis, region,
             set_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'Consent_Record', 'confidential', 1,
                'none', 'eu-west', '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 38 FAILED: a second spelling of a resource type was accepted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- The same for an incident category. No source here enumerates a taxonomy, so the shape is
    -- all there is; without it one category arrives in three spellings and nothing groups.
    BEGIN
        INSERT INTO plt01.sec_incidents
            (tenant_id, severity, category, summary, detected_at, personal_data_involved,
             recorded_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'low', 'Access Anomaly',
                'mis-spelled category', now(), 'no',
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 38 FAILED: a free-text incident category was accepted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
END $$;
ROLLBACK;

-- The release is final, and only a trigger can say so: a CHECK sees one row and not what the row
-- used to be, so the constraint above happily permits a released hold to be released again with
-- a different date, or set back to NULL so it reads as a hold that was never lifted. Either
-- rewrites how long deletion was suspended, which is the whole reason the row is kept.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
UPDATE plt01.sec_legal_holds
SET released_at = now(), release_reason = 'claim settled',
    released_by = '33333333-3333-4333-8333-333333333333',
    release_correlation_id = '33333333-3333-4333-8333-333333333333'
WHERE hold_id = '99999999-0000-4000-8000-000000000006';
DO $$
BEGIN
    BEGIN
        UPDATE plt01.sec_legal_holds
        SET released_at = TIMESTAMPTZ '2020-01-01 00:00:00+00', release_reason = 'clerical'
        WHERE hold_id = '99999999-0000-4000-8000-000000000006';
        RAISE EXCEPTION 'CHECK 38 FAILED: a release was backdated after the fact';
    EXCEPTION
        WHEN restrict_violation THEN NULL;
    END;
    BEGIN
        UPDATE plt01.sec_legal_holds
        SET released_at = NULL, release_reason = NULL, released_by = NULL,
            release_correlation_id = NULL
        WHERE hold_id = '99999999-0000-4000-8000-000000000006';
        RAISE EXCEPTION 'CHECK 38 FAILED: a released hold was made to read as never released';
    EXCEPTION
        WHEN restrict_violation THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- seed (tenant plane, MOD-010)
-- The outbox is the one table in this repository a producer writes from inside somebody else's
-- transaction, so its isolation matters in a way the others' does not: a leak here is not a
-- read of another tenant's row, it is another tenant's *business event* arriving in this
-- tenant's consumers and projections.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
INSERT INTO plt01.evt_subscriptions
    (tenant_id, subscription_id, consumer, event_type, replay_safety, registered_by,
     correlation_id)
VALUES (:'tenant_a', '77777777-0000-4000-8000-000000000001', 'timeline',
        'tenant.provisioned', 'safe', :'actor', :'actor');
INSERT INTO plt01.evt_outbox
    (tenant_id, event_id, event_type, schema_version, aggregate_type, aggregate_id,
     actor_id, correlation_id, payload, idempotency_key)
VALUES (:'tenant_a', '77777777-0000-4000-8000-000000000002', 'tenant.provisioned', 1,
        'tenant', :'tenant_a', :'actor', :'actor',
        '{"tenant_id": "a", "external_key": "k", "display_name": "n", "region": "eu-west"}'::jsonb,
        'seed-provision-1');
INSERT INTO plt01.evt_deliveries (tenant_id, consumer, event_id)
VALUES (:'tenant_a', 'timeline', '77777777-0000-4000-8000-000000000002');
INSERT INTO plt01.evt_dead_letters
    (tenant_id, dead_letter_id, event_id, consumer, reason, attempts)
VALUES (:'tenant_a', '77777777-0000-4000-8000-000000000003',
        '77777777-0000-4000-8000-000000000002', 'ledger', 'handler raised', 5);
INSERT INTO plt01.evt_replay_jobs
    (tenant_id, job_id, consumer, event_types, from_time, to_time, requested_by,
     correlation_id)
VALUES (:'tenant_a', '77777777-0000-4000-8000-000000000004', 'timeline',
        ARRAY['tenant.provisioned'], TIMESTAMPTZ '2026-11-01 00:00:00+00',
        TIMESTAMPTZ '2026-12-01 00:00:00+00', :'actor', :'actor');
COMMIT;

BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
INSERT INTO plt01.evt_subscriptions
    (tenant_id, subscription_id, consumer, event_type, registered_by, correlation_id)
VALUES (:'tenant_b', '66666666-0000-4000-8000-000000000001', 'timeline',
        'tenant.provisioned', :'actor', :'actor');
COMMIT;

-- ---------------------------------------------------------------- 39. evt tables isolate
-- Swept from the catalogue, not named table by table, and that is not a stylistic choice: the
-- MOD-009 review removed FORCE RLS from a table whose name happened not to appear in a check
-- and watched the whole suite report success. Checks 17, 22, 28 and 33 all do it this way.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
DECLARE
    unprotected text;
BEGIN
    SELECT string_agg(relname, ', ') INTO unprotected
    FROM pg_class
    WHERE relnamespace = 'plt01'::regnamespace AND relkind = 'r' AND relname LIKE 'evt\_%'
      AND NOT (relrowsecurity AND relforcerowsecurity);
    IF unprotected IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 39 FAILED: evt_ tables without ENABLE and FORCE RLS: %',
            unprotected;
    END IF;
    IF (SELECT count(*) FROM pg_class
        WHERE relnamespace = 'plt01'::regnamespace AND relkind = 'r'
          AND relname LIKE 'evt\_%') < 5 THEN
        RAISE EXCEPTION 'CHECK 39 FAILED: fewer than 5 evt_ tables, so the sweep proved nothing';
    END IF;
    IF (SELECT count(*) FROM pg_class
        WHERE relnamespace = 'plt01'::regnamespace AND relkind = 'r' AND relname LIKE 'evt\_%'
          AND pg_get_userbyid(relowner) <> 'veyro_cp_migrator') <> 0 THEN
        RAISE EXCEPTION 'CHECK 39 FAILED: an evt_ table is not owned by the migrator';
    END IF;
    -- Every policy must exist, must carry a WITH CHECK that says exactly what USING says, and
    -- must actually read the tenant GUC. A policy whose halves agree on `true` would pass the
    -- first two tests and nothing else.
    IF (SELECT count(*) FROM pg_policies
        WHERE schemaname = 'plt01' AND tablename LIKE 'evt\_%'
          AND (with_check IS NULL OR with_check IS DISTINCT FROM qual)) <> 0 THEN
        RAISE EXCEPTION 'CHECK 39 FAILED: WITH CHECK missing or weaker than USING on an evt_ table';
    END IF;
    IF (SELECT count(*) FROM pg_policies
        WHERE schemaname = 'plt01' AND tablename LIKE 'evt\_%') < 5 THEN
        RAISE EXCEPTION 'CHECK 39 FAILED: fewer than 5 evt_ policies, so the sweep proved nothing';
    END IF;
    IF (SELECT count(*) FROM pg_policies
        WHERE schemaname = 'plt01' AND tablename LIKE 'evt\_%'
          AND qual NOT LIKE '%current_setting(''app.tenant_id''%') <> 0 THEN
        RAISE EXCEPTION 'CHECK 39 FAILED: an evt_ policy does not read app.tenant_id';
    END IF;
END $$;
COMMIT;

-- Behaviourally, both directions, over every table.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['evt_outbox', 'evt_deliveries', 'evt_dead_letters',
                               'evt_replay_jobs']
    LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 39 FAILED: tenant B sees % rows of tenant A in %', seen, tbl;
        END IF;
    END LOOP;
    IF (SELECT count(*) FROM plt01.evt_subscriptions) <> 1 THEN
        RAISE EXCEPTION 'CHECK 39 FAILED: tenant B sees % subscriptions, expected its own 1',
            (SELECT count(*) FROM plt01.evt_subscriptions);
    END IF;
END $$;
COMMIT;

BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    IF (SELECT count(*) FROM plt01.evt_outbox) <> 1
       OR (SELECT count(*) FROM plt01.evt_subscriptions) <> 1
       OR (SELECT count(*) FROM plt01.evt_deliveries) <> 1
       OR (SELECT count(*) FROM plt01.evt_dead_letters) <> 1
       OR (SELECT count(*) FROM plt01.evt_replay_jobs) <> 1 THEN
        RAISE EXCEPTION 'CHECK 39 FAILED: tenant A cannot see its own event rows';
    END IF;
END $$;
COMMIT;

BEGIN;
SET LOCAL ROLE veyro_cp_migrator;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['evt_outbox', 'evt_subscriptions', 'evt_deliveries',
                               'evt_dead_letters', 'evt_replay_jobs']
    LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 39 FAILED: the table owner read % rows of %, so FORCE RLS is off',
                seen, tbl;
        END IF;
    END LOOP;
END $$;
COMMIT;

-- ---------------------------------------------------------------- 40. fail closed, evt tables
BEGIN;
SET LOCAL ROLE veyro_cp_app;
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['evt_outbox', 'evt_subscriptions', 'evt_deliveries',
                               'evt_dead_letters', 'evt_replay_jobs']
    LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 40 FAILED: % returned % rows with no tenant context',
                tbl, seen;
        END IF;
    END LOOP;

    -- An event appended with no context is an event nobody can attribute to a tenant, which is
    -- worse than no event: it would fan out to whichever tenant's consumers happened to match.
    BEGIN
        INSERT INTO plt01.evt_outbox
            (tenant_id, event_type, schema_version, aggregate_type, aggregate_id,
             correlation_id, payload)
        VALUES ('11111111-1111-4111-8111-111111111111', 'tenant.activated', 1, 'tenant',
                '11111111-1111-4111-8111-111111111111',
                '33333333-3333-4333-8333-333333333333', '{"a": 1}'::jsonb);
        RAISE EXCEPTION 'CHECK 40 FAILED: an event was appended with no tenant context';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

-- Tenant B cannot plant an event into tenant A. This is the write-side case, and for this table
-- it is the one that matters most: a forged event is acted on by every consumer that subscribes
-- to its type, and the outbox has no DELETE for any runtime role, so it cannot be taken back.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
BEGIN
    BEGIN
        INSERT INTO plt01.evt_outbox
            (tenant_id, event_type, schema_version, aggregate_type, aggregate_id,
             correlation_id, payload)
        VALUES ('11111111-1111-4111-8111-111111111111', 'tenant.suspended', 1, 'tenant',
                '11111111-1111-4111-8111-111111111111',
                '33333333-3333-4333-8333-333333333333', '{"planted": true}'::jsonb);
        RAISE EXCEPTION 'CHECK 40 FAILED: tenant B planted an event in tenant A';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.evt_replay_jobs
            (tenant_id, consumer, event_types, from_time, to_time, requested_by,
             correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'timeline',
                ARRAY['tenant.provisioned'], TIMESTAMPTZ '2026-01-01 00:00:00+00',
                TIMESTAMPTZ '2027-01-01 00:00:00+00',
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 40 FAILED: tenant B requested a replay in tenant A';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 41. cross-tenant parents
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
BEGIN
    BEGIN
        INSERT INTO plt01.evt_deliveries (tenant_id, consumer, event_id)
        VALUES ('22222222-2222-4222-8222-222222222222', 'timeline',
                '77777777-0000-4000-8000-000000000002');
        RAISE EXCEPTION 'CHECK 41 FAILED: a delivery was queued for another tenant''s event';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.evt_dead_letters
            (tenant_id, event_id, consumer, reason, attempts)
        VALUES ('22222222-2222-4222-8222-222222222222',
                '77777777-0000-4000-8000-000000000002', 'ledger', 'borrowed', 1);
        RAISE EXCEPTION 'CHECK 41 FAILED: another tenant''s event was dead-lettered here';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
END $$;
ROLLBACK;

-- `event_id` is globally unique, which is the one index in this schema that spans tenants. It
-- is safe only because the value is generated by the database and `append_event` refuses to
-- take one; asserted here so that a later change making it caller-supplied has to confront this.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
BEGIN
    BEGIN
        INSERT INTO plt01.evt_outbox
            (tenant_id, event_id, event_type, schema_version, aggregate_type, aggregate_id,
             correlation_id, payload)
        VALUES ('22222222-2222-4222-8222-222222222222',
                '77777777-0000-4000-8000-000000000002', 'tenant.activated', 1, 'tenant',
                '22222222-2222-4222-8222-222222222222',
                '33333333-3333-4333-8333-333333333333', '{"a": 1}'::jsonb);
        RAISE EXCEPTION 'CHECK 41 FAILED: event_id is not globally unique';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 42. the relay cannot forge
-- The whole point of separating dispatch state from the envelope: a relay marks an event sent
-- and cannot change what it says. A relay that could rewrite a payload is a relay that can
-- forge an event, and every consumer downstream would believe it.
--
-- **The column grants are compared in full against the catalogue, not checked against a list of
-- names somebody thought to write down.** The first version of this check named nine columns
-- across two tables and tested one of them for the worker role; an independent reviewer widened
-- ten different grants and the suite reported 43/43 every time -- including UPDATE on
-- `evt_outbox.event_type` for the relay, which re-routes a committed event to a different
-- consumer set. That is check 39's lesson one level further in: a denylist proves the names in
-- it, and the moment somebody adds a column is the moment the list is wrong. In this module the
-- column-scoped grant *is* the integrity mechanism -- there is no DELETE and no hash chain
-- behind it -- so it gets the sweep.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
DECLARE
    wrong text;
BEGIN
    WITH expected(tbl, cols) AS (VALUES
        ('evt_outbox',
         'attempts,available_at,dispatched_at,last_error,status'),
        ('evt_subscriptions',
         'active,deactivate_correlation_id,deactivated_at,deactivated_by,max_attempts,replay_safety'),
        ('evt_deliveries',
         'attempts,available_at,from_replay_job_id,handled_at,last_error,status'),
        ('evt_dead_letters',
         'release_correlation_id,release_reason,released_at,released_by'),
        ('evt_replay_jobs',
         'events_replayed,finished_at,last_error,ran_by,run_correlation_id,started_at,status'))
    SELECT string_agg(
               e.tbl || ' / ' || g.grantee || ': ' || coalesce(a.actual, '(none)'), '; ')
    INTO wrong
    FROM expected e
    CROSS JOIN (VALUES ('veyro_cp_app'), ('veyro_cp_worker')) AS g(grantee)
    -- `has_column_privilege` over `pg_attribute`, not `information_schema.column_privileges`:
    -- the information_schema views are filtered to what the *current* user can see, so running
    -- as `veyro_cp_app` they report nothing at all about `veyro_cp_worker` and the comparison
    -- would be vacuous for the relay role -- the very role this check is most about.
    LEFT JOIN LATERAL (
        SELECT string_agg(att.attname, ',' ORDER BY att.attname) AS actual
        FROM pg_attribute att
        WHERE att.attrelid = ('plt01.' || e.tbl)::regclass
          AND att.attnum > 0 AND NOT att.attisdropped
          AND has_column_privilege(g.grantee, att.attrelid, att.attname, 'UPDATE')
    ) a ON true
    WHERE coalesce(a.actual, '(none)') <> e.cols;
    IF wrong IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 42 FAILED: UPDATE column grants differ from the expected set: %',
            wrong;
    END IF;

    -- A table-level UPDATE grant would make every column writable while leaving the
    -- column-privilege view above looking correct, because PostgreSQL reports the table grant
    -- as a grant on every column -- so this is belt and braces rather than a duplicate.
    -- No runtime role holds DELETE, TRUNCATE or REFERENCES anywhere in this module, and no
    -- role outside the three expected ones holds anything at all. Read from `pg_class.relacl`
    -- for the same visibility reason as above.
    IF (SELECT count(*) FROM pg_class c, aclexplode(c.relacl) acl
        WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind = 'r'
          AND c.relname LIKE 'evt\_%'
          AND pg_get_userbyid(acl.grantee) IN ('veyro_cp_app', 'veyro_cp_worker')
          AND acl.privilege_type IN ('DELETE', 'TRUNCATE', 'REFERENCES')) <> 0 THEN
        RAISE EXCEPTION 'CHECK 42 FAILED: a runtime role holds DELETE, TRUNCATE or REFERENCES';
    END IF;
    IF (SELECT count(*) FROM pg_class c, aclexplode(c.relacl) acl
        WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind = 'r'
          AND c.relname LIKE 'evt\_%'
          AND acl.grantee <> 0
          AND pg_get_userbyid(acl.grantee)
              NOT IN ('veyro_cp_app', 'veyro_cp_worker', 'veyro_cp_migrator')) <> 0 THEN
        RAISE EXCEPTION 'CHECK 42 FAILED: an evt_ table is granted to somebody unexpected';
    END IF;
    -- PUBLIC is grantee 0 in an ACL entry, and a PUBLIC grant would make every assertion above
    -- irrelevant.
    IF (SELECT count(*) FROM pg_class c, aclexplode(c.relacl) acl
        WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind = 'r'
          AND c.relname LIKE 'evt\_%' AND acl.grantee = 0) <> 0 THEN
        RAISE EXCEPTION 'CHECK 42 FAILED: an evt_ table carries a PUBLIC grant';
    END IF;

    -- Behaviourally too, because a catalogue row is a claim about behaviour.
    BEGIN
        UPDATE plt01.evt_outbox SET payload = '{"forged": true}'::jsonb;
        RAISE EXCEPTION 'CHECK 42 FAILED: an event payload was rewritten';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        UPDATE plt01.evt_outbox SET event_type = 'tenant.suspended';
        RAISE EXCEPTION 'CHECK 42 FAILED: a committed event was re-routed to another type';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

-- The same from the relay role's own seat. Nothing in this file had ever acted as
-- `veyro_cp_worker`, so a policy carrying `OR current_user = 'veyro_cp_worker'` passed every
-- check while the relay read and wrote every tenant's events. MOD-010 is the first module where
-- the worker has an operational job on the tables, so this is where the block belongs.
BEGIN;
SET LOCAL ROLE veyro_cp_worker;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['evt_outbox', 'evt_deliveries', 'evt_dead_letters',
                               'evt_replay_jobs']
    LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 42 FAILED: the worker role read % rows of tenant A in %',
                seen, tbl;
        END IF;
    END LOOP;
    BEGIN
        UPDATE plt01.evt_outbox SET payload = '{"forged": true}'::jsonb;
        RAISE EXCEPTION 'CHECK 42 FAILED: the worker rewrote an event payload';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

BEGIN;
SET LOCAL ROLE veyro_cp_worker;
DO $$
BEGIN
    IF (SELECT count(*) FROM plt01.evt_outbox) <> 0 THEN
        RAISE EXCEPTION 'CHECK 42 FAILED: the worker read events with no tenant context';
    END IF;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 43. the CHECKs actually bite
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    -- A payload that is not an object passes `jsonb` and breaks every consumer that reads a
    -- field out of it.
    BEGIN
        INSERT INTO plt01.evt_outbox
            (tenant_id, event_type, schema_version, aggregate_type, aggregate_id,
             correlation_id, payload)
        VALUES ('11111111-1111-4111-8111-111111111111', 'tenant.activated', 1, 'tenant',
                '11111111-1111-4111-8111-111111111111',
                '33333333-3333-4333-8333-333333333333', '[1, 2, 3]'::jsonb);
        RAISE EXCEPTION 'CHECK 43 FAILED: an event payload was an array';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- "Dispatched" and a dispatch time are one fact written twice.
    BEGIN
        UPDATE plt01.evt_outbox SET status = 'dispatched'
        WHERE event_id = '77777777-0000-4000-8000-000000000002';
        RAISE EXCEPTION 'CHECK 43 FAILED: an event was dispatched with no dispatch time';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A blank idempotency key is not a key, and every blank one would collide under the
    -- partial unique index.
    BEGIN
        INSERT INTO plt01.evt_outbox
            (tenant_id, event_type, schema_version, aggregate_type, aggregate_id,
             correlation_id, payload, idempotency_key)
        VALUES ('11111111-1111-4111-8111-111111111111', 'tenant.activated', 1, 'tenant',
                '11111111-1111-4111-8111-111111111111',
                '33333333-3333-4333-8333-333333333333', '{"a": 1}'::jsonb, '   ');
        RAISE EXCEPTION 'CHECK 43 FAILED: a blank idempotency key was accepted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- The producer's dedupe: the same key twice in one tenant is the same event.
    BEGIN
        INSERT INTO plt01.evt_outbox
            (tenant_id, event_type, schema_version, aggregate_type, aggregate_id,
             correlation_id, payload, idempotency_key)
        VALUES ('11111111-1111-4111-8111-111111111111', 'tenant.activated', 1, 'tenant',
                '11111111-1111-4111-8111-111111111111',
                '33333333-3333-4333-8333-333333333333', '{"a": 1}'::jsonb,
                'seed-provision-1');
        RAISE EXCEPTION 'CHECK 43 FAILED: the same idempotency key was appended twice';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;

    -- Allowing side effects on a replay is the decision somebody will be asked about.
    BEGIN
        INSERT INTO plt01.evt_replay_jobs
            (tenant_id, consumer, event_types, from_time, to_time, side_effects,
             requested_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'messaging',
                ARRAY['tenant.provisioned'], TIMESTAMPTZ '2026-01-01 00:00:00+00',
                TIMESTAMPTZ '2027-01-01 00:00:00+00', 'allow',
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 43 FAILED: a replay allowed side effects with no reason';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A backwards window selects nothing and reads as a replay that found no events.
    BEGIN
        INSERT INTO plt01.evt_replay_jobs
            (tenant_id, consumer, event_types, from_time, to_time, requested_by,
             correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'timeline',
                ARRAY['tenant.provisioned'], TIMESTAMPTZ '2027-01-01 00:00:00+00',
                TIMESTAMPTZ '2026-01-01 00:00:00+00',
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 43 FAILED: a replay window ran backwards';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A consumer that never runs, and one whose retries would run for a month.
    BEGIN
        INSERT INTO plt01.evt_subscriptions
            (tenant_id, consumer, event_type, max_attempts, registered_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'broken', 'tenant.activated', 0,
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 43 FAILED: a subscription allowed zero attempts';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- `active` and the deactivation stamp are one fact written twice.
    BEGIN
        UPDATE plt01.evt_subscriptions SET active = false
        WHERE subscription_id = '77777777-0000-4000-8000-000000000001';
        RAISE EXCEPTION 'CHECK 43 FAILED: a subscription went inactive with no deactivation time';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- ...and deactivation is attributed, like every other state change here. This case has to
    -- set `active` and `deactivated_at` together, or `evt_subscriptions_active_consistent`
    -- refuses it first and the attribution constraint is never reached: dropping the
    -- attribution constraint left the first version of this check passing, which is the
    -- "fails for the wrong reason" trap check 10 in this file was written to remember.
    BEGIN
        UPDATE plt01.evt_subscriptions
        SET active = false, deactivated_at = now()
        WHERE subscription_id = '77777777-0000-4000-8000-000000000001';
        RAISE EXCEPTION 'CHECK 43 FAILED: a subscription was deactivated with nobody''s name on it';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A dead letter released with no reason, or by nobody.
    BEGIN
        UPDATE plt01.evt_dead_letters SET released_at = now()
        WHERE dead_letter_id = '77777777-0000-4000-8000-000000000003';
        RAISE EXCEPTION 'CHECK 43 FAILED: a dead letter was released with nobody''s name on it';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A delivery cannot be terminal without saying when.
    BEGIN
        UPDATE plt01.evt_deliveries SET status = 'handled'
        WHERE consumer = 'timeline' AND event_id = '77777777-0000-4000-8000-000000000002';
        RAISE EXCEPTION 'CHECK 43 FAILED: a delivery was handled at no particular time';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- **The delivery primary key is the deduplication**, and nothing proved it. Dropping it
    -- left the suite green: `dispatch_pending` inserts with `ON CONFLICT DO NOTHING` and no
    -- conflict target, which stays valid SQL with no primary key and simply stops
    -- deduplicating, so at-least-once silently became at-least-twice -- and for a `suppress`
    -- consumer that means the effect runs again.
    BEGIN
        INSERT INTO plt01.evt_deliveries (tenant_id, consumer, event_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'timeline',
                '77777777-0000-4000-8000-000000000002');
        RAISE EXCEPTION 'CHECK 43 FAILED: one event was queued twice for one consumer';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;

    -- One consumer, one subscription per event type.
    BEGIN
        INSERT INTO plt01.evt_subscriptions
            (tenant_id, consumer, event_type, registered_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'timeline', 'tenant.provisioned',
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 43 FAILED: a consumer was subscribed to one type twice';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;

    -- A live dead letter per (consumer, event): quarantining the same delivery twice while the
    -- first quarantine is unreleased would double-count the failure.
    BEGIN
        INSERT INTO plt01.evt_dead_letters
            (tenant_id, event_id, consumer, reason, attempts)
        VALUES ('11111111-1111-4111-8111-111111111111',
                '77777777-0000-4000-8000-000000000002', 'ledger', 'again', 5);
        RAISE EXCEPTION 'CHECK 43 FAILED: one delivery was quarantined twice at once';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;

    -- An event type outside the catalogue's grammar reaches no consumer and no archive knows
    -- how to read it.
    BEGIN
        INSERT INTO plt01.evt_outbox
            (tenant_id, event_type, schema_version, aggregate_type, aggregate_id,
             correlation_id, payload)
        VALUES ('11111111-1111-4111-8111-111111111111', 'Tenant Activated', 1, 'tenant',
                '11111111-1111-4111-8111-111111111111',
                '33333333-3333-4333-8333-333333333333', '{"a": 1}'::jsonb);
        RAISE EXCEPTION 'CHECK 43 FAILED: a malformed event type was accepted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A status outside the three the relay understands, and a version that cannot name a schema.
    BEGIN
        INSERT INTO plt01.evt_outbox
            (tenant_id, event_type, schema_version, aggregate_type, aggregate_id,
             correlation_id, payload, status)
        VALUES ('11111111-1111-4111-8111-111111111111', 'tenant.activated', 1, 'tenant',
                '11111111-1111-4111-8111-111111111111',
                '33333333-3333-4333-8333-333333333333', '{"a": 1}'::jsonb, 'maybe');
        RAISE EXCEPTION 'CHECK 43 FAILED: an unknown outbox status was accepted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.evt_outbox
            (tenant_id, event_type, schema_version, aggregate_type, aggregate_id,
             correlation_id, payload)
        VALUES ('11111111-1111-4111-8111-111111111111', 'tenant.activated', 0, 'tenant',
                '11111111-1111-4111-8111-111111111111',
                '33333333-3333-4333-8333-333333333333', '{"a": 1}'::jsonb);
        RAISE EXCEPTION 'CHECK 43 FAILED: schema version zero was accepted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A consumer name outside the grammar cannot be matched by a subscription lookup.
    BEGIN
        INSERT INTO plt01.evt_subscriptions
            (tenant_id, consumer, event_type, registered_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'Timeline Service',
                'tenant.activated', '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 43 FAILED: a malformed consumer name was accepted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A quarantine with no reason, or none attempted, says nothing about what broke.
    BEGIN
        INSERT INTO plt01.evt_dead_letters
            (tenant_id, event_id, consumer, reason, attempts)
        VALUES ('11111111-1111-4111-8111-111111111111',
                '77777777-0000-4000-8000-000000000002', 'other', '   ', 3);
        RAISE EXCEPTION 'CHECK 43 FAILED: a dead letter was filed with a blank reason';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.evt_dead_letters
            (tenant_id, event_id, consumer, reason, attempts)
        VALUES ('11111111-1111-4111-8111-111111111111',
                '77777777-0000-4000-8000-000000000002', 'other', 'broke', 0);
        RAISE EXCEPTION 'CHECK 43 FAILED: a dead letter claimed zero attempts';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A replay type list that is empty, or carries something that is not an event name. The
    -- second used to pass: `cardinality > 0` admits ARRAY[NULL] and ARRAY[''], and a job for a
    -- type that cannot exist completes with `events_replayed = 0`, which reads as "there was
    -- nothing to replay" rather than "you mistyped it".
    BEGIN
        INSERT INTO plt01.evt_replay_jobs
            (tenant_id, consumer, event_types, from_time, to_time, requested_by,
             correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'timeline', ARRAY[]::text[],
                TIMESTAMPTZ '2026-01-01 00:00:00+00', TIMESTAMPTZ '2027-01-01 00:00:00+00',
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 43 FAILED: a replay named no event types';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.evt_replay_jobs
            (tenant_id, consumer, event_types, from_time, to_time, requested_by,
             correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'timeline', ARRAY['Billing.*'],
                TIMESTAMPTZ '2026-01-01 00:00:00+00', TIMESTAMPTZ '2027-01-01 00:00:00+00',
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 43 FAILED: a replay named a type that is not an event name';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- Starting a replay is a second decision, and it had nobody's name on it.
    BEGIN
        UPDATE plt01.evt_replay_jobs SET status = 'running', started_at = now()
        WHERE job_id = '77777777-0000-4000-8000-000000000004';
        RAISE EXCEPTION 'CHECK 43 FAILED: a replay was run with nobody''s name on it';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A finished job must say when it finished.
    BEGIN
        UPDATE plt01.evt_replay_jobs SET status = 'completed'
        WHERE job_id = '77777777-0000-4000-8000-000000000004';
        RAISE EXCEPTION 'CHECK 43 FAILED: a replay completed at no particular time';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- Every reference carries the tenant into its parent, including the registry.
    BEGIN
        INSERT INTO plt01.evt_deliveries
            (tenant_id, consumer, event_id, from_replay_job_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'ghost',
                '77777777-0000-4000-8000-000000000002',
                '77777777-0000-4000-8000-0000000000ff');
        RAISE EXCEPTION 'CHECK 43 FAILED: a delivery named a replay job that does not exist';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
END $$;
ROLLBACK;

-- The registry reference, which the composite foreign keys do not cover: an event for a tenant
-- that is not in `plt01_platform.tenants` at all.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '44444444-4444-4444-8444-444444444444';
DO $$
BEGIN
    BEGIN
        INSERT INTO plt01.evt_outbox
            (tenant_id, event_type, schema_version, aggregate_type, aggregate_id,
             correlation_id, payload)
        VALUES ('44444444-4444-4444-8444-444444444444', 'tenant.activated', 1, 'tenant',
                '44444444-4444-4444-8444-444444444444',
                '33333333-3333-4333-8333-333333333333', '{"a": 1}'::jsonb);
        RAISE EXCEPTION 'CHECK 43 FAILED: an event was appended for an unregistered tenant';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
END $$;
ROLLBACK;

\echo 'tenant isolation: 43/43 checks passed'
