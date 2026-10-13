#!/usr/bin/env python3
"""
Fail-closed CPython 3.13 / linux-x86_64 / 64-bit interpreter assertion
(MOD-001, M1-C-06 — decision record
`knowledge/03-Modules/MOD-001/evidence/implementation/
M1-C-06-MYPY-CI-LOCK-ARCHITECTURE-2026-10-09.md` §4 and acceptance B2/B9).

Lock-independent and stdlib-only. Denies (exit 1) unless the interpreter
running it satisfies ALL of:

  1. sys.implementation.name == "cpython"
  2. sys.version_info[:2] == (3, 13)  (exact, not a lower bound)
  3. sysconfig.get_platform() starts with "linux-x86_64"
  4. sys.maxsize > 2**32  (64-bit)

Every check is evaluated (no short-circuit) so the evidence output names
each outcome. `check_interpreter` is a pure function over injected values;
only `main` reads the live interpreter. A local run is NOT evidence that CI
behaves identically, and a macOS/Python 3.14 host is expected to deny.
"""

import sys
import sysconfig

EXPECTED_IMPLEMENTATION = "cpython"
EXPECTED_VERSION = (3, 13)
EXPECTED_PLATFORM_PREFIX = "linux-x86_64"
MIN_EXCLUSIVE_MAXSIZE = 2**32


def check_interpreter(implementation, version_info, platform, maxsize):
    """Return a list of (check_name, passed, observed) tuples. Pure."""
    try:
        version = tuple(version_info)[:2]
    except TypeError:
        version = None
    return [
        (
            "implementation_is_cpython",
            implementation == EXPECTED_IMPLEMENTATION,
            implementation,
        ),
        ("version_is_3_13", version == EXPECTED_VERSION, version),
        (
            "platform_is_linux_x86_64",
            isinstance(platform, str) and platform.startswith(EXPECTED_PLATFORM_PREFIX),
            platform,
        ),
        (
            "is_64_bit",
            isinstance(maxsize, int)
            and not isinstance(maxsize, bool)
            and maxsize > MIN_EXCLUSIVE_MAXSIZE,
            maxsize,
        ),
    ]


def all_passed(results):
    """Deny on an empty result set as well as on any failed check."""
    return bool(results) and all(passed for _, passed, _ in results)


def main():
    print(f"executable: {sys.executable}")
    print(f"version: {sys.version}")
    results = check_interpreter(
        sys.implementation.name,
        sys.version_info,
        sysconfig.get_platform(),
        sys.maxsize,
    )
    for name, passed, observed in results:
        print(f"{name}: {'PASS' if passed else 'FAIL'} (observed={observed!r})")
    if all_passed(results):
        print("RESULT: ALLOW")
        return 0
    print("RESULT: DENY")
    return 1


if __name__ == "__main__":
    sys.exit(main())
