# Gate 2 (module-deps) — Verdict C implementation record

**Model:** `claude-sonnet-5` (environment-reported model ID, verbatim).

**Authorized by:** Verdict D of
`knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-ARCHITECTURE-DECISION-2026-10-05.md`
(fresh Opus `veyro-lead`, 2026-10-05) — the single bounded
`veyro-implementer` dispatch, strictly the five items listed there.

**This is an implementation record, NOT a review and NOT a scenario PASS
claim.** Verdict D routes the next step to a gate-2-scoped
`veyro-code-reviewer`; no review was performed by this dispatch, no
`REVIEW_IN_FLIGHT.md` claim was made, and no scenario status marker was
edited.

No commit, no `git add`, no push was performed. All changes below remain
uncommitted working-tree modifications alongside the rest of the
session's pre-existing WIP (~34 modified / many untracked files),
untouched by this dispatch except as listed under "Files changed."

---

## Item 1 — Duplicate-prefix rejection in `parse_module_manifest`

**Done.** Added a per-module `seen_prefixes_this_module` set inside the
existing `for prefix in prefixes:` loop in `parse_module_manifest`
(`tools/validate_architecture_gates.py`). An exact duplicate entry
within one module now raises
`GateInputError(f"module {name!r} has duplicate owned_table_prefixes entry {prefix!r}")`
— this reuses the existing mechanism: every `GateInputError` raised
inside the module-deps gate's manifest-loading path is caught once, at
the `run_module_deps_gate` call site, and wrapped into a
`Violation("MODULE_DEPS_GATE_INPUT_INVALID", "-", str(exc))`, exactly
the same way every other input error in this function already surfaces
(no parallel error-rendering path was added). The message contains the
literal substring `duplicate owned_table_prefixes entry` and names both
the module and the offending prefix, mirroring the existing
`owned_schemas` duplicate-rejection style Verdict C cites for parity.

The pre-existing cross-module overlap check
(`if mod_a == mod_b: continue`, then `pre_a.startswith(pre_b) or
pre_b.startswith(pre_a)` → `GateInputError`) was left untouched — same-
module nested prefixes (`["cal_", "cal_event_"]`) still pass, and
cross-module overlap is still rejected with no exception path.

**Tests added** in `tools/tests/test_validate_architecture_gates.py`,
next to the existing rule-7 tests:

- `test_rule7_duplicate_owned_table_prefixes_entry_is_error` — a module
  declaring `["cal_", "cal_"]` is asserted to produce
  `MODULE_DEPS_GATE_INPUT_INVALID` (via the existing
  `_assert_md_input_error` helper) AND the violation detail is asserted
  to contain `duplicate owned_table_prefixes entry`, `'calendar'`, and
  `'cal_'`.
- `test_longest_prefix_cross_module_control_longer_prefix_attributed_correctly`
  — see the LIMITATIONS section below for why this, not a fully
  ambiguous cross-module longest-match race, is the decisive test that
  is actually reachable.
- The pre-existing
  `test_longest_prefix_ownership_resolution_same_module_nested_prefixes`
  (same-module nesting ACCEPTED) and
  `test_rule7_prefix_that_is_a_prefix_of_another_is_error` (cross-module
  overlap REJECTED) were left passing, unweakened, as the explicit
  controls for cases 1 and 2.

### Decisive longest-match assertion — honest limitation

The dispatch instructions asked for the longest-match resolution to be
"demonstrably exercised" with an identifier matching both of one
module's nested prefixes, plus "a cross-module control proving a
longer-prefix-owned table is attributed correctly," and explicitly
allowed stating if a fully decisive assertion is not reachable.

**It is not fully reachable, by design, and that is the point of
Verdict C's rule 7.** `_resolve_owner`'s longest-match loop
(`tools/validate_architecture_gates.py`, in `_resolve_owner`) only ever
has more than one *candidate* prefix matching the same identifier when
two declared prefixes are a literal string-prefix of one another. Rule
7 bans that shape globally **except** when both prefixes belong to the
same module — and when both belong to the same module, the "longer" and
"shorter" candidates resolve to the identical owner, so no identifier
can ever reach `_resolve_owner` with two matching prefixes that disagree
about who owns the table. A genuinely decisive test (one where picking
the wrong candidate would change the reported owner) would require two
*different* modules' overlapping prefixes to reach runtime resolution —
exactly the input shape rule 7 rejects at manifest-parse time, before
`_resolve_owner` is ever called. I did not find, and do not believe
there exists, a way to construct that case through the public
`run_module_deps_gate`/CLI surface without first disabling rule 7 itself
(which is out of scope — rule 7 is the thing being preserved).

What I added instead, as the closest available control:
`test_longest_prefix_cross_module_control_longer_prefix_attributed_correctly`
exercises two *different*, non-overlapping modules where one's prefix
(`billing_order_`) is longer than the other's (`mem_`) but the two never
share a matching identifier (rule 7 permits this — they do not overlap).
A table (`billing_order_items`) that only the longer prefix matches is
asserted to resolve to its true owner (`billing`) via a
`CROSS_DOMAIN_SQL_IMPORT` citing `membership -> billing`, not to the
other module and not as unowned. This proves cross-module attribution
correctness in the ordinary (non-ambiguous) case, but it is **not** a
test of competing same-identifier candidates across modules — that
remains, correctly, unreachable.

The existing same-module nested-prefix test
(`test_longest_prefix_ownership_resolution_same_module_nested_prefixes`)
was left as the one and only accepted shape under which two prefixes
can both match an identifier at all; I did not find additional
discriminating power to add to it beyond what it already asserts (PASS,
no `CROSS_DOMAIN_SQL_IMPORT`), for the same structural reason above —
same-module nesting can never produce a wrong-owner outcome, by the
invariant Verdict C itself states.

## Item 2 — Docstring and in-file comment updates

**Done.**

- `tools/validate_architecture_gates.py`'s gate-2 input-contract
  docstring (the `## Module dependency/SQL gate` section, previously
  lines ~174-178) replaced the stale "two declared prefixes where one is
  a prefix of the other, across modules and including duplicates" with
  an explicit three-case statement: same-module nesting ACCEPTED (and
  named as the only reachable shape for rule 5's longest-match
  resolution); cross-module overlap ERROR with no exception path; exact
  same-module duplicate ERROR as malformed input. It cites
  `GATE2-ARCHITECTURE-DECISION-2026-10-05.md` Verdict C by name. The
  existing "this gate's input contract is not yet fixed by an ADR"
  sentence (end of the docstring, near `MODULE_DEPS_SOURCE_UNINSPECTABLE`
  discussion) was left exactly as-is — Verdict B only recommends an ADR
  and does not author one, so no ADR is claimed to exist.
- `tools/tests/test_validate_architecture_gates.py`'s
  `test_longest_prefix_ownership_resolution_same_module_nested_prefixes`
  comment, previously headed "ASSUMPTION (documented, not independently
  confirmed against the implementation)," was rewritten to cite
  `GATE2-ARCHITECTURE-DECISION-2026-10-05.md` Verdict C as the settling
  authority instead of presenting itself as an unconfirmed assumption,
  and now also cross-references the new duplicate-rejection test.

## Item 3 — Ruff findings

**Done, exactly the 3 named findings, nothing else.**

- `RUF100` at `tools/tests/test_validate_architecture_gates.py:1133`
  (unused `# noqa: F401` on the `try: from validate_architecture_gates
  import (...)` block) — the `# noqa: F401` comment removed; the names
  are genuinely used later in the file so no suppression was needed.
- `RUF100` at `tools/tests/test_validate_architecture_gates.py:1145`
  (unused `# noqa: F401,E402` on `from validate_architecture_gates
  import IMPLEMENTED_GATES`) — the `# noqa` comment removed entirely
  (ruff reported `E402` itself as a non-enabled rule in this project's
  config, so neither code needed suppression).
- `ISC004` at `tools/validate_architecture_gates.py:1797` (originally;
  shifted slightly by the docstring edit in item 2, landing at line
  ~1816 by the time this was fixed) — the four-line implicitly
  concatenated string literal inside the `notes +=
  [...]` list was wrapped in parentheses.

The 12 pre-existing `E501` findings on these two files were **not**
touched, by design, per the dispatch's explicit instruction not to
mass-fix them in this diff.

**Verification (exact command and result):**
```
backend/.venv/bin/ruff check tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py
```
```
All checks passed!
```
Exit code 0.

## Item 4 — Fixture-scoped scenario evidence

**Done.** See
`knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-VERDICT-C-SCENARIO-EVIDENCE-2026-10-05.md`
for the full criterion-by-criterion mapping and verbatim captured CLI
output for SCN-MOD001-006, -007, -095, -096, plus the Verdict A.4
default-invocation fail-closed proof. Summary:

- **Positive** (SCN-006): synthetic `membership`/`billing` pair, PASS,
  exit 0.
- **Negative 1** (SCN-007): same tree with `membership/service.py`
  edited to import `billing`'s raw ORM model → `CROSS_DOMAIN_SQL_IMPORT`
  naming both modules/domains, resolved path, and `relpath:lineno`, FAIL,
  exit 1.
- **Negative 2** (SCN-095 positive / SCN-096 negative): **all four**
  normative `BIDIRECTIONAL_PAIRS` entries were exercised in both
  directions (`COM-01↔COM-03`, `DAT-01↔REL-01`, `GRO-01↔ENG-01`,
  `LIF-01↔GOV-04`) — this exceeds the "at least one pair, state which
  were/weren't exercised" floor the dispatch instructions set as
  acceptable; all eight runs (4 pairs × 2 directions) are captured
  verbatim with exit codes.
- **Negative 3** (Verdict A.4, not a SCN number): the real default
  invocation with no `contracts/modules/ownership.json` →
  `MODULE_DEPS_GATE_INPUT_INVALID`, ERROR, exit 2 — recorded as the
  correct fail-closed proof, not a defect.
- Every artifact in that evidence file states "fixture-scoped; real-tree
  domain ownership DEFERRED" on its face, and makes no real-tree PASS
  claim.
- No scenario is declared PASS/MET; `SCENARIOS.md`, `STATUS.md`,
  `TEST_RESULTS.md`, `CURRENT_STATE.md` were not edited.

## Item 5 — CI fact

**Reported, no CI change made.** The repository contains **no committed
CI configuration of any kind**. Confirmed this dispatch (cheap
re-confirmation of the orchestrator's already-established fact):

```
git ls-files | grep -E '\.github/|\.gitlab-ci|azure-pipelines|Jenkinsfile|circleci|\.buildkite'
```
→ no output (zero matches).

```
git ls-files | grep -E '\.ya?ml$'
```
→ only `knowledge/00-System/module-capabilities.schema.yaml`,
`knowledge/00-System/skl-rule-id.schema.yaml`, and the two
`module-capabilities.yaml` module manifests (MOD-000, MOD-001) — no
workflow files.

```
git grep -l -- '--gate module-deps'
```
→ only knowledge markdown
(`knowledge/00-System/CURRENT_HANDOFF.md`,
`knowledge/03-Modules/MOD-000/evidence/handoff-archive/CHUNK-41-2026-09-18-round11-remediation.md`,
`knowledge/03-Modules/MOD-001/IMPLEMENTATION.md`,
`knowledge/03-Modules/MOD-001/SCENARIOS.md`) — no workflow invokes the
gate.

**Conclusion:** no committed workflow invokes `--gate module-deps` with
repo defaults; CI is not red today, because there is no CI. Verdict
A.4's unresolved premise ("if a committed workflow invokes `--gate
module-deps` with repo defaults, CI is red today by design") is
therefore moot/not-yet-live. Choosing between A.4's two legal
resolutions (pin the CI step to a fixture tree with explicit flags and
label it fixture-scoped, vs. hold the CI step unwired with the gap
disclosed) remains deferred, as instructed — no CI change was made.

---

## Verification commands and exact results

**Focused new/changed tests:**
```
backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -k "prefix or duplicate" -q
```
```
......                                                                   [100%]
6 passed, 84 deselected in 0.03s
```

**Full `tools/tests/` suite:**
```
backend/.venv/bin/python -m pytest tools/tests/ -q
```
```
........................................................................ [ 44%]
........................................................................ [ 88%]
...................                                                      [100%]
163 passed in 2.24s
```
No pre-existing failures were present before or after this diff — all
163 tests pass cleanly both times this was run during the dispatch.

**Ruff, both files:**
```
backend/.venv/bin/ruff check tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py
```
```
All checks passed!
```
Exit code 0.

---

## Files changed (all remain uncommitted WIP)

- `tools/validate_architecture_gates.py` — duplicate-prefix rejection
  (item 1), docstring update (item 2), ISC004 fix (item 3). This file
  was already untracked (`??`) at dispatch start — it is new, not a
  modification of a tracked file, per the repository's own `git status`
  at dispatch start.
- `tools/tests/test_validate_architecture_gates.py` — two new tests
  (item 1), comment update (item 2), two RUF100 fixes (item 3). Also
  already untracked (`??`) at dispatch start, for the same reason.
- `knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-VERDICT-C-SCENARIO-EVIDENCE-2026-10-05.md`
  — new file, item 4.
- `knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-VERDICT-C-IMPLEMENTATION-2026-10-05.md`
  — this file, new.

No other file in the working tree was touched. All pre-existing
modified (`M`) and untracked (`??`) files from other in-flight work
(SCN-070, DOM-002, the new `backend/app/modules/*` scaffolds, etc.) were
left exactly as found — confirmed by `git status --porcelain` before and
after this dispatch showing no additional files beyond the four listed
above.

No `contracts/modules/ownership.json` was created. No real-tree domain
binding was authored. No paid service, real member data, deploy, or
material product/pricing/business/architecture/scope change was
involved.

---

## LIMITATIONS (honest, not absorbed silently)

1. **Fully decisive cross-module longest-match assertion is not
   reachable** through the public `run_module_deps_gate`/CLI surface,
   by the structural reason explained in detail under Item 1 above:
   Verdict C's own rule 7 bans the only input shape (two different
   modules with overlapping prefixes) that would let two candidate
   prefixes disagree about ownership. The added
   `test_longest_prefix_cross_module_control_longer_prefix_attributed_correctly`
   is the closest available control (non-overlapping cross-module
   longer-vs-shorter prefix, correct attribution) but does not test
   competing candidates.
2. **§6.3 pair directions:** exceeded the floor — all four normative
   pairs were exercised in both directions (8 runs total), not just one.
   No gap here, noted for completeness since the dispatch instructions
   allowed partial coverage if budget-constrained.
3. **E501 findings left unfixed by design** — 12 pre-existing line-length
   findings on these two files were explicitly out of scope per the
   dispatch instructions and were not touched.
4. **Real-tree gate-2 activation remains DEFERRED** — no
   `contracts/modules/ownership.json` was authored or proposed; this
   stays owner-reserved per Verdict A, out of scope for this dispatch.
5. **DOM-001 (Appendix I) re-verification** — SCN-MOD001-007's closing
   clause ("proves DOM-001") was not independently re-verified against
   TSD Appendix I text by this dispatch; the evidence shows the gate
   produces the denial shape the scenario describes, but whether that
   constitutes a complete proof of DOM-001 as a named invariant is left
   to scenario review.
6. **Gate-2 input-contract ADR** (Verdict B's recommendation) was not
   authored — explicitly out of scope for this dispatch, routed to the
   lead's own next dispatch per Verdict D.

---

## Next step (per Verdict D, not performed here)

A gate-2-scoped `veyro-code-reviewer` independent review of this diff
and evidence set, followed by scenario review. No gatekeeper
involvement at this stage. This dispatch does not claim
`REVIEW_IN_FLIGHT.md`, does not perform that review itself, and does not
promote any scenario.
