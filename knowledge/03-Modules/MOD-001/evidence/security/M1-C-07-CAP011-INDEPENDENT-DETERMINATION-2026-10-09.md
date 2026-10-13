---
doc: M1-C-07 CAP-011 independent capability-security determination
status: DETERMINATION RECORDED — BOTH VERDICTS BLOCKED (no approval granted)
date: 2026-10-09
module: MOD-001
bounded-operation: M1-C-07
runner-operation: 16a4c985-397c-4158-b3d0-7fe3071ecee0
subgoal: M1-C-07-CAP011-INDEPENDENT-DECISION
reviewer-role: veyro-security-reviewer (Opus assurance tier), fresh context
reviewer-model: claude-opus-5
authority: CAPABILITY_POLICY.md stage 4 (independent evaluation) + stage 5 evidence
  review; M1-C-07 GOV-01-R01/R02; DEVELOPMENT_CONSTITUTION model routing
scope-of-this-record: CAP-011 (pytest 9.1.1) capability-security determination only
not-this-record: gate-3, F14, SCN-070, module certification, confidence review,
  Veyro test-code review, CI result, scenario promotion
---

# CAP-011 (pytest 9.1.1) — independent capability-security determination

## 0. Verdicts, up front

| # | Question put to this review | Verdict |
|---|---|---|
| 1 | Narrowly scoped **local** Veyro-test invocation via the exact pinned wrapper `tools/run_scoped_pytest.py` (`df0c857e…3d85d`) | **BLOCKED** |
| 2 | **Linux CI / required-status-check** use via `.github/workflows/test-pyramid.yml` (`ad9fc364…7cdd3`) | **BLOCKED** |

Neither verdict is `REJECTED`. Nothing found here is unsalvageable: the wrapper's
design is the right design for this boundary, and the synthetic evidence behind it
is unusually honest and non-vacuous. Both verdicts are `BLOCKED` on a small, named,
implementer-reachable dependency set (§5, §6). No owner approval is required to
clear any of it.

`approved_by` is **not** assigned and `review_status` is **not** advanced by this
record. CAP-011 remains `QUALIFIED — NOT APPROVED`, `lifecycle_status` not ACTIVE.
No conditional, partial or implied approval is granted by any sentence in this file.

## 1. Independence, session, and what this reviewer did and did not do

- **Reviewer operation** `16a4c985-397c-4158-b3d0-7fe3071ecee0`, fresh
  `veyro-security-reviewer` context, `claude-opus-5`. Distinct from every
  operation that produced the material under review:
  `d77d0542-…` (Sonnet, stage-5 drill + draft row), `7fa75e8b-…` (target-scope
  analogue), `e44c73c5-…` (wrapper/workflow candidate), `3e9f0b56-…` (exact-runner
  drill), `3721b2d8-…` (`ARCHITECTURE_CRITICAL`, claude-opus-5 — scope/pin
  reconciliation and the registry edit). No shared context with any of them.
- `CAPABILITY_POLICY.md`'s routing clause requires an **Opus assurance role in a
  fresh context**, reviewing implementer-produced evidence and *not* re-running the
  tests. It does not require a different base model. Operation `3721b2d8-…` also ran
  on `claude-opus-5` in an `ARCHITECTURE_CRITICAL` implementation role; the
  separation relied on here is role + fresh context, stated plainly so nobody later
  mistakes it for model diversity.
- **Global claim honoured.** `REVIEW_IN_FLIGHT.md` `current_claim` reads
  `IN_FLIGHT` for this exact determination, naming this operation id and this report
  path, timestamped `2026-10-09T17:48:43Z` — written by the orchestrator before
  dispatch, as the protocol requires. This reviewer did not write, clear or edit the
  claim.
- **Ran, read-only:** `verify_baselines.py` (**PASS**, 4/4 governing baseline hashes
  and 4/4 identity strings match `PROJECT_INDEX.md`), `validate_capabilities.py`
  (**FAIL, 6 errors** — the six intended CAP-011/CAP-012 fail-closed holds and
  nothing else; the hold is real, live, and not merely asserted in prose), `shasum`
  over the artifacts, `git ls-files`/`git status`, and targeted `grep`/`find`
  inspection.
- **Did not run:** pytest (any invocation, any tree), pip, any scanner, any Veyro
  test, any CI, any qualification drill, the wrapper itself (not even `--plan`). No
  file was edited except this report. No registry, manifest, scenario, control or
  review-claim byte was touched.

## 2. Byte identity verified this session

Every artifact was re-hashed independently rather than trusted from the evidence.

| Artifact | SHA-256 observed now | Matches implementer claim | Git state |
|---|---|---|---|
| `tools/run_scoped_pytest.py` | `df0c857e208e8a74550d1a0331dd783c152970d85e749a5b970f5fc56713d85d` | yes | **untracked** |
| `.github/workflows/test-pyramid.yml` | `ad9fc36441434ff961940c2b2033c473d9a83db5f1cf12af7b28824626a7cdd3` | yes | **untracked** |
| `backend/requirements-typecheck-linux-x86_64-cp313.lock.txt` | `5e7596d408190a6103ffe1e3988f1c88ea33a34306302cc7de6f0570340e95de` | yes | **untracked** |
| `backend/requirements-dev.lock.txt` | `5b9383fe128cb1d7d8b8442c82fe305988980915140215f4a4f5e3adcbe2d698` | yes | **untracked** |
| `tools/tests/test_validate_idempotency_contract.py` (the one extra target) | `f5d5fc135e1f4c880bfc04897829501967459c553ab9b718026f2f908a31d301` | yes (equals the "real file" hash the drill names) | **untracked** |
| `backend/pyproject.toml` | — | `[tool.pytest.ini_options]` holds exactly `testpaths = ["tests"]`, as the row claims | tracked |

Also verified independently: no root `pyproject.toml`, `pytest.ini`, `tox.ini`,
`setup.cfg` or `conftest.py` at `.`, `tools/` or `tools/tests/` (root carries only
`ruff.toml`, which is not a pytest config source), so the row's `--confcutdir`
precondition for the extra target holds today. No symlink anywhere under
`backend/tests` (`find -type l` → none). HEAD is `e481b81`; the registry carries
unrelated dirty changes, as disclosed.

**Nothing under review is committed.** Six of the seven artifacts above are
untracked working-tree files. The hashes are therefore point-in-time observations by
this reviewer, not reviewable pins in history.

## 3. What the implementer got right (stated so the blockers are not read as a rejection of the design)

These are affirmative findings, verified against source rather than taken from the
evidence narrative:

1. **The caller genuinely cannot supply a path.** `argparse` `choices=sorted(SUITES)`
   plus a second `SUITES.get()` table lookup; every path in the argv is a
   repository-relative literal in the frozen `SUITES` table
   (`tools/run_scoped_pytest.py:122-166`). This is the correct response to the
   target-scope drill's §4.1 finding that `--rootdir`/`--confcutdir` do not bound an
   explicit path argument. No flag, env var or marker file can add a target.
2. **Canonicalisation is component-wise, not `resolve()`-and-hope.** `_canonical`
   (`:169-192`) refuses `""`, `.`, `..` and absolute components, walks down checking
   `is_symlink()` at each step, then independently asserts `resolved == current` and
   `root in resolved.parents`. Three statements, each sufficient alone, which is the
   right posture for a containment check.
3. **Zero-collection and path-error cannot read as success.** `_assert_suite_usable`
   refuses a missing/empty suite before pytest starts, and `classify_exit` (`:345`)
   maps every rc other than 0 and 1 to `EXIT_DENIED` — so rc 4 and rc 5, the two
   fail-open shapes the drill found, are denials. rc 1 is kept distinct from a
   denial, which is the correct distinction and is explicitly exercised (N1 vs N2–N8).
4. **Ambient overrides are denied, not stripped.** `ambient_denials` (`:222-240`)
   refuses any inherited `PYTEST_*` and any non-empty `PYTHONPATH`, including
   `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` arriving from outside. Refusing rather than
   silently normalising is the right call and the reasoning in the docstring is sound.
5. **The version pin is load-bearing, not documentary.** The `--version` probe runs
   before the suite and denies on mismatch (`:334-342`, `:366-376`), and negative
   case N8 observed exactly that: pytest 9.1.0 substituted for 9.1.1 → rc 2, no test
   executed. Without N8 the pin would have been a comment; with it, it is a control.
6. **The synthetic evidence is non-vacuous by construction.** The target-scope
   analogue's G1–G4 controls each relax one isolation knob and show the decoy
   ancestor conftest, decoy ini, `PYTEST_ADDOPTS` and a `PYTHONPATH` `pytest11`
   entry-point plugin all *do* take effect when permitted — so the governed runs'
   "not loaded" results mean something. This is the part of the evidence I would most
   want to see and it is present.
7. **The exact-artifact drill is the right drill.** Five wheels installed by hash
   into a disposable CPython **3.13.13** venv (CI's asserted minor version), the
   byte-identical committed runner copied in and re-hashed in place, three-way
   hash agreement (local == lock == PyPI digest) on all five, 5/5 positive and 9/9
   negative. The iniconfig 2.3.1-vs-2.3.0 divergence was measured rather than
   waved at, and the honest consequence — the probe pins pytest alone, so closure
   drift is caught only by the hash-enforced install — was recorded rather than
   buried.
8. **Workflow hygiene.** `test-pyramid.yml` has **zero** `uses:` lines (verified) and
   **zero** `secrets.` references, `permissions: {}`, tokenless pinned-SHA git fetch
   with 40-hex and owner/repo validation, untrusted values reaching shell only via
   `env:`, `--require-hashes --only-binary=:all: --no-deps` with `PIP_*` unset and
   `PIP_CONFIG_FILE=/dev/null`, no unpinned fallback. This satisfies `iac.md`
   control 5 by construction (no action to qualify) and is the correct pattern.
9. **Honesty is consistent across all four evidence records**, including a
   self-reported near-miss (the scripted registry edit that damaged CAP-009/CAP-010
   rows and was caught by the project's own validator, then reconciled to an exact
   pre-dispatch full-registry hash). Disclosing that strengthens rather than weakens
   the evidence set.

## 4. Blocking findings

### B1 — The scope cell misstates the wrapper's own environment containment (blocks verdict 1 and 2)

The CAP-011 `scope` cell states the invocation shape as "a clean environment (any
inherited `PYTEST_*` and a non-empty `PYTHONPATH` are **denied**, not stripped;
**`HOME`/`TMPDIR` confined**; `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`; child env built
from an 8-name allowlist)".

The committed wrapper does **not** confine `HOME` or `TMPDIR`. It passes them
through verbatim:

```
INHERITED_ENV_VARS = ("PATH", "HOME", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "TZ")   # :91
child = {name: env[name] for name in INHERITED_ENV_VARS if name in env}                  # :245
```

`child_env` copies the ambient values of all four of `HOME`, `TMPDIR`, `TMP`, `TEMP`
into the pytest child. The confinement the row describes came from the **drill
driver**, not the artifact: the reconciliation record states each case ran under
`env -i` with a temporary `HOME` and `TMPDIR`, and the exact-runner drill says the
same. So:

- the normative scope text is factually wrong about a control for the exact artifact
  it governs, and
- every positive and negative result in the evidence set was obtained under a
  containment the wrapper itself does not establish. A real local run writes with the
  developer's real `HOME` and real `TMPDIR`.

pytest-level exposure from this is low (`-s` drops user site-packages, so no
`~/.local` `pytest11` plugin can load; `-p no:cacheprovider` stops cache writes;
pytest reads no user-level config). The exposure that matters is the **test code**,
which runs with the real home directory. Given that the suites' code is itself
unreviewed (§4.3, §4.4), this is not a cosmetic wording defect — it is the
difference between the shape that was drilled and the shape that would run.

This is the same defect class M1-C-07 was chartered to close (a row describing
something other than what the artifacts do). Two instances were closed; this is a
third, in the same cell, and it was not detected by the reconciliation.

### B2 — The symlink control bounds collection targets, not the import closure (blocks verdict 1 and 2)

`_assert_suite_usable` scans only the suite directory itself, and the scope cell
generalises that to: "a symlinked test or subdirectory is the one way an allowlisted
path can still execute code from outside the tree."

That is not correct. For the four backend suites the argv is
`python -E -s -B -m pytest …`, and `-m` prepends the cwd — `backend` — to
`sys.path`. The suites import from `backend/tests/harness/`, which lies **outside
all four allowlisted suite directories and outside the symlink scan**. Verified: 9
collected files across `backend/tests/unit` and `backend/tests/integration` import
`tests.harness.*`, and `backend/tests/integration/conftest.py` imports
`tests.harness.authn`, `tests.harness.postgres` and `tests.harness.tenant_isolation`
at module scope. A symlinked or substituted module under `backend/tests/harness/`
would execute with no refusal of any kind.

Today this is a control gap, not a live breach: `find backend/tests -type l` returns
nothing, so no symlink exists anywhere in the tree right now. But the row asserts a
boundary stronger than the code enforces, and the import closure is a wider surface
than the collection target — which is precisely the kind of overstatement that stops
being harmless the moment someone relies on the sentence.

### B3 — The one extra target is both unexamined and not inert (blocks verdict 1 and 2)

Adding `tools/tests/test_validate_idempotency_contract.py` to the allowlist is the
*novel* part of this scope extension — the four backend layers were already the
drafted scope. The evidence for the novel part is:

- the exact-artifact drill deliberately placed a **synthetic stand-in** at that path
  (`f9fcb785…ca882`), not the real file (`f5d5fc13…1d301`), and says so;
- so there is **zero behavioural evidence** about the file whose addition is the
  thing being authorised. §6.4 of the reconciliation states this plainly, to its
  credit.

Independently inspected this session, the real file is not an assert-only fixture:
it calls `subprocess.run(...)` at least twice (lines ~454, ~466) to drive the lint's
`main()` as a child process. That means the allowlisted target **spawns further
processes**, which inherit the wrapper's allowlisted environment — including, per
B1, the real `HOME` — and whose argv the wrapper does not govern in any way. The
wrapper's containment claims end at the pytest process; this target steps past that
edge by design.

A scope extension whose only new member has no behavioural evidence, is not
committed, and spawns child processes is not a scope extension an independent
reviewer can approve on this evidence.

### B4 — No CI execution of any kind, and the workflow is not committed (blocks verdict 2, independently and fatally)

1. `test-pyramid.yml` is **untracked**. A `pull_request`-triggered workflow runs from
   the repository; an uncommitted workflow cannot execute at all, and `iac.md`
   control 1 is explicit that no `.github/workflows/**` change takes effect anywhere
   before it lands as a reviewed commit.
2. **No run has ever occurred.** The hash-enforced install, the 3.13 interpreter
   assertion and candidate search, the `PIP_*` scrub, the skip/`passed` grep denials,
   and the `PIPESTATUS` handling are all correct **by construction only**. Under
   `CAPABILITY_POLICY.md` stage 5 the capability needs a recorded positive **and**
   negative result for the shape in which it will be used; the CI shape has neither.
3. **No linux-x86_64 execution.** `sysconfig.get_platform()` during the drill was
   `macosx-26.0-arm64`, and `tools/assert_ci_python313.py` would correctly deny on
   that host. Platform equivalence rests on the `py3-none-any` wheel tags — a sound
   argument, but an argument, not an observation. The CI micro version of 3.13 is
   unknown.
4. **This review is not a workflow review.** I examined `test-pyramid.yml` only as
   it bears on CAP-011's invocation containment. It has had no independent
   code/config review of its own, and this record is explicitly not that review, not
   gate-3, not F14 and not SCN-070.

### B5 — The CI artifact set the row describes is not the artifact set CI installs (blocks verdict 2)

The `content_hash` cell establishes the exact artifact set as "five closure
artifacts… all single pure-Python `py3-none-any` wheels… each lock hash names
exactly one platform-independent artifact". That is true of the five, and the
three-way verification behind it is good work.

It is not, however, a description of the environment a CI pytest run would execute
in. All three pytest-running jobs install with `-r "$lock"` — the **whole** 14-entry
lock. Read directly, that lock also installs `mypy==2.3.1`, `ast-serialize==0.11.2`,
`librt==0.15.0`, `mypy-extensions`, `pathspec`, `typing-extensions`,
`psycopg==3.3.6` and `psycopg-binary==3.3.6`. Consequences:

- A CAP-011 pytest run in CI would execute inside a venv that also contains
  **CAP-012's entire artifact set** (`mypy`, itself `QUALIFIED — NOT APPROVED`), plus
  four platform-specific **compiled** wheels. The CAP-012 row itself records that for
  its compiled wheels "which platform artifact each lock hash names is unverified."
- Mitigations are real and should be credited: `--require-hashes` means pip installs
  only bytes matching the pin or fails closed, and `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`
  means a `pytest11` entry point in any of those distributions cannot load. The
  residual is provenance of the extra compiled wheels, not substitution.
- `psycopg` is genuinely needed by the integration layer, so the broad install is not
  a mistake — but the row must describe the set it actually installs before a CI
  determination can rest on it. Together with B1 and B2 this is the **third and
  fourth** instance of the same registry-vs-artifact divergence pattern, which is
  itself a finding about the row's reliability, not just about four sentences.

### B6 — One of four CI matrix layers cannot pass, so "required status check" is not yet a coherent ask (blocks verdict 2)

The row and the workflow both state that `backend-integration` is expected to
**deny** on a GitHub ubuntu runner: CAP-008's disposable-Postgres fixture is pinned
to the local Colima engine (verified — `backend/tests/integration/conftest.py` opens
with `disposable_postgres()` from `tests.harness.postgres`, and CAP-008's registry
row pins Colima 0.10.3 / Lima 2.2.0 / a digest-pinned `postgres:16-alpine`). The
workflow is honest about this and deliberately does not fake a Linux route.

Designating `test-pyramid` as a required status check in that state would either
hold the required check permanently red or create pressure to improvise an
unqualified Linux Postgres route. Separately, the `regression` job's observed local
result is FAIL (correctly — it fails *because* CAP-011/CAP-012 are not approved),
which is circular until this determination resolves. Required-status designation
additionally needs GOV-01-R04 non-bypassability evidence, which cannot exist for a
workflow that has never run.

### Non-blocking observations (recorded, not conditions)

- **Local runs have no hash-enforced install at all.** Locally the interpreter would
  be `backend/.venv/bin/python` (Python 3.14.5, iniconfig **2.3.0**), not the pinned
  CI closure. The probe pins pytest's version string only; the row already concedes
  the installed tree "is not proven to come from the pinned wheel." The iniconfig
  substitution control gives reasonable comfort that this divergence is not
  behaviour-affecting for the drilled cases. Worth stating in the row's local-scope
  sentence; not independently blocking.
- **TOCTOU between the symlink scan and pytest start** is inherent and acceptable:
  anyone able to win that race already has write access to the checkout. Hardlinks
  are likewise not detectable by the scan and likewise require write access. Note as
  disclosed limits, do not engineer against them.
- **`classify_version` concatenates stdout and stderr** before an exact string
  compare, so any extra byte on either stream denies. That is the correct direction
  (fail closed) and N8 confirms the mechanism works on the pinned artifact.
- **`tools/tests/.pytest_cache/` and `tools/tests/__pycache__/` exist on disk** —
  artefacts of the pre-existing unregistered pytest use already disclosed under
  BUG-057 (OPEN, P1 proposed). Not created by anything under review; `-p
  no:cacheprovider` prevents the governed shape from adding to them.
- **The wrapper's own tests cannot run through the wrapper**, since `tools/tests` is
  not an allowlisted directory. Correct and deliberate; noted so nobody "fixes" it by
  widening the allowlist to the directory.

## 5. Verdict 1 — local, narrowly scoped Veyro-test invocation: **BLOCKED**

The wrapper is the right instrument and I would expect it to clear review once the
row describes it accurately and the one novel target has evidence. It cannot clear
review now, because approving verdict 1 would mean approving a `scope` cell that
misstates two of the controls it relies on (B1, B2) and a five-entry allowlist whose
only new member has no behavioural evidence and is not inert (B3).

**Exact minimum dependency set for verdict 1** — all four are implementer-reachable;
none needs owner approval:

1. **Resolve B1 one way or the other, not both and not partially.** Either (a) make
   the wrapper actually confine `HOME`/`TMPDIR` (and `TMP`/`TEMP`) to a disposable
   per-run location and re-run the exact-artifact positive/negative set in that
   shape, or (b) correct the `scope` cell to state that `HOME`, `TMPDIR`, `TMP` and
   `TEMP` are inherited verbatim from the invoking environment, and record the
   residual that follows. (a) is the stronger fix and is a small change; (b) is
   acceptable if the residual is stated.
2. **Resolve B2:** either extend the symlink scan to the whole import closure the
   suites reach under cwd (at minimum `backend/tests/**`, which covers
   `backend/tests/harness/`), or correct the `scope` cell's "the one way" sentence to
   name the import closure as outside the scan. Again one or the other, explicitly.
3. **Resolve B3:** either drop `idempotency-contract` from the bounded local grant
   (leaving the four backend layers as the drafted scope always was), or produce
   evidence about the **real** file — a read-only review of its actual bytes plus a
   drill run against a copy of the real file rather than an `assert True` stand-in —
   and state in the row that the target spawns child processes outside the wrapper's
   environment control.
4. **Re-dispatch a fresh independent determination** against the corrected row and
   artifacts, with a new `REVIEW_IN_FLIGHT.md` claim written before dispatch. This
   record is spent; it cannot be re-read as an approval of a later, different row.

Recommended but **not** a condition of verdict 1: commit the artifacts, so the
reviewed bytes are pinned by history rather than by a working-tree hash observed in
§2. (For verdict 2 this is a hard condition — see B4.)

## 6. Verdict 2 — Linux CI and required-status use: **BLOCKED**

Three of the blockers here are independently fatal and cannot be closed by any
amount of registry editing: the workflow is not committed (B4.1), no CI run of any
kind exists (B4.2), and no linux-x86_64 execution has ever been observed (B4.3).
Under `CAPABILITY_POLICY.md` stage 5 that is a missing qualification, not a
paperwork gap.

**Exact minimum dependency set for verdict 2:**

1. Everything in §5 (the wrapper's containment and the extra target are the same
   wrapper and the same target in CI).
2. **Commit** `test-pyramid.yml`, `tools/run_scoped_pytest.py`, the Linux cp313 lock,
   `tools/assert_ci_python313.py`, the lint, its declaration and the extra target —
   `iac.md` control 1 requires a reviewed commit before a workflow change takes
   effect anywhere.
3. **An independent code/config review of `test-pyramid.yml` in its own right.** This
   record is not it.
4. **A real run on a real linux-x86_64 CPython 3.13 GitHub runner**, with the
   hash-enforced install observed to succeed and at least one deliberate negative
   (e.g. a mutated lock hash, or a substituted pytest version) observed to deny. The
   pin is correct by construction; CI has never demonstrated that it holds.
5. **Correct the artifact-set statement (B5)** to describe the whole 14-entry lock
   the workflow installs, naming the CAP-012 and compiled-wheel overlap and the
   mitigations (`--require-hashes`, autoload disabled) rather than describing a
   five-wheel closure as if it were the runtime environment.
6. **Resolve B6 before any required-status designation:** either qualify a Linux
   Postgres route for `backend-integration`, or explicitly exclude that layer from
   the CI grant and from the required-check set. Do not designate a required status
   check while a matrix layer is known to deny.
7. Only then: a fresh independent determination for the CI shape, separately from the
   local one. The two shapes have different evidence and should not be granted
   together on one record.

## 7. Precise next legal action

**For the implementer (no owner approval needed):** close §5 items 1–3 as a single
bounded remediation — pick (a) or (b) for B1, pick one resolution for B2, pick one
resolution for B3 — record the choices and any re-drill as new evidence, and correct
the CAP-011 `scope` cell to match the artifacts exactly. Do **not** advance
`review_status`, `approved_by`, `approved_date` or `next_review_due`; those remain
for an independent determination. Do not run pytest on any Veyro path, and do not
push or run `test-pyramid.yml`, in the course of that remediation.

**For the orchestrator:** record this determination's disposition in the durable
files, then clear the `REVIEW_IN_FLIGHT.md` claim per its own protocol — on *result
recorded*, not on this agent's exit. The next review round for CAP-011 is a fresh
`veyro-security-reviewer` determination against the corrected row, claimed before
dispatch.

**Unchanged by this record:** CAP-011 `QUALIFIED — NOT APPROVED`, `lifecycle_status`
not ACTIVE, `approved_by` unset. `validate_capabilities.py` continues to report the
six intended fail-closed holds (verified live this session), and
`tools/validate_capability_manifest.py`'s equivalent holds stand. No gate, no
scenario, no module dependency is satisfied. No pytest run on any Veyro path is
authorised. No CI run is authorised. MOD-001 certification status, WIP=1 and the four
owner-reserved restrictions are untouched. BUG-057 remains OPEN and is not cured
here.
