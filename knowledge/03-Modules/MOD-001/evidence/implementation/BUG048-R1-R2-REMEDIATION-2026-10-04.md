---
doc: BUG048-R1-R2-REMEDIATION
module: MOD-001
bug: BUG-048
date: 2026-10-04
session: bounded implementation/remediation work unit, scoped to the round-1 independent
  review's two P2 findings (R1, R2) only
session_model_attestation: `knowledge/05-QA/tools/mr_verify.py` on this session's own
  transcript `~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/50b16e73-5e11-430e-a47b-bd038aa0f89a.jsonl`,
  expected tier `opus`, agent label `veyro-critical-engineer` — **PASS, 58 turns, 100%
  consistent, resolved model `claude-opus-5`**. Attests the implementation route only; it
  attests nothing about independent review or BUG-048 closure.
status: R1 CODE FIX VERIFIED BY EXECUTION + R2 RECORDS RECONCILED — BUG-048 still OPEN,
  NOT independently reviewed for the strengthened assertion, NOT self-approved, NOT closed
---

# BUG-048 R1/R2 remediation — the post-restore assertion checks ALL four DML privileges

Charge boundary for this work unit: the two **P2** findings of
`knowledge/03-Modules/MOD-001/evidence/code-review/BUG048-SLICE5-ACL-RESTORE-CODE-REVIEW-ROUND1-2026-10-04.md`
— **R1** (the `has_table_privilege` comma-list check is ANY/OR, not ALL, so a partial-grant
mutant survives it) and **R2** (the two durable evidence records overstate the assertion's
strength). Nothing else. No independent review dispatched, performed, self-attested or
claimed; BUG-048 not closed; no scenario promoted; `REVIEW_IN_FLIGHT.md`, `CURRENT_STATE.md`,
`CURRENT_HANDOFF.md`, `BUG_REGISTRY.md`, DOM-002, R04/ADR-010 A2 and every other in-flight
work unit untouched. Nothing committed, nothing pushed, no `reset`/`stash`/`discard`, and
all 304 pre-existing working-tree entries preserved.

## 0. Provenance — what pre-existed this session, and what this session did

This matters for attribution and must not be blurred.

**Pre-existing in the uncommitted working tree when this session started:**

1. The R1 **code change itself**, already applied to
   `backend/tests/integration/test_tenant_isolation_harness.py` (the `bool_and`/`unnest`
   assertion at `:170-176`, the `_RUNTIME_DML: list[str]` constant at `:46`, and the
   explaining comment at `:42-45` / `:166-169`).
2. The R1/R2 **addendum in the bug record**
   (`evidence/bugs/BUG-048-harness-owner-restore-drops-runtime-grant.md`, section
   "Round-1 independent review (2026-10-04) and the R1 strengthening"), which already
   stated the fix and already **referenced this file by name**.

**What was missing, and is the actual gap this session closed:** this file did not exist.
The bug record's reference to it was **dangling**, so every execution claim that addendum
makes ("the SELECT-only partial-grant mutant survives the old ANY/OR assertion … and is
killed by the new one, a one-privilege narrowing (DELETE dropped) is also killed, and the
original no-grant mutant remains killed") had **no evidence on disk** backing it. The prior
bounded session appears to have applied the code edit and the bug-record addendum and then
stopped before writing the record or amending the second durable record.

**What this session did:** (a) read the committed change rather than assuming it, (b)
independently executed the full proof set below — including the mutant that substantiates
R1's own premise at the pytest level, not just at the SQL-probe level the round-1 review
used — so those claims are now evidence-backed rather than asserted, (c) wrote this record,
and (d) reconciled `BUG048-REMEDIATION-2026-10-04.md`, which still carried the overstated
text R2 named and which the prior session never touched (R2's second half). **This session
wrote no new line of test or production code**; it verified, proved, and recorded.

This session is **not** an independent review of the strengthened assertion, and does not
present itself as one. Acting on a review's findings is not reviewing them.

## 1. R1 — the fix under verification (unchanged by this session)

`backend/tests/integration/test_tenant_isolation_harness.py:170-176`, the fifth
post-condition of `test_scn067_negative_harness_detects_broken_fixture`, running for all
five breakage cases:

    assert one_row(
        admin.execute(
            "SELECT bool_and(has_table_privilege(%s, 'harness.access_grant', p))"
            " FROM unnest(%s::text[]) AS p",
            (RUNTIME_ROLE, _RUNTIME_DML),
        )
    )[0] is True, f"runtime role lost part of its DML grant after restoring {name}"

with `_RUNTIME_DML: list[str] = ["SELECT", "INSERT", "UPDATE", "DELETE"]` (`:46`).

Three properties, each verified below rather than assumed:

1. **ALL, not ANY.** `bool_and` over the unnested array evaluates
   `has_table_privilege` once per privilege and conjoins the results, so a role holding
   three of four fails it. This is what the pre-R1 single call with a comma-separated list
   could not do — PostgreSQL reads that list as ANY/OR.
2. **The expectation is not derived from the grant.** `_RUNTIME_DML` is a separate literal
   list, deliberately not parsed out of `_RUNTIME_GRANT`. A future narrowing edit to the
   grant statement is therefore *caught by* the assertion rather than silently followed by
   it — mutants A and C below are exactly that edit, and both fail.
3. **The repair is untouched.** The `finally` loop (`:156-158`) still executes every
   restore statement regardless of outcome, so the ACL is always repaired; only the
   *verification* changed. Restore ordering (`OWNER TO` before `GRANT`, `:132`) is
   unchanged and remains load-bearing per the round-1 review's Q1.

R1's recommended `bool_and` form was adopted; the review's alternative (asserting the
literal `relacl` entry) was not, and the review's three **P3** findings were not addressed
— see §6.

## 2. Executed evidence — literal commands, literal results

Interpreter `backend/.venv/bin/python`, **Python 3.14.5**. Approved Colima/Docker binding
(CAP-008, APPROVED, no drift — §4). `-p no:randomly` pins collection order so each result
is attributable to the order under test rather than to a random seed.

### 2.1 Preflight and the file as committed

| # | command | result |
|---|---|---|
| 1 | `docker ps -a` / `docker volume ls` | 1 pre-existing out-of-scope container (`vigilant_matsumoto`, the unrelated `tradingview-mcp` workload), 2 pre-existing volumes (`712bec68008e…`, `tradingview-mcp-session`) |
| 2 | `backend/.venv/bin/python --version` | `Python 3.14.5` |
| 3 | `cd backend && timeout 480 .venv/bin/python -m pytest -q -p no:randomly tests/integration/test_tenant_isolation_harness.py` | **`12 passed in 1.75s`**, exit 0 |

### 2.2 Mutant apparatus

All four mutants were run in a throwaway full-structure copy at
`/tmp/veyro-bug048-r1-drill/` (`backend/tests`, `backend/app`, `backend/migrations`,
`backend/pyproject.toml`, `tools/`, venv symlinked), **never in the repository** — no repo
implementation or test file was edited at any point. Unmutated drill baseline:
`12 passed in 2.67s`, confirming the copy reproduces the repo result before any mutation.

Unlike the round-1 review, which was constrained to replicate the restore logic in SQL
inside a probe, these mutants edit the **real test file in the drill copy** and run the
**real pytest assertion**. That closes the one substitution the review stated plainly as a
limit (its §Limits item 4).

### 2.3 Mutant results — kill/survive table

| mutant | mutation | assertion under test | command | result | verdict |
|---|---|---|---|---|---|
| **A** | `_RUNTIME_GRANT` narrowed to `GRANT SELECT ON harness.access_grant TO veyro_runtime` | committed `bool_and` | `timeout 480 .venv/bin/python -m pytest -q -p no:randomly tests/integration/test_tenant_isolation_harness.py` | **`1 failed, 11 passed in 1.76s`** | **KILLED** |
| **B** | same `GRANT SELECT` partial grant, **plus** the pre-R1 shape restored (`_RUNTIME_DML = "SELECT, INSERT, UPDATE, DELETE"` as a `str`, single `has_table_privilege(%s, 'harness.access_grant', %s)` call) | pre-R1 comma-list | same | **`12 passed in 1.72s`** | **SURVIVED** |
| **C** | `_RUNTIME_GRANT` narrowed to `GRANT SELECT, INSERT, UPDATE` (DELETE dropped — 3 of 4) | committed `bool_and` | same | **`1 failed, 11 passed in 1.73s`** | **KILLED** |
| **D** | `_RUNTIME_GRANT` removed from the `runtime_owns_table` restore list entirely (the original BUG-048 shape) | committed `bool_and` | same | **`1 failed, 11 passed in 1.69s`** | **KILLED** |

**A vs B is the whole of R1, proven.** The identical defect — a SELECT-only partial
re-grant — is **invisible** to the pre-R1 assertion (`12 passed`, a fully green suite) and
**fatal** to the committed one. R1 was a real hole, and it is now closed.

Failure site and message, identical for A, C and D
(`tests/integration/test_tenant_isolation_harness.py:170`):

    E       AssertionError: runtime role lost part of its DML grant after restoring runtime_owns_table
    E       assert False is True

The pre-existing posture post-condition **passed in the same runs**, with
`probe.failures` carrying only the in-window expected `POSTURE:RUNTIME_ROLE_OWNS_TABLE` —
re-confirming BUG-048's founding finding that posture is blind to a dropped or narrowed ACL
entry, and therefore that this assertion, not posture, is the regression lock.

Drill teardown: the file was restored from a pristine pre-mutation copy, verified
`diff -q`-identical to the repo's own file (`DRILL-RESTORED-IDENTICAL-TO-REPO`), re-run to
`12 passed in 1.65s`, and the whole `/tmp` tree then deleted.

### 2.4 Full suite and order permutations (repository, unmutated)

| check | command | result |
|---|---|---|
| full suite, default order | `cd backend && timeout 1800 .venv/bin/python -m pytest -q -p no:randomly` | **`204 passed in 25.74s`** |
| full suite, Slice-5 **first** | same, with `tests/integration/test_tenant_isolation_harness.py` then the other 13 files explicitly | **`204 passed in 24.67s`** |
| full suite, Slice-5 **last** | same, other 13 files then the Slice-5 file | **`204 passed in 25.83s`** |
| lint | `cd backend && timeout 300 .venv/bin/python -m ruff check .` | **`All checks passed!`** |
| types (strict) | `cd backend && timeout 600 .venv/bin/python -m mypy tests/` | **`Success: no issues found in 28 source files`** |

204 is the established baseline total — this work adds no test function and removes none.
Both non-default orders BUG-048's closure criteria name (Slice-5 first *and* last) pass in a
single pytest session each.

**Carried forward from the round-1 review and NOT weakened here:** these order permutations
remain a **no-regression check, not a reproduction**, for the reason
`BUG048-REMEDIATION-2026-10-04.md` §4 established and the review independently corroborated
— `test_architecture_gate_rls.py` carries `_RUNTIME_GRANT` in one of its own early restore
lists and incidentally repairs the ACL before any of its own assertions run. The mutants in
§2.3, not these orders, are what proves the lock holds.

## 3. R2 — how the two durable records were reconciled

R2's finding was that two durable records described the post-condition as if it verified the
full DML set when it verified ANY of it. Both are now accurate, **by dated addendum with the
original text preserved verbatim** — no silent rewrite, so an auditor can still read what
was claimed, when, and on what basis:

1. **`evidence/bugs/BUG-048-harness-owner-restore-drops-runtime-grant.md`** — its R1/R2
   addendum pre-existed this session (§0) and already states the ANY/OR correction
   accurately, naming the window during which criterion 2 was met "only in letter." This
   session added only a short dated provenance note recording that this file's reference to
   this record was dangling until now, and which session did which half. Its original
   Finding/Impact/Closure-criteria/Remediation sections are untouched.
2. **`evidence/implementation/BUG048-REMEDIATION-2026-10-04.md`** — the record R2 named
   first, and the one the prior session never touched. Its §1.4 still **quotes the pre-R1
   comma-list assertion as the committed code**, its §3 calls it "proven load-bearing," and
   its §4 calls it "the real regression lock" without qualification. This session appended a
   dated **§7 addendum** stating precisely which of those claims were true, which were
   overstated and in what way, and which are now superseded — while leaving §1-§6 exactly
   as written, including the self-reported-model caveat and the §4 self-correction, both of
   which remain accurate.

What was **not** corrected, because measurement confirmed it was never wrong: §2's
"byte-identical ACL entry" claim. The round-1 review re-measured it independently and it
holds (`Q1-FIX-byte-identical-to-baseline True`). Over-correcting an accurate record would
be its own evidence defect.

## 4. Governance checks (all this session)

| check | command | result |
|---|---|---|
| governing baselines | `backend/.venv/bin/python knowledge/00-System/verify_baselines.py` | **PASS — 4/4 match `PROJECT_INDEX.md`** (Blueprint, TSD v1.4.1, EIP v1.4.1, design bundle) |
| capability registry | `backend/.venv/bin/python knowledge/00-System/validate_capabilities.py` | **PASS — 8 capabilities, all registered and APPROVED**, 0 errors |
| module capability manifest | `backend/.venv/bin/python tools/validate_capability_manifest.py --manifest knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml` | **PASS — 10 capability/Rule IDs**, no cyclic dependency, no missing mandatory privileged-surface Rule |
| capability drift | `backend/.venv/bin/python knowledge/05-QA/tools/capability_drift_check.py` | **PASS — 8 capabilities, no drift**; CAP-008 version/hash unchanged since approval |

Owner-reserved restrictions: no paid service or spend; no real member data (the
`access_grant` fixtures remain synthetic `synthetic-member-NNNN`/`synthetic-zone-N` rows);
no Production touch; no material product/pricing/business/architecture/scope change. No new
capability or tool is introduced — `bool_and`/`unnest`/`has_table_privilege` are plain SQL
over the already-registered CAP-008 Postgres binding. No governing baseline file touched.

Docker state after every run was **identical** to the preflight reading in §2.1 — same one
out-of-scope container, same two volumes, no harness container or volume residue, and no
prune of any kind was run. `git status --porcelain` measured immediately after all execution
and before this record was written was **byte-identical** to the session-start capture
(304 entries) — the mutants left nothing behind, and no pre-existing uncommitted work was
modified, reset, stashed or discarded.

## 5. What this does NOT establish

- **BUG-048 is still OPEN, and this record does not close it or change its status.**
  Closure criterion 4 (independent review) is **unmet for the strengthened assertion**. The
  round-1 review reviewed the *pre-R1* shape and found exactly this hole; the code that
  replaced it has had **no** independent review. A fresh-context `veyro-code-reviewer`
  (Opus) round 2, covering the `bool_and` assertion and these mutant results, is the next
  action. None was dispatched, self-attested, or claimed by this session, and
  `REVIEW_IN_FLIGHT.md` was neither read-claimed nor written.
- **No independent re-verification of the round-1 review's own SQL-level measurements.** Its
  `relacl` byte-identity, restore-ordering, PUBLIC-grant and role-attribute probe results
  are accepted from that record; this session re-proved only the pytest-level mutant
  behaviour, which is what R1 turned on.
- **Full-suite order permutations were not exhaustive.** Default, Slice-5-first and
  Slice-5-last were run this session; the *fully reversed* file order recorded in
  `BUG048-REMEDIATION-2026-10-04.md` §5 was **not** re-run, and is accepted from that record.
- **`knowledge/05-QA/tools/run_regression.py` was not re-run this session.** Its only known
  failure is the pre-existing `evidence_integrity_check.py` `CURRENT_HANDOFF.md`
  commit-staleness artifact of this project's no-commit-mid-round convention, already
  recorded as a standing artifact; re-running it would add a run record outside this charge.
  Stated as a gap rather than silently omitted.
- **Nothing else closed, promoted, or advanced.** SCN-MOD001-067, SCN-MOD001-009, R04 /
  ADR-010 A2, DOM-002 (whose round 5 remains `INTERRUPTED_IN_FLIGHT_EVIDENCE` with no
  verdict) and MOD-001 certification are all exactly as they were.

## 6. Unresolved items carried forward

| id | finding | disposition |
|---|---|---|
| **R3** | P3 — the grant verification is the last of five assertions, so an earlier failure skips it and yields no ACL diagnostic | **Open residual.** Not addressed: the sibling `_broken` helper has the same shape, so changing it here alone would diverge from the established idiom. Fix belongs with a charge that can touch both. |
| **R4** | P3 — the post-condition is catalog-only; no behavioural proof the `runtime` connection can actually perform DML | **Open residual.** `probe_same_tenant` is already on hand and would kill mutants A/C/D behaviourally as well; adding it is a real strengthening, out of this charge's scope. |
| **R5** | P3 — a PUBLIC grant satisfies the assertion with the runtime ACL entry absent; same idiom in the sibling `test_architecture_gate_rls.py`, which *does* carry PUBLIC-grant breakages | **Open residual, two halves.** Not reachable from Slice-5's breakage set (no Slice-5 breakage grants to PUBLIC — verified by the round-1 review across all five). The sibling-file half is explicitly left to its own bounded look, per that review's own recommendation. |
| **criterion 4** | independent review of the strengthened assertion | **Blocking for closure.** §5, first bullet. |
| — | the fully-reversed order permutation and `run_regression.py` | **Not re-run this session.** §5, bullets 3-4. |

**Recommended next action:** dispatch a fresh-context independent `veyro-code-reviewer`
(Opus) round 2 over `backend/tests/integration/test_tenant_isolation_harness.py` plus this
record and the reconciled `BUG048-REMEDIATION-2026-10-04.md` §7, following
`REVIEW_IN_FLIGHT.md`'s claim protocol (write the `IN_FLIGHT` claim before the dispatch call
returns). R3/R4/R5 are non-blocking and may be carried as recorded residuals or charged
separately — that is the orchestrator's and ultimately the owner's call, not this session's.
