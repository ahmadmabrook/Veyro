"""MOD-027's pure decisions: the sales stage, the board column, and when a lead goes cold.

**A lead is a `ppl_persons` row and this module is the sales record attached to it.**
ADM-CRM-01 states that as a structural requirement -- "a lead, a trialist and a member are one
record at three stages, never three records" -- so nothing here holds a name, a number or an
address, and nothing here decides anything about a person's identity.

No I/O, no imports beyond the standard library. `service.py` reads the rows and calls these.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


class PipelineError(Exception):
    """A pipeline decision this module refuses to make."""


#: The *sales* stages, which are the ones this module stores. `on_trial` and `joined` are
#: MOD-017's answer and are derived in `board_stage`; `lost` is slice 3's and is deliberately
#: not declared here, because a declared value nothing writes is this build's most-repeated
#: finding -- found in MOD-012, MOD-013, MOD-016, MOD-017, MOD-020 and MOD-022.
STAGES = ("new", "contacted", "toured")

#: **Forward only, and the design gives no affordance for going back.** ADM-CRM-01 draws
#: counts and ADM-CRM-03 draws one next action; neither offers a way to un-reach a stage, and
#: "this lead has toured" is a fact about what happened rather than a status somebody curates.
#: A tour that fell through is a *touchpoint* saying so -- the timeline is where that belongs,
#: and it is the one record ADM-CRM-07 says survives a lead being lost. Stated rather than
#: discovered, because a sales team will ask for the backwards move and the answer is that it
#: would make the board's "Toured · 6" a count nobody can reconstruct.
EDGES: dict[str, tuple[str, ...]] = {
    "new": ("contacted",),
    "contacted": ("toured",),
    "toured": (),
}

#: What the board draws, in its own order. The last two are not stored -- see `board_stage`.
BOARD_COLUMNS = ("new", "contacted", "toured", "on_trial", "joined")

#: ADM-CRM-04's three options, and ADM-CRM-03 renders a *set* of them ("interested in classes
#: and PT"). A closed vocabulary, unlike a source: these are what the business sells rather
#: than where a lead came from.
INTERESTS = ("classes", "pt", "gym_only")

#: What a salesperson can record. `tour` is its own kind rather than a `visit` with prose,
#: because reaching the `toured` stage is the fact the board counts and a kind a report can
#: group by is worth more than a sentence it cannot.
TOUCHPOINT_KINDS = ("call", "message", "email", "visit", "tour", "note")

#: **Forty-eight hours, from the canvas.** ADM-CRM-02's first chip is "No contact 48h · 7" and
#: ADM-CRM-01's header says "36 open leads · 7 going cold", so the two agree and this is the
#: figure behind both. A tenant may well want it configurable; nothing in this build carries a
#: CRM setting, and inventing one before a screen asks for it would be inventing product.
GOING_COLD_AFTER = timedelta(hours=48)


@dataclass(frozen=True)
class Membership:
    """What MOD-017 says about this person, reduced to the two facts the board needs.

    `service.py` builds it from a membership read. Kept as a value rather than passed as two
    booleans so a caller cannot supply "on a trial" and "not on a trial" at once.
    """

    active: bool
    on_trial_product: bool


def check_transition(from_stage: str, to_stage: str) -> None:
    """Refuse a stage move the pipeline does not admit.

    Written against `EDGES` rather than as a chain of `if`s, so a mutation sweep can read the
    table and a reader sees the whole machine at once -- MOD-017's `lifecycle.EDGES` idiom.
    """
    if from_stage not in STAGES:
        raise PipelineError(f"{from_stage!r} is not a sales stage")
    if to_stage not in STAGES:
        raise PipelineError(f"{to_stage!r} is not a sales stage")
    if to_stage not in EDGES[from_stage]:
        raise PipelineError(f"a lead does not move from {from_stage} to {to_stage}")


def board_stage(stage: str, membership: Membership | None) -> str:
    """Which of ADM-CRM-01's five columns this lead belongs in.

    **The last two columns are MOD-017's answer, not a stored value.** "On trial" is "this
    person has an active membership on a trial product" and "Joined" is "... on one that is
    not"; a stored `on_trial` would be a second definition of whether somebody has a
    membership and would go stale the moment a trial lapsed -- MOD-018's
    one-module-two-definitions finding, created on purpose.

    **A membership outranks the sales stage**, because it is the later fact: a lead whose
    stage still reads `contacted` because nobody moved it, and who has since bought a
    membership, is a member. The sales stage is what somebody typed; the membership is what
    happened.
    """
    if stage not in STAGES:
        raise PipelineError(f"{stage!r} is not a sales stage")
    if membership is not None and membership.active:
        return "on_trial" if membership.on_trial_product else "joined"
    return stage


#: ADM-CRM-07's four, and nothing else. ADR-0010 D9: closed because the one thing the field
#: exists for is a report, and a group-by needs a closed set -- free text makes it a group-by
#: over typos. The same four are a CHECK on the column and a test compares the two, which is
#: MOD-026's precedent for a vocabulary in both places.
#:
#: **No screen reads it yet.** ADM-CRM-07's footnote sends the reason to "source effectiveness
#: in ADM-RPT-03", and that screen is the *membership* report: it draws "WHY THE 23 LEFT" from
#: "ADM-MSH-07's required field" -- members cancelling, not leads who never joined. ADR-0010's
#: build order names ADM-RPT-06, which the registry does not contain. So the destination is
#: undrawn and the closed set stands on its own reasoning.
#:
#: **There is no "Other".** The canvas draws four and no catch-all; `no_longer_responding` is
#: the one that absorbs a lead who simply stopped, and `lost_detail` is where a salesperson
#: writes what they actually learned. A fifth is a product decision, not a migration.
LOST_REASONS = (
    "too_expensive", "joined_elsewhere", "location_or_hours", "no_longer_responding")

#: When a lost lead becomes worth another try. ADR-0010 D10: the canvas says "re-contact after
#: 90 days is a supported flow rather than a fresh record", and the emphasis is on *rather than
#: a fresh record* -- the point is that re-contact does not duplicate the person, which the
#: one-lead-per-person index already enforces. Ninety days is when it becomes appropriate.
RECONTACT_AFTER = timedelta(days=90)


def check_lost_reason(reason: str) -> str:
    """One of `LOST_REASONS`, refused at the boundary rather than left to the CHECK.

    A reason reaching the column is a `CheckViolation` the handlers turn into a 422 anyway; a
    route that refuses first names the request instead, which is what the one person who could
    fix it would read.
    """
    if reason not in LOST_REASONS:
        raise PipelineError(f"{reason!r} is not one of the four reasons ADM-CRM-07 offers")
    return reason


def is_recontactable(*, lost_at: datetime | None, now: datetime) -> bool:
    """Whether a lost lead has been lost long enough to be worth another try.

    **Advisory, never a lock.** ADR-0010 D10: reopening is always permitted, because locking
    it for ninety days would make a lead marked lost by mistake uncorrectable for a quarter on
    a routine permission -- which is MOD-013's "an irreversible act must not be declarable on a
    routine permission", and this slice is the one that owes the same remedy to
    `crm_lead_interests`. So this answers a read and gates nothing.
    """
    if lost_at is None:
        return False
    return now - lost_at >= RECONTACT_AFTER


def is_going_cold(
    *, last_touch_at: datetime | None, created_at: datetime, now: datetime,
    lost_at: datetime | None = None,
) -> bool:
    """Whether this lead has had no contact for `GOING_COLD_AFTER`.

    **A lead nobody has ever touched is counted from when it was created**, which is the
    uncomfortable direction and the right one: the canvas's own example is "Rana Sabbagh NO
    CONTACT · 2 DAYS" beside "open day · 2d", so the badge is about the lead's age where there
    is no touchpoint. Treating an untouched lead as warm would hide exactly the ones the chip
    exists to surface -- the opposite of MOD-014's "an unknown birth date is not a minor",
    because here the absence *is* the signal rather than a gap in what is known.

    **And a lost lead is never going cold**, which is why this takes `lost_at`. Nobody has
    failed to ring them: they said no, and the reason is on the record. Counting them would
    put every refusal into the one chip that exists to surface a lead somebody has forgotten,
    which is the number a manager acts on first.
    """
    if lost_at is not None:
        return False
    since = last_touch_at if last_touch_at is not None else created_at
    return now - since >= GOING_COLD_AFTER


def hours_since_contact(
    *, last_touch_at: datetime | None, created_at: datetime, now: datetime,
) -> int:
    """Whole hours since the last touchpoint, or since the lead was created.

    Whole hours because the card draws "4h" and "2d" and this app has one number path --
    `formatInteger` throws for a fraction, which cost a 500 on a rendered page once.
    """
    since = last_touch_at if last_touch_at is not None else created_at
    seconds = (now - since).total_seconds()
    return max(0, int(seconds // 3600))


def check_interests(interests: tuple[str, ...]) -> tuple[str, ...]:
    """The declared interests, de-duplicated, in the vocabulary's own order.

    **`gym_only` is not combined with the other two**, which the words themselves say: a lead
    interested in classes is not interested in the gym *only*. ADM-CRM-04 draws three options
    and ADM-CRM-03 renders "interested in classes and PT", so the set is real and this is the
    one pair it cannot contain -- refused rather than silently dropped, because a form that
    quietly discarded a tick would be lying about what it recorded.
    """
    for interest in interests:
        if interest not in INTERESTS:
            raise PipelineError(f"{interest!r} is not an interest")
    chosen = tuple(i for i in INTERESTS if i in interests)
    if "gym_only" in chosen and len(chosen) > 1:
        raise PipelineError("gym_only_is_not_combined_with_another_interest")
    return chosen


def stage_from_touchpoint(stage: str, kind: str) -> str:
    """The stage a touchpoint of this kind moves a lead to, or the stage it is already at.

    **The board's first two moves are facts somebody records, not buttons.** A lead that has
    been called is `contacted` and one that has toured is `toured`, so recording the
    touchpoint is the move -- which is what keeps the count on the board and the timeline on
    the profile from disagreeing. The caller still has an explicit stage command for the
    cases a touchpoint does not cover.

    It never moves a lead *back*: a note on a toured lead leaves it toured, because `EDGES`
    has no reverse edge and this function would otherwise be the one writer that defeats it.
    """
    if kind not in TOUCHPOINT_KINDS:
        raise PipelineError(f"{kind!r} is not a touchpoint kind")
    if stage not in STAGES:
        raise PipelineError(f"{stage!r} is not a sales stage")
    reached = "toured" if kind == "tour" else "contacted"
    return reached if STAGES.index(reached) > STAGES.index(stage) else stage
