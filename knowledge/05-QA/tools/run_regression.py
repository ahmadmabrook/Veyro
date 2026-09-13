#!/usr/bin/env python3
"""Permanent regression harness for MOD-000's control-plane checks.

Authored 2026-09-13, Phase 10 readiness (SCN-MOD000-091 -- "Permanent-
regression automation harness exists"). Wraps the 5 checks this project
has run by hand after every material change since Phase 1 into one
command with one aggregate pass/fail result and a durable, timestamped
pass record.

Honest scope note: this is a local aggregator, not a CI-wired pipeline
(no CI infrastructure exists on this project and standing one up is out
of MOD-000's control-plane-bootstrap scope). It re-runs the same 5
checks a human or CI job would run, and is runnable directly today by
the owner or by a human terminal session outside Claude Code's own
Bash-guard-gated tool calls. It is not yet on `bash_guard.py`'s trusted-
script allowlist (`.claude/security/**` is Edit/Write-denied to
non-owner sessions, and adding a new trusted script there requires an
owner-authorized edit plus an independent security re-review, per this
project's own established discipline for that specific file) -- so a
Claude Code agent session cannot invoke this script directly through
its own governed Bash tool today. This is a disclosed activation gap,
not a claim that the harness itself does not work.

Usage:
    python3 knowledge/05-QA/tools/run_regression.py
"""
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

CHECKS = [
    ("verify_baselines.py",
     ["python3", str(REPO_ROOT / "knowledge/00-System/verify_baselines.py")]),
    ("validate_catalog.py",
     ["python3", str(REPO_ROOT / "knowledge/03-Modules/MOD-000/scenario-catalog/tools/validate_catalog.py")]),
    ("validate_capabilities.py",
     ["python3", str(REPO_ROOT / "knowledge/00-System/validate_capabilities.py")]),
    ("evidence_integrity_check.py",
     ["python3", str(REPO_ROOT / "knowledge/03-Modules/MOD-000/evidence/scenario-execution/phase3/tools/evidence_integrity_check.py")]),
    ("test_bash_guard.py",
     ["python3", str(REPO_ROOT / ".claude/security/tests/test_bash_guard.py")]),
]


def run_one(name, cmd):
    try:
        result = subprocess.run(
            cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=120
        )
    except subprocess.TimeoutExpired:
        return name, False, "TIMEOUT after 120s"
    except OSError as exc:
        return name, False, f"failed to launch: {exc}"
    ok = result.returncode == 0
    # verify_baselines.py / validate_catalog.py / validate_capabilities.py /
    # evidence_integrity_check.py print "PASS" and exit 0 on success;
    # test_bash_guard.py (unittest) prints "OK" on stderr and exits 0.
    tail = (result.stdout + result.stderr).strip().splitlines()
    summary = tail[-1] if tail else "(no output)"
    return name, ok, summary


def main():
    results = [run_one(name, cmd) for name, cmd in CHECKS]
    all_pass = all(ok for _, ok, _ in results)

    lines = []
    lines.append(f"MOD-000 regression run: {datetime.now(timezone.utc).isoformat()}")
    lines.append("=" * 70)
    for name, ok, summary in results:
        status = "PASS" if ok else "FAIL"
        lines.append(f"[{status}] {name}: {summary}")
    lines.append("=" * 70)
    lines.append(f"AGGREGATE RESULT: {'PASS' if all_pass else 'FAIL'} ({sum(1 for _, ok, _ in results if ok)}/{len(results)} checks passed)")

    output = "\n".join(lines)
    print(output)

    record_dir = REPO_ROOT / "knowledge/05-QA/tools/regression-runs"
    record_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    record_path = record_dir / f"RUN_{stamp}.txt"
    record_path.write_text(output + "\n")
    print(f"\nRecord written: {record_path.relative_to(REPO_ROOT)}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
