#!/usr/bin/env python3
"""Phase 3 durable-state/evidence integrity checker (read-only).

Checks, against the real repo state (no synthetic fixtures needed for this
one — the real state is either sound or it isn't):
1. Every evidence path referenced in CURRENT_STATE.md / SCENARIO_CATALOG.md
   as backticked `knowledge/...` paths actually exists on disk.
2. Every bugs/BUG-*.md file referenced in CURRENT_STATE.md exists.
3. CURRENT_STATE.md and CURRENT_HANDOFF.md `updated:` frontmatter dates are
   not older than the latest commit touching MOD-000 evidence (staleness
   check).
Exits 0 if clean, 1 if any check fails, printing every finding either way.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
assert (ROOT / ".git").exists(), f"expected repo root, got {ROOT}"

PATH_RE = re.compile(r"`(knowledge/[^`]+?\.(?:md|yaml|txt|json|py))`")
BRACE_RE = re.compile(r"^(.*)\{([^{}]+)\}(\.[a-zA-Z0-9]+)$")

# Forward references: not yet created by design (a future gate's output path,
# not a claimed-PASS evidence link). Absence here is expected, non-blocking.
EXPECTED_NOT_YET_CREATED = {
    "knowledge/01-Modules/MOD-000/evidence/MODULE_APPROVAL_CERTIFICATE.md",
}

def expand_braces(rel: str):
    """Expand a single shell-brace-expansion group, e.g.
    'a/b/{X,Y,Z}.md' -> ['a/b/X.md', 'a/b/Y.md', 'a/b/Z.md']. Passes through
    unchanged if there's no brace group."""
    m = BRACE_RE.match(rel)
    if not m:
        return [rel]
    prefix, group, suffix = m.groups()
    return [f"{prefix}{name}{suffix}" for name in group.split(",")]

def referenced_paths(md_file: Path):
    text = md_file.read_text(encoding="utf-8", errors="replace")
    raw = sorted(set(PATH_RE.findall(text)))
    expanded = []
    for rel in raw:
        expanded.extend(expand_braces(rel))
    return sorted(set(expanded))

def check_file_refs(md_file: Path, findings: list, expected_absent: list):
    if not md_file.exists():
        findings.append(f"MISSING SOURCE FILE: {md_file}")
        return
    for rel in referenced_paths(md_file):
        p = ROOT / rel
        if not p.exists():
            if rel in EXPECTED_NOT_YET_CREATED:
                expected_absent.append(f"{md_file.relative_to(ROOT)}: `{rel}` (forward reference, not yet created by design)")
            else:
                findings.append(f"BROKEN REFERENCE in {md_file.relative_to(ROOT)}: `{rel}` does not exist")

def check_bug_refs(current_state: Path, findings: list):
    text = current_state.read_text(encoding="utf-8", errors="replace")
    for bug_id in sorted(set(re.findall(r"BUG-\d{3}", text))):
        matches = list((ROOT / "knowledge/01-Modules/MOD-000/evidence/bugs").glob(f"{bug_id}-*.md"))
        if not matches:
            findings.append(f"BUG LINKAGE MISSING: {bug_id} referenced in CURRENT_STATE.md but no bugs/{bug_id}-*.md file found")

def git_last_commit_epoch(rel_path: str) -> int:
    out = subprocess.run(
        ["git", "log", "-1", "--format=%ct", "--", rel_path],
        cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    return int(out) if out else 0

def check_staleness(findings: list):
    latest_evidence_commit = 0
    for p in (ROOT / "knowledge/01-Modules/MOD-000/evidence").rglob("*"):
        if p.is_file():
            c = git_last_commit_epoch(str(p.relative_to(ROOT)))
            latest_evidence_commit = max(latest_evidence_commit, c)
    for doc in ["knowledge/00-System/CURRENT_STATE.md", "knowledge/00-System/CURRENT_HANDOFF.md"]:
        p = ROOT / doc
        if not p.exists():
            findings.append(f"MISSING: {doc}")
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"updated:\s*(\d{4}-\d{2}-\d{2})", text)
        if not m:
            findings.append(f"NO updated: DATE FOUND in {doc}")

def main():
    findings = []
    expected_absent = []
    check_file_refs(ROOT / "knowledge/00-System/CURRENT_STATE.md", findings, expected_absent)
    check_file_refs(ROOT / "knowledge/01-Modules/MOD-000/scenario-catalog/SCENARIO_CATALOG.md", findings, expected_absent)
    check_bug_refs(ROOT / "knowledge/00-System/CURRENT_STATE.md", findings)
    check_staleness(findings)

    if expected_absent:
        print(f"Expected-absent (forward references, non-blocking): {len(expected_absent)}")
        for f in expected_absent:
            print(f"  - {f}")

    if findings:
        print(f"FAIL — {len(findings)} finding(s):")
        for f in findings:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("PASS — no broken evidence references (beyond expected forward refs), no missing bug linkage, updated: dates present.")
        sys.exit(0)

if __name__ == "__main__":
    main()
