---
doc: BUG048-SLICE5-ACL-RESTORE-CODE-REVIEW-ROUND2
module: MOD-001
bug: BUG-048
date: 2026-10-04
reviewer_role: veyro-code-reviewer (fresh-context independent Opus code review, DC-06)
reviewer_model_self_reported: claude-opus-5[1m] (**self-reported** from this session's
  environment banner — "Opus 5 (1M context), exact model ID claude-opus-5[1m]". This session
  produced **no** `mr_verify.py` attestation and claims none; the orchestrator runs
  `knowledge/05-QA/tools/mr_verify.py` against this session's actual transcript independently.)
round: 2 (reviewing the R1-strengthened assertion and the R2 record reconciliation. Round 1 is
  `BUG048-SLICE5-ACL-RESTORE-CODE-REVIEW-ROUND1-2026-10-04.md`; this round does not re-open it.)
status: COMPLETE — PASS-with-findings (P0=0, P1=0, P2=0, P3=2 new + 3 carried)
independence: I am an independent, fresh-context reviewer. I did NOT write the code under
  review, did not author any record under review, and had no part in the BUG-048 remediation
  or the R1/R2 follow-up session. No self-approval. I closed nothing and changed no status.
---

# BUG-048 Slice-5 ACL-restore — independent code review, round 2

## Scope

Bounded to the closure of round 1's two **P2** findings:

* **R1** — the post-restore grant assertion was ANY/OR, not ALL, so a partial-grant mutant
  survived it.
* **R2** — the durable records overstated that assertion's strength.

Artifacts reviewed: `backend/tests/integration/test_tenant_isolation_harness.py` (the
`_RUNTIME_DML` constant `:46`, the explaining comments `:42-45` and `:166-169`, and the
`bool_and`/`unnest` assertion `:170-176`);
`knowledge/03-Modules/MOD-001/evidence/implementation/BUG048-R1-R2-REMEDIATION-2026-10-04.md`;
the dated §7 addendum in
`knowledge/03-Modules/MOD-001/evidence/implementation/BUG048-REMEDIATION-2026-10-04.md`;
the dated addendum + provenance note in
`knowledge/03-Modules/MOD-001/evidence/bugs/BUG-048-harness-owner-restore-drops-runtime-grant.md`;
round 1's report. Read for context: `backend/tests/harness/postgres.py`,
`backend/tests/harness/tenant_isolation.py`, `backend/tests/integration/conftest.py`,
`backend/pyproject.toml`, `SESSION_BOOTSTRAP.md`, the project `CLAUDE.md` and the four
`.claude/rules/` files in the session context.

Not pursued, per charge: DOM-002 (not re-opened — its code-review cycle is closed), R04 /
ADR-010 A2, SCN-MOD001-067 and SCN-MOD001-009 promotion, MOD-001 certification, the sibling
`test_architecture_gate_rls.py`'s own correctness, and the full-suite order permutations
(accepted from record — I found no concrete named risk requiring a re-run; see §B.1).

## VERDICT

**PASS-with-findings.** Both round-1 P2 findings are **genuinely closed**, verified by my own
execution rather than accepted from either record.

| severity | count | findings |
|---|---|---|
| **P0** | **0** | — |
| **P1** | **0** | — |
| **P2** | **0** | round 1's R1 and R2 are both **CLOSED** — see Q1/Q2 (R1) and Q3 (R2) |
| **P3** | **2 new** | **R2-1** the expectation list `_RUNTIME_DML` is itself unguarded (my mutant E survives); **R2-2** no gate detects a dangling cross-reference between durable records |
| **P3** | **3 carried** | round 1's R3 (assertion placement), R4 (no behavioural DML post-condition), R5 (PUBLIC-grant path + sibling-file exposure) — disposition as open residuals confirmed honest, none has become blocking |

The `bool_and`/`unnest` assertion is a **true conjunction over all four privileges**, is
**fail-closed in every degenerate binding case I could construct**, and is **load-bearing** —
the identical partial-grant defect is invisible to the pre-R1 shape (`12 passed`) and fatal to
the committed one (`1 failed, 11 passed`). The three mutants the remediation record tabulates
all reproduce **exactly** as recorded; nothing I measured contradicts its §2.3 table. The two
record reconciliations preserve the original text verbatim and describe the strength
accurately. Nothing here warrants BLOCKED. No owner-reserved restriction, unregistered
capability, or baseline drift is implicated.

---

## (A) Observed by execution THIS session — literal command → literal result

Interpreter: `/Users/ahmadmabrouk/Desktop/Veyro/backend/.venv/bin/python`, **Python 3.14.5**.
Docker route: the project's own pinned CAP-008 binding — `/opt/homebrew/bin/docker` →
`../Cellar/docker/29.6.0/bin/docker`, `Docker version 29.6.0, build fb59821d45` (matches
`postgres.py`'s `TRUSTED_DOCKER_CLI_REALPATH` / `TRUSTED_DOCKER_CLI_VERSION`), Colima socket
`/Users/ahmadmabrouk/.colima/default/docker.sock` present. Every container came from
`disposable_postgres()` on the digest-pinned
`postgres@sha256:721873c3…6080ea`. `-p no:randomly` throughout.

### A.0 Baseline and integrity

    git rev-parse HEAD                  -> 015d7ef3dca4cd42f335226b789b8610fd218c92
    git status --porcelain | wc -l       -> 306
    shasum -a 256 backend/tests/integration/test_tenant_isolation_harness.py
      -> fd8de67fae35eb81b3291c8864353b43c836d03c83794fc601819d184e123c5d

Matches the charge exactly. Read-only git only (`status`, `diff`, `log`, `rev-parse`,
`check-ignore`). No `add`/`commit`/`push`/`reset`/`stash`/`checkout --`/`restore`/`clean`.

### A.1 Docker state before / after — identical

    # BEFORE                                        # AFTER
    0a670e63ab46 mikeh1975/tradingview-mcp:latest   0a670e63ab46 mikeh1975/tradingview-mcp:latest
      "node dist/index.js" Up 2 hours                 "node dist/index.js" Up 2 hours
      NAMES vigilant_matsumoto                        NAMES vigilant_matsumoto

    local 712bec68008ece99c2974826cc2f384d370b4c6bfa6054854ee98cf2ec361acf   (both readings)
    local tradingview-mcp-session                                            (both readings)

One pre-existing out-of-scope container, two pre-existing volumes, **byte-identical before and
after all work**. I left them alone. **No `docker volume prune`, `docker system prune`, or any
blanket prune was run at any point.** No harness container or volume residue.

### A.2 Drill apparatus (throwaway, outside the repository)

Built `/tmp/veyro-bug048-r2-drill/` mirroring `backend/tests`, `backend/app`,
`backend/migrations`, `backend/pyproject.toml`, `tools/`, with `backend/.venv` **symlinked** to
the repo venv — the remediation record's own apparatus. A pristine pre-mutation copy was kept
at `/tmp/veyro-bug048-r2-drill/PRISTINE_test_tenant_isolation_harness.py`.

    shasum -a 256 /tmp/.../backend/tests/integration/test_tenant_isolation_harness.py \
                  /Users/.../backend/tests/integration/test_tenant_isolation_harness.py
    -> fd8de67fae35eb81b3291c8864353b43c836d03c83794fc601819d184e123c5d   (both)

**Unmutated drill baseline**, established before any mutation:

    cd /tmp/veyro-bug048-r2-drill/backend && timeout 600 .venv/bin/python -m pytest -q \
      -p no:randomly tests/integration/test_tenant_isolation_harness.py
    -> 12 passed in 1.77s      (exit 0)

So the copy reproduces the repository result before mutation; every later kill is attributable
to the mutation, not the copy. **All mutation happened in this `/tmp` copy. No repository
implementation, test, or governance file was edited at any point** — confirmed in §A.6.

### A.3 Q1 semantics probe (SQL level, real fixture)

    cd /tmp/veyro-bug048-r2-drill/backend && PYTHONPATH=. timeout 600 \
      .venv/bin/python /tmp/bug048_review_probe_round2.py

Literal output (probe source reproduced verbatim in the Apparatus appendix below):

    [0-BASELINE-relacl] '{veyro_schema_owner=arwdDxt/veyro_schema_owner,veyro_runtime=arwd/veyro_schema_owner}'
    [Q1a-unnest-rowcount] 4
    [Q1a-unnest-rows] [('SELECT', 1), ('INSERT', 2), ('UPDATE', 3), ('DELETE', 4)]
    [Q1a-array-roundtrip-text] '{SELECT,INSERT,UPDATE,DELETE}'
    [Q1a-array-length] 4
    [Q1a-per-privilege-full-grant] [('SELECT', True), ('INSERT', True), ('UPDATE', True), ('DELETE', True)]
    [Q1e-FULL-GRANT-committed] 'bool_and=True -> `is True` = True -> assertion PASSES'
    [Q1c-SELECT-ONLY-relacl] '{veyro_schema_owner=arwdDxt/veyro_schema_owner,veyro_runtime=r/veyro_schema_owner}'
    [Q1b-SELECT-ONLY-commalist] True
    [Q1c-SELECT-ONLY-per-privilege] [('SELECT', True), ('INSERT', False), ('UPDATE', False), ('DELETE', False)]
    [Q1c-SELECT-ONLY-committed] 'bool_and=False -> `is True` = False -> assertion FAILS'
    [Q1c-3-OF-4-relacl] '{veyro_schema_owner=arwdDxt/veyro_schema_owner,veyro_runtime=arw/veyro_schema_owner}'
    [Q1c-3-OF-4-committed] 'bool_and=False -> `is True` = False -> assertion FAILS'
    [Q1c-NO-GRANT-relacl] '{veyro_schema_owner=arwdDxt/veyro_schema_owner}'
    [Q1c-NO-GRANT-committed] 'bool_and=False -> `is True` = False -> assertion FAILS'
    [Q1d-restored-relacl] '{veyro_schema_owner=arwdDxt/veyro_schema_owner,veyro_runtime=arwd/veyro_schema_owner}'
    [Q1d-empty-list-rowcount-or-error] 0
    [Q1d-empty-list-committed] 'bool_and=None -> `is True` = False -> assertion FAILS'
    [Q1d-single-SELECT-rowcount-or-error] 1
    [Q1d-single-SELECT-committed] 'bool_and=True -> `is True` = True -> assertion PASSES'
    [Q1d-duplicated-SELECT-rowcount-or-error] 4
    [Q1d-duplicated-SELECT-committed] 'bool_and=True -> `is True` = True -> assertion PASSES'
    [Q1d-typo-SELCT-rowcount-or-error] 4
    [Q1d-typo-SELCT-committed] 'RAISED InvalidParameterValue: unrecognized privilege type: "SELCT"'
    [Q1d-BROKEN-acl-relacl] '{veyro_schema_owner=arwdDxt/veyro_schema_owner,veyro_runtime=r/veyro_schema_owner}'
    [Q1d-BROKEN-acl-with-single-SELECT-list] 'bool_and=True -> `is True` = True -> assertion PASSES'
    [Q1d-BROKEN-acl-with-empty-list] 'bool_and=None -> `is True` = False -> assertion FAILS'
    [Q1f-broken-relacl] '{veyro_runtime=arwdDxt/veyro_runtime}'
    [Q1f-after-owner-only-committed] 'bool_and=False -> `is True` = False -> assertion FAILS'
    [Q1f-after-full-restore-relacl] '{veyro_schema_owner=arwdDxt/veyro_schema_owner,veyro_runtime=arwd/veyro_schema_owner}'
    [Q1f-byte-identical-to-pre] True
    [Q1f-after-full-restore-committed] 'bool_and=True -> `is True` = True -> assertion PASSES'

### A.4 Q2 mutants (pytest level, real test file in the drill copy)

Each mutant was applied to the drill copy by exact-string replacement with a
`count == 1` assertion (so no mutation can silently miss or double-apply), `diff`-ed against
the pristine copy to show exactly what changed, run, then reverted from pristine before the
next. Command for every run:

    cd /tmp/veyro-bug048-r2-drill/backend && timeout 600 .venv/bin/python -m pytest -q \
      -p no:randomly tests/integration/test_tenant_isolation_harness.py

| mutant | literal diff vs pristine | literal pytest result | verdict |
|---|---|---|---|
| **baseline** | *(none)* | `12 passed in 1.77s` | n/a |
| **A** partial grant vs **committed** `bool_and` | `:41` `GRANT SELECT, INSERT, UPDATE, DELETE …` → `GRANT SELECT …` | `1 failed, 11 passed in 1.71s` | **KILLED** |
| **B** *discriminating control* — same partial grant vs **pre-R1** comma-list | `:41` as A; `:46` `_RUNTIME_DML: list[str] = [...]` → `_RUNTIME_DML: str = "SELECT, INSERT, UPDATE, DELETE"`; `:172-173` `bool_and(...)/unnest(%s::text[])` → `SELECT has_table_privilege(%s, 'harness.access_grant', %s)` | `12 passed in 1.66s` | **SURVIVED** |
| **C** 3-of-4 (DELETE dropped) vs committed | `:41` → `GRANT SELECT, INSERT, UPDATE …` | `1 failed, 11 passed in 1.71s` | **KILLED** |
| **D** no-grant, original BUG-048 shape | `:132` `[... OWNER TO {OWNER_ROLE}", _RUNTIME_GRANT]` → `[... OWNER TO {OWNER_ROLE}"]` | `1 failed, 11 passed in 1.68s` | **KILLED** |
| **E** *my addition* — grant **and** `_RUNTIME_DML` both narrowed to `SELECT` | `:41` as A; `:46` → `_RUNTIME_DML: list[str] = ["SELECT"]` | `12 passed in 1.69s` | **SURVIVED** → finding **R2-1** |

Failure site and message, identical for A, C and D:

    >       assert one_row(
                admin.execute(
                    "SELECT bool_and(has_table_privilege(%s, 'harness.access_grant', p))"
                    " FROM unnest(%s::text[]) AS p",
                    (RUNTIME_ROLE, _RUNTIME_DML),
                )
            )[0] is True, f"runtime role lost part of its DML grant after restoring {name}"
    E       AssertionError: runtime role lost part of its DML grant after restoring runtime_owns_table
    E       assert False is True

    tests/integration/test_tenant_isolation_harness.py:170: AssertionError
    FAILED tests/integration/test_tenant_isolation_harness.py::test_scn067_negative_harness_detects_broken_fixture[runtime_owns_table]

Exactly one parametrized case fails in each kill — `[runtime_owns_table]`, the only case whose
restore touches the ACL. The captured evidence line in the same failing runs shows
`"failures": ["POSTURE:RUNTIME_ROLE_OWNS_TABLE"]` and
`"posture_violations": ["RUNTIME_ROLE_OWNS_TABLE"]` only, with the posture-restored assertion
(`:165`) passing — independently re-confirming BUG-048's founding finding that **posture is
blind to a dropped or narrowed ACL entry**, and therefore that this assertion, not posture, is
the regression lock.

### A.5 Drill teardown and repository re-verification

    cp PRISTINE_test_tenant_isolation_harness.py backend/tests/integration/test_tenant_isolation_harness.py
    diff -q <drill file> <repo file>   -> DRILL-RESTORED-IDENTICAL-TO-REPO
    shasum -a 256 <drill file> <repo file>
      -> fd8de67fae35eb81b3291c8864353b43c836d03c83794fc601819d184e123c5d   (both)
    <drill, unmutated re-run>          -> 12 passed in 1.69s

    rm -rf /tmp/veyro-bug048-r2-drill /tmp/bug048_review_probe_round2.py
    ls -d /tmp/veyro-bug048-r2-drill   -> No such file or directory
    ls /tmp/bug048_review_probe_round2.py -> No such file or directory

Against the **repository** file (not the copy):

    cd backend && timeout 600 .venv/bin/python -m pytest -q -p no:randomly \
      tests/integration/test_tenant_isolation_harness.py   -> 12 passed in 1.71s
    cd backend && timeout 300 .venv/bin/python -m ruff check .   -> All checks passed!
    cd backend && timeout 600 .venv/bin/python -m mypy tests/    -> Success: no issues found in 28 source files

`.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/` and `__pycache__/` are all covered by
`backend/.gitignore` (verified with `git check-ignore -v`), so these runs add no working-tree
entry — confirmed in §A.6.

### A.6 Final repository integrity

    git rev-parse HEAD              -> 015d7ef3dca4cd42f335226b789b8610fd218c92   (unchanged)
    git status --porcelain | wc -l  -> 306   (measured after all execution, AND again after
                                             this report was written — still 306, see note)

**Note on the expected "306 + 1".** The charge expected 307 after my report. It is **306**, and
that is correct rather than a missing file. `knowledge/03-Modules/MOD-001/evidence/code-review/`
has **zero tracked files** (`git ls-files <dir> | wc -l` -> `0`), so default
`git status --porcelain` collapses the whole directory into **one** `??` entry — which was
already among the 306. My report landed inside an already-counted entry and so adds no new
line. Verified present explicitly:

    git status --porcelain | grep code-review
      -> ?? knowledge/03-Modules/MOD-001/evidence/code-review/
    git status --porcelain -uall | grep ROUND2
      -> ?? knowledge/03-Modules/MOD-001/evidence/code-review/BUG048-SLICE5-ACL-RESTORE-CODE-REVIEW-ROUND2-2026-10-04.md
    git status --porcelain -uall | wc -l   -> 336   (the directory-collapsed 306 expands to 336)

Recording this because the charge's integrity check was stated as an exact arithmetic match and
it does not hold for a reason worth knowing: for this evidence tree, the porcelain count is
insensitive to adding a report, so "306 + 1" cannot be used as the completeness signal for a
review's own deliverable here. The load-bearing checks — unchanged HEAD, unchanged
`test_tenant_isolation_harness.py` hash, and the report's verified presence — all hold.
    shasum -a 256 backend/tests/integration/test_tenant_isolation_harness.py
      -> fd8de67fae35eb81b3291c8864353b43c836d03c83794fc601819d184e123c5d   (unchanged)
    git status --porcelain -- backend/tests/integration/test_tenant_isolation_harness.py
      ->  M backend/tests/integration/test_tenant_isolation_harness.py   (the implementer's
            change, untouched by me)

All 306 pre-existing entries preserved. The only thing this review adds to the tree is this
report. **I did not touch** `BUG-048-harness-owner-restore-drops-runtime-grant.md`,
`BUG048-REMEDIATION-2026-10-04.md`, `BUG048-R1-R2-REMEDIATION-2026-10-04.md`,
`REVIEW_IN_FLIGHT.md`, `CURRENT_STATE.md`, `CURRENT_HANDOFF.md`, `BUG_REGISTRY.md`, or any
governing baseline. I did not read-claim, write, or clear `REVIEW_IN_FLIGHT.md`.

### A.7 Governance checks (all run by me this session)

| check | command | literal result |
|---|---|---|
| governing baselines | `backend/.venv/bin/python knowledge/00-System/verify_baselines.py` | `PASS — all 4 governing baseline hashes match … PROJECT_INDEX.md exactly.` (Blueprint `80f4b381…`, TSD `0d41c8a1…`, EIP `e5b5ec3b…`, design bundle `c96f77ab…`) |
| capability registry | `… knowledge/00-System/validate_capabilities.py` | `PASS — 8 capability/capabilities, all registered and APPROVED`, **0 errors** |
| capability drift | `… knowledge/05-QA/tools/capability_drift_check.py` | `PASS — 8 capabilities checked, no drift detected.` CAP-008 version/hash unchanged since approval |
| module manifest | `… tools/validate_capability_manifest.py --manifest knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml` | `PASS — 10 capability/Rule ID(s) … no cyclic dependency; no missing mandatory privileged-surface Rule`, **0 errors** |

---

## (B) Accepted from previously recorded evidence WITHOUT re-execution

Stated so no accepted number is mistaken for my own measurement.

1. **The full-suite order permutations.** `BUG048-REMEDIATION-2026-10-04.md` §5's **204
   passed** in default / Slice-5-first / Slice-5-last / fully-reversed order, and
   `BUG048-R1-R2-REMEDIATION-2026-10-04.md` §2.4's **204 passed** in default /
   Slice-5-first / Slice-5-last. **Not re-run.** Per charge I re-run a permutation only on a
   concrete named risk; I found none. My reasoning: the permutations are, by both records'
   own correction and round 1's independent corroboration, a *no-regression* check rather than
   a reproduction (the sibling `test_architecture_gate_rls.py` carries `_RUNTIME_GRANT` in an
   early restore list and incidentally repairs the ACL before its own assertions run). The
   regression lock is the assertion, and that I measured directly at the pytest level in §A.4.
   A permutation re-run would therefore not discriminate anything the mutants do not. If the
   204 figures are wrong, this review does not catch it.
2. **Round 1's own SQL-level measurements** that I did not re-take: the PUBLIC-grant path
   (`Q2b`), the runtime role's NOINHERIT/NOSUPERUSER/NOBYPASSRLS/zero-membership attributes
   (`[0-ROLE-attrs]`), and the ACL/flag invariance of the four non-owner breakage cases. I did
   independently re-measure `relacl` byte-identity across the owner round-trip
   (`Q1f-byte-identical-to-pre True`), which agrees with round 1's
   `Q1-FIX-byte-identical-to-baseline True`.
3. **`run_regression.py`** was not run by me (as it was not by the R1/R2 session). The
   standing `evidence_integrity_check.py` `CURRENT_HANDOFF.md` commit-staleness artifact of
   this project's no-commit-mid-round convention is accepted as a known artifact; I observed
   it incidentally in the pre-existing run record `RUN_20261004T103621Z.txt`, which I read but
   did not produce.
4. **The `mr_verify.py` attestation of the R1/R2 session** (`PASS, 58 turns, 100% consistent,
   `claude-opus-5`, transcript `50b16e73-…jsonl`). Accepted from that record's front matter;
   I did not run `mr_verify.py` against anyone's transcript, including my own.

---

## Q1 — Is the `bool_and` assertion genuinely ALL-four, by my own execution?

**Answer: YES, unambiguously, and it is fail-closed in every degenerate binding case I could
construct.** Measured, not accepted.

**The parameter binding is real, not silently single-element or empty.** The committed SQL is
`unnest(%s::text[])` with `_RUNTIME_DML` bound as a Python `list[str]`. psycopg adapts it to a
genuine 4-element PostgreSQL array: the round-trip renders as `{SELECT,INSERT,UPDATE,DELETE}`,
`array_length(…, 1)` is **4**, and the unnest produces **4 rows** carrying exactly
`('SELECT', 1), ('INSERT', 2), ('UPDATE', 3), ('DELETE', 4)`. This was the specific vacuity
risk the charge named, and it does not obtain.

**Each privilege is evaluated independently.** Under a SELECT-only ACL
(`veyro_runtime=r/veyro_schema_owner`), the per-row evaluation is
`[('SELECT', True), ('INSERT', False), ('UPDATE', False), ('DELETE', False)]` — four distinct
`has_table_privilege` evaluations, not one list-valued call.

**It is a true conjunction.** `bool_and` over those four rows yields `False` for SELECT-only,
`False` for 3-of-4 (`arw`, DELETE dropped), `False` for no grant at all, and `True` only for
the full `arwd` entry. The assertion's `… [0] is True` therefore FAILS in the first three and
PASSES only in the last.

**Round 1's R1 premise is independently confirmed.** In the *same* SELECT-only state, the
pre-R1 form `has_table_privilege(role, table, 'SELECT, INSERT, UPDATE, DELETE')` returns
**True** (`[Q1b-SELECT-ONLY-commalist] True`). PostgreSQL does read a comma list as ANY/OR.
R1 was a real hole, measured twice now by two independent reviewers.

**Degenerate cases — all fail-closed:**

| degenerate binding | rows | `bool_and` | what the committed assertion does |
|---|---|---|---|
| `[]` (empty list) | **0** | **`None`** (NULL over zero rows) | `None is True` → `False` → **assertion FAILS** |
| `["SELECT"]` | 1 | `True` | assertion PASSES — *vacuous w.r.t. the other three* → **R2-1** |
| `["SELECT"]*4` (duplicates) | 4 | `True` | assertion PASSES — vacuous, same class → R2-1 |
| `["SELCT", …]` (typo) | 4 | — | **raises** `InvalidParameterValue: unrecognized privilege type: "SELCT"` → test ERRORS |

The charge specifically asked what happens in the zero-row case, since `bool_and` over zero
rows returns NULL. The answer is the safe one: because the assertion compares with the
identity operator `is True` rather than a truthiness test, `None` fails it. A `== True` or a
bare `assert one_row(...)[0]` would also have failed on `None`, but `is True` additionally
rejects any non-`bool` truthy value. **The `is True` form is load-bearing for fail-closure and
should not be "simplified" by a future edit.**

**End-to-end against the real owner round-trip:** after `OWNER TO veyro_runtime` the ACL is
`{veyro_runtime=arwdDxt/veyro_runtime}`; after `OWNER TO veyro_schema_owner` **alone** the
assertion FAILS (BUG-048's original shape, caught); after the committed restore list's second
statement the ACL is byte-identical to the provisioned baseline
(`Q1f-byte-identical-to-pre True`) and the assertion PASSES.

## Q2 — Independently killing the mutants

**Answer: all three mutants the record tabulates reproduce exactly, the discriminating control
survives exactly, and nothing I measured contradicts §2.3.** One additional mutant of my own
(E) survived and is reported as **R2-1**.

See the literal table in §A.4. Summarised:

| mutant | result | verdict | agrees with record §2.3? |
|---|---|---|---|
| **A** partial `GRANT SELECT` vs committed `bool_and` | `1 failed, 11 passed` | **KILLED** | **yes** (its row A) |
| **B** same partial grant vs **pre-R1** comma-list *(control)* | `12 passed` | **SURVIVED** | **yes** (its row B) |
| **C** 3-of-4, DELETE dropped | `1 failed, 11 passed` | **KILLED** | **yes** (its row C) |
| **D** re-grant removed (original BUG-048 shape) | `1 failed, 11 passed` | **KILLED** | **yes** (its row D) |
| **E** grant *and* `_RUNTIME_DML` both narrowed *(mine)* | `12 passed` | **SURVIVED** | not in the record — **new, R2-1** |

**A vs B is decisive and I measured both.** The identical defect — a SELECT-only partial
re-grant on the `runtime_owns_table` restore — leaves the pre-R1 shape **fully green** and
makes the committed shape **fail at `:170` with the intended message**. That is what proves the
new assertion is load-bearing rather than incidentally green, and it is the one claim neither
record could be allowed to establish on its own authority. It holds.

Mutation was performed on the **real test file inside the drill copy** and run through the
**real pytest assertion**, which is the apparatus the remediation record used and which closes
round 1's stated substitution limit (round 1 could only replicate the restore logic in SQL
inside a probe). I confirm the drill copy was restored from pristine, verified
`diff -q`-identical and hash-identical to the repository file, re-run clean, and then deleted
along with my probe; and that the repository file's hash is unchanged from session start
(§A.5, §A.6).

## Q3 — Record accuracy (R2)

**Answer: R2 is closed. Both records now describe the assertion's actual strength accurately,
the original text is preserved rather than silently rewritten, the dangling cross-reference is
resolved, and every execution claim I could re-measure matches what I measured.**

**Does any record still overstate the lock? No.** I checked the specific claims:

* `BUG048-REMEDIATION-2026-10-04.md` **§1.4 still quotes the pre-R1 comma-list assertion
  verbatim** as the committed code — i.e. the original text really is preserved, not rewritten.
  The file's front matter now carries an `addendum:` pointer stating that §7 corrects
  §1.4/§3/§4 and that §1-§6 are preserved verbatim, with "read §7 before relying on any
  §1.4/§3/§4 statement about the assertion's strength." That forward-pointer matters: it is
  what stops a reader who stops at §1.4 from over-trusting it, and it is correctly placed in
  front matter rather than buried.
* The **§7 addendum is accurate.** Its claim-by-claim table is right on every row I can
  adjudicate: §1.4's existence claim accurate / its implied strength overstated; §3's Drill-1
  total-loss kill accurate (my mutant D); §4's "which mechanism is the lock" accurate but "how
  much that lock covered" overstated; §2's byte-identity accurate and correctly **not**
  corrected. Declining to over-correct an accurate claim is itself good evidence discipline.
  Its own mutant table matches my §A.4 results row for row.
* The **bug record's** addendum states the ANY/OR correction, names the window in which
  criterion 2 was met "only in letter," records the R1 fix, and keeps its original
  Finding/Impact/Closure-criteria/Remediation sections intact. Accurate.
* **The previously-dangling cross-reference is resolved.** `BUG048-R1-R2-REMEDIATION-2026-10-04.md`
  exists at the path the bug record names, and the bug record's own dated provenance note
  discloses that the reference pointed at a non-existent file until that record was written —
  disclosing one's own prior evidence gap rather than quietly filling it is the right handling.

**Does the remediation record's own execution account match what I measure?** Yes, on every
item I re-took: its §2.1 focused `12 passed` (I measured `12 passed in 1.71s` in the repo and
`12 passed in 1.77s` as the drill baseline); its `ruff` clean and `mypy` strict clean on 28
files (I re-ran both — `All checks passed!`, `Success: no issues found in 28 source files`);
its §4 governance table (I re-ran all four validators — all PASS with the same counts: 4/4
baselines, 8 capabilities, no drift, 10 manifest IDs); its §2.3 mutant table (§A.4); its
Docker-state and no-prune discipline (§A.1). I found **no** contradiction.

**Is §0's provenance account consistent with what `git diff` shows?** Consistent, and not
contradicted — but with a limit worth stating precisely rather than glossing. `git diff` for
the file shows the **cumulative** working-tree delta against HEAD `015d7ef3`: the full BUG-048
remediation *and* the R1 strengthening as one combined change. It shows the `bool_and`/`unnest`
form present and the pre-R1 comma-list form absent, which is consistent with §0's claim that
the R1 code change pre-existed the R1/R2 session and that the session "wrote no new line of
test or production code." But a cumulative diff **cannot by itself** separate what the first
session did from what the second did, so git alone can neither confirm nor refute the split.
What does corroborate it is filesystem ordering, which I measured independently: the test file's
mtime is **2026-10-04 13:33:25**, whereas `BUG048-R1-R2-REMEDIATION-2026-10-04.md` is
**13:46:48** and the two reconciled records are **13:47:34** and **13:47:48** — i.e. the code
edit precedes the R1/R2 session's record-writing by ~13 minutes, and the round-1 report
(**13:29:09**) precedes the code edit, exactly the sequence §0 describes. I treat §0 as
**consistent and corroborated by mtime, not independently provable from git**, and I am not
asserting more than that.

**Minor, non-finding observations** (recorded because I noticed them, not inflated):

* `BUG048-R1-R2-REMEDIATION-2026-10-04.md` states "all 304 pre-existing working-tree entries
  preserved." I measured 306. This **reconciles cleanly** and is not an error: 304 at that
  session's start, `+1` for the record it created (`305`), `+1` for
  `BUG048-ROUND2-ACPX-RAW-2026-10-04.txt`, which the orchestrator created afterwards at
  **14:03:47** (after that session's last write at 13:47:48) = **306**. I verified the mtime
  ordering that makes this add up.
* That record's §2.3 teardown claim ("the whole `/tmp` tree then deleted") is **true as
  scoped** — `/tmp/veyro-bug048-r1-drill/` is indeed absent. Three unrelated scratch files it
  does not claim to have deleted (`/tmp/bug048r1_gitstatus_{before,after,final}.txt`) remain.
  Not a defect against any claim made.
* A `/tmp/veyro-bug048-review/` full-structure copy (`backend/` + `tools/`, mtime
  **13:13:27**) and `/tmp/bug048_review_probe.py` (**13:24:21**) still exist. The timestamps
  fall in round 1's window, and round 1's report states its charge excluded `/tmp`
  full-structure copies — but round 1's front matter also records an *interrupted prior
  attempt* at the same review, which is an equally plausible author. **I cannot attribute it**
  and I deliberately **did not delete it**, since it may be another session's evidence. Flagged
  for the orchestrator's `/tmp` hygiene, not charged as a finding against anyone.

## Q4 — Residuals and closure posture

**Is carrying R3/R4/R5 as open P3 residuals honest? Yes.** Each is recorded with its finding
text, an explicit disposition, and a stated reason, and none is characterised as fixed. R3's
reason (the sibling `_broken` helper shares the shape, so changing one file alone would diverge
from the established idiom, and the fix belongs to a charge that can touch both) is a sound
engineering reason rather than an excuse. R4's (the behavioural `probe_same_tenant`
strengthening is real but out of charge) is accurate — and I note it would have killed my
mutant E as well, which makes R4 the most valuable of the three. R5's two halves are correctly
separated, with the Slice-5 half marked unreachable from the current breakage set and the
sibling-file half left to its own bounded look.

**Has any of them become blocking in light of the strengthened assertion? No.**

* **R3** (placement) is unchanged in character: the *repair* remains unconditional in the
  `finally` loop (`:156-158`) — I confirmed the restore still always runs — while the
  *verification* at `:170` remains the fifth and last assertion. The strengthening made the
  verification sharper, not differently placed. Still P3.
* **R4** (no behavioural post-condition) is *less* pressing than before for the privilege set
  it names, since the catalog check now covers all four rather than any one. It gains a new
  reason to exist (it would be immune to R2-1's expectation-list hole), but not a blocking one.
* **R5** (PUBLIC-grant path) is untouched by the strengthening — `bool_and` over four
  independently-evaluated `has_table_privilege` calls is just as satisfied by a PUBLIC grant as
  one comma-list call was, because the hole is in *which grantee* the predicate pins, not in
  how many privileges it checks. Still unreachable from Slice-5's breakage set (accepted from
  round 1, §B.2). Still P3. Round 1's alternative fix — asserting the literal
  `veyro_runtime=arwd/veyro_schema_owner` `relacl` entry — would close R5 **and** R2-1 at once,
  which is now the strongest single argument for adopting it.

**Is BUG-048's closure criterion 2 ("a post-restore grant assertion exists") met in strength,
not merely in letter?** **Yes, for the four DML privileges the fixture is provisioned with** —
this is my own measurement, not either record's claim. The assertion exists, runs for all five
breakage cases, is a true conjunction over all four privileges, is fail-closed on a NULL/empty
result and errors on an invalid privilege name, and is demonstrably load-bearing: the defect
that survived the pre-R1 shape is fatal to it. Criterion 2 is no longer satisfied "in letter
only."

The one qualification I will not leave out: that strength is **bounded by the completeness of
`_RUNTIME_DML` itself**, which nothing cross-checks (**R2-1**, P3). So the honest formulation is
"met in strength, with a one-constant residual," not "met absolutely."

**I do not close BUG-048 and I have not altered its status.** Criterion 4 is the orchestrator's
and ultimately the owner's call on the strength of this document; it is not mine to self-award.
I promoted no scenario, changed no gate, and wrote nothing outside this report.

---

## Findings

### R2-1 — P3 — the expectation list `_RUNTIME_DML` is itself unguarded, so the lock is one constant deep

**Anchors:** `backend/tests/integration/test_tenant_isolation_harness.py:46` (the constant),
`:42-45` (the comment asserting resistance to narrowing edits), `:170-176` (the assertion).

**Measured this session.** Mutant **E** — narrowing `_RUNTIME_GRANT` to `GRANT SELECT …`
**and** narrowing `_RUNTIME_DML` to `["SELECT"]` — yields **`12 passed in 1.69s`**: a fully
green suite with the runtime role holding only `SELECT` on `harness.access_grant` after
restore. The SQL-level probe shows the same shape directly: with a SELECT-only ACL in place,
`_RUNTIME_DML = ["SELECT"]` gives `bool_and=True → assertion PASSES`
(`[Q1d-BROKEN-acl-with-single-SELECT-list]`).

The comment at `:42-45` says the expectation is "deliberately NOT derived from
`_RUNTIME_GRANT`: a future narrowing edit to that statement has to be caught by this list, not
silently followed by it." That is true as far as it goes, and the design intent is right. But
the protection is exactly one line deep: nothing mechanically ties `_RUNTIME_DML` to the
privilege set `create_tenant_table`
(`backend/tests/harness/tenant_isolation.py:134`) actually provisions. The same wording appears
in the durable records (`BUG048-R1-R2-REMEDIATION-2026-10-04.md` §1 property 2; the bug
record's R1-fixed paragraph), so to that extent they claim slightly more future-proofing than
holds — a smaller instance of exactly the R2 class, which is why I raise it here rather than
leaving it unsaid.

**Concrete failure scenario.** A developer narrows `_RUNTIME_GRANT` (to match a later
production grant change, or while copying the breakage case). The suite goes red at `:170`
with "runtime role lost part of its DML grant". They read the message as the *expectation*
being stale rather than the *grant* being wrong — the single most common response to a failing
assertion — and update `_RUNTIME_DML` to match. The suite returns to `12 passed`, posture stays
silent (ACL-blind, per BUG-048's founding finding), and the next test in collection order that
performs a runtime `INSERT`/`UPDATE`/`DELETE` on `harness.access_grant` fails with
`permission denied for table access_grant`. That is BUG-048's exact symptom, re-introduced
behind a green guard — the same outcome R1 was raised to prevent, one level up.

**Recommended fix (either, not both).** Preferably adopt round 1's alternative and assert the
literal provisioned ACL entry, which removes the free-floating expectation entirely and closes
**R5** at the same time — I measured the entry to be stable and byte-identical across the owner
round-trip (`Q1f-byte-identical-to-pre True`):

    assert one_row(admin.execute(
        "SELECT relacl::text FROM pg_class WHERE oid = 'harness.access_grant'::regclass"
    ))[0] == "{veyro_schema_owner=arwdDxt/veyro_schema_owner,veyro_runtime=arwd/veyro_schema_owner}", \
        f"runtime role's ACL entry not restored byte-identically after restoring {name}"

Alternatively, keep `bool_and` but source the privilege list from the harness module that
provisions it (a single exported constant shared by `create_tenant_table`, `_RUNTIME_GRANT` and
the assertion), so that a narrowing edit cannot be made consistent in one place without being
visibly inconsistent in another. Either way, **keep the `is True` comparison** — Q1 shows it is
what makes the zero-row/NULL case fail closed.

Severity rationale: **P3, not P2.** Unlike R1, this is not reachable by an edit to one
statement whose guard then stays green — it requires a deliberate second edit to the
expectation constant that the in-code comment explicitly warns against. It is a residual
hardening opportunity in a test-only file, not a live defect in the committed code, and the
committed code is correct as written.

### R2-2 — P3 — nothing detects a durable record referencing a file that does not exist

**Anchors:** `knowledge/03-Modules/MOD-001/evidence/bugs/BUG-048-harness-owner-restore-drops-runtime-grant.md`
(the "Provenance note" section, which discloses the defect);
`knowledge/05-QA/tools/` (where the missing check would live).

The R2 reconciliation's own account names a real, already-materialised failure: the bug record
referenced `BUG048-R1-R2-REMEDIATION-2026-10-04.md` by name while that file did not exist, so
four specific execution claims sat on disk with **no backing evidence** for a period. That
instance is now closed — the file exists, the claims are evidence-backed, and the gap is
disclosed rather than hidden, which is the right handling.

What is **not** closed is the defect class. I checked: no tool under `knowledge/05-QA/tools/`
or `knowledge/00-System/*.py` performs reference resolution over the knowledge tree.
`evidence_integrity_check.py` checks commit staleness, not whether a referenced path exists.
So the next dangling reference is equally undetectable, and a gatekeeper reading a record that
cites a non-existent evidence file has no mechanical signal.

**Concrete failure scenario.** A session writes a bug-record addendum citing
`evidence/implementation/FOO-REMEDIATION.md` for its execution results, then is interrupted
before writing it (precisely what happened here). A later gatekeeper reads the addendum, sees a
specific named evidence path, treats the claims as backed, and certifies on them. Nothing in
the regression suite objects.

**Recommended fix.** Add a check to `knowledge/05-QA/tools/` (or to
`evidence_integrity_check.py`) that extracts `knowledge/…` and `backend/…` path references
from `knowledge/**/*.md` and fails when a referenced path does not exist on disk. This is a
cheap, high-leverage governance gate and it would have caught this instance at the moment it
was created. **Out of my charge to implement** — I made no change.

### Carried forward from round 1 (not re-adjudicated, disposition confirmed)

| id | finding | my assessment this round |
|---|---|---|
| **R3** | P3 — grant verification is the last of five assertions, skipped on any earlier failure | **Still open, still P3.** Repair remains unconditional in `finally` (`:156-158`); only verification is late. Unchanged by the strengthening. |
| **R4** | P3 — catalog-only; no behavioural proof the `runtime` connection can do DML | **Still open, still P3.** Now *also* the fix that would be immune to R2-1. Most valuable of the three. |
| **R5** | P3 — a PUBLIC grant satisfies the assertion with the runtime entry absent; same idiom in the sibling file | **Still open, still P3, untouched by the strengthening** — the hole is in which grantee is pinned, not in how many privileges are checked. Closed as a side effect by R2-1's preferred `relacl` fix. |

---

## Governance scan — performed, nothing found

Run and reported even though clean, per charge.

* **Owner-reserved restrictions — no violation.** *No paid services or spend*: every tool used
  is local (project venv, pinned Homebrew Docker CLI, local Colima VM, digest-pinned
  `postgres:16-alpine`); nothing reached a paid API or provisioned a billable resource. *No
  real member data*: the fixtures remain synthetic — `access_grant` rows are
  `synthetic-member-NNNN`/`synthetic-zone-N` shaped, tenant ids are per-run `uuid4()`, and the
  runtime password is a per-run `secrets.token_urlsafe(24)` that is never committed. *No
  Production*: all work ran against throwaway containers on `127.0.0.1`, force-removed on exit;
  no deploy or promotion of any kind. *No material product/pricing/business/architecture/scope
  change*: I changed no code, config, or governing document; the change under review is a
  test-only post-condition in an existing test.
* **No unregistered or unqualified capability use.** The change introduces no new capability —
  `bool_and`, `unnest` and `has_table_privilege` are plain SQL over the already-registered
  **CAP-008** Postgres/Colima binding, which `validate_capabilities.py` reports APPROVED and
  `capability_drift_check.py` reports version/hash unchanged since approval. My own tooling was
  confined to that same CAP-008 route plus the project venv's pytest/ruff/mypy and read-only
  git. I used no MCP connector; in particular I made no Notion call, so
  `.claude/rules/global/notion-mcp-scope-discipline.md` was not engaged.
* **No baseline drift.** All four governing baselines hash-match `PROJECT_INDEX.md` (§A.7). No
  governing baseline file was read-modified or renamed. HEAD unchanged.
* **No secrets-rule exposure.** Nothing credential-shaped was written to any file by me; the
  probe generated no credential and printed none (it logs only ACL text, booleans and row
  counts), per `.claude/rules/infra/secrets.md`.
* **Docker discipline (CAP-008 / BUG-051) honoured.** Pinned CLI and Colima socket verified
  before use; `disposable_postgres()` used for every container; `docker ps -a` / `docker volume
  ls` identical before and after (§A.1); no prune of any kind; the one pre-existing
  out-of-scope container and two pre-existing volumes left untouched.
* **Review-separation (DC-06) honoured.** Fresh context, no authorship of the code or any
  record under review, no self-approval, no fix implemented, nothing closed. I did not
  read-claim, write, or clear `REVIEW_IN_FLIGHT.md`.

---

## Limits — what I did NOT verify, and why

1. **No full-suite run, in any order.** Accepted from record (§B.1) with my reasoning for why
   a permutation re-run would not discriminate anything the mutants do. The **204 passed**
   figures are **not my measurement**.
2. **I did not re-take round 1's PUBLIC-grant, role-attribute, or non-owner-breakage
   ACL-invariance measurements** (§B.2). My R5 assessment therefore rests on round 1's
   execution for the "no Slice-5 breakage grants to PUBLIC" premise, not my own.
3. **No `mr_verify.py` attestation.** My model id in the front matter is **self-reported** from
   my environment banner. I ran `mr_verify.py` against no transcript — not mine, not the R1/R2
   session's. The R1/R2 session's attestation is accepted from its record (§B.4).
4. **`run_regression.py` not run** (§B.3).
5. **Provenance has an irreducible limit.** `git diff` shows only the cumulative delta against
   HEAD, so the "what pre-existed vs what that session did" split in §0 is corroborated by
   file mtimes and the records' own account, **not proven from git**. Stated plainly in Q3
   rather than papered over.
6. **PostgreSQL version scope.** Every semantic I measured — comma-list ANY/OR, `bool_and` NULL
   over zero rows, `text[]` binding, owner-change ACL rewrite, `unrecognized privilege type` —
   was measured only on the digest-pinned `postgres:16-alpine`. These are long-standing
   PostgreSQL behaviours, but my evidence covers that image.
7. **I did not review the sibling `test_architecture_gate_rls.py`'s own correctness**, R04 /
   ADR-010 A2, SCN-MOD001-067 or SCN-MOD001-009 promotion, MOD-001 certification, or any other
   modified/untracked path in the 306-entry working tree. **DOM-002 was not re-opened,
   reviewed, resumed, or replaced** — its code-review cycle is closed and I treated it as
   strictly out of scope.
8. **I did not attribute or remove the pre-existing `/tmp` artifacts** from other sessions
   (Q3's third observation). Deliberate: they may be another session's evidence.
9. **Mutant E is my own construction**, not from any record, and is reported as a residual
   hardening finding rather than a defect in committed behaviour.

## Apparatus — reproduction probe

Per hard constraint 2, **the only file I created in the repository is this report** (final
working-tree count 306 + 1). Rather than add a second file and break that count, the probe's
full source is reproduced here; it is byte-for-byte what produced the §A.3 output. Recreate it
at `/tmp/bug048_review_probe_round2.py` and run it from a drill copy's `backend/` directory
with `PYTHONPATH=.` as shown in §A.3. It was deleted at teardown along with the drill tree.

```python
"""Round-2 independent code review probe for BUG-048 R1 (the bool_and/unnest
post-restore assertion).  Measures, against the project's own real fixture on
the pinned CAP-008 Colima/postgres:16-alpine binding:

  Q1a  the exact committed SQL's parameter binding: does `unnest(%s::text[])`
       with a Python list[str] really produce one row per privilege?
  Q1b  comma-list `has_table_privilege` semantics (ANY/OR) - re-measured
  Q1c  the committed bool_and form under a SELECT-only ACL (must be False)
  Q1d  degenerate bindings: empty list (zero rows -> bool_and NULL), single
       element, duplicated element, invalid privilege name - and in each case
       what the committed `... [0] is True` assertion would DO.
  Q1e  the full-grant baseline (must be True) and relacl identity.

Read-only against the repository: run from /tmp, imports the drill copy's
harness.  Spins up and tears down its own disposable container.
"""

from __future__ import annotations

import psycopg

from tests.harness.postgres import disposable_postgres
from tests.harness.tenant_isolation import (
    ACCESS_GRANT,
    ACCESS_GRANT_COLUMNS,
    OWNER_ROLE,
    RUNTIME_ROLE,
    create_tenant_table,
    one_row,
    provision_roles,
)

# verbatim from test_tenant_isolation_harness.py:46
_RUNTIME_DML: list[str] = ["SELECT", "INSERT", "UPDATE", "DELETE"]
# verbatim from test_tenant_isolation_harness.py:172-173
COMMITTED_SQL = (
    "SELECT bool_and(has_table_privilege(%s, 'harness.access_grant', p))"
    " FROM unnest(%s::text[]) AS p"
)


def log(tag: str, value: object) -> None:
    print(f"[{tag}] {value!r}")


def relacl(admin: psycopg.Connection[tuple[object, ...]]) -> str:
    return str(
        one_row(
            admin.execute(
                "SELECT relacl::text FROM pg_class WHERE oid = 'harness.access_grant'::regclass"
            )
        )[0]
    )


def committed_assertion_outcome(admin, privs) -> str:
    """Exactly what the committed assertion does, including the `is True` test."""
    try:
        value = one_row(admin.execute(COMMITTED_SQL, (RUNTIME_ROLE, privs)))[0]
    except Exception as exc:  # noqa: BLE001 - we are measuring the failure mode
        return f"RAISED {type(exc).__name__}: {str(exc).splitlines()[0]}"
    passes = value is True
    return f"bool_and={value!r} -> `is True` = {passes} -> assertion {'PASSES' if passes else 'FAILS'}"


def main() -> None:
    with disposable_postgres() as pg:
        with psycopg.connect(pg.superuser_dsn, autocommit=True) as admin:
            provision_roles(admin)
            create_tenant_table(admin, ACCESS_GRANT, ACCESS_GRANT_COLUMNS)

            log("0-BASELINE-relacl", relacl(admin))

            # ---- Q1a: does the %s::text[] binding really unnest to 4 rows? ----
            rows = admin.execute(
                "SELECT p, row_number() OVER () FROM unnest(%s::text[]) AS p", (_RUNTIME_DML,)
            ).fetchall()
            log("Q1a-unnest-rowcount", len(rows))
            log("Q1a-unnest-rows", rows)
            log(
                "Q1a-array-roundtrip-text",
                one_row(admin.execute("SELECT (%s::text[])::text", (_RUNTIME_DML,)))[0],
            )
            log(
                "Q1a-array-length",
                one_row(
                    admin.execute("SELECT array_length(%s::text[], 1)", (_RUNTIME_DML,))
                )[0],
            )
            # and that each unnested value is evaluated independently
            per_priv = admin.execute(
                "SELECT p, has_table_privilege(%s, 'harness.access_grant', p)"
                " FROM unnest(%s::text[]) AS p",
                (RUNTIME_ROLE, _RUNTIME_DML),
            ).fetchall()
            log("Q1a-per-privilege-full-grant", per_priv)

            # ---- Q1e: full-grant baseline ----
            log("Q1e-FULL-GRANT-committed", committed_assertion_outcome(admin, _RUNTIME_DML))

            # ---- Q1b/Q1c: narrow the ACL to SELECT only ----
            admin.execute(f"REVOKE ALL ON harness.access_grant FROM {RUNTIME_ROLE}")
            admin.execute(f"GRANT SELECT ON harness.access_grant TO {RUNTIME_ROLE}")
            log("Q1c-SELECT-ONLY-relacl", relacl(admin))
            log(
                "Q1b-SELECT-ONLY-commalist",
                one_row(
                    admin.execute(
                        "SELECT has_table_privilege(%s, 'harness.access_grant', %s)",
                        (RUNTIME_ROLE, "SELECT, INSERT, UPDATE, DELETE"),
                    )
                )[0],
            )
            log(
                "Q1c-SELECT-ONLY-per-privilege",
                admin.execute(
                    "SELECT p, has_table_privilege(%s, 'harness.access_grant', p)"
                    " FROM unnest(%s::text[]) AS p",
                    (RUNTIME_ROLE, _RUNTIME_DML),
                ).fetchall(),
            )
            log("Q1c-SELECT-ONLY-committed", committed_assertion_outcome(admin, _RUNTIME_DML))

            # 3-of-4 (DELETE missing)
            admin.execute(f"GRANT INSERT, UPDATE ON harness.access_grant TO {RUNTIME_ROLE}")
            log("Q1c-3-OF-4-relacl", relacl(admin))
            log("Q1c-3-OF-4-committed", committed_assertion_outcome(admin, _RUNTIME_DML))

            # no grant at all
            admin.execute(f"REVOKE ALL ON harness.access_grant FROM {RUNTIME_ROLE}")
            log("Q1c-NO-GRANT-relacl", relacl(admin))
            log("Q1c-NO-GRANT-committed", committed_assertion_outcome(admin, _RUNTIME_DML))

            # ---- Q1d: degenerate expectation-list bindings ----
            # restore the full grant first so the ONLY variable is the list
            admin.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON harness.access_grant TO {RUNTIME_ROLE}"
            )
            log("Q1d-restored-relacl", relacl(admin))
            for label, privs in [
                ("empty-list", []),
                ("single-SELECT", ["SELECT"]),
                ("duplicated-SELECT", ["SELECT", "SELECT", "SELECT", "SELECT"]),
                ("typo-SELCT", ["SELCT", "INSERT", "UPDATE", "DELETE"]),
            ]:
                log(f"Q1d-{label}-rowcount-or-error", _rowcount(admin, privs))
                log(f"Q1d-{label}-committed", committed_assertion_outcome(admin, privs))

            # now the degenerate list against a BROKEN acl - does it still fail?
            admin.execute(f"REVOKE ALL ON harness.access_grant FROM {RUNTIME_ROLE}")
            admin.execute(f"GRANT SELECT ON harness.access_grant TO {RUNTIME_ROLE}")
            log("Q1d-BROKEN-acl-relacl", relacl(admin))
            log(
                "Q1d-BROKEN-acl-with-single-SELECT-list",
                committed_assertion_outcome(admin, ["SELECT"]),
            )
            log(
                "Q1d-BROKEN-acl-with-empty-list",
                committed_assertion_outcome(admin, []),
            )

            # ---- owner round-trip end to end, committed restore order ----
            admin.execute(
                f"REVOKE ALL ON harness.access_grant FROM {RUNTIME_ROLE}"
            )
            admin.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON harness.access_grant TO {RUNTIME_ROLE}"
            )
            pre = relacl(admin)
            admin.execute(f"ALTER TABLE harness.access_grant OWNER TO {RUNTIME_ROLE}")
            log("Q1f-broken-relacl", relacl(admin))
            admin.execute(f"ALTER TABLE harness.access_grant OWNER TO {OWNER_ROLE}")
            log("Q1f-after-owner-only-committed", committed_assertion_outcome(admin, _RUNTIME_DML))
            admin.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON harness.access_grant TO {RUNTIME_ROLE}"
            )
            post = relacl(admin)
            log("Q1f-after-full-restore-relacl", post)
            log("Q1f-byte-identical-to-pre", post == pre)
            log("Q1f-after-full-restore-committed", committed_assertion_outcome(admin, _RUNTIME_DML))


def _rowcount(admin, privs) -> object:
    try:
        return len(admin.execute("SELECT p FROM unnest(%s::text[]) AS p", (privs,)).fetchall())
    except Exception as exc:  # noqa: BLE001
        return f"RAISED {type(exc).__name__}"


if __name__ == "__main__":
    main()
```

## Closure

**This review does not close BUG-048 and does not alter its status.** I changed no
implementation, test, or governance file; I did not touch the bug record, either remediation
record, `REVIEW_IN_FLIGHT.md`, `CURRENT_STATE.md`, `CURRENT_HANDOFF.md`, `BUG_REGISTRY.md`, or
any governing baseline. No scenario promoted, no gate advanced, no capability registered.

**My recommendation to whoever decides closure:** round 1's R1 and R2 are genuinely closed —
R1 by measurement I took myself at both SQL and pytest level, R2 by reading the reconciled
records against what I measured. The committed fix is correct, the assertion is a true
all-four conjunction, it is fail-closed on every degenerate binding I could construct, and it
is load-bearing against the exact defect that survived its predecessor. Closure criterion 2 is
now met in strength, not merely in letter. **R2-1 and R2-2 are both P3 and neither should block
closure**; the cleanest disposition is to carry R2-1 alongside R3/R4/R5 and note that round 1's
`relacl`-entry alternative would close R2-1 and R5 together in one edit, which is the single
highest-value follow-up available in this file. R2-2 is a governance-tooling recommendation
independent of BUG-048 and belongs in its own charge.
