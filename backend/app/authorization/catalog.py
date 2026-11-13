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
