"""MOD-018 COM-04: the I/O, and the one thing about it that is load-bearing.

**`post_journal` takes a connection, not a pool.** This is MOD-010's `append_event` argument
applied to money, and it is the whole design: a payment recorded in `fin_payments` without its
journal, or a journal without its payment, is a state nothing can reconcile -- and the only way
to mean "these commit together" is to run the posting inside the caller's transaction on the
caller's connection. Every other service in this build takes a pool and opens its own
`tenant_scope`; a version of this one that did the same would read identically and guarantee
nothing.

**A pool-taking convenience wrapper around it is the bug**, which is why the one that exists is
called `post_journal_in_its_own_transaction` and is correct only where there is no state change
to be atomic with -- a manual journal somebody typed, a correction, a recognition run.

Three other things to know before extending it:

* **Nothing stores a balance.** COM-04-R07. A balance is a sum over postings and a wallet
  balance is a sum over entries, computed where it is needed. The cost is a query per read and
  the benefit is that a statement and a balance cannot disagree, because they are the same sum
  read to different depths.

* **A period is opened by the first posting into it.** There is no worker runtime here to open
  months ahead, and a build where the first sale of December fails because nobody opened
  December is worse than one that opens it. The row records who opened it, so "who opened this
  period" stays answerable; the *close* is the control, and that is a deliberate command.

* **A refusal that had to be recorded is raised after the commit.** `tenant_scope` rolls back
  when the block raises, so a path that writes a reconciliation case and then refuses would
  throw the case away. The `_settled` shape is MOD-007's, MOD-008's, MOD-013's and MOD-017's,
  and it is used here wherever a refusal leaves evidence.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from psycopg import Connection, errors

from app.db import Pool, tenant_scope
from app.errors import Conflict, InvalidRequest, NotFound
from app.events import service as events
from app.ledger import accounts, periods, recognition, settlement, wallet


def _now() -> datetime:
    return datetime.now(UTC)


def _today() -> date:
    return _now().date()


def _check_name(error: errors.CheckViolation) -> str:
    name = getattr(error.diag, "constraint_name", None)
    return str(name) if name else "constraint_violation"


def _fk_subject(error: errors.ForeignKeyViolation) -> str:
    """Which parent a foreign-key violation was about.

    A bare `not_found` on a command naming five parents tells the caller nothing, and guessing
    the commonest one is how somebody spends an afternoon on the wrong id. MOD-017's helper,
    with this module's parents.
    """
    name = str(getattr(error.diag, "constraint_name", "") or "")
    for fragment, subject in (
        ("account", "ledger_account_not_found"),
        ("period", "financial_period_not_found"),
        ("journal", "journal_not_found"),
        ("wallet", "wallet_not_found"),
        ("schedule", "recognition_schedule_not_found"),
        ("settlement", "settlement_not_found"),
        ("session", "cash_session_not_found"),
        ("deposit", "deposit_not_found"),
        ("payment", "payment_not_found"),
        ("refund", "refund_not_found"),
        ("person", "person_not_found"),
        ("legal_entit", "legal_entity_not_found"),
        ("location", "location_not_found"),
        ("brand", "brand_not_found"),
    ):
        if fragment in name:
            return subject
    return "a_referenced_row_was_not_found"


def _append(
    conn: Connection[Any], tenant_id: str, event_type: str, aggregate_type: str,
    aggregate_id: str, payload: dict[str, Any], *, correlation_id: str, actor_id: str,
) -> None:
    """Append an event in the caller's transaction, which is MOD-010's whole design."""
    events.append_event(
        conn, tenant_id, event_type=event_type, aggregate_type=aggregate_type,
        aggregate_id=aggregate_id, payload=payload, correlation_id=correlation_id,
        actor_id=actor_id)


# ------------------------------------------------------------------ the chart of accounts

def open_account(
    pool: Pool, tenant_id: str, *, account_code: str, account_kind: str,
    display_name: str, currency: str, actor_id: str, correlation_id: str,
    brand_id: str | None = None, location_id: str | None = None,
    legal_entity_id: str | None = None,
) -> dict[str, Any]:
    """Create one account in this tenant's chart.

    `account_kind` comes from `app.ledger.accounts.KINDS` and is checked against the catalogue
    here, so a caller gets a sentence rather than a constraint name -- and the shape CHECK on
    the column is what makes it true of rows written by anything else.
    """
    if account_kind not in accounts.KIND_BY_KEY:
        raise InvalidRequest(f"unknown_account_kind_{account_kind}")
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.led_accounts
                    (tenant_id, account_code, account_kind, display_name, currency,
                     brand_id, location_id, legal_entity_id, created_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING account_id
                """,
                (tenant_id, account_code.upper(), account_kind, display_name,
                 currency.upper(), brand_id, location_id, legal_entity_id, actor_id,
                 correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_account_code_already_exists") from None
        except errors.ForeignKeyViolation as e:
            raise NotFound(_fk_subject(e)) from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
    kind = accounts.KIND_BY_KEY[account_kind]
    return {"account_id": str(row[0]), "account_code": account_code.upper(),
            "account_kind": account_kind, "account_class": kind.account_class,
            "normal_side": accounts.normal_side(account_kind),
            "currency": currency.upper()}


def retire_account(
    pool: Pool, tenant_id: str, account_id: str, *, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Stop an account being posted to. Its postings stay exactly where they are.

    **Retired rather than deleted**, because a balance is a sum over postings and deleting the
    account would make every past journal that used it unreadable. A retired account still has
    a balance and still appears in a trial balance; what it does not accept is a new posting.
    """
    moment = _now()
    with tenant_scope(pool, tenant_id) as conn:
        current = conn.execute(
            "SELECT status FROM plt01.led_accounts WHERE account_id = %s FOR UPDATE",
            (account_id,),
        ).fetchone()
        if current is None:
            raise NotFound("ledger_account_not_found")
        if str(current[0]) == "retired":
            return {"account_id": account_id, "status": "retired", "repeated": True}
        conn.execute(
            "UPDATE plt01.led_accounts SET status = 'retired', retired_at = %s,"
            " retired_by = %s, retire_correlation_id = %s"
            " WHERE account_id = %s AND status = 'active'",
            (moment, actor_id, correlation_id, account_id))
    return {"account_id": account_id, "status": "retired", "repeated": False}


def _account(conn: Connection[Any], account_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT account_kind, currency, status, account_code, location_id,"
        " legal_entity_id FROM plt01.led_accounts WHERE account_id = %s",
        (account_id,),
    ).fetchone()
    if row is None:
        raise NotFound("ledger_account_not_found")
    return {"account_kind": str(row[0]), "currency": str(row[1]),
            "status": str(row[2]), "account_code": str(row[3]),
            "location_id": str(row[4]) if row[4] else None,
            "legal_entity_id": str(row[5]) if row[5] else None}


def _account_of_kind(
    conn: Connection[Any], account_id: str, kinds: tuple[str, ...], *, currency: str,
    role: str,
) -> dict[str, Any]:
    """An account the caller named, checked for what it is before anything posts to it.

    **This is one helper because the same omission happened at five sites.** Three commands
    checked the kind of the accounts they named and three did not, and the one that mattered
    most was the till close: `suspense_account_id` was unchecked, so the module's only routine
    AAL-1 permission posted an arbitrary amount between the drawer and *any* account in the
    chart -- a reviewer cleared every member's outstanding receivable with it, through the
    permission whose written justification for being routine is that the variance goes to
    suspense and opens a case. The identical movement through `POST /ledger/journals` is
    refused, because that permission is financial and needs a step-up.
    """
    account = _account(conn, account_id)
    if account["account_kind"] not in kinds:
        raise Conflict(
            f"the account {account['account_code']} is {account['account_kind']} and the "
            f"{role} of this posting needs {' or '.join(kinds)}")
    if account["status"] != "active":
        raise Conflict(f"the account {account['account_code']} is retired")
    if account["currency"] != currency.upper():
        raise Conflict(
            f"the account {account['account_code']} is in {account['currency']}")
    return account


# ------------------------------------------------------------------ financial periods

def _period_for(
    conn: Connection[Any], tenant_id: str, *, legal_entity_id: str, posted_on: date,
    actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """The period a date belongs to, opened if it does not exist yet.

    **Opened by the first posting into it**, because there is no worker here to open months
    ahead and a build where the first sale of December fails because nobody opened December is
    worse than one that opens it. The row records who opened it, so the question stays
    answerable; the *close* is the control and that is a deliberate command.

    **A month before one already closed is not opened.** COM-04-R06's lock is enforced per
    period *row*, and a month nobody ever posted into has no row and therefore cannot have been
    closed -- so a tenant whose 2026 books were filed had every earlier month wide open, and a
    posting into one of them changed the entity's cumulative position after the figures went
    out. That is the whole thing the lock exists to prevent, reached without touching a closed
    period at all.
    """
    try:
        key = periods.period_key_for(posted_on)
        bounds = periods.month_bounds(key)
    except accounts.LedgerError as e:
        # The one `month_bounds` call site in this file that did not wrap it, which made a
        # mistyped year a 500 on four money routes -- including `/finance/invoices`, and only
        # for tenants that had set a chart up, since the bridge skips before this without one.
        raise InvalidRequest(str(e)) from None
    row = conn.execute(
        "SELECT period_id, period_key, starts_on, ends_on, status FROM plt01.led_periods"
        " WHERE legal_entity_id = %s AND period_key = %s",
        (legal_entity_id, key),
    ).fetchone()
    if row is None:
        filed = conn.execute(
            "SELECT period_key FROM plt01.led_periods"
            " WHERE legal_entity_id = %s AND closed_at IS NOT NULL AND starts_on > %s"
            " ORDER BY starts_on LIMIT 1",
            (legal_entity_id, bounds[0]),
        ).fetchone()
        if filed is not None:
            raise Conflict(
                f"the period {key} was never opened and {filed[0]} has already been "
                f"closed; post the correction in an open period and reference the original")
        starts_on, ends_on = bounds
        try:
            created = conn.execute(
                """
                INSERT INTO plt01.led_periods
                    (tenant_id, legal_entity_id, period_key, starts_on, ends_on,
                     created_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, legal_entity_id, period_key) DO NOTHING
                RETURNING period_id
                """,
                (tenant_id, legal_entity_id, key, starts_on, ends_on, actor_id,
                 correlation_id),
            ).fetchone()
        except errors.ForeignKeyViolation as e:
            raise NotFound(_fk_subject(e)) from None
        if created is None:
            # Another transaction opened it between the read and the insert. `DO NOTHING`
            # then a re-read, never a caught `UniqueViolation`: a caught one leaves the
            # transaction aborted and the SELECT after it raises `InFailedSqlTransaction`,
            # which MOD-013 and MOD-016 each learned the same way.
            row = conn.execute(
                "SELECT period_id, period_key, starts_on, ends_on, status"
                " FROM plt01.led_periods WHERE legal_entity_id = %s AND period_key = %s",
                (legal_entity_id, key),
            ).fetchone()
            assert row is not None
        else:
            return {"period_id": str(created[0]), "period_key": key,
                    "starts_on": starts_on, "ends_on": ends_on, "status": "open",
                    "opened_here": True}
    assert row is not None
    return {"period_id": str(row[0]), "period_key": str(row[1]), "starts_on": row[2],
            "ends_on": row[3], "status": str(row[4]), "opened_here": False}


def _period_admitting(
    conn: Connection[Any], tenant_id: str, *, legal_entity_id: str, posted_on: date,
    purpose: str, actor_id: str, correlation_id: str, fall_back_to_open: bool,
) -> tuple[dict[str, Any], date]:
    """The period a journal goes in, and the date it is posted on.

    **Without the fallback, beginning the month-end close stopped the product.** `closing` is a
    state an accountant enters deliberately -- it is the whole reason the state exists -- and
    the bridge runs inside MOD-017's transaction, so a refusal rolled the business write back:
    no invoice could be issued, no serial allocated, and a card the provider had already
    charged could not be recorded, which is how a member gets dunned for a payment that
    succeeded. A close begun on the 28th shut the till for four days.

    So a *bridged* posting walks forward to the first period that admits it, which is what an
    accountant means by "it goes in the next open period": the document keeps its own date and
    the journal says when it was posted. A journal posted by hand does not walk -- it is
    refused, loudly, because somebody is there to read the refusal and choose.
    """
    at = posted_on
    for _ in range(13):
        period = _period_for(
            conn, tenant_id, legal_entity_id=legal_entity_id, posted_on=at,
            actor_id=actor_id, correlation_id=correlation_id)
        # **Checked here and by the trigger, for the same reason as the balance.** The period's
        # status is a fact about another row, so this is the readable refusal and the trigger
        # is the one that holds for a writer this service is not.
        try:
            periods.check_postable(
                periods.Period(period["period_key"], period["starts_on"],
                               period["ends_on"], period["status"]),
                purpose)
        except accounts.LedgerError as e:
            if not fall_back_to_open:
                raise Conflict(str(e)) from None
            at = period["ends_on"] + timedelta(days=1)
            continue
        return period, at
    raise Conflict("no_period_within_a_year_admits_this_posting")


def close_period(
    pool: Pool, tenant_id: str, *, legal_entity_id: str, period_key: str,
    actor_id: str, correlation_id: str, target: str = "closed",
) -> dict[str, Any]:
    """Move a period along its lifecycle. COM-04-R06's lock control.

    `closing` stops ordinary trade and admits the close's own work -- recognition to post,
    settlements to match, variances to explain. `closed` admits nothing, and the correction for
    anything discovered afterwards is a posting in the open period that references the original.

    **A reopening is its own target with its own written reason**, because it is the one act
    that lets a filed figure change. A statement should be able to say "this month was reopened
    on the fourteenth" rather than silently differ from the one that was filed.
    """
    moment = _now()
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT period_id, status FROM plt01.led_periods"
            " WHERE legal_entity_id = %s AND period_key = %s FOR UPDATE",
            (legal_entity_id, period_key),
        ).fetchone()
        if row is None:
            raise NotFound("financial_period_not_found")
        period_id, current = str(row[0]), str(row[1])
        if current == target:
            return {"period_id": period_id, "period_key": period_key,
                    "status": current, "repeated": True}
        try:
            periods.check_transition(current, target)
        except accounts.LedgerError as e:
            raise Conflict(str(e)) from None
        if target == "closed":
            # **What is still unanswered is reported, not blocked.** A period with open
            # reconciliation cases can be closed -- a tenant that could not close a month
            # because of a 2.00 till variance would stop reconciling rather than stop closing
            # -- and the count comes back so the closer knows what they are signing off.
            unresolved = conn.execute(
                "SELECT count(*) FROM plt01.led_reconciliation_cases"
                " WHERE legal_entity_id = %s AND status IN ('open', 'investigating')",
                (legal_entity_id,),
            ).fetchone()
            conn.execute(
                "UPDATE plt01.led_periods SET status = 'closed', closed_at = %s,"
                " closed_by = %s, close_correlation_id = %s"
                " WHERE period_id = %s AND status = %s",
                (moment, actor_id, correlation_id, period_id, current))
            return {"period_id": period_id, "period_key": period_key,
                    "status": "closed", "repeated": False,
                    "unresolved_cases": int(unresolved[0]) if unresolved else 0}
        conn.execute(
            "UPDATE plt01.led_periods SET status = %s WHERE period_id = %s AND status = %s",
            (target, period_id, current))
    return {"period_id": period_id, "period_key": period_key, "status": target,
            "repeated": False}


def reopen_period(
    pool: Pool, tenant_id: str, *, legal_entity_id: str, period_key: str, reason: str,
    actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Reopen a closed period, with a reason that goes on the row.

    Separate from `close_period` because it is a different act with a different permission: one
    makes a figure final and the other un-makes it, and an auditor asks about the second.
    """
    if not reason.strip():
        raise InvalidRequest("reopening_a_closed_period_states_why")
    moment = _now()
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT period_id, status FROM plt01.led_periods"
            " WHERE legal_entity_id = %s AND period_key = %s FOR UPDATE",
            (legal_entity_id, period_key),
        ).fetchone()
        if row is None:
            raise NotFound("financial_period_not_found")
        period_id, current = str(row[0]), str(row[1])
        if current == "reopened":
            return {"period_id": period_id, "period_key": period_key,
                    "status": current, "repeated": True}
        try:
            periods.check_transition(current, "reopened")
        except accounts.LedgerError as e:
            raise Conflict(str(e)) from None
        try:
            conn.execute(
                "UPDATE plt01.led_periods SET status = 'reopened', reopened_at = %s,"
                " reopened_by = %s, reopen_reason = %s, reopen_correlation_id = %s"
                " WHERE period_id = %s AND status = %s",
                (moment, actor_id, reason.strip(), correlation_id, period_id, current))
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
    return {"period_id": period_id, "period_key": period_key, "status": "reopened",
            "repeated": False}


# ------------------------------------------------------------------ journals and postings

def post_journal(
    conn: Connection[Any], tenant_id: str, *, legal_entity_id: str,
    lines: list[dict[str, Any]], posted_on: date, currency: str, source_kind: str,
    source_ref: str, description: str, idempotency_key: str, actor_id: str,
    correlation_id: str, purpose: str = "trade", fall_back_to_open: bool = False,
    corrects_journal_id: str | None = None, correction_reason: str | None = None,
) -> dict[str, Any]:
    """PostJournal. **Takes a connection, because a posting commits with what caused it.**

    Paragraph 105's requirement for state and outbox, applied to money: a payment recorded in
    `fin_payments` without its journal is a balance the ledger does not know about, and a
    journal without its payment is money the ledger invented. The only way to mean "together"
    is the caller's own transaction.

    **Balanced here and at commit.** `accounts.check_balanced` refuses before any row is
    written, which gives a readable error and costs one pass over a list; the deferred
    constraint trigger on `led_postings` makes it true of rows written by anything else. Both,
    because the first is for the caller and the second is for the next service.

    Idempotent on `idempotency_key`, scoped to this legal entity -- MOD-017's finding, where a
    key reused across two payers returned the other payer's invoice and reported a successful
    repeat.
    """
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    if not description.strip():
        raise InvalidRequest("a_journal_describes_what_it_is")
    if purpose not in periods.PURPOSES:
        raise InvalidRequest(f"unknown_journal_purpose_{purpose}")
    # **The purpose agrees with the source kind, or it is `close`.** `purpose` decides whether
    # a period under close admits the journal, and with it free a caller sent the identical
    # trade in as `settlement` after being refused as `trade`. Everything but `close` is
    # derivable from where the journal came from; `close` is the accountant's own accrual and
    # the route charges `finance.period.close` for it.
    derived = periods.PURPOSE_BY_SOURCE.get(source_kind, "trade")
    if purpose not in (derived, "close"):
        raise InvalidRequest(
            f"a {source_kind} journal is {derived} or close, not {purpose}")
    amounts = [int(line["amount_minor"]) for line in lines]
    try:
        accounts.check_balanced(amounts)
    except accounts.LedgerError as e:
        raise InvalidRequest(str(e)) from None
    control_total = accounts.control_total(amounts)
    existing = conn.execute(
        # **Scoped to the source kind**, because the unique key is, and because a lookup by
        # the bare key handed a caller another command's journal: a decoy keyed
        # `wallet-credit-X` was returned as the repeat of a wallet credit keyed `X`, so the
        # credit's own journal was never written and 1000.00 of refundable value existed with
        # no liability behind it.
        "SELECT journal_id, legal_entity_id, control_total_minor, currency, posted_on,"
        " purpose, source_ref FROM plt01.led_journals"
        " WHERE source_kind = %s AND idempotency_key = %s",
        (source_kind, idempotency_key.strip()),
    ).fetchone()
    if existing is not None:
        if str(existing[1]) != legal_entity_id:
            raise Conflict("this_idempotency_key_belongs_to_another_legal_entity")
        if str(existing[6]) != source_ref:
            raise Conflict("this_idempotency_key_belongs_to_another_movement")
        return {"journal_id": str(existing[0]),
                "control_total_minor": int(existing[2]), "currency": str(existing[3]),
                "posted_on": existing[4].isoformat(), "purpose": str(existing[5]),
                "period_opened": False, "repeated": True}
    period, posted_on = _period_admitting(
        conn, tenant_id, legal_entity_id=legal_entity_id, posted_on=posted_on,
        purpose=purpose, actor_id=actor_id, correlation_id=correlation_id,
        fall_back_to_open=fall_back_to_open)
    try:
        row = conn.execute(
            """
            INSERT INTO plt01.led_journals
                (tenant_id, legal_entity_id, period_id, purpose, posted_on, currency,
                 control_total_minor, source_kind, source_ref, corrects_journal_id,
                 correction_reason, description, idempotency_key, posted_by,
                 correlation_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING journal_id
            """,
            (tenant_id, legal_entity_id, period["period_id"], purpose, posted_on,
             currency.upper(), control_total, source_kind, source_ref,
             corrects_journal_id, (correction_reason or "").strip() or None,
             description.strip(), idempotency_key.strip(), actor_id, correlation_id),
        ).fetchone()
    except errors.UniqueViolation:
        raise Conflict("this_journal_was_posted_by_somebody_else") from None
    except errors.ForeignKeyViolation as e:
        raise NotFound(_fk_subject(e)) from None
    except errors.CheckViolation as e:
        raise InvalidRequest(_check_name(e)) from None
    except errors.RaiseException as e:
        # The period trigger's refusal, which is prose rather than a constraint name.
        raise Conflict(str(e).strip().splitlines()[0]) from None
    assert row is not None
    journal_id = str(row[0])
    for number, line in enumerate(lines, start=1):
        account_id = str(line["account_id"])
        account = _account(conn, account_id)
        if account["status"] != "active":
            raise Conflict(
                f"the account {account['account_code']} is retired and takes no postings")
        if account["currency"] != currency.upper():
            raise Conflict(
                f"the account {account['account_code']} is in {account['currency']} and "
                f"this journal is in {currency.upper()}")
        try:
            conn.execute(
                """
                INSERT INTO plt01.led_postings
                    (tenant_id, journal_id, account_id, amount_minor, currency,
                     subject_person_id, memo, line_number)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (tenant_id, journal_id, account_id, int(line["amount_minor"]),
                 currency.upper(), line.get("subject_person_id"),
                 (line.get("memo") or "").strip() or None, number))
        except errors.ForeignKeyViolation as e:
            raise NotFound(_fk_subject(e)) from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
    _append(conn, tenant_id, "ledger.posted", "journal", journal_id,
            {"journal_id": journal_id, "legal_entity_id": legal_entity_id,
             "purpose": purpose, "currency": currency.upper(),
             "control_total_minor": control_total, "posted_on": posted_on.isoformat(),
             "source_kind": source_kind},
            correlation_id=correlation_id, actor_id=actor_id)
    return {"journal_id": journal_id, "control_total_minor": control_total,
            "currency": currency.upper(), "posted_on": posted_on.isoformat(),
            "purpose": purpose, "period_key": period["period_key"],
            "period_opened": bool(period["opened_here"]), "repeated": False}


def post_journal_in_its_own_transaction(
    pool: Pool, tenant_id: str, **kwargs: Any,
) -> dict[str, Any]:
    """`post_journal` with a transaction of its own, for the journals that have nothing to be
    atomic *with*.

    **Named at length on purpose.** MOD-010 called the equivalent
    `append_event_in_its_own_transaction` for the same reason: a short name would get used from
    a path that has a state change to pair with, and the pairing is the whole point. Correct
    for a manual journal somebody typed, a correction, a recognition run and a settlement
    import -- each of which *is* the state change.
    """
    with tenant_scope(pool, tenant_id) as conn:
        return post_journal(conn, tenant_id, **kwargs)


def correct_journal(
    pool: Pool, tenant_id: str, journal_id: str, *, reason: str, idempotency_key: str,
    actor_id: str, correlation_id: str, posted_on: date | None = None,
) -> dict[str, Any]:
    """Reverse a posted journal with a compensating entry. Paragraph 1685's only correction.

    **Every posting is negated and nothing is edited.** The original stays exactly where it is,
    the reversal names it, and a reader asking "what happened here" sees both -- which is what
    paragraph 1688's "finance can explain every balance" needs and what an edit would have
    destroyed.

    **Dated in the open period, not in the original's.** A correction discovered in December for
    a November mistake belongs in December, because that is the period whose figures change;
    posting it into a closed November would make the filed statement wrong with nothing to say
    so. That is also why the trigger refuses it.
    """
    if not reason.strip():
        raise InvalidRequest("a_correction_states_why")
    today = posted_on or _today()
    with tenant_scope(pool, tenant_id) as conn:
        original = conn.execute(
            "SELECT legal_entity_id, currency, purpose, source_kind, source_ref,"
            " description FROM plt01.led_journals WHERE journal_id = %s",
            (journal_id,),
        ).fetchone()
        if original is None:
            raise NotFound("journal_not_found")
        if str(original[2]) == "correction":
            # **A correction of a correction is allowed and a *reversal* of one is not.** The
            # second is almost always somebody trying to undo an undo, which leaves three
            # journals and no clear position; the honest move is a fresh correction of the
            # original with a reason that says what the net effect should be.
            raise Conflict("a_correction_is_not_itself_reversed_by_another")
        already = conn.execute(
            "SELECT journal_id, idempotency_key, control_total_minor, currency, posted_on"
            " FROM plt01.led_journals WHERE corrects_journal_id = %s",
            (journal_id,),
        ).fetchone()
        if already is not None:
            # **Idempotent to the caller, not only in the table.** This command took a key and
            # ignored it on the repeat path, so a client whose request timed out after the
            # commit was told 409 for work that had succeeded -- MOD-017's own blocking
            # finding, and every sibling here returns `repeated`. A *different* key on an
            # already-corrected journal is still a refusal, because that is a second
            # correction rather than a retry of the first.
            if str(already[1]) == idempotency_key.strip():
                return {"corrects_journal_id": journal_id,
                        "journal_id": str(already[0]),
                        "control_total_minor": int(already[2]),
                        "currency": str(already[3]),
                        "posted_on": already[4].isoformat(), "purpose": "correction",
                        "period_opened": False, "repeated": True}
            raise Conflict("this_journal_has_already_been_corrected")
        postings = conn.execute(
            "SELECT account_id, amount_minor, subject_person_id, memo"
            " FROM plt01.led_postings WHERE journal_id = %s ORDER BY line_number",
            (journal_id,),
        ).fetchall()
        assert postings
        reversed_lines = [
            {"account_id": str(p[0]), "amount_minor": -int(p[1]),
             "subject_person_id": p[2],
             "memo": f"reversal: {p[3]}" if p[3] else "reversal"}
            for p in postings
        ]
        posted = post_journal(
            conn, tenant_id, legal_entity_id=str(original[0]), lines=reversed_lines,
            posted_on=today, currency=str(original[1]), purpose="correction",
            source_kind="correction", source_ref=journal_id,
            corrects_journal_id=journal_id, correction_reason=reason.strip(),
            description=f"reversal of {original[5]}",
            idempotency_key=idempotency_key, actor_id=actor_id,
            correlation_id=correlation_id)
    return {"corrects_journal_id": journal_id, **posted}


# ------------------------------------------------------------------ the member wallet

def _wallet(
    conn: Connection[Any], tenant_id: str, *, person_id: str, currency: str,
    actor_id: str, correlation_id: str, create: bool = True,
) -> dict[str, Any]:
    """The person's wallet in that currency, opened if it does not exist and `create`.

    **One per person per currency**, which the unique index enforces -- two would make "what do
    I have" answerable twice and let the spend order take from whichever the caller named.

    **An advisory lock rather than `FOR UPDATE` on the row.** The wallet row is immutable now
    -- there is no freeze and so no UPDATE grant -- and `SELECT ... FOR UPDATE` needs the
    UPDATE privilege, so the lock the debit path relies on to stop two concurrent spends each
    reading the same balance cannot be taken on the row. An advisory lock needs no table
    privilege and serialises exactly what has to be serialised.
    """
    conn.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"led_wallet:{tenant_id}:{person_id}:{currency.upper()}",))
    row = conn.execute(
        "SELECT wallet_id FROM plt01.led_wallets"
        " WHERE person_id = %s AND currency = %s",
        (person_id, currency.upper()),
    ).fetchone()
    if row is not None:
        return {"wallet_id": str(row[0]), "opened_here": False}
    if not create:
        raise NotFound("wallet_not_found")
    try:
        created = conn.execute(
            """
            INSERT INTO plt01.led_wallets
                (tenant_id, person_id, currency, created_by, correlation_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, person_id, currency) DO NOTHING
            RETURNING wallet_id
            """,
            (tenant_id, person_id, currency.upper(), actor_id, correlation_id),
        ).fetchone()
    except errors.ForeignKeyViolation as e:
        raise NotFound(_fk_subject(e)) from None
    if created is None:
        row = conn.execute(
            "SELECT wallet_id FROM plt01.led_wallets"
            " WHERE person_id = %s AND currency = %s",
            (person_id, currency.upper()),
        ).fetchone()
        assert row is not None
        return {"wallet_id": str(row[0]), "opened_here": False}
    return {"wallet_id": str(created[0]), "opened_here": True}


def _wallet_entries(
    conn: Connection[Any], wallet_id: str,
) -> list[wallet.Entry]:
    return [
        wallet.Entry(str(r[0]), int(r[1]), r[2])
        for r in conn.execute(
            "SELECT value_kind, amount_minor, expires_on FROM plt01.led_wallet_entries"
            " WHERE wallet_id = %s", (wallet_id,)).fetchall()
    ]


def _wallet_accounts(
    conn: Connection[Any], *, currency: str, kinds: set[str],
    legal_entity_id: str | None = None,
) -> dict[str, str]:
    """The liability accounts the wallet kinds post to, by kind.

    Looked up rather than passed, because a caller able to name the account could post a
    promotional credit into the refundable liability -- which is precisely the distinction
    paragraph 1686 calls a Critical Control, defeated by a body field.
    """
    wanted = {wallet.LIABILITY_ACCOUNT[kind] for kind in kinds}
    found: dict[str, str] = {}
    for row in conn.execute(
        # Ordered and entity-preferring, for `chart_for`'s reason: an unordered pick made the
        # liability an artefact of scan order.
        "SELECT account_kind, account_id FROM plt01.led_accounts"
        " WHERE account_kind = ANY(%s) AND currency = %s AND status = 'active'"
        " AND location_id IS NULL"
        " AND (legal_entity_id IS NULL OR legal_entity_id = %s)"
        " ORDER BY account_kind, (legal_entity_id IS NULL), account_code",
        (sorted(wanted), currency.upper(), legal_entity_id),
    ).fetchall():
        found.setdefault(str(row[0]), str(row[1]))
    missing = wanted - set(found)
    if missing:
        raise Conflict(
            "this tenant has no active "
            + ", ".join(sorted(missing))
            + f" account in {currency.upper()}; open the chart first")
    return {kind: found[wallet.LIABILITY_ACCOUNT[kind]] for kind in kinds}


def credit_wallet(
    pool: Pool, tenant_id: str, *, person_id: str, value_kind: str, amount_minor: int,
    currency: str, reason: str, source_kind: str, idempotency_key: str,
    legal_entity_id: str, counterpart_account_id: str, actor_id: str,
    correlation_id: str, expires_on: date | None = None,
    source_ref: str | None = None, at: date | None = None,
) -> dict[str, Any]:
    """CreditWallet. The entry and its journal, in one transaction.

    **A wallet credit is a liability going up and something else moving in the other
    direction**, and what that something else is depends on why: cash the member paid in moves
    from a cash or provider account, and value the tenant gave away is a marketing expense.
    So the counterpart is named by the caller and the *liability* side is derived from the
    value kind -- the asymmetry is deliberate, because the liability is the half paragraph 1686
    makes a Critical Control and the half a caller must not be able to choose.
    """
    today = at or _today()
    if not reason.strip():
        raise InvalidRequest("a_wallet_credit_states_why")
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    try:
        wallet.check_credit(value_kind=value_kind, amount_minor=amount_minor,
                            expires_on=expires_on, at=today)
    except accounts.LedgerError as e:
        raise InvalidRequest(str(e)) from None
    with tenant_scope(pool, tenant_id) as conn:
        prior = conn.execute(
            "SELECT entry_id, wallet_id, value_kind, amount_minor"
            " FROM plt01.led_wallet_entries WHERE idempotency_key = %s",
            (idempotency_key.strip(),),
        ).fetchone()
        if prior is not None:
            held = _wallet(conn, tenant_id, person_id=person_id, currency=currency,
                           actor_id=actor_id, correlation_id=correlation_id, create=False)
            if str(prior[1]) != held["wallet_id"]:
                raise Conflict("this_idempotency_key_belongs_to_another_wallet")
            return {"entry_id": str(prior[0]), "wallet_id": held["wallet_id"],
                    "value_kind": str(prior[2]), "amount_minor": int(prior[3]),
                    "repeated": True}
        held = _wallet(conn, tenant_id, person_id=person_id, currency=currency,
                       actor_id=actor_id, correlation_id=correlation_id)
        # **Where the value came from, not wherever the caller pointed.** Unchecked, a
        # promotional giveaway was charged to `receivable` -- overstating the tenant's debtors
        # by every credit ever issued -- and a credit whose counterpart was the wallet
        # liability itself created 500.00 of refundable member value with nothing on the
        # balance sheet, because `sum(amount_minor) = 0` is satisfied by +N and -N on one
        # account.
        _account_of_kind(conn, counterpart_account_id, WALLET_COUNTERPART,
                         currency=currency, role="counterpart")
        liability = _wallet_accounts(conn, currency=currency, kinds={value_kind},
                                     legal_entity_id=legal_entity_id)
        posted = post_journal(
            conn, tenant_id, legal_entity_id=legal_entity_id,
            lines=[
                {"account_id": counterpart_account_id, "amount_minor": amount_minor,
                 "subject_person_id": person_id, "memo": reason.strip()},
                {"account_id": liability[value_kind], "amount_minor": -amount_minor,
                 "subject_person_id": person_id, "memo": reason.strip()},
            ],
            posted_on=today, currency=currency, source_kind="wallet",
            source_ref=held["wallet_id"], description=f"wallet credit: {reason.strip()}",
            idempotency_key=f"wallet-credit-{idempotency_key.strip()}",
            actor_id=actor_id, correlation_id=correlation_id)
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.led_wallet_entries
                    (tenant_id, wallet_id, value_kind, amount_minor, expires_on,
                     journal_id, reason, source_kind, source_ref, idempotency_key,
                     actor_id, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING entry_id
                """,
                (tenant_id, held["wallet_id"], value_kind, amount_minor, expires_on,
                 posted["journal_id"], reason.strip(), source_kind, source_ref,
                 idempotency_key.strip(), actor_id, correlation_id),
            ).fetchone()
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        entry_id = str(row[0])
        balance = wallet.balances(_wallet_entries(conn, held["wallet_id"]), at=today)
        _append(conn, tenant_id, "wallet.credited", "wallet", held["wallet_id"],
                {"wallet_id": held["wallet_id"], "person_id": person_id,
                 "value_kind": value_kind, "amount_minor": amount_minor,
                 "currency": currency.upper(), "journal_id": posted["journal_id"]},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"entry_id": entry_id, "wallet_id": held["wallet_id"],
            "value_kind": value_kind, "amount_minor": amount_minor,
            "journal_id": posted["journal_id"], "balances": balance,
            "spendable_minor": sum(balance.values()), "repeated": False}


def debit_wallet(
    pool: Pool, tenant_id: str, *, person_id: str, amount_minor: int, currency: str,
    reason: str, idempotency_key: str, legal_entity_id: str,
    counterpart_account_id: str, actor_id: str, correlation_id: str,
    source_kind: str = "spend", source_ref: str | None = None, at: date | None = None,
) -> dict[str, Any]:
    """DebitWallet. **The caller does not choose which value is spent.**

    `wallet.plan_debit` decides, in `SPEND_ORDER`: promotional first because it expires and is
    worth nothing lapsed, cash last because cash is the only kind a member can ask for back.
    A caller able to name the kind would be able to spend the refundable balance first and
    leave the member holding value they can never get back -- which is the same shape as every
    "derive, never accept" finding in this build, applied to the member's money.

    One wallet entry per kind spent, each with its own journal line, because the two liabilities
    are different accounts and a single line would post to one of them for both.
    """
    today = at or _today()
    if not reason.strip():
        raise InvalidRequest("a_wallet_debit_states_why")
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    with tenant_scope(pool, tenant_id) as conn:
        held = _wallet(conn, tenant_id, person_id=person_id, currency=currency,
                       actor_id=actor_id, correlation_id=correlation_id, create=False)
        prior = conn.execute(
            "SELECT entry_id, wallet_id, value_kind, amount_minor"
            # **`starts_with`, not `LIKE`.** The key is caller text and was interpolated
            # into a pattern, so a debit keyed `%` was answered 201 `repeated: True` quoting
            # the previous sale's figure -- a till handed over 90.00 of goods for 1.00 of
            # wallet value -- and a legitimate key holding `%` or `_` made the day's second
            # sale free.
            " FROM plt01.led_wallet_entries"
            " WHERE starts_with(idempotency_key, %s)",
            (f"{idempotency_key.strip()}:",),
        ).fetchall()
        if prior:
            if any(str(p[1]) != held["wallet_id"] for p in prior):
                raise Conflict("this_idempotency_key_belongs_to_another_wallet")
            return {"wallet_id": held["wallet_id"], "repeated": True,
                    "spent": [{"value_kind": str(p[2]),
                               "amount_minor": -int(p[3])} for p in prior],
                    "amount_minor": -sum(int(p[3]) for p in prior)}
        _account_of_kind(conn, counterpart_account_id, WALLET_COUNTERPART,
                         currency=currency, role="counterpart")
        entries = _wallet_entries(conn, held["wallet_id"])
        try:
            plan = wallet.plan_debit(entries, amount_minor=amount_minor, at=today)
        except accounts.LedgerError as e:
            raise Conflict(str(e)) from None
        liability = _wallet_accounts(
            conn, currency=currency, kinds={spend.value_kind for spend in plan},
            legal_entity_id=legal_entity_id)
        lines: list[dict[str, Any]] = [
            {"account_id": counterpart_account_id, "amount_minor": -amount_minor,
             "subject_person_id": person_id, "memo": reason.strip()},
        ]
        lines.extend(
            {"account_id": liability[spend.value_kind],
             "amount_minor": spend.amount_minor,
             "subject_person_id": person_id,
             "memo": f"{spend.value_kind}: {reason.strip()}"}
            for spend in plan)
        posted = post_journal(
            conn, tenant_id, legal_entity_id=legal_entity_id, lines=lines,
            posted_on=today, currency=currency, source_kind="wallet",
            source_ref=held["wallet_id"], description=f"wallet debit: {reason.strip()}",
            idempotency_key=f"wallet-debit-{idempotency_key.strip()}",
            actor_id=actor_id, correlation_id=correlation_id)
        for spend in plan:
            try:
                conn.execute(
                    """
                    INSERT INTO plt01.led_wallet_entries
                        (tenant_id, wallet_id, value_kind, amount_minor, journal_id,
                         reason, source_kind, source_ref, idempotency_key, actor_id,
                         correlation_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (tenant_id, held["wallet_id"], spend.value_kind,
                     -spend.amount_minor, posted["journal_id"], reason.strip(),
                     source_kind, source_ref,
                     f"{idempotency_key.strip()}:{spend.value_kind}", actor_id,
                     correlation_id))
            except errors.CheckViolation as e:
                raise InvalidRequest(_check_name(e)) from None
        balance = wallet.balances(_wallet_entries(conn, held["wallet_id"]), at=today)
        _append(conn, tenant_id, "wallet.debited", "wallet", held["wallet_id"],
                {"wallet_id": held["wallet_id"], "person_id": person_id,
                 "amount_minor": amount_minor, "currency": currency.upper(),
                 "journal_id": posted["journal_id"]},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"wallet_id": held["wallet_id"], "amount_minor": amount_minor,
            "journal_id": posted["journal_id"],
            "spent": [{"value_kind": s.value_kind, "amount_minor": s.amount_minor}
                      for s in plan],
            "balances": balance, "spendable_minor": sum(balance.values()),
            "repeated": False}


def wallet_statement(
    pool: Pool, tenant_id: str, *, person_id: str, currency: str,
    at: date | None = None,
) -> dict[str, Any]:
    """COM-04-R07's statement, reconstructed from the entries.

    **The running balance is computed here rather than stored**, so a statement and a balance
    cannot disagree: they are the same sum read to different depths. The lapsed entries are
    returned marked rather than dropped, because "where did my 10.00 go" is the question a
    member actually asks and a statement that silently omitted the expiry cannot answer it.
    """
    today = at or _today()
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT wallet_id FROM plt01.led_wallets"
            " WHERE person_id = %s AND currency = %s",
            (person_id, currency.upper()),
        ).fetchone()
        if row is None:
            raise NotFound("wallet_not_found")
        wallet_id = str(row[0])
        rows = conn.execute(
            "SELECT occurred_at, value_kind, amount_minor, expires_on, reason"
            " FROM plt01.led_wallet_entries WHERE wallet_id = %s ORDER BY occurred_at",
            (wallet_id,),
        ).fetchall()
    entries = [wallet.Entry(str(r[1]), int(r[2]), r[3]) for r in rows]
    held = wallet.balances(entries, at=today)
    return {
        "wallet_id": wallet_id, "person_id": person_id, "currency": currency.upper(),
        "as_of": today.isoformat(),
        "balances": held, "spendable_minor": sum(held.values()),
        "refundable_minor": wallet.refundable(entries, at=today),
        "lines": wallet.statement_lines(
            [(r[0], wallet.Entry(str(r[1]), int(r[2]), r[3]), str(r[4])) for r in rows],
            at=today),
    }


# ------------------------------------------------------------------ revenue recognition

def open_recognition_schedule(
    pool: Pool, tenant_id: str, *, legal_entity_id: str, source_kind: str,
    source_ref: str, basis: str, total_minor: int, currency: str,
    unearned_account_id: str, revenue_account_id: str, actor_id: str,
    correlation_id: str, subject_person_id: str | None = None,
    starts_on: date | None = None, ends_on: date | None = None,
    units_total: int | None = None,
) -> dict[str, Any]:
    """Declare how a sale earns. Paragraph 1695.

    **This does not post anything.** The cash and the unearned-revenue liability are posted by
    whatever took the money -- that is the state change the journal has to be atomic with --
    and this records the rule by which the liability becomes revenue. A schedule that posted on
    creation would be a second place the opening entry could come from.
    """
    try:
        recognition.check_schedule(recognition.Schedule(
            basis=basis, total_minor=total_minor, currency=currency.upper(),
            starts_on=starts_on, ends_on=ends_on, units_total=units_total))
    except accounts.LedgerError as e:
        raise InvalidRequest(str(e)) from None
    with tenant_scope(pool, tenant_id) as conn:
        for account_id, expected in (
            (unearned_account_id, "unearned_revenue"),
            (revenue_account_id, "revenue"),
        ):
            account = _account(conn, account_id)
            # **The accounts are checked for kind, not just for existence.** A schedule that
            # moved money from one revenue account to another would recognise nothing and read
            # as though it had -- MOD-017's "a lookup that proves something exists does not
            # authorise what you do next", applied to a chart.
            if account["account_kind"] != expected:
                raise Conflict(
                    f"the account {account['account_code']} is "
                    f"{account['account_kind']} and this side needs {expected}")
            if account["currency"] != currency.upper():
                raise Conflict(
                    f"the account {account['account_code']} is in {account['currency']}")
            if account["status"] != "active":
                raise Conflict(f"the account {account['account_code']} is retired")
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.led_recognition_schedules
                    (tenant_id, legal_entity_id, source_kind, source_ref,
                     subject_person_id, basis, total_minor, currency, starts_on, ends_on,
                     units_total, unearned_account_id, revenue_account_id, created_by,
                     correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING schedule_id
                """,
                (tenant_id, legal_entity_id, source_kind, source_ref, subject_person_id,
                 basis, total_minor, currency.upper(), starts_on, ends_on, units_total,
                 unearned_account_id, revenue_account_id, actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_sale_already_has_a_recognition_schedule") from None
        except errors.ForeignKeyViolation as e:
            raise NotFound(_fk_subject(e)) from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
    return {"schedule_id": str(row[0]), "basis": basis, "total_minor": total_minor,
            "currency": currency.upper(), "status": "active"}


def _recognised(conn: Connection[Any], schedule_id: str) -> int:
    """What has been recognised against a schedule: a sum over the runs, never a column."""
    row = conn.execute(
        "SELECT coalesce(sum(amount_minor), 0) FROM plt01.led_recognition_runs"
        " WHERE schedule_id = %s",
        (schedule_id,),
    ).fetchone()
    return int(row[0]) if row else 0


def post_recognition(
    pool: Pool, tenant_id: str, schedule_id: str, *, idempotency_key: str,
    actor_id: str, correlation_id: str, units_delivered: int | None = None,
    at: date | None = None,
) -> dict[str, Any]:
    """PostRevenueRecognition: move what is earned from unearned revenue to revenue.

    **Cumulative, which is what makes it safe to run twice.** `recognition.earned_by` answers
    "how much of this is earned by now" and the posting is the difference against what the runs
    already come to -- so ten calls in one day post once and then post nothing. An incremental
    design would double-count the day it ran twice, and there is no worker here to guarantee it
    runs once.

    **Nothing earned is not an error.** The ordinary answer on most days is zero, and a command
    that refused would make a sweep over every live schedule a sweep of mostly failures.

    **`as_of` is not in the future**, which is MOD-011's unbounded `observed_at` finding in a
    worse place: unbounded, a caller sent a date five thousand days out and the whole of a
    prepaid year became revenue in one call, with the schedule marked `complete` so the real
    recognition could never be posted and the journal dated outside every as-of read. That is
    paragraph 1695 inverted by the module written to enforce it.

    **And `units_delivered` is the caller's word, which is a declared gap rather than a
    control.** The delivery count for an `entitlement_grant` schedule is MOD-017's
    `mem_entitlement_ledger` and nothing resolves it here, so a caller can report ten classes
    delivered with nothing booked. The bound that does hold is the schedule's own
    `units_total`, so the overstatement cannot exceed what was sold.
    """
    today = at or _today()
    if today > _today():
        raise InvalidRequest(
            "recognition is measured up to today; a future date would recognise revenue "
            "that has not been earned")
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT legal_entity_id, basis, total_minor, currency, starts_on, ends_on,"
            " units_total, unearned_account_id, revenue_account_id, status,"
            " subject_person_id, source_kind, source_ref"
            " FROM plt01.led_recognition_schedules WHERE schedule_id = %s FOR UPDATE",
            (schedule_id,),
        ).fetchone()
        if row is None:
            raise NotFound("recognition_schedule_not_found")
        if str(row[9]) != "active":
            raise Conflict(f"this_recognition_schedule_is_{row[9]}")
        schedule = recognition.Schedule(
            basis=str(row[1]), total_minor=int(row[2]), currency=str(row[3]),
            starts_on=row[4], ends_on=row[5],
            units_total=int(row[6]) if row[6] is not None else None)
        already = _recognised(conn, schedule_id)
        delivered = units_delivered if units_delivered is not None else 0
        try:
            amount = recognition.to_recognise(
                schedule, already_minor=already, at=today, units_delivered=delivered)
            earned = recognition.earned_by(
                schedule, at=today, units_delivered=delivered)
        except accounts.LedgerError as e:
            raise InvalidRequest(str(e)) from None
        if amount == 0:
            return {
                "schedule_id": schedule_id, "amount_minor": 0,
                "recognised_total_minor": already,
                "earned_to_date_minor": earned,
                "remaining_minor": recognition.remaining(
                    schedule, already_minor=already),
                "over_recognised_minor": recognition.over_recognised(
                    schedule, already_minor=already, at=today,
                    units_delivered=delivered),
                "posted": False,
            }
        # **The liability has to be there to be drawn down.** The schedule's `total_minor`
        # and the invoice's `unearned_minor` are two unrelated figures a caller supplies, and
        # `unearned_minor` defaults to zero -- so a schedule opened against an invoice that
        # credited nothing to unearned revenue drove that liability to *minus* 500.00, the
        # ledger asserting that members have prepaid negative money. Reachable by accident on
        # the ordinary path, not only by an attacker.
        held = -_balance_of(conn, str(row[7]), at=today)
        if amount > held:
            raise Conflict(
                f"this schedule would recognise {amount} and its unearned revenue account "
                f"holds {held}; the sale has to be billed to unearned revenue first")
        prior = conn.execute(
            "SELECT run_id, amount_minor, schedule_id FROM plt01.led_recognition_runs"
            " WHERE idempotency_key = %s",
            (idempotency_key.strip(),),
        ).fetchone()
        if prior is not None:
            if str(prior[2]) != schedule_id:
                raise Conflict("this_idempotency_key_belongs_to_another_schedule")
            return {"schedule_id": schedule_id, "run_id": str(prior[0]),
                    "amount_minor": int(prior[1]),
                    "recognised_total_minor": already, "posted": False,
                    "repeated": True}
        posted = post_journal(
            conn, tenant_id, legal_entity_id=str(row[0]),
            lines=[
                {"account_id": str(row[7]), "amount_minor": amount,
                 "subject_person_id": row[10], "memo": "revenue recognised"},
                {"account_id": str(row[8]), "amount_minor": -amount,
                 "subject_person_id": row[10], "memo": "revenue recognised"},
            ],
            posted_on=today, currency=str(row[3]), purpose="recognition",
            source_kind="recognition", source_ref=schedule_id,
            description=f"recognition for {row[11]} {row[12]}",
            idempotency_key=f"recognition-{idempotency_key.strip()}",
            actor_id=actor_id, correlation_id=correlation_id)
        try:
            run = conn.execute(
                """
                INSERT INTO plt01.led_recognition_runs
                    (tenant_id, schedule_id, journal_id, amount_minor,
                     earned_to_date_minor, recognised_before_minor, as_of,
                     units_delivered, idempotency_key, posted_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING run_id
                """,
                (tenant_id, schedule_id, posted["journal_id"], amount, earned, already,
                 today, units_delivered, idempotency_key.strip(), actor_id,
                 correlation_id),
            ).fetchone()
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert run is not None
        total = already + amount
        if total >= schedule.total_minor:
            # **Complete, because there is nothing left to earn**, and a schedule left active
            # with nothing remaining is one every sweep re-reads for ever.
            conn.execute(
                "UPDATE plt01.led_recognition_schedules SET status = 'complete',"
                " closed_at = %s, closed_by = %s,"
                " close_reason = 'fully recognised', close_correlation_id = %s"
                " WHERE schedule_id = %s AND status = 'active'",
                (_now(), actor_id, correlation_id, schedule_id))
    return {"schedule_id": schedule_id, "run_id": str(run[0]), "amount_minor": amount,
            "journal_id": posted["journal_id"], "recognised_total_minor": total,
            "earned_to_date_minor": earned,
            "remaining_minor": schedule.total_minor - total,
            "status": "complete" if total >= schedule.total_minor else "active",
            "posted": True, "repeated": False}


def recognition_due(
    pool: Pool, tenant_id: str, *, at: date | None = None, limit: int = 200,
) -> dict[str, Any]:
    """Which live schedules have something to recognise now. For the sweep nothing runs.

    **A read, so it posts nothing**, and the figures come from the same decision functions
    `post_recognition` uses -- which is what makes it a preview rather than a second opinion.
    An `on_delivery` schedule is listed with its units unknown, because only the module that
    owns the delivery can say how many there have been; this names the schedule and stops.
    """
    today = at or _today()
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT s.schedule_id, s.basis, s.total_minor, s.currency, s.starts_on,"
            " s.ends_on, s.units_total, s.source_kind, s.source_ref,"
            " coalesce(sum(r.amount_minor), 0)"
            " FROM plt01.led_recognition_schedules s"
            " LEFT JOIN plt01.led_recognition_runs r ON r.schedule_id = s.schedule_id"
            " WHERE s.status = 'active'"
            " GROUP BY s.schedule_id, s.basis, s.total_minor, s.currency, s.starts_on,"
            "          s.ends_on, s.units_total, s.source_kind, s.source_ref"
            " ORDER BY s.schedule_id LIMIT %s",
            (max(1, min(limit, 1000)),),
        ).fetchall()
    due: list[dict[str, Any]] = []
    for row in rows:
        schedule = recognition.Schedule(
            basis=str(row[1]), total_minor=int(row[2]), currency=str(row[3]),
            starts_on=row[4], ends_on=row[5],
            units_total=int(row[6]) if row[6] is not None else None)
        already = int(row[9])
        if schedule.basis == "on_delivery":
            due.append({
                "schedule_id": str(row[0]), "basis": schedule.basis,
                "currency": schedule.currency,
                "source_kind": str(row[7]), "source_ref": str(row[8]),
                "recognised_minor": already,
                "remaining_minor": recognition.remaining(
                    schedule, already_minor=already),
                "amount_due_minor": None,
                "why": "delivery count comes from the module that owns the delivery",
            })
            continue
        amount = recognition.to_recognise(schedule, already_minor=already, at=today)
        if amount == 0:
            continue
        due.append({
            "schedule_id": str(row[0]), "basis": schedule.basis,
            "currency": schedule.currency,
            "source_kind": str(row[7]), "source_ref": str(row[8]),
            "recognised_minor": already, "amount_due_minor": amount,
            "remaining_minor": recognition.remaining(schedule, already_minor=already),
        })
    return {"as_of": today.isoformat(), "due": due, "count": len(due)}


# ------------------------------------------------------------------ provider settlement

def import_settlement(
    pool: Pool, tenant_id: str, *, legal_entity_id: str, provider_key: str,
    provider_batch_ref: str, settled_on: date, currency: str,
    claimed_total_minor: int, lines: list[dict[str, Any]], idempotency_key: str,
    actor_id: str, correlation_id: str, document_ref: str | None = None,
) -> dict[str, Any]:
    """ImportSettlement. COM-04-R04: the file, its lines, their verdicts and the cases.

    **Everything commits together.** The import, each line's match verdict and every
    reconciliation case the matching opened are one transaction: a half-imported file is a set
    of verdicts nobody can reproduce, because re-running the match later would read a different
    ledger.

    **An unmatched line opens a case and is not absorbed.** `led_reconciliation_cases` is
    where the question lives, and nothing is quietly folded into fees.

    **A fee and a payout post; the other kinds do not.** Those two definitionally have no
    counterpart in this build -- the fee is the provider's charge and the payout is the
    provider paying out -- so they are the two lines that *must* move a balance, and without
    them `provider_clearing` was debited by every card payment and relieved by nothing: it grew
    without bound, and `allocate_payment`'s whole argument for landing payments there was a
    reconciliation that read the account and never settled it. A chargeback, its reversal and
    an adjustment all open a case instead, because each of them reverses or amends a payment
    this module cannot resolve to one row, and posting a guess is worse than asking.
    """
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    if not lines:
        raise InvalidRequest("a_settlement_import_has_at_least_one_line")
    # The route caps the list at 5 000, so this is the service-level bound for a caller that
    # is not the route -- stated at the same figure rather than at one nothing can reach.
    if len(lines) > 5_000:
        raise InvalidRequest("a_settlement_import_is_at_most_5000_lines")
    parsed: list[settlement.Line] = []
    for item in lines:
        try:
            line = settlement.Line(
                line_kind=str(item["line_kind"]),
                provider_ref=str(item["provider_ref"]),
                amount_minor=int(item["amount_minor"]),
                currency=str(item.get("currency", currency)).upper())
            settlement.check_line(line)
        except (KeyError, ValueError, accounts.LedgerError) as e:
            raise InvalidRequest(str(e) or "a_settlement_line_is_malformed") from None
        parsed.append(line)
    computed = settlement.control_total(parsed)
    if set(computed) != {currency.upper()}:
        raise InvalidRequest(
            "a settlement import is in one currency; its lines name "
            + ", ".join(sorted(computed)))
    computed_total = computed[currency.upper()]
    with tenant_scope(pool, tenant_id) as conn:
        prior = conn.execute(
            "SELECT settlement_id, legal_entity_id, line_count, computed_total_minor"
            " FROM plt01.led_settlements WHERE idempotency_key = %s",
            (idempotency_key.strip(),),
        ).fetchone()
        if prior is not None:
            if str(prior[1]) != legal_entity_id:
                raise Conflict("this_idempotency_key_belongs_to_another_legal_entity")
            return {"settlement_id": str(prior[0]), "line_count": int(prior[2]),
                    "computed_total_minor": int(prior[3]), "repeated": True}
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.led_settlements
                    (tenant_id, legal_entity_id, provider_key, provider_batch_ref,
                     settled_on, currency, claimed_total_minor, computed_total_minor,
                     line_count, document_ref, imported_by, idempotency_key,
                     correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING settlement_id
                """,
                (tenant_id, legal_entity_id, provider_key, provider_batch_ref,
                 settled_on, currency.upper(), claimed_total_minor, computed_total,
                 len(parsed), document_ref, actor_id, idempotency_key.strip(),
                 correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_provider_batch_has_already_been_imported") from None
        except errors.ForeignKeyViolation as e:
            raise NotFound(_fk_subject(e)) from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        settlement_id = str(row[0])
        outcomes: dict[str, int] = {}
        cases: list[str] = []
        # The accounts the two posting kinds need. Absent, the import still records its
        # verdicts and says what it could not post -- the bridge's rule, for the same reason.
        movement = chart_for(conn, currency=currency,
                             kinds=("provider_clearing", "provider_fee", "bank"),
                             legal_entity_id=legal_entity_id)
        unposted: list[str] = []
        posted_lines = 0
        for number, line in enumerate(parsed, start=1):
            recorded = _recorded_for(conn, line)
            verdict = settlement.match(line, _settlement_recorded(recorded))
            outcomes[verdict.outcome] = outcomes.get(verdict.outcome, 0) + 1
            conn.execute(
                """
                INSERT INTO plt01.led_settlement_lines
                    (tenant_id, settlement_id, line_number, line_kind, provider_ref,
                     amount_minor, currency, outcome, outcome_reason,
                     matched_payment_id, matched_refund_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (tenant_id, settlement_id, number, line.line_kind, line.provider_ref,
                 line.amount_minor, line.currency, verdict.outcome, verdict.reason,
                 recorded["payment_id"] if recorded and verdict.outcome == "matched"
                 else None,
                 recorded["refund_id"] if recorded and verdict.outcome == "matched"
                 else None))
            if line.line_kind in ("fee", "payout"):
                if movement is None:
                    unposted.append(line.provider_ref)
                else:
                    # A fee is the provider taking its charge out of what it owes us: an
                    # expense up, the clearing balance down. A payout is the provider paying:
                    # the bank up, the clearing balance down. `amount_minor` arrives signed
                    # the provider's way -- a fee negative, a payout positive -- so the
                    # magnitude is what moves and the direction is decided here.
                    size = abs(line.amount_minor)
                    other = (movement["provider_fee"] if line.line_kind == "fee"
                             else movement["bank"])
                    post_journal(
                        conn, tenant_id, legal_entity_id=legal_entity_id,
                        lines=[
                            {"account_id": other, "amount_minor": size,
                             "memo": f"{line.line_kind} {line.provider_ref}"},
                            {"account_id": movement["provider_clearing"],
                             "amount_minor": -size,
                             "memo": f"{line.line_kind} {line.provider_ref}"},
                        ],
                        posted_on=settled_on, currency=line.currency,
                        purpose="settlement", source_kind="settlement",
                        source_ref=settlement_id,
                        description=f"settlement {line.line_kind}",
                        idempotency_key=f"settlement-{settlement_id}-{number}",
                        actor_id=actor_id, correlation_id=correlation_id,
                        fall_back_to_open=True)
                    posted_lines += 1
            # **A fee and a payout open no case.** They are the provider's own movements and
            # match nothing here by design; a case for each would bury the lines that need
            # somebody. Every other unmatched line gets one.
            elif verdict.needs_a_case:
                cases.append(_open_case(
                    conn, tenant_id, legal_entity_id=legal_entity_id,
                    case_kind="settlement_line", subject_kind="settlement_line",
                    subject_ref=f"{settlement_id}:{number}",
                    expected_minor=(
                        int(recorded["amount_minor"]) if recorded else 0),
                    observed_minor=line.amount_minor, currency=line.currency,
                    detail=verdict.reason,
                    idempotency_key=f"{idempotency_key.strip()}:line:{number}",
                    actor_id=actor_id, correlation_id=correlation_id))
        total_verdict = settlement.check_control_total(
            claimed_minor=claimed_total_minor, computed_minor=computed_total,
            currency=currency.upper())
        if total_verdict.needs_a_case:
            cases.append(_open_case(
                conn, tenant_id, legal_entity_id=legal_entity_id,
                case_kind="settlement_total", subject_kind="settlement",
                subject_ref=settlement_id, expected_minor=claimed_total_minor,
                observed_minor=computed_total, currency=currency.upper(),
                detail=total_verdict.reason,
                idempotency_key=f"{idempotency_key.strip()}:total",
                actor_id=actor_id, correlation_id=correlation_id))
        _append(conn, tenant_id, "settlement.imported", "settlement", settlement_id,
                {"settlement_id": settlement_id, "provider_key": provider_key,
                 "legal_entity_id": legal_entity_id, "currency": currency.upper(),
                 "line_count": len(parsed), "computed_total_minor": computed_total},
                correlation_id=correlation_id, actor_id=actor_id)
    out: dict[str, Any] = {
        "settlement_id": settlement_id, "line_count": len(parsed),
        "computed_total_minor": computed_total,
        "claimed_total_minor": claimed_total_minor,
        "outcomes": outcomes, "cases_opened": cases,
        "posted_lines": posted_lines, "repeated": False}
    if unposted:
        out["ledger_skipped_because"] = (
            f"this tenant has no provider clearing, provider fee and bank account in "
            f"{currency.upper()}, so {len(unposted)} movement line(s) recorded their "
            f"verdict and posted nothing")
    return out


def _recorded_for(
    conn: Connection[Any], line: settlement.Line,
) -> dict[str, Any] | None:
    """What this build recorded against a provider reference, if anything.

    Looks in MOD-017's payments and refunds, which are the two places a provider reference
    lands. **Counted rather than fetched with `LIMIT 1`**: two rows sharing a reference is a
    `duplicate` verdict rather than a silent pick, which is MOD-010's "a decision made once per
    job and applied per item" in its smallest form.
    """
    payments = conn.execute(
        "SELECT payment_id, amount_minor, currency FROM plt01.fin_payments"
        " WHERE provider_ref = %s",
        (line.provider_ref,),
    ).fetchall()
    refunds = conn.execute(
        "SELECT refund_id, amount_minor, currency FROM plt01.fin_refunds"
        " WHERE provider_ref = %s",
        (line.provider_ref,),
    ).fetchall()
    total = len(payments) + len(refunds)
    if total == 0:
        return None
    if payments:
        first = payments[0]
        return {"payment_id": str(first[0]), "refund_id": None,
                "amount_minor": int(first[1]), "currency": str(first[2]),
                "count": total}
    first = refunds[0]
    return {"payment_id": None, "refund_id": str(first[0]),
            "amount_minor": int(first[1]), "currency": str(first[2]), "count": total}


def _settlement_recorded(row: dict[str, Any] | None) -> settlement.Recorded | None:
    if row is None:
        return None
    return settlement.Recorded(
        reference=str(row.get("payment_id") or row.get("refund_id")),
        amount_minor=int(row["amount_minor"]), currency=str(row["currency"]),
        count=int(row["count"]))


# ------------------------------------------------------------------ the open questions

def _open_case(
    conn: Connection[Any], tenant_id: str, *, legal_entity_id: str, case_kind: str,
    subject_kind: str, subject_ref: str, expected_minor: int, observed_minor: int,
    currency: str, detail: str, idempotency_key: str, actor_id: str,
    correlation_id: str, opened_on: date | None = None,
) -> str:
    """Open one reconciliation case in the caller's transaction, idempotently.

    **A case is opened with the figures as they were**, because the thing being reconciled may
    move afterwards and the question was about the two numbers at the time. Idempotent on the
    key so a re-import opens the same case rather than a second one -- and `DO NOTHING` then a
    re-read, never a caught `UniqueViolation`, which leaves the transaction aborted.
    """
    row = conn.execute(
        """
        INSERT INTO plt01.led_reconciliation_cases
            (tenant_id, legal_entity_id, case_kind, subject_kind, subject_ref,
             expected_minor, observed_minor, currency, detail, opened_on, opened_by,
             idempotency_key, correlation_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
        RETURNING case_id
        """,
        (tenant_id, legal_entity_id, case_kind, subject_kind, subject_ref,
         expected_minor, observed_minor, currency.upper(), detail,
         opened_on or _today(), actor_id, idempotency_key, correlation_id),
    ).fetchone()
    if row is not None:
        case_id = str(row[0])
        _append(conn, tenant_id, "reconciliation.mismatch.detected",
                "reconciliation_case", case_id,
                {"case_id": case_id, "case_kind": case_kind,
                 "legal_entity_id": legal_entity_id, "currency": currency.upper(),
                 "expected_minor": expected_minor, "observed_minor": observed_minor},
                correlation_id=correlation_id, actor_id=actor_id)
        return case_id
    existing = conn.execute(
        "SELECT case_id FROM plt01.led_reconciliation_cases WHERE idempotency_key = %s",
        (idempotency_key,),
    ).fetchone()
    assert existing is not None
    return str(existing[0])


def resolve_case(
    pool: Pool, tenant_id: str, case_id: str, *, outcome: str, resolution: str,
    actor_id: str, correlation_id: str, resolution_journal_id: str | None = None,
) -> dict[str, Any]:
    """Close a reconciliation case, with a resolution that names who decided.

    **`written_off` is a decision about money and it says so in the status.** A case folded
    into fees and marked `resolved` would be a write-off nobody reported; the separate status is
    what lets a report count the money this tenant decided to stop chasing.

    **A cited journal has to be about this case.** `resolution_journal_id` had a foreign key
    and nothing else behind it, so a case could be written off citing an unrelated journal and
    the row that *is* the audit read as though that journal had cleared a mismatch it has
    nothing to do with -- MOD-016's `approval_id` finding in another table.
    """
    if not resolution.strip():
        raise InvalidRequest("resolving_a_reconciliation_case_states_how")
    if outcome not in ("resolved", "written_off", "abandoned", "investigating"):
        raise InvalidRequest(f"unknown_case_outcome_{outcome}")
    moment = _now()
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT status FROM plt01.led_reconciliation_cases"
            " WHERE case_id = %s FOR UPDATE",
            (case_id,),
        ).fetchone()
        if row is None:
            raise NotFound("reconciliation_case_not_found")
        current = str(row[0])
        if current == outcome:
            return {"case_id": case_id, "status": current, "repeated": True}
        if resolution_journal_id is not None:
            cited = conn.execute(
                "SELECT purpose, source_kind FROM plt01.led_journals"
                " WHERE journal_id = %s",
                (resolution_journal_id,),
            ).fetchone()
            if cited is None:
                raise NotFound("ledger_journal_not_found")
            if str(cited[0]) not in ("correction", "settlement", "close"):
                raise Conflict(
                    "a reconciliation case is cleared by a correction, a settlement entry "
                    f"or a closing entry; that journal is {cited[0]}")
        if current in ("resolved", "written_off", "abandoned"):
            raise Conflict(f"this_case_is_already_{current}")
        if outcome == "investigating":
            conn.execute(
                "UPDATE plt01.led_reconciliation_cases SET status = 'investigating'"
                " WHERE case_id = %s AND status = 'open'",
                (case_id,))
            return {"case_id": case_id, "status": "investigating", "repeated": False}
        try:
            conn.execute(
                "UPDATE plt01.led_reconciliation_cases SET status = %s, resolution = %s,"
                " resolution_journal_id = %s, resolved_at = %s, resolved_by = %s,"
                " resolve_correlation_id = %s"
                " WHERE case_id = %s AND status IN ('open', 'investigating')",
                (outcome, resolution.strip(), resolution_journal_id, moment, actor_id,
                 correlation_id, case_id))
        except errors.ForeignKeyViolation as e:
            raise NotFound(_fk_subject(e)) from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
    return {"case_id": case_id, "status": outcome, "repeated": False}


def open_cases(
    pool: Pool, tenant_id: str, *, legal_entity_id: str | None = None,
    at: date | None = None, limit: int = 200,
) -> dict[str, Any]:
    """Every unanswered reconciliation question, with how long it has been open.

    Paragraph 1699's SLI is "reconciliation mismatch = 0 unresolved past SLA". The SLA is a
    tenant's own number and the sources state none, so what this returns is the age -- and
    whichever figure a tenant sets, the list is what somebody works.
    """
    today = at or _today()
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT case_id, legal_entity_id, case_kind, subject_kind, subject_ref,"
            " expected_minor, observed_minor, currency, detail, status, opened_on"
            " FROM plt01.led_reconciliation_cases"
            " WHERE status IN ('open', 'investigating')"
            "   AND (%s::uuid IS NULL OR legal_entity_id = %s)"
            " ORDER BY opened_on, case_id LIMIT %s",
            (legal_entity_id, legal_entity_id, max(1, min(limit, 1000))),
        ).fetchall()
    return {
        "as_of": today.isoformat(), "count": len(rows),
        "cases": [
            {"case_id": str(r[0]), "legal_entity_id": str(r[1]),
             "case_kind": str(r[2]), "subject_kind": str(r[3]),
             "subject_ref": str(r[4]), "expected_minor": int(r[5]),
             "observed_minor": int(r[6]),
             "difference_minor": int(r[6]) - int(r[5]),
             "currency": str(r[7]), "detail": str(r[8]), "status": str(r[9]),
             "opened_on": r[10].isoformat(),
             "age_days": settlement.ageing(r[10], at=today)}
            for r in rows],
    }


# ------------------------------------------------------------------ cash, drawers, deposits

def open_cash_session(
    pool: Pool, tenant_id: str, *, location_id: str, cash_account_id: str,
    drawer_label: str, currency: str, opening_float_minor: int, idempotency_key: str,
    actor_id: str, correlation_id: str, float_source_account_id: str | None = None,
    legal_entity_id: str | None = None, at: date | None = None,
) -> dict[str, Any]:
    """Open a till. COM-04-R05.

    **One open session per drawer**, which the partial index enforces: two would make "what
    should be in this till" answerable twice and the second close would be measured against
    the first's postings. The index cannot be the *refusal*, though -- an insert can name only
    one index in its `ON CONFLICT`, and this one already names the idempotency key, so the
    second open raised an uncaught `UniqueViolation` and answered 500 while telling the caller
    to try again. The readable refusal comes from a check under an advisory lock on the drawer;
    the index stays as the backstop for a writer that is not this function.

    **A float that is not posted is cash the ledger does not know about.** The close's variance
    posting exists to keep the drawer's account balance equal to the money that is there, and
    that is only true if the float got there by a journal: with the float merely declared on
    the row, banking the takings drove the drawer's own account negative by exactly the float.
    So a non-zero float is posted from the account it was drawn from -- the safe -- and
    `_expected_in_drawer` then reads the balance rather than adding a number the caller sent.
    """
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    if opening_float_minor and not (float_source_account_id and legal_entity_id):
        raise InvalidRequest("a_float_names_the_account_it_came_from_and_an_entity")
    today = at or _today()
    with tenant_scope(pool, tenant_id) as conn:
        account = _account(conn, cash_account_id)
        if account["account_kind"] != "cash":
            raise Conflict(
                f"the account {account['account_code']} is {account['account_kind']} "
                f"and a till session needs a cash account")
        if account["currency"] != currency.upper():
            raise Conflict(f"the account {account['account_code']} is in "
                           f"{account['currency']}")
        # **A drawer at this site, not another site's drawer.** A location-scoped cash account
        # named from a different location opened a session whose close then moved the other
        # site's balance; a tenant-wide cash account is allowed, because a single-site tenant
        # has one.
        if (account["location_id"] is not None
                and account["location_id"] != location_id):
            raise Conflict(
                f"the account {account['account_code']} belongs to another location")
        # Serialises two opens of the same drawer, so the check below is authoritative and
        # the caller gets a sentence instead of a constraint name. An advisory lock needs no
        # table privilege and there is no drawer row to take `FOR UPDATE` on.
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"led_drawer:{tenant_id}:{location_id}:{drawer_label}",))
        standing = conn.execute(
            "SELECT session_id, idempotency_key FROM plt01.led_cash_sessions"
            " WHERE location_id = %s AND drawer_label = %s AND status = 'open'",
            (location_id, drawer_label),
        ).fetchone()
        if standing is not None and str(standing[1]) != idempotency_key.strip():
            raise Conflict("this_drawer_already_has_an_open_session")
        row = conn.execute(
            """
            INSERT INTO plt01.led_cash_sessions
                (tenant_id, location_id, cash_account_id, drawer_label, currency,
                 opening_float_minor, opened_by, idempotency_key, correlation_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
            RETURNING session_id
            """,
            (tenant_id, location_id, cash_account_id, drawer_label, currency.upper(),
             opening_float_minor, actor_id, idempotency_key.strip(), correlation_id),
        ).fetchone()
        if row is None:
            prior = conn.execute(
                "SELECT session_id, location_id, drawer_label, status"
                " FROM plt01.led_cash_sessions WHERE idempotency_key = %s",
                (idempotency_key.strip(),),
            ).fetchone()
            assert prior is not None
            if str(prior[1]) != location_id or str(prior[2]) != drawer_label:
                raise Conflict("this_idempotency_key_belongs_to_another_drawer")
            return {"session_id": str(prior[0]), "status": str(prior[3]),
                    "repeated": True}
        session_id = str(row[0])
        float_journal_id: str | None = None
        if opening_float_minor:
            assert float_source_account_id is not None and legal_entity_id is not None
            source = _account(conn, float_source_account_id)
            if source["account_kind"] != "cash":
                raise Conflict(
                    f"the account {source['account_code']} is "
                    f"{source['account_kind']} and a float comes from a cash account")
            if float_source_account_id == cash_account_id:
                raise Conflict("a_float_cannot_come_from_the_drawer_it_opens")
            # In the drawer's own transaction, because a session that exists with its float
            # unposted is the defect this posting closes.
            float_journal_id = post_journal(
                conn, tenant_id, legal_entity_id=legal_entity_id,
                lines=[
                    {"account_id": cash_account_id,
                     "amount_minor": opening_float_minor,
                     "memo": f"opening float for {drawer_memo(session_id)}"},
                    {"account_id": float_source_account_id,
                     "amount_minor": -opening_float_minor,
                     "memo": "float drawn for a till"},
                ],
                posted_on=today, currency=currency.upper(), purpose="trade",
                source_kind="cash_session", source_ref=session_id,
                description="opening float",
                idempotency_key=f"cash-float-{session_id}",
                actor_id=actor_id, correlation_id=correlation_id)["journal_id"]
    return {"session_id": session_id, "status": "open", "drawer_label": drawer_label,
            "opening_float_minor": opening_float_minor,
            "float_journal_id": float_journal_id, "repeated": False}


def _expected_in_drawer(
    conn: Connection[Any], *, cash_account_id: str, at: date,
) -> int:
    """What the ledger says should be in the till: the drawer account's own balance.

    **Derived from the postings, with no number the caller sent.** The declared float is a
    physical count and it is posted at open, so it is already in this sum -- adding it again
    here would have let a caller lower the expected figure and make a short till balance,
    which is the caller-supplied-control shape every review in this build has found.
    """
    row = conn.execute(
        # **Bounded by the posting date**, like `account_balance` thirty lines down. Without
        # the join this summed journals dated in the future as well, so one journal dated next
        # year moving 100.00 out of the till made today's close balance: nothing posted to
        # suspense, no written reason demanded and no case opened -- which is the bound the
        # permission catalogue cites when it leaves `finance.cash.session` routine. It also
        # misfired with no adversary, on any legitimately back- or future-dated journal
        # touching a till account.
        "SELECT coalesce(sum(p.amount_minor), 0) FROM plt01.led_postings p"
        " JOIN plt01.led_journals j ON j.journal_id = p.journal_id"
        " WHERE p.account_id = %s AND j.posted_on <= %s",
        (cash_account_id, at),
    ).fetchone()
    return int(row[0]) if row else 0


def close_cash_session(
    pool: Pool, tenant_id: str, session_id: str, *, counted_minor: int,
    legal_entity_id: str, suspense_account_id: str, actor_id: str,
    correlation_id: str, variance_reason: str | None = None,
    at: date | None = None,
) -> dict[str, Any]:
    """Count a till and close it. COM-04-R05's discrepancy workflow.

    **A variance is posted to `suspense` and opens a case.** Neither half is optional: posting
    it keeps the ledger's cash balance equal to the money that is actually there, and the case
    is the question nobody has answered yet. Absorbing it into an expense would make the till
    balance and the question disappear together.

    **An unexplained variance refuses the close**, which is the one control in this table: a
    till 2.00 down every evening with nothing written against it is a pattern only visible later
    if each close said something at the time.
    """
    today = at or _today()
    settled: Exception | None = None
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT location_id, cash_account_id, currency, opening_float_minor,"
            " opened_at, status, counted_minor, expected_minor, variance_journal_id"
            " FROM plt01.led_cash_sessions WHERE session_id = %s FOR UPDATE",
            (session_id,),
        ).fetchone()
        if row is None:
            raise NotFound("cash_session_not_found")
        if str(row[5]) != "open":
            return {"session_id": session_id, "status": str(row[5]),
                    "counted_minor": int(row[6]) if row[6] is not None else None,
                    "expected_minor": int(row[7]) if row[7] is not None else None,
                    "variance_minor": (
                        int(row[6]) - int(row[7])
                        if row[6] is not None and row[7] is not None else None),
                    "repeated": True}
        expected = _expected_in_drawer(conn, cash_account_id=str(row[1]), at=today)
        # **Suspense, not any account in the chart.** Unchecked, this route -- gated on the
        # module's only routine, AAL-1 permission -- posted an arbitrary amount between the
        # drawer and whatever the caller named: a reviewer cleared a 10,000.00 receivable with
        # it, and the identical movement through `POST /ledger/journals` is refused because
        # that permission is financial and needs a step-up.
        _account_of_kind(conn, suspense_account_id, ("suspense",),
                         currency=str(row[2]), role="counterpart")
        count = settlement.Count(
            expected_minor=expected, counted_minor=counted_minor,
            currency=str(row[2]))
        try:
            settlement.check_close(count, reason=variance_reason)
        except accounts.LedgerError as e:
            raise InvalidRequest(str(e)) from None
        gap = settlement.variance(count)
        journal_id: str | None = None
        case_id: str | None = None
        if gap != 0:
            # The drawer holds more or less than the ledger thought, so the cash account moves
            # to match reality and the difference lands in suspense until somebody explains it.
            posted = post_journal(
                conn, tenant_id, legal_entity_id=legal_entity_id,
                lines=[
                    {"account_id": str(row[1]), "amount_minor": gap,
                     "memo": f"till count variance on {drawer_memo(session_id)}"},
                    {"account_id": suspense_account_id, "amount_minor": -gap,
                     "memo": "unexplained till variance"},
                ],
                posted_on=today, currency=str(row[2]), purpose="trade",
                source_kind="cash_session", source_ref=session_id,
                description="till count variance",
                idempotency_key=f"cash-variance-{session_id}",
                actor_id=actor_id, correlation_id=correlation_id)
            journal_id = posted["journal_id"]
            case_id = _open_case(
                conn, tenant_id, legal_entity_id=legal_entity_id,
                case_kind="cash_variance", subject_kind="cash_session",
                subject_ref=session_id, expected_minor=expected,
                observed_minor=counted_minor, currency=str(row[2]),
                detail=(variance_reason or "").strip() or "a till that did not balance",
                idempotency_key=f"cash-variance-{session_id}", actor_id=actor_id,
                correlation_id=correlation_id, opened_on=today)
        try:
            conn.execute(
                "UPDATE plt01.led_cash_sessions SET status = 'closed',"
                " expected_minor = %s, counted_minor = %s, variance_reason = %s,"
                " closed_at = %s, closed_by = %s, close_correlation_id = %s,"
                " variance_journal_id = %s"
                " WHERE session_id = %s AND status = 'open'",
                (expected, counted_minor, (variance_reason or "").strip() or None,
                 _now(), actor_id, correlation_id, journal_id, session_id))
        except errors.CheckViolation as e:
            settled = InvalidRequest(_check_name(e))
    if settled is not None:
        raise settled
    return {"session_id": session_id, "status": "closed", "expected_minor": expected,
            "counted_minor": counted_minor, "variance_minor": gap,
            "variance_journal_id": journal_id, "case_id": case_id, "repeated": False}


def drawer_memo(session_id: str) -> str:
    """A short, stable memo for a till journal. Named so the posting is readable later."""
    return f"session {session_id[:8]}"


def create_deposit(
    pool: Pool, tenant_id: str, *, location_id: str, cash_account_id: str,
    bank_account_id: str, currency: str, declared_minor: int, deposited_on: date,
    session_ids: list[str], legal_entity_id: str, idempotency_key: str,
    actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Bank a bag of cash. The journal moves it from `cash` to `bank` immediately.

    **Posted on the way out, not on the way in.** The money has left the premises, so the till
    no longer holds it -- and a ledger that waited for the bank's confirmation would show cash
    in a drawer that is empty for the days the bag is in transit. The bank's own figure arrives
    later and is reconciled against this one, which is what `credited_minor` is for.

    **The sessions it banks are recorded**, because the question when the bank disagrees is
    always which takings were in the bag.
    """
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    if not session_ids:
        raise InvalidRequest("a_deposit_names_the_sessions_it_banks")
    with tenant_scope(pool, tenant_id) as conn:
        prior = conn.execute(
            "SELECT deposit_id, declared_minor, status FROM plt01.led_deposits"
            " WHERE idempotency_key = %s",
            (idempotency_key.strip(),),
        ).fetchone()
        if prior is not None:
            return {"deposit_id": str(prior[0]), "declared_minor": int(prior[1]),
                    "status": str(prior[2]), "repeated": True}
        for account_id, expected in (
            (cash_account_id, "cash"), (bank_account_id, "bank"),
        ):
            account = _account(conn, account_id)
            if account["account_kind"] != expected:
                raise Conflict(
                    f"the account {account['account_code']} is "
                    f"{account['account_kind']} and this side needs {expected}")
            if account["currency"] != currency.upper():
                raise Conflict(
                    f"the account {account['account_code']} is in {account['currency']}")
        # **The bag's composition is checked against the sessions before anything posts.** A
        # deposit declaring more than the sessions it names is either a miscount or cash from
        # somewhere nobody recorded, and both are questions rather than postings.
        # **A session is banked once**, checked here so the caller gets a sentence: the
        # unique key behind it is the backstop, and the composition trigger would otherwise
        # refuse first with a message about an amount. One session in two bags was 400.00 in
        # the bank against minus 200.00 in a drawer, under two idempotency keys, which is the
        # ordinary retry-with-a-new-key case.
        already = conn.execute(
            "SELECT session_id FROM plt01.led_deposit_sessions"
            " WHERE session_id = ANY(%s) LIMIT 1",
            (session_ids,),
        ).fetchone()
        if already is not None:
            raise Conflict(
                f"the session {already[0]} has already been banked in another deposit")
        banked = conn.execute(
            "SELECT coalesce(sum(counted_minor), 0), count(*) FROM plt01.led_cash_sessions"
            " WHERE session_id = ANY(%s) AND status = 'closed' AND currency = %s",
            (session_ids, currency.upper()),
        ).fetchone()
        assert banked is not None
        if int(banked[1]) != len(set(session_ids)):
            raise Conflict(
                "a deposit banks closed sessions in its own currency; "
                f"{int(banked[1])} of {len(set(session_ids))} named ones qualify")
        posted = post_journal(
            conn, tenant_id, legal_entity_id=legal_entity_id,
            lines=[
                {"account_id": bank_account_id, "amount_minor": declared_minor,
                 "memo": "bank deposit in transit"},
                {"account_id": cash_account_id, "amount_minor": -declared_minor,
                 "memo": "bank deposit in transit"},
            ],
            posted_on=deposited_on, currency=currency, source_kind="deposit",
            source_ref=idempotency_key.strip(), description="bank deposit",
            idempotency_key=f"deposit-{idempotency_key.strip()}",
            actor_id=actor_id, correlation_id=correlation_id)
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.led_deposits
                    (tenant_id, location_id, cash_account_id, bank_account_id, currency,
                     declared_minor, deposited_on, journal_id, created_by,
                     idempotency_key, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING deposit_id
                """,
                (tenant_id, location_id, cash_account_id, bank_account_id,
                 currency.upper(), declared_minor, deposited_on, posted["journal_id"],
                 actor_id, idempotency_key.strip(), correlation_id),
            ).fetchone()
        except errors.ForeignKeyViolation as e:
            raise NotFound(_fk_subject(e)) from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        deposit_id = str(row[0])
        shares = _deposit_shares(declared_minor, len(set(session_ids)))
        for session_id, share in zip(sorted(set(session_ids)), shares, strict=True):
            try:
                conn.execute(
                    """
                    INSERT INTO plt01.led_deposit_sessions
                        (tenant_id, deposit_id, session_id, amount_minor, added_by,
                         correlation_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (tenant_id, deposit_id, session_id, share, actor_id,
                     correlation_id))
            except errors.ForeignKeyViolation as e:
                raise NotFound(_fk_subject(e)) from None
            except errors.CheckViolation as e:
                raise InvalidRequest(_check_name(e)) from None
        case_id: str | None = None
        verdict = settlement.deposit_matches(
            declared_minor=declared_minor, sessions_minor=int(banked[0]))
        if verdict.needs_a_case:
            case_id = _open_case(
                conn, tenant_id, legal_entity_id=legal_entity_id,
                case_kind="deposit_variance", subject_kind="deposit",
                subject_ref=deposit_id, expected_minor=int(banked[0]),
                observed_minor=declared_minor, currency=currency.upper(),
                detail=verdict.reason,
                idempotency_key=f"deposit-declared-{idempotency_key.strip()}",
                actor_id=actor_id, correlation_id=correlation_id,
                opened_on=deposited_on)
    return {"deposit_id": deposit_id, "declared_minor": declared_minor,
            "sessions_minor": int(banked[0]), "journal_id": posted["journal_id"],
            "status": "in_transit", "case_id": case_id, "repeated": False}


def _deposit_shares(declared_minor: int, sessions: int) -> list[int]:
    """How a bag's declared total is attributed across the sessions it banks.

    **Evenly, by largest remainder, and that is an approximation stated rather than hidden.**
    The bag holds one pile of notes; which session each note came from is not recoverable, and a
    split that pretended otherwise would be a fabricated attribution. What the attribution is
    *for* is answering "which takings were in this bag" when the bank disagrees, and for that
    the set matters more than the split.
    """
    from app.billing import money
    return money.allocate(declared_minor, [1] * max(sessions, 1))


def confirm_deposit(
    pool: Pool, tenant_id: str, deposit_id: str, *, credited_minor: int,
    credited_on: date, legal_entity_id: str, suspense_account_id: str,
    actor_id: str, correlation_id: str, bank_reference: str | None = None,
) -> dict[str, Any]:
    """What the bank says it received. COM-04-R05's payout reconciliation.

    **A deposit credited for a different amount is `short`, not `credited`.** The separate
    status is what stops a report of "deposits credited" quietly being a report of "deposits the
    bank disagreed with" -- and the difference posts to suspense and opens a case, like a till
    variance, because it is the same kind of unanswered question.
    """
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT declared_minor, currency, bank_account_id, status, credited_minor"
            " FROM plt01.led_deposits WHERE deposit_id = %s FOR UPDATE",
            (deposit_id,),
        ).fetchone()
        if row is None:
            raise NotFound("deposit_not_found")
        if str(row[3]) != "in_transit":
            return {"deposit_id": deposit_id, "status": str(row[3]),
                    "credited_minor": int(row[4]) if row[4] is not None else None,
                    "repeated": True}
        declared, currency = int(row[0]), str(row[1])
        # The same omission as the till close, behind a financial permission rather than a
        # routine one -- correctness rather than escalation, and the same one-line fix.
        _account_of_kind(conn, suspense_account_id, ("suspense",),
                         currency=currency, role="counterpart")
        gap = credited_minor - declared
        journal_id: str | None = None
        case_id: str | None = None
        if gap != 0:
            posted = post_journal(
                conn, tenant_id, legal_entity_id=legal_entity_id,
                lines=[
                    {"account_id": str(row[2]), "amount_minor": gap,
                     "memo": "bank credited a different amount"},
                    {"account_id": suspense_account_id, "amount_minor": -gap,
                     "memo": "unexplained deposit variance"},
                ],
                posted_on=credited_on, currency=currency, purpose="trade",
                source_kind="deposit", source_ref=deposit_id,
                description="deposit variance",
                idempotency_key=f"deposit-variance-{deposit_id}",
                actor_id=actor_id, correlation_id=correlation_id)
            journal_id = posted["journal_id"]
            case_id = _open_case(
                conn, tenant_id, legal_entity_id=legal_entity_id,
                case_kind="deposit_variance", subject_kind="deposit",
                subject_ref=deposit_id, expected_minor=declared,
                observed_minor=credited_minor, currency=currency,
                detail=f"the bank credited {credited_minor} against a declared {declared}",
                idempotency_key=f"deposit-credited-{deposit_id}", actor_id=actor_id,
                correlation_id=correlation_id, opened_on=credited_on)
        try:
            conn.execute(
                "UPDATE plt01.led_deposits SET status = %s, credited_minor = %s,"
                " credited_on = %s, bank_reference = %s, confirm_journal_id = %s,"
                " confirmed_at = %s, confirmed_by = %s, confirm_correlation_id = %s"
                " WHERE deposit_id = %s AND status = 'in_transit'",
                ("credited" if gap == 0 else "short", credited_minor, credited_on,
                 (bank_reference or "").strip() or None, journal_id, _now(), actor_id,
                 correlation_id, deposit_id))
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
    return {"deposit_id": deposit_id,
            "status": "credited" if gap == 0 else "short",
            "declared_minor": declared, "credited_minor": credited_minor,
            "variance_minor": gap, "variance_journal_id": journal_id,
            "case_id": case_id, "repeated": False}


# ------------------------------------------------------------------ the reads
#
# **Every figure here is a sum over postings or entries.** COM-04-R07 and paragraph 1683: there
# is no stored balance to read, and the cost of a query per read is what buys the guarantee that
# a statement and a balance cannot disagree.

def _balance_of(conn: Connection[Any], account_id: str, *, at: date) -> int:
    """The signed sum over one account, on a connection a caller already holds.

    Separate from `account_balance` because that one opens its own transaction, and the two
    places that need this figure -- the recognition draw-down and the till's expectation -- are
    inside somebody else's.
    """
    row = conn.execute(
        "SELECT coalesce(sum(p.amount_minor), 0) FROM plt01.led_postings p"
        " JOIN plt01.led_journals j ON j.journal_id = p.journal_id"
        " WHERE p.account_id = %s AND j.posted_on <= %s",
        (account_id, at),
    ).fetchone()
    return int(row[0]) if row else 0


def account_balance(
    pool: Pool, tenant_id: str, account_id: str, *, as_of: date | None = None,
) -> dict[str, Any]:
    """One account's balance, in its own direction, as of a date.

    **`signed_increase` is what turns the signed posting into the account's own language.** A
    liability credited by 500 has *increased* by 500, and a reader asking "how much wallet value
    does this member hold" wants 500 rather than -500. The raw signed sum comes back too, so a
    trial balance can add the columns up and get zero.
    """
    today = as_of or _today()
    with tenant_scope(pool, tenant_id) as conn:
        account = _account(conn, account_id)
        row = conn.execute(
            "SELECT coalesce(sum(p.amount_minor), 0), count(*)"
            " FROM plt01.led_postings p"
            " JOIN plt01.led_journals j ON j.journal_id = p.journal_id"
            " WHERE p.account_id = %s AND j.posted_on <= %s",
            (account_id, today),
        ).fetchone()
    signed = int(row[0]) if row else 0
    return {
        "account_id": account_id, "account_code": account["account_code"],
        "account_kind": account["account_kind"],
        "account_class": accounts.KIND_BY_KEY[account["account_kind"]].account_class,
        "normal_side": accounts.normal_side(account["account_kind"]),
        "currency": account["currency"], "as_of": today.isoformat(),
        "signed_minor": signed,
        "balance_minor": accounts.signed_increase(account["account_kind"], signed),
        "posting_count": int(row[1]) if row else 0,
    }


def trial_balance(
    pool: Pool, tenant_id: str, *, legal_entity_id: str, currency: str,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Every account's balance, and the proof that the whole ledger balances.

    **The totals are the point.** Every journal balances, so the debits and the credits of all
    of them are equal by construction -- and a trial balance where they are not is a ledger that
    lost rows. `balanced` is that comparison, returned rather than asserted: a read that threw
    would be a read nobody could use to *diagnose* the problem.

    **Both predicates are in the `WHERE`, and that is the whole of this function's history.**
    They started in the `ON` clause of a `LEFT JOIN`, where a posting whose journal matched
    neither the entity nor the date survived the join with NULL journal columns and was summed
    anyway -- so a per-entity trial balance carried the other entity's journals, and a
    period-end one carried journals posted after the date it was asked for, which is the figure
    a close is signed off against moving whenever a later month is posted. The subquery is
    what makes "no postings" and "no matching postings" the same answer while the filter still
    bites.
    """
    today = as_of or _today()
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT a.account_id, a.account_code, a.account_kind, a.status,"
            " coalesce(("
            "   SELECT sum(p.amount_minor) FROM plt01.led_postings p"
            "     JOIN plt01.led_journals j ON j.journal_id = p.journal_id"
            "    WHERE p.account_id = a.account_id"
            "      AND j.posted_on <= %s AND j.legal_entity_id = %s), 0)"
            " FROM plt01.led_accounts a"
            " WHERE a.currency = %s"
            # An account belonging to another entity is not on this entity's trial balance,
            # even at zero: a reader cannot tell a zero balance from a foreign account.
            "   AND (a.legal_entity_id IS NULL OR a.legal_entity_id = %s)"
            " ORDER BY a.account_code",
            (today, legal_entity_id, currency.upper(), legal_entity_id),
        ).fetchall()
    lines = []
    debits = credits = 0
    for row in rows:
        signed = int(row[4])
        if signed > 0:
            debits += signed
        else:
            credits += -signed
        lines.append({
            "account_id": str(row[0]), "account_code": str(row[1]),
            "account_kind": str(row[2]), "status": str(row[3]),
            "account_class": accounts.KIND_BY_KEY[str(row[2])].account_class,
            "debit_minor": signed if signed > 0 else 0,
            "credit_minor": -signed if signed < 0 else 0,
            "balance_minor": accounts.signed_increase(str(row[2]), signed),
        })
    return {
        "legal_entity_id": legal_entity_id, "currency": currency.upper(),
        "as_of": today.isoformat(), "lines": lines,
        "debit_total_minor": debits, "credit_total_minor": credits,
        "balanced": debits == credits,
        "difference_minor": debits - credits,
    }


def get_journal(pool: Pool, tenant_id: str, journal_id: str) -> dict[str, Any]:
    """One journal with its postings, which is how a balance is explained."""
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT j.legal_entity_id, j.purpose, j.posted_on, j.currency,"
            " j.control_total_minor, j.source_kind, j.source_ref,"
            " j.corrects_journal_id, j.correction_reason, j.description,"
            " j.occurred_at, j.posted_by, p.period_key, p.status"
            " FROM plt01.led_journals j"
            " JOIN plt01.led_periods p ON p.period_id = j.period_id"
            " WHERE j.journal_id = %s",
            (journal_id,),
        ).fetchone()
        if row is None:
            raise NotFound("journal_not_found")
        postings = conn.execute(
            "SELECT p.line_number, p.account_id, a.account_code, a.account_kind,"
            " p.amount_minor, p.memo, p.subject_person_id"
            " FROM plt01.led_postings p"
            " JOIN plt01.led_accounts a ON a.account_id = p.account_id"
            " WHERE p.journal_id = %s ORDER BY p.line_number",
            (journal_id,),
        ).fetchall()
        corrected_by = conn.execute(
            "SELECT journal_id FROM plt01.led_journals WHERE corrects_journal_id = %s",
            (journal_id,),
        ).fetchone()
    return {
        "journal_id": journal_id, "legal_entity_id": str(row[0]),
        "purpose": str(row[1]), "posted_on": row[2].isoformat(),
        "currency": str(row[3]), "control_total_minor": int(row[4]),
        "source_kind": str(row[5]), "source_ref": str(row[6]),
        "corrects_journal_id": str(row[7]) if row[7] else None,
        "correction_reason": str(row[8]) if row[8] else None,
        "corrected_by_journal_id": str(corrected_by[0]) if corrected_by else None,
        "description": str(row[9]), "occurred_at": row[10].isoformat(),
        "posted_by": str(row[11]), "period_key": str(row[12]),
        "period_status": str(row[13]),
        "postings": [
            {"line_number": int(p[0]), "account_id": str(p[1]),
             "account_code": str(p[2]), "account_kind": str(p[3]),
             "amount_minor": int(p[4]), "side": accounts.side_of(int(p[4])),
             "memo": str(p[5]) if p[5] else None,
             "subject_person_id": str(p[6]) if p[6] else None}
            for p in postings],
    }


def export_period(
    pool: Pool, tenant_id: str, *, legal_entity_id: str, period_key: str,
    target_system: str, target_ref: str, currency: str, idempotency_key: str,
    actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """ReconcileControlTotal, as an export record. COM-04-R06.

    **The export is a record of what was sent, not the file.** This build has no object store
    and no accounting integration; what it can do honestly is state the control totals a batch
    carried, so the question "did last November reach the accounts system, and with what
    figures" has an answer. A row claiming a file that was never produced would be the
    fabricated-evidence shape this codebase has been bitten by five times -- which is why
    `target_ref` is the *other* system's handle, supplied by whatever did the sending.

    **A period that is not closed cannot be exported.** An export of an open month is a figure
    that will change after it was filed, which is the whole thing COM-04-R06's lock exists to
    prevent.
    """
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    with tenant_scope(pool, tenant_id) as conn:
        period = conn.execute(
            "SELECT period_id, status FROM plt01.led_periods"
            " WHERE legal_entity_id = %s AND period_key = %s",
            (legal_entity_id, period_key),
        ).fetchone()
        if period is None:
            raise NotFound("financial_period_not_found")
        if str(period[1]) not in ("closed", "reopened"):
            raise Conflict(
                f"the period {period_key} is {period[1]} and an export of an open period "
                f"is a figure that changes after it was filed")
        prior = conn.execute(
            "SELECT export_id, journal_count, debit_total_minor FROM plt01.led_exports"
            " WHERE idempotency_key = %s",
            (idempotency_key.strip(),),
        ).fetchone()
        if prior is not None:
            return {"export_id": str(prior[0]), "journal_count": int(prior[1]),
                    "debit_total_minor": int(prior[2]), "repeated": True}
        totals = conn.execute(
            "SELECT count(DISTINCT j.journal_id),"
            " coalesce(sum(p.amount_minor) FILTER (WHERE p.amount_minor > 0), 0),"
            " coalesce(-sum(p.amount_minor) FILTER (WHERE p.amount_minor < 0), 0)"
            " FROM plt01.led_journals j"
            " JOIN plt01.led_postings p ON p.journal_id = j.journal_id"
            " WHERE j.period_id = %s AND j.currency = %s",
            (str(period[0]), currency.upper()),
        ).fetchone()
        assert totals is not None
        if int(totals[0]) == 0:
            raise Conflict(
                f"the period {period_key} has no {currency.upper()} journals to export")
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.led_exports
                    (tenant_id, period_id, target_system, target_ref, journal_count,
                     debit_total_minor, credit_total_minor, currency, exported_by,
                     idempotency_key, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING export_id
                """,
                (tenant_id, str(period[0]), target_system, target_ref, int(totals[0]),
                 int(totals[1]), int(totals[2]), currency.upper(), actor_id,
                 idempotency_key.strip(), correlation_id),
            ).fetchone()
        except errors.CheckViolation as e:
            # `led_exports_balances` is the one that fires here, and it means the query lost
            # rows rather than that a journal was unbalanced -- which the trigger made
            # impossible. Worth the distinct message.
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
    return {"export_id": str(row[0]), "period_key": period_key,
            "journal_count": int(totals[0]), "debit_total_minor": int(totals[1]),
            "credit_total_minor": int(totals[2]), "currency": currency.upper(),
            "repeated": False}


# ------------------------------------------------------------------ the MOD-017 bridge
#
# **These four take a connection, because they exist to be called from inside MOD-017's own
# transactions.** An invoice without its receivable, a payment without its clearing entry or a
# refund without its reversal is a balance the ledger does not know about -- and the only way
# to mean "together" is the caller's transaction. This is the whole reason `post_journal` has
# the signature it has.
#
# **A tenant with no chart of accounts is not an error.** The chart is tenant configuration and
# a tenant mid-setup must not find that its till has stopped working, so a missing account
# leaves the business write intact and reports why rather than refusing. What makes that
# honest rather than silent is that the caller is *told*: every bridged command returns either
# a `ledger_journal_id` or a `ledger_skipped_because`, and a test asserts the posting happens
# once the chart exists.

#: What may sit opposite a wallet movement. Cash the member paid in comes from a cash, bank or
#: clearing account; value the tenant gave away is `contra_revenue`; value spent is revenue
#: earned. **Never a wallet liability**, which is what made +N/-N on one account possible, and
#: never a receivable, which is what turned a giveaway into a debt the member owes.
WALLET_COUNTERPART: tuple[str, ...] = (
    "cash", "bank", "provider_clearing", "contra_revenue", "revenue", "unearned_revenue",
)

#: What each bridged posting needs from the chart, by the account kinds it moves between.
_BRIDGE_ACCOUNTS: dict[str, tuple[str, ...]] = {
    "invoice": ("receivable", "revenue", "tax_payable", "unearned_revenue"),
    "payment": ("receivable", "provider_clearing", "cash"),
    "refund": ("receivable", "provider_clearing", "cash"),
    "credit_note": ("receivable", "contra_revenue", "tax_payable"),
}


def chart_for(
    conn: Connection[Any], *, currency: str, kinds: tuple[str, ...],
    legal_entity_id: str | None = None,
) -> dict[str, str] | None:
    """The account of each kind in that currency for that entity, or None if any is missing.

    Tenant-wide means `location_id IS NULL`: a till's cash account is per location and is named
    explicitly by whatever knows which till, while a receivable or a tax liability is one
    account for the entity. Returning None rather than raising is what lets the bridge skip
    rather than refuse.

    **An account scoped to the entity wins over the tenant-wide one, and the choice is
    ordered.** The first version filtered on neither the entity nor anything deterministic and
    filled a dict in row order, so which revenue account an invoice credited was the planner's
    choice -- a reviewer watched the same four invoices land in `REV` on one run and
    `REV-RETAIL` on the next -- and a two-entity tenant's receivable landed in the *other*
    entity's account, which forecloses the per-entity separation COM-03-R07 needs and this
    docstring already claimed ("one account for the entity"). A tenant that keeps two accounts
    of one kind and no entity scope gets the lower code, stated rather than discovered.
    """
    found: dict[str, str] = {}
    for row in conn.execute(
        "SELECT account_kind, account_id FROM plt01.led_accounts"
        " WHERE account_kind = ANY(%s) AND currency = %s AND status = 'active'"
        "   AND location_id IS NULL"
        "   AND (legal_entity_id IS NULL OR legal_entity_id = %s)"
        " ORDER BY account_kind, (legal_entity_id IS NULL), account_code",
        (sorted(set(kinds)), currency.upper(), legal_entity_id),
    ).fetchall():
        found.setdefault(str(row[0]), str(row[1]))
    if set(found) != set(kinds):
        return None
    return found


def post_invoice(
    conn: Connection[Any], tenant_id: str, *, invoice_id: str, legal_entity_id: str,
    net_minor: int, tax_minor: int, currency: str, issued_on: date,
    document_number: str, actor_id: str, correlation_id: str,
    subject_person_id: str | None = None,
    unearned_minor: int = 0,
) -> dict[str, Any]:
    """The receivable an issued invoice creates. Called from MOD-017's own transaction.

    **`unearned_minor` is the part of the net that has not been delivered yet**, and it is the
    whole of paragraph 1695 in one argument: a year's membership billed in January credits
    `unearned_revenue` rather than `revenue`, and a recognition schedule moves it across as the
    service is delivered. The caller supplies it because only the caller knows what was sold;
    zero -- a retail sale, a joining fee -- is the ordinary case and credits revenue outright.
    """
    chart = chart_for(conn, currency=currency,
                      kinds=_BRIDGE_ACCOUNTS["invoice"],
                      legal_entity_id=legal_entity_id)
    if chart is None:
        return {"posted": False,
                "ledger_skipped_because": "this tenant has no ledger chart in "
                                          f"{currency.upper()}"}
    if unearned_minor < 0 or unearned_minor > net_minor:
        raise InvalidRequest(
            "the unearned part of an invoice is between nothing and its whole net")
    earned = net_minor - unearned_minor
    lines: list[dict[str, Any]] = [
        {"account_id": chart["receivable"], "amount_minor": net_minor + tax_minor,
         "subject_person_id": subject_person_id, "memo": document_number},
    ]
    if earned:
        lines.append({"account_id": chart["revenue"], "amount_minor": -earned,
                      "subject_person_id": subject_person_id,
                      "memo": document_number})
    if unearned_minor:
        lines.append({"account_id": chart["unearned_revenue"],
                      "amount_minor": -unearned_minor,
                      "subject_person_id": subject_person_id,
                      "memo": f"{document_number} (not yet delivered)"})
    if tax_minor:
        lines.append({"account_id": chart["tax_payable"], "amount_minor": -tax_minor,
                      "subject_person_id": subject_person_id,
                      "memo": f"{document_number} tax"})
    posted = post_journal(
        conn, tenant_id, legal_entity_id=legal_entity_id, lines=lines,
        posted_on=issued_on, currency=currency, source_kind="invoice",
        fall_back_to_open=True,
        source_ref=invoice_id, description=f"invoice {document_number}",
        idempotency_key=f"invoice-{invoice_id}", actor_id=actor_id,
        correlation_id=correlation_id)
    return {"posted": True, "ledger_journal_id": posted["journal_id"],
            "unearned_minor": unearned_minor, "earned_minor": earned}


def post_credit_note(
    conn: Connection[Any], tenant_id: str, *, invoice_id: str, legal_entity_id: str,
    net_minor: int, tax_minor: int, currency: str, issued_on: date,
    document_number: str, actor_id: str, correlation_id: str,
    subject_person_id: str | None = None,
) -> dict[str, Any]:
    """A credit note's effect: revenue given back and a receivable reduced.

    **`contra_revenue`, not a negative posting to revenue.** The two net to the same figure and
    they answer different questions: a revenue account read on its own should say what was sold,
    and what was given back belongs beside it where somebody can see how much of the month was
    credits. Paragraph 115 names the account for exactly this.
    """
    chart = chart_for(conn, currency=currency,
                      kinds=_BRIDGE_ACCOUNTS["credit_note"],
                      legal_entity_id=legal_entity_id)
    if chart is None:
        return {"posted": False,
                "ledger_skipped_because": "this tenant has no ledger chart in "
                                          f"{currency.upper()}"}
    lines: list[dict[str, Any]] = [
        {"account_id": chart["contra_revenue"], "amount_minor": net_minor,
         "subject_person_id": subject_person_id, "memo": document_number},
        {"account_id": chart["receivable"], "amount_minor": -(net_minor + tax_minor),
         "subject_person_id": subject_person_id, "memo": document_number},
    ]
    if tax_minor:
        lines.insert(1, {"account_id": chart["tax_payable"], "amount_minor": tax_minor,
                         "subject_person_id": subject_person_id,
                         "memo": f"{document_number} tax"})
    posted = post_journal(
        conn, tenant_id, legal_entity_id=legal_entity_id, lines=lines,
        posted_on=issued_on, currency=currency, source_kind="credit_note",
        fall_back_to_open=True,
        source_ref=invoice_id, description=f"credit note {document_number}",
        idempotency_key=f"credit-note-{invoice_id}", actor_id=actor_id,
        correlation_id=correlation_id)
    return {"posted": True, "ledger_journal_id": posted["journal_id"]}


def allocate_payment(
    conn: Connection[Any], tenant_id: str, *, payment_id: str, legal_entity_id: str,
    amount_minor: int, currency: str, method: str, received_on: date,
    actor_id: str, correlation_id: str, subject_person_id: str | None = None,
    cash_account_id: str | None = None,
) -> dict[str, Any]:
    """AllocatePayment: money arrived, so a receivable goes down and an asset goes up.

    **Which asset depends on how the money came.** Cash lands in a till -- a per-location
    account, so the caller names it -- and everything else lands in `provider_clearing`, which
    is where it stays until the provider settles it to the bank. That clearing account is the
    one COM-04-R04's settlement import reconciles against, and it only means anything if
    payments land there rather than going straight to `bank`.
    """
    chart = chart_for(conn, currency=currency, kinds=("receivable",),
                      legal_entity_id=legal_entity_id)
    if chart is None:
        return {"posted": False,
                "ledger_skipped_because": "this tenant has no ledger chart in "
                                          f"{currency.upper()}"}
    if method == "cash":
        if cash_account_id is None:
            return {"posted": False,
                    "ledger_skipped_because": "a cash payment needs the till's account"}
        # Unchecked, a cash payment named the tax liability account: the receivable cleared,
        # the drawer never moved, and the tax owed to an authority went negative by exactly
        # the cash collected.
        _account_of_kind(conn, cash_account_id, ("cash",), currency=currency, role="debit")
        asset = cash_account_id
    else:
        clearing = chart_for(conn, currency=currency, kinds=("provider_clearing",),
                             legal_entity_id=legal_entity_id)
        if clearing is None:
            return {"posted": False,
                    "ledger_skipped_because": "this tenant has no provider clearing "
                                              f"account in {currency.upper()}"}
        asset = clearing["provider_clearing"]
    posted = post_journal(
        conn, tenant_id, legal_entity_id=legal_entity_id,
        lines=[
            {"account_id": asset, "amount_minor": amount_minor,
             "subject_person_id": subject_person_id, "memo": f"payment by {method}"},
            {"account_id": chart["receivable"], "amount_minor": -amount_minor,
             "subject_person_id": subject_person_id, "memo": f"payment by {method}"},
        ],
        posted_on=received_on, currency=currency, source_kind="payment",
        fall_back_to_open=True,
        source_ref=payment_id, description=f"payment by {method}",
        idempotency_key=f"payment-{payment_id}", actor_id=actor_id,
        correlation_id=correlation_id)
    return {"posted": True, "ledger_journal_id": posted["journal_id"]}


def post_refund(
    conn: Connection[Any], tenant_id: str, *, refund_id: str, legal_entity_id: str,
    amount_minor: int, currency: str, refunded_on: date, actor_id: str,
    correlation_id: str, subject_person_id: str | None = None,
) -> dict[str, Any]:
    """Money going back: the clearing asset goes down and the receivable comes back.

    **The receivable comes back rather than revenue going down.** A refund without a credit note
    means the invoice still stands and the member owes it again, which is MOD-017's own reading
    -- and a refund that is *meant* to leave no debt is a refund plus a credit note, which posts
    its own `contra_revenue`. Collapsing the two here would make every refund reduce revenue,
    including the ones that do not.
    """
    chart = chart_for(conn, currency=currency,
                      kinds=("receivable", "provider_clearing"),
                      legal_entity_id=legal_entity_id)
    if chart is None:
        return {"posted": False,
                "ledger_skipped_because": "this tenant has no ledger chart in "
                                          f"{currency.upper()}"}
    posted = post_journal(
        conn, tenant_id, legal_entity_id=legal_entity_id,
        lines=[
            {"account_id": chart["receivable"], "amount_minor": amount_minor,
             "subject_person_id": subject_person_id, "memo": "refund"},
            {"account_id": chart["provider_clearing"], "amount_minor": -amount_minor,
             "subject_person_id": subject_person_id, "memo": "refund"},
        ],
        posted_on=refunded_on, currency=currency, source_kind="refund",
        fall_back_to_open=True,
        source_ref=refund_id, description="refund", idempotency_key=f"refund-{refund_id}",
        actor_id=actor_id, correlation_id=correlation_id)
    return {"posted": True, "ledger_journal_id": posted["journal_id"]}
