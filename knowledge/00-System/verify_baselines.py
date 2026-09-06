#!/usr/bin/env python3
"""
Automated governing-baseline integrity check.

Authored 2026-09-06 (Phase 7 remediation, SEC-11). An independent
fresh-context `veyro-security-reviewer` found that, before this tool
existed, detection of a tampered/swapped governing baseline artifact was
entirely manual (re-hash by hand, compare by eye against
PROJECT_INDEX.md) — proven by appending 8 bytes to a scratch copy of the
Blueprint and confirming neither `validate_catalog.py` nor
`evidence_integrity_check.py` noticed. `git status` did notice an
in-place tracked edit, but that signal does not cover a baseline that is
swapped and then committed, nor one restored from a compromised clone.

This script reads the four expected SHA-256 hashes directly out of
`knowledge/00-System/PROJECT_INDEX.md` (never hardcodes a second copy
that could silently drift from the recorded index), recomputes all four
using the exact same procedures PROJECT_INDEX.md documents (per-file
SHA-256 for the three docx baselines; the documented deterministic
manifest procedure for the design-bundle directory), and fails closed —
`BLOCKED: BASELINE_INTEGRITY_FAILURE` — on any mismatch, missing file, or
inability to locate an expected hash in PROJECT_INDEX.md.

This tool NEVER modifies, renames, or writes to any of the four baseline
artifacts — read-only hashing only.
"""
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True,
    cwd=Path(__file__).resolve().parent,
).stdout.strip())
assert (ROOT / ".git").exists(), f"expected repo root, got {ROOT}"

PROJECT_INDEX = ROOT / "knowledge/00-System/PROJECT_INDEX.md"

# The three docx baselines are matched by filename directly inside
# PROJECT_INDEX.md's own baseline table row: `<filename>` ... `<hash>`.
DOCX_BASELINES = [
    "Gym_OS_Master_Product_Blueprint_v1_English.docx",
    "Veyro_Technical_System_Design_v1.4.1_English_FINAL.docx",
    "Veyro_Engineering_Implementation_Plan_v1.4.1_English_FINAL_APPROVED_GOVERNING_BASELINE.docx",
]
DESIGN_BUNDLE_DIR = "veyro-product-experience-design"

_HEX64 = r"[0-9a-f]{64}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_design_bundle(bundle_dir: Path) -> str:
    """Reproduces PROJECT_INDEX.md's documented deterministic manifest
    method exactly: find every tracked file (excluding .DS_Store) sorted
    by path, SHA-256 each, concatenate as "<hash>  <relpath>\\n" lines
    (this is exactly what `shasum -a 256` prints per file), then SHA-256
    the concatenated manifest text itself."""
    files = sorted(
        p for p in bundle_dir.rglob("*")
        if p.is_file() and p.name != ".DS_Store"
    )
    manifest_lines = []
    for p in files:
        rel = p.relative_to(bundle_dir)
        manifest_lines.append(f"{sha256_file(p)}  ./{rel}\n")
    manifest_text = "".join(manifest_lines)
    return hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()


def expected_docx_hash(index_text: str, filename: str) -> str | None:
    # PROJECT_INDEX.md's table row format: | # | Name | Identity | `<filename>` | `<hash>` | bytes | date |
    m = re.search(rf"`{re.escape(filename)}`\s*\|\s*`({_HEX64})`", index_text)
    return m.group(1) if m else None


def expected_manifest_hash(index_text: str) -> str | None:
    m = re.search(rf"Manifest hash \(bundle identity\):\*\*\s*`({_HEX64})`", index_text)
    return m.group(1) if m else None


def main():
    if not PROJECT_INDEX.exists():
        print(f"BLOCKED: BASELINE_INTEGRITY_FAILURE — {PROJECT_INDEX} does not exist, cannot locate expected hashes.")
        return 1
    index_text = PROJECT_INDEX.read_text(encoding="utf-8", errors="replace")

    failures = []
    checked = []

    for filename in DOCX_BASELINES:
        expected = expected_docx_hash(index_text, filename)
        if expected is None:
            failures.append(f"{filename}: no SHA-256 hash found for this filename in {PROJECT_INDEX} — cannot verify.")
            continue
        path = ROOT / filename
        if not path.exists():
            failures.append(f"{filename}: file does not exist at {path}.")
            continue
        actual = sha256_file(path)
        checked.append((filename, expected, actual))
        if actual != expected:
            failures.append(f"{filename}: HASH MISMATCH — expected {expected}, got {actual}.")

    expected_manifest = expected_manifest_hash(index_text)
    bundle_dir = ROOT / DESIGN_BUNDLE_DIR
    if expected_manifest is None:
        failures.append(f"design bundle manifest: no manifest hash found in {PROJECT_INDEX} — cannot verify.")
    elif not bundle_dir.is_dir():
        failures.append(f"design bundle manifest: directory does not exist at {bundle_dir}.")
    else:
        actual_manifest = sha256_design_bundle(bundle_dir)
        checked.append((DESIGN_BUNDLE_DIR, expected_manifest, actual_manifest))
        if actual_manifest != expected_manifest:
            failures.append(f"{DESIGN_BUNDLE_DIR}: MANIFEST HASH MISMATCH — expected {expected_manifest}, got {actual_manifest}.")

    print(f"Checked {len(checked)} of {len(DOCX_BASELINES) + 1} expected governing baselines against {PROJECT_INDEX}:")
    for name, expected, actual in checked:
        status = "MATCH" if expected == actual else "MISMATCH"
        print(f"  [{status}] {name}: {actual}")

    if failures:
        print(f"\nBLOCKED: BASELINE_INTEGRITY_FAILURE — {len(failures)} finding(s):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"\nPASS — all {len(checked)} governing baseline hashes match {PROJECT_INDEX} exactly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
