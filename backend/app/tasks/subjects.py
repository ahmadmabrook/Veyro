"""MOD-026 · AUT-02-R01: what a task or a case can be about.

**The vocabulary is closed and three of its members name modules this build does not have.**
R01 lists member, lead, tenant, invoice, incident, device, booking, asset and workflow. A
lead is MOD-027's, a workflow MOD-055's, and nothing here owns an asset at all -- so the
honest shape is a closed discriminator plus an id the service resolves where it can, which is
MOD-016's `order_reference` precedent.

**Why closed rather than free text.** R07 asks for workload and outcome reporting, and a
caller able to name its own kind makes "how many tasks are about invoices" a group-by over
typos. That is MOD-010's restricted-field argument -- the rule checks declared names and a
value carries anything -- pointed at a discriminator instead of a payload.

**Why no foreign key per kind.** Nine nullable columns with eight NULL on every row is the
shape MOD-021's two supersession findings are about, and under MATCH SIMPLE a composite key
with a NULL skips its check entirely. One kind and one id, with the service doing the lookup,
is the only version that stays readable.
"""

from __future__ import annotations

from typing import Final

#: Every kind R01 names, in the order it names them. The CHECK in
#: `migrations/tenant/0019_tasks_and_cases.sql` carries the same nine, and
#: `test_tasks_domain.py` compares the two so the two cannot drift.
SUBJECT_KINDS: Final[tuple[str, ...]] = (
    "member", "lead", "tenant", "invoice", "incident", "device", "booking", "asset",
    "workflow",
)

#: The kinds whose rows exist in this build, and the table the service resolves each against.
#:
#: **`tenant` is deliberately absent and is not a gap.** A task about the tenant is about the
#: row's own `tenant_id`, which the request already carries and RLS already bounds, so there
#: is nothing to look up -- which is why `subject_id` is NULL for exactly that kind and a
#: CHECK makes the two agree.
RESOLVABLE: Final[dict[str, str]] = {
    "member": "plt01.ppl_persons",
    "invoice": "plt01.fin_invoices",
    "incident": "plt01.sec_incidents",
    "device": "plt01.dev_devices",
    "booking": "plt01.bkg_bookings",
}

#: The kinds that are a recorded claim rather than a resolved reference, with the module that
#: would make each resolvable. Disclosed here rather than discovered: a task against one of
#: these can name an id nothing in the tenant has, and R07 will count it.
UNRESOLVABLE: Final[dict[str, str]] = {
    "lead": "MOD-027",
    "asset": "no module in this build owns an asset",
    "workflow": "MOD-055",
}


class SubjectError(ValueError):
    """A subject that is not expressible, as opposed to one that cannot be found."""


def check_subject(kind: str, subject_id: str | None) -> None:
    """Refuse a subject the schema would refuse, before it reaches the schema.

    **The id's presence is decided by the kind, both ways.** A `tenant` subject with an id is
    a caller naming something the column does not mean, and any other kind without one is a
    task about nothing -- and both are the schema's rule, repeated here so the caller gets a
    422 naming the field rather than a constraint name.
    """
    if kind not in SUBJECT_KINDS:
        raise SubjectError(
            f"{kind!r} is not a subject kind; AUT-02-R01 names "
            + ", ".join(SUBJECT_KINDS)
        )
    if kind == "tenant" and subject_id is not None:
        raise SubjectError(
            "a task about the tenant carries no subject id: the tenant is the row's own "
            "tenant_id, which the request already carries")
    if kind != "tenant" and subject_id is None:
        raise SubjectError(f"a {kind} subject needs the {kind}'s id")


def is_a_claim(kind: str) -> bool:
    """Is this kind recorded rather than resolved.

    The service calls this to decide whether to look the subject up, and a read returns it so
    a surface can say "this names a lead and nothing here can confirm it" instead of showing
    an id that looks verified. Keyed on the dict rather than on a second list, because two
    lists of the same fact disagree the day a module lands.
    """
    if kind not in SUBJECT_KINDS:
        raise SubjectError(f"{kind!r} is not a subject kind")
    return kind in UNRESOLVABLE


def table_for(kind: str) -> str:
    """The table a resolvable kind resolves against.

    Raises for a claim kind rather than returning None, because a caller that treated None as
    "no check needed" would skip the lookup for the five kinds that have one -- which is this
    build's "a lookup that proves something exists does not authorise what you do next" from
    the other side.
    """
    if kind in UNRESOLVABLE:
        raise SubjectError(
            f"a {kind} subject is a recorded claim in this build ({UNRESOLVABLE[kind]}), "
            "so there is no table to resolve it against")
    if kind not in RESOLVABLE:
        raise SubjectError(f"{kind!r} resolves against nothing")
    return RESOLVABLE[kind]


def _check_vocabulary_is_partitioned() -> None:
    """Every kind is resolvable, a claim, or `tenant` -- checked at import.

    MOD-010's argument for checking a catalogue where it is declared rather than at a
    registration endpoint: a kind that is in neither map is one the service will fall through
    on, and the failure would surface as a task nobody can file rather than as a mistake in
    this file. Both directions, because a stale entry in either map is the same defect as a
    missing one -- which is the lesson this repository records for the message catalogue, the
    id sweep's exemptions and the worker's name list.
    """
    placed = set(RESOLVABLE) | set(UNRESOLVABLE) | {"tenant"}
    missing = set(SUBJECT_KINDS) - placed
    if missing:
        raise AssertionError(
            f"these subject kinds are neither resolvable nor declared claims: "
            f"{sorted(missing)}")
    extra = placed - set(SUBJECT_KINDS)
    if extra:
        raise AssertionError(
            f"these are mapped and are not subject kinds: {sorted(extra)}")
    both = set(RESOLVABLE) & set(UNRESOLVABLE)
    if both:
        raise AssertionError(f"these are both resolvable and a claim: {sorted(both)}")


_check_vocabulary_is_partitioned()
