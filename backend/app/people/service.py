"""MOD-014 PPL-01 service: people, profiles, contact points, relationships, merge and timeline.

The decisions live in `app.people.dedup`, `lifecycle`, `merge`, `timeline`, `fields` and
`visibility`. This module reads rows, calls those, and writes what they return.

**The 360 read is composed, never stored.** Paragraph 816: "the canonical model follows aggregate
ownership rather than a single shared member schema. Member 360 is a read projection assembled
from domain-owned records and the event timeline." So `member_360` queries this module's own
tables plus the timeline and reports, per section, where the data came from -- and a section
whose owning module does not exist yet says so rather than returning an empty list that reads as
"this member has no invoices".

**Masking is applied here, on the way out.** MOD-008 computes `masked_fields` on every allowed
decision and from MOD-008 to MOD-013 nothing read it. Every read in this module takes the gate's
list and the caller's permissions, and `visibility` applies both -- the gate's field names and
the classification each custom field and note carries. A read path that forgot would hand over
the unmasked record, so the reads take the list as a required argument rather than an optional
one.

**What this module cannot do, stated here rather than discovered later.**

* **It cannot verify an identity link.** `iam` is a separate plane under a separate role; the
  link is recorded and a stale one is possible. `LinkIdentity` is the only writer.
* **It cannot find a merged person's rows in other modules.** Paragraph 1300 forbids
  cross-domain write-table access, so a merge points the losing record at the survivor and
  leaves every other module's references intact. Readers follow the pointer.
* **It does not search.** Paragraph 4218's permission-aware search index is ENG-01's, and a
  `LIKE` scan presented as search would be a read path with no freshness contract and no
  pre-filter.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from psycopg import Connection, errors

from app.authorization.service import Forbidden
from app.db import Pool, tenant_scope
from app.errors import Conflict, InvalidRequest, NotFound
from app.events import service as events
from app.identity.service import normalize_email, normalize_phone
from app.people import dedup, fields, lifecycle, merge, timeline, visibility

#: What a note can be about. Three, because the product distinguishes them and the masking has
#: to: health information, what staff write about a person, and everything else.
NOTE_CLASSES = ("general", "health", "sensitive")

#: Each note class mapped to one of MOD-008's five sensitivity classes. `sensitive` becomes
#: `identity` rather than inventing a sixth class: a class the gate has never heard of reads as
#: unmasked, which is the direction that leaks.
NOTE_VISIBILITY = {"general": "none", "health": "health", "sensitive": "identity"}


def _now() -> datetime:
    return datetime.now(UTC)


def _check_name(error: errors.CheckViolation) -> str:
    name = getattr(error.diag, "constraint_name", None)
    return str(name) if name else "constraint_violation"


def _masks(
    gate_fields: tuple[str, ...], readable: frozenset[str],
) -> tuple[str, ...]:
    """The gate's masked fields plus this module's class mask, as one list.

    Two halves, and the second one was missing. The gate names what a tenant's MASK policy
    picked out; `visibility.classified_masks` names the columns whose class the caller holds no
    permission for. Every read in this module goes through here, so there is one place to look
    and no read can take only half of it.
    """
    return tuple(sorted(set(gate_fields) | set(visibility.classified_masks(readable))))


def _require_guardianship(
    conn: Connection[Any], person: dict[str, Any], held_permissions: set[str],
    actor_person_id: str | None,
) -> str:
    """Paragraph 1372, on **every** path that returns a minor's data.

    `get_person` had this and the notes and timeline reads did not, so a reviewer read a child's
    notes with the credential the record read had just refused. Hoisted into one function that
    all four reads call, because the next read somebody adds will call it too -- which a copy in
    each of three places would not guarantee.

    **A `Forbidden`, not a `Conflict`.** Every other authorization refusal in this build is 403,
    and a 409 told the caller the request conflicted with something rather than that they may
    not make it. The refusal still reaches no audit log, because the gate already allowed and
    MOD-008 audits denials: that is a real gap and it is in the known-gaps list rather than
    papered over here.
    """
    age = _age_years(person["date_of_birth"], _now().date())
    minor = visibility.is_minor(age)
    guardian = (
        actor_person_id is not None
        and _is_guardian_of(conn, actor_person_id, str(person["person_id"]))
    )
    allowed, why = visibility.guardianship_satisfied(
        minor=minor, actor_is_guardian=guardian,
        held_permissions=frozenset(held_permissions))
    if not allowed:
        raise Forbidden(why)
    return why


def _check_version(expected: int, actual: int) -> None:
    """`lifecycle.check_version`, as a service error rather than a bare `ValueError`.

    The decision modules raise their own exception type on purpose -- they know nothing about
    HTTP -- so every service that calls one has to translate. Calling `check_version` directly
    let a stale version propagate as a plain `ValueError`, which the error handlers do not
    catch: the caller got a 500 reading "try again" for a condition whose correct answer is
    "re-read the record and send the version you saw". Found by the tests, where it surfaced as
    the wrong exception type.
    """
    try:
        lifecycle.check_version(expected, actual)
    except lifecycle.LifecycleError as e:
        raise Conflict(str(e)) from None


def normalize_contact(kind: str, raw: str) -> str:
    """The stored match value for a contact point.

    **MOD-007's normalizers, imported rather than reimplemented.** A second spelling rule would
    make a duplicate invisible to whichever module disagreed, and MOD-011's review already found
    one instance of exactly that: a limiter that lowercased where `normalize_phone` strips
    separators, so eight spellings of one number each got a full budget.

    An address has no normalizer anywhere in the build and this module does not invent one --
    postal normalization is jurisdictional and getting it wrong merges two neighbours. A folded
    string is the honest answer and `dedup` weights an address match at nothing, so the weak
    normalization decides nothing.
    """
    if kind == "email":
        return normalize_email(raw)
    if kind == "phone":
        return normalize_phone(raw)
    if kind == "address":
        return " ".join(raw.split()).lower()
    raise InvalidRequest(f"unknown_contact_kind_{kind}")


# ------------------------------------------------------------------------------ people

#: How many holders of one contact value a single read may return.
#:
#: Small on purpose. An exact normalized match on a phone number is one person, or a handful
#: on a shared family line; a ceiling in the hundreds would make this a way to enumerate a
#: tenant's members one value at a time rather than a duplicate check. The caller may ask for
#: less and not for more, which is every other listing read in this build.
CONTACT_MATCH_PAGE = 10

#: How many people one lookup may name. FD-02 draws two side by side and its canvas's own rule
#: is that "ambiguous matches list side by side rather than guessing" -- so this is a handful a
#: receptionist can compare while somebody waits, not a page to scroll. Bounded on the server
#: for the reason every listing read here is: unbounded would be a bulk export of a tenant's
#: members on a routine permission.
LOOKUP_PAGE = 10

#: The shortest prefix a lookup will answer. **Two, because one letter is every member whose
#: name starts with it** -- which is not an ambiguous match a desk resolves by photo, it is the
#: whole tenant in alphabetical order, and an index scan over it is no cheaper than a scan. The
#: refusal says so rather than returning the first ten of three thousand, which would read as
#: "these are the matches".
LOOKUP_MIN_PREFIX = 2


def holders_of(pool: Pool, tenant_id: str, *, kind: str, value: str) -> list[str]:
    """Which live people already hold this contact value. The existence half of `match_contact`.

    **It lives here because MOD-027 holds no number.** FD-05's walk-in command has to refuse a
    phone that already belongs to somebody -- `AUTO_MERGE_THRESHOLD` is `None` precisely
    because two siblings at one address with one family line is the ordinary case, so silently
    reusing whoever holds the number would be making the merge decision paragraph 10200
    reserves for a person. A query on `ppl_contact_points` written in `app/crm/` would break
    that module's own stated property and the test that asserts it, so the clause is here, in
    the module that owns contact data.

    **The same normalizer and the same two clauses as `match_contact`, and a different
    question.** It answers "is there anybody" rather than "who, masked" -- so there is nothing
    to mask and no gate argument: it returns ids a caller already has to hold
    `people.person.write` to act on, and a caller wanting the names calls the read beside it.
    `merge_status = 'active'` is the survivor, for that read's own reason: a merge leaves the
    losing record's contact points where they are, so one number sits on two rows.
    """
    normalized = normalize_contact(kind, value)
    if not normalized:
        raise InvalidRequest("a_contact_value_is_not_blank")
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT DISTINCT p.person_id FROM plt01.ppl_contact_points c"
            " JOIN plt01.ppl_persons p ON p.person_id = c.person_id"
            " WHERE c.kind = %s AND c.value_normalized = %s"
            "   AND p.merge_status = 'active'"
            " ORDER BY p.person_id LIMIT %s",
            (kind, normalized, CONTACT_MATCH_PAGE),
        ).fetchall()
    return [str(r[0]) for r in rows]


def match_contact(
    pool: Pool, tenant_id: str, *, kind: str, value: str,
    masked_fields: tuple[str, ...], held_permissions: set[str], limit: int = 5,
) -> dict[str, Any]:
    """Who already holds this contact point, asked before anybody is created.

    **ADM-MEM-10 runs this as the phone is typed, before anything is saved**: "This number
    already has a record -- Hala Barakat, joined Feb 2025. Continue and you will create a
    second record for the same person." The canvas's own note says why it is a read rather
    than a cleanup: "preventing the duplicate costs one screen; ADM-MEM-11 exists because
    prevention is never perfect."

    **`find_duplicates` could not answer this.** It scores *pairs that already exist* -- both
    sides have to be rows in the table -- so the one moment where a duplicate is cheap to
    prevent, the moment before the second record exists, had nothing to ask. This is that
    read, and it is the eighth instance of this build's "a writer with no reader" shape read
    from the other end: the index it uses, `ppl_contact_points_by_value`, has existed since
    MOD-014 was built with its own comment saying "finding everybody who shares an address is
    how `find_duplicates` works", and no route could ask it a value.

    **Normalized by the write's own function.** `normalize_contact` is MOD-007's normalizer
    imported rather than reimplemented, and it is what `create_person` stores; a second
    spelling rule here would make a duplicate invisible to exactly this check, which is
    MOD-011's review finding where a limiter lowercased and `normalize_phone` strips
    separators, so eight spellings of one number each got a full budget.

    **Masked like every other read in this module**, both halves as required arguments. The
    name is the point of the banner -- a desk cannot recognise a person from a uuid -- and it
    is `identity` class, so a routine AAL-1 session sees the withheld marker and the rest of
    the row, which is still enough to say "somebody already has this number". This adds no
    capability: the same permission already reads any person by id and lists every member.

    **Active records only, which is what makes the answer actionable.** A merge leaves the
    losing person's contact points where they are -- "a merge copies and nothing cleans up" --
    so one number can sit on two rows, and offering the merged-away one would point a desk at
    a record whose own readers are told to follow a pointer. `merge_status = 'active'` is the
    survivor, which is the record somebody would open.
    """
    normalized = normalize_contact(kind, value)
    if not normalized:
        raise InvalidRequest("a_contact_value_is_not_blank")
    if limit < 1 or limit > CONTACT_MATCH_PAGE:
        raise InvalidRequest("bad_limit")
    readable = visibility.readable_classes(frozenset(held_permissions))
    masks = _masks(masked_fields, readable)
    with tenant_scope(pool, tenant_id) as conn:
        # **One row per person, oldest first, bounded.** `DISTINCT ON` collapses a person who
        # holds the same value twice -- two contact rows of one kind are forbidden per person
        # by `ppl_contact_points_distinct`, so this is the cross-kind and primary-flag case --
        # and the outer order is by when the record was known, because the oldest is the one a
        # second entry would be duplicating. Unordered would make the planner the author, which
        # is MOD-018's `chart_for` finding; unbounded would be a bulk read on a routine
        # permission. One extra row is fetched so `more` is a fact rather than an inference.
        rows = conn.execute(
            "SELECT * FROM ("
            "  SELECT DISTINCT ON (p.person_id)"
            "    p.person_id, p.legal_name, p.preferred_name, p.created_at,"
            "    m.lifecycle_state, m.member_number, m.joined_on, c.is_primary"
            "    FROM plt01.ppl_contact_points c"
            "    JOIN plt01.ppl_persons p ON p.person_id = c.person_id"
            "    LEFT JOIN plt01.ppl_member_profiles m ON m.person_id = c.person_id"
            "   WHERE c.kind = %s AND c.value_normalized = %s"
            "     AND p.merge_status = 'active'"
            "   ORDER BY p.person_id, c.is_primary DESC"
            ") q"
            " ORDER BY coalesce(q.joined_on, q.created_at::date), q.person_id"
            " LIMIT %s",
            (kind, normalized, limit + 1),
        ).fetchall()
    more = len(rows) > limit
    rows = rows[:limit]
    people = [
        visibility.apply_record(
            {
                "person_id": str(r[0]),
                "legal_name": r[1],
                "preferred_name": r[2],
                "known_since": r[3].date().isoformat(),
                "lifecycle_state": r[4],
                "member_number": r[5],
                "joined_on": r[6].isoformat() if r[6] else None,
                "is_primary": bool(r[7]),
            },
            masks,
        )
        for r in rows
    ]
    return {
        "kind": kind,
        "matches": people,
        "count": len(people),
        #: True when the bound was reached, so a surface says "and others" rather than
        #: implying the list is everybody who holds this number.
        "more": more,
        "limit": limit,
        "masked_fields": list(masks),
        #: Named rather than omitted, because the canvas's banner reads "Hala Barakat . Club .
        #: Sweifieh . joined Feb 2025" and two of those four are other modules' or nobody's.
        "fields_this_module_cannot_answer": {
            "plan": "membership.record.read (MOD-017)",
            "club": "no home-club concept exists in this build",
        },
        #: An exact match is one signal, not the judgement.
        "a_match_is_not_a_duplicate_verdict": (
            "this is the same normalized contact point, which is one of `dedup.WEIGHTS`' "
            "signals rather than the whole score. A second record for one person is sometimes "
            "right -- a shared family phone is the ordinary case -- so this says who already "
            "holds it and leaves the decision to the person typing, which is paragraph "
            "10200's requirement that a human decides"),
        #: And it is deliberately not a search.
        "this_is_an_exact_match_and_not_a_search": (
            "the value is normalized and compared for equality, so a mistyped digit finds "
            "nothing. There is no fuzzy match here for `dedup`'s own reason: an edit distance "
            "produces a confident wrong answer on two siblings at one address"),
    }


def create_person(
    pool: Pool, tenant_id: str, *, legal_name: str, actor_id: str, correlation_id: str,
    preferred_name: str | None = None, date_of_birth: date | None = None,
    contacts: list[dict[str, str]] | None = None, at: datetime | None = None,
) -> dict[str, Any]:
    """CreatePerson, with its contact points, and publish `person.created`.

    The contact points come in the same command because a person with no way to reach them is a
    record nobody can use, and two commands would mean a window where the duplicate detector
    sees a nameless-looking person with no signals.

    **A birth date in the future is refused here**, not only by the constraint: the CHECK uses
    `CURRENT_DATE`, which makes it time-dependent, and a validation the caller gets a 422 for is
    better than a 500 from a constraint whose message names a column.
    """
    moment = at or _now()
    if not legal_name.strip():
        raise InvalidRequest("a_person_has_a_legal_name")
    if date_of_birth is not None and date_of_birth > moment.date():
        raise InvalidRequest("a_birth_date_is_in_the_past")
    prepared: list[tuple[str, str, str, bool]] = []
    for entry in contacts or []:
        kind = str(entry.get("kind", ""))
        raw = str(entry.get("value", ""))
        prepared.append((kind, raw, normalize_contact(kind, raw),
                         bool(entry.get("is_primary", False))))

    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.ppl_persons
                    (tenant_id, legal_name, preferred_name, date_of_birth, created_by,
                     correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING person_id, version, created_at
                """,
                (tenant_id, legal_name.strip(), (preferred_name or None), date_of_birth,
                 actor_id, correlation_id),
            ).fetchone()
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        person_id = str(row[0])
        for kind, raw, normalized, primary in prepared:
            try:
                conn.execute(
                    """
                    INSERT INTO plt01.ppl_contact_points
                        (tenant_id, person_id, kind, value_raw, value_normalized, is_primary,
                         recorded_by, correlation_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (tenant_id, person_id, kind, raw.strip(), normalized, primary, actor_id,
                     correlation_id),
                )
            except errors.UniqueViolation:
                raise Conflict("this_contact_point_was_given_twice") from None
            except errors.CheckViolation as e:
                raise InvalidRequest(_check_name(e)) from None
        _append(conn, tenant_id, "person.created", person_id,
                {"person_id": person_id, "legal_name_present": True},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"person_id": person_id, "version": int(row[1]),
            "created_at": row[2].isoformat()}


def get_person(
    pool: Pool, tenant_id: str, person_id: str, *, masked_fields: tuple[str, ...],
    held_permissions: set[str], actor_person_id: str | None = None,
) -> dict[str, Any]:
    """One person with their contact points, custom fields and tags -- masked.

    `masked_fields` and `held_permissions` are **required**, not optional. A read path that
    could be called without them would be a read path somebody calls without them, which is how
    "the mask is computed but not applied" survived five modules.

    A minor's record needs guardianship or staff permission (paragraph 1372). The check runs
    before anything is returned and the refusal names which of the two was missing.
    """
    readable = visibility.readable_classes(frozenset(held_permissions))
    # **The gate's mask plus this module's own class mask.** The gate names the fields a
    # tenant's MASK policy picked out; `classified_masks` names the ones the caller holds no
    # class permission for. Without the second half a routine read returned `date_of_birth` and
    # every contact value in the clear while masking a classified custom field beside them --
    # found independently by two reviewers, and the bound the permission catalogue claims for
    # `people.person.read` being routine.
    masks = _masks(masked_fields, readable)
    with tenant_scope(pool, tenant_id) as conn:
        person = _person_row(conn, person_id)
        _require_guardianship(conn, person, held_permissions, actor_person_id)
        age = _age_years(person["date_of_birth"], _now().date())
        minor = visibility.is_minor(age)
        guardian = (
            actor_person_id is not None
            and _is_guardian_of(conn, actor_person_id, person_id)
        )
        _, why = visibility.guardianship_satisfied(
            minor=minor, actor_is_guardian=guardian,
            held_permissions=frozenset(held_permissions))
        record = {
            **person,
            "is_minor": minor,
            "guardianship": why,
            "contact_points": _contact_points(conn, person_id),
            "tags": _tags(conn, person_id),
            "custom_fields": _custom_fields(conn, person_id, readable),
            "relationships": _relationships(conn, person_id),
        }
    return visibility.apply_record(record, masks)


#: What a members list may be bounded to. Larger than a page on purpose: the design's own
#: scale note says "Filters query server-side, the count states matches against total,
#: selection is bounded to the loaded page" and "there is no state where 4,812 rows render".
PEOPLE_PAGE = 200

#: How many identities one call may resolve to people. The callers are screens rendering the
#: actors on a page, so the bound is a page's worth -- and bounded on the server, because an
#: unbounded read of the whole link table is "which of this tenant's members can sign in".
IDENTITY_LINK_PAGE = 200


#: How many people one batched read may name.
#:
#: **A roster, not a page of them.** FD-06 draws eighteen rows and a waitlist of three; the
#: ceiling is well past the largest class a `sch_sessions` capacity admits, and it is a
#: ceiling rather than no bound because a repeated query parameter with none is a request
#: whose cost the caller chooses.
NAMES_BATCH = 200


def lookup_people(
    pool: Pool, tenant_id: str, *, query: str,
    masked_fields: tuple[str, ...], held_permissions: set[str],
    limit: int = 5,
) -> dict[str, Any]:
    """Find the person standing at the desk, by the start of their name. FD-02. ADR-0012.

    **A lookup, not a search**, and the distinction is the whole of ADR-0012 rather than a
    nicety: paragraph 4218's permission-aware search index with a mandatory query pre-filter is
    ENG-01's, and this read has none of the four properties that objection is about. One entity.
    One tenant, enforced by RLS *below* the query, so the pre-filter is the database's rather
    than something this function remembers. No index to go stale, because it reads the table of
    record. And a bounded page every row of which goes through this module's own gate.

    **The prefix is matched against the index `0032` adds, and the one `0009` already had cannot
    do it.** That one is `(tenant_id, lower(legal_name))` with the default operator class, which
    serves the equality `find_duplicates` folds a name for and -- because this database is not
    in the C locale -- gives a sequential scan for `LIKE 'hala%'`. Measured, not assumed.

    **Masked like every other read here**, both halves as required arguments. `legal_name` is
    `identity` class, so a routine AAL-1 desk gets the withheld marker and the rest of the row,
    which is still enough to say two people match -- and the screen offers the step-up rather
    than a column of markers with nothing to act on, which is the members list's own finding.

    **Active records only**, for `match_contact`'s reason: a merge leaves the losing person's
    rows where they are, so offering the merged-away one would point a desk at a record whose
    own readers are told to follow a pointer.

    **No ranking and no score.** The canvas requires ambiguous matches "side by side rather
    than guessing", so the order is the name's own and the desk decides. A relevance figure
    over two rows would be a confident answer about which person is in front of them.
    """
    folded = " ".join(query.split()).lower()
    if len(folded) < LOOKUP_MIN_PREFIX:
        raise InvalidRequest("a_lookup_needs_at_least_two_characters")
    if limit < 1 or limit > LOOKUP_PAGE:
        raise InvalidRequest("bad_limit")
    readable = visibility.readable_classes(frozenset(held_permissions))
    masks = _masks(masked_fields, readable)
    with tenant_scope(pool, tenant_id) as conn:
        # **`LIKE`, with the pattern's own metacharacters escaped.** The query is what somebody
        # typed, so a `%` in it would match everything from that point and a `_` any single
        # character -- MOD-018 shipped exactly that in a wallet idempotency key and a till
        # handed over 90.00 of goods for 1.00. `\` is escaped first, because escaping it after
        # the others would double the escapes they introduced.
        pattern = (folded.replace("\\", "\\\\")
                   .replace("%", "\\%").replace("_", "\\_")) + "%"
        # One extra row, so `more` is a fact rather than an inference -- and ordered by the
        # folded name then the id, because an unordered lookup makes the planner the author
        # and two people called Hala would come back in whichever order a scan found them.
        rows = conn.execute(
            "SELECT p.person_id, p.legal_name, p.preferred_name, p.date_of_birth,"
            "       m.lifecycle_state, m.member_number, m.joined_on,"
            "       t.location_id"
            "  FROM plt01.ppl_persons p"
            "  LEFT JOIN plt01.ppl_member_profiles m ON m.person_id = p.person_id"
            "  LEFT JOIN plt01.ppl_tenant_profiles t ON t.person_id = p.person_id"
            " WHERE lower(p.legal_name) LIKE %s AND p.merge_status = 'active'"
            " ORDER BY lower(p.legal_name), p.person_id"
            " LIMIT %s",
            (pattern, limit + 1),
        ).fetchall()
    more = len(rows) > limit
    rows = rows[:limit]
    people = [
        visibility.apply_record(
            {
                "person_id": str(r[0]),
                "legal_name": r[1],
                "preferred_name": r[2],
                "lifecycle_state": r[4],
                "member_number": r[5],
                "joined_on": r[6].isoformat() if r[6] else None,
                # **The club, which is a filter on this module and the only one it has.** The
                # canvas prints "Club · Sweifieh" -- a plan and a site -- and the plan is
                # MOD-017's. This is the tenant profile's own location, composed by name on the
                # surface because `ppl_tenant_profiles` holds an id.
                "location_id": str(r[7]) if r[7] else None,
            },
            masks,
        )
        for r in rows
    ]
    return {
        "query": folded,
        "count": len(people),
        "more": more,
        "people": people,
        "masked_fields": list(masks),
        # Said on the read rather than left to a surface, because each is a claim a screen
        # would otherwise make on this module's behalf.
        "a_prefix_of_the_name_and_nothing_else": (
            "this matches the start of a person's legal name. It is not a search: there is no "
            "index to be stale, no ranking, and no match on a preferred name, a note or an "
            "address -- ADM-SRCH-01's command bar across entities is a different read"),
        "a_number_is_matched_whole": (
            "a phone or an email is `GET /people/contact-match`, which normalizes and matches "
            "the whole value on purpose: a mistyped digit finding somebody else is worse than "
            "finding nobody"),
        "the_plan_and_the_photo_are_not_this_module_s": (
            "FD-02 confirms identity by a photo and shows a plan beside it. The plan is "
            "MOD-017's and the photo needs an object store, so a surface composes the first "
            "and says the second is absent"),
    }


def names_of(
    pool: Pool, tenant_id: str, person_ids: list[str], *,
    masked_fields: tuple[str, ...], held_permissions: set[str],
) -> dict[str, Any]:
    """Who these people are, for a surface that already holds a list of ids.

    **One request for a roster, not one per row.** Every screen in this build that shows
    another module's rows beside a person composes the two -- paragraph 1300 bars the join and
    a surface asking twice is not a join -- and the staff list already paid for the other half
    of that lesson: fifty rows asking one at a time is the round-trip problem `/authz/checks`
    exists for. FD-06's roster is MOD-020's and the names are MOD-014's, so this is the shape
    that composition needs.

    **Masked like every other read here**, both halves as required arguments, so a routine
    front-desk session gets the withheld marker and a stepped-up one gets the name -- the same
    answer `GET /people/{id}` would give for each of them, which is the property that makes a
    batch safe: it is a list of single reads and not a weaker one.

    **It answers about the ids it was given and says which it did not find.** A caller holding
    a stale id gets it back under `unknown` rather than a shorter list it has to diff, and a
    merged-away person resolves to nothing here for `match_contact`'s reason -- the record is
    dead and its readers are told to follow a pointer.
    """
    if len(person_ids) > NAMES_BATCH:
        raise InvalidRequest("too_many_person_ids")
    wanted = sorted(set(person_ids))
    if not wanted:
        return {"people": [], "unknown": [], "masked_fields": []}
    readable = visibility.readable_classes(frozenset(held_permissions))
    masks = _masks(masked_fields, readable)
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT p.person_id, p.legal_name, p.preferred_name,"
            "       m.lifecycle_state, m.member_number"
            "  FROM plt01.ppl_persons p"
            "  LEFT JOIN plt01.ppl_member_profiles m ON m.person_id = p.person_id"
            " WHERE p.person_id = ANY(%s) AND p.merge_status = 'active'"
            " ORDER BY p.person_id",
            (wanted,),
        ).fetchall()
    people = [
        visibility.apply_record(
            {
                "person_id": str(r[0]),
                "legal_name": r[1],
                "preferred_name": r[2],
                "lifecycle_state": r[3],
                "member_number": r[4],
            },
            masks,
        )
        for r in rows
    ]
    found = {person["person_id"] for person in people}
    return {
        "people": people,
        #: Named rather than dropped: a caller that diffed two lists to find them would be
        #: re-deriving what this read already knows.
        "unknown": [one for one in wanted if one not in found],
        "masked_fields": list(masks),
    }


def list_people(
    pool: Pool, tenant_id: str, *, masked_fields: tuple[str, ...],
    held_permissions: set[str], lifecycle_state: str | None = None,
    tag_key: str | None = None, limit: int = 50,
) -> dict[str, Any]:
    """The members list ADM-MEM-05 specifies, bounded to the columns this module owns.

    **The design names seven columns and this module can answer two of them.** MEMBER and
    STATE are MOD-014's; PLAN and RENEWS are MOD-017's, BALANCE is MOD-018's, LAST VISIT is
    MOD-020's or MOD-022's, and CLUB is a home-club concept no module has. Paragraph 1300 bars
    cross-domain write-table access and this read does not reach across it: the surface
    composes the other columns from each owning module's own list route, the way the Member
    360 already composes its blocks, and `columns_this_module_cannot_answer` says which ones
    so a page cannot quietly render an empty cell as a fact.

    **This is a list, not a search.** MOD-014's standing gap records why there is no free-text
    search here: paragraph 4218 puts a permission-aware index with a mandatory query pre-filter
    in ENG-01, and a `LIKE` scan presented as search is a read path with no freshness contract
    and no pre-filter. The design's search field is therefore unanswerable by this build, and
    saying so is better than a box that scans.

    Masked like every other read in this module -- the gate's fields and the caller's class
    permissions both, as required arguments, because a read path that can be called without
    them is a read path somebody calls without them.
    """
    if lifecycle_state is not None and lifecycle_state not in lifecycle.MEMBER_STATES:
        raise InvalidRequest(f"unknown_lifecycle_state_{lifecycle_state}")
    if limit < 1 or limit > PEOPLE_PAGE:
        raise InvalidRequest("bad_limit")
    readable = visibility.readable_classes(frozenset(held_permissions))
    masks = _masks(masked_fields, readable)

    where = ["p.merge_status = 'active'"]
    args: list[Any] = []
    if lifecycle_state is not None:
        where.append("m.lifecycle_state = %s")
        args.append(lifecycle_state)
    if tag_key is not None:
        where.append(
            "EXISTS (SELECT 1 FROM plt01.ppl_tags t"
            " WHERE t.person_id = p.person_id AND t.tag_key = %s AND t.removed_at IS NULL)")
        args.append(tag_key)

    with tenant_scope(pool, tenant_id) as conn:
        # **The total is of the tenant, and the count is of the match.** The design's own
        # footer reads "Showing 1-50 of 18 matching · 4,812 total", and the difference is the
        # whole point: a filtered list that reports only its own length implies the records
        # that did not match do not exist.
        total = conn.execute(
            "SELECT count(*) FROM plt01.ppl_persons WHERE merge_status = 'active'"
        ).fetchone()
        matching = conn.execute(
            "SELECT count(*) FROM plt01.ppl_persons p"
            " LEFT JOIN plt01.ppl_member_profiles m ON m.person_id = p.person_id"
            f" WHERE {' AND '.join(where)}",
            tuple(args),
        ).fetchone()
        # **The sub-line ADM-MEM-05 draws**: "4,812 active · 312 expired · 68 frozen · all
        # locations". It is a count over the whole tenant, not over the page -- a surface that
        # summed the fifty rows it loaded would report the page as the business, which is the
        # same defect as summing a bounded list to get a month. One grouped query.
        #
        # **A person with no member profile is counted under `none`** rather than dropped, so
        # the figures add up to `total`: a lead who has never been sold anything is a person
        # this tenant has, and a sub-line whose parts did not sum would invite the reader to
        # look for the missing ones.
        by_state = conn.execute(
            "SELECT coalesce(m.lifecycle_state, 'none'), count(*)"
            " FROM plt01.ppl_persons p"
            " LEFT JOIN plt01.ppl_member_profiles m ON m.person_id = p.person_id"
            " WHERE p.merge_status = 'active'"
            " GROUP BY 1 ORDER BY 1"
        ).fetchall()
        rows = conn.execute(
            "SELECT p.person_id, p.legal_name, p.preferred_name, p.date_of_birth,"
            " m.lifecycle_state, m.member_number, m.joined_on"
            " FROM plt01.ppl_persons p"
            " LEFT JOIN plt01.ppl_member_profiles m ON m.person_id = p.person_id"
            f" WHERE {' AND '.join(where)}"
            # Ordered, because an unordered list makes the planner the author -- MOD-018's
            # `chart_for` finding, and a list a reader pages through needs a stable order.
            " ORDER BY coalesce(m.joined_on, p.created_at::date) DESC, p.person_id"
            " LIMIT %s",
            (*args, limit),
        ).fetchall()

    people = [
        visibility.apply_record(
            {
                "person_id": str(r[0]),
                "legal_name": r[1],
                "preferred_name": r[2],
                "date_of_birth": r[3].isoformat() if r[3] else None,
                "lifecycle_state": r[4],
                "member_number": r[5],
                "joined_on": r[6].isoformat() if r[6] else None,
            },
            masks,
        )
        for r in rows
    ]
    return {
        "people": people,
        "matching": int(matching[0]) if matching else 0,
        "total": int(total[0]) if total else 0,
        #: Per lifecycle state over the whole tenant, which is the design's own sub-line and
        #: the count beside each quick filter. Every key sums into `total`.
        "by_state": {str(r[0]): int(r[1]) for r in by_state},
        "limit": limit,
        #: Named rather than omitted. A column rendered empty reads as "this member has none".
        "columns_this_module_cannot_answer": {
            "plan": "membership.record.read (MOD-017)",
            "renews": "membership.record.read (MOD-017)",
            "balance": "finance.ledger.read (MOD-018)",
            "last_visit": "no per-person visit read exists in this build",
            "club": "no home-club concept exists in this build",
        },
        #: The design's search field. Unanswerable here, and why.
        "search_is_not_available_because":
            "paragraph 4218 puts a permission-aware search index with a mandatory query "
            "pre-filter in ENG-01, which is not built; a LIKE scan presented as search would "
            "be a read path with no freshness contract and no pre-filter",
    }


#: What a staff list may be bounded to. The same ceiling as the members list and for the same
#: reason: unbounded is a bulk export and a denial of service at once.
STAFF_PAGE = 200

#: The employment states `ppl_staff_profiles` admits.
#:
#: **ADM-STF-01 draws three chips -- Active, Invited, Left -- and only two of them are states
#: of this table.** `invited` is an invitation, and there is no invitation anywhere in this
#: build: no table, no token, no expiry, nothing that sends. A chip reading "Invited / 0" would
#: say that nobody has been invited rather than that nothing can invite anybody, which is the
#: confident wrong answer this repository keeps finding. `suspended` is the third real state and
#: the design has no chip for it, so it gets one.
STAFF_STATES = ("active", "suspended", "ended")


def list_staff(
    pool: Pool, tenant_id: str, *, masked_fields: tuple[str, ...],
    held_permissions: set[str], employment_state: str | None = None,
    location_id: str | None = None, limit: int = 50,
) -> dict[str, Any]:
    """ADM-STF-01's staff list -- the first reader `ppl_staff_profiles` has ever had.

    The table was written by MOD-014 with `upsert_staff_profile` and `end_staff_employment` and
    read by nothing: a staff profile could be created, ended and versioned, and the only way to
    find out what a tenant's team was consisted of knowing a person id already. That is this
    build's recurring "a writer with no reader" shape, now four times over, and the remedy is
    the same one `GET /brands` and `GET /memberships` took -- a route on the server rather than
    inference in the client.

    **The design names four columns and this module owns two of them.** NAME and CLUBS are
    partly here; ROLE is MOD-008's `iam.role_assignments` and LAST SEEN is MOD-007's
    `iam.sessions`, both on a plane this role holds nothing in -- `veyro_cp_app` has no
    privilege in `iam` at all, which is the separation MOD-007 exists to keep. So the surface
    composes them from each module's own read through each module's own gate, exactly as the
    Member 360 composes membership and money onto a person. `columns_this_module_cannot_answer`
    names them, because a column rendered empty reads as a fact about the person.

    **`location_id` is a filter, not a restriction.** The design says "a Club Manager sees only
    their own club's staff"; `permit` resolves against the tenant-wide default scope, so a
    narrower assignment covers nothing and nothing here derives a reader's own club. That is
    MOD-014's standing gap, and the response says so rather than letting a filter read as a
    boundary.

    Masked like every other read in this module -- the gate's fields and the caller's class
    permissions both, as required arguments.
    """
    if employment_state is not None and employment_state not in STAFF_STATES:
        raise InvalidRequest(f"unknown_employment_state_{employment_state}")
    if limit < 1 or limit > STAFF_PAGE:
        raise InvalidRequest("bad_limit")
    readable = visibility.readable_classes(frozenset(held_permissions))
    masks = _masks(masked_fields, readable)

    where = ["p.merge_status = 'active'"]
    args: list[Any] = []
    if employment_state is not None:
        where.append("s.employment_state = %s")
        args.append(employment_state)
    if location_id is not None:
        where.append("s.location_id = %s")
        args.append(location_id)

    with tenant_scope(pool, tenant_id) as conn:
        # The chips, over the whole tenant rather than over the page. A surface that counted
        # the rows it loaded would report the page as the team.
        by_state = conn.execute(
            "SELECT s.employment_state, count(*)"
            " FROM plt01.ppl_staff_profiles s"
            " JOIN plt01.ppl_persons p ON p.person_id = s.person_id"
            " WHERE p.merge_status = 'active' GROUP BY 1 ORDER BY 1"
        ).fetchall()
        matching = conn.execute(
            "SELECT count(*) FROM plt01.ppl_staff_profiles s"
            " JOIN plt01.ppl_persons p ON p.person_id = s.person_id"
            f" WHERE {' AND '.join(where)}",
            tuple(args),
        ).fetchone()
        rows = conn.execute(
            "SELECT s.person_id, p.legal_name, p.preferred_name, s.staff_profile_id,"
            " s.job_title, s.employment_state, s.started_on, s.ended_on, s.location_id,"
            " l.location_name, s.version, i.identity_id"
            " FROM plt01.ppl_staff_profiles s"
            " JOIN plt01.ppl_persons p ON p.person_id = s.person_id"
            " LEFT JOIN plt01.locations l ON l.location_id = s.location_id"
            " LEFT JOIN plt01.ppl_identity_links i ON i.person_id = s.person_id"
            f" WHERE {' AND '.join(where)}"
            # Ordered, because an unordered list makes the planner the author -- and a team
            # list a reader scans wants the people who are here first.
            #
            # **By what the state means, not by how it spells.** Alphabetically `active` <
            # `ended` < `suspended`, which would put the people who have left above the ones
            # who are suspended -- and a suspended employee is still on the team. The three
            # states have an order and it is not their collation.
            " ORDER BY CASE s.employment_state"
            "   WHEN 'active' THEN 0 WHEN 'suspended' THEN 1 ELSE 2 END,"
            " coalesce(s.started_on, '0001-01-01'::date) DESC, s.person_id"
            " LIMIT %s",
            (*args, limit),
        ).fetchall()

    staff = [
        visibility.apply_record(
            {
                "person_id": str(r[0]),
                "legal_name": r[1],
                "preferred_name": r[2],
                "staff_profile_id": str(r[3]),
                "job_title": r[4],
                "employment_state": r[5],
                "started_on": r[6].isoformat() if r[6] else None,
                "ended_on": r[7].isoformat() if r[7] else None,
                "location_id": str(r[8]) if r[8] else None,
                "location_name": r[9],
                "version": int(r[10]),
                # The handle the role and last-seen composition is made with. An opaque id
                # and nothing else -- and its presence is itself the fact ADM-STF-01 cares
                # about, because a staff profile with no identity link has no login to lose.
                "identity_id": str(r[11]) if r[11] else None,
            },
            masks,
        )
        for r in rows
    ]
    return {
        "staff": staff,
        "matching": int(matching[0]) if matching else 0,
        "total": sum(int(r[1]) for r in by_state),
        #: Per employment state over the whole tenant. Every key sums into `total`.
        "by_state": {str(r[0]): int(r[1]) for r in by_state},
        "limit": limit,
        "states": list(STAFF_STATES),
        #: Named rather than omitted, and each names the permission that answers it.
        "columns_this_module_cannot_answer": {
            "role": "authz.role.read (MOD-008): iam.role_assignments, another plane",
            "last_seen": "identity.identity.read (MOD-007): iam.sessions, another plane",
            "clubs_beyond_the_home_location":
                "authz.role.read (MOD-008): a staff profile carries one location and the "
                "scopes a person can actually reach are their role assignments'",
        },
        #: ADM-STF-01's third chip. There is no invitation in this build at all.
        "invited_is_not_a_state_here":
            "a staff invitation has no table, no token and no expiry in this build, and "
            "nothing sends one; ADM-STF-03 is unbuilt rather than empty",
        #: The design's warning box. Certifications are not recorded anywhere here.
        "certifications_are_not_recorded":
            "no table in this build holds a coach certification or its expiry, so the "
            "design's 30-day certification warning has nothing to read",
        #: The filter is a filter. Saying so is cheaper than a reader deriving a boundary.
        "the_location_filter_is_not_a_boundary":
            "permit resolves against the tenant-wide default scope, so a brand- or "
            "location-scoped role covers nothing here and nothing derives a reader's own "
            "club; this narrows the list and does not restrict who may read it",
    }


def read_staff_profile(pool: Pool, tenant_id: str, person_id: str) -> dict[str, Any]:
    """One staff profile, for ADM-STF-02's header -- the employment half and nothing else.

    No name and no masking, deliberately: the person is `GET /people/{id}`, which applies the
    gate's mask and this module's class mask and the guardianship check. A second read that
    returned a name under its own rules would be a second place the mask has to be right, which
    is how "computed but not applied" survived five modules.
    """
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT s.staff_profile_id, s.person_id, s.job_title, s.employment_state,"
            " s.started_on, s.ended_on, s.location_id, l.location_name, s.version,"
            " s.updated_at, i.identity_id"
            " FROM plt01.ppl_staff_profiles s"
            " LEFT JOIN plt01.locations l ON l.location_id = s.location_id"
            " LEFT JOIN plt01.ppl_identity_links i ON i.person_id = s.person_id"
            " WHERE s.person_id = %s",
            (person_id,),
        ).fetchone()
    if row is None:
        raise NotFound("staff_profile_not_found")
    return {
        "staff_profile_id": str(row[0]), "person_id": str(row[1]), "job_title": row[2],
        "employment_state": row[3],
        "started_on": row[4].isoformat() if row[4] else None,
        "ended_on": row[5].isoformat() if row[5] else None,
        "location_id": str(row[6]) if row[6] else None, "location_name": row[7],
        "version": int(row[8]), "updated_at": row[9].isoformat(),
        "identity_id": str(row[10]) if row[10] else None,
        #: A staff profile carries one location. What a person can actually reach is their
        #: role assignments' scopes, which is MOD-008's read and the design's CLUBS row.
        "the_home_location_is_not_the_scope":
            "this is where they work; what they may reach is authz.role.read's assignment "
            "scopes",
    }


def update_person(
    pool: Pool, tenant_id: str, person_id: str, *, expected_version: int, actor_id: str,
    correlation_id: str, legal_name: str | None = None, preferred_name: str | None = None,
    date_of_birth: date | None = None, at: datetime | None = None,
) -> dict[str, Any]:
    """UpdateProfile's person half, under optimistic concurrency.

    The version the caller read is sent back and a mismatch is refused. Two front-desk staff
    editing one record is the ordinary case, and last-write-wins discards whichever finished
    first -- which is nobody's intent and leaves no trace.
    """
    moment = at or _now()
    if date_of_birth is not None and date_of_birth > moment.date():
        raise InvalidRequest("a_birth_date_is_in_the_past")
    changed: list[str] = []
    with tenant_scope(pool, tenant_id) as conn:
        current = _person_row(conn, person_id)
        _check_version(expected_version, int(current["version"]))
        if current["merge_status"] != "active":
            raise Conflict("this_person_has_been_merged_away")
        values: dict[str, Any] = {}
        if legal_name is not None and legal_name.strip() != current["legal_name"]:
            if not legal_name.strip():
                raise InvalidRequest("a_person_has_a_legal_name")
            values["legal_name"] = legal_name.strip()
            changed.append("legal_name")
        if preferred_name is not None and preferred_name != current["preferred_name"]:
            values["preferred_name"] = preferred_name or None
            changed.append("preferred_name")
        if date_of_birth is not None and date_of_birth != current["date_of_birth"]:
            values["date_of_birth"] = date_of_birth
            changed.append("date_of_birth")
        if not values:
            raise InvalidRequest("this_update_changes_nothing")
        assignments = ", ".join(f"{name} = %s" for name in values)
        try:
            updated = conn.execute(
                f"UPDATE plt01.ppl_persons SET {assignments}, version = version + 1,"
                f" updated_at = now() WHERE person_id = %s AND version = %s",
                (*values.values(), person_id, expected_version),
            ).rowcount
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        # The guard is on the version as well as the id, and the row count is checked: a second
        # writer between the read above and this write would otherwise have its change silently
        # overwritten by ours, which is the lost update the version exists to stop.
        if updated == 0:
            raise Conflict("this_person_changed_while_being_updated")
        _append(conn, tenant_id, "profile.updated", person_id,
                {"person_id": person_id, "changed_fields": sorted(changed)},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"person_id": person_id, "version": expected_version + 1,
            "changed_fields": sorted(changed)}


def link_identity(
    pool: Pool, tenant_id: str, person_id: str, *, identity_id: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """LinkIdentity: record which MOD-007 identity signs in as this person.

    **Unverifiable from here, and that is the plane separation working.** `veyro_cp_app` holds
    nothing in `iam`, so this module cannot confirm the identity exists, belongs to this tenant
    or is not already somebody else's. The unique index enforces the last of those *within this
    table*, which is what stops one login resolving to two member records; the first two are the
    gap, and a caller supplying a wrong uuid produces a link that resolves to nobody.
    """
    with tenant_scope(pool, tenant_id) as conn:
        _person_row(conn, person_id)
        try:
            conn.execute(
                """
                INSERT INTO plt01.ppl_identity_links
                    (tenant_id, person_id, identity_id, linked_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (tenant_id, person_id, identity_id, actor_id, correlation_id),
            )
        except errors.UniqueViolation:
            raise Conflict("this_identity_is_already_linked_to_a_person") from None
    return {"person_id": person_id, "identity_id": identity_id, "linked": True}


# ------------------------------------------------------------------------------ profiles

def person_of_identity(pool: Pool, tenant_id: str, *, identity_id: str) -> str | None:
    """Which person this MOD-007 identity signs in as, if the link has been recorded.

    Used to decide whether a caller is reading their own record or their own dependent's.
    `None` is the ordinary answer for a staff session: staff hold permissions and do not need
    to be anybody in particular.
    """
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT person_id FROM plt01.ppl_identity_links WHERE identity_id = %s",
            (identity_id,),
        ).fetchone()
        if row is None:
            return None
        # **Follow the merge pointer.** `ppl_identity_links` is insert-only and a merge leaves
        # it pointing at the record that was merged away, so without this walk a member whose
        # duplicate was merged resolved to the dead id for ever: their own app read the stale
        # record, and a guardian whose duplicate was merged was silently refused their own
        # dependent. "Readers follow the pointer" was the stated design and no reader did it.
        return _survivor_of(conn, str(row[0]))


def people_of_identities(
    pool: Pool, tenant_id: str, *, identity_ids: list[str],
) -> dict[str, Any]:
    """Which person each of these MOD-007 identities signs in as. The batch of the one above.

    **`person_of_identity` had no batch and the surfaces that need one are the ones that
    render an actor.** A till's `opened_by`, a shift's `closed_by`, an attendance's
    `recorded_by` are all identities, and a screen showing "handed over from 7f3a1c2e" is a
    screen nobody can read -- so the composition is identity, then person, then
    `GET /people/names`, and asking one at a time is the round-trip problem the staff list
    already paid for.

    **An identity with no link is absent from the answer rather than present with a null**,
    because the two facts a caller acts on are different: a staff identity that is nobody in
    particular is the ordinary case, and a surface has to say "a staff member" rather than
    draw a blank name. The merge pointer is followed for the reason the single read follows
    it: `ppl_identity_links` is insert-only, so a merge leaves it naming the record that was
    merged away.
    """
    if not identity_ids:
        return {"count": 0, "people": []}
    if len(identity_ids) > IDENTITY_LINK_PAGE:
        raise InvalidRequest("too_many_identities")
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT identity_id, person_id FROM plt01.ppl_identity_links"
            " WHERE identity_id = ANY(%s)",
            (list(identity_ids),),
        ).fetchall()
        out = [{"identity_id": str(r[0]),
                "person_id": _survivor_of(conn, str(r[1]))} for r in rows]
    return {
        "count": len(out),
        "people": sorted(out, key=lambda row: row["identity_id"]),
        "an_unlinked_identity_is_absent": (
            "an identity with no person is left out rather than returned with a null: staff "
            "hold permissions and do not have to be anybody in particular, and a surface "
            "says so rather than drawing an empty name"),
    }


def upsert_tenant_profile(
    pool: Pool, tenant_id: str, person_id: str, *, actor_id: str, correlation_id: str,
    expected_version: int | None = None, brand_id: str | None = None,
    location_id: str | None = None, acquisition_source: str | None = None,
    preferred_language: str | None = None, notes_internal: str | None = None,
) -> dict[str, Any]:
    """The tenant's own view of a person. Created on first write, versioned after that."""
    with tenant_scope(pool, tenant_id) as conn:
        _person_row(conn, person_id)
        existing = conn.execute(
            "SELECT profile_id, version FROM plt01.ppl_tenant_profiles WHERE person_id = %s",
            (person_id,),
        ).fetchone()
        if existing is None:
            try:
                row = conn.execute(
                    """
                    INSERT INTO plt01.ppl_tenant_profiles
                        (tenant_id, person_id, brand_id, location_id, acquisition_source,
                         preferred_language, notes_internal, updated_by, correlation_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING profile_id, version
                    """,
                    (tenant_id, person_id, brand_id, location_id, acquisition_source,
                     preferred_language, notes_internal, actor_id, correlation_id),
                ).fetchone()
            except errors.CheckViolation as e:
                raise InvalidRequest(_check_name(e)) from None
            except errors.ForeignKeyViolation:
                raise NotFound("brand_or_location_not_found") from None
            assert row is not None
            created = True
            profile_id, version = str(row[0]), int(row[1])
        else:
            if expected_version is None:
                raise InvalidRequest("this_profile_exists_so_send_the_version_you_read")
            _check_version(expected_version, int(existing[1]))
            try:
                updated = conn.execute(
                    """
                    UPDATE plt01.ppl_tenant_profiles
                    SET brand_id = %s, location_id = %s, acquisition_source = %s,
                        preferred_language = %s, notes_internal = %s, version = version + 1,
                        updated_at = now(), updated_by = %s, correlation_id = %s
                    WHERE person_id = %s AND version = %s
                    """,
                    (brand_id, location_id, acquisition_source, preferred_language,
                     notes_internal, actor_id, correlation_id, person_id, expected_version),
                ).rowcount
            except errors.CheckViolation as e:
                raise InvalidRequest(_check_name(e)) from None
            except errors.ForeignKeyViolation:
                raise NotFound("brand_or_location_not_found") from None
            if updated == 0:
                raise Conflict("this_profile_changed_while_being_updated")
            created = False
            profile_id, version = str(existing[0]), expected_version + 1
        _append(conn, tenant_id, "profile.updated", person_id,
                {"person_id": person_id, "changed_fields": ["tenant_profile"]},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"profile_id": profile_id, "person_id": person_id, "version": version,
            "created": created}


def create_member_profile(
    pool: Pool, tenant_id: str, person_id: str, *, actor_id: str, correlation_id: str,
    member_number: str | None = None, joined_on: date | None = None,
    lifecycle_state: str = "lead",
) -> dict[str, Any]:
    """CreateMemberProfile. The person's standing as a member, which starts as a lead."""
    if lifecycle_state not in lifecycle.MEMBER_STATES:
        raise InvalidRequest(f"unknown_lifecycle_state_{lifecycle_state}")
    with tenant_scope(pool, tenant_id) as conn:
        _person_row(conn, person_id)
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.ppl_member_profiles
                    (tenant_id, person_id, lifecycle_state, member_number, joined_on,
                     updated_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING member_profile_id, version
                """,
                (tenant_id, person_id, lifecycle_state, member_number, joined_on, actor_id,
                 correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_person_already_has_a_member_profile_or_number") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        _append(conn, tenant_id, "member.lifecycle.changed", person_id,
                {"person_id": person_id, "from_state": "none", "to_state": lifecycle_state},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"member_profile_id": str(row[0]), "person_id": person_id,
            "lifecycle_state": lifecycle_state, "version": int(row[1])}


def change_member_lifecycle(
    pool: Pool, tenant_id: str, person_id: str, *, to_state: str, expected_version: int,
    actor_id: str, correlation_id: str, reason: str | None = None,
) -> dict[str, Any]:
    """Move a member through the lifecycle, refusing a move the machine does not admit."""
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT lifecycle_state, version FROM plt01.ppl_member_profiles"
            " WHERE person_id = %s",
            (person_id,),
        ).fetchone()
        if row is None:
            raise NotFound("member_profile_not_found")
        current = str(row[0])
        _check_version(expected_version, int(row[1]))
        try:
            lifecycle.check_member_transition(current, to_state)
        except lifecycle.LifecycleError as e:
            raise Conflict(str(e)) from None
        if lifecycle.reason_required(to_state) and not (reason or "").strip():
            raise InvalidRequest(f"moving_a_member_to_{to_state}_states_a_reason")
        updated = conn.execute(
            "UPDATE plt01.ppl_member_profiles SET lifecycle_state = %s,"
            " state_changed_at = now(), state_reason = %s, version = version + 1,"
            " updated_at = now(), updated_by = %s, correlation_id = %s"
            " WHERE person_id = %s AND version = %s",
            (to_state, (reason or None), actor_id, correlation_id, person_id,
             expected_version),
        ).rowcount
        if updated == 0:
            raise Conflict("this_member_profile_changed_while_being_updated")
        _append(conn, tenant_id, "member.lifecycle.changed", person_id,
                {"person_id": person_id, "from_state": current, "to_state": to_state},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"person_id": person_id, "from_state": current, "to_state": to_state,
            "version": expected_version + 1}


def upsert_staff_profile(
    pool: Pool, tenant_id: str, person_id: str, *, actor_id: str, correlation_id: str,
    job_title: str | None = None, location_id: str | None = None,
    started_on: date | None = None,
) -> dict[str, Any]:
    with tenant_scope(pool, tenant_id) as conn:
        _person_row(conn, person_id)
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.ppl_staff_profiles
                    (tenant_id, person_id, job_title, location_id, started_on, updated_by,
                     correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING staff_profile_id, version
                """,
                (tenant_id, person_id, job_title, location_id, started_on, actor_id,
                 correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            # **It is called `upsert` and it only ever inserted.** A second call raised, so a
            # job title or a location could never be changed despite the UPDATE grant and the
            # `version` column. Found by review as a functional gap that was not in the
            # known-gaps list either.
            try:
                updated = conn.execute(
                    "UPDATE plt01.ppl_staff_profiles SET job_title = %s, location_id = %s,"
                    " started_on = coalesce(%s, started_on), version = version + 1,"
                    " updated_at = now(), updated_by = %s, correlation_id = %s"
                    " WHERE person_id = %s RETURNING staff_profile_id, version",
                    (job_title, location_id, started_on, actor_id, correlation_id, person_id),
                ).fetchone()
            except errors.ForeignKeyViolation:
                raise NotFound("location_not_found") from None
            except errors.CheckViolation as e:
                raise InvalidRequest(_check_name(e)) from None
            assert updated is not None
            return {"staff_profile_id": str(updated[0]), "person_id": person_id,
                    "version": int(updated[1]), "created": False}
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        except errors.ForeignKeyViolation:
            raise NotFound("location_not_found") from None
        assert row is not None
    return {"staff_profile_id": str(row[0]), "person_id": person_id, "version": int(row[1]),
            "created": True}


def end_staff_employment(
    pool: Pool, tenant_id: str, person_id: str, *, expected_version: int, ended_on: date,
    actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Employment ends once. Re-hiring is a new period, not an un-ending of this one."""
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT employment_state, version FROM plt01.ppl_staff_profiles"
            " WHERE person_id = %s",
            (person_id,),
        ).fetchone()
        if row is None:
            raise NotFound("staff_profile_not_found")
        _check_version(expected_version, int(row[1]))
        try:
            lifecycle.check_staff_transition(str(row[0]), "ended")
        except lifecycle.LifecycleError as e:
            raise Conflict(str(e)) from None
        try:
            updated = conn.execute(
                "UPDATE plt01.ppl_staff_profiles SET employment_state = 'ended',"
                " ended_on = %s, version = version + 1, updated_at = now(), updated_by = %s,"
                " correlation_id = %s WHERE person_id = %s AND version = %s",
                (ended_on, actor_id, correlation_id, person_id, expected_version),
            ).rowcount
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        if updated == 0:
            raise Conflict("this_staff_profile_changed_while_being_updated")
    return {"person_id": person_id, "employment_state": "ended",
            "version": expected_version + 1}


# ------------------------------------------------------------------------ contact points

def add_contact_point(
    pool: Pool, tenant_id: str, person_id: str, *, kind: str, value: str, actor_id: str,
    correlation_id: str, is_primary: bool = False,
) -> dict[str, Any]:
    normalized = normalize_contact(kind, value)
    with tenant_scope(pool, tenant_id) as conn:
        _person_row(conn, person_id)
        if is_primary:
            # Demote the current primary first: the partial unique index would otherwise refuse
            # the insert, and "you already have a primary email" is not a useful answer to
            # "make this the primary email".
            conn.execute(
                "UPDATE plt01.ppl_contact_points SET is_primary = false, updated_at = now()"
                " WHERE person_id = %s AND kind = %s AND is_primary",
                (person_id, kind),
            )
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.ppl_contact_points
                    (tenant_id, person_id, kind, value_raw, value_normalized, is_primary,
                     recorded_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING contact_point_id
                """,
                (tenant_id, person_id, kind, value.strip(), normalized, is_primary, actor_id,
                 correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_person_already_has_this_contact_point") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        _append(conn, tenant_id, "profile.updated", person_id,
                {"person_id": person_id, "changed_fields": [f"contact_{kind}"]},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"contact_point_id": str(row[0]), "person_id": person_id, "kind": kind,
            "is_primary": is_primary}


def verify_contact_point(
    pool: Pool, tenant_id: str, contact_point_id: str, *, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Mark a contact point as verified, which is what `dedup` weights most heavily.

    **This records a verification; it does not perform one.** Nothing here sends a code or reads
    a reply -- MOD-013 cannot send and there is no provider. So the row says a named actor
    asserted it at a time, which is the same shape MOD-012's `validated` install state takes and
    for the same reason: a state reading "verified" with nothing having verified anything is the
    fabricated-evidence shape this build has been bitten by five times.

    **And the row now actually carries the name.** The first version wrote only `verified_at`,
    returned `asserted_by` to the caller and said in this very docstring that the row recorded
    it -- with no second record anywhere, because MOD-008 audits denials and `veyro_cp_app`
    holds nothing in `iam`. `verified_at` is the signal `dedup.WEIGHTS` scores highest, so it is
    the evidence an operator destroys a record on. Found by review.
    """
    with tenant_scope(pool, tenant_id) as conn:
        updated = conn.execute(
            "UPDATE plt01.ppl_contact_points SET verified_at = now(), verified_by = %s,"
            " verify_correlation_id = %s, updated_at = now()"
            " WHERE contact_point_id = %s AND verified_at IS NULL",
            (actor_id, correlation_id, contact_point_id),
        ).rowcount
        if updated == 0:
            raise Conflict("this_contact_point_is_unknown_or_already_verified")
    return {"contact_point_id": contact_point_id, "verified": True, "asserted_by": actor_id}


# ------------------------------------------------------------------------ relationships

def add_relationship(
    pool: Pool, tenant_id: str, *, kind: str, from_person_id: str, to_person_id: str,
    actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """AddRelationship, and publish `relationship.created`.

    Both people are checked to exist in this tenant, which the foreign keys enforce anyway --
    the explicit read is so the refusal is a 404 naming which one, rather than a constraint name.
    """
    with tenant_scope(pool, tenant_id) as conn:
        _person_row(conn, from_person_id)
        _person_row(conn, to_person_id)
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.ppl_relationships
                    (tenant_id, kind, from_person_id, to_person_id, created_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING relationship_id, valid_from
                """,
                (tenant_id, kind, from_person_id, to_person_id, actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_relationship_already_exists") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        _append(conn, tenant_id, "relationship.created", from_person_id,
                {"from_person_id": from_person_id, "to_person_id": to_person_id, "kind": kind},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"relationship_id": str(row[0]), "kind": kind,
            "valid_from": row[1].isoformat()}


def end_relationship(
    pool: Pool, tenant_id: str, relationship_id: str, *, reason: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """End a relationship. It is not deleted and it is not re-pointed.

    `from_person_id`, `to_person_id` and `kind` carry no UPDATE grant, so "who was this
    member's coach in March" stays answerable -- which is the whole reason the relationship is
    time-bounded rather than a row somebody removes.
    """
    if not reason.strip():
        raise InvalidRequest("ending_a_relationship_states_a_reason")
    with tenant_scope(pool, tenant_id) as conn:
        # **Who ended it, which the first version took as an argument and used for nothing.**
        # Ending a `guardian_dependent` edge is the act that removes a guardian's read access to
        # a minor's record, and there is no second record of it anywhere. Found by review.
        updated = conn.execute(
            "UPDATE plt01.ppl_relationships SET valid_to = now(), ended_reason = %s,"
            " ended_by = %s, end_correlation_id = %s"
            " WHERE relationship_id = %s AND valid_to IS NULL",
            (reason, actor_id, correlation_id, relationship_id),
        ).rowcount
        if updated == 0:
            raise Conflict("this_relationship_is_unknown_or_already_ended")
    return {"relationship_id": relationship_id, "ended": True, "ended_by": actor_id}


# --------------------------------------------------------------------------------- notes

def record_note(
    pool: Pool, tenant_id: str, person_id: str, *, body: str, actor_id: str,
    correlation_id: str, note_class: str = "general",
) -> dict[str, Any]:
    """RecordMemberNote. Insert-only, and classified so the masking knows who may read it."""
    if note_class not in NOTE_CLASSES:
        raise InvalidRequest(f"unknown_note_class_{note_class}")
    if not body.strip():
        raise InvalidRequest("a_note_has_a_body")
    with tenant_scope(pool, tenant_id) as conn:
        _person_row(conn, person_id)
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.ppl_person_notes
                    (tenant_id, person_id, note_class, body, recorded_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING note_id, recorded_at
                """,
                (tenant_id, person_id, note_class, body.strip(), actor_id, correlation_id),
            ).fetchone()
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
    return {"note_id": str(row[0]), "person_id": person_id, "note_class": note_class,
            "recorded_at": row[1].isoformat()}


def withdraw_note(
    pool: Pool, tenant_id: str, note_id: str, *, reason: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Withdraw a note. The body stays; the withdrawal is recorded beside it."""
    if not reason.strip():
        raise InvalidRequest("withdrawing_a_note_states_a_reason")
    with tenant_scope(pool, tenant_id) as conn:
        try:
            updated = conn.execute(
                "UPDATE plt01.ppl_person_notes SET withdrawn_at = now(), withdrawn_by = %s,"
                " withdraw_reason = %s WHERE note_id = %s AND withdrawn_at IS NULL",
                (actor_id, reason, note_id),
            ).rowcount
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        if updated == 0:
            raise Conflict("this_note_is_unknown_or_already_withdrawn")
    return {"note_id": note_id, "withdrawn": True}


def list_notes(
    pool: Pool, tenant_id: str, person_id: str, *, masked_fields: tuple[str, ...],
    held_permissions: set[str], actor_person_id: str | None = None,
    include_withdrawn: bool = False, limit: int = 50,
) -> list[dict[str, Any]]:
    """A person's notes, with the body of each class the caller may not read replaced.

    **The record survives and only its content goes**, which is `visibility.redact_classified`'s
    reasoning: telling a coach that a member has no health notes when they have three is worse
    than telling them there are three they cannot read.

    `masked_fields` is **required**, and the guardianship check runs here too. The first version
    had neither: a reviewer read a minor's notes with the credential `GET /people/{id}` had just
    refused, and a MASK policy naming `body` applied through the 360 and not through this route
    -- a control a caller turns off by choosing an endpoint. A control consulted on one path and
    not its sibling is this repository's most frequent finding, and this is the fourth module it
    has appeared in.
    """
    readable = visibility.readable_classes(frozenset(held_permissions))
    masks = _masks(masked_fields, readable)
    sql = ["SELECT note_id, note_class, body, recorded_at, recorded_by, withdrawn_at,"
           " withdraw_reason FROM plt01.ppl_person_notes WHERE person_id = %s"]
    args: list[Any] = [person_id]
    if not include_withdrawn:
        sql.append(" AND withdrawn_at IS NULL")
    sql.append(" ORDER BY recorded_at DESC LIMIT %s")
    args.append(max(1, min(limit, 500)))
    with tenant_scope(pool, tenant_id) as conn:
        _require_guardianship(conn, _person_row(conn, person_id), held_permissions,
                              actor_person_id)
        rows = conn.execute("".join(sql), tuple(args)).fetchall()
    records = [{"note_id": str(r[0]), "note_class": str(r[1]), "body": r[2],
                "recorded_at": r[3].isoformat(), "recorded_by": str(r[4]),
                "withdrawn_at": r[5].isoformat() if r[5] else None,
                "withdraw_reason": r[6],
                # `visibility` works in MOD-008's five classes and a note's class is the
                # product's three, so the mapping is here and stated: a `general` note rides
                # with the profile read, a `health` one needs the health permission (unreachable
                # in this build, deliberately), and a `sensitive` one -- what staff write about
                # a person rather than about their body -- needs the identity permission, which
                # is financial class and so wants a stepped-up session.
                "visibility_class": NOTE_VISIBILITY[str(r[1])]} for r in rows]
    redacted = visibility.redact_classified(
        records, class_field="visibility_class", body_fields=("body",), readable=readable)
    return [visibility.apply_record(r, masks) for r in redacted]


# ------------------------------------------------------------------- tags and custom fields

def create_tag(
    pool: Pool, tenant_id: str, *, tag_key: str, display_name: str, actor_id: str,
    correlation_id: str, is_internal: bool = False,
) -> dict[str, Any]:
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.ppl_tags
                    (tenant_id, tag_key, display_name, is_internal, created_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING tag_id
                """,
                (tenant_id, tag_key, display_name, is_internal, actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_tag_key_already_exists") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
    return {"tag_id": str(row[0]), "tag_key": tag_key}


def apply_tag(
    pool: Pool, tenant_id: str, person_id: str, *, tag_id: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Apply a tag, or re-apply one that was removed, and say which happened.

    **The first version reported success for a write it had not made.** The row is keyed on
    (tenant, person, tag), so `DO NOTHING` against a *removed* row left the tag off the person
    while the response said `applied: True` -- a removed tag could never be re-applied, and the
    caller was told otherwise. MOD-010's un-reactivatable subscription, whose error said the
    opposite of what was true. Found by review.

    Re-applying rewrites the attribution, because there is one row per pairing for ever and
    attributing it to the person who applied it the first time would be the wrong record. That
    costs the first application's attribution and is the lesser loss; the migration says so.
    """
    with tenant_scope(pool, tenant_id) as conn:
        _person_row(conn, person_id)
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.ppl_person_tags
                    (tenant_id, person_id, tag_id, applied_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, person_id, tag_id) DO UPDATE
                SET applied_at = now(), applied_by = EXCLUDED.applied_by,
                    correlation_id = EXCLUDED.correlation_id,
                    removed_at = NULL, removed_by = NULL
                RETURNING (xmax <> 0) AS was_there_already
                """,
                (tenant_id, person_id, tag_id, actor_id, correlation_id),
            ).fetchone()
        except errors.ForeignKeyViolation:
            raise NotFound("tag_not_found") from None
        assert row is not None
    return {"person_id": person_id, "tag_id": tag_id, "applied": True,
            "reapplied": bool(row[0])}


def remove_tag(
    pool: Pool, tenant_id: str, person_id: str, *, tag_id: str, actor_id: str,
) -> dict[str, Any]:
    with tenant_scope(pool, tenant_id) as conn:
        updated = conn.execute(
            "UPDATE plt01.ppl_person_tags SET removed_at = now(), removed_by = %s"
            " WHERE person_id = %s AND tag_id = %s AND removed_at IS NULL",
            (actor_id, person_id, tag_id),
        ).rowcount
        if updated == 0:
            raise Conflict("this_tag_is_not_applied_to_this_person")
    return {"person_id": person_id, "tag_id": tag_id, "removed": True}


def define_custom_field(
    pool: Pool, tenant_id: str, *, field_key: str, display_name: str, value_type: str,
    actor_id: str, correlation_id: str, sensitivity: str = "none", is_required: bool = False,
    options: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Declare a custom field. The type and the sensitivity are final once written.

    Neither carries an UPDATE grant: re-typing a field leaves unparseable values readable, and
    re-marking one `none` unmasks in bulk what was collected as health data. Retiring it and
    declaring a new one is the path.
    """
    option_values = tuple(str(o["value"]) for o in (options or []))
    definition = fields.Definition(
        field_key=field_key, display_name=display_name, value_type=value_type,
        sensitivity=sensitivity, is_required=is_required, options=option_values)
    try:
        fields.check_definition(definition)
    except fields.FieldError as e:
        raise InvalidRequest(str(e)) from None
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.ppl_custom_field_defs
                    (tenant_id, field_key, display_name, value_type, sensitivity, is_required,
                     created_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING field_id
                """,
                (tenant_id, field_key, display_name, value_type, sensitivity, is_required,
                 actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_field_key_already_exists") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        field_id = str(row[0])
        for option in options or []:
            # Wrapped, because this was the one INSERT in the module whose CheckViolation
            # reached the caller as a 500: a blank option display name is a 422.
            try:
                conn.execute(
                    "INSERT INTO plt01.ppl_custom_field_options"
                    " (tenant_id, field_id, option_value, display_name)"
                    " VALUES (%s, %s, %s, %s)",
                    (tenant_id, field_id, option["value"],
                     option.get("display_name") or option["value"]),
                )
            except errors.CheckViolation as e:
                raise InvalidRequest(_check_name(e)) from None
    return {"field_id": field_id, "field_key": field_key, "value_type": value_type,
            "sensitivity": sensitivity}


def set_custom_field_value(
    pool: Pool, tenant_id: str, person_id: str, *, field_key: str, value: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Set a value, refused unless it parses as the definition's declared type."""
    with tenant_scope(pool, tenant_id) as conn:
        _person_row(conn, person_id)
        definition = _field_definition(conn, field_key)
        try:
            stored = fields.normalize_value(definition[1], value)
        except fields.FieldError as e:
            raise InvalidRequest(str(e)) from None
        conn.execute(
            """
            INSERT INTO plt01.ppl_custom_field_values
                (tenant_id, person_id, field_id, value_text, updated_by, correlation_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, person_id, field_id)
            DO UPDATE SET value_text = EXCLUDED.value_text, updated_at = now(),
                          updated_by = EXCLUDED.updated_by,
                          correlation_id = EXCLUDED.correlation_id
            """,
            (tenant_id, person_id, definition[0], stored, actor_id, correlation_id),
        )
    return {"person_id": person_id, "field_key": field_key, "value": stored}


# -------------------------------------------------------------------- duplicates and merge

def find_duplicates(
    pool: Pool, tenant_id: str, person_id: str, *, actor_id: str, correlation_id: str,
    store: bool = True,
) -> list[dict[str, Any]]:
    """Score this person against the people who share a contact value, name or birth date.

    **Candidates are drawn by an exact signal first, then scored.** A scan of every person in the
    tenant scored pairwise is O(n^2) and the module is specified against 450,000 profiles; what
    this does is use the indexes to find the small set that shares something, which is also the
    only set that could score above the threshold given no signal here is fuzzy.
    """
    with tenant_scope(pool, tenant_id) as conn:
        subject = _signals(conn, person_id)
        others = _candidate_signals(conn, subject)
        scored = [dedup.compare(subject, other) for other in others]
        worth = dedup.rank([c for c in scored if dedup.worth_reviewing(c)])
        # **A decided pair stays decided.** The partial unique index only covers `status =
        # 'open'`, so the upsert happily inserted a second row beside a `dismissed` one and the
        # next run put the pair an operator had just rejected straight back in the queue --
        # directly against `dismiss_duplicate_candidate`'s own docstring, and the shape
        # `REVIEW_THRESHOLD`'s comment names: an unread queue is worse than none because it
        # looks like the control is running. Found by review.
        decided = _decided_pairs(conn, [c.ordered for c in worth])
        fresh = [c for c in worth if c.ordered not in decided]
        if store:
            for candidate in fresh:
                lower, higher = candidate.ordered
                conn.execute(
                    """
                    INSERT INTO plt01.ppl_duplicate_candidates
                        (tenant_id, lower_person_id, higher_person_id, score, signals,
                         correlation_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (tenant_id, lower_person_id, higher_person_id)
                        WHERE status = 'open'
                    DO NOTHING
                    """,
                    (tenant_id, lower, higher, candidate.score, list(candidate.signals),
                     correlation_id),
                )
    return [{"person_id": c.person_id, "other_person_id": c.other_person_id,
             "score": c.score, "signals": list(c.signals)} for c in fresh]


#: What a duplicate candidate's status can be. Validated rather than passed through, so an
#: unknown value is a 422 instead of an empty list that reads as "no candidates".
CANDIDATE_STATUSES = ("open", "merged", "dismissed")


def list_duplicate_candidates(
    pool: Pool, tenant_id: str, *, status: str = "open", limit: int = 50,
) -> list[dict[str, Any]]:
    if status not in CANDIDATE_STATUSES:
        raise InvalidRequest(f"unknown_candidate_status_{status}")
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT candidate_id, lower_person_id, higher_person_id, score, signals, status,"
            " detected_at, decided_at, decision_reason FROM plt01.ppl_duplicate_candidates"
            " WHERE status = %s ORDER BY score DESC, detected_at LIMIT %s",
            (status, max(1, min(limit, 500))),
        ).fetchall()
    return [{"candidate_id": str(r[0]), "lower_person_id": str(r[1]),
             "higher_person_id": str(r[2]), "score": int(r[3]), "signals": list(r[4]),
             "status": r[5], "detected_at": r[6].isoformat(),
             "decided_at": r[7].isoformat() if r[7] else None,
             "decision_reason": r[8]} for r in rows]


def dismiss_duplicate_candidate(
    pool: Pool, tenant_id: str, candidate_id: str, *, reason: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """These are two different people. Recorded, so the detector's queue does not re-raise it."""
    if not reason.strip():
        raise InvalidRequest("dismissing_a_candidate_states_a_reason")
    with tenant_scope(pool, tenant_id) as conn:
        try:
            updated = conn.execute(
                "UPDATE plt01.ppl_duplicate_candidates SET status = 'dismissed',"
                " decided_at = now(), decided_by = %s, decision_reason = %s"
                " WHERE candidate_id = %s AND status = 'open'",
                (actor_id, reason, candidate_id),
            ).rowcount
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        if updated == 0:
            raise Conflict("this_candidate_is_unknown_or_already_decided")
    return {"candidate_id": candidate_id, "status": "dismissed"}


def plan_merge(pool: Pool, tenant_id: str, *, source_person_id: str,
               target_person_id: str) -> dict[str, Any]:
    """What a merge of these two would move, and what it would leave behind.

    A separate read so an operator sees the size and the retentions **before** agreeing. The
    retentions are the part that surprises people: two member profiles do not combine.
    """
    with tenant_scope(pool, tenant_id) as conn:
        source = _person_row(conn, source_person_id)
        target = _person_row(conn, target_person_id)
        plan = _merge_plan(conn, source_person_id, target_person_id)
    return {"source_person_id": source_person_id, "target_person_id": target_person_id,
            "source_status": source["merge_status"], "target_status": target["merge_status"],
            "contact_points": plan.contact_points, "relationships": plan.relationships,
            "notes": plan.notes, "tags": plan.tags, "custom_fields": plan.custom_fields,
            "retained": list(plan.retained)}


def merge_persons(
    pool: Pool, tenant_id: str, *, source_person_id: str, target_person_id: str, reason: str,
    actor_id: str, correlation_id: str, candidate_id: str | None = None,
) -> dict[str, Any]:
    """MergePerson. Reviewable, reversible and audited -- paragraph 10200.

    **Nothing is deleted.** The source keeps its row pointing at the target, because every other
    module references it by id and paragraph 1300 forbids this module writing their tables. What
    moves is what this module owns: contact points, live relationships, notes, tags and custom
    field values that the target does not already have.
    """
    with tenant_scope(pool, tenant_id) as conn:
        source = _person_row(conn, source_person_id)
        target = _person_row(conn, target_person_id)
        try:
            merge.check_merge(
                source_person_id=source_person_id, target_person_id=target_person_id,
                source_status=str(source["merge_status"]),
                target_status=str(target["merge_status"]),
                source_has_identity_link=_has_identity_link(conn, source_person_id),
                target_has_identity_link=_has_identity_link(conn, target_person_id),
                reason=reason)
        except merge.MergeError as e:
            raise Conflict(str(e)) from None
        plan = _merge_plan(conn, source_person_id, target_person_id)
        moved = _perform_merge(conn, tenant_id, source_person_id, target_person_id,
                               actor_id=actor_id, correlation_id=correlation_id)
        conn.execute(
            "UPDATE plt01.ppl_persons SET merge_status = 'merged',"
            " merged_into_person_id = %s, merged_at = now(), version = version + 1,"
            " updated_at = now() WHERE person_id = %s AND merge_status = 'active'",
            (target_person_id, source_person_id),
        )
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.ppl_merges
                    (tenant_id, source_person_id, target_person_id, reason,
                     moved_contact_points, moved_relationships, moved_notes, moved_tags,
                     moved_custom_fields, merged_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING merge_id
                """,
                (tenant_id, source_person_id, target_person_id, reason,
                 moved["contact_points"], moved["relationships"], moved["notes"],
                 moved["tags"], moved["custom_fields"], actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_person_has_already_been_merged") from None
        assert row is not None
        if candidate_id is not None:
            conn.execute(
                "UPDATE plt01.ppl_duplicate_candidates SET status = 'merged',"
                " decided_at = now(), decided_by = %s, decision_reason = %s"
                " WHERE candidate_id = %s AND status = 'open'",
                (actor_id, reason, candidate_id),
            )
        _append(conn, tenant_id, "person.merged", target_person_id,
                {"source_person_id": source_person_id, "target_person_id": target_person_id},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"merge_id": str(row[0]), "source_person_id": source_person_id,
            "target_person_id": target_person_id, "moved": moved,
            "retained": list(plan.retained)}


def reverse_merge(
    pool: Pool, tenant_id: str, merge_id: str, *, reason: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Undo a merge, as far as this module can.

    **"Reversible where feasible" is the honest part of paragraph 10200, and this is where the
    limit is.** The source record becomes active again and its merge row records the reversal.
    What does *not* come back is the detail of which contact points and relationships were the
    source's: the merge re-pointed them and this module did not keep a per-row ledger, only the
    counts, so the rows stay with the target. Everything another module wrote against the
    survivor in the meantime also stays there.

    Stated rather than implied, because an operator told "reversed" would otherwise reasonably
    believe the two records are as they were.
    """
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT source_person_id, target_person_id, reversed_at, moved_contact_points,"
            " moved_relationships, moved_notes, moved_tags, moved_custom_fields"
            " FROM plt01.ppl_merges WHERE merge_id = %s",
            (merge_id,),
        ).fetchone()
        if row is None:
            raise NotFound("merge_not_found")
        source_person_id = str(row[0])
        source = _person_row(conn, source_person_id)
        try:
            merge.check_reversal(reversed_at=row[2],
                                 source_status=str(source["merge_status"]), reason=reason)
        except merge.MergeError as e:
            raise Conflict(str(e)) from None
        # **The merge row is claimed first, and its row count is checked.** Two callers both
        # passed `check_reversal` -- which reads before it writes -- and both were told
        # `reversed: True` while one row was written and the person's version was bumped twice.
        # Claiming the merge before touching the person makes the unique `reversed_at IS NULL`
        # predicate the arbiter, which is what `check_reversal`'s own docstring says must
        # happen. Found by review with two concurrent callers.
        try:
            claimed = conn.execute(
                "UPDATE plt01.ppl_merges SET reversed_at = now(), reversed_by = %s,"
                " reverse_reason = %s, reverse_correlation_id = %s"
                " WHERE merge_id = %s AND reversed_at IS NULL",
                (actor_id, reason, correlation_id, merge_id),
            ).rowcount
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        if claimed == 0:
            raise Conflict("this_merge_was_reversed_by_somebody_else")
        # And the person UPDATE carries the status predicate, so a reversal cannot un-merge a
        # record that a *later* merge has since moved: without it the person read `active`
        # while `ppl_merges_one_live_per_source` kept them permanently un-mergeable.
        restored = conn.execute(
            "UPDATE plt01.ppl_persons SET merge_status = 'active',"
            " merged_into_person_id = NULL, merged_at = NULL, version = version + 1,"
            " updated_at = now()"
            " WHERE person_id = %s AND merge_status = 'merged'"
            "   AND merged_into_person_id = %s",
            (source_person_id, str(row[1])),
        ).rowcount
        if restored == 0:
            raise Conflict("this_person_has_been_merged_again_since")
    return {"merge_id": merge_id, "source_person_id": source_person_id,
            "reversed": True,
            "not_restored": {
                "contact_points": int(row[3]), "relationships": int(row[4]),
                "notes": int(row[5]), "tags": int(row[6]),
                "custom_fields": int(row[7]),
                # **"Copied", not "re-pointed".** The merge inserts on the survivor and leaves
                # the source's rows where they are -- it has no choice, because `person_id`
                # carries no UPDATE grant and no table here carries DELETE. The earlier wording
                # would have had an operator believe the source lost them. And custom fields
                # were counted, returned and then omitted from this list entirely, which in a
                # reviewer's probe hid a health-classified value copied onto another person and
                # left there after the reversal.
                "why": "the merge copied these rows onto the surviving person and recorded "
                       "only counts, so the copies stay there; the source keeps its own"}}


# ------------------------------------------------------------------------------ timeline

def project_timeline(
    pool: Pool, tenant_id: str, *, limit: int = 500,
) -> dict[str, Any]:
    """Build timeline entries from events in the outbox that are not yet projected.

    **Idempotent by the unique index on (person, event).** Paragraph 4225 says the projection
    can be rebuilt from retained events, and a rebuild re-runs over the same rows -- so a second
    pass has to be free rather than doubling every member's history.

    Nothing drives this on a schedule. That is the same missing worker runtime as MOD-007's
    challenge sweep, MOD-009's retention sweep, MOD-010's relay, MOD-011's objectives and
    MOD-012's rotations -- the seventh module to want it, and the second where the absence
    changes the product: a timeline nobody projects is a timeline that stays empty.
    """
    projected = 0
    skipped = 0
    with tenant_scope(pool, tenant_id) as conn:
        # **Only events that have not been projected yet.** Without the NOT EXISTS the query
        # returned the same oldest `limit` rows on every call, so a tenant's timeline stopped
        # at the first batch and every later run reported `projected: 0` -- indistinguishable
        # from "caught up". Found by review; the docstring above had always claimed this
        # predicate existed.
        rows = conn.execute(
            "SELECT o.event_id, o.event_type, o.payload, o.occurred_at, o.aggregate_type,"
            " o.aggregate_id FROM plt01.evt_outbox o"
            " WHERE o.event_type = ANY(%s)"
            "   AND NOT EXISTS (SELECT 1 FROM plt01.ppl_timeline_entries e"
            "                   WHERE e.event_id = o.event_id)"
            " ORDER BY o.occurred_at, o.event_id LIMIT %s",
            (list(timeline.PROJECTED), max(1, min(limit, 5000))),
        ).fetchall()
        for event_id, event_type, payload, occurred_at, aggregate_type, aggregate_id in rows:
            try:
                result = timeline.project(str(event_type), dict(payload))
            except timeline.TimelineError:
                # A projected type whose payload lost its subject field is a producer
                # regression, not a reason to abandon the batch: the rest of the events are
                # fine and a loop that stopped would be MOD-010's poison-row finding again.
                skipped += 1
                continue
            if result is None:
                continue
            person_id, summary, visibility_class = result
            # The person must exist in this tenant. An event naming a subject that is not a
            # person here -- MOD-009's consent subjects are identity ids, not person ids -- is
            # skipped rather than inserted against a dangling reference.
            if not _person_exists(conn, person_id):
                skipped += 1
                continue
            inserted = conn.execute(
                """
                INSERT INTO plt01.ppl_timeline_entries
                    (tenant_id, person_id, event_id, event_type, occurred_at, aggregate_type,
                     aggregate_id, summary, visibility_class)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, person_id, event_id) DO NOTHING
                """,
                (tenant_id, person_id, str(event_id), str(event_type), occurred_at,
                 str(aggregate_type), str(aggregate_id), summary, visibility_class),
            ).rowcount
            projected += inserted
    return {"projected": projected, "skipped": skipped, "considered": len(rows)}


def read_timeline(
    pool: Pool, tenant_id: str, person_id: str, *, masked_fields: tuple[str, ...],
    held_permissions: set[str], actor_person_id: str | None = None, limit: int = 50,
) -> list[dict[str, Any]]:
    """A person's timeline, with each entry the caller may not read redacted rather than hidden.

    Paragraph 4224: masking is applied **at read time**, which is why the class travels on the
    row and the permissions are a parameter. Baking one reader's view into the projection would
    make it wrong for every other reader.

    The docstring used to say exactly that while the function applied no mask at all: a
    reviewer wrote a MASK policy for `people.timeline.read` -- the very action this route gates
    -- and read the unmasked summary through it. `masked_fields` is required now, and the
    guardianship check runs here as well.
    """
    readable = visibility.readable_classes(frozenset(held_permissions))
    masks = _masks(masked_fields, readable)
    with tenant_scope(pool, tenant_id) as conn:
        _require_guardianship(conn, _person_row(conn, person_id), held_permissions,
                              actor_person_id)
        rows = conn.execute(
            "SELECT entry_id, event_id, event_type, occurred_at, aggregate_type,"
            " aggregate_id, summary, visibility_class FROM plt01.ppl_timeline_entries"
            " WHERE person_id = %s ORDER BY occurred_at DESC, entry_id LIMIT %s",
            (person_id, max(1, min(limit, 500))),
        ).fetchall()
    entries = [{"entry_id": str(r[0]), "event_id": str(r[1]), "event_type": r[2],
                "occurred_at": r[3].isoformat(), "aggregate_type": r[4],
                "aggregate_id": str(r[5]), "summary": r[6], "visibility_class": r[7]}
               for r in rows]
    redacted = visibility.redact_classified(
        entries, class_field="visibility_class", body_fields=("summary",), readable=readable)
    return [visibility.apply_record(r, masks) for r in redacted]


def member_360(
    pool: Pool, tenant_id: str, person_id: str, *, masked_fields: tuple[str, ...],
    held_permissions: set[str], actor_person_id: str | None = None,
) -> dict[str, Any]:
    """PPL-01-R02: the composed member view, with every section's provenance stated.

    **It is a composition, not a stored row.** Paragraph 816 is explicit, and the consequence is
    the `sections` block: each part names where it came from, and the parts whose owning module
    does not exist in this build say so. A 360 that returned `"invoices": []` for a member with
    twelve invoices -- because COM-01 is unbuilt -- would be a confident wrong answer in the
    place a staff member looks before talking to somebody.
    """
    person = get_person(pool, tenant_id, person_id, masked_fields=masked_fields,
                        held_permissions=held_permissions, actor_person_id=actor_person_id)
    with tenant_scope(pool, tenant_id) as conn:
        member = conn.execute(
            "SELECT lifecycle_state, state_changed_at, member_number, joined_on, version"
            " FROM plt01.ppl_member_profiles WHERE person_id = %s",
            (person_id,),
        ).fetchone()
        staff = conn.execute(
            "SELECT employment_state, job_title, location_id, started_on, ended_on, version"
            " FROM plt01.ppl_staff_profiles WHERE person_id = %s",
            (person_id,),
        ).fetchone()
        # **MOD-009's consent subject is an `identity_id`, not a `person_id`**, which this
        # module says itself two hundred lines up -- so counting on the person id was a
        # permanent zero, which is exactly the "returning `[]` for a member with twelve" failure
        # the `sections` block exists to prevent. Resolved through `ppl_identity_links`, and the
        # section text says so. A person with no linked identity has no consent records to
        # count, which is true rather than merely zero.
        consents = conn.execute(
            "SELECT count(*) FROM plt01.sec_consent_records"
            " WHERE subject_id IN (SELECT identity_id FROM plt01.ppl_identity_links"
            "                      WHERE person_id = %s)",
            (person_id,),
        ).fetchone()
    notes = list_notes(pool, tenant_id, person_id, masked_fields=masked_fields,
                       held_permissions=held_permissions,
                       actor_person_id=actor_person_id)
    entries = read_timeline(pool, tenant_id, person_id, masked_fields=masked_fields,
                            held_permissions=held_permissions,
                            actor_person_id=actor_person_id)
    composed = {
        "person": person,
        "member_profile": None if member is None else {
            "lifecycle_state": member[0], "state_changed_at": member[1].isoformat(),
            "member_number": member[2],
            "joined_on": member[3].isoformat() if member[3] else None,
            "version": int(member[4])},
        "staff_profile": None if staff is None else {
            "employment_state": staff[0], "job_title": staff[1],
            "location_id": str(staff[2]) if staff[2] else None,
            "started_on": staff[3].isoformat() if staff[3] else None,
            "ended_on": staff[4].isoformat() if staff[4] else None,
            "version": int(staff[5])},
        "notes": notes,
        "timeline": entries,
        "consent_record_count": int(consents[0]) if consents else 0,
        # **Every section says where it came from, and the absent ones say why.** PPL-01-R02
        # lists twelve areas; five are readable here and seven are not. Returning an empty list
        # for those would read as "none", which is the difference between "this member has no
        # outstanding balance" and "nothing here knows".
        #
        # **And "why" has two answers now, which it did not when this was written.** Five of
        # these sections said "not built in this repository" and four of those modules have
        # since been built -- so the Member 360 was telling a staff member that bookings and
        # finance do not exist in a build that has both. That is this module's own stated
        # failure mode from the other side: a confident wrong answer in the place somebody
        # looks before talking to a member. The true statement for those is that the module
        # exists and *this projection does not read it*, which is a gap in the wiring rather
        # than in the product -- and paragraph 1300's ban on cross-domain write-table access is
        # why the wiring is not a one-line join. Found by looking at the page.
        "sections": {
            "identity": "ppl_persons, ppl_contact_points (this module)",
            "lifecycle": "ppl_member_profiles (this module)",
            "coaching": "ppl_relationships, kind=coach_client (this module)",
            "consent": "sec_consent_records (MOD-009), counted only, resolved through "
                       "ppl_identity_links because MOD-009 keys on an identity",
            "timeline": "ppl_timeline_entries, projected from MOD-010's outbox",
            "membership": "unavailable: MOD-017 (COM-01) owns this and nothing here reads "
                          "it; a cross-domain read is what paragraph 1300 bars",
            "entitlements": "unavailable: MOD-017 (COM-01) owns this and nothing here "
                            "reads it",
            # **Two different things are called attendance, and only one is unavailable.**
            # MOD-020 owns class attendance -- who was marked present at a session -- and
            # nothing here reads it. Door entries are MOD-022's, and the member record's own
            # Attendance tab reads them directly. Saying "attendance: nothing here reads it"
            # without that distinction puts a flat contradiction under a tab that is showing
            # somebody their visits, which is this screen's own stale-claim defect in a new
            # place.
            # An em-dash, not two hyphens: this string is rendered to a reader. The `--`
            # house style belongs in comments, and the siblings here carry none.
            "attendance": "unavailable: class attendance \u2014 who was marked present at a "
                          "session \u2014 is MOD-020's (OPS-02) and nothing here reads it. Door "
                          "entries are MOD-022's and the surface reads them directly; they "
                          "are not in this projection",
            "bookings": "unavailable: MOD-019 (OPS-01) owns this and nothing here reads it",
            "nutrition": "unavailable: CCH-02 is not built in this repository",
            "progress": "unavailable: CCH-03 is not built in this repository",
            "finance": "unavailable: MOD-018 (COM-04) owns this and nothing here reads it",
            "messages": "unavailable: ENG-01 is not built in this repository",
            "support": "unavailable: SUP-01 is not built in this repository",
        },
    }
    return visibility.apply_record(
        composed, _masks(masked_fields, visibility.readable_classes(
            frozenset(held_permissions))))


# ------------------------------------------------------------------------------ helpers

def _append(
    conn: Connection[Any], tenant_id: str, event_type: str, aggregate_id: str,
    payload: dict[str, Any], *, correlation_id: str, actor_id: str,
) -> None:
    """Append an event in the caller's transaction.

    `append_event` takes a connection, not a pool, which is MOD-010's whole design: paragraph
    105 requires the state change and the event to commit atomically, and a version that opened
    its own transaction would read identically and guarantee nothing.
    """
    events.append_event(
        conn, tenant_id, event_type=event_type, aggregate_type="person",
        aggregate_id=aggregate_id, payload=payload, correlation_id=correlation_id,
        actor_id=actor_id,
    )


def _person_row(conn: Connection[Any], person_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT person_id, legal_name, preferred_name, date_of_birth, merge_status,"
        " merged_into_person_id, version, created_at, updated_at"
        " FROM plt01.ppl_persons WHERE person_id = %s",
        (person_id,),
    ).fetchone()
    if row is None:
        raise NotFound("person_not_found")
    return {"person_id": str(row[0]), "legal_name": row[1], "preferred_name": row[2],
            "date_of_birth": row[3], "merge_status": row[4],
            "merged_into_person_id": str(row[5]) if row[5] else None,
            "version": int(row[6]), "created_at": row[7].isoformat(),
            "updated_at": row[8].isoformat()}


def _person_exists(conn: Connection[Any], person_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM plt01.ppl_persons WHERE person_id = %s", (person_id,)
    ).fetchone()
    return row is not None


def _age_years(born: date | None, today: date) -> int | None:
    if born is None:
        return None
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def _decided_pairs(
    conn: Connection[Any], pairs: list[tuple[str, str]],
) -> set[tuple[str, str]]:
    """Which of these ordered pairs an operator has already merged or dismissed.

    The partial unique index only covers `status = 'open'`, so without this the detector
    inserted a second row beside a `dismissed` one and put the pair an operator had just
    rejected straight back in the queue.
    """
    if not pairs:
        return set()
    # Two parallel arrays rather than an array of tuples: psycopg cannot bind an anonymous
    # composite type, and naming a composite in the schema for one lookup would be worse.
    rows = conn.execute(
        "SELECT lower_person_id, higher_person_id FROM plt01.ppl_duplicate_candidates"
        " WHERE status <> 'open' AND lower_person_id = ANY(%s)"
        "   AND higher_person_id = ANY(%s)",
        ([lower for lower, _ in pairs], [higher for _, higher in pairs]),
    ).fetchall()
    # The query over-matches when several pairs are in flight, so the exact pairs are filtered
    # here: a cross-product match would suppress a candidate nobody had decided.
    wanted = set(pairs)
    return {(str(r[0]), str(r[1])) for r in rows} & wanted


def _survivor_of(conn: Connection[Any], person_id: str) -> str:
    """The person this id resolves to after any merges, walking the pointer.

    Cycle-safe through `merge.survivor_of`, which is the pure walk: the schema forbids the
    length-one case and `check_merge` forbids the ordinary way to build a longer one, and that
    is exactly the argument that would leave a read path trusting an invariant it cannot see.

    One query per hop. A chain longer than one needs a reversal followed by a new merge, so in
    practice this is one row.
    """
    chain: dict[str, str | None] = {}
    current: str | None = person_id
    while current is not None and current not in chain:
        row = conn.execute(
            "SELECT merged_into_person_id FROM plt01.ppl_persons WHERE person_id = %s",
            (current,),
        ).fetchone()
        if row is None:
            chain[current] = None
            break
        chain[current] = str(row[0]) if row[0] else None
        current = chain[current]
    try:
        return merge.survivor_of(chain, person_id)
    except merge.MergeError:
        # A cycle. Returning the id unchanged is the fail-closed answer: the caller reads the
        # record they asked for rather than being sent somewhere by a broken pointer.
        return person_id


def _is_guardian_of(conn: Connection[Any], actor_person_id: str, person_id: str) -> bool:
    # Both sides resolved through the pointer, so a merge on either does not quietly revoke a
    # guardian's access to their own dependent.
    actor_person_id = _survivor_of(conn, actor_person_id)
    person_id = _survivor_of(conn, person_id)
    row = conn.execute(
        "SELECT 1 FROM plt01.ppl_relationships WHERE kind = 'guardian_dependent'"
        " AND from_person_id = %s AND to_person_id = %s AND valid_to IS NULL",
        (actor_person_id, person_id),
    ).fetchone()
    return row is not None


def _has_identity_link(conn: Connection[Any], person_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM plt01.ppl_identity_links WHERE person_id = %s", (person_id,)
    ).fetchone()
    return row is not None


def _contact_points(conn: Connection[Any], person_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT contact_point_id, kind, value_raw, value_normalized, is_primary, verified_at"
        " FROM plt01.ppl_contact_points WHERE person_id = %s ORDER BY kind, is_primary DESC",
        (person_id,),
    ).fetchall()
    return [{"contact_point_id": str(r[0]), "kind": r[1], "value_raw": r[2],
             "value_normalized": r[3], "is_primary": r[4],
             "verified_at": r[5].isoformat() if r[5] else None} for r in rows]


def _tags(conn: Connection[Any], person_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT t.tag_id, t.tag_key, t.display_name, t.is_internal, pt.applied_at"
        " FROM plt01.ppl_person_tags pt JOIN plt01.ppl_tags t ON t.tag_id = pt.tag_id"
        " WHERE pt.person_id = %s AND pt.removed_at IS NULL ORDER BY t.tag_key",
        (person_id,),
    ).fetchall()
    return [{"tag_id": str(r[0]), "tag_key": r[1], "display_name": r[2],
             "is_internal": r[3], "applied_at": r[4].isoformat()} for r in rows]


def _custom_fields(
    conn: Connection[Any], person_id: str, readable: frozenset[str],
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT d.field_key, d.display_name, d.value_type, d.sensitivity, v.value_text"
        " FROM plt01.ppl_custom_field_values v"
        " JOIN plt01.ppl_custom_field_defs d ON d.field_id = v.field_id"
        " WHERE v.person_id = %s ORDER BY d.field_key",
        (person_id,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for key, display, value_type, sensitivity, value in rows:
        hidden = sensitivity != "none" and sensitivity not in readable
        out.append({"field_key": key, "display_name": display, "value_type": value_type,
                    "sensitivity": sensitivity,
                    "value": visibility.MASK if hidden else value,
                    "redacted": hidden})
    return out


def _relationships(conn: Connection[Any], person_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT relationship_id, kind, from_person_id, to_person_id, valid_from, valid_to"
        " FROM plt01.ppl_relationships"
        " WHERE (from_person_id = %s OR to_person_id = %s) AND valid_to IS NULL"
        " ORDER BY kind, valid_from",
        (person_id, person_id),
    ).fetchall()
    return [{"relationship_id": str(r[0]), "kind": r[1], "from_person_id": str(r[2]),
             "to_person_id": str(r[3]), "valid_from": r[4].isoformat(),
             "direction": "from" if str(r[2]) == person_id else "to"} for r in rows]


def _field_definition(
    conn: Connection[Any], field_key: str,
) -> tuple[str, fields.Definition]:
    row = conn.execute(
        "SELECT field_id, field_key, display_name, value_type, sensitivity, is_required,"
        " retired_at FROM plt01.ppl_custom_field_defs WHERE field_key = %s",
        (field_key,),
    ).fetchone()
    if row is None:
        raise NotFound("custom_field_not_found")
    if row[6] is not None:
        raise Conflict("this_custom_field_is_retired")
    options = conn.execute(
        "SELECT option_value FROM plt01.ppl_custom_field_options WHERE field_id = %s"
        " ORDER BY option_value",
        (row[0],),
    ).fetchall()
    return str(row[0]), fields.Definition(
        field_key=str(row[1]), display_name=str(row[2]), value_type=str(row[3]),
        sensitivity=str(row[4]), is_required=bool(row[5]),
        options=tuple(str(o[0]) for o in options))


def _signals(conn: Connection[Any], person_id: str) -> dedup.PersonSignals:
    person = _person_row(conn, person_id)
    contacts = conn.execute(
        "SELECT kind, value_normalized, verified_at FROM plt01.ppl_contact_points"
        " WHERE person_id = %s",
        (person_id,),
    ).fetchall()
    households = conn.execute(
        "SELECT CASE WHEN from_person_id = %s THEN to_person_id ELSE from_person_id END"
        " FROM plt01.ppl_relationships WHERE kind = 'household' AND valid_to IS NULL"
        "   AND (from_person_id = %s OR to_person_id = %s)",
        (person_id, person_id, person_id),
    ).fetchall()
    return dedup.PersonSignals(
        person_id=person_id,
        legal_name_folded=dedup.fold_name(str(person["legal_name"])),
        date_of_birth=person["date_of_birth"],
        emails=frozenset(c[1] for c in contacts if c[0] == "email"),
        phones=frozenset(c[1] for c in contacts if c[0] == "phone"),
        verified_emails=frozenset(c[1] for c in contacts
                                  if c[0] == "email" and c[2] is not None),
        verified_phones=frozenset(c[1] for c in contacts
                                  if c[0] == "phone" and c[2] is not None),
        household_ids=frozenset(str(h[0]) for h in households),
    )


def _candidate_signals(
    conn: Connection[Any], subject: dedup.PersonSignals,
) -> list[dedup.PersonSignals]:
    """Everybody who shares an exact signal with the subject, through the indexes.

    The query draws the small set; `dedup.compare` scores it. A pairwise scan of the tenant is
    O(n^2) against the 450,000 profiles the module is specified for, and no signal in `dedup` is
    fuzzy, so nothing outside this set could score above the threshold.
    """
    values = sorted(subject.emails | subject.phones)
    ids: set[str] = set()
    if values:
        # **`merge_status = 'active'` on this draw too.** A merge copies the source's contact
        # points onto the survivor, so without the filter the detector re-raised the pair it
        # had just merged -- and `check_merge` refuses a merged source, so that candidate could
        # never be decided. The merge created the shared value that re-raises it.
        rows = conn.execute(
            "SELECT DISTINCT c.person_id FROM plt01.ppl_contact_points c"
            " JOIN plt01.ppl_persons p ON p.person_id = c.person_id"
            " WHERE c.value_normalized = ANY(%s) AND p.merge_status = 'active'",
            (values,),
        ).fetchall()
        ids.update(str(r[0]) for r in rows)
    rows = conn.execute(
        "SELECT person_id FROM plt01.ppl_persons"
        " WHERE merge_status = 'active' AND person_id <> %s"
        "   AND (lower(legal_name) = %s OR (date_of_birth IS NOT NULL"
        "        AND date_of_birth = %s))",
        (subject.person_id, subject.legal_name_folded, subject.date_of_birth),
    ).fetchall()
    ids.update(str(r[0]) for r in rows)
    ids.discard(subject.person_id)
    return [_signals(conn, other) for other in sorted(ids)]


def _merge_plan(
    conn: Connection[Any], source_person_id: str, target_person_id: str,
) -> merge.MergePlan:
    def count(sql: str, *args: Any) -> int:
        row = conn.execute(sql, args).fetchone()
        return int(row[0]) if row else 0

    source_member = count(
        "SELECT count(*) FROM plt01.ppl_member_profiles WHERE person_id = %s",
        source_person_id)
    target_member = count(
        "SELECT count(*) FROM plt01.ppl_member_profiles WHERE person_id = %s",
        target_person_id)
    source_staff = count(
        "SELECT count(*) FROM plt01.ppl_staff_profiles WHERE person_id = %s",
        source_person_id)
    target_staff = count(
        "SELECT count(*) FROM plt01.ppl_staff_profiles WHERE person_id = %s",
        target_person_id)
    number_row = conn.execute(
        "SELECT member_number FROM plt01.ppl_member_profiles WHERE person_id = %s",
        (source_person_id,),
    ).fetchone()
    return merge.MergePlan(
        source_person_id=source_person_id, target_person_id=target_person_id,
        contact_points=count(
            "SELECT count(*) FROM plt01.ppl_contact_points WHERE person_id = %s",
            source_person_id),
        relationships=count(
            "SELECT count(*) FROM plt01.ppl_relationships"
            " WHERE (from_person_id = %s OR to_person_id = %s) AND valid_to IS NULL",
            source_person_id, source_person_id),
        notes=count(
            "SELECT count(*) FROM plt01.ppl_person_notes WHERE person_id = %s",
            source_person_id),
        tags=count(
            "SELECT count(*) FROM plt01.ppl_person_tags"
            " WHERE person_id = %s AND removed_at IS NULL", source_person_id),
        custom_fields=count(
            "SELECT count(*) FROM plt01.ppl_custom_field_values WHERE person_id = %s",
            source_person_id),
        retained=merge.plan_retentions(
            source_has_member_profile=source_member > 0,
            target_has_member_profile=target_member > 0,
            source_has_staff_profile=source_staff > 0,
            target_has_staff_profile=target_staff > 0,
            source_member_number=(str(number_row[0]) if number_row and number_row[0]
                                  else None)),
    )


def _perform_merge(
    conn: Connection[Any], tenant_id: str, source_person_id: str, target_person_id: str,
    *, actor_id: str, correlation_id: str,
) -> dict[str, int]:
    """Move what this module owns, skipping what the target already has.

    Contact points and tags move by insert-and-skip rather than by UPDATE, because the target
    may already hold the same value and the unique indexes refuse a duplicate -- and a merge
    that failed on the second of fifty rows would leave a half-merged pair.

    A relationship moves by **ending the old one and inserting its replacement**, because
    `from_person_id`, `to_person_id` and `kind` carry no UPDATE grant: "who was this member's
    coach in March" has to stay answerable, and re-pointing the row would rewrite it.
    """
    moved = {"contact_points": 0, "relationships": 0, "notes": 0, "tags": 0,
             "custom_fields": 0}

    contacts = conn.execute(
        "SELECT kind, value_raw, value_normalized, verified_at FROM plt01.ppl_contact_points"
        " WHERE person_id = %s",
        (source_person_id,),
    ).fetchall()
    for kind, raw, normalized, verified in contacts:
        inserted = conn.execute(
            """
            INSERT INTO plt01.ppl_contact_points
                (tenant_id, person_id, kind, value_raw, value_normalized, is_primary,
                 verified_at, recorded_by, correlation_id)
            VALUES (%s, %s, %s, %s, %s, false, %s, %s, %s)
            ON CONFLICT (tenant_id, person_id, kind, value_normalized) DO NOTHING
            """,
            (tenant_id, target_person_id, kind, raw, normalized, verified, actor_id,
             correlation_id),
        ).rowcount
        moved["contact_points"] += inserted

    relationships = conn.execute(
        "SELECT relationship_id, kind, from_person_id, to_person_id"
        " FROM plt01.ppl_relationships"
        " WHERE (from_person_id = %s OR to_person_id = %s) AND valid_to IS NULL",
        (source_person_id, source_person_id),
    ).fetchall()
    for relationship_id, kind, from_person, to_person in relationships:
        new_from = target_person_id if str(from_person) == source_person_id else str(from_person)
        new_to = target_person_id if str(to_person) == source_person_id else str(to_person)
        if new_from == new_to:
            # The merge would make this a self-relationship, which the schema refuses and which
            # is the right answer: a coach merged into their own client is one person, and the
            # relationship between them no longer means anything.
            conn.execute(
                "UPDATE plt01.ppl_relationships SET valid_to = now(),"
                " ended_reason = 'both sides merged into one person', ended_by = %s,"
                " end_correlation_id = %s WHERE relationship_id = %s",
                (actor_id, correlation_id, relationship_id),
            )
            continue
        conn.execute(
            "UPDATE plt01.ppl_relationships SET valid_to = now(),"
            " ended_reason = 'moved by merge', ended_by = %s, end_correlation_id = %s"
            " WHERE relationship_id = %s",
            (actor_id, correlation_id, relationship_id),
        )
        inserted = conn.execute(
            """
            INSERT INTO plt01.ppl_relationships
                (tenant_id, kind, from_person_id, to_person_id, created_by, correlation_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, kind, from_person_id, to_person_id)
                WHERE valid_to IS NULL
            DO NOTHING
            """,
            (tenant_id, kind, new_from, new_to, actor_id, correlation_id),
        ).rowcount
        moved["relationships"] += inserted

    notes = conn.execute(
        "SELECT note_class, body, recorded_by, correlation_id FROM plt01.ppl_person_notes"
        " WHERE person_id = %s AND withdrawn_at IS NULL",
        (source_person_id,),
    ).fetchall()
    for note_class, body, recorded_by, note_correlation in notes:
        conn.execute(
            "INSERT INTO plt01.ppl_person_notes"
            " (tenant_id, person_id, note_class, body, recorded_by, correlation_id)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (tenant_id, target_person_id, note_class, body, recorded_by, note_correlation),
        )
        moved["notes"] += 1

    tags = conn.execute(
        "SELECT tag_id, applied_by, correlation_id FROM plt01.ppl_person_tags"
        " WHERE person_id = %s AND removed_at IS NULL",
        (source_person_id,),
    ).fetchall()
    for tag_id, applied_by, tag_correlation in tags:
        inserted = conn.execute(
            "INSERT INTO plt01.ppl_person_tags"
            " (tenant_id, person_id, tag_id, applied_by, correlation_id)"
            " VALUES (%s, %s, %s, %s, %s)"
            " ON CONFLICT (tenant_id, person_id, tag_id) DO NOTHING",
            (tenant_id, target_person_id, tag_id, applied_by, tag_correlation),
        ).rowcount
        moved["tags"] += inserted

    values = conn.execute(
        "SELECT field_id, value_text FROM plt01.ppl_custom_field_values WHERE person_id = %s",
        (source_person_id,),
    ).fetchall()
    for field_id, value_text in values:
        inserted = conn.execute(
            "INSERT INTO plt01.ppl_custom_field_values"
            " (tenant_id, person_id, field_id, value_text, updated_by, correlation_id)"
            " VALUES (%s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (tenant_id, person_id, field_id) DO NOTHING",
            (tenant_id, target_person_id, field_id, value_text, actor_id, correlation_id),
        ).rowcount
        moved["custom_fields"] += inserted

    return moved
