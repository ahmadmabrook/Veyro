---
doc: ADR-006
status: DECIDED (2026-09-19) — bounded Convergence Gate adopted, OWN-005
date: 2026-09-19
---

# ADR-006: Bounded Convergence Gate replaces the MOD-001 repeated-full-Scenario-Review stopping rule

## Context

MOD-001 ran 16 consecutive independent Scenario Review rounds
(`knowledge/03-Modules/MOD-001/SCENARIOS.md` §5). Each round found real
P0/P1/P2/Editorial defects, all remediated the same session, then
required a completely fresh full independent round to confirm the
remediation — per a rule cited from round 4 onward as **"the owner's
explicit review-budget rule"** (`SCENARIOS.md:2839`, restated per-round
as "Round-15 Gate Rule" / "Round-16 Gate Rule": *"any P0 or P1 means
remediate, keep NOT READY, do not evaluate Definition of Ready, another
independent Scenario Review is required"*). Round 16 (2026-09-19)
returned `P0=0, P1=4, P2=6, Editorial=4`; all findings were remediated
same session; a separate independent evidence-integrity adjudication
confirmed 0 Ready-blocking defects. The rule as stated would still have
required an unbounded Round 17.

A governance adjudication was run this session
(`knowledge/03-Modules/MOD-001/STATUS.md`, `CURRENT_HANDOFF.md` chunk
46/47) to determine whether higher-precedence governance actually
requires this specific stopping condition. Findings:

- **`EIP_MIRROR.md:1622-1719`** (§8, Definition of Ready / Module
  Lifecycle table) lists **Ready** and **Scenario Review** as two
  distinct, sequential gates (`Backlog → Locked → Ready → Scenario
  Review → In Development → ...`, `EIP_MIRROR.md:1407-1413`). Ready's
  own minimum evidence (dependencies/scope/module-spec/environment,
  `EIP_MIRROR.md:1627-1633`) does not require Scenario Review to
  already be clean. Scenario Review's own minimum evidence
  (`EIP_MIRROR.md:1665-1668`) is "Scenario Catalog reviewed by
  independent QA context; all Required requirements/behaviors mapped;
  high-risk deepening complete" — no round-count or P0/P1-counting
  mechanic is specified.
- **`DEVELOPMENT_CONSTITUTION.md`** DC-02/03/05/06/07 require
  independent, fresh-context review and full execution of Required
  scenarios before approval; DC-08 requires zero known P0/P1/P2
  defects at **module certification**, not at the intermediate
  Scenario Review gate specifically. None of these mandate that a
  remediated round must be re-verified by a from-scratch catalog
  re-audit rather than a bounded, independent, fresh-context
  verification of the remediation plus the invariants that matter.
- TSD is silent on this process question (architecture document, not
  process).
- The specific stopping condition traces only to `SCENARIOS.md:2839`'s
  "the owner's explicit review-budget rule." `OWNER_APPROVALS.md` was
  checked directly and carries no corresponding `OWN-<NNN>` row — this
  citation was never durably backfilled, unlike every other real owner
  decision on this project.
- Direct project precedent exists for resolving an identical pattern
  (every independent review round finding something new) via an
  **owner-authorized bounded round-cap**, not an open-ended loop: the
  Bash guard v1→v2 security review (`CURRENT_HANDOFF.md` chunks 20-24)
  hit exactly this shape and was resolved by explicit owner
  authorization of a capped final round plus a named architecture
  conclusion, never self-granted by the reviewing/orchestrating
  session.

**Conclusion of the adjudication:** the repeated-full-round stopping
condition is not mandated by Blueprint/TSD/EIP/DC at the level of
strictness it has been enforced; it is a locally-observed operating
rule, attributed to the owner but not durably recorded, and does not
by itself satisfy DC-09's "no silent process deviation without an ADR"
in reverse (i.e., its own introduction was never given an ADR either).
Only the owner can authorize changing a rule attributed to their own
instruction — this ADR does not self-authorize that change.

## Decision needed (owner-reserved — this ADR cannot self-resolve it)

Replace the repeated-full-Scenario-Review stopping rule with a bounded
Convergence Gate, or require Round 17 (and any subsequent rounds) to
proceed under the original rule as stated.

## Decision (2026-09-19)

**Owner chose option (a):** replace the local MOD-001 stopping rule
with the bounded Convergence Gate rule below. Recorded as `OWN-005` in
`knowledge/00-System/OWNER_APPROVALS.md`. The owner explicitly confirmed
the original rule was never intended to create an unbounded review loop,
and that this decision does not lower any technical acceptance
criterion.

### Bounded Convergence Gate rule (in force, supersedes the repeated-full-round rule)

After an independent Scenario Review returns findings and those
findings are remediated:

1. A fresh-context independent Convergence Gate verifies: all previous
   P0/P1 remediation; directly affected critical invariants; current
   Ready-blocking P0/P1; baseline integrity; capability/routing state;
   owner/external gates.
2. A new issue may block Ready only when it is: directly supported by a
   governing source; a present planning defect; materially prevents
   safe/correct implementation from starting; not an explicitly
   governed implementation-time deferred obligation.
3. P2/editorial/cleanup/new-hardening findings do not trigger a new
   planning-review cycle unless the governing source explicitly makes
   them a Ready condition.
4. If the Convergence Gate returns current Ready-blocking `P0=0`,
   `P1=0`, and all critical Definition-of-Ready invariants `PASS`, the
   planning-review cycle may terminate and MOD-001 may proceed to
   Definition of Ready.
5. The Convergence Gate does not replace later Code Review, Manual QA,
   Security review, Performance/Load review, Gatekeeper certification,
   cumulative regression, or module approval.

P0/P1 standards are unchanged; independent fresh-context assurance
remains mandatory; explicitly governed implementation-time deferred
work (e.g. the `ADR-005`-deferred rule-file content) is not itself a
Ready blocker merely because it is not yet implemented.

## Consequences

- Scenario Review Round 17, as an unbounded full-catalog re-audit
  triggered automatically by round 16 having returned P1 findings, is
  **not required**. The next legally allowed action is a bounded,
  fresh-context Convergence Gate against round 16's remediation — not
  a 17th full independent Scenario Review, not implementation, not a
  self-granted Ready determination.
- This rule governs MOD-001's remaining planning-review cycle and sets
  precedent for future modules' planning-review cycles absent a
  module-specific owner override.
- `knowledge/03-Modules/MOD-001/STATUS.md` and `SCENARIOS.md` §5 are
  corrected to reference this rule going forward; historical round
  entries (rounds 1-16) are left unedited, per this project's existing
  policy of not rewriting historical review-log rows — a dated
  correction note is appended instead.

## Status

**DECIDED.** Not yet exercised: no Convergence Gate has been run under
this rule as of this ADR's authoring. MOD-001 remains ACTIVATED —
PLANNING/SPECIFICATION IN PROGRESS, **NOT READY, NOT APPROVED**;
implementation has not started and was not started by this ADR; no
Scenario Review Round 17 was run.
