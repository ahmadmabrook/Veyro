---
doc: M1-C-07 CAP-011 independent-report B1-B3 remediation
status: SYNTHETIC_ONLY_NOT_APPROVED
date: 2026-10-09
bounded-operation: M1-C-07
role: Sonnet IMPLEMENTATION (no approval, no self-review)
answers: knowledge/03-Modules/MOD-001/evidence/security/M1-C-07-CAP011-INDEPENDENT-DETERMINATION-2026-10-09.md §4-5 (B1, B2, B3)
---

# CAP-011 B1-B3: dispositions and real-file synthetic-copy drill

CAP-011 stays `QUALIFIED — NOT APPROVED`; `approved_by`/`next_review_due` unset; lifecycle not ACTIVE. This record closes B1-B3 for the narrow LOCAL scope **by correcting the description and producing evidence**. It does not touch B4-B6, create a CI run, or approve anything. The independent determination it answers is spent; a fresh one is required.

## 1. Dispositions

| ID | Resolution chosen | What changed |
|---|---|---|
| B1 | Option (b): correct the scope | Registry scope cell no longer says `HOME`/`TMPDIR` "confined". It states `HOME`, `TMPDIR`, `TMP`, `TEMP` are inherited **verbatim** (`INHERITED_ENV_VARS`, `child_env`), that test code runs with the caller's real home/temp, and that every prior drill's containment was supplied by the driver (`env -i` + disposable dirs), not by the wrapper. The wrapper's behaviour was **not** changed. |
| B2 | Correct the overclaim | Wrapper docstring item 4 (and the registry's symlink sentence) no longer present the scan as the only/complete bound. Stated: the scan covers the collection target only; the import closure (`backend/tests/harness/`, conftest chain, reached via `-m` putting `backend` on `sys.path`) is outside it; a symlinked/substituted module there would execute without refusal; none exists today (reviewer's `find`, not re-run here); control gap, not closed. |
| B3 | Retain the single target; produce real-file evidence | Drill below on a byte-identical copy of the real file. Registry now states the target spawns child processes outside the wrapper's argv control. |

The wrapper edit is docstring-only: the AST with the module docstring blanked is identical before/after (checked). Wrapper SHA-256 changed `df0c857e…3d85d` → `626210e6f5c7385e7a4e7b1a07bfcf784494eb2fd014616f745da23f0abb88cb`. Earlier evidence that cites `df0c857e…` describes the same executable code; its hash is stale only as a file identifier.

Also added to the wrapper docstring: an "Environment honesty" paragraph (B1) and the statement that `idempotency-contract` spawns further processes (B3).

## 2. Real-file inspection (B3)

`tools/tests/test_validate_idempotency_contract.py`, 669 lines, SHA-256 `f5d5fc135e1f4c880bfc04897829501967459c553ab9b718026f2f908a31d301` (equals the hash the determination recorded). It does `sys.path.insert(0, <tools/>)` and imports `validate_idempotency_contract` — **required supporting input**, SHA-256 `3336e41c8355e4f45b4293197a3fb82e35c2d4d622f1de71b5fa5f916ae9f41c` (imports only `argparse, json, re, sys, dataclasses, pathlib, typing`; no network, no `environ`, no `subprocess`). The test uses `tempfile.TemporaryDirectory` and `subprocess.run([sys.executable, <validator script>, <tmp json>], capture_output=True)` in one test (`test_cli_exit_code_matches_verdict`): 1 positive + 6 denied = **7 child processes**. No `env=` argument, so children inherit the pytest child's environment. All values are synthetic. `backend/pyproject.toml` (SHA-256 `039332c96ab93d82de930d1c84e3351a160829604126868da3a2a8fdfdd40695`) is the borrowed config; its only pytest key is `testpaths`.

The wrapper, validator and test file are untracked in Git (`??`); `backend/pyproject.toml` is tracked. The three untracked inputs are pinned here only by working-tree hashes.

## 3. Drill

Method: a fresh `mktemp -d` tree holding **only** the four copied files above (hashes source-vs-copy compared: IDENTICAL), run via the copied wrapper under `env -i PATH=/usr/bin:/bin HOME=<disposable> TMPDIR=<disposable> LANG=C`. Interpreter `backend/.venv/bin/python` — CPython **3.14.5**, pytest **9.1.1**, iniconfig **2.3.0** (the locally installed set; **not** the CI-lock 3.13 / iniconfig 2.3.1 set; no network or venv build this operation). The wrapper's `REPO_ROOT` resolved to the temp tree, so pytest never received a Veyro path. Scripts: `/tmp/b3drill2.sh` (disposable, not committed). pytest was run only on the temp copy.

| Case | Expected | Observed |
|---|---|---|
| P1 positive, real copied test via wrapper | rc 0 | rc 0, `33 passed`; wrapper line `suite=idempotency-contract rc=0` |
| P2 repeat | identical | rc 0, `33 passed` |
| N1 copied validator neutered (`evaluate_declaration` returns `[]` immediately) | tests fail, not denial | rc 1, `22 failed, 11 passed`, "pytest reported test failures" |
| N2 test file replaced by symlink to outside tree | refuse before pytest | rc 2, `DENY: symlink refused in the path to the suite` |
| N3 ambient `PYTEST_ADDOPTS=-x` | refuse | rc 2, `DENY: PYTEST_ADDOPTS is set…` |
| N3b ambient `PYTHONPATH=/tmp` | refuse | rc 2, `DENY: PYTHONPATH is set…` |
| N4 supporting `validate_idempotency_contract.py` absent | not a pass | rc 2, collection error `ModuleNotFoundError`, "not a usable result" |

N1 shows the target is discriminating (the real tests detect a broken lint) and that rc 1 is reported as test failure, not denial. N4 shows the supporting module is a hard input.

**Subprocess argv / child-environment boundary (C1).** A probe block was inserted into the *copied* validator only (guarded by `__name__ == "__main__"`; positive run still `33 passed`), logging each grandchild's argv, environment and interpreter flags. 7 grandchild runs observed (1 + 6, as read from the test). Findings:

- argv: `[<interpreter>, <tree>/tools/validate_idempotency_contract.py, <json under the test's TemporaryDirectory>]` — chosen by the test file, not the wrapper. The temp directory sits under the disposable `TMPDIR`, because `TMPDIR` is inherited verbatim.
- environment: `HOME` and `TMPDIR` equal the caller-supplied values **verbatim** (B1 confirmed empirically); an injected non-allowlisted variable (`EXTRA_AMBIENT`) was absent; `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` propagated; the only other keys (`PYTEST_CURRENT_TEST`, `PYTEST_VERSION`, `LC_CTYPE`, `__CF_USER_TEXT_ENCODING`) were added by pytest/CPython/macOS, and `TZ` was passed in by the driver.
- interpreter flags in the grandchild: `-E`, `-s`, `-B` all **off**. Isolation applies to the pytest process, not its children. Practical exposure is low here because the child env is already an allowlist with no `PYTHON*` variable, but the wrapper does not guarantee it.

**Side effects / hashes.** The pristine tree (sha256 of every file) before vs after all runs: identical — no `__pycache__`, cache dir or other write (`-B`, `-p no:cacheprovider`). The disposable `HOME` held no entries. The four Veyro source hashes before vs after: identical. Cleanup: every disposable tree, home and output directory removed (`ls /tmp/veyro-b3*` empty; two directories from an earlier aborted first-pass script of mine were removed by name).

An earlier version of the script ran the probe case incorrectly (the probe was appended after the validator's own `sys.exit`, so it never fired and the case printed no data); it was corrected and the whole script re-run. The numbers above are from the corrected run; the pass/fail results for P1-N4 were identical across both runs.

## 4. Non-pytest validation

- `python -I -c ast.parse` of `tools/run_scoped_pytest.py`: parses; docstring-blanked AST identical to the pre-edit copy.
- `knowledge/00-System/validate_capabilities.py`: parses the edited CAP-011 row (17 columns, same as CAP-012) and reports the expected fail-closed `CAPABILITY_NOT_APPROVED` holds for CAP-011/CAP-012 only (3 messages each, 6 total) — the intended hold, not a parse error. Not a pass.
- No pytest, CI, scanner or mypy was run on any Veyro path.

## 5. Residuals (not cured here)

1. B1: test code runs with the caller's real `HOME`/temp. Option (a) (confine in the wrapper) remains available and stronger; not taken.
2. B2: no import-closure scan. Extending the scan to `backend/tests/**` is the alternative; not taken.
3. B3: the target spawns unmanaged children (above). The drill used the local venv (3.14.5, iniconfig 2.3.0), macOS arm64 only; it is evidence about the file's behaviour on this interpreter, not about the CI closure. It ran a *copy*; nothing here says the file passes inside the Veyro checkout, which is intended.
4. B4-B6 are untouched and independently fatal to verdict 2: no CI run, workflow uncommitted, CI lock/matrix defects. The four inputs remain uncommitted, so reviewed bytes are pinned only by the hashes above.
5. `module-capabilities.yaml` was not edited (it contains no "confined" claim and points at the registry as authoritative).

## 6. Next independent-review boundary

Verdict 1 (local, narrowly scoped) needs a **fresh** `veyro-security-reviewer` determination with a new `REVIEW_IN_FLIGHT.md` claim written *before* dispatch (not done here). It should review: the corrected CAP-011 row, `tools/run_scoped_pytest.py` (`626210e6…abb88cb`), and this record, and may re-check any hash above. It should rule specifically on whether residuals 1-2 are acceptable as disclosed or require option (a)/closure-scan. No run of any Veyro test is permitted until that determination is APPROVED.
