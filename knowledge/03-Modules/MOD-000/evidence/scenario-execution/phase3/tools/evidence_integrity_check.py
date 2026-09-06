#!/usr/bin/env python3
"""Durable-state/evidence integrity checker (read-only).

Rewritten 2026-09-04 (Phase 5 remediation, finding F5-020) — the original
version's staleness check computed the latest evidence-commit timestamp
but never actually compared it to anything (dead code, could never fail),
and its path-reference scan covered only 2 of the ~10 durable "brain"
files, which is exactly why a dangling `knowledge/04-Decisions/` reference
in SESSION_BOOTSTRAP.md survived three prior phases undetected.

Checks, against the real repo state:
1. Every evidence/config path referenced (backticked `knowledge/...` or
   `.claude/...` paths) across all durable "brain" files actually exists
   on disk.
2. Every bugs/BUG-*.md file referenced in CURRENT_STATE.md exists.
3. CURRENT_STATE.md / CURRENT_HANDOFF.md `updated:` dates are not older
   than the latest commit touching MOD-000 evidence (now an actual
   comparison, not dead code).
Exits 0 if clean, 1 if any check fails, printing every finding either way.
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

PATH_RE = re.compile(r"`((?:knowledge|\.claude)/[^`\n]+?\.(?:md|yaml|yml|txt|json|py))`")
BRACE_RE = re.compile(r"^(.*)\{([^{}]+)\}(\.[a-zA-Z0-9]+)$")
# Investigated 2026-09-05 (final Phase 5 re-review, NF-3): this checker has a
# known blind spot -- SCENARIO_CATALOG.md's own prose convention writes many
# evidence pointers as a bare `evidence/...` shorthand (meaning "relative to
# some evidence root"), which PATH_RE never matches at all (it requires a
# `knowledge/` or `.claude/` prefix). This is exactly how 3 wrong evidence
# paths in the D-1 matrix went undetected -- those 3 have been fixed directly
# (see SCENARIO_CATALOG.md's D-1 table). A naive fix (resolve every bare
# `evidence/...` against knowledge/03-Modules/MOD-000/) was attempted and
# reverted: the bare-path convention actually resolves against at least 3
# different roots depending on context (MOD-000/evidence/, MOD-000/scenario-
# catalog/evidence/, and knowledge/05-QA/capability-evidence/ post-BUG-017-
# migration), so a single-prefix resolution produced ~20 false positives
# rather than closing the gap. A real fix needs per-context resolution rules,
# not a single prefix -- left as an honest, documented residual limitation
# rather than landing a noisier, less-trustworthy checker.

# Rewritten 2026-09-05 (vault migration, BUG-017): scan EVERY markdown/yaml
# file under knowledge/ and .claude/ plus root CLAUDE.md, rather than a
# curated list — a hardcoded list is exactly how the old 04-Decisions
# reference in SESSION_BOOTSTRAP.md survived undetected for three phases.
def discover_scanned_files():
    files = ["CLAUDE.md"]
    for base in ("knowledge", ".claude"):
        for p in (ROOT / base).rglob("*"):
            if p.is_file() and p.suffix in (".md", ".yaml", ".yml"):
                files.append(str(p.relative_to(ROOT)))
    return sorted(set(files))

SCANNED_FILES = discover_scanned_files()

# Intentionally local-only, gitignored-by-design config — NOT a forward
# reference (it will never be created by durable tooling; it's correct
# for it to be absent from any clone). Added 2026-09-06 (Phase 7,
# SEC-12/RES-01): both an independent security review and an independent
# performance/resilience review found this checker PASSES in the working
# copy but FAILS with 6 findings in a fresh clone of the same commit,
# because `.claude/settings.local.json` (gitignored per `.gitignore`,
# confirmed untracked via `git ls-files`) is referenced by path from 6
# durable evidence files. A real disaster-recovery session that clones
# and runs this checker got a false BLOCKED on a correctly-local-only
# artifact. Kept as a distinct set from EXPECTED_NOT_YET_CREATED because
# the semantics differ: those paths will exist once created; this path
# is correct to never exist in a clone.
EXPECTED_LOCAL_ONLY = {
    ".claude/settings.local.json",
}

# Forward references: not yet created by design (a future gate's output path,
# not a claimed-PASS evidence link). Absence here is expected, non-blocking.
EXPECTED_NOT_YET_CREATED = {
    "knowledge/03-Modules/MOD-000/APPROVAL.md",
    # Described in prose as a hypothetical/proposed throwaway test file
    # (SCN-020's canary-rule test idea), not a claim that it currently exists.
    ".claude/rules/canary.md",
    # A deliberately-fake path used as illustrative text in the Phase 3
    # Notion-drift negative-test writeup — never was, never will be real.
    "knowledge/WRONG/PATH/does-not-match-durable-record.md",
    # Named as the future evidence path for scenarios not yet executed
    # (SCN-067, SCN-068) — forward references to drills not yet run.
    "knowledge/05-QA/capability-evidence/CREDENTIAL_EXPOSURE_SCAN.md",
    "knowledge/05-QA/capability-evidence/RESOLUTION_BOUND_DRILL.md",
    "knowledge/05-QA/capability-evidence/AUTHENTICATION_FAILURE_DRILL.md",
}

# Pre-2026-09-05-migration vault paths, narrated in ADR-001/ADR-002 as
# historical/removed structure — not a current-state claim when quoted
# inside an ADR. Added 2026-09-05 (N-11) to narrow the old blanket
# ADR-file exemption.
PRE_MIGRATION_PATH_PREFIXES = (
    "knowledge/01-Modules/",
    "knowledge/02-Decisions/",
    "knowledge/03-ExternalGates/",
    "knowledge/04-Capabilities/",
)

def expand_braces(rel: str):
    m = BRACE_RE.match(rel)
    if not m:
        return [rel]
    prefix, group, suffix = m.groups()
    return [f"{prefix}{name}{suffix}" for name in group.split(",")]

def referenced_paths(text: str):
    raw = sorted(set(PATH_RE.findall(text)))
    raw = [r for r in raw if "*" not in r and "?" not in r and "|" not in r]  # glob patterns and "a|b|c" shorthand aren't literal paths to check
    raw = [r for r in raw if "MOD-xxx" not in r]  # illustrative placeholder module ID (ADR-001's Appendix D schema example), never a real path
    expanded = []
    for rel in raw:
        expanded.extend(expand_braces(rel))
    return sorted(set(expanded))

def check_file_refs(rel_path: str, findings: list, expected_absent: list):
    md_file = ROOT / rel_path
    if not md_file.exists():
        findings.append(f"MISSING SOURCE FILE: {rel_path}")
        return
    # ADRs narrate historical/decision context, including paths that
    # deliberately no longer exist (that's the point of documenting a
    # migration). Narrowed 2026-09-05 (second Phase 5 re-review, N-11):
    # this used to skip ADR files entirely, which meant ADR-002's own
    # migration path map -- key BUG-017 evidence, and unlike ADR-001 not
    # purely historical -- was never validated. Now only path references
    # starting with a known pre-migration prefix are exempted inside an
    # ADR; every other referenced path in an ADR (including ADR-002's
    # "new path" column) must actually exist, same as any other file.
    is_adr = bool(re.match(r"^knowledge/04-Decisions/ADR-\d+", rel_path))
    text = md_file.read_text(encoding="utf-8", errors="replace")
    for rel in referenced_paths(text):
        p = ROOT / rel
        if not p.exists():
            if is_adr and any(rel.startswith(prefix) for prefix in PRE_MIGRATION_PATH_PREFIXES):
                expected_absent.append(f"{rel_path}: `{rel}` (historical pre-migration path, ADR narrative, not a current-state claim)")
            elif rel in EXPECTED_NOT_YET_CREATED:
                expected_absent.append(f"{rel_path}: `{rel}` (forward reference, not yet created by design)")
            elif rel in EXPECTED_LOCAL_ONLY:
                expected_absent.append(f"{rel_path}: `{rel}` (intentionally local-only/gitignored, correct to be absent in any clone)")
            else:
                findings.append(f"BROKEN REFERENCE in {rel_path}: `{rel}` does not exist")

def check_bug_refs(findings: list):
    text = (ROOT / "knowledge/00-System/CURRENT_STATE.md").read_text(encoding="utf-8", errors="replace")
    for bug_id in sorted(set(re.findall(r"BUG-\d{3}", text))):
        matches = list((ROOT / "knowledge/03-Modules/MOD-000/evidence/bugs").glob(f"{bug_id}-*.md"))
        if not matches:
            findings.append(f"BUG LINKAGE MISSING: {bug_id} referenced in CURRENT_STATE.md but no bugs/{bug_id}-*.md file found")

def latest_commit_dates_under(rel_dir: str) -> dict:
    """Latest commit date per tracked file under rel_dir, via ONE bulk
    `git log` call rather than one subprocess per file.

    Rewritten 2026-09-06 (Phase 7, PERF-01): an independent performance
    review measured the original per-file `git log -1 -- <path>` loop at
    93% of this checker's total runtime (1.17s of 1.26s for 68 files,
    17.2ms/file, confirmed linear but with heavy per-call subprocess
    overhead — sys time dominated). A single `git log --name-only`
    pass over the same scope returns equivalent information in ~0.03s
    (measured ~40x cheaper) by walking history once and recording, for
    each path, the date of the first (newest, since git log is
    newest-first) commit that touched it.
    """
    proc = subprocess.run(
        ["git", "log", "--format=COMMIT:%cs", "--name-only", "--", rel_dir],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    latest_by_path: dict = {}
    current_date = None
    for line in proc.stdout.splitlines():
        if line.startswith("COMMIT:"):
            current_date = line[len("COMMIT:"):]
            continue
        line = line.strip()
        if not line or current_date is None:
            continue
        if line not in latest_by_path:  # first time seen = newest, since log is newest-first
            latest_by_path[line] = current_date
    return latest_by_path

def check_staleness(findings: list):
    latest_evidence_date = "0000-00-00"
    evidence_rel = "knowledge/03-Modules/MOD-000/evidence"
    latest_by_path = latest_commit_dates_under(evidence_rel)
    for p in (ROOT / evidence_rel).rglob("*"):
        if p.is_file():
            d = latest_by_path.get(str(p.relative_to(ROOT)))
            if d and d > latest_evidence_date:
                latest_evidence_date = d
    for doc in ["knowledge/00-System/CURRENT_STATE.md", "knowledge/00-System/CURRENT_HANDOFF.md"]:
        p = ROOT / doc
        if not p.exists():
            findings.append(f"MISSING: {doc}")
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"updated:\s*(\d{4}-\d{2}-\d{2})", text)
        if not m:
            findings.append(f"NO updated: DATE FOUND in {doc}")
            continue
        doc_date = m.group(1)
        # A doc's own commit may postdate its "updated:" text if the commit itself
        # is what set that date (same-day is fine) — only flag a REAL staleness gap:
        # evidence committed strictly after the doc's last real commit, on a later date.
        doc_commit_out = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", doc],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
        doc_commit_date = doc_commit_out or doc_date
        if latest_evidence_date > doc_commit_date:
            findings.append(
                f"STALE: {doc} last committed {doc_commit_date} (updated: field says {doc_date}), "
                f"but MOD-000 evidence has a later commit dated {latest_evidence_date} — "
                f"{doc} may not reflect the most recent evidence."
            )

def main():
    findings = []
    expected_absent = []
    for rel_path in SCANNED_FILES:
        check_file_refs(rel_path, findings, expected_absent)
    check_bug_refs(findings)
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
        print(f"PASS — no broken evidence references (beyond expected forward refs) across {len(SCANNED_FILES)} scanned files, no missing bug linkage, staleness check compared real dates.")
        sys.exit(0)

if __name__ == "__main__":
    main()
