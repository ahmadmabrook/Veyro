"""
Input/output data-exposure lint (MOD-001, the card's mandatory Security-scope
baseline control "input/output data exposure"; SCN-MOD001-126).

Per `REQUIREMENTS.md`'s own "Input/output data-exposure lint" row (added
Scenario Review round 8, P0-1), the obligation is: "Every OpenAPI response
schema field explicitly declared (no undeclared/wildcard serialization);
every request schema rejects extra/undeclared fields -- a schema-level
allowlist check distinct from the permission lint (action declarations, not
field shape) and from SCN-029/122/043 (committed-file secrets, log
statements, data-classification tagging respectively)".
`IMPLEMENTATION.md` §6 lists it among MOD-001's *own* implementation
obligations, and §3 names the trigger (`contracts/openapi/`), the expected
output ("Named undeclared-response-field or extra-request-field report") and
the reason it is CI-bound ("Runs against the actual committed OpenAPI
contract, not a developer's local, possibly-stale copy").

## What makes this a schema-shape lint and nothing else

The distinction from the other six baseline controls is load-bearing, so
this tool reads exactly one kind of input: a committed OpenAPI contract
document. It never scans source files, never scans log statements, never
looks at data-classification tags, and -- deliberately -- carries **no
known-sensitive-name blacklist and no literal secret scanning**. A field
named `password` is not a finding here; an object shape that can serialize
fields nobody declared *is*, whatever those fields are called. That is the
only property this lint enforces, which is what keeps it orthogonal to
SCN-029 (committed-file secrets), SCN-MOD001-122 (log statements) and
SCN-MOD001-043 (classification tagging).

## The two rules

  * **Response shapes** -- every object shape reachable from a path
    operation's responses must declare its serialized fields
    (`properties`) *and* prohibit arbitrary additional ones
    (`additionalProperties: false`). An absent `additionalProperties`, a
    `true`, an unrestricted `{}`, a bare `true` boolean schema, or a typed
    map (`additionalProperties: {"type": "string"}`) all permit field names
    outside the declared set, so all are denied: that is exactly how an
    internal column leaks through a catch-all response shape.
  * **Request shapes** -- every object shape reachable from a path
    operation's `requestBody` must likewise set
    `additionalProperties: false`, so an undeclared field cannot ride past
    validation (hidden-field injection).

Both rules follow nested objects, array `items`, and local
`#/components/schemas/...` `$ref` indirection, because a shape that is
strict at the top level and permissive two levels down leaks just as
freely. Laxness cannot be hidden behind a `$ref` or inside an array.

## Why a wildcard finding cites a location and an allowlist, not a field name

The scenario's wording ("denied, citing the undeclared field") cannot be
satisfied literally for the wildcard case, and saying so is better than
faking it: a schema that permits additional properties admits *infinitely
many* undeclared names, so there is no single field to name. Each finding
therefore cites the exact JSON-Pointer location of the admitting object,
the construct that admits (`absent` / `true` / `{}` / typed map) and the
declared allowlist the leak would fall outside of -- which is the
actionable report. The field-level claim is instead discharged
mechanically: `declared_field_names()` and `admits_undeclared_fields()` are
exported, and the focused tests use them to prove that a named undeclared
field (an internal column) is admitted by the wildcard fixture and refused
by the strict one.

## Its own diagnostics do not echo contract values

Findings carry schema *locations*, *field names* and *construct kinds*
only. No `example`, `examples`, `default`, `enum`, `const` or `pattern`
value from the contract is ever printed, because those are the places a
contract author is most likely to have pasted a real-looking payload, and a
lint whose denial republishes it into a CI log has moved the exposure, not
closed it.

## Fail-closed rule

"Cannot determine the shape" always resolves to deny, never to "assume
strict". The repository has **no `contracts/openapi/` source yet** -- this
tool does not invent one and does not create one, so a default run today
exits nonzero with `MISSING_CONTRACT_SOURCE`. Every other
unreadable/unparseable/unsupported/ambiguous construct is its own named
code (see the `FINDING_*` constants): a composition keyword
(`allOf`/`anyOf`/`oneOf`/`not`) whose `additionalProperties` interaction
this tool does not attempt to evaluate, a dynamic-key construct
(`patternProperties`, `unevaluatedProperties`, ...), a schema with no
determinable type, an object declaring zero fields, a response with no
schema, a non-local or dangling `$ref`. None of them is a silent skip, and
none of them can produce a PASS.

Deliberately dependency-free (stdlib only, `json` + `argparse`), matching
`validate_migration_ordering.py`'s stated "zero new dependencies"
convention and `validate_sensitive_logging.py`'s structure. No JSON-Schema
validator is imported: this is a static shape lint, not a payload
validator.

## Deliberate bounds, stated plainly (not a generic OpenAPI framework)

  * **JSON only.** OpenAPI 3.1 JSON is the minimum and only supported
    contract encoding; a non-`.json` contract path is
    `UNSUPPORTED_CONTRACT_FORMAT` rather than a YAML parse attempt (no
    stdlib YAML parser exists, and adding a dependency is out of scope).
  * **Version pinned to 3.1.x.** 3.0.x is rejected (its `nullable`/schema
    dialect differs), and so is anything above 3.1.x, because this tool's
    reading of those semantics is unverified. Fail-closed direction.
  * **Reachability is "from `paths`".** `components` entries no path
    operation reaches, and `webhooks`, are out of scope by construction --
    an unreachable shape serializes nothing. `$ref` at the path-item,
    response-object or requestBody-object level (as opposed to inside a
    schema) is unsupported and denied rather than resolved.
  * **Operation `parameters` are out of scope.** They are scalar-ish
    inputs, not object body shapes; the request rule this scenario names is
    about the request *body* admitting undeclared fields.
  * **A typed map is denied.** `additionalProperties: {"type": "string"}`
    is a legitimate shape in many real APIs, and this lint still denies it,
    because it constrains value types without constraining field *names*.
    A future module that needs a genuine map must declare it some other way
    or amend this rule explicitly -- the conservative direction is the only
    safe default for an exposure gate.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONTRACT_PATH = REPO_ROOT / "contracts" / "openapi" / "openapi.json"

# --- source-level fail-closed codes ---------------------------------------
FINDING_MISSING_CONTRACT = "MISSING_CONTRACT_SOURCE"
FINDING_UNREADABLE_CONTRACT = "UNREADABLE_CONTRACT_SOURCE"
FINDING_UNPARSEABLE_CONTRACT = "UNPARSEABLE_CONTRACT_SOURCE"
FINDING_UNSUPPORTED_FORMAT = "UNSUPPORTED_CONTRACT_FORMAT"
FINDING_INVALID_ROOT = "INVALID_CONTRACT_ROOT"
FINDING_UNSUPPORTED_VERSION = "UNSUPPORTED_CONTRACT_VERSION"
FINDING_NO_PATH_OPERATIONS = "NO_PATH_OPERATIONS"

# --- document-structure fail-closed codes ---------------------------------
FINDING_INVALID_PATHS = "INVALID_PATHS_OBJECT"
FINDING_INVALID_PATH_ITEM = "INVALID_PATH_ITEM"
FINDING_PATH_ITEM_WITHOUT_OPERATION = "PATH_ITEM_WITHOUT_OPERATION"
FINDING_INVALID_OPERATION = "INVALID_OPERATION_OBJECT"
FINDING_MISSING_RESPONSES = "MISSING_RESPONSES_OBJECT"
FINDING_INVALID_RESPONSE = "INVALID_RESPONSE_OBJECT"
FINDING_MISSING_RESPONSE_SCHEMA = "MISSING_RESPONSE_SCHEMA"
FINDING_INVALID_REQUEST_BODY = "INVALID_REQUEST_BODY_OBJECT"
FINDING_MISSING_REQUEST_SCHEMA = "MISSING_REQUEST_SCHEMA"
FINDING_UNSUPPORTED_INDIRECTION = "UNSUPPORTED_OBJECT_REF"

# --- schema fail-closed codes ---------------------------------------------
FINDING_INVALID_SCHEMA = "INVALID_SCHEMA_OBJECT"
FINDING_WILDCARD_SCHEMA = "WILDCARD_SCHEMA"
FINDING_AMBIGUOUS_TYPE = "AMBIGUOUS_SCHEMA_TYPE"
FINDING_UNSUPPORTED_CONSTRUCT = "UNSUPPORTED_SCHEMA_CONSTRUCT"
FINDING_UNRESOLVABLE_REF = "UNRESOLVABLE_SCHEMA_REF"
FINDING_NO_DECLARED_FIELDS = "NO_DECLARED_OBJECT_FIELDS"
FINDING_MISSING_ARRAY_ITEMS = "MISSING_ARRAY_ITEMS"

# --- the two SCN-MOD001-126 exposure codes --------------------------------
FINDING_RESPONSE_EXPOSURE = "UNDECLARED_RESPONSE_FIELDS_PERMITTED"
FINDING_REQUEST_EXPOSURE = "UNDECLARED_REQUEST_FIELDS_PERMITTED"

ROLE_RESPONSE = "response"
ROLE_REQUEST = "request"
_EXPOSURE_CODE_BY_ROLE = {
    ROLE_RESPONSE: FINDING_RESPONSE_EXPOSURE,
    ROLE_REQUEST: FINDING_REQUEST_EXPOSURE,
}

SUPPORTED_VERSION_RE = re.compile(r"^3\.1\.\d+$")
SUPPORTED_CONTRACT_SUFFIX = ".json"

# OpenAPI 3.1 fixed operation keys. Anything else in a path item is either a
# known non-operation field (ignored) or unsupported indirection (denied).
OPERATION_METHODS = (
    "get",
    "put",
    "post",
    "delete",
    "options",
    "head",
    "patch",
    "trace",
)
_IGNORED_PATH_ITEM_KEYS = frozenset({"summary", "description", "servers", "parameters"})

# The only status codes allowed to carry no response body at all. Any other
# response without `content` is MISSING_RESPONSE_SCHEMA, not an implied
# empty body.
_BODILESS_STATUS_CODES = frozenset({"204", "304"})

_SCHEMA_REF_PREFIX = "#/components/schemas/"

_SCALAR_TYPES = frozenset({"string", "number", "integer", "boolean", "null"})
_KNOWN_TYPES = _SCALAR_TYPES | {"object", "array"}

# Composition keywords: their interaction with `additionalProperties` is the
# single most common way a strict-looking schema is not strict. This tool
# does not attempt to evaluate it and denies instead.
_UNSUPPORTED_COMPOSITION_KEYWORDS = ("allOf", "anyOf", "oneOf", "not")

# Dynamic-key / conditional constructs whose effective field set cannot be
# read off the schema statically.
_UNSUPPORTED_DYNAMIC_KEYWORDS = (
    "$dynamicRef",
    "$recursiveRef",
    "additionalItems",
    "contains",
    "dependentRequired",
    "dependentSchemas",
    "discriminator",
    "else",
    "if",
    "patternProperties",
    "prefixItems",
    "propertyNames",
    "then",
    "unevaluatedItems",
    "unevaluatedProperties",
)

# Annotation keywords that may sit beside a `$ref` without making the schema
# ambiguous. Any other sibling is denied.
_ALLOWED_REF_SIBLINGS = frozenset(
    {
        "$ref",
        "default",
        "deprecated",
        "description",
        "example",
        "examples",
        "readOnly",
        "title",
        "writeOnly",
    }
)

# Cap on how many declared field names a single finding prints, so a wide
# object cannot produce an unbounded diagnostic.
_MAX_REPORTED_FIELDS = 12


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """One denial, carrying the JSON-Pointer location plus the path/operation
    `IMPLEMENTATION.md` §3 names as this lint's required output shape.

    `detail` never contains a value drawn from the contract (no example,
    default, enum, const or pattern) -- only field names, construct kinds and
    locations.
    """

    location: str
    code: str
    detail: str
    api_path: str | None = None
    method: str | None = None

    def __str__(self) -> str:
        where = ""
        if self.api_path is not None:
            where = f" [path={self.api_path} operation={self.method or '-'}]"
        return f"{self.location}: {self.code}: {self.detail}{where}"

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return (self.location, self.code, self.detail)


@dataclass
class ValidationOutcome:
    """Findings plus the counters the CLI needs to tell a real pass from a
    vacuous one, resolved in a single pass (the `ValidationOutcome` shape
    `validate_migration_ordering.py` adopted for its R4-1 finding: never
    re-probe the source to decide which notice to print)."""

    findings: list[Finding] = field(default_factory=list)
    contract_path: str = ""
    operations_checked: int = 0
    response_schemas_checked: int = 0
    request_schemas_checked: int = 0

    @property
    def problems(self) -> list[str]:
        return [str(f) for f in sorted(self.findings, key=lambda f: f.sort_key)]

    @property
    def denied(self) -> bool:
        return bool(self.findings)

    def codes(self) -> list[str]:
        return [f.code for f in sorted(self.findings, key=lambda f: f.sort_key)]


# ---------------------------------------------------------------------------
# Exported field-shape predicates
# ---------------------------------------------------------------------------


def declared_field_names(schema: Any) -> list[str]:
    """The explicitly declared serialized field names of an object schema.

    Does not resolve `$ref` -- it answers only about the schema node handed
    to it, which is what makes it usable as an allowlist assertion in tests.
    """
    if not isinstance(schema, dict):
        return []
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []
    return sorted(str(name) for name in properties)


def admits_undeclared_fields(schema: Any) -> bool:
    """True when the schema node permits a field name outside its own
    declared set -- the exact property SCN-MOD001-126 exists to forbid.

    `additionalProperties: false` is the only strict form. Absent, `true`,
    `{}` and a typed map all admit undeclared names (a typed map constrains
    value types, never names).
    """
    if schema is True:
        return True
    if not isinstance(schema, dict):
        return False
    if "additionalProperties" not in schema:
        return True
    return schema["additionalProperties"] is not False


def _describe_additional_properties(schema: Any) -> str:
    """Name the admitting construct without echoing any contract value."""
    if schema is True:
        return "bare true schema"
    if not isinstance(schema, dict):
        return "non-object schema"
    if "additionalProperties" not in schema:
        return "additionalProperties absent"
    value = schema["additionalProperties"]
    if value is True:
        return "additionalProperties=true"
    if isinstance(value, dict):
        if not value:
            return "additionalProperties={} (unrestricted wildcard schema)"
        return "additionalProperties=<typed map schema> (constrains values, not field names)"
    return f"additionalProperties=<{type(value).__name__}>"


def _format_field_list(names: list[str]) -> str:
    if not names:
        return "none"
    shown = names[:_MAX_REPORTED_FIELDS]
    suffix = "" if len(names) <= _MAX_REPORTED_FIELDS else f", +{len(names) - len(shown)} more"
    return ", ".join(shown) + suffix


# ---------------------------------------------------------------------------
# JSON-Pointer locations
# ---------------------------------------------------------------------------


def _escape(segment: str) -> str:
    return str(segment).replace("~", "~0").replace("/", "~1")


def _child(location: str, *segments: str) -> str:
    return location + "".join(f"/{_escape(s)}" for s in segments)


# ---------------------------------------------------------------------------
# Schema walk
# ---------------------------------------------------------------------------


class _SchemaChecker:
    """Walks every schema reachable from a path operation, collecting
    findings. One instance per contract document."""

    def __init__(self, components_schemas: Any) -> None:
        self._components = components_schemas if isinstance(components_schemas, dict) else {}
        self.findings: list[Finding] = []
        self._api_path: str | None = None
        self._method: str | None = None

    # -- bookkeeping -------------------------------------------------------

    def set_operation(self, api_path: str | None, method: str | None) -> None:
        self._api_path = api_path
        self._method = method

    def add(self, location: str, code: str, detail: str) -> None:
        self.findings.append(
            Finding(
                location=location,
                code=code,
                detail=detail,
                api_path=self._api_path,
                method=self._method,
            )
        )

    # -- the walk ----------------------------------------------------------

    def check_schema(
        self,
        schema: Any,
        location: str,
        role: str,
        visited: frozenset[str] = frozenset(),
    ) -> None:
        """Check one schema node and everything reachable from it.

        `visited` carries the resolved `$ref` pointers already entered on
        this branch, which makes a recursive schema terminate after its
        shape has been checked once (a cycle is finite, not a finding).
        """
        # JSON-Schema boolean forms. `true` admits anything -> wildcard;
        # `false` admits nothing, which is not a serializable shape.
        if schema is True:
            self.add(
                location,
                FINDING_WILDCARD_SCHEMA,
                "bare `true` schema permits any shape, so no field is declared",
            )
            return
        if schema is False:
            self.add(
                location,
                FINDING_INVALID_SCHEMA,
                "bare `false` schema admits no value and declares no serializable shape",
            )
            return
        if not isinstance(schema, dict):
            self.add(
                location,
                FINDING_INVALID_SCHEMA,
                f"schema must be an object or boolean, got {type(schema).__name__}",
            )
            return

        if "$ref" in schema:
            self._check_ref(schema, location, role, visited)
            return

        if not schema:
            self.add(
                location,
                FINDING_WILDCARD_SCHEMA,
                "empty schema `{}` permits any shape, so no field is declared",
            )
            return

        if self._reject_unsupported_keywords(schema, location):
            return

        resolved_type = self._resolve_type(schema, location)
        if resolved_type is None:
            return
        if resolved_type == "object":
            self._check_object(schema, location, role, visited)
        elif resolved_type == "array":
            self._check_array(schema, location, role, visited)
        # Scalar shapes declare no fields, so there is nothing further to do.

    def _check_ref(
        self, schema: dict[str, Any], location: str, role: str, visited: frozenset[str]
    ) -> None:
        ref = schema["$ref"]
        unexpected = sorted(set(schema) - _ALLOWED_REF_SIBLINGS)
        if unexpected:
            self.add(
                location,
                FINDING_UNSUPPORTED_CONSTRUCT,
                f"`$ref` combined with schema keyword(s) {', '.join(unexpected)}; "
                "the effective field set is ambiguous",
            )
            return
        if not isinstance(ref, str) or not ref.startswith(_SCHEMA_REF_PREFIX):
            self.add(
                location,
                FINDING_UNRESOLVABLE_REF,
                "only local `#/components/schemas/<name>` references are supported",
            )
            return
        name = ref[len(_SCHEMA_REF_PREFIX) :]
        if "/" in name or not name or name not in self._components:
            self.add(
                location,
                FINDING_UNRESOLVABLE_REF,
                f"reference target `{_SCHEMA_REF_PREFIX}{name}` is not a declared component schema",
            )
            return
        if ref in visited:
            # Recursive shape: already checked on this branch.
            return
        # The ref trail is appended verbatim, not pointer-escaped: a reader
        # needs to see `#/components/schemas/Member`, not its escaped form.
        self.check_schema(
            self._components[name],
            f"{location}/$ref({ref})",
            role,
            visited | {ref},
        )

    def _reject_unsupported_keywords(self, schema: dict[str, Any], location: str) -> bool:
        present = [kw for kw in _UNSUPPORTED_COMPOSITION_KEYWORDS if kw in schema]
        if present:
            self.add(
                location,
                FINDING_UNSUPPORTED_CONSTRUCT,
                f"composition keyword(s) {', '.join(present)}: this lint does not evaluate "
                "their interaction with additionalProperties and fails closed",
            )
            return True
        present = [kw for kw in _UNSUPPORTED_DYNAMIC_KEYWORDS if kw in schema]
        if present:
            self.add(
                location,
                FINDING_UNSUPPORTED_CONSTRUCT,
                f"dynamic/conditional keyword(s) {', '.join(present)}: the effective field "
                "set cannot be read statically",
            )
            return True
        return False

    def _resolve_type(self, schema: dict[str, Any], location: str) -> str | None:
        """Return "object", "array", "scalar", or None (a finding was added).

        A `type` list is accepted for the nullable idiom (`["object",
        "null"]`); a list mixing object and array, or object and a scalar,
        is ambiguous and denied.
        """
        declared = schema.get("type")
        if declared is None:
            if "properties" in schema or "additionalProperties" in schema:
                return "object"
            if "items" in schema:
                return "array"
            self.add(
                location,
                FINDING_AMBIGUOUS_TYPE,
                "schema declares no `type` and no `properties`/`items`, so its serialized "
                "shape cannot be determined",
            )
            return None

        if isinstance(declared, str):
            members = [declared]
        elif isinstance(declared, list) and declared and all(isinstance(m, str) for m in declared):
            members = list(declared)
        else:
            self.add(
                location,
                FINDING_AMBIGUOUS_TYPE,
                "`type` must be a string or a non-empty list of strings",
            )
            return None

        unknown = sorted({m for m in members if m not in _KNOWN_TYPES})
        if unknown:
            self.add(
                location,
                FINDING_AMBIGUOUS_TYPE,
                f"unknown `type` value(s) {', '.join(unknown)}",
            )
            return None

        significant = sorted({m for m in members if m != "null"})
        if len(significant) > 1:
            self.add(
                location,
                FINDING_AMBIGUOUS_TYPE,
                f"`type` union {', '.join(significant)} mixes shapes; the serialized field "
                "set is ambiguous",
            )
            return None
        if not significant:
            return "scalar"
        only = significant[0]
        return only if only in ("object", "array") else "scalar"

    def _check_object(
        self, schema: dict[str, Any], location: str, role: str, visited: frozenset[str]
    ) -> None:
        properties = schema.get("properties")
        if properties is not None and not isinstance(properties, dict):
            self.add(
                location,
                FINDING_INVALID_SCHEMA,
                "`properties` must be an object",
            )
            return

        names = declared_field_names(schema)
        if not names:
            self.add(
                location,
                FINDING_NO_DECLARED_FIELDS,
                "object schema declares no `properties`, so no serialized field is "
                "explicitly declared",
            )
            # Still report an admitting construct below: an object that both
            # declares nothing and admits anything is two distinct defects.

        if admits_undeclared_fields(schema):
            self.add(
                location,
                _EXPOSURE_CODE_BY_ROLE[role],
                f"object shape permits field names outside its declared set "
                f"({_describe_additional_properties(schema)}); declared fields: "
                f"{_format_field_list(names)}",
            )

        for name in names:
            self.check_schema(
                properties[name],
                _child(location, "properties", name),
                role,
                visited,
            )

    def _check_array(
        self, schema: dict[str, Any], location: str, role: str, visited: frozenset[str]
    ) -> None:
        if "items" not in schema:
            self.add(
                location,
                FINDING_MISSING_ARRAY_ITEMS,
                "array schema declares no `items`, so its element shape is undetermined",
            )
            return
        self.check_schema(schema["items"], _child(location, "items"), role, visited)


# ---------------------------------------------------------------------------
# Document walk
# ---------------------------------------------------------------------------


def _check_content(
    checker: _SchemaChecker,
    content: Any,
    location: str,
    role: str,
    missing_schema_code: str,
) -> int:
    """Check every media type's schema. Returns the number checked."""
    if not isinstance(content, dict) or not content:
        checker.add(
            location,
            missing_schema_code,
            "`content` is missing, empty or not an object, so no body shape is declared",
        )
        return 0
    checked = 0
    for media_type in sorted(content):
        media_location = _child(location, media_type)
        media_object = content[media_type]
        if not isinstance(media_object, dict):
            checker.add(
                media_location,
                missing_schema_code,
                "media-type object must be an object",
            )
            continue
        if "schema" not in media_object:
            checker.add(
                media_location,
                missing_schema_code,
                "media-type object declares no `schema`, so its field set is undeclared",
            )
            continue
        checker.check_schema(media_object["schema"], _child(media_location, "schema"), role)
        checked += 1
    return checked


def _check_responses(checker: _SchemaChecker, operation: dict[str, Any], location: str) -> int:
    responses = operation.get("responses")
    if not isinstance(responses, dict) or not responses:
        checker.add(
            _child(location, "responses"),
            FINDING_MISSING_RESPONSES,
            "operation declares no non-empty `responses` object",
        )
        return 0
    checked = 0
    for status in sorted(responses, key=str):
        status_location = _child(location, "responses", str(status))
        response = responses[status]
        if not isinstance(response, dict):
            checker.add(
                status_location,
                FINDING_INVALID_RESPONSE,
                "response object must be an object",
            )
            continue
        if "$ref" in response:
            checker.add(
                status_location,
                FINDING_UNSUPPORTED_INDIRECTION,
                "`$ref` at the response-object level is not resolved by this lint; "
                "reference a component *schema* instead",
            )
            continue
        if "content" not in response:
            if str(status) in _BODILESS_STATUS_CODES:
                continue
            checker.add(
                status_location,
                FINDING_MISSING_RESPONSE_SCHEMA,
                f"response declares no `content` and status `{status}` is not a bodiless "
                f"status ({', '.join(sorted(_BODILESS_STATUS_CODES))})",
            )
            continue
        checked += _check_content(
            checker,
            response["content"],
            _child(status_location, "content"),
            ROLE_RESPONSE,
            FINDING_MISSING_RESPONSE_SCHEMA,
        )
    return checked


def _check_request_body(checker: _SchemaChecker, operation: dict[str, Any], location: str) -> int:
    if "requestBody" not in operation:
        return 0
    request_body = operation["requestBody"]
    body_location = _child(location, "requestBody")
    if not isinstance(request_body, dict):
        checker.add(
            body_location,
            FINDING_INVALID_REQUEST_BODY,
            "requestBody object must be an object",
        )
        return 0
    if "$ref" in request_body:
        checker.add(
            body_location,
            FINDING_UNSUPPORTED_INDIRECTION,
            "`$ref` at the requestBody-object level is not resolved by this lint; "
            "reference a component *schema* instead",
        )
        return 0
    return _check_content(
        checker,
        request_body.get("content"),
        _child(body_location, "content"),
        ROLE_REQUEST,
        FINDING_MISSING_REQUEST_SCHEMA,
    )


def evaluate_contract_document(document: Any) -> ValidationOutcome:
    """Check an already-parsed OpenAPI document. Exposed so the focused tests
    can drive synthetic fixtures without writing a production contract."""
    outcome = ValidationOutcome()

    if not isinstance(document, dict):
        outcome.findings.append(
            Finding(
                "#",
                FINDING_INVALID_ROOT,
                f"contract root must be a JSON object, got {type(document).__name__}",
            )
        )
        return outcome

    version = document.get("openapi")
    if not isinstance(version, str) or not SUPPORTED_VERSION_RE.match(version):
        outcome.findings.append(
            Finding(
                "#/openapi",
                FINDING_UNSUPPORTED_VERSION,
                "only OpenAPI 3.1.x is supported; this lint fails closed rather than "
                "guessing an unverified dialect's additionalProperties semantics",
            )
        )
        return outcome

    paths = document.get("paths")
    if paths is not None and not isinstance(paths, dict):
        outcome.findings.append(
            Finding("#/paths", FINDING_INVALID_PATHS, "`paths` must be an object")
        )
        return outcome
    if not paths:
        outcome.findings.append(
            Finding(
                "#/paths",
                FINDING_NO_PATH_OPERATIONS,
                "contract declares no path operations; failing closed rather than "
                "reporting a vacuous pass over an empty surface",
            )
        )
        return outcome

    components = document.get("components")
    components_schemas = components.get("schemas") if isinstance(components, dict) else None
    checker = _SchemaChecker(components_schemas)

    for api_path in sorted(paths):
        path_location = _child("#/paths", api_path)
        path_item = paths[api_path]
        checker.set_operation(api_path, None)
        if not isinstance(path_item, dict):
            checker.add(path_location, FINDING_INVALID_PATH_ITEM, "path item must be an object")
            continue
        if "$ref" in path_item:
            checker.add(
                path_location,
                FINDING_UNSUPPORTED_INDIRECTION,
                "`$ref` at the path-item level is not resolved by this lint",
            )
            continue
        methods = [m for m in OPERATION_METHODS if m in path_item]
        if not methods:
            unexpected = sorted(set(path_item) - _IGNORED_PATH_ITEM_KEYS)
            checker.add(
                path_location,
                FINDING_PATH_ITEM_WITHOUT_OPERATION,
                "path item declares no HTTP operation"
                + (f"; unrecognized key(s): {', '.join(unexpected)}" if unexpected else ""),
            )
            continue
        for method in methods:
            operation = path_item[method]
            operation_location = _child(path_location, method)
            checker.set_operation(api_path, method)
            if not isinstance(operation, dict):
                checker.add(
                    operation_location,
                    FINDING_INVALID_OPERATION,
                    "operation object must be an object",
                )
                continue
            outcome.operations_checked += 1
            outcome.response_schemas_checked += _check_responses(
                checker, operation, operation_location
            )
            outcome.request_schemas_checked += _check_request_body(
                checker, operation, operation_location
            )

    outcome.findings.extend(checker.findings)
    return outcome


# ---------------------------------------------------------------------------
# Source loading (fail-closed)
# ---------------------------------------------------------------------------


def run_validation(contract_path: Path) -> ValidationOutcome:
    """Load and check the canonical contract, failing closed on a source that
    is missing, unreadable, not JSON, or not an OpenAPI 3.1 document.

    The repository has no `contracts/openapi/` source yet, so a default run
    denies with `MISSING_CONTRACT_SOURCE`. That is the intended behaviour:
    this tool never invents or creates a contract to validate.
    """
    outcome = ValidationOutcome(contract_path=str(contract_path))

    if contract_path.suffix.lower() != SUPPORTED_CONTRACT_SUFFIX:
        outcome.findings.append(
            Finding(
                str(contract_path),
                FINDING_UNSUPPORTED_FORMAT,
                f"only a `{SUPPORTED_CONTRACT_SUFFIX}` OpenAPI 3.1 contract is supported "
                "(stdlib-only, no YAML parser)",
            )
        )
        return outcome

    if not contract_path.exists():
        outcome.findings.append(
            Finding(
                str(contract_path),
                FINDING_MISSING_CONTRACT,
                "canonical OpenAPI contract source does not exist; failing closed rather "
                "than reporting a pass over a contract that was never read",
            )
        )
        return outcome

    try:
        raw = contract_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        outcome.findings.append(
            Finding(
                str(contract_path),
                FINDING_UNREADABLE_CONTRACT,
                f"contract source could not be read ({type(exc).__name__})",
            )
        )
        return outcome

    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        outcome.findings.append(
            Finding(
                f"{contract_path}:{exc.lineno}",
                FINDING_UNPARSEABLE_CONTRACT,
                f"contract source is not valid JSON ({exc.msg})",
            )
        )
        return outcome

    document_outcome = evaluate_contract_document(document)
    document_outcome.contract_path = str(contract_path)
    return document_outcome


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Input/output data-exposure lint (MOD-001, SCN-MOD001-126). "
        "Denies any OpenAPI 3.1 path-operation response shape that does not "
        "explicitly declare its serialized fields and prohibit additional ones, and "
        "any request body shape that admits undeclared fields. Schema-level only: no "
        "name blacklist, no secret scanning. Dependency-free, fails closed on a "
        "missing/unreadable contract and on any construct it cannot evaluate.",
    )
    p.add_argument(
        "--contract",
        type=Path,
        default=DEFAULT_CONTRACT_PATH,
        help=f"Path to the canonical OpenAPI 3.1 JSON contract "
        f"(default: {DEFAULT_CONTRACT_PATH.relative_to(REPO_ROOT)}). A missing file is a "
        f"denial, never a skip.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    outcome = run_validation(args.contract)

    print("=" * 70)
    print("MOD-001 INPUT/OUTPUT DATA-EXPOSURE LINT (SCN-MOD001-126)")
    print("=" * 70)
    print(f"\nContract: {outcome.contract_path}")
    print(f"Operations checked: {outcome.operations_checked}")
    print(f"Response schemas checked: {outcome.response_schemas_checked}")
    print(f"Request schemas checked: {outcome.request_schemas_checked}")

    if outcome.denied:
        print(f"\nDENY: {len(outcome.findings)} problem(s) found:")
        for problem in outcome.problems:
            print(f"  - {problem}")
        return 1

    print(
        "\nPASS - every reachable response shape declares its serialized fields and "
        "prohibits additional ones, and every request shape rejects undeclared fields."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
