"""MOD-014 PPL-01: applying a field mask to a record that is about to be returned.

**This is the module MOD-008's `Decision.mask` was computed for.** From MOD-008 to MOD-013 the
masked-field list was produced on every allowed decision and read by nothing, because no gated
read path had fields worth masking. PPL-01 is the first that does -- paragraph 1320 asks for
privacy controls over preferred name, contact channels, sensitive notes, progress media and
minors, and paragraph 4224 says each timeline item "applies permission/field masking at read
time".

Three rules, and each exists because the obvious implementation gets it wrong:

* **Mask on the way out, never filter on the way in.** A query that omitted the column would
  leave the caller unable to tell a masked field from an absent one, and the two mean different
  things: "you may not see this person's phone number" and "this person has no phone number"
  lead to different next actions at a front desk.

* **A nested record is masked too.** The 360 read is a composition of lists of records, and a
  mask applied only to the top level is a mask a reader walks around by looking one level down.
  `apply` recurses through lists and dicts.

* **A class, not a field name, decides a whole record.** A note classified `health` is not a
  record with a masked field in it; the body is the health information. `redact_classified`
  replaces the body of a record whose class the caller may not read, and leaves the fact that
  the record exists -- because "this member has three health notes you may not read" is what
  tells a coach to ask somebody who can.

Nothing here reads a row or asks a question of MOD-008. The caller supplies the masked-field
list the gate produced and the classes the caller holds; this module decides what that means for
a record.
"""

from __future__ import annotations

from typing import Any

#: What a masked value is replaced with. Matches `authorization.decision.Decision.mask`, because
#: two different placeholders in one response would read as two different conditions.
MASK = "***"

#: The classes a record can be marked with. `none` is readable with the record it belongs to;
#: the rest need the matching permission. Deliberately the same five as MOD-008's
#: `SENSITIVE_FIELDS` values, so a class here cannot be one the gate has never heard of.
CLASSES = ("none", "contact", "identity", "financial", "health", "biometric")

#: Which permission lets a caller read each class. A class with no permission behind it would be
#: unreadable by everybody, which is a different bug from being readable by everybody and is why
#: this map is exhaustive rather than defaulted.
CLASS_PERMISSIONS: dict[str, str] = {
    "none": "",
    "contact": "member.profile.read",
    "identity": "member.identity.read",
    "financial": "member.finance.read",
    "health": "member.health.read",
    "biometric": "member.health.read",
}

#: **`health` and `biometric` are unreadable in this build, by anybody.**
#:
#: `member.health.read` is `biometric_sensitive`, which MOD-007's policy maps to AAL 3, which
#: needs a hardware authenticator MOD-007 cannot verify -- so the permission can be granted and
#: can never be exercised. That is the same deliberate dead end MOD-008 records for break-glass
#: support access, and the consequence here is that a health-classified note or custom field is
#: stored, counted and masked for every caller.
#:
#: Named rather than left to be discovered, because the alternative -- quietly mapping health to
#: something reachable -- is how a field somebody collected as medical information becomes
#: readable at the front desk.
UNREACHABLE_CLASSES = ("health", "biometric")


class VisibilityError(ValueError):
    """A visibility input this module will not accept."""


def check_class(value: str) -> str:
    if value not in CLASSES:
        raise VisibilityError(f"{value!r} is not a visibility class")
    return value


def readable_classes(held_permissions: set[str] | frozenset[str]) -> frozenset[str]:
    """Which classes these permissions open.

    `none` is always in the result: a record with no classification is readable by whoever could
    read the thing it belongs to, and the gate already decided that.
    """
    return frozenset(
        {"none"}
        | {name for name, needed in CLASS_PERMISSIONS.items()
           if needed and needed in held_permissions}
    )


#: **This module's own column names, mapped to MOD-008's classes.**
#:
#: MOD-008's `SENSITIVE_FIELDS` names the fields it knows -- `date_of_birth`, `email`, `phone`,
#: `address` and the rest -- and those names are what a tenant's MASK policy reaches for. But a
#: contact point is stored as `value_raw`/`value_normalized`, and the person's own `legal_name`
#: and `preferred_name` are not in MOD-008's table at all. So the first version masked a
#: `contact`-classified *custom field* while returning the phone number it held in the clear
#: beside it, and handed `date_of_birth` -- the canonical `identity` field in MOD-008's own
#: table -- to a routine AAL-1 caller. Two reviewers found it independently.
#:
#: The map is here rather than in MOD-008 because these are this module's column names: the
#: catalogue is code about what the software can do, and a storage column is not that.
COLUMN_CLASSES: dict[str, str] = {
    # The person's own identifying columns.
    "date_of_birth": "identity",
    "legal_name": "identity",
    "preferred_name": "identity",
    # A contact point, under the names this module stores it as.
    "value_raw": "contact",
    "value_normalized": "contact",
    # And under the names MOD-008 uses, so a policy or a caller reaching for `email` is not
    # silently reaching for nothing.
    "email": "contact",
    "phone": "contact",
    "address": "contact",
}


def classified_masks(readable: frozenset[str]) -> tuple[str, ...]:
    """The column names this caller may not read, by class.

    Merged into the gate's `masked_fields` at every read, so a caller holding only
    `people.person.read` sees `***` for the identity and contact classes -- which is the bound
    the permission catalogue claims for that permission being routine, and which did not exist
    until this function did.
    """
    return tuple(sorted(
        name for name, klass in COLUMN_CLASSES.items() if klass not in readable
    ))


def apply(record: Any, masked_fields: tuple[str, ...] | frozenset[str]) -> Any:
    """Replace every masked field with `MASK`, at every depth.

    Recursive on purpose. The 360 read returns a dict of lists of dicts, and a mask applied only
    at the top level would leave `profile.email` masked while `contact_points[0].value_raw`
    carried the same address -- which is the shape of mistake this whole module exists to stop
    making, one level down.
    """
    names = set(masked_fields)
    if not names:
        return record
    return _walk(record, names)


def apply_record(
    record: dict[str, Any], masked_fields: tuple[str, ...] | frozenset[str],
) -> dict[str, Any]:
    """`apply` for a record, typed. The recursive worker has to be `Any`; callers do not."""
    result = apply(record, masked_fields)
    assert isinstance(result, dict)
    return result


def _walk(node: Any, names: set[str]) -> Any:
    if isinstance(node, dict):
        return {k: (MASK if k in names else _walk(v, names)) for k, v in node.items()}
    # Tuples and sets as well as lists. No record this module builds contains one today, which
    # is exactly why a reviewer called the omission latent rather than reachable -- and a mask
    # that silently stops at a container type is the kind of hole somebody opens by changing a
    # list comprehension to a generator.
    if isinstance(node, list):
        return [_walk(item, names) for item in node]
    if isinstance(node, tuple):
        return tuple(_walk(item, names) for item in node)
    if isinstance(node, set | frozenset):
        return {_walk(item, names) for item in node}
    return node


def redact_classified(
    records: list[dict[str, Any]], *, class_field: str, body_fields: tuple[str, ...],
    readable: frozenset[str],
) -> list[dict[str, Any]]:
    """Blank the body of each record whose class the caller may not read, keeping the record.

    **The record survives and only its content goes.** Dropping it would tell a coach that a
    member has no health notes when they have three, and "ask somebody who can read these" is a
    better outcome than a confident wrong answer. Paragraph 10280: "only minimum necessary
    health context is exposed to each role" -- minimum necessary is not zero knowledge that the
    context exists.
    """
    out: list[dict[str, Any]] = []
    for record in records:
        marked = str(record.get(class_field, "none"))
        if marked in readable:
            out.append(record)
            continue
        hidden = dict(record)
        for field in body_fields:
            if field in hidden:
                hidden[field] = MASK
        hidden["redacted"] = True
        hidden["redacted_because"] = f"{marked}_requires_{CLASS_PERMISSIONS.get(marked, '?')}"
        out.append(hidden)
    return out


def is_minor(age_years: int | None) -> bool:
    """Whether this person is a minor, from an age this module was handed.

    **Eighteen, and the threshold is stated rather than configured.** The sources name minors in
    four places and give no age anywhere, so a per-tenant setting would be this module inventing
    product; eighteen is the ordinary meaning of the word in the jurisdictions the sources
    discuss. A tenant that needs another number needs a decision recorded somewhere, not a
    default chosen here.

    `None` -- an unknown birth date -- is **not** a minor. That is the uncomfortable direction
    and it is the right one: treating every undated person as a minor would make a guardian
    relationship mandatory before anybody could read the record of a member who simply never
    gave a birthday, which is most leads. The service records that the answer was unknown, so a
    policy that wants to fail the other way has something to match on.
    """
    return age_years is not None and age_years < 18


def guardianship_satisfied(
    *, minor: bool, actor_is_guardian: bool, held_permissions: set[str] | frozenset[str],
) -> tuple[bool, str]:
    """Whether a minor's record may be exposed to this caller. Paragraph 1372.

    Two ways in, and no third: the caller is a recorded guardian of this person, or the caller
    holds the permission that says staff may read member profiles. The second is not a loophole
    -- a gym's staff have to be able to serve a fourteen-year-old at the desk -- but it is the
    one that makes the guardian path meaningful, because a *member-app* caller holds nothing of
    the sort and so reaches only their own dependents.

    Returns the reason as well as the verdict, because a refusal a member sees needs to say
    which of the two was missing.
    """
    if not minor:
        return True, "not_a_minor"
    if actor_is_guardian:
        return True, "actor_is_a_recorded_guardian"
    if "member.profile.read" in held_permissions:
        return True, "staff_profile_read"
    return False, "a_minors_record_needs_guardianship_or_staff_permission"
