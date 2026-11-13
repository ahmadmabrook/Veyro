-- MOD-006 PLT-03-R01 platform track: the SaaS plan catalogue Veyro sells itself on.
--
-- This is platform state, not tenant state, so it sits in `plt01_platform` with no row-level
-- security and no grant to either runtime role -- the same boundary `0002_tenant_registry.sql`
-- draws, for the same reason: a tenant-facing connection must not be able to reach it at all.
--
-- **A published plan version is immutable, and the privilege layer is what makes that true.**
-- `saas_prices` and `saas_plan_entitlements` carry no UPDATE grant whatsoever, and `saas_plans`
-- carries a column-level UPDATE on the three lifecycle columns only. The money, the interval,
-- the trial length and the entitlement limits therefore cannot be edited after the fact by any
-- code path, including a mistaken one. Changing what a plan costs means publishing a new
-- `plan_version`; subscriptions already sold stay on the version they were sold on.
--
-- That matters because an invoice is evidence. If today's catalogue could be edited, last
-- quarter's invoice could no longer be reconstructed from the rows that produced it, and
-- "financial correctness" would rest on nobody having run the wrong UPDATE.

CREATE TABLE plt01_platform.saas_plans (
    plan_code text NOT NULL,
    plan_version bigint NOT NULL,
    edition text NOT NULL,
    status text NOT NULL DEFAULT 'draft',
    currency text NOT NULL,
    region text NOT NULL,
    billing_interval text NOT NULL,
    contract_months integer,
    base_price_minor bigint NOT NULL,
    trial_days integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    retired_at timestamptz,
    PRIMARY KEY (plan_code, plan_version),
    CONSTRAINT saas_plans_code_shape CHECK (plan_code ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    CONSTRAINT saas_plans_version_positive CHECK (plan_version > 0),
    CONSTRAINT saas_plans_status CHECK (status IN ('draft', 'published', 'retired')),
    -- ISO 4217 shape only. The set of currencies Veyro actually sells in is a commercial
    -- decision the sources do not state, so it is not invented here.
    CONSTRAINT saas_plans_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT saas_plans_interval CHECK (billing_interval IN ('monthly', 'annual', 'contract')),
    -- Money is stored in integer minor units throughout this module. No column anywhere is
    -- floating point: 0.1 + 0.2 is not 0.3 in binary floating point, and an invoice that is a
    -- cent out is a defect whatever its cause.
    CONSTRAINT saas_plans_price_not_negative CHECK (base_price_minor >= 0),
    CONSTRAINT saas_plans_trial_not_negative CHECK (trial_days >= 0),
    CONSTRAINT saas_plans_contract_months CHECK (
        (billing_interval = 'contract') = (contract_months IS NOT NULL)
        AND (contract_months IS NULL OR contract_months > 0)
    ),
    CONSTRAINT saas_plans_published_at CHECK
        (status = 'draft' OR published_at IS NOT NULL),
    CONSTRAINT saas_plans_retired_at CHECK
        ((status = 'retired') = (retired_at IS NOT NULL))
);

CREATE TABLE plt01_platform.saas_prices (
    price_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_code text NOT NULL,
    plan_version bigint NOT NULL,
    price_code text NOT NULL,
    kind text NOT NULL,
    meter_code text,
    unit text,
    unit_price_minor bigint NOT NULL,
    included_quantity bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (plan_code, plan_version)
        REFERENCES plt01_platform.saas_plans (plan_code, plan_version),
    UNIQUE (plan_code, plan_version, price_code),
    CONSTRAINT saas_prices_kind CHECK (kind IN ('base', 'addon', 'overage')),
    -- An overage price that names no meter cannot be applied to anything, so the row would be
    -- a priced line nobody could ever bill or explain.
    CONSTRAINT saas_prices_overage_needs_meter CHECK (kind <> 'overage' OR meter_code IS NOT NULL),
    CONSTRAINT saas_prices_amount_not_negative CHECK (unit_price_minor >= 0),
    CONSTRAINT saas_prices_included_not_negative CHECK (included_quantity >= 0)
);

CREATE TABLE plt01_platform.saas_plan_entitlements (
    plan_code text NOT NULL,
    plan_version bigint NOT NULL,
    feature_code text NOT NULL,
    limit_value bigint,
    unlimited boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (plan_code, plan_version, feature_code),
    FOREIGN KEY (plan_code, plan_version)
        REFERENCES plt01_platform.saas_plans (plan_code, plan_version),
    -- Exactly one of the two says what the limit is. A row that is both unlimited and capped,
    -- or neither, has no reading, and an entitlement check would have to guess.
    CONSTRAINT saas_plan_entitlements_limit_shape CHECK (
        (unlimited AND limit_value IS NULL)
        OR (NOT unlimited AND limit_value IS NOT NULL AND limit_value >= 0)
    )
);

-- Lifecycle columns only. Price terms and entitlement limits have no UPDATE path at all.
GRANT SELECT, INSERT ON plt01_platform.saas_plans TO veyro_cp_platform;
GRANT UPDATE (status, published_at, retired_at)
    ON plt01_platform.saas_plans TO veyro_cp_platform;
GRANT SELECT, INSERT ON plt01_platform.saas_prices TO veyro_cp_platform;
GRANT SELECT, INSERT ON plt01_platform.saas_plan_entitlements TO veyro_cp_platform;
