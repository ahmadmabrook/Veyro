---
doc: BUG-035
status: OPEN
module: MOD-001
severity: P1 (blocks treating `backend/**`/`infra/**`/CI rule content as qualified/reliable; does not block non-backend/infra/CI implementation work)
opened: 2026-09-19
---

# BUG-035 — 9 new `backend/`/`infra/` Rule files: independent qualification review returned BLOCKED (P0=0, P1=4, P2=8, Editorial=7)

## Finding

Per `knowledge/00-System/CAPABILITY_POLICY.md` (governs "every Skill,
**Rule**, Plugin, MCP server, hook, or script"; a capability "cannot
become `ACTIVE` based only on a description or a successful install; it
must have passed [qualification] first"; "No capability may become
`APPROVED` solely from a Sonnet implementation run"), the 9 rule files
`BUG-034` delivered (`.claude/rules/backend/{architecture,api,database,concurrency,performance}.md`,
`.claude/rules/infra/{iac,secrets,observability,release}.md`) required
independent Opus qualification review before being treated as reliable
governance content. A fresh-context `veyro-security-reviewer` (Opus)
dispatch ran that review and returned:

**P0=0, P1=4, P2=8, Editorial=7 — verdict BLOCKED.**

Full record: `knowledge/03-Modules/MOD-001/evidence/model-routing/RULE_QUALIFICATION_REVIEW_2026-09-19.md`.

The 4 P1 findings:

1. **`infra/release.md` control 1** permits an "explicit, authenticated,
   audited manual override" rollback trigger path that its own cited
   authority (`IMPLEMENTATION.md` §3's Canary row: "not a
   manually-callable endpoint") explicitly forbids, with no cited source
   authorizing the carve-out — a security-relaxing addition introduced
   by rule text alone, which `EIP_MIRROR.md:20631-20639` and DC-09 both
   require an ADR for.
2. **The 5 backend files cover none of H.3's "transaction/idempotency/
   reconciliation" element**, despite `architecture.md`/`api.md` both
   quoting the exact EIP §4.3 row that names it (behind an elided
   ellipsis), and MOD-001 already owning
   `tools/validate_idempotency_contract.py` as a blocking CI gate.
3. **The 4 infra files (governing `.github/workflows/**`) have no
   third-party CI-Action supply-chain control** (pin/provenance review),
   despite `secrets.md` protecting exactly the tier-scoped secrets such
   an action would touch, and Appendix H.4's "Third-party/community/
   unknown → BLOCKED until independent approval" row applying directly.
4. **Stage-7 registration gap** — orchestrator-side, no re-authoring
   needed; closed as part of this bug's own filing (see "Registration"
   below).

## Decision

Per the reviewer's own disposition and this project's established
remediation pattern (fix, then a fresh independent re-review — never the
drafting session's or the finding session's own say-so): P1-1 through
P1-3 require re-authoring by the chartered surface agents
(`veyro-infra-sre-engineer` for P1-1/P1-3, `veyro-backend-engineer` for
P1-2), each producing corrected content the owner can apply the same way
`BUG-034`'s original patch was applied (`.claude/rules/**` remains
owner-gated — this is not new; the write-access problem `BUG-034` solved
was specifically about *creating* the files the first time, not a
standing exemption for future edits). A fresh independent qualification
review must then re-run before `review_status` may read `APPROVED`.

**Not remediated this session** — deliberately, per the mission's own
scope: "determine the next dependency-safe MOD-001 implementation
slice" (step 8) is a distinct instruction from "remediate every finding
this same turn," and re-authoring 3 files plus a third review round is
substantial work this session chose not to fold into an already-large
turn without being asked. This is recorded as a real, open, honestly
scoped follow-up, not silently deferred.

## Registration (P1-4, closed as part of this filing)

RULE-001 through RULE-009 are registered in
`knowledge/00-System/CAPABILITY_REGISTRY.md` with `review_status: BLOCKED`
(not `APPROVED`) — `qualified_by` names the drafting agents (Sonnet),
`approved_by` is empty (qualification did not pass), `content_hash` uses
the 9 SHA-256 values the reviewer independently computed, `evidence`
points to `RULE_QUALIFICATION_REVIEW_2026-09-19.md`. This follows
`CAP-007`'s own precedent of registering a capability before it clears
qualification (`QUALIFIED`/`BLOCKED` states are real, trackable registry
states, not "not yet a row").

## What this bug does NOT block

Backend/**/infra/**/CI implementation is not attempted relying on these
rules while this bug is open. Other MOD-001 implementation work
(`tools/**`, `contracts/**`) is unaffected — the same boundary `BUG-034`
enforced for slice 1 continues to apply here, for a different underlying
reason (content quality rather than write access).

## Non-goals

This bug does not authorize weakening the qualification bar to make it
pass more easily (e.g. accepting the P1-1 manual-override carve-out
without an ADR, or treating the missing idempotency/transaction coverage
as out of scope without a recorded reason) — the fix is re-authoring the
content to actually meet the bar, not lowering the bar.
