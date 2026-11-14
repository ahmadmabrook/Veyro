-- MOD-011 REL-02: metric points, objectives, synthetic checks, capacity forecasts and cost
-- allocation. Tables are module-prefixed `ops_` as the other tenant modules are.
--
-- Every table repeats the four protections documented at the head of
-- `0001_organization_hierarchy.sql`: tenant-leading primary key, ENABLE plus FORCE row level
-- security, the `current_setting('app.tenant_id', true)` predicate that is NULL when no context
-- is set, and composite foreign keys carrying `tenant_id` into every parent -- including the
-- reference to `plt01_platform.tenants`, which two earlier modules carried and no check proved
-- until a reviewer pointed it out.
--
-- Five decisions are specific to this module.
--
--   * **Metric points are insert-only and pre-bucketed.** One row per (metric, bucket,
--     dimensions), with a count and a total, and the bucket is an hour. That is not a time-series
--     database and does not pretend to be: there are no percentiles, so a performance budget
--     stated as a p95 cannot be evaluated here and `app/observability/objectives.py` refuses to
--     evaluate one rather than quietly comparing a mean to it. A counter's rate and a duration's
--     mean are both available from count and total, which is what the objectives this build can
--     actually check are expressed in.
--
--   * **The metric catalogue is in code**, as MOD-008's permissions and MOD-010's event types
--     are. `app/observability/catalog.py` declares each metric's kind, unit, owner and dimension
--     names, and validates every point before it is written. The dimension rule is the whole of
--     TSD paragraph 3508's "logs are not a shadow database" that this module can mechanise: a
--     dimension may not be a field MOD-008 classifies as restricted, and a dimension whose
--     values are not a closed set has to carry a written argument for being unbounded.
--
--   * **Cost is an input, not an observation.** There is no cloud bill, no AI invoice and no
--     messaging statement in this repository, so `ops_cost_records` records figures a caller
--     supplies -- exactly as `app.billing.service.issue_invoice` takes a tax rate it cannot
--     derive. What is built is the ledger, the budget, the burn arithmetic and the alert; what is
--     absent is any feed, and a module that invented one would be reporting a margin nobody
--     measured.
--
--   * **A synthetic check is registered here and run elsewhere.** TSD paragraph 3501 wants
--     probes against login, search, booking, payment and check-in. Running them needs a prober
--     outside this process; `ops_synthetic_checks` is the registry and `ops_synthetic_results` is
--     the insert-only ledger a prober writes to. Nothing in this build runs one, and nothing
--     writes a result that did not come from a caller -- a row saying "passed" that no probe
--     produced is the fabricated-evidence shape this codebase has already been bitten by twice.
--
--   * **An objective is a threshold on a metric over a window**, and SLOs and performance
--     budgets are the same shape with different names: both say "this series, compared this way,
--     against this number, over this long". One table with a `kind` rather than two tables that
--     would drift. The comparison is explicit because "better" is upward for an availability
--     ratio and downward for a latency.

-- ---------------------------------------------------------------- metric points

CREATE TABLE plt01.ops_metric_points (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    point_id uuid NOT NULL DEFAULT gen_random_uuid(),
    metric_key text NOT NULL,
    -- The hour this point covers, truncated by the service. A bucket rather than a timestamp
    -- because one row per observation is a shadow database by volume alone.
    bucket_start timestamptz NOT NULL,
    dimensions jsonb NOT NULL DEFAULT '{}'::jsonb,
    -- `observations` and `total` together give a count, a rate and a mean. A gauge writes
    -- `observations = 1` and reads `total` as the level, which is why the columns are named for
    -- what they hold rather than for a kind.
    observations bigint NOT NULL,
    total numeric NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, point_id),
    CONSTRAINT ops_metric_key_shape
        CHECK (metric_key ~ '^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*)+$'),
    CONSTRAINT ops_metric_observations_positive CHECK (observations > 0),
    CONSTRAINT ops_metric_dimensions_is_an_object
        CHECK (jsonb_typeof(dimensions) = 'object'),
    -- The bucket is the hour, so a point whose start is not on the hour would aggregate with
    -- nothing and read as a gap.
    CONSTRAINT ops_metric_bucket_is_hourly
        CHECK (bucket_start = date_trunc('hour', bucket_start))
);
-- The read path: one series over a window, optionally sliced by dimension.
CREATE INDEX ops_metric_points_series
    ON plt01.ops_metric_points (tenant_id, metric_key, bucket_start);
-- One row per (metric, bucket, dimensions). The service adds to the existing row rather than
-- appending a second, so a series is a sum over buckets and not over duplicates -- and the
-- uniqueness is what makes `ON CONFLICT ... DO UPDATE` the increment rather than a race.
CREATE UNIQUE INDEX ops_metric_points_bucket
    ON plt01.ops_metric_points (tenant_id, metric_key, bucket_start, dimensions);
ALTER TABLE plt01.ops_metric_points ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ops_metric_points FORCE ROW LEVEL SECURITY;
CREATE POLICY ops_metric_points_tenant ON plt01.ops_metric_points
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- objectives

-- SLOs (DefineSLI, SetSLO) and performance budgets, which are the same shape. Retired, never
-- deleted: an objective that was in force when something breached it is the thing somebody will
-- ask about, and a row that can vanish cannot answer.
CREATE TABLE plt01.ops_objectives (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    objective_id uuid NOT NULL DEFAULT gen_random_uuid(),
    objective_key text NOT NULL,
    kind text NOT NULL,
    metric_key text NOT NULL,
    comparison text NOT NULL,
    threshold numeric NOT NULL,
    window_hours integer NOT NULL,
    -- How the window is reduced to the one number the threshold is compared against. Stored
    -- rather than derived from the metric's kind, because the same series answers different
    -- questions: a counter's `sum` is a volume and its `rate_per_hour` is a load, and an
    -- objective that meant one and got the other reads as a verdict either way. The closed set
    -- is what `app/observability/objectives.py` can compute from an observation count and a
    -- total -- which excludes every percentile, and that refusal is the point.
    aggregate_as text NOT NULL,
    -- **Which series.** A metric's dimensions are declared in `app/observability/catalog.py`,
    -- and an objective names the exact set it is about -- every declared dimension, with a
    -- value. Without this an objective on `events.delivery_success` aggregates every consumer
    -- together, so one consumer failing totally is invisible behind nine healthy ones and a
    -- breach pages somebody with no way to tell which consumer failed. That is the merge
    -- `metrics.series` already refuses for a partial dimension match, applied one level up;
    -- found by review, where ten thousand successes hid a consumer sitting at zero.
    --
    -- An objective "across all consumers" is therefore not expressible, deliberately: the
    -- merged number measures nothing anybody defined.
    dimensions jsonb NOT NULL DEFAULT '{}'::jsonb,
    -- Who answers for it, per TSD paragraph 3506's "alert routing with ownership, runbook and
    -- escalation". A free-text owner rather than a foreign key because the owner is a team, and
    -- there is no team table in this build; the runbook is a reference somebody can follow.
    owner text NOT NULL,
    runbook_ref text NOT NULL,
    set_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    set_at timestamptz NOT NULL DEFAULT now(),
    retired_at timestamptz,
    retired_by uuid,
    retire_correlation_id uuid,
    PRIMARY KEY (tenant_id, objective_id),
    CONSTRAINT ops_objectives_key_shape
        CHECK (objective_key ~ '^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*)*$'),
    CONSTRAINT ops_objectives_metric_shape
        CHECK (metric_key ~ '^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*)+$'),
    CONSTRAINT ops_objectives_kind CHECK (kind IN ('slo', 'performance_budget')),
    -- Which direction is "good". An availability ratio wants `at_least`; a latency wants
    -- `at_most`. Deriving it from the kind would be wrong for both: an SLO on error rate is
    -- `at_most` and a performance budget on throughput is `at_least`.
    CONSTRAINT ops_objectives_comparison CHECK (comparison IN ('at_least', 'at_most')),
    CONSTRAINT ops_objectives_aggregate
        CHECK (aggregate_as IN ('sum', 'rate_per_hour', 'mean', 'last')),
    CONSTRAINT ops_objectives_dimensions_is_an_object
        CHECK (jsonb_typeof(dimensions) = 'object'),
    CONSTRAINT ops_objectives_window_sane CHECK (window_hours BETWEEN 1 AND 8760),
    CONSTRAINT ops_objectives_owner_not_blank CHECK (owner ~ '[^[:space:]]'),
    -- Paragraph 3509: "alerts must be actionable, owned and tied to user/business impact". A
    -- runbook reference is the actionable half, and an objective with none produces an alert
    -- whose recipient has nothing to do.
    CONSTRAINT ops_objectives_runbook_not_blank CHECK (runbook_ref ~ '[^[:space:]]'),
    CONSTRAINT ops_objectives_retirement_attributed CHECK (
        (retired_at IS NULL AND retired_by IS NULL AND retire_correlation_id IS NULL)
        OR (retired_at IS NOT NULL AND retired_by IS NOT NULL
            AND retire_correlation_id IS NOT NULL))
);
CREATE UNIQUE INDEX ops_objectives_live_key
    ON plt01.ops_objectives (tenant_id, objective_key) WHERE retired_at IS NULL;
ALTER TABLE plt01.ops_objectives ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ops_objectives FORCE ROW LEVEL SECURITY;
CREATE POLICY ops_objectives_tenant ON plt01.ops_objectives
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- synthetic checks

CREATE TABLE plt01.ops_synthetic_checks (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    check_id uuid NOT NULL DEFAULT gen_random_uuid(),
    check_key text NOT NULL,
    -- What the probe exercises, in words. Not a URL: a URL in a tenant-writable column that
    -- something later fetches is a request-forgery primitive, and nothing in this build fetches
    -- anything. A prober that grows one needs its own allowlist, not this column.
    description text NOT NULL,
    workflow text NOT NULL,
    interval_seconds integer NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    registered_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    registered_at timestamptz NOT NULL DEFAULT now(),
    disabled_at timestamptz,
    disabled_by uuid,
    disable_correlation_id uuid,
    PRIMARY KEY (tenant_id, check_id),
    UNIQUE (tenant_id, check_key),
    CONSTRAINT ops_synthetic_key_shape
        CHECK (check_key ~ '^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*)*$'),
    -- The workflows paragraph 3501 names. A closed set, because a check against a workflow the
    -- product does not have is a check nothing can ever run.
    CONSTRAINT ops_synthetic_workflow CHECK (workflow IN (
        'login', 'member_search', 'booking', 'payment', 'pos', 'check_in', 'webhook',
        'messaging')),
    CONSTRAINT ops_synthetic_description_not_blank CHECK (description ~ '[^[:space:]]'),
    CONSTRAINT ops_synthetic_interval_sane
        CHECK (interval_seconds BETWEEN 30 AND 86400),
    CONSTRAINT ops_synthetic_enabled_consistent CHECK (enabled = (disabled_at IS NULL)),
    CONSTRAINT ops_synthetic_disable_attributed CHECK (
        (disabled_at IS NULL AND disabled_by IS NULL AND disable_correlation_id IS NULL)
        OR (disabled_at IS NOT NULL AND disabled_by IS NOT NULL
            AND disable_correlation_id IS NOT NULL))
);
ALTER TABLE plt01.ops_synthetic_checks ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ops_synthetic_checks FORCE ROW LEVEL SECURITY;
CREATE POLICY ops_synthetic_checks_tenant ON plt01.ops_synthetic_checks
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- Insert-only: a probe result is a measurement, and a measurement somebody can revise is not
-- one. The failure detail is capped by the service rather than by a constraint, because a
-- constraint on length would refuse the evidence instead of trimming it.
CREATE TABLE plt01.ops_synthetic_results (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    result_id uuid NOT NULL DEFAULT gen_random_uuid(),
    check_id uuid NOT NULL,
    outcome text NOT NULL,
    duration_ms integer NOT NULL,
    detail text,
    -- Who submitted it, and under which correlation id. Every other insert-only table in this
    -- file carries both, and this is the one whose own module docstring names the risk: a row
    -- saying `passed` that no probe produced. The row cannot be revised, and until this column
    -- existed nothing in the system could say who wrote it -- MOD-009's rule recurring, that
    -- evidence with nobody's name on it answers nothing. An allowed action is not audited by
    -- MOD-008 by design, so there was no second record to fall back on.
    recorded_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    observed_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, result_id),
    FOREIGN KEY (tenant_id, check_id)
        REFERENCES plt01.ops_synthetic_checks (tenant_id, check_id),
    CONSTRAINT ops_synthetic_results_outcome CHECK (outcome IN ('passed', 'failed')),
    CONSTRAINT ops_synthetic_results_duration_sane CHECK (duration_ms >= 0),
    -- A failure with no detail is an alert nobody can act on, which paragraph 3509 forbids.
    -- `coalesce` is load-bearing: `NULL ~ '[^[:space:]]'` is NULL and a CHECK passes on NULL,
    -- which is how MOD-009's legal-hold constraint admitted the row it existed to refuse.
    CONSTRAINT ops_synthetic_results_failure_explained CHECK (
        outcome <> 'failed' OR coalesce(detail, '') ~ '[^[:space:]]')
);
CREATE INDEX ops_synthetic_results_recent
    ON plt01.ops_synthetic_results (tenant_id, check_id, observed_at DESC);
ALTER TABLE plt01.ops_synthetic_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ops_synthetic_results FORCE ROW LEVEL SECURITY;
CREATE POLICY ops_synthetic_results_tenant ON plt01.ops_synthetic_results
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- capacity

-- RecordCapacityForecast. Insert-only, because a forecast is a statement somebody made on a
-- date, and the interesting question later is always what was predicted *then* rather than what
-- the prediction would be now.
CREATE TABLE plt01.ops_capacity_forecasts (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    forecast_id uuid NOT NULL DEFAULT gen_random_uuid(),
    resource text NOT NULL,
    horizon_days integer NOT NULL,
    current_value numeric NOT NULL,
    projected_value numeric NOT NULL,
    -- The capacity the projection is measured against. Stored, not just used: the headroom is
    -- derived from it, and a derived number whose input is thrown away cannot be re-checked
    -- from the row afterwards -- which makes "derived rather than accepted" unverifiable a
    -- month later, when it is the only time anybody asks.
    limit_value numeric,
    headroom_bp integer,
    basis text NOT NULL,
    forecast_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    forecast_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, forecast_id),
    CONSTRAINT ops_capacity_resource_shape CHECK (resource ~ '^[a-z0-9]+(_[a-z0-9]+)*$'),
    CONSTRAINT ops_capacity_horizon_sane CHECK (horizon_days BETWEEN 1 AND 1095),
    CONSTRAINT ops_capacity_values_sane
        CHECK (current_value >= 0 AND projected_value >= 0),
    -- A forecast with no stated basis is a number somebody will treat as a measurement.
    CONSTRAINT ops_capacity_basis_not_blank CHECK (basis ~ '[^[:space:]]'),
    CONSTRAINT ops_capacity_limit_positive CHECK (limit_value IS NULL OR limit_value > 0),
    -- A headroom is derived from the limit, so a projection far past it produces a large
    -- negative number; this bounds it into the column rather than letting the arithmetic
    -- overflow into a 500. -1000000 bp is a projection a hundred times the limit, which is
    -- past every decision anybody would make from it.
    CONSTRAINT ops_capacity_headroom_bounded
        CHECK (headroom_bp IS NULL OR headroom_bp BETWEEN -1000000 AND 10000),
    -- A limit with no headroom, or a headroom with no limit, is a row that cannot say where
    -- its own number came from.
    CONSTRAINT ops_capacity_headroom_follows_limit
        CHECK ((limit_value IS NULL) = (headroom_bp IS NULL))
);
CREATE INDEX ops_capacity_forecasts_recent
    ON plt01.ops_capacity_forecasts (tenant_id, resource, forecast_at DESC);
ALTER TABLE plt01.ops_capacity_forecasts ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ops_capacity_forecasts FORCE ROW LEVEL SECURITY;
CREATE POLICY ops_capacity_forecasts_tenant ON plt01.ops_capacity_forecasts
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- cost and budgets

-- AllocateCost. Insert-only, and in minor units as an integer, because MOD-015's conventions
-- apply to every amount in this repository: no column and no function here is floating point,
-- and a cost that can be revised cannot be reconciled against the bill it came from. A
-- correction is a later row with a negative amount, which is why the amount is signed.
CREATE TABLE plt01.ops_cost_records (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    cost_record_id uuid NOT NULL DEFAULT gen_random_uuid(),
    period_start date NOT NULL,
    period_end date NOT NULL,
    -- The dimensions paragraph 3504 names. A closed set: a cost booked against a dimension no
    -- report knows about is a cost that silently does not appear in the margin.
    dimension text NOT NULL,
    dimension_value text NOT NULL,
    currency char(3) NOT NULL,
    amount_minor bigint NOT NULL,
    source text NOT NULL,
    corrects_cost_record_id uuid,
    allocated_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    allocated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, cost_record_id),
    FOREIGN KEY (tenant_id, corrects_cost_record_id)
        REFERENCES plt01.ops_cost_records (tenant_id, cost_record_id),
    CONSTRAINT ops_cost_dimension CHECK (dimension IN (
        'domain', 'environment', 'ai_model', 'messaging', 'storage', 'integration',
        'support', 'compute')),
    CONSTRAINT ops_cost_dimension_value_not_blank
        CHECK (dimension_value ~ '[^[:space:]]'),
    CONSTRAINT ops_cost_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT ops_cost_period_ordered CHECK (period_end >= period_start),
    -- The one place a cost may be zero and not a mistake is a correction that cancels itself,
    -- which is a later row rather than this one.
    CONSTRAINT ops_cost_amount_not_zero CHECK (amount_minor <> 0),
    -- A figure somebody supplied has to say where it came from: there is no cloud bill in this
    -- repository, so provenance is the only thing distinguishing a measurement from a guess.
    CONSTRAINT ops_cost_source_not_blank CHECK (source ~ '[^[:space:]]'),
    CONSTRAINT ops_cost_no_self_correction CHECK (
        corrects_cost_record_id IS NULL OR corrects_cost_record_id <> cost_record_id)
);
CREATE INDEX ops_cost_records_period
    ON plt01.ops_cost_records (tenant_id, period_start, dimension);
ALTER TABLE plt01.ops_cost_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ops_cost_records FORCE ROW LEVEL SECURITY;
CREATE POLICY ops_cost_records_tenant ON plt01.ops_cost_records
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE plt01.ops_budgets (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    budget_id uuid NOT NULL DEFAULT gen_random_uuid(),
    budget_key text NOT NULL,
    dimension text NOT NULL,
    dimension_value text,
    currency char(3) NOT NULL,
    amount_minor bigint NOT NULL,
    period text NOT NULL,
    -- Basis points of the budget at which a burn alert fires, so 8000 is "warn at 80%".
    warn_at_bp integer NOT NULL DEFAULT 8000,
    owner text NOT NULL,
    set_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    set_at timestamptz NOT NULL DEFAULT now(),
    retired_at timestamptz,
    retired_by uuid,
    retire_correlation_id uuid,
    PRIMARY KEY (tenant_id, budget_id),
    CONSTRAINT ops_budgets_key_shape
        CHECK (budget_key ~ '^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*)*$'),
    CONSTRAINT ops_budgets_dimension CHECK (dimension IN (
        'domain', 'environment', 'ai_model', 'messaging', 'storage', 'integration',
        'support', 'compute', 'total')),
    -- A `total` budget covers everything and names no value; any other dimension must name one,
    -- or the budget would match every cost in that dimension and read as a total.
    CONSTRAINT ops_budgets_value_matches_dimension CHECK (
        (dimension = 'total' AND dimension_value IS NULL)
        OR (dimension <> 'total' AND coalesce(dimension_value, '') ~ '[^[:space:]]')),
    CONSTRAINT ops_budgets_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT ops_budgets_amount_positive CHECK (amount_minor > 0),
    CONSTRAINT ops_budgets_period CHECK (period IN ('monthly', 'quarterly', 'annual')),
    CONSTRAINT ops_budgets_warn_sane CHECK (warn_at_bp BETWEEN 1 AND 10000),
    CONSTRAINT ops_budgets_owner_not_blank CHECK (owner ~ '[^[:space:]]'),
    CONSTRAINT ops_budgets_retirement_attributed CHECK (
        (retired_at IS NULL AND retired_by IS NULL AND retire_correlation_id IS NULL)
        OR (retired_at IS NOT NULL AND retired_by IS NOT NULL
            AND retire_correlation_id IS NOT NULL))
);
CREATE UNIQUE INDEX ops_budgets_live_key
    ON plt01.ops_budgets (tenant_id, budget_key) WHERE retired_at IS NULL;
ALTER TABLE plt01.ops_budgets ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ops_budgets FORCE ROW LEVEL SECURITY;
CREATE POLICY ops_budgets_tenant ON plt01.ops_budgets
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- Insert-only. An alert is the record that somebody was told, and TSD paragraph 3509 makes the
-- actionability of an alert a control -- so the row carries the owner and the amount that fired
-- it rather than pointing at a budget whose terms may since have changed. That is MOD-008's
-- snapshot-your-terms finding: terms re-derived at read time are not the terms somebody acted on.
CREATE TABLE plt01.ops_budget_alerts (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    alert_id uuid NOT NULL DEFAULT gen_random_uuid(),
    budget_id uuid NOT NULL,
    period_start date NOT NULL,
    threshold_bp integer NOT NULL,
    spent_minor bigint NOT NULL,
    budget_minor bigint NOT NULL,
    currency char(3) NOT NULL,
    owner text NOT NULL,
    raised_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, alert_id),
    FOREIGN KEY (tenant_id, budget_id) REFERENCES plt01.ops_budgets (tenant_id, budget_id),
    CONSTRAINT ops_budget_alerts_threshold_sane CHECK (threshold_bp BETWEEN 1 AND 100000),
    CONSTRAINT ops_budget_alerts_amounts_sane
        CHECK (spent_minor >= 0 AND budget_minor > 0),
    CONSTRAINT ops_budget_alerts_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT ops_budget_alerts_owner_not_blank CHECK (owner ~ '[^[:space:]]')
);
-- One alert per budget, period and threshold. The second crossing of 80% in a month is not news,
-- and without this an hourly sweep would raise one every hour -- which is how an alert channel
-- becomes something people mute, and a muted alert is worse than none.
CREATE UNIQUE INDEX ops_budget_alerts_once
    ON plt01.ops_budget_alerts (tenant_id, budget_id, period_start, threshold_bp);
ALTER TABLE plt01.ops_budget_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ops_budget_alerts FORCE ROW LEVEL SECURITY;
CREATE POLICY ops_budget_alerts_tenant ON plt01.ops_budget_alerts
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- privileges

-- Metric points accumulate within a bucket, so this is the one table in the module with a real
-- UPDATE -- and it is scoped to the two columns that accumulate. The metric key, the bucket and
-- the dimensions are the identity of the series: a point whose key could change is a
-- measurement that can be moved to another chart.
GRANT SELECT, INSERT ON plt01.ops_metric_points TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (observations, total) ON plt01.ops_metric_points
    TO veyro_cp_app, veyro_cp_worker;

-- An objective and a budget are retired, never edited: changing a threshold under an alert that
-- already fired rewrites the reason it fired.
GRANT SELECT, INSERT ON plt01.ops_objectives TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (retired_at, retired_by, retire_correlation_id) ON plt01.ops_objectives
    TO veyro_cp_app, veyro_cp_worker;
GRANT SELECT, INSERT ON plt01.ops_budgets TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (retired_at, retired_by, retire_correlation_id) ON plt01.ops_budgets
    TO veyro_cp_app, veyro_cp_worker;

-- A check is enabled or disabled; what it probes and how often are what it is.
GRANT SELECT, INSERT ON plt01.ops_synthetic_checks TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (enabled, interval_seconds, disabled_at, disabled_by, disable_correlation_id)
    ON plt01.ops_synthetic_checks TO veyro_cp_app, veyro_cp_worker;

-- Measurements and evidence: insert-only for both runtime roles, with no UPDATE at all. A probe
-- result, a forecast, a cost figure and an alert are each a statement somebody made at a time,
-- and each is worthless if the party being asked about it can revise it. Checks 44 to 48 in
-- backend/tests/sql/isolation.sql compare these grants against the catalogue in full rather
-- than against a list of column names -- which is what MOD-010's review showed a denylist is
-- worth.
GRANT SELECT, INSERT ON plt01.ops_synthetic_results TO veyro_cp_app, veyro_cp_worker;
GRANT SELECT, INSERT ON plt01.ops_capacity_forecasts TO veyro_cp_app, veyro_cp_worker;
GRANT SELECT, INSERT ON plt01.ops_cost_records TO veyro_cp_app, veyro_cp_worker;
GRANT SELECT, INSERT ON plt01.ops_budget_alerts TO veyro_cp_app, veyro_cp_worker;
