-- MOD-026 slice 2, first job — INV-AUT-02 in the database.
--
-- > "Approvers cannot approve their own restricted actions unless explicit emergency policy
-- > applies."
--
-- MOD-026 is the module that invariant belongs to, and **a module cannot claim an invariant
-- whose only enforcement is a layer it does not own.** Today the rule lives in
-- `app/authorization/approval.py` and nowhere else: `iam.approval_decisions` carries exactly
-- one CHECK, on the `decision` domain, plus a unique index that stops one person pressing the
-- button twice. The service is correct, and the service is the service -- this build's
-- standing premise is that the schema is the half that holds when it is wrong, which is why
-- MOD-018 wrote seven one-way triggers and MOD-021 wrote fourteen.
--
-- Design record: `knowledge/00-Decisions/ADR-0009-mod026-tasks-cases-approvals-sla.md`.

-- ------------------------------------------------ the snapshot has to be a snapshot
--
-- **MOD-008's review found that re-deriving an approval's terms at decision time let somebody
-- holding `authz.policy.write` switch separation of duties off for a request already in
-- flight and then approve their own.** The fix was to snapshot the terms onto
-- `iam.approval_requests` when the request is made. That closed the re-derivation and left
-- the snapshot itself rewritable: the grant is table-wide `UPDATE`, so `separation_of_duties`,
-- `requested_by`, `required_approvals`, `required_permissions`, `amount_minor` and
-- `expires_at` are all writable by the runtime role, and the same attack works one step over.
--
-- The service writes exactly two columns here -- `state` and `decided_at`, in one statement --
-- so the grant is narrowed to those. That is MOD-016's `cat_prices.effective_to` finding for
-- the third time in this build: **a granted column no service writes is an unattributed edit
-- path**, and here it is an edit path through the one control INV-AUT-02 names.
--
-- **`SELECT ... FOR UPDATE` still works under a column-scoped grant**, which was measured
-- rather than reasoned about: `has_table_privilege(..., 'UPDATE')` reads false afterwards, so
-- deriving the answer from that would have been wrong, and the trigger below depends on it.
REVOKE UPDATE ON iam.approval_requests FROM veyro_iam_app;
GRANT UPDATE (state, decided_at) ON iam.approval_requests TO veyro_iam_app;

-- -------------------------------------------- an approver is not the requester
--
-- **Conditional, and that is the part the obvious version gets wrong.**
-- `approval.py` reads `if policy.separation_of_duties and decided_by == requested_by`, so a
-- policy may legitimately permit self-approval -- which is also what the invariant's own
-- "unless explicit emergency policy applies" provides for. A trigger refusing it outright
-- would make the database and the service disagree, which is MOD-020's waitlist shape, where
-- both encodings agreed with each other and neither agreed with the service.
--
-- **It reads the snapshot and never the policy.** Re-deriving here would reintroduce the
-- defect the snapshot exists to prevent, one layer down.
--
-- **`FOR UPDATE`, not `FOR SHARE` and not a bare read.** A trigger that reads a parent row to
-- decide whether a child may be written has to lock it: MOD-019's capacity trigger took a
-- share lock and two ordinary transactions put four places in a two-place class, and MOD-021
-- shipped three triggers that took no lock at all. Without it, two approvers racing one
-- request both read `state = 'pending'` and the second could be the requester.
--
-- It cannot be a CHECK, because `requested_by` lives on the parent row and a CHECK cannot see
-- another table -- the `sec_legal_holds` reason, from a different direction.
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
    -- **A missing parent is the foreign key's refusal, not this one.** The composite key on
    -- (tenant_id, request_id) is checked after this BEFORE trigger, so this branch would
    -- otherwise answer for it and the probe could not tell the two apart -- the confusion
    -- this repository records for MOD-019's two session triggers and MOD-021's three
    -- `NOT EXISTS` branches. Returning lets the key speak.
    IF asked_by IS NULL THEN
        RETURN NEW;
    END IF;
    IF separated AND NEW.decided_by = asked_by THEN
        RAISE EXCEPTION
            'the requester may not decide their own request: this approval policy requires '
            'separation of duties, which was snapshotted onto the request when it was made';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER approval_decisions_decider_is_not_the_requester
    BEFORE INSERT ON iam.approval_decisions
    FOR EACH ROW EXECUTE FUNCTION iam.approval_decider_is_not_the_requester();

REVOKE ALL ON FUNCTION iam.approval_decider_is_not_the_requester() FROM PUBLIC;
