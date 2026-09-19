#!/usr/bin/env python3
"""
CI-gate baseline-artifact binding schema validator (MOD-001, GOV-01-R04).

Authored 2026-09-19 as MOD-001's first implementation slice, per
`knowledge/03-Modules/MOD-001/REQUIREMENTS.md` §3 ("Baseline-artifact
binding schema validation") and `SCENARIOS.md` SCN-MOD001-025/026/124.

This is the CI-gate generalization of `knowledge/00-System/verify_baselines.py`
(MOD-000's manual, session-bootstrap tool). `verify_baselines.py` only
detects one failure mode — a recorded hash that no longer matches the
real artifact's bytes. The EIP mandates five distinct fail-closed
conditions for this gate, verbatim (`EIP_MIRROR.md` lines 4140-4143,
4253-4263): "Baseline-binding validator rejects use of an unapproved
candidate EIP, missing/ambiguous artifact identity, missing content hash
or identity/hash mismatch," plus "PROJECT_INDEX.md entries for all
governing baselines with non-empty cryptographic hashes and
SESSION_BOOTSTRAP.md enforcement metadata." This script implements all
five, each with its own named error code:

  - BASELINE_INTEGRITY_FAILURE          (identity/hash mismatch; also used
                                          for a missing project-index file
                                          or a missing real artifact file,
                                          matching `verify_baselines.py`'s
                                          own existing convention)
  - UNAPPROVED_CANDIDATE_EIP            (EIP artifact's PROJECT_INDEX.md
                                          row flags it candidate/unapproved
                                          rather than the approved
                                          governing baseline)
  - MISSING_OR_AMBIGUOUS_ARTIFACT_IDENTITY (a baseline has no
                                          PROJECT_INDEX.md row at all, or
                                          its identity string is shared by
                                          more than one row)
  - MISSING_CONTENT_HASH                (a row/identity is present but its
                                          hash field is empty or malformed
                                          — distinct from a mismatched hash)
  - BOOTSTRAP_ENFORCEMENT_METADATA_MISSING (SESSION_BOOTSTRAP.md's own
                                          mandatory-pre-action/fail-closed
                                          declaration is missing or gone)

Reused verbatim from `verify_baselines.py` (not imported — this script is
self-contained, matching this project's existing per-validator convention
of `knowledge/00-System/validate_capabilities.py`, which also does not
import `verify_baselines.py` — avoids coupling to a sibling script whose
module-level code runs a `subprocess` call at import time): the exact
per-file SHA-256 procedure (`sha256_file`), the exact deterministic
design-bundle manifest procedure (`sha256_design_bundle`), and the exact
regex used to pull the recorded design-bundle manifest hash out of
`PROJECT_INDEX.md` (`expected_manifest_hash`). The per-docx recorded-hash
extraction is NOT reused verbatim from `verify_baselines.py`'s
`expected_docx_hash` — that function's single regex (hash must
immediately follow the filename token) cannot distinguish "no row for
this artifact at all" from "row present, hash field empty," which this
tool must tell apart (MISSING_OR_AMBIGUOUS_ARTIFACT_IDENTITY vs.
MISSING_CONTENT_HASH). Instead this tool parses the baseline table into
discrete rows first and inspects each row's own hash cell — see
`parse_baseline_table_rows` below.

Why identity/hash extraction is scoped to markdown TABLE ROWS only, never
a whole-document substring search: `PROJECT_INDEX.md`'s own prose repeats
several identity strings and filenames outside the table (its own
"Identity binding added" paragraph quotes "VEYRO-MPB-1.0" and
"VEYRO-UX-V1-170-APPROVED" verbatim in explanatory text; its "Governing
Baseline Precedence" list repeats each docx filename in backticks with no
hash alongside). A naive whole-document occurrence count would flag the
real, correct file as MISSING_OR_AMBIGUOUS_ARTIFACT_IDENTITY (a false
positive: >1 whole-document occurrence of an identity string that appears
exactly once in the actual table). This was verified by direct
inspection of the real file's current text before this design was
finalized, not assumed. `parse_baseline_table_rows` below only matches
lines beginning `| <digit(s)> |` (the table's real data rows; both the
header row and the `|---|...` separator row are excluded, since their
first cell is not a digit), so identity/hash checks never see prose.

## SESSION_BOOTSTRAP.md "enforcement metadata" — the one condition with
## no hash-comparable ground truth; documented here for reviewer evaluation
## per the task's own instruction, since this is a rule this script had to
## invent, not one it could source-cite:

`check_bootstrap_enforcement_metadata` below fails closed
(BOOTSTRAP_ENFORCEMENT_METADATA_MISSING) unless ALL of the following
hold against the target `SESSION_BOOTSTRAP.md` (or its `--bootstrap`
override):
  1. The file exists and is readable.
  2. Its content is non-empty (stripped).
  3. It contains the literal phrase "before any action" (case-insensitive)
     — SESSION_BOOTSTRAP.md's own header declares itself mandatory
     pre-action reading ("Read this first, every session, before any
     action."); this phrase is the concrete, falsifiable stand-in for
     that declaration.
  4. It contains the literal substring "BLOCKED:" (case-sensitive) — this
     project's own established fail-closed directive convention, used
     throughout SESSION_BOOTSTRAP.md's own §5 ("report `BLOCKED:
     SESSION_RESTORE_FAILURE`") and every other validator in this repo;
     its presence is the concrete, falsifiable stand-in for "the file
     carries a fail-closed rule," not just mandatory-reading framing with
     no enforcement teeth.
Both (3) and (4) must hold — either one alone (mandatory-reading framing
with no fail-closed rule, or a fail-closed rule with no mandatory-reading
framing) is insufficient for "enforcement metadata" as the EIP names it.
This is a deliberately shallow, structural check (text presence, not
semantic understanding of the file) — consistent with this project's
existing validators, which are regex/string checks, not NLP — and is
falsifiable: deleting either phrase from a throwaway `SESSION_BOOTSTRAP.md`
copy, or pointing `--bootstrap` at a nonexistent/empty file, must and does
trip this condition.

This tool NEVER modifies, renames, or writes to any of the four governing
baseline artifacts, the real `PROJECT_INDEX.md`, or the real
`SESSION_BOOTSTRAP.md` — read-only against all of them, always. The
`--project-index`/`--bootstrap` arguments exist specifically so this tool
can be pointed at a throwaway fixture copy for negative testing (SCN-025,
SCN-124) without ever touching the real files; both default to the real
paths when omitted.
"""
import argparse
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

DEFAULT_PROJECT_INDEX = ROOT / "knowledge/00-System/PROJECT_INDEX.md"
DEFAULT_BOOTSTRAP = ROOT / "knowledge/00-System/SESSION_BOOTSTRAP.md"

DESIGN_BUNDLE_DIR = "veyro-product-experience-design"

# The four governing baselines, per `PROJECT_INDEX.md`/`SESSION_BOOTSTRAP.md`
# §1. `identity` is the exact EIP-coded identity string both files are
# required to bind; `display` is used only in human-readable messages.
BASELINE_ARTIFACTS = [
    {
        "identity": "VEYRO-MPB-1.0",
        "display": "Master Product Blueprint",
        "kind": "docx",
        "filename": "Gym_OS_Master_Product_Blueprint_v1_English.docx",
    },
    {
        "identity": "Veyro TSD v1.4.1",
        "display": "Technical System Design",
        "kind": "docx",
        "filename": "Veyro_Technical_System_Design_v1.4.1_English_FINAL.docx",
    },
    {
        "identity": "VEYRO-UX-V1-170-APPROVED",
        "display": "Design bundle (170-screen UX baseline)",
        "kind": "bundle",
        "filename": None,
    },
    {
        "identity": "VEYRO-EIP-1.4.1-20260827",
        "display": "Engineering Implementation Plan",
        "kind": "docx",
        "filename": "Veyro_Engineering_Implementation_Plan_v1.4.1_English_FINAL_APPROVED_GOVERNING_BASELINE.docx",
    },
]

_HEX64 = r"[0-9a-f]{64}"
_HASH_CELL_RE = re.compile(rf"^`({_HEX64})`$")
_CANDIDATE_RE = re.compile(r"\b(candidate|unapproved)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Ported verbatim from knowledge/00-System/verify_baselines.py — same
# hashing/manifest procedures, not reinvented. See module docstring for
# why the per-docx *extraction* function is NOT reused (existence/missing/
# ambiguous vs. missing-hash need to be told apart; the manifest-hash
# extraction below IS reused unchanged, since a dedicated unique label
# line has no such ambiguity to resolve).
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_design_bundle(bundle_dir: Path) -> str:
    """Reproduces PROJECT_INDEX.md's documented deterministic manifest
    method exactly: find every tracked file (excluding .DS_Store) sorted
    by path, SHA-256 each, concatenate as "<hash>  <relpath>\\n" lines,
    then SHA-256 the concatenated manifest text itself."""
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


def expected_manifest_hash(index_text: str) -> str | None:
    m = re.search(rf"Manifest hash \(bundle identity\):\*\*\s*`({_HEX64})`", index_text)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# New: row-scoped table parsing (see module docstring for why this is
# scoped to table rows, never a whole-document search).
# ---------------------------------------------------------------------------

def parse_baseline_table_rows(index_text: str) -> list[dict]:
    """Parses PROJECT_INDEX.md's baseline table into discrete rows. Only
    matches lines shaped `| <digit(s)> | ... |` — the table's real data
    rows. The header row (`| # | Artifact | ... |`) and the `|---|...`
    separator row are both excluded by construction (their first cell is
    not a digit), so this never picks up markdown table furniture as a
    baseline entry."""
    rows = []
    for line in index_text.splitlines():
        line = line.strip()
        if not re.match(r"^\|\s*\d+\s*\|", line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 5:
            continue  # malformed/unrelated row shape, not this table
        rows.append({
            "num": cells[0],
            "artifact": cells[1],
            "identity_raw": cells[2],
            "path_raw": cells[3],
            "hash_raw": cells[4],
        })
    return rows


def check_identity_presence_and_ambiguity(rows: list[dict]) -> list[dict]:
    """Condition (b): every one of the 4 expected identity strings must
    appear in exactly one row's identity cell — zero rows means the
    baseline has no PROJECT_INDEX.md row at all (or its identity was
    replaced with something else entirely); more than one row means two
    baselines are sharing one identity string. Both dispositions are the
    same named error per the card's own text."""
    denials = []
    for artifact in BASELINE_ARTIFACTS:
        matches = [r for r in rows if artifact["identity"] in r["identity_raw"]]
        if len(matches) == 0:
            denials.append({
                "code": "MISSING_OR_AMBIGUOUS_ARTIFACT_IDENTITY",
                "artifact": artifact["display"],
                "detail": f"no PROJECT_INDEX.md row found whose identity cell contains '{artifact['identity']}'.",
            })
        elif len(matches) > 1:
            row_nums = [r["num"] for r in matches]
            denials.append({
                "code": "MISSING_OR_AMBIGUOUS_ARTIFACT_IDENTITY",
                "artifact": artifact["display"],
                "detail": f"identity string '{artifact['identity']}' appears in {len(matches)} rows ({row_nums}) — ambiguous.",
            })
    return denials


def check_unapproved_candidate_eip(rows: list[dict]) -> list[dict]:
    """Condition (a): the EIP artifact's row is identified by its
    Artifact-name column (not its identity column — that column is
    exactly what this fixture class may have altered), then its identity
    cell is checked for a literal 'candidate'/'unapproved' flag. The real
    PROJECT_INDEX.md row reads '...(currently promoted governing EIP —
    see contradiction note below)', which contains neither word."""
    denials = []
    eip_rows = [r for r in rows if "engineering implementation plan" in r["artifact"].lower()]
    for r in eip_rows:
        if _CANDIDATE_RE.search(r["identity_raw"]):
            denials.append({
                "code": "UNAPPROVED_CANDIDATE_EIP",
                "artifact": "Engineering Implementation Plan",
                "detail": f"row {r['num']}'s identity cell flags it candidate/unapproved: '{r['identity_raw']}'.",
            })
    return denials


def check_missing_content_hash(rows: list[dict], index_text: str, project_index_path: Path) -> tuple[list[dict], dict, str | None]:
    """Condition (c). Returns (denials, recorded_docx_hashes, recorded_manifest_hash).
    Only fires for an artifact whose row genuinely exists (found via
    `path_raw`, i.e. the filename/bundle-path cell) — an artifact with no
    row at all is already reported by check_identity_presence_and_ambiguity
    and is deliberately not double-reported here."""
    denials = []
    recorded_docx_hashes = {}
    recorded_manifest_hash = None

    for artifact in BASELINE_ARTIFACTS:
        if artifact["kind"] != "docx":
            continue
        filename = artifact["filename"]
        row = next((r for r in rows if f"`{filename}`" in r["path_raw"]), None)
        if row is None:
            continue  # no row — condition (b) already reports this artifact
        m = _HASH_CELL_RE.match(row["hash_raw"])
        if m is None:
            denials.append({
                "code": "MISSING_CONTENT_HASH",
                "artifact": artifact["display"],
                "detail": f"row {row['num']} is present but its hash cell is empty/malformed: '{row['hash_raw']}'.",
            })
        else:
            recorded_docx_hashes[filename] = m.group(1)

    bundle_row = next((r for r in rows if f"`{DESIGN_BUNDLE_DIR}/`" in r["path_raw"]), None)
    if bundle_row is not None:
        manifest_hash = expected_manifest_hash(index_text)
        if manifest_hash is None:
            denials.append({
                "code": "MISSING_CONTENT_HASH",
                "artifact": "Design bundle (170-screen UX baseline)",
                "detail": f"row {bundle_row['num']} is present but no 'Manifest hash (bundle identity):' value was found in {project_index_path.name}.",
            })
        else:
            recorded_manifest_hash = manifest_hash

    return denials, recorded_docx_hashes, recorded_manifest_hash


def check_hash_mismatch(recorded_docx_hashes: dict, recorded_manifest_hash: str | None) -> list[dict]:
    """Condition (e), the original verify_baselines.py mismatch case —
    only attempted for an artifact whose recorded hash was actually
    extracted above (condition (c) already denies the empty/malformed
    case, so there is nothing to compare there)."""
    denials = []

    for artifact in BASELINE_ARTIFACTS:
        if artifact["kind"] != "docx":
            continue
        filename = artifact["filename"]
        expected = recorded_docx_hashes.get(filename)
        if expected is None:
            continue
        path = ROOT / filename
        if not path.exists():
            denials.append({
                "code": "BASELINE_INTEGRITY_FAILURE",
                "artifact": artifact["display"],
                "detail": f"file does not exist at {path}.",
            })
            continue
        actual = sha256_file(path)
        if actual != expected:
            denials.append({
                "code": "BASELINE_INTEGRITY_FAILURE",
                "artifact": artifact["display"],
                "detail": f"HASH MISMATCH — expected {expected}, got {actual}.",
            })

    if recorded_manifest_hash is not None:
        bundle_dir = ROOT / DESIGN_BUNDLE_DIR
        if not bundle_dir.is_dir():
            denials.append({
                "code": "BASELINE_INTEGRITY_FAILURE",
                "artifact": "Design bundle (170-screen UX baseline)",
                "detail": f"directory does not exist at {bundle_dir}.",
            })
        else:
            actual_manifest = sha256_design_bundle(bundle_dir)
            if actual_manifest != recorded_manifest_hash:
                denials.append({
                    "code": "BASELINE_INTEGRITY_FAILURE",
                    "artifact": "Design bundle (170-screen UX baseline)",
                    "detail": f"MANIFEST HASH MISMATCH — expected {recorded_manifest_hash}, got {actual_manifest}.",
                })

    return denials


def check_bootstrap_enforcement_metadata(bootstrap_path: Path) -> list[dict]:
    """Condition (d). See module docstring for the exact, falsifiable
    rule this check applies and its rationale."""
    if not bootstrap_path.exists():
        return [{
            "code": "BOOTSTRAP_ENFORCEMENT_METADATA_MISSING",
            "artifact": "SESSION_BOOTSTRAP.md",
            "detail": f"{bootstrap_path} does not exist.",
        }]

    text = bootstrap_path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        return [{
            "code": "BOOTSTRAP_ENFORCEMENT_METADATA_MISSING",
            "artifact": "SESSION_BOOTSTRAP.md",
            "detail": f"{bootstrap_path} exists but is empty.",
        }]

    has_mandatory_read = "before any action" in text.lower()
    has_fail_closed = "BLOCKED:" in text

    if has_mandatory_read and has_fail_closed:
        return []

    missing = []
    if not has_mandatory_read:
        missing.append("the literal phrase 'before any action' (mandatory-pre-action-reading declaration)")
    if not has_fail_closed:
        missing.append("the literal substring 'BLOCKED:' (fail-closed directive)")
    return [{
        "code": "BOOTSTRAP_ENFORCEMENT_METADATA_MISSING",
        "artifact": "SESSION_BOOTSTRAP.md",
        "detail": f"{bootstrap_path} is missing: {'; '.join(missing)}.",
    }]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="CI-gate baseline-artifact binding schema validator (MOD-001, GOV-01-R04). "
                     "Read-only against the real governing baselines/PROJECT_INDEX.md/SESSION_BOOTSTRAP.md "
                     "always; point --project-index/--bootstrap at a throwaway fixture copy for negative testing."
    )
    p.add_argument(
        "--project-index", type=Path, default=DEFAULT_PROJECT_INDEX,
        help=f"Path to PROJECT_INDEX.md to validate (default: {DEFAULT_PROJECT_INDEX}).",
    )
    p.add_argument(
        "--bootstrap", type=Path, default=DEFAULT_BOOTSTRAP,
        help=f"Path to SESSION_BOOTSTRAP.md to validate (default: {DEFAULT_BOOTSTRAP}).",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    project_index_path: Path = args.project_index
    bootstrap_path: Path = args.bootstrap

    if not project_index_path.exists():
        print(f"BLOCKED: BASELINE_INTEGRITY_FAILURE — {project_index_path} does not exist, cannot locate expected hashes/identities.")
        return 1
    index_text = project_index_path.read_text(encoding="utf-8", errors="replace")

    rows = parse_baseline_table_rows(index_text)

    denials: list[dict] = []
    denials += check_identity_presence_and_ambiguity(rows)
    denials += check_unapproved_candidate_eip(rows)
    hash_denials, recorded_docx_hashes, recorded_manifest_hash = check_missing_content_hash(rows, index_text, project_index_path)
    denials += hash_denials
    denials += check_hash_mismatch(recorded_docx_hashes, recorded_manifest_hash)
    denials += check_bootstrap_enforcement_metadata(bootstrap_path)

    print("=" * 70)
    print("MOD-001 BASELINE-ARTIFACT BINDING SCHEMA VALIDATOR")
    print("=" * 70)
    print(f"\nProject index checked: {project_index_path}")
    print(f"Bootstrap file checked: {bootstrap_path}")
    print(f"\n5 fail-closed conditions checked: BASELINE_INTEGRITY_FAILURE (mismatch), "
          f"UNAPPROVED_CANDIDATE_EIP, MISSING_OR_AMBIGUOUS_ARTIFACT_IDENTITY, "
          f"MISSING_CONTENT_HASH, BOOTSTRAP_ENFORCEMENT_METADATA_MISSING.")

    if denials:
        print(f"\nBLOCKED: {len(denials)} finding(s):")
        for d in denials:
            print(f"  - {d['code']} — {d['artifact']}: {d['detail']}")
        return 1

    print(f"\nPASS — all 4 governing baselines correctly bound (identity present & unambiguous, "
          f"content hash present & matching, EIP not flagged candidate/unapproved) and "
          f"SESSION_BOOTSTRAP.md enforcement metadata present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
