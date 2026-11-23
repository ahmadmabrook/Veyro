-- MOD-026 slice 2 — AUT-02-R05's delegation, and the three refusals that make it safe.
--
-- Design record: `knowledge/00-Decisions/ADR-0009-mod026-tasks-cases-approvals-sla.md`.
--
-- **MOD-008 had a `delegated_from` column and deleted it**, because "no code set and no
-- evaluator read" it -- a column implying a delegation model that did not exist, which is
-- this build's recurring shape. So the model is built or the word is not claimed.
--
-- **Delegation is new capability that can defeat the invariant MOD-026 claims.** INV-AUT-02
-- compares the decider against the requester; if Alice raises a request and has delegated her
-- approval authority to Bob, Bob deciding it is Alice approving her own request through a
-- proxy -- separation of duties intact in the column and gone in fact. That is MOD-007's "a
-- remedy is new capability, so review it as such", which was learned when a recovery
-- allowance added to close one finding reached `issue_recovery_codes` and became a backdoor.
-- So this migration adds one table and one column, and three refusals.

-- --------------------------------------------------------- the delegations
--
-- **A window, both ends, and no open-ended form.** A delegation with no end is a permanent
-- transfer of approval authority, which is a role assignment and already has a table;
-- conflating the two would let a convenience for somebody's holiday become a standing grant
-- nobody reviews. Ninety days is the ceiling, which is longer than any absence this is for.
CREATE TABLE iam.approval_delegations (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    delegation_id uuid NOT NULL DEFAULT gen_random_uuid(),
    from_identity_id uuid NOT NULL,
    to_identity_id uuid NOT NULL,
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    reason text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    create_correlation_id uuid NOT NULL,
    revoked_at timestamptz,
    revoked_by uuid,
    revoke_reason text,
    revoke_correlation_id uuid,
    PRIMARY KEY (tenant_id, delegation_id),
    FOREIGN KEY (tenant_id, from_identity_id)
        REFERENCES iam.identities (tenant_id, identity_id),
    FOREIGN KEY (tenant_id, to_identity_id)
        REFERENCES iam.identities (tenant_id, identity_id),
    FOREIGN KEY (tenant_id, created_by) REFERENCES iam.identities (tenant_id, identity_id),
    CONSTRAINT approval_delegations_not_self CHECK (from_identity_id <> to_identity_id),
    CONSTRAINT approval_delegations_reason_stated CHECK (reason ~ '[^[:space:]]'),
    CONSTRAINT approval_delegations_ordered CHECK (ends_at > starts_at),
    -- Ninety days, and a start no more than a year out. MOD-021's rule: a window whose two
    -- ends the same writer supplies is not a window, so at least one of them is bounded
    -- against the server's clock. One-sided, because a lower bound fails every existing row
    -- the next time the constraint is validated.
    CONSTRAINT approval_delegations_bounded
        CHECK (ends_at - starts_at <= interval '90 days'),
    CONSTRAINT approval_delegations_not_parked
        CHECK (starts_at <= now() + interval '365 days'),
    CONSTRAINT approval_delegations_revocation_attributed CHECK (
        (revoked_at IS NULL AND revoked_by IS NULL AND revoke_reason IS NULL
         AND revoke_correlation_id IS NULL)
        OR (revoked_at IS NOT NULL AND revoked_by IS NOT NULL
            AND coalesce(revoke_reason, '') ~ '[^[:space:]]'
            AND revoke_correlation_id IS NOT NULL))
);
ALTER TABLE iam.approval_delegations ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.approval_delegations FORCE ROW LEVEL SECURITY;
CREATE POLICY approval_delegations_tenant ON iam.approval_delegations
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE INDEX approval_delegations_live
    ON iam.approval_delegations (tenant_id, to_identity_id, from_identity_id, ends_at)
    WHERE revoked_at IS NULL;

-- ------------------------------------------- on whose authority a decision was made
--
-- **Both identities, because they answer different questions.** "Who actually decided" is
-- `decided_by` and is what INV-AUT-02 is about; "on whose authority" is this. A model storing
-- only one of them cannot answer the other, and a delegated approval that recorded only the
-- delegator would put a decision in somebody's name that they did not make -- which is the
-- "evidence with nobody's name on it" finding inverted.
ALTER TABLE iam.approval_decisions
    ADD COLUMN on_behalf_of uuid,
    ADD CONSTRAINT approval_decisions_on_behalf_is_not_self
        CHECK (on_behalf_of IS NULL OR on_behalf_of <> decided_by),
    ADD FOREIGN KEY (tenant_id, on_behalf_of)
        REFERENCES iam.identities (tenant_id, identity_id);

-- ------------------------------- the requester may not decide through a proxy either
--
-- The invariant's trigger, extended. Everything about it that was true stays true: it reads
-- the request's **snapshot** and never the policy, it is **conditional** on that snapshot
-- because a policy may legitimately permit self-approval, and it takes `FOR UPDATE` because
-- a trigger that reads a parent row to decide whether a child may be written has to lock it.
--
-- What is new is one clause. Without it the whole of separation of duties is bought by
-- delegating to a colleague for an afternoon.
CREATE OR REPLACE FUNCTION iam.approval_decider_is_not_the_requester() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    asked_by uuid;
    separated boolean;
BEGIN
    SELECT requested_by, separation_of_duties INTO asked_by, separated
    FROM iam.approval_requests
    WHERE tenant_id = NEW.tenant_id AND request_id = NEW.request_id
    FOR UPDATE;
    -- A missing parent is the foreign key's refusal, not this one: the composite key is
    -- checked after this BEFORE trigger, so returning lets the key speak and keeps the two
    -- distinguishable.
    IF asked_by IS NULL THEN
        RETURN NEW;
    END IF;
    IF separated AND NEW.decided_by = asked_by THEN
        RAISE EXCEPTION
            'the requester may not decide their own request: this approval policy requires '
            'separation of duties, which was snapshotted onto the request when it was made';
    END IF;
    IF separated AND NEW.on_behalf_of = asked_by THEN
        RAISE EXCEPTION
            'the requester may not decide their own request through a delegate: separation '
            'of duties is about whose authority the decision carries, not only whose hand '
            'pressed the button';
    END IF;
    RETURN NEW;
END;
$$;

-- -------------------------------------- a cited delegation is the authority, or it is not
--
-- **"A cited authority is the authority, or it is decoration beside the figure."** MOD-017's
-- rule, learned when an agreement cited a price resolution for 45.00 and recorded 4.50. Here
-- the figure is somebody else's approval power: without this, `on_behalf_of` is a text field
-- that says whatever the caller types, and any approver claims anybody's authority.
--
-- The delegation has to be live **at the moment of the decision**, which is `now()` and not a
-- caller-supplied instant: a decision time a caller chooses decides whether the authority
-- existed, which is MOD-011's unbounded `observed_at` in a place where it grants power.
CREATE OR REPLACE FUNCTION iam.approval_delegation_is_live() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    IF NEW.on_behalf_of IS NULL THEN
        RETURN NEW;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM iam.approval_delegations
         WHERE tenant_id = NEW.tenant_id
           AND from_identity_id = NEW.on_behalf_of
           AND to_identity_id = NEW.decided_by
           AND revoked_at IS NULL
           AND starts_at <= now() AND ends_at > now()
    ) THEN
        RAISE EXCEPTION
            'this decision claims to act on another identity''s authority and no live '
            'delegation grants it';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER approval_decisions_delegation_is_live
    BEFORE INSERT ON iam.approval_decisions
    FOR EACH ROW EXECUTE FUNCTION iam.approval_delegation_is_live();

-- ------------------------------------------------- a delegation is not transitive
--
-- Bob delegating onward to Carol makes "on whose authority" a chain, and a chain cannot be
-- evaluated at decision time without walking it -- which is a recursive query on every
-- approval, and a loop if anybody closes one. The honest answer is to refuse the second hop
-- and say so, which is also the answer MOD-019 gives for a dependency cycle: the service
-- refuses rather than the schema modelling something it cannot check cheaply.
CREATE OR REPLACE FUNCTION iam.approval_delegation_is_not_transitive() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM iam.approval_delegations
         WHERE tenant_id = NEW.tenant_id
           AND to_identity_id = NEW.from_identity_id
           AND revoked_at IS NULL
           AND ends_at > now()
    ) THEN
        RAISE EXCEPTION
            'this identity already holds a delegation from somebody else, and a delegation '
            'is not passed on: whose authority a decision carries has to be one answer';
    END IF;
    IF EXISTS (
        SELECT 1 FROM iam.approval_delegations
         WHERE tenant_id = NEW.tenant_id
           AND from_identity_id = NEW.to_identity_id
           AND revoked_at IS NULL
           AND ends_at > now()
    ) THEN
        RAISE EXCEPTION
            'this identity has already delegated their own approvals away, so they cannot '
            'hold somebody else''s as well';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER approval_delegations_not_transitive
    BEFORE INSERT ON iam.approval_delegations
    FOR EACH ROW EXECUTE FUNCTION iam.approval_delegation_is_not_transitive();

-- ----------------------------------------------------------------- the grants
--
-- **The revocation only.** Who delegated to whom and for how long is what the row exists to
-- state; moving any of it would rewrite whose authority an approval already carried, which
-- is MOD-016's `cat_prices.effective_to` in the one place it would be worst.
GRANT SELECT, INSERT ON iam.approval_delegations TO veyro_iam_app;
GRANT UPDATE (revoked_at, revoked_by, revoke_reason, revoke_correlation_id)
    ON iam.approval_delegations TO veyro_iam_app;

REVOKE ALL ON FUNCTION iam.approval_delegation_is_live() FROM PUBLIC;
REVOKE ALL ON FUNCTION iam.approval_delegation_is_not_transitive() FROM PUBLIC;
