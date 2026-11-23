-- MOD-026 slice 5 — AUT-02-R05's last word: "sequential, parallel".
--
-- Design record: `knowledge/00-Decisions/ADR-0009-mod026-tasks-cases-approvals-sla.md`, D1a.
--
-- **The engine had no notion of a second *kind* of approver.** `required_approvals` is a
-- quorum of one authority, so "a club manager and then finance" was unexpressible -- and the
-- essential content of the requirement is exactly those two facts: an approval can need more
-- than one kind of approver, and sequential means the second kind cannot decide before the
-- first has.
--
-- **A stage is "N holders of permission P", keyed by the permission**, which is what makes the
-- combination rule survive. `policy_for` combines every applicable policy and never chooses
-- between them, because a single column naming one permission had to pick by row order when
-- two policies applied at the same strictness. A stage *list* has that problem one level up:
-- concatenating two policies' stages is order-dependent, the exact dependence combining was
-- built to remove. Keyed by permission it is not -- the count is the most any policy asks for
-- and the ordinal is the highest any gives it.
--
-- **A policy with no stage rows is a single-stage policy**, whose stage is its own
-- `required_permission` and `required_approvals`. So nothing already written changes, and this
-- migration backfills nothing: the absence *is* the existing meaning rather than a state to
-- migrate.
--
-- **`UNIQUE (tenant_id, request_id, decided_by)` is untouched, and it is what makes a stage
-- mean something.** One person, one decision per request across every stage: a two-stage
-- approval decided twice by one person is one approval wearing two hats, which is the thing
-- stages exist to prevent. The constraint that already stopped a quorum being one person
-- pressing the button twice turns out to be the constraint a stage needs, unchanged.

-- ------------------------------------------------- a policy's stages, in order
--
-- **One permission per stage.** A stage is one authority, so the set-versus-column argument
-- `approval_requests.required_permissions` settles does not arise here: where two policies
-- both name a stage for the same permission, the combination takes the larger count, and where
-- they name different permissions those are different stages.
CREATE TABLE iam.approval_policy_stages (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    approval_policy_id uuid NOT NULL,
    ordinal integer NOT NULL,
    required_permission text NOT NULL,
    required_approvals integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    create_correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, approval_policy_id, ordinal),
    FOREIGN KEY (tenant_id, approval_policy_id)
        REFERENCES iam.approval_policies (tenant_id, approval_policy_id),
    FOREIGN KEY (tenant_id, created_by) REFERENCES iam.identities (tenant_id, identity_id),
    -- **One stage per permission within a policy.** Two stages naming the same authority is a
    -- quorum written as two rows, and the two encodings would then disagree about what the
    -- count is -- which is this build's "one module, two definitions" in a primary key.
    UNIQUE (tenant_id, approval_policy_id, required_permission),
    CONSTRAINT approval_policy_stages_ordinal CHECK (ordinal BETWEEN 1 AND 8),
    CONSTRAINT approval_policy_stages_count CHECK (required_approvals BETWEEN 1 AND 20),
    -- The same shape `approval_policies.action` and `role_permissions` use: a permission is
    -- three dotted segments and there is no wildcard, in the grammar or the evaluator.
    CONSTRAINT approval_policy_stages_permission_shape CHECK
        (required_permission ~ '^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*){2}$')
);
ALTER TABLE iam.approval_policy_stages ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.approval_policy_stages FORCE ROW LEVEL SECURITY;
CREATE POLICY approval_policy_stages_tenant ON iam.approval_policy_stages
    FOR ALL TO veyro_iam_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **Whether the stages are in order, on the policy rather than on each stage.** R05 names the
-- two as properties of an approval rather than of a step, and a per-stage flag would admit
-- "stage 2 is sequential and stage 3 is not", which is not a thing anybody means.
ALTER TABLE iam.approval_policies
    ADD COLUMN sequential boolean NOT NULL DEFAULT false;

-- ---------------------------------------------- the request's own snapshot
--
-- **Snapshotted, which is not a new decision.** MOD-008's review put the snapshot on the
-- request after re-deriving the terms let somebody holding `authz.policy.write` turn
-- separation of duties off for a request already in flight and then approve their own. A
-- stage list re-derived at decision time is the same defect with more surface.
CREATE TABLE iam.approval_request_stages (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    request_id uuid NOT NULL,
    ordinal integer NOT NULL,
    required_permission text NOT NULL,
    required_approvals integer NOT NULL,
    PRIMARY KEY (tenant_id, request_id, ordinal),
    FOREIGN KEY (tenant_id, request_id)
        REFERENCES iam.approval_requests (tenant_id, request_id),
    UNIQUE (tenant_id, request_id, required_permission),
    CONSTRAINT approval_request_stages_ordinal CHECK (ordinal BETWEEN 1 AND 8),
    CONSTRAINT approval_request_stages_count CHECK (required_approvals BETWEEN 1 AND 20),
    CONSTRAINT approval_request_stages_permission_shape CHECK
        (required_permission ~ '^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*){2}$')
);
ALTER TABLE iam.approval_request_stages ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.approval_request_stages FORCE ROW LEVEL SECURITY;
CREATE POLICY approval_request_stages_tenant ON iam.approval_request_stages
    FOR ALL TO veyro_iam_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE iam.approval_requests
    ADD COLUMN sequential boolean NOT NULL DEFAULT false;

-- **A decision names the stage it is for, and cannot name one the request does not have.**
-- Defaulted to 1 so every existing decision keeps its meaning -- a request with no stage rows
-- is single-stage, and its one stage is ordinal 1.
ALTER TABLE iam.approval_decisions
    ADD COLUMN stage_ordinal integer NOT NULL DEFAULT 1;
-- **And no range CHECK on it, because the trigger below subsumes one.** A BEFORE trigger runs
-- before every CHECK on the table, and `approval_decision_names_a_real_stage` refuses any
-- ordinal the request has not got -- which for a staged request means anything outside its own
-- stages, themselves bounded 1..8, and for a single-stage request means anything but 1. So a
-- range CHECK here had no isolating case and could not have one: the mutation sweep said so by
-- reporting its drop as uncaught, and the probe written for it was answered by the trigger.
-- Deleted rather than tested harder, which is the judgement MOD-016 made for a kind domain its
-- operand constraint already named and MOD-018 for a ceiling a trigger already bounded.

-- ------------------------------------------------------------- the refusals
--
-- **A decision on a stage the request does not have.** Not a foreign key, because a
-- single-stage request has no stage rows at all -- so "ordinal 1 with no rows" is the one
-- admissible absence and every other ordinal is a decision about nothing. A composite key
-- cannot express that; a trigger can, and it says which case it refused.
CREATE OR REPLACE FUNCTION iam.approval_decision_names_a_real_stage() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    staged integer;
BEGIN
    SELECT count(*) INTO staged FROM iam.approval_request_stages
     WHERE tenant_id = NEW.tenant_id AND request_id = NEW.request_id;
    IF staged = 0 THEN
        IF NEW.stage_ordinal <> 1 THEN
            RAISE EXCEPTION
                'this request has one stage, so a decision on stage % is a decision about '
                'nothing', NEW.stage_ordinal;
        END IF;
        RETURN NEW;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM iam.approval_request_stages
         WHERE tenant_id = NEW.tenant_id AND request_id = NEW.request_id
           AND ordinal = NEW.stage_ordinal
    ) THEN
        RAISE EXCEPTION 'this request has no stage %', NEW.stage_ordinal;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER approval_decisions_stage_exists
    BEFORE INSERT ON iam.approval_decisions
    FOR EACH ROW EXECUTE FUNCTION iam.approval_decision_names_a_real_stage();

-- **A sequential stage is open only when every earlier one has its count, and there is
-- deliberately no lock.** The first version took `FOR UPDATE` on the request row, by analogy
-- with MOD-019's `FOR SHARE` finding -- a trigger that reads a parent row to decide whether a
-- child may be written has to lock it. The mutation sweep reported its removal as uncaught,
-- and checking each reader is why it is gone rather than tested harder:
--
--   * `sequential` cannot move. `veyro_iam_app` holds UPDATE on `state` and `decided_at` and
--     on nothing else, so the flag this reads is immutable for every runtime writer.
--   * The earlier stages' approvals come from `approval_decisions`, which is insert-only.
--     Two concurrent decisions at READ COMMITTED each see only committed rows, so each is
--     fail-*closed* with respect to the other: without the lock, a stage-2 decision racing
--     the stage-1 approval it depends on is refused rather than admitted. There is no
--     direction in which the absence lets through something the lock would have refused.
--
-- So the lock would only have made this guard *more permissive* under concurrency, which is
-- the wrong direction for a guard -- and the service's own `SELECT ... FOR UPDATE` in
-- `_decide_in_tx` is what makes the ordinary path deterministic for a caller.
CREATE OR REPLACE FUNCTION iam.approval_stage_is_open() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    in_order boolean;
    unmet integer;
BEGIN
    SELECT sequential INTO in_order FROM iam.approval_requests
     WHERE tenant_id = NEW.tenant_id AND request_id = NEW.request_id;
    IF in_order IS NULL OR NOT in_order OR NEW.stage_ordinal = 1 THEN
        RETURN NEW;
    END IF;
    SELECT count(*) INTO unmet
      FROM iam.approval_request_stages s
     WHERE s.tenant_id = NEW.tenant_id AND s.request_id = NEW.request_id
       AND s.ordinal < NEW.stage_ordinal
       AND s.required_approvals > (
           SELECT count(DISTINCT d.decided_by) FROM iam.approval_decisions d
            WHERE d.tenant_id = s.tenant_id AND d.request_id = s.request_id
              AND d.stage_ordinal = s.ordinal AND d.decision = 'approved');
    IF unmet > 0 THEN
        RAISE EXCEPTION
            'stage % is not open: % earlier stage(s) have not been approved, and this '
            'approval is sequential', NEW.stage_ordinal, unmet;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER approval_decisions_stage_is_open
    BEFORE INSERT ON iam.approval_decisions
    FOR EACH ROW EXECUTE FUNCTION iam.approval_stage_is_open();

-- ----------------------------------------------------------------- the grants
--
-- **Insert and select only, on both stage tables.** A policy's stages are retired with the
-- policy -- `retired_at` is already how a policy stops applying -- and a request's stages are
-- the snapshot, which is the whole point: a stage list that could be edited after a request
-- was made is the defect the snapshot exists to prevent.
GRANT SELECT, INSERT ON iam.approval_policy_stages TO veyro_iam_app;
GRANT SELECT, INSERT ON iam.approval_request_stages TO veyro_iam_app;

REVOKE ALL ON FUNCTION iam.approval_decision_names_a_real_stage() FROM PUBLIC;
REVOKE ALL ON FUNCTION iam.approval_stage_is_open() FROM PUBLIC;
