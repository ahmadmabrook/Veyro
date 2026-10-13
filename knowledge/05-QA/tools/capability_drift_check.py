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

# The 'Version/hash snapshot at approval' section is a *different* table
# from the live registry table above it, using the same '| CAP-NNN | ... |'
# leading shape but only 3 cells, not REGISTRY_COLUMNS' 15. Both parsers
# key off this one marker so the split point can never disagree between
# them (added 2026-10-01, BUG-043: the live-row parser used to scan the
# *whole* file including this section, misreporting every 3-cell snapshot
# row as an "UNPARSEABLE REGISTRY ROW").
SNAPSHOT_MARKER = "## Version/hash snapshot at approval"

# The existing convention this file already uses for CAP-007 (added
# 2026-09-28, OWN-006/ADR-007): a dated prose marker, not a table column,
# recording a capability lifecycle transition. Date is captured as a
# literal ISO string (not free text) so multiple markers for the same
# capability can be sorted and the *latest* one resolved -- added
# 2026-10-01 (BUG-045) after the original single-match version let any
# RETIRED marker win permanently, with no way for a later REINSTATED/
# ACTIVE marker to supersede it.
STATUS_UPDATE_RE = re.compile(
    r"\*\*(CAP-\d+) status update \((\d{4}-\d{2}-\d{2})\):\s*(RETIRED|REVOKED|REINSTATED|ACTIVE)\.\*\*"
)

# The "## Lifecycle status" section's own per-capability sentence (the
# exact phrasing this file uses, e.g. "CAP-007's `lifecycle_status` is
# now **`REVOKED`**"). Treated as the authoritative corroborating record
# a status-update marker must agree with before it's trusted -- an
# unbacked marker (no matching sentence here) must not be able to
# silently retire/reinstate a capability on its own.
LIFECYCLE_FIELD_RE = re.compile(
    r"(CAP-\d+)'s `lifecycle_status` is now \*\*`(ACTIVE|DEPRECATED|REVOKED)`\*\*"
)

_RETIRED_WORDS = {"RETIRED", "REVOKED"}
_ACTIVE_WORDS = {"REINSTATED", "ACTIVE"}


def _lifecycle_bucket(word: str) -> str:
    """Collapses the 4 status-update words (+ the field's own 3-value
    enum) into the 2 buckets this check actually cares about: whether a
    capability is currently being relied upon or not. DEPRECATED has no
    clean bucket -- deliberately returns 'UNKNOWN' so it can never
    silently match either side."""
    if word in _RETIRED_WORDS:
        return "RETIRED"
    if word in _ACTIVE_WORDS:
        return "ACTIVE"
    return "UNKNOWN"


def resolve_capability_lifecycle(text: str) -> tuple[dict, list]:
    """Fail-closed lifecycle resolution shared by this script and
    run_regression.py. Returns (resolved, conflicts):

    - resolved: {id: 'RETIRED'|'ACTIVE'} -- only for capabilities whose
      *latest-dated* status-update marker is corroborated by a matching
      `lifecycle_status` field sentence in the same bucket. A capability
      with no status-update marker at all is simply absent here (normal
      approved/pending handling applies, unaffected).
    - conflicts: human-readable strings for any capability whose
      lifecycle state could NOT be safely resolved: same-date markers
      disagreeing with each other, or a marker with no corroborating
      field sentence, or a marker that disagrees with the field sentence.
      Callers must fail closed on these -- never guess, never silently
      treat an unresolved capability as retired (that's the exact
      direction that would suppress real drift-gating) or as reinstated.
    """
    markers: dict = {}
    for cid, date, word in STATUS_UPDATE_RE.findall(text):
        markers.setdefault(cid, []).append((date, word))

    field = dict(LIFECYCLE_FIELD_RE.findall(text))

    resolved = {}
    conflicts = []
    for cid, entries in sorted(markers.items()):
        by_date = {}
        has_same_date_conflict = False
        for date, word in entries:
            if date in by_date and by_date[date] != word:
                conflicts.append(
                    f"{cid}: conflicting status-update markers on the same date "
                    f"{date} ('{by_date[date]}' vs '{word}') — cannot safely "
                    f"resolve lifecycle state, failing closed rather than "
                    f"guessing which one is authoritative."
                )
                has_same_date_conflict = True
            by_date[date] = word
        if has_same_date_conflict:
            continue

        latest_date = max(by_date)
        latest_word = by_date[latest_date]
        latest_bucket = _lifecycle_bucket(latest_word)

        field_word = field.get(cid)
        field_bucket = _lifecycle_bucket(field_word) if field_word else None

        if field_bucket is None:
            conflicts.append(
                f"{cid}: status-update marker ('{latest_word}', {latest_date}) has "
                f"no corroborating `lifecycle_status` field sentence in the "
                f"'## Lifecycle status' section — an unbacked lifecycle claim is "
                f"not trusted; failing closed rather than silently honoring it."
            )
            continue
        if field_bucket != latest_bucket:
            conflicts.append(
                f"{cid}: status-update marker resolves to '{latest_bucket}' "
                f"('{latest_word}', {latest_date}) but the registry's own "
                f"`lifecycle_status` field says '{field_word}' ('{field_bucket}') — "
                f"disagreement between the two records; failing closed rather "
                f"than guessing which is right."
            )
            continue

        resolved[cid] = latest_bucket
    return resolved, conflicts


def parse_registry_rows(text: str) -> tuple[dict, list]:
    """Returns (rows, unparsed_lines). Only scans the live registry table
    (everything before SNAPSHOT_MARKER) -- the snapshot section below it
    uses the same '| CAP-NNN | ... |' leading shape with a different
    (3-cell) column count and must never be mistaken for a live row.
    A line starting '| CAP-' *within the live table* that does NOT split
    into exactly len(REGISTRY_COLUMNS) cells is a real parsing failure,
    not noise -- it is returned in unparsed_lines rather than silently
    dropped, so main() can fail closed on it instead of quietly checking
    fewer capabilities than exist (found by the final certification-scope
    Gatekeeper review, 2026-09-13, P2-2: the original version's bare
    `continue` let a capability go unchecked with no error and a
    still-PASSing exit code)."""
    live_table_text = text.split(SNAPSHOT_MARKER, 1)[0]
    rows = {}
    unparsed = []
    for line in live_table_text.splitlines():
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
    if SNAPSHOT_MARKER not in text:
        return {}
    section = text.split(SNAPSHOT_MARKER, 1)[1]
    # Stop at the next '##' heading so we don't read past the section.
    section = section.split("\n## ", 1)[0]
    snapshot = {}
    for line in section.splitlines():
        m = SNAPSHOT_ROW_RE.match(line.strip())
        if m:
            cid, version, content_hash = m.groups()
            snapshot[cid] = (version, content_hash)
    return snapshot


def is_approved(review_status_cell: str) -> bool:
    """A live row's review_status cell is 'approved' only if it actually
    starts with APPROVED (after stripping markdown bold markers) --
    'PENDING - ...' and similar not-yet-qualified states are not."""
    return review_status_cell.lstrip("*").strip().upper().startswith("APPROVED")


def evaluate_capability(cid: str, row: dict, snap, retired_status: str | None) -> tuple[list, list]:
    """Pure decision logic for one live registry row, extracted out of
    main() so it's directly unit-testable. Returns (errors, info)."""
    errors, info = [], []
    approved = is_approved(row.get("review_status", ""))
    live_version = row.get("version", "")
    live_hash = row.get("content_hash", "")

    if retired_status:
        if snap is not None and (snap[0] != live_version or snap[1] != live_hash):
            info.append(
                f"{cid}: {retired_status} — non-live, reapproval-for-continued-reliance "
                f"not applicable. Version/hash differ from the approval snapshot "
                f"(expected for a capability whose content changed after its last "
                f"approval and before retirement); not flagged as drift requiring "
                f"re-review since there is no continued reliance to gate."
            )
        else:
            info.append(f"{cid}: {retired_status} — non-live, reapproval-for-continued-reliance not applicable.")
        return errors, info

    if not approved:
        if snap is None:
            info.append(f"{cid}: not yet approved (review_status does not start with APPROVED) — no approval baseline to drift-check against.")
        else:
            info.append(f"{cid}: not yet approved — version/hash snapshot present but not compared, since there is no approval for it to have drifted from.")
        return errors, info

    if snap is None:
        errors.append(f"{cid}: APPROVED but no snapshot row recorded — cannot detect drift for this capability. Add one in the same commit that approves it.")
        return errors, info

    snap_version, snap_hash = snap
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
    return errors, info


def main():
    if not REGISTRY.exists():
        print(f"BLOCKED: CAPABILITY_REGISTRY_UNREADABLE — {REGISTRY} does not exist.")
        return 1

    text = REGISTRY.read_text(encoding="utf-8", errors="replace")
    rows, unparsed = parse_registry_rows(text)
    snapshot = parse_snapshot(text)
    resolved_lifecycle, lifecycle_conflicts = resolve_capability_lifecycle(text)

    errors = []
    info = []

    # Unresolved lifecycle state (same-date conflict, or a marker with no/
    # disagreeing corroboration) is itself a registry-integrity error --
    # fail closed, do not silently treat the capability as retired (that
    # would suppress its real drift-gating) or as reinstated.
    errors.extend(lifecycle_conflicts)

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
        # Only a resolved-and-corroborated RETIRED/REVOKED bucket routes
        # through the non-live path. A resolved ACTIVE bucket (e.g. a
        # later REINSTATED marker superseding an earlier RETIRED one) is
        # deliberately NOT passed through -- it falls back to normal
        # approved/pending drift-gating, exactly as if it had never been
        # retired at all.
        retired_status = resolved_lifecycle.get(cid)
        if retired_status != "RETIRED":
            retired_status = None
        cap_errors, cap_info = evaluate_capability(cid, row, snap, retired_status)
        errors.extend(cap_errors)
        info.extend(cap_info)

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
