#!/usr/bin/env python3
"""
Unit test for tools/validate_repo_skeleton.py (MOD-001, SCN-MOD001-003).

Proves both directions against an isolated `tempfile.TemporaryDirectory`
fixture, never the real repo tree — a separate agent is concurrently
creating the real backend/ for this same slice, and asserting against it
would make this unit test's outcome depend on that agent's own progress;
that is an integration concern, not this test's job.

  1. test_all_required_paths_present_passes — fixture with every
     REQUIRED_PATHS entry present -> find_missing_paths returns [] (PASS).
  2. test_one_required_path_missing_fails_named — same fixture with one
     required path deleted -> find_missing_paths returns exactly that one
     path, named (FAIL), not a silent partial success.
  3. test_deleting_top_level_directory_names_every_nested_path — the
     scenario's own literal case (delete a required top-level directory,
     not just one file) -> every path nested under it is individually
     named missing, none silently dropped.

Run directly with `python3 tools/tests/test_validate_repo_skeleton.py`
(no pytest dependency needed) or with pytest if available.
"""
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from validate_repo_skeleton import REQUIRED_PATHS, find_missing_paths


def _make_fixture(root: Path) -> None:
    for rel in REQUIRED_PATHS:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("")


def test_all_required_paths_present_passes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_fixture(root)
        assert find_missing_paths(root, REQUIRED_PATHS) == []


def test_one_required_path_missing_fails_named():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_fixture(root)
        victim = REQUIRED_PATHS[0]
        (root / victim).unlink()
        missing = find_missing_paths(root, REQUIRED_PATHS)
        assert missing == [victim], missing


def test_deleting_top_level_directory_names_every_nested_path():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_fixture(root)
        shutil.rmtree(root / "backend")
        missing = find_missing_paths(root, REQUIRED_PATHS)
        assert missing == REQUIRED_PATHS, missing


if __name__ == "__main__":
    test_all_required_paths_present_passes()
    test_one_required_path_missing_fails_named()
    test_deleting_top_level_directory_names_every_nested_path()
    print("PASS — all 3 tests passed.")
