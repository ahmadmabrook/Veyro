"""A malformed identifier answers 422, everywhere, and a structural sweep that keeps it so.

**MOD-009 closed this for its own routes and named the rest as a gap**: `require_uuid` guards
every privacy route, and `POST /brands` and its siblings still answered 500 with a database
exception. The behavioural cases below are what prove the fix; the sweep is what stops the next
module re-opening it, because a per-route list has to be edited when somebody adds a route and
that edit is the moment one slips through -- this repository's own rule about per-table lists,
applied to the request path.

**Why a 500 here is worse than it looks.** `psycopg` raises `InvalidTextRepresentation` for a
value that is not a uuid, which no handler catches, so the caller gets a stack-trace-shaped
answer to a request they got wrong -- and the error names the column, which is a small
disclosure about the schema to somebody who may hold nothing. A 422 says "that is not an id"
and nothing else.
"""

from __future__ import annotations

import ast
import pathlib
import unittest
import uuid
from typing import Any

from tests.support import GatedApiTestCase

#: The callables that make an identifier safe to pass on. Three shape-check it and one does
#: something else that is sufficient:
#:
#: * `require_uuid` and `optional_uuid` are the shape check.
#: * `consent_subject` derives MOD-009's subject and calls `optional_uuid` itself.
#: * `_b64` and `_b64url` are for a WebAuthn credential id, which is base64 rather than a uuid.
#:   **`_b64url` is the strict one and is what every WebAuthn field now uses**: the two
#:   alphabets agree on most byte strings and differ on the rest, so accepting either would
#:   mean one credential id decoding to two different byte strings depending on which decoder
#:   saw it. Adding it here rather than widening the pattern is the point -- a validator is
#:   named, not inferred.
#: * **`owned` is not a shape check and is still enough.** It refuses anything that is not the
#:   session's own identity id with a 404, so a malformed value -- which can never equal a real
#:   uuid -- stops there. A second check behind it would be a second spelling of the same rule.
#: * **`require_uuids` is the repeated-query-parameter form.** A batched read takes
#:   `identity_id` several times over, and a comprehension calling `require_uuid` per element
#:   passes the loop variable, so this sweep -- which reads names -- would report the
#:   parameter unwrapped. One call taking the parameter itself is the shape the sweep can see,
#:   and it bounds the count as well, because an unbounded repeated parameter is a request
#:   whose cost the caller chooses.
VALIDATORS = frozenset({
    "require_uuid", "optional_uuid", "require_uuids", "_b64", "_b64url", "consent_subject",
    "owned"})

#: Parameter names that are never an entity id. `tenant_id` is the header, validated by its own
#: dependency; `correlation_id` is a trace handle that every route carries.
NOT_AN_ENTITY = frozenset({"tenant_id", "correlation_id"})

#: Routes whose `_id` body field is deliberately **not** a uuid, with the reason. Each entry is
#: a claim about a column, and the test below checks the claim rather than trusting it.
NOT_A_UUID: dict[tuple[str, str], tuple[str, str, str]] = {
    ("POST", "/authz/approvals"): (
        "resource_id", "iam.approval_requests", "resource_id",
    ),
    # **MOD-005's exposure subject is caller-chosen text on purpose**, which MOD-010's review
    # made a finding about from the other side: a reviewer put an email address and a lab
    # result in it, and the remedy was to hash it in the *event* rather than to constrain the
    # column. So these three are not uuids and must not be checked as though they were.
    ("POST", "/experiments/{experiment_key}/allocate"): (
        "subject_id", "plt01.cfg_exposures", "subject_id",
    ),
    ("GET", "/flags"): ("subject_id", "plt01.cfg_exposures", "subject_id"),
    ("GET", "/config/bundle"): ("subject_id", "plt01.cfg_exposures", "subject_id"),
    ("POST", "/platform/tenants"): (
        "actor_id", "", "",
    ),
}

#: Why the one entry with no column behind it is exempt. `/platform/tenants` goes through the S0
#: envelope validator, which checks `actor_id` before the service sees it -- a second check in
#: the route would be a second spelling of the same rule.
ENVELOPE_VALIDATED = {("POST", "/platform/tenants")}


def _routes_with_unwrapped_ids() -> list[tuple[str, str, list[str]]]:
    """Every route that passes an id to something other than a validator.

    **Both classes, because the first version swept only one.** A body field and a path or
    query parameter reach the same columns, and `/config/resolved` took `brand_id` as a query
    string -- so a sweep over bodies alone passed while fifteen routes answered 500 to a
    malformed one in the URL.

    Read with `ast` rather than by grep, for `GateCoverageTests`' reason: a text search over
    `main.py` cannot tell which route a line belongs to, so a field validated in *one* route
    would read as validated in all of them -- which is how the first version of this sweep
    reported zero. It also visited only module-level functions, so every route, nested inside
    `create_app`, was invisible to it.
    """
    source = pathlib.Path("app/main.py").read_text()
    out: list[tuple[str, str, list[str]]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        routes = [
            (decorator.func.attr.upper(), decorator.args[0].value)
            for decorator in node.decorator_list
            if isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr in ("get", "post", "put", "patch", "delete")
            and decorator.args
            and isinstance(decorator.args[0], ast.Constant)
        ]
        if not routes:
            continue
        parameters = {
            argument.arg
            for argument in [*node.args.args, *node.args.kwonlyargs]
            if argument.arg.endswith("_id") and argument.arg not in NOT_AN_ENTITY
            and "TenantId" not in (
                ast.unparse(argument.annotation) if argument.annotation else "")
        }
        wrapped: set[str] = set()
        raw: set[str] = set()
        for sub in ast.walk(node):
            if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                    and sub.func.id in VALIDATORS):
                for argument in [*sub.args, *(k.value for k in sub.keywords)]:
                    if isinstance(argument, ast.Name):
                        wrapped.add(argument.id)
                    if (isinstance(argument, ast.Attribute)
                            and isinstance(argument.value, ast.Name)
                            and argument.value.id == "body"):
                        wrapped.add(argument.attr)
            if (isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name)
                    and sub.value.id == "body" and sub.attr.endswith("_id")
                    and sub.attr not in NOT_AN_ENTITY):
                raw.add(sub.attr)
        missing = sorted((raw | parameters) - wrapped)
        if missing:
            method, path = routes[0]
            out.append((method, path, missing))
    return out


class SweepTests(unittest.TestCase):
    """The structural half. No database: this is a property of the source."""

    def test_every_body_id_is_shape_checked_or_declared_not_to_be_one(self):
        """**The sweep, not a list of the routes somebody remembered.**

        A route added with an unchecked id fails here, which is where the person adding it is
        looking -- rather than as a 500 in somebody else's module a month later.
        """
        unwrapped = {(method, path): missing
                     for method, path, missing in _routes_with_unwrapped_ids()}
        undeclared = sorted(key for key in unwrapped if key not in NOT_A_UUID)
        self.assertEqual(
            undeclared, [],
            "these routes pass a caller's id straight to the database: wrap it in "
            "require_uuid/optional_uuid, or declare it in NOT_A_UUID with the column that "
            "proves it is not a uuid",
        )

    def test_a_declaration_that_is_no_longer_needed_is_refused(self):
        """Both directions, as MOD-010 does for payloads. A route that *became* validated and
        kept its exemption is a line nobody will re-read, and the next field to go unchecked on
        that route would be covered by it."""
        unwrapped = {(method, path) for method, path, _ in _routes_with_unwrapped_ids()}
        stale = sorted(key for key in NOT_A_UUID if key not in unwrapped)
        self.assertEqual(stale, [], "these exemptions are no longer needed")


class ColumnTests(GatedApiTestCase):
    """The claims in `NOT_A_UUID` are about columns, so they are checked against the catalogue."""

    def test_a_field_declared_not_a_uuid_lands_in_a_column_that_is_not_one(self):
        """**An exemption is a claim about the schema, and a claim nobody checks is a comment.**
        If one of these columns is ever changed to `uuid`, the exemption becomes the defect it
        was written to rule out, and this is what notices."""
        for route, (field, table, column) in sorted(NOT_A_UUID.items()):
            if route in ENVELOPE_VALIDATED:
                continue
            with self.subTest(f"{route[0]} {route[1]} {field}"):
                schema, _, name = table.partition(".")
                if not name:
                    schema, name = "iam", schema
                with self._identity_pool.connection() as conn:
                    kind = conn.execute(
                        "SELECT format_type(a.atttypid, a.atttypmod)"
                        "  FROM pg_class c"
                        "  JOIN pg_namespace n ON n.oid = c.relnamespace"
                        "  JOIN pg_attribute a ON a.attrelid = c.oid"
                        " WHERE n.nspname = %s AND c.relname = %s AND a.attname = %s",
                        (schema, name, column)).fetchone()
                self.assertIsNotNone(kind, f"{table}.{column} does not exist")
                assert kind is not None
                self.assertNotEqual(
                    kind[0], "uuid",
                    f"{table}.{column} is a uuid now, so the exemption for {route} is wrong")


class MalformedIdTests(GatedApiTestCase):
    """The behavioural half: a malformed id answers 422 rather than 500.

    A sample rather than every route, and the sweep above is what makes a sample honest. The
    ones here are the ones the gap named plus one per module that had any, because a body that
    is otherwise valid is what makes the case non-vacuous -- a case that 422s on a missing
    field proves nothing about the id.
    """

    BAD = "not-a-uuid"

    def cases(self, tenant_id: str) -> list[tuple[str, str, dict[str, Any]]]:
        correlation = str(uuid.uuid4())
        return [
            ("post", "/brands",
             {"organization_id": self.BAD, "brand_name": "A brand"}),
            ("post", "/locations",
             {"brand_id": self.BAD, "location_name": "A site",
              "timezone": "Asia/Amman"}),
            ("post", "/config/values",
             {"config_key": "a.key", "value": "1", "scope_type": "brand",
              "brand_id": self.BAD, "published_by": str(uuid.uuid4()),
              "correlation_id": correlation}),
            ("post", "/config/preview",
             {"config_key": "a.key", "value": "1", "scope_type": "brand",
              "brand_id": self.BAD}),
            ("post", "/authz/assignments",
             {"identity_id": self.BAD, "role_key": "a_role",
              "correlation_id": correlation}),
            ("post", "/usage",
             {"meter_code": "a_meter", "quantity": 1,
              "idempotency_key": str(uuid.uuid4()), "actor_id": self.BAD,
              "correlation_id": correlation}),
            ("post", "/invoices",
             {"actor_id": self.BAD, "correlation_id": correlation, "tax_rate_bp": 0}),
            ("post", "/subscription",
             {"plan_code": "a_plan", "plan_version": 1, "actor_id": self.BAD,
              "correlation_id": correlation}),
        ]

    def query_cases(self) -> list[tuple[str, str]]:
        """**A path or a query string reaches the same columns as a body**, and the first
        version of this file swept only bodies -- so fifteen routes answered 500 to a malformed
        id in the URL while the sweep reported the request path clean."""
        return [
            f"/config/resolved?brand_id={self.BAD}",
            f"/invoices/{self.BAD}",
            f"/authz/assignments/{self.BAD}?correlation_id={uuid.uuid4()}",
            f"/authz/check?action=tenancy.organization.read&brand_id={self.BAD}"
            f"&correlation_id={uuid.uuid4()}",
        ]

    def test_a_malformed_id_in_a_body_answers_422_and_not_500(self):
        tenant_id = self.tenant()
        for method, path, body in self.cases(tenant_id):
            with self.subTest(f"{method.upper()} {path}"):
                response = getattr(self.client, method)(
                    path, json=body, headers=self.headers(tenant_id))
                self.assertEqual(
                    response.status_code, 422,
                    f"{path} answered {response.status_code}: {response.text[:200]}")

    def test_a_malformed_id_in_a_path_or_a_query_answers_422_too(self):
        tenant_id = self.tenant()
        for path in self.query_cases():
            with self.subTest(path):
                response = self.client.get(path, headers=self.headers(tenant_id))
                self.assertEqual(
                    response.status_code, 422,
                    f"{path} answered {response.status_code}: {response.text[:200]}")

    def test_an_unauthenticated_identity_registration_is_the_same(self):
        """`POST /identities` is the one route in this set with no session, which makes it the
        one where a 500 is reachable by anybody holding a tenant id."""
        tenant_id = self.tenant()
        response = self.client.post("/identities", json={
            "display_name": "Nobody", "email": f"x-{uuid.uuid4().hex[:8]}@acme.test",
            "password": "a-long-enough-password", "person_id": self.BAD,
            "correlation_id": str(uuid.uuid4())},
            headers={"X-Veyro-Tenant": tenant_id})
        self.assertEqual(response.status_code, 422, response.text)


if __name__ == "__main__":
    unittest.main()
