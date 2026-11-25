-- MOD-008 / ADM-STF-03 — a staff invitation. ADR-0017.
--
-- **There was no invitation of any kind in this build**: no table, no token, no expiry, and
-- nothing that accepts one. `POST /identities` is open, which MOD-007 records as a gap, so the
-- only way somebody joined a tenant was to be registered by whoever held the tenant's uuid and
-- then granted a role in a second act. ADM-STF-03 is one act with a link at the end of it.
--
-- **The invitation is MOD-008's** (ADR-0017 D1), because the control that must not be bypassed
-- is "a grantor may only grant permissions they themselves hold, at a scope they themselves
-- cover" -- the rule a review found a clerk escalating through, and MOD-008's own. The identity
-- creation it ends in is MOD-007's and is called on this transaction's connection.
--
-- **The token is a digest and nothing here can hold the link** (D3), which is `iam.sessions`'
-- own shape and for the same reason. The consequence is D4: a resend cannot be the same link,
-- because the plaintext is gone -- so a resend is a *new* invitation superseding the old,
-- rather than a rewritten expiry. Nothing about when a link was valid is edited.
--
-- **No name, because the canvas collects none** (D11). ADM-STF-03's form is an address, a
-- role and the clubs, and its pending list draws `yasmin@nadi.jo` rather than a person -- so a
-- `display_name` here would be a column this build invented, holding a copy of somebody's name
-- in the plane whose own authentication log deliberately records none. The identity's name is
-- the invitee's own, typed on the page where they set their password.
--
-- **No status column** (D6). Pending is derived -- not accepted, not revoked, and not past
-- `expires_at` -- so "2d left" is arithmetic over the row and there is no counter to go stale.
-- A stored `expired` flag would be a live link the product calls dead, or the reverse.

-- ------------------------------------------------------------- the invitation

CREATE TABLE iam.invitations (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    invitation_id uuid NOT NULL DEFAULT gen_random_uuid(),
    -- Normalized by `normalize_email` before it gets here, which is what makes the one-live
    -- index below mean "this person" rather than "this spelling".
    email_normalized text NOT NULL,
    role_id uuid NOT NULL,
    -- **A digest, never the token.** 32 bytes of SHA-256, as `iam.sessions.token_hash` is: a
    -- table somebody can read is a table the wrong person can read, and an invitation is a
    -- bearer credential that creates an identity with a role.
    token_hash bytea NOT NULL,
    expires_at timestamptz NOT NULL,
    -- What this one replaces, where a resend minted a new link (D4). A chain rather than an
    -- edit, so "when was that link valid" stays answerable.
    supersedes_invitation_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    accepted_at timestamptz,
    accepted_identity_id uuid,
    revoked_at timestamptz,
    revoked_by uuid,
    revoke_reason text,
    PRIMARY KEY (tenant_id, invitation_id),
    UNIQUE (tenant_id, token_hash),
    FOREIGN KEY (tenant_id, role_id) REFERENCES iam.roles (tenant_id, role_id),
    FOREIGN KEY (tenant_id, created_by)
        REFERENCES iam.identities (tenant_id, identity_id),
    FOREIGN KEY (tenant_id, accepted_identity_id)
        REFERENCES iam.identities (tenant_id, identity_id),
    FOREIGN KEY (tenant_id, supersedes_invitation_id)
        REFERENCES iam.invitations (tenant_id, invitation_id),
    CONSTRAINT invitations_token_hash_length CHECK (octet_length(token_hash) = 32),
    CONSTRAINT invitations_email_shape
        CHECK (email_normalized ~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'),
    -- **A window, bounded at both ends against the row's own creation** (D8). The upper bound
    -- is the interesting half: a year-long invitation is a permanent back door with a friendly
    -- name, so thirty days is the ceiling and the canvas's seven is the default the service
    -- applies.
    CONSTRAINT invitations_window CHECK (
        expires_at > created_at AND expires_at <= created_at + interval '30 days'),
    -- An acceptance names who it became, and a revocation names who stopped it and why. Both
    -- all-or-none, and the `coalesce` is load-bearing: a CHECK passes on NULL, which is how
    -- MOD-009's legal hold admitted the row it existed to refuse.
    CONSTRAINT invitations_acceptance_attributed
        CHECK ((accepted_at IS NULL) = (accepted_identity_id IS NULL)),
    CONSTRAINT invitations_revocation_attributed CHECK (
        (revoked_at IS NULL AND revoked_by IS NULL AND revoke_reason IS NULL)
        OR (revoked_at IS NOT NULL AND revoked_by IS NOT NULL
            AND coalesce(revoke_reason, '') ~ '[^[:space:]]')),
    -- **Settled once, and not both ways.** An invitation that is accepted *and* revoked is a
    -- row nobody can read: either somebody joined on a link that was withdrawn, or a joined
    -- member's access was taken back by a control that is not revocation -- which is
    -- `revoke_assignment`'s job and leaves evidence of its own.
    CONSTRAINT invitations_one_outcome
        CHECK (accepted_at IS NULL OR revoked_at IS NULL),
    CONSTRAINT invitations_not_self
        CHECK (supersedes_invitation_id IS NULL
               OR supersedes_invitation_id <> invitation_id)
);

ALTER TABLE iam.invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.invitations FORCE ROW LEVEL SECURITY;
CREATE POLICY invitations_tenant ON iam.invitations
    FOR ALL TO veyro_iam_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

COMMENT ON TABLE iam.invitations IS
    'ADM-STF-03. One invitation to join a tenant with a role at named clubs. The link is a '
    'bearer credential, so only its digest is here; pending is derived rather than stored.';

-- **One live invitation per address** (D5). Two live ones with different roles for one person
-- means whichever link they click decides what they can do, which is an ambiguity nobody would
-- defend -- so a resend revokes and inserts in one transaction and the index is satisfied by
-- construction. Partial on the two settled states and not on the expiry: an expired invitation
-- still holds the slot, because the remedy for one is a resend rather than a second live link
-- beside it.
CREATE UNIQUE INDEX invitations_one_live_per_email
    ON iam.invitations (tenant_id, email_normalized)
    WHERE accepted_at IS NULL AND revoked_at IS NULL;

CREATE INDEX invitations_by_created_at
    ON iam.invitations (tenant_id, created_at DESC);

-- ------------------------------------------------------- the clubs it is for
--
-- **A child table, because the canvas invites somebody to two clubs** (D7).
-- `iam.role_assignments` admits exactly one scope per row, so "Khalda, Sweifieh" is two
-- assignments -- and the accept creates one per row here. The references into `plt01` are the
-- same composite keys `role_assignments` already carries: `veyro_iam_app` holds no privileges
-- there, and the foreign key is the database's rather than the role's.
CREATE TABLE iam.invitation_scopes (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    invitation_id uuid NOT NULL,
    scope_type text NOT NULL,
    brand_id uuid,
    location_id uuid,
    -- **A surrogate key and a `coalesce`d unique index**, because a primary key cannot carry
    -- an expression and NULLs are distinct in a plain unique one -- so two identical
    -- tenant-wide rows would both be admitted. MOD-033's `mem_plan_entitlements_one_live` is
    -- the precedent and the reason is the same: "all clubs" is a row with no location.
    invitation_scope_id uuid NOT NULL DEFAULT gen_random_uuid(),
    PRIMARY KEY (tenant_id, invitation_scope_id),
    FOREIGN KEY (tenant_id, invitation_id)
        REFERENCES iam.invitations (tenant_id, invitation_id),
    FOREIGN KEY (tenant_id, brand_id) REFERENCES plt01.brands (tenant_id, brand_id),
    FOREIGN KEY (tenant_id, location_id)
        REFERENCES plt01.locations (tenant_id, location_id),
    -- The same shape `role_assignments_scope_shape` states, because these rows become those
    -- rows: a scope this table admits and that one refuses would be an invitation nobody can
    -- accept.
    CONSTRAINT invitation_scopes_shape CHECK (
        (scope_type = 'tenant' AND brand_id IS NULL AND location_id IS NULL)
        OR (scope_type = 'brand' AND brand_id IS NOT NULL AND location_id IS NULL)
        OR (scope_type = 'location' AND location_id IS NOT NULL AND brand_id IS NULL))
);

ALTER TABLE iam.invitation_scopes ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.invitation_scopes FORCE ROW LEVEL SECURITY;
CREATE POLICY invitation_scopes_tenant ON iam.invitation_scopes
    FOR ALL TO veyro_iam_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE UNIQUE INDEX invitation_scopes_one_per_scope
    ON iam.invitation_scopes (
        tenant_id, invitation_id, scope_type,
        coalesce(brand_id, '00000000-0000-0000-0000-000000000000'),
        coalesce(location_id, '00000000-0000-0000-0000-000000000000'));

COMMENT ON TABLE iam.invitation_scopes IS
    'The clubs an invitation is for. One row per scope, because a role assignment admits one.';

-- ------------------------------------------------------------- settled once

-- **An invitation is settled once, and what settled it is never re-attributed.** A CHECK
-- cannot see `OLD`, which is MOD-009's `sec_legal_holds` finding: the acceptance and the
-- revocation each have an attribution, and a row that could be re-pointed afterwards would
-- make "who let this person in" a question with two answers.
CREATE OR REPLACE FUNCTION iam.invitation_is_settled_once()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF OLD.accepted_at IS NOT NULL AND (
        NEW.accepted_at IS DISTINCT FROM OLD.accepted_at
        OR NEW.accepted_identity_id IS DISTINCT FROM OLD.accepted_identity_id) THEN
        RAISE EXCEPTION 'this invitation has been accepted and by whom is recorded once';
    END IF;
    IF OLD.revoked_at IS NOT NULL AND (
        NEW.revoked_at IS DISTINCT FROM OLD.revoked_at
        OR NEW.revoked_by IS DISTINCT FROM OLD.revoked_by
        OR NEW.revoke_reason IS DISTINCT FROM OLD.revoke_reason) THEN
        RAISE EXCEPTION 'this invitation has been withdrawn and by whom is recorded once';
    END IF;
    -- The link, the role and the window are what the invitation *is*; a resend is a new
    -- row (D4) rather than a rewritten one.
    IF NEW.token_hash <> OLD.token_hash OR NEW.role_id <> OLD.role_id
       OR NEW.expires_at <> OLD.expires_at THEN
        RAISE EXCEPTION
            'an invitation keeps its link, its role and its window; a resend is a new '
            'invitation';
    END IF;
    -- **The address may not move while the link is alive** (D12). An invitation is a bearer
    -- credential that creates an identity with a role, and the address is where it is sent --
    -- so a writable address on a live row is a way to redirect somebody else's grant. On a
    -- settled row the token is spent or withdrawn and `accept_invitation` refuses it either
    -- way, which is what makes MOD-009's erasure the only writer that can reach here.
    IF NEW.email_normalized <> OLD.email_normalized
       AND OLD.accepted_at IS NULL AND OLD.revoked_at IS NULL THEN
        RAISE EXCEPTION
            'this invitation is still live and its address is where the link was sent';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION iam.invitation_is_settled_once() FROM PUBLIC;

CREATE TRIGGER invitations_settled_once
    BEFORE UPDATE ON iam.invitations
    FOR EACH ROW EXECUTE FUNCTION iam.invitation_is_settled_once();

-- ----------------------------------------------------------------- the grants
--
-- **Insert and select, plus the two outcomes and the address.** The link, the role and the
-- window carry no UPDATE at all, which is what makes the trigger above the second line of
-- defence rather than the only one; the scopes are insert-only, because an invitation whose
-- clubs could change after it was sent is a link whose meaning moved under the person holding
-- it.
--
-- **The address is granted for one writer and the trigger names it** (D12). MOD-009's registry
-- is what forced the question: this row holds a staff member's email in the clear because the
-- canvas's pending list draws it, and `iam.identities.email_normalized` -- the authoritative
-- copy -- *is* cleared by an erasure. Leaving this one immutable would make an invitation the
-- most reachable copy of an erased person's address in the build, in the one plane where
-- erasure works at all. So the column is writable and the trigger refuses the write while the
-- invitation is live, which is the half that keeps a bearer credential from being redirected.
--
-- **No DELETE anywhere**, as nowhere in `iam`: "was this address ever invited, by whom, and
-- what happened" is asked precisely when somebody should not have been let in.
GRANT SELECT, INSERT ON iam.invitations TO veyro_iam_app;
GRANT UPDATE (accepted_at, accepted_identity_id, revoked_at, revoked_by, revoke_reason,
              email_normalized)
    ON iam.invitations TO veyro_iam_app;
GRANT SELECT, INSERT ON iam.invitation_scopes TO veyro_iam_app;
