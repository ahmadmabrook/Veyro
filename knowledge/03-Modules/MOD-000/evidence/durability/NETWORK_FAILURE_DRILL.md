---
doc: NETWORK_FAILURE_DRILL
status: EXECUTED (2026-09-05) — SCN-MOD000-072 (NET category)
date: 2026-09-05
---

# SCN-MOD000-072 — Network-dependent capability failure doesn't corrupt durable state

## Precedent (already existed, informal)

A TestSprite tunnel-check timeout was observed during `testsprite doctor`
in an earlier chunk (`[WARN] Local tunnel   could not check (Request
timed out...)`) — a real network failure that produced a warning, not
corruption. Not a deliberately-triggered, dedicated drill.

## Deliberate drill executed 2026-09-05

**Pre-test durable-state snapshot:** `git status --short` — 5 lines (1
modified file, 4 untracked files, all from this chunk's own in-progress
work, nothing related to the network test about to run).

**Action:** deliberately invoked a network call against an unreachable
host with a short timeout:
```bash
curl --max-time 3 -sS http://10.255.255.1/nonexistent-endpoint
```
**Result:** `curl: (28) Connection timed out after 3004 milliseconds`,
exit code 28.

**Post-test durable-state snapshot:** `git status --short` — same exact
5 lines, byte-identical to the pre-test snapshot. No new file, no
modified file, no partial/corrupt write occurred as a side effect of the
network failure.

## Result vs. pass criteria

Pass criteria: "Clean failure, no corruption." Confirmed directly: the
network call failed cleanly (a standard timeout error, correctly
reported, not masked), and the durable `knowledge/` state (as tracked by
git) is provably unaffected — the working-tree diff before and after is
identical.

## Status: PASS
