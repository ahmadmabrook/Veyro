-- MOD-026 slice 3b — AUT-02-R06: the clocks and their pauses.
--
-- The arithmetic is `app/tasks/sla.py` and nothing here duplicates it. What these two tables
-- hold is the *input*: what the target is, when it started, which calendar it is measured
-- against, and every span it was stopped for.
--
-- **There is no countdown column and the absence is swept for.** A stored "minutes
-- remaining" is a second copy of the truth that goes stale between writes, and a breach
-- flag is the same thing with fewer values. MOD-018 stores no balance, MOD-019 no
-- `held_count`, MOD-016 derives `in_window`, MOD-022 derives occupancy; this is the fifth,
-- and the forbidden-name sweep in the isolation suite is how the absence is kept, because an
-- absence is exactly what a later migration restores.

-- ------------------------------------------------------------------ the clocks
--
-- **A clock is about one task or one case, never both and never neither.** A clock with no
-- subject is a timer nobody is waiting on; one with two is a figure two backlogs would
-- count. The CHECK is the same shape as `tsk_business_hours`' anchor rule and for the same
-- reason -- MOD-020's "a declared state nothing writes" in the shape of a row nothing reads.
--
-- **`location_id` is resolved when the clock starts, not read later.** A queue can be moved
-- between clubs, and a clock re-measured against a different calendar afterwards would
-- change what a member was promised after the fact -- MOD-017's "a session snapshots
-- everything that describes it", applied to a promise instead of a class.
CREATE TABLE plt01.tsk_sla_clocks (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    clock_id uuid NOT NULL DEFAULT gen_random_uuid(),
    task_id uuid,
    case_id uuid,
    location_id uuid NOT NULL,
    target_seconds integer NOT NULL,
    warn_at_basis_points integer NOT NULL DEFAULT 8000,
    started_at timestamptz NOT NULL,
    escalate_to_queue_id uuid,
    status text NOT NULL DEFAULT 'running',
    settled_at timestamptz,
    settled_by uuid,
    settle_reason text,
    settle_correlation_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    create_correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, clock_id),
    FOREIGN KEY (tenant_id, task_id) REFERENCES plt01.tsk_tasks (tenant_id, task_id),
    FOREIGN KEY (tenant_id, case_id) REFERENCES plt01.tsk_cases (tenant_id, case_id),
    FOREIGN KEY (tenant_id, location_id)
        REFERENCES plt01.locations (tenant_id, location_id),
    FOREIGN KEY (tenant_id, escalate_to_queue_id)
        REFERENCES plt01.tsk_queues (tenant_id, queue_id),
    CONSTRAINT tsk_sla_clocks_one_subject CHECK ((task_id IS NULL) <> (case_id IS NULL)),
    -- **A target in seconds, bounded.** `sla.due_at` walks at most two years of business
    -- hours before refusing, and an unbounded integer here would reach that ceiling as a
    -- 500 rather than as a refusal at the boundary -- MOD-011's and MOD-012's finding, where
    -- `NumericValueOutOfRange` is a `DataError` and not the `CheckViolation` the handlers
    -- catch. One minute to one year of wall-clock seconds.
    CONSTRAINT tsk_sla_clocks_target_sane
        CHECK (target_seconds BETWEEN 60 AND 31536000),
    -- **Basis points, not a float.** A fraction stored as a double is a figure that renders
    -- differently in two places, which is the money discipline this build applies everywhere
    -- else; 8000 is 80%.
    CONSTRAINT tsk_sla_clocks_warn_sane
        CHECK (warn_at_basis_points BETWEEN 1 AND 9999),
    CONSTRAINT tsk_sla_clocks_status
        CHECK (status IN ('running', 'met', 'breached', 'cancelled')),
    CONSTRAINT tsk_sla_clocks_settlement_attributed CHECK (
        (status = 'running' AND settled_at IS NULL AND settled_by IS NULL
         AND settle_reason IS NULL AND settle_correlation_id IS NULL)
        OR (status <> 'running' AND settled_at IS NOT NULL AND settled_by IS NOT NULL
            AND coalesce(settle_reason, '') ~ '[^[:space:]]'
            AND settle_correlation_id IS NOT NULL))
);
ALTER TABLE plt01.tsk_sla_clocks ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.tsk_sla_clocks FORCE ROW LEVEL SECURITY;
CREATE POLICY tsk_sla_clocks_tenant ON plt01.tsk_sla_clocks
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
-- One running clock per subject: two targets on one task is two promises, and which one a
-- breach report counts would be the planner's choice.
CREATE UNIQUE INDEX tsk_sla_clocks_one_running_per_task
    ON plt01.tsk_sla_clocks (tenant_id, task_id)
    WHERE status = 'running' AND task_id IS NOT NULL;
CREATE UNIQUE INDEX tsk_sla_clocks_one_running_per_case
    ON plt01.tsk_sla_clocks (tenant_id, case_id)
    WHERE status = 'running' AND case_id IS NOT NULL;
CREATE INDEX tsk_sla_clocks_running
    ON plt01.tsk_sla_clocks (tenant_id, location_id, started_at)
    WHERE status = 'running';

-- ----------------------------------------------------------------- the pauses
--
-- R06's "pause reasons". **A row with an actor and a reason, because "why did this clock
-- stop" is asked precisely when a target was missed** -- which is the "evidence with nobody's
-- name on it answers nothing" rule, in the one place a missed promise gets explained.
--
-- An open pause has no `resumed_at`; the arithmetic treats it as running to `now()`.
CREATE TABLE plt01.tsk_sla_pauses (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    pause_id uuid NOT NULL DEFAULT gen_random_uuid(),
    clock_id uuid NOT NULL,
    paused_at timestamptz NOT NULL,
    resumed_at timestamptz,
    reason text NOT NULL,
    paused_by uuid NOT NULL,
    pause_correlation_id uuid NOT NULL,
    resumed_by uuid,
    resume_correlation_id uuid,
    PRIMARY KEY (tenant_id, pause_id),
    FOREIGN KEY (tenant_id, clock_id)
        REFERENCES plt01.tsk_sla_clocks (tenant_id, clock_id),
    CONSTRAINT tsk_sla_pauses_reason_stated CHECK (reason ~ '[^[:space:]]'),
    CONSTRAINT tsk_sla_pauses_ordered CHECK (resumed_at IS NULL OR resumed_at > paused_at),
    CONSTRAINT tsk_sla_pauses_resumption_attributed CHECK (
        (resumed_at IS NULL AND resumed_by IS NULL AND resume_correlation_id IS NULL)
        OR (resumed_at IS NOT NULL AND resumed_by IS NOT NULL
            AND resume_correlation_id IS NOT NULL))
);
ALTER TABLE plt01.tsk_sla_pauses ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.tsk_sla_pauses FORCE ROW LEVEL SECURITY;
CREATE POLICY tsk_sla_pauses_tenant ON plt01.tsk_sla_pauses
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
-- One open pause per clock: a clock paused twice is stopped once, and two open rows make
-- "how long was it stopped" a sum over overlapping spans.
CREATE UNIQUE INDEX tsk_sla_pauses_one_open
    ON plt01.tsk_sla_pauses (tenant_id, clock_id) WHERE resumed_at IS NULL;

-- -------------------------------------- a clock and its subject share a tenant and a queue
--
-- The composite keys already carry `tenant_id`. What they cannot see is a clock whose
-- escalation queue has been retired -- an escalation route to a queue nobody reads is an
-- alarm wired to a disconnected bell, and it is the shape MOD-021's "a lookup that proves
-- something exists does not authorise what you do next" warns about.
--
-- `FOR UPDATE`, because a trigger that reads a parent row to decide whether a child may be
-- written has to lock it: MOD-019 shipped `FOR SHARE` and MOD-021 shipped three with none.
CREATE OR REPLACE FUNCTION plt01.tsk_sla_escalation_is_live() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    queue_status text;
BEGIN
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

CREATE TRIGGER tsk_sla_clocks_escalation_is_live
    BEFORE INSERT OR UPDATE ON plt01.tsk_sla_clocks
    FOR EACH ROW EXECUTE FUNCTION plt01.tsk_sla_escalation_is_live();

-- ------------------------------------------- a settled clock stays settled
--
-- A CHECK cannot see what a row used to be -- MOD-009's `sec_legal_holds` rule, and the
-- reason seven of MOD-018's lifecycle columns were rewritable while reading as immutable.
CREATE OR REPLACE FUNCTION plt01.tsk_sla_settlement_is_final() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    IF OLD.status <> 'running' THEN
        IF NEW.status <> OLD.status THEN
            RAISE EXCEPTION
                'this clock was already settled as %; a target is judged once', OLD.status;
        END IF;
        IF NEW.settled_at IS DISTINCT FROM OLD.settled_at
           OR NEW.settled_by IS DISTINCT FROM OLD.settled_by
           OR NEW.settle_reason IS DISTINCT FROM OLD.settle_reason THEN
            RAISE EXCEPTION
                'who settled this clock, when and why do not move once it is settled';
        END IF;
    END IF;
    IF NEW.started_at IS DISTINCT FROM OLD.started_at
       OR NEW.target_seconds IS DISTINCT FROM OLD.target_seconds THEN
        RAISE EXCEPTION
            'a target and its start do not move: re-measuring a promise after the fact is '
            'how a missed one becomes a met one';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER tsk_sla_clocks_settlement_final
    BEFORE UPDATE ON plt01.tsk_sla_clocks
    FOR EACH ROW EXECUTE FUNCTION plt01.tsk_sla_settlement_is_final();

-- ----------------------------------------------------------------- the grants
--
-- No DELETE, no TRUNCATE, no REFERENCES for any runtime role: a clock is the record of what
-- a tenant promised and whether it kept it, which is exactly what R07's compliance reporting
-- reads. A column is in an UPDATE grant only where a service writes it.

GRANT SELECT, INSERT ON plt01.tsk_sla_clocks TO veyro_cp_app, veyro_cp_worker;
-- Not `target_seconds`, `started_at`, `location_id` or the subject: the trigger refuses
-- those and the grant means it never has to.
GRANT UPDATE (status, settled_at, settled_by, settle_reason, settle_correlation_id,
              escalate_to_queue_id, warn_at_basis_points)
    ON plt01.tsk_sla_clocks TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.tsk_sla_pauses TO veyro_cp_app, veyro_cp_worker;
-- The resumption only. Not `paused_at` or `reason`: when a clock stopped and why is what the
-- row exists to state, and moving either rewrites how long a target was suspended -- the
-- `sec_legal_holds` finding, which is where this rule came from.
GRANT UPDATE (resumed_at, resumed_by, resume_correlation_id)
    ON plt01.tsk_sla_pauses TO veyro_cp_app, veyro_cp_worker;

REVOKE ALL ON FUNCTION plt01.tsk_sla_escalation_is_live() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.tsk_sla_settlement_is_final() FROM PUBLIC;
