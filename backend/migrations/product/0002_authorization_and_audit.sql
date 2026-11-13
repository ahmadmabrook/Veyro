-- MOD-008 IAM-03-R01..R07: roles, scoped assignments, policies, approvals and the audit log.
--
-- Same schema and same role as MOD-007 (TSD paragraph 1253 puts IAM-03 in the `iam` schema too),
-- so every table repeats the four protections documented at the head of
-- `../tenant/0001_organization_hierarchy.sql` with `veyro_iam_app` as the policy's role.
--
-- IAM-03 states two critical controls, and each is a structural decision here rather than a rule
-- the service is trusted to follow:
--
--   * **Default deny and least privilege are mandatory.** Nothing in this schema can express
--     "allow everything". A role holds an explicit list of permissions, an assignment carries an
--     explicit scope, and `app.authorization.decision` starts from deny and requires a reason to
--     move. There is no wildcard column and no `is_admin` boolean, because either would be a way
--     to grant everything without naming anything.
--   * **Audit records are write-once and integrity-protected.** Insert-only grants make them
--     write-once. Integrity is a hash chain: every row carries the digest of the row before it
--     in its tenant, so removing or editing one breaks every digest after it and the break is
--     detectable by anybody who can read the table. Insert-only alone would not survive somebody
--     with database access; the chain does not stop them either, but it stops them doing it
--     *quietly*, which is what "integrity-protected" has to mean when the attacker may be an
--     administrator.
--
-- **There is no `permissions` table.** TSD paragraph 1281 names Permission as an authoritative
-- entity and this file models it as a code-level catalogue (`app.authorization.catalog`) that
-- `iam.role_permissions` references by name, with a CHECK on the shape. A permission is a fact
-- about what the software can do, not about a tenant: a per-tenant table would let two tenants
-- disagree about which permissions exist, and the only thing that could resolve the disagreement
-- is the code. The deviation is deliberate and is recorded in CLAUDE.md.

CREATE TABLE iam.roles (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    role_id uuid NOT NULL DEFAULT gen_random_uuid(),
    role_key text NOT NULL,
    display_name text NOT NULL,
    description text,
    -- A built-in role is seeded by the product and may not be edited by a tenant; a custom one
    -- is the tenant's own. IAM-03-R01 asks for both.
    builtin boolean NOT NULL DEFAULT false,
    version bigint NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, role_id),
    UNIQUE (tenant_id, role_key),
    CONSTRAINT roles_key_shape CHECK (role_key ~ '^[a-z0-9]+(_[a-z0-9]+)*$'),
    CONSTRAINT roles_version_positive CHECK (version > 0)
);
ALTER TABLE iam.roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.roles FORCE ROW LEVEL SECURITY;
CREATE POLICY roles_tenant ON iam.roles
    FOR ALL TO veyro_iam_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE iam.role_permissions (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    role_id uuid NOT NULL,
    permission text NOT NULL,
    granted_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, role_id, permission),
    FOREIGN KEY (tenant_id, role_id) REFERENCES iam.roles (tenant_id, role_id),
    -- `module.resource.action`, and no wildcard character is in the class. A permission that
    -- could be written `billing.*` would be least privilege in name only.
    CONSTRAINT role_permissions_shape CHECK
        (permission ~ '^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*){2}$')
);
ALTER TABLE iam.role_permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.role_permissions FORCE ROW LEVEL SECURITY;
CREATE POLICY role_permissions_tenant ON iam.role_permissions
    FOR ALL TO veyro_iam_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE iam.role_assignments (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    assignment_id uuid NOT NULL DEFAULT gen_random_uuid(),
    identity_id uuid NOT NULL,
    role_id uuid NOT NULL,
    -- The Scope entity, as columns rather than a bare id, for the reason MOD-005 gives at
    -- `cfg_values`: a polymorphic id cannot be foreign-keyed, so containment would rest on
    -- application code. Here it rests on two composite keys into the tenant plane.
    scope_type text NOT NULL DEFAULT 'tenant',
    brand_id uuid,
    location_id uuid,
    -- IAM-03-R04: delegation and temporary access. An assignment that expires needs no
    -- revocation to stop working, which is what makes temporary access actually temporary.
    -- `granted_by` is the whole delegation record. An earlier draft also carried
    -- `delegated_from`, which no code set and no evaluator read -- a column implying a
    -- delegation model that did not exist. What makes a grant legitimate is enforced in
    -- `assign_role` instead: a grantor may only grant permissions they themselves hold, at a
    -- scope they themselves cover.
    granted_by uuid NOT NULL,
    granted_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    revoked_at timestamptz,
    revoked_reason text,
    PRIMARY KEY (tenant_id, assignment_id),
    FOREIGN KEY (tenant_id, role_id) REFERENCES iam.roles (tenant_id, role_id),
    FOREIGN KEY (tenant_id, identity_id)
        REFERENCES iam.identities (tenant_id, identity_id),
    FOREIGN KEY (tenant_id, brand_id) REFERENCES plt01.brands (tenant_id, brand_id),
    FOREIGN KEY (tenant_id, location_id) REFERENCES plt01.locations (tenant_id, location_id),
    CONSTRAINT role_assignments_scope_shape CHECK (
        (scope_type = 'tenant' AND brand_id IS NULL AND location_id IS NULL)
        OR (scope_type = 'brand' AND brand_id IS NOT NULL AND location_id IS NULL)
        OR (scope_type = 'location' AND location_id IS NOT NULL AND brand_id IS NULL)
    ),
    CONSTRAINT role_assignments_expiry CHECK (expires_at IS NULL OR expires_at > granted_at),
    CONSTRAINT role_assignments_revoked_reason CHECK
        ((revoked_at IS NULL) = (revoked_reason IS NULL))
);
ALTER TABLE iam.role_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.role_assignments FORCE ROW LEVEL SECURITY;
CREATE POLICY role_assignments_tenant ON iam.role_assignments
    FOR ALL TO veyro_iam_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE UNIQUE INDEX role_assignments_live
    ON iam.role_assignments (tenant_id, identity_id, role_id, scope_type,
                             coalesce(brand_id, '00000000-0000-0000-0000-000000000000'::uuid),
                             coalesce(location_id, '00000000-0000-0000-0000-000000000000'::uuid))
    WHERE revoked_at IS NULL;

CREATE INDEX role_assignments_by_identity
    ON iam.role_assignments (tenant_id, identity_id) WHERE revoked_at IS NULL;

CREATE TABLE iam.policies (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    policy_id uuid NOT NULL DEFAULT gen_random_uuid(),
    policy_key text NOT NULL,
    -- IAM-03-R02 and R03. `deny` outranks `allow` in the evaluator whatever the priority says,
    -- so a policy written to protect health data or a minor's record cannot be overridden by
    -- adding a higher-priority allow.
    effect text NOT NULL,
    action text NOT NULL,
    match jsonb NOT NULL DEFAULT '{}'::jsonb,
    masked_fields text[] NOT NULL DEFAULT '{}',
    priority integer NOT NULL DEFAULT 100,
    description text,
    version bigint NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    retired_at timestamptz,
    PRIMARY KEY (tenant_id, policy_id),
    CONSTRAINT policies_effect CHECK (effect IN ('allow', 'deny', 'mask')),
    CONSTRAINT policies_key_shape CHECK (policy_key ~ '^[a-z0-9]+(_[a-z0-9]+)*$'),
    CONSTRAINT policies_action_shape CHECK
        (action ~ '^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*){2}$'),
    CONSTRAINT policies_match_is_object CHECK (jsonb_typeof(match) = 'object'),
    -- A mask policy that masks nothing, or an allow/deny that masks something, is a row whose
    -- effect cannot be read off its own columns.
    CONSTRAINT policies_mask_shape CHECK
        ((effect = 'mask') = (cardinality(masked_fields) > 0))
);
ALTER TABLE iam.policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.policies FORCE ROW LEVEL SECURITY;
CREATE POLICY policies_tenant ON iam.policies
    FOR ALL TO veyro_iam_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE UNIQUE INDEX policies_live_key
    ON iam.policies (tenant_id, policy_key) WHERE retired_at IS NULL;

CREATE TABLE iam.approval_policies (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    approval_policy_id uuid NOT NULL DEFAULT gen_random_uuid(),
    action text NOT NULL,
    -- IAM-03-R05: by amount, risk, role, location and action type. A threshold of zero means
    -- every instance of the action needs approval.
    threshold_minor bigint NOT NULL DEFAULT 0,
    required_permission text NOT NULL,
    required_approvals integer NOT NULL DEFAULT 1,
    -- One policy names one permission. Where several policies apply at once the decider must
    -- hold **all** of them, which is why the request below carries a set rather than a column.

    separation_of_duties boolean NOT NULL DEFAULT true,
    version bigint NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    retired_at timestamptz,
    PRIMARY KEY (tenant_id, approval_policy_id),
    CONSTRAINT approval_policies_action_shape CHECK
        (action ~ '^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*){2}$'),
    CONSTRAINT approval_policies_threshold CHECK (threshold_minor >= 0),
    CONSTRAINT approval_policies_count CHECK (required_approvals >= 1)
);
-- **Approval policies are tenant-wide.** IAM-03-R05 names location among the dimensions, and an
-- earlier draft carried `scope_type`, `brand_id` and `location_id` here -- never selected, never
-- matched, so a location-scoped policy would have applied everywhere while reading as though it
-- did not. The columns are gone and the gap is in CLAUDE.md, which is the honest way round.
ALTER TABLE iam.approval_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.approval_policies FORCE ROW LEVEL SECURITY;
CREATE POLICY approval_policies_tenant ON iam.approval_policies
    FOR ALL TO veyro_iam_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE iam.approval_requests (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    request_id uuid NOT NULL DEFAULT gen_random_uuid(),
    action text NOT NULL,
    resource_type text NOT NULL,
    resource_id text,
    amount_minor bigint,
    currency text,
    reason text,
    requested_by uuid NOT NULL,
    -- Snapshotted when the request is made, and authoritative when it is decided. Re-deriving
    -- them from today's policies let somebody holding `authz.policy.write` turn separation of
    -- duties off for a request already in flight and then approve their own.
    required_approvals integer NOT NULL,
    separation_of_duties boolean NOT NULL,
    -- A **set**, not a column. When two policies apply at the same strictness and name
    -- different permissions, a single column has to choose, and whatever rule it chooses by --
    -- row order, or a sort -- is arbitrary. Requiring all of them is the only answer that is
    -- both deterministic and not weaker than either policy alone.
    required_permissions text[] NOT NULL,
    state text NOT NULL DEFAULT 'pending',
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    decided_at timestamptz,
    PRIMARY KEY (tenant_id, request_id),
    FOREIGN KEY (tenant_id, requested_by)
        REFERENCES iam.identities (tenant_id, identity_id),
    CONSTRAINT approval_requests_state CHECK
        (state IN ('pending', 'approved', 'rejected', 'expired', 'withdrawn')),
    CONSTRAINT approval_requests_count CHECK (required_approvals >= 1),
    CONSTRAINT approval_requests_decided_at CHECK
        ((state = 'pending') = (decided_at IS NULL)),
    CONSTRAINT approval_requests_amount CHECK
        ((amount_minor IS NULL) = (currency IS NULL)),
    CONSTRAINT approval_requests_currency_shape CHECK
        (currency IS NULL OR currency ~ '^[A-Z]{3}$'),
    CONSTRAINT approval_requests_permissions_present CHECK
        (cardinality(required_permissions) > 0)
);
ALTER TABLE iam.approval_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.approval_requests FORCE ROW LEVEL SECURITY;
CREATE POLICY approval_requests_tenant ON iam.approval_requests
    FOR ALL TO veyro_iam_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE iam.approval_decisions (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    decision_id uuid NOT NULL DEFAULT gen_random_uuid(),
    request_id uuid NOT NULL,
    decided_by uuid NOT NULL,
    decision text NOT NULL,
    reason text,
    decided_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, decision_id),
    FOREIGN KEY (tenant_id, request_id)
        REFERENCES iam.approval_requests (tenant_id, request_id),
    FOREIGN KEY (tenant_id, decided_by)
        REFERENCES iam.identities (tenant_id, identity_id),
    -- One decision per approver per request. Without it, "two approvals" could be one person
    -- pressing the button twice, which is the whole thing a second approval exists to prevent.
    UNIQUE (tenant_id, request_id, decided_by),
    CONSTRAINT approval_decisions_decision CHECK (decision IN ('approved', 'rejected'))
);
ALTER TABLE iam.approval_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.approval_decisions FORCE ROW LEVEL SECURITY;
CREATE POLICY approval_decisions_tenant ON iam.approval_decisions
    FOR ALL TO veyro_iam_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- The chain head. One row per tenant, holding the sequence and digest of the newest audit entry.
-- It is the only mutable part of the audit mechanism, and it exists so that appending can take a
-- row lock: without it two concurrent appends would read the same previous digest and fork the
-- chain, which verification would report as tampering.
CREATE TABLE iam.audit_chain_heads (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    sequence bigint NOT NULL DEFAULT 0,
    head_hash bytea NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id),
    CONSTRAINT audit_chain_heads_sequence CHECK (sequence >= 0),
    CONSTRAINT audit_chain_heads_hash_length CHECK (octet_length(head_hash) = 32)
);
ALTER TABLE iam.audit_chain_heads ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.audit_chain_heads FORCE ROW LEVEL SECURITY;
CREATE POLICY audit_chain_heads_tenant ON iam.audit_chain_heads
    FOR ALL TO veyro_iam_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE iam.audit_events (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    audit_id uuid NOT NULL DEFAULT gen_random_uuid(),
    sequence bigint NOT NULL,
    category text NOT NULL,
    action text NOT NULL,
    outcome text NOT NULL,
    actor_identity_id uuid,
    on_behalf_of uuid,
    resource_type text,
    resource_id text,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    correlation_id uuid NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    -- The chain. `prev_hash` is the digest of the entry before this one in this tenant, and
    -- `entry_hash` covers **every** column above together with `prev_hash` -- `on_behalf_of`
    -- included, which an earlier draft stored outside the digest. That is the field recording an
    -- AI or a support agent acting as a member, which is the attribution most worth forging.
    -- Deleting or editing any row invalidates every digest after it.
    prev_hash bytea NOT NULL,
    entry_hash bytea NOT NULL,
    PRIMARY KEY (tenant_id, audit_id),
    FOREIGN KEY (tenant_id, actor_identity_id)
        REFERENCES iam.identities (tenant_id, identity_id),
    FOREIGN KEY (tenant_id, on_behalf_of)
        REFERENCES iam.identities (tenant_id, identity_id),
    -- A gap in the sequence is as detectable as a broken digest, and this makes a duplicate
    -- impossible rather than merely detectable.
    UNIQUE (tenant_id, sequence),
    UNIQUE (tenant_id, entry_hash),
    CONSTRAINT audit_events_sequence_positive CHECK (sequence > 0),
    CONSTRAINT audit_events_outcome CHECK (outcome IN ('allowed', 'denied', 'recorded')),
    -- IAM-03-R06 names the categories that must be audited. A row outside them is a category
    -- somebody invented at a call site rather than one the requirement asked for.
    CONSTRAINT audit_events_category CHECK (category IN (
        'authentication', 'data_access', 'configuration', 'finance', 'access', 'ai', 'support'
    )),
    CONSTRAINT audit_events_hash_lengths CHECK
        (octet_length(prev_hash) = 32 AND octet_length(entry_hash) = 32)
);
ALTER TABLE iam.audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.audit_events FORCE ROW LEVEL SECURITY;
CREATE POLICY audit_events_tenant ON iam.audit_events
    FOR ALL TO veyro_iam_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE INDEX audit_events_by_time ON iam.audit_events (tenant_id, occurred_at);
CREATE INDEX audit_events_by_actor ON iam.audit_events (tenant_id, actor_identity_id, occurred_at);

CREATE TABLE iam.access_reviews (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    review_id uuid NOT NULL DEFAULT gen_random_uuid(),
    title text NOT NULL,
    state text NOT NULL DEFAULT 'open',
    opened_by uuid NOT NULL,
    opened_at timestamptz NOT NULL DEFAULT now(),
    closed_at timestamptz,
    PRIMARY KEY (tenant_id, review_id),
    FOREIGN KEY (tenant_id, opened_by) REFERENCES iam.identities (tenant_id, identity_id),
    CONSTRAINT access_reviews_state CHECK (state IN ('open', 'completed')),
    CONSTRAINT access_reviews_closed_at CHECK ((state = 'completed') = (closed_at IS NOT NULL))
);
ALTER TABLE iam.access_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.access_reviews FORCE ROW LEVEL SECURITY;
CREATE POLICY access_reviews_tenant ON iam.access_reviews
    FOR ALL TO veyro_iam_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE iam.access_review_items (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    item_id uuid NOT NULL DEFAULT gen_random_uuid(),
    review_id uuid NOT NULL,
    assignment_id uuid NOT NULL,
    decision text NOT NULL DEFAULT 'pending',
    decided_by uuid,
    decided_at timestamptz,
    note text,
    PRIMARY KEY (tenant_id, item_id),
    FOREIGN KEY (tenant_id, review_id) REFERENCES iam.access_reviews (tenant_id, review_id),
    FOREIGN KEY (tenant_id, assignment_id)
        REFERENCES iam.role_assignments (tenant_id, assignment_id),
    FOREIGN KEY (tenant_id, decided_by) REFERENCES iam.identities (tenant_id, identity_id),
    UNIQUE (tenant_id, review_id, assignment_id),
    CONSTRAINT access_review_items_decision CHECK
        (decision IN ('pending', 'kept', 'revoked')),
    CONSTRAINT access_review_items_decided CHECK
        ((decision = 'pending') = (decided_by IS NULL AND decided_at IS NULL))
);
ALTER TABLE iam.access_review_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.access_review_items FORCE ROW LEVEL SECURITY;
CREATE POLICY access_review_items_tenant ON iam.access_review_items
    FOR ALL TO veyro_iam_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- Mutable configuration: roles, their permissions, assignments, policies and reviews.
GRANT SELECT, INSERT, UPDATE ON iam.roles TO veyro_iam_app;
GRANT SELECT, INSERT, UPDATE ON iam.role_permissions TO veyro_iam_app;
GRANT SELECT, INSERT, UPDATE ON iam.role_assignments TO veyro_iam_app;
GRANT SELECT, INSERT, UPDATE ON iam.policies TO veyro_iam_app;
GRANT SELECT, INSERT, UPDATE ON iam.approval_policies TO veyro_iam_app;
GRANT SELECT, INSERT, UPDATE ON iam.approval_requests TO veyro_iam_app;
GRANT SELECT, INSERT, UPDATE ON iam.access_reviews TO veyro_iam_app;
GRANT SELECT, INSERT, UPDATE ON iam.access_review_items TO veyro_iam_app;

-- A permission may be taken off a role, which is the one place a DELETE is the honest operation:
-- an ungranted permission is an absence, not a revoked row, and keeping tombstones here would
-- make "what can this role do" a query over history rather than over state. The audit log
-- records the removal, which is where that history belongs.
GRANT DELETE ON iam.role_permissions TO veyro_iam_app;

-- The chain head moves; the chain itself does not.
GRANT SELECT, INSERT, UPDATE ON iam.audit_chain_heads TO veyro_iam_app;

-- The audit log. Insert and select, and nothing else, for every role. Checks 30 to 32 prove it.
GRANT SELECT, INSERT ON iam.audit_events TO veyro_iam_app;

-- A decision stands. Changing one after the fact would make "two approvals" unverifiable.
GRANT SELECT, INSERT ON iam.approval_decisions TO veyro_iam_app;
