"""Mutations against ADR-0014's scope answer, one protection at a time.

What these prove is that a location-scoped caller can read at all, that they are *bounded*
rather than merely filtered, that a route which has not opted in still refuses them, that a
tenant-wide caller is unchanged, and that a brand scope is refused rather than guessed at.

**The limitation these close is the single most-repeated product one in this build**, recorded
in MOD-014, MOD-017, MOD-026 and MOD-027 in almost the same words: "a brand- or
location-scoped role cannot use this module at all".

Each removes one protection and nothing else; the harness compares the file's bytes before and
after, so a mutation that did not apply is reported NOT RUN rather than counted as a gap.

    VEYRO_DATABASE_URL=... python3 -m tests.mutate_scoped_gate
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import signal
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
MAIN = "app/main.py"
AUTHZ = "app/authorization/service.py"
DEC = "app/authorization/decision.py"
PEOPLE = "app/people/service.py"
TESTS = [
    "tests.test_authorization_api",
    "tests.test_gating.GateCoverageTests",
]

MUTATIONS = [
    # **The whole finding.** Without the re-decision a location-scoped caller is refused every
    # gated read, which is what every tenant in this build looked like until now.
    ("a location-scoped caller is refused the read entirely",
     AUTHZ,
     "            if where and not decided.allowed:",
     "            if False and not decided.allowed:"),
    # **Re-decided at their own broadest scope, not hand-waved.** Asking at the default scope
    # again gives the same refusal, so the mutation is the honest form of "notice a grant
    # exists and allow": it skips the evaluator.
    ("the re-decision asks at the default scope rather than theirs",
     AUTHZ,
     "                    request=authz.Request(action=action, scope=where[0],",
     "                    request=authz.Request(action=action, scope=authz.Scope(),"),
    # **`tenant_wide` is what `permit` keys on**, so a caller whose grants are all scoped
    # reading as tenant-wide is the leak this change exists to avoid: every untaught route
    # would return the whole tenant.
    ("a scoped caller reads as tenant-wide",
     AUTHZ,
     "                tenant_wide=any(one.scope_type == authz.TENANT for one in where))",
     "                tenant_wide=True)"),
    # **The opt-in, and the half that keeps it fail-closed.** Without it every route that has
    # not been taught to filter answers a scoped caller with the whole tenant.
    ("a route that has not opted in admits a scoped caller",
     MAIN,
     "        if not scoped and not gate.tenant_wide:",
     "        if False and not gate.tenant_wide:"),
    # **The boundary, as opposed to the filter.** `location_id` is what the reader asked for
    # and `only_locations` is where they may look; without the predicate the gate's answer is
    # computed and discarded, which is `Decision.mask`'s own five-module history.
    ("the gate's answer is computed and the query is not bounded",
     PEOPLE,
     '        where.append("s.location_id = ANY(%s)")',
     '        where.append("%s IS NOT NULL")'),
    # The route half of the same thing: a gate answer never passed on.
    ("the route never passes the boundary to the read",
     MAIN,
     "            only_locations=only,",
     "            only_locations=None,"),
    # **A brand scope is refused rather than guessed at.** `Scope.covers` says this module
    # does not know the hierarchy and must not guess; bounding on a brand id nobody resolved
    # would be that guess, and admitting a brand-scoped caller with no bound is the leak.
    ("a brand-scoped caller is admitted with no boundary",
     MAIN,
     "        if only is not None and not only:",
     "        if False and not only:"),
    # **`None` and `Scope()` are two questions, and the first implementation of this ADR was
    # silently inert because both check routes passed the second.** `/staff` answered a club
    # manager "yes" while the gate every surface reads answered "no" -- a screen saying "Not
    # permitted" over a read that would have worked.
    ("the check routes ask the tenant-wide question again",
     MAIN,
     "        if brand_id is None and location_id is None:\n            return None",
     "        if False:\n            return None"),
    # **A scope appears once**, however many roles grant it there -- and the tenant scope
    # comes first, which is what lets `tenant_wide` be read off `where[0]`'s kind without a
    # second rule.
    ("the scopes come back in whatever order the rows did",
     DEC,
     "    return tuple(sorted(\n        seen,",
     "    return tuple((\n        seen,"),
    # **Only the permission being asked about.** Without the filter a caller holding *any*
    # permission at a club would read as holding *this* one there.
    ("any permission at a club counts as this one",
     DEC,
     "        if not assignment.live(now) or permission not in assignment.permissions:",
     "        if not assignment.live(now):"),
    # **Live assignments only**, so an expired or revoked grant does not open a club.
    ("an expired or revoked assignment still opens its club",
     DEC,
     "        if not assignment.live(now) or permission not in assignment.permissions:",
     "        if permission not in assignment.permissions:"),
]


def digest(path: pathlib.Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def main() -> int:
    caught: list[str] = []
    uncaught: list[str] = []
    notrun: list[str] = []
    for name, rel, old, new in MUTATIONS:
        path = BACKEND / rel
        original = path.read_text()
        before = digest(path)

        def restore(
            *_: object, path: pathlib.Path = path, original: str = original,
        ) -> None:
            path.write_text(original)
            sys.exit(130)

        handlers = {
            sig: signal.signal(sig, restore)
            for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
        try:
            if original.count(old) != 1:
                notrun.append(f"{name}: anchor appears {original.count(old)} times")
                continue
            path.write_text(original.replace(old, new, 1))
            if digest(path) == before:
                notrun.append(f"{name}: file unchanged")
                continue
            run = subprocess.run(
                ["../.venv/bin/python3", "-B", "-m", "unittest", *TESTS],
                cwd=BACKEND, capture_output=True, text=True, env=os.environ.copy())
            (caught if run.returncode != 0 else uncaught).append(name)
        finally:
            path.write_text(original)
            assert digest(path) == before, f"{rel} not restored"
            for sig, previous in handlers.items():
                signal.signal(sig, previous)

    for name in caught:
        print(f"CAUGHT    {name}")
    for name in uncaught:
        print(f"UNCAUGHT  {name}")
    for name in notrun:
        print(f"NOT RUN   {name}")
    print(f"\n{len(caught)}/{len(MUTATIONS)} caught, {len(notrun)} not run")
    return 0 if not uncaught and not notrun else 1


if __name__ == "__main__":
    sys.exit(main())
