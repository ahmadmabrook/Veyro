"""Mutations against the price quote, one protection at a time.

**The quote is three decisions and a delegation**, and each is a line somebody could change
without any test noticing unless it is broken on purpose: which permission it charges, that it
writes nothing, and that a field it does not have is refused rather than ignored.

**The last of those is the one worth the sweep.** Pydantic ignores an unknown field by
default, so before `extra="forbid"` a caller sending `coupon_code` got a figure with the
coupon *not* applied -- a plausible number, which is worse than a refusal. Removing the config
line is the mutation, and only the coupon case sees it.

Each removes one protection and nothing else; the harness compares the file's bytes before and
after, so a mutation that did not apply is reported NOT RUN rather than counted as a gap.

    VEYRO_DATABASE_URL=... python3 -m tests.mutate_price_quote
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
CATALOG = "app/catalog/service.py"
TESTS = ["tests.test_catalog_api.QuoteTests"]

MUTATIONS = [
    # **The permission.** Charging the sale's permission for a read makes the quote
    # unreachable by a front desk that may see what a sale costs and may not make one -- which
    # is the whole product point, and no other case here would notice.
    ("the quote charges the sale's permission instead of the read's",
     MAIN,
     '        permit(session, "catalog.price.read", body.correlation_id)\n'
     '        return catalog.quote_price(',
     '        permit(session, "catalog.price.resolve", body.correlation_id)\n'
     '        return catalog.quote_price('),
    # **The flag that is the whole difference.** With `store=True` the quote writes the
    # receipt it exists not to write, and a page view leaves a row in an insert-only table.
    ("the quote stores its resolution after all",
     CATALOG,
     '        location_id=location_id, subject_id=subject_id, at=at, store=False)',
     '        location_id=location_id, subject_id=subject_id, at=at, store=True)'),
    # **The absence that has to be a control.** Without the config line a coupon code is
    # dropped in silence and the undiscounted figure is returned as though it were the answer.
    ("an unknown field is ignored rather than refused",
     MAIN,
     '    model_config = ConfigDict(extra="forbid")\n\n    variant_id: str',
     '    variant_id: str'),
    # **The disclosure.** A null resolution id on a response whose sibling route always
    # carries one reads as a write that failed, so the sentence is the thing a reader acts on.
    ("the quote stops saying that nothing was recorded",
     CATALOG,
     '    quoted["recorded"] = False',
     '    quoted["recorded"] = True'),
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
