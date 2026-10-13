"""
Unit tests for tools/validate_data_exposure.py (MOD-001, the card's mandatory
Security-scope baseline control "input/output data exposure";
SCN-MOD001-126).

The scenario's own steps drive tests 1-4: a synthetic OpenAPI response schema
whose catch-all/wildcard shape silently serializes an undeclared field
(an internal column), a synthetic request schema that admits an extra
undeclared field past validation, and the companion positive where every
response field is explicitly declared and the request rejects anything
outside its own declared set. All fixtures are synthetic dicts defined in
this file -- the repository deliberately has no `contracts/openapi/` source,
and these tests do not create one.

  1. test_wildcard_response_can_leak_an_undeclared_field - the scenario's
     negative (a): a response shape with `additionalProperties: true` ->
     DENY (UNDECLARED_RESPONSE_FIELDS_PERMITTED), and the leak itself is
     proven field-by-field: an internal column is absent from
     `declared_field_names()` yet admitted by `admits_undeclared_fields()`.
  2. test_request_schema_admits_extra_hidden_field - the scenario's
     negative (b): a request body shape missing
     `additionalProperties: false` -> DENY
     (UNDECLARED_REQUEST_FIELDS_PERMITTED), with the same two-predicate
     leak proof for a hidden injected field.
  3. test_strict_contract_passes - the companion positive: nested objects,
     an array of `$ref`-ed items, a bodiless 204 and a strict request body
     -> ALLOW, zero findings.
  4. test_strict_predicates_refuse_the_same_fields - the positive's mirror:
     the strict shapes admit nothing outside their declared set.
  5. test_unrestricted_wildcard_additional_properties_schema_denies -
     `additionalProperties: {}` -> DENY (the "unrestricted wildcard schema"
     form named in the obligation).
  6. test_additional_properties_absent_denies - the most common real shape:
     `additionalProperties` simply not written.
  7. test_typed_map_additional_properties_denies - a typed map constrains
     value types, never field names -> DENY.
  8. test_nested_inline_object_laxness_is_not_a_bypass - strict at the top,
     lax one level down -> DENY, citing the nested location.
  9. test_ref_target_laxness_is_not_a_bypass - strict at the top, lax
     behind a local `$ref` -> DENY, citing the ref trail.
  10. test_array_item_laxness_is_not_a_bypass - laxness inside `items`.
  11. test_recursive_ref_terminates - a strict self-referencing schema is
      finite and passes (a cycle is not a finding).
  12. test_unresolvable_and_non_local_refs_fail_closed - dangling and
      external references -> UNRESOLVABLE_SCHEMA_REF.
  13. test_ref_with_schema_sibling_fails_closed - `$ref` next to a schema
      keyword -> UNSUPPORTED_SCHEMA_CONSTRUCT.
  14. test_boolean_schemas_fail_closed - `true` -> WILDCARD_SCHEMA,
      `false` -> INVALID_SCHEMA_OBJECT.
  15. test_composition_keywords_fail_closed - allOf/anyOf/oneOf/not.
  16. test_dynamic_keywords_fail_closed - patternProperties and
      unevaluatedProperties.
  17. test_ambiguous_type_fails_closed - no `type` and no
      `properties`/`items`, and a shape-mixing `type` union.
  18. test_object_without_declared_properties_fails_closed - strict but
      declaring nothing -> NO_DECLARED_OBJECT_FIELDS.
  19. test_array_without_items_fails_closed.
  20. test_missing_empty_and_non_schema_responses_fail_closed - no
      `responses`, empty `responses`, a non-204 response with no `content`,
      empty `content`, and a media type with no `schema`.
  21. test_bodiless_204_response_is_allowed - the one deliberate exception.
  22. test_object_level_refs_fail_closed - `$ref` at the path-item,
      response-object and requestBody-object level is denied, not resolved.
  23. test_invalid_inputs_fail_closed - non-object root, non-object paths,
      non-object path item/operation, path item with no operation.
  24. test_unsupported_version_fails_closed - 3.0.3, a missing `openapi`
      key, and 3.2.0 (above the verified range).
  25. test_missing_canonical_contract_source_denies - the repository state
      this tool must handle today: the canonical path does not exist ->
      MISSING_CONTRACT_SOURCE, never a pass.
  26. test_unreadable_unparseable_and_non_json_sources_fail_closed.
  27. test_empty_paths_object_fails_closed - no vacuous pass over an empty
      surface.
  28. test_findings_do_not_echo_contract_values - a denial report prints
      locations, field names and construct kinds, never an `example`,
      `default`, `enum`, `const` or `pattern` value.
  29. test_findings_are_deterministic - identical, sorted output across
      runs.
  30. test_cli_exit_code_matches_verdict - `main()` driven as a real
      subprocess: exit 1 on the lax fixture, exit 0 on the strict one.
  31. test_default_contract_path_is_canonical - the default is
      `contracts/openapi/openapi.json`, and a default CLI run today fails
      closed on the absent source.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from validate_data_exposure import (
    DEFAULT_CONTRACT_PATH,
    FINDING_AMBIGUOUS_TYPE,
    FINDING_INVALID_OPERATION,
    FINDING_INVALID_PATH_ITEM,
    FINDING_INVALID_PATHS,
    FINDING_INVALID_ROOT,
    FINDING_INVALID_SCHEMA,
    FINDING_MISSING_ARRAY_ITEMS,
    FINDING_MISSING_CONTRACT,
    FINDING_MISSING_REQUEST_SCHEMA,
    FINDING_MISSING_RESPONSE_SCHEMA,
    FINDING_MISSING_RESPONSES,
    FINDING_NO_DECLARED_FIELDS,
    FINDING_NO_PATH_OPERATIONS,
    FINDING_PATH_ITEM_WITHOUT_OPERATION,
    FINDING_REQUEST_EXPOSURE,
    FINDING_RESPONSE_EXPOSURE,
    FINDING_UNPARSEABLE_CONTRACT,
    FINDING_UNREADABLE_CONTRACT,
    FINDING_UNRESOLVABLE_REF,
    FINDING_UNSUPPORTED_CONSTRUCT,
    FINDING_UNSUPPORTED_FORMAT,
    FINDING_UNSUPPORTED_INDIRECTION,
    FINDING_UNSUPPORTED_VERSION,
    FINDING_WILDCARD_SCHEMA,
    admits_undeclared_fields,
    declared_field_names,
    evaluate_contract_document,
    run_validation,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VALIDATOR_SCRIPT = REPO_ROOT / "tools" / "validate_data_exposure.py"

# A field name standing in for an internal column that was never part of the
# declared public shape -- the concrete thing a wildcard response leaks.
INTERNAL_COLUMN = "internal_owner_row_id"
# A field name standing in for a hidden field injected past request
# validation.
INJECTED_FIELD = "is_platform_admin"

# Synthetic, never-real fixture values, self-labeling rather than
# plausible-looking per `.claude/rules/infra/secrets.md` control 1. These
# exist only to prove the lint's own report never echoes a contract value.
SENTINEL_EXAMPLE = "EXAMPLE_NOT_A_REAL_VALUE_SENTINEL_A"
SENTINEL_DEFAULT = "EXAMPLE_NOT_A_REAL_VALUE_SENTINEL_B"
SENTINEL_ENUM = "EXAMPLE_NOT_A_REAL_VALUE_SENTINEL_C"
SENTINEL_PATTERN = "EXAMPLE_NOT_A_REAL_VALUE_SENTINEL_D"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _strict_contract() -> dict[str, Any]:
    """The companion positive: every reachable response field explicitly
    declared, every object prohibiting additional fields, with nesting, an
    array of `$ref`-ed items and a strict request body."""
    return {
        "openapi": "3.1.0",
        "info": {"title": "Synthetic MOD-001 fixture", "version": "0.0.0"},
        "paths": {
            "/members/{member_id}": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "Member",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Member"}
                                }
                            },
                        },
                        "204": {"description": "No content"},
                    }
                },
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/MemberCreate"}
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "description": "Created",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Member"}
                                }
                            },
                        }
                    },
                },
            }
        },
        "components": {
            "schemas": {
                "Member": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "member_id": {"type": "string"},
                        "profile": {"$ref": "#/components/schemas/Profile"},
                        "bookings": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/Booking"},
                        },
                    },
                },
                "Profile": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "display_name": {"type": "string"},
                        "locale": {"type": ["string", "null"]},
                    },
                },
                "Booking": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"booking_id": {"type": "string"}},
                },
                "MemberCreate": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"display_name": {"type": "string"}},
                },
            }
        },
    }


def _response_schema_contract(schema: Any) -> dict[str, Any]:
    """A minimal 3.1 contract whose single GET returns `schema`."""
    return {
        "openapi": "3.1.0",
        "paths": {
            "/members": {
                "get": {"responses": {"200": {"content": {"application/json": {"schema": schema}}}}}
            }
        },
    }


def _request_schema_contract(schema: Any) -> dict[str, Any]:
    """A minimal 3.1 contract whose single POST accepts `schema` and returns
    a strict body, so any finding must come from the request side."""
    return {
        "openapi": "3.1.0",
        "paths": {
            "/members": {
                "post": {
                    "requestBody": {"content": {"application/json": {"schema": schema}}},
                    "responses": {
                        "201": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "properties": {"member_id": {"type": "string"}},
                                    }
                                }
                            }
                        }
                    },
                }
            }
        },
    }


def _codes(document: Any) -> list[str]:
    return evaluate_contract_document(document).codes()


def _problems(document: Any) -> list[str]:
    return evaluate_contract_document(document).problems


def _assert_allowed(document: Any) -> None:
    outcome = evaluate_contract_document(document)
    assert not outcome.denied, outcome.problems


def _assert_denied(document: Any, code: str) -> list[str]:
    outcome = evaluate_contract_document(document)
    assert outcome.denied, "expected a denial, got a clean pass"
    matching = [p for p in outcome.problems if f": {code}: " in p]
    assert matching, outcome.problems
    return matching


# ---------------------------------------------------------------------------
# 1-4: the scenario's own two negatives and its companion positive
# ---------------------------------------------------------------------------


def test_wildcard_response_can_leak_an_undeclared_field():
    """SCN-MOD001-126 step (a): a catch-all response shape through which an
    internal column serializes without ever being declared."""
    leaky = {
        "type": "object",
        "additionalProperties": True,
        "properties": {"member_id": {"type": "string"}},
    }

    # The leak, proven at field level: the internal column is not in the
    # declared set, yet the shape admits it anyway.
    assert INTERNAL_COLUMN not in declared_field_names(leaky)
    assert admits_undeclared_fields(leaky) is True

    matching = _assert_denied(_response_schema_contract(leaky), FINDING_RESPONSE_EXPOSURE)
    report = matching[0]
    assert "additionalProperties=true" in report
    assert "declared fields: member_id" in report
    # The report names the offending path, operation and schema location.
    assert "path=/members" in report
    assert "operation=get" in report
    assert "#/paths/~1members/get/responses/200/content/application~1json/schema" in report


def test_request_schema_admits_extra_hidden_field():
    """SCN-MOD001-126 step (b): a request shape that lets an undeclared
    field ride past validation."""
    leaky = {
        "type": "object",
        "properties": {"display_name": {"type": "string"}},
    }

    assert INJECTED_FIELD not in declared_field_names(leaky)
    assert admits_undeclared_fields(leaky) is True

    matching = _assert_denied(_request_schema_contract(leaky), FINDING_REQUEST_EXPOSURE)
    report = matching[0]
    assert "additionalProperties absent" in report
    assert "declared fields: display_name" in report
    assert "path=/members" in report
    assert "operation=post" in report
    assert "requestBody" in report
    # The request rule is reported under its own code, never the response one.
    assert FINDING_RESPONSE_EXPOSURE not in _codes(_request_schema_contract(leaky))


def test_strict_contract_passes():
    outcome = evaluate_contract_document(_strict_contract())
    assert not outcome.denied, outcome.problems
    assert outcome.operations_checked == 2
    assert outcome.response_schemas_checked == 2
    assert outcome.request_schemas_checked == 1


def test_strict_predicates_refuse_the_same_fields():
    schemas = _strict_contract()["components"]["schemas"]
    member, member_create = schemas["Member"], schemas["MemberCreate"]

    assert admits_undeclared_fields(member) is False
    assert INTERNAL_COLUMN not in declared_field_names(member)
    assert declared_field_names(member) == ["bookings", "member_id", "profile"]

    assert admits_undeclared_fields(member_create) is False
    assert INJECTED_FIELD not in declared_field_names(member_create)


# ---------------------------------------------------------------------------
# 5-7: the other admitting constructs
# ---------------------------------------------------------------------------


def test_unrestricted_wildcard_additional_properties_schema_denies():
    schema = {
        "type": "object",
        "additionalProperties": {},
        "properties": {"member_id": {"type": "string"}},
    }
    assert admits_undeclared_fields(schema) is True
    matching = _assert_denied(_response_schema_contract(schema), FINDING_RESPONSE_EXPOSURE)
    assert "unrestricted wildcard schema" in matching[0]


def test_additional_properties_absent_denies():
    schema = {"type": "object", "properties": {"member_id": {"type": "string"}}}
    matching = _assert_denied(_response_schema_contract(schema), FINDING_RESPONSE_EXPOSURE)
    assert "additionalProperties absent" in matching[0]


def test_typed_map_additional_properties_denies():
    schema = {
        "type": "object",
        "additionalProperties": {"type": "string"},
        "properties": {"member_id": {"type": "string"}},
    }
    assert admits_undeclared_fields(schema) is True
    matching = _assert_denied(_response_schema_contract(schema), FINDING_RESPONSE_EXPOSURE)
    assert "constrains values, not field names" in matching[0]


# ---------------------------------------------------------------------------
# 8-11: nesting, $ref and recursion -- no trivial bypass
# ---------------------------------------------------------------------------


def test_nested_inline_object_laxness_is_not_a_bypass():
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "member_id": {"type": "string"},
            "profile": {
                "type": "object",
                "additionalProperties": True,
                "properties": {"display_name": {"type": "string"}},
            },
        },
    }
    matching = _assert_denied(_response_schema_contract(schema), FINDING_RESPONSE_EXPOSURE)
    assert len(matching) == 1, matching
    assert matching[0].split(":")[0].endswith("/schema/properties/profile"), matching[0]


def test_ref_target_laxness_is_not_a_bypass():
    document = _strict_contract()
    document["components"]["schemas"]["Profile"].pop("additionalProperties")
    matching = _assert_denied(document, FINDING_RESPONSE_EXPOSURE)
    # The location carries the whole ref trail, so a reviewer can see which
    # operation reached the lax component.
    assert all("$ref(#/components/schemas/Member)" in m for m in matching), matching
    assert all("$ref(#/components/schemas/Profile)" in m for m in matching), matching


def test_array_item_laxness_is_not_a_bypass():
    document = _strict_contract()
    document["components"]["schemas"]["Booking"]["additionalProperties"] = True
    matching = _assert_denied(document, FINDING_RESPONSE_EXPOSURE)
    assert all("/properties/bookings/items/" in m for m in matching), matching


def test_recursive_ref_terminates():
    document = _response_schema_contract({"$ref": "#/components/schemas/Node"})
    document["components"] = {
        "schemas": {
            "Node": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "node_id": {"type": "string"},
                    "child": {"$ref": "#/components/schemas/Node"},
                    "siblings": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/Node"},
                    },
                },
            }
        }
    }
    _assert_allowed(document)


# ---------------------------------------------------------------------------
# 12-19: fail-closed on constructs this lint does not evaluate
# ---------------------------------------------------------------------------


def test_unresolvable_and_non_local_refs_fail_closed():
    dangling = _response_schema_contract({"$ref": "#/components/schemas/DoesNotExist"})
    _assert_denied(dangling, FINDING_UNRESOLVABLE_REF)

    external = _response_schema_contract({"$ref": "./shared.json#/Member"})
    _assert_denied(external, FINDING_UNRESOLVABLE_REF)

    wrong_section = _response_schema_contract({"$ref": "#/components/responses/Member"})
    _assert_denied(wrong_section, FINDING_UNRESOLVABLE_REF)

    non_string = _response_schema_contract({"$ref": 7})
    _assert_denied(non_string, FINDING_UNRESOLVABLE_REF)


def test_ref_with_schema_sibling_fails_closed():
    document = _strict_contract()
    document["paths"]["/members/{member_id}"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] = {
        "$ref": "#/components/schemas/Member",
        "additionalProperties": True,
    }
    matching = _assert_denied(document, FINDING_UNSUPPORTED_CONSTRUCT)
    assert "additionalProperties" in matching[0]

    # An annotation sibling is fine and does not block the walk.
    document["paths"]["/members/{member_id}"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] = {"$ref": "#/components/schemas/Member", "description": "a member"}
    _assert_allowed(document)


def test_boolean_schemas_fail_closed():
    _assert_denied(_response_schema_contract(True), FINDING_WILDCARD_SCHEMA)
    assert admits_undeclared_fields(True) is True
    _assert_denied(_response_schema_contract(False), FINDING_INVALID_SCHEMA)
    _assert_denied(_response_schema_contract({}), FINDING_WILDCARD_SCHEMA)
    _assert_denied(_response_schema_contract("not-a-schema"), FINDING_INVALID_SCHEMA)


def test_composition_keywords_fail_closed():
    strict_member = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"member_id": {"type": "string"}},
    }
    for keyword in ("allOf", "anyOf", "oneOf"):
        schema = {keyword: [strict_member]}
        matching = _assert_denied(_response_schema_contract(schema), FINDING_UNSUPPORTED_CONSTRUCT)
        assert keyword in matching[0]
    matching = _assert_denied(
        _response_schema_contract({"not": strict_member}), FINDING_UNSUPPORTED_CONSTRUCT
    )
    assert "not" in matching[0]


def test_dynamic_keywords_fail_closed():
    for keyword in ("patternProperties", "unevaluatedProperties", "propertyNames"):
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {"member_id": {"type": "string"}},
            keyword: {},
        }
        matching = _assert_denied(_response_schema_contract(schema), FINDING_UNSUPPORTED_CONSTRUCT)
        assert keyword in matching[0]


def test_ambiguous_type_fails_closed():
    _assert_denied(_response_schema_contract({"description": "shapeless"}), FINDING_AMBIGUOUS_TYPE)
    _assert_denied(_response_schema_contract({"type": ["object", "array"]}), FINDING_AMBIGUOUS_TYPE)
    _assert_denied(_response_schema_contract({"type": "widget"}), FINDING_AMBIGUOUS_TYPE)
    _assert_denied(_response_schema_contract({"type": []}), FINDING_AMBIGUOUS_TYPE)


def test_object_without_declared_properties_fails_closed():
    schema = {"type": "object", "additionalProperties": False}
    codes = _codes(_response_schema_contract(schema))
    assert FINDING_NO_DECLARED_FIELDS in codes, codes
    # Strict-but-empty declares nothing; it does not also admit anything.
    assert FINDING_RESPONSE_EXPOSURE not in codes, codes

    # Declaring nothing *and* admitting anything is two distinct defects.
    codes = _codes(_response_schema_contract({"type": "object", "additionalProperties": True}))
    assert FINDING_NO_DECLARED_FIELDS in codes, codes
    assert FINDING_RESPONSE_EXPOSURE in codes, codes

    _assert_denied(
        _response_schema_contract(
            {
                "type": "object",
                "properties": [],
            }
        ),
        FINDING_INVALID_SCHEMA,
    )


def test_array_without_items_fails_closed():
    _assert_denied(_response_schema_contract({"type": "array"}), FINDING_MISSING_ARRAY_ITEMS)


# ---------------------------------------------------------------------------
# 20-24: document-level structure
# ---------------------------------------------------------------------------


def test_missing_empty_and_non_schema_responses_fail_closed():
    no_responses = {"openapi": "3.1.0", "paths": {"/members": {"get": {}}}}
    _assert_denied(no_responses, FINDING_MISSING_RESPONSES)

    empty_responses = {"openapi": "3.1.0", "paths": {"/members": {"get": {"responses": {}}}}}
    _assert_denied(empty_responses, FINDING_MISSING_RESPONSES)

    no_content = {
        "openapi": "3.1.0",
        "paths": {"/members": {"get": {"responses": {"200": {"description": "ok"}}}}},
    }
    _assert_denied(no_content, FINDING_MISSING_RESPONSE_SCHEMA)

    empty_content = {
        "openapi": "3.1.0",
        "paths": {"/members": {"get": {"responses": {"200": {"content": {}}}}}},
    }
    _assert_denied(empty_content, FINDING_MISSING_RESPONSE_SCHEMA)

    no_schema = {
        "openapi": "3.1.0",
        "paths": {
            "/members": {"get": {"responses": {"200": {"content": {"application/json": {}}}}}}
        },
    }
    _assert_denied(no_schema, FINDING_MISSING_RESPONSE_SCHEMA)

    request_without_content = _request_schema_contract({})
    request_without_content["paths"]["/members"]["post"]["requestBody"] = {"required": True}
    _assert_denied(request_without_content, FINDING_MISSING_REQUEST_SCHEMA)


def test_bodiless_204_response_is_allowed():
    document = {
        "openapi": "3.1.0",
        "paths": {"/members/{member_id}": {"delete": {"responses": {"204": {}}}}},
    }
    _assert_allowed(document)

    # The exception is status-scoped, not a general "no content is fine".
    document["paths"]["/members/{member_id}"]["delete"]["responses"] = {"200": {}}
    _assert_denied(document, FINDING_MISSING_RESPONSE_SCHEMA)


def test_object_level_refs_fail_closed():
    path_item_ref = {"openapi": "3.1.0", "paths": {"/members": {"$ref": "#/components/x"}}}
    _assert_denied(path_item_ref, FINDING_UNSUPPORTED_INDIRECTION)

    response_ref = {
        "openapi": "3.1.0",
        "paths": {
            "/members": {"get": {"responses": {"200": {"$ref": "#/components/responses/Member"}}}}
        },
    }
    _assert_denied(response_ref, FINDING_UNSUPPORTED_INDIRECTION)

    body_ref = _request_schema_contract({})
    body_ref["paths"]["/members"]["post"]["requestBody"] = {
        "$ref": "#/components/requestBodies/MemberCreate"
    }
    _assert_denied(body_ref, FINDING_UNSUPPORTED_INDIRECTION)


def test_invalid_inputs_fail_closed():
    _assert_denied(["not", "an", "object"], FINDING_INVALID_ROOT)
    _assert_denied({"openapi": "3.1.0", "paths": []}, FINDING_INVALID_PATHS)
    _assert_denied({"openapi": "3.1.0", "paths": {"/members": "nope"}}, FINDING_INVALID_PATH_ITEM)
    _assert_denied(
        {"openapi": "3.1.0", "paths": {"/members": {"get": "nope"}}}, FINDING_INVALID_OPERATION
    )
    matching = _assert_denied(
        {"openapi": "3.1.0", "paths": {"/members": {"parameters": [], "kinda": {}}}},
        FINDING_PATH_ITEM_WITHOUT_OPERATION,
    )
    assert "kinda" in matching[0]


def test_unsupported_version_fails_closed():
    for version in ("3.0.3", "3.2.0", "2.0", "3.1", ""):
        document = _strict_contract()
        document["openapi"] = version
        assert _codes(document) == [FINDING_UNSUPPORTED_VERSION], version

    missing = _strict_contract()
    missing.pop("openapi")
    assert _codes(missing) == [FINDING_UNSUPPORTED_VERSION]


# ---------------------------------------------------------------------------
# 25-27: the source boundary
# ---------------------------------------------------------------------------


def test_missing_canonical_contract_source_denies():
    with tempfile.TemporaryDirectory() as tmp:
        absent = Path(tmp) / "contracts" / "openapi" / "openapi.json"
        outcome = run_validation(absent)
        assert outcome.codes() == [FINDING_MISSING_CONTRACT], outcome.problems
        assert outcome.operations_checked == 0


def test_unreadable_unparseable_and_non_json_sources_fail_closed():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # A directory at the contract path is readable-as-a-path but not as
        # a file.
        directory = tmp_path / "openapi.json"
        directory.mkdir()
        assert run_validation(directory).codes() == [FINDING_UNREADABLE_CONTRACT]

        broken = tmp_path / "broken.json"
        broken.write_text("{not json", encoding="utf-8")
        assert run_validation(broken).codes() == [FINDING_UNPARSEABLE_CONTRACT]

        yaml_like = tmp_path / "openapi.yaml"
        yaml_like.write_text("openapi: 3.1.0\n", encoding="utf-8")
        assert run_validation(yaml_like).codes() == [FINDING_UNSUPPORTED_FORMAT]

        good = tmp_path / "openapi.json"
        good.rmdir()
        good.write_text(json.dumps(_strict_contract()), encoding="utf-8")
        outcome = run_validation(good)
        assert not outcome.denied, outcome.problems
        assert outcome.contract_path == str(good)


def test_empty_paths_object_fails_closed():
    assert _codes({"openapi": "3.1.0", "paths": {}}) == [FINDING_NO_PATH_OPERATIONS]
    assert _codes({"openapi": "3.1.0"}) == [FINDING_NO_PATH_OPERATIONS]


# ---------------------------------------------------------------------------
# 28-31: report properties and the CLI
# ---------------------------------------------------------------------------


def test_findings_do_not_echo_contract_values():
    schema = {
        "type": "object",
        "additionalProperties": True,
        "properties": {
            "member_id": {
                "type": "string",
                "example": SENTINEL_EXAMPLE,
                "default": SENTINEL_DEFAULT,
                "enum": [SENTINEL_ENUM],
                "pattern": SENTINEL_PATTERN,
            }
        },
    }
    report = "\n".join(_problems(_response_schema_contract(schema)))
    assert report, "expected a denial"
    for sentinel in (SENTINEL_EXAMPLE, SENTINEL_DEFAULT, SENTINEL_ENUM, SENTINEL_PATTERN):
        assert sentinel not in report, report
    # The declared field *name* is reported -- that is the allowlist, not a value.
    assert "member_id" in report


def test_findings_are_deterministic():
    document = _strict_contract()
    document["components"]["schemas"]["Profile"].pop("additionalProperties")
    document["components"]["schemas"]["Booking"]["additionalProperties"] = True
    first = evaluate_contract_document(copy.deepcopy(document)).problems
    second = evaluate_contract_document(copy.deepcopy(document)).problems
    assert first == second
    assert first == sorted(first)
    assert len(first) > 1, first


def test_cli_exit_code_matches_verdict():
    with tempfile.TemporaryDirectory() as tmp:
        lax = Path(tmp) / "lax.json"
        lax.write_text(
            json.dumps(
                _response_schema_contract(
                    {
                        "type": "object",
                        "additionalProperties": True,
                        "properties": {"member_id": {"type": "string"}},
                    }
                )
            ),
            encoding="utf-8",
        )
        strict = Path(tmp) / "strict.json"
        strict.write_text(json.dumps(_strict_contract()), encoding="utf-8")

        denied = subprocess.run(
            [sys.executable, str(VALIDATOR_SCRIPT), "--contract", str(lax)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert denied.returncode == 1, denied.stdout + denied.stderr
        assert FINDING_RESPONSE_EXPOSURE in denied.stdout

        allowed = subprocess.run(
            [sys.executable, str(VALIDATOR_SCRIPT), "--contract", str(strict)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert allowed.returncode == 0, allowed.stdout + allowed.stderr
        assert "PASS" in allowed.stdout


def test_default_contract_path_is_canonical():
    assert DEFAULT_CONTRACT_PATH == REPO_ROOT / "contracts" / "openapi" / "openapi.json"

    result = subprocess.run(
        [sys.executable, str(VALIDATOR_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    if DEFAULT_CONTRACT_PATH.exists():
        # If a real contract ever lands, the default run must still produce a
        # deterministic verdict and must not be reporting an absent source.
        assert result.returncode in (0, 1), result.stdout + result.stderr
        assert FINDING_MISSING_CONTRACT not in result.stdout
    else:
        # Today's repository state: no `contracts/openapi/` source exists, and
        # this tool denies rather than inventing or creating one.
        assert result.returncode == 1, result.stdout + result.stderr
        assert FINDING_MISSING_CONTRACT in result.stdout
