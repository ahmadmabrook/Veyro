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


MECHANISMS = ("delete", "anonymize", "covered", "pseudonymize", "unreachable", "write_once")
#: `write_once` exists because `unreachable` was being claimed for columns the database *can*
#: write. An independent reviewer showed two MOD-010 entries declaring "the database refuses to
#: change it" over columns sitting in a column-scoped UPDATE grant, with nothing but a service
#: predicate between them and a rewritten record -- application convention, which is exactly
#: what this registry exists not to rely on.
#:
#: The distinction that matters to erasure is the same for both: no erasure path touches the
#: column. The distinction that matters to a reviewer is not. `unreachable` means the grants
#: make the column immutable, and the test asserts that. `write_once` means a service writes it
#: once under a predicate and no erasure path clears it, and the test asserts the grant exists
#: and that nothing claims to clear it -- an honest, weaker statement rather than a false strong
#: one.

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
    # `write_once`, not `unreachable`: these columns sit in `sec_dsar_requests`'s
    # column-scoped UPDATE grant, so the database does not refuse to change them -- the request
    # state machine does. Written as `unreachable` before the registry's test could tell the
    # difference, and found when it could.
    Reachability("plt01", "sec_dsar_requests", "identity_verified_by", "write_once",
                 "written when the gate passes; guarded by the state machine, not by the grant"),
    Reachability("plt01", "sec_dsar_requests", "legal_checked_by", "write_once",
                 "written when the gate passes; guarded by the state machine, not by the grant"),
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
    Reachability("plt01", "sec_processing_purposes", "retired_by", "write_once",
                 "written with the retirement; `retired_at IS NULL` in the service is what "
                 "refuses a second one, not the grant"),
    Reachability("plt01", "sec_retention_policies", "retired_by", "write_once",
                 "written with the retirement; the service retires the live policy only"),
    # The one actual `unreachable` among the actor columns, and the only one backed by
    # something the database enforces: `sec_legal_holds_release_is_final` refuses any change to
    # a released row. The column is in the UPDATE grant, so the registry's test allows this
    # entry only because the trigger exists and the reason says so.
    Reachability("plt01", "sec_legal_holds", "released_by", "unreachable",
                 "written with the release, and a BEFORE UPDATE trigger refuses any later "
                 "change to a released hold"),
    Reachability("plt01", "sec_consent_definitions", "defined_by", "unreachable",
                 "the definitions table carries no UPDATE grant at all"),
    # MOD-010. `evt_outbox.actor_id` is the one here that can name the data subject rather than
    # a member of staff: an event about somebody's own action carries them as the actor. It is
    # unreachable all the same, and that is the honest answer rather than a comfortable one --
    # a published event has been fanned out to consumers and archived, and rewriting the copy
    # in this table would not reach any of them. The catalogue's own rule is what keeps the
    # residue small: a payload may not carry a restricted field, so what survives here is an
    # identifier and not a person's details.
    Reachability("plt01", "evt_outbox", "actor_id", "unreachable",
                 "an appended event is history; no UPDATE grant on this column"),
    # Declared by hand, because the completeness sweep cannot see it: the subject identifier is
    # inside a `jsonb` column, and that sweep matches column *names*. Five wired producers put a
    # `subject_id` in here -- consent granted and withdrawn, both DSAR events, and the
    # experiment exposure (hashed). The residue report would otherwise name `actor_id` and stay
    # silent about the newest and largest store of subject identifiers in the build, which is a
    # residue list that reports something untrue. Found by review.
    Reachability("plt01", "evt_outbox", "payload", "unreachable",
                 "an appended event is history; no UPDATE grant on this column, and no DELETE "
                 "for any runtime role on the table"),
    Reachability("plt01", "evt_subscriptions", "registered_by", "unreachable",
                 "the UPDATE is scoped to activation and the retry budget"),
    # `write_once`, not `unreachable`: both columns are in the runtime roles' column-scoped
    # UPDATE grant, so the database does **not** refuse to change them -- only a service
    # predicate (`AND active`, `AND released_at IS NULL`) does, and MOD-010 defines no trigger
    # of the kind `sec_legal_holds` has. These two entries claimed otherwise and a reviewer
    # rewrote both columns as `veyro_cp_app` to prove it.
    Reachability("plt01", "evt_subscriptions", "deactivated_by", "write_once",
                 "written with the deactivation and cleared only by a reactivation; no erasure "
                 "path touches it, and the grant is column-scoped rather than absent"),
    Reachability("plt01", "evt_dead_letters", "released_by", "write_once",
                 "written with the release; guarded by `released_at IS NULL` in the service "
                 "rather than by the database, which is the honest statement"),
    Reachability("plt01", "evt_replay_jobs", "requested_by", "unreachable",
                 "a replay job's terms are fixed when it is requested; no UPDATE grant on this "
                 "column"),
    # MOD-011. Measurements and evidence carry the actor who recorded them; the two
    # registries carry the actor who retired or disabled an entry. None is an erasure
    # target, and the sweep found every one of them by the `_by` suffix rule -- which is
    # the rule doing its job on a module still being written.
    Reachability("plt01", "ops_budgets", "retired_by", "write_once",
                 "written with the retirement or disable; the service moves the live row only"),
    Reachability("plt01", "ops_budgets", "set_by", "unreachable",
                 "insert-only measurement or evidence; no UPDATE grant on this column"),
    Reachability("plt01", "ops_capacity_forecasts", "forecast_by", "unreachable",
                 "insert-only measurement or evidence; no UPDATE grant on this column"),
    Reachability("plt01", "ops_cost_records", "allocated_by", "unreachable",
                 "insert-only measurement or evidence; no UPDATE grant on this column"),
    Reachability("plt01", "ops_objectives", "retired_by", "write_once",
                 "written with the retirement or disable; the service moves the live row only"),
    Reachability("plt01", "ops_objectives", "set_by", "unreachable",
                 "insert-only measurement or evidence; no UPDATE grant on this column"),
    Reachability("plt01", "ops_synthetic_checks", "disabled_by", "write_once",
                 "written with the retirement or disable; the service moves the live row only"),
    Reachability("plt01", "ops_synthetic_checks", "registered_by", "unreachable",
                 "insert-only measurement or evidence; no UPDATE grant on this column"),
    # Added after review, with the column it declares. The comment above said measurements
    # carry the actor who recorded them, and this was the one table where that was untrue --
    # the one whose own module docstring names a fabricated `passed` as the risk.
    Reachability("plt01", "ops_synthetic_results", "recorded_by", "unreachable",
                 "insert-only measurement or evidence; no UPDATE grant on this column"),
    # MOD-012. An install, a connection and a credential reference each record the actor who
    # made the decision, because the question after an incident is always who gave a third
    # party access and when. `write_once` where a lifecycle column carries the grant that
    # writes it once; `unreachable` where there is no UPDATE grant at all.
    Reachability("plt01", "int_installs", "installed_by", "unreachable",
                 "insert-only decision; no UPDATE grant on this column"),
    Reachability("plt01", "int_installs", "uninstalled_by", "write_once",
                 "written with the uninstall; `state = 'uninstalled'` in the service is what "
                 "refuses a second one, not the grant"),
    Reachability("plt01", "int_connections", "authorized_by", "write_once",
                 "written when the connection is authorized; the lifecycle machine is what "
                 "refuses a second authorization, not the grant"),
    Reachability("plt01", "int_connections", "validated_by", "write_once",
                 "written on each validation, which is deliberately repeatable: a connection "
                 "validated this morning and one validated a year ago are different facts"),
    Reachability("plt01", "int_connections", "revoked_by", "write_once",
                 "written with the revocation; `revoked_at IS NULL` in the service is what "
                 "refuses a second one, not the grant"),
    Reachability("plt01", "int_credential_refs", "recorded_by", "unreachable",
                 "insert-only evidence; a rotation is a new row and no UPDATE grant reaches "
                 "this column"),
    Reachability("plt01", "int_sync_cursors", "reset_by", "write_once",
                 "written with each reset, which is repeatable by design: re-reading a window "
                 "twice is two decisions somebody made"),
    Reachability("plt01", "int_connector_runs", "started_by", "unreachable",
                 "insert-only evidence; no UPDATE grant on this column"),
    # MOD-013. A notification is the one place this build stores what a tenant said to a
    # person, and the recipient is named on four tables. None is an erasure target today:
    # the authored message carries no UPDATE grant at all (paragraph 2474 -- "delivery failure
    # never rewrites the authored message"), and no runtime role holds DELETE anywhere in the
    # module. That is a real residue and it is disclosed rather than glossed.
    Reachability("plt01", "ntf_notifications", "recipient_id", "unreachable",
                 "the authored message is insert-only; no UPDATE grant on this column -- and "
                 "the row it keeps alive carries `rendered_subject` and `rendered_body`, so "
                 "the full text of every message ever sent to this person survives verbatim "
                 "beside the identifier"),
    Reachability("plt01", "ntf_notifications", "requested_by", "unreachable",
                 "the authored message is insert-only; no UPDATE grant on this column"),
    Reachability("plt01", "ntf_preferences", "recipient_id", "unreachable",
                 "a preference's subject is its identity; no UPDATE grant on this column"),
    Reachability("plt01", "ntf_preferences", "set_by", "write_once",
                 "rewritten on each change, because setting a preference again is a new act "
                 "by whoever did it"),
    Reachability("plt01", "ntf_digests", "recipient_id", "unreachable",
                 "a digest's subject is its identity; no UPDATE grant on this column"),
    Reachability("plt01", "ntf_templates", "authored_by", "unreachable",
                 "insert-only authorship; no UPDATE grant on this column"),
    Reachability("plt01", "ntf_templates", "approved_by", "write_once",
                 "written with the approval; `approved_at IS NULL` in the service is what "
                 "refuses a second one, not the grant"),
    Reachability("plt01", "ntf_channel_policies", "set_by", "write_once",
                 "rewritten on each change, as the preference's is"),
    Reachability("plt01", "ntf_suppressions", "recorded_by", "unreachable",
                 "insert-only evidence; no UPDATE grant on this column"),
    Reachability("plt01", "ntf_suppressions", "released_by", "write_once",
                 "written with the release; `released_at IS NULL` in the service is what "
                 "refuses a second one, not the grant"),
    # **Declared by hand, because no sweep matching column names would find it.** A digest of
    # `channel:address` is how this module remembers a bounce and matches a recipient without
    # holding a contact address -- but it is *pseudonymous, not anonymous*: somebody with a
    # candidate address can test it. Neither table carries UPDATE on it or DELETE at all, so an
    # erasure leaves it, and a residue report that omitted it would understate what survives.
    Reachability("plt01", "ntf_notifications", "address_digest", "unreachable",
                 "a SHA-256 of channel:address, held so a bounce can be remembered without a "
                 "contact address; pseudonymous rather than anonymous, and no runtime role can "
                 "update or delete it"),
    Reachability("plt01", "ntf_suppressions", "address_digest", "unreachable",
                 "the suppression list is keyed on this digest, so clearing it would resume "
                 "sending to an address that bounced or complained; no UPDATE grant"),
    Reachability("plt01", "ntf_recipient_channels", "recipient_id", "unreachable",
                 "the binding's subject is its identity; no UPDATE grant on this column"),
    Reachability("plt01", "ntf_recipient_channels", "bound_by", "unreachable",
                 "insert-only attribution; no UPDATE grant on this column"),
    Reachability("plt01", "ntf_recipient_channels", "rebound_by", "write_once",
                 "written with the rebinding, which is a fresh act by whoever did it"),
    Reachability("plt01", "ntf_recipient_channels", "address_digest", "write_once",
                 "the same pseudonymous digest as the two above; a rebinding overwrites it, so "
                 "the grant exists, but no erasure path locates this table and nothing clears "
                 "it on a request"),
    # **Free text a caller supplies, which is where a contact address actually ends up.** The
    # column names say nothing about a person, so the name sweep finds none of these; the
    # ordinary content of an SMTP rejection is `550 5.1.1 <jane@example.com>: Recipient address
    # rejected`, and a dispatcher reports exactly that. This is MOD-010's `cfg_exposures`
    # finding again -- the restricted-field rule reads names and a value carries anything --
    # and these three are the module's honest answer to it: declared, with the mechanism each
    # one's grants actually support.
    Reachability("plt01", "ntf_deliveries", "last_error", "write_once",
                 "a provider's own error text, which routinely quotes the address it "
                 "rejected; rewritten on each attempt, so the grant exists, but the erasure "
                 "executor reaches only `iam` and `ntf_deliveries` names no subject it could "
                 "be located by -- so nothing clears it"),
    Reachability("plt01", "ntf_deliveries", "provider_ref", "write_once",
                 "a provider's handle for the message, free text from the same caller, with "
                 "the same grant and the same absence of an erasure path"),
    Reachability("plt01", "ntf_suppressions", "detail", "unreachable",
                 "why an address was suppressed, free text that for a bounce quotes the "
                 "address; the table carries no UPDATE on it and no DELETE, deliberately, so "
                 "this is residue an erasure cannot reach"),
    # ---------------------------------------------------------------- MOD-014, PPL-01
    #
    # **This is the module that makes an erasure mean something, and the one that shows what it
    # still cannot reach.** `ppl_contact_points` holds the only copy of a member's email and
    # phone in the build -- MOD-007 holds the authentication identifier and MOD-013 deliberately
    # holds a digest -- so the four `anonymize` entries below are the first in `plt01` with an
    # executor behind them, reached through `ppl_identity_links` because a DSAR names an
    # identity and these tables are keyed on a person.
    #
    # Everything else here is insert-only by grant, which is correct on its own terms and is
    # residue all the same: a relationship, a merge record, a note and a timeline entry each
    # exist so that something stays answerable afterwards, and "afterwards" includes after an
    # erasure. Declared, not glossed.
    # The declared column of an `anonymize` entry has to be one the database can write, so
    # these four are declared on the *value* column with `locate_by="person_id"`, and the
    # subject column beside each one is `unreachable` because a primary or foreign key is not
    # something an erasure clears. The test that insists on this is the one a reviewer added
    # after two MOD-010 entries claimed the database refused a write it permitted.
    Reachability("plt01", "ppl_persons", "person_id", "unreachable",
                 "the primary key, which every other ppl_ table and every other module "
                 "references; the identifying values beside it are cleared -- see "
                 "ppl_persons.legal_name"),
    Reachability("plt01", "ppl_persons", "legal_name", "anonymize",
                 "the canonical person row is emptied rather than removed: the name and the "
                 "birth date are what identify somebody, and the birth date also decides "
                 "whether they are a minor",
                 clears=("legal_name", "preferred_name", "date_of_birth"),
                 locate_by="person_id"),
    Reachability("plt01", "ppl_persons", "created_by", "unreachable",
                 "who created the record; no UPDATE grant on this column, so it survives the "
                 "erasure of what they created"),
    Reachability("plt01", "ppl_persons", "merged_into_person_id", "write_once",
                 "written by a merge and cleared by its reversal, so the grant exists; no "
                 "erasure path touches it"),
    Reachability("plt01", "ppl_contact_points", "person_id", "unreachable",
                 "the row stays attached to the person; what it holds is cleared -- see "
                 "ppl_contact_points.value_raw"),
    Reachability("plt01", "ppl_contact_points", "value_raw", "anonymize",
                 "**the only copy of a member's address in this build.** Both value columns "
                 "are replaced with a per-row tombstone rather than emptied, because the "
                 "unique index on (person, kind, value) would otherwise refuse the second one",
                 clears=("value_raw", "value_normalized"), locate_by="person_id"),
    Reachability("plt01", "ppl_contact_points", "recorded_by", "unreachable",
                 "who entered the address; no UPDATE grant, so it survives the erasure of the "
                 "address itself"),
    Reachability("plt01", "ppl_contact_points", "verified_by", "write_once",
                 "who asserted the verification -- the signal the duplicate detector weights "
                 "most heavily, so the evidence an operator destroys a record on; in the "
                 "UPDATE grant, and no erasure path clears it"),
    Reachability("plt01", "ppl_tenant_profiles", "person_id", "unreachable",
                 "the profile stays attached to the person; its free text is cleared -- see "
                 "ppl_tenant_profiles.notes_internal"),
    Reachability("plt01", "ppl_tenant_profiles", "notes_internal", "anonymize",
                 "the tenant's own notes about this person are free text somebody typed and "
                 "are cleared; the brand, location and acquisition source are the tenant's "
                 "commercial record and are not",
                 clears=("notes_internal",), locate_by="person_id"),
    Reachability("plt01", "ppl_tenant_profiles", "updated_by", "write_once",
                 "rewritten on each change, because updating a profile is a fresh act by "
                 "whoever did it"),
    Reachability("plt01", "ppl_custom_field_values", "person_id", "unreachable",
                 "the value row stays attached to the person; the value is cleared -- see "
                 "ppl_custom_field_values.value_text"),
    Reachability("plt01", "ppl_custom_field_values", "value_text", "anonymize",
                 "a tenant can collect anything here, so every value is cleared regardless of "
                 "the field's declared sensitivity -- the classification decides who may read "
                 "it, not whether it is personal",
                 clears=("value_text",), locate_by="person_id"),
    Reachability("plt01", "ppl_custom_field_values", "updated_by", "write_once",
                 "rewritten on each change, as the profile's is"),
    Reachability("plt01", "ppl_identity_links", "person_id", "unreachable",
                 "insert-only: an identity that signed in as this person did so, and a link "
                 "that could be removed would make a past authorization unexplainable"),
    Reachability("plt01", "ppl_identity_links", "identity_id", "unreachable",
                 "the same row, from the other side; no UPDATE grant on either column"),
    Reachability("plt01", "ppl_identity_links", "linked_by", "unreachable",
                 "insert-only attribution"),
    Reachability("plt01", "ppl_member_profiles", "person_id", "unreachable",
                 "the member lifecycle is the tenant's own record of a commercial "
                 "relationship; no UPDATE grant on this column"),
    Reachability("plt01", "ppl_member_profiles", "updated_by", "write_once",
                 "rewritten on each lifecycle change"),
    Reachability("plt01", "ppl_staff_profiles", "person_id", "unreachable",
                 "an employment history is an employment record; no UPDATE grant on this "
                 "column"),
    Reachability("plt01", "ppl_staff_profiles", "updated_by", "write_once",
                 "rewritten on each change"),
    Reachability("plt01", "ppl_relationships", "from_person_id", "unreachable",
                 "a relationship ends rather than being re-pointed, so who it was between "
                 "carries no UPDATE grant -- which is what keeps \"who was this member's coach "
                 "in March\" answerable, and is also why an erasure cannot reach it"),
    Reachability("plt01", "ppl_relationships", "to_person_id", "unreachable",
                 "the other side of the same row, with the same grant and the same "
                 "consequence"),
    Reachability("plt01", "ppl_relationships", "created_by", "unreachable",
                 "insert-only attribution"),
    Reachability("plt01", "ppl_relationships", "ended_by", "write_once",
                 "who ended the relationship, which for a guardian edge is who removed a "
                 "guardian's access to a minor's record; in the UPDATE grant and never "
                 "cleared"),
    Reachability("plt01", "ppl_tags", "created_by", "unreachable",
                 "insert-only authorship of the tag definition"),
    Reachability("plt01", "ppl_person_tags", "person_id", "unreachable",
                 "who was tagged and when is what a member asks about; insert-only"),
    Reachability("plt01", "ppl_person_tags", "applied_by", "write_once",
                 "who applied it. In the UPDATE grant since re-applying a removed tag had to "
                 "become possible -- the row is keyed on (person, tag) for ever, so a "
                 "re-application rewrites the attribution rather than adding a second row, "
                 "which is the lesser of two losses and is stated in the migration"),
    Reachability("plt01", "ppl_person_tags", "removed_by", "write_once",
                 "written when the tag is removed; `removed_at IS NULL` in the service is what "
                 "refuses a second removal, not the grant"),
    Reachability("plt01", "ppl_custom_field_defs", "created_by", "unreachable",
                 "insert-only authorship of the field definition"),
    Reachability("plt01", "ppl_person_notes", "person_id", "unreachable",
                 "a note is insert-only because one that could be edited is one nobody can "
                 "rely on in the dispute it exists for; the body therefore survives an "
                 "erasure, which is the sharpest residue in this module"),
    Reachability("plt01", "ppl_person_notes", "recorded_by", "unreachable",
                 "who wrote it; insert-only"),
    Reachability("plt01", "ppl_person_notes", "withdrawn_by", "write_once",
                 "written with the withdrawal; `withdrawn_at IS NULL` in the service is what "
                 "refuses a second one, not the grant"),
    Reachability("plt01", "ppl_duplicate_candidates", "lower_person_id", "unreachable",
                 "the pair an operator decided on carries no UPDATE grant, so the evidence "
                 "they acted on cannot be rewritten afterwards"),
    Reachability("plt01", "ppl_duplicate_candidates", "higher_person_id", "unreachable",
                 "the other half of the same pair"),
    Reachability("plt01", "ppl_duplicate_candidates", "decided_by", "write_once",
                 "written with the decision; `status = 'open'` in the service is what refuses "
                 "a second one, not the grant"),
    Reachability("plt01", "ppl_merges", "source_person_id", "unreachable",
                 "paragraph 10200 requires a merge to be fully audited, so what was merged "
                 "into what carries no UPDATE grant and no DELETE at all"),
    Reachability("plt01", "ppl_merges", "target_person_id", "unreachable",
                 "the other side of the same record"),
    Reachability("plt01", "ppl_merges", "merged_by", "unreachable",
                 "who merged them; insert-only, for the same reason"),
    Reachability("plt01", "ppl_merges", "reversed_by", "write_once",
                 "written with the reversal; `reversed_at IS NULL` in the service is what "
                 "refuses a second one, not the grant"),
    Reachability("plt01", "ppl_timeline_entries", "person_id", "unreachable",
                 "the projection is insert-only in full, because one that could be edited in "
                 "place would be a second divergent copy of history rather than a view of it"),
    # **Hand-declared, because the sweep matches column names and these are values.** Three
    # columns hold text about a person under names that say nothing about one, and all three
    # are in tables with no UPDATE grant on them -- so they are residue an erasure cannot
    # reach, exactly like MOD-013's `ntf_suppressions.detail`.
    Reachability("plt01", "ppl_person_notes", "body", "unreachable",
                 "what a coach or a front desk wrote about this person, in their words; the "
                 "note is insert-only by design and this is the text that survives"),
    Reachability("plt01", "ppl_timeline_entries", "summary", "unreachable",
                 "one sentence per projected event, naming states and relationship kinds "
                 "rather than values -- `timeline.check_summary_fields` refuses a renderer "
                 "that reads a classified field -- and insert-only, so it survives"),
    Reachability("plt01", "ppl_member_profiles", "member_number", "write_once",
                 "the tenant's own member number, which agreements, cards and turnstiles may "
                 "carry; in the UPDATE grant, and no erasure path clears it"),
    # ---------------------------------------------------------------- MOD-016, COM-02
    #
    # **Almost all of this is commercial record rather than personal data**, and the three
    # columns that do name a person are on insert-only tables. A coupon redemption, a price
    # resolution and a bundle fulfilment are each evidence of a commercial act: a receipt
    # somebody could rewrite afterwards is worse than one that survives an erasure, so they are
    # declared as residue rather than made clearable.
    #
    # **Five free-text columns are declared too, and the reason is a review finding.** An
    # earlier version of this block said the resolutions carry "no name and no contact detail
    # -- only the subject id and the arithmetic", and a reviewer disproved it with an ordinary
    # override: `override_reason` is caller text that `pricing.override` renders into a `Step`
    # and the service stores into `explanation`, so "waived for Jane Smith,
    # jane.smith@example.com, 07700 900123, after her knee surgery in March" landed in the
    # least erasable store in the module. The reachability sweep matches column *names*, so
    # none of these five would ever be found by it -- the same reason MOD-010 declares
    # `evt_outbox.payload` and MOD-014 its timeline summaries by hand.
    Reachability("plt01", "cat_tax_categories", "created_by", "unreachable",
                 "who named the regime; no UPDATE grant on this column"),
    Reachability("plt01", "cat_products", "created_by", "unreachable",
                 "insert-only authorship of the product"),
    Reachability("plt01", "cat_products", "published_by", "write_once",
                 "written when the product is published; `status = 'draft'` in the service is "
                 "what refuses a second publication, not the grant"),
    Reachability("plt01", "cat_product_texts", "updated_by", "write_once",
                 "rewritten on each change, because editing a translation is a fresh act by "
                 "whoever did it"),
    Reachability("plt01", "cat_variants", "created_by", "unreachable",
                 "insert-only authorship of the variant"),
    Reachability("plt01", "cat_price_books", "created_by", "unreachable",
                 "insert-only authorship of the book"),
    Reachability("plt01", "cat_prices", "created_by", "unreachable",
                 "**COM-02-R07 as a privilege**: a price carries no UPDATE on anything it "
                 "says, so who wrote it survives with the amount"),
    Reachability("plt01", "cat_prices", "superseded_by_actor", "write_once",
                 "**who withdrew the price** -- and the one the sweep cannot see, because it "
                 "matches columns ending in `_by` and this one does not. It is here by hand "
                 "for the same reason MOD-010 declares `evt_outbox.payload` by hand. Written "
                 "with the supersession; `superseded_by IS NULL` in the service is what "
                 "refuses a second one, not the grant"),
    Reachability("plt01", "cat_price_books", "activated_by", "write_once",
                 "who switched the tenant's prices on; `status = 'draft'` in the service is "
                 "what refuses a second activation, not the grant"),
    Reachability("plt01", "cat_products", "retired_by", "write_once",
                 "who withdrew the product; the status transition in the service is what "
                 "refuses a second retirement, not the grant"),
    Reachability("plt01", "cat_bundle_items", "created_by", "unreachable",
                 "who composed the bundle. Insert-only in full: what a sale owed is what it "
                 "owed on the day, and a clearable composition would make a past obligation "
                 "unanswerable"),
    Reachability("plt01", "cat_prices", "superseded_by", "write_once",
                 "**not a person.** This names the price that replaced this one, and the "
                 "registry's sweep matches any column ending in `_by`; declared so the sweep "
                 "has an answer rather than so an erasure has a target"),
    Reachability("plt01", "cat_promotions", "created_by", "unreachable",
                 "insert-only authorship of the campaign"),
    Reachability("plt01", "cat_promotions", "activated_by", "write_once",
                 "written when the promotion goes live; `status = 'draft'` in the service is "
                 "what refuses a second activation, not the grant"),
    Reachability("plt01", "cat_eligibility_rules", "created_by", "unreachable",
                 "a rule is insert-only in full: editing one would change what a past "
                 "resolution would have decided, which the stored explanation exists to make "
                 "answerable"),
    Reachability("plt01", "cat_coupons", "created_by", "unreachable",
                 "insert-only authorship of the code"),
    Reachability("plt01", "cat_coupons", "revoked_by", "write_once",
                 "written with the revocation; `status = 'active'` in the service is what "
                 "refuses a second one, not the grant"),
    Reachability("plt01", "cat_coupon_redemptions", "subject_id", "unreachable",
                 "who redeemed the code. The ledger is insert-only because the usage limits "
                 "are counted from it -- a clearable row would be a single-use coupon with "
                 "unlimited uses -- so this is residue an erasure cannot reach"),
    Reachability("plt01", "cat_coupon_redemptions", "redeemed_by", "unreachable",
                 "the staff member who took the redemption; insert-only for the same reason"),
    Reachability("plt01", "cat_price_resolutions", "subject_id", "unreachable",
                 "who the price was resolved for. Paragraph 10220 requires the explanation to "
                 "be kept and the table carries no UPDATE grant at all, so an order citing a "
                 "resolution still explains after an erasure -- which is the point and is also "
                 "the residue"),
    Reachability("plt01", "cat_price_resolutions", "requested_by", "unreachable",
                 "the till or the staff member who asked; insert-only"),
    Reachability("plt01", "cat_discount_approvals", "approved_by", "unreachable",
                 "**paragraph 10220's audit half.** An override approved by somebody whose "
                 "name could later be removed would not be an audit at all; insert-only in "
                 "full"),
    Reachability("plt01", "cat_discount_approvals", "requested_by", "unreachable",
                 "who asked for the override, which is the other half of the separation of "
                 "duties the constraint enforces"),
    Reachability("plt01", "cat_bundles", "created_by", "unreachable",
                 "insert-only authorship of the bundle composition"),
    Reachability("plt01", "cat_bundle_fulfilments", "subject_id", "unreachable",
                 "who the bundle was delivered to. Insert-only, because over-delivery is "
                 "checked by counting these rows and a clearable one would be a member with "
                 "more sessions than they bought"),
    Reachability("plt01", "cat_bundle_fulfilments", "recorded_by", "unreachable",
                 "who says it was delivered -- the whole reason the row exists, since nothing "
                 "in this build fulfils anything"),
    # The five free-text columns. Each is prose a caller wrote, on a table with no UPDATE and
    # no DELETE grant, so each is residue an erasure cannot reach and says so.
    Reachability("plt01", "cat_price_resolutions", "explanation", "unreachable",
                 "**the explanation paragraph 10220 requires**, and it includes the reason "
                 "text of any manual override -- caller prose, which is where a name, an "
                 "address or a health fact realistically ends up. No UPDATE grant at all, "
                 "because a receipt somebody can rewrite is not a receipt"),
    Reachability("plt01", "cat_discount_approvals", "reason", "unreachable",
                 "why the override was approved; caller prose on the table that is paragraph "
                 "10220's audit half, insert-only in full"),
    Reachability("plt01", "cat_discount_requests", "reason", "unreachable",
                 "why it was asked for; the same shape as the approval's reason"),
    Reachability("plt01", "cat_discount_requests", "requested_by", "unreachable",
                 "who asked, derived from their own session -- which is what makes the "
                 "separation of duties on the approval real"),
    Reachability("plt01", "cat_bundle_fulfilments", "detail", "unreachable",
                 "why a delivery failed or was reversed; whatever the fulfilling module "
                 "reports, which in practice is a provider's own error text"),
    Reachability("plt01", "cat_bundle_fulfilments", "external_reference", "unreachable",
                 "the fulfilling module's own handle for the delivery; opaque by intent and "
                 "free text in fact"),
    Reachability("plt01", "cat_bundle_fulfilments", "order_reference", "unreachable",
                 "the sale this delivery was against. COM-01 owns orders and is not built, so "
                 "this is free text with no foreign key behind it"),
    Reachability("plt01", "cat_coupon_redemptions", "order_reference", "unreachable",
                 "the same, on the redemption ledger"),
    Reachability("plt01", "int_connector_runs", "settled_by", "write_once",
                 "written when the run is settled; `status = 'running'` in the service is what "
                 "refuses a second settlement, not the grant"),
    Reachability("plt01", "int_connector_runs", "released_by", "write_once",
                 "written with the release; `status = 'dead'` in the service is what refuses a "
                 "second one, not the grant"),
    Reachability("plt01", "int_connector_runs", "reconciled_by", "write_once",
                 "written with the reconciliation; `reconciled_at IS NULL` in the service is "
                 "what refuses a second one, not the grant"),
    # ---------------------------------------------------------------- MOD-017, COM-01
    #
    # **This module holds the contract a person signed and the record of what they were
    # entitled to, and almost none of it can be erased.** That is not an oversight: an
    # agreement, a lifecycle history and an entitlement ledger are each the thing a dispute is
    # argued from, and MOD-009's registry exists to say so rather than to pretend otherwise.
    # The one erasable identifier is on the live membership row, and even there the number
    # survives because a turnstile reads it.
    #
    # **And eleven free-text columns are declared by hand**, because the reachability sweep
    # matches column *names* and none of these has a name a sweep could recognise. Every one
    # holds what a caller or a provider sent, and the realistic content of several of them is a
    # person: a provider's decline message naming the cardholder, a reason an operator typed, a
    # locator that is an address rather than a reference. MOD-013 shipped exactly this with an
    # SMTP rejection and MOD-016 with five columns of prose; the sweep found neither. The
    # declaration is the only thing that will.
    #
    # `mem_contract_versions.body` is the same case and is the one this module noticed first:
    # tenant-authored prose, and a bespoke clause naming the member is the ordinary way a name
    # gets into it.
    Reachability("plt01", "mem_contract_versions", "created_by", "unreachable",
                 "who drafted the terms; the body carries no UPDATE grant and neither does "
                 "this"),
    Reachability("plt01", "mem_contract_versions", "published_by", "write_once",
                 "who published the version; `status = 'draft'` in the service is what "
                 "refuses a second publication, not the grant"),
    Reachability("plt01", "mem_contract_versions", "body", "unreachable",
                 "**the terms themselves**, tenant-authored prose, and the realistic place a "
                 "member's name appears in a bespoke clause. No UPDATE grant: a contract "
                 "whose wording could be edited after signing is not a contract"),
    Reachability("plt01", "mem_membership_terms", "created_by", "unreachable",
                 "who defined the terms; insert-only authorship"),
    Reachability("plt01", "mem_agreements", "person_id", "unreachable",
                 "**the member who signed.** The agreement is the contract; an erasure that "
                 "unlinked it would leave a signed obligation belonging to nobody, which is "
                 "worse for the member than the residue"),
    Reachability("plt01", "mem_agreements", "signed_by", "write_once",
                 "**who recorded the signature**, which is not the person who signed. The "
                 "service refuses a second signing on `status = 'draft'`, not the grant"),
    Reachability("plt01", "mem_agreements", "signed_by_person_id", "write_once",
                 "who actually signed -- the member, or a guardian, which is why it is a "
                 "separate column. It is in the signature grant because it moves once, from "
                 "nothing to signed; `status = 'draft'` in the service is what refuses a "
                 "second signature, not the grant"),
    Reachability("plt01", "mem_agreements", "created_by", "unreachable",
                 "the staff member who drew the agreement up; insert-only"),
    Reachability("plt01", "mem_memberships", "person_id", "unreachable",
                 "**not erasable, and the first draft of this entry claimed it was.** The "
                 "reasoning was that the membership row is a cache of state rather than the "
                 "contract, so the link could be cleared; the registry's own test refused it, "
                 "because `person_id` is not in this table's UPDATE grant and so the database "
                 "will not allow it. Granting UPDATE to make the claim true would be the "
                 "wrong fix: the agreement beside it keeps the signer anyway, so clearing "
                 "this would buy nothing an erasure report could honestly count"),
    Reachability("plt01", "mem_memberships", "created_by", "unreachable",
                 "who activated it; insert-only"),
    Reachability("plt01", "mem_lifecycle_changes", "decided_by", "unreachable",
                 "**COM-01-R07's history.** Insert-only in full, because as-of reconstruction "
                 "for disputes is only true of a history nobody can rewrite"),
    Reachability("plt01", "mem_lifecycle_changes", "requested_by_person_id", "unreachable",
                 "the member who asked for the change, where they did. COM-01-R06's "
                 "self-service request, and the other half of the pair an auditor compares"),
    Reachability("plt01", "mem_freezes", "decided_by", "unreachable",
                 "who approved the hold; insert-only on everything but the close"),
    Reachability("plt01", "mem_freezes", "requested_by_person_id", "unreachable",
                 "the member who asked to be frozen"),
    Reachability("plt01", "mem_freezes", "resumed_by", "write_once",
                 "who ended the hold; `ends_on IS NULL` in the service is what refuses a "
                 "second resume, not the grant"),
    Reachability("plt01", "mem_entitlement_policies", "created_by", "unreachable",
                 "who declared what this entitlement means; insert-only"),
    Reachability("plt01", "mem_entitlement_grants", "person_id", "unreachable",
                 "**who the right belongs to.** The grant is the fulfilment authority and the "
                 "ledger beside it has no UPDATE grant at all, so clearing this would leave "
                 "a balance belonging to nobody while the movements still said who drew it"),
    Reachability("plt01", "mem_entitlement_grants", "created_by", "unreachable",
                 "who granted it; insert-only"),
    Reachability("plt01", "mem_entitlement_grants", "revoked_by", "write_once",
                 "who revoked it; `status` in the service is what refuses a second "
                 "revocation, not the grant"),
    Reachability("plt01", "mem_entitlement_reservations", "person_id", "unreachable",
                 "who held the quantity. The reservation is what the ledger movements point "
                 "at, and the ledger is insert-only"),
    Reachability("plt01", "mem_entitlement_reservations", "held_by", "unreachable",
                 "the till or the booking flow that took the hold; insert-only"),
    Reachability("plt01", "mem_entitlement_reservations", "settled_by", "write_once",
                 "who consumed or released it; `status = 'held'` in the service is what "
                 "refuses a second settlement, not the grant"),
    Reachability("plt01", "mem_entitlement_ledger", "actor_id", "unreachable",
                 "**who caused each movement.** The ledger is the balance that decides whether "
                 "a member gets through a turnstile and the record of every draw-down they "
                 "have made; it carries no UPDATE and no DELETE grant at all"),

    # ---------------------------------------------------------------- MOD-017, COM-03
    #
    # **Restricted data, and the least erasable family in the build.** An invoice is a document
    # a tax authority reads, a payment is what an accountant reconciles a bank statement
    # against, and a tax record is a figure a return was built from -- none of the three can be
    # edited by any runtime role, and all three name the person who paid. COM-03's own
    # classification in the TSD is `Restricted` for exactly this reason.
    #
    # The honest statement is the one MOD-009's registry was built to make: an erasure request
    # from a member who has ever been invoiced reaches their identity and their contact
    # details and does not reach their financial history, because the law that compels the
    # erasure is not the law that compels the retention.
    Reachability("plt01", "fin_billing_accounts", "payer_person_id", "unreachable",
                 "**who pays.** The account is the party an invoice is addressed to, and the "
                 "invoices beside it have no UPDATE grant on anything they say"),
    Reachability("plt01", "fin_billing_accounts", "created_by", "unreachable",
                 "who opened the account; insert-only"),
    Reachability("plt01", "fin_billing_accounts", "closed_by", "write_once",
                 "who closed it; `status` in the service is what refuses a second closure, "
                 "not the grant"),
    Reachability("plt01", "fin_billing_schedules", "created_by", "unreachable",
                 "who set the schedule; insert-only"),
    Reachability("plt01", "fin_billing_schedules", "paused_by", "write_once",
                 "who paused it; `status` in the service is what refuses a second pause"),
    Reachability("plt01", "fin_fiscal_series", "created_by", "unreachable",
                 "who opened the numbering series; insert-only, and a trigger stops the "
                 "counter being rewound"),
    Reachability("plt01", "fin_invoices", "fiscalized_by", "write_once",
                 "**who moved the fiscal state**, deliberately not the issuer: the person "
                 "who issues invoices is not necessarily the person who files them. It moves "
                 "with each transition, which is why it is not `unreachable`"),
    Reachability("plt01", "fin_invoices", "issued_by", "unreachable",
                 "**who issued the document.** Every figure, the serial and the number carry "
                 "no UPDATE grant: this is what a tax authority reads and a member disputes"),
    Reachability("plt01", "fin_payment_intents", "created_by", "unreachable",
                 "who raised the intent; the amount and the account are fixed at creation"),
    Reachability("plt01", "fin_payments", "recorded_by", "unreachable",
                 "**who recorded that money arrived.** No UPDATE grant at all -- this is the "
                 "row an accountant reconciles the bank statement against"),
    Reachability("plt01", "fin_refund_requests", "requested_by", "unreachable",
                 "who asked for the refund, derived from their own session. It is one half of "
                 "the separation of duties the approval compares, so clearing it would make "
                 "the comparison unverifiable after the fact"),
    Reachability("plt01", "fin_refunds", "approved_by", "unreachable",
                 "**paragraph 1598's approval.** The one act in this module that sends money "
                 "back out; an approver whose name could later be removed would not be an "
                 "approval at all"),
    Reachability("plt01", "fin_refunds", "requested_by", "unreachable",
                 "the other half of that comparison, copied from the request"),
    Reachability("plt01", "fin_disputes", "recorded_by", "unreachable",
                 "who recorded the bank's claim; the claim itself is insert-only"),
    Reachability("plt01", "fin_disputes", "responded_by", "write_once",
                 "who answered it; the response columns move together, once"),
    Reachability("plt01", "fin_dunning_cases", "opened_by", "unreachable",
                 "who opened the recovery journey; insert-only"),
    Reachability("plt01", "fin_dunning_cases", "closed_by", "write_once",
                 "who closed it and how; `status` in the service is what refuses a second "
                 "closure"),
    Reachability("plt01", "fin_tax_records", "recorded_by", "unreachable",
                 "**who recorded the liability.** No UPDATE grant on anything the row "
                 "reports: this is the figure a return was built from"),
    Reachability("plt01", "fin_tax_records", "exported_by", "write_once",
                 "who included it in an accounting export; set once, so the same figure is "
                 "not exported twice without a deliberate act"),
    # ---------------------------------------------- MOD-017's free text, declared by hand
    #
    # Three of these have an UPDATE grant and so could be cleared by an erasure that chose to;
    # the rest have none at all and are residue, which is the honest statement. Closing it
    # needs either a provider error vocabulary or an erasure path into `plt01` for prose --
    # MOD-016 left the same five columns open for the same reason.
    Reachability("plt01", "mem_freezes", "reason", "unreachable",
                 "**why a membership was frozen**, prose an operator typed, and for a medical "
                 "hold the place a condition is described in free text whatever the evidence "
                 "column is for. No UPDATE grant: a freeze's reason is what an allowance "
                 "dispute is argued from"),
    Reachability("plt01", "mem_freezes", "evidence_ref", "unreachable",
                 "where a medical note lives. Constrained to a URI-shaped locator, so it "
                 "cannot hold the note -- but a locator can name the patient"),
    Reachability("plt01", "mem_lifecycle_changes", "reason", "unreachable",
                 "why a membership moved, prose a caller supplies, in the table COM-01-R07 "
                 "calls the one a dispute is argued from. No UPDATE grant"),
    Reachability("plt01", "mem_entitlement_grants", "revoke_reason", "write_once",
                 "why a grant was written off; the service refuses a second revocation, not "
                 "the grant"),
    Reachability("plt01", "mem_entitlement_ledger", "reason", "unreachable",
                 "why each movement happened. The ledger has no UPDATE and no DELETE grant "
                 "at all, which is what makes it the authority on a balance"),
    Reachability("plt01", "mem_agreements", "signature_evidence_ref", "write_once",
                 "where the signature is held. A URI-shaped locator, and one that routinely "
                 "names the signer in its path"),
    Reachability("plt01", "fin_invoice_lines", "description", "unreachable",
                 "**what was charged for**, in words. Insert-only in full, which is the point: "
                 "what was charged is what was charged. A line reading 'personal training "
                 "with Jane, Tuesdays' is the ordinary case"),
    Reachability("plt01", "fin_payment_intents", "payment_method_ref", "unreachable",
                 "a token somebody else holds. Constrained to a locator shape so a card "
                 "number will not fit, which is the control paragraph 1597 needs -- and no "
                 "UPDATE grant, because what was charged against is what was charged "
                 "against"),
    Reachability("plt01", "fin_payment_intents", "failure_detail", "write_once",
                 "**the provider's own sentence**, and the realistic content of one is "
                 "`declined for card 4242 held by JANE SMITH`. It is why the failure event "
                 "carries the code and not this"),
    Reachability("plt01", "fin_payment_intents", "provider_ref", "write_once",
                 "the provider's handle for the attempt; opaque, and declared because "
                 "nothing stops a provider putting a person in it"),
    Reachability("plt01", "fin_refund_requests", "reason", "unreachable",
                 "why a refund was asked for. The request table has no UPDATE grant at all: "
                 "it is the half of the separation of duties the approval compares against"),
    Reachability("plt01", "fin_refunds", "approval_reason", "unreachable",
                 "why it was approved, in the approver's words. No UPDATE grant on what was "
                 "decided"),
    Reachability("plt01", "fin_disputes", "response_ref", "write_once",
                 "where the response evidence is held; a locator, and a bank's case file is "
                 "named after the cardholder"),
    Reachability("plt01", "fin_disputes", "provider_case_ref", "unreachable",
                 "the bank's own case reference. No UPDATE grant: the claim is fixed, "
                 "because the bank made it"),
    Reachability("plt01", "fin_invoices", "fiscal_ack_ref", "write_once",
                 "the tax authority's own handle for the filing; set once by the service, "
                 "not by the grant"),
    Reachability("plt01", "fin_invoices", "fiscal_exemption_reason", "write_once",
                 "why a document was declared outside the regime, in words"),
    Reachability("plt01", "fin_dunning_cases", "resolution", "write_once",
                 "how a recovery journey ended, in words. The commonest sentence here is "
                 "about the member's circumstances"),
    # ---------------------------------------------------------------- MOD-018, COM-04
    #
    # **This module is the one place in the build where "cannot be erased" is the *requirement*
    # rather than the gap.** Paragraph 1685 is a Critical Control: posted financial entries are
    # never edited or deleted. So every column below is `unreachable` because the grant says so,
    # and that is the ledger working rather than erasure failing -- which is exactly what
    # MOD-009's registry exists to be able to say.
    #
    # What a subject erasure reaches here is nothing, and the completion report says so. The
    # closest honest thing an erasure could do is stop *new* postings naming the person, which
    # is a property of the callers rather than of this schema.
    Reachability("plt01", "led_accounts", "created_by", "unreachable",
                 "who opened the account; no UPDATE grant on the identity of a chart entry"),
    Reachability("plt01", "led_accounts", "retired_by", "write_once",
                 "who retired it; the service refuses a second retirement, not the grant"),
    Reachability("plt01", "led_periods", "created_by", "unreachable",
                 "who opened the period, which is whoever posted into the month first"),
    Reachability("plt01", "led_periods", "closed_by", "write_once",
                 "**who made a figure final.** The one act an auditor asks about, with "
                 "`reopened_by` beside it for the act that un-makes it"),
    Reachability("plt01", "led_periods", "reopened_by", "write_once",
                 "who let a filed figure change, with a reason the constraint requires"),
    Reachability("plt01", "led_journals", "posted_by", "unreachable",
                 "**who posted the money.** The journal has no UPDATE grant at all, which is "
                 "paragraph 1685: posted entries are never edited or deleted"),
    Reachability("plt01", "led_postings", "subject_person_id", "unreachable",
                 "**who a movement was about.** No UPDATE grant: a posting whose subject "
                 "could be re-pointed is a balance attributable to the wrong member, and the "
                 "statement built from it would be somebody else's"),
    Reachability("plt01", "led_wallets", "person_id", "unreachable",
                 "**whose wallet it is**, and the only copy of that fact. No UPDATE grant: a "
                 "wallet re-pointed at another person hands them a balance"),
    Reachability("plt01", "led_wallets", "created_by", "unreachable",
                 "who opened it, which is whoever first credited or debited it"),
    Reachability("plt01", "led_wallet_entries", "actor_id", "unreachable",
                 "**who moved the value.** The entries have no UPDATE grant at all, because "
                 "the balance is their sum: an editable entry is an editable balance, and a "
                 "member whose wallet could be edited cannot argue about last week"),
    Reachability("plt01", "led_recognition_schedules", "created_by", "unreachable",
                 "who declared how a sale earns"),
    Reachability("plt01", "led_recognition_schedules", "subject_person_id", "unreachable",
                 "whose prepaid service this is. No UPDATE grant on the subject"),
    Reachability("plt01", "led_recognition_schedules", "closed_by", "write_once",
                 "who closed the schedule, or `fully recognised` where the service did"),
    Reachability("plt01", "led_recognition_runs", "posted_by", "unreachable",
                 "who moved a figure from a liability to revenue. Insert-only in full: the "
                 "three numbers on the row have to keep agreeing with each other"),
    Reachability("plt01", "led_settlements", "imported_by", "unreachable",
                 "who imported the provider's file"),
    Reachability("plt01", "led_cash_sessions", "opened_by", "unreachable",
                 "who opened the till"),
    Reachability("plt01", "led_cash_sessions", "closed_by", "write_once",
                 "**who counted it.** With `variance_reason` beside it, this is the only "
                 "record of a till that did not balance and what was said about it"),
    Reachability("plt01", "led_deposits", "created_by", "unreachable",
                 "who sealed the bag"),
    Reachability("plt01", "led_deposits", "confirmed_by", "write_once",
                 "who recorded what the bank credited"),
    Reachability("plt01", "led_deposit_sessions", "added_by", "unreachable",
                 "who said these takings were in that bag"),
    Reachability("plt01", "led_reconciliation_cases", "opened_by", "unreachable",
                 "who raised the question, which is usually the import that found it"),
    Reachability("plt01", "led_reconciliation_cases", "resolved_by", "write_once",
                 "**who answered it**, including who decided to write money off"),
    Reachability("plt01", "led_exports", "exported_by", "unreachable",
                 "who sent a period to the accounts system. Insert-only in full"),
    # ------------------------------------------ MOD-018's free text, declared by hand
    #
    # The sweep matches column *names* and none of these has a name it could recognise. Every
    # one holds what a caller, a clerk or a provider typed, and the realistic content of a
    # posting memo is "Personal training with Jane, Tuesdays".
    # ---------------------------------------------------------------- MOD-019, OPS-01
    #
    # **The scheduling plane's only member identifiers are the two below**: who holds a place,
    # and which person a `staff` resource is. Everything else naming somebody is an actor id --
    # who published a schedule, who cancelled a class -- which is the evidence the module
    # exists to keep.
    Reachability("plt01", "sch_capacity_holds", "person_id", "unreachable",
                 "**who was in the room.** The holds have no UPDATE on this column and no "
                 "DELETE for any role, because 'who attended' is the answer to a dispute "
                 "about a session that has happened"),
    Reachability("plt01", "sch_resources", "person_id", "unreachable",
                 "which person a staff resource is. No UPDATE covers it: re-pointing a "
                 "resource at another person would rewrite who taught every past session"),
    Reachability("plt01", "sch_resources", "created_by", "unreachable",
                 "who added a schedulable resource"),
    Reachability("plt01", "sch_resources", "retired_by", "write_once",
                 "**who withdrew it**, which takes every class holding it off the schedule; "
                 "the trigger beside the table makes the retirement final"),
    Reachability("plt01", "sch_availability_windows", "created_by", "unreachable",
                 "who set this rota window, which is what a schedule is generated against"),
    Reachability("plt01", "sch_availability_windows", "withdrawn_by", "write_once",
                 "**who took a rota window back**, which is the act that puts a coach back "
                 "on the schedule after an absence was recorded against them; 0017's "
                 "trigger makes the withdrawal final"),
    Reachability("plt01", "sch_availability_windows", "withdrawn_at", "write_once",
                 "when it was taken back, which bounds how long the absence stood"),
    Reachability("plt01", "sch_availability_windows", "withdraw_correlation_id",
                 "write_once",
                 "the request that withdrew it, which names no subject and is declared "
                 "because the sweep reads column names"),
    Reachability("plt01", "sch_templates", "created_by", "unreachable",
                 "who drafted a schedule"),
    Reachability("plt01", "sch_templates", "published_by", "write_once",
                 "**who published it**, which is the act paragraph 1841 governs: a draft "
                 "affects nobody and a publication is what members plan their week around"),
    Reachability("plt01", "sch_templates", "retired_by", "write_once",
                 "who stopped a recurring class"),
    Reachability("plt01", "sch_session_resources", "assignment_id", "unreachable",
                 "the assignment's own key, which names nobody -- declared because the sweep "
                 "reads column names and this one ends in a word it watches for"),
    Reachability("plt01", "sch_recurrence_rules", "created_by", "unreachable",
                 "who wrote this version of the recurrence. The table has no UPDATE grant at "
                 "all, because a rule a session cites describes what that session is"),
    Reachability("plt01", "sch_capacity_policies", "created_by", "unreachable",
                 "who set the capacity a session was published with"),
    Reachability("plt01", "sch_restrictions", "created_by", "unreachable",
                 "who added an eligibility rule, which is what refuses a member a place"),
    Reachability("plt01", "sch_template_requirements", "created_by", "unreachable",
                 "who decided what a session needs"),
    Reachability("plt01", "sch_sessions", "created_by", "unreachable",
                 "who generated this session"),
    Reachability("plt01", "sch_sessions", "cancelled_by", "write_once",
                 "**who cancelled a class members had booked.** The one-way trigger makes it "
                 "final, because the cancellation is what they were told"),
    Reachability("plt01", "sch_session_resources", "assigned_by", "unreachable",
                 "who assigned a resource to a session. No UPDATE grant: what a session held "
                 "is what the conflict detector decided against"),
    Reachability("plt01", "sch_session_resources", "superseded_by", "write_once",
                 "**who took a resource off a session** -- the coach who was substituted out, "
                 "the studio a class was moved from. The `sch_session_resources_one_way` "
                 "trigger refuses a second supersession, so re-assigning the same resource is "
                 "a new assignment row rather than a cleared marker: an earlier version "
                 "cleared it, which made this the one attribution in the module a later write "
                 "could erase"),
    Reachability("plt01", "sch_session_changes", "recorded_by", "unreachable",
                 "who substituted, relocated or handed off a session. Insert-only, because "
                 "each is a thing a member was told"),
    Reachability("plt01", "sch_capacity_holds", "taken_by", "unreachable",
                 "who put this person in the class"),
    Reachability("plt01", "sch_capacity_holds", "released_by", "write_once",
                 "**who took them out of it**, which is the act a member notices most"),
    Reachability("plt01", "sch_conflict_overrides", "overridden_by", "unreachable",
                 "**who published over a resource conflict.** Paragraph 1842's Critical "
                 "Control is 'permission and reason', and this is the only record of either"),
    # ---------------------------------------------------------------- MOD-020, OPS-02
    #
    # **Booking holds the member's own history of attending**, which is a record of where
    # somebody was on a given evening -- so every column naming them is here, and the two the
    # module can erase are named rather than claimed.
    Reachability("plt01", "bkg_bookings", "person_id", "unreachable",
                 "**who held this place.** No UPDATE on the column and no DELETE for any "
                 "role: whether a member was in a class is the answer to a dispute about a "
                 "sanction, and the trigger beside the table refuses a change to it as well"),
    Reachability("plt01", "bkg_bookings", "booked_by", "unreachable",
                 "who made the booking -- the member themself, or a front desk"),
    Reachability("plt01", "bkg_bookings", "checked_in_by", "write_once",
                 "**who marked them present.** The one-way trigger refuses a second "
                 "check-in, so the attribution is final once written"),
    Reachability("plt01", "bkg_bookings", "cancelled_by", "write_once",
                 "who cancelled the place, which decides whether the member owes anything"),
    Reachability("plt01", "bkg_bookings", "idempotency_key", "unreachable",
                 "the caller's own handle, free text and so able to carry a subject. No "
                 "UPDATE and no DELETE"),
    Reachability("plt01", "bkg_bookings", "cancellation_reason", "write_once",
                 "**why a member could not come, in their own words** -- which is where a "
                 "medical reason goes in practice, and the reason the booking read masks it "
                 "unless the caller could have written one"),
    Reachability("plt01", "bkg_waitlist_entries", "person_id", "unreachable",
                 "who is waiting for a place"),
    Reachability("plt01", "bkg_waitlist_entries", "joined_by", "unreachable",
                 "who put them on the waitlist"),
    Reachability("plt01", "bkg_waitlist_entries", "settled_by", "write_once",
                 "who closed the entry; the one-way trigger makes it final"),
    Reachability("plt01", "bkg_waitlist_entries", "settle_reason", "write_once",
                 "why the entry closed, in prose"),
    Reachability("plt01", "bkg_waitlist_entries", "idempotency_key", "unreachable",
                 "the caller's own handle, free text. No UPDATE and no DELETE"),
    Reachability("plt01", "bkg_cancellations", "person_id", "unreachable",
                 "**whose cancellation this was.** Insert-only in full: what a member was "
                 "told they owe is what they were told"),
    Reachability("plt01", "bkg_cancellations", "cancelled_by", "unreachable",
                 "who cancelled it"),
    Reachability("plt01", "bkg_cancellations", "reason", "unreachable",
                 "why, in the member's own words, on a row with no UPDATE and no DELETE -- "
                 "so this is residue no erasure in this build can reach"),
    Reachability("plt01", "bkg_no_shows", "person_id", "unreachable",
                 "**who missed a class**, which is the basis of a sanction and so the answer "
                 "to an appeal about one. Insert-only apart from the overturn"),
    Reachability("plt01", "bkg_no_shows", "recorded_by", "unreachable",
                 "who recorded it -- a settlement, which nobody sets by hand"),
    Reachability("plt01", "bkg_no_shows", "overturned_by", "write_once",
                 "**who upheld the appeal that stopped this counting.** The attribution "
                 "constraint is all-or-none and the service writes it once"),
    Reachability("plt01", "bkg_appeals", "subject_person_id", "unreachable",
                 "**whose sanction is disputed.** No UPDATE, and the one-way trigger refuses "
                 "a change to it: an appeal that could be re-pointed is one member's "
                 "grounds deciding another's record"),
    Reachability("plt01", "bkg_appeals", "raised_by", "unreachable",
                 "who raised it"),
    Reachability("plt01", "bkg_appeals", "decided_by", "write_once",
                 "**who decided it**, which is the separation of duties this table exists "
                 "for; the one-way trigger makes the decision final"),
    Reachability("plt01", "bkg_appeals", "decided_by_person_id", "write_once",
                 "the person that decider is, where they have a record -- the half the "
                 "constraint compares against the subject, because an identity id would let "
                 "one member decide their own appeal from a second login"),
    Reachability("plt01", "bkg_appeals", "grounds", "unreachable",
                 "**why the member says the sanction is wrong, in their own words** -- where "
                 "a medical reason goes, on a row with no UPDATE. Residue no erasure reaches, "
                 "and the reason the appeal list is behind the deciding permission"),
    Reachability("plt01", "bkg_appeals", "decision_note", "write_once",
                 "why the decision went the way it did"),
    Reachability("plt01", "bkg_appeals", "idempotency_key", "unreachable",
                 "the caller's own handle, free text. No UPDATE and no DELETE"),
    Reachability("plt01", "bkg_attendance_intents", "person_id", "unreachable",
                 "**who said whether they were coming.** Insert-only, because a change of "
                 "mind is a new row and overwriting would lose that the gym was told twice"),
    Reachability("plt01", "bkg_attendance_intents", "declared_by", "unreachable",
                 "who declared it -- the member, or a front desk taking a telephone call"),
    Reachability("plt01", "bkg_attendance_intents", "idempotency_key", "unreachable",
                 "the caller's own handle, free text. No UPDATE and no DELETE"),
    Reachability("plt01", "bkg_policies", "created_by", "unreachable",
                 "who published this version of the booking policy"),
    Reachability("plt01", "bkg_policies", "retired_by", "write_once",
                 "who withdrew it"),
    Reachability("plt01", "bkg_policies", "retire_reason", "write_once",
                 "why it was withdrawn"),
    # Free text a subject can appear in. Declared by hand, because the sweep matches column
    # *names* and none of these says 'subject' -- the same group MOD-018 has, for the same
    # reason, and pinned by a named test for the same reason again.
    Reachability("plt01", "sch_availability_windows", "reason", "unreachable",
                 "why somebody is absent, in an operator's own words -- which is where a "
                 "health fact goes in practice, and the reason this is declared. **It was "
                 "`write_once` until 0017**, which revoked the `UPDATE (starts_at, ends_at, "
                 "reason)` grant 0013 wrote and no service ever used; the database now "
                 "refuses the write outright, which is the stronger and truer statement"),
    Reachability("plt01", "sch_availability_windows", "withdrawn_reason", "unreachable",
                 "why a rota window was taken back, in an operator's own words -- the same "
                 "free text one column over, and the same reason it is declared by hand. "
                 "The column carries an UPDATE grant because the withdrawal is what writes "
                 "it; what makes it unreachable afterwards is 0017's trigger "
                 "`sch_availability_windows_one_way`, which refuses any write to a window "
                 "already withdrawn -- `sec_legal_holds.released_by`'s shape exactly"),
    Reachability("plt01", "sch_templates", "retire_reason", "write_once",
                 "why a recurring class was stopped"),
    Reachability("plt01", "sch_session_changes", "reason", "unreachable",
                 "why a class changed, in prose. Insert-only and no erasure path clears it"),
    Reachability("plt01", "sch_conflict_overrides", "reason", "unreachable",
                 "why a conflict was overridden; the evidence for paragraph 1842"),
    Reachability("plt01", "sch_conflict_overrides", "conflict_summary", "unreachable",
                 "what the detector found, as it was found: recomputing it later would read "
                 "a schedule that has since moved"),
    # Four more a reviewer wrote a name, a date of birth, a phone number and an address into,
    # through the ordinary routes, and read back out of the tables. None of them is *for* a
    # subject and all four hold whatever a caller types, which is the whole reason this group
    # is declared by hand -- the sweep matches column names.
    Reachability("plt01", "sch_capacity_holds", "source_ref", "unreachable",
                 "**what took the place**, in the caller's own words: an order number, a till "
                 "reference, or -- as a reviewer demonstrated -- a member's name, date of "
                 "birth and allergies. No UPDATE and no DELETE, so no erasure reaches it"),
    Reachability("plt01", "sch_capacity_holds", "idempotency_key", "unreachable",
                 "the caller's handle for its own retry, which is free text and so can carry "
                 "a subject. No UPDATE and no DELETE"),
    Reachability("plt01", "sch_resources", "display_name", "anonymize",
                 "**a staff resource's display name is a person's own name.** It carries an "
                 "UPDATE grant and the row names the person it is, so an erasure reaches it "
                 "through `person_id` -- the one column in this group that is genuinely "
                 "clearable",
                 clears=("display_name",), locate_by="person_id"),
    Reachability("plt01", "sch_templates", "display_name", "write_once",
                 "what a class is called, which is a person's name whenever it is a personal "
                 "training slot -- 'PT with Jane, Tuesdays'. UPDATE is granted, so this is not "
                 "`unreachable`; what no erasure can do is *find* it, because nothing relates "
                 "a template to a person. Renaming it is a tenant's own act"),
    Reachability("plt01", "sch_capacity_holds", "release_reason", "write_once",
                 "why a place was given up or taken away"),

    Reachability("plt01", "led_postings", "memo", "unreachable",
                 "**the statement line.** Insert-only in full, and the place a member's name "
                 "or a service's description lands on a journal"),
    Reachability("plt01", "led_journals", "description", "unreachable",
                 "what the journal was for, in words. No UPDATE grant"),
    Reachability("plt01", "led_journals", "source_ref", "unreachable",
                 "the handle of whatever caused it; free text for a `manual` journal"),
    Reachability("plt01", "led_journals", "correction_reason", "unreachable",
                 "why a figure was reversed, which is the sentence an auditor reads"),
    Reachability("plt01", "led_wallet_entries", "reason", "unreachable",
                 "why value moved, in words, on a member's own statement"),
    Reachability("plt01", "led_wallet_entries", "source_ref", "unreachable",
                 "what the movement was against; free text"),
    Reachability("plt01", "led_periods", "reopen_reason", "write_once",
                 "**why a filed month was reopened**, which is prose an operator types: a "
                 "reviewer put an address and a date of birth in one and read it back. The "
                 "trigger beside it makes the reason final once written"),
    Reachability("plt01", "led_recognition_schedules", "close_reason", "write_once",
                 "why a schedule was cancelled before it finished earning, in an operator's "
                 "own words"),
    Reachability("plt01", "led_recognition_schedules", "source_ref", "unreachable",
                 "the sale this schedule earns against, which is free text because the "
                 "module that owns orders does not exist; no UPDATE grant covers it"),
    Reachability("plt01", "led_cash_sessions", "variance_reason", "write_once",
                 "**what the clerk said about a till that did not balance.** The sentence "
                 "the whole control exists to capture"),
    Reachability("plt01", "led_settlement_lines", "provider_ref", "unreachable",
                 "the provider's own handle for a movement. Insert-only in full"),
    Reachability("plt01", "led_settlement_lines", "outcome_reason", "unreachable",
                 "why the matcher reached its verdict, built from the provider's figures"),
    Reachability("plt01", "led_reconciliation_cases", "detail", "unreachable",
                 "what the discrepancy was, often a provider's own sentence"),
    Reachability("plt01", "led_reconciliation_cases", "resolution", "write_once",
                 "how it was answered, in the resolver's words"),
    Reachability("plt01", "led_reconciliation_cases", "subject_ref", "unreachable",
                 "what the case is about; free text because the subject is in five tables"),
    Reachability("plt01", "led_settlements", "provider_batch_ref", "unreachable",
                 "the provider's own batch handle. Insert-only in full"),
    Reachability("plt01", "led_settlements", "document_ref", "unreachable",
                 "where the file is held. A URI-shaped locator, and one that names a date "
                 "and a merchant"),
    Reachability("plt01", "led_deposits", "bank_reference", "write_once",
                 "the bank's own reference for the credit"),
    Reachability("plt01", "led_exports", "target_ref", "unreachable",
                 "the accounting system's own handle for the batch"),
    Reachability("plt01", "evt_replay_jobs", "ran_by", "write_once",
                 "written when the job starts; `status = 'requested'` in the service is what "
                 "refuses a second run, not the grant"),
    # ------------------------------------------------------ MOD-021, ECO-03
    #
    # **Every one of these is an identity, not a member**, which is the whole of this module's
    # privacy position: MOD-021 registers boxes. There is no `person_id` anywhere in `dev_`,
    # and what a reader read is MOD-022's. The two `superseded_by` columns are not people at
    # all, declared by hand for the reason MOD-016 declares its own: the sweep matches a `_by`
    # suffix and cannot tell a row reference from an actor.
    Reachability("plt01", "dev_device_types", "created_by", "unreachable",
                 "who drafted a model of hardware"),
    Reachability("plt01", "dev_device_types", "published_by", "write_once",
                 "**who settled what this model may be asked to do**, which every unit "
                 "enrolled against it snapshots. The one-way trigger makes it final"),
    Reachability("plt01", "dev_device_types", "retired_by", "write_once",
                 "who stopped new units being enrolled against a model"),
    Reachability("plt01", "dev_type_capabilities", "created_by", "unreachable",
                 "who declared a capability on a model. No UPDATE grant at all: what a "
                 "published type may be asked to do is what somebody reviewed"),
    Reachability("plt01", "dev_devices", "created_by", "unreachable",
                 "who enrolled this unit"),
    Reachability("plt01", "dev_devices", "activated_by", "write_once",
                 "**who brought a door into service on the strength of its commissioning "
                 "record.** The one-way trigger refuses a change, because this is the "
                 "attribution paragraph 4175's gate rests on"),
    Reachability("plt01", "dev_devices", "quarantined_by", "write_once",
                 "who took a unit out of service, which stops a club using it"),
    Reachability("plt01", "dev_devices", "retired_by", "write_once",
                 "who ended a unit's life and revoked what authenticated it"),
    Reachability("plt01", "dev_device_capabilities", "created_by", "unreachable",
                 "who copied a model's capability onto a unit. No UPDATE grant: this is what "
                 "bounds every command the unit can be sent"),
    Reachability("plt01", "dev_certificates", "issued_by", "unreachable",
                 "**who gave a device the credential it authenticates with.** No UPDATE "
                 "grant on it or on the fingerprint: widening what a device may authenticate "
                 "with is a new certificate"),
    Reachability("plt01", "dev_certificates", "revoked_by", "write_once",
                 "who withdrew a device's credential, which is the act that bumps the "
                 "revocation epoch every gateway compares against"),
    Reachability("plt01", "dev_certificates", "superseded_by", "write_once",
                 "**not a person.** This names the certificate that replaced this one, so a "
                 "rotation chain stays walkable; it is here by hand because the sweep "
                 "matches a `_by` suffix and cannot tell a reference from an actor. "
                 "`write_once` rather than `unreachable` because the rotation grant covers "
                 "it -- the one-way trigger is what refuses a change, and the registry's own "
                 "check caught the stronger claim"),
    Reachability("plt01", "dev_safety_profiles", "commissioned_by", "unreachable",
                 "**who claimed that a building's egress wiring is what it is.** This is the "
                 "most load-bearing attribution in the module and carries no UPDATE grant at "
                 "all: TSD section 16.4 is a fire code, and a safety record that could be "
                 "edited is a building whose records pass an audit it would fail"),
    Reachability("plt01", "dev_safety_profiles", "superseded_by", "write_once",
                 "**not a person**, for `dev_certificates.superseded_by`'s reason: it names "
                 "the re-commissioning that replaced this one. The trigger makes it final"),
    Reachability("plt01", "dev_commissioning_tests", "tested_by", "unreachable",
                 "**who ran a safety test and said what happened.** Insert-only in full: a "
                 "failure that could be edited into a pass is paragraph 4175 with its teeth "
                 "pulled"),
    Reachability("plt01", "dev_firmware", "released_by", "unreachable",
                 "who published an image for a model of hardware to fetch"),
    Reachability("plt01", "dev_firmware", "withdrawn_by", "write_once",
                 "who pulled an image, which the trigger makes final because a fixed build "
                 "is a new version"),
    Reachability("plt01", "dev_commands", "issued_by", "unreachable",
                 "**who told a device to do something**, including a door to release. MOD-008 "
                 "audits denials rather than allowed acts and this module's role holds "
                 "nothing in `iam`, so this row is the only record there is -- and the "
                 "one-way trigger refuses a change to it"),
    Reachability("plt01", "dev_policy_snapshots", "issued_by", "unreachable",
                 "who published the authorization projection a gateway runs on offline"),
    Reachability("plt01", "dev_health_reports", "reported_by", "unreachable",
                 "**who said a device was fine.** An operator who does not drive to the club "
                 "is relying on it, which is MOD-011's fabricated `passed` one module over"),

    # The attribution the review added. `dev_commands` carried `issued_by` alone, so the
    # only name on a row saying a door opened was the party that did not make the claim.
    Reachability("plt01", "dev_commands", "delivered_by", "write_once",
                 "**who collected this command**, which for an unlock is who the door was "
                 "handed to. The delivering write holds the grant and the one-way trigger "
                 "admits no second delivery; no erasure reaches it"),
    Reachability("plt01", "dev_commands", "settled_by", "write_once",
                 "**who reported what the device did**, which is the only record that a "
                 "door opened. MOD-008 audits denials and this role holds nothing in `iam`"),
    Reachability("plt01", "dev_devices", "reactivated_by", "write_once",
                 "**who put a withdrawn access point back into production**, which is a "
                 "passage through paragraph 4175's gate in its own right. Rewritten on each "
                 "return to service and cleared by nothing"),
    Reachability("plt01", "dev_sync_conflicts", "reported_by", "unreachable",
                 "**which gateway said the two copies disagreed.** The table carries no "
                 "UPDATE grant at all, so this is residue an erasure cannot reach"),

    # **And the free text, which the sweep cannot see.** The reachability sweep matches column
    # *names*, so a prose column and a `jsonb` object are invisible to it -- every module from
    # MOD-013 on declares this residue by hand, and MOD-021's first version declared none: all
    # twenty entries above are actor columns. A reviewer wrote a member's address and date of
    # birth into a settled command's outcome and into a health report's peripherals and read
    # both back. The device dispatcher is the likeliest writer of a contact address in this
    # module, exactly as MOD-013's `ntf_deliveries.last_error` is in that one.
    Reachability("plt01", "dev_commands", "outcome_detail", "write_once",
                 "**what a gateway said happened**, free text it supplies -- the ordinary "
                 "content of a reader rejection names the card and whoever presented it. "
                 "The settling write holds the grant, and no erasure path reaches `plt01` "
                 "through a device, so nothing clears it"),
    Reachability("plt01", "dev_commands", "arguments", "unreachable",
                 "**what a command was parameterised with.** `commands.check_arguments` "
                 "admits only declared keys and `set_maintenance`'s reason is the one free "
                 "string among them; the column carries no UPDATE grant"),
    Reachability("plt01", "dev_health_reports", "peripherals", "unreachable",
                 "**a device's own peripheral inventory**, caller-supplied and bounded in "
                 "shape but not in meaning: a reader that names the last member it saw puts "
                 "that name here. Insert-only with no UPDATE grant"),
    Reachability("plt01", "dev_sync_conflicts", "detail", "unreachable",
                 "**what a gateway said diverged**, free text it supplies -- which is the "
                 "whole point of the column, since the two digests beside it say nothing a "
                 "person can act on. Insert-only, with no UPDATE grant"),
    Reachability("plt01", "dev_commissioning_tests", "detail", "unreachable",
                 "**what a safety test found**, written by whoever ran it, on an insert-only "
                 "table with no UPDATE grant -- a failure that names the person who was "
                 "trapped is the realistic input"),
    Reachability("plt01", "dev_safety_profiles", "door_description", "unreachable",
                 "**which door this is**, in a building. Prose, and the supersede trigger "
                 "makes it final once another commissioning replaces the row"),
    Reachability("plt01", "dev_devices", "display_name", "write_once",
                 "**what a unit is called**, which is where 'jane's office door' goes. "
                 "`configure_device` holds the grant, so it is rewritable -- but no erasure "
                 "locates a device from a subject, so nothing clears it on a request"),
    Reachability("plt01", "dev_devices", "config", "write_once",
                 "**a device's own settings**, a tenant-written object bounded in shape and "
                 "not in meaning. Rewritable by `configure_device` and reached by no "
                 "erasure"),
    Reachability("plt01", "dev_devices", "quarantine_reason", "write_once",
                 "**why a door was taken out of service**, which is where an incident naming "
                 "a member gets written. Written once per quarantine and never cleared"),
    Reachability("plt01", "dev_devices", "retire_reason", "write_once",
                 "**why a unit was retired.** Same shape as the quarantine reason"),
    Reachability("plt01", "dev_device_types", "retire_reason", "write_once",
                 "**why a model was withdrawn.** Prose, written once"),
    Reachability("plt01", "dev_certificates", "revoke_reason", "unreachable",
                 "**why a credential was withdrawn**, which is where 'the gateway Jane took "
                 "home' is written. The one-way trigger makes a revoked row final"),
    Reachability("plt01", "dev_firmware", "withdraw_reason", "write_once",
                 "**why a build was pulled.** Prose, and the one-way trigger makes a "
                 "withdrawal final"),
    Reachability("plt01", "dev_firmware", "release_notes", "write_once",
                 "**what changed in a build**, prose a release manager writes. The status "
                 "write holds the grant; no erasure reaches it"),

    # ------------------------------------------------------------------ MOD-022 access control
    #
    # **This is the module where the residue is a movement history.** Every other module's
    # residue is a figure or a sentence; `acc_decisions` and `acc_events` are a record of which
    # person stood at which door at which minute, for as long as the tenant keeps the rows --
    # and both tables are insert-only for both runtime roles, so an erasure reaches neither.
    # Article 17 is not satisfied here and the registry is where that is said out loud, the
    # same way MOD-009's does it for the ledger and the audit chain.
    #
    # The one mitigation that is real: **no credential value is stored anywhere.**
    # `acc_credentials.credential_digest` is a SHA-256 and there is no column a card number
    # could sit in, which is MOD-013's digest decision applied to a badge. It is pseudonymous
    # rather than anonymous -- somebody holding a candidate card can test it -- so it is
    # declared rather than claimed to be nothing.
    Reachability("plt01", "acc_credentials", "person_id", "unreachable",
                 "**whose card this is.** The column carries no UPDATE grant, because "
                 "re-pointing a credential at a different person is how a card walks from "
                 "one member to another with the history following it. So an erasure cannot "
                 "clear it: that a person once held a credential survives their deletion"),
    Reachability("plt01", "acc_credentials", "credential_digest", "unreachable",
                 "**a SHA-256 of the value presented**, never the value. Pseudonymous, not "
                 "anonymous -- somebody holding a candidate card can test it -- and there is "
                 "no UPDATE grant, so the digest outlives the person it identified"),
    Reachability("plt01", "acc_credentials", "issued_by", "unreachable",
                 "who enrolled a credential against a person. Insert-only: an issuer that "
                 "could be rewritten is an enrolment nobody is accountable for"),
    Reachability("plt01", "acc_credentials", "revoked_by", "write_once",
                 "**who killed a card.** The revoking write holds the grant and the one-way "
                 "state trigger admits no second revocation, so it is written once and "
                 "cleared by nothing"),
    Reachability("plt01", "acc_credentials", "revoke_reason", "write_once",
                 "**why a card was withdrawn**, which is where 'lost it at the hospital' "
                 "gets typed. Written with the revocation and reached by no erasure"),

    Reachability("plt01", "acc_decisions", "person_id", "unreachable",
                 "**who was at which door, and whether they got in.** The whole table is "
                 "insert-only for both runtime roles -- which is what makes a refusal "
                 "something nobody can quietly delete, and what makes this residue an "
                 "erasure cannot reach. The most sensitive thing this module keeps"),
    Reachability("plt01", "acc_decisions", "decided_by", "unreachable",
                 "the identity the reader called under. Insert-only for the table's reason"),
    Reachability("plt01", "acc_decisions", "overridden_by", "unreachable",
                 "**who let somebody through against the policy.** The point of the row, and "
                 "insert-only so the override cannot be reattributed afterwards"),
    Reachability("plt01", "acc_decisions", "public_reason", "unreachable",
                 "the refusal a turnstile may display. A closed set of codes rendered to "
                 "text, so it names nothing by itself -- declared because it sits beside the "
                 "private half and a reader of this registry should see both"),
    Reachability("plt01", "acc_decisions", "private_reason", "unreachable",
                 "**the half a turnstile never shows**: that this member is overdue, or is a "
                 "minor with no guardian on file, or was refused by an anti-passback window "
                 "two minutes after somebody else used their card. Health-adjacent facts "
                 "about a named person, insert-only, reached by no erasure. "
                 "`access.decision.read_reason` is the permission that gates reading it"),
    Reachability("plt01", "acc_decisions", "override_reason", "unreachable",
                 "**why a member was admitted against the policy**, written by whoever did "
                 "it -- 'her card is in the car, I know her' is the realistic input, and so "
                 "is a medical one. Insert-only"),

    Reachability("plt01", "acc_events", "person_id", "unreachable",
                 "**who actually walked through.** A decision is what the server said; an "
                 "event is what the reader saw, and the two are kept apart on purpose. "
                 "Insert-only, so the movement history outlives an erasure"),
    Reachability("plt01", "acc_events", "recorded_by", "unreachable",
                 "the identity the reader reported under. Insert-only"),
    Reachability("plt01", "acc_events", "reconciled_by", "write_once",
                 "**who settled what an offline reader had queued**, which is the only name "
                 "on a judgement that somebody was admitted who should not have been. "
                 "Written once by the reconciliation and cleared by nothing"),

    Reachability("plt01", "acc_emergency_unlocks", "ordered_by", "unreachable",
                 "**who released every door in a zone.** Insert-only, because paragraph "
                 "4178's dual approval rests on this name being the one that was there"),
    Reachability("plt01", "acc_emergency_unlocks", "reviewed_by", "write_once",
                 "**the second person**, after the fact. The review write holds the grant "
                 "and the constraint refuses the orderer's own id; nothing clears it"),
    Reachability("plt01", "acc_emergency_unlocks", "reason", "unreachable",
                 "**why every door in a zone was released**, prose written during an "
                 "emergency -- which is exactly when somebody types a member's name and what "
                 "happened to them. Insert-only"),
    Reachability("plt01", "acc_emergency_unlocks", "review_note", "write_once",
                 "**what the reviewer concluded**, same shape as the reason above"),

    # The configuration tables. A zone and a point are places rather than people, so the
    # actor columns are the subject-bearing ones -- but a retirement reason is prose, and
    # MOD-021 already records that 'jane's office door' is what goes in a display name.
    Reachability("plt01", "acc_zones", "created_by", "unreachable",
                 "who declared an area this software decides about. Insert-only"),
    Reachability("plt01", "acc_zones", "retired_by", "write_once",
                 "who stopped a zone deciding anything. Written once with the retirement"),
    Reachability("plt01", "acc_zones", "retire_reason", "write_once",
                 "**why an area stopped being controlled.** Prose, written once"),
    Reachability("plt01", "acc_points", "created_by", "unreachable",
                 "**who put a device at a door, facing one way.** Insert-only: the direction "
                 "decides whether this point may decide at all, so its commissioning is not "
                 "something to reattribute"),
    Reachability("plt01", "acc_points", "retired_by", "write_once",
                 "who took a door out of service. Written once with the retirement"),
    Reachability("plt01", "acc_points", "retire_reason", "write_once",
                 "**why a door stopped being controlled**, which is where an incident "
                 "naming a member gets written"),
    Reachability("plt01", "acc_policies", "created_by", "unreachable",
                 "who drafted the terms a door decides by. Insert-only, because the "
                 "separation of duties rests on this not being the publisher"),
    Reachability("plt01", "acc_policies", "published_by", "write_once",
                 "**who settled the terms.** The publishing write holds the grant and the "
                 "constraint refuses the author's own id; the status trigger admits no "
                 "second publication"),
    Reachability("plt01", "acc_policies", "retired_by", "write_once",
                 "who withdrew a live policy. Written once"),
    Reachability("plt01", "acc_policies", "retire_reason", "write_once",
                 "**why terms were withdrawn.** Prose, written once"),

    # ---------------------------------------------------- MOD-026, slice 1
    #
    # **The sweep found fifteen of these and the rest are declared by hand**, which is the
    # division MOD-021 records: the actor columns match on their names and the free-text ones
    # never will. A task title is the clearest case in this module -- "call Hala about her
    # card" is the ordinary way somebody writes one -- and a settlement reason is where "she
    # asked us to stop contacting her" goes.
    Reachability("plt01", "tsk_queues", "created_by", "unreachable",
                 "who opened a work queue. Insert-only"),
    Reachability("plt01", "tsk_queues", "retired_by", "write_once",
                 "who closed a queue. Written once with the retirement"),
    Reachability("plt01", "tsk_queues", "retire_reason", "write_once",
                 "**why a queue stopped taking work.** Prose, written once"),
    Reachability("plt01", "tsk_business_hours", "created_by", "unreachable",
                 "who stated when a club's people are at work. Insert-only, because the "
                 "window is what an SLA was measured against"),
    Reachability("plt01", "tsk_business_hours", "withdrawn_by", "write_once",
                 "who took a calendar window back. Written once with the withdrawal"),
    Reachability("plt01", "tsk_business_hours", "withdraw_reason", "write_once",
                 "**why a window was withdrawn.** Prose, written once"),
    Reachability("plt01", "tsk_business_hours", "note", "unreachable",
                 "**prose on a calendar window**, where 'closed for Khalid's wedding' is the "
                 "ordinary thing to write. Insert-only: no runtime role holds UPDATE on it"),
    # **`unreachable`, not `covered`, and the registry's own guard is why.** `covered` is
    # defined as "names the subject only by `identity_id`, and the row that identifier points
    # at is itself anonymized", and its test requires the reference to be into `iam`. These
    # are `ppl_persons` ids. The argument still holds -- MOD-014 extended the executor to
    # anonymise that row -- but `unreachable` is the stronger and truer statement about *this*
    # column: no runtime role can write it at all.
    Reachability("plt01", "tsk_cases", "subject_id", "unreachable",
                 "**who or what this case is about.** Insert-only: moving it would keep the "
                 "case's whole history and start describing somebody else"),
    Reachability("plt01", "tsk_cases", "title", "write_once",
                 "**the case's own sentence**, which names the member it is about as often "
                 "as not. Editable, and no erasure path clears it"),
    Reachability("plt01", "tsk_cases", "opened_by", "unreachable",
                 "who opened the case. Insert-only"),
    Reachability("plt01", "tsk_cases", "resolved_by", "write_once",
                 "who resolved it. The one-way trigger admits no second resolution"),
    Reachability("plt01", "tsk_cases", "resolution_reason", "write_once",
                 "**what happened in the end.** Prose, and the one field a case exists for; "
                 "the trigger makes it final"),
    # `0024`, ADM-CC-06's own fields. The assignee is the one here that moves on every
    # reassignment, so `write_once` would be accepted by every test while being plainly
    # false -- the judgement MOD-026's task assignee already cost once. `anonymize` is the
    # true one: a case owned by somebody who has been erased is unowned work, and who
    # actually resolved it survives on the write-once `resolved_by`.
    Reachability("plt01", "tsk_cases", "assignee_person_id", "anonymize",
                 "**who owns this exception now.** It moves on every handover, so the "
                 "erasure clears it: an exception owned by an erased person is unowned work, "
                 "and who resolved it survives on `resolved_by`",
                 clears=("assignee_person_id",), locate_by="assignee_person_id"),
    # **These two are not cleared, and the constraint is why.**
    # `tsk_cases_snooze_attributed` admits all five snooze columns or none, so clearing these
    # alone is a row the schema refuses -- and clearing all five would un-defer the case,
    # moving it back into a queue somebody has to work. An erasure that changes what a tenant
    # has to do today has a side effect, so these are residue and say so.
    Reachability("plt01", "tsk_cases", "snoozed_by", "write_once",
                 "who deferred it. Cleared by an early return, which is a product act, and "
                 "never by an erasure: the five snooze columns are all-or-none and dropping "
                 "them all would put the case back in somebody's queue"),
    Reachability("plt01", "tsk_cases", "snooze_reason", "write_once",
                 "**why it was deferred.** Prose -- waiting on the member's consultant is "
                 "how one gets written -- and residue no erasure reaches, for the reason "
                 "beside it"),
    Reachability("plt01", "tsk_case_affected", "affected_id", "unreachable",
                 "**one of the records an exception is about.** Insert-only and in the "
                 "primary key, which is what makes the count of affected records one a "
                 "batch action can be sized by"),
    Reachability("plt01", "tsk_case_affected", "added_by", "unreachable",
                 "who put this record on the exception. Insert-only"),
    Reachability("plt01", "tsk_case_affected", "withdrawn_by", "write_once",
                 "who took it off again. The withdrawal is written once and no erasure path "
                 "clears it, because a record taken off by mistake is what the row answers"),
    Reachability("plt01", "tsk_case_affected", "withdraw_reason", "write_once",
                 "**why a record was taken off an exception.** Prose, written once, and "
                 "residue no erasure can reach"),
    Reachability("plt01", "tsk_case_entries", "recorded_by", "unreachable",
                 "who wrote a line on the case. Insert-only: the table has no UPDATE grant "
                 "at all, because an entry nobody can rely on is no use in the dispute it "
                 "exists for"),
    Reachability("plt01", "tsk_case_entries", "summary", "unreachable",
                 "**the line itself**, which is where a conversation with a member is "
                 "written down. No UPDATE grant, so nothing can clear it -- the same residue "
                 "MOD-014's notes carry, and declared for the same reason"),
    Reachability("plt01", "tsk_case_entries", "document_ref", "unreachable",
                 "a locator for a file this build does not hold, whose path may name the "
                 "member. No UPDATE grant"),
    Reachability("plt01", "tsk_tasks", "subject_id", "unreachable",
                 "what the task is about; see `tsk_cases.subject_id`. Insert-only"),
    # **`anonymize`, which means the executor really clears it.** This column is the one in
    # the module that is neither insert-only nor written once: it moves every time work is
    # reassigned. So `write_once` would be a false sentence that the test would nonetheless
    # accept -- the mechanism name saying one thing while the reason corrected it, which is
    # the "a docstring is not an attribution" shape. Clearing is also the right behaviour: a
    # task assigned to somebody who has been erased is unassigned work, and who actually did
    # it survives on `settled_by`.
    Reachability("plt01", "tsk_tasks", "assignee_person_id", "anonymize",
                 "**the staff member the work sits with.** Set to NULL, which un-assigns "
                 "their open tasks -- the column is nullable because an unassigned task is "
                 "the queue's whole purpose, so there is no tombstone to invent",
                 clears=("assignee_person_id",), locate_by="assignee_person_id"),
    Reachability("plt01", "tsk_tasks", "title", "write_once",
                 "**the task's own sentence**, and the likeliest place in this module for a "
                 "member's name: 'call Hala about her card' is how one gets written. "
                 "Editable, and no erasure path clears it"),
    Reachability("plt01", "tsk_tasks", "created_by", "unreachable",
                 "who raised the task. Insert-only"),
    Reachability("plt01", "tsk_tasks", "settled_by", "write_once",
                 "who finished or called it off. The settlement trigger makes it final"),
    Reachability("plt01", "tsk_tasks", "settle_reason", "write_once",
                 "**why it was not done**, which is the question R07's outcome reporting is "
                 "for. Prose, made final by the same trigger"),
    Reachability("plt01", "tsk_tasks", "evidence_ref", "write_once",
                 "a locator whose path may name the member. Editable while the task is open "
                 "and cleared by nothing"),
    Reachability("plt01", "tsk_checklist_items", "created_by", "unreachable",
                 "who wrote the checklist. Insert-only"),
    Reachability("plt01", "tsk_checklist_items", "completed_by", "write_once",
                 "**who ticked the step.** Written once with the tick, because a checklist "
                 "whose ticks nobody owns is a checklist nobody can be asked about"),
    Reachability("plt01", "tsk_checklist_items", "label", "write_once",
                 "**the step's own words**, which name a member as readily as a task title "
                 "does. Editable, and cleared by nothing"),
    # ---------------------------------------------------- MOD-026, slice 2 (iam)
    #
    # The sweep demanded two of these; the other four are declared by hand, which is the
    # division MOD-021 records. `from_identity_id` and `to_identity_id` are the row's whole
    # point and carry no UPDATE grant, so the database refuses to move them -- which is also
    # what makes "whose authority did this approval carry" answerable a year later.
    Reachability("iam", "approval_delegations", "from_identity_id", "unreachable",
                 "**whose approval authority was handed over.** Insert-only: moving it would "
                 "rewrite whose authority an approval already carried"),
    Reachability("iam", "approval_delegations", "to_identity_id", "unreachable",
                 "who held it. Insert-only, for the same reason"),
    Reachability("iam", "approval_delegations", "created_by", "unreachable",
                 "who delegated. The same identity as `from_identity_id` by construction -- "
                 "the service derives it from the session -- and kept separately because a "
                 "column that merely agrees today is not a column that answers tomorrow"),
    Reachability("iam", "approval_delegations", "reason", "unreachable",
                 "**why somebody handed their approvals over**, which is prose and is where "
                 "'she is in hospital' gets written. No UPDATE grant, so nothing clears it"),
    Reachability("iam", "approval_delegations", "revoked_by", "write_once",
                 "who took it back. Written once with the revocation"),
    Reachability("iam", "approval_delegations", "revoke_reason", "write_once",
                 "**why it ended early.** Prose, written once"),
    Reachability("iam", "approval_policy_stages", "created_by", "unreachable",
                 "**who wrote this step of a staged approval.** `GRANT SELECT, INSERT` and "
                 "nothing else, so neither the step nor the name on it moves: a stage order "
                 "that could be edited after requests were made against it is the defect the "
                 "request's own snapshot exists to prevent, and the author is what makes the "
                 "order answerable a year later"),
    Reachability("iam", "approval_decisions", "on_behalf_of", "unreachable",
                 "**on whose authority a decision was made**, which is half of what makes an "
                 "approval accountable. The table has no UPDATE grant at all: a decision is "
                 "what was decided"),

    # ---------------------------------------------------- MOD-026, slice 3b
    #
    # Four demanded by the sweep and two declared by hand: both reason columns are prose,
    # and `tsk_sla_pauses.reason` is the one a reader should worry about -- "waiting on the
    # member's consultant" is how somebody records why a clock stopped.
    Reachability("plt01", "tsk_sla_clocks", "created_by", "unreachable",
                 "who put a target on this work. Insert-only: a promise is not reattributed"),
    Reachability("plt01", "tsk_sla_clocks", "settled_by", "write_once",
                 "who judged the target met, breached or cancelled. The one-way trigger "
                 "admits no second judgement"),
    Reachability("plt01", "tsk_sla_clocks", "settle_reason", "write_once",
                 "**why a target was judged as it was.** Prose, made final by the same "
                 "trigger"),
    Reachability("plt01", "tsk_sla_pauses", "paused_by", "unreachable",
                 "who stopped the clock. Insert-only, because when it stopped and who said "
                 "so is what the row exists to state"),
    Reachability("plt01", "tsk_sla_pauses", "reason", "unreachable",
                 "**why the clock stopped**, which is prose and is asked precisely when a "
                 "target was missed. No UPDATE grant, so nothing clears it"),
    Reachability("plt01", "tsk_sla_pauses", "resumed_by", "write_once",
                 "who started it again. Written once with the resumption"),

    Reachability("plt01", "tsk_dependencies", "created_by", "unreachable",
                 "who said this task waits on that one. Insert-only, because the table has "
                 "no UPDATE grant: changing which task blocks which is two edges and both "
                 "should be visible"),
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


#: Mechanisms no erasure path touches. Both belong in the residue a completion report
#: discloses: the distinction between them is about *why* the column does not change, which
#: matters to a reviewer and not to the subject whose identifier survives either way.
_NOT_ERASED = ("unreachable", "write_once")


def unreachable_columns() -> tuple[Reachability, ...]:
    """The columns erasure cannot reach, which is what a completion report has to disclose.

    Includes `write_once` as well as `unreachable`. Returning only the latter would have
    dropped two columns out of every residue report the moment `write_once` was introduced --
    the report would have got shorter without anything becoming erasable.
    """
    return tuple(r for r in SUBJECT_COLUMNS if r.mechanism in _NOT_ERASED)


def write_once_columns() -> tuple[Reachability, ...]:
    """Columns a service writes once and no erasure path clears. Not the same as unreachable."""
    return tuple(r for r in SUBJECT_COLUMNS if r.mechanism == "write_once")


def deletion_is_complete() -> bool:
    """Whether erasure can be total in this build. It cannot, and saying so is the point.

    A caller that reports a deletion request "completed" without consulting this is reporting
    something untrue. `app.privacy.dsar` uses it to decide between `completed` and a partial
    completion that names what survived.
    """
    return not unreachable_columns()
