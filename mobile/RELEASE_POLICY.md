---
doc: MOBILE_RELEASE_POLICY
status: LIVE — policy document (enforcement lives in `backend/app/version_negotiation.py`)
module: MOD-001
requirement: GOV-01-R07
scenario: SCN-MOD001-115
created: 2026-10-09
---

# Mobile Minimum-Supported-Version, Optional/Forced-Update and Kill-Switch Policy

This is the **policy document** `IMPLEMENTATION.md` §12 names at
`mobile/RELEASE_POLICY.md`. Its enforcement is
`backend/app/version_negotiation.py` — a separate artifact, per §12's own
split ("`mobile/RELEASE_POLICY.md` above is the policy *document*; this is
the policy's *enforcement*"). This file states no rule the governing
baseline does not already state; where it names a concrete value that the
baseline does not fix, it says so explicitly rather than inventing one.

## 1. Governing source

TSD §24.3 "Mobile Release Policy" (`TSD_MIRROR.md` lines 11670-11700),
verbatim on the four clauses this file governs:

- "Backend APIs preserve compatibility for minimum supported app
  versions; server can expose capability/version negotiation."
- "Remote config controls rollout but cannot repair an incompatible API
  contract."
- "Minimum supported version, optional/forced update and kill-switch
  policy are explicit; forced update is reserved for security/critical
  incompatibility."
- "White-label fleet release metadata is tracked per branded app and
  store."

Module anchors: `REQUIREMENTS.md` GOV-01-R07 (including its
security-implications text: forced-update/kill-switch "must not be
triggerable without the equivalent of an authorized release decision"),
`IMPLEMENTATION.md` §12, and `SCN-MOD001-115`.

Per `REQUIREMENTS.md` §0, the governing `.docx` wins over this
mirror-sourced restatement on any conflict.

## 2. The three dispositions

Every negotiation of a client app version against the minimum supported
version resolves to exactly one of three dispositions. These are the
three `SCN-MOD001-115` enumerates, and they are the only three.

**At or above the minimum supported version — normal operation.** The
client operates with no update prompt and no block. This is the clause
"backend APIs preserve compatibility for minimum supported app
versions": a client inside the supported range is never degraded by this
policy.

**Below the minimum supported version, no forced update authorized —
operates, with an update prompt.** The client is *not* blocked. It
continues to operate and is told an update is available. The minimum
supported version alone is a prompt threshold, never a block threshold.

**Below the minimum supported version, with an authorized forced update
— blocked, citing the forced-update requirement.** The client is blocked
and the reason is carried in the decision, so the client surface can say
why rather than failing opaquely.

A client at or above the minimum is **never** blocked, even while a
forced update is authorized. A forced update's blast radius is the
below-minimum population only; a release decision cannot be used to
block the entire fleet.

## 3. Forced update is reserved — two reasons, closed set

Per TSD §24.3, "forced update is reserved for security/critical
incompatibility." The reserved set is therefore exactly two reasons:

| Reason | When it applies |
|---|---|
| `security` | A security defect in the client that cannot be mitigated server-side. |
| `critical_incompatibility` | The client can no longer transact against the supported API contract at all. |

The set is **closed**, not illustrative. A release decision asserting a
forced update with no reason, or with any reason outside these two, is
**rejected** — it is not downgraded to an optional-update prompt and not
applied. Convenience, marketing, feature rollout, and
deprecation-tidiness are not reserved reasons and cannot authorize a
forced update.

## 4. Authorization — a forced update/kill-switch needs an authorized release decision

`REQUIREMENTS.md` GOV-01-R07's security-implications text is binding:
the forced-update/kill-switch "must not be triggerable without the
equivalent of an authorized release decision."

- The **only** input that can activate a forced update is a release
  decision whose authorization is **cryptographically verified** against
  the exact bytes received. Verification precedes any parsing or any
  trust in the decision's content.
- Authorization that is **absent** or that **does not match the received
  bytes** (tampered payload, tampered signature, or a signature produced
  under a different key) is **denied**. Denial is the outcome — not a
  fallback to the previous decision, not a fallback to an optional-update
  prompt, not a default-allow.
- The verifying key is **injected by the caller**. The enforcement module
  holds no key, reads no key from the environment or from a file, and has
  no default key, so it cannot be wired to a real secret by omission
  (`.claude/rules/infra/secrets.md` control 1).
- The enforcement module **exposes verification, not signing**. Its
  synthetic HMAC verifier nevertheless holds a symmetric key; a process
  with that key could compute signatures. Production signer/verifier
  separation is not established by this slice.

**Disclosed limit.** Which authority holds the signing key, and in what
custody, is **not** decided by this policy and is not decided anywhere in
the governing baseline this module read. A real signing authority (a
managed KMS, a code-signing CA) is DC-16 owner-reserved spend —
`REQUIREMENTS.md` GOV-01-R07's and GOV-01-R03's own "Owner/external
gates" rows name a paid code-signing CA as exactly that. MOD-001's proof
is therefore a **synthetic** key injected by a test, never a real
credential, and the custody decision is left open rather than invented
here.

## 5. Remote config controls rollout, never the contract

Per TSD §24.3, "remote config controls rollout but cannot repair an
incompatible API contract." Structurally, in this policy's enforcement:

- Remote config is **not an input** to the negotiation. The enforcement
  contract accepts a client version, an API version, and a signed release
  decision — there is no rollout-percentage or remote-config parameter it
  could read.
- The signed decision's shape is **closed**: an unrecognized field in the
  decision payload is rejected, not ignored. A rollout-flavoured field
  cannot ride along inside a decision and change a disposition.
- Changing remote config therefore cannot lift a forced-update block.
  `SCN-MOD001-117`(b) tests that companion property against
  `backend/app/crash_remote_config_intake.py`, which this slice does not
  implement.

## 6. White-label fleet release metadata

TSD §24.3 tracks release metadata "per branded app and store." That
metadata is carried in `mobile/TOOLCHAIN_MATRIX.md`'s
`whitelabel_release_metadata` section per `IMPLEMENTATION.md` §12, not in
this file. **That file does not exist yet** — it is a separate
GOV-01-R07 obligation outside this slice's scope, named here so the
dependency is visible rather than implied. This policy's dispositions are
per-decision and brand-agnostic: a release decision names its own
minimum supported version, so distinct branded fleets are served by
distinct decisions, not by a brand switch inside this policy.

## 7. What this policy deliberately does not fix

**No concrete minimum supported version is set here.** The authoritative
minimum travels inside each signed release decision, which is where the
enforcement contract reads it from. Pinning a number in this document
would create a second, unsigned source of truth for the one value the
authorization exists to protect. It would also be fiction: MOD-006 owns
the mobile application (`REQUIREMENTS.md` GOV-01-R07, OUT of scope), no
real client build exists, and no real store release has occurred, so
there is no real version floor to record.

**No store-rollout mechanics, no real store action.** Apple/Google
developer-account provisioning and any real store submission are DC-16
owner-reserved per GOV-01-R07's own "Owner/external gates" row.

**No client-side prompt or block UI.** Per `IMPLEMENTATION.md` §12,
MOD-006 "owns only the client-side prompt/block UI, not the negotiation
decision itself." This policy and its enforcement produce the
disposition; rendering it is MOD-006's.

## 8. Enforcement cross-reference

`backend/app/version_negotiation.py` implements §2, §3, §4 and §5 above
as an executable contract: versioned surface, RFC 7807
(`application/problem+json`) failure bodies per `ADR_CONFORMANCE.md`'s
ADR-004 obligation, cryptographically verified authorization, and
fail-closed denial. `backend/tests/unit/test_version_negotiation.py`
exercises the three dispositions of §2 plus the absent-authorization and
tampered-authorization negatives of §4, all on synthetic values.

Conformance state for ADR-004 remains **PLANNED, not proven** until
`SCN-MOD001-119`(a) executes for real — this slice does not change that
scenario's status.
