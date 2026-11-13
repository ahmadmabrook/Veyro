"""MOD-009 SEC-01-R06: what the consent log means, decided without touching the database.

`sec_consent_records` is an append-only log of grants and withdrawals. Nothing stores "this
subject has consented": that state is derived here, every time it is asked for, from the rows.
A stored flag would be a second source of truth beside the evidence, and the two disagree exactly
when it matters -- after a withdrawal that half-committed, or after a document was republished.

The decisions in this module are the ones a court or a regulator asks about, so each says which
source sentence it comes from.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Definition:
    """A consent kind this tenant collects."""

    definition_id: str
    consent_type: str
    requires_guardian: bool
    withdrawable: bool


@dataclass(frozen=True)
class Version:
    """One published document. Consent binds to this, not to the consent kind."""

    consent_version_id: str
    definition_id: str
    version: int
    language: str
    document_hash: str
    effective_from: datetime


@dataclass(frozen=True)
class Record:
    """One grant or withdrawal, as stored."""

    record_id: str
    subject_id: str
    definition_id: str
    consent_version_id: str
    action: str
    signed_at: datetime
    guardian_subject_id: str | None = None


@dataclass(frozen=True)
class State:
    """What is true now about one subject and one consent kind."""

    definition_id: str
    granted: bool
    consent_version_id: str | None
    signed_at: datetime | None
    stale: bool
    """True when consent was given to a version that is no longer the current one.

    Stale is not withdrawn. The subject agreed to something, and that agreement stands for the
    processing it covered; it simply does not extend to a document they have not seen. Collapsing
    the two would either destroy evidence of a real agreement or claim an agreement never made.
    """


class ConsentError(ValueError):
    """A consent record that cannot be written as asked."""


def latest(records: list[Record], definition_id: str) -> Record | None:
    """The record that decides current state: the latest by `signed_at`, ties broken by order.

    Ordering is by when the subject signed, not by when the row was written. A paper waiver
    digitised on Monday was signed on Saturday; if a withdrawal arrived by email on Sunday, the
    withdrawal wins even though its row is older. Sorting by `recorded_at` would get that
    backwards, and it is the ordering a dispute turns on.

    Ties keep the later row in the supplied order. The caller reads in insertion order, so two
    records signed at the same instant resolve to the one recorded second -- arbitrary, but
    deterministic, and an arbitrary rule that is written down beats an arbitrary rule that is not.
    """
    best: Record | None = None
    for record in records:
        if record.definition_id != definition_id:
            continue
        if best is None or record.signed_at >= best.signed_at:
            best = record
    return best


def state_of(
    records: list[Record], definition_id: str, current_version_id: str | None
) -> State:
    """Whether this subject's consent for this kind is in force, and against which document."""
    decisive = latest(records, definition_id)
    if decisive is None or decisive.action == "withdrawn":
        return State(definition_id, False, None, None, stale=False)
    stale = current_version_id is not None and decisive.consent_version_id != current_version_id
    return State(
        definition_id=definition_id,
        granted=True,
        consent_version_id=decisive.consent_version_id,
        signed_at=decisive.signed_at,
        stale=stale,
    )


def current_version(versions: list[Version], definition_id: str, language: str,
                    now: datetime) -> Version | None:
    """The version in force for a language: the highest-numbered one already effective.

    A version with `effective_from` in the future is published but not yet in force, which is how
    a tenant gives notice of a policy change before it takes effect. Consent collected today
    binds today's document, not the one that starts next month.
    """
    candidates = [
        v for v in versions
        if v.definition_id == definition_id and v.language == language and v.effective_from <= now
    ]
    return max(candidates, key=lambda v: v.version) if candidates else None


def check_grant(
    definition: Definition, version: Version, *, guardian_subject_id: str | None,
    subject_id: str, signed_at: datetime, now: datetime,
) -> None:
    """Refuse a grant that would not be evidence of anything. Raises, or returns None.

    Each refusal is a case where storing the row would leave the tenant believing it has consent
    that it does not have, which is worse than having no record at all.
    """
    if version.definition_id != definition.definition_id:
        raise ConsentError("version_belongs_to_another_consent_type")
    if definition.requires_guardian and guardian_subject_id is None:
        # SEC-01-R06 lists health and biometrics among the consent kinds, and TSD paragraph 4382
        # names the guardian in the record. A minor's consent without the guardian who gave it is
        # not consent, and the tenant would have no way to tell afterwards which rows were sound.
        raise ConsentError("guardian_required")
    if guardian_subject_id is not None and guardian_subject_id == subject_id:
        raise ConsentError("guardian_cannot_be_the_subject")
    if signed_at > now:
        # A signature dated in the future is either a clock error or backdating in the wrong
        # direction; either way the ordering rule in `latest` would make it outrank every real
        # record indefinitely.
        raise ConsentError("signed_in_the_future")
    if signed_at < version.effective_from:
        # Signing a document before it existed. This is the one that catches a backdated import
        # being pointed at the wrong version, which otherwise produces a record that looks sound
        # and attests to a document the subject never saw.
        raise ConsentError("signed_before_the_document_was_effective")


def check_withdrawal(definition: Definition, state: State) -> None:
    """Refuse a withdrawal that cannot be honoured, rather than recording a false one.

    A non-withdrawable consent is not a trick: it is the case where the processing has another
    lawful basis and consent was never what permitted it. Terms of service are the usual example
    -- withdrawing them ends the contract, which is a different operation with different
    consequences, and recording it here would tell the subject their data stopped being processed
    when it did not.
    """
    if not state.granted:
        raise ConsentError("not_currently_granted")
    if not definition.withdrawable:
        raise ConsentError("consent_is_not_withdrawable")


def outstanding(
    definitions: list[Definition], versions: list[Version], records: list[Record],
    *, language: str, now: datetime,
) -> list[dict[str, object]]:
    """Every consent kind this subject has not granted against the version now in force.

    This is what a member app asks on sign-in, and what makes a stale consent actionable rather
    than merely recorded.
    """
    rows: list[dict[str, object]] = []
    for definition in definitions:
        in_force = current_version(versions, definition.definition_id, language, now)
        state = state_of(records, definition.definition_id,
                         in_force.consent_version_id if in_force else None)
        if state.granted and not state.stale:
            continue
        rows.append({
            "definition_id": definition.definition_id,
            "consent_type": definition.consent_type,
            "reason": "stale" if state.granted else "never_granted",
            "current_version_id": in_force.consent_version_id if in_force else None,
            "requires_guardian": definition.requires_guardian,
        })
    return rows
