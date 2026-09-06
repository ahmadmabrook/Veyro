---
doc: BUG-021
status: FIXED (2026-09-06)
found_date: 2026-09-06
found_by: Phase 7 fresh-context Opus veyro-performance-reviewer (PERF-01)
severity: P2 (performance)
---

# BUG-021: `evidence_integrity_check.py`'s staleness check spawned one git subprocess per file

## What is wrong

`check_staleness()` called `git log -1 --format=%cs -- <path>` once per
evidence file. Measured: 1.169s of 1.255-1.362s total runtime (93%) for
68 files (17.2ms/file). Confirmed genuinely linear, not quadratic
(15.7/15.9/16.2 ms/file at 200/500/1000 synthetic files), but `sys` time
dominance (7.66s of 16.82s at E=1000) shows the per-call subprocess
overhead is the real cost, and `git log -1 -- <path>` walks history until
it finds a touching commit, so the true complexity is O(files × history
depth) — the reviewer measured per-file cost creeping from 15.0 to
16.2ms as 3 commits were added during testing.

## Remediation applied (2026-09-06)

Replaced the per-file loop with one bulk `git log --format=COMMIT:%cs
--name-only -- <evidence-dir>` call, parsed into a `{path: latest_date}`
dict in a single pass (newest-first log, so the first time a path is seen
is its latest touching commit).

**Live-verified:** the full checker now runs in ~0.16s against the real
103-file scan (down from ~1.26-1.36s), same `PASS` result, same 12
expected-absent entries, same 0 findings.

**Independently re-verified (2026-09-06, Phase 7 re-review):** three
timed runs against the real repo measured 0.15s/0.11s/0.11s (down from
the original 1.26-1.36s), same PASS result and same 12 expected-absent
entries. The re-reviewer also A/B-tested the new bulk-git-log method
against the old per-file method across all 68 real evidence-directory
paths known to both: 0 disagreements, identical
`latest_evidence_date`. One forward-looking, zero-impact-today caveat
the re-review noted: the bulk call omits `-m`, so a path changed only in
a merge commit would be missed by both the old and new method equally —
there are 0 merge commits in this repo's history, so no current effect;
worth remembering if this project ever adopts merge commits.

## Certification impact

Does not block Phase 7 (P2 performance, now fixed). At today's MOD-000
scale (68-103 files) this saved ~1.1s per check-in; the reviewer's
projection was ~17s at ~1000 evidence files (a scale this project may
reach across many modules) before this fix — now bounded to a single git
call regardless of file count.

## Affected

`knowledge/03-Modules/MOD-000/evidence/scenario-execution/phase3/tools/
evidence_integrity_check.py`.
