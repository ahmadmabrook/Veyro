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
        # lists twelve areas; five are readable here and seven belong to modules this build does
        # not have. Returning an empty list for those would read as "none", which is the
        # difference between "this member has no outstanding balance" and "nothing here knows".
        "sections": {
            "identity": "ppl_persons, ppl_contact_points (this module)",
            "lifecycle": "ppl_member_profiles (this module)",
            "coaching": "ppl_relationships, kind=coach_client (this module)",
            "consent": "sec_consent_records (MOD-009), counted only, resolved through "
                       "ppl_identity_links because MOD-009 keys on an identity",
            "timeline": "ppl_timeline_entries, projected from MOD-010's outbox",
            "membership": "unavailable: COM-01 is not built in this repository",
            "entitlements": "unavailable: COM-01 is not built in this repository",
            "attendance": "unavailable: OPS-02 is not built in this repository",
            "bookings": "unavailable: OPS-01 is not built in this repository",
            "nutrition": "unavailable: CCH-02 is not built in this repository",
            "progress": "unavailable: CCH-03 is not built in this repository",
            "finance": "unavailable: COM-04 is not built in this repository",
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
