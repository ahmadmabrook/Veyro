---
doc: M1-C-07 CAP-011 LOCAL independent re-determination (B1-B3)
status: DETERMINATION RECORDED — LOCAL SCOPE APPROVED (bounded); CI SHAPE UNTOUCHED AND STILL BLOCKED
date: 2026-10-09
module: MOD-001
bounded-operation: M1-C-07
runner-operation: ccfbd38d-6937-4e7f-9af5-faf9711bd1c1
reviewer-role: veyro-security-reviewer (Opus assurance tier), fresh context
reviewer-model: claude-opus-5
authority: CAPABILITY_POLICY.md stage 4 (independent evaluation) + stage 5 evidence review
scope-of-this-record: CAP-011 (pytest 9.1.1) LOCAL narrow-scope determination only
not-this-record: Linux CI, required status checks, Veyro test-code review, workflow
  review, scenario outcomes, gate results, module certification, B4-B6
---

# CAP-011 (pytest 9.1.1) — LOCAL scope independent re-determination

## 0. Verdict, up front

| # | Question put to this review | Verdict |
|---|---|---|
| 1 | Narrowly scoped **LOCAL** invocation via the pinned wrapper `tools/run_scoped_pytest.py` (`626210e6…abb88cb`) on the four backend suites + the one idempotency-contract file | **APPROVED (bounded — see §4)** |
| 2 | Linux CI / required-status-check use | **not determined here; remains BLOCKED on B4-B6** |

B1, B2 and B3 are each **RESOLVED**, independently verified below. This record
grants no CI approval, no evidentiary reliance, and no approval of Veyro test code.
I make no registry edit and no self-grant; the orchestrator records the verdict.

## 1. Attestation and independence

- Fresh `veyro-security-reviewer` context, `claude-opus-5`, dispatched under runner
  operation `ccfbd38d-6937-4e7f-9af5-faf9711bd1c1`. No shared context with any
  implementation session (`d77d0542-…` draft row/stage-5 drill, `e44c73c5-…` wrapper
  candidate, `3e9f0b56-…` exact-runner drill, `3721b2d8-…` scope/pin reconciliation,
  or the Sonnet B1-B3 remediation session).
- **Claim honoured.** `REVIEW_IN_FLIGHT.md` `current_claim` reads `IN_FLIGHT` for this
  exact operation and this report path, dispatched `2026-10-09T18:05:43Z`, written
  before dispatch. I did not write, clear or edit the claim.
- **Did not run:** pytest (any tree, any invocation, not even `--plan`), the wrapper,
  pip, mypy, any scanner, any CI, any synthetic probe, any Veyro test,
  `validate_capabilities.py`. No file edited except this report. No registry, wrapper,
  test, claim, scenario or control byte touched.
- **Ran, read-only:** `shasum`, `git status`, `find`, `grep`, `sed`/`wc` source
  inspection.

## 2. Byte identity re-hashed this session (all four pins MATCH)

| Artifact | SHA-256 observed now | Pinned at dispatch | Git |
|---|---|---|---|
| `tools/run_scoped_pytest.py` | `626210e6f5c7385e7a4e7b1a07bfcf784494eb2fd014616f745da23f0abb88cb` | MATCH | untracked |
| `knowledge/00-System/CAPABILITY_REGISTRY.md` (whole file) | `6922821651ce405dd3a1b6903dc2abe56a4db62ef490feabfef16a2e489e991a` | MATCH | modified |
| B1B3 remediation record | `1ac31224b0611626b32765c06cd183fa61718a08126eb649bd19d99b69d577f1` | MATCH | untracked |
| `tools/tests/test_validate_idempotency_contract.py` | `f5d5fc135e1f4c880bfc04897829501967459c553ab9b718026f2f908a31d301` | MATCH | untracked |

Also re-hashed: `tools/validate_idempotency_contract.py` `3336e41c…e9f41c` and
`backend/pyproject.toml` `039332c9…40695` — both equal the values the remediation
record claims. No drift. This review is of this snapshot.

## 3. Independent dispositions

### B1 — environment containment misstatement: **RESOLVED** (permitted option (b))

Verified in source, not from the narrative: `INHERITED_ENV_VARS` (`:104`) contains
`HOME`, `TMPDIR`, `TMP`, `TEMP`, and `child_env` (`:258`) copies them verbatim. There
is no confinement anywhere in the file.

The registry `scope` cell now states exactly that — all four variables named,
"inherited VERBATIM", "the wrapper does NOT confine them" — and records the residual
that follows: test code under every allowlisted target runs with the caller's real
home and temp directories and can read and write them, and every prior drill's
containment came from the driver (`env -i`) rather than the artifact. The wrapper
docstring carries the same statement ("Environment honesty", `:49-57`). The normative
overclaim is gone; the only surviving occurrences of "confined" are a correctly
attributed quotation of the superseded wording in CAP-011's own correction note, and
CAP-012's separate mypy scope. The disposition is also empirically confirmed rather
than asserted: the remediation's C1 probe observed `HOME`/`TMPDIR` verbatim in the
grandchild processes and an injected non-allowlisted variable absent.

This is accurate, complete and explicit disclosure under the option the prior review
permitted ("acceptable if the residual is stated"). Resolved.

### B2 — symlink scan vs import closure: **RESOLVED** (permitted option)

The "the one way" overclaim is removed from the normative text (it survives only
inside the attributed correction note). The row and the wrapper docstring (`:38-47`)
now both state that the scan covers the collection target only, that the import
closure is outside it, that `-m` puts `backend` on `sys.path`, that the suites import
`backend/tests/harness/` and the conftest chain from outside every scanned directory,
that a symlinked or substituted module there would execute with no refusal, and that
this is an unclosed control gap rather than an observed breach.

I verified the factual substrate independently: 9 files under the allowlisted suites
import `tests.harness.*` (matching the prior reviewer's count), and
`backend/tests/integration/conftest.py` imports `tests.harness.authn`,
`tests.harness.postgres` and `tests.harness.tenant_isolation` at module scope.
`find backend/tests -type l` returns nothing, and each of the four suite directories
is symlink-free today. The description now matches the code. Resolved.

Residual severity, assessed: exploiting the unscanned closure requires write access to
the checkout, which the prior review already classified as an acceptable disclosed
limit in its TOCTOU/hardlink observation. The same reasoning covers a substituted
harness module. Disclosed limit, not a control failure for the local shape.

### B3 — the one novel target: **RESOLVED** (real-file positive and negative evidence)

The prior review permitted retention if backed by a read-only review of the real
file's bytes plus a drill against a copy of the real file, with the child-process
behaviour stated in the row. All three exist, and I re-derived the file's properties
from source rather than accepting them:

- 669 lines; SHA-256 equals the pinned real-file hash; **33 `def test_` functions**,
  which corroborates the drill's `33 passed` as a full, non-partial run.
- `sys.path.insert(0, <tools/>)` (`:100`) then imports `validate_idempotency_contract`
  — a hard supporting input, as the drill's N4 negative (absent module → rc 2
  collection error, not a pass) demonstrates.
- Exactly two `subprocess.run` call sites (`:454`, `:466`), consistent with the 7
  grandchildren observed (1 + a 6-iteration loop). Argv is chosen by the test, not the
  wrapper — correctly disclosed in the row.
- All five filesystem interactions are `tempfile.TemporaryDirectory`. No network, no
  `os.environ` mutation, no `rmtree`/`unlink`, no bare `open(`.
- The real supporting validator imports only `argparse, json, re, sys, dataclasses,
  pathlib, typing` — no `subprocess`, no `environ`, no network. Matches the claim.
- The negatives are discriminating, which is what makes the positive non-vacuous: N1
  (neutered validator) → rc 1 with `22 failed, 11 passed`, so the real tests actually
  detect a broken lint; N2 symlinked target → rc 2; N3/N3b ambient `PYTEST_ADDOPTS` /
  `PYTHONPATH` → rc 2; before/after tree hashes identical.

One delta between the drilled copy and a real local run, which I closed by direct
review rather than leaving open: the test resolves `REPO_ROOT`/`VALIDATOR_SCRIPT` from
its own location (`:117-118`), so in the Veyro checkout the grandchildren would execute
the **real** `tools/validate_idempotency_contract.py`. Those are the bytes I reviewed
above (`3336e41c…`), stdlib-only. Separately, that all 33 tests passed in a four-file
temp tree establishes the suite is hermetic — it reads no repository state — so the
copy drill is representative of a real-checkout run. Resolved.

## 4. Verdict 1 — LOCAL: **APPROVED**, bounded

The wrapper is the right instrument, its description now matches its behaviour, and
the one novel allowlist member has real-file positive and negative evidence. I
re-verified each of the prior review's affirmative control findings against the
current bytes: the caller cannot supply a path (closed `argparse` choice set plus a
second table lookup, `:326-328`, `:401-411`); canonicalisation is component-wise with
three independent containment assertions (`:182-205`); missing/empty suites and pytest
rc 4/5 are denials, with rc 1 kept distinct (`:208-232`, `:358-364`); ambient
`PYTEST_*`/`PYTHONPATH` are denied rather than stripped (`:235-253`); and the version
probe denies before any test runs (`:347-355`, `:379-389`). All four suite directories
are present, non-empty and symlink-free, and `backend/pyproject.toml` carries exactly
`testpaths = ["tests"]` with no `backend/conftest.py`, so the row's preconditions hold.

I did not treat the uncommitted state as a local blocker, and I am not changing that
criterion: a local run executes from the working tree by definition, so a commit pins
reviewed bytes for history but is not a precondition of the run — unlike a CI workflow,
which cannot execute uncommitted at all. **Recommended, not required:** commit the four
inputs so the approved bytes are pinned by history rather than by §2's hashes.

**What this approval authorises:** local execution of
`python tools/run_scoped_pytest.py <suite>` on the five allowlisted targets only, with
synthetic fixtures only, under the two disclosed residuals (verbatim `HOME`/`TMPDIR`;
unscanned import closure).

**What it does not authorise** — none of this follows from any sentence above: Linux
CI, any workflow run, any required status check (B4-B6 untouched and still blocking);
any GOV-01-R01/R04 gate result, scenario PASS or module certification; any evidentiary
reliance on a pytest result; the correctness or safety of the Veyro test code under the
four backend paths, which has had no independent review and whose review remains a
dependency the row itself names before reliance; CAP-012/mypy; any real member data,
real credential or production target. The four backend entries allowlist *paths*, not
reviewed bytes — the test code there changes, and this approval never covered it.

## 5. Non-blocking observations (recorded, not conditions)

1. **No skip guard in the wrapper.** `classify_exit` maps rc 0 to `EXIT_OK` labelled
   "all collected tests passed", and nothing inspects skips; `-rs` is printed but never
   parsed. An all-skipped run would therefore report success, and the label is
   literally untrue whenever anything skips. Not blocking today, because the engine
   dependency fails **closed** rather than skipping (`backend/tests/harness/postgres.py`
   raises `RuntimeError` on an absent or non-approved engine) and the four suites
   contain exactly one narrow in-body skip (`test_architecture_gate_rls.py:523`,
   `postgres_fdw` absent from the pinned image), with the contract layer carrying its
   own suppression guard. Worth closing before the CI shape, where the row notes the
   workflow — not the wrapper — holds the skip/`passed` denials.
2. **One real-file behaviour the remediation's inspection did not name:**
   `path.chmod(0o000)` / `chmod(0o600)` (`:420`, `:424`). Benign — a file the test
   creates inside its own `TemporaryDirectory`, restored in a `finally`, touching
   nothing pre-existing and nothing Veyro. Inside the already-disclosed
   tempfile-plus-verbatim-`TMPDIR` envelope, so it changes no disposition; recorded
   because B3's whole point was that this target had been unexamined.
3. **The row calls the wrapper "the byte-identical committed runner"** in the
   exact-artifact drill sentence; it is untracked. Historical-provenance wording, not a
   control claim, but it is the same registry-vs-reality pattern M1-C-07 was chartered
   to close.
4. **The docstring-only claim is not independently reproducible** — no pre-edit copy
   survives, so I could not diff `df0c857e…` myself. It is not load-bearing here: I
   reviewed the current bytes in full against the row and against each prior
   affirmative finding. The consistent +13-line offset at every landmark the prior
   review cited is consistent with a docstring-only insertion.
5. **Local runs still have no hash-enforced install** (`backend/.venv`, CPython 3.14.5,
   iniconfig 2.3.0 rather than the CI 3.13/2.3.1 set); the probe pins pytest's version
   string alone. Already disclosed in the row and measured by the iniconfig
   substitution control. Carried forward from the prior review as non-blocking.
6. **BUG-057 (pre-existing unregistered pytest use) remains OPEN** and is not cured
   here. Worth stating plainly that this grant improves that posture rather than
   worsening it: it replaces direct `pytest <path>` calls with a path-allowlisted,
   version-pinned, ambient-override-denying, zero-collection-fail-closed wrapper.

## 6. Precise next legal action

**Orchestrator:** record this LOCAL disposition in the durable files and set the
CAP-011 approval fields for the **local scope only**, exactly as bounded in §4 —
`review_status` must continue to show the CI shape as not approved, and must not read
as a whole-row APPROVED. Then clear the `REVIEW_IN_FLIGHT.md` claim per its own
protocol, on result recorded. I granted nothing and edited nothing.

**Unchanged by this record:** B4-B6 open and independently fatal to the CI shape; no CI
run authorised; no workflow approved; no gate, scenario or module dependency satisfied;
Veyro test-code review still outstanding; BUG-057 OPEN; MOD-001 certification status,
WIP=1 and the four owner-reserved restrictions untouched.
