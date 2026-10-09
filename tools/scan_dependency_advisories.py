#!/usr/bin/env python3
"""
Fail-closed dependency-advisory scanner (MOD-001, GOV-01-R03/GOV-01-R04 —
the "vulnerability" CI stage; input to SCN-MOD001-094).

Route decision:
`knowledge/03-Modules/MOD-001/evidence/implementation/
M1-C-06-SCANNER-CAPABILITY-ROUTE-2026-10-09.md` §3.2 selected a
project-authored stdlib client over `pip-audit` (the named, pre-reasoned
fallback) because dependency scanning is a data-lookup problem: the quality
lives in the advisory database, not in the client, and OSV supplies the CVE
alias SCN-MOD001-094 requires the gate to cite. `M1-C-06-CAP-ORDERING-PLAN-
DECISION-2026-10-09.md` §3 narrows that to its honest form — this file is
project source, governed by `CAPABILITY_POLICY.md` like the eight
`tools/validate_*.py` gate scripts, but it is not a third-party executable,
so it triggers no acquisition-provenance review and claims no exemption. Its
assurance rides the planned shared material-code review, which has not
happened: **nothing here is an independent security assurance, a CI result,
or a scenario PASS.**

## What it does

Reads one explicitly-named requirements lock file in the exact shape
`tools/generate_requirements_lock.py` writes, queries the free OSV API once
per pinned package, and denies on any validated advisory.

## Both inputs are untrusted

The lock file and every OSV response are untrusted input. Neither is ever
executed, `eval`'d or imported — the response is parsed with `json.loads`
and nothing else. Only two classes of response-derived value are ever
echoed: an advisory ID matching `ADVISORY_ID_RE` and a CVE alias matching
`CVE_RE`. Every other field (`summary`, `details`, `references`, `affected`,
…) is never read and never printed; anything rejected is reported as a
count, never as its value. That is the BUG-055 value-free-report discipline
applied to a second untrusted source.

## Fail-closed contract — a clean result must be positively established

ALLOW (exit 0) requires **all** of: at least one pinned package parsed from
the lock; one valid, well-shaped, advisory-free response recorded for
**every** parsed package; and zero problems of any kind. Silence, an empty
response body, an unparsed package, or "no rows" is never a pass — a
dependency scanner that passes while offline is worse than none.

Exit codes (stable):

  0  ALLOW   — every queried package returned a valid empty advisory result.
  1  DENY    — at least one validated advisory (VULNERABILITY_ADVISORY_PRESENT).
  2  DENY    — the clean result could not be established at all: lock absent,
               unreadable, empty, malformed or unpinned; network failure,
               non-200, oversized or malformed response; missing/invalid
               advisory-source data; incomplete coverage; bad usage.

Precedence when both occur: a detected advisory wins (exit 1), so a decisive
vulnerability is never downgraded to a transport-error code. Exit 2 is
reserved for "no advisory detected **and** clean could not be established".
Both are nonzero, so neither path can produce a false clean.

## Scope limits (deliberate)

PyPI ecosystem only, `name==version` pins only, one advisory source, no
caching, no retries, no severity policy, no allowlist/ignore file, no
fixed-version suggestion. Those are absent because the control is a gate,
not a framework; add one only when a scenario actually requires it.

This tool never writes to the checked tree, never installs a package, and
has no default lock path — the lock file is a required argument precisely so
that no invocation can drift onto the real lock by omission.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

OSV_QUERY_URL = "https://api.osv.dev/v1/query"
ECOSYSTEM = "PyPI"
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_TIMEOUT_SECONDS = 120.0
MAX_RESPONSE_BYTES = 1_048_576  # 1 MiB; an OSV query answer is orders smaller.
MAX_ADVISORIES_PER_PACKAGE = 256

# PEP 503-shaped distribution name, bounded length.
NAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]{0,62}[A-Za-z0-9])?$")
# Deliberately narrower than PEP 440: no whitespace, comma, or comparison
# operator can survive it, so an unpinned or multi-specifier requirement
# cannot be mistaken for an exact version.
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.!+-]{0,63}$")
HASH_LINE_RE = re.compile(r"^--hash=sha256:([0-9a-f]{64})$")
# OSV advisory IDs: GHSA-xxxx-xxxx-xxxx, PYSEC-2021-123, CVE-2019-1234, …
ADVISORY_ID_RE = re.compile(r"^[A-Z]{2,10}-[0-9A-Za-z]{1,16}(?:-[0-9A-Za-z]{1,16}){0,4}$")
CVE_RE = re.compile(r"^CVE-[0-9]{4}-[0-9]{4,19}$")

CLEAN = "clean"
VULNERABLE = "vulnerable"
ERROR = "error"


class LockEntry(NamedTuple):
    """One exactly-pinned package parsed from the lock file."""

    name: str
    version: str
    sha256: str


class Advisory(NamedTuple):
    """A validated advisory reference. `cves` holds only CVE-shaped aliases."""

    advisory_id: str
    cves: tuple[str, ...]


class AdvisoryOutcome(NamedTuple):
    """Result of one package's advisory query.

    `problem` is set if and only if `kind` is ERROR; `advisories` is non-empty
    if and only if `kind` is VULNERABLE. `ignored_alias_count` is a count, not
    a list of values — unrecognised alias text is never echoed.
    """

    kind: str
    advisories: tuple[Advisory, ...]
    problem: str | None
    ignored_alias_count: int


class FetchResult(NamedTuple):
    """What a fetcher returns: an HTTP status and at most
    MAX_RESPONSE_BYTES + 1 bytes of body (the extra byte is what makes an
    oversized response detectable rather than silently truncated)."""

    status: int
    body: bytes


Fetcher = Callable[[str, bytes, float], FetchResult]


def _urllib_fetcher(url: str, payload: bytes, timeout: float) -> FetchResult:
    """The only code path in this module that touches the network. Every test
    injects a substitute, so no test performs a live request."""
    if not url.startswith("https://"):
        raise ValueError("advisory source URL must be https")
    request = urllib.request.Request(  # noqa: S310 - scheme asserted above
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return FetchResult(int(response.status), response.read(MAX_RESPONSE_BYTES + 1))


def parse_lock(path: Path) -> tuple[list[LockEntry], list[str]]:
    """Parses the lock shape `tools/generate_requirements_lock.py` writes:

        name==version \\
            --hash=sha256:<64 lowercase hex>

    Returns (entries, problems); a non-empty `problems` list means the lock
    must not be scanned at all. Comments and blank lines are skipped. Every
    package line must be exactly pinned with `==` and followed by exactly one
    valid hash line — a second hash line, a missing one, a non-`==`
    specifier, a pip directive (`-r`, `-e`, `--index-url`), an extras or
    marker suffix, or a duplicate package are all named problems rather than
    tolerated variations. A parser that guesses at an unfamiliar line cannot
    promise it scanned everything in the file.
    """
    problems: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [], [f"{path}: MISSING_LOCK — the named lock file does not exist"]
    except (OSError, UnicodeDecodeError) as exc:
        return [], [
            f"{path}: UNREADABLE_LOCK — the lock file could not be read as UTF-8 "
            f"({type(exc).__name__}), so its contents are unknown; an unreadable "
            f"lock must never report a scan"
        ]

    content: list[tuple[int, str]] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if line.endswith("\\"):
            line = line[:-1].strip()
        if not line or line.startswith("#"):
            continue
        content.append((number, line))

    entries: list[LockEntry] = []
    seen: dict[str, int] = {}
    index = 0
    while index < len(content):
        number, line = content[index]
        index += 1
        if HASH_LINE_RE.match(line) or line.startswith("--hash="):
            problems.append(
                f"{path}:{number}: MALFORMED_LOCK_ENTRY — a hash line with no "
                f"preceding pinned package line"
            )
            continue
        if line.startswith("-"):
            problems.append(
                f"{path}:{number}: MALFORMED_LOCK_ENTRY — pip directives are not "
                f"supported in a lock this gate scans; every line must be an "
                f"exact '==' pin with its own hash"
            )
            continue
        name, separator, version = line.partition("==")
        name = name.strip()
        version = version.strip()
        if not separator or not NAME_RE.match(name) or not VERSION_RE.match(version):
            problems.append(
                f"{path}:{number}: UNPINNED_LOCK_ENTRY — this line is not an exact "
                f"'name==version' pin, so the version actually installed is not "
                f"determined by the lock and no advisory query could be exact"
            )
            # Still consume a following hash line so it is not re-reported.
            if index < len(content) and HASH_LINE_RE.match(content[index][1]):
                index += 1
            continue
        if name in seen:
            problems.append(
                f"{path}:{number}: DUPLICATE_LOCK_ENTRY — '{name}' is already pinned "
                f"at line {seen[name]}; refusing to guess which pin the gate means"
            )
        if index >= len(content):
            problems.append(
                f"{path}:{number}: MALFORMED_LOCK_ENTRY — '{name}' has no following "
                f"'--hash=sha256:<64 hex>' line"
            )
            continue
        hash_number, hash_line = content[index]
        match = HASH_LINE_RE.match(hash_line)
        if match is None:
            problems.append(
                f"{path}:{hash_number}: MALFORMED_LOCK_ENTRY — expected exactly one "
                f"'--hash=sha256:<64 lowercase hex>' line after '{name}'"
            )
            continue
        index += 1
        if index < len(content) and HASH_LINE_RE.match(content[index][1]):
            problems.append(
                f"{path}:{content[index][0]}: MALFORMED_LOCK_ENTRY — '{name}' carries "
                f"more than one hash line; the generated lock shape is exactly one"
            )
            index += 1
            continue
        seen.setdefault(name, number)
        entries.append(LockEntry(name, version, match.group(1)))

    if not problems and not entries:
        problems.append(
            f"{path}: EMPTY_LOCK — no pinned package was found, so a pass would "
            f"mean nothing was scanned"
        )
    return sorted(entries), problems


def _validate_advisories(payload: object) -> AdvisoryOutcome:
    """Shape-validates one decoded OSV response. The response is data: only
    `vulns[].id` and `vulns[].aliases[]` are read at all, and only values
    matching their strict pattern are ever carried into the report."""
    if not isinstance(payload, dict):
        return AdvisoryOutcome(
            ERROR,
            (),
            "MALFORMED_ADVISORY_RESPONSE — the response body is not a JSON object",
            0,
        )
    # OSV omits 'vulns' entirely for a package with no advisories, so an
    # absent key is the normal clean answer. An explicitly null 'vulns' is
    # not: the key was answered with a non-list, which is a malformation and
    # must deny — a response shape this client does not understand can never
    # establish a clean result.
    if "vulns" not in payload:
        return AdvisoryOutcome(CLEAN, (), None, 0)
    vulns = payload["vulns"]
    if not isinstance(vulns, list):
        return AdvisoryOutcome(
            ERROR, (), "MALFORMED_ADVISORY_RESPONSE — 'vulns' is not a list", 0
        )
    if not vulns:
        return AdvisoryOutcome(CLEAN, (), None, 0)
    if len(vulns) > MAX_ADVISORIES_PER_PACKAGE:
        return AdvisoryOutcome(
            ERROR,
            (),
            f"MALFORMED_ADVISORY_RESPONSE — 'vulns' holds more than "
            f"{MAX_ADVISORIES_PER_PACKAGE} entries",
            0,
        )

    merged: dict[str, set[str]] = {}
    ignored_aliases = 0
    for position, vuln in enumerate(vulns):
        if not isinstance(vuln, dict):
            return AdvisoryOutcome(
                ERROR,
                (),
                f"MALFORMED_ADVISORY_RESPONSE — advisory at index {position} is not "
                f"a JSON object",
                0,
            )
        advisory_id = vuln.get("id")
        if not isinstance(advisory_id, str) or not ADVISORY_ID_RE.match(advisory_id):
            return AdvisoryOutcome(
                ERROR,
                (),
                f"INVALID_ADVISORY_ID — the advisory at index {position} has no "
                f"well-formed 'id', so the advisory it describes cannot be cited; "
                f"the value is withheld from this report by design",
                0,
            )
        aliases = vuln.get("aliases", [])
        if aliases in (None,):
            aliases = []
        if not isinstance(aliases, list):
            return AdvisoryOutcome(
                ERROR,
                (),
                f"MALFORMED_ADVISORY_RESPONSE — 'aliases' of the advisory at index "
                f"{position} is not a list",
                0,
            )
        cves = merged.setdefault(advisory_id, set())
        for alias in aliases:
            if not isinstance(alias, str):
                return AdvisoryOutcome(
                    ERROR,
                    (),
                    f"MALFORMED_ADVISORY_RESPONSE — a non-string alias in the "
                    f"advisory at index {position}",
                    0,
                )
            if CVE_RE.match(alias):
                cves.add(alias)
            else:
                ignored_aliases += 1
        if CVE_RE.match(advisory_id):
            cves.add(advisory_id)

    advisories = tuple(
        Advisory(advisory_id, tuple(sorted(merged[advisory_id])))
        for advisory_id in sorted(merged)
    )
    return AdvisoryOutcome(VULNERABLE, advisories, None, ignored_aliases)


def query_package(
    entry: LockEntry,
    fetcher: Fetcher,
    timeout: float,
    url: str = OSV_QUERY_URL,
) -> AdvisoryOutcome:
    """One bounded advisory query for one pinned package. Every failure mode —
    transport, status, size, encoding, JSON, shape — is a named ERROR outcome;
    none of them can produce CLEAN."""
    payload = json.dumps(
        {"package": {"name": entry.name, "ecosystem": ECOSYSTEM}, "version": entry.version}
    ).encode("utf-8")
    try:
        result = fetcher(url, payload, timeout)
    except urllib.error.HTTPError as exc:
        # Only the numeric status is echoed; the error body is server-controlled.
        return AdvisoryOutcome(
            ERROR,
            (),
            f"ADVISORY_SOURCE_HTTP_STATUS — the advisory source answered HTTP "
            f"{int(exc.code)}, so no advisory data was obtained",
            0,
        )
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return AdvisoryOutcome(
            ERROR,
            (),
            f"ADVISORY_SOURCE_UNREACHABLE — the advisory source could not be "
            f"queried ({type(exc).__name__}); an unreachable advisory source is "
            f"never a clean result",
            0,
        )
    except Exception as exc:  # noqa: BLE001 - fail closed with the class named
        return AdvisoryOutcome(
            ERROR,
            (),
            f"ADVISORY_SOURCE_UNREACHABLE — unexpected {type(exc).__name__} while "
            f"querying the advisory source",
            0,
        )

    if not isinstance(result, FetchResult) or not isinstance(result.body, bytes):
        return AdvisoryOutcome(
            ERROR, (), "MALFORMED_ADVISORY_RESPONSE — the fetcher returned no body", 0
        )
    if result.status != 200:
        return AdvisoryOutcome(
            ERROR,
            (),
            f"ADVISORY_SOURCE_HTTP_STATUS — the advisory source answered HTTP "
            f"{result.status}, not 200, so no advisory data was obtained",
            0,
        )
    if len(result.body) > MAX_RESPONSE_BYTES:
        return AdvisoryOutcome(
            ERROR,
            (),
            f"ADVISORY_RESPONSE_TOO_LARGE — the response exceeded "
            f"{MAX_RESPONSE_BYTES} bytes and was not parsed",
            0,
        )
    try:
        decoded = json.loads(result.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return AdvisoryOutcome(
            ERROR,
            (),
            f"MALFORMED_ADVISORY_RESPONSE — the response body is not UTF-8 JSON "
            f"({type(exc).__name__})",
            0,
        )
    return _validate_advisories(decoded)


def decide(
    entry_count: int, clean_count: int, findings: list[str], errors: list[str]
) -> tuple[int, str]:
    """Pure verdict function: the only place an exit code is chosen.

    ALLOW is expressed as a positive equality — every pinned package produced
    a valid empty result — rather than as the absence of problems, so a future
    loop that skipped a package would fail closed as
    `INCOMPLETE_ADVISORY_COVERAGE` instead of passing on a short result list.
    A detected advisory takes precedence over a coverage/transport problem so
    a decisive finding is never downgraded to exit 2.
    """
    unique_findings = sorted(set(findings))
    unique_errors = sorted(set(errors))
    if unique_findings:
        return 1, f"DENY — {len(unique_findings)} validated advisory finding(s)"
    if unique_errors:
        return 2, f"DENY — {len(unique_errors)} problem(s); clean not established"
    if entry_count <= 0 or clean_count != entry_count:
        return 2, (
            f"DENY — INCOMPLETE_ADVISORY_COVERAGE: {clean_count} valid empty "
            f"result(s) for {entry_count} pinned package(s); a clean result must "
            f"be established for every package, never inferred from no rows"
        )
    return 0, f"ALLOW — {entry_count} package(s), every one a valid empty result"


def run_scan(
    lockfile: Path,
    fetcher: Fetcher = _urllib_fetcher,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    url: str = OSV_QUERY_URL,
    emit: Callable[[str], None] = print,
) -> int:
    """The one authoritative scan pass. Returns this module's exit code."""
    emit("=" * 70)
    emit("MOD-001 DEPENDENCY ADVISORY SCAN (GOV-01-R03/R04, SCN-MOD001-094 input)")
    emit("=" * 70)
    emit(f"lockfile: {lockfile}")
    emit(f"advisory source: {url} (ecosystem {ECOSYSTEM})")

    if not isinstance(timeout, float | int) or not 0 < timeout <= MAX_TIMEOUT_SECONDS:
        emit(f"problem: INVALID_TIMEOUT — timeout must be >0 and <={MAX_TIMEOUT_SECONDS}")
        emit("RESULT: DENY — INVALID_TIMEOUT")
        return 2

    entries, problems = parse_lock(lockfile)
    emit(f"packages pinned: {len(entries)}")
    if problems:
        for problem in problems:
            emit(f"problem: {problem}")
        emit(f"RESULT: DENY — {len(problems)} lock problem(s); nothing was queried")
        return 2

    findings: list[str] = []
    errors: list[str] = []
    clean_count = 0
    for entry in entries:
        outcome = query_package(entry, fetcher, timeout, url)
        if outcome.kind == ERROR:
            assert outcome.problem is not None  # AdvisoryOutcome's own invariant
            errors.append(f"{entry.name}=={entry.version}: {outcome.problem}")
            emit(f"{entry.name}=={entry.version}: ERROR")
            continue
        if outcome.kind == VULNERABLE:
            for advisory in outcome.advisories:
                cited = ", ".join(advisory.cves) if advisory.cves else "no CVE alias"
                findings.append(
                    f"{entry.name}=={entry.version}: VULNERABILITY_ADVISORY_PRESENT — "
                    f"{advisory.advisory_id} ({cited})"
                )
            emit(
                f"{entry.name}=={entry.version}: ADVISORY "
                f"({len(outcome.advisories)} advisory/advisories, "
                f"{outcome.ignored_alias_count} non-CVE alias value(s) ignored)"
            )
            continue
        clean_count += 1
        emit(f"{entry.name}=={entry.version}: CLEAN (valid empty advisory result)")

    for finding in sorted(set(findings)):
        emit(f"finding: {finding}")
    for error in sorted(set(errors)):
        emit(f"problem: {error}")

    code, verdict = decide(len(entries), clean_count, findings, errors)
    emit(f"RESULT: {verdict}")
    return code


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fail-closed dependency-advisory scanner (MOD-001 GOV-01-R03/R04). "
            "Queries the OSV API once per exactly-pinned package in the named lock "
            "file and denies on any validated advisory. Exit 0 ALLOW, 1 advisory "
            "found, 2 clean could not be established."
        )
    )
    parser.add_argument(
        "lockfile",
        type=Path,
        help=(
            "Path to the requirements lock file to scan. Required and never "
            "defaulted, so no invocation can drift onto the real project lock."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Per-query timeout in seconds (default {DEFAULT_TIMEOUT_SECONDS}).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, fetcher: Fetcher = _urllib_fetcher) -> int:
    args = parse_args(argv)
    return run_scan(args.lockfile, fetcher=fetcher, timeout=args.timeout)


if __name__ == "__main__":
    sys.exit(main())
