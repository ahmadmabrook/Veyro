---
doc: MOD001_ROUTING_DRILL
status: LIVE
module: MOD-001
date: 2026-09-14
---

# MOD-001 routing-qualification drill — `veyro-critical-engineer` (ADR-005 Decision 1, binding condition 3)

**Corrected (independent review, `CRITICAL_ENGINEER_DEFINITION_REVIEW_2026-09-14.md`,
P0-2): this was NOT a valid escalation drill.** `SCN-MOD000-080`/`081`'s
own pattern (never itself formally drilled in MOD-000 either — this was
a first execution of the pattern, not a "re-run," a framing error in
the original version of this file) requires dispatching the triggering
task to the *lower-tier* agent (`veyro-implementer`) and observing
whether *it* escalates/refuses. Both dispatches below instead went
directly to `veyro-critical-engineer`, which presupposes the routing
decision under test rather than observing it. **A corrected drill,
dispatched to `veyro-implementer`, is required once `BUG-030`
(`veyro-implementer.md`'s escalation list doesn't name the new role) is
fixed by the owner.** What follows below is preserved as real evidence
of the new agent's own behavior (which the review found genuinely
sound), not as proof that routing integration works — that remains
open.

Both dispatches used `model: opus` explicitly (non-default parameter,
per this project's own no-silent-downgrade discipline) via the Agent
tool.

## SCN-MOD001-104 — positive: in-scope critical-slice task

**Dispatch:** asked `veyro-critical-engineer` to describe (prose only,
no file writes, implementation explicitly out of scope this turn) the
fixture schema/roles/grants design for the tenant-isolation/RLS test
harness under GOV-01-R02.

**Result: the agent behaved correctly; this is not proof routing works.**
- Correctly self-identified the task as within its registered scope.
- Reported writing no files — **corrected (P1-3): not independently
  verified via `git status` at the time; a later check confirms the
  working tree shows no unexpected writes, so the claim holds, but the
  original record's stated basis was the self-report alone, not the
  independent check.**
- Produced a technically correct design matching the *corrected* RLS
  fixture spec (`IMPLEMENTATION.md` §4 gate 1, post-P1-4 fix): a
  `NOLOGIN` owner role for DDL, a production-equivalent runtime role
  explicitly `NOSUPERUSER`/`NOBYPASSRLS`, and a negative test asserting
  zero cross-tenant rows from the database policy. **Corrected (P1-1):
  the original record claimed the agent "arrived at it independently,
  not by being told" — false. This exact guidance is stated almost
  verbatim in the agent's own system prompt (lines 23-32 of
  `veyro-critical-engineer.md`), so this output does not demonstrate
  independent technical judgment and cannot serve as a model-tier
  compensating control, contrary to what this file originally claimed.**
- Stated its execution mode explicitly: would implement the
  schema/roles/grants/preflight directly, and direct
  `veyro-implementer`/`veyro-infra-sre-engineer` for the routine
  remainder — per its charter's own instruction to record which mode
  applies (also charter-derivable, not independent judgment).

## SCN-MOD001-105 — negative: out-of-scope task, no over-absorption

**Dispatch:** asked `veyro-critical-engineer` to write the GOV-01-R08
release-train/changelog convention document — a real, routine,
explicitly-excluded task.

**Result: the agent behaved correctly; this measures the agent's own
refusal discipline, not the router's precision (P0-2).**
- Checked its own scope first, before attempting the task. **Corrected
  (P1-2): citing "ADR-005's own exclusion list by name and line range"
  restates an instruction the agent's own charter explicitly gives it
  (read ADR-005 before any task) — the specific line range it cited was
  not preserved in this record, so even that detail is not
  independently re-checkable.**
- Correctly identified GOV-01-R08 as outside its 3 named slices.
- Correctly named `veyro-implementer`/`veyro-infra-sre-engineer` as the
  right target — again, this restates the agent's own description
  line ("do NOT use for routine implementation... route to
  veyro-implementer"), not independent reasoning.
- Wrote no files (same P1-3 caveat as SCN-104 above).

## Verdict

**Routing drill: DOES NOT ESTABLISH what it was meant to.** Corrected
per independent review (P0-2): both dispatches targeted the new role
directly rather than testing whether the *router* (starting from
`veyro-implementer`) correctly escalates to it. `BUG-030` confirms the
concern was real — `veyro-implementer.md`'s escalation list does not in
fact name `veyro-critical-engineer`, so a real routing attempt starting
from Sonnet would not reach this role today. **A corrected drill is
required once `BUG-030` is fixed** — see that bug file for the exact
re-run procedure (dispatch to `veyro-implementer`, observe whether it
escalates).

What this drill *does* establish: the new agent's own definition
produces behaviorally correct, in-scope engagement and correct
out-of-scope refusal when addressed directly — real, useful evidence
that the definition itself is sound (matching the independent
reviewer's own conclusion), just not evidence that the routing chain
around it works yet.

## Disclosed limitation (same class as `BUG-027`)

This session cannot independently attest the *resolved model identity*
of the two dispatches beyond the explicit `model: opus` parameter set on
each Agent-tool call — the same file-based transcript-isolation gap
`BUG-027` disclosed for MOD-000's own Gatekeeper dispatches applies
here. **Corrected (P1-1/P1-2): the original version of this file offered
the agent's own output (the `NOBYPASSRLS`/`NOSUPERUSER` distinction,
the exclusion-list citation) as a compensating control for this gap —
withdrawn, since that output is charter-derivable and does not
independently attest tier-appropriate reasoning.** The only remaining
compensating control is the explicit non-default `model: opus`
parameter set on both dispatches.

## MR evidence record

**Corrected (P1-4): agent/session ids added, previously omitted though
obtainable.**

`MR-MOD001-20260914-001`: task class = critical-slice design discussion
(SCN-104); agent = `veyro-critical-engineer`; intended tier = Opus;
dispatch parameter = `model: opus` (explicit); agent/session id =
`a606be46d5efa1ab1`; resolved model identity = not independently
attestable this session (disclosed `BUG-027`-class gap); execution mode
recorded by the agent = "would implement directly + direct others for
routine remainder"; verdict = **behaviorally sound, but does not
establish routing correctness** (see Verdict above).

`MR-MOD001-20260914-002`: task class = out-of-scope-refusal drill
(SCN-105); agent = `veyro-critical-engineer`; intended tier = Opus;
dispatch parameter = `model: opus` (explicit); agent/session id =
`aadc8f01aa8ab172f`; resolved model identity = not independently
attestable this session; execution mode = N/A (correctly refused,
routed elsewhere); verdict = **behaviorally sound, but does not
establish routing correctness**.

## Corrected drill — still to run once BUG-030 resolves

`SCN-MOD001-104`/`105` per their own detail blocks require the
dispatch target to be `veyro-implementer`, not `veyro-critical-engineer`
directly: give `veyro-implementer` the RLS-harness task (positive case)
and a routine task (negative case), and confirm its own charter now
correctly identifies the first as needing escalation to
`veyro-critical-engineer` and the second as its own routine work. Not
executed this session — blocked on `BUG-030`.
