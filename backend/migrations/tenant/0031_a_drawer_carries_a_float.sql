-- MOD-018 -- a till is handed over, not emptied, and the handover note goes with it.
--
-- FD-07's canvas is a handover. It draws the previous shift's own figure -- "Kareem left
-- **JOD 50.00** at 16:04" -- a float count, the sentence "If your count differs, say so now --
-- a discrepancy found at open belongs to the previous shift", and the note he left:
-- "Sweifieh reader still down -- admit manually and mention it." Underneath it: "The handover
-- note is part of the shift, not a WhatsApp message that leaves with the person who wrote it."
--
-- **That sentence only means something if the next person is counting the same money**, and
-- that is where this module and the design disagreed. `0012`'s model is a drawer that is
-- emptied: `open_cash_session` draws the float from the safe by journal, which is right for a
-- till that holds nothing and double-counts the money for a handover. Measured, before any of
-- this was written:
--
--     Kareem opens, 50.00 float from the safe     till 5000   safe -5000
--     a 20.00 sale                                till 7000
--     he counts 70.00 and closes, balanced        till 7000
--     he banks the 20.00 and leaves the float     till 5000   <- what the canvas draws
--     Layla opens and counts the 50.00 there      till 10000  safe -10000
--
-- The drawer account then says 100.00 while there are 50.00 in notes, so Layla's close posts a
-- 50.00 shortfall to suspense against her name, the safe is 50.00 short with nothing having
-- left it, and it compounds every shift. Reachable through `POST /ledger/cash-sessions` as it
-- stands, by a desk doing what the design says to do.
--
-- **So the float is posted when it is actually drawn, and not otherwise.** Which it is comes
-- from the drawer account's own balance at the moment of opening rather than from a flag the
-- caller sends -- deriving it is the only version of this that a caller cannot choose, and a
-- `handover: true` field would be the caller-supplied-control shape every review in this
-- build has found. An empty drawer has to be funded and the float comes from the safe, exactly
-- as before; a drawer that already holds money is a handover and nothing moves, because
-- nothing moved.
--
-- The three columns below are what makes that handover reconstructible, and they are written
-- by the INSERT alone -- no UPDATE grant, so a handover cannot be restated once it is
-- recorded.
ALTER TABLE plt01.led_cash_sessions
    -- What the ledger said was in the drawer when this session opened, against which
    -- `opening_float_minor` is the count the person made. **Stored rather than recomputed**:
    -- a posting can be back-dated, so re-deriving this balance later gives a different number
    -- from the one the person was shown, and the whole claim is "she counted 50.00 and the
    -- ledger said 50.00". The close keeps both its figures for the same reason.
    --
    -- NULL on every row written before this migration, and on nothing after it.
    ADD COLUMN opening_expected_minor bigint,
    -- "If your count differs, say so now." The reason belongs to the shift being handed over
    -- rather than to the one opening, which is what the case this writes says.
    ADD COLUMN opening_variance_reason text;

-- Bounded at the boundary, like every other money column here: `NumericValueOutOfRange` is a
-- `DataError` rather than the `CheckViolation` the handlers catch, so an unbounded bigint is a
-- 500 on input a caller sends.
ALTER TABLE plt01.led_cash_sessions
    ADD CONSTRAINT led_cash_sessions_opening_expected_bounded
        CHECK (opening_expected_minor IS NULL
               OR (opening_expected_minor >= -1000000000000
                   AND opening_expected_minor <= 1000000000000));

ALTER TABLE plt01.led_cash_sessions
    ADD CONSTRAINT led_cash_sessions_opening_reason_not_blank
        CHECK (opening_variance_reason IS NULL
               OR opening_variance_reason ~ '[^[:space:]]');

-- **A handover that does not balance states why.** The close's own control, at the other end
-- of the shift: a till 2.00 down every evening with nothing written against it is a pattern
-- only visible later if each count said something at the time, and the same holds for a till
-- 2.00 down every morning. `coalesce` is load-bearing -- `length(btrim(NULL)) > 0` is NULL and
-- a CHECK passes on NULL, so without it this admits the exact row it exists to refuse.
--
-- **Zero is what "not a handover" is**, and it is the same fact the service derives rather
-- than a second one beside it: a drawer the ledger says holds nothing has to be funded, so a
-- float of 50.00 against a balance of zero is money being put in rather than money missing.
-- A boolean saying which case this was would be two columns able to disagree about one shift.
ALTER TABLE plt01.led_cash_sessions
    ADD CONSTRAINT led_cash_sessions_opening_variance_explained
        CHECK (opening_expected_minor IS NULL
               OR opening_expected_minor = 0
               OR opening_float_minor = opening_expected_minor
               OR coalesce(opening_variance_reason, '') ~ '[^[:space:]]');

-- **There is deliberately no constraint refusing a reason on a count that agreed**, and the
-- first draft of this migration had one. `settlement.check_close` declines exactly that rule
-- at the other end of the shift, in as many words: "a clerk explaining a session that balanced
-- is harmless and the note is worth keeping, so there is deliberately no branch for it". Two
-- ends of one shift with opposite rules about the same field is one-module-two-definitions
-- created on purpose, so the open follows the close.

-- **The handover note: written by the person going off shift, read by the next one.** Free
-- text, and that is the point -- "Sweifieh reader still down", "two protein bar boxes arrived,
-- not yet counted in" is not a vocabulary anybody can close. It is subject-bearing in
-- practice, because the realistic note names a member, so it is declared in MOD-009's registry
-- rather than left for the name-matching sweep that will never find it.
ALTER TABLE plt01.led_cash_sessions
    ADD COLUMN handover_note text;

ALTER TABLE plt01.led_cash_sessions
    ADD CONSTRAINT led_cash_sessions_handover_note_not_blank
        CHECK (handover_note IS NULL OR handover_note ~ '[^[:space:]]');

-- A note handed over by a shift that has not ended is a note nobody can be given.
ALTER TABLE plt01.led_cash_sessions
    ADD CONSTRAINT led_cash_sessions_handover_note_needs_a_close
        CHECK (handover_note IS NULL OR closed_at IS NOT NULL);

-- The close writes it, so it joins the close's grant. **Immutable once written even so**:
-- `led_cash_close_is_final` refuses every UPDATE where the old status is not `open`, so the
-- one statement that may set this column is the close itself, and the note a reader is handed
-- is the note the previous person wrote. That trigger is why the privacy registry declares
-- this column unreachable while a grant names it.
GRANT UPDATE (handover_note) ON plt01.led_cash_sessions TO veyro_cp_app, veyro_cp_worker;

-- **A deposit says what it leaves behind, and the three figures add up.** This is the second
-- consequence of the model above rather than a separate change. `deposit_matches` compares the
-- bag against the sum of the sessions' closing counts, so once a float legitimately stays in
-- the drawer every honest banking is a mismatch and opens a `deposit_variance` case -- a case
-- per shift, which is how a reconciliation board stops being read.
--
-- Tolerating a smaller bag is the wrong fix: banking less than the till held and pocketing the
-- difference is exactly what that comparison exists to catch. So the remainder is **declared**
-- instead, and `declared + retained = counted` is the arithmetic. It defaults to zero, which is
-- today's behaviour unchanged, and what makes the claim checkable rather than polite is the
-- handover at the other end: the retained amount is what the next person counts, and a
-- discrepancy there is the canvas's own "belongs to the previous shift".
ALTER TABLE plt01.led_deposits
    ADD COLUMN retained_minor bigint NOT NULL DEFAULT 0;

ALTER TABLE plt01.led_deposits
    ADD CONSTRAINT led_deposits_retained_bounded
        CHECK (retained_minor >= 0 AND retained_minor <= 1000000000000);

COMMENT ON COLUMN plt01.led_deposits.retained_minor IS
    'What was deliberately left in the drawer rather than banked: the next shift''s float. '
    'Declared by whoever sealed the bag, and checked by the next open''s count.';

-- **A morning discrepancy is a different question from an evening one**, so it is a different
-- case kind. `cash_variance` is "the till was short when this shift counted it"; this one is
-- "the money left overnight is not the money that was left". A board that could not tell them
-- apart would attribute the first to whoever found it, which is the one attribution the
-- canvas's own sentence exists to get right.
ALTER TABLE plt01.led_reconciliation_cases
    DROP CONSTRAINT led_reconciliation_cases_kind;
ALTER TABLE plt01.led_reconciliation_cases
    ADD CONSTRAINT led_reconciliation_cases_kind CHECK (case_kind IN (
        'settlement_line', 'settlement_total', 'cash_variance', 'handover_variance',
        'deposit_variance', 'control_total'));
