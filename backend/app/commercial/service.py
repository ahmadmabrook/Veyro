"""MOD-017 COM-01 and COM-03: the I/O, and the locks that make the decisions safe.

The decisions are in `lifecycle`, `entitlements`, `invoicing` and `collections` and do no I/O.
This module holds the transactions, and four things about it are load-bearing:

* **A reservation takes a lock on its grant before it counts.** `SELECT ... FOR UPDATE` on
  `mem_entitlement_grants`, then sum the ledger, then insert. MOD-016 shipped the
  count-then-insert version for coupons and a reviewer ran six concurrent redemptions of a
  single-use code and had four accepted. The lock is the narrowest that makes the count stable:
  it serialises draws on one grant and nothing else.

* **A fiscal serial is allocated under a lock and never skips.** `SELECT ... FOR UPDATE` on
  `fin_fiscal_series`, then `last_serial + 1`. A sequence would be faster and would leave gaps
  on rollback, and a gap in a tax series is something an authority asks about.

* **Every event is appended in the transaction that caused it.** `append_event` takes the
  connection, which is MOD-010's whole design: a control and the state it bounds commit
  together or the event is a separate fact that can fail on its own.

* **A refusal that had to be recorded is raised after the commit.** `tenant_scope` rolls back
  when the block raises, so a path that writes evidence and then refuses would throw the
  evidence away. The `_settled` shape exists in MOD-007, MOD-008 and MOD-013 for the same
  reason and is used here wherever a refusal leaves a record.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from psycopg import Connection, errors

from app.commercial import collections, entitlements, invoicing, lifecycle, reporting
from app.db import Pool, tenant_scope
from app.errors import Conflict, InvalidRequest, NotFound, ServiceError
from app.events import service as events
from app.ledger import service as ledger


def _now() -> datetime:
    return datetime.now(UTC)


def _today() -> date:
    return _now().date()


def _check_name(error: errors.CheckViolation) -> str:
    name = getattr(error.diag, "constraint_name", None)
    return str(name) if name else "constraint_violation"


def _append(
    conn: Connection[Any], tenant_id: str, event_type: str, aggregate_type: str,
    aggregate_id: str, payload: dict[str, Any], *, correlation_id: str, actor_id: str,
) -> None:
    """Append an event in the caller's transaction, which is MOD-010's whole design."""
    events.append_event(
        conn, tenant_id, event_type=event_type, aggregate_type=aggregate_type,
        aggregate_id=aggregate_id, payload=payload, correlation_id=correlation_id,
        actor_id=actor_id)


# ------------------------------------------------------------------ contracts and terms

def draft_contract_version(
    pool: Pool, tenant_id: str, *, contract_key: str, body: str,
    minimum_term_months: int, notice_days: int, renewal_mode: str,
    cancellation_mode: str, freeze_days_per_year: int, grace_days: int,
    actor_id: str, correlation_id: str, locale: str = "en",
    early_termination_months: int | None = None,
) -> dict[str, Any]:
    """Write a contract version as a draft. It is not signable until somebody else publishes it.

    **Two acts, not one.** The first version of this module wrote and published in a single
    command, and argued for it: "a version that existed as a draft for a moment is a version an
    agreement could have been signed against with nobody having approved the terms." That
    argument was false here -- `create_agreement` resolves only a *published* version, so a
    draft is unsignable by construction -- and it bought a real cost, because the one command
    made the author and the publisher the same person by definition.

    This is the prose a member is held to and the policy numbers every lifecycle decision is
    measured against, published under the tenant's name to everybody who signs on these terms.
    MOD-013 reached the same conclusion about notification templates and MOD-016 about a
    discount above the threshold: the act that commits the tenant is a second act by a second
    person. `mem_contract_versions_publisher_is_not_author` is the half the service cannot
    weaken.

    The version number is allocated from what exists, under a lock on the key's highest row, so
    two concurrent drafts of the same key do not both become version 3.
    """
    if not body.strip():
        raise InvalidRequest("a_contract_version_states_its_terms")
    if cancellation_mode not in ("immediate", "end_of_notice", "end_of_term"):
        raise InvalidRequest(f"unknown_cancellation_mode_{cancellation_mode}")
    if renewal_mode not in ("manual", "automatic", "none"):
        raise InvalidRequest(f"unknown_renewal_mode_{renewal_mode}")
    with tenant_scope(pool, tenant_id) as conn:
        # **The lock is on the highest existing row, not on an aggregate.** The first version
        # of this wrote `SELECT coalesce(max(version), 0) ... FOR UPDATE`, which PostgreSQL
        # refuses outright -- `FOR UPDATE is not allowed with aggregate functions` -- so it was
        # a lock that could never have run. Locking the latest row serialises every publication
        # after the first; for the very first there is no row to lock and the unique index
        # decides the race, which is the same answer by a different mechanism.
        highest = conn.execute(
            "SELECT version FROM plt01.mem_contract_versions WHERE contract_key = %s"
            " ORDER BY version DESC LIMIT 1 FOR UPDATE",
            (contract_key,),
        ).fetchone()
        version = (int(highest[0]) if highest else 0) + 1
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.mem_contract_versions
                    (tenant_id, contract_key, version, body, locale, minimum_term_months,
                     notice_days, renewal_mode, cancellation_mode, freeze_days_per_year,
                     grace_days, early_termination_months, status, created_by,
                     correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'draft', %s, %s)
                RETURNING contract_version_id
                """,
                (tenant_id, contract_key, version, body, locale, minimum_term_months,
                 notice_days, renewal_mode, cancellation_mode, freeze_days_per_year,
                 grace_days, early_termination_months, actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_contract_version_was_drafted_by_somebody_else") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        version_id = str(row[0])
    return {"contract_version_id": version_id, "contract_key": contract_key,
            "version": version, "status": "draft",
            "early_termination_months": early_termination_months}


def publish_contract_version(
    pool: Pool, tenant_id: str, contract_version_id: str, *, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Publish a drafted contract version, by somebody other than its author.

    **The refusal is here and in the schema, and the schema is the one that counts.** The
    service's choice of SQL is not the writer that constraint exists for; this check is so the
    caller gets a sentence rather than a constraint name.

    A republication of an already-published version is the idempotent answer rather than a
    conflict: the publish button pressed twice is the ordinary case, and a command that refuses
    its own completed work is one a client keeps retrying.
    """
    moment = _now()
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT contract_key, version, status, created_by"
            " FROM plt01.mem_contract_versions WHERE contract_version_id = %s FOR UPDATE",
            (contract_version_id,),
        ).fetchone()
        if row is None:
            raise NotFound("contract_version_not_found")
        contract_key, version, status, author = (
            str(row[0]), int(row[1]), str(row[2]), str(row[3]))
        if status == "published":
            return {"contract_version_id": contract_version_id,
                    "contract_key": contract_key, "version": version,
                    "status": "published", "repeated": True}
        if status != "draft":
            raise Conflict(f"this_contract_version_is_{status}")
        if author == actor_id:
            raise Conflict("the_author_of_a_contract_version_does_not_publish_it")
        try:
            conn.execute(
                "UPDATE plt01.mem_contract_versions SET status = 'published',"
                " published_at = %s, published_by = %s, publish_correlation_id = %s"
                " WHERE contract_version_id = %s AND status = 'draft'",
                (moment, actor_id, correlation_id, contract_version_id))
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        _append(conn, tenant_id, "contract_version.published", "contract",
                contract_version_id,
                {"contract_version_id": contract_version_id, "contract_key": contract_key,
                 "version": version},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"contract_version_id": contract_version_id, "contract_key": contract_key,
            "version": version, "status": "published", "repeated": False}


def define_membership_terms(
    pool: Pool, tenant_id: str, *, product_id: str, contract_key: str,
    membership_kind: str, billing_period: str, actor_id: str, correlation_id: str,
    installment_count: int | None = None, prepaid_days: int | None = None,
) -> dict[str, Any]:
    """Attach membership terms to a catalogue product.

    **The product must be a membership.** The catalogue says what a thing is; terms on a retail
    SKU would be a contract nobody could fulfil, and refusing it here is cheaper than
    discovering it at the point of sale.
    """
    with tenant_scope(pool, tenant_id) as conn:
        product = conn.execute(
            "SELECT product_type, status FROM plt01.cat_products WHERE product_id = %s",
            (product_id,),
        ).fetchone()
        if product is None:
            raise NotFound("product_not_found")
        if str(product[0]) != "membership":
            raise Conflict(f"a_{product[0]}_product_does_not_take_membership_terms")
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.mem_membership_terms
                    (tenant_id, product_id, contract_key, membership_kind, billing_period,
                     installment_count, prepaid_days, is_off_peak, status, created_by,
                     correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active', %s, %s)
                RETURNING membership_terms_id
                """,
                (tenant_id, product_id, contract_key, membership_kind, billing_period,
                 installment_count, prepaid_days, membership_kind == "off_peak",
                 actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_product_already_has_membership_terms") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
    return {"membership_terms_id": str(row[0]), "product_id": product_id,
            "membership_kind": membership_kind}


# ------------------------------------------------------------------ agreements

def current_agreement(conn: Connection[Any], membership: dict[str, Any]) -> str:
    """The agreement this membership is on **now**, which is not the one it points at.

    **`mem_memberships.agreement_id` is the chain's root and is immutable by grant.** That is
    deliberate: what the member originally agreed to does not move, which is what makes "what
    did they agree to in March" answerable from the row rather than from a history. What they
    are on *now* is derived by walking `mem_agreements.supersedes_agreement_id` forward --
    the column whose own comment says it is "for an upgrade, downgrade or transfer ... so the
    chain answers what did this member have in March".

    **This function exists because nothing followed that chain and the write path already
    did.** `create_agreement` takes `supersedes_agreement_id` and
    `POST /memberships/agreements` exposes it, so a superseding agreement was writable today
    -- and all five readers of a membership's terms went straight to the root. After an
    upgrade the freeze allowance was counted against the original contract's
    `freeze_days_per_year`, the cancellation fee against the original `amount_minor` and
    `minimum_term_ends_on`, and the notice period and the buy-out against a contract version
    the member had moved off. Every figure this module discloses, answering from the agreement
    they left, with no adversary and one route call.

    **One definition, read by every caller**, because two would be MOD-018's
    one-module-two-definitions finding on the figure a member disputes.

    **Bounded, and a cycle cannot hang it.** `mem_agreements_not_self` refuses a one-step
    loop and `mem_agreements_one_live_supersession` refuses a fork, and neither can see a
    two-step cycle -- A superseded by B and B superseded by A are two rows with distinct
    predecessors, so both are writable. The walk therefore stops at `_AGREEMENT_CHAIN` and
    **refuses rather than quoting whichever link it had reached**: a figure from the middle of
    a chain is a figure nobody agreed to, which is worse than an error on the one read a
    member disputes. A listing read refuses on the same condition, through the same depth.
    """
    row = conn.execute(
        f"WITH RECURSIVE {_WALK_FROM_ONE} SELECT agreement_id, depth FROM walk"
        " ORDER BY depth DESC LIMIT 1",
        (membership["agreement_id"],),
    ).fetchone()
    assert row is not None  # the seed row is the agreement itself
    if int(row[1]) >= _AGREEMENT_CHAIN:
        raise Conflict("agreement_chain_too_long")
    return str(row[0])


#: How far a supersession walk goes before it refuses. Thirty is more product changes than any
#: membership has, and the bound is what keeps a chain a caller writes link by link from
#: becoming a loop nobody can read past. It is interpolated into the SQL below rather than
#: written there, because a bound in two places is a bound that can disagree with itself.
_AGREEMENT_CHAIN = 30

#: **The one recursive step, read by both walks.** Which row comes next is the whole rule, and
#: two copies of it would be MOD-018's one-module-two-definitions finding on the figures a
#: member disputes -- so the single-membership walk and the listing walk are built from this
#: string rather than each spelling it out.
#:
#: **`void` is the agreement domain's own word.** The first version filtered
#: `status <> 'cancelled'` -- a *membership* status, not an agreement one, so the filter
#: matched every row and a voided upgrade would still have governed. `0025`'s partial unique
#: index carries the same predicate, so the index and the walk agree about which successor is
#: live.
_SUPERSESSION_STEP = (
    " JOIN plt01.mem_agreements a"
    "   ON a.supersedes_agreement_id = w.agreement_id AND a.status <> 'void'"
    f" WHERE w.depth < {_AGREEMENT_CHAIN}")

#: One membership's chain, seeded from the root agreement id the caller passes.
_WALK_FROM_ONE = (
    "walk AS ("
    " SELECT %s::uuid AS agreement_id, 0 AS depth"
    " UNION ALL"
    " SELECT a.agreement_id, w.depth + 1 FROM walk w"
    + _SUPERSESSION_STEP + ")")

def _walk_from(seed_where: str) -> str:
    """Several memberships' chains at once, for a read that joins the live agreement per row.

    **Resolving per row would be one query per membership**, and a list is the one place that
    cost is not payable -- so this is a recursive CTE and `DISTINCT ON ... depth DESC` takes
    each chain's deepest link. `depth` is carried out so a listing can refuse a truncated
    chain on the same condition the single read does.

    **The seed is bounded by the caller's own predicate**, not left as every membership in the
    tenant. An unbounded seed is a full scan of `mem_memberships` plus a recursive join on
    every page view of the member list, which is the busiest read in the module -- and the
    predicate is already written, because each caller filters on the same columns. The seed's
    parameters therefore come *first* in the tuple, before the outer query's.
    """
    return (
        "walk AS ("
        " SELECT m.membership_id, m.agreement_id, 0 AS depth"
        " FROM plt01.mem_memberships m"
        f" WHERE {seed_where}"
        " UNION ALL"
        " SELECT w.membership_id, a.agreement_id, w.depth + 1 FROM walk w"
        + _SUPERSESSION_STEP + "),"
        " live AS (SELECT DISTINCT ON (membership_id) membership_id, agreement_id, depth"
        " FROM walk ORDER BY membership_id, depth DESC)")


def _refuse_a_truncated_chain(rows: Sequence[Any], depth_at: int) -> None:
    """Refuse a listing whose data contains a supersession chain longer than the walk.

    **The same condition and the same error as the single read**, because a rule with two
    behaviours is a rule two callers can disagree about. The only way to reach the bound is a
    cycle -- two agreements superseding each other, which `mem_agreements_not_self` and
    `mem_agreements_one_live_supersession` both admit -- so this is a data defect somebody has
    to fix, and quoting the thirtieth link's amount as the current one would be this build's
    fabricated-figure shape in the place a manager reads the business.

    It withholds correct rows along with the bad one, which is deliberate: a list that refuses
    says the figures cannot be trusted, and a list that marks one row asks every surface to
    learn a field it will not read.
    """
    if any(int(r[depth_at]) >= _AGREEMENT_CHAIN for r in rows):
        raise Conflict("agreement_chain_too_long")


def _terms_of(conn: Connection[Any], agreement_id: str) -> lifecycle.Terms:
    """The contract terms this agreement was signed under.

    **Read from the version the agreement names, never from the current version of the key.**
    A signature means the member agreed to *those* terms, so a lifecycle decision measured
    against whatever has been published since would be measured against something nobody
    agreed to -- which is the whole reason `contract_version_id` is pinned on the agreement
    rather than the key being re-resolved.
    """
    row = conn.execute(
        "SELECT c.minimum_term_months, c.notice_days, c.renewal_mode,"
        " c.cancellation_mode, c.freeze_days_per_year, c.grace_days,"
        " c.early_termination_months"
        " FROM plt01.mem_agreements a"
        " JOIN plt01.mem_contract_versions c"
        "   ON c.contract_version_id = a.contract_version_id"
        " WHERE a.agreement_id = %s",
        (agreement_id,),
    ).fetchone()
    if row is None:
        raise NotFound("agreement_not_found")
    return lifecycle.Terms(
        minimum_term_months=int(row[0]), notice_days=int(row[1]),
        renewal_mode=str(row[2]), cancellation_mode=str(row[3]),
        freeze_days_per_year=int(row[4]), grace_days=int(row[5]),
        early_termination_months=(None if row[6] is None else int(row[6])))


def create_agreement(
    pool: Pool, tenant_id: str, *, person_id: str, membership_terms_id: str,
    variant_id: str, amount_minor: int, currency: str, starts_on: date,
    actor_id: str, correlation_id: str, price_resolution_id: str | None = None,
    supersedes_agreement_id: str | None = None,
) -> dict[str, Any]:
    """CreateMembershipAgreement: the contract, unsigned.

    **The contract version is resolved here and pinned, not supplied.** A caller able to name
    the version would be able to name an older one with a shorter minimum term -- the authority
    bought with a body field, which is the shape this repository has now shipped four times.
    The terms say which contract key applies and the latest published version of that key is
    what the member signs.

    **The minimum term is computed at signing and stored.** The version may be retired later
    and the member's commitment does not move with it, which is also why `lifecycle.Terms` is
    read from the pinned version everywhere afterwards.

    **A cited price resolution is the authority on the figure, not a decoration beside it.**
    The first version took `amount_minor`, `currency` and `price_resolution_id` from the
    caller and never compared them, so an agreement could cite MOD-016's receipt for 45.00 JOD
    and record 4.50 -- with the resolution id on the row making the figure read as priced and
    approved. That is this repository's recurring finding stated exactly: a control keyed on a
    value the caller supplies, shape-checked and never checked for correspondence. When a
    resolution is cited its own `final_amount_minor`, `currency` and `variant_id` are what get
    written, and a resolution for a different variant is refused rather than quietly used.

    An agreement with no resolution cited keeps the caller's figure, because there is no other
    source for a negotiated or legacy price. That is what the financial action class on
    `membership.agreement.write` buys, and it is a real difference between the two paths: one
    is a price MOD-016 decided, the other is a price somebody typed.
    """
    with tenant_scope(pool, tenant_id) as conn:
        terms = conn.execute(
            "SELECT contract_key, status FROM plt01.mem_membership_terms"
            " WHERE membership_terms_id = %s",
            (membership_terms_id,),
        ).fetchone()
        if terms is None:
            raise NotFound("membership_terms_not_found")
        if str(terms[1]) != "active":
            raise Conflict(f"these_membership_terms_are_{terms[1]}")
        version = conn.execute(
            "SELECT contract_version_id, minimum_term_months FROM plt01.mem_contract_versions"
            " WHERE contract_key = %s AND status = 'published'"
            " ORDER BY version DESC LIMIT 1",
            (str(terms[0]),),
        ).fetchone()
        if version is None:
            raise Conflict("no_published_contract_version_for_these_terms")
        contract_version_id = str(version[0])
        if price_resolution_id is not None:
            resolution = conn.execute(
                "SELECT variant_id, final_amount_minor, currency"
                " FROM plt01.cat_price_resolutions WHERE resolution_id = %s",
                (price_resolution_id,),
            ).fetchone()
            if resolution is None:
                raise NotFound("price_resolution_not_found")
            if str(resolution[0]) != variant_id:
                raise Conflict("this_price_resolution_is_for_another_variant")
            amount_minor, currency = int(resolution[1]), str(resolution[2])
        minimum_term_ends_on = lifecycle.minimum_term_end(
            starts_on, lifecycle.Terms(minimum_term_months=int(version[1])))
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.mem_agreements
                    (tenant_id, person_id, membership_terms_id, contract_version_id,
                     variant_id, price_resolution_id, amount_minor, currency, starts_on,
                     minimum_term_ends_on, supersedes_agreement_id, status, created_by,
                     correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'draft', %s, %s)
                RETURNING agreement_id
                """,
                (tenant_id, person_id, membership_terms_id, contract_version_id,
                 variant_id, price_resolution_id, amount_minor, currency.upper(),
                 starts_on, minimum_term_ends_on, supersedes_agreement_id, actor_id,
                 correlation_id),
            ).fetchone()
        except errors.ForeignKeyViolation as e:
            raise NotFound(_fk_subject(e)) from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        except errors.UniqueViolation:
            # **`mem_agreements_one_live_supersession`, which is what makes the chain a
            # chain.** Two live agreements superseding one predecessor is a fork, and
            # `current_agreement` would then answer whichever the planner returned first --
            # which is MOD-018's unordered-lookup finding on the figures a member disputes.
            # Caught here rather than left to psycopg, because an uncaught unique violation
            # is a 500 telling the caller to try again when the answer is that an upgrade of
            # that agreement already exists.
            raise Conflict("this_agreement_is_already_superseded") from None
        assert row is not None
        agreement_id = str(row[0])
        _append(conn, tenant_id, "membership.created", "agreement", agreement_id,
                {"agreement_id": agreement_id, "person_id": person_id,
                 "membership_terms_id": membership_terms_id,
                 "contract_version_id": contract_version_id},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"agreement_id": agreement_id, "person_id": person_id,
            "contract_version_id": contract_version_id,
            # The figures that were actually written, which are the resolution's when one was
            # cited. A caller that sent its own and got these back is being told so.
            "amount_minor": amount_minor, "currency": currency.upper(),
            "price_resolution_id": price_resolution_id,
            "minimum_term_ends_on": (
                minimum_term_ends_on.isoformat() if minimum_term_ends_on else None),
            "status": "draft"}


def _fk_subject(error: errors.ForeignKeyViolation) -> str:
    """Which parent a foreign-key violation was about.

    A bare `not_found` on a command that names five parents tells the caller nothing, and
    guessing the commonest one is how a caller spends an afternoon on the wrong id.
    """
    name = str(getattr(error.diag, "constraint_name", "") or "")
    for fragment, subject in (
        ("person", "person_not_found"),
        ("variant", "variant_not_found"),
        ("membership_terms", "membership_terms_not_found"),
        ("contract_version", "contract_version_not_found"),
        ("price_resolution", "price_resolution_not_found"),
        ("supersedes", "superseded_agreement_not_found"),
        ("membership", "membership_not_found"),
        ("policy", "entitlement_policy_not_found"),
        ("grant", "grant_not_found"),
        ("invoice", "invoice_not_found"),
        ("payment", "payment_not_found"),
        ("billing_account", "billing_account_not_found"),
        ("legal_entit", "legal_entity_not_found"),
        ("series", "fiscal_series_not_found"),
        ("schedule", "billing_schedule_not_found"),
        ("brand", "brand_not_found"),
        ("location", "location_not_found"),
    ):
        if fragment in name:
            return subject
    return "a_referenced_row_was_not_found"


def sign_agreement(
    pool: Pool, tenant_id: str, agreement_id: str, *, signature_kind: str,
    signature_evidence_ref: str, signed_by_person_id: str, actor_id: str,
    correlation_id: str, at: datetime | None = None,
) -> dict[str, Any]:
    """Record the member's signature. COM-01-R02.

    **A signature is recorded, not performed.** Nothing in this build captures one, so this
    says that a named party signed in a named way at a named time with evidence held
    elsewhere -- the same shape as MOD-012's `validated` install state and MOD-014's contact
    verification, and for the same reason.

    **Only a draft can be signed**, and the guard is on the UPDATE rather than on a prior read:
    a read-then-write would let two concurrent signings both succeed and the second overwrite
    the first's evidence.

    **Who recorded the signature is written down, and the signing is published.** The first
    version took an `actor_id` and a `correlation_id` and used neither, and published nothing --
    so the act that makes a contract binding, with a minimum term and a cancellation fee behind
    it, was the one act in the module with no name on it and no event. MOD-008 audits denials
    rather than allowed actions and `veyro_cp_app` holds nothing in `iam`, so this row was the
    only record there could be. Fifth module to ship that shape.
    """
    moment = at or _now()
    if not signature_evidence_ref.strip():
        raise InvalidRequest("a_signature_cites_its_evidence")
    with tenant_scope(pool, tenant_id) as conn:
        try:
            updated = conn.execute(
                "UPDATE plt01.mem_agreements SET status = 'signed', signed_at = %s,"
                " signed_by_person_id = %s, signed_by = %s, sign_correlation_id = %s,"
                " signature_kind = %s, signature_evidence_ref = %s"
                " WHERE agreement_id = %s AND status = 'draft'"
                " RETURNING person_id",
                (moment, signed_by_person_id, actor_id, correlation_id, signature_kind,
                 signature_evidence_ref.strip(), agreement_id),
            ).fetchone()
        except errors.ForeignKeyViolation as e:
            raise NotFound(_fk_subject(e)) from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        if updated is None:
            raise Conflict("this_agreement_is_unknown_or_not_a_draft")
        _append(conn, tenant_id, "membership.agreement_signed", "agreement", agreement_id,
                {"agreement_id": agreement_id, "person_id": str(updated[0]),
                 "signature_kind": signature_kind, "signed_at": moment.isoformat()},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"agreement_id": agreement_id, "status": "signed",
            "signed_at": moment.isoformat()}


# ------------------------------------------------------------------ the membership lifecycle

def _membership(conn: Connection[Any], membership_id: str) -> dict[str, Any]:
    """The membership's own facts, with its row locked.

    **`FOR UPDATE`**, because every lifecycle command reads the status, decides, and writes --
    and without the lock two concurrent freezes both read `active` and both insert, which the
    one-live-freeze index then refuses as a 500 rather than a conflict.
    """
    row = conn.execute(
        "SELECT agreement_id, person_id, status, starts_on, ends_on,"
        " current_period_start, current_period_end, version"
        " FROM plt01.mem_memberships WHERE membership_id = %s FOR UPDATE",
        (membership_id,),
    ).fetchone()
    if row is None:
        raise NotFound("membership_not_found")
    return {"agreement_id": str(row[0]), "person_id": str(row[1]), "status": str(row[2]),
            "starts_on": row[3], "ends_on": row[4], "current_period_start": row[5],
            "current_period_end": row[6], "version": int(row[7])}


def _recorded_change(
    conn: Connection[Any], membership_id: str, idempotency_key: str, change_kind: str,
) -> dict[str, Any] | None:
    """The change this key already produced, or None.

    **Consulted before the transition is decided, not after.** The first version checked the
    edge first, so a retried `resume` saw the membership already `active`, found no
    `active -> active` edge and answered 409 -- the command was idempotent in the ledger and
    not idempotent to the caller, which is the half that matters. A retry must get the original
    answer back, and a command that refuses its own completed work is one a client will keep
    retrying. Found by this module's own tests before review saw it.
    """
    row = conn.execute(
        "SELECT change_id, membership_id, change_kind, from_status, to_status,"
        " effective_on, disclosed_fee_minor"
        " FROM plt01.mem_lifecycle_changes WHERE idempotency_key = %s",
        (idempotency_key,),
    ).fetchone()
    if row is None:
        return None
    if str(row[1]) != membership_id:
        raise Conflict("this_idempotency_key_belongs_to_another_membership")
    # **And the key has to belong to this command.** Three callers consult this -- freeze,
    # resume and cancel -- and the first version compared only the membership, so a client
    # reusing one key across two of them got the *other* command's change back and was told its
    # own had already happened. A `cancel` answered with the `freeze` that key recorded reads
    # as a cancellation that took effect, and nothing cancelled anything. Same shape as the
    # membership check above and as MOD-016's key reused across two coupon codes.
    if str(row[2]) != change_kind:
        raise Conflict("this_idempotency_key_belongs_to_another_command")
    return {"change_id": str(row[0]), "change_kind": str(row[2]),
            "from_status": str(row[3]), "to_status": str(row[4]),
            "effective_on": row[5],
            "disclosed_fee_minor": int(row[6]) if row[6] is not None else None}


def _record_change(
    conn: Connection[Any], tenant_id: str, *, membership_id: str, change_kind: str,
    from_status: str, to_status: str, effective_on: date, reason: str,
    idempotency_key: str, actor_id: str, correlation_id: str,
    requested_by_person_id: str | None = None,
    disclosed_fee_minor: int | None = None, disclosed_fee_currency: str | None = None,
    invoice_id: str | None = None,
) -> tuple[str, bool]:
    """Insert one lifecycle change, idempotently. Returns `(change_id, repeated)`.

    **`DO NOTHING` then re-read, never a caught `UniqueViolation`.** A caught unique violation
    leaves the transaction aborted, so the SELECT that followed it raised
    `InFailedSqlTransaction` and the caller got a 500 instead of the idempotent answer.
    MOD-013's `_suppress` and MOD-016's `_record_redemption` learned this the same way.
    """
    row = conn.execute(
        """
        INSERT INTO plt01.mem_lifecycle_changes
            (tenant_id, membership_id, change_kind, from_status, to_status, effective_on,
             decided_by, requested_by_person_id, disclosed_fee_minor,
             disclosed_fee_currency, invoice_id, reason, idempotency_key, correlation_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
        RETURNING change_id
        """,
        (tenant_id, membership_id, change_kind, from_status, to_status, effective_on,
         actor_id, requested_by_person_id, disclosed_fee_minor, disclosed_fee_currency,
         invoice_id, reason, idempotency_key, correlation_id),
    ).fetchone()
    if row is not None:
        return str(row[0]), False
    existing = conn.execute(
        "SELECT change_id, membership_id FROM plt01.mem_lifecycle_changes"
        " WHERE idempotency_key = %s",
        (idempotency_key,),
    ).fetchone()
    assert existing is not None
    # **The re-read is checked against this membership.** The key is unique per tenant, so a
    # key reused across two memberships would otherwise return the *other* membership's change
    # and report the command as a successful repeat -- MOD-016's finding, where a key reused
    # across two coupon codes told the caller the second had been redeemed.
    if str(existing[1]) != membership_id:
        raise Conflict("this_idempotency_key_belongs_to_another_membership")
    return str(existing[0]), True


def activate_membership(
    pool: Pool, tenant_id: str, *, agreement_id: str, membership_number: str,
    idempotency_key: str, actor_id: str, correlation_id: str,
    at: date | None = None,
) -> dict[str, Any]:
    """ActivateMembership: create the live membership from a signed agreement.

    **A signed agreement, not a draft.** The signature is what makes the contract exist, and a
    membership activated from an unsigned agreement is access granted under terms nobody
    accepted.
    """
    today = at or _today()
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    with tenant_scope(pool, tenant_id) as conn:
        agreement = conn.execute(
            "SELECT person_id, status, starts_on, signed_at, membership_terms_id"
            " FROM plt01.mem_agreements WHERE agreement_id = %s FOR UPDATE",
            (agreement_id,),
        ).fetchone()
        if agreement is None:
            raise NotFound("agreement_not_found")
        if agreement[3] is None:
            raise Conflict("an_unsigned_agreement_does_not_activate_a_membership")
        if str(agreement[1]) not in ("signed", "active"):
            raise Conflict(f"this_agreement_is_{agreement[1]}")
        # **A retried activation gets the membership it already made.** The first version let
        # the insert hit `mem_memberships_one_per_agreement` and answered 409, so a client
        # whose request timed out after the commit was told the activation had failed -- while
        # `_record_change` beside it was carefully idempotent. The agreement is locked above,
        # so this read and the insert below cannot race.
        existing = conn.execute(
            "SELECT membership_id, membership_number, status, current_period_start,"
            " current_period_end FROM plt01.mem_memberships WHERE agreement_id = %s",
            (agreement_id,),
        ).fetchone()
        if existing is not None:
            return {"membership_id": str(existing[0]), "status": str(existing[2]),
                    "membership_number": str(existing[1]),
                    "current_period_start": existing[3].isoformat(),
                    "current_period_end": existing[4].isoformat(),
                    "repeated": True}
        period = conn.execute(
            "SELECT billing_period FROM plt01.mem_membership_terms"
            " WHERE membership_terms_id = %s",
            (str(agreement[4]),),
        ).fetchone()
        assert period is not None
        starts_on = agreement[2]
        if str(period[0]) == "one_off":
            period_start, period_end = starts_on, starts_on
        else:
            # **The first period is the one before the first renewal**, which is why the
            # argument is the day before the start. `renewal_period` returns the period
            # *after* the date it is given, so passing `starts_on` returned a window opening
            # the day after -- and the first version kept that window's end while overriding
            # its start, making the first period one day longer than every later one. A
            # monthly membership starting on 1 January ran to 1 February, the next period
            # opened on 2 February, and the drift compounded for the life of the membership.
            period_start, period_end = lifecycle.renewal_period(
                current_end=starts_on - _days(1), billing_period=str(period[0]))
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.mem_memberships
                    (tenant_id, agreement_id, person_id, membership_number, status,
                     starts_on, status_effective_on, current_period_start,
                     current_period_end, created_by, correlation_id)
                VALUES (%s, %s, %s, %s, 'pending', %s, %s, %s, %s, %s, %s)
                RETURNING membership_id
                """,
                (tenant_id, agreement_id, str(agreement[0]), membership_number.upper(),
                 starts_on, today, period_start, period_end, actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict(
                "this_agreement_already_has_a_membership_or_the_number_is_taken") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        membership_id = str(row[0])
        lifecycle.check_transition("activation", "pending", "active")
        # **The activation takes effect on the agreement's start date, not on today.**
        # COM-01-R04 asks for effective dating and this is the first place it bites: a
        # membership sold on the first of January and activated on the tenth is active from
        # the first, because that is what the member signed and what they were billed for. The
        # first version used today, so `status_as_of` answered `pending` for every day between
        # the start and the activation -- and a dispute about access in that window is exactly
        # the kind COM-01-R07 exists to settle. Found by this module's own tests.
        change_id, _ = _record_change(
            conn, tenant_id, membership_id=membership_id, change_kind="activation",
            from_status="pending", to_status="active", effective_on=starts_on,
            reason="membership activated from a signed agreement",
            idempotency_key=idempotency_key.strip(), actor_id=actor_id,
            correlation_id=correlation_id)
        conn.execute(
            "UPDATE plt01.mem_memberships SET status = 'active', status_effective_on = %s,"
            " status_change_id = %s, version = version + 1"
            " WHERE membership_id = %s AND status = 'pending'",
            (starts_on, change_id, membership_id))
        conn.execute(
            "UPDATE plt01.mem_agreements SET status = 'active'"
            " WHERE agreement_id = %s AND status = 'signed'",
            (agreement_id,))
        _append(conn, tenant_id, "membership.activated", "membership", membership_id,
                {"membership_id": membership_id, "agreement_id": agreement_id,
                 "person_id": str(agreement[0])},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"membership_id": membership_id, "status": "active",
            "membership_number": membership_number.upper(),
            "current_period_start": period_start.isoformat(),
            "current_period_end": period_end.isoformat(), "repeated": False}


def freeze_allowance(
    pool: Pool, tenant_id: str, membership_id: str, *, at: date | None = None,
) -> dict[str, Any]:
    """What is left of a membership's freeze allowance, before anybody freezes anything.

    **`allowance_days_used_before` was returned by the *write* and by nothing else**, so the
    only way to learn how much of the contract's allowance a member had spent was to spend
    some more of it and read the answer. The seventh instance of this build's "a writer with
    no reader" shape, and ADM-MSH-03 cannot be drawn without it: the canvas states "2 of 3
    freeze months used this year" **in the consequence panel, before the button**, which is
    the same decision ADM-PAY-09 makes about a till -- the figure that bounds the act is
    shown before the act, because the common problem is a mistake rather than a fraud.

    **Every number here comes from the function the write uses**, not from a second
    expression that agrees with it today: `_contract_year`, `lifecycle.freeze_days_used` and
    `lifecycle.check_freeze`. MOD-018's `_expected_in_drawer` had a sibling thirty lines away
    that differed by a date bound, and one journal dated next year made a short till balance.
    A screen that said "2 of 3 used" while the write counted differently would be worse than
    one that said nothing.
    """
    today = at or _today()
    with tenant_scope(pool, tenant_id) as conn:
        membership = _membership(conn, membership_id)
        terms = _terms_of(conn, current_agreement(conn, membership))
        year_start, year_end = _contract_year(membership["starts_on"], today)
        windows = [
            lifecycle.FreezeWindow(
                starts_on=r[0], ends_on=r[1], counts_against_allowance=bool(r[2]))
            for r in conn.execute(
                "SELECT starts_on, ends_on, counts_against_allowance FROM plt01.mem_freezes"
                " WHERE membership_id = %s", (membership_id,)).fetchall()
        ]
        used = lifecycle.freeze_days_used(windows, year_start, year_end)
    allowed = int(terms.freeze_days_per_year)
    remaining = max(0, allowed - used)
    # **An open freeze is counted to the end of the contract year**, which is
    # `freeze_days_used`'s own conservative direction: it is spending the allowance right
    # now, and treating it as free until it closes would let somebody hold a membership
    # frozen indefinitely inside a thirty-day allowance. That is right and it makes the
    # figure surprising -- a seven-day freeze taken today reads as 275 of 30 used -- so the
    # read says which case it is rather than leaving a panel to print a number nobody can
    # reconcile against the days they asked for.
    counting_open = any(
        w.counts_against_allowance and w.ends_on is None for w in windows)
    return {
        "membership_id": membership_id,
        "status": membership["status"],
        "counting_an_open_freeze": counting_open,
        "contract_year": {"from": year_start.isoformat(), "to": year_end.isoformat()},
        "allowance_days": allowed,
        "days_used": used,
        "days_remaining": remaining,
        # **The window a freeze may start in, because the module refuses anything else.**
        # `freeze_membership` takes a start within the month before today -- a month back
        # because one agreed at the desk on Friday is recorded on Monday -- and refuses a
        # future date outright, since nothing in this build applies a booked freeze when its
        # day arrives and a booked freeze that never takes effect is worse than one that
        # cannot be booked. A form that offered a future date would be offering a refusal.
        "may_start_between": {
            "from": (today - _days(31)).isoformat(), "to": today.isoformat()},
        "allows_freezing": allowed > 0,
        "an_open_freeze_counts_to_the_year_end": (
            "a freeze that has not been resumed is counted to the end of the contract year, "
            "because it is spending the allowance now -- so while one is open the figure is "
            "what it would cost if nobody resumed it, not the days anybody asked for"),
        "the_figure_is_the_writes_own": (
            "days_used is `lifecycle.freeze_days_used` over this membership's own freezes "
            "inside the contract year containing today, which is the expression "
            "`freeze_membership` checks against -- not a second one that agrees with it "
            "today"),
    }


def freeze_membership(
    pool: Pool, tenant_id: str, membership_id: str, *, freeze_kind: str, starts_on: date,
    days: int, reason: str, idempotency_key: str, actor_id: str, correlation_id: str,
    evidence_ref: str | None = None, requested_by_person_id: str | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """FreezeMembership. COM-01-R04, with the contract's allowance enforced.

    **The allowance is checked against the freezes that exist, under the membership's lock.**
    Counting and then inserting without the lock is the race MOD-016 shipped for coupons; here
    it would let a member exceed a thirty-day allowance by sending two requests at once.

    The contract year is taken from the membership's own start date rather than the calendar,
    because "thirty days a year" in a contract signed in March means March to March.

    **And the start date is bounded to the month before today.** It was unbounded, and the
    allowance is counted in the contract year containing it, so a member who had spent all
    thirty days sent `starts_on` one day before their anniversary and got a second allowance --
    the whole of COM-01-R04's limit bought with a date field.

    A month *back* because a freeze agreed at the desk on Friday is recorded on Monday. Nothing
    *forward*, and that is a deliberate narrowing rather than an oversight: a freeze booked for
    next month would have to be applied when the date arrived, there is no worker runtime in
    this build to apply it, and a booked freeze that never takes effect is worse than one that
    cannot be booked. The first version admitted ninety days ahead and wrote
    `status = 'frozen'` immediately, so a freeze booked for August made the membership read as
    frozen in May -- a turnstile asking "is this member frozen" got yes for three months while
    `status_as_of` correctly said no. Refusing what this build cannot honour is the honest half
    of that fix; the cache-moves-when-effective half is below, where it is now trivially true.
    """
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    # **The kind decides which command this is**, and the idempotency lookup needs it before
    # it can tell a retried medical hold from a retried freeze. The first version passed the
    # literal `"freeze"`, so a retried medical hold was refused as another command's key.
    change_kind = "medical_hold" if freeze_kind == "medical_hold" else "freeze"
    today = _today()
    with tenant_scope(pool, tenant_id) as conn:
        membership = _membership(conn, membership_id)
        prior = _recorded_change(
            conn, membership_id, idempotency_key.strip(), change_kind)
        if prior is not None:
            live = conn.execute(
                "SELECT freeze_id, planned_ends_on, counts_against_allowance"
                " FROM plt01.mem_freezes"
                " WHERE membership_id = %s AND ends_on IS NULL",
                (membership_id,),
            ).fetchone()
            # **The repeated answer is read back, not reconstructed.** The first version
            # returned the change's effective date as `planned_ends_on` and a hard-coded zero
            # for the allowance already used -- two figures a client would believe, neither of
            # them this freeze's. A retry has to get the original answer, and the original
            # answer is on the row.
            return {"membership_id": membership_id,
                    "freeze_id": str(live[0]) if live else None,
                    "status": membership["status"],
                    "effective_on": prior["effective_on"].isoformat(),
                    "planned_ends_on": (
                        live[1].isoformat() if live and live[1] else None),
                    "counts_against_allowance": (
                        bool(live[2]) if live
                        else lifecycle.counts_against_allowance(freeze_kind)),
                    "repeated": True}
        if expected_version is not None and membership["version"] != expected_version:
            raise Conflict("this_membership_changed_since_it_was_read")
        terms = _terms_of(conn, current_agreement(conn, membership))
        try:
            lifecycle.check_transition(change_kind, membership["status"], "frozen")
        except lifecycle.LifecycleError as e:
            raise Conflict(str(e)) from None
        counts = lifecycle.counts_against_allowance(freeze_kind)
        if not (today - _days(31) <= starts_on <= today):
            raise InvalidRequest("a_freeze_starts_within_the_month_before_today")
        year_start, year_end = _contract_year(membership["starts_on"], starts_on)
        decision_year = _contract_year(membership["starts_on"], today)
        if (year_start, year_end) != decision_year:
            raise InvalidRequest("a_freeze_starts_in_the_contract_year_it_is_decided_in")
        windows = [
            lifecycle.FreezeWindow(
                starts_on=r[0], ends_on=r[1], counts_against_allowance=bool(r[2]))
            for r in conn.execute(
                "SELECT starts_on, ends_on, counts_against_allowance FROM plt01.mem_freezes"
                " WHERE membership_id = %s", (membership_id,)).fetchall()
        ]
        used = lifecycle.freeze_days_used(windows, year_start, year_end)
        if counts:
            try:
                lifecycle.check_freeze(
                    requested_days=days, terms=terms, already_used=used)
            except lifecycle.LifecycleError as e:
                raise Conflict(str(e)) from None
        elif days <= 0 or days > 365:
            raise InvalidRequest("a_hold_lasts_between_one_day_and_a_year")
        # **The plan and the outcome are two columns.** `ends_on` stays NULL while the freeze
        # is live -- that is what the one-live-freeze index reads and what `resume` closes --
        # and `planned_ends_on` is what the member asked for. The first version computed this
        # date, returned it to the caller and stored it nowhere, so a freeze that nobody
        # resumed ran for ever and the allowance arithmetic counted it as open-ended.
        planned_ends_on = starts_on + _days(days - 1)
        try:
            frozen = conn.execute(
                """
                INSERT INTO plt01.mem_freezes
                    (tenant_id, membership_id, freeze_kind, starts_on, ends_on,
                     planned_ends_on, counts_against_allowance, extends_term, evidence_ref,
                     reason, requested_by_person_id, decided_by, correlation_id)
                VALUES (%s, %s, %s, %s, NULL, %s, %s, true, %s, %s, %s, %s, %s)
                RETURNING freeze_id
                """,
                (tenant_id, membership_id, freeze_kind, starts_on, planned_ends_on, counts,
                 evidence_ref, reason, requested_by_person_id, actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_membership_is_already_frozen") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert frozen is not None
        change_id, repeated = _record_change(
            conn, tenant_id, membership_id=membership_id, change_kind=change_kind,
            from_status=membership["status"], to_status="frozen", effective_on=starts_on,
            reason=reason, idempotency_key=idempotency_key.strip(), actor_id=actor_id,
            correlation_id=correlation_id,
            requested_by_person_id=requested_by_person_id)
        # **The cache moves because the change is effective**, which the bound above makes
        # true of every freeze this command will write. The schema calls `mem_memberships` "a
        # cache of the latest effective change", and a future-dated freeze would break that
        # claim -- so the start date is bounded rather than the cache being left behind for
        # something to catch up on later. `cancel_membership` is the one command that really
        # does record a future-dated change, and it leaves the status alone.
        assert starts_on <= today
        conn.execute(
            "UPDATE plt01.mem_memberships SET status = 'frozen',"
            " status_effective_on = %s, status_change_id = %s, version = version + 1"
            " WHERE membership_id = %s",
            (starts_on, change_id, membership_id))
        _append(conn, tenant_id, "membership.frozen", "membership", membership_id,
                {"membership_id": membership_id, "freeze_id": str(frozen[0]),
                 "freeze_kind": freeze_kind, "effective_on": starts_on.isoformat()},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"membership_id": membership_id, "freeze_id": str(frozen[0]),
            "status": "frozen", "effective_on": starts_on.isoformat(),
            "planned_ends_on": planned_ends_on.isoformat(),
            "allowance_days_used_before": used, "counts_against_allowance": counts,
            "repeated": repeated}


def _days(n: int) -> timedelta:
    """`timedelta(days=n)`, named so the date arithmetic below reads as dates."""
    return timedelta(days=n)


def _contract_year(membership_start: date, moment: date) -> tuple[date, date]:
    """The contract year containing `moment`, counted from the membership's own start.

    "Thirty freeze days a year" in a contract signed in March means March to March, not
    January to January -- a calendar year would hand a member signing in November a second
    allowance eight weeks later.
    """
    years = moment.year - membership_start.year
    try:
        anniversary = membership_start.replace(year=membership_start.year + years)
    except ValueError:
        # 29 February in a non-leap year.
        anniversary = membership_start.replace(year=membership_start.year + years, day=28)
    if anniversary > moment:
        years -= 1
        try:
            anniversary = membership_start.replace(year=membership_start.year + years)
        except ValueError:
            anniversary = membership_start.replace(
                year=membership_start.year + years, day=28)
    try:
        end = membership_start.replace(year=membership_start.year + years + 1)
    except ValueError:
        end = membership_start.replace(year=membership_start.year + years + 1, day=28)
    return anniversary, end - _days(1)


def resume_membership(
    pool: Pool, tenant_id: str, membership_id: str, *, reason: str, idempotency_key: str,
    actor_id: str, correlation_id: str, at: date | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """ResumeMembership, closing the live freeze and extending the term where it says to.

    COM-01-R05's expiry extension: a freeze that `extends_term` pushes the agreement's end out
    by the days actually frozen -- which is the days it ran, not the days that were asked for,
    because a member who resumed early did not spend the rest.
    """
    today = at or _today()
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    with tenant_scope(pool, tenant_id) as conn:
        membership = _membership(conn, membership_id)
        prior = _recorded_change(
            conn, membership_id, idempotency_key.strip(), "resume")
        if prior is not None:
            # The freeze this resume closed, found by the date it was closed on. One freeze is
            # live at a time and a resume closes it, so on any given day there is at most one
            # -- unless a second freeze was taken and resumed the same day, where the latest
            # is returned and the earlier one is not reachable from here.
            closed = conn.execute(
                "SELECT freeze_id, starts_on, ends_on FROM plt01.mem_freezes"
                " WHERE membership_id = %s AND ends_on = %s"
                " ORDER BY resumed_at DESC LIMIT 1",
                (membership_id, prior["effective_on"]),
            ).fetchone()
            return {"membership_id": membership_id, "status": membership["status"],
                    "effective_on": prior["effective_on"].isoformat(),
                    "freeze_id": str(closed[0]) if closed else None,
                    "frozen_days": (
                        (closed[2] - closed[1]).days if closed else None),
                    "repeated": True}
        if expected_version is not None and membership["version"] != expected_version:
            raise Conflict("this_membership_changed_since_it_was_read")
        try:
            lifecycle.check_transition("resume", membership["status"], "active")
        except lifecycle.LifecycleError as e:
            raise Conflict(str(e)) from None
        live = conn.execute(
            "SELECT freeze_id, starts_on, extends_term FROM plt01.mem_freezes"
            " WHERE membership_id = %s AND ends_on IS NULL FOR UPDATE",
            (membership_id,),
        ).fetchone()
        frozen_days = 0
        freeze_id: str | None = None
        if live is not None:
            freeze_id = str(live[0])
            # **A freeze cannot end before it began**, and `ends_on` was written as today
            # whatever the start said. Unreachable through `freeze_membership` now that a
            # freeze cannot start in the future, and kept because a row written by anything
            # else still has a start date and this is a `CHECK` away from a 500.
            closed_on = max(today, live[1])
            frozen_days = (closed_on - live[1]).days
            conn.execute(
                "UPDATE plt01.mem_freezes SET ends_on = %s, resumed_at = now(),"
                " resumed_by = %s, resume_correlation_id = %s"
                " WHERE freeze_id = %s AND ends_on IS NULL",
                (closed_on, actor_id, correlation_id, freeze_id))
            # **An open-ended agreement has no end to extend.** The first version wrote
            # `coalesce(ends_on, today) + frozen_days`, which invented an expiry for a rolling
            # membership out of the date somebody happened to resume on -- a monthly membership
            # with no end date acquired one two weeks out and then lapsed. COM-01-R05's
            # extension applies to a term; a membership with no term is not extended.
            if bool(live[2]) and frozen_days > 0:
                conn.execute(
                    "UPDATE plt01.mem_agreements SET ends_on = ends_on + %s"
                    " WHERE agreement_id = %s AND ends_on IS NOT NULL",
                    (frozen_days, current_agreement(conn, membership)))
        change_id, repeated = _record_change(
            conn, tenant_id, membership_id=membership_id, change_kind="resume",
            from_status=membership["status"], to_status="active", effective_on=today,
            reason=reason, idempotency_key=idempotency_key.strip(), actor_id=actor_id,
            correlation_id=correlation_id)
        conn.execute(
            "UPDATE plt01.mem_memberships SET status = 'active', status_effective_on = %s,"
            " status_change_id = %s, version = version + 1 WHERE membership_id = %s",
            (today, change_id, membership_id))
        _append(conn, tenant_id, "membership.resumed", "membership", membership_id,
                {"membership_id": membership_id, "effective_on": today.isoformat(),
                 "frozen_days": frozen_days},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"membership_id": membership_id, "status": "active",
            "effective_on": today.isoformat(), "freeze_id": freeze_id,
            "frozen_days": frozen_days, "repeated": repeated}


def preview_cancellation(
    pool: Pool, tenant_id: str, membership_id: str, *, at: date | None = None,
) -> dict[str, Any]:
    """COM-01-R06's fee disclosure, as a read with no side effect.

    **"Members understand consequences before confirming changes"** is a required outcome
    (paragraph 1500), and a disclosure the member cannot see before deciding is not one. So the
    effective date and the fee are computed here, returned with their reasoning, and recorded
    on the change when the member confirms -- which is how the figure they were shown and the
    figure that was applied are provably the same one.

    **The fee is `lifecycle.cancellation_fee`, which is what makes that last sentence true.**
    It used to be an inline proration here and another one in `cancel_membership`: two
    expressions, identical, agreeing for as long as nobody edited one of them. Adding the
    contract buy-out ADM-MSH-07 discloses pulled them apart in the worst direction -- this
    read would have quoted a figure the command then refused as a mismatch, which is the
    disclosure requirement defeated by the function that exists to serve it. MOD-018's "one
    module, two definitions of the same balance", in a module whose own header says a control
    and the state it bounds commit together.

    **And this is the reader ADM-MSH-07's backlog entry said did not exist.** It said the fee
    was learnable only by cancelling, which was wrong -- this route has been here since the
    module was built. The gap was never the read; it was that the read quoted a different
    product from the one the design approved, and nothing compared the two because no screen
    rendered either. A claimed gap is a claim to check before building on it.
    """
    today = at or _today()
    with tenant_scope(pool, tenant_id) as conn:
        membership = conn.execute(
            "SELECT m.agreement_id, m.status, m.current_period_start,"
            " m.current_period_end, m.version"
            " FROM plt01.mem_memberships m WHERE m.membership_id = %s",
            (membership_id,),
        ).fetchone()
        if membership is None:
            raise NotFound("membership_not_found")
        # **The agreement is resolved, never joined on `m.agreement_id`.** That column is the
        # chain's root, so the obvious one-query join answers from the contract the member has
        # moved off -- every figure below it (the term end, the amount the buy-out is a
        # multiple of, the currency, and the terms themselves) would be the superseded one's.
        # This is the whole of `current_agreement`'s reason for existing, and this read is
        # where it costs the most: the fee is the figure a member disputes.
        agreement_id = current_agreement(conn, {"agreement_id": membership[0]})
        agreement = conn.execute(
            "SELECT minimum_term_ends_on, amount_minor, currency"
            " FROM plt01.mem_agreements WHERE agreement_id = %s",
            (agreement_id,),
        ).fetchone()
        assert agreement is not None
        terms = _terms_of(conn, agreement_id)
    status = str(membership[1])
    period_start, period_end, version = membership[2], membership[3], int(membership[4])
    minimum_term_ends_on: date | None = agreement[0]
    amount_minor, currency = int(agreement[1]), str(agreement[2])
    # **Whether it can be cancelled at all, asked the way the command asks it.** A panel
    # pricing a cancellation the command would refuse as a bad transition is a figure offered
    # for an act that cannot happen -- and the screen needs to say which of the two it is.
    may_cancel, refused_because = True, None
    try:
        lifecycle.check_transition("cancellation", status, "cancelled")
    except lifecycle.LifecycleError as e:
        may_cancel, refused_because = False, str(e)
    effective_on, steps = lifecycle.cancellation_effective_on(
        decided_on=today, terms=terms, period_end=period_end,
        minimum_term_ends_on=minimum_term_ends_on)
    fee_minor, fee_parts, fee_steps = lifecycle.cancellation_fee(
        effective_on=effective_on, terms=terms, amount_minor=amount_minor,
        period_start=period_start, period_end=period_end,
        minimum_term_ends_on=minimum_term_ends_on)
    return {
        "membership_id": membership_id, "status": status,
        # The form's optimistic-concurrency token, because the command takes
        # `expected_version` and a screen that cannot supply it is a screen whose write
        # cannot be guarded -- two staff cancelling one membership is MOD-014's ordinary case.
        "version": version,
        "may_cancel": may_cancel,
        "refused_because": refused_because,
        "effective_on": effective_on.isoformat(),
        "ends_immediately": effective_on <= today,
        "disclosed_fee_minor": fee_minor,
        "disclosed_fee_currency": currency,
        # **The parts, not only the total.** They answer different questions and a member
        # disputing one should not have to take the other on trust -- which is MOD-018's
        # argument for four wallet balances rather than one, and is what makes the headline
        # figure checkable rather than merely stated.
        "fee_parts": fee_parts,
        "amount_minor": amount_minor,
        "explanation": list(steps) + list(fee_steps),
        "cancellation_mode": terms.cancellation_mode,
        "notice_days": terms.notice_days,
        "commitment": {
            "minimum_term_months": terms.minimum_term_months,
            "ends_on": (
                minimum_term_ends_on.isoformat() if minimum_term_ends_on else None),
            # **Whether access ends before the term does, which is the fee's own condition
            # and is NOT "is there still a commitment".** Those are the same sentence only
            # while a contract allows an early exit: where it does not, the clause above
            # pushes `effective_on` *to* the term end, so this goes false exactly when the
            # member is most firmly held. A surface reading it as "the term is over" told
            # such a member their commitment had been served nine months early, and the
            # freeze offer that keeps a commitment intact was withheld from the only member
            # it mattered to. Kept, because the buy-out is charged on precisely this, and
            # pinned by a test rather than by this comment.
            "leaving_early": (
                minimum_term_ends_on is not None and effective_on < minimum_term_ends_on),
            # **Is the commitment running today**, which is the question a screen asks and
            # the one it cannot work out for itself: `today` is not on this response, and a
            # client comparing `ends_on` against its own clock would be counting days in a
            # frame this build has three recorded defects from. MOD-016's `in_window` and
            # MOD-018's `admits_trade` for the same reason -- the implication is the fact.
            "term_is_running": (
                minimum_term_ends_on is not None and today < minimum_term_ends_on),
            # Three states, as the column has them: no early exit, a free one, or a priced
            # one. A screen reading a null as a zero would tell a member they may walk away
            # free from a contract that holds them to March.
            "early_termination_months": terms.early_termination_months,
            "may_leave_early": terms.early_termination_months is not None,
        },
        # **The alternative the canvas puts above the button.** "A freeze costs him nothing
        # and keeps the commitment intact" is only true where the contract allows one; how
        # much of the allowance is left is `freeze_allowance`'s answer rather than a second
        # count here.
        "freeze_is_an_alternative": terms.freeze_days_per_year > 0,
        "the_fee_is_what_it_costs_not_what_is_owed": (
            "period_minor is what the current billing period costs for the part of it the "
            "member will have used when access ends -- whether that period has already been "
            "paid is a question for the invoice and the payments against it, which this "
            "read does not join to. early_termination_minor is the contract's buy-out and "
            "is always a new charge"),
        "the_figures_are_the_writes_own": (
            "effective_on and disclosed_fee_minor are `cancellation_effective_on` and "
            "`cancellation_fee` over this membership's own terms, which are the expressions "
            "`cancel_membership` compares an acknowledged figure against -- not a second "
            "pair that agrees with them today"),
    }


def cancel_membership(
    pool: Pool, tenant_id: str, membership_id: str, *, reason: str, idempotency_key: str,
    actor_id: str, correlation_id: str, acknowledged_fee_minor: int | None = None,
    requested_by_person_id: str | None = None, at: date | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """CancelMembership. COM-01-R02's notice and COM-01-R06's disclosure.

    **The fee the member acknowledged is compared against the fee that is actually due**, and a
    mismatch refuses. Without that, the preview and the command are two independent
    calculations and the member can be shown one figure and charged another -- which is the
    defect a disclosure requirement exists to prevent, and it is the same shape as MOD-016's
    approval that had to match the list price it was measured against.

    A caller that passes nothing is not disclosing anything, and the change records no fee.
    That is allowed for a staff-initiated cancellation and is why the column is nullable: a
    disclosed fee of zero and no disclosure at all are different facts.
    """
    today = at or _today()
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    with tenant_scope(pool, tenant_id) as conn:
        membership = _membership(conn, membership_id)
        prior = _recorded_change(
            conn, membership_id, idempotency_key.strip(), "cancellation")
        if prior is not None:
            # **The recorded fee, not the one this retry happens to carry.** The first version
            # echoed `acknowledged_fee_minor` straight back and reported `fee_due_minor` as
            # None, so a second call sending a different figure was told it had been accepted
            # -- the disclosure check bypassed by retrying with the number you wanted. The
            # comparison the first call made is re-made against what was written down.
            if (acknowledged_fee_minor is not None
                    and acknowledged_fee_minor != prior["disclosed_fee_minor"]):
                raise Conflict(
                    f"this cancellation was confirmed at a disclosed fee of "
                    f"{prior['disclosed_fee_minor']} and this request says "
                    f"{acknowledged_fee_minor}")
            return {"membership_id": membership_id, "change_id": prior["change_id"],
                    "effective_on": prior["effective_on"].isoformat(),
                    "takes_effect_immediately": prior["effective_on"] <= today,
                    "disclosed_fee_minor": prior["disclosed_fee_minor"],
                    "fee_due_minor": prior["disclosed_fee_minor"],
                    # The recorded row carries the total and not its parts, so a repeat
                    # reports no breakdown rather than re-deriving one against terms that
                    # may have been superseded since. Answering from what was written down
                    # is this function's own rule one field over.
                    "fee_parts": None, "reasoning": [],
                    "entitlements_revoked": [], "repeated": True}
        if expected_version is not None and membership["version"] != expected_version:
            raise Conflict("this_membership_changed_since_it_was_read")
        try:
            lifecycle.check_transition(
                "cancellation", membership["status"], "cancelled")
        except lifecycle.LifecycleError as e:
            raise Conflict(str(e)) from None
        agreement_id = current_agreement(conn, membership)
        agreement = conn.execute(
            "SELECT minimum_term_ends_on, amount_minor, currency FROM plt01.mem_agreements"
            " WHERE agreement_id = %s",
            (agreement_id,),
        ).fetchone()
        assert agreement is not None
        terms = _terms_of(conn, agreement_id)
        effective_on, reasoning = lifecycle.cancellation_effective_on(
            decided_on=today, terms=terms, period_end=membership["current_period_end"],
            minimum_term_ends_on=agreement[0])
        # **One function decides the fee, and the quote reads the same one.** The first
        # version computed the period part inline here and `cancellation_quote` did not
        # exist, so the only reader of this arithmetic was a test asserting the arithmetic --
        # which is how it went unnoticed that the design charges a buy-out this build refused
        # to have. A second expression in the quote that agreed with this one today is
        # MOD-018's "one module, two definitions of the same balance", and the figure here is
        # the one a member acknowledges.
        fee_minor, fee_parts, fee_steps = lifecycle.cancellation_fee(
            effective_on=effective_on, terms=terms, amount_minor=int(agreement[1]),
            period_start=membership["current_period_start"],
            period_end=membership["current_period_end"],
            minimum_term_ends_on=agreement[0])
        if acknowledged_fee_minor is not None and acknowledged_fee_minor != fee_minor:
            raise Conflict(
                f"the fee disclosed was {acknowledged_fee_minor} and the fee due is "
                f"{fee_minor}; re-read the preview before confirming")
        change_id, repeated = _record_change(
            conn, tenant_id, membership_id=membership_id, change_kind="cancellation",
            from_status=membership["status"], to_status="cancelled",
            effective_on=effective_on, reason=reason,
            idempotency_key=idempotency_key.strip(), actor_id=actor_id,
            correlation_id=correlation_id,
            requested_by_person_id=requested_by_person_id,
            disclosed_fee_minor=acknowledged_fee_minor,
            disclosed_fee_currency=(
                str(agreement[2]) if acknowledged_fee_minor is not None else None))
        # **The status moves only once the cancellation is effective.** A cancellation under
        # notice leaves the membership active until the notice runs out, which is what a notice
        # period *is* -- and the history carries the decision from today, so the member cannot
        # be told later that nobody cancelled.
        revoked: list[dict[str, Any]] = []
        if effective_on <= today:
            conn.execute(
                "UPDATE plt01.mem_memberships SET status = 'cancelled',"
                " status_effective_on = %s, status_change_id = %s, ends_on = %s,"
                " version = version + 1 WHERE membership_id = %s",
                (effective_on, change_id, effective_on, membership_id))
            # The entitlements this membership gave stop being drawable in the same
            # transaction. A future-dated cancellation revokes nothing yet, because the
            # member is still paying for the notice period and still entitled to train;
            # `memberships.revoke_ended_grants` is the worker job that revokes them when the
            # date arrives, which this comment said did not exist until the runtime landed.
            revoked = _revoke_grants(
                conn, tenant_id, membership_id=membership_id,
                reason=f"the membership was cancelled: {reason}", actor_id=actor_id,
                correlation_id=correlation_id, moment=_now())
        else:
            conn.execute(
                "UPDATE plt01.mem_memberships SET ends_on = %s, version = version + 1"
                " WHERE membership_id = %s",
                (effective_on, membership_id))
        _append(conn, tenant_id, "membership.cancelled", "membership", membership_id,
                {"membership_id": membership_id, "effective_on": effective_on.isoformat(),
                 "change_id": change_id},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"membership_id": membership_id, "change_id": change_id,
            "effective_on": effective_on.isoformat(),
            "takes_effect_immediately": effective_on <= today,
            "disclosed_fee_minor": acknowledged_fee_minor,
            "fee_due_minor": fee_minor, "fee_parts": fee_parts,
            # **The reasoning was computed and discarded by the only caller.**
            # `cancellation_effective_on` returns its steps because "COM-01-R06 requires the
            # member to understand the consequence before confirming -- a date with no
            # explanation is the thing they dispute", and this function unpacked it into `_`.
            # A value computed for a reason nobody reads is this build's recurring shape, and
            # here the reason was written down beside the value that implements it.
            "reasoning": list(reasoning) + list(fee_steps),
            "entitlements_revoked": revoked, "repeated": repeated}


#: The change kinds whose reason is health data, so the prose is masked rather than returned.
#:
#: **A medical hold's reason is a condition, whatever column it is written in.** The freeze's
#: `evidence_ref` is constrained to a locator precisely so a diagnosis cannot be stored there --
#: and `reason` beside it is unconstrained prose that the ordinary operator will use to say why.
#: `membership.record.read` is routine and AAL 1, which a front desk and a turnstile hold, so
#: returning it put a staged diagnosis in front of every holder of the cheapest read in the
#: module. MOD-008 classifies health as `biometric_sensitive`, MOD-014 records that such a
#: class is unreadable by anybody in this build because AAL 3 needs a hardware factor MOD-007
#: cannot verify, and this read reaches the same answer the same way: the text is held, its
#: presence is stated, and nobody here can read it.
HEALTH_REASON_KINDS: frozenset[str] = frozenset({"medical_hold"})

#: What a masked reason reads as. MOD-014's rule: a redacted record still exists, because
#: telling a coach there is no medical hold when there is one is worse than telling them there
#: is one they cannot read.
MASKED_REASON = "[redacted: health data, unreadable at any assurance level in this build]"


def _reason_or_mask(change_kind: str, reason: str) -> str:
    return MASKED_REASON if change_kind in HEALTH_REASON_KINDS else reason


def membership_as_of(
    pool: Pool, tenant_id: str, membership_id: str, *, moment: date,
) -> dict[str, Any]:
    """COM-01-R07's as-of reconstruction, for one membership on one date.

    **Replayed from the history, not read from the cache.** The status column on
    `mem_memberships` answers "now"; this answers "then", and the two are different questions
    that a dispute turns on. A cancellation decided in January effective in March leaves the
    membership active in February, and this is the function that says so.

    **A medical hold's reason is masked** -- see `HEALTH_REASON_KINDS`. The entry stays in the
    history with its dates and its kind, because a hold a reader cannot see at all is a gap in
    a dispute record; what they cannot see is the sentence describing why.
    """
    with tenant_scope(pool, tenant_id) as conn:
        exists = conn.execute(
            "SELECT membership_number, starts_on, status FROM plt01.mem_memberships"
            " WHERE membership_id = %s",
            (membership_id,),
        ).fetchone()
        if exists is None:
            raise NotFound("membership_not_found")
        rows = conn.execute(
            "SELECT change_kind, from_status, to_status, effective_on, decided_at, reason"
            " FROM plt01.mem_lifecycle_changes WHERE membership_id = %s"
            " ORDER BY effective_on, change_kind",
            (membership_id,),
        ).fetchall()
    changes = [
        lifecycle.Change(str(r[0]), str(r[1]), str(r[2]), r[3]) for r in rows]
    return {
        "membership_id": membership_id,
        "membership_number": str(exists[0]),
        "as_of": moment.isoformat(),
        "status_as_of": lifecycle.status_as_of("pending", changes, moment),
        "status_now": str(exists[2]),
        "history": [
            {"change_kind": str(r[0]), "from_status": str(r[1]), "to_status": str(r[2]),
             "effective_on": r[3].isoformat(), "decided_at": r[4].isoformat(),
             "reason": _reason_or_mask(str(r[0]), str(r[5])),
             "reason_withheld": str(r[0]) in HEALTH_REASON_KINDS}
            for r in rows],
    }


# ------------------------------------------------------------------ entitlements

def define_entitlement_policy(
    pool: Pool, tenant_id: str, *, policy_key: str, display_name: str,
    entitlement_type: str, actor_id: str, correlation_id: str, is_counted: bool = True,
    reservation_ttl_seconds: int = 900, carryover_mode: str = "none",
    carryover_limit: int | None = None,
) -> dict[str, Any]:
    """Declare what one kind of entitlement means in this tenant. COM-01-R03."""
    if entitlement_type not in entitlements.ENTITLEMENT_TYPES:
        raise InvalidRequest(f"unknown_entitlement_type_{entitlement_type}")
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.mem_entitlement_policies
                    (tenant_id, policy_key, display_name, entitlement_type, is_counted,
                     reservation_ttl_seconds, carryover_mode, carryover_limit, created_by,
                     correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING policy_id
                """,
                (tenant_id, policy_key, display_name, entitlement_type, is_counted,
                 reservation_ttl_seconds, carryover_mode, carryover_limit, actor_id,
                 correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_entitlement_policy_key_already_exists") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
    return {"policy_id": str(row[0]), "policy_key": policy_key,
            "entitlement_type": entitlement_type, "is_counted": is_counted}


def grant_entitlement(
    pool: Pool, tenant_id: str, *, person_id: str, policy_id: str, source_kind: str,
    valid_from: datetime, reason: str, actor_id: str, correlation_id: str,
    quantity: int | None = None, valid_to: datetime | None = None,
    membership_id: str | None = None, source_id: str | None = None,
    brand_id: str | None = None, location_id: str | None = None,
    usable_from_minute: int | None = None, usable_to_minute: int | None = None,
) -> dict[str, Any]:
    """GrantEntitlement, and the opening movement in the same transaction.

    **A counted grant's opening balance is a ledger row, not the `granted_quantity` column.**
    The column records what was sold; the ledger records what is left, and there is exactly one
    authority on the second. Writing the grant without its opening movement would make the
    balance zero on a grant that says ten, which is the shape a stored-balance design produces
    on every edge case rather than just this one.

    `is_counted` comes from the policy, not from the caller: a caller able to send it could
    make an unlimited grant of something the tenant sells by the ten.
    """
    with tenant_scope(pool, tenant_id) as conn:
        policy = conn.execute(
            "SELECT is_counted, status, entitlement_type FROM plt01.mem_entitlement_policies"
            " WHERE policy_id = %s",
            (policy_id,),
        ).fetchone()
        if policy is None:
            raise NotFound("entitlement_policy_not_found")
        if str(policy[1]) != "active":
            raise Conflict("this_entitlement_policy_is_retired")
        is_counted = bool(policy[0])
        if is_counted and quantity is None:
            raise InvalidRequest("a_counted_entitlement_is_granted_in_a_quantity")
        if not is_counted and quantity is not None:
            raise InvalidRequest("an_unlimited_entitlement_takes_no_quantity")
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.mem_entitlement_grants
                    (tenant_id, person_id, policy_id, source_kind, source_id,
                     membership_id, is_counted, granted_quantity, valid_from, valid_to,
                     brand_id, location_id, usable_from_minute, usable_to_minute,
                     created_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING grant_id
                """,
                (tenant_id, person_id, policy_id, source_kind, source_id, membership_id,
                 is_counted, quantity, valid_from, valid_to, brand_id, location_id,
                 usable_from_minute, usable_to_minute, actor_id, correlation_id),
            ).fetchone()
        except errors.ForeignKeyViolation as e:
            raise NotFound(_fk_subject(e)) from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        grant_id = str(row[0])
        if is_counted:
            assert quantity is not None
            _movement(conn, tenant_id, grant_id=grant_id, movement_kind="grant",
                      delta=quantity, reason=reason, actor_id=actor_id,
                      correlation_id=correlation_id)
        _append(conn, tenant_id, "entitlement.granted", "entitlement", grant_id,
                {"grant_id": grant_id, "person_id": person_id, "policy_id": policy_id,
                 "entitlement_type": str(policy[2]), "is_counted": is_counted},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"grant_id": grant_id, "person_id": person_id, "is_counted": is_counted,
            "granted_quantity": quantity}


def _movement(
    conn: Connection[Any], tenant_id: str, *, grant_id: str, movement_kind: str,
    delta: int, reason: str, actor_id: str, correlation_id: str,
    reservation_id: str | None = None,
) -> str:
    """One ledger row, with its sign checked by the decision layer before the database sees it.

    Checked in both places on purpose: the decision function gives a readable refusal and the
    constraint makes it true of rows written by anything else, including a later service that
    forgets to call this.
    """
    entitlements.check_sign(movement_kind, delta)
    row = conn.execute(
        """
        INSERT INTO plt01.mem_entitlement_ledger
            (tenant_id, grant_id, reservation_id, movement_kind, delta, actor_id, reason,
             correlation_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING movement_id
        """,
        (tenant_id, grant_id, reservation_id, movement_kind, delta, actor_id, reason,
         correlation_id),
    ).fetchone()
    assert row is not None
    return str(row[0])


def _grant_locked(conn: Connection[Any], grant_id: str) -> tuple[entitlements.Grant, int]:
    """A grant and its balance, with the grant row locked. Returns `(grant, balance)`.

    **The lock is what makes the balance safe to act on.** Between the sum and the insert,
    nothing else may draw on this grant -- which is the race MOD-016 shipped for coupons and a
    reviewer demonstrated with six concurrent redemptions. It serialises draws on one grant and
    leaves every other grant in the tenant untouched, which is the narrowest lock that works.
    """
    row = conn.execute(
        "SELECT grant_id, is_counted, granted_quantity, valid_from, valid_to, status,"
        " brand_id, location_id, usable_from_minute, usable_to_minute"
        " FROM plt01.mem_entitlement_grants WHERE grant_id = %s FOR UPDATE",
        (grant_id,),
    ).fetchone()
    if row is None:
        raise NotFound("grant_not_found")
    grant = entitlements.Grant(
        grant_id=str(row[0]), is_counted=bool(row[1]),
        granted_quantity=int(row[2]) if row[2] is not None else None,
        valid_from=row[3], valid_to=row[4], status=str(row[5]),
        brand_id=str(row[6]) if row[6] else None,
        location_id=str(row[7]) if row[7] else None,
        usable_from_minute=int(row[8]) if row[8] is not None else None,
        usable_to_minute=int(row[9]) if row[9] is not None else None)
    movements = [
        entitlements.Movement(str(m[0]), int(m[1]))
        for m in conn.execute(
            "SELECT movement_kind, delta FROM plt01.mem_entitlement_ledger"
            " WHERE grant_id = %s", (grant_id,)).fetchall()
    ]
    return grant, entitlements.balance_of(movements)


def _scope_of_location(
    conn: Connection[Any], location_id: str, moment: datetime,
) -> tuple[str, int]:
    """The location's brand and the local time there, as minutes since midnight.

    **Derived, never accepted.** `reserve_entitlement` took `brand_id` and `local_minute` from
    the caller beside the `location_id`, and `entitlements.usable` gates on both: a grant
    scoped to one brand was drawn on at another by sending the grant's own brand id, and an
    off-peak grant was drawn on at seven in the evening by sending `600`. The second is the
    worse of the two, because the whole point of an off-peak membership is that it is cheaper.
    This repository's recurring finding, for the fifth module running.

    The timezone is the location's own, which is why this cannot be computed in Python from a
    UTC instant: an off-peak window is stated in the member's local time and a server in UTC
    would refuse every evening draw in Amman and allow every one in Honolulu. PostgreSQL has
    the zone database; `AT TIME ZONE` is the conversion.
    """
    row = conn.execute(
        "SELECT brand_id,"
        " extract(hour FROM %s AT TIME ZONE timezone) * 60"
        " + extract(minute FROM %s AT TIME ZONE timezone)"
        " FROM plt01.locations WHERE location_id = %s",
        (moment, moment, location_id),
    ).fetchone()
    if row is None:
        raise NotFound("location_not_found")
    return str(row[0]), int(row[1])


def reserve_entitlement(
    pool: Pool, tenant_id: str, *, grant_id: str, purpose_kind: str, quantity: int,
    idempotency_key: str, actor_id: str, correlation_id: str,
    purpose_ref: str | None = None, location_id: str | None = None,
    at: datetime | None = None,
) -> dict[str, Any]:
    """ReserveEntitlement: hold quantity atomically, with an expiry.

    Paragraph 1506: "Reservation is atomic and expiring." Atomic because the grant is locked
    before the balance is summed and the row is inserted in the same transaction; expiring
    because a hold nothing settles would strand a member's own credit the first time a booking
    flow was abandoned.

    **The expiry is computed from the policy now and stored.** A policy change must neither
    extend nor expire a hold that already exists -- a hold whose expiry moved under it is the
    one a member loses a booking to.

    **The sweep of lapsed holds commits in its own transaction, before the draw.** It was in
    the same one, and `tenant_scope` rolls back on a raise -- so a refused draw threw away
    every expiry it had just recorded. That is the common case rather than an edge: the usual
    reason a member is short is holds that lapsed, so each attempt freed the quantity, refused
    on the balance it had read before freeing it, and rolled the freeing back. A member with
    three lapsed holds was refused for ever.

    Two transactions rather than the `_settled` shape, because the sweep is not evidence *of*
    the refusal -- it is independent work that is correct whether or not the draw succeeds, and
    it is idempotent and guarded on `status = 'held'`. The cost is that another member's draw
    can take the freed quantity in between, which is an honest race between two bookings and
    is decided correctly by the lock below.
    """
    moment = at or _now()
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    with tenant_scope(pool, tenant_id) as conn:
        _expire_lapsed_holds(conn, tenant_id, grant_id, moment=moment, actor_id=actor_id,
                             correlation_id=correlation_id)
    with tenant_scope(pool, tenant_id) as conn:
        brand_id: str | None = None
        local_minute: int | None = None
        if location_id is not None:
            brand_id, local_minute = _scope_of_location(conn, location_id, moment)
        grant, balance = _grant_locked(conn, grant_id)
        ttl = conn.execute(
            "SELECT p.reservation_ttl_seconds FROM plt01.mem_entitlement_grants g"
            " JOIN plt01.mem_entitlement_policies p ON p.policy_id = g.policy_id"
            " WHERE g.grant_id = %s",
            (grant_id,),
        ).fetchone()
        assert ttl is not None
        verdict = entitlements.usable(
            grant, at=moment, quantity=quantity,
            balance=balance if grant.is_counted else None,
            location_id=location_id, brand_id=brand_id, local_minute=local_minute)
        if not verdict.ok:
            raise Conflict(verdict.reason)
        expires_at = entitlements.reservation_expiry(
            held_at=moment, ttl_seconds=int(ttl[0]))
        row = conn.execute(
            """
            INSERT INTO plt01.mem_entitlement_reservations
                (tenant_id, grant_id, person_id, quantity, purpose_kind, purpose_ref,
                 held_at, expires_at, idempotency_key, held_by, correlation_id)
            SELECT %s, g.grant_id, g.person_id, %s, %s, %s, %s, %s, %s, %s, %s
            FROM plt01.mem_entitlement_grants g WHERE g.grant_id = %s
            ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
            RETURNING reservation_id
            """,
            (tenant_id, quantity, purpose_kind, purpose_ref, moment, expires_at,
             idempotency_key.strip(), actor_id, correlation_id, grant_id),
        ).fetchone()
        if row is None:
            existing = conn.execute(
                "SELECT reservation_id, grant_id, status FROM"
                " plt01.mem_entitlement_reservations WHERE idempotency_key = %s",
                (idempotency_key.strip(),),
            ).fetchone()
            assert existing is not None
            if str(existing[1]) != grant_id:
                raise Conflict("this_idempotency_key_belongs_to_another_grant")
            return {"reservation_id": str(existing[0]), "grant_id": grant_id,
                    "status": str(existing[2]), "balance_after": balance,
                    "repeated": True}
        reservation_id = str(row[0])
        if grant.is_counted:
            _movement(conn, tenant_id, grant_id=grant_id, movement_kind="reserve",
                      delta=-quantity, reason=f"held for {purpose_kind}",
                      actor_id=actor_id, correlation_id=correlation_id,
                      reservation_id=reservation_id)
            balance -= quantity
        _append(conn, tenant_id, "entitlement.reserved", "entitlement", grant_id,
                {"grant_id": grant_id, "reservation_id": reservation_id,
                 "quantity": quantity, "purpose_kind": purpose_kind,
                 "expires_at": expires_at.isoformat()},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"reservation_id": reservation_id, "grant_id": grant_id, "status": "held",
            "expires_at": expires_at.isoformat(), "balance_after": balance,
            "repeated": False}


def _expire_lapsed_holds(
    conn: Connection[Any], tenant_id: str, grant_id: str, *, moment: datetime,
    actor_id: str, correlation_id: str,
) -> int:
    """Settle every hold on this grant whose expiry has passed, returning the quantity freed.

    **The read path sweeps, because nothing else does.** There is no worker runtime in this
    build -- the ninth module to want one -- and a lapsed hold that nobody settles reduces a
    member's balance for ever. Doing it here, inside the transaction that is about to read the
    balance, means the answer is right at the moment it is used.

    Each settlement is guarded on `status = 'held'`, so a hold another transaction has just
    consumed is not expired out from under it.
    """
    lapsed = conn.execute(
        "SELECT reservation_id, quantity FROM plt01.mem_entitlement_reservations"
        " WHERE grant_id = %s AND status = 'held' AND expires_at <= %s FOR UPDATE",
        (grant_id, moment),
    ).fetchall()
    freed = 0
    for reservation_id, quantity in lapsed:
        settled = conn.execute(
            "UPDATE plt01.mem_entitlement_reservations SET status = 'expired',"
            " settled_at = %s, settled_by = %s, settle_correlation_id = %s"
            " WHERE reservation_id = %s AND status = 'held'",
            (moment, actor_id, correlation_id, str(reservation_id)),
        ).rowcount
        if settled == 0:
            continue
        counted = conn.execute(
            "SELECT is_counted FROM plt01.mem_entitlement_grants WHERE grant_id = %s",
            (grant_id,),
        ).fetchone()
        if counted is not None and bool(counted[0]):
            _movement(conn, tenant_id, grant_id=grant_id,
                      movement_kind="reservation_expired", delta=int(quantity),
                      reason="the hold lapsed unsettled", actor_id=actor_id,
                      correlation_id=correlation_id,
                      reservation_id=str(reservation_id))
        freed += int(quantity)
    return freed


def settle_reservation(
    pool: Pool, tenant_id: str, reservation_id: str, *, outcome: str, actor_id: str,
    correlation_id: str, reason: str | None = None, at: datetime | None = None,
) -> dict[str, Any]:
    """ConsumeEntitlement or ReleaseEntitlement, depending on `outcome`.

    **One command for both, because they are one decision made two ways** -- the service
    delivered or it did not -- and two commands would be two places to get the ledger sign
    wrong. A consumption moves nothing: the quantity left the balance when it was held, and
    taking it again is the double-count the schema's `consume_is_neutral` constraint exists to
    refuse.

    **Only a held reservation settles**, guarded on the UPDATE's row count rather than on a
    prior read. A reservation two callers settle concurrently must settle once, and a read-then-
    write would let the second overwrite the first's outcome and its actor.
    """
    moment = at or _now()
    if outcome not in ("consumed", "released"):
        raise InvalidRequest("a_reservation_is_consumed_or_released")
    if outcome == "released" and not (reason or "").strip():
        raise InvalidRequest("a_release_states_why")
    with tenant_scope(pool, tenant_id) as conn:
        held = conn.execute(
            "SELECT grant_id, quantity, status FROM plt01.mem_entitlement_reservations"
            " WHERE reservation_id = %s FOR UPDATE",
            (reservation_id,),
        ).fetchone()
        if held is None:
            raise NotFound("reservation_not_found")
        if str(held[2]) != "held":
            raise Conflict(f"this_reservation_is_already_{held[2]}")
        grant_id, quantity = str(held[0]), int(held[1])
        settled = conn.execute(
            "UPDATE plt01.mem_entitlement_reservations SET status = %s, settled_at = %s,"
            " settled_by = %s, settle_correlation_id = %s, settle_reason = %s"
            " WHERE reservation_id = %s AND status = 'held'",
            (outcome, moment, actor_id, correlation_id,
             (reason or "").strip() or None, reservation_id),
        ).rowcount
        if settled == 0:
            raise Conflict("this_reservation_was_settled_by_somebody_else")
        counted = conn.execute(
            "SELECT is_counted FROM plt01.mem_entitlement_grants WHERE grant_id = %s",
            (grant_id,),
        ).fetchone()
        assert counted is not None
        if bool(counted[0]):
            if outcome == "consumed":
                _movement(conn, tenant_id, grant_id=grant_id, movement_kind="consume",
                          delta=0, reason="the service was delivered", actor_id=actor_id,
                          correlation_id=correlation_id, reservation_id=reservation_id)
            else:
                _movement(conn, tenant_id, grant_id=grant_id, movement_kind="release",
                          delta=quantity, reason=(reason or "").strip(),
                          actor_id=actor_id, correlation_id=correlation_id,
                          reservation_id=reservation_id)
        _append(conn, tenant_id,
                "entitlement.consumed" if outcome == "consumed" else "entitlement.released",
                "entitlement", grant_id,
                {"grant_id": grant_id, "reservation_id": reservation_id,
                 "quantity": quantity},
                correlation_id=correlation_id, actor_id=actor_id)
        _, balance = _grant_locked(conn, grant_id)
    return {"reservation_id": reservation_id, "grant_id": grant_id, "status": outcome,
            "balance_after": balance}


def revoke_grants_of_ended_memberships(
    pool: Pool, tenant_id: str, *, actor_id: str, correlation_id: str,
    at: datetime | None = None, limit: int = 200,
) -> dict[str, Any]:
    """Revoke the grants of memberships whose end has passed, which nothing did before.

    **This is the half of a future-dated cancellation that never arrived.**
    `cancel_membership` revokes grants in its own transaction when the date is today or
    earlier, and deliberately does not when it is later: "the member is still paying for the
    notice period and still entitled to train". Nothing revoked them when the date came, so a
    member who cancelled with notice kept drawing on their entitlements afterwards -- which is
    `_revoke_grants`' own "access the member is no longer paying for", in the path that
    survived the fix.

    **The door was never wrong and the entitlement was**, which is why this was easy to miss.
    MOD-022 reads the membership's dates rather than its cached status, and says so in a
    comment: a row that reads `active` can be a membership that ended last month, so the
    turnstile refuses. `entitlements.usable` sees only the grant -- its own status and its own
    `valid_to`, which is optional -- so a perpetual grant from a cancelled membership stayed
    drawable and a booking took a place somebody paying could have had.

    **No new decision.** The person cancelled, with an effective date, and that decision is a
    row; this applies it. `ends_on` is what the cancellation wrote and what the door already
    judges by, so the predicate is the same fact in both places rather than a second rule.

    **A failure on one membership must not stop the rest** -- MOD-010's relay. Each membership
    is revoked in its own transaction so a grant that cannot be locked leaves the others alone,
    and the failure is named rather than counted.

    Idempotent by the predicate: `_revoke_grants` selects `status = 'active'`, so a second pass
    over the same membership finds nothing and writes nothing.
    """
    if limit < 1 or limit > 500:
        raise InvalidRequest("limit_out_of_range")
    moment = at or _now()
    today = moment.date()
    with tenant_scope(pool, tenant_id) as conn:
        due = conn.execute(
            """
            SELECT DISTINCT m.membership_id FROM plt01.mem_memberships m
            JOIN plt01.mem_entitlement_grants g ON g.membership_id = m.membership_id
            WHERE m.ends_on IS NOT NULL AND m.ends_on < %s AND g.status = 'active'
            ORDER BY m.membership_id
            LIMIT %s
            """,
            (today, limit),
        ).fetchall()
    memberships = [str(r[0]) for r in due]

    revoked = 0
    failed: list[dict[str, str]] = []
    for membership_id in memberships:
        try:
            with tenant_scope(pool, tenant_id) as conn:
                gone = _revoke_grants(
                    conn, tenant_id, membership_id=membership_id,
                    reason="the membership ended and its notice period has run out",
                    actor_id=actor_id, correlation_id=correlation_id, moment=moment)
            revoked += len(gone)
        except ServiceError as e:
            failed.append({"membership_id": membership_id, "reason": str(e)})
    return {"memberships": len(memberships), "grants_revoked": revoked, "failed": failed,
            "truncated": len(memberships) == limit}


def _revoke_grants(
    conn: Connection[Any], tenant_id: str, *, membership_id: str, reason: str,
    actor_id: str, correlation_id: str, moment: datetime,
) -> list[dict[str, Any]]:
    """Revoke every live grant this membership gave, returning what was revoked.

    **A cancelled membership whose entitlements still work is access the member is no longer
    paying for.** Paragraph 1496 keeps membership state, billing state and access state apart,
    and that separation is about not *conflating* them -- not about leaving them unrelated. The
    first version of this module cancelled the membership and left every grant `active`, so a
    member with twenty classes left kept all twenty and the turnstile had no reason to stop
    them. The entitlement is what COM-01 calls the fulfilment authority; cancelling the
    agreement it came from has to reach it.

    **What is held stays held.** A reservation is a booking somebody made, and voiding it from
    here would cancel a class the member is about to attend without telling the system that
    schedules it. The grant stops being drawable; the holds settle their own way.

    Each revocation is a ledger row for what remained, so the balance afterwards is zero by
    arithmetic rather than by the status column saying so.
    """
    revoked: list[dict[str, Any]] = []
    rows = conn.execute(
        "SELECT grant_id FROM plt01.mem_entitlement_grants"
        " WHERE membership_id = %s AND status = 'active' ORDER BY created_at",
        (membership_id,),
    ).fetchall()
    for (grant_id,) in rows:
        grant, balance = _grant_locked(conn, str(grant_id))
        if grant.status != "active":
            continue
        if grant.is_counted and balance > 0:
            _movement(conn, tenant_id, grant_id=str(grant_id), movement_kind="revoke",
                      delta=-balance, reason=reason, actor_id=actor_id,
                      correlation_id=correlation_id)
        conn.execute(
            "UPDATE plt01.mem_entitlement_grants SET status = 'revoked', revoked_at = %s,"
            " revoked_by = %s, revoke_reason = %s, version = version + 1"
            " WHERE grant_id = %s AND status = 'active'",
            (moment, actor_id, reason, str(grant_id)))
        person = conn.execute(
            "SELECT person_id, policy_id FROM plt01.mem_entitlement_grants"
            " WHERE grant_id = %s", (str(grant_id),)).fetchone()
        assert person is not None
        _append(conn, tenant_id, "entitlement.revoked", "entitlement", str(grant_id),
                {"grant_id": str(grant_id), "person_id": str(person[0]),
                 "policy_id": str(person[1])},
                correlation_id=correlation_id, actor_id=actor_id)
        revoked.append({"grant_id": str(grant_id),
                        "quantity_revoked": balance if grant.is_counted else None})
    return revoked


def revoke_entitlement(
    pool: Pool, tenant_id: str, grant_id: str, *, reason: str, actor_id: str,
    correlation_id: str, at: datetime | None = None,
) -> dict[str, Any]:
    """RevokeEntitlement: stop a grant being drawable, and write off what was left.

    **A revocation is not a deletion.** The grant, its ledger and every reservation taken
    against it stay exactly where they are; what changes is that the balance goes to zero by a
    movement with an actor and a reason on it. "How many classes did this member lose and who
    decided" is a question a complaint turns on.
    """
    moment = at or _now()
    if not reason.strip():
        raise InvalidRequest("a_revocation_states_why")
    with tenant_scope(pool, tenant_id) as conn:
        grant, balance = _grant_locked(conn, grant_id)
        if grant.status == "revoked":
            return {"grant_id": grant_id, "status": "revoked", "quantity_revoked": 0,
                    "repeated": True}
        if grant.status != "active":
            raise Conflict(f"this_entitlement_is_{grant.status}")
        written_off = balance if grant.is_counted else None
        if grant.is_counted and balance > 0:
            _movement(conn, tenant_id, grant_id=grant_id, movement_kind="revoke",
                      delta=-balance, reason=reason.strip(), actor_id=actor_id,
                      correlation_id=correlation_id)
        conn.execute(
            "UPDATE plt01.mem_entitlement_grants SET status = 'revoked', revoked_at = %s,"
            " revoked_by = %s, revoke_reason = %s, version = version + 1"
            " WHERE grant_id = %s AND status = 'active'",
            (moment, actor_id, reason.strip(), grant_id))
        row = conn.execute(
            "SELECT person_id, policy_id FROM plt01.mem_entitlement_grants"
            " WHERE grant_id = %s", (grant_id,)).fetchone()
        assert row is not None
        _append(conn, tenant_id, "entitlement.revoked", "entitlement", grant_id,
                {"grant_id": grant_id, "person_id": str(row[0]),
                 "policy_id": str(row[1])},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"grant_id": grant_id, "status": "revoked",
            "quantity_revoked": written_off, "repeated": False}


def entitlement_balance(
    pool: Pool, tenant_id: str, grant_id: str, *, actor_id: str, correlation_id: str,
    at: datetime | None = None,
) -> dict[str, Any]:
    """What is left on a grant, and how much of it is held.

    "You have two classes left" and "two of your classes are held for a booking you have not
    attended" are different answers to the same question, and a member asking gets both.

    **This read takes an actor, because it can write.** Sweeping lapsed holds inserts ledger
    rows, and every row in that ledger names who caused it -- a sweep attributed to a nil uuid
    would be the "evidence with nobody's name on it" shape this build has shipped four times,
    arrived at by the side door of calling it a read. The caller is whoever asked; they are
    gated, so there is always one.
    """
    moment = at or _now()
    with tenant_scope(pool, tenant_id) as conn:
        _expire_lapsed_holds(conn, tenant_id, grant_id, moment=moment, actor_id=actor_id,
                             correlation_id=correlation_id)
        grant, balance = _grant_locked(conn, grant_id)
        # Holds come from the reservations in `held` status, which is the row that *is* the
        # hold -- not from the ledger, whose language is about the balance.
        live = [
            int(r[0]) for r in conn.execute(
                "SELECT quantity FROM plt01.mem_entitlement_reservations"
                " WHERE grant_id = %s AND status = 'held'", (grant_id,)).fetchall()
        ]
    return {"grant_id": grant_id, "is_counted": grant.is_counted,
            "granted_quantity": grant.granted_quantity,
            "balance": balance if grant.is_counted else None,
            "held": entitlements.held_quantity(live) if grant.is_counted else None,
            "status": grant.status,
            "valid_from": grant.valid_from.isoformat(),
            "valid_to": grant.valid_to.isoformat() if grant.valid_to else None}


# ------------------------------------------------------------------ billing and invoicing

def create_billing_account(
    pool: Pool, tenant_id: str, *, payer_person_id: str, account_number: str,
    currency: str, legal_entity_id: str, actor_id: str, correlation_id: str,
    account_kind: str = "individual", payment_terms_days: int = 0,
) -> dict[str, Any]:
    """CreateBillingAccount. COM-03-R01's consolidated household and corporate billing.

    The account is who *pays*, which is not always the member who *owes*: a parent pays for
    three children and a company for forty employees. One account, many schedules.
    """
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.fin_billing_accounts
                    (tenant_id, payer_person_id, account_kind, account_number, currency,
                     legal_entity_id, payment_terms_days, created_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING billing_account_id
                """,
                (tenant_id, payer_person_id, account_kind, account_number.upper(),
                 currency.upper(), legal_entity_id, payment_terms_days, actor_id,
                 correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_account_number_already_exists") from None
        except errors.ForeignKeyViolation as e:
            raise NotFound(_fk_subject(e)) from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
    return {"billing_account_id": str(row[0]), "account_number": account_number.upper(),
            "currency": currency.upper(), "account_kind": account_kind}


def open_fiscal_series(
    pool: Pool, tenant_id: str, *, legal_entity_id: str, series_code: str,
    actor_id: str, correlation_id: str, document_kind: str = "invoice",
) -> dict[str, Any]:
    """Open a numbering series for one legal entity. COM-03-R07."""
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.fin_fiscal_series
                    (tenant_id, legal_entity_id, series_code, document_kind, created_by,
                     correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING series_id
                """,
                (tenant_id, legal_entity_id, series_code.upper(), document_kind, actor_id,
                 correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_series_already_exists_for_this_legal_entity") from None
        except errors.ForeignKeyViolation as e:
            raise NotFound(_fk_subject(e)) from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
    return {"series_id": str(row[0]), "series_code": series_code.upper(),
            "document_kind": document_kind, "last_serial": 0}


def _allocate_serial(conn: Connection[Any], series_id: str) -> tuple[int, str]:
    """The next serial in a series, under a lock. Returns `(serial, series_code)`.

    **`FOR UPDATE`, and `last_serial + 1` with no skipping.** A PostgreSQL sequence would be
    faster and is explicitly non-transactional: it leaves gaps when a transaction rolls back,
    and a gap in a tax series is something an authority asks about. Two invoices sharing a
    serial is worse still -- a tax offence rather than a bug -- so the counter is a row and the
    lock is what makes it one number at a time.
    """
    row = conn.execute(
        "SELECT series_code, last_serial, status FROM plt01.fin_fiscal_series"
        " WHERE series_id = %s FOR UPDATE",
        (series_id,),
    ).fetchone()
    if row is None:
        raise NotFound("fiscal_series_not_found")
    if str(row[2]) != "active":
        raise Conflict("this_fiscal_series_is_closed")
    serial = int(row[1]) + 1
    conn.execute(
        "UPDATE plt01.fin_fiscal_series SET last_serial = %s WHERE series_id = %s",
        (serial, series_id))
    return serial, str(row[0])


def issue_invoice(
    pool: Pool, tenant_id: str, *, billing_account_id: str, series_id: str,
    lines: list[dict[str, Any]], issued_on: date, due_on: date, jurisdiction: str,
    idempotency_key: str, actor_id: str, correlation_id: str,
    membership_id: str | None = None, schedule_id: str | None = None,
    credits_invoice_id: str | None = None, unearned_minor: int = 0,
) -> dict[str, Any]:
    """IssueInvoice: the document, its lines, its serial and its tax records, atomically.

    **No draft state.** The five figures, the lines, the serial and the tax are what was
    issued, and the row exists only once it has been -- MOD-015 made the same call and the
    reason is the same: a correction is a credit note, so there is nothing for a draft to be.

    **The tax records are written in the same transaction**, one per rate, because an invoice
    whose tax liability was recorded a moment later is an invoice that can exist without one if
    the second write fails. That is MOD-010's `append_event` argument applied to a tax return.

    The rate comes from the caller per line. Rates are jurisdictional and the sources state
    none -- MOD-015's `issue_invoice` set that precedent and MOD-016 followed it -- so what is
    enforced here is that whatever rate was applied is recorded on the line and in the return.

    **A credit note is issued through this same command**, with `credits_invoice_id` set and a
    series whose `document_kind` is `credit_note`. The first version could not issue one at
    all: it never passed the column, and `fin_invoices_credit_note_credits_something` makes
    `document_kind = 'credit_note'` and a credited invoice the same fact -- so a credit-note
    series existed, could be opened, and refused every document anybody tried to number from
    it. The module's own header calls the credit note "the only correction path" there is, and
    it was unreachable.

    The amounts on a credit note are positive, like MOD-015's, and read as a reduction by
    `_apply_to_invoice`; a credit for more than the invoice it credits is refused, because a
    credit note is a correction and not a way to pay somebody.

    **`unearned_minor` is the part of the net that has not been delivered yet**, and it is
    paragraph 1695 in one argument: a year's membership billed in January credits MOD-018's
    `unearned_revenue` rather than `revenue`, and a recognition schedule moves it across as the
    service is delivered. Only the caller knows what was sold, which is why it is an argument;
    zero -- a retail sale, a joining fee -- is the ordinary case.
    """
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    try:
        totals = invoicing.compute_totals([
            invoicing.LineInput(
                description=str(item.get("description", "")),
                quantity=int(item.get("quantity", 1)),
                unit_net_minor=int(item.get("unit_net_minor", 0)),
                tax_rate_bp=int(item.get("tax_rate_bp", 0)),
                variant_id=item.get("variant_id"),
                price_resolution_id=item.get("price_resolution_id"),
                tax_category_id=item.get("tax_category_id"))
            for item in lines])
    except invoicing.InvoicingError as e:
        raise InvalidRequest(str(e)) from None
    with tenant_scope(pool, tenant_id) as conn:
        account = conn.execute(
            "SELECT currency, legal_entity_id, status FROM plt01.fin_billing_accounts"
            " WHERE billing_account_id = %s",
            (billing_account_id,),
        ).fetchone()
        if account is None:
            raise NotFound("billing_account_not_found")
        if str(account[2]) != "active":
            raise Conflict(f"this_billing_account_is_{account[2]}")
        currency, legal_entity_id = str(account[0]), str(account[1])
        # **The series must belong to the account's legal entity.** A serial drawn from another
        # entity's series would break COM-03-R07's per-entity uniqueness from the side nobody
        # watches: the index would still hold, and the number would be filed under the wrong
        # taxpayer. Derived from the account rather than taken beside it.
        series = conn.execute(
            "SELECT legal_entity_id, document_kind FROM plt01.fin_fiscal_series"
            " WHERE series_id = %s",
            (series_id,),
        ).fetchone()
        if series is None:
            raise NotFound("fiscal_series_not_found")
        if str(series[0]) != legal_entity_id:
            raise Conflict("this_series_belongs_to_another_legal_entity")
        document_kind = str(series[1])
        if (document_kind == "credit_note") != (credits_invoice_id is not None):
            raise InvalidRequest("a_credit_note_credits_an_invoice_and_nothing_else_does")
        if credits_invoice_id is not None:
            credited = conn.execute(
                "SELECT billing_account_id, currency, gross_minor FROM plt01.fin_invoices"
                " WHERE invoice_id = %s AND document_kind = 'invoice' FOR UPDATE",
                (credits_invoice_id,),
            ).fetchone()
            if credited is None:
                raise NotFound("invoice_not_found")
            if str(credited[0]) != billing_account_id:
                raise Conflict("that_invoice_belongs_to_another_billing_account")
            if str(credited[1]) != currency:
                raise Conflict("that_invoice_is_in_another_currency")
            outstanding = conn.execute(
                "SELECT coalesce(sum(gross_minor), 0) FROM plt01.fin_invoices"
                " WHERE credits_invoice_id = %s",
                (credits_invoice_id,),
            ).fetchone()
            room = int(credited[2]) - (int(outstanding[0]) if outstanding else 0)
            if totals.gross_minor > room:
                raise Conflict(
                    f"{room} of that invoice is uncredited and "
                    f"{totals.gross_minor} was asked")
        existing = conn.execute(
            "SELECT invoice_id, document_number, billing_account_id, net_minor,"
            " tax_minor, gross_minor, currency, serial, payment_status, fiscal_status"
            " FROM plt01.fin_invoices WHERE idempotency_key = %s",
            (idempotency_key.strip(),),
        ).fetchone()
        if existing is not None:
            # **The key has to belong to this account.** It is unique per tenant, so a key
            # reused across two payers returned the *other* payer's invoice and reported the
            # call as a successful repeat -- the caller believes it has billed account B and
            # the money is owed by account A. MOD-016's finding, where a key reused across two
            # coupon codes told the caller the second had been redeemed.
            if str(existing[2]) != billing_account_id:
                raise Conflict("this_idempotency_key_belongs_to_another_billing_account")
            return {"invoice_id": str(existing[0]),
                    "document_number": str(existing[1]), "serial": int(existing[7]),
                    "net_minor": int(existing[3]), "tax_minor": int(existing[4]),
                    "gross_minor": int(existing[5]), "currency": str(existing[6]),
                    "payment_status": str(existing[8]),
                    "fiscal_status": str(existing[9]), "repeated": True}
        serial, series_code = _allocate_serial(conn, series_id)
        number = invoicing.document_number(series_code, serial)
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.fin_invoices
                    (tenant_id, billing_account_id, legal_entity_id, series_id, serial,
                     document_number, document_kind, schedule_id, membership_id,
                     credits_invoice_id, net_minor, tax_minor, gross_minor, currency,
                     issued_on, due_on, idempotency_key, issued_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s)
                RETURNING invoice_id
                """,
                (tenant_id, billing_account_id, legal_entity_id, series_id, serial,
                 number, document_kind, schedule_id, membership_id, credits_invoice_id,
                 totals.net_minor, totals.tax_minor, totals.gross_minor, currency,
                 issued_on, due_on, idempotency_key.strip(), actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_invoice_was_issued_by_somebody_else") from None
        except errors.ForeignKeyViolation as e:
            raise NotFound(_fk_subject(e)) from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        invoice_id = str(row[0])
        for line in totals.lines:
            try:
                conn.execute(
                    """
                    INSERT INTO plt01.fin_invoice_lines
                        (tenant_id, invoice_id, line_number, description, variant_id,
                         price_resolution_id, tax_category_id, quantity, unit_net_minor,
                         net_minor, tax_rate_bp, tax_minor, gross_minor)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (tenant_id, invoice_id, line.line_number, line.description,
                     line.variant_id, line.price_resolution_id, line.tax_category_id,
                     line.quantity, line.unit_net_minor, line.net_minor,
                     line.tax_rate_bp, line.tax_minor, line.gross_minor))
            except errors.ForeignKeyViolation as e:
                raise NotFound(_fk_subject(e)) from None
            except errors.CheckViolation as e:
                raise InvalidRequest(_check_name(e)) from None
        for rate, taxable, taxed in totals.tax_by_rate:
            try:
                conn.execute(
                    """
                    INSERT INTO plt01.fin_tax_records
                        (tenant_id, invoice_id, legal_entity_id, jurisdiction,
                         tax_rate_bp, taxable_minor, tax_minor, currency, period_start,
                         period_end, recorded_by, correlation_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (tenant_id, invoice_id, legal_entity_id, jurisdiction.upper(), rate,
                     taxable, taxed, currency, issued_on, issued_on, actor_id,
                     correlation_id))
            except errors.CheckViolation as e:
                raise InvalidRequest(_check_name(e)) from None
        _append(conn, tenant_id, "invoice.issued", "invoice", invoice_id,
                {"invoice_id": invoice_id, "billing_account_id": billing_account_id,
                 "document_number": number, "currency": currency,
                 "gross_minor": totals.gross_minor, "due_on": due_on.isoformat()},
                correlation_id=correlation_id, actor_id=actor_id)
        # A credit note changes what is owed on the invoice it credits, in the same
        # transaction that issued it: an invoice fully credited and still reading `unpaid` is
        # one a dunning sweep opens a recovery journey against.
        if credits_invoice_id is not None:
            _apply_to_invoice(conn, tenant_id, credits_invoice_id, at=issued_on)
        # **MOD-018 posts the receivable in this transaction.** An invoice without its journal
        # is a balance the ledger does not know about, and a journal without its invoice is
        # money the ledger invented -- so the posting runs on this connection. A tenant with no
        # chart of accounts gets the invoice and a reason, because the chart is configuration
        # and a tenant mid-setup must not find its till has stopped working.
        if credits_invoice_id is None:
            ledger_result = ledger.post_invoice(
                conn, tenant_id, invoice_id=invoice_id,
                legal_entity_id=legal_entity_id, net_minor=totals.net_minor,
                tax_minor=totals.tax_minor, currency=currency, issued_on=issued_on,
                document_number=number, actor_id=actor_id,
                correlation_id=correlation_id,
                subject_person_id=_payer_of(conn, billing_account_id),
                unearned_minor=unearned_minor)
        else:
            ledger_result = ledger.post_credit_note(
                conn, tenant_id, invoice_id=invoice_id,
                legal_entity_id=legal_entity_id, net_minor=totals.net_minor,
                tax_minor=totals.tax_minor, currency=currency, issued_on=issued_on,
                document_number=number, actor_id=actor_id,
                correlation_id=correlation_id,
                subject_person_id=_payer_of(conn, billing_account_id))
    return {"invoice_id": invoice_id, "document_number": number, "serial": serial,
            "net_minor": totals.net_minor, "tax_minor": totals.tax_minor,
            "gross_minor": totals.gross_minor, "currency": currency,
            "document_kind": document_kind, "credits_invoice_id": credits_invoice_id,
            "payment_status": "unpaid", "fiscal_status": "pending", "repeated": False,
            **ledger_result}


# ------------------------------------------------------------------ payments

def create_payment_intent(
    pool: Pool, tenant_id: str, *, billing_account_id: str, amount_minor: int,
    method: str, provider_key: str, idempotency_key: str,
    actor_id: str, correlation_id: str, invoice_id: str | None = None,
    payment_method_ref: str | None = None,
) -> dict[str, Any]:
    """CreatePaymentIntent: what a provider is about to be asked to do.

    **The intent exists before anything is attempted**, which is paragraph 1609's "persist
    PENDING explicitly". A provider that times out then leaves a row saying what was asked,
    and the reconciliation has something to ask about. Creating the intent *after* the attempt
    would mean a timed-out charge with no record of itself -- the state that becomes a double
    charge the next time somebody retries.

    **Nothing here talks to a provider**, and that is owner-reserved rather than unfinished:
    taking money is real financial expenditure. What this builds is the half that must be
    correct whatever the provider turns out to be.
    """
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    with tenant_scope(pool, tenant_id) as conn:
        account = conn.execute(
            "SELECT currency, status FROM plt01.fin_billing_accounts"
            " WHERE billing_account_id = %s",
            (billing_account_id,),
        ).fetchone()
        if account is None:
            raise NotFound("billing_account_not_found")
        if str(account[1]) != "active":
            raise Conflict(f"this_billing_account_is_{account[1]}")
        # **The currency is the account's, and there is no parameter for one.** A caller able
        # to send it could create an intent for 4500 USD against an invoice for 4500 JOD --
        # two minor-unit counts that are equal and mean different sums of money, which is the
        # comparison MOD-015's whole money discipline forbids and MOD-016 shipped once in its
        # approvals. Derive, never accept: the strongest form of that rule is not having the
        # argument.
        if invoice_id is not None:
            invoice = conn.execute(
                "SELECT billing_account_id, currency FROM plt01.fin_invoices"
                " WHERE invoice_id = %s",
                (invoice_id,),
            ).fetchone()
            if invoice is None:
                raise NotFound("invoice_not_found")
            if str(invoice[0]) != billing_account_id:
                raise Conflict("this_invoice_belongs_to_another_billing_account")
            if str(invoice[1]) != str(account[0]):
                raise Conflict("this_invoice_is_in_another_currency")
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.fin_payment_intents
                    (tenant_id, billing_account_id, invoice_id, method, provider_key,
                     payment_method_ref, amount_minor, currency, idempotency_key,
                     created_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
                RETURNING intent_id
                """,
                (tenant_id, billing_account_id, invoice_id, method, provider_key,
                 payment_method_ref, amount_minor, str(account[0]),
                 idempotency_key.strip(), actor_id, correlation_id),
            ).fetchone()
        except errors.CheckViolation as e:
            # `payment_method_ref` has to look like a locator, which is the control paragraph
            # 1597 rests on -- and a card number pasted into it answered 500 with a database
            # exception rather than a 422 saying what was wrong. MOD-009 found the same thing
            # for eight of its own routes.
            raise InvalidRequest(_check_name(e)) from None
        if row is None:
            prior = conn.execute(
                "SELECT intent_id, status, billing_account_id FROM"
                " plt01.fin_payment_intents WHERE idempotency_key = %s",
                (idempotency_key.strip(),),
            ).fetchone()
            assert prior is not None
            if str(prior[2]) != billing_account_id:
                raise Conflict("this_idempotency_key_belongs_to_another_account")
            return {"intent_id": str(prior[0]), "status": str(prior[1]), "repeated": True}
    return {"intent_id": str(row[0]), "status": "pending",
            "amount_minor": amount_minor, "currency": str(account[0]),
            "repeated": False}


def settle_payment_intent(
    pool: Pool, tenant_id: str, intent_id: str, *, outcome: str, actor_id: str,
    correlation_id: str, provider_ref: str | None = None,
    failure_code: str | None = None, failure_detail: str | None = None,
    received_at: datetime | None = None, cash_account_id: str | None = None,
) -> dict[str, Any]:
    """ApplyPayment or RecordPaymentFailure: what the provider says happened.

    **A success writes the payment in the same transaction as the intent's settlement**, and
    one payment per intent is a unique index rather than a check -- a provider callback
    delivered twice is the ordinary case, and the index is what makes the replay free instead
    of a double charge.

    **`unknown` is a real outcome and it is not a failure.** A provider that answered nothing
    has told us nothing; recording that as declined is how a member is dunned for a payment
    that actually succeeded. It settles nothing, publishes nothing, and leaves the intent for
    the reconciliation.

    **Only an unsettled intent settles**, guarded on the UPDATE's row count. Two callbacks
    arriving together must produce one settlement, and a read-then-write would let the second
    overwrite the first -- MOD-013's lease finding and MOD-010's delivery finding, both of
    which were exactly this.
    """
    moment = received_at or _now()
    if outcome not in ("succeeded", "failed", "cancelled", "unknown"):
        raise InvalidRequest("an_intent_settles_as_succeeded_failed_cancelled_or_unknown")
    if outcome == "failed" and not (failure_code or "").strip():
        raise InvalidRequest("a_failure_carries_a_code")
    with tenant_scope(pool, tenant_id) as conn:
        intent = conn.execute(
            "SELECT billing_account_id, invoice_id, method, amount_minor, currency, status"
            " FROM plt01.fin_payment_intents WHERE intent_id = %s FOR UPDATE",
            (intent_id,),
        ).fetchone()
        if intent is None:
            raise NotFound("payment_intent_not_found")
        current = str(intent[5])
        if current in ("succeeded", "failed", "cancelled"):
            raise Conflict(f"this_intent_is_already_{current}")
        if outcome == "unknown":
            conn.execute(
                "UPDATE plt01.fin_payment_intents SET status = 'unknown',"
                " attempts = attempts + 1, failure_detail = %s"
                " WHERE intent_id = %s AND status IN ('pending',"
                " 'requires_authentication', 'unknown')",
                ((failure_detail or "").strip() or None, intent_id))
            return {"intent_id": intent_id, "status": "unknown",
                    "reason": "the provider did not answer; nothing is settled"}
        try:
            # **The provider reference is unique per provider**, which is what makes a
            # replayed webhook free -- and this UPDATE is where it is written, so a provider
            # that sends one reference for two intents violated that index here and the
            # caller got a 500 with the transaction aborted. A provider reusing a reference
            # is a provider bug; answering 409 says which one.
            settled = conn.execute(
                "UPDATE plt01.fin_payment_intents SET status = %s, settled_at = %s,"
                " provider_ref = coalesce(%s, provider_ref), failure_code = %s,"
                " failure_detail = %s, attempts = attempts + 1"
                " WHERE intent_id = %s AND status IN ('pending',"
                " 'requires_authentication', 'unknown')",
                (outcome, moment, provider_ref, (failure_code or "").strip() or None,
                 (failure_detail or "").strip() or None, intent_id),
            ).rowcount
        except errors.UniqueViolation:
            raise Conflict(
                "this_provider_reference_belongs_to_another_intent") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        if settled == 0:
            raise Conflict("this_intent_was_settled_by_somebody_else")
        payment_id: str | None = None
        # **The posting's verdict reaches the caller.** The first version computed it and threw
        # it away, so a cash payment with no till named -- which the route could not name at
        # all -- was silently not posted while the response read as an ordinary success.
        ledger_result: dict[str, Any] = {}
        if outcome == "succeeded":
            try:
                paid = conn.execute(
                    """
                    INSERT INTO plt01.fin_payments
                        (tenant_id, billing_account_id, intent_id, invoice_id, method,
                         amount_minor, currency, received_at, provider_ref, recorded_by,
                         correlation_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING payment_id
                    """,
                    (tenant_id, str(intent[0]), intent_id, intent[1], str(intent[2]),
                     int(intent[3]), str(intent[4]), moment, provider_ref, actor_id,
                     correlation_id),
                ).fetchone()
            except errors.UniqueViolation:
                raise Conflict("this_intent_has_already_produced_a_payment") from None
            except errors.CheckViolation as e:
                raise InvalidRequest(_check_name(e)) from None
            assert paid is not None
            payment_id = str(paid[0])
            if intent[1] is not None:
                _apply_to_invoice(conn, tenant_id, str(intent[1]), at=moment.date())
            # **MOD-018 posts the money in this transaction.** A payment recorded without its
            # clearing entry is a receivable the ledger still thinks is owed, and the
            # settlement import that reconciles the provider has nothing to match against.
            entity = conn.execute(
                "SELECT legal_entity_id FROM plt01.fin_billing_accounts"
                " WHERE billing_account_id = %s",
                (str(intent[0]),),
            ).fetchone()
            if entity is not None:
                ledger_result = ledger.allocate_payment(
                    conn, tenant_id, payment_id=payment_id,
                    legal_entity_id=str(entity[0]), amount_minor=int(intent[3]),
                    currency=str(intent[4]), method=str(intent[2]),
                    received_on=moment.date(), actor_id=actor_id,
                    correlation_id=correlation_id,
                    subject_person_id=_payer_of(conn, str(intent[0])),
                    cash_account_id=cash_account_id)
            _append(conn, tenant_id, "payment.succeeded", "payment", payment_id,
                    {"payment_id": payment_id, "intent_id": intent_id,
                     "billing_account_id": str(intent[0]),
                     "amount_minor": int(intent[3]), "currency": str(intent[4])},
                    correlation_id=correlation_id, actor_id=actor_id)
        elif outcome == "failed":
            # **No `failure_detail` in the payload.** It is the provider's own sentence and the
            # realistic content of one is `declined for card 4242... held by JANE SMITH`. The
            # outbox is the one store in this build no erasure reaches, and MOD-013 shipped
            # exactly this with an SMTP rejection.
            _append(conn, tenant_id, "payment.failed", "intent", intent_id,
                    {"intent_id": intent_id, "billing_account_id": str(intent[0]),
                     "amount_minor": int(intent[3]), "currency": str(intent[4]),
                     "failure_code": (failure_code or "").strip()},
                    correlation_id=correlation_id, actor_id=actor_id)
    return {"intent_id": intent_id, "status": outcome, "payment_id": payment_id,
            "failure_class": collections.classify_failure(
                (failure_code or "").strip() or None),
            **ledger_result}


def _payer_of(conn: Connection[Any], billing_account_id: str) -> str | None:
    """The person a billing account bills, for the subject on a ledger posting.

    A posting about a member should say so: `led_postings.subject_person_id` is what makes
    "every movement about this person" one predicate rather than a join through three tables.
    """
    row = conn.execute(
        "SELECT payer_person_id FROM plt01.fin_billing_accounts"
        " WHERE billing_account_id = %s",
        (billing_account_id,),
    ).fetchone()
    return str(row[0]) if row and row[0] else None


def _apply_to_invoice(
    conn: Connection[Any], tenant_id: str, invoice_id: str, *, at: date,
) -> str:
    """Recompute an invoice's payment status from what has arrived, and write it.

    **Derived from the money, never asserted by a caller.** The commonest way an invoice comes
    to read `paid` while money is outstanding is a caller passing the status it expected; this
    sums the payments, the refunds and the credit notes and decides.

    **A refund is subtracted from what arrived.** The first version read `fin_payments` and
    ignored `fin_refunds` entirely, so an invoice refunded in full went on reading `paid` --
    the member had their money back and the invoice said it was settled, which is the figure an
    accountant reconciles a bank statement against and the one a dunning sweep decides not to
    chase. MOD-011 found the mirror of this in its margin read, which summed invoices and never
    looked at credit notes.

    A refund in `unknown` state counts as gone, for the same reason `request_refund` treats it
    as spent: the provider has not said, and reading it as money still held is the direction
    that refunds twice.
    """
    row = conn.execute(
        "SELECT gross_minor, due_on, payment_status FROM plt01.fin_invoices"
        " WHERE invoice_id = %s FOR UPDATE",
        (invoice_id,),
    ).fetchone()
    if row is None:
        raise NotFound("invoice_not_found")
    paid = conn.execute(
        "SELECT coalesce(sum(amount_minor), 0) FROM plt01.fin_payments"
        " WHERE invoice_id = %s",
        (invoice_id,),
    ).fetchone()
    refunded = conn.execute(
        "SELECT coalesce(sum(r.amount_minor), 0) FROM plt01.fin_refunds r"
        " JOIN plt01.fin_payments p ON p.payment_id = r.payment_id"
        " WHERE p.invoice_id = %s AND r.status IN ('succeeded', 'unknown')",
        (invoice_id,),
    ).fetchone()
    credited = conn.execute(
        "SELECT coalesce(sum(gross_minor), 0) FROM plt01.fin_invoices"
        " WHERE credits_invoice_id = %s",
        (invoice_id,),
    ).fetchone()
    target = invoicing.payment_status_for(
        gross_minor=int(row[0]),
        paid_minor=((int(paid[0]) if paid else 0)
                    - (int(refunded[0]) if refunded else 0)),
        credited_minor=int(credited[0]) if credited else 0, due_on=row[1], at=at)
    current = str(row[2])
    if target == current:
        return current
    try:
        invoicing.check_payment_transition(current, target)
    except invoicing.InvoicingError:
        # **A move the machine does not have is left alone rather than forced.** An invoice
        # already written off does not silently become `paid` because a stray payment arrived
        # against it; that is a case for a human, and overwriting the write-off would destroy
        # the evidence that one was made.
        return current
    # **`paid_at` moves with the status, both ways.** `fin_invoices_paid_has_a_time` is an
    # equality, so an invoice leaving `paid` has to let go of the timestamp -- and the first
    # version kept it, which made every refund that un-paid an invoice a constraint violation
    # and a 500. Nothing is lost: `fin_payments.received_at` is when the money arrived and this
    # column is a cache of "is it settled now", which is the question the status answers.
    conn.execute(
        "UPDATE plt01.fin_invoices SET payment_status = %s,"
        " paid_at = CASE WHEN %s::text = 'paid' THEN now() ELSE NULL END"
        " WHERE invoice_id = %s AND payment_status = %s",
        (target, target, invoice_id, current))
    return target


def outstanding_minor_on(
    conn: Connection[Any], person_id: str,
) -> int:
    """What this person owes, in minor units, on the caller's connection.

    **It lives here because this module owns the definition.** MOD-022 needs a figure to
    compare a zone's arrears threshold against, and re-deriving it there would be two
    definitions of one balance that can disagree -- MOD-018's `_expected_in_drawer` finding,
    where one function bounded the date and its neighbour did not, and today's till close
    balanced on a journal dated next year.

    The expression is `_apply_to_invoice`'s, read across every invoice on every billing
    account the person pays for: gross, less what arrived, plus what went back out, plus what
    was credited. A refund in `unknown` counts as gone, for `request_refund`'s reason -- the
    provider has not said, and reading it as money still held is the direction that refunds
    twice.

    **`written_off` is excluded and `credited` is not.** A write-off is a decision that the
    money will not arrive, so holding a member out of the building over it would be charging
    them twice for the same forgiveness; a credit note has already reduced the gross through
    `credits_invoice_id`, so excluding it as well would double-count the reduction.
    """
    row = conn.execute(
        """
        SELECT coalesce(sum(
            i.gross_minor
            - coalesce((SELECT sum(p.amount_minor) FROM plt01.fin_payments p
                         WHERE p.invoice_id = i.invoice_id), 0)
            + coalesce((SELECT sum(r.amount_minor) FROM plt01.fin_refunds r
                         JOIN plt01.fin_payments p2 ON p2.payment_id = r.payment_id
                        WHERE p2.invoice_id = i.invoice_id
                          AND r.status IN ('succeeded', 'unknown')), 0)
            - coalesce((SELECT sum(c.gross_minor) FROM plt01.fin_invoices c
                         WHERE c.credits_invoice_id = i.invoice_id), 0)
        ), 0)
        FROM plt01.fin_invoices i
        JOIN plt01.fin_billing_accounts a
          ON a.billing_account_id = i.billing_account_id AND a.tenant_id = i.tenant_id
        WHERE a.payer_person_id = %s AND i.document_kind = 'invoice'
          AND i.payment_status IN ('unpaid', 'part_paid', 'overdue')
        """,
        (person_id,)).fetchone()
    return max(0, int(row[0])) if row else 0


# ------------------------------------------------------------------ refunds and recovery

def request_refund(
    pool: Pool, tenant_id: str, *, payment_id: str, amount_minor: int, reason: str,
    requester_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Ask for a refund. The requester is the caller's own session, never a field.

    **The first of two acts**, because paragraph 1598 requires an approval and a separation of
    duties collapsed into one insert is unverifiable in principle -- MOD-016 shipped that and
    all three of its reviewers approved their own override by typing a uuid. The approval
    compares two identities the server derived, and this is where the first one comes from.

    **The amount is bounded by what was actually paid, less what has already been refunded** --
    a refund exceeding the payment is money leaving that never arrived. The check here is an
    early courtesy so a caller is told immediately; **the binding one is in `approve_refund`**,
    under a lock, because that is the act that commits the money.

    The first version locked the payment with `SELECT ... FOR UPDATE`, which PostgreSQL refuses
    outright: `FOR UPDATE` requires the UPDATE privilege and `fin_payments` deliberately has no
    UPDATE grant at all. So the lock could never have run -- it answered
    `permission denied for table fin_payments` on every call -- and the row it tried to lock is
    not the one that needed locking anyway. Found by this module's own tests.
    """
    if not reason.strip():
        raise InvalidRequest("a_refund_request_states_a_reason")
    with tenant_scope(pool, tenant_id) as conn:
        payment = conn.execute(
            "SELECT amount_minor, currency FROM plt01.fin_payments"
            " WHERE payment_id = %s",
            (payment_id,),
        ).fetchone()
        if payment is None:
            raise NotFound("payment_not_found")
        already = conn.execute(
            "SELECT coalesce(sum(amount_minor), 0) FROM plt01.fin_refunds"
            " WHERE payment_id = %s AND status IN ('pending', 'succeeded', 'unknown')",
            (payment_id,),
        ).fetchone()
        refundable = int(payment[0]) - (int(already[0]) if already else 0)
        if amount_minor > refundable:
            raise Conflict(
                f"{refundable} of this payment is refundable and {amount_minor} was asked")
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.fin_refund_requests
                    (tenant_id, payment_id, amount_minor, currency, reason, requested_by,
                     correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING request_id
                """,
                (tenant_id, payment_id, amount_minor, str(payment[1]), reason,
                 requester_id, correlation_id),
            ).fetchone()
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
    return {"request_id": str(row[0]), "payment_id": payment_id,
            "amount_minor": amount_minor, "currency": str(payment[1]),
            "refundable_minor": refundable, "requested_by": requester_id}


def approve_refund(
    pool: Pool, tenant_id: str, *, request_id: str, approval_reason: str,
    idempotency_key: str, approver_id: str, correlation_id: str,
    acknowledged_amount_minor: int | None = None,
) -> dict[str, Any]:
    """RefundPayment: decide a recorded request. Paragraph 1598's approval.

    Every figure comes from the request row, and `requested_by` with it, so the schema's
    `approved_by <> requested_by` compares two identities the server derived. Nothing is taken
    from the body except the approver's own reason.

    The refund is created `pending`: there is no provider in this build, so it is settled by
    whatever eventually does the sending. A refund recorded as `succeeded` with nothing having
    sent money would be the fabricated-evidence shape this codebase has been bitten by five
    times.

    **The refundable total is re-checked here, under a lock on the billing account.** Two
    separate requests, each for most of one payment, could both be approved otherwise -- one
    decision per *request* is a unique index and says nothing about two requests. The lock is
    on the account rather than on the payment because `fin_payments` has no UPDATE grant and so
    cannot be locked `FOR UPDATE` at all; the account is the narrowest row that can be, and
    serialising approvals per account is the right granularity anyway.

    **`acknowledged_amount_minor` is the approver saying which figure they are approving.** The
    separation of duties establishes that two people were involved and says nothing about what
    the second one read: a request amended -- which it cannot be here, the table has no UPDATE
    grant -- or simply misread leaves an approval of a figure nobody looked at. The same shape
    as the cancellation fee a member acknowledges, and MOD-016's approval that had to match the
    list price it was measured against. Optional, because a staff approval through an interface
    that showed the request is already looking at it.

    **A retried approval gets the decision it already made.** The first version let the insert
    hit the one-decision-per-request index and answered 409, so a client whose request timed
    out after the commit was told the approval had failed and a second approver was asked for.
    """
    if not approval_reason.strip():
        raise InvalidRequest("an_approval_states_a_reason")
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    with tenant_scope(pool, tenant_id) as conn:
        asked = conn.execute(
            "SELECT r.payment_id, r.amount_minor, r.currency, r.requested_by,"
            " p.billing_account_id, p.amount_minor FROM plt01.fin_refund_requests r"
            " JOIN plt01.fin_payments p ON p.payment_id = r.payment_id"
            " WHERE r.request_id = %s",
            (request_id,),
        ).fetchone()
        if asked is None:
            raise NotFound("refund_request_not_found")
        if (acknowledged_amount_minor is not None
                and acknowledged_amount_minor != int(asked[1])):
            raise Conflict(
                f"this request is for {asked[1]} and the approval says "
                f"{acknowledged_amount_minor}")
        decided = conn.execute(
            "SELECT refund_id, status, amount_minor, currency, approved_by, requested_by"
            " FROM plt01.fin_refunds WHERE request_id = %s",
            (request_id,),
        ).fetchone()
        if decided is not None:
            return {"refund_id": str(decided[0]), "request_id": request_id,
                    "status": str(decided[1]), "amount_minor": int(decided[2]),
                    "currency": str(decided[3]), "approved_by": str(decided[4]),
                    "requested_by": str(decided[5]), "repeated": True}
        conn.execute(
            "SELECT 1 FROM plt01.fin_billing_accounts WHERE billing_account_id = %s"
            " FOR UPDATE",
            (str(asked[4]),))
        # **`unknown` counts as spent.** The first version summed only `pending` and
        # `succeeded`, and `unknown` means the provider did not answer -- so a refund that may
        # well have left was treated as money still held, and the same amount was approved a
        # second time. Settling the first as succeeded afterwards leaves the member refunded
        # twice, which is the one direction in this module that cannot be corrected by a
        # later row. A refund that is genuinely lost is reconciled to `failed`, which frees
        # the amount back.
        already = conn.execute(
            "SELECT coalesce(sum(amount_minor), 0) FROM plt01.fin_refunds"
            " WHERE payment_id = %s AND status IN ('pending', 'succeeded', 'unknown')",
            (str(asked[0]),),
        ).fetchone()
        refundable = int(asked[5]) - (int(already[0]) if already else 0)
        if int(asked[1]) > refundable:
            raise Conflict(
                f"{refundable} of this payment is refundable and {asked[1]} was approved")
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.fin_refunds
                    (tenant_id, request_id, payment_id, billing_account_id, amount_minor,
                     currency, approved_by, requested_by, approval_reason,
                     idempotency_key, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING refund_id
                """,
                (tenant_id, request_id, str(asked[0]), str(asked[4]), int(asked[1]),
                 str(asked[2]), approver_id, str(asked[3]), approval_reason,
                 idempotency_key.strip(), correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_request_has_already_been_decided") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        refund_id = str(row[0])
        _append(conn, tenant_id, "refund.approved", "refund", refund_id,
                {"refund_id": refund_id, "payment_id": str(asked[0]),
                 "amount_minor": int(asked[1]), "currency": str(asked[2])},
                correlation_id=correlation_id, actor_id=approver_id)
    return {"refund_id": refund_id, "request_id": request_id, "status": "pending",
            "amount_minor": int(asked[1]), "currency": str(asked[2]),
            "approved_by": approver_id, "requested_by": str(asked[3]),
            "repeated": False}


def settle_refund(
    pool: Pool, tenant_id: str, refund_id: str, *, outcome: str, actor_id: str,
    correlation_id: str, provider_ref: str | None = None,
    failure_code: str | None = None, at: datetime | None = None,
) -> dict[str, Any]:
    """What the provider says became of a refund. COM-03-R06.

    `unknown` is a real outcome here too, and for the same reason: a refund recorded as failed
    that actually left is money gone with the member still owed it.

    **A succeeded refund is applied to the invoice the payment settled.** It was not, so an
    invoice refunded in full went on reading `paid`; `_apply_to_invoice` now subtracts refunds
    and this is where it is called from.

    **A settlement that repeats itself is the idempotent answer, and one that contradicts an
    earlier one is refused.** A provider callback is delivered more than once and the
    redeliveries do not arrive in order, so `succeeded` twice has to be free while `failed`
    after `succeeded` has to be a conflict rather than a silent overwrite of which way the
    money went.
    """
    moment = at or _now()
    if outcome not in ("succeeded", "failed", "unknown"):
        raise InvalidRequest("a_refund_settles_as_succeeded_failed_or_unknown")
    if outcome == "failed" and not (failure_code or "").strip():
        raise InvalidRequest("a_failure_carries_a_code")
    with tenant_scope(pool, tenant_id) as conn:
        current = conn.execute(
            "SELECT status, payment_id, amount_minor, currency FROM plt01.fin_refunds"
            " WHERE refund_id = %s FOR UPDATE",
            (refund_id,),
        ).fetchone()
        if current is None:
            raise NotFound("refund_not_found")
        was = str(current[0])
        if was == outcome:
            return {"refund_id": refund_id, "status": was, "repeated": True}
        if was in ("succeeded", "failed"):
            raise Conflict(f"this_refund_is_already_{was}")
        if outcome == "unknown":
            conn.execute(
                "UPDATE plt01.fin_refunds SET status = 'unknown'"
                " WHERE refund_id = %s AND status = 'pending'",
                (refund_id,))
            return {"refund_id": refund_id, "status": "unknown", "repeated": False,
                    "reason": "the provider did not answer; nothing is settled"}
        settled = conn.execute(
            "UPDATE plt01.fin_refunds SET status = %s, settled_at = %s,"
            " provider_ref = coalesce(%s, provider_ref), failure_code = %s"
            " WHERE refund_id = %s AND status IN ('pending', 'unknown')",
            (outcome, moment, provider_ref, (failure_code or "").strip() or None,
             refund_id),
        ).rowcount
        if settled == 0:
            raise Conflict("this_refund_was_settled_by_somebody_else")
        invoiced = conn.execute(
            "SELECT invoice_id FROM plt01.fin_payments WHERE payment_id = %s",
            (str(current[1]),),
        ).fetchone()
        if invoiced is not None and invoiced[0] is not None:
            _apply_to_invoice(conn, tenant_id, str(invoiced[0]), at=moment.date())
        if outcome == "succeeded":
            # **And MOD-018 posts the money going back, in this transaction.** A refund
            # recorded without its reversal leaves the clearing account holding money that
            # has left, which is the figure the settlement import reconciles.
            account = conn.execute(
                "SELECT b.legal_entity_id, b.billing_account_id"
                " FROM plt01.fin_refunds r"
                " JOIN plt01.fin_billing_accounts b"
                "   ON b.billing_account_id = r.billing_account_id"
                " WHERE r.refund_id = %s",
                (refund_id,),
            ).fetchone()
            if account is not None:
                ledger.post_refund(
                    conn, tenant_id, refund_id=refund_id,
                    legal_entity_id=str(account[0]), amount_minor=int(current[2]),
                    currency=str(current[3]), refunded_on=moment.date(),
                    actor_id=actor_id, correlation_id=correlation_id,
                    subject_person_id=_payer_of(conn, str(account[1])))
            _append(conn, tenant_id, "refund.completed", "refund", refund_id,
                    {"refund_id": refund_id, "payment_id": str(current[1]),
                     "amount_minor": int(current[2]), "currency": str(current[3])},
                    correlation_id=correlation_id, actor_id=actor_id)
    return {"refund_id": refund_id, "status": outcome, "repeated": False}


def start_dunning(
    pool: Pool, tenant_id: str, *, invoice_id: str, idempotency_key: str,
    actor_id: str, correlation_id: str, at: date | None = None,
) -> dict[str, Any]:
    """StartDunning. COM-03-R04.

    **An unpaid invoice, checked here rather than assumed.** Opening a case against a paid
    invoice is a member dunned for money they have already sent, which is the complaint that
    reaches a regulator rather than a support queue.

    **The access recommendation is recorded and not applied.** Paragraph 1496: billing state
    and access state are related and never conflated. Suspending a membership is a lifecycle
    change with its own decision, its own permission and its own history entry.
    """
    today = at or _today()
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    with tenant_scope(pool, tenant_id) as conn:
        invoice = conn.execute(
            "SELECT billing_account_id, payment_status, due_on FROM plt01.fin_invoices"
            " WHERE invoice_id = %s FOR UPDATE",
            (invoice_id,),
        ).fetchone()
        if invoice is None:
            raise NotFound("invoice_not_found")
        if str(invoice[1]) not in ("unpaid", "part_paid", "overdue"):
            raise Conflict(f"this_invoice_is_{invoice[1]}_and_needs_no_dunning")
        terms = conn.execute(
            "SELECT payment_terms_days FROM plt01.fin_billing_accounts"
            " WHERE billing_account_id = %s",
            (str(invoice[0]),),
        ).fetchone()
        assert terms is not None
        step = collections.opening_step(due_on=invoice[2], grace_days=int(terms[0]))
        row = conn.execute(
            """
            INSERT INTO plt01.fin_dunning_cases
                (tenant_id, billing_account_id, invoice_id, stage, opened_on,
                 next_action_on, access_recommendation, idempotency_key, opened_by,
                 correlation_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
            RETURNING case_id
            """,
            (tenant_id, str(invoice[0]), invoice_id, step.stage, today, step.due_on,
             step.access_recommendation, idempotency_key.strip(), actor_id,
             correlation_id),
        ).fetchone() if not _case_already_open(conn, invoice_id) else None
        # **Two unique indexes on one insert, and `ON CONFLICT` can name only one.** The
        # clause above handles the idempotency key; `fin_dunning_cases_one_open` is a separate
        # partial index, so a second case opened under a *different* key raised an uncaught
        # `UniqueViolation` and the caller got a 500. That is MOD-012's "an in-flight lock
        # applies to every writer of that status", one layer up -- there, `start_run` caught
        # the violation and its two siblings did not.
        if row is None and _case_already_open(conn, invoice_id):
            raise Conflict("this_invoice_already_has_an_open_dunning_case")
        if row is None:
            prior = conn.execute(
                "SELECT case_id, invoice_id, stage, next_action_on, access_recommendation"
                " FROM plt01.fin_dunning_cases WHERE idempotency_key = %s",
                (idempotency_key.strip(),),
            ).fetchone()
            assert prior is not None
            if str(prior[1]) != invoice_id:
                raise Conflict("this_idempotency_key_belongs_to_another_invoice")
            return {"case_id": str(prior[0]), "invoice_id": invoice_id,
                    "stage": int(prior[2]),
                    "next_action_on": (
                        prior[3].isoformat() if prior[3] else None),
                    "access_recommendation": str(prior[4]), "repeated": True}
        case_id = str(row[0])
        _append(conn, tenant_id, "dunning.started", "dunning_case", case_id,
                {"case_id": case_id, "invoice_id": invoice_id,
                 "billing_account_id": str(invoice[0]), "stage": step.stage},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"case_id": case_id, "invoice_id": invoice_id, "stage": step.stage,
            "next_action_on": step.due_on.isoformat(),
            "notification_key": step.notification_key,
            "access_recommendation": step.access_recommendation, "repeated": False}


def _case_already_open(conn: Connection[Any], invoice_id: str) -> bool:
    """Whether this invoice already has a live recovery journey.

    Checked before the insert as well as being enforced by `fin_dunning_cases_one_open`,
    because the index can only be reported as a conflict and the caller deserves to be told
    which conflict it was.
    """
    row = conn.execute(
        "SELECT 1 FROM plt01.fin_dunning_cases WHERE invoice_id = %s"
        " AND status IN ('open', 'paused')",
        (invoice_id,),
    ).fetchone()
    return row is not None


def advance_dunning(
    pool: Pool, tenant_id: str, case_id: str, *, actor_id: str, correlation_id: str,
    notification_ref: str | None = None, at: date | None = None,
) -> dict[str, Any]:
    """Move a dunning case to its next stage, or close it when the journey is over.

    **The invoice is re-read, and a case whose invoice has been paid closes as recovered.** A
    control consulted once is a control with a window -- MOD-009's rule, and this window is
    days long: the ordinary thing that happens between two dunning stages is that the member
    pays. Advancing without re-reading is a final notice sent to somebody who settled on
    Tuesday.
    """
    today = at or _today()
    with tenant_scope(pool, tenant_id) as conn:
        case = conn.execute(
            "SELECT invoice_id, billing_account_id, stage, status, next_action_on"
            " FROM plt01.fin_dunning_cases WHERE case_id = %s FOR UPDATE",
            (case_id,),
        ).fetchone()
        if case is None:
            raise NotFound("dunning_case_not_found")
        if str(case[3]) != "open":
            raise Conflict(f"this_dunning_case_is_{case[3]}")
        invoice = conn.execute(
            "SELECT payment_status, due_on FROM plt01.fin_invoices WHERE invoice_id = %s",
            (str(case[0]),),
        ).fetchone()
        assert invoice is not None
        if str(invoice[0]) in ("paid", "credited", "written_off"):
            conn.execute(
                "UPDATE plt01.fin_dunning_cases SET status = 'recovered',"
                " next_action_on = NULL, closed_at = now(), closed_by = %s,"
                " resolution = %s WHERE case_id = %s AND status = 'open'",
                (actor_id, f"the invoice is {invoice[0]}", case_id))
            return {"case_id": case_id, "status": "recovered",
                    "reason": f"the invoice is {invoice[0]}"}
        terms = conn.execute(
            "SELECT payment_terms_days FROM plt01.fin_billing_accounts"
            " WHERE billing_account_id = %s",
            (str(case[1]),),
        ).fetchone()
        assert terms is not None
        step = collections.next_step(
            current_stage=int(case[2]), due_on=invoice[1], grace_days=int(terms[0]))
        if step is None:
            conn.execute(
                "UPDATE plt01.fin_dunning_cases SET status = 'abandoned',"
                " next_action_on = NULL, closed_at = now(), closed_by = %s,"
                " resolution = %s WHERE case_id = %s AND status = 'open'",
                (actor_id, "the journey reached its final stage unpaid", case_id))
            return {"case_id": case_id, "status": "abandoned",
                    "reason": "the journey reached its final stage unpaid"}
        moved = conn.execute(
            "UPDATE plt01.fin_dunning_cases SET stage = %s, next_action_on = %s,"
            " access_recommendation = %s, attempts = attempts + 1,"
            " last_notification_ref = coalesce(%s, last_notification_ref)"
            " WHERE case_id = %s AND status = 'open' AND stage = %s",
            (step.stage, step.due_on, step.access_recommendation, notification_ref,
             case_id, int(case[2])),
        ).rowcount
        if moved == 0:
            raise Conflict("this_dunning_case_was_advanced_by_somebody_else")
    return {"case_id": case_id, "status": "open", "stage": step.stage,
            "next_action_on": step.due_on.isoformat(),
            "notification_key": step.notification_key,
            "access_recommendation": step.access_recommendation,
            "is_final": step.is_final, "advanced_on": today.isoformat()}


def reconcile_intent(
    pool: Pool, tenant_id: str, intent_id: str, *, provider_status: str | None,
    actor_id: str, correlation_id: str, provider_ref: str | None = None,
) -> dict[str, Any]:
    """COM-03-R06's payment-status reconciliation, for one intent.

    **A provider answer that contradicts a settled record is reported, not applied.** Only the
    provider knows what it did; only a human should decide what to do when the two records
    disagree about money, and overwriting a `succeeded` payment with `failed` would destroy the
    evidence of the disagreement along with the member's credit.

    **And it cannot settle an intent nobody ever attempted.** `collections.reconcile` is the
    decision function and it answers correctly for every pair, but the *settlement* was
    reachable for a `pending` intent -- so a caller could create a payment for a charge no
    provider had ever been asked about, naming the outcome itself and the `provider_ref` with
    it. That is `finance.payment.take` bought with a different permission.

    `attempts` is incremented only by `settle_payment_intent`, which always moves the status,
    so an intent is either `pending` with nothing attempted or `unknown` with an attempt whose
    answer went missing -- and the second is what a reconciliation is for. Marking a pending
    intent `unknown` is still allowed, because that is how one becomes reconcilable and it
    creates nothing; what is refused is settling one terminally.
    """
    with tenant_scope(pool, tenant_id) as conn:
        intent = conn.execute(
            "SELECT status FROM plt01.fin_payment_intents WHERE intent_id = %s FOR UPDATE",
            (intent_id,),
        ).fetchone()
        if intent is None:
            raise NotFound("payment_intent_not_found")
        recorded = str(intent[0])
        try:
            verdict, reason = collections.reconcile(
                recorded_status=str(intent[0]), provider_status=provider_status)
        except collections.CollectionsError as e:
            raise InvalidRequest(str(e)) from None
        if reason == "provider_disagrees_escalate":
            return {"intent_id": intent_id, "status": str(intent[0]),
                    "reason_code": reason, "provider_status": provider_status,
                    "escalated": True}
        if verdict == recorded:
            return {"intent_id": intent_id, "status": verdict, "reason_code": reason,
                    "escalated": False}
        if recorded == "pending" and verdict != "unknown":
            raise Conflict(
                "this_intent_was_never_attempted_so_there_is_nothing_to_settle")
    # **Settled outside the block that read it**, through the ordinary command, so there is one
    # place that writes a payment and one place that enforces one payment per intent.
    settled = settle_payment_intent(
        pool, tenant_id, intent_id, outcome=verdict, actor_id=actor_id,
        correlation_id=correlation_id, provider_ref=provider_ref,
        failure_code="reconciled_as_failed" if verdict == "failed" else None,
        failure_detail="settled by reconciliation against the provider"
        if verdict == "failed" else None)
    return {"intent_id": intent_id, "status": verdict, "reason_code": reason,
            "payment_id": settled.get("payment_id"), "escalated": False}


def fiscalize_invoice(
    pool: Pool, tenant_id: str, invoice_id: str, *, target: str, actor_id: str,
    correlation_id: str, ack_ref: str | None = None,
    exemption_reason: str | None = None, at: datetime | None = None,
) -> dict[str, Any]:
    """FiscalizeInvoice: move the *fiscal* state, which is not the payment state.

    Paragraph 1607, as a command. **`fiscal_complete` requires the authority's
    acknowledgement**, which is the Jordan rule the paragraph names and the general shape
    besides: a server-allocated serial means the document is numbered, and numbering is not
    filing. The serial is allocated at issue and every invoice has one, so the serial alone
    could never be the test.

    Nothing here speaks to a tax authority. The transition is recorded with the reference the
    authority gave, and an invoice that reads `fiscal_complete` with nothing behind it is
    refused by a constraint rather than by this function alone.

    **Who moved the state is recorded, and the move is published.** The first version took an
    `actor_id` and a `correlation_id` and wrote neither, and published nothing -- so the act
    that declares a document filed with a tax authority, or declares it outside the regime
    altogether, had no name on it. The catalogue's own reason for a separate permission here is
    that "the person who issues invoices is not necessarily the person who files them", and
    the only name on the row was the issuer's.

    **`not_required` states why.** It is terminal, needs no acknowledgement and sidesteps the
    one control this table is proud of, so it is the transition that most needs a reason -- and
    `fin_invoices_exemption_reasoned` is what makes that true of rows written by anything else.
    """
    moment = at or _now()
    with tenant_scope(pool, tenant_id) as conn:
        invoice = conn.execute(
            "SELECT fiscal_status, legal_entity_id, document_number"
            " FROM plt01.fin_invoices WHERE invoice_id = %s FOR UPDATE",
            (invoice_id,),
        ).fetchone()
        if invoice is None:
            raise NotFound("invoice_not_found")
        current = str(invoice[0])
        if current == target:
            return {"invoice_id": invoice_id, "fiscal_status": current,
                    "previous_fiscal_status": current, "acknowledged": False,
                    "repeated": True}
        try:
            invoicing.check_fiscal_transition(current, target)
        except invoicing.InvoicingError as e:
            raise Conflict(str(e)) from None
        if target == "fiscal_complete" and not (ack_ref or "").strip():
            raise Conflict("fiscal_completion_needs_the_authority_acknowledgement")
        if target == "not_required" and not (exemption_reason or "").strip():
            raise InvalidRequest("declaring_a_document_outside_the_regime_states_why")
        try:
            # The `::text` casts are load-bearing: an untyped NULL parameter inside a `CASE`
            # leaves PostgreSQL unable to infer the type and it answers
            # `could not determine data type of parameter` -- a 500 on the ordinary path where
            # no acknowledgement is being recorded. Found by this module's own tests.
            moved = conn.execute(
                "UPDATE plt01.fin_invoices SET fiscal_status = %s,"
                " fiscal_ack_ref = coalesce(%s::text, fiscal_ack_ref),"
                " fiscal_acked_at = CASE WHEN %s::text IS NOT NULL THEN %s::timestamptz"
                " ELSE fiscal_acked_at END,"
                " fiscalized_by = %s, fiscalized_at = %s, fiscalize_correlation_id = %s,"
                " fiscal_exemption_reason = %s"
                " WHERE invoice_id = %s AND fiscal_status = %s",
                (target, (ack_ref or "").strip() or None, (ack_ref or "").strip() or None,
                 moment, actor_id, moment, correlation_id,
                 (exemption_reason or "").strip() or None, invoice_id, current),
            ).rowcount
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        if moved == 0:
            raise Conflict("this_invoice_was_fiscalized_by_somebody_else")
        _append(conn, tenant_id, "invoice.fiscalized", "invoice", invoice_id,
                {"invoice_id": invoice_id, "legal_entity_id": str(invoice[1]),
                 "document_number": str(invoice[2]), "fiscal_status": target},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"invoice_id": invoice_id, "fiscal_status": target,
            "previous_fiscal_status": current,
            "acknowledged": bool((ack_ref or "").strip()), "repeated": False}


def refunds_of_payment(
    pool: Pool, tenant_id: str, payment_id: str,
) -> dict[str, Any]:
    """Every refund request and decision against one payment, with what is still refundable.

    **There was no way to read a refund at all.** The module had four commands that write one
    and nothing that returns one, so the approver could not see the request they were
    approving, the requester could not see what became of it, and `refundable_minor` -- the
    figure both `request_refund` and `approve_refund` refuse against -- was computable only by
    being refused. An approval that cannot be preceded by a read is a separation of duties the
    second person performs blind.
    """
    with tenant_scope(pool, tenant_id) as conn:
        payment = conn.execute(
            "SELECT amount_minor, currency, invoice_id, received_at"
            " FROM plt01.fin_payments WHERE payment_id = %s",
            (payment_id,),
        ).fetchone()
        if payment is None:
            raise NotFound("payment_not_found")
        requests = conn.execute(
            "SELECT request_id, amount_minor, currency, requested_by, requested_at,"
            " reason FROM plt01.fin_refund_requests WHERE payment_id = %s"
            " ORDER BY requested_at",
            (payment_id,),
        ).fetchall()
        decisions = conn.execute(
            "SELECT refund_id, request_id, amount_minor, currency, status, approved_by,"
            " requested_by, approved_at, settled_at, failure_code,"
            " credit_note_invoice_id FROM plt01.fin_refunds WHERE payment_id = %s"
            " ORDER BY approved_at",
            (payment_id,),
        ).fetchall()
    spent = sum(int(d[2]) for d in decisions
                if str(d[4]) in ("pending", "succeeded", "unknown"))
    return {
        "payment_id": payment_id, "amount_minor": int(payment[0]),
        "currency": str(payment[1]),
        "invoice_id": str(payment[2]) if payment[2] else None,
        "received_at": payment[3].isoformat(),
        "refundable_minor": int(payment[0]) - spent,
        "requests": [
            {"request_id": str(r[0]), "amount_minor": int(r[1]),
             "currency": str(r[2]), "requested_by": str(r[3]),
             "requested_at": r[4].isoformat(), "reason": str(r[5])}
            for r in requests],
        "refunds": [
            {"refund_id": str(d[0]), "request_id": str(d[1]),
             "amount_minor": int(d[2]), "currency": str(d[3]), "status": str(d[4]),
             "approved_by": str(d[5]), "requested_by": str(d[6]),
             "approved_at": d[7].isoformat(),
             "settled_at": d[8].isoformat() if d[8] else None,
             "failure_code": str(d[9]) if d[9] else None,
             "credit_note_invoice_id": str(d[10]) if d[10] else None}
            for d in decisions],
    }


# ------------------------------------------------------------------ the scheme's dispute
#
# **COM-03-R06's chargeback, and the table this module shipped with no writer at all.**
# `plt01.fin_disputes` has existed since MOD-017's migration -- forced RLS, twelve
# constraints, an isolation check, four privacy declarations -- and nothing in `app/` read or
# wrote it. The module's registry entry lists disputes among what works. Found by building
# ADM-PAY-03, whose disputed state is an evidence-deadline banner: a state no screen can
# reach is the vacuous branch this codebase has now shipped eight times, and the remedy is
# the writer rather than a caveat on the page.
#
# **One permission, because none of this is a Veyro decision.** The refund is split in two
# because somebody chooses to send money back and paragraph 1598 wants a second person on
# that choice. Every transition here records what another party did -- the scheme opened it,
# the tenant sent evidence, the scheme decided -- so a separation of duties would be a
# ceremony over somebody else's judgement. What the rows carry instead is attribution, by
# constraint, because `veyro_cp_app` holds nothing in `iam` and MOD-008 audits denials rather
# than allowed acts: the row is the only record there can be.
#
# **No event is published, and that is deliberate.** COM-03's event list has no dispute
# event, and inventing one is inventing product -- MOD-012's precedent for a standalone
# revocation, which publishes nothing for the same reason.


def record_dispute(
    pool: Pool, tenant_id: str, *, payment_id: str, provider_case_ref: str,
    dispute_kind: str, reason_code: str, amount_minor: int, currency: str,
    opened_on: date, respond_due_on: date, actor_id: str, correlation_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """The scheme has told us money is being taken back. COM-03-R06.

    **Recorded, not performed.** There is no provider here, so this is a named actor's
    statement that a scheme opened a case at a time -- MOD-012's `validated` install state
    and MOD-014's contact verification, in the one place where being wrong costs the member's
    money. The scheme's own case reference is required and unique per tenant, because that
    reference is how the two sides identify the same dispute and a second row for one case
    would double the tenant's apparent exposure.

    **Three things are derived from the payment rather than accepted.** The billing account,
    so a dispute cannot name another payer's; the ceiling, because a scheme disputes at most
    what was charged and a larger figure is a data error that would overstate what is at
    risk; and the currency, which must match -- MOD-016 shipped an approval that compared
    minor-unit counts across currencies and a reviewer authorised a JOD reduction in USD.

    **A deadline before the opening is refused by the schema**, and the window is returned so
    a caller never has to subtract two dates to find out how long it has.
    """
    if not provider_case_ref.strip():
        raise InvalidRequest("a_dispute_needs_the_schemes_case_reference")
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    if dispute_kind not in ("chargeback", "inquiry", "pre_arbitration"):
        raise InvalidRequest("bad_dispute_kind")
    if amount_minor <= 0 or amount_minor > 10**12:
        raise InvalidRequest("bad_amount")
    try:
        window = collections.evidence_window(
            opened_on=opened_on, respond_due_on=respond_due_on, at=_today())
    except collections.DisputeError as error:
        raise InvalidRequest(str(error)) from error

    with tenant_scope(pool, tenant_id) as conn:
        payment = conn.execute(
            "SELECT billing_account_id, amount_minor, currency, invoice_id"
            " FROM plt01.fin_payments WHERE payment_id = %s",
            (payment_id,),
        ).fetchone()
        if payment is None:
            raise NotFound("payment_not_found")
        if str(payment[2]) != currency:
            raise Conflict("a_dispute_is_in_the_currency_of_the_payment")
        if amount_minor > int(payment[1]):
            raise Conflict("a_dispute_cannot_exceed_the_payment_it_is_against")
        row = conn.execute(
            """
            INSERT INTO plt01.fin_disputes
                (tenant_id, payment_id, billing_account_id, provider_case_ref,
                 dispute_kind, reason_code, amount_minor, currency, opened_on,
                 respond_due_on, idempotency_key, recorded_by, correlation_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
            RETURNING dispute_id
            """,
            (tenant_id, payment_id, str(payment[0]), provider_case_ref.strip(),
             dispute_kind, reason_code, amount_minor, currency, opened_on,
             respond_due_on, idempotency_key.strip(), actor_id, correlation_id),
        ).fetchone()
        if row is None:
            # **Answered from what was recorded, and compared on more than one field.** An
            # idempotency key compared on the aggregate alone is this repository's
            # most-repeated defect -- five modules -- and here the aggregate is the payment,
            # so a retry naming a different case reference would be handed the first case
            # back. Both are compared.
            prior = conn.execute(
                "SELECT dispute_id, payment_id, provider_case_ref, amount_minor, status,"
                " respond_due_on, opened_on FROM plt01.fin_disputes"
                " WHERE idempotency_key = %s",
                (idempotency_key.strip(),),
            ).fetchone()
            assert prior is not None
            if (str(prior[1]) != payment_id
                    or str(prior[2]) != provider_case_ref.strip()
                    or int(prior[3]) != amount_minor):
                raise Conflict("this_idempotency_key_belongs_to_another_dispute")
            return {
                "dispute_id": str(prior[0]), "payment_id": payment_id,
                "status": str(prior[4]), "repeated": True,
                **collections.evidence_window(
                    opened_on=prior[6], respond_due_on=prior[5], at=_today()),
            }
        dispute_id = str(row[0])
    return {
        "dispute_id": dispute_id, "payment_id": payment_id,
        "invoice_id": str(payment[3]) if payment[3] else None,
        "billing_account_id": str(payment[0]), "status": "open",
        "amount_minor": amount_minor, "currency": currency,
        "respond_due_on": respond_due_on.isoformat(), "repeated": False, **window,
    }


def respond_to_dispute(
    pool: Pool, tenant_id: str, dispute_id: str, *, response_ref: str, actor_id: str,
    correlation_id: str, at: datetime | None = None,
) -> dict[str, Any]:
    """Evidence has been sent to the scheme. COM-03-R06.

    **A locator, not the evidence.** `fin_disputes_response_not_blank` takes any non-blank
    text and the column is declared `write_once` in the privacy registry, so what goes in it
    is a reference to wherever the provider portal keeps the submission -- a free-text field
    on an un-erasable row is where a member's medical note ends up, which is MOD-017's
    `evidence_ref` finding one table over.

    **A response after the deadline is recorded rather than refused**, and the window comes
    back saying so. The scheme will reject it, but "we answered on the 20th and the deadline
    was the 15th" is precisely the fact a later argument turns on, and a command that refused
    would leave the tenant with no record of having tried. What would be wrong is letting it
    read as timely, which `window_has_closed` prevents.
    """
    moment = at or _now()
    if not response_ref.strip():
        raise InvalidRequest("a_response_needs_a_locator")
    with tenant_scope(pool, tenant_id) as conn:
        current = conn.execute(
            "SELECT status, opened_on, respond_due_on FROM plt01.fin_disputes"
            " WHERE dispute_id = %s FOR UPDATE",
            (dispute_id,),
        ).fetchone()
        if current is None:
            raise NotFound("dispute_not_found")
        try:
            collections.check_dispute_transition(str(current[0]), "responded")
        except collections.DisputeError as error:
            raise Conflict(str(error)) from error
        conn.execute(
            "UPDATE plt01.fin_disputes SET status = 'responded', response_ref = %s,"
            " responded_at = %s, responded_by = %s WHERE dispute_id = %s"
            " AND status = %s",
            (response_ref.strip(), moment, actor_id, dispute_id, str(current[0])),
        )
        window = collections.evidence_window(
            opened_on=current[1], respond_due_on=current[2], at=moment.date())
    return {
        "dispute_id": dispute_id, "status": "responded",
        "responded_at": moment.isoformat(), "correlation_id": correlation_id, **window,
    }


def settle_dispute(
    pool: Pool, tenant_id: str, dispute_id: str, *, outcome: str, actor_id: str,
    correlation_id: str, at: datetime | None = None,
) -> dict[str, Any]:
    """The scheme has decided. COM-03-R06.

    **`lost` is money gone and this module does not move it.** A lost chargeback is a
    reversal the provider performs on its own settlement, so what belongs here is the record;
    the money appears in MOD-018's settlement import as a chargeback line, which opens a
    reconciliation case because it reverses a payment nothing here can resolve to one row.
    Posting a guess from this side would be two definitions of the same reversal.

    **A dispute may be settled without a response.** A scheme can withdraw an inquiry, or
    decide against a tenant that missed the deadline, and a machine that required `responded`
    first would make a missed deadline unrecordable -- which is the one outcome a tenant most
    needs on the record.
    """
    moment = at or _now()
    if outcome not in collections.DISPUTE_OUTCOMES:
        raise InvalidRequest("bad_outcome")
    with tenant_scope(pool, tenant_id) as conn:
        current = conn.execute(
            "SELECT status, amount_minor, currency, payment_id FROM plt01.fin_disputes"
            " WHERE dispute_id = %s FOR UPDATE",
            (dispute_id,),
        ).fetchone()
        if current is None:
            raise NotFound("dispute_not_found")
        if str(current[0]) == outcome:
            # Idempotent to the caller: a client whose request timed out after the commit is
            # told what happened rather than 409 for work that succeeded. MOD-017's own
            # blocking review finding, three commands over.
            return {"dispute_id": dispute_id, "status": outcome, "repeated": True,
                    "amount_minor": int(current[1]), "currency": str(current[2])}
        try:
            collections.check_dispute_transition(str(current[0]), outcome)
        except collections.DisputeError as error:
            raise Conflict(str(error)) from error
        conn.execute(
            "UPDATE plt01.fin_disputes SET status = %s, outcome = %s, closed_at = %s"
            " WHERE dispute_id = %s AND status = %s",
            (outcome, outcome, moment, dispute_id, str(current[0])),
        )
    return {
        "dispute_id": dispute_id, "status": outcome, "outcome": outcome,
        "amount_minor": int(current[1]), "currency": str(current[2]),
        "payment_id": str(current[3]), "closed_at": moment.isoformat(),
        "correlation_id": correlation_id, "repeated": False,
    }


def get_invoice(pool: Pool, tenant_id: str, invoice_id: str) -> dict[str, Any]:
    """One invoice with its lines, both statuses and what has been paid against it.

    **Four things this read did not answer that its own list route did, or that ADM-PAY-03
    needs.** The detail read returning less about an invoice's identity than the row that
    linked to it is the asymmetry worth naming: `list_invoices` has returned
    `payer_person_id` and `credits_invoice_id` from the start.

    - **`payer_person_id`**, so a surface can ask MOD-014 for the member's name through
      MOD-014's own gate. No name, address or birth date crosses this boundary -- that rule
      is unchanged -- and an identifier is what MOD-018's journal read already returns.
    - **`fiscal_ack_ref`**, because the design's paid state is "JoFotara reference shown" and
      a boolean cannot be shown. The reference is the authority's own and is about the
      document, not the person.
    - **`credit_notes`**, with each one's id and number. `credited_minor` is a sum, and the
      design is explicit that a correction is "a credit note with its own number and a link
      to the original" -- a sum cannot be linked, so the screen could state the reduction and
      not where it came from.
    - **`days_late`**, from `invoicing.days_late`, because the header states it and a client
      deriving it from a date and its own clock answers differently in another timezone.
    """
    today = _now().date()
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT i.billing_account_id, i.document_number, i.document_kind, i.net_minor,"
            " i.tax_minor, i.gross_minor, i.currency, i.issued_on, i.due_on,"
            " i.payment_status, i.paid_at, i.fiscal_status, i.fiscal_ack_ref, i.serial,"
            " b.payer_person_id, i.credits_invoice_id, i.fiscal_acked_at,"
            " i.fiscal_exemption_reason"
            " FROM plt01.fin_invoices i"
            " JOIN plt01.fin_billing_accounts b"
            "   ON b.billing_account_id = i.billing_account_id"
            " WHERE i.invoice_id = %s",
            (invoice_id,),
        ).fetchone()
        if row is None:
            raise NotFound("invoice_not_found")
        lines = conn.execute(
            "SELECT line_number, description, quantity, unit_net_minor, net_minor,"
            " tax_rate_bp, tax_minor, gross_minor FROM plt01.fin_invoice_lines"
            " WHERE invoice_id = %s ORDER BY line_number",
            (invoice_id,),
        ).fetchall()
        paid = conn.execute(
            "SELECT coalesce(sum(amount_minor), 0) FROM plt01.fin_payments"
            " WHERE invoice_id = %s",
            (invoice_id,),
        ).fetchone()
        refunded = conn.execute(
            "SELECT coalesce(sum(r.amount_minor), 0) FROM plt01.fin_refunds r"
            " JOIN plt01.fin_payments p ON p.payment_id = r.payment_id"
            " WHERE p.invoice_id = %s AND r.status IN ('succeeded', 'unknown')",
            (invoice_id,),
        ).fetchone()
        credit_notes = conn.execute(
            "SELECT invoice_id, document_number, gross_minor, currency, issued_on"
            " FROM plt01.fin_invoices WHERE credits_invoice_id = %s"
            " ORDER BY issued_on, serial",
            (invoice_id,),
        ).fetchall()
    return {
        "invoice_id": invoice_id, "billing_account_id": str(row[0]),
        "payer_person_id": str(row[14]),
        "credits_invoice_id": str(row[15]) if row[15] else None,
        "refunded_minor": int(refunded[0]) if refunded else 0,
        "credited_minor": sum(int(note[2]) for note in credit_notes),
        "credit_notes": [
            {"invoice_id": str(note[0]), "document_number": str(note[1]),
             "gross_minor": int(note[2]), "currency": str(note[3]),
             "issued_on": note[4].isoformat()}
            for note in credit_notes],
        "document_number": str(row[1]), "document_kind": str(row[2]),
        "serial": int(row[13]),
        "days_late": invoicing.days_late(
            due_on=row[8], at=today, payment_status=str(row[9])),
        "net_minor": int(row[3]), "tax_minor": int(row[4]), "gross_minor": int(row[5]),
        "currency": str(row[6]), "issued_on": row[7].isoformat(),
        "due_on": row[8].isoformat(),
        "payment_status": str(row[9]),
        "paid_at": row[10].isoformat() if row[10] else None,
        "fiscal_status": str(row[11]), "fiscal_acknowledged": row[12] is not None,
        # **The three things the design's JoFotara block renders**, each a column that
        # already existed: "Sent to JoFotara · reference JF-88214" needs the reference,
        # "quiet confirmation on the invoice with the timestamp" needs the instant, and
        # `not_required` is the one fiscal state whose whole meaning is its reason --
        # `fin_invoices_exemption_reasoned` makes the reason and the state the same fact, so
        # returning the state without it hands a reader a claim with no basis.
        "fiscal_ack_ref": str(row[12]) if row[12] else None,
        "fiscal_acked_at": row[16].isoformat() if row[16] else None,
        "fiscal_exemption_reason": str(row[17]) if row[17] else None,
        "paid_minor": int(paid[0]) if paid else 0,
        "lines": [
            {"line_number": int(line[0]), "description": str(line[1]),
             "quantity": int(line[2]), "unit_net_minor": int(line[3]),
             "net_minor": int(line[4]), "tax_rate_bp": int(line[5]),
             "tax_minor": int(line[6]), "gross_minor": int(line[7])}
            for line in lines],
    }


# ------------------------------------------------------------------ reads
#
# **MOD-017 had no listing route of any kind.** Every read in the module above takes an id the
# caller already has to know, so a membership, an agreement, a grant, a billing account and an
# invoice were each reachable only by having just written one. That is the "a writer with no
# reader" shape `GET /brands` had in MOD-004 -- a module whose state cannot be observed is a
# module whose state nobody can check -- and the remedy is the same: a route, rather than a
# client that infers the ids from somewhere else.
#
# Three rules hold for everything in this section.
#
# **Nothing here returns a name, an address, a birth date or anything else about a person.**
# MOD-014 owns those columns and applies `Decision.mask` to them on the way out, filtered by
# the caller's assurance. A membership list carrying the member's legal name beside the id
# would be a lateral read path around `people.person.read` -- MOD-010's `events.event.read`
# finding in this module's clothes, where one routine permission returned another module's
# restricted fields. A surface that wants both calls both modules, each through its own gate.
#
# **Every list is bounded and ordered.** Unbounded is a bulk export and a denial of service at
# once, so `limit` is checked against a ceiling rather than passed through; unordered makes the
# query planner the author, which is MOD-018's `chart_for` finding, and here it would also make
# pagination meaningless. The order is newest first on a stable column with the primary key as
# the tiebreak, because two memberships created in one transaction share `created_at`.
#
# **A filter value outside its domain refuses rather than returning nothing.** `status=actve`
# and "this member has no active membership" are different answers, and a list that renders
# both as an empty table is a surface that cannot be trusted. This is the same judgement as
# MOD-016's `Eligibility.blocks_redemption`: a value nobody thought about must refuse.

#: The most rows any list in this module will return. A page is what a person reads; a figure
#: larger than this is a report, and a report is a different kind of read with a different
#: permission behind it.
LIST_LIMIT = 200

MEMBERSHIP_STATUSES = frozenset({
    "pending", "active", "frozen", "grace", "suspended", "cancelled", "expired",
    "transferred"})
GRANT_STATUSES = frozenset({"active", "exhausted", "expired", "revoked"})
INVOICE_PAYMENT_STATUSES = frozenset({
    "unpaid", "part_paid", "paid", "overdue", "written_off", "credited"})
#: `fin_invoices_fiscal_status`'s own six values. Separate from the payment statuses above
#: because the two move independently -- an invoice can be paid and unfiled, or filed and
#: unpaid -- and one vocabulary for both would invite the conflation the migration forbids.
INVOICE_FISCAL_STATUSES = frozenset({
    "pending", "submitted", "acknowledged", "fiscal_complete", "rejected", "not_required"})
#: `fin_dunning_cases_status`'s own five values, so a filter cannot ask for a status the
#: column refuses and get an empty list back as though nobody were in that state.
DUNNING_STATUSES = frozenset({"open", "paused", "recovered", "written_off", "abandoned"})


def _bounded(limit: int) -> int:
    if limit < 1 or limit > LIST_LIMIT:
        raise InvalidRequest("bad_limit")
    return limit


def _one_of(value: str | None, allowed: frozenset[str], error: str) -> str | None:
    if value is not None and value not in allowed:
        raise InvalidRequest(error)
    return value


def list_memberships(
    pool: Pool, tenant_id: str, *, person_id: str | None = None,
    status: str | None = None, limit: int = 50,
) -> dict[str, Any]:
    """The memberships in this tenant, newest first, optionally one person's.

    `status` is the **cached** status, which answers "now". A dispute about what was true on a
    past date is `membership_as_of`, which replays the history instead -- and the two disagree
    on purpose for a future-dated cancellation, because nothing in this build applies one when
    its notice runs out.
    """
    limit = _bounded(limit)
    _one_of(status, MEMBERSHIP_STATUSES, "bad_status")
    where = ["true"]
    params: list[Any] = []
    if person_id is not None:
        where.append("m.person_id = %s")
        params.append(person_id)
    if status is not None:
        where.append("m.status = %s")
        params.append(status)
    # **The walk is seeded by the same predicate**, so listing one person's memberships walks
    # one person's chains rather than every chain in the tenant. The filters are on `m.`
    # columns the seed has, so the predicate is reused rather than written twice; its
    # parameters go first because the CTE is first in the statement.
    seed = list(params)
    params.append(limit)
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            f"WITH RECURSIVE {_walk_from(' AND '.join(where))}"
            " SELECT m.membership_id, m.person_id, m.membership_number, m.status,"
            " m.starts_on, m.ends_on, m.current_period_start, m.current_period_end,"
            " m.status_effective_on, l.agreement_id, a.amount_minor, a.currency,"
            " a.minimum_term_ends_on, t.membership_kind, t.billing_period, t.is_off_peak,"
            " m.agreement_id, l.depth"
            " FROM plt01.mem_memberships m"
            # **The agreement is the chain's live end, not `m.agreement_id`.** The obvious
            # join is on the root, which after an upgrade carries the amount, currency and
            # term of the contract the member has moved off -- the figures on this row.
            " JOIN live l ON l.membership_id = m.membership_id"
            " JOIN plt01.mem_agreements a ON a.agreement_id = l.agreement_id"
            " JOIN plt01.mem_membership_terms t"
            "   ON t.membership_terms_id = a.membership_terms_id"
            f" WHERE {' AND '.join(where)}"
            " ORDER BY m.created_at DESC, m.membership_id DESC LIMIT %s",
            tuple(seed + params),
        ).fetchall()
    _refuse_a_truncated_chain(rows, 17)
    return {
        "memberships": [
            {"membership_id": str(r[0]), "person_id": str(r[1]),
             "membership_number": str(r[2]), "status": str(r[3]),
             "starts_on": r[4].isoformat(), "ends_on": r[5].isoformat() if r[5] else None,
             "current_period_start": r[6].isoformat() if r[6] else None,
             "current_period_end": r[7].isoformat() if r[7] else None,
             "status_effective_on": r[8].isoformat(), "agreement_id": str(r[9]),
             # **The root as well, named as what it is.** `agreement_id` is what governs this
             # membership today, which is what the figures beside it are from; the root is
             # the immutable link `mem_memberships` carries and is what answers "what did
             # they originally sign". Returning only the root beside the current agreement's
             # amount would be a row whose id does not explain its own numbers.
             "original_agreement_id": str(r[16]),
             "amount_minor": int(r[10]), "currency": str(r[11]),
             "minimum_term_ends_on": r[12].isoformat() if r[12] else None,
             "membership_kind": str(r[13]), "billing_period": str(r[14]),
             "is_off_peak": bool(r[15])}
            for r in rows],
        "count": len(rows), "limit": limit,
        "truncated": len(rows) == limit,
    }


def get_membership(pool: Pool, tenant_id: str, membership_id: str) -> dict[str, Any]:
    """One membership with the agreement it was sold on and the terms that agreement cites.

    The figures come from the agreement rather than from the product, because an agreement
    snapshots what was actually sold: re-reading today's price would answer a different
    question from the one a member's contract answers.
    """
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            f"WITH RECURSIVE {_walk_from('m.membership_id = %s')}"
            " SELECT m.person_id, m.membership_number, m.status, m.starts_on, m.ends_on,"
            " m.current_period_start, m.current_period_end, m.status_effective_on,"
            " m.version, a.agreement_id, a.amount_minor, a.currency, a.starts_on,"
            " a.ends_on, a.minimum_term_ends_on, a.status, a.signed_at, a.signature_kind,"
            " a.price_resolution_id, a.contract_version_id, t.membership_terms_id,"
            " t.contract_key, t.membership_kind, t.billing_period, t.installment_count,"
            " t.prepaid_days, t.is_off_peak, t.product_id, m.agreement_id, l.depth"
            " FROM plt01.mem_memberships m"
            # The chain's live end, not its root -- every `a.` column below is a figure the
            # member is held to and after an upgrade the root carries the one they left.
            " JOIN live l ON l.membership_id = m.membership_id"
            " JOIN plt01.mem_agreements a ON a.agreement_id = l.agreement_id"
            " JOIN plt01.mem_membership_terms t"
            "   ON t.membership_terms_id = a.membership_terms_id"
            " WHERE m.membership_id = %s",
            (membership_id, membership_id),
        ).fetchone()
        if row is None:
            raise NotFound("membership_not_found")
        _refuse_a_truncated_chain([row], 29)
        changes = conn.execute(
            "SELECT change_kind, from_status, to_status, effective_on, decided_at, reason"
            " FROM plt01.mem_lifecycle_changes WHERE membership_id = %s"
            " ORDER BY effective_on DESC, decided_at DESC",
            (membership_id,),
        ).fetchall()
    return {
        "membership_id": membership_id, "person_id": str(row[0]),
        "membership_number": str(row[1]), "status": str(row[2]),
        "starts_on": row[3].isoformat(), "ends_on": row[4].isoformat() if row[4] else None,
        "current_period_start": row[5].isoformat() if row[5] else None,
        "current_period_end": row[6].isoformat() if row[6] else None,
        "status_effective_on": row[7].isoformat(), "version": int(row[8]),
        "agreement": {
            # **The agreement that governs today, with the root named beside it.** This block
            # is resolved through the supersession chain, so after an upgrade every figure in
            # it is the live contract's; `original_agreement_id` is the immutable link
            # `mem_memberships` carries and is what answers "what did they first sign".
            "agreement_id": str(row[9]),
            "original_agreement_id": str(row[28]),
            "supersedes_an_earlier_agreement": int(row[29]) > 0,
            "amount_minor": int(row[10]),
            "currency": str(row[11]), "starts_on": row[12].isoformat(),
            "ends_on": row[13].isoformat() if row[13] else None,
            "minimum_term_ends_on": row[14].isoformat() if row[14] else None,
            "status": str(row[15]),
            "signed_at": row[16].isoformat() if row[16] else None,
            "signature_kind": str(row[17]) if row[17] else None,
            "price_resolution_id": str(row[18]) if row[18] else None,
            "contract_version_id": str(row[19]),
        },
        "terms": {
            "membership_terms_id": str(row[20]), "contract_key": str(row[21]),
            "membership_kind": str(row[22]), "billing_period": str(row[23]),
            "installment_count": int(row[24]) if row[24] is not None else None,
            "prepaid_days": int(row[25]) if row[25] is not None else None,
            "is_off_peak": bool(row[26]), "product_id": str(row[27]),
        },
        # The same masking `membership_as_of` applies, for the same reason and to the same
        # kinds: a medical hold's reason is a health fact whatever column it is in, and it is
        # unreadable at every assurance level this build can reach.
        "history": [
            {"change_kind": str(c[0]), "from_status": str(c[1]), "to_status": str(c[2]),
             "effective_on": c[3].isoformat(), "decided_at": c[4].isoformat(),
             "reason": _reason_or_mask(str(c[0]), str(c[5])),
             "reason_withheld": str(c[0]) in HEALTH_REASON_KINDS}
            for c in changes],
    }


def list_entitlement_grants(
    pool: Pool, tenant_id: str, *, person_id: str | None = None,
    membership_id: str | None = None, status: str | None = None, limit: int = 50,
) -> dict[str, Any]:
    """What a member may use, with the remaining balance summed from the ledger.

    **The balance here is read, not settled.** `entitlement_balance` sweeps lapsed holds first
    and therefore writes, which is why it takes an actor; a list that swept would write one
    ledger row per expired hold per page view. So a held quantity on this list can be stale in
    the member's favour -- it may include holds that have since lapsed -- and the number that
    settles a draw is the one `reserve_entitlement` computes under the grant's own lock.
    """
    limit = _bounded(limit)
    _one_of(status, GRANT_STATUSES, "bad_status")
    where = ["true"]
    params: list[Any] = []
    if person_id is not None:
        where.append("g.person_id = %s")
        params.append(person_id)
    if membership_id is not None:
        where.append("g.membership_id = %s")
        params.append(membership_id)
    if status is not None:
        where.append("g.status = %s")
        params.append(status)
    params.append(limit)
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT g.grant_id, g.person_id, g.membership_id, g.is_counted,"
            " g.granted_quantity, g.valid_from, g.valid_to, g.status, g.source_kind,"
            " g.brand_id, g.location_id, g.usable_from_minute, g.usable_to_minute,"
            " p.policy_key, p.display_name, p.entitlement_type"
            " FROM plt01.mem_entitlement_grants g"
            " JOIN plt01.mem_entitlement_policies p ON p.policy_id = g.policy_id"
            f" WHERE {' AND '.join(where)}"
            " ORDER BY g.created_at DESC, g.grant_id DESC LIMIT %s",
            tuple(params),
        ).fetchall()
        # **The arithmetic is `entitlements.balance_of`, not a `sum()` in the SQL.** Both are
        # addition today, which is exactly why writing the second one is tempting and why it
        # is wrong: a balance with two definitions has two answers the day either moves, and
        # this module's own invoice list says so one function down. The movements come back
        # raw and the domain function adds them, so a grant's balance here and a grant's
        # balance under the draw lock are the same expression.
        ids = [str(r[0]) for r in rows]
        moved: dict[str, list[entitlements.Movement]] = {i: [] for i in ids}
        holds: dict[str, list[int]] = {i: [] for i in ids}
        if ids:
            for m in conn.execute(
                "SELECT grant_id, movement_kind, delta"
                " FROM plt01.mem_entitlement_ledger WHERE grant_id = ANY(%s)",
                (ids,),
            ).fetchall():
                moved[str(m[0])].append(entitlements.Movement(str(m[1]), int(m[2])))
            for h in conn.execute(
                "SELECT grant_id, quantity FROM plt01.mem_entitlement_reservations"
                " WHERE grant_id = ANY(%s) AND status = 'held'",
                (ids,),
            ).fetchall():
                holds[str(h[0])].append(int(h[1]))
    return {
        "grants": [
            {"grant_id": str(r[0]), "person_id": str(r[1]),
             "membership_id": str(r[2]) if r[2] else None,
             "is_counted": bool(r[3]),
             "granted_quantity": int(r[4]) if r[4] is not None else None,
             "valid_from": r[5].isoformat(),
             "valid_to": r[6].isoformat() if r[6] else None,
             "status": str(r[7]), "source_kind": str(r[8]),
             "brand_id": str(r[9]) if r[9] else None,
             "location_id": str(r[10]) if r[10] else None,
             "usable_from_minute": int(r[11]) if r[11] is not None else None,
             "usable_to_minute": int(r[12]) if r[12] is not None else None,
             "policy_key": str(r[13]), "display_name": str(r[14]),
             "entitlement_type": str(r[15]),
             "balance": (entitlements.balance_of(moved[str(r[0])])
                         if r[3] else None),
             "held": (entitlements.held_quantity(holds[str(r[0])])
                      if r[3] else None)}
            for r in rows],
        "count": len(rows), "limit": limit, "truncated": len(rows) == limit,
        "balance_is_unswept": True,
    }


def list_billing_accounts(
    pool: Pool, tenant_id: str, *, person_id: str | None = None, limit: int = 50,
) -> dict[str, Any]:
    """The billing accounts in this tenant, optionally those one person pays for.

    `payer_person_id` is who pays, which is not always who trains: COM-03-R01's household and
    corporate accounts are exactly the case where the two differ, so this filter answers "what
    does this person pay for" and not "who is billed for this member".
    """
    limit = _bounded(limit)
    where = ["true"]
    params: list[Any] = []
    if person_id is not None:
        where.append("payer_person_id = %s")
        params.append(person_id)
    params.append(limit)
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT billing_account_id, payer_person_id, account_kind, account_number,"
            " currency, legal_entity_id, status, payment_terms_days, closed_at"
            " FROM plt01.fin_billing_accounts"
            f" WHERE {' AND '.join(where)}"
            " ORDER BY created_at DESC, billing_account_id DESC LIMIT %s",
            tuple(params),
        ).fetchall()
    return {
        "accounts": [
            {"billing_account_id": str(r[0]), "payer_person_id": str(r[1]),
             "account_kind": str(r[2]), "account_number": str(r[3]),
             "currency": str(r[4]), "legal_entity_id": str(r[5]), "status": str(r[6]),
             "payment_terms_days": int(r[7]),
             "closed_at": r[8].isoformat() if r[8] else None}
            for r in rows],
        "count": len(rows), "limit": limit, "truncated": len(rows) == limit,
    }


def invoice_history(pool: Pool, tenant_id: str, invoice_id: str) -> dict[str, Any]:
    """What has happened to one invoice, in order -- ADM-PAY-03's own middle section.

    > 17 Aug 06:00  Issued and charged automatically
    > 17 Aug 06:01  Declined · card expired · Visa ···4417
    > 18 Aug 06:00  Retry 1 declined · same reason
    > 19 Aug 06:12  Retry 2 declined · dunning stopped, 2 of 2 used

    **Composed from three insert-only tables, never from a status field.** The invoice's own
    status is a cache of what these rows add up to; a timeline built from it would say what is
    true now and nothing about how it got there, which is the opposite of what the screen is
    for. The design's immutability note is the reason this can be trusted as an audit trail:
    "Issued invoices are never edited. Corrections are credit notes with their own number and
    a link to the original."

    Four kinds of entry, each from the table that owns it: the issue itself, every payment
    intent and its outcome (including the `unknown` one, which is a provider that did not
    answer and is not the same as a failure), every payment actually recorded, and the dunning
    case with the attempts it has spent. A refund is a payment's own event and carries the
    payment it reverses.
    """
    with tenant_scope(pool, tenant_id) as conn:
        invoice = conn.execute(
            "SELECT document_number, issued_on, gross_minor, currency, billing_account_id"
            " FROM plt01.fin_invoices WHERE invoice_id = %s",
            (invoice_id,),
        ).fetchone()
        if invoice is None:
            raise NotFound("invoice_not_found")
        intents = conn.execute(
            "SELECT intent_id, status, amount_minor, currency, created_at, settled_at,"
            " failure_code, method FROM plt01.fin_payment_intents"
            " WHERE invoice_id = %s ORDER BY created_at",
            (invoice_id,),
        ).fetchall()
        payments = conn.execute(
            "SELECT payment_id, amount_minor, currency, method, received_at, provider_ref"
            " FROM plt01.fin_payments WHERE invoice_id = %s ORDER BY received_at",
            (invoice_id,),
        ).fetchall()
        refunds = conn.execute(
            "SELECT r.refund_id, r.amount_minor, r.currency, r.status, r.approved_at,"
            " r.settled_at, r.approval_reason FROM plt01.fin_refunds r"
            " JOIN plt01.fin_payments p ON p.payment_id = r.payment_id"
            " WHERE p.invoice_id = %s ORDER BY r.approved_at",
            (invoice_id,),
        ).fetchall()
        dunning = conn.execute(
            "SELECT case_id, stage, status, opened_on, next_action_on, attempts,"
            " access_recommendation, closed_at, resolution FROM plt01.fin_dunning_cases"
            " WHERE invoice_id = %s ORDER BY opened_on",
            (invoice_id,),
        ).fetchall()
        # **The dispute, which this read did not include and the screen cannot do without.**
        # ADM-PAY-03's disputed state is "evidence deadline banner", and `respond_due_on` is
        # a real date set by the card scheme -- the one deadline in this module that is
        # somebody else's and cannot be extended. A dispute is recorded against the *payment*
        # rather than the invoice, so it reaches an invoice through the payment it reverses,
        # which is also why a timeline built from the invoice's own status could never show
        # one: `payment_status` stays `paid` throughout a chargeback.
        disputes = conn.execute(
            "SELECT d.dispute_id, d.dispute_kind, d.reason_code, d.amount_minor,"
            " d.currency, d.opened_on, d.respond_due_on, d.status, d.responded_at,"
            " d.closed_at, d.provider_case_ref FROM plt01.fin_disputes d"
            " JOIN plt01.fin_payments p ON p.payment_id = d.payment_id"
            " WHERE p.invoice_id = %s ORDER BY d.opened_on",
            (invoice_id,),
        ).fetchall()

    events: list[dict[str, Any]] = [{
        "kind": "issued",
        "at": invoice[1].isoformat(),
        "amount_minor": int(invoice[2]),
        "currency": str(invoice[3]),
        "detail": str(invoice[0]),
    }]
    for row in intents:
        events.append({
            "kind": "payment_intent",
            "at": (row[5] or row[4]).isoformat(),
            "status": str(row[1]),
            "amount_minor": int(row[2]),
            "currency": str(row[3]),
            "method": str(row[7]),
            # **`unknown` is not a failure.** The provider did not answer, which means money
            # may well have left; MOD-017 treats it as outstanding for refunding purposes and
            # a timeline that called it "declined" would be stating the opposite.
            "detail": str(row[6]) if row[6] else None,
        })
    for row in payments:
        events.append({
            "kind": "payment",
            "at": row[4].isoformat(),
            "amount_minor": int(row[1]),
            "currency": str(row[2]),
            "method": str(row[3]),
            "detail": str(row[5]) if row[5] else None,
        })
    for row in refunds:
        events.append({
            "kind": "refund",
            # Settled if the provider answered, approved if not: a refund in flight belongs
            # on the timeline at the moment somebody approved it, not at a time that does not
            # exist yet.
            "at": (row[5] or row[4]).isoformat(),
            "status": str(row[3]),
            "amount_minor": int(row[1]),
            "currency": str(row[2]),
            "detail": str(row[6]),
        })
    for row in dunning:
        events.append({
            "kind": "dunning",
            "at": (row[7] or row[3]).isoformat(),
            "status": str(row[2]),
            "stage": int(row[1]),
            "attempts": int(row[5]),
            "access_recommendation": str(row[6]),
            "next_action_on": row[4].isoformat() if row[4] else None,
            "detail": str(row[8]) if row[8] else None,
        })

    for row in disputes:
        events.append({
            "kind": "dispute",
            # Opened, responded or closed -- whichever is the latest thing that happened to
            # it, because a dispute is one row that moves rather than a row per step.
            "at": (row[9] or row[8] or row[5]).isoformat(),
            "status": str(row[7]),
            "dispute_kind": str(row[1]),
            "reason_code": str(row[2]),
            "amount_minor": int(row[3]),
            "currency": str(row[4]),
            "opened_on": row[5].isoformat(),
            "respond_due_on": row[6].isoformat(),
            "detail": str(row[10]),
        })

    events.sort(key=lambda event: event["at"])
    #: The scheme's deadline on the dispute still waiting for a response, if there is one.
    #: Lifted out of the events because a banner is about one deadline and a reader scanning
    #: a timeline for the earliest open dispute is deriving the thing the server already
    #: knows -- MOD-016's `in_window` judgement.
    awaiting = [
        event for event in events
        if event["kind"] == "dispute" and event["status"] in ("open", "responded")]
    return {
        "invoice_id": invoice_id,
        "document_number": str(invoice[0]),
        "events": events,
        "evidence_due_on": (
            min(str(event["respond_due_on"]) for event in awaiting) if awaiting else None),
        #: ADM-PAY-03's own note, which is a product fact rather than a surface's caption.
        "immutable_because":
            "An issued invoice is never edited: the five ledger tables are insert-only for "
            "both runtime roles, so a correction is a credit note with its own number and a "
            "link to the original. That is what makes this timeline an audit trail.",
    }


def list_invoices(
    pool: Pool, tenant_id: str, *, billing_account_id: str | None = None,
    person_id: str | None = None, payment_status: str | None = None,
    fiscal_status: str | None = None, limit: int = 50,
) -> dict[str, Any]:
    """Issued documents, newest first, with what has been paid against each.

    **`payment_status` is the stored figure, not one recomputed here.** `_apply_to_invoice`
    maintains it inside the transaction of every payment, credit note and refund, which is
    what makes it the answer rather than a cache: a list that re-derived it would be a second
    definition of the same balance, and MOD-018's till close shipped exactly that pair and
    disagreed with itself.

    There is no draft state in this module, so every row here is a document that was issued
    and numbered. A correction is a credit note, which appears as its own row with
    `document_kind = 'credit_note'` and a `credits_invoice_id`.
    """
    limit = _bounded(limit)
    _one_of(payment_status, INVOICE_PAYMENT_STATUSES, "bad_payment_status")
    # **The two statuses move independently and neither implies the other**, which the
    # migration states at length: an invoice can be paid and unfiled, or filed and unpaid. So
    # the filters are separate, and a caller asking for a rejected filing is not asking about
    # money. ADM-CC-01's COMPLIANCE item is exactly this read.
    _one_of(fiscal_status, INVOICE_FISCAL_STATUSES, "bad_fiscal_status")
    where = ["true"]
    params: list[Any] = []
    if billing_account_id is not None:
        where.append("i.billing_account_id = %s")
        params.append(billing_account_id)
    if person_id is not None:
        where.append("b.payer_person_id = %s")
        params.append(person_id)
    if payment_status is not None:
        where.append("i.payment_status = %s")
        params.append(payment_status)
    if fiscal_status is not None:
        where.append("i.fiscal_status = %s")
        params.append(fiscal_status)
    params.append(limit)
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT i.invoice_id, i.billing_account_id, b.payer_person_id,"
            " i.document_number, i.document_kind, i.net_minor, i.tax_minor, i.gross_minor,"
            " i.currency, i.issued_on, i.due_on, i.payment_status, i.fiscal_status,"
            " i.credits_invoice_id,"
            " coalesce((SELECT sum(p.amount_minor) FROM plt01.fin_payments p"
            "            WHERE p.invoice_id = i.invoice_id), 0)"
            " FROM plt01.fin_invoices i"
            " JOIN plt01.fin_billing_accounts b"
            "   ON b.billing_account_id = i.billing_account_id"
            f" WHERE {' AND '.join(where)}"
            " ORDER BY i.issued_on DESC, i.serial DESC, i.invoice_id DESC LIMIT %s",
            tuple(params),
        ).fetchall()
    return {
        "invoices": [
            {"invoice_id": str(r[0]), "billing_account_id": str(r[1]),
             "payer_person_id": str(r[2]), "document_number": str(r[3]),
             "document_kind": str(r[4]), "net_minor": int(r[5]), "tax_minor": int(r[6]),
             "gross_minor": int(r[7]), "currency": str(r[8]),
             "issued_on": r[9].isoformat(), "due_on": r[10].isoformat(),
             "payment_status": str(r[11]), "fiscal_status": str(r[12]),
             "credits_invoice_id": str(r[13]) if r[13] else None,
             "paid_minor": int(r[14])}
            for r in rows],
        "count": len(rows), "limit": limit, "truncated": len(rows) == limit,
    }


# ---------------------------------------------------------------- ADM-CC-01's four figures
#
# **These are aggregates, and that is why they are reads of their own rather than arithmetic
# in a surface.** `list_invoices` and `list_memberships` are bounded at 200 rows, so a client
# that summed one would report the first page as the month -- and a balance with two
# definitions has two answers the day either moves, which is the finding MOD-018's till close
# shipped and `list_entitlement_grants` records one function up.
#
# The Command Center's own metric row is four figures. Three are below; the fourth, lead
# conversion over thirty days, has no module in this build and is named as absent on the
# screen rather than approximated from something else.


def collections_summary(
    pool: Pool, tenant_id: str, *, as_of: date | None = None, weeks: int = 12,
    week_start: int = reporting.SATURDAY,
) -> dict[str, Any]:
    """What was collected this month, against the same point last month, per currency.

    ADM-CC-01's first metric and its twelve-week chart. Four things about the shape:

    **Per currency, never summed across.** `money.py`'s first convention is that an amount is
    an integer count of minor units in one currency, and a tenant may bill in several. One
    total over two currencies is the comparison MOD-016's discount approval made and a
    reviewer found: an approval reasoned in JOD authorised the same minor-unit count in USD.
    So the response is a list and the screen renders a metric cell per currency, which
    degenerates to the design's single cell for a single-currency tenant.

    **A payment, not an invoice.** "Collected" is money received, which is `fin_payments`;
    `fin_invoices.gross_minor` is money *owed*. MOD-011's `gross_margin` read invoices and was
    blind to credit notes for the same confusion one module over.

    **Refunds are subtracted and said to be.** A month that took 1,000 and refunded 400
    collected 600, and a figure that ignored the refund would overstate in the direction
    nobody checks -- which is MOD-011's finding again, with the sign reversed.

    **By legal entity, which is not the design's "by location".** ADM-CC-01's second chart
    breaks the month down by club -- Abdoun, Khalda, Sweifieh. The dimension on the money
    chain here is `fin_billing_accounts.legal_entity_id`, and a legal entity is not a location:
    MOD-004's hierarchy puts brands and locations *under* one, so three clubs under a single
    entity are one row. Relabelling it would be a confident wrong answer on a revenue chart,
    so it is returned as what it is and the response says the design asked for something else.
    """
    as_of = as_of or _today()
    if weeks < 1 or weeks > reporting.MAX_WEEKS:
        raise InvalidRequest("bad_weeks")
    if week_start < 0 or week_start > 6:
        raise InvalidRequest("bad_week_start")
    this = reporting.month_to_date(as_of)
    before = reporting.comparable_previous_month(as_of)
    buckets = reporting.week_buckets(as_of, weeks, week_start=week_start)
    with tenant_scope(pool, tenant_id) as conn:
        # One statement per span rather than one grouped by span, because the spans overlap:
        # a week bucket can sit inside the month-to-date window, and a row counted twice in a
        # grouped query would need a join nobody can read.
        totals = {
            name: _collected_between(conn, span)
            for name, span in (("this", this), ("previous", before))
        }
        weekly: list[tuple[reporting.Span, bool, dict[str, int]]] = [
            (span, reporting.is_partial(span, as_of), _collected_between(conn, span))
            for span in buckets
        ]
        entities = conn.execute(
            "SELECT b.legal_entity_id, p.currency,"
            " sum(p.amount_minor)"
            " - coalesce((SELECT sum(r.amount_minor) FROM plt01.fin_refunds r"
            "   JOIN plt01.fin_payments rp ON rp.payment_id = r.payment_id"
            "   JOIN plt01.fin_billing_accounts rb"
            "     ON rb.billing_account_id = rp.billing_account_id"
            "   WHERE r.status = 'succeeded' AND rp.currency = p.currency"
            "     AND rb.legal_entity_id = b.legal_entity_id"
            "     AND r.settled_at::date >= %s AND r.settled_at::date <= %s), 0)"
            " FROM plt01.fin_payments p"
            " JOIN plt01.fin_billing_accounts b"
            "   ON b.billing_account_id = p.billing_account_id"
            " WHERE p.received_at::date >= %s AND p.received_at::date <= %s"
            " GROUP BY b.legal_entity_id, p.currency"
            " ORDER BY b.legal_entity_id, p.currency",
            (this.first, this.last, this.first, this.last),
        ).fetchall()
    currencies = sorted({c for totals_by in totals.values() for c in totals_by})
    return {
        "as_of": as_of.isoformat(),
        "month_to_date": {"first": this.first.isoformat(), "last": this.last.isoformat(),
                          "days": this.days},
        "comparable_previous_month": {
            "first": before.first.isoformat(), "last": before.last.isoformat(),
            "days": before.days,
            # The clamp is stated rather than left to be derived from two dates: a 31st
            # compared against a 28th is a shorter span, and a reader has to know.
            "clamped": before.days != this.days},
        "collected": [
            {"currency": currency,
             "collected_minor": totals["this"].get(currency, 0),
             "previous_minor": totals["previous"].get(currency, 0),
             "change_bp": reporting.change_bp(
                 totals["this"].get(currency, 0), totals["previous"].get(currency, 0)),
             # A projection, named as one. Nothing may render this as money collected.
             "pace_minor": reporting.pace(totals["this"].get(currency, 0), as_of),
             "by_week": [
                 {"first": span.first.isoformat(), "last": span.last.isoformat(),
                  "partial": partial, "collected_minor": sums.get(currency, 0)}
                 for span, partial, sums in weekly],
             "by_legal_entity": [
                 {"legal_entity_id": str(r[0]), "collected_minor": int(r[2])}
                 for r in entities if str(r[1]) == currency],
             }
            for currency in currencies],
        "week_start": week_start,
        "pace_is_a_projection":
            "pace_minor is a straight-line projection -- collected, divided by the days "
            "elapsed, times the days in the month. It is not money collected and must not be "
            "rendered as a total. The design states no basis for its own pace figure, so the "
            "method is named here rather than reverse-engineered from one illustration.",
        "partial_weeks_are_not_extrapolated":
            "A bucket containing as_of is marked partial and carries only what it holds.",
        "by_location_is_unavailable":
            "The design breaks this down by club. Money here carries a legal entity, and "
            "MOD-004's hierarchy puts brands and locations under one -- so three clubs under "
            "a single entity are one row. by_legal_entity is what the data supports.",
    }


def _collected_between(conn: Connection, span: reporting.Span) -> dict[str, int]:
    """Payments received in `span` less refunds settled in it, per currency.

    Both halves are bounded at both ends. A one-sided window is MOD-011's `evaluate_budget`
    finding, which reported a January budget 45% consumed as 143%.
    """
    taken = conn.execute(
        "SELECT currency, sum(amount_minor) FROM plt01.fin_payments"
        " WHERE received_at::date >= %s AND received_at::date <= %s GROUP BY currency",
        (span.first, span.last),
    ).fetchall()
    given_back = conn.execute(
        "SELECT p.currency, sum(r.amount_minor) FROM plt01.fin_refunds r"
        " JOIN plt01.fin_payments p ON p.payment_id = r.payment_id"
        " WHERE r.status = 'succeeded'"
        "   AND r.settled_at::date >= %s AND r.settled_at::date <= %s"
        " GROUP BY p.currency",
        (span.first, span.last),
    ).fetchall()
    out = {str(r[0]): int(r[1]) for r in taken}
    for row in given_back:
        out[str(row[0])] = out.get(str(row[0]), 0) - int(row[1])
    return out


def revenue_report(
    pool: Pool, tenant_id: str, *, as_of: date | None = None,
) -> dict[str, Any]:
    """ADM-RPT-02: what was collected, what was invoiced, what is still owed, what went back.

    **Four columns because they are four facts.** The canvas says so in its own words --
    "Collected and invoiced are separate columns because they are separate facts. A report
    showing one number labelled 'revenue' is the reason operators cannot reconcile their own
    books." Collected is money received (`fin_payments` less settled refunds); invoiced is
    money billed (`fin_invoices`, less credit notes, which MOD-017 stores positive and always
    reads as a reduction); outstanding is what those invoices still owe; refunded is what went
    back. A tenant that invoiced 41,592 and collected 41,280 is owed 312, and only a report
    carrying both can say that.

    **By source is COM-02-R01's own vocabulary, not a taxonomy invented here.** The design's
    rows are Memberships, Personal training, Classes and Retail; an invoice line carries a
    `variant_id`, a variant belongs to a product and a product has a `product_type` from a
    closed set of eight. So the split is a join rather than a guess -- which matters, because
    the alternative is classifying free-text descriptions, and a revenue report that sorted
    "PT block of 10" into Retail by a keyword would be a confident wrong answer about money.
    A line with no variant is its own row rather than being dropped or assigned: an invoice
    raised by hand is real revenue and silently losing it would make the sources disagree with
    the total.

    **Outstanding is floored per invoice, not in aggregate.** An overpaid invoice owes nothing;
    summing signed differences would let it cancel out a genuinely unpaid one and report a
    tenant as settled while an invoice goes unchased.

    **Every figure is bounded at both ends and compared against the same point last month.**
    MOD-011's `evaluate_budget` read a one-sided window and reported a January budget 45%
    consumed as 143%, then wrote three insert-only alert rows about it.
    """
    as_of = as_of or _today()
    this = reporting.month_to_date(as_of)
    before = reporting.comparable_previous_month(as_of)
    with tenant_scope(pool, tenant_id) as conn:
        collected = {
            name: _collected_between(conn, span)
            for name, span in (("this", this), ("previous", before))
        }
        invoiced = {name: _invoiced_between(conn, span)
                    for name, span in (("this", this), ("previous", before))}
        refunded = {name: _refunded_between(conn, span)
                    for name, span in (("this", this), ("previous", before))}
        outstanding = _outstanding_for(conn, this)
        sources = {name: _by_source_between(conn, span)
                   for name, span in (("this", this), ("previous", before))}
        entity_sources = _by_source_and_entity(conn, this)
    currencies = sorted(
        {c for group in (collected, invoiced, refunded) for by in group.values() for c in by}
        | set(outstanding)
    )
    types = sorted({t for by in sources.values() for (t, c) in by})

    def source_rows(currency: str) -> list[dict[str, Any]]:
        rows = []
        for product_type in types:
            now = sources["this"].get((product_type, currency), 0)
            then = sources["previous"].get((product_type, currency), 0)
            if now == 0 and then == 0:
                continue
            rows.append({
                "product_type": product_type,
                "net_minor": now,
                "previous_minor": then,
                "change_bp": reporting.change_bp(now, then),
                "by_legal_entity": [
                    {"legal_entity_id": entity, "net_minor": amount}
                    for (t, c, entity), amount in sorted(entity_sources.items())
                    if t == product_type and c == currency],
            })
        return rows

    return {
        "as_of": as_of.isoformat(),
        "month_to_date": {"first": this.first.isoformat(), "last": this.last.isoformat(),
                          "days": this.days},
        "comparable_previous_month": {
            "first": before.first.isoformat(), "last": before.last.isoformat(),
            "days": before.days, "clamped": before.days != this.days},
        "currencies": [
            {
                "currency": currency,
                "collected_minor": collected["this"].get(currency, 0),
                "collected_previous_minor": collected["previous"].get(currency, 0),
                "collected_change_bp": reporting.change_bp(
                    collected["this"].get(currency, 0),
                    collected["previous"].get(currency, 0)),
                "invoiced_minor": invoiced["this"].get(currency, 0),
                "invoiced_previous_minor": invoiced["previous"].get(currency, 0),
                "invoiced_change_bp": reporting.change_bp(
                    invoiced["this"].get(currency, 0), invoiced["previous"].get(currency, 0)),
                # Outstanding is a position, not a flow: it is what the invoices issued in this
                # window still owe *now*, so there is no previous-month figure to compare it
                # against. One would be the balance as it stood a month ago, which is a
                # different question and needs the payments that have landed since.
                "outstanding_minor": outstanding.get(currency, 0),
                "refunded_minor": refunded["this"].get(currency, 0),
                "refunded_previous_minor": refunded["previous"].get(currency, 0),
                # **The figure the sources add up to, stated rather than left to be derived.**
                # `invoiced_minor` is gross and a source row is net, so a reader checking the
                # breakdown against the headline figure finds it short by the tax -- which
                # reads as a breakdown that lost a row. Revenue is net by convention here
                # (MOD-011's `gross_margin` reads invoices net of tax and of the partner
                # share, because tax is collected on somebody else's behalf), so the sources
                # are net and the total they make is returned beside them.
                "invoiced_net_minor": sum(
                    amount for (_, c), amount in sources["this"].items() if c == currency),
                "by_source": source_rows(currency),
            }
            for currency in currencies],
        "outstanding_is_a_position":
            "outstanding_minor is what the invoices issued in this window still owe as of "
            "now, not a figure for the window. It carries no previous-month comparison "
            "because the comparable number is a balance as it stood then, which this read "
            "does not reconstruct.",
        "unattributed_source_is_a_row":
            "An invoice line with no variant cannot be attributed to a product type and is "
            "returned as the `unattributed` source rather than dropped, so the sources sum to "
            "invoiced_net_minor exactly.",
        "sources_are_net":
            "A source row is net of tax, and invoiced_minor is gross. Tax is collected on "
            "somebody else's behalf and is not revenue, so the breakdown is net and "
            "invoiced_net_minor is the figure it adds up to.",
        "by_location_is_unavailable":
            "The design breaks this down by club. Money here carries a legal entity, and "
            "MOD-004's hierarchy puts brands and locations under one -- so three clubs under "
            "a single entity are one row. by_legal_entity is what the data supports.",
    }


def _invoiced_between(conn: Connection, span: reporting.Span) -> dict[str, int]:
    """Invoices issued in `span`, less credit notes issued in it, per currency.

    A credit note is stored positive and always read as a reduction -- MOD-017's rule, and
    MOD-011's `gross_margin` was blind to exactly this and reported a 50% margin on a period
    that earned nothing.
    """
    out: dict[str, int] = {}
    for kind, sign in (("invoice", 1), ("credit_note", -1)):
        rows = conn.execute(
            "SELECT currency, sum(gross_minor) FROM plt01.fin_invoices"
            " WHERE document_kind = %s AND issued_on >= %s AND issued_on <= %s"
            " GROUP BY currency",
            (kind, span.first, span.last),
        ).fetchall()
        for row in rows:
            out[str(row[0])] = out.get(str(row[0]), 0) + sign * int(row[1])
    return out


def _refunded_between(conn: Connection, span: reporting.Span) -> dict[str, int]:
    """Refunds settled in `span`, per currency, as a positive figure."""
    rows = conn.execute(
        "SELECT p.currency, sum(r.amount_minor) FROM plt01.fin_refunds r"
        " JOIN plt01.fin_payments p ON p.payment_id = r.payment_id"
        " WHERE r.status = 'succeeded'"
        "   AND r.settled_at::date >= %s AND r.settled_at::date <= %s"
        " GROUP BY p.currency",
        (span.first, span.last),
    ).fetchall()
    return {str(r[0]): int(r[1]) for r in rows}


def _outstanding_for(conn: Connection, span: reporting.Span) -> dict[str, int]:
    """What the invoices issued in `span` still owe, floored per invoice.

    Floored per invoice because an overpaid one owes nothing: summing signed differences lets
    it cancel a genuinely unpaid invoice and reports the tenant settled while one goes
    unchased.
    """
    rows = conn.execute(
        # **`fin_payments` has no status column**, by design: the table has no UPDATE grant at
        # all, so a row exists only because the money arrived and a payment recorded in error
        # is reversed by a refund rather than edited. Filtering on one would have been a
        # predicate against a column that is not there.
        "SELECT i.currency, greatest("
        "   i.gross_minor"
        "   - coalesce((SELECT sum(p.amount_minor) FROM plt01.fin_payments p"
        "       WHERE p.invoice_id = i.invoice_id), 0)"
        "   + coalesce((SELECT sum(r.amount_minor) FROM plt01.fin_refunds r"
        "       JOIN plt01.fin_payments rp ON rp.payment_id = r.payment_id"
        "       WHERE rp.invoice_id = i.invoice_id AND r.status = 'succeeded'), 0)"
        "   - coalesce((SELECT sum(c.gross_minor) FROM plt01.fin_invoices c"
        "       WHERE c.credits_invoice_id = i.invoice_id"
        "         AND c.document_kind = 'credit_note'), 0)"
        " , 0)"
        " FROM plt01.fin_invoices i"
        " WHERE i.document_kind = 'invoice'"
        "   AND i.issued_on >= %s AND i.issued_on <= %s",
        (span.first, span.last),
    ).fetchall()
    out: dict[str, int] = {}
    for row in rows:
        out[str(row[0])] = out.get(str(row[0]), 0) + int(row[1])
    return out


_SOURCE_SELECT = (
    " FROM plt01.fin_invoice_lines l"
    " JOIN plt01.fin_invoices i ON i.invoice_id = l.invoice_id"
    " LEFT JOIN plt01.cat_variants v ON v.variant_id = l.variant_id"
    " LEFT JOIN plt01.cat_products pr ON pr.product_id = v.product_id"
    " WHERE i.document_kind = 'invoice'"
    "   AND i.issued_on >= %s AND i.issued_on <= %s"
)


def _by_source_between(
    conn: Connection, span: reporting.Span,
) -> dict[tuple[str, str], int]:
    """Net revenue per (product type, currency) for invoices issued in `span`."""
    rows = conn.execute(
        "SELECT coalesce(pr.product_type, 'unattributed'), i.currency, sum(l.net_minor)"
        + _SOURCE_SELECT
        + " GROUP BY 1, 2",
        (span.first, span.last),
    ).fetchall()
    return {(str(r[0]), str(r[1])): int(r[2]) for r in rows}


def _by_source_and_entity(
    conn: Connection, span: reporting.Span,
) -> dict[tuple[str, str, str], int]:
    """The same split, broken down by the billing account's legal entity."""
    rows = conn.execute(
        "SELECT coalesce(pr.product_type, 'unattributed'), i.currency,"
        " b.legal_entity_id, sum(l.net_minor)"
        " FROM plt01.fin_invoice_lines l"
        " JOIN plt01.fin_invoices i ON i.invoice_id = l.invoice_id"
        " JOIN plt01.fin_billing_accounts b"
        "   ON b.billing_account_id = i.billing_account_id"
        " LEFT JOIN plt01.cat_variants v ON v.variant_id = l.variant_id"
        " LEFT JOIN plt01.cat_products pr ON pr.product_id = v.product_id"
        " WHERE i.document_kind = 'invoice'"
        "   AND i.issued_on >= %s AND i.issued_on <= %s"
        " GROUP BY 1, 2, 3",
        (span.first, span.last),
    ).fetchall()
    return {(str(r[0]), str(r[1]), str(r[2])): int(r[3]) for r in rows}


def membership_summary(
    pool: Pool, tenant_id: str, *, as_of: date | None = None, expiring_within_days: int = 7,
) -> dict[str, Any]:
    """How many memberships are live, what moved this month, and what is about to expire.

    ADM-CC-01's second metric -- "ACTIVE MEMBERS · 4,812 · +38 this month · 61 joined, 23
    left" -- and its RETENTION attention item, "14 memberships expire within 7 days · JOD
    4,760.00 renewal value".

    **Joined and left come from the lifecycle history, not from the status column.** That
    column is a cache of where a membership is now and says nothing about how it got there, so
    a net figure derived from it would be the count of memberships that *are* active rather
    than the ones that *became* active this month. `mem_lifecycle_changes` is insert-only and
    carries `effective_on`, which is the date the member experienced.

    **Renewal value is the agreement's amount, per currency.** It is what the membership was
    sold at, which is the figure a renewal conversation is about; it is not a forecast and it
    is not summed across currencies.
    """
    as_of = as_of or _today()
    if expiring_within_days < 1 or expiring_within_days > 365:
        raise InvalidRequest("bad_window")
    month = reporting.month_to_date(as_of)
    until = as_of + timedelta(days=expiring_within_days)
    with tenant_scope(pool, tenant_id) as conn:
        by_status = conn.execute(
            "SELECT status, count(*) FROM plt01.mem_memberships GROUP BY status",
        ).fetchall()
        # `activation` is how a membership becomes live; `cancellation` and `expiry` are the
        # two ways it stops. The other eight kinds in the constraint are moves within a life.
        moved = conn.execute(
            "SELECT change_kind, count(*) FROM plt01.mem_lifecycle_changes"
            " WHERE effective_on >= %s AND effective_on <= %s"
            "   AND change_kind IN ('activation', 'cancellation', 'expiry')"
            " GROUP BY change_kind",
            (month.first, month.last),
        ).fetchall()
        expiring = conn.execute(
            f"WITH RECURSIVE {_walk_from("m.status IN ('active', 'grace')")}"
            " SELECT m.membership_id, m.person_id, m.membership_number, m.status,"
            " m.current_period_end, m.ends_on, a.amount_minor, a.currency,"
            " t.membership_kind, t.billing_period, l.depth"
            " FROM plt01.mem_memberships m"
            # The live end: this read *sums* `amount_minor` into the value expiring this
            # month, so a superseded figure is wrong in a total nothing else can check.
            " JOIN live l ON l.membership_id = m.membership_id"
            " JOIN plt01.mem_agreements a ON a.agreement_id = l.agreement_id"
            " JOIN plt01.mem_membership_terms t"
            "   ON t.membership_terms_id = a.membership_terms_id"
            " WHERE m.status IN ('active', 'grace')"
            "   AND coalesce(m.ends_on, m.current_period_end) IS NOT NULL"
            "   AND coalesce(m.ends_on, m.current_period_end) >= %s"
            "   AND coalesce(m.ends_on, m.current_period_end) <= %s"
            " ORDER BY coalesce(m.ends_on, m.current_period_end), m.membership_id"
            " LIMIT %s",
            (as_of, until, LIST_LIMIT),
        ).fetchall()
    _refuse_a_truncated_chain(expiring, 10)
    counts = {str(r[0]): int(r[1]) for r in by_status}
    kinds = {str(r[0]): int(r[1]) for r in moved}
    joined = kinds.get("activation", 0)
    left = kinds.get("cancellation", 0) + kinds.get("expiry", 0)
    value: dict[str, int] = {}
    for row in expiring:
        value[str(row[7])] = value.get(str(row[7]), 0) + int(row[6])
    return {
        "as_of": as_of.isoformat(),
        "active": counts.get("active", 0),
        "by_status": counts,
        "this_month": {
            "first": month.first.isoformat(), "last": month.last.isoformat(),
            "joined": joined, "left": left, "net": joined - left},
        "expiring": {
            "within_days": expiring_within_days, "until": until.isoformat(),
            "count": len(expiring),
            "renewal_value": [
                {"currency": currency, "amount_minor": amount}
                for currency, amount in sorted(value.items())],
            "memberships": [
                {"membership_id": str(r[0]), "person_id": str(r[1]),
                 "membership_number": str(r[2]), "status": str(r[3]),
                 "expires_on": (r[5] or r[4]).isoformat(),
                 "amount_minor": int(r[6]), "currency": str(r[7]),
                 "membership_kind": str(r[8]), "billing_period": str(r[9])}
                for r in expiring],
            "truncated": len(expiring) == LIST_LIMIT,
        },
        "movement_is_from_the_history":
            "joined and left are counted from mem_lifecycle_changes by effective_on. The "
            "status column is a cache of where a membership is now and cannot answer what "
            "moved.",
    }


def list_dunning_cases(
    pool: Pool, tenant_id: str, *, status: str = "open", limit: int = 50,
) -> dict[str, Any]:
    """The recovery journeys, with what each is trying to collect and how far it has got.

    ADM-CC-01's first attention item -- "6 payments failed overnight · JOD 312.00 at risk" --
    and the module's only writer-with-no-reader left after the listing reads were added: a
    case could be opened and advanced and there was no way to see one.

    **`attempts` is the figure that makes a case actionable**, because `collections.py` bounds
    a journey by it and the module's own review found that a caller reporting the same failure
    twice froze the count and the run could never reach `dead`. A board that showed the stage
    without the attempts would be showing the half that moves on its own.
    """
    limit = _bounded(limit)
    _one_of(status, DUNNING_STATUSES, "bad_status")
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT c.case_id, c.billing_account_id, c.invoice_id, c.stage, c.status,"
            " c.opened_on, c.next_action_on, c.attempts, c.access_recommendation,"
            " c.owner_ref, c.resolution, i.document_number, i.gross_minor, i.currency,"
            " i.payment_status, i.due_on, b.payer_person_id,"
            " coalesce((SELECT sum(p.amount_minor) FROM plt01.fin_payments p"
            "            WHERE p.invoice_id = i.invoice_id), 0)"
            " FROM plt01.fin_dunning_cases c"
            " JOIN plt01.fin_invoices i ON i.invoice_id = c.invoice_id"
            " JOIN plt01.fin_billing_accounts b"
            "   ON b.billing_account_id = c.billing_account_id"
            " WHERE c.status = %s"
            " ORDER BY c.next_action_on NULLS LAST, c.opened_on, c.case_id"
            " LIMIT %s",
            (status, limit),
        ).fetchall()
    cases = [
        {"case_id": str(r[0]), "billing_account_id": str(r[1]), "invoice_id": str(r[2]),
         "stage": int(r[3]), "status": str(r[4]), "opened_on": r[5].isoformat(),
         "next_action_on": r[6].isoformat() if r[6] else None, "attempts": int(r[7]),
         "access_recommendation": str(r[8]), "owner_ref": str(r[9]) if r[9] else None,
         "resolution": str(r[10]) if r[10] else None,
         "document_number": str(r[11]), "gross_minor": int(r[12]), "currency": str(r[13]),
         "payment_status": str(r[14]), "due_on": r[15].isoformat(),
         "payer_person_id": str(r[16]),
         # What is actually still at risk, which is not the invoice's gross once something has
         # been paid against it.
         "outstanding_minor": int(r[12]) - int(r[17])}
        for r in rows]
    at_risk: dict[str, int] = {}
    for case in cases:
        currency = str(case["currency"])
        at_risk[currency] = at_risk.get(currency, 0) + int(case["outstanding_minor"])
    return {
        "cases": cases, "count": len(cases), "limit": limit,
        "truncated": len(cases) == limit,
        "at_risk": [{"currency": c, "amount_minor": a} for c, a in sorted(at_risk.items())],
        "at_risk_is_outstanding":
            "at_risk sums what is still unpaid on each cited invoice, not the invoice total.",
    }


def recovery_workspace(
    pool: Pool, tenant_id: str, *, limit: int = 50,
) -> dict[str, Any]:
    """ADM-PAY-05: the failed payments as one decision, sorted by what each one wants.

    The design's argument for this being a workspace rather than a list is that "the six are
    one decision, not six" -- and that is only true once the set has been *sorted*, because a
    batch mixing a member who needs a new card with a member whose membership ended is six
    decisions wearing one button. So this read's job is the sort: it pairs each open dunning
    case with the failure that opened it and the standing of the membership the invoice cites,
    and runs `collections.recovery_treatment` over the pair.

    **Every figure in the header is read off the set rather than supplied.** "All retries
    exhausted" is true when no case is still waiting on an automatic attempt, and "no access
    blocked" when every case's stage recommends `none` -- the two sentences the canvas puts
    under the count. A caller that passed either in would be able to head a workspace with a
    claim its own rows contradict.

    **The membership is the one the invoice cites, never the payer's latest.**
    `fin_invoices.membership_id` is the debt's own reference; picking "the newest membership
    this person has" would answer about a different agreement whenever somebody has two, and
    would make the planner the author when they have two starting on one day.

    **The failure's code is returned and its text is not.** This module's own header says a
    decision branches on the code and never on the prose, and the same reasoning applies to
    what a read hands out: `failure_detail` is unbounded free text a provider supplied, on a
    tenant-wide money permission, and it adds nothing a reader can act on that the code does
    not already say. It is also why the design's "Visa ···4417" has no
    counterpart here -- paragraph 1597 keeps card data out of Veyro entirely, so the method's
    *kind* is the whole of what this build knows about the instrument.

    **No name, no address, no card** -- `payments_ledger`'s rule, for its reason.
    `finance.dunning.read` is tenant-wide, so returning names would make this a lateral read
    path around `people.person.read`. A surface that wants names composes.
    """
    limit = _bounded(limit)
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT c.case_id, c.invoice_id, c.stage, c.attempts AS case_attempts,"
            " c.access_recommendation, c.next_action_on, c.opened_on,"
            " i.document_number, i.gross_minor, i.currency, i.due_on, i.membership_id,"
            " b.payer_person_id,"
            " coalesce((SELECT sum(p.amount_minor) FROM plt01.fin_payments p"
            "            WHERE p.invoice_id = i.invoice_id), 0) AS paid_minor,"
            " f.failure_code, f.method, f.created_at,"
            " (SELECT count(*) FROM plt01.fin_payment_intents pa"
            "   WHERE pa.invoice_id = i.invoice_id AND pa.status = 'failed')"
            "   AS charges_presented,"
            " m.status, m.membership_number"
            " FROM plt01.fin_dunning_cases c"
            " JOIN plt01.fin_invoices i ON i.invoice_id = c.invoice_id"
            " JOIN plt01.fin_billing_accounts b"
            "   ON b.billing_account_id = c.billing_account_id"
            # The failure that opened the case: the most recent failed intent against this
            # invoice. LATERAL rather than a window, because one row per case is what the
            # decision takes and a join that could multiply the cases would change the count
            # in the header.
            " LEFT JOIN LATERAL ("
            "   SELECT pi.failure_code, pi.method, pi.created_at"
            "     FROM plt01.fin_payment_intents pi"
            "    WHERE pi.invoice_id = i.invoice_id AND pi.status = 'failed'"
            "    ORDER BY pi.created_at DESC, pi.intent_id"
            "    LIMIT 1) f ON true"
            " LEFT JOIN plt01.mem_memberships m ON m.membership_id = i.membership_id"
            " WHERE c.status = 'open'"
            " ORDER BY c.next_action_on NULLS LAST, c.opened_on, c.case_id"
            " LIMIT %s",
            (limit,),
        ).fetchall()
    cases: list[dict[str, Any]] = []
    at_risk: dict[str, int] = {}
    by_treatment: dict[str, int] = {t: 0 for t in collections.TREATMENTS}
    for r in rows:
        membership_status = str(r[18]) if r[18] else None
        # **The retry budget counts charges presented against this invoice**, which is neither
        # the case's `attempts` (that counts dunning *steps* taken, and a notice is not a
        # charge) nor one intent's own counter. A retry in this build is a new intent -- a
        # settled one does not settle again -- so an intent's column sits at one however many
        # times the card has been tried, and reading it would make `may_retry` answer "there
        # is budget left" for ever. `may_retry`'s own docstring is about charges presented:
        # "a budget of four attempts is not permission to present a stolen card four times".
        attempts = int(r[17])
        failure_code = str(r[14]) if r[14] else None
        verdict = collections.recovery_treatment(
            failure_code, attempts=attempts, membership_status=membership_status)
        by_treatment[verdict.treatment] += 1
        currency = str(r[9])
        outstanding = int(r[8]) - int(r[13])
        at_risk[currency] = at_risk.get(currency, 0) + outstanding
        cases.append({
            "case_id": str(r[0]), "invoice_id": str(r[1]), "stage": int(r[2]),
            "dunning_attempts": int(r[3]), "access_recommendation": str(r[4]),
            "next_action_on": r[5].isoformat() if r[5] else None,
            "opened_on": r[6].isoformat(),
            "document_number": str(r[7]), "currency": currency,
            "outstanding_minor": outstanding, "due_on": r[10].isoformat(),
            "payer_person_id": str(r[12]),
            "failure_code": failure_code,
            "failure_class": collections.classify_failure(failure_code),
            "method": str(r[15]) if r[15] else None,
            "charges_presented": attempts,
            "failed_at": r[16].isoformat() if r[16] else None,
            "membership_id": str(r[11]) if r[11] else None,
            "membership_status": membership_status,
            "membership_number": str(r[19]) if r[19] else None,
            "treatment": verdict.treatment,
            "treatment_reason": verdict.reason,
            "may_retry": verdict.may_retry,
            # Which message the *system* would send at this stage, which is the mechanism
            # behind the design's "the distinction is enforced by the system rather than left
            # to the sender": the stage picks the template key, not whoever clicks.
            "notification_key": collections.stage(int(r[2])).notification_key,
        })
    return {
        "cases": cases, "count": len(cases), "limit": limit,
        "truncated": len(cases) == limit,
        "at_risk": [{"currency": c, "amount_minor": a} for c, a in sorted(at_risk.items())],
        "by_treatment": by_treatment,
        # The canvas's two header sentences, derived.
        "all_retries_exhausted": by_treatment[collections.TREATMENT_RETRY] == 0,
        "access_recommendations": sorted({str(c["access_recommendation"]) for c in cases}),
        "no_access_blocked": all(
            c["access_recommendation"] == "none" for c in cases),
        "at_risk_is_outstanding":
            "at_risk sums what is still unpaid on each cited invoice, not the invoice total.",
        "nothing_here_sends":
            "This read sorts the cases and sends nothing. MOD-013 authors a notification and"
            " no provider collects it, and this build has no payment link to put in one, so"
            " the batch action the design draws has no writer behind it.",
        "no_card_detail_exists":
            "A failed charge carries its method's kind and a provider's failure code. There is"
            " no card brand and no last four anywhere in this build: paragraph 1597 keeps card"
            " data out of Veyro, so `payment_method_ref` is a token held by the provider.",
    }


def list_disputes(
    pool: Pool, tenant_id: str, *, status: str | None = None, limit: int = 50,
    at: date | None = None,
) -> dict[str, Any]:
    """ADM-PAY-10: the chargebacks, with how long is left to answer each one.

    **The module's last writer with no reader.** `record_dispute`, `respond_to_dispute` and
    `settle_dispute` were all reachable and nothing could list what they had written, so a
    dispute existed only for whoever had just recorded it -- the same shape this repository
    has closed for MOD-004's brands, MOD-017's memberships, MOD-018's chart and MOD-013's
    template body.

    **The window is computed here, not left to a reader to subtract two dates.** The canvas
    leads with "Evidence due 26 August · 7 days" and then "Missing the deadline forfeits
    the amount automatically", which is the whole urgency of the screen -- and
    `collections.evidence_window` already decides it, including letting `days_remaining` go
    negative rather than clamping, because a closed window is the dispute somebody most needs
    to see. A surface subtracting the dates itself would be a second definition of the one
    figure the screen is about.

    **No name and no card** -- `payments_ledger`'s rule. The row carries `payer_person_id`
    and the document the dispute is against; a surface that wants a name composes.
    """
    limit = _bounded(limit)
    _one_of(status, frozenset(collections.DISPUTE_STATUSES), "bad_status")
    at = at or datetime.now(UTC).date()
    where = ["true"]
    params: list[Any] = []
    if status is not None:
        where.append("d.status = %s")
        params.append(status)
    params.append(limit)
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT d.dispute_id, d.payment_id, d.provider_case_ref, d.dispute_kind,"
            " d.reason_code, d.amount_minor, d.currency, d.opened_on, d.respond_due_on,"
            " d.status, d.response_ref, d.responded_at, d.outcome, d.closed_at,"
            " b.payer_person_id, p.received_at, p.method, p.invoice_id,"
            " i.document_number, i.fiscal_status, i.fiscal_ack_ref,"
            " i.membership_id, i.issued_on"
            " FROM plt01.fin_disputes d"
            " JOIN plt01.fin_billing_accounts b"
            "   ON b.billing_account_id = d.billing_account_id"
            " JOIN plt01.fin_payments p ON p.payment_id = d.payment_id"
            " LEFT JOIN plt01.fin_invoices i ON i.invoice_id = p.invoice_id"
            f" WHERE {' AND '.join(where)}"
            " ORDER BY d.respond_due_on, d.opened_on, d.dispute_id"
            " LIMIT %s",
            tuple(params),
        ).fetchall()
    disputes = []
    at_stake: dict[str, int] = {}
    for r in rows:
        window = collections.evidence_window(
            opened_on=r[7], respond_due_on=r[8], at=at)
        currency = str(r[6])
        if str(r[9]) in ("open", "responded"):
            at_stake[currency] = at_stake.get(currency, 0) + int(r[5])
        disputes.append({
            "dispute_id": str(r[0]), "payment_id": str(r[1]),
            "provider_case_ref": str(r[2]), "dispute_kind": str(r[3]),
            "reason_code": str(r[4]), "amount_minor": int(r[5]), "currency": currency,
            "opened_on": r[7].isoformat(), "respond_due_on": r[8].isoformat(),
            "status": str(r[9]),
            "response_ref": str(r[10]) if r[10] else None,
            "responded_at": r[11].isoformat() if r[11] else None,
            "outcome": str(r[12]) if r[12] else None,
            "closed_at": r[13].isoformat() if r[13] else None,
            "payer_person_id": str(r[14]),
            "paid_at": r[15].isoformat(), "method": str(r[16]),
            "invoice_id": str(r[17]) if r[17] else None,
            "document_number": str(r[18]) if r[18] else None,
            "fiscal_status": str(r[19]) if r[19] else None,
            "fiscal_ack_ref": str(r[20]) if r[20] else None,
            "membership_id": str(r[21]) if r[21] else None,
            "billed_on": r[22].isoformat() if r[22] else None,
            **window,
        })
    return {
        "disputes": disputes, "count": len(disputes), "limit": limit,
        "truncated": len(disputes) == limit, "as_of": at.isoformat(),
        "at_stake": [{"currency": c, "amount_minor": a}
                     for c, a in sorted(at_stake.items())],
        "at_stake_is_undecided_only":
            "at_stake sums the disputes still open or answered and awaiting a decision. A"
            " dispute already won or lost is settled money and is not at stake.",
        "the_amount_is_held_by_the_acquirer":
            "A chargeback holds the amount at the provider until the scheme decides. Nothing"
            " in this build moves it: `settle_dispute` records the outcome and a lost"
            " chargeback is reconciled against the provider statement, not reversed here.",
        "evidence_is_assembled_by_the_caller":
            "This read returns the dispute and its deadline. What a gym can prove -- the"
            " check-ins in the billed month, the signed agreement, the invoice and its fiscal"
            " acknowledgement -- lives in MOD-022, MOD-017 and the invoice, each behind its own"
            " permission, so a surface composes them rather than this read joining across"
            " them.",
    }


def payments_ledger(
    pool: Pool, tenant_id: str, *, since: date | None = None, until: date | None = None,
    needs_action_only: bool = False, limit: int = 100,
) -> dict[str, Any]:
    """ADM-PAY-01: money in, money out and money contested, on one axis.

    > Refunds carry a negative sign and the parenthetical original. **A refund is never shown
    > as a payment of a different colour -- it is a different sign on the same axis.**

    That line is the whole design of this read, and it is why the four tables are unioned
    rather than returned as four lists: a surface that drew payments, then refunds, then
    disputes would make the reader add up three columns to find out what a day actually
    took, and would let a refund hide under a heading nobody scrolled to.

    **A failed charge is a row, not an absence.** `fin_payment_intents` carries the attempts
    that never became payments -- the canvas's "6 failed" -- and leaving them out would make
    this a list of successes. `needs_action` marks the three kinds that want a person: a
    failed or unknown intent, a pending refund, and an open dispute.

    **No name, no address, no card.** The row carries `payer_person_id` and the method's
    *kind*, and nothing else about anybody: `finance.payment.read` is a tenant-wide money
    permission, and returning names here would make it a lateral read path around
    `people.person.read` -- MOD-010's `events.event.read` finding, which this repository has
    paid for once. A surface that wants names composes, the way the members list does.
    """
    until = until or datetime.now(UTC).date()
    since = since or (until - timedelta(days=30))
    if since > until:
        raise InvalidRequest("a_ledger_window_ends_after_it_starts")
    if not 1 <= limit <= 500:
        raise InvalidRequest("a_payments_ledger_takes_between_one_and_five_hundred")
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            # One SELECT per kind, unioned, each projecting the same seven columns. The
            # amount's sign is set here rather than by the caller, because "a refund is a
            # different sign on the same axis" is a property of the data and not of a view.
            "SELECT * FROM ("
            "  SELECT 'payment' AS kind, p.payment_id AS row_id, p.received_at AS at,"
            "         a.payer_person_id, p.method, p.amount_minor, p.currency,"
            "         'received' AS state, false AS needs_action, p.payment_id AS about"
            "    FROM plt01.fin_payments p"
            "    JOIN plt01.fin_billing_accounts a"
            "      ON a.billing_account_id = p.billing_account_id"
            "  UNION ALL"
            # An intent that settled became a payment above; only the ones that did not are
            # news. `unknown` is MOD-017's "the provider did not answer", which is the state
            # that most needs a person and is easiest to leave out of a ledger.
            "  SELECT 'attempt', i.intent_id, i.created_at, a.payer_person_id, i.method,"
            "         i.amount_minor, i.currency, i.status,"
            "         i.status IN ('failed', 'unknown'), i.intent_id"
            "    FROM plt01.fin_payment_intents i"
            "    JOIN plt01.fin_billing_accounts a"
            "      ON a.billing_account_id = i.billing_account_id"
            "   WHERE i.status <> 'succeeded'"
            "  UNION ALL"
            "  SELECT 'refund', r.refund_id, r.approved_at, a.payer_person_id, 'refund',"
            "         -r.amount_minor, r.currency, r.status, r.status = 'pending',"
            "         r.payment_id"
            "    FROM plt01.fin_refunds r"
            "    JOIN plt01.fin_billing_accounts a"
            "      ON a.billing_account_id = r.billing_account_id"
            "  UNION ALL"
            "  SELECT 'dispute', d.dispute_id, d.opened_on::timestamptz, a.payer_person_id,"
            "         d.dispute_kind, -d.amount_minor, d.currency, d.status,"
            "         d.status IN ('open', 'under_review'), d.payment_id"
            "    FROM plt01.fin_disputes d"
            "    JOIN plt01.fin_billing_accounts a"
            "      ON a.billing_account_id = d.billing_account_id"
            ") ledger"
            " WHERE at::date >= %s AND at::date <= %s"
            "   AND (NOT %s OR needs_action)"
            " ORDER BY at DESC, row_id"
            " LIMIT %s",
            (since, until, needs_action_only, limit)).fetchall()
    entries = [
        {"kind": str(r[0]), "row_id": str(r[1]), "at": r[2].isoformat(),
         "payer_person_id": None if r[3] is None else str(r[3]),
         "method": str(r[4]), "amount_minor": int(r[5]), "currency": str(r[6]),
         "state": str(r[7]), "needs_action": bool(r[8]),
         # What a refund or a dispute is *about*: the payment it reverses. The canvas calls
         # it "the parenthetical original", and without it a negative row is a figure with
         # no story.
         "about_payment_id": None if r[9] is None else str(r[9])} for r in rows]
    return {
        "entries": entries,
        "count": len(entries),
        "since": since.isoformat(), "until": until.isoformat(),
        "needs_action": sum(1 for e in entries if e["needs_action"]),
        "failed": sum(1 for e in entries
                      if e["kind"] == "attempt" and e["state"] == "failed"),
        "refunded": sum(1 for e in entries if e["kind"] == "refund"),
        "disputed": sum(1 for e in entries if e["kind"] == "dispute"),
        "truncated": len(entries) == limit,
        "a_refund_is_a_sign_not_a_kind":
            "Refunds and disputes carry a negative amount on the same axis as a payment. "
            "They are never a payment of a different colour.",
        "no_name_is_returned":
            "Rows carry payer_person_id and nothing else about anybody. A tenant-wide money "
            "permission must not become a read path around people.person.read.",
    }
