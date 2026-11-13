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

\echo 'tenant isolation: 20/20 checks passed'
