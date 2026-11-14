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
    Reachability("plt01", "evt_replay_jobs", "ran_by", "write_once",
                 "written when the job starts; `status = 'requested'` in the service is what "
                 "refuses a second run, not the grant"),
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
