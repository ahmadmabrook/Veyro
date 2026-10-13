---
doc: BUG048-SLICE5-ACL-RESTORE-CODE-REVIEW-ROUND1
module: MOD-001
bug: BUG-048
date: 2026-10-04
reviewer_role: veyro-code-reviewer (fresh-context independent Opus code review, DC-06)
reviewer_model_self_reported: claude-opus-5[1m] (self-reported from this session's environment
  banner; no mr_verify.py attestation produced by this session)
agent_id: code-reviewer/BUG048-slice5-acl-restore/round1 (subagent thread, see parent dispatch)
round: 1 (a PRIOR attempt at this same review was interrupted mid-test and produced NO verdict;
  it is not resumed, not read as findings, and not counted as a completed review)
status: COMPLETE — PASS-with-findings (P0=0, P1=0, P2=2, P3=3)
independence: I am an independent, fresh-context reviewer. I did NOT write the code under
  review and had no part in the BUG-048 remediation session. No self-approval.
---

# BUG-048 Slice-5 ACL-restore fix — independent code review, round 1

## Scope

One file under review: `backend/tests/integration/test_tenant_isolation_harness.py`
(uncommitted working-tree change, `git diff` for that path only). Nothing else in the
working tree is in scope for this review.

Reference material read before any execution:
`knowledge/03-Modules/MOD-001/evidence/bugs/BUG-048-harness-owner-restore-drops-runtime-grant.md`,
`knowledge/03-Modules/MOD-001/evidence/implementation/BUG048-REMEDIATION-2026-10-04.md`,
`backend/tests/harness/tenant_isolation.py`,
`backend/tests/integration/test_architecture_gate_rls.py` (sibling, already reviewed),
`backend/tests/integration/conftest.py`,
`knowledge/00-System/DEVELOPMENT_CONSTITUTION.md` DC-06.

## VERDICT

**PASS-with-findings.**

| severity | count | findings |
|---|---|---|
| **P0** | **0** | — |
| **P1** | **0** | — |
| **P2** | **2** | R1 (assertion is ANY/OR, not ALL — partial-grant mutant survives), R2 (durable record overstates the assertion's strength) |
| **P3** | **3** | R3 (assertion placement), R4 (catalog-only, no behavioural DML post-condition), R5 (PUBLIC-grant path not excluded; adjacent sibling-file exposure) |

The change is correct, is a genuine improvement over the pre-fix shape, repairs the ACL
byte-identically, and its new post-condition does kill the actual BUG-048 defect. Nothing in it
is unsafe, nothing regresses, and no owner-reserved restriction, unregistered capability, or
baseline drift is implicated. It does **not** warrant BLOCKED. The P2 findings are about the
*strength* of the new regression lock and the *accuracy* of the durable record describing it,
not about whether the fix works.

## Executed-this-session vs accepted-from-record

This distinction is deliberate: Q3 was charged as evidence-based, not re-executed.

### A. Observed by execution THIS session (literal command -> literal result)

1. `cd backend && timeout 300 .venv/bin/python /tmp/bug048_review_probe.py`
   -> the full `[...]` probe output quoted verbatim under Q1 and Q2. This covers: the
   provisioned baseline `relacl`/`nspacl`/RLS-flag state, the comma-list
   `has_table_privilege` semantics, the PUBLIC-grant path, the runtime role's
   NOINHERIT/NOSUPERUSER/NOBYPASSRLS/zero-membership attributes, the owner round-trip with and
   without the re-grant, the reversed restore order, the partial re-grant, and the ACL/flag
   invariance of the other four breakage cases.
2. `cd backend && timeout 480 .venv/bin/python -m pytest -q -p no:randomly tests/integration/test_tenant_isolation_harness.py`
   -> `12 passed in 6.44s`, exit 0. (The single bounded test invocation the charge allows.)
3. Docker state before and after, via the pinned Homebrew CLI against the Colima socket
   (`docker ps -a` / `docker volume ls`): before and after are **identical** — one pre-existing
   out-of-scope container `vigilant_matsumoto` and two pre-existing volumes
   (`712bec68008e…`, `tradingview-mcp-session`). No prune of any kind was run. No harness
   container or volume residue.
4. `git status --porcelain` -> the only in-scope repo path still shows as
   `M backend/tests/integration/test_tenant_isolation_harness.py` (the implementer's change,
   untouched by me). The only thing this review added to the tree is this report. No
   `git add`/`commit`/`push`/`stash`/`reset` was run.
5. Static reads (not execution, but my own first-hand reading, not the record's summary) of
   `test_tenant_isolation_harness.py` in full, `tests/harness/tenant_isolation.py`,
   `tests/integration/conftest.py`, and `test_architecture_gate_rls.py` lines 55-200 / 318-340.

### B. Accepted from previously recorded evidence WITHOUT re-execution

1. `BUG048-REMEDIATION-2026-10-04.md` §5's full-suite order permutations — **204 passed** in
   default order, Slice-5-first, Slice-5-last, and fully reversed. Not re-run (charge: no
   full-suite permutations, no `/tmp` full-structure copies).
2. §5's `ruff check .` clean and `mypy tests/` strict clean (28 files). Not re-run.
3. §5's governance-check table, including the pre-existing `evidence_integrity_check.py`
   `CURRENT_HANDOFF.md` staleness artifact. Not re-run.
4. §3's Drill 1/Drill 2 pytest-level results in the deleted `/tmp` copy. Not re-run — but Drill
   1's substance (re-grant removed -> the new assertion fails, posture stays silent) was
   **independently reproduced at the SQL level** this session as mutant M1, so I am not relying
   on the record for that claim.
5. §2's `relacl` table. Independently re-measured this session; it matches.

## Q1 — Does the owner round-trip actually restore `veyro_runtime` DML?

**Answer: YES. The re-grant is correct, the ordering is correct and load-bearing, the
"byte-identical ACL entry" claim holds, and the deliberate omission of a
`has_schema_privilege` assertion is safe for the Slice-5 breakage set.** All four
sub-claims were verified by direct execution this session, not accepted from the record.

Probe: `/tmp/bug048_review_probe.py`, preserved for reproduction as
`knowledge/03-Modules/MOD-001/evidence/code-review/bug048_review_probe_round1.py` (throwaway,
run from outside the repo tree; imports the project's own
`disposable_postgres()` / CAP-008 Colima route and `create_tenant_table`, so the fixture under
measurement is the real one). Command:
`cd backend && timeout 300 .venv/bin/python /tmp/bug048_review_probe.py`.

Literal results:

    [0-BASELINE-relacl] {veyro_schema_owner=arwdDxt/veyro_schema_owner,veyro_runtime=arwd/veyro_schema_owner}
    [0-BASELINE-nspacl] {veyro_schema_owner=UC/veyro_schema_owner,veyro_runtime=U/veyro_schema_owner}
    [0-BASELINE-flags]  ('veyro_schema_owner', True, True, 1, True, True)   # owner, rowsec, forcerowsec, policies, tenant_id NOT NULL, polqual present
    [Q1-M1-owned-by-runtime-relacl]   {veyro_runtime=arwdDxt/veyro_runtime}
    [Q1-M1-after-roundtrip-relacl]    {veyro_schema_owner=arwdDxt/veyro_schema_owner}
    [Q1-M1-after-roundtrip-htp(list)] False
    [Q1-FIX-relacl] {veyro_schema_owner=arwdDxt/veyro_schema_owner,veyro_runtime=arwd/veyro_schema_owner}
    [Q1-FIX-byte-identical-to-baseline] True
    [Q1-FIX-htp(list)] True

1. **Privilege set / object / grantee / grantor all match.** `_RUNTIME_GRANT`
   (`test_tenant_isolation_harness.py:41`) is `GRANT SELECT, INSERT, UPDATE, DELETE ON
   harness.access_grant TO veyro_runtime`; `create_tenant_table`
   (`backend/tests/harness/tenant_isolation.py:134`) issues the identical privilege list on the
   identical object to the identical grantee. The only difference is the issuing session:
   `create_tenant_table` runs it inside `as_schema_owner()` (`SET ROLE veyro_schema_owner`),
   while the restore runs it on the raw superuser `admin` connection. Measured, that difference
   is immaterial — PostgreSQL's `select_best_grantor` attributes a superuser-issued GRANT to the
   object's owner, so the restored entry is `veyro_runtime=arwd/veyro_schema_owner`, and the
   whole `relacl` array (entries *and* their order) compares byte-equal to the provisioned
   baseline (`Q1-FIX-byte-identical-to-baseline True`). The remediation record's
   "byte-identical" claim is confirmed, not merely privilege-equivalent.

2. **Restore ordering is correct, and the reverse order is genuinely broken.** Measured:

       [Q1-REV-grant-while-runtime-owns-relacl] {veyro_runtime=arwdDxt/veyro_runtime}
       [Q1-REV-after-owner-back-relacl]         {veyro_schema_owner=arwdDxt/veyro_schema_owner}
       [Q1-REV-htp(list)]                       False
       [Q1-REV-byte-identical-to-baseline]      False

   Issuing the GRANT while `veyro_runtime` still owns the table makes the grantee equal to the
   owner, so it merges into the owner's own default entry; the subsequent `OWNER TO
   veyro_schema_owner` then rewrites that merged entry and the runtime entry is lost again —
   exactly the BUG-048 failure. `OWNER TO` first, then `GRANT`, is the only order that works.
   The committed list `[OWNER TO veyro_schema_owner, _RUNTIME_GRANT]`
   (`test_tenant_isolation_harness.py:128`) is in that order, and the `finally` loop at
   lines 153-154 preserves list order, so this is correct as written. Worth noting for future
   edits: the ordering is load-bearing and nothing in the code comments says so.

3. **No other `BREAKAGES` case mutates the ACL.** Measured for all four remaining cases —
   ACL unchanged *even while broken*, and ACL/schema-ACL/flags identical to baseline after
   restore:

       [Q1-OTHER[rls_disabled]]       acl_changed_while_broken=False acl_after_restore_identical=True nspacl_identical=True flags_identical=True
       [Q1-OTHER[permissive_policy]]  ... all True / False as above
       [Q1-OTHER[rls_not_forced]]     ... all True / False as above
       [Q1-OTHER[tenant_id_nullable]] ... all True / False as above

   So `permissive_policy` and `rls_disabled` do fully revert, and the new assertion is
   redundant-but-harmless for those four (it is a regression lock, not a live check, there).

4. **Nothing else `create_tenant_table` provisions is dropped by the owner round-trip.**
   Measured across the owner round-trip: schema ACL (`nspacl`, which carries the
   `GRANT USAGE ON SCHEMA harness TO veyro_runtime`) unchanged
   (`Q1-M1-nspacl-unchanged True`); `relrowsecurity`, `relforcerowsecurity`, policy count (1),
   policy qual presence, and `tenant_id.attnotnull` all unchanged (`Q1-M1-flags-unchanged
   True`). The table has no sequence (its `id` default is `gen_random_uuid()`, not a serial) and
   no column-level grants, so there is nothing else grant-shaped to lose. **The deliberate
   omission of the sibling file's `has_schema_privilege(..., 'harness', 'USAGE')` assertion is
   therefore genuinely safe for this breakage set** — independently verified, not taken on the
   record's word. (It would become necessary the moment a Slice-5 breakage touched schema
   ownership or schema grants.)

## Q2 — Is the new post-condition load-bearing, or vacuous?

**Answer: PARTIALLY load-bearing. It kills a total loss of the grant, but it is materially
weaker than the record implies: `has_table_privilege` with a comma-separated privilege list is
ANY/OR in PostgreSQL, not ALL, so the assertion passes with only `SELECT` restored.** See
findings R1, R3, R4, R5.

**(a) Comma-list semantics — measured, OR/ANY.** With the runtime ACL entry narrowed to `r`
(SELECT only):

    [Q2a-only-SELECT-relacl]      {veyro_schema_owner=arwdDxt/veyro_schema_owner,veyro_runtime=r/veyro_schema_owner}
    [Q2a-only-SELECT-htp(list)]   True      <-- the committed assertion still passes
    [Q2a-only-SELECT-htp(INSERT)] False
    [Q2a-only-SELECT-htp(SELECT)] True
    [Q2a-none-relacl]             {veyro_schema_owner=arwdDxt/veyro_schema_owner}
    [Q2a-none-htp(list)]          False

So `has_table_privilege(role, table, 'SELECT, INSERT, UPDATE, DELETE')` is **true if ANY of the
listed privileges is held**. The assertion at
`backend/tests/integration/test_tenant_isolation_harness.py:163-168` therefore proves only "the
runtime role holds at least one of the four", not "the runtime role holds all four DML
privileges" — which is what BUG-048's closure criterion and the remediation record's wording
both read as. This is finding **R1**.

**(b) Can it be true with the ACL entry genuinely absent?** Yes, via a PUBLIC grant — measured:

    [Q2b-PUBLIC-relacl]                                 {veyro_schema_owner=arwdDxt/veyro_schema_owner,=arwd/veyro_schema_owner}
    [Q2b-PUBLIC-htp(list)-with-runtime-entry-absent]    True

Role inheritance and superuser status are **not** live escape routes here:
`[0-ROLE-attrs] (False, False, False, 0)` — `veyro_runtime` is NOINHERIT, NOSUPERUSER,
NOBYPASSRLS, with zero role memberships. And because the privilege is queried for a *named*
role rather than `current_user`, the `admin` connection's own superuser status is irrelevant.
No Slice-5 breakage grants anything to PUBLIC, so (b) is not exploitable by the current
breakage set — but the check does not pin the specific `veyro_runtime=arwd/veyro_schema_owner`
entry. Finding **R5**.

**(c) Placement.** The assertion is the *fifth and last* assertion in the test body (line 163),
after `probe.failures`, `codes <= posture_violations`, the behavioural-leak check, and the
posture-restored check. The **repair** itself is in the `finally` block (lines 152-154), so the
ACL is always restored regardless of outcome — that part is right. But the **verification**
never runs if any earlier assertion fails, so a run that fails for an unrelated reason produces
no ACL evidence at all. The sibling `_broken` helper has the same shape (its checks sit after
its own `try/finally`), so this is idiom-consistent rather than novel. Finding **R3**, P3.

**(d) Partial re-grant — mutant SURVIVES.** Measured:

    [Q2d-M2-partial-relacl]        {veyro_schema_owner=arwdDxt/veyro_schema_owner,veyro_runtime=r/veyro_schema_owner}
    [Q2d-M2-htp(list)]             True
    [Q2d-M2-ASSERTION-WOULD-PASS]  True
    [Q2d-M2-byte-identical-to-baseline] False
    [Q2d-M2-posture-violations]    (posture is blind to ACL, as BUG-048 states)

### Mutants run this session (explicit kill/survive table)

Mutation was performed in the throwaway probe, replicating the committed restore logic in SQL,
**not** by editing any repo file (hard constraint) and **not** by building a `/tmp` repo copy.

| mutant | what was changed | assertion result | verdict |
|---|---|---|---|
| **M1** — `_RUNTIME_GRANT` removed from the restore list (pre-fix shape) | `OWNER TO owner` only | `has_table_privilege(...) is True` -> **False** | **KILLED** |
| **M2** — `_RUNTIME_GRANT` narrowed to `GRANT SELECT` | partial re-grant | assertion -> **True** (passes) | **SURVIVED** |
| **M3** — restore order reversed (`GRANT` before `OWNER TO`) | ordering | assertion -> **False** | **KILLED** |
| **M4** — runtime entry absent but PUBLIC holds `arwd` | ACL entry genuinely gone | assertion -> **True** (passes) | **SURVIVED** (not reachable from the current breakage set) |

M1 killed is the important one: it reproduces BUG-048's own defect and the new assertion
catches it, with the posture post-condition staying silent — so the fix is **not** vacuous and
the remediation's Drill-1 claim is independently corroborated. M2/M4 surviving is why the
assertion is a *partial* regression lock rather than the full one the record describes.

## Q3 — Full-suite order closure

**Answer: the §4 self-correction is right, and I independently corroborated its mechanism.
Closure criteria 1-3 are met as literally worded, but criterion 3 is non-probative and
criterion 2 is weaker than its wording implies — so "genuinely met" applies to 1, and
"met-but-only-partially-meaningful" applies to 2 and 3.** Criterion 4 is what this review
addresses.

Per-criterion, against BUG-048's own closure list ("Restore re-grants DML; a post-restore grant
assertion exists; the full backend suite passes under at least one non-default order … ;
independent review"):

| # | criterion | status | basis |
|---|---|---|---|
| 1 | restore re-grants DML | **MET, verified by me** | Q1; byte-identical `relacl`, correct ordering |
| 2 | post-restore grant assertion exists | **MET in letter, PARTIAL in strength** | Q2; exists and runs for all 5 cases, kills M1, but survives M2/M4 (R1) |
| 3 | full suite passes under >=1 non-default order | **MET as worded, NON-PROBATIVE** | accepted from §5 (B.1); §4's own correction |
| 4 | independent review | **this document** | DC-06 — I did not write the code |

**Is the §4 correction right? Yes.** It claims the order permutations are a no-regression check
rather than a reproduction, because `test_architecture_gate_rls.py` incidentally repairs the ACL
before any of its own assertions run. I corroborated that mechanism by static reading rather
than by re-running the suite:

* `test_p1_canonical_harness_passes` (`test_architecture_gate_rls.py:156`) is the first test
  collected in that file and needs **no** DML on `harness.access_grant` — it runs the catalog
  gate via `_gate(admin)` and `_gate(runtime)` and checks `search_path`. A missing runtime DML
  grant is an *insufficiency*, and that gate hunts *excess* privilege, so it still passes.
* `test_p2_dml_through_clean_group_role` (line 168) is the first `_broken` user. Its break list
  contains `REVOKE ALL ON harness.access_grant FROM veyro_runtime` (a no-op if the entry is
  already gone) and its **restore list contains `_RUNTIME_GRANT`** (line 178); its in-window DML
  runs through the group role, not the runtime grant. So by the time `_broken`'s own
  `has_table_privilege` post-condition (line 136) evaluates, the ACL has already been repaired.

That is a complete mechanical explanation for how the pre-fix shape could still yield
`204 passed` with the Slice-5 file placed first, which is exactly what §4 reports. So the
honest correction is accurate, and the implementer was right to downgrade their own order
evidence rather than claim it as a reproduction. Consequence I agree with: **the post-restore
assertion, not the order permutations, is the regression lock** — which is precisely why R1
(that lock being ANY-of-four rather than all-four) matters more than it would otherwise.

I did not re-run any permutation, per the charge. My one bounded run (A.2, `12 passed`) confirms
only that the file passes as committed in its own default intra-file order.

## Findings

### R1 — P2 — `has_table_privilege` with a comma-separated list is ANY, not ALL

`backend/tests/integration/test_tenant_isolation_harness.py:42` (`_RUNTIME_DML`) and
`:163-168` (the assertion).

Measured this session: with the runtime entry narrowed to `r` (SELECT only),
`has_table_privilege('veyro_runtime', 'harness.access_grant', 'SELECT, INSERT, UPDATE, DELETE')`
returns **True** (`[Q2a-only-SELECT-htp(list)] True`, and `htp(INSERT)` False in the same
state). The assertion therefore proves "at least one of the four", not "all four". Mutant M2
(partial re-grant) survives it.

Concrete failure scenario: someone later edits `_RUNTIME_GRANT` — narrowing it to
`GRANT SELECT`, splitting it, or copying it to a new breakage case with a typo in the privilege
list. The Slice-5 file still reports 12 passed, the posture post-condition stays silent (it is
ACL-blind, as BUG-048 established), and the next file in collection order that does a runtime
`INSERT`/`UPDATE`/`DELETE` on `harness.access_grant` fails with `permission denied for table
access_grant` — BUG-048's exact symptom, re-introduced with its own guard green.

Recommended fix (one statement, same connection, no new dependency):

    assert one_row(admin.execute(
        "SELECT bool_and(has_table_privilege(%s, 'harness.access_grant', p))"
        " FROM unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE']) AS p",
        (RUNTIME_ROLE,),
    ))[0] is True, f"runtime role lost part of its DML grant after restoring {name}"

(An equally strong alternative: assert `relacl` contains the literal
`veyro_runtime=arwd/veyro_schema_owner` entry, which this session measured to be stable and
byte-identical across the round-trip, and which would also kill M4/R5.)

### R2 — P2 — the durable record overstates the assertion's strength

`knowledge/03-Modules/MOD-001/evidence/implementation/BUG048-REMEDIATION-2026-10-04.md` §1.4,
§3 ("proven load-bearing"), §4 ("the post-restore assertion is the real regression lock"), and
`knowledge/03-Modules/MOD-001/evidence/bugs/BUG-048-…md` lines 47-52 / 80-84.

The record reads as though the post-condition verifies the full DML set; measured, it verifies
ANY of it (R1). The Drill-1 claim is accurate — M1 is genuinely killed — but "the real
regression lock" is a partial lock, and a future gatekeeper reading only these files would
over-trust it. Note that §2's separate "byte-identical ACL entry" claim **is** confirmed by my
own measurement and needs no correction.

Concrete failure scenario: BUG-048 is closed on the strength of this record, R1's hole is never
addressed, and a later narrowing edit reopens the defect silently.

Recommended fix: amend the two evidence files to state that the post-condition is an
ANY-of-four check pending R1, and either adopt R1's `bool_and` form (preferred) or record the
limitation explicitly as a known residual. This is an orchestrator/owner edit — **I made no
change to either file**, per my no-edit constraint.

### R3 — P3 — the verification is the last of five assertions, so it is skipped on any earlier failure

`backend/tests/integration/test_tenant_isolation_harness.py:163` (after the asserts at
:157, :158, :160, :161).

The **repair** is safely in the `finally` block (:152-154) and always runs — that part is
correct. The **verification** does not run if `probe.failures`, the posture-code check, the
behavioural-leak check, or the posture-restored check fails first, so a run that fails for an
unrelated reason yields no ACL evidence at all, which is the exact diagnostic a future BUG-048
recurrence would need. The sibling `_broken` helper has the same shape, so this is
idiom-consistent, not novel — hence P3 rather than P2.

Recommended fix: perform the grant verification immediately after the `finally` restore loop
(before the probe assertions), or move it into a small helper invoked from `finally`, so it is
unconditional.

### R4 — P3 — catalog-only post-condition; no behavioural proof the runtime connection can do DML

`backend/tests/integration/test_tenant_isolation_harness.py:163-168`.

The check interrogates `pg_class`-derived privilege state through the `admin` connection. That
is correctly role-named (so `admin`'s superuser status does not short-circuit it — verified),
but it never exercises the `runtime` connection. This file already has a stronger instrument on
hand: `probe_same_tenant(runtime, admin, ACCESS_GRANT, b, access_grant_row(93)).failures == []`
performs a real same-tenant SELECT, UPDATE and INSERT as the non-privileged role and would kill
M2 and M4 as well as M1.

Concrete failure scenario: any future ACL mutation that leaves *some* privilege but not the set
the harness actually needs (R1's class, plus column-level revokes, plus a `REVOKE`-then-
`GRANT`-wrong-privilege sequence) passes the catalog check and fails later as a permission
error in another file.

Recommended fix: add (not replace) a behavioural post-condition for the `runtime_owns_table`
case at minimum, using the existing `probe_same_tenant` helper.

### R5 — P3 — a PUBLIC grant satisfies the assertion with the runtime ACL entry genuinely absent

`backend/tests/integration/test_tenant_isolation_harness.py:163-168`.

Measured: with the runtime entry removed and `arwd` granted to PUBLIC,
`has_table_privilege('veyro_runtime', …, list)` returns **True**
(`[Q2b-PUBLIC-htp(list)-with-runtime-entry-absent] True`). So the check does not pin the
specific `veyro_runtime=arwd/veyro_schema_owner` entry. Role-inheritance and superuser escape
routes are **not** live (`[0-ROLE-attrs] (False, False, False, 0)` — NOINHERIT, NOSUPERUSER,
NOBYPASSRLS, zero memberships), and **no Slice-5 breakage grants anything to PUBLIC** (verified
across all five cases), so this is not reachable from the file under review. P3 for that reason.

**Adjacent, explicitly OUT of this charge's one-file scope — recommend filing separately:** the
already-reviewed sibling `backend/tests/integration/test_architecture_gate_rls.py:136` uses the
identical ANY-semantics idiom in `_broken`, and that file *does* carry PUBLIC-grant breakages on
the same table (`n16_public_select` :393, `n21_public_truncate` :415, plus the `n29`/`n31b`
PUBLIC cases), where both R1's and R5's holes are materially more reachable. I did not review
that file's behaviour and am not asserting a defect in it — only that the same idiom there
deserves its own bounded look. I made no change to it.

Recommended fix for the reviewed file: adopt R1's `bool_and` form plus an explicit `relacl`
entry comparison, which closes R5 at the same time.

## Limits — what I did NOT verify, and why

1. **No full-suite run, in any order.** Charged not to (no long permutations, no `/tmp`
   full-structure copies). The `204 passed` x4 results in `BUG048-REMEDIATION-2026-10-04.md` §5
   are **accepted from the record**, not re-executed. If those numbers are wrong, this review
   does not catch it.
2. **No `ruff` / `mypy` re-run.** Accepted from §5. I did read the new type annotation
   (`BREAKAGES: list[tuple[str, str, list[str], set[str], bool]]`, :91) and the signature change
   (`restore_sql: list[str]`, :144) and they are internally consistent with the five tuple
   literals and the `finally` loop, but I did not re-execute the type checker.
3. **One bounded test invocation only**, and it was the Slice-5 file in its own default order.
   I did not run the sibling R04 file, the other integration files, or any cross-file order.
4. **Mutation was done at the SQL level in a throwaway probe, not by editing the test file.**
   The hard constraint forbids edits to any implementation or test file, so M1-M4 replicate the
   committed restore logic in SQL against the real fixture rather than mutating Python. The
   logic replicated is a two-statement list executed in order, identical to the `finally` loop,
   so I consider the substitution faithful — but it is a substitution, stated plainly.
5. **The `elevated_login` bypass-probe role's ACL entry across the owner round-trip was not
   measured.** Reasoning for why it is immaterial: that fixture (`conftest.py:69-85`) is
   function-scoped and creates a fresh role plus fresh grants on every use, and the parametrized
   breakage test is collected before both tests that use it, so no later test depends on a
   bypass-probe grant surviving a round-trip. Not verified, judged immaterial.
6. **PostgreSQL version scope.** All measurements are against the harness's pinned
   `postgres:16-alpine` digest. The ANY-semantics and owner-change ACL-rewrite behaviours are
   long-standing PostgreSQL semantics, but I verified them only on that pinned image.
7. **Not assessed, because out of charge:** DOM-002 round 5, SCN-009, SCN-067 promotion,
   ADR-010 A2, R04, the sibling R04 file's own correctness (beyond the two static structural
   points Q3 needed), and every other modified/untracked path in the working tree.
8. **Governance scan performed, nothing found.** No new capability or tool use is introduced by
   this change (`has_table_privilege` is plain SQL on the already-registered CAP-008 Postgres
   binding); no paid service, no real member data (`access_grant` fixtures remain synthetic
   `synthetic-member-NNNN` / `synthetic-zone-N` rows), no Production touch, no material product/
   pricing/architecture/scope change, no governing-baseline file touched. No
   owner-reserved-restriction violation and no baseline drift identified.

## Closure

**This review does not itself close BUG-048, and does not alter its status.** I made no change
to `BUG-048-harness-owner-restore-drops-runtime-grant.md`, to
`BUG048-REMEDIATION-2026-10-04.md`, to `REVIEW_IN_FLIGHT.md`, to `CURRENT_STATE.md`, to
`CURRENT_HANDOFF.md`, to `BUG_REGISTRY.md`, or to any implementation or test file. No scenario
was promoted. Closure — and whether R1/R2 must be resolved first or may be carried as recorded
residuals — is the orchestrator's and ultimately the owner's call, not mine.

My recommendation to whoever makes that call: the fix itself is sound and should not be
reworked. R1 is a two-line strengthening of an assertion that is already in the right place and
would take one bounded re-run to verify; resolving R1 and R2 before closure would leave BUG-048
closed on a regression lock that actually holds for the full privilege set, which is what the
bug's own closure criteria were reaching for.
