# SCN-070 round-4 root-cause correction — watchdog checkpoint (2026-10-04)

Bounded unit: MOD-001 / GOV-01-R06 / SCN-MOD001-070. Git HEAD `e481b814a80923849dddfe7a49319112aae7b023`. This records a substantive, uncommitted implementation produced by the prior ACPX Claude turn, which stopped before a final response or implementation report. The raw capture is `SCN070-ROUND4-ROOTCAUSE-ACPX-RETRY-RAW-2026-10-04.txt`. No ACPX writer or reviewer was live at watchdog inspection. This is **not** an independent review or scenario PASS.

## Changed strategy and evidence

`tools/validate_migration_ordering.py` now has a tri-state `acquire_records_dir()` using error-propagating `os.stat`/`os.lstat` and a single `run_validation()` result carrying both problems and the notice. `main()` consumes that result without a second `Path.exists()`/discovery pass. Tests cover the unreadable ancestor with a destructive record under default and `--require-dir` CLI modes, readable controls, absent/empty/wrong-type paths, symlinks, injected `PermissionError`/`EIO`, and structural single-acquisition locks. The round-3 record received dated append-only correction of its contradicted fail-closed assertion.

Watchdog independently executed after the prior ACPX turn stopped:

- `backend/.venv/bin/python -m pytest tools/tests/test_validate_migration_ordering.py -q`: **55 passed**.
- `backend/.venv/bin/python knowledge/03-Modules/MOD-001/evidence/implementation/scn070_ordering_lint_mutation_killcheck.py`: sane baseline, **20/20 mutants killed**, no survivors; tool and test hashes unchanged by the kill-check.
- `backend/.venv/bin/python -m mypy tools/validate_migration_ordering.py`: PASS, no issues.
- `backend/.venv/bin/python knowledge/00-System/verify_baselines.py`: **4/4 MATCH**.
- `git diff --check`: clean.
- `ruff check` on the two files: **not PASS** — 4 diagnostics (two EXE001 shebang/mode and two FLY002 fixture joins). Their disposition was not adjudicated in this checkpoint.

The root-cause correction and negative/mutation evidence are material progress, but the prior Claude turn has no final verdict, no independent review of this new snapshot, and no scenario promotion. SCN-070 remains pending independent assessment. DOM-002 round-5 remains interrupted, non-resumable, and outside this work unit. All pre-existing uncommitted work is preserved; no owner-stop condition observed.
