-- MOD-018, COM-04: the immutable financial source of truth for money, credits, liabilities and
-- provider settlement. Fifteen tables in `plt01` under the forced row-level security every
-- `plt01` table obeys.
--
-- **This is the ledger, and it lives beside the business tables rather than in a schema of its
-- own.** Paragraph 1663 says "Product PostgreSQL ledger schema", and paragraph 926 says the V1
-- product database uses "a small number of schemas (app, iam, ledger, audit) rather than one
-- schema per domain" with "module-prefixed table names" making ownership explicit. The second
-- is what this build implements, and the reason is decisive rather than stylistic: **a posting
-- must commit in the transaction that caused it.** A payment recorded in `fin_payments` without
-- its journal, or a journal without its payment, is precisely the state MOD-010's
-- `append_event` argument forbids -- and a separate schema under a separate role cannot share a
-- transaction with `plt01`, because the roles here hold nothing in each other's schemas and are
-- members of no role. So the privilege boundary that makes the ledger immutable is the *grant*
-- rather than the role: no runtime role holds UPDATE or DELETE on a posted journal or posting,
-- and check 80 proves that per column and per role rather than trusting this comment.
--
-- A later deployment that wants the physical separation has to solve the atomicity first. The
-- honest note is that it is unsolved, not that the schema name was an oversight.
--
-- Six decisions are specific to this module.
--
--   * **Signs, not sides.** A posting carries one signed `amount_minor`: positive is a debit,
--     negative is a credit. Two columns -- a side and a magnitude -- can disagree with each
--     other, and a row that says `credit 500` in a `debit_minor` column is a defect no
--     constraint can see. With one column, "this journal balances" is exactly
--     `sum(amount_minor) = 0`, which is a thing the database can check.
--
--   * **The balance check is a DEFERRABLE constraint trigger**, the first in this build. A
--     journal balances across rows, so no CHECK can express it and no BEFORE trigger can see
--     the rows that have not been inserted yet. `SET CONSTRAINTS`-style deferral to commit is
--     the only mechanism that makes "every journal in this database balances" true of rows
--     written by anything -- including a later service, a repair script or a migration. The
--     decision function in `app/ledger/accounts.py` refuses earlier and more readably; this is
--     the half that still holds when the service is wrong.
--
--   * **A closed period refuses postings, by trigger.** COM-04-R06. The period's status is a
--     fact about another row, so again no CHECK reaches it. Once finance has told an authority
--     what a month was, a posting dated into that month makes the statement and the filing
--     disagree with nothing to say which is current -- so the correction is a posting in the
--     open period that references the original, which is the answer this build gives every
--     time an insert-only table is asked to change its mind.
--
--   * **No balance is stored anywhere.** COM-04-R07: "statements and balances reconstructed
--     from entries rather than mutable totals." There is no `balance_minor` on an account, a
--     wallet or a schedule, and there is no column one could be cached in -- which is a control
--     that is an *absence*, so check 80 pins every column list in full. A cached total is a
--     second authority that can disagree with the first, and the disagreement surfaces as a
--     member who cannot spend value their statement says they hold.
--
--   * **Promotional, refundable and cash-equivalent wallet value stay distinct.** Paragraph
--     1686, a Critical Control. A member holding 50.00 they paid in and 10.00 the tenant gave
--     away holds two different things: the first is money the tenant owes and must refund on
--     request, the second is a marketing expense already incurred. One balance makes them
--     indistinguishable the moment either is spent, and the tenant then either refuses a refund
--     it owes or pays out money it never took. Four `value_kind` values, two liability
--     accounts, and `app/ledger/wallet.py` decides the spend order.
--
--   * **Service credits are MOD-017's, not this module's.** COM-04-R03 asks for "separate
--     non-monetary service credits such as PT sessions, classes, guest passes and
--     assessments", and `mem_entitlement_grants` with its insert-only movement ledger is
--     exactly that -- built, gated, reviewed and already the authority on whether a member may
--     train. A second store here would be the shadow-database mistake MOD-009 argues against,
--     with the two copies able to disagree and only one of them reachable by an erasure. What
--     this module adds is the *money* side those credits always had and never posted: a pack
--     sold creates unearned revenue, and a session consumed earns it.

-- ---------------------------------------------------------------- the chart of accounts
--
-- **The kinds are in code (`app/ledger/accounts.py`) and the accounts are rows.** Same
-- division as MOD-008's permissions, MOD-010's event types and MOD-011's metrics, for the same
-- reason: a kind is a fact about what this software posts, so two tenants disagreeing about
-- whether `unearned_revenue` is a liability would be unresolvable. The accounts themselves are
-- per tenant, per currency and sometimes per location -- one cash account per till is the
-- ordinary arrangement -- so those are rows.
CREATE TABLE plt01.led_accounts (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    account_id uuid NOT NULL DEFAULT gen_random_uuid(),
    -- The tenant's own code for it, which is what appears on an export to an accounting
    -- system. Shaped rather than free text, because an export maps on it.
    account_code text NOT NULL,
    -- One of `app.ledger.accounts.KINDS`. A CHECK constrains the shape and the catalogue is
    -- the authority on the set -- the same arrangement as `iam.role_permissions`, and for the
    -- same reason: a per-tenant table of kinds would let two tenants disagree with the code.
    account_kind text NOT NULL,
    display_name text NOT NULL,
    -- **One currency per account.** An account holding two currencies has no balance: adding
    -- 100 JOD to 100 USD is the arithmetic MOD-015's money discipline forbids, and the FX
    -- postings exist precisely so a movement between currencies is two accounts and a
    -- difference rather than one account and a guess.
    currency char(3) NOT NULL,
    brand_id uuid,
    location_id uuid,
    legal_entity_id uuid,
    status text NOT NULL DEFAULT 'active',
    retired_at timestamptz,
    retired_by uuid,
    retire_correlation_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, account_id),
    UNIQUE (tenant_id, account_code),
    FOREIGN KEY (tenant_id, brand_id) REFERENCES plt01.brands (tenant_id, brand_id),
    FOREIGN KEY (tenant_id, location_id)
        REFERENCES plt01.locations (tenant_id, location_id),
    FOREIGN KEY (tenant_id, legal_entity_id)
        REFERENCES plt01.legal_entities (tenant_id, legal_entity_id),
    CONSTRAINT led_accounts_code_shape
        CHECK (account_code ~ '^[A-Z0-9][A-Z0-9._-]{1,31}$'),
    CONSTRAINT led_accounts_kind_shape CHECK (account_kind ~ '^[a-z][a-z0-9_]{1,31}$'),
    CONSTRAINT led_accounts_name_not_blank CHECK (display_name ~ '[^[:space:]]'),
    CONSTRAINT led_accounts_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT led_accounts_status CHECK (status IN ('active', 'retired')),
    -- A retirement names who and when and under which correlation, or none of the three.
    CONSTRAINT led_accounts_retirement_attributed CHECK (
        (retired_at IS NULL AND retired_by IS NULL AND retire_correlation_id IS NULL)
        OR (retired_at IS NOT NULL AND retired_by IS NOT NULL
            AND retire_correlation_id IS NOT NULL)),
    CONSTRAINT led_accounts_retired_is_retired
        CHECK ((status = 'retired') = (retired_at IS NOT NULL)),
    -- A location-scoped account names its brand too, so "every account at this brand" is one
    -- predicate rather than a join nobody remembers to write.
    CONSTRAINT led_accounts_location_names_a_brand
        CHECK (location_id IS NULL OR brand_id IS NOT NULL)
);
CREATE INDEX led_accounts_by_kind
    ON plt01.led_accounts (tenant_id, account_kind, currency);
ALTER TABLE plt01.led_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.led_accounts FORCE ROW LEVEL SECURITY;
CREATE POLICY led_accounts_tenant ON plt01.led_accounts
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- financial periods
--
-- COM-04-R06's "financial periods, lock controls, correction entries". Monthly, because
-- paragraph 1663 names monthly partitions and a period shorter than the shortest filing cycle
-- is a close nobody asked for. The key is derived from the date by
-- `app.ledger.periods.period_key_for`, so two callers cannot disagree about which period a
-- date falls in.
CREATE TABLE plt01.led_periods (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    period_id uuid NOT NULL DEFAULT gen_random_uuid(),
    legal_entity_id uuid NOT NULL,
    -- `2026-11`. Derived, never chosen.
    period_key text NOT NULL,
    starts_on date NOT NULL,
    ends_on date NOT NULL,
    status text NOT NULL DEFAULT 'open',
    -- Every move carries its actor, because closing a period is the act that makes a figure
    -- final and reopening one is the act that un-makes it.
    closed_at timestamptz,
    closed_by uuid,
    close_correlation_id uuid,
    reopened_at timestamptz,
    reopened_by uuid,
    reopen_reason text,
    reopen_correlation_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, period_id),
    -- One period per entity per month. Two would make "what was November" answerable twice.
    UNIQUE (tenant_id, legal_entity_id, period_key),
    FOREIGN KEY (tenant_id, legal_entity_id)
        REFERENCES plt01.legal_entities (tenant_id, legal_entity_id),
    CONSTRAINT led_periods_key_shape CHECK (period_key ~ '^[0-9]{4}-[0-9]{2}$'),
    CONSTRAINT led_periods_dates_ordered CHECK (ends_on >= starts_on),
    CONSTRAINT led_periods_status
        CHECK (status IN ('open', 'closing', 'closed', 'reopened')),
    CONSTRAINT led_periods_close_attributed CHECK (
        (closed_at IS NULL AND closed_by IS NULL AND close_correlation_id IS NULL)
        OR (closed_at IS NOT NULL AND closed_by IS NOT NULL
            AND close_correlation_id IS NOT NULL)),
    -- **One direction only.** A period that was closed, reopened and is now closing again
    -- keeps its close timestamp -- the reopening record is what says it was reopened in
    -- between -- so "a close time means the status is closed" is false on the one edge out of
    -- `reopened`, and the biconditional made that edge unsatisfiable: the route answered 500
    -- and a reopened period could never be re-closed. What still has to hold is that a closed
    -- or reopened period has a close time, and the trigger below is what stops one
    -- disappearing.
    CONSTRAINT led_periods_closed_is_closed
        CHECK (status NOT IN ('closed', 'reopened') OR closed_at IS NOT NULL),
    -- **A reopening states why.** It is the one act that lets a filed figure change, so a
    -- reopened period with no reason is the row an auditor asks about and nobody can answer.
    CONSTRAINT led_periods_reopen_attributed CHECK (
        (reopened_at IS NULL AND reopened_by IS NULL AND reopen_reason IS NULL
         AND reopen_correlation_id IS NULL)
        OR (reopened_at IS NOT NULL AND reopened_by IS NOT NULL
            AND coalesce(reopen_reason, '') ~ '[^[:space:]]'
            AND reopen_correlation_id IS NOT NULL)),
    -- One direction, for `closed_is_closed`'s reason: a period that was reopened and is now
    -- closing again keeps the record of the reopening, which is the whole point of having
    -- one, so the biconditional made the only edge out of `reopened` unsatisfiable. That a
    -- reopening never *disappears* is the one-way trigger's job.
    CONSTRAINT led_periods_reopened_is_reopened
        CHECK (status <> 'reopened' OR reopened_at IS NOT NULL)
);
CREATE INDEX led_periods_by_date
    ON plt01.led_periods (tenant_id, legal_entity_id, starts_on);
ALTER TABLE plt01.led_periods ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.led_periods FORCE ROW LEVEL SECURITY;
CREATE POLICY led_periods_tenant ON plt01.led_periods
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- journals and postings
--
-- **The journal is the header and the postings are the money.** A journal says why it exists,
-- what caused it and which period it belongs to; its postings say which accounts moved and by
-- how much. The pair is insert-only in full: there is no UPDATE grant on either table for any
-- runtime role, which is paragraph 1685's Critical Control -- "posted financial entries are
-- never edited or deleted; corrections use compensating entries" -- as a privilege rather than
-- as a sentence.
--
-- `source_kind` and `source_ref` are what makes a posting explicable a year later. Paragraph
-- 1688's required outcome is "finance can explain every balance", and a balance is explicable
-- only if each movement in it points at the thing that caused it.
CREATE TABLE plt01.led_journals (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    journal_id uuid NOT NULL DEFAULT gen_random_uuid(),
    legal_entity_id uuid NOT NULL,
    period_id uuid NOT NULL,
    -- Why this journal exists, from `app.ledger.periods.PURPOSES`. A closing period admits
    -- some purposes and not others, which is the whole point of the `closing` state.
    purpose text NOT NULL,
    -- The accounting date, which is not the moment it was written: a correction posted in
    -- December for a November discovery is dated in December, because that is the period it
    -- changes. `occurred_at` is when the row appeared.
    posted_on date NOT NULL,
    currency char(3) NOT NULL,
    -- The sum of the debits. Stored so a control-total reconciliation can compare a figure
    -- against the postings without re-summing them -- and so a journal whose postings were
    -- tampered with disagrees with its own header. Both halves are insert-only, which is what
    -- makes that disagreement evidence rather than a stale cache.
    control_total_minor bigint NOT NULL,
    -- What caused it. `invoice`, `payment`, `refund`, `wallet`, `recognition`, `settlement`,
    -- `cash_session`, `correction` or `manual`; the reference is that row's id or handle.
    source_kind text NOT NULL,
    source_ref text NOT NULL,
    -- **A correction names what it corrects.** Paragraph 1685: corrections use compensating
    -- entries, and a compensating entry nobody can tie to the original is a second mystery
    -- rather than an explanation.
    corrects_journal_id uuid,
    correction_reason text,
    description text NOT NULL,
    idempotency_key text NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    posted_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, journal_id),
    -- **Per source kind, not per tenant.** The commands compose their own keys into this
    -- column -- `wallet-credit-<key>`, `deposit-<id>`, `cash-variance-<id>` -- and
    -- `POST /ledger/journals` writes to it too. With one namespace a caller posted a decoy
    -- journal keyed `wallet-credit-TOPUP-9`, then credited a wallet with key `TOPUP-9` and was
    -- handed the decoy back as a repeat: 1000.00 of refundable member value with no liability
    -- in the ledger, and a trial balance that cannot see it because the decoy balanced. The
    -- route is restricted to `manual`, so the namespaces are disjoint and the caller cannot
    -- write into a command's.
    UNIQUE (tenant_id, source_kind, idempotency_key),
    FOREIGN KEY (tenant_id, legal_entity_id)
        REFERENCES plt01.legal_entities (tenant_id, legal_entity_id),
    FOREIGN KEY (tenant_id, period_id) REFERENCES plt01.led_periods (tenant_id, period_id),
    FOREIGN KEY (tenant_id, corrects_journal_id)
        REFERENCES plt01.led_journals (tenant_id, journal_id),
    CONSTRAINT led_journals_purpose CHECK (purpose IN (
        'trade', 'correction', 'recognition', 'settlement', 'close')),
    CONSTRAINT led_journals_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT led_journals_control_total_positive
        CHECK (control_total_minor > 0 AND control_total_minor <= 1000000000000),
    CONSTRAINT led_journals_source_kind CHECK (source_kind IN (
        'invoice', 'payment', 'refund', 'credit_note', 'wallet', 'recognition',
        'settlement', 'cash_session', 'deposit', 'correction', 'manual')),
    CONSTRAINT led_journals_source_ref_not_blank CHECK (source_ref ~ '[^[:space:]]'),
    CONSTRAINT led_journals_description_not_blank CHECK (description ~ '[^[:space:]]'),
    CONSTRAINT led_journals_key_not_blank CHECK (idempotency_key ~ '[^[:space:]]'),
    CONSTRAINT led_journals_not_self
        CHECK (corrects_journal_id IS NULL OR corrects_journal_id <> journal_id),
    -- **A correction is the only purpose that corrects something, and it always does.** A
    -- `trade` journal pointing at another journal is somebody using the field for a note; a
    -- correction pointing at nothing is the compensating entry nobody can tie to an original.
    CONSTRAINT led_journals_correction_corrects
        CHECK ((purpose = 'correction') = (corrects_journal_id IS NOT NULL)),
    CONSTRAINT led_journals_correction_reasoned
        CHECK ((purpose = 'correction')
               = (coalesce(correction_reason, '') ~ '[^[:space:]]'))
);
CREATE INDEX led_journals_by_period
    ON plt01.led_journals (tenant_id, period_id, posted_on);
CREATE INDEX led_journals_by_source
    ON plt01.led_journals (tenant_id, source_kind, source_ref);
ALTER TABLE plt01.led_journals ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.led_journals FORCE ROW LEVEL SECURITY;
CREATE POLICY led_journals_tenant ON plt01.led_journals
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **One signed amount per posting**, because two columns can disagree with each other. Positive
-- is a debit and negative is a credit, `app.ledger.accounts.side_of` is the one place that
-- names them, and "this journal balances" is then exactly `sum(amount_minor) = 0` -- which is
-- something the database can check and a `debit_minor`/`credit_minor` pair is not.
CREATE TABLE plt01.led_postings (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    posting_id uuid NOT NULL DEFAULT gen_random_uuid(),
    journal_id uuid NOT NULL,
    account_id uuid NOT NULL,
    -- Positive debits, negative credits. Never zero: a posting of nothing is not a posting.
    amount_minor bigint NOT NULL,
    currency char(3) NOT NULL,
    -- Who the movement is about, where there is a person. Nullable, because most postings are
    -- about an account rather than a member -- a provider fee is nobody's.
    subject_person_id uuid,
    -- Free text for the statement line. The realistic content is "Monthly membership,
    -- November", and it is declared in `SUBJECT_COLUMNS` because free text holds anything.
    memo text,
    line_number integer NOT NULL,
    PRIMARY KEY (tenant_id, posting_id),
    UNIQUE (tenant_id, journal_id, line_number),
    FOREIGN KEY (tenant_id, journal_id)
        REFERENCES plt01.led_journals (tenant_id, journal_id),
    FOREIGN KEY (tenant_id, account_id)
        REFERENCES plt01.led_accounts (tenant_id, account_id),
    FOREIGN KEY (tenant_id, subject_person_id)
        REFERENCES plt01.ppl_persons (tenant_id, person_id),
    CONSTRAINT led_postings_amount_not_zero CHECK (amount_minor <> 0),
    CONSTRAINT led_postings_amount_sane
        CHECK (amount_minor >= -1000000000000 AND amount_minor <= 1000000000000),
    CONSTRAINT led_postings_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT led_postings_memo_not_blank CHECK (memo IS NULL OR memo ~ '[^[:space:]]'),
    CONSTRAINT led_postings_line_positive CHECK (line_number >= 1)
);
CREATE INDEX led_postings_by_account
    ON plt01.led_postings (tenant_id, account_id, journal_id);
CREATE INDEX led_postings_by_journal ON plt01.led_postings (tenant_id, journal_id);
CREATE INDEX led_postings_by_subject
    ON plt01.led_postings (tenant_id, subject_person_id)
    WHERE subject_person_id IS NOT NULL;
ALTER TABLE plt01.led_postings ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.led_postings FORCE ROW LEVEL SECURITY;
CREATE POLICY led_postings_tenant ON plt01.led_postings
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **The balanced-journal constraint, deferred to commit.** Paragraph 1694 names it and this is
-- the only mechanism that can express it: a journal balances *across rows*, so no CHECK can see
-- it and no immediate trigger can see the rows that have not been inserted yet. Deferring to
-- the end of the transaction means the postings go in one at a time and the sum is checked once
-- they are all there.
--
-- Five things it also checks, each because the alternative is a silently wrong statement:
-- every posting in a journal is in the journal's currency (a mixed journal has no meaning and
-- no balance); every posting is in its *account's* currency as well, because the balance this
-- module offers is `sum(amount_minor)` over an account and a sum across currencies is the
-- arithmetic MOD-015's money discipline forbids; no account appears twice in one journal,
-- because +N and -N on one account sums to zero and moves nothing while satisfying every other
-- rule here; the journal's stored control total equals its debits (so a header that disagrees
-- with its body is refused rather than becoming evidence); and the line numbers run from one
-- with no gaps (a missing line is the shape a truncated import takes).
--
-- **There is no `lines < 2` branch.** A journal with one posting cannot balance, because
-- `led_postings_amount_not_zero` refuses a posting of nothing; the branch that used to be here
-- was subsumed by that CHECK and had no isolating case, which a reviewer proved by disabling
-- it with the suite still green. The obligation that *is* needed -- a journal has at least one
-- posting -- is on `led_journals` below, because a journal with no postings fires a trigger on
-- `led_postings` zero times.
--
-- `AFTER INSERT ... FOR EACH ROW` rather than per statement, because the postings may arrive in
-- separate statements; deferral collapses the repeated work to one check per journal per
-- transaction in the ordinary case, and correctness does not depend on how they were batched.
CREATE OR REPLACE FUNCTION plt01.led_journal_balances()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    total bigint;
    debits bigint;
    lines integer;
    top integer;
    claimed bigint;
    journal_currency char(3);
    wrong_currency integer;
    wrong_account integer;
    repeated_account integer;
BEGIN
    SELECT coalesce(sum(amount_minor), 0), coalesce(sum(amount_minor)
               FILTER (WHERE amount_minor > 0), 0), count(*), coalesce(max(line_number), 0)
      INTO total, debits, lines, top
      FROM plt01.led_postings
     WHERE tenant_id = NEW.tenant_id AND journal_id = NEW.journal_id;
    IF total <> 0 THEN
        RAISE EXCEPTION
            'journal % does not balance: its postings sum to % rather than zero',
            NEW.journal_id, total;
    END IF;
    IF top <> lines THEN
        RAISE EXCEPTION
            'journal % has % postings numbered up to %; the numbers run from one with no gaps',
            NEW.journal_id, lines, top;
    END IF;
    SELECT control_total_minor, currency INTO claimed, journal_currency
      FROM plt01.led_journals
     WHERE tenant_id = NEW.tenant_id AND journal_id = NEW.journal_id;
    IF claimed IS DISTINCT FROM debits THEN
        RAISE EXCEPTION
            'journal % claims a control total of % and its debits come to %',
            NEW.journal_id, claimed, debits;
    END IF;
    SELECT count(*) INTO wrong_currency
      FROM plt01.led_postings
     WHERE tenant_id = NEW.tenant_id AND journal_id = NEW.journal_id
       AND currency <> journal_currency;
    IF wrong_currency > 0 THEN
        RAISE EXCEPTION
            'journal % is in % and % of its postings are not',
            NEW.journal_id, journal_currency, wrong_currency;
    END IF;
    -- **A posting is in its account's currency.** The account's own `currency` column is
    -- protected from UPDATE so that existing postings stay addable; that makes the label
    -- immutable and said nothing at all about the values it labels, so a JOD posting sat in a
    -- USD account and the account's balance became a sum across two currencies.
    SELECT count(*) INTO wrong_account
      FROM plt01.led_postings p
      JOIN plt01.led_accounts a
        ON a.tenant_id = p.tenant_id AND a.account_id = p.account_id
     WHERE p.tenant_id = NEW.tenant_id AND p.journal_id = NEW.journal_id
       AND p.currency <> a.currency;
    IF wrong_account > 0 THEN
        RAISE EXCEPTION
            'journal % has % posting(s) in a currency its account does not hold',
            NEW.journal_id, wrong_account;
    END IF;
    -- **No account twice in one journal.** `sum(amount_minor) = 0` is exactly "the journal
    -- balances" only when the lines are about different accounts: +N and -N on one account
    -- satisfies it, moves nothing, and was the route to 1000.00 of refundable wallet value
    -- with no liability recorded anywhere.
    SELECT count(*) INTO repeated_account
      FROM (SELECT account_id FROM plt01.led_postings
             WHERE tenant_id = NEW.tenant_id AND journal_id = NEW.journal_id
             GROUP BY account_id HAVING count(*) > 1) AS repeats;
    IF repeated_account > 0 THEN
        RAISE EXCEPTION
            'journal % posts to % account(s) twice; one line per account',
            NEW.journal_id, repeated_account;
    END IF;
    RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER led_postings_balance
    AFTER INSERT ON plt01.led_postings
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION plt01.led_journal_balances();

-- **A journal has at least one posting, checked at commit.** The balance trigger is on
-- `led_postings`, so a journal with no postings fires it zero times and nothing about it is
-- ever evaluated -- not the balance, not the control total. That was not theoretical: a header
-- claiming a 500.00 control total with no postings behind it satisfied the mandatory
-- `journal_id` on `led_wallet_entries`, so a member held 500.00 of spendable value with no
-- liability in the ledger, which is the state this module's wallet section says cannot exist.
-- It is also how a journal reached a closed period: park the header while the month is open,
-- close the month, then insert the postings.
CREATE OR REPLACE FUNCTION plt01.led_journal_has_postings()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    lines integer;
    period_status text;
    period_label text;
BEGIN
    SELECT count(*) INTO lines
      FROM plt01.led_postings
     WHERE tenant_id = NEW.tenant_id AND journal_id = NEW.journal_id;
    IF lines = 0 THEN
        RAISE EXCEPTION
            'journal % has no postings; a journal is its postings', NEW.journal_id;
    END IF;
    -- **And its period is re-read at commit.** The `BEFORE INSERT` check below reads the
    -- period when the header goes in; a close that commits between then and this
    -- transaction's commit would otherwise land the money in a filed month.
    SELECT status, period_key INTO period_status, period_label
      FROM plt01.led_periods
     WHERE tenant_id = NEW.tenant_id AND period_id = NEW.period_id;
    IF period_status = 'closed' THEN
        RAISE EXCEPTION
            'the period % was closed before this transaction committed', period_label;
    END IF;
    IF period_status = 'closing' AND NEW.purpose = 'trade' THEN
        RAISE EXCEPTION
            'the period % began closing before this transaction committed', period_label;
    END IF;
    RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER led_journals_have_postings
    AFTER INSERT ON plt01.led_journals
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION plt01.led_journal_has_postings();

-- **A posting into a closed period is refused, by trigger**, because the period's status is a
-- fact about another row. COM-04-R06's lock control. Immediate as well as deferred: the
-- immediate half gives the caller a readable error at the first posting, and the deferred half
-- on `led_journals` above is what catches a close that commits later in the same window.
--
-- **It takes `FOR SHARE` on the period row**, which is the whole race. An ordinary foreign-key
-- insert takes `FOR KEY SHARE`, and an UPDATE of the non-key `status` takes `FOR NO KEY
-- UPDATE`; those two do not conflict, so a till inserting a journal and an accountant closing
-- the month ran straight past each other and 75.00 of trade landed in a month that was closed
-- and filed before the postings existed. `FOR SHARE` does conflict with `FOR NO KEY UPDATE`,
-- so the close waits for the posting transaction to finish.
--
-- **And the journal's entity must own the period.** Nothing related the two, so an entity whose
-- November was closed posted more November trade through a *sibling* entity's open November
-- period -- one transaction, no race -- which defeats the lock outright and puts two legal
-- entities' journals in one export.
CREATE OR REPLACE FUNCTION plt01.led_period_admits_posting()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    period_status text;
    period_label text;
    period_from date;
    period_to date;
    period_entity uuid;
BEGIN
    SELECT status, period_key, starts_on, ends_on, legal_entity_id
      INTO period_status, period_label, period_from, period_to, period_entity
      FROM plt01.led_periods
     WHERE tenant_id = NEW.tenant_id AND period_id = NEW.period_id
       FOR SHARE;
    IF period_status IS NULL THEN
        RAISE EXCEPTION 'journal names a period that does not exist';
    END IF;
    IF period_entity <> NEW.legal_entity_id THEN
        RAISE EXCEPTION
            'journal is for legal entity % and the period % belongs to %',
            NEW.legal_entity_id, period_label, period_entity;
    END IF;
    IF NEW.posted_on < period_from OR NEW.posted_on > period_to THEN
        RAISE EXCEPTION
            'a journal dated % is outside the period % (% to %)',
            NEW.posted_on, period_label, period_from, period_to;
    END IF;
    IF period_status = 'closed' THEN
        RAISE EXCEPTION
            'the period % is closed and admits no postings; post the correction in the open '
            'period and reference the original',
            period_label;
    END IF;
    IF period_status = 'closing' AND NEW.purpose = 'trade' THEN
        RAISE EXCEPTION
            'the period % is closing and admits no trade postings', period_label;
    END IF;
    IF period_status = 'reopened' AND NEW.purpose NOT IN ('correction', 'close') THEN
        RAISE EXCEPTION
            'the period % was reopened and admits corrections only', period_label;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER led_journals_period_admits
    BEFORE INSERT ON plt01.led_journals
    FOR EACH ROW EXECUTE FUNCTION plt01.led_period_admits_posting();

-- ---------------------------------------------------------------- the member wallet
--
-- COM-04-R02. One wallet per person per currency, and no balance column anywhere: the balance
-- is the sum of the entries, which is COM-04-R07 and the reason there is nothing here to cache
-- it in.
CREATE TABLE plt01.led_wallets (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    wallet_id uuid NOT NULL DEFAULT gen_random_uuid(),
    person_id uuid NOT NULL,
    currency char(3) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, wallet_id),
    -- **One wallet per person per currency.** Two would make "what do I have" answerable
    -- twice, and the spend order could then take from whichever the caller named.
    UNIQUE (tenant_id, person_id, currency),
    FOREIGN KEY (tenant_id, person_id) REFERENCES plt01.ppl_persons (tenant_id, person_id),
    CONSTRAINT led_wallets_currency_shape CHECK (currency ~ '^[A-Z]{3}$')
);
-- **There is no freeze, and that is a deletion rather than an omission.** This table carried a
-- `status`, four freeze columns, an attribution CHECK and an UPDATE grant -- and nothing in the
-- build could set any of them: `debit_wallet` read the status and refused a frozen wallet, so
-- the refusal was unreachable and the grant was the only writer, which a reviewer used to clear
-- a freeze and its reason with one statement. COM-04 does not ask for a freeze, and inventing
-- one means inventing who may apply it, on what grounds, how it is lifted and what the member
-- sees. MOD-012 paid for the other choice: a column implying a control nobody implemented is
-- worse than no column. So `led_wallets` now has no UPDATE grant at all, which makes it the
-- sixth insert-only table here.
ALTER TABLE plt01.led_wallets ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.led_wallets FORCE ROW LEVEL SECURITY;
CREATE POLICY led_wallets_tenant ON plt01.led_wallets
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **Four kinds of value, kept apart.** Paragraph 1686's Critical Control: promotional,
-- refundable and cash-equivalent balances remain distinct. The entries are insert-only in full
-- -- no UPDATE and no DELETE grant -- so a balance is a sum nobody can edit, and an expiry is
-- evaluated at read time rather than swept, because there is no worker to sweep it and a
-- balance that counted lapsed value until one ran is value a member could spend after it had
-- gone.
CREATE TABLE plt01.led_wallet_entries (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    entry_id uuid NOT NULL DEFAULT gen_random_uuid(),
    wallet_id uuid NOT NULL,
    -- `cash`, `promotional`, `referral` or `refund_credit`. The set is
    -- `app.ledger.wallet.SPEND_ORDER` and the order is a decision about the member's interest:
    -- promotional first because it expires and is worth nothing lapsed, cash last because cash
    -- is the only kind a member can ask for back.
    value_kind text NOT NULL,
    -- Positive credits, negative debits. Never zero.
    amount_minor bigint NOT NULL,
    -- **Cash value does not expire**, and that asymmetry is the point: it is money the member
    -- paid in, so an expiry on it would be the tenant keeping money it owes. Enforced below.
    expires_on date,
    -- The journal that posted the money side. Every wallet movement has one, because a wallet
    -- balance is a liability and a liability that moved without a posting is a balance the
    -- ledger does not know about.
    journal_id uuid NOT NULL,
    reason text NOT NULL,
    source_kind text NOT NULL,
    source_ref text,
    idempotency_key text NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    actor_id uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, entry_id),
    UNIQUE (tenant_id, idempotency_key),
    FOREIGN KEY (tenant_id, wallet_id) REFERENCES plt01.led_wallets (tenant_id, wallet_id),
    FOREIGN KEY (tenant_id, journal_id)
        REFERENCES plt01.led_journals (tenant_id, journal_id),
    CONSTRAINT led_wallet_entries_kind
        CHECK (value_kind IN ('cash', 'promotional', 'referral', 'refund_credit')),
    CONSTRAINT led_wallet_entries_amount_not_zero CHECK (amount_minor <> 0),
    CONSTRAINT led_wallet_entries_amount_sane
        CHECK (amount_minor >= -1000000000000 AND amount_minor <= 1000000000000),
    CONSTRAINT led_wallet_entries_reason_not_blank CHECK (reason ~ '[^[:space:]]'),
    CONSTRAINT led_wallet_entries_source_kind CHECK (source_kind IN (
        'purchase', 'refund', 'goodwill', 'referral', 'promotion', 'spend', 'expiry',
        'correction', 'migration')),
    CONSTRAINT led_wallet_entries_source_ref_not_blank
        CHECK (source_ref IS NULL OR source_ref ~ '[^[:space:]]'),
    CONSTRAINT led_wallet_entries_key_not_blank CHECK (idempotency_key ~ '[^[:space:]]'),
    -- Cash does not expire, and a debit does not either -- an expiry on a negative entry is
    -- a field nothing reads, which is how a column comes to mean two things.
    CONSTRAINT led_wallet_entries_cash_does_not_expire
        CHECK (value_kind <> 'cash' OR expires_on IS NULL),
    CONSTRAINT led_wallet_entries_debits_do_not_expire
        CHECK (amount_minor > 0 OR expires_on IS NULL)
);
CREATE INDEX led_wallet_entries_by_wallet
    ON plt01.led_wallet_entries (tenant_id, wallet_id, occurred_at);
CREATE INDEX led_wallet_entries_expiring
    ON plt01.led_wallet_entries (tenant_id, expires_on)
    WHERE expires_on IS NOT NULL;
ALTER TABLE plt01.led_wallet_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.led_wallet_entries FORCE ROW LEVEL SECURITY;
CREATE POLICY led_wallet_entries_tenant ON plt01.led_wallet_entries
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- revenue recognition
--
-- Paragraph 1695: "Unearned revenue and RevenueRecognitionSchedule prevent prepaid membership
-- cash from becoming day-one revenue." A member who pays for a year in January has not given
-- the tenant a year of revenue; they have given it cash and taken a claim on eleven months of
-- service still owed.
CREATE TABLE plt01.led_recognition_schedules (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    schedule_id uuid NOT NULL DEFAULT gen_random_uuid(),
    legal_entity_id uuid NOT NULL,
    -- What was sold. A MOD-017 invoice line, an entitlement grant or a catalogue variant.
    source_kind text NOT NULL,
    source_ref text NOT NULL,
    subject_person_id uuid,
    -- `straight_line` earns by day, `on_delivery` by unit consumed, `immediate` when sold.
    -- Charging time against a class pack would recognise revenue for sessions the member can
    -- still demand, which is why the basis is a column rather than a convention.
    basis text NOT NULL,
    total_minor bigint NOT NULL,
    currency char(3) NOT NULL,
    starts_on date,
    ends_on date,
    units_total integer,
    -- The accounts the recognition moves between. Pinned at creation, because a chart change
    -- must not silently re-aim a schedule already running.
    unearned_account_id uuid NOT NULL,
    revenue_account_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'active',
    closed_at timestamptz,
    closed_by uuid,
    close_reason text,
    close_correlation_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, schedule_id),
    -- One schedule per thing sold. Two would recognise the same money twice.
    UNIQUE (tenant_id, source_kind, source_ref),
    FOREIGN KEY (tenant_id, legal_entity_id)
        REFERENCES plt01.legal_entities (tenant_id, legal_entity_id),
    FOREIGN KEY (tenant_id, subject_person_id)
        REFERENCES plt01.ppl_persons (tenant_id, person_id),
    FOREIGN KEY (tenant_id, unearned_account_id)
        REFERENCES plt01.led_accounts (tenant_id, account_id),
    FOREIGN KEY (tenant_id, revenue_account_id)
        REFERENCES plt01.led_accounts (tenant_id, account_id),
    CONSTRAINT led_recognition_schedules_source_kind CHECK (source_kind IN (
        'invoice_line', 'entitlement_grant', 'agreement', 'manual')),
    CONSTRAINT led_recognition_schedules_source_ref_not_blank
        CHECK (source_ref ~ '[^[:space:]]'),
    CONSTRAINT led_recognition_schedules_basis
        CHECK (basis IN ('straight_line', 'on_delivery', 'immediate')),
    CONSTRAINT led_recognition_schedules_total_positive
        CHECK (total_minor > 0 AND total_minor <= 1000000000000),
    CONSTRAINT led_recognition_schedules_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT led_recognition_schedules_status
        CHECK (status IN ('active', 'complete', 'cancelled')),
    -- **The basis decides which columns are present**, and a schedule carrying both a period
    -- and a unit count is one nothing can evaluate: `earned_by` would have to choose, and
    -- whichever it chose would be wrong half the time.
    CONSTRAINT led_recognition_schedules_period_matches_basis
        CHECK ((basis = 'straight_line') = (starts_on IS NOT NULL)),
    CONSTRAINT led_recognition_schedules_period_pair
        CHECK ((starts_on IS NULL) = (ends_on IS NULL)),
    CONSTRAINT led_recognition_schedules_units_match_basis
        CHECK ((basis = 'on_delivery') = (units_total IS NOT NULL)),
    CONSTRAINT led_recognition_schedules_dates_ordered
        CHECK (ends_on IS NULL OR starts_on IS NULL OR ends_on >= starts_on),
    CONSTRAINT led_recognition_schedules_period_bounded
        CHECK (ends_on IS NULL OR starts_on IS NULL OR ends_on - starts_on <= 3650),
    CONSTRAINT led_recognition_schedules_units_sane
        CHECK (units_total IS NULL OR (units_total > 0 AND units_total <= 100000)),
    CONSTRAINT led_recognition_schedules_accounts_differ
        CHECK (unearned_account_id <> revenue_account_id),
    CONSTRAINT led_recognition_schedules_close_attributed CHECK (
        (closed_at IS NULL AND closed_by IS NULL AND close_reason IS NULL
         AND close_correlation_id IS NULL)
        OR (closed_at IS NOT NULL AND closed_by IS NOT NULL
            AND coalesce(close_reason, '') ~ '[^[:space:]]'
            AND close_correlation_id IS NOT NULL)),
    CONSTRAINT led_recognition_schedules_closed_is_closed
        CHECK ((status IN ('complete', 'cancelled')) = (closed_at IS NOT NULL))
);
CREATE INDEX led_recognition_schedules_live
    ON plt01.led_recognition_schedules (tenant_id, status, basis);
ALTER TABLE plt01.led_recognition_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.led_recognition_schedules FORCE ROW LEVEL SECURITY;
CREATE POLICY led_recognition_schedules_tenant ON plt01.led_recognition_schedules
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **What has been recognised is a sum over these rows, not a column on the schedule.**
-- COM-04-R07 again: the cumulative figure `app.ledger.recognition.earned_by` computes is
-- compared against this sum, and the difference is what gets posted -- which is what makes the
-- command safe to run ten times in one day. Insert-only in full.
CREATE TABLE plt01.led_recognition_runs (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    run_id uuid NOT NULL DEFAULT gen_random_uuid(),
    schedule_id uuid NOT NULL,
    journal_id uuid NOT NULL,
    -- What this run moved from unearned to earned. Positive: a negative recognition is a
    -- correction somebody makes deliberately, as a `correction` journal with a reason.
    amount_minor bigint NOT NULL,
    -- The figures the decision was made from, so a run is reproducible: the cumulative earned
    -- figure and the state it was measured against.
    earned_to_date_minor bigint NOT NULL,
    recognised_before_minor bigint NOT NULL,
    as_of date NOT NULL,
    units_delivered integer,
    idempotency_key text NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    posted_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, run_id),
    UNIQUE (tenant_id, idempotency_key),
    FOREIGN KEY (tenant_id, schedule_id)
        REFERENCES plt01.led_recognition_schedules (tenant_id, schedule_id),
    FOREIGN KEY (tenant_id, journal_id)
        REFERENCES plt01.led_journals (tenant_id, journal_id),
    CONSTRAINT led_recognition_runs_amount_positive
        CHECK (amount_minor > 0 AND amount_minor <= 1000000000000),
    -- The ceiling only: the floor is implied by `amount_positive` and `before_sane`
    -- together, since `adds_up` makes this the sum of those two, so a case that isolates it
    -- does not exist and a constraint nobody can test is one the sweep cannot defend.
    CONSTRAINT led_recognition_runs_earned_sane
        CHECK (earned_to_date_minor <= 1000000000000),
    CONSTRAINT led_recognition_runs_before_sane
        CHECK (recognised_before_minor >= 0
               AND recognised_before_minor <= 1000000000000),
    -- **The arithmetic holds in the row.** What was posted is the difference between what is
    -- earned and what had been recognised, and a row where those three disagree is the defect
    -- nobody would spot by reading the amount.
    CONSTRAINT led_recognition_runs_adds_up
        CHECK (amount_minor = earned_to_date_minor - recognised_before_minor),
    CONSTRAINT led_recognition_runs_units_sane
        CHECK (units_delivered IS NULL
               OR (units_delivered >= 0 AND units_delivered <= 100000)),
    CONSTRAINT led_recognition_runs_key_not_blank CHECK (idempotency_key ~ '[^[:space:]]')
);
CREATE INDEX led_recognition_runs_by_schedule
    ON plt01.led_recognition_runs (tenant_id, schedule_id, as_of);
ALTER TABLE plt01.led_recognition_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.led_recognition_runs FORCE ROW LEVEL SECURITY;
CREATE POLICY led_recognition_runs_tenant ON plt01.led_recognition_runs
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- provider settlement
--
-- COM-04-R04. **A settlement is what the provider says it paid out, and it rarely equals what
-- this build thinks it took.** The difference is fees, timing, chargebacks and the provider's
-- own corrections, and the whole point of importing one is to find out which.
CREATE TABLE plt01.led_settlements (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    settlement_id uuid NOT NULL DEFAULT gen_random_uuid(),
    legal_entity_id uuid NOT NULL,
    provider_key text NOT NULL,
    -- The provider's own identifier for the file or payout batch. One import per batch.
    provider_batch_ref text NOT NULL,
    settled_on date NOT NULL,
    currency char(3) NOT NULL,
    -- What the file's own header claims the net payout is, and what its lines come to. **Both
    -- are stored**, because a file whose header disagrees with its body was truncated or
    -- edited in transit, and importing it would post half a day's takings as all of them.
    claimed_total_minor bigint NOT NULL,
    computed_total_minor bigint NOT NULL,
    line_count integer NOT NULL,
    status text NOT NULL DEFAULT 'imported',
    -- Where the file came from. A locator, never the file: this build has no object store, and
    -- a column that could hold the bytes is a column somebody puts card numbers in.
    document_ref text,
    imported_at timestamptz NOT NULL DEFAULT now(),
    imported_by uuid NOT NULL,
    idempotency_key text NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, settlement_id),
    UNIQUE (tenant_id, idempotency_key),
    -- **One import per provider batch.** A file imported twice doubles every posting it makes,
    -- and a provider re-sending a batch is the ordinary case rather than an edge.
    UNIQUE (tenant_id, provider_key, provider_batch_ref),
    FOREIGN KEY (tenant_id, legal_entity_id)
        REFERENCES plt01.legal_entities (tenant_id, legal_entity_id),
    CONSTRAINT led_settlements_provider_shape
        CHECK (provider_key ~ '^[a-z][a-z0-9_.-]{1,62}$'),
    CONSTRAINT led_settlements_batch_not_blank CHECK (provider_batch_ref ~ '[^[:space:]]'),
    CONSTRAINT led_settlements_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT led_settlements_totals_sane CHECK (
        claimed_total_minor >= -1000000000000
        AND claimed_total_minor <= 1000000000000
        AND computed_total_minor >= -1000000000000
        AND computed_total_minor <= 1000000000000),
    CONSTRAINT led_settlements_line_count_positive
        CHECK (line_count > 0 AND line_count <= 100000),
    CONSTRAINT led_settlements_status
        CHECK (status IN ('imported', 'reconciled', 'disputed')),
    CONSTRAINT led_settlements_document_is_a_locator
        CHECK (document_ref IS NULL
               OR document_ref ~ '^[a-z][a-z0-9+.-]*://[^[:space:]]+$'),
    CONSTRAINT led_settlements_key_not_blank CHECK (idempotency_key ~ '[^[:space:]]')
);
CREATE INDEX led_settlements_by_date
    ON plt01.led_settlements (tenant_id, provider_key, settled_on);
ALTER TABLE plt01.led_settlements ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.led_settlements FORCE ROW LEVEL SECURITY;
CREATE POLICY led_settlements_tenant ON plt01.led_settlements
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- One line per movement the provider reports, with the verdict `app.ledger.settlement.match`
-- reached. **The verdict is stored and insert-only**: re-running a match that reached a
-- different answer is a new line nobody can write, so a changed verdict is a reconciliation
-- case rather than a rewritten row.
CREATE TABLE plt01.led_settlement_lines (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    line_id uuid NOT NULL DEFAULT gen_random_uuid(),
    settlement_id uuid NOT NULL,
    line_number integer NOT NULL,
    line_kind text NOT NULL,
    provider_ref text NOT NULL,
    amount_minor bigint NOT NULL,
    currency char(3) NOT NULL,
    -- What the matcher concluded, and in its own words. The outcome is a declared value a
    -- report can branch on; the reason is the sentence a human reads.
    outcome text NOT NULL,
    outcome_reason text NOT NULL,
    -- What it matched, where it matched something. MOD-017's payment or refund.
    matched_payment_id uuid,
    matched_refund_id uuid,
    PRIMARY KEY (tenant_id, line_id),
    UNIQUE (tenant_id, settlement_id, line_number),
    FOREIGN KEY (tenant_id, settlement_id)
        REFERENCES plt01.led_settlements (tenant_id, settlement_id),
    FOREIGN KEY (tenant_id, matched_payment_id)
        REFERENCES plt01.fin_payments (tenant_id, payment_id),
    FOREIGN KEY (tenant_id, matched_refund_id)
        REFERENCES plt01.fin_refunds (tenant_id, refund_id),
    CONSTRAINT led_settlement_lines_kind CHECK (line_kind IN (
        'payment', 'refund', 'fee', 'chargeback', 'chargeback_reversal', 'adjustment',
        'payout')),
    CONSTRAINT led_settlement_lines_ref_not_blank CHECK (provider_ref ~ '[^[:space:]]'),
    CONSTRAINT led_settlement_lines_amount_not_zero CHECK (amount_minor <> 0),
    CONSTRAINT led_settlement_lines_amount_sane
        CHECK (amount_minor >= -1000000000000 AND amount_minor <= 1000000000000),
    CONSTRAINT led_settlement_lines_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT led_settlement_lines_outcome CHECK (outcome IN (
        'matched', 'amount_mismatch', 'unmatched', 'duplicate', 'not_expected')),
    CONSTRAINT led_settlement_lines_reason_not_blank
        CHECK (outcome_reason ~ '[^[:space:]]'),
    CONSTRAINT led_settlement_lines_line_positive CHECK (line_number >= 1),
    -- **A line matches at most one thing.** Two references would make "what did this settle"
    -- answerable twice, and the amount comparison would have had to pick one.
    CONSTRAINT led_settlement_lines_one_match
        CHECK (matched_payment_id IS NULL OR matched_refund_id IS NULL),
    -- And only a matched line names a match: an `unmatched` line carrying a payment id is a
    -- row whose outcome and whose body disagree.
    CONSTRAINT led_settlement_lines_match_matches_outcome
        CHECK ((outcome = 'matched')
               = (matched_payment_id IS NOT NULL OR matched_refund_id IS NOT NULL))
);
CREATE INDEX led_settlement_lines_by_outcome
    ON plt01.led_settlement_lines (tenant_id, outcome, settlement_id);
CREATE INDEX led_settlement_lines_by_ref
    ON plt01.led_settlement_lines (tenant_id, provider_ref);
ALTER TABLE plt01.led_settlement_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.led_settlement_lines FORCE ROW LEVEL SECURITY;
CREATE POLICY led_settlement_lines_tenant ON plt01.led_settlement_lines
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- the open questions
--
-- **Nothing is absorbed silently and nothing is written off automatically.** An unmatched
-- settlement line, a till that does not balance and a deposit that disagrees with the sessions
-- it banks are all the same kind of thing: a question nobody has answered. Paragraph 1699's
-- "reconciliation mismatch = 0 unresolved past SLA" is a target somebody works, not an
-- invariant this code can assert -- so what the schema provides is a row per question with an
-- age and a resolution that names who decided.
CREATE TABLE plt01.led_reconciliation_cases (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    case_id uuid NOT NULL DEFAULT gen_random_uuid(),
    legal_entity_id uuid NOT NULL,
    case_kind text NOT NULL,
    -- What the case is about. A settlement line, a cash session, a deposit or a control total.
    subject_kind text NOT NULL,
    subject_ref text NOT NULL,
    -- The two figures that disagree, which is what a case *is*. Stored rather than recomputed,
    -- because the thing being reconciled may move afterwards and the question was about the
    -- figures at the time.
    expected_minor bigint NOT NULL,
    observed_minor bigint NOT NULL,
    currency char(3) NOT NULL,
    detail text NOT NULL,
    status text NOT NULL DEFAULT 'open',
    opened_on date NOT NULL,
    -- Where it ended, and who said so. A case resolved by a correcting journal names it.
    resolution text,
    resolution_journal_id uuid,
    resolved_at timestamptz,
    resolved_by uuid,
    resolve_correlation_id uuid,
    opened_by uuid NOT NULL,
    idempotency_key text NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, case_id),
    UNIQUE (tenant_id, idempotency_key),
    FOREIGN KEY (tenant_id, legal_entity_id)
        REFERENCES plt01.legal_entities (tenant_id, legal_entity_id),
    FOREIGN KEY (tenant_id, resolution_journal_id)
        REFERENCES plt01.led_journals (tenant_id, journal_id),
    CONSTRAINT led_reconciliation_cases_kind CHECK (case_kind IN (
        'settlement_line', 'settlement_total', 'cash_variance', 'deposit_variance',
        'control_total')),
    CONSTRAINT led_reconciliation_cases_subject_kind CHECK (subject_kind IN (
        'settlement', 'settlement_line', 'cash_session', 'deposit', 'account', 'period')),
    CONSTRAINT led_reconciliation_cases_subject_not_blank
        CHECK (subject_ref ~ '[^[:space:]]'),
    CONSTRAINT led_reconciliation_cases_amounts_sane CHECK (
        expected_minor >= -1000000000000 AND expected_minor <= 1000000000000
        AND observed_minor >= -1000000000000 AND observed_minor <= 1000000000000),
    CONSTRAINT led_reconciliation_cases_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT led_reconciliation_cases_detail_not_blank CHECK (detail ~ '[^[:space:]]'),
    CONSTRAINT led_reconciliation_cases_status CHECK (status IN (
        'open', 'investigating', 'resolved', 'written_off', 'abandoned')),
    CONSTRAINT led_reconciliation_cases_key_not_blank
        CHECK (idempotency_key ~ '[^[:space:]]'),
    -- **A case exists because two figures disagree**, so one that opens with them equal is a
    -- case about nothing -- and in a table whose whole purpose is the unanswered question, a
    -- row about nothing is noise an operator learns to ignore.
    CONSTRAINT led_reconciliation_cases_figures_differ
        CHECK (expected_minor <> observed_minor),
    -- A resolution names who and when and under which correlation, and says what it was.
    CONSTRAINT led_reconciliation_cases_resolution_attributed CHECK (
        (resolved_at IS NULL AND resolved_by IS NULL AND resolution IS NULL
         AND resolve_correlation_id IS NULL)
        OR (resolved_at IS NOT NULL AND resolved_by IS NOT NULL
            AND coalesce(resolution, '') ~ '[^[:space:]]'
            AND resolve_correlation_id IS NOT NULL)),
    CONSTRAINT led_reconciliation_cases_closed_is_resolved
        CHECK ((status IN ('resolved', 'written_off', 'abandoned'))
               = (resolved_at IS NOT NULL)),
    -- A journal may only be cited by a case that was actually resolved.
    CONSTRAINT led_reconciliation_cases_journal_needs_a_resolution
        CHECK (resolution_journal_id IS NULL OR resolved_at IS NOT NULL)
);
CREATE INDEX led_reconciliation_cases_open
    ON plt01.led_reconciliation_cases (tenant_id, status, opened_on)
    WHERE status IN ('open', 'investigating');
CREATE INDEX led_reconciliation_cases_by_subject
    ON plt01.led_reconciliation_cases (tenant_id, subject_kind, subject_ref);
ALTER TABLE plt01.led_reconciliation_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.led_reconciliation_cases FORCE ROW LEVEL SECURITY;
CREATE POLICY led_reconciliation_cases_tenant ON plt01.led_reconciliation_cases
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- cash, drawers and deposits
--
-- COM-04-R05: "cash drawer, bank deposit and payout reconciliation with discrepancy
-- workflows." **The variance is the finding, not the money.** A till 2.00 down is noise; a till
-- 2.00 down every evening with nothing written against it is a pattern, and the only way that
-- pattern is visible later is if each close said something at the time.
CREATE TABLE plt01.led_cash_sessions (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    session_id uuid NOT NULL DEFAULT gen_random_uuid(),
    location_id uuid NOT NULL,
    -- The till's own cash account, so a session's postings land where that drawer's balance is.
    cash_account_id uuid NOT NULL,
    -- A tenant's label for the drawer. Two tills at one desk are two labels.
    drawer_label text NOT NULL,
    currency char(3) NOT NULL,
    -- What was in it at the start, counted by the person opening. **The service posts this
    -- across from the account it came from** -- the safe -- so the drawer's own balance is the
    -- money in the drawer. A float that lived only here was cash the ledger did not know
    -- about: banking the takings then drove the drawer's account negative by exactly the
    -- float, and the expected count was a number the caller sent rather than one derived.
    opening_float_minor bigint NOT NULL,
    status text NOT NULL DEFAULT 'open',
    opened_at timestamptz NOT NULL DEFAULT now(),
    opened_by uuid NOT NULL,
    -- The close. `expected` is the drawer account's own balance, derived from its postings
    -- with no number the caller sent; `counted` is what the person found. Both are recorded,
    -- because the variance is the difference and a stored difference could disagree with its
    -- own inputs.
    expected_minor bigint,
    counted_minor bigint,
    variance_reason text,
    closed_at timestamptz,
    closed_by uuid,
    close_correlation_id uuid,
    -- The journal that posted the variance to `suspense`, where there was one.
    variance_journal_id uuid,
    idempotency_key text NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, session_id),
    UNIQUE (tenant_id, idempotency_key),
    FOREIGN KEY (tenant_id, location_id)
        REFERENCES plt01.locations (tenant_id, location_id),
    FOREIGN KEY (tenant_id, cash_account_id)
        REFERENCES plt01.led_accounts (tenant_id, account_id),
    FOREIGN KEY (tenant_id, variance_journal_id)
        REFERENCES plt01.led_journals (tenant_id, journal_id),
    CONSTRAINT led_cash_sessions_label_not_blank CHECK (drawer_label ~ '[^[:space:]]'),
    CONSTRAINT led_cash_sessions_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT led_cash_sessions_float_not_negative
        CHECK (opening_float_minor >= 0 AND opening_float_minor <= 1000000000000),
    CONSTRAINT led_cash_sessions_status
        CHECK (status IN ('open', 'closed', 'abandoned')),
    CONSTRAINT led_cash_sessions_counts_not_negative CHECK (
        (counted_minor IS NULL OR
         (counted_minor >= 0 AND counted_minor <= 1000000000000))
        AND (expected_minor IS NULL OR
             (expected_minor >= -1000000000000 AND expected_minor <= 1000000000000))),
    -- A close records both figures, its actor and its correlation, or none of them.
    CONSTRAINT led_cash_sessions_close_attributed CHECK (
        (closed_at IS NULL AND closed_by IS NULL AND close_correlation_id IS NULL
         AND counted_minor IS NULL AND expected_minor IS NULL)
        OR (closed_at IS NOT NULL AND closed_by IS NOT NULL
            AND close_correlation_id IS NOT NULL
            AND counted_minor IS NOT NULL AND expected_minor IS NOT NULL)),
    CONSTRAINT led_cash_sessions_closed_is_closed
        CHECK ((status IN ('closed', 'abandoned')) = (closed_at IS NOT NULL)),
    -- **A variance is explained or the close is refused.** The one control in this table.
    CONSTRAINT led_cash_sessions_variance_explained
        CHECK (counted_minor IS NULL OR expected_minor IS NULL
               OR counted_minor = expected_minor
               OR coalesce(variance_reason, '') ~ '[^[:space:]]'),
    -- And a variance journal only exists where there was a variance.
    CONSTRAINT led_cash_sessions_journal_needs_a_variance
        CHECK (variance_journal_id IS NULL
               OR (counted_minor IS NOT NULL AND expected_minor IS NOT NULL
                   AND counted_minor <> expected_minor))
);
-- **One open session per drawer.** Two would make "what should be in this till" answerable
-- twice, and the second close would be measured against the first's postings.
CREATE UNIQUE INDEX led_cash_sessions_one_open
    ON plt01.led_cash_sessions (tenant_id, location_id, drawer_label)
    WHERE status = 'open';
CREATE INDEX led_cash_sessions_by_location
    ON plt01.led_cash_sessions (tenant_id, location_id, opened_at);
ALTER TABLE plt01.led_cash_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.led_cash_sessions FORCE ROW LEVEL SECURITY;
CREATE POLICY led_cash_sessions_tenant ON plt01.led_cash_sessions
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- A bank deposit: cash leaving the premises for an account. The journal moves it from `cash`
-- to `bank`, and the deposit row is what ties the two together when the bank statement arrives
-- days later saying a different number.
CREATE TABLE plt01.led_deposits (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    deposit_id uuid NOT NULL DEFAULT gen_random_uuid(),
    location_id uuid NOT NULL,
    cash_account_id uuid NOT NULL,
    bank_account_id uuid NOT NULL,
    currency char(3) NOT NULL,
    -- What was put in the bag, declared by the person who sealed it.
    declared_minor bigint NOT NULL,
    -- What the bank said it received, when it says so. Nullable until then, which is the whole
    -- reason this is a row rather than a journal: the gap between the two is days long.
    credited_minor bigint,
    bank_reference text,
    deposited_on date NOT NULL,
    credited_on date,
    status text NOT NULL DEFAULT 'in_transit',
    journal_id uuid NOT NULL,
    confirm_journal_id uuid,
    confirmed_at timestamptz,
    confirmed_by uuid,
    confirm_correlation_id uuid,
    idempotency_key text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, deposit_id),
    UNIQUE (tenant_id, idempotency_key),
    FOREIGN KEY (tenant_id, location_id)
        REFERENCES plt01.locations (tenant_id, location_id),
    FOREIGN KEY (tenant_id, cash_account_id)
        REFERENCES plt01.led_accounts (tenant_id, account_id),
    FOREIGN KEY (tenant_id, bank_account_id)
        REFERENCES plt01.led_accounts (tenant_id, account_id),
    FOREIGN KEY (tenant_id, journal_id)
        REFERENCES plt01.led_journals (tenant_id, journal_id),
    FOREIGN KEY (tenant_id, confirm_journal_id)
        REFERENCES plt01.led_journals (tenant_id, journal_id),
    CONSTRAINT led_deposits_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT led_deposits_declared_positive
        CHECK (declared_minor > 0 AND declared_minor <= 1000000000000),
    CONSTRAINT led_deposits_credited_sane
        CHECK (credited_minor IS NULL
               OR (credited_minor >= 0 AND credited_minor <= 1000000000000)),
    CONSTRAINT led_deposits_reference_not_blank
        CHECK (bank_reference IS NULL OR bank_reference ~ '[^[:space:]]'),
    CONSTRAINT led_deposits_status
        CHECK (status IN ('in_transit', 'credited', 'short', 'lost')),
    CONSTRAINT led_deposits_accounts_differ CHECK (cash_account_id <> bank_account_id),
    CONSTRAINT led_deposits_key_not_blank CHECK (idempotency_key ~ '[^[:space:]]'),
    -- A confirmation names who and when, and carries what the bank said and when.
    CONSTRAINT led_deposits_confirmation_attributed CHECK (
        (confirmed_at IS NULL AND confirmed_by IS NULL AND confirm_correlation_id IS NULL
         AND credited_minor IS NULL AND credited_on IS NULL)
        OR (confirmed_at IS NOT NULL AND confirmed_by IS NOT NULL
            AND confirm_correlation_id IS NOT NULL
            AND credited_minor IS NOT NULL AND credited_on IS NOT NULL)),
    CONSTRAINT led_deposits_settled_is_confirmed
        CHECK ((status IN ('credited', 'short')) = (confirmed_at IS NOT NULL)),
    -- **`credited` means the bank agreed.** A deposit credited for a different amount is
    -- `short`, which is a distinct status precisely so a report of "deposits credited" is not
    -- quietly a report of "deposits the bank disagreed with".
    CONSTRAINT led_deposits_credited_agrees
        CHECK (status <> 'credited' OR credited_minor = declared_minor),
    CONSTRAINT led_deposits_short_disagrees
        CHECK (status <> 'short' OR credited_minor <> declared_minor),
    CONSTRAINT led_deposits_dates_ordered
        CHECK (credited_on IS NULL OR credited_on >= deposited_on)
);
CREATE INDEX led_deposits_in_transit
    ON plt01.led_deposits (tenant_id, deposited_on)
    WHERE status = 'in_transit';
ALTER TABLE plt01.led_deposits ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.led_deposits FORCE ROW LEVEL SECURITY;
CREATE POLICY led_deposits_tenant ON plt01.led_deposits
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- Which till sessions a deposit banks. **A join table rather than a column on the session**,
-- because one bag routinely holds several sessions and one session is occasionally split across
-- two bags -- and because a session's row is closed and insert-only by then.
CREATE TABLE plt01.led_deposit_sessions (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    deposit_id uuid NOT NULL,
    session_id uuid NOT NULL,
    -- What of that session's cash went into this bag. Allows a split, and the sum across a
    -- session's rows is what the deposit reconciliation compares against.
    amount_minor bigint NOT NULL,
    added_at timestamptz NOT NULL DEFAULT now(),
    added_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, deposit_id, session_id),
    -- **One session is banked once.** The primary key permits one session in unlimited
    -- deposits, and nothing read this table before inserting -- so a reviewer banked a
    -- 200.00 session in two deposits under two idempotency keys, which is the ordinary
    -- retry-with-a-new-key case: 400.00 in the bank, minus 200.00 in a drawer, no
    -- reconciliation case, and the clean route to pocketing 200.00 of notes while the
    -- negative drawer reads as a banking error. A split bag is one row with a smaller
    -- amount, not a second deposit.
    UNIQUE (tenant_id, session_id),
    FOREIGN KEY (tenant_id, deposit_id)
        REFERENCES plt01.led_deposits (tenant_id, deposit_id),
    FOREIGN KEY (tenant_id, session_id)
        REFERENCES plt01.led_cash_sessions (tenant_id, session_id),
    -- **The floor only.** The ceiling is the trigger below, which bounds this against what
    -- the session actually counted -- and since a count is itself bounded at 1e12, a
    -- hand-written ceiling here is subsumed and has no isolating case. One constraint that is
    -- the stronger statement beats two where the weaker is permanently unprovable.
    CONSTRAINT led_deposit_sessions_amount_positive CHECK (amount_minor > 0)
);

-- **A banked session is closed, at this deposit's own location, for no more than it counted.**
-- All three are facts about other rows, so a CHECK cannot see them, and without them a deposit
-- at one site banked another site's till for ten times what that till held.
CREATE OR REPLACE FUNCTION plt01.led_banked_session_agrees()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    session_status text;
    session_counted bigint;
    session_location uuid;
    session_currency char(3);
    deposit_location uuid;
    deposit_currency char(3);
    already bigint;
BEGIN
    SELECT status, counted_minor, location_id, currency
      INTO session_status, session_counted, session_location, session_currency
      FROM plt01.led_cash_sessions
     WHERE tenant_id = NEW.tenant_id AND session_id = NEW.session_id;
    SELECT location_id, currency INTO deposit_location, deposit_currency
      FROM plt01.led_deposits
     WHERE tenant_id = NEW.tenant_id AND deposit_id = NEW.deposit_id;
    IF session_status <> 'closed' THEN
        RAISE EXCEPTION
            'till session % is % and only a closed session has takings to bank',
            NEW.session_id, session_status;
    END IF;
    IF session_location <> deposit_location THEN
        RAISE EXCEPTION
            'till session % is at another location than this deposit', NEW.session_id;
    END IF;
    IF session_currency <> deposit_currency THEN
        RAISE EXCEPTION
            'till session % is in % and this deposit is in %', NEW.session_id,
            session_currency, deposit_currency;
    END IF;
    SELECT coalesce(sum(amount_minor), 0) INTO already
      FROM plt01.led_deposit_sessions
     WHERE tenant_id = NEW.tenant_id AND session_id = NEW.session_id
       AND deposit_id <> NEW.deposit_id;
    IF already + NEW.amount_minor > session_counted THEN
        RAISE EXCEPTION
            'till session % counted % and % has already been banked from it',
            NEW.session_id, session_counted, already;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER led_deposit_sessions_agree
    BEFORE INSERT ON plt01.led_deposit_sessions
    FOR EACH ROW EXECUTE FUNCTION plt01.led_banked_session_agrees();
CREATE INDEX led_deposit_sessions_by_session
    ON plt01.led_deposit_sessions (tenant_id, session_id);
ALTER TABLE plt01.led_deposit_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.led_deposit_sessions FORCE ROW LEVEL SECURITY;
CREATE POLICY led_deposit_sessions_tenant ON plt01.led_deposit_sessions
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- the accounting export
--
-- COM-04-R06's "export to accounting systems", as a record of what was exported rather than as
-- the file.
--
-- **One export per period per target system, and the period has to be closed.** The first
-- version of this comment claimed a trigger it did not have and a marker that does not exist,
-- while the grant block forty lines down said the opposite -- "nothing about it moves, which is
-- why it needs no trigger". Neither was the control: the only unique key was the
-- caller-supplied idempotency key, so one period was exported twice to the same system under
-- two keys and 5,000.00 of debits reached the accounting system twice, which is exactly the
-- double-counted period the comment named. The unique index below is the control, and the
-- trigger is what makes "a closed period" a fact the database knows rather than a check one
-- service happens to make.
CREATE TABLE plt01.led_exports (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    export_id uuid NOT NULL DEFAULT gen_random_uuid(),
    period_id uuid NOT NULL,
    -- What system it went to, and that system's own handle for the batch.
    target_system text NOT NULL,
    target_ref text NOT NULL,
    -- The control totals the export carried, per the TSD's ReconcileControlTotal command: the
    -- debits, the credits and the journal count. Stored so a later question about the export
    -- is answerable without rebuilding it.
    journal_count integer NOT NULL,
    debit_total_minor bigint NOT NULL,
    credit_total_minor bigint NOT NULL,
    currency char(3) NOT NULL,
    exported_at timestamptz NOT NULL DEFAULT now(),
    exported_by uuid NOT NULL,
    idempotency_key text NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, export_id),
    UNIQUE (tenant_id, idempotency_key),
    FOREIGN KEY (tenant_id, period_id) REFERENCES plt01.led_periods (tenant_id, period_id),
    CONSTRAINT led_exports_system_shape
        CHECK (target_system ~ '^[a-z][a-z0-9_.-]{1,62}$'),
    CONSTRAINT led_exports_ref_not_blank CHECK (target_ref ~ '[^[:space:]]'),
    CONSTRAINT led_exports_count_positive
        CHECK (journal_count > 0 AND journal_count <= 10000000),
    CONSTRAINT led_exports_totals_sane CHECK (
        debit_total_minor >= 0 AND debit_total_minor <= 1000000000000
        AND credit_total_minor >= 0 AND credit_total_minor <= 1000000000000),
    -- **The export balances or it is not an export.** Every journal in it balanced, so the
    -- debits and the credits of a set of journals are equal by construction -- and a row where
    -- they are not is an export built from a query that lost rows.
    CONSTRAINT led_exports_balances CHECK (debit_total_minor = credit_total_minor),
    CONSTRAINT led_exports_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT led_exports_key_not_blank CHECK (idempotency_key ~ '[^[:space:]]')
);
CREATE INDEX led_exports_by_period ON plt01.led_exports (tenant_id, period_id);
-- The control the comment above names. A second system is a second export; the same system
-- twice is the figure counted twice.
CREATE UNIQUE INDEX led_exports_one_per_system
    ON plt01.led_exports (tenant_id, period_id, target_system);

-- **An export of an open month is a figure that changes after it was filed.** The service
-- refuses one; this is the half that holds when the service is wrong.
CREATE OR REPLACE FUNCTION plt01.led_export_needs_a_closed_period()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    period_status text;
    period_label text;
BEGIN
    SELECT status, period_key INTO period_status, period_label
      FROM plt01.led_periods
     WHERE tenant_id = NEW.tenant_id AND period_id = NEW.period_id;
    IF period_status <> 'closed' THEN
        RAISE EXCEPTION
            'the period % is % and an export of a period that is not closed is a figure that '
            'changes after it was filed', period_label, period_status;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER led_exports_period_is_closed
    BEFORE INSERT ON plt01.led_exports
    FOR EACH ROW EXECUTE FUNCTION plt01.led_export_needs_a_closed_period();
ALTER TABLE plt01.led_exports ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.led_exports FORCE ROW LEVEL SECURITY;
CREATE POLICY led_exports_tenant ON plt01.led_exports
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ------------------------------------------------- lifecycle decisions are made once
--
-- **A CHECK cannot see what a row used to be.** MOD-009 learned this on `sec_legal_holds` and
-- this file cited it for `fin_tax_records` -- and then left six of its own lifecycle decisions
-- to the service, which an independent reviewer executed one at a time: a filed period
-- un-closed with no reason, re-opened to trade, re-closed under a different actor and reading
-- as a month closed once; a 400.00 cash shortfall on a bank deposit erased; a till close
-- rewritten so the drawer balanced and the written variance deleted; a reconciliation
-- resolution and the name of whoever decided to write money off replaced. Every one of those
-- columns is declared `write_once` in the privacy registry, and every one was service
-- discipline only, in the module whose premise is "this is the half that still holds when the
-- service is wrong."
--
-- Six triggers rather than one dispatching on `TG_TABLE_NAME`: each protects a different set
-- of columns, each gets its own mutation, and a reader of one does not have to read the other
-- five. The rules are the same in all of them -- the status moves only along a sanctioned
-- edge, a settlement timestamp is never cleared and never moves backwards, and whoever made
-- the decision is never replaced.

CREATE OR REPLACE FUNCTION plt01.led_period_is_one_way()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF OLD.status <> NEW.status AND NOT (
        (OLD.status = 'open' AND NEW.status = 'closing')
        OR (OLD.status = 'closing' AND NEW.status IN ('closed', 'open'))
        OR (OLD.status = 'closed' AND NEW.status = 'reopened')
        OR (OLD.status = 'reopened' AND NEW.status = 'closing')
    ) THEN
        RAISE EXCEPTION
            'a financial period does not move from % to %', OLD.status, NEW.status;
    END IF;
    -- A close time never disappears and never moves earlier. A re-close moves it forward,
    -- which is the truthful statement; the reopening record says it was reopened between.
    IF OLD.closed_at IS NOT NULL
       AND (NEW.closed_at IS NULL OR NEW.closed_at < OLD.closed_at) THEN
        RAISE EXCEPTION 'the close of period % has already been recorded', OLD.period_key;
    END IF;
    IF OLD.reopened_at IS NOT NULL
       AND (NEW.reopened_at IS NULL OR NEW.reopened_at < OLD.reopened_at) THEN
        RAISE EXCEPTION 'the reopening of period % has already been recorded', OLD.period_key;
    END IF;
    IF OLD.reopen_reason IS NOT NULL
       AND NEW.reopen_reason IS DISTINCT FROM OLD.reopen_reason THEN
        RAISE EXCEPTION 'the reason period % was reopened does not change', OLD.period_key;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER led_periods_one_way
    BEFORE UPDATE ON plt01.led_periods
    FOR EACH ROW EXECUTE FUNCTION plt01.led_period_is_one_way();

CREATE OR REPLACE FUNCTION plt01.led_account_retirement_is_final()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF OLD.status = 'retired' AND NEW.status <> 'retired' THEN
        RAISE EXCEPTION
            'account % is retired; open a new account rather than reviving it',
            OLD.account_code;
    END IF;
    IF OLD.retired_at IS NOT NULL AND (
        NEW.retired_at IS DISTINCT FROM OLD.retired_at
        OR NEW.retired_by IS DISTINCT FROM OLD.retired_by) THEN
        RAISE EXCEPTION 'the retirement of account % has already been recorded',
            OLD.account_code;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER led_accounts_one_way
    BEFORE UPDATE ON plt01.led_accounts
    FOR EACH ROW EXECUTE FUNCTION plt01.led_account_retirement_is_final();

CREATE OR REPLACE FUNCTION plt01.led_cash_close_is_final()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF OLD.status <> 'open' THEN
        RAISE EXCEPTION
            'till session % is % and a closed drawer is not counted again', OLD.session_id,
            OLD.status;
    END IF;
    IF NEW.status NOT IN ('closed', 'abandoned') THEN
        RAISE EXCEPTION 'a till session closes or is abandoned; % is neither', NEW.status;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER led_cash_sessions_one_way
    BEFORE UPDATE ON plt01.led_cash_sessions
    FOR EACH ROW EXECUTE FUNCTION plt01.led_cash_close_is_final();

CREATE OR REPLACE FUNCTION plt01.led_deposit_confirmation_is_final()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF OLD.status <> 'in_transit' THEN
        RAISE EXCEPTION
            'deposit % is % and what the bank did with a bag is recorded once',
            OLD.deposit_id, OLD.status;
    END IF;
    IF NEW.status NOT IN ('credited', 'short', 'lost') THEN
        RAISE EXCEPTION 'a deposit is credited, short or lost; % is none of those',
            NEW.status;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER led_deposits_one_way
    BEFORE UPDATE ON plt01.led_deposits
    FOR EACH ROW EXECUTE FUNCTION plt01.led_deposit_confirmation_is_final();

CREATE OR REPLACE FUNCTION plt01.led_case_resolution_is_final()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF OLD.status IN ('resolved', 'written_off') THEN
        RAISE EXCEPTION
            'case % is already % and who decided that does not change', OLD.case_id,
            OLD.status;
    END IF;
    IF NEW.status NOT IN ('investigating', 'resolved', 'written_off') THEN
        RAISE EXCEPTION 'a reconciliation case does not move to %', NEW.status;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER led_reconciliation_cases_one_way
    BEFORE UPDATE ON plt01.led_reconciliation_cases
    FOR EACH ROW EXECUTE FUNCTION plt01.led_case_resolution_is_final();

CREATE OR REPLACE FUNCTION plt01.led_schedule_close_is_final()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF OLD.status <> 'active' THEN
        RAISE EXCEPTION
            'schedule % is % and a settled schedule does not reopen', OLD.schedule_id,
            OLD.status;
    END IF;
    IF NEW.status NOT IN ('active', 'complete', 'cancelled') THEN
        RAISE EXCEPTION 'a recognition schedule does not move to %', NEW.status;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER led_recognition_schedules_one_way
    BEFORE UPDATE ON plt01.led_recognition_schedules
    FOR EACH ROW EXECUTE FUNCTION plt01.led_schedule_close_is_final();

CREATE OR REPLACE FUNCTION plt01.led_settlement_status_is_one_way()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF OLD.status = 'reconciled' AND NEW.status <> 'reconciled' THEN
        RAISE EXCEPTION
            'settlement % is reconciled; a later disagreement is a case, not a status change',
            OLD.settlement_id;
    END IF;
    IF NEW.status NOT IN ('imported', 'reconciled', 'disputed') THEN
        RAISE EXCEPTION 'a settlement does not move to %', NEW.status;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER led_settlements_one_way
    BEFORE UPDATE ON plt01.led_settlements
    FOR EACH ROW EXECUTE FUNCTION plt01.led_settlement_status_is_one_way();

-- ---------------------------------------------------------------- privileges
--
-- **Paragraph 1685 is a Critical Control and this block is where it lives**: "posted financial
-- entries are never edited or deleted; corrections use compensating entries." Five tables carry
-- no UPDATE grant at all, and each is a figure somebody is accountable for -- the journal, the
-- posting, the wallet entry, the recognition run and the settlement line. A correction is a new
-- row that references the old one, which is the only answer an insert-only ledger has and the
-- reason paragraph 1683 can ask for balances reconstructed from entries.
--
-- Paragraph 1694 says it from the other side: "no update/delete privilege on posted entries."
-- Check 80 compares the whole column list per table *and per role* against this block, because
-- MOD-010's review showed that a hand-written list of the columns that matter is not a pin.

GRANT SELECT, INSERT ON plt01.led_accounts TO veyro_cp_app, veyro_cp_worker;
-- An account's kind, its currency and its scope do not move: re-pointing a `liability` at an
-- `asset` would silently invert every balance ever read from it, and changing the currency
-- would make the existing postings unaddable. Only the retirement does.
GRANT UPDATE (display_name, status, retired_at, retired_by, retire_correlation_id)
    ON plt01.led_accounts TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.led_periods TO veyro_cp_app, veyro_cp_worker;
-- A period's dates and its key are derived from the month and never move. The lifecycle does,
-- which is what closing and reopening are.
GRANT UPDATE (status, closed_at, closed_by, close_correlation_id, reopened_at,
              reopened_by, reopen_reason, reopen_correlation_id)
    ON plt01.led_periods TO veyro_cp_app, veyro_cp_worker;

-- **The journal has no UPDATE grant at all**, and neither has the posting. This is the whole
-- of paragraph 1685: what was posted is what was posted. A journal recorded in error is
-- reversed by a `correction` journal that names it, which leaves both visible -- and the pair
-- is what makes "explain this balance" answerable, where an edit would have left a figure with
-- no history.
GRANT SELECT, INSERT ON plt01.led_journals TO veyro_cp_app, veyro_cp_worker;
GRANT SELECT, INSERT ON plt01.led_postings TO veyro_cp_app, veyro_cp_worker;

-- The person and the currency are the wallet's identity and nothing else is on the row, so
-- there is no UPDATE grant: see the deletion recorded at the table.
GRANT SELECT, INSERT ON plt01.led_wallets TO veyro_cp_app, veyro_cp_worker;

-- **A wallet entry has no UPDATE grant at all.** The balance is their sum, so an editable
-- entry is an editable balance -- and a member whose wallet could be edited has no way to
-- argue about what it held last week. An expiry is evaluated at read time rather than written
-- over the row, which is also why nothing here needs to move.
GRANT SELECT, INSERT ON plt01.led_wallet_entries TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.led_recognition_schedules
    TO veyro_cp_app, veyro_cp_worker;
-- **The basis, the total and the two accounts carry no UPDATE grant.** Changing the basis of a
-- schedule already running would re-derive every past recognition against a different rule and
-- leave the postings that were made unexplainable; changing the total would mean money
-- recognised against an amount nobody sold. Only the close moves.
GRANT UPDATE (status, closed_at, closed_by, close_reason, close_correlation_id)
    ON plt01.led_recognition_schedules TO veyro_cp_app, veyro_cp_worker;

-- **A recognition run has no UPDATE grant at all.** It is the record of a figure moved from a
-- liability to revenue, and the three numbers on it have to keep agreeing with each other --
-- which the `adds_up` constraint makes true at insert and the missing grant keeps true.
GRANT SELECT, INSERT ON plt01.led_recognition_runs TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.led_settlements TO veyro_cp_app, veyro_cp_worker;
-- The file's own figures and its batch reference are what was imported. Only the reconciliation
-- state moves.
GRANT UPDATE (status) ON plt01.led_settlements TO veyro_cp_app, veyro_cp_worker;

-- **A settlement line has no UPDATE grant at all**, verdict included. Re-running a match that
-- reached a different answer is a reconciliation case rather than a rewritten row: the first
-- verdict is evidence of what the file and the ledger said at import, and overwriting it
-- destroys the only record that they ever disagreed.
GRANT SELECT, INSERT ON plt01.led_settlement_lines TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.led_reconciliation_cases TO veyro_cp_app, veyro_cp_worker;
-- The two figures that disagree are the case. Only its journey and its resolution move.
GRANT UPDATE (status, resolution, resolution_journal_id, resolved_at, resolved_by,
              resolve_correlation_id)
    ON plt01.led_reconciliation_cases TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.led_cash_sessions TO veyro_cp_app, veyro_cp_worker;
-- The drawer, its account and its opening float are fixed when the session opens. The close
-- writes the two counts, the variance reason and the journal, once.
GRANT UPDATE (status, expected_minor, counted_minor, variance_reason, closed_at,
              closed_by, close_correlation_id, variance_journal_id)
    ON plt01.led_cash_sessions TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.led_deposits TO veyro_cp_app, veyro_cp_worker;
-- What was declared and which accounts it moves between are fixed. What the bank said arrives
-- days later, which is the only thing that moves.
GRANT UPDATE (status, credited_minor, credited_on, bank_reference, confirm_journal_id,
              confirmed_at, confirmed_by, confirm_correlation_id)
    ON plt01.led_deposits TO veyro_cp_app, veyro_cp_worker;

-- A deposit's composition is settled when the bag is sealed.
GRANT SELECT, INSERT ON plt01.led_deposit_sessions TO veyro_cp_app, veyro_cp_worker;

-- An export is a record of what was sent, and nothing about it moves. What needed a trigger is
-- the obligation *before* the insert -- the period has to be closed -- which is above.
GRANT SELECT, INSERT ON plt01.led_exports TO veyro_cp_app, veyro_cp_worker;
