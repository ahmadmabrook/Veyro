"""ADM-CRM-05: what a running trial looks like, decided from what happened.

**The screen is a *state* of ADM-CRM-03 rather than a route of its own**, which the canvas
says by labelling one card with both ids -- "ADM-CRM-03 · LEAD PROFILE · ADM-CRM-05 · TRIAL
RUNNING". So what this module decides is the four figures and the one sentence that appear on
the lead profile while the person is on a trial.

**It describes use and refuses to predict.** The drawn canvas's fourth cell is
`High ENGAGEMENT`; the prototype runtime calls the same cell `CONVERSION LIKELIHOOD`, and that
is a prediction about a person -- which MOD-020 refuses outright for the no-show score, because
"paragraph 1889's 'must not discriminate unlawfully' is a property of a population under a
model rather than of an expression, so no function can promise it". The same reasoning holds
here and the drawn canvas is the deliverable, so this says how much of the trial somebody has
used. That is an observation, and it is what the canvas's own prose argues from: "she has used
the trial more than most -- this is a conversion, not a chase."

**Every figure is inclusive of the day it is counted on**, because the canvas's three numbers
only agree that way: `DAY 6 OF 7` beside `2 DAYS LEFT` beside "her trial ends tomorrow" is a
seven-day trial on its sixth day, with today and tomorrow left. A test pins all three against
one window, because an exclusive count gets two of the three right.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

#: How much of a trial somebody has used, worst to best. A closed set, because a band is
#: rendered as a word and an open one would be a vocabulary the catalogue cannot translate.
ENGAGEMENT = ("none", "light", "steady", "high")

#: Visits per elapsed day at which a trial reads as each band.
#:
#: **A judgement, stated here because the sources state none.** Half the days is the shape of
#: somebody who has made the place part of their week, which is what the canvas's "more than
#: most" is about -- four visits in six days is 0.67. A quarter is somebody who is coming but
#: has not settled into it. Below that is a trial that has been opened and not used, and zero
#: is its own band rather than the bottom of a scale: "nobody has been in" is a different
#: conversation from "they came once".
#:
#: They are deliberately not configurable. A tenant that could move them would be able to
#: report every trial as `high`, and the band is read by a person deciding whether to ring
#: somebody rather than by anything that acts on it.
HIGH_PER_DAY = 0.5
STEADY_PER_DAY = 0.25


class TrialError(ValueError):
    """A trial figure that cannot be computed from the facts given."""


@dataclass(frozen=True)
class Window:
    """The trial's own window, which is `mem_memberships.starts_on` and `ends_on`.

    **Both ends are dates in the club's own zone**, not instants: a trial is a number of days
    and a day is a local fact. MOD-019 paid for the other version.
    """

    starts_on: date
    ends_on: date

    def __post_init__(self) -> None:
        if self.ends_on < self.starts_on:
            raise TrialError("a trial cannot end before it starts")

    @property
    def days(self) -> int:
        """How many days the trial runs for, inclusive of both ends."""
        return (self.ends_on - self.starts_on).days + 1


def day_of(window: Window, today: date) -> int:
    """Which day of the trial today is -- the `6` in "DAY 6 OF 7".

    **Clamped at both ends rather than refused.** A trial read before it starts is day 1 and
    one read after it ends is its last day, because this figure is rendered beside a countdown
    that says the rest: a screen that raised for a lapsed trial would fail on the one state
    ADM-CRM-07 is about.
    """
    if today < window.starts_on:
        return 1
    if today > window.ends_on:
        return window.days
    return (today - window.starts_on).days + 1


def days_left(window: Window, today: date) -> int:
    """Days remaining including today -- the `2` in "2 DAYS LEFT".

    Inclusive, which is the only reading under which the canvas's own three figures agree: on
    day 6 of 7 there are two days left and the trial ends tomorrow.
    """
    if today > window.ends_on:
        return 0
    if today < window.starts_on:
        return window.days
    return (window.ends_on - today).days + 1


def ends_tomorrow(window: Window, today: date) -> bool:
    """Whether the canvas's "Her trial ends tomorrow" is the true sentence."""
    return window.ends_on == today + timedelta(days=1)


def has_lapsed(window: Window, today: date) -> bool:
    """Whether the trial is over. The one state that is not a conversation about converting."""
    return today > window.ends_on


def engagement(*, visits: int, window: Window, today: date) -> str:
    """How much of the trial has been used, as one of `ENGAGEMENT`.

    **Visits rather than classes**, because a visit is the fact that somebody came and a class
    is what they did when they got here: a member who trains in the gym four times is as
    engaged as one who takes four classes, and a band keyed on classes would read the first as
    absent. The class count is a figure beside this one rather than an input to it -- which is
    also what the canvas does, drawing `4 VISITS` and `4 CLASSES` as two cells.

    **Measured over the days elapsed, not over the whole trial.** On day two of seven, two
    visits is somebody who has come every day; measured against seven it is 0.29 and reads as
    light. The canvas's sentence is about what has happened so far, and a band that improved as
    the trial ran out would be useless on the day it matters.
    """
    if visits < 0:
        raise TrialError("a visit count cannot be negative")
    if visits == 0:
        return "none"
    elapsed = day_of(window, today)
    per_day = visits / elapsed
    if per_day >= HIGH_PER_DAY:
        return "high"
    if per_day >= STEADY_PER_DAY:
        return "steady"
    return "light"
