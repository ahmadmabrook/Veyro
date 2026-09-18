---
doc: MOD-001_ROUTING_DRILL_BUG031_BUG032_CLOSURE
module: MOD-001
status: LIVE — CLOSURE EVIDENCE
date: 2026-09-17
---

# MOD-001 — Routing qualification drill: BUG-031/BUG-032 closure verification

## Context

The owner applied the drafted patch to `.claude/agents/veyro-implementer.md`
(commit `0afa609`, "fix: route activated surface profiles and test
authoring") to close `BUG-031` (P0, escalated round 7 — activated
Infra/SRE/CI and Backend surface-profile agents unreachable from any
escalation path) and `BUG-032` (P1 — `veyro-test-author` unreachable).
This drill independently verifies the patch and re-proves routing in
all 6 directions ADR-005/MODEL_ROUTING.md's routing model requires.

## 1. Owner-patch byte-for-byte verification

Independently confirmed by direct `Read` of
`.claude/agents/veyro-implementer.md` (not taken on the owner's word):
the file's current content matches the drafted patch exactly —
paragraph 3 (infra/backend activated-surface-profile escalation) and
paragraph 4 (deterministic-test-authoring escalation to
`veyro-test-author`) are both present, word-for-word as drafted, with
no other line in the file altered. Cross-checked against
`git log --oneline` (commit `0afa609` present on top of `5cfceba`,
matching `origin/main`) and `git show --stat 0afa609` (exactly 1 file
changed, `.claude/agents/veyro-implementer.md`, 5 insertions/1
deletion — consistent with a clean two-paragraph insertion).
`.claude/agents/veyro-lead.md` independently re-read and confirmed
byte-identical to its prior content — no change required or made there.

**Result: PASS — genuine, exact match.**

## 2. Routing qualification drill — 6 dispatches to `veyro-implementer`

Each dispatch was a fresh `Agent` call with `subagent_type:
veyro-implementer`, explicitly instructed not to write/edit/create any
file and not to run any repository-modifying Bash command — this is a
routing determination drill, not real implementation (MOD-001
implementation remains LOCKED). `git status` re-checked clean
immediately after all 6 dispatches completed, confirming none wrote
anything.

### 2.1 Activated Infra profile → `veyro-infra-sre-engineer`

Task: implement `.github/workflows/ci.yml` wiring MOD-001's
architecture-gate validators into CI.

Result: **escalated correctly.** The dispatched agent quoted its own
patched instruction text verbatim, cross-checked `MODEL_ROUTING.md`
§4.3's table row (Infra/SRE/CI: ACTIVATED for MOD-001, REGISTERED,
`veyro-infra-sre-engineer`), and refused to proceed, citing ADR-005's
explicit rejection of `veyro-implementer` standing in for the surface
engineer.

### 2.2 Activated Backend profile → `veyro-backend-engineer`

Task: implement `backend/app/main.py` (routine FastAPI entrypoint
scaffolding, explicitly excluding the critical-slice harness).

Result: **escalated correctly.** Quoted the patched instruction
verbatim, cross-checked `MODEL_ROUTING.md`'s Backend row (ACTIVATED,
bounded, excludes the critical-slice harness), and correctly
distinguished this routine-backend task from the critical-slice
carve-out named in the same paragraph.

### 2.3 Registered critical slice → `veyro-critical-engineer`

Task: implement the tenant-isolation/RLS test harness's fixture
schema/roles/grants (GOV-01-R02, ADR-005 Decision 1 slice 1).

Result: **escalated correctly**, and unaffected by the new patch
paragraphs — the pre-existing critical-slice carve-out (unchanged by
this patch) fired as designed, and the agent explicitly confirmed the
new Backend-profile carve-out does not override it ("excluding a
registered critical-slice harness, which routes to
veyro-critical-engineer per the paragraph above").

### 2.4 Deterministic test authoring → `veyro-test-author`

Task: write pytest cases for `SCN-MOD001-016`'s idempotency-contract
lint against its already-specified behavior.

Result: **escalated correctly.** Quoted the new fourth-paragraph
instruction verbatim, cross-checked `MODEL_ROUTING.md`'s test-authoring
row resolving to `veyro-test-author`, and correctly distinguished this
from `veyro-scenario-reviewer` (catalog-design judgment, not authoring
against an already-fixed spec) — closing `BUG-032`'s exact defect.

### 2.5 Routine, non-specialized implementation → remains with `veyro-implementer`

Task: author `mobile/TOOLCHAIN_MATRIX.md` (plain documentation, not
`backend/**`/`infra/**`, not a registered critical slice, not test
authoring).

Result: **no specialist carve-out fires**, confirmed by the dispatched
agent explicitly checking each of the three new/existing carve-outs
(activated Backend/Infra profiles, the ADR-005 critical-slice list,
deterministic test authoring) and finding none applicable — this is the
proof that routine implementation remains `veyro-implementer`'s own
routing-tier responsibility. The agent additionally (correctly, and
consistent with the project's WIP=1/no-implementation-before-Ready
discipline) flagged that MOD-001 implementation is not authorized at
all right now regardless of routing tier, and declined to produce the
file on that separate, higher-order ground — this is additional
correct caution, not a contradiction of the routing-tier proof above.

### 2.6 Architecture/ADR decision → `veyro-lead`

Task: decide whether MOD-001 should activate the KMP Mobile §4.3
surface profile ahead of MOD-006, and whether this needs an ADR
amendment.

Result: **escalated correctly**, unaffected by the new patch
paragraphs — the pre-existing architecture-decision carve-out fired,
with the agent also correctly citing `OWN-003`'s rule that the
orchestrating Sonnet session must delegate Opus-reserved
architecture/ADR judgment calls rather than deciding them itself.

## 3. Summary

All 6 required routing outcomes independently proven in one drill,
zero files written, zero repository-modifying commands run:

| Task class | Required destination | Result |
|---|---|---|
| `infra/**`/`.github/workflows/**` (Infra ACTIVATED) | `veyro-infra-sre-engineer` | PASS |
| `backend/**` (Backend ACTIVATED, non-critical-slice) | `veyro-backend-engineer` | PASS |
| Registered critical slice | `veyro-critical-engineer` | PASS |
| Deterministic test authoring | `veyro-test-author` | PASS |
| Routine, non-specialized implementation | `veyro-implementer` (routing tier) | PASS |
| Architecture/ADR decision | `veyro-lead` | PASS |

**`BUG-031` (P0, activated-surface-profile reachability): CLOSED.**
**`BUG-032` (P1, `veyro-test-author` reachability): CLOSED.**

**Disclosed gap (Scenario Review round 10, P1-4): none of this file's
six dispatches recorded an `MR-MOD001-<date>-<NNN>` evidence record or
an agent/session identity, though `EIP_MIRROR.md` lines 1095-1100 and
`ADR-005`'s binding condition 4 require that evidence. Not retroactively
edited here — a fresh dispatch with full MR-format evidence, re-proving
this same routing behavior, is recorded instead in
`ROUTING_DRILL_2026-09-18-mr-evidence-backfill.md`.**
