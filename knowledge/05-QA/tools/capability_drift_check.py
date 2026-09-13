#!/usr/bin/env python3
"""Material-change / version-drift detector for CAPABILITY_REGISTRY.md.

Authored 2026-09-13, Phase 10 readiness, closing BUG-025 / SCN-MOD000-084
("Material capability change triggers mandatory re-evaluation" -- EIP
Sec4.2 stage 9). `validate_capabilities.py` (2026-09-06) checks that
required fields are non-blank, but never compares a capability's
*current* `version`/`content_hash` against the value recorded *at
approval time* -- so a capability whose version silently changed after
approval, with `review_status`/`approved_by` left untouched, would still
report PASS. This script closes that specific gap.

Why this is a separate script rather than an extension of
`validate_capabilities.py`: that file's SHA-256 hash is pinned inside
`.claude/security/bash_guard.py`'s `_ALLOWED_PYTHON_SCRIPTS` map, and
`.claude/security/**` is Edit/Write-denied to this session (by design).
Editing `validate_capabilities.py` would silently break its own
guard-trust the moment its hash no longer matched the pinned value --
so a *new* file is the only way to add this check without requiring an
owner-authorized `bash_guard.py` edit as a prerequisite. (Wiring this
new script into the guard's allowlist has the same disclosed activation
gap as `run_regression.py` -- see that script's own docstring and
`knowledge/05-QA/REGRESSION_INDEX.md`.)

Mechanism: `CAPABILITY_REGISTRY.md`'s "Version/hash snapshot at
approval" section (added alongside this script) records each
capability's `version` and `content_hash` as of its `approved_date`.
This script re-reads the registry's live `version`/`content_hash`
cells and compares them against that snapshot. A mismatch means a
material change happened without a matching re-approval -- exactly the
condition SCN-084/BUG-025 named.

Usage:
    python3 knowledge/05-QA/tools/capability_drift_check.py
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True,
    cwd=Path(__file__).resolve().parent,
).stdout.strip())
assert (ROOT / ".git").exists(), f"expected repo root, got {ROOT}"

REGISTRY = ROOT / "knowledge/00-System/CAPABILITY_REGISTRY.md"

REGISTRY_COLUMNS = [
    "id", "capability", "provenance", "version", "content_hash", "scope",
    "review_status", "qualified_by", "qualified_date", "approved_by",
    "approved_date", "last_reviewed_at", "next_review_due",
    "rollback_target", "evidence",
]

# Matches a snapshot-table data row: | CAP-NNN | version | content_hash |
SNAPSHOT_ROW_RE = re.compile(r"^\|\s*(CAP-\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|$")


def parse_registry_rows(text: str) -> tuple[dict, list]:
    """Returns (rows, unparsed_lines). A line starting '| CAP-' that does
    NOT split into exactly len(REGISTRY_COLUMNS) cells is a real parsing
    failure, not noise -- it is returned in unparsed_lines rather than
    silently dropped, so main() can fail closed on it instead of quietly
    checking fewer capabilities than exist (found by the final
    certification-scope Gatekeeper review, 2026-09-13, P2-2: the original
    version's bare `continue` let a capability go unchecked with no
    error and a still-PASSing exit code)."""
    rows = {}
    unparsed = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("| CAP-"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != len(REGISTRY_COLUMNS):
            unparsed.append((line, len(cells)))
            continue
        row = dict(zip(REGISTRY_COLUMNS, cells))
        rows[row["id"]] = row
    return rows, unparsed


def parse_snapshot(text: str) -> dict:
    """Parse the 'Version/hash snapshot at approval' table into
    {id: (version, content_hash)}. Only rows inside that section are
    considered, found by scanning after its own heading marker."""
    marker = "## Version/hash snapshot at approval"
    if marker not in text:
        return {}
    section = text.split(marker, 1)[1]
    # Stop at the next '##' heading so we don't read past the section.
    section = section.split("\n## ", 1)[0]
    snapshot = {}
    for line in section.splitlines():
        m = SNAPSHOT_ROW_RE.match(line.strip())
        if m:
            cid, version, content_hash = m.groups()
            snapshot[cid] = (version, content_hash)
    return snapshot


def main():
    if not REGISTRY.exists():
        print(f"BLOCKED: CAPABILITY_REGISTRY_UNREADABLE — {REGISTRY} does not exist.")
        return 1

    text = REGISTRY.read_text(encoding="utf-8", errors="replace")
    rows, unparsed = parse_registry_rows(text)
    snapshot = parse_snapshot(text)

    errors = []
    info = []

    for line, cell_count in unparsed:
        errors.append(
            f"UNPARSEABLE REGISTRY ROW — expected {len(REGISTRY_COLUMNS)} "
            f"cells, got {cell_count}: {line!r}. This capability is NOT "
            f"being drift-checked until this row is fixed — fix the row, "
            f"do not ignore this finding."
        )

    if not snapshot:
        print("BLOCKED: NO_SNAPSHOT_SECTION — 'Version/hash snapshot at "
              "approval' section not found in CAPABILITY_REGISTRY.md. "
              "This check cannot run without it.")
        return 1

    for cid, row in sorted(rows.items()):
        snap = snapshot.get(cid)
        if snap is None:
            errors.append(f"{cid}: no snapshot row recorded — cannot detect drift for this capability. Add one in the same commit that approves it.")
            continue
        snap_version, snap_hash = snap
        live_version = row.get("version", "")
        live_hash = row.get("content_hash", "")
        if snap_version != live_version:
            errors.append(
                f"{cid}: MATERIAL CHANGE DETECTED — version drifted from "
                f"'{snap_version}' (at approval) to '{live_version}' (current) "
                f"with no matching re-approval. Per CAPABILITY_POLICY.md stage 9, "
                f"this requires a fresh stage 4-5 pass before continued reliance."
            )
        if snap_hash != live_hash:
            errors.append(
                f"{cid}: MATERIAL CHANGE DETECTED — content_hash drifted from "
                f"'{snap_hash}' (at approval) to '{live_hash}' (current) with no "
                f"matching re-approval."
            )
        if snap_version == live_version and snap_hash == live_hash:
            info.append(f"{cid}: version/hash unchanged since approval — no drift.")

    # Reverse direction (found by the second certification-scope Gatekeeper
    # review, 2026-09-13): the loop above only walks live registry rows, so a
    # capability present in the snapshot section but deleted or renamed out
    # of the live table produced no error and still exited PASS. A missing
    # capability is itself a material change worth flagging, not silence.
    for cid in sorted(set(snapshot) - set(rows)):
        errors.append(
            f"{cid}: has a snapshot row but no corresponding live registry "
            f"row — either deleted, renamed, or the registry table is "
            f"malformed. This capability is unaccounted for."
        )

    print("=" * 70)
    print("MOD-000 CAPABILITY MATERIAL-CHANGE / VERSION-DRIFT CHECK")
    print("=" * 70)
    print(f"\nRegistry: {REGISTRY}\n")
    if info:
        print(f"--- INFO ({len(info)}) ---")
        for line in info:
            print(f"  [i] {line}")
        print()
    if errors:
        print(f"--- ERRORS ({len(errors)}) ---")
        for line in errors:
            print(f"  [!] {line}")
        print()
    print("=" * 70)
    if errors:
        print(f"RESULT: FAIL — {len(errors)} finding(s).")
        return 1
    print(f"RESULT: PASS — {len(info)} capabilities checked, no drift detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
