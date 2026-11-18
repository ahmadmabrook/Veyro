-- MOD-022 OPS-03: check-in, access control and entitlement decisions.
--
-- **Eight `acc_` tables, under the same forced RLS as every other `plt01` table.** The
-- pattern in `0001_organization_hierarchy.sql` is copied exactly and each of its four parts
-- is load-bearing: `tenant_id NOT NULL`, a tenant-leading primary key, ENABLE *and* FORCE row
-- level security, and a policy whose predicate is the approved one on both halves. A
-- composite foreign key carries `tenant_id` into every parent reference.
--
-- **This is the module that joins three planes that did not know about each other.** MOD-021
-- has the door and the command that opens it, MOD-017 has the entitlement that says whether
-- somebody may train, and MOD-014 has the person. Every one of those references is a real
-- composite foreign key here, because they are all in `plt01` under one role -- which is the
-- rare case where "no cross-domain write-table access" (paragraph 1300) and an enforceable
-- reference are both available: this module *reads* them and writes only its own tables.
--
-- **A credential identifies; policy and entitlement authorize** (paragraph 4155, said again
-- at 876 and 10129). The schema half of that is `acc_credentials`, which carries a person and
-- a hash and not one attribute that could bear on a decision -- no membership state, no
-- entitlement, no balance. A column here that did would be a credential that authorizes.
--
-- **And no column holds a credential in the clear.** `credential_digest` is a SHA-256, which
-- is what makes paragraph 4161's "only pseudonymous credential hashes" true of the snapshot
-- rather than a thing somebody meant. Check 107 asserts the column list in full, because the
-- control is an absence and an absence is exactly what a later migration adds back.

-- ------------------------------------------------------------------- the zones
--
-- **A zone is where the risk is declared.** Paragraph 4160 makes an offline authorization's
-- lifetime depend on what it opens -- twelve hours standard, two for high-risk -- which is
-- the only place in this build where that is true, and the reason a zone is a row.
CREATE TABLE plt01.acc_zones (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    zone_id uuid NOT NULL DEFAULT gen_random_uuid(),
    location_id uuid NOT NULL,
    zone_key text NOT NULL,
    display_name text NOT NULL,
    risk_class text NOT NULL DEFAULT 'standard',
    status text NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    retired_at timestamptz,
    retired_by uuid,
    retire_reason text,
    retire_correlation_id uuid,
    PRIMARY KEY (tenant_id, zone_id),
    UNIQUE (tenant_id, zone_key),
    FOREIGN KEY (tenant_id, location_id)
        REFERENCES plt01.locations (tenant_id, location_id),
    CONSTRAINT acc_zones_risk_class
        CHECK (risk_class IN ('standard', 'high_risk')),
    CONSTRAINT acc_zones_status CHECK (status IN ('active', 'retired')),
    CONSTRAINT acc_zones_key_shape CHECK (zone_key ~ '^[a-z][a-z0-9._-]{1,47}$'),
    CONSTRAINT acc_zones_name_not_blank CHECK (display_name ~ '[^[:space:]]'),
    CONSTRAINT acc_zones_name_bounded CHECK (length(display_name) <= 120),
    CONSTRAINT acc_zones_retired_is_retired
        CHECK ((status = 'retired') = (retired_at IS NOT NULL)),
    CONSTRAINT acc_zones_retirement_attributed CHECK (
        (retired_at IS NULL AND retired_by IS NULL AND retire_reason IS NULL
         AND retire_correlation_id IS NULL)
        OR (retired_at IS NOT NULL AND retired_by IS NOT NULL
            AND coalesce(retire_reason, '') ~ '[^[:space:]]'
            AND retire_correlation_id IS NOT NULL))
);
ALTER TABLE plt01.acc_zones ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.acc_zones FORCE ROW LEVEL SECURITY;
CREATE POLICY acc_zones_tenant ON plt01.acc_zones
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE INDEX acc_zones_by_location ON plt01.acc_zones (tenant_id, location_id);

-- ------------------------------------------------------------------ the points
--
-- **An access point is the join MOD-021 deliberately did not make.** A device knows what it
-- can do and which location it is at; it knows nothing about a member. This row says which
-- device stands at which zone and which way it faces.
--
-- `direction` is the one field with a life-safety consequence. Paragraph 4177: egress is
-- never conditioned on Veyro membership, cloud reachability or software authorization -- so
-- an `exit` reader records that somebody left and never decides, and `zones.decides_entry` is
-- the function that says so.
CREATE TABLE plt01.acc_points (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    point_id uuid NOT NULL DEFAULT gen_random_uuid(),
    zone_id uuid NOT NULL,
    device_id uuid NOT NULL,
    direction text NOT NULL,
    display_name text NOT NULL,
    status text NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    retired_at timestamptz,
    retired_by uuid,
    retire_reason text,
    retire_correlation_id uuid,
    PRIMARY KEY (tenant_id, point_id),
    -- **One point per device.** A single reader standing at two zones is two answers to
    -- "which policy applies", and the planner would pick one.
    UNIQUE (tenant_id, device_id),
    FOREIGN KEY (tenant_id, zone_id) REFERENCES plt01.acc_zones (tenant_id, zone_id),
    FOREIGN KEY (tenant_id, device_id) REFERENCES plt01.dev_devices (tenant_id, device_id),
    CONSTRAINT acc_points_direction CHECK (direction IN ('entry', 'exit', 'both')),
    CONSTRAINT acc_points_status CHECK (status IN ('active', 'retired')),
    CONSTRAINT acc_points_name_not_blank CHECK (display_name ~ '[^[:space:]]'),
    CONSTRAINT acc_points_name_bounded CHECK (length(display_name) <= 120),
    CONSTRAINT acc_points_retired_is_retired
        CHECK ((status = 'retired') = (retired_at IS NOT NULL)),
    CONSTRAINT acc_points_retirement_attributed CHECK (
        (retired_at IS NULL AND retired_by IS NULL AND retire_reason IS NULL
         AND retire_correlation_id IS NULL)
        OR (retired_at IS NOT NULL AND retired_by IS NOT NULL
            AND coalesce(retire_reason, '') ~ '[^[:space:]]'
            AND retire_correlation_id IS NOT NULL))
);
ALTER TABLE plt01.acc_points ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.acc_points FORCE ROW LEVEL SECURITY;
CREATE POLICY acc_points_tenant ON plt01.acc_points
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE INDEX acc_points_by_zone ON plt01.acc_points (tenant_id, zone_id);

-- ---------------------------------------------------------------- the policies
--
-- **A published policy version is immutable and a decision cites the exact one.** Paragraph
-- 1952: "decision references exact snapshot/policy version". MOD-015's plan version and
-- MOD-016's price are the precedent, and the reason is the same one in a different currency:
-- a decision re-derived a year later against today's policy is not the decision that was
-- made, and this is the table somebody will be asked about after an incident.
--
-- **Two acts by two people**, for MOD-017's contract-version reason: a policy decides who
-- gets through a door, and the author settling their own draft is one person deciding that.
CREATE TABLE plt01.acc_policies (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    policy_id uuid NOT NULL DEFAULT gen_random_uuid(),
    zone_id uuid NOT NULL,
    version integer NOT NULL,
    status text NOT NULL DEFAULT 'draft',
    -- Minutes since midnight in the location's own zone. NULL for both means always open,
    -- which is what a 24-hour club is; one without the other is a window with one end.
    opens_minute integer,
    closes_minute integer,
    requires_entitlement boolean NOT NULL DEFAULT true,
    -- In minor units, and **NULL means this zone does not look at a balance at all.** Zero
    -- would mean "no arrears admitted", which is a different and much stricter statement.
    max_balance_minor bigint,
    min_age_years integer,
    anti_passback_seconds integer NOT NULL DEFAULT 0,
    capacity integer,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    published_at timestamptz,
    published_by uuid,
    publish_correlation_id uuid,
    retired_at timestamptz,
    retired_by uuid,
    retire_reason text,
    retire_correlation_id uuid,
    PRIMARY KEY (tenant_id, policy_id),
    UNIQUE (tenant_id, zone_id, version),
    FOREIGN KEY (tenant_id, zone_id) REFERENCES plt01.acc_zones (tenant_id, zone_id),
    CONSTRAINT acc_policies_status CHECK (status IN ('draft', 'published', 'retired')),
    CONSTRAINT acc_policies_version_positive CHECK (version >= 1 AND version <= 100000),
    CONSTRAINT acc_policies_hours_paired
        CHECK ((opens_minute IS NULL) = (closes_minute IS NULL)),
    CONSTRAINT acc_policies_opens_in_a_day
        CHECK (opens_minute IS NULL OR (opens_minute >= 0 AND opens_minute < 1440)),
    CONSTRAINT acc_policies_closes_in_a_day
        CHECK (closes_minute IS NULL OR (closes_minute >= 0 AND closes_minute < 1440)),
    -- **A window with both ends equal is not a window.** It reads as "open all day" to a
    -- careless reader and as "open for nothing" to `policy._within`, which wraps past
    -- midnight; neither is a thing anybody meant to configure.
    CONSTRAINT acc_policies_hours_differ
        CHECK (opens_minute IS NULL OR opens_minute <> closes_minute),
    CONSTRAINT acc_policies_balance_sane
        CHECK (max_balance_minor IS NULL
               OR (max_balance_minor >= 0 AND max_balance_minor <= 1000000000000)),
    CONSTRAINT acc_policies_age_sane
        CHECK (min_age_years IS NULL OR (min_age_years >= 0 AND min_age_years <= 120)),
    -- Twelve hours, because anti-passback longer than a shift stops a member who legitimately
    -- left and came back, and because an unbounded integer here is a lockout nobody can
    -- explain. Zero means the zone does not enforce it.
    CONSTRAINT acc_policies_passback_sane
        CHECK (anti_passback_seconds >= 0 AND anti_passback_seconds <= 43200),
    CONSTRAINT acc_policies_capacity_sane
        CHECK (capacity IS NULL OR (capacity >= 0 AND capacity <= 1000000)),
    CONSTRAINT acc_policies_published_is_published
        CHECK (status = 'draft' OR published_at IS NOT NULL),
    CONSTRAINT acc_policies_publication_attributed CHECK (
        (published_at IS NULL AND published_by IS NULL AND publish_correlation_id IS NULL)
        OR (published_at IS NOT NULL AND published_by IS NOT NULL
            AND publish_correlation_id IS NOT NULL)),
    -- The half the service cannot weaken. MOD-016's discount approval and MOD-017's contract
    -- version, in the place where the thing being settled is who gets through a door.
    CONSTRAINT acc_policies_publisher_is_not_author
        CHECK (published_by IS NULL OR published_by <> created_by),
    CONSTRAINT acc_policies_retired_is_retired
        CHECK ((status = 'retired') = (retired_at IS NOT NULL)),
    CONSTRAINT acc_policies_retirement_attributed CHECK (
        (retired_at IS NULL AND retired_by IS NULL AND retire_reason IS NULL
         AND retire_correlation_id IS NULL)
        OR (retired_at IS NOT NULL AND retired_by IS NOT NULL
            AND coalesce(retire_reason, '') ~ '[^[:space:]]'
            AND retire_correlation_id IS NOT NULL))
);
ALTER TABLE plt01.acc_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.acc_policies FORCE ROW LEVEL SECURITY;
CREATE POLICY acc_policies_tenant ON plt01.acc_policies
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
-- **One live policy per zone at every statement**, which is what makes "the policy that
-- applied" a single answer rather than whichever row the planner reached first.
CREATE UNIQUE INDEX acc_policies_one_live_per_zone
    ON plt01.acc_policies (tenant_id, zone_id) WHERE status = 'published';

-- ------------------------------------------------------------- the credentials
--
-- **A credential identifies a subject and carries nothing that could authorize one.** No
-- membership state, no entitlement, no balance, no date of birth: every one of those is read
-- from the module that owns it at decision time, so a stolen card is a stolen identity rather
-- than a stolen permission.
--
-- `credential_digest` is a SHA-256 of the identifier the member presents. The raw value is
-- nowhere in this build -- MOD-013's shape for a contact address, and here it is also
-- paragraph 4161's requirement about what an edge snapshot may replicate.
CREATE TABLE plt01.acc_credentials (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    credential_id uuid NOT NULL DEFAULT gen_random_uuid(),
    person_id uuid NOT NULL,
    kind text NOT NULL,
    credential_digest text NOT NULL,
    state text NOT NULL DEFAULT 'active',
    -- **The epoch a reader compares its snapshot against.** MOD-021 keeps one per device for
    -- the device's own withdrawals; this is the credential's, so revoking one card does not
    -- invalidate every snapshot in the building.
    revocation_epoch integer NOT NULL DEFAULT 0,
    issued_at timestamptz NOT NULL DEFAULT now(),
    issued_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    expires_at timestamptz,
    revoked_at timestamptz,
    revoked_by uuid,
    revoke_reason text,
    revoke_correlation_id uuid,
    PRIMARY KEY (tenant_id, credential_id),
    -- One digest is one credential in a tenant: two rows for one card is two answers to who
    -- is at the door.
    UNIQUE (tenant_id, credential_digest),
    FOREIGN KEY (tenant_id, person_id) REFERENCES plt01.ppl_persons (tenant_id, person_id),
    CONSTRAINT acc_credentials_kind CHECK (kind IN (
        'qr_rotating', 'nfc_card', 'wallet_pass', 'physical_card', 'pin',
        'staff_assisted', 'biometric')),
    CONSTRAINT acc_credentials_state CHECK (state IN ('active', 'revoked', 'expired')),
    CONSTRAINT acc_credentials_digest_shape
        CHECK (credential_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT acc_credentials_epoch_sane
        CHECK (revocation_epoch >= 0 AND revocation_epoch <= 2000000000),
    CONSTRAINT acc_credentials_expiry_after_issue
        CHECK (expires_at IS NULL OR expires_at > issued_at),
    CONSTRAINT acc_credentials_not_postdated
        CHECK (issued_at <= now() + interval '5 minutes'),
    CONSTRAINT acc_credentials_revoked_is_revoked
        CHECK ((state = 'revoked') = (revoked_at IS NOT NULL)),
    CONSTRAINT acc_credentials_revocation_attributed CHECK (
        (revoked_at IS NULL AND revoked_by IS NULL AND revoke_reason IS NULL
         AND revoke_correlation_id IS NULL)
        OR (revoked_at IS NOT NULL AND revoked_by IS NOT NULL
            AND coalesce(revoke_reason, '') ~ '[^[:space:]]'
            AND revoke_correlation_id IS NOT NULL))
);
ALTER TABLE plt01.acc_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.acc_credentials FORCE ROW LEVEL SECURITY;
CREATE POLICY acc_credentials_tenant ON plt01.acc_credentials
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE INDEX acc_credentials_by_person
    ON plt01.acc_credentials (tenant_id, person_id, issued_at DESC);

-- ---------------------------------------------------------------- the decisions
--
-- **Insert-only, and the only record of why a door did or did not open.** MOD-008 audits
-- denials of *permissions* and `veyro_cp_app` holds nothing in `iam`, so when a member asks
-- why they were turned away, or a regulator asks who was let in, this row is the answer and
-- there is no second one.
--
-- **Two reasons, which is paragraph 1944's Critical Control as a pair of columns.** The
-- public one is what a screen above a turnstile may show; the private one is what the front
-- desk and this evidence hold. `policy.PUBLIC_SAFE` decides which codes may share them, and
-- `masked` records that they differ -- so "how often did we tell somebody to see the desk"
-- is a query rather than a text search.
CREATE TABLE plt01.acc_decisions (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    decision_id uuid NOT NULL DEFAULT gen_random_uuid(),
    point_id uuid NOT NULL,
    zone_id uuid NOT NULL,
    -- NULL when the credential was not recognised at all, which is the commonest denial and
    -- the one that must not need a person to be invented for it.
    credential_id uuid,
    person_id uuid,
    granted boolean NOT NULL,
    code text NOT NULL,
    public_reason text NOT NULL,
    private_reason text NOT NULL,
    masked boolean NOT NULL,
    -- Paragraph 1952's exact references. NULL where no policy was reached: an unknown
    -- credential is refused before any policy is read.
    policy_id uuid,
    policy_version integer,
    snapshot_id uuid,
    device_mode text NOT NULL,
    passback_scope text NOT NULL,
    occupancy_seen integer,
    override_reason text,
    overridden_by uuid,
    decided_at timestamptz NOT NULL DEFAULT now(),
    decided_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    idempotency_key text NOT NULL,
    PRIMARY KEY (tenant_id, decision_id),
    UNIQUE (tenant_id, idempotency_key),
    FOREIGN KEY (tenant_id, point_id) REFERENCES plt01.acc_points (tenant_id, point_id),
    FOREIGN KEY (tenant_id, zone_id) REFERENCES plt01.acc_zones (tenant_id, zone_id),
    FOREIGN KEY (tenant_id, credential_id)
        REFERENCES plt01.acc_credentials (tenant_id, credential_id),
    FOREIGN KEY (tenant_id, person_id) REFERENCES plt01.ppl_persons (tenant_id, person_id),
    FOREIGN KEY (tenant_id, policy_id) REFERENCES plt01.acc_policies (tenant_id, policy_id),
    FOREIGN KEY (tenant_id, snapshot_id)
        REFERENCES plt01.dev_policy_snapshots (tenant_id, snapshot_id),
    CONSTRAINT acc_decisions_code CHECK (code IN (
        'granted', 'granted_by_override', 'credential_unknown', 'credential_revoked',
        'credential_expired', 'credential_replayed', 'credential_window',
        'reader_clock_unreliable', 'wrong_zone', 'outside_opening_hours', 'zone_closed',
        'membership_inactive', 'no_entitlement', 'outstanding_balance', 'age_restricted',
        'safety_hold', 'anti_passback', 'zone_at_capacity', 'device_untrusted',
        'snapshot_stale', 'point_not_an_entry')),
    -- **The code decides whether the door opened**, so the boolean cannot disagree with it.
    -- Two columns that can contradict each other are MOD-018's reason for deriving a
    -- posting's side from its sign.
    CONSTRAINT acc_decisions_granted_matches_code
        CHECK (granted = (code IN ('granted', 'granted_by_override'))),
    -- **And an override is the only way `granted` is true without every check passing.**
    -- A flag on an ordinary grant is MOD-013's `priority: "critical"`; a separate code with
    -- a mandatory reason and a named actor is what makes "how often was the policy
    -- overridden" answerable.
    CONSTRAINT acc_decisions_override_attributed CHECK (
        (code <> 'granted_by_override'
         AND override_reason IS NULL AND overridden_by IS NULL)
        OR (code = 'granted_by_override'
            AND coalesce(override_reason, '') ~ '[^[:space:]]'
            AND overridden_by IS NOT NULL)),
    CONSTRAINT acc_decisions_override_reason_bounded
        CHECK (override_reason IS NULL OR length(override_reason) <= 500),
    -- **A policy version comes with its policy.** Half a citation is a decision that names
    -- no terms at all.
    CONSTRAINT acc_decisions_policy_cited_whole
        CHECK ((policy_id IS NULL) = (policy_version IS NULL)),
    CONSTRAINT acc_decisions_policy_version_sane
        CHECK (policy_version IS NULL
               OR (policy_version >= 1 AND policy_version <= 100000)),
    CONSTRAINT acc_decisions_reasons_not_blank
        CHECK (public_reason ~ '[^[:space:]]' AND private_reason ~ '[^[:space:]]'),
    CONSTRAINT acc_decisions_reasons_bounded
        CHECK (length(public_reason) <= 200 AND length(private_reason) <= 500),
    -- **`masked` is derived, not declared, and what it means is that the member was given
    -- the discreet line.** The first version read `masked = (public_reason <> private_reason)`
    -- and was wrong in the ordinary case: a grant says "welcome" publicly and "every check
    -- passed" privately, which are two different strings carrying the same nothing -- so every
    -- successful entry was refused by this constraint, and the module could not admit anybody.
    -- Found by the first HTTP test that presented a valid card.
    --
    -- The literal is pinned here on purpose. `policy.DISCREET` is the Python half and
    -- `test_the_discreet_line_is_the_same_string_in_both_halves` is what stops the two
    -- drifting: a service that changed the wording would start writing rows this refuses, or
    -- worse, rows that read as unmasked while the member was told nothing.
    CONSTRAINT acc_decisions_masked_is_the_discreet_line
        CHECK (masked = (public_reason = 'please see the front desk')),
    CONSTRAINT acc_decisions_mode CHECK (device_mode IN ('online', 'offline', 'supervised')),
    CONSTRAINT acc_decisions_passback_scope
        CHECK (passback_scope IN ('global', 'controller_group')),
    CONSTRAINT acc_decisions_occupancy_sane
        CHECK (occupancy_seen IS NULL
               OR (occupancy_seen >= 0 AND occupancy_seen <= 1000000)),
    CONSTRAINT acc_decisions_key_not_blank CHECK (idempotency_key ~ '[^[:space:]]'),
    CONSTRAINT acc_decisions_key_bounded CHECK (length(idempotency_key) <= 200),
    CONSTRAINT acc_decisions_not_postdated
        CHECK (decided_at <= now() + interval '5 minutes'),
    -- **A granted decision names who it was for.** A door that opened for nobody in
    -- particular is an entry nothing can be reconciled against, and the whole of
    -- anti-passback and occupancy reads these rows.
    CONSTRAINT acc_decisions_grant_names_a_person
        CHECK (NOT granted OR person_id IS NOT NULL)
);
ALTER TABLE plt01.acc_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.acc_decisions FORCE ROW LEVEL SECURITY;
CREATE POLICY acc_decisions_tenant ON plt01.acc_decisions
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE INDEX acc_decisions_by_zone
    ON plt01.acc_decisions (tenant_id, zone_id, decided_at DESC);
CREATE INDEX acc_decisions_by_credential
    ON plt01.acc_decisions (tenant_id, credential_id, decided_at DESC);

-- ------------------------------------------------------------------ the events
--
-- **What actually happened at the door, which is not the same as what was decided.** A
-- granted decision whose member walked away is a decision with no entry, and occupancy reads
-- these rows rather than the decisions for exactly that reason.
--
-- `local_sequence` and `idempotency_key` are paragraph 4168's: "Offline events carry local
-- monotonic sequence and idempotency key; reconnect reconciliation deduplicates and flags
-- policy conflicts rather than rewriting history."
CREATE TABLE plt01.acc_events (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    event_id uuid NOT NULL DEFAULT gen_random_uuid(),
    point_id uuid NOT NULL,
    zone_id uuid NOT NULL,
    direction text NOT NULL,
    credential_id uuid,
    person_id uuid,
    decision_id uuid,
    occurred_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    recorded_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    source text NOT NULL,
    local_sequence bigint,
    idempotency_key text NOT NULL,
    -- Set by reconciliation, never at the time. NULL means nothing has looked at it yet.
    reconciled_outcome text,
    reconciled_at timestamptz,
    reconciled_by uuid,
    reconcile_correlation_id uuid,
    PRIMARY KEY (tenant_id, event_id),
    UNIQUE (tenant_id, idempotency_key),
    FOREIGN KEY (tenant_id, point_id) REFERENCES plt01.acc_points (tenant_id, point_id),
    FOREIGN KEY (tenant_id, zone_id) REFERENCES plt01.acc_zones (tenant_id, zone_id),
    FOREIGN KEY (tenant_id, credential_id)
        REFERENCES plt01.acc_credentials (tenant_id, credential_id),
    FOREIGN KEY (tenant_id, person_id) REFERENCES plt01.ppl_persons (tenant_id, person_id),
    FOREIGN KEY (tenant_id, decision_id)
        REFERENCES plt01.acc_decisions (tenant_id, decision_id),
    CONSTRAINT acc_events_direction CHECK (direction IN ('entry', 'exit')),
    CONSTRAINT acc_events_source CHECK (source IN ('online', 'offline')),
    -- **An offline event carries its device's own sequence; an online one does not.** The
    -- sequence is what makes a reconnect's batch orderable without trusting the clock, and a
    -- sequence on an online event would be a number nothing produced.
    CONSTRAINT acc_events_sequence_matches_source
        CHECK ((source = 'offline') = (local_sequence IS NOT NULL)),
    CONSTRAINT acc_events_sequence_sane
        CHECK (local_sequence IS NULL
               OR (local_sequence >= 0 AND local_sequence <= 9000000000000000)),
    CONSTRAINT acc_events_key_not_blank CHECK (idempotency_key ~ '[^[:space:]]'),
    CONSTRAINT acc_events_key_bounded CHECK (length(idempotency_key) <= 200),
    CONSTRAINT acc_events_not_postdated
        CHECK (occurred_at <= now() + interval '5 minutes'),
    CONSTRAINT acc_events_reconciled_outcome CHECK (
        reconciled_outcome IS NULL
        OR reconciled_outcome IN ('accepted', 'duplicate', 'policy_conflict',
                                  'stale_snapshot')),
    CONSTRAINT acc_events_reconciliation_attributed CHECK (
        (reconciled_outcome IS NULL AND reconciled_at IS NULL AND reconciled_by IS NULL
         AND reconcile_correlation_id IS NULL)
        OR (reconciled_outcome IS NOT NULL AND reconciled_at IS NOT NULL
            AND reconciled_by IS NOT NULL AND reconcile_correlation_id IS NOT NULL))
);
ALTER TABLE plt01.acc_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.acc_events FORCE ROW LEVEL SECURITY;
CREATE POLICY acc_events_tenant ON plt01.acc_events
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE INDEX acc_events_by_zone
    ON plt01.acc_events (tenant_id, zone_id, occurred_at DESC);
CREATE INDEX acc_events_by_credential
    ON plt01.acc_events (tenant_id, credential_id, occurred_at DESC);

-- --------------------------------------------------------- the replay evidence
--
-- Paragraph 4183: "Edge readers validate signature, scope, revocation epoch and recent-token
-- replay cache **before** policy evaluation." A rotating token is good for thirty seconds and
-- a screenshot of one is good for the same thirty seconds -- the mitigation is the short
-- lifetime plus the fact that the second presentation is recognised, which is this table.
--
-- **It is the one table in this module that is meant to be swept.** Every row expires, and
-- nothing here loops; the fourteenth module to want the worker runtime this build does not
-- have, and the first where the absence is pure growth rather than a product gap.
CREATE TABLE plt01.acc_replay_tokens (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    token_key text NOT NULL,
    credential_id uuid NOT NULL,
    point_id uuid NOT NULL,
    seen_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    correlation_id uuid NOT NULL,
    -- **The key is the primary key**, which is what makes the second presentation a unique
    -- violation rather than a race two readers can both win. MOD-010's delivery key is the
    -- precedent: the deduplication *is* the constraint.
    PRIMARY KEY (tenant_id, token_key),
    FOREIGN KEY (tenant_id, credential_id)
        REFERENCES plt01.acc_credentials (tenant_id, credential_id),
    FOREIGN KEY (tenant_id, point_id) REFERENCES plt01.acc_points (tenant_id, point_id),
    CONSTRAINT acc_replay_tokens_key_shape CHECK (token_key ~ '^[0-9a-f]{64}$'),
    CONSTRAINT acc_replay_tokens_window CHECK (expires_at > seen_at),
    -- Ninety seconds is the token's thirty plus both reader tolerances; a longer window here
    -- is a table that holds evidence nothing could act on.
    CONSTRAINT acc_replay_tokens_window_bounded
        CHECK (expires_at - seen_at <= interval '90 seconds')
);
ALTER TABLE plt01.acc_replay_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.acc_replay_tokens FORCE ROW LEVEL SECURITY;
CREATE POLICY acc_replay_tokens_tenant ON plt01.acc_replay_tokens
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE INDEX acc_replay_tokens_by_expiry ON plt01.acc_replay_tokens (tenant_id, expires_at);

-- ----------------------------------------------------------- the emergency log
--
-- Paragraph 4178: "Emergency unlock is a distinct privileged command with step-up/dual
-- approval where time permits, device target, reason, actor and outcome audit."
--
-- **Where time permits is doing real work in that sentence.** A second approver is required
-- *after the fact* rather than before it: a fire is not a moment to go looking for a
-- colleague, so the release happens on one authority and the row is unsettled until somebody
-- else reviews it. That is the opposite trade from MOD-016's discount approval, deliberately,
-- and the reason is that the harm of a wrongly-refused emergency unlock is not symmetric with
-- the harm of a wrongly-granted one.
CREATE TABLE plt01.acc_emergency_unlocks (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    unlock_id uuid NOT NULL DEFAULT gen_random_uuid(),
    zone_id uuid NOT NULL,
    reason text NOT NULL,
    points_released integer NOT NULL,
    ordered_at timestamptz NOT NULL DEFAULT now(),
    ordered_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    idempotency_key text NOT NULL,
    reviewed_at timestamptz,
    reviewed_by uuid,
    review_note text,
    review_correlation_id uuid,
    PRIMARY KEY (tenant_id, unlock_id),
    UNIQUE (tenant_id, idempotency_key),
    FOREIGN KEY (tenant_id, zone_id) REFERENCES plt01.acc_zones (tenant_id, zone_id),
    CONSTRAINT acc_emergency_unlocks_reason_not_blank CHECK (reason ~ '[^[:space:]]'),
    CONSTRAINT acc_emergency_unlocks_reason_bounded CHECK (length(reason) <= 500),
    CONSTRAINT acc_emergency_unlocks_released_sane
        CHECK (points_released >= 0 AND points_released <= 10000),
    CONSTRAINT acc_emergency_unlocks_key_not_blank CHECK (idempotency_key ~ '[^[:space:]]'),
    CONSTRAINT acc_emergency_unlocks_key_bounded CHECK (length(idempotency_key) <= 200),
    CONSTRAINT acc_emergency_unlocks_not_postdated
        CHECK (ordered_at <= now() + interval '5 minutes'),
    CONSTRAINT acc_emergency_unlocks_review_attributed CHECK (
        (reviewed_at IS NULL AND reviewed_by IS NULL AND review_note IS NULL
         AND review_correlation_id IS NULL)
        OR (reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL
            AND coalesce(review_note, '') ~ '[^[:space:]]'
            AND review_correlation_id IS NOT NULL)),
    -- **The reviewer is not the person who ordered it.** That is the whole of the dual
    -- approval paragraph 4178 asks for, moved to the only moment it can happen.
    CONSTRAINT acc_emergency_unlocks_reviewer_is_not_orderer
        CHECK (reviewed_by IS NULL OR reviewed_by <> ordered_by),
    CONSTRAINT acc_emergency_unlocks_review_after_order
        CHECK (reviewed_at IS NULL OR reviewed_at >= ordered_at)
);
ALTER TABLE plt01.acc_emergency_unlocks ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.acc_emergency_unlocks FORCE ROW LEVEL SECURITY;
CREATE POLICY acc_emergency_unlocks_tenant ON plt01.acc_emergency_unlocks
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE INDEX acc_emergency_unlocks_unreviewed
    ON plt01.acc_emergency_unlocks (tenant_id, ordered_at DESC) WHERE reviewed_at IS NULL;

-- ---------------------------------------------------------------- the triggers
--
-- Everything a CHECK cannot see: what a row used to be, and whether a caller-supplied id
-- points at something related to the row it sits on. **"A pair of caller-supplied ids that
-- nothing relates is two halves of a control"** is this repository's own standard, and this
-- module has more of those pairs than any before it -- a decision names a point, a zone, a
-- credential, a person, a policy and a snapshot, and five of the six could be another
-- tenant's business entirely if nothing compared them.

CREATE OR REPLACE FUNCTION plt01.acc_zone_is_one_way()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF NEW.status <> OLD.status AND NOT (OLD.status = 'active' AND NEW.status = 'retired')
       THEN
        RAISE EXCEPTION 'a zone does not move from % to %', OLD.status, NEW.status;
    END IF;
    IF NEW.location_id <> OLD.location_id OR NEW.zone_key <> OLD.zone_key THEN
        RAISE EXCEPTION
            'a zone keeps its building and its key; every decision ever made here names it';
    END IF;
    -- **Risk may be tightened and not loosened.** A gym that decides the weights room is
    -- high-risk is making an assessment; one that quietly moves it back is extending the
    -- life of every offline authorization issued for it afterwards, with no record that the
    -- assessment changed. Retire the zone and declare a new one.
    IF OLD.risk_class = 'high_risk' AND NEW.risk_class <> 'high_risk' THEN
        RAISE EXCEPTION
            'a high-risk zone is not re-classified in place; retire it and declare the '
            'replacement, so the assessment that changed is on the record';
    END IF;
    IF OLD.retired_at IS NOT NULL AND (
        NEW.retired_at IS DISTINCT FROM OLD.retired_at
        OR NEW.retired_by IS DISTINCT FROM OLD.retired_by) THEN
        RAISE EXCEPTION 'who retired this zone, and when, is recorded once';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER acc_zones_one_way
    BEFORE UPDATE ON plt01.acc_zones
    FOR EACH ROW EXECUTE FUNCTION plt01.acc_zone_is_one_way();

CREATE OR REPLACE FUNCTION plt01.acc_point_is_one_way()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF NEW.status <> OLD.status AND NOT (OLD.status = 'active' AND NEW.status = 'retired')
       THEN
        RAISE EXCEPTION 'an access point does not move from % to %', OLD.status, NEW.status;
    END IF;
    -- **A reader that changed direction rewrites what every past event meant.** An exit
    -- re-labelled an entry turns a building's occupancy inside out, retroactively, with
    -- nothing in the history saying so.
    IF NEW.zone_id <> OLD.zone_id OR NEW.device_id <> OLD.device_id
       OR NEW.direction <> OLD.direction THEN
        RAISE EXCEPTION
            'an access point keeps its zone, its device and the way it faces; a reader that '
            'moved is one re-commissioned, and the old row says what it was';
    END IF;
    IF OLD.retired_at IS NOT NULL AND (
        NEW.retired_at IS DISTINCT FROM OLD.retired_at
        OR NEW.retired_by IS DISTINCT FROM OLD.retired_by) THEN
        RAISE EXCEPTION 'who retired this access point, and when, is recorded once';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER acc_points_one_way
    BEFORE UPDATE ON plt01.acc_points
    FOR EACH ROW EXECUTE FUNCTION plt01.acc_point_is_one_way();

-- **An access point is a device that can actually move a barrier, and that is in service**,
-- both checked here rather than assumed: a point declared over a barcode scanner is a zone
-- whose policy nothing can enforce, and `emergency_unlock` would be sent to a device with no
-- door.
--
-- The state check was added after an HTTP test commissioned a point on a device that had been
-- registered and nothing else -- no safety profile, no commissioning tests, never activated.
-- MOD-021 still refused the unlock, so no door opened; what was created was **a point that
-- reads as commissioned and can never work**, and a decision taken at it returns `granted`
-- while nothing moves. That is the fabricated-evidence shape this codebase has been bitten by
-- repeatedly, and paragraph 4175 is the rule it offends: a failed or missing commissioning
-- blocks opening the access point in production, and declaring the point *is* putting it into
-- production.
--
-- `active` is MOD-021's own `enrollment.OPERABLE`, which is the state in which a device accepts
-- any command at all. A later quarantine does not retire the point, and should not: the point
-- is still correctly recorded, and `check_issue` refuses the command. What this refuses is
-- creating one that was never fit in the first place.
CREATE OR REPLACE FUNCTION plt01.acc_point_is_an_actuator()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    device_state text;
BEGIN
    -- `FOR UPDATE`, not `FOR SHARE`: two share locks do not conflict, so two inserters would
    -- each read a device nobody had quarantined yet and both commit. The rules file records
    -- this for MOD-019's capacity trigger and again for MOD-021's three.
    SELECT state INTO device_state FROM plt01.dev_devices
     WHERE tenant_id = NEW.tenant_id AND device_id = NEW.device_id
     FOR UPDATE;
    IF device_state IS NULL THEN
        RAISE EXCEPTION 'this access point cites a device that does not exist';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM plt01.dev_device_capabilities
         WHERE tenant_id = NEW.tenant_id AND device_id = NEW.device_id
           AND capability = 'access.actuate') THEN
        RAISE EXCEPTION
            'this device moves no barrier, so it is not an access point; a reader that only '
            'identifies belongs to a point whose barrier is another device';
    END IF;
    IF device_state <> 'active' THEN
        RAISE EXCEPTION
            'this device is %, so it is not in service; an access point is declared over a '
            'device that passed its commissioning and was activated, because a point that '
            'reads as commissioned and can never open is worse than no point',
            device_state;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER acc_points_actuator
    BEFORE INSERT ON plt01.acc_points
    FOR EACH ROW EXECUTE FUNCTION plt01.acc_point_is_an_actuator();

CREATE OR REPLACE FUNCTION plt01.acc_policy_is_one_way()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF NEW.status <> OLD.status AND NOT (
        (OLD.status = 'draft' AND NEW.status IN ('published', 'retired'))
        OR (OLD.status = 'published' AND NEW.status = 'retired')
    ) THEN
        RAISE EXCEPTION
            'an access policy does not move from % to %; a published one is what decisions '
            'were made against', OLD.status, NEW.status;
    END IF;
    -- **A published policy's terms are frozen.** Paragraph 1952 wants a decision to cite the
    -- exact version, and a version whose terms could still move is a citation of nothing.
    IF OLD.status <> 'draft' AND (
        NEW.opens_minute IS DISTINCT FROM OLD.opens_minute
        OR NEW.closes_minute IS DISTINCT FROM OLD.closes_minute
        OR NEW.requires_entitlement IS DISTINCT FROM OLD.requires_entitlement
        OR NEW.max_balance_minor IS DISTINCT FROM OLD.max_balance_minor
        OR NEW.min_age_years IS DISTINCT FROM OLD.min_age_years
        OR NEW.anti_passback_seconds IS DISTINCT FROM OLD.anti_passback_seconds
        OR NEW.capacity IS DISTINCT FROM OLD.capacity) THEN
        RAISE EXCEPTION
            'this policy is % and its terms are what decisions cite; a change is a new '
            'version', OLD.status;
    END IF;
    IF NEW.zone_id <> OLD.zone_id OR NEW.version <> OLD.version THEN
        RAISE EXCEPTION 'an access policy keeps its zone and its version number';
    END IF;
    IF OLD.published_at IS NOT NULL AND (
        NEW.published_at IS DISTINCT FROM OLD.published_at
        OR NEW.published_by IS DISTINCT FROM OLD.published_by
        OR NEW.publish_correlation_id IS DISTINCT FROM OLD.publish_correlation_id) THEN
        RAISE EXCEPTION 'who published this access policy, and when, is recorded once';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER acc_policies_one_way
    BEFORE UPDATE ON plt01.acc_policies
    FOR EACH ROW EXECUTE FUNCTION plt01.acc_policy_is_one_way();

CREATE OR REPLACE FUNCTION plt01.acc_credential_is_one_way()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF NEW.state <> OLD.state AND NOT (
        OLD.state = 'active' AND NEW.state IN ('revoked', 'expired')
    ) THEN
        RAISE EXCEPTION 'a credential does not move from % to %', OLD.state, NEW.state;
    END IF;
    -- **A credential keeps whose it is.** Re-pointing one at another member is handing that
    -- member's entitlements to whoever holds the card, with the card's own history intact --
    -- which is the single worst write available in this module.
    IF NEW.person_id <> OLD.person_id OR NEW.kind <> OLD.kind
       OR NEW.credential_digest <> OLD.credential_digest THEN
        RAISE EXCEPTION
            'a credential keeps its holder, its kind and what it is; a card issued to '
            'somebody else is a different credential';
    END IF;
    -- The epoch only goes up, for MOD-021's reason one layer over: a reader compares it
    -- numerically, so a lower number makes every stale snapshot look current.
    IF NEW.revocation_epoch < OLD.revocation_epoch THEN
        RAISE EXCEPTION
            'a revocation epoch does not go backwards; % is below %',
            NEW.revocation_epoch, OLD.revocation_epoch;
    END IF;
    IF OLD.revoked_at IS NOT NULL THEN
        RAISE EXCEPTION 'this credential is revoked and does not change again';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER acc_credentials_one_way
    BEFORE UPDATE ON plt01.acc_credentials
    FOR EACH ROW EXECUTE FUNCTION plt01.acc_credential_is_one_way();

-- **The correspondence trigger, which is most of this module's integrity.** A decision names
-- six things and five of them could be unrelated to each other and to the door the member is
-- standing at. Every one is compared.
CREATE OR REPLACE FUNCTION plt01.acc_decision_is_coherent()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    point_zone uuid;
    point_direction text;
    point_status text;
    credential_person uuid;
    policy_zone uuid;
    policy_status text;
BEGIN
    SELECT zone_id, direction, status
      INTO point_zone, point_direction, point_status
      FROM plt01.acc_points
     WHERE tenant_id = NEW.tenant_id AND point_id = NEW.point_id
     FOR UPDATE;
    IF point_zone IS NULL THEN
        RAISE EXCEPTION 'this decision cites an access point that does not exist';
    END IF;
    IF point_zone <> NEW.zone_id THEN
        RAISE EXCEPTION
            'this decision names a zone that is not the one its access point stands at';
    END IF;
    -- **An exit reader decides nothing.** Paragraph 4177 puts egress outside the Veyro
    -- application path, so there is no policy, no grace and no configuration that lets a
    -- decision be recorded against a door somebody is leaving through: the refusal is here,
    -- in the database, rather than in a service that could be bypassed.
    IF point_direction = 'exit' AND NEW.code <> 'point_not_an_entry' THEN
        RAISE EXCEPTION
            'this access point faces out; egress is never conditioned on membership, '
            'reachability or software authorization, so nothing decides here';
    END IF;
    IF point_status <> 'active' AND NEW.code NOT IN ('device_untrusted', 'snapshot_stale')
       THEN
        RAISE EXCEPTION 'this access point is %; it decides nothing', point_status;
    END IF;
    IF NEW.credential_id IS NOT NULL THEN
        SELECT person_id INTO credential_person FROM plt01.acc_credentials
         WHERE tenant_id = NEW.tenant_id AND credential_id = NEW.credential_id;
        IF credential_person IS NULL THEN
            RAISE EXCEPTION 'this decision cites a credential that does not exist';
        END IF;
        -- **The person on the row is the credential's holder, not a caller's claim.** A
        -- decision naming one member's credential and another's person is a grant recorded
        -- against somebody who was not there -- and anti-passback, occupancy and every
        -- report read the person.
        IF NEW.person_id IS NOT NULL AND NEW.person_id <> credential_person THEN
            RAISE EXCEPTION
                'this decision names a person who does not hold the credential it cites';
        END IF;
    END IF;
    IF NEW.policy_id IS NOT NULL THEN
        SELECT zone_id, status INTO policy_zone, policy_status FROM plt01.acc_policies
         WHERE tenant_id = NEW.tenant_id AND policy_id = NEW.policy_id;
        IF policy_zone IS NULL THEN
            RAISE EXCEPTION 'this decision cites a policy that does not exist';
        END IF;
        IF policy_zone <> NEW.zone_id THEN
            RAISE EXCEPTION
                'this decision cites a policy belonging to another zone';
        END IF;
        IF policy_status = 'draft' THEN
            RAISE EXCEPTION
                'this decision cites a policy nobody published; a draft is terms somebody '
                'is still writing';
        END IF;
    END IF;
    -- **A grant names the policy it passed.** The only grants without one are an override,
    -- which is a decision made *against* the policy, and that is why it has its own code.
    IF NEW.granted AND NEW.code = 'granted' AND NEW.policy_id IS NULL THEN
        RAISE EXCEPTION
            'a granted decision cites the policy version it satisfied; one that cites none '
            'is a door that opened on nobody''s terms';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER acc_decisions_coherent
    BEFORE INSERT ON plt01.acc_decisions
    FOR EACH ROW EXECUTE FUNCTION plt01.acc_decision_is_coherent();

-- A decision is evidence. Nothing in this build changes one, and the grant says so; the
-- trigger is what holds for the writer that is not the service.
CREATE OR REPLACE FUNCTION plt01.acc_decision_is_final()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    RAISE EXCEPTION
        'an access decision is what was decided at the door; a later view of it is another '
        'decision, not an edit of this one';
END;
$$;
CREATE TRIGGER acc_decisions_final
    BEFORE UPDATE ON plt01.acc_decisions
    FOR EACH ROW EXECUTE FUNCTION plt01.acc_decision_is_final();

-- **An event agrees with the decision it cites, and with the door it happened at.**
CREATE OR REPLACE FUNCTION plt01.acc_event_is_coherent()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    point_zone uuid;
    point_direction text;
    decision_point uuid;
    decision_person uuid;
    decision_granted boolean;
    credential_person uuid;
BEGIN
    SELECT zone_id, direction INTO point_zone, point_direction FROM plt01.acc_points
     WHERE tenant_id = NEW.tenant_id AND point_id = NEW.point_id
     FOR UPDATE;
    IF point_zone IS NULL THEN
        RAISE EXCEPTION 'this access event cites an access point that does not exist';
    END IF;
    IF point_zone <> NEW.zone_id THEN
        RAISE EXCEPTION
            'this access event names a zone that is not the one its point stands at';
    END IF;
    -- A reader that faces one way cannot have seen somebody go the other. `both` is a
    -- turnstile that reads in each direction and sees either.
    IF point_direction <> 'both' AND point_direction <> NEW.direction THEN
        RAISE EXCEPTION
            'this access point faces %, so it did not see an %', point_direction,
            NEW.direction;
    END IF;
    IF NEW.credential_id IS NOT NULL THEN
        SELECT person_id INTO credential_person FROM plt01.acc_credentials
         WHERE tenant_id = NEW.tenant_id AND credential_id = NEW.credential_id;
        IF credential_person IS NULL THEN
            RAISE EXCEPTION 'this access event cites a credential that does not exist';
        END IF;
        IF NEW.person_id IS NOT NULL AND NEW.person_id <> credential_person THEN
            RAISE EXCEPTION
                'this access event names a person who does not hold the credential it cites';
        END IF;
    END IF;
    IF NEW.decision_id IS NOT NULL THEN
        SELECT point_id, person_id, granted
          INTO decision_point, decision_person, decision_granted
          FROM plt01.acc_decisions
         WHERE tenant_id = NEW.tenant_id AND decision_id = NEW.decision_id;
        IF decision_point IS NULL THEN
            RAISE EXCEPTION 'this access event cites a decision that does not exist';
        END IF;
        IF decision_point <> NEW.point_id THEN
            RAISE EXCEPTION
                'this access event cites a decision made at another access point';
        END IF;
        IF decision_person IS DISTINCT FROM NEW.person_id THEN
            RAISE EXCEPTION
                'this access event cites a decision about somebody else';
        END IF;
        -- **An entry cannot cite a refusal.** A row saying somebody walked in on a decision
        -- that turned them away is the one shape that would make every occupancy and
        -- anti-passback read wrong in the direction nobody checks.
        IF NEW.direction = 'entry' AND NOT decision_granted THEN
            RAISE EXCEPTION
                'this entry cites a decision that refused it; a member who came in anyway '
                'is a door held open, which is an incident rather than an entry';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER acc_events_coherent
    BEFORE INSERT ON plt01.acc_events
    FOR EACH ROW EXECUTE FUNCTION plt01.acc_event_is_coherent();

-- An event's own facts are final; only reconciliation writes, and it writes once.
CREATE OR REPLACE FUNCTION plt01.acc_event_is_one_way()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF NEW.point_id <> OLD.point_id OR NEW.zone_id <> OLD.zone_id
       OR NEW.direction <> OLD.direction OR NEW.occurred_at <> OLD.occurred_at
       OR NEW.credential_id IS DISTINCT FROM OLD.credential_id
       OR NEW.person_id IS DISTINCT FROM OLD.person_id
       OR NEW.decision_id IS DISTINCT FROM OLD.decision_id
       OR NEW.source <> OLD.source
       OR NEW.local_sequence IS DISTINCT FROM OLD.local_sequence THEN
        RAISE EXCEPTION
            'an access event is what a reader saw; reconciliation flags it and never '
            'rewrites it';
    END IF;
    IF OLD.reconciled_at IS NOT NULL THEN
        RAISE EXCEPTION
            'this event was reconciled on % and the outcome is recorded once',
            OLD.reconciled_at;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER acc_events_one_way
    BEFORE UPDATE ON plt01.acc_events
    FOR EACH ROW EXECUTE FUNCTION plt01.acc_event_is_one_way();

-- An emergency unlock's order is final; the review is written once, by somebody else.
CREATE OR REPLACE FUNCTION plt01.acc_emergency_is_one_way()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF NEW.zone_id <> OLD.zone_id OR NEW.reason <> OLD.reason
       OR NEW.ordered_at <> OLD.ordered_at OR NEW.ordered_by <> OLD.ordered_by
       OR NEW.points_released <> OLD.points_released THEN
        RAISE EXCEPTION
            'what was released, where, why and by whom is what an emergency unlock is; a '
            'later view of it is the review';
    END IF;
    IF OLD.reviewed_at IS NOT NULL THEN
        RAISE EXCEPTION 'this emergency unlock was reviewed on %', OLD.reviewed_at;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER acc_emergency_unlocks_one_way
    BEFORE UPDATE ON plt01.acc_emergency_unlocks
    FOR EACH ROW EXECUTE FUNCTION plt01.acc_emergency_is_one_way();

-- -------------------------------------------- MOD-021's vocabulary gains one action
--
-- **An emergency release is not an unlock, and the difference is which way the door is
-- being opened for.** `unlock_momentary` admits somebody, so paragraph 4175 gates it on a
-- complete commissioning record -- a door whose fire-alarm input failed its test must not
-- be opened for a member. An emergency unlock is egress, and paragraph 4177 puts egress
-- outside the Veyro application path entirely: refusing to release a door *because its
-- safety test failed* is exactly backwards, since a failed safety test is the strongest
-- possible reason to want it open.
--
-- So the action is added here, where the module that needs it lives, and the capability
-- trigger is replaced to apply the commissioning gate to `unlock_momentary` only. Nothing
-- else about MOD-021 moves: `safety.HOLD_COMMANDS` still has no intersection with the
-- vocabulary, and a release is the opposite of a hold.
ALTER TABLE plt01.dev_commands DROP CONSTRAINT dev_commands_action;
ALTER TABLE plt01.dev_commands ADD CONSTRAINT dev_commands_action CHECK (action IN (
    'unlock_momentary', 'emergency_unlock', 'reboot', 'diagnostics', 'sync_now',
    'update_firmware', 'rotate_certificate', 'set_maintenance', 'clear_maintenance',
    'report_peripherals'));

-- An emergency release is deliverable for five minutes rather than one: the member at the
-- turnstile is gone in a minute, and an evacuation is not.
ALTER TABLE plt01.dev_commands ADD CONSTRAINT dev_commands_emergency_window_is_five_minutes
    CHECK (action <> 'emergency_unlock'
           OR expires_at - issued_at <= interval '300 seconds');

CREATE OR REPLACE FUNCTION plt01.dev_command_is_within_capability()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    needs text;
    device_state text;
    passing integer;
BEGIN
    SELECT state INTO device_state FROM plt01.dev_devices
     WHERE tenant_id = NEW.tenant_id AND device_id = NEW.device_id
     FOR UPDATE;
    IF device_state IS NULL THEN
        RAISE EXCEPTION 'this command cites a device that does not exist';
    END IF;
    IF device_state <> 'active' THEN
        RAISE EXCEPTION
            'this device is %; a command goes to a device in service', device_state;
    END IF;
    needs := CASE NEW.action
        WHEN 'unlock_momentary' THEN 'access.actuate'
        WHEN 'emergency_unlock' THEN 'access.actuate'
        WHEN 'report_peripherals' THEN 'telemetry'
        ELSE NULL END;
    IF needs IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM plt01.dev_device_capabilities
         WHERE tenant_id = NEW.tenant_id AND device_id = NEW.device_id
           AND capability = needs) THEN
        RAISE EXCEPTION
            'this device does not declare %, so it cannot be asked to %', needs, NEW.action;
    END IF;
    IF NEW.action = 'unlock_momentary' AND NOT EXISTS (
        SELECT 1 FROM plt01.dev_safety_profiles
         WHERE tenant_id = NEW.tenant_id AND device_id = NEW.device_id
           AND superseded_at IS NULL) THEN
        RAISE EXCEPTION
            'this access point has no live hardware safety profile, so nothing here records '
            'how its egress behaves';
    END IF;
    IF NEW.action = 'unlock_momentary' THEN
        SELECT count(*) INTO passing FROM (
            SELECT DISTINCT ON (test_name) test_name, outcome
            FROM plt01.dev_commissioning_tests
            WHERE tenant_id = NEW.tenant_id AND device_id = NEW.device_id
              AND test_name IN ('power_loss', 'edge_agent_crash', 'controller_disconnect',
                                'fire_alarm_input', 'emergency_unlock', 'recovery',
                                'manual_override')
            ORDER BY test_name, tested_at DESC, test_id DESC) latest
         WHERE outcome = 'passed';
        IF passing <> 7 THEN
            RAISE EXCEPTION
                'this access point has % of 7 passing commissioning tests; a failed or '
                'missing safety test blocks opening it', passing;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

-- ----------------------------------------------------------------- the grants
--
-- **Every "insert-only" claim above is a missing grant, and that is where it lives.** No
-- runtime role gets DELETE, TRUNCATE or REFERENCES on anything here: a decision is the only
-- record of why a door opened, and an event is the only record that somebody walked through.

GRANT SELECT, INSERT ON plt01.acc_zones TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (display_name, status, retired_at, retired_by, retire_reason,
              retire_correlation_id, risk_class)
    ON plt01.acc_zones TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.acc_points TO veyro_cp_app, veyro_cp_worker;
-- Not `zone_id`, `device_id` or `direction`: the trigger refuses those and the grant means
-- it never has to.
GRANT UPDATE (display_name, status, retired_at, retired_by, retire_reason,
              retire_correlation_id)
    ON plt01.acc_points TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.acc_policies TO veyro_cp_app, veyro_cp_worker;
-- **The lifecycle only.** Not one term: a published policy is what decisions cite, and the
-- draft's terms are settled by the publication rather than edited after it.
GRANT UPDATE (status, published_at, published_by, publish_correlation_id, retired_at,
              retired_by, retire_reason, retire_correlation_id)
    ON plt01.acc_policies TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.acc_credentials TO veyro_cp_app, veyro_cp_worker;
-- **Not `person_id`, `kind` or `credential_digest`.** Re-pointing a credential at another
-- member hands that member's entitlements to whoever holds the card, with the card's own
-- history intact.
GRANT UPDATE (state, revocation_epoch, expires_at, revoked_at, revoked_by, revoke_reason,
              revoke_correlation_id)
    ON plt01.acc_credentials TO veyro_cp_app, veyro_cp_worker;

-- **No UPDATE at all.** A decision is what was decided at the door.
GRANT SELECT, INSERT ON plt01.acc_decisions TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.acc_events TO veyro_cp_app, veyro_cp_worker;
-- The reconciliation only, which flags and never rewrites.
GRANT UPDATE (reconciled_outcome, reconciled_at, reconciled_by, reconcile_correlation_id)
    ON plt01.acc_events TO veyro_cp_app, veyro_cp_worker;

-- **DELETE on the replay cache, which is the one place in this build that has it.** Every
-- other table here is evidence; this one is a window of nonces that is useless the moment it
-- expires, and a table with no DELETE that grows per presentation would be the unbounded
-- primitive MOD-011's rate limiter argues against. `veyro_cp_app` is excluded -- CLAUDE.md
-- states that absolutely -- so the sweep is the worker's, and the worker is what this build
-- does not have.
GRANT SELECT, INSERT ON plt01.acc_replay_tokens TO veyro_cp_app, veyro_cp_worker;
GRANT DELETE ON plt01.acc_replay_tokens TO veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.acc_emergency_unlocks TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (reviewed_at, reviewed_by, review_note, review_correlation_id)
    ON plt01.acc_emergency_unlocks TO veyro_cp_app, veyro_cp_worker;

REVOKE ALL ON FUNCTION plt01.acc_zone_is_one_way() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.acc_point_is_one_way() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.acc_point_is_an_actuator() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.acc_policy_is_one_way() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.acc_credential_is_one_way() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.acc_decision_is_coherent() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.acc_decision_is_final() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.acc_event_is_coherent() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.acc_event_is_one_way() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.acc_emergency_is_one_way() FROM PUBLIC;
