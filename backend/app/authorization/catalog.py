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
    # **A class per permission, because one permission for all of them is one class.** MOD-014's
    # field masking maps each of MOD-008's five sensitivity classes to the permission that opens
    # it, and the first version pointed `identity` and `contact` at the same one -- which made a
    # national id exactly as protected as an email address -- and `financial` at a *write*
    # permission, which is not a read control at all. Both are financial class, so reading
    # either needs a stepped-up session as well as the grant.
    _p("member.identity.read", "See a member's identity documents and date of birth",
       "data_access", "financial"),
    _p("member.finance.read", "See a member's financial identifiers",
       "data_access", "financial"),
    # MOD-014, people, profiles and Member 360.
    #
    # The read permissions are routine: a front desk looks somebody up a hundred times a day and
    # a step-up requirement on that would mean nobody is ever looked up. What they open is
    # bounded by the masking -- a routine read returns the record with every class the caller
    # does not separately hold replaced, which is the control `member.identity.read` and
    # `member.finance.read` above are the keys to.
    _p("people.person.read", "See a person and their profiles", "data_access"),
    _p("people.person.write", "Create or change a person", "data_access", "financial"),
    _p("people.relationship.write", "Record or end a relationship between two people",
       "data_access", "financial"),
    # **A note is what somebody wrote about a person and it cannot be edited**, so writing one
    # is financial class: the record it creates is permanent and will be read in a dispute.
    _p("people.note.write", "Record or withdraw a note about a person",
       "data_access", "financial"),
    _p("people.timeline.read", "Read a person's timeline", "data_access"),
    # **Merging is the one operation here that makes a record stop being usable**, and
    # paragraph 10200 requires it to be reviewable. Financial class, so an AAL-1 session cannot
    # reach it at all, and the reversal is charged the same because undoing a merge is as
    # consequential as making one.
    _p("people.merge.decide", "Merge two people, or reverse a merge",
       "data_access", "financial"),
    _p("people.duplicate.review", "See and dismiss duplicate candidates", "data_access"),
    # The schema a tenant's custom fields and tags live under. Configuration rather than data
    # access, because declaring a field is changing what the product collects about everybody.
    _p("people.schema.write", "Declare a tag or a custom field",
       "configuration", "financial"),
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
    # MOD-013, notifications. Authoring a template is content that goes out under the tenant's
    # name to everybody, so writing and approving it are `financial`-class and are **separate
    # permissions** -- an author cannot approve their own, which the schema enforces too.
    _p("notifications.template.read", "See notification templates", "data_access"),
    _p("notifications.template.write", "Create or retire a notification template",
       "configuration", "financial"),
    _p("notifications.template.approve", "Approve a template for publication",
       "configuration", "financial"),
    _p("notifications.preference.read", "See a recipient's notification preferences",
       "data_access"),
    _p("notifications.preference.write", "Set a recipient's notification preferences",
       "data_access"),
    # Separate from `template.read`, which shared it at first: the channel policy carries
    # `cost_per_message_minor`, so a role granted "see notification templates" was also
    # reading what every message costs the tenant.
    _p("notifications.policy.read", "See channel policies and their per-message cost",
       "configuration"),
    _p("notifications.policy.write", "Enable a channel, set its fallback or its cost",
       "configuration", "financial"),
    _p("notifications.notification.read", "See notifications and their delivery state",
       "data_access"),
    # The message text, which is the most personal thing this build renders. Separate from the
    # list permission so a support role can see that something was sent without reading it --
    # MOD-010's lateral-read finding, answered by splitting the read rather than by a comment.
    _p("notifications.notification.read_content",
       "Read the text of a notification that was sent", "data_access", "financial"),
    _p("notifications.notification.request", "Request a notification", "data_access"),
    # **A critical alert is a different permission from an ordinary request.** It overrides the
    # recipient's opt-out, their quiet hours and their frequency cap, and the first version
    # bought that with the routine permission above plus a non-blank string in the body --
    # paragraph 2461's "only under documented policy" satisfied by one keystroke, which is
    # MOD-009's `consent_subject` finding in this module's clothes. Financial class, so it
    # needs a stepped-up session as well as the grant.
    _p("notifications.notification.request_critical",
       "Request a notification that overrides a recipient's preferences",
       "data_access", "financial"),
    # Moving a recipient's address binding is how somebody would walk a complainant's address
    # away from the bounce suppression recorded against it, so it is not the write permission
    # that sets an ordinary preference.
    _p("notifications.recipient.rebind",
       "Move a recipient's address binding on a channel", "data_access", "financial"),
    # Routine, and the sixth of its kind: a dispatcher runs on a loop and a step-up requirement
    # would mean nothing is ever sent. Its reach is bounded by what it can change -- a delivery
    # settles itself, and the authored message carries no UPDATE grant at all.
    _p("notifications.delivery.dispatch", "Claim and settle a delivery", "data_access"),
    _p("notifications.suppression.read", "See suppressed addresses", "data_access"),
    _p("notifications.suppression.write", "Suppress an address", "data_access"),
    # Releasing is a decision to resume sending to an address that asked to stop, so it is
    # financial-class and the schema only admits it for an unsubscribe.
    _p("notifications.suppression.release", "Release a suppression",
       "configuration", "financial"),
    # MOD-016, the commercial catalog and its pricing.
    #
    # **The two reads a till does constantly are routine**, because a step-up requirement on
    # resolving a price or redeeming a code would mean nothing is ever sold. Their reach is
    # bounded by what they can change -- and the first version of this comment claimed more
    # than was true, which is worth leaving in place as the correction it is. It said a
    # resolution "carries no authority of its own" and that a redemption "cannot exceed the
    # limits counted from the ledger beside it". Both were false: the resolution *is* the
    # number the customer pays, and nothing on the pricing path wrote the ledger the limits
    # were counted from, so a single-use 90% code priced six sales on `catalog.price.resolve`
    # alone. `resolve_price` now redeems in the same transaction, which is what makes the
    # second half of that sentence true; the first half is simply withdrawn.
    _p("catalog.product.read", "See the product catalog", "data_access"),
    _p("catalog.price.read", "See price books and what a sale would cost", "data_access"),
    _p("catalog.price.resolve", "Resolve a price and record the explanation", "data_access"),
    _p("catalog.coupon.redeem", "Redeem a coupon code", "data_access"),
    # Asking for a discount changes nothing by itself -- the approval is the authority -- so
    # this is routine and the one beside it is financial. The two exist separately because a
    # separation of duties needs two acts to compare.
    _p("catalog.discount.request", "Ask for a manual price override", "configuration"),
    # Writing the catalogue is a commercial act with a financial consequence for every sale
    # that follows, so each of these is financial class and needs a stepped-up session.
    _p("catalog.product.write", "Create or change a product", "configuration", "financial"),
    _p("catalog.product.publish", "Publish or retire a product",
       "configuration", "financial"),
    _p("catalog.price.write", "Write a price or a price book", "configuration", "financial"),
    _p("catalog.promotion.read", "See promotions and coupons", "data_access"),
    _p("catalog.promotion.write", "Create, activate or revoke a promotion or coupon",
       "configuration", "financial"),
    # **The one permission that lets somebody choose the price.** Paragraph 10220: "manual
    # price overrides and high discounts require explicit permission and audit." The permission
    # is this; the audit is `cat_discount_approvals`, and the schema refuses an approver who is
    # also the requester.
    _p("catalog.discount.approve", "Approve a recorded discount request",
       "configuration", "financial"),
    _p("catalog.bundle.write", "Define what a bundle owes", "configuration", "financial"),
    # **Financial, not routine, and the first version had it wrong for an instructive reason.**
    # It was classed routine on MOD-013's dispatcher precedent -- whatever fulfils a bundle
    # runs on a loop -- with "the record it writes is insert-only" offered as why that was
    # safe. Insert-only was in fact what made it unrecoverable: a reviewer recorded all ten
    # sessions of a ten-session bundle as delivered on a routine AAL-1 session, and the real
    # fulfiller was then refused for ever, with no UPDATE and no DELETE grant to undo it.
    # There is now a `reversed` outcome, so the act is correctable -- and it is still
    # financial, because extinguishing a paid-for entitlement is not a routine read.
    _p("catalog.bundle.fulfil", "Record what a bundle sale delivered",
       "configuration", "financial"),
    # MOD-017, the membership contract a member signs and the money it generates.
    #
    # **`finance.*` rather than `billing.*`, which is MOD-015's.** Those permissions govern
    # Veyro billing the tenant for its subscription; these govern the tenant billing its own
    # members. One prefix for both would let a role granted "see invoices" see the wrong
    # party's -- the two are owed by different people in different currencies.
    #
    # **The split is by consequence, not by table.** Reading a membership is routine; moving
    # one is financial, because every lifecycle act either changes what a member may do or
    # changes what they owe. The two reads a turnstile and a front desk do constantly stay
    # routine for MOD-016's reason -- a step-up on "may this member train" would mean nobody
    # trains -- and what bounds them is that neither can change anything.
    _p("membership.record.read", "See a membership, its history and its terms",
       "data_access"),
    # **Drafting a contract version and publishing it are two permissions**, because the
    # schema makes them two acts by two people and a role holding one permission for both
    # would satisfy the separation only by accident. This is the prose a member is held to and
    # the policy numbers every lifecycle decision is measured against, published under the
    # tenant's name to everybody who signs on these terms -- MOD-013's author-and-approver
    # split on notification templates, applied to the document with legal effect.
    _p("membership.contract.write", "Draft a membership contract version",
       "configuration", "financial"),
    _p("membership.contract.publish",
       "Publish a contract version somebody else drafted",
       "configuration", "financial"),
    _p("membership.agreement.write", "Create or sign a membership agreement",
       "configuration", "financial"),
    # Activation is separate from writing the agreement because it is the act that starts the
    # money and the access: the same person routinely does both, and an auditor asks which.
    _p("membership.agreement.activate", "Activate a signed agreement",
       "configuration", "financial"),
    # **Freezing, resuming and cancelling are financial**, each for a different reason:
    # a freeze stops billing and extends a term, a resume restarts both, and a cancellation
    # ends a contract with a fee the member was quoted.
    _p("membership.lifecycle.change", "Freeze, resume, transfer or cancel a membership",
       "configuration", "financial"),
    _p("membership.entitlement.read", "See what a member is entitled to and what is left",
       "data_access"),
    # **Granting is financial and drawing is routine**, which is the division that matters: a
    # grant creates a right somebody did not buy, and a draw consumes a right they did. A
    # turnstile and a booking flow hold the second and nothing more.
    _p("membership.entitlement.grant", "Grant or revoke an entitlement",
       "configuration", "financial"),
    _p("membership.entitlement.draw", "Reserve, consume or release an entitlement",
       "data_access"),
    _p("finance.account.read", "See a member billing account, its invoices and its schedule",
       "data_access"),
    _p("finance.account.write", "Create or change a member billing account or schedule",
       "configuration", "financial"),
    # Issuing an invoice allocates a fiscal serial that can never be reused, which is why it
    # is its own permission rather than part of writing a schedule.
    _p("finance.invoice.issue", "Issue a member invoice and allocate its fiscal serial",
       "configuration", "financial"),
    _p("finance.payment.take", "Create a payment intent and settle it",
       "configuration", "financial"),
    # **The refund is two permissions, because paragraph 1598 requires an approval and the
    # schema compares two derived identities.** Asking changes nothing; approving sends money
    # back out, which is the one act in this module that moves money away from the tenant.
    _p("finance.refund.request", "Ask for a member refund", "configuration"),
    _p("finance.refund.approve", "Approve a member refund somebody else requested",
       "configuration", "financial"),
    _p("finance.dunning.manage", "Open and advance a recovery journey",
       "configuration", "financial"),
    # **Fiscalization is its own permission.** It is the act that tells a tax authority an
    # invoice is final, and the person who issues invoices is not necessarily the person who
    # files them.
    _p("finance.fiscal.manage",
       "Move an invoice's fiscal state and record its acknowledgement",
       "configuration", "financial"),
    # Reconciling an unknown provider state decides whether money arrived, so it is financial
    # even though it writes no new charge.
    _p("finance.payment.reconcile",
       "Reconcile a payment whose provider state is unknown",
       "configuration", "financial"),
    # MOD-018, the ledger. **`finance.ledger.*` rather than more `finance.account.*`**,
    # because the two answer different questions and one role routinely holds only the first:
    # a bookkeeper reads and posts journals and has no business creating a member's billing
    # account, and a front-desk role is the reverse.
    #
    # **Reading the ledger is `data_access` and routine**, which is deliberate and worth
    # stating: a trial balance is how somebody finds out that something is wrong, and a read
    # that needed a step-up is a read nobody does until the month-end panic. What bounds it is
    # that it changes nothing.
    _p("finance.ledger.read",
       "See the chart of accounts, journals, postings, recognition schedules, "
       "reconciliation cases and a trial balance", "data_access"),
    # **Posting is financial and so is correcting**, and correcting is separate: a correction
    # reverses a figure somebody already reported, and an auditor asks which role could do
    # that rather than which role could post at all.
    _p("finance.ledger.post", "Post a journal to the ledger",
       "configuration", "financial"),
    _p("finance.ledger.correct", "Reverse a posted journal with a compensating entry",
       "configuration", "financial"),
    _p("finance.ledger.chart", "Open or retire a ledger account",
       "configuration", "financial"),
    # **The wallet is two permissions, because they move money in opposite directions.**
    # Crediting creates a liability the tenant owes -- a giveaway, a goodwill gesture, money
    # taken in -- and debiting spends a member's own balance. A role that could do the second
    # and not the first is a till; one that could do the first and not the second is marketing.
    _p("finance.wallet.read", "See a member's wallet balance and statement", "data_access"),
    _p("finance.wallet.credit", "Add value to a member's wallet",
       "configuration", "financial"),
    _p("finance.wallet.debit", "Spend a member's wallet value",
       "configuration", "financial"),
    # Recognition moves money from a liability to revenue, which is the figure a tax return is
    # built from.
    _p("finance.recognition.manage",
       "Declare how a sale earns and post what it has earned",
       "configuration", "financial"),
    _p("finance.settlement.import", "Import and match a provider settlement file",
       "configuration", "financial"),
    _p("finance.reconciliation.manage",
       "Work a reconciliation case: investigate, resolve or write it off",
       "configuration", "financial"),
    # **A till session is routine.** A front desk opens and closes a drawer every shift, and a
    # step-up per close is a step-up nobody completes -- so what bounds it is that the variance
    # is posted to suspense and opens a case rather than disappearing. MOD-016's reasoning
    # about the two reads a turnstile does, applied to the act a clerk does hourly.
    _p("finance.cash.session", "Open and close a till session", "configuration"),
    # Banking the cash is not: it is money leaving the premises.
    _p("finance.cash.deposit", "Bank a deposit and confirm what the bank credited",
       "configuration", "financial"),
    # **Closing a period makes a figure final and reopening one un-makes it**, which is why
    # they are two permissions. An auditor asks about the second.
    _p("finance.period.close",
       "Begin or finish closing a financial period, and post the close's own entries",
       "configuration", "financial"),
    _p("finance.period.reopen", "Reopen a closed financial period",
       "configuration", "financial"),
    _p("finance.export.run", "Export a closed period to an accounting system",
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
