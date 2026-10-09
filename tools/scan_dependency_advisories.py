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

## Declaration-consistency mode (`--check-declarations`)

Scanning the lock is only worth as much as the lock's coverage of what is
actually declared. `--check-declarations <lock> --declares <source> ...`
answers exactly one question, offline and with no advisory query at all:
**is every exactly-pinned dependency declared in those sources pinned to the
same version in the scanned lock?** A dependency added to
`backend/requirements-dev.txt` or `backend/pyproject.toml` but absent from
(or pinned differently in) `backend/requirements-dev.lock.txt` would
otherwise be installed without ever having been scanned.

This mode exits 0 (ALLOW) or 2 (DENY); exit 1 stays reserved for a validated
advisory. ALLOW requires every declaration in every named source to resolve
to an identically-versioned lock pin, with zero problems — an unreadable,
oversized, symlinked, malformed or unsupported source denies rather than
contributing zero declarations. Declaration sources are untrusted data: they
are read as bytes, never executed, imported or installed, `pyproject.toml` is
decoded with `tomllib` and nothing else, and no problem message echoes a
declaration's own text (only its path/line or its table position, plus a
NAME_RE-validated distribution name).

Deliberate limits of this mode, each a DENY rather than a guess: only
`name==version` and `name[extras]==version` forms are accepted (a range,
marker, direct URL, prefix pin, pip directive or line continuation is an
UNSUPPORTED_DECLARATION); comparison is exact string equality on the version,
so a declaration and a lock pin that differ only in PEP 440 spelling deny;
only `[project.dependencies]`, `[project.optional-dependencies.*]`,
`[dependency-groups.*]` and `[build-system.requires]` are read, and a
dependency key anywhere else in the TOML is an UNSUPPORTED_DECLARATION_SITE;
dynamic dependency metadata denies. The check is one-directional by design —
the lock is expected to be a superset (it carries the transitive closure), so
a lock pin with no declaration is not a problem. An extras marker is checked
against its base distribution's pin only: `psycopg[binary]==3.3.6` requires
`psycopg==3.3.6` in the lock, and the extra's own transitive distributions are
covered only in that they, too, must be pinned in the lock to be installed by
`--require-hashes`.

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

try:  # `tomllib` is stdlib from 3.11; keep this module importable on 3.10.
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - only reachable on Python 3.10
    tomllib = None  # type: ignore[assignment]

OSV_QUERY_URL = "https://api.osv.dev/v1/query"
ECOSYSTEM = "PyPI"
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_TIMEOUT_SECONDS = 120.0
MAX_RESPONSE_BYTES = 1_048_576  # 1 MiB; an OSV query answer is orders smaller.
MAX_ADVISORIES_PER_PACKAGE = 256
# Bounds for `--check-declarations`. A declaration source is a hand-maintained
# intent file; anything past these bounds is refused rather than parsed.
MAX_DECLARATION_SOURCE_BYTES = 262_144
MAX_DECLARATIONS = 512
MAX_TOML_DEPTH = 12
# TOML keys that declare dependencies. Finding one outside the four sites this
# mode reads is a DENY, not a silent skip.
DEPENDENCY_KEY_NAMES = frozenset(
    {"dependencies", "optional-dependencies", "dev-dependencies", "requires", "requires-dist"}
)

# PEP 503-shaped distribution name, bounded length.
NAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]{0,62}[A-Za-z0-9])?$")
# Deliberately narrower than PEP 440: no whitespace, comma, or comparison
# operator can survive it, so an unpinned or multi-specifier requirement
# cannot be mistaken for an exact version.
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.!+-]{0,63}$")
HASH_LINE_RE = re.compile(r"^--hash=sha256:([0-9a-f]{64})$")
# The only declaration form `--check-declarations` accepts: an exact `==` pin,
# optionally carrying extras. Deliberately whitespace-free, so a marker
# (`; python_version < "3.13"`), a direct reference (`name @ url`), a range, a
# multi-specifier or a prefix pin (`==1.2.*`) cannot match and must deny.
PINNED_REQUIREMENT_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9](?:[A-Za-z0-9._-]{0,62}[A-Za-z0-9])?)"
    r"(?:\[(?P<extras>[A-Za-z0-9][A-Za-z0-9._,-]{0,126})\])?"
    r"==(?P<version>[A-Za-z0-9][A-Za-z0-9.!+-]{0,63})$"
)
# pip's own inline-comment rule: a `#` preceded by whitespace.
INLINE_COMMENT_RE = re.compile(r"\s+#.*$")
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


class Declaration(NamedTuple):
    """One exactly-pinned dependency declaration read from an intent source.

    `site` is a location label only (`<path>:<line>`, or `<path>
    [project.dependencies][0]`) — never the declaration's own text.
    """

    site: str
    name: str
    version: str


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


def normalize_name(name: str) -> str:
    """PEP 503 normalized name — the key the PyPI advisory corpus is indexed
    under. OSV answers an unknown name and a package with no advisories with
    the same empty body, so a non-normalized query must never be relied on to
    be normalized upstream. Reports keep the lock's own spelling."""
    return re.sub(r"[-_.]+", "-", name).lower()


# --- Declaration-consistency mode ------------------------------------------
# Closes the gap where a dependency declared in an intent file but absent from
# (or differently pinned in) the scanned lock would be installed unscanned.


def _parse_pin(text: str) -> tuple[str, str] | None:
    """Returns (name, version) for an exact `name[extras]==version` pin, or
    None for every other form. None is always a DENY at the call site: a form
    this function does not recognise cannot be shown to be covered by the
    lock, and guessing at it is exactly what a gate must not do."""
    match = PINNED_REQUIREMENT_RE.match(text)
    if match is None:
        return None
    extras = match.group("extras")
    if extras is not None:
        parts = extras.split(",")
        if not all(NAME_RE.match(part) for part in parts):
            return None
    return match.group("name"), match.group("version")


def _safe_key(key: str) -> str:
    """TOML keys are untrusted text, so only a NAME_RE-shaped key is echoed."""
    return key if NAME_RE.match(key) else "<non-conforming-key>"


def _read_source(path: Path) -> tuple[str | None, str | None]:
    """Reads one declaration source as bounded UTF-8 text. Returns
    (text, problem); exactly one of the two is None. A symlink is refused here
    as well as by the workflow's blob-mode screen — this function must be safe
    to call on any path, not only on one already screened."""
    try:
        if path.is_symlink():
            return None, (
                f"{path}: REFUSED_SYMLINK_SOURCE — a declaration source must be a "
                f"regular file, so its contents cannot be redirected elsewhere"
            )
        size = path.stat().st_size
    except FileNotFoundError:
        return None, (
            f"{path}: MISSING_DECLARATION_SOURCE — the named declaration source "
            f"does not exist, so its declarations are unknown"
        )
    except OSError as exc:
        return None, (
            f"{path}: UNREADABLE_DECLARATION_SOURCE — the declaration source could "
            f"not be inspected ({type(exc).__name__})"
        )
    if size > MAX_DECLARATION_SOURCE_BYTES:
        return None, (
            f"{path}: DECLARATION_SOURCE_TOO_LARGE — larger than "
            f"{MAX_DECLARATION_SOURCE_BYTES} bytes and was not parsed"
        )
    try:
        return path.read_text(encoding="utf-8"), None
    except (OSError, UnicodeDecodeError) as exc:
        return None, (
            f"{path}: UNREADABLE_DECLARATION_SOURCE — not readable as UTF-8 "
            f"({type(exc).__name__}), so its declarations are unknown"
        )


def parse_requirements_declarations(path: Path) -> tuple[list[Declaration], list[str]]:
    """Reads exact pins from a requirements-style intent file.

    Comments (whole-line and pip's whitespace-then-`#` inline form) and blank
    lines are skipped. Every other line must be an exact
    `name[extras]==version` pin: a pip directive (`-r`, `-e`, `--index-url`,
    `--hash=`), a line continuation, a range, a marker, a direct URL or a
    prefix pin is a named problem, never a tolerated variation.
    """
    text, problem = _read_source(path)
    if problem is not None or text is None:
        return [], [problem] if problem is not None else []

    declarations: list[Declaration] = []
    problems: list[str] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            problems.append(
                f"{path}:{number}: UNSUPPORTED_DECLARATION — a line continuation; an "
                f"intent file this gate reads must declare one exact pin per line"
            )
            continue
        line = INLINE_COMMENT_RE.sub("", line).strip()
        if not line:
            continue
        pin = _parse_pin(line)
        if pin is None:
            problems.append(
                f"{path}:{number}: UNSUPPORTED_DECLARATION — not an exact "
                f"'name[extras]==version' pin; pip directives, ranges, markers, "
                f"direct references and prefix pins are refused because the lock "
                f"cannot be shown to cover what they resolve to"
            )
            continue
        declarations.append(Declaration(f"{path}:{number}", pin[0], pin[1]))
    return declarations, problems


def _is_handled_site(trail: tuple[str, ...]) -> bool:
    """The four TOML sites this mode reads. Everything else that declares
    dependencies is an UNSUPPORTED_DECLARATION_SITE."""
    if trail in (
        ("project", "dependencies"),
        ("project", "optional-dependencies"),
        ("build-system", "requires"),
    ):
        return True
    if len(trail) == 2 and trail[0] == "dependency-groups":
        return True
    return len(trail) == 3 and trail[:2] == ("project", "optional-dependencies")


def _unsupported_declaration_sites(path: Path, data: object) -> list[str]:
    """Walks the whole decoded document and reports any dependency-declaring
    key outside the four handled sites. This is what makes the mode fail
    closed against a declaration route it was never taught to read."""
    problems: list[str] = []

    def walk(node: object, trail: tuple[str, ...]) -> None:
        if len(trail) > MAX_TOML_DEPTH:
            problems.append(
                f"{path}: MALFORMED_PYPROJECT — table nesting deeper than "
                f"{MAX_TOML_DEPTH} was not inspected"
            )
            return
        if not isinstance(node, dict):
            return
        for key in sorted(node):
            if not isinstance(key, str):
                continue
            here = trail + (key,)
            if key in DEPENDENCY_KEY_NAMES and not _is_handled_site(here):
                label = ".".join(_safe_key(part) for part in here)
                problems.append(
                    f"{path} [{label}]: UNSUPPORTED_DECLARATION_SITE — this gate "
                    f"reads declarations only from [project.dependencies], "
                    f"[project.optional-dependencies.*], [dependency-groups.*] and "
                    f"[build-system.requires]; a dependency declared anywhere else "
                    f"cannot be shown to be covered by the scanned lock"
                )
            walk(node[key], here)

    walk(data, ())
    return problems


def parse_pyproject_declarations(path: Path) -> tuple[list[Declaration], list[str]]:
    """Reads exact pins from a `pyproject.toml` intent file.

    The file is decoded with `tomllib` and nothing else — never imported,
    executed or evaluated. Only the four sites `_is_handled_site` names are
    read; dynamic dependency metadata and any dependency key elsewhere deny.
    """
    text, problem = _read_source(path)
    if problem is not None or text is None:
        return [], [problem] if problem is not None else []
    if tomllib is None:  # pragma: no cover - only reachable on Python 3.10
        return [], [
            (
                f"{path}: TOML_SUPPORT_UNAVAILABLE — this interpreter has no 'tomllib' "
                f"(Python 3.11+), so the declarations in this file cannot be read and "
                f"the lock cannot be shown to cover them"
            )
        ]
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError, RecursionError) as exc:
        return [], [
            (
                f"{path}: MALFORMED_PYPROJECT — not decodable as TOML "
                f"({type(exc).__name__}), so its declarations are unknown"
            )
        ]

    declarations: list[Declaration] = []
    problems: list[str] = []

    def collect(items: object, site: str) -> None:
        if items is None:
            return
        if not isinstance(items, list):
            problems.append(
                f"{path} {site}: MALFORMED_PYPROJECT — expected an array of "
                f"dependency strings"
            )
            return
        for position, item in enumerate(items):
            where = f"{path} {site}[{position}]"
            if not isinstance(item, str):
                problems.append(
                    f"{where}: MALFORMED_PYPROJECT — a non-string dependency entry "
                    f"(a PEP 735 include-group or table form is not read here)"
                )
                continue
            pin = _parse_pin(item.strip())
            if pin is None:
                problems.append(
                    f"{where}: UNSUPPORTED_DECLARATION — not an exact "
                    f"'name[extras]==version' pin; ranges, markers, direct "
                    f"references and prefix pins are refused because the lock "
                    f"cannot be shown to cover what they resolve to"
                )
                continue
            declarations.append(Declaration(where, pin[0], pin[1]))

    def table(node: object, name: str, site: str) -> dict | None:
        value = node.get(name) if isinstance(node, dict) else None
        if value is None:
            return None
        if not isinstance(value, dict):
            problems.append(f"{path} {site}: MALFORMED_PYPROJECT — expected a table")
            return None
        return value

    project = table(data, "project", "[project]")
    if project is not None:
        collect(project.get("dependencies"), "[project.dependencies]")
        optional = table(project, "optional-dependencies", "[project.optional-dependencies]")
        for extra in sorted(optional or {}):
            collect(optional[extra], f"[project.optional-dependencies.{_safe_key(extra)}]")
        dynamic = project.get("dynamic")
        if isinstance(dynamic, list) and any(
            isinstance(item, str) and item in ("dependencies", "optional-dependencies")
            for item in dynamic
        ):
            problems.append(
                f"{path}: DYNAMIC_DEPENDENCIES — dependencies are declared dynamically, "
                f"so what gets installed is not statically readable from this file and "
                f"the lock cannot be shown to cover it"
            )
    groups = table(data, "dependency-groups", "[dependency-groups]")
    for group in sorted(groups or {}):
        collect(groups[group], f"[dependency-groups.{_safe_key(group)}]")
    build_system = table(data, "build-system", "[build-system]")
    if build_system is not None:
        collect(build_system.get("requires"), "[build-system.requires]")

    problems.extend(_unsupported_declaration_sites(path, data))
    return declarations, problems


def check_declarations(
    lockfile: Path,
    sources: list[Path],
    emit: Callable[[str], None] = print,
) -> int:
    """Verifies the lock covers every exact pin declared in `sources`.

    Returns 0 (ALLOW) or 2 (DENY) — exit 1 stays reserved for a validated
    advisory. No network request is made and no declaration source is
    executed, imported or installed. ALLOW is a positive equality (every
    declaration resolved to an identically-versioned lock pin, zero problems),
    so a future loop that skipped a declaration fails closed instead of
    passing on a short list.
    """
    emit("=" * 70)
    emit("MOD-001 LOCK/INTENT DECLARATION CONSISTENCY (GOV-01-R04, SCN-MOD001-094)")
    emit("=" * 70)
    emit(f"lockfile: {lockfile}")
    emit(f"declaration sources: {len(sources)}")

    problems: list[str] = []
    entries, lock_problems = parse_lock(lockfile)
    problems.extend(lock_problems)
    locked: dict[str, LockEntry] = {}
    for entry in entries:
        key = normalize_name(entry.name)
        if key in locked:
            problems.append(
                f"{lockfile}: DUPLICATE_LOCK_ENTRY — two pins normalize to the same "
                f"PEP 503 name, so which version the gate scanned for it is ambiguous"
            )
            continue
        locked[key] = entry
    emit(f"packages pinned: {len(locked)}")
    if problems:
        for problem in sorted(set(problems)):
            emit(f"problem: {problem}")
        emit(
            f"RESULT: DENY — {len(set(problems))} lock problem(s); no declaration "
            f"was checked"
        )
        return 2

    declarations: list[Declaration] = []
    for source in sources:
        suffix = source.suffix.lower()
        if suffix == ".toml":
            found, source_problems = parse_pyproject_declarations(source)
        elif suffix == ".txt":
            found, source_problems = parse_requirements_declarations(source)
        else:
            found, source_problems = [], [
                (
                    f"{source}: UNSUPPORTED_DECLARATION_SOURCE — only a '.txt' "
                    f"requirements file or a '.toml' pyproject file is read by this mode"
                )
            ]
        declarations.extend(found)
        problems.extend(source_problems)
        emit(f"{source}: {len(found)} exact pin(s), {len(source_problems)} problem(s)")

    if len(declarations) > MAX_DECLARATIONS:
        problems.append(
            f"TOO_MANY_DECLARATIONS — {len(declarations)} declarations exceed the "
            f"{MAX_DECLARATIONS} this check compares"
        )

    matched = 0
    for declaration in declarations:
        entry = locked.get(normalize_name(declaration.name))
        if entry is None:
            problems.append(
                f"{declaration.site}: UNLOCKED_DECLARATION — '{declaration.name}' is "
                f"declared here but is not pinned in the scanned lock, so the gate "
                f"never queried an advisory for the version that would be installed"
            )
            continue
        if entry.version != declaration.version:
            problems.append(
                f"{declaration.site}: DECLARATION_VERSION_MISMATCH — '{declaration.name}' "
                f"is declared at a version the lock does not pin, so the version "
                f"installed from this declaration is not the version scanned (values "
                f"withheld from this report by design)"
            )
            continue
        matched += 1

    for problem in sorted(set(problems)):
        emit(f"problem: {problem}")
    if problems:
        emit(
            f"RESULT: DENY — {len(set(problems))} declaration problem(s); the lock "
            f"cannot be shown to cover every declared dependency"
        )
        return 2
    if matched != len(declarations):
        emit(
            f"RESULT: DENY — INCOMPLETE_DECLARATION_COVERAGE: {matched} of "
            f"{len(declarations)} declaration(s) were resolved against the lock"
        )
        return 2
    emit(
        f"RESULT: ALLOW — {matched} declaration(s) across {len(sources)} source(s), "
        f"every one pinned at the same version in the scanned lock"
    )
    return 0


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
        {
            "package": {"name": normalize_name(entry.name), "ecosystem": ECOSYSTEM},
            "version": entry.version,
        }
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
    parser.add_argument(
        "--check-declarations",
        action="store_true",
        help=(
            "Declaration-consistency mode: instead of querying advisories, verify "
            "that every exact pin declared in each --declares source is pinned to "
            "the same version in the lock file. Exit 0 ALLOW, 2 DENY; makes no "
            "network request."
        ),
    )
    parser.add_argument(
        "--declares",
        action="append",
        default=[],
        metavar="PATH",
        help=(
            "A dependency-intent source to check against the lock (repeatable). A "
            "'.txt' path is read as a requirements file, a '.toml' path as a "
            "pyproject file; any other suffix denies. Only read in "
            "--check-declarations mode."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, fetcher: Fetcher = _urllib_fetcher) -> int:
    args = parse_args(argv)
    if args.check_declarations:
        return check_declarations(args.lockfile, [Path(source) for source in args.declares])
    if args.declares:
        # Never silently ignore a named declaration source: a caller that meant
        # to check one and got an advisory scan instead would read a green
        # result as consistency evidence it never produced.
        print(
            "problem: BAD_USAGE — --declares is only read in --check-declarations "
            "mode; refusing to ignore a named declaration source"
        )
        print("RESULT: DENY — BAD_USAGE")
        return 2
    return run_scan(args.lockfile, fetcher=fetcher, timeout=args.timeout)


if __name__ == "__main__":
    sys.exit(main())
