---
doc: RULE_QUALIFICATION_REVIEW_ROUND2
status: LIVE
module: MOD-001
updated: 2026-09-19
---

# BUG-035 — Round 2 independent qualification re-review (2026-09-19)

## Context

Round 1 (`RULE_QUALIFICATION_REVIEW_2026-09-19.md`) returned P0=0, P1=4,
P2=8, Editorial=7 — BLOCKED — on the 9 `backend/`/`infra/` Rule files
`BUG-034` delivered. The owner applied a remediation patch targeting
exactly 3 of the 4 P1s (P1-4, the registration gap, was already closed
as part of `BUG-035`'s own filing): commit
`f74f4fba7720dfb60e1cfe5947e477611392d84e` ("fix: remediate MOD-001 rule
qualification P1 findings"), touching `.claude/rules/backend/api.md`,
`.claude/rules/backend/architecture.md`, `.claude/rules/infra/iac.md`,
`.claude/rules/infra/release.md` (+130/-10). This commit is `HEAD` and
matches `origin/main`.

This is a **fresh, independent, second** qualification review —
dispatched to a new fresh-context `veyro-security-reviewer` (Opus) with
no memory of round 1 or of drafting the remediation, per
`CAPABILITY_POLICY.md`'s binding rule that no capability may become
`APPROVED` solely from a Sonnet implementation run. Per this project's
established BUG-013/022/023 precedent (a review round that finds real
issues gets recorded and the session stops there — no patching by the
reviewing/orchestrating session, no forcing a clean result), this round
is being recorded as run, not silently discarded, even though its
verdict is BLOCKED again.

## Pre-review verification (orchestrating session, independent of the reviewer)

- `git rev-parse HEAD` = `git rev-parse origin/main` =
  `f74f4fba7720dfb60e1cfe5947e477611392d84e` — confirmed before dispatch.
- `verify_baselines.py` re-run: PASS, 4/4 governing baseline hashes match
  `PROJECT_INDEX.md`.
- MOD-001 lifecycle state re-confirmed: `IMPLEMENTATION IN PROGRESS`
  (`STATUS.md`).
- `BUG-035` re-confirmed `OPEN`; `RULE-001` through `RULE-009`
  re-confirmed `BLOCKED` in both `CAPABILITY_REGISTRY.md` and
  `evidence/module-capabilities.yaml` before the round started.

## Reviewer's verdict

**P0=0, P1=1 — verdict BLOCKED.**

### Verification point 1 — unauthorized manual rollback override: CLOSED

`infra/release.md` control 1 now states the rollback trigger's "only
trigger path is the pipeline's own SLO/guardrail evaluation crossing a
pre-declared threshold... no carve-out of any kind, including an
audited one, since no cited source authorizes one." The reviewer
independently confirmed the cited authority (`IMPLEMENTATION.md` line
348, Canary row) reads verbatim "not a manually-callable endpoint," and
that the rule now matches it exactly, with no residual carve-out
anywhere in the 4 infra files. **Genuinely closed.**

### Verification point 2 — backend transaction/idempotency/reconciliation coverage: CLOSED

`architecture.md` control 7 (explicit transaction boundaries, same-
transaction outbox writes, a named/tested reconciliation obligation) and
`api.md` control 8 (the full 6-element idempotency contract) were both
independently cross-checked against `EIP_MIRROR.md` lines 1270-1277 /
20926-20933, `REQUIREMENTS.md` line 584, and
`tools/validate_idempotency_contract.py`'s named-element report. The
reviewer found this to be "real gate-checkable substance, not
gesturing." **Genuinely closed.**

### Verification point 3 — third-party CI-Action supply-chain control: PARTIALLY CLOSED — new P1 found

`iac.md` control 5's SHA-pinning requirement is well-specified and
correctly closes the "floating tag/branch" half of the original P1-3.
**But the same control introduces a new, unauthorized trust carve-out**:
it self-grants trusted-publisher status to `actions/*` and `github/*`
(exempting them from independent capability review and from the
`APPROVED CAP-<NNN>` registry requirement) with no `OWN-<NNN>` entry
authorizing it — while the same sentence demands exactly that
`OWN-<NNN>` entry for any *other* publisher to be trusted. This is
recorded as **P1-A** below.

### Verification point 4 — RULE-001..009 registration consistency: CONSISTENT (hashes now stale by exactly the changed files, expected)

The reviewer recomputed SHA-256 for all 9 files and found exactly the 4
remediated files' `CAPABILITY_REGISTRY.md` hashes stale, matching the
files the remediation commit touched — no unexplained drift.
`module-capabilities.yaml` and `BUG-035` agree with the registry on all
9 IDs/paths/status. This orchestrating session independently
recomputed the same 4 hashes via `shasum -a 256` before writing this
file and confirmed an exact match to the reviewer's reported values:

| File | New SHA-256 |
|---|---|
| `.claude/rules/infra/iac.md` | `bb2af775917712be5c25c10480d3a3b2c08e845476379bcb7842b8274c1197e4` |
| `.claude/rules/infra/release.md` | `0e60f29ae4f3bffac26980c1e897e39790395d4292bf8a688fd2c4c819daf643` |
| `.claude/rules/backend/architecture.md` | `edf94618a08fefcfcaa926d079c4757165e2c741da199083f97ecccd252b93a3` |
| `.claude/rules/backend/api.md` | `5a021269e04f78b78d4b41e72ef1df6ea075e840a7955fd40231d64b69160772` |

## P0 findings

None.

## P1 findings

**P1-A (new, introduced by this remediation) — `.claude/rules/infra/iac.md`
control 5 creates an unauthorized default-trust class for third-party
GitHub Actions.**

Exact text (control 5, current HEAD): "an action published by
`actions/*`, `github/*`, or another publisher an `OWN-<NNN>` entry in
`OWNER_APPROVALS.md` has explicitly named as trusted may be adopted once
SHA-pinned... ('Qualify in project before relying on it for a gate,' not
a full independent review)."

This orchestrating session independently re-verified both load-bearing
facts the reviewer's finding depends on, directly from the primary
sources (not taken on the subagent's word):

- Read `knowledge/00-System/OWNER_APPROVALS.md` in full: only `OWN-001`
  through `OWN-003` and `OWN-005` exist; none names a GitHub Action
  publisher as trusted. No `OWN-<NNN>` entry authorizes the `actions/*`/
  `github/*` carve-out the rule text grants itself.
- Read `knowledge/00-System/CAPABILITY_POLICY.md` line 30 directly:
  "Third-party (non-Anthropic-first-party, non-harness-native)
  capabilities get no exemption of any kind." A GitHub Action published
  by a third party (even a well-known one like `actions/*`) is not an
  Anthropic first-party capability or harness-native tool, so this
  clause admits no carve-out for it absent the owner-approval path the
  rule's own text otherwise requires for "another publisher."

Both checks confirm the finding: the rule grants itself an exemption no
higher-precedence source authorizes, the same defect class as the
original P1-1 (a security-relaxing carve-out introduced by rule text
alone, with no ADR/owner-approval backing it — `DC-09`'s own
requirement). Rating it P1 (not P2) is consistent with how this project
rated the structurally identical P1-1 finding in round 1.

**Not remediated this session** — per the mission's explicit scope: this
session runs the fresh re-review and records the result; it does not
re-author rule files (`.claude/rules/**` also remains owner-gated
regardless). Closing P1-A requires either (a) removing the
trusted-publisher clause so every `uses:` reference needs both a SHA pin
and an `APPROVED CAP-<NNN>` row, or (b) an ADR plus an `OWN-<NNN>` entry
explicitly authorizing `actions/*`/`github/*` as trusted, reconciled
against `CAPABILITY_POLICY.md`'s "no exemption of any kind" clause.

## P2 / Editorial (non-blocking, recorded for a future remediation pass, not acted on this round)

- `api.md`/`architecture.md` fail-closed sections were not updated to
  name their own new controls (8 and 7 respectively) among the
  CI-blocking checks they enumerate — `iac.md`'s equivalent section was
  correctly updated ("all four" → "all five"), so this is an
  inconsistency between sibling files, not a missing capability.
- No CI validator yet implements `iac.md` control 5's SHA-pinning check
  — enforced at authoring/review time only for now.
- All 9 files still carry a stale `<!-- Target path once applied: ... -->`
  scaffold comment on line 1 (pre-existing, not from this commit).

## Disposition

`BUG-035` remains **OPEN**. `RULE-001` through `RULE-009` remain
**BLOCKED** in `CAPABILITY_REGISTRY.md` and `module-capabilities.yaml` —
not marked `APPROVED`, per this review's own P0=0/P1=1 result and the
governing mission's explicit "if and only if P0=0 and P1=0" gate. No
rule file was re-authored this session. No further review round was
requested or run this session.
