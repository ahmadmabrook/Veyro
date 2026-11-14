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
    -- Ordinary and partitioned tables ('r' and 'p'): pg_class also holds this schema's indexes,
    -- and an index never carries row security, so matching on the name alone reports every
    -- table as unprotected.
    -- **'p' is not optional, and leaving it out is how a sweep passes vacuously.** A
    -- partitioned table is relkind 'p'; it holds no storage of its own and is what rows are
    -- addressed through, so a sweep testing only 'r' reports every check passing while
    -- CREATE TABLE ... PARTITION BY LIST (tenant_id) carries unprotected rows under this very
    -- prefix. A reviewer demonstrated it against MOD-013's sweep with a table holding
    -- plaintext contact addresses, readable from another tenant's context and from none. The
    -- filter had been copied forward through nine modules, so it is fixed in all of them at
    -- once rather than in the module where it was found.
    FOR forced IN
        SELECT relforcerowsecurity FROM pg_class
        WHERE relnamespace = 'plt01'::regnamespace AND relkind IN ('r', 'p') AND relname LIKE 'cfg\_%'
    LOOP
        IF NOT forced THEN
            RAISE EXCEPTION 'CHECK 17 FAILED: a cfg_ table does not FORCE row level security';
        END IF;
    END LOOP;
    IF (SELECT count(*) FROM pg_class
        WHERE relnamespace = 'plt01'::regnamespace AND relkind IN ('r', 'p') AND relname LIKE 'cfg\_%'
          AND relrowsecurity AND relforcerowsecurity) <> 7 THEN
        RAISE EXCEPTION 'CHECK 17 FAILED: expected 7 cfg_ tables with RLS enabled and forced, got %',
            (SELECT count(*) FROM pg_class
             WHERE relnamespace = 'plt01'::regnamespace AND relkind IN ('r', 'p')
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
        WHERE relnamespace = 'plt01'::regnamespace AND relkind IN ('r', 'p') AND relname LIKE 'bil\_%'
          AND relrowsecurity AND relforcerowsecurity) <> 9 THEN
        RAISE EXCEPTION 'CHECK 22 FAILED: expected 9 bil_ tables with RLS enabled and forced, got %',
            (SELECT count(*) FROM pg_class
             WHERE relnamespace = 'plt01'::regnamespace AND relkind IN ('r', 'p')
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
        WHERE relnamespace = 'iam'::regnamespace AND relkind IN ('r', 'p')
          AND NOT (relrowsecurity AND relforcerowsecurity)) <> 0 THEN
        RAISE EXCEPTION 'CHECK 28 FAILED: iam tables without forced RLS: %',
            (SELECT string_agg(relname, ', ') FROM pg_class
             WHERE relnamespace = 'iam'::regnamespace AND relkind IN ('r', 'p')
               AND NOT (relrowsecurity AND relforcerowsecurity));
    END IF;
    IF (SELECT count(*) FROM pg_class
        WHERE relnamespace = 'iam'::regnamespace AND relkind IN ('r', 'p')) < 7 THEN
        RAISE EXCEPTION 'CHECK 28 FAILED: the iam schema is missing tables, so the sweep above proved nothing';
    END IF;
    -- Every iam table must be owned by the migrator. One owned by a superuser would ignore
    -- FORCE entirely, and the `RESET ROLE` in the platform migration makes that a live risk.
    IF (SELECT count(*) FROM pg_class
        WHERE relnamespace = 'iam'::regnamespace AND relkind IN ('r', 'p')
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
    WHERE relnamespace = 'plt01'::regnamespace AND relkind IN ('r', 'p') AND relname LIKE 'sec\_%'
      AND NOT (relrowsecurity AND relforcerowsecurity);
    IF unprotected IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 33 FAILED: sec_ tables without ENABLE and FORCE RLS: %',
            unprotected;
    END IF;
    IF (SELECT count(*) FROM pg_class
        WHERE relnamespace = 'plt01'::regnamespace AND relkind IN ('r', 'p')
          AND relname LIKE 'sec\_%') < 9 THEN
        RAISE EXCEPTION 'CHECK 33 FAILED: fewer than 9 sec_ tables, so the sweep proved nothing';
    END IF;
    -- A table owned by a superuser ignores FORCE entirely, so the sweep above would be reading
    -- a flag that does not bind.
    IF (SELECT count(*) FROM pg_class
        WHERE relnamespace = 'plt01'::regnamespace AND relkind IN ('r', 'p') AND relname LIKE 'sec\_%'
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
    WHERE relnamespace = 'plt01'::regnamespace AND relkind IN ('r', 'p') AND relname LIKE 'evt\_%'
      AND NOT (relrowsecurity AND relforcerowsecurity);
    IF unprotected IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 39 FAILED: evt_ tables without ENABLE and FORCE RLS: %',
            unprotected;
    END IF;
    IF (SELECT count(*) FROM pg_class
        WHERE relnamespace = 'plt01'::regnamespace AND relkind IN ('r', 'p')
          AND relname LIKE 'evt\_%') < 5 THEN
        RAISE EXCEPTION 'CHECK 39 FAILED: fewer than 5 evt_ tables, so the sweep proved nothing';
    END IF;
    IF (SELECT count(*) FROM pg_class
        WHERE relnamespace = 'plt01'::regnamespace AND relkind IN ('r', 'p') AND relname LIKE 'evt\_%'
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
        WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
          AND c.relname LIKE 'evt\_%'
          AND pg_get_userbyid(acl.grantee) IN ('veyro_cp_app', 'veyro_cp_worker')
          AND acl.privilege_type IN ('DELETE', 'TRUNCATE', 'REFERENCES')) <> 0 THEN
        RAISE EXCEPTION 'CHECK 42 FAILED: a runtime role holds DELETE, TRUNCATE or REFERENCES';
    END IF;
    IF (SELECT count(*) FROM pg_class c, aclexplode(c.relacl) acl
        WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
          AND c.relname LIKE 'evt\_%'
          AND acl.grantee <> 0
          AND pg_get_userbyid(acl.grantee)
              NOT IN ('veyro_cp_app', 'veyro_cp_worker', 'veyro_cp_migrator')) <> 0 THEN
        RAISE EXCEPTION 'CHECK 42 FAILED: an evt_ table is granted to somebody unexpected';
    END IF;
    -- PUBLIC is grantee 0 in an ACL entry, and a PUBLIC grant would make every assertion above
    -- irrelevant.
    IF (SELECT count(*) FROM pg_class c, aclexplode(c.relacl) acl
        WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
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


-- ---------------------------------------------------------------- seed (tenant plane, MOD-011)
-- Metric points are the one table in this module a *gauge of another module's behaviour* writes
-- to, from the relay and from the gate, so its isolation is the one that decides whether one
-- tenant's operational picture can be assembled from another's traffic.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
INSERT INTO plt01.ops_metric_points
    (tenant_id, point_id, metric_key, bucket_start, dimensions, observations, total)
VALUES (:'tenant_a', '88888888-0000-4000-8000-000000000001', 'authz.denials',
        TIMESTAMPTZ '2026-11-14 09:00:00+00', '{"category": "finance"}'::jsonb, 3, 3);
INSERT INTO plt01.ops_objectives
    (tenant_id, objective_id, objective_key, kind, metric_key, comparison, threshold,
     window_hours, aggregate_as, owner, runbook_ref, set_by, correlation_id)
VALUES (:'tenant_a', '88888888-0000-4000-8000-000000000002', 'login.availability', 'slo',
        'ops.synthetic_success', 'at_least', 0.999, 24, 'mean', 'platform-ops',
        'RB-REL-02#login', :'actor', :'actor');
INSERT INTO plt01.ops_synthetic_checks
    (tenant_id, check_id, check_key, description, workflow, interval_seconds, registered_by,
     correlation_id)
VALUES (:'tenant_a', '88888888-0000-4000-8000-000000000003', 'login.probe',
        'Signs a synthetic member in', 'login', 60, :'actor', :'actor');
INSERT INTO plt01.ops_synthetic_results
    (tenant_id, result_id, check_id, outcome, duration_ms, detail, recorded_by,
     correlation_id, observed_at)
VALUES (:'tenant_a', '88888888-0000-4000-8000-000000000004',
        '88888888-0000-4000-8000-000000000003', 'failed', 812, 'timed out at the token step',
        :'actor', :'actor', TIMESTAMPTZ '2026-11-14 09:15:00+00');
INSERT INTO plt01.ops_capacity_forecasts
    (tenant_id, forecast_id, resource, horizon_days, current_value, projected_value,
     limit_value, headroom_bp, basis, forecast_by, correlation_id)
VALUES (:'tenant_a', '88888888-0000-4000-8000-000000000005', 'database_connections', 90,
        120, 430, 500, 1400, 'linear fit over 60 days of peak concurrency', :'actor',
        :'actor');
INSERT INTO plt01.ops_cost_records
    (tenant_id, cost_record_id, period_start, period_end, dimension, dimension_value,
     currency, amount_minor, source, allocated_by, correlation_id)
VALUES (:'tenant_a', '88888888-0000-4000-8000-000000000006', DATE '2026-11-01',
        DATE '2026-11-30', 'ai_model', 'claude-opus', 'EUR', 412000,
        'vendor statement 2026-11', :'actor', :'actor');
INSERT INTO plt01.ops_budgets
    (tenant_id, budget_id, budget_key, dimension, dimension_value, currency, amount_minor,
     period, warn_at_bp, owner, set_by, correlation_id)
VALUES (:'tenant_a', '88888888-0000-4000-8000-000000000007', 'ai.monthly', 'ai_model',
        'claude-opus', 'EUR', 500000, 'monthly', 8000, 'platform-ops', :'actor', :'actor');
INSERT INTO plt01.ops_budget_alerts
    (tenant_id, alert_id, budget_id, period_start, threshold_bp, spent_minor, budget_minor,
     currency, owner)
VALUES (:'tenant_a', '88888888-0000-4000-8000-000000000008',
        '88888888-0000-4000-8000-000000000007', DATE '2026-11-01', 8000, 412000, 500000,
        'EUR', 'platform-ops');
COMMIT;

-- Tenant B holds one forecast of its own, so a predicate that leaked shows up as a count above
-- the expected one rather than as the zero an empty table would give anyway.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
INSERT INTO plt01.ops_capacity_forecasts
    (tenant_id, resource, horizon_days, current_value, projected_value, basis, forecast_by,
     correlation_id)
VALUES (:'tenant_b', 'storage_bytes', 30, 10, 20, 'tenant B''s own forecast', :'actor',
        :'actor');
COMMIT;

-- ---------------------------------------------------------------- 44. ops tables isolate
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['ops_metric_points', 'ops_objectives', 'ops_synthetic_checks',
                               'ops_synthetic_results', 'ops_cost_records', 'ops_budgets',
                               'ops_budget_alerts']
    LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 44 FAILED: tenant B sees % rows of tenant A in %', seen, tbl;
        END IF;
    END LOOP;
    IF (SELECT count(*) FROM plt01.ops_capacity_forecasts) <> 1 THEN
        RAISE EXCEPTION 'CHECK 44 FAILED: tenant B sees % forecasts, expected its own 1',
            (SELECT count(*) FROM plt01.ops_capacity_forecasts);
    END IF;
    IF EXISTS (SELECT 1 FROM plt01.ops_capacity_forecasts
               WHERE resource = 'database_connections') THEN
        RAISE EXCEPTION 'CHECK 44 FAILED: tenant B read tenant A''s capacity forecast';
    END IF;
END $$;
COMMIT;

BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    -- All eight, positively. A table whose positive case nobody asserts could return zero for
    -- the wrong reason and only the negative sweep would notice -- which is the direction that
    -- reads as a pass.
    IF (SELECT count(*) FROM plt01.ops_metric_points) <> 1
       OR (SELECT count(*) FROM plt01.ops_objectives) <> 1
       OR (SELECT count(*) FROM plt01.ops_synthetic_checks) <> 1
       OR (SELECT count(*) FROM plt01.ops_synthetic_results) <> 1
       OR (SELECT count(*) FROM plt01.ops_capacity_forecasts) <> 1
       OR (SELECT count(*) FROM plt01.ops_cost_records) <> 1
       OR (SELECT count(*) FROM plt01.ops_budgets) <> 1
       OR (SELECT count(*) FROM plt01.ops_budget_alerts) <> 1 THEN
        RAISE EXCEPTION 'CHECK 44 FAILED: tenant A cannot see its own ops rows';
    END IF;
END $$;
COMMIT;

-- Swept from the catalogue, never from a list of table names: that is checks 17, 22, 28, 33 and
-- 39's shared lesson and the one MOD-009 regressed on. Both halves of the policy are asserted --
-- `USING` keeps another tenant's rows out of a read and `WITH CHECK` keeps this tenant from
-- writing a row labelled as somebody else's, and a policy carrying only the first passes every
-- read test while leaving writes unguarded.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
DECLARE
    unprotected text;
BEGIN
    SELECT string_agg(relname, ', ') INTO unprotected
    FROM pg_class
    WHERE relnamespace = 'plt01'::regnamespace AND relkind IN ('r', 'p') AND relname LIKE 'ops\_%'
      AND NOT (relrowsecurity AND relforcerowsecurity);
    IF unprotected IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 44 FAILED: ops_ tables without ENABLE and FORCE RLS: %',
            unprotected;
    END IF;
    IF (SELECT count(*) FROM pg_class
        WHERE relnamespace = 'plt01'::regnamespace AND relkind IN ('r', 'p')
          AND relname LIKE 'ops\_%') < 8 THEN
        RAISE EXCEPTION 'CHECK 44 FAILED: fewer than 8 ops_ tables, so the sweep proved nothing';
    END IF;
    -- A table owned by a superuser ignores FORCE entirely, so the flag above would not bind.
    IF (SELECT count(*) FROM pg_class
        WHERE relnamespace = 'plt01'::regnamespace AND relkind IN ('r', 'p') AND relname LIKE 'ops\_%'
          AND pg_get_userbyid(relowner) <> 'veyro_cp_migrator') <> 0 THEN
        RAISE EXCEPTION 'CHECK 44 FAILED: an ops_ table is not owned by the migrator';
    END IF;
    -- Every ops_ table has exactly one policy, and that policy carries both halves of the
    -- predicate. A table with no policy at all under FORCE RLS denies everything, which fails
    -- safe but silently -- and a policy whose `WITH CHECK` is missing inherits `USING`, which
    -- is only equivalent until somebody edits one of them.
    SELECT string_agg(c.relname, ', ') INTO unprotected
    FROM pg_class c
    LEFT JOIN pg_policies p
      ON p.schemaname = 'plt01' AND p.tablename = c.relname
     AND p.qual = '(tenant_id = (NULLIF(current_setting(''app.tenant_id''::text, true), ''''::text))::uuid)'
     AND p.with_check = p.qual
    WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
      AND c.relname LIKE 'ops\_%' AND p.policyname IS NULL;
    IF unprotected IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 44 FAILED: ops_ tables without the exact tenant predicate in '
            'both USING and WITH CHECK: %', unprotected;
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
    FOREACH tbl IN ARRAY ARRAY['ops_metric_points', 'ops_objectives', 'ops_synthetic_checks',
                               'ops_synthetic_results', 'ops_capacity_forecasts',
                               'ops_cost_records', 'ops_budgets', 'ops_budget_alerts']
    LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 44 FAILED: the table owner read % rows of %, so FORCE RLS is off',
                seen, tbl;
        END IF;
    END LOOP;
END $$;
COMMIT;

-- **The worker role gets its own seat, because a second policy is OR'd with the first.**
-- Everything above this point runs as `veyro_cp_app`. PostgreSQL combines permissive policies
-- with OR, so `CREATE POLICY ... ON plt01.ops_cost_records FOR ALL TO veyro_cp_worker USING
-- (true)` leaves every assertion above untouched and true -- the module's own policy is still
-- there, still exactly right, still the only one the catalogue comparison looks at -- while the
-- worker reads every tenant's ledger from any context and from no context.
--
-- This is verbatim the regression check 42's comment records: `veyro_cp_worker` was never
-- exercised behaviourally anywhere in the suite, so a policy naming it passed everything. That
-- was found for `evt_` tables by MOD-010's review and the fix was scoped to `evt_` tables;
-- MOD-011 granted the worker identical access to eight more and inherited the blind spot, and a
-- reviewer opened all eight while the suite reported 48/48. **A role that holds a grant gets a
-- seat, in every module.**
BEGIN;
SET LOCAL ROLE veyro_cp_worker;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['ops_metric_points', 'ops_objectives', 'ops_synthetic_checks',
                               'ops_synthetic_results', 'ops_cost_records', 'ops_budgets',
                               'ops_budget_alerts']
    LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 44 FAILED: the worker read % rows of tenant A in % from '
                'tenant B''s context', seen, tbl;
        END IF;
    END LOOP;
    -- Tenant B owns exactly one forecast, so the worker seeing it is the positive case that
    -- stops this block passing because the worker can see nothing at all.
    IF (SELECT count(*) FROM plt01.ops_capacity_forecasts) <> 1 THEN
        RAISE EXCEPTION 'CHECK 44 FAILED: the worker sees % forecasts in tenant B, expected 1',
            (SELECT count(*) FROM plt01.ops_capacity_forecasts);
    END IF;
    IF EXISTS (SELECT 1 FROM plt01.ops_capacity_forecasts
               WHERE resource = 'database_connections') THEN
        RAISE EXCEPTION 'CHECK 44 FAILED: the worker read tenant A''s forecast from tenant B';
    END IF;
END $$;
COMMIT;

BEGIN;
SET LOCAL ROLE veyro_cp_worker;
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['ops_metric_points', 'ops_objectives', 'ops_synthetic_checks',
                               'ops_synthetic_results', 'ops_capacity_forecasts',
                               'ops_cost_records', 'ops_budgets', 'ops_budget_alerts']
    LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 44 FAILED: the worker read % rows of % with no tenant context',
                seen, tbl;
        END IF;
    END LOOP;
END $$;
ROLLBACK;

-- And the structural half of the same finding: exactly one permissive policy per table. The
-- predicate comparison above asserts that a *matching* policy exists, which an added second
-- policy satisfies trivially. A restrictive policy would be additional protection and is not
-- what this refuses.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
DECLARE
    extra text;
BEGIN
    SELECT string_agg(c.relname || ' (' || n::text || ')', ', ') INTO extra
    FROM pg_class c
    CROSS JOIN LATERAL (
        SELECT count(*) AS n FROM pg_policies p
        WHERE p.schemaname = 'plt01' AND p.tablename = c.relname AND p.permissive = 'PERMISSIVE'
    ) counted
    WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
      AND c.relname LIKE 'ops\_%' AND counted.n <> 1;
    IF extra IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 44 FAILED: ops_ tables without exactly one permissive policy: %',
            extra;
    END IF;
    -- A tenant-leading primary key, which the isolation rule states and nothing asserted. It is
    -- index locality rather than a leak, and it is one query.
    SELECT string_agg(c.relname, ', ') INTO extra
    FROM pg_class c
    JOIN pg_index i ON i.indrelid = c.oid AND i.indisprimary
    WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
      AND c.relname LIKE 'ops\_%'
      AND (SELECT attname FROM pg_attribute
           WHERE attrelid = c.oid AND attnum = i.indkey[0]) <> 'tenant_id';
    IF extra IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 44 FAILED: ops_ tables whose primary key does not lead with '
            'tenant_id: %', extra;
    END IF;
END $$;
COMMIT;

-- ---------------------------------------------------------------- 45. fail closed, ops tables
BEGIN;
SET LOCAL ROLE veyro_cp_app;
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['ops_metric_points', 'ops_objectives', 'ops_synthetic_checks',
                               'ops_synthetic_results', 'ops_capacity_forecasts',
                               'ops_cost_records', 'ops_budgets', 'ops_budget_alerts']
    LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 45 FAILED: % returned % rows with no tenant context',
                tbl, seen;
        END IF;
    END LOOP;

    -- A measurement written with no context is a measurement nobody can attribute, and this
    -- one would land in whichever tenant's dashboard happened to query the key.
    BEGIN
        INSERT INTO plt01.ops_metric_points
            (tenant_id, metric_key, bucket_start, dimensions, observations, total)
        VALUES ('11111111-1111-4111-8111-111111111111', 'authz.denials',
                TIMESTAMPTZ '2026-11-14 10:00:00+00', '{"category": "finance"}'::jsonb, 1, 1);
        RAISE EXCEPTION 'CHECK 45 FAILED: a metric point was written with no tenant context';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.ops_cost_records
            (tenant_id, period_start, period_end, dimension, dimension_value, currency,
             amount_minor, source, allocated_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', DATE '2026-11-01', DATE '2026-11-30',
                'compute', 'api', 'EUR', 1, 'nowhere',
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 45 FAILED: a cost was allocated with no tenant context';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

-- A tenant cannot label a row as somebody else's, which is the `WITH CHECK` half doing its job
-- rather than the `USING` half.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    BEGIN
        INSERT INTO plt01.ops_metric_points
            (tenant_id, metric_key, bucket_start, dimensions, observations, total)
        VALUES ('22222222-2222-4222-8222-222222222222', 'authz.denials',
                TIMESTAMPTZ '2026-11-14 10:00:00+00', '{"category": "finance"}'::jsonb, 1, 1);
        RAISE EXCEPTION 'CHECK 45 FAILED: a point was written into another tenant';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 46. cross-tenant parents
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
BEGIN
    BEGIN
        INSERT INTO plt01.ops_synthetic_results
            (tenant_id, check_id, outcome, duration_ms, recorded_by, correlation_id,
             observed_at)
        VALUES ('22222222-2222-4222-8222-222222222222',
                '88888888-0000-4000-8000-000000000003', 'passed', 10,
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333', now());
        RAISE EXCEPTION 'CHECK 46 FAILED: a result was recorded against another tenant''s check';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.ops_budget_alerts
            (tenant_id, budget_id, period_start, threshold_bp, spent_minor, budget_minor,
             currency, owner)
        VALUES ('22222222-2222-4222-8222-222222222222',
                '88888888-0000-4000-8000-000000000007', DATE '2026-11-01', 8000, 1, 2, 'EUR',
                'borrowed');
        RAISE EXCEPTION 'CHECK 46 FAILED: an alert was raised against another tenant''s budget';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.ops_cost_records
            (tenant_id, period_start, period_end, dimension, dimension_value, currency,
             amount_minor, source, corrects_cost_record_id, allocated_by, correlation_id)
        VALUES ('22222222-2222-4222-8222-222222222222', DATE '2026-11-01', DATE '2026-11-30',
                'ai_model', 'claude-opus', 'EUR', -1, 'correction',
                '88888888-0000-4000-8000-000000000006',
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 46 FAILED: another tenant''s cost record was corrected from here';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
END $$;
ROLLBACK;

-- The registry reference, which the composite foreign keys do not cover: an ops row for a
-- tenant that is not in `plt01_platform.tenants` at all.
--
-- **Swept from the catalogue and sampled behaviourally, not sampled alone.** The first version
-- of this proved one table of eight and a reviewer dropped the other seven -- including the cost
-- ledger and the budget registry -- with the suite still reporting every check passing. The
-- migration's own header singles this reference out as the one two earlier modules carried with
-- nothing proving it; writing one case and asserting the rest is how that happens again.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
DECLARE
    missing text;
BEGIN
    SELECT string_agg(c.relname, ', ') INTO missing
    FROM pg_class c
    WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
      AND c.relname LIKE 'ops\_%'
      AND NOT EXISTS (
          SELECT 1 FROM pg_constraint fk
          WHERE fk.conrelid = c.oid AND fk.contype = 'f'
            AND fk.confrelid = 'plt01_platform.tenants'::regclass
            AND fk.conkey = ARRAY[(SELECT attnum FROM pg_attribute
                                   WHERE attrelid = c.oid AND attname = 'tenant_id')]);
    IF missing IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 46 FAILED: ops_ tables with no tenant registry foreign key: %',
            missing;
    END IF;
END $$;
COMMIT;

BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '44444444-4444-4444-8444-444444444444';
DO $$
BEGIN
    BEGIN
        INSERT INTO plt01.ops_metric_points
            (tenant_id, metric_key, bucket_start, dimensions, observations, total)
        VALUES ('44444444-4444-4444-8444-444444444444', 'authz.denials',
                TIMESTAMPTZ '2026-11-14 10:00:00+00', '{"category": "finance"}'::jsonb, 1, 1);
        RAISE EXCEPTION 'CHECK 46 FAILED: a point was recorded for an unregistered tenant';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 47. measurements are evidence
-- Four of the eight tables carry no UPDATE at all and the other four carry a column-scoped one,
-- and in this module that grant **is** the integrity mechanism: there is no hash chain behind a
-- probe result, a forecast, a cost figure or an alert, so the only thing standing between a
-- measurement and a convenient revision of it is the absence of a privilege.
--
-- Swept in full against the catalogue, per column and per role, because MOD-010's review showed
-- what a hand-written list of column names is worth: ten different grant-widenings passed 43/43.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
DECLARE
    wrong text;
BEGIN
    WITH expected(tbl, cols) AS (VALUES
        ('ops_metric_points', 'observations,total'),
        ('ops_objectives', 'retire_correlation_id,retired_at,retired_by'),
        ('ops_synthetic_checks',
         'disable_correlation_id,disabled_at,disabled_by,enabled,interval_seconds'),
        ('ops_synthetic_results', '(none)'),
        ('ops_capacity_forecasts', '(none)'),
        ('ops_cost_records', '(none)'),
        ('ops_budgets', 'retire_correlation_id,retired_at,retired_by'),
        ('ops_budget_alerts', '(none)'))
    SELECT string_agg(
               e.tbl || ' / ' || g.grantee || ': ' || coalesce(a.actual, '(none)'), '; ')
    INTO wrong
    FROM expected e
    CROSS JOIN (VALUES ('veyro_cp_app'), ('veyro_cp_worker')) AS g(grantee)
    -- `has_column_privilege` over `pg_attribute`, not `information_schema.column_privileges`:
    -- those views are filtered to what the current user can see, so running as `veyro_cp_app`
    -- they report nothing about `veyro_cp_worker` and the comparison would be vacuous for half
    -- the roles it claims to cover.
    LEFT JOIN LATERAL (
        SELECT string_agg(att.attname, ',' ORDER BY att.attname) AS actual
        FROM pg_attribute att
        WHERE att.attrelid = ('plt01.' || e.tbl)::regclass
          AND att.attnum > 0 AND NOT att.attisdropped
          AND has_column_privilege(g.grantee, att.attrelid, att.attname, 'UPDATE')
    ) a ON true
    WHERE coalesce(a.actual, '(none)') <> e.cols;
    IF wrong IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 47 FAILED: UPDATE column grants differ from the expected set: %',
            wrong;
    END IF;

    -- The expectation above is per column and per role, and its *table* list was hand-written,
    -- so a ninth `ops_` table with table-wide UPDATE to both roles passed it in silence. The
    -- list has to cover the catalogue, which makes adding a table without stating what it may
    -- update a failure rather than an omission.
    SELECT string_agg(c.relname, ', ') INTO wrong
    FROM pg_class c
    WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
      AND c.relname LIKE 'ops\_%'
      AND c.relname NOT IN ('ops_metric_points', 'ops_objectives', 'ops_synthetic_checks',
                            'ops_synthetic_results', 'ops_capacity_forecasts',
                            'ops_cost_records', 'ops_budgets', 'ops_budget_alerts');
    IF wrong IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 47 FAILED: ops_ tables with no stated UPDATE expectation: %',
            wrong;
    END IF;

    -- The three bans below read `pg_class.relacl`, which holds table-level grants only, so a
    -- *column*-level grant is invisible to all three: `GRANT SELECT (detail) ON
    -- plt01.ops_synthetic_results TO PUBLIC` and `GRANT REFERENCES (tenant_id) ... TO
    -- veyro_cp_app` both passed. Neither is exploitable today -- a PUBLIC grantee matches no
    -- policy and `veyro_iam_app` holds no USAGE on `plt01` -- but the isolation rule states
    -- the PUBLIC and REFERENCES bans without that qualification, and a ban enforced only at
    -- one granularity is a ban somebody will step around at the other.
    IF (SELECT count(*) FROM pg_class c
        JOIN pg_attribute att ON att.attrelid = c.oid AND att.attnum > 0
                             AND NOT att.attisdropped AND att.attacl IS NOT NULL,
        LATERAL aclexplode(att.attacl) acl
        WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
          AND c.relname LIKE 'ops\_%'
          AND (acl.grantee = 0
               OR acl.privilege_type IN ('DELETE', 'TRUNCATE', 'REFERENCES')
               OR pg_get_userbyid(acl.grantee)
                  NOT IN ('veyro_cp_app', 'veyro_cp_worker', 'veyro_cp_migrator'))) <> 0 THEN
        RAISE EXCEPTION 'CHECK 47 FAILED: a column-level grant is PUBLIC, is REFERENCES, or '
            'names a role outside the three expected ones';
    END IF;

    IF (SELECT count(*) FROM pg_class c, aclexplode(c.relacl) acl
        WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
          AND c.relname LIKE 'ops\_%'
          AND pg_get_userbyid(acl.grantee) IN ('veyro_cp_app', 'veyro_cp_worker')
          AND acl.privilege_type IN ('DELETE', 'TRUNCATE', 'REFERENCES')) <> 0 THEN
        RAISE EXCEPTION 'CHECK 47 FAILED: a runtime role holds DELETE, TRUNCATE or REFERENCES';
    END IF;
    IF (SELECT count(*) FROM pg_class c, aclexplode(c.relacl) acl
        WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
          AND c.relname LIKE 'ops\_%'
          AND acl.grantee <> 0
          AND pg_get_userbyid(acl.grantee)
              NOT IN ('veyro_cp_app', 'veyro_cp_worker', 'veyro_cp_migrator')) <> 0 THEN
        RAISE EXCEPTION 'CHECK 47 FAILED: an ops_ table is granted to somebody unexpected';
    END IF;
    -- PUBLIC is grantee 0, and a PUBLIC grant would make every assertion above irrelevant.
    IF (SELECT count(*) FROM pg_class c, aclexplode(c.relacl) acl
        WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
          AND c.relname LIKE 'ops\_%' AND acl.grantee = 0) <> 0 THEN
        RAISE EXCEPTION 'CHECK 47 FAILED: an ops_ table carries a PUBLIC grant';
    END IF;

    -- Behaviourally too, because a catalogue row is a claim about behaviour. Each of these is
    -- a rewrite somebody with a motive would want: a probe failure made to read as a pass, a
    -- forecast made to agree with what happened, a cost reduced after the margin was reported,
    -- an alert's owner moved to somebody who was not told.
    BEGIN
        UPDATE plt01.ops_synthetic_results SET outcome = 'passed', detail = NULL;
        RAISE EXCEPTION 'CHECK 47 FAILED: a probe failure was rewritten as a pass';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        UPDATE plt01.ops_capacity_forecasts SET projected_value = 1;
        RAISE EXCEPTION 'CHECK 47 FAILED: a capacity forecast was revised';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        UPDATE plt01.ops_cost_records SET amount_minor = 1;
        RAISE EXCEPTION 'CHECK 47 FAILED: an allocated cost was revised';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        UPDATE plt01.ops_budget_alerts SET owner = 'nobody';
        RAISE EXCEPTION 'CHECK 47 FAILED: a raised alert''s owner was rewritten';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    -- The identity of a series: a point whose metric key, bucket or dimensions could change is
    -- a measurement that can be moved onto another chart, which is indistinguishable from
    -- fabricating one there.
    BEGIN
        UPDATE plt01.ops_metric_points SET metric_key = 'ops.synthetic_success';
        RAISE EXCEPTION 'CHECK 47 FAILED: a metric point was moved to another series';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        UPDATE plt01.ops_metric_points SET dimensions = '{"category": "access"}'::jsonb;
        RAISE EXCEPTION 'CHECK 47 FAILED: a metric point''s dimensions were rewritten';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    -- An objective's threshold is what it was when something breached it. Editing it rewrites
    -- the reason an alert fired, which is why retirement is the only exit.
    BEGIN
        UPDATE plt01.ops_objectives SET threshold = 0;
        RAISE EXCEPTION 'CHECK 47 FAILED: an objective''s threshold was edited';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        UPDATE plt01.ops_budgets SET amount_minor = 99999999;
        RAISE EXCEPTION 'CHECK 47 FAILED: a budget was edited rather than retired';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        DELETE FROM plt01.ops_budget_alerts;
        RAISE EXCEPTION 'CHECK 47 FAILED: a raised alert was deleted';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

-- The accumulation column grant is a real UPDATE, so it has to be shown to work as well as to
-- be bounded -- a check that only proves what is refused would pass just as happily if the
-- grant were missing altogether and the service were silently failing to accumulate.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    INSERT INTO plt01.ops_metric_points
        (tenant_id, metric_key, bucket_start, dimensions, observations, total)
    VALUES ('11111111-1111-4111-8111-111111111111', 'authz.denials',
            TIMESTAMPTZ '2026-11-14 09:00:00+00', '{"category": "finance"}'::jsonb, 2, 2)
    ON CONFLICT (tenant_id, metric_key, bucket_start, dimensions) DO UPDATE
    SET observations = plt01.ops_metric_points.observations + EXCLUDED.observations,
        total = plt01.ops_metric_points.total + EXCLUDED.total;
    IF (SELECT observations FROM plt01.ops_metric_points
        WHERE point_id = '88888888-0000-4000-8000-000000000001') <> 5 THEN
        RAISE EXCEPTION 'CHECK 47 FAILED: the bucket did not accumulate';
    END IF;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 48. the ops constraints
-- The rules a reader of the service would assume and only the database can hold. Each of these
-- has been removed and the suite watched to fail; a constraint nobody has broken on purpose is
-- a constraint nobody has tested.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    -- The bucket is the hour. A point off the hour aggregates with nothing and reads as a gap
    -- in the series rather than as the measurement it is.
    BEGIN
        INSERT INTO plt01.ops_metric_points
            (tenant_id, metric_key, bucket_start, dimensions, observations, total)
        VALUES ('11111111-1111-4111-8111-111111111111', 'authz.denials', TIMESTAMPTZ '2026-11-14 09:17:00+00',
                '{"category": "access"}'::jsonb, 1, 1);
        RAISE EXCEPTION 'CHECK 48 FAILED: a point was written off the hour';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- A zero-observation point makes a mean a division by zero and a ratio meaningless.
    BEGIN
        INSERT INTO plt01.ops_metric_points
            (tenant_id, metric_key, bucket_start, dimensions, observations, total)
        VALUES ('11111111-1111-4111-8111-111111111111', 'authz.denials', TIMESTAMPTZ '2026-11-14 11:00:00+00',
                '{"category": "access"}'::jsonb, 0, 0);
        RAISE EXCEPTION 'CHECK 48 FAILED: a point with no observations was written';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- Dimensions are an object. An array or a scalar here would compare unequal to every
    -- dimension slice a reader sends and so would be invisible to every query.
    BEGIN
        INSERT INTO plt01.ops_metric_points
            (tenant_id, metric_key, bucket_start, dimensions, observations, total)
        VALUES ('11111111-1111-4111-8111-111111111111', 'authz.denials', TIMESTAMPTZ '2026-11-14 12:00:00+00',
                '["category"]'::jsonb, 1, 1);
        RAISE EXCEPTION 'CHECK 48 FAILED: dimensions were written as an array';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- The unique index *is* the accumulation. Without it two writers each insert and the series
    -- doubles silently, which is the failure a dashboard cannot show you.
    BEGIN
        INSERT INTO plt01.ops_metric_points
            (tenant_id, metric_key, bucket_start, dimensions, observations, total)
        VALUES ('11111111-1111-4111-8111-111111111111', 'authz.denials', TIMESTAMPTZ '2026-11-14 09:00:00+00',
                '{"category": "finance"}'::jsonb, 1, 1);
        RAISE EXCEPTION 'CHECK 48 FAILED: a second row was written for one bucket';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;

    -- An objective's aggregate is a closed set, and the set is what this store can compute. A
    -- percentile admitted here would be evaluated against a mean and reported as a verdict.
    BEGIN
        INSERT INTO plt01.ops_objectives
            (tenant_id, objective_key, kind, metric_key, comparison, threshold, window_hours,
             aggregate_as, owner, runbook_ref, set_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'api.p95', 'performance_budget', 'events.delivery_duration',
                'at_most', 500, 24, 'p95', 'platform-ops', 'RB-REL-02', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: a percentile objective was admitted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- An objective with no runbook produces an alert whose recipient has nothing to do, which
    -- is the actionability control in paragraph 3504 read as a constraint. Blank, not absent:
    -- `length(btrim(' ')) > 0` is the form that catches a caller sending whitespace to satisfy
    -- a NOT NULL.
    BEGIN
        INSERT INTO plt01.ops_objectives
            (tenant_id, objective_key, kind, metric_key, comparison, threshold, window_hours,
             aggregate_as, owner, runbook_ref, set_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'api.load', 'slo', 'events.delivery_success', 'at_least', 0.99,
                24, 'mean', 'platform-ops', '   ', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: an objective was defined with a blank runbook';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- Two live objectives under one key would be two answers to the same question.
    BEGIN
        INSERT INTO plt01.ops_objectives
            (tenant_id, objective_key, kind, metric_key, comparison, threshold, window_hours,
             aggregate_as, owner, runbook_ref, set_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'login.availability', 'slo', 'ops.synthetic_success', 'at_least',
                0.5, 24, 'mean', 'somebody-else', 'RB-REL-02', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: a second live objective took the same key';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;
    -- Retiring without saying who. The one act that ends an objective's authority has to carry
    -- an actor, for the same reason releasing a legal hold does: the row is the only record.
    BEGIN
        UPDATE plt01.ops_objectives SET retired_at = now()
        WHERE objective_id = '88888888-0000-4000-8000-000000000002';
        RAISE EXCEPTION 'CHECK 48 FAILED: an objective was retired by nobody';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A failed probe with no detail is an alert nobody can act on. `coalesce` is load-bearing
    -- in the constraint: `length(btrim(NULL)) > 0` is NULL and a CHECK passes on NULL, which is
    -- exactly how MOD-009's legal-hold constraint admitted the row it existed to refuse.
    BEGIN
        INSERT INTO plt01.ops_synthetic_results
            (tenant_id, check_id, outcome, duration_ms, detail, recorded_by, correlation_id,
             observed_at)
        VALUES ('11111111-1111-4111-8111-111111111111',
                '88888888-0000-4000-8000-000000000003', 'failed', 10, NULL,
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333', now());
        RAISE EXCEPTION 'CHECK 48 FAILED: a failure was recorded with no detail';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- A check whose flag and whose history disagree. Either reading is defensible on its own,
    -- which is what makes the pair unanswerable.
    BEGIN
        UPDATE plt01.ops_synthetic_checks SET disabled_at = now(), disabled_by = '33333333-3333-4333-8333-333333333333',
            disable_correlation_id = '33333333-3333-4333-8333-333333333333'
        WHERE check_id = '88888888-0000-4000-8000-000000000003';
        RAISE EXCEPTION 'CHECK 48 FAILED: a check reads enabled and disabled at once';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A zero cost is a row that changes no total and hides in every report; a correction is a
    -- later row with the opposite sign, never this one.
    BEGIN
        INSERT INTO plt01.ops_cost_records
            (tenant_id, period_start, period_end, dimension, dimension_value, currency,
             amount_minor, source, allocated_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', DATE '2026-11-01', DATE '2026-11-30', 'compute', 'api', 'EUR', 0,
                'vendor', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: a zero cost was allocated';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- A cost with no stated source is a guess that will be read as a measurement, and there is
    -- no bill in this repository to settle the question later.
    BEGIN
        INSERT INTO plt01.ops_cost_records
            (tenant_id, period_start, period_end, dimension, dimension_value, currency,
             amount_minor, source, allocated_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', DATE '2026-11-01', DATE '2026-11-30', 'compute', 'api', 'EUR', 5,
                '  ', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: a cost was allocated with no source';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- A period that runs backwards sums into whichever range a report happens to ask for.
    BEGIN
        INSERT INTO plt01.ops_cost_records
            (tenant_id, period_start, period_end, dimension, dimension_value, currency,
             amount_minor, source, allocated_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', DATE '2026-11-30', DATE '2026-11-01', 'compute', 'api', 'EUR', 5,
                'vendor', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: a cost period ran backwards';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A non-total budget with no dimension value matches every cost in its dimension and so
    -- reads as a total while claiming to be narrower -- the direction that under-alerts.
    BEGIN
        INSERT INTO plt01.ops_budgets
            (tenant_id, budget_key, dimension, dimension_value, currency, amount_minor,
             period, owner, set_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'ai.unscoped', 'ai_model', NULL, 'EUR', 1000, 'monthly',
                'platform-ops', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: a dimensioned budget named no value';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- One alert per budget, period and threshold. Without it an hourly sweep raises the same
    -- alert every hour, which is how a channel becomes one people mute.
    BEGIN
        INSERT INTO plt01.ops_budget_alerts
            (tenant_id, budget_id, period_start, threshold_bp, spent_minor, budget_minor,
             currency, owner)
        VALUES ('11111111-1111-4111-8111-111111111111', '88888888-0000-4000-8000-000000000007', DATE '2026-11-01', 8000,
                420000, 500000, 'EUR', 'platform-ops');
        RAISE EXCEPTION 'CHECK 48 FAILED: the same burn alert was raised twice';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;

    -- ------------------------------------------------------------------------------------
    -- Everything from here was added after review. The first version of check 48 proved
    -- twelve constraints and three indexes, and its preamble said -- truthfully of those
    -- fifteen and falsely of the module -- that each had been broken on purpose. A reviewer
    -- dropped 24 of the remaining ones individually and the suite reported 48/48 every time,
    -- including four of the five on `ops_capacity_forecasts`, which had no evidence at all.
    -- A constraint nobody has broken on purpose is a constraint nobody has tested, and the
    -- sentence only means something if it covers the table rather than the sample.
    -- ------------------------------------------------------------------------------------

    -- An objective names the series it is about, and the shape has to be an object for the
    -- equality in `_buckets_for` to compare against anything a producer writes.
    BEGIN
        INSERT INTO plt01.ops_objectives
            (tenant_id, objective_key, kind, metric_key, comparison, threshold, window_hours,
             aggregate_as, dimensions, owner, runbook_ref, set_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'bad.dims', 'slo', 'ops.synthetic_success', 'at_least', 0.99, 24,
                'mean', '["check_key"]'::jsonb, 'platform-ops', 'RB', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: an objective''s dimensions were written as an array';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- The closed sets. A kind or a comparison outside them is a row the evaluator has no
    -- branch for, and `evaluate` would compare with whichever operator happened to be last.
    BEGIN
        INSERT INTO plt01.ops_objectives
            (tenant_id, objective_key, kind, metric_key, comparison, threshold, window_hours,
             aggregate_as, owner, runbook_ref, set_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'bad.kind', 'vibes', 'ops.synthetic_success', 'at_least', 0.99, 24,
                'mean', 'platform-ops', 'RB', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: an objective of an unknown kind was admitted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.ops_objectives
            (tenant_id, objective_key, kind, metric_key, comparison, threshold, window_hours,
             aggregate_as, owner, runbook_ref, set_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'bad.cmp', 'slo', 'ops.synthetic_success', 'roughly', 0.99, 24,
                'mean', 'platform-ops', 'RB', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: an objective comparison outside the set was admitted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- A window of a year is the ceiling; zero or negative is a window the aggregate divides by.
    BEGIN
        INSERT INTO plt01.ops_objectives
            (tenant_id, objective_key, kind, metric_key, comparison, threshold, window_hours,
             aggregate_as, owner, runbook_ref, set_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'bad.window', 'slo', 'ops.synthetic_success', 'at_least', 0.99, 0,
                'mean', 'platform-ops', 'RB', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: an objective with a zero window was admitted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- An unowned objective produces an alert addressed to nobody, which is the other half of
    -- the actionability control the runbook case already covers.
    BEGIN
        INSERT INTO plt01.ops_objectives
            (tenant_id, objective_key, kind, metric_key, comparison, threshold, window_hours,
             aggregate_as, owner, runbook_ref, set_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'bad.owner', 'slo', 'ops.synthetic_success', 'at_least', 0.99, 24,
                'mean', '  ', 'RB', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: an objective was defined with a blank owner';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A metric key that is not a dotted key is a series no reader will ever ask for by name.
    BEGIN
        INSERT INTO plt01.ops_metric_points
            (tenant_id, metric_key, bucket_start, dimensions, observations, total)
        VALUES ('11111111-1111-4111-8111-111111111111', 'Authz Denials', TIMESTAMPTZ '2026-11-14 13:00:00+00',
                '{"category": "access"}'::jsonb, 1, 1);
        RAISE EXCEPTION 'CHECK 48 FAILED: a point was written under a malformed metric key';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A probe result carries who submitted it. The row is insert-only and MOD-008 does not
    -- audit an allowed action, so this column is the only possible record -- which is why the
    -- module's own docstring names fabricated results as the risk it is guarding against.
    BEGIN
        INSERT INTO plt01.ops_synthetic_results
            (tenant_id, check_id, outcome, duration_ms, correlation_id, observed_at)
        VALUES ('11111111-1111-4111-8111-111111111111', '88888888-0000-4000-8000-000000000003', 'passed', 10, '33333333-3333-4333-8333-333333333333', now());
        RAISE EXCEPTION 'CHECK 48 FAILED: a probe result was recorded by nobody';
    EXCEPTION
        WHEN not_null_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.ops_synthetic_results
            (tenant_id, check_id, outcome, duration_ms, recorded_by, observed_at)
        VALUES ('11111111-1111-4111-8111-111111111111', '88888888-0000-4000-8000-000000000003', 'passed', 10, '33333333-3333-4333-8333-333333333333', now());
        RAISE EXCEPTION 'CHECK 48 FAILED: a probe result was recorded with no correlation id';
    EXCEPTION
        WHEN not_null_violation THEN NULL;
    END;
    -- An outcome outside the pair is a result the ratio metric cannot score.
    BEGIN
        INSERT INTO plt01.ops_synthetic_results
            (tenant_id, check_id, outcome, duration_ms, recorded_by, correlation_id,
             observed_at)
        VALUES ('11111111-1111-4111-8111-111111111111', '88888888-0000-4000-8000-000000000003', 'maybe', 10, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', now());
        RAISE EXCEPTION 'CHECK 48 FAILED: a probe outcome outside the pair was admitted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- A negative duration drags the latency mean below every real observation.
    BEGIN
        INSERT INTO plt01.ops_synthetic_results
            (tenant_id, check_id, outcome, duration_ms, recorded_by, correlation_id,
             observed_at)
        VALUES ('11111111-1111-4111-8111-111111111111', '88888888-0000-4000-8000-000000000003', 'passed', -1, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', now());
        RAISE EXCEPTION 'CHECK 48 FAILED: a negative probe duration was admitted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A second live check under one key means two registries disagreeing about what a probe is.
    BEGIN
        INSERT INTO plt01.ops_synthetic_checks
            (tenant_id, check_key, description, workflow, interval_seconds, registered_by,
             correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'login.probe', 'a second one', 'login', 60, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: a second check took the same key';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;
    -- A workflow the product does not have is a check nothing can ever run.
    BEGIN
        INSERT INTO plt01.ops_synthetic_checks
            (tenant_id, check_key, description, workflow, interval_seconds, registered_by,
             correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'tp.probe', 'teleports', 'teleport', 60, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: a check against an unknown workflow was admitted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- A one-second interval is a prober hammering the product it is measuring.
    BEGIN
        INSERT INTO plt01.ops_synthetic_checks
            (tenant_id, check_key, description, workflow, interval_seconds, registered_by,
             correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'fast.probe', 'too eager', 'login', 1, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: a one-second probe interval was admitted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- Disabling without saying who, the same control the objective case covers. Three tables
    -- carry this constraint and only one of them was tested.
    BEGIN
        UPDATE plt01.ops_synthetic_checks SET enabled = false, disabled_at = now()
        WHERE check_id = '88888888-0000-4000-8000-000000000003';
        RAISE EXCEPTION 'CHECK 48 FAILED: a check was disabled by nobody';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A forecast with no stated basis is a number somebody will treat as a measurement; the
    -- migration argues for exactly this constraint and nothing broke it.
    BEGIN
        INSERT INTO plt01.ops_capacity_forecasts
            (tenant_id, resource, horizon_days, current_value, projected_value, basis,
             forecast_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'cpu', 30, 1, 2, '   ', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: a forecast was recorded with no basis';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.ops_capacity_forecasts
            (tenant_id, resource, horizon_days, current_value, projected_value, basis,
             forecast_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'cpu', 30, 1, -5, 'negative capacity', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: a negative projection was admitted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.ops_capacity_forecasts
            (tenant_id, resource, horizon_days, current_value, projected_value, basis,
             forecast_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'cpu', 0, 1, 2, 'no horizon', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: a forecast with a zero horizon was admitted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.ops_capacity_forecasts
            (tenant_id, resource, horizon_days, current_value, projected_value, basis,
             forecast_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'CPU Cores', 30, 1, 2, 'malformed resource', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: a malformed resource name was admitted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- The headroom and the limit it was derived from travel together, or the row cannot say
    -- where its own number came from.
    BEGIN
        INSERT INTO plt01.ops_capacity_forecasts
            (tenant_id, resource, horizon_days, current_value, projected_value, headroom_bp,
             basis, forecast_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'cpu', 30, 1, 2, 5000, 'headroom from nowhere', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: a headroom was recorded with no limit behind it';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.ops_capacity_forecasts
            (tenant_id, resource, horizon_days, current_value, projected_value, limit_value,
             headroom_bp, basis, forecast_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'cpu', 30, 1, 2, 0, 0, 'a limit of nothing', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: a capacity limit of zero was admitted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.ops_capacity_forecasts
            (tenant_id, resource, horizon_days, current_value, projected_value, limit_value,
             headroom_bp, basis, forecast_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'cpu', 30, 1, 2, 100, 99999, 'impossible headroom', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: a headroom above the limit itself was admitted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A correction pointing at itself is a cycle any reader of the ledger walks.
    BEGIN
        INSERT INTO plt01.ops_cost_records
            (tenant_id, cost_record_id, period_start, period_end, dimension, dimension_value,
             currency, amount_minor, source, corrects_cost_record_id, allocated_by,
             correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '88888888-0000-4000-8000-0000000000aa', DATE '2026-11-01',
                DATE '2026-11-30', 'compute', 'api', 'EUR', -5, 'self correction',
                '88888888-0000-4000-8000-0000000000aa', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: a cost record corrected itself';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- A currency that is not three upper-case letters cannot be grouped against a budget.
    BEGIN
        INSERT INTO plt01.ops_cost_records
            (tenant_id, period_start, period_end, dimension, dimension_value, currency,
             amount_minor, source, allocated_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', DATE '2026-11-01', DATE '2026-11-30', 'compute', 'api', 'eur', 5,
                'vendor', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: a malformed currency was admitted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- A cost booked against a dimension no report knows about silently does not appear in the
    -- margin, which is the one direction a FinOps error is never noticed in.
    BEGIN
        INSERT INTO plt01.ops_cost_records
            (tenant_id, period_start, period_end, dimension, dimension_value, currency,
             amount_minor, source, allocated_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', DATE '2026-11-01', DATE '2026-11-30', 'vibes', 'api', 'EUR', 5,
                'vendor', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: a cost in an unknown dimension was admitted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.ops_cost_records
            (tenant_id, period_start, period_end, dimension, dimension_value, currency,
             amount_minor, source, allocated_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', DATE '2026-11-01', DATE '2026-11-30', 'compute', '  ', 'EUR', 5,
                'vendor', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: a cost named a blank dimension value';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A budget of zero or less divides the burn arithmetic; a warning point outside the range
    -- either never fires or fires immediately.
    BEGIN
        INSERT INTO plt01.ops_budgets
            (tenant_id, budget_key, dimension, dimension_value, currency, amount_minor,
             period, owner, set_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'zero.budget', 'compute', 'api', 'EUR', 0, 'monthly', 'ops', '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: a budget of zero was admitted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.ops_budgets
            (tenant_id, budget_key, dimension, dimension_value, currency, amount_minor,
             period, warn_at_bp, owner, set_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'loud.budget', 'compute', 'api', 'EUR', 100, 'monthly', 0, 'ops',
                '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: a warning point of zero basis points was admitted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- A period outside the three the burn window is derived from leaves the spend query with
    -- no upper bound to compute.
    BEGIN
        INSERT INTO plt01.ops_budgets
            (tenant_id, budget_key, dimension, dimension_value, currency, amount_minor,
             period, owner, set_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'odd.budget', 'compute', 'api', 'EUR', 100, 'fortnightly', 'ops',
                '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: a budget period outside the three was admitted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- Two live budgets under one key means the burn alert and the margin report answer the
    -- same question differently, and `retire_budget` moves whichever one it finds first.
    BEGIN
        INSERT INTO plt01.ops_budgets
            (tenant_id, budget_key, dimension, dimension_value, currency, amount_minor,
             period, owner, set_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'ai.monthly', 'ai_model', 'claude-opus', 'EUR', 1, 'monthly', 'ops',
                '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 48 FAILED: a second live budget took the same key';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;
    -- Retiring without saying who. The third of the three identical constraints, and the two
    -- untested ones were droppable in silence.
    BEGIN
        UPDATE plt01.ops_budgets SET retired_at = now() WHERE budget_id = '88888888-0000-4000-8000-000000000007';
        RAISE EXCEPTION 'CHECK 48 FAILED: a budget was retired by nobody';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- An alert is the record that somebody was told, so it carries a recipient and amounts
    -- that can be read back against the budget it snapshotted.
    BEGIN
        INSERT INTO plt01.ops_budget_alerts
            (tenant_id, budget_id, period_start, threshold_bp, spent_minor, budget_minor,
             currency, owner)
        VALUES ('11111111-1111-4111-8111-111111111111', '88888888-0000-4000-8000-000000000007', DATE '2026-12-01', 8000, 1, 0, 'EUR', 'ops');
        RAISE EXCEPTION 'CHECK 48 FAILED: an alert was raised against a budget of zero';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.ops_budget_alerts
            (tenant_id, budget_id, period_start, threshold_bp, spent_minor, budget_minor,
             currency, owner)
        VALUES ('11111111-1111-4111-8111-111111111111', '88888888-0000-4000-8000-000000000007', DATE '2026-12-01', 8000, 1, 2, 'EUR', '  ');
        RAISE EXCEPTION 'CHECK 48 FAILED: an alert was raised with no owner to receive it';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
END $$;
ROLLBACK;


-- ---------------------------------------------------------------- seed (tenant plane, MOD-012)
-- An install authorizes a third party to reach a tenant's data, so a leak here is not a read of
-- another tenant's row -- it is one tenant able to see, and in the worst case to widen, which
-- provider accounts another tenant is connected to and with which scopes.
BEGIN;
SET LOCAL ROLE veyro_cp_platform;
-- Registered as a draft and published afterwards, which is the only order the catalogue
-- admits: `int_definition_versions_draft_only` refuses a write once the parent is published,
-- so a seed that published first could not declare its own scopes.
INSERT INTO plt01_platform.int_definitions
    (definition_key, version, provider, display_name, criticality, support_owner, description)
VALUES ('acme.payments', 1, 'Acme', 'Acme Payments', 'critical', 'platform-ops',
        'Takes card payments');
INSERT INTO plt01_platform.int_definition_versions
    (definition_key, version, kind, name, required, field_type, enum_values)
VALUES ('acme.payments', 1, 'capability', 'payments', false, NULL, NULL),
       ('acme.payments', 1, 'scope', 'payments.charge', true, NULL, NULL),
       ('acme.payments', 1, 'scope', 'payments.refund', false, NULL, NULL),
       ('acme.payments', 1, 'region', 'eu-west', false, NULL, NULL),
       ('acme.payments', 1, 'config', 'merchant_id', true, 'reference', NULL);
UPDATE plt01_platform.int_definitions SET status = 'published', published_at = now()
WHERE definition_key = 'acme.payments' AND version = 1;
COMMIT;

BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
INSERT INTO plt01.int_installs
    (tenant_id, install_id, definition_key, definition_version, definition_snapshot,
     criticality, config, state, fallback_plan, reconciliation_plan, exit_plan, installed_by,
     correlation_id)
VALUES (:'tenant_a', '99999999-1000-4000-8000-000000000001', 'acme.payments', 1,
        '{"definition_key": "acme.payments", "version": 1}'::jsonb, 'critical',
        '{"merchant_id": "m-1"}'::jsonb, 'active', 'manual terminal', 'daily settlement file',
        'export and switch provider', :'actor', :'actor');
INSERT INTO plt01.int_connections
    (tenant_id, connection_id, install_id, external_account_ref, region, granted_scopes,
     state, authorized_at, authorized_by, validated_at, validated_by, validation_evidence,
     correlation_id)
VALUES (:'tenant_a', '99999999-1000-4000-8000-000000000002',
        '99999999-1000-4000-8000-000000000001', 'acct_live_1', 'eu-west',
        ARRAY['payments.charge'], 'validated', now(), :'actor', now(), :'actor',
        'test charge accepted', :'actor');
INSERT INTO plt01.int_credential_refs
    (tenant_id, credential_ref_id, connection_id, vault_ref, scopes, issued_at, expires_at,
     recorded_by, correlation_id)
VALUES (:'tenant_a', '99999999-1000-4000-8000-000000000003',
        '99999999-1000-4000-8000-000000000002', 'vault://acme/live-1',
        ARRAY['payments.charge'], now(), now() + INTERVAL '90 days', :'actor', :'actor');
INSERT INTO plt01.int_sync_cursors
    (tenant_id, cursor_id, connection_id, resource, position, observed_at)
VALUES (:'tenant_a', '99999999-1000-4000-8000-000000000004',
        '99999999-1000-4000-8000-000000000002', 'settlements', 'cur-1', now());
INSERT INTO plt01.int_connector_runs
    (tenant_id, run_id, connection_id, resource, status, started_by, correlation_id)
VALUES (:'tenant_a', '99999999-1000-4000-8000-000000000005',
        '99999999-1000-4000-8000-000000000002', 'settlements', 'running', :'actor', :'actor');
COMMIT;

-- Tenant B holds one install of its own, so a leaked predicate shows up as a count above the
-- expected one rather than as the zero an empty table would give anyway.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
INSERT INTO plt01.int_installs
    (tenant_id, definition_key, definition_version, definition_snapshot, criticality, config,
     installed_by, correlation_id)
VALUES (:'tenant_b', 'acme.payments', 1,
        '{"definition_key": "acme.payments", "version": 1}'::jsonb, 'critical',
        '{"merchant_id": "m-2"}'::jsonb, :'actor', :'actor');
COMMIT;

-- ---------------------------------------------------------------- 49. int tables isolate
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['int_connections', 'int_credential_refs', 'int_sync_cursors',
                               'int_connector_runs']
    LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 49 FAILED: tenant B sees % rows of tenant A in %', seen, tbl;
        END IF;
    END LOOP;
    IF (SELECT count(*) FROM plt01.int_installs) <> 1 THEN
        RAISE EXCEPTION 'CHECK 49 FAILED: tenant B sees % installs, expected its own 1',
            (SELECT count(*) FROM plt01.int_installs);
    END IF;
    IF EXISTS (SELECT 1 FROM plt01.int_installs WHERE config ->> 'merchant_id' = 'm-1') THEN
        RAISE EXCEPTION 'CHECK 49 FAILED: tenant B read tenant A''s merchant configuration';
    END IF;
END $$;
COMMIT;

BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    IF (SELECT count(*) FROM plt01.int_installs) <> 1
       OR (SELECT count(*) FROM plt01.int_connections) <> 1
       OR (SELECT count(*) FROM plt01.int_credential_refs) <> 1
       OR (SELECT count(*) FROM plt01.int_sync_cursors) <> 1
       OR (SELECT count(*) FROM plt01.int_connector_runs) <> 1 THEN
        RAISE EXCEPTION 'CHECK 49 FAILED: tenant A cannot see its own integration rows';
    END IF;
END $$;
COMMIT;

-- The catalogue sweep, with both halves of the policy, the owner check, the count guard, the
-- one-permissive-policy rule and the tenant-leading primary key -- the full set checks 44 ended
-- up with after MOD-011's review, written in from the start here rather than added afterwards.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
DECLARE
    bad text;
BEGIN
    SELECT string_agg(relname, ', ') INTO bad
    FROM pg_class
    WHERE relnamespace = 'plt01'::regnamespace AND relkind IN ('r', 'p') AND relname LIKE 'int\_%'
      AND NOT (relrowsecurity AND relforcerowsecurity);
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 49 FAILED: int_ tables without ENABLE and FORCE RLS: %', bad;
    END IF;
    IF (SELECT count(*) FROM pg_class
        WHERE relnamespace = 'plt01'::regnamespace AND relkind IN ('r', 'p')
          AND relname LIKE 'int\_%') < 5 THEN
        RAISE EXCEPTION 'CHECK 49 FAILED: fewer than 5 int_ tables, so the sweep proved nothing';
    END IF;
    IF (SELECT count(*) FROM pg_class
        WHERE relnamespace = 'plt01'::regnamespace AND relkind IN ('r', 'p') AND relname LIKE 'int\_%'
          AND pg_get_userbyid(relowner) <> 'veyro_cp_migrator') <> 0 THEN
        RAISE EXCEPTION 'CHECK 49 FAILED: an int_ table is not owned by the migrator';
    END IF;
    SELECT string_agg(c.relname, ', ') INTO bad
    FROM pg_class c
    LEFT JOIN pg_policies p
      ON p.schemaname = 'plt01' AND p.tablename = c.relname
     AND p.qual = '(tenant_id = (NULLIF(current_setting(''app.tenant_id''::text, true), ''''::text))::uuid)'
     AND p.with_check = p.qual
    WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
      AND c.relname LIKE 'int\_%' AND p.policyname IS NULL;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 49 FAILED: int_ tables without the exact tenant predicate in '
            'both USING and WITH CHECK: %', bad;
    END IF;
    SELECT string_agg(c.relname || ' (' || n::text || ')', ', ') INTO bad
    FROM pg_class c
    CROSS JOIN LATERAL (
        SELECT count(*) AS n FROM pg_policies p
        WHERE p.schemaname = 'plt01' AND p.tablename = c.relname AND p.permissive = 'PERMISSIVE'
    ) counted
    WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
      AND c.relname LIKE 'int\_%' AND counted.n <> 1;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 49 FAILED: int_ tables without exactly one permissive policy: %',
            bad;
    END IF;
    SELECT string_agg(c.relname, ', ') INTO bad
    FROM pg_class c
    JOIN pg_index i ON i.indrelid = c.oid AND i.indisprimary
    WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
      AND c.relname LIKE 'int\_%'
      AND (SELECT attname FROM pg_attribute
           WHERE attrelid = c.oid AND attnum = i.indkey[0]) <> 'tenant_id';
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 49 FAILED: int_ tables whose primary key does not lead with '
            'tenant_id: %', bad;
    END IF;
END $$;
COMMIT;

-- The owner, and then the worker. Both seats, because a role nobody sits as is a role nothing
-- is proved about -- the lesson MOD-010 learned for `evt_` and MOD-011 inherited by scoping the
-- fix to one module's prefix.
BEGIN;
SET LOCAL ROLE veyro_cp_migrator;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['int_installs', 'int_connections', 'int_credential_refs',
                               'int_sync_cursors', 'int_connector_runs']
    LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 49 FAILED: the table owner read % rows of %, so FORCE RLS is off',
                seen, tbl;
        END IF;
    END LOOP;
END $$;
COMMIT;

BEGIN;
SET LOCAL ROLE veyro_cp_worker;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['int_connections', 'int_credential_refs', 'int_sync_cursors',
                               'int_connector_runs']
    LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 49 FAILED: the worker read % rows of tenant A in % from '
                'tenant B''s context', seen, tbl;
        END IF;
    END LOOP;
    IF (SELECT count(*) FROM plt01.int_installs) <> 1 THEN
        RAISE EXCEPTION 'CHECK 49 FAILED: the worker sees % installs in tenant B, expected 1',
            (SELECT count(*) FROM plt01.int_installs);
    END IF;
END $$;
COMMIT;

BEGIN;
SET LOCAL ROLE veyro_cp_worker;
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['int_installs', 'int_connections', 'int_credential_refs',
                               'int_sync_cursors', 'int_connector_runs']
    LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 49 FAILED: the worker read % rows of % with no tenant context',
                seen, tbl;
        END IF;
    END LOOP;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 50. fail closed, int tables
BEGIN;
SET LOCAL ROLE veyro_cp_app;
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['int_installs', 'int_connections', 'int_credential_refs',
                               'int_sync_cursors', 'int_connector_runs']
    LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 50 FAILED: % returned % rows with no tenant context',
                tbl, seen;
        END IF;
    END LOOP;
    -- A connection written with no context is a third party authorized against nobody, which
    -- would read as authorized for whichever tenant's query found it.
    BEGIN
        INSERT INTO plt01.int_connections
            (tenant_id, install_id, external_account_ref, region, granted_scopes,
             correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111',
                '99999999-1000-4000-8000-000000000001', 'acct_x', 'eu-west',
                ARRAY['payments.charge'], '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 50 FAILED: a connection was authorized with no tenant context';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.int_credential_refs
            (tenant_id, connection_id, vault_ref, scopes, issued_at, recorded_by,
             correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111',
                '99999999-1000-4000-8000-000000000002', 'vault://x',
                ARRAY['payments.charge'], now(), '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 50 FAILED: a credential reference was written with no context';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    BEGIN
        INSERT INTO plt01.int_installs
            (tenant_id, definition_key, definition_version, definition_snapshot, criticality,
             installed_by, correlation_id)
        VALUES ('22222222-2222-4222-8222-222222222222', 'acme.payments', 1, '{}'::jsonb,
                'convenience', '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 50 FAILED: an install was written into another tenant';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;


-- ---------------------------------------------------------------- 51. cross-tenant parents
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
BEGIN
    BEGIN
        INSERT INTO plt01.int_connections
            (tenant_id, install_id, external_account_ref, region, granted_scopes,
             correlation_id)
        VALUES ('22222222-2222-4222-8222-222222222222',
                '99999999-1000-4000-8000-000000000001', 'acct_borrowed', 'eu-west',
                ARRAY['payments.charge'], '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 51 FAILED: a connection was hung off another tenant''s install';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.int_credential_refs
            (tenant_id, connection_id, vault_ref, scopes, issued_at, recorded_by,
             correlation_id)
        VALUES ('22222222-2222-4222-8222-222222222222',
                '99999999-1000-4000-8000-000000000002', 'vault://borrowed',
                ARRAY['payments.charge'], now(), '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 51 FAILED: a credential was attached to another tenant''s '
            'connection';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.int_connector_runs
            (tenant_id, connection_id, resource, started_by, correlation_id)
        VALUES ('22222222-2222-4222-8222-222222222222',
                '99999999-1000-4000-8000-000000000002', 'settlements',
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 51 FAILED: a run was started on another tenant''s connection';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.int_sync_cursors
            (tenant_id, connection_id, resource, position, observed_at)
        VALUES ('22222222-2222-4222-8222-222222222222',
                '99999999-1000-4000-8000-000000000002', 'settlements', 'cur-x', now());
        RAISE EXCEPTION 'CHECK 51 FAILED: a cursor was set on another tenant''s connection';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
END $$;
ROLLBACK;

-- The registry reference, swept from the catalogue and sampled behaviourally -- the shape
-- check 46 ended up with after a reviewer dropped seven of eight foreign keys in silence.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
DECLARE
    missing text;
BEGIN
    SELECT string_agg(c.relname, ', ') INTO missing
    FROM pg_class c
    WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
      AND c.relname LIKE 'int\_%'
      AND NOT EXISTS (
          SELECT 1 FROM pg_constraint fk
          WHERE fk.conrelid = c.oid AND fk.contype = 'f'
            AND fk.confrelid = 'plt01_platform.tenants'::regclass
            AND fk.conkey = ARRAY[(SELECT attnum FROM pg_attribute
                                   WHERE attrelid = c.oid AND attname = 'tenant_id')]);
    IF missing IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 51 FAILED: int_ tables with no tenant registry foreign key: %',
            missing;
    END IF;

    -- **And every other parent reference, compared in full against the catalogue.** The first
    -- version swept the registry reference and *sampled* four intra-module parents
    -- behaviourally, which left two droppable in silence: the rotation chain's self-reference,
    -- which is the only thing keeping a credential's predecessor inside its own tenant, and
    -- the entries table's reference to the definition it belongs to, without which scopes can
    -- be written for a version nobody registered. That is MOD-011's shape one level in -- one
    -- case written and the rest asserted -- so this compares the set rather than listing the
    -- ones somebody remembered.
    WITH live AS (
        SELECT c.conrelid::regclass::text || ': '
               || (SELECT string_agg(a.attname, ',' ORDER BY k.ord)
                   FROM unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord)
                   JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum)
               || ' -> ' || c.confrelid::regclass::text AS fk
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.contype = 'f' AND t.relname LIKE 'int\_%'
          AND t.relnamespace IN ('plt01'::regnamespace, 'plt01_platform'::regnamespace)
    ), expected(fk) AS (VALUES
        ('plt01.int_installs: tenant_id -> plt01_platform.tenants'),
        ('plt01.int_connections: tenant_id -> plt01_platform.tenants'),
        ('plt01.int_connections: tenant_id,install_id -> plt01.int_installs'),
        ('plt01.int_credential_refs: tenant_id -> plt01_platform.tenants'),
        ('plt01.int_credential_refs: tenant_id,connection_id -> plt01.int_connections'),
        ('plt01.int_credential_refs: tenant_id,supersedes_credential_ref_id -> plt01.int_credential_refs'),
        ('plt01.int_sync_cursors: tenant_id -> plt01_platform.tenants'),
        ('plt01.int_sync_cursors: tenant_id,connection_id -> plt01.int_connections'),
        ('plt01.int_connector_runs: tenant_id -> plt01_platform.tenants'),
        ('plt01.int_connector_runs: tenant_id,connection_id -> plt01.int_connections'),
        ('plt01_platform.int_definition_versions: definition_key,version -> plt01_platform.int_definitions'))
    SELECT string_agg(fk, '; ') INTO missing FROM (
        (SELECT fk FROM expected EXCEPT SELECT fk FROM live)
        UNION ALL
        (SELECT fk FROM live EXCEPT SELECT fk FROM expected)
    ) differences;
    IF missing IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 51 FAILED: foreign keys differ from the expected set: %',
            missing;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.contype = 'f' AND t.relname = 'int_definition_versions'
          AND c.confrelid = 'plt01_platform.int_definitions'::regclass) THEN
        RAISE EXCEPTION 'CHECK 51 FAILED: a definition version''s entries may belong to a '
            'definition nobody registered';
    END IF;
END $$;
COMMIT;

-- Behaviourally, for the two the first version did not reach.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
BEGIN
    BEGIN
        INSERT INTO plt01.int_credential_refs
            (tenant_id, connection_id, vault_ref, scopes, issued_at,
             supersedes_credential_ref_id, recorded_by, correlation_id)
        VALUES ('22222222-2222-4222-8222-222222222222',
                '99999999-1000-4000-8000-000000000002', 'vault://x',
                ARRAY['payments.charge'], now(), '99999999-1000-4000-8000-000000000003',
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 51 FAILED: a rotation chain reached into another tenant';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
END $$;
ROLLBACK;

BEGIN;
SET LOCAL ROLE veyro_cp_platform;
DO $$
BEGIN
    BEGIN
        INSERT INTO plt01_platform.int_definition_versions
            (definition_key, version, kind, name)
        VALUES ('acme.never_registered', 7, 'scope', 'payments.charge');
        RAISE EXCEPTION 'CHECK 51 FAILED: scopes were declared for a version nobody registered';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
END $$;
ROLLBACK;

BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '44444444-4444-4444-8444-444444444444';
DO $$
BEGIN
    BEGIN
        INSERT INTO plt01.int_installs
            (tenant_id, definition_key, definition_version, definition_snapshot, criticality,
             installed_by, correlation_id)
        VALUES ('44444444-4444-4444-8444-444444444444', 'acme.payments', 1, '{}'::jsonb,
                'convenience', '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 51 FAILED: an install was made for an unregistered tenant';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
END $$;
ROLLBACK;

-- ------------------------------------------------- 52. a credential reference holds no secret
-- **The control in this module is the absence of a column**, and an absence is exactly what a
-- later migration adds back without anybody noticing. There is no vault in this repository, so
-- `int_credential_refs` names where a secret lives and holds metadata about it; a column that
-- could carry the value itself would turn every list route into one that returns credentials.
--
-- The column list is compared in full rather than checked for a denylist of suspicious names,
-- because a denylist is what MOD-010's review showed a hand-written list of names is worth:
-- `token`, `secret` and `api_key` are the names somebody would not use.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
DECLARE
    wrong text;
BEGIN
    -- **Every table's column list, not just the one the control is named after.** The first
    -- version pinned `int_credential_refs` alone, which is where the "no column a secret could
    -- go in" claim lives -- and a reviewer then added `access_token` to `int_connections`,
    -- `api_key` to `int_installs` and `shared_secret` to `int_definitions`, each leaving the
    -- suite at 54/54. The header's own reasoning is that an absence is what a later migration
    -- adds back without anybody noticing, and the next migration's secret will not be on the
    -- table that happens to be pinned.
    WITH expected(tbl, cols) AS (VALUES
        ('plt01.int_connections',
             'authorized_at,authorized_by,connection_id,correlation_id,created_at,external_account_ref,granted_scopes,install_id,region,revoke_reason,revoked_at,revoked_by,state,tenant_id,validated_at,validated_by,validation_evidence'),
        ('plt01.int_connector_runs',
             'attempts,claimed_until,conflicts,connection_id,correlation_id,finished_at,last_error,max_attempts,next_attempt_at,reconcile_correlation_id,reconciled_at,reconciled_by,reconciled_local,reconciled_matched,reconciled_provider,records_read,records_written,release_correlation_id,release_reason,released_at,released_by,resource,run_id,settle_correlation_id,settled_by,started_at,started_by,status,tenant_id'),
        ('plt01.int_credential_refs',
             'connection_id,correlation_id,credential_ref_id,expires_at,issued_at,recorded_at,recorded_by,retired_at,scopes,supersedes_credential_ref_id,tenant_id,vault_ref'),
        ('plt01.int_installs',
             'activated_at,config,correlation_id,criticality,definition_key,definition_snapshot,definition_version,disabled_at,exit_plan,fallback_plan,install_id,installed_at,installed_by,reconciliation_plan,state,tenant_id,uninstall_correlation_id,uninstall_reason,uninstalled_at,uninstalled_by'),
        ('plt01.int_sync_cursors',
             'conflict_policy,connection_id,cursor_id,observed_at,position,reset_at,reset_by,reset_reason,resource,tenant_id,updated_at'),
        ('plt01_platform.int_definition_versions',
             'definition_key,description,entry_id,enum_values,field_type,kind,name,required,version'),
        ('plt01_platform.int_definitions',
             'created_at,criticality,definition_key,description,display_name,provider,published_at,retired_at,status,support_owner,version'))
    SELECT string_agg(e.tbl || ': ' || coalesce(a.actual, '(none)'), '; ') INTO wrong
    FROM expected e
    LEFT JOIN LATERAL (
        SELECT string_agg(att.attname, ',' ORDER BY att.attname) AS actual
        FROM pg_attribute att
        WHERE att.attrelid = e.tbl::regclass AND att.attnum > 0 AND NOT att.attisdropped
    ) a ON true
    WHERE coalesce(a.actual, '(none)') <> e.cols;
    IF wrong IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 52 FAILED: int_ columns are not the expected set, so a secret '
            'may now have somewhere to live: %', wrong;
    END IF;
END $$;
COMMIT;

-- And the same for the definition catalogue's field types: there is no `secret` type, so a
-- definition cannot ask a tenant to paste a credential into a configuration value either. On
-- the platform seat, because the tenant-facing role cannot read that schema at all -- which
-- check 53 asserts in its own right.
BEGIN;
SET LOCAL ROLE veyro_cp_platform;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM plt01_platform.int_definition_versions
        WHERE field_type IS NOT NULL
          AND field_type NOT IN ('string', 'integer', 'boolean', 'reference', 'enum')) THEN
        RAISE EXCEPTION 'CHECK 52 FAILED: a definition declares a configuration field type '
            'outside the closed set';
    END IF;
    -- On a *draft* parent, because a published one is refused by the trigger before the field
    -- type is ever looked at -- and a case that passes because a different control fired is
    -- the vacuity this suite has now been bitten by twice.
    INSERT INTO plt01_platform.int_definitions
        (definition_key, version, provider, display_name, criticality, support_owner,
         description)
    VALUES ('acme.draft', 1, 'Acme', 'Draft', 'convenience', 'ops', 'd');
    BEGIN
        INSERT INTO plt01_platform.int_definition_versions
            (definition_key, version, kind, name, field_type)
        VALUES ('acme.draft', 1, 'config', 'api_key', 'secret');
        RAISE EXCEPTION 'CHECK 52 FAILED: a definition declared a secret configuration field, '
            'which is a credential in a column every list route reads';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 53. integration privileges
-- Two things this module needs the privilege layer for, both of which are the whole mechanism
-- behind a sentence somebody will later rely on.
--
--   * **`granted_scopes` carries no UPDATE.** Widening what a third party may reach is a new
--     authorization with its own decision, not an edit to the old row -- which is the only way
--     "what did this connection hold on the fourteenth" stays answerable.
--   * **A credential reference is written once and retired.** The vault reference, the scopes
--     and the expiry are what a breach review reads, and a rotation is a new row.
--
-- Swept per column and per role against the catalogue, with the table list required to cover
-- every `int_` table, because a hand-written list of either is what the last two reviews broke.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
DECLARE
    wrong text;
BEGIN
    WITH expected(tbl, cols) AS (VALUES
        ('int_installs',
         'activated_at,config,disabled_at,exit_plan,fallback_plan,reconciliation_plan,state,'
         'uninstall_correlation_id,uninstall_reason,uninstalled_at,uninstalled_by'),
        ('int_connections',
         'authorized_at,authorized_by,revoke_reason,revoked_at,revoked_by,state,'
         'validated_at,validated_by,validation_evidence'),
        ('int_credential_refs', 'retired_at'),
        ('int_sync_cursors',
         'conflict_policy,observed_at,position,reset_at,reset_by,reset_reason,updated_at'),
        ('int_connector_runs',
         'attempts,claimed_until,conflicts,finished_at,last_error,next_attempt_at,'
         'reconcile_correlation_id,reconciled_at,reconciled_by,reconciled_local,'
         'reconciled_matched,reconciled_provider,records_read,records_written,'
         'release_correlation_id,release_reason,released_at,released_by,'
         'settle_correlation_id,settled_by,status'))
    SELECT string_agg(
               e.tbl || ' / ' || g.grantee || ': ' || coalesce(a.actual, '(none)'), '; ')
    INTO wrong
    FROM expected e
    CROSS JOIN (VALUES ('veyro_cp_app'), ('veyro_cp_worker')) AS g(grantee)
    LEFT JOIN LATERAL (
        SELECT string_agg(att.attname, ',' ORDER BY att.attname) AS actual
        FROM pg_attribute att
        WHERE att.attrelid = ('plt01.' || e.tbl)::regclass
          AND att.attnum > 0 AND NOT att.attisdropped
          AND has_column_privilege(g.grantee, att.attrelid, att.attname, 'UPDATE')
    ) a ON true
    WHERE coalesce(a.actual, '(none)') <> e.cols;
    IF wrong IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 53 FAILED: UPDATE column grants differ from the expected set: %',
            wrong;
    END IF;

    SELECT string_agg(c.relname, ', ') INTO wrong
    FROM pg_class c
    WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
      AND c.relname LIKE 'int\_%'
      AND c.relname NOT IN ('int_installs', 'int_connections', 'int_credential_refs',
                            'int_sync_cursors', 'int_connector_runs');
    IF wrong IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 53 FAILED: int_ tables with no stated UPDATE expectation: %',
            wrong;
    END IF;

    IF (SELECT count(*) FROM pg_class c, aclexplode(c.relacl) acl
        WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
          AND c.relname LIKE 'int\_%'
          AND pg_get_userbyid(acl.grantee) IN ('veyro_cp_app', 'veyro_cp_worker')
          AND acl.privilege_type IN ('DELETE', 'TRUNCATE', 'REFERENCES')) <> 0 THEN
        RAISE EXCEPTION 'CHECK 53 FAILED: a runtime role holds DELETE, TRUNCATE or REFERENCES';
    END IF;
    IF (SELECT count(*) FROM pg_class c, aclexplode(c.relacl) acl
        WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
          AND c.relname LIKE 'int\_%' AND acl.grantee <> 0
          AND pg_get_userbyid(acl.grantee)
              NOT IN ('veyro_cp_app', 'veyro_cp_worker', 'veyro_cp_migrator')) <> 0 THEN
        RAISE EXCEPTION 'CHECK 53 FAILED: an int_ table is granted to somebody unexpected';
    END IF;
    IF (SELECT count(*) FROM pg_class c, aclexplode(c.relacl) acl
        WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
          AND c.relname LIKE 'int\_%' AND acl.grantee = 0) <> 0 THEN
        RAISE EXCEPTION 'CHECK 53 FAILED: an int_ table carries a PUBLIC grant';
    END IF;
    IF (SELECT count(*) FROM pg_class c
        JOIN pg_attribute att ON att.attrelid = c.oid AND att.attnum > 0
                             AND NOT att.attisdropped AND att.attacl IS NOT NULL,
        LATERAL aclexplode(att.attacl) acl
        WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
          AND c.relname LIKE 'int\_%'
          AND (acl.grantee = 0
               OR acl.privilege_type IN ('DELETE', 'TRUNCATE', 'REFERENCES')
               OR pg_get_userbyid(acl.grantee)
                  NOT IN ('veyro_cp_app', 'veyro_cp_worker', 'veyro_cp_migrator'))) <> 0 THEN
        RAISE EXCEPTION 'CHECK 53 FAILED: a column-level grant is PUBLIC, is REFERENCES, or '
            'names a role outside the three expected ones';
    END IF;

    -- Behaviourally, because a catalogue row is a claim about behaviour. Each of these is the
    -- rewrite somebody with a motive would reach for.
    BEGIN
        UPDATE plt01.int_connections SET granted_scopes = ARRAY['payments.charge',
                                                                'payments.refund'];
        RAISE EXCEPTION 'CHECK 53 FAILED: a connection''s granted scopes were widened in place';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        UPDATE plt01.int_credential_refs SET vault_ref = 'vault://somewhere-else';
        RAISE EXCEPTION 'CHECK 53 FAILED: a credential reference was repointed';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        UPDATE plt01.int_credential_refs SET scopes = ARRAY['payments.refund'];
        RAISE EXCEPTION 'CHECK 53 FAILED: a credential reference''s scopes were rewritten';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        UPDATE plt01.int_credential_refs SET expires_at = now() + INTERVAL '10 years';
        RAISE EXCEPTION 'CHECK 53 FAILED: a credential reference''s expiry was extended';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        UPDATE plt01.int_installs SET definition_snapshot = '{"version": 99}'::jsonb;
        RAISE EXCEPTION 'CHECK 53 FAILED: an install''s definition snapshot was rewritten';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        UPDATE plt01.int_connector_runs SET connection_id = gen_random_uuid();
        RAISE EXCEPTION 'CHECK 53 FAILED: a run was moved to another connection';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        DELETE FROM plt01.int_connections;
        RAISE EXCEPTION 'CHECK 53 FAILED: a connection was deleted rather than revoked';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

-- The platform-plane catalogue is unreachable from either runtime role, in both directions:
-- no grant on the tables and no USAGE on the schema. The plan catalogue gets the same check,
-- and this one matters for a reason that one does not have -- a definition declares the scopes
-- an install may grant a third party, so a tenant-facing role able to write one would be a
-- tenant-facing role that chooses what it is allowed to hand out.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    IF (SELECT count(*) FROM pg_class c, aclexplode(c.relacl) acl
        WHERE c.relnamespace = 'plt01_platform'::regnamespace AND c.relkind IN ('r', 'p')
          AND c.relname LIKE 'int\_%'
          AND pg_get_userbyid(acl.grantee) IN ('veyro_cp_app', 'veyro_cp_worker')) <> 0 THEN
        RAISE EXCEPTION 'CHECK 53 FAILED: a runtime role is granted the definition catalogue';
    END IF;
    -- Not USAGE on the schema: both runtime roles hold that deliberately, because the D6.3
    -- allowlist functions live there and EXECUTE needs it. `0001_roles_and_schemas.sql` says
    -- so: "object privileges are granted per table by the migration that creates it, so a new
    -- table is unreachable until its own migration says who may read it." The property is
    -- therefore the absence of a *table* privilege, which the assertion above covers and this
    -- one proves by attempting the read.
    IF has_table_privilege('veyro_cp_app', 'plt01_platform.int_definitions', 'SELECT')
       OR has_table_privilege('veyro_cp_worker', 'plt01_platform.int_definitions', 'SELECT')
       OR has_table_privilege('veyro_cp_app', 'plt01_platform.int_definition_versions',
                              'SELECT') THEN
        RAISE EXCEPTION 'CHECK 53 FAILED: a runtime role may select the definition catalogue';
    END IF;
    BEGIN
        PERFORM count(*) FROM plt01_platform.int_definitions;
        RAISE EXCEPTION 'CHECK 53 FAILED: the app role read the definition catalogue';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

-- A published definition version is immutable, which is what makes an install answerable: the
-- scopes on the version are the permissions a third party was granted, and a version that
-- could be edited afterwards means nobody can say what an install actually authorized.
BEGIN;
SET LOCAL ROLE veyro_cp_platform;
DO $$
DECLARE
    actual text;
BEGIN
    SELECT coalesce(string_agg(att.attname, ',' ORDER BY att.attname), '(none)') INTO actual
    FROM pg_attribute att
    WHERE att.attrelid = 'plt01_platform.int_definitions'::regclass
      AND att.attnum > 0 AND NOT att.attisdropped
      AND has_column_privilege('veyro_cp_platform', att.attrelid, att.attname, 'UPDATE');
    IF actual <> 'published_at,retired_at,status' THEN
        RAISE EXCEPTION 'CHECK 53 FAILED: the platform role may update % on int_definitions',
            actual;
    END IF;
    SELECT coalesce(string_agg(att.attname, ',' ORDER BY att.attname), '(none)') INTO actual
    FROM pg_attribute att
    WHERE att.attrelid = 'plt01_platform.int_definition_versions'::regclass
      AND att.attnum > 0 AND NOT att.attisdropped
      AND has_column_privilege('veyro_cp_platform', att.attrelid, att.attname, 'UPDATE');
    IF actual <> '(none)' THEN
        RAISE EXCEPTION 'CHECK 53 FAILED: a definition version''s entries are editable: %',
            actual;
    END IF;
    BEGIN
        UPDATE plt01_platform.int_definition_versions SET required = false
        WHERE definition_key = 'acme.payments';
        RAISE EXCEPTION 'CHECK 53 FAILED: a published version''s scopes were edited';
    EXCEPTION
        WHEN insufficient_privilege OR restrict_violation THEN NULL;
    END;
    -- **The INSERT, which the grant cannot see.** `GRANT SELECT, INSERT` plus a unique index
    -- stops re-declaring a name that already exists and stops nothing else, so a published
    -- version's scope set was additive-mutable -- and a *required* scope could be added to it.
    -- Installs keep their snapshot, so the blast radius is new installs against "version 1"
    -- authorizing a wider scope set than the one that was published and reviewed, which is the
    -- control paragraph 3032 names. Found by review; the header rested it on "the wrong
    -- UPDATE" and the wrong INSERT was unguarded.
    BEGIN
        INSERT INTO plt01_platform.int_definition_versions
            (definition_key, version, kind, name, required)
        VALUES ('acme.payments', 1, 'scope', 'members.read_all', true);
        RAISE EXCEPTION 'CHECK 53 FAILED: a scope was added to a published definition version';
    EXCEPTION
        WHEN restrict_violation THEN NULL;
    END;
    BEGIN
        DELETE FROM plt01_platform.int_definition_versions
        WHERE definition_key = 'acme.payments' AND kind = 'scope';
        RAISE EXCEPTION 'CHECK 53 FAILED: a published version''s scopes were deleted';
    EXCEPTION
        WHEN insufficient_privilege OR restrict_violation THEN NULL;
    END;
    -- A publication date answers "when did installs against this version become possible", and
    -- a retirement that can be undone is not one. A CHECK sees only the new row, so this needs
    -- the trigger -- MOD-009's rule about `OLD`, one module later.
    BEGIN
        UPDATE plt01_platform.int_definitions SET published_at = now() - INTERVAL '1 year'
        WHERE definition_key = 'acme.payments' AND version = 1;
        RAISE EXCEPTION 'CHECK 53 FAILED: a publication date was moved';
    EXCEPTION
        WHEN restrict_violation THEN NULL;
    END;
    BEGIN
        UPDATE plt01_platform.int_definitions SET status = 'retired', retired_at = now()
        WHERE definition_key = 'acme.payments' AND version = 1;
        UPDATE plt01_platform.int_definitions SET status = 'published', retired_at = NULL
        WHERE definition_key = 'acme.payments' AND version = 1;
        RAISE EXCEPTION 'CHECK 53 FAILED: a retired definition was un-retired';
    EXCEPTION
        WHEN restrict_violation THEN NULL;
    END;
    BEGIN
        DELETE FROM plt01_platform.int_definitions WHERE definition_key = 'acme.payments';
        RAISE EXCEPTION 'CHECK 53 FAILED: a published definition was deleted';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;


-- ---------------------------------------------------------------- 54. the int_ constraints
-- Every CHECK constraint and every unique index on this module's tables, on both planes. Not a
-- sample: the rule in `.claude/rules/backend/mod004-rls.md` is that a constraint nobody has
-- broken on purpose is a constraint nobody has tested, and that it has to mean the table rather
-- than the ones somebody thought to write down. MOD-011's check 48 proved fifteen of its
-- module's constraints and said in its own preamble that it proved them all; a reviewer dropped
-- 24 of the rest in silence. This one is written from the catalogue of constraints that exist.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    -- A definition key that is not a key names a catalogue entry nothing can resolve.
    BEGIN
        INSERT INTO plt01.int_installs
            (tenant_id, definition_key, definition_version, definition_snapshot,
             criticality, config, state, installed_by, correlation_id,
             uninstalled_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'Acme Payments', 1, '{}'::jsonb, 'convenience', '{}'::jsonb, 'installed', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: a malformed definition key was installed';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- Version zero is not a version anybody published.
    BEGIN
        INSERT INTO plt01.int_installs
            (tenant_id, definition_key, definition_version, definition_snapshot,
             criticality, config, state, installed_by, correlation_id,
             uninstalled_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'other.thing', 0, '{}'::jsonb, 'convenience', '{}'::jsonb, 'installed', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: an install named version zero';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- The snapshot is what makes an install answerable without the other plane; an array there is a snapshot no reader can use.
    BEGIN
        INSERT INTO plt01.int_installs
            (tenant_id, definition_key, definition_version, definition_snapshot,
             criticality, config, state, installed_by, correlation_id,
             uninstalled_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'other.thing', 1, '[]'::jsonb, 'convenience', '{}'::jsonb, 'installed', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: a definition snapshot was written as an array';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- Configuration is an object for the same reason.
    BEGIN
        INSERT INTO plt01.int_installs
            (tenant_id, definition_key, definition_version, definition_snapshot,
             criticality, config, state, installed_by, correlation_id,
             uninstalled_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'other.thing', 1, '{}'::jsonb, 'convenience', '[]'::jsonb, 'installed', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: an install config was written as an array';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- Criticality decides whether the activation gate demands a fallback and an exit plan, so a value outside the set is an install that gate cannot classify.
    BEGIN
        INSERT INTO plt01.int_installs
            (tenant_id, definition_key, definition_version, definition_snapshot,
             criticality, config, state, installed_by, correlation_id,
             uninstalled_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'other.thing', 1, '{}'::jsonb, 'vibes', '{}'::jsonb, 'installed', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: an install took an unknown criticality';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A state outside the machine is one no transition can leave.
    BEGIN
        INSERT INTO plt01.int_installs
            (tenant_id, definition_key, definition_version, definition_snapshot,
             criticality, config, state, installed_by, correlation_id,
             uninstalled_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'other.thing', 1, '{}'::jsonb, 'convenience', '{}'::jsonb, 'paused', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: an install took a state the lifecycle does not have';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- An uninstall is the act that ends a third party's reach, so it carries who and why.
    BEGIN
        INSERT INTO plt01.int_installs
            (tenant_id, definition_key, definition_version, definition_snapshot,
             criticality, config, state, installed_by, correlation_id,
             uninstalled_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'other.thing', 1, '{}'::jsonb, 'convenience', '{}'::jsonb, 'uninstalled', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', now());
        RAISE EXCEPTION 'CHECK 54 FAILED: an integration was uninstalled by nobody';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- And the flag and the timestamp cannot disagree: one says the install is gone and the other says it is live, and whichever a query reads is the answer it gets.
    BEGIN
        INSERT INTO plt01.int_installs
            (tenant_id, definition_key, definition_version, definition_snapshot,
             criticality, config, state, installed_by, correlation_id,
             uninstalled_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'other.thing', 1, '{}'::jsonb, 'convenience', '{}'::jsonb, 'uninstalled', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: an install reads uninstalled with no uninstall recorded';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- One live install per definition. Two means two sets of scopes nobody can reconcile and a sync that writes through whichever the query found first.
    BEGIN
        INSERT INTO plt01.int_installs
            (tenant_id, definition_key, definition_version, definition_snapshot,
             criticality, config, state, installed_by, correlation_id,
             uninstalled_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'acme.payments', 1, '{}'::jsonb, 'convenience', '{}'::jsonb, 'installed', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: a second live install took the same definition';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;

    -- A connection state outside the machine.
    BEGIN
        INSERT INTO plt01.int_connections
            (tenant_id, install_id, external_account_ref, region,
             granted_scopes, state, authorized_at, authorized_by, validated_at,
             validated_by, validation_evidence, revoked_at, revoked_by,
             revoke_reason, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '99999999-1000-4000-8000-000000000001', 'acct_new', 'eu-west', ARRAY['payments.charge'], 'half_open', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 54 FAILED: a connection took an unknown state';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A blank provider account is a connection to nothing, which still holds scopes.
    BEGIN
        INSERT INTO plt01.int_connections
            (tenant_id, install_id, external_account_ref, region,
             granted_scopes, state, authorized_at, authorized_by, validated_at,
             validated_by, validation_evidence, revoked_at, revoked_by,
             revoke_reason, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '99999999-1000-4000-8000-000000000001', '  ', 'eu-west', ARRAY['payments.charge'], 'pending', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 54 FAILED: a connection named a blank provider account';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- The region decides residency, so a malformed one is a promise nobody can check.
    BEGIN
        INSERT INTO plt01.int_connections
            (tenant_id, install_id, external_account_ref, region,
             granted_scopes, state, authorized_at, authorized_by, validated_at,
             validated_by, validation_evidence, revoked_at, revoked_by,
             revoke_reason, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '99999999-1000-4000-8000-000000000001', 'acct_new', 'EU West', ARRAY['payments.charge'], 'pending', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 54 FAILED: a connection took a malformed region';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- **No wildcard.** A scope set that can be widened by a character is one nobody can review, and the holder is outside the building.
    BEGIN
        INSERT INTO plt01.int_connections
            (tenant_id, install_id, external_account_ref, region,
             granted_scopes, state, authorized_at, authorized_by, validated_at,
             validated_by, validation_evidence, revoked_at, revoked_by,
             revoke_reason, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '99999999-1000-4000-8000-000000000001', 'acct_new', 'eu-west', ARRAY['payments.*'], 'pending', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 54 FAILED: a wildcard scope was granted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- An authorization with a timestamp and no actor is access granted by nobody.
    BEGIN
        INSERT INTO plt01.int_connections
            (tenant_id, install_id, external_account_ref, region,
             granted_scopes, state, authorized_at, authorized_by, validated_at,
             validated_by, validation_evidence, revoked_at, revoked_by,
             revoke_reason, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '99999999-1000-4000-8000-000000000001', 'acct_new', 'eu-west', ARRAY['payments.charge'], 'authorized', now(), NULL, NULL, NULL, NULL, NULL, NULL, NULL, '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 54 FAILED: a connection was authorized by nobody';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A validation with no evidence is a state change anybody can assert for free, and activation depends on this state.
    BEGIN
        INSERT INTO plt01.int_connections
            (tenant_id, install_id, external_account_ref, region,
             granted_scopes, state, authorized_at, authorized_by, validated_at,
             validated_by, validation_evidence, revoked_at, revoked_by,
             revoke_reason, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '99999999-1000-4000-8000-000000000001', 'acct_new', 'eu-west', ARRAY['payments.charge'], 'validated', now(), '33333333-3333-4333-8333-333333333333', now(), '33333333-3333-4333-8333-333333333333', NULL, NULL, NULL, NULL, '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 54 FAILED: a connection was validated with no evidence';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A revocation states a reason, because the question afterwards is why access ended.
    BEGIN
        INSERT INTO plt01.int_connections
            (tenant_id, install_id, external_account_ref, region,
             granted_scopes, state, authorized_at, authorized_by, validated_at,
             validated_by, validation_evidence, revoked_at, revoked_by,
             revoke_reason, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '99999999-1000-4000-8000-000000000001', 'acct_new', 'eu-west', ARRAY['payments.charge'], 'revoked', NULL, NULL, NULL, NULL, NULL, now(), '33333333-3333-4333-8333-333333333333', NULL, '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 54 FAILED: a connection was revoked for no stated reason';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- And the flag and the timestamp cannot disagree.
    BEGIN
        INSERT INTO plt01.int_connections
            (tenant_id, install_id, external_account_ref, region,
             granted_scopes, state, authorized_at, authorized_by, validated_at,
             validated_by, validation_evidence, revoked_at, revoked_by,
             revoke_reason, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '99999999-1000-4000-8000-000000000001', 'acct_new', 'eu-west', ARRAY['payments.charge'], 'revoked', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 54 FAILED: a connection reads revoked with no revocation';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- One live connection per provider account per install. Two would each hold their own scopes against one account, and revoking one would read as revoking access.
    BEGIN
        INSERT INTO plt01.int_connections
            (tenant_id, install_id, external_account_ref, region,
             granted_scopes, state, authorized_at, authorized_by, validated_at,
             validated_by, validation_evidence, revoked_at, revoked_by,
             revoke_reason, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '99999999-1000-4000-8000-000000000001', 'acct_live_1', 'eu-west', ARRAY['payments.charge'], 'pending', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 54 FAILED: a second live connection took the same account';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;

    -- A reference that is not a locator. This is the case that matters: a blank value was
    -- always refused, and a credential pasted into the column was not -- which made the
    -- absence of a secret column a naming convention rather than the control the header
    -- claims it is.
    --
    -- The literal is deliberately *not* shaped like any real provider's key. The first version
    -- used a realistic `sk_live_...` and GitHub's push protection refused the commit, which is
    -- the control working: a test fixture that matches a live-key pattern is one somebody will
    -- eventually have to whitelist, and whitelisting a secret-scanning hit is a habit worth
    -- not starting. What the constraint refuses is anything without a scheme, so the shape of
    -- the string is irrelevant to what is being proved.
    BEGIN
        INSERT INTO plt01.int_credential_refs
            (tenant_id, credential_ref_id, connection_id, vault_ref, scopes, issued_at,
             expires_at, supersedes_credential_ref_id, retired_at, recorded_by,
             correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', gen_random_uuid(),
                '99999999-1000-4000-8000-000000000002',
                'raw-credential-material-not-a-locator', ARRAY['payments.charge'], now(), NULL,
                NULL, now(), '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 54 FAILED: a raw secret was accepted as a vault reference';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- A credential reference with no reference names nothing.
    BEGIN
        INSERT INTO plt01.int_credential_refs
            (tenant_id, credential_ref_id, connection_id, vault_ref, scopes,
             issued_at, expires_at, supersedes_credential_ref_id, retired_at,
             recorded_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', gen_random_uuid(), '99999999-1000-4000-8000-000000000002', '  ', ARRAY['payments.charge'], now(), NULL, NULL, now(), '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 54 FAILED: a credential reference named no vault location';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- An expiry before issue is a credential that was never valid, and the rotation reminder would fire on it for ever.
    BEGIN
        INSERT INTO plt01.int_credential_refs
            (tenant_id, credential_ref_id, connection_id, vault_ref, scopes,
             issued_at, expires_at, supersedes_credential_ref_id, retired_at,
             recorded_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', gen_random_uuid(), '99999999-1000-4000-8000-000000000002', 'vault://new', ARRAY['payments.charge'], now(), now() - INTERVAL '1 day', NULL, now(), '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 54 FAILED: a credential expired before it was issued';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A reference superseding itself is a rotation chain that loops.
    BEGIN
        INSERT INTO plt01.int_credential_refs
            (tenant_id, credential_ref_id, connection_id, vault_ref, scopes,
             issued_at, expires_at, supersedes_credential_ref_id, retired_at,
             recorded_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '99999999-1000-4000-8000-0000000000aa', '99999999-1000-4000-8000-000000000002', 'vault://new', ARRAY['payments.charge'], now(), NULL, '99999999-1000-4000-8000-0000000000aa', now(), '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 54 FAILED: a credential reference superseded itself';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- Scopes carry the same no-wildcard rule as the connection's.
    BEGIN
        INSERT INTO plt01.int_credential_refs
            (tenant_id, credential_ref_id, connection_id, vault_ref, scopes,
             issued_at, expires_at, supersedes_credential_ref_id, retired_at,
             recorded_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', gen_random_uuid(), '99999999-1000-4000-8000-000000000002', 'vault://new', ARRAY['payments.*'], now(), NULL, NULL, now(), '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 54 FAILED: a wildcard scope was recorded on a credential reference';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- One live reference per connection. Two means two secrets are current, and a rotation that retired one would leave the other reachable with scopes nobody re-reviewed.
    BEGIN
        INSERT INTO plt01.int_credential_refs
            (tenant_id, credential_ref_id, connection_id, vault_ref, scopes,
             issued_at, expires_at, supersedes_credential_ref_id, retired_at,
             recorded_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', gen_random_uuid(), '99999999-1000-4000-8000-000000000002', 'vault://new', ARRAY['payments.charge'], now(), NULL, NULL, NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 54 FAILED: a second live credential reference was written';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;

    -- A resource that is not a resource name is a cursor nothing will look up.
    BEGIN
        INSERT INTO plt01.int_sync_cursors
            (tenant_id, connection_id, resource, position, observed_at,
             conflict_policy, reset_at, reset_by, reset_reason)
        VALUES ('11111111-1111-4111-8111-111111111111', '99999999-1000-4000-8000-000000000002', 'Invoices!', 'c-1', now(), 'manual', NULL, NULL, NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: a cursor took a malformed resource';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A blank position is a cursor that cannot say where the sync got to.
    BEGIN
        INSERT INTO plt01.int_sync_cursors
            (tenant_id, connection_id, resource, position, observed_at,
             conflict_policy, reset_at, reset_by, reset_reason)
        VALUES ('11111111-1111-4111-8111-111111111111', '99999999-1000-4000-8000-000000000002', 'invoices', '  ', now(), 'manual', NULL, NULL, NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: a cursor was written with a blank position';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A conflict policy outside the three is one `conflict_resolution` cannot apply.
    BEGIN
        INSERT INTO plt01.int_sync_cursors
            (tenant_id, connection_id, resource, position, observed_at,
             conflict_policy, reset_at, reset_by, reset_reason)
        VALUES ('11111111-1111-4111-8111-111111111111', '99999999-1000-4000-8000-000000000002', 'invoices', 'c-1', now(), 'newest_wins', NULL, NULL, NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: a cursor took an unknown conflict policy';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- Moving a cursor backwards re-reads a window the provider may bill for, so the reset carries who did it and why.
    BEGIN
        INSERT INTO plt01.int_sync_cursors
            (tenant_id, connection_id, resource, position, observed_at,
             conflict_policy, reset_at, reset_by, reset_reason)
        VALUES ('11111111-1111-4111-8111-111111111111', '99999999-1000-4000-8000-000000000002', 'invoices', 'c-1', now(), 'manual', now(), NULL, NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: a cursor was reset by nobody';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- One cursor per connection and resource. Two would advance independently and the next sync would read from whichever the query found.
    BEGIN
        INSERT INTO plt01.int_sync_cursors
            (tenant_id, connection_id, resource, position, observed_at,
             conflict_policy, reset_at, reset_by, reset_reason)
        VALUES ('11111111-1111-4111-8111-111111111111', '99999999-1000-4000-8000-000000000002', 'settlements', 'c-1', now(), 'manual', NULL, NULL, NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: a second cursor took the same resource';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;

    -- A run status outside the set is one no retry decision covers. `finished_at` is set so
    -- that `..._finished` is satisfied and this case tests the status constraint rather than
    -- passing because a sibling fired first -- which is what it did until the mutation sweep
    -- dropped the status constraint and watched the suite stay green.
    BEGIN
        INSERT INTO plt01.int_connector_runs
            (tenant_id, connection_id, resource, status, attempts, max_attempts,
             records_read, records_written, conflicts, last_error, finished_at,
             settled_by, settle_correlation_id, started_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '99999999-1000-4000-8000-000000000002', 'invoices', 'wedged', 1, 5, 0, 0, 0, 'boom', now(), '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 54 FAILED: a run took an unknown status';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A malformed resource, as above.
    BEGIN
        INSERT INTO plt01.int_connector_runs
            (tenant_id, connection_id, resource, status, attempts, max_attempts,
             records_read, records_written, conflicts, last_error, finished_at,
             settled_by, settle_correlation_id, started_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '99999999-1000-4000-8000-000000000002', 'Settlements!', 'running', 1, 5, 0, 0, 0, NULL, NULL, NULL, NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 54 FAILED: a run named a malformed resource';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- Attempts past the budget is a run that has outlived its own retry policy.
    BEGIN
        INSERT INTO plt01.int_connector_runs
            (tenant_id, connection_id, resource, status, attempts, max_attempts,
             records_read, records_written, conflicts, last_error, finished_at,
             settled_by, settle_correlation_id, started_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '99999999-1000-4000-8000-000000000002', 'invoices', 'failed', 6, 5, 0, 0, 0, 'boom', now(), '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 54 FAILED: a run exceeded its own attempt budget';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- Negative counts are a report nobody can reproduce.
    BEGIN
        INSERT INTO plt01.int_connector_runs
            (tenant_id, connection_id, resource, status, attempts, max_attempts,
             records_read, records_written, conflicts, last_error, finished_at,
             settled_by, settle_correlation_id, started_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '99999999-1000-4000-8000-000000000002', 'invoices', 'running', 1, 5, -1, 0, 0, NULL, NULL, NULL, NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 54 FAILED: a run recorded a negative record count';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A failure with no error is a diagnostic nobody can act on, which is the whole of paragraph 3028's diagnostics that a constraint can hold.
    BEGIN
        INSERT INTO plt01.int_connector_runs
            (tenant_id, connection_id, resource, status, attempts, max_attempts,
             records_read, records_written, conflicts, last_error, finished_at,
             settled_by, settle_correlation_id, started_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '99999999-1000-4000-8000-000000000002', 'invoices', 'failed', 1, 5, 0, 0, 0, NULL, now(), '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 54 FAILED: a run failed with nothing recorded about why';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- One running run per connection and resource: a lock rather than a lease, because two
    -- concurrent syncs of one resource read the same window and both advance the same cursor,
    -- so one of them ends up having skipped records it never saw. The seed holds a running
    -- run on `settlements`.
    BEGIN
        INSERT INTO plt01.int_connector_runs
            (tenant_id, connection_id, resource, status, started_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111',
                '99999999-1000-4000-8000-000000000002', 'settlements', 'running',
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 54 FAILED: a second run started on a resource already syncing';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;
    -- A settled run names who settled it, so that a fabricated "synced four million records"
    -- does not carry only the name of the party that did not make the claim.
    BEGIN
        INSERT INTO plt01.int_connector_runs
            (tenant_id, connection_id, resource, status, last_error, finished_at,
             started_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111',
                '99999999-1000-4000-8000-000000000002', 'invoices', 'succeeded', NULL, now(),
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 54 FAILED: a run was settled by nobody';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- A settlement actor with no correlation id is half a record.
    BEGIN
        INSERT INTO plt01.int_connector_runs
            (tenant_id, connection_id, resource, status, finished_at, settled_by,
             started_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111',
                '99999999-1000-4000-8000-000000000002', 'invoices', 'succeeded', now(),
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 54 FAILED: a settlement carried no correlation id';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- Releasing a quarantined run puts a connector that burned its whole budget back in front
    -- of a provider, so it carries who and why.
    BEGIN
        UPDATE plt01.int_connector_runs SET released_at = now()
        WHERE run_id = '99999999-1000-4000-8000-000000000005';
        RAISE EXCEPTION 'CHECK 54 FAILED: a quarantined run was released by nobody';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- A reconciliation is a claim about two sides, made by somebody, with the totals behind it.
    BEGIN
        UPDATE plt01.int_connector_runs SET reconciled_at = now(), reconciled_local = 5,
            reconciled_provider = 5, reconciled_matched = 5
        WHERE run_id = '99999999-1000-4000-8000-000000000005';
        RAISE EXCEPTION 'CHECK 54 FAILED: a reconciliation was recorded by nobody';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- And its arithmetic has to describe two sets, in the database as well as in Python.
    BEGIN
        UPDATE plt01.int_connector_runs SET reconciled_at = now(),
            reconciled_by = '33333333-3333-4333-8333-333333333333',
            reconcile_correlation_id = '33333333-3333-4333-8333-333333333333',
            reconciled_local = 3, reconciled_provider = 3, reconciled_matched = 5
        WHERE run_id = '99999999-1000-4000-8000-000000000005';
        RAISE EXCEPTION 'CHECK 54 FAILED: a reconciliation matched more than exists';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
    -- A finished timestamp and a running status cannot both be true.
    BEGIN
        INSERT INTO plt01.int_connector_runs
            (tenant_id, connection_id, resource, status, attempts, max_attempts,
             records_read, records_written, conflicts, last_error, finished_at,
             settled_by, settle_correlation_id, started_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '99999999-1000-4000-8000-000000000002', 'invoices', 'running', 1, 5, 0, 0, 0, NULL, now(), NULL, NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 54 FAILED: a run reads running and finished at once';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
END $$;
ROLLBACK;

BEGIN;
SET LOCAL ROLE veyro_cp_platform;
DO $$
BEGIN
    -- The entry cases need a **draft** parent: `int_definition_versions_draft_only` refuses a
    -- write to a published version before the column constraints are ever looked at, so
    -- pointing them at the seeded (published) `acme.payments` would make every one of them
    -- pass because a different control fired. This block rolls back.
    INSERT INTO plt01_platform.int_definitions
        (definition_key, version, provider, display_name, criticality, support_owner,
         description)
    VALUES ('acme.case', 1, 'Acme', 'Case', 'convenience', 'ops', 'd');
    INSERT INTO plt01_platform.int_definition_versions
        (definition_key, version, kind, name, required)
    VALUES ('acme.case', 1, 'scope', 'payments.charge', true);
    -- A definition key that is not a key.
    BEGIN
        INSERT INTO plt01_platform.int_definitions
            (definition_key, version, provider, display_name, status, criticality,
             support_owner, description, published_at, retired_at)
        VALUES ('Acme Payments', 1, 'P', 'D', 'draft', 'convenience', 'ops', 'd', NULL, NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: a malformed definition key was registered';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A blank provider names nobody to call when it breaks.
    BEGIN
        INSERT INTO plt01_platform.int_definitions
            (definition_key, version, provider, display_name, status, criticality,
             support_owner, description, published_at, retired_at)
        VALUES ('other.thing', 1, '  ', 'D', 'draft', 'convenience', 'ops', 'd', NULL, NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: a definition named a blank provider';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- Version zero.
    BEGIN
        INSERT INTO plt01_platform.int_definitions
            (definition_key, version, provider, display_name, status, criticality,
             support_owner, description, published_at, retired_at)
        VALUES ('other.thing', 0, 'P', 'D', 'draft', 'convenience', 'ops', 'd', NULL, NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: a definition took version zero';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A status outside the three the install path reads. `published_at` is set for the same
    -- reason as the run case above: without it `..._published_at` fires first and this case
    -- proves nothing about the status constraint.
    BEGIN
        INSERT INTO plt01_platform.int_definitions
            (definition_key, version, provider, display_name, status, criticality,
             support_owner, description, published_at, retired_at)
        VALUES ('other.thing', 1, 'P', 'D', 'beta', 'convenience', 'ops', 'd', now(), NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: a definition took an unknown status';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- Criticality decides the activation obligations.
    BEGIN
        INSERT INTO plt01_platform.int_definitions
            (definition_key, version, provider, display_name, status, criticality,
             support_owner, description, published_at, retired_at)
        VALUES ('other.thing', 1, 'P', 'D', 'draft', 'vibes', 'ops', 'd', NULL, NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: a definition took an unknown criticality';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- Paragraph 3024 asks for a support owner, and a blank one is an integration whose failures have no recipient.
    BEGIN
        INSERT INTO plt01_platform.int_definitions
            (definition_key, version, provider, display_name, status, criticality,
             support_owner, description, published_at, retired_at)
        VALUES ('other.thing', 1, 'P', 'D', 'draft', 'convenience', '  ', 'd', NULL, NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: a definition named no support owner';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A blank description is a catalogue entry nobody can choose from.
    BEGIN
        INSERT INTO plt01_platform.int_definitions
            (definition_key, version, provider, display_name, status, criticality,
             support_owner, description, published_at, retired_at)
        VALUES ('other.thing', 1, 'P', 'D', 'draft', 'convenience', 'ops', '  ', NULL, NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: a definition carried no description';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A published version with no publication date cannot say when installs became possible against it.
    BEGIN
        INSERT INTO plt01_platform.int_definitions
            (definition_key, version, provider, display_name, status, criticality,
             support_owner, description, published_at, retired_at)
        VALUES ('other.thing', 1, 'P', 'D', 'published', 'convenience', 'ops', 'd', NULL, NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: a definition was published with no date';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- And a retired one likewise.
    BEGIN
        INSERT INTO plt01_platform.int_definitions
            (definition_key, version, provider, display_name, status, criticality,
             support_owner, description, published_at, retired_at)
        VALUES ('other.thing', 1, 'P', 'D', 'retired', 'convenience', 'ops', 'd', now(), NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: a definition was retired with no date';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- An entry kind outside the four the reader branches on.
    BEGIN
        INSERT INTO plt01_platform.int_definition_versions
            (definition_key, version, kind, name, required, field_type, enum_values)
        VALUES ('acme.case', 1, 'pricing', 'messaging', false, NULL, NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: a definition entry took an unknown kind';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A blank name is an entry nothing can match.
    BEGIN
        INSERT INTO plt01_platform.int_definition_versions
            (definition_key, version, kind, name, required, field_type, enum_values)
        VALUES ('acme.case', 1, 'capability', '  ', false, NULL, NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: a definition entry was named blank';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A configuration field declares a type; nothing else does.
    BEGIN
        INSERT INTO plt01_platform.int_definition_versions
            (definition_key, version, kind, name, required, field_type, enum_values)
        VALUES ('acme.case', 1, 'config', 'merchant', false, NULL, NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: a configuration field was declared with no type';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- And a capability must not.
    BEGIN
        INSERT INTO plt01_platform.int_definition_versions
            (definition_key, version, kind, name, required, field_type, enum_values)
        VALUES ('acme.case', 1, 'capability', 'storage', false, 'string', NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: a capability was declared with a field type';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- An enum with no values is a field with no legal value.
    BEGIN
        INSERT INTO plt01_platform.int_definition_versions
            (definition_key, version, kind, name, required, field_type, enum_values)
        VALUES ('acme.case', 1, 'config', 'mode', false, 'enum', NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: an enum configuration field declared no values';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- And values on something that is not an enum are values nothing reads.
    BEGIN
        INSERT INTO plt01_platform.int_definition_versions
            (definition_key, version, kind, name, required, field_type, enum_values)
        VALUES ('acme.case', 1, 'config', 'mode', false, 'string', ARRAY['a']);
        RAISE EXCEPTION 'CHECK 54 FAILED: a non-enum field declared enum values';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- Only a scope or a configuration field can be required: a required capability is a capability, and a required region is a contradiction.
    BEGIN
        INSERT INTO plt01_platform.int_definition_versions
            (definition_key, version, kind, name, required, field_type, enum_values)
        VALUES ('acme.case', 1, 'region', 'us-east', true, NULL, NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: a region was declared required';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- One entry per kind and name per version.
    BEGIN
        INSERT INTO plt01_platform.int_definition_versions
            (definition_key, version, kind, name, required, field_type, enum_values)
        VALUES ('acme.case', 1, 'scope', 'payments.charge', true, NULL, NULL);
        RAISE EXCEPTION 'CHECK 54 FAILED: a definition declared one entry twice';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;
END $$;
ROLLBACK;


-- ---------------------------------------------------------------- seed (tenant plane, MOD-013)
-- A notification carries the text a tenant sent to one of its members, so a leak here is one
-- tenant reading another's correspondence -- the most personal thing this build renders.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
INSERT INTO plt01.ntf_templates
    (tenant_id, template_id, template_key, version, category, channel, locale, subject, body,
     variables, status, authored_by, correlation_id, approved_at, approved_by, published_at)
VALUES (:'tenant_a', 'aaaaaaaa-1000-4000-8000-000000000001', 'invoice.issued', 1,
        'transactional', 'email', 'en', 'Invoice {{ number }}',
        'Your invoice {{ number }} is ready.', ARRAY['number'], 'published', :'actor',
        :'actor', now(), '44444444-4444-4444-8444-444444444444', now());
INSERT INTO plt01.ntf_preferences
    (tenant_id, preference_id, recipient_id, category, channel, allowed, digest_mode, set_by,
     correlation_id)
VALUES (:'tenant_a', 'aaaaaaaa-1000-4000-8000-000000000002',
        '55555555-5555-4555-8555-555555555555', 'marketing', 'email', false, 'immediate',
        :'actor', :'actor');
INSERT INTO plt01.ntf_channel_policies
    (tenant_id, policy_id, channel, enabled, fallback_channel, cost_per_message_minor,
     currency, set_by, correlation_id)
VALUES (:'tenant_a', 'aaaaaaaa-1000-4000-8000-000000000003', 'email', true, 'sms', 12, 'EUR',
        :'actor', :'actor');
INSERT INTO plt01.ntf_notifications
    (tenant_id, notification_id, template_id, template_key, template_version, category,
     channel, locale, rendered_subject, rendered_body, recipient_id, address_digest,
     priority, status, decision_reason, idempotency_key, requested_by, correlation_id)
VALUES (:'tenant_a', 'aaaaaaaa-1000-4000-8000-000000000004',
        'aaaaaaaa-1000-4000-8000-000000000001', 'invoice.issued', 1, 'transactional', 'email',
        'en', 'Invoice INV-1', 'Your invoice INV-1 is ready.',
        '55555555-5555-4555-8555-555555555555', repeat('a', 64), 'normal', 'requested',
        'no_preference_stops_it', 'seed-invoice-1', :'actor', :'actor');
INSERT INTO plt01.ntf_deliveries
    (tenant_id, delivery_id, notification_id, channel)
VALUES (:'tenant_a', 'aaaaaaaa-1000-4000-8000-000000000005',
        'aaaaaaaa-1000-4000-8000-000000000004', 'email');
INSERT INTO plt01.ntf_suppressions
    (tenant_id, suppression_id, channel, address_digest, reason, correlation_id)
VALUES (:'tenant_a', 'aaaaaaaa-1000-4000-8000-000000000006', 'email', repeat('b', 64),
        'bounced', :'actor');
INSERT INTO plt01.ntf_digests
    (tenant_id, digest_id, recipient_id, category, channel, window_start, window_end)
VALUES (:'tenant_a', 'aaaaaaaa-1000-4000-8000-000000000007',
        '55555555-5555-4555-8555-555555555555', 'coaching', 'email',
        TIMESTAMPTZ '2026-11-14 00:00:00+00', TIMESTAMPTZ '2026-11-15 00:00:00+00');
INSERT INTO plt01.ntf_digest_entries (tenant_id, digest_id, notification_id)
VALUES (:'tenant_a', 'aaaaaaaa-1000-4000-8000-000000000007',
        'aaaaaaaa-1000-4000-8000-000000000004');
INSERT INTO plt01.ntf_recipient_channels
    (tenant_id, recipient_id, channel, address_digest, bound_by, correlation_id)
VALUES (:'tenant_a', '55555555-5555-4555-8555-555555555555', 'email', repeat('9', 64),
        :'actor', :'actor');
COMMIT;

-- Tenant B holds one template of its own, so a leaked predicate shows up as a count above the
-- expected one rather than as the zero an empty table would give anyway.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
INSERT INTO plt01.ntf_templates
    (tenant_id, template_key, version, category, channel, locale, subject, body, variables,
     authored_by, correlation_id)
VALUES (:'tenant_b', 'welcome.sent', 1, 'operational', 'email', 'is', 'Velkomin',
        'Velkomin {{ name }}.', ARRAY['name'], :'actor', :'actor');
COMMIT;

-- ---------------------------------------------------------------- 55. ntf tables isolate
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['ntf_preferences', 'ntf_channel_policies',
                               'ntf_notifications', 'ntf_deliveries', 'ntf_suppressions',
                               'ntf_digests', 'ntf_digest_entries',
                               'ntf_recipient_channels']
    LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 55 FAILED: tenant B sees % rows of tenant A in %', seen, tbl;
        END IF;
    END LOOP;
    IF (SELECT count(*) FROM plt01.ntf_templates) <> 1 THEN
        RAISE EXCEPTION 'CHECK 55 FAILED: tenant B sees % templates, expected its own 1',
            (SELECT count(*) FROM plt01.ntf_templates);
    END IF;
    IF EXISTS (SELECT 1 FROM plt01.ntf_templates WHERE template_key = 'invoice.issued') THEN
        RAISE EXCEPTION 'CHECK 55 FAILED: tenant B read tenant A''s template';
    END IF;
END $$;
COMMIT;

BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    IF (SELECT count(*) FROM plt01.ntf_templates) <> 1
       OR (SELECT count(*) FROM plt01.ntf_preferences) <> 1
       OR (SELECT count(*) FROM plt01.ntf_channel_policies) <> 1
       OR (SELECT count(*) FROM plt01.ntf_notifications) <> 1
       OR (SELECT count(*) FROM plt01.ntf_deliveries) <> 1
       OR (SELECT count(*) FROM plt01.ntf_suppressions) <> 1
       OR (SELECT count(*) FROM plt01.ntf_digests) <> 1
       OR (SELECT count(*) FROM plt01.ntf_digest_entries) <> 1
       OR (SELECT count(*) FROM plt01.ntf_recipient_channels) <> 1 THEN
        RAISE EXCEPTION 'CHECK 55 FAILED: tenant A cannot see its own notification rows';
    END IF;
END $$;
COMMIT;

-- The catalogue sweep: RLS on both halves of the policy, one permissive policy per table, the
-- migrator as owner, a count guard, and a tenant-leading primary key. The full shape checks 44
-- and 49 arrived at.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
DECLARE
    bad text;
BEGIN
    SELECT string_agg(relname, ', ') INTO bad
    FROM pg_class
    WHERE relnamespace = 'plt01'::regnamespace AND relkind IN ('r', 'p') AND relname LIKE 'ntf\_%'
      AND NOT (relrowsecurity AND relforcerowsecurity);
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 55 FAILED: ntf_ tables without ENABLE and FORCE RLS: %', bad;
    END IF;
    IF (SELECT count(*) FROM pg_class
        WHERE relnamespace = 'plt01'::regnamespace AND relkind IN ('r', 'p')
          AND relname LIKE 'ntf\_%') < 9 THEN
        RAISE EXCEPTION 'CHECK 55 FAILED: fewer than 8 ntf_ tables, so the sweep proved nothing';
    END IF;
    IF (SELECT count(*) FROM pg_class
        WHERE relnamespace = 'plt01'::regnamespace AND relkind IN ('r', 'p') AND relname LIKE 'ntf\_%'
          AND pg_get_userbyid(relowner) <> 'veyro_cp_migrator') <> 0 THEN
        RAISE EXCEPTION 'CHECK 55 FAILED: an ntf_ table is not owned by the migrator';
    END IF;
    SELECT string_agg(c.relname, ', ') INTO bad
    FROM pg_class c
    LEFT JOIN pg_policies p
      ON p.schemaname = 'plt01' AND p.tablename = c.relname
     AND p.qual = '(tenant_id = (NULLIF(current_setting(''app.tenant_id''::text, true), ''''::text))::uuid)'
     AND p.with_check = p.qual
    WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
      AND c.relname LIKE 'ntf\_%' AND p.policyname IS NULL;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 55 FAILED: ntf_ tables without the exact tenant predicate in '
            'both USING and WITH CHECK: %', bad;
    END IF;
    SELECT string_agg(c.relname || ' (' || n::text || ')', ', ') INTO bad
    FROM pg_class c
    CROSS JOIN LATERAL (
        SELECT count(*) AS n FROM pg_policies p
        WHERE p.schemaname = 'plt01' AND p.tablename = c.relname AND p.permissive = 'PERMISSIVE'
    ) counted
    WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
      AND c.relname LIKE 'ntf\_%' AND counted.n <> 1;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 55 FAILED: ntf_ tables without exactly one permissive policy: %',
            bad;
    END IF;
    SELECT string_agg(c.relname, ', ') INTO bad
    FROM pg_class c
    JOIN pg_index i ON i.indrelid = c.oid AND i.indisprimary
    WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
      AND c.relname LIKE 'ntf\_%'
      AND (SELECT attname FROM pg_attribute
           WHERE attrelid = c.oid AND attnum = i.indkey[0]) <> 'tenant_id';
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 55 FAILED: ntf_ tables whose primary key does not lead with '
            'tenant_id: %', bad;
    END IF;
END $$;
COMMIT;

-- The owner seat, then the worker seat, under another tenant's context and under none.
BEGIN;
SET LOCAL ROLE veyro_cp_migrator;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['ntf_templates', 'ntf_preferences', 'ntf_channel_policies',
                               'ntf_notifications', 'ntf_deliveries', 'ntf_suppressions',
                               'ntf_digests', 'ntf_digest_entries',
                               'ntf_recipient_channels']
    LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 55 FAILED: the table owner read % rows of %, so FORCE RLS is off',
                seen, tbl;
        END IF;
    END LOOP;
END $$;
COMMIT;

BEGIN;
SET LOCAL ROLE veyro_cp_worker;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['ntf_preferences', 'ntf_channel_policies',
                               'ntf_notifications', 'ntf_deliveries', 'ntf_suppressions',
                               'ntf_digests', 'ntf_digest_entries',
                               'ntf_recipient_channels']
    LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 55 FAILED: the worker read % rows of tenant A in % from '
                'tenant B''s context', seen, tbl;
        END IF;
    END LOOP;
    IF (SELECT count(*) FROM plt01.ntf_templates) <> 1 THEN
        RAISE EXCEPTION 'CHECK 55 FAILED: the worker sees % templates in tenant B, expected 1',
            (SELECT count(*) FROM plt01.ntf_templates);
    END IF;
END $$;
COMMIT;

BEGIN;
SET LOCAL ROLE veyro_cp_worker;
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['ntf_templates', 'ntf_preferences', 'ntf_channel_policies',
                               'ntf_notifications', 'ntf_deliveries', 'ntf_suppressions',
                               'ntf_digests', 'ntf_digest_entries',
                               'ntf_recipient_channels']
    LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 55 FAILED: the worker read % rows of % with no tenant context',
                seen, tbl;
        END IF;
    END LOOP;
END $$;
ROLLBACK;

-- ---------------------------------------------------------------- 56. fail closed, ntf tables
BEGIN;
SET LOCAL ROLE veyro_cp_app;
DO $$
DECLARE
    tbl text;
    seen bigint;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['ntf_templates', 'ntf_preferences', 'ntf_channel_policies',
                               'ntf_notifications', 'ntf_deliveries', 'ntf_suppressions',
                               'ntf_digests', 'ntf_digest_entries',
                               'ntf_recipient_channels']
    LOOP
        EXECUTE format('SELECT count(*) FROM plt01.%I', tbl) INTO seen;
        IF seen <> 0 THEN
            RAISE EXCEPTION 'CHECK 56 FAILED: % returned % rows with no tenant context',
                tbl, seen;
        END IF;
    END LOOP;
    -- A notification written with no context is a message addressed to nobody's tenant, which
    -- would read as belonging to whichever tenant's query found it.
    BEGIN
        INSERT INTO plt01.ntf_notifications
            (tenant_id, template_id, template_key, template_version, category, channel,
             locale, rendered_subject, rendered_body, recipient_id, address_digest, status,
             decision_reason, idempotency_key, requested_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111',
                'aaaaaaaa-1000-4000-8000-000000000001', 'invoice.issued', 1, 'transactional',
                'email', 'en', 'S', 'B', '55555555-5555-4555-8555-555555555555',
                repeat('c', 64), 'requested', 'r', 'no-context-1',
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 56 FAILED: a notification was authored with no tenant context';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.ntf_suppressions
            (tenant_id, channel, address_digest, reason, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'email', repeat('d', 64), 'bounced',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 56 FAILED: a suppression was written with no tenant context';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    BEGIN
        INSERT INTO plt01.ntf_preferences
            (tenant_id, recipient_id, category, channel, set_by, correlation_id)
        VALUES ('22222222-2222-4222-8222-222222222222',
                '55555555-5555-4555-8555-555555555555', 'coaching', 'email',
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 56 FAILED: a preference was written into another tenant';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;


-- ---------------------------------------------------------------- 57. cross-tenant parents
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
BEGIN
    BEGIN
        INSERT INTO plt01.ntf_notifications
            (tenant_id, template_id, template_key, template_version, category, channel,
             locale, rendered_subject, rendered_body, recipient_id, address_digest, status,
             decision_reason, idempotency_key, requested_by, correlation_id)
        VALUES ('22222222-2222-4222-8222-222222222222',
                'aaaaaaaa-1000-4000-8000-000000000001', 'invoice.issued', 1, 'transactional',
                'email', 'en', 'S', 'B', '55555555-5555-4555-8555-555555555555',
                repeat('e', 64), 'requested', 'r', 'borrowed-template-1',
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 57 FAILED: a notification was rendered from another tenant''s '
            'template';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.ntf_deliveries (tenant_id, notification_id, channel)
        VALUES ('22222222-2222-4222-8222-222222222222',
                'aaaaaaaa-1000-4000-8000-000000000004', 'email');
        RAISE EXCEPTION 'CHECK 57 FAILED: a delivery was attached to another tenant''s '
            'notification';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO plt01.ntf_digest_entries (tenant_id, digest_id, notification_id)
        VALUES ('22222222-2222-4222-8222-222222222222',
                'aaaaaaaa-1000-4000-8000-000000000007',
                'aaaaaaaa-1000-4000-8000-000000000004');
        RAISE EXCEPTION 'CHECK 57 FAILED: another tenant''s notification was folded into a '
            'digest here';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
END $$;
ROLLBACK;

-- Every foreign key compared as a set, which is the shape check 51 ended up with after a
-- reviewer dropped two that only a behavioural sample covered.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
DECLARE
    missing text;
BEGIN
    WITH live AS (
        SELECT c.conrelid::regclass::text || ': '
               || (SELECT string_agg(a.attname, ',' ORDER BY k.ord)
                   FROM unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord)
                   JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum)
               || ' -> ' || c.confrelid::regclass::text AS fk
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.contype = 'f' AND t.relname LIKE 'ntf\_%'
          AND t.relnamespace = 'plt01'::regnamespace
    ), expected(fk) AS (VALUES
        ('plt01.ntf_templates: tenant_id -> plt01_platform.tenants'),
        ('plt01.ntf_preferences: tenant_id -> plt01_platform.tenants'),
        ('plt01.ntf_channel_policies: tenant_id -> plt01_platform.tenants'),
        ('plt01.ntf_notifications: tenant_id -> plt01_platform.tenants'),
        ('plt01.ntf_notifications: tenant_id,template_id -> plt01.ntf_templates'),
        ('plt01.ntf_notifications: tenant_id,consent_record_id -> plt01.sec_consent_records'),
        ('plt01.ntf_deliveries: tenant_id -> plt01_platform.tenants'),
        ('plt01.ntf_deliveries: tenant_id,notification_id -> plt01.ntf_notifications'),
        ('plt01.ntf_suppressions: tenant_id -> plt01_platform.tenants'),
        ('plt01.ntf_digests: tenant_id -> plt01_platform.tenants'),
        ('plt01.ntf_digest_entries: tenant_id -> plt01_platform.tenants'),
        ('plt01.ntf_digest_entries: tenant_id,digest_id -> plt01.ntf_digests'),
        ('plt01.ntf_digest_entries: tenant_id,notification_id -> plt01.ntf_notifications'),
        ('plt01.ntf_recipient_channels: tenant_id -> plt01_platform.tenants'))
    SELECT string_agg(fk, '; ') INTO missing FROM (
        (SELECT fk FROM expected EXCEPT SELECT fk FROM live)
        UNION ALL
        (SELECT fk FROM live EXCEPT SELECT fk FROM expected)
    ) differences;
    IF missing IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 57 FAILED: foreign keys differ from the expected set: %',
            missing;
    END IF;
END $$;
COMMIT;

-- The registry reference behaviourally, for one table.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '44444444-4444-4444-8444-444444444444';
DO $$
BEGIN
    BEGIN
        INSERT INTO plt01.ntf_channel_policies
            (tenant_id, channel, set_by, correlation_id)
        VALUES ('44444444-4444-4444-8444-444444444444', 'email',
                '33333333-3333-4333-8333-333333333333',
                '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 57 FAILED: a channel policy was set for an unregistered tenant';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
END $$;
ROLLBACK;

-- ------------------------------------------- 58. this module holds no contact address
-- **The control is the absence of a column**, as it was for MOD-012's credential references --
-- and an absence is exactly what a later migration adds back without anybody noticing. Every
-- table's column list is compared in full, not just the two that carry a digest, because the
-- next migration's address will not be on the table that happens to be pinned.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
DECLARE
    wrong text;
BEGIN
    WITH expected(tbl, cols) AS (VALUES
        ('plt01.ntf_templates',
         'approved_at,approved_by,authored_by,body,category,channel,correlation_id,'
         'created_at,locale,published_at,retired_at,status,subject,template_id,'
         'template_key,tenant_id,variables,version'),
        ('plt01.ntf_preferences',
         'allowed,category,channel,correlation_id,daily_cap,digest_mode,preference_id,'
         'quiet_from,quiet_timezone,quiet_until,recipient_id,set_by,tenant_id,updated_at'),
        ('plt01.ntf_channel_policies',
         'channel,correlation_id,cost_per_message_minor,currency,enabled,fallback_channel,'
         'policy_id,set_by,tenant_id,updated_at'),
        ('plt01.ntf_notifications',
         'address_digest,bypass_policy_ref,category,channel,consent_record_id,'
         'correlation_id,decision_reason,idempotency_key,locale,notification_id,priority,'
         'recipient_id,rendered_body,rendered_subject,requested_at,requested_by,'
         'scheduled_for,status,template_id,template_key,template_version,tenant_id'),
        ('plt01.ntf_deliveries',
         'attempts,channel,created_at,delivered_at,delivery_id,dispatched_at,last_error,'
         'max_attempts,next_attempt_at,notification_id,provider_ref,state,tenant_id'),
        ('plt01.ntf_suppressions',
         'address_digest,channel,correlation_id,detail,reason,recorded_at,recorded_by,'
         'release_correlation_id,release_reason,released_at,released_by,suppression_id,'
         'tenant_id'),
        ('plt01.ntf_digests',
         'category,channel,closed_at,created_at,digest_id,notification_count,recipient_id,'
         'state,tenant_id,window_end,window_start'),
        ('plt01.ntf_digest_entries',
         'added_at,digest_id,notification_id,tenant_id'),
        -- No address column here either: the binding is digest to recipient, and the thing
        -- being bound is still only ever a digest.
        ('plt01.ntf_recipient_channels',
         'address_digest,bound_at,bound_by,channel,correlation_id,rebind_correlation_id,'
         'rebind_reason,rebound_at,rebound_by,recipient_id,tenant_id'))
    SELECT string_agg(e.tbl || ': ' || coalesce(a.actual, '(none)'), '; ') INTO wrong
    FROM expected e
    LEFT JOIN LATERAL (
        SELECT string_agg(att.attname, ',' ORDER BY att.attname) AS actual
        FROM pg_attribute att
        WHERE att.attrelid = e.tbl::regclass AND att.attnum > 0 AND NOT att.attisdropped
    ) a ON true
    WHERE coalesce(a.actual, '(none)') <> e.cols;
    IF wrong IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 58 FAILED: ntf_ columns are not the expected set, so a contact '
            'address may now have somewhere to live: %', wrong;
    END IF;

    -- The table list has to cover the catalogue, so a ninth table is a failure rather than an
    -- omission -- which is what check 47 was missing until a reviewer added a table and
    -- watched the suite pass.
    SELECT string_agg(c.relname, ', ') INTO wrong
    FROM pg_class c
    WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
      AND c.relname LIKE 'ntf\_%'
      AND ('plt01.' || c.relname) NOT IN (
          'plt01.ntf_templates', 'plt01.ntf_preferences', 'plt01.ntf_channel_policies',
          'plt01.ntf_notifications', 'plt01.ntf_deliveries', 'plt01.ntf_suppressions',
          'plt01.ntf_digests', 'plt01.ntf_digest_entries',
          'plt01.ntf_recipient_channels');
    IF wrong IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 58 FAILED: ntf_ tables with no stated column list: %', wrong;
    END IF;

    -- And the two digests are digests. A column that admitted an address would make the
    -- absence of an address column a naming convention, which is MOD-012's `vault_ref`
    -- finding one module later.
    BEGIN
        INSERT INTO plt01.ntf_suppressions
            (tenant_id, channel, address_digest, reason, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'email', 'member@example.test',
                'bounced', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 58 FAILED: an address was accepted where a digest belongs';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
END $$;
ROLLBACK;


-- ---------------------------------------------------------------- 59. notification privileges
-- Two sentences in this module rest entirely on the privilege layer.
--
--   * **"Delivery failure never rewrites the authored message"** (paragraph 2474). The rendered
--     subject and body, the recipient, the digest of their address, the category and the
--     consent that permitted it carry no UPDATE grant at all; only the status and the schedule
--     move.
--   * **"Only an unsubscribe may be released."** `reason` carries no UPDATE, so a bounce cannot
--     be relabelled an unsubscribe and then lifted -- which is the route around the constraint
--     that refuses the lift itself.
--
-- Swept per column and per role, with the table list required to cover the catalogue.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
DECLARE
    wrong text;
BEGIN
    WITH expected(tbl, cols) AS (VALUES
        ('ntf_templates',
         'approved_at,approved_by,body,published_at,retired_at,status,subject,variables'),
        ('ntf_preferences',
         'allowed,correlation_id,daily_cap,digest_mode,quiet_from,quiet_timezone,'
         'quiet_until,set_by,updated_at'),
        ('ntf_channel_policies',
         'correlation_id,cost_per_message_minor,currency,enabled,fallback_channel,set_by,'
         'updated_at'),
        ('ntf_notifications', 'scheduled_for,status'),
        ('ntf_deliveries',
         'attempts,delivered_at,dispatched_at,last_error,next_attempt_at,provider_ref,state'),
        ('ntf_suppressions',
         'release_correlation_id,release_reason,released_at,released_by'),
        ('ntf_digests', 'closed_at,notification_count,state'),
        ('ntf_digest_entries', '(none)'),
        ('ntf_recipient_channels',
         'address_digest,rebind_correlation_id,rebind_reason,rebound_at,rebound_by'))
    SELECT string_agg(
               e.tbl || ' / ' || g.grantee || ': ' || coalesce(a.actual, '(none)'), '; ')
    INTO wrong
    FROM expected e
    CROSS JOIN (VALUES ('veyro_cp_app'), ('veyro_cp_worker')) AS g(grantee)
    LEFT JOIN LATERAL (
        SELECT string_agg(att.attname, ',' ORDER BY att.attname) AS actual
        FROM pg_attribute att
        WHERE att.attrelid = ('plt01.' || e.tbl)::regclass
          AND att.attnum > 0 AND NOT att.attisdropped
          AND has_column_privilege(g.grantee, att.attrelid, att.attname, 'UPDATE')
    ) a ON true
    WHERE coalesce(a.actual, '(none)') <> e.cols;
    IF wrong IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 59 FAILED: UPDATE column grants differ from the expected set: %',
            wrong;
    END IF;

    SELECT string_agg(c.relname, ', ') INTO wrong
    FROM pg_class c
    WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
      AND c.relname LIKE 'ntf\_%'
      AND c.relname NOT IN ('ntf_templates', 'ntf_preferences', 'ntf_channel_policies',
                            'ntf_notifications', 'ntf_deliveries', 'ntf_suppressions',
                            'ntf_digests', 'ntf_digest_entries',
                            'ntf_recipient_channels');
    IF wrong IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 59 FAILED: ntf_ tables with no stated UPDATE expectation: %',
            wrong;
    END IF;

    IF (SELECT count(*) FROM pg_class c, aclexplode(c.relacl) acl
        WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
          AND c.relname LIKE 'ntf\_%'
          AND pg_get_userbyid(acl.grantee) IN ('veyro_cp_app', 'veyro_cp_worker')
          AND acl.privilege_type IN ('DELETE', 'TRUNCATE', 'REFERENCES')) <> 0 THEN
        RAISE EXCEPTION 'CHECK 59 FAILED: a runtime role holds DELETE, TRUNCATE or REFERENCES';
    END IF;
    IF (SELECT count(*) FROM pg_class c, aclexplode(c.relacl) acl
        WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
          AND c.relname LIKE 'ntf\_%' AND acl.grantee <> 0
          AND pg_get_userbyid(acl.grantee)
              NOT IN ('veyro_cp_app', 'veyro_cp_worker', 'veyro_cp_migrator')) <> 0 THEN
        RAISE EXCEPTION 'CHECK 59 FAILED: an ntf_ table is granted to somebody unexpected';
    END IF;
    IF (SELECT count(*) FROM pg_class c, aclexplode(c.relacl) acl
        WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
          AND c.relname LIKE 'ntf\_%' AND acl.grantee = 0) <> 0 THEN
        RAISE EXCEPTION 'CHECK 59 FAILED: an ntf_ table carries a PUBLIC grant';
    END IF;
    IF (SELECT count(*) FROM pg_class c
        JOIN pg_attribute att ON att.attrelid = c.oid AND att.attnum > 0
                             AND NOT att.attisdropped AND att.attacl IS NOT NULL,
        LATERAL aclexplode(att.attacl) acl
        WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
          AND c.relname LIKE 'ntf\_%'
          AND (acl.grantee = 0
               OR acl.privilege_type IN ('DELETE', 'TRUNCATE', 'REFERENCES')
               OR pg_get_userbyid(acl.grantee)
                  NOT IN ('veyro_cp_app', 'veyro_cp_worker', 'veyro_cp_migrator'))) <> 0 THEN
        RAISE EXCEPTION 'CHECK 59 FAILED: a column-level grant is PUBLIC, is REFERENCES, or '
            'names a role outside the three expected ones';
    END IF;

    -- Behaviourally. Each of these is the rewrite somebody with a motive would reach for.
    BEGIN
        UPDATE plt01.ntf_notifications SET rendered_body = 'something else';
        RAISE EXCEPTION 'CHECK 59 FAILED: an authored message was rewritten';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        UPDATE plt01.ntf_notifications SET category = 'marketing';
        RAISE EXCEPTION 'CHECK 59 FAILED: a notification''s category was changed after the fact';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        UPDATE plt01.ntf_notifications SET address_digest = repeat('f', 64);
        RAISE EXCEPTION 'CHECK 59 FAILED: a notification was readdressed';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        UPDATE plt01.ntf_suppressions SET reason = 'unsubscribed';
        RAISE EXCEPTION 'CHECK 59 FAILED: a bounce was relabelled an unsubscribe';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        UPDATE plt01.ntf_suppressions SET address_digest = repeat('f', 64);
        RAISE EXCEPTION 'CHECK 59 FAILED: a suppression was moved to another address';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        UPDATE plt01.ntf_templates SET authored_by = gen_random_uuid();
        RAISE EXCEPTION 'CHECK 59 FAILED: a template''s author was rewritten';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        DELETE FROM plt01.ntf_notifications;
        RAISE EXCEPTION 'CHECK 59 FAILED: an authored notification was deleted';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        DELETE FROM plt01.ntf_digest_entries;
        RAISE EXCEPTION 'CHECK 59 FAILED: a digest entry was deleted';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;
END $$;
ROLLBACK;

-- A published template's content is immutable by trigger as well as by grant, because the
-- grant admits a body change on a draft and cannot see the status -- MOD-012's finding, which
-- this module inherits rather than rediscovers.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    BEGIN
        UPDATE plt01.ntf_templates SET body = 'a different message'
        WHERE template_id = 'aaaaaaaa-1000-4000-8000-000000000001';
        RAISE EXCEPTION 'CHECK 59 FAILED: a published template''s body was changed';
    EXCEPTION
        WHEN restrict_violation THEN NULL;
    END;
    BEGIN
        UPDATE plt01.ntf_templates SET variables = ARRAY['number', 'amount']
        WHERE template_id = 'aaaaaaaa-1000-4000-8000-000000000001';
        RAISE EXCEPTION 'CHECK 59 FAILED: a published template gained a variable';
    EXCEPTION
        WHEN restrict_violation THEN NULL;
    END;
    BEGIN
        UPDATE plt01.ntf_templates SET published_at = now() - INTERVAL '1 year'
        WHERE template_id = 'aaaaaaaa-1000-4000-8000-000000000001';
        RAISE EXCEPTION 'CHECK 59 FAILED: a publication date was moved';
    EXCEPTION
        WHEN restrict_violation THEN NULL;
    END;
    BEGIN
        UPDATE plt01.ntf_templates SET status = 'retired', retired_at = now()
        WHERE template_id = 'aaaaaaaa-1000-4000-8000-000000000001';
        UPDATE plt01.ntf_templates SET status = 'published', retired_at = NULL
        WHERE template_id = 'aaaaaaaa-1000-4000-8000-000000000001';
        RAISE EXCEPTION 'CHECK 59 FAILED: a retired template was un-retired';
    EXCEPTION
        WHEN restrict_violation THEN NULL;
    END;
    -- **Immutability by trigger has to refuse the demotion, not only the edit.** `status` is
    -- in the UPDATE grant, so a single-statement test proves nothing about a writer willing
    -- to use three: demote to draft (no content field moves, so the body guard sleeps),
    -- rewrite the body (OLD.status now reads 'draft'), publish again (approved_at and
    -- approved_by were never cleared, so the approval constraint is satisfied). The row then
    -- carries an attacker's text under the original approver's name and timestamp, which is
    -- the separation of duties on content defeated end to end. Found by review; the case is
    -- three statements because the defect was.
    BEGIN
        UPDATE plt01.ntf_templates SET status = 'draft'
        WHERE template_id = 'aaaaaaaa-1000-4000-8000-000000000001';
        UPDATE plt01.ntf_templates SET body = 'Pay at http://attacker.example/pay'
        WHERE template_id = 'aaaaaaaa-1000-4000-8000-000000000001';
        UPDATE plt01.ntf_templates SET status = 'published'
        WHERE template_id = 'aaaaaaaa-1000-4000-8000-000000000001';
        RAISE EXCEPTION 'CHECK 59 FAILED: a published template was demoted and rewritten';
    EXCEPTION
        WHEN restrict_violation THEN NULL;
    END;
END $$;
ROLLBACK;


-- ---------------------------------------------------------------- 60. the ntf_ constraints
-- Every CHECK constraint and every unique index on this module's tables. Generated from the
-- catalogue of constraints that exist rather than from the ones somebody thought to write
-- down, and **each case sets every other column so the row violates exactly one rule** -- the
-- sibling-constraint vacuity MOD-011 shipped and MOD-012 reintroduced within the hour.
BEGIN;
SET LOCAL ROLE veyro_cp_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
BEGIN
    -- A template key that is not a key names content nothing can resolve.
    BEGIN
        INSERT INTO plt01.ntf_templates
            (tenant_id, template_key, version, category, channel, locale, subject,
             body, variables, status, authored_by, correlation_id, approved_at,
             approved_by, published_at, retired_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'Invoice Issued', 1, 'operational', 'email', 'en', 'S', 'B', ARRAY[]::text[], 'draft', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', NULL, NULL, NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a malformed template key was stored';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- Version zero.
    BEGIN
        INSERT INTO plt01.ntf_templates
            (tenant_id, template_key, version, category, channel, locale, subject,
             body, variables, status, authored_by, correlation_id, approved_at,
             approved_by, published_at, retired_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'other.thing', 0, 'operational', 'email', 'en', 'S', 'B', ARRAY[]::text[], 'draft', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', NULL, NULL, NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a template took version zero';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A category outside the four decides nothing about consent or opt-out.
    BEGIN
        INSERT INTO plt01.ntf_templates
            (tenant_id, template_key, version, category, channel, locale, subject,
             body, variables, status, authored_by, correlation_id, approved_at,
             approved_by, published_at, retired_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'other.thing', 1, 'promotional', 'email', 'en', 'S', 'B', ARRAY[]::text[], 'draft', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', NULL, NULL, NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a template took an unknown category';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A channel outside the five is a template nothing can send.
    BEGIN
        INSERT INTO plt01.ntf_templates
            (tenant_id, template_key, version, category, channel, locale, subject,
             body, variables, status, authored_by, correlation_id, approved_at,
             approved_by, published_at, retired_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'other.thing', 1, 'operational', 'carrier_pigeon', 'en', '', 'B', ARRAY[]::text[], 'draft', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', NULL, NULL, NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a template took an unknown channel';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A locale that is not a locale cannot be matched by a request.
    BEGIN
        INSERT INTO plt01.ntf_templates
            (tenant_id, template_key, version, category, channel, locale, subject,
             body, variables, status, authored_by, correlation_id, approved_at,
             approved_by, published_at, retired_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'other.thing', 1, 'operational', 'email', 'English', 'S', 'B', ARRAY[]::text[], 'draft', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', NULL, NULL, NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a template took a malformed locale';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A template with no body is a message with nothing in it.
    BEGIN
        INSERT INTO plt01.ntf_templates
            (tenant_id, template_key, version, category, channel, locale, subject,
             body, variables, status, authored_by, correlation_id, approved_at,
             approved_by, published_at, retired_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'other.thing', 1, 'operational', 'email', 'en', 'S', '   ', ARRAY[]::text[], 'draft', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', NULL, NULL, NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a template was stored with a blank body';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- Only email shows a subject: one on an SMS is text its author expects to be read and that goes nowhere.
    BEGIN
        INSERT INTO plt01.ntf_templates
            (tenant_id, template_key, version, category, channel, locale, subject,
             body, variables, status, authored_by, correlation_id, approved_at,
             approved_by, published_at, retired_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'other.thing', 1, 'operational', 'sms', 'en', 'Subject', 'B', ARRAY[]::text[], 'draft', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', NULL, NULL, NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: an sms template carried a subject';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- And an email without one has nothing in the inbox line.
    BEGIN
        INSERT INTO plt01.ntf_templates
            (tenant_id, template_key, version, category, channel, locale, subject,
             body, variables, status, authored_by, correlation_id, approved_at,
             approved_by, published_at, retired_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'other.thing', 1, 'operational', 'email', 'en', '  ', 'B', ARRAY[]::text[], 'draft', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', NULL, NULL, NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: an email template carried no subject';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A status outside the three the authoring path reads.
    BEGIN
        INSERT INTO plt01.ntf_templates
            (tenant_id, template_key, version, category, channel, locale, subject,
             body, variables, status, authored_by, correlation_id, approved_at,
             approved_by, published_at, retired_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'other.thing', 1, 'operational', 'email', 'en', 'S', 'B', ARRAY[]::text[], 'review', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', NULL, NULL, NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a template took an unknown status';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- An approval with a timestamp and no approver is an approval by nobody.
    BEGIN
        INSERT INTO plt01.ntf_templates
            (tenant_id, template_key, version, category, channel, locale, subject,
             body, variables, status, authored_by, correlation_id, approved_at,
             approved_by, published_at, retired_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'other.thing', 1, 'operational', 'email', 'en', 'S', 'B', ARRAY[]::text[], 'draft', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', now(), NULL, NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a template was approved by nobody';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- **An author cannot approve their own template.** It goes out under the tenant's name to everybody, which is MOD-008's separation of duties applied to content.
    BEGIN
        INSERT INTO plt01.ntf_templates
            (tenant_id, template_key, version, category, channel, locale, subject,
             body, variables, status, authored_by, correlation_id, approved_at,
             approved_by, published_at, retired_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'other.thing', 1, 'operational', 'email', 'en', 'S', 'B', ARRAY[]::text[], 'draft', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', now(), '33333333-3333-4333-8333-333333333333', NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: an author approved their own template';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- Publication requires an approval, which is what makes the approval a control rather than a field.
    BEGIN
        INSERT INTO plt01.ntf_templates
            (tenant_id, template_key, version, category, channel, locale, subject,
             body, variables, status, authored_by, correlation_id, approved_at,
             approved_by, published_at, retired_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'other.thing', 1, 'operational', 'email', 'en', 'S', 'B', ARRAY[]::text[], 'published', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', NULL, NULL, now(), NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a template was published without an approval';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- And the retirement flag and timestamp cannot disagree.
    BEGIN
        INSERT INTO plt01.ntf_templates
            (tenant_id, template_key, version, category, channel, locale, subject,
             body, variables, status, authored_by, correlation_id, approved_at,
             approved_by, published_at, retired_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'other.thing', 1, 'operational', 'email', 'en', 'S', 'B', ARRAY[]::text[], 'retired', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', NULL, NULL, NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a template reads retired with no retirement';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- And nothing else carries a retirement date, so a live template cannot read as withdrawn to anybody auditing what was in use when.
    BEGIN
        INSERT INTO plt01.ntf_templates
            (tenant_id, template_key, version, category, channel, locale, subject,
             body, variables, status, authored_by, correlation_id, approved_at,
             approved_by, published_at, retired_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'other.thing', 2, 'operational', 'email', 'en', 'S', 'B', ARRAY[]::text[], 'published', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', now(), '44444444-4444-4444-8444-444444444444', now(), now());
        RAISE EXCEPTION 'CHECK 60 FAILED: a published template carried a retirement date';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- An approval is a moment and a person together. The sibling case nulls both, so the half that says an approver with no timestamp is refused had no evidence -- and that half is what keeps `approved_by` from reading as an approval nobody dated.
    BEGIN
        INSERT INTO plt01.ntf_templates
            (tenant_id, template_key, version, category, channel, locale, subject,
             body, variables, status, authored_by, correlation_id, approved_at,
             approved_by, published_at, retired_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'other.thing', 3, 'operational', 'email', 'en', 'S', 'B', ARRAY[]::text[], 'draft', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', NULL, '44444444-4444-4444-8444-444444444444', NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a template carried an approver with no approval time';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- One row per key and version.
    BEGIN
        INSERT INTO plt01.ntf_templates
            (tenant_id, template_key, version, category, channel, locale, subject,
             body, variables, status, authored_by, correlation_id, approved_at,
             approved_by, published_at, retired_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'invoice.issued', 1, 'transactional', 'email', 'en', 'S', 'B', ARRAY[]::text[], 'draft', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', NULL, NULL, NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a second template took the same key and version';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;

    -- **One key is one message, so one key is one category.** A key whose email version is
    -- transactional and whose SMS version is marketing would let a fallback change what the
    -- message is permitted to do: paragraph 2463's separation walked around by sending to the
    -- other channel. The service checks it with a SELECT, which two concurrent creates of a
    -- new key both pass, so the trigger is the control and this is its evidence.
    BEGIN
        INSERT INTO plt01.ntf_templates
            (tenant_id, template_key, version, category, channel, locale, subject,
             body, variables, status, authored_by, correlation_id, approved_at,
             approved_by, published_at, retired_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'invoice.issued', 1, 'marketing', 'sms', 'en', '', 'B', ARRAY[]::text[], 'draft', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', NULL, NULL, NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: one template key carried two categories';
    EXCEPTION
        WHEN restrict_violation THEN NULL;
    END;

    -- A category outside the four.
    BEGIN
        INSERT INTO plt01.ntf_preferences
            (tenant_id, recipient_id, category, channel, allowed, quiet_from,
             quiet_until, quiet_timezone, daily_cap, digest_mode, set_by,
             correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '55555555-5555-4555-8555-555555555555', 'promotional', 'push', true, NULL, NULL, NULL, NULL, 'immediate', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a preference took an unknown category';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A channel outside the five.
    BEGIN
        INSERT INTO plt01.ntf_preferences
            (tenant_id, recipient_id, category, channel, allowed, quiet_from,
             quiet_until, quiet_timezone, daily_cap, digest_mode, set_by,
             correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '55555555-5555-4555-8555-555555555555', 'coaching', 'fax', true, NULL, NULL, NULL, NULL, 'immediate', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a preference took an unknown channel';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A digest mode outside the three the decision reads.
    BEGIN
        INSERT INTO plt01.ntf_preferences
            (tenant_id, recipient_id, category, channel, allowed, quiet_from,
             quiet_until, quiet_timezone, daily_cap, digest_mode, set_by,
             correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '55555555-5555-4555-8555-555555555555', 'coaching', 'push', true, NULL, NULL, NULL, NULL, 'weekly', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a preference took an unknown digest mode';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A negative cap would refuse everything including the first message.
    BEGIN
        INSERT INTO plt01.ntf_preferences
            (tenant_id, recipient_id, category, channel, allowed, quiet_from,
             quiet_until, quiet_timezone, daily_cap, digest_mode, set_by,
             correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '55555555-5555-4555-8555-555555555555', 'coaching', 'push', true, NULL, NULL, NULL, -1, 'immediate', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a negative daily cap was stored';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- Quiet hours need both ends: one alone is a window with no other side.
    BEGIN
        INSERT INTO plt01.ntf_preferences
            (tenant_id, recipient_id, category, channel, allowed, quiet_from,
             quiet_until, quiet_timezone, daily_cap, digest_mode, set_by,
             correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '55555555-5555-4555-8555-555555555555', 'coaching', 'push', true, TIME '22:00', NULL, NULL, NULL, 'immediate', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: quiet hours were stored with one end';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- And a timezone, because a quiet hour in the server's zone is a quiet hour for nobody -- this module has no person record to read one from.
    BEGIN
        INSERT INTO plt01.ntf_preferences
            (tenant_id, recipient_id, category, channel, allowed, quiet_from,
             quiet_until, quiet_timezone, daily_cap, digest_mode, set_by,
             correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '55555555-5555-4555-8555-555555555555', 'coaching', 'push', true, TIME '22:00', TIME '07:00', NULL, NULL, 'immediate', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: quiet hours were stored with no timezone';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- **Only an optional category may be switched off.** A member who mutes marketing still gets their invoice: a preference that could suppress a transactional message would mean a tenant unable to tell somebody their payment failed.
    BEGIN
        INSERT INTO plt01.ntf_preferences
            (tenant_id, recipient_id, category, channel, allowed, quiet_from,
             quiet_until, quiet_timezone, daily_cap, digest_mode, set_by,
             correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '55555555-5555-4555-8555-555555555555', 'transactional', 'push', false, NULL, NULL, NULL, NULL, 'immediate', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a transactional notification was switched off by a preference';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- One preference per recipient, category and channel.
    BEGIN
        INSERT INTO plt01.ntf_preferences
            (tenant_id, recipient_id, category, channel, allowed, quiet_from,
             quiet_until, quiet_timezone, daily_cap, digest_mode, set_by,
             correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '55555555-5555-4555-8555-555555555555', 'marketing', 'email', true, NULL, NULL, NULL, NULL, 'immediate', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a second preference took the same slot';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;

    -- A channel outside the five.
    BEGIN
        INSERT INTO plt01.ntf_channel_policies
            (tenant_id, channel, enabled, fallback_channel, cost_per_message_minor,
             currency, set_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'fax', true, NULL, NULL, NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a channel policy named an unknown channel';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A fallback to itself is a loop that sends nothing.
    BEGIN
        INSERT INTO plt01.ntf_channel_policies
            (tenant_id, channel, enabled, fallback_channel, cost_per_message_minor,
             currency, set_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'sms', true, 'sms', NULL, NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a channel fell back to itself';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A fallback outside the five.
    BEGIN
        INSERT INTO plt01.ntf_channel_policies
            (tenant_id, channel, enabled, fallback_channel, cost_per_message_minor,
             currency, set_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'sms', true, 'fax', NULL, NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a channel fell back to an unknown channel';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A cost needs its currency, or it is a number with no unit.
    BEGIN
        INSERT INTO plt01.ntf_channel_policies
            (tenant_id, channel, enabled, fallback_channel, cost_per_message_minor,
             currency, set_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'sms', true, NULL, 12, NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a cost was stored with no currency';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A negative cost would make a margin report read as income.
    BEGIN
        INSERT INTO plt01.ntf_channel_policies
            (tenant_id, channel, enabled, fallback_channel, cost_per_message_minor,
             currency, set_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'sms', true, NULL, -1, 'EUR', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a negative message cost was stored';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A currency that is not three upper-case letters cannot be grouped.
    BEGIN
        INSERT INTO plt01.ntf_channel_policies
            (tenant_id, channel, enabled, fallback_channel, cost_per_message_minor,
             currency, set_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'sms', true, NULL, 12, 'eur', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a malformed currency was stored';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- One policy per channel.
    BEGIN
        INSERT INTO plt01.ntf_channel_policies
            (tenant_id, channel, enabled, fallback_channel, cost_per_message_minor,
             currency, set_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'email', true, NULL, NULL, NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a second policy took the same channel';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;

    -- A category outside the four.
    BEGIN
        INSERT INTO plt01.ntf_notifications
            (tenant_id, template_id, template_key, template_version, category, channel,
             locale, rendered_subject, rendered_body, recipient_id, address_digest,
             priority, bypass_policy_ref, status, decision_reason, consent_record_id,
             idempotency_key, scheduled_for, requested_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000001', 'invoice.issued', 1, 'promotional', 'email', 'en', 'S', 'B', '55555555-5555-4555-8555-555555555555', repeat('9', 64), 'normal', NULL, 'requested',
                'r', NULL, 'case-1', NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a notification took an unknown category';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A channel outside the five.
    BEGIN
        INSERT INTO plt01.ntf_notifications
            (tenant_id, template_id, template_key, template_version, category, channel,
             locale, rendered_subject, rendered_body, recipient_id, address_digest,
             priority, bypass_policy_ref, status, decision_reason, consent_record_id,
             idempotency_key, scheduled_for, requested_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000001', 'invoice.issued', 1, 'transactional', 'fax', 'en', '', 'B', '55555555-5555-4555-8555-555555555555', repeat('9', 64), 'normal', NULL, 'requested',
                'r', NULL, 'case-1', NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a notification took an unknown channel';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A malformed locale.
    BEGIN
        INSERT INTO plt01.ntf_notifications
            (tenant_id, template_id, template_key, template_version, category, channel,
             locale, rendered_subject, rendered_body, recipient_id, address_digest,
             priority, bypass_policy_ref, status, decision_reason, consent_record_id,
             idempotency_key, scheduled_for, requested_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000001', 'invoice.issued', 1, 'transactional', 'email', 'English', 'S', 'B', '55555555-5555-4555-8555-555555555555', repeat('9', 64), 'normal', NULL, 'requested',
                'r', NULL, 'case-1', NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a notification took a malformed locale';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A priority outside the three the decision reads.
    BEGIN
        INSERT INTO plt01.ntf_notifications
            (tenant_id, template_id, template_key, template_version, category, channel,
             locale, rendered_subject, rendered_body, recipient_id, address_digest,
             priority, bypass_policy_ref, status, decision_reason, consent_record_id,
             idempotency_key, scheduled_for, requested_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000001', 'invoice.issued', 1, 'transactional', 'email', 'en', 'S', 'B', '55555555-5555-4555-8555-555555555555', repeat('9', 64), 'urgent', NULL, 'requested',
                'r', NULL, 'case-1', NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a notification took an unknown priority';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A status outside the five.
    BEGIN
        INSERT INTO plt01.ntf_notifications
            (tenant_id, template_id, template_key, template_version, category, channel,
             locale, rendered_subject, rendered_body, recipient_id, address_digest,
             priority, bypass_policy_ref, status, decision_reason, consent_record_id,
             idempotency_key, scheduled_for, requested_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000001', 'invoice.issued', 1, 'transactional', 'email', 'en', 'S', 'B', '55555555-5555-4555-8555-555555555555', repeat('9', 64), 'normal', NULL, 'queued',
                'r', NULL, 'case-1', NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a notification took an unknown status';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A message with no body.
    BEGIN
        INSERT INTO plt01.ntf_notifications
            (tenant_id, template_id, template_key, template_version, category, channel,
             locale, rendered_subject, rendered_body, recipient_id, address_digest,
             priority, bypass_policy_ref, status, decision_reason, consent_record_id,
             idempotency_key, scheduled_for, requested_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000001', 'invoice.issued', 1, 'transactional', 'email', 'en', 'S', '  ', '55555555-5555-4555-8555-555555555555', repeat('9', 64), 'normal', NULL, 'requested',
                'r', NULL, 'case-1', NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a notification was authored with a blank body';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- An email with no subject, and the same rule as the template's.
    BEGIN
        INSERT INTO plt01.ntf_notifications
            (tenant_id, template_id, template_key, template_version, category, channel,
             locale, rendered_subject, rendered_body, recipient_id, address_digest,
             priority, bypass_policy_ref, status, decision_reason, consent_record_id,
             idempotency_key, scheduled_for, requested_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000001', 'invoice.issued', 1, 'transactional', 'email', 'en', '  ', 'B', '55555555-5555-4555-8555-555555555555', repeat('9', 64), 'normal', NULL, 'requested',
                'r', NULL, 'case-1', NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: an email notification carried no subject';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- **An address where a digest belongs.** The absence of an address column is this module's control; a column that accepted one would make it a naming convention.
    BEGIN
        INSERT INTO plt01.ntf_notifications
            (tenant_id, template_id, template_key, template_version, category, channel,
             locale, rendered_subject, rendered_body, recipient_id, address_digest,
             priority, bypass_policy_ref, status, decision_reason, consent_record_id,
             idempotency_key, scheduled_for, requested_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000001', 'invoice.issued', 1, 'transactional', 'email', 'en', 'S', 'B', '55555555-5555-4555-8555-555555555555', 'member@example.test', 'normal', NULL, 'requested',
                'r', NULL, 'case-1', NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: an address was accepted where a digest belongs';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A blank idempotency key is a request nothing can deduplicate, which is half of paragraph 2464.
    BEGIN
        INSERT INTO plt01.ntf_notifications
            (tenant_id, template_id, template_key, template_version, category, channel,
             locale, rendered_subject, rendered_body, recipient_id, address_digest,
             priority, bypass_policy_ref, status, decision_reason, consent_record_id,
             idempotency_key, scheduled_for, requested_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000001', 'invoice.issued', 1, 'transactional', 'email', 'en', 'S', 'B', '55555555-5555-4555-8555-555555555555', repeat('9', 64), 'normal', NULL, 'requested',
                'r', NULL, '  ', NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a notification was authored with a blank idempotency key';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A decision with no reason recorded is a notification nobody can explain to the member who asks why they never heard anything.
    BEGIN
        INSERT INTO plt01.ntf_notifications
            (tenant_id, template_id, template_key, template_version, category, channel,
             locale, rendered_subject, rendered_body, recipient_id, address_digest,
             priority, bypass_policy_ref, status, decision_reason, consent_record_id,
             idempotency_key, scheduled_for, requested_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000001', 'invoice.issued', 1, 'transactional', 'email', 'en', 'S', 'B', '55555555-5555-4555-8555-555555555555', repeat('9', 64), 'normal', NULL, 'requested',
                '  ', NULL, 'case-1', NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a notification recorded no decision reason';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- **A critical alert names the policy that lets it bypass preferences.** Paragraph 2461 says only under documented policy, and a boolean would be a field every caller sets.
    BEGIN
        INSERT INTO plt01.ntf_notifications
            (tenant_id, template_id, template_key, template_version, category, channel,
             locale, rendered_subject, rendered_body, recipient_id, address_digest,
             priority, bypass_policy_ref, status, decision_reason, consent_record_id,
             idempotency_key, scheduled_for, requested_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000001', 'invoice.issued', 1, 'transactional', 'email', 'en', 'S', 'B', '55555555-5555-4555-8555-555555555555', repeat('9', 64), 'critical', NULL, 'requested',
                'r', NULL, 'case-1', NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a critical notification named no bypass policy';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- And a bypass reference on something that is not critical is a field claiming an authority it does not have.
    BEGIN
        INSERT INTO plt01.ntf_notifications
            (tenant_id, template_id, template_key, template_version, category, channel,
             locale, rendered_subject, rendered_body, recipient_id, address_digest,
             priority, bypass_policy_ref, status, decision_reason, consent_record_id,
             idempotency_key, scheduled_for, requested_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000001', 'invoice.issued', 1, 'transactional', 'email', 'en', 'S', 'B', '55555555-5555-4555-8555-555555555555', repeat('9', 64), 'normal', 'RB-ENG-02#alerts', 'requested',
                'r', NULL, 'case-1', NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a non-critical notification carried a bypass policy';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- **Marketing cites the consent that permitted it.** A marketing notification with no consent record is the separation in paragraph 2463 defeated at the one place it is enforceable.
    BEGIN
        INSERT INTO plt01.ntf_notifications
            (tenant_id, template_id, template_key, template_version, category, channel,
             locale, rendered_subject, rendered_body, recipient_id, address_digest,
             priority, bypass_policy_ref, status, decision_reason, consent_record_id,
             idempotency_key, scheduled_for, requested_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000001', 'invoice.issued', 1, 'marketing', 'email', 'en', 'S', 'B', '55555555-5555-4555-8555-555555555555', repeat('9', 64), 'normal', NULL, 'requested',
                'r', NULL, 'case-1', NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a marketing notification cited no consent';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- **And nothing else may cite one**, which is the direction that stops a transactional receipt riding on a marketing consent and making it read as used. An equality constraint needs a case per side; one case proves half of it.
    BEGIN
        INSERT INTO plt01.ntf_notifications
            (tenant_id, template_id, template_key, template_version, category, channel,
             locale, rendered_subject, rendered_body, recipient_id, address_digest,
             priority, bypass_policy_ref, status, decision_reason, consent_record_id,
             idempotency_key, scheduled_for, requested_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000001', 'invoice.issued', 1, 'transactional', 'email', 'en', 'S', 'B', '55555555-5555-4555-8555-555555555555', repeat('9', 64), 'normal', NULL, 'requested',
                'r', '99999999-0000-4000-8000-000000000004', 'case-cites', NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a transactional notification cited a consent record';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A deferred notification carries the moment it is due, or nothing will ever send it.
    BEGIN
        INSERT INTO plt01.ntf_notifications
            (tenant_id, template_id, template_key, template_version, category, channel,
             locale, rendered_subject, rendered_body, recipient_id, address_digest,
             priority, bypass_policy_ref, status, decision_reason, consent_record_id,
             idempotency_key, scheduled_for, requested_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000001', 'invoice.issued', 1, 'transactional', 'email', 'en', 'S', 'B', '55555555-5555-4555-8555-555555555555', repeat('9', 64), 'normal', NULL, 'deferred',
                'r', NULL, 'case-1', NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a deferred notification carried no schedule';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- **An SMS carries no subject line**, the direction the sibling case leaves open. The template's twin constraint has both sides; the notification's had one, so an email subject travelling on an SMS was undetected -- which is the bug this module's own fallback rework was written to stop producing.
    BEGIN
        INSERT INTO plt01.ntf_notifications
            (tenant_id, template_id, template_key, template_version, category, channel,
             locale, rendered_subject, rendered_body, recipient_id, address_digest,
             priority, bypass_policy_ref, status, decision_reason, consent_record_id,
             idempotency_key, scheduled_for, requested_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000001', 'invoice.issued', 1, 'transactional', 'sms', 'en', 'Your invoice', 'B', '55555555-5555-4555-8555-555555555555', repeat('9', 64), 'normal', NULL, 'requested',
                'r', NULL, 'case-sms-subject', NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: an sms notification carried a subject line';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- One notification per idempotency key, which is the request half of paragraph 2464: a caller that asks twice authors one notification.
    BEGIN
        INSERT INTO plt01.ntf_notifications
            (tenant_id, template_id, template_key, template_version, category, channel,
             locale, rendered_subject, rendered_body, recipient_id, address_digest,
             priority, bypass_policy_ref, status, decision_reason, consent_record_id,
             idempotency_key, scheduled_for, requested_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000001', 'invoice.issued', 1, 'transactional', 'email', 'en', 'S', 'B', '55555555-5555-4555-8555-555555555555', repeat('9', 64), 'normal', NULL, 'requested',
                'r', NULL, 'seed-invoice-1', NULL, '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a second notification took the same idempotency key';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;

    -- A channel outside the five.
    BEGIN
        INSERT INTO plt01.ntf_deliveries
            (tenant_id, notification_id, channel, state, attempts, max_attempts,
             last_error, delivered_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000004', 'fax', 'pending', 0, 5, NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a delivery took an unknown channel';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A state outside the six the machine admits.
    BEGIN
        INSERT INTO plt01.ntf_deliveries
            (tenant_id, notification_id, channel, state, attempts, max_attempts,
             last_error, delivered_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000004', 'sms', 'queued', 0, 5, NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a delivery took an unknown state';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- Attempts past the budget is a delivery that outlived its own retry policy.
    BEGIN
        INSERT INTO plt01.ntf_deliveries
            (tenant_id, notification_id, channel, state, attempts, max_attempts,
             last_error, delivered_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000004', 'sms', 'dead', 6, 5, 'boom', NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a delivery exceeded its own attempt budget';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A failure with no error is a diagnostic nobody can act on.
    BEGIN
        INSERT INTO plt01.ntf_deliveries
            (tenant_id, notification_id, channel, state, attempts, max_attempts,
             last_error, delivered_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000004', 'sms', 'failed', 1, 5, NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a delivery failed with nothing recorded about why';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A delivered message carries the moment it was delivered, and nothing else does.
    BEGIN
        INSERT INTO plt01.ntf_deliveries
            (tenant_id, notification_id, channel, state, attempts, max_attempts,
             last_error, delivered_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000004', 'sms', 'delivered', 1, 5, NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a delivery reads delivered with no delivery time';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- **And nothing but a delivered one carries that time**, so a failure cannot be read off a status page as a success.
    BEGIN
        INSERT INTO plt01.ntf_deliveries
            (tenant_id, notification_id, channel, state, attempts, max_attempts,
             last_error, delivered_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000004', 'sms', 'failed', 1, 5, 'boom', now());
        RAISE EXCEPTION 'CHECK 60 FAILED: a failed delivery carried a delivery time';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A negative attempt count is a budget running backwards. `attempts_sane` is three conjuncts and the sibling case exercises one of them.
    BEGIN
        INSERT INTO plt01.ntf_deliveries
            (tenant_id, notification_id, channel, state, attempts, max_attempts,
             last_error, delivered_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000004', 'sms', 'pending', -1, 5, NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a delivery recorded a negative attempt count';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- And a budget of zero is a delivery that may never be tried, which reads as a message silently dropped rather than as one that failed.
    BEGIN
        INSERT INTO plt01.ntf_deliveries
            (tenant_id, notification_id, channel, state, attempts, max_attempts,
             last_error, delivered_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000004', 'sms', 'pending', 0, 0, NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a delivery took an attempt budget of zero';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- **One delivery per notification and channel.** That uniqueness is the transport half of paragraph 2464: a dispatcher that sent a message, timed out and retried settles the row it already holds.
    BEGIN
        INSERT INTO plt01.ntf_deliveries
            (tenant_id, notification_id, channel, state, attempts, max_attempts,
             last_error, delivered_at)
        VALUES ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-1000-4000-8000-000000000004', 'email', 'pending', 0, 5, NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a second delivery was created for one notification and channel';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;

    -- A channel outside the five.
    BEGIN
        INSERT INTO plt01.ntf_suppressions
            (tenant_id, channel, address_digest, reason, correlation_id, released_at,
             released_by, release_reason, release_correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'fax', repeat('9', 64), 'bounced', '33333333-3333-4333-8333-333333333333', NULL, NULL, NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a suppression took an unknown channel';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- An address where a digest belongs, as above.
    BEGIN
        INSERT INTO plt01.ntf_suppressions
            (tenant_id, channel, address_digest, reason, correlation_id, released_at,
             released_by, release_reason, release_correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'sms', 'member@example.test', 'bounced', '33333333-3333-4333-8333-333333333333', NULL, NULL, NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: an address was accepted where a suppression digest belongs';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A reason outside the three.
    BEGIN
        INSERT INTO plt01.ntf_suppressions
            (tenant_id, channel, address_digest, reason, correlation_id, released_at,
             released_by, release_reason, release_correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'sms', repeat('9', 64), 'disliked', '33333333-3333-4333-8333-333333333333', NULL, NULL, NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a suppression took an unknown reason';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- **Only an unsubscribe may be released.** A bounce or a complaint is the channel's judgement about deliverability, and a tenant that could clear those would be choosing to keep sending to an address that rejected them.
    BEGIN
        INSERT INTO plt01.ntf_suppressions
            (tenant_id, channel, address_digest, reason, correlation_id, released_at,
             released_by, release_reason, release_correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'sms', repeat('9', 64), 'bounced', '33333333-3333-4333-8333-333333333333', now(), '33333333-3333-4333-8333-333333333333', 'we think it is fine now', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a bounce suppression was released';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- And a release carries who and why.
    BEGIN
        INSERT INTO plt01.ntf_suppressions
            (tenant_id, channel, address_digest, reason, correlation_id, released_at,
             released_by, release_reason, release_correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'sms', repeat('9', 64), 'unsubscribed', '33333333-3333-4333-8333-333333333333', now(), NULL, NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a suppression was released by nobody';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- **And the reason is the half that matters, so it has its own case.** The constraint is one disjunction over four columns, and a single case nulling all four proves the `who` and says nothing about the `why` -- MOD-009's `sec_legal_holds_release_reasoned` coalesce finding, which passes a blank string where a null is refused.
    BEGIN
        INSERT INTO plt01.ntf_suppressions
            (tenant_id, channel, address_digest, reason, correlation_id, released_at,
             released_by, release_reason, release_correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'sms', repeat('9', 64), 'unsubscribed', '33333333-3333-4333-8333-333333333333', now(), '33333333-3333-4333-8333-333333333333', '   ', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a suppression was released for no stated reason';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- One live suppression per channel and address: a second would mean a release that cleared one left the other standing.
    BEGIN
        INSERT INTO plt01.ntf_suppressions
            (tenant_id, channel, address_digest, reason, correlation_id, released_at,
             released_by, release_reason, release_correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', 'email', repeat('b', 64), 'bounced', '33333333-3333-4333-8333-333333333333', NULL, NULL, NULL, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a second live suppression took the same address';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;

    -- A category outside the four.
    BEGIN
        INSERT INTO plt01.ntf_digests
            (tenant_id, recipient_id, category, channel, window_start, window_end,
             state, notification_count, closed_at)
        VALUES ('11111111-1111-4111-8111-111111111111', '55555555-5555-4555-8555-555555555555', 'promotional', 'sms', TIMESTAMPTZ '2026-12-01 00:00:00+00', TIMESTAMPTZ '2026-12-02 00:00:00+00', 'open', 0, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a digest took an unknown category';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A channel outside the five.
    BEGIN
        INSERT INTO plt01.ntf_digests
            (tenant_id, recipient_id, category, channel, window_start, window_end,
             state, notification_count, closed_at)
        VALUES ('11111111-1111-4111-8111-111111111111', '55555555-5555-4555-8555-555555555555', 'coaching', 'fax', TIMESTAMPTZ '2026-12-01 00:00:00+00', TIMESTAMPTZ '2026-12-02 00:00:00+00', 'open', 0, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a digest took an unknown channel';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A window that runs backwards covers nothing.
    BEGIN
        INSERT INTO plt01.ntf_digests
            (tenant_id, recipient_id, category, channel, window_start, window_end,
             state, notification_count, closed_at)
        VALUES ('11111111-1111-4111-8111-111111111111', '55555555-5555-4555-8555-555555555555', 'coaching', 'sms', TIMESTAMPTZ '2026-12-02 00:00:00+00', TIMESTAMPTZ '2026-12-01 00:00:00+00', 'open', 0, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a digest window ran backwards';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A state outside the three.
    BEGIN
        INSERT INTO plt01.ntf_digests
            (tenant_id, recipient_id, category, channel, window_start, window_end,
             state, notification_count, closed_at)
        VALUES ('11111111-1111-4111-8111-111111111111', '55555555-5555-4555-8555-555555555555', 'coaching', 'sms', TIMESTAMPTZ '2026-12-01 00:00:00+00', TIMESTAMPTZ '2026-12-02 00:00:00+00', 'draft', 0, now());
        RAISE EXCEPTION 'CHECK 60 FAILED: a digest took an unknown state';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A negative count is a batch with fewer than nothing in it.
    BEGIN
        INSERT INTO plt01.ntf_digests
            (tenant_id, recipient_id, category, channel, window_start, window_end,
             state, notification_count, closed_at)
        VALUES ('11111111-1111-4111-8111-111111111111', '55555555-5555-4555-8555-555555555555', 'coaching', 'sms', TIMESTAMPTZ '2026-12-01 00:00:00+00', TIMESTAMPTZ '2026-12-02 00:00:00+00', 'open', -1, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a digest recorded a negative count';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- An open digest has not been closed, and a closed one has.
    BEGIN
        INSERT INTO plt01.ntf_digests
            (tenant_id, recipient_id, category, channel, window_start, window_end,
             state, notification_count, closed_at)
        VALUES ('11111111-1111-4111-8111-111111111111', '55555555-5555-4555-8555-555555555555', 'coaching', 'sms', TIMESTAMPTZ '2026-12-01 00:00:00+00', TIMESTAMPTZ '2026-12-02 00:00:00+00', 'open', 0, now());
        RAISE EXCEPTION 'CHECK 60 FAILED: a digest reads open and closed at once';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- And a closed digest carries the moment it closed, or the window it batched is unknowable afterwards.
    BEGIN
        INSERT INTO plt01.ntf_digests
            (tenant_id, recipient_id, category, channel, window_start, window_end,
             state, notification_count, closed_at)
        VALUES ('11111111-1111-4111-8111-111111111111', '55555555-5555-4555-8555-555555555555', 'coaching', 'sms', TIMESTAMPTZ '2026-12-03 00:00:00+00', TIMESTAMPTZ '2026-12-04 00:00:00+00', 'closed', 1, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a closed digest recorded no closing time';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A binding on a channel nothing sends over routes a member nowhere.
    BEGIN
        INSERT INTO plt01.ntf_recipient_channels
            (tenant_id, recipient_id, channel, address_digest, bound_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '55555555-5555-4555-8555-555555555556', 'pigeon', repeat('1', 64), '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a binding took an unknown channel';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- **An address where a digest belongs is the thing this module cannot hold.** The shape
    -- check is the control, not a convention: without it the binding table becomes the second
    -- copy of everyone's contact details that the digest design exists to avoid.
    BEGIN
        INSERT INTO plt01.ntf_recipient_channels
            (tenant_id, recipient_id, channel, address_digest, bound_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '55555555-5555-4555-8555-555555555556', 'email', 'alice@tenant-a.test', '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a binding took an address where a digest belongs';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- A rebinding carries who and when, or neither.
    BEGIN
        INSERT INTO plt01.ntf_recipient_channels
            (tenant_id, recipient_id, channel, address_digest, bound_by, correlation_id,
             rebound_at, rebound_by, rebind_reason, rebind_correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '55555555-5555-4555-8555-555555555556', 'email', repeat('1', 64), '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', now(), NULL, 'they changed address', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a binding was moved by nobody';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- And a written reason, which is the half a blank string walks past when the coalesce is
    -- missing -- the same case the suppression release has, for the same reason.
    BEGIN
        INSERT INTO plt01.ntf_recipient_channels
            (tenant_id, recipient_id, channel, address_digest, bound_by, correlation_id,
             rebound_at, rebound_by, rebind_reason, rebind_correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '55555555-5555-4555-8555-555555555556', 'email', repeat('1', 64), '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333', now(), '33333333-3333-4333-8333-333333333333', '  ', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: a binding was moved for no stated reason';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- **One digest belongs to one recipient.** Without this the correspondence holds in one
    -- direction only, and a caller supplying a person id where an identity id was meant binds
    -- the right address to the wrong person with nothing refusing it.
    BEGIN
        INSERT INTO plt01.ntf_recipient_channels
            (tenant_id, recipient_id, channel, address_digest, bound_by, correlation_id)
        VALUES ('11111111-1111-4111-8111-111111111111', '55555555-5555-4555-8555-555555555556', 'email', repeat('9', 64), '33333333-3333-4333-8333-333333333333', '33333333-3333-4333-8333-333333333333');
        RAISE EXCEPTION 'CHECK 60 FAILED: one address digest was bound to two recipients';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;

    -- One open digest per recipient, category, channel and window: two would split a batch that exists to be one message.
    BEGIN
        INSERT INTO plt01.ntf_digests
            (tenant_id, recipient_id, category, channel, window_start, window_end,
             state, notification_count, closed_at)
        VALUES ('11111111-1111-4111-8111-111111111111', '55555555-5555-4555-8555-555555555555', 'coaching', 'email', TIMESTAMPTZ '2026-11-14 00:00:00+00', TIMESTAMPTZ '2026-11-15 00:00:00+00', 'open', 0, NULL);
        RAISE EXCEPTION 'CHECK 60 FAILED: a second open digest took the same window';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;

    -- **A notification belongs to at most one digest**, because two would send it twice -- the
    -- one thing paragraph 2464 forbids. A *second* digest, not the same one: repeating the
    -- same triple is refused by the primary key, so that version of this case proved nothing
    -- about the constraint it names. The mutation sweep is what found it.
    BEGIN
        INSERT INTO plt01.ntf_digests
            (tenant_id, digest_id, recipient_id, category, channel, window_start, window_end)
        VALUES ('11111111-1111-4111-8111-111111111111',
                'aaaaaaaa-1000-4000-8000-00000000000f',
                '55555555-5555-4555-8555-555555555555', 'coaching', 'email',
                TIMESTAMPTZ '2026-12-20 00:00:00+00', TIMESTAMPTZ '2026-12-21 00:00:00+00');
        INSERT INTO plt01.ntf_digest_entries (tenant_id, digest_id, notification_id)
        VALUES ('11111111-1111-4111-8111-111111111111',
                'aaaaaaaa-1000-4000-8000-00000000000f',
                'aaaaaaaa-1000-4000-8000-000000000004');
        RAISE EXCEPTION 'CHECK 60 FAILED: a notification was folded into a second digest';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;
END $$;
ROLLBACK;

\echo 'tenant isolation: 60/60 checks passed'
