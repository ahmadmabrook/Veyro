#!/usr/bin/env python3
"""
Repository-skeleton required-path validator (MOD-001, GOV-01-R01 test-pyramid
infrastructure slice).

Per `knowledge/03-Modules/MOD-001/SCENARIOS.md` SCN-MOD001-003 (Group A —
Repository skeleton): "delete a required top-level directory... re-run the
bootstrap/lint check. Expected: the check fails closed with a named
'missing required directory' error, not a silent partial success." This
script is that bootstrap/lint check: it walks a manifest of required repo
paths, reports PASS (exit 0) only if every one exists, and otherwise fails
closed (non-zero exit, every missing path individually named — never a
partial/silent success).

## Why the manifest is deliberately incomplete right now

MOD-001's full target topology (`IMPLEMENTATION.md` §1) also names
admin-web/, frontdesk-web/, mobile/, contracts/, infra/,
.github/workflows/, and tools/ itself — none of which are built yet. Only
backend/ is being built this slice (a separate concurrent agent is
creating backend/pyproject.toml, backend/app/**,
backend/tests/{unit,component,integration,contract}/**). Hardcoding the
full future topology as "required" would make this tool report a false
FAIL against legitimate not-yet-built work — dishonest evidence, and the
opposite of what a fail-closed gate is for. REQUIRED_PATHS below is
therefore seeded with only what this slice actually creates.

This manifest grows as each MOD-001 topology slice lands (see
IMPLEMENTATION.md §1); it is deliberately NOT the full target topology
yet. Future slices add their own entries to the plain list below — no
sidecar config file is used, since the list itself is already the
smallest thing that is both human-editable and diffable (matching
`validate_baseline_binding.py`'s own `BASELINE_ARTIFACTS` list
convention, not `validate_capability_manifest.py`'s pattern, which reads
an externally-authored manifest rather than declaring one).

## Naming: MISSING_REQUIRED_PATH, not the scenario's literal
## "missing required directory"

REQUIRED_PATHS mixes files (`backend/pyproject.toml`,
`backend/app/__init__.py`) and would-be directories, so the emitted error
code is the accurate superset name, MISSING_REQUIRED_PATH — reported
alongside the human-readable scenario framing so the intent stays
traceable. Deleting an actual top-level directory (e.g. `backend/`, the
scenario's literal case) is handled correctly without a separate
directory-only check: every REQUIRED_PATHS entry nested under it stops
existing too, so each is individually named missing — not collapsed into
one vague "backend/ is gone" line and not silently skipped.

This tool never writes to the checked tree — read-only, always.
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True,
    cwd=Path(__file__).resolve().parent,
).stdout.strip())
assert (ROOT / ".git").exists(), f"expected repo root, got {ROOT}"

# This manifest grows as each MOD-001 topology slice lands (see
# IMPLEMENTATION.md §1); it is deliberately NOT the full target topology yet.
REQUIRED_PATHS = [
    "backend/pyproject.toml",
    "backend/app/__init__.py",
    "backend/app/modules/_shared/__init__.py",
    "backend/tests/unit/__init__.py",
    "backend/tests/component/__init__.py",
    "backend/tests/integration/__init__.py",
    "backend/tests/contract/__init__.py",
]


def find_missing_paths(root: Path, required_paths: list[str]) -> list[str]:
    """Returns the subset of `required_paths` that do not exist under
    `root`, in declared order. Empty list means every required path is
    present (PASS). A path is checked with `Path.exists()`, so a required
    top-level directory being deleted entirely correctly surfaces every
    path nested under it as its own missing entry, rather than being
    silently absorbed into a single parent check."""
    return [rel for rel in required_paths if not (root / rel).exists()]


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

    missing = find_missing_paths(root, REQUIRED_PATHS)

    print("=" * 70)
    print("MOD-001 REPOSITORY-SKELETON REQUIRED-PATH VALIDATOR")
    print("=" * 70)
    print(f"\nRoot checked: {root}")
    print(f"Required paths checked: {len(REQUIRED_PATHS)}")

    if missing:
        print(f"\nBLOCKED: MISSING_REQUIRED_PATH — {len(missing)} required path(s) absent:")
        for rel in missing:
            print(f"  - {rel}")
        return 1

    print(f"\nPASS — all {len(REQUIRED_PATHS)} required paths present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
