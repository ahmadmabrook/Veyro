-- MOD-010 DAT-01: the transactional outbox, per-consumer delivery with retry and dead-letter,
-- and controlled replay. Tables are module-prefixed `evt_` as the other tenant modules are.
--
-- Every table repeats the four protections documented at the head of
-- `0001_organization_hierarchy.sql`: tenant-leading primary key, ENABLE plus FORCE row level
-- security, the `current_setting('app.tenant_id', true)` predicate that is NULL when no context
-- is set, and composite foreign keys carrying `tenant_id` into every parent. Read that file's
-- comment before changing anything here.
--
-- Five decisions are specific to this module and are stated rather than left to be inferred.
--
--   * **The outbox exists so that state and event commit together.** TSD paragraph 105: "state
--     and outbox commit atomically". That is the entire reason this table is in `plt01` beside
--     the rows it describes rather than in a queue: an event appended in the same transaction as
--     the state change it reports cannot describe a change that was rolled back, and a change
--     that committed cannot fail to produce its event. `app.events.service.append_event` takes a
--     **connection**, not a pool, which is unlike every other service in this repository and is
--     the mechanism behind that sentence. A version that took a pool would open its own
--     transaction and the guarantee would be gone while the code still read as though it held.
--
--   * **Dispatch state is separate from the event.** TSD paragraph 3253: "dispatched-at state
--     does not change business payload". The runtime roles hold a column-scoped UPDATE on the
--     five dispatch columns and on nothing else, so a relay can mark an event sent and cannot
--     alter what it says. A relay that could rewrite a payload is a relay that can forge one. The
--     grant names five columns; check 42 asserts the whole column list from the catalogue
--     rather than a hand-written denylist, because a denylist proves only the names somebody
--     thought to write down -- which is the MOD-009 lesson one level further in, and it was
--     found here by review before it was found by an incident.
--
--   * **`event_id` is globally unique, and never comes from a caller.** Paragraph 3253 requires
--     it, and a unique index spanning tenants is in tension with the rest of this schema: a
--     collision would be a refusal one tenant could observe about another. It is safe here only
--     because the value is `gen_random_uuid()` and `append_event` refuses to take one as input,
--     so no caller can probe for a collision. A producer's own dedupe handle is
--     `idempotency_key`, which is tenant-scoped exactly because it *is* caller-supplied.
--
--   * **Retry is per consumer, not per event.** `evt_deliveries` carries one row per
--     (consumer, event) with its own attempt count and backoff, and the primary key is the
--     deduplication: at-least-once delivery means a consumer sees an event twice, and the row
--     that already says `handled` is what makes the second time cheap. Counting attempts on the
--     event instead would let one failing consumer exhaust the budget for every other.
--
--   * **Replay suppresses side effects unless somebody says otherwise.** TSD paragraph 200:
--     "replay defaults to suppress-side-effects", and paragraph 2 of that section requires every
--     consumer to declare a replay-safety class. The column default is `suppress`, the service
--     requires a written reason to pass `allow`, and `evt_subscriptions.replay_safety` is the
--     consumer's own declaration. Replaying a month of `saas.payment.failed` into a consumer
--     that sends email is the failure this prevents.

-- ---------------------------------------------------------------- the outbox

CREATE TABLE plt01.evt_outbox (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    event_id uuid NOT NULL DEFAULT gen_random_uuid(),
    -- The canonical envelope of TSD paragraph 3235: tenant, aggregate, actor, correlation,
    -- causation, schema, timestamp and source. `source` is the owner module, which the
    -- catalogue in app/events/catalog.py holds against the event type rather than repeating
    -- per row -- two rows of the same type cannot have different owners, and a column that can
    -- disagree with the catalogue is a column that eventually does.
    event_type text NOT NULL,
    schema_version integer NOT NULL,
    aggregate_type text NOT NULL,
    aggregate_id uuid NOT NULL,
    -- Optimistic concurrency where the owning module has a version to give. Nullable because
    -- several do not, and a zero would read as "version zero" rather than "not applicable".
    aggregate_version bigint,
    -- Null when the system acted rather than a person: a dunning sweep has no actor, and
    -- inventing one would make an automated action look like somebody's decision.
    actor_id uuid,
    correlation_id uuid NOT NULL,
    causation_id uuid,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    payload jsonb NOT NULL,
    -- The producer's own handle, tenant-scoped because it is the one part of the envelope a
    -- caller chooses. Null for events whose producer has no natural key.
    idempotency_key text,
    status text NOT NULL DEFAULT 'pending',
    attempts integer NOT NULL DEFAULT 0,
    available_at timestamptz NOT NULL DEFAULT now(),
    last_error text,
    dispatched_at timestamptz,
    PRIMARY KEY (tenant_id, event_id),
    CONSTRAINT evt_outbox_type_shape
        CHECK (event_type ~ '^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*)+$'),
    CONSTRAINT evt_outbox_aggregate_shape
        CHECK (aggregate_type ~ '^[a-z0-9]+(_[a-z0-9]+)*$'),
    CONSTRAINT evt_outbox_version_positive CHECK (schema_version > 0),
    CONSTRAINT evt_outbox_attempts_sane CHECK (attempts >= 0),
    CONSTRAINT evt_outbox_status CHECK (status IN ('pending', 'dispatched', 'dead')),
    -- "Dispatched" and a dispatch time are one fact written twice; they cannot disagree. The
    -- `coalesce` habit does not apply -- both sides are non-null booleans -- but the shape is
    -- the same one `sec_dsar_completed_consistent` uses, for the same reason.
    CONSTRAINT evt_outbox_dispatch_consistent CHECK (
        (status = 'dispatched') = (dispatched_at IS NOT NULL)),
    -- A blank key is not a key, and it would collide with every other blank one under the
    -- partial unique index below. `coalesce` is load-bearing: `NULL ~ '[^[:space:]]'` is NULL
    -- and a CHECK passes on NULL, which is how the MOD-009 legal-hold constraint admitted the
    -- row it existed to refuse.
    CONSTRAINT evt_outbox_key_not_blank CHECK (
        idempotency_key IS NULL OR coalesce(idempotency_key, '') ~ '[^[:space:]]'),
    -- A payload is an object. An array or a bare scalar would pass `jsonb` and break every
    -- consumer that reads a field out of it.
    CONSTRAINT evt_outbox_payload_is_an_object CHECK (jsonb_typeof(payload) = 'object')
);
-- Globally unique, per TSD paragraph 3253. Safe only because the value is generated here; see
-- the header.
CREATE UNIQUE INDEX evt_outbox_event_id_global ON plt01.evt_outbox (event_id);
-- The producer's dedupe: appending the same key twice in one tenant is refused, which is what
-- makes `append_event` safe to call from a command that may itself be retried.
CREATE UNIQUE INDEX evt_outbox_idempotency
    ON plt01.evt_outbox (tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
-- The relay's claim query. Partial, because the pending set is small and the dispatched set
-- grows without bound.
CREATE INDEX evt_outbox_claimable
    ON plt01.evt_outbox (tenant_id, available_at) WHERE status = 'pending';
-- TSD paragraph 3253's tenant/aggregate/time index: the history of one thing, in order.
CREATE INDEX evt_outbox_aggregate
    ON plt01.evt_outbox (tenant_id, aggregate_type, aggregate_id, occurred_at);
-- The operational explorer of paragraph 3241: everything that happened under one correlation.
CREATE INDEX evt_outbox_correlation ON plt01.evt_outbox (tenant_id, correlation_id, occurred_at);
-- Replay selects by type and window.
CREATE INDEX evt_outbox_replay ON plt01.evt_outbox (tenant_id, event_type, occurred_at);
ALTER TABLE plt01.evt_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.evt_outbox FORCE ROW LEVEL SECURITY;
CREATE POLICY evt_outbox_tenant ON plt01.evt_outbox
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- subscriptions

-- Routing (TSD paragraph 3239) plus the replay-safety declaration paragraph 200 requires of
-- every consumer. A subscription is deactivated, never deleted: a consumer that vanished is a
-- consumer somebody will ask about when an old event turns up undelivered.
CREATE TABLE plt01.evt_subscriptions (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    subscription_id uuid NOT NULL DEFAULT gen_random_uuid(),
    consumer text NOT NULL,
    event_type text NOT NULL,
    -- `suppress` means replaying into this consumer must not re-run its effects: it sends
    -- messages, takes money or drives a device. `idempotent` means it has its own guard.
    -- `safe` means it only writes a projection it would rebuild anyway. The default is the
    -- strictest, because a consumer whose author did not think about replay is a consumer that
    -- is not safe for it.
    replay_safety text NOT NULL DEFAULT 'suppress',
    max_attempts integer NOT NULL DEFAULT 5,
    active boolean NOT NULL DEFAULT true,
    registered_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    registered_at timestamptz NOT NULL DEFAULT now(),
    deactivated_at timestamptz,
    deactivated_by uuid,
    deactivate_correlation_id uuid,
    PRIMARY KEY (tenant_id, subscription_id),
    UNIQUE (tenant_id, consumer, event_type),
    CONSTRAINT evt_subscriptions_consumer_shape
        CHECK (consumer ~ '^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*)*$'),
    CONSTRAINT evt_subscriptions_type_shape
        CHECK (event_type ~ '^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*)+$'),
    CONSTRAINT evt_subscriptions_replay_safety
        CHECK (replay_safety IN ('suppress', 'idempotent', 'safe')),
    -- One attempt is a consumer with no retry at all, which is a choice; zero is a consumer
    -- that never runs. The ceiling stops a typo turning a transient failure into a month of
    -- retries.
    CONSTRAINT evt_subscriptions_attempts_sane CHECK (max_attempts BETWEEN 1 AND 100),
    -- Deactivation is attributed, like every other state change in this repository, and the
    -- three columns move together.
    CONSTRAINT evt_subscriptions_deactivation_attributed CHECK (
        (deactivated_at IS NULL AND deactivated_by IS NULL
         AND deactivate_correlation_id IS NULL)
        OR (deactivated_at IS NOT NULL AND deactivated_by IS NOT NULL
            AND deactivate_correlation_id IS NOT NULL)),
    -- `active` and the deactivation stamp are one fact written twice.
    CONSTRAINT evt_subscriptions_active_consistent CHECK (
        active = (deactivated_at IS NULL))
);
CREATE INDEX evt_subscriptions_routing
    ON plt01.evt_subscriptions (tenant_id, event_type) WHERE active;
ALTER TABLE plt01.evt_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.evt_subscriptions FORCE ROW LEVEL SECURITY;
CREATE POLICY evt_subscriptions_tenant ON plt01.evt_subscriptions
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- replay

-- Controlled replay (TSD paragraphs 3241 and 3251's ReplayProjection). The window and the type
-- set are fixed when the job is requested and cannot move afterwards -- the terms of a replay
-- are what somebody approved, and a job whose scope can widen after approval is the
-- snapshot-your-terms defect MOD-008's review found, in another costume.
CREATE TABLE plt01.evt_replay_jobs (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    job_id uuid NOT NULL DEFAULT gen_random_uuid(),
    consumer text NOT NULL,
    event_types text[] NOT NULL,
    from_time timestamptz NOT NULL,
    to_time timestamptz NOT NULL,
    -- Paragraph 200: "replay defaults to suppress-side-effects". The default is in the column
    -- so that a caller which forgets the field gets the safe answer rather than the convenient
    -- one, and `app.events.service.request_replay` requires a written reason to pass `allow`.
    side_effects text NOT NULL DEFAULT 'suppress',
    side_effects_reason text,
    status text NOT NULL DEFAULT 'requested',
    requested_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    requested_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    ran_by uuid,
    run_correlation_id uuid,
    finished_at timestamptz,
    events_replayed bigint NOT NULL DEFAULT 0,
    last_error text,
    PRIMARY KEY (tenant_id, job_id),
    -- Requesting a replay and running it are two decisions, and a job carrying
    -- `side_effects = 'allow'` re-delivers a window of events with their effects live. Only
    -- `requested_by` was recorded, so the second decision had nobody's name on it -- the same
    -- rule MOD-009 learned about releasing a legal hold, found again here by review.
    CONSTRAINT evt_replay_run_attributed CHECK (
        (started_at IS NULL AND ran_by IS NULL AND run_correlation_id IS NULL)
        OR (started_at IS NOT NULL AND ran_by IS NOT NULL
            AND run_correlation_id IS NOT NULL)),
    CONSTRAINT evt_replay_side_effects CHECK (side_effects IN ('suppress', 'allow')),
    -- Allowing side effects on a replay is the decision somebody will be asked about, so it
    -- carries its reason in the row. `coalesce` again: without it the NULL case passes.
    CONSTRAINT evt_replay_allow_reasoned CHECK (
        side_effects = 'suppress' OR coalesce(side_effects_reason, '') ~ '[^[:space:]]'),
    CONSTRAINT evt_replay_status
        CHECK (status IN ('requested', 'running', 'completed', 'failed')),
    CONSTRAINT evt_replay_window CHECK (to_time > from_time),
    -- Both halves. An empty list replays nothing; an element that is not a well-formed
    -- event name is a type that cannot exist, and the job then completes with
    -- `events_replayed = 0`, which reads as "there was nothing to replay" rather than "you
    -- mistyped it". `ARRAY[NULL]::text[]` fails the second test rather than returning NULL,
    -- because `<@`-style element predicates over an array containing NULL evaluate to false.
    CONSTRAINT evt_replay_types_well_formed CHECK (
        cardinality(event_types) > 0
        AND array_to_string(event_types, ',')
            ~ '^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*)+(,[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*)+)*$'),
    CONSTRAINT evt_replay_replayed_sane CHECK (events_replayed >= 0),
    CONSTRAINT evt_replay_finished_consistent CHECK (
        (status IN ('completed', 'failed')) = (finished_at IS NOT NULL))
);
CREATE INDEX evt_replay_jobs_recent ON plt01.evt_replay_jobs (tenant_id, requested_at DESC);
ALTER TABLE plt01.evt_replay_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.evt_replay_jobs FORCE ROW LEVEL SECURITY;
CREATE POLICY evt_replay_jobs_tenant ON plt01.evt_replay_jobs
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- deliveries (the inbox)

-- One row per (consumer, event). **The primary key is the deduplication**: at-least-once
-- delivery means a consumer will see an event twice, and the row already saying `handled` is
-- what makes the second time a no-op instead of a second effect. TSD paragraph 62 states the
-- rule from the consumer's side -- "deduplicate by event_id/idempotency key" -- and this is the
-- table that lets a consumer obey it without inventing its own.
CREATE TABLE plt01.evt_deliveries (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    consumer text NOT NULL,
    event_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    attempts integer NOT NULL DEFAULT 0,
    available_at timestamptz NOT NULL DEFAULT now(),
    first_queued_at timestamptz NOT NULL DEFAULT now(),
    handled_at timestamptz,
    last_error text,
    -- True when this row was created by a replay rather than by the original dispatch, so the
    -- evidence distinguishes "the consumer saw this when it happened" from "we sent it again".
    from_replay_job_id uuid,
    PRIMARY KEY (tenant_id, consumer, event_id),
    FOREIGN KEY (tenant_id, event_id) REFERENCES plt01.evt_outbox (tenant_id, event_id),
    -- A composite reference like every other one here. It had none, so the column recording
    -- "this delivery came from a replay rather than from the original dispatch" could name a
    -- job that does not exist, or one in another tenant -- forgeable evidence, which is the
    -- `on_behalf_of` finding from MOD-008's review in another costume.
    FOREIGN KEY (tenant_id, from_replay_job_id)
        REFERENCES plt01.evt_replay_jobs (tenant_id, job_id),
    CONSTRAINT evt_deliveries_status
        CHECK (status IN ('pending', 'handled', 'suppressed', 'dead')),
    CONSTRAINT evt_deliveries_attempts_sane CHECK (attempts >= 0),
    -- A terminal status and a settle time are one fact written twice. `suppressed` and `dead`
    -- are terminal too: a suppressed replay was decided, not merely skipped.
    CONSTRAINT evt_deliveries_settled_consistent CHECK (
        (status IN ('handled', 'suppressed', 'dead')) = (handled_at IS NOT NULL))
);
CREATE INDEX evt_deliveries_claimable
    ON plt01.evt_deliveries (tenant_id, consumer, available_at) WHERE status = 'pending';
ALTER TABLE plt01.evt_deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.evt_deliveries FORCE ROW LEVEL SECURITY;
CREATE POLICY evt_deliveries_tenant ON plt01.evt_deliveries
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- dead letters

-- A delivery that exhausted its attempts. Quarantine rather than discard (TSD's QuarantineDelivery
-- command, paragraph 3251): the event is still in the outbox and the row says which consumer
-- could not take it and why, which is the question asked during an incident.
--
-- Released, not deleted, and re-quarantinable: the partial unique index keys on the live ones
-- only, so a released dead letter that fails again gets a second row and the history of both
-- attempts survives. That is the opposite of `sec_legal_holds`, where a release is final,
-- because here the earlier quarantine is a fact about the past rather than a control over the
-- present.
CREATE TABLE plt01.evt_dead_letters (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    dead_letter_id uuid NOT NULL DEFAULT gen_random_uuid(),
    event_id uuid NOT NULL,
    consumer text NOT NULL,
    reason text NOT NULL,
    attempts integer NOT NULL,
    quarantined_at timestamptz NOT NULL DEFAULT now(),
    released_at timestamptz,
    released_by uuid,
    release_reason text,
    release_correlation_id uuid,
    PRIMARY KEY (tenant_id, dead_letter_id),
    FOREIGN KEY (tenant_id, event_id) REFERENCES plt01.evt_outbox (tenant_id, event_id),
    CONSTRAINT evt_dead_letters_reason_not_blank CHECK (reason ~ '[^[:space:]]'),
    CONSTRAINT evt_dead_letters_attempts_sane CHECK (attempts > 0),
    CONSTRAINT evt_dead_letters_release_attributed CHECK (
        (released_at IS NULL AND released_by IS NULL AND release_reason IS NULL
         AND release_correlation_id IS NULL)
        OR (released_at IS NOT NULL AND released_by IS NOT NULL
            AND coalesce(release_reason, '') ~ '[^[:space:]]'
            AND release_correlation_id IS NOT NULL))
);
CREATE UNIQUE INDEX evt_dead_letters_live
    ON plt01.evt_dead_letters (tenant_id, consumer, event_id) WHERE released_at IS NULL;
CREATE INDEX evt_dead_letters_recent
    ON plt01.evt_dead_letters (tenant_id, quarantined_at DESC);
ALTER TABLE plt01.evt_dead_letters ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.evt_dead_letters FORCE ROW LEVEL SECURITY;
CREATE POLICY evt_dead_letters_tenant ON plt01.evt_dead_letters
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- privileges

-- The outbox: appended and marked, never edited. The column list is the whole of the dispatch
-- state and nothing else, so a relay can say an event was sent and cannot change what it says.
-- Check 42 proves these grants by comparing the whole column list against the catalogue, so a
-- grant widened by one column anywhere in this module fails it. It did not always: the first
-- version listed column names by hand and ten distinct widenings passed the suite, including
-- UPDATE on `evt_outbox.event_type` for the relay role -- which re-routes a committed event to
-- a different consumer set, and is forging an event from every consumer's point of view.
GRANT SELECT, INSERT ON plt01.evt_outbox TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (status, attempts, available_at, last_error, dispatched_at) ON plt01.evt_outbox
    TO veyro_cp_app, veyro_cp_worker;

-- A subscription's consumer and event type are what it *is*; only its activation and its retry
-- budget move. Re-pointing a subscription at another event type would silently re-route a live
-- consumer, which is a new subscription rather than an edit.
GRANT SELECT, INSERT ON plt01.evt_subscriptions TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (active, max_attempts, replay_safety, deactivated_at, deactivated_by,
              deactivate_correlation_id)
    ON plt01.evt_subscriptions TO veyro_cp_app, veyro_cp_worker;

-- A delivery row moves through its own retry, so it needs a real UPDATE -- but not on the three
-- columns that identify it, which are the primary key, nor on when it was first queued.
GRANT SELECT, INSERT ON plt01.evt_deliveries TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (status, attempts, available_at, handled_at, last_error, from_replay_job_id)
    ON plt01.evt_deliveries TO veyro_cp_app, veyro_cp_worker;

-- Quarantine evidence. The reason, the consumer and the attempt count are what the row is for;
-- only the release moves.
GRANT SELECT, INSERT ON plt01.evt_dead_letters TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (released_at, released_by, release_reason, release_correlation_id)
    ON plt01.evt_dead_letters TO veyro_cp_app, veyro_cp_worker;

-- A replay job's terms -- the consumer, the window, the type set and the side-effect policy --
-- are fixed when it is requested. Only its progress moves.
GRANT SELECT, INSERT ON plt01.evt_replay_jobs TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (status, started_at, ran_by, run_correlation_id, finished_at, events_replayed,
              last_error)
    ON plt01.evt_replay_jobs TO veyro_cp_app, veyro_cp_worker;
