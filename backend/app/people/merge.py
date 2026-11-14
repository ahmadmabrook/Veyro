"""MOD-014 PPL-01-R04: what a merge is allowed to do, and what it must leave behind.

Paragraph 10200: "merges are reviewable, reversible where feasible and fully audited." Three
words, and each one is a constraint on the shape of the operation:

* **Reviewable** means a human decides. `dedup.AUTO_MERGE_THRESHOLD` is `None` on purpose.
* **Reversible where feasible** means the merge records what it moved, so the reversal knows what
  to put back. A merge that just rewrote foreign keys and left no record would be irreversible
  in practice even where it was reversible in principle.
* **Fully audited** means the provenance row survives the reversal. `ppl_merges` has no DELETE
  grant, so "was this person ever merged, by whom, on what evidence" stays answerable after
  somebody undoes it -- which is the half a tidy-up would destroy.

**The survivor is chosen, not computed.** An operator says which record wins, because the
machine cannot know that the one with more data is the right one -- the richer record is
routinely the duplicate somebody created by accident and then used for a month. What this module
does is refuse the merges that would corrupt something, and say what a merge of these two would
move so the operator can see it before agreeing.

**Nothing is deleted.** The losing person keeps its row with `merge_status = 'merged'` and a
pointer at the survivor, because every booking, invoice and audit entry in every other module
references it by id, and this module has no way to find them -- paragraph 1300 forbids
cross-domain write-table access, so a merge that rewrote other modules' rows would be exactly
the thing the architecture bans. Readers follow the pointer instead. That is what makes the
merge reversible at all.
"""

from __future__ import annotations

from dataclasses import dataclass


class MergeError(ValueError):
    """A merge this module will not perform."""


@dataclass(frozen=True)
class MergePlan:
    """What a merge would do, before it does it."""

    source_person_id: str
    target_person_id: str
    #: Named counts, so an operator sees the size of the change. The reversal reads these back.
    contact_points: int = 0
    relationships: int = 0
    notes: int = 0
    tags: int = 0
    custom_fields: int = 0
    #: Things the merge will *not* move, with a reason each. An operator agreeing to a merge is
    #: entitled to know what gets left behind rather than discovering it afterwards.
    retained: tuple[str, ...] = ()


def check_merge(
    *, source_person_id: str, target_person_id: str, source_status: str, target_status: str,
    source_has_identity_link: bool, target_has_identity_link: bool, reason: str,
) -> None:
    """Refuse the merges that would corrupt something. Everything else is the operator's call.

    Five refusals:

    1. **Nothing merges into itself.** A cycle of length one strands every reference that
       follows the pointer.
    2. **Neither side may already be merged.** Merging into a record that is itself merged away
       builds a chain, and a chain means a reader following one pointer still lands on a dead
       record; reversing the middle link would then be ambiguous about what it restores.
    3. **Two sign-in identities cannot become one person.** MOD-007 is a separate plane and this
       module cannot revoke a session there, so a merge that left two identities pointing at one
       person would mean two people logging in as each other -- the worst outcome available
       here. The operator has to decide which identity survives and unlink the other first,
       which is a MOD-007 action with its own audit trail.
    4. **A merge states a reason**, because it is the one operation in this module that makes a
       record stop being usable and somebody will ask about it.
    5. (Implicit, enforced by the caller) the operator holds the merge permission, which is
       financial class, so an AAL-1 session cannot do this at all.
    """
    if source_person_id == target_person_id:
        raise MergeError("a_person_cannot_be_merged_into_themselves")
    if source_status != "active":
        raise MergeError("the_source_person_is_already_merged")
    if target_status != "active":
        raise MergeError("the_target_person_is_already_merged")
    if source_has_identity_link and target_has_identity_link:
        raise MergeError(
            "both_people_have_a_sign_in_identity_so_one_must_be_unlinked_first"
        )
    if not reason.strip():
        raise MergeError("a_merge_states_a_reason")


def check_reversal(*, reversed_at: object, source_status: str, reason: str) -> None:
    """Refuse a reversal that has already happened, or one of a merge that did not.

    A reversal of a reversal is not an idempotent repeat: the second caller believes it is
    undoing something, and succeeding silently would tell them the person was restored when
    somebody else had already restored and possibly re-merged them.
    """
    if reversed_at is not None:
        raise MergeError("this_merge_has_already_been_reversed")
    if source_status != "merged":
        raise MergeError("the_source_person_is_not_merged")
    if not reason.strip():
        raise MergeError("a_reversal_states_a_reason")


def plan_retentions(
    *, source_has_member_profile: bool, target_has_member_profile: bool,
    source_has_staff_profile: bool, target_has_staff_profile: bool,
    source_member_number: str | None,
) -> tuple[str, ...]:
    """What a merge of these two leaves behind, each with the reason.

    **The profiles do not merge, and this is the part that surprises people.** A member profile
    and a staff profile are one per person by unique constraint, so when both sides have one
    there is no way to combine them without choosing which lifecycle state and which member
    number survive -- and either choice silently rewrites a fact somebody relies on. The
    target's profile stands; the source's stays attached to the merged-away person where it is
    still readable, and the counts say so.

    A member number is the sharpest case: COM-01's agreements, a turnstile and a printed card may
    all carry it, so reassigning it would point physical things at a different person. It stays
    with the record it was issued to.
    """
    retained: list[str] = []
    if source_has_member_profile and target_has_member_profile:
        retained.append(
            "the source member profile stays with the merged-away person: lifecycle state and "
            "member number cannot be combined without silently choosing one"
        )
    if source_has_staff_profile and target_has_staff_profile:
        retained.append(
            "the source staff profile stays with the merged-away person: two employment "
            "histories are two periods, not one"
        )
    if source_member_number is not None:
        retained.append(
            f"member number {source_member_number} stays with the merged-away person: "
            "agreements, cards and turnstiles may carry it"
        )
    return tuple(retained)


def survivor_of(chain: dict[str, str | None], person_id: str) -> str:
    """Follow the merge pointers to the record that is still active.

    `chain` maps a person to the person it was merged into, or `None` when it is active. A
    reader handed an id that was merged away a year ago has to land on the survivor, and the
    constraint that forbids merging an already-merged record keeps this short in practice -- but
    a reversal followed by a new merge can lengthen it, so this walks rather than taking one
    step.

    **Cycle-safe, because a cycle here is an infinite loop in a read path.** The schema forbids
    the length-one case and `check_merge` forbids the ordinary way to build a longer one, which
    is exactly the argument that would leave this function trusting an invariant it cannot see.
    """
    seen = {person_id}
    current = person_id
    while True:
        nxt = chain.get(current)
        if nxt is None:
            return current
        if nxt in seen:
            raise MergeError(f"the merge chain through {person_id} is a cycle")
        seen.add(nxt)
        current = nxt
