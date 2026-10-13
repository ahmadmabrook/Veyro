---
doc: SCN070-MIGRATION-ORDERING-LINT-SECURITY-REVIEW-ROUND3
module: MOD-001
requirement: GOV-01-R06 (Database-change policy/tooling), TSD §24.2
scenario: SCN-MOD001-070 (MIG · Blocker · negative)
round: 3
date: 2026-10-04
role: veyro-security-reviewer (Opus tier, fresh context)
verdict: BLOCKED
counts: P0=0 / P1=0 / P2=1 / P3=3
---

# SCN-MOD001-070 — Independent Security Review, Round 3

Fresh-context independent review of the **second** remediation
(`evidence/implementation/SCN070-ROUND2-REMEDIATION-2026-10-04.md`) of the
GOV-01-R06 migration-ordering lint.

## 1. Independence statement

This session began with zero prior context from the SCN-070 implementation,
round-1 remediation, or round-2 remediation sessions. No claim in those
records was accepted as true; every closure below was re-derived by direct
execution against purpose-built fixtures, with a **positive control** proving
the probe discriminates between the pre-fix and post-fix code. All fixtures
were created under `mktemp -d` (`/tmp/scn070r3.uzjU3J`), never inside the
repository tree. No repository file was modified except this report, which is
the only file this round authored.

## 2. Model / session evidence

- **Model identity (self-attested from this agent's own environment
  block):** `Opus 5 (1M context)`, exact model ID `claude-opus-5[1m]`.
  This satisfies the Opus-class attestation gate in the dispatch
  instruction and in `DEVELOPMENT_CONSTITUTION.md` model-routing terms.
- **How determined:** read directly from the runtime environment
  declaration provided to this agent at invocation ("You are powered by
  the model named Opus 5 (1M context). The exact model ID is
  `claude-opus-5[1m]`"). This is a self-report, not an externally
  cryptographically-verified attestation.
- **Dispatch linkage:** `knowledge/00-System/REVIEW_IN_FLIGHT.md`
  `current_claim` reads `IN_FLIGHT — SCN-MOD001-070 independent
  security/scenario review round 3, watchdog
  66643874-e295-4d53-a846-ee79cb6c3a44, dispatched
  2026-10-04T13:05:36.452509+00:00`. That claim matches this round; no
  collision was found and no second concurrent round-3 reviewer was
  observed.
- **Attestation is PARTIAL — stated plainly:** this agent could not read
  its own Claude Code session UUID or subagent transcript id from inside
  the sandbox, so the session id is recorded only indirectly via the
  watchdog id above. The **model-class** attestation (Opus) is firm; the
  **session-id** attestation is indirect. Because this round's verdict is
  `BLOCKED`, no PASS rests on the partial component.
- A pre-existing `SCN070-ROUND3-ACPX-RAW-2026-10-04.txt` (16:07 local) was
  observed in the security evidence directory with **no corresponding
  round-3 report on disk**, consistent with an earlier round-3 attempt that
  was interrupted before producing a verdict. It was not read for verdict
  purposes and contributed nothing to this report.

## 3. Baseline-integrity check

```
$ backend/.venv/bin/python knowledge/00-System/verify_baselines.py
Checked 4 of 4 expected governing baselines against .../PROJECT_INDEX.md:
  [MATCH] Gym_OS_Master_Product_Blueprint_v1_English.docx: 80f4b381...d426ef
  [MATCH] Veyro_Technical_System_Design_v1.4.1_English_FINAL.docx: 0d41c8a1...158e8
  [MATCH] Veyro_Engineering_Implementation_Plan_v1.4.1_...GOVERNING_BASELINE.docx: e5b5ec3b...866b6
  [MATCH] veyro-product-experience-design: c96f77abdf4345b231a60b37f832d76ac82cf52fb8b00ae3066f20bb10a36dbb
PASS — all 4 governing baseline hashes match ... exactly.   (exit 0)
```

Outcome: **PASS.** No `BASELINE_INTEGRITY_FAILURE`. Proceeded.

## 4. Scope

**In scope.** MOD-001 / SCN-MOD001-070 / GOV-01-R06 migration-ordering
lint, round-3 review of the second remediation: independent closure
verification of round-2 findings R2-1, R2-2, R2-3; the expanded mutation
battery; the lint's unit suite; and a regression scan of the surfaces the
second remediation changed (`tools/validate_migration_ordering.py`,
`tools/tests/test_validate_migration_ordering.py`,
`backend/migrations/TEMPLATE.md`, and the kill-check script).

**Explicitly out of scope.** DOM-002 round 5 is
`INTERRUPTED_IN_FLIGHT_EVIDENCE` and non-resumable. It was not read for
verdict purposes, not resumed, and is not commented on further here. Also
out of scope: BUG-048/BUG-050/CAP-008 work, any promotion decision, and
any control-plane state change.

**Change surface identified by `git diff` (second + first remediation are
both uncommitted against `HEAD` = `3552299`):**

```
backend/migrations/TEMPLATE.md                  |  28 ++
tools/tests/test_validate_migration_ordering.py | 450 +++++++++++++-
tools/validate_migration_ordering.py            | 158 ++++++-
3 files changed, 616 insertions(+), 20 deletions(-)
```

**Positive-control method.** Because both remediations are uncommitted,
`HEAD` is the *pre-round-1* lint, which is a coarse control for R2 findings.
To get an exact post-R1/pre-R2 control, three precise single-guard revert
variants were built from the current file by exact-match string replacement
(asserted to match exactly once), reproducing the behaviour each R2 fix
changed and nothing else:

| Control | Revert applied | Represents |
|---|---|---|
| `preR2_1_nosymlink.py` | `if path.is_symlink():` → `if False:` | post-R1, pre-R2-1 |
| `preR2_2_dupkey.py` | `if key in fields:` → `if False:` | post-R1, pre-R2-2 |
| `preR2_3_notdir.py` | `if not records_dir.is_dir():` → `if not records_dir.exists():`, `if records_dir.exists():` → `if False:` | post-R1, pre-R2-3 |
| `old_lint.py` | `git show HEAD:tools/validate_migration_ordering.py` | pre-R1 (coarse) |

The real tool was never reverted, stashed, or written to. `sha256` of the
live lint: `34b3a43b9d55cec552be096e4d70e76f986c302eff367e2f31f068607c4a81be`
(unchanged, re-asserted by the kill-check's own `finally`/`atexit` guard).

## 5. Per-closure verdicts

### R2-1 — symlinked child fail-open → **CLOSED**

Five symlink shapes were built. `--require-dir` was passed throughout.

```
$ python new_lint.py --records-dir $T/<fixture> --require-dir
```

| Fixture | New lint | `preR2_1_nosymlink` control | `old_lint` (pre-R1) | Discriminates? |
|---|---|---|---|---|
| `f_symdir` — valid 4-phase set **plus** symlinked `q4/` dir hiding a lone destructive `contract` | exit 1, `q4: SYMLINK_IN_RECORDS_TREE` | **exit 0, PASS** | **exit 0, PASS** | **YES** |
| `f_symfile` — symlinked `*.yaml` record (in-tree target) | exit 1, `0002_link.yaml: SYMLINK_IN_RECORDS_TREE` | **exit 0, PASS** | **exit 0, PASS** | **YES** |
| `f_symout` — symlink whose target is **outside** the tree | exit 1, `SYMLINK_IN_RECORDS_TREE` | exit 1 (BLOCKED, different reason) | exit 1 | no (control also rejects) |
| `f_dangling` — broken/dangling symlink | exit 1, `SYMLINK_IN_RECORDS_TREE` | exit 1 **unhandled traceback** | exit 1 **unhandled traceback** | partial (error *quality* only) |
| `f_loop` — mutual symlink loop `loopa ↔ loopb` | exit 1, 2× `SYMLINK_IN_RECORDS_TREE` | exit 1 | **exit 0, PASS** | YES vs pre-R1 |

**Verdict: CLOSED.** The decisive shape — the exact round-2 defect, a
destructive out-of-order `contract` hidden behind a symlinked directory
while real records exist — now fails closed at exit 1 with an explicit,
attributable, grep-able error naming the relative path and the reason. The
positive control is valid and discriminating: the identical fixture passes
clean (exit 0) with only the `is_symlink()` guard neutralised. The symlink
**loop** does not hang or recurse infinitely, which was a plausible failure
mode of a reported-rather-than-resolved design and is confirmed absent.

Honest caveats, stated rather than glossed: for `f_symout` the probe does
**not** discriminate — the control rejects it too, via `OUT_OF_ORDER_PHASE`
on the resolved target, so that row proves nothing about the fix. For
`f_dangling` both old and new exit non-zero; the fix converts an unhandled
`FileNotFoundError` traceback into a named problem, which is a real
diagnostic improvement but not a fail-open closure. Neither caveat
undermines the closure, which rests on `f_symdir`/`f_symfile`.

Judged against `SCENARIOS.md` SCN-MOD001-070 ("the migration-safety lint
**rejects** it") and the lint's own absolute docstring claim that every
other file anywhere in the tree is reported "not silently skipped", the
report-and-reject design is an adequate satisfaction of the requirement —
the requirement is rejection, not traversal.

### R2-2 — duplicate phase-key fail-open → **CLOSED** (for the key-collision shape)

```
$ python new_lint.py --records-dir $T/<fixture>
```

| Fixture | New lint | `preR2_2_dupkey` control | `old_lint` | Discriminates? |
|---|---|---|---|---|
| `d_exact` — `phase: contract` then `phase: expand` (reader sees `contract`) | exit 1, `DUPLICATE_FRONT_MATTER_KEY` | **exit 0, PASS** | **exit 0, PASS** | **YES** |
| `d_ws` — `phase:` then `  phase  :` (whitespace-differing) | exit 1, `DUPLICATE_FRONT_MATTER_KEY` | **exit 0, PASS** | **exit 0, PASS** | **YES** |
| `d_changeid` — `change_id: alpha` then `change_id: beta` | exit 1, `DUPLICATE_FRONT_MATTER_KEY` | **exit 0, PASS** | **exit 0, PASS** | **YES** |
| `d_case` — `Phase: contract` + `phase: expand` | **exit 0, PASS** | exit 0 | exit 0 | n/a — see R3-2 |
| `d_uni` — Cyrillic-`е` homoglyph `phasе: contract` + `phase: expand` | **exit 0, PASS** | exit 0 | exit 0 | n/a — see R3-2 |

**Verdict: CLOSED** for the defect R2-2 named. Duplicate keys are rejected,
not last-write-wins; key normalisation via `.strip()` means a
whitespace-padded repeat is correctly caught as the same key. The positive
control is valid and discriminating on all three duplicate shapes.

The two near-duplicate rows are **not** R2-2 recurrences — `Phase` and the
homoglyph `phasе` are genuinely distinct YAML keys, and the lint still
enforces the real lowercase `phase`, so no out-of-order record passes. They
surface a separate, lesser gap (unknown front-matter keys are silently
ignored), recorded below as **R3-2 (P3)**, not as a failed closure.

### R2-3 — `--require-dir` existing-file fail-open → **CLOSED**

```
$ python new_lint.py --records-dir $T/<target> --require-dir
```

| `--records-dir` target | New lint | `preR2_3_notdir` control | `old_lint` | Discriminates? |
|---|---|---|---|---|
| (a) regular file | exit 1, `RECORDS_PATH_NOT_A_DIRECTORY` | **exit 0, vacuous-pass NOTICE** | **exit 0, PASS** | **YES** |
| (b) symlink → file | exit 1, `RECORDS_PATH_NOT_A_DIRECTORY` | **exit 0, vacuous-pass NOTICE** | **exit 0, PASS** | **YES** |
| (c) symlink → real records dir | exit 0, PASS | exit 0 | exit 0 | intended (documented: works) |
| (d) non-existent path | exit 1, `MISSING_RECORDS_DIR` | exit 1 | **exit 0, PASS** | YES vs pre-R1 |
| (e) directory with mode `000` | **exit 0, PASS + false NOTICE** | exit 0 | exit 0 | **NOT CLOSED — see R3-1** |

**Verdict: CLOSED** for shapes (a)–(d), which are the shapes R2-3 named.
Not-a-directory now fails closed with or without the flag; the positive
control is valid and discriminating. Case (c) behaving as a pass is correct
and matches the documented contract in `TEMPLATE.md`.

Case **(e)** is a *new* finding of the same defect class, recorded as R3-1
below. It is not scored as an R2-3 closure failure — R2-3 did not name it —
but it is material, and it is the reason this round is `BLOCKED`.

## 6. Mutation battery and test suite — actual numbers

```
$ backend/.venv/bin/python -m pytest tools/tests/test_validate_migration_ordering.py -q
.............................                                            [100%]
29 passed in 0.36s
```

```
$ backend/.venv/bin/python .../scn070_ordering_lint_mutation_killcheck.py
m0 baseline (unmutated): SANE — unit exit 0, PASS — all 29 tests passed
M1  check_ordering returns [] immediately:            KILLED by unit+cli-negative+cli-lone
M2  ordering predicate accepts any skip-ahead:        KILLED by unit+cli-negative
M3  start-phase guard neutralized (R1-1, SURVIVED r1):KILLED by unit+cli-lone
M4  validate_fields returns [] immediately:           KILLED by unit
M5  main() rejection exit code neutralized (R1-2,
    SURVIVED r1):                                     KILLED by unit+cli-negative+cli-lone
M6  discovery narrowed back to glob('*.yaml'):        KILLED by unit
M7  UNRECOGNIZED_RECORD_FILE suppressed:              KILLED by unit
M8  --require-dir neutralized:                        KILLED by unit
M9  symlink guard neutralized (R2-1 fix removed):     KILLED by unit
M10 duplicate front-matter key last-wins (R2-2):      KILLED by unit
M11 non-directory records path accepted (R2-3):       KILLED by unit
real tool sha256 unchanged:  34b3a43b9d55cec552be096e4d70e76f986c302eff367e2f31f068607c4a81be
real test sha256 unchanged:  79d369d9cff6d14ac6540d76a7ac6407afbc4cac359ffb82df506ca47e6cc8c3
11/11 mutations killed; survivors=[]
round-1 survivors now killed: ['M3 ...', 'M5 ...']          (exit 0)
```

**Results: 29/29 unit tests pass; 11/11 mutants killed, 0 survivors.** The
two round-1 survivors (M3, M5) are independently confirmed dead.

**Is the battery self-satisfying?** Audited directly, and **no** — it is
structurally honest on four counts that an inflated battery would fail:
(1) every mutation anchor must match the real file **exactly once** or the
run aborts with `INVALID` exit 2 rather than claiming an unperformed kill;
(2) an unmutated baseline must be sane across all three controls before any
kill verdict is accepted, aborting with exit 2 otherwise; (3) the real
tool's and test file's SHA-256 are asserted unchanged in `finally`, at
`atexit`, and on `SIGINT`/`SIGTERM`; (4) it returns exit 1 on any survivor,
so it cannot report success without asserting. The round-2 re-anchoring of
M7 is documented in-script with its reason (the prior anchor produced a
strictly broader mutant), which is the right direction of correction.

Two honest limits on the battery: M9/M10/M11 are each killed by `unit`
only, meaning their kill depends entirely on the new unit tests rather than
on an end-to-end CLI control — adequate, but thinner than M1/M5. And the
battery's mutant set is defined by what the fixes *are*; it cannot discover
a fail-open nobody wrote a guard for, which is exactly how R3-1 below
survived a 11/11-killed battery.

## 7. Regression findings on the changed surfaces

| Check | Result |
|---|---|
| Broad/bare `except` swallowing | **Clean** — the only `except` in the lint is `except RecordError`, narrow and re-reported into `problems`. No bare `except:`, no `except Exception`. |
| New fail-open paths | **One found** (R3-1). All other new branches terminate in a `problems` append. |
| TOCTOU between stat and open | **No material exposure** — `is_dir()`/`is_symlink()` then `read_text()`; the tool is read-only over a repo-local tree and takes no action on the result beyond reporting. A race would change the diagnostic, not grant anything. |
| Path traversal / symlink escape | **Hardened** — symlinks are reported and never followed; `relative_to(records_dir)` is computed on non-followed paths, so no escape via link. |
| Non-deterministic ordering | **Clean** — `sorted(rglob("*"))` and `sorted(records)`; repeated runs over the real tree were byte-identical. |
| Exit-code correctness (0 only on clean pass) | **Correct except R3-1** — `main()` returns 1 whenever `problems` is non-empty, 0 otherwise. R3-1 is a case where `problems` is wrongly empty, not a case where a non-empty `problems` exits 0. |
| Credential-shaped values in new fixtures/tests (`.claude/rules/infra/secrets.md`) | **Clean — P0 count 0.** Grepped the lint, the 450-line test addition, and `TEMPLATE.md` for `password/secret/token/api_key/PRIVATE KEY/AKIA/ghp_/sk-/postgres(ql)://` — zero hits. Fixtures use `jane@example.com`, `j@e.com`, `SELECT 1`, `drop it`. No real member data; all records synthetic and self-labelled. |
| Absolute host paths in output | Present by design (`Records dir checked: <abs path>`, and inside `RECORDS_PATH_NOT_A_DIRECTORY`/`MISSING_RECORDS_DIR`). Local developer paths, not secrets; necessary for diagnostics. Recorded as R3-3 (P3) for CI-log hygiene only. |
| `TEMPLATE.md` accuracy | Checked against behaviour. Its claims about `UNRECOGNIZED_RECORD_FILE`, `DUPLICATE_FRONT_MATTER_KEY`, `SYMLINK_IN_RECORDS_TREE`, `RECORDS_PATH_NOT_A_DIRECTORY`, `--require-dir` and the vacuous-pass NOTICE all **match** observed behaviour, including the "symlink *to* the records dir is fine" carve-out. No documentation drift found. |
| CI wiring | **None exists.** No `.github/workflows/` directory is present; the only repo references to the lint are prose in `TEMPLATE.md`. The lint is a tool, not yet an enforced gate. Pre-existing and consistent with the round-1 R1-4 `--require-dir` recommendation for "future CI wiring"; recorded as R3-4 (P3) context, not a new defect. |

## 8. Findings

**Counts: P0 = 0 · P1 = 0 · P2 = 1 · P3 = 3.**

Fingerprint convention (introduced this round — the round-2 report used no
stable fingerprints): `SCN070-<DEFECT-CLASS>-<LOCATION>`, so a later round
can match a recurrence even if the finding number changes.

| ID | Sev | Fingerprint | Finding |
|---|---|---|---|
| R3-1 | **P2** | `SCN070-ENUM-FAILOPEN-unreadable-records-dir` | Unreadable records directory yields a clean exit-0 `PASS` that hides a destructive out-of-order record, with an affirmatively false NOTICE. |
| R3-2 | P3 | `SCN070-UNKNOWN-KEY-IGNORED-parse_front_matter` | Unknown front-matter keys are silently ignored, so a decoy `Phase:`/homoglyph key can show a reader a different phase than the one enforced. No ordering bypass. |
| R3-3 | P3 | `SCN070-ABSPATH-IN-DIAGNOSTIC-main` | Absolute host paths printed in output/diagnostics; CI-log hygiene only, no credential exposure. |
| R3-4 | P3 | `SCN070-NO-CI-GATE-wiring` | The lint is invoked by no CI workflow; nothing mechanically enforces GOV-01-R06 yet. Pre-existing, by design at this stage. |

Carried forward from round 2, re-verified and **not** re-counted here:
R2-4's unreadable-permission / non-UTF-8 **record-file** cases remain open
as a round-2 P3 (they exit 1; only the diagnostic is poor). See the
verification block inside R3-1.

### R3-1 (P2) — an unreadable records directory hides a destructive out-of-order record behind a clean `PASS`, even with `--require-dir`

**Invariant violated.** The same one R2-1 and R2-3 violated, and the one the
lint's own module docstring asserts absolutely: record discovery is
exhaustive — "never a silent partial pass", and "an unreadable or misplaced
file becomes a visible failure rather than an invisible omission". That
claim is still false for an unreadable *directory*. The in-code comment at
the symlink guard scopes the exception narrowly to records (files):
"unreadable-permission and non-UTF-8 **records** still raise". The
directory case does not raise — it passes.

**Mechanism.** `validate_directory()` gates on `records_dir.is_dir()`, which
succeeds on a mode-`000` directory (the inode is statable via the parent).
`discover_records()` then iterates `records_dir.rglob("*")`, and
`pathlib`'s globbing **swallows `OSError`/`PermissionError` and yields an
empty iterator**. `problems` is therefore empty, `main()` returns 0, and the
vacuous-pass branch prints a NOTICE asserting the directory "contains no
migration records" — a statement that is simply untrue.

**Reproduced decisively — same directory, same single record, only the mode
changed:**

```
$ printf -- '---\nchange_id: drop_members_table\nphase: contract\n...' \
    > $T/np/0001_destructive_contract.yaml

# readable:
$ python tools/validate_migration_ordering.py --records-dir $T/np --require-dir
BLOCKED: 1 problem(s) found:
  - 0001_destructive_contract.yaml: OUT_OF_ORDER_PHASE — change_id
    'drop_members_table' starts at 'contract' but must start with 'expand'
(exit 1)

$ chmod 000 $T/np
# unreadable, WITH --require-dir:
$ python tools/validate_migration_ordering.py --records-dir $T/np --require-dir
Records dir checked: /tmp/scn070r3.uzjU3J/np
NOTICE: records dir exists but contains no migration records — vacuous
        pass, no record was checked.
PASS — every migration record is complete and phase-ordered correctly
       (or no records exist yet).
(exit 0)
```

Root cause confirmed at the `pathlib` layer, not inferred:

```
$ python -c "..."
is_dir: True
rglob list: []
iterdir raised: PermissionError [Errno 13] Permission denied: '/tmp/.../np'
```

`rglob` returns `[]` where `iterdir()` raises. Run as uid 501, not root.

**Positive control.** Not applicable in the usual direction — this is a new
open defect, not a claimed closure. The control that matters is the
*readable* run above, which proves the record is genuinely destructive and
genuinely detected when enumeration succeeds; the exit-0 PASS is therefore
purely an artifact of the swallowed enumeration failure, not of the record
being acceptable. This also explains why the 11/11 kill-check missed it: no
guard exists to mutate.

**Distinct from round 2's R2-4 — verified, not assumed.** Round 2 did flag
unreadable-permission and non-UTF-8 **records** (files), and the second
remediation's own record honestly leaves them open ("a permission-denied or
undecodable record still dies with a traceback. Not [fixed]"). Both were
re-executed this round to confirm the distinction:

```
# unreadable RECORD FILE (mode 000), --require-dir
PermissionError: [Errno 13] Permission denied: '.../ur/0001.yaml'   (exit 1)
# non-UTF-8 RECORD FILE, --require-dir
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 40  (exit 1)
```

Those two are **fail-closed** on the only thing a CI gate consumes — they
exit 1 — and are merely ugly (an unhandled traceback instead of a named
problem). They remain the carried-forward round-2 P3 they already were and
are **not** re-counted in this round's totals. R3-1 is categorically
different and categorically worse: the unreadable **directory** exits **0**
with the `PASS` line. A reviewer reading round 2's "unreadable-permissions
still open" note could reasonably believe this whole class is fail-closed;
for the directory case it is not.

**Why P2 and why it blocks.** Severity is set by parity with the round-2
report's own scoring and reasoning. Round 2 rated R2-1 and R2-3 as P2 on the
grounds that "a genuinely destructive, genuinely out-of-order `contract`
record produces a clean exit 0 and the ordinary `PASS` line… the precise
condition SCN-MOD001-070 — a Blocker-tier negative scenario — exists to
prove impossible." R3-1 reproduces that condition exactly, and is in one
respect worse: the output does not merely stay silent, it affirmatively
reports a false fact about the tree it failed to read. The realistic trigger
is not exotic — a UID/ownership mismatch on a mounted volume in a container
or CI runner is the ordinary way a directory becomes unreadable, and it is
the same "green forever" failure mode that round 1 judged worth fixing in
R1-4 (typo'd path). `--require-dir`, the flag added precisely to stop
vacuous passes, does not help here.

**Direction of fix (not prescriptive).** Enumerate with a method that
surfaces the error — e.g. an explicit `os.scandir`/`iterdir` walk whose
`OSError` becomes a named `UNREADABLE_RECORDS_PATH` problem — so that an
un-enumerable tree is a visible failure. A narrow `os.access`/`iterdir`
probe on each directory before globbing would also close the named shape.
Whichever is chosen, the mutation battery should gain an M12 anchored on the
new guard, so a later removal is caught.

### R3-2 (P3) — unknown front-matter keys silently ignored

A record declaring `Phase: contract` (capital P, a genuinely distinct YAML
key) alongside `phase: expand` passes with exit 0; so does a Cyrillic-`е`
homoglyph `phasе: contract`. The lint enforces the real lowercase `phase`,
so **no out-of-order record passes** and the ordering invariant holds — this
is why it is P3, not a fail-open. But it is the same reader-versus-enforcer
divergence R2-2 was about, and it sits against the lint's own stated
preference for rejecting rather than silently skipping. A one-line
unknown-key rejection (any front-matter key not in `REQUIRED_FIELDS` becomes
`UNRECOGNIZED_RECORD_FIELD`) would close it and would also catch ordinary
typos in optional-looking fields.

### R3-3 (P3) — absolute host paths in diagnostics

`main()` prints `Records dir checked: <absolute path>`, and
`RECORDS_PATH_NOT_A_DIRECTORY`/`MISSING_RECORDS_DIR` embed the full path.
These are developer/CI paths, carry no credential-shaped value, and are
diagnostically useful; checked explicitly against
`.claude/rules/infra/secrets.md` and found **not** a violation. Noted only
so a future CI log-retention decision is made knowingly.

### R3-4 (P3) — no CI wiring

No `.github/workflows/` exists; nothing invokes the lint automatically.
GOV-01-R06's tooling exists but is not yet an enforced gate. Pre-existing
and consistent with MOD-001's planning scope and the R1-4 "any future CI
wiring should pass `--require-dir`" recommendation; recorded for continuity,
not charged against this remediation.

## 9. Verdict

**Decision rule applied** (stated before the verdict, as required): any open
P0 or P1 ⇒ `BLOCKED`; any P2 closure that could not be independently
verified ⇒ `BLOCKED`; any **newly-found open P2 that reproduces the
scenario's own forbidden condition** — a destructive, out-of-order
`contract` record producing exit 0 and the ordinary `PASS` line — ⇒
`BLOCKED`, by parity with the round-2 report's own reasoning for R2-1/R2-3;
fail closed on doubt.

Applied: P0 = 0, P1 = 0. All three round-2 P2 findings are independently
**CLOSED**, each with a valid discriminating positive control — this is real,
honest, load-bearing remediation work and the second remediation's claims
held up under adversarial re-execution. But R3-1 is an open P2 of exactly
the forbidden shape, reproduced decisively and reduced to its root cause.

**VERDICT: BLOCKED**

SCN-MOD001-070 must remain `EXECUTED — PENDING INDEPENDENT REVIEW`. It is
**not** promoted by this round.

## 10. Record-integrity statement

This round:

- did **not** promote SCN-MOD001-070 or any scenario;
- did **not** modify any product, tool, or test code — `tools/validate_migration_ordering.py`
  and `tools/tests/test_validate_migration_ordering.py` were opened read-only
  and their SHA-256 values are recorded unchanged in §4/§6;
- did **not** edit `CURRENT_STATE.md`, `CURRENT_HANDOFF.md`,
  `REVIEW_IN_FLIGHT.md`, `AUTONOMOUS_CONVERGENCE_STATE.json`, `STATUS.md`,
  `TEST_RESULTS.md`, `BUG_REGISTRY.md`, or any DOM-002 artifact;
- did **not** commit anything to git;
- authored exactly one file: this report;
- created all fixtures under `mktemp -d` (`/tmp/scn070r3.uzjU3J`), never
  inside the repository tree, and used only synthetic data — no real member
  data, no credentials, no paid service, no spend, no deploy. No
  owner-reserved restriction was engaged.
