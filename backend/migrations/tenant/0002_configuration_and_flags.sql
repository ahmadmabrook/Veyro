-- MOD-005 PLT-02-R01..R06 tenant track: typed configuration, feature flags, kill switches and
-- experiment assignment. Tables are module-prefixed `cfg_` per TSD paragraph 1026.
--
-- Every table repeats the four protections documented at the head of
-- `0001_organization_hierarchy.sql`, and for the same reasons: tenant-leading primary key,
-- ENABLE plus FORCE row level security, the `current_setting('app.tenant_id', true)` predicate
-- that is NULL when no context is set, and composite foreign keys carrying `tenant_id` into
-- every parent. Read that file's comment before changing anything here.
--
-- Two things are specific to this module and worth stating rather than inferring:
--
--   * `cfg_values` and `cfg_exposures` are append-only in the privilege layer -- the runtime
--     roles get SELECT and INSERT and nothing else. PLT-02's required outcome is that "every
--     change is reversible" (TSD paragraph 1021) and its runbook requires "repair without
--     history rewrite" (paragraph 1034). A rollback is therefore a new version whose payload
--     equals an older one, never an UPDATE over the old row, and the database refuses the
--     alternative rather than trusting the service to avoid it.
--   * configuration scope is polymorphic (tenant, brand or location) but is NOT stored as a
--     bare `scope_id`. A bare id could not be foreign-keyed, so containment would rest on
--     application code. Instead `brand_id` and `location_id` are separate nullable columns with
--     their own composite foreign keys, and a CHECK ties exactly one of them to `scope_type`.
--     Cross-tenant and cross-scope rows are then refused by the database.

CREATE TABLE plt01.cfg_definitions (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    definition_id uuid NOT NULL DEFAULT gen_random_uuid(),
    config_key text NOT NULL,
    value_type text NOT NULL,
    default_value jsonb NOT NULL,
    validation jsonb NOT NULL DEFAULT '{}'::jsonb,
    owner_module text NOT NULL,
    description text,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, definition_id),
    UNIQUE (tenant_id, config_key),
    CONSTRAINT cfg_definitions_key_shape CHECK (config_key ~ '^[a-z0-9]+(\.[a-z0-9_]+)+$'),
    CONSTRAINT cfg_definitions_value_type CHECK
        (value_type IN ('boolean', 'integer', 'number', 'string', 'json'))
);
ALTER TABLE plt01.cfg_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.cfg_definitions FORCE ROW LEVEL SECURITY;
CREATE POLICY cfg_definitions_tenant ON plt01.cfg_definitions
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE plt01.cfg_values (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    value_id uuid NOT NULL DEFAULT gen_random_uuid(),
    definition_id uuid NOT NULL,
    scope_type text NOT NULL,
    brand_id uuid,
    location_id uuid,
    value jsonb NOT NULL,
    version bigint NOT NULL,
    rolled_back_from bigint,
    published_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    published_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, value_id),
    FOREIGN KEY (tenant_id, definition_id)
        REFERENCES plt01.cfg_definitions (tenant_id, definition_id),
    FOREIGN KEY (tenant_id, brand_id) REFERENCES plt01.brands (tenant_id, brand_id),
    FOREIGN KEY (tenant_id, location_id) REFERENCES plt01.locations (tenant_id, location_id),
    UNIQUE NULLS NOT DISTINCT (tenant_id, definition_id, scope_type, brand_id, location_id, version),
    CONSTRAINT cfg_values_version_positive CHECK (version > 0),
    CONSTRAINT cfg_values_scope_shape CHECK (
        (scope_type = 'tenant' AND brand_id IS NULL AND location_id IS NULL)
        OR (scope_type = 'brand' AND brand_id IS NOT NULL AND location_id IS NULL)
        OR (scope_type = 'location' AND location_id IS NOT NULL AND brand_id IS NULL)
    )
);
ALTER TABLE plt01.cfg_values ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.cfg_values FORCE ROW LEVEL SECURITY;
CREATE POLICY cfg_values_tenant ON plt01.cfg_values
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE plt01.cfg_flags (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    flag_id uuid NOT NULL DEFAULT gen_random_uuid(),
    flag_key text NOT NULL,
    description text,
    enabled boolean NOT NULL DEFAULT false,
    default_variant text NOT NULL DEFAULT 'off',
    kill_switch_engaged boolean NOT NULL DEFAULT false,
    kill_switch_reason text,
    version bigint NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, flag_id),
    UNIQUE (tenant_id, flag_key),
    CONSTRAINT cfg_flags_key_shape CHECK (flag_key ~ '^[a-z0-9]+(\.[a-z0-9_]+)+$'),
    CONSTRAINT cfg_flags_version_positive CHECK (version > 0),
    -- A kill switch that is engaged without a stated reason is an outage nobody can explain
    -- later. PLT-02-R03's switches cover payments, AI actions and hardware; the reason is the
    -- only record of why the capability went dark.
    CONSTRAINT cfg_flags_kill_switch_reasoned CHECK
        (NOT kill_switch_engaged OR kill_switch_reason IS NOT NULL)
);
ALTER TABLE plt01.cfg_flags ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.cfg_flags FORCE ROW LEVEL SECURITY;
CREATE POLICY cfg_flags_tenant ON plt01.cfg_flags
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE plt01.cfg_flag_rules (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    rule_id uuid NOT NULL DEFAULT gen_random_uuid(),
    flag_id uuid NOT NULL,
    priority integer NOT NULL,
    match jsonb NOT NULL DEFAULT '{}'::jsonb,
    rollout_bp integer NOT NULL DEFAULT 10000,
    variant text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    -- Replacing a flag's targeting retires the old rules rather than deleting them, because
    -- `veyro_cp_app` holds no DELETE here (D6.2) and because the previous targeting is the only
    -- record of who was being served what before a change. Evaluation reads live rules only.
    retired_at timestamptz,
    PRIMARY KEY (tenant_id, rule_id),
    FOREIGN KEY (tenant_id, flag_id) REFERENCES plt01.cfg_flags (tenant_id, flag_id),
    -- Basis points, not percent: 10000 is 100.00%. A percentage column cannot express the
    -- fractional rollouts PLT-02-R02 needs without a rounding argument at every call site.
    CONSTRAINT cfg_flag_rules_rollout_range CHECK (rollout_bp BETWEEN 0 AND 10000),
    CONSTRAINT cfg_flag_rules_match_is_object CHECK (jsonb_typeof(match) = 'object')
);
ALTER TABLE plt01.cfg_flag_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.cfg_flag_rules FORCE ROW LEVEL SECURITY;
CREATE POLICY cfg_flag_rules_tenant ON plt01.cfg_flag_rules
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- One live rule per priority per flag. Partial, so retired rules keep their original priority
-- and the history stays readable instead of being renumbered.
CREATE UNIQUE INDEX cfg_flag_rules_live_priority
    ON plt01.cfg_flag_rules (tenant_id, flag_id, priority) WHERE retired_at IS NULL;

CREATE TABLE plt01.cfg_experiments (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    experiment_id uuid NOT NULL DEFAULT gen_random_uuid(),
    experiment_key text NOT NULL,
    status text NOT NULL DEFAULT 'draft',
    -- The salt is fixed when the experiment is created and never changes: changing it would
    -- silently reassign every already-exposed subject, which is the one thing an experiment
    -- must not do.
    salt text NOT NULL,
    version bigint NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    PRIMARY KEY (tenant_id, experiment_id),
    UNIQUE (tenant_id, experiment_key),
    CONSTRAINT cfg_experiments_key_shape CHECK (experiment_key ~ '^[a-z0-9]+(\.[a-z0-9_]+)+$'),
    CONSTRAINT cfg_experiments_status CHECK (status IN ('draft', 'running', 'completed')),
    CONSTRAINT cfg_experiments_version_positive CHECK (version > 0),
    CONSTRAINT cfg_experiments_completed_at CHECK
        ((status = 'completed') = (completed_at IS NOT NULL))
);
ALTER TABLE plt01.cfg_experiments ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.cfg_experiments FORCE ROW LEVEL SECURITY;
CREATE POLICY cfg_experiments_tenant ON plt01.cfg_experiments
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE plt01.cfg_variants (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    variant_id uuid NOT NULL DEFAULT gen_random_uuid(),
    experiment_id uuid NOT NULL,
    variant_key text NOT NULL,
    weight integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, variant_id),
    FOREIGN KEY (tenant_id, experiment_id)
        REFERENCES plt01.cfg_experiments (tenant_id, experiment_id),
    UNIQUE (tenant_id, experiment_id, variant_key),
    CONSTRAINT cfg_variants_weight_positive CHECK (weight > 0)
);
ALTER TABLE plt01.cfg_variants ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.cfg_variants FORCE ROW LEVEL SECURITY;
CREATE POLICY cfg_variants_tenant ON plt01.cfg_variants
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE plt01.cfg_exposures (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    exposure_id uuid NOT NULL DEFAULT gen_random_uuid(),
    experiment_id uuid NOT NULL,
    subject_id text NOT NULL,
    variant_key text NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, exposure_id),
    FOREIGN KEY (tenant_id, experiment_id)
        REFERENCES plt01.cfg_experiments (tenant_id, experiment_id),
    -- One exposure per subject per experiment. Assignment is deterministic, so a repeated call
    -- must return the same variant and must not record a second exposure; this constraint is
    -- what makes that idempotence a property of the data rather than of the caller.
    UNIQUE (tenant_id, experiment_id, subject_id),
    CONSTRAINT cfg_exposures_subject_not_blank CHECK (length(btrim(subject_id)) > 0)
);
ALTER TABLE plt01.cfg_exposures ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.cfg_exposures FORCE ROW LEVEL SECURITY;
CREATE POLICY cfg_exposures_tenant ON plt01.cfg_exposures
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- Definitions, flags, rules, experiments and variants are mutable registry state.
GRANT SELECT, INSERT, UPDATE ON plt01.cfg_definitions TO veyro_cp_app;
GRANT SELECT, INSERT, UPDATE ON plt01.cfg_flags TO veyro_cp_app;
GRANT SELECT, INSERT, UPDATE ON plt01.cfg_flag_rules TO veyro_cp_app;
GRANT SELECT, INSERT, UPDATE ON plt01.cfg_experiments TO veyro_cp_app;
GRANT SELECT, INSERT, UPDATE ON plt01.cfg_variants TO veyro_cp_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON plt01.cfg_definitions TO veyro_cp_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON plt01.cfg_flags TO veyro_cp_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON plt01.cfg_flag_rules TO veyro_cp_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON plt01.cfg_experiments TO veyro_cp_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON plt01.cfg_variants TO veyro_cp_worker;

-- Published configuration versions and recorded exposures are history. No UPDATE and no DELETE
-- for either runtime role, so neither a service bug nor a worker can rewrite what was published
-- or who saw which variant. Checks 19 and 20 in backend/tests/sql/isolation.sql prove it.
GRANT SELECT, INSERT ON plt01.cfg_values TO veyro_cp_app;
GRANT SELECT, INSERT ON plt01.cfg_values TO veyro_cp_worker;
GRANT SELECT, INSERT ON plt01.cfg_exposures TO veyro_cp_app;
GRANT SELECT, INSERT ON plt01.cfg_exposures TO veyro_cp_worker;
