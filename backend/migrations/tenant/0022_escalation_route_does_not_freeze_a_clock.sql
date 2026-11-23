-- MOD-026 (AUT-02-R06): an escalation route that has gone must not freeze the clock.
--
-- `tsk_sla_escalation_is_live` is `BEFORE INSERT OR UPDATE` and re-judges the route on every
-- write, so retiring a queue refused **every later update to every clock pointing at it** --
-- including the settlement. A target whose escalation queue was merged into another team
-- could therefore never be judged: it stayed `running` for ever, the missed promise was
-- never recorded, and R07's compliance reporting counted it as still in hand.
--
-- **A guard that admits a state nothing can leave is worse than no guard**, which is
-- MOD-016's bundle-fulfilment finding and MOD-018's "a state machine's only exit has to be
-- reachable". The control is "a clock may not be pointed at a dead bell"; it was behaving as
-- "a clock pointed at a dead bell is frozen", and the second is not a stricter version of
-- the first -- it refuses the one write that makes the record true.
--
-- The remedy is the one this module's own sibling already uses: `tsk_task_matches_its_case`
-- re-checks its parent only on an INSERT or when the pointer actually moves
-- (`OLD.case_id IS DISTINCT FROM NEW.case_id`). The same clause here, written one file
-- later and not applied, is what this migration adds. Setting or repointing a route to a
-- retired queue is still refused; an unchanged route is not re-judged.
--
-- **Found by writing the second reader.** `sweep_breaches` settles a breached clock, and the
-- case for "the route was retired after the clock started" -- which this build's own "a
-- control consulted once is a control with a window" rule says to write -- reported nothing
-- breached instead of a breach with a skipped escalation.

CREATE OR REPLACE FUNCTION plt01.tsk_sla_escalation_is_live() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    queue_status text;
BEGIN
    -- The route is judged when it is set and when it moves, and at no other time. Judging it
    -- on every update makes a retired queue a lock on the row.
    IF TG_OP = 'UPDATE'
       AND NEW.escalate_to_queue_id IS NOT DISTINCT FROM OLD.escalate_to_queue_id THEN
        RETURN NEW;
    END IF;
    IF NEW.escalate_to_queue_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT status INTO queue_status FROM plt01.tsk_queues
     WHERE tenant_id = NEW.tenant_id AND queue_id = NEW.escalate_to_queue_id
     FOR UPDATE;
    -- A missing queue is the foreign key's refusal; returning keeps the two tellable apart.
    IF queue_status IS NULL THEN
        RETURN NEW;
    END IF;
    IF queue_status <> 'active' THEN
        RAISE EXCEPTION
            'this clock escalates to a retired queue, which is an alarm wired to a bell '
            'nobody answers';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION plt01.tsk_sla_escalation_is_live() FROM PUBLIC;
