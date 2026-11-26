-- MOD-019 / ADM-SCH-05 — a personal-training session: one coach, one member, one credit.
-- ADR-0019.
--
-- **A PT session is a `sch_sessions` row, and the reasoning is not aesthetic.** The design
-- draws PT on the coach's own week grid (ADM-SCH-04), so it has to hold the coach's time --
-- and a resource is held through `sch_session_resources`, which references this table. More
-- decisively, `_held_over` is the reader every conflict decision is made from and it reads
-- `sch_session_resources` joined to `sch_sessions`: a PT booking in a table beside this one
-- would be **invisible to the class generator**, so a coach teaching at 17:30 would be
-- assigned a class at 17:30 with nothing objecting. Extending that reader to a second source
-- is two definitions of "is this coach free", which `conflicts.py` exists to have one of.
--
-- **So what changes is what a session may cite.** `template_id`, `rule_id` and `policy_id`
-- were NOT NULL with foreign keys, and a PT booking comes from none of them: a person picked
-- an instant. A class names all three; a personal session names none, and says which it is.
--
-- **The default is what this build already did**, which is load-bearing rather than cautious:
-- every session already generated keeps its three references and no reader of an existing row
-- changes verdict. ADR-0011's reasoning about the billing anchor, applied to a discriminator.
--
-- **And the defect this slice is most likely to ship is in the application, not here.** Six
-- places write `JOIN plt01.sch_templates t ON t.template_id = s.template_id` to get a label.
-- An inner join on a nullable column *silently drops the row* -- so a PT session would vanish
-- from the schedule board, from the coach's week and from the conflict reader, and the last
-- of those means a double-booked coach with nothing objecting. All six are LEFT joins now and
-- the HTTP and browser layers each assert a PT session is present where a class is.

-- ---------------------------------------------------------------- the kind

ALTER TABLE plt01.sch_sessions
    ADD COLUMN session_kind text NOT NULL DEFAULT 'class';

COMMENT ON COLUMN plt01.sch_sessions.session_kind IS
    'A class, which came from a template and its rule, or a personal session, which came '
    'from somebody picking an instant. ADM-SCH-04 names the absence of this: "a class and a '
    'personal-training session are one state because nothing records a session kind".';

ALTER TABLE plt01.sch_sessions
    ADD CONSTRAINT sch_sessions_kind
        CHECK (session_kind IN ('class', 'personal'));

-- ---------------------------------------------------------------- what each kind cites

ALTER TABLE plt01.sch_sessions
    ALTER COLUMN template_id DROP NOT NULL,
    ALTER COLUMN rule_id DROP NOT NULL,
    ALTER COLUMN policy_id DROP NOT NULL;

-- **A biconditional, so neither half can drift.** A class with no rule could not say what it
-- came from, which is paragraph 4149's whole point; a personal session citing a rule would be
-- claiming an origin it does not have, and `(rule_id, starts_at)` -- the generation
-- idempotency -- would then make two coaches' PT at one instant collide.
ALTER TABLE plt01.sch_sessions
    ADD CONSTRAINT sch_sessions_class_came_from_a_template
        CHECK ((session_kind = 'class')
               = (template_id IS NOT NULL AND rule_id IS NOT NULL
                  AND policy_id IS NOT NULL));

-- **A personal session holds one person**, which is what makes it personal rather than a
-- class of one: the capacity is the session's own snapshot either way, and a PT row declaring
-- twelve places would be a class nobody could book through this command.
ALTER TABLE plt01.sch_sessions
    ADD CONSTRAINT sch_sessions_personal_holds_one
        CHECK (session_kind <> 'personal'
               OR (capacity = 1 AND overbook_places = 0));

CREATE INDEX sch_sessions_personal_by_start
    ON plt01.sch_sessions (tenant_id, starts_at)
    WHERE session_kind = 'personal';
COMMENT ON INDEX plt01.sch_sessions_personal_by_start IS
    'ADM-SCH-05 asks what a coach already has at an instant, and the calendar reads both '
    'kinds over a window. The class path has `(rule_id, starts_at)` for the same job and a '
    'personal session cites no rule.';

-- ---------------------------------------------------------------- the grants
--
-- **No statement, and that is the decision.** `sch_sessions` carries a table-level
-- `GRANT SELECT, INSERT`, which covers a column added later, and its UPDATE is column-scoped
-- over the lifecycle columns only -- a column-scoped grant does not extend to a new column,
-- so `session_kind` is insert-only without a statement. Which is right: what a session *is*
-- does not change, and a class that became a personal session would be a row whose own
-- history is unreadable.
--
-- The three columns that became nullable keep the grants they had, which for `template_id`,
-- `rule_id` and `policy_id` is no UPDATE at all: a session cites the rule it came from and
-- that does not move. `0013`'s comment says why, and dropping NOT NULL does not weaken it.
