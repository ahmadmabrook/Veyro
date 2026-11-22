"""Break each wired sweep's own protections and require its cases to fail.

**The protection here is an absence of writes**, which is the hardest kind to test by looking
at a green suite: the wiring works either way, and the difference between "announced once"
and "announced every five minutes for ever" is a row count in a table with no DELETE grant.
So each mutation removes one piece of the dedupe and the case that names it has to go red.

Two of them are about the savepoint rather than the key, because catching a `Conflict` without
one leaves a transaction PostgreSQL has aborted and the commit afterwards is what fails -- the
shape MOD-022's review recorded, where a failure path carried on inside a dead transaction and
the one control that noticed a replay left no evidence at all.

**Two protections here are deliberately not mutated, because neither mutation would be
evidence.** The savepoint around the append reads as load-bearing and is not: PostgreSQL's
`COMMIT` on a transaction that has already errored performs a rollback and reports success, and
nothing follows the append in that transaction -- so removing the savepoint changes no
behaviour at all, which is this repository's "a mutation that changes nothing is not evidence".
It stays because the next writer to add a statement after the append would otherwise lose it
silently, and because a bare `except Conflict` on a connection with no savepoint is the exact
shape MOD-022's review found. And the sweep's per-objective `except` has no isolating case: the
reachable trigger is an operator retiring an objective between the listing transaction and that
objective's own evaluation, which is a window between two transactions rather than inside
either. Both are stated in `evaluate_live_objectives`' own docstring instead.

Run it with the database up, from `backend/`:

    VEYRO_DATABASE_URL=... python tests/mutate_worker_sweeps.py
"""
import pathlib
import subprocess
import sys

SERVICE = pathlib.Path("app/observability/service.py")
DECIDE = pathlib.Path("app/observability/objectives.py")
REGISTRY = pathlib.Path("app/worker/registry.py")
NOTIFY = pathlib.Path("app/notifications/service.py")
COMMERCIAL = pathlib.Path("app/commercial/service.py")

MUTATIONS = [
    # The dedupe itself. Without the key every evaluation announces, which is 288 rows a day
    # per breaching objective at this job's cadence, in a table nothing can delete from.
    (SERVICE, "no idempotency key, so every evaluation announces",
     "                        idempotency_key=objectives.breach_key("
     "objective_id, window_start),\n",
     ""),
    # The window. Flooring to the objective's own window is what makes "once per window" mean
    # anything; using the raw instant makes the key unique per microsecond.
    (SERVICE, "key built from the instant rather than the window",
     "            window_start = objectives.announcement_window(\n"
     "                until or _now(), window_hours=row[5])",
     "            window_start = until or _now()"),
    # The window length, ignored. A 24-hour objective would then announce hourly -- and this
    # is the one mutation in the file that the *integration* tests cannot see, because four
    # ticks inside one hour agree whatever the window length is. Its case is a domain test
    # over two instants hours apart, which is why this file names a suite per mutation.
    (DECIDE, "window length ignored, so every objective announces hourly",
     "    span = window_hours * 3600",
     "    span = 3600", "tests.test_observability_domain"),
    # The empty-window rule, which predates this change and had no case until the sweep's
    # tests arrived: announcing on no data is how an alert channel gets muted.
    (SERVICE, "an empty window announces a breach",
     "        if not verdict.met and verdict.buckets > 0:",
     "        if not verdict.met:"),
    # The job's own wiring: a registry entry naming a key its job does not return reports zero
    # units for ever, which an operations board reads as "it ran and did nothing".
    (REGISTRY, "the units key names something the job does not return",
     '        units="evaluated",',
     '        units="objectives_evaluated",'),

    # MOD-013's digest close. The one thing this sweep could get wrong is closing a window
    # early, because the index that keeps a batch in one row is partial on `state = 'open'`:
    # an early close lets the next notification in that window open a second row and split
    # the batch the index exists to prevent.
    (NOTIFY, "a digest window is closed before it has ended",
     "                WHERE state = 'open' AND window_end <= %s",
     "                WHERE state = 'open' AND window_start <= %s"),
    # And closing something that is not open would re-stamp a closed digest's `closed_at`,
    # losing when the window actually ended.
    (NOTIFY, "a digest already closed is closed again",
     "                WHERE state = 'open' AND window_end <= %s",
     "                WHERE window_end <= %s"),

    # MOD-017's ended-membership revocation. The two directions that matter are opposite
    # harms: revoking a membership still inside its notice takes away training the member has
    # paid for, and not revoking one whose notice ran out is access nobody is paying for.
    (COMMERCIAL, "a membership still inside its notice has its grants revoked",
     "            WHERE m.ends_on IS NOT NULL AND m.ends_on < %s AND g.status = 'active'",
     "            WHERE m.ends_on IS NOT NULL AND g.status = 'active'",
     "tests.test_commercial_api.EndedMembershipGrantTests"),
    (COMMERCIAL, "a membership whose notice ran out keeps its grants",
     "            WHERE m.ends_on IS NOT NULL AND m.ends_on < %s AND g.status = 'active'",
     "            WHERE m.ends_on IS NULL AND g.status = 'active'",
     "tests.test_commercial_api.EndedMembershipGrantTests"),
]

#: The suite each mutation is judged by. Most are the worker's integration tests; the window
#: length is a domain test, because no number of ticks inside one hour can tell a 24-hour
#: window from an hourly one.
CASE = "tests.test_worker"


def main() -> int:
    originals = {path: path.read_text() for path in {m[0] for m in MUTATIONS}}
    caught, gaps, notrun = 0, [], []
    try:
        for mutation in MUTATIONS:
            path, name, frm, to = mutation[:4]
            case = mutation[4] if len(mutation) > 4 else CASE
            text = originals[path]
            if text.count(frm) != 1:
                notrun.append(f"{name}: anchor appears {text.count(frm)} times, not once")
                print(f"SKIP  {name}")
                continue
            path.write_text(text.replace(frm, to, 1))
            try:
                run = subprocess.run([sys.executable, "-m", "unittest", case],
                                     capture_output=True, text=True, timeout=600)
                out = run.stdout + run.stderr
                if "Ran 0 tests" in out:
                    notrun.append(f"{name}: the suite did not run")
                    print(f"SKIP  {name} (suite did not run)")
                elif run.returncode != 0:
                    caught += 1
                    print(f"ok    {name} -- caught")
                else:
                    gaps.append(name)
                    print(f"GAP   {name} -- the suite stayed green")
            finally:
                path.write_text(text)
    finally:
        # **Restored whatever happened**, including on a signal: this repository has lost an
        # hour to a sweep killed with a mutation still in the tree, twice.
        for path, text in originals.items():
            path.write_text(text)

    print(f"\n{caught}/{len(MUTATIONS)} caught")
    if gaps:
        print("UNCAUGHT:\n  " + "\n  ".join(gaps))
    if notrun:
        print("NOT RUN:\n  " + "\n  ".join(notrun))
    return 0 if not gaps and not notrun else 1


if __name__ == "__main__":
    sys.exit(main())
