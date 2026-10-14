#!/usr/bin/env python3
"""
Unit test for tools/validate_repo_skeleton.py (MOD-001, SCN-MOD001-003).

Uses isolated `tempfile.TemporaryDirectory` fixtures; the real repository
is checked separately by the validator CLI.

  1. test_all_required_paths_present_passes — fixture with every
     REQUIRED_PATHS entry present -> find_missing_paths returns [] (PASS).
  2. test_one_required_path_missing_fails_named — same fixture with one
     required path deleted -> find_missing_paths returns exactly that one
     path, named (FAIL), not a silent partial success.
  3. test_deleting_top_level_directory_names_every_nested_path — the
     scenario's own literal case (delete a required top-level directory,
     not just one file) -> every path nested under it is individually
     named missing, none silently dropped.

Run directly with `backend/.venv/bin/python tools/tests/test_validate_repo_skeleton.py`
(no pytest dependency needed) or with pytest if available.
"""
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from validate_repo_skeleton import REQUIRED_PATHS, find_invalid_paths, find_missing_paths


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


def test_directory_in_place_of_required_file_fails():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_fixture(root)
        victim = REQUIRED_PATHS[0]
        (root / victim).unlink()
        (root / victim).mkdir()
        assert find_invalid_paths(root, REQUIRED_PATHS) == [(victim, "not a regular file")]


def test_file_in_place_of_ancestor_directory_fails():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_fixture(root)
        shutil.rmtree(root / "backend" / "tests" / "unit")
        (root / "backend" / "tests" / "unit").write_text("")
        victim = "backend/tests/unit/__init__.py"
        assert find_invalid_paths(root, [victim]) == [(victim, "ancestor is not a directory")]


def test_symlinked_required_file_fails():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_fixture(root)
        victim = REQUIRED_PATHS[0]
        target = root / "elsewhere.txt"
        target.write_text("")
        (root / victim).unlink()
        (root / victim).symlink_to(target)
        assert find_invalid_paths(root, REQUIRED_PATHS) == [(victim, "symlink in path")]


def test_symlinked_ancestor_directory_fails():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_fixture(root)
        real = root / "real_backend"
        (root / "backend").rename(real)
        (root / "backend").symlink_to(real, target_is_directory=True)
        assert find_missing_paths(root, REQUIRED_PATHS) == REQUIRED_PATHS


def test_dangling_symlink_fails():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_fixture(root)
        victim = REQUIRED_PATHS[0]
        (root / victim).unlink()
        (root / victim).symlink_to(root / "does_not_exist")
        assert find_missing_paths(root, REQUIRED_PATHS) == [victim]


def test_trailing_slash_requires_real_directory():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "d").mkdir()
        (root / "f").write_text("")
        assert find_missing_paths(root, ["d/"]) == []
        assert find_missing_paths(root, ["f/"]) == ["f/"]


if __name__ == "__main__":
    test_all_required_paths_present_passes()
    test_one_required_path_missing_fails_named()
    test_deleting_top_level_directory_names_every_nested_path()
    test_directory_in_place_of_required_file_fails()
    test_file_in_place_of_ancestor_directory_fails()
    test_symlinked_required_file_fails()
    test_symlinked_ancestor_directory_fails()
    test_dangling_symlink_fails()
    test_trailing_slash_requires_real_directory()
    print("PASS — all 9 tests passed.")
