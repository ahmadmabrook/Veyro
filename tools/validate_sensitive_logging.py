"""
Sensitive-logging lint (MOD-001, GOV-01-R03/R04 — the card's mandatory
Security-scope baseline control "sensitive logging"; SCN-MOD001-122).

Per `REQUIREMENTS.md`'s own "Sensitive-logging lint" row (added Scenario
Review round 6, P1-1), the obligation is: "No secret/PII-shaped pattern in
log statements — a real, buildable static check, distinct from SCN-029's
secret-scanning (which scans committed files, not log statements)", with
`IMPLEMENTATION.md` §3 naming the expected output as a "Named file/line +
secret- or PII-pattern-class report". `IMPLEMENTATION.md` §6 lists it among
MOD-001's *own* implementation obligations (not a harness deferred to a
later module). The upstream authority both files cite is the card's
Security-scope baseline (`EIP_MIRROR.md` lines 4267-4271); this module was
built from those two project files, which is why the baseline is cited
here secondhand rather than quoted.

## What makes this a log-statement lint and not a file-content scan

The distinction from SCN-029 secret-scanning is load-bearing, so this tool
never scans raw file text. It parses each `*.py` file with `ast` (stdlib)
and inspects **only the argument expressions of calls it has identified as
log statements** — a call `<receiver>.<level>(...)` where `<level>` is one
of debug/info/warning/warn/error/exception/critical/fatal/log and the
receiver's trailing identifier contains "log" (`logger`, `self.log`,
`logging.getLogger(__name__)`, `structlog.get_logger()`, `audit_log`).
A secret-shaped constant sitting in a module-level assignment, a docstring,
or a test fixture string is therefore *not* a finding here — that is
SCN-029's scope, and overlapping the two would make both reports
unreadable.

Within those argument expressions the tool reports two pattern classes:

  * `SECRET_SHAPED` — a credential-shaped string constant (private-key
    block, AWS access key id, `sk-`/`gh*_`/`xox*-` prefixed token, JWT, or
    a generic opaque token: 20+ alphanumerics containing both a letter and
    a digit), or a credential-named identifier interpolated into the log
    text (`password`, `secret`, `token`, `api_key`, `client_secret`,
    `authorization`, ...).
  * `PII_SHAPED` — an email-address string constant, or a PII-named
    identifier interpolated into the log text (`email`, `phone`, `ssn`,
    `national_id`, `date_of_birth`, `first_name`, ...).

Both the lazy-`%s` form (`logger.info("user %s", user.email)`) and the
f-string form (`logger.info(f"user {user.email}")`) are covered by the same
single rule, because in both cases the offending identifier appears as a
`Name`/`Attribute` node inside the call's arguments.

## The pre-redacted positive

A log statement that passes an already-redacted value is not a finding.
Two mechanisms, both deliberate and narrow:

  1. A redaction-marked identifier (`redacted_email`, `email_hash`,
     `masked_phone`, `token_fingerprint`) does not match, because the
     marker is checked before the sensitive-name rules.
  2. A call whose callee is redaction-marked (`redact(user.email)`,
     `mask_token(t)`) is skipped **together with its whole argument
     subtree** — the sensitive identifier inside it is never reached.

A literal placeholder (`"[REDACTED]"`, `"***"`, `EXAMPLE_NOT_A_REAL_KEY`
per `.claude/rules/infra/secrets.md`) passes by construction: the generic
opaque-token rule requires 20+ *alphanumerics* containing at least one
digit, which no such placeholder satisfies.

## Its own diagnostics do not echo the secret

Every literal match is masked in the report (first 3 characters plus a
length) rather than printed. A lint whose denial message republishes the
credential it found into a CI log has moved the leak, not closed it.

## Fail-closed rule

"Cannot inspect" always resolves to deny, never to "assume clean":
an unreadable or undecodable file is `UNREADABLE_SOURCE_FILE`, a file
`ast` cannot parse is `UNPARSEABLE_SOURCE_FILE`, an explicitly named path
that does not exist is `MISSING_SOURCE_PATH`, and having nothing at all to
inspect is `NO_SOURCE_FILES`. None of these is a silent skip.

Because MOD-001's tree currently contains **zero** log statements, a
default run is a true but vacuous pass. Following
`validate_migration_ordering.py`'s R1-4 precedent (every historical PASS in
that vault having been vacuous), that case prints an explicit notice, and
`--require-log-statements` converts it into a denial so future CI wiring
cannot pass green forever against a path that stopped containing code.

Deliberately dependency-free (stdlib only), matching
`validate_migration_ordering.py`'s stated "zero new dependencies"
convention and `validate_workflow_trust.py`'s structure.

## Deliberate simplifications, stated plainly

  * Receiver detection is "trailing identifier contains log", which would
    also match a `catalog`/`dialog` object that happened to expose an
    `.info()`/`.error()` method. That is the conservative direction (a
    false positive is reviewable; a missed log statement is not) and no
    such shape exists in this tree.
  * Identifier rules match on a camelCase-normalized name
    (`apiKey` -> `api_key`), not on resolved value types. This lint makes
    no attempt at dataflow: a secret assigned to a neutrally-named local
    and then logged is out of reach of any static check this cheap, and is
    the residual this tool does not claim to cover.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE_ROOTS = (REPO_ROOT / "backend", REPO_ROOT / "tools")
EXCLUDED_DIR_NAMES = frozenset(
    {".git", ".venv", "__pycache__", "node_modules", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
)

FINDING_CODE = "SENSITIVE_DATA_IN_LOG_STATEMENT"
PATTERN_CLASS_SECRET = "SECRET_SHAPED"
PATTERN_CLASS_PII = "PII_SHAPED"

NOTICE_NO_LOG_STATEMENTS = (
    "NOTICE: no log statements exist in the scanned tree yet, so this pass is "
    "true but vacuous. Pass --require-log-statements to fail closed on that case."
)

LOG_METHOD_NAMES = frozenset(
    {"debug", "info", "warning", "warn", "error", "exception", "critical", "fatal", "log"}
)
_LOGGER_RECEIVER_HINT = "log"

# ---------------------------------------------------------------------------
# Pattern rules. Each entry is (rule_name, compiled_regex); rule names appear
# verbatim in the report so a denial names *which* shape matched, not just the
# pattern class.
# ---------------------------------------------------------------------------

_LITERAL_SECRET_RULES = (
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws_access_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("sk_prefixed_api_key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
)

_LITERAL_PII_RULES = (
    (
        "email_address",
        re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"),
    ),
)

# Generic opaque-credential heuristic: a long unbroken alphanumeric run that
# mixes letters and digits. Deliberately excludes `_` and `-` from the run so
# that explicitly-fake placeholders of the `EXAMPLE_NOT_A_REAL_KEY` shape
# (`.claude/rules/infra/secrets.md` control 1) can never match.
_OPAQUE_TOKEN_RE = re.compile(r"[A-Za-z0-9]{20,}")

_REDACTION_MARKER_RE = re.compile(
    r"(?:^|_)(?:redact|redacted|redaction|mask|masked|hash|hashed|digest|fingerprint"
    r"|scrubbed|sanitized|anonymized|pseudonymized|placeholder|obfuscated)(?:$|_)"
)

_IDENTIFIER_SECRET_RULES = (
    ("password_identifier", re.compile(r"(?:^|_)(?:password|passwd|pwd|passphrase)(?:$|_)")),
    ("secret_identifier", re.compile(r"(?:^|_)(?:secret|client_secret)(?:$|_)")),
    ("token_identifier", re.compile(r"(?:^|_)token(?:$|_)")),
    (
        "key_identifier",
        re.compile(
            r"(?:^|_)(?:api_?key|access_?key|private_?key|signing_?key|secret_?key|session_?key)(?:$|_)"
        ),
    ),
    (
        "credential_identifier",
        re.compile(r"(?:^|_)(?:credential|credentials|authorization|auth_?header)(?:$|_)"),
    ),
)

_IDENTIFIER_PII_RULES = (
    ("email_identifier", re.compile(r"(?:^|_)e_?mail(?:$|_)")),
    (
        "phone_identifier",
        re.compile(r"(?:^|_)(?:phone|phone_?number|msisdn|mobile_?number)(?:$|_)"),
    ),
    (
        "government_id_identifier",
        re.compile(r"(?:^|_)(?:ssn|national_?id|passport_?no|passport_?number|id_?number)(?:$|_)"),
    ),
    ("date_of_birth_identifier", re.compile(r"(?:^|_)(?:dob|date_of_birth|birth_?date)(?:$|_)")),
    (
        "person_name_identifier",
        re.compile(r"(?:^|_)(?:full_?name|first_?name|last_?name|surname)(?:$|_)"),
    ),
)


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """One denial, carrying the file/line and pattern class `IMPLEMENTATION.md`
    §3 names as this lint's required output shape."""

    path: str
    line: int
    pattern_class: str
    rule: str
    subject: str
    log_call: str
    log_call_line: int

    def __str__(self) -> str:
        return (
            f"{self.path}:{self.line}: {FINDING_CODE}: "
            f"pattern_class={self.pattern_class} rule={self.rule} "
            f"subject={self.subject} in {self.log_call}() at line {self.log_call_line}"
        )

    @property
    def sort_key(self) -> tuple[int, str, str, str]:
        return (self.line, self.pattern_class, self.rule, self.subject)


@dataclass
class ValidationOutcome:
    """Problems plus the counters the CLI needs to tell a real pass from a
    vacuous one, resolved in a single pass (the `ValidationOutcome` shape
    `validate_migration_ordering.py` adopted for its R4-1 finding: never
    re-probe the tree to decide which notice to print)."""

    problems: list[str] = field(default_factory=list)
    notice: str | None = None
    files_checked: int = 0
    log_statements_inspected: int = 0


def _mask(value: str) -> str:
    """Report a matched literal without republishing it."""
    head = value[:3]
    return f"{head}...(len={len(value)})"


def _normalize_identifier(name: str) -> str:
    """`apiKey` -> `api_key`, `UserEMail` -> `user_e_mail`, so one lowercase
    underscore-anchored rule covers snake_case, camelCase and SCREAMING_CASE."""
    spaced = re.sub(r"(?<=[A-Za-z0-9])(?=[A-Z][a-z])", "_", name)
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", spaced)
    return spaced.lower()


def _is_redaction_marked(identifier: str) -> bool:
    return bool(_REDACTION_MARKER_RE.search(_normalize_identifier(identifier)))


def _classify_identifier(identifier: str) -> tuple[str, str] | None:
    """Return (pattern_class, rule) for a sensitive identifier, else None."""
    normalized = _normalize_identifier(identifier)
    if _REDACTION_MARKER_RE.search(normalized):
        return None
    for rule, pattern in _IDENTIFIER_SECRET_RULES:
        if pattern.search(normalized):
            return (PATTERN_CLASS_SECRET, rule)
    for rule, pattern in _IDENTIFIER_PII_RULES:
        if pattern.search(normalized):
            return (PATTERN_CLASS_PII, rule)
    return None


def _classify_literal(text: str) -> list[tuple[str, str, str]]:
    """Return (pattern_class, rule, masked_subject) for every match in a string
    constant that appears inside a log statement's arguments."""
    hits: list[tuple[str, str, str]] = []
    for rule, pattern in _LITERAL_SECRET_RULES:
        match = pattern.search(text)
        if match:
            hits.append((PATTERN_CLASS_SECRET, rule, _mask(match.group(0))))
    for rule, pattern in _LITERAL_PII_RULES:
        match = pattern.search(text)
        if match:
            hits.append((PATTERN_CLASS_PII, rule, _mask(match.group(0))))
    if not any(cls == PATTERN_CLASS_SECRET for cls, _, _ in hits):
        for match in _OPAQUE_TOKEN_RE.finditer(text):
            token = match.group(0)
            if any(c.isdigit() for c in token) and any(c.isalpha() for c in token):
                hits.append((PATTERN_CLASS_SECRET, "opaque_credential_token", _mask(token)))
                break
    return hits


# ---------------------------------------------------------------------------
# Log-statement identification
# ---------------------------------------------------------------------------


def _receiver_identifier(node: ast.expr) -> str | None:
    """Trailing identifier of a log call's receiver chain: `logger` for
    `logger`, `log` for `self.log`, `getLogger` for
    `logging.getLogger(__name__)`, `get_logger` for `structlog.get_logger()`."""
    current: ast.expr | None = node
    while current is not None:
        if isinstance(current, ast.Name):
            return current.id
        if isinstance(current, ast.Attribute):
            return current.attr
        if isinstance(current, ast.Call):
            current = current.func
            continue
        if isinstance(current, ast.Subscript):
            current = current.value
            continue
        return None
    return None


def _log_call_label(call: ast.Call) -> str | None:
    """Return `<receiver>.<level>` if this call is a log statement, else None."""
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr not in LOG_METHOD_NAMES:
        return None
    receiver = _receiver_identifier(func.value)
    if receiver is None or _LOGGER_RECEIVER_HINT not in receiver.lower():
        return None
    return f"{receiver}.{func.attr}"


def _iter_log_calls(tree: ast.AST) -> list[tuple[ast.Call, str]]:
    calls: list[tuple[ast.Call, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            label = _log_call_label(node)
            if label is not None:
                calls.append((node, label))
    return calls


def _argument_roots(call: ast.Call) -> list[ast.expr]:
    """Every expression a log statement actually renders: positional args,
    `*args` splats and keyword values. The callee chain itself is excluded —
    `logger.info` is not sensitive data."""
    roots: list[ast.expr] = list(call.args)
    roots.extend(kw.value for kw in call.keywords if kw.value is not None)
    return roots


def _scan_log_call(path_label: str, call: ast.Call, label: str) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[tuple[int, str, str, str]] = set()

    def record(line: int, pattern_class: str, rule: str, subject: str) -> None:
        key = (line, pattern_class, rule, subject)
        if key in seen:
            return
        seen.add(key)
        findings.append(
            Finding(
                path=path_label,
                line=line,
                pattern_class=pattern_class,
                rule=rule,
                subject=subject,
                log_call=label,
                log_call_line=call.lineno,
            )
        )

    stack: list[ast.AST] = list(_argument_roots(call))
    while stack:
        node = stack.pop()
        line = getattr(node, "lineno", call.lineno)

        if isinstance(node, ast.Call):
            callee = _receiver_identifier(node.func)
            if callee is not None and _is_redaction_marked(callee):
                # Redaction wrapper: the whole subtree is already safe, so it is
                # never descended into. This is what makes `redact(user.email)`
                # a pass without weakening the bare `user.email` case.
                continue

        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for pattern_class, rule, subject in _classify_literal(node.value):
                record(line, pattern_class, rule, subject)

        identifier: str | None = None
        if isinstance(node, ast.Name):
            identifier = node.id
        elif isinstance(node, ast.Attribute):
            identifier = node.attr
        if identifier is not None:
            classified = _classify_identifier(identifier)
            if classified is not None:
                record(line, classified[0], classified[1], identifier)

        stack.extend(ast.iter_child_nodes(node))

    return sorted(findings, key=lambda f: f.sort_key)


# ---------------------------------------------------------------------------
# File / tree entry points
# ---------------------------------------------------------------------------


def evaluate_source_text(text: str, *, name: str = "<text>") -> tuple[list[str], int]:
    """Return (problems, log_statements_inspected) for one source text.

    An empty problems list means ALLOW. Unparseable text fails closed rather
    than reporting zero problems.
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError) as exc:
        return ([f"{name}: UNPARSEABLE_SOURCE_FILE: {exc}"], 0)

    log_calls = _iter_log_calls(tree)
    problems: list[str] = []
    for call, label in log_calls:
        problems.extend(str(f) for f in _scan_log_call(name, call, label))
    return (problems, len(log_calls))


def validate_file(path: Path) -> tuple[list[str], int]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return ([f"{path}: UNREADABLE_SOURCE_FILE: {exc}"], 0)
    return evaluate_source_text(text, name=str(path))


def discover_source_files(root: Path) -> list[Path]:
    """Every `*.py` under `root`, excluding vendored/generated directories.
    A file given explicitly on the command line is never filtered out here."""
    if root.is_file():
        return [root]
    if not root.is_dir():
        return []
    found: list[Path] = []
    for candidate in root.rglob("*.py"):
        if any(part in EXCLUDED_DIR_NAMES for part in candidate.parts):
            continue
        found.append(candidate)
    return sorted(set(found))


def run_validation(
    targets: list[Path],
    *,
    require_log_statements: bool = False,
) -> ValidationOutcome:
    """Validate explicit files and/or roots, failing closed on a named path
    that does not exist and on having nothing at all to inspect."""
    outcome = ValidationOutcome()

    files: list[Path] = []
    for target in targets:
        if not target.exists():
            outcome.problems.append(
                f"{target}: MISSING_SOURCE_PATH: named target does not exist; failing "
                f"closed rather than reporting a pass over a path that was never read"
            )
            continue
        files.extend(discover_source_files(target))

    files = sorted(set(files))
    outcome.files_checked = len(files)

    if not files and not outcome.problems:
        outcome.problems.append(
            "NO_SOURCE_FILES: no *.py file was available to inspect; failing closed "
            "rather than reporting a pass over an empty file set"
        )

    for path in files:
        problems, inspected = validate_file(path)
        outcome.problems.extend(problems)
        outcome.log_statements_inspected += inspected

    if outcome.problems:
        return outcome

    if outcome.log_statements_inspected == 0:
        if require_log_statements:
            outcome.problems.append(
                f"NO_LOG_STATEMENTS_INSPECTED: {outcome.files_checked} file(s) contained "
                f"zero log statements and --require-log-statements was set; failing closed "
                f"rather than reporting a vacuous pass"
            )
            return outcome
        outcome.notice = NOTICE_NO_LOG_STATEMENTS

    return outcome


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Sensitive-logging lint (MOD-001, GOV-01-R03/R04, SCN-MOD001-122). "
        "Parses each *.py file and denies secret-shaped or PII-shaped data "
        "interpolated into a log statement's arguments, naming the file/line and "
        "pattern class. Distinct from secret-scanning: only log-statement "
        "arguments are inspected, never arbitrary file contents. Dependency-free, "
        "fails closed on anything it cannot read or parse.",
    )
    p.add_argument(
        "targets",
        nargs="*",
        type=Path,
        help="Files or directories to scan. Default (none given): "
        + ", ".join(str(r) for r in DEFAULT_SOURCE_ROOTS),
    )
    p.add_argument(
        "--require-log-statements",
        action="store_true",
        help="Fail closed (NO_LOG_STATEMENTS_INSPECTED, exit 1) if the scan found zero "
        "log statements, instead of reporting a true-but-vacuous pass. Any future CI "
        "wiring should pass this so a relocated or emptied source path cannot pass "
        "green forever (the R1-4 precedent from validate_migration_ordering.py).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    targets = args.targets if args.targets else list(DEFAULT_SOURCE_ROOTS)
    outcome = run_validation(targets, require_log_statements=args.require_log_statements)

    print("=" * 70)
    print("MOD-001 SENSITIVE-LOGGING LINT (GOV-01-R03/R04, SCN-MOD001-122)")
    print("=" * 70)
    print(f"\nTargets: {', '.join(str(t) for t in targets)}")
    print(f"Files checked: {outcome.files_checked}")
    print(f"Log statements inspected: {outcome.log_statements_inspected}")

    if outcome.problems:
        print(f"\nDENY: {len(outcome.problems)} problem(s) found:")
        for problem in outcome.problems:
            print(f"  - {problem}")
        return 1

    if outcome.notice:
        print(f"\n{outcome.notice}")

    print(
        "\nPASS - no secret-shaped or PII-shaped data is interpolated into any "
        "inspected log statement."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
