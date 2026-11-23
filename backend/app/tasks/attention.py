"""What an attention item *is*, decided here and with no I/O. ADM-CC-06 and ADM-CC-07.

A case is the record; an attention item is the case read the way the Command Center reads it.
Three things the screens need and the row does not state, so each is a function rather than a
column -- MOD-018's no-stored-balance for the fifth time in this module, after the SLA clock,
the blocking set and `in_window`:

  * **the state**, which is five values the canvas names and two columns plus a viewer;
  * **how long it took**, which is two instants;
  * **the median of those**, which ADM-CC-07 prints as a headline and which a client
    computing it would make a second definition of a figure a manager quotes.

There is deliberately no `is_overdue` here: ADM-TSK-01's Overdue chip counts tasks past
`due_at`, which is a comparison the read does in SQL over the whole queue rather than a
decision about one row.
"""

from __future__ import annotations

from datetime import datetime

#: The five states ADM-CC-06 draws. `resolved` and `snoozed` cannot both hold --
#: `tsk_cases_snooze_is_not_a_resolution` makes the row unwritable -- so the precedence
#: below never has to choose between them, and that is a schema guarantee rather than a
#: convention here.
STATES: tuple[str, ...] = ("unassigned", "mine", "someone_else", "resolved", "snoozed")


class AttentionError(ValueError):
    """A decision this module refuses to make."""


def item_state(
    *, status: str, snoozed_until: datetime | None, now: datetime,
    assignee_person_id: str | None, viewer_person_id: str | None,
) -> str:
    """Which of ADM-CC-06's five states this item is in, for this reader.

    **Lifecycle first, then assignment**, because the sheet's actions differ by lifecycle and
    only its *labels* differ by assignment: a resolved item offers Reopen whoever owns it,
    and a snoozed one shows its reason and return date. Reading it the other way round would
    put a Release button on a case nobody has to look at until Monday.

    **A snooze is derived, never stored.** `status = 'open' AND snoozed_until > now()` is the
    whole definition; the columns are the deferral's account of itself. A fourth status would
    need the forward-only rank in `tsk_case_resolution_is_final` to admit a reversal, and two
    encodings of one rule that disagree is MOD-020's waitlist edge -- from the moment one
    member failed to answer an offer, nobody was promoted again while places sat free.

    **A return date that has passed is not a state.** The item is back in the queue and the
    columns stay, because "this was deferred to Monday and nobody looked" is exactly what a
    manager asks about on Tuesday. Nothing sweeps them, which is why the comparison is here.

    `viewer_person_id` may be None -- a reader with no person record on this tenant -- and
    then an assigned item reads as `someone_else`, which is true: it is not theirs.
    """
    if status != "open":
        return "resolved"
    if snoozed_until is not None and snoozed_until > now:
        return "snoozed"
    if assignee_person_id is None:
        return "unassigned"
    return "mine" if assignee_person_id == viewer_person_id else "someone_else"


def may_act(state: str) -> bool:
    """Whether this reader's own actions are live, as opposed to visible and read-only.

    ADM-CC-06: assigned to someone else "keeps every action visible but read-only, with
    'Nadia is handling this' and a Take over that records the handover." So the actions are
    rendered either way -- hiding them would make the sheet look like a different screen
    depending on who opened it -- and `may_act` decides whether they do anything. Taking
    over is the one act that is live in every state, because it is how a reader *gets* to
    act, and it is not in this function for that reason.
    """
    if state not in STATES:
        raise AttentionError(f"{state!r} is not an attention-item state")
    return state in ("unassigned", "mine")


def took_seconds(*, opened_at: datetime, resolved_at: datetime | None) -> int | None:
    """ADM-CC-07's TOOK column: real elapsed time, not business hours.

    **Deliberately wall-clock, unlike an SLA target.** The SLA is a promise measured against
    what a club said it would be open for; this is "how long did the member wait", and a
    manager reading "41 minutes" against a case opened at eight in the evening means forty-one
    minutes. Measuring it in business hours would make an overnight exception read as having
    been handled instantly.

    None where nothing has been resolved, rather than zero: a case still open has not taken
    any length of time yet, and zero is a case resolved the instant it was raised.
    """
    if resolved_at is None:
        return None
    if resolved_at < opened_at:
        raise AttentionError("a case cannot be resolved before it was opened")
    return int((resolved_at - opened_at).total_seconds())


def median_seconds(values: tuple[int, ...]) -> int | None:
    """ADM-CC-07's "Median 41 minutes", computed where it can be tested.

    **On the server, because a median in a client is a second definition of a figure a
    manager quotes.** MOD-018 shipped two expressions for one till balance and a journal
    dated next year made the drawer balance; `remaining_seconds` is returned rather than
    derived from two instants for the same reason.

    The mean of the two middle values on an even count, floored to the second -- the ordinary
    definition, stated because the alternative (the lower middle) differs by up to a second
    and somebody would eventually notice the two readings disagree. None for an empty window,
    which is MOD-011's rule: nothing resolved is not a median of zero, and a dashboard that
    reported one would read as a team resolving everything instantly.
    """
    if not values:
        return None
    if any(v < 0 for v in values):
        raise AttentionError("a resolution cannot have taken negative time")
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) // 2
