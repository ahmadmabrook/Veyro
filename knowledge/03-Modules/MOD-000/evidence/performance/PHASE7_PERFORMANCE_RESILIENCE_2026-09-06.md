---
doc: PHASE7_PERFORMANCE_RESILIENCE
status: EXECUTED (2026-09-06) — Phase 7 performance and resilience assurance
date: 2026-09-06
---

# Phase 7 — Performance and Resilience Assurance (MOD-000 control plane)

Governing commit at start: `0eacccef6ca93b9694e89fcd6ed69a553b952fea`.
Reviewer: fresh-context `veyro-performance-reviewer`, Opus tier,
technically attested via `mr_verify.py` against its own subagent
transcript (98 turns, 100% `claude-opus-5`, not self-report). Scope:
MOD-000 control-plane performance only — explicitly not product load
testing; no numeric SLOs were fabricated where the EIP prescribes none.

## Baseline table (as measured by the reviewer, before this session's fixes)

| Operation | Dataset | Duration | Result |
|---|---|---|---|
| 4-artifact baseline hash verification | 3 docx + 54-file bundle manifest | 0.07-0.10s | PASS, all 4 match |
| Same, inside fresh clone | identical | 0.09s | PASS, 4/4 identical |
| `validate_catalog.py` | 95 scenarios | 0.037-0.046s | PASS |
| `validate_catalog.py` @ 950 scenarios (synthetic 10x) | — | 0.04s | linear, no quadratic term |
| `evidence_integrity_check.py` | 103 files scanned, 68 evidence files | 1.255-1.362s | PASS (93% = per-file git log loop) |
| `evidence_integrity_check.py` @ 1000 synthetic evidence files | — | 16.82s | confirmed O(files), not worse |
| `mr_verify.py` | 203-turn / 8.8MB real transcript | 0.05s, peak RSS 53.8MB | PASS |
| `mr_verify.py` | 13,191-line / 25.8MB main-session transcript | 0.15s, peak RSS 142.3MB | BLOCKED (correct, pre-fix false positive from `<synthetic>` sentinel) |
| `git clone` full repo | 204 tracked files | 1.92s | PASS |
| Tier-1 bootstrap read | 7-8 files, ~93KB | n/a | ~23,300 tokens (12.3% of 190k budget) |
| Fresh-session restore | 36 files / 173,776B vs 686,171B whole vault | n/a | 25.3% of vault, bounded, no full-tree scan |

## Findings and disposition

| ID | Severity | Summary | Disposition |
|---|---|---|---|
| PERF-01 | P2 | `evidence_integrity_check.py`'s staleness check: one `git log` subprocess per file, 93% of runtime | FIXED, live-verified (~0.16s vs ~1.3s, ~8x on real data). `BUG-021`. |
| PERF-02 | P2 | `CURRENT_HANDOFF.md` unbounded append growth (+2,894B/revision, accelerating) | Retention note added to `CURRENT_HANDOFF.md` itself; not restructured (preserve-history convention). |
| PERF-03 | P2 | `mr_verify.py` reads whole transcript into memory (~4.9x RSS amplification) | FIXED, bundled with SEC-08/09 fix. `BUG-015`. |
| PERF-04 | Editorial | `CURRENT_STATE.md` has very long single lines, defeats partial reading | Acknowledged, reviewer's own note says "none required," not remediated this chunk. |
| PERF-05 | Editorial | `validate_catalog.py` hardcodes catalog path/expected count | Acknowledged, not remediated this chunk (MOD-000-only tool for now, low value until MOD-001 reuse). |
| RES-01 | P2 | `evidence_integrity_check.py` fails on a clean clone (same root cause as SEC-12) | FIXED, live-verified. `BUG-019`. |
| RES-02 | P2 | `validate_catalog.py` silently swallows duplicate scenario IDs | FIXED, live-verified. `BUG-020`. |
| RES-03 | Editorial | Dangling markdown link in `PROJECT_INDEX.md` (pre-migration path) | FIXED. |
| RES-04 | Editorial | `validate_catalog.py` raises raw exception on missing file | FIXED, bundled with RES-02. `BUG-020`. |

## Resilience results (as delivered by the reviewer, independently re-affirmed by this session's own separate re-tests during remediation)

- **Fresh-clone recovery: PASS.** Real `git clone` of the private repo
  succeeded (1.92s, same credentials), HEAD matched the governing commit
  exactly, all 4 baseline hashes recomputed identically inside the clone,
  zero content divergence (`diff -rq --exclude=.git`) beyond expected
  gitignored/IDE cruft. The one real finding was RES-01/SEC-12 (now
  fixed).
- **Interrupted session / handoff sufficiency: SUFFICIENT**, with 3 minor
  gaps: (1) neither `CURRENT_STATE.md` nor `CURRENT_HANDOFF.md` names the
  Phase 7 reviewer roles or pass criteria explicitly (derivable from
  `.claude/agents/` but not pointed to); (2) neither file states the
  current governing commit SHA (git is authoritative, but a fresh session
  must derive it); (3) the RES-01/SEC-12 clone-only failure was
  undocumented (now fixed and documented).
- **Git divergence: DETECTABLE**, demonstrated on a disposable temp
  branch inside a throwaway clone (never touching real `main`, never
  pushed, no history rewritten) via SHA string comparison,
  `git rev-list --left-right --count`, `git merge-base`, and independent
  confirmation against `git ls-remote`.
- **Missing capability → governed BLOCKED, not silent substitution:**
  covered structurally by `BUG-014`'s new `validate_capabilities.py`
  (`BLOCKED: CAPABILITY_UNREGISTERED`) and by the pre-existing
  `CAPABILITY_POLICY.md` fail-closed rule, now with a real technical
  backstop rather than review-time-only enforcement.
- **Corrupted/missing evidence:** covered by `evidence_integrity_check.py`
  (mutation-tested this chunk: an injected broken reference and a deleted
  detail block were both caught, both by the security reviewer and
  independently re-confirmed during this session's own testing).

## Overall reviewer verdict (as delivered)

**APPROVED — 0 P0, 0 P1.** 5 P2, 4 Editorial (all listed above).

## This session's remediation and live re-verification (2026-09-06)

PERF-01, PERF-03, RES-01, RES-02, RES-04 are all fixed and live-verified
(see corresponding `BUG-0NN-*.md` files, which include exact commands and
before/after timings for the performance fixes). PERF-02 was addressed
with a documentation-only retention note (see `CURRENT_HANDOFF.md`'s
frontmatter-adjacent note) rather than a restructure, consistent with
this project's "preserve history, append corrections" convention.
PERF-04/PERF-05/RES-03 are Editorial; RES-03 was fixed (one-line link
correction), PERF-04/05 acknowledged and left as documented, non-blocking
observations per the reviewer's own assessment.

**No P0/P1 was found on the performance/resilience side — this half of
Phase 7 independently reached APPROVED before any remediation was even
needed.** The remediation above closes real P2/Editorial gaps but does
not change this verdict.
