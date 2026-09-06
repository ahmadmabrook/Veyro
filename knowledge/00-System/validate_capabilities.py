#!/usr/bin/env python3
"""
Capability supply-chain governance validator.

Authored 2026-09-06 (Phase 7 remediation, SEC-07). An independent
fresh-context `veyro-security-reviewer` proved, by injecting four
simultaneous synthetic fixtures into scratch copies of
`module-capabilities.yaml` and `CAPABILITY_REGISTRY.md` (an unregistered
capability, a scope-expanded duplicate capability_id, a registry row with
blank provenance/hash/approved_by and a past-due next_review_due, and a
malformed version string) — this project's capability supply-chain
governance (`CAPABILITY_POLICY.md`'s "Fail-closed rule (absolute)": an
unregistered capability must produce `BLOCKED: CAPABILITY_UNREGISTERED`)
had ZERO technical enforcement. Both `validate_catalog.py` and
`evidence_integrity_check.py` PASSed against every injected fixture; no
tool in the repo actually opens, parses, or cross-checks the registry
against the manifest. `CAPABILITY_POLICY.md`'s fail-closed rule was
stated absolutely with no caveat that enforcement was manual/review-time
only.

This script closes that gap mechanically (not a replacement for human/
fresh-context review — a second, independent layer alongside it):

1. Every `capability_id` in `module-capabilities.yaml` must appear
   exactly once (no duplicates — a duplicate is itself a supply-chain
   integrity failure, silently overwritten data or an attempted scope
   expansion under an existing ID).
2. Every `capability_id` in `module-capabilities.yaml` must exist as a
   row in `CAPABILITY_REGISTRY.md`'s table. Absence is
   `BLOCKED: CAPABILITY_UNREGISTERED`, per `CAPABILITY_POLICY.md`'s own
   stated rule.
3. Every registry row that capability depends on must show a
   `review_status` containing "APPROVED" (a `QUALIFIED`-only row cannot
   satisfy a module dependency, per `CAPABILITY_POLICY.md`'s fail-closed
   reminder: "No module task may depend on a capability whose
   review_status is not APPROVED, except the qualification drill
   itself").
4. `approved_by` must be non-empty for an APPROVED row, UNLESS the row's
   `review_status` text itself documents a first-party/harness exemption
   (the project's own established pattern for CAP-003/CAP-004/first-party
   Browser-and-Simulator harness tools) — an approval with no exemption
   language and no named approver is the exact defect this check exists
   to catch.
5. `next_review_due` must not be in the past for any APPROVED row
   (excluding rows whose review_status documents an exemption, which
   carry `N/A (exemption)` by design).
6. Registry rows for a dependency must not have an EMPTY provenance,
   version, or content_hash cell UNLESS the row documents a first-party
   exemption (again matching CAP-003/CAP-004's already-documented,
   policy-sanctioned pattern of `N/A` cells).

This is a lightweight, purpose-built parser (regex-based, consistent with
this project's other validators) rather than a YAML library dependency —
`module-capabilities.yaml`'s structure is simple and stable enough that a
targeted parser is more appropriate than adding a new third-party
dependency for one small file.
"""
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True,
    cwd=Path(__file__).resolve().parent,
).stdout.strip())
assert (ROOT / ".git").exists(), f"expected repo root, got {ROOT}"

MANIFEST = ROOT / "knowledge/03-Modules/MOD-000/evidence/module-capabilities.yaml"
REGISTRY = ROOT / "knowledge/00-System/CAPABILITY_REGISTRY.md"

REGISTRY_COLUMNS = [
    "id", "capability", "provenance", "version", "content_hash", "scope",
    "review_status", "qualified_by", "qualified_date", "approved_by",
    "approved_date", "last_reviewed_at", "next_review_due",
    "rollback_target", "evidence",
]


def parse_manifest_capability_ids(text: str) -> list[str]:
    """Every `capability_id: CAP-NNN` occurrence, in order, duplicates
    included (duplicate detection is the caller's job — this just extracts)."""
    return re.findall(r"capability_id:\s*(CAP-\d+)", text)


def parse_registry_rows(text: str) -> dict:
    """Parse CAPABILITY_REGISTRY.md's pipe-table data rows (first cell
    matches CAP-NNN) into {capability_id: {column_name: cell_text}}."""
    rows = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("| CAP-"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != len(REGISTRY_COLUMNS):
            continue  # malformed row — a real gap, but this validator's job is
            # supply-chain field checks, not markdown-table-shape checks
        row = dict(zip(REGISTRY_COLUMNS, cells))
        rows[row["id"]] = row
    return rows


# Hardened 2026-09-06 (Phase 7 re-review, RR-3): the original check was a
# bare `"exemption" in review_status.lower()` substring test. An
# independent fresh-context re-review proved this is a one-word kill
# switch — appending the literal text "(documented exemption)" to ANY
# row's review_status, including a row already missing every required
# field, disabled checks 4/5/6 entirely and produced a false PASS. It
# also matters today: CAP-003/004/005's real review_status text already
# contains the bare word "exemption" incidentally, so those checks were
# already inert for half the registry. Requiring the specific, narrower
# "first-party ... exemption" phrase this project's own established
# pattern actually uses (see CAP-003/004's real rows) closes the
# one-word bypass; it is still a text match, not a structural field, and
# should eventually become its own registry column rather than free text
# — tracked, not built this chunk.
_EXEMPTION_RE = re.compile(r"first-party.{0,40}exemption", re.IGNORECASE)


def is_exempted(review_status: str) -> bool:
    return bool(_EXEMPTION_RE.search(review_status))


def main():
    if not MANIFEST.exists():
        print(f"BLOCKED: CAPABILITY_MANIFEST_UNREADABLE — {MANIFEST} does not exist.")
        return 1
    if not REGISTRY.exists():
        print(f"BLOCKED: CAPABILITY_REGISTRY_UNREADABLE — {REGISTRY} does not exist.")
        return 1

    manifest_text = MANIFEST.read_text(encoding="utf-8", errors="replace")
    registry_text = REGISTRY.read_text(encoding="utf-8", errors="replace")

    manifest_ids = parse_manifest_capability_ids(manifest_text)
    registry_rows = parse_registry_rows(registry_text)

    errors = []
    info = []

    # 1. Duplicate capability_id in the manifest
    seen = set()
    duplicates = set()
    for cid in manifest_ids:
        if cid in seen:
            duplicates.add(cid)
        seen.add(cid)
    if duplicates:
        errors.append(f"Duplicate capability_id in module-capabilities.yaml (scope-expansion-under-existing-ID risk, or corrupted manifest): {sorted(duplicates)}")
    else:
        info.append(f"{len(seen)} distinct capability_id(s) in manifest, no duplicates.")

    today = date.today().isoformat()

    for cid in sorted(seen):
        row = registry_rows.get(cid)
        # 2. Unregistered capability — the exact defect CAPABILITY_POLICY.md's
        #    fail-closed rule names explicitly.
        if row is None:
            errors.append(f"BLOCKED: CAPABILITY_UNREGISTERED — {cid} is used in module-capabilities.yaml but has no row in {REGISTRY}.")
            continue

        review_status = row.get("review_status", "")
        exempt = is_exempted(review_status)

        # 3. Must be APPROVED, not merely QUALIFIED, to satisfy a dependency.
        if "approved" not in review_status.lower():
            errors.append(f"{cid}: review_status '{review_status}' does not contain APPROVED — cannot satisfy a module dependency (QUALIFIED-only is insufficient per CAPABILITY_POLICY.md's fail-closed reminder).")

        # 4. approved_by required unless exempted.
        approved_by = row.get("approved_by", "")
        if not exempt and (not approved_by or approved_by.upper().startswith("N/A")):
            errors.append(f"{cid}: APPROVED with no named approved_by and no documented first-party/harness exemption — an approval with no accountable Opus reviewer.")

        # 5. next_review_due not in the past, unless exempted.
        next_review_due = row.get("next_review_due", "")
        if not exempt:
            m = re.match(r"(\d{4}-\d{2}-\d{2})", next_review_due)
            if not m:
                errors.append(f"{cid}: next_review_due '{next_review_due}' is not a parseable date and is not exempted.")
            elif m.group(1) < today:
                errors.append(f"{cid}: next_review_due {m.group(1)} is in the past (today: {today}) — cannot satisfy any gate until re-evaluated, per CAPABILITY_POLICY.md.")

        # 6. provenance / version / content_hash must not be blank unless exempted.
        for field in ("provenance", "version", "content_hash"):
            value = row.get(field, "")
            if not exempt and not value:
                errors.append(f"{cid}: required supply-chain field '{field}' is empty and not exempted.")

        if not errors or all(not e.startswith(cid) for e in errors):
            info.append(f"{cid}: registered, {review_status[:60]}{'...' if len(review_status) > 60 else ''}")

    print("=" * 70)
    print("MOD-000 CAPABILITY SUPPLY-CHAIN VALIDATOR")
    print("=" * 70)
    print(f"\nManifest: {MANIFEST}\nRegistry: {REGISTRY}")
    print(f"\n--- INFO ({len(info)}) ---")
    for i in info:
        print(f"  [i] {i}")
    print(f"\n--- ERRORS ({len(errors)}) ---")
    for e in errors:
        print(f"  [X] {e}")
    print("\n" + "=" * 70)
    if errors:
        print(f"RESULT: FAIL — {len(errors)} error(s) found.")
        return 1
    print(f"RESULT: PASS — {len(seen)} capability/capabilities, all registered and APPROVED with required fields present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
