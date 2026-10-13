# SCN-MOD001-070 — Migration-Ordering Lint: Independent Security/Scenario Review, Round 1

Date: 2026-10-04
Reviewer: fresh-context independent `veyro-security-reviewer` (Opus tier), round 1.
Scope: SCN-MOD001-070 ONLY. I authored none of the material under review.

## Verdict

**BLOCKED (findings require remediation)**

**P0=0 / P1=1 / P2=5 / P3=5**

The lint is real, correct on every case I exercised, and the evidence record's
three factual claims all reproduce exactly. But the executed controls do **not**
genuinely establish the scenario's own literal acceptance clause: the single
code path that rejects a destructive `contract` migration with *none* of its
predecessors present is covered by **zero** control, and a mutant that
neutralizes it **survives the whole 6-test suite and the recorded CLI negative
control green** (mutant M3 below). A separate mutant that neutralizes the
rejection exit code also survives green (M5). Promotion on the present
controls would credit a Blocker-severity negative scenario to a control that
does not detect its own fail-open.

## Runtime identity evidence

- Agent id (session): `6b220074-1fd4-4dcb-9c3c-3ae09481a541` (`CLAUDE_CODE_SESSION_ID`); `CLAUDE_CODE_CHILD_SESSION=1`, `AI_AGENT=claude-code_2-1-274_agent`, `CLAUDE_EFFORT=high`.
- Per `knowledge/05-QA/tools/mr_verify.py`'s own documented finding, no environment variable exposes the resolved model; the transcript `model` field is the real signal. I therefore make **no self-attestation of model identity** — the orchestrator must run `mr_verify.py` against my transcript for the above session id and expect the Opus family.

## Integrity / fail-closed compliance

- Read-only on all product, tool and test code. Every mutation probe ran in throwaway copies under `/tmp` only.
- `tools/validate_migration_ordering.py` SHA-256 `d3d61ca12eaf68da1fc791941383c19eaa448360d4f494e13c97d891f86caf00`; `tools/tests/test_validate_migration_ordering.py` SHA-256 `780c573869f2013268199ebb3ce74ad8d03d80b1c8eeacdc6d2c04789e534d9e`. Both diffed byte-for-byte against the pristine `/tmp` base copy after all probes: **IDENTICAL**. Neither appears in `git status --porcelain`.
- All `/tmp` probe trees (`/tmp/scn070_mut`, `/tmp/scn070_r1_probe`) deleted and absence confirmed.
- `git status --porcelain` on the review targets shows only pre-existing uncommitted work present in this session's own opening snapshot (`SCENARIOS.md`, `REQUIREMENTS.md`, `tools/validate_capability_manifest.py`). I edited no tracked file. No commit, push, stash, reset or checkout was run. The 255+ file uncommitted body of work is preserved.
- I did **not** promote SCN-MOD001-070, did not edit its `SCENARIOS.md` status, and did not certify MOD-001. I did not read-for-review, resume or touch DOM-002 round 5, BUG-048, SCN-MOD001-009, R04/ADR-010 A2, SCN-067, or module certification.
- Owner-reserved absolutes respected: no spend, no real member data (all fixtures synthetic), no deploy, no scope change.

## The verbatim acceptance text (the standard)

`knowledge/03-Modules/MOD-001/SCENARIOS.md:1652-1656`, quoted verbatim:

> **SCN-MOD001-070 · MIG · Blocker · GOV-01-R06, negative · Automated · veyro-security-reviewer/Opus · EXECUTED — PENDING INDEPENDENT REVIEW (2026-10-04)**
> Steps: a deliberately out-of-order destructive (contract-phase)
> migration attempted before its expand+backfill+switch predecessors have
> run. Expected: the migration-safety lint rejects it — companion
> negative to 022.
> Execution evidence: `evidence/implementation/SCN070-MIGRATION-ORDERING-EXECUTION-2026-10-04.md` (synthetic CLI negative exit 1 with `OUT_OF_ORDER_PHASE`, ordered control exit 0; 6/6 unit tests). No PASS/promotion before fresh independent review.

### Clause-by-clause judgment

| Clause | Met? | Basis |
|---|---|---|
| "a deliberately out-of-order destructive (contract-phase) migration attempted before its **expand+backfill+switch** predecessors have run" | **PARTIALLY MET** | The executed negative is `expand` + `migrate` + `contract` — contract missing only its `switch` predecessor. Two of the three named predecessors *were* present. The clause's broadest and purest instantiation (contract with none of its predecessors) is handled correctly by the real lint (probe P-LONE, exit 1) but is exercised by **no** unit test and **no** recorded control, and mutant M3 proves that path is entirely unguarded. See R1-1. |
| "Expected: the migration-safety lint rejects it" | **MET at execution time, NOT regression-protected** | Reproduced: exit 1, `OUT_OF_ORDER_PHASE`, naming `0003_contract.yaml`, the `change_id`, and the missing `switch`. But the rejection *signal* (the non-zero exit) has zero automated coverage — mutant M5 survives green. See R1-2. |
| "companion negative to 022" | **MET, organizationally** | SCN-MOD001-022 (`SCENARIOS.md:732`) PASSed via the **runtime** harness against disposable Colima/Postgres; SCN-070 is discharged by a **static text lint**. The two companions share no instrument. This split is not my invention and not a new deviation — three prior independent reviews already ratified it (`GOV01-R02-MIGRATION-SAFETY-HARNESS-INDEPENDENT-REVIEW-2026-10-03.md:113`, `...-SECURITY-REREVIEW-R3-2026-10-03.md:256`, `...-SECURITY-REREVIEW-R5-2026-10-03.md:175`), and the harness source itself declines to reimplement it (`backend/tests/integration/test_migration_safety_harness.py:10-12`, `backend/tests/harness/migration_safety.py:285-288`). Recorded for transparency as R1-11, not scored as a defect. |

### Governing requirement

`knowledge/03-Modules/MOD-001/REQUIREMENTS.md:370-400` (GOV-01-R06, "Database-change policy/tooling"). Implementation obligation: "a lint rejecting a destructive (contract-phase) migration that isn't preceded by an expand+backfill+switch sequence". Acceptance criteria: "the lint rejects an out-of-order destructive migration; a valid 4-phase migration passes". Evidence obligation: "a synthetic 4-phase migration run end to end against a throwaway schema, **including** a deliberately-destructive migration attempted out of order and proven rejected." OUT of scope: "any actual product schema — none exists yet."

### Phase vocabulary — verified, not assumed

I checked the correspondence rather than assuming it. The scenario says "expand+backfill+switch"; the lint implements `PHASE_ORDER = ["expand", "migrate", "switch", "contract"]` (`tools/validate_migration_ordering.py:65`). The bridge is TSD §24.2's own verbatim text as quoted in `REQUIREMENTS.md:374-377`: "Expand -> migrate/backfill -> switch reads/writes -> contract". The lint documents the equivalence explicitly at `:42-44` ("`migrate` covers 'migrate/backfill'"), and `backend/migrations/TEMPLATE.md:6-10` repeats it. **This is a documented equivalence, not a defect** — a real mismatch would have been a P1, and it is not one. Recorded as R1-10 (P3) only for the narrower point that nothing checks a `migrate` record actually *describes* a backfill.

## Executed test and probe table

Every command run from `/Users/ahmadmabrouk/Desktop/Veyro`. `PY` = `backend/.venv/bin/python` (Python 3.14.5).

| # | Literal command | Observed result | Pass/Fail |
|---|---|---|---|
| T1 | `backend/.venv/bin/python tools/tests/test_validate_migration_ordering.py` | stdout `PASS — all 6 tests passed.`, exit **0** | PASS — record's "6/6" claim **reproduced** |
| T2 | `$PY tools/validate_migration_ordering.py --records-dir /tmp/scn070_r1_probe/negative` (fixture: `0001_expand.yaml`/`0002_migrate.yaml`/`0003_contract.yaml`, one `change_id`) | `BLOCKED: 1 problem(s) found:` / `0003_contract.yaml: OUT_OF_ORDER_PHASE — change_id 'add_widget_column' jumps to 'contract' without a preceding 'switch'`, exit **1** | PASS — record's exit-1 / `OUT_OF_ORDER_PHASE` / `0003_contract.yaml` claims all **reproduced verbatim** |
| T3 | same tool, `--records-dir /tmp/scn070_r1_probe/positive` (ordered `expand`/`migrate`/`switch`/`contract`) | `PASS — every migration record is complete and phase-ordered correctly (or no records exist yet).`, exit **0** | PASS — record's ordered-control claim **reproduced** |
| T4 | `$PY tools/validate_migration_ordering.py` (no args — real tree default) | `Records dir checked: .../backend/migrations/records` then PASS line, exit **0** | PASS, but **vacuous**: `backend/migrations/records/` contains only `.gitkeep`, zero `*.yaml`. Every repo-wide "`validate_migration_ordering.py` PASS" claim elsewhere in the vault is a pass over an empty directory. |
| P-LONE | fixture = a single `0001_contract.yaml`, no predecessors at all | `0001_contract.yaml: OUT_OF_ORDER_PHASE — change_id 'add_widget_column' starts at 'contract' but must start with 'expand'`, exit **1** | Real lint **correct**. But no test/control covers this; see M3. |
| P-YML | the *identical* out-of-order negative as T2 with `.yml` extensions | PASS line, exit **0** | **FAIL-OPEN** (R1-3) |
| P-SUBDIR | out-of-order negative nested in `<dir>/2026q4/` | PASS line, exit **0** | **FAIL-OPEN** (R1-3) |
| P-MD | lone out-of-order `contract` record as `0001_contract.md` | PASS line, exit **0** | **FAIL-OPEN** (R1-3) |
| P-BOGUSPATH | `--records-dir /tmp/scn070_does_not_exist_at_all` | PASS line, exit **0**, indistinguishable from a genuine pass | **FAIL-OPEN on misconfiguration** (R1-4) |
| P-DUP | one record with `phase: contract` then `phase: expand` (duplicate key) | PASS line, exit **0** — last value silently wins | Fail-open parser ambiguity (R1-8) |
| P-CASE | ordered `add_widget` expand/migrate/switch, then `contract` under `Add_Widget` | `0004_contract.yaml: OUT_OF_ORDER_PHASE — ... 'Add_Widget' starts at 'contract' but must start with 'expand'`, exit **1** | PASS — fails closed on change_id drift, correct and strict |
| P-REGRESS | full 4 phases then a 5th `expand` record | `0005_e2.yaml: OUT_OF_ORDER_PHASE — change_id 'c1' jumps to 'expand' without a preceding 'contract'`, exit **1** | Fails closed (safe) but the diagnostic **misnames the cause** (R1-7) |
| P-EMPTYDIR | existing but empty directory | exit **0** | PASS — documented intentional behavior |
| G1 | `ls -d .github/workflows` | `No such file or directory` | No CI exists; lint is not CI-wired (R1-5) |
| G2 | `grep -n "validate_" knowledge/05-QA/tools/run_regression.py` | gate list at `:39-42` contains only `validate_catalog.py` and `validate_capabilities.py` | Lint **absent** from the aggregate regression runner (R1-5) |
| I1 | `shasum -a 256` + `diff` of both real files against pristine `/tmp` base | `IDENTICAL_TOOL`, `IDENTICAL_TEST` | PASS — read-only constraint honored |

## Mutation table

Each mutant is a copy of the real lint under `/tmp/scn070_mut/<id>/tools/validate_migration_ordering.py`, with the real unit-test file copied alongside at `.../tools/tests/`. `m0` is an unmutated control. All deleted at closeout. "Killed" = the 6-test suite exits non-zero **or** the recorded CLI negative control stops exiting 1.

| Mutant | Location | Mutation | 6-test suite | CLI negative control | Killed? |
|---|---|---|---|---|---|
| m0 | `/tmp/scn070_mut/m0/` | none (control) | exit 0, 6/6 | exit **1**, `OUT_OF_ORDER_PHASE` | n/a — baseline sane |
| **M1** | `/tmp/scn070_mut/m1/` | `check_ordering` returns `[]` immediately (`:117`) | **exit 1** — `AssertionError: []` at `test_contract_without_switch_fails_closed`, line 81 | exit **0**, PASS line | **KILLED** (both) |
| **M2** | `/tmp/scn070_mut/m2/` | ordering predicate neutralized: `if phase_index == last + 1:` → `>= last + 1` (`:136`), i.e. any skip-ahead accepted | **exit 1** — `AssertionError: []` at line 81 | exit **0**, PASS line | **KILLED** (both) |
| **M3** | `/tmp/scn070_mut/m3/` | start-phase guard neutralized: `if phase_index != 0:` → `if False:` (`:124`) and `highest_index[change_id] = 0` → `= phase_index` (`:131`) — a `change_id` may begin at **any** phase | **exit 0, 6/6 green** | exit **1**, still correct (fixture's violating record never reaches the start guard) | **SURVIVED — decisive. P1 (R1-1).** Confirmed semantically live: against the P-LONE fixture the real lint exits 1 and M3 exits **0** with the PASS line, i.e. M3 silently accepts a destructive `contract` with no predecessors whatsoever. |
| **M4** | `/tmp/scn070_mut/m4/` | `validate_fields` returns `[]` immediately (`:99`) — no record-completeness check | **exit 1** — `AssertionError: []` at `test_missing_required_field_fails_closed`, line 95 | exit 1 (unaffected, as expected) | **KILLED** (by the field test) |
| **M5** | `/tmp/scn070_mut/m5/` | `main()`'s `return 1` → `return 0` on problems (`:201`) — rejection exit code neutralized | **exit 0, 6/6 green** | prints `BLOCKED: 1 problem(s) found` but exits **0** | **SURVIVED. P2 (R1-2).** No test exercises `main()` or any exit code; the only thing that ever observed exit 1 was a human reading a terminal. |

Two of five semantic mutants survive. The suite kills the two ordering mutants and the completeness mutant; it does not kill the start-guard mutant or the exit-code mutant.

## Findings

### R1-1 · **P1** · The start-phase guard is covered by zero control, and a fail-open mutant survives green
**File:line:** `tools/validate_migration_ordering.py:123-132` (the `if change_id not in highest_index:` branch and its `if phase_index != 0:` guard); `tools/tests/test_validate_migration_ordering.py:58-115` (no test reaches it); `knowledge/03-Modules/MOD-001/evidence/implementation/SCN070-MIGRATION-ORDERING-EXECUTION-2026-10-04.md:7` (the recorded negative control does not reach it either).

**What is wrong.** Every one of the six unit tests, and the recorded CLI negative control, seeds each `change_id` with an `expand` record first. The guard that rejects a `change_id` whose *first* record is already `migrate`, `switch` or `contract` is therefore never executed by any control. Mutant M3 neutralizes exactly that guard and the entire suite stays green (6/6) **and** the recorded negative control still exits 1 — because the fixture's violating record is reached through the *advance* path, not the *start* path. Proof that the mutant is not cosmetic: against probe P-LONE (a single `0001_contract.yaml`, no predecessors at all) the real lint exits 1 naming "starts at 'contract' but must start with 'expand'", while M3 exits **0** with the PASS line.

This matters because P-LONE is the acceptance text's own broadest reading — "attempted before its expand+backfill+switch predecessors have **run**", i.e. none of them present. The executed control proves only the weaker variant where two of three predecessors are present and `switch` is missing. A Blocker-severity negative scenario whose purest case is both unexercised and undetectably removable is not established by its controls. (Counter-argument, stated honestly: the executed control *does* instantiate one true reading of the clause, so this is a coverage-and-durability failure rather than a false claim. I still score it P1, consistent with this project's established calibration, where surviving mutants T5/T6/T7/T11 were each treated as blocking and required a fix before closure — see `knowledge/00-System/CURRENT_HANDOFF.md:211-231`.)

**Recommended fix.** Add two tests to `tools/tests/test_validate_migration_ordering.py`: (a) `test_lone_contract_with_no_predecessors_fails_closed` — a directory containing only a `contract` record, asserting exactly one problem containing `OUT_OF_ORDER_PHASE`, the `change_id`, the filename, and the substring `starts at 'contract' but must start with 'expand'`; and (b) the same for a lone `switch` record. Then re-run the M3 mutant and record that it is killed. Add the lone-contract case to the recorded CLI negative control as a second, separately-cited negative observation.

### R1-2 · **P2** · `main()`'s exit-code contract — the actual rejection signal — has no automated coverage; mutant M5 survives
**File:line:** `tools/validate_migration_ordering.py:188-205` (`main()`, `return 1` at `:201`); `tools/tests/test_validate_migration_ordering.py:36` (imports only `validate_directory`; `main` is never imported or called).

**What is wrong.** Every test calls `validate_directory` and inspects the returned problem list. Nothing tests `main()`, the printed output, or the process exit code. Mutant M5 (`return 1` → `return 0`) leaves the suite 6/6 green while the CLI prints `BLOCKED: 1 problem(s) found` and exits 0 — a perfect silent fail-open for any gate that keys on exit status. The evidence record rests its negative proof on "exit **1**" (`SCN070-...-2026-10-04.md:7`), a value no durable control protects.

**Recommended fix.** Add `test_cli_exit_code_is_1_on_violation` and `test_cli_exit_code_is_0_on_ordered_control` driving `main()` via `subprocess.run([sys.executable, TOOL, "--records-dir", fixture])`, asserting `returncode` **and** the presence of `OUT_OF_ORDER_PHASE` / absence of `BLOCKED` in stdout. Re-run M5 and record it killed.

### R1-3 · **P2** · Non-`.yaml` and nested records are silently ignored — the identical negative passes with exit 0
**File:line:** `tools/validate_migration_ordering.py:157` (`for path in sorted(records_dir.glob("*.yaml")):`).

**What is wrong.** `glob("*.yaml")` ignores `.yml`, `.md`, and anything in a subdirectory. Probes P-YML, P-MD and P-SUBDIR each took a genuinely out-of-order destructive record set and got exit **0** with the PASS line. `.yml` is an everyday spelling of a YAML file and `.md` is the extension of the very template authors copy from (`backend/migrations/TEMPLATE.md`), so both are live authoring-error paths. This contradicts the tool's own stated contract at `:56-57` — "fails closed as `OUT_OF_ORDER_PHASE` ... never a silent partial pass" — and the fail-closed posture `.claude/rules/infra/secrets.md` establishes as this project's default. Mitigation that keeps this at P2 rather than P1: `TEMPLATE.md:3` does prescribe `.yaml` explicitly, and `records/` currently holds no records at all.

**Recommended fix.** Either glob `("*.yaml", "*.yml")` and `rglob`, or — preferable, because it is explicit — enumerate every file in the tree that is *not* a matched record (excluding `.gitkeep`) and emit a `UNRECOGNIZED_RECORD_FILE` problem for each, so an ignored file is a failure rather than silence. Add a test for each of the three shapes.

### R1-4 · **P2** · A nonexistent or typo'd `--records-dir` returns exit 0 with the PASS line
**File:line:** `tools/validate_migration_ordering.py:152-153` (`if not records_dir.exists(): return []`) and `:203-205` (the PASS text).

**What is wrong.** Probe P-BOGUSPATH pointed the tool at `/tmp/scn070_does_not_exist_at_all` and got exit 0 and the ordinary PASS line. The docstring at `:150-152` justifies absent-directory-as-PASS for the legitimate "no product schema exists yet" state, which is reasonable — but the behavior conflates that state with a misconfigured path, so a future CI job with a mistyped or relocated `--records-dir` would pass green forever. The PASS text's own parenthetical ("or no records exist yet") does not distinguish the two.

**Recommended fix.** Keep exit 0 for the absent-directory case but print a distinct, grep-able line (e.g. `NOTICE: records dir does not exist — vacuous pass`), and add an opt-in `--require-dir` flag that makes a missing directory exit 1. Any future CI wiring should pass `--require-dir`. Add a test asserting the notice line and the flag's exit 1.

### R1-5 · **P2** · The lint is invoked by no automated gate
**File:line:** `knowledge/05-QA/tools/run_regression.py:39-42` (gate list contains only `validate_catalog.py` and `validate_capabilities.py`); no `.github/workflows` directory exists in the repository (verified, probe G1).

**What is wrong.** GOV-01-R06's IN-scope list (`REQUIREMENTS.md:383-384`) names "the migration-safety CI check (already named under GOV-01-R04)". The lint exists but is run only when a session manually remembers it — which is why the vault's many "`validate_migration_ordering.py` PASS" lines (e.g. `knowledge/00-System/CURRENT_HANDOFF.md:187`) are hand-run, and, per probe T4, vacuous over an empty directory. Combined with R1-2, a regression in the exit-code path would be caught by nothing at all. I note the dependency honestly: no CI exists anywhere in MOD-001 yet, so this is substantially GOV-01-R04 slice work rather than a defect in the lint, which is why it is P2 and not P1.

**Recommended fix.** Add the lint (with `--require-dir` per R1-4 once records exist) to `run_regression.py`'s gate list now — that is a one-line, zero-dependency change that makes the control load-bearing today — and carry the CI-workflow wiring as an explicit GOV-01-R04 obligation rather than an assumed one.

### R1-6 · **P2** · The evidence record is not re-runnable from its own text, and does not disclose its uncovered paths
**File:line:** `knowledge/03-Modules/MOD-001/evidence/implementation/SCN070-MIGRATION-ORDERING-EXECUTION-2026-10-04.md:7` and `:9`.

**What is wrong.** Everything the record asserts is **true** — I reproduced all three claims verbatim (T1/T2/T3), so there is no misstatement, and `:3` and `:9` are commendably careful about not claiming a PASS. But the record states no literal CLI command, no fixture directory path, no fixture file contents, and no captured stdout. Its load-bearing specific claim — that the output "named `0003_contract.yaml`" — depends entirely on fixture filenames the record never states; I could only verify it by reconstructing the fixture by inference. Its claim that "the fixture directory was removed automatically" is unverifiable for the same reason. Separately, `:9` asserts the two outcomes "distinguish the rejected destructive out-of-order contract from the accepted ordered control" without disclosing that no control touches the start-phase guard or the exit code — an omission that reads as more decisiveness than the controls carry. This falls short of the standard set by this module's own prior review records, which carry literal command tables (e.g. `GOV01-R02-SLICE7-...-ROUND4-2026-10-03.md:116`).

**Recommended fix.** Amend the record to embed the literal commands, the fixture path and the exact fixture front matter, and the verbatim stdout for both runs; and add one sentence naming what the controls do **not** cover (the no-predecessors start case, and `main()`'s exit code) pending R1-1/R1-2.

### R1-7 · **P3** · Backward-jump diagnostic misnames the cause
**File:line:** `tools/validate_migration_ordering.py:139` (`needed = PHASE_ORDER[last + 1] if phase_index > last else PHASE_ORDER[last]`) and the message at `:140-143`.

Probe P-REGRESS (four ordered phases, then a fifth `expand`) correctly exits 1, but reports "jumps to 'expand' without a preceding 'contract'" — `contract` had in fact already run; the real problem is a *regression*, not a missing predecessor. Fails closed, so the safety direction is right, but a misleading diagnostic costs a future reader a cycle. **Fix:** branch the message, emitting a distinct `OUT_OF_ORDER_PHASE — ... regresses from 'contract' to 'expand'` for `phase_index < last`, with a test.

### R1-8 · **P3** · Duplicate front-matter keys silently last-win
**File:line:** `tools/validate_migration_ordering.py:90-91` (`fields[key.strip()] = value.strip()`).

Probe P-DUP: a record declaring `phase: contract` and then `phase: expand` passes with exit 0, the second value silently overwriting the first. A record can thus misrepresent its own phase to a human reader while satisfying the lint. Low likelihood, but the parser is hand-rolled precisely to avoid a YAML dependency, so duplicate-key rejection is cheap. **Fix:** raise `RecordError` with a `DUPLICATE_FIELD` code on any repeated key, with a test.

### R1-9 · **P3** · Hand-maintained test list and hardcoded count in the direct-invocation path
**File:line:** `tools/tests/test_validate_migration_ordering.py:118-125`.

The `__main__` block hand-lists six calls and prints a hardcoded "all 6 tests passed." A newly added test function is silently not executed under the documented no-pytest invocation path (`:27-29`) — the very path the evidence record used and the one R1-1's new tests will be added to, so the two findings compound. **Fix:** iterate the module's own `test_*` callables via `globals()` and print the discovered count, so the number cannot drift from reality.

### R1-10 · **P3** · Nothing checks that a `migrate` record actually describes a backfill
**File:line:** `tools/validate_migration_ordering.py:95-108` (`validate_fields` checks presence/non-emptiness only).

The phase-vocabulary correspondence itself is sound and documented (see the section above) — **not** a defect. The residual gap is narrower: TSD §24.2 as quoted at `REQUIREMENTS.md:377-379` requires large backfills to be "online/resumable jobs with progress and throttling", and `TEMPLATE.md:33-36` tells authors to record that throttling in the `migrate` record's `lock_impact`, but the lint only checks that `lock_impact` is non-empty. A `migrate` record reading `lock_impact: n` passes (my own fixtures did). Not a SCN-070 clause; recorded so a future slice owns it. **Fix:** out of scope here — raise it against GOV-01-R06's backfill-throttling obligation.

### R1-11 · **P3** · The two "companion" scenarios share no instrument, and R06's bundled evidence obligation is discharged across two
**File:line:** `knowledge/03-Modules/MOD-001/REQUIREMENTS.md:388-390` (evidence obligation); `SCENARIOS.md:732-738` (SCN-022 PASS via runtime harness); `backend/tests/integration/test_migration_safety_harness.py:10-12`.

R06's evidence obligation reads as one exercise — a throwaway-schema 4-phase run "**including** a deliberately-destructive migration attempted out of order and proven rejected." In practice SCN-022 did the positive arm against real Postgres and the harness explicitly declines the out-of-order arm, which SCN-070 now discharges as a static text lint over YAML records with no schema involved. I reached this as a genuine question and resolved it as **acceptable**: R06's own OUT-of-scope line removes the product schema, the lint's docstring (`:12-23`) argues the deferral explicitly, and three prior independent reviews already ruled that SCN-070 belongs to the static lint and earns no credit from the harness. Recorded as a disclosure, not a defect. **Fix:** none required; a future schema-owning module should re-prove the out-of-order rejection against a real schema when one exists.

## Do the executed controls establish the scenario?

**They do NOT, not yet.** Specifically:

- What **is** genuinely established: the lint exists, is stdlib-only and read-only, and correctly rejects a `contract` record lacking its `switch` predecessor with exit 1 and a precise, file-and-change-id-naming `OUT_OF_ORDER_PHASE` diagnostic, while accepting an ordered four-phase control with exit 0. All three of the evidence record's factual claims reproduce verbatim. Two of the three ordering-logic mutants are killed by the existing suite. The lint also fails closed on several cases beyond its tests (lone contract, change_id case drift, phase regression). The evidence record is honest about not being a PASS.
- What is **not** established: that the control detects its own fail-open. The scenario's own literal "before its predecessors have **run**" case rides on a guard that no test and no recorded control touches, and mutant M3 removes that guard without turning anything red. The rejection exit code the record cites as proof is likewise unprotected (M5). Three further fail-open surfaces (R1-3, R1-4) let a genuinely out-of-order record set pass with exit 0 today, and the lint is wired into no automated gate at all (R1-5).

### Owed before promotion would be legitimate

1. **R1-1 (P1, blocking):** add the lone-`contract` and lone-`switch` no-predecessor tests, re-run mutant M3, and record it killed.
2. **R1-2 (P2):** add `main()`/exit-code tests via `subprocess`, re-run mutant M5, and record it killed.
3. **R1-3 / R1-4 (P2):** close the `.yml`/`.md`/subdirectory and missing-directory fail-opens, or record an explicit, owner-visible accepted-risk decision for each.
4. **R1-5 (P2):** register the lint in `run_regression.py` so it is load-bearing somewhere, and carry CI wiring as an explicit GOV-01-R04 obligation.
5. **R1-6 (P2):** amend the evidence record with literal commands, fixture contents, verbatim stdout, and an explicit statement of what the controls do not cover.
6. A **round-2 fresh-context independent review** re-running the mutation battery above against the fixed code. I am not eligible to review my own findings' remediation.

I did not promote SCN-MOD001-070, did not alter its `SCENARIOS.md` status, and did not certify MOD-001. This document is a round-1 finding record only.

---

## Orchestrator attestation addendum (2026-10-04, dispatching session)

Added by the dispatching/orchestrating session after the review returned.
The reviewer deliberately made **no** self-attestation of its own model
identity (per `mr_verify.py`'s own documented finding that no environment
variable exposes the resolved model); the following was produced
independently by the orchestrator against the reviewer's **actual**
transcript, not from anything the reviewer reported about itself.

**Model-route verification — PASS.**

```
backend/.venv/bin/python knowledge/05-QA/tools/mr_verify.py \
  ~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/6b220074-1fd4-4dcb-9c3c-3ae09481a541/subagents/agent-a18f7d9e9bda89a75.jsonl \
  opus veyro-security-reviewer
```

```json
{
  "verdict": "PASS",
  "reason": "46 turn(s), 100% consistent, model 'claude-opus-5' matches required tier 'opus'.",
  "models_observed": ["claude-opus-5"],
  "expected_tier": "opus"
}
```

- Reviewer agentId: `a18f7d9e9bda89a75`; agent type `veyro-security-reviewer`.
- Parent/orchestrating session: `6b220074-1fd4-4dcb-9c3c-3ae09481a541`.
- 46/46 assistant turns resolved to `claude-opus-5`, no mid-task
  substitution. Qualified Opus identity is therefore **verified**, not
  assumed — the review is tier-legitimate.

**Independent re-execution of the headline P1 (R1-1).** The orchestrator
did not accept R1-1 on the reviewer's word. It was reproduced from
scratch in a separate throwaway copy (`/tmp/scn070_verify/`, since
deleted), applying the same M3 mutation (`if phase_index != 0:` →
`if False:` in `check_ordering`'s start-phase guard):

| Check | Observed |
| --- | --- |
| 6 unit tests against the M3-mutated lint | `PASS — all 6 tests passed.`, exit 0 — **mutant survives** |
| Lone `contract` record, no predecessors, M3 lint | exit **0**, PASS line — destructive contract silently accepted |
| Same lone `contract` record, **real** unmutated lint | exit **1**, `0001_contract.yaml: OUT_OF_ORDER_PHASE — change_id 'drop_col' starts at 'contract' but must start with 'expand'` |

This confirms R1-1 as **CONFIRMED, not merely plausible**: the real lint
does implement the start-phase guard correctly, but no test and no
recorded control exercises it, so the guard is undetectably removable —
exactly the reviewer's finding. R1-1 stands on independent execution.

**Integrity re-verified by the orchestrator:**

- `tools/validate_migration_ordering.py` and
  `tools/tests/test_validate_migration_ordering.py` — absent from
  `git status --porcelain`; mtimes still 2026-09-29, i.e. untouched by
  this review.
- `SCENARIOS.md` carries a pre-existing `M` whose mtime (14:51:05 local)
  predates the review dispatch (~14:54 local) — it is the implementing
  session's earlier edit, **not** a reviewer modification. No scenario
  status was altered and SCN-MOD001-070 was **not** promoted.
- `git rev-parse --short HEAD` = `e481b81`, unchanged. 309 uncommitted
  entries preserved; no commit, push, stash, reset, or checkout.
- All mutation probes (reviewer's `/tmp/scn070_mut/*` and the
  orchestrator's `/tmp/scn070_verify/`) confirmed deleted.

**Status after this round:** SCN-MOD001-070 remains **EXECUTED — NOT
PROMOTED**, now with an independently-reviewed verdict of BLOCKED
(P1=1) against it. R1-1 requires remediation by an implementation-tier
session, followed by a fresh independent round 2 — this round is not a
self-approval and promotes nothing.
