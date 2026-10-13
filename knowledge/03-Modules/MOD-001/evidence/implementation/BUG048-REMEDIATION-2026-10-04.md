---
doc: BUG048-REMEDIATION
module: MOD-001
bug: BUG-048
date: 2026-10-04
session: retained orchestrating session (Opus 5 1M context, `claude-opus-5[1m]` per this
  session's own environment banner — no `mr_verify.py` transcript attestation was produced
  for this session, so treat the identity as self-reported, not independently attested)
status: FIXED LOCALLY — NOT independently reviewed, NOT self-approved, NOT closed
addendum: §7 (appended 2026-10-04) corrects this record's §1.4/§3/§4 per round-1 review
  finding R2 — the post-restore assertion as originally written was ANY/OR, not ALL. §1-§6
  are preserved verbatim; read §7 before relying on any §1.4/§3/§4 statement about the
  assertion's strength. See `BUG048-R1-R2-REMEDIATION-2026-10-04.md`.
---

# BUG-048 remediation — Slice-5 `runtime_owns_table` owner-restore re-grants runtime DML

Scope of this session: BUG-048 only. No edit to `R04`, `ADR-010` A2, `SCN-067`,
`DOM-002`/round 5, `REVIEW_IN_FLIGHT.md`, or any scenario promotion. No commit, no push.
No independent review dispatched, performed, self-attested, or claimed.

## 1. Change made (one file)

`backend/tests/integration/test_tenant_isolation_harness.py` — the only file changed.

1. New module constants, mirroring the already-reviewed sibling file
   `test_architecture_gate_rls.py`'s own `_RUNTIME_GRANT` idiom rather than inventing a
   second mechanism:
   - `_RUNTIME_GRANT` — `GRANT SELECT, INSERT, UPDATE, DELETE ON harness.access_grant TO
     veyro_runtime`, the same statement `tests/harness/tenant_isolation.py`'s
     `create_tenant_table` provisions the fixture with.
   - `_RUNTIME_DML` — the privilege list the post-restore assertion checks.
2. `BREAKAGES`' third tuple element changed from a single `str` to `list[str]`, matching
   `test_architecture_gate_rls.py`'s own `BREAKAGES` shape (its restore element has always
   been a list). All five entries wrapped; only the `runtime_owns_table` entry gains a
   second statement, `_RUNTIME_GRANT`, after the `OWNER TO veyro_schema_owner` restore.
3. The `finally` block loops over the restore statements instead of executing one.
4. **Post-restore grant assertion added**, running for every breakage case, not just the
   owner one:

       assert one_row(admin.execute(
           "SELECT has_table_privilege(%s, 'harness.access_grant', %s)",
           (RUNTIME_ROLE, _RUNTIME_DML),
       ))[0] is True, f"runtime role lost its DML grant after restoring {name}"

   This is the post-condition BUG-048's own closure criteria asked for, and the same check
   `test_architecture_gate_rls.py`'s `_broken` helper already performs.

Not done, deliberately: no `has_schema_privilege` assertion (the sibling R04 helper has
one, but no Slice-5 breakage touches schema ownership, so adding it here would be
unexercised scope); no change to `tests/harness/tenant_isolation.py`; no change to any
other test file.

## 2. ACL restored byte-identically (measured, not assumed)

BUG-048's own probe recorded the provisioned ACL as
`veyro_runtime=arwd/veyro_schema_owner` before the breakage and
`{veyro_schema_owner=arwdDxt/veyro_schema_owner}` after the "restore".

Measured this session with a throwaway probe test appended to a `/tmp` copy, reporting
`pg_class.relacl` after the Slice-5 file ran in the same pytest session:

| state | `has_table_privilege(veyro_runtime, …, SELECT/INSERT)` | `relacl` runtime entry |
|---|---|---|
| pre-fix (re-grant removed) | `(False, False)` | **absent** |
| post-fix (as committed) | `(True, True)` | `veyro_runtime=arwd/veyro_schema_owner` |

The grantor matches the original because PostgreSQL attributes a superuser-issued `GRANT`
to the object's owner, so the restored ACL entry is byte-identical to the one
`create_tenant_table` provisions — not merely privilege-equivalent. The `veyro_bypass_probe_*`
entry also present in both readings is the pre-existing `elevated_login` fixture's role,
unrelated to this bug.

## 3. Non-vacuity drill (the fix and the assertion are both load-bearing)

Run in a throwaway full-structure copy at `/tmp/veyro-bug048-drill/` (`backend/tests`,
`backend/app`, `backend/migrations`, `backend/pyproject.toml`, `tools/`, venv symlinked),
never in the repository. Confirmed afterwards via `git status --porcelain` that no repo
file was touched by the drill and no drill artifact leaked into the tree; the copy was then
deleted.

- **Drill 1 — re-grant removed, new assertion kept:** `1 failed, 11 passed`, failing
  exactly at the new assertion with `AssertionError: runtime role lost its DML grant after
  restoring runtime_owns_table` / `assert False is True`. The pre-existing
  `read_posture(...).violations == []` post-condition passed in the same run, confirming
  BUG-048's own finding that posture is blind to a dropped ACL entry.
- **Drill 2 — re-grant and assertion both removed (pre-fix shape):** the Slice-5 file alone
  passes `12 passed`, reproducing the masking BUG-048 describes.

## 4. Honest correction to BUG-048's stated order-dependence

BUG-048's Impact section says "Running that file before another runtime-DML test
(reordering, a random-order run, or a new test after it) reproduces the same." **Measured
this session, that is no longer true of the current suite, and the full-suite order
permutations below therefore do not demonstrate the fix.**

With the complete pre-fix shape in the drill copy, the whole backend suite with the
Slice-5 file placed **first** passed `204 passed`. Direct ACL measurement explains why:
the runtime grant is genuinely gone after the Slice-5 file (§2, pre-fix row), but
`test_architecture_gate_rls.py` — the next file in that order, and the only other file
doing runtime DML on `harness.access_grant` — carries `_RUNTIME_GRANT` in one of its own
early restore lists, so it incidentally repairs the ACL before any of its own
`has_table_privilege` post-conditions run. Probe after that file: `(True, True)`,
`veyro_runtime=arwd/veyro_schema_owner`.

So the defect is masked by **two** independent coincidences, not the one BUG-048 names:
the Slice-5 file sorting last in default collection order, **and** the R04 file's own
unrelated re-grant repairing the ACL for it. The 7 "permission denied for table
access_grant" failures BUG-048 reports came from an intermediate state of the R04 file
during its own development, before its restores were fixed — consistent with that bug
file's own "The R04 test's own restore is fixed" sentence.

**Consequence for the evidence:** the order runs in §5 are a no-regression check, not a
reproduction. The load-bearing regression lock for BUG-048 is the §1.4 post-restore
assertion, proven load-bearing by Drill 1 — not the order permutations.

## 5. Executed results (all this session, approved Colima binding / CAP-008)

Interpreter: `backend/.venv/bin/python`, Python 3.14.5. Every command run from `backend/`.

| check | command | result |
|---|---|---|
| Slice-5 file focused | `pytest -q tests/integration/test_tenant_isolation_harness.py` | **12 passed** |
| full suite, default order | `pytest -q` | **204 passed** |
| full suite, Slice-5 **first** | `pytest -q <slice5> <13 other files>` | **204 passed** |
| full suite, Slice-5 **last** | `pytest -q <13 other files> <slice5>` | **204 passed** |
| full suite, fully reversed file order | `pytest -q $(ls tests/*/test_*.py \| sort -r)` | **204 passed** |
| lint | `ruff check .` | **All checks passed** |
| types | `mypy tests/` (strict) | **Success, 28 source files** |

204 is the same total as the established pre-session baseline — the change adds assertions,
not test functions. Both of BUG-048's closure criteria asking for a non-default order are
satisfied (Slice-5 first *and* last, each in a single pytest session), with the §4 caveat
that neither order reproduces the pre-fix defect in today's suite.

### Governance checks

| check | result |
|---|---|
| `knowledge/00-System/verify_baselines.py` | **PASS, 4/4** governing baselines unchanged |
| `knowledge/00-System/validate_capabilities.py` | **PASS**, 8 capabilities, CAP-008 still APPROVED |
| `tools/validate_capability_manifest.py --manifest …/MOD-001/evidence/module-capabilities.yaml` | **PASS**, 10 capability/Rule IDs |
| `knowledge/05-QA/tools/capability_drift_check.py` | **PASS**, 8 capabilities, no drift |
| `knowledge/05-QA/tools/run_regression.py` | **FAIL (3/4)** — `evidence_integrity_check.py` only, on the pre-existing `CURRENT_HANDOFF.md` commit-staleness artifact of this project's no-commit-mid-round convention. Not caused by this change; already recorded as a standing artifact in `CURRENT_STATE.md`. Recorded honestly, not worked around. Run record: `knowledge/05-QA/tools/regression-runs/RUN_20261004T100601Z.txt` |

### Docker state

`docker ps -a` and `docker volume ls` identical before and after every run this session:
one pre-existing, out-of-scope container (`vigilant_matsumoto`, the unrelated
`tradingview-mcp` workload) and two pre-existing volumes
(`712bec68008e…`, `tradingview-mcp-session`). No harness container or volume residue.

## 6. What is NOT established

- **No independent review.** This fix was written by this session. Per DC-06 and this
  project's own convention, BUG-048 is **fixed locally, not closed**, and is still counted
  as an open P2. A fresh-context independent review (`veyro-code-reviewer`, Opus) of this
  one-file change is the explicit next action. None was dispatched; `REVIEW_IN_FLIGHT.md`
  was not read-claimed or written by this session.
- **No model attestation for this session.** The model identity in this file's front matter
  is self-reported from the session environment banner. No `mr_verify.py` run attests it.
- **Nothing else closed or promoted.** `SCN-067`, `R04`/`ADR-010` A2, DOM-002 round 5, and
  MOD-001 certification are all untouched and remain in whatever state they were in.
- **§4's correction is a measurement, not a re-review** of BUG-048's original filing. The
  original P2 severity and safe-failure-direction assessment are unchanged by it.

## Orchestrator model attestation (2026-10-04)

`mr_verify.py` on the matching one-shot ACPX implementation transcript `~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/a93143a2-b2cf-4916-9137-a67e08adf54f.jsonl`, expected tier `opus`, agent label `veyro-critical-engineer`: **PASS, 102/102 turns, resolved model `claude-opus-5`**. This attests the implementation route, not independent review or BUG-048 closure.

## 7. Addendum (2026-10-04) — §1.4/§3/§4 overstated the assertion's strength (review finding R2)

**Everything above this heading is preserved exactly as originally written, including the
assertion quoted in §1.4 and the wording §3/§4 use about it. This addendum does not rewrite
it — it records which of those claims held, which did not, and what superseded them, so the
record of what was claimed on 2026-10-04 and on what basis stays readable.** Appended by the
bounded R1/R2 work unit recorded in `BUG048-R1-R2-REMEDIATION-2026-10-04.md`
(`mr_verify.py` on that session's own transcript: **PASS, 58 turns, `claude-opus-5`**). That
session wrote no test or production code; it verified the already-applied R1 fix by
execution and reconciled this record.

### What was overstated

The round-1 independent review
(`knowledge/03-Modules/MOD-001/evidence/code-review/BUG048-SLICE5-ACL-RESTORE-CODE-REVIEW-ROUND1-2026-10-04.md`,
verdict **PASS-with-findings, P0=0/P1=0/P2=2/P3=3**) found as its finding **R1 (P2)** that
the assertion §1.4 quotes —

    "SELECT has_table_privilege(%s, 'harness.access_grant', %s)", (RUNTIME_ROLE, _RUNTIME_DML)

— passes a **comma-separated** privilege list, which PostgreSQL evaluates as **ANY/OR, not
ALL**. It returns true when the role holds *at least one* of `SELECT`/`INSERT`/`UPDATE`/
`DELETE`. Its finding **R2 (P2)** was that this record describes that check as though it
verified the full DML set. Specifically, as against the text above:

| claim in this record | status |
|---|---|
| §1.4 "**Post-restore grant assertion added**, running for every breakage case" | **Accurate.** The assertion did exist and did run for all five cases. |
| §1.4's implied strength — that it is the full-DML post-condition BUG-048's closure criteria asked for | **Overstated.** It proved "holds at least one of the four", not "holds all four". |
| §3 Drill 1, "the fix and the assertion are both load-bearing", re-grant removed → assertion fails | **Accurate, and independently confirmed.** A *total* loss of the grant was genuinely caught; the review reproduced it at SQL level and the R1/R2 session re-killed it at pytest level (its mutant D). |
| §4 "the post-restore assertion is the real regression lock" | **Accurate as to *which* mechanism is the lock** (not the order permutations) — the §4 self-correction stands. **Overstated as to how much that lock covered**: it was a partial lock. |
| §2 "byte-identical to the one `create_tenant_table` provisions" | **Accurate, no correction needed.** Independently re-measured by the review (`Q1-FIX-byte-identical-to-baseline True`). |

**Consequence, stated plainly.** From this record's own date until the R1 fix, closure
criterion 2 ("a post-restore grant assertion exists") was satisfied **in letter only**. A
partial re-grant — a later narrowing edit to `_RUNTIME_GRANT`, a copied breakage case with a
typo'd privilege list — would have passed the assertion silently, re-opening BUG-048 behind
its own green guard. The posture post-condition could not have caught it either, being
ACL-blind by BUG-048's founding finding.

### What superseded it

The assertion is now `bool_and(has_table_privilege(...))` over an unnested
`SELECT`/`INSERT`/`UPDATE`/`DELETE` array
(`backend/tests/integration/test_tenant_isolation_harness.py:170-176`), evaluating each
privilege individually, with the expectation list `_RUNTIME_DML` deliberately **not** derived
from `_RUNTIME_GRANT` so a narrowing edit is caught rather than followed. The `finally`
restore loop is unchanged — the repair still always runs.

Proven at the pytest level against the real fixture, closing the one substitution the
round-1 review stated as a limit (it could only mutate SQL inside a probe, not the test file
itself). Full commands and raw results in `BUG048-R1-R2-REMEDIATION-2026-10-04.md` §2:

| mutant | assertion | result |
|---|---|---|
| `GRANT SELECT` only (partial re-grant) | **pre-R1** comma-list | `12 passed` — **SURVIVED** |
| `GRANT SELECT` only (partial re-grant) | **current** `bool_and` | `1 failed, 11 passed` — **KILLED** |
| `GRANT SELECT, INSERT, UPDATE` (DELETE dropped) | current `bool_and` | `1 failed, 11 passed` — **KILLED** |
| re-grant removed entirely (original BUG-048 shape) | current `bool_and` | `1 failed, 11 passed` — **KILLED** |

The first two rows are R2's correction in one line: the same defect, invisible to what §1.4
describes, fatal to what replaced it.

Re-verified unmutated in the repository by that session: focused **12 passed**; full suite
**204 passed** in default order, **204 passed** Slice-5-first, **204 passed** Slice-5-last;
`ruff check .` clean; `mypy tests/` strict clean, 28 files. §5's *fully reversed* order
permutation and the `run_regression.py` governance run were **not** re-run and remain
accepted from §5 as originally recorded.

### What this addendum does not change

§4's correction to BUG-048's stated order-dependence stands unaltered, and the order
permutations in §5 remain a **no-regression check, not a reproduction** — the mutants above,
not those orders, are what proves the lock. §6's caveats all still apply: the model identity
in this file's front matter is still self-reported for the original session, and **BUG-048
remains OPEN**. Closure criterion 4 is still unmet, now for a further reason — the
strengthened assertion has had **no** independent review, and the session that strengthened
it was acting on the review's findings, not reviewing them. A fresh-context round 2 is the
next action; none was dispatched, self-attested or claimed, `REVIEW_IN_FLIGHT.md` was not
touched, and nothing was committed or pushed. The review's three **P3** findings (R3
assertion placement, R4 no behavioural DML post-condition, R5 PUBLIC-grant path plus the
adjacent same-idiom exposure in the sibling `test_architecture_gate_rls.py`) are
**non-blocking and remain open residuals**.
