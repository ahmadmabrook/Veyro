"""`python -m app.worker` -- one tick, or a loop until something says stop.

`--once` is the mode a test, a CI job and an operator checking a deployment all want: it runs
every job for every active tenant regardless of cadence, prints what it did as JSON, and exits
non-zero if any run failed. The loop mode is the one a process manager runs, and it exits only
on a signal -- a tick that fails is logged and the next one is attempted, because the
alternative is a process that dies on one tenant's bad data and takes every other tenant's
schedule with it.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
from datetime import timedelta
from types import FrameType

from app import db
from app.config import load_settings
from app.worker.names import JOB_NAMES
from app.worker.registry import JOBS
from app.worker.runner import Pools, run_forever, run_tick

#: Long enough that a tick is cheap and short enough that the shortest cadence in the registry
#: (fifteen seconds, the event relay) is actually honoured rather than rounded up.
DEFAULT_INTERVAL = timedelta(seconds=15)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.worker",
                                     description="Run Veyro's scheduled jobs.")
    parser.add_argument("--once", action="store_true",
                        help="run every job for every active tenant once, then exit")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL.total_seconds(),
                        help="seconds between ticks in loop mode")
    parser.add_argument("--job", action="append", choices=sorted(JOB_NAMES), default=None,
                        help="restrict to these jobs (repeatable)")
    parser.add_argument("--tenant", action="append", default=None,
                        help="restrict to these tenant ids (repeatable)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = load_settings()
    jobs = tuple(j for j in JOBS if args.job is None or j.name in args.job)
    if not jobs:
        print("no job matched", file=sys.stderr)
        return 2

    # Checked here rather than left to `tenant_scope`, which raises inside the job -- so a
    # mistyped id would be six job failures and a non-zero exit instead of one clear line.
    for tenant in args.tenant or ():
        if not db.is_tenant_id(tenant):
            print(f"not a tenant id: {tenant}", file=sys.stderr)
            return 2

    pools = Pools(platform=db.make_platform_pool(settings.database_url),
                  app=db.make_tenant_pool(settings.database_url),
                  worker=db.make_worker_pool(settings.database_url))
    try:
        if args.once:
            report = run_tick(pools, jobs=jobs, tenant_ids=args.tenant)
            print(json.dumps(report.summary(), indent=2))
            return 1 if report.failures else 0

        stopping = False

        def _stop(_signum: int, _frame: FrameType | None) -> None:
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)
        run_forever(pools, interval=timedelta(seconds=args.interval), jobs=jobs,
                    stop=lambda: stopping)
        return 0
    finally:
        for pool in (pools.platform, pools.app, pools.worker):
            pool.close()


if __name__ == "__main__":
    raise SystemExit(main())
