-- MOD-012 ECO-02: integration installs, connections, credential references, sync cursors and
-- connector runs. Tables are module-prefixed `int_` as the other tenant modules are.
--
-- Every table repeats the four protections documented at the head of
-- `0001_organization_hierarchy.sql`: tenant-leading primary key, ENABLE plus FORCE row level
-- security, the `current_setting('app.tenant_id', true)` predicate that is NULL when no context
-- is set, and composite foreign keys carrying `tenant_id` into every parent -- including the
-- reference to `plt01_platform.tenants`, which checks 49 to 53 sweep from the catalogue rather
-- than proving one table and asserting the rest, because MOD-011's review showed what that is
-- worth.
--
-- Four decisions are specific to this module.
--
--   * **A credential reference holds a reference, and there is no column it could hold a secret
--     in.** `vault_ref` names a secret kept somewhere this build cannot read. There is no vault
--     here -- MOD-007 says so about TOTP seeds, MOD-009 says so about crypto-shred -- so the
--     honest thing is a table that *cannot* store one rather than one that stores one carefully.
--     The scopes, the expiry and the rotation history are metadata about a secret, which is
--     what this build is able to know. Check 52 asserts the column list, because the control is
--     the absence of a column and an absence is exactly what a later migration adds back.
--
--   * **An install snapshots the definition version it was made against**, the same way
--     `bil_subscriptions` snapshots its plan. The catalogue lives in `plt01_platform` under a
--     role this plane cannot reach, published versions are immutable there, and the snapshot is
--     what lets somebody answer "what did this tenant actually authorize" a year later without
--     a cross-plane join that the role separation forbids anyway.
--
--   * **Revocation and uninstallation leave the row.** A connection a provider revoked and an
--     integration a tenant removed are both things somebody will ask about afterwards --
--     usually when asking what a third party could reach and until when. Neither table carries
--     a DELETE grant for any runtime role.
--
--   * **Granted scopes are an array with a shape, and there is no wildcard.** MOD-008 refuses
--     `billing.*` in its permission grammar for a reason that applies harder here, because the
--     holder is outside the building: a scope set that can be widened by a character is one
--     nobody can review.

-- ---------------------------------------------------------------- installs

CREATE TABLE plt01.int_installs (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    install_id uuid NOT NULL DEFAULT gen_random_uuid(),
    definition_key text NOT NULL,
    definition_version bigint NOT NULL,
    -- What the definition said when this install was made. The catalogue is on the other plane
    -- and immutable there; this is what makes the install answerable without reaching for it.
    definition_snapshot jsonb NOT NULL,
    criticality text NOT NULL,
    config jsonb NOT NULL DEFAULT '{}'::jsonb,
    state text NOT NULL DEFAULT 'installed',
    -- Paragraph 3033's obligations, written per install because what a tenant falls back *to*
    -- depends on what else that tenant has. Enforced at activation by
    -- `app/integrations/lifecycle.py`, not by a constraint: an install may be created and
    -- explored before anybody has written an exit plan for it, and refusing that would push
    -- the decision to the moment somebody is least able to make it.
    fallback_plan text,
    reconciliation_plan text,
    exit_plan text,
    installed_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    installed_at timestamptz NOT NULL DEFAULT now(),
    activated_at timestamptz,
    disabled_at timestamptz,
    uninstalled_at timestamptz,
    uninstalled_by uuid,
    uninstall_correlation_id uuid,
    uninstall_reason text,
    PRIMARY KEY (tenant_id, install_id),
    CONSTRAINT int_installs_key_shape
        CHECK (definition_key ~ '^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*)*$'),
    CONSTRAINT int_installs_version_positive CHECK (definition_version > 0),
    CONSTRAINT int_installs_snapshot_is_an_object
        CHECK (jsonb_typeof(definition_snapshot) = 'object'),
    CONSTRAINT int_installs_config_is_an_object CHECK (jsonb_typeof(config) = 'object'),
    CONSTRAINT int_installs_criticality
        CHECK (criticality IN ('convenience', 'important', 'critical')),
    CONSTRAINT int_installs_state
        CHECK (state IN ('installed', 'active', 'disabled', 'uninstalled')),
    -- An uninstall is the one act that ends a third party's reach, so it carries who, why and
    -- under which correlation id -- MOD-009's rule that evidence with nobody's name on it
    -- answers nothing, applied to the act somebody will ask about in a breach review.
    CONSTRAINT int_installs_uninstall_attributed CHECK (
        (uninstalled_at IS NULL AND uninstalled_by IS NULL
         AND uninstall_correlation_id IS NULL AND uninstall_reason IS NULL)
        OR (uninstalled_at IS NOT NULL AND uninstalled_by IS NOT NULL
            AND uninstall_correlation_id IS NOT NULL
            AND length(btrim(coalesce(uninstall_reason, ''))) > 0)),
    CONSTRAINT int_installs_uninstalled_state
        CHECK ((state = 'uninstalled') = (uninstalled_at IS NOT NULL))
);
-- One live install per definition. A tenant with two installs of one provider has two sets of
-- scopes nobody can reconcile, and a sync that writes through whichever the query found first.
CREATE UNIQUE INDEX int_installs_live_definition
    ON plt01.int_installs (tenant_id, definition_key) WHERE uninstalled_at IS NULL;
ALTER TABLE plt01.int_installs ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.int_installs FORCE ROW LEVEL SECURITY;
CREATE POLICY int_installs_tenant ON plt01.int_installs
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- connections

CREATE TABLE plt01.int_connections (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    connection_id uuid NOT NULL DEFAULT gen_random_uuid(),
    install_id uuid NOT NULL,
    -- The provider's own handle for the account this connects to. Opaque here, and **not a
    -- credential**: an account id is something a support engineer needs to see in a list.
    external_account_ref text NOT NULL,
    region text NOT NULL,
    granted_scopes text[] NOT NULL,
    state text NOT NULL DEFAULT 'pending',
    authorized_at timestamptz,
    authorized_by uuid,
    -- `validated` means somebody recorded a validation, not that this build performed one:
    -- there is no provider here to answer. The evidence column is what the row actually is --
    -- a claim made by a named party at a time -- and a state that read as "verified" while
    -- nothing verified anything is the shape MOD-011's synthetic results were built to avoid.
    validated_at timestamptz,
    validated_by uuid,
    validation_evidence text,
    revoked_at timestamptz,
    revoked_by uuid,
    revoke_reason text,
    correlation_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, connection_id),
    FOREIGN KEY (tenant_id, install_id) REFERENCES plt01.int_installs (tenant_id, install_id),
    CONSTRAINT int_connections_state
        CHECK (state IN ('pending', 'authorized', 'validated', 'revoked')),
    CONSTRAINT int_connections_account_not_blank
        CHECK (length(btrim(external_account_ref)) > 0),
    CONSTRAINT int_connections_region_shape CHECK (region ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    -- No wildcard, in the grammar or anywhere else. A scope set widened by a character is one
    -- nobody can review, and the holder is outside the building. `array_to_string` is how a
    -- regex reaches an array in a CHECK -- a subquery is not allowed in one.
    CONSTRAINT int_connections_scope_shape CHECK (
        array_length(granted_scopes, 1) IS NULL
        OR array_to_string(granted_scopes, ',')
           ~ '^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*)+(,[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*)+)*$'),
    CONSTRAINT int_connections_authorization_attributed CHECK (
        (authorized_at IS NULL) = (authorized_by IS NULL)),
    -- A validation with no evidence is a state change somebody can assert for free, which is
    -- the whole thing this column exists to stop.
    CONSTRAINT int_connections_validation_attributed CHECK (
        (validated_at IS NULL AND validated_by IS NULL AND validation_evidence IS NULL)
        OR (validated_at IS NOT NULL AND validated_by IS NOT NULL
            AND length(btrim(coalesce(validation_evidence, ''))) > 0)),
    CONSTRAINT int_connections_revocation_attributed CHECK (
        (revoked_at IS NULL AND revoked_by IS NULL AND revoke_reason IS NULL)
        OR (revoked_at IS NOT NULL AND revoked_by IS NOT NULL
            AND length(btrim(coalesce(revoke_reason, ''))) > 0)),
    CONSTRAINT int_connections_revoked_state
        CHECK ((state = 'revoked') = (revoked_at IS NOT NULL))
);
CREATE INDEX int_connections_by_install ON plt01.int_connections (tenant_id, install_id);
-- One live connection per provider account per install. Two would each hold their own scopes
-- against the same account, and a revocation of one would read as a revocation.
CREATE UNIQUE INDEX int_connections_live_account
    ON plt01.int_connections (tenant_id, install_id, external_account_ref)
    WHERE revoked_at IS NULL;
ALTER TABLE plt01.int_connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.int_connections FORCE ROW LEVEL SECURITY;
CREATE POLICY int_connections_tenant ON plt01.int_connections
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- credential references

-- **There is no column here a secret could go in, and that is the control.** `vault_ref` names
-- something kept where this build cannot read it; everything else is metadata about a secret
-- rather than a secret. Check 52 asserts the column list against the catalogue, because the
-- protection is an absence and an absence is exactly what a later migration adds back without
-- anybody noticing.
--
-- Insert-only, and a rotation is a new row rather than an edit: the question somebody asks in a
-- breach review is which reference was live on a given day, and a column that can be rewritten
-- cannot answer it.
CREATE TABLE plt01.int_credential_refs (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    credential_ref_id uuid NOT NULL DEFAULT gen_random_uuid(),
    connection_id uuid NOT NULL,
    -- Where the secret lives, in whatever notation the vault that holds it uses. There is no
    -- such vault in this repository, so every value here today points at something outside it.
    vault_ref text NOT NULL,
    scopes text[] NOT NULL,
    issued_at timestamptz NOT NULL,
    expires_at timestamptz,
    supersedes_credential_ref_id uuid,
    retired_at timestamptz,
    recorded_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, credential_ref_id),
    FOREIGN KEY (tenant_id, connection_id)
        REFERENCES plt01.int_connections (tenant_id, connection_id),
    FOREIGN KEY (tenant_id, supersedes_credential_ref_id)
        REFERENCES plt01.int_credential_refs (tenant_id, credential_ref_id),
    -- A *reference*, with the shape of one. Non-blank text alone meant a live API key was a
    -- valid "vault reference", which made the absence of a secret column a naming convention
    -- rather than the control the header claims -- MOD-010's recorded lesson that the
    -- restricted-field rule checks names and a value can carry anything, one module later. A
    -- scheme-prefixed locator is not proof, and it is the difference between a mistake and a
    -- deliberate act.
    CONSTRAINT int_credential_refs_vault_ref_is_a_locator
        CHECK (vault_ref ~ '^[a-z][a-z0-9+.-]*://[^[:space:]]+$'),
    CONSTRAINT int_credential_refs_expiry_after_issue
        CHECK (expires_at IS NULL OR expires_at > issued_at),
    CONSTRAINT int_credential_refs_no_self_supersede CHECK (
        supersedes_credential_ref_id IS NULL
        OR supersedes_credential_ref_id <> credential_ref_id),
    CONSTRAINT int_credential_refs_scope_shape CHECK (
        array_length(scopes, 1) IS NULL
        OR array_to_string(scopes, ',')
           ~ '^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*)+(,[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*)+)*$')
);
CREATE INDEX int_credential_refs_by_connection
    ON plt01.int_credential_refs (tenant_id, connection_id, recorded_at DESC);
-- One live reference per connection. Two would mean two secrets are current and a rotation
-- that retired one would leave the other reachable with scopes nobody re-reviewed.
CREATE UNIQUE INDEX int_credential_refs_live
    ON plt01.int_credential_refs (tenant_id, connection_id) WHERE retired_at IS NULL;
ALTER TABLE plt01.int_credential_refs ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.int_credential_refs FORCE ROW LEVEL SECURITY;
CREATE POLICY int_credential_refs_tenant ON plt01.int_credential_refs
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- sync cursors

CREATE TABLE plt01.int_sync_cursors (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    cursor_id uuid NOT NULL DEFAULT gen_random_uuid(),
    connection_id uuid NOT NULL,
    resource text NOT NULL,
    -- Opaque: a timestamp, a token or a sequence number, whichever the provider uses. This
    -- build never orders two positions, which is why `check_advance` compares when each was
    -- observed instead.
    -- Nullable, because the **policy** can be set before the first sync: the conflict policy
    -- is the tenant's decision and has to be settable without letting a connector create the
    -- row first -- which is how the routine sync permission came to be the one choosing it.
    position text,
    observed_at timestamptz NOT NULL,
    conflict_policy text NOT NULL DEFAULT 'manual',
    reset_at timestamptz,
    reset_by uuid,
    reset_reason text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, cursor_id),
    FOREIGN KEY (tenant_id, connection_id)
        REFERENCES plt01.int_connections (tenant_id, connection_id),
    UNIQUE (tenant_id, connection_id, resource),
    CONSTRAINT int_sync_cursors_resource_shape CHECK (resource ~ '^[a-z0-9]+(_[a-z0-9]+)*$'),
    CONSTRAINT int_sync_cursors_position_not_blank
        CHECK (position IS NULL OR length(btrim(position)) > 0),
    -- `manual` by default, which is the conservative one: it refuses to pick a side rather
    -- than silently overwriting whichever copy the tenant cares about.
    CONSTRAINT int_sync_cursors_conflict_policy
        CHECK (conflict_policy IN ('local_wins', 'provider_wins', 'manual')),
    -- Moving a cursor backwards means re-reading a window, which for a provider that bills per
    -- call is money. It is allowed, and it carries who did it and why.
    CONSTRAINT int_sync_cursors_reset_attributed CHECK (
        (reset_at IS NULL AND reset_by IS NULL AND reset_reason IS NULL)
        OR (reset_at IS NOT NULL AND reset_by IS NOT NULL
            AND length(btrim(coalesce(reset_reason, ''))) > 0))
);
ALTER TABLE plt01.int_sync_cursors ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.int_sync_cursors FORCE ROW LEVEL SECURITY;
CREATE POLICY int_sync_cursors_tenant ON plt01.int_sync_cursors
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- connector runs

-- One row per attempt at a resource. `started_by` is whoever asked; nothing in this build runs
-- a connector, so every row here was written by a caller rather than produced by a sync that
-- happened -- the same honest shape as MOD-011's probe results, and for the same reason.
CREATE TABLE plt01.int_connector_runs (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    run_id uuid NOT NULL DEFAULT gen_random_uuid(),
    connection_id uuid NOT NULL,
    resource text NOT NULL,
    status text NOT NULL DEFAULT 'running',
    attempts integer NOT NULL DEFAULT 1,
    max_attempts integer NOT NULL DEFAULT 5,
    records_read bigint NOT NULL DEFAULT 0,
    records_written bigint NOT NULL DEFAULT 0,
    conflicts integer NOT NULL DEFAULT 0,
    last_error text,
    next_attempt_at timestamptz,
    claimed_until timestamptz,
    -- Releasing a quarantined run puts a connector that burned its whole retry budget back in
    -- front of a third-party provider, and it resets the attempt count -- so the row afterwards
    -- reads as a fresh run and nothing would say a human decided that. Every comparable act in
    -- this module carries its actor; this one carried only a docstring saying it did, which
    -- review caught. There is nowhere else the record could land: MOD-008 audits denials and
    -- not allowed actions, and `veyro_cp_app` holds nothing in `iam`.
    released_at timestamptz,
    released_by uuid,
    release_reason text,
    release_correlation_id uuid,
    -- Who settled the run, which is not who started it. `integrations.sync.run` is routine and
    -- tenant-wide, so any holder can finish any running run -- and without this the only name
    -- on a fabricated "synced four million records" is the name of the party that did not make
    -- the claim. MOD-008 audits denials and not allowed actions, so there is no second record.
    settled_by uuid,
    settle_correlation_id uuid,
    -- A reconciliation is a separate claim about two sides, made by somebody, once. The counts
    -- are stored rather than folded into `conflicts` alone: a difference with no totals behind
    -- it is a number nobody can reproduce.
    reconciled_at timestamptz,
    reconciled_by uuid,
    reconcile_correlation_id uuid,
    reconciled_local bigint,
    reconciled_provider bigint,
    reconciled_matched bigint,
    started_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    PRIMARY KEY (tenant_id, run_id),
    FOREIGN KEY (tenant_id, connection_id)
        REFERENCES plt01.int_connections (tenant_id, connection_id),
    CONSTRAINT int_connector_runs_status
        CHECK (status IN ('running', 'succeeded', 'failed', 'dead')),
    CONSTRAINT int_connector_runs_resource_shape CHECK (resource ~ '^[a-z0-9]+(_[a-z0-9]+)*$'),
    CONSTRAINT int_connector_runs_attempts_sane
        CHECK (attempts >= 1 AND max_attempts >= 1 AND attempts <= max_attempts),
    CONSTRAINT int_connector_runs_counts_sane CHECK (
        records_read >= 0 AND records_written >= 0 AND conflicts >= 0),
    -- A failure with no error is a diagnostic nobody can act on, which is the whole of
    -- paragraph 3028's "diagnostics" that a constraint can hold.
    CONSTRAINT int_connector_runs_failure_explained CHECK (
        status NOT IN ('failed', 'dead') OR length(btrim(coalesce(last_error, ''))) > 0),
    CONSTRAINT int_connector_runs_finished CHECK (
        (status = 'running') = (finished_at IS NULL)),
    CONSTRAINT int_connector_runs_settlement_attributed CHECK (
        (settled_by IS NULL) = (settle_correlation_id IS NULL)),
    -- A settled run names who settled it. `running` is the only status that has not been.
    CONSTRAINT int_connector_runs_settled_has_an_actor CHECK (
        status = 'running' OR settled_by IS NOT NULL),
    CONSTRAINT int_connector_runs_reconciliation_attributed CHECK (
        (reconciled_at IS NULL AND reconciled_by IS NULL AND reconcile_correlation_id IS NULL
         AND reconciled_local IS NULL AND reconciled_provider IS NULL
         AND reconciled_matched IS NULL)
        OR (reconciled_at IS NOT NULL AND reconciled_by IS NOT NULL
            AND reconcile_correlation_id IS NOT NULL AND reconciled_local >= 0
            AND reconciled_provider >= 0 AND reconciled_matched >= 0
            AND reconciled_matched <= least(reconciled_local, reconciled_provider))),
    CONSTRAINT int_connector_runs_release_attributed CHECK (
        (released_at IS NULL AND released_by IS NULL AND release_reason IS NULL
         AND release_correlation_id IS NULL)
        OR (released_at IS NOT NULL AND released_by IS NOT NULL
            AND release_correlation_id IS NOT NULL
            AND length(btrim(coalesce(release_reason, ''))) > 0))
);
CREATE INDEX int_connector_runs_recent
    ON plt01.int_connector_runs (tenant_id, connection_id, started_at DESC);
CREATE INDEX int_connector_runs_due
    ON plt01.int_connector_runs (tenant_id, status, next_attempt_at);
-- One running run per connection and resource. **A lock, not a lease**, and the distinction is
-- deliberate: MOD-010's relay uses a lease because two deliveries of one event are tolerable
-- under at-least-once, and two concurrent syncs of one resource are not -- they both read the
-- same window and both advance the same cursor, so one of them ends up having skipped records
-- it never saw. `claimed_until` still bounds how long a runner may hold it.
CREATE UNIQUE INDEX int_connector_runs_one_in_flight
    ON plt01.int_connector_runs (tenant_id, connection_id, resource)
    WHERE status = 'running';
ALTER TABLE plt01.int_connector_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.int_connector_runs FORCE ROW LEVEL SECURITY;
CREATE POLICY int_connector_runs_tenant ON plt01.int_connector_runs
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- privileges

-- An install moves through its lifecycle and its obligations are written after it exists, so
-- the UPDATE is column-scoped to exactly those. The definition it was made against, the
-- snapshot of that definition and who installed it are what the row *is*.
GRANT SELECT, INSERT ON plt01.int_installs TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (state, config, fallback_plan, reconciliation_plan, exit_plan, activated_at,
              disabled_at, uninstalled_at, uninstalled_by, uninstall_correlation_id,
              uninstall_reason)
    ON plt01.int_installs TO veyro_cp_app, veyro_cp_worker;

-- A connection is authorized, validated and revoked. **`granted_scopes` carries no UPDATE**:
-- widening what a third party may reach is a new authorization, with a new row and a new
-- decision, not an edit to the old one -- which is the only way the question "what did this
-- connection hold on the fourteenth" stays answerable.
GRANT SELECT, INSERT ON plt01.int_connections TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (state, authorized_at, authorized_by, validated_at, validated_by,
              validation_evidence, revoked_at, revoked_by, revoke_reason)
    ON plt01.int_connections TO veyro_cp_app, veyro_cp_worker;

-- A credential reference is written once and retired. Nothing else about it may change: the
-- vault reference, the scopes it carries and when it expires are the facts a breach review
-- reads, and a rotation is a new row that supersedes this one.
GRANT SELECT, INSERT ON plt01.int_credential_refs TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (retired_at) ON plt01.int_credential_refs TO veyro_cp_app, veyro_cp_worker;

-- A cursor is a position that moves; that is what it is for.
GRANT SELECT, INSERT ON plt01.int_sync_cursors TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (position, observed_at, conflict_policy, reset_at, reset_by, reset_reason,
              updated_at)
    ON plt01.int_sync_cursors TO veyro_cp_app, veyro_cp_worker;

-- A run settles. Its connection, its resource and who started it do not.
GRANT SELECT, INSERT ON plt01.int_connector_runs TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (status, attempts, records_read, records_written, conflicts, last_error,
              next_attempt_at, claimed_until, finished_at, released_at, released_by,
              release_reason, release_correlation_id, settled_by, settle_correlation_id,
              reconciled_at, reconciled_by, reconcile_correlation_id, reconciled_local,
              reconciled_provider, reconciled_matched)
    ON plt01.int_connector_runs TO veyro_cp_app, veyro_cp_worker;
