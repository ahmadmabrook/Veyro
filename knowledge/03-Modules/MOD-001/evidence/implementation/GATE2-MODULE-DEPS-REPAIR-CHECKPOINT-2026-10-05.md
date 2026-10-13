---
doc: GATE2-MODULE-DEPS-REPAIR-CHECKPOINT
module: MOD-001
requirement: GOV-01-R04 (TSD §24.1 gate 2 — module dependency/SQL lint); SCN-MOD001-006/007/095/096
date: 2026-10-05
implemented_by: bounded ACPX continuation session (claude-opus-5[1m]) — repair of an interrupted prior session's WIP, not a fresh implementation
status: WIP REPAIRED AND GREEN LOCALLY — no review, no scenario promoted, no gate declared PASS, no commit/push. One semantic judgment call (fix 3) requires independent review before any promotion.
---

# Gate 2 (module-deps) — integration repair of interrupted WIP

## 1. What this session was and was not

A prior guarded Claude operation implementing TSD §24.1 gate 2 timed out
after 1200s, leaving two **untracked** WIP files in a non-importable state:

- `tools/validate_architecture_gates.py` (1846 lines)
- `tools/tests/test_validate_architecture_gates.py` (1854 lines)

This session was a **bounded repair of that session's test/CLI integration
only**. It did not author the gate, did not review it, did not promote any
scenario, did not declare any gate PASS, and did not commit or push. No
SCN-070, RLS-gate, permission-gate, or RLS/permission-architecture file was
touched. All prior uncommitted work across the repo is preserved; WIP=1
preserved; MOD-002 still locked.

## 2. Reproduced failure (as handed off)

```
backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py \
    -q --disable-warnings --maxfail=1
```

Observed, matching the handoff exactly: **53 passed, then
`test_scn006_own_schema_and_approved_interface_pass` FAILED** with
`NameError: name 'ast' is not defined` at
`tools/validate_architecture_gates.py:1730`.

## 3. The three defects found and fixed

All three were integration errors confined to gate 2's own code paths.

**Fix 1 — missing `import ast` (the handed-off failure).** Gate 2 uses `ast`
at ~20 sites (`ast.parse`, `ast.walk`, `ast.Import`, `ast.JoinedStr`, …) but
the module's import block (lines 249-258) never imported it. Added `import
ast` in alphabetical position. This is purely additive: gates 1 (RLS) and 4
(permission) do not use `ast`, and the full-suite result in §4 confirms no
behavioral change to them.

**Fix 2 — unowned-table disclosure named only a count, not the identifier.**
`test_unowned_table_reference_is_disclosed_not_flagged` asserts the report
notes name the unowned identifier; the implementation emitted only
`"1 unowned table identifier reference(s) (not flagged)"`. Changed
`_scan_sql_text` to return `list[str]` instead of `int` and added
`_unowned_note()`, which names the distinct identifiers, sorted, capped at
`_UNOWNED_NOTE_LIMIT = 20` with a `(+N more)` suffix so a large legacy tree
cannot flood a report. The gate's verdict is unchanged — an unowned
identifier is still disclosed, never flagged.

**Fix 3 — rule 7 prefix-overlap check rejected same-module nested prefixes
(SEMANTIC JUDGMENT CALL — see §6).** The overlap check compared all prefix
pairs, so one module declaring `cal_` and `cal_event_` was an input ERROR.
Narrowed the check to skip same-module pairs (`if mod_a == mod_b: continue`).

## 4. Actual verification results

All run with `backend/.venv/bin/python` (system `python3` is 3.9.6 and cannot
parse this tree's PEP 604 syntax).

| Check | Result |
|---|---|
| Focused file `tools/tests/test_validate_architecture_gates.py` | **88 passed, 0 failed** |
| Full `tools/tests/` suite (regression check on gates 1/4 and other tools) | **161 passed, 0 failed** |
| `python -m py_compile` on both WIP files | **OK** |
| `ruff check` (both files) | 3 findings, **all pre-existing** — see §5 |
| CLI end-to-end, 5 cases | **all 5 as expected** — see below |

CLI cases run against throwaway synthetic trees (`--gate module-deps`):

| Case | Expected | Actual |
|---|---|---|
| 1. clean 2-module tree | PASS / exit 0 | PASS, 5 subjects, exit 0 |
| 2. cross-domain deep import | FAIL / exit 1 | FAIL `CROSS_DOMAIN_SQL_IMPORT: billing -> membership`, exit 1 |
| 3. unowned SQL table | PASS, identifier named | PASS, note reads `1 unowned table identifier reference(s) (not flagged): unowned_legacy_table`, exit 0 |
| 4. same-module nested prefixes (fix 3) | PASS / exit 0 | PASS, exit 0 |
| 5. cross-module nested prefixes (rule 7 preserved) | ERROR / exit 2 | ERROR `ambiguous table prefix ownership: 'membership':'membership_' and 'billing':'membership_billing_' overlap`, exit 2 |

Two earlier CLI attempts failed closed with `MODULE_DEPS_GATE_INPUT_INVALID`
(missing `__init__.py`; manifest missing `"version": 1`). **Both were defects
in my throwaway fixture, not in the tool** — recorded because the gate
fail-closing on a malformed fixture is itself the correct observed behavior.

## 5. Limitations and things deliberately NOT done

1. **Lint debt left in place, by design.** `ruff check` reports 3 findings
   (`RUF100` ×2 at test lines 1133/1145 — vestigial `noqa` directives;
   `ISC004` at tool line 1797 — the multi-line coverage note's implicit
   string concatenation inside a list literal), plus **12 `E501`**
   line-length violations against the project's configured
   `line-length = 100` (tool lines 149, 1026, 1155; test lines 201, 202,
   232, 446, 849, 1043, and others). **None of these anchor on a line this
   session authored** — all are the interrupted session's own lines. I
   verified the `ISC004` concatenation is an intentional single sentence, not
   a missing comma, so it is a style finding and not a latent bug. Left
   unfixed to honor "preserve prior WIP" and keep the repair diff small and
   reviewable. Calibration note: committed `tools/` files are **not** clean
   under this same broad ruleset either (6 findings across three committed
   files: `EXE001`, `FLY002`, `DTZ011`), so repo-wide Ruff cleanliness is not
   an established convention here. **Follow-up: a style pass over both files
   before commit.**
2. **No ownership manifest exists.** `DEFAULT_MODULE_MANIFEST` is
   `contracts/modules/ownership.json`, which **does not exist**. Running
   `--gate module-deps` with repo defaults therefore fails closed:
   `MODULE_DEPS_GATE_INPUT_INVALID: module manifest … missing or a symlink`
   (correct behavior). Authoring that manifest means declaring domain
   ownership and public interfaces for the six domain modules under
   `backend/app/modules/` — a material contract/architecture artifact,
   outside this bounded repair's scope and **not created here**. Gate 2
   cannot run against the real tree until it exists.
3. **No scenario promoted.** SCN-MOD001-006/007/095/096 are **NOT** claimed
   PASS, MET, or promoted by this session. Local green tests are not a
   scenario verdict.
4. **No review, no self-review.** This session implemented the repair and
   therefore cannot review it. `REVIEW_IN_FLIGHT.md` was not read as a claim
   and no review was dispatched; no review claim was written.
5. **No commit or push.** Both files remain untracked.
6. **`_UNOWNED_NOTE_LIMIT = 20` is an unreviewed choice** by this session. No
   test pins the cap or the `(+N more)` suffix shape.

## 6. The one judgment call an independent reviewer must settle

Fix 3 is **not** a pure integration repair — it changes gate semantics, and I
resolved a genuine implementation-vs-test conflict in favor of the test.

The test (`test_longest_prefix_ownership_resolution_same_module_nested_prefixes`)
carries its own in-file comment marking its premise as an **"ASSUMPTION
(documented, not independently confirmed against the implementation)"**. Its
argument, which I found sound: overlap is only *ambiguous* across two
different modules, since the owner is identical either way when one module
declares both prefixes — and that is the only shape under which rule 5's
"longest matching `owned_table_prefixes`" is a reachable resolution rule at
all. Narrowing also keeps the cross-module test
(`test_rule7_prefix_that_is_a_prefix_of_another_is_error`) green, verified
both by that test and by CLI case 5.

Two disclosures a reviewer should weigh:

- Gate 2's input contract is **not yet fixed by an ADR** (unlike gates 1 and
  4, fixed by ADR-010) — the tool says so in its own report notes. So there
  is no authority this session could have checked the intent against, which
  is exactly why it is flagged rather than treated as settled.
- A side effect: an exact **duplicate** prefix within one module (e.g.
  `["cal_", "cal_"]`) is now also accepted. It is harmless for ownership
  resolution, no test covers it, and I did **not** add a new error class for
  it, which would have been unrequested scope.

If a reviewer judges the implementation's original global check correct, the
fix is to revert the three-line narrowing and delete that test instead.

## 7. Exact files changed by this session

Both were already-existing untracked WIP; no new source file was created.

- `tools/validate_architecture_gates.py` — fixes 1, 2, 3 (added `import ast`;
  added `_UNOWNED_NOTE_LIMIT`/`_unowned_note()`; `_scan_sql_text` now returns
  `list[str]`; `unowned_identifiers` is now a list; rule 7 skips same-module
  pairs).
- `tools/tests/test_validate_architecture_gates.py` — **not modified**.
- `knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-MODULE-DEPS-REPAIR-CHECKPOINT-2026-10-05.md`
  — this record.

## 8. Next legal action

Author `contracts/modules/ownership.json` (material artifact — needs its own
routing decision), **or** dispatch a fresh independent code review of gate 2
settling §6. Promotion of SCN-MOD001-006/007/095/096 is blocked on both.
