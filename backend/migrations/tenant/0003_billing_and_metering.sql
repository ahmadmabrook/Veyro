-- MOD-006 PLT-03-R02..R06 tenant track: subscriptions, entitlements, metering and invoices.
--
-- Protections are the four documented at the head of `0001_organization_hierarchy.sql`. What
-- follows is only what is specific to money, because money fails differently from the rest of
-- the product: a wrong row is not a bug a user reports, it is a number somebody is charged.
--
-- **Every amount is an integer in minor units.** There is no floating-point column in this file.
-- A `numeric` would be exact too, but minor units make the unit unambiguous at every boundary --
-- `1250` in a JSON body cannot be read as twelve and a half of anything -- and they are what the
-- payment providers this module will eventually talk to expect.
--
-- **Five tables are insert-only in the privilege layer**: `bil_subscription_changes`,
-- `bil_usage_records`, `bil_invoices`, `bil_invoice_lines` and `bil_credit_notes`. Neither
-- runtime role holds UPDATE or DELETE on any of them. An invoice therefore has no draft state in
-- the database at all -- a row exists only once the invoice is issued, and a correction is a
-- credit note, never an edit. That is how a ledger works, and it means the question "what did we
-- charge them in March" has exactly one answer forever.
--
-- **There is no subscription without a plan snapshot.** `plan_code`, `plan_version` and `terms`
-- record what was sold. The catalogue lives in the other plane (`plt01_platform.saas_plans`) and
-- a tenant-facing connection cannot read it -- the two planes hold no membership in each other,
-- deliberately -- so there is no foreign key here and none is wanted. Even if there were, a
-- catalogue row is the wrong authority for an old invoice: the subscription's snapshot is the
-- contract, and the catalogue is just what is for sale today.

CREATE TABLE plt01.bil_subscriptions (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    subscription_id uuid NOT NULL DEFAULT gen_random_uuid(),
    plan_code text NOT NULL,
    plan_version bigint NOT NULL,
    terms jsonb NOT NULL,
    status text NOT NULL,
    currency text NOT NULL,
    billing_interval text NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    trial_ends_on date,
    started_on date NOT NULL,
    cancelled_on date,
    -- PLT-03-R06 partner/reseller attribution. Basis points, as everywhere in this codebase:
    -- a revenue share written as a percentage cannot express 2.5% without a rounding argument.
    partner_code text,
    revenue_share_bp integer,
    version bigint NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, subscription_id),
    CONSTRAINT bil_subscriptions_status CHECK
        (status IN ('trialing', 'active', 'past_due', 'suspended', 'cancelled')),
    CONSTRAINT bil_subscriptions_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT bil_subscriptions_interval CHECK
        (billing_interval IN ('monthly', 'annual', 'contract')),
    CONSTRAINT bil_subscriptions_period CHECK (period_end > period_start),
    CONSTRAINT bil_subscriptions_cancelled_on CHECK
        ((status = 'cancelled') = (cancelled_on IS NOT NULL)),
    CONSTRAINT bil_subscriptions_trial CHECK
        (status <> 'trialing' OR trial_ends_on IS NOT NULL),
    CONSTRAINT bil_subscriptions_revenue_share CHECK (
        (partner_code IS NULL AND revenue_share_bp IS NULL)
        OR (partner_code IS NOT NULL AND revenue_share_bp BETWEEN 0 AND 10000)
    ),
    CONSTRAINT bil_subscriptions_version_positive CHECK (version > 0)
);
ALTER TABLE plt01.bil_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.bil_subscriptions FORCE ROW LEVEL SECURITY;
CREATE POLICY bil_subscriptions_tenant ON plt01.bil_subscriptions
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- One live subscription per tenant. Cancelled ones stay, so the history of what a tenant was on
-- is never lost, and a second live row cannot be created by a retry or a race.
CREATE UNIQUE INDEX bil_subscriptions_one_live
    ON plt01.bil_subscriptions (tenant_id) WHERE status <> 'cancelled';

CREATE TABLE plt01.bil_subscription_changes (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    change_id uuid NOT NULL DEFAULT gen_random_uuid(),
    subscription_id uuid NOT NULL,
    change_kind text NOT NULL,
    from_plan_code text,
    from_plan_version bigint,
    to_plan_code text,
    to_plan_version bigint,
    from_status text,
    to_status text,
    effective_on date NOT NULL,
    proration_minor bigint NOT NULL DEFAULT 0,
    reason text,
    actor_id uuid NOT NULL,
    correlation_id uuid NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, change_id),
    FOREIGN KEY (tenant_id, subscription_id)
        REFERENCES plt01.bil_subscriptions (tenant_id, subscription_id),
    CONSTRAINT bil_subscription_changes_kind CHECK
        (change_kind IN ('start', 'upgrade', 'downgrade', 'change', 'renew', 'status',
                        'cancel'))
);
ALTER TABLE plt01.bil_subscription_changes ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.bil_subscription_changes FORCE ROW LEVEL SECURITY;
CREATE POLICY bil_subscription_changes_tenant ON plt01.bil_subscription_changes
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE plt01.bil_entitlements (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    entitlement_id uuid NOT NULL DEFAULT gen_random_uuid(),
    subscription_id uuid NOT NULL,
    feature_code text NOT NULL,
    limit_value bigint,
    unlimited boolean NOT NULL DEFAULT false,
    source text NOT NULL DEFAULT 'plan',
    version bigint NOT NULL DEFAULT 1,
    granted_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, entitlement_id),
    FOREIGN KEY (tenant_id, subscription_id)
        REFERENCES plt01.bil_subscriptions (tenant_id, subscription_id),
    UNIQUE (tenant_id, subscription_id, feature_code),
    CONSTRAINT bil_entitlements_source CHECK (source IN ('plan', 'grant')),
    CONSTRAINT bil_entitlements_limit_shape CHECK (
        (unlimited AND limit_value IS NULL)
        OR (NOT unlimited AND limit_value IS NOT NULL AND limit_value >= 0)
    )
);
ALTER TABLE plt01.bil_entitlements ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.bil_entitlements FORCE ROW LEVEL SECURITY;
CREATE POLICY bil_entitlements_tenant ON plt01.bil_entitlements
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE plt01.bil_usage_meters (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    meter_id uuid NOT NULL DEFAULT gen_random_uuid(),
    meter_code text NOT NULL,
    unit text NOT NULL,
    aggregation text NOT NULL DEFAULT 'sum',
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, meter_id),
    UNIQUE (tenant_id, meter_code),
    CONSTRAINT bil_usage_meters_code_shape CHECK (meter_code ~ '^[a-z0-9]+(\.[a-z0-9_]+)+$'),
    -- 'sum' adds every record in the window; 'max' takes the peak (seats, concurrent streams);
    -- 'last' takes the most recent reading (a gauge). Anything else would need a stated rule for
    -- how late events and corrections combine, and the sources state none.
    CONSTRAINT bil_usage_meters_aggregation CHECK (aggregation IN ('sum', 'max', 'last'))
);
ALTER TABLE plt01.bil_usage_meters ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.bil_usage_meters FORCE ROW LEVEL SECURITY;
CREATE POLICY bil_usage_meters_tenant ON plt01.bil_usage_meters
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- PLT-03's first critical control, in one table: "metering records are idempotent, attributable
-- and auditable".
--
--   idempotent   -- UNIQUE (tenant_id, meter_id, idempotency_key). A retried emitter cannot
--                   double-count, and the database is what refuses it rather than a cache.
--   attributable -- actor_id and correlation_id are NOT NULL. Every recorded quantity names who
--                   recorded it and which request it belonged to.
--   auditable    -- insert-only, and `occurred_at` is kept separately from `recorded_at` so a
--                   late event lands in the period it happened in while the audit trail still
--                   shows when it arrived. A correction points at the record it corrects and may
--                   carry a negative quantity; an original may not.
CREATE TABLE plt01.bil_usage_records (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    record_id uuid NOT NULL DEFAULT gen_random_uuid(),
    meter_id uuid NOT NULL,
    idempotency_key text NOT NULL,
    quantity bigint NOT NULL,
    occurred_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    corrects_record_id uuid,
    actor_id uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, record_id),
    FOREIGN KEY (tenant_id, meter_id)
        REFERENCES plt01.bil_usage_meters (tenant_id, meter_id),
    FOREIGN KEY (tenant_id, corrects_record_id)
        REFERENCES plt01.bil_usage_records (tenant_id, record_id),
    UNIQUE (tenant_id, meter_id, idempotency_key),
    CONSTRAINT bil_usage_records_quantity CHECK
        (quantity >= 0 OR corrects_record_id IS NOT NULL),
    CONSTRAINT bil_usage_records_key_not_blank CHECK (length(btrim(idempotency_key)) > 0)
);
ALTER TABLE plt01.bil_usage_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.bil_usage_records FORCE ROW LEVEL SECURITY;
CREATE POLICY bil_usage_records_tenant ON plt01.bil_usage_records
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE INDEX bil_usage_records_window
    ON plt01.bil_usage_records (tenant_id, meter_id, occurred_at);

CREATE TABLE plt01.bil_quotas (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    quota_id uuid NOT NULL DEFAULT gen_random_uuid(),
    meter_id uuid NOT NULL,
    period text NOT NULL,
    limit_quantity bigint NOT NULL,
    overage_allowed boolean NOT NULL DEFAULT false,
    hard_stop boolean NOT NULL DEFAULT false,
    version bigint NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, quota_id),
    FOREIGN KEY (tenant_id, meter_id)
        REFERENCES plt01.bil_usage_meters (tenant_id, meter_id),
    UNIQUE (tenant_id, meter_id, period),
    CONSTRAINT bil_quotas_period CHECK (period IN ('day', 'month', 'billing_period')),
    CONSTRAINT bil_quotas_limit_not_negative CHECK (limit_quantity >= 0),
    -- Billing the overage and refusing the request are opposite answers to exceeding a quota.
    -- A row asserting both has no behaviour, so the caller would have to pick one silently.
    CONSTRAINT bil_quotas_overage_or_stop CHECK (NOT (overage_allowed AND hard_stop))
);
ALTER TABLE plt01.bil_quotas ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.bil_quotas FORCE ROW LEVEL SECURITY;
CREATE POLICY bil_quotas_tenant ON plt01.bil_quotas
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE plt01.bil_invoices (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    invoice_id uuid NOT NULL DEFAULT gen_random_uuid(),
    invoice_number text NOT NULL,
    subscription_id uuid NOT NULL,
    currency text NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    subtotal_minor bigint NOT NULL,
    tax_minor bigint NOT NULL DEFAULT 0,
    tax_rate_bp integer,
    total_minor bigint NOT NULL,
    partner_code text,
    revenue_share_minor bigint NOT NULL DEFAULT 0,
    issued_at timestamptz NOT NULL DEFAULT now(),
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, invoice_id),
    FOREIGN KEY (tenant_id, subscription_id)
        REFERENCES plt01.bil_subscriptions (tenant_id, subscription_id),
    UNIQUE (tenant_id, invoice_number),
    CONSTRAINT bil_invoices_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT bil_invoices_period CHECK (period_end > period_start),
    -- The one arithmetic identity the database can check by itself. Whether the subtotal matches
    -- the lines it cannot see; `bil_invoice_lines` holds that half, and the service and its
    -- tests hold the join between them.
    CONSTRAINT bil_invoices_total CHECK (total_minor = subtotal_minor + tax_minor),
    CONSTRAINT bil_invoices_tax_not_negative CHECK (tax_minor >= 0),
    CONSTRAINT bil_invoices_tax_rate CHECK (tax_rate_bp IS NULL OR tax_rate_bp >= 0),
    CONSTRAINT bil_invoices_revenue_share CHECK (
        (partner_code IS NULL AND revenue_share_minor = 0)
        OR (partner_code IS NOT NULL AND revenue_share_minor >= 0)
    )
);
ALTER TABLE plt01.bil_invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.bil_invoices FORCE ROW LEVEL SECURITY;
CREATE POLICY bil_invoices_tenant ON plt01.bil_invoices
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE plt01.bil_invoice_lines (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    line_id uuid NOT NULL DEFAULT gen_random_uuid(),
    invoice_id uuid NOT NULL,
    line_no integer NOT NULL,
    kind text NOT NULL,
    description text NOT NULL,
    quantity bigint NOT NULL,
    unit_price_minor bigint NOT NULL,
    amount_minor bigint NOT NULL,
    meter_code text,
    PRIMARY KEY (tenant_id, line_id),
    FOREIGN KEY (tenant_id, invoice_id)
        REFERENCES plt01.bil_invoices (tenant_id, invoice_id),
    UNIQUE (tenant_id, invoice_id, line_no),
    CONSTRAINT bil_invoice_lines_kind CHECK
        (kind IN ('base', 'addon', 'overage', 'proration', 'discount')),
    -- Every line multiplies out. Proration and discount lines carry quantity 1 and put the whole
    -- amount in the unit price, so the identity holds for them too and a line whose displayed
    -- numbers do not produce its own total cannot be stored.
    CONSTRAINT bil_invoice_lines_amount CHECK (amount_minor = quantity * unit_price_minor),
    CONSTRAINT bil_invoice_lines_quantity_positive CHECK (quantity > 0),
    -- Only a discount and a proration may be negative. A discount is one by definition; a
    -- proration is negative when a mid-period downgrade credits more than the new plan charges,
    -- which is a real line on a real invoice. A negative base or overage line would mean the
    -- product paid the customer for using it, which is never what was meant.
    CONSTRAINT bil_invoice_lines_sign CHECK
        (unit_price_minor >= 0 OR kind IN ('discount', 'proration'))
);
ALTER TABLE plt01.bil_invoice_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.bil_invoice_lines FORCE ROW LEVEL SECURITY;
CREATE POLICY bil_invoice_lines_tenant ON plt01.bil_invoice_lines
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE plt01.bil_credit_notes (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    credit_note_id uuid NOT NULL DEFAULT gen_random_uuid(),
    credit_note_number text NOT NULL,
    invoice_id uuid NOT NULL,
    amount_minor bigint NOT NULL,
    reason text NOT NULL,
    actor_id uuid NOT NULL,
    correlation_id uuid NOT NULL,
    issued_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, credit_note_id),
    FOREIGN KEY (tenant_id, invoice_id)
        REFERENCES plt01.bil_invoices (tenant_id, invoice_id),
    UNIQUE (tenant_id, credit_note_number),
    -- Stored positive and always read as a reduction. A signed column invites the question of
    -- which sign means which, and the answer would differ between two readers of the same row.
    CONSTRAINT bil_credit_notes_amount_positive CHECK (amount_minor > 0),
    CONSTRAINT bil_credit_notes_reason_not_blank CHECK (length(btrim(reason)) > 0)
);
ALTER TABLE plt01.bil_credit_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.bil_credit_notes FORCE ROW LEVEL SECURITY;
CREATE POLICY bil_credit_notes_tenant ON plt01.bil_credit_notes
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- Mutable registry state: a subscription moves through its lifecycle, entitlements are regranted
-- on a plan change, meters and quotas are configured.
GRANT SELECT, INSERT, UPDATE ON plt01.bil_subscriptions TO veyro_cp_app;
GRANT SELECT, INSERT, UPDATE ON plt01.bil_entitlements TO veyro_cp_app;
GRANT SELECT, INSERT, UPDATE ON plt01.bil_usage_meters TO veyro_cp_app;
GRANT SELECT, INSERT, UPDATE ON plt01.bil_quotas TO veyro_cp_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON plt01.bil_subscriptions TO veyro_cp_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON plt01.bil_entitlements TO veyro_cp_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON plt01.bil_usage_meters TO veyro_cp_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON plt01.bil_quotas TO veyro_cp_worker;

-- The ledger. No UPDATE and no DELETE for either runtime role, so a charge, a metered quantity
-- and a credit cannot be revised after the fact by any code path. Checks 24 to 26 in
-- backend/tests/sql/isolation.sql prove the grants rather than trusting this comment.
GRANT SELECT, INSERT ON plt01.bil_subscription_changes TO veyro_cp_app;
GRANT SELECT, INSERT ON plt01.bil_subscription_changes TO veyro_cp_worker;
GRANT SELECT, INSERT ON plt01.bil_usage_records TO veyro_cp_app;
GRANT SELECT, INSERT ON plt01.bil_usage_records TO veyro_cp_worker;
GRANT SELECT, INSERT ON plt01.bil_invoices TO veyro_cp_app;
GRANT SELECT, INSERT ON plt01.bil_invoices TO veyro_cp_worker;
GRANT SELECT, INSERT ON plt01.bil_invoice_lines TO veyro_cp_app;
GRANT SELECT, INSERT ON plt01.bil_invoice_lines TO veyro_cp_worker;
GRANT SELECT, INSERT ON plt01.bil_credit_notes TO veyro_cp_app;
GRANT SELECT, INSERT ON plt01.bil_credit_notes TO veyro_cp_worker;
