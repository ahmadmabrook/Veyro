-- MOD-019 (OPS-01): a rota window can be withdrawn.
--
-- **Found by building ADM-SCH-04's write form**, which the canvas draws a button for and the
-- screen named as its next piece of work. `sch_availability_windows` carried
-- `GRANT SELECT, INSERT` and nothing else, so a window written once was permanent: there was
-- no way to take back a day off entered on the wrong date, correct a shift typed as 06:00
-- instead of 16:00, or end a working pattern. A rota could only ever grow.
--
-- That is invisible while the only writer is a seed script and decisive the moment a form
-- exists. `scheduling.availability.write` is `configuration` with no financial class --
-- routine, AAL 1, held by whoever runs the floor, and the catalogue argues for that
-- deliberately: "a rota is edited by the people who run the floor, and refusing them a
-- step-up every time somebody books a day off would make the rota wrong instead". A routine
-- permission whose every act is uncorrectable is MOD-013's rule from the other side -- "an
-- irreversible act must not be declarable on a routine permission" -- and MOD-016's "a guard
-- that admits a state nothing can leave is worse than no guard". So the button needs the
-- remedy before it needs the form.
--
-- **A withdrawal, not a delete, and no DELETE grant is added.** "Was this coach marked off on
-- the fourteenth, and who said so" has to stay answerable after somebody takes it back: a
-- deleted row answers nothing, and the question gets asked precisely when a member was turned
-- away. This is the module's own `sch_sessions` cancellation one table over -- a status, an
-- actor, a written reason, one-way by trigger -- and MOD-012's rule that widening or
-- narrowing what somebody may reach is a new record rather than an edit.

ALTER TABLE plt01.sch_availability_windows
    -- The three move together or not at all, which the constraint below enforces: a window
    -- withdrawn by nobody for no reason is the "evidence with nobody's name on it" shape this
    -- build has now hit in seven modules.
    ADD COLUMN withdrawn_at timestamptz,
    ADD COLUMN withdrawn_by uuid,
    ADD COLUMN withdrawn_reason text,
    ADD COLUMN withdraw_correlation_id uuid;

ALTER TABLE plt01.sch_availability_windows
    ADD CONSTRAINT sch_availability_windows_withdrawal_attributed
        CHECK (
            (withdrawn_at IS NULL) = (withdrawn_by IS NULL)
            AND (withdrawn_at IS NULL) = (withdrawn_reason IS NULL)
            AND (withdrawn_at IS NULL) = (withdraw_correlation_id IS NULL)),
    -- **The shape is `~ '[^[:space:]]'`**: the value contains at least one character that
    -- is not whitespace. The trimming form this repository banned across 118 constraints is
    -- true for a single tab and a single newline, because PostgreSQL's one-argument trim
    -- strips spaces only -- and `test_migration_shape` reads these files to keep it gone,
    -- which is why the banned pattern is described here rather than quoted.
    --
    -- No `coalesce` is needed on this one, and that is deliberate rather than an omission:
    -- the sibling above already requires the reason to be present exactly when the
    -- withdrawal is, so there is no row where this column is NULL and ought to be refused.
    -- Where a constraint does have to admit NULL, the wrapper is load-bearing -- a CHECK
    -- passes on NULL, which is MOD-009's `sec_legal_holds` finding.
    ADD CONSTRAINT sch_availability_windows_withdrawal_reasoned
        CHECK (withdrawn_reason IS NULL OR withdrawn_reason ~ '[^[:space:]]');

-- **Live windows, which is what every read wants.** A partial index rather than a filter on
-- the existing one: a withdrawn window is read only when somebody asks what the rota used to
-- say, and that is not the hot path.
CREATE INDEX sch_availability_windows_live
    ON plt01.sch_availability_windows (tenant_id, resource_id, window_kind)
    WHERE withdrawn_at IS NULL;

-- **A withdrawal is final, and a CHECK cannot see what the row used to be.** MOD-009's
-- `sec_legal_holds` rule, which MOD-018 and MOD-021 have each paid for since: the attribution
-- CHECK above says the four columns agree with each other and says nothing about whether they
-- were replaced, so without this a window could be withdrawn, un-withdrawn and withdrawn
-- again under a different name with the row afterwards reading as a single clean act. Nothing
-- else on this row may move either -- the times, the kind, the day and the reason are what the
-- rota said, and a rota that can be edited in place is a rota nobody can read back.
CREATE OR REPLACE FUNCTION plt01.sch_availability_window_withdrawal_is_final()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF OLD.withdrawn_at IS NOT NULL THEN
        RAISE EXCEPTION
            'this availability window was already withdrawn; add a new one rather than '
            'rewriting the withdrawal';
    END IF;
    IF NEW.window_kind IS DISTINCT FROM OLD.window_kind
        OR NEW.resource_id IS DISTINCT FROM OLD.resource_id
        OR NEW.timezone IS DISTINCT FROM OLD.timezone
        OR NEW.starts_at IS DISTINCT FROM OLD.starts_at
        OR NEW.ends_at IS DISTINCT FROM OLD.ends_at
        OR NEW.weekday IS DISTINCT FROM OLD.weekday
        OR NEW.on_date IS DISTINCT FROM OLD.on_date
        OR NEW.reason IS DISTINCT FROM OLD.reason
        OR NEW.created_by IS DISTINCT FROM OLD.created_by THEN
        RAISE EXCEPTION
            'an availability window is withdrawn, never edited; what it said is what the '
            'rota said';
    END IF;
    IF NEW.withdrawn_at IS NULL THEN
        RAISE EXCEPTION
            'the only update an availability window admits is its withdrawal';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER sch_availability_windows_one_way
    BEFORE UPDATE ON plt01.sch_availability_windows
    FOR EACH ROW EXECUTE FUNCTION plt01.sch_availability_window_withdrawal_is_final();

-- **And the grant that let a window be rewritten in place goes.** `0013` granted
-- `UPDATE (starts_at, ends_at, reason)` to both runtime roles with the comment "a rota is
-- edited, so a window's times move" -- and **nothing in this build ever wrote them**. That is
-- MOD-016's `cat_prices.effective_to` exactly: a grant no service uses, over the values that
-- decide the thing the table exists to say, with no attribution column anywhere to record
-- that they moved. A shift silently retimed from 06:00 to 16:00 would leave a rota reading as
-- though it had always said so, and the member turned away at the door has no way to find out
-- otherwise. Withdrawing the window and adding the corrected one is the same edit with a
-- history, which is what the trigger above means by "what it said is what the rota said".
REVOKE UPDATE (starts_at, ends_at, reason)
    ON plt01.sch_availability_windows FROM veyro_cp_app, veyro_cp_worker;

-- **Four columns, and only to the role that serves a request.** The worker drives no job here
-- -- withdrawing somebody's day off is a judgement, not a sweep -- and a role that holds a
-- grant it never uses is a seat at a table it has no business at, which is the regression
-- check 44 exists for. No DELETE for anybody, as before.
GRANT UPDATE (withdrawn_at, withdrawn_by, withdrawn_reason, withdraw_correlation_id)
    ON plt01.sch_availability_windows TO veyro_cp_app;
