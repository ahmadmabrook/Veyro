-- MOD-026 slice 1 — AUT-02-R01, R02, R03: the business calendar, tasks and cases.
--
-- Design record: `knowledge/00-Decisions/ADR-0009-mod026-tasks-cases-approvals-sla.md`.
-- Slices 2 (approval stages and delegation), 3 (SLA clocks and escalation) and 4 (the
-- reporting read and the three screens) follow; nothing here depends on them, which is why
-- this is the slice that lands first.
--
-- Three decisions from the ADR are visible in the shapes below and are worth restating where
-- somebody will read them:
--
--   * **A task's subject is a closed nine-name vocabulary with an id and no foreign key.**
--     R01 names member, lead, tenant, invoice, incident, device, booking, asset and workflow;
--     three of those are modules this build does not have. A free-text kind would make "how
--     many tasks are about invoices" unanswerable, which is MOD-010's restricted-field
--     argument applied to a discriminator, so the kind is a CHECK and the id is a claim the
--     service resolves for the six kinds whose tables exist.
--   * **Business hours are this module's own table** -- nothing in this repository records
--     when a club is open, MOD-022 says so and refuses to derive it, and MOD-019's rota is a
--     *resource's* rather than a site's.
--   * **No countdown is stored anywhere.** An SLA clock arrives in slice 3 as a function of
--     its target, its pauses and this calendar. The forbidden-name sweep in the isolation
--     suite is how that absence is kept, because an absence is what a later migration adds
--     back -- MOD-018's no-stored-balance and MOD-019's no-`held_count` for the third time.

-- ----------------------------------------------------------------- the queues
--
-- **A queue is a row rather than a string, because "team queue" is R02's word for something
-- nothing in this build models.** A text column would make every misspelling a new team and
-- would make R07's workload report a group-by over typos. The alternative -- a team module --
-- is not in AUT-02's scope, so the smallest honest thing is a named queue this module owns.
--
-- `location_id` is nullable and is a *scope*, not a boundary: a queue may belong to one club
-- or to the whole tenant, and `permit` resolves tenant-wide, so a club manager sees every
-- queue. That is MOD-014's standing scope gap and it is stated here rather than implied by a
-- column that looks like it restricts something.
CREATE TABLE plt01.tsk_queues (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    queue_id uuid NOT NULL DEFAULT gen_random_uuid(),
    queue_key text NOT NULL,
    display_name text NOT NULL,
    location_id uuid,
    status text NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    create_correlation_id uuid NOT NULL,
    retired_at timestamptz,
    retired_by uuid,
    retire_reason text,
    retire_correlation_id uuid,
    PRIMARY KEY (tenant_id, queue_id),
    FOREIGN KEY (tenant_id, location_id)
        REFERENCES plt01.locations (tenant_id, location_id),
    CONSTRAINT tsk_queues_key_shape
        CHECK (queue_key ~ '^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*)*$'
               AND length(queue_key) BETWEEN 2 AND 63),
    CONSTRAINT tsk_queues_name_stated CHECK (display_name ~ '[^[:space:]]'),
    CONSTRAINT tsk_queues_status CHECK (status IN ('active', 'retired')),
    -- A retirement is one decision, so the three facts about it arrive together or not at
    -- all. `coalesce` is load-bearing: `NULL ~ ...` is NULL and a CHECK passes on NULL, so
    -- without it a queue could be retired with no stated reason -- the trap MOD-014 and
    -- MOD-021 each paid for once.
    CONSTRAINT tsk_queues_retirement_attributed CHECK (
        (retired_at IS NULL AND retired_by IS NULL AND retire_reason IS NULL
         AND retire_correlation_id IS NULL)
        OR (retired_at IS NOT NULL AND retired_by IS NOT NULL
            AND coalesce(retire_reason, '') ~ '[^[:space:]]'
            AND retire_correlation_id IS NOT NULL)),
    CONSTRAINT tsk_queues_retired_is_retired
        CHECK ((status = 'retired') = (retired_at IS NOT NULL))
);
ALTER TABLE plt01.tsk_queues ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.tsk_queues FORCE ROW LEVEL SECURITY;
CREATE POLICY tsk_queues_tenant ON plt01.tsk_queues
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE UNIQUE INDEX tsk_queues_one_key ON plt01.tsk_queues (tenant_id, queue_key);

-- -------------------------------------------------------- the business calendar
--
-- INV-AUT-02: "SLA calculation is time-zone and business-calendar aware." The timezone is
-- `plt01.locations.timezone`, which MOD-019 already reads every rota window in; the calendar
-- is this.
--
-- **The weekly/dated split is MOD-019's, deliberately reused rather than re-chosen.** A row
-- with a `weekday` binds that weekday every week; a row with an `on_date` binds that date
-- only. Two rules in one build for "when is this open" is a pair of answers that disagree the
-- day either moves, and `sch_availability_windows` has the shape already.
--
-- **A location with no rows has no business hours, which is not the same as being closed all
-- week.** MOD-019's first version read an empty rota as "never available" and nothing could
-- be scheduled in a tenant at all. Here the consequence is an SLA that runs on wall-clock
-- elapsed time, and slice 3's response says so -- a clock that never advances is a breach
-- that never fires, which is the worse of the two failures.
--
-- **`kind` exists because a dated row has to be able to say "closed".** A public holiday is
-- not an absence of hours, it is a statement that the weekly pattern does not apply that day,
-- and without it the only way to express one would be deleting rows this table has no DELETE
-- grant for.
CREATE TABLE plt01.tsk_business_hours (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    window_id uuid NOT NULL DEFAULT gen_random_uuid(),
    location_id uuid NOT NULL,
    kind text NOT NULL,
    weekday integer,
    on_date date,
    opens_at time,
    closes_at time,
    note text,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    create_correlation_id uuid NOT NULL,
    withdrawn_at timestamptz,
    withdrawn_by uuid,
    withdraw_reason text,
    withdraw_correlation_id uuid,
    PRIMARY KEY (tenant_id, window_id),
    FOREIGN KEY (tenant_id, location_id)
        REFERENCES plt01.locations (tenant_id, location_id),
    CONSTRAINT tsk_business_hours_kind CHECK (kind IN ('open', 'closed')),
    -- Exactly one of the two ways to say when. A row with both is two rules, and a row with
    -- neither binds nothing while reading as a calendar entry -- MOD-020's "a declared state
    -- nothing writes" in the shape of a row nothing reads.
    CONSTRAINT tsk_business_hours_one_anchor
        CHECK ((weekday IS NULL) <> (on_date IS NULL)),
    CONSTRAINT tsk_business_hours_weekday CHECK (weekday IS NULL OR weekday BETWEEN 0 AND 6),
    -- An `open` row states hours; a `closed` row states a day and must not pretend to.
    CONSTRAINT tsk_business_hours_open_has_hours CHECK (
        (kind = 'open' AND opens_at IS NOT NULL AND closes_at IS NOT NULL
         AND opens_at < closes_at)
        OR (kind = 'closed' AND opens_at IS NULL AND closes_at IS NULL)),
    -- A closed day is always dated: "closed every Tuesday" is the absence of a Tuesday `open`
    -- row, and allowing both ways to say it would let the two disagree.
    CONSTRAINT tsk_business_hours_closed_is_dated
        CHECK (kind = 'open' OR on_date IS NOT NULL),
    CONSTRAINT tsk_business_hours_note_stated
        CHECK (note IS NULL OR note ~ '[^[:space:]]'),
    -- **A withdrawal, not a delete**, which is MOD-019's `0017` lesson: the write is a routine
    -- permission the people who run the floor hold, and a routine permission whose every act
    -- is uncorrectable is MOD-013's rule from the other side. "Was this club marked closed on
    -- the fourteenth, and who said so" gets asked precisely when an SLA was missed.
    CONSTRAINT tsk_business_hours_withdrawal_attributed CHECK (
        (withdrawn_at IS NULL AND withdrawn_by IS NULL AND withdraw_reason IS NULL
         AND withdraw_correlation_id IS NULL)
        OR (withdrawn_at IS NOT NULL AND withdrawn_by IS NOT NULL
            AND coalesce(withdraw_reason, '') ~ '[^[:space:]]'
            AND withdraw_correlation_id IS NOT NULL))
);
ALTER TABLE plt01.tsk_business_hours ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.tsk_business_hours FORCE ROW LEVEL SECURITY;
CREATE POLICY tsk_business_hours_tenant ON plt01.tsk_business_hours
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
-- Partial on the live rows, because the clock arithmetic reads only those and a withdrawn
-- window is history.
CREATE INDEX tsk_business_hours_live
    ON plt01.tsk_business_hours (tenant_id, location_id, weekday, on_date)
    WHERE withdrawn_at IS NULL;

-- ------------------------------------------------------------------ the cases
--
-- AUT-02-R03: "Case container for multi-step problems with communication, timeline, documents
-- and resolution reason."
--
-- **The resolution reason is mandatory on resolution, by constraint.** A case closed with no
-- stated reason is the one thing a case is for: somebody asks, months later, what happened,
-- and "resolved" on its own answers nothing. This is the seventh table in this build whose
-- terminal state carries an attribution trio for that reason.
CREATE TABLE plt01.tsk_cases (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    case_id uuid NOT NULL DEFAULT gen_random_uuid(),
    case_number text NOT NULL,
    title text NOT NULL,
    queue_id uuid NOT NULL,
    -- **A problem that comes back is a new case citing the old one, not a reopened one.**
    -- The first draft of this file let a resolved case return to `open` and claimed in a
    -- comment that its first resolution's attribution stayed put -- which the attribution
    -- CHECK below makes false, because an `open` case must have those columns NULL, so
    -- reopening would erase exactly what the comment promised. Two encodings of one rule
    -- that disagree is MOD-020's waitlist finding, and the fix is to pick the one that can
    -- be true: the status is forward-only and a recurrence is a row.
    recurs_from_case_id uuid,
    -- The same closed vocabulary as a task's, because a case is about one of the same nine
    -- things. See `tsk_tasks` for why it is closed and why there is no foreign key.
    subject_kind text NOT NULL,
    subject_id uuid,
    priority text NOT NULL DEFAULT 'normal',
    status text NOT NULL DEFAULT 'open',
    opened_at timestamptz NOT NULL DEFAULT now(),
    opened_by uuid NOT NULL,
    open_correlation_id uuid NOT NULL,
    resolved_at timestamptz,
    resolved_by uuid,
    resolution_reason text,
    resolve_correlation_id uuid,
    PRIMARY KEY (tenant_id, case_id),
    FOREIGN KEY (tenant_id, queue_id) REFERENCES plt01.tsk_queues (tenant_id, queue_id),
    FOREIGN KEY (tenant_id, recurs_from_case_id)
        REFERENCES plt01.tsk_cases (tenant_id, case_id),
    CONSTRAINT tsk_cases_not_self CHECK (case_id <> recurs_from_case_id),
    CONSTRAINT tsk_cases_number_shape
        CHECK (case_number ~ '^[A-Z0-9][A-Z0-9-]{1,31}$'),
    CONSTRAINT tsk_cases_title_stated CHECK (title ~ '[^[:space:]]'),
    CONSTRAINT tsk_cases_subject_kind CHECK (subject_kind IN (
        'member', 'lead', 'tenant', 'invoice', 'incident', 'device', 'booking', 'asset',
        'workflow')),
    CONSTRAINT tsk_cases_subject_id_matches_kind
        CHECK ((subject_kind = 'tenant') = (subject_id IS NULL)),
    CONSTRAINT tsk_cases_priority
        CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    CONSTRAINT tsk_cases_status CHECK (status IN ('open', 'resolved', 'closed')),
    -- Resolved and closed both carry the reason: closing is how a resolved case is filed, and
    -- a case that reached `closed` without ever being resolved would be a case abandoned with
    -- no record, which is the state this constraint exists to make unwritable.
    CONSTRAINT tsk_cases_resolution_attributed CHECK (
        (status = 'open' AND resolved_at IS NULL AND resolved_by IS NULL
         AND resolution_reason IS NULL AND resolve_correlation_id IS NULL)
        OR (status IN ('resolved', 'closed') AND resolved_at IS NOT NULL
            AND resolved_by IS NOT NULL
            AND coalesce(resolution_reason, '') ~ '[^[:space:]]'
            AND resolve_correlation_id IS NOT NULL))
);
ALTER TABLE plt01.tsk_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.tsk_cases FORCE ROW LEVEL SECURITY;
CREATE POLICY tsk_cases_tenant ON plt01.tsk_cases
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE UNIQUE INDEX tsk_cases_one_number ON plt01.tsk_cases (tenant_id, case_number);
CREATE INDEX tsk_cases_by_queue ON plt01.tsk_cases (tenant_id, queue_id, status);
CREATE INDEX tsk_cases_by_subject ON plt01.tsk_cases (tenant_id, subject_kind, subject_id);

-- --------------------------------------------------------- the case timeline
--
-- R03's "communication, timeline, documents" in one insert-only ledger, because all three are
-- the same fact -- something happened on this case at a time, and somebody can name it.
--
-- **A document is a reference, not a file.** There is no object store in this build; the
-- isolation rules name one beside regions and keys. So `document_ref` has to *look* like a
-- locator, which is MOD-012's `vault_ref` and MOD-017's `evidence_ref` rule: a non-blank text
-- column beside a comment promising it holds no payload is a naming convention rather than a
-- control, and a reviewer disproved exactly that claim once already with a card number.
--
-- **No UPDATE grant at all.** An entry that could be edited is an entry nobody can rely on in
-- the dispute it exists for, so a correction is another entry -- MOD-014's note rule.
CREATE TABLE plt01.tsk_case_entries (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    entry_id uuid NOT NULL DEFAULT gen_random_uuid(),
    case_id uuid NOT NULL,
    entry_kind text NOT NULL,
    summary text NOT NULL,
    document_ref text,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    recorded_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, entry_id),
    FOREIGN KEY (tenant_id, case_id) REFERENCES plt01.tsk_cases (tenant_id, case_id),
    CONSTRAINT tsk_case_entries_kind CHECK (entry_kind IN (
        'note', 'communication', 'document', 'status_change', 'escalation')),
    CONSTRAINT tsk_case_entries_summary_stated CHECK (summary ~ '[^[:space:]]'),
    -- A locator or nothing. The shape is what makes the absence of a payload column a control
    -- rather than a promise.
    CONSTRAINT tsk_case_entries_document_is_a_locator CHECK (
        document_ref IS NULL
        OR document_ref ~ '^[a-z][a-z0-9+.-]*://[^[:space:]]+$'),
    CONSTRAINT tsk_case_entries_document_matches_kind
        CHECK (entry_kind <> 'document' OR document_ref IS NOT NULL),
    -- **Forward-only, and bounded against the server's clock.** MOD-011's unbounded
    -- `observed_at` let a routine caller hold an objective green through an outage still to
    -- come; a timeline entry dated next year is the same defect in a dispute record. Late is
    -- legitimate -- somebody writes up Friday's call on Monday -- so only the future is
    -- bounded, and the bound is one-sided because a lower bound fails every existing row the
    -- next time the constraint is validated.
    CONSTRAINT tsk_case_entries_not_in_the_future
        CHECK (occurred_at <= recorded_at + interval '5 minutes')
);
ALTER TABLE plt01.tsk_case_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.tsk_case_entries FORCE ROW LEVEL SECURITY;
CREATE POLICY tsk_case_entries_tenant ON plt01.tsk_case_entries
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE INDEX tsk_case_entries_by_case
    ON plt01.tsk_case_entries (tenant_id, case_id, occurred_at DESC, entry_id DESC);

-- ------------------------------------------------------------------ the tasks
--
-- AUT-02-R01 and R02. The subject vocabulary is the whole of R01 and the reason it is a CHECK
-- rather than free text is in the ADR: a caller able to name its own kind makes R07's
-- "how many tasks are about invoices" unanswerable, which is MOD-010's restricted-field
-- argument pointed at a discriminator.
--
-- **Six of the nine kinds resolve and three cannot.** A member is `ppl_persons`, an invoice
-- `fin_invoices`, a device `dev_devices`, a booking `bkg_bookings`, an incident
-- `sec_incidents`, and a tenant is the row's own `tenant_id`. A lead is MOD-027's, a workflow
-- MOD-055's, and nothing in this build owns an asset at all -- so there is no foreign key for
-- any of them, and the service resolves the six it can and records the other three as claims.
-- A composite key per kind would need nine nullable columns and eight of them NULL on every
-- row, which is the shape MOD-021's supersession findings are about.
--
-- **`assignee_person_id` is nullable and that is the queue's whole purpose**: an unassigned
-- task is work nobody has picked up, which is a state R07 has to be able to count, not an
-- incomplete row.
CREATE TABLE plt01.tsk_tasks (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    task_id uuid NOT NULL DEFAULT gen_random_uuid(),
    queue_id uuid NOT NULL,
    case_id uuid,
    title text NOT NULL,
    subject_kind text NOT NULL,
    subject_id uuid,
    assignee_person_id uuid,
    priority text NOT NULL DEFAULT 'normal',
    status text NOT NULL DEFAULT 'open',
    due_at timestamptz,
    evidence_ref text,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    create_correlation_id uuid NOT NULL,
    settled_at timestamptz,
    settled_by uuid,
    settle_reason text,
    settle_correlation_id uuid,
    PRIMARY KEY (tenant_id, task_id),
    FOREIGN KEY (tenant_id, queue_id) REFERENCES plt01.tsk_queues (tenant_id, queue_id),
    FOREIGN KEY (tenant_id, case_id) REFERENCES plt01.tsk_cases (tenant_id, case_id),
    FOREIGN KEY (tenant_id, assignee_person_id)
        REFERENCES plt01.ppl_persons (tenant_id, person_id),
    CONSTRAINT tsk_tasks_title_stated CHECK (title ~ '[^[:space:]]'),
    CONSTRAINT tsk_tasks_subject_kind CHECK (subject_kind IN (
        'member', 'lead', 'tenant', 'invoice', 'incident', 'device', 'booking', 'asset',
        'workflow')),
    CONSTRAINT tsk_tasks_subject_id_matches_kind
        CHECK ((subject_kind = 'tenant') = (subject_id IS NULL)),
    CONSTRAINT tsk_tasks_priority CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    CONSTRAINT tsk_tasks_status
        CHECK (status IN ('open', 'in_progress', 'blocked', 'done', 'cancelled')),
    -- **Bounded, because a date is caller input and `date` has an end.** MOD-019 shipped a
    -- thirty-day rule in year 9999 that walked off the end of `date` and answered 500 with
    -- the draft already committed. Ten years is longer than any task anybody means and short
    -- enough that the arithmetic in slice 3 cannot overflow.
    CONSTRAINT tsk_tasks_due_is_sane
        CHECK (due_at IS NULL OR due_at < created_at + interval '10 years'),
    CONSTRAINT tsk_tasks_evidence_is_a_locator CHECK (
        evidence_ref IS NULL OR evidence_ref ~ '^[a-z][a-z0-9+.-]*://[^[:space:]]+$'),
    -- Done and cancelled are both settlements and both carry a reason: "why was this not
    -- done" is the question R07's outcome reporting is for, and a cancelled task with no
    -- reason is a row that answers it with silence.
    CONSTRAINT tsk_tasks_settlement_attributed CHECK (
        (status IN ('open', 'in_progress', 'blocked') AND settled_at IS NULL
         AND settled_by IS NULL AND settle_reason IS NULL
         AND settle_correlation_id IS NULL)
        OR (status IN ('done', 'cancelled') AND settled_at IS NOT NULL
            AND settled_by IS NOT NULL
            AND coalesce(settle_reason, '') ~ '[^[:space:]]'
            AND settle_correlation_id IS NOT NULL))
);
ALTER TABLE plt01.tsk_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.tsk_tasks FORCE ROW LEVEL SECURITY;
CREATE POLICY tsk_tasks_tenant ON plt01.tsk_tasks
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
-- The three reads R07 needs, and the one a person needs: my work, the queue's backlog, and
-- everything about one subject.
CREATE INDEX tsk_tasks_by_assignee
    ON plt01.tsk_tasks (tenant_id, assignee_person_id, status, due_at);
CREATE INDEX tsk_tasks_by_queue ON plt01.tsk_tasks (tenant_id, queue_id, status, due_at);
CREATE INDEX tsk_tasks_by_subject ON plt01.tsk_tasks (tenant_id, subject_kind, subject_id);
CREATE INDEX tsk_tasks_by_case ON plt01.tsk_tasks (tenant_id, case_id)
    WHERE case_id IS NOT NULL;

-- --------------------------------------------------------- the checklist items
--
-- R02's checklist. One row per step, ordered, each tickable once with an actor -- because a
-- checklist whose ticks nobody owns is a checklist nobody can be asked about.
CREATE TABLE plt01.tsk_checklist_items (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    item_id uuid NOT NULL DEFAULT gen_random_uuid(),
    task_id uuid NOT NULL,
    ordinal integer NOT NULL,
    label text NOT NULL,
    completed_at timestamptz,
    completed_by uuid,
    complete_correlation_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    create_correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, item_id),
    FOREIGN KEY (tenant_id, task_id) REFERENCES plt01.tsk_tasks (tenant_id, task_id),
    CONSTRAINT tsk_checklist_items_label_stated CHECK (label ~ '[^[:space:]]'),
    CONSTRAINT tsk_checklist_items_ordinal CHECK (ordinal BETWEEN 1 AND 200),
    CONSTRAINT tsk_checklist_items_completion_attributed CHECK (
        (completed_at IS NULL AND completed_by IS NULL
         AND complete_correlation_id IS NULL)
        OR (completed_at IS NOT NULL AND completed_by IS NOT NULL
            AND complete_correlation_id IS NOT NULL))
);
ALTER TABLE plt01.tsk_checklist_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.tsk_checklist_items FORCE ROW LEVEL SECURITY;
CREATE POLICY tsk_checklist_items_tenant ON plt01.tsk_checklist_items
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE UNIQUE INDEX tsk_checklist_items_one_per_ordinal
    ON plt01.tsk_checklist_items (tenant_id, task_id, ordinal);

-- ----------------------------------------------------------- the dependencies
--
-- R02's "dependency": this task cannot start until that one is settled.
--
-- **A row rather than a column, because a task may wait on several.** A single
-- `blocked_by_task_id` would make the second dependency unrecordable, and the realistic case
-- -- a case whose four steps converge on one -- is exactly what R03 calls a multi-step
-- problem.
--
-- **Self-reference and cycles.** The constraint below refuses a task depending on itself,
-- which is the one case a CHECK can see. A longer cycle spans rows and is the service's
-- to refuse; it is named as a gap rather than wished away, because a recursive trigger on
-- every insert is a cost this module's write volume does not justify and a cycle leaves every
-- task in it `blocked`, which is visible rather than silent.
CREATE TABLE plt01.tsk_dependencies (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    dependency_id uuid NOT NULL DEFAULT gen_random_uuid(),
    task_id uuid NOT NULL,
    depends_on_task_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    create_correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, dependency_id),
    FOREIGN KEY (tenant_id, task_id) REFERENCES plt01.tsk_tasks (tenant_id, task_id),
    FOREIGN KEY (tenant_id, depends_on_task_id)
        REFERENCES plt01.tsk_tasks (tenant_id, task_id),
    CONSTRAINT tsk_dependencies_not_self CHECK (task_id <> depends_on_task_id)
);
ALTER TABLE plt01.tsk_dependencies ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.tsk_dependencies FORCE ROW LEVEL SECURITY;
CREATE POLICY tsk_dependencies_tenant ON plt01.tsk_dependencies
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE UNIQUE INDEX tsk_dependencies_one_edge
    ON plt01.tsk_dependencies (tenant_id, task_id, depends_on_task_id);
CREATE INDEX tsk_dependencies_by_blocker
    ON plt01.tsk_dependencies (tenant_id, depends_on_task_id);

-- ------------------------------------------------- a case belongs to its queue
--
-- **A task's case and the task's queue have to be the same tenant's business, and the
-- correspondence trigger is what says so.** The composite foreign keys already carry
-- `tenant_id`, so cross-tenant is impossible; what they cannot see is a task filed under one
-- queue while its case sits in another, which makes R07's workload report count the same work
-- in two places and makes "whose backlog is this" unanswerable.
--
-- `FOR UPDATE`, not `FOR SHARE` and not a bare read: MOD-019's capacity trigger took a share
-- lock and two ordinary transactions put four places in a two-place class, and MOD-021 shipped
-- three triggers that took no lock at all. A trigger that reads a parent row to decide whether
-- a child may be written has to lock it.
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
    IF case_queue IS NULL THEN
        RAISE EXCEPTION 'this task names a case that does not exist in this tenant';
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

CREATE TRIGGER tsk_tasks_match_their_case
    BEFORE INSERT OR UPDATE ON plt01.tsk_tasks
    FOR EACH ROW EXECUTE FUNCTION plt01.tsk_task_matches_its_case();

-- ------------------------------------------- a settlement is made once, and stays
--
-- A CHECK cannot see what a row used to be -- MOD-009's `sec_legal_holds` rule, and the
-- reason seven of MOD-018's lifecycle columns were rewritable while reading as immutable. The
-- attribution CHECK above says a settled task names who settled it; it says nothing about
-- somebody settling it again under a different name, or returning it to `open` so the
-- settlement reads as never having happened.
CREATE OR REPLACE FUNCTION plt01.tsk_settlement_is_final() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    IF OLD.settled_at IS NOT NULL THEN
        IF NEW.settled_at IS DISTINCT FROM OLD.settled_at
           OR NEW.settled_by IS DISTINCT FROM OLD.settled_by
           OR NEW.settle_reason IS DISTINCT FROM OLD.settle_reason THEN
            RAISE EXCEPTION
                'this task was already settled; who settled it, when and why do not move';
        END IF;
        IF NEW.status NOT IN ('done', 'cancelled') THEN
            RAISE EXCEPTION
                'a settled task does not reopen; raise a new one and say why in its title';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER tsk_tasks_settlement_final
    BEFORE UPDATE ON plt01.tsk_tasks
    FOR EACH ROW EXECUTE FUNCTION plt01.tsk_settlement_is_final();

-- ------------------------------------------- a resolution is made once, and stays
--
-- The same rule for a case, and `open -> resolved -> closed` is the only direction.
--
-- **A resolved case does not reopen, and `recurs_from_case_id` is why it does not have to.**
-- The alternative was tried in this file's first draft and could not be made coherent: the
-- attribution CHECK requires an `open` case to carry no resolution, so a reopen would erase
-- the very attribution the trigger was written to protect. A recurrence is therefore a new
-- case that cites the old, which is this build's answer everywhere else -- MOD-016's credit
-- note, MOD-019's new rule version, MOD-014's merge pointer.
CREATE OR REPLACE FUNCTION plt01.tsk_case_resolution_is_final() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    rank integer;
    was integer;
BEGIN
    rank := CASE NEW.status WHEN 'open' THEN 1 WHEN 'resolved' THEN 2 ELSE 3 END;
    was := CASE OLD.status WHEN 'open' THEN 1 WHEN 'resolved' THEN 2 ELSE 3 END;
    IF rank < was THEN
        RAISE EXCEPTION
            'a case moves open to resolved to closed and not back; a problem that returns '
            'is a new case citing this one';
    END IF;
    IF OLD.resolved_at IS NOT NULL THEN
        IF NEW.resolved_at IS DISTINCT FROM OLD.resolved_at
           OR NEW.resolved_by IS DISTINCT FROM OLD.resolved_by
           OR NEW.resolution_reason IS DISTINCT FROM OLD.resolution_reason THEN
            RAISE EXCEPTION
                'this case was already resolved; who resolved it, when and why do not move';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER tsk_cases_resolution_final
    BEFORE UPDATE ON plt01.tsk_cases
    FOR EACH ROW EXECUTE FUNCTION plt01.tsk_case_resolution_is_final();

-- ----------------------------------------------------------------- the grants
--
-- **Every "insert-only" and "immutable" claim above is a missing grant, and this is where it
-- lives.** No runtime role gets DELETE, TRUNCATE or REFERENCES on anything here: a settled
-- task and a resolved case are the record of what the people running a club actually did, and
-- R07's compliance reporting reads exactly that.
--
-- MOD-016's `cat_prices.effective_to` lesson is applied throughout: a column is in an UPDATE
-- grant only where a service function writes it. A granted column nothing writes is an
-- unattributed edit path, and that has now been found twice in this build.

GRANT SELECT, INSERT ON plt01.tsk_queues TO veyro_cp_app, veyro_cp_worker;
-- Not `queue_key`: the key is what R07 groups by and what a saved view names, so re-pointing
-- it silently re-labels every historical figure.
GRANT UPDATE (display_name, status, retired_at, retired_by, retire_reason,
              retire_correlation_id)
    ON plt01.tsk_queues TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.tsk_business_hours TO veyro_cp_app, veyro_cp_worker;
-- **The withdrawal only.** Correcting a window is withdrawing it and adding the corrected
-- one, which is the same edit with a history -- MOD-019's `0017` decision, taken for the same
-- reason: an unattributed retime of the values the table exists to state.
GRANT UPDATE (withdrawn_at, withdrawn_by, withdraw_reason, withdraw_correlation_id)
    ON plt01.tsk_business_hours TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.tsk_cases TO veyro_cp_app, veyro_cp_worker;
-- Not `case_number`, `subject_kind` or `subject_id`: the number is read out to people and the
-- subject is what the case is *about*, so moving either makes the history of this case the
-- history of something else.
-- Nor `recurs_from_case_id`: which case this one came back from is stated when it is opened,
-- and a pointer a later write can re-aim is MOD-021's supersession finding.
GRANT UPDATE (title, queue_id, priority, status, resolved_at, resolved_by,
              resolution_reason, resolve_correlation_id)
    ON plt01.tsk_cases TO veyro_cp_app, veyro_cp_worker;

-- **No UPDATE at all.** An entry is what happened.
GRANT SELECT, INSERT ON plt01.tsk_case_entries TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.tsk_tasks TO veyro_cp_app, veyro_cp_worker;
-- Not `subject_kind`, `subject_id` or `created_by`. Re-pointing a task's subject is the
-- `cat_prices` finding in this module's clothes: the row keeps its history and starts
-- describing different work.
GRANT UPDATE (queue_id, case_id, title, assignee_person_id, priority, status, due_at,
              evidence_ref, settled_at, settled_by, settle_reason, settle_correlation_id)
    ON plt01.tsk_tasks TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.tsk_checklist_items TO veyro_cp_app, veyro_cp_worker;
-- The tick and the label. Not `ordinal`: re-ordering a checklist after somebody ticked step
-- three means the tick is now on a different step.
GRANT UPDATE (label, completed_at, completed_by, complete_correlation_id)
    ON plt01.tsk_checklist_items TO veyro_cp_app, veyro_cp_worker;

-- **No UPDATE at all.** A dependency is added or it is not; changing which task blocks which
-- is two edges, and both of them should be visible.
GRANT SELECT, INSERT ON plt01.tsk_dependencies TO veyro_cp_app, veyro_cp_worker;

REVOKE ALL ON FUNCTION plt01.tsk_task_matches_its_case() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.tsk_settlement_is_final() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.tsk_case_resolution_is_final() FROM PUBLIC;
