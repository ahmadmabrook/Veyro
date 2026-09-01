---
scope: global
---

# Rule: Owner-Reserved Restrictions (absolute)

Applies to every agent, every module, no exceptions without explicit recorded owner approval in `knowledge/03-ExternalGates/`:

1. No paid services or spend of any kind.
2. No processing of real member data — synthetic fixtures only.
3. No deploy or promotion to Production.
4. No material product, pricing, business, architecture, or scope change without explicit owner approval.

Violating any of these is a hard stop, not a judgment call. If a task appears to require one of these, stop and report `BLOCKED: OWNER_APPROVAL_REQUIRED` naming which restriction applies.
