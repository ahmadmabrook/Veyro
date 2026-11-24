"""Mutations against the settable scrypt work factor, one protection at a time.

What these prove is that the deployed cost is still the default, that the band bites at both
ends, that `config.load_settings` refuses the setting outside `local`, and that `needs_rehash`
asks about what *this* process would store rather than about the constant -- the clause that
keeps a lowered cost from becoming more work rather than less.

Each removes one protection and nothing else; the harness compares the file's bytes before and
after, so a mutation that did not apply is reported NOT RUN rather than counted as a gap.

    VEYRO_DATABASE_URL=... python3 -m tests.mutate_work_factor
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import signal
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
SEC = "app/identity/secrets.py"
CFG = "app/config.py"
TESTS = ["tests.test_identity_domain", "tests.test_app"]

MUTATIONS = [
    # ---- the deployed cost is still the deployed cost -------------------------------------
    # The whole point of the constant: a password is low-entropy, so the only defence against
    # an offline attack on a stolen table is making each guess expensive.
    ("the shipped work factor is lowered",
     SEC,
     'DEFAULT_SCRYPT_PARAMS: dict[str, int] = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}',
     'DEFAULT_SCRYPT_PARAMS: dict[str, int] = {"n": 2**10, "r": 8, "p": 1, "dklen": 32}'),
    ("the process keeps a lowered factor instead of restoring the deployed one",
     SEC,
     "    if exponent is None:\n        _cost_log2 = COST_LOG2\n        return",
     "    if exponent is None:\n        return"),
    # ---- the band -------------------------------------------------------------------------
    ("the band stops biting",
     SEC,
     "    if not MIN_COST_LOG2 <= exponent <= COST_LOG2:",
     "    if False:"),
    ("the floor is removed, so a one-round hash is admitted",
     SEC,
     "    if not MIN_COST_LOG2 <= exponent <= COST_LOG2:",
     "    if not 0 <= exponent <= COST_LOG2:"),
    ("the ceiling is removed, so the knob can raise the cost too",
     SEC,
     "    if not MIN_COST_LOG2 <= exponent <= COST_LOG2:",
     "    if not MIN_COST_LOG2 <= exponent:"),
    # ---- what a hash carries --------------------------------------------------------------
    # A hash that stored the constant while being computed at the lowered cost would verify
    # against nothing, and one computed at the constant while storing the lowered figure would
    # be a row claiming to be cheaper than it is.
    ("a hash carries the constant rather than the factor in force",
     SEC,
     '    return {**DEFAULT_SCRYPT_PARAMS, "n": 2**_cost_log2}',
     "    return dict(DEFAULT_SCRYPT_PARAMS)"),
    # ---- the rehash question --------------------------------------------------------------
    ("needs_rehash asks about the constant rather than about this process",
     SEC,
     "    wanted = {**effective_params(), **(params or {})}",
     "    wanted = {**DEFAULT_SCRYPT_PARAMS, **(params or {})}"),
    # ---- the refusal outside local --------------------------------------------------------
    # Fail closed: an environment that is not local refuses to start rather than quietly
    # making every stored password cheap.
    ("development and staging stop refusing the setting",
     CFG,
     '        if environment != "local":\n'
     '            raise ConfigError(\n'
     '                "VEYRO_SCRYPT_COST_LOG2 is a local-only test setting; "\n'
     '                f"VEYRO_ENV is {environment!r}")',
     "        if False:\n            pass"),
    ("the configured value is no longer bounded",
     CFG,
     "        if not secrets.MIN_COST_LOG2 <= cost <= secrets.COST_LOG2:",
     "        if False:"),
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
