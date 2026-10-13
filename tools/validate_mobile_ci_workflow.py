"""
Static wiring check for .github/workflows/mobile-ci.yml (MOD-001, GOV-01-R07;
SCN-MOD001-052/055/100/101/128). Stdlib only, no YAML parser (matches
validate_workflow_trust.py). Checks wiring only - it never claims a build ran.

    validate_mobile_ci_workflow.py [--root DIR]

Defects (one per line, exit 1):
  TRIGGER_MISSING      pull_request `paths:` filter absent or lacks a required glob
  TRIGGER_STALE        a tracked file under mobile/ matches no path-filter glob (SCN-100)
  JOB_MISSING          a required job id is absent (names the dimension, SCN-128)
  RUNNER_MISASSIGNED   an Android job is not on ubuntu-24.04 (SCN-055/101)
  IOS_RUNNER_COMMITTED an iOS job commits a runner label (must stay variable-driven)
  FORBIDDEN_REFERENCE  macOS runner reference, secrets., uses:, or credential token (SCN-056)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

WORKFLOW = ".github/workflows/mobile-ci.yml"
REQUIRED_GLOBS = ("mobile/**", WORKFLOW, "tools/validate_toolchain_matrix.py", "tools/validate_mobile_ci_workflow.py")
ANDROID_JOBS = ("android-build", "android-regression", "android-ui-qualification",
                "android-accessibility-qualification", "android-performance-qualification")
IOS_JOBS = ("ios-build", "ios-regression", "ios-smoke")
FORBIDDEN = (r"macos", r"\bsecrets\.", r"^\s*-?\s*uses\s*:", r"(?i)(apple|play).{0,20}(credential|account|key)")


def _strip(text: str) -> list[str]:
    return [re.sub(r"(?:^|\s)#.*$", "", l).rstrip() for l in text.splitlines()]


def parse(text: str) -> tuple[list[str], dict[str, str]]:
    """(pull_request path globs, job id -> runs-on value)."""
    lines = _strip(text)
    globs: list[str] = []
    in_on = in_pr = in_paths = False
    for l in lines:
        if re.match(r"^on\s*:", l):
            in_on, in_pr, in_paths = True, False, False
        elif re.match(r"^\S", l):
            in_on = in_pr = in_paths = False
        elif in_on and re.match(r"^  pull_request\s*:", l):
            in_pr, in_paths = True, False
        elif in_on and re.match(r"^  \S", l):
            in_pr = in_paths = False
        elif in_pr and re.match(r"^    paths\s*:", l):
            in_paths = True
        elif in_pr and re.match(r"^    \S", l):
            in_paths = False
        elif in_paths and (m := re.match(r"^\s+-\s+['\"]?([^'\"]+?)['\"]?\s*$", l)):
            globs.append(m.group(1))
    jobs: dict[str, str] = {}
    in_jobs, job = False, None
    for l in lines:
        if re.match(r"^jobs\s*:", l):
            in_jobs = True
        elif re.match(r"^\S", l):
            in_jobs = False
        elif in_jobs and (m := re.match(r"^  ([A-Za-z0-9_-]+)\s*:\s*$", l)):
            job = m.group(1)
            jobs[job] = ""
        elif in_jobs and job and (m := re.match(r"^    runs-on\s*:\s*(.+?)\s*$", l)):
            jobs[job] = m.group(1)
    return globs, jobs


def glob_re(glob: str) -> re.Pattern[str]:
    out, i = "", 0
    while i < len(glob):
        if glob.startswith("**", i):
            out += ".*"
            i += 2
        elif glob[i] == "*":
            out += "[^/]*"
            i += 1
        else:
            out += re.escape(glob[i])
            i += 1
    return re.compile(out + r"\Z")


def triggered_jobs(changed: list[str], globs: list[str], jobs: dict[str, str]) -> list[str]:
    """Jobs the workflow runs for a change set (no per-job filters: all or none)."""
    pats = [glob_re(g) for g in globs]
    return sorted(jobs) if any(p.match(c) for c in changed for p in pats) else []


def tracked_mobile_files(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in (root / "mobile").rglob("*") if p.is_file())


def check(root: Path, files: list[str] | None = None) -> list[str]:
    try:
        text = (root / WORKFLOW).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"TRIGGER_MISSING: unreadable {WORKFLOW} ({type(exc).__name__})"]
    globs, jobs = parse(text)
    defects: list[str] = []
    if not globs:
        defects.append("TRIGGER_MISSING: no pull_request paths filter")
    for g in REQUIRED_GLOBS:
        if globs and g not in globs:
            defects.append(f"TRIGGER_MISSING: paths filter lacks '{g}'")
    for f in (tracked_mobile_files(root) if files is None else files):
        if not any(glob_re(g).match(f) for g in globs):
            defects.append(f"TRIGGER_STALE: {f} matches no path-filter glob")
    for j in ANDROID_JOBS + IOS_JOBS:
        if j not in jobs:
            defects.append(f"JOB_MISSING: {j}")
    for j in ANDROID_JOBS:
        if j in jobs and jobs[j] != "ubuntu-24.04":
            defects.append(f"RUNNER_MISASSIGNED: {j} runs-on={jobs[j]!r}")
    for j in IOS_JOBS:
        if j in jobs and not re.fullmatch(r"\$\{\{\s*vars\.[A-Z0-9_]+\s*\}\}", jobs[j]):
            defects.append(f"IOS_RUNNER_COMMITTED: {j} runs-on={jobs[j]!r}")
    for pat in FORBIDDEN:
        for l in _strip(text):
            if re.search(pat, l, re.IGNORECASE | re.MULTILINE):
                defects.append(f"FORBIDDEN_REFERENCE: {pat!r} in {l.strip()!r}")
    return defects


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    defects = check(ap.parse_args(argv).root)
    for d in defects:
        print(d)
    if not defects:
        print("PASS: mobile-ci wiring is statically consistent (no build executed; not a scenario PASS)")
    return 1 if defects else 0


if __name__ == "__main__":
    sys.exit(main())
