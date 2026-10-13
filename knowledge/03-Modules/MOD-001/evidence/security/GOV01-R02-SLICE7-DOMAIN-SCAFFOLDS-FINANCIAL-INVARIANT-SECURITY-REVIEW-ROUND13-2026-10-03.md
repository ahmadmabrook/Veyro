---
doc: GOV-01-R02 Slice-7 domain scaffolds + financial-invariant harness — INDEPENDENT SECURITY RE-REVIEW, ROUND 13
module: MOD-001
scenarios: SCN-MOD001-132, SCN-MOD001-133
bug: BUG-050 (OPEN)
round: 13
date: 2026-10-03
verdict: BLOCKED — P0=0 / P1=0 / P2=1 / P3=1
reviewer: veyro-security-reviewer (fresh context, agentId `a0dbc9135bcee9227`; did not implement, code-review, or security-review any prior round of this slice, and did not author any round-12 remediation text)
model_proof: §1 of this file — directly observed facts only. This reviewer deliberately did **not** run `mr_verify.py` against its own transcript; per the dispatching charge, the orchestrating session performs that check externally.
scope: review-only. No source file edited, no commit, no push, no scenario promoted, no bug closed, `REVIEW_IN_FLIGHT.md` not touched. This file is the only file written.
---

# Round-13 independent security re-review — GOV-01-R02 Slice 7

## 0. Charge and what was actually done

Charge: (i) verify the R12-1 / R12-2 / R12-3 corrections for **accuracy, not
presence**, by reading the current text at each named location; (ii)
independently reconstruct `T6+G1c`, `T6+G2s`, `T6+G3s`, `T6+G4s` from round
12's prose and re-run the plain `T6+G7` / `T6+G8` / `T6+G8b` compositions to
confirm NR11-1 / R11b-1's fix has not regressed; (iii) re-run the six-token
derivation query and reconcile its count; (iv) assess BUG-050 and
SCN-MOD001-132 / 133's acceptance criteria against current code; (v) avoid a
gratuitous re-review loop — report a clean-of-product-defects verdict plainly
if that is what the evidence shows; (vi) review the live tree with the same
rigor as prior rounds (full suite, `ruff`, mypy strict).

Everything below was executed this session. Every finding carries an exact
command and its exact observed output. All mutation work ran in `/tmp/r13/`
and all live-Postgres drills in a throwaway `rsync` copy at `/tmp/r13be/`
(since removed); the real tree was never mutated (§8).

Taxonomy was reconstructed from prose, not copied from any prior round's
scratch code. The generator script is `/tmp/r13/gen.py` (throwaway):

- **T6** — `ctx.prec = 27` inserted alongside the `Inexact` trap inside
  `assert_debits_equal_credits`' `localcontext()`.
- **G7** — swap `_COMPARISON_MATCH` / `_PRECISION_MATCH` at the boundary
  test's single `pytest.raises` call site.
- **G8** — truncate `_COMPARISON_MATCH` from `r"^DEBITS_NE_CREDITS"` to
  `r"^D"` at its definition.
- **G8b** — the same truncation as a late rebind after the constant block.
- **G1c** — local rebind of `_COMPARISON_MATCH` inside the boundary test
  function.
- **G2 / G3 / G4** — `from pytest import raises`; `match` passed via
  `**{"match": ...}` unpacking; module alias `import pytest as pt` →
  `pt.raises(...)`. Suffix `s` = decoy **co-located** in the same enclosing
  test function; no suffix = decoy in a **new** test function.

## 1. Session and model identity

### 1.1 Directly observed facts

| Item | Value |
|---|---|
| Agent type | `veyro-security-reviewer` |
| agentId | `a0dbc9135bcee9227` (distinct from every prior recorded reviewer agentId: round 11 `af75f1199b8cc03bf`, round 11B `a4858d8fc935f0a35`, round 12 `aa3d6319bcb6991a6`) |
| Parent session id | `586640ef-129e-44ab-93d9-e873e0a2dbff` |
| Transcript path | `/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/586640ef-129e-44ab-93d9-e873e0a2dbff/subagents/agent-a0dbc9135bcee9227.jsonl` |
| `.meta.json` contents (verbatim) | `{"agentType":"veyro-security-reviewer","description":"MOD-001 BUG-050 round-13 independent security review","toolUseId":"toolu_01ScnPAXbtgmMfC2zw4dzafM","spawnDepth":1,"requestShape":"background","requestNonInteractive":true}` |
| Harness-declared model | `Opus 5`, exact id `claude-opus-5` (stated in this session's runtime environment block) |
| Model rows observed in own transcript | `grep -o '"model":"[^"]*"' … \| sort -u` → `"model":"claude-opus-5"` (single distinct value) |
| Spawn depth | 1 |

Identity was established by reading this reviewer's own `.meta.json` and
confirming the transcript file was the only one being actively written under
the parent session's `subagents/` directory at dispatch time, and that its
first row carries this round's dispatch text (`"round 13"`) and
`agentId: "a0dbc9135bcee9227"`.

### 1.2 Deliberate non-self-attestation

Round 12's §1.2 disclosed that it had self-attested via `mr_verify.py` and
recorded orchestrator re-attestation as a required follow-up; that follow-up
was performed and is recorded (`CURRENT_STATE.md:4`: PASS 85/85
`claude-opus-5`).

This round takes the cleaner path the charge directed: **this reviewer did not
run `mr_verify.py` against its own transcript and makes no model-assurance
PASS claim about itself.** The facts in §1.1 are what an external check needs.
The orchestrating session should run:

```
backend/.venv/bin/python knowledge/05-QA/tools/mr_verify.py \
  ~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/586640ef-129e-44ab-93d9-e873e0a2dbff/subagents/agent-a0dbc9135bcee9227.jsonl \
  opus veyro-security-reviewer
```

and record the resulting verdict and turn count. Note that `.meta.json` for
this round does **not** carry the explicit `"model":"opus"` key round 12's
did — the transcript's own per-row `model` field is the signal here.

**Provider/model-assurance failure? No.** No provider limit, model fallback,
`<synthetic>` row, or interruption occurred. This is **not**
`BLOCKED: MODEL_ASSURANCE_UNVERIFIED`.

### 1.3 R12-5's claim mechanism was honored before this dispatch

`knowledge/00-System/REVIEW_IN_FLIGHT.md` front matter, read this session:

```
current_claim: IN_FLIGHT — BUG-050 round 13, claimed by watchdog cron
66643874-e295-4d53-a846-ee79cb6c3a44, dispatched 2026-10-03T19:34:00+00:00.
Expected subagent: veyro-security-reviewer (fresh Opus). Clear on result
recorded, not merely on subagent completion.
```

The claim names this exact round and expected agent type and was written
before dispatch, and `SESSION_BOOTSTRAP.md:83` carries the corresponding §4
step requiring it be read and honored. **R12-5's process fix is in place and
was actually used.** Clearing the claim is the orchestrating session's action,
not this reviewer's, and this reviewer did not edit the file.

## 2. Verdict

**BLOCKED — P0=0 / P1=0 / P2=1 / P3=1.**

**Zero false cleans in `assert_debits_equal_credits` — the ninth consecutive
round** — across 19 reconstructed mutants/compositions, a 35,000-case
differential fuzz against an exact `Fraction` oracle on two independently
written generators, a direct non-suite module-load probe, and 4 live
SCN-132 drills against a real disposable Postgres.

**No finding is a product defect.** `assert_debits_equal_credits` is
unchanged, unregressed, and correct on every case tested. NR11-1 / R11b-1's
structural fix has **not** regressed. R12-3 is genuinely and accurately fixed.
Both scenarios' acceptance criteria as written are **MET** on current code.

The single P2 is that **R12-1's and R12-2's corrections are themselves
factually wrong about one of the four gaps** — they replaced a false claim
with a differently false claim, which is precisely the failure mode this
round was dispatched to detect. BUG-050 is therefore **not closeable this
round** and SCN-MOD001-133 should **not** be promoted this round. §4.1 gives
the exact corrected wording so round 14 need not be another discovery round.

## 3. Round-12 remediation — verified against current text and executable reality

### 3.1 R12-3 (module-alias gap added to the authoritative docstring) — **REMEDIATED, and accurate**

`test_financial_invariant_scaffold.py:331-337` now discloses a fourth gap
verbatim: the check "does not see a call reached through a module alias such
as `import pytest as pt; pt.raises(...)` (only the literal name `pytest` is
matched; disclosed 2026-10-03, round 12, R12-3 …)".

Verified true on both halves. By code: the walker at lines 389-391 requires
`isinstance(func, ast.Attribute) and func.attr == "raises"` **and**
`isinstance(func.value, ast.Name) and func.value.id == "pytest"`, so `pt` is
invisible to it. By execution: `t6_g4s` is a fully green 22-passed suite
(§4.2 table). The disclosed-gap list is now complete at four for every shape
this reviewer could reach. **Accurate, not merely present.**

Also re-confirmed, so round 14 need not re-derive it: the walker tests
`isinstance(function, ast.FunctionDef)`, excluding `ast.AsyncFunctionDef`, so
a `match=` site inside an `async def test_…` is invisible to it — but
`pytest 9.1.1` is installed with **no** asyncio plugin
(`pip list | grep -i -E "asyncio|anyio"` → empty), so an async test cannot
run here and the shape is not a reachable escape. It would become one if
`pytest-asyncio` were ever added.

### 3.2 NR11-1 / R11b-1 — **still fixed, no regression**

All eight core mutants rebuilt from prose in `/tmp/r13/` and run with
`backend/.venv/bin/python -m pytest -q <mutant>.py`:

| Mutant | Observed | Killing test |
|---|---|---|
| `base` (unmutated copy, SHA-256 `5577fafd…`) | **22 passed**, exit 0 | — |
| `t6` | **1 failed, 21 passed**, exit 1 | `test_precision_boundary_within_context_still_compares_exactly` |
| `g7` | **2 failed, 20 passed**, exit 1 | boundary test + `test_match_assertions_use_only_the_shared_constants` |
| `g8` | **1 failed, 21 passed**, exit 1 | `test_all_match_assertions_are_anchored` |
| `g8b` | **1 failed, 21 passed**, exit 1 | `test_all_match_assertions_are_anchored` |
| `g1c` | **22 passed**, exit 0 | — (behaviourally inert without T6) |
| **`t6_g7`** | **1 failed, 21 passed**, exit 1 | `test_match_assertions_use_only_the_shared_constants` |
| **`t6_g8`** | **1 failed, 21 passed**, exit 1 | `test_all_match_assertions_are_anchored` |
| **`t6_g8b`** | **1 failed, 21 passed**, exit 1 | `test_all_match_assertions_are_anchored` |

Identical to round 12's table in every cell, including which specific
assertion carries each kill. The round-11 structural fix is intact; round 12's
docstring/record edits did not regress it. Independently corroborated by
docstring-stripped AST hashes (§8) showing the executable logic is what the
tests exercise.

## 4. Findings

### 4.1 R13-1 (P2) — R12-1's and R12-2's corrections are themselves false for the name-binding gap: all four claim a decoy that gap must not have

**What the corrected text now says.** Two distinct corrected passages, six
locations, one shared error:

(a) `backend/tests/contract/test_financial_invariant_scaffold.py:339-352`
(the authoritative, author-facing location), verbatim:

> "**Corrected 2026-10-03, round 12 (R12-1):** … a decoy placed in a
> **different** test function still defeats the count, but now trips the
> correspondence assertion instead, so **each of these four gaps is
> undetected only when its decoy is co-located inside the same enclosing
> test function** as the mutated call site — holding both backstops constant
> at once, not just one. … (`T6+G1c`, `T6+G2s`, `T6+G3s`, `T6+G4s` all
> reproduce the co-located shape …)"

(b) the five durable records R12-2 corrected, each asserting the opposite
placement for the same gap:

| Location | Corrected text (excerpt) |
|---|---|
| `knowledge/00-System/CURRENT_STATE.md:38`, `:40`, `:48` | "`T6+G1c`, which does reproduce in the documented decoy-in-a-different-function shape"; "to name only `T6+G1c` as actually reproducing the documented shape" |
| `knowledge/00-System/CURRENT_HANDOFF.md:34`, `:36`, `:50` | "`T6+G1c`, which **genuinely** reproduces in the documented decoy-in-a-different-function shape" |
| `knowledge/03-Modules/MOD-001/STATUS.md:18` | "only `T6+G1c` reproduces in the documented decoy-in-a-different-function shape" |
| `knowledge/03-Modules/MOD-001/TEST_RESULTS.md:19` | "only one of the three (name-binding, `T6+G1c`) actually reproduces in the round-10/11-documented decoy shape (a decoy in a different function)" |
| `knowledge/03-Modules/MOD-001/evidence/bugs/BUG-050-…md:241`, `:257`, `:264` | "Round 12 found `T6+G1c` **does** reproduce in the documented shape"; "each now states that only `T6+G1c` reproduces in the documented decoy-in-a-different-function shape" |

So the code docstring says the name-binding gap needs a **co-located** decoy;
the five records say it reproduces with a decoy in a **different** function.
They cannot both be right, and **neither is.**

**Measured reality.** All three decoy placements for the name-binding gap,
built in `/tmp/r13/` and run with
`backend/.venv/bin/python -m pytest -q <f>.py`:

| Variant | Shape | Observed |
|---|---|---|
| **`t6_g1c_nodecoy`** | local rebind in the boundary function, **no decoy at all** | **22 passed, exit 0 — fully green (SURVIVES)** |
| `t6_g1c_colocated_after` | same + decoy **co-located** in the boundary function (placed after the rebind so the local is bound — no `UnboundLocalError` artifact) | **1 failed, 21 passed**, exit 1 — `AssertionError: expected 4 pytest.raises(..., match=...) call sites, found 5` |
| `t6_g1c_crossfunc` | same + decoy in a **new** test function | **1 failed, 21 passed**, exit 1 — `test_match_assertions_use_only_the_shared_constants` |

The mechanism is simple once measured, and is the opposite of the other three
gaps. In `G2`/`G3`/`G4` the mutated call site becomes **invisible** to the AST
walker, so a decoy is *required* to restore `len(match_args) == 4`, and it
must be co-located to also hold
`set(found_by_function) == set(expected_constant_by_function)` and the
single-value unpack. In `G1c` the mutated site stays **fully visible** as a
bare `ast.Name(id="_COMPARISON_MATCH")` in the expected function — both
backstops are already satisfied — so a decoy is not merely unnecessary, it is
**fatal**: any fifth site, wherever placed, trips the count (and, if
co-located, the `[value] = found_by_function[name]` unpack as well).

**Why the error propagated.** The original round-11 text at
`BUG-050-…md:241` described `T6+G1c` as "local shadow of `_COMPARISON_MATCH`,
**decoy keeping the call-site count at 4**" — wrong from the start. Round 12's
own §4.1 table recorded the shape correctly as "no decoy", but its remediation
text then carried the inherited decoy framing forward into all six locations
instead of correcting it. `CURRENT_HANDOFF.md:36` is explicit that the
pre-write re-verification covered `T6+G2`/`T6+G3`/`T6+G4` only — "reconstructed
`T6+G2`/`T6+G3` … and the newly-disclosed `T6+G4`" — so `G1c`, the one gap
whose characterization was already wrong, is precisely the one that was not
re-executed before the correction was written. That re-verification was
otherwise sound: this reviewer independently confirms cross-function decoy
KILLED and co-located decoy SURVIVES for all three of `G2`/`G3`/`G4` (§4.2).

**Operational consequence, which is why this is P2 and not P3.** The docstring
is the authoritative disclosure a future author or reviewer acts on. Following
its recipe for the name-binding gap — add a co-located decoy — produces a red
suite, from which the honest conclusion is "this gap is closed." It is not
closed; it is open in a *simpler* form than any record describes, needing no
decoy at all. That is the identical failure mode, in the identical location,
that this project rated P2 as NR10-1 and again as R12-1, and the five-record
half is the same false-attestation class rated P2 as NR5-2, NR6-2 and R12-2.
Rating it P3 would be inconsistent with five prior calibrations. Counted as
**one** finding across six locations rather than split into two, because it is
one factual error replicated, and splitting it would inflate the count.

**Exact corrected wording**, so round 14 is a verification round and not
another discovery round. Replace the "each of these four gaps" clause with a
per-gap statement, e.g.:

> The first gap (name rebinding) needs **no** decoy: the mutated call site is
> still a bare `Name` with the expected id in the expected function, so both
> backstops already hold, and adding any fifth `match=` site — co-located or
> not — trips the `== 4` count. The other three gaps (`from pytest import
> raises`, `**kwargs` unpacking, module alias) make the mutated site invisible
> to the walker, so each needs exactly one decoy to restore the count, and
> that decoy must be **co-located in the same enclosing test function** or it
> trips the per-function correspondence assertion instead. Evidence:
> `T6+G1c` (no decoy) and `T6+G2s`/`T6+G3s`/`T6+G4s` (co-located decoy) are
> each a green 22-passed suite; `T6+G2`/`T6+G3`/`T6+G4` (cross-function decoy)
> and `T6+G1c` with any decoy are each killed.

and correct the five records to say that `T6+G1c` reproduces **with no decoy**,
not in the "decoy-in-a-different-function shape."

### 4.2 The co-located-decoy mechanism for G2 / G3 / G4 — independently confirmed exactly as round 12 described

Reconstructed from round 12's §4.1 / §4.3 prose, not from its scratch code:

| Variant | Shape | Observed |
|---|---|---|
| `t6_g2` | `from pytest import raises` at the boundary site + decoy in a **new** function | **1 failed, 22 passed**, exit 1 — `test_match_assertions_use_only_the_shared_constants` |
| **`t6_g2s`** | same, decoy **co-located** | **22 passed, exit 0 — fully green** |
| `t6_g3` | `**{"match": …}` unpack + decoy in a **new** function | **1 failed, 22 passed**, exit 1 |
| **`t6_g3s`** | same, decoy **co-located** | **22 passed, exit 0 — fully green** |
| `t6_g4` | `import pytest as pt`; `pt.raises(…)` + decoy in a **new** function | **1 failed, 22 passed**, exit 1 |
| **`t6_g4s`** | same, decoy **co-located** | **22 passed, exit 0 — fully green** |

Round 12's labels for these six are correct in every cell.

**The masked defect is real, verified without the test suite at all.** Loading
the mutated module directly (`sys.modules` registered before `exec_module`, per
the OBS-7c trap — `/tmp/r13/defect_real.py`) and calling
`assert_debits_equal_credits` on a genuinely out-of-balance, fully evaluable
set (`1E+27` Dr, `1` Dr, `1E+27` Cr):

```
base_m   -> DEBITS_NE_CREDITS: total debits 1000000000000000000000000001 != total credits 1000000000…
t6_m     -> DEBITS_CREDITS_UNEVALUABLE_PRECISION: leg amounts could not be summed without rounding a…
```

So `T6+G1c`, `T6+G2s`, `T6+G3s` and `T6+G4s` each hide a real cross-route
mislabel behind a fully green 22-passed suite. This is a cross-route
*mislabel*, not a false clean: the harness still refuses the set in both
cases.

### 4.3 R13-2 (P3) — 16 record locations claim `ruff format --check` clean "scoped to `backend/`"; measured, 7 files under `backend/` would be reformatted

Round 12's own report §8 claimed this correctly and narrowly: "`ruff format
--check` **on both Slice-7 files** | 2 files already formatted". Five durable
records generalized that two-file check into a whole-tree claim.

**Locations** (`rg -n 'ruff format --check` both clean \(scoped'`): 16
occurrences across `CURRENT_STATE.md:64,72`, `MOD-001/STATUS.md:16,18,20,22`,
`BUG-050-…md:206,222,245,268`, and `BUG_REGISTRY.md:206` (×6), each reading
"`ruff check`/`ruff format --check` both clean (scoped to `backend/`)".

**Measured, from `backend/`:**

```
$ .venv/bin/python -m ruff format --check .
7 files would be reformatted, 41 files already formatted
   --> tests/harness/authn.py:68:100
   --> tests/harness/migration_safety.py:157:19
   --> tests/harness/postgres.py:174:19
   --> tests/harness/tenant_isolation.py:91:74
   --> tests/integration/test_architecture_gate_rls.py:76:18
   --> tests/integration/test_authn_harness.py:69:15
   --> tests/integration/test_migration_safety_harness.py:230:19
```

```
$ .venv/bin/python -m ruff format --check tests/contract/test_financial_invariant_scaffold.py tests/contract/test_domain_scaffold_inventory.py
2 files already formatted
```

`ruff check .` is genuinely clean tree-wide ("All checks passed!"), so only the
formatter half of the claim is wrong.

**Why P3.** None of the 7 files is a Slice-7 file; all are uncommitted
Slice-5/6 harness and integration work, outside BUG-050's and Slice 7's edit
scope, and the condition pre-dates round 12. The finding is recorded because
(a) it is the same over-generalization class as R12-2 — a narrower check
attested as a broader one, direction of error overstating cleanliness — and
(b) `IMPLEMENTATION.md` §3 treats formatting as part of a blocking CI stage,
so a tree that would fail it is worth knowing about before anything merges.
**Recommended disposition:** route to the Slice-5/6 owner as a separate
formatting pass, and narrow the 16 record claims to "both Slice-7 files",
which is what was actually measured. Not grounds to block BUG-050 on its own.

### 4.4 Checked and clean — no finding

**Third-party capability trust (CAP-008, the only third-party capability this
review exercised).** `CAPABILITY_REGISTRY.md:23` was parsed field by field,
not skimmed. Every `CAPABILITY_POLICY.md`-required supply-chain field is
present and substantive: provenance (Colima MIT / Lima Apache-2.0 /
colima-core MIT / moby + docker-cli Apache-2.0, each confirmed from the
project's own upstream `LICENSE` rather than package metadata); version pins
(Colima 0.10.3, Lima 2.2.0, engine 29.5.2, CLI 29.6.0, colima-core v0.10.4);
content hashes (Postgres by SHA-256 digest, VM image by SHA-512); scope;
`review_status` **APPROVED** (2026-10-02, independent Opus re-review
P0=0/P1=0); `qualified_by` Sonnet and a **distinct** `approved_by`
(`veyro-security-reviewer`, fresh `claude-opus-5-5`, `mr_verify.py` PASS
37/37) — i.e. no self-approval; `approved_date` / `last_reviewed_at`
2026-10-02; `next_review_due` **2026-12-31, in date**; a real
`rollback_target` (fail closed, explicitly no mock fallback); and linked
evidence. `validate_capabilities.py` → `PASS — 7 capability/capabilities, all
registered and APPROVED with required fields present`;
`validate_capability_manifest.py` → `PASS — 7 … no cyclic dependency; no
missing mandatory privileged-surface Rule`; `capability_drift_check.py` →
`PASS — 8 capabilities checked, no drift detected` (8 vs 7 reconciles: CAP-007
is RETIRED per `OWN-006`/ADR-007 and is excluded from the APPROVED count).
**No third-party capability is being treated as trusted without qualification
evidence.** One reader trap worth naming: the registry's front matter is
reverse-chronological and a *preserved historical* entry still reads
"`review_status` remains **`QUALIFIED`**, still **not `APPROVED`**"; the live
row and `current_as_of` both say APPROVED, so that text is superseded, not
current. It is correctly labelled "Prior update", so this is a note, not a
finding.

**R12-4's CAP-008 scope items — status noted only, not re-litigated per the
charge.** Still undisposed: `docker ps` this session still shows
`mikeh1975/tradingview-mcp:latest` / `frosty_bhabha` / `Up 2 days`
co-resident on the same socket, and CAP-008's own scope field still discloses
the writable-home VM mount. Round 12 recorded these as a separate pending
CAP-008 disposition; nothing in `CAPABILITY_REGISTRY.md` has closed them. This
had **no** bearing on this round's verdict and was not re-reviewed.

**Owner-reserved restrictions.** No paid service and no spend of any kind; no
real member data (every fixture synthetic, Postgres bound to `127.0.0.1` with
`--rm`); no deploy or Production promotion; no material product, pricing,
business, architecture, or scope change. A targeted scan of both Slice-7 files
for credential-shaped values
(`rg -i 'password|secret|token|api[_-]?key|BEGIN .*PRIVATE KEY|postgres://|AKIA'`)
returned **nothing**, and no scratch artifact contains one — consistent with
`.claude/rules/infra/secrets.md` controls 1 and 3. Zero leftover containers
after the drills (`docker ps -a` shows only the pre-existing co-resident
image). No commit, no push, no branch.

## 5. Open-gap re-evaluation

**Are the deliberately-open gaps still acceptable as open?** Scoping: **yes**,
unchanged. Disclosure: **no, not as currently written** — see R13-1.

The scoping judgment holds for the same reason rounds 10-12 gave, now
re-verified rather than inherited: every surviving escape (`T6+G1c` with no
decoy, `T6+G2s`, `T6+G3s`, `T6+G4s`) requires **editing the test file
itself**. None is reachable from product code, none touches
`assert_debits_equal_credits`, and the function is fuzz-clean at 35,000 cases
(§6). This file's own NF-7 precedent
(`test_domain_scaffold_inventory.py:32-36`: "any test-level check has this
limit when its own files can be edited") remains the right precedent.

**A process observation this reviewer thinks matters more than either
finding.** Rounds 9, 10, 11, 12 and now 13 have each found an inaccuracy in
the documentation that the *previous* round's remediation wrote. The code has
been clean for nine rounds; the loop is being sustained by hand-written prose
about a mechanism that is cheap to measure and easy to describe slightly
wrongly. The way out is not a sixth prose narrowing. Either (a) replace the
mechanism paragraph with the small evidence table in §4.1/§4.2 — shapes and
observed outcomes, which is checkable by re-running the mutants — or (b) delete
the mechanism description from the docstring entirely, keep only the
enumeration of the four gaps (which has been accurate since R12-3) plus a
pointer to the evidence file. Option (b) removes the whole class of finding
permanently and loses nothing a reader needs.

Deliberately **not** expanded into: R04, SCN-067, BUG-048, ADR-010 Amendment
A2 — none was read into, commented on, or acted upon.

## 6. Independent adversarial execution — mutants, compositions, fuzz

**19 reconstructions, all in `/tmp/r13/`:** `t6`, `g7`, `g8`, `g8b`, `g1c`,
`t6_g7`, `t6_g8`, `t6_g8b`, `t6_g2`, `t6_g3`, `t6_g4`,
`t6_g1c_colocated`, `t6_g1c_colocated_after`, `t6_g1c_crossfunc` —
**KILLED**. `base`, `t6_g1c` / `t6_g1c_nodecoy`, `t6_g2s`, `t6_g3s`,
`t6_g4s` — **green 22-passed**, every survivor a self-check-disclosure gap
requiring an edit to the test file, not a product defect.

**Differential fuzz — 35,000 cases, two independently written generators,
exact `Fraction` oracle, zero false cleans and zero false alarms**
(`/tmp/r13/fuzz.py`). A *false clean* is defined as the oracle finding a set
genuinely unbalanced while the harness raises nothing; a *false alarm* as the
oracle finding it exactly balanced while the harness raises
`DEBITS_NE_CREDITS`. The precision route is neither — it is an explicit
refusal to evaluate.

```
gen_a mixed/extreme N=20000 {'clean': 2174, 'neq': 6726, 'prec': 11100, 'other': 0} FALSE_CLEANS=0 FALSE_ALARMS=0
gen_b money-only    N=15000 {'clean': 7507, 'neq': 7493, 'prec': 0,     'other': 0} FALSE_CLEANS=0 FALSE_ALARMS=0
TOTAL_FALSE_CLEANS = 0  TOTAL_FALSE_ALARMS = 0
```

Generator A mixes plausible money, extreme exponents (`1E-40`…`1E+45`) and
20-34 digit mantissas, force-balancing roughly half the cases through a
`Fraction`-exact closing leg. Generator B is independently shaped: strictly
plausible 2-decimal money built as matched postings with exactly one
perturbation, which drives the **comparison** route specifically and yields a
near-exact 50/50 split (7507 balanced / 7493 unbalanced) with every verdict
correct and no precision-route escape at all. `sys.modules` was registered
before `exec_module` in every load (OBS-7c trap avoided).

## 7. Scenario review against stated acceptance criteria

Both scenarios' live text was re-read at `SCENARIOS.md` (SCN-MOD001-132 and
SCN-MOD001-133 blocks), not taken from the dispatch summary.

### SCN-MOD001-132 — acceptance criteria MET, verified by real execution

The scenario requires: for each of the six named domains
(`backend/app/modules/{membership,booking,payment,ledger,pos,access}/`), run
that domain's `tests/test_scaffold_live.py` and have all six pass, "proving
the harness (test discovery, fixture DB connection, tenant-context resolver
from `_shared/`) is live for that domain path"; and negatively, that when one
domain's fixture is deleted or deliberately broken, "the CI test-run step
reports a non-zero exit naming that specific domain's missing/failing
scaffold, rather than silently reporting the suite green with five domains
actually collected."

CAP-008 was checked **before** use (§4.4: APPROVED, `next_review_due`
2026-12-31, in date). Colima running (`macOS Virtualization.Framework`,
`aarch64`, runtime `docker`). Drills ran in a throwaway `rsync` copy at
`/tmp/r13be/` (`.venv`, `__pycache__`, `.pytest_cache` excluded), since
removed; the real tree was never mutated. Different domains were chosen than
round 12 used (it broke `ledger` and `pos`), so the drills are genuinely
independent rather than a replay:

| Drill | Observed |
|---|---|
| Positive — all six domains, direct | `pytest backend/app/modules -q` → **6 passed in 1.57s** |
| Positive — inventory check | `pytest -q tests/contract/test_domain_scaffold_inventory.py` in `/tmp/r13be/` → **2 passed in 1.89s** (the ~1.8s first-test cost is consistent with a genuine container start, not a stub) |
| Negative A — **delete** the `payment` scaffold | **2 failed**; `AssertionError: missing domain scaffold(s): ['payment']` — names exactly the deleted domain |
| Negative B — **break** the `access` assertion (`== (1,)` → `== (2,)`) | exit **1**; `AssertionError: domain scaffold inventory not clean (exit=1): {'access': 'failed'}` — names exactly `access`, and only `access` |
| Restore check | after restoring both files → **2 passed in 1.82s** |

Negative A also exercised the file's own documented fail-closed behaviour: the
second test reported all six domains as `EXPECTED_EXACTLY_ONE_GOT_0:[]` under
a collection error — it never claims a domain passed when nothing could prove
it, exactly as the module docstring (lines 12-23) states, and exactly the
opposite of "silently reporting the suite green with five domains collected."

Does the scenario verify what it claims? **Yes.** Its NF-7 content-blindness
limitation (lines 32-36) is honestly stated and correctly scoped.
**SCN-MOD001-132 has no blocking finding of its own this round.** It remains
recorded `NOT EXECUTED` in `SCENARIOS.md`, which is correct — nothing has
promoted it, including this review.

### SCN-MOD001-133 — acceptance criteria MET; promotion still blocked on BUG-050

The scenario requires the harness to assert debits equal credits and pass on a
balanced synthetic set, and, on a deliberately unbalanced set (a debit with no
matching credit), to fail "citing the specific invariant violated — proving
the harness itself detects a real violation, not a rubber-stamp pass."

Both are satisfied on current code: `test_balanced_synthetic_entries_pass` and
`test_unbalanced_synthetic_entry_fails_closed` (which asserts
`match=_COMPARISON_MATCH`, i.e. the anchored `^DEBITS_NE_CREDITS`, on a
message carrying both totals and the leg count) pass, with the whole file at
**22 passed in 0.02s**. The 35,000-case fuzz (§6) is far stronger evidence
than the scenario's own criteria demand, and the direct module-load probe
(§4.2) confirms the real-imbalance detection independently of pytest.

Does the scenario verify what it claims? **Yes, for the criteria as written.**
The caveat is unchanged from rounds 10-12: its criteria say nothing about the
self-check tests that rounds 8-13 have been fighting over, which exist above
and beyond SCN-133's text. **SCN-MOD001-133 must not be promoted this round**
while BUG-050 is open with R13-1 outstanding.

## 8. Tree integrity and scope boundaries honored

| Check | Observed |
|---|---|
| `git rev-parse HEAD` | `e516bedabf3d654ad3ae16d948b8f3522739ddc2` — unchanged, before and after all drills |
| SHA-256 `test_financial_invariant_scaffold.py` | `5577fafd5f7554f75db5266f26c5544950218b3a9d60869220023e895a02a047` — matches the hash `BUG-050-…md:268` records post-round-12-remediation, exactly |
| SHA-256 `test_domain_scaffold_inventory.py` | `ef6d23fa49a7f15198afe0a060a6bc922bc944414aac8f1f15d84fb9cafd021a` — unchanged since round 10 |
| **New this round:** `assert_debits_equal_credits` docstring-stripped AST SHA-256 | `98b20085401e8bd1e8363051179f48604764ea24c4da4e87159f2b970fc40162` |
| **New this round:** whole-file docstring-stripped AST SHA-256 | `ba8ed9c340789c5df6f137aa2922a0c6ab3f647a4dda22357aea4d026d835ba2` |
| `git diff --check` (unscoped) | clean, exit 0 |
| `git status --porcelain \| wc -l` | 226 entries (round 12: 223; delta = `…ROUND12…md`, `REVIEW_IN_FLIGHT.md`, and the round-12 remediation's own record edits). **No entry produced by this review** — all scratch was in `/tmp/r13/` and `/tmp/r13be/`, both removed |
| Full suite, `pytest backend/ -q` | **200 passed in 24.90s** |
| Full suite, `pytest -q` from `backend/` | **194 passed in 23.20s** |
| Count reconciliation | 194 + the 6 `app/modules/*/tests/test_scaffold_live.py` domain scaffolds = **200**. `pyproject.toml` sets `testpaths = ["tests"]`, so invoking from `backend/` excludes `app/modules`, while `pytest backend/` includes them. Round 12's recorded 194 is the `testpaths` figure; **not a discrepancy** |
| Focused Slice-7 pair | **24 passed** (22 + 2) |
| Financial-invariant file alone | **22 passed in 0.02s** |
| Whole `tests/contract/` directory | **25 passed** — the extra being the pre-existing `tests/contract/test_scaffold_live.py`, consistent with round 12 |
| `ruff check .` (from `backend/`) | **All checks passed!**, exit 0 |
| `ruff format --check` on both Slice-7 files | **2 files already formatted**, exit 0 |
| `ruff format --check .` (from `backend/`) | **7 files would be reformatted, 41 already formatted** — see R13-2; no Slice-7 file among the 7 |
| `mypy app tests` (strict) | **Success: no issues found in 47 source files**, exit 0 |
| `verify_baselines.py` | **PASS — all 4 governing baseline hashes match `PROJECT_INDEX.md` exactly** |
| `validate_capabilities.py` | **PASS — 7 capabilities, all registered and APPROVED with required fields present** |
| `validate_capability_manifest.py` | **PASS — 7 capability/Rule ID(s), no cyclic dependency, no missing mandatory privileged-surface Rule** |
| `validate_baseline_binding.py` | **PASS — all 4 governing baselines correctly bound; `SESSION_BOOTSTRAP.md` enforcement metadata present** |
| `validate_repo_skeleton.py` | **PASS — all 7 required paths present** |
| `validate_migration_ordering.py` | **PASS — every migration record complete and phase-ordered** |
| `capability_drift_check.py` | **PASS — 8 capabilities checked, no drift detected** |

The two docstring-stripped AST hashes are this round's own contribution to the
evidence trail: they let any future round distinguish a documentation edit
from a logic edit mechanically, instead of relying on a prose assertion that
"only docstrings changed" — which is the exact class of claim R13-1 shows can
go wrong.

`run_regression.py` was deliberately **not** run: it writes an untracked
`knowledge/05-QA/tools/regression-runs/RUN_*.txt` artifact (a side effect
disclosed in round 11 §10), and this round's charge was to write exactly one
new file. Rounds 11 and 12 recorded it PASS 4/4 (1 N/A) against the same
`HEAD`; this round neither confirms nor disputes that.

**Scope boundaries.** `BUG_REGISTRY.md`, `BUG-050-…md`, `CURRENT_STATE.md`,
`CURRENT_HANDOFF.md`, `STATUS.md`, `TEST_RESULTS.md`, `SCENARIOS.md`,
`CAPABILITY_REGISTRY.md`, `REVIEW_IN_FLIGHT.md` and `SESSION_BOOTSTRAP.md`
were all **read but not written**. BUG-050 not closed; neither scenario
promoted; the in-flight claim not cleared. This file is the only file written.

## 9. Record integrity

**Derivation query — re-run this round, 38 files, reconciles exactly.**

```
rg -l 'BUG-050|test_financial_invariant_scaffold|SCN-MOD001-133|SCN-MOD001-132|test_domain_scaffold_inventory|test_scaffold_live' knowledge .claude | sort
```

**38 files**, up from round 12's 35. The growth is expected and fully
explained — three additions, each verified rather than assumed:

1. `…SECURITY-REVIEW-ROUND12-2026-10-03.md` — did not exist when round 12 ran
   the query (its own §9 derived 35 as 32 + `ROUND11` + `ROUND11B` +
   `SLICE-7-ROUND11-COLLISION-CHECKPOINT`, i.e. excluding itself).
2. `knowledge/00-System/REVIEW_IN_FLIGHT.md` — new file, created by the
   round-12 remediation for R12-5; contains 2 `BUG-050` mentions.
3. `knowledge/00-System/SESSION_BOOTSTRAP.md` — **newly** matching. Verified,
   not inferred: `git show HEAD:knowledge/00-System/SESSION_BOOTSTRAP.md | rg -c '<6 tokens>'`
   returns no match, so the token arrived with the uncommitted R12-5 §4 step
   at line 83, which cites BUG-050 as the collision's origin.

35 + 3 = **38, exact.** A changed count is not itself a defect; the query
continues to reproduce the full historical set with a fully explained delta,
and **the 6-token query should be retained as the round-14 baseline**.

**Currency of the live documents.** All are current to round 12 and name a
fresh round 13 as the next legally allowed action, which is what was
dispatched. `SCENARIOS.md` correctly shows both scenarios `NOT EXECUTED`.
`MOD-001/IMPLEMENTATION.md` is correctly in its own plan-document bucket.
**No stale-currency finding this round** — the second consecutive round with
none.

**Internal consistency.** The round-12 verdict (BLOCKED, P0=0/P1=0/P2=2/P3=3)
is stated identically across `CURRENT_STATE.md`, `CURRENT_HANDOFF.md`,
`STATUS.md`, `TEST_RESULTS.md`, `BUG_REGISTRY.md` and `BUG-050-…md`. The
round-11 collision remains consistently described, neither report renumbered,
both preserved. Hash records are accurate: `BUG-050-…md:268`'s
`5577fafd…` matches the live file byte-for-byte, with an honest explanation of
why a docstring-only edit changes the hash. `CURRENT_HANDOFF.md:36` honestly
discloses which mutants the pre-write re-verification actually covered — which
is what made R13-1 findable. Dates are internally consistent.

**The one integrity defect is R13-1** (§4.1): six locations, including the
authoritative code docstring, state a decoy requirement that executable
reality contradicts. R13-2 is a second, milder instance of the same
over-generalization habit.

## 10. Closure assessment and next action

**BUG-050 is not closeable this round** — R13-1 is an open P2 in the
authoritative disclosure location. **SCN-MOD001-133 must not be promoted this
round.** SCN-MOD001-132 has no blocking finding of its own (§7); whether to
promote it independently of BUG-050 remains the orchestrator's/lead's call, as
rounds 3-12 each separately noted, and this reviewer makes no such decision.

**Next action recommendations** (none performed here):

1. **Remediation pass (routine-implementation tier, not self-certified by any
   reviewer):** apply R13-1's exact corrected wording from §4.1 to the code
   docstring and the five records — **and re-execute `T6+G1c` with no decoy,
   with a co-located decoy, and with a cross-function decoy before writing the
   correction.** The round-12 remediation's single failure was re-verifying
   three of four gaps and writing text about all four; the fix is to re-verify
   the one it skipped.
2. **Strongly consider §5's option (b)** — delete the mechanism paragraph from
   the docstring entirely, keep the four-gap enumeration (accurate since
   R12-3) plus a pointer to the evidence. Five consecutive rounds have each
   found an error in the previous round's prose about this one mechanism. The
   paragraph is the finding generator, and nothing a reader needs is lost by
   removing it.
3. **Narrow R13-2's 16 claims** to "both Slice-7 files" (what was measured) and
   route the 7 unformatted Slice-5/6 files to their owner as a separate
   formatting pass.
4. **Record the round-13 state** in the six durable records
   (`BUG_REGISTRY.md` row and front matter, `BUG-050-…md` round-13 section,
   `CURRENT_STATE.md`, `CURRENT_HANDOFF.md`, `STATUS.md`, `TEST_RESULTS.md`),
   including the 38-file query reconciliation and the two new
   docstring-stripped AST hashes.
5. **Orchestrator:** run `mr_verify.py` against this reviewer's full real
   transcript (§1.2) and record the verdict and turn count; then clear
   `REVIEW_IN_FLIGHT.md`'s claim once this result is recorded, per that file's
   own protocol.
6. **Route R12-4 to its separate CAP-008 disposition** with a dated
   remediation target; both items were still open and undisposed this session
   (§4.4), untouched by this round.
7. **Then a fresh round-14 `veyro-security-reviewer`** that verifies R13-1's
   and R13-2's corrections for accuracy, independently reconstructs all three
   `G1c` decoy placements plus `T6+G2s`/`T6+G3s`/`T6+G4s`, re-runs the 6-token
   query against the 38-file baseline, and re-runs the mutant/fuzz/drill set.
   If recommendation 2 is taken, round 14 should be a short verification round,
   not another discovery round.

R04, SCN-067, BUG-048 and ADR-010 Amendment A2 remain separately BLOCKED on
the unrelated Anthropic model-assurance safeguard, entirely untouched by this
round.

**Explicit statement: zero false cleans found in `assert_debits_equal_credits`
this round — the ninth consecutive round, now across 19 mutants/compositions,
35,000 fuzz cases against an exact `Fraction` oracle with zero false alarms as
well, and a direct non-suite module-load probe. The function itself is not the
problem and has not been the problem since round 4. Both scenarios'
acceptance criteria as written are MET on current code. Every open finding is
about the accuracy of the prose describing the self-check that surrounds the
function — and in this reviewer's judgment, that prose should be deleted
rather than corrected a sixth time.**
