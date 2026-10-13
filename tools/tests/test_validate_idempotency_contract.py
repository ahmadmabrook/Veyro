"""
Unit tests for tools/validate_idempotency_contract.py (MOD-001, GOV-01-R02 —
the card's CI idempotency-contract lint for externally retryable mutations;
SCN-MOD001-016).

The scenario's own two halves drive this file.

Part (a), the static lint. SCN-MOD001-016(a) requires six synthetic command
declarations, "each missing exactly one of the card's 6 required elements in
turn", each denied "citing the specific missing element by name", plus a
companion positive in which all six are present:

  1. test_each_required_element_is_independently_denied_by_name - the
     scenario's core step, parameterized over all six elements: removing
     exactly one element denies that element *by name* and names no other
     element, so each of the six is proven independently rather than six
     declarations all failing for one shared reason.
  2. test_complete_declaration_passes - the companion positive.
  3. test_retention_window_under_24h_is_denied - the general floor.
  4. test_financial_path_retention_at_24h_is_denied - the scenario's
     "separately, under the longer payment/fiscal-path minimum for a command
     flagged financial" case: 24h satisfies the general minimum and is still
     denied once financial_path is true, with its own distinct reason code.
  5. test_financial_path_retention_longer_than_24h_passes - the paired
     positive, so case 4 is discriminating rather than a blanket denial of
     every financial declaration.
  6. test_non_financial_retention_at_exactly_24h_passes - the boundary on the
     other side, so the >= in the general floor is proven inclusive.
  7. test_retention_window_boolean_is_not_read_as_a_number - `true` must not
     read as 1 hour (bool is an int in Python).
  8. test_unscoped_key_tuple_is_denied - an empty `scope_fields` is denied as
     IDEMPOTENCY_KEY_TUPLE_NOT_SCOPED; "scoped" is the load-bearing word in
     element 1 and a bare global key must not pass it.
  9. test_near_miss_conflict_error_code_is_denied - a plausible misspelling
     of the stable 409 code, which is the realistic failure mode for a code
     clients branch on.
  10. test_conflict_http_status_must_be_409 - 200, and `true`, both denied.
  11. test_missing_propagation_target_names_the_missing_target - dropping
      `provider_dispatch` names it specifically; dropping `outbox` names that.
  12. test_unknown_propagation_target_is_denied - propagating somewhere else
      does not satisfy element 5.
  13. test_non_deterministic_derivative_input_is_denied - a derivative that
      declares deterministic=true while deriving from a timestamp.
  14. test_derivative_declaring_non_deterministic_is_denied - `deterministic:
      false` and a missing flag.
  15. test_unknown_declaration_field_is_denied - strictness: a silently
      ignored key would let a misspelling read as an enforced contract.
  16. test_externally_retryable_must_be_declared_true - absent, and false.
  17. test_missing_financial_path_flag_fails_closed - the retention threshold
      cannot be chosen without it, so its absence is a denial rather than a
      default to the weaker threshold.
  18. test_malformed_json_fails_closed / test_non_object_declaration_fails_closed
      / test_missing_declaration_path_fails_closed /
      test_unreadable_declaration_file_fails_closed /
      test_empty_declaration_set_fails_closed - the fail-closed set: never a
      zero-problem pass over something that could not be read.
  19. test_cli_exit_code_matches_verdict - `main()` driven as a real
      subprocess: exit 1 for each of the six missing-element declarations with
      the element named on stdout, exit 0 for the complete one.

Part (b), the runtime behavior. SCN-MOD001-016(b) requires a synthetic
endpoint "built from the passing declaration", then the same request twice
with the same Idempotency-Key (expect the stored result, not a duplicate side
effect) and a retry with the same key but a different payload (expect "the
stable 409 ... the lint in (a) confirmed is declared"):

  20. test_runtime_replay_returns_stored_result_with_one_side_effect
  21. test_runtime_same_key_different_payload_returns_stable_409
  22. test_runtime_409_is_stable_across_repeats - the baseline calls the code
      *stable*, so the conflict is asserted to repeat identically rather than
      degrade on a second attempt.
  23. test_runtime_distinct_keys_each_take_effect - the discriminating
      control: dedup must not be unconditional, or tests 20-22 would pass
      against an endpoint that simply never does anything twice.
  24. test_runtime_endpoint_is_built_from_the_linted_declaration - the link
      between the two halves: the endpoint reads its field names, conflict
      status and conflict code out of the declaration part (a) passed, so
      (b) cannot drift from the contract (a) proved. Driven by mutating the
      declaration, not by inspecting attributes.

`SyntheticIdempotentCommandEndpoint` below is that synthetic endpoint. It
lives in this test module on purpose: it is a scenario fixture, not product
code, and MOD-001 implements no real command surface (GOV-01-R02's "OUT of
scope" is explicit that the actual membership/booking/payment business logic
belongs to MOD-004/MOD-015+/MOD-019+). It holds no real provider, no
credential and no real member data — only synthetic values.
"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from validate_idempotency_contract import (
    ELEMENT_CONFLICT,
    ELEMENT_KEY_TUPLE,
    ELEMENT_PROPAGATION,
    ELEMENT_PROVIDER_DERIVATIVE,
    ELEMENT_RETENTION,
    ELEMENT_STORED,
    REQUIRED_ELEMENTS,
    STABLE_CONFLICT_ERROR_CODE,
    evaluate_declaration,
    evaluate_declaration_text,
    run_validation,
    validate_declaration_file,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VALIDATOR_SCRIPT = REPO_ROOT / "tools" / "validate_idempotency_contract.py"


# ---------------------------------------------------------------------------
# The complete synthetic declaration, and the six one-element-missing
# derivations of it.
#
# Every value here is synthetic and self-labeling: a `synthetic.*` command
# name and field names that exist in no real schema. No credential, no
# provider endpoint, no member data (owner-reserved restrictions 1 and 2).
# ---------------------------------------------------------------------------

COMPLETE_DECLARATION: dict[str, Any] = {
    "command": "synthetic.widget.create",
    "externally_retryable": True,
    "financial_path": False,
    "idempotency_key_tuple": {
        "key_field": "idempotency_key",
        "scope_fields": ["tenant_id", "command_name"],
    },
    "retention_window_hours": 24,
    "stored_request_hash_field": "request_payload_sha256",
    "stored_result_field": "stored_response",
    "conflict_http_status": 409,
    "conflict_error_code": STABLE_CONFLICT_ERROR_CODE,
    "command_id_propagation": {
        "field": "command_id",
        "targets": ["outbox", "provider_dispatch"],
    },
    "provider_idempotency_derivative": {
        "field": "provider_idempotency_reference",
        "derived_from": ["tenant_id", "command_id"],
        "deterministic": True,
    },
}

# Which top-level key(s) carry each element. Removing exactly these produces
# the scenario's "missing exactly one of the six elements" declaration.
ELEMENT_KEYS: dict[str, tuple[str, ...]] = {
    ELEMENT_KEY_TUPLE: ("idempotency_key_tuple",),
    ELEMENT_RETENTION: ("retention_window_hours",),
    ELEMENT_STORED: ("stored_request_hash_field", "stored_result_field"),
    ELEMENT_CONFLICT: ("conflict_http_status", "conflict_error_code"),
    ELEMENT_PROPAGATION: ("command_id_propagation",),
    ELEMENT_PROVIDER_DERIVATIVE: ("provider_idempotency_derivative",),
}


def declaration(**overrides: Any) -> dict[str, Any]:
    """A deep copy of the complete declaration with `overrides` applied. A
    value of `REMOVE` deletes the key."""
    data = copy.deepcopy(COMPLETE_DECLARATION)
    for key, value in overrides.items():
        if value is REMOVE:
            data.pop(key, None)
        else:
            data[key] = value
    return data


class _Remove:
    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return "REMOVE"


REMOVE = _Remove()


def without_element(element: str) -> dict[str, Any]:
    data = copy.deepcopy(COMPLETE_DECLARATION)
    for key in ELEMENT_KEYS[element]:
        del data[key]
    return data


def elements_named(problems: list[str]) -> set[str]:
    """Every element name the report cites, read back out of the report text —
    so these tests assert on the operator-visible output, not on internals."""
    named = set()
    for element in REQUIRED_ELEMENTS:
        if any(f"element={element} " in p for p in problems):
            named.add(element)
    return named


def reasons(problems: list[str]) -> set[str]:
    out = set()
    for problem in problems:
        for token in problem.split():
            if token.startswith("reason="):
                out.add(token[len("reason=") :].rstrip(":"))
    return out


def assert_denied_for(problems: list[str], element: str, reason: str) -> None:
    assert problems, f"expected a denial for {element}, got a clean pass"
    assert element in elements_named(problems), problems
    assert reason in reasons(problems), problems


# ---------------------------------------------------------------------------
# Part (a) - the static lint
# ---------------------------------------------------------------------------


def test_each_required_element_is_independently_denied_by_name():
    """SCN-MOD001-016(a)'s core step. Six declarations, each missing exactly
    one element; each denied citing *that* element and no other."""
    assert len(REQUIRED_ELEMENTS) == 6, REQUIRED_ELEMENTS
    for element in REQUIRED_ELEMENTS:
        problems = evaluate_declaration(without_element(element), name=f"missing-{element}.json")
        assert problems, f"{element}: expected a denial, got a clean pass"
        assert elements_named(problems) == {element}, (element, problems)
        assert all("IDEMPOTENCY_CONTRACT_INCOMPLETE" in p for p in problems), problems


def test_complete_declaration_passes():
    assert evaluate_declaration(COMPLETE_DECLARATION, name="complete.json") == []


def test_retention_window_under_24h_is_denied():
    problems = evaluate_declaration(declaration(retention_window_hours=23))
    assert_denied_for(problems, ELEMENT_RETENTION, "RETENTION_WINDOW_BELOW_MINIMUM")
    assert elements_named(problems) == {ELEMENT_RETENTION}, problems


def test_financial_path_retention_at_24h_is_denied():
    """The scenario's separate financial case: 24h clears the general minimum
    and is still denied, under its own distinct reason code."""
    problems = evaluate_declaration(declaration(financial_path=True, retention_window_hours=24))
    assert_denied_for(problems, ELEMENT_RETENTION, "RETENTION_WINDOW_BELOW_FINANCIAL_MINIMUM")
    assert "RETENTION_WINDOW_BELOW_MINIMUM" not in reasons(problems), problems
    assert elements_named(problems) == {ELEMENT_RETENTION}, problems


def test_financial_path_retention_longer_than_24h_passes():
    assert evaluate_declaration(declaration(financial_path=True, retention_window_hours=48)) == []


def test_non_financial_retention_at_exactly_24h_passes():
    assert evaluate_declaration(declaration(financial_path=False, retention_window_hours=24)) == []


def test_retention_window_boolean_is_not_read_as_a_number():
    problems = evaluate_declaration(declaration(retention_window_hours=True))
    assert_denied_for(problems, ELEMENT_RETENTION, "RETENTION_WINDOW_NOT_NUMERIC")


def test_unscoped_key_tuple_is_denied():
    problems = evaluate_declaration(
        declaration(idempotency_key_tuple={"key_field": "idempotency_key", "scope_fields": []})
    )
    assert_denied_for(problems, ELEMENT_KEY_TUPLE, "IDEMPOTENCY_KEY_TUPLE_NOT_SCOPED")
    assert elements_named(problems) == {ELEMENT_KEY_TUPLE}, problems


def test_missing_key_field_in_tuple_is_denied():
    problems = evaluate_declaration(
        declaration(idempotency_key_tuple={"scope_fields": ["tenant_id"]})
    )
    assert_denied_for(problems, ELEMENT_KEY_TUPLE, "IDEMPOTENCY_KEY_TUPLE_MISSING_KEY_FIELD")


def test_near_miss_conflict_error_code_is_denied():
    problems = evaluate_declaration(
        declaration(conflict_error_code="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOADS")
    )
    assert_denied_for(problems, ELEMENT_CONFLICT, "CONFLICT_ERROR_CODE_NOT_STABLE_CONTRACT")
    assert elements_named(problems) == {ELEMENT_CONFLICT}, problems


def test_conflict_http_status_must_be_409():
    for bad_status in (200, 400, 500, True):
        problems = evaluate_declaration(declaration(conflict_http_status=bad_status))
        assert_denied_for(problems, ELEMENT_CONFLICT, "CONFLICT_HTTP_STATUS_NOT_409")


def test_missing_propagation_target_names_the_missing_target():
    for dropped, kept in (
        ("provider_dispatch", ["outbox"]),
        ("outbox", ["provider_dispatch"]),
    ):
        problems = evaluate_declaration(
            declaration(command_id_propagation={"field": "command_id", "targets": kept})
        )
        assert_denied_for(problems, ELEMENT_PROPAGATION, "COMMAND_ID_PROPAGATION_MISSING_TARGET")
        assert any(f"'{dropped}'" in p for p in problems), (dropped, problems)


def test_unknown_propagation_target_is_denied():
    problems = evaluate_declaration(
        declaration(
            command_id_propagation={
                "field": "command_id",
                "targets": ["outbox", "provider_dispatch", "somewhere_else"],
            }
        )
    )
    assert_denied_for(problems, ELEMENT_PROPAGATION, "UNKNOWN_PROPAGATION_TARGET")


def test_non_deterministic_derivative_input_is_denied():
    for bad_input in ("request_timestamp", "random_seed", "created_at_time", "retry_nonce"):
        problems = evaluate_declaration(
            declaration(
                provider_idempotency_derivative={
                    "field": "provider_idempotency_reference",
                    "derived_from": ["tenant_id", bad_input],
                    "deterministic": True,
                }
            )
        )
        assert_denied_for(
            problems,
            ELEMENT_PROVIDER_DERIVATIVE,
            "PROVIDER_IDEMPOTENCY_DERIVATIVE_INPUT_NOT_DETERMINISTIC",
        )
        assert elements_named(problems) == {ELEMENT_PROVIDER_DERIVATIVE}, (bad_input, problems)


def test_derivative_declaring_non_deterministic_is_denied():
    for flag in (False, REMOVE):
        derivative: dict[str, Any] = {
            "field": "provider_idempotency_reference",
            "derived_from": ["tenant_id", "command_id"],
        }
        if flag is not REMOVE:
            derivative["deterministic"] = flag
        problems = evaluate_declaration(declaration(provider_idempotency_derivative=derivative))
        assert_denied_for(
            problems,
            ELEMENT_PROVIDER_DERIVATIVE,
            "PROVIDER_IDEMPOTENCY_DERIVATIVE_NOT_DETERMINISTIC",
        )


def test_empty_derivation_inputs_are_denied():
    problems = evaluate_declaration(
        declaration(
            provider_idempotency_derivative={
                "field": "provider_idempotency_reference",
                "derived_from": [],
                "deterministic": True,
            }
        )
    )
    assert_denied_for(
        problems, ELEMENT_PROVIDER_DERIVATIVE, "PROVIDER_IDEMPOTENCY_DERIVATIVE_NO_INPUTS"
    )


def test_missing_stored_result_field_is_denied_distinctly_from_the_hash():
    problems = evaluate_declaration(declaration(stored_result_field=REMOVE))
    assert_denied_for(problems, ELEMENT_STORED, "MISSING_STORED_RESULT_FIELD")
    assert "MISSING_STORED_REQUEST_HASH_FIELD" not in reasons(problems), problems


def test_unknown_declaration_field_is_denied():
    problems = evaluate_declaration(declaration(retention_windoe_hours=48))
    assert "UNKNOWN_DECLARATION_FIELD" in reasons(problems), problems
    assert any("retention_windoe_hours" in p for p in problems), problems


def test_externally_retryable_must_be_declared_true():
    assert "MISSING_RETRYABILITY_DECLARATION" in reasons(
        evaluate_declaration(declaration(externally_retryable=REMOVE))
    )
    assert "NOT_DECLARED_EXTERNALLY_RETRYABLE" in reasons(
        evaluate_declaration(declaration(externally_retryable=False))
    )


def test_missing_financial_path_flag_fails_closed():
    problems = evaluate_declaration(declaration(financial_path=REMOVE))
    assert "MISSING_FINANCIAL_PATH_FLAG" in reasons(problems), problems


def test_missing_command_name_is_denied():
    assert "MISSING_COMMAND_NAME" in reasons(evaluate_declaration(declaration(command=REMOVE)))


def test_malformed_json_fails_closed():
    problems = evaluate_declaration_text("{not json", name="broken.json")
    assert "MALFORMED_DECLARATION_JSON" in reasons(problems), problems


def test_non_object_declaration_fails_closed():
    for text in ("[]", '"a string"', "42", "null"):
        problems = evaluate_declaration_text(text, name="not-an-object.json")
        assert "DECLARATION_NOT_OBJECT" in reasons(problems), (text, problems)


def test_missing_declaration_path_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        outcome = run_validation([Path(tmp) / "nope.json"])
    assert "MISSING_DECLARATION_PATH" in reasons(outcome.problems), outcome.problems


def test_unreadable_declaration_file_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "unreadable.json"
        path.write_text(json.dumps(COMPLETE_DECLARATION), encoding="utf-8")
        path.chmod(0o000)
        try:
            problems = validate_declaration_file(path)
        finally:
            path.chmod(0o600)
    assert "UNREADABLE_DECLARATION_FILE" in reasons(problems), problems


def test_empty_declaration_set_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        outcome = run_validation([Path(tmp)])
    assert "NO_DECLARATION_FILES" in reasons(outcome.problems), outcome.problems
    assert outcome.declarations_checked == 0


def test_run_validation_over_a_directory_reads_every_declaration():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "good.json").write_text(json.dumps(COMPLETE_DECLARATION), encoding="utf-8")
        (root / "bad.json").write_text(
            json.dumps(without_element(ELEMENT_CONFLICT)), encoding="utf-8"
        )
        outcome = run_validation([root])
    assert outcome.declarations_checked == 2
    assert elements_named(outcome.problems) == {ELEMENT_CONFLICT}, outcome.problems


def test_cli_exit_code_matches_verdict():
    """`main()` as a real subprocess: exit 1 and the element named on stdout
    for each of the six, exit 0 for the complete declaration."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        complete = root / "complete.json"
        complete.write_text(json.dumps(COMPLETE_DECLARATION), encoding="utf-8")
        ok = subprocess.run(
            [sys.executable, str(VALIDATOR_SCRIPT), str(complete)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert ok.returncode == 0, ok.stdout + ok.stderr
        assert "PASS" in ok.stdout, ok.stdout

        for element in REQUIRED_ELEMENTS:
            path = root / f"missing-{element}.json"
            path.write_text(json.dumps(without_element(element)), encoding="utf-8")
            denied = subprocess.run(
                [sys.executable, str(VALIDATOR_SCRIPT), str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
            assert denied.returncode == 1, (element, denied.stdout + denied.stderr)
            assert f"element={element} " in denied.stdout, (element, denied.stdout)
            assert "DENY" in denied.stdout, denied.stdout


# ---------------------------------------------------------------------------
# Part (b) - the synthetic runtime endpoint, built from the passing declaration
# ---------------------------------------------------------------------------


class IdempotencyConflict(Exception):
    """Raised with the declared stable 409 contract. Carries the status and
    code read out of the declaration, never literals of its own."""

    def __init__(self, status: int, error_code: str) -> None:
        super().__init__(f"{status} {error_code}")
        self.status = status
        self.error_code = error_code


class SyntheticIdempotentCommandEndpoint:
    """SCN-MOD001-016(b)'s "synthetic endpoint built from the passing
    declaration".

    Every name and value it behaves by is read out of the declaration — the
    scope/key fields, the stored-hash and stored-result field names, the
    conflict status and code, the propagation targets and the provider
    derivative. That is the point: part (b) cannot drift from the contract
    part (a) proved, because there is no second copy of it here.

    In-memory only. No database, no provider, no network, no credential.
    """

    def __init__(self, decl: dict[str, Any]) -> None:
        key_tuple = decl["idempotency_key_tuple"]
        propagation = decl["command_id_propagation"]
        derivative = decl["provider_idempotency_derivative"]

        self.command = decl["command"]
        self._key_field: str = key_tuple["key_field"]
        self._scope_fields: tuple[str, ...] = tuple(key_tuple["scope_fields"])
        self._hash_field: str = decl["stored_request_hash_field"]
        self._result_field: str = decl["stored_result_field"]
        self._conflict_status: int = decl["conflict_http_status"]
        self._conflict_code: str = decl["conflict_error_code"]
        self._command_id_field: str = propagation["field"]
        self._targets: tuple[str, ...] = tuple(propagation["targets"])
        self._derivative_field: str = derivative["field"]
        self._derivative_inputs: tuple[str, ...] = tuple(derivative["derived_from"])

        self._store: dict[tuple[str, ...], dict[str, Any]] = {}
        # One entry per *real* side effect. The dedup claim in (b) is a
        # statement about this list's length, not about a return value.
        self.side_effects: list[str] = []
        self.dispatches: list[tuple[str, str]] = []

    @staticmethod
    def _digest(*parts: str) -> str:
        return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()

    def _stored_key(self, request: dict[str, Any]) -> tuple[str, ...]:
        """The scoped Idempotency-Key tuple element 1 declares."""
        return tuple(str(request[f]) for f in self._scope_fields) + (str(request[self._key_field]),)

    @staticmethod
    def _payload_hash(payload: Any) -> str:
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def post(self, request: dict[str, Any]) -> dict[str, Any]:
        stored_key = self._stored_key(request)
        payload_hash = self._payload_hash(request["payload"])

        stored = self._store.get(stored_key)
        if stored is not None:
            if stored[self._hash_field] != payload_hash:
                raise IdempotencyConflict(self._conflict_status, self._conflict_code)
            return {"status": 200, "replayed": True, "body": stored[self._result_field]}

        command_id = self._digest(*stored_key, payload_hash)
        result = {"widget_id": self._digest("widget", command_id), "created": True}

        # The one real side effect, plus the command_id propagation element 5
        # declares and the deterministic derivative element 6 declares.
        self.side_effects.append(command_id)
        for target in self._targets:
            self.dispatches.append((target, command_id))
        provider_reference = self._digest(
            *(str(request.get(name, command_id)) for name in self._derivative_inputs)
        )

        self._store[stored_key] = {
            self._hash_field: payload_hash,
            self._result_field: result,
            self._command_id_field: command_id,
            self._derivative_field: provider_reference,
        }
        return {"status": 201, "replayed": False, "body": result}


def synthetic_request(
    *, key: str = "idem-key-0001", payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    """A synthetic request carrying the scope fields the declaration names."""
    return {
        "tenant_id": "tenant-synthetic-0001",
        "command_name": "synthetic.widget.create",
        "idempotency_key": key,
        "payload": payload if payload is not None else {"label": "widget-a"},
    }


def passing_endpoint() -> SyntheticIdempotentCommandEndpoint:
    """Built only from a declaration this lint actually passes — so the
    runtime half is wired to a contract proven complete, not to an arbitrary
    dict."""
    assert evaluate_declaration(COMPLETE_DECLARATION) == []
    return SyntheticIdempotentCommandEndpoint(COMPLETE_DECLARATION)


def test_runtime_replay_returns_stored_result_with_one_side_effect():
    endpoint = passing_endpoint()
    request = synthetic_request()

    first = endpoint.post(request)
    second = endpoint.post(dict(request))

    assert first["replayed"] is False and first["status"] == 201, first
    assert second["replayed"] is True and second["status"] == 200, second
    assert second["body"] == first["body"], (first, second)
    assert len(endpoint.side_effects) == 1, endpoint.side_effects
    assert endpoint.dispatches == [
        ("outbox", endpoint.side_effects[0]),
        ("provider_dispatch", endpoint.side_effects[0]),
    ], endpoint.dispatches


def test_runtime_same_key_different_payload_returns_stable_409():
    endpoint = passing_endpoint()
    endpoint.post(synthetic_request(payload={"label": "widget-a"}))

    try:
        endpoint.post(synthetic_request(payload={"label": "widget-b"}))
    except IdempotencyConflict as conflict:
        assert conflict.status == 409, conflict.status
        assert conflict.error_code == STABLE_CONFLICT_ERROR_CODE, conflict.error_code
    else:
        raise AssertionError("expected IdempotencyConflict, the request was accepted")

    assert len(endpoint.side_effects) == 1, endpoint.side_effects


def test_runtime_409_is_stable_across_repeats():
    endpoint = passing_endpoint()
    endpoint.post(synthetic_request(payload={"label": "widget-a"}))

    seen = []
    for _ in range(3):
        try:
            endpoint.post(synthetic_request(payload={"label": "widget-b"}))
        except IdempotencyConflict as conflict:
            seen.append((conflict.status, conflict.error_code))
    assert seen == [(409, STABLE_CONFLICT_ERROR_CODE)] * 3, seen
    assert len(endpoint.side_effects) == 1, endpoint.side_effects


def test_runtime_distinct_keys_each_take_effect():
    """The discriminating control: without this, tests 20-22 would also pass
    against an endpoint that simply refuses every second request."""
    endpoint = passing_endpoint()
    first = endpoint.post(synthetic_request(key="idem-key-0001"))
    second = endpoint.post(synthetic_request(key="idem-key-0002"))

    assert first["replayed"] is False and second["replayed"] is False, (first, second)
    assert len(endpoint.side_effects) == 2, endpoint.side_effects
    assert first["body"] != second["body"], (first, second)


def test_runtime_endpoint_is_built_from_the_linted_declaration():
    """Change the declaration's conflict code and the runtime's 409 payload
    changes with it — proving (b) reads the contract rather than restating
    it. The mutated declaration is also shown to be *denied* by (a), so this
    coupling is not a loophole: only a declaration part (a) passes can
    legitimately reach the runtime."""
    mutated = declaration(conflict_error_code="SOME_OTHER_CODE")
    assert_denied_for(
        evaluate_declaration(mutated), ELEMENT_CONFLICT, "CONFLICT_ERROR_CODE_NOT_STABLE_CONTRACT"
    )

    endpoint = SyntheticIdempotentCommandEndpoint(mutated)
    endpoint.post(synthetic_request(payload={"label": "widget-a"}))
    try:
        endpoint.post(synthetic_request(payload={"label": "widget-b"}))
    except IdempotencyConflict as conflict:
        assert conflict.error_code == "SOME_OTHER_CODE", conflict.error_code
    else:
        raise AssertionError("expected IdempotencyConflict, the request was accepted")
