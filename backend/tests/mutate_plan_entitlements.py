"""Mutations against ADR-0013's plan-to-entitlement edge, one protection at a time.

What these prove is that an activation really grants what the plan declares, that the mapping
is read at activation and never again, that a plan change revokes only what *that plan* gave,
that a future-dated downgrade leaves the rights alone, and that the loss panel's four lists are
four different facts rather than one.

**The canvas's own note is the requirement**: "The loss is stated before the saving, and the
credit expiry is the line that matters -- a member who discovers it afterwards has been quietly
charged for something they never got."

Each removes one protection and nothing else; the harness compares the file's bytes before and
after, so a mutation that did not apply is reported NOT RUN rather than counted as a gap.

    VEYRO_DATABASE_URL=... python3 -m tests.mutate_plan_entitlements
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import signal
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
MEM = "app/commercial/service.py"
ENT = "app/commercial/entitlements.py"
TESTS = [
    "tests.test_commercial_api.PlanEntitlementTests",
    "tests.test_commercial_api.PlanMoveTests",
]

MUTATIONS = [
    # **The hole this slice closes.** Without the call, activating a membership grants
    # nothing -- which is what this build did until now, and what made COM-01-R03's whole
    # entitlement model unreachable from the product.
    # The first version of this mutation was `granted = [] or _grant_plan(...)`, which in
    # Python evaluates the call -- so it changed nothing and came back uncaught. A conditional
    # expression is the well-formed form: the whole call becomes the unreachable else branch.
    ("an activation grants nothing",
     MEM,
     "        granted = _grant_plan(\n"
     "            conn, tenant_id, membership_id=membership_id, person_id=str(agreement[0]),",
     "        granted = [] if True else _grant_plan(\n"
     "            conn, tenant_id, membership_id=membership_id, person_id=str(agreement[0]),"),
    # **The opening movement**, without which a counted grant's balance is zero on a grant
    # that says two: this module has exactly one authority on a balance and it is the ledger.
    ("a counted grant is written without its opening movement",
     MEM,
     "        if right.is_counted:\n"
     "            assert right.quantity is not None\n"
     "            _movement(conn, tenant_id, grant_id=grant_id, movement_kind=\"grant\",",
     "        if False and right.is_counted:\n"
     "            assert right.quantity is not None\n"
     "            _movement(conn, tenant_id, grant_id=grant_id, movement_kind=\"grant\","),
    # **`from_variant_id`**, which is the whole reason the column exists: without it a plan
    # change cannot tell which rights the plan being left gave, so a downgrade would have to
    # revoke every grant the membership ever had -- goodwill ones included.
    ("a plan change revokes every grant rather than the leaving plan's",
     MEM,
     "        \" WHERE membership_id = %s AND from_variant_id = %s AND status = 'active'\"\n"
     "        \" ORDER BY created_at\",\n"
     "        (membership_id, variant_id),",
     "        \" WHERE membership_id = %s AND coalesce(from_variant_id, %s) IS NOT NULL\"\n"
     "        \"   AND status = 'active' ORDER BY created_at\",\n"
     "        (membership_id, variant_id),"),
    # **Only where the change is effective now.** A downgrade takes effect at the next
    # renewal, and ADM-MSH-06's canvas is explicit that the member keeps what they paid for:
    # "she has paid for August at the higher rate and keeps it".
    ("a future-dated downgrade revokes the rights today",
     MEM,
     "        moved: dict[str, Any] = {\"revoked\": [], \"granted\": []}\n"
     "        if change.effective_on <= today:",
     "        moved: dict[str, Any] = {\"revoked\": [], \"granted\": []}\n"
     "        if True:"),
    # **The write-off is the balance, which is already net of what is held.** Subtracting
    # the hold a second time -- which the first version of this function did -- writes off
    # nothing on a grant with one of two credits booked, leaving a *revoked* grant carrying a
    # balance of one. `_revoke_grants`' own comment says the movement exists so that "the
    # balance afterwards is zero by arithmetic rather than by the status column saying so".
    ("a reserved credit is subtracted twice, so a revoked grant keeps a balance",
     MEM,
     "        writable = balance if grant.is_counted else 0",
     "        writable = max(balance - held, 0) if grant.is_counted else 0"),
    # **The scope is part of a right's identity**, which is ADM-MSH-06's own distinction
    # between "all-clubs access" and "access to Abdoun and Sweifieh": the same policy at two
    # scopes, so a diff keyed on the policy alone reports no change.
    ("two scopes of one right are treated as the same right",
     ENT,
     "    return (one.policy_id == other.policy_id\n"
     "            and one.brand_id == other.brand_id\n"
     "            and one.location_id == other.location_id",
     "    return (one.policy_id == other.policy_id\n"
     "            and True\n"
     "            and True"),
    # **A requantified right is neither kept nor lost.** Four sessions becoming two is the
    # half a member argues about, and calling it "kept" reads as no change.
    ("a smaller quantity reads as keeping the right",
     ENT,
     "        if match.quantity == one.quantity:\n"
     "            kept.append(match)",
     "        if True:\n"
     "            kept.append(match)"),
    # **A counted right is declared in a quantity**, refused when a plan is declared rather
    # than when a member activates one -- because an activation refused for a plan's own
    # misconfiguration is a member at a desk who has paid.
    ("a counted right may be declared with no quantity",
     ENT,
     '    if is_counted and quantity is None:\n'
     '        raise EntitlementError("a_counted_entitlement_is_granted_in_a_quantity")',
     '    if False and quantity is None:\n'
     '        raise EntitlementError("a_counted_entitlement_is_granted_in_a_quantity")'),
    ("an uncounted right may be declared with a quantity",
     ENT,
     '    if not is_counted and quantity is not None:\n'
     '        raise EntitlementError("an_unlimited_entitlement_takes_no_quantity")',
     '    if False and quantity is not None:\n'
     '        raise EntitlementError("an_unlimited_entitlement_takes_no_quantity")'),
    # **A withdrawn right is not granted.** Without the filter a plan goes on granting a
    # right somebody withdrew, which is the remedy the column exists to provide, defeated.
    ("a withdrawn right is still granted at activation",
     MEM,
     '        " WHERE e.variant_id = %s AND e.withdrawn_at IS NULL AND p.status = \'active\'"',
     '        " WHERE e.variant_id = %s AND p.status = \'active\'"'),
    # **No mutation for the retired-policy clause, and the absence is the finding.**
    # `mem_entitlement_policies` carries no UPDATE grant for any runtime role, so
    # `retired` is a declared status nothing in this build can write -- another instance
    # of the shape this repository keeps finding, in the table COM-01-R03's rights are
    # declared in. The clause stays because it mirrors `grant_entitlement`'s own check
    # and will be right the day a retire command exists; there is no writer for a probe
    # to be until then.
    # **A double withdrawal is a 409, not a silent success**, because a withdrawal reporting
    # ok twice reads as two different acts.
    ("a second withdrawal reports success",
     MEM,
     '            raise Conflict("this_plan_entitlement_is_already_withdrawn")',
     '            return {"plan_entitlement_id": plan_entitlement_id, "withdrawn": True,\n'
     '                    "grants_already_written_are_unchanged": True}'),
    # **The duplicate is a 409 naming the scope**, rather than psycopg's 500 telling a caller
    # to try again when the answer is that the plan already grants it.
    # **A well-formed replacement.** The first version of this mutation named
    # `_NeverRaised`, which does not exist -- so the suite failed with a `NameError` and the
    # harness reported CAUGHT for a reason unrelated to the catch. That is the fourth form of
    # ill-formed mutation this repository records, and the cheapest to write.
    ("a duplicate declaration answers 500 instead of naming the scope",
     MEM,
     "        except errors.UniqueViolation:\n"
     "            # Caught as a 409 rather than left to psycopg's 500",
     "        except errors.NotNullViolation:\n"
     "            # Caught as a 409 rather than left to psycopg's 500"),
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
