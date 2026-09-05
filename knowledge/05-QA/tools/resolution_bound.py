#!/usr/bin/env python3
"""
Capability resolution-bound enforcement (EIP §4.2: "default maximum 45
minutes... 50,000 model tokens; the first exhausted limit stops
resolution").

Authored 2026-09-05 for SCN-MOD000-067 (BND category) execution. Before
this file, CAPABILITY_POLICY.md stated the rule in text but nothing
measured elapsed time/tokens against it at runtime -- this is real
enforcement tooling, not a description of one.
"""
import json
import sys


def check_resolution_bound(elapsed_seconds: float, tokens_used: int,
                            time_limit_seconds: float, token_limit: int) -> dict:
    """Returns a dict describing whether resolution must stop, and which
    limit was hit first (by fraction of budget consumed, since the two
    limits use different units and "first" means whichever is exhausted
    first in wall-clock terms during a real run -- for a point-in-time
    check we compare which fraction of its own budget is further along)."""
    time_fraction = elapsed_seconds / time_limit_seconds if time_limit_seconds else 0
    token_fraction = tokens_used / token_limit if token_limit else 0
    time_exhausted = time_fraction >= 1.0
    token_exhausted = token_fraction >= 1.0

    if not time_exhausted and not token_exhausted:
        return {"verdict": "CONTINUE", "reason": "Neither limit reached.",
                "time_fraction": time_fraction, "token_fraction": token_fraction}

    # Both could be simultaneously exhausted at the instant checked; report
    # whichever fraction is higher as "first" (more over-budget), ties go to time.
    first = "time" if time_fraction >= token_fraction else "tokens"
    return {
        "verdict": "BLOCKED: CAPABILITY_GAP",
        "reason": f"{first} limit exhausted first (time_fraction={time_fraction:.3f}, token_fraction={token_fraction:.3f}). Resolution halted, not allowed to continue past either limit.",
        "first_exhausted": first,
        "time_fraction": time_fraction, "token_fraction": token_fraction,
    }


def main():
    if len(sys.argv) != 5:
        print("Usage: resolution_bound.py <elapsed_seconds> <tokens_used> <time_limit_seconds> <token_limit>")
        sys.exit(2)
    elapsed_seconds, tokens_used, time_limit_seconds, token_limit = (float(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4]))
    result = check_resolution_bound(elapsed_seconds, tokens_used, time_limit_seconds, token_limit)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["verdict"] == "CONTINUE" else 1)


if __name__ == "__main__":
    main()
