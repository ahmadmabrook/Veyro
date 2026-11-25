"""Mutations against ADM-PAY-06's dunning policy, one protection at a time.

What these prove is that the two settable figures reach the decisions rather than only the
response, that the journey's one un-invertible ordering is refused, that the notices do not
move when the access grace does, and that a value written past the registry cannot take a
dunning run down.

Each removes one protection and nothing else; the harness compares the file's bytes before and
after, so a mutation that did not apply is reported NOT RUN rather than counted as a gap.

    VEYRO_DATABASE_URL=... python3 -m tests.mutate_dunning_policy
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
COLLECTIONS = "app/commercial/collections.py"
SERVICE = "app/commercial/service.py"

#: (id, file, from, to, the dotted test that must fail)
_DOMAIN = "tests.test_commercial_domain.DunningPolicyTests"
_API = "tests.test_commercial_api.DunningPolicyApiTests"
_WORKSPACE = "tests.test_commercial_api.CommandCentreReadTests"

MUTATIONS = [
    # **The lower bound is the journey's one un-invertible ordering.** The `warn` stage sits at
    # seven days, so a grace shorter than that restricts access before the member has been
    # warned -- which is why the band starts at eight rather than at one.
    ("a grace shorter than the warning is admitted",
     COLLECTIONS,
     "        if not (MIN_ACCESS_GRACE_DAYS <= self.access_grace_days <= MAX_ACCESS_GRACE_DAYS):",
     "        if False:",
     f"{_DOMAIN}.test_a_grace_shorter_than_the_warning_is_refused"),
    # A budget outside one to twenty is a figure `may_retry` would refuse later, stored now.
    ("a retry budget outside the band is stored",
     COLLECTIONS,
     "        if self.retry_attempts < 1 or self.retry_attempts > 20:",
     "        if False:",
     f"{_DOMAIN}.test_the_retry_budget_is_bounded_where_it_is_decided"),
    # **The head of the journey is the product's notice schedule.** Shifting it too would make
    # "allow access for 30 days" also mean "warn after 15", which the canvas does not say.
    ("the notice schedule moves with the access grace",
     COLLECTIONS,
     "        (n, days + shift if n >= _ACCESS_STAGE else days, key, access)",
     "        (n, days + shift, key, access)",
     f"{_DOMAIN}.test_the_tail_moves_with_the_grace_and_the_notices_do_not"),
    # The figure reaches the dates, not only the sort: a journey run on the module's constant
    # while a workspace sorted by the tenant's is two answers to one question.
    ("an advance is dated by the module's constant rather than the tenant's figure",
     COLLECTIONS,
     "    step = stage(following, policy)",
     "    step = stage(following)",
     f"{_API}.test_the_published_grace_is_the_date_a_case_is_advanced_to"),
    # **The writer this guards against is the one that is not a route**, and this read is on
    # the path of every advance.
    ("a value written past the registry raises instead of falling back",
     SERVICE,
     "    except collections.CollectionsError:\n        policy = collections.DEFAULT_POLICY",
     "    except collections.CollectionsError:\n        raise",
     f"{_API}.test_a_value_written_past_the_registry_cannot_take_a_dunning_run_down"),
    # A `jsonb` value is whatever somebody wrote; a string where an integer belongs would reach
    # `Policy` as a type it does not check and the band would never be evaluated.
    ("a non-integer value is passed through to the policy",
     SERVICE,
     "        return value if isinstance(value, int) and not isinstance(value, bool) else fallback",
     "        return value if value is not None else fallback",
     f"{_API}.test_a_value_of_the_wrong_type_falls_back_rather_than_raising"),
    # **A default is not a decision.** Without `declared` a surface cannot tell a tenant that
    # chose these figures from one that has never been configured.
    ("a default is indistinguishable from a decision",
     SERVICE,
     "    return policy, sorted(got)",
     "    return policy, [DUNNING_RETRY_KEY, DUNNING_GRACE_KEY]",
     f"{_API}.test_a_tenant_that_has_declared_nothing_reads_the_defaults_and_says_so"),
    # One rule per tenant: a brand or location value winning would make the journey differ by
    # club, which is not what a collections policy is.
    ("a brand or location value overrides the tenant's policy",
     SERVICE,
     "        \"    ON v.definition_id = d.definition_id AND v.scope_type = 'tenant'\"",
     "        \"    ON v.definition_id = d.definition_id\"",
     f"{_API}.test_a_brand_value_does_not_override_the_tenant_s_policy"),
    # **The budget is what the workspace sorts on.** Reading the default here would sort a
    # tenant's failed payments by somebody else's policy.
    ("the workspace sorts by the module's default budget",
     SERVICE,
     "            max_attempts=policy.retry_attempts)",
     "            max_attempts=collections.DEFAULT_RETRY_ATTEMPTS)",
     f"{_WORKSPACE}.test_the_workspace_sorts_by_the_tenant_s_own_retry_budget"),
    # The pair is validated before either is written, so a refused figure publishes nothing.
    # **Not the route's own body**, which bounds both figures and so can never reach this:
    # the writer this guards against is the one that is not a route, and the case drives the
    # service directly. Without it the valid half publishes and the refusal leaves a tenant
    # half-configured.
    ("a refused pair publishes the half that was valid",
     SERVICE,
     "        collections.Policy(\n            retry_attempts=retry_attempts, "
     "access_grace_days=access_grace_days)",
     "        pass",
     f"{_API}.test_a_refused_pair_publishes_neither_half"),
]


def run(test: str) -> bool:
    """True when the named test fails, which is what a caught mutation looks like."""
    done = subprocess.run(
        [sys.executable, "-B", "-m", "unittest", test],
        cwd=BACKEND, capture_output=True, text=True, timeout=600)
    return done.returncode != 0


def main() -> int:
    caught, gaps, not_run = 0, [], []
    for name, rel, frm, to, test in MUTATIONS:
        path = BACKEND / rel
        original = path.read_text()
        if original.count(frm) != 1:
            not_run.append(f"{name}: the anchor appears {original.count(frm)} times")
            print(f"SKIP  {name}")
            continue
        path.write_text(original.replace(frm, to, 1))
        try:
            # The bytes changed, or the mutation is a no-op and proves nothing.
            if path.read_text() == original:
                not_run.append(f"{name}: the file is unchanged")
                continue
            if run(test):
                caught += 1
                print(f"ok    {name} -- caught")
            else:
                gaps.append(name)
                print(f"GAP   {name} -- UNCAUGHT by {test}")
        finally:
            path.write_text(original)
    for line in not_run:
        print(f"NOT RUN  {line}")
    print(f"\n{caught}/{len(MUTATIONS)} mutations caught"
          + (f", {len(not_run)} not run" if not_run else ""))
    return 1 if gaps or not_run else 0


if __name__ == "__main__":
    raise SystemExit(main())
