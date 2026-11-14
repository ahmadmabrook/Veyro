"""MOD-008 IAM-03: the permission catalogue, and what counts as a sensitive field.

**Permissions live in code, not in a table.** TSD paragraph 1281 names Permission as an
authoritative entity, and this module is it: a permission is a fact about what the software can
do, so a per-tenant table would let two tenants disagree about which permissions exist and the
only thing able to resolve the disagreement would be this file. `iam.role_permissions` references
these names and a CHECK constrains their shape. The deviation is recorded in CLAUDE.md.

A permission is `module.resource.action`. There is no wildcard, in the grammar or in the
evaluator: `billing.*` cannot be written, stored or matched. A role that needs three things names
three things, which is what least privilege costs and what makes an access review legible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PERMISSION = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*){2}$", re.ASCII)


class CatalogError(ValueError):
    """A permission, action or field that this module does not define."""


@dataclass(frozen=True)
class Permission:
    name: str
    description: str
    category: str
    """The audit category an action under this permission is recorded in (IAM-03-R06)."""
    action_class: str = "routine"
    """Which assurance level exercising this permission needs, as `app.identity.policy` names
    them. Written per permission rather than derived from the category, so each one is a visible
    decision somebody can disagree with.

    `privileged` means assurance level 3, which needs a hardware authenticator, which needs the
    WebAuthn verification MOD-007 does not have. Permissions marked that way therefore **cannot
    be exercised in this build at all** -- that is deliberate for break-glass support access and
    AI acting on a member's behalf, which should not be available until the strongest factor is.
    Role administration is `financial` (level 2) rather than `privileged`, because marking it
    privileged would make authorization unadministrable.
    """


def _p(name: str, description: str, category: str,
       action_class: str = "routine") -> tuple[str, Permission]:
    if not PERMISSION.fullmatch(name):
        raise CatalogError(f"{name!r} is not module.resource.action")
    if action_class not in ("routine", "financial", "privileged", "biometric_sensitive"):
        raise CatalogError(f"{action_class!r} is not an action class")
    return name, Permission(name=name, description=description, category=category,
                            action_class=action_class)


PERMISSIONS: dict[str, Permission] = dict([
    # MOD-004, the organization hierarchy.
    _p("tenancy.organization.read", "See organizations", "data_access"),
    _p("tenancy.organization.write", "Create or change organizations",
       "configuration", "financial"),
    _p("tenancy.brand.write", "Create or change brands", "configuration", "financial"),
    _p("tenancy.location.write", "Create or change locations", "configuration", "financial"),
    # MOD-005, configuration and flags.
    _p("config.definition.read", "See configuration definitions", "data_access"),
    _p("config.definition.write", "Register configuration keys", "configuration"),
    _p("config.value.publish", "Publish a configuration value", "configuration", "financial"),
    _p("config.value.rollback", "Roll a configuration value back", "configuration", "financial"),
    _p("config.flag.read", "See feature flags", "data_access"),
    _p("config.flag.write", "Change a feature flag's policy", "configuration", "financial"),
    _p("config.kill_switch.engage", "Engage or release a kill switch",
       "configuration", "financial"),
    _p("config.experiment.write", "Create or move an experiment", "configuration", "financial"),
    # Allocating is a runtime act a device performs on a member's first screen, so it is routine
    # like the other evaluation permissions -- but it **writes**, and `cfg_exposures` carries no
    # UPDATE or DELETE grant, so what it writes is permanent and is the basis of every analysis
    # of the experiment. It had been guarded by `config.flag.read`, whose own description is
    # "See feature flags"; a read-only kiosk credential could fabricate exposures for subjects
    # that do not exist, and nothing could remove them.
    #
    # Routine is correct here rather than merely pragmatic: a device cannot reach assurance
    # level 2 at all, because `complete_step_up` accepts only a verified password or recovery
    # code and there is nobody at the kiosk to present one. Marking this `financial` would not
    # add a factor; it would make the route unusable by its only caller, which is how a control
    # ends up switched off or routed around. What bounds the write instead is that it is its own
    # permission and that it is idempotent per (experiment, subject), so a compromised credential
    # can add rows for subject ids it invents but cannot rewrite one. The residual is volume, and
    # volume is the missing rate limiter's job -- see the gap list in CLAUDE.md.
    _p("config.experiment.allocate", "Assign a subject to an experiment variant", "data_access"),
    # MOD-015, commerce.
    _p("billing.plan.write", "Create or publish a plan version", "finance", "financial"),
    _p("billing.subscription.read", "See the subscription", "finance"),
    _p("billing.subscription.write", "Start or change a subscription", "finance", "financial"),
    _p("billing.invoice.read", "See invoices", "finance"),
    _p("billing.invoice.issue", "Issue an invoice", "finance", "financial"),
    _p("billing.credit_note.issue", "Credit an invoice", "finance", "financial"),
    _p("billing.refund.issue", "Issue a refund", "finance", "financial"),
    _p("billing.refund.approve", "Approve a refund", "finance", "financial"),
    # Routine on purpose, and the one `finance` permission that is. Recording a measurement is
    # machine telemetry at volume -- an emitter logging messages sent -- not a decision about
    # money. Requiring a stepped-up human session for it would be unworkable and would get the
    # check switched off; the decisions that spend the measurement (issuing, crediting,
    # approving) are the ones that need a second factor, and they have one.
    _p("billing.usage.record", "Record metered usage", "finance"),
    # Separate from recording, and financial, for the reason the comment above gives: a quota is
    # what decides when usage starts costing money and when it stops being allowed at all, and
    # defining a meter decides what is measured. Guarding them with the telemetry permission let
    # the credential being measured raise its own limit and switch its hard stop off.
    _p("billing.meter.write", "Define or change a usage meter", "finance", "financial"),
    _p("billing.quota.write", "Set a usage quota, overage or hard stop", "finance",
       "financial"),
    # MOD-007, identity.
    _p("identity.identity.read", "See identities", "data_access"),
    _p("identity.identity.write", "Create or change an identity", "access", "financial"),
    _p("identity.session.revoke", "Revoke somebody else's session", "access", "financial"),
    _p("identity.device.revoke", "Revoke somebody else's device", "access", "financial"),
    # MOD-008, authorization itself.
    _p("authz.role.read", "See roles and their permissions", "access"),
    _p("authz.role.write", "Create or change a role", "access", "financial"),
    _p("authz.assignment.write", "Grant or revoke a role", "access", "financial"),
    _p("authz.policy.write", "Write an authorization policy", "access", "financial"),
    _p("authz.approval.decide", "Decide an approval request", "access", "financial"),
    _p("authz.audit.read", "Read the audit log", "access"),
    _p("authz.access_review.conduct", "Open and complete an access review", "access", "financial"),
    # Member data, the thing most of the product is about.
    _p("member.profile.read", "See a member's profile", "data_access"),
    _p("member.profile.write", "Change a member's profile", "data_access", "financial"),
    _p("member.health.read", "See a member's health information",
       "data_access", "biometric_sensitive"),
    # MOD-009, privacy, consent and data subject requests.
    #
    # The categories are IAM-03-R06's closed set. There is no `privacy` audit category and this
    # file does not invent one: `iam.audit_events` has a CHECK over exactly those seven names,
    # so a permission categorised `privacy` would pass here and then fail at the moment a
    # denial had to be written -- which is the moment the record matters most.
    _p("privacy.purpose.read", "See the register of processing purposes", "data_access"),
    _p("privacy.purpose.write", "Register or retire a processing purpose",
       "configuration", "financial"),
    _p("privacy.consent.read", "See a subject's consent state and history", "data_access"),
    _p("privacy.consent.define", "Define a consent kind or publish a consent document",
       "configuration", "financial"),
    # Recording one's own consent is routine because the subject doing it is on a phone or a
    # kiosk at AAL-1, and a consent that can only be given from a stepped-up session cannot be
    # given at all. Recording somebody *else's* is a different act: it writes an insert-only
    # claim that a named person agreed to something, and nothing can remove it afterwards. The
    # route derives the subject from the session and asks for the second permission only when
    # the caller names a different one -- MOD-008's "derive a scope, never accept one", applied
    # to the subject of a consent record.
    _p("privacy.consent.record", "Record or withdraw one's own consent", "data_access"),
    _p("privacy.consent.record_on_behalf", "Record or withdraw consent for somebody else",
       "data_access", "financial"),
    _p("privacy.retention.read", "See retention policies and legal holds", "data_access"),
    _p("privacy.retention.write", "Set or retire a retention policy",
       "configuration", "financial"),
    # Placing a hold suspends deletion; releasing one resumes it. Both change what the product
    # is allowed to destroy, so both are financial-class and neither is available to a session
    # that only proved a password on an unfamiliar device.
    _p("privacy.legal_hold.write", "Place or release a legal hold", "configuration", "financial"),
    _p("privacy.dsar.read", "See data subject requests and their evidence", "data_access"),
    _p("privacy.dsar.open", "Open a data subject request", "data_access"),
    _p("privacy.dsar.verify", "Verify a requester's identity or clear the legal check",
       "data_access", "financial"),
    _p("privacy.dsar.fulfil", "Fulfil or refuse a data subject request",
       "data_access", "financial"),
    _p("privacy.incident.read", "See recorded security incidents", "access"),
    # Routine on purpose, and the one place in this module where that is a judgement rather than
    # an obvious call. An incident is recorded *during* an incident, and the incident may be the
    # authentication plane being unavailable; a step-up requirement here would mean the worst
    # events are the ones that go unrecorded. The row is insert-only either way, so a false
    # incident record is visible rather than destructive.
    _p("privacy.incident.record", "Record a security incident", "access"),
    # MOD-010, domain events. Categories are IAM-03-R06's closed set again; there is no
    # `events` audit category and this file does not invent one.
    _p("events.event.read", "Read the outbox, a trace or an aggregate's timeline",
       "data_access"),
    _p("events.subscription.read", "See which consumers receive which events", "data_access"),
    _p("events.subscription.write", "Route an event type to a consumer, or stop routing it",
       "configuration", "financial"),
    # Routine, and the third entry of its kind. A relay runs this on a loop as a worker; a
    # step-up requirement would mean no events are ever delivered. Its reach is bounded by what
    # it can do: the outbox grants UPDATE on the dispatch columns only, so a compromised relay
    # can mark events sent and cannot change what any of them says.
    _p("events.dispatch.run", "Fan pending events out to their subscribers", "data_access"),
    _p("events.dead_letter.read", "See quarantined deliveries", "data_access"),
    # Releasing is a decision to run a consumer against an event that already broke it, and
    # re-requesting a replay is a decision to send things again. Both are financial-class, and
    # both record who decided and why.
    _p("events.dead_letter.release", "Requeue a quarantined delivery",
       "configuration", "financial"),
    _p("events.replay.request", "Open a replay job", "configuration", "financial"),
    _p("events.replay.run", "Execute a replay job", "configuration", "financial"),
    # MOD-011, observability and FinOps. Reading a metric series is `data_access`; a cost
    # figure, a budget and a margin are money, so they are `finance` and carry the step-up that
    # every other financial write in this build carries.
    _p("ops.metric.read", "Read a metric series", "data_access"),
    # Routine, and the fourth entry of its kind, for the same reason as the relay's: a prober
    # runs on a loop and a step-up requirement would mean no probe ever reports. Its reach is
    # bounded by what it can do -- `ops_synthetic_results` is insert-only for both runtime
    # roles, so a compromised prober can add a false result and can revise nothing.
    _p("ops.metric.record", "Record a measurement or a probe result", "data_access"),
    _p("ops.objective.read", "See objectives and their verdicts", "data_access"),
    _p("ops.objective.write", "Define or retire an objective", "configuration", "financial"),
    _p("ops.synthetic.read", "See synthetic checks and their results", "data_access"),
    _p("ops.synthetic.write", "Register, enable or disable a synthetic check",
       "configuration", "financial"),
    _p("ops.capacity.read", "See capacity forecasts", "data_access"),
    _p("ops.capacity.write", "Record a capacity forecast", "configuration", "financial"),
    # **This one reads MOD-015's invoices.** Gross margin is not computable without revenue, so
    # `/ops/margin` sums `bil_invoices` net of tax, partner share and credit notes under this
    # permission rather than `billing.invoice.read`. It returns a per-currency aggregate over
    # the caller's own tenant and no invoice detail, and the two permissions are the same
    # category and the same action class -- but MOD-010's blocking finding was exactly "one
    # permission became a lateral read path around another module's", so the deliberateness
    # belongs here and not only in a route docstring.
    _p("ops.cost.read", "See cost allocation and gross margin", "finance"),
    _p("ops.cost.write", "Allocate a cost", "finance", "financial"),
    _p("ops.budget.read", "See budgets and burn alerts", "finance"),
    _p("ops.budget.write", "Set or retire a budget, or evaluate its burn",
       "finance", "financial"),
    # MOD-012, integration adapters. Authorizing a connection hands a third party access to a
    # tenant's data, so every write here is `financial`-class and needs a stepped-up session --
    # the same bar as a billing write, which is the right comparison: both give something away.
    _p("integrations.install.read", "See installed integrations and their configuration",
       "data_access"),
    _p("integrations.install.write", "Install, configure, activate or disable an integration",
       "configuration", "financial"),
    _p("integrations.install.uninstall", "Remove an integration and revoke its connections",
       "configuration", "financial"),
    _p("integrations.connection.read", "See connections, their scopes and their state",
       "data_access"),
    # The one that actually grants a third party reach. Separate from `install.write` so a role
    # can configure an integration without being able to widen who it talks to.
    _p("integrations.connection.authorize", "Authorize or revoke a connection to a provider",
       "access", "financial"),
    _p("integrations.credential.read",
       "See credential references, their scopes and their expiry", "access"),
    _p("integrations.credential.rotate", "Record a credential rotation", "access", "financial"),
    _p("integrations.sync.read", "See connector runs, cursors and diagnostics", "data_access"),
    # Routine, and the fifth of its kind: a connector runs on a loop, and a step-up requirement
    # would mean nothing ever syncs. Its reach is bounded by what it can do -- a run may settle
    # itself and move a cursor, and may not change what it is connected to or with which scopes.
    _p("integrations.sync.run", "Start, settle or retry a connector run", "data_access"),
    _p("integrations.sync.reset", "Move a cursor backwards, or reconcile",
       "configuration", "financial"),
    # The platform-plane catalogue. No tenant holds this: the surface it guards is the one that
    # publishes definitions, and it is unauthenticated today like the rest of that plane.
    _p("integrations.definition.publish", "Publish or retire an integration definition",
       "configuration", "financial"),
    # Support and AI, named separately because IAM-03-R06 audits them separately.
    _p("support.session.start", "Start a supported session as another user",
       "support", "privileged"),
    _p("ai.action.invoke", "Have an AI act on a member's behalf", "ai", "privileged"),
])

# IAM-03-R03: field-level masking for financial, biometric, health, identity and contact
# attributes. Naming them here rather than at each call site means a new surface inherits the
# classification instead of inventing one.
SENSITIVE_FIELDS: dict[str, str] = {
    "iban": "financial",
    "card_last4": "financial",
    "tax_number": "financial",
    "biometric_template": "biometric",
    "health_notes": "health",
    "medical_conditions": "health",
    "national_id": "identity",
    "passport_number": "identity",
    "date_of_birth": "identity",
    "email": "contact",
    "phone": "contact",
    "address": "contact",
}


def require_permission(name: str) -> Permission:
    """Look a permission up, refusing one this build does not define.

    A permission that is not in the catalogue cannot be granted and cannot be checked, so a typo
    in a role definition fails loudly at the moment it is written rather than quietly denying
    forever afterwards -- or, worse, quietly allowing if some future evaluator treats an unknown
    permission as a wildcard.
    """
    try:
        return PERMISSIONS[name]
    except KeyError:
        raise CatalogError(f"{name!r} is not a permission this build defines") from None


def audit_category(permission: str) -> str:
    return require_permission(permission).category


def action_class(permission: str) -> str:
    """The assurance level exercising this permission needs. See `Permission.action_class`."""
    return require_permission(permission).action_class


def classify_field(field: str) -> str | None:
    """What kind of sensitive attribute a field is, or None when it is ordinary."""
    return SENSITIVE_FIELDS.get(field)
