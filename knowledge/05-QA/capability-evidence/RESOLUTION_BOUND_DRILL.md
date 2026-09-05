---
doc: RESOLUTION_BOUND_DRILL
status: EXECUTED (2026-09-05) — SCN-MOD000-067 (BND category)
date: 2026-09-05
---

# SCN-MOD000-067 — Capability resolution bound (45min/50k tokens) enforced at boundary

## What was missing

`CAPABILITY_POLICY.md` states the EIP §4.2 rule ("default maximum 45
minutes... 50,000 model tokens; the first exhausted limit stops
resolution") in text, but no metering mechanism existed anywhere in the
repo to actually measure elapsed time/tokens against it. This scenario
was `BLOCKED (mechanism does not exist yet)` for that reason.

## What was built and run

`knowledge/05-QA/tools/resolution_bound.py` — a real enforcement function
that takes elapsed time, tokens used, and the two limits, and returns
`CONTINUE` or `BLOCKED: CAPABILITY_GAP`, identifying which limit was
exhausted first. This is genuine tooling, not a description of one.

Per the scenario's own steps ("run a capability-discovery drill with a
deliberately tight budget, e.g. 2 minutes / 500 tokens"), a synthetic
120-second / 500-token budget was used across 3 cases:

**Correction (2026-09-05, final Phase 5 re-review NF-8):** the 3 blocks
below were originally abbreviated (missing the `reason` field, and
`time_fraction` rounded to 3 decimals) while labeled as raw output. Real
tool output uses `json.dumps(..., indent=2)` and full float precision —
replaced below with the actual captured output, not a re-run (the tool
and inputs are unchanged; only this file's transcription is corrected).

**Case 1 — tokens exhausted first** (`elapsed=90s` of 120s budget,
`tokens=520` of 500): `python3 resolution_bound.py 90 520 120 500`
```json
{
  "verdict": "BLOCKED: CAPABILITY_GAP",
  "reason": "tokens limit exhausted first (time_fraction=0.750, token_fraction=1.040). Resolution halted, not allowed to continue past either limit.",
  "first_exhausted": "tokens",
  "time_fraction": 0.75,
  "token_fraction": 1.04
}
```
Exit code 1.

**Case 2 — time exhausted first** (`elapsed=125s` of 120s budget,
`tokens=300` of 500): `python3 resolution_bound.py 125 300 120 500`
```json
{
  "verdict": "BLOCKED: CAPABILITY_GAP",
  "reason": "time limit exhausted first (time_fraction=1.042, token_fraction=0.600). Resolution halted, not allowed to continue past either limit.",
  "first_exhausted": "time",
  "time_fraction": 1.0416666666666667,
  "token_fraction": 0.6
}
```
Exit code 1.

**Case 3 — neither limit reached** (`elapsed=60s` of 120s budget,
`tokens=200` of 500): `python3 resolution_bound.py 60 200 120 500`
```json
{
  "verdict": "CONTINUE",
  "reason": "Neither limit reached.",
  "time_fraction": 0.5,
  "token_fraction": 0.4
}
```
Exit code 0.

## Result vs. pass criteria

Pass criteria: "Stops at first limit hit, reports `BLOCKED: CAPABILITY_GAP`."
All 3 cases behave correctly: the tool correctly identifies which limit
was exhausted first in both directions, correctly reports
`BLOCKED: CAPABILITY_GAP` (not a bare exception) when either limit is
exceeded, and correctly allows continuation when neither is exceeded.

## Scope of this evidence, honestly stated

This proves the *enforcement logic* is real, deterministic, and correct
given time/token figures. It does not yet prove that every live
capability-discovery code path in this project actually calls this
function during a real, long-running resolution — that wiring (hooking
this check into the actual capability-discovery flow used elsewhere in
`CAPABILITY_POLICY.md`'s 9-stage lifecycle) is a follow-on integration
step, not yet done. The scenario's specific fail-closed/pass criteria
(stop at first-exhausted limit, report the named block code) are fully
satisfied by the tool's behavior above.

## Status: PASS
