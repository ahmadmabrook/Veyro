"""MOD-009 SEC-01-R05: data classification, and where a subject's data can be reached.

Two registries live here, both in code rather than in a table, for the reason
`app.authorization.catalog` gives for permissions: a classification is a fact about what the
software stores, so a per-tenant table would let two tenants disagree about whether a national id
is restricted and only this file could settle it.

**The class axis is not the kind axis.** MOD-008 already records what *kind* of sensitive
attribute a field is -- financial, biometric, health, identity, contact -- because that is what
its masking decision needs. TSD paragraph 4330 defines something different: four *classes*,
public through restricted, each with a different handling baseline. This module maps one onto the
other rather than listing the fields again, so a field added to the catalogue inherits a class
instead of silently having none.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.authorization.catalog import SENSITIVE_FIELDS

# TSD paragraph 4330, in order of increasing restriction. The order matters: `at_least` compares
# by position, and a control written for `confidential` must also fire for `restricted`.
CLASSES: tuple[str, ...] = ("public", "internal", "confidential", "restricted")

# Mapping MOD-008's kinds onto those classes, using the examples paragraph 4330 gives for each.
# Contact data is named there under Confidential ("Member contact, contracts, business metrics,
# support"); financial, health, biometric and credential data are named under Restricted. Identity
# documents sit with credentials: a passport number is not a contact detail, and a date of birth
# is what distinguishes a minor, which SEC-01-R06 makes a guardian-consent question.
KIND_CLASS: dict[str, str] = {
    "financial": "restricted",
    "biometric": "restricted",
    "health": "restricted",
    "identity": "restricted",
    "contact": "confidential",
}

# What each class requires, from the Baseline column of paragraph 4330. `purpose_required` is the
# operative one in code: paragraph 4383 says "has access is insufficient without permitted purpose
# for restricted data", which is a second gate beyond the permission MOD-008 checks.
PURPOSE_REQUIRED_AT = "restricted"


def classify_field(field: str) -> str:
    """The class of a named field. Ordinary fields are `internal`, never `public`.

    Defaulting an unknown field to `internal` rather than `public` is the fail-closed direction:
    a field nobody has classified yet is at least tenant-scoped and subject to normal retention,
    where `public` would exempt it from both. It is the weakest claim that is still safe, which
    is the right default for a registry somebody will forget to update.
    """
    kind = SENSITIVE_FIELDS.get(field)
    return KIND_CLASS[kind] if kind is not None else "internal"


def at_least(value: str, floor: str) -> bool:
    """Whether `value` is at or above `floor` in the classification order."""
    if value not in CLASSES:
        raise ValueError(f"{value!r} is not a data class")
    if floor not in CLASSES:
        raise ValueError(f"{floor!r} is not a data class")
    return CLASSES.index(value) >= CLASSES.index(floor)


def purpose_required(data_class: str) -> bool:
    """Whether reading this class needs a declared processing purpose, not only a permission."""
    return at_least(data_class, PURPOSE_REQUIRED_AT)


def classify_resource(fields: list[str]) -> str:
    """The class of a record, which is the class of its most restricted field.

    A row holding one restricted field is a restricted row: the handling baseline follows the
    data that needs it most, not the average.
    """
    best = "internal"
    for field in fields:
        candidate = classify_field(field)
        if at_least(candidate, best):
            best = candidate
    return best


# --------------------------------------------------------------------- deletion reachability


@dataclass(frozen=True)
class Reachability:
    """How a subject's rows in one column can be acted on, and why that is the mechanism.

    TSD paragraph 4394 lists delete, anonymize and pseudonymize for PostgreSQL domain rows. Two
    more appear here because this build needs to say two things that list cannot:

    * `covered` -- the row holds no identifying data of its own. It names the subject only by
      `identity_id`, and the row that identifier points at is itself anonymized, so emptying this
      one would destroy a referential link while erasing nothing. A role assignment is the clear
      case: after erasure it says that an anonymous identity once held a role, which is what a
      correctly erased assignment should say.
    * `unreachable` -- no mechanism exists here at all. It is not a way of acting on the row; it
      is the explicit statement that the database refuses to change it, which is the only honest
      thing to record for an insert-only ledger row.

    Three fields say three different things, and keeping them apart is the whole point:

    * `column` is the column that *names a person*. The completeness check enumerates these, so
      every such column in the database must appear here exactly once.
    * `locate_by` is the column an erasure *filters on* to find the subject's rows. It defaults
      to `column` and differs whenever a table names the subject twice: `iam.identities` holds
      both `identity_id` and `person_id`, and a subject is always located by the former.
    * `clears` names the columns actually *overwritten*.

    The first version of this dataclass had `column` doing the first two jobs at once. The
    `person_id` entry then produced `WHERE person_id = <an identity id>`, matched nothing, and
    reported success -- an erasure that silently erased nothing, which is the exact failure the
    registry exists to prevent. `locate_by` exists because of that.
    """

    schema: str
    table: str
    column: str
    mechanism: str
    reason: str
    clears: tuple[str, ...] = ()
    locate_by: str = ""

    def locator(self) -> str:
        """The column to filter on when finding this subject's rows."""
        return self.locate_by or self.column


MECHANISMS = ("delete", "anonymize", "covered", "pseudonymize", "unreachable")

# Every column in either plane that names a natural person: the subject of a request, the
# guardian who signed for them, or the actor who did something. An actor is a data subject too --
# a staff member asking for erasure is asking about exactly these rows.
#
# **What this registry is for.** A deletion request can only be answered honestly if somebody has
# enumerated where the subject's data actually is. `backend/tests/sql/reachability.sql` checks
# this list against the live catalogue in both directions: a subject-bearing column missing from
# here fails, and a declaration that disagrees with the grants fails. A mechanism cannot be
# claimed that the database would refuse.
#
# **Read the `unreachable` entries before extending this.** They are not an oversight. The rows
# they name are insert-only on purpose -- the financial ledger, the audit chain and the
# authentication log carry no UPDATE and no DELETE for any runtime role precisely so that no code
# path can revise them, and that property is load-bearing for financial correctness and for the
# audit chain's tamper evidence. The consequence is stated plainly in CLAUDE.md: **this build
# cannot fully fulfil a deletion request.** Closing it means storing a pseudonym that resolves
# through a mapping which can itself be destroyed -- the subject-envelope crypto-shred paragraph
# 4397 describes -- which is a schema change across MOD-005, MOD-008 and MOD-015 and not
# something to bolt onto the end of this module.
SUBJECT_COLUMNS: tuple[Reachability, ...] = (
    # The identity plane's mutable tables. `veyro_iam_app` holds UPDATE and no DELETE anywhere,
    # by MOD-007's design, so anonymize is the mechanism wherever there is identifying material
    # to destroy. `clears` names exactly what is overwritten.
    #
    # `identities` is the one that matters: emptying it is the erasure, and every other table
    # that names the subject only by `identity_id` is `covered` by it.
    Reachability("iam", "identities", "identity_id", "anonymize",
                 "the row is referenced by every other iam table, so it is emptied, not removed; "
                 "clearing these is what makes the subject anonymous everywhere at once. The "
                 "email is replaced rather than emptied: MOD-007 requires every identity to "
                 "keep at least one identifier, and a row that breaks that invariant is a row "
                 "the rest of the identity plane cannot reason about",
                 clears=("email_normalized", "phone_normalized", "display_name")),
    Reachability("iam", "identities", "person_id", "anonymize",
                 "the cross-tenant link is what joins a person's identities in other tenants; "
                 "severing it is part of the erasure and is done by re-randomising it. Located "
                 "by identity_id, because the value being replaced is the one we are looking up",
                 clears=("person_id",), locate_by="identity_id"),
    Reachability("iam", "credentials", "identity_id", "anonymize",
                 "a password or recovery hash is restricted material in its own right, so it is "
                 "overwritten rather than left pointing at an emptied identity, and revoked in "
                 "the same statement so the row does not read as a live credential that merely "
                 "cannot verify",
                 clears=("salt", "secret_hash", "status", "revoked_at", "consumed_at")),
    Reachability("iam", "devices", "identity_id", "anonymize",
                 "a device fingerprint identifies the person who carries it, and survives the "
                 "identity row being emptied",
                 clears=("fingerprint", "label", "platform")),
    Reachability("iam", "sessions", "identity_id", "anonymize",
                 "a live session must not outlive the erasure, and the token digest is material",
                 clears=("token_hash", "revoked_at", "revoke_reason")),
    Reachability("iam", "passkeys", "identity_id", "anonymize",
                 "a credential id and public key identify the authenticator and through it the "
                 "person",
                 clears=("webauthn_credential_id", "public_key", "aaguid", "label")),
    Reachability("iam", "challenges", "identity_id", "anonymize",
                 "never swept today, so these rows outlive the login that created them",
                 clears=("nonce_hash",)),

    # Covered by the identity row: these name the subject and hold nothing else about them.
    Reachability("iam", "role_assignments", "identity_id", "covered",
                 "after erasure this says an anonymous identity held a role, which is what a "
                 "correctly erased assignment should say"),
    Reachability("iam", "role_assignments", "granted_by", "covered",
                 "the grantor is a subject, and is erased through their own identity row"),
    Reachability("iam", "access_reviews", "opened_by", "covered", "the reviewer is a subject"),
    Reachability("iam", "access_review_items", "decided_by", "covered",
                 "the decider is a subject"),
    Reachability("iam", "approval_requests", "requested_by", "covered",
                 "the requester is a subject"),

    # The identity plane's evidence. No UPDATE and no DELETE, deliberately.
    Reachability("iam", "audit_events", "actor_identity_id", "unreachable",
                 "the hash chain covers this column; changing it would break the chain, which is "
                 "the tamper evidence IAM-03-R06 exists to provide"),
    Reachability("iam", "auth_events", "identity_id", "unreachable",
                 "the authentication log is insert-only so that a successful attacker cannot "
                 "erase their own login"),
    Reachability("iam", "approval_decisions", "decided_by", "unreachable",
                 "who approved what is the separation-of-duties evidence; a decision whose "
                 "decider can be erased cannot be audited"),

    # The tenant plane. Every one of these is unreachable, and the reasons differ.
    Reachability("plt01", "cfg_exposures", "subject_id", "unreachable",
                 "insert-only so a recorded experiment exposure cannot be revised; it is the "
                 "basis of the experiment's analysis"),
    Reachability("plt01", "cfg_values", "published_by", "unreachable",
                 "insert-only so a published configuration version cannot be rewritten"),
    Reachability("plt01", "bil_usage_records", "actor_id", "unreachable",
                 "the metering ledger is insert-only; a quantity that can be revised is not a "
                 "ledger"),
    Reachability("plt01", "bil_subscription_changes", "actor_id", "unreachable",
                 "the subscription history is insert-only so an old invoice stays reconstructible"),
    Reachability("plt01", "bil_credit_notes", "actor_id", "unreachable",
                 "a credit note is a correction to an issued invoice and cannot itself be edited"),
    Reachability("plt01", "sec_consent_records", "subject_id", "unreachable",
                 "the consent record is the evidence that processing was lawful; erasing the "
                 "subject from it destroys the defence of the processing already done"),
    Reachability("plt01", "sec_consent_records", "guardian_subject_id", "unreachable",
                 "same row, same reason: a guardian's signature is part of the evidence"),
    Reachability("plt01", "sec_consent_versions", "published_by", "unreachable",
                 "insert-only so a document somebody agreed to cannot change afterwards"),
    Reachability("plt01", "sec_dsar_requests", "subject_id", "unreachable",
                 "the request's own subject: the UPDATE grant is column-scoped to the state "
                 "machine, so that a deletion request cannot be turned into an access request"),
    Reachability("plt01", "sec_dsar_requests", "opened_by", "unreachable", "same row"),
    Reachability("plt01", "sec_dsar_requests", "identity_verified_by", "unreachable", "same row"),
    Reachability("plt01", "sec_dsar_requests", "legal_checked_by", "unreachable", "same row"),
    Reachability("plt01", "sec_legal_holds", "subject_id", "unreachable",
                 "a hold names who it protects; the UPDATE is scoped to release"),
    Reachability("plt01", "sec_legal_holds", "placed_by", "unreachable", "same row"),
    Reachability("plt01", "sec_incidents", "recorded_by", "unreachable",
                 "insert-only incident evidence"),
    Reachability("plt01", "sec_processing_purposes", "registered_by", "unreachable",
                 "the UPDATE is scoped to retirement"),
    Reachability("plt01", "sec_retention_policies", "set_by", "unreachable",
                 "the UPDATE is scoped to retirement"),
    # The actor columns added when an independent review found that releasing a hold and
    # retiring a purpose were unattributable. They name staff rather than the data subject, and
    # the suffix rule catches them anyway -- which is the rule working. Each is reachable in
    # principle (the column is writable) and unreachable in fact: the writable window closes the
    # moment the value is set, because the same constraint that requires an actor also refuses a
    # second retirement, and the legal-hold trigger refuses any later change at all.
    Reachability("plt01", "sec_processing_purposes", "retired_by", "unreachable",
                 "write-once with the retirement; a second retirement is refused"),
    Reachability("plt01", "sec_retention_policies", "retired_by", "unreachable",
                 "write-once with the retirement; a retired policy is never re-retired"),
    Reachability("plt01", "sec_legal_holds", "released_by", "unreachable",
                 "write-once with the release, and the trigger refuses any later change"),
    Reachability("plt01", "sec_consent_definitions", "defined_by", "unreachable",
                 "the definitions table carries no UPDATE grant at all"),
)


def reachable_columns() -> tuple[Reachability, ...]:
    """The columns an erasure actually acts on: the ones with something to destroy.

    `covered` entries are deliberately not here. They are reached -- the subject is anonymous in
    them once the identity row is emptied -- but nothing is done to them, and a plan that listed
    them as work would overstate what runs.
    """
    return tuple(r for r in SUBJECT_COLUMNS if r.mechanism in ("anonymize", "delete"))


def covered_columns() -> tuple[Reachability, ...]:
    """The columns made anonymous by erasing the identity row they reference."""
    return tuple(r for r in SUBJECT_COLUMNS if r.mechanism == "covered")


def unreachable_columns() -> tuple[Reachability, ...]:
    """The columns it cannot, which is what a completion report has to disclose."""
    return tuple(r for r in SUBJECT_COLUMNS if r.mechanism == "unreachable")


def deletion_is_complete() -> bool:
    """Whether erasure can be total in this build. It cannot, and saying so is the point.

    A caller that reports a deletion request "completed" without consulting this is reporting
    something untrue. `app.privacy.dsar` uses it to decide between `completed` and a partial
    completion that names what survived.
    """
    return not unreachable_columns()
