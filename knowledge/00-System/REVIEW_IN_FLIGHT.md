---
doc: REVIEW_IN_FLIGHT
status: LIVE — minimal durable claim mechanism, authored 2026-10-03 per R12-5 (round-12 independent review, `knowledge/03-Modules/MOD-001/evidence/security/GOV01-R02-SLICE7-DOMAIN-SCAFFOLDS-FINANCIAL-INVARIANT-SECURITY-REVIEW-ROUND12-2026-10-03.md` §4.5), implementing the process fix R11b-2/`SLICE-7-ROUND11-COLLISION-CHECKPOINT-2026-10-03.md` recommended after two orchestrating sessions independently dispatched the same round-11 review without knowing about each other.
current_claim: CLEAR — M1-C-05 exact-snapshot independent review round 1 BLOCKED recorded 2026-10-09T22:04:34.350156+00:00; report knowledge/03-Modules/MOD-001/evidence/code-review/M1-C-05-TRUSTED-DEPENDENCY-CI-REVIEW-2026-10-10.md; sha256 d3597d1f1e92344a36be1634f3690cb05126f9b51faa617a71a4ca76e87a1389; no remote effect, no C13 integrated verdict.
prior_claim_gate2_r2_parse_interrupted: IN_FLIGHT — MOD-001 GOV-01-R04 gate-2 combined independent code review round 2 for SCN-MOD001-006, SCN-MOD001-007, SCN-MOD001-095, SCN-MOD001-096, runner operation 50621021-95a3-46ae-bc94-ddd0bcc3a3c1, claimed 2026-10-05T22:56:25.145758+00:00; expected report knowledge/03-Modules/MOD-001/evidence/code-review/GATE2-MODULE-DEPS-CODE-REVIEW-ROUND2-2026-10-06.md. Do not dispatch a second reviewer; clear only after verified result or explicit interruption reconciliation. Reconciled as interrupted pre-agent parse, not a review result.
prior_claim_scn070_round4: IN_FLIGHT — SCN-MOD001-070 exceptional independent security/scenario review round 4, watchdog 66643874-e295-4d53-a846-ee79cb6c3a44, dispatched 2026-10-04T13:44:08.312137+00:00; fresh Opus via ACPX. Fulfilled by the dispatching session in-process and cleared above. Protocol note: the dispatching session verified at start that this claim's timestamp matched its own launch second (REVIEW_IN_FLIGHT.md mtime 2026-10-04T16:44:08 local = 13:44:08Z, identical to the acpx wrapper's own start time), so the claim was its own correctly-pre-written claim, not a stale one from the earlier interrupted round-4 launch — it was therefore honored, not cleared-and-replaced, and no second claim was written. The earlier interrupted round-4 launch produced no report and no verdict and is not counted.
prior_claim_scn070: IN_FLIGHT — SCN-MOD001-070 independent security/scenario evidence review round 1, claimed by watchdog 66643874-e295-4d53-a846-ee79cb6c3a44, dispatched 2026-10-04T11:51:44.275553+00:00. Expected subagent: fresh veyro-security-reviewer/Opus via ACPX. Clear on result recorded, not merely on process exit.
prior_claim: IN_FLIGHT — BUG-048 independent code review round 1 recovery, claimed by watchdog 66643874-e295-4d53-a846-ee79cb6c3a44, dispatched 2026-10-04T10:20:14.933383+00:00. Expected subagent: fresh Opus via ACPX. Clear only after result recorded. (Fulfilled by the dispatching session in-process; cleared above on result recorded, not merely on subagent exit.)
prior_claim_2: CLEAR — BUG-048 round-1 attempt interrupted without verdict, reconciled 2026-10-04T10:19:45.195270+00:00; no live Veyro ACPX/Claude reviewer or pytest process, transcript 3ae687f2-4ec8-4329-a048-cec0a3a7dd87 stopped at 2026-10-04T10:13:48Z during a test call, and no report exists. No completed review counted. DOM-002 round 5 remains interrupted/non-resumable.

Prior claim (round 1, watchdog 66643874-e295-4d53-a846-ee79cb6c3a44, dispatched 2026-10-04T03:03:51.309736+00:00) fulfilled by this same dispatching session, not superseded by crash recovery — the dispatch ran to completion in-process and its result is recorded above.

Round-14 retry claim cleared 2026-10-03T21:19:34+00:00: completed report exists and CURRENT_STATE.md records independently attested verdict; no live ACPX process at watchdog inspection. No new verdict inferred.

Prior claim cleared 2026-10-03T23:52:00+03:00, crash-recovery check performed per this file's own protocol: no live process found for session `ce6d2387-78e1-44fd-8f4d-58d7b04ab090` (`ps aux` shows no matching PID), its subagent transcript `ce6d2387-78e1-44fd-8f4d-58d7b04ab090/subagents/agent-a0c4cdd71de27097d.jsonl` (meta confirms `agentType: veyro-security-reviewer`, description "MOD-001 BUG-050 round-14 independent security review") stopped at 279 lines with no further activity, and no completed round-14 report exists under `MOD-001/evidence/security/` (only the round-13 report and a raw partial capture, `BUG050-ROUND14-RETRY-ACPX-RAW-2026-10-03.txt`, neither a finished governance report). Confirmed genuinely stale (dispatching process crashed/interrupted before the review ran), not merely old-looking. No verdict inferred from the interrupted attempt's partial output.
---

# Review-in-flight claim

**2026-10-04 control note:** The SCN-MOD001-009 fresh independent review was dispatched while this claim still read CLEAR; its report noted that this protocol was missed. No duplicate review or active reviewer was observed. The result is preserved and independently model-attested, but this is a control-plane process defect, not a precedent to skip the pre-dispatch claim. Future fresh independent reviews must write IN_FLIGHT before launch.

## Why this file exists

Round 11 of MOD-001's Slice-7/BUG-050 remediation had a real collision:
two orchestrating sessions, neither aware of the other, each dispatched
their own fresh round-11 `veyro-security-reviewer` over an overlapping
window. Both were real, both independently attested, and reconciling
them after the fact cost a full remediation pass. This file is the
minimal fix: a single durable claim an orchestrating session checks
before dispatching a fresh independent review round for **any** bug or
module, and clears when the round's result is recorded.

This is a governance/record artifact, not a lock service — it has no
enforcement mechanism of its own. It works only if every orchestrating
session actually reads and honors it, which is why `SESSION_BOOTSTRAP.md`
§4 requires it.

## Protocol

1. **Before dispatching a fresh independent review round** (security,
   scenario-catalog, code, or gatekeeper — any role this project treats
   as independent/fresh-context per `DEVELOPMENT_CONSTITUTION.md`'s model
   routing), read this file's `current_claim` field.
   - If `CLEAR`: proceed, and immediately write a new claim (step 2)
     *before* the dispatch call, not after — the race this file exists
     to close is the gap between "decided to dispatch" and "recorded
     having dispatched."
   - If already `IN_FLIGHT`: do **not** dispatch a second review for the
     same bug/module/round class. Go to "Checking a claim," below.

2. **Writing a claim.** Replace `current_claim` with:
   ```
   current_claim: IN_FLIGHT — <bug/module id> round <N>, claimed by
   orchestrating session <session id or description>, dispatched
   <UTC timestamp>. Expected subagent: <agent type>. Clear on result
   recorded, not merely on subagent completion.
   ```
   Commit this edit to the live file before the dispatch call returns
   control, not as an afterthought after the review's report already
   exists — a claim written late defends against nothing.

3. **Clearing a claim.** Once the review's result has been read and
   recorded in the relevant durable files (not merely once the subagent
   process exits), replace `current_claim` with:
   ```
   current_claim: CLEAR — round <N> result recorded <UTC timestamp>,
   see <path to the round's report>.
   ```
   Clearing is tied to *recording the result*, not to the subagent
   finishing, because a subagent can finish and its report can sit
   unread while a second session checks this file — the claim should
   still read `IN_FLIGHT` through that gap.

## Crash recovery — a stale-looking claim is not proof either way

A session can crash, be interrupted by a provider limit, or simply end
its turn between writing an `IN_FLIGHT` claim and clearing it. **Do not
assume a claim equals an active process, and do not assume a claim is
abandoned just because it looks old.** Before acting on an `IN_FLIGHT`
claim one way or the other:

- Check for a live subagent transcript matching the claim's recorded
  identity (search `~/.claude/projects/<project>/` for a `subagents/
  agent-*.jsonl` started at or after the claimed dispatch time, or a
  running process via `ps`). A matching live transcript still being
  written means the review is genuinely in flight — wait or check back,
  do not dispatch a second one.
- If no matching live transcript or process exists, look for whether the
  review's report was actually written (the "next legally allowed
  action" the claim names should point at a report path once done). A
  completed report with an uncleared claim means the clearing step was
  simply missed — clear it now, with a dated note, and record the
  result as normal.
- If neither a live process nor a completed report exists, the claim is
  genuinely stale (the dispatching session crashed or was interrupted
  before the review ran). Clear it with a dated note explaining what was
  found, and only then dispatch the review that was originally intended.
- **Never clear a claim you have not actually checked.** "It looks old"
  or "it's probably fine" is exactly the silent assumption this file
  exists to prevent — the cost of checking is a few minutes; the cost of
  a second concurrent dispatch is a full reconciliation pass, as round
  11 demonstrated.

## Scope

This file is a single global claim slot, not a per-module queue. Under
this project's own WIP=1 constraint (one active module at a time), a
single slot is sufficient — if that constraint changes, this file's
single-claim design would need to change with it, which is itself a
reason to keep this file minimal rather than building out a queue this
project does not yet need.

Round-16 recovery 2026-10-03T23:33:57.076180+00:00: reviewer transcript agent-aba25ab718d28c1ae.jsonl stopped at 2026-10-03T23:23:57Z after a rejected test-tool call; PID 28962 is absent, no ACPX process or completed round-16 report exists. No verdict inferred. Original claim cleared for a fresh independent retry.

Round-16 retry recovery 2026-10-04T00:05:36.275087+00:00: prior retry parent/subagent transcript 76f94e23-227b-4247-8b7e-46cc5c9e350f / agent-aaa1fcc5be6cc6f94 stopped at 2026-10-03T23:54:50Z on a tool rejection contemporaneous with the 1200-second cron timeout. No exit-code file, no live Veyro ACPX process, and no completed round-16 report exist. No verdict inferred. The prior claim was checked and superseded by a bounded continuation claim before dispatch. Existing work preserved.
