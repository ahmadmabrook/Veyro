"""
Fixed-suite path-allowlist pytest runner (MOD-001, M1-C-07; GOV-01-R01/R02).

**This tool authorises nothing.** CAP-011 (`pytest` 9.1.1) is
`QUALIFIED — NOT APPROVED` in `knowledge/00-System/CAPABILITY_REGISTRY.md`:
its independent determination and `approved_by` fields do not exist, so no
reliance on a pytest result is permitted and no run through this file is a
gate, scenario or assurance result. What this file supplies is the one open
dependency the CAP-011 row names as a *precondition* of any later reliance —
"a path-allowlist wrapper (not yet written/qualified)" — in reviewable,
committed form, so the candidate workflow stops calling `pytest` directly with
a shell-interpolated path.

Why a wrapper is the only thing that can enforce the boundary. The CAP-011
target-scope drill (`knowledge/03-Modules/MOD-001/evidence/implementation/
M1-C-06-PYTEST-TARGET-SCOPE-SYNTHETIC-2026-10-09.md` §4) recorded two findings
that no pytest flag closes:

  * **An explicit path argument outside the root is honoured** — including
    `../` traversal — and the conftest at that location *executes*, despite
    `--rootdir` and `--confcutdir`. `--confcutdir` only stops ancestor
    discovery above itself; it is not an argument allowlist. "So the discovery
    boundary is therefore enforced only by the caller."
  * **`testpaths` falls back to cwd** when it names a missing directory and no
    path argument is given, so a renamed suite silently widens the run.

Hence: the caller never supplies a path. The CLI takes one suite *name* from a
closed set, and every path in the argv comes from the literal `SUITES` table
below, canonicalised against this file's own repository location. There is no
flag, environment variable or marker file that can add a target.

What it denies, all before pytest is started (`plan()` raises `Denied`):
  1. an unknown suite name (closed `argparse` choice set *and* a table lookup);
  2. a missing suite — absent directory, absent file, or wrong kind — rather
     than letting pytest's rc 4/5 look like a pass;
  3. an empty suite directory (no `test_*.py`), which would otherwise report
     success by collecting nothing;
  4. a symlink anywhere in the path to the suite, or on any entry inside it.
     This scan covers the collection target only. It is NOT a bound on the
     import closure: for the backend suites `-m` puts `backend` on `sys.path`,
     and the suites import `backend/tests/harness/` (and the conftest chain),
     which lie outside every scanned suite directory. A symlinked or
     substituted module there would execute with no refusal from this tool;
  5. an ambient pytest override in the environment — any inherited `PYTEST_*`
     variable (the drill's G4 control proved `PYTEST_ADDOPTS` is honoured) and
     a non-empty `PYTHONPATH` (its G1 control proved an entry-point plugin on
     `PYTHONPATH` loads when autoload is on).

Environment honesty. The child environment is built from `INHERITED_ENV_VARS`,
which copies `PATH`, `HOME`, `TMPDIR`, `TMP`, `TEMP`, `LANG`, `LC_ALL` and `TZ`
from the invoking environment **verbatim**. This tool does not confine `HOME`
or the temp variables to a disposable location: test code runs with the
caller's real home and temp directories. Any evidence that ran under a
disposable `HOME`/`TMPDIR` got that containment from the driver, not from
this file. The `idempotency-contract` suite also spawns further processes
itself (`subprocess.run` of the lint's CLI); those inherit this child
environment and their argv is not governed by this tool.

Non-zero exits are never "ok": rc 1 is reported as test failures and every
other non-zero pytest rc — 2, 3, and in particular 4 (path not found) and 5
(nothing collected) — is a denial, per the drill's §4.3 finding.

Scope honesty. This file is written against CAP-011's drafted invocation shape
and adds no approval. Two boundaries it does not close, and does not pretend
to: the `idempotency-contract` suite lives outside `backend/tests`, which is
the only tree the drafted scope names, and it borrows `backend/pyproject.toml`
as its explicit `-c` config because that is the repository's only committed
`[tool.pytest.ini_options]` (its single `testpaths` key is inert here, since an
explicit path argument is always passed); and the version probe's eligibility
check binds the run to the hash-installed pytest but was never executed
against a Veyro path by the authoring session.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Distinct on purpose: a denial must never be readable as "the suite passed",
# and it must also never be readable as "a test failed" — the two have
# different follow-up actions.
EXIT_OK = 0
EXIT_TEST_FAILURES = 1
EXIT_DENIED = 2

# CAP-011's pinned release. The candidate workflow installs it from
# `backend/requirements-typecheck-linux-x86_64-cp313.lock.txt` under
# `--require-hashes`, so this assertion is what carries that pin into the
# invocation rather than leaving it at install time only.
EXPECTED_PYTEST_VERSION = "pytest 9.1.1"

# The only environment variables passed through to pytest. Everything else is
# dropped: the child is built from this list, never inherited wholesale. `-E`
# (implied by `-I`) makes the child ignore every `PYTHON*` variable anyway, so
# none are set here.
INHERITED_ENV_VARS = ("PATH", "HOME", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "TZ")


class Denied(Exception):
    """A fail-closed refusal. Raised before any pytest process is started."""


@dataclass(frozen=True)
class Suite:
    """One allowlisted suite. Every field is a repository-relative literal.

    `cwd`, `config`, `rootdir` and `confcutdir` are carried per suite rather
    than derived, so the invocation shape of each suite is readable here
    instead of being assembled at call time.
    """

    target: str
    is_dir: bool
    cwd: str
    config: str
    rootdir: str
    confcutdir: str


# The path allowlist. Written out entry by entry rather than generated, so a
# reviewer reads the exact set of paths this tool can ever point pytest at.
#
# The four backend layers carry the drafted CAP-011 shape verbatim: cwd
# `backend`, config `backend/pyproject.toml`, and `--rootdir`/`--confcutdir`
# both `backend` — the integration suite's own `conftest.py` sits below that
# cut and still loads, while every ancestor conftest/ini is out of reach.
SUITES: dict[str, Suite] = {
    "backend-unit": Suite(
        target="backend/tests/unit",
        is_dir=True,
        cwd="backend",
        config="backend/pyproject.toml",
        rootdir="backend",
        confcutdir="backend",
    ),
    "backend-component": Suite(
        target="backend/tests/component",
        is_dir=True,
        cwd="backend",
        config="backend/pyproject.toml",
        rootdir="backend",
        confcutdir="backend",
    ),
    "backend-contract": Suite(
        target="backend/tests/contract",
        is_dir=True,
        cwd="backend",
        config="backend/pyproject.toml",
        rootdir="backend",
        confcutdir="backend",
    ),
    "backend-integration": Suite(
        target="backend/tests/integration",
        is_dir=True,
        cwd="backend",
        config="backend/pyproject.toml",
        rootdir="backend",
        confcutdir="backend",
    ),
    # Single file, not a directory: the GOV-01-R02 idempotency-contract lint's
    # own focused tests. `--confcutdir` is the file's own directory, so neither
    # `tools/` nor the repository root can contribute a conftest.
    "idempotency-contract": Suite(
        target="tools/tests/test_validate_idempotency_contract.py",
        is_dir=False,
        cwd=".",
        config="backend/pyproject.toml",
        rootdir=".",
        confcutdir="tools/tests",
    ),
}


def _canonical(root: Path, rel: str) -> Path:
    """Resolve `rel` under `root`, refusing a symlink in any component.

    Checked component by component on the way down, because `Path.resolve()`
    alone would quietly *follow* a symlink and hand back a path that looks
    well-behaved. The post-resolve equality is a second, independent statement
    that nothing was followed.
    """
    if rel == ".":
        return root
    parts = rel.split("/")
    if any(part in ("", ".", "..") for part in parts) or rel.startswith("/"):
        raise Denied(f"unsafe relative path in the fixed suite table: {rel!r}")
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise Denied(f"symlink refused in the path to the suite: {rel} (at {part!r})")
    resolved = current.resolve()
    if resolved != current:
        raise Denied(f"{rel} does not canonicalise to itself ({resolved}): refusing")
    if root not in resolved.parents:
        raise Denied(f"{rel} resolves outside the repository root: {resolved}")
    return resolved


def _assert_suite_usable(target: Path, suite: Suite, name: str) -> int:
    """Require a present, symlink-free, non-empty suite. Returns the file count."""
    if not suite.is_dir:
        if not target.is_file():
            raise Denied(f"suite {name!r} names a missing file: {suite.target}")
        return 1
    if not target.is_dir():
        raise Denied(f"suite {name!r} names a missing directory: {suite.target}")
    collected = 0
    for entry in sorted(target.rglob("*")):
        # `rglob` does not recurse through a symlinked directory, but it does
        # yield the link itself, which is what gets refused here.
        if entry.is_symlink():
            raise Denied(
                f"symlink inside suite {name!r}: {entry.relative_to(target)} — a "
                f"symlinked test or package can execute code from outside the suite"
            )
        if entry.is_file() and entry.name.startswith("test_") and entry.suffix == ".py":
            collected += 1
    if collected == 0:
        raise Denied(
            f"suite {name!r} holds no test_*.py file: an empty run reports success by "
            f"collecting nothing"
        )
    return collected


def ambient_denials(env: Mapping[str, str]) -> list[str]:
    """Inherited settings that would re-scope pytest from outside the argv.

    Denied rather than silently stripped: an environment carrying
    `PYTEST_ADDOPTS` is an environment someone configured, and quietly ignoring
    it would hide the fact that the run was not the run that was asked for.
    """
    denials = [
        f"{name} is set in the environment ({name}={env[name]!r}): an ambient pytest "
        f"override can add plugins, flags or a config this allowlist never declared"
        for name in sorted(env)
        if name.startswith("PYTEST_")
    ]
    if env.get("PYTHONPATH"):
        denials.append(
            "PYTHONPATH is set: it can place a `pytest11` entry-point plugin on the "
            "import path, so it is refused rather than inherited"
        )
    return denials


def child_env(env: Mapping[str, str]) -> dict[str, str]:
    """The child environment, built from the allowlist rather than inherited."""
    child = {name: env[name] for name in INHERITED_ENV_VARS if name in env}
    child["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return child


@dataclass(frozen=True)
class Plan:
    """A fully-canonicalised, inspectable invocation. Nothing here is a result."""

    name: str
    cwd: Path
    target: Path
    config: Path
    rootdir: Path
    confcutdir: Path
    collected_files: int

    def argv(self, python: str) -> list[str]:
        """The exact pytest argv.

        `-E` ignores every `PYTHON*` variable and `-s` drops user
        site-packages, so neither an inherited path nor a user-installed
        `pytest11` plugin can reach the run; `-B` keeps it from writing
        bytecode into the checkout. Deliberately **not** `-I`: isolated mode
        also implies `-P`, which would stop the working directory being
        prepended to `sys.path` and so change how the suites' own imports
        resolve. The two flags above carry the isolation that is wanted here
        without altering import semantics, which this session cannot test
        (doing so would mean invoking pytest on Veyro tests while CAP-011 is
        NOT APPROVED).
        """
        return [
            python,
            "-E",
            "-s",
            "-B",
            "-m",
            "pytest",
            "-c",
            str(self.config),
            f"--rootdir={self.rootdir}",
            f"--confcutdir={self.confcutdir}",
            "-p",
            "no:cacheprovider",
            "-rs",
            str(self.target),
        ]

    def as_dict(self, python: str) -> dict:
        return {
            "tool": "tools/run_scoped_pytest.py",
            "suite": self.name,
            "cwd": str(self.cwd),
            "target": str(self.target),
            "config": str(self.config),
            "rootdir": str(self.rootdir),
            "confcutdir": str(self.confcutdir),
            "test_files_in_suite": self.collected_files,
            "argv": self.argv(python),
            "child_env_keys": sorted(child_env(os.environ)),
            "capability_status": "CAP-011 QUALIFIED - NOT APPROVED; no result here is a gate",
        }


def plan(name: str, repo_root: Path | None = None, env: Mapping[str, str] | None = None) -> Plan:
    """Validate the suite and canonicalise its paths. Starts no process."""
    root = (repo_root if repo_root is not None else REPO_ROOT).resolve()
    environ = env if env is not None else os.environ
    suite = SUITES.get(name)
    if suite is None:
        raise Denied(f"unknown suite {name!r}; allowed: {sorted(SUITES)}")
    for denial in ambient_denials(environ):
        raise Denied(denial)
    target = _canonical(root, suite.target)
    collected = _assert_suite_usable(target, suite, name)
    config = _canonical(root, suite.config)
    if not config.is_file():
        raise Denied(f"explicit pytest config is missing: {suite.config}")
    return Plan(
        name=name,
        cwd=_canonical(root, suite.cwd),
        target=target,
        config=config,
        rootdir=_canonical(root, suite.rootdir),
        confcutdir=_canonical(root, suite.confcutdir),
        collected_files=collected,
    )


def classify_version(returncode: int, stdout: str) -> str | None:
    """None if the reported version is the pinned one, else the refusal reason."""
    reported = stdout.strip()
    if returncode != 0 or reported != EXPECTED_PYTEST_VERSION:
        return (
            f"pytest reported {reported!r} (rc={returncode}), expected "
            f"{EXPECTED_PYTEST_VERSION!r}: this is not the hash-installed CAP-011 pin"
        )
    return None


def classify_exit(returncode: int) -> tuple[int, str]:
    """Map a pytest rc. 4 (path not found) and 5 (nothing collected) are errors."""
    if returncode == 0:
        return EXIT_OK, "all collected tests passed"
    if returncode == 1:
        return EXIT_TEST_FAILURES, "pytest reported test failures"
    return EXIT_DENIED, f"pytest exited {returncode}: not a usable result"


def run(name: str, python: str | None = None) -> int:
    """Validate, assert the pinned pytest, then run the one allowlisted target.

    pytest's own stdout/stderr are inherited, not captured: the workflow tees
    and greps that text for its skip/passed denials, so it must pass through
    byte-for-byte.
    """
    interpreter = python or sys.executable
    current = plan(name)
    print(json.dumps(current.as_dict(interpreter), indent=2, sort_keys=True), flush=True)

    environment = child_env(os.environ)
    probe = subprocess.run(
        current.argv(interpreter)[:-1] + ["--version"],
        cwd=current.cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    reason = classify_version(probe.returncode, probe.stdout + probe.stderr)
    if reason is not None:
        raise Denied(reason)

    result = subprocess.run(
        current.argv(interpreter), cwd=current.cwd, env=environment, check=False
    )
    code, label = classify_exit(result.returncode)
    print(f"run_scoped_pytest: suite={name} rc={result.returncode} — {label}", flush=True)
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "suite",
        choices=sorted(SUITES),
        help="the allowlisted suite to run; no path argument is accepted",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="validate and print the canonicalised invocation without running pytest",
    )
    args = parser.parse_args(argv)
    try:
        if args.plan:
            print(json.dumps(plan(args.suite).as_dict(sys.executable), indent=2, sort_keys=True))
            return EXIT_OK
        return run(args.suite)
    except Denied as exc:
        print(f"DENY: {exc}", file=sys.stderr)
        return EXIT_DENIED


if __name__ == "__main__":
    raise SystemExit(main())
