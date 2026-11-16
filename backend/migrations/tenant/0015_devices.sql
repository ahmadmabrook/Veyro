-- MOD-021 ECO-03: hardware abstraction, the edge runtime's contract and the device fleet.
--
-- **Twelve `dev_` tables, under the same forced RLS as every other `plt01` table.** The pattern in
-- `0001_organization_hierarchy.sql` is copied exactly and each of its four parts is
-- load-bearing: `tenant_id NOT NULL`, a tenant-leading primary key, ENABLE *and* FORCE row
-- level security, and a policy whose predicate is the approved one on both halves. A composite
-- foreign key carries `tenant_id` into every parent reference.
--
-- **The registry is tenant-scoped, which is paragraph 3063's own classification**
-- ("Confidential/tenant-scoped") and is why the device type lives here rather than on the
-- platform plane beside MOD-012's integration definitions. The cost is stated: two tenants
-- with the same model of turnstile each declare it. The alternative was worse -- the platform
-- plane is unauthenticated in this build, and a device type decides which *capabilities* a
-- tenant may then command, so putting it there would widen the gap MOD-012 already records.
--
-- **The capability vocabulary is code, not a table.** `app/devices/capabilities.py` is the
-- authority, the same deviation MOD-008 makes for permissions and MOD-010 for event types and
-- for the same reason: paragraph 3086's outcome is that "hardware vendors can change without
-- rewriting gym workflows", which only holds if a workflow names a capability rather than a
-- vendor -- and two tenants disagreeing about what `access.actuate` means is unresolvable by
-- anything but the code that drives it.
--
-- **No column in this schema can hold a private key, a certificate body or a signature**, and
-- there is no type one could go in. A certificate row carries a fingerprint and a `vault_ref`
-- locating material somewhere this build cannot read; a command and a snapshot carry a digest
-- this software computes and a `signature_ref` to a signature it cannot produce. That is
-- MOD-012's `vault_ref` shape for MOD-012's reason -- there is no key vault here, so the
-- honest table is one that *cannot* hold the secret rather than one that holds it carefully.
-- Check 103 pins every column list, because in all three places the control is an absence and
-- an absence is exactly what a later migration adds back.
--
-- **And section 16.4 is the half that matters most.** A failed or missing commissioning test
-- blocks opening an access point (paragraph 4175); a fail-secure barrier on an egress path is
-- refused outright rather than recorded with a warning (4172, 4173); and no row here can ask
-- a door to stay shut, because `commands.COMMAND_ACTIONS` has no such action and
-- `safety.HOLD_COMMANDS` is the list of words that are refused if somebody adds one. Those
-- are fire-code rules, so they are refusals with no permission that buys them rather than
-- settings somebody could change.

-- ------------------------------------------------------------- the device type
--
-- What somebody bought: a vendor's model, and the capabilities it can be asked for. Versioned
-- through `status` rather than a version number, because a device type is not re-priced the
-- way MOD-015's plan is -- a new model is a new type, and what changes about an existing one
-- is whether it may still be enrolled.
CREATE TABLE plt01.dev_device_types (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    type_id uuid NOT NULL DEFAULT gen_random_uuid(),
    type_code text NOT NULL,
    vendor text NOT NULL,
    model text NOT NULL,
    -- One of `capabilities.DEVICE_KINDS`. Constrained here as well, because a kind decides
    -- whether a safety profile is required and a row the code cannot interpret is a device
    -- nothing can command.
    kind text NOT NULL,
    display_name text NOT NULL,
    status text NOT NULL DEFAULT 'draft',
    published_at timestamptz,
    published_by uuid,
    publish_correlation_id uuid,
    retired_at timestamptz,
    retired_by uuid,
    retire_reason text,
    retire_correlation_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, type_id),
    UNIQUE (tenant_id, type_code),
    CONSTRAINT dev_device_types_status
        CHECK (status IN ('draft', 'published', 'retired')),
    CONSTRAINT dev_device_types_kind CHECK (kind IN (
        'turnstile', 'door_controller', 'biometric_terminal', 'scanner', 'kiosk', 'pos',
        'equipment', 'gateway')),
    CONSTRAINT dev_device_types_code_not_blank CHECK (type_code ~ '[^[:space:]]'),
    CONSTRAINT dev_device_types_vendor_not_blank CHECK (vendor ~ '[^[:space:]]'),
    CONSTRAINT dev_device_types_model_not_blank CHECK (model ~ '[^[:space:]]'),
    CONSTRAINT dev_device_types_name_not_blank CHECK (display_name ~ '[^[:space:]]'),
    -- A published type names who published it and when; MOD-008 audits denials rather than
    -- allowed acts and this module's role holds nothing in `iam`, so this row is the only
    -- record that somebody declared what a model of hardware may be asked to do.
    -- **Two acts by two people.** Declaring `access.actuate` is what makes a model of
    -- hardware commandable as a barrier, and publication freezes the capability set every
    -- unit afterwards snapshots -- so the author cannot settle their own declaration. This
    -- is the half the service cannot weaken, which is the whole lesson of MOD-016's
    -- discount approval and MOD-017's contract version.
    CONSTRAINT dev_device_types_publisher_is_not_author
        CHECK (published_by IS NULL OR published_by <> created_by),
    CONSTRAINT dev_device_types_publication_attributed CHECK (
        (published_at IS NULL AND published_by IS NULL AND publish_correlation_id IS NULL)
        OR (published_at IS NOT NULL AND published_by IS NOT NULL
            AND publish_correlation_id IS NOT NULL)),
    CONSTRAINT dev_device_types_published_is_published
        CHECK (status = 'draft' OR published_at IS NOT NULL),
    CONSTRAINT dev_device_types_retirement_attributed CHECK (
        (retired_at IS NULL AND retired_by IS NULL AND retire_reason IS NULL
         AND retire_correlation_id IS NULL)
        OR (retired_at IS NOT NULL AND retired_by IS NOT NULL
            AND coalesce(retire_reason, '') ~ '[^[:space:]]'
            AND retire_correlation_id IS NOT NULL)),
    CONSTRAINT dev_device_types_retired_is_retired
        CHECK ((status = 'retired') = (retired_at IS NOT NULL))
);
ALTER TABLE plt01.dev_device_types ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.dev_device_types FORCE ROW LEVEL SECURITY;
CREATE POLICY dev_device_types_tenant ON plt01.dev_device_types
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- The capabilities a type declares. **Insert-only, and frozen once published**, which is the
-- control MOD-012's review found missing on its own definition entries: a unique index on the
-- name stops re-declaring one and stops nothing else, so a *new* capability could be added to
-- a type devices were already enrolled against -- and a device snapshots its type at
-- registration, so the blast radius is new devices authorised to do more than the model
-- somebody reviewed. The trigger below refuses any write once the type is out of draft.
CREATE TABLE plt01.dev_type_capabilities (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    type_id uuid NOT NULL,
    capability text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, type_id, capability),
    FOREIGN KEY (tenant_id, type_id)
        REFERENCES plt01.dev_device_types (tenant_id, type_id),
    -- The seven of `capabilities.CAPABILITIES`. Named here as well as in code because a value
    -- outside them is a capability no command can ask for, so a device declaring one looks
    -- able to do something this software cannot drive.
    CONSTRAINT dev_type_capabilities_known CHECK (capability IN (
        'credential.read', 'access.actuate', 'biometric.match', 'scan', 'print', 'payment',
        'telemetry'))
);
ALTER TABLE plt01.dev_type_capabilities ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.dev_type_capabilities FORCE ROW LEVEL SECURITY;
CREATE POLICY dev_type_capabilities_tenant ON plt01.dev_type_capabilities
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ----------------------------------------------------------------- the device
--
-- One physical unit, enrolled against a type and assigned to a location. Paragraph 3077:
-- "Device enrollment, tenant/location assignment, certificate, firmware, configuration and
-- remote revoke."
CREATE TABLE plt01.dev_devices (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    device_id uuid NOT NULL DEFAULT gen_random_uuid(),
    type_id uuid NOT NULL,
    location_id uuid NOT NULL,
    -- The vendor's own identifier for the unit, which is what somebody reads off the case
    -- when they are standing in front of it. Unique per tenant, so two rows cannot claim one
    -- box -- which is how a replacement workflow loses track of which is live.
    serial_number text NOT NULL,
    display_name text NOT NULL,
    state text NOT NULL DEFAULT 'registered',
    -- `jsonb` the tenant supplies. **Values are not inspected**, which is the same disclosure
    -- MOD-012 makes about an install's config: a field named `api_key` would be accepted, and
    -- the column has an UPDATE grant so unlike an event payload it is at least erasable.
    config jsonb NOT NULL DEFAULT '{}'::jsonb,
    -- When this device last reported. **Reachability is derived from it and never stored**:
    -- a cached `online` flag is MOD-018's cached balance applied to a boolean, and the
    -- disagreement surfaces as somebody driving to a club whose turnstile is fine.
    last_seen_at timestamptz,
    -- Paragraph 4179's counter. A gateway holding an older epoch has missed a revocation,
    -- which is a different failure from an expired snapshot and is reported as one. Monotonic
    -- by trigger, because rewinding it is how a revoked credential starts working again.
    revocation_epoch integer NOT NULL DEFAULT 0,
    -- Paragraph 3092's optimistic concurrency. Two operators editing one device is ordinary;
    -- last-write-wins discards whichever finished first and leaves no trace.
    version integer NOT NULL DEFAULT 1,
    activated_at timestamptz,
    activated_by uuid,
    activate_correlation_id uuid,
    -- **And the last return to service, which is a different decision.** `activated_*` is
    -- the first one and is final by trigger, correctly: it is the attribution paragraph
    -- 4175's gate rests on. But `activate_device` re-runs that gate on every pass, so a
    -- quarantine-and-return -- this module's own replacement workflow, and what a failed
    -- fire-alarm re-test now forces -- is another passage through it. The first version
    -- wrote nothing on that pass, so a live door's fire-code attribution named whoever
    -- activated it months earlier, and the trigger made it impossible to correct.
    reactivated_at timestamptz,
    reactivated_by uuid,
    reactivate_correlation_id uuid,
    quarantined_at timestamptz,
    quarantined_by uuid,
    quarantine_reason text,
    quarantine_correlation_id uuid,
    retired_at timestamptz,
    retired_by uuid,
    retire_reason text,
    retire_correlation_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, device_id),
    UNIQUE (tenant_id, serial_number),
    FOREIGN KEY (tenant_id, type_id)
        REFERENCES plt01.dev_device_types (tenant_id, type_id),
    FOREIGN KEY (tenant_id, location_id)
        REFERENCES plt01.locations (tenant_id, location_id),
    CONSTRAINT dev_devices_state CHECK (state IN (
        'registered', 'provisioned', 'active', 'maintenance', 'quarantined', 'retired')),
    CONSTRAINT dev_devices_serial_not_blank CHECK (serial_number ~ '[^[:space:]]'),
    CONSTRAINT dev_devices_name_not_blank CHECK (display_name ~ '[^[:space:]]'),
    CONSTRAINT dev_devices_epoch_sane
        CHECK (revocation_epoch >= 0 AND revocation_epoch <= 2000000000),
    CONSTRAINT dev_devices_version_positive CHECK (version >= 1),
    CONSTRAINT dev_devices_config_is_an_object CHECK (jsonb_typeof(config) = 'object'),
    CONSTRAINT dev_devices_activation_attributed CHECK (
        (activated_at IS NULL AND activated_by IS NULL
         AND activate_correlation_id IS NULL)
        OR (activated_at IS NOT NULL AND activated_by IS NOT NULL
            AND activate_correlation_id IS NOT NULL)),
    -- **A device that has ever been live keeps the record of it.** Not a biconditional with
    -- the state: a device goes to maintenance and back, and `activated_at` is when it first
    -- opened rather than when it was last switched on -- MOD-018's `closed_at` lesson, where
    -- a biconditional made the one legitimate re-entry unsatisfiable.
    CONSTRAINT dev_devices_live_was_activated
        CHECK (state NOT IN ('active', 'maintenance') OR activated_at IS NOT NULL),
    CONSTRAINT dev_devices_reactivation_attributed CHECK (
        (reactivated_at IS NULL AND reactivated_by IS NULL
         AND reactivate_correlation_id IS NULL)
        OR (reactivated_at IS NOT NULL AND reactivated_by IS NOT NULL
            AND reactivate_correlation_id IS NOT NULL)),
    -- A device cannot have returned to service before it first entered it.
    CONSTRAINT dev_devices_reactivation_ordered CHECK (
        reactivated_at IS NULL OR
        (activated_at IS NOT NULL AND reactivated_at >= activated_at)),
    CONSTRAINT dev_devices_quarantine_attributed CHECK (
        (quarantined_at IS NULL AND quarantined_by IS NULL AND quarantine_reason IS NULL
         AND quarantine_correlation_id IS NULL)
        OR (quarantined_at IS NOT NULL AND quarantined_by IS NOT NULL
            AND coalesce(quarantine_reason, '') ~ '[^[:space:]]'
            AND quarantine_correlation_id IS NOT NULL)),
    CONSTRAINT dev_devices_quarantined_is_quarantined
        CHECK (state <> 'quarantined' OR quarantined_at IS NOT NULL),
    CONSTRAINT dev_devices_retirement_attributed CHECK (
        (retired_at IS NULL AND retired_by IS NULL AND retire_reason IS NULL
         AND retire_correlation_id IS NULL)
        OR (retired_at IS NOT NULL AND retired_by IS NOT NULL
            AND coalesce(retire_reason, '') ~ '[^[:space:]]'
            AND retire_correlation_id IS NOT NULL)),
    CONSTRAINT dev_devices_retired_is_retired
        CHECK ((state = 'retired') = (retired_at IS NOT NULL))
);
ALTER TABLE plt01.dev_devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.dev_devices FORCE ROW LEVEL SECURITY;
CREATE POLICY dev_devices_tenant ON plt01.dev_devices
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE INDEX dev_devices_by_location
    ON plt01.dev_devices (tenant_id, location_id, state);
CREATE INDEX dev_devices_by_last_seen
    ON plt01.dev_devices (tenant_id, state, last_seen_at);

-- **The device's own capabilities, snapshotted from its type at registration.** MOD-012's
-- install shape and for its reason: somebody has to be able to answer "what was this unit
-- authorised to do in March" without a join to a type whose declaration has since moved, and
-- a command is bounded by *this* list rather than by the type's current one. Insert-only, and
-- the trigger below refuses one the type does not declare.
CREATE TABLE plt01.dev_device_capabilities (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    device_id uuid NOT NULL,
    capability text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, device_id, capability),
    FOREIGN KEY (tenant_id, device_id)
        REFERENCES plt01.dev_devices (tenant_id, device_id)
    -- **No domain CHECK on `capability` here, deliberately.** It would be subsumed: the
    -- trigger below refuses any capability the device's *type* does not declare, and
    -- `dev_type_capabilities_known` already bounds what a type may declare -- so no row
    -- can reach a CHECK on this column with that trigger as anything but the second
    -- refusal. MOD-020's lesson ("a correspondence trigger makes every bound on the column
    -- it relates derived") and MOD-016's ("a constraint subsumed by a sibling should be
    -- deleted, not tested harder"), arrived at from the same direction. The bound lives on
    -- `dev_type_capabilities`, where it has an isolating case.
);
ALTER TABLE plt01.dev_device_capabilities ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.dev_device_capabilities FORCE ROW LEVEL SECURITY;
CREATE POLICY dev_device_capabilities_tenant ON plt01.dev_device_capabilities
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ------------------------------------------------------------ the certificate
--
-- Paragraph 3083, a Critical Control: "Devices authenticate with rotating certificates;
-- default credentials are forbidden."
--
-- **There is no column here a private key or a certificate body could go in**, and that is
-- the control rather than a convention: `vault_ref` locates the material somewhere this build
-- cannot read, and it has to *look* like a locator -- MOD-012 shipped a `vault_ref` that was
-- merely non-blank, which made a live API key a valid "vault reference" and the absence of a
-- secret column a naming convention. Check 103 asserts the column list in full and tries to
-- add one.
--
-- **Rotation overlaps.** The outgoing certificate becomes `superseded` and stays honoured
-- until its own expiry, because a device whose certificate was replaced the instant the new
-- one was issued is locked out for as long as it takes to receive it -- which for a gateway
-- on a flaky link is long enough to shut a club. `revoked` is the other path and is immediate:
-- that is the difference between the two states and the reason both exist.
CREATE TABLE plt01.dev_certificates (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    certificate_id uuid NOT NULL DEFAULT gen_random_uuid(),
    device_id uuid NOT NULL,
    -- Normalised lowercase hex, which is what the unique index sees: two spellings of one
    -- fingerprint must not be two rows, and the forbidden-default list is checked against the
    -- normalised value because the default somebody pastes is `DE:AD:BE:EF:...`.
    fingerprint text NOT NULL,
    vault_ref text NOT NULL,
    state text NOT NULL DEFAULT 'pending',
    not_before timestamptz NOT NULL,
    not_after timestamptz NOT NULL,
    superseded_by uuid,
    superseded_at timestamptz,
    revoked_at timestamptz,
    revoked_by uuid,
    revoke_reason text,
    revoke_correlation_id uuid,
    issued_at timestamptz NOT NULL DEFAULT now(),
    issued_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, certificate_id),
    -- One row per fingerprint per tenant. **This is the other half of "default credentials are
    -- forbidden"**: the forbidden list catches the placeholder, and this catches ten thousand
    -- units sharing whatever their vendor actually printed.
    UNIQUE (tenant_id, fingerprint),
    FOREIGN KEY (tenant_id, device_id)
        REFERENCES plt01.dev_devices (tenant_id, device_id),
    -- **Deferred, because a rotation points the outgoing certificate at its replacement
    -- before that row exists.** The alternative orders all fail: inserting the new one first
    -- violates `one_active_per_device`, and setting `superseded_at` without `superseded_by`
    -- violates the pairing beside it. Deferring the *reference* keeps every other rule true
    -- at every statement and makes the pointer true at commit, which is what matters.
    FOREIGN KEY (tenant_id, superseded_by)
        REFERENCES plt01.dev_certificates (tenant_id, certificate_id)
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT dev_certificates_state
        CHECK (state IN ('pending', 'active', 'superseded', 'revoked')),
    -- 32 to 128 lowercase hex characters: a shorter value is not a digest of anything and the
    -- case is fixed so the unique index cannot be defeated by shouting.
    CONSTRAINT dev_certificates_fingerprint_shape
        CHECK (fingerprint ~ '^[0-9a-f]{32,128}$'),
    -- **A locator, not a secret.** `uri:`, `vault:` or a path -- something that names where
    -- the material is. A sixteen-digit number does not match this, which is the point.
    CONSTRAINT dev_certificates_vault_ref_is_a_locator
        CHECK (vault_ref ~ '^[a-z][a-z0-9+.-]*:[^[:space:]]+$'),
    -- **No `not_after > not_before` here.** It is subsumed: `lifetime_sane` below requires
    -- at least twenty-four hours between them, which refuses every row this would. A
    -- constraint with no isolating case is deleted rather than tested harder -- MOD-016's
    -- `cat_eligibility_rules_kind`, MOD-020's four copied policy bounds.
    -- A day to a year: paragraph 3083's word is "rotating", and both bounds are the ones
    -- `certificates.MIN_LIFETIME` and `MAX_LIFETIME` state.
    CONSTRAINT dev_certificates_lifetime_sane CHECK (
        not_after - not_before >= interval '24 hours'
        AND not_after - not_before <= interval '366 days'),
    CONSTRAINT dev_certificates_not_self CHECK (superseded_by IS DISTINCT FROM certificate_id),
    CONSTRAINT dev_certificates_supersession_paired
        CHECK ((superseded_by IS NULL) = (superseded_at IS NULL)),
    CONSTRAINT dev_certificates_superseded_is_superseded
        CHECK (state <> 'superseded' OR superseded_at IS NOT NULL),
    CONSTRAINT dev_certificates_revocation_attributed CHECK (
        (revoked_at IS NULL AND revoked_by IS NULL AND revoke_reason IS NULL
         AND revoke_correlation_id IS NULL)
        OR (revoked_at IS NOT NULL AND revoked_by IS NOT NULL
            AND coalesce(revoke_reason, '') ~ '[^[:space:]]'
            AND revoke_correlation_id IS NOT NULL)),
    CONSTRAINT dev_certificates_revoked_is_revoked
        CHECK ((state = 'revoked') = (revoked_at IS NOT NULL))
);
ALTER TABLE plt01.dev_certificates ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.dev_certificates FORCE ROW LEVEL SECURITY;
CREATE POLICY dev_certificates_tenant ON plt01.dev_certificates
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
-- **One live certificate per device.** A device with two active certificates is a device whose
-- rotation did not finish, and the next rotation would have to guess which it is replacing.
CREATE UNIQUE INDEX dev_certificates_one_active_per_device
    ON plt01.dev_certificates (tenant_id, device_id)
    WHERE state = 'active';

-- --------------------------------------------------- the hardware safety profile
--
-- TSD section 16.4, paragraph 4172: "Every access point is commissioned with a hardware safety
-- profile: fail-safe, fail-secure or mechanical-free-egress according to door type, fire code,
-- landlord/civil-defence requirements and vendor certification. Software cannot override
-- required egress behavior."
--
-- **Insert-only in its claims**, because the row is what a commissioning certificate is
-- checked against later: a profile somebody could edit is a building whose records pass an
-- audit it would fail. Re-commissioning is a new row that supersedes, and the supersession is
-- final by trigger.
--
-- **The three booleans are claims this software cannot verify**, and that is said rather than
-- implied: whether a fire-alarm release is wired outside the application path is a physical
-- fact about a building. What the row does is make the claim an attributed record a named
-- person made at a time, and `dev_commissioning_tests` beside it is what has to pass before
-- the access point may open at all.
CREATE TABLE plt01.dev_safety_profiles (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    profile_id uuid NOT NULL DEFAULT gen_random_uuid(),
    device_id uuid NOT NULL,
    profile text NOT NULL,
    on_egress_path boolean NOT NULL,
    fire_release_is_independent boolean NOT NULL,
    local_emergency_input boolean NOT NULL,
    -- A locator for the certification the commissioner holds -- a vendor certificate, a fire
    -- officer's sign-off. Shaped like a reference for `vault_ref`'s reason: a free-text column
    -- beside a safety claim is where somebody writes the claim instead of filing it.
    evidence_ref text NOT NULL,
    door_description text NOT NULL,
    superseded_at timestamptz,
    superseded_by uuid,
    supersede_correlation_id uuid,
    commissioned_at timestamptz NOT NULL DEFAULT now(),
    commissioned_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, profile_id),
    FOREIGN KEY (tenant_id, device_id)
        REFERENCES plt01.dev_devices (tenant_id, device_id),
    -- Deferred for `dev_certificates`' reason: a re-commissioning supersedes the live
    -- profile before inserting its replacement, because `one_live_per_device` admits exactly
    -- one at every statement.
    FOREIGN KEY (tenant_id, superseded_by)
        REFERENCES plt01.dev_safety_profiles (tenant_id, profile_id)
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT dev_safety_profiles_profile
        CHECK (profile IN ('fail_safe', 'fail_secure', 'mechanical_free_egress')),
    -- **The constraint that is the fire code.** A fail-secure barrier on an egress path holds
    -- the door shut when the power fails, and an egress path without an independent fire
    -- release or a local emergency input is egress conditioned on this software. Refused by
    -- the database, so a writer that is not the service cannot record one either.
    CONSTRAINT dev_safety_profiles_egress_is_never_software_gated CHECK (
        on_egress_path = false
        OR (profile IN ('fail_safe', 'mechanical_free_egress')
            AND fire_release_is_independent = true
            AND local_emergency_input = true)),
    CONSTRAINT dev_safety_profiles_evidence_is_a_locator
        CHECK (evidence_ref ~ '^[a-z][a-z0-9+.-]*:[^[:space:]]+$'),
    CONSTRAINT dev_safety_profiles_door_described
        CHECK (door_description ~ '[^[:space:]]'),
    CONSTRAINT dev_safety_profiles_not_self
        CHECK (superseded_by IS DISTINCT FROM profile_id),
    CONSTRAINT dev_safety_profiles_supersession_attributed CHECK (
        (superseded_at IS NULL AND superseded_by IS NULL
         AND supersede_correlation_id IS NULL)
        OR (superseded_at IS NOT NULL AND superseded_by IS NOT NULL
            AND supersede_correlation_id IS NOT NULL))
);
ALTER TABLE plt01.dev_safety_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.dev_safety_profiles FORCE ROW LEVEL SECURITY;
CREATE POLICY dev_safety_profiles_tenant ON plt01.dev_safety_profiles
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE UNIQUE INDEX dev_safety_profiles_one_live_per_device
    ON plt01.dev_safety_profiles (tenant_id, device_id)
    WHERE superseded_at IS NULL;

-- --------------------------------------------------- the commissioning record
--
-- Paragraph 4175: "Commissioning tests power loss, edge-agent crash, controller disconnect,
-- fire-alarm input, emergency unlock, recovery and manual override. **A failed safety test
-- blocks opening the access point in production.**"
--
-- Insert-only, so a failure cannot be edited into a pass. A re-test after a repair is another
-- row, and `safety.may_go_live` reads the latest per test name -- which is what makes a repair
-- possible without rewriting history.
CREATE TABLE plt01.dev_commissioning_tests (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    test_id uuid NOT NULL DEFAULT gen_random_uuid(),
    device_id uuid NOT NULL,
    test_name text NOT NULL,
    outcome text NOT NULL,
    -- What happened, in the commissioner's words. Required for a failure, because a failed
    -- safety test that says nothing is a door nobody can repair.
    detail text,
    tested_at timestamptz NOT NULL DEFAULT now(),
    tested_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, test_id),
    FOREIGN KEY (tenant_id, device_id)
        REFERENCES plt01.dev_devices (tenant_id, device_id),
    CONSTRAINT dev_commissioning_tests_name CHECK (test_name IN (
        'power_loss', 'edge_agent_crash', 'controller_disconnect', 'fire_alarm_input',
        'emergency_unlock', 'recovery', 'manual_override')),
    CONSTRAINT dev_commissioning_tests_outcome CHECK (outcome IN ('passed', 'failed')),
    CONSTRAINT dev_commissioning_tests_failure_explained
        CHECK (outcome <> 'failed' OR coalesce(detail, '') ~ '[^[:space:]]')
);
ALTER TABLE plt01.dev_commissioning_tests ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.dev_commissioning_tests FORCE ROW LEVEL SECURITY;
CREATE POLICY dev_commissioning_tests_tenant ON plt01.dev_commissioning_tests
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE INDEX dev_commissioning_tests_by_device
    ON plt01.dev_commissioning_tests (tenant_id, device_id, test_name, tested_at DESC);

-- -------------------------------------------------------------- the firmware
--
-- Paragraph 3080's staged rollout, per device type: a version is `available`, `staged` to part
-- of the fleet, or `withdrawn`. What a device is actually running is reported on its health,
-- not stored here -- a column saying what a device *should* be on is a plan, and the two are
-- different facts that MOD-018's cached-balance argument says not to conflate.
CREATE TABLE plt01.dev_firmware (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    firmware_id uuid NOT NULL DEFAULT gen_random_uuid(),
    type_id uuid NOT NULL,
    version text NOT NULL,
    status text NOT NULL DEFAULT 'available',
    -- A locator for the image and its own digest, so a gateway can check what it fetched.
    -- Neither is the image: this table holds no binary and has no column for one.
    image_ref text NOT NULL,
    image_digest text NOT NULL,
    release_notes text NOT NULL,
    withdrawn_at timestamptz,
    withdrawn_by uuid,
    withdraw_reason text,
    withdraw_correlation_id uuid,
    released_at timestamptz NOT NULL DEFAULT now(),
    released_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, firmware_id),
    UNIQUE (tenant_id, type_id, version),
    FOREIGN KEY (tenant_id, type_id)
        REFERENCES plt01.dev_device_types (tenant_id, type_id),
    CONSTRAINT dev_firmware_status
        CHECK (status IN ('available', 'staged', 'withdrawn')),
    -- The same shape, for the same reason: it reaches `firmware.updated` in the outbox.
    CONSTRAINT dev_firmware_version_shape
        CHECK (version ~ '^[0-9A-Za-z][0-9A-Za-z._+-]{0,63}$'),
    CONSTRAINT dev_firmware_image_is_a_locator
        CHECK (image_ref ~ '^[a-z][a-z0-9+.-]*:[^[:space:]]+$'),
    CONSTRAINT dev_firmware_digest_shape CHECK (image_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT dev_firmware_notes_not_blank CHECK (release_notes ~ '[^[:space:]]'),
    CONSTRAINT dev_firmware_withdrawal_attributed CHECK (
        (withdrawn_at IS NULL AND withdrawn_by IS NULL AND withdraw_reason IS NULL
         AND withdraw_correlation_id IS NULL)
        OR (withdrawn_at IS NOT NULL AND withdrawn_by IS NOT NULL
            AND coalesce(withdraw_reason, '') ~ '[^[:space:]]'
            AND withdraw_correlation_id IS NOT NULL)),
    CONSTRAINT dev_firmware_withdrawn_is_withdrawn
        CHECK ((status = 'withdrawn') = (withdrawn_at IS NOT NULL))
);
ALTER TABLE plt01.dev_firmware ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.dev_firmware FORCE ROW LEVEL SECURITY;
CREATE POLICY dev_firmware_tenant ON plt01.dev_firmware
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- --------------------------------------------------------------- the command
--
-- Paragraph 3084, a Critical Control: "Remote commands are scoped, signed, audited and bounded
-- by device safety." Four properties and four mechanisms: the device reference and the
-- capability trigger scope it, `payload_digest` is what makes tampering detectable,
-- `issued_by` plus the correlation is the audit, and `commands.check_issue` plus
-- `safety.check_command_safety` bound it.
--
-- **No action here can hold a barrier shut.** `commands.COMMAND_ACTIONS` has nine entries and
-- the only one that touches a door is `unlock_momentary`; the CHECK below names the same nine,
-- so a writer that is not the service cannot invent `lock_down` either. That is paragraph
-- 4173 as an absence from a vocabulary rather than as a rule somebody enforces.
--
-- **And a command expires.** A device offline when one is issued must not receive it three
-- days later and open a door for whoever is standing there: `expires_at` is bounded at a
-- minute for an unlock and a day for anything else, and `may_deliver` refuses a stale one.
CREATE TABLE plt01.dev_commands (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    command_id uuid NOT NULL DEFAULT gen_random_uuid(),
    device_id uuid NOT NULL,
    action text NOT NULL,
    arguments jsonb NOT NULL DEFAULT '{}'::jsonb,
    -- A digest of exactly what was asked, computed by `commands.digest`. **Not a signature**:
    -- there is no key here, and `signature_ref` is where the signature a gateway verifies
    -- lives -- a column claiming to hold one this software never made would be the
    -- fabricated-evidence shape.
    payload_digest text NOT NULL,
    signature_ref text,
    state text NOT NULL DEFAULT 'issued',
    expires_at timestamptz NOT NULL,
    delivered_at timestamptz,
    -- **Who collected it and who settled it.** The first version carried `issued_by` alone,
    -- so the only name on a row saying a door opened was the party that did *not* make the
    -- claim -- and `devices.agent.report` is routine, AAL 1 and tenant-wide, so any holder
    -- could settle any command in the tenant as completed. MOD-008 audits denials rather
    -- than allowed acts and `veyro_cp_app` holds nothing in `iam`, so this row is the only
    -- record there can be. Sixth module for that shape; `dev_health_reports.reported_by`
    -- beside it had it from the start.
    delivered_by uuid,
    delivery_correlation_id uuid,
    acknowledged_at timestamptz,
    settled_at timestamptz,
    settled_by uuid,
    settle_correlation_id uuid,
    outcome_detail text,
    idempotency_key text NOT NULL,
    issued_at timestamptz NOT NULL DEFAULT now(),
    issued_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, command_id),
    UNIQUE (tenant_id, idempotency_key),
    FOREIGN KEY (tenant_id, device_id)
        REFERENCES plt01.dev_devices (tenant_id, device_id),
    CONSTRAINT dev_commands_action CHECK (action IN (
        'unlock_momentary', 'reboot', 'diagnostics', 'sync_now', 'update_firmware',
        'rotate_certificate', 'set_maintenance', 'clear_maintenance',
        'report_peripherals')),
    CONSTRAINT dev_commands_state CHECK (state IN (
        'issued', 'delivered', 'acknowledged', 'completed', 'failed', 'expired')),
    CONSTRAINT dev_commands_digest_shape CHECK (payload_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT dev_commands_signature_is_a_locator
        CHECK (signature_ref IS NULL
               OR signature_ref ~ '^[a-z][a-z0-9+.-]*:[^[:space:]]+$'),
    CONSTRAINT dev_commands_arguments_is_an_object
        CHECK (jsonb_typeof(arguments) = 'object'),
    CONSTRAINT dev_commands_key_not_blank CHECK (idempotency_key ~ '[^[:space:]]'),
    CONSTRAINT dev_commands_window_ordered CHECK (expires_at > issued_at),
    -- **And `issued_at` is not a free clock.** Every window below is a difference between
    -- two columns the same writer supplies, so the minute an unlock is deliverable for was
    -- a minute *starting whenever the writer said* -- a reviewer parked one three days out
    -- and it was openable for forty-five seconds on the night it chose, with every CHECK
    -- satisfied. That is the attack this table's own comment names, performed against the
    -- writer it names. The bound is one-sided on purpose: an upper bound is what stops the
    -- parking, and a lower one would fail every row on a restore.
    CONSTRAINT dev_commands_not_postdated
        CHECK (issued_at <= now() + interval '5 minutes'),
    -- **An unlock is deliverable for a minute.** Stated in the schema as well as in
    -- `commands.ISSUE_WINDOW`, because the writer that is not the service could otherwise
    -- park an unlock with a week's deadline and let it fire on a night shift.
    CONSTRAINT dev_commands_unlock_window_is_a_minute CHECK (
        action <> 'unlock_momentary' OR expires_at - issued_at <= interval '60 seconds'),
    CONSTRAINT dev_commands_window_bounded
        CHECK (expires_at - issued_at <= interval '24 hours'),
    CONSTRAINT dev_commands_delivery_ordered CHECK (
        delivered_at IS NULL OR delivered_at >= issued_at),
    -- `acknowledgement_ordered` subsumes "an acknowledgement needs a delivery": with
    -- `delivered_at` NULL the comparison is NULL and the CHECK passes, so the pair was two
    -- constraints where one is permanently unprovable. Written as one that bites on both.
    CONSTRAINT dev_commands_acknowledgement_ordered CHECK (
        acknowledged_at IS NULL
        OR (delivered_at IS NOT NULL AND acknowledged_at >= delivered_at)),
    CONSTRAINT dev_commands_settled_is_settled
        CHECK ((state IN ('completed', 'failed', 'expired')) = (settled_at IS NOT NULL)),
    CONSTRAINT dev_commands_delivered_is_delivered
        CHECK (state NOT IN ('delivered', 'acknowledged') OR delivered_at IS NOT NULL),
    CONSTRAINT dev_commands_acknowledged_is_acknowledged
        CHECK (state <> 'acknowledged' OR acknowledged_at IS NOT NULL),
    CONSTRAINT dev_commands_failure_explained
        CHECK (state <> 'failed' OR coalesce(outcome_detail, '') ~ '[^[:space:]]'),
    -- A collection and a settlement each name somebody, or neither happened.
    CONSTRAINT dev_commands_delivery_attributed CHECK (
        (delivered_at IS NULL AND delivered_by IS NULL
         AND delivery_correlation_id IS NULL)
        OR (delivered_at IS NOT NULL AND delivered_by IS NOT NULL
            AND delivery_correlation_id IS NOT NULL)),
    CONSTRAINT dev_commands_settlement_attributed CHECK (
        (settled_at IS NULL AND settled_by IS NULL AND settle_correlation_id IS NULL)
        OR (settled_at IS NOT NULL AND settled_by IS NOT NULL
            AND settle_correlation_id IS NOT NULL))
);
ALTER TABLE plt01.dev_commands ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.dev_commands FORCE ROW LEVEL SECURITY;
CREATE POLICY dev_commands_tenant ON plt01.dev_commands
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE INDEX dev_commands_waiting
    ON plt01.dev_commands (tenant_id, device_id, state, expires_at);

-- ------------------------------------------------------- the policy snapshot
--
-- Paragraph 1949: "Edge snapshot is a signed authorization projection with bounded TTL."
-- Insert-only: a snapshot whose window could be extended is an authorization nobody can
-- withdraw, which is the whole of what "bounded" means. Superseding one is issuing another.
CREATE TABLE plt01.dev_policy_snapshots (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    snapshot_id uuid NOT NULL DEFAULT gen_random_uuid(),
    device_id uuid NOT NULL,
    -- The epoch this snapshot was built at. A gateway holding one below the device's current
    -- epoch has missed a revocation; `snapshots.check_fresh_enough` reports that separately
    -- from staleness because the remedy differs.
    revocation_epoch integer NOT NULL,
    content_digest text NOT NULL,
    signature_ref text,
    issued_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    issued_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, snapshot_id),
    FOREIGN KEY (tenant_id, device_id)
        REFERENCES plt01.dev_devices (tenant_id, device_id),
    CONSTRAINT dev_policy_snapshots_digest_shape
        CHECK (content_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT dev_policy_snapshots_signature_is_a_locator
        CHECK (signature_ref IS NULL
               OR signature_ref ~ '^[a-z][a-z0-9+.-]*:[^[:space:]]+$'),
    -- **The ceiling only.** A lower bound here would be subsumed: the trigger below
    -- refuses a snapshot built below the device's own epoch, and that column is bounded at
    -- zero -- so no row reaches a `>= 0` here with the trigger as anything but the second
    -- refusal. The ceiling is still primitive, because the trigger compares against the
    -- device and says nothing about how far above it a snapshot may claim to be.
    CONSTRAINT dev_policy_snapshots_epoch_sane
        CHECK (revocation_epoch <= 2000000000),
    -- Five minutes to twelve hours, which `snapshots.MIN_TTL` and `MAX_TTL` state and which
    -- paragraph 1953's sixty-second revocation target is the reason for.
    -- The same clock, for the same reason: `ttl_bounded` below measures a difference
    -- between two caller-supplied columns, so a snapshot dated a week ahead was an edge
    -- authorization nobody could withdraw for seven and a half days -- which is the exact
    -- opposite of what paragraph 1949's "bounded TTL" buys.
    CONSTRAINT dev_policy_snapshots_not_postdated
        CHECK (issued_at <= now() + interval '5 minutes'),
    CONSTRAINT dev_policy_snapshots_ttl_bounded CHECK (
        expires_at - issued_at >= interval '5 minutes'
        AND expires_at - issued_at <= interval '12 hours')
);
ALTER TABLE plt01.dev_policy_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.dev_policy_snapshots FORCE ROW LEVEL SECURITY;
CREATE POLICY dev_policy_snapshots_tenant ON plt01.dev_policy_snapshots
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE INDEX dev_policy_snapshots_by_device
    ON plt01.dev_policy_snapshots (tenant_id, device_id, issued_at DESC);

-- --------------------------------------------------------- the health report
--
-- Paragraph 3079's fleet dashboard, as the insert-only ledger whatever runs on the gateway
-- writes to. **Online status is not a column**: it is derived in `fleet.reachability` from
-- `dev_devices.last_seen_at`, because a stored flag is a second authority that disagrees with
-- the last report. `peripherals` is the one `jsonb` here and is a device's own inventory.
CREATE TABLE plt01.dev_health_reports (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    report_id uuid NOT NULL DEFAULT gen_random_uuid(),
    device_id uuid NOT NULL,
    latency_ms integer NOT NULL,
    error_count integer NOT NULL,
    storage_free_bytes bigint NOT NULL,
    agent_version text NOT NULL,
    peripherals jsonb NOT NULL DEFAULT '{}'::jsonb,
    reported_at timestamptz NOT NULL DEFAULT now(),
    -- **Who reported it**, which the sibling ledgers in this build learned the hard way:
    -- MOD-011's synthetic results shipped with no actor and its own docstring named a
    -- fabricated `passed` as the risk. A health report says a device is fine, and an operator
    -- who does not drive to the club is relying on it.
    reported_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, report_id),
    FOREIGN KEY (tenant_id, device_id)
        REFERENCES plt01.dev_devices (tenant_id, device_id),
    CONSTRAINT dev_health_reports_latency_sane
        CHECK (latency_ms >= 0 AND latency_ms <= 600000),
    CONSTRAINT dev_health_reports_errors_sane
        CHECK (error_count >= 0 AND error_count <= 1000000000),
    CONSTRAINT dev_health_reports_storage_sane
        CHECK (storage_free_bytes >= 0 AND storage_free_bytes <= 1125899906842624),
    -- **A version is a version.** It reaches `device.online` in the outbox, which no
    -- erasure clears, and a reviewer put an address and a date of birth in it. A non-blank
    -- check admits anything with a character in it; this admits what a build is named.
    CONSTRAINT dev_health_reports_version_shape
        CHECK (agent_version ~ '^[0-9A-Za-z][0-9A-Za-z._+-]{0,63}$'),
    CONSTRAINT dev_health_reports_peripherals_is_an_object
        CHECK (jsonb_typeof(peripherals) = 'object')
);
ALTER TABLE plt01.dev_health_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.dev_health_reports FORCE ROW LEVEL SECURITY;
CREATE POLICY dev_health_reports_tenant ON plt01.dev_health_reports
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE INDEX dev_health_reports_by_device
    ON plt01.dev_health_reports (tenant_id, device_id, reported_at DESC);


-- **What a gateway and the registry disagreed about.** ECO-03's sync-conflict record, and it
-- is a table because the first version had none: the route demanded a `detail`, validated it,
-- returned a response saying "recorded, not resolved" and threw the text away, leaving an
-- operator two hex strings. That is MOD-012's `release_run` shape -- a field required of the
-- caller, validated, and discarded under a docstring claiming it was recorded.
--
-- **The digests are what the event carries; the prose stays here.** `evt_outbox` is the one
-- store no erasure reaches, so the human sentence about what diverged lives in a table with
-- its own declaration in `SUBJECT_COLUMNS` and the event carries the conflict's id.
CREATE TABLE plt01.dev_sync_conflicts (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    conflict_id uuid NOT NULL DEFAULT gen_random_uuid(),
    device_id uuid NOT NULL,
    detail text NOT NULL,
    local_digest text NOT NULL,
    remote_digest text NOT NULL,
    reported_at timestamptz NOT NULL DEFAULT now(),
    reported_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, conflict_id),
    FOREIGN KEY (tenant_id, device_id)
        REFERENCES plt01.dev_devices (tenant_id, device_id),
    CONSTRAINT dev_sync_conflicts_detail_not_blank CHECK (detail ~ '[^[:space:]]'),
    CONSTRAINT dev_sync_conflicts_detail_bounded CHECK (length(detail) <= 1000),
    CONSTRAINT dev_sync_conflicts_local_shape CHECK (local_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT dev_sync_conflicts_remote_shape CHECK (remote_digest ~ '^[0-9a-f]{64}$'),
    -- A conflict is two copies that differ. Two identical digests is not one.
    CONSTRAINT dev_sync_conflicts_actually_differ CHECK (local_digest <> remote_digest)
);
ALTER TABLE plt01.dev_sync_conflicts ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.dev_sync_conflicts FORCE ROW LEVEL SECURITY;
CREATE POLICY dev_sync_conflicts_tenant ON plt01.dev_sync_conflicts
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE INDEX dev_sync_conflicts_by_device
    ON plt01.dev_sync_conflicts (tenant_id, device_id, reported_at DESC);

-- ---------------------------------------------------------------- the triggers
--
-- **A CHECK cannot see what a row used to be**, which is MOD-009's `sec_legal_holds` lesson
-- and is why the lifecycle rules are here. And **a pair of caller-supplied ids that nothing
-- relates is two halves of a control**, which is MOD-013's and MOD-020's: every reference
-- below is checked against what it points at, because the service deriving them correctly
-- today says nothing about the writer every trigger in this file exists for -- a migration, a
-- repair script, the DDL role.

-- A published type's capabilities are what somebody reviewed. **The whole row is frozen, not
-- just the declared names**: MOD-012 shipped `GRANT SELECT, INSERT` plus a unique index on the
-- entry name, which stops re-declaring a name and stops nothing else -- so a *required* scope
-- could be added to a published version, and installs made against "version 1" afterwards
-- authorised a wider set than the one reviewed. Here the same shape would widen what a device
-- model may be commanded to do.
CREATE OR REPLACE FUNCTION plt01.dev_type_capabilities_are_frozen()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    type_status text;
BEGIN
    -- `FOR UPDATE`, for the reason the other two parent reads take it: unlocked, a
    -- capability inserted concurrently with the publication lands on a published type, and
    -- every unit enrolled afterwards snapshots it.
    SELECT status INTO type_status FROM plt01.dev_device_types
     WHERE tenant_id = NEW.tenant_id AND type_id = NEW.type_id
     FOR UPDATE;
    IF type_status IS NULL THEN
        RAISE EXCEPTION 'this capability cites a device type that does not exist';
    END IF;
    IF type_status <> 'draft' THEN
        RAISE EXCEPTION
            'this device type is % and what it may be asked to do was settled when it was '
            'published; a different capability set is a different type', type_status;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER dev_type_capabilities_frozen
    BEFORE INSERT ON plt01.dev_type_capabilities
    FOR EACH ROW EXECUTE FUNCTION plt01.dev_type_capabilities_are_frozen();

-- A device's capability is one its type declares. **The snapshot is a copy, not a free
-- choice**: without this a device could be registered against a plain scanner and declare
-- `access.actuate`, and `commands.check_issue` -- which bounds a command by the *device's*
-- list -- would then let somebody unlock a barcode reader's non-existent door, with no safety
-- profile demanded because nothing about the type said it was an access point.
CREATE OR REPLACE FUNCTION plt01.dev_device_capability_is_declared()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    owning_type uuid;
BEGIN
    SELECT type_id INTO owning_type FROM plt01.dev_devices
     WHERE tenant_id = NEW.tenant_id AND device_id = NEW.device_id;
    IF owning_type IS NULL THEN
        RAISE EXCEPTION 'this capability cites a device that does not exist';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM plt01.dev_type_capabilities
         WHERE tenant_id = NEW.tenant_id AND type_id = owning_type
           AND capability = NEW.capability) THEN
        RAISE EXCEPTION
            'this device''s type does not declare %; a device can do what its model can do',
            NEW.capability;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER dev_device_capabilities_declared
    BEFORE INSERT ON plt01.dev_device_capabilities
    FOR EACH ROW EXECUTE FUNCTION plt01.dev_device_capability_is_declared();

-- The device lifecycle, and what a device *is*. **`type_id`, `location_id` and
-- `serial_number` do not move**: the type is what bounds its commands, the location is what a
-- fleet view and an access policy are scoped by, and the serial is the box. A device that
-- moved rooms is a device re-enrolled, because "what was driving that door in March" has to
-- stay answerable -- and the replacement workflow paragraph 3080 names is a new row plus a
-- quarantine, not an edit.
CREATE OR REPLACE FUNCTION plt01.dev_device_is_one_way()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF NEW.state <> OLD.state AND NOT (
        (OLD.state = 'registered' AND NEW.state IN ('provisioned', 'retired'))
        OR (OLD.state = 'provisioned' AND NEW.state IN ('active', 'quarantined', 'retired'))
        OR (OLD.state = 'active'
            AND NEW.state IN ('maintenance', 'quarantined', 'retired'))
        OR (OLD.state = 'maintenance'
            AND NEW.state IN ('active', 'quarantined', 'retired'))
        OR (OLD.state = 'quarantined'
            AND NEW.state IN ('active', 'maintenance', 'retired'))
    ) THEN
        RAISE EXCEPTION 'a device does not move from % to %', OLD.state, NEW.state;
    END IF;
    IF NEW.type_id <> OLD.type_id OR NEW.location_id <> OLD.location_id
       OR NEW.serial_number <> OLD.serial_number THEN
        RAISE EXCEPTION
            'a device keeps its model, its location and its serial; a unit that moved is one '
            're-enrolled, and the old row says what was driving that door';
    END IF;
    -- **The epoch only goes up.** Rewinding it is how a revoked credential starts working
    -- again: a gateway compares its snapshot's epoch numerically, so a lower number on the
    -- device makes every stale snapshot look current.
    IF NEW.revocation_epoch < OLD.revocation_epoch THEN
        RAISE EXCEPTION
            'a revocation epoch does not go backwards; % is below %',
            NEW.revocation_epoch, OLD.revocation_epoch;
    END IF;
    -- **And `activated_at` is written once.** Clearing it would let a device that has been in
    -- service read as never commissioned, which is the one fact `safety.may_go_live` is
    -- checked against.
    IF OLD.activated_at IS NOT NULL AND (
        NEW.activated_at IS DISTINCT FROM OLD.activated_at
        OR NEW.activated_by IS DISTINCT FROM OLD.activated_by
        OR NEW.activate_correlation_id IS DISTINCT FROM OLD.activate_correlation_id) THEN
        RAISE EXCEPTION 'when this device first went into service is recorded once';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER dev_devices_one_way
    BEFORE UPDATE ON plt01.dev_devices
    FOR EACH ROW EXECUTE FUNCTION plt01.dev_device_is_one_way();

-- A certificate's lifecycle and identity. **The fingerprint, the vault reference and the
-- window do not move**: widening what a device may authenticate with is a new certificate, so
-- that "what could open that door on the fourteenth" stays answerable. MOD-012's rule, where
-- the same shape was a connection's granted scopes.
CREATE OR REPLACE FUNCTION plt01.dev_certificate_is_one_way()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF NEW.state <> OLD.state AND NOT (
        (OLD.state = 'pending' AND NEW.state IN ('active', 'revoked'))
        OR (OLD.state = 'active' AND NEW.state IN ('superseded', 'revoked'))
        OR (OLD.state = 'superseded' AND NEW.state = 'revoked')
    ) THEN
        RAISE EXCEPTION
            'a certificate does not move from % to %', OLD.state, NEW.state;
    END IF;
    IF NEW.device_id <> OLD.device_id OR NEW.fingerprint <> OLD.fingerprint
       OR NEW.vault_ref <> OLD.vault_ref
       OR NEW.not_before <> OLD.not_before OR NEW.not_after <> OLD.not_after THEN
        RAISE EXCEPTION
            'a certificate keeps its device, its fingerprint, its material and its window; '
            'widening what a device may authenticate with is a new certificate';
    END IF;
    IF OLD.revoked_at IS NOT NULL THEN
        RAISE EXCEPTION 'this certificate is revoked and does not change again';
    END IF;
    -- **A superseded certificate is finished too.** The branch above freezes a revoked one
    -- and nothing froze a superseded one, so its replacement pointer and the date it was
    -- replaced were rewritable and backdatable -- which is "what could open that door on the
    -- fourteenth" becoming editable through the pointer, in the table whose fingerprint and
    -- window are frozen precisely to keep that answerable. `dev_safety_profiles` had this
    -- branch from the start; this one did not.
    IF OLD.superseded_at IS NOT NULL AND (
        NEW.superseded_at IS DISTINCT FROM OLD.superseded_at
        OR NEW.superseded_by IS DISTINCT FROM OLD.superseded_by) THEN
        RAISE EXCEPTION
            'this certificate was superseded on % and its replacement is recorded once',
            OLD.superseded_at;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER dev_certificates_one_way
    BEFORE UPDATE ON plt01.dev_certificates
    FOR EACH ROW EXECUTE FUNCTION plt01.dev_certificate_is_one_way();

-- A safety profile is about an access point, and its claims never change. **Only a device
-- that actuates has one**, because commissioning a fire-alarm test on a receipt printer is
-- how a safety gate gets routed around -- and a profile on a non-actuating device would let
-- `safety.may_go_live` pass on a door that has none.
CREATE OR REPLACE FUNCTION plt01.dev_safety_profile_is_an_access_point()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    exists_device boolean;
BEGIN
    SELECT true INTO exists_device FROM plt01.dev_devices
     WHERE tenant_id = NEW.tenant_id AND device_id = NEW.device_id;
    IF exists_device IS NULL THEN
        RAISE EXCEPTION 'this safety profile cites a device that does not exist';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM plt01.dev_device_capabilities
         WHERE tenant_id = NEW.tenant_id AND device_id = NEW.device_id
           AND capability = 'access.actuate') THEN
        RAISE EXCEPTION
            'this device moves no barrier, so it is not an access point and has no hardware '
            'safety profile';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER dev_safety_profiles_access_point
    BEFORE INSERT ON plt01.dev_safety_profiles
    FOR EACH ROW EXECUTE FUNCTION plt01.dev_safety_profile_is_an_access_point();

-- And a supersession is final, with the claims untouched. A profile whose booleans could be
-- edited is a building whose records pass an audit it would fail.
CREATE OR REPLACE FUNCTION plt01.dev_safety_profile_supersede_is_final()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF OLD.superseded_at IS NOT NULL THEN
        RAISE EXCEPTION
            'this safety profile was superseded on % and does not change again',
            OLD.superseded_at;
    END IF;
    IF NEW.device_id <> OLD.device_id OR NEW.profile <> OLD.profile
       OR NEW.on_egress_path <> OLD.on_egress_path
       OR NEW.fire_release_is_independent <> OLD.fire_release_is_independent
       OR NEW.local_emergency_input <> OLD.local_emergency_input
       OR NEW.evidence_ref <> OLD.evidence_ref
       OR NEW.commissioned_by <> OLD.commissioned_by
       OR NEW.commissioned_at <> OLD.commissioned_at THEN
        RAISE EXCEPTION
            'what was commissioned at this access point, and by whom, is recorded once; a '
            're-commissioning supersedes it';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER dev_safety_profiles_supersede_final
    BEFORE UPDATE ON plt01.dev_safety_profiles
    FOR EACH ROW EXECUTE FUNCTION plt01.dev_safety_profile_supersede_is_final();

-- A command's lifecycle and what it asks. **The action, the arguments, the digest and the
-- device do not move**: re-aiming a committed command is forging one from the device's point
-- of view, which is MOD-010's finding about `evt_outbox.event_type` in a place where the
-- consequence is a door.
CREATE OR REPLACE FUNCTION plt01.dev_command_is_one_way()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF NEW.state <> OLD.state AND NOT (
        (OLD.state = 'issued' AND NEW.state IN ('delivered', 'expired', 'failed'))
        OR (OLD.state = 'delivered'
            AND NEW.state IN ('acknowledged', 'failed', 'expired'))
        -- **An acknowledged command cannot expire.** The device has it; whether it worked is
        -- the device's to report, and timing it out here would record "expired" for an unlock
        -- that opened the door.
        OR (OLD.state = 'acknowledged' AND NEW.state IN ('completed', 'failed'))
    ) THEN
        RAISE EXCEPTION 'a command does not move from % to %', OLD.state, NEW.state;
    END IF;
    -- `signature_ref` is written once, with the delivery: it locates the signature a
    -- gateway verifies the frozen digest against, so a re-pointable locator on a frozen
    -- digest is an asymmetry with nothing behind it.
    IF OLD.signature_ref IS NOT NULL AND NEW.signature_ref IS DISTINCT FROM OLD.signature_ref
       THEN
        RAISE EXCEPTION 'this command''s signature is recorded once';
    END IF;
    IF NEW.device_id <> OLD.device_id OR NEW.action <> OLD.action
       OR NEW.arguments <> OLD.arguments OR NEW.payload_digest <> OLD.payload_digest
       OR NEW.expires_at <> OLD.expires_at OR NEW.issued_by <> OLD.issued_by THEN
        RAISE EXCEPTION
            'a command keeps its device, its action, its arguments, its digest, its deadline '
            'and whoever issued it; a different instruction is a different command';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER dev_commands_one_way
    BEFORE UPDATE ON plt01.dev_commands
    FOR EACH ROW EXECUTE FUNCTION plt01.dev_command_is_one_way();

-- A command is within the device's own snapshotted capabilities, and an actuation goes only
-- to a commissioned access point. **The service checks both and this is for the writer that
-- is not the service** -- and the second half is paragraph 4175 at the row: a command telling
-- an uncommissioned door to open is the thing a failed safety test is supposed to block.
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
    -- **`FOR UPDATE`, not a plain read.** A trigger that reads a parent row to decide
    -- whether a child may be written has to lock it, or two ordinary transactions at READ
    -- COMMITTED each see the old value and both commit -- MOD-019's `FOR SHARE` finding one
    -- notch weaker, because this took no lock at all. Here the race is a quarantine against
    -- an unlock: the act that is meant to be a remote revoke, losing to the command it is
    -- meant to stop.
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
    -- **And paragraph 4175 itself, which the first version did not read.** The branch above
    -- asks only whether a profile row exists, and both its message and this file's header
    -- claimed it was the commissioning gate -- so a door that reached `active` by any writer
    -- other than `activate_device` opened on request with six of seven fire-code tests never
    -- run, and a *failed* fire-alarm re-test changed nothing at the row. "A lookup that
    -- proves something exists does not authorise what you do next", with a fire code as the
    -- subject.
    --
    -- The latest answer per test is the one that counts, which is why this is `DISTINCT ON`
    -- rather than an existence check: a door that passed in March, failed a re-test in June
    -- and was never repaired has a passing row, and paragraph 4175's words are that a
    -- *failed* test blocks opening it.
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
CREATE TRIGGER dev_commands_within_capability
    BEFORE INSERT ON plt01.dev_commands
    FOR EACH ROW EXECUTE FUNCTION plt01.dev_command_is_within_capability();

-- A snapshot's epoch is the device's own, and never below it. A snapshot built at an older
-- epoch than the device has reached has missed a revocation before it was even issued.
CREATE OR REPLACE FUNCTION plt01.dev_snapshot_epoch_is_current()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    device_epoch integer;
BEGIN
    -- `FOR UPDATE`: a plain read let a revocation and a snapshot commit side by side, so a
    -- snapshot was written at an epoch the device had already left -- valid for twelve
    -- hours, and exactly the state this trigger's own message calls "already missed a
    -- revocation". Two ordinary transactions, no adversarial timing.
    SELECT revocation_epoch INTO device_epoch FROM plt01.dev_devices
     WHERE tenant_id = NEW.tenant_id AND device_id = NEW.device_id
     FOR UPDATE;
    IF device_epoch IS NULL THEN
        RAISE EXCEPTION 'this snapshot cites a device that does not exist';
    END IF;
    IF NEW.revocation_epoch < device_epoch THEN
        RAISE EXCEPTION
            'this snapshot was built at epoch % and the device has reached %; it has '
            'already missed a revocation', NEW.revocation_epoch, device_epoch;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER dev_policy_snapshots_epoch_current
    BEFORE INSERT ON plt01.dev_policy_snapshots
    FOR EACH ROW EXECUTE FUNCTION plt01.dev_snapshot_epoch_is_current();

-- A commissioning test is about a device that moves a barrier. The same argument as the
-- safety profile's: a fire-alarm test recorded against a printer is a record that satisfies
-- `may_go_live` for nothing.
CREATE OR REPLACE FUNCTION plt01.dev_commissioning_is_an_access_point()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM plt01.dev_devices
         WHERE tenant_id = NEW.tenant_id AND device_id = NEW.device_id) THEN
        RAISE EXCEPTION 'this commissioning record cites a device that does not exist';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM plt01.dev_device_capabilities
         WHERE tenant_id = NEW.tenant_id AND device_id = NEW.device_id
           AND capability = 'access.actuate') THEN
        RAISE EXCEPTION
            'this device moves no barrier; the commissioning tests are about an access point';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER dev_commissioning_tests_access_point
    BEFORE INSERT ON plt01.dev_commissioning_tests
    FOR EACH ROW EXECUTE FUNCTION plt01.dev_commissioning_is_an_access_point();

-- A firmware image belongs to the type it was built for, and a withdrawal is final.
CREATE OR REPLACE FUNCTION plt01.dev_firmware_is_one_way()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF OLD.withdrawn_at IS NOT NULL THEN
        RAISE EXCEPTION
            'this firmware was withdrawn on % and does not come back; a fixed build is a '
            'new version', OLD.withdrawn_at;
    END IF;
    IF NEW.type_id <> OLD.type_id OR NEW.version <> OLD.version
       OR NEW.image_ref <> OLD.image_ref OR NEW.image_digest <> OLD.image_digest THEN
        RAISE EXCEPTION
            'a firmware release keeps its type, its version and the image it is; a different '
            'image is a different version';
    END IF;
    -- **And no transition branch, deliberately.** `dev_firmware_status` admits three
    -- values and `dev_firmware_withdrawn_is_withdrawn` makes `withdrawn` and a withdrawal
    -- timestamp the same fact, so every move this module would want to refuse is a move
    -- *out of* `withdrawn` -- which the branch above already refuses, by the timestamp. A
    -- transition check here would be dead code with no isolating probe available, which is
    -- the shape MOD-016 deleted `cat_eligibility_rules_kind` for and MOD-020 deleted four
    -- bounds for: a rule subsumed by a sibling is deleted, not tested harder.
    RETURN NEW;
END;
$$;
CREATE TRIGGER dev_firmware_one_way
    BEFORE UPDATE ON plt01.dev_firmware
    FOR EACH ROW EXECUTE FUNCTION plt01.dev_firmware_is_one_way();

-- A device type's publication and retirement are each recorded once.
CREATE OR REPLACE FUNCTION plt01.dev_device_type_is_one_way()
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
            'a device type does not move from % to %; a published one is what devices were '
            'enrolled against', OLD.status, NEW.status;
    END IF;
    IF OLD.published_at IS NOT NULL AND (
        NEW.published_at IS DISTINCT FROM OLD.published_at
        OR NEW.published_by IS DISTINCT FROM OLD.published_by
        OR NEW.publish_correlation_id IS DISTINCT FROM OLD.publish_correlation_id) THEN
        RAISE EXCEPTION 'who published this device type, and when, is recorded once';
    END IF;
    IF NEW.type_code <> OLD.type_code OR NEW.kind <> OLD.kind THEN
        RAISE EXCEPTION
            'a device type keeps its code and its kind; the kind decides whether a safety '
            'profile is required at all';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER dev_device_types_one_way
    BEFORE UPDATE ON plt01.dev_device_types
    FOR EACH ROW EXECUTE FUNCTION plt01.dev_device_type_is_one_way();

-- **A replacement is for the same device, checked at commit.** Nothing related either
-- supersession pointer to the row's own unit: a turnstile's certificate could be recorded
-- as superseded by a scanner's, leaving the first with no active credential and a rotation
-- history naming another box -- and a fire door's `fail_safe` commissioning could be
-- superseded by another door's `fail_secure` one, so following that door's chain read
-- "re-commissioned as fail_secure, no independent fire release". That is the exact row
-- `egress_is_never_software_gated` exists to make unrecordable, written through a pointer
-- that crossed doors. "A pair of caller-supplied ids that nothing relates is two halves of
-- a control" is this file's own standard.
--
-- **Deferred, like the foreign key it mirrors**, and for the same reason: a rotation points
-- the outgoing row at a successor that does not exist yet, because inserting first violates
-- `one_active_per_device` and a null pointer violates the pairing. An immediate check would
-- make the honest order unwritable, so this fires at COMMIT -- which means a probe for it
-- has to say `SET CONSTRAINTS ALL IMMEDIATE` first, or it watches a transaction that never
-- commits.
CREATE OR REPLACE FUNCTION plt01.dev_certificate_replaces_its_own_device()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF NEW.superseded_by IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM plt01.dev_certificates c
         WHERE c.tenant_id = NEW.tenant_id AND c.certificate_id = NEW.superseded_by
           AND c.device_id = NEW.device_id) THEN
        RAISE EXCEPTION
            'a certificate is replaced by one issued to the same device; this replacement '
            'belongs to another unit';
    END IF;
    RETURN NEW;
END;
$$;
CREATE CONSTRAINT TRIGGER dev_certificates_replacement_is_its_own
    AFTER UPDATE ON plt01.dev_certificates
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION plt01.dev_certificate_replaces_its_own_device();

CREATE OR REPLACE FUNCTION plt01.dev_profile_replaces_its_own_device()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF NEW.superseded_by IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM plt01.dev_safety_profiles p
         WHERE p.tenant_id = NEW.tenant_id AND p.profile_id = NEW.superseded_by
           AND p.device_id = NEW.device_id) THEN
        RAISE EXCEPTION
            'a commissioning is superseded by another commissioning of the same access '
            'point; this one belongs to a different door';
    END IF;
    RETURN NEW;
END;
$$;
CREATE CONSTRAINT TRIGGER dev_safety_profiles_replacement_is_its_own
    AFTER UPDATE ON plt01.dev_safety_profiles
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION plt01.dev_profile_replaces_its_own_device();
REVOKE ALL ON FUNCTION plt01.dev_certificate_replaces_its_own_device() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.dev_profile_replaces_its_own_device() FROM PUBLIC;


-- ----------------------------------------------------------------- the grants
--
-- **Every "insert-only" claim above is a missing grant, and that is where it lives.** A
-- comment saying a row is immutable is a comment; a column absent from an UPDATE grant is a
-- refusal from the database. Check 102 compares the whole column list per table and per role
-- against this file, read through `has_column_privilege`, because a column-level widening is
-- invisible to a check that reads `pg_class.relacl` -- MOD-010's finding, which cost ten
-- undetected grant changes.
--
-- No runtime role gets DELETE, TRUNCATE or REFERENCES on anything here. A device's history is
-- what answers "what was driving that door in March", and a command's is the only record that
-- somebody told a door to open.

GRANT SELECT, INSERT ON plt01.dev_device_types TO veyro_cp_app, veyro_cp_worker;
-- The lifecycle only. **Not `type_code` or `kind`**: the code is what a tenant's own tooling
-- refers to a model by, and the kind decides whether a safety profile is required -- a
-- turnstile re-labelled a scanner is an access point with no commissioning gate.
GRANT UPDATE (display_name, vendor, model, status, published_at, published_by,
              publish_correlation_id, retired_at, retired_by, retire_reason,
              retire_correlation_id)
    ON plt01.dev_device_types TO veyro_cp_app, veyro_cp_worker;

-- **No UPDATE at all.** What a model may be asked to do is settled when it is published, and
-- the trigger above refuses even an insert once it is out of draft.
GRANT SELECT, INSERT ON plt01.dev_type_capabilities TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.dev_devices TO veyro_cp_app, veyro_cp_worker;
-- **Not `type_id`, `location_id` or `serial_number`**, which the trigger also refuses: those
-- three are what the device *is*, and every later decision reads them. `last_seen_at` and
-- `revocation_epoch` are here because a gateway reporting in and a revocation are the two
-- things that happen to a device without anybody editing it.
GRANT UPDATE (display_name, config, state, last_seen_at, revocation_epoch, version,
              activated_at, activated_by, activate_correlation_id,
              reactivated_at, reactivated_by, reactivate_correlation_id, quarantined_at,
              quarantined_by, quarantine_reason, quarantine_correlation_id, retired_at,
              retired_by, retire_reason, retire_correlation_id)
    ON plt01.dev_devices TO veyro_cp_app, veyro_cp_worker;

-- **No UPDATE at all.** A device's capabilities are the snapshot of its type at registration;
-- widening them later is what makes "what was this unit authorised to do in March"
-- unanswerable, and narrowing them is a replacement.
GRANT SELECT, INSERT ON plt01.dev_device_capabilities TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.dev_certificates TO veyro_cp_app, veyro_cp_worker;
-- **Not `fingerprint`, `vault_ref`, `not_before` or `not_after`.** Widening what a device may
-- authenticate with, or how long for, is a new certificate -- which is the only way "what
-- could open that door on the fourteenth" stays answerable. MOD-012's rule about a
-- connection's granted scopes, in the place where the scope is a building.
GRANT UPDATE (state, superseded_by, superseded_at, revoked_at, revoked_by, revoke_reason,
              revoke_correlation_id)
    ON plt01.dev_certificates TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.dev_safety_profiles TO veyro_cp_app, veyro_cp_worker;
-- **The supersession only.** Every claim on the row -- the profile, whether the door is on an
-- egress path, whether the fire release is independent, whether a local emergency input
-- exists, the evidence and who commissioned it -- carries no UPDATE grant at all. That is
-- section 16.4 as a privilege: a building's safety record cannot be edited, only superseded by
-- another commissioning that says who did it.
GRANT UPDATE (superseded_at, superseded_by, supersede_correlation_id)
    ON plt01.dev_safety_profiles TO veyro_cp_app, veyro_cp_worker;

-- **No UPDATE at all.** A failed safety test cannot be edited into a pass; a repair is a
-- re-test, which is another row.
GRANT SELECT, INSERT ON plt01.dev_commissioning_tests TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.dev_firmware TO veyro_cp_app, veyro_cp_worker;
-- Not `version`, `image_ref` or `image_digest`: a different image is a different version, and
-- re-pointing a released one is how a gateway fetches something nobody reviewed.
GRANT UPDATE (status, release_notes, withdrawn_at, withdrawn_by, withdraw_reason,
              withdraw_correlation_id)
    ON plt01.dev_firmware TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.dev_commands TO veyro_cp_app, veyro_cp_worker;
-- **The lifecycle only.** Not the action, the arguments, the digest, the deadline or the
-- device: re-aiming a committed command is forging one from the device's point of view, which
-- is MOD-010's `evt_outbox.event_type` finding where the consequence is a door opening.
GRANT UPDATE (state, delivered_at, delivered_by, delivery_correlation_id,
              acknowledged_at, settled_at, settled_by, settle_correlation_id,
              outcome_detail, signature_ref)
    ON plt01.dev_commands TO veyro_cp_app, veyro_cp_worker;

-- **No UPDATE at all.** A snapshot whose window could be extended is an authorization nobody
-- can withdraw, which is the whole of what paragraph 1949's "bounded TTL" means.
GRANT SELECT, INSERT ON plt01.dev_policy_snapshots TO veyro_cp_app, veyro_cp_worker;

-- **No UPDATE at all.** A health report is what an operator decides not to drive to a club
-- on; one that could be edited afterwards is MOD-011's fabricated `passed`.
GRANT SELECT, INSERT ON plt01.dev_health_reports TO veyro_cp_app, veyro_cp_worker;

-- **No UPDATE at all.** A conflict record is what a gateway said diverged at a moment; a
-- resolution is another act, and nothing in this build performs one.
GRANT SELECT, INSERT ON plt01.dev_sync_conflicts TO veyro_cp_app, veyro_cp_worker;

-- And no PUBLIC execute on any of the trigger functions, which rule 5 of the isolation rule
-- forbids outright and which nothing in this suite checked until MOD-020's review found two
-- asserted controls with no evidence.
REVOKE ALL ON FUNCTION plt01.dev_type_capabilities_are_frozen() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.dev_device_capability_is_declared() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.dev_device_is_one_way() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.dev_certificate_is_one_way() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.dev_safety_profile_is_an_access_point() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.dev_safety_profile_supersede_is_final() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.dev_command_is_one_way() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.dev_command_is_within_capability() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.dev_snapshot_epoch_is_current() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.dev_commissioning_is_an_access_point() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.dev_firmware_is_one_way() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.dev_device_type_is_one_way() FROM PUBLIC;
