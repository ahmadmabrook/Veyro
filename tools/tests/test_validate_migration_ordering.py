#!/usr/bin/env python3
"""
Unit test for tools/validate_migration_ordering.py (MOD-001, GOV-01-R06).

Proves both directions against an isolated `tempfile.TemporaryDirectory`
fixture, never a real migrations tree — no real product schema exists yet
(R06's own "OUT of scope" line).

  1. test_empty_directory_passes — no records dir at all -> PASS (no
     product schema exists yet, this is not a missing-directory error).
  2. test_valid_four_phase_change_passes — a real
     expand->migrate->switch->contract sequence for one change_id, every
     TSD §24.2 field present -> PASS.
  3. test_contract_without_switch_fails_closed — the scenario's own
     literal case (a destructive contract-phase migration attempted out
     of order) -> OUT_OF_ORDER_PHASE, naming the change_id and the
     missing prior phase, not a silent partial pass.
  4. test_missing_required_field_fails_closed — a record missing
     `rollback_strategy` -> MISSING_REQUIRED_FIELD, naming the file and
     field.
  5. test_invalid_phase_value_fails_closed — a record with
     `phase: deploy` (not one of the 4 TSD stages) -> INVALID_PHASE.
  6. test_repeated_phase_is_allowed — two `expand` files for the same
     change_id before `migrate` -> PASS (multiple expand steps are a
     real pattern, not an ordering violation).

## Round-1 independent-review additions (2026-10-04)

`SCN070-MIGRATION-ORDERING-LINT-SECURITY-REVIEW-ROUND1-2026-10-04.md`
found that the six tests above leave two code paths covered by nothing,
and proved it with surviving mutants: neutralizing the start-phase guard
(mutant M3) and neutralizing `main()`'s rejection exit code (mutant M5)
both kept the suite 6/6 green. Added, grouped by finding — described, never
numbered, so this docstring cannot drift from the file again (round-2
finding R2-6 caught exactly that drift: the list stopped at "15-17" while
18 tests existed):

  R1-1 (P1): lone `contract` / lone `switch` with NO predecessors at all —
        the scenario's own broadest reading ("before its expand+backfill+
        switch predecessors have run", i.e. none present). The only tests
        that reach the start-phase guard, and what kills mutant M3.
  R1-2 (P2): `main()` driven as a real subprocess, asserting the process
        exit code (1 on violation, 0 on the ordered control) and the stdout
        text. The exit code is the actual rejection signal the evidence
        record rests on, and nothing tested it before — kills M5.
  R1-3 (P2): a `.yml`, a `.md`, and a nested-subdirectory record set, each
        of which previously passed with exit 0 while genuinely out of order
        -> now UNRECOGNIZED_RECORD_FILE. Plus `.gitkeep` staying ignored,
        so the real empty records dir still passes.
  R1-4 (P2): a missing `--records-dir` reports a vacuous-pass NOTICE and
        exit 0 by default, and fails closed with `--require-dir`.

## Round-2 independent-review additions (2026-10-04)

`...-SECURITY-REVIEW-ROUND2-2026-10-04.md` confirmed R1-1 … R1-6 closed by
execution, and found three further P2 fail-opens — two of which let a
genuinely destructive, genuinely out-of-order `contract` record produce a
clean exit 0 with the ordinary PASS line:

  R2-1 (P2): a symlinked child directory hid a destructive out-of-order
        record (`rglob` does not descend through one; `is_dir()` follows the
        link and skips it). Covered with the decisive mixed fixture (valid
        4-phase set + symlinked `q4/` holding a lone `contract`, so no
        vacuous-pass notice fires), its CLI form, a dangling `*.yaml`
        symlink, and a positive control that real subdirectories and
        symlink-free trees are unaffected.
  R2-2 (P2): a duplicated `phase:` key last-won, so a record a human reads
        as `contract` linted as `expand`. Covered in both orders, for a
        non-`phase` key, and with a positive control that a normal record
        and a colon-bearing value still pass.
  R2-3 (P2): `--require-dir` was inert when `--records-dir` resolved to an
        existing regular file. Covered with and without the flag, plus a
        positive control that a symlink TO a real records directory is
        still usable.

## Round-3 independent-review additions (2026-10-04)

`...-SECURITY-REVIEW-ROUND3-2026-10-04.md` independently closed R2-1/R2-2/
R2-3 and found one open P2:

  R3-1 (P2, architectural): `Path.rglob` swallows OSError/PermissionError
        and yields an empty iterator, so an unreadable directory was
        indistinguishable from an empty one — a mode-000 records dir holding a
        destructive out-of-order `contract` exited 0 with the PASS line and a
        NOTICE affirmatively claiming it held no records. No guard existed to
        mutate, which is why the 11-mutant battery missed it. Fixed at the
        enumerator (`enumerate_tree`), not with another top-level check.
        Covered by deterministic injected-`os.scandir` failures at both the
        root and a nested subtree, a readable/unenumerable same-tree
        discriminating pair, a live `chmod 000` drill, and two enumerator
        positive controls (symlinks still yielded-but-not-descended;
        a readable nested tree enumerated exhaustively and deterministically).

        The injected tests pass as any uid including root. The live chmod
        tests return early (skip) when the host does not actually enforce mode
        000 — running as root, or a permission-ignoring mount — rather than
        failing and manufacturing a platform false positive. On the
        remediation host (uid 501, APFS) mode 000 was verified enforced, so
        they genuinely executed.

Run directly with
`python3 tools/tests/test_validate_migration_ordering.py` (no pytest
dependency needed) or with pytest if available. The direct-invocation
path discovers `test_*` callables dynamically and prints the discovered
count, so a newly added test can never be silently skipped and the count
can never drift from reality (R1-9 — the previous hand-maintained list
would have silently not run any of the additions above).
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent / "validate_migration_ordering.py"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from validate_migration_ordering import (
    NOTICE_ABSENT,
    NOTICE_NO_RECORDS,
    RECORDS_PATH_ABSENT,
    RECORDS_PATH_DIRECTORY,
    RECORDS_PATH_ERROR,
    acquire_records_dir,
    enumerate_tree,
    run_validation,
    validate_directory,
)

VALID_FIELDS = {
    "owner": "jane@example.com",
    "lock_impact": "none",
    "rollback_strategy": "drop the new object",
    "validation_query": "SELECT 1",
}


def _write_record(root: Path, filename: str, change_id: str, phase: str, **overrides) -> None:
    fields = {"change_id": change_id, "phase": phase, **VALID_FIELDS, **overrides}
    lines = ["---"]
    for key, value in fields.items():
        if value is not None:
            lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    lines.append("Synthetic fixture record — not a real migration.")
    (root / filename).write_text("\n".join(lines), encoding="utf-8")


def test_empty_directory_passes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "does_not_exist"
        assert validate_directory(root) == []


def test_valid_four_phase_change_passes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_record(root, "0001_widget_expand.yaml", "add_widget_column", "expand")
        _write_record(root, "0002_widget_migrate.yaml", "add_widget_column", "migrate")
        _write_record(root, "0003_widget_switch.yaml", "add_widget_column", "switch")
        _write_record(root, "0004_widget_contract.yaml", "add_widget_column", "contract")
        assert validate_directory(root) == []


def test_contract_without_switch_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_record(root, "0001_widget_expand.yaml", "add_widget_column", "expand")
        _write_record(root, "0002_widget_migrate.yaml", "add_widget_column", "migrate")
        _write_record(root, "0003_widget_contract.yaml", "add_widget_column", "contract")
        problems = validate_directory(root)
        assert len(problems) == 1, problems
        assert "OUT_OF_ORDER_PHASE" in problems[0]
        assert "add_widget_column" in problems[0]
        assert "0003_widget_contract.yaml" in problems[0]


def test_missing_required_field_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_record(
            root, "0001_widget_expand.yaml", "add_widget_column", "expand",
            rollback_strategy="",
        )
        problems = validate_directory(root)
        assert len(problems) == 1, problems
        assert "MISSING_REQUIRED_FIELD" in problems[0]
        assert "rollback_strategy" in problems[0]


def test_invalid_phase_value_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_record(root, "0001_widget_deploy.yaml", "add_widget_column", "deploy")
        problems = validate_directory(root)
        assert len(problems) == 1, problems
        assert "INVALID_PHASE" in problems[0]


def test_repeated_phase_is_allowed():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_record(root, "0001_widget_expand_a.yaml", "add_widget_column", "expand")
        _write_record(root, "0002_widget_expand_b.yaml", "add_widget_column", "expand")
        _write_record(root, "0003_widget_migrate.yaml", "add_widget_column", "migrate")
        assert validate_directory(root) == []


# --- R1-1 (P1): the start-phase guard. Nothing above reaches it, because
# every fixture above seeds its change_id with an `expand` record first.
# Mutant M3 (`if phase_index != 0:` -> `if False:` plus
# `highest_index[change_id] = 0` -> `= phase_index`) survived the six tests
# above completely green. These two tests are what kill it.

def test_lone_contract_with_no_predecessors_fails_closed():
    """The acceptance clause's broadest reading: a destructive contract-phase
    migration attempted before ANY of its expand/backfill/switch predecessors
    have run — none of them present at all."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_record(root, "0001_widget_contract.yaml", "add_widget_column", "contract")
        problems = validate_directory(root)
        assert len(problems) == 1, problems
        assert "OUT_OF_ORDER_PHASE" in problems[0]
        assert "add_widget_column" in problems[0]
        assert "0001_widget_contract.yaml" in problems[0]
        assert "starts at 'contract' but must start with 'expand'" in problems[0]


def test_lone_switch_with_no_predecessors_fails_closed():
    """Same guard, non-destructive phase: a `switch` that never saw an
    `expand` or `migrate` must also fail closed, not just `contract`."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_record(root, "0001_widget_switch.yaml", "add_widget_column", "switch")
        problems = validate_directory(root)
        assert len(problems) == 1, problems
        assert "OUT_OF_ORDER_PHASE" in problems[0]
        assert "0001_widget_switch.yaml" in problems[0]
        assert "starts at 'switch' but must start with 'expand'" in problems[0]


# --- R1-2 (P2): main()'s exit-code contract. Every test above calls
# validate_directory() and inspects a returned list; nothing ran the CLI, so
# mutant M5 (main()'s `return 1` -> `return 0`) printed "BLOCKED" and exited 0
# while the suite stayed green. The evidence record's proof IS the exit code,
# so it needs a durable control.

def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True, text=True, check=False,
    )


def test_cli_exit_code_is_1_on_violation():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_record(root, "0001_widget_expand.yaml", "add_widget_column", "expand")
        _write_record(root, "0002_widget_migrate.yaml", "add_widget_column", "migrate")
        _write_record(root, "0003_widget_contract.yaml", "add_widget_column", "contract")
        result = _run_cli("--records-dir", str(root))
        assert result.returncode == 1, (result.returncode, result.stdout)
        assert "BLOCKED" in result.stdout, result.stdout
        assert "OUT_OF_ORDER_PHASE" in result.stdout, result.stdout
        assert "0003_widget_contract.yaml" in result.stdout, result.stdout


def test_cli_exit_code_is_0_on_ordered_control():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_record(root, "0001_widget_expand.yaml", "add_widget_column", "expand")
        _write_record(root, "0002_widget_migrate.yaml", "add_widget_column", "migrate")
        _write_record(root, "0003_widget_switch.yaml", "add_widget_column", "switch")
        _write_record(root, "0004_widget_contract.yaml", "add_widget_column", "contract")
        result = _run_cli("--records-dir", str(root))
        assert result.returncode == 0, (result.returncode, result.stdout)
        assert "BLOCKED" not in result.stdout, result.stdout
        assert "OUT_OF_ORDER_PHASE" not in result.stdout, result.stdout
        assert "PASS" in result.stdout, result.stdout
        # A pass over real records must NOT carry a vacuous-pass notice.
        assert "NOTICE" not in result.stdout, result.stdout


# --- R1-3 (P2): records the old `glob("*.yaml")` silently ignored. Each
# fixture below is a genuinely out-of-order destructive record set that
# previously produced exit 0 and the PASS line.

def test_yml_extension_record_is_not_silently_ignored():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_record(root, "0001_widget_expand.yml", "add_widget_column", "expand")
        _write_record(root, "0002_widget_contract.yml", "add_widget_column", "contract")
        problems = validate_directory(root)
        assert len(problems) == 2, problems
        assert all("UNRECOGNIZED_RECORD_FILE" in p for p in problems), problems
        assert any("0002_widget_contract.yml" in p for p in problems), problems


def test_markdown_record_is_not_silently_ignored():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_record(root, "0001_widget_contract.md", "add_widget_column", "contract")
        problems = validate_directory(root)
        assert len(problems) == 1, problems
        assert "UNRECOGNIZED_RECORD_FILE" in problems[0]
        assert "0001_widget_contract.md" in problems[0]


def test_nested_subdirectory_record_is_not_silently_ignored():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        nested = root / "2026q4"
        nested.mkdir()
        _write_record(nested, "0001_widget_expand.yaml", "add_widget_column", "expand")
        _write_record(nested, "0002_widget_contract.yaml", "add_widget_column", "contract")
        problems = validate_directory(root)
        assert len(problems) == 2, problems
        assert all("UNRECOGNIZED_RECORD_FILE" in p for p in problems), problems
        # The relative path, not just the bare filename, so the reader can
        # actually find the misplaced file.
        assert any("2026q4/0002_widget_contract.yaml" in p for p in problems), problems


def test_gitkeep_placeholder_is_ignored_without_a_problem():
    """The R1-3 fix must not break the live tree: `backend/migrations/records/`
    contains exactly one file, `.gitkeep`, and must still pass."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".gitkeep").write_text("", encoding="utf-8")
        assert validate_directory(root) == []


# --- R1-4 (P2): a nonexistent/typo'd --records-dir previously returned exit 0
# and the ordinary PASS line, indistinguishable from a genuine pass.

def test_missing_dir_with_require_dir_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "typo_does_not_exist"
        problems = validate_directory(root, require_dir=True)
        assert len(problems) == 1, problems
        assert "MISSING_RECORDS_DIR" in problems[0]
        assert "typo_does_not_exist" in problems[0]
        # Default behavior is unchanged — absent dir is still a pass.
        assert validate_directory(root) == []


def test_cli_missing_dir_prints_vacuous_pass_notice_and_exits_0():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "typo_does_not_exist"
        result = _run_cli("--records-dir", str(root))
        assert result.returncode == 0, (result.returncode, result.stdout)
        assert "NOTICE: records dir does not exist" in result.stdout, result.stdout
        assert "vacuous pass" in result.stdout, result.stdout


def test_cli_blocked_run_emits_no_vacuous_pass_notice():
    """Self-check on the R1-4 notice itself: an UNRECOGNIZED_RECORD_FILE run
    finds zero *records*, so a naive implementation prints "vacuous pass"
    directly above "BLOCKED" — self-contradictory, and the same
    misleading-diagnostic failure mode R1-7 describes. The notice belongs on
    the pass path only."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_record(root, "0001_widget_contract.yml", "add_widget_column", "contract")
        result = _run_cli("--records-dir", str(root))
        assert result.returncode == 1, (result.returncode, result.stdout)
        assert "UNRECOGNIZED_RECORD_FILE" in result.stdout, result.stdout
        assert "NOTICE" not in result.stdout, result.stdout
        assert "vacuous pass" not in result.stdout, result.stdout


def test_cli_require_dir_exits_1_on_missing_dir():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "typo_does_not_exist"
        result = _run_cli("--records-dir", str(root), "--require-dir")
        assert result.returncode == 1, (result.returncode, result.stdout)
        assert "MISSING_RECORDS_DIR" in result.stdout, result.stdout
        assert "NOTICE" not in result.stdout, result.stdout


# --- R2-1 (P2): a symlinked subdirectory hid a destructive out-of-order record
# behind a fully clean exit-0 PASS with no NOTICE, because `rglob` does not
# descend through symlinked directories and `is_dir()` follows the link.

def test_symlinked_subdir_hiding_destructive_contract_fails_closed():
    """The decisive R2-1 shape: a VALID complete 4-phase set for change_a, plus a
    symlinked child dir whose target holds a lone destructive `contract` for
    change_b. Real records are present, so neither vacuous-pass notice fires —
    this previously produced an indistinguishable false PASS."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "records"
        root.mkdir()
        hidden = Path(tmp) / "hidden"
        hidden.mkdir()
        _write_record(root, "0001_a_expand.yaml", "change_a", "expand")
        _write_record(root, "0002_a_migrate.yaml", "change_a", "migrate")
        _write_record(root, "0003_a_switch.yaml", "change_a", "switch")
        _write_record(root, "0004_a_contract.yaml", "change_a", "contract")
        _write_record(hidden, "0005_b_contract.yaml", "change_b", "contract")
        (root / "q4").symlink_to(hidden, target_is_directory=True)
        problems = validate_directory(root)
        assert len(problems) == 1, problems
        assert "SYMLINK_IN_RECORDS_TREE" in problems[0]
        assert "q4" in problems[0]


def test_cli_symlinked_subdir_exits_1_with_no_vacuous_notice():
    """Same shape through the CLI with --require-dir, the exact invocation a CI
    gate would use: must be exit 1, and must not claim a vacuous pass."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "records"
        root.mkdir()
        hidden = Path(tmp) / "hidden"
        hidden.mkdir()
        _write_record(root, "0001_a_expand.yaml", "change_a", "expand")
        _write_record(hidden, "0005_b_contract.yaml", "change_b", "contract")
        (root / "q4").symlink_to(hidden, target_is_directory=True)
        result = _run_cli("--records-dir", str(root), "--require-dir")
        assert result.returncode == 1, (result.returncode, result.stdout)
        assert "SYMLINK_IN_RECORDS_TREE" in result.stdout, result.stdout
        assert "NOTICE" not in result.stdout, result.stdout


def test_dangling_yaml_symlink_is_a_named_problem_not_a_traceback():
    """A broken `*.yaml` symlink used to reach parse_front_matter and die with an
    uncaught FileNotFoundError. Now caught at discovery."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "0001_x.yaml").symlink_to(root / "nope_does_not_exist.yaml")
        problems = validate_directory(root)
        assert len(problems) == 1, problems
        assert "SYMLINK_IN_RECORDS_TREE" in problems[0]
        assert "0001_x.yaml" in problems[0]


def test_real_subdir_and_symlink_free_tree_still_behave(
):
    """Positive control for R2-1: the symlink guard must not disturb either a
    legitimate all-real-records pass, or the real-subdirectory rejection R1-3
    already established."""
    with tempfile.TemporaryDirectory() as tmp:
        ok = Path(tmp) / "ok"
        ok.mkdir()
        _write_record(ok, "0001_a_expand.yaml", "change_a", "expand")
        _write_record(ok, "0002_a_migrate.yaml", "change_a", "migrate")
        _write_record(ok, "0003_a_switch.yaml", "change_a", "switch")
        _write_record(ok, "0004_a_contract.yaml", "change_a", "contract")
        assert validate_directory(ok) == []

        real_nested = Path(tmp) / "nested"
        (real_nested / "q4").mkdir(parents=True)
        _write_record(real_nested / "q4", "0001_b_contract.yaml", "change_b", "contract")
        problems = validate_directory(real_nested)
        assert len(problems) == 1, problems
        assert "UNRECOGNIZED_RECORD_FILE" in problems[0]
        assert "q4/0001_b_contract.yaml" in problems[0]


# --- R2-2 (P2): a duplicated `phase:` key let a record a human reads as
# `contract` lint as `expand` and pass green. Outcome turned purely on which
# duplicate landed last.

def _write_duplicate_phase_record(root: Path, filename: str, first: str, second: str) -> None:
    (root / filename).write_text("\n".join((
        "---", "change_id: add_widget_column", f"phase: {first}",
        "owner: jane@example.com",
        "lock_impact: DROP COLUMN — destructive, rewrites table",
        "rollback_strategy: restore from backup", "validation_query: SELECT 1",
        f"phase: {second}", "---", "",
        "Synthetic fixture record — not a real migration.",
    )), encoding="utf-8")


def test_duplicate_phase_key_contract_then_expand_fails_closed():
    """The decisive R2-2 shape: authoritative first line says `contract`, a later
    duplicate says `expand`. Previously PASS with exit 0."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_duplicate_phase_record(root, "0001_widget.yaml", "contract", "expand")
        problems = validate_directory(root)
        assert len(problems) == 1, problems
        assert "DUPLICATE_FRONT_MATTER_KEY" in problems[0]
        assert "'phase'" in problems[0]
        assert "0001_widget.yaml" in problems[0]


def test_duplicate_phase_key_fails_closed_in_either_order():
    """Order-independence: round 2 proved the old outcome flipped purely on which
    duplicate landed last. Both orders must now fail, and identically."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "transposed"
        root.mkdir()
        _write_duplicate_phase_record(root, "0001_widget.yaml", "expand", "contract")
        problems = validate_directory(root)
        assert len(problems) == 1, problems
        assert "DUPLICATE_FRONT_MATTER_KEY" in problems[0]


def test_duplicate_non_phase_key_also_fails_closed():
    """Any repeated key, not just `phase` — the same last-one-wins ambiguity
    applies to `change_id`, which would silently re-key an ordering chain."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "0001_widget.yaml").write_text("\n".join((
            "---", "change_id: real_change", "phase: expand",
            "owner: jane@example.com", "lock_impact: none",
            "rollback_strategy: drop it", "validation_query: SELECT 1",
            "change_id: other_change", "---",
        )), encoding="utf-8")
        problems = validate_directory(root)
        assert len(problems) == 1, problems
        assert "DUPLICATE_FRONT_MATTER_KEY" in problems[0]
        assert "'change_id'" in problems[0]


def test_single_keys_and_repeated_colons_in_values_still_pass():
    """Positive control for R2-2: the duplicate-key guard must not reject a normal
    record, nor a value that legitimately contains a colon (the parser splits on
    the FIRST colon, so `lock_impact: ACCESS EXCLUSIVE: ~200ms` is one key)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "0001_widget_expand.yaml").write_text("\n".join((
            "---", "change_id: add_widget_column", "phase: expand",
            "owner: jane@example.com",
            "lock_impact: ACCESS EXCLUSIVE: ~200ms, low-traffic window only",
            "rollback_strategy: DROP INDEX CONCURRENTLY IF EXISTS ix_w",
            "validation_query: SELECT count(*) FROM w WHERE c IS NULL", "---", "",
            "Free text below the fence is ignored: including colons.",
        )), encoding="utf-8")
        assert validate_directory(root) == []


# --- R2-3 (P2): --require-dir was inert when --records-dir resolved to an
# existing non-directory; rglob on a non-directory yields nothing, so exit 0.

def test_regular_file_as_records_dir_fails_closed_without_the_flag():
    with tempfile.TemporaryDirectory() as tmp:
        plain = Path(tmp) / "plainfile.txt"
        plain.write_text("not a records directory\n", encoding="utf-8")
        problems = validate_directory(plain)
        assert len(problems) == 1, problems
        assert "RECORDS_PATH_NOT_A_DIRECTORY" in problems[0]
        assert "plainfile.txt" in problems[0]
        # And with the flag, which round 2 proved inert for this shape.
        assert validate_directory(plain, require_dir=True) == problems


def test_cli_regular_file_as_records_dir_exits_1_with_require_dir():
    with tempfile.TemporaryDirectory() as tmp:
        plain = Path(tmp) / "plainfile.txt"
        plain.write_text("not a records directory\n", encoding="utf-8")
        result = _run_cli("--records-dir", str(plain), "--require-dir")
        assert result.returncode == 1, (result.returncode, result.stdout)
        assert "RECORDS_PATH_NOT_A_DIRECTORY" in result.stdout, result.stdout
        # The old output claimed a vacuous pass here; it must not anymore.
        assert "NOTICE" not in result.stdout, result.stdout
        assert "vacuous pass" not in result.stdout, result.stdout


def test_symlink_to_a_real_records_dir_is_still_usable():
    """Positive control for R2-3: `is_dir()` follows symlinks, so passing a symlink
    to a real records directory as --records-dir must keep working. Only symlinks
    found *inside* the tree are rejected (R2-1)."""
    with tempfile.TemporaryDirectory() as tmp:
        real = Path(tmp) / "real_records"
        real.mkdir()
        _write_record(real, "0001_widget_expand.yaml", "add_widget_column", "expand")
        _write_record(real, "0002_widget_contract.yaml", "add_widget_column", "contract")
        link = Path(tmp) / "records_link"
        link.symlink_to(real, target_is_directory=True)
        problems = validate_directory(link, require_dir=True)
        # Reached and linted the records through the link — the ordering violation
        # is found, not a RECORDS_PATH_NOT_A_DIRECTORY or a vacuous pass.
        assert len(problems) == 1, problems
        assert "OUT_OF_ORDER_PHASE" in problems[0]
        assert "0002_widget_contract.yaml" in problems[0]


# --- R3-1 (P2, architectural root cause): `Path.rglob` swallows
# OSError/PermissionError and yields an empty iterator, so an unreadable
# directory was indistinguishable from an empty one. A mode-000 records dir
# holding a destructive out-of-order `contract` exited 0 with the PASS line AND
# a NOTICE affirmatively claiming it contained no records. No guard existed to
# mutate, which is why the 11-mutant battery missed it. `enumerate_tree()`
# reports its own traversal failures instead.
#
# Covered two independent ways on purpose. The injected-failure tests are
# deterministic and pass as any uid including root; the live chmod drill proves
# the real mechanism on a real filesystem but SKIPS when the host does not
# actually enforce mode 000 (running as root, or a permission-ignoring mount),
# rather than failing and manufacturing a platform false positive.

def _fake_scandir_raising_on(target: Path, errno_msg: str = "Permission denied"):
    """Returns a drop-in for `os.scandir` that raises PermissionError for
    `target` only and delegates every other path to the real implementation."""
    real = os.scandir

    def fake(path=".", *args, **kwargs):
        if Path(path) == target:
            raise PermissionError(13, errno_msg, str(target))
        return real(path, *args, **kwargs)

    return fake


def test_unenumerable_root_is_a_named_problem_injected():
    """Deterministic R3-1: enumeration of the records dir itself fails."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_record(root, "0001_destructive_contract.yaml", "drop_members_table", "contract")
        real = os.scandir
        os.scandir = _fake_scandir_raising_on(root)
        try:
            problems = validate_directory(root, require_dir=True)
        finally:
            os.scandir = real
        assert len(problems) == 1, problems
        assert "UNREADABLE_RECORDS_PATH" in problems[0]
        assert "Permission denied" in problems[0]
        assert str(root) in problems[0]


def test_unenumerable_subdirectory_is_a_named_problem_injected():
    """The subtree case, which a top-level-only permission check would miss: the
    records dir reads fine and holds a VALID complete 4-phase set, but a real
    child directory cannot be enumerated. Real records are present, so no
    vacuous-pass notice would fire — exactly the shape that was an
    indistinguishable clean PASS."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_record(root, "0001_a_expand.yaml", "change_a", "expand")
        _write_record(root, "0002_a_migrate.yaml", "change_a", "migrate")
        _write_record(root, "0003_a_switch.yaml", "change_a", "switch")
        _write_record(root, "0004_a_contract.yaml", "change_a", "contract")
        nested = root / "q4"
        nested.mkdir()
        real = os.scandir
        os.scandir = _fake_scandir_raising_on(nested)
        try:
            problems = validate_directory(root, require_dir=True)
        finally:
            os.scandir = real
        assert len(problems) == 1, problems
        assert "UNREADABLE_RECORDS_PATH" in problems[0]
        assert "q4" in problems[0]
        # Named by RELATIVE path for a nested dir, not the absolute host path.
        assert str(root) not in problems[0]


def test_readable_and_unenumerable_same_tree_discriminate_injected():
    """The decisive positive/negative pair the round-3 report specified: same
    directory, same single destructive record, only enumerability changed."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_record(root, "0001_destructive_contract.yaml", "drop_members_table", "contract")

        # Readable: the record is genuinely destructive and genuinely detected.
        readable = validate_directory(root, require_dir=True)
        assert len(readable) == 1, readable
        assert "OUT_OF_ORDER_PHASE" in readable[0]
        assert "starts at 'contract' but must start with 'expand'" in readable[0]

        # Unenumerable: must NOT be a pass, and must not be silent.
        real = os.scandir
        os.scandir = _fake_scandir_raising_on(root)
        try:
            unreadable = validate_directory(root, require_dir=True)
        finally:
            os.scandir = real
        assert len(unreadable) == 1, unreadable
        assert "UNREADABLE_RECORDS_PATH" in unreadable[0]
        assert unreadable != readable


def test_cli_unenumerable_root_exits_1_with_no_false_vacuous_notice():
    """Through the real CLI, driven by an injected failure via a sitecustomize-free
    wrapper: a subprocess cannot share the monkeypatch, so this uses the live
    chmod mechanism and SKIPS if the host does not enforce it (see module note).
    The assertion that matters is that the old output — exit 0, PASS, and
    'contains no migration records' — is gone."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "np"
        root.mkdir()
        _write_record(root, "0001_destructive_contract.yaml", "drop_members_table", "contract")
        os.chmod(root, 0o000)
        try:
            try:
                os.listdir(root)
                return  # host does not enforce mode 000 (root/permission-ignoring mount)
            except PermissionError:
                pass
            result = _run_cli("--records-dir", str(root), "--require-dir")
            assert result.returncode == 1, (result.returncode, result.stdout)
            assert "UNREADABLE_RECORDS_PATH" in result.stdout, result.stdout
            assert "PASS" not in result.stdout, result.stdout
            assert "contains no migration records" not in result.stdout, result.stdout
        finally:
            os.chmod(root, 0o700)


def test_live_chmod_000_directory_fails_closed():
    """The live drill on a real filesystem, same skip discipline. Proves the
    injected tests above are modelling the real mechanism, not a fiction."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "np"
        root.mkdir()
        _write_record(root, "0001_destructive_contract.yaml", "drop_members_table", "contract")
        os.chmod(root, 0o000)
        try:
            try:
                os.listdir(root)
                return  # not enforced on this host — skip rather than false-fail
            except PermissionError:
                pass
            problems = validate_directory(root, require_dir=True)
            assert len(problems) == 1, problems
            assert "UNREADABLE_RECORDS_PATH" in problems[0]
        finally:
            os.chmod(root, 0o700)


def test_enumerate_tree_still_yields_symlinks_without_descending():
    """Regression guard on the enumerator swap itself: `enumerate_tree` must keep
    `rglob`'s exact symlink semantics — yield the symlink entry, never descend
    it — or R2-1's SYMLINK_IN_RECORDS_TREE guard would stop seeing it and the
    walk could follow links out of the tree or into a cycle."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "records"
        root.mkdir()
        hidden = Path(tmp) / "hidden"
        hidden.mkdir()
        _write_record(hidden, "0005_b_contract.yaml", "change_b", "contract")
        (root / "q4").symlink_to(hidden, target_is_directory=True)
        entries, problems = enumerate_tree(root)
        assert problems == [], problems
        assert [e.path.name for e in entries] == ["q4"], entries
        # Not descended: the target's record is absent from the enumeration.
        assert not any(e.path.name == "0005_b_contract.yaml" for e in entries), entries
        # R4-1: the classification travels WITH the entry, read once from the
        # DirEntry, so discover_records' symlink guard never has to re-probe
        # through `Path.is_symlink()` (which answers False on OSError).
        assert entries[0].is_symlink is True, entries
        assert entries[0].is_dir is False, entries


def test_enumerate_tree_is_exhaustive_and_deterministic_on_a_readable_tree():
    """Positive control for the enumerator: a readable nested tree enumerates
    every entry, reports no problem, and is sorted."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_record(root, "0001_a_expand.yaml", "change_a", "expand")
        (root / "q4" / "deep").mkdir(parents=True)
        _write_record(root / "q4" / "deep", "0002_a_migrate.yaml", "change_a", "migrate")
        entries, problems = enumerate_tree(root)
        assert problems == [], problems
        relative = [e.path.relative_to(root).as_posix() for e in entries]
        assert relative == sorted(relative), relative
        assert set(relative) == {
            "0001_a_expand.yaml", "q4", "q4/deep", "q4/deep/0002_a_migrate.yaml",
        }, relative
        # R4-1: every entry carries a real classification, none a symlink here.
        by_relative = {e.path.relative_to(root).as_posix(): e for e in entries}
        assert by_relative["q4"].is_dir is True, entries
        assert by_relative["q4/deep"].is_dir is True, entries
        assert by_relative["0001_a_expand.yaml"].is_dir is False, entries
        assert not any(e.is_symlink for e in entries), entries


# --- R4-1 (P2, architectural root cause, third recurrence of the same
# invariant family): round 3 replaced the error-suppressing enumerator but left
# `records_dir.is_dir()` / `records_dir.exists()` on the gate in FRONT of it and
# a third `args.records_dir.exists()` in `main()`'s notice path. Those pathlib
# predicates return False on OSError exactly as `rglob` yielded nothing, so the
# identical observable defect migrated one layer out: a records dir that exists
# and holds a destructive out-of-order `contract`, but whose PARENT is mode 000,
# produced exit 0, the ordinary PASS line, and a NOTICE affirmatively stating
# the directory "does not exist" — under the default invocation, which is the
# one `run_regression.py` actually uses.
#
# Covered four independent ways on purpose, because a behavioral test per known
# shape is precisely what failed to generalize three rounds running:
#   * live `chmod 000` on the PARENT, with and without --require-dir, helper and
#     CLI, plus the readable counterpart as a discriminating control;
#   * injected `PermissionError` and injected non-permission `OSError` on the
#     acquisition itself, deterministic and passing as any uid including root
#     (the live drills cannot run as root — mode 000 is not enforced there);
#   * real `NotADirectoryError` and broken-symlink shapes, which reach the same
#     tri-state branch through a different errno;
#   * two structural locks — an AST check that no pathlib existence/type probe
#     decides a PASS or NOTICE anywhere in the module, and a call-count check
#     that `main()` never re-runs discovery. Those are what make the fix
#     irreversible-in-one-line rather than merely correct for today's shapes.


class _HostSkip(Exception):
    """A host-capability precondition for a live-filesystem drill is not met."""


def _skip(reason: str) -> None:
    """Skips loudly in both supported invocation paths, rather than returning
    silently. Round-4 finding R4-4 is about exactly that: the two round-3 live
    drills use a bare `return`, so on a host that does not enforce mode 000 they
    report as PASSED with no assertion executed and the headline count silently
    overstates coverage. Under pytest this raises a real SKIPPED; under the
    documented `python3 tools/tests/test_...py` path the `__main__` runner below
    catches it, counts it separately, and prints it. (The two pre-existing round-3
    drills are deliberately left as they are — R4-4 is a P3 outside this bounded
    remediation's charge, and is carried forward in the evidence record.)"""
    if "pytest" in sys.modules:
        sys.modules["pytest"].skip(reason)
    raise _HostSkip(reason)


def _require_enforced_mode_000(path: Path) -> None:
    try:
        os.listdir(path)
    except PermissionError:
        return
    _skip(f"host does not enforce mode 000 on {path} (root, or a permission-ignoring mount)")


def _destructive_tree_behind(parent_mode: int):
    """Builds `<tmp>/parent/records/0001_destructive_contract.yaml` — a lone,
    genuinely destructive, genuinely out-of-order `contract` — and chmods the
    PARENT (never the records dir itself, which stays readable in its own right:
    that is what makes this a different shape from round 3's A1/A2). Yields the
    records path."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "parent"
            records = parent / "records"
            records.mkdir(parents=True)
            _write_record(records, "0001_destructive_contract.yaml",
                          "drop_members_table", "contract")
            os.chmod(parent, parent_mode)
            try:
                yield records
            finally:
                os.chmod(parent, 0o700)

    return _ctx()


def test_unreadable_parent_hiding_destructive_record_fails_closed_by_default():
    """The decisive R4-1 shape on the DEFAULT invocation — no `--require-dir`,
    i.e. the only invocation `knowledge/05-QA/tools/run_regression.py` makes.
    Before the tri-state acquisition this returned `[]` (a pass)."""
    with _destructive_tree_behind(0o000) as records:
        _require_enforced_mode_000(records.parent)
        problems = validate_directory(records)
        assert len(problems) == 1, problems
        assert "UNREADABLE_RECORDS_PATH" in problems[0], problems
        assert "Permission denied" in problems[0], problems
        # The old false claim must be gone: the directory DOES exist.
        assert "does not exist" not in problems[0], problems


def test_unreadable_parent_with_require_dir_names_the_real_reason():
    """With the flag the pre-fix code did exit 1, but for a factually wrong
    reason — `MISSING_RECORDS_DIR` ("does not exist") over a directory that
    exists and is merely unreachable, pointing an operator at a typo instead of
    a permission fault. A right exit code for a wrong reason is still a defect."""
    with _destructive_tree_behind(0o000) as records:
        _require_enforced_mode_000(records.parent)
        problems = validate_directory(records, require_dir=True)
        assert len(problems) == 1, problems
        assert "UNREADABLE_RECORDS_PATH" in problems[0], problems
        assert "MISSING_RECORDS_DIR" not in problems[0], problems


def test_readable_parent_same_tree_finds_the_destructive_record():
    """The discriminating positive half of the pair: identical tree, identical
    record, only the parent's mode changed. A guard that fires unconditionally
    is as defective as one that never fires."""
    with _destructive_tree_behind(0o700) as records:
        problems = validate_directory(records)
        assert len(problems) == 1, problems
        assert "OUT_OF_ORDER_PHASE" in problems[0], problems
        assert "starts at 'contract' but must start with 'expand'" in problems[0], problems


def test_cli_unreadable_parent_exits_1_with_no_false_absent_notice():
    """Through the real CLI on the default invocation — exit code and
    diagnostic inspected at the process boundary, not just the helper's return
    value. The exact pre-fix output was exit 0, `PASS`, and
    "NOTICE: records dir does not exist"."""
    with _destructive_tree_behind(0o000) as records:
        _require_enforced_mode_000(records.parent)
        result = _run_cli("--records-dir", str(records))
        assert result.returncode == 1, (result.returncode, result.stdout)
        assert "UNREADABLE_RECORDS_PATH" in result.stdout, result.stdout
        assert "PASS" not in result.stdout, result.stdout
        assert "NOTICE" not in result.stdout, result.stdout
        assert "does not exist" not in result.stdout, result.stdout


def test_cli_unreadable_parent_exits_1_with_require_dir():
    with _destructive_tree_behind(0o000) as records:
        _require_enforced_mode_000(records.parent)
        result = _run_cli("--records-dir", str(records), "--require-dir")
        assert result.returncode == 1, (result.returncode, result.stdout)
        assert "UNREADABLE_RECORDS_PATH" in result.stdout, result.stdout
        assert "MISSING_RECORDS_DIR" not in result.stdout, result.stdout
        assert "PASS" not in result.stdout, result.stdout


# --- Injected acquisition failures. The live drills above prove the real
# mechanism but cannot run as root; these are deterministic, uid-independent,
# and cover errnos a temp directory cannot easily produce.

def _fake_stat_raising_on(target: Path, exc: OSError, which: str = "stat"):
    """Drop-in for `os.stat`/`os.lstat` that raises `exc` for `target` only and
    delegates every other path to the real implementation (so pathlib, tempfile
    and subprocess machinery keep working during the drill)."""
    real = getattr(os, which)

    def fake(path=".", *args, **kwargs):
        try:
            same = Path(path) == target
        except TypeError:          # fd or bytes path — never our target
            same = False
        if same:
            raise exc
        return real(path, *args, **kwargs)

    return fake


def _with_injected_stat(target: Path, exc: OSError, also_lstat: bool = True):
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        real_stat, real_lstat = os.stat, os.lstat
        os.stat = _fake_stat_raising_on(target, exc, "stat")
        if also_lstat:
            os.lstat = _fake_stat_raising_on(target, exc, "lstat")
        try:
            yield
        finally:
            os.stat, os.lstat = real_stat, real_lstat

    return _ctx()


def _with_asymmetric_injected_stat(target: Path, stat_exc: OSError, lstat_exc: OSError):
    """Injects a DIFFERENT exception into `os.stat` and into `os.lstat` for
    `target` only, delegating every other path to the real syscall.

    `_with_injected_stat` can only give both calls the *same* exception, which
    is round-5 finding R5-1's test-coverage gap: `acquire_records_dir` probes
    `os.lstat` precisely to discriminate the ENOENT-from-`stat` case, so the
    branch that classifies lstat's own failure is unreachable by any symmetric
    injection and was therefore never exercised. It held
    `except OSError: return ABSENT` — an unknown state asserted as an absence —
    while 55/55 tests and 20/20 mutants were green.

    No *static* filesystem shape reaches this pair, because `stat` and `lstat`
    resolve all ancestor components identically; it needs the path to change
    between the two syscalls (or a filesystem that answers them
    inconsistently). Injection is how it becomes deterministically testable
    rather than a race nobody can pin."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        real_stat, real_lstat = os.stat, os.lstat
        os.stat = _fake_stat_raising_on(target, stat_exc, "stat")
        os.lstat = _fake_stat_raising_on(target, lstat_exc, "lstat")
        try:
            yield
        finally:
            os.stat, os.lstat = real_stat, real_lstat

    return _ctx()


def test_injected_permission_error_fails_closed_in_both_flag_modes():
    """R4-1's mechanism, deterministic: acquisition raises `PermissionError`.
    Must be a named nonzero problem WITH and WITHOUT `--require-dir` — the flag
    is an assertion about a missing directory and must not be what stands
    between an unreadable tree and a green run."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "records"
        root.mkdir()
        _write_record(root, "0001_destructive_contract.yaml", "drop_members_table", "contract")
        exc = PermissionError(13, "Permission denied", str(root))
        with _with_injected_stat(root, exc):
            default = validate_directory(root)
            required = validate_directory(root, require_dir=True)
        assert len(default) == 1, default
        assert "UNREADABLE_RECORDS_PATH" in default[0], default
        assert "Permission denied" in default[0], default
        assert required == default, (required, default)


def test_injected_non_permission_oserror_fails_closed_in_both_flag_modes():
    """Any other `OSError` — EIO here — is equally "state unknown", not absent.
    Folding only `PermissionError` out of the absent bucket would leave the same
    invariant alive for every other errno."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "records"
        root.mkdir()
        exc = OSError(5, "Input/output error", str(root))
        with _with_injected_stat(root, exc):
            default = validate_directory(root)
            required = validate_directory(root, require_dir=True)
        assert len(default) == 1, default
        assert "UNREADABLE_RECORDS_PATH" in default[0], default
        assert "Input/output error" in default[0], default
        assert required == default, (required, default)


def test_injected_file_not_found_is_the_only_absent_case():
    """Control proving the injection harness discriminates rather than making
    everything fail: a genuine `FileNotFoundError` (and no symlink at the path)
    still produces the documented default vacuous PASS, and still fails closed
    under `--require-dir`. If this test ever failed, the two above would be
    passing for the trivial reason that acquisition rejects everything."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "records"
        root.mkdir()
        exc = FileNotFoundError(2, "No such file or directory", str(root))
        with _with_injected_stat(root, exc):
            assert validate_directory(root) == []
            required = validate_directory(root, require_dir=True)
        assert len(required) == 1, required
        assert "MISSING_RECORDS_DIR" in required[0], required


# --- Round-5 finding R5-1: the asymmetric stat/lstat outcome classes -------
#
# `acquire_records_dir` makes TWO syscalls, so its outcome space is the
# Cartesian product of their results, not a single list of shapes. Round 4
# enumerated the `os.stat` half and left the `os.lstat` half as a bare
# `except OSError: return ABSENT`. The tests below cover every row of that
# product's ENOENT-from-stat column, including the discriminating controls, so
# the table is closed by execution and not only by the docstring that
# describes it.


def test_asymmetric_lstat_permission_error_is_error_not_absent():
    """R5-1's exact mechanism: `stat` says ENOENT, `lstat` says EACCES. The
    tool has NOT determined that the path is absent — it has determined that
    it cannot tell. Before the fix this returned `problems == []`, exit 0, the
    ordinary PASS line, and a NOTICE affirmatively stating the directory "does
    not exist", which is invariant I-1's definition of a fail-open."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "records"
        root.mkdir()
        _write_record(root, "0001_destructive_contract.yaml", "drop_members_table", "contract")
        with _with_asymmetric_injected_stat(
            root,
            FileNotFoundError(2, "No such file or directory", str(root)),
            PermissionError(13, "Permission denied", str(root)),
        ):
            default = validate_directory(root)
            required = validate_directory(root, require_dir=True)
            outcome = run_validation(root)
        assert len(default) == 1, default
        assert "UNREADABLE_RECORDS_PATH" in default[0], default
        assert "Permission denied" in default[0], default
        # Not merely nonzero: the *reason* must not claim absence. Round 4
        # recorded "right exit code, wrong reason" as part of R4-1.
        assert "MISSING_RECORDS_DIR" not in default[0], default
        assert "does not exist" not in default[0], default
        assert required == default, (required, default)
        # And no notice may accompany it (I-2).
        assert outcome.notice is None, outcome


def test_asymmetric_lstat_eio_is_error_not_absent():
    """Not just EACCES: folding only `PermissionError` out of the absent
    bucket would leave the same invariant alive for every other errno. EIO is
    the canonical "the device answered, with a failure" case."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "records"
        root.mkdir()
        with _with_asymmetric_injected_stat(
            root,
            FileNotFoundError(2, "No such file or directory", str(root)),
            OSError(5, "Input/output error", str(root)),
        ):
            default = validate_directory(root)
            required = validate_directory(root, require_dir=True)
        assert len(default) == 1, default
        assert "UNREADABLE_RECORDS_PATH" in default[0], default
        assert "Input/output error" in default[0], default
        assert required == default, (required, default)


def test_asymmetric_lstat_eloop_is_error_not_absent():
    """ELOOP from `lstat` specifically: `lstat` does not follow the final
    symlink, so an ELOOP here means the ancestor chain is looping. Still
    indeterminate, still never an absence."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "records"
        root.mkdir()
        with _with_asymmetric_injected_stat(
            root,
            FileNotFoundError(2, "No such file or directory", str(root)),
            OSError(62, "Too many levels of symbolic links", str(root)),
        ):
            default = validate_directory(root)
            required = validate_directory(root, require_dir=True)
        assert len(default) == 1, default
        assert "UNREADABLE_RECORDS_PATH" in default[0], default
        assert "Too many levels of symbolic links" in default[0], default
        assert required == default, (required, default)


def test_asymmetric_both_enoent_is_the_only_absent_row():
    """Discriminating control for the three tests above. If this failed, they
    would be passing for the trivial reason that the asymmetric harness makes
    everything fail. ENOENT from BOTH calls is the one row of the table that
    may produce the documented vacuous pass — and it still fails closed under
    `--require-dir`."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "records"
        root.mkdir()
        with _with_asymmetric_injected_stat(
            root,
            FileNotFoundError(2, "No such file or directory", str(root)),
            FileNotFoundError(2, "No such file or directory", str(root)),
        ):
            default = validate_directory(root)
            required = validate_directory(root, require_dir=True)
            outcome = run_validation(root)
        assert default == [], default
        assert outcome.notice is not None and "does not exist" in outcome.notice, outcome
        assert len(required) == 1, required
        assert "MISSING_RECORDS_DIR" in required[0], required


def test_asymmetric_stat_enoent_with_real_lstat_succeeding_is_broken_symlink():
    """The remaining row of the ENOENT-from-stat column, and the first use of
    `_with_injected_stat(..., also_lstat=False)` — the parameter existed
    specifically to allow asymmetric injection and round 5 found it had never
    once been called that way. `lstat` is left real and succeeds (the fixture
    directory is genuinely there), which is indistinguishable to the tool from
    a dangling symlink, so `BROKEN_RECORDS_SYMLINK` is the correct row."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "records"
        root.mkdir()
        exc = FileNotFoundError(2, "No such file or directory", str(root))
        with _with_injected_stat(root, exc, also_lstat=False):
            default = validate_directory(root)
            required = validate_directory(root, require_dir=True)
        assert len(default) == 1, default
        assert "BROKEN_RECORDS_SYMLINK" in default[0], default
        assert required == default, (required, default)


def test_no_except_handler_in_acquire_records_dir_folds_oserror_into_absent():
    """Structural lock on the total classification table (round-5 R5-1).

    Five rounds removed this same unknown-folded-into-absent fold from five
    different sites (`rglob` -> `Path.is_dir`/`exists` -> `main()`'s second
    probe -> `DirEntry` classification -> the `lstat` fallback). Each time, the
    behavioral test added afterwards pinned the shape that had just been
    found, and the fold reappeared at the next site that had no test. This test
    is deliberately structural instead: `RECORDS_PATH_ABSENT` may be returned
    ONLY from a handler whose caught type is exactly `FileNotFoundError`.

    That is the invariant, not the shape — a bare `except OSError`, an
    `except (OSError, ValueError)`, or a bare `except:` that returns ABSENT all
    fail here regardless of which syscall they sit on, and so would a sixth
    site added later. Round 5 observed that no test exercised and no mutant
    anchored on the offending branch; a decision-level check of every `except`
    clause in this function is what would have caught it."""
    import ast

    source = Path(TOOL).read_text(encoding="utf-8")
    tree = ast.parse(source)
    func = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.FunctionDef) and n.name == "acquire_records_dir"),
        None,
    )
    assert func is not None, "acquire_records_dir not found — test anchor is stale"

    # Parent map over the function body, so each `return ABSENT` is attributed
    # to its INNERMOST enclosing handler. Handlers nest here (the lstat probe
    # sits inside `except FileNotFoundError`), so a transitive `ast.walk` of a
    # handler would wrongly credit an outer handler with an inner return.
    parent: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(func):
        for child in ast.iter_child_nodes(node):
            parent[child] = node

    def _innermost_handler(node: ast.AST) -> ast.ExceptHandler | None:
        cur = parent.get(node)
        while cur is not None:
            if isinstance(cur, ast.ExceptHandler):
                return cur
            cur = parent.get(cur)
        return None

    absent_returns = [
        ret for ret in ast.walk(func)
        if isinstance(ret, ast.Return)
        and any(isinstance(sub, ast.Name) and sub.id == "RECORDS_PATH_ABSENT"
                for sub in ast.walk(ret))
    ]
    assert absent_returns, (
        "no `return RECORDS_PATH_ABSENT` found in acquire_records_dir — test "
        "anchor is stale"
    )

    offenders = []
    for ret in absent_returns:
        handler = _innermost_handler(ret)
        if handler is None:
            offenders.append("returned outside any except handler")
            continue
        caught = handler.type
        if not (isinstance(caught, ast.Name) and caught.id == "FileNotFoundError"):
            offenders.append(
                ast.dump(caught) if caught is not None else "bare except")

    assert not offenders, (
        "a `return RECORDS_PATH_ABSENT` in acquire_records_dir is reached from a "
        f"caught type other than FileNotFoundError: {offenders}. This is round-5 "
        "finding R5-1 — 'I could not read this path' must never be classified as "
        "'this path is not there'. Return RECORDS_PATH_ERROR with a named problem "
        "instead."
    )
    # And ABSENT must stay reachable by exactly one route, so the fold cannot be
    # reintroduced by *adding* a second absent-returning branch somewhere else.
    assert len(absent_returns) == 1, (
        f"expected exactly one `return RECORDS_PATH_ABSENT`, found "
        f"{len(absent_returns)}"
    )


def test_records_path_under_a_regular_file_fails_closed_in_both_flag_modes():
    """A real, non-injected `NotADirectoryError`: `--records-dir` points below a
    regular file. `Path.exists()` answers False here too, so the pre-fix code
    treated it as absent — a vacuous pass by default. ENOTDIR is not absence."""
    with tempfile.TemporaryDirectory() as tmp:
        plain = Path(tmp) / "plainfile.txt"
        plain.write_text("not a directory\n", encoding="utf-8")
        under = plain / "records"
        default = validate_directory(under)
        required = validate_directory(under, require_dir=True)
        assert len(default) == 1, default
        assert "UNREADABLE_RECORDS_PATH" in default[0], default
        assert "Not a directory" in default[0], default
        assert required == default, (required, default)


def test_broken_symlink_records_dir_fails_closed_in_both_flag_modes():
    """A dangling symlink AT the records path: `stat` raises
    `FileNotFoundError`, but the path itself is present, so "does not exist"
    would be a false statement about it and `absent` would be the wrong
    tri-state bucket. Distinct, named, nonzero in both modes."""
    with tempfile.TemporaryDirectory() as tmp:
        link = Path(tmp) / "records_link"
        link.symlink_to(Path(tmp) / "nope_does_not_exist", target_is_directory=True)
        default = validate_directory(link)
        required = validate_directory(link, require_dir=True)
        assert len(default) == 1, default
        assert "BROKEN_RECORDS_SYMLINK" in default[0], default
        assert required == default, (required, default)


def test_acquire_records_dir_is_tri_state_on_real_paths():
    """The acquisition contract itself, directly: three real paths, three
    distinct kinds, and `problem` set if and only if the kind is the error one."""
    with tempfile.TemporaryDirectory() as tmp:
        present = Path(tmp) / "records"
        present.mkdir()
        absent = Path(tmp) / "nope"
        wrong_type = Path(tmp) / "plainfile.txt"
        wrong_type.write_text("x\n", encoding="utf-8")

        assert acquire_records_dir(present) == (RECORDS_PATH_DIRECTORY, None)
        assert acquire_records_dir(absent) == (RECORDS_PATH_ABSENT, None)
        bad = acquire_records_dir(wrong_type)
        assert bad.kind == RECORDS_PATH_ERROR, bad
        assert bad.problem is not None and "RECORDS_PATH_NOT_A_DIRECTORY" in bad.problem, bad

        # A symlink to a real directory still resolves to the directory case
        # (os.stat follows links, exactly as the replaced is_dir() did).
        link = Path(tmp) / "records_link"
        link.symlink_to(present, target_is_directory=True)
        assert acquire_records_dir(link) == (RECORDS_PATH_DIRECTORY, None)


# --- The notice is now a value carried by the one validation result, not a
# second filesystem probe in main(). These pin the shared-result contract.

def test_absent_dir_yields_the_absent_notice_and_no_problem():
    with tempfile.TemporaryDirectory() as tmp:
        outcome = run_validation(Path(tmp) / "nope")
        assert outcome.problems == [], outcome
        assert outcome.notice == NOTICE_ABSENT, outcome


def test_empty_dir_yields_the_no_records_notice_and_no_problem():
    with tempfile.TemporaryDirectory() as tmp:
        outcome = run_validation(Path(tmp))
        assert outcome.problems == [], outcome
        assert outcome.notice == NOTICE_NO_RECORDS, outcome


def test_populated_valid_dir_yields_no_notice_at_all():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_record(root, "0001_widget_expand.yaml", "add_widget_column", "expand")
        _write_record(root, "0002_widget_migrate.yaml", "add_widget_column", "migrate")
        outcome = run_validation(root)
        assert outcome.problems == [], outcome
        assert outcome.notice is None, outcome


def test_notice_is_never_returned_alongside_problems():
    """`ValidationOutcome`'s invariant, across one shape per acquisition branch
    plus one in-tree problem. A "vacuous pass" notice printed next to a BLOCKED
    verdict is the misleading-diagnostic mode of R1-7, and R4-1's observable
    symptom was exactly a notice that contradicted reality — so the two are
    bound together structurally here, not by convention in main()."""
    with tempfile.TemporaryDirectory() as tmp:
        plain = Path(tmp) / "plainfile.txt"
        plain.write_text("x\n", encoding="utf-8")
        ordering = Path(tmp) / "ordering"
        ordering.mkdir()
        _write_record(ordering, "0001_c.yaml", "change_a", "contract")
        unrecognized = Path(tmp) / "unrecognized"
        unrecognized.mkdir()
        _write_record(unrecognized, "0001_c.yml", "change_a", "contract")

        shapes = [
            run_validation(plain),                                   # wrong type
            run_validation(plain / "records"),                       # ENOTDIR
            run_validation(Path(tmp) / "nope", require_dir=True),    # absent + flag
            run_validation(ordering),                                # ordering violation
            run_validation(unrecognized),                            # zero records found
        ]
        for outcome in shapes:
            assert outcome.problems, outcome
            assert outcome.notice is None, outcome


def test_main_does_not_rediscover_records_after_validation():
    """Structural lock on the other half of R4-1: `main()` used to decide which
    notice to print by calling `discover_records()` a SECOND time (and
    `.exists()` a third). Any re-derivation of the verdict is a chance for the
    two to disagree, which is how a false notice reached stdout. Discovery must
    run exactly once per invocation."""
    import contextlib
    import io

    import validate_migration_ordering as tool

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_record(root, "0001_widget_expand.yaml", "add_widget_column", "expand")
        real = tool.discover_records
        calls = []

        def counting(records_dir):
            calls.append(records_dir)
            return real(records_dir)

        argv = sys.argv
        tool.discover_records = counting
        sys.argv = ["validate_migration_ordering.py", "--records-dir", str(root)]
        captured = io.StringIO()
        try:
            with contextlib.redirect_stdout(captured):
                exit_code = tool.main()
        finally:
            tool.discover_records = real
            sys.argv = argv
        assert exit_code == 0, captured.getvalue()
        assert len(calls) == 1, calls


def test_unclassifiable_tree_entry_is_a_named_problem_injected():
    """The same invariant one level down, inside the walk: `enumerate_tree`'s
    per-entry `is_dir()` used to answer an `OSError` with `descend = False` and
    record nothing, so an entry whose type could not be read was silently
    treated as a non-directory and never descended — unknown folded into
    "nothing under here". It must be a named problem instead."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_record(root, "0001_a_expand.yaml", "change_a", "expand")
        (root / "q4").mkdir()

        real_scandir = os.scandir

        class _Opaque:
            def __init__(self, entry):
                self._entry = entry
                self.path = entry.path
                self.name = entry.name

            def is_symlink(self):
                raise PermissionError(13, "Permission denied", self.path)

            def is_dir(self, follow_symlinks=True):
                raise PermissionError(13, "Permission denied", self.path)

        class _Scan:
            def __init__(self, path):
                self._path = path

            def __enter__(self):
                return [
                    _Opaque(e) if e.name == "q4" else e
                    for e in real_scandir(self._path)
                ]

            def __exit__(self, *_):
                return False

        os.scandir = lambda path=".", *a, **k: _Scan(path)
        try:
            entries, problems = enumerate_tree(root)
            cli_problems = validate_directory(root, require_dir=True)
        finally:
            os.scandir = real_scandir

        assert len(problems) == 1, problems
        assert "UNCLASSIFIABLE_RECORDS_ENTRY" in problems[0], problems
        assert "q4" in problems[0], problems
        assert "Permission denied" in problems[0], problems
        # Reported, not enumerated as a classified entry — and it reaches the
        # caller's verdict rather than dying inside the walk.
        assert [e.path.name for e in entries] == ["0001_a_expand.yaml"], entries
        assert any("UNCLASSIFIABLE_RECORDS_ENTRY" in p for p in cli_problems), cli_problems


def test_discovery_consumes_captured_classification_not_a_fresh_probe():
    """Pins WHICH source of truth `discover_records` reads an entry's type from.

    The two can only be told apart by making them disagree, so this injects a
    `DirEntry` that reports a real directory as not-a-directory. Correct
    behavior is to act on the captured classification — treat it as a non-record
    file and name it `UNRECOGNIZED_RECORD_FILE`, which is fail-closed. Re-probing
    with `path.is_dir()` instead answers True, `continue`s, and silently skips
    it — and here that skip hides a destructive out-of-order `contract`.

    Without this test the "consume, never re-probe" half of the R4-1 fix is
    enforced only by the source-level AST lock above; mutant M20 (re-probe
    through pathlib) survives every other control in the suite."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "q4").mkdir()
        _write_record(root / "q4", "0001_destructive_contract.yaml",
                      "drop_members_table", "contract")

        real_scandir = os.scandir

        class _MisreportingDir:
            """A real directory that reports itself as a plain file."""

            def __init__(self, entry):
                self.path = entry.path
                self.name = entry.name

            def is_symlink(self):
                return False

            def is_dir(self, follow_symlinks=True):
                return False

        class _Scan:
            def __init__(self, path):
                self._path = path

            def __enter__(self):
                return [_MisreportingDir(e) if e.name == "q4" else e
                        for e in real_scandir(self._path)]

            def __exit__(self, *_):
                return False

        os.scandir = lambda path=".", *a, **k: _Scan(path)
        try:
            problems = validate_directory(root, require_dir=True)
        finally:
            os.scandir = real_scandir

        assert len(problems) == 1, problems
        assert "UNRECOGNIZED_RECORD_FILE" in problems[0], problems
        assert "q4" in problems[0], problems


def test_no_pathlib_existence_probe_decides_a_pass_or_notice():
    """Structural lock, deliberately source-level rather than behavioral.

    Three rounds of this scenario fixed one error-swallowing probe each and
    watched the identical fail-open reappear at the next layer out (`rglob` ->
    `is_dir`/`exists` on the gate -> `exists` in main()'s notice path). A
    behavioral test per known shape cannot close that, because the defect is
    the CLASS of call, not any one site. So: no `Path.exists()`,
    `Path.is_dir()`, `Path.is_file()` or `Path.is_symlink()` anywhere in the
    module. Those four return False on OSError instead of raising, which is
    what makes "could not read" and "not there" indistinguishable.

    The only metadata probes allowed are `os.scandir`'s `DirEntry` methods
    inside `enumerate_tree`, whose OSError is caught and named
    (`UNCLASSIFIABLE_RECORDS_ENTRY`), and `os.stat`/`os.lstat` in
    `acquire_records_dir`, which raise. If a future change genuinely needs a
    new probe, it must widen this allowlist in the same commit — which is the
    point: the widening becomes visible in review instead of silent."""
    import ast

    source = Path(TOOL).read_text(encoding="utf-8")
    tree = ast.parse(source)
    swallowing = {"exists", "is_dir", "is_file", "is_symlink"}
    allowed = {"entry.is_dir", "entry.is_symlink"}
    found = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in swallowing):
            found.add(ast.unparse(node.func))
    assert found <= allowed, (
        f"error-swallowing pathlib metadata probe(s) in {TOOL.name}: "
        f"{sorted(found - allowed)} — see this test's docstring (R4-1)"
    )
    # Non-vacuity: the check must actually be looking at the right file and
    # finding the two legitimate DirEntry probes, not an empty set because the
    # AST walk or the attribute names drifted.
    assert found == allowed, (
        f"expected exactly the two allowlisted DirEntry probes, found {sorted(found)}"
    )


if __name__ == "__main__":
    # R1-9: discovered, never hand-listed. The previous `__main__` block named
    # six calls explicitly and printed a hardcoded "all 6 tests passed", so any
    # test added below it — including every R1-1/R1-2 test that kills mutants
    # M3 and M5 — would have been silently skipped under this exact documented
    # invocation path, the one the evidence record used.
    discovered = [(name, obj) for name, obj in sorted(globals().items())
                  if name.startswith("test_") and callable(obj)]
    if not discovered:
        print("FAIL — no test_* functions discovered; the runner itself is broken.")
        sys.exit(1)
    # R4-1 addition: a host-capability skip is reported, never swallowed. A live
    # drill that cannot run on this host must not be counted as a pass (R4-4's
    # critique of the round-3 drills' bare `return`).
    skipped: list[tuple[str, str]] = []
    for name, fn in discovered:
        try:
            fn()
        except _HostSkip as exc:
            skipped.append((name, str(exc)))
    for name, reason in skipped:
        print(f"SKIPPED — {name}: {reason}")
    print(f"PASS — {len(discovered) - len(skipped)} of {len(discovered)} tests passed, "
          f"{len(skipped)} skipped (discovered dynamically, not hand-listed).")
