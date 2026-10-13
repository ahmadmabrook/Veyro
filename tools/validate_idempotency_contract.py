"""
Idempotency-contract lint (MOD-001, GOV-01-R02 — the card's CI
idempotency-contract lint for externally retryable mutations;
SCN-MOD001-016 part (a)).

`REQUIREMENTS.md`'s "Idempotency-contract lint" row (line 584) states the
obligation as: "For externally retryable mutations: scoped Idempotency-Key
tuple, retention window (>=24h, longer for payment/fiscal), stored request
hash/result, stable 409 `IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD`,
`command_id` propagation to outbox/provider dispatch, deterministic provider
idempotency derivatives", citing `EIP_MIRROR.md` lines 4148-4157.
`IMPLEMENTATION.md` §1 names this file, and §3's CI row names the expected
output as a "Named missing-element report (key-tuple scoping, retention
window, stored-hash field, 409-code reference, command_id propagation, or
provider-derivative field)". `SCENARIOS.md`'s SCN-MOD001-016 part (a) is the
scenario that exercises it: six synthetic declarations, each missing exactly
one of the six elements, each expected to be denied "citing the specific
missing element by name", plus a complete declaration that passes.

This tool implements part (a) only. Part (b) — the runtime dedup/409
behavior — needs no tool of its own (`IMPLEMENTATION.md` §1 says so
explicitly) and is covered by the synthetic runtime fixture in
`tools/tests/test_validate_idempotency_contract.py`.

## Input: one strict JSON command declaration per file

The input is a *declaration*, not source code: this lint reads what a
command says about its own idempotency contract. Exactly one JSON object per
file, with these keys and no others (an unrecognized key is a denial, not an
ignored extra — see "Strictness" below):

    {
      "command": "synthetic.widget.create",
      "externally_retryable": true,
      "financial_path": false,
      "idempotency_key_tuple": {
        "key_field": "idempotency_key",
        "scope_fields": ["tenant_id", "command_name"]
      },
      "retention_window_hours": 24,
      "stored_request_hash_field": "request_payload_sha256",
      "stored_result_field": "stored_response",
      "conflict_http_status": 409,
      "conflict_error_code": "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD",
      "command_id_propagation": {
        "field": "command_id",
        "targets": ["outbox", "provider_dispatch"]
      },
      "provider_idempotency_derivative": {
        "field": "provider_idempotency_reference",
        "derived_from": ["tenant_id", "command_id"],
        "deterministic": true
      }
    }

Three keys are structural rather than one of the six elements, and all three
are mandatory:

  * `command` — the declaration's subject, so a report names *which* command
    is incomplete.
  * `externally_retryable` — must be literally `true`. The CI row scopes this
    lint to "a command declaration for an externally-retryable mutation", so
    a declaration that does not assert its own retryability is out of
    contract, not out of scope: it is denied rather than skipped. Deciding
    *which* committed declarations are in scope belongs to the CI wiring,
    which is not part of this change.
  * `financial_path` — required because element 2 cannot be evaluated
    without it. Defaulting a missing flag to "not financial" would apply the
    weaker of two thresholds to an undeclared path, so its absence fails
    closed instead.

## The six elements, and why each check is shaped the way it is

Element names below appear verbatim in every denial, which is what makes the
report a "named missing-element report".

  1. `scoped_idempotency_key_tuple` — `idempotency_key_tuple` must name the
     key field *and* at least one scope field. "Scoped" is checked
     structurally (a non-empty `scope_fields` list) rather than against an
     allowlist of blessed dimension names, because this module owns no real
     tenancy vocabulary yet and guessing one would be a product decision.
  2. `retention_window` — `retention_window_hours` must be >= 24, and on a
     `financial_path` command strictly greater than 24. The baseline's own
     words are ">=24 h and longer for payment/fiscal paths": it fixes the
     general floor numerically and the fiscal one only comparatively. This
     lint therefore enforces exactly that and **does not invent a fiscal
     figure** — picking one (90 days, 7 years) would be a material product
     decision and is owner-reserved. Stated residual: a financial command
     declaring 25h satisfies this lint. The module that owns a real
     payment/fiscal path must tighten the threshold with its own recorded
     retention figure.
  3. `stored_request_hash_and_result` — both `stored_request_hash_field` and
     `stored_result_field` must be named. The baseline says "stored request
     hash/result"; a stored hash with no stored result cannot answer a retry
     with the original outcome, and a stored result with no hash cannot tell
     a replay from a different payload reusing the key.
  4. `stable_409_conflict_code` — `conflict_http_status` must be 409 and
     `conflict_error_code` must be exactly
     `IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD`. The baseline calls this
     code *stable*, so a near-miss spelling is a denial: the whole point of a
     stable code is that a client can branch on it.
  5. `command_id_propagation` — must name the propagated field and both
     targets the baseline names, `outbox` and `provider_dispatch`. A target
     outside that pair is a denial rather than an ignored extra, so this
     check cannot be satisfied by propagating somewhere else entirely.
  6. `deterministic_provider_idempotency_derivative` — must name the derived
     field, declare `deterministic: true`, and list the inputs it derives
     from. Each input name is additionally checked against a narrow list of
     non-deterministic tokens (`random`, `uuid`, `now`, `timestamp`, `time`,
     `clock`, `nonce`, `sequence`), so a derivative that declares itself
     deterministic while deriving from a clock is denied. Stated residual:
     this is a name-shaped check on a declaration, not an analysis of a real
     derivation function — a non-deterministic input under a neutral name is
     out of reach of any declaration-level lint, and the runtime half of
     SCN-MOD001-016 is what exercises actual behavior.

## Strictness

An unrecognized top-level key, an unrecognized key inside one of the three
nested objects, or an unrecognized propagation target is denied
(`UNKNOWN_DECLARATION_FIELD` / `UNKNOWN_PROPAGATION_TARGET`). A lint that
silently ignores what it does not understand would pass a declaration whose
author believed a misspelled key was being enforced.

Booleans are rejected where a number is required: `True` is an `int` in
Python, and `"retention_window_hours": true` must not read as 1 hour.

## Fail-closed rule

"Cannot read it" always resolves to deny, never to "assume compliant": a
named path that does not exist is `MISSING_DECLARATION_PATH`, an unreadable
or undecodable file is `UNREADABLE_DECLARATION_FILE`, invalid JSON is
`MALFORMED_DECLARATION_JSON`, a JSON document that is not an object is
`DECLARATION_NOT_OBJECT`, and having nothing at all to inspect is
`NO_DECLARATION_FILES`. Targets are required on the command line and there
is no default root, which is what removes the vacuous-pass class that
`validate_migration_ordering.py`'s R1-4 and
`validate_sensitive_logging.py`'s `--require-log-statements` had to add
flags for: this tool cannot report a pass over a path nobody named.

Deliberately dependency-free (stdlib only), matching the "zero new
dependencies" convention of the sibling validators in this directory.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FINDING_CODE = "IDEMPOTENCY_CONTRACT_INCOMPLETE"
SCHEMA_FINDING_CODE = "MALFORMED_IDEMPOTENCY_DECLARATION"

# The six elements named by EIP_MIRROR.md lines 4148-4157, in the order the
# baseline lists them. These strings are the report's `element=` values.
ELEMENT_KEY_TUPLE = "scoped_idempotency_key_tuple"
ELEMENT_RETENTION = "retention_window"
ELEMENT_STORED = "stored_request_hash_and_result"
ELEMENT_CONFLICT = "stable_409_conflict_code"
ELEMENT_PROPAGATION = "command_id_propagation"
ELEMENT_PROVIDER_DERIVATIVE = "deterministic_provider_idempotency_derivative"

REQUIRED_ELEMENTS = (
    ELEMENT_KEY_TUPLE,
    ELEMENT_RETENTION,
    ELEMENT_STORED,
    ELEMENT_CONFLICT,
    ELEMENT_PROPAGATION,
    ELEMENT_PROVIDER_DERIVATIVE,
)

MINIMUM_RETENTION_HOURS = 24
STABLE_CONFLICT_ERROR_CODE = "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD"
STABLE_CONFLICT_HTTP_STATUS = 409
REQUIRED_PROPAGATION_TARGETS = ("outbox", "provider_dispatch")

STRUCTURAL_FIELDS = ("command", "externally_retryable", "financial_path")
ELEMENT_FIELDS = (
    "idempotency_key_tuple",
    "retention_window_hours",
    "stored_request_hash_field",
    "stored_result_field",
    "conflict_http_status",
    "conflict_error_code",
    "command_id_propagation",
    "provider_idempotency_derivative",
)
KNOWN_FIELDS = frozenset(STRUCTURAL_FIELDS + ELEMENT_FIELDS)

KEY_TUPLE_FIELDS = frozenset({"key_field", "scope_fields"})
PROPAGATION_FIELDS = frozenset({"field", "targets"})
DERIVATIVE_FIELDS = frozenset({"field", "derived_from", "deterministic"})

# Narrow, deliberately short list of non-deterministic input markers. See the
# module docstring's stated residual: this is a name-shaped check.
_NON_DETERMINISTIC_INPUT_RE = re.compile(
    r"(?:^|_)(?:random|rand|uuid|uuid4|guid|now|timestamp|time|clock|nonce|sequence|seq)(?:$|_)"
)


@dataclass
class ValidationOutcome:
    """Problems plus the counters the CLI needs to describe what it read.

    Resolved in a single pass — the tree is never re-probed to decide what to
    print (the shape `validate_migration_ordering.py` adopted for its R4-1
    finding).
    """

    problems: list[str] = field(default_factory=list)
    declarations_checked: int = 0


def _normalize(name: str) -> str:
    """`providerUUID` -> `provider_uuid`, so one lowercase underscore-anchored
    rule covers snake_case, camelCase and SCREAMING_CASE input names."""
    spaced = re.sub(r"(?<=[A-Za-z0-9])(?=[A-Z][a-z])", "_", name)
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", spaced)
    return spaced.lower()


def _is_real_number(value: Any) -> bool:
    """True for a JSON number. `bool` is excluded on purpose: `True` is an
    `int` in Python, and `"retention_window_hours": true` must not read as 1.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_named(value: Any) -> bool:
    """True for a non-empty, non-blank string — the shape every declared field
    name must have."""
    return isinstance(value, str) and value.strip() != ""


def _is_name_list(value: Any) -> bool:
    return isinstance(value, list) and all(_is_named(item) for item in value)


class _Reporter:
    """Accumulates one declaration's problems in the report's fixed shape."""

    def __init__(self, name: str) -> None:
        self._name = name
        self.problems: list[str] = []

    def element(self, element: str, reason: str, detail: str) -> None:
        self.problems.append(
            f"{self._name}: {FINDING_CODE}: element={element} reason={reason}: {detail}"
        )

    def schema(self, reason: str, detail: str) -> None:
        self.problems.append(f"{self._name}: {SCHEMA_FINDING_CODE}: reason={reason}: {detail}")


def _check_structural_fields(data: dict[str, Any], report: _Reporter) -> None:
    """The three non-element keys. All mandatory; see the module docstring for
    why a missing `financial_path` fails closed rather than defaulting."""
    for unknown in sorted(set(data) - KNOWN_FIELDS):
        report.schema(
            "UNKNOWN_DECLARATION_FIELD",
            f"'{unknown}' is not a field of this declaration format; a silently "
            f"ignored key would let a misspelling read as an enforced contract",
        )

    if "command" not in data:
        report.schema("MISSING_COMMAND_NAME", "no 'command' key, so no subject to report on")
    elif not _is_named(data["command"]):
        report.schema(
            "COMMAND_NAME_NOT_NAMED",
            f"'command' must be a non-empty string, got {data['command']!r}",
        )

    if "externally_retryable" not in data:
        report.schema(
            "MISSING_RETRYABILITY_DECLARATION",
            "no 'externally_retryable' key; this lint's inputs are declarations for "
            "externally-retryable mutations, so an unasserted one is denied, not skipped",
        )
    elif data["externally_retryable"] is not True:
        report.schema(
            "NOT_DECLARED_EXTERNALLY_RETRYABLE",
            f"'externally_retryable' must be literally true, got {data['externally_retryable']!r}",
        )

    if "financial_path" not in data:
        report.schema(
            "MISSING_FINANCIAL_PATH_FLAG",
            "no 'financial_path' key, so the retention threshold in element "
            f"'{ELEMENT_RETENTION}' cannot be chosen; failing closed rather than "
            "applying the weaker of two thresholds to an undeclared path",
        )
    elif not isinstance(data["financial_path"], bool):
        report.schema(
            "FINANCIAL_PATH_FLAG_NOT_BOOLEAN",
            f"'financial_path' must be a boolean, got {data['financial_path']!r}",
        )


def _check_key_tuple(data: dict[str, Any], report: _Reporter) -> None:
    """Element 1 — scoped Idempotency-Key tuple."""
    if "idempotency_key_tuple" not in data:
        report.element(
            ELEMENT_KEY_TUPLE,
            "MISSING_IDEMPOTENCY_KEY_TUPLE",
            "no 'idempotency_key_tuple' declared",
        )
        return

    tuple_decl = data["idempotency_key_tuple"]
    if not isinstance(tuple_decl, dict):
        report.element(
            ELEMENT_KEY_TUPLE,
            "IDEMPOTENCY_KEY_TUPLE_NOT_OBJECT",
            f"'idempotency_key_tuple' must be an object with 'key_field' and "
            f"'scope_fields', got {type(tuple_decl).__name__}",
        )
        return

    for unknown in sorted(set(tuple_decl) - KEY_TUPLE_FIELDS):
        report.element(
            ELEMENT_KEY_TUPLE,
            "UNKNOWN_DECLARATION_FIELD",
            f"'{unknown}' is not a field of 'idempotency_key_tuple'",
        )

    if not _is_named(tuple_decl.get("key_field")):
        report.element(
            ELEMENT_KEY_TUPLE,
            "IDEMPOTENCY_KEY_TUPLE_MISSING_KEY_FIELD",
            "'key_field' must name the field carrying the Idempotency-Key itself",
        )

    scope_fields = tuple_decl.get("scope_fields")
    if not _is_name_list(scope_fields):
        report.element(
            ELEMENT_KEY_TUPLE,
            "IDEMPOTENCY_KEY_TUPLE_SCOPE_FIELDS_NOT_NAMED",
            f"'scope_fields' must be a list of non-empty field names, got {scope_fields!r}",
        )
    elif not scope_fields:
        report.element(
            ELEMENT_KEY_TUPLE,
            "IDEMPOTENCY_KEY_TUPLE_NOT_SCOPED",
            "'scope_fields' is empty, so the key is global rather than scoped; the "
            "baseline requires a scoped Idempotency-Key tuple",
        )


def _check_retention(data: dict[str, Any], report: _Reporter) -> None:
    """Element 2 — retention window (>=24h, strictly longer on a financial
    path). The fiscal figure itself is deliberately not invented here; see the
    module docstring's stated residual."""
    if "retention_window_hours" not in data:
        report.element(
            ELEMENT_RETENTION,
            "MISSING_RETENTION_WINDOW",
            "no 'retention_window_hours' declared",
        )
        return

    hours = data["retention_window_hours"]
    if not _is_real_number(hours):
        report.element(
            ELEMENT_RETENTION,
            "RETENTION_WINDOW_NOT_NUMERIC",
            f"'retention_window_hours' must be a number of hours, got {hours!r}",
        )
        return

    if hours < MINIMUM_RETENTION_HOURS:
        report.element(
            ELEMENT_RETENTION,
            "RETENTION_WINDOW_BELOW_MINIMUM",
            f"{hours}h is under the {MINIMUM_RETENTION_HOURS}h general minimum",
        )
        return

    # The financial threshold is a separate denial, because SCN-MOD001-016(a)
    # requires the under-24h case and the under-financial-minimum case to be
    # provable independently of each other.
    if data.get("financial_path") is True and hours <= MINIMUM_RETENTION_HOURS:
        report.element(
            ELEMENT_RETENTION,
            "RETENTION_WINDOW_BELOW_FINANCIAL_MINIMUM",
            f"{hours}h meets the {MINIMUM_RETENTION_HOURS}h general minimum but this "
            f"command declares financial_path=true, and the baseline requires a window "
            f"longer than {MINIMUM_RETENTION_HOURS}h on payment/fiscal paths",
        )


def _check_stored_request_hash_and_result(data: dict[str, Any], report: _Reporter) -> None:
    """Element 3 — stored request hash/result."""
    for field_name, reason in (
        ("stored_request_hash_field", "MISSING_STORED_REQUEST_HASH_FIELD"),
        ("stored_result_field", "MISSING_STORED_RESULT_FIELD"),
    ):
        if field_name not in data:
            report.element(ELEMENT_STORED, reason, f"no '{field_name}' declared")
        elif not _is_named(data[field_name]):
            report.element(
                ELEMENT_STORED,
                reason,
                f"'{field_name}' must name a non-empty field, got {data[field_name]!r}",
            )


def _check_conflict_contract(data: dict[str, Any], report: _Reporter) -> None:
    """Element 4 — stable 409 IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD."""
    if "conflict_error_code" not in data:
        report.element(
            ELEMENT_CONFLICT,
            "MISSING_CONFLICT_ERROR_CODE",
            f"no 'conflict_error_code' declared; the baseline requires a reference to "
            f"the stable '{STABLE_CONFLICT_ERROR_CODE}' code",
        )
    elif data["conflict_error_code"] != STABLE_CONFLICT_ERROR_CODE:
        report.element(
            ELEMENT_CONFLICT,
            "CONFLICT_ERROR_CODE_NOT_STABLE_CONTRACT",
            f"'conflict_error_code' must be exactly '{STABLE_CONFLICT_ERROR_CODE}', got "
            f"{data['conflict_error_code']!r}; a near-miss spelling defeats the point of "
            f"a stable code a client can branch on",
        )

    if "conflict_http_status" not in data:
        report.element(
            ELEMENT_CONFLICT,
            "MISSING_CONFLICT_HTTP_STATUS",
            f"no 'conflict_http_status' declared; the baseline requires "
            f"{STABLE_CONFLICT_HTTP_STATUS}",
        )
    elif data["conflict_http_status"] != STABLE_CONFLICT_HTTP_STATUS or isinstance(
        data["conflict_http_status"], bool
    ):
        report.element(
            ELEMENT_CONFLICT,
            "CONFLICT_HTTP_STATUS_NOT_409",
            f"'conflict_http_status' must be {STABLE_CONFLICT_HTTP_STATUS}, got "
            f"{data['conflict_http_status']!r}",
        )


def _check_command_id_propagation(data: dict[str, Any], report: _Reporter) -> None:
    """Element 5 — command_id propagation to outbox/provider dispatch."""
    if "command_id_propagation" not in data:
        report.element(
            ELEMENT_PROPAGATION,
            "MISSING_COMMAND_ID_PROPAGATION",
            "no 'command_id_propagation' declared",
        )
        return

    propagation = data["command_id_propagation"]
    if not isinstance(propagation, dict):
        report.element(
            ELEMENT_PROPAGATION,
            "COMMAND_ID_PROPAGATION_NOT_OBJECT",
            f"'command_id_propagation' must be an object with 'field' and 'targets', got "
            f"{type(propagation).__name__}",
        )
        return

    for unknown in sorted(set(propagation) - PROPAGATION_FIELDS):
        report.element(
            ELEMENT_PROPAGATION,
            "UNKNOWN_DECLARATION_FIELD",
            f"'{unknown}' is not a field of 'command_id_propagation'",
        )

    if not _is_named(propagation.get("field")):
        report.element(
            ELEMENT_PROPAGATION,
            "COMMAND_ID_PROPAGATION_MISSING_FIELD",
            "'field' must name the propagated command-id field",
        )

    targets = propagation.get("targets")
    if not _is_name_list(targets):
        report.element(
            ELEMENT_PROPAGATION,
            "COMMAND_ID_PROPAGATION_TARGETS_NOT_NAMED",
            f"'targets' must be a list of non-empty target names, got {targets!r}",
        )
        return

    declared = [_normalize(t) for t in targets]
    for required in REQUIRED_PROPAGATION_TARGETS:
        if required not in declared:
            report.element(
                ELEMENT_PROPAGATION,
                "COMMAND_ID_PROPAGATION_MISSING_TARGET",
                f"'{required}' is not among the declared targets {sorted(declared)}; the "
                f"baseline requires propagation to "
                f"{' and '.join(REQUIRED_PROPAGATION_TARGETS)}",
            )
    for target in sorted(set(declared) - set(REQUIRED_PROPAGATION_TARGETS)):
        report.element(
            ELEMENT_PROPAGATION,
            "UNKNOWN_PROPAGATION_TARGET",
            f"'{target}' is not one of "
            f"{list(REQUIRED_PROPAGATION_TARGETS)}; propagating elsewhere does not "
            f"satisfy this element",
        )


def _check_provider_derivative(data: dict[str, Any], report: _Reporter) -> None:
    """Element 6 — deterministic provider idempotency derivative."""
    if "provider_idempotency_derivative" not in data:
        report.element(
            ELEMENT_PROVIDER_DERIVATIVE,
            "MISSING_PROVIDER_IDEMPOTENCY_DERIVATIVE",
            "no 'provider_idempotency_derivative' declared",
        )
        return

    derivative = data["provider_idempotency_derivative"]
    if not isinstance(derivative, dict):
        report.element(
            ELEMENT_PROVIDER_DERIVATIVE,
            "PROVIDER_IDEMPOTENCY_DERIVATIVE_NOT_OBJECT",
            f"'provider_idempotency_derivative' must be an object with 'field', "
            f"'derived_from' and 'deterministic', got {type(derivative).__name__}",
        )
        return

    for unknown in sorted(set(derivative) - DERIVATIVE_FIELDS):
        report.element(
            ELEMENT_PROVIDER_DERIVATIVE,
            "UNKNOWN_DECLARATION_FIELD",
            f"'{unknown}' is not a field of 'provider_idempotency_derivative'",
        )

    if not _is_named(derivative.get("field")):
        report.element(
            ELEMENT_PROVIDER_DERIVATIVE,
            "PROVIDER_IDEMPOTENCY_DERIVATIVE_MISSING_FIELD",
            "'field' must name the derived provider-idempotency field",
        )

    if derivative.get("deterministic") is not True:
        report.element(
            ELEMENT_PROVIDER_DERIVATIVE,
            "PROVIDER_IDEMPOTENCY_DERIVATIVE_NOT_DETERMINISTIC",
            f"'deterministic' must be literally true, got {derivative.get('deterministic')!r}",
        )

    derived_from = derivative.get("derived_from")
    if not _is_name_list(derived_from):
        report.element(
            ELEMENT_PROVIDER_DERIVATIVE,
            "PROVIDER_IDEMPOTENCY_DERIVATIVE_INPUTS_NOT_NAMED",
            f"'derived_from' must be a list of non-empty input names, got {derived_from!r}",
        )
        return
    if not derived_from:
        report.element(
            ELEMENT_PROVIDER_DERIVATIVE,
            "PROVIDER_IDEMPOTENCY_DERIVATIVE_NO_INPUTS",
            "'derived_from' is empty, so nothing fixes the derivative's value",
        )
        return

    for item in derived_from:
        if _NON_DETERMINISTIC_INPUT_RE.search(_normalize(item)):
            report.element(
                ELEMENT_PROVIDER_DERIVATIVE,
                "PROVIDER_IDEMPOTENCY_DERIVATIVE_INPUT_NOT_DETERMINISTIC",
                f"input '{item}' is non-deterministic, so the derivative cannot be "
                f"reproduced on retry even though it declares deterministic=true",
            )


_ELEMENT_CHECKS = (
    _check_key_tuple,
    _check_retention,
    _check_stored_request_hash_and_result,
    _check_conflict_contract,
    _check_command_id_propagation,
    _check_provider_derivative,
)


def evaluate_declaration(data: Any, *, name: str = "<declaration>") -> list[str]:
    """Return every problem with one already-parsed declaration.

    An empty list means ALLOW. A document that is not a JSON object fails
    closed rather than reporting zero problems.
    """
    report = _Reporter(name)
    if not isinstance(data, dict):
        report.schema(
            "DECLARATION_NOT_OBJECT",
            f"a declaration must be a JSON object, got {type(data).__name__}",
        )
        return report.problems

    _check_structural_fields(data, report)
    for check in _ELEMENT_CHECKS:
        check(data, report)
    return report.problems


def evaluate_declaration_text(text: str, *, name: str = "<text>") -> list[str]:
    """Parse and evaluate one declaration's JSON text, failing closed on
    invalid JSON rather than reporting a clean pass."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        return [f"{name}: {SCHEMA_FINDING_CODE}: reason=MALFORMED_DECLARATION_JSON: {exc}"]
    return evaluate_declaration(data, name=name)


def validate_declaration_file(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{path}: {SCHEMA_FINDING_CODE}: reason=UNREADABLE_DECLARATION_FILE: {exc}"]
    return evaluate_declaration_text(text, name=str(path))


def discover_declaration_files(target: Path) -> list[Path]:
    """Every `*.json` under `target`. A file named explicitly on the command
    line is never filtered out by extension."""
    if target.is_file():
        return [target]
    if not target.is_dir():
        return []
    return sorted(set(target.rglob("*.json")))


def run_validation(targets: list[Path]) -> ValidationOutcome:
    """Validate explicit declaration files and/or directories, failing closed
    on a named path that does not exist and on having nothing to inspect."""
    outcome = ValidationOutcome()

    files: list[Path] = []
    for target in targets:
        if not target.exists():
            outcome.problems.append(
                f"{target}: {SCHEMA_FINDING_CODE}: reason=MISSING_DECLARATION_PATH: named "
                f"target does not exist; failing closed rather than reporting a pass over "
                f"a path that was never read"
            )
            continue
        files.extend(discover_declaration_files(target))

    files = sorted(set(files))
    outcome.declarations_checked = len(files)

    if not files and not outcome.problems:
        outcome.problems.append(
            f"{SCHEMA_FINDING_CODE}: reason=NO_DECLARATION_FILES: no *.json declaration was "
            f"available to inspect; failing closed rather than reporting a pass over an "
            f"empty file set"
        )

    for path in files:
        outcome.problems.extend(validate_declaration_file(path))

    return outcome


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Idempotency-contract lint (MOD-001, GOV-01-R02, SCN-MOD001-016 part a). "
        "Reads strict JSON command declarations for externally-retryable mutations and "
        "denies any that is missing one of the six required contract elements, naming the "
        "element. Dependency-free; fails closed on anything it cannot read or parse. "
        "Targets are required: there is no default root, so this lint cannot report a pass "
        "over a path nobody named.",
    )
    p.add_argument(
        "targets",
        nargs="+",
        type=Path,
        help="Declaration files (*.json) or directories containing them.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    outcome = run_validation(list(args.targets))

    print("=" * 70)
    print("MOD-001 IDEMPOTENCY-CONTRACT LINT (GOV-01-R02, SCN-MOD001-016a)")
    print("=" * 70)
    print(f"\nTargets: {', '.join(str(t) for t in args.targets)}")
    print(f"Declarations checked: {outcome.declarations_checked}")
    print(f"Required elements: {', '.join(REQUIRED_ELEMENTS)}")

    if outcome.problems:
        print(f"\nDENY: {len(outcome.problems)} problem(s) found:")
        for problem in outcome.problems:
            print(f"  - {problem}")
        return 1

    print(
        f"\nPASS - all {outcome.declarations_checked} declaration(s) declare all "
        f"{len(REQUIRED_ELEMENTS)} required idempotency-contract elements."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
