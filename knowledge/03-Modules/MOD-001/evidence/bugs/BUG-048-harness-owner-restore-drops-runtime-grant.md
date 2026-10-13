---
doc: BUG-048
module: MOD-001 (file: backend/tests/integration/test_tenant_isolation_harness.py)
severity: P2 (test-reliability defect in a Blocker-tier harness suite; fails toward false FAILURES, never false-clean evidence)
status: CLOSED 2026-10-04 — round-2 fresh independent code review PASS P0/P1/P2=0; R1/R2 P2 findings verified closed. P3 residuals nonblocking; no module/scenario certification implied.
filed: 2026-10-02 by veyro-critical-engineer (Opus, claude-opus-5-5), GOV-01-R04 critical slice
remediated: 2026-10-04 by the retained orchestrating session (self-reported `claude-opus-5[1m]`,
  no mr_verify attestation) — see the Remediation section below and
  `knowledge/03-Modules/MOD-001/evidence/implementation/BUG048-REMEDIATION-2026-10-04.md`
---

# BUG-048 — Slice-5 `runtime_owns_table` breakage restore silently revokes the runtime role's DML grant

## Finding

`test_scn067_negative_harness_detects_broken_fixture[runtime_owns_table]`
breaks the fixture with `ALTER TABLE harness.access_grant OWNER TO
veyro_runtime` and restores it with `... OWNER TO veyro_schema_owner`.
Postgres rewrites the ACL on each owner change, so the original
`veyro_runtime=arwd/veyro_schema_owner` entry is merged into the
temporary owner's privileges and then lost. After "restore",
`veyro_runtime` has no SELECT/INSERT/UPDATE/DELETE on `access_grant`.

The test's own post-condition (`read_posture(...).violations == []`)
checks role/table posture, not grants, so it does not notice.

## Reproduction (real execution, approved Colima binding)

`knowledge/03-Modules/MOD-001/evidence/implementation/bug048_acl_restore_probe.py`
(raw output in `evidence/security/R04-RLS-PERMISSION-GATES-RAW-2026-10-02.txt` §7):

    before : (True,  '{veyro_schema_owner=arwdDxt/veyro_schema_owner,veyro_runtime=arwd/veyro_schema_owner}')
    after  : (False, '{veyro_schema_owner=arwdDxt/veyro_schema_owner}')

## Impact

Masked today only by ordering: it is the last breakage case, and no later
test in that file needs runtime DML. It surfaced when the new R04 file
(which sorts earlier) used the same restore. It produced 7 "permission
denied for table access_grant" failures in that run. Running that file
before another runtime-DML test (reordering, a random-order run, or a
new test after it) reproduces the same. The failure direction is safe (a denied query reads as failure, not isolation), so
there is no false-clean risk, but the suite's results depend on order.

## Not fixed in the R04 slice

The fix is a one-line re-grant after the owner restore, plus a
`has_table_privilege` post-condition like the one the R04 test now uses.
It was deliberately not applied: the R04 dispatch was scoped to the two
gates only, and this test belongs to the already-reviewed Slice-5
harness. The R04 test's own restore is fixed and asserts grants after
every breakage.

## Closure criteria

Restore re-grants DML; a post-restore grant assertion exists; the full
backend suite passes under at least one non-default order (e.g. the
Slice-5 file run first and last); independent review.

## Remediation (2026-10-04) — fixed locally, NOT closed

Full record, including every command and raw result:
`knowledge/03-Modules/MOD-001/evidence/implementation/BUG048-REMEDIATION-2026-10-04.md`.

One file changed: `backend/tests/integration/test_tenant_isolation_harness.py`.
The `runtime_owns_table` restore now runs two statements — `OWNER TO
veyro_schema_owner` followed by the same `GRANT SELECT, INSERT, UPDATE,
DELETE … TO veyro_runtime` that `create_tenant_table` provisions the
fixture with — and every breakage case now ends with a
`has_table_privilege` post-condition, the same check the sibling R04
file's `_broken` helper already performs. `BREAKAGES`' restore element
became `list[str]` to match that sibling file's own shape.

Measured ACL after the Slice-5 file, same pytest session: pre-fix
`(False, False)` with the runtime entry absent; post-fix `(True, True)`
with `veyro_runtime=arwd/veyro_schema_owner` — byte-identical to the
provisioned entry, since PostgreSQL attributes a superuser `GRANT` to the
object's owner.

Closure criteria 1-3 are met: re-grant present; post-restore assertion
present and proven load-bearing (removing the re-grant in a throwaway
`/tmp` copy makes the new assertion fail with "runtime role lost its DML
grant after restoring runtime_owns_table", while the pre-existing posture
post-condition still passes in the same run); full backend suite
**204/204** in default order, with the Slice-5 file first, with it last,
and fully reversed, plus `ruff check` clean and `mypy tests/` strict clean
(28 files).

**Correction to this file's own Impact section, measured 2026-10-04.** The
claim "Running that file before another runtime-DML test … reproduces the
same" no longer holds for the current suite. With the complete pre-fix
shape restored in the drill copy, the whole suite with the Slice-5 file
placed *first* passed 204/204 — because `test_architecture_gate_rls.py`,
the only other file doing runtime DML on `access_grant`, carries
`_RUNTIME_GRANT` in one of its own early restore lists and incidentally
repairs the ACL before any of its own assertions run. The defect was
therefore masked by two coincidences, not one. Consequence: the
order-permutation runs are a no-regression check, not a reproduction, and
the post-restore assertion is the real regression lock. The original P2
severity and the safe-failure-direction assessment are unchanged.

Closure criterion 4 (**independent review**) is **not met**. This fix was
written by the session recording it, so per DC-06 BUG-048 stays
not-closed and continues to count as an open P2. A fresh-context
`veyro-code-reviewer` (Opus) review of this one-file change is the next
action; none was dispatched, self-attested, or claimed, and
`REVIEW_IN_FLIGHT.md` was not touched. Nothing was committed or pushed.

## Round-1 independent review (2026-10-04) and the R1 strengthening

An independent fresh-context Opus code review of the above remediation
was completed —
`knowledge/03-Modules/MOD-001/evidence/code-review/BUG048-SLICE5-ACL-RESTORE-CODE-REVIEW-ROUND1-2026-10-04.md`,
verdict **PASS-with-findings, P0=0/P1=0/P2=2/P3=3**. It confirmed by its
own execution that the re-grant is correct, that the restore ordering
(`OWNER TO` before `GRANT`) is load-bearing, that the ACL is repaired
byte-identically, and that the pre-fix no-grant shape is genuinely
caught. It also found the new post-condition **materially weaker than
this file's own text above implied** (finding R1, P2).

**Correction to the "post-restore grant assertion" claim above, measured
by that review and re-measured here.** As first written, the assertion
called `has_table_privilege(role, table, 'SELECT, INSERT, UPDATE,
DELETE')` with a **comma-separated** privilege list. PostgreSQL treats
that list as **ANY/OR, not ALL**: the call returns true if the role holds
*at least one* of the four. So from 2026-10-04 (first remediation) until
the R1 fix recorded below, closure criterion 2 was met only in letter —
the assertion proved "the runtime role holds at least one DML privilege
after restore", not the full-DML post-condition this file's closure
criteria were reaching for. A partial re-grant (e.g. a later narrowing
edit to `_RUNTIME_GRANT`) would have passed it silently, re-opening this
defect behind its own green guard.

**R1 fixed (2026-10-04, bounded follow-up session).** The assertion is
now `bool_and(has_table_privilege(...))` over an unnested
`SELECT`/`INSERT`/`UPDATE`/`DELETE` array, so **all four** privileges are
checked individually. The expectation list (`_RUNTIME_DML`) is
deliberately not derived from the `_RUNTIME_GRANT` statement, so a future
narrowing edit to the grant is caught by the assertion rather than
silently followed by it. The `finally` restore loop is unchanged — the
repair still always runs. Proven by execution against the real fixture:
the SELECT-only partial-grant mutant **survives** the old ANY/OR
assertion (12 passed) and is **killed** by the new one, a one-privilege
narrowing (DELETE dropped) is also killed, and the original no-grant
mutant **remains killed**. Full commands and raw results:
`knowledge/03-Modules/MOD-001/evidence/implementation/BUG048-R1-R2-REMEDIATION-2026-10-04.md`.

The review's three P3 findings (R3 assertion placement, R4 no behavioural
DML post-condition, R5 PUBLIC-grant path plus the adjacent same-idiom
exposure in the sibling `test_architecture_gate_rls.py`) are
**non-blocking and deliberately not addressed** by that bounded session;
they are carried as recorded residuals for a future charge, with R5's
sibling-file half explicitly left to its own bounded look.

**BUG-048 remains OPEN.** Criterion 4 is still unmet: the R1/R2 work was
done by a session acting on the review's findings, not by an independent
reviewer, so it is not self-approved and not closed. A **fresh**
independent review covering the strengthened assertion is the next
action. None was dispatched, self-attested, or claimed, and
`REVIEW_IN_FLIGHT.md` was not touched. Nothing committed or pushed.

### Provenance note (2026-10-04) — the above reference was dangling until now

Recorded so attribution across the two sessions stays honest; nothing in
the section above is retracted.

The session that applied the R1 code change to
`backend/tests/integration/test_tenant_isolation_harness.py` and wrote
the section above stopped before producing
`knowledge/03-Modules/MOD-001/evidence/implementation/BUG048-R1-R2-REMEDIATION-2026-10-04.md`
and before amending the second durable record R2 named. So from that
point until this note, the reference above pointed at a **file that did
not exist**, and the execution claims it makes (the partial-grant mutant
surviving the old ANY/OR assertion and being killed by the new one, the
DELETE-dropped narrowing killed, the original no-grant mutant still
killed) had **no evidence on disk** backing them.

A following bounded work unit (`mr_verify.py` on its own transcript:
**PASS, 58 turns, `claude-opus-5`**) closed that gap: it wrote no test or
production code, independently executed the full mutant set at the pytest
level against the real fixture — rather than at the SQL-probe level the
round-1 review was constrained to — re-verified the repository unmutated
(focused **12 passed**; full suite **204 passed** in default,
Slice-5-first and Slice-5-last orders; `ruff` clean; `mypy tests/` strict
clean, 28 files), wrote the referenced record, and appended the dated §7
addendum to `BUG048-REMEDIATION-2026-10-04.md` that R2's first half
required. **The claims above are therefore now evidence-backed rather
than asserted**, and the reference resolves.

That session did not review the strengthened assertion, dispatch or claim
any review, touch `REVIEW_IN_FLIGHT.md`, change this bug's status,
promote any scenario, or commit or push anything. **BUG-048 stays OPEN**
and criterion 4 stays unmet.

## Closure adjudication — 2026-10-04

Fresh independent round-2 code review returned PASS (P0/P1/P2=0), and the orchestrator verified the reviewer transcript: `mr_verify.py` PASS, 108/108 turns `claude-opus-5`. The reviewer executed the focused 12-test file, reproduced the original no-grant and partial-grant mutants as killed by the strengthened assertion, and confirmed the pre-fix ANY/OR control survives. The two R1/R2 P2 findings and all BUG-048 closure criteria are met. Two new and three carried P3 observations are documented as nonblocking in the report; they do not trigger another reassurance review. No claim is made that R04/ADR-010 A2, SCN-067, or MOD-001 certification passed. Report: `knowledge/03-Modules/MOD-001/evidence/code-review/BUG048-SLICE5-ACL-RESTORE-CODE-REVIEW-ROUND2-2026-10-04.md`.
