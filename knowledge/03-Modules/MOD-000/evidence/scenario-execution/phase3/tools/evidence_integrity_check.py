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
2. Every bugs/BUG-*.md file referenced in CURRENT_STATE.md exists in a module evidence tree.
3. CURRENT_STATE.md / CURRENT_HANDOFF.md `updated:` dates are not older
   than the latest commit touching MOD-000 evidence (now an actual
   comparison, not dead code).
Exits 0 if clean, 1 if any check fails, printing every finding either way.
"""
import hashlib
import os
import re
import stat
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True,
    cwd=Path(__file__).resolve().parent,
).stdout.strip())
assert (ROOT / ".git").exists(), f"expected repo root, got {ROOT}"

# OWN-008/ADR-009: the owner removed MOD-001's active evidence tree and
# superseded root documents. Historical citations remain verifiable against
# this immutable pre-reset Git commit; this is NEVER current gate proof.
MOD001_HISTORICAL_COMMIT = "7f3aba9242abb00b7e394e1d1579bbb2e11468e1"

def historical_mod001_blobs():
    result = subprocess.run(
        ["git", "ls-tree", "-r", MOD001_HISTORICAL_COMMIT, "--", "knowledge/03-Modules/MOD-001"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    return {line.split("\t", 1)[1] for line in result.stdout.splitlines()
            if line.startswith(("100644 blob ", "100755 blob ")) and "\t" in line}

HISTORICAL_MOD001_BLOBS = historical_mod001_blobs()

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
    # The owner settings-activation patch: deliberately not authored until
    # a Bash-guard review round returns P0=0/P1=0 (writing it earlier would
    # imply a readiness the guard hasn't earned) — referenced in
    # CURRENT_HANDOFF.md as the next step once that happens, per the
    # BASH_GUARD_V2_ROUND3_REVIEW_2026-09-07.md gate outcome.
    "knowledge/03-Modules/MOD-000/evidence/security/BUG-013-022-023-OWNER-SETTINGS-PATCH.md",
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

# Historical archive binding (GOV-01-R01, 2026-10-13). The 14 legacy
# MOD-001 root Markdown documents were deleted from the module root (MOD-001.md
# is the only active module-root operational Markdown). Raw historical
# citations of those exact root paths stay valid ONLY while a byte-identical
# archive copy exists at HISTORICAL_ARCHIVE_DIR, pinned by SHA-256 of the
# original HEAD blob. Fail-closed: the archive copy must be a regular,
# non-symlink file (no symlinked ancestor directory) whose content matches the
# pin. No other missing path is treated as historical. The archive confers no
# current authority or certification credit.
LEGACY_ROOT_DIR = "knowledge/03-Modules/MOD-001"
HISTORICAL_ARCHIVE_DIR = "knowledge/03-Modules/MOD-001/evidence/historical-superseded-root-md"
LEGACY_ROOT_SHA256 = {
    "ADR_CONFORMANCE.md": "0d41da483df0718a54de9659ec4e15469bae8fafc5e5c69816f47e654c93794f",
    "CAPABILITIES.md": "9a7a4a9cdfe9ac6bcf6f7f95afcf378836c1163ef4643d73261550707362d4f5",
    "CODE_REVIEW.md": "b029ea8b2e7a811e1dd97df313733c491d7acf76056908c1ac0102a9e22d27ed",
    "IMPLEMENTATION.md": "4a954234a402a0cc16863e4c8d9010d637fbb3e836ecc736e19f2f5702c02b31",
    "LOAD_SECURITY.md": "010e26327f29b617be7c8d0d2b9172e30295a57cfbbea07939b6b0e5b5e8df60",
    "MANUAL_QA.md": "0b83394f31dc7ca6ef26d784191f8cd0dc91aa9430811bd7ed89d8465eab373c",
    "MODEL_ROUTE.md": "8572e437a41dac256d354a013642ba5130d44c2f50ab970a47c4edd0c5ee73d6",
    "REQUIREMENTS.md": "08c835aae2c3b632ec64dba1177c342afbd110a1b470919b5cd93ebdd9e967e0",
    "RUNBOOK.md": "8d2593f9d1cc1056057255de17e76caf93f175b952ed4fcac31806809581a213",
    "SCENARIOS.md": "9391ee69fe0f6318c1bcc74238fd4f15d35b43c360d52e15f7e11f85c01ebb49",
    "STATUS.md": "9cf2626d736a9933f9cbf2403a506c5874979a3dc9cb9bab66848f74052f707a",
    "TESTSPRITE.md": "bd97814801d0d9f3a0cc041d09006e67c2a46010bad17e7f6c8a80c52aa5a9db",
    "TEST_PLAN.md": "bc2ea9ffadddf0019565a0c9dedefc8cc16d4671f219cae4bf0e26c0e6cd71d3",
    "TEST_RESULTS.md": "158efeae9949ad1d9363bc222b3f00bc8b47b52d60e11e70ac996fe210b70542",
}

def legacy_root_name(rel: str):
    """Basename if rel is exactly one of the 14 deleted legacy root paths."""
    prefix = LEGACY_ROOT_DIR + "/"
    if rel.startswith(prefix) and rel[len(prefix):] in LEGACY_ROOT_SHA256:
        return rel[len(prefix):]
    return None

def historical_archive_problem(name: str):
    """None if the archive copy of `name` is a genuine regular non-symlink
    file matching its pinned SHA-256; otherwise a reason string."""
    rel = f"{HISTORICAL_ARCHIVE_DIR}/{name}"
    cur = ROOT
    for part in rel.split("/")[:-1]:
        cur = cur / part
        if cur.is_symlink():
            return f"archive path component is a symlink: {cur.relative_to(ROOT)}"
    path = ROOT / rel
    # O_NONBLOCK: opening a substituted FIFO read-only must not block waiting
    # for a writer; the S_ISREG check below then rejects it.
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return "archive copy is missing"
    except OSError as e:
        return f"archive copy cannot be opened without following symlinks ({e.__class__.__name__})"
    try:
        # fstat before building a file object: os.fdopen on a directory fd
        # raises IsADirectoryError and would crash the whole checker.
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return "archive copy is not a regular file"
        with os.fdopen(fd, "rb") as fh:
            fd = None  # ownership transferred to fh
            digest = hashlib.sha256(fh.read()).hexdigest()
    finally:
        if fd is not None:
            os.close(fd)
    if digest != LEGACY_ROOT_SHA256[name]:
        return f"archive copy sha256 {digest} != pinned {LEGACY_ROOT_SHA256[name]}"
    return None

# Abbreviated historical citations (GOV-01-R01, 2026-10-13). The immutable
# SCN070-ROUND5-ROOTCAUSE-IMPLEMENTATION historical file cites exactly three
# evidence files with an elided `knowledge/.../` prefix. Exactly these three
# (citing file, abbreviated reference) pairs map to a declared full target; the
# target must be a genuine regular non-symlink file. This is not a generic
# `knowledge/...` exemption: any other abbreviated name, or a missing/symlinked
# target, is still a BROKEN REFERENCE.
ABBREV_SOURCE = "knowledge/03-Modules/MOD-001/evidence/implementation/SCN070-ROUND5-ROOTCAUSE-IMPLEMENTATION-2026-10-05.md"
ABBREV_TARGET_DIR = "knowledge/03-Modules/MOD-001/evidence/implementation"
ABBREVIATED_HISTORICAL_REFS = {
    (ABBREV_SOURCE, f"knowledge/.../{name}"): f"{ABBREV_TARGET_DIR}/{name}"
    for name in (
        "SCN070-R5-1-ASYMMETRIC-INJECTION-DRILL-2026-10-05.txt",
        "SCN070-ROUND3-REMEDIATION-2026-10-04.md",
        "scn070_ordering_lint_mutation_killcheck.py",
    )
}

def regular_file_problem(rel: str):
    """None if `rel` is a genuine regular file reached without any symlink
    (including ancestor directories); otherwise a reason string."""
    cur = ROOT
    for part in rel.split("/")[:-1]:
        cur = cur / part
        if cur.is_symlink():
            return f"path component is a symlink: {cur.relative_to(ROOT)}"
    try:
        fd = os.open(ROOT / rel, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return "target is missing"
    except OSError as e:
        return f"target cannot be opened without following symlinks ({e.__class__.__name__})"
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return "target is not a regular file"
    finally:
        os.close(fd)
    return None

def expand_braces(rel: str):
    m = BRACE_RE.match(rel)
    if not m:
        return [rel]
    prefix, group, suffix = m.groups()
    return [f"{prefix}{name}{suffix}" for name in group.split(",")]

def referenced_paths(text: str):
    raw = sorted(set(PATH_RE.findall(text)))
    raw = [r for r in raw if "*" not in r and "?" not in r and "|" not in r]  # glob patterns and "a|b|c" shorthand aren't literal paths to check
    raw = [r for r in raw if not any(token in r for token in ("MOD-xxx", "MOD-XXX", "<MOD>", "<active MOD>"))]  # illustrative module placeholders, never literal paths
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
    if rel_path.startswith(HISTORICAL_ARCHIVE_DIR + "/") and rel_path[len(HISTORICAL_ARCHIVE_DIR) + 1:] in LEGACY_ROOT_SHA256:
        # Pinned immutable historical copy: its own raw citations are not
        # re-resolved, but only while its identity verifies (else a finding).
        problem = historical_archive_problem(rel_path.rsplit("/", 1)[-1])
        if problem:
            findings.append(f"HISTORICAL ARCHIVE INVALID: {rel_path}: {problem}")
        return
    text = md_file.read_text(encoding="utf-8", errors="replace")
    for rel in referenced_paths(text):
        if "RULE-<NNN>" in rel:
            # Generic per-rule-file placeholder token used in prose (e.g.
            # "see knowledge/05-QA/capability-evidence/RULE-<NNN>/...") to
            # mean "each RULE-NNN's own evidence file", never a literal path.
            expected_absent.append(f"{rel_path}: `{rel}` (RULE-<NNN> is a generic placeholder token, not a literal path)")
            continue
        p = ROOT / rel
        if not p.exists():
            if rel.startswith(".claude/rules/") and rel.count("/") == 2:
                # Rules were reorganized into admin/backend/global/infra/
                # subdirectories (ADR-005 surface-profile work); many docs
                # still cite the bare pre-reorg filename. Resolve by
                # basename anywhere under .claude/rules/ before calling it
                # broken, same fix already applied to check_bug_refs below
                # for the analogous MOD-000-hardcoded bugs/ path.
                basename = rel.rsplit("/", 1)[-1]
                matches = list((ROOT / ".claude/rules").glob(f"*/{basename}"))
                if len(matches) == 1:
                    continue
            if is_adr and any(rel.startswith(prefix) for prefix in PRE_MIGRATION_PATH_PREFIXES):
                expected_absent.append(f"{rel_path}: `{rel}` (historical pre-migration path, ADR narrative, not a current-state claim)")
            elif rel in HISTORICAL_MOD001_BLOBS:
                expected_absent.append(f"{rel_path}: `{rel}` (verified pre-reset Git historical citation at {MOD001_HISTORICAL_COMMIT}; no current gate authority)")
            elif legacy_root_name(rel):
                name = legacy_root_name(rel)
                problem = historical_archive_problem(name)
                if problem:
                    findings.append(
                        f"BROKEN HISTORICAL REFERENCE in {rel_path}: `{rel}` is a deleted legacy root document "
                        f"and its pinned archive `{HISTORICAL_ARCHIVE_DIR}/{name}` is invalid: {problem}"
                    )
                else:
                    expected_absent.append(f"{rel_path}: `{rel}` (deleted legacy root doc; verified pinned historical archive copy, no current authority)")
            elif (rel_path, rel) in ABBREVIATED_HISTORICAL_REFS:
                target = ABBREVIATED_HISTORICAL_REFS[(rel_path, rel)]
                problem = regular_file_problem(target)
                if problem:
                    findings.append(
                        f"BROKEN HISTORICAL REFERENCE in {rel_path}: `{rel}` is an abbreviated citation "
                        f"declared to resolve to `{target}`, which is invalid: {problem}"
                    )
                else:
                    expected_absent.append(f"{rel_path}: `{rel}` (abbreviated historical citation; verified declared full target `{target}`)")
            elif rel in EXPECTED_NOT_YET_CREATED:
                expected_absent.append(f"{rel_path}: `{rel}` (forward reference, not yet created by design)")
            elif rel in EXPECTED_LOCAL_ONLY:
                expected_absent.append(f"{rel_path}: `{rel}` (intentionally local-only/gitignored, correct to be absent in any clone)")
            else:
                findings.append(f"BROKEN REFERENCE in {rel_path}: `{rel}` does not exist")

def check_bug_refs(findings: list):
    text = (ROOT / "knowledge/00-System/CURRENT_STATE.md").read_text(encoding="utf-8", errors="replace")
    registry = (ROOT / "knowledge/05-QA/BUG_REGISTRY.md").read_text(encoding="utf-8", errors="replace")
    for bug_id in sorted(set(re.findall(r"BUG-\d{3}", text))):
        if not re.search(rf"(?<![\w-]){re.escape(bug_id)}(?![\w-])", registry):
            findings.append(f"BUG LINKAGE MISSING: {bug_id} referenced in CURRENT_STATE.md but absent from BUG_REGISTRY.md")

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

def discover_module_evidence_roots() -> list:
    """Historical MOD-000 evidence plus current lean module documents.
    A fresh MOD-001.md commit must not be invisible to the staleness check."""
    roots = [
        str(p.relative_to(ROOT))
        for p in (ROOT / "knowledge/03-Modules").glob("MOD-*/evidence")
        if p.is_dir()
    ]
    roots.extend(str(p.relative_to(ROOT)) for p in (ROOT / "knowledge/03-Modules").glob("MOD-*/MOD-*.md") if p.is_file())
    return sorted(roots)

def latest_date_across_roots(evidence_roots: list) -> str:
    latest_evidence_date = "0000-00-00"
    for evidence_rel in evidence_roots:
        latest_by_path = latest_commit_dates_under(evidence_rel)
        root_path = ROOT / evidence_rel
        for p in ([root_path] if root_path.is_file() else root_path.rglob("*")):
            if p.is_file():
                d = latest_by_path.get(str(p.relative_to(ROOT)))
                if d and d > latest_evidence_date:
                    latest_evidence_date = d
    return latest_evidence_date

def check_staleness(findings: list):
    latest_evidence_date = latest_date_across_roots(discover_module_evidence_roots())
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
                f"but tracked module evidence (all MOD-*/evidence trees) has a later commit dated {latest_evidence_date} — "
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
