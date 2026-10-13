"""SCN-MOD001-070 migration-ordering-lint mutation kill-check.

Reproducible replacement for the round-1 reviewer's ad-hoc `/tmp` mutation
probes (`SCN070-MIGRATION-ORDERING-LINT-SECURITY-REVIEW-ROUND1-2026-10-04.md`
"Mutation table"), written so any later session — or the round-2 independent
reviewer — can re-derive the same verdict with one command instead of
reconstructing seven mutations by hand. Same shape and same safety discipline
as this module's existing `r04_gate_mutation_killcheck.py`, deliberately: it is
the established convention here, not a new one.

Every mutant is applied to a COPY of `tools/validate_migration_ordering.py`
inside a temporary mirror. The real tool is opened read-only, never written;
its SHA-256 is asserted unchanged in `finally`, at interpreter exit, and on
SIGINT/SIGTERM, so even an interrupted run still proves (or visibly fails to
prove) that the real file is intact.

A mutant is KILLED if any of three controls notices it:
  * `unit`            — the mirror's own unit suite exits non-zero;
  * `cli-negative`    — the CLI over the evidence record's recorded negative
                        fixture (expand + migrate + contract) stops exiting 1;
  * `cli-lone`        — the CLI over a lone `contract` record with no
                        predecessors at all stops exiting 1.

M3 (start-phase guard) and M5 (rejection exit code) are the two mutants that
SURVIVED all controls at round 1. They must now be killed; a survivor among
them fails this run, as does a survivor anywhere else.
"""

from __future__ import annotations

import atexit
import hashlib
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
REAL_TOOL = ROOT / "tools" / "validate_migration_ordering.py"
REAL_TEST = ROOT / "tools" / "tests" / "test_validate_migration_ordering.py"
PY = str(ROOT / "backend" / ".venv" / "bin" / "python")
REAL_SHA = hashlib.sha256(REAL_TOOL.read_bytes()).hexdigest()
REAL_TEST_SHA = hashlib.sha256(REAL_TEST.read_bytes()).hexdigest()

VALID_FIELDS = (
    "owner: jane@example.com",
    "lock_impact: none",
    "rollback_strategy: drop the new object",
    "validation_query: SELECT 1",
)


def _assert_real_files_unchanged() -> None:
    for path, expected in ((REAL_TOOL, REAL_SHA), (REAL_TEST, REAL_TEST_SHA)):
        now = hashlib.sha256(path.read_bytes()).hexdigest()
        if now != expected:
            print(f"REAL FILE CHANGED: {path} {expected} -> {now}", flush=True)
            sys.exit(3)


atexit.register(_assert_real_files_unchanged)
for _sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(_sig, lambda *_: (_assert_real_files_unchanged(), sys.exit(130)))


def _write_record(root: Path, filename: str, change_id: str, phase: str) -> None:
    body = "\n".join(("---", f"change_id: {change_id}", f"phase: {phase}",
                      *VALID_FIELDS, "---", "",
                      "Synthetic fixture record — not a real migration."))
    (root / filename).write_text(body, encoding="utf-8")


def _build_mirror() -> Path:
    """Copy the tool and its unit suite (stdlib-only, nothing else is read),
    then build the two CLI control fixtures alongside them."""
    mirror = Path(tempfile.mkdtemp(prefix="veyro-scn070-killcheck-"))
    for rel in ("tools/validate_migration_ordering.py",
                "tools/tests/test_validate_migration_ordering.py"):
        (mirror / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, mirror / rel)

    # Control 1: the evidence record's own recorded negative — contract missing
    # only its `switch` predecessor. Reaches check_ordering's ADVANCE path.
    negative = mirror / "fixtures" / "negative"
    negative.mkdir(parents=True)
    _write_record(negative, "0001_expand.yaml", "add_widget_column", "expand")
    _write_record(negative, "0002_migrate.yaml", "add_widget_column", "migrate")
    _write_record(negative, "0003_contract.yaml", "add_widget_column", "contract")

    # Control 2: the acceptance clause's broadest reading — a destructive
    # contract with NO predecessors. Reaches the START path (the R1-1 gap).
    lone = mirror / "fixtures" / "lone_contract"
    lone.mkdir(parents=True)
    _write_record(lone, "0001_contract.yaml", "add_widget_column", "contract")
    return mirror


# name -> list of (exact anchor, replacement). Every anchor must match exactly
# once in the real tool, or the run aborts rather than reporting a kill it did
# not actually perform.
M: dict[str, list[tuple[str, str]]] = {
    "M1 check_ordering returns [] immediately": [(
        "    problems = []\n    highest_index: dict[str, int] = {}",
        "    return []\n    problems = []\n    highest_index: dict[str, int] = {}")],
    "M2 ordering predicate accepts any skip-ahead": [(
        "        if phase_index == last + 1:", "        if phase_index >= last + 1:")],
    "M3 start-phase guard neutralized (R1-1, SURVIVED at round 1)": [
        ("            if phase_index != 0:", "            if False:"),
        ("            highest_index[change_id] = 0",
         "            highest_index[change_id] = phase_index")],
    "M4 validate_fields returns [] immediately": [(
        "    problems = []\n    for field in REQUIRED_FIELDS:",
        "    return []\n    problems = []\n    for field in REQUIRED_FIELDS:")],
    "M5 main() rejection exit code neutralized (R1-2, SURVIVED at round 1)": [(
        "        return 1", "        return 0")],
    # Re-anchored 2026-10-04 (R3 pass): the old anchor was discover_records'
    # `for path in sorted(records_dir.rglob("*")):` line, which the R3-1
    # enumerator swap removed. The harness refused the whole run with exit 2
    # rather than reporting a kill it had not performed — working as designed.
    # Same semantics at the new seam: narrow enumeration to direct *.yaml only,
    # so non-.yaml and nested files are silently ignored again.
    # Replacement re-shaped 2026-10-04 (R4 pass): `enumerate_tree` now returns
    # `TreeEntry` tuples, so the old bare-`Path` replacement would have died of an
    # AttributeError — a kill by type mismatch, which proves nothing about whether
    # a control notices the silent skip. Rebuilt as a type-faithful reversion that
    # really does narrow discovery back to direct *.yaml only.
    "M6 discovery narrowed back to glob('*.yaml') (R1-3 fix removed)": [(
        "    entries, problems = enumerate_tree(records_dir)",
        ('    entries, problems = [TreeEntry(p, p.is_symlink(), p.is_dir()) '
         'for p in sorted(records_dir.glob("*.yaml"))], []'))],
    # Re-anchored 2026-10-04 (R2 pass): the old anchor was the `relative = ...`
    # assignment, which the R2-1 fix moved to the top of the loop — inserting
    # `continue` there suppressed ALL discovery, a strictly broader mutant than
    # intended. Anchored on the UNRECOGNIZED append itself, it again isolates
    # exactly the pre-fix silent-skip of a non-record file.
    "M7 UNRECOGNIZED_RECORD_FILE suppressed (R1-3 fix removed)": [(
        '        problems.append(\n            f"{relative}: UNRECOGNIZED_RECORD_FILE',
        '        continue\n        problems.append(\n            f"{relative}: UNRECOGNIZED_RECORD_FILE')],
    "M8 --require-dir neutralized (R1-4 fix removed)": [(
        "        if require_dir:", "        if False:")],
    # Round-2 additions: prove the three R2 fixes are load-bearing, not untested
    # additions. Each reverts the guard to the exact pre-fix behavior round 2
    # reproduced as a clean exit-0 PASS.
    # Re-anchored 2026-10-04 (R4 pass): the old anchor was
    # `if path.is_symlink():`, which the R4-1 fix replaced with the classification
    # the enumerator captured once (`entry.is_symlink`) — pathlib's predicate
    # answers False on OSError, so the guard that closed R2-1 could itself simply
    # fail to fire. Same seam, same semantics: neutralize the symlink guard.
    "M9 symlink guard neutralized (R2-1 fix removed)": [(
        "        if entry.is_symlink:", "        if False:")],
    "M10 duplicate front-matter key last-wins again (R2-2 fix removed)": [(
        "        if key in fields:", "        if False:")],
    # Re-anchored 2026-10-04 (R4 pass): both old anchors were the pathlib
    # predicate pair the R4-1 fix deleted outright. The not-a-directory rejection
    # now lives on the stat mode check inside acquire_records_dir.
    "M11 non-directory records path accepted again (R2-3 fix removed)": [(
        "    if not stat.S_ISDIR(info.st_mode):", "    if False:")],
    # Round-3 additions. Two distinct reverts of the SAME architectural fix,
    # deliberately: M12 keeps the explicit walk but silences its error report
    # (the "someone deletes the guard" case); M13 reverts the enumerator itself
    # back to error-suppressing `rglob` (the literal pre-fix state the round-3
    # report reproduced). A fix that only M12 catches would still be
    # architecturally reversible in one line.
    "M12 UNREADABLE_RECORDS_PATH report suppressed (R3-1 guard removed)": [(
        '            problems.append(\n                f"{where}: UNREADABLE_RECORDS_PATH',
        '            continue\n            problems.append(\n                f"{where}: UNREADABLE_RECORDS_PATH')],
    # Replacement re-shaped 2026-10-04 (R4 pass), same reason as M6: type-faithful
    # now, so the kill is attributable to a control noticing suppressed errors
    # rather than to an AttributeError. The pathlib probes in the replacement are
    # deliberate — they are what the pre-fix code used.
    "M13 enumerator reverted to error-suppressing rglob (R3-1 root cause restored)": [(
        "    entries, problems = enumerate_tree(records_dir)",
        ('    entries, problems = [TreeEntry(p, p.is_symlink(), p.is_dir()) '
         'for p in sorted(records_dir.rglob("*"))], []'))],
    # Round-4 additions (R4-1). The round-3 battery could not have found R4-1:
    # every mutant in it was defined by a fix that existed, and R4-1 was a
    # fail-open nobody had written a guard for. M14-M20 are therefore anchored on
    # the tri-state acquisition and the shared-result contract, which is where the
    # invariant now lives. M14 is the literal pre-fix state the round-4 review
    # reproduced; M15/M19 fold "unknown" back into "absent" by a different route
    # each; M16 restores main()'s second probe; M17 is the same fold one level
    # down, inside the walk; M18 lets a notice accompany a BLOCKED verdict again;
    # M20 reintroduces a re-probe in the consumer. A fix that only M14 catches
    # would still be reversible one errno at a time.
    "M14 tri-state acquisition replaced by pathlib is_dir/exists (R4-1 root cause restored)": [(
        "    try:\n        info = os.stat(records_dir)\n    except FileNotFoundError:",
        ("    if records_dir.is_dir():\n"
         "        return RecordsPath(RECORDS_PATH_DIRECTORY, None)\n"
         "    if not records_dir.exists():\n"
         "        return RecordsPath(RECORDS_PATH_ABSENT, None)\n"
         "    try:\n        info = os.stat(records_dir)\n    except FileNotFoundError:"))],
    "M15 metadata OSError folded back into absent (R4-1 fix removed)": [(
        "    except OSError as exc:\n        return RecordsPath(RECORDS_PATH_ERROR, (",
        ("    except OSError as exc:\n"
         "        return RecordsPath(RECORDS_PATH_ABSENT, None)\n"
         "        return RecordsPath(RECORDS_PATH_ERROR, ("))],
    "M16 main() re-probes the filesystem for its notice (R4-1 fix removed)": [(
        "    if outcome.notice:\n        print(outcome.notice)",
        ("    if not args.records_dir.exists():\n"
         "        print(NOTICE_ABSENT)\n"
         "    elif not discover_records(args.records_dir)[0]:\n"
         "        print(NOTICE_NO_RECORDS)"))],
    "M17 UNCLASSIFIABLE_RECORDS_ENTRY report suppressed (R4-1 guard removed)": [(
        ('                problems.append(\n                    f"{path.relative_to(root).as_posix()}: '
         'UNCLASSIFIABLE_RECORDS_ENTRY'),
        ('                continue\n                problems.append(\n'
         '                    f"{path.relative_to(root).as_posix()}: UNCLASSIFIABLE_RECORDS_ENTRY'))],
    # Deliberately narrow: `if False:` here would have DROPPED every problem,
    # which the ordinary CLI controls kill for the wrong reason (no verdict at
    # all) and which proves nothing about the notice invariant. This keeps the
    # verdict intact and only re-permits a contradictory notice beside it.
    "M18 notice allowed to accompany problems again (R1-7/R4-1 invariant removed)": [(
        "    if problems:\n        return ValidationOutcome(problems, None)",
        ("    if problems:\n        return ValidationOutcome(\n"
         "            problems, NOTICE_NO_RECORDS if not record_paths else None)"))],
    "M19 broken records symlink folded into absent (R4-1 fix removed)": [(
        ('        return RecordsPath(RECORDS_PATH_ERROR, (\n'
         '            f"{records_dir}: BROKEN_RECORDS_SYMLINK'),
        ('        return RecordsPath(RECORDS_PATH_ABSENT, None)\n'
         '        return RecordsPath(RECORDS_PATH_ERROR, (\n'
         '            f"{records_dir}: BROKEN_RECORDS_SYMLINK'))],
    "M20 consumer re-probes entry type through pathlib (R4-1 fix removed)": [(
        "        if entry.is_dir or path.name in IGNORED_NON_RECORD_FILES:",
        "        if path.is_dir() or path.name in IGNORED_NON_RECORD_FILES:")],
    # Added 2026-10-05 for round-5 finding R5-1. The round-4 battery (M14-M20)
    # anchored on the branches round 4 had just written, and R5-1 was the one
    # error-classification branch none of them touched: M15 mutates the OUTER
    # `except OSError`, M19 mutates the sibling BROKEN_RECORDS_SYMLINK return,
    # and neither reaches the inner lstat handler. M21 is therefore the
    # literal pre-fix state of that branch — the `except OSError: return
    # ABSENT` fold the round-5 review found live at HEAD while 55/55 tests and
    # 20/20 mutants were green. M22 reintroduces the same fold by the other
    # available route (classifying lstat's *error* as absent while leaving the
    # ENOENT handler in place), which is why the kill must come from the
    # asymmetric behavioral tests and the decision-level structural lock
    # rather than from a shape-specific guard. A fix that only M21 catches is
    # not a fix.
    "M21 lstat OSError folded back into absent (R5-1 root cause restored)": [(
        ("        except FileNotFoundError:\n"
         "            return RecordsPath(RECORDS_PATH_ABSENT, None)"),
        ("        except OSError:\n"
         "            return RecordsPath(RECORDS_PATH_ABSENT, None)"))],
    "M22 lstat error branch returns absent instead of a named error (R5-1 fix removed)": [(
        ("        except OSError as exc:\n"
         "            return RecordsPath(RECORDS_PATH_ERROR, (\n"
         '                f"{records_dir}: UNREADABLE_RECORDS_PATH — the path\'s metadata could "'),
        ("        except OSError as exc:\n"
         "            return RecordsPath(RECORDS_PATH_ABSENT, None)\n"
         "            return RecordsPath(RECORDS_PATH_ERROR, (\n"
         '                f"{records_dir}: UNREADABLE_RECORDS_PATH — the path\'s metadata could "'))],
}

# Mutants that survived every control at round 1 and must now be killed.
ROUND1_SURVIVORS = {name for name in M if "SURVIVED at round 1" in name}


def _cli_rejects(mirror: Path, fixture: str) -> bool:
    """True if the mirror CLI still exits 1 over `fixture` (i.e. still rejects)."""
    result = subprocess.run(
        [PY, "tools/validate_migration_ordering.py",
         "--records-dir", str(mirror / "fixtures" / fixture)],
        cwd=mirror, capture_output=True, text=True, check=False)
    return result.returncode == 1


def main() -> int:
    original = REAL_TOOL.read_text()
    bad = [name for name, pairs in M.items()
           if any(original.count(old) != 1 for old, _ in pairs)]
    if bad:
        print(f"INVALID: anchors not matching exactly once: {bad}")
        return 2

    mirror = _build_mirror()
    copy = mirror / "tools" / "validate_migration_ordering.py"
    results: list[tuple[str, list[str]]] = []
    try:
        # Baseline: unmutated mirror must be sane, or no kill claim means anything.
        copy.write_text(original)
        base_unit = subprocess.run([PY, "tools/tests/test_validate_migration_ordering.py"],
                                   cwd=mirror, capture_output=True, text=True, check=False)
        base_ok = (base_unit.returncode == 0
                   and _cli_rejects(mirror, "negative")
                   and _cli_rejects(mirror, "lone_contract"))
        print(f"m0 baseline (unmutated): {'SANE' if base_ok else 'INSANE'} — "
              f"unit exit {base_unit.returncode}, {base_unit.stdout.strip().splitlines()[-1] if base_unit.stdout.strip() else '(no output)'}",
              flush=True)
        if not base_ok:
            print("ABORT: unmutated baseline is not sane; no kill verdict is meaningful.")
            return 2

        for name, pairs in M.items():
            mutated = original
            for old, new in pairs:
                mutated = mutated.replace(old, new)
            copy.write_text(mutated)
            killed: list[str] = []
            unit = subprocess.run([PY, "tools/tests/test_validate_migration_ordering.py"],
                                  cwd=mirror, capture_output=True, text=True, check=False)
            if unit.returncode != 0:
                killed.append("unit")
            if not _cli_rejects(mirror, "negative"):
                killed.append("cli-negative")
            if not _cli_rejects(mirror, "lone_contract"):
                killed.append("cli-lone")
            results.append((name, killed))
            print(f"{name}: {'KILLED by ' + '+'.join(killed) if killed else 'SURVIVED'}",
                  flush=True)
    finally:
        shutil.rmtree(mirror, ignore_errors=True)
        _assert_real_files_unchanged()

    survivors = [n for n, k in results if not k]
    print(f"\nreal tool sha256 unchanged:  {REAL_SHA}")
    print(f"real test sha256 unchanged:  {REAL_TEST_SHA}")
    print(f"{len(results) - len(survivors)}/{len(results)} mutations killed; "
          f"survivors={survivors}")
    still_surviving = sorted(ROUND1_SURVIVORS.intersection(survivors))
    if still_surviving:
        print(f"ROUND-1 SURVIVORS NOT YET KILLED: {still_surviving}")
    else:
        print(f"round-1 survivors now killed: {sorted(ROUND1_SURVIVORS)}")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
