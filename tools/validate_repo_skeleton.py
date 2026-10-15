#!/usr/bin/env python3
"""Fail-closed MOD-001 GOV-01-R01 repository-skeleton check.

REQUIRED_PATHS enumerates only the currently required files; passing it does
not certify the full repository topology or test pyramid. MOD-001's full
target topology (IMPLEMENTATION.md §1) also names admin-web/, frontdesk-web/,
mobile/, contracts/, infra/, .github/workflows/, and tools/ itself, none of
which are in this manifest yet - hardcoding them as required before they are
built would make this check report a false FAIL against legitimate
not-yet-built work. Missing, wrong-type and symlinked paths fail with a named
reason. The check is read-only. Scenario and evidence: SCENARIOS.md
SCN-MOD001-003; status: IMPLEMENTATION.md §1.
"""
import argparse
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True,
    cwd=Path(__file__).resolve().parent,
).stdout.strip())
assert (ROOT / ".git").exists(), f"expected repo root, got {ROOT}"

# Add paths only when their topology becomes mandatory; this is not a claim
# that the complete MOD-001 repository skeleton is present.
REQUIRED_PATHS = [
    "backend/pyproject.toml",
    "backend/app/__init__.py",
    "backend/app/modules/_shared/__init__.py",
    "backend/tests/unit/__init__.py",
    "backend/tests/component/__init__.py",
    "backend/tests/integration/__init__.py",
    "backend/tests/contract/__init__.py",
]


def path_problem(root: Path, rel: str) -> str | None:
    """Returns None if `rel` is a valid required path under `root`, else a
    short reason. Fails closed: every component below `root` must be a real
    (non-symlink) entry, intermediate components must be directories, and the
    final component must be a regular file (or a directory if `rel` ends with
    "/"). `Path.exists()` alone would pass a directory standing in for a
    required file, or a symlink (even dangling-to-elsewhere) standing in for a
    required path or one of its ancestors."""
    parts = Path(rel).parts
    cur = root
    for i, part in enumerate(parts):
        cur = cur / part
        try:
            mode = cur.lstat().st_mode
        except OSError:
            return "missing"
        if stat.S_ISLNK(mode):
            return "symlink in path"
        last = i == len(parts) - 1
        if not last:
            if not stat.S_ISDIR(mode):
                return "ancestor is not a directory"
        elif rel.endswith("/"):
            if not stat.S_ISDIR(mode):
                return "not a directory"
        elif not stat.S_ISREG(mode):
            return "not a regular file"
    return None


def find_invalid_paths(root: Path, required_paths: list[str]) -> list[tuple[str, str]]:
    """Returns `(path, reason)` for every required path that is missing or
    of the wrong type, in declared order."""
    return [(rel, why) for rel in required_paths if (why := path_problem(root, rel))]


def find_missing_paths(root: Path, required_paths: list[str]) -> list[str]:
    """Returns the subset of `required_paths` that are missing or invalid
    (wrong type, or reached through a symlink) under `root`, in declared
    order. Empty list means every required path is a genuine entry (PASS). A
    required top-level directory being deleted entirely surfaces every path
    nested under it as its own entry, rather than being collapsed into a
    single parent check."""
    return [rel for rel, _ in find_invalid_paths(root, required_paths)]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Repository-skeleton required-path validator (MOD-001, "
                     "SCN-MOD001-003). Fails closed (non-zero exit, every missing "
                     "path individually named) if any required path is absent; "
                     "exits 0 with a clean PASS if all are present."
    )
    p.add_argument(
        "--root", type=Path, default=ROOT,
        help=f"Repository root to validate (default: {ROOT}). Point this at a "
             "throwaway fixture directory for negative testing without touching "
             "the real repo tree.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    root: Path = args.root

    missing = find_invalid_paths(root, REQUIRED_PATHS)

    print("=" * 70)
    print("MOD-001 REPOSITORY-SKELETON REQUIRED-PATH VALIDATOR")
    print("=" * 70)
    print(f"\nRoot checked: {root}")
    print(f"Required paths checked: {len(REQUIRED_PATHS)}")

    if missing:
        print(f"\nBLOCKED: MISSING_REQUIRED_PATH — {len(missing)} required path(s) absent or invalid:")
        for rel, why in missing:
            print(f"  - {rel} ({why})")
        return 1

    print(f"\nPASS — all {len(REQUIRED_PATHS)} required paths present as genuine entries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
