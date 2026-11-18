#!/usr/bin/env python3
"""Break one decision at a time and check that `test_access_domain` notices.

**A test that still passes when you remove the thing it guards is not evidence.** That is the
rule `.claude/rules/backend/mod004-rls.md` states for the schema, and there is no reason the
Python half should be held to a weaker one -- a 52-test suite that went green on its first run
is exactly when to ask whether it is testing anything.

Each mutation edits one source line, runs the suite, and expects a FAILURE. A mutation whose
suite still passes is reported as a gap, and one whose anchor did not match exactly once is
reported as not-run rather than as a catch: "the statement did not apply" recorded as a catch
is the false green this whole exercise exists to prevent.

    ../.venv/bin/python3 -m tests.mutate_access_domain
    ../.venv/bin/python3 -m tests.mutate_access_domain passback   # one subset
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
ACCESS = ROOT / "app" / "access"

#: (id, why, file, anchor, replacement). The replacement is a *plausible* alternative in each
#: case rather than a deliberate break, because the mutations worth running are the ones
#: somebody could write by accident.
MUTATIONS: list[tuple[str, str, str, str, str]] = [
    (
        "public-restricted",
        "a reason about somebody's account must not be readable off a turnstile",
        "policy.py",
        '    "anti_passback", "zone_at_capacity", "device_untrusted", "point_not_an_entry",',
        '    "anti_passback", "zone_at_capacity", "device_untrusted", "point_not_an_entry",\n'
        '    "outstanding_balance",',
    ),
    (
        "caller-chosen-public",
        "the public half is chosen by the code, never by the call site",
        "policy.py",
        "        public_reason=(public or private) if safe else DISCREET,",
        "        public_reason=public or private,",
    ),
    (
        "exit-decides",
        "paragraph 4177: an exit reader never makes an access decision",
        "zones.py",
        '    return direction in ("entry", "both")',
        '    return direction in ("entry", "both", "exit")',
    ),
    (
        "midnight-wrap",
        "an opening window that wraps past midnight is a night shift, not 'never'",
        "policy.py",
        "    if opens <= closes:\n        return opens <= minute < closes\n"
        "    return minute >= opens or minute < closes",
        "    return opens <= minute < closes",
    ),
    (
        "unknown-age-admitted",
        "at a door an unknown date of birth is not an adult",
        "policy.py",
        "        if subject.age_years is None:",
        "        if False:",
    ),
    (
        "first-entry-is-a-passback",
        "never having entered is not entering zero seconds ago",
        "passback.py",
        "    if previous is None:\n        return None",
        "    if previous is None:\n        return 0",
    ),
    (
        "negative-occupancy",
        "an advisory count is floored rather than reported negative",
        "occupancy.py",
        "    return max(0, entries - exits)",
        "    return entries - exits",
    ),
    (
        "clock-check-everything",
        "a bad reader clock refuses a rotating token and not a card",
        "credentials.py",
        "    if kind not in ROTATING_KINDS:\n        return\n"
        "    if abs(device_skew) > MAX_DEVICE_CLOCK_SKEW:",
        "    if abs(device_skew) > MAX_DEVICE_CLOCK_SKEW:",
    ),
    (
        "replay-key-drops-counter",
        "a replay key that ignores the counter lets a counter go backwards into a free slot",
        "credentials.py",
        '        f"{presented.digest}:{presented.rotation_counter}:'
        "{(presented.nonce or '').strip()}\")",
        '        f"{presented.digest}:{(presented.nonce or \'\').strip()}")',
    ),
    (
        "replay-expiry-from-device",
        "the replay window is measured from the server's clock, not the token's",
        "credentials.py",
        "    return at + REPLAY_WINDOW",
        "    return (presented.expires_at or at) + REPLAY_WINDOW",
    ),
    (
        "high-risk-ceiling",
        "a high-risk zone's offline authorization lives two hours, not twelve",
        "zones.py",
        '    "high_risk": timedelta(hours=2),',
        '    "high_risk": timedelta(hours=12),',
    ),
    (
        "stale-epoch-snapshot",
        "a snapshot minted before a revocation has already missed it",
        "offline.py",
        "    if posture.snapshot_epoch is None or posture.snapshot_epoch < posture.device_epoch:",
        "    if False:",
    ),
    (
        "capacity-off-by-one",
        "a zone at its capacity is full",
        "policy.py",
        "    if policy.capacity is not None and occupancy is not None"
        " and occupancy >= policy.capacity:",
        "    if policy.capacity is not None and occupancy is not None"
        " and occupancy > policy.capacity:",
    ),
    (
        "override-needs-no-reason",
        "an override states why",
        "policy.py",
        '    if not reason.strip():\n        raise AccessError("an override states why")',
        "    pass",
    ),
    (
        "override-reads-as-granted",
        "an override is its own code, not a flag on an ordinary grant",
        "policy.py",
        '        granted=True, code="granted_by_override", public_reason="welcome",',
        '        granted=True, code="granted", public_reason="welcome",',
    ),
    (
        "rotating-lifetime-unbounded",
        "a token minted for longer than the lifetime is a screenshot somebody can still use",
        "credentials.py",
        "    if presented.expires_at - presented.issued_at > ROTATING_LIFETIME:",
        "    if False:",
    ),
    (
        "unknown-code-accepted",
        "a free-text refusal is not a stable reason code",
        "policy.py",
        "    if code not in REASON_CODES:\n        raise AccessError"
        '(f"{code!r} is not an access reason code")',
        "    pass",
    ),
    (
        "supervised-decides",
        "a device whose clock cannot be trusted decides nothing on its own",
        "offline.py",
        '    return posture.mode != "supervised"',
        "    return True",
    ),
    (
        "unknown-risk-defaults",
        "an unknown risk class is refused rather than quietly treated as standard",
        "zones.py",
        "    if risk not in RISK_CLASSES:",
        "    if False:",
    ),
    (
        "one-reader-is-measured",
        "a zone that counts everybody in and nobody out is advisory",
        "occupancy.py",
        '    return "measured" if (readers.has_entry_reader and readers.has_exit_reader) '
        'else "advisory"',
        '    return "measured" if (readers.has_entry_reader or readers.has_exit_reader) '
        'else "advisory"',
    ),
]


def run_suite() -> bool:
    """True when the suite passes."""
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "tests.test_access_domain"],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
    )
    return result.returncode == 0


def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    chosen = [m for m in MUTATIONS if not only or only in m[0]]

    caught, gaps, not_run = 0, [], []
    for name, why, filename, anchor, replacement in chosen:
        path = ACCESS / filename
        original = path.read_text()
        occurrences = original.count(anchor)
        if occurrences != 1:
            not_run.append(f"{name}: the anchor appears {occurrences} times, not once")
            print(f"SKIP  {name} (anchor matched {occurrences} times)")
            continue
        path.write_text(original.replace(anchor, replacement))
        try:
            if run_suite():
                gaps.append(f"{name}: {why}")
                print(f"GAP   {name} -- the suite stayed green")
            else:
                caught += 1
                print(f"ok    {name} -- caught")
        finally:
            path.write_text(original)

    print(f"\n{caught}/{len(chosen)} mutations caught")
    if gaps:
        print("\nUNCAUGHT:\n  " + "\n  ".join(gaps))
    if not_run:
        print("\nNOT RUN:\n  " + "\n  ".join(not_run))
    return 0 if not gaps and not not_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
