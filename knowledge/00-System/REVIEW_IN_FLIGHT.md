---
doc: REVIEW_IN_FLIGHT
status: LIVE — minimal durable claim mechanism, authored 2026-10-03 per R12-5 (round-12 independent review, `knowledge/03-Modules/MOD-001/evidence/security/GOV01-R02-SLICE7-DOMAIN-SCAFFOLDS-FINANCIAL-INVARIANT-SECURITY-REVIEW-ROUND12-2026-10-03.md` §4.5), implementing the process fix R11b-2/`SLICE-7-ROUND11-COLLISION-CHECKPOINT-2026-10-03.md` recommended after two orchestrating sessions independently dispatched the same round-11 review without knowing about each other.
current_claim: CLEAR — MOD-001 DOM-002 code-review round 2 result recorded 2026-10-04T04:19:19.795989+00:00, see knowledge/03-Modules/MOD-001/evidence/code-review/DOM002-CONCURRENCY-PATTERN-CODE-REVIEW-ROUND2-2026-10-04.md; independent mr_verify.py PASS 102/102 claude-opus-5; verdict PASS P0=0/P1=0/P2=1/P3=4; findings R2-1..R2-5 remain for remediation.

Prior claim (round 1, watchdog 66643874-e295-4d53-a846-ee79cb6c3a44, dispatched 2026-10-04T03:03:51.309736+00:00) fulfilled by this same dispatching session, not superseded by crash recovery — the dispatch ran to completion in-process and its result is recorded above.

Round-14 retry claim cleared 2026-10-03T21:19:34+00:00: completed report exists and CURRENT_STATE.md records independently attested verdict; no live ACPX process at watchdog inspection. No new verdict inferred.

Prior claim cleared 2026-10-03T23:52:00+03:00, crash-recovery check performed per this file's own protocol: no live process found for session `ce6d2387-78e1-44fd-8f4d-58d7b04ab090` (`ps aux` shows no matching PID), its subagent transcript `ce6d2387-78e1-44fd-8f4d-58d7b04ab090/subagents/agent-a0c4cdd71de27097d.jsonl` (meta confirms `agentType: veyro-security-reviewer`, description "MOD-001 BUG-050 round-14 independent security review") stopped at 279 lines with no further activity, and no completed round-14 report exists under `MOD-001/evidence/security/` (only the round-13 report and a raw partial capture, `BUG050-ROUND14-RETRY-ACPX-RAW-2026-10-03.txt`, neither a finished governance report). Confirmed genuinely stale (dispatching process crashed/interrupted before the review ran), not merely old-looking. No verdict inferred from the interrupted attempt's partial output.
---

# Review-in-flight claim

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
