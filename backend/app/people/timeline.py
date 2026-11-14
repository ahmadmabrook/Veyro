"""MOD-014 PPL-01-R03: which domain events become timeline entries, and what they say.

Paragraph 4223: "timeline is a projection of selected domain events into human-readable entries.
It is not the source of truth for domain state." Paragraph 4021: "timeline projections store
user-safe event summaries, not raw event payloads." Paragraph 4224: each item "references the
authoritative aggregate/event and applies permission/field masking at read time."

Those three sentences decide everything here:

* **Selected.** A projection of every event would be a second copy of the event log with a
  different retention policy and no owner. `PROJECTED` is the list, and it is short.
* **A summary, not a payload.** Each entry is one sentence, rendered here from named fields of
  the event. The renderer takes only the fields it names, so an event that grows a field does
  not grow the timeline -- which is the mechanism that makes "user-safe" true rather than hoped
  for. MOD-010's review found a caller-chosen string inside `jsonb` carrying a date of birth
  into a store nothing could erase from; a timeline that copied payloads would repeat it.
* **Masked at read time, not at projection time.** The entry carries the visibility class and
  the read path applies the mask, because the caller's permissions are not known when the
  projection runs -- and baking one reader's view into the stored row would make the projection
  wrong for every other reader.

**A summary names no value from a restricted class.** `check_summary_fields` refuses a renderer
that reads one, at import, so a future entry cannot put a health note or a national id into a
sentence this module stores. The class on the entry says a restricted *thing happened*; reading
what it was means going to the module that owns it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.authorization.catalog import SENSITIVE_FIELDS
from app.events.catalog import EVENT_TYPES
from app.people import visibility


class TimelineError(ValueError):
    """A timeline projection input this module will not accept."""


@dataclass(frozen=True)
class Projection:
    """How one event type becomes one timeline entry."""

    event_type: str
    #: Which of MOD-008's classes reading this entry needs. `none` means it rides with the
    #: timeline permission.
    visibility_class: str
    #: The payload fields the summary is rendered from. Named, so nothing else can reach it.
    fields: tuple[str, ...]
    #: The person the entry belongs to, as a payload field name. A projection whose event does
    #: not name a person cannot be attached to anybody's timeline.
    subject_field: str
    render: Callable[[dict[str, Any]], str]


def _person_created(p: dict[str, Any]) -> str:
    return "Person record created"


def _profile_updated(p: dict[str, Any]) -> str:
    changed = p.get("changed_fields") or ()
    names = ", ".join(sorted(str(f) for f in changed)) if changed else "details"
    return f"Profile updated: {names}"


def _lifecycle_changed(p: dict[str, Any]) -> str:
    return f"Membership status changed from {p.get('from_state')} to {p.get('to_state')}"


def _person_merged(p: dict[str, Any]) -> str:
    return "Duplicate record merged into this one"


def _relationship_created(p: dict[str, Any]) -> str:
    return f"Relationship added: {str(p.get('kind', '')).replace('_', ' ')}"


#: The events that reach a member's timeline. **Short on purpose.**
#:
#: PPL-01's own five, plus the four MOD-009 events that are about a person and that a member is
#: entitled to see on their own record -- a consent they gave and a request they filed are
#: theirs, and a timeline that omitted them would make the privacy surface the only place to
#: find them.
#:
#: Deliberately absent: everything from MOD-013, MOD-011, MOD-012 and MOD-005. A notification
#: being sent is a delivery record, not a life event, and one entry per notification would bury
#: the five that matter under thousands. When a module wants its events on the timeline it adds
#: a `Projection` here with a summary somebody wrote, which is the review point.
PROJECTED: dict[str, Projection] = {
    p.event_type: p
    for p in (
        Projection("person.created", "none", ("person_id",), "person_id", _person_created),
        Projection("profile.updated", "none", ("person_id", "changed_fields"), "person_id",
                   _profile_updated),
        Projection("member.lifecycle.changed", "none",
                   ("person_id", "from_state", "to_state"), "person_id", _lifecycle_changed),
        Projection("person.merged", "none", ("target_person_id",), "target_person_id",
                   _person_merged),
        Projection("relationship.created", "none", ("from_person_id", "kind"),
                   "from_person_id", _relationship_created),
        # **MOD-009's four consent and DSAR events are deliberately absent**, and the first
        # version projected them. Two things were wrong with that and a reviewer found both:
        # their `subject_id` is an `identity_id` rather than a `person_id`, so every one was
        # skipped on every run while still occupying a slot in the projection window; and they
        # declared `purpose_code` and `request_type`, which those events do not carry -- so the
        # one that did land stored `Consent granted for None` into a table with no UPDATE grant.
        #
        # Reaching them needs a join through `ppl_identity_links`, which is a different shape of
        # projection from "this event names a person"; `member_360` counts the records instead.
        # The import-time check below now refuses a projection whose fields MOD-010's catalogue
        # does not declare, so this cannot recur by being written back in.
    )
}

#: The longest a stored summary may be. A sentence, not a paragraph: an entry long enough to
#: hold a note is an entry somebody will put a note in.
MAX_SUMMARY = 200


def check_summary_fields() -> None:
    """Refuse a projection that cannot work, at import. Three rules.

    **One: no field MOD-008 classifies as sensitive.** The same rule MOD-010 applies to event
    payloads, one layer further on, and for a sharper reason -- an event is at least erasable in
    principle, while `ppl_timeline_entries` has no UPDATE grant at all. A summary that quoted a
    health note would be the least erasable copy of it in the build.

    **Two: the event type exists and declares every field this projection reads.** Missing, the
    first version declared `purpose_code` on `consent.granted`, which that event does not carry
    -- so `render` was handed `None` and stored the sentence `Consent granted for None` into a
    table nothing can rewrite. This is the import-time compatibility check MOD-010 applies to
    its own catalogue, which this module's docstring invokes and did not perform.

    **Three: the subject field is one of those declared fields**, so a projection cannot be
    attached to a person the event never names.

    Enforced where the projection is written rather than where it runs, because the person
    adding a field to a renderer is the person who can still choose a different one.
    """
    for projection in PROJECTED.values():
        declared = EVENT_TYPES.get((projection.event_type, 1))
        if declared is None:
            raise TimelineError(
                f"{projection.event_type} is not an event MOD-010's catalogue declares at "
                f"version 1, so nothing will ever produce it"
            )
        for field in projection.fields:
            if field in SENSITIVE_FIELDS:
                raise TimelineError(
                    f"{projection.event_type} reads {field!r}, which MOD-008 classifies as "
                    f"{SENSITIVE_FIELDS[field]}: a timeline summary cannot carry it"
                )
            if field not in declared.fields:
                raise TimelineError(
                    f"{projection.event_type} reads {field!r}, which that event does not "
                    f"carry: the summary would render it as None into a table with no UPDATE "
                    f"grant"
                )
        if projection.subject_field not in projection.fields:
            raise TimelineError(
                f"{projection.event_type}'s subject field {projection.subject_field!r} is not "
                f"one of the fields it declares"
            )
        visibility.check_class(projection.visibility_class)


check_summary_fields()


def project(event_type: str, payload: dict[str, Any]) -> tuple[str, str, str] | None:
    """One event in, `(person_id, summary, visibility_class)` out -- or `None` to skip it.

    `None` rather than an exception for an unprojected type, because the projector runs over
    every event in the outbox and most of them are not about a person. An exception would make
    the ordinary case an error path.

    A projected event whose payload is missing the subject field *is* an error: the projection
    declared that field and the producer stopped sending it, which is the compatibility break
    MOD-010's catalogue is supposed to prevent. Failing loudly here is how it gets noticed.
    """
    projection = PROJECTED.get(event_type)
    if projection is None:
        return None
    subject = payload.get(projection.subject_field)
    if not subject:
        raise TimelineError(
            f"{event_type} carries no {projection.subject_field}, so it cannot be projected "
            f"onto anybody's timeline"
        )
    # Only the declared fields reach the renderer. An event that grows a field does not grow the
    # timeline, which is what makes "user-safe summary" a mechanism rather than an intention.
    narrowed = {name: payload.get(name) for name in projection.fields}
    summary = projection.render(narrowed).strip()
    if not summary:
        raise TimelineError(f"{event_type} rendered an empty summary")
    return str(subject), summary[:MAX_SUMMARY], projection.visibility_class
