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
    backend/.venv/bin/python knowledge/05-QA/tools/run_regression.py
"""
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import capability_drift_check as cdc  # reuses its RETIRED-marker parser, not a copy

CHECKS = [
    ("verify_baselines.py",
     [sys.executable, str(REPO_ROOT / "knowledge/00-System/verify_baselines.py")]),
    ("validate_catalog.py",
     [sys.executable, str(REPO_ROOT / "knowledge/03-Modules/MOD-000/scenario-catalog/tools/validate_catalog.py")]),
    ("validate_capabilities.py",
     [sys.executable, str(REPO_ROOT / "knowledge/00-System/validate_capabilities.py")]),
    ("evidence_integrity_check.py",
     [sys.executable, str(REPO_ROOT / "knowledge/03-Modules/MOD-000/evidence/scenario-execution/phase3/tools/evidence_integrity_check.py")]),
    # Added 2026-10-04 (SCN-MOD001-070 round-1 review, R1-5): the GOV-01-R06
    # migration-ordering lint was invoked by no automated gate at all -- every
    # "validate_migration_ordering.py PASS" in the vault was hand-run, so a
    # regression in it (e.g. the exit-code fail-open mutant M5) would have been
    # caught by nothing. Both entries are registered, deliberately:
    #   * the lint itself, so the gate exists today -- though note it is
    #     currently VACUOUS (backend/migrations/records/ holds only .gitkeep, and
    #     the lint now prints a grep-able "NOTICE: ... vacuous pass" saying so).
    #     --require-dir is NOT passed yet: the path does exist, and requiring
    #     records to exist would fail the repo today for a legitimate reason
    #     (R06's own OUT-of-scope line -- no product schema). CI wiring and
    #     --require-dir remain an explicit GOV-01-R04 obligation.
    #   * its unit suite, which is the genuinely load-bearing half while the
    #     records dir is empty: it is what kills the M3 start-phase-guard and M5
    #     exit-code mutants (see
    #     MOD-001/evidence/implementation/scn070_ordering_lint_mutation_killcheck.py).
    ("validate_migration_ordering.py",
     [sys.executable, str(REPO_ROOT / "tools/validate_migration_ordering.py")]),
    ("test_validate_migration_ordering.py",
     [sys.executable, str(REPO_ROOT / "tools/tests/test_validate_migration_ordering.py")]),
    ("test_bash_guard.py",
     [sys.executable, str(REPO_ROOT / ".claude/security/tests/test_bash_guard.py")]),
]

# Added 2026-10-01 (BUG-044): test_bash_guard.py exercises CAP-007's
# PreToolUse enforcement, which OWN-006/ADR-007 retired 2026-09-28
# (bash_guard.py replaced with an inert allow-stub, commit 058ed27). The
# suite now correctly, permanently fails 149/194 -- it is testing
# behavior that was deliberately removed, not a real regression. Treating
# that as a current gate failure is itself wrong: it would either block
# every future regression run forever for a known, owner-authorized
# reason, or train sessions to ignore this harness's FAIL verdicts
# entirely. This name is read from the *live* registry on every run
# (via cdc.resolve_capability_lifecycle), not hardcoded -- if CAP-007 is
# ever reinstated (a later-dated REINSTATED/ACTIVE marker, corroborated
# by the registry's own `lifecycle_status` field), this check
# automatically resumes running and gating normally again, with no code
# change required here. An *unresolved* lifecycle claim (same-date
# conflict, or an unbacked/disagreeing marker -- see BUG-045) must never
# be trusted to mean "retired"; it is printed as a registry-integrity failure and the suite
# keeps running/gating normally; the aggregate fails closed even if all
# individual checks happen to pass.
# ROLLBACK: if CAP-007 is reinstated, all 194 tests in
# .claude/security/tests/test_bash_guard.py must pass again before this
# harness may report the suite as a live regression gate.
RETIRED_SUITE_FOR_CAPABILITY = {"test_bash_guard.py": "CAP-007"}


def retired_capability_ids(conflicts_out: list | None = None) -> set:
    """Returns the set of capability IDs whose lifecycle state resolves,
    fail-closed, to RETIRED. Any lifecycle conflict is appended to
    conflicts_out (if given) rather than silently affecting the result --
    an unresolved capability is never included in the returned set, so it
    is never treated as retired."""
    text = cdc.REGISTRY.read_text(encoding="utf-8", errors="replace")
    resolved, conflicts = cdc.resolve_capability_lifecycle(text)
    if conflicts_out is not None:
        conflicts_out.extend(conflicts)
    return {cid for cid, bucket in resolved.items() if bucket == "RETIRED"}


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


def run_all(checks, retired_ids):
    """ok is True/False for a real pass/fail, or None for a check that was
    excluded because its underlying capability is RETIRED -- None is never
    counted toward all_pass or the X/Y passed tally."""
    results = []
    for name, cmd in checks:
        gating_capability = RETIRED_SUITE_FOR_CAPABILITY.get(name)
        if gating_capability and gating_capability in retired_ids:
            results.append((
                name, None,
                f"RETIRED/NOT_APPLICABLE — {gating_capability} retired (OWN-006/ADR-007); "
                f"not executed as a current gate; must be restored if {gating_capability} is reinstated",
            ))
            continue
        results.append(run_one(name, cmd))
    return results


def main():
    lifecycle_conflicts: list = []
    results = run_all(CHECKS, retired_capability_ids(lifecycle_conflicts))
    scored = [(name, ok, summary) for name, ok, summary in results if ok is not None]
    all_pass = not lifecycle_conflicts and all(ok for _, ok, _ in scored)

    lines = []
    lines.append(f"MOD-000 regression run: {datetime.now(timezone.utc).isoformat()}")
    lines.append("=" * 70)
    if lifecycle_conflicts:
        lines.append("LIFECYCLE CONFLICTS (aggregate FAIL; no capability below was treated as retired on an unresolved claim):")
        for c in lifecycle_conflicts:
            lines.append(f"  [!] {c}")
        lines.append("=" * 70)
    for name, ok, summary in results:
        status = "N/A" if ok is None else ("PASS" if ok else "FAIL")
        lines.append(f"[{status}] {name}: {summary}")
    lines.append("=" * 70)
    lines.append(f"AGGREGATE RESULT: {'PASS' if all_pass else 'FAIL'} ({sum(1 for _, ok, _ in scored if ok)}/{len(scored)} checks passed{', ' + str(len(results) - len(scored)) + ' N/A excluded' if len(results) != len(scored) else ''})")

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
