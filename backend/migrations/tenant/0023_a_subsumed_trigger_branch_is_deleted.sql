-- MOD-026: two trigger branches that no row can reach alone, deleted rather than tested
-- harder.
--
-- CHECK 114 gave this module's eleven trigger refusals their first isolating probes, and a
-- mutation sweep over those probes found two with no case available -- not because the probe
-- was badly written, but because every row that reaches the branch is already refused by
-- something else. That is MOD-016's `cat_eligibility_rules_kind` judgement, which this file
-- follows: one rule that a reader can reason about beats two where the weaker is permanently
-- unprovable. A branch nobody can break on purpose is a branch nobody has tested, and it
-- reads as a control.
--
-- **`tsk_settlement_is_final`: "a settled task does not reopen".** It fires when the row was
-- settled and the new status is not `done` or `cancelled`. For such a row to satisfy
-- `tsk_tasks_settlement_attributed`, all four settlement columns must be NULL -- and NULLing
-- `settled_at` trips the branch above it, which runs first. So the two together cover every
-- case it has, and the operator sees a clearer sentence from whichever speaks.
--
-- **`tsk_task_matches_its_case`: "this task names a case that does not exist".** The
-- composite foreign key `(tenant_id, case_id)` refuses exactly that row, in this tenant and
-- in any other. This module's own sibling already settled how to handle it:
-- `tsk_sla_escalation_is_live` *returns* on a missing queue, with the comment "a missing
-- queue is the foreign key's refusal; returning keeps the two tellable apart". The same
-- shape here, so the lookup guards the branches below it rather than duplicating the key --
-- and `case_queue` being NULL leaves both of those false, so the row falls through to the
-- key that is the actual control.
--
-- Neither change weakens anything: both rows are refused before and after, by the constraint
-- and the key that were always the control. What changes is that every surviving branch has
-- a case that only it answers.

CREATE OR REPLACE FUNCTION plt01.tsk_task_matches_its_case() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    case_queue uuid;
    case_status text;
BEGIN
    IF NEW.case_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT queue_id, status INTO case_queue, case_status
    FROM plt01.tsk_cases
    WHERE tenant_id = NEW.tenant_id AND case_id = NEW.case_id
    FOR UPDATE;
    -- A missing case is the foreign key's refusal; returning keeps the two tellable apart,
    -- which is what this module's escalation trigger already does for a missing queue. Both
    -- branches below are false when the lookup found nothing, so the row reaches the key.
    IF case_queue IS NULL THEN
        RETURN NEW;
    END IF;
    IF case_queue <> NEW.queue_id THEN
        RAISE EXCEPTION
            'this task is filed under a different queue from its case, so the same work '
            'would be counted in two backlogs';
    END IF;
    -- **A new task on a closed case is work nobody will see.** A resolved case can still take
    -- one -- the resolution may need following up -- but closed is filed, and reopening is a
    -- status change somebody makes on purpose.
    IF case_status = 'closed' AND (TG_OP = 'INSERT' OR OLD.case_id IS DISTINCT FROM
                                   NEW.case_id) THEN
        RAISE EXCEPTION 'this case is closed, so a task cannot be added to it';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION plt01.tsk_settlement_is_final() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    IF OLD.settled_at IS NOT NULL THEN
        -- Reopening is covered by this branch together with
        -- `tsk_tasks_settlement_attributed`: a status outside done/cancelled needs all four
        -- settlement columns NULL, and NULLing `settled_at` is refused right here.
        IF NEW.settled_at IS DISTINCT FROM OLD.settled_at
           OR NEW.settled_by IS DISTINCT FROM OLD.settled_by
           OR NEW.settle_reason IS DISTINCT FROM OLD.settle_reason THEN
            RAISE EXCEPTION
                'this task was already settled; who settled it, when and why do not move';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION plt01.tsk_task_matches_its_case() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.tsk_settlement_is_final() FROM PUBLIC;
