---
doc: GOV01-R02-SLICE7-SECURITY-REVIEW-ROUND15
status: BLOCKED — P0=0 / P1=0 / P2=3 / P3=2
round: 15
date: 2026-10-04
scope: MOD-001 GOV-01-R02 Slice 7 — SCN-MOD001-132 (six-domain scaffold inventory), SCN-MOD001-133 (financial-invariant harness); BUG-050
reviewer: veyro-security-reviewer (Opus tier), fresh context, zero memory of any prior round
review_only: true — no source file edited, no scenario promoted, no bug closed, no commit/push, REVIEW_IN_FLIGHT.md not written
---

# Round-15 independent security re-review — GOV-01-R02 Slice 7

## 0. Charge and what was actually done

Dispatched to (i) independently reconstruct and execute all four R14-1
execution-suppression shapes against round 14's remediation
(`test_critical_negative_tests_are_not_suppressed`); (ii) give a reasoned
in-scope/out-of-scope disposition for the companion inventory file's
analogous guard-function gap; (iii) probe further execution-suppression shapes
round 14 did not exhaust, separating source-text-catchable gaps from shapes
round 14 already correctly disclosed; (iv) re-run the 6-token derivation query
and reconcile the unresolved 41-vs-42 discrepancy; (v) re-verify
SCN-MOD001-132 live via CAP-008 if the environment permits; (vi) run the full
real suites plus `ruff check`, `ruff format --check`, `mypy --strict`.

All six were executed. No prior round's prose was accepted as evidence: every
mutant was rebuilt from prose in a throwaway `/tmp/r15/` tree, every count and
assertion message below is this session's own observed output.

Nineteen variants were built and run in total. CAP-008 **was** available this
round (Colima running), so SCN-132's live acceptance criteria were
independently re-verified against a real disposable Postgres — the first round
since 13 to do so.

## 1. Session and model identity

### 1.1 Directly observed facts

| Fact | Observed value |
|---|---|
| agentId | `a6d1b165f6bc7f0de` |
| Transcript | `/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/74fc7c27-158f-4682-8a81-668891a46625/subagents/agent-a6d1b165f6bc7f0de.jsonl` |
| Parent session | `74fc7c27-158f-4682-8a81-668891a46625` |
| Repo HEAD at start and end | `e516bedabf3d654ad3ae16d948b8f3522739ddc2` (unchanged) |
| agentId distinct from all prior rounds | Yes — verified against the 14 prior `subagents/agent-*.jsonl` files on disk; no collision |

### 1.2 Deliberate non-self-attestation

Per ADR-004 / MODEL_ROUTING and this round's explicit dispatch charge, this
reviewer did **not** run `mr_verify.py` against its own transcript and makes
**no self-attestation** of its own model identity. Independent attestation via

```
backend/.venv/bin/python knowledge/05-QA/tools/mr_verify.py \
  /Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/74fc7c27-158f-4682-8a81-668891a46625/subagents/agent-a6d1b165f6bc7f0de.jsonl \
  opus veyro-security-reviewer
```

is the orchestrating session's job to run externally. This follows rounds
13/14's convention, not round 12's self-attested deviation.

**One discrepancy the orchestrator should resolve before attesting.**
`BUG050-ROUND15-WATCHDOG-CHECKPOINT-2026-10-04.md` records the dispatching
ACPX session as `72553ce0-d186-4fbc-87f1-0bda58bdc31f`. This reviewer's
actually-observed parent session is `74fc7c27-158f-4682-8a81-668891a46625`.
Both facts are recorded as observed; this reviewer does not guess which
transcript the orchestrator should attest. The path in §1.1 is the one this
reviewer's own tool calls were written to.

## 2. Verdict

**BLOCKED — P0=0 / P1=0 / P2=3 / P3=2.**

| Severity | Count and summary |
|---|---|
| P0 | 0 |
| P1 | 0 |
| P2 | 3 — **R15-1**: round 14's new guard does not guard *itself* (nor the other three self-checks); skipping/redefining/rebinding the guard reopens all four R14-1 shapes, fully green, ruff and mypy clean. **R15-2**: the guard's suppressing-marker matcher is shape-bound to the literal `pytest.mark.*` attribute chain; `from pytest import mark` and `import pytest as pt` both escape it, fully green, ruff and mypy clean. **R15-3**: the companion inventory file's two guard functions have the same gap, confirmed executable — a rebind makes the inventory report **"2 passed"** while a domain scaffold is genuinely broken. |
| P3 | 2 — **R15-4**: module-level `pytestmark` suppression (list and single-mark forms) escapes the guard and is not in round 14's disclosure list. **R15-5**: CAP-008 scope-minimality — a co-resident unregistered third-party container directly observed **running** on CAP-008's engine, undisposed for a sixth consecutive round. |

**Round 14's R14-1 fix is genuinely correct for exactly the four shapes it
claimed, and nothing more.** All four are confirmed closed by execution (§3).
Round 14's R14-2 docstring/record correction is also confirmed accurate (§3.3).
Zero false cleans were found in `assert_debits_equal_credits` itself — the
**eleventh** consecutive round with that result, and the function is
hash-identical to round 13/14's recorded values (§8).

Every finding this round is a *test-harness self-protection* defect, not a
product defect. None is reachable from product code; each requires editing a
Slice-7 test file. That is the same exploitation precondition rounds 10-14
applied when rating `T6+G1c`/`G2s`/`G3s`/`G4s` and R14-1 at P2, so the
severities here are consistent with that precedent rather than inflated.

## 3. Round-14's remediation — verified by execution

Mutants reconstructed from prose only (BUG-050's record and the test file's own
docstring history), not from any diff:

- **T6** — `ctx.prec = 27` inserted immediately after
  `ctx.traps[Inexact] = True` in `assert_debits_equal_credits`. Under T6 a
  genuinely out-of-balance *and* fully evaluable leg set is misreported under
  `DEBITS_CREDITS_UNEVALUABLE_PRECISION` instead of `DEBITS_NE_CREDITS` — the
  NR4-2/NR5-1-class cross-route mislabel.
- **G9b** — `@pytest.mark.skip(reason="flaky on CI, re-enable later")` on
  `test_precision_boundary_within_context_still_compares_exactly` (the only
  test that detects T6).
- **G9c** — `@pytest.mark.xfail(reason="known issue")` on the same test.
- **G10** — a second, vacuous `def` of that test's name appended to the file.
- **G10d** — a post-definition module-level rebind of that test's name to a
  no-op callable.

Baseline, this session: live file `23 passed`; SHA-256
`5565338125bc5c27f1d014687ec7173473b761bf915805a589f21c0090430457`
(`test_financial_invariant_scaffold.py`),
`ef6d23fa49a7f15198afe0a060a6bc922bc944414aac8f1f15d84fb9cafd021a`
(`test_domain_scaffold_inventory.py` — matches round 14's recorded value
exactly, unchanged since round 10).

### 3.1 All four R14-1 shapes — **CONFIRMED CLOSED**

Command, per variant directory:
`cd /tmp/r15/<variant> && .venv/bin/python -m pytest test_financial_invariant_scaffold.py -q -p no:cacheprovider`

| Variant | Shape | Result | exit | Kill path |
|---|---|---|---|---|
| `v00_base` | unmutated copy | **23 passed** | 0 | — (control) |
| `v01_t6_only` | T6 alone | **1 failed, 22 passed** | 1 | boundary test's anchored `match=` (correct pre-existing kill) |
| `v10_t6_g9b_skip` | T6 + G9b | **1 failed, 21 passed, 1 skipped** | **1** | **new guard**, line 503 |
| `v11_t6_g9c_xfail` | T6 + G9c | **1 failed, 21 passed, 1 xfailed** | **1** | **new guard**, line 503 |
| `v07_t6_g10_redef` | T6 + G10 | **1 failed, 22 passed** | **1** | **new guard**, line 480 |
| `v12_t6_g10d_rebind` | T6 + G10d | **1 failed, 22 passed** | **1** | **new guard**, line 482 |

Exact assertion text, each observed this session:

```
v10:  E  AssertionError: required negative-case test(s) carry a suppressing marker:
         {'test_precision_boundary_within_context_still_compares_exactly': ['skip']}
      test_financial_invariant_scaffold.py:503: AssertionError

v11:  E  AssertionError: required negative-case test(s) carry a suppressing marker:
         {'test_precision_boundary_within_context_still_compares_exactly': ['xfail']}
      test_financial_invariant_scaffold.py:503: AssertionError

v07:  E  AssertionError: required negative-case test(s) redefined more than once:
         {'test_precision_boundary_within_context_still_compares_exactly': 2}
      test_financial_invariant_scaffold.py:480: AssertionError

v12:  E  AssertionError: required negative-case test(s) rebound to another value after
         definition: ['test_precision_boundary_within_context_still_compares_exactly']
      test_financial_invariant_scaffold.py:482: AssertionError
```

Each fails via the new guard's **own** distinct assertion, not an incidental
side effect — three of the guard's four sub-assertions are each independently
exercised (marker, redefinition, rebind). Round 14's claim is accurate in
every particular.

**Isolation controls also run** (each suppression shape *without* T6:
`v20`-`v23`): all four likewise fail via the new guard, `1 failed, 21-22
passed`. So the guard fires on the suppression itself, independent of whether
a masked defect happens to be present — the correct, stronger behaviour.

**Also confirmed caught, not claimed by round 14:**

| Variant | Shape | Result |
|---|---|---|
| `s6_t6_skipif` | `@pytest.mark.skipif(True, reason=...)` | **1 failed, 21 passed, 1 skipped**, exit 1 — caught (`skipif` is in `suppressing_marks`) |
| `x1_t6_bare_skip_decorator` | `@pytest.mark.skip` with **no** call parens | **1 failed, 21 passed, 1 skipped**, exit 1 — caught (the guard's `decorator.func if isinstance(decorator, ast.Call) else decorator` handles the non-Call form) |

### 3.2 T6 is no longer masked

Under all four shapes the suite exits **non-zero**. The boundary test is still
skipped/xfailed/shadowed in each case — the guard does not *restore* T6's
detection, it makes the suppression itself loud. That is the correct and
honest semantics for a source-text check, and it is sufficient: an exit-1
suite is not a false clean.

### 3.3 R14-2 — **CONFIRMED FIXED, accurately**

The live docstring of `test_match_assertions_use_only_the_shared_constants`
(lines 342-362) now reads as a dated round-14 correction that (a) retains the
accurate mechanism parenthetical (`G1c` needs no decoy; the other three each
need a co-located decoy), (b) states plainly that the previous "deliberately
not described"/"stops at the four-gap enumeration" framing was false, and (c)
points at BUG-050's round-13 and round-14 sections for re-runnable evidence.
The self-contradiction round 14 identified is gone, and correct disclosure was
preserved rather than deleted — exactly what round 14 recommended. No residual
finding.

## 4. Findings

### 4.1 R15-1 (P2) — NEW: the new guard does not guard itself; suppressing the guard reopens all four R14-1 shapes, fully green

**The defect.** `test_critical_negative_tests_are_not_suppressed`'s
`required_names` set was read directly from the AST this session and contains
exactly four entries:

```
required_names = ['test_precision_boundary_within_context_still_compares_exactly',
                  'test_precision_loss_fails_closed',
                  'test_unbalanced_synthetic_entry_fails_closed',
                  'test_unmatched_credit_fails_closed']
```

The guard itself is absent, and so are the other three structural self-checks
(`test_all_match_assertions_are_anchored`,
`test_match_assertions_use_only_the_shared_constants`,
`test_error_codes_are_mutually_disjoint`). The guard protects the tests it
watches but nothing protects the watcher. Round 14's fix therefore moves the
single point of failure one level up rather than removing it.

**Confirmed by execution.** Each variant combines T6, a skip on the boundary
test (the R14-1 shape round 14 closed), *and* a suppression of the guard
itself:

| Variant | Shape | pytest | exit | `ruff check` | `mypy --strict` |
|---|---|---|---|---|---|
| `s1_t6_skip_boundary_skip_guard` | T6 + skip boundary + **skip the guard** | **21 passed, 2 skipped** | **0** | **All checks passed!** | **Success** |
| `s2_t6_skip_boundary_redef_guard` | T6 + skip boundary + **vacuous redefinition of the guard** | **22 passed, 1 skipped** | **0** | F811, Found 1 error | Found 1 error |
| `s3_t6_skip_boundary_rebind_guard` | T6 + skip boundary + **post-definition rebind of the guard** | **22 passed, 1 skipped** | **0** | F811, Found 1 error | **Success** |

`s1` is the serious one: **exit 0, ruff clean, mypy clean**, T6's real defect
present and undetected. It is two plausible decorator lines, each with a
routine-sounding reason string. `s2`/`s3` also exit 0; ruff's F811 catches
them, but §4.6 establishes that lint is not an enforced gate here — there is
no `.github/` directory at all.

`s1`'s observed output, confirming the guard is simply not run:

```
21 passed, 2 skipped in 0.02s     (exit 0)
```

**Why this is a new finding and not R14-1 restated.** R14-1 is "the four
negative-case tests can be suppressed." R15-1 is "the mechanism that detects
that can itself be suppressed by the same means." The fix is different too:
R14-1 needed a new check; R15-1 needs four names added to an existing set.

**Not disclosed anywhere.** The guard's own docstring enumerates what it does
not catch — "a `conftest.py`-level skip, a collection-time `pytest.skip()`
call inside the test body, or deselection via `-k`/`-m`." Self-suppression of
the guard is not among them, nor is it in BUG-050, `CURRENT_STATE.md`,
`CURRENT_HANDOFF.md`, or any of the fourteen prior reports.

**Source-text-catchable, therefore in scope for a fix.** Adding the guard's
own name plus the three other self-check names to `required_names` closes
`s1`/`s2`/`s3` with no new mechanism — the existing three sub-assertions
already do the work. This reviewer did not implement it (review-only dispatch).

### 4.2 R15-2 (P2) — NEW: the suppressing-marker matcher is shape-bound; `from pytest import mark` and `import pytest as pt` both escape it

**The defect.** The guard's decorator test requires the exact AST shape
`pytest` → `.mark` → `.{skip,xfail,skipif}`:

```python
isinstance(target, ast.Attribute)
and target.attr in suppressing_marks
and isinstance(target.value, ast.Attribute)
and target.value.attr == "mark"
and isinstance(target.value.value, ast.Name)
and target.value.value.id == "pytest"
```

Two one-line import changes defeat it:

| Variant | Shape | pytest | exit | `ruff check` | `mypy --strict` |
|---|---|---|---|---|---|
| `s4_t6_markalias_skip` | T6 + `from pytest import mark` + `@mark.skip(reason=...)` on the boundary test | **22 passed, 1 skipped** | **0** | **All checks passed!** | **Success** |
| `s5_t6_modalias_skip` | T6 + `import pytest as pt` + `@pt.mark.skip(reason=...)` | **22 passed, 1 skipped** | **0** | **All checks passed!** | **Success** |

Both are **fully clean false cleans**: exit 0, both lint gates green, T6's
defect live. `s4` collapses the chain to `mark` → `.skip` (no `pytest` Name
node). `s5` keeps the three-level chain but the root Name is `pt`.

**Why this is a finding rather than an already-disclosed gap.** These are
precisely the analogues of this file's long-disclosed `G2`
(`from pytest import raises`) and `G4` (`import pytest as pt`)
walker-blindness gaps — but those two are disclosed against
`test_match_assertions_use_only_the_shared_constants`'s walker. Round 14 wrote
a brand-new check with its own brand-new matcher and its own disclosure
paragraph, and that paragraph names only conftest-level skip, in-body
`pytest.skip()`, and `-k`/`-m`. The import-shape family was a known,
twice-documented weakness of the exact AST idiom round 14 chose to reuse, and
the new check inherited it undisclosed. That is the aggravating fact: the
project already knew this escape family existed and did not carry the
knowledge across to the new check.

**Source-text-catchable, therefore in scope for a fix.** Matching on the
decorator's trailing attribute name (`skip`/`xfail`/`skipif`) regardless of the
receiver chain, or resolving `pytest`'s bound aliases from the module's own
`Import`/`ImportFrom` nodes, closes both. Either is a small change to code the
guard already has.

### 4.3 R15-3 (P2) — the companion inventory file's guard-function gap: **IN SCOPE**, confirmed executable, worst-shaped false clean in the lineage

Round 14 flagged this and explicitly declined to fix or scope it, leaving the
disposition to this round. **Disposition: in scope for BUG-050, and blocking
for SCN-MOD001-132.** Reasoning below, then the executable evidence.

#### 4.3.1 Reasoned disposition — why in scope

Three independent grounds, any one of which would suffice:

1. **SCN-MOD001-132's own negative case names this exact outcome as the thing
   that must not happen.** Its scenario text (`SCENARIOS.md`) requires that
   when a domain scaffold is deleted or deliberately broken, the test-run step
   "reports a non-zero exit naming that specific domain's missing/failing
   scaffold, **rather than silently reporting the suite green**." Variants `d3`
   and `d4` below do exactly the forbidden thing: broken domain, suite green,
   exit 0. This is not an invented adjacent concern — it is a direct failure of
   the scenario's own stated acceptance boundary. That alone settles scope.
2. **Precedent within this very bug.** BUG-050 round 2's NF-3 was an
   SCN-132 finding **in this same file** about **this same mechanism** ("a
   skipped `test_scaffold_live` reported the domain clean"). The project
   already treats skip-based false cleans in `test_domain_scaffold_inventory.py`
   as BUG-050 findings. Declining scope now would be inconsistent with the
   bug's own thirteen-round history.
3. **Both scenarios are governed under one bug and one review lineage.** All
   fifteen reports are titled `…SLICE7-DOMAIN-SCAFFOLDS-FINANCIAL-INVARIANT…`
   and both SCN-132 and SCN-133 are held unpromoted by BUG-050. There is no
   separate tracking vehicle this finding could be moved to without creating a
   new, unreviewed one.

The counter-argument — that SCN-132 "has no blocking finding of its own" per
rounds 9-14, so the file should be left alone — does not survive ground 1.
Rounds 9-14 said that because nobody had tested this shape against SCN-132's
file. This round did.

#### 4.3.2 Executable evidence

Drilled in a throwaway copy of the backend tree (`/tmp/r15/d*`, real
`.venv` symlinked, real disposable Postgres via CAP-008). Control: unmutated
copy, `2 passed in 1.73s`. A **different** domain was broken than prior rounds
used (`access` for the break, `pos` for the deletion), so this is a genuinely
independent drill, not a replay.

| Variant | Shape | pytest | exit | `ruff check` | `mypy --strict` |
|---|---|---|---|---|---|
| `d1_delete_pos` | `pos` scaffold file deleted | **2 failed** | 1 | — | — |
| `d2_break_access` | `access` scaffold assertion broken | **1 failed, 1 passed** | 1 | — | — |
| `d3_break_access_skip_guards` | `access` broken + **`@pytest.mark.skip` on both guard functions** | **2 skipped** | **0** | **All checks passed!** | **Success** |
| `d4_break_access_rebind_guards` | `access` broken + **both guard names rebound to a no-op** | **2 passed** | **0** | F811 ×2 | **Success** |

`d1` and `d2` are the positive control — SCN-132's negative case works
correctly on live code, naming exactly the right domain (§6.2).

**`d4` is the most deceptive output anywhere in BUG-050's fifteen rounds.** The
inventory check reports a clean `2 passed` — not a skip, not a deselection, an
affirmative pass — while a domain scaffold is genuinely broken and `mypy
--strict` is clean. A reviewer reading CI output or a test report sees
confirmation that all six domain scaffolds are live. Only ruff's F811 objects,
and there is no CI to run it (§4.6). `d3` is milder in output (`2 skipped`) but
passes **all three** gates, including ruff.

`test_domain_scaffold_inventory.py` does not even import `pytest`, so `d3`
needs one added import line; `d4` needs no import at all — three appended
lines, no decorator, no import, mypy-clean.

**Severity P2**, matching R14-1's precedent (exploitation requires editing the
test file; the masked defect is a broken scaffold, not corrupted product
behaviour). It is the most severe member of the class to date on the strength
of `d4`'s affirmative-pass output.

### 4.4 R15-4 (P3) — module-level `pytestmark` suppression escapes the guard and is not in its disclosure list

| Variant | Shape | pytest | exit | `ruff check` | `mypy --strict` |
|---|---|---|---|---|---|
| `p1_t6_module_pytestmark_skip` | T6 + `pytestmark = [pytest.mark.skip(reason="module temporarily disabled")]` | **23 skipped** | **0** | **All checks passed!** | **Success** |
| `x2_t6_pytestmark_single` | T6 + `pytestmark = pytest.mark.skip(reason="module off")` (non-list form) | **23 skipped** | **0** | **All checks passed!** | **Success** |

**Caught by the guard? No.** `pytestmark` is an `ast.Assign` whose target name
is not in `required_names`, so neither the rebind branch nor the decorator
branch sees it. And because the whole module is skipped, the guard itself never
runs — the same self-suppression root cause as R15-1, reached by a different
route.

**New finding, not already disclosed.** Round 14's disclosure names
"a `conftest.py`-level skip, a collection-time `pytest.skip()` call inside the
test body, or deselection via `-k`/`-m`." A module-level `pytestmark` is none
of those three: it is neither external to the file (unlike conftest), nor
inside a test body, nor a deselection — it is an in-file, source-visible,
whole-module skip application. It is squarely the kind of thing a source-text
check *can* see (`tree.body` contains the assignment outright), so it belongs
in scope for a fix rather than in the disclosed-and-declined bucket.

**P3, not P2**, for one honest reason: `23 skipped` with zero passes is a loud,
hard-to-miss output. R15-1's `21 passed, 2 skipped` and R15-2's `22 passed, 1
skipped` look like a routine temporarily-disabled test; `23 skipped` looks like
nothing ran. The escape is real and the fix is cheap, but the realistic chance
of it surviving a human glance at the output is materially lower.

### 4.5 R15-5 (P3) — CAP-008 scope minimality: a co-resident unregistered third-party container is **running**, undisposed for a sixth consecutive round

CAP-008's qualification evidence is sound and is **not** treated as trusted
without it (§7.1). This finding is narrower: capability **scope**.

Directly observed this session, not inferred:

```
docker ps  -> mikeh1975/tradingview-mcp:latest | Up 2 days | frosty_bhabha
docker images ->
    postgres:<none>                   721873c34ceb
    mikeh1975/tradingview-mcp:latest  f6485198ea8a
```

An unregistered third-party container image is **actively running** on the same
Colima engine CAP-008 registers, and has been for two days. CAP-008's `scope`
field describes only "a disposable Postgres container per pytest session,
bound to `127.0.0.1`, `--rm`, force-removed on exit" — the co-resident
workload is not named there. The registry **does** honestly disclose the other
half of R12-4 ("the local Colima VM presently mounts the user home directory
writable (broader effective filesystem reach than the fixture needs)"), so
that one is disclosed-not-minimal; the co-resident image is simply unrecorded.

This is R12-4, raised round 12, carried without disposition through rounds 13
and 14, and now round 15 — six consecutive rounds. Rounds 12-14 each recorded
it as "not a BUG-050 finding," and this round agrees on *blocking* effect: it
does **not** block SCN-132, SCN-133, or BUG-050's closure. It is raised as a
finding rather than a fourth consecutive observation because this reviewer's
standing charge covers capabilities granted broader scope than their stated
need, the deviation is now confirmed live rather than theoretical, and an item
that only ever ages on the review clock is being tracked by nothing.

### 4.6 Compensating controls — independently re-verified absent

Re-checked directly rather than inherited from round 14:

- `backend/pyproject.toml` `[tool.pytest.ini_options]` contains **only**
  `testpaths = ["tests"]` — no `addopts`, no `--strict-markers`, no `-W error`,
  nothing that converts a skip into a failure.
- **`.github/` does not exist** (`ls .github` → No such file or directory).
  There is no CI at all. So ruff's F811 — the only automated defence that fires
  on `s2`/`s3`/`d4` — is a locally-runnable lint, not an enforced gate.
  MOD-001's `IMPLEMENTATION.md` §3 plans the blocking lint stage; it is not
  built.
- `mypy --strict` is clean on `s1`, `s3`, `s4`, `s5`, `p1`, `x2`, `d3`, `d4`.

## 5. Further-probed shapes — caught / not-caught, and new-or-not

The charge asked for a per-shape ruling distinguishing source-text-catchable
gaps (in scope for a fix) from shapes round 14 already correctly disclosed as
structurally uncatchable without a true execution witness.

| Shape | Caught by round 14's guard? | Observed | Source-text-catchable? | Disposition |
|---|---|---|---|---|
| Module-level `pytestmark = [pytest.mark.skip(...)]` | **No** | `23 skipped`, exit 0, ruff+mypy clean (`p1`) | **Yes** — a module-level `Assign` in `tree.body` | **NEW FINDING R15-4 (P3)** — not in round 14's disclosure list |
| Module-level `pytestmark = pytest.mark.skip(...)` (non-list) | **No** | `23 skipped`, exit 0, ruff+mypy clean (`x2`) | **Yes** | Same finding, R15-4 |
| `conftest.py`-level skip (`pytest_collection_modifyitems` adding a skip marker) | **No** | `21 passed, 2 skipped`, exit 0 (`p3`) | **No** — the suppression lives in a different file the guard does not and should not parse | **NOT a new finding** — explicitly disclosed by round 14's own docstring |
| Collection/runtime `pytest.skip()` inside the test body | **No** | `22 passed, 1 skipped`, exit 0, ruff+mypy clean (`p2`) | Arguably yes in the trivial first-statement form, but not in general (any conditional path can reach it) | **NOT a new finding** — explicitly disclosed by round 14's own docstring, verbatim: "a collection-time `pytest.skip()` call inside the test body" |
| Deselection via `-k` / `-m` | **No** | `21 passed, 2 deselected`, exit 0 (`-k "not precision_boundary and not not_suppressed"` on `v01_t6_only`) | **No** — the suppression is in the invocation, not the source | **NOT a new finding** — explicitly disclosed by round 14's own docstring |
| Suppressing the guard itself (skip / redefine / rebind) | **No** | exit 0 in all three; `s1` ruff+mypy clean | **Yes** — four names added to `required_names` | **NEW FINDING R15-1 (P2)** |
| `from pytest import mark` → `@mark.skip(...)` | **No** | `22 passed, 1 skipped`, exit 0, ruff+mypy clean (`s4`) | **Yes** | **NEW FINDING R15-2 (P2)** |
| `import pytest as pt` → `@pt.mark.skip(...)` | **No** | `22 passed, 1 skipped`, exit 0, ruff+mypy clean (`s5`) | **Yes** | **NEW FINDING R15-2 (P2)** |
| `@pytest.mark.skipif(True, ...)` | **Yes** | exit 1, guard's marker assertion (`s6`) | — | Correctly caught; no finding |
| `@pytest.mark.skip` with no call parens | **Yes** | exit 1, guard's marker assertion (`x1`) | — | Correctly caught; no finding |

**Round 14's three disclosed exclusions are therefore all genuine and all
correctly characterised** — each was reproduced this round and each is either
structurally outside a source-text check (conftest, `-k`/`-m`) or
only-trivially-inside it (in-body `pytest.skip()`). Round 14 drew that line
honestly. The three new findings sit entirely on the *catchable* side of it,
which is why they are findings rather than additions to the disclosure list.

**Observation, not a finding (NF-7 parallel).** A reader could also edit
`required_names` itself to drop the boundary test, silencing the guard with no
marker, no redefinition and no rebind. This is the same irreducible limit the
inventory file already discloses as NF-7 ("an edit to this file's own `DOMAINS`
tuple stays green — any test-level check has this limit when its own files can
be edited"). It is recorded here so round 16 need not re-derive it, and is
explicitly **not** raised as a finding: no self-checking test can defend its
own expectation set.

## 6. SCN-MOD001-132 — live acceptance criteria independently RE-CONFIRMED this round

### 6.1 CAP-008 was available and was used

Checked before assuming, per the charge:

```
which docker colima limactl -> /usr/local/bin/docker /opt/homebrew/bin/colima /opt/homebrew/bin/limactl
docker context ls           -> colima * (unix:///Users/ahmadmabrouk/.colima/default/docker.sock)
colima status               -> colima is running (macOS Virtualization.Framework, arch aarch64, runtime docker)
```

A real disposable Postgres was genuinely created and destroyed. Captured with
`docker events` running concurrently with the real inventory test:

```
create   postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea
start    postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea
kill     postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea
die      postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea
destroy  postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea
```

The digest matches CAP-008's registered pin
(`sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea`)
exactly, and the container is destroyed, confirming cleanup. The initial 1.93 s
wall time looked too fast for a container spin-up, so it was **not** taken on
trust — the event capture above is why this is recorded as confirmed rather
than assumed.

### 6.2 Acceptance criteria — MET on live code

| Criterion | Evidence this round | Status |
|---|---|---|
| All six domain scaffolds collect and pass against a real fixture DB | `pytest tests/contract/test_domain_scaffold_inventory.py -q` → **2 passed**; `pytest tests app/modules -q` → **201 passed** (195 + the six scaffolds) | **MET** |
| Negative: a deleted scaffold is reported, naming that domain | `d1_delete_pos` → exit 1, `AssertionError: missing domain scaffold(s): ['pos']` | **MET** |
| Negative: a broken scaffold is reported, naming that domain, non-zero exit | `d2_break_access` → exit 1, `AssertionError: domain scaffold inventory not clean (exit=1): {'access': 'failed'}` — exactly one domain, by name | **MET** |
| Negative: fail-closed on collection error (never claims a domain passed when nothing proved it) | `d1` also fails `test_all_six_domain_scaffolds_pass` with all six as `EXPECTED_EXACTLY_ONE_GOT_0:[]` at `exit=4` | **MET** |

**SCN-132's substantive acceptance criteria are MET on live code, independently
re-verified by this round's own drills against a real disposable Postgres** —
the first independent live re-verification since round 13. Rounds 14's
un-re-verified inheritance is now discharged.

**However, SCN-132 is not promotable**, because R15-3 is a finding against
SCN-132's own file demonstrating that the very negative-case guarantee above
can be silenced into an affirmative `2 passed`. The criteria are met; the
proof that they stay met is not yet tamper-evident.

## 7. Standing security-review charge

### 7.1 Third-party capability trust — not trusted without qualification evidence

CAP-008 (Docker Engine via Colima 0.10.3 + Lima 2.2.0 + pinned
`postgres:16-alpine`) is the only third-party capability bearing on Slice 7,
and it is **not** treated as trusted without qualification evidence. Verified
directly against `CAPABILITY_REGISTRY.md` this session, field by field:

| `CAPABILITY_POLICY.md` supply-chain field | Present? | Observed |
|---|---|---|
| provenance | Yes | Colima MIT, Lima Apache-2.0, colima-core MIT, moby + docker-cli Apache-2.0; licences confirmed from each project's own upstream `LICENSE`, not package metadata |
| version pins | Yes | Colima 0.10.3; Lima 2.2.0; Engine 29.5.2; CLI 29.6.0; colima-core v0.10.4 |
| content hashes | Yes, with a disclosed limitation | Postgres image by SHA-256 digest; Colima VM image by SHA-512; **Colima/Lima/Docker binaries not independently hashed** — recorded in the registry's own `content_hash` field, not hidden |
| scope | Yes, with the §4.5 gap | Disposable Postgres per session, loopback-bound, `--rm`; home-directory mount disclosed |
| `review_status` | **APPROVED** 2026-10-02 | By a fresh independent Opus capability-security re-review, P0=0/P1=0, `mr_verify.py` PASS 37/37 |
| not self-approved | Confirmed | `qualified_by` Sonnet; `approved_by` a distinct fresh Opus `veyro-security-reviewer` session |
| `next_review_due` | 2026-12-31 | **Not** past due |

`knowledge/00-System/validate_capabilities.py` → **PASS, 7 capabilities, all
registered and APPROVED with required fields present, 0 errors.** No finding on
qualification. The scope-minimality gap is §4.5 (R15-5).

### 7.2 Real member data, credentials, spend

- **Real member data: none.** Both Slice-7 files and all six domain scaffolds
  use only synthetic fixtures (`synthetic:cash`, `synthetic:revenue`,
  `synthetic:deferred`, `uuid4()` identifiers, single-letter account names). A
  PII-shaped scan (`@gmail|@hotmail|@yahoo|@outlook|13-16 digit runs|+10-digit
  phone`) over both Slice-7 files returns exactly one hit,
  `Decimal("1.0000000000000000000000000001")` — the NR3-1 precision-probe
  constant, not a card number.
- **Credentials: none.** A secret-shaped scan
  (`password|secret|api[_-]?key|bearer|BEGIN … PRIVATE KEY|sk-ant|ANTHROPIC_API|postgres(ql)?://|AKIA|AWS_SECRET`)
  over both Slice-7 files and all six domain scaffolds returns **zero hits**.
  No `.env` is referenced from any committed workflow — there are no workflows.
  The disposable Postgres DSN is generated at runtime by the harness, never
  committed.
- **Spend: none.** No paid service touched, invoked, or provisioned. All work
  was local `pytest`/`ruff`/`mypy`/`rg`/`docker` against the existing
  `backend/.venv` and the already-approved local Colima engine. The Postgres
  image was already present locally (no registry pull).
- **Owner-reserved restrictions: all four honoured.** No spend; no real member
  data; no deploy or promotion to Production; no material
  product/pricing/business/architecture/scope change.

### 7.3 `REVIEW_IN_FLIGHT.md` — this round's dispatch is the claimed one

Read directly; **not modified by this reviewer** (the orchestrator owns that
file). `current_claim`:

```
IN_FLIGHT — BUG-050 round 15, claimed by Veyro watchdog cron
66643874-e295-4d53-a846-ee79cb6c3a44, dispatched 2026-10-03T21:39:49.581359+00:00.
Expected subagent: veyro-security-reviewer (fresh Opus) via fresh ACPX session
veyro-bug050-round15-20261004. Clear on result recorded, not merely on subagent
completion.
```

This confirms the round-15 dispatch was claimed before dispatch (file mtime
2026-10-04 00:39; the watchdog checkpoint it names is 00:40). The file also
records two prior clearances performed with genuine crash-recovery checks
rather than blind overwrites, consistent with its own protocol. The expected
subagent type matches this reviewer's role. The session-id discrepancy noted in
§1.2 is the one open item for the orchestrator. **No finding.**

## 8. `assert_debits_equal_credits` is unchanged — independently corroborated

Three independent AST digests of the function, docstring-stripped, computed
this session by a method re-derived from round 14's recorded method names:

| Method | SHA-256 | vs round 14's record |
|---|---|---|
| `ast.dump(node, include_attributes=True)` | `14d70eb1b280528d597d13c651d4992f641c9e724258191daa7adec6cd0053b9` | **exact match** |
| `ast.dump(node, indent=2)` | `c72d9cefa359a041663568edd15a6c4badf20865542a9f38c59be93bce7aeb20` | **exact match** |
| `ast.unparse(node)` | `ae11bc1bff3b69aeca609f9ebc5879a5da0c6a806959add533a3f0816495414b` | **exact match** |

All three match, including the line-number-sensitive `include_attributes=True`
variant — so round 14's remediation genuinely touched only test scaffolding and
docstrings *after* this function, never the invariant itself. The function is
byte-stable since round 4. **Zero false cleans in
`assert_debits_equal_credits` this round — the eleventh consecutive round.**

`test_domain_scaffold_inventory.py`'s whole-file SHA-256
(`ef6d23fa49a7f15198afe0a060a6bc922bc944414aac8f1f15d84fb9cafd021a`) matches
round 14's recorded value exactly — unchanged since round 10, confirming
round 14's remediation did not silently touch the companion file (consistent
with its own explicit out-of-scope disposition).

## 9. Derivation query — 43 files; the 41-vs-42 discrepancy is RESOLVED

Run from the repository root, the recorded 6-token baseline:

```
rg -l 'BUG-050|test_financial_invariant_scaffold|SCN-MOD001-133|SCN-MOD001-132|test_domain_scaffold_inventory|test_scaffold_live' knowledge .claude | sort
```

**Result: 43 files.** Round 14's report recorded **41**; round 14's remediation
session then measured **42** and left the delta unreconciled, flagging it as
round 15's charge. Both numbers are correct, and the discrepancy is a
one-turn-of-the-clock effect, now proven by mtime rather than inferred:

| Step | Count | Delta |
|---|---|---|
| Round 14's own query, run before its report was written | **41** | — |
| `…SECURITY-REVIEW-ROUND14-2026-10-03.md`, mtime **2026-10-04 00:05** | **42** | +1 — round 14's own report. It did not exist when round 14 ran its query; round 14's §5 excludes itself by the same logic NR9-4/NR10-3 settled. **This is the entire 41-vs-42 delta.** |
| `BUG050-ROUND15-WATCHDOG-CHECKPOINT-2026-10-04.md`, mtime **2026-10-04 00:40** | **43** | +1 — created by *this* round's own dispatching watchdog session, consistent with `REVIEW_IN_FLIGHT.md`'s mtime of 00:39 |

**41 + 1 + 1 = 43, reconciling exactly.** Verified by sorting all 43 files by
mtime: the only entries later than round 14's report (00:05) are the round-14
remediation's own edits to files **already** inside the 41
(`CURRENT_STATE.md` 00:27, `CURRENT_HANDOFF.md` 00:28, `STATUS.md` 00:29,
`TEST_RESULTS.md` 00:30, `BUG-050…md` 00:37, `BUG_REGISTRY.md` 00:38,
`REVIEW_IN_FLIGHT.md` 00:39 — re-edits, not count deltas) plus the single new
watchdog checkpoint at 00:40. The round-14 remediation session's 42 was
therefore correct and benign; nothing was unaccounted for.

**No previously-unknown live-claim document surfaced. No stale-currency finding
this round — the fourth consecutive round with none.** The round-15 watchdog
checkpoint was read in full and correctly claims no verdict ("**No round-15
verdict or PASS claimed**"), so it introduces no false attestation. The 6-token
query is retained as the round-16 baseline; it is dynamic by design, and
round 16 should re-run it rather than trust 43.

## 10. Routine gates — this session's own runs

| Gate | Command | Result |
|---|---|---|
| Financial-invariant file alone | `pytest tests/contract/test_financial_invariant_scaffold.py -q` | **23 passed** |
| Slice-7 pair | `pytest tests/contract/test_financial_invariant_scaffold.py tests/contract/test_domain_scaffold_inventory.py -q` | **25 passed** |
| Full backend suite (`testpaths = ["tests"]`) | `pytest -q` | **195 passed** |
| Full incl. six domain scaffolds | `pytest tests app/modules -q` | **201 passed** |
| Lint | `ruff check .` from `backend/` | **All checks passed!** (clean tree-wide) |
| Format, Slice-7 pair | `ruff format --check tests/contract/test_financial_invariant_scaffold.py tests/contract/test_domain_scaffold_inventory.py` | **2 files already formatted** |
| Format, whole tree | `ruff format --check .` from `backend/` | **7 would reformat / 41 formatted** — the same 7 pre-existing, out-of-scope Slice-5/6 harness files rounds 13/14 recorded; none is Slice-7, none introduced by this lineage |
| Types | `mypy --strict .` from `backend/` | **Success: no issues found in 47 source files** |
| Types, Slice-7 pair | `mypy --strict` on both files | **Success: no issues found in 2 source files** |
| Capability validator | `knowledge/00-System/validate_capabilities.py` | **PASS — 7 capabilities, 0 errors** |

All counts match round 14's remediation record exactly (23 / 25 / 195 / 201,
47 mypy files, 7-would-reformat). No regression, and no inflated claim found in
that record's own numbers.

## 11. Tree integrity and scope boundaries honoured

| Boundary | Observed |
|---|---|
| `git rev-parse HEAD` start and end | `e516bedabf3d654ad3ae16d948b8f3522739ddc2`, unchanged |
| Slice-7 file hashes start and end | Identical (`5565338125bc…`, `ef6d23fa49a7…`) — **no source file was edited by this reviewer** |
| `git diff --check` (unscoped) | clean |
| Commit / push | none |
| `CURRENT_STATE.md`, `CURRENT_HANDOFF.md`, `BUG_REGISTRY.md`, `REVIEW_IN_FLIGHT.md`, `SCENARIOS.md`, `STATUS.md` | read only, **not modified** |
| Scenario promotion / BUG-050 closure | **none** — not this reviewer's authority |
| Throwaway artifacts | All nineteen variants under `/tmp/r15/`, outside the repository; the backend-tree copies used symlinked `.venv` and were never written back |
| Docker side effects | Only the harness's own disposable Postgres containers, each confirmed destroyed by `docker events` |

## 12. Scenario and closure assessment

| Item | Status |
|---|---|
| **SCN-MOD001-133** acceptance criteria (balanced set passes; unbalanced set fails citing the specific invariant) | **MET on live code** — `23 passed`; `v01_t6_only` confirms the negative route genuinely fails closed with the anchored `DEBITS_NE_CREDITS` match. **Not promotable**: R15-1/R15-2 are open P2 false-clean routes through the harness's own self-protection apparatus. |
| **SCN-MOD001-132** acceptance criteria | **MET on live code, independently re-verified live this round** (§6.2) — real Postgres at CAP-008's pinned digest; both negatives name exactly the right domain. **Not promotable**: R15-3 is an open P2 finding against SCN-132's own file. |
| **R14-1's four shapes** | **All four CONFIRMED CLOSED** (§3.1) |
| **R14-2** | **CONFIRMED FIXED, accurately** (§3.3) |
| **Companion inventory file gap** | **IN SCOPE** for BUG-050, finding R15-3 (§4.3.1 gives the reasoning) |
| **BUG-050** | Remains **OPEN**. Three new P2 findings. |
| **`assert_debits_equal_credits`** | Zero false cleans, eleventh consecutive round; hash-stable since round 4 |
| **R15-5 / R12-4 CAP-008 scope** | Open, non-blocking for BUG-050/SCN-132/SCN-133; needs its own disposition, now six rounds old |

**A note on the shape of this lineage, offered as judgment rather than a
finding.** Fifteen rounds have now each closed the specific shapes the prior
round named and been defeated by an adjacent one. R14-1 was closed correctly;
R15-1 is the same mechanism aimed at the closer; R15-2 is a known escape family
inherited by a new check. Every one of these is catchable only because the
check reasons about source text, and every fix extends that surface by one
more shape. The three findings here are individually cheap to fix (four names
in a set; a looser decorator match; one `pytestmark` assertion; the same guard
copied to the companion file), and a remediator should fix them — but the
recurring pattern is itself the signal round 14 already identified: a
source-text check cannot witness execution. The durable exit is the
execution-witness mechanism round 14 named and deliberately did not build
(e.g. a `pytest_sessionfinish` hook asserting the named negative tests
actually reported `passed`), which would close R14-1, R15-1, R15-2, R15-3,
R15-4, the conftest shape, the in-body `pytest.skip()` shape, and `-k`/`-m`
deselection **in one mechanism**, and would also be immune to the NF-7-class
expectation-set edit in a way no in-file check can be. Whether that is worth
building for a placeholder scaffold harness is a scoping judgment for the
remediating session and the orchestrator, not a security requirement this
reviewer imposes. Recorded, not performed.

## 13. Next legally allowed action

1. **A remediation pass** (retained routine-implementation tier; the security
   judgment above is Opus-reserved and must not be self-certified by the
   remediator) that disposes of R15-1, R15-2, R15-3 and R15-4. Per this bug's
   own repeated lesson, each fix must be proven by **reconstructing the shape
   and observing it fail**, not asserted in prose: `s1`/`s2`/`s3` (guard
   self-suppression), `s4`/`s5` (marker import shapes), `d3`/`d4` (companion
   file), `p1`/`x2` (module `pytestmark`). The remediator should also re-run
   the four R14-1 shapes to confirm no regression, and should decide
   explicitly — recorded either way — whether to take the one-mechanism
   execution-witness route (§12) instead of a fifth round of shape-by-shape
   source-text extension.
2. **A fresh round-16 `veyro-security-reviewer`** that independently verifies
   that remediation by execution (not by reading the note), re-runs the 6-token
   derivation query against this round's **43**-file baseline and reconciles
   any delta, and re-verifies both scenarios live with CAP-008 (available and
   working this round — §6.1).
3. **R15-5 / R12-4's CAP-008 scope-minimality disposition** should be taken
   out of the BUG-050 review clock and given its own owner-visible decision. It
   is non-blocking for Slice 7 and should stop aging inside these reports.
4. **Not yet:** promoting SCN-MOD001-132 or SCN-MOD001-133, closing BUG-050,
   or starting any next module (WIP=1; MOD-002+ remain locked).
5. **Orchestrator-only:** run `mr_verify.py` externally per §1.2, resolve the
   §1.2 session-id discrepancy before attesting, record this round's result in
   the durable files, and only then clear `REVIEW_IN_FLIGHT.md`'s round-15
   claim — per that file's own "clear on result recorded, not merely on
   subagent completion" protocol.

## Reviewer identification (for orchestrator-side `mr_verify.py`)

- **agentId:** `a6d1b165f6bc7f0de`
- **Transcript:** `/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/74fc7c27-158f-4682-8a81-668891a46625/subagents/agent-a6d1b165f6bc7f0de.jsonl`
- **Expected tier / role arguments:** `opus veyro-security-reviewer`
- **No self-attestation was performed or claimed** (§1.2).
