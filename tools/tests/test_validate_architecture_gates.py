#!/usr/bin/env python3
"""
Unit tests for tools/validate_architecture_gates.py (MOD-001, GOV-01-R04 —
TSD §24.1 RLS lint and permission lint only).

Permission gate: real files in an isolated temp directory — a valid contract
passes, and every deliberate-negative fixture fails closed citing the
endpoint, including the "one bad operation among good ones" case and the
empty-contract (vacuous) case, which must never read as PASS.

RLS gate: the pure verdict function over hand-built catalogs, so every
violation code is reachable without a database. The same verdicts against a
real Postgres catalog, with the runtime-role leak they predict, are in
backend/tests/integration/test_architecture_gate_rls.py.

Run directly (`python3 tools/tests/test_validate_architecture_gates.py`) or
with pytest.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
from validate_architecture_gates import (
    _SCREEN_ID_RE,
    _SCREEN_PROVENANCE_PATHS,
    _SCREEN_ROW_KEYS,
    CANONICAL_TENANT_PREDICATE,
    DEFAULT_SCREEN_CONTRACTS,
    DEFAULT_SCREEN_EIP,
    DEFAULT_SCREEN_REGISTRY,
    DEFAULT_SCREEN_SOURCE,
    DEFERRED_GATES,
    ERROR,
    FAIL,
    INCONCLUSIVE,
    PASS,
    PINNED_SEARCH_PATH,
    SCREEN_BINDING_FIELDS,
    SCREEN_BOUND,
    SCREEN_OWNER_STATUSES,
    SCREEN_SURFACES,
    SCREEN_UNBOUND,
    AclGrant,
    GateInputError,
    Policy,
    Relation,
    RlsCatalog,
    RlsManifest,
    RoleInfo,
    _command_inventory_digest,
    _event_field_digest,
    collect_rls_catalog,
    evaluate_rls,
    load_rls_manifest,
    parse_registry,
    parse_rls_manifest,
    parse_screen_contracts,
    parse_screen_registry,
    run_domain_uniqueness_gate,
    run_event_contract_gate,
    run_permission_gate,
    run_rls_gate,
    run_screen_contract_gate,
)

# --- permission gate fixtures -------------------------------------------------

AUTH = "authenticated"


# ADR-010 D5.1: non-`authenticated` entries cite an approval that resolves in the
# repository and names the permission. ADR-009 (DECIDED) names exactly the three
# illustrative non-session permissions used by these synthetic fixtures.
FIXTURE_APPROVAL = "ADR-009"


def _entry(scopes, auth=AUTH, justification=None, approval=None):
    e = {"scopes": scopes, "authentication": auth}
    if justification is not None:
        e["justification"] = justification
        e["approval"] = approval or FIXTURE_APPROVAL
    return e


REGISTRY = {
    "version": 2,
    "permissions": {
        "members.profile.read": _entry(["location", "self"]),
        "billing.refund.create": _entry(["location"]),
        "iam.session.create": _entry(["self"], "credential_exchange",
                                     "IAM-01 sign-in establishes the principal."),
        "billing.provider_event.ingest": _entry(["explicit_resource"], "provider_signature",
                                                "TSD §11.4 HMAC-signed provider callback."),
        "platform.health.read": _entry(["explicit_resource"], "anonymous",
                                       "Synthetic liveness probe; returns no tenant data."),
    },
}

_UNSET = object()


def _op(op_id, decl, auth=AUTH, security=_UNSET):
    op = {"operationId": op_id, "responses": {"200": {"description": "ok"}}}
    if decl is not None:
        op["x-veyro-permission"] = decl
    if auth is not None:
        op["x-veyro-authentication"] = auth
    if security is not _UNSET:
        op["security"] = security
    return op


READ = {"action": "read", "resource": "members.profile", "scope": "self"}
REFUND = {"action": "create", "resource": "billing.refund", "scope": "location"}


SESSION_SCHEME = {"session": {"type": "http", "scheme": "bearer"}}


def _doc(paths, root_security=_UNSET, **extra):
    doc = {"openapi": "3.1.0", "info": {"title": "synthetic", "version": "0"},
           "components": {"securitySchemes": SESSION_SCHEME},
           "security": [{"session": []}], "paths": paths}
    if root_security is not _UNSET:
        if root_security is None:
            del doc["security"]
        else:
            doc["security"] = root_security
    doc.update(extra)
    return doc


VALID_PATHS = {
    "/members/{id}/profile": {"get": _op("getProfile", READ)},
    "/refunds": {"post": _op("createRefund", REFUND)},
}


def _run(paths=None, registry=REGISTRY, extra_files=None, doc=None):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        openapi = root / "openapi"
        openapi.mkdir()
        if doc is not None:
            (openapi / "api.json").write_text(json.dumps(doc))
        elif paths is not None:
            (openapi / "api.json").write_text(json.dumps(_doc(paths)))
        for name, text in (extra_files or {}).items():
            (openapi / name).write_text(text)
        reg = root / "registry.json"
        reg.write_text(registry if isinstance(registry, str) else json.dumps(registry))
        return run_permission_gate(openapi, reg)


def _single_violation(report, endpoint_fragment, detail_fragment):
    assert report.status == FAIL, report.render()
    assert report.exit_code == 1
    assert len(report.violations) == 1, report.render()
    v = report.violations[0]
    assert v.code == "UNREGISTERED_PERMISSION"
    assert endpoint_fragment in v.subject, v
    assert detail_fragment in v.detail, v


def test_permission_valid_contract_passes():
    report = _run(VALID_PATHS)
    assert report.status == PASS, report.render()
    assert report.exit_code == 0
    assert report.checked == [
        "api.json:GET /members/{id}/profile (getProfile)",
        "api.json:POST /refunds (createRefund)",
    ]


def test_permission_missing_declaration_fails_citing_endpoint():
    paths = dict(VALID_PATHS, **{"/members": {"delete": _op("deleteMember", None)}})
    _single_violation(_run(paths), "DELETE /members (deleteMember)", "no x-veyro-permission")


def test_permission_unregistered_name_fails():
    decl = {"action": "impersonate", "resource": "platform.tenant", "scope": "tenant"}
    paths = dict(VALID_PATHS, **{"/impersonate": {"post": _op("impersonate", decl)}})
    _single_violation(_run(paths), "POST /impersonate", "'platform.tenant.impersonate' is not registered")


def test_permission_each_missing_field_fails():
    for missing in ("action", "resource", "scope"):
        decl = {k: v for k, v in READ.items() if k != missing}
        report = _run({"/p": {"get": _op("p", decl)}})
        _single_violation(report, "GET /p", f"declaration missing {missing}")


def test_permission_undeclared_extra_key_fails():
    decl = dict(READ, bypass=True)
    _single_violation(_run({"/p": {"get": _op("p", decl)}}), "GET /p", "undeclared key(s) bypass")


def test_permission_scope_outside_grammar_fails():
    decl = dict(READ, scope="global")
    _single_violation(_run({"/p": {"get": _op("p", decl)}}), "GET /p", "not in the TSD §8.4 scope grammar")


def test_permission_scope_not_registered_for_permission_fails():
    decl = dict(READ, scope="tenant")  # valid grammar, not registered for members.profile.read
    _single_violation(_run({"/p": {"get": _op("p", decl)}}), "GET /p", "'tenant' is not registered")


def test_permission_malformed_resource_fails():
    for resource in ("profile", "members.profile.extra", "Members.Profile", ""):
        decl = dict(READ, resource=resource)
        _single_violation(_run({"/p": {"get": _op("p", decl)}}), "GET /p", "is not <domain>.<resource>")


def test_permission_non_string_values_fail():
    _single_violation(_run({"/p": {"get": _op("p", dict(READ, action=["read"]))}}), "GET /p", "action")
    _single_violation(_run({"/p": {"get": _op("p", "members.profile.read")}}), "GET /p", "must be an object")


def test_permission_path_level_declaration_does_not_cover_operations():
    item = {"x-veyro-permission": READ, "get": _op("p", None)}
    _single_violation(_run({"/p": item}), "GET /p", "no x-veyro-permission")


def test_permission_every_http_method_is_checked():
    item = {m: _op(f"op_{m}", None) for m in
            ("get", "put", "post", "delete", "options", "head", "patch", "trace")}
    report = _run({"/p": item})
    assert report.status == FAIL
    assert len(report.violations) == 8


def test_permission_empty_contract_is_inconclusive_not_pass():
    for paths in ({}, {"/p": {"summary": "no operations"}}):
        report = _run(paths)
        assert report.status == INCONCLUSIVE, report.render()
        assert report.exit_code == 2
        assert report.codes() == {"PERMISSION_GATE_VACUOUS"}
    report = _run(None)  # directory with no documents at all
    assert report.status == INCONCLUSIVE


def test_permission_unsupported_or_unreadable_input_is_error():
    cases = [
        _run(VALID_PATHS, extra_files={"other.yaml": "openapi: 3.1.0\n"}),
        _run(VALID_PATHS, extra_files={"broken.json": "{not json"}),
        _run(VALID_PATHS, extra_files={"swagger.json": json.dumps({"swagger": "2.0", "paths": {}})}),
        _run({"/p": {"$ref": "#/components/pathItems/p"}}),
        _run(VALID_PATHS, registry="{not json"),
    ]
    for report in cases:
        assert report.status == ERROR, report.render()
        assert report.exit_code == 2
        assert report.codes() == {"PERMISSION_GATE_INPUT_INVALID"}


def test_permission_operations_outside_scan_are_errors():
    # R1 P1-B: a valid GET must not let hidden operations PASS.
    cases = [
        {"/p": {"get": _op("p", READ), "POST": _op("x", None)}},
        {"/p": {"get": _op("p", READ), "query": _op("q", None)}},
        {"/p": {"get": _op("p", READ), "additionalOperations": {"COPY": _op("c", None)}}},
        {"/p": {"get": _op("p", READ), "Get": _op("g", None)}},
    ]
    for paths in cases:
        report = _run(paths)
        assert report.status == ERROR, (paths, report.render())
        assert "unsupported key" in report.violations[0].detail


def test_permission_only_openapi_31_supported():
    # ADR-009 D1.2: 3.0.x refused too.
    for version in ("3.0.3", "3.2.0", "3.1", "3.10.0", "4.0.0", "3.1.0\n", 3.1, None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "openapi").mkdir()
            doc = dict(_doc(VALID_PATHS), openapi=version)
            (root / "openapi" / "api.json").write_text(json.dumps(doc))
            (root / "r.json").write_text(json.dumps(REGISTRY))
            report = run_permission_gate(root / "openapi", root / "r.json")
            assert report.status == ERROR, (version, report.render())
    for version in ("3.1.0", "3.1.1"):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "openapi").mkdir()
            (root / "openapi" / "api.json").write_text(
                json.dumps(dict(_doc(VALID_PATHS), openapi=version)))
            (root / "r.json").write_text(json.dumps(REGISTRY))
            assert run_permission_gate(root / "openapi", root / "r.json").status == PASS


def test_permission_strict_json_inputs():
    dup_doc = ('{"openapi": "3.1.0", "paths": {"/p": {"get": {"x-veyro-permission": '
               + json.dumps(READ) + '}, "get": {}}}}')
    deep = "[" * 100000 + "]" * 100000
    entry = json.dumps(_entry(["self"]))
    dup_registry = ('{"version": 2, "permissions": {"members.profile.read": ' + entry
                    + ', "members.profile.read": ' + entry + '}}')
    for report in (
        _run(VALID_PATHS, extra_files={"dup.json": dup_doc}),
        _run(VALID_PATHS, extra_files={"deep.json": deep}),
        _run(VALID_PATHS, registry=dup_registry),
        _run(VALID_PATHS, registry=deep),
    ):
        assert report.status == ERROR, report.render()
        assert report.codes() == {"PERMISSION_GATE_INPUT_INVALID"}


def test_permission_trailing_newline_identifiers_rejected():
    for decl, reason in ((dict(READ, action="read\n"), "is not a lowercase identifier"),
                         (dict(READ, resource="members.profile\n"), "is not <domain>.<resource>")):
        _single_violation(_run({"/p": {"get": _op("p", decl)}}), "GET /p", reason)
    reg = {"version": 2, "permissions": {"members.profile.read\n": _entry(["self"])}}
    assert _run(VALID_PATHS, registry=reg).status == ERROR


def test_permission_registry_type_confusion_is_structured_error():
    for raw in (
        {"version": True, "permissions": {}},
        {"version": 1.0, "permissions": {}},
        {"version": 2, "permissions": {"members.profile.read": _entry([["self"]])}},
        {"version": 2, "permissions": {"members.profile.read": _entry([{"a": 1}])}},
    ):
        try:
            parse_registry(raw)
        except GateInputError:
            continue
        raise AssertionError(f"accepted {raw}")


def test_permission_invalid_registry_is_error():
    bad_registries = [
        {"version": 1, "permissions": {}},  # N24: v1 refused (ADR-010 D5.1)
        {"version": 3, "permissions": {}},
        {"version": 2, "permissions": {"members.read": _entry(["self"])}},
        {"version": 2, "permissions": {"members.profile.read": _entry([])}},
        {"version": 2, "permissions": {"members.profile.read": _entry(["global"])}},
        {"version": 2, "permissions": {"members.profile.read": _entry(["self", "self"])}},
        {"version": 2, "permissions": {"members.profile.read": dict(_entry(["self"]), x=1)}},
        {"version": 2, "permissions": {}, "extra": True},
        # ADR-009 D2: authentication required, closed enum, no default.
        {"version": 2, "permissions": {"members.profile.read": {"scopes": ["self"]}}},
        {"version": 2, "permissions": {"members.profile.read": _entry(["self"], "public")}},
        {"version": 2, "permissions": {"members.profile.read": _entry(["self"], "Anonymous",
                                                                      "x")}},
        {"version": 2, "permissions": {"members.profile.read": _entry(["self"], ["anonymous"],
                                                                      "x")}},
        # non-session class without (or with blank / non-string) justification
        {"version": 2, "permissions": {"iam.session.create": _entry(["self"],
                                                                    "credential_exchange")}},
        {"version": 2, "permissions": {"iam.session.create": _entry(["self"],
                                                                    "credential_exchange", " ")}},
        {"version": 2, "permissions": {"iam.session.create": {"scopes": ["self"],
            "authentication": "anonymous", "justification": 1, "approval": "ADR-009"}}},
        # `authenticated` carrying a justification is not exactly {scopes, authentication}
        {"version": 2, "permissions": {"members.profile.read": _entry(["self"], AUTH, "why")}},
    ]
    for registry in bad_registries:
        report = _run(VALID_PATHS, registry=registry)
        assert report.status == ERROR, (registry, report.render())


def test_permission_missing_inputs_are_error():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert run_permission_gate(root / "nope", root / "nope.json").status == ERROR
        (root / "registry.json").write_text(json.dumps(REGISTRY))
        assert run_permission_gate(root / "nope", root / "registry.json").status == ERROR


def test_permission_cli_exit_codes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        openapi = root / "openapi"
        openapi.mkdir()
        reg = root / "registry.json"
        reg.write_text(json.dumps(REGISTRY))
        doc = openapi / "api.json"

        def cli():
            return subprocess.run(
                [sys.executable, str(TOOLS / "validate_architecture_gates.py"), "--gate",
                 "permission", "--openapi-dir", str(openapi), "--registry", str(reg), "--json"],
                capture_output=True, text=True, check=False,
            )

        doc.write_text(json.dumps(_doc(VALID_PATHS)))
        ok = cli()
        assert ok.returncode == 0, ok.stdout + ok.stderr
        assert json.loads(ok.stdout)["status"] == PASS
        doc.write_text(json.dumps(_doc({"/p": {"get": _op("p", None)}})))
        bad = cli()
        assert bad.returncode == 1
        assert json.loads(bad.stdout)["violations"][0]["code"] == "UNREGISTERED_PERMISSION"


def test_deferred_gates_never_pass():
    for gate in DEFERRED_GATES:
        res = subprocess.run(
            [sys.executable, str(TOOLS / "validate_architecture_gates.py"), "--gate", gate],
            capture_output=True, text=True, check=False,
        )
        assert res.returncode == 2, (gate, res.stdout)
        assert "GATE_NOT_IMPLEMENTED" in res.stdout


def test_event_contract_shared_scenario_batch():
    """SCN-008/019/130: registered, unregistered, changed without/with OWN."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "app"
        src.mkdir()
        current = root / "registry.json"
        baseline = root / "baseline.json"
        approvals = root / "knowledge" / "00-System"
        approvals.mkdir(parents=True)
        event = {"schema": {"type": "object"}, "classification": "internal"}
        changed = {"schema": {"type": "string"}, "classification": "internal"}
        baseline.write_text(json.dumps({"events": {"veyro.created": event}}))

        def run() -> tuple[int, dict]:
            result = subprocess.run(
                [sys.executable, str(TOOLS / "validate_architecture_gates.py"),
                 "--gate", "event-contract", "--json", "--event-source-dir", str(src),
                 "--event-registry", str(current), "--event-baseline", str(baseline),
                 "--event-approval-root", str(root)], capture_output=True, text=True,
                check=False,
            )
            return result.returncode, json.loads(result.stdout)

        (src / "flow.py").write_text('emit_event("veyro.created")\n')
        current.write_text(json.dumps({"events": {"veyro.created": event}}))
        code, report = run()
        assert (code, report["status"]) == (0, PASS)

        (src / "flow.py").write_text('emit_event("veyro.missing")\n')
        code, report = run()
        assert code == 1 and report["violations"][0]["code"] == "UNREGISTERED_EVENT_CONTRACT"

        (src / "flow.py").write_text('emit_event("veyro.created")\n')
        current.write_text(json.dumps({"events": {"veyro.created": changed}}))
        code, report = run()
        assert code == 1 and report["violations"][0]["code"] == "EVENT_CHANGE_UNAPPROVED"

        changed["ownerApproval"] = "OWN-999"
        current.write_text(json.dumps({"events": {"veyro.created": changed}}))
        (approvals / "OWNER_APPROVALS.md").write_text("| OWN-999 | veyro.created | synthetic test approval |\n")
        code, report = run()
        assert (code, report["status"]) == (0, PASS)

        (src / "flow.py").write_text('emit_event(variable)\n')
        code, report = run()
        assert code == 1 and report["violations"][0]["code"] == "UNREGISTERED_EVENT_CONTRACT"


def test_event_field_digest_is_order_independent_and_distinguishing():
    """`_event_field_digest` is the primitive `EVENT_CHANGE_UNAPPROVED`'s diff
    citation is built from (gate-3 review R1 P2-2): it must depend only on the
    value, not on Python dict insertion order, and it must actually
    distinguish different values -- otherwise a digest-based diff citation
    would be no citation at all."""
    a = {"type": "object", "properties": {"x": {"type": "string"}, "y": {"type": "integer"}}}
    b = {"properties": {"y": {"type": "integer"}, "x": {"type": "string"}}, "type": "object"}
    assert _event_field_digest(a) == _event_field_digest(b)
    assert _event_field_digest(a) != _event_field_digest({"type": "string"})
    assert len(_event_field_digest(a)) == 64
    assert _event_field_digest("internal") != _event_field_digest("pii")


def test_event_change_unapproved_cites_bounded_diff():
    """Gate-3 review R1 P2-2: `EVENT_CHANGE_UNAPPROVED` named the changed
    field but never cited the diff itself, against both SCN-130
    (`SCENARIOS.md:984-987`) and this gate's own IMPLEMENTATION.md row, which
    both require denial "citing the event and the unapproved diff". The
    finding's own close-by clause accepts a hash in place of the raw value,
    so this pins that the resulting digest pair actually distinguishes old
    from new, is reported independently per changed field (`schema` and
    `classification` do not get entangled or dropped), and never grows with
    the size of the underlying value -- the schema in particular has no
    upper size bound, so citing it verbatim would be the large-payload leak
    the finding warns against.
    """
    digest_pair = re.compile(r"([a-z]+) ([0-9a-f]{64})->([0-9a-f]{64})")

    def gate(old_schema, old_class, new_schema, new_class):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "app"
            src.mkdir()
            registry, baseline = root / "registry.json", root / "baseline.json"
            baseline.write_text(json.dumps({"events": {"veyro.created":
                {"schema": old_schema, "classification": old_class}}}))
            registry.write_text(json.dumps({"events": {"veyro.created":
                {"schema": new_schema, "classification": new_class}}}))
            (src / "flow.py").write_text('emit_event("veyro.created")\n')
            return run_event_contract_gate(src, registry, baseline, root)

    # Schema-only change: cites "schema" and only "schema" -- classification
    # is untouched, so it must not appear in the diff at all.
    report = gate({"type": "object"}, "internal", {"type": "string"}, "internal")
    assert (report.status, report.exit_code) == (FAIL, 1), report.render()
    violation = report.violations[0]
    assert (violation.code, violation.subject) == ("EVENT_CHANGE_UNAPPROVED", "veyro.created")
    assert "missing OWN-NNN approval" in violation.detail
    pairs = {field: (old, new) for field, old, new in digest_pair.findall(violation.detail)}
    assert set(pairs) == {"schema"}, violation.detail
    assert pairs["schema"][0] != pairs["schema"][1]
    assert "object" not in violation.detail and "string" not in violation.detail

    # Classification-only change: the mirror case -- "classification" only.
    report = gate({"type": "object"}, "internal", {"type": "object"}, "pii")
    violation = report.violations[0]
    pairs = {field: (old, new) for field, old, new in digest_pair.findall(violation.detail)}
    assert set(pairs) == {"classification"}, violation.detail
    assert pairs["classification"][0] != pairs["classification"][1]
    assert "pii" not in violation.detail and "internal" not in violation.detail

    # Both fields changed in the same entry: both cited, independently, each
    # still distinguishing its own old value from its new one.
    report = gate({"type": "object"}, "internal", {"type": "string"}, "pii")
    violation = report.violations[0]
    pairs = {field: (old, new) for field, old, new in digest_pair.findall(violation.detail)}
    assert set(pairs) == {"schema", "classification"}, violation.detail
    assert pairs["schema"][0] != pairs["schema"][1]
    assert pairs["classification"][0] != pairs["classification"][1]
    assert pairs["schema"] != pairs["classification"]

    # A schema with no realistic size bound must still produce a small,
    # fixed-size detail -- the digest, not the value, is what is cited.
    huge_old = {"type": "object",
                "properties": {f"field_{i}": {"type": "string"} for i in range(500)}}
    huge_new = {"type": "object",
                "properties": {f"field_{i}": {"type": "string"} for i in range(500)},
                "required": ["field_0"]}
    report = gate(huge_old, "internal", huge_new, "internal")
    violation = report.violations[0]
    assert len(violation.detail) < 300, len(violation.detail)
    assert "field_499" not in violation.detail

    # Unchanged control: identical schema and classification never reach the
    # diff/approval path, so no digest and no violation are produced.
    report = gate({"type": "object"}, "internal", {"type": "object"}, "internal")
    assert (report.status, report.exit_code) == (PASS, 0), report.render()


def test_event_contract_aliased_emitter_cannot_yield_a_green_pass():
    """Gate-3 review R1 P1-1: an aliased emitter must be inspected, not skipped.

    The fail-open this pins: an unregistered event emitted through
    `from veyro.bus import emit_event as publish` was invisible to the matcher,
    and because one legitimate literal call kept `checked` non-empty the vacuity
    note never fired either — so the gate reported PASS with an unregistered
    event in the tree. Every case below therefore keeps that one legitimate
    canonical call present, so no verdict here can come from an empty scan.

    Expectations here were reversed by ADR-012, deliberately and not quietly
    (see that ADR's "Disclosed contract reversal"). Under D4 an import rename is
    itself ERROR `EVENT_EMITTER_UNINSPECTABLE`, so the one landed positive-case
    assertion inverts PASS → ERROR and eight of the nine landed denial
    assertions invert FAIL / exit 1 → ERROR / exit 2. Only the literal-`getattr`
    case stays FAIL, because it is the one shape whose emitter reference is a
    direct callee. Every reversal moves strictly toward denial on the ordering
    `clean < FAIL < ERROR`; none clears an input the pre-ADR-012 gate denied.
    One source line may legitimately produce both an escape and a
    resolved-callee finding, so these assert status, code and subject
    *membership*, never whole-list equality.
    """
    event = {"schema": {"type": "object"}, "classification": "internal"}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "app"
        src.mkdir()
        registry, baseline = root / "registry.json", root / "baseline.json"
        registry.write_text(json.dumps({"events": {"veyro.created": event}}))
        baseline.write_text(registry.read_text())
        (src / "flow.py").write_text('emit_event("veyro.created")\n')
        legitimate = f"{src / 'flow.py'}:1"

        def gate(source):
            (src / "aliased.py").write_text(source)
            return run_event_contract_gate(src, registry, baseline, root)

        # ADR-012 D4 reverses this case: an alias emitting a *registered* event
        # is still visibly inspected (the call itself resolves and raises no
        # contract violation), but the rename at its own import line is ERROR,
        # because that binding is as re-exportable as an assignment alias and
        # has no Load-context use for D3 to catch.
        ok = gate('from veyro.bus import emit_event as publish\npublish("veyro.created")\n')
        assert ok.status == ERROR, ok.render()
        assert ok.exit_code == 2, ok.render()
        assert [(v.code, v.subject) for v in ok.violations] == [
            ("EVENT_EMITTER_UNINSPECTABLE", f"{src / 'aliased.py'}:1")], ok.render()
        assert {f"{src / 'aliased.py'}:2", legitimate} <= set(ok.checked), ok.checked

        # Every alias shape the resolver claims, each emitting an unregistered
        # event alongside the valid call above. All but the literal-`getattr`
        # case now deny as ERROR rather than FAIL (ADR-012 D4/D3), while
        # retaining the concurrent `UNREGISTERED_EVENT_CONTRACT` FAIL wherever
        # the call's own callee did resolve.
        escape, unregistered = "EVENT_EMITTER_UNINSPECTABLE", "UNREGISTERED_EVENT_CONTRACT"
        both = {escape, unregistered}
        denied = {
            "from-import alias (the reproduced defect)": (
                'from veyro.bus import emit_event as publish\npublish("veyro.missing")\n',
                ERROR, both),
            "relative from-import alias": (
                'from .bus import emit_event as publish\npublish("veyro.missing")\n',
                ERROR, both),
            "assignment alias chain": (
                ('from veyro.bus import emit_event\npublish = emit_event\n'
                 'send = publish\nsend("veyro.missing")\n'),
                ERROR, both),
            "alias assigned from an attribute": (
                'import veyro.bus as bus\npublish = bus.emit_event\npublish("veyro.missing")\n',
                ERROR, both),
            # The one case that stays FAIL: its emitter reference is a direct
            # callee, so the gate does know the event id and can name it.
            "getattr with a literal attribute": (
                'import veyro.bus as bus\ngetattr(bus, "emit_event")("veyro.missing")\n',
                FAIL, {unregistered}),
            # ADR-012 D3a: the `NamedExpr` is not itself a reference, so this
            # reports the inner `Name` escape exactly once and does *not* also
            # resolve the callee — hence no concurrent id-naming FAIL.
            "walrus used directly as the callee": (
                'from veyro.bus import emit_event\n(publish := emit_event)("veyro.missing")\n',
                ERROR, {escape}),
            "parameter default": (
                ('from veyro.bus import emit_event\ndef go(publish=emit_event):\n'
                 '    publish("veyro.missing")\n'),
                ERROR, both),
            # File-wide bindings are not lexically scoped, so shadowing the alias
            # name later does not buy back invisibility. Pinned so this deliberate
            # over-approximation (the fail-closed direction) is not silently narrowed.
            "alias shadowed by a later local definition": (
                ('from veyro.bus import emit_event as publish\ndef publish(event):\n'
                 '    return event\npublish("veyro.missing")\n'),
                ERROR, both),
        }
        for name, (source, status, codes) in denied.items():
            report = gate(source)
            assert report.status == status, (name, report.render())
            assert report.exit_code == (2 if status == ERROR else 1), (name, report.render())
            assert report.codes() == codes, (name, report.render())
            if unregistered in codes:
                assert ("UNREGISTERED_EVENT_CONTRACT", "veyro.missing") in [
                    (v.code, v.detail) for v in report.violations], (name, report.render())

        # A dynamic event id reached through an alias denies on the same rule the
        # canonical call already used, citing the shape rather than an id — and
        # that FAIL is retained beside the D4 import-rename ERROR rather than
        # being displaced by it (ADR-012 D6: ERROR dominates, both are reported).
        dynamic = gate('from veyro.bus import emit_event as publish\npublish(name)\n')
        assert dynamic.status == ERROR, dynamic.render()
        assert dynamic.exit_code == 2, dynamic.render()
        assert ("UNREGISTERED_EVENT_CONTRACT", "non-literal event id") in [
            (v.code, v.detail) for v in dynamic.violations], dynamic.render()
        assert escape in dynamic.codes(), dynamic.render()

        # The resolver must not manufacture emitters out of unrelated code: each
        # of these leaves `checked` at the one legitimate call and stays PASS.
        for name, source in {
            "a local function that merely shares an alias name":
                'def publish(event):\n    return event\npublish("veyro.missing")\n',
            "an unrelated getattr binding":
                'import os\nhandler = getattr(os, "listdir")\nhandler("veyro.missing")\n',
            "an unrelated walrus":
                'if (n := len("veyro.missing")):\n    print(n)\n',
        }.items():
            report = gate(source)
            assert report.status == PASS, (name, report.render())
            assert report.checked == [legitimate], (name, report.checked)


def test_event_contract_escaped_emitter_cannot_yield_a_green_pass():
    """ADR-012 D2-D5: a recognised emitter reference that is not a direct callee,
    a renamed import, or the emitter's name as a bare string literal must deny.

    This is the reviewer's *second* closure condition for R1 P1-1, which the
    bounded alias remediation did not meet: an unresolvable or dynamic
    emitter-shaped reference must be a violation rather than an omission. The
    status inversion it closes was measured — one escaping module *alone* yielded
    INCONCLUSIVE / exit 2, while the same module beside one valid canonical call
    yielded PASS / exit 0, so adding correct code upgraded denial to PASS. Every
    case below therefore keeps that one legitimate canonical call present, so no
    verdict here can come from an empty scan, and each asserts code membership
    rather than list equality because one line may produce two findings.

    An escape is ERROR, not FAIL (D6): the gate knows the reference is
    uninspectable but cannot name the event id, so `UNREGISTERED_EVENT_CONTRACT`
    would assert a fact it does not have.
    """
    event = {"schema": {"type": "object"}, "classification": "internal"}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "app"
        src.mkdir()
        registry, baseline = root / "registry.json", root / "baseline.json"
        registry.write_text(json.dumps({"events": {"veyro.created": event}}))
        baseline.write_text(registry.read_text())
        (src / "flow.py").write_text('emit_event("veyro.created")\n')
        legitimate = f"{src / 'flow.py'}:1"

        def gate(source):
            (src / "escaped.py").write_text(source)
            return run_event_contract_gate(src, registry, baseline, root)

        imported = "from veyro.bus import emit_event\n"
        # D3: a recognised Load-context use in any non-callee position. The
        # emitted event is *registered* in every case, so nothing here could
        # deny on the event id — the escape itself is the enforceable event.
        escaped = {
            "call argument": f"{imported}register(emit_event)\n",
            "keyword argument": f"{imported}register(handler=emit_event)\n",
            "dict value": f'{imported}HANDLERS = {{"created": emit_event}}\n',
            "list element": f"{imported}HANDLERS = [emit_event]\n",
            "tuple element": f"{imported}HANDLERS = (emit_event,)\n",
            "assignment right-hand side": f"{imported}publish = emit_event\n",
            "annotated assignment right-hand side":
                f"{imported}publish: object = emit_event\n",
            "class-body assignment": f"{imported}class Bus:\n    send = emit_event\n",
            "instance-attribute assignment":
                f"{imported}class Bus:\n    def __init__(self):\n"
                "        self.send = emit_event\n",
            "conditional expression": f"{imported}publish = emit_event if flag else None\n",
            "return value": f"{imported}def get():\n    return emit_event\n",
            "attribute access that is not a callee":
                'import veyro.bus as bus\nHANDLERS = [bus.emit_event]\n',
            "literal getattr retrieval that is not a callee":
                'import veyro.bus as bus\npublish = getattr(bus, "emit_event")\n',
            # D4: the one shape with no Load-context use to catch. This is the
            # in-tree cross-file re-export fail-open — `a.py` renames, `b.py`
            # imports the renamed symbol and contains nothing recognisable — and
            # it is closed here module-locally, at `a.py`'s own import line.
            "import rename": 'from veyro.bus import emit_event as publish\n',
            # D3a: exactly one finding, from the inner `Name`; the `NamedExpr`
            # is not itself a reference, so the callee position is not double-counted.
            "walrus binding used as the callee":
                f'{imported}(publish := emit_event)("veyro.created")\n',
        }
        for name, source in escaped.items():
            report = gate(source)
            assert report.status == ERROR, (name, report.render())
            assert report.exit_code == 2, (name, report.render())
            assert "EVENT_EMITTER_UNINSPECTABLE" in report.codes(), (name, report.render())
            # The valid canonical call is still inspected and still disclosed:
            # an ERROR run reports both partitions rather than discarding `checked`.
            assert legitimate in report.checked, (name, report.checked)

        # D5, tier-2: the emitter's name as a bare string literal. Exact-match
        # only — `globals()["emit" + "_event"]` defeats it, which is a reach
        # limit and not a security property (residual 2).
        dynamic = {
            "string-keyed globals lookup": 'globals()["emit_event"]("veyro.created")\n',
            "getattr through a string constant":
                'import veyro.bus as bus\nNAME = "emit_event"\n'
                'getattr(bus, NAME)("veyro.created")\n',
            "computed attrgetter":
                'import operator\nfetch = operator.attrgetter("emit_event")\n',
            # D7: there is no test-path exemption. `mock.patch.object` installs a
            # replacement emitter and denies here; the dotted
            # `mock.patch("veyro.bus.emit_event")` spelling is the convention to
            # use, but only because it is outside D5's exact-match reach — it is
            # NOT the safer form.
            "mock.patch.object on the emitter attribute":
                'import veyro.bus as bus\nfrom unittest import mock\n'
                'mock.patch.object(bus, "emit_event")\n',
        }
        for name, source in dynamic.items():
            report = gate(source)
            assert report.status == ERROR, (name, report.render())
            assert report.exit_code == 2, (name, report.render())
            assert "DYNAMIC_EVENT_EMITTER_REFERENCE" in report.codes(), (name, report.render())

        # D2/D2a: a `Store`/`Del` target names a binding and is never evaluated
        # as a value, so the target itself must not report. Dropping the
        # `ast.Load` test makes every one of these ERROR for no reason, and makes
        # `self.emit_event = emit_event` report twice instead of once.
        assert gate("emit_event = None\n").status == PASS, "canonical Store target"
        assert gate(f"{imported}del emit_event\n").status == PASS, "canonical Del target"
        assert gate('class Bus:\n    def __init__(self):\n'
                    '        self.emit_event = None\n').status == PASS, "attribute Store"
        assert gate('import veyro.bus as bus\ndel bus.emit_event\n').status == PASS, "attribute Del"
        once = gate(f'{imported}class Bus:\n    def __init__(self):\n'
                    '        self.emit_event = emit_event\n')
        assert once.status == ERROR, once.render()
        assert [v.code for v in once.violations] == ["EVENT_EMITTER_UNINSPECTABLE"], once.render()

        # And the aggregate vacuity guard is retained as a non-vacuity
        # *disclosure* only (D8): an escapes-only tree is ERROR with an empty
        # `checked`, which the trusted workflow's NOT_APPLICABLE path cannot
        # absorb because that path requires INCONCLUSIVE.
        (src / "flow.py").write_text("")
        alone = gate(f"{imported}publish = emit_event\n")
        assert (alone.status, alone.exit_code) == (ERROR, 2), alone.render()
        assert alone.checked == [], alone.checked
        assert "EVENT_CONTRACT_GATE_VACUOUS" not in alone.codes(), alone.render()


def test_event_contract_ordinary_indirection_is_not_an_emitter():
    """ADR-012: the non-interference set — ordinary indirection that happens to
    look emitter-shaped must stay PASS, with `checked` at exactly the one
    legitimate canonical call.

    This pins the other side of the contract. D5 keys on the emitter's own name
    rather than on a reflective-construct denylist precisely so that `globals()`,
    a dict of callables, a decorator or a non-literal `getattr` are not
    themselves violations; the rejected denylist alternative would have made
    them so, open-endedly and aliasably.
    """
    event = {"schema": {"type": "object"}, "classification": "internal"}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "app"
        src.mkdir()
        registry, baseline = root / "registry.json", root / "baseline.json"
        registry.write_text(json.dumps({"events": {"veyro.created": event}}))
        baseline.write_text(registry.read_text())
        (src / "flow.py").write_text('emit_event("veyro.created")\n')
        legitimate = f"{src / 'flow.py'}:1"

        for name, source in {
            "identity wrapper":
                'def identity(fn):\n    return fn\nidentity(print)("veyro.missing")\n',
            "dict-of-callables dispatch":
                'HANDLERS = {"created": print}\nHANDLERS["created"]("veyro.missing")\n',
            "string-keyed globals lookup of an unrelated name":
                'key = "print"\nglobals()[key]("veyro.missing")\n',
            "non-literal getattr":
                'import os\nattr = "listdir"\ngetattr(os, attr)("veyro.missing")\n',
            "decorator":
                'def deco(fn):\n    return fn\n\n@deco\ndef go():\n    return None\n',
            "a local function that merely shares an alias name":
                'def publish(event):\n    return event\npublish("veyro.missing")\n',
        }.items():
            (src / "ordinary.py").write_text(source)
            report = run_event_contract_gate(src, registry, baseline, root)
            assert report.status == PASS, (name, report.render())
            assert report.exit_code == 0, (name, report.render())
            assert report.checked == [legitimate], (name, report.checked)


def test_event_contract_registry_removal_requires_its_own_owner_approval():
    """Gate-3 review R1 P1-2: withdrawing a baseline event cannot reach PASS.

    The fail-open this pins: the change-detection loop iterated the *candidate
    registry* and looked each id up in the baseline, so an event present in the
    baseline and absent from the registry was never examined at all. A change
    dropping both the registry entry and its emitter raised no
    `UNREGISTERED_EVENT_CONTRACT` (no emitter left to inspect) and no
    `EVENT_CHANGE_UNAPPROVED` (no registry key to iterate), so the gate reported
    PASS with zero violations while a published contract was silently withdrawn
    — the maximal compatibility break, on the axis TSD §24.1 reserves to the
    owner.

    The route added for an *intentional* removal is a candidate-side
    `removals: {<event id>: "OWN-NNN"}` citation resolved through
    `resolve_withdrawal_approval` (action intent is pinned separately, below).
    Three properties are pinned beyond mere presence, because each is a way an
    approval could appear to authorise a removal it never spoke to: the cited
    record must approve withdrawing the event and resolve to exactly one live
    row; it may not be the record the *baseline* entry
    itself carries, which approved that entry rather than its withdrawal; and a
    citation for an id the baseline does not carry is refused as input, so one
    cannot be pre-staged for a later deletion or left behind after a baseline
    refresh.

    One legitimate canonical `emit_event` call stays in the tree throughout, so
    no verdict here comes from an empty scan and no PASS below is the vacuity
    disclosure wearing a different name.
    """
    def entry(kind: str = "object", approval: str | None = None) -> dict:
        built: dict = {"schema": {"type": kind}, "classification": "internal"}
        if approval is not None:
            built["ownerApproval"] = approval
        return built

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "app"
        src.mkdir()
        registry, baseline = root / "registry.json", root / "baseline.json"
        approvals = root / "knowledge" / "00-System"
        approvals.mkdir(parents=True)
        register = approvals / "OWNER_APPROVALS.md"
        # OWN-997 is the approval the baseline entry already carries and OWN-999
        # the distinct record authorising the withdrawal. Both name the event, so
        # the refusal of OWN-997 below cannot be mistaken for a resolver miss.
        rows = ("| OWN-997 | Approve schema change of event veyro.leaving | synthetic | "
                "2026-10-09 | synthetic |\n"
                "| OWN-998 | Approve withdrawal of event unrelated.event | synthetic | "
                "2026-10-09 | synthetic |\n"
                "| OWN-999 | Approve withdrawal of event `veyro.leaving` | synthetic | "
                "2026-10-09 | synthetic |\n")
        register.write_text(rows)
        baseline.write_text(json.dumps({"events": {
            "veyro.leaving": entry(approval="OWN-997"),
            "veyro.staying": entry()}}))
        (src / "flow.py").write_text('emit_event("veyro.staying")\n')
        legitimate = f"{src / 'flow.py'}:1"
        staying = {"veyro.staying": entry()}

        def gate(document: dict):
            registry.write_text(json.dumps(document))
            return run_event_contract_gate(src, registry, baseline, root)

        # Unchanged control: both entries retained, byte-identical to baseline.
        unchanged = gate({"events": {"veyro.leaving": entry(approval="OWN-997"),
                                     **staying}})
        assert (unchanged.status, unchanged.exit_code) == (PASS, 0), unchanged.render()
        assert unchanged.checked == [legitimate], unchanged.checked

        # The reproduced defect: entry and emitter both dropped, nothing cited.
        absent = gate({"events": staying})
        assert (absent.status, absent.exit_code) == (FAIL, 1), absent.render()
        assert [(v.code, v.subject) for v in absent.violations] == [
            ("EVENT_REMOVED_UNAPPROVED", "veyro.leaving")], absent.render()
        assert "missing OWN-NNN approval" in absent.violations[0].detail
        assert absent.checked == [legitimate], absent.checked

        # Each insufficient citation, all naming the withdrawn event. An ADR is
        # not sufficient for this owner-reserved decision, matching the change
        # path; OWN-998 resolves but approves another event's withdrawal; OWN-997 both
        # resolves and names it, and is refused anyway because it is the
        # baseline entry's own prior approval.
        for ref, expected in (("ADR-012", "missing OWN-NNN approval"),
                              ("OWN-998", "does not approve withdrawal of 'veyro.leaving'"),
                              ("OWN-997", "prior approval")):
            report = gate({"events": staying, "removals": {"veyro.leaving": ref}})
            assert (report.status, report.exit_code) == (FAIL, 1), (ref, report.render())
            assert [(v.code, v.subject) for v in report.violations] == [
                ("EVENT_REMOVED_UNAPPROVED", "veyro.leaving")], (ref, report.render())
            assert expected in report.violations[0].detail, (ref, report.render())

        # A duplicated register row makes the citation ambiguous, so it resolves
        # to no single owner decision and still denies.
        register.write_text(rows + "| OWN-999 | Approve withdrawal of event veyro.leaving "
                                   "| synthetic duplicate | 2026-10-09 | synthetic |\n")
        duplicate = gate({"events": staying, "removals": {"veyro.leaving": "OWN-999"}})
        assert (duplicate.status, duplicate.exit_code) == (FAIL, 1), duplicate.render()
        assert duplicate.codes() == {"EVENT_REMOVED_UNAPPROVED"}, duplicate.render()
        assert "2 OWNER_APPROVALS rows, need 1" in duplicate.violations[0].detail
        register.write_text(rows)

        # The approved withdrawal — the one shape that clears.
        approved = gate({"events": staying, "removals": {"veyro.leaving": "OWN-999"}})
        assert (approved.status, approved.exit_code) == (PASS, 0), approved.render()
        assert approved.violations == [], approved.render()
        assert approved.checked == [legitimate], approved.checked

        # Changed control: an approved removal is not blanket approval, so a
        # retained entry's unapproved schema change still denies on its own axis.
        changed = gate({"events": {"veyro.staying": entry("string")},
                        "removals": {"veyro.leaving": "OWN-999"}})
        assert (changed.status, changed.exit_code) == (FAIL, 1), changed.render()
        assert [(v.code, v.subject) for v in changed.violations] == [
            ("EVENT_CHANGE_UNAPPROVED", "veyro.staying")], changed.render()

        # Structural refusals, each ERROR rather than FAIL: the gate cannot read
        # a contract decision out of a self-contradictory or pre-staged document.
        contradiction = gate({"events": {"veyro.leaving": entry(approval="OWN-997"),
                                         **staying},
                              "removals": {"veyro.leaving": "OWN-999"}})
        assert (contradiction.status, contradiction.exit_code) == (ERROR, 2), \
            contradiction.render()
        assert contradiction.codes() == {"EVENT_CONTRACT_GATE_INPUT_INVALID"}, \
            contradiction.render()
        assert "declared removed while still registered" in \
            contradiction.violations[0].detail

        prestaged = gate({"events": staying,
                          "removals": {"veyro.leaving": "OWN-999",
                                       "veyro.never": "OWN-999"}})
        assert (prestaged.status, prestaged.exit_code) == (ERROR, 2), prestaged.render()
        assert prestaged.codes() == {"EVENT_CONTRACT_GATE_INPUT_INVALID"}, prestaged.render()
        assert "absent from the baseline" in prestaged.violations[0].detail

        # The baseline is the old approved state, and it legitimately carries
        # the tombstones of removals this gate already accepted — it is itself a
        # candidate that passed (the lifecycle test below is the one that pins
        # that end to end). What it may never do is supply the citation for a
        # *new* withdrawal, which is the place an old approval could be read:
        # `veyro.earlier`'s accepted tombstone leaves `veyro.leaving` — still
        # registered in this baseline — exactly as un-cited as before.
        baseline.write_text(json.dumps({
            "events": {"veyro.leaving": entry(approval="OWN-997"), **staying},
            "removals": {"veyro.earlier": "OWN-999"}}))
        uninherited = gate({"events": staying})
        assert (uninherited.status, uninherited.exit_code) == (FAIL, 1), uninherited.render()
        assert [(v.code, v.subject) for v in uninherited.violations] == [
            ("EVENT_REMOVED_UNAPPROVED", "veyro.leaving")], uninherited.render()
        assert "missing OWN-NNN approval" in uninherited.violations[0].detail
        # Cited candidate-side it clears, exactly as against a tombstone-free
        # baseline: a tombstone the baseline carries neither authorises nor
        # obstructs a different id's withdrawal.
        beside = gate({"events": staying, "removals": {"veyro.leaving": "OWN-999"}})
        assert (beside.status, beside.exit_code) == (PASS, 0), beside.render()
        assert beside.violations == [], beside.render()
        assert beside.checked == [legitimate], beside.checked


def test_event_contract_approved_removal_survives_promotion_to_baseline():
    """Gate-3 review R1 P1-2, second half: the accepted-baseline lifecycle.

    The fail-closed removal route R1 P1-2 added (previous test) was unusable
    across a baseline refresh, which is the only way it is ever actually used.
    An approved removal cleared as a candidate, but promoting that very accepted
    candidate to be the next baseline — the normal lifecycle, since the baseline
    *is* the last candidate this gate passed — made the next run ERROR on its
    own input twice over: the baseline was refused outright for declaring
    `removals`, and the candidate's unchanged tombstone was refused as
    pre-staged because the id was no longer in the baseline's `events`. A gate
    whose own PASS cannot become its next baseline denies every subsequent run
    regardless of what the change contains, so no removal could be shipped.

    The correction: a candidate `removals` entry byte-identical to one the
    baseline already carries is settled history and re-approves nothing. Pinned
    here across two promotion generations, together with the four ways that
    could have become a fail-open — a restated tombstone under a different
    citation, a newly pre-staged id, an already-spent approval re-aimed at a
    second event, and an accepted tombstone standing in for a missing citation.

    One legitimate canonical `emit_event` call stays in the tree throughout, so
    no PASS below is the vacuity disclosure wearing a different name.
    """
    def entry(approval: str | None = None) -> dict:
        built: dict = {"schema": {"type": "object"}, "classification": "internal"}
        if approval is not None:
            built["ownerApproval"] = approval
        return built

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "app"
        src.mkdir()
        registry, baseline = root / "registry.json", root / "baseline.json"
        approvals = root / "knowledge" / "00-System"
        approvals.mkdir(parents=True)
        # OWN-997 is `veyro.leaving`'s prior change approval, OWN-999 the record
        # authorising its withdrawal, OWN-996 a distinct record authorising
        # `veyro.later`'s withdrawal one generation afterwards. OWN-999 approves
        # withdrawing only `veyro.leaving`, so re-aiming it at `veyro.later`
        # below is refused by the resolver rather than by a shape check.
        (approvals / "OWNER_APPROVALS.md").write_text(
            "| OWN-996 | Approve withdrawal of event veyro.later | synthetic | 2026-10-09 | s |\n"
            "| OWN-997 | Approve schema change of event veyro.leaving | synthetic | 2026-10-09 | s |\n"
            "| OWN-998 | Approve withdrawal of event unrelated.event | synthetic | 2026-10-09 | s |\n"
            "| OWN-999 | Approve withdrawal of event veyro.leaving | synthetic | 2026-10-09 | s |\n")
        (src / "flow.py").write_text('emit_event("veyro.staying")\n')
        legitimate = f"{src / 'flow.py'}:1"
        # `veyro.later` is registered with no emitter of its own, so removing it
        # in generation 2 raises no concurrent UNREGISTERED_EVENT_CONTRACT and
        # every verdict below is attributable to the removal axis alone.
        kept = {"veyro.staying": entry(), "veyro.later": entry()}

        def gate(document: dict):
            registry.write_text(json.dumps(document))
            return run_event_contract_gate(src, registry, baseline, root)

        def promote() -> None:
            """The lifecycle step: the accepted candidate becomes the baseline,
            byte-identical, tombstones included."""
            baseline.write_text(registry.read_text())

        baseline.write_text(json.dumps(
            {"events": {"veyro.leaving": entry(approval="OWN-997"), **kept}}))

        # Step 1 — the initial withdrawal, nothing cited: denied.
        denied = gate({"events": kept})
        assert (denied.status, denied.exit_code) == (FAIL, 1), denied.render()
        assert [(v.code, v.subject) for v in denied.violations] == [
            ("EVENT_REMOVED_UNAPPROVED", "veyro.leaving")], denied.render()

        # Step 2 — the same withdrawal, cited candidate-side: clears.
        approved = gate({"events": kept, "removals": {"veyro.leaving": "OWN-999"}})
        assert (approved.status, approved.exit_code) == (PASS, 0), approved.render()
        assert approved.violations == [], approved.render()
        assert approved.checked == [legitimate], approved.checked

        # Step 3 — the defect this test exists for. Promote that accepted
        # candidate and re-run it unchanged: previously ERROR/2
        # EVENT_CONTRACT_GATE_INPUT_INVALID on the gate's own last PASS.
        promote()
        settled = gate({"events": kept, "removals": {"veyro.leaving": "OWN-999"}})
        assert (settled.status, settled.exit_code) == (PASS, 0), settled.render()
        assert settled.violations == [], settled.render()
        assert settled.checked == [legitimate], settled.checked

        # Step 4 — a tombstone is settled only byte-identically. Restating the
        # same id under a different citation names no removal this run can see,
        # since the id is no longer in the baseline's `events`, and is refused
        # as input rather than quietly treated as already-approved.
        restated = gate({"events": kept, "removals": {"veyro.leaving": "OWN-998"}})
        assert (restated.status, restated.exit_code) == (ERROR, 2), restated.render()
        assert restated.codes() == {"EVENT_CONTRACT_GATE_INPUT_INVALID"}, restated.render()
        assert "removals declares veyro.leaving, absent from the baseline" in \
            restated.violations[0].detail, restated.render()

        # Step 5 — carrying the settled tombstone does not open the document to
        # pre-staged citations alongside it; only the genuinely new id is named.
        prestaged = gate({"events": kept, "removals": {"veyro.leaving": "OWN-999",
                                                       "veyro.never": "OWN-999"}})
        assert (prestaged.status, prestaged.exit_code) == (ERROR, 2), prestaged.render()
        assert prestaged.codes() == {"EVENT_CONTRACT_GATE_INPUT_INVALID"}, prestaged.render()
        assert "removals declares veyro.never, absent from the baseline" in \
            prestaged.violations[0].detail, prestaged.render()

        # Step 6 — the spent approval cannot be re-aimed. OWN-999 is live and
        # already authorised one withdrawal; pointed at a second event it does
        # not approve withdrawing, it denies on the removal axis, and the settled tombstone
        # beside it contributes no violation of its own.
        reaimed = gate({"events": {"veyro.staying": entry()},
                        "removals": {"veyro.leaving": "OWN-999",
                                     "veyro.later": "OWN-999"}})
        assert (reaimed.status, reaimed.exit_code) == (FAIL, 1), reaimed.render()
        assert [(v.code, v.subject) for v in reaimed.violations] == [
            ("EVENT_REMOVED_UNAPPROVED", "veyro.later")], reaimed.render()
        assert "does not approve withdrawal of 'veyro.later'" in reaimed.violations[0].detail, \
            reaimed.render()

        # Step 7 — and an accepted tombstone never stands in for a citation the
        # candidate owes: dropping `veyro.later` with only the settled
        # `veyro.leaving` entry present is as un-cited as step 1.
        uncited = gate({"events": {"veyro.staying": entry()},
                        "removals": {"veyro.leaving": "OWN-999"}})
        assert (uncited.status, uncited.exit_code) == (FAIL, 1), uncited.render()
        assert [(v.code, v.subject) for v in uncited.violations] == [
            ("EVENT_REMOVED_UNAPPROVED", "veyro.later")], uncited.render()
        assert "missing OWN-NNN approval" in uncited.violations[0].detail

        # Step 8 — generation 2: a second withdrawal with its own distinct
        # approval clears beside the settled tombstone, and promoting a baseline
        # that now carries two tombstones leaves the unchanged candidate passing.
        second = {"events": {"veyro.staying": entry()},
                  "removals": {"veyro.leaving": "OWN-999", "veyro.later": "OWN-996"}}
        cleared = gate(second)
        assert (cleared.status, cleared.exit_code) == (PASS, 0), cleared.render()
        assert cleared.violations == [], cleared.render()
        promote()
        again = gate(second)
        assert (again.status, again.exit_code) == (PASS, 0), again.render()
        assert again.violations == [], again.render()
        assert again.checked == [legitimate], again.checked

        # Step 9 — disclosed, not a safety claim: a later candidate may drop a
        # settled tombstone. Nothing is withdrawn by the omission (the id is
        # absent from the baseline's `events` either way), and re-registering it
        # afterwards is an addition, which neither half of this gate has ever
        # required an approval for.
        retired = gate({"events": {"veyro.staying": entry()}})
        assert (retired.status, retired.exit_code) == (PASS, 0), retired.render()
        assert retired.violations == [], retired.render()

        # Step 10 — the premise the whole lifecycle rests on, pinned on the
        # *baseline* side rather than only the candidate side. A baseline's
        # `events` and `removals` key sets are disjoint because a document
        # declaring one id both ways is refused as input; that disjointness is
        # what makes a tombstone structurally unreachable by the
        # `baseline - registry` removal accounting, so "a baseline tombstone can
        # never be read as the approval for a withdrawal" is a property of the
        # input contract and not of the order of a few conditions.
        baseline.write_text(json.dumps({
            "events": {"veyro.staying": entry(), "veyro.later": entry()},
            "removals": {"veyro.later": "OWN-996"}}))
        both = gate({"events": {"veyro.staying": entry()},
                     "removals": {"veyro.later": "OWN-996"}})
        assert (both.status, both.exit_code) == (ERROR, 2), both.render()
        assert both.codes() == {"EVENT_CONTRACT_GATE_INPUT_INVALID"}, both.render()
        assert "veyro.later: declared removed while still registered" in \
            both.violations[0].detail, both.render()
        assert str(baseline) in both.violations[0].detail, both.render()


def test_event_contract_removal_approval_must_approve_that_withdrawal():
    """Gate-3 R1 P1-2, approval intent: a removal citation must be an owner row
    whose *Action approved* explicitly approves withdrawing exactly that event.

    The false green this pins (independently replayed 2026-10-09): candidate
    `removals.gone=OWN-999` cleared PASS/exit 0 against a live row approving only
    the introduction of `gone` and saying withdrawal is not approved, because the
    removal path used mention-only `resolve_approval`. TSD §24.1 reserves the
    compatibility decision to the owner, so a different decision about the same
    event cannot stand in for it. Synthetic register rows only.
    """
    def entry() -> dict:
        return {"schema": {"type": "object"}, "classification": "internal"}

    def own(ref: str, action: str, scope: str = "synthetic") -> str:
        return f"| {ref} | {action} | {scope} | 2026-10-09 | synthetic |\n"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "app"
        src.mkdir()
        (src / "flow.py").write_text('emit_event("kept")\n')
        registry, baseline = root / "registry.json", root / "baseline.json"
        baseline.write_text(json.dumps({"events": {"gone": entry(), "kept": entry()}}))
        approvals = root / "knowledge" / "00-System"
        approvals.mkdir(parents=True)
        register = approvals / "OWNER_APPROVALS.md"

        def gate(action: str, scope: str = "synthetic"):
            register.write_text(own("OWN-999", action, scope))
            registry.write_text(json.dumps({"events": {"kept": entry()},
                                            "removals": {"gone": "OWN-999"}}))
            return run_event_contract_gate(src, registry, baseline, root)

        # Positive: a clear, explicit withdrawal approval for exactly `gone`.
        for action in ("Approve withdrawal of event `gone`",
                       "Approved removal of the event gone from the registry",
                       "Authorise withdrawal of event gone."):
            ok = gate(action)
            assert (ok.status, ok.exit_code) == (PASS, 0), (action, ok.render())
            assert ok.violations == [], (action, ok.render())

        denied = (
            # The reproduced false green: introduction-only, withdrawal refused.
            ("Approve introduction of event gone only; withdrawal is not approved",
             "synthetic", "negation"),
            # Introduction-only, with no negation to lean on.
            ("Approve introduction of event gone", "synthetic",
             "does not approve withdrawal of 'gone'"),
            # Another event's withdrawal; `gone` mentioned only in Scope.
            ("Approve withdrawal of event other", "covers gone",
             "does not approve withdrawal of 'gone'"),
            # A different id sharing `gone` as a prefix.
            ("Approve withdrawal of event gone.v2", "synthetic",
             "does not approve withdrawal of 'gone'"),
            # Negated withdrawal phrased around the exact approving clause.
            ("Do not approve withdrawal of event gone", "synthetic", "negation"),
            ("Withdrawal of event gone is not approved", "synthetic", "negation"),
            # Withdrawal intent stated only outside *Action approved*.
            ("Approve introduction of event gone", "Approve withdrawal of event gone",
             "does not approve withdrawal of 'gone'"),
        )
        for action, scope, expected in denied:
            report = gate(action, scope)
            assert (report.status, report.exit_code) == (FAIL, 1), (action, report.render())
            assert [(v.code, v.subject) for v in report.violations] == [
                ("EVENT_REMOVED_UNAPPROVED", "gone")], (action, report.render())
            assert expected in report.violations[0].detail, (action, report.render())

        # A register row not in the table's 5-column shape is not bindable.
        register.write_text("| OWN-999 | Approve withdrawal of event gone |\n")
        registry.write_text(json.dumps({"events": {"kept": entry()},
                                        "removals": {"gone": "OWN-999"}}))
        short = run_event_contract_gate(src, registry, baseline, root)
        assert (short.status, short.exit_code) == (FAIL, 1), short.render()
        assert "not a 5-column" in short.violations[0].detail, short.render()


def test_event_contract_schema_must_be_in_the_supported_json_schema_subset():
    """Gate-3 R1 P2-1: a nonempty dict is not a JSON Schema.

    `{"x": 1}` used to register an event. Each `schema` -- in the candidate and
    the baseline alike, before membership or diff can produce PASS -- must now
    sit inside the documented dependency-free subset, else input ERROR naming
    the event and the JSON Pointer of the offending node.
    """
    good = {"type": "object", "properties": {"id": {"type": "string"},
                                             "tags": {"type": "array",
                                                      "items": {"type": "string"}}},
            "required": ["id"], "additionalProperties": False}
    bad_schemas = (
        ({"x": 1}, "at /: unsupported keyword(s) ['x']"),
        ({"type": "obj"}, "at /type:"),
        ({"type": ["object", "object"]}, "at /type:"),
        ({"type": "object", "properties": {"id": {"x": 1}}},
         "at /properties/id: unsupported keyword(s) ['x']"),
        ({"type": "object", "properties": {"id": {"type": 7}}}, "at /properties/id/type:"),
        ({"type": "object", "properties": {"id": "string"}},
         "at /properties/id: schema must be an object"),
        ({"type": "object", "properties": []}, "at /properties: must be an object"),
        ({"type": "object", "required": "id"}, "at /required:"),
        ({"type": "array", "items": {"$ref": "#/x"}}, "at /items: unsupported keyword(s) ['$ref']"),
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "app"
        src.mkdir()
        (src / "flow.py").write_text('emit_event("veyro.created")\n')
        registry, baseline = root / "registry.json", root / "baseline.json"

        def gate(candidate: dict, accepted: dict):
            registry.write_text(json.dumps({"events": {"veyro.created": {
                "schema": candidate, "classification": "internal"}}}))
            baseline.write_text(json.dumps({"events": {"veyro.created": {
                "schema": accepted, "classification": "internal"}}}))
            return run_event_contract_gate(src, registry, baseline, root)

        ok = gate(good, good)
        assert (ok.status, ok.exit_code) == (PASS, 0), ok.render()

        for schema, expected in bad_schemas:
            # Candidate/baseline parity: the same malformed schema denies identically
            # whichever side carries it.
            for side, report in (("registry", gate(schema, good)), ("baseline", gate(good, schema))):
                assert (report.status, report.exit_code) == (ERROR, 2), (side, schema, report.render())
                [violation] = report.violations
                assert violation.code == "EVENT_CONTRACT_GATE_INPUT_INVALID", (side, report.render())
                assert f"{side}.json: veyro.created:" in violation.detail, (side, report.render())
                assert expected in violation.detail, (side, schema, violation.detail)


# --- ADR-009 D1-D4 ----------------------------------------------------------------

SIGN_IN = {"action": "create", "resource": "iam.session", "scope": "self"}
INGEST = {"action": "ingest", "resource": "billing.provider_event", "scope": "explicit_resource"}
HEALTH = {"action": "read", "resource": "platform.health", "scope": "explicit_resource"}
FOUR_CLASSES = {
    "/members/{id}/profile": {"get": _op("getProfile", READ)},
    "/sessions": {"post": _op("signIn", SIGN_IN, "credential_exchange", [])},
    "/webhooks/provider": {"post": _op("ingest", INGEST, "provider_signature", [])},
    "/health": {"get": _op("health", HEALTH, "anonymous", [])},
}


def test_adr009_one_operation_of_each_class_passes_with_visible_inventory():
    report = _run(FOUR_CLASSES)
    assert report.status == PASS, report.render()
    assert report.inventory == [
        {"endpoint": "api.json:GET /health (health)", "authentication": "anonymous",
         "permission": "platform.health.read", "approval": "ADR-009"},
        {"endpoint": "api.json:POST /sessions (signIn)", "authentication": "credential_exchange",
         "permission": "iam.session.create", "approval": "ADR-009"},
        {"endpoint": "api.json:POST /webhooks/provider (ingest)",
         "authentication": "provider_signature", "permission": "billing.provider_event.ingest",
         "approval": "ADR-009"},
    ]
    assert ("authentication classes: authenticated=1, credential_exchange=1, "
            "provider_signature=1, anonymous=1") in report.notes
    text = report.render()
    for row in report.inventory:
        assert (f"inventory: {row['authentication']}: {row['endpoint']} -> "
                f"{row['permission']} (approval ADR-009)") in text


def test_adr009_inventory_printed_by_cli_on_pass():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "openapi").mkdir()
        (root / "openapi" / "api.json").write_text(json.dumps(_doc(FOUR_CLASSES)))
        (root / "r.json").write_text(json.dumps(REGISTRY))
        base = [sys.executable, str(TOOLS / "validate_architecture_gates.py"), "--gate",
                "permission", "--openapi-dir", str(root / "openapi"), "--registry",
                str(root / "r.json")]
        text = subprocess.run(base, capture_output=True, text=True, check=False)
        js = subprocess.run([*base, "--json"], capture_output=True, text=True, check=False)
    assert text.returncode == 0 and js.returncode == 0, text.stdout + js.stdout
    assert text.stdout.count("inventory: ") == 3
    assert ("inventory: anonymous: api.json:GET /health (health) -> platform.health.read "
            "(approval ADR-009)") in text.stdout
    assert len(json.loads(js.stdout)["inventory"]) == 3


def test_adr009_missing_or_unknown_authentication_class_fails():
    _single_violation(_run({"/p": {"get": _op("p", READ, auth=None)}}), "GET /p",
                      "no x-veyro-authentication")
    for bad in ("public", "Anonymous", "authenticated ", "", ["anonymous"], None.__class__.__name__):
        report = _run({"/p": {"get": _op("p", READ, auth=bad)}})
        _single_violation(report, "GET /p", "is not one of")


def test_adr009_operation_class_must_match_registry_class():
    # anonymous declaration on an `authenticated`-registered permission, security made
    # consistent so the two-key mismatch is the only failure.
    _single_violation(_run({"/p": {"get": _op("p", READ, "anonymous", [])}}), "GET /p",
                      "does not match registry class 'authenticated'")
    # authenticated declaration on a credential_exchange-registered permission
    _single_violation(_run({"/s": {"post": _op("s", SIGN_IN, AUTH)}}), "POST /s",
                      "does not match registry class 'credential_exchange'")
    # credential_exchange vs registry anonymous
    _single_violation(_run({"/h": {"get": _op("h", HEALTH, "credential_exchange", [])}}),
                      "GET /h", "does not match registry class 'anonymous'")


def test_adr009_authenticated_security_consistency():
    cases = [
        (_doc({"/p": {"get": _op("p", READ)}}, root_security=[{}]), "empty security requirement"),
        (_doc({"/p": {"get": _op("p", READ)}}, root_security=[{"session": []}, {}]),
         "empty security requirement"),
        (_doc({"/p": {"get": _op("p", READ, security=[])}}), "no effective security"),
        (_doc({"/p": {"get": _op("p", READ)}}, root_security=None), "no effective security"),
        (_doc({"/p": {"get": _op("p", READ, security=[{"session": []}, {}])}}),
         "empty security requirement"),
    ]
    for doc, reason in cases:
        _single_violation(_run(doc=doc), "GET /p", reason)


def test_adr009_anonymous_requires_explicit_empty_security():
    for op in (_op("h", HEALTH, "anonymous"), _op("h", HEALTH, "anonymous", [{"session": []}]),
               _op("h", HEALTH, "anonymous", [{}])):
        _single_violation(_run({"/h": {"get": op}}), "GET /h", '"security": [] explicitly')
    # inheriting an empty root is still not explicit
    doc = _doc({"/h": {"get": _op("h", HEALTH, "anonymous")}}, root_security=[])
    _single_violation(_run(doc=doc), "GET /h", '"security": [] explicitly')


def test_adr009_non_session_classes_may_not_inherit_root_security():
    # ADR-010 D5.2 reclassifies this from a violation to an input ERROR.
    for paths in ({"/s": {"post": _op("s", SIGN_IN, "credential_exchange")}},
                  {"/w": {"post": _op("w", INGEST, "provider_signature")}}):
        report = _run(paths)
        assert report.status == ERROR, report.render()
        assert "must set security explicitly" in report.violations[0].detail
    # explicit non-empty security is allowed when the scheme is defined
    assert _run({"/s": {"post": _op("s", SIGN_IN, "credential_exchange",
                                    [{"session": []}])}}).status == PASS


def test_adr009_operation_bearing_blind_spots_are_errors():
    op = {"get": _op("p", READ)}
    callback_op = dict(_op("p", READ), callbacks={"cb": {"{$url}": {"post": _op("c", READ)}}})
    docs = [
        _doc({"/p": op}, webhooks={}),
        _doc({"/p": op}, webhooks={"evt": {"post": _op("w", READ)}}),
        _doc({"/p": {"get": callback_op}}),
        _doc({"/p": op}, components={"securitySchemes": SESSION_SCHEME, "pathItems": {}}),
        _doc({"/p": op}, components={"securitySchemes": SESSION_SCHEME, "callbacks": {}}),
        _doc({"p": op}),
        _doc({"/p": op}, components=[]),
        _doc({"/p": op}, root_security=[{"apiKey": []}]),
        _doc({"/p": {"get": _op("p", READ, security=[["session"]])}}),
        _doc({"/p": {"get": dict(_op("p", READ), operationId=7)}}),
    ]
    for doc in docs:
        report = _run(doc=doc)
        assert report.status == ERROR, (doc, report.render())
        assert report.codes() == {"PERMISSION_GATE_INPUT_INVALID"}


def _run_files(files, registry=REGISTRY):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "openapi").mkdir()
        for name, doc in files.items():
            target = root / "openapi" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(doc))
        (root / "r.json").write_text(json.dumps(registry))
        return run_permission_gate(root / "openapi", root / "r.json")


def test_adr009_cross_document_duplicates_are_errors():
    a = _doc({"/members/{id}/profile": {"get": _op("getProfile", READ)}})
    same_route = _doc({"/members/{memberId}/profile": {"get": _op("getProfile2", READ)}})
    same_op_id = _doc({"/other": {"get": _op("getProfile", READ)}})
    for files in ({"a.json": a, "sub/b.json": same_route}, {"a.json": a, "b.json": same_op_id}):
        report = _run_files(files)
        assert report.status == ERROR, report.render()
        assert "duplicate" in report.violations[0].detail
    within = _doc({"/x": {"get": _op("dup", READ)}, "/y": {"get": _op("dup", READ)}})
    assert _run_files({"a.json": within}).status == ERROR
    # different method on the same template is a different operation
    ok = _doc({"/x/{id}": {"get": _op("g", READ), "post": _op("q", REFUND)}})
    assert _run_files({"a.json": ok}).status == PASS


def test_adr009_symlinks_are_errors():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        real = root / "real.json"
        real.write_text(json.dumps(_doc(VALID_PATHS)))
        (root / "r.json").write_text(json.dumps(REGISTRY))
        for case in ("file", "dir", "openapi_dir", "registry"):
            openapi = root / f"openapi_{case}"
            openapi.mkdir()
            registry = root / "r.json"
            if case == "file":
                (openapi / "api.json").symlink_to(real)
            elif case == "dir":
                (root / "realdir").mkdir(exist_ok=True)
                (openapi / "linked").symlink_to(root / "realdir", target_is_directory=True)
            elif case == "openapi_dir":
                (openapi / "api.json").write_text(real.read_text())
                link = root / "openapi_link"
                link.symlink_to(openapi, target_is_directory=True)
                openapi = link
            else:
                (openapi / "api.json").write_text(real.read_text())
                registry = root / "r_link.json"
                registry.symlink_to(root / "r.json")
            report = run_permission_gate(openapi, registry)
            assert report.status == ERROR, (case, report.render())


def test_adr009_no_exemption_or_skip_option_in_cli():
    res = subprocess.run([sys.executable, str(TOOLS / "validate_architecture_gates.py"), "--help"],
                         capture_output=True, text=True, check=False)
    lowered = res.stdout.lower()
    for word in ("exempt", "skip", "allowlist", "public", "ignore"):
        assert word not in lowered, word


# --- ADR-010 D5 (registry approvals, security strictness) ---------------------------


def _approval_root(adr_text=None, own_rows=None, extra_adr=None):
    root = Path(tempfile.mkdtemp(prefix="veyro-d5-"))
    (root / "knowledge" / "04-Decisions").mkdir(parents=True)
    (root / "knowledge" / "00-System").mkdir(parents=True)
    if adr_text is not None:
        (root / "knowledge" / "04-Decisions" / "ADR-901-fixture.md").write_text(adr_text)
    if extra_adr is not None:
        ref, status, body = extra_adr
        (root / "knowledge" / "04-Decisions" / f"{ref}-fixture.md").write_text(
            f"---\nstatus: {status}\n---\n{body}\n")
    (root / "knowledge" / "00-System" / "OWNER_APPROVALS.md").write_text(
        "| ID | Decision |\n|---|---|\n" + "".join(f"{r}\n" for r in (own_rows or [])))
    return root


def _registry_with(approval):
    """REGISTRY with every non-`authenticated` entry citing the synthetic ADR-901 (which
    names all three), and iam.session.create citing `approval` — so each case varies one
    approval and every other approval in the document genuinely resolves."""
    reg = json.loads(json.dumps(REGISTRY))
    for entry in reg["permissions"].values():
        if "approval" in entry:
            entry["approval"] = "ADR-901"
    reg["permissions"]["iam.session.create"]["approval"] = approval
    return reg


_ADR901 = ("---\nstatus: DECIDED\n---\niam.session.create\nbilling.provider_event.ingest\n"
           "platform.health.read\n")


def _run_with_root(paths, registry, root):
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "openapi").mkdir()
        (d / "openapi" / "api.json").write_text(json.dumps(_doc(paths)))
        (d / "r.json").write_text(json.dumps(registry))
        return run_permission_gate(d / "openapi", d / "r.json", root)


def test_n24_registry_approval_rules():
    sign_in = {"/s": {"post": _op("s", SIGN_IN, "credential_exchange", [])}}
    good = _approval_root(_ADR901,
                          ["| OWN-901 | approves iam.session.create |", "| OWN-902 | other |"])
    assert _run_with_root(sign_in, _registry_with("ADR-901"), good).status == PASS
    assert _run_with_root(sign_in, _registry_with("OWN-901"), good).status == PASS
    # Other entries still need ADR-901 to resolve, so these roots carry a second ADR whose
    # status/content is the variable under test.
    no_mention = _approval_root(_ADR901, extra_adr=("ADR-902", "DECIDED", "nothing relevant"))
    superseded = _approval_root(_ADR901, extra_adr=("ADR-902", "SUPERSEDED",
                                                    "iam.session.create"))
    cases = [
        (_registry_with("ADR-999"), good),        # unresolvable ADR
        (_registry_with("ADR-902"), no_mention),  # record lacks the permission name
        (_registry_with("ADR-902"), superseded),  # not DECIDED/ACCEPTED
        (_registry_with("OWN-902"), good),        # OWN row lacks the permission name
        (_registry_with("OWN-999"), good),        # no OWN row
        (_registry_with("ADR-1"), good),          # malformed reference
    ]
    missing = _registry_with("ADR-901")
    del missing["permissions"]["iam.session.create"]["approval"]
    on_auth = _registry_with("ADR-901")
    on_auth["permissions"]["members.profile.read"]["approval"] = "ADR-901"
    v1 = dict(_registry_with("ADR-901"), version=1)
    cases += [(missing, good), (on_auth, good), (v1, good)]
    for registry, root in cases:
        report = _run_with_root(sign_in, registry, root)
        assert report.status == ERROR, (registry["permissions"].get("iam.session.create"),
                                        report.render())
        assert report.codes() == {"PERMISSION_GATE_INPUT_INVALID"}


def test_n25_security_strictness_is_error():
    def scheme_doc(bad):
        # The valid `session` scheme stays so root security still resolves; `bad` is the
        # only defect, and the authenticated op references it (R2 P3 case for {}).
        schemes = dict(SESSION_SCHEME, bad=bad)
        return _doc({"/p": {"get": _op("p", READ, security=[{"bad": []}])}},
                    components={"securitySchemes": schemes})
    cases = [
        (_doc({"/s": {"post": dict(_op("s", SIGN_IN, "credential_exchange"), security=None)}}),
         "security must be a list"),
        (_doc({"/w": {"post": dict(_op("w", INGEST, "provider_signature"), security=None)}}),
         "security must be a list"),
        (scheme_doc({}), "securitySchemes.bad type None"),
        (scheme_doc({"$ref": "#/components/securitySchemes/session"}),
         "securitySchemes.bad must be an inline"),
        (scheme_doc({"type": "bearer"}), "type 'bearer' unsupported"),
        (scheme_doc({"type": "apiKey", "name": "k"}), "needs a non-empty 'in'"),
        (scheme_doc({"type": "apiKey", "name": "k", "in": "body"}), "query/header/cookie"),
        (scheme_doc({"type": "http", "scheme": " "}), "needs a non-empty 'scheme'"),
        (scheme_doc({"type": "oauth2", "flows": {}}), "needs a non-empty 'flows'"),
        (scheme_doc({"type": "openIdConnect"}), "needs a non-empty 'openIdConnectUrl'"),
        # an unreferenced malformed scheme is still ERROR: every defined scheme is validated
        (dict(_doc(VALID_PATHS), components={"securitySchemes": dict(SESSION_SCHEME, unused={})}),
         "securitySchemes.unused"),
        (_doc({"/p": {"get": _op("p", READ, security=[{"session": "scope"}])}}),
         "security must be a list"),
        (_doc({"/p": {"get": _op("p", READ, security=[{"session": [1]}])}}),
         "security must be a list"),
        (_doc({"/p": {"get": _op("p", READ, security=[{"apiKey": []}])}}), "undefined scheme"),
        (dict(_doc({"/p": {"get": _op("p", READ, security=[{"session": []}])}}), security=None),
         "root: security must be a list"),
    ]
    for doc, fragment in cases:
        report = _run(doc=doc)
        assert report.status == ERROR, (doc, report.render())
        assert report.codes() == {"PERMISSION_GATE_INPUT_INVALID"}
        assert fragment in report.violations[0].detail, (fragment, report.render())
    good_schemes = {"k": {"type": "apiKey", "name": "X-Key", "in": "header"},
                    "b": {"type": "http", "scheme": "bearer"}, "m": {"type": "mutualTLS"},
                    "o": {"type": "oauth2", "flows": {"clientCredentials": {}}},
                    "i": {"type": "openIdConnect", "openIdConnectUrl": "https://example.invalid"}}
    doc = _doc({"/p": {"get": _op("p", READ, security=[{"b": []}])}}, root_security=None,
               components={"securitySchemes": good_schemes})
    report = _run(doc=doc)
    assert report.status == PASS, report.render()


# --- RLS gate (ADR-010): pure verdicts -------------------------------------------

EXPR = CANONICAL_TENANT_PREDICATE
GOOD_POLICY = Policy("tenant_isolation", True, "*", EXPR, EXPR, True)
GOOD_TABLE = Relation("harness", "access_grant", "r", True, True, True, True, True, (GOOD_POLICY,))
RT_ROLE = RoleInfo("veyro_runtime", 20000)
DML = [AclGrant("table", "harness.access_grant", p, "veyro_runtime",
                relation="harness.access_grant", schema="harness")
       for p in ("SELECT", "INSERT", "UPDATE", "DELETE")]
BASE = RlsCatalog("veyro_runtime", True, 160015, "postgres", (RT_ROLE,), (GOOD_TABLE,),
                  (*DML, AclGrant("schema", "harness", "USAGE", "veyro_runtime",
                                        schema="harness"),
                         AclGrant("database", "postgres", "CONNECT", "PUBLIC")),
                  scanned_schemas=("harness",))


def _rls(catalog=BASE, manifest=None, **kw):
    return evaluate_rls(catalog, manifest or RlsManifest(), **kw)


def _with(**changes):
    return replace(BASE, **changes)


def _tokens(report):
    return [(v.code, v.detail) for v in report.violations]


def _expect(report, code, fragment):
    assert report.status == FAIL, report.render()
    assert any(c == code and fragment in d for c, d in _tokens(report)), report.render()


def test_rls_canonical_catalog_passes():
    report = _rls()
    assert report.status == PASS, report.render()
    assert report.checked == ["harness.access_grant"]


def test_rls_table_rules_fail():
    for rel, code, frag in [
        (replace(GOOD_TABLE, rls_enabled=False), "RLS_NOT_ENFORCED", "ENABLE"),
        (replace(GOOD_TABLE, rls_forced=False), "RLS_NOT_ENFORCED", "FORCE"),
        (replace(GOOD_TABLE, policies=()), "RLS_NOT_ENFORCED", "no RLS policy"),
        (replace(GOOD_TABLE, tenant_id_not_null=False), "RLS_TENANT_ID_NULLABLE", "nullable"),
        (replace(GOOD_TABLE, tenant_id_uuid=False), "RLS_TENANT_ID_NOT_UUID", "not uuid"),
    ]:
        _expect(_rls(_with(relations=(rel,))), code, frag)


def test_rls_predicate_deparse_and_dependency_closure():
    for using, check in [("true", "true"), ("(tenant_id IS NOT NULL)", None),
                         ("(tenant_id = tenant_id)", None), (f"({EXPR} OR true)", None),
                         (EXPR, "('tenant_id'::text IS NOT NULL)"),
                         (EXPR.replace("app.tenant_id", "app.other"), None)]:
        pol = Policy("p", True, "*", using, check, True)
        _expect(_rls(_with(relations=(replace(GOOD_TABLE, policies=(pol,)),))),
                "RLS_NOT_ENFORCED", "canonical tenant predicate")
    # Single-clause faults, so one rule cannot mask the other: a tautological USING with a
    # canonical WITH CHECK (read leak), a SELECT-only permissive policy, and the reverse.
    for pol, frag in [(Policy("p", True, "*", "true", EXPR, True), "USING"),
                      (Policy("p", True, "r", "true", None, True), "USING"),
                      (Policy("p", True, "*", EXPR, "true", True), "WITH CHECK"),
                      (Policy("p", True, "a", None, "true", True), "WITH CHECK")]:
        report = _rls(_with(relations=(replace(GOOD_TABLE, policies=(GOOD_POLICY, pol)),)))
        assert [d for c, d in _tokens(report)] and all(frag in d for c, d in _tokens(report)), (
            frag, report.render())
    hijacked = Policy("p", True, "*", EXPR, EXPR, True, ("operator public.=(uuid,uuid)",))
    _expect(_rls(_with(relations=(replace(GOOD_TABLE, policies=(hijacked,)),))),
            "RLS_NOT_ENFORCED", "depends on")
    narrow = Policy("narrow", False, "*", "true", "true", True, ("function f()",))
    other_role = Policy("reporting", True, "r", "true", None, False)
    ok = replace(GOOD_TABLE, policies=(GOOD_POLICY, narrow, other_role))
    assert _rls(_with(relations=(ok,))).status == PASS


def test_rls_attributes_predefined_roles_and_ownership():
    for role, frag in [
        (replace(RT_ROLE, replication=True), "ATTRIBUTE:REPLICATION@veyro_runtime"),
        (replace(RT_ROLE, createrole=True), "ATTRIBUTE:CREATEROLE@veyro_runtime"),
        (replace(RT_ROLE, createdb=True), "ATTRIBUTE:CREATEDB@veyro_runtime"),
        (replace(RT_ROLE, bypassrls=True), "ATTRIBUTE:BYPASSRLS@veyro_runtime"),
        (replace(RT_ROLE, superuser=True), "ATTRIBUTE:SUPERUSER@veyro_runtime"),
    ]:
        _expect(_rls(_with(closure=(role,))), "RLS_RUNTIME_ROLE_ELEVATED", frag)
    for name, oid in [("pg_execute_server_program", 4571), ("pg_database_owner", 6171),
                      ("pg_custom_named", 30000)]:
        _expect(_rls(_with(closure=(RT_ROLE, RoleInfo(name, oid)))),
                "RLS_RUNTIME_ROLE_ELEVATED", f"PREDEFINED_ROLE:{name}")
    group = RoleInfo("veyro_group", 30001, bypassrls=True)
    _expect(_rls(_with(closure=(RT_ROLE, group))), "RLS_RUNTIME_ROLE_ELEVATED",
            "ATTRIBUTE:BYPASSRLS@veyro_group")
    for owned in [("schema", "harness"), ("database", "postgres"), ("sequence", "o.s")]:
        _expect(_rls(_with(owned=(owned,))), "RLS_RUNTIME_ROLE_ELEVATED",
                f"OWNS:{owned[0]}:{owned[1]}")


def test_rls_privilege_allow_table_is_default_deny():
    cases = [
        AclGrant("table", "harness.access_grant", "TRUNCATE", "veyro_runtime",
                 relation="harness.access_grant", schema="harness"),
        AclGrant("table", "harness.access_grant", "MAINTAIN", "veyro_runtime",
                 relation="harness.access_grant", schema="harness"),
        AclGrant("table", "harness.access_grant", "SELECT", "PUBLIC",
                 relation="harness.access_grant", schema="harness"),
        AclGrant("schema", "harness", "CREATE", "veyro_runtime", schema="harness"),
        AclGrant("database", "postgres", "CREATE", "veyro_runtime"),
        AclGrant("large_object", "16500", "SELECT", "veyro_runtime"),
        AclGrant("tablespace", "pg_default", "CREATE", "veyro_runtime"),
        AclGrant("parameter", "work_mem", "SET", "veyro_runtime"),
        AclGrant("fdw", "postgres_fdw", "USAGE", "veyro_runtime"),
        AclGrant("server", "s", "USAGE", "veyro_runtime"),
        AclGrant("sequence", "harness.s", "USAGE", "PUBLIC", relation="harness.s",
                 schema="harness"),
        AclGrant("some_future_class", "x", "USAGE", "veyro_runtime"),
    ]
    for gr in cases:
        _expect(_rls(_with(grants=(*BASE.grants, gr))), "RLS_RUNTIME_ROLE_ELEVATED",
                f"PRIVILEGE:{gr.obj_class}:{gr.identity}:{gr.privilege}@{gr.grantee}")
    allowed = [AclGrant("sequence", "harness.s", p, "veyro_runtime", relation="harness.s",
                        schema="harness") for p in ("USAGE", "SELECT", "UPDATE")]
    allowed += [AclGrant("function", "harness.f()", "EXECUTE", "PUBLIC", schema="harness"),
                AclGrant("type", "harness.t", "USAGE", "PUBLIC", schema="harness"),
                AclGrant("database", "postgres", "TEMPORARY", "PUBLIC")]
    seq = Relation("harness", "s", "S")
    assert _rls(_with(grants=(*BASE.grants, *allowed),
                      relations=(GOOD_TABLE, seq))).status == PASS


def test_rls_system_acl_must_equal_initial():
    modified = AclGrant("function", "pg_read_binary_file(text)", "EXECUTE", "PUBLIC",
                        system=True, in_initial=False, schema="pg_catalog")
    _expect(_rls(_with(grants=(*BASE.grants, modified))), "RLS_RUNTIME_ROLE_ELEVATED",
            "SYSTEM_ACL_MODIFIED:pg_read_binary_file(text):EXECUTE@PUBLIC")
    stock = AclGrant("function", "lower(text)", "EXECUTE", "PUBLIC", system=True,
                     in_initial=True, schema="pg_catalog")
    assert _rls(_with(grants=(*BASE.grants, stock))).status == PASS
    # PG16 information_schema pin: only the initdb PUBLIC shape is tolerated.
    info_ok = [AclGrant("view", "information_schema.tables", "SELECT", "PUBLIC", system=True,
                        in_initial=False, relation="information_schema.tables",
                        schema="information_schema"),
               AclGrant("schema", "information_schema", "USAGE", "PUBLIC", system=True,
                        in_initial=False, schema="information_schema")]
    assert _rls(_with(grants=(*BASE.grants, *info_ok))).status == PASS
    for bad in [replace(info_ok[0], privilege="INSERT"), replace(info_ok[0], grantee="veyro_runtime"),
                replace(info_ok[1], privilege="CREATE")]:
        _expect(_rls(_with(grants=(*BASE.grants, bad))), "RLS_RUNTIME_ROLE_ELEVATED",
                "SYSTEM_ACL_MODIFIED")
    on_pg17 = _with(server_version_num=170002, grants=(*BASE.grants, *info_ok))
    assert evaluate_rls(on_pg17, RlsManifest()).status == ERROR  # unpinned major, see N23



def _info(name, cls="view", priv="SELECT", grantee="PUBLIC", **kw):
    ident = f"information_schema.{name}"
    return AclGrant(cls, kw.pop("identity", ident), priv, grantee, system=True, in_initial=False,
                    relation=ident, schema="information_schema", **kw)


def test_a1_n32_information_schema_pin_is_exact_per_object():
    import validate_architecture_gates as gates
    pinned = [_info("tables"), _info("sql_features", "table"),
              AclGrant("schema", "information_schema", "USAGE", "PUBLIC", system=True,
                       in_initial=False, schema="information_schema")]
    assert _rls(_with(grants=(*BASE.grants, *pinned))).status == PASS
    assert len(gates.PINNED_INFORMATION_SCHEMA_SELECT[16]) == 62
    for bad, why in [
        (_info("_pg_user_mappings"), "stock but not pinned (H10)"),
        (_info("sql_parts", "table"), "stock but not pinned"),
        (_info("tables", "table"), "class mismatch: pin is per object AND class"),
        (_info("sql_features", "view"), "class mismatch"),
        (_info("tables", grantee="veyro_runtime"), "non-PUBLIC grantee"),
        (_info("tables", priv="INSERT"), "privilege other than SELECT"),
        (_info("tables", identity="information_schema.tables.table_name"), "column ACL"),
        (_info("tables", has_init_privs=True), "pin only applies without pg_init_privs"),
        (_info("zz_new"), "unknown relation name"),
        (AclGrant("schema", "information_schema", "CREATE", "PUBLIC", system=True,
                  in_initial=False, schema="information_schema"), "schema CREATE"),
    ]:
        report = _rls(_with(grants=(*BASE.grants, bad)))
        assert report.status == FAIL, (why, report.render())
        assert any("SYSTEM_ACL_MODIFIED" in d for _, d in _tokens(report)), (why, report.render())
    # Pin applied to an unpinned major: even if a future major's predicate were pinned,
    # its information_schema set must be pinned separately before anything is tolerated.
    gates.PINNED_TENANT_PREDICATES[17] = EXPR
    try:
        report = _rls(_with(server_version_num=170002, grants=(*BASE.grants, *pinned)))
    finally:
        del gates.PINNED_TENANT_PREDICATES[17]
    assert report.status == FAIL and any("SYSTEM_ACL_MODIFIED" in d for _, d in _tokens(report))


def test_a1_non_stock_objects_in_system_schemas():
    for gr in [
        AclGrant("view", "information_schema.zz_leak", "SELECT", "PUBLIC", non_stock=True,
                 relation="information_schema.zz_leak", schema="information_schema"),
        AclGrant("function", "zz_count()", "EXECUTE", "PUBLIC", non_stock=True,
                 schema="pg_catalog"),
        # a non-stock object named like a pinned one is still non-stock
        AclGrant("view", "information_schema.tables", "SELECT", "PUBLIC", non_stock=True,
                 relation="information_schema.tables", schema="information_schema"),
    ]:
        _expect(_rls(_with(grants=(*BASE.grants, gr))), "RLS_RUNTIME_ROLE_ELEVATED",
                f"NON_STOCK_SYSTEM_OBJECT:{gr.obj_class}:{gr.identity}:{gr.privilege}@PUBLIC")

def test_rls_out_of_scope_views_matviews_foreign_tables():
    other = AclGrant("table", "other.t", "SELECT", "veyro_runtime", relation="other.t",
                     schema="other")
    _expect(_rls(_with(grants=(*BASE.grants, other),
                       relations=(GOOD_TABLE, Relation("other", "t", "r")))),
            "RLS_RUNTIME_ROLE_ELEVATED", "OUT_OF_SCOPE:other.t")

    def granted(rel, priv="SELECT"):
        return _with(relations=(GOOD_TABLE, rel), grants=(*BASE.grants, AclGrant(
            {"v": "view", "m": "matview", "f": "foreign_table"}[rel.kind], rel.qualified, priv,
            "veyro_runtime", relation=rel.qualified, schema=rel.schema)))
    view = Relation("harness", "v", "v")
    _expect(_rls(granted(view)), "RLS_NOT_ENFORCED", "security_invoker")
    assert _rls(granted(replace(view, security_invoker=True))).status == PASS
    mv = Relation("harness", "mv", "m")
    _expect(_rls(granted(mv)), "RLS_NOT_ENFORCED", "materialized view")
    listed = RlsManifest({"harness.mv": "matview"})
    assert _rls(granted(mv), listed).status == PASS
    _expect(_rls(granted(mv, "INSERT"), listed), "RLS_RUNTIME_ROLE_ELEVATED",
            "PRIVILEGE:matview:harness.mv:INSERT")
    tid_mv = replace(mv, has_tenant_id=True)
    _expect(_rls(granted(tid_mv), listed), "RLS_EXEMPTION_INVALID", "has tenant_id")
    _expect(_rls(granted(Relation("harness", "ft", "f"))), "RLS_NOT_ENFORCED", "foreign table")
    # ungranted views/matviews/foreign tables are not violations (ADR-010 D4.4)
    assert _rls(_with(relations=(GOOD_TABLE, view, mv, Relation("harness", "ft", "f")))
                ).status == PASS


def test_rls_manifest_entry_semantics_and_unclassified():
    lookup = Relation("harness", "lookup", "r")
    _expect(_rls(_with(relations=(GOOD_TABLE, lookup))), "RLS_TABLE_UNCLASSIFIED", "")
    assert _rls(_with(relations=(GOOD_TABLE, lookup)),
                RlsManifest({"harness.lookup": "table"})).status == PASS
    for manifest, frag in [(RlsManifest({"harness.gone": "table"}), "does not exist"),
                           (RlsManifest({"harness.access_grant": "table"}), "has tenant_id"),
                           (RlsManifest({"harness.lookup": "matview"}), "does not match relkind")]:
        _expect(_rls(_with(relations=(GOOD_TABLE, lookup)), manifest), "RLS_EXEMPTION_INVALID",
                frag)


def test_rls_tenant_context_lo_compat_and_security_definer():
    _expect(_rls(_with(tenant_context_defaults=("app.tenant_id=x@role=veyro_runtime,database=*",))),
            "RLS_RUNTIME_ROLE_ELEVATED", "TENANT_CONTEXT_DEFAULT:app.tenant_id=x")
    _expect(_rls(_with(lo_compat_privileges=True)), "RLS_RUNTIME_ROLE_ELEVATED",
            "ATTRIBUTE:LO_COMPAT_PRIVILEGES@postgres")
    sd = _with(security_definer=("harness.f()",))
    _expect(_rls(sd), "RLS_SECURITY_DEFINER_UNREVIEWED", "")
    reviewed = RlsManifest(reviewed_security_definer_functions=frozenset({"harness.f()"}))
    assert _rls(sd, reviewed).status == PASS


def test_rls_scope_inputs():
    assert _rls(_with(missing_schemas=("harnes",))).status == ERROR
    missing_role = _with(runtime_exists=False, closure=())
    assert "RLS_RUNTIME_ROLE_MISSING" in _rls(missing_role).codes()
    _expect(_rls(required_tables=["harness.member"]), "RLS_REQUIRED_TABLE_MISSING", "")
    vacuous = _rls(_with(relations=(), grants=()))
    assert (vacuous.status, vacuous.codes()) == (INCONCLUSIVE, {"RLS_GATE_VACUOUS"})


# --- N22 manifest problems, N23 inspector problems -----------------------------------


def _manifest_root(adr_status="DECIDED", adr_keys=("harness.lookup",), own_row=None):
    root = Path(tempfile.mkdtemp(prefix="veyro-n22-"))
    (root / "knowledge" / "04-Decisions").mkdir(parents=True)
    (root / "knowledge" / "00-System").mkdir(parents=True)
    (root / "knowledge" / "04-Decisions" / "ADR-901-fixture.md").write_text(
        f"---\nstatus: {adr_status}\n---\n" + "\n".join(adr_keys) + "\n")
    (root / "knowledge" / "00-System" / "OWNER_APPROVALS.md").write_text(
        "| ID | Decision |\n|---|---|\n" + (f"{own_row}\n" if own_row else ""))
    return root


def _m(approval="ADR-901", kind="table", version=2, name="harness.lookup", **extra):
    return {"version": version,
            "platform_scope_relations": {name: {"kind": kind, "reason": "r",
                                                "approval": approval, **extra}},
            "reviewed_security_definer_functions": {}}


def test_n22_manifest_problems_are_errors():
    good = _manifest_root()
    assert parse_rls_manifest(_m(), good).platform_scope_relations == {"harness.lookup": "table"}
    own = _manifest_root(own_row="| OWN-901 | classifies harness.lookup |")
    assert parse_rls_manifest(_m("OWN-901"), own).platform_scope_relations
    bad = [
        (_m(version=1), good), (_m(version=True), good), (_m("ADR-999"), good),
        (_m(), _manifest_root(adr_keys=("other.table",))),
        (_m(), _manifest_root(adr_status="PROPOSED")),
        (_m("OWN-901"), _manifest_root(own_row="| OWN-901 | something else |")),
        (_m("OWN-902"), own), (_m(kind="view"), good), (_m(name="Harness.Lookup"), good),
        (_m(extra_key=1), good), ({**_m(), "extra": {}}, good),
        ({"version": 2, "platform_scope_relations": {},
          "reviewed_security_definer_functions": {"harness.f()": {"reason": "r",
                                                                  "approval": "ADR-999"}}}, good),
    ]
    for raw, root in bad:
        try:
            parse_rls_manifest(raw, root)
        except GateInputError:
            continue
        raise AssertionError(f"accepted manifest {raw}")


def test_n22_manifest_file_rules():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        for content in (('{"version": 2, "platform_scope_relations": {}, '
                        '"reviewed_security_definer_functions": {}, "version": 2}'),
                        "[" * 100000 + "]" * 100000, "{not json"):
            f = d / "m.json"
            f.write_text(content)
            try:
                load_rls_manifest(f, d)
            except GateInputError:
                continue
            raise AssertionError(content[:40])
        try:
            load_rls_manifest(d / "missing.json", d)
            raise AssertionError("missing manifest accepted")
        except GateInputError:
            pass
        real = d / "real.json"
        real.write_text(json.dumps(_m()))
        (d / "link.json").symlink_to(real)
        try:
            load_rls_manifest(d / "link.json", _manifest_root())
            raise AssertionError("symlinked manifest accepted")
        except GateInputError:
            pass
    # The committed skeleton parses and is empty (ADR-010 D3.6).
    committed = load_rls_manifest()
    assert committed.platform_scope_relations == {} and not committed.reviewed_security_definer_functions


def test_n22_cli_has_no_manifest_flag():
    res = subprocess.run(
        [sys.executable, str(TOOLS / "validate_architecture_gates.py"), "--gate", "rls",
         "--runtime-role", "veyro_runtime", "--non-tenant-manifest", "x.json"],
        capture_output=True, text=True, check=False, env={"PATH": "/usr/bin:/bin"},
    )
    assert res.returncode == 2 and "unrecognized arguments" in res.stderr


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeConn:
    """Scripted inspector connection for N23 (no database needed)."""

    def __init__(self, search_path=PINNED_SEARCH_PATH, fail_on=None, autocommit=True):
        self.autocommit = autocommit
        self.search_path = search_path
        self.fail_on = fail_on
        self.log = []

    def execute(self, query, params=None):
        self.log.append(query)
        if self.fail_on and self.fail_on in query:
            raise RuntimeError("permission denied for table")
        if "current_setting('search_path')" in query:
            return _FakeResult([(self.search_path,)])
        return _FakeResult([])


def test_n23_inspector_problems_are_errors():
    assert evaluate_rls(_with(server_version_num=170000), RlsManifest()).status == ERROR
    assert evaluate_rls(_with(server_version_num=180000), RlsManifest()).status == ERROR
    # Each case must fail for its own stated reason, not an incidental one.
    for conn, reason in ((_FakeConn(search_path="public, pg_catalog"), "search_path read-back"),
                         (_FakeConn(fail_on="server_version"), "catalog read failed"),
                         (_FakeConn(fail_on="pg_init_privs"), "catalog read failed"),
                         (_FakeConn(autocommit=False), "autocommit")):
        try:
            collect_rls_catalog(conn, "veyro_runtime")
        except GateInputError as exc:
            assert reason in str(exc), (reason, str(exc))
            continue
        raise AssertionError(conn.log)
    conn = _FakeConn(search_path="public, pg_catalog")
    report = run_rls_gate(conn, "veyro_runtime", manifest=RlsManifest())
    assert (report.status, report.codes()) == (ERROR, {"RLS_GATE_INPUT_INVALID"})
    assert "search_path read-back" in report.violations[0].detail
    # nothing after the pin and its read-back ran before the ERROR
    assert conn.log == [f"SET search_path = {PINNED_SEARCH_PATH}",
                        "SELECT pg_catalog.current_setting('search_path')", "RESET search_path"]
    # D2.1: the pin is the first statement; nothing reads the catalog before it.
    assert conn.log[0] == f"SET search_path = {PINNED_SEARCH_PATH}"


def test_rls_cli_without_dsn_is_error():
    res = subprocess.run(
        [sys.executable, str(TOOLS / "validate_architecture_gates.py"), "--gate", "rls",
         "--runtime-role", "veyro_runtime"],
        capture_output=True, text=True, check=False,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert res.returncode == 2, res.stdout + res.stderr
    assert "VEYRO_RLS_GATE_DSN is not set" in res.stdout


# --- module-deps gate (TSD §24.1 gate 2) ---------------------------------------
#
# Tests here are written against the CONTRACT dispatched alongside this task (TSD
# §24.1 gate 2 / GOV-01-R04, SCN-MOD001-006/007/095/096), not against
# `tools/validate_architecture_gates.py`'s current contents — at the time this
# section was authored the module had no module-deps symbols at all (only the
# `"module-deps"` name in `DEFERRED_GATES`). The import below is therefore
# best-effort: if the contract's names do not exist yet, every test in this
# section fails individually at call time with a clear NameError, and the
# pre-existing tests above are unaffected (no module-level ImportError is
# allowed to escape and break collection of the rest of this file).

try:
    from validate_architecture_gates import (
        _PREFIX_FLOOR_RE,
        ATTR_CTE,
        ATTR_EXTERNAL,
        ATTR_OWNED,
        ATTR_SYSTEM,
        ATTR_UNATTRIBUTED,
        BIDIRECTIONAL_PAIRS,
        ROOT_IMPORTER,
        SHARED_PACKAGE,
        AttributionOutcome,
        GateInputError,
        ModuleEntry,
        Violation,
        _d74_dedupe_order,
        _dedupe_coverage_violations,
        attribute_table_identifier,
        load_module_manifest,
        parse_module_manifest,
        run_module_deps_gate,
    )
except ImportError:
    pass

# IMPLEMENTED_GATES already exists today (it is `("rls", "permission")` pre-module-deps);
# this import is unconditional, unlike the contract-specific names above.
from validate_architecture_gates import IMPLEMENTED_GATES

# Four TSD §6.3 pinned pairs (normative, not manifest-configurable): the permitted
# synchronous edge is `from_domain -> to_domain`; the reverse edge must stay
# event-driven. Domain codes copied verbatim from TSD_MIRROR.md lines 1521-1570.
_PINNED_PAIRS = (
    ("COM-01", "COM-03"),
    ("REL-01", "DAT-01"),
    ("GRO-01", "ENG-01"),
    ("LIF-01", "GOV-04"),
)


def _md_tree(tmp: Path) -> Path:
    """`<tmp>/app/__init__.py` + `<tmp>/app/modules/__init__.py`, matching the
    contract's own example so the derived modules-root dotted path is
    `app.modules`. Returns the modules dir (`<tmp>/app/modules`)."""
    (tmp / "app").mkdir()
    (tmp / "app" / "__init__.py").write_text('"""app root."""\n')
    modules_dir = tmp / "app" / "modules"
    modules_dir.mkdir()
    (modules_dir / "__init__.py").write_text('"""modules root."""\n')
    return modules_dir


def _md_module(modules_dir: Path, name: str, files: dict) -> None:
    """Create/extend a module directory. A docstring-only `__init__.py` is added
    unless the caller supplies its own, matching rule 8's "lone docstring is not
    substantive" baseline."""
    moddir = modules_dir / name
    moddir.mkdir(parents=True, exist_ok=True)
    merged = {"__init__.py": '"""module."""\n', **files}
    for relpath, content in merged.items():
        p = moddir / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)


def _md_entry(domain, prefixes, interfaces, schemas=None):
    entry = {"domain": domain, "owned_table_prefixes": list(prefixes) if isinstance(
        prefixes, (list, tuple)) else prefixes, "public_interfaces": list(interfaces) if
        isinstance(interfaces, (list, tuple)) else interfaces}
    if schemas is not None:
        entry["owned_schemas"] = list(schemas)
    return entry


def _md_manifest(modules: dict) -> dict:
    return {"version": 1, "modules": modules}


def _md_materialize_interfaces(modules_dir: Path, raw, modules_root: str = "app.modules") -> None:
    """R1-F13 / ADR-011 D2: a declared `public_interfaces` entry must now resolve
    to a real `<path>.py` or `<path>/__init__.py` inside its own module's
    directory. The fixtures in this module were written when existence was
    unchecked, so most declare `app.modules.<name>.interface` without their
    `build` callable ever creating that file. This creates *exactly* the declared
    paths and nothing else, as **empty** modules: empty keeps the file
    non-substantive (so no fixture's substantive/vacuous determination changes)
    *and* contributes no docstring position, so the D6.4 docstring-exclusion
    counts the F10 family asserts are untouched as well. Only the file-existence
    precondition each fixture always intended changes. A fixture that means to
    exercise a *missing* or otherwise invalid interface opts out with
    `materialize_interfaces=False`.

    Deliberately tolerant of malformed input: many callers hand this a manifest
    that is invalid on purpose, and the schema violation they are asserting must
    still be the one the gate reports."""
    if not isinstance(raw, dict) or not isinstance(raw.get("modules"), dict):
        return
    for name, entry in raw["modules"].items():
        if not isinstance(name, str) or not isinstance(entry, dict):
            continue
        moddir = modules_dir / name
        if not moddir.is_dir():
            continue  # D5.6: a declared-but-absent module's interfaces stay unverified
        prefix = f"{modules_root}.{name}."
        ifaces = entry.get("public_interfaces")
        for iface in ifaces if isinstance(ifaces, list) else ():
            if not isinstance(iface, str) or not iface.startswith(prefix):
                continue
            parts = iface[len(prefix):].split(".")
            if not all(part.isidentifier() for part in parts):
                continue
            target = moddir.joinpath(*parts[:-1]) / f"{parts[-1]}.py"
            pkg_init = moddir.joinpath(*parts) / "__init__.py"
            if target.exists() or pkg_init.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("")


def _md_write_manifest(modules_dir: Path, manifest_path: Path, modules: dict) -> dict:
    """Write a manifest for an inline (non-`_md_run`) fixture tree and satisfy
    R1-F13's interface-existence precondition for it in one step, so such a tree
    gets exactly the treatment `_md_run` gives — see
    `_md_materialize_interfaces`."""
    raw = _md_manifest(modules)
    _md_materialize_interfaces(modules_dir, raw)
    manifest_path.write_text(json.dumps(raw))
    return raw


def _md_run(modules, build, manifest=None, write_manifest=True,
            materialize_interfaces=True):
    """`build(modules_dir)` populates module source trees under a fresh
    `app/modules` scaffold; `modules` is the manifest's `modules` mapping (ignored
    if `manifest` is supplied verbatim, e.g. to exercise a malformed top level)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        modules_dir = _md_tree(root)
        build(modules_dir)
        manifest_path = root / "module-manifest.json"
        raw = manifest if manifest is not None else _md_manifest(modules)
        if materialize_interfaces:
            _md_materialize_interfaces(modules_dir, raw)
        if write_manifest:
            manifest_path.write_text(json.dumps(raw))
        return run_module_deps_gate(modules_dir, manifest_path)


def _md_base_modules():
    return {"membership": _md_entry("MEM-01", ["membership_"],
                                    ["app.modules.membership.interface"])}


def _md_base_build(modules_dir):
    _md_module(modules_dir, "membership", {
        "service.py": "from app.modules.membership.models import Member\n",
        "models.py": "class Member:\n    pass\n",
    })


def _assert_md_input_error(report, label):
    assert report.status == ERROR, (label, report.render())
    assert report.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, (label, report.render())


def test_module_deps_contract_constants_shape():
    assert SHARED_PACKAGE == "_shared"
    assert len(BIDIRECTIONAL_PAIRS) == 4
    assert isinstance(ModuleEntry, type)
    assert callable(parse_module_manifest)
    assert callable(run_module_deps_gate)
    assert "module-deps" in IMPLEMENTED_GATES
    assert "module-deps" not in DEFERRED_GATES


def test_scn006_own_schema_and_approved_interface_pass():
    def build(modules_dir):
        _md_module(modules_dir, "membership", {
            "service.py": (
                "from app.modules.membership.models import Member\n"
                "from app.modules.billing.interface import preview_charge\n"
                "\n\n"
                "def summarize(member):\n"
                "    preview_charge(member)\n"
                "    return member\n"
            ),
            "models.py": "class Member:\n    pass\n",
            "repo.sql": "SELECT id FROM membership_roster WHERE active = true\n",
        })
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge(member):\n    return None\n",
            "models.py": "class Invoice:\n    pass\n",
        })

    modules = {
        "membership": _md_entry("MEM-01", ["membership_"],
                                ["app.modules.membership.interface"]),
        "billing": _md_entry("BIL-02", ["billing_"], ["app.modules.billing.interface"]),
    }
    report = _md_run(modules, build)
    assert report.status == PASS, report.render()
    assert report.checked


def test_scn007_cross_domain_raw_import_fails_citing_both_modules():
    def build(modules_dir):
        _md_module(modules_dir, "membership", {
            "service.py": "from app.modules.billing.models import Invoice\n",
            "reporting.sql": "SELECT total FROM billing_invoice WHERE paid = true\n",
        })
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge(member):\n    return None\n",
            "models.py": "class Invoice:\n    pass\n",
        })

    modules = {
        "membership": _md_entry("MEM-01", ["membership_"],
                                ["app.modules.membership.interface"]),
        "billing": _md_entry("BIL-02", ["billing_"], ["app.modules.billing.interface"]),
    }
    report = _md_run(modules, build)
    assert report.status == FAIL, report.render()
    assert report.exit_code == 1
    cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    assert len(cross) >= 2, report.render()  # one for the raw import, one for the raw SQL
    for v in cross:
        blob = f"{v.subject} {v.detail}"
        assert "membership" in blob and "billing" in blob, v


def test_scn007_raw_table_reference_is_denied_cross_domain_and_clean_for_own_table():
    """SCN-MOD001-007's raw-table half on its own, as a matched negative/positive pair
    over one fixture shape. The test above bundles a raw Python import with a raw SQL
    reference and asserts only that at least two findings mention both module names,
    so it cannot distinguish a correct table attribution from an import finding whose
    text happens to name the same two modules. Here the only cross-module signal in
    the tree is the table identifier itself: `membership` owns `mem_`, `billing` owns
    `bil_`, and no file imports across the boundary.

    Negative: `SELECT id FROM bil_invoices` inside `membership` is ADR-011 D3.2 state 2
    (owned by a module other than the importer) and must be exactly one FAIL
    `CROSS_DOMAIN_SQL_IMPORT` whose subject and detail name the importer (`membership`,
    via the cited path) and the owner (`billing`).

    Positive: the same statement against `mem_roster` is state 1 (owned by the
    importer) and must be clean -- so the denial comes from attribution, not from
    merely reading a raw `.sql` file."""
    modules = {
        "membership": _md_entry("MEM-01", ["mem_"], ["app.modules.membership.interface"]),
        "billing": _md_entry("BIL-02", ["bil_"], ["app.modules.billing.interface"]),
    }

    def _build(sql):
        def build(modules_dir):
            _md_module(modules_dir, "membership", {
                "service.py": "from app.modules.membership.models import Member\n",
                "models.py": "class Member:\n    pass\n",
                "repo.sql": sql,
            })
            _md_module(modules_dir, "billing", {
                "interface.py": "def preview_charge(member):\n    return None\n",
                "models.py": "class Invoice:\n    pass\n",
            })

        return build

    cross = _md_run(modules, _build("SELECT id FROM bil_invoices\n"))
    assert cross.status == FAIL, cross.render()
    assert cross.exit_code == 1, cross.render()
    assert cross.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, cross.render()
    assert len(cross.violations) == 1, cross.render()
    v = cross.violations[0]
    assert v.subject == "membership -> billing", v
    assert v.detail.startswith("membership/repo.sql:"), v
    assert "'bil_invoices'" in v.detail, v
    assert "owned by 'billing'" in v.detail, v

    own = _md_run(modules, _build("SELECT id FROM mem_roster\n"))
    assert own.status == PASS, own.render()
    assert own.exit_code == 0, own.render()
    assert own.codes() == set(), own.render()
    assert "membership/repo.sql" in own.checked, own.checked


# --- ADR-011 addendum D6.7, bounded first increment -------------------------------
#
# GATE2-R2-N01-D6.7-FROM-LIST-FIRST-SUBCASE-2026-10-06: before this increment,
# `_extract_table_identifiers` took one identifier per `FROM`/`JOIN`/`INTO`/
# `UPDATE`/`TABLE` keyword match, so `SELECT a FROM mem_roster, bil_invoices`
# extracted only `mem_roster` -- the first, clean, same-module element -- and the
# second, cross-domain element was never attributed at all. Because the D6.3 I-1
# backstop fires only when NOTHING extracts (`if not idents:`), that one clean
# extraction silently disarmed the refusal that would otherwise have covered the
# whole statement (qualified root-cause record
# `knowledge/03-Modules/MOD-001/evidence/implementation/
# GATE2-R2-N01-N02-QUALIFIED-ROOT-CAUSE-2026-10-06.md` §3.2/§5.1 row N1).
#
# This increment implements ONLY the `FROM`-list comma-continuation subcase (the
# first of D6.7's per-position corpus) and its non-vacuity positive control (row
# P2). The rest of the bounded record's §5 corpus -- JOIN/INTO/UPDATE/TABLE list
# continuation, USING/REFERENCES/ONLY, aliasing, and the mutation set M-E1..M-E7
# in full -- remains pending and is NOT asserted here.

def test_gate2_d6_7_n1_from_list_comma_continuation_cross_domain_py_literal():
    """§5.1 row N1, `.py` string-literal path: `SELECT a FROM mem_roster,
    bil_invoices`. `mem_roster` (own, D3.2 state 1) is the clean first list
    element; `bil_invoices` (another module's table, D3.2 state 2) is the second.
    The fix must attribute BOTH independently, so the second element's
    CROSS_DOMAIN_SQL_IMPORT is never disarmed by the first element's clean
    outcome -- asserted both as the outward verdict and, via `_f12b_counts`, as
    the own/other count split, so a fix that merely swapped which single
    identifier it extracts could not pass this test by accident."""
    report = _f12b_run({"service.py": 'Q = "SELECT a FROM mem_roster, bil_invoices"\n'})
    assert report.status == FAIL, report.render()
    assert report.exit_code == 1, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    assert len(cross) == 1, report.render()
    assert cross[0].subject == "membership -> billing", cross[0]
    assert "'bil_invoices'" in cross[0].detail, cross[0]
    counts = _f12b_counts(report)
    assert counts["own"] == 1, counts        # mem_roster: the clean first element
    assert counts["other"] == 1, counts      # bil_invoices: not disarmed by the first


def test_gate2_d6_7_n1_from_list_comma_continuation_cross_domain_sql_file():
    """§5.1 row N1, `.sql` file path -- the identical fixture and assertions as
    the `.py` literal test above, so the fix is pinned through both source
    shapes the gate scans, not merely the AST-string-literal one."""
    report = _f12b_run({"query.sql": "SELECT a FROM mem_roster, bil_invoices\n"})
    assert report.status == FAIL, report.render()
    assert report.exit_code == 1, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    assert len(cross) == 1, report.render()
    assert cross[0].subject == "membership -> billing", cross[0]
    assert "'bil_invoices'" in cross[0].detail, cross[0]
    assert "membership/query.sql" in report.checked, report.checked
    counts = _f12b_counts(report)
    assert counts["own"] == 1, counts
    assert counts["other"] == 1, counts


def test_gate2_d6_7_p2_same_module_from_list_comma_stays_clean_py_literal():
    """§5.1 row P2, `.py` string-literal path -- the non-vacuity discriminator:
    `SELECT a FROM mem_roster, mem_events` is a same-module comma list and must
    stay PASS exit 0. A fix that ERRORs or FAILs on every multi-element FROM list
    (e.g. a blanket refusal instead of per-element attribution) would satisfy N1
    above and fail this one -- the pair together is what proves the fix is
    attribution-based, not a wider trigger."""
    report = _f12b_run({"service.py": 'Q = "SELECT a FROM mem_roster, mem_events"\n'})
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    assert report.violations == [], report.render()
    counts = _f12b_counts(report)
    assert counts["own"] == 2, counts
    assert counts["other"] == 0, counts


def test_gate2_d6_7_p2_same_module_from_list_comma_stays_clean_sql_file():
    """§5.1 row P2, `.sql` file path -- the identical fixture and assertions as
    the `.py` literal test above."""
    report = _f12b_run({"query.sql": "SELECT a FROM mem_roster, mem_events\n"})
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    assert report.violations == [], report.render()
    assert "membership/query.sql" in report.checked, report.checked
    counts = _f12b_counts(report)
    assert counts["own"] == 2, counts
    assert counts["other"] == 0, counts


def test_gate2_d6_7_from_list_extraction_mutation_control_both_elements_lexed():
    """Targeted mutation/invariant control for this increment (in the same
    documented-drill convention as the other hand-verified mutants in this
    file, e.g. the value-vs-identity mutant noted at
    `test_f10_identical_text_in_a_non_leading_string_statement_still_fails`):
    a white-box pin directly on `_extract_table_identifiers`, independent of
    the gate's verdict plumbing, so a regression is caught at the layer it was
    introduced in even if some other layer's behaviour happened to mask it.

    The mutant this kills: reverting `_identifier_after_from_keyword`'s
    comma-continuation walk to stop after the first list element (i.e.
    restoring the pre-increment one-identifier-per-`FROM`-match behaviour).
    Manually applying that mutant and re-running this test was verified by
    hand to fail -- `_extract_table_identifiers` then returns only
    `['mem_roster']`, not both elements -- before being reverted; see the
    evidence record's mutation-drill section. This is the ADR-011 D6.7.1
    monotone-bias property made executable: narrowing the extractor's walk is
    never a free optimisation, and this test is what would catch doing so by
    accident."""
    from validate_architecture_gates import _extract_table_identifiers
    idents = _extract_table_identifiers("SELECT a FROM mem_roster, bil_invoices")
    assert idents == ["mem_roster", "bil_invoices"], idents
    # Three elements, so a mutant that only widens the walk by exactly one
    # position (rather than truly looping) is also caught.
    three = _extract_table_identifiers("SELECT a FROM mem_roster, bil_invoices, mem_events")
    assert three == ["mem_roster", "bil_invoices", "mem_events"], three


# --- ADR-011 addendum D6.7.2, bounded second increment: REFERENCES signal ---------
#
# GATE2-R2-N01-D6.7-REFERENCES-SIGNAL-2026-10-06: before this increment,
# `CREATE TABLE mem_t (c int REFERENCES bil_invoices)` extracted only `mem_t`
# (via the `TABLE` keyword) -- `REFERENCES` is a `_TABLE_POSITION_KEYWORDS`
# member but was absent from both `_extract_table_identifiers` and
# `_dangling_keywords`, so the `bil_invoices` cross-domain target was never
# examined at all. Because `idents` was non-empty (`mem_t` extracted cleanly),
# neither the per-element attribution loop nor the `if not idents:` I-1
# backstop ever looked at the REFERENCES target -- reproduced live before this
# fix: `_extract_table_identifiers("CREATE TABLE mem_t (c int REFERENCES "
# "bil_invoices)")` returned `['mem_t']` only, and the full fixture below
# reported PASS exit 0 with `other == 0` -- the §5.1 row N3 false clean named
# in the qualified root-cause record. This increment implements ONLY the
# REFERENCES signal (row N3) and pins the P4 `JOIN ... USING (id)` non-vacuity
# control; N4 `DELETE ... USING`, ONLY, the remaining N/mutation corpus, and
# D8 truthfulness all remain pending and are NOT asserted here.
#
# N4 is implemented and asserted separately below
# (GATE2-R04-GATE2-R2-N01-D67-SHARED-SIGNAL-ACCOUNTING-N4): REFERENCES above
# was refactored onto a shared single-identifier signal-source seam so USING
# could join it without a third hand-duplicated copy. ONLY, the remaining
# N/mutation corpus, and D8 truthfulness remain pending and are NOT asserted
# here or below.

def test_gate2_d6_7_n3_references_signal_cross_domain_py_literal():
    """§5.1 row N3, `.py` string-literal path: `CREATE TABLE mem_t (c int
    REFERENCES bil_invoices)`. `mem_t` (own, D3.2 state 1) is the clean
    `TABLE`-position identifier; `bil_invoices` (another module's table, D3.2
    state 2) is the REFERENCES target. The fix must attribute the REFERENCES
    target independently of `mem_t`'s clean outcome, so the cross-domain
    reference is never disarmed by the statement's own table name extracting
    cleanly -- asserted both as the outward verdict and, via `_f12b_counts`,
    as the own/other count split."""
    report = _f12b_run({
        "service.py": 'Q = "CREATE TABLE mem_t (c int REFERENCES bil_invoices)"\n',
    })
    assert report.status == FAIL, report.render()
    assert report.exit_code == 1, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    assert len(cross) == 1, report.render()
    assert cross[0].subject == "membership -> billing", cross[0]
    assert "'bil_invoices'" in cross[0].detail, cross[0]
    counts = _f12b_counts(report)
    assert counts["own"] == 1, counts        # mem_t: the clean TABLE-position identifier
    assert counts["other"] == 1, counts      # bil_invoices: not disarmed by mem_t


def test_gate2_d6_7_n3_references_signal_cross_domain_sql_file():
    """§5.1 row N3, `.sql` file path -- the identical fixture and assertions as
    the `.py` literal test above, so the fix is pinned through both source
    shapes the gate scans, not merely the AST-string-literal one."""
    report = _f12b_run({
        "query.sql": "CREATE TABLE mem_t (c int REFERENCES bil_invoices)\n",
    })
    assert report.status == FAIL, report.render()
    assert report.exit_code == 1, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    assert len(cross) == 1, report.render()
    assert cross[0].subject == "membership -> billing", cross[0]
    assert "'bil_invoices'" in cross[0].detail, cross[0]
    assert "membership/query.sql" in report.checked, report.checked
    counts = _f12b_counts(report)
    assert counts["own"] == 1, counts
    assert counts["other"] == 1, counts


def test_gate2_d6_7_p4_join_using_column_list_stays_clean_py_literal():
    """§5.1 row P4, `.py` string-literal path -- the non-vacuity discriminator
    D6.7.4's REFERENCES addition must not break: `SELECT a FROM mem_x JOIN
    mem_y USING (id)` is a join-condition column list, not a table position,
    and must stay PASS exit 0. This is the one real false-positive hazard a
    REFERENCES/USING-adjacent signal addition creates; pinning it here is what
    proves the REFERENCES seam did not also start treating `USING (col)` as a
    table-position signal."""
    report = _f12b_run({
        "service.py": 'Q = "SELECT a FROM mem_x JOIN mem_y USING (id)"\n',
    })
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    assert report.violations == [], report.render()
    counts = _f12b_counts(report)
    assert counts["own"] == 2, counts
    assert counts["other"] == 0, counts


def test_gate2_d6_7_p4_join_using_column_list_stays_clean_sql_file():
    """§5.1 row P4, `.sql` file path -- the identical fixture and assertions as
    the `.py` literal test above."""
    report = _f12b_run({
        "query.sql": "SELECT a FROM mem_x JOIN mem_y USING (id)\n",
    })
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    assert report.violations == [], report.render()
    assert "membership/query.sql" in report.checked, report.checked
    counts = _f12b_counts(report)
    assert counts["own"] == 2, counts
    assert counts["other"] == 0, counts


def test_gate2_d6_7_references_signal_mutation_control_not_silently_accounted():
    """Targeted mutation/invariant control for this increment, in the same
    white-box convention as
    `test_gate2_d6_7_from_list_extraction_mutation_control_both_elements_lexed`:
    a pin directly on `_extract_table_identifiers`/`_dangling_keywords`,
    independent of the gate's verdict plumbing.

    The mutant this kills: removing `_REFERENCES_KEYWORD_RE`'s loop from
    `_extract_table_identifiers` while leaving `_dangling_keywords`'s own
    REFERENCES loop in place. Manually applying that mutant and re-running
    this test was verified by hand to fail: `_extract_table_identifiers`
    then returns `['mem_t']` only (the N3 false clean this increment fixes),
    while `_dangling_keywords` still correctly reports `False` for the same
    text -- because `bil_invoices` genuinely does lex to a well-formed
    identifier, the dangling check has nothing to flag. That combination is
    exactly 'falsely marking the REFERENCES signal accounted without
    attribution': the signal is not dangling (so no ERROR fires) and yet its
    identifier never reaches D3.2 attribution (so no FAIL fires either) --
    the gate would report PASS. This is the ADR-011 D6.7.2 per-position
    accounting invariant made executable: a signal's dangling status and its
    presence in the attributed-identifier list must never be allowed to
    disagree."""
    from validate_architecture_gates import (
        _dangling_keywords,
        _extract_table_identifiers,
    )
    n3 = "CREATE TABLE mem_t (c int REFERENCES bil_invoices)"
    idents = _extract_table_identifiers(n3)
    assert idents == ["mem_t", "bil_invoices"], idents
    assert _dangling_keywords(n3) is False, n3
    # The complementary direction: a REFERENCES signal with no well-formed
    # identifier after it must be dangling (fail closed), never silently
    # treated as accounted just because some other identifier in the same
    # statement extracted cleanly.
    dangling_ref = "ALTER foo ADD CONSTRAINT fk REFERENCES \n"
    assert _extract_table_identifiers(dangling_ref) == [], dangling_ref
    assert _dangling_keywords(dangling_ref) is True, dangling_ref


# --- ADR-011 addendum D6.7.2, bounded third increment: context-sensitive USING ---
#
# GATE2-R04-GATE2-R2-N01-D67-SHARED-SIGNAL-ACCOUNTING-N4: before this increment,
# `DELETE FROM mem_t USING bil_invoices WHERE ...` extracted only `mem_t` (via the
# `FROM` keyword) -- `USING` was not a signal source for either
# `_extract_table_identifiers` or `_dangling_keywords`, so the `bil_invoices`
# cross-domain DELETE target was never examined at all, reproduced live before
# this fix: `_extract_table_identifiers` returned `['mem_t']` only and the full
# fixture below reported PASS exit 0 with `other == 0` -- the same
# partial-extraction-disarms-accounting shape as row N3, named as row N4 in the
# qualified root-cause record and confirmed still live by the N4 strategy
# reconciliation record
# (`GATE2-R2-N01-D67-N4-STRATEGY-RECONCILIATION-2026-10-06.md`). This increment
# implements ONLY the context-sensitive USING signal (row N4, the single-target
# `DELETE ... USING <table>` shape) on the shared
# `_SINGLE_IDENTIFIER_SIGNAL_SOURCES` seam REFERENCES was refactored onto, and
# re-pins the P4 `JOIN ... USING (id)` non-vacuity control (unaffected, since a
# `USING` immediately followed by `(` is excluded from the signal source itself,
# never reaching `_identifier_after_keyword`). ONLY, the remaining N/mutation
# corpus, and D8 truthfulness all remain pending and are NOT asserted here.

def test_gate2_d6_7_n4_using_signal_cross_domain_py_literal():
    """Row N4, `.py` string-literal path: `DELETE FROM mem_t USING bil_invoices
    WHERE mem_t.id = bil_invoices.mem_id`. `mem_t` (own, D3.2 state 1) is the
    clean `FROM`-position identifier; `bil_invoices` (another module's table,
    D3.2 state 2) is the `USING` target. The fix must attribute the USING
    target independently of `mem_t`'s clean outcome, so the cross-domain
    reference is never disarmed by the statement's own table name extracting
    cleanly -- asserted both as the outward verdict and, via `_f12b_counts`, as
    the own/other count split."""
    report = _f12b_run({
        "service.py": (
            'Q = "DELETE FROM mem_t USING bil_invoices '
            'WHERE mem_t.id = bil_invoices.mem_id"\n'
        ),
    })
    assert report.status == FAIL, report.render()
    assert report.exit_code == 1, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    assert len(cross) == 1, report.render()
    assert cross[0].subject == "membership -> billing", cross[0]
    assert "'bil_invoices'" in cross[0].detail, cross[0]
    counts = _f12b_counts(report)
    assert counts["own"] == 1, counts        # mem_t: the clean FROM-position identifier
    assert counts["other"] == 1, counts      # bil_invoices: not disarmed by mem_t


def test_gate2_d6_7_n4_using_signal_cross_domain_sql_file():
    """Row N4, `.sql` file path -- the identical fixture and assertions as the
    `.py` literal test above, so the fix is pinned through both source shapes
    the gate scans, not merely the AST-string-literal one."""
    report = _f12b_run({
        "query.sql": (
            "DELETE FROM mem_t USING bil_invoices "
            "WHERE mem_t.id = bil_invoices.mem_id\n"
        ),
    })
    assert report.status == FAIL, report.render()
    assert report.exit_code == 1, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    assert len(cross) == 1, report.render()
    assert cross[0].subject == "membership -> billing", cross[0]
    assert "'bil_invoices'" in cross[0].detail, cross[0]
    assert "membership/query.sql" in report.checked, report.checked
    counts = _f12b_counts(report)
    assert counts["own"] == 1, counts
    assert counts["other"] == 1, counts


def test_gate2_d6_7_p4_join_using_column_list_still_stays_clean_after_n4():
    """Re-pin of row P4 after the N4 USING signal landed, directly against the
    extraction/dangling helpers rather than only the report-level test above:
    `JOIN mem_x USING (id)`'s `USING` must never become a signal at all -- it
    is excluded by `_using_table_position_matches` before either consumer
    looks at it, so adding the context-sensitive USING signal source must not
    resurrect the false-positive hazard a context-free USING addition would
    have created."""
    from validate_architecture_gates import (
        _dangling_keywords,
        _extract_table_identifiers,
    )
    p4 = "SELECT a FROM mem_x JOIN mem_y USING (id)"
    assert _extract_table_identifiers(p4) == ["mem_x", "mem_y"], p4
    assert _dangling_keywords(p4) is False, p4


def test_gate2_d6_7_using_signal_mutation_control_dropped_signal_not_silently_accounted():
    """Targeted mutation/invariant control for this increment, in the same
    white-box convention as
    `test_gate2_d6_7_references_signal_mutation_control_not_silently_accounted`:
    a pin directly on `_extract_table_identifiers`/`_dangling_keywords`,
    independent of the gate's verdict plumbing.

    The mutant this kills: dropping `_using_table_position_matches` from
    `_TABLE_POSITION_SIGNAL_SOURCES` (equivalently: removing USING's signal
    from `_extract_table_identifiers` while leaving it in `_dangling_keywords`,
    or vice versa). Manually applying the "drop from the shared tuple" mutant
    and re-running this test was verified by hand to fail:
    `_extract_table_identifiers` then returns `['mem_t']` only (the N4 false
    clean this increment fixes) and `_dangling_keywords` returns `False` for
    the same text (since `bil_invoices` genuinely lexes to a well-formed
    identifier, so there is nothing for a dropped-and-therefore-silent signal
    to flag) -- the gate would report PASS. Because both consumers walk the
    same `_TABLE_POSITION_SIGNAL_SOURCES` tuple, a mutant that drops the
    USING source necessarily drops it from both at once, so this one
    assertion pair is sufficient to catch either direction of accounting
    drift, not just a hand-duplicated-copy divergence between two
    independent call sites.

    The tuple this asserts membership in was renamed from
    `_SINGLE_IDENTIFIER_SIGNAL_SOURCES` by
    GATE2-R04-GATE2-R2-N01-D67-SHARED-LIST-WALK-JOIN-USING, which moved USING
    onto the shared list walk -- so the tuple is no longer
    single-identifier-only. What this test pins is unchanged: that USING is a
    recognised signal source at all, seen identically by both consumers."""
    from validate_architecture_gates import (
        _TABLE_POSITION_SIGNAL_SOURCES,
        _dangling_keywords,
        _extract_table_identifiers,
        _using_table_position_matches,
    )
    assert _using_table_position_matches in _TABLE_POSITION_SIGNAL_SOURCES
    n4 = "DELETE FROM mem_t USING bil_invoices WHERE mem_t.id = bil_invoices.mem_id"
    idents = _extract_table_identifiers(n4)
    assert idents == ["mem_t", "bil_invoices"], idents
    assert _dangling_keywords(n4) is False, n4
    # The complementary direction: a USING signal with no well-formed identifier
    # after it must be dangling (fail closed), never silently treated as
    # accounted just because some other identifier in the same statement
    # extracted cleanly.
    dangling_using = "DELETE FROM mem_t USING \n"
    assert _extract_table_identifiers(dangling_using) == ["mem_t"], dangling_using
    assert _dangling_keywords(dangling_using) is True, dangling_using


# --- ADR-011 addendum D6.7.2: the explicit per-position result stream ------------
#
# GATE2-R04-GATE2-R2-N01-D67-EXPLICIT-POSITION-RESULT-CORE-ALIAS-LISTS. The three
# increments above each closed one signal, but the accounting *seam* was still the
# aggregate one the round-2 P0 was found in: extraction returned a `list[str]` plus
# a statement-wide dangling boolean, and `_scan_sql_statement` asked the
# statement-level question `if not idents:`. That question cannot prove every
# recognised position was accounted -- it is answered "an identifier extracted, so
# nothing is unaccounted" by a statement where one position lexed cleanly and
# another was never resolved. Reproduced live before this increment
# (`GATE2-R2-N01-D67-POSITION-ACCOUNTING-ROOT-CAUSE-2026-10-06.md` §2, run through
# the real gate report): `SELECT a FROM mem_roster m, bil_invoices b` and the `AS`
# form both reached **PASS exit 0** with `own=1 other=0` -- the cross-domain second
# element lost behind the first element's alias -- while the D8 note simultaneously
# claimed its counts were complete.
#
# This increment replaces that seam with `_table_position_results`: one record per
# recognised table position, each carrying either an identifier for D3.2
# attribution or an unresolved reason, and the scanner walks those records rather
# than a separately-built identifier list. Rows N8/N9 (the FROM comma continuation
# after a bare alias and after an `AS` alias) are the first list forms covered.
# D6.7.3's remaining list forms (JOIN/INTO/UPDATE/TABLE/USING/REFERENCES/ONLY
# continuation), correct `ONLY` attribution, the full N1-N10/P1-P5/M-E1-M-E7
# corpus, and D8's lower-bound-vs-complete wording all remain pending and are NOT
# asserted here.

def test_gate2_d6_7_n8_from_list_bare_alias_cross_domain_py_literal():
    """Row N8, `.py` string-literal path: `SELECT a FROM mem_roster m,
    bil_invoices b`. `mem_roster` (own, D3.2 state 1) is the clean first element
    and `bil_invoices` (another module's table, D3.2 state 2) is the second, each
    carrying a bare alias. The per-position stream must recognise and attribute
    both, so the second element's CROSS_DOMAIN_SQL_IMPORT is never disarmed by the
    first element's clean outcome -- asserted as the outward verdict and, via
    `_f12b_counts`, as the own/other split, so a fix that merely swapped which
    single identifier it extracts could not pass by accident."""
    report = _f12b_run({
        "service.py": 'Q = "SELECT a FROM mem_roster m, bil_invoices b"\n',
    })
    assert report.status == FAIL, report.render()
    assert report.exit_code == 1, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    assert len(cross) == 1, report.render()
    assert cross[0].subject == "membership -> billing", cross[0]
    assert "'bil_invoices'" in cross[0].detail, cross[0]
    counts = _f12b_counts(report)
    assert counts["own"] == 1, counts        # mem_roster: the clean first element
    assert counts["other"] == 1, counts      # bil_invoices: not lost behind `m`


def test_gate2_d6_7_n8_from_list_bare_alias_cross_domain_sql_file():
    """Row N8, `.sql` file path -- the identical fixture and assertions as the
    `.py` literal test above, so the fix is pinned through both source shapes the
    gate scans, not merely the AST-string-literal one."""
    report = _f12b_run({"query.sql": "SELECT a FROM mem_roster m, bil_invoices b\n"})
    assert report.status == FAIL, report.render()
    assert report.exit_code == 1, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    assert len(cross) == 1, report.render()
    assert cross[0].subject == "membership -> billing", cross[0]
    assert "'bil_invoices'" in cross[0].detail, cross[0]
    assert "membership/query.sql" in report.checked, report.checked
    counts = _f12b_counts(report)
    assert counts["own"] == 1, counts
    assert counts["other"] == 1, counts


def test_gate2_d6_7_n9_from_list_as_alias_cross_domain_py_literal():
    """Row N9, `.py` string-literal path: the `AS`-alias form of N8, `SELECT a
    FROM mem_roster AS m, bil_invoices AS b`. Asserted separately from the bare
    form because the two reach the continuation by different branches of
    `_skip_list_element_alias` -- a fix covering only the bare form would leave
    this row at the PASS exit 0 the root-cause record reproduced."""
    report = _f12b_run({
        "service.py": 'Q = "SELECT a FROM mem_roster AS m, bil_invoices AS b"\n',
    })
    assert report.status == FAIL, report.render()
    assert report.exit_code == 1, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    assert len(cross) == 1, report.render()
    assert cross[0].subject == "membership -> billing", cross[0]
    assert "'bil_invoices'" in cross[0].detail, cross[0]
    counts = _f12b_counts(report)
    assert counts["own"] == 1, counts
    assert counts["other"] == 1, counts


def test_gate2_d6_7_n9_from_list_as_alias_cross_domain_sql_file():
    """Row N9, `.sql` file path -- the identical fixture and assertions as the
    `.py` literal test above."""
    report = _f12b_run({
        "query.sql": "SELECT a FROM mem_roster AS m, bil_invoices AS b\n",
    })
    assert report.status == FAIL, report.render()
    assert report.exit_code == 1, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    assert len(cross) == 1, report.render()
    assert cross[0].subject == "membership -> billing", cross[0]
    assert "'bil_invoices'" in cross[0].detail, cross[0]
    assert "membership/query.sql" in report.checked, report.checked
    counts = _f12b_counts(report)
    assert counts["own"] == 1, counts
    assert counts["other"] == 1, counts


def test_gate2_d6_7_own_table_aliased_from_list_stays_clean():
    """The non-vacuity discriminator for N8/N9, through both source shapes: a
    same-module aliased comma list must stay PASS exit 0, in both the bare and
    `AS` forms, with *both* elements counted at D3.2 state 1. A fix that refused
    every aliased list -- or one that reached the second element but could not
    attribute it -- would satisfy N8/N9 above and fail here; the pair together is
    what proves the fix is per-position attribution rather than a wider
    refusal."""
    for sql in ("SELECT a FROM mem_roster m, mem_events e",
                "SELECT a FROM mem_roster AS m, mem_events AS e"):
        for files in ({"service.py": f'Q = "{sql}"\n'}, {"query.sql": f"{sql}\n"}):
            report = _f12b_run(files)
            assert report.status == PASS, (sql, files, report.render())
            assert report.exit_code == 0, (sql, report.render())
            assert report.violations == [], (sql, report.render())
            counts = _f12b_counts(report)
            assert counts["own"] == 2, (sql, counts)
            assert counts["other"] == 0, (sql, counts)


def test_gate2_d6_7_unresolved_second_position_errors_after_a_clean_first():
    """The D6.7.2 invariant the replaced `if not idents:` guard could not state,
    asserted at the report level through both source shapes: a statement whose
    first table position resolves cleanly and whose second does not is ERROR
    `MODULE_DEPS_SOURCE_UNINSPECTABLE` at exit 2 -- *not* a PASS that silently
    reports only the element that lexed.

    Both fixtures carry a clean own-table first element, so neither can reach the
    refusal via the old statement-level route (`idents` is non-empty for both):
    the trailing-comma case has nothing after the `,` at all, and the subquery
    case has an element the lexer cannot reduce to an identifier (D6.7.3's "an
    element the lexer cannot reduce to an identifier is ERROR, never dropped").
    The refusal must also *name* the unresolved signal, since a refusal that
    cannot say which position went unaccounted is not actionable.

    The mutant this kills: restoring the statement-level guard, i.e. refusing
    only when *nothing* in the statement resolved (`if unresolved and not
    any(p.identifier for p in positions):`) -- the partial-extraction-disarms-
    accounting defect itself. Verified by hand to fail."""
    for sql in ("SELECT a FROM mem_roster m, ",
                "SELECT a FROM mem_roster m, (SELECT 1) s"):
        for files in ({"service.py": f'Q = "{sql}"\n'}, {"query.sql": f"{sql}\n"}):
            report = _f12b_run(files)
            assert report.status == ERROR, (sql, files, report.render())
            assert report.exit_code == 2, (sql, report.render())
            assert "MODULE_DEPS_SOURCE_UNINSPECTABLE" in report.codes(), (
                sql, report.render())
            named = [v for v in report.violations
                     if v.code == "MODULE_DEPS_SOURCE_UNINSPECTABLE"
                     and "FROM signal at offset" in v.detail]
            assert len(named) == 1, (sql, report.render())


def test_gate2_d6_7_position_stream_mutation_control_every_position_accounted():
    """Targeted mutation/invariant control for this increment, in the same
    white-box convention as the other hand-verified mutants in this file (e.g.
    `test_gate2_d6_7_using_signal_mutation_control_dropped_signal_not_silently_accounted`):
    a pin directly on `_table_position_results` -- the seam itself -- independent
    of the gate's verdict plumbing, so a regression is caught at the layer it was
    introduced in.

    Three properties, each killing a different mutant:

      * the aliased list yields one record per element. Mutant: dropping the
        `_skip_list_element_alias` step from `_table_list_positions`'s walk (i.e.
        restoring the pre-increment behaviour, where the continuation had to
        follow the element identifier immediately). Verified by hand to fail --
        the stream then holds one record, `mem_roster`, and the whole statement
        is clean.
      * the alias skip must not read an ordinary trailing clause as a list. This
        is the one real false-positive hazard the skip creates: in `FROM mem_t t
        GROUP BY x, y` the words after `mem_t` all lex exactly like bare aliases.
        Mutant: skipping aliases greedily (a `while` loop over
        `_skip_list_element_alias`) instead of one element alias gated on a
        following `,`. Verified by hand to fail -- the walk then steps over `t`,
        `GROUP`, `BY` and `x`, finds the `,` that belongs to the GROUP BY list,
        and extracts the column name `y` as a table position
        (`['mem_t', 'y']`), which under a manifest owning neither would be a
        false ERROR on ordinary SQL. Note the weaker variant -- skipping one
        alias unconditionally rather than gating it on the `,` -- was also run
        and is an *equivalent* mutant, not a surviving one: a single skip that
        is not followed by a `,` ends the walk either way, so it changes no
        output and no test here claims to kill it.
      * a record can never carry neither or both of an identifier and an
        unresolved reason. Mutant: deleting `_TablePositionResult.__post_init__`.
        That invariant is what makes the two derived views
        (`_extract_table_identifiers`/`_dangling_keywords`) exact complements, so
        no position can be simultaneously absent from attribution and absent from
        the refusal -- the accounting hole this increment closed."""
    from validate_architecture_gates import (
        _dangling_keywords,
        _extract_table_identifiers,
        _table_position_results,
        _TablePositionResult,
    )
    for sql in ("SELECT a FROM mem_roster m, bil_invoices b",
                "SELECT a FROM mem_roster AS m, bil_invoices AS b"):
        positions = _table_position_results(sql)
        assert [p.identifier for p in positions] == ["mem_roster", "bil_invoices"], sql
        assert all(p.signal.upper() == "FROM" for p in positions), sql
        assert all(p.unresolved is None for p in positions), sql
        assert _dangling_keywords(sql) is False, sql

    # A three-element aliased list, so a mutant that widens the walk by exactly
    # one position rather than truly looping is caught too.
    three = _table_position_results("SELECT a FROM mem_roster m, bil_invoices b, mem_events e")
    assert [p.identifier for p in three] == ["mem_roster", "bil_invoices", "mem_events"], three

    trailing_clause = "SELECT a FROM mem_t t GROUP BY x, y"
    assert _extract_table_identifiers(trailing_clause) == ["mem_t"], trailing_clause
    assert len(_table_position_results(trailing_clause)) == 1, trailing_clause
    assert _dangling_keywords(trailing_clause) is False, trailing_clause

    # The complementary direction: an unresolved position after a clean one is a
    # record of its own, naming its signal -- never a silently shortened list.
    unresolved = _table_position_results("SELECT a FROM mem_roster m, ")
    assert [p.identifier for p in unresolved] == ["mem_roster", None], unresolved
    assert unresolved[1].unresolved is not None, unresolved
    assert unresolved[1].signal.upper() == "FROM", unresolved
    assert "FROM signal at offset" in unresolved[1].describe(), unresolved[1].describe()

    # Neither-nor and both-at-once are each rejected at construction (same
    # try/except convention as this file's other fail-closed constructor pins,
    # which keeps the direct-run path at the bottom of this file working).
    for identifier, reason in ((None, None), ("mem_roster", "unresolved anyway")):
        try:
            _TablePositionResult("FROM", 14, 19, identifier, reason)
        except ValueError:
            continue
        raise AssertionError(f"accepted {identifier!r}/{reason!r}")


# --- ADR-011 addendum D6.7.3: one shared list walk for FROM, JOIN and USING -----
#
# GATE2-R04-GATE2-R2-N01-D67-SHARED-LIST-WALK-JOIN-USING. The position-result core
# above made the *accounting* per-position, but the comma-continuation walk itself
# was still reachable only from `FROM`: JOIN and the context-sensitive
# table-position USING each contributed exactly one single-identifier position, so
# the second element of their lists was never a recognised position at all and
# therefore could not be unaccounted. Reproduced live against this source
# immediately before this increment (`GATE2-R2-N01-D67-POST-CORE-STAGNATION-
# RECONCILIATION-2026-10-06.md`, and re-run directly by this session):
#
#   SELECT a FROM mem_roster JOIN mem_events, bil_invoices ON 1=1
#   DELETE FROM mem_roster USING mem_events, bil_invoices WHERE 1=1
#
# both reached **PASS exit 0** with `own=2 other=0` -- the billing target absent
# from the stream entirely -- while the identical list under `FROM` was already
# correctly refused. That asymmetry is the point: the defect was in the *reach* of
# one list mechanism, not in two keywords, which is why this increment routes every
# list signal through the single `_table_list_positions` walk via
# `_LIST_POSITION_SIGNALS` rather than adding a JOIN copy and a USING copy of it.
#
# INTO/TABLE/UPDATE/REFERENCES list positions were pending at this block and are
# now covered by the FOUR-SIGNALS block below it. Still pending and NOT asserted
# in either: `ONLY` and bare-verb list positions, correct `ONLY` target
# attribution, the full N1-N10/P1-P5/M-E1-M-E7 corpus, and D6.7.5's
# lower-bound-vs-complete D8 wording.

_D67_SHARED_JOIN_NEGATIVE = "SELECT a FROM mem_roster JOIN mem_events, bil_invoices ON 1=1"
_D67_SHARED_USING_NEGATIVE = (
    "DELETE FROM mem_roster USING mem_events, bil_invoices WHERE 1=1"
)


def _d67_shared_assert_cross_domain_list(sql, files, report):
    """The shared assertion body for the two negatives below: exactly one
    CROSS_DOMAIN_SQL_IMPORT at FAIL exit 1, naming the billing target, with the
    D8 own/other split read out of the report's own disclosure note.

    `own == 2` is what makes this more than a "something failed" assertion: both
    clean own-module positions must still be attributed, so a fix that refused the
    whole statement, or that reached the third element by losing the second, cannot
    satisfy it."""
    assert report.status == FAIL, (sql, files, report.render())
    assert report.exit_code == 1, (sql, report.render())
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, (sql, report.render())
    cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    assert len(cross) == 1, (sql, report.render())
    assert cross[0].subject == "membership -> billing", cross[0]
    assert "'bil_invoices'" in cross[0].detail, cross[0]
    counts = _f12b_counts(report)
    assert counts["own"] == 2, (sql, counts)       # mem_roster + mem_events
    assert counts["other"] == 1, (sql, counts)     # bil_invoices, no longer absent


def test_gate2_d6_7_join_comma_list_cross_domain_py_literal():
    """`JOIN mem_events, bil_invoices`, `.py` string-literal path. The `FROM` and
    first `JOIN` positions both resolve to own-module tables, so this statement
    reached PASS exit 0 before the shared walk: `idents` was non-empty *and* every
    recognised position was accounted -- the second JOIN element simply was not a
    position. It must now be one."""
    report = _f12b_run({"service.py": f'Q = "{_D67_SHARED_JOIN_NEGATIVE}"\n'})
    _d67_shared_assert_cross_domain_list(_D67_SHARED_JOIN_NEGATIVE, "py", report)


def test_gate2_d6_7_join_comma_list_cross_domain_sql_file():
    """`JOIN mem_events, bil_invoices`, real `.sql` fixture file -- the identical
    assertions as the `.py` literal above, so the shared walk is pinned through
    both source shapes the gate scans rather than only the AST one."""
    report = _f12b_run({"query.sql": f"{_D67_SHARED_JOIN_NEGATIVE}\n"})
    _d67_shared_assert_cross_domain_list(_D67_SHARED_JOIN_NEGATIVE, "sql", report)
    assert "membership/query.sql" in report.checked, report.checked


def test_gate2_d6_7_delete_using_comma_list_cross_domain_py_literal():
    """`DELETE ... USING mem_events, bil_invoices`, `.py` string-literal path. The
    second list family, and the reason this increment is one mechanism rather than
    one patch: USING's single-target form was already a recognised signal (row N4),
    so only the *list* reach was missing -- exactly as for JOIN."""
    report = _f12b_run({"service.py": f'Q = "{_D67_SHARED_USING_NEGATIVE}"\n'})
    _d67_shared_assert_cross_domain_list(_D67_SHARED_USING_NEGATIVE, "py", report)


def test_gate2_d6_7_delete_using_comma_list_cross_domain_sql_file():
    """`DELETE ... USING mem_events, bil_invoices`, real `.sql` fixture file --
    identical assertions as the `.py` literal above."""
    report = _f12b_run({"query.sql": f"{_D67_SHARED_USING_NEGATIVE}\n"})
    _d67_shared_assert_cross_domain_list(_D67_SHARED_USING_NEGATIVE, "sql", report)
    assert "membership/query.sql" in report.checked, report.checked


def test_gate2_d6_7_own_table_join_and_using_comma_lists_stay_clean():
    """The non-vacuity discriminator for the two negatives above, through both
    source shapes: a same-module JOIN list and a same-module DELETE USING list
    must stay PASS exit 0 with *every* element counted at D3.2 state 1, and the P4
    control `JOIN ... USING (id)` -- a join-condition column list, never a table
    position -- must stay PASS exit 0 as well.

    P4 is re-pinned here specifically because this increment is the one that makes
    `USING` a list signal: a shared walk that forgot the column-list exclusion
    would now try to walk `(id)` as a list of table positions, which would refuse
    ordinary SQL. The exclusion lives in `_using_table_position_matches`, before
    either consumer or the walk sees the match, so the two cannot drift."""
    cases = [
        ("SELECT a FROM mem_roster JOIN mem_events, mem_dues ON 1=1", 3),
        ("DELETE FROM mem_roster USING mem_events, mem_dues WHERE 1=1", 3),
        ("SELECT a FROM mem_x JOIN mem_y USING (id)", 2),          # row P4
    ]
    for sql, own in cases:
        for files in ({"service.py": f'Q = "{sql}"\n'}, {"query.sql": f"{sql}\n"}):
            report = _f12b_run(files)
            assert report.status == PASS, (sql, files, report.render())
            assert report.exit_code == 0, (sql, report.render())
            assert report.violations == [], (sql, report.render())
            counts = _f12b_counts(report)
            assert counts["own"] == own, (sql, counts)
            assert counts["other"] == 0, (sql, counts)


def test_gate2_d6_7_unresolved_list_element_errors_after_a_clean_join_or_using_position():
    """D6.7.2/D6.7.3 for the two new list families: a clean first JOIN/USING
    position followed by a comma element the lexer cannot reduce to an identifier
    is ERROR `MODULE_DEPS_SOURCE_UNINSPECTABLE` at exit 2, never a PASS that
    silently reports only the elements that lexed.

    Both fixtures carry *two* cleanly-resolved own-module positions ahead of the
    unresolved one, so neither can reach the refusal by the statement-level route
    the position-result core already removed -- and the refusal must name the
    originating signal (`JOIN`/`USING`, with its offset), since a refusal that
    cannot say which position went unaccounted is not actionable. A parenthesised
    subquery element is the chosen shape because it is the one D6.7.3 calls out
    explicitly: unresolved at exit 2 rather than silently dropped."""
    for sql, signal in (
        ("SELECT a FROM mem_roster JOIN mem_events, (SELECT 1) s ON 1=1", "JOIN"),
        ("DELETE FROM mem_roster USING mem_events, (SELECT 1) s WHERE 1=1", "USING"),
    ):
        for files in ({"service.py": f'Q = "{sql}"\n'}, {"query.sql": f"{sql}\n"}):
            report = _f12b_run(files)
            assert report.status == ERROR, (sql, files, report.render())
            assert report.exit_code == 2, (sql, report.render())
            assert "MODULE_DEPS_SOURCE_UNINSPECTABLE" in report.codes(), (
                sql, report.render())
            named = [v for v in report.violations
                     if v.code == "MODULE_DEPS_SOURCE_UNINSPECTABLE"
                     and f"{signal} signal at offset" in v.detail]
            assert len(named) == 1, (sql, report.render())


def test_gate2_d6_7_shared_list_walk_mutation_control_one_mutant_both_families():
    """Targeted mutation/invariant control for this increment, in the same
    white-box convention as the other hand-verified mutants in this file: a pin
    directly on the shared seam rather than on the gate's verdict plumbing.

    The property is that the continuation is *shared*, which is what makes a
    single mutant visible to both list families at once. Two mutants were applied
    by hand to the real source and re-run:

      * `_LIST_POSITION_SIGNALS = frozenset({"FROM"})` -- i.e. taking JOIN and
        USING back off the shared walk, the state this increment started from.
        Verified by hand to fail: the stream then holds `['mem_roster',
        'mem_events']` for *both* fixtures below, the billing element vanishes
        from the stream rather than becoming unresolved, `_dangling_keywords` is
        `False`, and the gate reports PASS exit 0. One edit, both families --
        and the own-table positive above is killed too (its `own` count drops
        from 3 to 2), so the mutant is not merely detected by a negative.
      * deleting the `while` continuation loop from `_table_list_positions`.
        Verified by hand to fail here *and* in the N1/N8/N9 `FROM`-list tests
        above -- the single mechanism cannot be removed for one family only,
        which is the structural property a per-keyword patch would not have.

    The equivalent-mutant note from the position-core control still applies: a
    mutant that merely reorders `_TABLE_POSITION_SIGNAL_SOURCES` changes position
    order but not accounting, and nothing here claims to kill it."""
    from validate_architecture_gates import (
        _LIST_POSITION_SIGNALS,
        _dangling_keywords,
        _extract_table_identifiers,
        _positions_for_signal,
        _table_list_positions,
        _table_position_results,
    )
    # The mechanism is one walk reached through one dispatch, not a copy per
    # keyword. The membership set itself is pinned in the FOUR-SIGNALS control
    # below, which owns the current contents; this assertion only needs the two
    # families this block is about to be on the shared walk.
    assert {"FROM", "JOIN", "USING"} <= _LIST_POSITION_SIGNALS, _LIST_POSITION_SIGNALS
    assert _positions_for_signal.__code__.co_names.count("_table_list_positions") == 1
    assert _table_list_positions is not None

    for sql, signal in ((_D67_SHARED_JOIN_NEGATIVE, "JOIN"),
                        (_D67_SHARED_USING_NEGATIVE, "USING")):
        idents = _extract_table_identifiers(sql)
        assert idents == ["mem_roster", "mem_events", "bil_invoices"], (sql, idents)
        assert _dangling_keywords(sql) is False, sql
        positions = _table_position_results(sql)
        # The continued elements belong to the signal that introduced them, so a
        # refusal can name it -- and the first position is still `FROM`'s, so the
        # walk extended the right list rather than re-reading the statement.
        assert [p.signal.upper() for p in positions] == ["FROM", signal, signal], (
            sql, [p.signal for p in positions])

    # A three-element list, so a mutant that widens the walk by exactly one
    # element rather than genuinely looping is caught for the new families too.
    for sql in ("SELECT a FROM mem_roster JOIN mem_events, bil_invoices, mem_dues ON 1=1",
                "DELETE FROM mem_roster USING mem_events, bil_invoices, mem_dues WHERE 1"):
        assert _extract_table_identifiers(sql) == [
            "mem_roster", "mem_events", "bil_invoices", "mem_dues"], sql

    # The complementary direction for both families: an unresolved continuation
    # element is a record of its own naming its signal, never a shortened list.
    for sql, signal in (
        ("SELECT a FROM mem_roster JOIN mem_events, (SELECT 1) s ON 1=1", "JOIN"),
        ("DELETE FROM mem_roster USING mem_events, (SELECT 1) s WHERE 1=1", "USING"),
    ):
        positions = _table_position_results(sql)
        assert [p.identifier for p in positions] == [
            "mem_roster", "mem_events", None], (sql, positions)
        assert positions[-1].signal.upper() == signal, positions[-1]
        assert f"{signal} signal at offset" in positions[-1].describe(), (
            positions[-1].describe())
        assert _dangling_keywords(sql) is True, sql


# --- ADR-011 addendum D6.7.3: the same shared list walk for INTO/TABLE/UPDATE/
# --- REFERENCES ------------------------------------------------------------------
#
# GATE2-R04-GATE2-R2-N01-D67-SHARED-LIST-WALK-FOUR-SIGNALS. The JOIN/USING block
# above established the shared walk; this one carries the four remaining
# comma-list families onto it. Each of these four keywords was *already* a
# recognised signal, so the first element of its list was always a position and
# the D6.3 statement backstop was always disarmed by it -- only the continuation
# was out of reach. Reproduced on both surfaces against this source immediately
# before this increment (`GATE2-R2-N01-D67-REMAINING-FAMILIES-D8-RECONCILIATION-
# 2026-10-06.md`, and re-run directly by this session):
#
#   INSERT INTO mem_t, bil_invoices SELECT 1                      PASS/0, own 1 other 0
#   DROP TABLE mem_t, bil_invoices                                PASS/0, own 1 other 0
#   UPDATE mem_t, bil_invoices SET x = 1                          PASS/0, own 1 other 0
#   CREATE TABLE mem_t (c int REFERENCES mem_a, bil_invoices)     PASS/0, own 2 other 0
#
# -- each a cross-domain raw-table reference at exit 0 with the billing target
# absent from the stream entirely, while the identical list under `FROM` was
# already refused. The fix is membership in `_LIST_POSITION_SIGNALS` and nothing
# else: no fifth copy of the continuation walk, which is what the mutation
# control at the end of this block pins.
#
# Still pending and NOT asserted here: `ONLY` (its single-target extraction
# yields `ONLY` itself as the identifier, which no list walk fixes), the
# bare-verb `TRUNCATE`/`COPY`/`GRANT ... ON` forms (no position result at all,
# refused only by the statement-level backstop), the full
# N1-N10/P1-P5/M-E1-M-E7 corpus, and D6.7.5's lower-bound-vs-complete D8 wording.
# (Both of those first two have since been closed by their own increments below --
# `ONLY` by GATE2-R2-N01-D67-ONLY-MODIFIER-SHARED-TARGET-WALK-2026-10-06 and
# `TRUNCATE` by GATE2-R2-N01-D67-TRUNCATE-BARE-VERB-SIGNAL-2026-10-06. `COPY` and
# `GRANT ... ON` remain pending. The list above is left as this increment's own
# record of what it did not claim.)

# Each row: the statement, and its expected D3.2 state-1 (own) count. The `own`
# figure is what makes these more than "something failed": every clean
# own-module position must still be attributed, so a fix that refused the whole
# statement, or that reached the cross-domain element by losing a preceding one,
# cannot satisfy them. `other` is 1 in every row -- the element that used to be
# invisible.
_D67_FOUR_SIGNAL_NEGATIVES = (
    ("INSERT INTO mem_t, bil_invoices SELECT 1", "INTO", 1),
    ("DROP TABLE mem_t, bil_invoices", "TABLE", 1),
    ("UPDATE mem_t, bil_invoices SET x = 1", "UPDATE", 1),
    ("CREATE TABLE mem_t (c int REFERENCES mem_a, bil_invoices)", "REFERENCES", 2),
)

# The unresolved-second-element control for the same four families. A
# parenthesised subquery is the shape D6.7.3 names explicitly: ERROR at exit 2
# rather than a silently shortened list. Each fixture's *first* element resolves
# cleanly to an own-module table, so none of them can reach the refusal by the
# statement-level route the position-result core already removed.
_D67_FOUR_SIGNAL_UNRESOLVED = (
    ("INSERT INTO mem_t, (SELECT 1) SELECT 1", "INTO"),
    ("DROP TABLE mem_t, (SELECT 1)", "TABLE"),
    ("UPDATE mem_t, (SELECT 1) SET x = 1", "UPDATE"),
    ("CREATE TABLE mem_t (c int REFERENCES mem_a, (SELECT 1))", "REFERENCES"),
)

# The non-vacuity discriminators: the ordinary SQL each of the four signals is
# overwhelmingly more likely to be followed by. A comma after `TABLE`, `INTO` or
# `UPDATE` usually opens a *column* list or a SET assignment list, not a table
# list, and `REFERENCES` usually carries one target -- so a walk that treated
# every comma as a list continuation would refuse routine statements. Each row
# is the statement and its expected own count.
_D67_FOUR_SIGNAL_POSITIVES = (
    ("CREATE TABLE mem_t (id int, x int)", 1),            # column list, not a table list
    ("UPDATE mem_t SET x = 1, y = 2", 1),                 # SET assignment list
    ("CREATE TABLE mem_t (c int REFERENCES mem_a)", 2),   # single REFERENCES target
    ("INSERT INTO mem_t (x, y) VALUES (1, 2)", 1),        # INSERT column list
)


def _d67_four_signal_files(sql):
    """The two source shapes the gate scans, for one statement: a `.py` string
    literal (the AST path) and a real `.sql` fixture file. Every row below is
    asserted through both, so no family is pinned on only one surface."""
    return ({"service.py": f'Q = "{sql}"\n'}, {"query.sql": f"{sql}\n"})


def test_gate2_d6_7_four_signal_comma_lists_cross_domain_both_surfaces():
    """D6.7.2/D6.7.3 for `INTO`, `TABLE`, `UPDATE` and `REFERENCES`: the second
    element of each one's comma list is now its own table position, so a
    cross-domain target there is `CROSS_DOMAIN_SQL_IMPORT` at FAIL exit 1 -- on
    both the `.py` literal and `.sql` file surfaces -- where all four reached
    PASS exit 0 before.

    The `own` assertion per row is the half that distinguishes a real fix from a
    blanket refusal, and the `other == 1` assertion is the defect itself: that
    element was not merely unattributed before, it was not in the stream."""
    for sql, _signal, own in _D67_FOUR_SIGNAL_NEGATIVES:
        for files in _d67_four_signal_files(sql):
            report = _f12b_run(files)
            assert report.status == FAIL, (sql, files, report.render())
            assert report.exit_code == 1, (sql, files, report.render())
            assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, (
                sql, files, report.render())
            cross = [v for v in report.violations
                     if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
            assert len(cross) == 1, (sql, files, report.render())
            assert cross[0].subject == "membership -> billing", (sql, cross[0])
            assert "'bil_invoices'" in cross[0].detail, (sql, cross[0])
            counts = _f12b_counts(report)
            assert counts["own"] == own, (sql, files, counts)
            assert counts["other"] == 1, (sql, files, counts)
    # The `.sql` surface really was scanned as a file, not merely as text.
    report = _f12b_run({"query.sql": f"{_D67_FOUR_SIGNAL_NEGATIVES[0][0]}\n"})
    assert "membership/query.sql" in report.checked, report.checked


def test_gate2_d6_7_four_signal_unresolved_second_element_errors_naming_signal():
    """D6.7.3's "an element the lexer cannot reduce to an identifier is ERROR,
    never dropped", for the four new families: a clean first element followed by
    a parenthesised subquery is `MODULE_DEPS_SOURCE_UNINSPECTABLE` at exit 2, and
    the refusal must name the originating signal -- a refusal that cannot say
    which position went unaccounted is not actionable."""
    for sql, signal in _D67_FOUR_SIGNAL_UNRESOLVED:
        for files in _d67_four_signal_files(sql):
            report = _f12b_run(files)
            assert report.status == ERROR, (sql, files, report.render())
            assert report.exit_code == 2, (sql, files, report.render())
            assert "MODULE_DEPS_SOURCE_UNINSPECTABLE" in report.codes(), (
                sql, files, report.render())
            named = [v for v in report.violations
                     if v.code == "MODULE_DEPS_SOURCE_UNINSPECTABLE"
                     and f"{signal} signal at offset" in v.detail]
            assert len(named) == 1, (sql, files, report.render())


def test_gate2_d6_7_four_signal_ordinary_comma_forms_stay_clean():
    """The non-vacuity control for the block above, through both surfaces. A
    column list, a `SET` assignment list, a single `REFERENCES` target and an
    `INSERT` column list must all stay PASS exit 0 with every genuine table
    position still counted at D3.2 state 1.

    This is the assertion that would catch the over-extraction a four-signal
    walk most plausibly causes: `TABLE`/`INTO`/`UPDATE` are followed by a comma
    far more often in ordinary SQL than in a table list, and a walk that read
    `(id int, x int)` as two table positions would ERROR on routine DDL -- the
    pressure-to-weaken-the-gate outcome ADR-011's Alternatives table rejects."""
    for sql, own in _D67_FOUR_SIGNAL_POSITIVES:
        for files in _d67_four_signal_files(sql):
            report = _f12b_run(files)
            assert report.status == PASS, (sql, files, report.render())
            assert report.exit_code == 0, (sql, files, report.render())
            assert report.violations == [], (sql, files, report.render())
            counts = _f12b_counts(report)
            assert counts["own"] == own, (sql, files, counts)
            assert counts["other"] == 0, (sql, files, counts)
            assert counts["unattributed"] == 0, (sql, files, counts)


def test_gate2_d6_7_four_signal_shared_walk_mutation_control():
    """Targeted mutation/invariant control for this increment, in the same
    white-box convention as the other hand-verified mutants in this file.

    Two mutants were applied by hand to the real source and re-run:

      * **dropped-signal**: removing `INTO`, `TABLE`, `UPDATE` and `REFERENCES`
        from `_LIST_POSITION_SIGNALS` -- i.e. the state this increment started
        from. Verified by hand to fail: `_extract_table_identifiers` drops the
        `bil_invoices` element in all four negatives, `_dangling_keywords` stays
        `False`, and the gate reports PASS exit 0, so the negatives above fail on
        status. The exact-set assertion below also fails directly, and is what
        makes a *partial* drop (one keyword put back, three left off) visible
        rather than only a total one.
      * **shared-continuation**: deleting the `while` continuation loop from
        `_table_list_positions`. Verified by hand to fail here *and* in the
        N1/N8/N9 `FROM`-list tests and the JOIN/USING block above -- one edit,
        every family. That is the structural property four hand-copied
        per-keyword walks would not have, and the reason this increment is a
        membership change rather than new code.

    Both mutants were reverted and the suite re-run green afterwards. The
    equivalent-mutant note from the earlier controls still applies: a mutant that
    merely reorders `_TABLE_POSITION_SIGNAL_SOURCES` changes position order but
    not accounting, and nothing here claims to kill it."""
    from validate_architecture_gates import (
        _LIST_POSITION_SIGNALS,
        _dangling_keywords,
        _extract_table_identifiers,
        _positions_for_signal,
        _table_position_results,
    )
    # The exact membership set, so a dropped or silently-renamed signal is a
    # failure here and not only in the behavioural tests above.
    # TRUNCATE, then COPY, then the GRANT/REVOKE object-clause `ON` joined this set
    # through their context-sensitive signal sources. Keep the exact set pinned so
    # none of those sources can silently lose the shared list walk.
    assert _LIST_POSITION_SIGNALS == {
        "FROM", "JOIN", "USING", "INTO", "TABLE", "UPDATE", "REFERENCES", "TRUNCATE",
        "COPY", "ON",
    }, _LIST_POSITION_SIGNALS
    # Still exactly one reference to the one walk: a per-keyword copy wired in
    # beside it would have to show up as a second call site here.
    assert _positions_for_signal.__code__.co_names.count(
        "_table_list_positions") == 1, _positions_for_signal.__code__.co_names

    for sql, signal, own in _D67_FOUR_SIGNAL_NEGATIVES:
        idents = _extract_table_identifiers(sql)
        assert idents[-1] == "bil_invoices", (sql, idents)
        assert len(idents) == own + 1, (sql, idents)
        # The continued element belongs to the signal that introduced it, so the
        # refusal and the FAIL can both name it.
        signals = [p.signal.upper() for p in _table_position_results(sql)]
        assert signals[-2:] == [signal, signal], (sql, signals)
        # Not reached via the statement-level backstop: nothing dangles here.
        assert _dangling_keywords(sql) is False, sql

    # Three-element lists, so a mutant that widens the walk by exactly one
    # element rather than genuinely looping is caught for these families too.
    for sql, expected in (
        ("INSERT INTO mem_t, bil_invoices, mem_d SELECT 1",
         ["mem_t", "bil_invoices", "mem_d"]),
        ("DROP TABLE mem_t, bil_invoices, mem_d",
         ["mem_t", "bil_invoices", "mem_d"]),
        ("UPDATE mem_t, bil_invoices, mem_d SET x = 1",
         ["mem_t", "bil_invoices", "mem_d"]),
        ("CREATE TABLE mem_t (c int REFERENCES mem_a, bil_invoices, mem_d)",
         ["mem_t", "mem_a", "bil_invoices", "mem_d"]),
    ):
        assert _extract_table_identifiers(sql) == expected, sql

    # The complementary direction for all four: an unresolved continuation
    # element is a record of its own naming its signal, never a shortened list.
    for sql, signal in _D67_FOUR_SIGNAL_UNRESOLVED:
        positions = _table_position_results(sql)
        assert positions[-1].identifier is None, (sql, positions)
        assert positions[-1].unresolved is not None, (sql, positions)
        assert positions[-1].signal.upper() == signal, positions[-1]
        assert _dangling_keywords(sql) is True, sql


# --- ADR-011 addendum D6.7.3: `ONLY` is a modifier on a table target -------------
#
# GATE2-R2-N01-D67-ONLY-MODIFIER-SHARED-TARGET-WALK-2026-10-06, implementing the
# first bounded increment named by
# `GATE2-R2-N01-D67-ONLY-BARE-SIGNAL-ROOT-CAUSE-2026-10-06.md`. `ONLY` is
# PostgreSQL's inheritance modifier on a table target already introduced by
# another signal -- *not* an independent table-position signal, and not a table
# name. Reproduced on both surfaces against this source immediately before this
# increment (that record's §"Reproduction", and re-run directly by this session):
#
#   SELECT * FROM ONLY mem_roster                 ERROR/2 MODULE_DEPS_TABLE_UNATTRIBUTED
#   SELECT * FROM mem_roster, ONLY mem_events     ERROR/2 MODULE_DEPS_TABLE_UNATTRIBUTED
#   SELECT * FROM mem_roster, ONLY bil_invoices   ERROR/2 MODULE_DEPS_TABLE_UNATTRIBUTED
#
# -- each because the target lexer read the modifier itself as the identifier
# (`'ONLY'`), so the two own-module statements were refused for a table that does
# not exist while their real, owned targets went unexamined, and the cross-domain
# one reported the same misattribution in place of the `CROSS_DOMAIN_SQL_IMPORT`
# the billing target earns. That is a false attribution, not an omitted signal:
# the fix consumes the modifier inside the shared target lexing used by both of
# `_table_list_positions`' element sites, and `ONLY` is deliberately NOT added to
# `_TABLE_POSITION_SIGNAL_SOURCES` or `_LIST_POSITION_SIGNALS` (either would emit
# a second position for one target). It stays a `_TABLE_POSITION_KEYWORDS` member,
# so a bare `ONLY` in text with no recognised signal still fails closed through
# the D6.3 I-1 backstop -- this increment removes no ERROR surface.
#
# Still pending and NOT asserted here: the bare-verb families (no position result at
# all as of this increment, refused only by the statement-level backstop -- the
# `TRUNCATE` one is covered by the next increment below, `COPY` and `GRANT ... ON`
# remain pending), the full N1-N10/P1-P5/M-E1-M-E7 corpus, D6.7.2 totality, and
# D6.7.5's lower-bound-vs-complete D8 wording.

_D67_ONLY_FIRST_OWN = "SELECT * FROM ONLY mem_roster"
_D67_ONLY_CONT_OWN = "SELECT * FROM mem_roster, ONLY mem_events"
_D67_ONLY_CONT_CROSS = "SELECT * FROM mem_roster, ONLY bil_invoices"
_D67_ONLY_DANGLING = "SELECT * FROM ONLY"
# The two non-ONLY controls the root-cause record requires alongside them, so the
# modifier work is shown not to have widened the walk onto a column list or
# invented a position where there is none.
_D67_ONLY_USING_COLUMN_LIST = "SELECT a FROM mem_x JOIN mem_y USING (id)"
_D67_ONLY_NO_POSITION = "SELECT 1"

# Exact per-position records: `(signal, signal_start, element_start, identifier)`.
# `element_start` is where the position's own *target text* begins, which is the
# `ONLY` itself when the modifier is written -- the modifier is part of the
# target, so a refusal points a reader at the whole target rather than at the
# identifier the lexer could not reach. Offsets are pinned exactly, not merely
# ordered, so a mutant that resolves the right identifier from the wrong place
# (or re-reads the statement to find it) is visible here.
_D67_ONLY_EXACT_POSITIONS = (
    (_D67_ONLY_FIRST_OWN, [("FROM", 9, 14, "mem_roster")]),
    (_D67_ONLY_CONT_OWN, [("FROM", 9, 14, "mem_roster"),
                          ("FROM", 9, 26, "mem_events")]),
    (_D67_ONLY_CONT_CROSS, [("FROM", 9, 14, "mem_roster"),
                            ("FROM", 9, 26, "bil_invoices")]),
    (_D67_ONLY_DANGLING, [("FROM", 9, 14, None)]),
    (_D67_ONLY_USING_COLUMN_LIST, [("FROM", 9, 14, "mem_x"),
                                   ("JOIN", 20, 25, "mem_y")]),
    (_D67_ONLY_NO_POSITION, []),
)


def test_gate2_d6_7_only_modifier_exact_table_positions():
    """The per-position accounting seam itself, exactly, for all six shapes --
    the assertion a verdict-level test cannot make: that `ONLY` contributes no
    position of its own and the target it modifies contributes exactly one.

    Pinning the full record tuple (signal, both offsets, identifier) is what
    distinguishes this increment's fix from two plausible wrong ones: treating
    `ONLY` as an independent signal would add a position (cardinality fails),
    and leaving the modifier unconsumed would resolve the position to `'ONLY'`
    (identifier fails). The dangling row pins the other required direction --
    `FROM ONLY` stays *one* unresolved position, with a reason naming the
    modifier rather than the misleading "the table name is concatenated in"."""
    from validate_architecture_gates import (
        _dangling_keywords,
        _extract_table_identifiers,
        _table_position_results,
    )
    for sql, expected in _D67_ONLY_EXACT_POSITIONS:
        positions = _table_position_results(sql)
        actual = [(p.signal.upper(), p.signal_start, p.element_start, p.identifier)
                  for p in positions]
        assert actual == expected, (sql, actual)
        # Each record carries exactly one of identifier/reason, per position.
        for p in positions:
            assert (p.identifier is None) != (p.unresolved is None), (sql, p)
        assert _extract_table_identifiers(sql) == [
            ident for _s, _ss, _es, ident in expected if ident is not None], sql
        assert _dangling_keywords(sql) is (
            any(ident is None for _s, _ss, _es, ident in expected)), sql

    # The dangling refusal names the modifier specifically, and the offset it
    # points at is the modifier's own, so the reader is sent to the right token.
    dangling = _table_position_results(_D67_ONLY_DANGLING)[0]
    assert dangling.unresolved == (
        "an 'ONLY' modifier is not followed by a table identifier"), dangling
    assert _D67_ONLY_DANGLING[dangling.element_start:].upper().startswith("ONLY"), (
        dangling, _D67_ONLY_DANGLING)
    assert "FROM signal at offset 9" in dangling.describe(), dangling.describe()


def test_gate2_d6_7_only_modifier_own_table_targets_stay_clean_both_surfaces():
    """Live gate, both source shapes: an `ONLY`-modified own-module target is
    clean at PASS exit 0 with the modified table counted at D3.2 state 1 -- in
    first position and in a `,` continuation alike -- where both were ERROR exit
    2 `MODULE_DEPS_TABLE_UNATTRIBUTED` naming `'ONLY'` before this increment.

    The two non-ONLY controls run here too: `JOIN ... USING (id)` must stay a
    column list contributing no table position of its own (so the modifier work
    did not widen the walk), and `SELECT 1` must stay a clean statement with no
    table position at all (so it did not invent one). Their presence is what
    makes the two ONLY rows evidence of a correct fix rather than of a
    blanket-clean path."""
    for sql, own in ((_D67_ONLY_FIRST_OWN, 1),
                     (_D67_ONLY_CONT_OWN, 2),
                     (_D67_ONLY_USING_COLUMN_LIST, 2),
                     (_D67_ONLY_NO_POSITION, 0)):
        for files in _d67_four_signal_files(sql):
            report = _f12b_run(files)
            assert report.status == PASS, (sql, files, report.render())
            assert report.exit_code == 0, (sql, files, report.render())
            assert report.violations == [], (sql, files, report.render())
            counts = _f12b_counts(report)
            assert counts["own"] == own, (sql, files, counts)
            assert counts["other"] == 0, (sql, files, counts)
            assert counts["unattributed"] == 0, (sql, files, counts)
    # The `.sql` surface really was scanned as a file, not merely as text.
    report = _f12b_run({"query.sql": f"{_D67_ONLY_FIRST_OWN}\n"})
    assert "membership/query.sql" in report.checked, report.checked


def test_gate2_d6_7_only_modifier_continuation_cross_domain_fails_both_surfaces():
    """Live gate, both source shapes: `FROM mem_roster, ONLY bil_invoices` is
    `CROSS_DOMAIN_SQL_IMPORT` at FAIL exit 1 naming the billing target.

    This is the row where the pre-increment misattribution was outright
    dangerous rather than merely noisy: the statement reads another module's
    table, and the gate reported an unattributed `'ONLY'` instead -- a refusal
    for the wrong reason, which a reader could clear by fixing the wrong thing.
    `own == 1` is the half that rules out a blanket refusal: the preceding
    own-module element must still be attributed."""
    for files in _d67_four_signal_files(_D67_ONLY_CONT_CROSS):
        report = _f12b_run(files)
        assert report.status == FAIL, (files, report.render())
        assert report.exit_code == 1, (files, report.render())
        assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, (files, report.render())
        cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
        assert len(cross) == 1, (files, report.render())
        assert cross[0].subject == "membership -> billing", cross[0]
        assert "'bil_invoices'" in cross[0].detail, cross[0]
        counts = _f12b_counts(report)
        assert counts["own"] == 1, (files, counts)
        assert counts["other"] == 1, (files, counts)
        assert counts["unattributed"] == 0, (files, counts)


def test_gate2_d6_7_only_modifier_dangling_target_errors_both_surfaces():
    """Live gate, both source shapes: a modifier with no target after it
    (`FROM ONLY`) is `MODULE_DEPS_SOURCE_UNINSPECTABLE` at ERROR exit 2, naming
    the `FROM` signal and the modifier as the reason.

    The fail-closed direction is preserved rather than improved here -- the
    pre-increment behaviour was also exit 2, via `MODULE_DEPS_TABLE_UNATTRIBUTED`
    on the identifier `'ONLY'`. What changes is which refusal fires and what it
    says: consuming the modifier makes this an *unresolved position* (D6.7.2's
    own class for a recognised position that yielded no identifier) rather than a
    state-6 attribution failure for a table nobody wrote."""
    for files in _d67_four_signal_files(_D67_ONLY_DANGLING):
        report = _f12b_run(files)
        assert report.status == ERROR, (files, report.render())
        assert report.exit_code == 2, (files, report.render())
        assert "MODULE_DEPS_SOURCE_UNINSPECTABLE" in report.codes(), (
            files, report.render())
        assert "MODULE_DEPS_TABLE_UNATTRIBUTED" not in report.codes(), (
            files, report.render())
        named = [v for v in report.violations
                 if v.code == "MODULE_DEPS_SOURCE_UNINSPECTABLE"
                 and "FROM signal at offset" in v.detail
                 and "'ONLY' modifier is not followed by a table identifier"
                 in v.detail]
        assert len(named) == 1, (files, report.render())


def test_gate2_d6_7_only_modifier_mutation_control():
    """Targeted mutation/invariant control for this increment, in the same
    white-box convention as the other hand-verified mutants in this file.

    Three mutants were applied by hand to the real source and re-run:

      * **no-modifier-consumption**: `_consume_only_modifier` returning `pos`
        unconditionally -- i.e. the state this increment started from. Verified
        by hand to fail: both own-module ONLY statements become ERROR exit 2
        `MODULE_DEPS_TABLE_UNATTRIBUTED` on the identifier `'ONLY'` (the clean
        test above fails on status), the cross-domain row stops being a FAIL at
        all (its test fails on status, not merely on counts), and the exact-record
        test fails on `identifier == 'ONLY'`.
      * **independent-ONLY-signal**: adding `_ONLY_MODIFIER_RE.finditer` to
        `_TABLE_POSITION_SIGNAL_SOURCES` while *keeping* consumption. Verified by
        hand to fail: each `ONLY` contributes an extra position resolving to the
        very table it modifies, so the exact-record test fails on cardinality
        (two records for one target in `_D67_ONLY_FIRST_OWN`, three for the
        continuation rows), the own-table clean test fails on its `own` count
        (2 and 3 instead of 1 and 2) and the cross-domain test fails on
        `other == 1` (observed 2 -- the verdict stays FAIL, so this mutant is
        caught by the counts, not by the status). The dangling row survives it:
        both positions are unresolved, so that statement is still
        `MODULE_DEPS_SOURCE_UNINSPECTABLE` at exit 2 and nothing in that test
        reads cardinality -- disclosed rather than claimed killed. This is the
        mutant the root-cause record singles out as the plausible wrong fix (it
        double-counts the target the modifier modifies), and the set-membership
        assertions below kill it directly as well as behaviourally.
      * **dropped-ONLY-continuation**: `break`ing out of the continuation loop
        when the element begins with the modifier, i.e. reaching the modifier but
        dropping the element it introduces. Verified by hand to fail: the
        cross-domain row returns to PASS exit 0 with `own 1 other 0` and the
        billing target absent from the stream entirely (the FAIL test fails on
        status), the own-table continuation row drops to `own 1`, and the
        exact-record test fails on cardinality. This is the control that
        distinguishes "consumed the modifier" from "walked the whole target",
        which a verdict-only assertion on the owned rows could not.

    Each mutant was applied to a throwaway full-structure copy of `tools/` under
    `/tmp` (never to the repository file, confirmed via `git status --porcelain`),
    and the copy was removed afterwards. The
    equivalent-mutant note from the earlier controls still applies: a mutant that
    merely reorders `_TABLE_POSITION_SIGNAL_SOURCES` changes position order but
    not accounting, and nothing here claims to kill it."""
    from validate_architecture_gates import (
        _LIST_POSITION_SIGNALS,
        _ONLY_MODIFIER_RE,
        _TABLE_POSITION_KEYWORDS,
        _TABLE_POSITION_SIGNAL_SOURCES,
        _consume_only_modifier,
        _lex_target_identifier,
        _table_list_positions,
        _table_position_results,
    )
    # `ONLY` is not a signal, in either of the two places a signal can be
    # declared -- so the independent-ONLY-signal mutant is a failure here and
    # not only in the behavioural tests above.
    assert "ONLY" not in _LIST_POSITION_SIGNALS, _LIST_POSITION_SIGNALS
    # COPY is the fifth source after TRUNCATE and the GRANT/REVOKE object-clause
    # `ON` the sixth (GATE2-R2-N01-D67-GRANT-REVOKE-ON-2026-10-06); a seventh,
    # `ONLY`-shaped entry cannot be added silently. The count is pinned exactly, as
    # before -- only the number moved, and it moved because a named, separately
    # tested source was added, not because this control was loosened. The
    # `__self__` check below names ONLY itself.
    assert len(_TABLE_POSITION_SIGNAL_SOURCES) == 6, _TABLE_POSITION_SIGNAL_SOURCES
    assert all(getattr(source, "__self__", None) is not _ONLY_MODIFIER_RE
               for source in _TABLE_POSITION_SIGNAL_SOURCES), (
        _TABLE_POSITION_SIGNAL_SOURCES)
    # ...but it IS still in D6.7.4's vocabulary floor, so this increment removed
    # no ERROR surface: a bare `ONLY` with no recognised signal still implies a
    # table position for the D6.3 I-1 backstop.
    assert "ONLY" in _TABLE_POSITION_KEYWORDS, _TABLE_POSITION_KEYWORDS

    # One consumption seam, reached by both element sites of the one walk: the
    # first element through `_target_identifier_after_keyword`, the continuation
    # through `_lex_target_identifier` directly. A second hand-rolled consumption
    # beside either would have to show up as a second call site here.
    assert _lex_target_identifier.__code__.co_names.count(
        "_consume_only_modifier") == 1, _lex_target_identifier.__code__.co_names
    walk_names = _table_list_positions.__code__.co_names
    assert "_target_identifier_after_keyword" in walk_names, walk_names
    assert "_lex_target_identifier" in walk_names, walk_names
    assert "_consume_only_modifier" not in walk_names, walk_names

    # The modifier is consumed only at a target's own start offset, so an `ONLY`
    # written anywhere else cannot be swallowed, and an identifier that merely
    # starts with `only` is untouched.
    assert _consume_only_modifier("ONLY mem_t", 0) == 5
    assert _consume_only_modifier("only_members", 0) == 0
    assert _consume_only_modifier("mem_t", 0) == 0
    # Consumed even with no target after it, which is what makes the dangling
    # form an unresolved position instead of resolving to the modifier's text.
    assert _consume_only_modifier("ONLY", 0) == 4

    # Cardinality and identifiers at the seam, for the three ONLY shapes: one
    # position per target, never one per modifier.
    assert [p.identifier for p in _table_position_results(_D67_ONLY_FIRST_OWN)] == [
        "mem_roster"], _D67_ONLY_FIRST_OWN
    assert [p.identifier for p in _table_position_results(_D67_ONLY_CONT_CROSS)] == [
        "mem_roster", "bil_invoices"], _D67_ONLY_CONT_CROSS
    # A modifier on every element of a longer aliased list, so a mutant that
    # consumes the modifier for exactly one element rather than at the shared
    # seam is caught.
    assert [p.identifier for p in _table_position_results(
        "SELECT * FROM ONLY mem_roster m, ONLY bil_invoices b, ONLY mem_dues")] == [
        "mem_roster", "bil_invoices", "mem_dues"]


# --- ADR-011 addendum D6.7.3: the bare-verb `TRUNCATE` table list ------------------
#
# GATE2-R2-N01-D67-TRUNCATE-BARE-VERB-SIGNAL-2026-10-06, implementing the second
# bounded increment named by
# `GATE2-R2-N01-D67-ONLY-BARE-SIGNAL-ROOT-CAUSE-2026-10-06.md` §"Structural seam"
# item 2 (the `ONLY` modifier was item 1). `TRUNCATE` is a *bare-verb* form: its
# target list follows the verb directly, with no table-position keyword in between,
# so unlike the seven signals already in `_LIST_POSITION_SIGNALS` there was nothing
# for the extractor to find it by. Re-executed against this source immediately
# before this increment (that record's §"Reproduction" table, and re-run directly by
# this session, which observed an empty position stream for every row below):
#
#   TRUNCATE mem_roster                  ERROR/2 MODULE_DEPS_SOURCE_UNINSPECTABLE (I-1)
#   TRUNCATE mem_roster, bil_invoices    ERROR/2 MODULE_DEPS_SOURCE_UNINSPECTABLE (I-1)
#
# -- i.e. the statement-wide D6.3 I-1 backstop was the only thing refusing them, so
# the first was refused as uninspectable for a statement whose single target this
# module owns outright, and the second never reached the per-element attribution
# that makes its billing target a `CROSS_DOMAIN_SQL_IMPORT`. That is the
# partial-accounting asymmetry D6.7.2 forbids rather than a false attribution: the
# positions were absent from the stream entirely, so a *mixed* statement carrying any
# other cleanly-extracting position could disarm the statement-wide fallback
# altogether (the counterexample `test_r2n01_d8_mixed_two_file_counterexample_...`
# was built on, before this increment moved it to the still-pending COPY family).
#
# The fix is the two changes the root-cause record prescribes and no third: a
# context-sensitive `_truncate_table_position_matches` signal source, plus
# `_LIST_POSITION_SIGNALS` membership so the list walk, the `ONLY` modifier and the
# unresolved-element rule all come from the one shared `_table_list_positions`. No
# duplicate extractor, no vocabulary-only widening, no change to the backstop.
#
# Two contexts are deliberately excluded by that source, and both are asserted
# below: `TRUNCATE TABLE x` (already walked through the literal `TABLE` signal --
# yielding here too would emit a second position stream for the same targets, the
# first of them resolving to the word `TABLE`), and `TRUNCATE` as a GRANT/REVOKE
# privilege name (`GRANT TRUNCATE ON mem_t TO r`, where the next token is the
# reserved `ON`, which can never be an unquoted table name).
#
# Still pending and NOT asserted here: the `COPY` and `GRANT`/`REVOKE ... ON`
# families (still no position result at all, still refused only by the I-1
# backstop), the full N1-N10/P1-P5/M-E1-M-E7 corpus, D6.7.2 totality, and D6.7.5's
# lower-bound-vs-complete D8 wording. (Both of those first two have since been
# closed by their own increments below -- `COPY` by
# GATE2-R2-N01-D67-COPY-DIRECTION-QUALIFIED-DECISION-2026-10-06 and
# `GRANT`/`REVOKE ... ON` by GATE2-R2-N01-D67-GRANT-REVOKE-ON-2026-10-06, which is
# why the `_D67_TRUNCATE_PRIVILEGE` row's expectation below moved from zero
# positions to the one GRANT object-clause position. The sentence above is left as
# this increment's own record of what it did not claim.)

_D67_TRUNCATE_SINGLE_OWN = "TRUNCATE mem_roster"
_D67_TRUNCATE_LIST_OWN = "TRUNCATE mem_roster, mem_events"
_D67_TRUNCATE_LIST_CROSS = "TRUNCATE mem_roster, bil_invoices"
_D67_TRUNCATE_ONLY_OWN = "TRUNCATE ONLY mem_roster"
_D67_TRUNCATE_ONLY_CROSS = "TRUNCATE mem_roster, ONLY bil_invoices"
# The `TABLE`-keyword form, which this source must leave to the existing `TABLE`
# signal: still two positions, still attributed to `TABLE` and not to `TRUNCATE`.
_D67_TRUNCATE_TABLE_FORM = "TRUNCATE TABLE mem_roster, mem_events"
# The GRANT/REVOKE privilege-name context, where `TRUNCATE` names a privilege and
# not the statement's verb.
_D67_TRUNCATE_PRIVILEGE = "GRANT TRUNCATE ON mem_roster TO someone"
# The two unresolved directions the root-cause record requires: a dangling verb with
# no target at all, and a comma continuation whose element never arrives.
_D67_TRUNCATE_DANGLING = "TRUNCATE"
_D67_TRUNCATE_MALFORMED_COMMA = "TRUNCATE mem_roster, "

# Exact per-position records: `(signal, signal_start, element_start, identifier)`,
# pinned exactly rather than merely ordered, so a mutant that finds the right
# identifier from the wrong place is visible. The two reused `ONLY`-section controls
# at the end are what make these rows evidence of a bounded fix rather than of a
# widened walk: `JOIN ... USING (id)` must stay a column list and `SELECT 1` must
# stay position-free.
_D67_TRUNCATE_EXACT_POSITIONS = (
    (_D67_TRUNCATE_SINGLE_OWN, [("TRUNCATE", 0, 9, "mem_roster")]),
    (_D67_TRUNCATE_LIST_OWN, [("TRUNCATE", 0, 9, "mem_roster"),
                              ("TRUNCATE", 0, 21, "mem_events")]),
    (_D67_TRUNCATE_LIST_CROSS, [("TRUNCATE", 0, 9, "mem_roster"),
                                ("TRUNCATE", 0, 21, "bil_invoices")]),
    # The `ONLY` modifier comes from the shared target lexing, not from a second
    # copy of it: one position per target, the modifier never an identifier.
    (_D67_TRUNCATE_ONLY_OWN, [("TRUNCATE", 0, 9, "mem_roster")]),
    (_D67_TRUNCATE_ONLY_CROSS, [("TRUNCATE", 0, 9, "mem_roster"),
                                ("TRUNCATE", 0, 21, "bil_invoices")]),
    # Excluded contexts: the `TABLE` form stays the `TABLE` signal's two positions
    # (never four, and never one resolving to the word `TABLE`), and the privilege
    # name contributes none *of its own*.
    (_D67_TRUNCATE_TABLE_FORM, [("TABLE", 9, 15, "mem_roster"),
                                ("TABLE", 9, 27, "mem_events")]),
    # The privilege-name row's one position is the GRANT object clause's `ON`,
    # contributed by `_grant_revoke_on_table_position_matches`
    # (GATE2-R2-N01-D67-GRANT-REVOKE-ON-2026-10-06) -- not by the `TRUNCATE`
    # source, which still yields nothing here (asserted directly in the mutation
    # control below). Before that increment this row was `[]`. The control this
    # row carries is unchanged and now pinned more tightly than it was: no
    # position resolves to the reserved word `on`, and none is attributed to a
    # `TRUNCATE` signal.
    (_D67_TRUNCATE_PRIVILEGE, [("ON", 15, 18, "mem_roster")]),
    # Unresolved, per position -- never a dropped element and never a shortened list.
    (_D67_TRUNCATE_DANGLING, [("TRUNCATE", 0, 8, None)]),
    (_D67_TRUNCATE_MALFORMED_COMMA, [("TRUNCATE", 0, 9, "mem_roster"),
                                     ("TRUNCATE", 0, 21, None)]),
    # Reused controls (unchanged by this increment).
    (_D67_ONLY_USING_COLUMN_LIST, [("FROM", 9, 14, "mem_x"),
                                   ("JOIN", 20, 25, "mem_y")]),
    (_D67_ONLY_NO_POSITION, []),
)


def test_gate2_d6_7_truncate_bare_verb_exact_table_positions():
    """The per-position accounting seam itself, exactly, for every shape -- the
    assertion a verdict-level test cannot make: that each `TRUNCATE` target is its
    own record naming the `TRUNCATE` signal, and that the two excluded contexts
    contribute what they contributed before and nothing more.

    Pinning the full record tuple is what separates this increment's fix from the
    wrong ones: a vocabulary-only patch leaves every row empty, a context-free
    `TRUNCATE` source makes `_D67_TRUNCATE_TABLE_FORM` four positions (the two extra
    ones resolving to the word `TABLE` and to `mem_events` a second time -- executed,
    not supposed) and gives `_D67_TRUNCATE_PRIVILEGE` a second, `TRUNCATE`-signalled
    position resolving to `on` beside the `ON` one it legitimately has, and a
    per-keyword copy of the list walk shows up as a missing `ONLY` consumption or a
    missing continuation here rather than only in a verdict."""
    from validate_architecture_gates import (
        _dangling_keywords,
        _extract_table_identifiers,
        _table_position_results,
    )
    for sql, expected in _D67_TRUNCATE_EXACT_POSITIONS:
        positions = _table_position_results(sql)
        actual = [(p.signal.upper(), p.signal_start, p.element_start, p.identifier)
                  for p in positions]
        assert actual == expected, (sql, actual)
        # Each record carries exactly one of identifier/reason, per position.
        for p in positions:
            assert (p.identifier is None) != (p.unresolved is None), (sql, p)
        assert _extract_table_identifiers(sql) == [
            ident for _s, _ss, _es, ident in expected if ident is not None], sql
        assert _dangling_keywords(sql) is (
            any(ident is None for _s, _ss, _es, ident in expected)), sql

    # The two unresolved shapes carry *different* reasons, so a refusal tells a
    # reader which of D6.7.3's two failures it is looking at rather than guessing.
    dangling = _table_position_results(_D67_TRUNCATE_DANGLING)[0]
    assert dangling.unresolved == (
        "not followed by an identifier (the table name is concatenated in)"), dangling
    assert "TRUNCATE signal at offset 0" in dangling.describe(), dangling.describe()
    malformed = _table_position_results(_D67_TRUNCATE_MALFORMED_COMMA)[-1]
    assert malformed.unresolved == (
        "a ',' list continuation is not followed by an identifier"), malformed
    assert "TRUNCATE signal at offset 0" in malformed.describe(), malformed.describe()


def test_gate2_d6_7_truncate_own_table_targets_stay_clean_both_surfaces():
    """Live gate, both source shapes: an own-module `TRUNCATE` target list is clean
    at PASS exit 0 with every target counted at D3.2 state 1 -- where every one of
    these was ERROR exit 2 `MODULE_DEPS_SOURCE_UNINSPECTABLE` via the I-1 backstop
    before this increment, for statements this module owns outright.

    The excluded-context rows run here too, and are the half that rules out a
    context-free source: `TRUNCATE TABLE mem_roster, mem_events` must still count
    exactly 2 own references (a context-free source would count 4 and report the
    word `TABLE` as unattributed, so this row would be ERROR), and
    `GRANT TRUNCATE ON mem_roster TO someone` (asserted in its own block below)
    must still never resolve `on` as a
    table -- it is now clean at own=1 through its GRANT object clause
    (GATE2-R2-N01-D67-GRANT-REVOKE-ON-2026-10-06, which replaced this row's
    pre-existing I-1 ERROR with the attribution of the one table the statement
    names), and a context-free `TRUNCATE` source would break it by adding a second
    position on the reserved word. The `JOIN ... USING (id)` and `SELECT 1`
    controls prove the walk was not widened and no position was invented."""
    for sql, own in ((_D67_TRUNCATE_SINGLE_OWN, 1),
                     (_D67_TRUNCATE_LIST_OWN, 2),
                     (_D67_TRUNCATE_ONLY_OWN, 1),
                     (_D67_TRUNCATE_TABLE_FORM, 2),
                     (_D67_ONLY_USING_COLUMN_LIST, 2),
                     (_D67_ONLY_NO_POSITION, 0)):
        for files in _d67_four_signal_files(sql):
            report = _f12b_run(files)
            assert report.status == PASS, (sql, files, report.render())
            assert report.exit_code == 0, (sql, files, report.render())
            assert report.violations == [], (sql, files, report.render())
            counts = _f12b_counts(report)
            assert counts["own"] == own, (sql, files, counts)
            assert counts["other"] == 0, (sql, files, counts)
            assert counts["unattributed"] == 0, (sql, files, counts)
    # The GRANT privilege-name context: this source still contributes nothing for
    # it, and specifically there is still no state-6 attribution of the reserved
    # word `ON` as a table -- the only reference counted is the one real table the
    # statement names, through the GRANT object clause's own signal. The
    # pre-GATE2-R2-N01-D67-GRANT-REVOKE-ON-2026-10-06 expectation here was the
    # statement-wide I-1 ERROR, which that increment's own tests now cover
    # directly; the invariant this block exists for -- `on` is never a table -- is
    # asserted here, not dropped.
    for files in _d67_four_signal_files(_D67_TRUNCATE_PRIVILEGE):
        report = _f12b_run(files)
        assert report.status == PASS, (files, report.render())
        assert report.exit_code == 0, (files, report.render())
        assert report.violations == [], (files, report.render())
        assert _f12b_counts(report) == {**_F12B_ZERO, "own": 1}, (
            files, report.render())
    from validate_architecture_gates import (
        _extract_table_identifiers,
        _truncate_table_position_matches,
    )
    assert _extract_table_identifiers(_D67_TRUNCATE_PRIVILEGE) == ["mem_roster"], \
        _extract_table_identifiers(_D67_TRUNCATE_PRIVILEGE)
    assert list(_truncate_table_position_matches(_D67_TRUNCATE_PRIVILEGE)) == []
    # The `.sql` surface really was scanned as a file, not merely as text.
    report = _f12b_run({"query.sql": f"{_D67_TRUNCATE_SINGLE_OWN}\n"})
    assert "membership/query.sql" in report.checked, report.checked


def test_gate2_d6_7_truncate_second_element_cross_domain_fails_both_surfaces():
    """Live gate, both source shapes: `TRUNCATE mem_roster, bil_invoices` is
    `CROSS_DOMAIN_SQL_IMPORT` at FAIL exit 1 naming the billing target, and so is
    the `ONLY`-modified spelling of the same list.

    This is the row the defect mattered most in: the statement *destroys* another
    module's table and the gate could only say the source was uninspectable, which
    is the weaker of the two claims and names no module boundary at all. `own == 1`
    is the half that rules out a blanket refusal -- the preceding own-module element
    must still be attributed, which a statement-wide fallback could never do."""
    for sql in (_D67_TRUNCATE_LIST_CROSS, _D67_TRUNCATE_ONLY_CROSS):
        for files in _d67_four_signal_files(sql):
            report = _f12b_run(files)
            assert report.status == FAIL, (sql, files, report.render())
            assert report.exit_code == 1, (sql, files, report.render())
            assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, (
                sql, files, report.render())
            cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
            assert len(cross) == 1, (sql, files, report.render())
            assert cross[0].subject == "membership -> billing", (sql, cross[0])
            assert "'bil_invoices'" in cross[0].detail, (sql, cross[0])
            counts = _f12b_counts(report)
            assert counts["own"] == 1, (sql, files, counts)
            assert counts["other"] == 1, (sql, files, counts)
            assert counts["unattributed"] == 0, (sql, files, counts)


def test_gate2_d6_7_truncate_unresolved_positions_error_both_surfaces():
    """Live gate, both source shapes: both unresolved directions are
    `MODULE_DEPS_SOURCE_UNINSPECTABLE` at ERROR exit 2, naming the `TRUNCATE`
    signal and the reason specific to each.

    The fail-closed direction is preserved rather than improved here -- a dangling
    `TRUNCATE` was already exit 2 via the statement-wide I-1 backstop. What changes
    is that the refusal now names the position: D6.7.2's own class for a recognised
    position that yielded no identifier, per position, so the malformed-continuation
    row still ERRORs even though its *first* element resolved cleanly.

    Both rows report zero attributed references, including the one whose first
    element resolved. That is the existing, deliberate shape of the D6.7.2 refusal
    and not a loss introduced here: `_scan_sql_statement` returns on any unresolved
    position *before* its attribution loop, so a refused statement contributes no
    counted reference -- the truthful figure, since the statement was refused rather
    than examined. The per-position discrimination that proves the first element was
    nonetheless resolved lives at the seam, in
    `test_gate2_d6_7_truncate_bare_verb_exact_table_positions`; what is asserted here
    instead is that the refusal names exactly ONE position and not the clean one, so
    a mutant that refused the whole statement indiscriminately is still caught at
    this level."""
    for sql, reason in (
        (_D67_TRUNCATE_DANGLING,
         "not followed by an identifier (the table name is concatenated in)"),
        (_D67_TRUNCATE_MALFORMED_COMMA,
         "a ',' list continuation is not followed by an identifier"),
    ):
        for files in _d67_four_signal_files(sql):
            report = _f12b_run(files)
            assert report.status == ERROR, (sql, files, report.render())
            assert report.exit_code == 2, (sql, files, report.render())
            assert "MODULE_DEPS_SOURCE_UNINSPECTABLE" in report.codes(), (
                sql, files, report.render())
            assert "MODULE_DEPS_TABLE_UNATTRIBUTED" not in report.codes(), (
                sql, files, report.render())
            named = [v for v in report.violations
                     if v.code == "MODULE_DEPS_SOURCE_UNINSPECTABLE"
                     and "TRUNCATE signal at offset" in v.detail
                     and reason in v.detail]
            assert len(named) == 1, (sql, files, report.render())
            # Exactly one position is named as unresolved: the clean `mem_roster`
            # element of the malformed-comma row is not swept into the refusal.
            assert named[0].detail.count("TRUNCATE signal at offset") == 1, (
                sql, files, named[0].detail)
            assert "mem_roster" not in named[0].detail, (sql, files, named[0].detail)
            # A refused statement contributes no attributed reference, by design.
            assert _f12b_counts(report) == _F12B_ZERO, (sql, files, report.render())


def test_gate2_d6_7_truncate_bare_verb_mutation_control():
    """Targeted mutation/invariant control for this increment, in the same
    white-box convention as the other hand-verified mutants in this file.

    Four mutants were applied by hand to the real source and re-run:

      * **omitted-signal-source** (the meaningful omission control): dropping
        `_truncate_table_position_matches` from `_TABLE_POSITION_SIGNAL_SOURCES`
        -- i.e. the state this increment started from. Verified by hand to fail:
        every `TRUNCATE` row of `_D67_TRUNCATE_EXACT_POSITIONS` becomes `[]`, so
        the exact-record test fails on the first one; the own-table test fails on
        status (PASS -> ERROR, back to the I-1 backstop) and the cross-domain test
        fails on status (FAIL -> ERROR), which is the defect itself -- a
        cross-domain TRUNCATE reported as merely uninspectable.
      * **omitted-list-membership**: keeping the signal source but removing
        `"TRUNCATE"` from `_LIST_POSITION_SIGNALS`, so the verb routes to
        `_single_identifier_position` instead of the shared walk. Verified by hand
        to fail in exactly the partial-list direction D6.7.3 forbids: the first
        target still resolves, so `_D67_TRUNCATE_SINGLE_OWN` still passes, but
        `_D67_TRUNCATE_LIST_CROSS` loses its second element entirely and returns to
        PASS exit 0 with `own 1 other 0` (the cross-domain test fails on status),
        `_D67_TRUNCATE_ONLY_OWN` fails because `_single_identifier_position` reads a
        bare identifier and resolves to the modifier text `'ONLY'`, and the
        exact-record test fails on cardinality. This is the control that
        distinguishes "found the verb" from "walked its whole list through the one
        shared walker".
      * **partial-list mutation**: `break`ing out of the continuation loop after the
        first continuation element, so a list is walked exactly one element further
        than before rather than to its end. Verified by hand to fail on the
        three-element rows asserted below (`mem_dues`/`bil_invoices` absent), while
        leaving every two-element row green -- which is why those three-element rows
        exist rather than only the two-element fixtures the verdict tests use.
      * **context-free source** (dropping both exclusions): verified by hand to fail
        on `_D67_TRUNCATE_TABLE_FORM`, which becomes four positions -- the observed
        stream is `TABLE/mem_roster`, `TABLE/mem_events`, `TRUNCATE/TABLE`,
        `TRUNCATE/mem_events`, i.e. the word `TABLE` attributed as a table name and
        `mem_events` counted twice, so the own-table test fails as that word reaches
        state 6 -- and on `_D67_TRUNCATE_PRIVILEGE`, which becomes one position
        resolving to `'on'`, so its ERROR code changes from
        MODULE_DEPS_SOURCE_UNINSPECTABLE to MODULE_DEPS_TABLE_UNATTRIBUTED and the
        code assertion fails. Each exclusion was then dropped *alone* and re-run:
        dropping only the `TABLE` exclusion kills the first row and leaves the
        privilege row correct; dropping only the `ON` exclusion kills the second and
        leaves the `TABLE` row correct. So neither exclusion is covered by the other,
        and both are load-bearing rather than one being decorative.

    Each mutant was applied to a throwaway full-structure copy of `tools/` under
    `/tmp` (never to the repository file, confirmed via `git status --porcelain`),
    and the copy was removed afterwards. The equivalent-mutant note from the earlier
    controls still applies: a mutant that merely reorders
    `_TABLE_POSITION_SIGNAL_SOURCES` changes position order but not accounting, and
    nothing here claims to kill it."""
    from validate_architecture_gates import (
        _BARE_VERB_FORMS,
        _LIST_POSITION_SIGNALS,
        _TABLE_POSITION_SIGNAL_SOURCES,
        _extract_table_identifiers,
        _positions_for_signal,
        _table_position_results,
        _truncate_table_position_matches,
    )
    # The two changes this increment is allowed to be, asserted as structure so a
    # silently-renamed source or a dropped membership fails here and not only
    # behaviourally.
    assert _truncate_table_position_matches in _TABLE_POSITION_SIGNAL_SOURCES, \
        _TABLE_POSITION_SIGNAL_SOURCES
    assert "TRUNCATE" in _LIST_POSITION_SIGNALS, _LIST_POSITION_SIGNALS
    # Still exactly one reference to the one walk: a TRUNCATE-specific copy wired in
    # beside it would have to show up as a second call site here.
    assert _positions_for_signal.__code__.co_names.count(
        "_table_list_positions") == 1, _positions_for_signal.__code__.co_names
    # `TRUNCATE` stays in D6.7.4's bare-verb vocabulary floor, so this increment
    # removes no ERROR surface from the shapes it does not resolve: `GRANT TRUNCATE,
    # SELECT ON ...` and the still-pending COPY family both still reach the I-1
    # backstop through it.
    assert "TRUNCATE" in _BARE_VERB_FORMS, _BARE_VERB_FORMS

    # Three-element lists, so the partial-list mutant (one element further, not to
    # the end) is caught -- including with a modifier and an alias on every element.
    for sql, expected in (
        ("TRUNCATE mem_roster, bil_invoices, mem_dues",
         ["mem_roster", "bil_invoices", "mem_dues"]),
        ("TRUNCATE ONLY mem_roster, ONLY bil_invoices, ONLY mem_dues",
         ["mem_roster", "bil_invoices", "mem_dues"]),
    ):
        assert _extract_table_identifiers(sql) == expected, sql
    # Trailing non-list clauses are not list elements: a walk that read `RESTART`
    # or `CASCADE` as a continuation would over-extract them into state 6 here.
    for sql, expected in (
        ("TRUNCATE mem_roster RESTART IDENTITY", ["mem_roster"]),
        ("TRUNCATE mem_roster, mem_events CASCADE", ["mem_roster", "mem_events"]),
    ):
        assert _extract_table_identifiers(sql) == expected, sql
    # The signal source's own two exclusions, at the source rather than through a
    # verdict: `TABLE`/`ON` are matched at the verb's target offset only, so an
    # identifier merely starting with either is not mistaken for the keyword.
    assert list(_truncate_table_position_matches(_D67_TRUNCATE_TABLE_FORM)) == []
    assert list(_truncate_table_position_matches(_D67_TRUNCATE_PRIVILEGE)) == []
    assert [m.start() for m in _truncate_table_position_matches(
        "TRUNCATE tablespace_log")] == [0]
    assert [m.start() for m in _truncate_table_position_matches(
        "TRUNCATE onboarding_log")] == [0]
    # D6.8 now suppresses the privilege-list TRUNCATE signal at the shared merge
    # point; the GRANT object-clause ON still carries the real table position.
    grant_privilege_list = _table_position_results(
        "GRANT TRUNCATE, SELECT ON mem_roster TO r")
    assert [(p.signal.upper(), p.unresolved is not None)
            for p in grant_privilege_list] == [("ON", False)], \
        grant_privilege_list


# --- ADR-011 addendum D6.7.3's remaining bare-verb family: COPY (dual-surface
# discriminating controls) -----------------------------------------------------
#
# GATE2-R2-N01-D67-COPY-DIRECTION-QUALIFIED-DECISION-2026-10-06 (the qualified
# decision this increment's §4.1/§5/§6 are drawn from, verbatim): `COPY` joins
# `_LIST_POSITION_SIGNALS` via its own context-sensitive
# `_copy_table_position_matches` signal source, and the top-level direction
# `FROM`/`TO` of a table-target COPY is excluded at the one
# `_TABLE_KEYWORD_RE.finditer` slot by a new context-sensitive wrapper appended
# LAST, never first (§4.1 items 1/2/4 -- mirroring the existing comment above
# `_TABLE_POSITION_SIGNAL_SOURCES` about why `_TABLE_KEYWORD_RE` itself stays
# first). `COPY (SELECT 1) TO STDOUT` is reclassified under the pre-existing
# D6.3 clause-3 clean zero-table class (decision record §2) -- a D6.3
# reclassification, not a D6.7 ERROR-surface removal, and neither
# `_BARE_VERB_FORMS` nor `_TABLE_POSITION_KEYWORDS` membership changes.
#
# None of this exists in the source yet: `_copy_table_position_matches` and the
# context-sensitive `FROM`-exclusion wrapper are not yet module symbols. Every
# test below that names either of them imports it locally inside the test
# function body, per this file's own isolation convention (see the module
# docstring note above each prior D6.7 increment's block and the task's own
# instruction) -- never at module scope -- so this file keeps collecting
# cleanly, and every pre-existing test in it stays green, while these new
# controls are RED.
#
# Rows C-01..C-20 below are the qualified decision's §5 table, verbatim, grouped
# by shared assertion shape rather than written as twenty standalone functions:
# own-table PASS (C-01/C-03/C-05/C-12/C-14/C-15/C-18), cross-domain FAIL
# (C-02/C-04/C-06/C-13/C-17), the D8 zero-table partition's own two rows
# (C-07/C-08), the undecidable-ERROR shape shared by C-08 and C-19, the
# retention/non-regression rows (C-09/C-10/C-11), the quoted-identifier D3.1
# control (C-16), and the mixed-statement/bare-verb-trigger row (C-20). M-C8 is
# §5.1's own mutation-control row -- the only mutation control this increment
# of the test file is scoped to encode.


def _copy_four_signal_files(sql):
    """COPY-family dual-surface fixture, as `_d67_four_signal_files` but via
    `repr(sql)` for the `.py` literal so a fixture containing its own quote
    characters (a quoted identifier, a single-quoted path, a PROGRAM command)
    embeds safely instead of corrupting the generated literal."""
    return ({"service.py": f"Q = {sql!r}\n"}, {"query.sql": f"{sql}\n"})


# C-01, C-03, C-05, C-12, C-14, C-15, C-18: own-module COPY targets across the
# seven shapes that must each resolve to exactly the one `mem_` position and
# nothing else -- the simple target form, the `FROM STDIN` direction form (the
# direction token must NOT survive as its own `STDIN` position), the
# query-form's inner `FROM`, a column list in front of the direction, a path
# literal plus a `WITH (...)` option clause, a `PROGRAM` destination, and the
# `ONLY` modifier (consumed by the shared target walk, never its own
# position).
_COPY_OWN_PASS_ROWS = (
    ("C-01", "COPY mem_roster TO STDOUT", ["mem_roster"]),
    ("C-03", "COPY mem_roster FROM STDIN", ["mem_roster"]),
    ("C-05", "COPY (SELECT * FROM mem_roster) TO STDOUT", ["mem_roster"]),
    ("C-12", "COPY mem_roster (a, b) FROM STDIN", ["mem_roster"]),
    ("C-14", "COPY mem_roster FROM '/tmp/x.csv' WITH (FORMAT csv)", ["mem_roster"]),
    ("C-15", "COPY mem_roster TO PROGRAM 'gzip > /tmp/x.gz'", ["mem_roster"]),
    ("C-18", "COPY ONLY mem_roster FROM STDIN", ["mem_roster"]),
)


def test_gate2_d6_7_copy_own_table_target_passes_both_surfaces():
    """C-01/C-03/C-05/C-12/C-14/C-15/C-18: every own-module COPY shape is PASS
    exit 0 with exactly one position resolving to the one `mem_` target, on
    both the `.py` literal and `.sql` file surfaces -- pinning status, exit
    code, position cardinality and the extracted identifier list per row,
    per §5's own instruction that codes alone are insufficient (the live
    defect produces the right-looking exit code with the wrong identifier).

    The two direction-token rows (C-03, C-18) additionally assert that no
    position's identifier is the literal `STDIN` -- the exact false position
    the direction-token exclusion exists to remove, and the shape M-C5
    (under-exclusion, retaining `FROM -> STDIN`) would reproduce."""
    from validate_architecture_gates import (
        _extract_table_identifiers,
        _table_position_results,
    )
    for cid, sql, idents in _COPY_OWN_PASS_ROWS:
        positions = _table_position_results(sql)
        assert _extract_table_identifiers(sql) == idents, (cid, sql)
        assert len(positions) == len(idents), (cid, sql, positions)
        assert all(p.identifier != "STDIN" for p in positions), (cid, sql, positions)
        for files in _copy_four_signal_files(sql):
            report = _f12b_run(files)
            assert report.status == PASS, (cid, sql, files, report.render())
            assert report.exit_code == 0, (cid, sql, files, report.render())
            assert report.violations == [], (cid, sql, files, report.render())
            counts = _f12b_counts(report)
            assert counts["own"] == 1, (cid, sql, files, counts)
            assert counts["other"] == 0, (cid, sql, files, counts)


# C-02, C-04, C-06, C-13, C-17: the same five shapes as the own-table group
# above, with the target swapped to a `bil_` identifier the membership module
# does not own.
_COPY_CROSS_FAIL_ROWS = (
    ("C-02", "COPY bil_invoices TO STDOUT", ["bil_invoices"]),
    ("C-04", "COPY bil_invoices FROM STDIN", ["bil_invoices"]),
    ("C-06", "COPY (SELECT * FROM bil_invoices) TO STDOUT", ["bil_invoices"]),
    ("C-13", "COPY bil_invoices (a, b) FROM STDIN", ["bil_invoices"]),
    ("C-17", "COPY public.bil_invoices FROM STDIN", ["public.bil_invoices"]),
)


def test_gate2_d6_7_copy_cross_domain_target_fails_both_surfaces():
    """C-02/C-04/C-06/C-13/C-17: every one of these COPY shapes names a
    billing target from a membership statement, and must FAIL
    `CROSS_DOMAIN_SQL_IMPORT` exit 1 -- naming both modules via `subject` and
    the target identifier via `detail`, on both surfaces -- where before this
    increment every one of them was invisible to extraction and reached only
    the weaker, module-blind I-1 `MODULE_DEPS_SOURCE_UNINSPECTABLE` ERROR.

    C-17 is this set's D3.3 rule-2 control: the dotted `public.`-qualified
    spelling must resolve through the same new signal source as the bare
    one, not a private regex that only recognises an unqualified name."""
    from validate_architecture_gates import (
        _extract_table_identifiers,
        _table_position_results,
    )
    for cid, sql, idents in _COPY_CROSS_FAIL_ROWS:
        positions = _table_position_results(sql)
        assert _extract_table_identifiers(sql) == idents, (cid, sql)
        assert len(positions) == len(idents), (cid, sql, positions)
        for files in _copy_four_signal_files(sql):
            report = _f12b_run(files)
            assert report.status == FAIL, (cid, sql, files, report.render())
            assert report.exit_code == 1, (cid, sql, files, report.render())
            assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, (
                cid, sql, files, report.render())
            cross = [v for v in report.violations
                     if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
            assert len(cross) == 1, (cid, sql, files, report.render())
            assert cross[0].subject == "membership -> billing", (cid, cross[0])
            assert repr(idents[0]) in cross[0].detail, (cid, cross[0])
            counts = _f12b_counts(report)
            assert counts["own"] == 0, (cid, sql, files, counts)
            assert counts["other"] == 1, (cid, sql, files, counts)


# C-07/C-08: the D8 zero-table partition's own two contrasting rows for this
# family -- the genuinely table-free query form, and the dangling bare verb.
_COPY_ZERO_TABLE_CLEAN = "COPY (SELECT 1) TO STDOUT"   # C-07
_COPY_ZERO_TABLE_DANGLING = "COPY"                     # C-08


def test_gate2_d6_7_copy_bare_verb_predicate_mutation_control():
    """M-C6: table-target and dangling COPY keep the D6.3 bare-verb
    backstop; only a balanced, table-free query form stands it down.

    The end-to-end C-08 ERROR alone cannot distinguish this predicate from
    the independent unresolved-position refusal, so pin the predicate itself.
    """
    from validate_architecture_gates import _has_bare_table_verb_form

    assert _has_bare_table_verb_form("COPY mem_roster TO STDOUT") is True
    assert _has_bare_table_verb_form(_COPY_ZERO_TABLE_DANGLING) is True
    assert _has_bare_table_verb_form(_COPY_ZERO_TABLE_CLEAN) is False


def test_gate2_d6_7_copy_zero_table_partition_both_surfaces():
    """C-07/C-08, the D8 zero-table partition's own two rows for this family.

    C-07 is the decision record's §2 reclassification: `COPY (SELECT 1) TO
    STDOUT` references no table at all, so it must be PASS exit 0 with zero
    positions, counted under the `clean` D8 counter and *not* under
    `implied`/`dangling` -- the reclassification §2 authorizes is D6.3
    clause 3's, applied to a form it did not enumerate, not an ERROR-surface
    removal from any D6.7 clause, and it must not move either of the other
    two counters.

    C-08 is the behavioural signature the decision record's §4.1 item 1 and
    §6 require for a bare, targetless `COPY`: once
    `_copy_table_position_matches` exists, a dangling `COPY` is *yielded* as
    a recognised-but-unresolved position rather than contributing nothing to
    the position stream at all, so it must now increment the derived
    `unresolved` D8 figure through the per-position-accounting `dangling`
    counter -- never through `implied`, which was this exact fixture's
    pre-increment class via the I-1 backstop alone. The later D8 fixtures
    used GRANT ... ON for the still-live implied class until
    GATE2-R2-N01-D67-GRANT-REVOKE-ON-2026-10-06 gave that family a signal source
    too; they now use a GRANT whose object is a non-table type, which that
    increment deliberately leaves on the backstop.
    A fix that only widened `_BARE_VERB_FORMS`/
    `_TABLE_POSITION_KEYWORDS` instead of adding the real signal source would
    leave this fixture on `implied` and is exactly what the `implied == 0`
    assertion below is for."""
    from validate_architecture_gates import _table_position_results
    for files in _copy_four_signal_files(_COPY_ZERO_TABLE_CLEAN):
        report = _f12e_run(files)
        assert report.status == PASS, (files, report.render())
        assert report.exit_code == 0, (files, report.render())
        assert report.violations == [], (files, report.render())
        counts = _f12e_counts(report)
        assert counts == {**_F12E_ZERO, "recognised": 1, "clean": 1}, (files, counts)
    assert _table_position_results(_COPY_ZERO_TABLE_CLEAN) == [], _COPY_ZERO_TABLE_CLEAN

    for files in _copy_four_signal_files(_COPY_ZERO_TABLE_DANGLING):
        report = _f12e_run(files)
        assert report.status == ERROR, (files, report.render())
        assert report.exit_code == 2, (files, report.render())
        assert report.codes() == {"MODULE_DEPS_SOURCE_UNINSPECTABLE"}, (
            files, report.render())
        counts = _f12e_counts(report)
        assert counts["unresolved"] == 1, (files, counts)
        assert counts["implied"] == 0, (files, counts)


# C-08/C-19: the undecidable shape §6 calls out explicitly -- a dangling bare
# `COPY` with nothing after it at all, and a query-form target whose
# parenthesis never closes. Both are *yielded* by the new signal source
# (never silently dropped), so the shared walk records exactly one unresolved
# position and both reach ERROR `MODULE_DEPS_SOURCE_UNINSPECTABLE` exit 2 --
# the pre-existing, safe-direction code and exit, unchanged by this increment.
_COPY_UNDECIDABLE_ROWS = (
    ("C-08", _COPY_ZERO_TABLE_DANGLING),
    ("C-19", "COPY (SELECT 1"),
)


def test_gate2_d6_7_copy_undecidable_target_errors_both_surfaces():
    """C-08/C-19 share one assertion shape: both are undecidable per §6
    (the target offset is neither a well-formed table identifier nor a
    balanced parenthesised query), so both must be ERROR
    `MODULE_DEPS_SOURCE_UNINSPECTABLE` exit 2 on both surfaces -- the safe
    direction an over-eager query-form detector (M-C6, "stop firing for
    every COPY") would fail by turning C-19 into a false clean PASS instead
    of leaving its unbalanced `(` undecidable."""
    for cid, sql in _COPY_UNDECIDABLE_ROWS:
        for files in _copy_four_signal_files(sql):
            report = _f12b_run(files)
            assert report.status == ERROR, (cid, sql, files, report.render())
            assert report.exit_code == 2, (cid, sql, files, report.render())
            assert report.codes() == {"MODULE_DEPS_SOURCE_UNINSPECTABLE"}, (
                cid, sql, files, report.render())


def test_gate2_d6_7_copy_ordinary_from_and_non_vacuity_do_not_regress():
    """C-09/C-10/C-11: this increment's §1.6 retention requirements, made
    concrete -- ordinary `SELECT ... FROM` stays a real table position in all
    text, unconditionally, and the pre-existing multi-element `FROM`/JOIN-
    USING non-vacuity controls must keep passing. None of these three
    statements contains a `COPY` token at all, so this group is the control
    against the over-reaching mutants that are not scoped to one COPY's own
    target offset (M-C3's global `FROM` suppression, and the over-exclusion
    direction M-C4 names) -- it is expected to be green against both the
    pre- and post-increment source, which is the point of a retention
    control."""
    for files in _copy_four_signal_files("SELECT a FROM bil_invoices"):  # C-09
        report = _f12b_run(files)
        assert report.status == FAIL, (files, report.render())
        assert report.exit_code == 1, (files, report.render())
        assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, (files, report.render())
    for files in _copy_four_signal_files(
            "SELECT a FROM mem_roster, mem_events"):  # C-10
        report = _f12b_run(files)
        assert report.status == PASS, (files, report.render())
        assert report.exit_code == 0, (files, report.render())
        counts = _f12b_counts(report)
        assert counts["own"] == 2, (files, counts)
    for files in _copy_four_signal_files(
            "SELECT a FROM mem_x JOIN mem_y USING (id)"):  # C-11
        report = _f12b_run(files)
        assert report.status == PASS, (files, report.render())
        assert report.exit_code == 0, (files, report.render())


_COPY_QUOTED_IDENTIFIER = 'COPY "BIL_INVOICES" FROM STDIN'


def test_gate2_d6_7_copy_quoted_identifier_reaches_shared_lexer_both_surfaces():
    """C-16: a double-quoted, case-preserved target -- the control that tells
    a genuine reach into the shared `_lex_dotted_identifier`/D3.1 lexer every
    other signal goes through apart from a context-free, hand-rolled scan
    (reading up to the next whitespace, say). The quotes and the upper-case
    spelling must both survive into the extracted identifier exactly as
    written, and D3.1's case-sensitivity rule for a quoted segment then makes
    it unattributed -- `"BIL_INVOICES"` matches no module's lower-case `bil_`
    prefix -- rather than a `CROSS_DOMAIN_SQL_IMPORT` or a clean PASS, either
    of which would mean the quote was silently stripped or folded before D3
    ever saw it."""
    from validate_architecture_gates import (
        _extract_table_identifiers,
        _table_position_results,
    )
    expected_ident = '"BIL_INVOICES"'
    assert _extract_table_identifiers(_COPY_QUOTED_IDENTIFIER) == [expected_ident], (
        _COPY_QUOTED_IDENTIFIER)
    assert len(_table_position_results(_COPY_QUOTED_IDENTIFIER)) == 1, (
        _COPY_QUOTED_IDENTIFIER)
    for files in _copy_four_signal_files(_COPY_QUOTED_IDENTIFIER):
        report = _f12b_run(files)
        assert report.status == ERROR, (files, report.render())
        assert report.exit_code == 2, (files, report.render())
        assert report.codes() == {"MODULE_DEPS_TABLE_UNATTRIBUTED"}, (
            files, report.render())
        assert any(expected_ident in v.detail for v in report.violations), (
            files, report.render())


_COPY_MIXED_STATEMENT = "COPY mem_roster FROM STDIN; COPY (SELECT 1) TO STDOUT"


def test_gate2_d6_7_copy_mixed_statement_both_surfaces_and_bare_verb_trigger():
    """C-20, in both of the table's two readings.

    As two lexically-certain `.sql`-cut statements (the ordinary way
    `_d8_statement_subjects` divides this exact text, on both surfaces): the
    first is an own-module table-target COPY (own=1) and the second is the
    D6.3 zero-table clean class (C-07's own fixture) -- together, one
    recognised own-module reference and one clean zero-table subject, with
    the combined report still PASS exit 0 and no unresolved position
    anywhere.

    As a single un-split segment -- the white-box reading §1.3/§5's own C-20
    row calls for, independent of where `_d8_statement_subjects` would
    actually cut it -- `_has_bare_table_verb_form` must still fire, because
    at least one `COPY` occurrence in the text (`COPY mem_roster FROM
    STDIN`) is a table-target form; per §2's second fail-closed boundary,
    the context-sensitive branch only stands down when *every* `COPY`
    occurrence is a well-formed query form, which is not the case for this
    text."""
    from validate_architecture_gates import _has_bare_table_verb_form
    for files in _copy_four_signal_files(_COPY_MIXED_STATEMENT):
        report = _f12b_run(files)
        assert report.status == PASS, (files, report.render())
        assert report.exit_code == 0, (files, report.render())
        assert report.violations == [], (files, report.render())
        b_counts = _f12b_counts(report)
        assert b_counts["own"] == 1, (files, b_counts)
        assert b_counts["other"] == 0, (files, b_counts)
    for files in _copy_four_signal_files(_COPY_MIXED_STATEMENT):
        report = _f12e_run(files)
        e_counts = _f12e_counts(report)
        assert e_counts["clean"] == 1, (files, e_counts)
        assert e_counts["unresolved"] == 0, (files, e_counts)
    # The white-box reading: the whole two-statement text handed to the
    # trigger as one un-split segment, independent of the statement
    # splitter -- a property that must hold regardless of where (or whether)
    # `_d8_statement_subjects` can cut this particular text.
    assert _has_bare_table_verb_form(_COPY_MIXED_STATEMENT) is True, (
        _COPY_MIXED_STATEMENT)


def test_gate2_d6_7_copy_signal_source_position_order_mutation_control():
    """M-C8's pin for this family: appending `_copy_table_position_matches`
    anywhere but last in `_TABLE_POSITION_SIGNAL_SOURCES` -- in particular
    before `_TABLE_KEYWORD_RE`'s own slot at index 0 -- would reorder which
    signal's position comes first for a mixed statement, and §4.1 item 2
    requires it appended LAST, for exactly the reason the comment above that
    tuple already gives for keeping `_TABLE_KEYWORD_RE` first: existing
    position-order assertions must stay unchanged. This is the control
    §5.1's M-C8 row names as "if none exists, one must be added before the
    mutant is run" for this family specifically -- this test is that
    addition. Against the pre-increment source, where
    `_copy_table_position_matches` does not exist at all, this fails at the
    import line itself, which is the correct RED shape for this control
    today (an import error on the not-yet-existing symbol, not a collection-
    wide failure, since the import is local to this function)."""
    from validate_architecture_gates import (
        _TABLE_POSITION_SIGNAL_SOURCES,
        _copy_table_position_matches,
        _grant_revoke_on_table_position_matches,
        _table_position_results,
    )
    assert _copy_table_position_matches in _TABLE_POSITION_SIGNAL_SOURCES, (
        _TABLE_POSITION_SIGNAL_SOURCES)
    assert _TABLE_POSITION_SIGNAL_SOURCES[0] is not _copy_table_position_matches, (
        _TABLE_POSITION_SIGNAL_SOURCES)
    # §4.1 item 2's rule is "appended, never inserted". COPY was the last entry
    # while it was the newest source; GATE2-R2-N01-D67-GRANT-REVOKE-ON-2026-10-06
    # appended the GRANT/REVOKE `ON` source after it under that same rule, which
    # leaves every pre-existing position's order untouched (the point of the rule)
    # and makes COPY's exact index the second-to-last. Still pinned exactly, and
    # still pinned against the mutant this control names -- COPY inserted before
    # `_table_keyword_position_matches` at index 0 -- with the appended source's own
    # index pinned in the same breath so a later entry cannot slip in between
    # unnoticed.
    assert (_TABLE_POSITION_SIGNAL_SOURCES.index(_copy_table_position_matches)
            == len(_TABLE_POSITION_SIGNAL_SOURCES) - 2), _TABLE_POSITION_SIGNAL_SOURCES
    assert (_TABLE_POSITION_SIGNAL_SOURCES.index(
        _grant_revoke_on_table_position_matches)
        == len(_TABLE_POSITION_SIGNAL_SOURCES) - 1), _TABLE_POSITION_SIGNAL_SOURCES

    # A concrete position-ORDER assertion, not just a tuple-membership one: an
    # ordinary `FROM` position must still precede a COPY-introduced position
    # in the returned sequence for one mixed statement carrying both.
    mixed = "SELECT a FROM mem_roster; COPY bil_invoices FROM STDIN"
    positions = _table_position_results(mixed)
    from_positions = [p for p in positions if p.signal.upper() == "FROM"]
    copy_positions = [p for p in positions if p.signal.upper() == "COPY"]
    assert len(from_positions) == 1, (mixed, positions)
    assert len(copy_positions) == 1, (mixed, positions)
    assert positions.index(from_positions[0]) < positions.index(copy_positions[0]), (
        mixed, positions)


# --- ADR-011 addendum D6.7.3's last bare-verb family: GRANT/REVOKE ... ON
# (dual-surface discriminating controls) --------------------------------------
#
# GATE2-R2-N01-D67-GRANT-REVOKE-ON-2026-10-06. Reproduced against the source
# immediately before this increment by this session directly (not quoted from a
# record), on both the `.py` string-literal and `.sql` file surfaces:
#
#   GRANT SELECT ON bil_invoices TO r      zero positions -> ERROR/2
#                                          MODULE_DEPS_SOURCE_UNINSPECTABLE (I-1)
#   REVOKE SELECT ON bil_invoices FROM r   one position, resolving to the grantee
#                                          ROLE `r` -> ERROR/2
#                                          MODULE_DEPS_TABLE_UNATTRIBUTED
#
# -- i.e. a statement handing another module's table to a role could only be
# refused as uninspectable, and the REVOKE spelling of it reported the *role* as
# the unattributed table while the billing target went unexamined. Neither names
# the `CROSS_DOMAIN_SQL_IMPORT` the billing target earns, which is the same
# partial/false-attribution asymmetry the `ONLY`, `TRUNCATE` and `COPY`
# increments each removed in their own family.
#
# The fix is the two changes the earlier bare-verb increments established and no
# third: a context-sensitive `_grant_revoke_on_table_position_matches` signal
# source, plus `_LIST_POSITION_SIGNALS` membership for `ON` so the comma list, the
# `ONLY` modifier and the unresolved-element rule all come from the one shared
# `_table_list_positions`. Plus the REVOKE-grantee `FROM` exclusion at index 0's
# existing wrapper, an offset-equality filter of the same shape as the
# COPY-direction exclusion already there (its offset bounded by a walk of the
# object list and an anchored match, not a search) -- without it the REVOKE row
# above keeps reporting its role as a table.
# No duplicate extractor, no second list walk, no backstop change, and
# deliberately no `_BARE_VERB_FORMS`/`_TABLE_POSITION_KEYWORDS` membership change.
#
# This increment removes NO ERROR surface: `_has_bare_table_verb_form`'s
# GRANT/REVOKE disjunct stays unconditional, so every GRANT/REVOKE `ON` form the
# signal source excludes -- `ON TABLE` (already walked by the `TABLE` signal) and
# the non-table object types (`ON SCHEMA`, `ON ALL TABLES IN SCHEMA`, ...) -- keeps
# exactly the I-1 refusal it had. Making that disjunct context-sensitive would
# reclassify those forms as clean zero-table statements, which is a D6.3 clause-3
# reclassification of the kind COPY's own qualified decision record had to
# authorize; no such record exists for these forms, so this increment does not
# make it.
#
# Still pending and NOT asserted here: the full N1-N10/P1-P5/M-E1-M-E7 corpus,
# D6.7.2 totality, D6.7.5's lower-bound-vs-complete D8 wording, and D3.2 state 3
# (CTE) wiring.

_D67_GRANT_SINGLE_OWN = "GRANT SELECT ON mem_roster TO r"
_D67_GRANT_SINGLE_CROSS = "GRANT SELECT ON bil_invoices TO r"
_D67_REVOKE_SINGLE_OWN = "REVOKE SELECT ON mem_roster FROM r"
_D67_REVOKE_SINGLE_CROSS = "REVOKE SELECT ON bil_invoices FROM r"
_D67_GRANT_LIST_OWN = "GRANT SELECT ON mem_roster, mem_events TO r"
_D67_GRANT_LIST_CROSS = "GRANT SELECT ON mem_roster, bil_invoices TO r"
# The modifier on a comma element and on the first element, so the shared target
# lexing is shown to be reached from both of the walk's element sites for this
# family too -- never one position per modifier.
_D67_GRANT_ONLY_CROSS = "GRANT SELECT ON mem_roster, ONLY bil_invoices TO r"
_D67_GRANT_ONLY_FIRST_OWN = "GRANT SELECT ON ONLY mem_roster TO r"
# A column-privilege list in front of the `ON`, and the `REVOKE GRANT OPTION FOR`
# spelling whose object clause sits after BOTH of the statement's verb keywords --
# the shape that must be de-duplicated to one position stream, not two.
_D67_GRANT_COLUMN_PRIVILEGE_OWN = "GRANT SELECT (col) ON mem_roster TO r"
_D67_REVOKE_GRANT_OPTION_OWN = "REVOKE GRANT OPTION FOR SELECT ON mem_roster FROM r"
# The two excluded contexts. The `TABLE`-keyword form must stay the `TABLE`
# signal's own two positions (never four, and never one resolving to the word
# `TABLE`); a non-table object type must yield no position at all and keep its
# pre-increment I-1 ERROR rather than resolve the object-type keyword as a table.
_D67_GRANT_TABLE_FORM = "GRANT SELECT ON TABLE mem_roster, mem_events TO r"
_D67_GRANT_NON_TABLE_OBJECT = "GRANT USAGE ON SCHEMA mem_private TO r"
# The two unresolved directions, as for TRUNCATE: a dangling object clause with no
# target at all, and a comma continuation whose element never arrives.
_D67_GRANT_DANGLING = "GRANT SELECT ON"
_D67_GRANT_MALFORMED_COMMA = "GRANT SELECT ON mem_roster, "
# The two non-vacuity controls this family specifically needs. An ordinary
# `JOIN ... ON` condition is the single most common `ON` in SQL and must stay a
# condition: a source keying on the bare keyword would resolve `mem_x.id` as a
# table position here. And a role revocation has no object clause at all, so its
# `FROM` must still be a position -- the grantee exclusion may not reach it.
_D67_JOIN_ON_CONDITION = "SELECT a FROM mem_x JOIN mem_y ON mem_x.id = mem_y.id"
_D67_REVOKE_ROLE_ONLY = "REVOKE admin FROM r"

# Exact per-position records: `(signal, signal_start, element_start, identifier)`,
# pinned exactly rather than merely ordered, so a mutant that finds the right
# identifier from the wrong place -- or from the wrong signal -- is visible.
_D67_GRANT_REVOKE_EXACT_POSITIONS = (
    (_D67_GRANT_SINGLE_OWN, [("ON", 13, 16, "mem_roster")]),
    (_D67_GRANT_SINGLE_CROSS, [("ON", 13, 16, "bil_invoices")]),
    (_D67_REVOKE_SINGLE_OWN, [("ON", 14, 17, "mem_roster")]),
    # The REVOKE rows are one position, not two: the grantee `FROM` is excluded,
    # so the role is not a table position. Before this increment this row was
    # exactly `[("FROM", 30, 35, "r")]` -- the role, and only the role.
    (_D67_REVOKE_SINGLE_CROSS, [("ON", 14, 17, "bil_invoices")]),
    (_D67_GRANT_LIST_OWN, [("ON", 13, 16, "mem_roster"),
                           ("ON", 13, 28, "mem_events")]),
    (_D67_GRANT_LIST_CROSS, [("ON", 13, 16, "mem_roster"),
                             ("ON", 13, 28, "bil_invoices")]),
    # The `ONLY` modifier comes from the shared target lexing, not from a second
    # copy of it: one position per target, the modifier never an identifier.
    (_D67_GRANT_ONLY_CROSS, [("ON", 13, 16, "mem_roster"),
                             ("ON", 13, 28, "bil_invoices")]),
    (_D67_GRANT_ONLY_FIRST_OWN, [("ON", 13, 16, "mem_roster")]),
    (_D67_GRANT_COLUMN_PRIVILEGE_OWN, [("ON", 19, 22, "mem_roster")]),
    # One stream for the two verb keywords sharing one object clause, never two.
    (_D67_REVOKE_GRANT_OPTION_OWN, [("ON", 31, 34, "mem_roster")]),
    # Excluded contexts.
    (_D67_GRANT_TABLE_FORM, [("TABLE", 16, 22, "mem_roster"),
                             ("TABLE", 16, 34, "mem_events")]),
    (_D67_GRANT_NON_TABLE_OBJECT, []),
    # Unresolved, per position -- never a dropped element and never a shortened list.
    (_D67_GRANT_DANGLING, [("ON", 13, 15, None)]),
    (_D67_GRANT_MALFORMED_COMMA, [("ON", 13, 16, "mem_roster"),
                                  ("ON", 13, 28, None)]),
    # Non-vacuity controls: the JOIN condition contributes no `ON` position at all,
    # and a role revocation's `FROM` is untouched by the grantee exclusion.
    (_D67_JOIN_ON_CONDITION, [("FROM", 9, 14, "mem_x"), ("JOIN", 20, 25, "mem_y")]),
    (_D67_REVOKE_ROLE_ONLY, [("FROM", 13, 18, "r")]),
)


def test_gate2_d6_7_grant_revoke_on_exact_table_positions():
    """The per-position accounting seam itself, exactly, for every shape of the
    last bare-verb family -- the assertion a verdict-level test cannot make: that
    each target is its own record naming the `ON` signal at the object clause's own
    offset, and that the excluded contexts contribute what they contributed before
    and nothing more.

    Pinning the full record tuple is what separates this increment's fix from the
    wrong ones. A vocabulary-only patch (adding `ON` to `_TABLE_POSITION_KEYWORDS`)
    leaves every GRANT row empty while silently making every `JOIN ... ON`
    statement imply a table position. A context-free `ON` source resolves
    `_D67_JOIN_ON_CONDITION` to a third position on `mem_x.id`, makes
    `_D67_GRANT_TABLE_FORM` four positions (the extra ones resolving to the word
    `TABLE`), and gives `_D67_GRANT_NON_TABLE_OBJECT` a position resolving to the
    word `SCHEMA`. A source yielding the GRANT/REVOKE *verb* instead of the `ON`
    reads the privilege list as the target list. A source without de-duplication
    gives `_D67_REVOKE_GRANT_OPTION_OWN` two records for one target. And a
    per-keyword copy of the list walk shows up as a missing `ONLY` consumption or a
    missing continuation here rather than only in a verdict."""
    from validate_architecture_gates import (
        _dangling_keywords,
        _extract_table_identifiers,
        _table_position_results,
    )
    for sql, expected in _D67_GRANT_REVOKE_EXACT_POSITIONS:
        positions = _table_position_results(sql)
        actual = [(p.signal.upper(), p.signal_start, p.element_start, p.identifier)
                  for p in positions]
        assert actual == expected, (sql, actual)
        # Each record carries exactly one of identifier/reason, per position.
        for p in positions:
            assert (p.identifier is None) != (p.unresolved is None), (sql, p)
        assert _extract_table_identifiers(sql) == [
            ident for _s, _ss, _es, ident in expected if ident is not None], sql
        assert _dangling_keywords(sql) is (
            any(ident is None for _s, _ss, _es, ident in expected)), sql

    # The two unresolved shapes carry *different* reasons, so a refusal tells a
    # reader which of D6.7.3's two failures it is looking at rather than guessing,
    # and both name the `ON` signal at its own offset rather than the verb's.
    dangling = _table_position_results(_D67_GRANT_DANGLING)[0]
    assert dangling.unresolved == (
        "not followed by an identifier (the table name is concatenated in)"), dangling
    assert "ON signal at offset 13" in dangling.describe(), dangling.describe()
    malformed = _table_position_results(_D67_GRANT_MALFORMED_COMMA)[-1]
    assert malformed.unresolved == (
        "a ',' list continuation is not followed by an identifier"), malformed
    assert "ON signal at offset 13" in malformed.describe(), malformed.describe()


def test_gate2_d6_7_grant_revoke_on_own_targets_stay_clean_both_surfaces():
    """Live gate, both source shapes: an own-module GRANT/REVOKE object list is
    clean at PASS exit 0 with every target counted at D3.2 state 1 -- where every
    GRANT row here was ERROR exit 2 `MODULE_DEPS_SOURCE_UNINSPECTABLE` via the I-1
    backstop before this increment, and the REVOKE row was ERROR exit 2
    `MODULE_DEPS_TABLE_UNATTRIBUTED` on the grantee role, for statements this
    module owns outright.

    The `own` figure per row is what makes this more than "something passed": a
    fix that silently stopped recognising the family would also be PASS exit 0, at
    own=0, and so fails here. The `TABLE`-form row is the half that rules out a
    context-free source -- it must still count exactly 2 own references, from the
    `TABLE` signal, never 4 with the word `TABLE` among them."""
    for sql, own in ((_D67_GRANT_SINGLE_OWN, 1),
                     (_D67_REVOKE_SINGLE_OWN, 1),
                     (_D67_GRANT_LIST_OWN, 2),
                     (_D67_GRANT_ONLY_FIRST_OWN, 1),
                     (_D67_GRANT_COLUMN_PRIVILEGE_OWN, 1),
                     (_D67_REVOKE_GRANT_OPTION_OWN, 1),
                     (_D67_GRANT_TABLE_FORM, 2),
                     (_D67_JOIN_ON_CONDITION, 2)):
        for files in _d67_four_signal_files(sql):
            report = _f12b_run(files)
            assert report.status == PASS, (sql, files, report.render())
            assert report.exit_code == 0, (sql, files, report.render())
            assert report.violations == [], (sql, files, report.render())
            counts = _f12b_counts(report)
            assert counts["own"] == own, (sql, files, counts)
            assert counts["other"] == 0, (sql, files, counts)
            assert counts["unattributed"] == 0, (sql, files, counts)
    # The `.sql` surface really was scanned as a file, not merely as text.
    report = _f12b_run({"query.sql": f"{_D67_GRANT_SINGLE_OWN}\n"})
    assert "membership/query.sql" in report.checked, report.checked


def test_gate2_d6_7_grant_revoke_on_cross_domain_fails_both_surfaces():
    """Live gate, both source shapes: a GRANT or REVOKE on another module's table
    is `CROSS_DOMAIN_SQL_IMPORT` at FAIL exit 1 naming the billing target.

    This is the row the defect mattered most in: the statement hands another
    module's table to a role, and the gate could only say the source was
    uninspectable (GRANT) or name the role as an unattributed table (REVOKE) --
    both of which an owner reading the report cannot act on, and neither of which
    is the boundary violation the statement commits. The `own` figure on the list
    rows is the other half: reaching the billing element by losing the preceding
    own-module one would satisfy a FAIL-only assertion."""
    for sql, own, other in ((_D67_GRANT_SINGLE_CROSS, 0, 1),
                            (_D67_REVOKE_SINGLE_CROSS, 0, 1),
                            (_D67_GRANT_LIST_CROSS, 1, 1),
                            (_D67_GRANT_ONLY_CROSS, 1, 1)):
        for files in _d67_four_signal_files(sql):
            report = _f12b_run(files)
            assert report.status == FAIL, (sql, files, report.render())
            assert report.exit_code == 1, (sql, files, report.render())
            assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, (
                sql, files, report.render())
            cross = [v for v in report.violations
                     if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
            assert len(cross) == 1, (sql, files, report.render())
            assert "bil_invoices" in cross[0].detail, (sql, files, report.render())
            counts = _f12b_counts(report)
            assert counts["own"] == own, (sql, files, counts)
            assert counts["other"] == other, (sql, files, counts)
            assert counts["unattributed"] == 0, (sql, files, counts)


def test_gate2_d6_7_grant_revoke_on_unresolved_and_excluded_forms_stay_error():
    """Live gate, both source shapes, for the three ERROR shapes this family must
    keep -- the half of the increment that proves no ERROR surface was removed.

    The first two are the per-position D6.7.2 refusal the new signal source makes
    possible: a dangling object clause and a comma element that never arrives are
    each `MODULE_DEPS_SOURCE_UNINSPECTABLE` at exit 2, now naming the `ON` signal
    and its offset instead of refusing the statement wholesale. The third is the
    form the source deliberately does NOT claim: a non-table object type yields no
    position at all and must keep exactly the statement-wide I-1 backstop refusal
    it had before this increment -- not become a clean zero-table PASS, which is
    what making `_has_bare_table_verb_form`'s GRANT/REVOKE disjunct
    context-sensitive would have done without a decision record authorizing it.

    The role-revocation row last is the grantee exclusion's own non-vacuity
    control: `REVOKE admin FROM r` has no object clause, so no exclusion is
    computed for it and its `FROM` is still a table position reaching D3.2 state 6,
    exactly as before this increment. An exclusion keyed on the `REVOKE` keyword
    alone would silence it and turn this ERROR into a clean PASS."""
    for sql, detail_substring in ((_D67_GRANT_DANGLING, "ON signal at offset 13"),
                                  (_D67_GRANT_MALFORMED_COMMA,
                                   "ON signal at offset 13"),
                                  (_D67_GRANT_NON_TABLE_OBJECT, "I-1 backstop")):
        for files in _d67_four_signal_files(sql):
            report = _f12b_run(files)
            assert report.status == ERROR, (sql, files, report.render())
            assert report.exit_code == 2, (sql, files, report.render())
            assert report.codes() == {"MODULE_DEPS_SOURCE_UNINSPECTABLE"}, (
                sql, files, report.render())
            assert any(detail_substring in v.detail for v in report.violations), (
                sql, files, report.render())
    for files in _d67_four_signal_files(_D67_REVOKE_ROLE_ONLY):
        report = _f12b_run(files)
        assert report.status == ERROR, (files, report.render())
        assert report.exit_code == 2, (files, report.render())
        assert report.codes() == {"MODULE_DEPS_TABLE_UNATTRIBUTED"}, (
            files, report.render())
        assert _f12b_counts(report) == {**_F12B_ZERO, "unattributed": 1}, (
            files, report.render())


def test_gate2_d6_7_grant_revoke_on_signal_source_mutation_control():
    """The two changes this increment is allowed to be, asserted as structure so a
    silently-renamed source or a dropped membership fails here and not only
    behaviourally -- plus the context-sensitivity each exclusion rests on, at the
    source rather than through a verdict.

    Mutants this kills directly, beyond the behavioural tests above:

      * **no-source**: removing `_grant_revoke_on_table_position_matches` from
        `_TABLE_POSITION_SIGNAL_SOURCES` -- the pre-increment state.
      * **no-membership**: removing `"ON"` from `_LIST_POSITION_SIGNALS`, so the
        object clause routes to `_single_identifier_position` and every comma
        element after the first disappears from the stream.
      * **context-free source**: `_ON_KEYWORD_RE.finditer` as the source, which
        claims every `JOIN ... ON` condition. Applied by hand to a throwaway copy
        of `tools/` under `/tmp` (never to the repository file, confirmed via
        `git status --porcelain`) and executed, not supposed:
        `_D67_JOIN_ON_CONDITION` gains a third position resolving to `mem_x.id`,
        `_D67_GRANT_NON_TABLE_OBJECT` one resolving to the word `SCHEMA`, and
        `_D67_GRANT_TABLE_FORM` becomes four positions, the extra two resolving to
        the word `TABLE` and to `mem_events` a second time. Four of this family's
        five tests fail under it; the cross-domain FAIL test *survives* it (that
        mutant over-claims rather than under-claims, and the billing target is
        still attributed), which is disclosed here rather than claimed killed.
      * **second list walk**: a GRANT-specific continuation copy, which would have
        to appear as a second `_table_list_positions` call site in
        `_positions_for_signal`.

    The equivalent-mutant note from the earlier controls still applies: a mutant
    that merely reorders `_TABLE_POSITION_SIGNAL_SOURCES` changes position order
    but not accounting, and nothing here claims to kill it."""
    from validate_architecture_gates import (
        _BARE_VERB_FORMS,
        _LIST_POSITION_SIGNALS,
        _REVOKE_KEYWORD_RE,
        _TABLE_POSITION_KEYWORDS,
        _TABLE_POSITION_SIGNAL_SOURCES,
        _extract_table_identifiers,
        _grant_revoke_on_table_position_matches,
        _positions_for_signal,
        _revoke_grantee_exclusion_offset,
    )
    assert _grant_revoke_on_table_position_matches in _TABLE_POSITION_SIGNAL_SOURCES, \
        _TABLE_POSITION_SIGNAL_SOURCES
    assert "ON" in _LIST_POSITION_SIGNALS, _LIST_POSITION_SIGNALS
    # Still exactly one reference to the one walk: an ON-specific copy wired in
    # beside it would have to show up as a second call site here.
    assert _positions_for_signal.__code__.co_names.count(
        "_table_list_positions") == 1, _positions_for_signal.__code__.co_names
    # The two vocabulary sets are deliberately UNCHANGED by this increment, which
    # is what keeps the excluded forms' I-1 ERROR surface intact: `ON` is still not
    # a generic table-position keyword (a `JOIN ... ON` condition is not a table
    # position), and the bare-verb floor still carries the two verbs it did.
    assert "ON" not in _TABLE_POSITION_KEYWORDS, _TABLE_POSITION_KEYWORDS
    assert _BARE_VERB_FORMS == {"TRUNCATE", "COPY"}, _BARE_VERB_FORMS

    # Three-element lists, so the partial-list mutant (one element further, not to
    # the end) is caught -- including with a modifier on every element.
    for sql, expected in (
        ("GRANT SELECT ON mem_roster, bil_invoices, mem_dues TO r",
         ["mem_roster", "bil_invoices", "mem_dues"]),
        ("REVOKE SELECT ON ONLY mem_roster, ONLY bil_invoices, ONLY mem_dues FROM r",
         ["mem_roster", "bil_invoices", "mem_dues"]),
    ):
        assert _extract_table_identifiers(sql) == expected, sql

    # The signal source's own context sensitivity, at the source. The object clause
    # is identified positively -- the first `ON` after the verb, with only
    # privilege-list text in between -- so a `JOIN ... ON` condition is not
    # claimed even when a GRANT statement sits beside it in the same subject, and
    # an `ON` whose target offset holds `TABLE` or a non-table object type is not
    # claimed at all.
    assert [m.start() for m in _grant_revoke_on_table_position_matches(
        _D67_GRANT_SINGLE_OWN)] == [13]
    assert list(_grant_revoke_on_table_position_matches(_D67_JOIN_ON_CONDITION)) == []
    assert list(_grant_revoke_on_table_position_matches(_D67_GRANT_TABLE_FORM)) == []
    assert list(_grant_revoke_on_table_position_matches(
        _D67_GRANT_NON_TABLE_OBJECT)) == []
    assert list(_grant_revoke_on_table_position_matches(
        "GRANT SELECT ON ALL TABLES IN SCHEMA mem_private TO r")) == []
    mixed = f"{_D67_GRANT_SINGLE_OWN}; {_D67_JOIN_ON_CONDITION}"
    assert [m.start() for m in _grant_revoke_on_table_position_matches(mixed)] == [13]
    # One `ON` yielded once, for the two verb keywords that share it.
    assert [m.start() for m in _grant_revoke_on_table_position_matches(
        _D67_REVOKE_GRANT_OPTION_OWN)] == [31]
    # The exclusions are matched at the object clause's own target offset, never
    # searched for, so an identifier merely *starting* with an excluded keyword is
    # not mistaken for it.
    for sql in ("GRANT SELECT ON tablespace_log TO r",
                "GRANT SELECT ON schema_migrations TO r",
                "GRANT SELECT ON all_members TO r"):
        assert len(list(_grant_revoke_on_table_position_matches(sql))) == 1, sql

    # A privilege name that is itself another source's signal is a PRE-EXISTING
    # residual, disclosed in that source's comment and deliberately not closed
    # here: `GRANT UPDATE ON mem_roster TO r` carries a stray `UPDATE` position
    # resolving to the reserved word `ON`, with and without this increment alike
    # (measured both ways on a throwaway copy). What this increment owns is the
    # object clause's own position, so only that is asserted -- the statement's
    # real target is extracted. The stray position's own outcome is NOT pinned
    # here, because an increment that gives those two sources the privilege-name
    # context sensitivity `TRUNCATE`'s source already has must be free to turn
    # these statements clean without rewriting this assertion.
    for sql in ("GRANT UPDATE ON mem_roster TO r",
                "GRANT REFERENCES ON mem_roster TO r",
                "GRANT TRUNCATE ON mem_roster TO r"):
        assert "mem_roster" in _extract_table_identifiers(sql), (
            sql, _extract_table_identifiers(sql))

    # The REVOKE grantee-`FROM` exclusion, as an offset computed per keyword match
    # by a bounded walk of the object list and an anchored match of `FROM` (an
    # offset-equality filter like COPY's direction exclusion, rather than a
    # role-name pattern): present for a REVOKE with an object clause that leads
    # into its own `FROM`, absent for one without (bounding itself is pinned by
    # `test_gate2_d6_7_revoke_grantee_exclusion_is_bounded_not_searched`).
    revoke = next(_REVOKE_KEYWORD_RE.finditer(_D67_REVOKE_SINGLE_CROSS))
    assert _revoke_grantee_exclusion_offset(_D67_REVOKE_SINGLE_CROSS, revoke) == \
        _D67_REVOKE_SINGLE_CROSS.index("FROM")
    role_only = next(_REVOKE_KEYWORD_RE.finditer(_D67_REVOKE_ROLE_ONLY))
    assert _revoke_grantee_exclusion_offset(_D67_REVOKE_ROLE_ONLY, role_only) is None
    # And a GRANT's own `FROM`-free form needs no exclusion at all, so an ordinary
    # `FROM` elsewhere in a GRANT-bearing subject is untouched.
    assert _extract_table_identifiers(
        f"{_D67_GRANT_SINGLE_OWN}; SELECT a FROM mem_events") == [
            "mem_events", "mem_roster"]


def _d67_revoke_bound_files(sql):
    """`_d67_four_signal_files` for a statement that spans lines. The `.py` shape is a
    triple-quoted literal, because a bare newline inside `"..."` is not a Python
    string at all -- and the newline is the point: a newline with no depth-0 `;`
    is one unsplit D8 subject."""
    return ({"dao.py": f'SQL = """\n{sql}\n"""\n'}, {"repo.sql": f"{sql}\n"})


_D67_REVOKE_NO_GRANTEE_FROM = "REVOKE SELECT ON mem_roster\nSELECT a FROM bil_invoices"
_D67_REVOKE_NO_GRANTEE_FROM_LIST = (
    "REVOKE SELECT ON mem_roster\nSELECT a FROM mem_x, bil_invoices")


def test_gate2_d6_7_revoke_grantee_exclusion_is_bounded_not_searched():
    """R1-F01/R2-N01 P0: `_revoke_grantee_exclusion_offset` must anchor-match the
    grantee `FROM` at the offset a positive walk of the REVOKE's own object list
    computes, never `.search` forward for the next `FROM` anywhere in the subject.

    Pure offsets. The two `None` rows are the defect: with no grantee `FROM` of its
    own, the unbounded search returned the offset of an unrelated later statement's
    ordinary `FROM` (37 for the first row), deleting that table position from the
    stream before the D6.7.2 accounting could see it."""
    from validate_architecture_gates import (
        _REVOKE_KEYWORD_RE,
        _revoke_grantee_exclusion_offset,
    )

    def offset(sql):
        return _revoke_grantee_exclusion_offset(
            sql, next(_REVOKE_KEYWORD_RE.finditer(sql)))

    assert offset(_D67_REVOKE_NO_GRANTEE_FROM) is None
    assert offset(_D67_REVOKE_NO_GRANTEE_FROM_LIST) is None
    # The plain `TO`-for-`FROM` authoring error and a dangling / truncated clause:
    # uncertain object clause -> no exclusion, so a later `FROM` is retained.
    for sql in ("REVOKE SELECT ON mem_roster TO r\nSELECT a FROM bil_invoices",
                "REVOKE SELECT ON\nSELECT a FROM bil_invoices",
                "REVOKE SELECT ON mem_roster,\nSELECT a FROM bil_invoices",
                "REVOKE SELECT ON mem_roster, FROM r",
                "REVOKE SELECT ON mem_roster",
                "REVOKE admin FROM r"):
        assert offset(sql) is None, sql
    # Own grantee `FROM`: excluded at exactly its own offset, and the later
    # ordinary `FROM` is not the one returned.
    own = "REVOKE SELECT ON mem_roster FROM r\nSELECT a FROM bil_invoices"
    assert offset(own) == own.index("FROM") == 28
    # Valid object-list shapes still compute their grantee `FROM`: comma list,
    # `TABLE` / `ONLY` modifiers on each element, qualified and quoted names, a
    # column privilege, `GRANT OPTION FOR`, and a newline before the `FROM`.
    for sql in ("REVOKE SELECT ON mem_roster, mem_events FROM r",
                "REVOKE SELECT ON mem_a, mem_b, mem_c FROM r",
                "REVOKE SELECT ON TABLE mem_roster FROM r",
                "REVOKE SELECT ON TABLE mem_roster, mem_events FROM r",
                "REVOKE SELECT ON ONLY mem_roster FROM r",
                "REVOKE SELECT ON ONLY mem_roster, ONLY mem_events FROM r",
                "REVOKE SELECT ON sb.mem_roster FROM r",
                'REVOKE SELECT ON "mem roster" FROM r',
                "REVOKE SELECT (col) ON mem_roster FROM r",
                "REVOKE GRANT OPTION FOR SELECT ON mem_roster FROM r",
                "REVOKE SELECT ON mem_roster ,mem_events\nFROM r"):
        assert offset(sql) == sql.index("FROM"), sql


def test_gate2_d6_7_revoke_without_grantee_from_keeps_later_from_both_surfaces():
    """Live gate, both source shapes: a REVOKE with no grantee `FROM` of its own
    must not delete a later ordinary `FROM`'s table position from the stream.

    1A/1F/1H were PASS exit 0 -- a cross-domain reference silently lost while the D8
    note called its count complete. They must now be nonzero and name the foreign
    table. The `own` / `other` figures are the other half: the REVOKE's own target
    stays attributed and the recovered `FROM` list (1H, whose second element is the
    cross-domain one) is attributed whole.

    The controls isolate one variable each and must not move: 1B no REVOKE at all,
    1C a depth-0 `;` between the statements, 1D a REVOKE with its own grantee
    `FROM`, 1G two separate `.py` literals (all FAIL exit 1); 1E, the lone own-domain
    REVOKE with its grantee `FROM`, and a longer own-domain list stay PASS exit 0."""
    for sql, own in ((_D67_REVOKE_NO_GRANTEE_FROM, 1),
                     (_D67_REVOKE_NO_GRANTEE_FROM_LIST, 2)):
        for files in _d67_revoke_bound_files(sql):
            report = _f12b_run(files)
            assert report.status == FAIL, (sql, files, report.render())
            assert report.exit_code == 1, (sql, files, report.render())
            assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, (
                sql, files, report.render())
            cross = [v for v in report.violations
                     if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
            assert len(cross) == 1 and "bil_invoices" in cross[0].detail, (
                sql, files, report.render())
            counts = _f12b_counts(report)
            assert counts["own"] == own, (sql, files, counts)
            assert counts["other"] == 1, (sql, files, counts)
            assert counts["unattributed"] == 0, (sql, files, counts)

    # Discriminating controls that stay FAIL exit 1.
    for sql, own in (("SELECT a FROM bil_invoices", 0),
                     ("REVOKE SELECT ON mem_roster;\nSELECT a FROM bil_invoices", 1),
                     ("REVOKE SELECT ON mem_roster FROM r\nSELECT a FROM bil_invoices",
                      1)):
        for files in _d67_revoke_bound_files(sql):
            report = _f12b_run(files)
            assert report.status == FAIL, (sql, files, report.render())
            assert report.exit_code == 1, (sql, files, report.render())
            assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, (
                sql, files, report.render())
            counts = _f12b_counts(report)
            assert (counts["own"], counts["other"]) == (own, 1), (sql, files, counts)
    report = _f12b_run({
        "dao.py": 'A = "REVOKE SELECT ON mem_roster"\n'
                  'B = "SELECT a FROM bil_invoices"\n'})
    assert (report.status, report.exit_code) == (FAIL, 1), report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()

    # Positive controls: a REVOKE with its own grantee `FROM` is still clean.
    for sql, own in ((_D67_REVOKE_SINGLE_OWN, 1),
                     ("REVOKE SELECT ON mem_roster, mem_events FROM r", 2),
                     ("REVOKE SELECT ON TABLE mem_roster FROM r", 1),
                     ("REVOKE SELECT ON ONLY mem_roster FROM r", 1),
                     ("SELECT a FROM mem_roster, mem_events", 2),
                     ("SELECT a FROM mem_x JOIN mem_y USING (id)", 2)):
        for files in _d67_revoke_bound_files(sql):
            report = _f12b_run(files)
            assert (report.status, report.exit_code) == (PASS, 0), (
                sql, files, report.render())
            assert report.violations == [], (sql, files, report.render())
            counts = _f12b_counts(report)
            assert counts["own"] == own, (sql, files, counts)
            assert counts["other"] == 0, (sql, files, counts)


def test_gate2_d6_7_revoke_all_tables_in_schema_fails_closed_with_shifted_reason():
    """The one disclosed behavioural delta of bounding the exclusion: `REVOKE ALL ON
    ALL TABLES IN SCHEMA sb FROM r`'s object clause is not a plain table list, so no
    grantee `FROM` is positively computed for it. Before, the unbounded search
    excluded that `FROM`, leaving zero positions and the D6.3 I-1 backstop
    (`MODULE_DEPS_SOURCE_UNINSPECTABLE`); now the `FROM` stays a position, resolves
    to the role `r`, and is D3.2 state 6 (`MODULE_DEPS_TABLE_UNATTRIBUTED`). ERROR
    exit 2 either way -- fail-closed in both, and the reason is what shifts.

    The GRANT spelling has no grantee `FROM` and is unaffected: it keeps its I-1
    refusal (pinned by the unresolved-and-excluded-forms test above)."""
    sql = "REVOKE ALL ON ALL TABLES IN SCHEMA sb FROM r"
    for files in _d67_four_signal_files(sql):
        report = _f12b_run(files)
        assert report.status == ERROR, (files, report.render())
        assert report.exit_code == 2, (files, report.render())
        assert report.codes() == {"MODULE_DEPS_TABLE_UNATTRIBUTED"}, (
            files, report.render())
        assert _f12b_counts(report) == {**_F12B_ZERO, "unattributed": 1}, (
            files, report.render())


# ADR-011 D6.8.9: privilege-list signal suppression corpus.
# Each row must be asserted on both .py and .sql surfaces with exact outcome codes
# and fixture readback proving the intended construct is present.

# Positive controls — must be clean, exit 0 (the narrowing is not vacuous)
_D68_P1 = "GRANT UPDATE ON mem_roster TO r"
_D68_P2 = "GRANT REFERENCES ON mem_roster TO r"
_D68_P3 = "GRANT SELECT ON mem_roster TO r"
_D68_P4 = "GRANT UPDATE (c1, c2) ON mem_roster TO r"
_D68_P5 = "GRANT TRUNCATE, SELECT ON mem_roster TO r"
_D68_P6 = "REVOKE GRANT OPTION FOR UPDATE ON mem_roster FROM r"
_D68_P7 = "SELECT a FROM mem_roster, mem_events"  # standing control
_D68_P8 = "SELECT a FROM mem_x JOIN mem_y USING (id)"  # standing control
_D68_P9 = "GRANT ALL PRIVILEGES ON mem_roster TO r"

# Negative controls — must fail closed with exact code
_D68_N1 = "UPDATE bil_invoices SET x = 1"  # ordinary UPDATE position
_D68_N2 = "CREATE TABLE mem_t (c int REFERENCES bil_invoices)"  # FK
_D68_N3 = "GRANT UPDATE ON bil_invoices TO r"  # disclosed ERROR 2 → FAIL 1
_D68_N4 = "GRANT SELECT, INSERT, UPDATE ON mem_a, bil_invoices TO r"  # inflation resolved
_D68_N5 = "GRANT SELECT\nUPDATE bil_invoices SET x FROM mem_a JOIN mem_b ON mem_q"
_D68_N6 = "GRANT SELECT\nCREATE TABLE mem_t (c int REFERENCES bil_invoices) ON mem_q"
_D68_N7 = "GRANT SELECT, UPDATE ON bil_invoices TO r"
_D68_N8 = "GRANT SELECT (UPDATE bil_invoices) ON mem_t TO r"  # depth-1
_D68_N9 = "GRANT UPDATE ON"  # dangling
_D68_N10 = "GRANT UPDATE ON ALL TABLES IN SCHEMA mem_private TO r"  # I-1 backstop
_D68_N11 = "REVOKE admin FROM r"  # grantee-exclusion non-vacuity
_D68_N12 = "INSERT INTO mem_t SELECT x FROM mem_a, bil_invoices"
_D68_N13 = "DELETE FROM mem_roster USING bil_invoices"
_D68_N14 = 'GRANT UPDATE ON "ON" TO r'  # quoted ON is different table

# Interaction rows (D6.8.7 ordering verification)
_D68_ROW_1A = "REVOKE SELECT ON mem_roster\nSELECT a FROM bil_invoices"
_D68_ROW_3A = "REVOKE UPDATE ON mem_roster\nSELECT a FROM bil_invoices"


def test_gate2_d6_8_positive_controls_own_domain_privilege_grants_clean():
    """ADR-011 D6.8.9 positive controls: own-module GRANT/REVOKE on privilege-name
    signals (UPDATE, REFERENCES, TRUNCATE) are now PASS exit 0, where each was
    ERROR exit 2 on the spurious position resolving to the reserved word ON
    before D6.8. The suppression is not vacuous: each row genuinely carries the
    suppressible token in a positively-computed privilege-list region.

    Fixture readback: each SQL constant is tested both as a .py string literal
    and as a .sql file, and the fixture is read back to prove the intended
    construct is present (the privilege word appears in the statement text)."""
    for sql, privilege_word in ((_D68_P1, "UPDATE"),
                                (_D68_P2, "REFERENCES"),
                                (_D68_P4, "UPDATE"),  # column-privilege
                                (_D68_P5, "TRUNCATE"),  # comma list
                                (_D68_P6, "UPDATE")):  # GRANT OPTION FOR
        for files in _d67_four_signal_files(sql):
            # Fixture readback: the privilege word is in the statement
            file_content = next(iter(files.values()))
            assert privilege_word in file_content, (sql, files)

            report = _f12b_run(files)
            assert report.status == PASS, (sql, files, report.render())
            assert report.exit_code == 0, (sql, files, report.render())
            assert report.violations == [], (sql, files, report.render())
            counts = _f12b_counts(report)
            assert counts["own"] >= 1, (sql, files, counts)
            assert counts["other"] == 0, (sql, files, counts)
            assert counts["unattributed"] == 0, (sql, files, counts)

    # Standing controls must stay PASS (not affected by D6.8)
    for sql in (_D68_P3, _D68_P7, _D68_P8, _D68_P9):
        for files in _d67_four_signal_files(sql):
            report = _f12b_run(files)
            assert report.status == PASS, (sql, files, report.render())
            assert report.exit_code == 0, (sql, files, report.render())


def test_gate2_d6_8_negative_controls_cross_domain_and_errors_fail_closed():
    """ADR-011 D6.8.9 negative controls: cross-domain references remain FAIL exit 1
    (D6.8.5 losslessness), ordinary keyword positions unchanged, dangling/
    unattributed stay ERROR exit 2. Row N3 is the disclosed ERROR 2 → FAIL 1
    movement; row N4 demonstrates inflation and duplication resolved."""
    # N1, N2: ordinary UPDATE/REFERENCES positions (not privilege-list tokens)
    for sql in (_D68_N1, _D68_N2):
        for files in _d67_four_signal_files(sql):
            report = _f12b_run(files)
            assert report.status == FAIL, (sql, files, report.render())
            assert report.exit_code == 1, (sql, files, report.render())
            assert "CROSS_DOMAIN_SQL_IMPORT" in report.codes(), (sql, files)
            assert any("bil_invoices" in v.detail for v in report.violations), (sql, files)

    # N3: disclosed ERROR 2 → FAIL 1 (status dominated by spurious ON is gone)
    for files in _d67_four_signal_files(_D68_N3):
        report = _f12b_run(files)
        assert report.status == FAIL, (_D68_N3, files, report.render())
        assert report.exit_code == 1, (_D68_N3, files, report.render())
        assert "CROSS_DOMAIN_SQL_IMPORT" in report.codes(), (_D68_N3, files)
        assert any("bil_invoices" in v.detail for v in report.violations), (_D68_N3, files)

    # N4: inflation and duplication resolved (2 references, not 4; emitted once)
    for files in _d67_four_signal_files(_D68_N4):
        report = _f12b_run(files)
        assert report.status == FAIL, (_D68_N4, files, report.render())
        assert report.exit_code == 1, (_D68_N4, files, report.render())
        cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
        assert len(cross) == 1, (_D68_N4, files, report.render())  # emitted once, not twice
        counts = _f12b_counts(report)
        assert counts["own"] == 1, (_D68_N4, files, counts)
        assert counts["other"] == 1, (_D68_N4, files, counts)
        assert counts["own"] + counts["other"] == 2, (_D68_N4, files, counts)

    # N5, N6, N8: region-rejection rows (load-bearing vocabulary check)
    for sql in (_D68_N5, _D68_N6, _D68_N8):
        for files in _d67_revoke_bound_files(sql) if "\n" in sql else _d67_four_signal_files(sql):
            report = _f12b_run(files)
            assert report.status == FAIL, (sql, files, report.render())
            assert report.exit_code == 1, (sql, files, report.render())
            assert "bil_invoices" in str(report.violations), (sql, files)

    # N9, N10: dangling/backstop errors
    for sql, expected_code in ((_D68_N9, "MODULE_DEPS_SOURCE_UNINSPECTABLE"),
                               (_D68_N10, "MODULE_DEPS_SOURCE_UNINSPECTABLE"),
                               (_D68_N11, "MODULE_DEPS_TABLE_UNATTRIBUTED")):
        for files in _d67_four_signal_files(sql):
            report = _f12b_run(files)
            assert report.status == ERROR, (sql, files, report.render())
            assert report.exit_code == 2, (sql, files, report.render())
            assert expected_code in report.codes(), (sql, files, report.codes())


def test_gate2_d6_8_interaction_rows_ordering_precondition_satisfied():
    """ADR-011 D6.8.7 interaction rows: row 1A (REVOKE SELECT) must stay non-zero
    after half (1) landed; row 3A (REVOKE UPDATE) must move from ERROR to FAIL
    naming bil_invoices correctly. These prove the ordering constraint: removing
    the accidental backstop moves 3A toward precision, not toward widening."""
    # Row 1A: REVOKE SELECT — must stay FAIL exit 1 (was PASS before half 1)
    for files in _d67_revoke_bound_files(_D68_ROW_1A):
        report = _f12b_run(files)
        assert report.status == FAIL, (_D68_ROW_1A, files, report.render())
        assert report.exit_code == 1, (_D68_ROW_1A, files, report.render())
        assert "CROSS_DOMAIN_SQL_IMPORT" in report.codes(), (_D68_ROW_1A, files)
        assert any("bil_invoices" in v.detail for v in report.violations), (_D68_ROW_1A, files)

    # Row 3A: REVOKE UPDATE — must be FAIL exit 1 naming bil_invoices
    # (was ERROR exit 2 on fake table ON before D6.8)
    for files in _d67_revoke_bound_files(_D68_ROW_3A):
        report = _f12b_run(files)
        assert report.status == FAIL, (_D68_ROW_3A, files, report.render())
        assert report.exit_code == 1, (_D68_ROW_3A, files, report.render())
        assert "CROSS_DOMAIN_SQL_IMPORT" in report.codes(), (_D68_ROW_3A, files)
        assert any("bil_invoices" in v.detail for v in report.violations), (_D68_ROW_3A, files)


def test_gate2_d6_8_suppressible_set_is_derived_intersection_pinned():
    """ADR-011 D6.8.1: the suppressible set must equal the computed intersection of
    PostgreSQL privilege names and table-position signal keywords. This assertion
    pins the derived identity so a future signal keyword that is also a privilege
    name is caught by a failing test rather than silently omitted."""
    from validate_architecture_gates import (
        _PG_PRIVILEGE_VOCABULARY,
        _SUPPRESSIBLE_PRIVILEGE_SIGNALS,
        _compute_suppressible_privilege_signals,
    )

    # The suppressible set must equal the computed intersection
    computed = _compute_suppressible_privilege_signals()
    assert _SUPPRESSIBLE_PRIVILEGE_SIGNALS == computed, \
        f"Expected {computed}, got {_SUPPRESSIBLE_PRIVILEGE_SIGNALS}"

    # Today that intersection is exactly {UPDATE, REFERENCES, TRUNCATE}
    assert _SUPPRESSIBLE_PRIVILEGE_SIGNALS == {"UPDATE", "REFERENCES", "TRUNCATE"}, \
        _SUPPRESSIBLE_PRIVILEGE_SIGNALS

    # ON must NOT be suppressible (two independent reasons: outside region by open
    # upper end, and not a privilege name)
    assert "ON" not in _SUPPRESSIBLE_PRIVILEGE_SIGNALS
    assert "ON" not in _PG_PRIVILEGE_VOCABULARY


def test_gate2_d6_8_region_upper_end_is_open_pinned():
    """ADR-011 D6.8.2/D6.8.6: the privilege-list region's upper end is OPEN at
    on.start(), meaning the object-clause ON is strictly outside every region and
    can never be suppressed. This is a pinned identity assertion because several
    plausible interval mutations (widening the upper end, moving the lower end,
    changing the comparison) are equivalent mutants under the layered defences."""
    from validate_architecture_gates import (
        _GRANT_REVOKE_RE,
        _ON_KEYWORD_RE,
        _privilege_list_region,
    )

    # The object ON must be outside every region

    text = "GRANT UPDATE ON mem_roster TO r"
    for verb in _GRANT_REVOKE_RE.finditer(text):
        region = _privilege_list_region(text, verb)
        assert region is not None, text
        a, b = region
        # The ON keyword match starts where the O appears, not the preceding space
        on_match = _ON_KEYWORD_RE.search(text, verb.end())
        assert on_match is not None
        assert b == on_match.start(), \
            f"Region upper end {b} must equal ON start {on_match.start()}"
        assert b > a, "Region must be non-empty"


# ===== ADR-011 D6.8.9: the finite two-surface corpus, completed =====
#
# The three corpus tests above assert a real subset of D6.8.9 but not the whole of it:
# rows N7, N12, N13 and N14 were defined as constants and never executed, no row
# asserted the D6.8.6 suppression figure at all, and no M-E8..M-E14 mutation control
# existed. The block below closes that, row by row, on both surfaces, with the exact
# outcome code and the suppression count asserted per row.
#
# Every expectation below was MEASURED against this source before it was written down,
# on both surfaces, and every row agreed with ADR-011 D6.8.9's table. Per that table's
# own standing instruction -- "a row whose measured outcome differs from this table is a
# stop-and-report, never a table edit" -- no expectation here was adjusted to fit.


def _d68_corpus_files(sql):
    """`_d67_four_signal_files`/`_d67_revoke_bound_files` for the D6.8.9 corpus, in the
    one `.py` shape that works for every row of it.

    The `.py` literal is always triple-quoted, and that is not cosmetic. Two row classes
    need it: D68-N5/N6 and rows 1A/3A span a newline (a bare newline inside `"..."` is
    not a Python string at all), and **D68-N14's SQL contains the double-quoted
    identifier `"ON"`**, which inside `Q = "..."` terminates the literal and leaves the
    file unparseable. Measured directly on this source: that fixture shape returns ERROR
    exit 2 `MODULE_DEPS_GATE_INPUT_INVALID` for a *Python-syntax* reason, so the row's
    `.py` surface never reached the SQL scanner and the adversarial construct N14 exists
    to test was never examined -- a row that looks asserted and is not. One shape for the
    whole corpus keeps every row's `.py` surface on the AST string-literal path it is
    meant to be exercising."""
    return ({"dao.py": f'SQL = """\n{sql}\n"""\n'}, {"query.sql": f"{sql}\n"})


def _d68_suppression_note(report):
    notes = [n for n in report.notes
             if "ADR-011 D6.8 privilege-list signal suppression" in n]
    assert len(notes) == 1, report.render()
    return notes[0]


def _d68_suppressed(report):
    """The D6.8.6 suppression figure read out of the disclosure note itself, so every
    row below asserts the number a human reader of the report would read -- never a
    separately recomputed figure that could agree with the code while the report lies.
    This is also what kills M-E14's hardcoded-zero half on every row at once."""
    note = _d68_suppression_note(report)
    head = "ADR-011 D6.8 privilege-list signal suppression: "
    assert head in note, note
    return int(note.split(head, 1)[1].split(" ", 1)[0])


def _d68_subjects(report):
    note = _d68_suppression_note(report)
    return int(note.split("tokens, across ", 1)[1].split(" ", 1)[0])


# The two multi-statement region-rejection rows, named once because several controls
# below reference them and they are too long to repeat inline.
_D68_SQL_N5 = "GRANT SELECT\nUPDATE bil_invoices SET x FROM mem_a JOIN mem_b ON mem_q"
_D68_SQL_N6 = ("GRANT SELECT\nCREATE TABLE mem_t (c int REFERENCES bil_invoices) "
               "ON mem_q")

# (row, SQL, status, exit code, exact code set, own, other, unattributed, suppressed)
#
# `own`/`other`/`unattributed` are the D3.2 figures read back out of the D8
# table-reference note; `suppressed` is the D6.8.6 figure read out of the new
# suppression note. The code set is asserted EXACTLY, per D6.8.9's "each asserting an
# exact outcome code".
_D68_CORPUS = (
    # --- Positive controls: clean, exit 0, so the narrowing is not vacuous over-ERRORing
    ("D68-P1", "GRANT UPDATE ON mem_roster TO r", PASS, 0, set(), 1, 0, 0, 1),
    ("D68-P2", "GRANT REFERENCES ON mem_roster TO r", PASS, 0, set(), 1, 0, 0, 1),
    ("D68-P3", "GRANT SELECT ON mem_roster TO r", PASS, 0, set(), 1, 0, 0, 0),
    ("D68-P4", "GRANT UPDATE (c1, c2) ON mem_roster TO r", PASS, 0, set(), 1, 0, 0, 1),
    ("D68-P5", "GRANT TRUNCATE, SELECT ON mem_roster TO r", PASS, 0, set(), 1, 0, 0, 1),
    ("D68-P6", "REVOKE GRANT OPTION FOR UPDATE ON mem_roster FROM r",
     PASS, 0, set(), 1, 0, 0, 1),
    ("D68-P7", "SELECT a FROM mem_roster, mem_events", PASS, 0, set(), 2, 0, 0, 0),
    ("D68-P8", "SELECT a FROM mem_x JOIN mem_y USING (id)", PASS, 0, set(), 2, 0, 0, 0),
    ("D68-P9", "GRANT ALL PRIVILEGES ON mem_roster TO r", PASS, 0, set(), 1, 0, 0, 0),
    # --- Negative controls: fail closed, exact code
    ("D68-N1", "UPDATE bil_invoices SET x = 1",
     FAIL, 1, {"CROSS_DOMAIN_SQL_IMPORT"}, 0, 1, 0, 0),
    ("D68-N2", "CREATE TABLE mem_t (c int REFERENCES bil_invoices)",
     FAIL, 1, {"CROSS_DOMAIN_SQL_IMPORT"}, 1, 1, 0, 0),
    ("D68-N3", "GRANT UPDATE ON bil_invoices TO r",
     FAIL, 1, {"CROSS_DOMAIN_SQL_IMPORT"}, 0, 1, 0, 1),
    ("D68-N4", "GRANT SELECT, INSERT, UPDATE ON mem_a, bil_invoices TO r",
     FAIL, 1, {"CROSS_DOMAIN_SQL_IMPORT"}, 1, 1, 0, 1),
    ("D68-N5", _D68_SQL_N5, FAIL, 1, {"CROSS_DOMAIN_SQL_IMPORT"}, 3, 1, 0, 0),
    ("D68-N6", _D68_SQL_N6, FAIL, 1, {"CROSS_DOMAIN_SQL_IMPORT"}, 2, 1, 0, 0),
    ("D68-N7", "GRANT SELECT, UPDATE ON bil_invoices TO r",
     FAIL, 1, {"CROSS_DOMAIN_SQL_IMPORT"}, 0, 1, 0, 1),
    ("D68-N8", "GRANT SELECT (UPDATE bil_invoices) ON mem_t TO r",
     FAIL, 1, {"CROSS_DOMAIN_SQL_IMPORT"}, 1, 1, 0, 0),
    ("D68-N9", "GRANT UPDATE ON",
     ERROR, 2, {"MODULE_DEPS_SOURCE_UNINSPECTABLE"}, 0, 0, 0, 1),
    ("D68-N10", "GRANT UPDATE ON ALL TABLES IN SCHEMA mem_private TO r",
     ERROR, 2, {"MODULE_DEPS_SOURCE_UNINSPECTABLE"}, 0, 0, 0, 1),
    ("D68-N11", "REVOKE admin FROM r",
     ERROR, 2, {"MODULE_DEPS_TABLE_UNATTRIBUTED"}, 0, 0, 1, 0),
    ("D68-N12", "INSERT INTO mem_t SELECT x FROM mem_a, bil_invoices",
     FAIL, 1, {"CROSS_DOMAIN_SQL_IMPORT"}, 2, 1, 0, 0),
    ("D68-N13", "DELETE FROM mem_roster USING bil_invoices",
     FAIL, 1, {"CROSS_DOMAIN_SQL_IMPORT"}, 1, 1, 0, 0),
    ("D68-N14", 'GRANT UPDATE ON "ON" TO r',
     ERROR, 2, {"MODULE_DEPS_TABLE_UNATTRIBUTED"}, 0, 0, 1, 1),
    # --- The §5 interaction rows
    ("1A", "REVOKE SELECT ON mem_roster\nSELECT a FROM bil_invoices",
     FAIL, 1, {"CROSS_DOMAIN_SQL_IMPORT"}, 1, 1, 0, 0),
    ("3A", "REVOKE UPDATE ON mem_roster\nSELECT a FROM bil_invoices",
     FAIL, 1, {"CROSS_DOMAIN_SQL_IMPORT"}, 1, 1, 0, 1),
)

# The rows whose refusal must name `bil_invoices` specifically, per D6.8.9. Kept apart
# from the table because it is a different claim from the exit code: D68-N3's whole
# point is that the denial names the right subject, not merely that it denies.
_D68_MUST_NAME_BILLING = frozenset({
    "D68-N1", "D68-N2", "D68-N3", "D68-N4", "D68-N5", "D68-N6", "D68-N7", "D68-N8",
    "D68-N12", "D68-N13", "1A", "3A",
})


def test_gate2_d6_8_9_corpus_every_row_on_both_surfaces_with_exact_codes():
    """ADR-011 D6.8.9, in full: P1-P9, N1-N14 and both §5 interaction rows, each on the
    `.py` string-literal surface and the `.sql` file surface, each asserting an exact
    outcome code set, the D3.2 figures, and the D6.8.6 suppression figure.

    Four of these rows (N7, N12, N13, N14) existed only as unexecuted constants before
    this increment, and no row asserted the suppression figure at all. The corpus is
    finite and closed, so "every row" is a checkable claim: the table's row count is
    pinned below against D6.8.9's own 9 + 14 + 2.

    Fixture readback per D6.8.9: each row's SQL is asserted present verbatim in the
    fixture content, and the gate's own `checked` list is asserted to name the file it
    was written to -- so a row cannot pass by testing a fixture the gate never read."""
    assert len(_D68_CORPUS) == 9 + 14 + 2, len(_D68_CORPUS)
    assert len({row[0] for row in _D68_CORPUS}) == len(_D68_CORPUS)

    for (row, sql, status, exit_code, codes,
         own, other, unattributed, suppressed) in _D68_CORPUS:
        for files in _d68_corpus_files(sql):
            name, content = next(iter(files.items()))
            # Fixture readback: the construct this row is about is literally present.
            assert sql in content, (row, name, content)
            report = _f12b_run(files)
            # ...and the gate really read that file, rather than the row passing
            # against a fixture that was never scanned.
            assert f"membership/{name}" in report.checked, (row, name, report.checked)

            assert report.status == status, (row, name, report.render())
            assert report.exit_code == exit_code, (row, name, report.render())
            assert report.codes() == codes, (row, name, report.render())
            counts = _f12b_counts(report)
            assert counts["own"] == own, (row, name, counts)
            assert counts["other"] == other, (row, name, counts)
            assert counts["unattributed"] == unattributed, (row, name, counts)
            # D6.8.6: the suppression figure, on every row including the PASS rows and
            # including the rows that suppress nothing. A row asserting only its exit
            # code cannot tell "suppressed, then refused for the right reason" from
            # "never suppressed at all".
            assert _d68_suppressed(report) == suppressed, (
                row, name, _d68_suppression_note(report))
            assert _d68_subjects(report) == (1 if suppressed else 0), (
                row, name, _d68_suppression_note(report))
            if row in _D68_MUST_NAME_BILLING:
                assert any("bil_invoices" in v.detail for v in report.violations), (
                    row, name, report.render())

    # D68-N4's own extra claim (row 2D's inflation and duplication): the cross-domain
    # code is emitted ONCE, not twice, and the D8 figure is 2 references, not 4.
    for files in _d68_corpus_files("GRANT SELECT, INSERT, UPDATE ON mem_a, bil_invoices TO r"):
        report = _f12b_run(files)
        cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
        assert len(cross) == 1, (files, report.render())
        assert _f12b_total(report) == 2, (files, _f12b_ref_note(report))

    # D68-N9's own extra claim: the dangling refusal survives suppression and still
    # names the object-`ON` signal -- the suppression removed the privilege word, not
    # the statement's real (dangling) target.
    for files in _d68_corpus_files("GRANT UPDATE ON"):
        report = _f12b_run(files)
        assert any("ON signal at offset" in v.detail for v in report.violations), (
            files, report.render())

    # D68-N10's disclosed reason change: zero positions after suppression, refused by
    # the D6.3 I-1 backstop rather than by a state-6 ERROR on the fake table `ON`.
    # Asserted, per D6.8.9's instruction that both disclosed deltas be assertions
    # rather than discoveries.
    for files in _d68_corpus_files("GRANT UPDATE ON ALL TABLES IN SCHEMA mem_private TO r"):
        report = _f12b_run(files)
        assert any("D6.3 I-1 backstop" in v.detail for v in report.violations), (
            files, report.render())

    # D68-N14's own extra claim: a table quoted `"ON"` is a DIFFERENT table under D3.1,
    # is still reached by the object-`ON` signal, and is attributed (to state 6, since
    # no fixture module owns it) rather than suppressed. Losslessness in the
    # adversarial case: the suppression here removed the privilege `UPDATE` only.
    for files in _d68_corpus_files('GRANT UPDATE ON "ON" TO r'):
        report = _f12b_run(files)
        assert any('"ON"' in v.detail for v in report.violations), (
            files, report.render())


# --- ADR-011 D6.8.9's mutation controls M-E8..M-E14 ---------------------------------
#
# Each mutant below is named with the source change it stands for and the row(s)
# D6.8.9 requires it to be killed by. Where a mutant is killable by a *direct* assertion
# on the predicate or the region function, that is what is written -- a unit assertion
# the mutated source fails is a stronger control than a gate-level row, because it names
# the condition rather than its downstream effect, and it cannot be satisfied by some
# other defence in the layered stack accidentally covering for the removed one.


def test_gate2_d6_8_m_e8_suppression_predicate_cannot_be_unconditional():
    """M-E8 -- the suppression predicate hardcoded true (every suppressible token
    suppressed everywhere, no region required). D6.8.9 requires it killed by D68-N1,
    D68-N2, D68-N5, D68-N6 and D68-N8.

    Killed directly at the predicate: each of those rows carries a suppressible keyword
    token (`UPDATE` or `REFERENCES`) that must NOT be suppressed, and the gate-level
    rows in the corpus test above are the same kill through the verdict. A hardcoded-true
    predicate returns True for every one of these and fails here."""
    from validate_architecture_gates import (
        _GRANT_REVOKE_RE,
        _SUPPRESSIBLE_PRIVILEGE_SIGNALS,
        _TABLE_POSITION_SIGNAL_SOURCES,
        _is_privilege_signal_suppressed,
        _privilege_list_region,
    )

    for row, sql in (("D68-N1", "UPDATE bil_invoices SET x = 1"),
                     ("D68-N2", "CREATE TABLE mem_t (c int REFERENCES bil_invoices)"),
                     ("D68-N5", _D68_SQL_N5),
                     ("D68-N6", _D68_SQL_N6),
                     ("D68-N8", "GRANT SELECT (UPDATE bil_invoices) ON mem_t TO r")):
        regions = [r for r in (_privilege_list_region(sql, v)
                               for v in _GRANT_REVOKE_RE.finditer(sql)) if r is not None]
        suppressible_seen = 0
        for source in _TABLE_POSITION_SIGNAL_SOURCES:
            for kw in source(sql):
                if kw.group().upper() not in _SUPPRESSIBLE_PRIVILEGE_SIGNALS:
                    continue
                suppressible_seen += 1
                assert not _is_privilege_signal_suppressed(sql, kw, regions), (
                    row, sql, kw.group(), kw.start(), regions)
        # Non-vacuity: if no suppressible token were present in the row at all, the
        # loop above would assert nothing and M-E8 would survive silently.
        assert suppressible_seen >= 1, (row, sql)


def test_gate2_d6_8_m_e9_region_validity_scan_is_load_bearing():
    """M-E9 -- D6.8.2's region-validity scan removed, so the region is accepted whenever
    an object `ON` is found. D6.8.9 requires it killed by D68-N5 and calls it "the single
    most important mutant: it is the one that reintroduces a false clean".

    Killed at the exact distinguishing condition: for D68-N5 an object `ON` match DOES
    exist (`_grant_revoke_object_on_match` spans the whole unrelated second statement,
    which is the measured hazard), and the region must still be `None` -- rejected by
    check 3, because `bil_invoices`, `mem_a`, `mem_b` and `x` are not privilege names.
    The mutant returns a region here and fails."""
    from validate_architecture_gates import (
        _GRANT_REVOKE_RE,
        _grant_revoke_object_on_match,
        _privilege_list_region,
    )

    sql = _D68_SQL_N5
    verb = next(_GRANT_REVOKE_RE.finditer(sql))
    # The precondition that makes this mutant possible at all: an object `ON` IS found,
    # so an interval-only rule has something to build a region from.
    on = _grant_revoke_object_on_match(sql, verb)
    assert on is not None, sql
    assert on.start() > sql.index("bil_invoices"), (
        "the hazard is that the candidate interval over-spans the second statement")
    # ...and the vocabulary check rejects it anyway.
    assert _privilege_list_region(sql, verb) is None, sql

    # The same rejection for each other non-privilege shape at depth 0, so the check is
    # not passing for this one row by accident.
    for rejected in (_D68_SQL_N6,
                     "GRANT SELECT 1 ON mem_roster TO r",
                     'GRANT "UPDATE" ON mem_roster TO r'):
        verbs = list(_GRANT_REVOKE_RE.finditer(rejected))
        assert verbs, rejected
        assert all(_privilege_list_region(rejected, v) is None for v in verbs), rejected


def test_gate2_d6_8_m_e10_depth_zero_condition_is_load_bearing():
    """M-E10 -- D6.8.3 condition 3 removed, so suppression is permitted at any
    parenthesis depth inside the region. D6.8.9 requires it killed by D68-N8.

    Killed at the condition: in `GRANT SELECT (UPDATE bil_invoices) ON mem_t TO r` the
    region IS positively computed and the `UPDATE` DOES lie wholly inside it -- both of
    the other two predicate conditions hold -- so depth is the only thing standing
    between that signal and a suppression that would lose the real cross-domain
    `bil_invoices`. The mutant suppresses it and fails here."""
    from validate_architecture_gates import (
        _GRANT_REVOKE_RE,
        _TABLE_POSITION_SIGNAL_SOURCES,
        _is_privilege_signal_suppressed,
        _privilege_list_region,
    )

    sql = "GRANT SELECT (UPDATE bil_invoices) ON mem_t TO r"
    verb = next(_GRANT_REVOKE_RE.finditer(sql))
    region = _privilege_list_region(sql, verb)
    # The two conditions that DO hold, asserted so the kill is attributable to depth.
    assert region is not None, sql
    a, b = region
    update = [kw for source in _TABLE_POSITION_SIGNAL_SOURCES for kw in source(sql)
              if kw.group().upper() == "UPDATE"]
    assert len(update) == 1, (sql, update)
    kw = update[0]
    assert a <= kw.start() and kw.end() <= b, (sql, region, kw.span())
    assert sql[kw.start() - 1] == "(", "the UPDATE is inside a column list, i.e. depth 1"
    # ...and depth 0 is what refuses the suppression.
    assert not _is_privilege_signal_suppressed(sql, kw, [region]), (sql, region)


def test_gate2_d6_8_m_e11_uncertainty_branch_retains_never_suppresses():
    """M-E11 -- the uncertainty branch flipped, i.e. suppress when no region is
    positively computed. D6.8.9 requires it killed by D68-N5.

    Killed at D6.8.4's invariant in its own terms: suppression is permitted only ON a
    bound, never FOR WANT OF one. With an empty region list -- which is exactly what
    D68-N5 and every non-GRANT row produce -- the predicate must return False for a
    suppressible token. The flipped mutant returns True and fails."""
    from validate_architecture_gates import (
        _GRANT_REVOKE_RE,
        _TABLE_POSITION_SIGNAL_SOURCES,
        _is_privilege_signal_suppressed,
        _privilege_list_region,
    )

    for sql in ("GRANT SELECT\nUPDATE bil_invoices SET x FROM mem_a JOIN mem_b ON mem_q",
                "UPDATE bil_invoices SET x = 1",
                "CREATE TABLE mem_t (c int REFERENCES bil_invoices)",
                "GRANT UPDATE"):          # dangling verb: no object ON, so no region
        regions = [r for r in (_privilege_list_region(sql, v)
                               for v in _GRANT_REVOKE_RE.finditer(sql)) if r is not None]
        assert regions == [], (sql, regions)
        checked = 0
        for source in _TABLE_POSITION_SIGNAL_SOURCES:
            for kw in source(sql):
                if kw.group().upper() in ("UPDATE", "REFERENCES", "TRUNCATE"):
                    checked += 1
                    assert not _is_privilege_signal_suppressed(sql, kw, regions), (
                        sql, kw.group(), kw.start())
        assert checked >= 1, sql


def test_gate2_d6_8_m_e12_suppression_lives_at_the_merge_point_only():
    """M-E12 -- suppression moved out of the merge point into an individual signal
    source (index 0's wrapper only), so `REFERENCES` (index 1) and `TRUNCATE` (index 3)
    escape it. D6.8.9 requires it killed by D68-P2 and D68-P5.

    Killed structurally, which is stronger than the two gate rows alone: the signal
    sources themselves must STILL YIELD the privilege-word matches -- a source that
    filtered them would be D6.8.6's forbidden second suppression site -- while the merged
    `_table_position_results` stream must have dropped them. A per-source mutant breaks
    the first half for index 0 and the second half for indices 1 and 3.

    This is also the positive form of D6.8.6's normative "may not be implemented inside
    an individual signal source, and may not be duplicated": there is exactly one place
    where the signal set and the position stream disagree."""
    from validate_architecture_gates import (
        _TABLE_POSITION_SIGNAL_SOURCES,
        _table_position_results,
    )

    # (row, SQL, source index that must still yield it, the keyword it must yield)
    for row, sql, index, keyword in (
            ("D68-P1", "GRANT UPDATE ON mem_roster TO r", 0, "UPDATE"),
            ("D68-P2", "GRANT REFERENCES ON mem_roster TO r", 1, "REFERENCES"),
            ("D68-P5", "GRANT TRUNCATE, SELECT ON mem_roster TO r", 3, "TRUNCATE")):
        yielded = [kw.group().upper()
                   for kw in _TABLE_POSITION_SIGNAL_SOURCES[index](sql)]
        assert keyword in yielded, (
            row, sql, index, yielded,
            ("the signal source must still yield the privilege word -- suppressing it "
             "inside the source is D6.8.6's forbidden second site"))
        # ...and the merge point is where it stops being a position.
        stream = _table_position_results(sql)
        assert [p.identifier for p in stream] == ["mem_roster"], (row, sql, stream)


def test_gate2_d6_8_m_e13_region_upper_end_is_not_empty():
    """M-E13 -- the region's upper end narrowed to `verb.end()` (an empty region),
    making D6.8 a silent no-op. D6.8.9 requires it killed by D68-P1, D68-P2, D68-P4,
    D68-P5 and by D68-N4's reference count.

    Killed at the interval: each of those rows must have a NON-EMPTY region whose upper
    end is the object `ON`'s start, and each must actually suppress something (the
    suppression figure in the corpus test above is the same kill read off the report).
    An empty region suppresses nothing, so every one of these rows reverts to its
    pre-D6.8 ERROR and fails."""
    from validate_architecture_gates import (
        _GRANT_REVOKE_RE,
        _grant_revoke_object_on_match,
        _privilege_list_region,
    )

    for row, sql in (("D68-P1", "GRANT UPDATE ON mem_roster TO r"),
                     ("D68-P2", "GRANT REFERENCES ON mem_roster TO r"),
                     ("D68-P4", "GRANT UPDATE (c1, c2) ON mem_roster TO r"),
                     ("D68-P5", "GRANT TRUNCATE, SELECT ON mem_roster TO r"),
                     ("D68-N4",
                      "GRANT SELECT, INSERT, UPDATE ON mem_a, bil_invoices TO r")):
        verb = next(_GRANT_REVOKE_RE.finditer(sql))
        region = _privilege_list_region(sql, verb)
        assert region is not None, (row, sql)
        a, b = region
        assert a == verb.end(), (row, sql, region)
        assert b > a, (row, sql, region, "an empty region makes D6.8 a silent no-op")
        on = _grant_revoke_object_on_match(sql, verb)
        assert on is not None and b == on.start(), (row, sql, region)


_D68_SUPPRESSION_COMPLETE_LABEL = (
    "the per-file scan ran to completion, so this is the run's whole suppression count "
    "-- and it is NOT evidence that the table-reference figure is complete: per ADR-011 "
    "D6.7.5 that figure remains a disclosed lower bound, and a figure this narrowing "
    "moved nearer the truth is still a lower bound"
)


def test_gate2_d6_8_m_e14_suppression_count_and_lower_bound_wording_pinned():
    """M-E14 -- the D6.8.6 suppression counter hardcoded to zero, OR the report's
    lower-bound wording for the table-reference figure replaced by an unconditional
    completeness claim. D6.8.9 requires a report-text assertion, "in the same way M-E6
    already is; no behavioural test covers a note's wording".

    So this is text-level on purpose, on both the `render()` and `asdict()`/`--json`
    surfaces, and on PASS, FAIL and ERROR alike:

      * the counter half is killed by a NONZERO figure on a run that really suppressed
        (every corpus row asserts its own figure too, so the hardcoded zero fails in
        24 more places);
      * the wording half is killed by pinning the exact sentence, written out here as an
        independent literal rather than read back from the module -- so a change to the
        source text fails this file instead of silently agreeing with itself;
      * and D6.8.8's "D6.7.5 is unchanged and unweakened" is asserted on the same runs
        through the existing `_r2n01_assert_lower_bound` pin, because a smaller
        table-reference figure must not come with a stronger claim about it."""
    suppressing = "GRANT UPDATE ON mem_roster TO r"          # PASS, suppresses 1
    cross = "GRANT UPDATE ON bil_invoices TO r"               # FAIL, suppresses 1
    dangling = "GRANT UPDATE ON"                              # ERROR, suppresses 1
    for sql, status in ((suppressing, PASS), (cross, FAIL), (dangling, ERROR)):
        for files in _d68_corpus_files(sql):
            report = _f12b_run(files)
            assert report.status == status, (sql, files, report.render())

            text_note = _d68_suppression_note(report)
            payload = json.loads(report.to_json())
            json_notes = [n for n in payload["notes"]
                          if "ADR-011 D6.8 privilege-list signal suppression" in n]
            assert len(json_notes) == 1, payload
            # One surface corrected and not the other is the M-E6 failure mode again.
            assert text_note == json_notes[0], (text_note, json_notes[0])

            # The counter half: nonzero, and disclosed as such.
            assert _d68_suppressed(report) == 1, (sql, files, text_note)
            assert "0 table-position signal(s) suppressed" not in text_note, text_note

            # The wording half: the exact completed-scan label, and no completeness
            # claim smuggled in beside it.
            assert _D68_SUPPRESSION_COMPLETE_LABEL in text_note, text_note
            assert "complete for this run" not in text_note, text_note
            # ...and none of ADR-011 D5.5's reserved coverage vocabulary, as with every
            # other D8 note in this file.
            for reserved in ("LOWER BOUND", "PARTIAL", "NOT_STARTED", "NOT FINAL",
                             "NOT STARTED"):
                assert reserved not in text_note, (reserved, text_note)

            # Exactly one such line on the rendered surface too.
            rendered = [line for line in report.render().splitlines()
                        if "ADR-011 D6.8 privilege-list signal suppression" in line]
            assert len(rendered) == 1, report.render()

            # D6.8.8: the table-reference figure is STILL a D6.7.5 lower bound on a run
            # in which suppression occurred. A narrowing may not buy a completeness
            # claim, and "no reduction in the reported figure may be presented as
            # evidence of completeness".
            _r2n01_assert_lower_bound(report)


def test_gate2_d6_8_suppression_disclosure_is_aggregated_across_subjects():
    """ADR-011 D6.8.6's "disclosed under D8 on every run including PASS", on the one
    dimension a per-call figure gets wrong: a run scans MANY subjects, so the figure
    must be a run-wide aggregate.

    This is the defect the local reconciliation record names: the count was computed at
    the merge point and assigned to a per-call attribute no report path read, so even
    once read it would have disclosed the LAST subject's suppressions and silently
    dropped every earlier one. Three suppressing subjects of different kinds -- a `.sql`
    file, a `str` literal and a decoded `bytes` literal -- must report 3, not 1."""
    report = _f12b_run({
        "a.py": 'A = """\nGRANT UPDATE ON mem_roster TO r\n"""\n'
                'B = b"GRANT REFERENCES ON mem_roster TO r"\n',
        "b.sql": "GRANT TRUNCATE, SELECT ON mem_roster TO r\n",
    })
    assert (report.status, report.exit_code) == (PASS, 0), report.render()
    assert _d68_suppressed(report) == 3, _d68_suppression_note(report)
    assert _d68_subjects(report) == 3, _d68_suppression_note(report)

    # Two suppressions in ONE subject count 2 signals in 1 subject, so the two figures
    # are not views of one another and neither can be derived from the other.
    one_subject = _f12b_run({
        "c.sql": "GRANT TRUNCATE, UPDATE ON mem_roster TO r\n"})
    assert (one_subject.status, one_subject.exit_code) == (PASS, 0), one_subject.render()
    assert _d68_suppressed(one_subject) == 2, _d68_suppression_note(one_subject)
    assert _d68_subjects(one_subject) == 1, _d68_suppression_note(one_subject)

    # And a run with nothing suppressible discloses an explicit zero rather than nothing
    # at all -- the claim D6.8.6 requires on every run including PASS.
    quiet = _f12b_run({"d.sql": "SELECT a FROM mem_roster\n"})
    assert (quiet.status, quiet.exit_code) == (PASS, 0), quiet.render()
    assert _d68_suppressed(quiet) == 0, _d68_suppression_note(quiet)
    assert _d68_subjects(quiet) == 0, _d68_suppression_note(quiet)


def test_gate2_d6_8_1_suppressible_set_derived_from_the_actual_signal_sources():
    """ADR-011 D6.8.1's first pinned identity, in the form that is NOT a tautology.

    The existing pin above asserts `_SUPPRESSIBLE_PRIVILEGE_SIGNALS ==
    _compute_suppressible_privilege_signals()` -- which cannot fail, because it calls the
    same function that produced the constant, and therefore cannot establish the
    future-proofing D6.8.1 asks for: "a future signal keyword that is also a privilege
    name is caught by a failing test rather than silently omitted".

    Three independent claims here instead:

      1. the set equals an independently re-derived intersection, computed in this file
         from each live source's own declared keyword pattern by a differently-written
         extraction -- so a hand-list reintroduced in the source fails here;
      2. a HYPOTHETICAL extra signal source whose keyword is a privilege name really does
         enter the derived set. This is the claim the tautological pin cannot make, and
         it is the one that matters: it proves the derivation reads the sources rather
         than reciting a constant beside them;
      3. a source that declares no keyword pattern FAILS CLOSED, loudly, instead of
         being silently skipped -- which is how a future family gets caught."""
    import re as _re

    from validate_architecture_gates import (
        _PG_PRIVILEGE_VOCABULARY,
        _SUPPRESSIBLE_PRIVILEGE_SIGNALS,
        _TABLE_POSITION_SIGNAL_SOURCES,
        _compute_suppressible_privilege_signals,
        _signal_source_keyword_tokens,
    )

    # (1) Independent re-derivation: read each source's declared pattern and pull the
    # tokens out with an extraction written differently from the source's own parser.
    independent = set()
    for source in _TABLE_POSITION_SIGNAL_SOURCES:
        pattern = (getattr(source, "signal_keyword_pattern", None)
                   or getattr(source, "__self__", None))
        assert isinstance(pattern, _re.Pattern), source
        body = pattern.pattern.replace(r"\b", "").replace("(?:", "").replace(")", "")
        tokens = [t for t in body.split("|") if t]
        assert tokens, pattern.pattern
        independent.update(t.upper() for t in tokens)
    assert independent == set(_signal_source_keyword_tokens(
        _TABLE_POSITION_SIGNAL_SOURCES)), independent
    assert _SUPPRESSIBLE_PRIVILEGE_SIGNALS == independent & set(
        _PG_PRIVILEGE_VOCABULARY), (_SUPPRESSIBLE_PRIVILEGE_SIGNALS, independent)
    # Today's value, stated so a change to the live sources is visible in review and not
    # merely consistent with itself.
    assert _SUPPRESSIBLE_PRIVILEGE_SIGNALS == {"UPDATE", "REFERENCES", "TRUNCATE"}, \
        _SUPPRESSIBLE_PRIVILEGE_SIGNALS

    # (2) The non-tautological half: a future signal source whose keyword is also a
    # privilege name is PICKED UP, not silently omitted. `DELETE` is a privilege name
    # that no current source yields, so it is absent today and present once a source
    # yields it -- which is precisely the condition the hand-list could not notice.
    assert "DELETE" in _PG_PRIVILEGE_VOCABULARY
    assert "DELETE" not in _SUPPRESSIBLE_PRIVILEGE_SIGNALS
    future = _re.compile(r"\bDELETE\b", _re.IGNORECASE).finditer
    widened = _compute_suppressible_privilege_signals(
        (*_TABLE_POSITION_SIGNAL_SOURCES, future))
    assert widened == _SUPPRESSIBLE_PRIVILEGE_SIGNALS | {"DELETE"}, widened

    # A future source whose keyword is NOT a privilege name changes nothing, so the
    # derivation is the intersection and not merely "every keyword".
    unrelated = _re.compile(r"\bMERGE\b", _re.IGNORECASE).finditer
    assert _compute_suppressible_privilege_signals(
        (*_TABLE_POSITION_SIGNAL_SOURCES, unrelated)) == _SUPPRESSIBLE_PRIVILEGE_SIGNALS

    # (3) Fail closed, loudly, on a source that declares nothing -- the alternative is
    # silent omission from the suppressible set, which is the failure D6.8.1 names.
    def undeclared(text):
        return iter(())

    # `pytest` is deliberately not imported in this file, so the raise is asserted the
    # way the rest of it asserts raises: by catching, and by failing if nothing raised.
    def _refuses(extra, fragment):
        try:
            computed = _compute_suppressible_privilege_signals(
                (*_TABLE_POSITION_SIGNAL_SOURCES, extra))
        except ValueError as exc:
            assert fragment in str(exc), (fragment, str(exc))
            return
        raise AssertionError(
            f"expected ValueError containing {fragment!r}; got {computed!r}")

    _refuses(undeclared, "declares no keyword pattern")
    # ...and on a case-sensitive pattern, whose tokens cannot be compared upper-cased.
    _refuses(_re.compile(r"\bDELETE\b").finditer, "case-sensitive")
    # ...and on a keyword pattern outside the shape the derivation parses, rather than
    # deriving a silently wrong token set from it.
    _refuses(_re.compile(r"DELETE|.*", _re.IGNORECASE).finditer, "shape")


def test_gate2_d6_8_2_object_on_is_never_inside_any_region():
    """ADR-011 D6.8.1/D6.8.2's second pinned identity, stated as the property rather
    than as one row: the object-clause `ON` match is **not a member of any region**, on
    every GRANT/REVOKE row of the corpus that has a region at all.

    Pinned by direct assertion rather than demanded as a mutation kill, because D6.8.9
    records that several plausible interval mutations (widening the upper end to
    end-of-text, moving the lower end to 0, making the upper comparison
    `kw.start() <= b`) are EQUIVALENT MUTANTS under the layered defences and cannot be
    killed by any corpus row.

    Both of D6.8.1's two independent reasons are asserted, since it requires that
    "both reasons must hold in the implementation; neither alone is relied upon": the
    `ON` is outside the region by the open upper end, AND `ON` is not in the privilege
    vocabulary so it is not in the derived suppressible set."""
    from validate_architecture_gates import (
        _GRANT_REVOKE_RE,
        _PG_PRIVILEGE_VOCABULARY,
        _SUPPRESSIBLE_PRIVILEGE_SIGNALS,
        _TABLE_POSITION_SIGNAL_SOURCES,
        _grant_revoke_object_on_match,
        _is_privilege_signal_suppressed,
        _privilege_list_region,
    )

    # Reason two, independent of any interval: `ON` is not a privilege name.
    assert "ON" not in _PG_PRIVILEGE_VOCABULARY
    assert "ON" not in _SUPPRESSIBLE_PRIVILEGE_SIGNALS

    # Reason one, over every corpus row that computes a region: the object `ON` lies
    # strictly outside it, so no `ON` signal is ever a suppression candidate.
    regioned = 0
    for _row, sql, *_rest in _D68_CORPUS:
        regions = []
        for verb in _GRANT_REVOKE_RE.finditer(sql):
            region = _privilege_list_region(sql, verb)
            if region is None:
                continue
            regioned += 1
            a, b = region
            on = _grant_revoke_object_on_match(sql, verb)
            assert on is not None, sql
            assert b == on.start(), (sql, region, on.span())
            # Open upper end: the `ON` match is NOT wholly within [a, b).
            assert not (a <= on.start() and on.end() <= b), (sql, region, on.span())
            regions.append(region)
        # ...and the object `ON` signals the stream actually carries are not suppressed.
        for source in _TABLE_POSITION_SIGNAL_SOURCES:
            for kw in source(sql):
                if kw.group().upper() == "ON":
                    assert not _is_privilege_signal_suppressed(sql, kw, regions), (
                        sql, kw.span(), regions)
    # Non-vacuity: the loop really did exercise regions.
    assert regioned >= 9, regioned


def test_scn095_bidirectional_pair_permitted_synchronous_direction_passes():
    for from_dom, to_dom in _PINNED_PAIRS:
        def build(modules_dir):
            _md_module(modules_dir, "upstream", {
                "service.py": "from app.modules.downstream.interface import call\n",
            })
            _md_module(modules_dir, "downstream", {
                "interface.py": "def call():\n    return None\n",
            })

        modules = {
            "upstream": _md_entry(from_dom, ["upstream_"], ["app.modules.upstream.interface"]),
            "downstream": _md_entry(to_dom, ["downstream_"],
                                    ["app.modules.downstream.interface"]),
        }
        report = _md_run(modules, build)
        assert report.status == PASS, (from_dom, to_dom, report.render())
        assert report.checked, (from_dom, to_dom)


def test_scn096_bidirectional_pair_reverse_edge_denied():
    for from_dom, to_dom in _PINNED_PAIRS:
        def build(modules_dir):
            _md_module(modules_dir, "upstream", {
                "interface.py": "def call():\n    return None\n",
            })
            _md_module(modules_dir, "downstream", {
                "service.py": "from app.modules.upstream.interface import call\n",
            })

        modules = {
            "upstream": _md_entry(from_dom, ["upstream_"], ["app.modules.upstream.interface"]),
            "downstream": _md_entry(to_dom, ["downstream_"],
                                    ["app.modules.downstream.interface"]),
        }
        report = _md_run(modules, build)
        assert report.status == FAIL, (from_dom, to_dom, report.render())
        assert report.exit_code == 1
        rev = [v for v in report.violations if v.code == "REVERSE_EDGE_NOT_EVENT_DRIVEN"]
        assert rev, (from_dom, to_dom, report.render())
        assert any(from_dom in v.detail and to_dom in v.detail for v in rev), (
            from_dom, to_dom, report.render())


def test_sixthree_pair_private_internal_import_denied_both_directions():
    # Rule 2 precedence: the §6.3 exception only licenses the *declared application
    # interface*, never private internals — in either direction of the pair.
    from_dom, to_dom = _PINNED_PAIRS[0]

    def build_forward(modules_dir):
        _md_module(modules_dir, "upstream", {
            "service.py": "from app.modules.downstream.models import Thing\n",
        })
        _md_module(modules_dir, "downstream", {
            "interface.py": "def call():\n    return None\n",
            "models.py": "class Thing:\n    pass\n",
        })

    modules = {
        "upstream": _md_entry(from_dom, ["upstream_"], ["app.modules.upstream.interface"]),
        "downstream": _md_entry(to_dom, ["downstream_"], ["app.modules.downstream.interface"]),
    }
    report = _md_run(modules, build_forward)
    assert report.status == FAIL, report.render()
    assert any(v.code == "CROSS_DOMAIN_SQL_IMPORT" for v in report.violations), report.render()

    def build_reverse(modules_dir):
        _md_module(modules_dir, "upstream", {
            "interface.py": "def call():\n    return None\n",
            "models.py": "class Thing:\n    pass\n",
        })
        _md_module(modules_dir, "downstream", {
            "service.py": "from app.modules.upstream.models import Thing\n",
        })

    report2 = _md_run(modules, build_reverse)
    assert report2.status == FAIL, report2.render()
    assert any(v.code == "CROSS_DOMAIN_SQL_IMPORT" for v in report2.violations), report2.render()


def test_relative_import_resolves_identically_to_absolute():
    def build(modules_dir):
        _md_module(modules_dir, "membership", {
            # file package is app.modules.membership; level=2 resolves to app.modules,
            # then + billing.models -> app.modules.billing.models (private, denied).
            "handlers.py": "from ..billing.models import Invoice\n",
        })
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge():\n    return None\n",
            "models.py": "class Invoice:\n    pass\n",
        })

    modules = {
        "membership": _md_entry("MEM-01", ["membership_"],
                                ["app.modules.membership.interface"]),
        "billing": _md_entry("BIL-02", ["billing_"], ["app.modules.billing.interface"]),
    }
    report = _md_run(modules, build)
    assert report.status == FAIL, report.render()
    cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    assert cross, report.render()
    assert any("membership" in f"{v.subject} {v.detail}" and
              "billing" in f"{v.subject} {v.detail}" for v in cross), report.render()


def test_shared_import_allowed_but_shared_importing_domain_denied():
    def build_ok(modules_dir):
        _md_module(modules_dir, "billing", {
            "service.py": "from app.modules._shared.tenant_context import get_tenant\n",
        })
        _md_module(modules_dir, "_shared", {
            "tenant_context.py": "def get_tenant():\n    return None\n",
        })

    modules = {"billing": _md_entry("BIL-02", ["billing_"], ["app.modules.billing.interface"])}
    report = _md_run(modules, build_ok)
    assert report.status == PASS, report.render()
    assert report.checked

    def build_denied(modules_dir):
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge():\n    return None\n",
            "models.py": "class Invoice:\n    pass\n",
        })
        _md_module(modules_dir, "_shared", {
            "util.py": "from app.modules.billing.models import Invoice\n",
        })

    report2 = _md_run(modules, build_denied)
    assert report2.status == FAIL, report2.render()
    assert any(v.code == "CROSS_DOMAIN_SQL_IMPORT" for v in report2.violations), report2.render()


def test_sql_file_cross_module_reference_is_flagged():
    def build(modules_dir):
        _md_module(modules_dir, "membership", {
            "reports.sql": "SELECT id FROM billing_invoice\n",
        })
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge():\n    return None\n",
        })

    modules = {
        "membership": _md_entry("MEM-01", ["membership_"],
                                ["app.modules.membership.interface"]),
        "billing": _md_entry("BIL-02", ["billing_"], ["app.modules.billing.interface"]),
    }
    report = _md_run(modules, build)
    assert report.status == FAIL, report.render()
    assert any(v.code == "CROSS_DOMAIN_SQL_IMPORT" for v in report.violations), report.render()


def test_unowned_table_reference_is_now_an_unattributed_error_not_a_benign_note():
    # GATE2-R1-D1A-SCANNER-WIRING-2026-10-05: this test previously asserted the
    # pre-ADR-011 behaviour ("unowned ⇒ disclosed note, not flagged"), which D3.2
    # state 6 explicitly inverts -- an identifier no module owns is now ERROR
    # MODULE_DEPS_TABLE_UNATTRIBUTED, never a silent PASS. Renamed and rewritten
    # rather than deleted, so the history of what this gate used to do before
    # ADR-011 stays visible in version control.
    def build(modules_dir):
        _md_module(modules_dir, "membership", {
            "reports.sql": "SELECT id FROM unowned_legacy_table\n",
        })

    report = _md_run(_md_base_modules(), build)
    assert report.status == ERROR, report.render()
    assert report.codes() == {"MODULE_DEPS_TABLE_UNATTRIBUTED"}, report.render()
    assert any("unowned_legacy_table" in v.detail for v in report.violations), report.render()


# --- GATE2-R1-D1A-SCANNER-WIRING-2026-10-05: `attribute_table_identifier` wired
# into the live `_scan_sql_text` path. Each test below drives the gate through a
# real `run_module_deps_gate` fixture tree (not a direct `attribute_table_identifier`
# call) to lock in the WIRING itself, distinct from the pure-function semantics the
# prior D1a increment's `test_attr_*` tests already lock in further below.


def test_wiring_schema_qualified_other_module_table_is_cross_domain_import():
    def build(modules_dir):
        _md_module(modules_dir, "membership", {
            "reports.sql": "SELECT id FROM public.bil_invoices\n",
        })
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge():\n    return None\n",
        })

    modules = {
        "membership": _md_entry("MEM-01", ["membership_"],
                                ["app.modules.membership.interface"]),
        "billing": _md_entry("BIL-02", ["bil_"], ["app.modules.billing.interface"]),
    }
    report = _md_run(modules, build)
    assert report.status == FAIL, report.render()
    cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    assert cross, report.render()
    assert any("bil_invoices" in v.detail for v in cross), report.render()


def test_wiring_case_variation_resolves_identically_to_lower_case():
    # Same construct as the test above, mixed/upper case throughout (schema,
    # keyword-adjacent identifier) -- ADR-011 D3.1 casefolds every unquoted
    # segment, so this must reach the identical CROSS_DOMAIN_SQL_IMPORT outcome.
    def build(modules_dir):
        _md_module(modules_dir, "membership", {
            "reports.sql": "SELECT id FROM Public.BIL_Invoices\n",
        })
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge():\n    return None\n",
        })

    modules = {
        "membership": _md_entry("MEM-01", ["membership_"],
                                ["app.modules.membership.interface"]),
        "billing": _md_entry("BIL-02", ["bil_"], ["app.modules.billing.interface"]),
    }
    report = _md_run(modules, build)
    assert report.status == FAIL, report.render()
    assert any(v.code == "CROSS_DOMAIN_SQL_IMPORT" for v in report.violations), report.render()


def test_wiring_known_external_table_is_clean_and_feasible():
    def build(modules_dir):
        _md_module(modules_dir, "membership", {
            "reports.sql": "SELECT id FROM legacy_table\n",
        })

    modules = {
        "membership": {
            "domain": "MEM-01",
            "owned_table_prefixes": ["membership_"],
            "public_interfaces": ["app.modules.membership.interface"],
            "external_table_references": ["legacy_table"],
        },
    }
    report = _md_run(modules, build)
    assert report.status == PASS, report.render()
    assert not report.violations, report.render()


def test_wiring_own_module_table_is_clean_and_feasible():
    def build(modules_dir):
        _md_module(modules_dir, "membership", {
            "reports.sql": "SELECT id FROM membership_roster\n",
        })

    report = _md_run(_md_base_modules(), build)
    assert report.status == PASS, report.render()
    assert not report.violations, report.render()


def test_wiring_unknown_identifier_is_unattributed_error_live():
    # A second, independently-named live-wiring lock for D3.2 state 6, distinct
    # from `test_unowned_table_reference_is_now_an_unattributed_error_not_a_benign_note`
    # above (which preserves the pre-ADR-011 test's history) -- purpose-built for
    # this wiring increment's own acceptance bar.
    def build(modules_dir):
        _md_module(modules_dir, "membership", {
            "reports.sql": "SELECT id FROM nobody_owns_this\n",
        })

    report = _md_run(_md_base_modules(), build)
    assert report.status == ERROR, report.render()
    assert report.codes() == {"MODULE_DEPS_TABLE_UNATTRIBUTED"}, report.render()
    assert any("nobody_owns_this" in v.detail for v in report.violations), report.render()


def test_wiring_no_regression_previously_clean_input_stays_clean():
    # Locks test_scn006's own-schema-and-approved-interface PASS shape against
    # this increment's rewrite of `_scan_sql_text`'s internals (`_resolve_owner`
    # replaced by `attribute_table_identifier`) -- the wiring change must not
    # change this pre-existing, already-passing outcome.
    def build(modules_dir):
        _md_module(modules_dir, "membership", {
            "service.py": (
                "from app.modules.membership.models import Member\n"
                "from app.modules.billing.interface import preview_charge\n"
                "\n\n"
                "def summarize(member):\n"
                "    preview_charge(member)\n"
                "    return member\n"
            ),
            "models.py": "class Member:\n    pass\n",
            "repo.sql": "SELECT id FROM membership_roster WHERE active = true\n",
        })
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge(member):\n    return None\n",
            "models.py": "class Invoice:\n    pass\n",
        })

    modules = {
        "membership": _md_entry("MEM-01", ["membership_"],
                                ["app.modules.membership.interface"]),
        "billing": _md_entry("BIL-02", ["billing_"], ["app.modules.billing.interface"]),
    }
    report = _md_run(modules, build)
    assert report.status == PASS, report.render()
    assert report.checked


def test_wiring_default_schema_from_manifest_reaches_attribution_call():
    # ADR-011 D3.3 rule 2: an identifier qualified by a *custom* default_schema
    # (not the implicit "public") must strip identically to a bare identifier.
    # Driven through `load_module_manifest` (not a hand-built `default_schema`
    # argument), so this fails if a future change re-hardcodes "public" anywhere
    # between manifest parsing and the attribution call.
    def build(modules_dir):
        _md_module(modules_dir, "membership", {
            "reports.sql": "SELECT id FROM sm.membership_roster\n",
        })

    manifest = {"version": 1, "default_schema": "sm", "modules": _md_base_modules()}
    report = _md_run(None, build, manifest=manifest)
    assert report.status == PASS, report.render()
    assert not report.violations, report.render()

    # Control: the identical qualifier against the *implicit* default_schema
    # ("public") must NOT strip -- "sm" is not owned as a schema by anyone, so
    # it is unattributed rather than silently resolving by prefix regardless.
    manifest_implicit_default = {"version": 1, "modules": _md_base_modules()}
    report2 = _md_run(None, build, manifest=manifest_implicit_default)
    assert report2.status == ERROR, report2.render()
    assert report2.codes() == {"MODULE_DEPS_TABLE_UNATTRIBUTED"}, report2.render()


def test_wiring_quoted_identifier_extracted_and_attributed_correctly():
    # GATE2-R1-D1A-QUOTED-LEXER-2026-10-05: this test previously encoded the
    # PRE-LEXER regex gap under the name
    # `test_wiring_quoted_identifier_disclosed_regex_gap_but_attribution_is_
    # correct` -- at that time the live `_TABLE_IDENT_RE`/`_dangling_keywords`
    # regex could not extract a double-quoted identifier at all, so the
    # live-scan control below reached `MODULE_DEPS_SOURCE_UNINSPECTABLE`
    # before `attribute_table_identifier` was ever reached with one. The
    # explicit character-by-character lexer built this increment
    # (`_lex_quoted_segment`/`_lex_dotted_identifier`, wired through
    # `_extract_table_identifiers`) closes that extraction gap, so the
    # live-scan control now correctly reaches a clean PASS instead. Renamed
    # rather than deleted, so the history of the pre-lexer gap stays visible
    # in version control. The two direct `attribute_table_identifier` calls
    # below are unchanged from the original test -- the attribution LOGIC was
    # already correct before this increment; only extraction was the gap.
    def build(modules_dir):
        _md_module(modules_dir, "membership", {"interface.py": "def x():\n    return None\n"})

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        modules_dir = _md_tree(root)
        build(modules_dir)
        manifest_path = root / "module-manifest.json"
        _md_write_manifest(modules_dir, manifest_path, _md_base_modules())
        modules, default_schema = load_module_manifest(manifest_path, "app.modules", modules_dir)

    out_upper = attribute_table_identifier('"MEMBERSHIP_ROSTER"', modules, "membership",
                                           default_schema)
    assert out_upper.state == ATTR_UNATTRIBUTED, out_upper  # case preserved, no owner matches

    out_lower = attribute_table_identifier('"membership_roster"', modules, "membership",
                                           default_schema)
    assert out_lower.state == ATTR_OWNED, out_lower
    assert out_lower.owner == "membership", out_lower

    # Live-scan control, confirming the CLOSED gap by execution rather than
    # merely asserting it in prose: the quoted identifier is now extracted
    # from the real source text and correctly attributed to its owning
    # module, so the scan is a clean PASS with zero violations.
    def build_live(modules_dir):
        _md_module(modules_dir, "membership", {
            "reports.sql": 'SELECT id FROM "membership_roster"\n',
        })

    report = _md_run(_md_base_modules(), build_live)
    assert report.status == PASS, report.render()
    assert not report.violations, report.render()


def test_wiring_quoted_cross_domain_reference_is_cross_domain_import():
    # A schema-qualified reference whose table segment is double-quoted (here
    # already lowercase, so quoting alone changes nothing about which
    # identifier it names) still resolves into another module's owned prefix
    # and is CROSS_DOMAIN_SQL_IMPORT, exactly as the unquoted form would be --
    # the quoted-lexer extraction path and the unquoted path converge on the
    # same attribution outcome.
    def build(modules_dir):
        _md_module(modules_dir, "membership", {
            "reports.sql": 'SELECT id FROM public."bil_invoices"\n',
        })
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge():\n    return None\n",
        })

    modules = {
        "membership": _md_entry("MEM-01", ["membership_"],
                                ["app.modules.membership.interface"]),
        "billing": _md_entry("BIL-02", ["bil_"], ["app.modules.billing.interface"]),
    }
    report = _md_run(modules, build)
    assert report.status == FAIL, report.render()
    cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    assert cross, report.render()
    assert any("bil_invoices" in v.detail for v in cross), report.render()


def test_wiring_quoted_unknown_identifier_is_unattributed_error():
    # A double-quoted identifier whose exact-case form no module owns
    # (ADR-011 D3.1: case is preserved, not casefolded, for a quoted segment)
    # reaches D3.2 state 6 -- ERROR, not a silent pass -- exactly like an
    # unquoted unowned reference does.
    def build(modules_dir):
        _md_module(modules_dir, "membership", {
            "reports.sql": 'SELECT id FROM "UNKNOWN_TABLE"\n',
        })

    report = _md_run(_md_base_modules(), build)
    assert report.status == ERROR, report.render()
    assert report.codes() == {"MODULE_DEPS_TABLE_UNATTRIBUTED"}, report.render()
    assert any("UNKNOWN_TABLE" in v.detail for v in report.violations), report.render()


def test_wiring_three_part_qualified_name_is_unattributed_error():
    # ADR-011 D3.3 rule 1: a 3+-part dotted name is outside the ownership
    # model entirely -- ERROR, never resolved by matching only the first two
    # parts (the prior regex's silent truncation to 2 parts, now closed by
    # the explicit lexer capturing the identifier in full).
    def build(modules_dir):
        _md_module(modules_dir, "membership", {
            "reports.sql": "SELECT id FROM some_db.public.bil_invoices\n",
        })

    report = _md_run(_md_base_modules(), build)
    assert report.status == ERROR, report.render()
    assert report.codes() == {"MODULE_DEPS_TABLE_UNATTRIBUTED"}, report.render()


def test_wiring_mixed_quoted_schema_unquoted_table_is_cross_domain_import():
    # The opposite mix from the cross-domain test above: the schema segment
    # is double-quoted (exact-case match to default_schema "public") and the
    # table segment is bare/unquoted. Default-schema stripping (ADR-011 D3.3
    # rule 2) must still apply when the schema segment itself arrives quoted,
    # so this must reach the same CROSS_DOMAIN_SQL_IMPORT outcome.
    def build(modules_dir):
        _md_module(modules_dir, "membership", {
            "reports.sql": 'SELECT id FROM "public".bil_invoices\n',
        })
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge():\n    return None\n",
        })

    modules = {
        "membership": _md_entry("MEM-01", ["membership_"],
                                ["app.modules.membership.interface"]),
        "billing": _md_entry("BIL-02", ["bil_"], ["app.modules.billing.interface"]),
    }
    report = _md_run(modules, build)
    assert report.status == FAIL, report.render()
    cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    assert cross, report.render()
    assert any("bil_invoices" in v.detail for v in cross), report.render()


def test_schema_qualified_ownership_resolution():
    # Schema-qualified resolution wins even when the table-prefix list would not
    # otherwise match this module's own tables (rule 5: owned_schemas first).
    def build_own(modules_dir):
        _md_module(modules_dir, "membership", {
            "reports.sql": "SELECT id FROM crm.roster\n",
        })

    modules_own = {
        "membership": _md_entry("MEM-01", ["unrelated_"], ["app.modules.membership.interface"],
                                schemas=["crm"]),
    }
    report = _md_run(modules_own, build_own)
    assert report.status == PASS, report.render()
    assert report.checked
    assert not any(v.code == "CROSS_DOMAIN_SQL_IMPORT" for v in report.violations)

    # A schema-qualified reference into a DIFFERENT module's declared schema is denied.
    def build_cross(modules_dir):
        _md_module(modules_dir, "membership", {
            "reports.sql": "SELECT id FROM bil_schema.invoice\n",
        })
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge():\n    return None\n",
        })

    modules_cross = {
        "membership": _md_entry("MEM-01", ["membership_"],
                                ["app.modules.membership.interface"], schemas=["mem_schema"]),
        "billing": _md_entry("BIL-02", ["billing_"], ["app.modules.billing.interface"],
                             schemas=["bil_schema"]),
    }
    report2 = _md_run(modules_cross, build_cross)
    assert report2.status == FAIL, report2.render()
    assert any(v.code == "CROSS_DOMAIN_SQL_IMPORT" for v in report2.violations), report2.render()


def test_longest_prefix_ownership_resolution_same_module_nested_prefixes():
    # Settled by GATE2-ARCHITECTURE-DECISION-2026-10-05.md Verdict C (not an unconfirmed
    # assumption): one module owning two nested prefixes ("cal_" and "cal_event_") is the
    # only shape that is ACCEPTED under the "owned" invariant, and the only shape under
    # which rule 5's "longest matching owned_table_prefixes" resolution is ever a live
    # choice — two declared prefixes can only both match the same identifier if one is a
    # literal string-prefix of the other, and Verdict C rejects that shape globally except
    # when both prefixes belong to the same module (where the true owner is identical
    # either way, so attribution stays unambiguous). This test exercises that accepted
    # shape; a naive implementation could still get it wrong (e.g. by treating the shorter
    # prefix's non-match as "unowned"). The cross-module case is independently covered,
    # and rejected with no exception path, by test_rule7_prefix_that_is_a_prefix_of_another_is_error
    # below; the exact-duplicate case is covered by
    # test_rule7_duplicate_owned_table_prefixes_entry_is_error.
    def build(modules_dir):
        _md_module(modules_dir, "calendar", {
            "reports.sql": "SELECT id FROM cal_event_slots\n",
        })

    modules = {
        "calendar": _md_entry("CAL-01", ["cal_", "cal_event_"],
                              ["app.modules.calendar.interface"]),
    }
    report = _md_run(modules, build)
    assert report.status == PASS, report.render()
    assert report.checked
    assert not any(v.code == "CROSS_DOMAIN_SQL_IMPORT" for v in report.violations)


def test_rule7_duplicate_owned_table_prefixes_entry_is_error():
    # Verdict C case 3: the exact same prefix declared twice by one module carries no
    # ownership information and is malformed input, distinct from case 1 (nested, accepted)
    # and case 2 (cross-module overlap, rejected with no exception path).
    modules = {
        "calendar": _md_entry("CAL-01", ["cal_", "cal_"], ["app.modules.calendar.interface"]),
    }

    def build(modules_dir):
        _md_module(modules_dir, "calendar", {
            "interface.py": "def x():\n    return None\n",
        })

    report = _md_run(modules, build)
    _assert_md_input_error(report, "duplicate owned_table_prefixes entry")
    assert any(
        "duplicate owned_table_prefixes entry" in v.detail
        and "'calendar'" in v.detail and "'cal_'" in v.detail
        for v in report.violations
    ), report.render()


def test_longest_prefix_cross_module_control_longer_prefix_attributed_correctly():
    """Cross-module control for rule 5's "longest matching owned_table_prefixes"
    resolution. This is deliberately NOT a test of two different modules' prefixes
    racing for the same identifier — Verdict C's rule 7 rejects that shape (overlapping
    prefixes across modules) at manifest-parse time with no exception path, so that
    ambiguous case can never reach runtime resolution at all
    (see test_rule7_prefix_that_is_a_prefix_of_another_is_error). What remains reachable,
    and is exercised here, is the non-ambiguous case: a module-owned prefix that happens
    to be longer than an unrelated, non-overlapping prefix owned by a different module
    still resolves to its true owner, not to the other module and not as unowned."""
    def build(modules_dir):
        _md_module(modules_dir, "membership", {
            "reports.sql": "SELECT id FROM billing_order_items\n",
        })
        _md_module(modules_dir, "billing", {
            "interface.py": "def x():\n    return None\n",
        })

    modules = {
        "membership": _md_entry("MEM-01", ["mem_"], ["app.modules.membership.interface"]),
        "billing": _md_entry("BIL-02", ["billing_order_"],
                             ["app.modules.billing.interface"]),
    }
    report = _md_run(modules, build)
    assert report.status == FAIL, report.render()
    assert any(
        v.code == "CROSS_DOMAIN_SQL_IMPORT" and v.subject == "membership -> billing"
        for v in report.violations
    ), report.render()


# --- rule 6: MODULE_DEPS_SOURCE_UNINSPECTABLE ------------------------------------


def test_rule6_dynamic_import_calls_are_uninspectable_errors():
    for label, call in (
        ("__import__", "__import__('app.modules.billing')\n"),
        ("importlib.import_module",
         "import importlib\nimportlib.import_module('app.modules.billing')\n"),
    ):
        def build(modules_dir, call=call):
            _md_module(modules_dir, "membership", {"service.py": call})
            _md_module(modules_dir, "billing", {
                "interface.py": "def x():\n    return None\n",
            })

        modules = {
            "membership": _md_entry("MEM-01", ["membership_"],
                                    ["app.modules.membership.interface"]),
            "billing": _md_entry("BIL-02", ["billing_"], ["app.modules.billing.interface"]),
        }
        report = _md_run(modules, build)
        assert report.status == ERROR, (label, report.render())
        assert report.codes() == {"MODULE_DEPS_SOURCE_UNINSPECTABLE"}, (label, report.render())


def test_rule6_imported_import_module_callable_is_uninspectable_error():
    """R1-F05: `from importlib import import_module` -- and its `as` alias -- used to
    be a silent exit-0 PASS, because the dynamic-import set was bound to the literal
    receiver name `importlib`. The bound name now comes from the import statement
    itself, resolved per file before the node walk."""
    for label, src in (
        ("from importlib import import_module",
         "from importlib import import_module\nimport_module('app.modules.billing')\n"),
        ("from importlib import import_module as <alias>",
         "from importlib import import_module as _load\n_load('app.modules.billing')\n"),
        ("call lexically above the import",
         ("def go():\n    return import_module('app.modules.billing')\n"
          "from importlib import import_module\n")),
        ("alias shadowing the receiver name itself",
         ("from importlib import import_module as importlib\n"
          "importlib('app.modules.billing')\n")),
    ):
        def build(modules_dir, src=src):
            _md_module(modules_dir, "membership", {"service.py": src})

        report = _md_run(_md_base_modules(), build)
        assert report.status == ERROR, (label, report.render())
        assert report.codes() == {"MODULE_DEPS_SOURCE_UNINSPECTABLE"}, (label, report.render())


def test_rule6_unimported_import_module_name_is_not_a_dynamic_import():
    """The discriminating negatives for the test above: the gate must key on the
    actual `importlib` binding, not on a called name that merely reads like one,
    and must not leak one file's binding into another."""
    for label, src in (
        ("unrelated local def named import_module",
         "def import_module(name):\n    return name\n\n\nimport_module('roster')\n"),
        ("unrelated local def named like the alias",
         "def _load(name):\n    return name\n\n\n_load('roster')\n"),
        ("relative import of a local importlib shim",
         "from .importlib import import_module\n\nimport_module('roster')\n"),
        ("importlib's import_module bound but never called",
         "from importlib import import_module\n"),
        ("a different importlib name entirely",
         "from importlib import metadata\n\nmetadata.version('veyro')\n"),
    ):
        def build(modules_dir, src=src):
            _md_module(modules_dir, "membership", {
                "service.py": src,
                "importlib.py": "def import_module(name):\n    return name\n",
            })

        report = _md_run(_md_base_modules(), build)
        assert report.status == PASS, (label, report.render())
        assert report.violations == [], (label, report.render())

    def build_two_files(modules_dir):
        # The binding is per file: `binder.py` importing it does not make
        # `other.py`'s own same-named callable a dynamic import.
        _md_module(modules_dir, "membership", {
            "binder.py": "from importlib import import_module\n",
            "other.py": "def import_module(name):\n    return name\n\n\nimport_module('x')\n",
        })

    report = _md_run(_md_base_modules(), build_two_files)
    assert report.status == PASS, report.render()
    assert report.violations == [], report.render()


def test_rule6_builtins_dunder_import_is_uninspectable_error():
    """R1-F05 (`builtins.__import__` idiom): `import builtins` followed by
    `builtins.__import__(...)` used to be a silent exit-0 PASS -- the attribute
    branch recognised the `__import__` attr only on the literal receiver name
    `importlib`. The receiver now comes from the `import builtins [as ...]`
    statement itself, resolved per file before the node walk."""
    for label, src in (
        ("import builtins",
         "import builtins\nbuiltins.__import__('app.modules.billing')\n"),
        ("import builtins as <alias>",
         "import builtins as _b\n_b.__import__('app.modules.billing')\n"),
        ("call lexically above the import",
         ("def go():\n    return builtins.__import__('app.modules.billing')\n"
          "import builtins\n")),
    ):
        def build(modules_dir, src=src):
            _md_module(modules_dir, "membership", {"service.py": src})

        report = _md_run(_md_base_modules(), build)
        assert report.status == ERROR, (label, report.render())
        assert report.exit_code == 2, (label, report.render())
        assert report.codes() == {"MODULE_DEPS_SOURCE_UNINSPECTABLE"}, (label, report.render())


def test_rule6_unimported_builtins_receiver_is_not_a_dynamic_import():
    """The discriminating negatives for the test above: the gate must key on the
    actual stdlib `builtins` binding and on the `__import__` attribute
    specifically -- not on a receiver that merely reads like one, not on any
    other attribute of the real module, and not across files."""
    shim = "class _Shim:\n    def __import__(self, name):\n        return name\n\n\n"
    for label, src in (
        ("unrelated local object named builtins",
         shim + "builtins = _Shim()\nbuiltins.__import__('roster')\n"),
        ("unrelated local object named like the alias",
         shim + "_b = _Shim()\n_b.__import__('roster')\n"),
        ("real builtins module, non-import attribute",
         "import builtins\n\nbuiltins.len([1])\n"),
        ("builtins imported but never called",
         "import builtins\n"),
    ):
        def build(modules_dir, src=src):
            _md_module(modules_dir, "membership", {"service.py": src})

        report = _md_run(_md_base_modules(), build)
        assert report.status == PASS, (label, report.render())
        assert report.violations == [], (label, report.render())

    def build_two_files(modules_dir):
        # The binding is per file: `binder.py` importing the real module does not
        # make `other.py`'s own same-named local object a dynamic import.
        _md_module(modules_dir, "membership", {
            "binder.py": "import builtins\n",
            "other.py": shim + "builtins = _Shim()\nbuiltins.__import__('x')\n",
        })

    report = _md_run(_md_base_modules(), build_two_files)
    assert report.status == PASS, report.render()
    assert report.violations == [], report.render()


def test_rule6_getattr_dynamic_import_is_uninspectable_error():
    """R1-F05 (`getattr` idiom): `getattr(importlib, 'import_module')(...)` used to be
    a silent exit-0 PASS -- the receiver sat behind a *call*, which neither the
    `ast.Name` nor the `ast.Attribute` branch can structurally see. The retrieval
    itself is now the finding, so the deferred two-step form is caught too, as is a
    non-constant attribute argument (unresolvable on a dynamic-import receiver).
    The same receiver fix covers the natural `import importlib as <alias>` binding,
    which was equally silent."""
    for label, src in (
        ("getattr(importlib, 'import_module')(...)",
         "import importlib\ngetattr(importlib, 'import_module')('app.modules.billing')\n"),
        ("getattr(importlib, '__import__')(...)",
         "import importlib\ngetattr(importlib, '__import__')('app.modules.billing')\n"),
        ("getattr retrieved first, called later",
         ("import importlib\n_load = getattr(importlib, 'import_module')\n"
          "_load('app.modules.billing')\n")),
        ("getattr on an `import importlib as <alias>` binding",
         "import importlib as il\ngetattr(il, 'import_module')('app.modules.billing')\n"),
        ("getattr on a binding from `import importlib.util`",
         ("import importlib.util\n"
          "getattr(importlib, 'import_module')('app.modules.billing')\n")),
        ("getattr(builtins, '__import__')(...)",
         "import builtins\ngetattr(builtins, '__import__')('app.modules.billing')\n"),
        ("non-constant attribute argument",
         ("import importlib\n_attr = 'import_module'\n"
          "getattr(importlib, _attr)('app.modules.billing')\n")),
        ("plain attribute call on an `import importlib as <alias>` binding",
         "import importlib as il\nil.import_module('app.modules.billing')\n"),
        ("retrieval lexically above the import",
         ("def go():\n    return getattr(importlib, 'import_module')('app.modules.billing')\n"
          "import importlib\n")),
    ):
        def build(modules_dir, src=src):
            _md_module(modules_dir, "membership", {"service.py": src})

        report = _md_run(_md_base_modules(), build)
        assert report.status == ERROR, (label, report.render())
        assert report.exit_code == 2, (label, report.render())
        assert report.codes() == {"MODULE_DEPS_SOURCE_UNINSPECTABLE"}, (label, report.render())
        # The getattr retrieval is counted once -- the enclosing `getattr(...)(...)`
        # application must not be reported as a second instance of the same import.
        assert len(report.violations) == 1, (label, report.render())


def test_rule6_benign_getattr_receiver_is_not_a_dynamic_import():
    """The discriminating negatives for the test above: the gate must key on an
    `importlib`/`builtins` receiver and on the dynamic-import attributes
    specifically -- not on any `getattr` that merely mentions a similar name, not
    on an unrelated attribute of the real `importlib`, and not across files."""
    shim = ("class _Shim:\n    def import_module(self, n):\n        return n\n\n"
            "    def __import__(self, n):\n        return n\n\n\n")
    for label, src in (
        ("unrelated local receiver named like a module",
         shim + "importlib_shim = _Shim()\ngetattr(importlib_shim, 'import_module')('roster')\n"),
        ("real importlib, unrelated attribute",
         "import importlib\n\ngetattr(importlib, 'machinery')\n"),
        ("builtins receiver, non-import attribute via getattr",
         "import builtins\n\ngetattr(builtins, 'len')([1])\n"),
        ("getattr on an unrelated object, import-shaped attribute name",
         shim + "obj = _Shim()\ngetattr(obj, '__import__')('roster')\n"),
        ("importlib submodule alias carries no import_module",
         "import importlib.util as iu\n\ngetattr(iu, 'find_spec')('roster')\n"),
        ("importlib bound but no getattr at all",
         "import importlib\n"),
    ):
        def build(modules_dir, src=src):
            _md_module(modules_dir, "membership", {"service.py": src})

        report = _md_run(_md_base_modules(), build)
        assert report.status == PASS, (label, report.render())
        assert report.violations == [], (label, report.render())

    def build_two_files(modules_dir):
        # The binding is per file: `binder.py` aliasing the real module does not make
        # `other.py`'s own same-named local object a dynamic-import receiver.
        _md_module(modules_dir, "membership", {
            "binder.py": "import importlib as il\n",
            "other.py": shim + "il = _Shim()\ngetattr(il, 'import_module')('x')\n",
        })

    report = _md_run(_md_base_modules(), build_two_files)
    assert report.status == PASS, report.render()
    assert report.violations == [], report.render()


def test_rule6_exec_of_import_bearing_source_is_uninspectable_error():
    """R1-F05 (`exec` idiom): round-1 review of this gate found
    `exec("from app.modules.billing.internals import s")` a silent exit-0 PASS --
    the import lives inside a string constant, invisible to the
    `ast.Import`/`ast.ImportFrom` walk, and the constant itself was only ever
    examined for SQL. An `exec` source is now admissible only when it is a string
    literal whose *parsed* AST carries no import statement, no dynamic-import
    call and no further `exec`; every unresolvable shape fails closed. The
    inspected string is parsed, never executed."""
    for label, src in (
        ("the round-1 shape: exec of a cross-module `from ... import`",
         "exec('from app.modules.billing.internals import s')\n"),
        ("exec of a plain import statement",
         "exec('import os')\n"),
        ("exec of a dynamic-import call",
         "exec(\"__import__('app.modules.billing')\")\n"),
        ("exec of a dynamic import on an outer-file importlib alias",
         ("import importlib as il\n"
          "exec(\"il.import_module('app.modules.billing')\")\n")),
        ("non-literal source (a name)",
         "_src = 'import os'\nexec(_src)\n"),
        ("f-string source",
         "_mod = 'os'\nexec(f'import {_mod}')\n"),
        ("concatenated source",
         "exec('imp' + 'ort os')\n"),
        ("bytes source",
         "exec(b'import os')\n"),
        ("starred source",
         "_args = ('import os',)\nexec(*_args)\n"),
        ("no source argument at all",
         "exec()\n"),
        ("unparseable source",
         "exec('def (')\n"),
        ("nested exec",
         'exec("exec(\'import os\')")\n'),
        ("builtins.exec",
         "import builtins\nbuiltins.exec('import os')\n"),
        ("<builtins alias>.exec",
         "import builtins as _b\n_b.exec('import os')\n"),
        ("from builtins import exec as <alias>",
         "from builtins import exec as _run\n_run('import os')\n"),
        ("call lexically above the `from builtins import exec` binding",
         ("def go():\n    return _run('import os')\n"
          "from builtins import exec as _run\n")),
        ("getattr(builtins, 'exec') retrieved first, called later",
         ("import builtins\n_run = getattr(builtins, 'exec')\n"
          "_run('import os')\n")),
    ):
        def build(modules_dir, src=src):
            _md_module(modules_dir, "membership", {"service.py": src})

        report = _md_run(_md_base_modules(), build)
        assert report.status == ERROR, (label, report.render())
        assert report.exit_code == 2, (label, report.render())
        assert report.codes() == {"MODULE_DEPS_SOURCE_UNINSPECTABLE"}, (label, report.render())
        # Counted once: neither the inspected string constant nor the enclosing
        # application of a `getattr`-retrieved `exec` is a second instance.
        assert len(report.violations) == 1, (label, report.render())


def test_rule6_exec_of_provably_import_free_source_is_not_uninspectable():
    """The discriminating negatives for the test above: `exec` of a string literal
    that provably carries no import stays admissible, and the check keys on the
    builtin `exec` specifically -- not on any callable or attribute that merely
    reads like one, and not across files."""
    shim = "class _Shim:\n    def exec(self, s):\n        return s\n\n\n"
    for label, src in (
        ("benign non-import source: assignment",
         "exec('x = 1')\n"),
        ("benign non-import source: arithmetic over several statements",
         "exec('a = 1\\nb = a + 1\\n')\n"),
        ("benign non-import source: call of a non-import builtin",
         "exec(\"print('hello')\")\n"),
        ("benign non-import source with explicit globals/locals",
         "exec('x = 1', {}, {})\n"),
        ("benign nested exec of non-import source",
         'exec("exec(\'x = 1\')")\n'),
        ("empty source",
         "exec('')\n"),
        ("unrelated local object with an `exec` method",
         shim + "obj = _Shim()\nobj.exec('import os')\n"),
        ("unrelated local object named builtins",
         shim + "builtins = _Shim()\nbuiltins.exec('import os')\n"),
        ("getattr for `exec` on an unrelated object",
         shim + "obj = _Shim()\ngetattr(obj, 'exec')('import os')\n"),
        ("no exec at all",
         "def go():\n    return 1\n"),
    ):
        def build(modules_dir, src=src):
            _md_module(modules_dir, "membership", {"service.py": src})

        report = _md_run(_md_base_modules(), build)
        assert report.status == PASS, (label, report.render())
        assert report.violations == [], (label, report.render())

    def build_two_files(modules_dir):
        # The binding is per file: `binder.py` aliasing the builtin does not make
        # `other.py`'s own same-named local callable an `exec`.
        _md_module(modules_dir, "membership", {
            "binder.py": "from builtins import exec as _run\n",
            "other.py": "def _run(s):\n    return s\n\n\n_run('import os')\n",
        })

    report = _md_run(_md_base_modules(), build_two_files)
    assert report.status == PASS, report.render()
    assert report.violations == [], report.render()


def test_rule6_fstring_with_sql_ish_literal_parts_is_uninspectable_error():
    def build(modules_dir):
        _md_module(modules_dir, "membership", {
            "repo.py": 'table = "roster"\nquery = f"SELECT * FROM membership_{table}"\n',
        })

    report = _md_run(_md_base_modules(), build)
    assert report.status == ERROR, report.render()
    assert report.codes() == {"MODULE_DEPS_SOURCE_UNINSPECTABLE"}, report.render()


def test_rule6_dangling_sql_keyword_without_identifier_is_uninspectable_error():
    def build(modules_dir):
        _md_module(modules_dir, "membership", {"repo.py": 'query = "SELECT * FROM "\n'})

    report = _md_run(_md_base_modules(), build)
    assert report.status == ERROR, report.render()
    assert report.codes() == {"MODULE_DEPS_SOURCE_UNINSPECTABLE"}, report.render()


def test_rule6_binop_sql_string_concatenation_is_uninspectable_error():
    def build(modules_dir):
        _md_module(modules_dir, "membership", {
            "repo.py": 'query = "SELECT * FROM " + "membership_roster"\n',
        })

    report = _md_run(_md_base_modules(), build)
    assert report.status == ERROR, report.render()
    assert report.codes() == {"MODULE_DEPS_SOURCE_UNINSPECTABLE"}, report.render()

    def build_mod(modules_dir):
        _md_module(modules_dir, "membership", {
            "repo.py": 'query = "SELECT * FROM %s" % ("membership_roster",)\n',
        })

    report2 = _md_run(_md_base_modules(), build_mod)
    assert report2.status == ERROR, report2.render()
    assert report2.codes() == {"MODULE_DEPS_SOURCE_UNINSPECTABLE"}, report2.render()


def test_rule6_join_assembled_sql_is_uninspectable_error():
    """R1-F06 (GATE2-R1-F06-JOIN-ASSEMBLED-SQL-2026-10-05): the review's exact
    reproducer `" ".join(["SELECT a", "FROM bil_invoices"])` was a silent exit-0
    PASS -- no fragment carries a resolvable table position on its own, so the
    per-`ast.Constant` scan cleared each in turn and the assembled statement was
    never examined. Each case below fails on the pre-fix code.

    The last case is deliberate parity with the `BinOp` branch above, which is
    ERROR for `"SELECT * FROM membership_roster" + " WHERE id = 1"` even though
    that is fully literal and its table is correctly owned by the importer:
    string-level assembly carrying a SQL-ish literal is ADR-011 D7.1 runtime
    assembly regardless of reducibility, and `.join` is held to the same rule.
    """
    for label, src in (
        ("review reproducer: verb fragment + table fragment",
         'query = " ".join(["SELECT a", "FROM bil_invoices"])\n'),
        ("tuple of fragments rather than a list",
         'query = " ".join(("SELECT a", "FROM bil_invoices"))\n'),
        ("non-literal separator, fragments spaced apart",
         'def build(sep):\n    return sep.join(["SELECT a", "FROM bil_invoices"])\n'),
        ("non-literal separator, verb only visible when fragments fuse",
         'def build(sep):\n    return sep.join(["SELE", "CT a FROM bil_invoices"])\n'),
        ("literal fragment plus a dynamic element",
         'table = "roster"\nquery = " ".join(["SELECT a FROM", table])\n'),
        ("owned table, fully literal: BinOp-branch parity",
         'query = " ".join(["SELECT * FROM membership_roster", "WHERE id = 1"])\n'),
    ):
        def build(modules_dir, src=src):
            _md_module(modules_dir, "membership", {"repo.py": src})

        report = _md_run(_md_base_modules(), build)
        assert report.status == ERROR, (label, report.render())
        assert report.codes() == {"MODULE_DEPS_SOURCE_UNINSPECTABLE"}, (label, report.render())


def test_rule6_benign_non_sql_join_is_not_uninspectable():
    """The discriminating negatives for the test above: the R1-F06 branch keys on
    the assembled fragments spelling SQL-ish text, not on `.join` being called, so
    ordinary string assembly stays admissible. A join with no literal text at all
    is also clean -- the branch asserts only what literal fragments already spell,
    and never guesses at a dynamic element (see the residual note in
    `_join_assembly_candidates`)."""
    for label, src in (
        ("path-style join", 'path = "/".join(["alpha", "beta", "gamma"])\n'),
        ("comma join", 'label = ", ".join(["alpha", "beta"])\n'),
        ("fully dynamic join: no literal fragments",
         'def render(items):\n    return ", ".join(items)\n'),
        ("comprehension argument: no literal elements",
         'def render(items):\n    return ",".join([str(i) for i in items])\n'),
        ("empty element list", 'label = ",".join([])\n'),
        ("a trigger verb embedded in a longer word is not a verb",
         'label = " ".join(["preselected", "items"])\n'),
        ("unrelated callable named join on a non-string receiver",
         'import os.path\n\npath = os.path.join("alpha", "beta")\n'),
        ("generator argument rather than a literal sequence",
         'def render(items):\n    return " ".join(str(i) for i in items)\n'),
    ):
        def build(modules_dir, src=src):
            _md_module(modules_dir, "membership", {"repo.py": src})

        report = _md_run(_md_base_modules(), build)
        assert report.status == PASS, (label, report.render())
        assert report.violations == [], (label, report.render())


def test_rule6_interpolated_verb_fstring_is_uninspectable_error():
    """R1-F06 (GATE2-R1-F06-INTERPOLATED-VERB-FSTRING-2026-10-05): the review's
    exact reproducer `f"{op} a FROM bil_invoices"` was a silent exit-0 PASS. The
    `JoinedStr` branch required `_is_sql_ish` of the literal parts, and the literal
    parts (`" a FROM bil_invoices"`) carry a table position but no `_TRIGGER_VERBS`
    verb -- the verb is in the interpolation hole -- so neither that branch nor the
    per-`ast.Constant` `_scan_sql_text` path (which returns on the same
    `_is_sql_ish` check) ever examined it. Every case below fails on the pre-fix
    code; the reproducer was confirmed PASS pre-fix by direct execution.

    The lowercase case is load-bearing against a narrowing that was considered and
    rejected: keying on an uppercase-as-written keyword would have kept exactly
    this fail-open for lowercase SQL.

    The last case asserts the branch's DISCLOSED over-approximation rather than
    hiding it -- the table-position test is this module's regex keyword
    classifier, so prose containing FROM/JOIN/INTO/UPDATE/TABLE/ONLY/REFERENCES as
    a word is reported too. That is the ERROR-direction cost ADR-011 D6.1 already
    accepts explicitly, and it is asserted here so the behaviour is pinned, not
    discovered later.
    """
    for label, src in (
        ("review reproducer: interpolated verb, literal FROM + table",
         'def q(op):\n    return f"{op} a FROM bil_invoices"\n'),
        ("lowercase keyword: no uppercase-only loosening",
         'def q(op):\n    return f"{op} a from bil_invoices"\n'),
        ("INTO, table owned by the importer: UNINSPECTABLE regardless of ownership",
         'def q(op):\n    return f"{op} INTO membership_roster"\n'),
        ("JOIN in literal position",
         'def q(op):\n    return f"{op} a JOIN bil_invoices"\n'),
        ("ONLY: a keyword outside the extractor\'s own FROM/JOIN/INTO/UPDATE/TABLE set",
         'def q(op):\n    return f"{op} ONLY membership_roster"\n'),
        ("TABLE keyword with both verb and identifier interpolated",
         'def q(op, name):\n    return f"{op} TABLE {name}"\n'),
        ("REFERENCES in literal position",
         'def q(op):\n    return f"{op} c REFERENCES bil_invoices"\n'),
        ("disclosed over-approximation: prose containing FROM as a word",
         'def q(n):\n    return f"loaded {n} rows from cache"\n'),
    ):
        def build(modules_dir, src=src):
            _md_module(modules_dir, "membership", {"repo.py": src})

        report = _md_run(_md_base_modules(), build)
        assert report.status == ERROR, (label, report.render())
        assert report.codes() == {"MODULE_DEPS_SOURCE_UNINSPECTABLE"}, (label, report.render())


def test_rule6_benign_fstring_without_table_position_is_not_uninspectable():
    """The discriminating negatives for the test above: the interpolated-verb branch
    keys on the literal parts carrying a table position, not on `ast.JoinedStr`
    being present, so ordinary f-strings stay admissible. Without these, a branch
    that simply reported every interpolated f-string would pass the ERROR test
    above while making the gate useless."""
    for label, src in (
        ("plain interpolation, no SQL vocabulary",
         'def greet(name):\n    return f"hello {name}"\n'),
        ("count message",
         'def msg(count):\n    return f"{count} items processed"\n'),
        ("keyword only as a substring, not a word",
         'def msg(x):\n    return f"{x} fromage and tabletop"\n'),
        ("two interpolations, no keyword",
         'def msg(a, b):\n    return f"{a} and {b}"\n'),
        ("f-string with no interpolation at all: no hole can supply a verb",
         'label = f"a FROM b"\n'),
        ("format spec and conversion, no keyword",
         'def msg(v):\n    return f"{v!r} at {v:>8}"\n'),
        ("nested quotes, no keyword", 'def msg(d):\n    return f"key {d[\'k\']}"\n'),
    ):
        def build(modules_dir, src=src):
            _md_module(modules_dir, "membership", {"repo.py": src})

        report = _md_run(_md_base_modules(), build)
        assert report.status == PASS, (label, report.render())
        assert report.violations == [], (label, report.render())


def test_rule6_fragment_sequence_concatenated_at_runtime_is_uninspectable_error():
    """R1-F06 (GATE2-R1-F06-FRAGMENT-LIST-CONCAT-2026-10-05): the review's third
    and last F06 idiom, recorded in its reproducer table as "list element then
    concat at runtime" with the source `PARTS = ['SELECT a', 'FROM bil_invoices']`,
    was a silent exit-0 PASS -- confirmed against the pre-fix code by direct
    execution of the review's own harness, in the same run that showed the two
    already-closed shapes (`.join`, interpolated-verb f-string) now ERRORing, so
    this is a live residual of F06 rather than a re-report of either fix.

    Neither closed branch reaches it: `_join_assembly_candidates` requires the
    display to BE a `.join` argument, and the per-`ast.Constant` scan sees one
    fragment at a time -- `"SELECT a"` triggers but carries no table position (so
    `_scan_sql_text` clears it at the D6.3 I-1 backstop) and `"FROM bil_invoices"`
    does not trigger at all.

    The first case is the review's reproducer verbatim; the second adds the
    runtime concatenation the review's label describes, to show the finding does
    not depend on the concatenation being visible. The last case is the same
    `BinOp`/`.join`-branch parity those branches already apply: string-level
    assembly carrying SQL-ish text with a table position is ADR-011 D7.1 runtime
    assembly regardless of whether the fragments happen to be fully literal and
    the table correctly owned.
    """
    for label, src in (
        ("review reproducer verbatim: bare list of fragments",
         'PARTS = ["SELECT a", "FROM bil_invoices"]\n'),
        ("same list, concatenated at runtime in a loop",
         ('PARTS = ["SELECT a", "FROM bil_invoices"]\n\n\ndef build():\n'
          '    out = ""\n    for p in PARTS:\n        out = out + " " + p\n    return out\n')),
        ("tuple display rather than a list",
         'PARTS = ("SELECT a", "FROM bil_invoices")\n'),
        ("set display rather than a list",
         'PARTS = {"SELECT a", "FROM bil_invoices"}\n'),
        ("verb only visible once adjacent fragments fuse",
         'PARTS = ["SELE", "CT a FROM bil_invoices"]\n'),
        ("literal fragments plus a dynamic element",
         'def build(table):\n    return ["SELECT a FROM", table]\n'),
        ("lowercase: no uppercase-only loosening",
         'PARTS = ["select a", "from bil_invoices"]\n'),
        ("joined by a name in another function, not at the display",
         ('PARTS = ["DELETE", "FROM bil_invoices"]\n\n\ndef build(sep):\n'
          '    return sep.join(PARTS)\n')),
        ("owned table, fully literal: BinOp/.join-branch parity",
         'PARTS = ["SELECT * FROM membership_roster", "WHERE id = 1"]\n'),
        ("disclosed over-approximation: prose spelling a verb and FROM across elements",
         'PARTS = ["select the row", "from cache"]\n'),
    ):
        def build(modules_dir, src=src):
            _md_module(modules_dir, "membership", {"repo.py": src})

        report = _md_run(_md_base_modules(), build)
        assert report.status == ERROR, (label, report.render())
        assert report.codes() == {"MODULE_DEPS_SOURCE_UNINSPECTABLE"}, (label, report.render())


def test_rule6_benign_sequence_and_concatenation_is_not_uninspectable():
    """The discriminating negatives for the test above. Without these, a branch
    that reported every literal sequence display would pass the ERROR test while
    making the gate useless -- a sequence of string literals is one of the most
    common shapes in ordinary Python.

    The branch is deliberately NARROWER than the `.join` branch, which keys on
    `_is_sql_ish` alone: a bare display carries no authorial "assemble a string
    here" signal, so this branch additionally requires a table position -- the
    pair of conditions under which the same text, written as one literal, would
    have reached `_scan_sql_text`'s table examination instead of being cleared.
    The verb-word-only cases below pin exactly that narrowing, and the
    `BARE_VERB`/`GRANT ... ON` cases pin that `_implies_table_position`'s
    bare-table-verb disjunct is live here and not only its keyword disjunct.
    """
    for label, src in (
        ("path-style list", 'PARTS = ["alpha", "beta", "gamma"]\n'),
        ("config tuple", 'FIELDS = ("id", "created_at", "name")\n'),
        ("verb word but no table position: narrowing is load-bearing",
         'FIELDS = ("id", "select")\n'),
        ("table-position keyword but no verb", 'PARTS = ["rows", "from cache"]\n'),
        ("prose with neither", 'PARTS = ["loaded rows", "ok"]\n'),
        ("keywords only as substrings, not words",
         'PARTS = ["selected", "fromage", "tabletop"]\n'),
        ("no literal element at all",
         'def build(a, b):\n    return [a, b]\n'),
        ("empty display", 'PARTS = []\n'),
        ("comprehension, not a display of literals",
         'def build(items):\n    return [str(i) for i in items]\n'),
        ("ordinary concatenation of non-SQL literals", 'LABEL = "alpha" + "beta"\n'),
    ):
        def build(modules_dir, src=src):
            _md_module(modules_dir, "membership", {"repo.py": src})

        report = _md_run(_md_base_modules(), build)
        assert report.status == PASS, (label, report.render())
        assert report.violations == [], (label, report.render())


def test_rule6_join_argument_sequence_reports_once_as_join_assembly():
    """The fragment-sequence branch must not double-report the already-closed
    `.join` shape: `ast.walk` yields the `Call` and its argument display as two
    separate nodes with no parent link, so without `_join_argument_sequences`
    both branches fire on one construct. One finding, carrying the `.join`
    branch's own more specific message, is the asserted behaviour -- the same
    "reported once, keeping the more specific report" rule the dynamic-import /
    `exec` / `.join` ordering inside `_uninspectable_for_node` already follows.

    Suppression loses no detection, and the last case proves it: with a literal
    separator the `.join` branch knows the assembled text exactly, which is
    strictly better information than this branch's two-extreme lower bound, so
    `"X".join(["SELE", "CT a FROM bil_invoices"])` is correctly PASS -- the real
    assembled text is `SELEXCT a FROM bil_invoices`, which is not SQL.
    """
    def build(modules_dir):
        _md_module(modules_dir, "membership", {
            "repo.py": 'query = " ".join(["SELECT a", "FROM bil_invoices"])\n',
        })

    report = _md_run(_md_base_modules(), build)
    assert report.status == ERROR, report.render()
    uninspectable = [v for v in report.violations
                     if v.code == "MODULE_DEPS_SOURCE_UNINSPECTABLE"]
    assert len(uninspectable) == 1, report.render()
    assert "`str.join` assembly" in uninspectable[0].detail, report.render()

    def build_exact_separator(modules_dir):
        _md_module(modules_dir, "membership", {
            "repo.py": 'query = "X".join(["SELE", "CT a FROM bil_invoices"])\n',
        })

    report2 = _md_run(_md_base_modules(), build_exact_separator)
    assert report2.status == PASS, report2.render()
    assert report2.violations == [], report2.render()


# --- ADR-011 D6.1/D6.3 (GATE2-R1-D6-TRIGGER-I1-2026-10-05): broad-trigger-verb
# widening and the corrected I-1 zero-table-statement backstop. Driven end-to-end
# through `run_module_deps_gate` via the existing `_md_*` fixture helpers above,
# matching this file's live-wiring-test convention, rather than importing the
# private `_TRIGGER_VERBS`/`_is_sql_ish`/`_dangling_keywords`/
# `_has_bare_table_verb_form` helpers directly.
#
# Four case groups, named exactly as D6.1/D6.3 name them:
#
#   broad-trigger verbs       -- a D6.1-widened verb that is NOT one of the
#                                 pre-widening SELECT/INSERT/UPDATE/DELETE/
#                                 TRUNCATE/COPY set must still drive a real
#                                 table reference all the way to attribution
#                                 (here, CROSS_DOMAIN_SQL_IMPORT), proving the
#                                 widened verb set is wired into live scanning,
#                                 not just declared in `_TRIGGER_VERBS`.
#   dangling table-position
#   keyword                   -- a keyword from the backstop's broader
#                                 `_TABLE_POSITION_KEYWORDS` set (ONLY/
#                                 REFERENCES -- not in the extractor's own
#                                 FROM/JOIN/INTO/UPDATE/TABLE set) with no
#                                 identifier extracted is ERROR via the I-1
#                                 backstop.
#   bare-table verbs           -- a verb form carrying no table-position keyword
#                                 of its own is ERROR via the I-1 backstop's
#                                 bare-verb-form check. TRUNCATE left this group
#                                 when GATE2-R2-N01-D67-TRUNCATE-BARE-VERB-SIGNAL-
#                                 2026-10-06 gave it a real signal source, COPY
#                                 when the qualified COPY decision gave it one,
#                                 and the GRANT/REVOKE *table-target* forms when
#                                 GATE2-R2-N01-D67-GRANT-REVOKE-ON-2026-10-06 gave
#                                 that family one -- each now drives a real
#                                 cross-module attribution in the group above
#                                 instead. What remains here is the GRANT/REVOKE
#                                 `ON` form whose object is not a table target,
#                                 which that increment deliberately leaves on the
#                                 backstop (see the row's own comment below).
#   clean/no-trigger cases      -- D6.3's own named list: a triggered statement
#                                 with no table position at all (`SELECT 1`,
#                                 `SELECT now()`, `ANALYZE`, a bare `VACUUM`) is
#                                 clean -- no violation at all.
def test_d6_trigger_verb_widening_and_i1_backstop_table_driven():
    cross_domain_modules = {
        "membership": _md_entry("MEM-01", ["membership_"],
                                ["app.modules.membership.interface"]),
        "billing": _md_entry("BIL-02", ["billing_"], ["app.modules.billing.interface"]),
    }

    def build_cross_domain(modules_dir, sql_text):
        _md_module(modules_dir, "membership", {"repo.sql": sql_text})
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge():\n    return None\n",
        })

    def build_membership_only(modules_dir, sql_text):
        _md_module(modules_dir, "membership", {"repo.sql": sql_text})

    # (label, sql_text, build_kind) where build_kind is "cross_domain" (group A,
    # expect FAIL/CROSS_DOMAIN_SQL_IMPORT against billing_invoice) or "membership_only"
    # (groups B/C, expect ERROR/MODULE_DEPS_SOURCE_UNINSPECTABLE via the I-1 backstop).
    error_cases = [
        # --- broad-trigger verbs (D6.1): widened verbs beyond SELECT/INSERT/
        # UPDATE/DELETE/TRUNCATE/COPY, each paired with a real cross-module
        # table reference so the widened verb must drive a real attribution,
        # not just a regex match in isolation.
        ("broad_trigger_merge", "MERGE INTO billing_invoice\n", "cross_domain", None),
        ("broad_trigger_create", "CREATE TABLE billing_invoice\n", "cross_domain", None),
        ("broad_trigger_alter", "ALTER TABLE billing_invoice\n", "cross_domain", None),
        ("broad_trigger_drop", "DROP TABLE billing_invoice\n", "cross_domain", None),
        ("broad_trigger_lock", "LOCK TABLE billing_invoice\n", "cross_domain", None),
        ("broad_trigger_comment", "COMMENT ON TABLE billing_invoice\n", "cross_domain", None),
        # --- dangling table-position keyword (D6.3 backstop): ONLY is in the
        # backstop's `_TABLE_POSITION_KEYWORDS` set but NOT in the extractor's
        # own FROM/JOIN/INTO/UPDATE/TABLE set (and not in the dedicated
        # REFERENCES signal added by ADR-011 D6.7.2 below), so it specifically
        # exercises the backstop branch rather than a dangling-keyword early
        # return.
        ("dangling_only_keyword", "SELECT ONLY \n", "membership_only", "I-1 backstop"),
        # REFERENCES moved from the I-1 backstop to the dedicated
        # `_REFERENCES_KEYWORD_RE` dangling-keyword check (ADR-011 D6.7.2,
        # GATE2-R2-N01-D6.7-REFERENCES-SIGNAL-2026-10-06): same ERROR/
        # MODULE_DEPS_SOURCE_UNINSPECTABLE outcome, now via the more specific
        # per-position message naming REFERENCES directly rather than the
        # generic statement-level backstop.
        ("dangling_references_keyword",
         "ALTER foo ADD CONSTRAINT fk REFERENCES \n", "membership_only", "REFERENCES"),
        # --- bare-table verbs (D6.3): no table-position keyword at all.
        #
        # TRUNCATE moved from the I-1 backstop to its own context-sensitive signal
        # source routed through the shared list walk (ADR-011 D6.7.3,
        # GATE2-R2-N01-D67-TRUNCATE-BARE-VERB-SIGNAL-2026-10-06), so it is now in
        # group A rather than group C: its target is extracted and attributed, which
        # makes `TRUNCATE billing_invoice` the CROSS_DOMAIN_SQL_IMPORT it names
        # instead of a statement-wide "source uninspectable" refusal. Strictly
        # stronger on the same tree -- the gate now says which boundary was crossed.
        # COPY now has its own source, as TRUNCATE does; and so does the
        # GRANT/REVOKE object clause as of GATE2-R2-N01-D67-GRANT-REVOKE-ON-
        # 2026-10-06, which moves both of the GRANT/REVOKE table-target rows below
        # from group C to group A for the same reason TRUNCATE moved: the target is
        # now extracted and attributed, so the gate names the boundary that was
        # crossed instead of refusing the whole source. Strictly stronger on the
        # same tree.
        ("bare_table_truncate", "TRUNCATE billing_invoice\n", "cross_domain", None),
        ("bare_table_copy", "COPY billing_invoice TO STDOUT\n", "cross_domain", None),
        ("bare_table_grant_on", "GRANT SELECT ON billing_invoice TO someone\n",
         "cross_domain", None),
        ("bare_table_revoke_on", "REVOKE SELECT ON billing_invoice FROM someone\n",
         "cross_domain", None),
        # Group C is NOT vacated by that move: `_has_bare_table_verb_form`'s
        # GRANT/REVOKE disjunct is deliberately still unconditional, so a
        # GRANT/REVOKE `ON` form whose object is not a single table target -- the
        # new signal source excludes those, naming no table rather than resolving
        # the object-type keyword as one -- keeps exactly the I-1 backstop refusal
        # it had before that increment. This row is the live control for that
        # disjunct, and it is the bare-verb-form branch specifically: there is no
        # `_TABLE_POSITION_KEYWORDS` member anywhere in the text.
        ("bare_table_grant_on_non_table_object",
         "GRANT USAGE ON SCHEMA membership_private TO someone\n",
         "membership_only", "I-1 backstop"),
    ]
    for label, sql_text, build_kind, detail_substring in error_cases:
        if build_kind == "cross_domain":
            def build(modules_dir, sql_text=sql_text):
                build_cross_domain(modules_dir, sql_text)
            report = _md_run(cross_domain_modules, build)
            assert report.status == FAIL, (label, report.render())
            assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, (label, report.render())
            assert any("billing_invoice" in v.detail for v in report.violations), \
                (label, report.render())
        else:
            def build(modules_dir, sql_text=sql_text):
                build_membership_only(modules_dir, sql_text)
            report = _md_run(_md_base_modules(), build)
            assert report.status == ERROR, (label, report.render())
            assert report.codes() == {"MODULE_DEPS_SOURCE_UNINSPECTABLE"}, \
                (label, report.render())
            assert any(detail_substring in v.detail for v in report.violations), \
                (label, report.render())

    # --- clean/no-trigger cases (D6.3's own named list): a triggered statement
    # with no table position at all is clean -- not even disclosed as a
    # violation (D8's own counter for this bucket is separate, out-of-scope
    # follow-on work; this only locks in that no ERROR/FAIL is raised).
    clean_cases = [
        ("clean_select_1", "SELECT 1\n"),
        ("clean_select_now", "SELECT now()\n"),
        ("clean_analyze", "ANALYZE\n"),
        ("clean_vacuum", "VACUUM\n"),
    ]
    for label, sql_text in clean_cases:
        def build(modules_dir, sql_text=sql_text):
            build_membership_only(modules_dir, sql_text)
        report = _md_run(_md_base_modules(), build)
        assert report.status == PASS, (label, report.render())
        assert not report.violations, (label, report.render())


# --- rule 8: MODULE_DEPS_GATE_VACUOUS --------------------------------------------


def test_rule8_docstring_only_tree_is_vacuous_not_pass():
    def build(modules_dir):
        _md_module(modules_dir, "membership", {})  # only the auto docstring __init__.py

    report = _md_run(_md_base_modules(), build)
    assert report.status == INCONCLUSIVE, report.render()
    assert report.codes() == {"MODULE_DEPS_GATE_VACUOUS"}, report.render()


# --- rule 7: MODULE_DEPS_GATE_INPUT_INVALID --------------------------------------


def test_rule7_missing_manifest_is_error():
    report = _md_run(_md_base_modules(), _md_base_build, write_manifest=False)
    _assert_md_input_error(report, "missing manifest")


def test_rule7_symlinked_manifest_is_error():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        modules_dir = _md_tree(root)
        _md_base_build(modules_dir)
        real = root / "real-manifest.json"
        real.write_text(json.dumps(_md_manifest(_md_base_modules())))
        link = root / "module-manifest.json"
        link.symlink_to(real)
        report = run_module_deps_gate(modules_dir, link)
        _assert_md_input_error(report, "symlinked manifest")


def test_rule7_manifest_version_must_be_1():
    for version in (2, 0, "1", 1.0, True, None):
        raw = {"version": version, "modules": _md_base_modules()}
        report = _md_run(None, _md_base_build, manifest=raw)
        _assert_md_input_error(report, version)


def test_rule7_manifest_unknown_top_level_key_is_error():
    raw = {"version": 1, "modules": _md_base_modules(), "extra": True}
    report = _md_run(None, _md_base_build, manifest=raw)
    _assert_md_input_error(report, "unknown top-level key")


def test_rule7_manifest_unknown_entry_key_is_error():
    entry = dict(_md_entry("MEM-01", ["membership_"], ["app.modules.membership.interface"]),
                 extra="x")
    report = _md_run({"membership": entry}, _md_base_build)
    _assert_md_input_error(report, "unknown entry key")


def test_rule7_module_named_shared_is_error():
    modules = {"_shared": _md_entry("MEM-01", ["shared_"], ["app.modules._shared.interface"])}

    def build(modules_dir):
        _md_module(modules_dir, "_shared", {"interface.py": "def x():\n    return None\n"})

    report = _md_run(modules, build)
    _assert_md_input_error(report, "module named _shared")


def test_rule7_malformed_domain_is_error():
    for domain in ("", 123, None, ["MEM-01"], "mem-01", "MEM01", "MEM-01\n"):
        modules = {"membership": _md_entry(domain, ["membership_"],
                                           ["app.modules.membership.interface"])}
        report = _md_run(modules, _md_base_build)
        _assert_md_input_error(report, domain)


def test_rule7_two_modules_sharing_a_domain_is_error():
    modules = {
        "membership": _md_entry("MEM-01", ["membership_"],
                                ["app.modules.membership.interface"]),
        "billing": _md_entry("MEM-01", ["billing_"], ["app.modules.billing.interface"]),
    }

    def build(modules_dir):
        _md_base_build(modules_dir)
        _md_module(modules_dir, "billing", {"interface.py": "def x():\n    return None\n"})

    report = _md_run(modules, build)
    _assert_md_input_error(report, "shared domain")


def test_rule7_empty_owned_table_prefixes_is_error():
    modules = {"membership": _md_entry("MEM-01", [], ["app.modules.membership.interface"])}
    report = _md_run(modules, _md_base_build)
    _assert_md_input_error(report, "empty owned_table_prefixes")


def test_rule7_prefix_that_is_a_prefix_of_another_is_error():
    modules = {
        "membership": _md_entry("MEM-01", ["mem"], ["app.modules.membership.interface"]),
        "billing": _md_entry("BIL-02", ["mem_billing_"], ["app.modules.billing.interface"]),
    }

    def build(modules_dir):
        _md_base_build(modules_dir)
        _md_module(modules_dir, "billing", {"interface.py": "def x():\n    return None\n"})

    report = _md_run(modules, build)
    _assert_md_input_error(report, "ambiguous prefix")


def test_rule7_public_interface_not_under_own_package_is_error():
    for bad_interface in (
        "app.modules.other.interface",
        "app.modules.membership",
        "app.modules.membershipx.interface",
        "membership.interface",
        123,
    ):
        modules = {"membership": _md_entry("MEM-01", ["membership_"], [bad_interface])}
        report = _md_run(modules, _md_base_build)
        _assert_md_input_error(report, bad_interface)


def test_rule7_module_dir_on_disk_without_manifest_entry_is_error():
    def build(modules_dir):
        _md_base_build(modules_dir)
        _md_module(modules_dir, "ghost", {"interface.py": "def x():\n    return None\n"})

    report = _md_run(_md_base_modules(), build)
    _assert_md_input_error(report, "ghost module dir with no manifest entry")


def test_rule7_modules_dir_shape_errors():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        manifest_path = root / "module-manifest.json"
        manifest_path.write_text(json.dumps(_md_manifest(_md_base_modules())))

        report = run_module_deps_gate(root / "nope", manifest_path)
        _assert_md_input_error(report, "missing modules-dir")

        (root / "app2").mkdir()
        (root / "app2" / "__init__.py").write_text("")
        no_init = root / "app2" / "modules"
        no_init.mkdir()  # deliberately no __init__.py here
        _md_module(no_init, "membership", {
            "service.py": "from app.modules.membership.models import Member\n",
            "models.py": "class Member:\n    pass\n",
        })
        report = run_module_deps_gate(no_init, manifest_path)
        _assert_md_input_error(report, "modules-dir without __init__.py")

        (root / "real").mkdir()
        real_modules_dir = _md_tree(root / "real")
        _md_base_build(real_modules_dir)
        link = root / "linked_modules"
        link.symlink_to(real_modules_dir, target_is_directory=True)
        report = run_module_deps_gate(link, manifest_path)
        _assert_md_input_error(report, "symlinked modules-dir")


def test_rule7_symlinked_source_file_is_error():
    def build(modules_dir):
        _md_base_build(modules_dir)
        real = modules_dir / "membership" / "real_models.py"
        real.write_text("class Real:\n    pass\n")
        (modules_dir / "membership" / "linked.py").symlink_to(real)

    report = _md_run(_md_base_modules(), build)
    _assert_md_input_error(report, "symlinked source file")


def test_rule7_py_file_that_fails_to_parse_is_error():
    def build(modules_dir):
        _md_base_build(modules_dir)
        (modules_dir / "membership" / "broken.py").write_text("def broken(:\n    pass\n")

    report = _md_run(_md_base_modules(), build)
    _assert_md_input_error(report, "unparseable .py")


_LATIN1_COOKIE_SOURCE = b'# -*- coding: latin-1 -*-\nNAME = "caf\xe9"\n'


def test_f07_non_utf8_python_source_is_named_error_not_traceback():
    """R1-F07 / ADR-011 D7.3: a non-UTF-8 `.py` file under `--modules-dir` used
    to reach a bare `path.read_text(encoding="utf-8")`, so the gate died with an
    uncaught `UnicodeDecodeError` -- exit 1, no `GateReport` at all (reproduced
    by direct execution before this increment). The fail-closed outcome is a
    named `MODULE_DEPS_GATE_INPUT_INVALID` ERROR at exit 2 on both surfaces.

    The fixture is *legal Python* under its PEP 263 coding cookie -- asserted
    here via `compile()` on the raw bytes, which honours the cookie -- so this
    is deliberately NOT the already-covered syntax-error case
    (test_rule7_py_file_that_fails_to_parse_is_error). The cookie is not
    honoured by the gate: unusable input, never a silent second decode and
    never a skip."""
    compile(_LATIN1_COOKIE_SOURCE, "latin.py", "exec")  # legal Python under its cookie
    try:
        _LATIN1_COOKIE_SOURCE.decode("utf-8")
        return  # defensive: fixture is no longer non-UTF-8, skip rather than false-green
    except UnicodeDecodeError:
        pass

    def build(modules_dir):
        _md_base_build(modules_dir)
        (modules_dir / "membership" / "latin.py").write_bytes(_LATIN1_COOKIE_SOURCE)

    report = _md_run(_md_base_modules(), build)
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, report.render()
    text = report.render()
    assert "PASS" not in text, text
    # the offending file is named, and the decode failure is distinguishable
    # from EACCES on the same read site
    assert "membership/latin.py" in text, text
    assert "UnicodeDecodeError" in text, text
    payload = json.loads(report.to_json())
    assert payload["status"] == ERROR, payload
    assert [v["code"] for v in payload["violations"]] == ["MODULE_DEPS_GATE_INPUT_INVALID"], payload


def test_f07_valid_utf8_non_ascii_python_source_still_passes():
    """Valid-UTF-8 control for the increment above: non-ASCII content that *is*
    UTF-8 must still be read, parsed and PASS. Without this control the fix
    could satisfy its own test by refusing every non-ASCII `.py` file."""
    def build(modules_dir):
        _md_base_build(modules_dir)
        # the same character as the latin-1 fixture, encoded as valid UTF-8
        (modules_dir / "membership" / "utf8.py").write_bytes(b'NAME = "caf\xc3\xa9"\n')

    report = _md_run(_md_base_modules(), build)
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    assert "membership/utf8.py" in report.checked, report.render()


def test_f07_unreadable_python_source_is_named_error_not_traceback():
    """Same read site, `OSError` rather than `UnicodeDecodeError`: an
    unreadable `.py` file must also become MODULE_DEPS_GATE_INPUT_INVALID at
    exit 2, not an uncaught `PermissionError`. Same chmod skip discipline as
    test_d5_unreadable_namespace_directory_surfaces_as_error_not_pass: return
    early (skip, not a false green) if this host does not enforce mode 000."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        modules_dir = _md_tree(root)
        _md_base_build(modules_dir)
        secret = modules_dir / "membership" / "secret.py"
        secret.write_text("x = 1\n")
        os.chmod(secret, 0o000)
        try:
            try:
                secret.read_bytes()
                return  # host does not enforce mode 000 -- skip, not a false green
            except PermissionError:
                pass
            manifest_path = root / "module-manifest.json"
            _md_write_manifest(modules_dir, manifest_path, _md_base_modules())
            report = run_module_deps_gate(modules_dir, manifest_path)
            assert report.status == ERROR, report.render()
            assert report.exit_code == 2, report.render()
            assert report.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, report.render()
            assert "membership/secret.py" in report.render(), report.render()
            assert "PASS" not in report.render(), report.render()
        finally:
            os.chmod(secret, 0o644)


_NON_UTF8_SQL_SOURCE = b"SELECT id FROM billing_invoice WHERE note = 'caf\xe9'\n"


def test_f07_non_utf8_sql_source_is_named_error_not_traceback():
    """R1-F07 / ADR-011 D7.3, `.sql` half
    (GATE2-R1-F07-SQL-DECODE-ERROR-2026-10-05): after the `.py` read was routed
    through the conversion helper, the `.sql` read at the same scan site was
    still a bare `path.read_text(encoding="utf-8")`, so a non-UTF-8 `.sql` file
    under `--modules-dir` killed the gate with an uncaught `UnicodeDecodeError`
    -- exit 1, no `GateReport` at all, on the text surface *and* under `--json`
    (both reproduced by direct CLI execution before this increment). The
    fail-closed outcome is a named `MODULE_DEPS_GATE_INPUT_INVALID` ERROR at
    exit 2 on both surfaces.

    The fixture's decodable prefix references `billing_invoice`, a table the
    manifest gives to another module, so a regression that skipped the
    undecodable file would be visible twice over: the gate would lose a real
    CROSS_DOMAIN_SQL_IMPORT finding *and* could report PASS over a file it
    never read. The asserted code set is exactly the input error and nothing
    else -- no byte of this file was decoded, so the gate must not claim to
    have found the cross-domain reference either, and must not re-read with
    `errors="replace"` and attribute identifiers out of corrupted text."""
    try:
        _NON_UTF8_SQL_SOURCE.decode("utf-8")
        return  # defensive: fixture is no longer non-UTF-8, skip rather than false-green
    except UnicodeDecodeError:
        pass

    def build(modules_dir):
        _md_module(modules_dir, "membership", {})
        (modules_dir / "membership" / "reports.sql").write_bytes(_NON_UTF8_SQL_SOURCE)
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge():\n    return None\n",
        })

    modules = {
        "membership": _md_entry("MEM-01", ["membership_"],
                                ["app.modules.membership.interface"]),
        "billing": _md_entry("BIL-02", ["billing_"], ["app.modules.billing.interface"]),
    }
    report = _md_run(modules, build)
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, report.render()
    text = report.render()
    assert "PASS" not in text, text
    # the offending file is named, and the decode failure stays distinguishable
    # from EACCES on the same read site
    assert "membership/reports.sql" in text, text
    assert "UnicodeDecodeError" in text, text
    payload = json.loads(report.to_json())
    assert payload["status"] == ERROR, payload
    assert [v["code"] for v in payload["violations"]] == ["MODULE_DEPS_GATE_INPUT_INVALID"], payload
    assert "membership/reports.sql" in payload["violations"][0]["detail"], payload
    assert payload["checked"] == [], payload


def test_f07_valid_utf8_non_ascii_sql_source_still_scans_and_passes():
    """Valid-UTF-8 control for the increment above: non-ASCII `.sql` content that
    *is* UTF-8 must still be read, scanned and PASS. Without this control the
    fix could satisfy its own test by refusing every non-ASCII `.sql` file. The
    file is asserted to have reached `checked`, not merely that the run is
    PASS: a `.sql` file is unconditionally substantive, so a refusal that
    dropped it would also have to be caught here rather than hidden behind an
    otherwise-clean tree."""
    def build(modules_dir):
        _md_base_build(modules_dir)
        # the same character as the non-UTF-8 fixture, encoded as valid UTF-8,
        # inside a literal in a query against the module's own owned table
        (modules_dir / "membership" / "notes.sql").write_bytes(
            b"SELECT id FROM membership_roster WHERE note = 'caf\xc3\xa9'\n"
        )

    report = _md_run(_md_base_modules(), build)
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    assert "membership/notes.sql" in report.checked, report.render()


def test_rule7_file_extension_outside_closed_set_is_error():
    def build(modules_dir):
        _md_base_build(modules_dir)
        (modules_dir / "membership" / "notes.cfg").write_text("x=1\n")

    report = _md_run(_md_base_modules(), build)
    _assert_md_input_error(report, "disallowed extension")


def test_rule7_md_txt_gitkeep_extensions_are_allowed():
    def build(modules_dir):
        _md_base_build(modules_dir)
        (modules_dir / "membership" / "NOTES.md").write_text("# notes\n")
        (modules_dir / "membership" / "README.txt").write_text("notes\n")
        (modules_dir / "membership" / ".gitkeep").write_text("")

    report = _md_run(_md_base_modules(), build)
    assert report.status == PASS, report.render()
    assert report.checked


def test_module_deps_removed_from_deferred_gates_invariant_holds_for_rest():
    assert "module-deps" not in DEFERRED_GATES
    assert "module-deps" in IMPLEMENTED_GATES
    # the pre-existing deferred-gates invariant (see test_deferred_gates_never_pass
    # above) must still hold for every gate name still left in DEFERRED_GATES now
    # that module-deps has moved out of it.
    assert DEFERRED_GATES  # still non-empty; the invariant below would be vacuous otherwise
    for gate in DEFERRED_GATES:
        res = subprocess.run(
            [sys.executable, str(TOOLS / "validate_architecture_gates.py"), "--gate", gate],
            capture_output=True, text=True, check=False,
        )
        assert res.returncode == 2, (gate, res.stdout)
        assert "GATE_NOT_IMPLEMENTED" in res.stdout


# --- ADR-011 D1/D2 manifest-schema checks (GATE2-R1-D1A-STABILIZATION-2026-10-05) -
# Focused unit tests against `parse_module_manifest` directly — no file-tree gate
# run needed for pure schema validation. D3 (identifier-attribution semantics),
# D4/D5's scanning behavior, and D6 (the SQL lexer) are a separate, deferred slice
# and are deliberately not exercised here.


def _pmm_base_raw() -> dict:
    """ADR-011 D2's own worked example, minus `owned_schemas`/`external_table_references`
    (both optional) so each test below can add exactly the field it means to exercise."""
    return {
        "version": 1,
        "modules": {
            "membership": {
                "domain": "MEM-01",
                "owned_table_prefixes": ["mem_"],
                "public_interfaces": ["app.modules.membership.interface"],
            },
        },
    }


def _pmm_tree(tmp: Path, raw, modules_root: str = "app.modules") -> Path:
    """A throwaway modules tree that satisfies ADR-011 D2's interface-existence
    precondition (R1-F13) for whatever `raw` declares — a directory per declared
    module plus exactly its declared `public_interfaces` files. Built from `raw`
    itself so that each schema test below still fails (or passes) for the one
    reason it names, rather than for a missing interface file it never meant to
    exercise. Deliberately tolerant of the deliberately-malformed manifests
    several of these tests hand it."""
    modules_dir = _md_tree(tmp)
    if isinstance(raw, dict) and isinstance(raw.get("modules"), dict):
        for name in raw["modules"]:
            if isinstance(name, str) and name.isidentifier():
                (modules_dir / name).mkdir(exist_ok=True)
    _md_materialize_interfaces(modules_dir, raw, modules_root)
    return modules_dir


def _pmm_parse(raw, modules_root: str = "app.modules"):
    """`parse_module_manifest` against a tree built by `_pmm_tree` and discarded
    immediately. `modules_dir` is a required argument as of R1-F13, and these are
    pure-schema unit tests with no tree of their own."""
    with tempfile.TemporaryDirectory() as tmp:
        modules_dir = _pmm_tree(Path(tmp), raw, modules_root)
        return parse_module_manifest(raw, modules_root, modules_dir)


def _assert_pmm_input_error(raw: dict, modules_root: str = "app.modules") -> None:
    try:
        _pmm_parse(raw, modules_root)
    except GateInputError:
        return
    raise AssertionError(f"expected GateInputError, none raised for {raw!r}")


def test_d2_module_name_invalid_identifier_is_error():
    for bad_name in ("Membership", "mem-ber", "123abc", "mem.ber"):
        raw = _pmm_base_raw()
        raw["modules"][bad_name] = raw["modules"].pop("membership")
        _assert_pmm_input_error(raw)


def test_d2_module_name_valid_identifier_passes():
    raw = _pmm_base_raw()
    out, _default_schema = _pmm_parse(raw)
    assert out["membership"].domain == "MEM-01"
    assert out["membership"].owned_table_prefixes == ("mem_",)


def test_d4_module_named_shared_or_root_is_reserved_error():
    # b5/c4: the reserved-importer set is {_shared, _root}, not only `_shared` —
    # `_root` fully matches `_MODULE_NAME_IDENT_RE` and must be refused too.
    for reserved in (SHARED_PACKAGE, "_root"):
        raw = _pmm_base_raw()
        entry = raw["modules"].pop("membership")
        entry["public_interfaces"] = [f"app.modules.{reserved}.interface"]
        raw["modules"][reserved] = entry
        _assert_pmm_input_error(raw)


def test_d2_prefix_floor_rejects_single_char_before_underscore():
    # b3: the floor is `+`, not `*` — "at least two characters before a mandatory
    # trailing underscore"; `a_` must now be rejected (it was accepted pre-fix).
    raw = _pmm_base_raw()
    raw["modules"]["membership"]["owned_table_prefixes"] = ["a_"]
    _assert_pmm_input_error(raw)


def test_d2_prefix_floor_accepts_two_chars_before_underscore():
    raw = _pmm_base_raw()
    raw["modules"]["membership"]["owned_table_prefixes"] = ["ab_"]
    out, _default_schema = _pmm_parse(raw)
    assert out["membership"].owned_table_prefixes == ("ab_",)


def test_d34_reserved_prefix_value_pg_is_rejected():
    # D3.4: `pg_` satisfies the floor (confirmed above) but is reserved and must
    # still be refused — the exact case the ADR calls out by name.
    raw = _pmm_base_raw()
    raw["modules"]["membership"]["owned_table_prefixes"] = ["pg_"]
    _assert_pmm_input_error(raw)


# --- R1-F12 / ADR-011 D2 prefix floor: denial + controls on every surface ---------
# `_PREFIX_FLOOR_RE` (applied in `parse_module_manifest`) already denied `a_` before
# this increment, and `test_d2_prefix_floor_rejects_single_char_before_underscore`
# above covers that one input at the in-memory parse layer. What was uncovered — and
# what F12's prefix half turns on, since an unbounded `a`/`a_` prefix claim is what
# the floor exists to refuse — is everything around it: the other two named inputs
# (`a`, `ab`), whether the ERROR actually *names* the offending input (the assertion
# above checks only the exception type, so a message naming nothing would pass it),
# whether the enforced pattern is still `+` rather than `*`, the `mem_`/`bil_`
# controls, and whether the denial survives the file-load and CLI surfaces instead of
# only the direct parse call.
_D2_FLOOR_DENIED = ("a", "ab", "a_")
_D2_FLOOR_ALLOWED = ("ab_", "mem_", "bil_")


def test_d2_prefix_floor_pattern_is_plus_not_star():
    # b3's whole point: `^[a-z][a-z0-9_]*_$` accepts `a_` (confirmed by execution
    # during adjudication). Pinning the enforced pattern makes a `+` -> `*`
    # weakening a direct test failure, not something only the input cases below
    # would catch indirectly.
    assert _PREFIX_FLOOR_RE.pattern == r"^[a-z][a-z0-9_]+_$"
    assert "*_$" not in _PREFIX_FLOOR_RE.pattern


def test_d2_prefix_floor_denies_named_inputs_with_named_error():
    for bad in _D2_FLOOR_DENIED:
        raw = _pmm_base_raw()
        raw["modules"]["membership"]["owned_table_prefixes"] = [bad]
        try:
            _pmm_parse(raw)
        except GateInputError as exc:
            msg = str(exc)
            # The ERROR must name the module, the offending entry, the field, and the
            # floor it was measured against — a bare "invalid manifest" would leave a
            # manifest author guessing which of several prefixes was refused.
            assert "'membership'" in msg, (bad, msg)
            assert repr(bad) in msg, (bad, msg)
            assert "owned_table_prefixes" in msg, (bad, msg)
            assert _PREFIX_FLOOR_RE.pattern in msg, (bad, msg)
        else:
            raise AssertionError(f"prefix {bad!r} was accepted by the floor")


def test_d2_prefix_floor_preserves_valid_controls():
    for good in _D2_FLOOR_ALLOWED:
        raw = _pmm_base_raw()
        raw["modules"]["membership"]["owned_table_prefixes"] = [good]
        out, _default_schema = _pmm_parse(raw)
        assert out["membership"].owned_table_prefixes == (good,), good


def test_d2_prefix_floor_denial_survives_manifest_load():
    # The floor must hold on the surface the gate actually uses (a manifest read off
    # disk via `load_module_manifest`), not only on a hand-built dict.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "module-manifest.json"
        # R1-F13: `load_module_manifest` now resolves declared interfaces against a
        # real tree, so one is scaffolded here. It satisfies the existence
        # precondition and nothing else — each assertion below still turns on the
        # prefix floor, which is what this test is about.
        modules_dir = _pmm_tree(Path(tmp), _pmm_base_raw())
        for bad in _D2_FLOOR_DENIED:
            raw = _pmm_base_raw()
            raw["modules"]["membership"]["owned_table_prefixes"] = [bad]
            path.write_text(json.dumps(raw))
            try:
                load_module_manifest(path, "app.modules", modules_dir)
            except GateInputError as exc:
                assert repr(bad) in str(exc), (bad, str(exc))
            else:
                raise AssertionError(f"prefix {bad!r} survived load_module_manifest")
        for good in _D2_FLOOR_ALLOWED:
            raw = _pmm_base_raw()
            raw["modules"]["membership"]["owned_table_prefixes"] = [good]
            path.write_text(json.dumps(raw))
            modules, _default_schema = load_module_manifest(path, "app.modules", modules_dir)
            assert modules["membership"].owned_table_prefixes == (good,), good


def test_d2_prefix_floor_denial_is_reported_as_gate_input_invalid():
    # Through the real gate against a real tree: the floor violation must become an
    # ERROR report under MODULE_DEPS_GATE_INPUT_INVALID that names the prefix, never
    # a FAIL and never a PASS.
    for bad in _D2_FLOOR_DENIED:
        modules = {"membership": _md_entry("MEM-01", [bad],
                                           ["app.modules.membership.interface"])}
        report = _md_run(modules, _md_base_build)
        _assert_md_input_error(report, f"prefix floor {bad!r}")
        assert any(repr(bad) in v.detail and "prefix floor" in v.detail
                   for v in report.violations), (bad, report.render())
    for good in _D2_FLOOR_ALLOWED:
        modules = {"membership": _md_entry("MEM-01", [good],
                                           ["app.modules.membership.interface"])}
        report = _md_run(modules, _md_base_build)
        assert report.status == PASS, (good, report.render())


def test_d2_prefix_floor_cli_output_and_exit_code():
    # The operator-facing surface: exit 2 with the offending prefix named in the
    # emitted report for each denied input, exit 0 for each control. Exercised as a
    # subprocess so the real `main()` argv path and exit code are what is measured.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        modules_dir = _md_tree(root)
        _md_base_build(modules_dir)
        manifest_path = root / "module-manifest.json"

        def cli(prefix):
            _md_write_manifest(modules_dir, manifest_path, {
                "membership": _md_entry("MEM-01", [prefix],
                                        ["app.modules.membership.interface"]),
            })
            return subprocess.run(
                [sys.executable, str(TOOLS / "validate_architecture_gates.py"), "--gate",
                 "module-deps", "--modules-dir", str(modules_dir), "--module-manifest",
                 str(manifest_path), "--json"],
                capture_output=True, text=True, check=False,
            )

        for bad in _D2_FLOOR_DENIED:
            res = cli(bad)
            assert res.returncode == 2, (bad, res.stdout + res.stderr)
            payload = json.loads(res.stdout)
            assert payload["status"] == ERROR, (bad, res.stdout)
            assert {v["code"] for v in payload["violations"]} == {
                "MODULE_DEPS_GATE_INPUT_INVALID"}, (bad, res.stdout)
            assert any(repr(bad) in v["detail"] for v in payload["violations"]), \
                (bad, res.stdout)
        for good in _D2_FLOOR_ALLOWED:
            res = cli(good)
            assert res.returncode == 0, (good, res.stdout + res.stderr)
            assert json.loads(res.stdout)["status"] == PASS, (good, res.stdout)


def test_d2_external_table_references_defaults_to_empty_tuple():
    raw = _pmm_base_raw()
    assert "external_table_references" not in raw["modules"]["membership"]
    out, _default_schema = _pmm_parse(raw)
    assert out["membership"].external_table_references == ()


def test_d2_external_table_references_valid_entries_are_stored():
    raw = _pmm_base_raw()
    raw["modules"]["membership"]["external_table_references"] = ["legacy_schema.legacy_table"]
    out, _default_schema = _pmm_parse(raw)
    assert out["membership"].external_table_references == ("legacy_schema.legacy_table",)


def test_d2_external_table_references_wildcard_entry_is_error():
    # D2/D3.5: "concrete identifiers only, no wildcards" — the cross-check that an
    # entry may not name another module's own prefix/schema is D3.5 attribution
    # logic and is deferred; only the shape (no wildcard) is schema-validated here.
    raw = _pmm_base_raw()
    raw["modules"]["membership"]["external_table_references"] = ["legacy_*"]
    _assert_pmm_input_error(raw)


def test_d2_default_schema_omitted_defaults_without_error():
    raw = _pmm_base_raw()
    assert "default_schema" not in raw
    _pmm_parse(raw)  # must not raise


def test_d2_default_schema_valid_identifier_passes():
    raw = _pmm_base_raw()
    raw["default_schema"] = "sm"
    _pmm_parse(raw)  # must not raise


def test_d2_default_schema_invalid_identifier_is_error():
    raw = _pmm_base_raw()
    raw["default_schema"] = "Not-Valid!"
    _assert_pmm_input_error(raw)


def test_d1_unknown_top_level_key_still_rejected_alongside_default_schema():
    # Guards against widening `_TOP_LEVEL_ALLOWED` by accident: `default_schema`
    # is now accepted, but an unrelated unknown top-level key is still refused.
    raw = _pmm_base_raw()
    raw["default_schema"] = "public"
    raw["bogus"] = True
    _assert_pmm_input_error(raw)


def test_d2_duplicate_overlap_detection_unchanged_same_module_nested_accepted():
    # Verdict C, carried forward unweakened by the D1/D2 additions above: one
    # module may own nested prefixes ('mem_' and 'mem_roster_').
    raw = _pmm_base_raw()
    raw["modules"]["membership"]["owned_table_prefixes"] = ["mem_", "mem_roster_"]
    out, _default_schema = _pmm_parse(raw)
    assert set(out["membership"].owned_table_prefixes) == {"mem_", "mem_roster_"}


def test_d2_duplicate_overlap_detection_unchanged_cross_module_overlap_rejected():
    raw = _pmm_base_raw()
    raw["modules"]["billing"] = {
        "domain": "BIL-02",
        "owned_table_prefixes": ["mem_roster_"],
        "public_interfaces": ["app.modules.billing.interface"],
    }
    _assert_pmm_input_error(raw)


def test_d2_duplicate_prefix_entry_within_module_still_rejected():
    raw = _pmm_base_raw()
    raw["modules"]["membership"]["owned_table_prefixes"] = ["mem_", "mem_"]
    _assert_pmm_input_error(raw)


# --- GATE2-R1-D1A-MANIFEST-COMPLETION-2026-10-05: three remaining ADR-011 D3
# manifest-level invariants -- owned_schemas reserved values (D3.4), owned_schemas
# disjoint from default_schema (D3.3(3)), and external_table_references never
# resolving to any declared module's owned prefix/schema (D3.5). Full D3
# identifier-attribution semantics used during SQL scanning (I-2) remain a
# separate, deferred slice -- not exercised here.


def test_d34_reserved_schema_value_pg_catalog_is_rejected():
    # D3.4: "pg_, pg_catalog, pg_temp and information_schema are rejected at
    # parse time as owned_table_prefixes OR owned_schemas values" -- pg_catalog
    # fully matches `_MODULE_NAME_IDENT_RE` and would otherwise silently pass
    # as an ordinary owned schema.
    raw = _pmm_base_raw()
    raw["modules"]["membership"]["owned_schemas"] = ["pg_catalog"]
    _assert_pmm_input_error(raw)


def test_d34_reserved_schema_value_pg_prefix_itself_is_rejected():
    # D3.4 names `pg_` explicitly: unlike `owned_table_prefixes`, `owned_schemas`
    # has no trailing-underscore floor to catch it incidentally, so the reserved
    # check alone must refuse it here.
    raw = _pmm_base_raw()
    raw["modules"]["membership"]["owned_schemas"] = ["pg_"]
    _assert_pmm_input_error(raw)


def test_d2_owned_schemas_non_reserved_value_passes():
    raw = _pmm_base_raw()
    raw["modules"]["membership"]["owned_schemas"] = ["sm"]
    out, _default_schema = _pmm_parse(raw)
    assert out["membership"].owned_schemas == ("sm",)


def test_d33_owned_schemas_entry_equal_to_default_schema_is_rejected():
    # b2(i): owned_schemas must be disjoint from default_schema -- otherwise a
    # module declaring the (implicit or explicit) default schema as its own
    # would capture every bare table resolved under it as state-1 clean.
    raw = _pmm_base_raw()
    assert "default_schema" not in raw  # implicit default is "public"
    raw["modules"]["membership"]["owned_schemas"] = ["public"]
    _assert_pmm_input_error(raw)


def test_d33_owned_schemas_entry_equal_to_custom_default_schema_is_rejected():
    raw = _pmm_base_raw()
    raw["default_schema"] = "sm"
    raw["modules"]["membership"]["owned_schemas"] = ["sm"]
    _assert_pmm_input_error(raw)


def test_d33_owned_schemas_disjoint_from_default_schema_passes():
    raw = _pmm_base_raw()
    raw["default_schema"] = "sm"
    raw["modules"]["membership"]["owned_schemas"] = ["other_schema"]
    out, _default_schema = _pmm_parse(raw)
    assert out["membership"].owned_schemas == ("other_schema",)


def test_d35_external_table_reference_resolving_to_own_prefix_is_rejected():
    # D3.5/b1: external_table_references is a declaration, never an exemption --
    # a module may not launder its *own* owned table through this field either
    # ("including the current module's own").
    raw = _pmm_base_raw()
    raw["modules"]["membership"]["external_table_references"] = ["mem_roster"]
    _assert_pmm_input_error(raw)


def test_d35_external_table_reference_resolving_to_other_modules_prefix_is_rejected():
    raw = _pmm_base_raw()
    raw["modules"]["billing"] = {
        "domain": "BIL-02",
        "owned_table_prefixes": ["bil_"],
        "public_interfaces": ["app.modules.billing.interface"],
        "external_table_references": ["mem_roster"],
    }
    _assert_pmm_input_error(raw)


def test_d35_external_table_reference_resolving_to_owned_schema_is_rejected():
    raw = _pmm_base_raw()
    raw["modules"]["membership"]["owned_schemas"] = ["sm"]
    raw["modules"]["billing"] = {
        "domain": "BIL-02",
        "owned_table_prefixes": ["bil_"],
        "public_interfaces": ["app.modules.billing.interface"],
        "external_table_references": ["sm.some_table"],
    }
    _assert_pmm_input_error(raw)


def test_d35_external_table_reference_wrapped_in_default_schema_is_rejected():
    # The default-schema-strip rule (D3.3 rule 2) must apply to
    # external_table_references too, or wrapping an owned prefix in the default
    # schema ("public.mem_roster" instead of "mem_roster") would bypass D3.5
    # entirely.
    raw = _pmm_base_raw()
    raw["modules"]["billing"] = {
        "domain": "BIL-02",
        "owned_table_prefixes": ["bil_"],
        "public_interfaces": ["app.modules.billing.interface"],
        "external_table_references": ["public.mem_roster"],
    }
    _assert_pmm_input_error(raw)


def test_d35_external_table_reference_not_resolving_to_any_owner_passes():
    raw = _pmm_base_raw()
    raw["modules"]["membership"]["owned_schemas"] = ["sm"]
    raw["modules"]["membership"]["external_table_references"] = ["legacy_schema.legacy_table"]
    out, _default_schema = _pmm_parse(raw)
    assert out["membership"].external_table_references == ("legacy_schema.legacy_table",)


# --- ADR-011 D3 pure table-identifier attribution helper (increment D1a) ------
#
# `attribute_table_identifier` is a standalone, pure function -- GATE2-R1-D1A-
# ATTRIBUTION-HELPER-2026-10-05.md. GATE2-R1-D1A-SCANNER-WIRING-2026-10-05 wired
# it into the live `_scan_sql_text` path (see the `_md_run`-based tests further
# below for that live-path coverage). These tests call it directly with
# hand-built `ModuleEntry` objects -- no manifest JSON, no file-tree gate run,
# matching the house style the D1/D2/D3-manifest tests above already use for a
# pure function.

_ATTR_DEFAULT_SCHEMA = "public"


def _attr_entry(name, prefixes=(), schemas=(), ext_refs=(), domain=None):
    return ModuleEntry(
        name=name,
        domain=domain or f"{name[:3].upper()}-01",
        owned_table_prefixes=tuple(prefixes),
        owned_schemas=tuple(schemas),
        public_interfaces=(f"app.modules.{name}.interface",),
        external_table_references=tuple(ext_refs),
    )


_ATTR_BILLING = _attr_entry("billing", prefixes=["bil_"])
_ATTR_MEMBERSHIP_SCHEMA = _attr_entry("membership", schemas=["sm"])
_ATTR_MODULES = {"billing": _ATTR_BILLING, "membership": _ATTR_MEMBERSHIP_SCHEMA}


def test_attr_bil_invoices_unquoted_variants_attribute_identically_p0():
    # ADR-011 D3.1 (PostgreSQL case semantics) + D3.3 rule 2 (default-schema
    # stripping): a bare name, an explicitly `public`-qualified name, and every
    # unquoted case variant of both must all resolve to the same owner.
    for raw in ("bil_invoices", "BIL_INVOICES", "Bil_Invoices",
               "public.bil_invoices", "PUBLIC.BIL_INVOICES", "Public.Bil_Invoices"):
        out = attribute_table_identifier(raw, _ATTR_MODULES, "billing", _ATTR_DEFAULT_SCHEMA)
        assert out.state == ATTR_OWNED, (raw, out)
        assert out.owner == "billing", (raw, out)


def test_attr_quoted_identifier_preserves_case_and_is_unattributed():
    # ADR-011 D3.1: a double-quoted identifier preserves case exactly -- it is
    # therefore a genuinely different identifier from the lowercase
    # `bil_invoices` the unquoted P0 case resolves against, and attributes
    # differently (unattributed: no module owns the exact-case string).
    out = attribute_table_identifier('"BIL_INVOICES"', _ATTR_MODULES, "billing",
                                     _ATTR_DEFAULT_SCHEMA)
    assert out.state == ATTR_UNATTRIBUTED, out
    assert out.owner is None, out


def test_attr_quoted_identifier_under_default_schema_still_preserves_case():
    out = attribute_table_identifier('public."BIL_INVOICES"', _ATTR_MODULES, "billing",
                                     _ATTR_DEFAULT_SCHEMA)
    assert out.state == ATTR_UNATTRIBUTED, out


def test_attr_quoted_lowercase_identifier_matches_like_unquoted():
    # Quoting alone does not change the outcome when the quoted text already
    # matches the lower-case form an unquoted identifier would casefold to.
    out = attribute_table_identifier('"bil_invoices"', _ATTR_MODULES, "billing",
                                     _ATTR_DEFAULT_SCHEMA)
    assert out.state == ATTR_OWNED, out
    assert out.owner == "billing", out


def test_attr_three_or_more_dotted_parts_is_unattributed_error():
    # ADR-011 D3.3 rule 1: a cross-database reference is outside the ownership
    # model entirely -- ERROR, not a silent pass.
    for raw in ("db.schema.bil_invoices", "a.b.c.d"):
        out = attribute_table_identifier(raw, _ATTR_MODULES, "billing", _ATTR_DEFAULT_SCHEMA)
        assert out.state == ATTR_UNATTRIBUTED, (raw, out)
        assert out.owner is None, (raw, out)


def test_attr_schema_owner_and_prefix_owner_conflict_is_unattributed_error():
    # membership owns schema "sm"; billing owns prefix "bil_". "sm.bil_invoices"
    # resolves ambiguously -- schema says membership, prefix says billing.
    # ADR-011 D3.3 rule 4: never resolved by iteration order, always ERROR.
    out = attribute_table_identifier("sm.bil_invoices", _ATTR_MODULES, "billing",
                                     _ATTR_DEFAULT_SCHEMA)
    assert out.state == ATTR_UNATTRIBUTED, out
    assert out.owner is None, out
    assert "membership" in out.reason and "billing" in out.reason, out.reason


def test_attr_schema_owner_alone_resolves_clean_when_no_conflicting_prefix():
    # Control for the conflict test above: same schema-owned identifier, but
    # the table part matches no other module's prefix -- schema governs cleanly.
    out = attribute_table_identifier("sm.roster", _ATTR_MODULES, "membership",
                                     _ATTR_DEFAULT_SCHEMA)
    assert out.state == ATTR_OWNED, out
    assert out.owner == "membership", out


def test_attr_cte_local_name_is_attributed_as_cte():
    out = attribute_table_identifier("recent_orders", _ATTR_MODULES, "billing",
                                     _ATTR_DEFAULT_SCHEMA, cte_names=frozenset({"recent_orders"}))
    assert out.state == ATTR_CTE, out
    assert out.owner is None, out


def test_attr_cte_local_name_takes_precedence_over_owned_prefix():
    # "bil_scratch" would otherwise resolve ATTR_OWNED via the "bil_" prefix --
    # CTE-local binding (ADR-011 D3.2 state 3) is checked first and wins.
    out = attribute_table_identifier("bil_scratch", _ATTR_MODULES, "billing",
                                     _ATTR_DEFAULT_SCHEMA, cte_names=frozenset({"bil_scratch"}))
    assert out.state == ATTR_CTE, out


def test_attr_reserved_system_schema_pg_catalog_is_system():
    out = attribute_table_identifier("pg_catalog.pg_class", _ATTR_MODULES, "billing",
                                     _ATTR_DEFAULT_SCHEMA)
    assert out.state == ATTR_SYSTEM, out
    assert out.owner is None, out


def test_attr_reserved_system_schema_information_schema_is_system():
    out = attribute_table_identifier("information_schema.tables", _ATTR_MODULES, "billing",
                                     _ATTR_DEFAULT_SCHEMA)
    assert out.state == ATTR_SYSTEM, out


def test_attr_bare_pg_prefixed_identifier_is_system():
    out = attribute_table_identifier("pg_stat_activity", _ATTR_MODULES, "billing",
                                     _ATTR_DEFAULT_SCHEMA)
    assert out.state == ATTR_SYSTEM, out


def test_attr_table_part_pg_prefix_under_nonreserved_schema_is_still_system():
    out = attribute_table_identifier("sm.pg_internal_scratch", _ATTR_MODULES, "membership",
                                     _ATTR_DEFAULT_SCHEMA)
    assert out.state == ATTR_SYSTEM, out


def test_attr_declared_external_reference_bare_is_clean():
    modules = dict(_ATTR_MODULES)
    modules["billing"] = _attr_entry("billing", prefixes=["bil_"], ext_refs=["legacy_table"])
    out = attribute_table_identifier("legacy_table", modules, "billing", _ATTR_DEFAULT_SCHEMA)
    assert out.state == ATTR_EXTERNAL, out
    assert out.owner is None, out


def test_attr_declared_external_reference_schema_qualified_is_clean():
    modules = dict(_ATTR_MODULES)
    modules["billing"] = _attr_entry("billing", prefixes=["bil_"],
                                     ext_refs=["legacy_schema.legacy_table"])
    out = attribute_table_identifier("legacy_schema.legacy_table", modules, "billing",
                                     _ATTR_DEFAULT_SCHEMA)
    assert out.state == ATTR_EXTERNAL, out


def test_attr_external_reference_is_scoped_to_the_declaring_module_only():
    # The same identifier, queried as if a DIFFERENT module (which declared no
    # such reference) were the importer, must not inherit billing's declared
    # external reference -- a deliberate, disclosed scoping decision (see
    # GATE2-R1-D1A-ATTRIBUTION-HELPER-2026-10-05.md LIMITATIONS).
    modules = dict(_ATTR_MODULES)
    modules["billing"] = _attr_entry("billing", prefixes=["bil_"], ext_refs=["legacy_table"])
    out = attribute_table_identifier("legacy_table", modules, "membership", _ATTR_DEFAULT_SCHEMA)
    assert out.state == ATTR_UNATTRIBUTED, out


def test_attr_unknown_identifier_is_unattributed_error():
    out = attribute_table_identifier("totally_unowned_thing", _ATTR_MODULES, "billing",
                                     _ATTR_DEFAULT_SCHEMA)
    assert out.state == ATTR_UNATTRIBUTED, out
    assert out.owner is None, out


def test_attr_cross_module_bare_identifier_is_owned_by_the_other_module():
    # D3.2 states 1/2 both collapse to ATTR_OWNED; the caller decides own-vs-
    # other by comparing `owner` to its own importer name, exactly as
    # `_scan_sql_text` does with this outcome's `owner` field.
    out = attribute_table_identifier("bil_invoices", _ATTR_MODULES, "membership",
                                     _ATTR_DEFAULT_SCHEMA)
    assert out.state == ATTR_OWNED, out
    assert out.owner == "billing", out
    assert out.owner != "membership"


def test_attr_is_pure_deterministic_and_does_not_mutate_inputs():
    modules_snapshot = dict(_ATTR_MODULES)
    cte_names = frozenset({"recent_orders"})
    first = attribute_table_identifier("bil_invoices", _ATTR_MODULES, "billing",
                                       _ATTR_DEFAULT_SCHEMA, cte_names)
    second = attribute_table_identifier("bil_invoices", _ATTR_MODULES, "billing",
                                        _ATTR_DEFAULT_SCHEMA, cte_names)
    assert first == second
    assert _ATTR_MODULES == modules_snapshot
    assert _ATTR_MODULES["billing"] is _ATTR_BILLING
    assert cte_names == frozenset({"recent_orders"})


def test_attr_outcome_is_a_structured_dataclass_not_a_bare_bool():
    out = attribute_table_identifier("bil_invoices", _ATTR_MODULES, "billing",
                                     _ATTR_DEFAULT_SCHEMA)
    assert isinstance(out, AttributionOutcome)
    assert not isinstance(out, bool)
    assert hasattr(out, "state") and hasattr(out, "owner") and hasattr(out, "reason")


# --- ADR-011 D3.2 state 3 pure lexical CTE-name collection (increment D6a) ----
#
# `_collect_cte_names` is a standalone, pure, lexical-only helper -- GATE2-R1-
# D6-CTE-HELPER-2026-10-05.md. It is deliberately NOT wired into
# `_scan_sql_text`/`run_module_deps_gate` by this increment (see the module-level
# comment on `_collect_cte_names` itself), so these tests call it directly,
# matching the house style the `attribute_table_identifier` pure-function tests
# above already use rather than driving it through a fixture tree.

try:
    from validate_architecture_gates import _collect_cte_names
except ImportError:
    pass


def test_cte_multiple_bindings_in_one_with_list_are_both_collected():
    # Requirement 1: multiple CTEs in one `WITH` list.
    sql = "WITH a AS (SELECT 1), b AS (SELECT 2) SELECT * FROM a, b"
    assert _collect_cte_names(sql) == frozenset({"a", "b"})


def test_cte_nested_subquery_identifiers_inside_the_body_are_not_collected():
    # Requirement 2: a nested FROM/subquery whose identifiers must NOT be
    # collected -- only the CTE's own bound name is a depth-0 binding; the
    # real table it selects from is not.
    sql = "WITH recent_orders AS (SELECT * FROM orders WHERE total > 100) SELECT * FROM recent_orders"
    out = _collect_cte_names(sql)
    assert out == frozenset({"recent_orders"}), out
    assert "orders" not in out


def test_cte_quoted_name_preserves_case_per_existing_normalisation_rule():
    # Requirement 3: a quoted CTE name -- case preserved, quotes stripped, via
    # the same `_normalize_identifier_segment` rule D3.1 already defines; no
    # second normalisation rule is invented here.
    sql = 'WITH "Recent_Orders" AS (SELECT 1) SELECT * FROM "Recent_Orders"'
    assert _collect_cte_names(sql) == frozenset({"Recent_Orders"})


def test_cte_unrelated_with_clause_produces_no_binding():
    # Requirement 4: an unrelated `WITH` (a storage-parameter clause, not a CTE
    # list -- there is no `name AS (` shape at all) must not produce a
    # binding; lexing fails closed at the very first token.
    sql = "CREATE TABLE foo (id int) WITH (fillfactor = 70)"
    assert _collect_cte_names(sql) == frozenset()


def test_cte_adversarial_nested_with_at_depth_one_is_not_a_false_depth_zero_binding():
    # Requirement 5: adversarial false-binding case. A naive scanner with no
    # depth tracking would see `WITH inner_cte AS (` textually and bind
    # `inner_cte` as if it were depth-0. It is actually nested one level deep
    # inside the outer `FROM (...)` subquery, so it must NOT be collected.
    sql = "SELECT * FROM (WITH inner_cte AS (SELECT 1) SELECT * FROM inner_cte) AS sub"
    assert _collect_cte_names(sql) == frozenset()


def test_cte_no_with_keyword_at_all_collects_nothing():
    assert _collect_cte_names("SELECT * FROM billing_invoice") == frozenset()


def test_cte_empty_text_collects_nothing():
    assert _collect_cte_names("") == frozenset()


def test_cte_unbalanced_body_paren_fails_closed_to_no_binding():
    # An unterminated body (no matching closing paren) is unlexable -- fails
    # closed to zero names rather than guessing the body ends at the string's
    # end.
    sql = "WITH a AS (SELECT * FROM billing_invoice"
    assert _collect_cte_names(sql) == frozenset()


def test_cte_is_pure_and_does_not_mutate_or_depend_on_call_order():
    sql = "WITH a AS (SELECT 1) SELECT * FROM a"
    first = _collect_cte_names(sql)
    second = _collect_cte_names(sql)
    assert first == second == frozenset({"a"})
    assert sql == "WITH a AS (SELECT 1) SELECT * FROM a"


# --- GATE2-R1-D6-CTE-LEXICAL-HARDENING-2026-10-05 -------------------------------
#
# `_collect_cte_names` remains the same unwired pure helper (see the module-level
# comment above it); this section hardens it against deceptive `WITH fake AS (`
# text inside single-quoted SQL string literals and SQL line/block comments, per
# `GATE2-R1-D6-CTE-LEXICAL-HARDENING-2026-10-05.md`. Positive cases first (real
# binding must still be found, including after a quoted/commented region ends),
# then adversarial negatives (a deceptive `WITH` inside any of those regions
# must NEVER create a binding), matching the house style above exactly.

def test_cte_recursive_still_not_recognised_lexical_hardening_is_orthogonal():
    # Baseline: this increment must not accidentally start recognising
    # RECURSIVE -- that is a separate, already-disclosed gap, out of scope.
    sql = "WITH RECURSIVE cte AS (SELECT 1) SELECT * FROM cte"
    assert _collect_cte_names(sql) == frozenset()


def test_cte_real_binding_after_single_quoted_text_is_still_collected():
    # Positive: a real CTE appearing textually AFTER a single-quoted literal
    # (even one containing deceptive `WITH fake AS (` text of its own) must
    # still be correctly bound once the literal closes.
    sql = "SELECT 'WITH fake AS (' AS decoy; WITH real_cte AS (SELECT 1) SELECT * FROM real_cte"
    assert _collect_cte_names(sql) == frozenset({"real_cte"})


def test_cte_real_binding_after_line_comment_is_still_collected():
    # Positive: a real CTE appearing after a `--` line comment (containing
    # its own deceptive `WITH fake AS (` text) must still bind correctly.
    sql = "-- WITH fake AS (\nWITH real_cte AS (SELECT 1) SELECT * FROM real_cte"
    assert _collect_cte_names(sql) == frozenset({"real_cte"})


def test_cte_real_binding_after_block_comment_is_still_collected():
    # Positive: same, for a `/* */` block comment.
    sql = "/* WITH fake AS ( */ WITH real_cte AS (SELECT 1) SELECT * FROM real_cte"
    assert _collect_cte_names(sql) == frozenset({"real_cte"})


def test_cte_doubled_quote_escape_inside_literal_does_not_close_early():
    # Positive/adversarial combined: SQL's `''` doubled-quote escape inside
    # the decoy literal must not be mistaken for the literal's close --
    # otherwise the remaining `s WITH fake AS ('` text would leak out as
    # ordinary SQL. The real CTE after it must still be the only binding.
    sql = "SELECT 'it''s WITH fake AS (' AS decoy; WITH real_cte AS (SELECT 1) SELECT * FROM real_cte"
    assert _collect_cte_names(sql) == frozenset({"real_cte"})


def test_cte_nested_block_comment_per_postgresql_nesting_semantics():
    # Positive: PostgreSQL block comments nest (verified against the live
    # PostgreSQL documentation -- see the source comment on
    # `_skip_block_comment`), so a `/* outer /* inner */ still-open */` is
    # ONE comment, not a comment that closes at the first `*/`. If nesting
    # were not honoured, the fake `WITH` inside would already be hidden by
    # the outer comment's own un-nested close -- so this also exercises the
    # adversarial decoy, not only the nesting mechanics.
    sql = ("/* outer /* WITH fake AS ( */ still inside outer comment */ "
           "WITH real_cte AS (SELECT 1) SELECT * FROM real_cte")
    assert _collect_cte_names(sql) == frozenset({"real_cte"})


def test_cte_fake_with_inside_single_quoted_literal_produces_no_binding():
    # Adversarial negative: the task's primary adversarial case. `WITH fake
    # AS (` inside an ordinary single-quoted literal must never bind.
    sql = "SELECT 'WITH fake AS (' AS decoy"
    assert _collect_cte_names(sql) == frozenset()


def test_cte_fake_with_inside_doubled_quote_escaped_literal_produces_no_binding():
    # Adversarial negative: same, but the literal itself uses doubled-quote
    # escaping before the decoy text.
    sql = "SELECT 'it''s WITH fake AS (' AS decoy"
    assert _collect_cte_names(sql) == frozenset()


def test_cte_fake_with_inside_unclosed_literal_produces_no_binding():
    # Adversarial negative: an unclosed literal running to end of input must
    # fail closed to zero bindings, not crash and not guess a close.
    sql = "SELECT 'unclosed decoy WITH fake AS ("
    assert _collect_cte_names(sql) == frozenset()


def test_cte_real_binding_before_unclosed_literal_is_still_kept():
    # Fail-closed boundary case: a real binding that lexically completes
    # BEFORE an unclosed literal later in the same text must still be kept
    # -- only scanning past the unclosed literal stops, not the whole result.
    sql = "WITH a AS (SELECT 1) SELECT 'unclosed decoy WITH fake AS ("
    assert _collect_cte_names(sql) == frozenset({"a"})


def test_cte_fake_with_inside_line_comment_produces_no_binding():
    # Adversarial negative: `WITH fake AS (` inside a `--` line comment must
    # never bind.
    sql = "-- WITH fake AS (\nSELECT 1"
    assert _collect_cte_names(sql) == frozenset()


def test_cte_fake_with_inside_block_comment_produces_no_binding():
    # Adversarial negative: same, for a `/* */` block comment.
    sql = "/* WITH fake AS ( */ SELECT 1"
    assert _collect_cte_names(sql) == frozenset()


def test_cte_fake_with_inside_unclosed_block_comment_produces_no_binding():
    # Adversarial negative: an unterminated block comment running to end of
    # input must fail closed to zero bindings, never crash, never guess a
    # close.
    sql = "/* WITH fake AS ( \nWITH also_fake AS (SELECT 1)"
    assert _collect_cte_names(sql) == frozenset()


def test_cte_unbalanced_parens_inside_literal_in_real_cte_body_does_not_corrupt_depth():
    # Adversarial negative (depth corruption, not false binding): a real
    # CTE's body contains a single-quoted literal whose content is bare
    # parens with no matching partner (`'((('`). Without skipping the
    # literal, those parens would shift `_skip_balanced_parens`'s depth
    # counter and either mis-locate the body's real closing paren or report
    # the body as unbalanced. The body must still be found to end exactly at
    # its own real closing paren, and nothing past it (a second, unrelated
    # table reference) is swept into the CTE's name set.
    sql = "WITH a AS (SELECT '(((' AS x) SELECT * FROM a, trailing_tbl"
    out = _collect_cte_names(sql)
    assert out == frozenset({"a"}), out
    assert "trailing_tbl" not in out


def test_cte_unbalanced_parens_inside_comment_in_real_cte_body_does_not_corrupt_depth():
    # Adversarial negative (depth corruption via comment, not literal): same
    # hazard, but the unbalanced paren is inside a `/* */` comment inside the
    # CTE body rather than a string literal.
    sql = "WITH a AS (SELECT 1 /* fake ( unbalanced */) SELECT * FROM a, trailing_tbl"
    out = _collect_cte_names(sql)
    assert out == frozenset({"a"}), out
    assert "trailing_tbl" not in out


def test_cte_backslash_escaped_quote_inside_literal_does_not_close_early():
    # Adversarial negative: a PostgreSQL `E'...'`-style backslash-escaped
    # quote (`\'`) inside the decoy literal must not be read as the
    # literal's real close -- `_skip_single_quoted_literal` treats a
    # backslash as escaping the next character for every single-quoted
    # literal, closing this exact false-binding risk (see its own
    # docstring). The real CTE after the literal is the only binding.
    sql = "SELECT E'foo\\' WITH fake AS (' AS decoy; WITH real_cte AS (SELECT 1) SELECT * FROM real_cte"
    assert _collect_cte_names(sql) == frozenset({"real_cte"})


# --- GATE2-R1-D6-CTE-DOLLAR-QUOTE-2026-10-05 ------------------------------------
#
# `_collect_cte_names` remains the same unwired pure helper. This section hardens
# it (and `_skip_balanced_parens`) against deceptive `WITH fake AS (` text and
# deceptive parens inside PostgreSQL dollar-quoted strings (`$$...$$` /
# `$tag$...$tag$`), per `GATE2-R1-D6-CTE-DOLLAR-QUOTE-2026-10-05.md`. Matches the
# house style above: adversarial negatives, a depth-corruption case, tag-matching
# cases, an unterminated-opener fail-closed case, a real binding after a
# dollar-quoted string, and the `$1` positional-parameter non-opener case.

def test_cte_fake_with_inside_dollar_quoted_string_produces_no_binding():
    # Adversarial negative: `WITH fake AS (` inside a `$$...$$` dollar-quoted
    # string must never bind.
    sql = "SELECT $$WITH fake AS ($$ AS decoy"
    assert _collect_cte_names(sql) == frozenset()


def test_cte_fake_with_inside_tagged_dollar_quoted_string_produces_no_binding():
    # Adversarial negative: same, for a tagged delimiter (`$tag$...$tag$`).
    sql = "SELECT $tag$WITH fake AS ($tag$ AS decoy"
    assert _collect_cte_names(sql) == frozenset()


def test_cte_unbalanced_parens_inside_dollar_quoted_string_does_not_corrupt_depth():
    # Adversarial negative (depth corruption, not false binding): a real CTE's
    # body contains a dollar-quoted string whose content is bare, unmatched
    # parens. Without skipping it atomically, those parens would shift
    # `_skip_balanced_parens`'s depth counter and either mis-locate the body's
    # real closing paren or sweep a trailing, unrelated table reference into
    # the result.
    sql = "WITH a AS (SELECT $$(((.$$ AS x) SELECT * FROM a, trailing_tbl"
    out = _collect_cte_names(sql)
    assert out == frozenset({"a"}), out
    assert "trailing_tbl" not in out


def test_cte_mismatched_dollar_quote_tag_does_not_close_early():
    # Adversarial negative: a closing delimiter with a DIFFERENT tag than the
    # opener does not close the string -- `$a$...$b$...$a$` only closes at the
    # matching `$a$`, so the deceptive `WITH fake AS (` between the mismatched
    # `$b$` and the real closing `$a$` must stay hidden inside the one string.
    sql = "SELECT $a$ $b$ WITH fake AS ( $a$ AS decoy"
    assert _collect_cte_names(sql) == frozenset()


def test_cte_unterminated_dollar_quoted_opener_fails_closed():
    # Fail-closed: an opener with no matching closing delimiter anywhere in
    # the text must consume the rest of the text (never guess a close, never
    # treat the remainder as ordinary SQL) and collect no bindings.
    sql = "SELECT $$unterminated decoy WITH fake AS ("
    assert _collect_cte_names(sql) == frozenset()


def test_cte_real_binding_before_unterminated_dollar_quote_is_still_kept():
    # Fail-closed boundary case, mirroring the single-quoted-literal
    # equivalent above: a real binding that lexically completes BEFORE an
    # unterminated dollar-quoted string later in the same text must still be
    # kept -- only scanning past the unterminated region stops.
    sql = "WITH a AS (SELECT 1) SELECT $$unterminated decoy WITH fake AS ("
    assert _collect_cte_names(sql) == frozenset({"a"})


def test_cte_real_binding_after_dollar_quoted_string_is_still_collected():
    # Positive: a real CTE appearing textually AFTER a dollar-quoted string
    # (even one containing its own deceptive `WITH fake AS (` text) must
    # still be correctly bound once the dollar-quoted string closes.
    sql = "SELECT $$WITH fake AS ($$ AS decoy; WITH real_cte AS (SELECT 1) SELECT * FROM real_cte"
    assert _collect_cte_names(sql) == frozenset({"real_cte"})


def test_cte_matching_tagged_dollar_quote_then_real_binding_is_collected():
    # Positive: a correctly-matched tagged delimiter closes normally, and the
    # real CTE after it is collected.
    sql = "SELECT $tag$decoy text$tag$ AS x; WITH real_cte AS (SELECT 1) SELECT * FROM real_cte"
    assert _collect_cte_names(sql) == frozenset({"real_cte"})


def test_cte_positional_parameter_is_not_misread_as_dollar_quote_opener():
    # Adversarial negative: `$1` (a positional parameter) must never be
    # treated as a dollar-quote opener -- it has no second `$` immediately
    # following and no valid identifier-shaped tag closed by one, so the `$`
    # is left as an ordinary character and the real CTE around it is
    # collected normally.
    sql = "WITH a AS (SELECT $1 AS x) SELECT * FROM a WHERE x = $1"
    assert _collect_cte_names(sql) == frozenset({"a"})


# --- GATE2-R1-D6-CTE-UNICODE-DOLLAR-2026-10-05 ----------------------------------
#
# `_collect_cte_names` remains the same unwired pure helper. The prior section's
# own residual-risk disclosure ("an unrecognised non-ASCII dollar-quote tag is
# safe-direction only") was WRONG: an unrecognised opener does not degrade to a
# missed binding, it degrades to the entire dollar-quoted region being scanned as
# ordinary top-level text, which can manufacture a FALSE binding. This section
# proves the attack, proves the fix, and locks both the Unicode-tag behaviour and
# every pre-existing ASCII/empty-tag/positional-parameter shape as regressions.

def test_cte_fake_with_inside_non_ascii_tagged_dollar_quoted_string_produces_no_binding():
    # The exact reproducing probe: an unrecognised `$café$...$café$` region
    # used to be scanned as ordinary top-level text, so the `WITH fake AS (`
    # inside it was collected as a FALSE binding. Fixed: the tag is now
    # recognised via PostgreSQL's real (Unicode-aware) identifier rules, so
    # the whole region is skipped atomically and `fake` is never bound.
    sql = "SELECT $café$ WITH fake AS (SELECT 1) $café$"
    out = _collect_cte_names(sql)
    assert "fake" not in out, out
    assert out == frozenset(), out


def test_cte_fake_with_inside_cjk_tagged_dollar_quoted_string_produces_no_binding():
    # Second non-Latin tag shape (CJK, not just a Latin letter with
    # diacritics) -- confirms the fix is genuinely Unicode-general
    # (`str.isalpha()`-based), not a narrow café-specific patch.
    sql = "SELECT $标签$ WITH fake AS (SELECT 1) $标签$"
    out = _collect_cte_names(sql)
    assert "fake" not in out, out
    assert out == frozenset(), out


def test_cte_decoy_parens_inside_non_ascii_tagged_dollar_quoted_string_do_not_corrupt_depth():
    # Depth-corruption variant with a non-ASCII tag: a real CTE's body
    # contains a non-ASCII-tagged dollar-quoted string full of bare,
    # unmatched parens. The region must still be skipped atomically so
    # `_skip_balanced_parens` locates the body's real closing paren and does
    # not sweep the trailing table reference into the result.
    sql = "WITH a AS (SELECT $café$(((.$café$ AS x) SELECT * FROM a, trailing_tbl"
    out = _collect_cte_names(sql)
    assert out == frozenset({"a"}), out
    assert "trailing_tbl" not in out


def test_cte_malformed_non_ascii_dollar_quote_region_fails_closed():
    # Malformed/unclosed region: the opener `$café$` is well-formed and
    # recognised, but no matching closing `$café$` ever appears before the
    # text ends. Must fail closed -- consume the rest of the text, collect
    # nothing past it, never guess a close or fall back to scanning the
    # remainder (including the deceptive `WITH fake AS (`) as ordinary SQL.
    sql = "SELECT $café$ WITH fake AS (SELECT 1)"
    assert _collect_cte_names(sql) == frozenset()


def test_cte_mismatched_non_ascii_dollar_quote_tag_does_not_close_early():
    # Mismatched tags: `$café$ ... $cafe$ ... $café$` (note: the middle tag
    # drops the accent, a one-character difference) must NOT close at the
    # mismatched `$cafe$` -- only the byte-for-byte-identical `$café$` may
    # close it, keeping the deceptive `WITH fake AS (` hidden inside one
    # single region.
    sql = "SELECT $café$ $cafe$ WITH fake AS ( $café$ AS decoy"
    assert _collect_cte_names(sql) == frozenset()


def test_cte_case_difference_dollar_quote_tag_mismatch_does_not_close_early():
    # Mismatched tags via a pure case difference (`$Tag$` vs `$tag$`) --
    # PostgreSQL dollar-quote tags are matched case-sensitively, so a
    # same-spelling-different-case closer must not close the string either.
    sql = "SELECT $Tag$ $tag$ WITH fake AS ( $Tag$ AS decoy"
    assert _collect_cte_names(sql) == frozenset()


def test_cte_positional_parameter_still_not_misread_after_unicode_fix():
    # Regression: `$1` must still never be treated as an opener now that tag
    # recognition is Unicode-aware -- a digit can never start a tag under
    # either the old ASCII rule or the new Unicode rule.
    sql = "WITH a AS (SELECT $1 AS x) SELECT * FROM a WHERE x = $1"
    assert _collect_cte_names(sql) == frozenset({"a"})


def test_cte_ascii_and_empty_tag_dollar_quotes_still_work_after_unicode_fix():
    # Regression: the pre-existing ASCII-tagged and empty-tag (`$$...$$`)
    # shapes from GATE2-R1-D6-CTE-DOLLAR-QUOTE-2026-10-05 must still behave
    # identically after switching the tag matcher to Unicode-aware logic.
    sql_empty = "SELECT $$WITH fake AS ($$ AS decoy"
    assert _collect_cte_names(sql_empty) == frozenset()
    sql_ascii = "SELECT $tag$WITH fake AS ($tag$ AS decoy"
    assert _collect_cte_names(sql_ascii) == frozenset()


def test_cte_real_binding_after_non_ascii_tagged_dollar_quoted_string_is_still_collected():
    # Positive: a real CTE appearing textually AFTER a correctly-closed
    # non-ASCII-tagged dollar-quoted string (even one containing its own
    # deceptive `WITH fake AS (` text) must still be correctly bound once
    # the region closes.
    sql = "SELECT $café$WITH fake AS ($café$ AS decoy; WITH real_cte AS (SELECT 1) SELECT * FROM real_cte"
    assert _collect_cte_names(sql) == frozenset({"real_cte"})


# --- GATE2-R1-D6-COMBINING-OPENER-REGRESSION-2026-10-05 -------------------------
#
# `_collect_cte_names` remains the same unwired pure helper. The prior section's
# Unicode-tag fix used `str.isalpha()` / `str.isalnum()` for tag characters, which
# does not cover Unicode combining marks (category Mn/Mc/Me) -- an NFD-decomposed
# tag such as `ta\u0301g` (`t`, `a`, COMBINING ACUTE ACCENT U+0301, `g` -- the
# canonical decomposition of `tag` with an acute on the `a`) stopped the opener
# scan at the combining mark, so the opener was misdetected as absent and the entire
# dollar-quoted body was scanned as ordinary top-level SQL, manufacturing a FALSE
# binding. This section proves the attack, proves the fix (continuation-only,
# never an initial character), and locks the byte-exact decomposed/precomposed
# closer distinction and every pre-existing shape as regressions.
#
# Every combining mark and precomposed letter below is written as an explicit
# `\u....` escape, never as a raw character: a raw combining mark renders on top
# of its base letter, which would make the decomposed (`ta\u0301g`) and
# precomposed (`t\u00e1g`) tags these tests deliberately contrast visually
# indistinguishable in the source.

def test_cte_decomposed_combining_mark_tag_is_matched_and_hides_fake_with():
    # The exact reproducing probe: a NFD-decomposed tag `ta\u0301g` (`t`, `a`,
    # COMBINING ACUTE ACCENT U+0301, `g`) must now be recognised as a valid
    # opener, so the whole dollar-quoted region is skipped atomically and the
    # deceptive real-looking `WITH bil_x AS (` inside it is never collected.
    sql = "SELECT $ta\u0301g$ WITH bil_x AS (SELECT 1) $ta\u0301g$"
    out = _collect_cte_names(sql)
    assert "bil_x" not in out, out
    assert out == frozenset(), out


def test_cte_unclosed_decomposed_combining_mark_tag_fails_closed():
    # Fail-closed: the decomposed-tag opener is recognised, but no matching
    # closing delimiter ever appears before the text ends. Must consume the
    # rest of the text and collect nothing, never fall back to scanning the
    # deceptive `WITH fake AS (` as ordinary SQL.
    sql = "SELECT $ta\u0301g$ WITH fake AS (SELECT 1)"
    assert _collect_cte_names(sql) == frozenset()


def test_cte_decomposed_opener_not_closed_by_precomposed_lookalike():
    # Decomposed and precomposed forms are NOT interchangeable closers, even
    # though they are canonically equivalent and render identically: the
    # decomposed `$ta\u0301g$` opener is not byte-identical to its precomposed
    # `$t\u00e1g$` counterpart (single U+00E1 LATIN SMALL LETTER A WITH ACUTE),
    # and `_skip_dollar_quoted_string` matches the closer byte-exactly with no
    # normalisation. So the deceptive `WITH fake AS (` between them stays hidden
    # inside the still-unclosed region (fails closed, same as any other
    # unterminated dollar-quoted string).
    sql = "SELECT $ta\u0301g$ WITH fake AS ( $t\u00e1g$ AS decoy"
    assert _collect_cte_names(sql) == frozenset()


def test_cte_positional_parameter_still_not_misread_after_combining_mark_fix():
    # Regression: `$1` must still never be treated as an opener now that tag
    # continuation also accepts combining marks -- a digit can never start a
    # tag under any of the old ASCII, Unicode, or combining-mark rules. Reuses
    # the existing shape: a real CTE binding plus `$1` usages.
    sql = "WITH a AS (SELECT $1 AS x) SELECT * FROM a WHERE x = $1"
    assert _collect_cte_names(sql) == frozenset({"a"})


def test_cte_ascii_and_precomposed_tags_still_work_after_combining_mark_fix():
    # Regression: the pre-existing ASCII-tagged and precomposed-non-ASCII-
    # tagged shapes must still behave identically after adding combining-mark
    # continuation support.
    sql_ascii = "SELECT $tag$WITH fake AS ($tag$ AS decoy"
    assert _collect_cte_names(sql_ascii) == frozenset()
    sql_precomposed = "SELECT $t\u00e1g$WITH fake AS ($t\u00e1g$ AS decoy"
    assert _collect_cte_names(sql_precomposed) == frozenset()


# --- GATE2-R1-D6-HIGHBIT-DOLLAR-TAG-LEXER-2026-10-05 ----------------------
#
# The prior "COMBINING-OPENER-REGRESSION" section's fix used
# `str.isalpha()` / `str.isalnum()` plus a Unicode category (`Mn`/`Mc`/`Me`)
# approximation for dollar-quote tag characters. That approximation
# diverged from PostgreSQL's actual byte lexer (`src/backend/parser/scan.l`,
# classes `dolq_start [A-Za-z\200-\377_]` / `dolq_cont [A-Za-z\200-\377_0-9]`)
# in the UNSAFE direction: because every well-formed non-ASCII UTF-8
# codepoint has a high-bit leading byte, scan.l's `dolq_start` accepts ANY
# non-ASCII codepoint as a tag START -- a bare combining mark, an emoji, and
# a C1 control character all validly start a tag. `str.isalpha()` is false
# for all three, so the prior code misdetected the opener as absent and let
# the dollar-quoted body leak into the ordinary top-level scan, manufacturing
# a false CTE binding. The test immediately below this header previously
# locked that false binding in as if it were the intended, correct result
# ("cannot start a tag") -- it is replaced here with the corrected,
# fail-closed assertion.
#
# Every non-ASCII character below is written as an explicit `\u....` /
# `\U........` escape, never as a raw character, for the same reason given
# at the top of the previous section: a raw combining mark or control
# character would not render distinguishably (or at all) in source.


def test_cte_bare_combining_mark_does_start_a_tag_and_hides_fake_with():
    # U+0301 COMBINING ACUTE ACCENT encodes in UTF-8 as the two bytes
    # `CC 81` -- a high-bit leading byte, so scan.l's `dolq_start
    # [A-Za-z\200-\377_]` accepts it as a valid tag START, not merely a
    # continuation. The opener is therefore correctly recognised here, the
    # whole dollar-quoted region is skipped atomically, and the deceptive
    # `WITH bil_x AS (` inside it is never collected. The old assertion
    # (`frozenset({"fake"})`/`bil_x` collected) was wrong: it rewarded a
    # misdetected-absent opener rather than a correctly-recognised one.
    # ACTUAL OBSERVED BEHAVIOUR (executed, not assumed): empty frozenset.
    sql = "SELECT $\u0301tag$ WITH bil_x AS (SELECT 1) $\u0301tag$"
    out = _collect_cte_names(sql)
    assert "bil_x" not in out, out
    assert out == frozenset(), out


def test_cte_highbit_opener_variants_vs_ascii_control_boundary():
    # Positive: an emoji (U+1F600, UTF-8 leading byte 0xF0) and a C1 control
    # character (U+0085, UTF-8 `C2 85`, leading byte 0xC2) are both
    # non-ASCII codepoints with a high-bit leading byte, so both are valid
    # `dolq_start` tag openers under scan.l -- both dollar-quoted regions
    # must be fully skipped, hiding the deceptive `WITH bil_x AS (` inside
    # each.
    sql_emoji = "SELECT $\U0001F600tag$ WITH bil_x AS (SELECT 1) $\U0001F600tag$"
    out_emoji = _collect_cte_names(sql_emoji)
    assert "bil_x" not in out_emoji, out_emoji
    assert out_emoji == frozenset(), out_emoji

    sql_c1 = "SELECT $\u0085tag$ WITH bil_x AS (SELECT 1) $\u0085tag$"
    out_c1 = _collect_cte_names(sql_c1)
    assert "bil_x" not in out_c1, out_c1
    assert out_c1 == frozenset(), out_c1

    # Boundary (other direction): U+0001 is an ASCII control character --
    # byte 0x01, which is NOT in `dolq_start [A-Za-z\200-\377_]` (it is
    # below 0x80 and outside `[A-Za-z_]`). So here the `$` is correctly left
    # as an ordinary character, no dollar-quote region is recognised at
    # all, and the text is scanned as ordinary top-level SQL -- which does
    # contain a real `WITH bil_x AS (SELECT 1)` clause, so `bil_x` is
    # correctly collected as a genuine binding. This assertion is what
    # proves the new predicate is faithful to scan.l's specific byte
    # classes rather than merely "accepts anything non-alphanumeric".
    sql_ascii_ctrl = "SELECT $\u0001tag$ WITH bil_x AS (SELECT 1) $\u0001tag$"
    out_ascii_ctrl = _collect_cte_names(sql_ascii_ctrl)
    assert out_ascii_ctrl == frozenset({"bil_x"}), out_ascii_ctrl


# --- GATE2-R1-D6-ONE-PASS-CTE-SCOPES-2026-10-05 ---------------------------------
#
# `_cte_scopes` is the pure, UNWIRED, one-pass statement-scope helper named by
# `GATE2-R1-D6-CTE-STATEMENT-SCOPE-LEAD-QUALIFICATION-2026-10-05.md` section
# 2(b)(1) as the smallest next legal subgoal after the named `veyro-lead`
# BLOCKED the two-function `_split_sql_statements` + reused-`_collect_cte_names`
# design. These tests call it directly, matching the house style the
# `_collect_cte_names` pure-function tests above already use, rather than
# driving it through `_scan_sql_text`/`run_module_deps_gate` -- `_cte_scopes`
# has no caller in the live scanning path.

try:
    from validate_architecture_gates import _cte_scopes
except ImportError:
    pass


def test_cte_scopes_same_statement_binding_is_visible_to_its_own_statement():
    # Same-statement binding: a single statement with no cut at all is one
    # scope, and its own CTE name is bound for it.
    sql = "WITH a AS (SELECT 1) SELECT * FROM a"
    assert _cte_scopes(sql) == [(sql, frozenset({"a"}))]


def test_cte_scopes_cross_statement_binding_does_not_leak():
    # Cross-statement non-leak: a CTE bound in the first statement must not
    # be visible to a second, later statement that merely shares its name.
    sql = "WITH a AS (SELECT 1) SELECT * FROM a; SELECT * FROM a"
    scopes = _cte_scopes(sql)
    assert len(scopes) == 2, scopes
    assert scopes[0] == ("WITH a AS (SELECT 1) SELECT * FROM a", frozenset({"a"}))
    assert scopes[1] == (" SELECT * FROM a", frozenset())


def test_cte_scopes_chained_ctes_and_nested_parens_in_the_body():
    # CTE body / nested parentheses: a binding list with two bindings, the
    # second referencing the first, and a body containing its own nested
    # subquery parens -- the whole binding list must be consumed atomically
    # without the nested parens corrupting the outer depth counter or
    # producing a premature cut.
    sql = ("WITH a AS (SELECT * FROM (SELECT 1) sub), "
           "b AS (SELECT * FROM a) SELECT * FROM b")
    assert _cte_scopes(sql) == [(sql, frozenset({"a", "b"}))]


def test_cte_scopes_semicolon_inside_single_quoted_literal_declines_only_its_own_statement():
    # Semicolon inside a quoted region: the real cut is the `;` AFTER the
    # literal closes, not the one hidden inside it. The first segment's
    # sliced text still contains the hidden `;`, so its binding (there is
    # none here, but the predicate still applies) is declined; the second,
    # real statement's own binding is unaffected -- the decline is
    # statement-local, not global.
    sql = "SELECT * FROM t WHERE x = 'a;b'; WITH c AS (SELECT 1) SELECT * FROM c"
    scopes = _cte_scopes(sql)
    assert len(scopes) == 2, scopes
    assert ";" in scopes[0][0]
    assert scopes[0][1] == frozenset()
    assert scopes[1][1] == frozenset({"c"})
    assert scopes[0][0] != sql and scopes[1][0] != sql


def test_cte_scopes_semicolon_inside_line_comment_declines_the_binding():
    # Semicolon inside a `--` line comment hides a real binding's own
    # statement from being trusted -- the binding is declined even though
    # the comment's `;` was never a candidate cut.
    sql = "-- cleanup; later\nWITH scratch AS (SELECT 1) SELECT * FROM scratch;\n"
    scopes = _cte_scopes(sql)
    assert scopes[0][1] == frozenset(), scopes
    assert ";" in scopes[0][0]

    # Control: the identical text with the semicolon removed from the
    # comment must bind cleanly -- proving the decline above is caused by
    # the hidden semicolon and not by something incidental.
    sql_control = "-- cleanup later\nWITH scratch AS (SELECT 1) SELECT * FROM scratch;\n"
    scopes_control = _cte_scopes(sql_control)
    assert scopes_control[0][1] == frozenset({"scratch"}), scopes_control
    assert ";" not in scopes_control[0][0]


def test_cte_scopes_semicolon_inside_dollar_quoted_body_is_not_a_statement_cut():
    # Semicolon inside a dollar-quoted body (e.g. a plpgsql function body):
    # the `;` inside `$$ ... $$` must not be treated as a statement cut,
    # but its presence still declines that one statement's own bindings --
    # only the real `;` after the body closes is a cut.
    sql = ("CREATE FUNCTION f() RETURNS void AS $$ BEGIN PERFORM 1; END $$ "
           "LANGUAGE plpgsql; SELECT * FROM bil_x")
    scopes = _cte_scopes(sql)
    assert len(scopes) == 2, scopes
    assert "CREATE FUNCTION" in scopes[0][0]
    assert scopes[0][1] == frozenset()
    assert "bil_x" in scopes[1][0]
    assert scopes[1][1] == frozenset()

    # Tagged dollar-quote variant behaves identically.
    sql_tagged = ("CREATE FUNCTION f() RETURNS void AS $tag$ BEGIN PERFORM 1; END $tag$ "
                  "LANGUAGE plpgsql; SELECT * FROM bil_x")
    scopes_tagged = _cte_scopes(sql_tagged)
    assert len(scopes_tagged) == 2, scopes_tagged
    assert scopes_tagged[0][1] == frozenset()
    assert scopes_tagged[1][1] == frozenset()


def test_cte_scopes_unterminated_single_quoted_literal_declines_whole_text():
    sql = "SELECT * FROM t WHERE x = 'unterminated"
    assert _cte_scopes(sql) == [(sql, frozenset())]


def test_cte_scopes_unterminated_block_comment_declines_whole_text():
    sql = "SELECT 1; /* unterminated"
    assert _cte_scopes(sql) == [(sql, frozenset())]


def test_cte_scopes_unterminated_dollar_quoted_string_declines_whole_text():
    sql = "SELECT 1; WITH a AS (SELECT 1) SELECT $$ unterminated"
    assert _cte_scopes(sql) == [(sql, frozenset())]


def test_cte_scopes_unterminated_double_quoted_identifier_declines_whole_text():
    sql = 'SELECT 1; WITH a AS (SELECT 1) SELECT * FROM "unterminated'
    assert _cte_scopes(sql) == [(sql, frozenset())]


def test_cte_scopes_with_jump_asymmetry_unconfirmed_binding_still_tracks_depth_correctly():
    # WITH-jump asymmetry: a column-name-list CTE head (`cte(a, b) AS (`) is
    # a shape `_parse_one_cte_binding` deliberately does not confirm (see
    # its own docstring), so the `WITH` -> `_parse_cte_binding_list` jump
    # does NOT advance the cursor here -- the binding list is left for the
    # ordinary character-by-character dispatch to walk instead. This proves
    # the single dispatch tracks depth-0 `;` cuts correctly regardless of
    # whether the jump fires: there is only one cursor, so the cut logic and
    # the WITH-recognition logic can never disagree about where they are.
    sql = "WITH cte(a,b) AS (SELECT 1); SELECT * FROM cte"
    scopes = _cte_scopes(sql)
    assert len(scopes) == 2, scopes
    assert scopes[0] == ("WITH cte(a,b) AS (SELECT 1)", frozenset())
    assert scopes[1] == (" SELECT * FROM cte", frozenset())


def test_cte_scopes_with_jump_confirmed_binding_resumes_depth_tracking_after_the_jump():
    # The jump-confirmed counterpart to the test above: once
    # `_parse_cte_binding_list` DOES confirm a binding and jumps the cursor
    # past its whole body, the very next real top-level `;` is still found
    # correctly -- the jump does not desynchronise the depth-0 cut logic
    # that resumes immediately after it.
    sql = "WITH a AS (SELECT 1); SELECT * FROM a"
    scopes = _cte_scopes(sql)
    assert len(scopes) == 2, scopes
    assert scopes[0] == ("WITH a AS (SELECT 1)", frozenset({"a"}))
    assert scopes[1] == (" SELECT * FROM a", frozenset())


def test_cte_scopes_empty_text_is_one_empty_scope():
    assert _cte_scopes("") == [("", frozenset())]


def test_cte_scopes_is_pure_and_does_not_mutate_or_depend_on_call_order():
    sql = "WITH a AS (SELECT 1) SELECT * FROM a; SELECT * FROM a"
    first = _cte_scopes(sql)
    second = _cte_scopes(sql)
    assert first == second
    assert sql == "WITH a AS (SELECT 1) SELECT * FROM a; SELECT * FROM a"


def test_cte_scopes_with_recursive_binding_fails_closed_in_both_scopes():
    # T1, third input (`GATE2-R1-D6-CTE-STATEMENT-SCOPE-DECISION-2026-10-05.md`
    # section 6): `RECURSIVE` must fail closed rather than bind -- both the
    # statement that declares the recursive CTE and the later statement that
    # merely shares its name get an empty binding set. T1a/T1b (the two
    # non-`RECURSIVE` T1 inputs) already exist above under other names; this
    # is the absent third input, the I-1 lock's `RECURSIVE` case.
    sql = "WITH RECURSIVE r AS (SELECT 1) SELECT * FROM r; SELECT * FROM r"
    scopes = _cte_scopes(sql)
    assert len(scopes) == 2, scopes
    assert scopes[0][1] == frozenset(), scopes
    assert scopes[1][1] == frozenset(), scopes


try:
    from validate_architecture_gates import _extract_table_identifiers
except ImportError:
    pass

from collections import Counter


def test_cte_scopes_extraction_equivalence_and_unlexable_decline():
    # T8 (decision section 6): the I-5 extraction-equivalence and
    # unlexable-decline lock. For each of the T1/T5/T7 inputs plus an
    # unterminated literal and a backslash-escape shape, the multiset of
    # table identifiers extracted segment-by-segment must equal the
    # multiset extracted from the whole text in one pass -- segmenting
    # must never gain or lose an identifier, only regroup which scope it
    # belongs to.
    t1_inputs = [
        ("WITH bil_scratch AS (SELECT 1) SELECT * FROM bil_scratch;"
        " SELECT * FROM bil_scratch"),
        ("WITH a AS (SELECT 1), b AS (SELECT * FROM a) SELECT * FROM b;"
        " SELECT * FROM a"),
        "WITH RECURSIVE r AS (SELECT 1) SELECT * FROM r; SELECT * FROM r",
    ]
    t5_input = "SELECT * FROM t WHERE x = 'a;b'; WITH c AS (SELECT 1) SELECT * FROM c"
    t7_inputs = [
        ("CREATE FUNCTION f() RETURNS void AS $$ BEGIN PERFORM 1;"
        " END $$ LANGUAGE plpgsql; SELECT * FROM bil_x"),
        ("CREATE FUNCTION f() RETURNS void AS $tag$ BEGIN PERFORM 1;"
        " END $tag$ LANGUAGE plpgsql; SELECT * FROM bil_x"),
    ]
    unterminated = "SELECT * FROM t WHERE x = 'unterminated"
    backslash_escape = "SELECT 'a\\'; WITH fake AS (SELECT 1) SELECT * FROM bil_t'"

    for sql in [*t1_inputs, t5_input, *t7_inputs, unterminated, backslash_escape]:
        scopes = _cte_scopes(sql)
        segment_counter = Counter()
        for seg, _names in scopes:
            segment_counter.update(_extract_table_identifiers(seg))
        whole_text_counter = Counter(_extract_table_identifiers(sql))
        assert segment_counter == whole_text_counter, sql

    # Unlexable decline, part 1: the unterminated literal yields exactly one
    # scope with an empty binding set.
    unterminated_scopes = _cte_scopes(unterminated)
    assert len(unterminated_scopes) == 1, unterminated_scopes
    assert unterminated_scopes[0][1] == frozenset(), unterminated_scopes

    # Unlexable decline, part 2: the adversarial over-skip shape -- a
    # backslash-escaped quote under `standard_conforming_strings` -- must
    # not produce a `fake` binding in any scope, demonstrating I-1 does not
    # depend on the lexer's skip decisions being right.
    backslash_scopes = _cte_scopes(backslash_escape)
    for _seg, names in backslash_scopes:
        assert "fake" not in names, backslash_scopes


def test_cte_scopes_segment_bindings_are_a_subset_of_whole_text_bindings():
    # T9 (`GATE2-R1-D6-CTE-STATEMENT-SCOPE-CORRECTION-2026-10-05.md`
    # section 5): the I-2a / Lemma L lock, and "the single most important
    # test added by this correction." For every input in the corpus and
    # every (segment, N(s)) pair `_cte_scopes` returns, N(s) must be a
    # subset of the whole-text binding set `_collect_cte_names` returns --
    # segmenting a statement list into scopes must never bind a name the
    # unsegmented whole-text walk would not also bind.
    #
    # Corpus: every input already named in section 6's T1/T5/T7/T8 (shared
    # with `test_cte_scopes_extraction_equivalence_and_unlexable_decline`
    # above) plus the adversarial seeds recorded in correction section 3.1.
    # Section 3.1 states "8 seeded adversarial inputs" but its prose
    # enumerates only seven distinct shapes, one of which (backslash-before-
    # quote) is the same shape as T8's `backslash_escape` input above and so
    # is not duplicated here. Of the remaining six, five are reconstructed
    # below directly from section 3.1's own descriptions and example text.
    # The sixth ("a false-cut shape whose tail re-lexes standalone") is now
    # covered by `false_cut_tail` below -- a NEWLY CONSTRUCTED REPLACEMENT
    # seed authored 2026-10-05 against the current one-pass `_cte_scopes`.
    # It is NOT the lost historical eighth seed: that seed remains
    # unreconstructable (the prototype that ran it was deleted, its exact
    # seed strings are not in the repository, and it was run against the
    # subsequently-BLOCKED two-function `_split_sql_statements` design, not
    # against `_cte_scopes`). No result from this forward corpus --
    # `false_cut_tail` included -- may be cited as evidence for section
    # 3.1's historical "8 seeds / 0 falsifications" claim. See
    # knowledge/03-Modules/MOD-001/evidence/implementation/
    # GATE2-R1-D6-T9-SEED-RECONCILIATION-2026-10-05.md, sections 2 and 5.
    t1_inputs = [
        ("WITH bil_scratch AS (SELECT 1) SELECT * FROM bil_scratch;"
        " SELECT * FROM bil_scratch"),
        ("WITH a AS (SELECT 1), b AS (SELECT * FROM a) SELECT * FROM b;"
        " SELECT * FROM a"),
        "WITH RECURSIVE r AS (SELECT 1) SELECT * FROM r; SELECT * FROM r",
    ]
    t5_input = "SELECT * FROM t WHERE x = 'a;b'; WITH c AS (SELECT 1) SELECT * FROM c"
    t7_inputs = [
        ("CREATE FUNCTION f() RETURNS void AS $$ BEGIN PERFORM 1;"
        " END $$ LANGUAGE plpgsql; SELECT * FROM bil_x"),
        ("CREATE FUNCTION f() RETURNS void AS $tag$ BEGIN PERFORM 1;"
        " END $tag$ LANGUAGE plpgsql; SELECT * FROM bil_x"),
    ]
    t8_extra = [
        "SELECT * FROM t WHERE x = 'unterminated",
        "SELECT 'a\\'; WITH fake AS (SELECT 1) SELECT * FROM bil_t'",
    ]
    # Correction section 3.1's adversarial seeds (backslash-before-quote
    # omitted as a duplicate of `t8_extra[1]` above; the "false-cut" shape
    # is covered by the newly constructed `false_cut_tail` replacement seed
    # below, not by this list).
    adversarial_seeds = [
        # the doubled-quote form
        "SELECT 'a''; WITH fake AS (SELECT 1) SELECT * FROM bil_t'",
        # an E'...' string
        "SELECT E'a\\'; WITH fake AS (SELECT 1) SELECT * FROM bil_t'",
        # a `;` inside a block comment
        "SELECT 1 /* ; WITH fake AS (SELECT 1) */ SELECT * FROM bil_t",
        # a `;` inside a `$$` body
        "SELECT $$ ; WITH fake AS (SELECT 1) $$ SELECT * FROM bil_t",
        # a `;` inside a `"c;ol"` quoted identifier
        'SELECT "c;ol" FROM t; WITH fake AS (SELECT 1) SELECT * FROM bil_t',
    ]

    # Newly constructed replacement for correction section 3.1's
    # unreconstructable eighth seed ("a false-cut shape whose tail re-lexes
    # standalone"). NOT the historical seed; see
    # GATE2-R1-D6-T9-SEED-RECONCILIATION-2026-10-05.md.
    false_cut_tail = "SELECT 'a ; WITH fake AS (SELECT 1) SELECT * FROM bil_t' FROM t"

    corpus = [
        *t1_inputs,
        t5_input,
        *t7_inputs,
        *t8_extra,
        *adversarial_seeds,
        false_cut_tail,
    ]

    saw_nonempty_segment_binding = False
    saw_whole_text_strictly_larger = False
    for sql in corpus:
        whole_text_names = _collect_cte_names(sql)
        for _seg, names in _cte_scopes(sql):
            assert names <= whole_text_names, (sql, names, whole_text_names)
            if names:
                saw_nonempty_segment_binding = True
            if names < whole_text_names:
                saw_whole_text_strictly_larger = True

    # Non-vacuity control: the subset assertion above must not be trivially
    # true on empty sets alone.
    assert saw_nonempty_segment_binding
    assert saw_whole_text_strictly_larger

    # `false_cut_tail` combined-behaviour assertions (GATE2-R1-D6-T9-SEED-
    # RECONCILIATION-2026-10-05.md section 2/addendum): the hazard-witness
    # assertion below (assert 4 further down) is NOT a regression detector
    # for `_cte_scopes` on its own -- it never calls that helper. These SCOPE
    # assertions are what would fail if a future edit regressed to a
    # false-cutting / re-lexing design, so they are the regression detector
    # and must be kept together as one block.
    false_cut_scopes = _cte_scopes(false_cut_tail)
    assert len(false_cut_scopes) == 1, false_cut_scopes
    assert false_cut_scopes[0][0] == false_cut_tail, false_cut_scopes
    assert false_cut_scopes[0][1] == frozenset(), false_cut_scopes
    assert all("fake" not in names for _seg, names in false_cut_scopes), (
        false_cut_scopes
    )
    assert _collect_cte_names(false_cut_tail) == frozenset(), (
        _collect_cte_names(false_cut_tail)
    )
    assert false_cut_scopes[0][1] <= _collect_cte_names(false_cut_tail), (
        false_cut_scopes,
        _collect_cte_names(false_cut_tail),
    )

    # Hazard witness / non-vacuity-and-danger proof (NOT the regression
    # detector): this proves the tail is genuinely hazardous when re-lexed
    # standalone, which is what makes `false_cut_tail` a false-cut-tail seed
    # rather than decoration. It does NOT by itself detect a change to
    # `_cte_scopes` (it never calls that helper) -- the combined scope
    # assertions above are the regression detector.
    false_cut_tail_suffix = false_cut_tail.split(";", 1)[1]
    assert _collect_cte_names(false_cut_tail_suffix) == frozenset({"fake"}), (
        _collect_cte_names(false_cut_tail_suffix)
    )


# --- GATE2-R1-D6-U1-LEXICAL-UNDER-SKIP-TESTS-2026-10-05 -------------------------
#
# Closes U1 from `GATE2-R1-D6-D3D9-PREWIRE-LEAD-JUDGMENT-2026-10-05.md` section
# 2.4/4(1): still-unwired regression tests against the one-pass `_cte_scopes`
# (not `_collect_cte_names` -- that is a different function, and coverage of a
# nearby shape there does not discharge this obligation for `_cte_scopes`) for
# five named dialect under-skip classes the lead's packet left unverified:
# nested PostgreSQL block comments, tagged dollar-quoting with an inner
# mismatched tag, `E'...'` backslash-escaped apostrophes, `U&` unicode-escape
# forms (both the `U&'...'` literal and the `U&"..."` quoted-identifier
# shape), and a doubled quote inside a double-quoted identifier (distinct from
# the already-covered doubled quote inside a single-quoted literal).
#
# Every input below uses `bil_invoices` as the probe identifier -- the exact
# masking name demonstrated by
# `GATE2-R1-D6-U2-PRECEDENCE-INSPECTION-2026-10-05.md` (importer `membership`,
# `billing` owning `bil_`) -- inside the inert region under test, plus a
# genuine depth-0 `real_cte` binding OUTSIDE that region in the same text, so
# no assertion here could pass vacuously by `_cte_scopes` simply returning no
# bindings anywhere. Per class, the acceptance criterion is a disjunction:
# `_cte_scopes` must either (a) consume the inert region atomically (never
# inspecting its content for a `WITH` at all) or (b) decline fail-closed (no
# binding / an empty binding set for the affected scope) -- and, unconditional
# on which branch applies, it must NEVER emit a binding sourced from inside
# the region. Each test asserts the unconditional never-emit property
# directly (searching every scope's binding set, not just one), and also
# pins the exact scope list `_cte_scopes` actually returns -- matching this
# file's existing house style for the `_cte_scopes` block above -- as a
# concrete record of which branch of the disjunction was actually observed
# for this input, without treating that observation as proof for every input.

def test_cte_scopes_nested_block_comment_never_emits_bil_invoices_binding():
    # U1 class 1: PostgreSQL block comments nest (`_skip_block_comment`'s own
    # docstring, citing the live PostgreSQL lexical-structure documentation),
    # so `/* outer /* nested */ ... */` is ONE comment, not two separately
    # -closed ones. A non-nesting skipper would close at the FIRST `*/` --
    # right after `nested ` -- exposing `WITH bil_invoices AS ( SELECT 1 )`
    # as ordinary top-level SQL and falsely binding `bil_invoices`.
    # `_cte_scopes` must never do that. There is no depth-0 `;` anywhere in
    # this text, so the whole thing is one scope.
    sql = ("/* outer /* nested */ WITH bil_invoices AS ( SELECT 1 ) */ "
           "WITH real_cte AS (SELECT 1) SELECT * FROM real_cte")
    scopes = _cte_scopes(sql)
    assert scopes == [(sql, frozenset({"real_cte"}))], scopes
    all_names = {name for _seg, names in scopes for name in names}
    assert "bil_invoices" not in all_names, scopes
    # Positive control: proves the assertion above is not vacuous.
    assert "real_cte" in all_names, scopes


def test_cte_scopes_tagged_dollar_quote_inner_mismatched_tag_never_emits_bil_invoices_binding():
    # U1 class 2: a tagged dollar-quoted string (`$fn$ ... $fn$`) whose body
    # contains an inner, DIFFERENTLY-tagged dollar-quote delimiter (`$$`).
    # `_skip_dollar_quoted_string` closes only on a literal, byte-exact match
    # of the SAME opening delimiter text (`str.find(delim, opener_end)`), so
    # the inner `$$` -- not equal to `$fn$` -- must never be mistaken for the
    # close; the decoy `WITH bil_invoices AS (...)` sitting between the inner
    # `$$` pair must stay hidden inside the outer `$fn$...$fn$` region for
    # its entire length. The real depth-0 `;` after the region closes is the
    # only cut, so this is two scopes.
    sql = ("SELECT $fn$ decoy $$ WITH bil_invoices AS ( SELECT 1 ) $$ still inside $fn$ AS x; "
           "WITH real_cte AS (SELECT 1) SELECT * FROM real_cte")
    scopes = _cte_scopes(sql)
    assert len(scopes) == 2, scopes
    assert scopes[0] == (
        "SELECT $fn$ decoy $$ WITH bil_invoices AS ( SELECT 1 ) $$ still inside $fn$ AS x",
        frozenset(),
    ), scopes
    assert scopes[1] == (
        " WITH real_cte AS (SELECT 1) SELECT * FROM real_cte",
        frozenset({"real_cte"}),
    ), scopes
    all_names = {name for _seg, names in scopes for name in names}
    assert "bil_invoices" not in all_names, scopes
    # Positive control: proves the assertion above is not vacuous.
    assert "real_cte" in all_names, scopes


def test_cte_scopes_e_string_escaped_apostrophe_never_emits_bil_invoices_binding():
    # U1 class 3: PostgreSQL `E'...'`-style backslash-escaped apostrophe
    # (`\'`) inside a decoy literal. `_skip_single_quoted_literal` treats a
    # backslash as escaping the next character for every single-quoted
    # literal (see its own docstring), so the escaped `\'` after `foo` must
    # not be read as the literal's real close -- if it were, the remaining
    # ` WITH bil_invoices AS ('` text would leak out as ordinary SQL one
    # token later and falsely bind `bil_invoices`.
    sql = ("SELECT E'foo\\' WITH bil_invoices AS (' AS decoy; "
           "WITH real_cte AS (SELECT 1) SELECT * FROM real_cte")
    scopes = _cte_scopes(sql)
    assert len(scopes) == 2, scopes
    assert scopes[0] == (
        "SELECT E'foo\\' WITH bil_invoices AS (' AS decoy",
        frozenset(),
    ), scopes
    assert scopes[1] == (
        " WITH real_cte AS (SELECT 1) SELECT * FROM real_cte",
        frozenset({"real_cte"}),
    ), scopes
    all_names = {name for _seg, names in scopes for name in names}
    assert "bil_invoices" not in all_names, scopes
    # Positive control: proves the assertion above is not vacuous.
    assert "real_cte" in all_names, scopes


def test_cte_scopes_u_ampersand_literal_never_emits_bil_invoices_binding():
    # U1 class 4a: a `U&'...'` Unicode-escape string literal. This module's
    # docstring for `_collect_cte_names` discloses that the `U&` prefix is
    # not recognised as a distinct shape -- the body is lexed as an ordinary
    # single-quoted literal by `_skip_single_quoted_literal`, which closes
    # correctly at the real terminating `'` in this (non-`UESCAPE`) common
    # case. The decoy `WITH bil_invoices AS (...)` inside the literal body
    # must stay hidden for the literal's entire length regardless of the
    # `U&` prefix.
    sql = ("SELECT U&'foo WITH bil_invoices AS (' AS decoy; "
           "WITH real_cte AS (SELECT 1) SELECT * FROM real_cte")
    scopes = _cte_scopes(sql)
    assert len(scopes) == 2, scopes
    assert scopes[0] == (
        "SELECT U&'foo WITH bil_invoices AS (' AS decoy",
        frozenset(),
    ), scopes
    assert scopes[1] == (
        " WITH real_cte AS (SELECT 1) SELECT * FROM real_cte",
        frozenset({"real_cte"}),
    ), scopes
    all_names = {name for _seg, names in scopes for name in names}
    assert "bil_invoices" not in all_names, scopes
    # Positive control: proves the assertion above is not vacuous.
    assert "real_cte" in all_names, scopes


def test_cte_scopes_u_ampersand_quoted_identifier_never_emits_bil_invoices_binding():
    # U1 class 4b: the `U&"..."` Unicode-escape quoted-identifier
    # counterpart to the literal form above. Per the same disclosed
    # limitation, the `U&` prefix is not recognised as a distinct shape --
    # the body is lexed as an ordinary double-quoted segment by the
    # pre-existing `_lex_quoted_segment` (its content, not its `U&` prefix,
    # is what `_cte_scopes` sees), which closes correctly at the real
    # terminating `"` in this common case. The decoy `WITH bil_invoices AS
    # (...)` inside the quoted-identifier body must stay hidden for its
    # entire length regardless of the `U&` prefix.
    sql = ('SELECT U&"foo WITH bil_invoices AS (" AS decoy; '
           'WITH real_cte AS (SELECT 1) SELECT * FROM real_cte')
    scopes = _cte_scopes(sql)
    assert len(scopes) == 2, scopes
    assert scopes[0] == (
        'SELECT U&"foo WITH bil_invoices AS (" AS decoy',
        frozenset(),
    ), scopes
    assert scopes[1] == (
        " WITH real_cte AS (SELECT 1) SELECT * FROM real_cte",
        frozenset({"real_cte"}),
    ), scopes
    all_names = {name for _seg, names in scopes for name in names}
    assert "bil_invoices" not in all_names, scopes
    # Positive control: proves the assertion above is not vacuous.
    assert "real_cte" in all_names, scopes


def test_cte_scopes_doubled_quote_inside_double_quoted_identifier_never_emits_bil_invoices_binding():
    # U1 class 5: a doubled quote (`""`, SQL's escaped-embedded-`"` rule)
    # inside a double-quoted IDENTIFIER -- distinct from the already-covered
    # doubled-quote escape inside a single-quoted LITERAL
    # (`test_cte_doubled_quote_escape_inside_literal_does_not_close_early`
    # above, which exercises `_skip_single_quoted_literal`, not
    # `_lex_quoted_segment`). `_cte_scopes` dispatches to
    # `_lex_quoted_segment` itself (not via `_skip_quote_or_comment`)
    # whenever it sees a bare `"`, so this confirms that same escape-aware
    # behaviour holds on `_cte_scopes`'s own direct call path: the `""`
    # after `a` must not be read as the identifier's real close, or the
    # remaining `b WITH bil_invoices AS ( SELECT 1 )" AS decoy` text would
    # leak out and falsely bind `bil_invoices`.
    sql = ('SELECT "a""b WITH bil_invoices AS ( SELECT 1 )" AS decoy; '
           'WITH real_cte AS (SELECT 1) SELECT * FROM real_cte')
    scopes = _cte_scopes(sql)
    assert len(scopes) == 2, scopes
    assert scopes[0] == (
        'SELECT "a""b WITH bil_invoices AS ( SELECT 1 )" AS decoy',
        frozenset(),
    ), scopes
    assert scopes[1] == (
        " WITH real_cte AS (SELECT 1) SELECT * FROM real_cte",
        frozenset({"real_cte"}),
    ), scopes
    all_names = {name for _seg, names in scopes for name in names}
    assert "bil_invoices" not in all_names, scopes
    # Positive control: proves the assertion above is not vacuous.
    assert "real_cte" in all_names, scopes


# --- GATE2-R1-D6-SEEDED-PROPERTY-CORPUS-2026-10-05 ------------------------------
#
# `GATE2-R1-D6-PREWIRE-TEST-SEQUENCING-LEAD-DECISION-2026-10-05.md` (d), step
# 2: "Seeded property/fuzz corpus increment. Correction §6.1's 'honest next
# step,' landed in-repository with its seed and token alphabet recorded, so
# the 300k claim stops being a deleted-prototype assertion." The historical
# "300k+8 fuzz result" (correction §3.1) is NOT reproduced here and is not
# cited as evidence by this corpus -- that prototype is deleted, its seeds
# are not in the repository, and it ran against the since-BLOCKED two-
# function `_split_sql_statements` design, not against `_cte_scopes` (see
# GATE2-R1-D6-T9-SEED-RECONCILIATION-2026-10-05.md). This is a forward,
# reproducible, in-repository corpus against the CURRENT one-pass
# `_cte_scopes`, nothing more.
#
# Stdlib `random` only, per the lead decision: "adopting `hypothesis` would
# be a `CAPABILITY_POLICY.md` lifecycle item by the same reasoning ADR-011
# D9 applies to third-party SQL parsers, with BUG-038 as the project's own
# precedent for skipping it." `random.Random` is instantiated locally below
# with a literal seed -- never the global `random` module -- so this corpus
# cannot be perturbed by test collection order or by another test's calls
# into the `random` module, and is byte-for-byte replayable from this
# function's own text with no external seed file.
import random

# Literal, replayable seed -- a future reader reconstructs the exact 512-case
# corpus from this seed plus the alphabet/assembly code below, with no other
# input.
_PROPERTY_CORPUS_SEED = 20261005
# ~512 generated cases, per the lead decision's "Target roughly 512 generated
# cases."
_PROPERTY_CORPUS_CASE_COUNT = 512

# Token alphabet, enumerated (26 chunk generators). Each one, given the local
# `random.Random` instance, returns one literal text fragment. Every shape
# the lead decision names is present:
#   - a plain non-`WITH` statement                      (plain_statement)
#   - single-quoted literals: plain, and with a hidden `;`
#   - `--` line comments: plain, and with a hidden `;`
#   - `/* */` block comments: plain, and with a hidden `;`
#   - `$$...$$` dollar-quoted bodies: plain, and with a hidden `;`
#   - `$tag$...$tag$` dollar-quoted bodies: plain, and with a hidden `;`
#   - nested-paren depth shapes (depth 1-4)
#   - a bare `;` statement cut
#   - `WITH <name> AS (...)` binding heads: a standalone head, a head whose
#     own statement also references the bound name (the positive shape --
#     "a real binding should be visible to its own statement"), a
#     `WITH RECURSIVE` head (I-1: must fail closed), and a column-name-list
#     head (`name(a, b) AS (...)`, deliberately unconfirmed by
#     `_parse_one_cte_binding`)
#   - a plain non-`WITH` statement referencing a `bil_`-prefixed table name
#   - four adversarial "`WITH fake AS (...)` sequestered inside a
#     literal/comment/dollar-quote" shapes
#   - four "unterminated region" shapes (single-quote, block comment,
#     dollar-quote, double-quoted identifier) -- each declines the WHOLE
#     text per `_cte_scopes`' own whole-text-decline rule
_PROPERTY_CORPUS_NAME_POOL = ("a", "b", "c", "bil_scratch", "cte1")


def _fuzz_plain_statement(rng):
    return rng.choice([
        "SELECT 1",
        "SELECT * FROM t",
        "SELECT * FROM bil_scratch",
        "UPDATE t SET x = 1",
        "SELECT * FROM a, b",
    ])


def _fuzz_single_quote_plain(rng):
    return "'plain literal text'"


def _fuzz_single_quote_hidden_semi(rng):
    return "'a;b'"


def _fuzz_line_comment_plain(rng):
    return "-- plain comment\n"


def _fuzz_line_comment_hidden_semi(rng):
    return "-- hidden ; comment\n"


def _fuzz_block_comment_plain(rng):
    return "/* plain comment */"


def _fuzz_block_comment_hidden_semi(rng):
    return "/* hidden ; comment */"


def _fuzz_dollar_quote_plain(rng):
    return "$$ plain body $$"


def _fuzz_dollar_quote_hidden_semi(rng):
    return "$$ hidden ; body $$"


def _fuzz_dollar_quote_tagged_plain(rng):
    tag = rng.choice(("tag", "q1"))
    return f"${tag}$ plain ${tag}$"


def _fuzz_dollar_quote_tagged_hidden_semi(rng):
    tag = rng.choice(("tag", "q1"))
    return f"${tag}$ hidden ; ${tag}$"


def _fuzz_nested_parens(rng):
    depth = rng.randint(1, 4)
    return "(" * depth + "SELECT 1" + ")" * depth


def _fuzz_bare_semicolon(rng):
    return ";"


def _fuzz_with_binding_plain(rng):
    name = rng.choice(_PROPERTY_CORPUS_NAME_POOL)
    return f"WITH {name} AS (SELECT 1)"


def _fuzz_with_binding_own_statement_positive(rng):
    # Positive shape: the bound name is referenced by its OWN statement, the
    # case the lead decision calls out explicitly ("a real binding should be
    # visible to its own statement").
    name = rng.choice(_PROPERTY_CORPUS_NAME_POOL)
    return f"WITH {name} AS (SELECT 1) SELECT * FROM {name}"


def _fuzz_with_binding_recursive(rng):
    # Adversarial/I-1 shape: `RECURSIVE` must fail closed (decision §6 T1,
    # third input; `test_cte_scopes_with_recursive_binding_fails_closed_in_
    # both_scopes` above) -- `name` must NOT end up bound here.
    name = rng.choice(_PROPERTY_CORPUS_NAME_POOL)
    return f"WITH RECURSIVE {name} AS (SELECT 1) SELECT * FROM {name}"


def _fuzz_with_binding_column_list(rng):
    # Adversarial shape: a column-name-list head is deliberately NOT
    # confirmed by `_parse_one_cte_binding` (see its own docstring), so
    # `name` must NOT end up bound here either.
    name = rng.choice(_PROPERTY_CORPUS_NAME_POOL)
    return f"WITH {name}(a, b) AS (SELECT 1) SELECT * FROM {name}"


def _fuzz_non_with_statement(rng):
    table = rng.choice(("t", "bil_scratch", "a", "billing_x"))
    return f"SELECT * FROM {table}"


def _fuzz_adversarial_with_in_single_quote(rng):
    return "'... WITH fake AS (SELECT 1) ...'"


def _fuzz_adversarial_with_in_line_comment(rng):
    return "-- WITH fake AS (SELECT 1)\n"


def _fuzz_adversarial_with_in_block_comment(rng):
    return "/* WITH fake AS (SELECT 1) */"


def _fuzz_adversarial_with_in_dollar_quote(rng):
    return "$$ WITH fake AS (SELECT 1) $$"


def _fuzz_unterminated_single_quote(rng):
    return "'unterminated"


def _fuzz_unterminated_block_comment(rng):
    return "/* unterminated"


def _fuzz_unterminated_dollar_quote(rng):
    return "$$ unterminated"


def _fuzz_unterminated_double_quote(rng):
    return '"unterminated'


_PROPERTY_CORPUS_ALPHABET = [
    ("plain_statement", _fuzz_plain_statement),
    ("single_quote_plain", _fuzz_single_quote_plain),
    ("single_quote_hidden_semi", _fuzz_single_quote_hidden_semi),
    ("line_comment_plain", _fuzz_line_comment_plain),
    ("line_comment_hidden_semi", _fuzz_line_comment_hidden_semi),
    ("block_comment_plain", _fuzz_block_comment_plain),
    ("block_comment_hidden_semi", _fuzz_block_comment_hidden_semi),
    ("dollar_quote_plain", _fuzz_dollar_quote_plain),
    ("dollar_quote_hidden_semi", _fuzz_dollar_quote_hidden_semi),
    ("dollar_quote_tagged_plain", _fuzz_dollar_quote_tagged_plain),
    ("dollar_quote_tagged_hidden_semi", _fuzz_dollar_quote_tagged_hidden_semi),
    ("nested_parens", _fuzz_nested_parens),
    ("bare_semicolon", _fuzz_bare_semicolon),
    ("with_binding_plain", _fuzz_with_binding_plain),
    ("with_binding_own_statement_positive", _fuzz_with_binding_own_statement_positive),
    ("with_binding_recursive", _fuzz_with_binding_recursive),
    ("with_binding_column_list", _fuzz_with_binding_column_list),
    ("non_with_statement", _fuzz_non_with_statement),
    ("adversarial_with_in_single_quote", _fuzz_adversarial_with_in_single_quote),
    ("adversarial_with_in_line_comment", _fuzz_adversarial_with_in_line_comment),
    ("adversarial_with_in_block_comment", _fuzz_adversarial_with_in_block_comment),
    ("adversarial_with_in_dollar_quote", _fuzz_adversarial_with_in_dollar_quote),
    ("unterminated_single_quote", _fuzz_unterminated_single_quote),
    ("unterminated_block_comment", _fuzz_unterminated_block_comment),
    ("unterminated_dollar_quote", _fuzz_unterminated_dollar_quote),
    ("unterminated_double_quote", _fuzz_unterminated_double_quote),
]

# Inter-chunk separators. Including a literal `;` (bare, and `"; "`) here --
# not only via the dedicated `bare_semicolon` chunk above -- is what makes
# multi-statement (multi-scope) cases common enough for the non-vacuity
# control below to be satisfied by construction, not by luck.
_PROPERTY_CORPUS_SEPARATORS = (" ", "", "; ", ";")


def _generate_property_corpus_case(rng):
    """One generated case: 1-4 chunks drawn uniformly from the alphabet
    above, joined by a randomly chosen separator per gap. Pure given `rng`;
    mutates no shared state other than advancing `rng` itself."""
    chunk_count = rng.randint(1, 4)
    pieces = [rng.choice(_PROPERTY_CORPUS_ALPHABET)[1](rng) for _ in range(chunk_count)]
    text = pieces[0]
    for piece in pieces[1:]:
        text += rng.choice(_PROPERTY_CORPUS_SEPARATORS) + piece
    return text


def test_cte_scopes_seeded_property_corpus_subset_and_extraction_equivalence():
    # Seeded property/fuzz corpus (lead decision (d) step 2): 512 generated
    # cases from a local `random.Random(_PROPERTY_CORPUS_SEED)` instance
    # (never the global `random` module), asserting T9's subset property and
    # I-5's extraction equivalence over EVERY generated case, with
    # replayable failure messages (seed, case index, full input) and
    # non-vacuity controls that an all-empty/degenerate corpus cannot pass.
    rng = random.Random(_PROPERTY_CORPUS_SEED)

    # Non-vacuity counters -- see the asserted lower bounds below.
    nonempty_segment_binding_count = 0
    multi_scope_case_count = 0

    for case_index in range(_PROPERTY_CORPUS_CASE_COUNT):
        sql = _generate_property_corpus_case(rng)
        scopes = _cte_scopes(sql)
        whole_text_names = _collect_cte_names(sql)

        if len(scopes) > 1:
            multi_scope_case_count += 1

        segment_counter = Counter()
        for seg, names in scopes:
            # T9 subset (I-2a / Lemma L lock): every segment's binding set
            # must be a subset of the whole-text binding set.
            assert names <= whole_text_names, (
                f"T9 subset violated -- seed={_PROPERTY_CORPUS_SEED!r} "
                f"case_index={case_index!r} input={sql!r} "
                f"segment_names={names!r} whole_text_names={whole_text_names!r}"
            )
            if names:
                nonempty_segment_binding_count += 1
            segment_counter.update(_extract_table_identifiers(seg))

        # I-5 extraction equivalence: the multiset of table identifiers
        # extracted segment-by-segment must equal the multiset extracted
        # from the whole text in one pass.
        whole_text_counter = Counter(_extract_table_identifiers(sql))
        assert segment_counter == whole_text_counter, (
            f"I-5 extraction equivalence violated -- "
            f"seed={_PROPERTY_CORPUS_SEED!r} case_index={case_index!r} "
            f"input={sql!r} segment_counter={segment_counter!r} "
            f"whole_text_counter={whole_text_counter!r}"
        )

    # Non-vacuity controls: observed against this exact seed/alphabet/count
    # at authoring time, 57 segments had a non-empty binding set
    # binding and 190 cases produced more than one scope. The bounds below
    # are set below those observed values (not merely `> 0`) so an
    # all-empty/degenerate generator regression is still caught, while
    # leaving headroom against alphabet-weighting drift that does not
    # actually break the generator.
    assert nonempty_segment_binding_count >= 30, nonempty_segment_binding_count
    assert multi_scope_case_count >= 100, multi_scope_case_count


def test_module_deps_cli_exit_codes_and_no_skip_flag():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        modules_dir = _md_tree(root)
        _md_base_build(modules_dir)
        manifest_path = root / "module-manifest.json"
        _md_write_manifest(modules_dir, manifest_path, _md_base_modules())

        def cli(*extra):
            return subprocess.run(
                [sys.executable, str(TOOLS / "validate_architecture_gates.py"), "--gate",
                 "module-deps", "--modules-dir", str(modules_dir), "--module-manifest",
                 str(manifest_path), *extra],
                capture_output=True, text=True, check=False,
            )

        ok = cli("--json")
        assert ok.returncode == 0, ok.stdout + ok.stderr
        assert json.loads(ok.stdout)["status"] == PASS
        assert json.loads(ok.stdout)["checked"]

        # introduce a FAIL: a cross-domain private import.
        _md_module(modules_dir, "billing", {
            "interface.py": "def x():\n    return None\n",
            "models.py": "class Invoice:\n    pass\n",
        })
        (modules_dir / "membership" / "bad.py").write_text(
            "from app.modules.billing.models import Invoice\n"
        )
        manifest2 = _md_manifest(_md_base_modules())
        manifest2["modules"]["billing"] = _md_entry(
            "BIL-02", ["billing_"], ["app.modules.billing.interface"])
        manifest_path.write_text(json.dumps(manifest2))
        bad = cli()
        assert bad.returncode == 1, bad.stdout + bad.stderr

        # unusable input (manifest removed) -> ERROR.
        manifest_path.unlink()
        err = cli()
        assert err.returncode == 2, err.stdout + err.stderr

    res = subprocess.run([sys.executable, str(TOOLS / "validate_architecture_gates.py"), "--help"],
                         capture_output=True, text=True, check=False)
    for flag in ("--skip", "--exempt", "--allow", "--allowlist", "--ignore"):
        assert flag not in res.stdout, flag


# --- ADR-011 D4 (GATE2-R1-D4-ROOT-FILE-SCAN-2026-10-05): files directly under
# --modules-dir are scanned, not refused, as the reserved domain-free _root
# importer. Driven end-to-end through run_module_deps_gate via the existing
# _md_* fixture helpers above, matching this file's live-wiring-test
# convention. Root-level fixture files are written directly inside each test's
# own `build(modules_dir)` callback (overwriting `_md_tree`'s docstring-only
# root `__init__.py` where a test needs custom root content).


def test_d4_root_conftest_importing_internals_fails():
    def build(modules_dir):
        (modules_dir / "conftest.py").write_text(
            "from app.modules.billing.models import Invoice\n"
        )
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge():\n    return None\n",
            "models.py": "class Invoice:\n    pass\n",
        })

    modules = {"billing": _md_entry("BIL-02", ["billing_"], ["app.modules.billing.interface"])}
    report = _md_run(modules, build)
    assert report.status == FAIL, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    assert any(v.subject == f"{ROOT_IMPORTER} -> billing" for v in report.violations), \
        report.render()
    assert any("conftest.py" in v.detail and "billing" in v.detail and "BIL-02" in v.detail
               for v in report.violations), report.render()


def test_d4_root_init_file_sql_literal_referencing_owned_table_is_a_permanent_fail():
    # ADR-011 D4's disclosed consequence: _root owns no table, so a reference to any
    # module-owned table from a modules-root file is a permanent FAIL
    # CROSS_DOMAIN_SQL_IMPORT, never an ERROR. Asserted deliberately so a future
    # reader cannot mistake this for a regression.
    def build(modules_dir):
        (modules_dir / "__init__.py").write_text(
            '"""modules root."""\n'
            'QUERY = "SELECT id FROM billing_invoice"\n'
        )
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge():\n    return None\n",
        })

    modules = {"billing": _md_entry("BIL-02", ["billing_"], ["app.modules.billing.interface"])}
    report = _md_run(modules, build)
    assert report.status == FAIL, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    assert any("billing_invoice" in v.detail for v in report.violations), report.render()


def test_d4_root_conftest_importing_public_interface_passes_and_is_scanned():
    def build(modules_dir):
        (modules_dir / "conftest.py").write_text(
            "from app.modules.billing.interface import preview_charge\n"
            "from app.modules.billing.interface.fixtures import make_invoice\n"
        )
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge():\n    return None\n",
        })

    modules = {"billing": _md_entry("BIL-02", ["billing_"], ["app.modules.billing.interface"])}
    report = _md_run(modules, build)
    assert report.status == PASS, report.render()
    # proves the file was actually scanned, not skipped as a root-level entry
    assert "conftest.py" in report.checked, report.render()


def test_d4_root_file_unattributed_table_reference_is_error():
    def build(modules_dir):
        (modules_dir / "conftest.py").write_text(
            'QUERY = "SELECT id FROM unowned_legacy_table"\n'
        )

    report = _md_run(_md_base_modules(), build)
    assert report.status == ERROR, report.render()
    assert report.codes() == {"MODULE_DEPS_TABLE_UNATTRIBUTED"}, report.render()
    assert any("unowned_legacy_table" in v.detail for v in report.violations), report.render()


def test_d4_root_level_sql_file_is_scanned():
    def build(modules_dir):
        (modules_dir / "seed.sql").write_text("SELECT id FROM billing_invoice\n")
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge():\n    return None\n",
        })

    modules = {"billing": _md_entry("BIL-02", ["billing_"], ["app.modules.billing.interface"])}
    report = _md_run(modules, build)
    assert report.status == FAIL, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    assert any("seed.sql" in v.detail for v in report.violations), report.render()


def test_d4_root_level_symlink_is_refused():
    def build(modules_dir):
        real = modules_dir / "real_conftest.py"
        real.write_text("x = 1\n")
        (modules_dir / "conftest.py").symlink_to(real)

    report = _md_run(_md_base_modules(), build)
    _assert_md_input_error(report, "symlinked root-level file")


def test_d4_root_scan_does_not_regress_preexisting_pass_and_vacuous_tests():
    # `_md_tree`'s docstring-only root `__init__.py` is now an inspected,
    # non-substantive file (ADR-011 D4) rather than an unscanned one -- confirm the
    # pre-existing docstring-only-tree vacuous test and a representative PASS test
    # still hold with root-file scanning wired in.
    def vacuous_build(modules_dir):
        _md_module(modules_dir, "membership", {})  # only the auto docstring __init__.py

    vacuous_report = _md_run(_md_base_modules(), vacuous_build)
    assert vacuous_report.status == INCONCLUSIVE, vacuous_report.render()
    assert vacuous_report.codes() == {"MODULE_DEPS_GATE_VACUOUS"}, vacuous_report.render()

    pass_report = _md_run(_md_base_modules(), _md_base_build)
    assert pass_report.status == PASS, pass_report.render()
    assert pass_report.checked


# --- ADR-011 D5 (GATE2-R1-D5-NAMESPACE-COVERAGE-2026-10-05, R1-F04): a second,
# independent enumeration of --modules-dir reconciled against discovery, closing the
# gap where a directory with no __init__.py (a fully importable PEP 420 namespace
# package) silently vanished from the gate's view. Driven end-to-end through
# run_module_deps_gate via the existing _md_* fixture helpers, matching this file's
# live-wiring-test convention (same section as the D4 root-file-scan tests above).


def test_d5_namespace_directory_without_init_and_non_inert_file_is_coverage_error():
    """R1-F04's exact reproducer: `rogue/` has no `__init__.py`, so
    `_discover_modules` silently drops it and `_root_level_files` never
    descends into it either -- before this increment the directory and its
    contents (a cross-domain internal import and cross-domain SQL, planted
    here exactly as round 1's own P4f case did) vanished with no note, no
    count, and exit 0 PASS. Now it is ERROR
    MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH, never PASS."""
    def build(modules_dir):
        _md_base_build(modules_dir)
        rogue = modules_dir / "rogue"
        rogue.mkdir()
        (rogue / "x.py").write_text(
            "from app.modules.membership.models import Member\n"
            'QUERY = "SELECT id FROM membership_roster"\n'
        )

    report = _md_run(_md_base_modules(), build)
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH"}, report.render()
    assert any(v.subject == "rogue/x.py" for v in report.violations), report.render()
    # the offending file is detected-and-errored, not content-scanned -- D5 is about
    # path attribution, not re-implementing full module treatment for rogue/.
    assert "rogue/x.py" not in report.checked, report.render()


def test_d5_reconciliation_does_not_regress_ordinary_clean_tree_pass():
    """D5's own reconciliation must introduce no false positive on a tree with
    nothing but a declared module and the modules-root file -- the ordinary
    PASS shape SCN006 already proves, re-asserted here as D5's own invariant,
    with the new reconciliation note visibly present."""
    report = _md_run(_md_base_modules(), _md_base_build)
    assert report.status == PASS, report.render()
    assert any("coverage reconciliation (ADR-011 D5)" in n for n in report.notes), \
        report.render()


def test_d5_namespace_directory_with_only_inert_files_is_not_forced_to_error():
    """ADR-011 D5.2's explicit carve-out: a non-discovered directory containing
    only inert files (.md/.txt/.gitkeep) is not forced to ERROR -- only a
    non-inert file inside it is. Also regresses the dot-file-vs-dot-directory
    pruning distinction: `.gitkeep` is a dot-*file* and must be counted as
    inert, never silently pruned as if it were a dot-directory."""
    def build(modules_dir):
        _md_base_build(modules_dir)
        docs = modules_dir / "docs_only"
        docs.mkdir()
        (docs / "README.md").write_text("# notes\n")
        (docs / ".gitkeep").write_text("")

    report = _md_run(_md_base_modules(), build)
    assert report.status == PASS, report.render()
    assert "MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH" not in report.codes(), report.render()
    assert any("2 inert file(s) in inert-only namespace director" in n for n in report.notes), \
        report.render()


def test_d5_coverage_bucket_counts_appear_in_text_and_json_report():
    """ADR-011 D5.5: all bucket counts appear in the report, in both text and
    --json, on every run -- so a PASS is self-evidencing rather than merely
    silent."""
    report = _md_run(_md_base_modules(), _md_base_build)
    assert report.status == PASS, report.render()
    text = report.render()
    assert "coverage reconciliation (ADR-011 D5):" in text, text
    assert "module director" in text and "modules-root file(s)" in text, text
    payload = json.loads(report.to_json())
    assert any("coverage reconciliation (ADR-011 D5):" in n for n in payload["notes"]), payload


def test_d5_relative_root_limit_is_disclosed():
    """ADR-011 D5.6: totality is relative to the supplied --modules-dir only --
    this must be on the face of the report, not merely true in the
    implementation, and a manifest-declared module with no directory stays
    the existing 'no_dir' note rather than becoming a new ERROR."""
    report = _md_run(_md_base_modules(), _md_base_build)
    assert report.status == PASS, report.render()
    assert any("relative to the supplied --modules-dir" in n for n in report.notes), \
        report.render()

    def no_dir_build(modules_dir):
        pass  # declares "membership" in the manifest but creates no directory for it

    no_dir_report = _md_run(_md_base_modules(), no_dir_build)
    # vacuous (nothing but the docstring-only modules-root file exists to inspect),
    # never GATE_INPUT_INVALID or MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH -- a
    # manifest-declared-but-absent module is the pre-existing "no_dir" note, D5
    # introduces no new ERROR for it.
    assert no_dir_report.status == INCONCLUSIVE, no_dir_report.render()
    assert no_dir_report.codes() == {"MODULE_DEPS_GATE_VACUOUS"}, no_dir_report.render()
    assert any("manifest entries with no directory" in n for n in no_dir_report.notes), \
        no_dir_report.render()


def test_d5_preserves_f03_root_file_scanning_behavior():
    """F03 preservation control: ADR-011 D4's modules-root file scanning
    (R1-F03, independently verified by
    GATE2-R1-F03-ROOT-FILE-SCAN-VERIFICATION-2026-10-05) must keep working
    byte-for-byte alongside D5's new reconciliation running in the same pass
    -- a root conftest.py's private cross-domain import is still denied, and
    an unrelated benign inert-only namespace directory elsewhere neither
    masks nor alters that denial."""
    def build(modules_dir):
        (modules_dir / "conftest.py").write_text(
            "from app.modules.billing.models import Invoice\n"
        )
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge():\n    return None\n",
            "models.py": "class Invoice:\n    pass\n",
        })
        docs = modules_dir / "docs_only"
        docs.mkdir()
        (docs / "README.md").write_text("# notes\n")

    modules = {"billing": _md_entry("BIL-02", ["billing_"], ["app.modules.billing.interface"])}
    report = _md_run(modules, build)
    assert report.status == FAIL, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    assert any(v.subject == f"{ROOT_IMPORTER} -> billing" for v in report.violations), \
        report.render()
    assert any("conftest.py" in v.detail and "billing" in v.detail and "BIL-02" in v.detail
               for v in report.violations), report.render()


def test_d5_symlink_inside_namespace_directory_is_refused_via_reconciliation():
    """ADR-011 D5.3, isolating the genuinely-exercised branch: a symlink nested
    inside a non-discovered directory is new territory. `_discover_modules`
    only checks whether its own top-level entries are symlinks, and `rogue/`
    itself is a plain directory (not a symlink), so that check passes it
    through harmlessly without ever raising; `_root_level_files` never
    descends into any directory at all. Only `_scan_namespace_subtree`'s own
    walk (the D5 reconciliation) ever visits `rogue/link.py` -- unlike the
    pre-existing D4 root-level symlink test
    (test_d4_root_level_symlink_is_refused), where `_discover_modules` or
    `_root_level_files` could independently have caught it first."""
    def build(modules_dir):
        rogue = modules_dir / "rogue"
        rogue.mkdir()
        real = modules_dir / "real_target.py"
        real.write_text("x = 1\n")
        (rogue / "link.py").symlink_to(real)

    report = _md_run(_md_base_modules(), build)
    _assert_md_input_error(report, "symlink inside non-discovered namespace directory")
    assert "link.py" in report.render(), report.render()


def test_d5_unreadable_namespace_directory_surfaces_as_error_not_pass():
    """ADR-011 D5.4: `Path.is_dir()`/`Path.is_file()` swallow every `OSError`
    (confirmed by direct execution of `os.path.isdir`'s own
    `except (OSError, ValueError): return False`), including `EACCES` -- using
    them to decide whether a namespace directory has content would silently
    treat an unreadable directory as empty, the exact fail-open shape SCN-070
    already found on another surface. `_scan_namespace_subtree` uses
    `os.scandir` instead, whose failure must surface as `GateInputError`,
    never a PASS. Same skip discipline as
    tools/tests/test_validate_migration_ordering.py's own live chmod drills:
    return early (skip, not a false green) if this host does not enforce
    mode 000 -- observed in this environment (non-root, mode 000 enforced) to
    actually exercise the ERROR path, not merely compile it."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        modules_dir = _md_tree(root)
        secret = modules_dir / "secret"
        secret.mkdir()
        (secret / "x.py").write_text("x = 1\n")
        os.chmod(secret, 0o000)
        try:
            try:
                os.listdir(secret)
                return  # host does not enforce mode 000 -- skip, not a false green
            except PermissionError:
                pass
            manifest_path = root / "module-manifest.json"
            _md_write_manifest(modules_dir, manifest_path, _md_base_modules())
            report = run_module_deps_gate(modules_dir, manifest_path)
            assert report.status == ERROR, report.render()
            assert report.exit_code == 2, report.render()
            assert report.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, report.render()
            assert "secret" in report.render(), report.render()
            assert "PASS" not in report.render(), report.render()
        finally:
            os.chmod(secret, 0o755)


# --- ADR-011 D5.1 recursive coverage reconciliation (ADR011-D5.1-RECURSIVE-
# COVERAGE-RECONCILIATION): the top-level bucketing above (test_d5_* tests) trusted
# `_walk_module` to have walked a discovered module/`_shared` subtree completely.
# These tests close that residual, named in
# GATE2-R1-F04-NAMESPACE-COVERAGE-VERIFICATION-2026-10-05.md's Limits: a second,
# genuinely independent recursive enumeration (`_enumerate_eligible_descendants`)
# is diffed against the real walked-path union, so a `_walk_module` omission
# *inside* an already-recognised subtree is now MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH
# instead of a silent PASS.


def test_d5_recursive_reconciliation_catches_walk_omission_in_module_subtree():
    """Discriminating control: the fixture below PASSes under the real
    `_walk_module`. Monkeypatching `_walk_module` to drop one nested,
    non-inert file inside the discovered `membership` subtree -- the exact
    shape the top-level-only reconciliation could not see, since
    `_discover_modules` never dropped `membership` itself -- must now ERROR
    citing that nested path, proving the recursive diff (not the pre-existing
    top-level bucketing) is what caught it."""
    import validate_architecture_gates as gates

    def build(modules_dir):
        _md_base_build(modules_dir)
        nested_dir = modules_dir / "membership" / "sub"
        nested_dir.mkdir()
        (nested_dir / "extra.py").write_text("def helper():\n    return None\n")

    modules = _md_base_modules()
    omitted_relpath = "membership/sub/extra.py"

    pass_report = _md_run(modules, build)
    assert pass_report.status == PASS, pass_report.render()
    assert omitted_relpath in pass_report.checked, pass_report.render()

    original_walk_module = gates._walk_module

    # `*args` so the patch stays agnostic to `_walk_module`'s optional ADR-011 D8
    # file-accounting sink (GATE2-R1-F12-D8-FILE-COUNTS-2026-10-05): the stub is here to
    # drop one file from the returned list, not to model the real signature, and it
    # forwards whatever it is given so the real walk's counting is unaffected.
    def patched_walk_module(mod_dir, *args):
        return [p for p in original_walk_module(mod_dir, *args) if p.name != "extra.py"]

    gates._walk_module = patched_walk_module
    try:
        error_report = _md_run(modules, build)
    finally:
        gates._walk_module = original_walk_module

    assert error_report.status == ERROR, error_report.render()
    assert error_report.exit_code == 2, error_report.render()
    assert "MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH" in error_report.codes(), \
        error_report.render()
    assert any(v.subject == omitted_relpath for v in error_report.violations), \
        error_report.render()


def test_d5_recursive_reconciliation_catches_walk_omission_in_shared_subtree():
    """Same omission shape as the module-subtree control above, but inside
    `_shared` -- `_shared` is never a `_discover_modules` candidate at all
    (it is explicitly excluded there), so this exercises a structurally
    different call path to the same recursive diff."""
    import validate_architecture_gates as gates

    def build(modules_dir):
        _md_base_build(modules_dir)
        _md_module(modules_dir, SHARED_PACKAGE, {
            "util/helpers.py": "def noop():\n    return None\n",
        })

    modules = _md_base_modules()
    omitted_relpath = f"{SHARED_PACKAGE}/util/helpers.py"

    pass_report = _md_run(modules, build)
    assert pass_report.status == PASS, pass_report.render()
    assert omitted_relpath in pass_report.checked, pass_report.render()

    original_walk_module = gates._walk_module

    # `*args`, for the reason the sibling test above records.
    def patched_walk_module(mod_dir, *args):
        return [p for p in original_walk_module(mod_dir, *args) if p.name != "helpers.py"]

    gates._walk_module = patched_walk_module
    try:
        error_report = _md_run(modules, build)
    finally:
        gates._walk_module = original_walk_module

    assert error_report.status == ERROR, error_report.render()
    assert error_report.exit_code == 2, error_report.render()
    assert "MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH" in error_report.codes(), \
        error_report.render()
    assert any(v.subject == omitted_relpath for v in error_report.violations), \
        error_report.render()


def test_d5_recursive_reconciliation_benign_full_scan_still_passes():
    """Non-vacuous control for the recursive diff itself: a realistic
    multi-file subtree (nested packages two levels deep, a pruned
    `__pycache__` holding a `.pyc`, an inert `.md` file, and a pruned
    dot-directory holding a file neither walk may ever see) must still PASS
    with the new recursive counts disclosed -- proving the reconciliation is
    not unconditionally ERRORing, and that both walks prune identically."""
    def build(modules_dir):
        _md_module(modules_dir, "membership", {
            "service.py": "from app.modules.membership.models import Member\n",
            "models.py": "class Member:\n    pass\n",
            "sub/nested.py": "def helper():\n    return None\n",
            "sub/deep/more.py": "def helper2():\n    return None\n",
            "NOTES.md": "# notes\n",
        })
        pycache = modules_dir / "membership" / "sub" / "__pycache__"
        pycache.mkdir()
        (pycache / "nested.cpython-311.pyc").write_text("not-really-bytecode\n")
        dotdir = modules_dir / "membership" / ".cache"
        dotdir.mkdir()
        (dotdir / "ignored.py").write_text("x = 1\n")

    report = _md_run(_md_base_modules(), build)
    assert report.status == PASS, report.render()
    assert "MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH" not in report.codes(), report.render()
    assert "membership/sub/deep/more.py" in report.checked, report.render()
    assert any("eligible descendant file(s) independently re-enumerated" in n
               for n in report.notes), report.render()


def test_d5_reverse_reconciliation_catches_walked_path_the_enumeration_rejects():
    """ADR-011 D5.1's *reverse* direction, which the forward per-subtree diff
    structurally cannot see: a path `_walk_module` reached that the second,
    independent enumeration does not find eligible in any bucket. The
    injected path is a real, readable file inside a discovered module's
    `__pycache__` -- a directory `_enumerate_eligible_descendants` prunes
    without descending -- so the two traversals genuinely disagree about
    whether it is in the tree. Discriminating, not unconditional: the same
    fixture PASSes under the real `_walk_module` (asserted first), the
    forward diff stays silent about it by construction (every enumerated
    path is still walked), and the ERROR names the injected path
    specifically. This is the shape the previous increment disclosed as its
    named residual -- a walk that over-reaches was accepted on its own
    say-so, since only the enumerated-minus-walked direction was
    computed."""
    import validate_architecture_gates as gates

    def build(modules_dir):
        _md_base_build(modules_dir)
        pycache = modules_dir / "membership" / "__pycache__"
        pycache.mkdir()
        (pycache / "stale.py").write_text("x = 1\n")

    modules = _md_base_modules()
    injected_relpath = "membership/__pycache__/stale.py"

    pass_report = _md_run(modules, build)
    assert pass_report.status == PASS, pass_report.render()
    assert injected_relpath not in pass_report.checked, pass_report.render()

    original_walk_module = gates._walk_module

    # `*args`, for the reason the sibling tests above record.
    def patched_walk_module(mod_dir, *args):
        files = original_walk_module(mod_dir, *args)
        stale = mod_dir / "__pycache__" / "stale.py"
        if stale.is_file():
            files = files + [stale]
        return files

    gates._walk_module = patched_walk_module
    try:
        error_report = _md_run(modules, build)
    finally:
        gates._walk_module = original_walk_module

    assert error_report.status == ERROR, error_report.render()
    assert error_report.exit_code == 2, error_report.render()
    assert "MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH" in error_report.codes(), \
        error_report.render()
    offenders = [v for v in error_report.violations if v.subject == injected_relpath]
    assert offenders, error_report.render()
    # the reverse diff is what reported it -- not the forward per-subtree diff,
    # whose detail text names the opposite condition
    assert any("reverse coverage reconciliation" in v.detail for v in offenders), \
        error_report.render()


def test_d5_reverse_reconciliation_benign_all_three_buckets_still_passes():
    """Benign control for the reverse diff: with the real `_walk_module`,
    every path the walks reach must be confirmed eligible by the independent
    enumeration across all three buckets `scan_units` draws from -- a
    discovered module subtree (nested two deep), `_shared`, and modules-root
    files (including an inert dot-file) -- while pruned `__pycache__` and
    dot-directory content is reached by neither traversal. Proves the reverse
    diff is not unconditionally ERRORing and that no bucket was omitted from
    the eligible union (an omitted bucket would ERROR every file in it)."""
    def build(modules_dir):
        _md_module(modules_dir, "membership", {
            "service.py": "from app.modules.membership.models import Member\n",
            "models.py": "class Member:\n    pass\n",
            "sub/deep/more.py": "def helper():\n    return None\n",
            "NOTES.md": "# notes\n",
        })
        _md_module(modules_dir, SHARED_PACKAGE, {
            "util/helpers.py": "def noop():\n    return None\n",
        })
        (modules_dir / "conftest.py").write_text("import os\n")
        (modules_dir / ".gitkeep").write_text("")
        pycache = modules_dir / "membership" / "__pycache__"
        pycache.mkdir()
        (pycache / "stale.py").write_text("x = 1\n")
        dotdir = modules_dir / "membership" / ".cache"
        dotdir.mkdir()
        (dotdir / "ignored.py").write_text("x = 1\n")

    report = _md_run(_md_base_modules(), build)
    assert report.status == PASS, report.render()
    assert "MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH" not in report.codes(), report.render()
    # all three buckets genuinely participated
    assert "membership/sub/deep/more.py" in report.checked, report.render()
    assert f"{SHARED_PACKAGE}/util/helpers.py" in report.checked, report.render()
    assert "conftest.py" in report.checked, report.render()
    assert any("reverse direction" in n for n in report.notes), report.render()


# --- ADR-011 D5.5/D8 on the coverage ERROR path (ADR011-D5.5-ERROR-PATH-COUNTS):
# D5.5 ("all bucket counts appear in the report") and D8 ("every run ... discloses
# ... all D5.1 bucket counts") are unqualified by outcome, but a GateInputError
# raised *inside* the coverage enumeration used to return a bare
# MODULE_DEPS_GATE_INPUT_INVALID report with no coverage disclosure at all. These
# two tests pin the counts to the ERROR path in both text and --json, and pin the
# partial labelling that keeps them from being read as complete totals.


def _d5_partial_build(modules_dir):
    """One fixture shared by the ERROR and readable-control runs below, so the
    only difference between them is whether `zz_secret/` can be enumerated.
    Entry names are chosen so `os.scandir`'s sorted order puts the unreadable
    directory last (`__init__.py` < `conftest.py` < `docs_only` < `membership`
    < `zz_secret`): the enumeration therefore aborts *after* four buckets have
    real nonzero counts, which is what makes the partial note discriminating
    rather than an all-zeros stub.

    R1-F13 / ADR-011 D2: membership's eligible-file count is 4, not the 3 this
    fixture was originally calibrated against, because `_md_base_modules()`
    declares `app.modules.membership.interface` and that file must now actually
    exist -- `_md_run`/`_md_write_manifest` materialize it (see
    `_md_materialize_interfaces`). The arithmetic below is re-derived, not
    relaxed: both runs share the same tree, so the only difference between them
    is still whether `zz_secret/` can be enumerated."""
    _md_base_build(modules_dir)                       # membership/: 4 eligible files
    # (__init__.py, service.py, models.py, + the materialized interface.py)
    (modules_dir / "conftest.py").write_text("import os\n")   # + __init__.py = 2 root
    docs = modules_dir / "docs_only"
    docs.mkdir()
    (docs / "README.md").write_text("# notes\n")      # 1 inert namespace file
    secret = modules_dir / "zz_secret"
    secret.mkdir()
    (secret / "x.py").write_text("x = 1\n")


def test_d5_coverage_bucket_counts_survive_the_coverage_error_path():
    """ADR-011 D5.5/D8 on an aborted enumeration. `zz_secret/` at mode 000 makes
    `_discover_modules`'s `(entry / "__init__.py").is_file()` return False (it
    swallows `EACCES` -- D5.4's whole point), so the directory is never
    discovered and only the coverage reconciliation reaches it, where
    `os.scandir` raises `PermissionError` -> `GateInputError`. The run must stay
    ERROR exit 2 under MODULE_DEPS_GATE_INPUT_INVALID *and* carry the bucket
    counts it had established, in text and in `--json`, explicitly labelled a
    lower bound with the unreached buckets UNKNOWN and D5.1's reverse direction
    declared not-run. Discriminating three ways: (a) the counts asserted are
    the specific nonzero values this fixture produces, not merely "a note
    exists"; (b) the *same* fixture with `zz_secret/` readable produces the
    complete note and no partial labelling, so the partial wording is not
    unconditional; (c) the complete note's both-directions-ran claim must be
    absent from the partial run, since the reverse diff never executed. Same
    chmod skip discipline as
    test_d5_unreadable_namespace_directory_surfaces_as_error_not_pass: return
    early rather than report a false green on a host that does not enforce
    mode 000."""
    # (b) readable control on the identical tree: enumeration completes, so the
    # note is the complete shape. (This run is ERROR too -- zz_secret/x.py is an
    # unattributed path -- which is precisely why it isolates the note shape
    # rather than the status.)
    readable = _md_run(_md_base_modules(), _d5_partial_build)
    assert readable.status == ERROR, readable.render()
    assert readable.codes() == {"MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH"}, readable.render()
    assert any("coverage reconciliation (ADR-011 D5):" in n for n in readable.notes), \
        readable.render()
    assert not any("PARTIAL" in n for n in readable.notes), readable.render()
    assert any("1 module directory" in n and "2 modules-root file(s)" in n
               for n in readable.notes), readable.render()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        modules_dir = _md_tree(root)
        _d5_partial_build(modules_dir)
        secret = modules_dir / "zz_secret"
        os.chmod(secret, 0o000)
        try:
            try:
                os.listdir(secret)
                return  # host does not enforce mode 000 -- skip, not a false green
            except PermissionError:
                pass
            manifest_path = root / "module-manifest.json"
            _md_write_manifest(modules_dir, manifest_path, _md_base_modules())
            report = run_module_deps_gate(modules_dir, manifest_path)
        finally:
            os.chmod(secret, 0o755)

    # fail-closed outcome unchanged by this increment
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, report.render()
    assert "zz_secret" in report.render(), report.render()
    assert "PASS" not in report.render(), report.render()

    # (a) the counts are present, partial-labelled, and accurate for what the
    # enumeration actually completed before aborting
    partial = [n for n in report.notes if "coverage reconciliation (ADR-011 D5) PARTIAL" in n]
    assert len(partial) == 1, report.render()
    note = partial[0]
    assert "LOWER BOUND" in note and "UNKNOWN rather than zero" in note, note
    assert "1 module directory" in note, note
    assert "0 _shared directories" in note, note
    assert "2 modules-root file(s)" in note, note
    assert "1 inert file(s) in inert-only namespace director" in note, note
    assert "4 eligible descendant file(s)" in note, note
    assert "0 unattributed path(s) found before the abort" in note, note
    # (c) no complete-run claim leaks onto the partial path
    assert not any("coverage reconciliation (ADR-011 D5):" in n for n in report.notes), \
        report.render()
    assert not any("runs both directions of the set diff" in n for n in report.notes), \
        report.render()
    assert any("reverse direction" in n and "did NOT run" in n for n in report.notes), \
        report.render()
    # D5.6's relativity limit is still true of a partial enumeration and stays disclosed
    assert any("relative to the supplied --modules-dir" in n for n in report.notes), \
        report.render()
    # gate-level disclosure that preceded the abort is not discarded with the frame
    assert any("declared module(s)" in n for n in report.notes), report.render()

    # both surfaces: text (render) and --json (notes are part of asdict())
    text = report.render()
    assert "coverage reconciliation (ADR-011 D5) PARTIAL" in text, text
    assert "4 eligible descendant file(s)" in text, text
    payload = json.loads(report.to_json())
    assert payload["status"] == ERROR, payload
    assert any("coverage reconciliation (ADR-011 D5) PARTIAL" in n
               for n in payload["notes"]), payload
    assert any("LOWER BOUND" in n for n in payload["notes"]), payload


def test_d5_benign_pass_reports_complete_counts_with_no_partial_labelling():
    """Benign PASS control for the partial-disclosure path: an ordinary clean
    tree must keep reporting the *complete* D5.5 bucket counts in both text and
    --json, with none of the partial vocabulary attached. Without this control
    the increment above could satisfy its own assertions by labelling every run
    partial, which would make a PASS report claim less than it actually
    established."""
    report = _md_run(_md_base_modules(), _md_base_build)
    assert report.status == PASS, report.render()
    text = report.render()
    payload = json.loads(report.to_json())
    assert "coverage reconciliation (ADR-011 D5):" in text, text
    assert any("coverage reconciliation (ADR-011 D5):" in n for n in payload["notes"]), payload
    assert any("runs both directions of the set diff" in n for n in report.notes), \
        report.render()
    for marker in ("PARTIAL", "LOWER BOUND", "UNKNOWN rather than zero", "did NOT run"):
        assert marker not in text, (marker, text)
        assert not any(marker in n for n in payload["notes"]), (marker, payload)


# --- ADR-011 D5.5/D8 on the *pre-coverage* ERROR path (ADR011-D5.5-PRECOVERAGE-
# ERROR-DISCLOSURE): the partial-disclosure increment above covers an abort
# *inside* the reconciliation pass. An abort *upstream* of it -- an absent
# --modules-dir is the simplest -- still returned `notes == []`: ERROR exit 2
# with no coverage disclosure at all in either surface, the same note-blind
# shape D5.5/D8 forbid. These two tests pin the pre-coverage shape and pin that
# it does not leak onto a run that did enumerate.


def test_d5_absent_modules_dir_discloses_not_started_rather_than_nothing():
    """ADR-011 D5.5/D8 on a run that aborted before the coverage enumeration
    began. `_modules_root_package` raises on the absent directory, upstream of
    `_reconcile_module_coverage`, so neither the complete nor the partial
    disclosure path can have run. The report must still carry a coverage note,
    in text and in `--json`.

    Discriminating four ways, because "a note exists" is too weak a bar here:
    (a) the fail-closed outcome is unchanged -- ERROR, exit 2,
    MODULE_DEPS_GATE_INPUT_INVALID, never PASS; (b) every bucket reads
    NOT_STARTED and the unattributed count UNKNOWN -- a zero-filled
    `_CoverageCounts()` would render `0 module directory`/`0 unattributed
    path(s)` and assert that the enumeration looked and found nothing, which is
    the fabricated-total failure mode D5.5 exists to prevent, so the absence of
    those zero strings is asserted explicitly; (c) the *partial* vocabulary must
    not be reused, since nothing was established before this abort; (d) both
    directions of D5.1's diff are declared not-run, so the absent
    MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH is not readable as a clean
    reconciliation."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        manifest_path = root / "module-manifest.json"
        manifest_path.write_text(json.dumps(_md_manifest(_md_base_modules())))
        report = run_module_deps_gate(root / "app" / "modules", manifest_path)

    # (a) fail-closed outcome unchanged by this increment
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, report.render()
    assert "PASS" not in report.render(), report.render()

    not_started = [n for n in report.notes
                   if "coverage reconciliation (ADR-011 D5) NOT_STARTED" in n]
    assert len(not_started) == 1, report.render()
    note = not_started[0]
    # (b) NOT_STARTED/UNKNOWN in every count slot, and no fabricated zeros
    assert "NOT_STARTED module directory/ies" in note, note
    assert "NOT_STARTED _shared directory/ies" in note, note
    assert "NOT_STARTED modules-root file(s)" in note, note
    assert "NOT_STARTED pruned entry/ies" in note, note
    assert "NOT_STARTED inert file(s) in inert-only namespace director" in note, note
    assert "NOT_STARTED eligible descendant file(s)" in note, note
    assert "unattributed path(s) UNKNOWN" in note, note
    for fabricated in ("0 module director", "0 _shared director", "0 modules-root file",
                       "0 pruned entr", "0 inert file(s)", "0 eligible descendant",
                       "0 unattributed path"):
        assert fabricated not in note, (fabricated, note)
    # (c) the partial shape's claims are not reused on a pass that never ran
    for marker in ("PARTIAL", "LOWER BOUND", "established before the abort",
                   "found before the abort", "coverage reconciliation (ADR-011 D5):"):
        assert not any(marker in n for n in report.notes), (marker, report.render())
    # (d) neither direction ran, and the complete run's claim is absent
    assert any("NEITHER direction" in n for n in report.notes), report.render()
    assert not any("runs both directions of the set diff" in n for n in report.notes), \
        report.render()
    # D5.6's relativity limit is exactly what a wrong/absent root needs disclosed
    assert any("relative to the supplied --modules-dir" in n for n in report.notes), \
        report.render()

    # both surfaces: text (render) and --json (notes are part of asdict())
    text = report.render()
    assert "coverage reconciliation (ADR-011 D5) NOT_STARTED" in text, text
    payload = json.loads(report.to_json())
    assert payload["status"] == ERROR, payload
    assert any("coverage reconciliation (ADR-011 D5) NOT_STARTED" in n
               for n in payload["notes"]), payload
    assert any("unattributed path(s) UNKNOWN" in n for n in payload["notes"]), payload


def test_d5_benign_pass_reports_no_not_started_labelling():
    """Benign PASS control for the pre-coverage path: an ordinary clean tree
    must keep reporting the *complete* D5.5 bucket counts, with real integers
    and none of the pre-coverage vocabulary. Without this control the increment
    above could satisfy its own assertions by labelling every run NOT_STARTED,
    which would make a PASS report disclaim coverage it actually performed."""
    report = _md_run(_md_base_modules(), _md_base_build)
    assert report.status == PASS, report.render()
    text = report.render()
    payload = json.loads(report.to_json())
    assert "coverage reconciliation (ADR-011 D5):" in text, text
    assert any("1 module directory" in n for n in report.notes), report.render()
    assert any("0 unattributed path(s)" in n for n in report.notes), report.render()
    # `directory/ies` is deliberately NOT a marker here: the complete note has
    # always carried that neutral plural for the namespace-inert bucket, so it
    # does not discriminate the pre-coverage shape. The count slots do.
    for marker in ("NOT_STARTED", "NEITHER direction", "unattributed path(s) UNKNOWN",
                   "module directory/ies", "pruned entry/ies"):
        assert marker not in text, (marker, text)
        assert not any(marker in n for n in payload["notes"]), (marker, payload)


# --- R1-F07 / ADR-011 D7.3: the remaining bare approval reads, and `main`'s -------
# outermost internal-error funnel (GATE2-R1-F07-D73-ERROR-FUNNEL-2026-10-05).
#
# Two halves of the same decision. (a) `resolve_approval` held the last two bare
# `path.read_text(encoding="utf-8")` calls in the file — the ADR record and the
# OWNER_APPROVALS register. Both are reached by the *permission* gate through
# `parse_registry` (and by the RLS gate through `parse_rls_manifest`), so an
# unreadable or non-UTF-8 approval record killed a gate run with an uncaught
# exception: exit 1, no `GateReport` at all. All four shapes below were reproduced
# by direct execution before this increment. (b) `main` had no outermost funnel, so
# an unexpected throw anywhere — including inside report *emission* — produced the
# same R1-F07 shape one layer up. D7.3 closes both by construction.
#
# Every negative here is paired with a positive control, because each fix could
# otherwise satisfy its own test by refusing all input or by funnelling every run.

import contextlib
import io

from validate_architecture_gates import GateReport, main

_SIGN_IN_PATHS = {"/s": {"post": _op("s", SIGN_IN, "credential_exchange", [])}}

# `_ADR901` with one latin-1 byte: still names all three permissions, so a gate that
# somehow decoded it would PASS — the failure cannot hide behind an unrelated miss.
_NON_UTF8_ADR_RECORD = (b"---\nstatus: DECIDED\n---\niam.session.create for caf\xe9\n"
                        b"billing.provider_event.ingest\nplatform.health.read\n")
_NON_UTF8_OWN_ROW = b"| OWN-901 | approves iam.session.create at caf\xe9 |\n"


def _assert_permission_input_error(report, *fragments):
    """Shared shape for the four approval-read negatives: ERROR, exit 2, exactly
    `PERMISSION_GATE_INPUT_INVALID`, never the word PASS anywhere in the report, on
    both the text and JSON surfaces."""
    text = report.render()
    assert report.status == ERROR, text
    assert report.exit_code == 2, text
    assert report.codes() == {"PERMISSION_GATE_INPUT_INVALID"}, text
    assert PASS not in text, text
    for fragment in fragments:
        assert fragment in text, (fragment, text)
    payload = json.loads(report.to_json())
    assert payload["status"] == ERROR, payload
    assert [v["code"] for v in payload["violations"]] == ["PERMISSION_GATE_INPUT_INVALID"], payload


def test_f07_non_utf8_adr_approval_record_is_named_error_not_traceback():
    """R1-F07 / ADR-011 D7.3, approval-read half: a non-UTF-8 ADR record reached a
    bare read inside `resolve_approval`, so the permission gate died with an
    uncaught `UnicodeDecodeError` (exit 1, no report — reproduced by direct
    execution before this increment). The fail-closed outcome is a named
    `PERMISSION_GATE_INPUT_INVALID` ERROR at exit 2.

    The message must attribute the *read*, not a downstream symptom: a swallow-to-
    empty-string "fix" would instead report "does not mention", misattributing an
    unusable input to a missing approval and sending a reader to the wrong file."""
    try:
        _NON_UTF8_ADR_RECORD.decode("utf-8")
        return  # defensive: fixture is no longer non-UTF-8, skip rather than false-green
    except UnicodeDecodeError:
        pass

    root = _approval_root(_ADR901, ["| OWN-901 | approves iam.session.create |"])
    (root / "knowledge" / "04-Decisions" / "ADR-901-fixture.md").write_bytes(_NON_UTF8_ADR_RECORD)
    report = _run_with_root(_SIGN_IN_PATHS, _registry_with("ADR-901"), root)
    _assert_permission_input_error(report, "approval ADR-901", "cannot read ADR record",
                                   "UnicodeDecodeError")
    assert "does not mention" not in report.render(), report.render()


def test_f07_valid_utf8_non_ascii_approval_record_still_resolves():
    """Valid-UTF-8 control for the negative above: a record whose non-ASCII content
    *is* UTF-8 must still be read and resolve to PASS. Without this control the fix
    could satisfy its own test by refusing every non-ASCII approval record — which
    would make every approval in the repository unresolvable."""
    root = _approval_root(_ADR901, ["| OWN-901 | approves iam.session.create |"])
    (root / "knowledge" / "04-Decisions" / "ADR-901-fixture.md").write_bytes(
        # the same character as the non-UTF-8 fixture, encoded as valid UTF-8
        _NON_UTF8_ADR_RECORD.replace(b"caf\xe9", b"caf\xc3\xa9")
    )
    report = _run_with_root(_SIGN_IN_PATHS, _registry_with("ADR-901"), root)
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()


def test_f07_unreadable_adr_approval_record_is_named_error_not_traceback():
    """Same read site, `OSError` rather than `UnicodeDecodeError`: an unreadable ADR
    record must also become `PERMISSION_GATE_INPUT_INVALID` at exit 2, not an
    uncaught `PermissionError`. The type name is asserted because decode failure and
    `EACCES` are otherwise indistinguishable in the report. Same chmod skip
    discipline as test_f07_unreadable_python_source_is_named_error_not_traceback:
    return early (skip, not a false green) if this host does not enforce mode 000."""
    root = _approval_root(_ADR901, ["| OWN-901 | approves iam.session.create |"])
    record = root / "knowledge" / "04-Decisions" / "ADR-901-fixture.md"
    os.chmod(record, 0o000)
    try:
        try:
            record.read_bytes()
            return  # host does not enforce mode 000 -- skip, not a false green
        except PermissionError:
            pass
        report = _run_with_root(_SIGN_IN_PATHS, _registry_with("ADR-901"), root)
        _assert_permission_input_error(report, "approval ADR-901", "cannot read ADR record",
                                       "PermissionError")
    finally:
        os.chmod(record, 0o644)


def test_f07_non_utf8_owner_approvals_register_is_named_error_not_traceback():
    """The second bare read in `resolve_approval`: a non-UTF-8 OWNER_APPROVALS
    register. Exercised through an `OWN-` reference so the register is actually
    read (an `ADR-` reference never opens it).

    The decisive assertion is that the report does *not* say "0 OWNER_APPROVALS
    rows, need 1". That is the message a swallow-to-empty-string would produce, and
    it is the dangerous shape: it reads as "this approval does not exist" when the
    truth is "the register could not be read", so the register could be made
    unreadable and every approval check would report a uniform, plausible miss."""
    try:
        _NON_UTF8_OWN_ROW.decode("utf-8")
        return  # defensive: fixture is no longer non-UTF-8, skip rather than false-green
    except UnicodeDecodeError:
        pass

    root = _approval_root(_ADR901, ["| OWN-901 | approves iam.session.create |"])
    (root / "knowledge" / "00-System" / "OWNER_APPROVALS.md").write_bytes(
        b"| ID | Decision |\n|---|---|\n" + _NON_UTF8_OWN_ROW)
    report = _run_with_root(_SIGN_IN_PATHS, _registry_with("OWN-901"), root)
    _assert_permission_input_error(report, "approval OWN-901",
                                   "cannot read OWNER_APPROVALS register", "UnicodeDecodeError")
    assert "rows, need 1" not in report.render(), report.render()


def test_f07_unreadable_owner_approvals_register_is_named_error_not_traceback():
    """`OSError` half of the register read, with the same anti-misattribution
    assertion. Same chmod skip discipline as the ADR-record case above."""
    root = _approval_root(_ADR901, ["| OWN-901 | approves iam.session.create |"])
    register = root / "knowledge" / "00-System" / "OWNER_APPROVALS.md"
    os.chmod(register, 0o000)
    try:
        try:
            register.read_bytes()
            return  # host does not enforce mode 000 -- skip, not a false green
        except PermissionError:
            pass
        report = _run_with_root(_SIGN_IN_PATHS, _registry_with("OWN-901"), root)
        _assert_permission_input_error(report, "approval OWN-901",
                                       "cannot read OWNER_APPROVALS register", "PermissionError")
        assert "rows, need 1" not in report.render(), report.render()
    finally:
        os.chmod(register, 0o644)


def test_f07_readable_owner_approvals_register_still_resolves():
    """Positive control for both register negatives: a readable, UTF-8 register with
    a matching row must still resolve to PASS, so neither fix above can have been
    achieved by refusing every `OWN-` reference."""
    root = _approval_root(_ADR901, ["| OWN-901 | approves iam.session.create |"])
    report = _run_with_root(_SIGN_IN_PATHS, _registry_with("OWN-901"), root)
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()


def test_f07_missing_owner_approvals_row_still_reports_the_missing_row():
    """Pre-existing semantics control: a genuinely absent `OWN-` row must still
    report the row-count miss, not the new read-failure message. The read-failure
    conversion must not have blurred "unreadable register" into "no such row" in
    either direction."""
    root = _approval_root(_ADR901, ["| OWN-902 | approves something else |"])
    report = _run_with_root(_SIGN_IN_PATHS, _registry_with("OWN-901"), root)
    _assert_permission_input_error(report, "approval OWN-901", "rows, need 1")
    assert "cannot read" not in report.render(), report.render()


# --- D7.3's outermost funnel in `main` --------------------------------------------

_EMISSION_SECRET = "dsn=postgres://user:pw@host/db"


def _cli(argv):
    """`main(argv)` with stdout captured, returning `(exit_code, stdout)`. Uses
    `redirect_stdout` rather than a pytest fixture because this file is also
    executed directly by its own `__main__` runner, which calls each test with no
    arguments."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(argv)
    return code, buf.getvalue()


def _md_cli_argv(root: Path, *extra):
    """A clean, PASS-worthy module tree on disk plus the argv that scans it."""
    modules_dir = _md_tree(root)
    _md_base_build(modules_dir)
    raw = _md_manifest(_md_base_modules())
    _md_materialize_interfaces(modules_dir, raw)  # R1-F13: see `_md_materialize_interfaces`
    manifest_path = root / "module-manifest.json"
    manifest_path.write_text(json.dumps(raw))
    return ["--gate", "module-deps", "--modules-dir", str(modules_dir),
            "--module-manifest", str(manifest_path), *extra]


@contextlib.contextmanager
def _emission_throws(exc_factory):
    """Inject an unexpected exception into report emission by replacing *both*
    `GateReport.render` and `GateReport.to_json`.

    Replacing both is the point: D7.3 requires the funnel's own emission to be a
    minimal last-resort path that does not call back into the report builder. Under
    this patch, a funnel that re-entered the builder would raise from inside its own
    handler and reproduce R1-F07's "non-zero exit, empty stdout" one layer up, so
    every assertion that the funnel still printed something is simultaneously an
    assertion that it did not re-enter."""
    original = (GateReport.render, GateReport.to_json)

    def boom(self):
        raise exc_factory()

    GateReport.render, GateReport.to_json = boom, boom
    try:
        yield
    finally:
        GateReport.render, GateReport.to_json = original


def test_f07_main_funnels_unexpected_emission_exception_on_text_surface():
    """R1-F07 / ADR-011 D7.3, funnel half: an unexpected exception raised while the
    report is being emitted used to escape `main` entirely — Python's own traceback,
    exit 1, nothing on stdout (reproduced by direct execution before this
    increment). It must now become a named `MODULE_DEPS_GATE_INTERNAL_ERROR` line at
    exit 2.

    The exception's *message* must not appear: an arbitrary unexpected error may
    carry a DSN or other connection parameter, which `_rls_from_cli` already refuses
    to disclose for exactly this reason. The class name is disclosed; the message is
    not."""
    with tempfile.TemporaryDirectory() as tmp:
        argv = _md_cli_argv(Path(tmp))
        with _emission_throws(lambda: RuntimeError(f"injected {_EMISSION_SECRET}")):
            code, out = _cli(argv)
    assert code == 2, out
    assert out.strip(), "funnel produced no report at all -- R1-F07's exact shape"
    assert "MODULE_DEPS_GATE_INTERNAL_ERROR" in out, out
    assert "[module-deps] ERROR" in out, out
    assert "RuntimeError" in out, out
    assert PASS not in out, out
    assert _EMISSION_SECRET not in out, out
    assert "Traceback" not in out, out


def test_f07_main_funnels_unexpected_emission_exception_on_json_surface():
    """Same injected failure under `--json`. The hand-built object must be real,
    parseable JSON carrying `GateReport.to_json`'s own key set, so a consumer that
    parses the gate's JSON still parses the funnel's output instead of choking on a
    stray text line (the funnel is useless to CI otherwise)."""
    real_keys = set(json.loads(GateReport("module-deps", ERROR).to_json()))
    with tempfile.TemporaryDirectory() as tmp:
        argv = _md_cli_argv(Path(tmp), "--json")
        with _emission_throws(lambda: RuntimeError(f"injected {_EMISSION_SECRET}")):
            code, out = _cli(argv)
    assert code == 2, out
    payload = json.loads(out)
    assert set(payload) == real_keys, (set(payload), real_keys)
    assert payload["status"] == ERROR, payload
    assert payload["gate"] == "module-deps", payload
    assert payload["checked"] == [], payload
    assert [v["code"] for v in payload["violations"]] == ["MODULE_DEPS_GATE_INTERNAL_ERROR"], payload
    assert payload["violations"][0]["subject"] == "-", payload
    assert "RuntimeError" in payload["violations"][0]["detail"], payload
    assert _EMISSION_SECRET not in out, out
    assert PASS not in out, out


def test_f07_internal_error_funnel_never_reenters_the_report_builder():
    """D7.3 states the funnel's emission must not call back into the report builder.
    Asserted against the funnel directly, with both builder methods replaced by a
    throw: a re-entering implementation raises out of its own handler here instead
    of returning 2 on both surfaces."""
    from validate_architecture_gates import _emit_internal_error

    with _emission_throws(lambda: RuntimeError("builder re-entered")):
        for as_json in (False, True):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = _emit_internal_error("module-deps", as_json, ValueError("boom"))
            out = buf.getvalue()
            assert code == 2, (as_json, out)
            assert "MODULE_DEPS_GATE_INTERNAL_ERROR" in out, (as_json, out)
            assert PASS not in out, (as_json, out)
            if as_json:
                json.loads(out)  # still valid JSON, built without the builder


def test_f07_internal_error_funnel_sanitises_the_gate_and_exception_tokens():
    """The only two varying tokens are sanitised to `[A-Za-z0-9_.-]`, so neither a
    hostile gate label nor an exotic exception class name can break JSON quoting or
    inject an extra report line into the text surface. Exercised directly because no
    CLI path can currently supply such a label — this guards the funnel against a
    future caller that could."""
    from validate_architecture_gates import _emit_internal_error

    class Weird_Error_(Exception):
        pass

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = _emit_internal_error('ga"te\nINJECTED: x', True, Weird_Error_("x"))
    out = buf.getvalue()
    assert code == 2, out
    payload = json.loads(out)  # would raise on an unescaped quote or newline
    assert payload["gate"] == "gateINJECTEDx", payload
    assert "Weird_Error_" in payload["violations"][0]["detail"], payload


def test_f07_main_funnel_reports_the_gate_that_was_running():
    """Truthful attribution: the funnel labels whichever gate argparse selected, so
    a crash under `--gate permission` is not misreported as a module-deps run. The
    violation *code* stays D7's single `MODULE_DEPS_GATE_INTERNAL_ERROR` — per-gate
    internal-error codes would be new entries in ADR-009/ADR-010's own taxonomies,
    deliberately not invented here."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "openapi").mkdir()
        (d / "openapi" / "api.json").write_text(json.dumps(_doc(_SIGN_IN_PATHS)))
        (d / "r.json").write_text(json.dumps(REGISTRY))
        argv = ["--gate", "permission", "--openapi-dir", str(d / "openapi"),
                "--registry", str(d / "r.json"), "--json"]
        with _emission_throws(lambda: RuntimeError("injected")):
            code, out = _cli(argv)
    assert code == 2, out
    payload = json.loads(out)
    assert payload["gate"] == "permission", payload
    assert [v["code"] for v in payload["violations"]] == ["MODULE_DEPS_GATE_INTERNAL_ERROR"], payload


def test_f07_main_funnel_does_not_catch_systemexit_or_keyboardinterrupt():
    """D7.3 names both exclusions explicitly. `SystemExit` must keep its own code
    (not be rewritten to 2), which is what makes argparse's usage exit and
    `sys.exit(main())` behave; `KeyboardInterrupt` must stay interrupting."""
    with tempfile.TemporaryDirectory() as tmp:
        argv = _md_cli_argv(Path(tmp))
        for factory, expected in ((lambda: SystemExit(7), SystemExit),
                                  (lambda: KeyboardInterrupt(), KeyboardInterrupt)):
            raised = None
            with _emission_throws(factory):
                try:
                    _cli(argv)
                except BaseException as exc:  # noqa: BLE001 -- that is the assertion
                    raised = exc
            assert isinstance(raised, expected), (expected, raised)
            if isinstance(raised, SystemExit):
                assert raised.code == 7, raised.code


def test_f07_argparse_usage_exit_still_propagates_through_the_funnel():
    """The same exclusion on the path that actually uses it today: an invalid
    `--gate` must still be argparse's own `SystemExit`, not a funnelled report.
    stderr is captured only to keep the usage block out of the test output."""
    raised = None
    try:
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            main(["--gate", "not-a-real-gate"])
    except SystemExit as exc:
        raised = exc
    assert isinstance(raised, SystemExit), raised
    assert raised.code == 2, raised.code


def test_f07_main_still_emits_the_real_report_when_nothing_throws():
    """Positive control for the funnel: wrapping the whole CLI body in `try` must
    not change a clean run. The real PASS report and exit 0 still come out on both
    surfaces, and the internal-error code appears nowhere."""
    with tempfile.TemporaryDirectory() as tmp:
        code, out = _cli(_md_cli_argv(Path(tmp)))
    assert code == 0, out
    assert "[module-deps] PASS" in out, out
    assert "MODULE_DEPS_GATE_INTERNAL_ERROR" not in out, out
    with tempfile.TemporaryDirectory() as tmp:  # a fresh tree: `_md_tree` creates `app/`
        json_code, json_out = _cli(_md_cli_argv(Path(tmp), "--json"))
    assert json_code == 0, json_out
    payload = json.loads(json_out)
    assert payload["status"] == PASS, payload
    assert payload["violations"] == [], payload
    assert payload["notes"], "a PASS must stay self-evidencing (ADR-011 D8)"


def test_f07_main_still_returns_exit_1_for_a_real_fail():
    """Second positive control: the funnel must not flatten real verdicts to its own
    exit 2. A genuine cross-domain import still exits 1 with its own FAIL code."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        modules_dir = _md_tree(root)
        _md_module(modules_dir, "membership",
                   {"service.py": "from app.modules.billing.models import Invoice\n"})
        _md_module(modules_dir, "billing", {"models.py": "class Invoice:\n    pass\n",
                                            "interface.py": "def preview():\n    return None\n"})
        manifest_path = root / "module-manifest.json"
        _md_write_manifest(modules_dir, manifest_path, {
            "membership": _md_entry("MEM-01", ["membership_"],
                                    ["app.modules.membership.interface"]),
            "billing": _md_entry("BIL-02", ["billing_"], ["app.modules.billing.interface"]),
        })
        code, out = _cli(["--gate", "module-deps", "--modules-dir", str(modules_dir),
                          "--module-manifest", str(manifest_path)])
    assert code == 1, out
    assert "CROSS_DOMAIN_SQL_IMPORT" in out, out
    assert "MODULE_DEPS_GATE_INTERNAL_ERROR" not in out, out
    assert PASS not in out, out


def test_f07_read_decode_conversion_stays_confined_to_its_two_helpers():
    """ADR-011 D7.3 says *one* helper converts read/decode failures. Asserted
    structurally over the tool's AST — not its text, so prose mentioning the call in
    a docstring does not register: every `.read_text(...)` call in the file must sit
    inside `_read_gate_text` (the text helper) or `_load_json` (its JSON-shaped
    sibling, which must also convert the parse step).

    A new bare read site anywhere else is exactly how R1-F07 recurred twice — the
    `.py` scan site, then the `.sql` one, then the two approval reads — so this is
    the regression guard for the next one rather than a restatement of the fix."""
    import ast

    source = (TOOLS / "validate_architecture_gates.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    owners = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for inner in ast.walk(node):
            if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "read_text"):
                owners.add(node.name)
    # Nested functions would report both names; neither helper nests one, so an
    # exact set is the right assertion and a new owner fails loudly.
    assert owners == {"_read_gate_text", "_load_json"}, owners


# --- R1-F09 (GATE2-R1-F09-D72-MIXED-REPORT-2026-10-05): ADR-011 D7.2 partitioned
# reporting of a *mixed* run.
#
# R1-F09's shape: a run that found a genuine CROSS_DOMAIN_SQL_IMPORT *and* hit an
# uninspectable SQL construct used to return an ERROR report built only from the
# ERROR-class buckets, silently discarding the FAIL-class `violations` it had
# already collected. The real finding vanished from both the text and the --json
# surface -- exit 2 read as "could not inspect", not as "could not inspect, and by
# the way here is a real cross-domain violation".
#
# D7.2 requires both partitions reported while the run stays ERROR at exit 2. The
# fixtures below pin that together with the two single-cause controls, because the
# failure mode is specifically about what survives when the two co-occur: either
# control alone passes against the pre-fix code.

_F09_MODULES = {
    "membership": _md_entry("MEM-01", ["membership_"], ["app.modules.membership.interface"]),
    "billing": _md_entry("BIL-02", ["billing_"], ["app.modules.billing.interface"]),
}

# A FROM with no identifier after it: the table name is concatenated in, so the
# scanner cannot inspect it -- MODULE_DEPS_SOURCE_UNINSPECTABLE, ERROR.
_F09_UNINSPECTABLE_SQL = "SELECT total FROM \n"
# A genuine cross-domain import of another module's internal path --
# CROSS_DOMAIN_SQL_IMPORT, FAIL.
_F09_CROSS_DOMAIN_PY = "from app.modules.billing.models import Invoice\n"


def _f09_billing(modules_dir):
    _md_module(modules_dir, "billing", {
        "models.py": "class Invoice:\n    pass\n",
        "interface.py": "def preview_charge(member):\n    return None\n",
    })


def _f09_run(membership_files):
    def build(modules_dir):
        _md_module(modules_dir, "membership", membership_files)
        _f09_billing(modules_dir)

    return _md_run(_F09_MODULES, build)


def _f09_partition_note(report):
    notes = [n for n in report.notes if "ADR-011 D7.2 partitioned report" in n]
    assert len(notes) == 1, report.render()
    return notes[0]


def test_f09_mixed_run_reports_both_partitions_as_error_exit_2():
    """The headline case: one genuine cross-domain import and one uninspectable SQL
    in the same run must yield BOTH named findings, with the run still ERROR at
    exit 2 (fail-closed -- an incomplete scan must not downgrade itself to FAIL)."""
    report = _f09_run({"service.py": _F09_CROSS_DOMAIN_PY,
                       "assemble.sql": _F09_UNINSPECTABLE_SQL})
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT",
                              "MODULE_DEPS_SOURCE_UNINSPECTABLE"}, report.render()

    cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    uninspectable = [v for v in report.violations
                     if v.code == "MODULE_DEPS_SOURCE_UNINSPECTABLE"]
    assert len(cross) == 1, report.render()
    assert len(uninspectable) == 1, report.render()
    # Each finding still names its own subject: the partitioned report must not
    # blur the two into a single summary row.
    assert cross[0].subject == "membership -> billing", cross[0]
    assert "service.py" in cross[0].detail, cross[0]
    assert uninspectable[0].subject == "membership/assemble.sql", uninspectable[0]

    # Partitioned, not interleaved: every FAIL-class violation precedes every
    # ERROR-class one, so a reader (or a corpus) can split the list by position.
    codes = [v.code for v in report.violations]
    assert codes.index("CROSS_DOMAIN_SQL_IMPORT") < \
        codes.index("MODULE_DEPS_SOURCE_UNINSPECTABLE"), codes

    # Both files were actually inspected, and `checked` stays the stable sorted list.
    assert "membership/service.py" in report.checked, report.checked
    assert "membership/assemble.sql" in report.checked, report.checked
    assert report.checked == sorted(report.checked), report.checked


def test_f09_mixed_run_carries_the_identical_finding_the_fail_only_run_produces():
    """Non-vacuity control for the test above: the cross-domain violation surfaced by
    the mixed run must be the *same* `Violation` the identical tree without the
    uninspectable file reports — same code, subject and detail. This is what
    distinguishes a genuinely preserved finding from a newly-synthesised summary row
    that merely happens to carry the right code."""
    mixed = _f09_run({"service.py": _F09_CROSS_DOMAIN_PY,
                      "assemble.sql": _F09_UNINSPECTABLE_SQL})
    fail_only = _f09_run({"service.py": _F09_CROSS_DOMAIN_PY})
    mixed_cross = [v for v in mixed.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    fail_cross = [v for v in fail_only.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    assert mixed_cross == fail_cross, (mixed.render(), fail_only.render())


def test_f09_fail_class_only_run_stays_fail_at_exit_1():
    """Control 1: the FAIL path must not be dragged to ERROR/2 by the partitioning
    change. A real cross-domain import with nothing uninspectable is still FAIL at
    exit 1, carries no ERROR-class code, and gets no partition note (that note belongs
    only to the ERROR return)."""
    report = _f09_run({"service.py": _F09_CROSS_DOMAIN_PY})
    assert report.status == FAIL, report.render()
    assert report.exit_code == 1, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    assert not any("ADR-011 D7.2 partitioned report" in n for n in report.notes), report.render()


def test_f09_uninspectable_only_run_stays_error_at_exit_2_and_says_zero_fail_class():
    """Control 2: the single-cause ERROR path is unchanged in status, exit code and
    codes — and its partition note now states `0 FAIL-class violation(s)` explicitly,
    which is what lets a reader tell "none were found" apart from R1-F09's old
    behaviour of finding some and then dropping them."""
    report = _f09_run({"assemble.sql": _F09_UNINSPECTABLE_SQL})
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_SOURCE_UNINSPECTABLE"}, report.render()
    note = _f09_partition_note(report)
    assert "0 FAIL-class violation(s) [none]" in note, note
    assert "1 ERROR-class finding(s) [MODULE_DEPS_SOURCE_UNINSPECTABLE]" in note, note


def test_f09_mixed_run_partition_note_counts_both_sides_and_warns_about_exit_2():
    """The note is the part that stops exit 2 from being read as "no cross-domain
    violation": it must count both partitions, name both codes, and say in so many
    words that the FAIL-class list is a lower bound because the scan did not
    complete."""
    report = _f09_run({"service.py": _F09_CROSS_DOMAIN_PY,
                       "assemble.sql": _F09_UNINSPECTABLE_SQL})
    note = _f09_partition_note(report)
    assert "1 FAIL-class violation(s) [CROSS_DOMAIN_SQL_IMPORT]" in note, note
    assert "1 ERROR-class finding(s) [MODULE_DEPS_SOURCE_UNINSPECTABLE]" in note, note
    assert "lower bound" in note, note
    assert "does not mean zero FAIL-class violations were found" in note, note


def test_f09_mixed_run_names_both_findings_on_both_cli_surfaces():
    """D7.2 asks for both findings on *both* surfaces. Driven through `main` so the
    text renderer and the `--json` serialiser are each exercised for real, and so the
    process-level exit code is asserted rather than inferred from the report object.

    Also the no-false-PASS assertion: `PASS` must appear nowhere in either surface."""
    def write_tree(root: Path):
        modules_dir = _md_tree(root)
        _md_module(modules_dir, "membership", {"service.py": _F09_CROSS_DOMAIN_PY,
                                               "assemble.sql": _F09_UNINSPECTABLE_SQL})
        _f09_billing(modules_dir)
        manifest_path = root / "module-manifest.json"
        _md_write_manifest(modules_dir, manifest_path, _F09_MODULES)
        return ["--gate", "module-deps", "--modules-dir", str(modules_dir),
                "--module-manifest", str(manifest_path)]

    with tempfile.TemporaryDirectory() as tmp:
        code, out = _cli(write_tree(Path(tmp)))
    assert code == 2, out
    assert "[module-deps] ERROR" in out, out
    assert "CROSS_DOMAIN_SQL_IMPORT" in out, out
    assert "MODULE_DEPS_SOURCE_UNINSPECTABLE" in out, out
    assert "ADR-011 D7.2 partitioned report" in out, out
    assert PASS not in out, out
    assert "MODULE_DEPS_GATE_INTERNAL_ERROR" not in out, out

    with tempfile.TemporaryDirectory() as tmp:  # a fresh tree: `_md_tree` creates `app/`
        json_code, json_out = _cli(write_tree(Path(tmp)) + ["--json"])
    assert json_code == 2, json_out
    payload = json.loads(json_out)
    assert payload["status"] == ERROR, payload
    codes = [v["code"] for v in payload["violations"]]
    assert codes.count("CROSS_DOMAIN_SQL_IMPORT") == 1, payload
    assert codes.count("MODULE_DEPS_SOURCE_UNINSPECTABLE") == 1, payload
    assert codes.index("CROSS_DOMAIN_SQL_IMPORT") < \
        codes.index("MODULE_DEPS_SOURCE_UNINSPECTABLE"), codes
    assert any("ADR-011 D7.2 partitioned report" in n for n in payload["notes"]), payload
    assert "membership/service.py" in payload["checked"], payload
    assert "membership/assemble.sql" in payload["checked"], payload


def test_f09_mixed_run_with_an_sql_sourced_cross_domain_finding_also_survives():
    """The same suppression applied to a FAIL-class finding produced by the SQL
    scanner itself, not only by the Python import walk — both land in the one
    `violations` list, so both were dropped by the pre-fix ERROR return. Two distinct
    cross-domain findings are expected here (the import and the SQL table reference),
    and the uninspectable file must not reduce that count."""
    report = _f09_run({
        "service.py": _F09_CROSS_DOMAIN_PY,
        "reporting.sql": "SELECT total FROM billing_invoice WHERE paid = true\n",
        "assemble.sql": _F09_UNINSPECTABLE_SQL,
    })
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    assert len(cross) == 2, report.render()
    assert any("reporting.sql" in v.detail for v in cross), report.render()
    assert any("service.py" in v.detail for v in cross), report.render()
    assert "2 FAIL-class violation(s)" in _f09_partition_note(report), report.render()


def test_f09_partitioning_did_not_wire_cte_state_3_into_live_scanning():
    """Guard on the adjacent prohibition this increment must not disturb: ADR-011
    D3.2 state 3 (CTE-local names) is still NOT collected by the live scan, so a
    WITH-bound name used in table position remains an unattributed ERROR rather than
    silently becoming clean. Asserted here because the D7.2 change touches the very
    return that carries `unattributed`, and a quiet widening of what reaches it would
    otherwise look like an improvement."""
    report = _f09_run({
        "cte.sql": "WITH scratch AS (SELECT 1) SELECT * FROM scratch\n",
    })
    assert report.status == ERROR, report.render()
    assert "MODULE_DEPS_TABLE_UNATTRIBUTED" in report.codes(), report.render()


# --- R1-F10 (GATE2-R1-F10-D64-DOCSTRING-EXCLUSION-2026-10-05): ADR-011 D6.4 -------
#
# R1-F10's shape: ordinary English prose in a docstring could be a permanent FAIL
# CROSS_DOMAIN_SQL_IMPORT. `_F10_PROSE` below is a real sentence an author would
# plausibly write, and it is exactly the input that reproduced the false FAIL against
# the pre-fix code -- a trigger verb (`select`), a table-position keyword (`from`) and
# an identifier `billing` owns, all in one clause.
#
# Every negative test below (docstring => no CROSS_DOMAIN) is paired with a positive
# control that puts the SAME BYTES in an executable position in the same file and
# requires a FAIL. Without those controls a "no violation" assertion would also pass
# against a scanner that had simply stopped working, or against prose that was never
# SQL-ish in the first place; with them, the two outcomes differ only in the string's
# AST position, which is the one thing D6.4 is allowed to key on.

import ast as _f10_ast

try:
    from validate_architecture_gates import _d64_docstring_note, _docstring_constant_ids
except ImportError:
    pass

_F10_MODULES = {
    "membership": _md_entry("MEM-01", ["membership_"], ["app.modules.membership.interface"]),
    "billing": _md_entry("BIL-02", ["billing_"], ["app.modules.billing.interface"]),
}

# The false-FAIL sentence itself. Used verbatim both as docstring text (must be
# excluded) and as executable literal text (must still be scanned).
_F10_PROSE = ("Never select data from billing_invoice directly; go through the billing "
              "public interface instead.")

# `_md_tree` + two `_md_module` calls contribute three docstring-only `__init__.py`
# files (`app/modules/__init__.py`, and one per module), all genuinely scanned. Every
# count assertion below is expressed relative to this baseline so it stays a real
# arithmetic check rather than a magic number.
_F10_SCAFFOLD_DOCSTRINGS = 3


def _f10_run(membership_files):
    def build(modules_dir):
        _md_module(modules_dir, "membership", membership_files)
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge(member):\n    return None\n",
        })

    return _md_run(_F10_MODULES, build)


def _f10_exclusion_note(report):
    notes = [n for n in report.notes if "ADR-011 D6.4 docstring exclusion" in n]
    assert len(notes) == 1, report.render()
    return notes[0]


def _f10_excluded_count(report):
    note = _f10_exclusion_note(report)
    head = "ADR-011 D6.4 docstring exclusion: "
    return int(note.split(head, 1)[1].split(" docstring position(s)", 1)[0])


def _f10_assert_docstring_is_clean(source, *, own_docstrings):
    """Shared assertion for the four docstring positions: the file passes, no
    cross-domain finding is reported anywhere, and the run says how many positions it
    withheld -- the file's own plus the scaffold's, counted exactly."""
    report = _f10_run({"service.py": source})
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    assert report.codes() == set(), report.render()
    assert "membership/service.py" in report.checked, report.checked
    assert _f10_excluded_count(report) == _F10_SCAFFOLD_DOCSTRINGS + own_docstrings, \
        report.render()
    return report


def test_f10_prose_in_a_module_docstring_is_not_a_false_cross_domain_fail():
    """The headline case: a module docstring whose prose happens to read as SQL."""
    _f10_assert_docstring_is_clean(
        f'"""Membership roster service.\n\n{_F10_PROSE}\n"""\n\n\ndef roster():\n'
        "    return []\n",
        own_docstrings=1,
    )


def test_f10_prose_in_a_class_docstring_is_not_a_false_cross_domain_fail():
    _f10_assert_docstring_is_clean(
        f'class Roster:\n    """Member roster.\n\n    {_F10_PROSE}\n    """\n\n'
        "    limit = 50\n",
        own_docstrings=1,
    )


def test_f10_prose_in_a_sync_function_docstring_is_not_a_false_cross_domain_fail():
    _f10_assert_docstring_is_clean(
        f'def roster():\n    """List the member roster.\n\n    {_F10_PROSE}\n    """\n'
        "    return []\n",
        own_docstrings=1,
    )


def test_f10_prose_in_an_async_function_docstring_is_not_a_false_cross_domain_fail():
    """`AsyncFunctionDef` is a distinct AST node from `FunctionDef`, so an exclusion
    written against only the sync node would leave every `async def` docstring still
    false-FAILing. Pinned separately for exactly that reason."""
    _f10_assert_docstring_is_clean(
        f'async def roster():\n    """List the member roster.\n\n    {_F10_PROSE}\n'
        '    """\n    return []\n',
        own_docstrings=1,
    )


def test_f10_nested_method_and_inner_function_docstrings_are_also_excluded():
    """D6.4's positions are structural, not top-level-only: a method inside a class and
    a function nested inside another function are both `body[0] Expr Constant` holders
    and both must be excluded. `ast.walk` reaches them; a hand-rolled top-level-only
    scan would not."""
    source = (
        f'"""Module.\n\n{_F10_PROSE}\n"""\n\n\n'
        f'class Roster:\n    """Class.\n\n    {_F10_PROSE}\n    """\n\n'
        f'    def rows(self):\n        """Method.\n\n        {_F10_PROSE}\n        """\n'
        f'        async def inner():\n            """Inner.\n\n            {_F10_PROSE}\n'
        '            """\n            return []\n\n'
        "        return inner\n"
    )
    _f10_assert_docstring_is_clean(source, own_docstrings=4)


def test_f10_identical_text_in_a_non_leading_string_statement_still_fails():
    """The non-vacuity control for every negative test above, and the identity-vs-value
    assertion: the function's `body[0]` docstring and its `body[1]` bare string
    statement hold BYTE-IDENTICAL text. Python binds only the first to `__doc__`, so
    only the first may be excluded -- an exclusion keyed on the string's *text* instead
    of its node identity would suppress both and silently lose a real finding.

    The fixture's byte-identity is asserted here rather than assumed: a docstring that
    merely *contains* the sentence (extra heading, indentation, trailing newline) has a
    different value, and a value-keyed implementation would survive against it. That
    exact drill was run -- a value-keyed mutant passes this test when the two literals
    differ by so much as leading whitespace."""
    source = (
        "def roster():\n"
        f'    "{_F10_PROSE}"\n'
        f'    "{_F10_PROSE}"\n'
        "    return []\n"
    )
    func = _f10_ast.parse(source).body[0]
    assert func.body[0].value.value == func.body[1].value.value, \
        "fixture must hold byte-identical text in both positions"

    report = _f10_run({"service.py": source})
    assert report.status == FAIL, report.render()
    assert report.exit_code == 1, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    assert len(cross) == 1, report.render()
    assert cross[0].subject == "membership -> billing", cross[0]
    assert "billing_invoice" in cross[0].detail, cross[0]
    # The surviving finding cites the executable statement's own line (3), never the
    # docstring's (2): the two positions are distinguished, not merged.
    assert cross[0].detail.startswith("membership/service.py:3:"), cross[0]
    # And the docstring position was still excluded and counted in the same run.
    assert _f10_excluded_count(report) == _F10_SCAFFOLD_DOCSTRINGS + 1, report.render()


def test_f10_identical_text_in_a_later_function_still_fails():
    """The cross-scope half of the same property: one function's docstring and a *second*
    function's executable literal hold byte-identical text. A value-keyed exclusion
    built per file would suppress the second function's real finding too, and unlike the
    test above this shape has no in-function ordering a reviewer could appeal to."""
    source = (
        "def documented():\n"
        f'    "{_F10_PROSE}"\n'
        "    return []\n\n\n"
        "def executes():\n"
        f'    return query("{_F10_PROSE}")\n'
    )
    report = _f10_run({"service.py": source})
    assert report.status == FAIL, report.render()
    assert report.exit_code == 1, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    assert len(cross) == 1, report.render()
    assert cross[0].detail.startswith("membership/service.py:7:"), cross[0]
    assert _f10_excluded_count(report) == _F10_SCAFFOLD_DOCSTRINGS + 1, report.render()


def test_f10_adjacent_executable_sql_in_an_excluded_docstrings_file_still_fails():
    """Exclusion is per-position, not per-file: a module docstring carrying the prose
    AND a real cross-domain query in the same file yields exactly one FAIL -- the
    query's. A file-level or module-level opt-out would lose it."""
    source = (
        f'"""Membership roster service.\n\n{_F10_PROSE}\n"""\n\n'
        'ROSTER_SQL = "SELECT total FROM billing_invoice WHERE paid = true"\n'
    )
    report = _f10_run({"service.py": source})
    assert report.status == FAIL, report.render()
    assert report.exit_code == 1, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    assert len(cross) == 1, report.render()
    assert "billing_invoice" in cross[0].detail, cross[0]
    assert cross[0].detail.startswith("membership/service.py:6:"), cross[0]


def test_f10_attribute_docstring_after_an_assignment_is_not_excluded():
    """PEP 258's attribute-"docstring" convention is a `body[1]` string statement that
    Python does not bind to `__doc__`. D6.4 excludes docstring positions, not strings
    that merely look documentary, so this one stays scanned."""
    source = f'LIMIT = 50\n"""{_F10_PROSE}"""\n'
    report = _f10_run({"service.py": source})
    assert report.status == FAIL, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    assert _f10_excluded_count(report) == _F10_SCAFFOLD_DOCSTRINGS, report.render()


def test_f10_fstring_in_docstring_position_is_still_uninspectable_error():
    """Fail-closed preserved on the shape that most resembles a docstring but is not
    one: an f-string in `body[0]` is a `JoinedStr`, never a `Constant`, so Python does
    not bind it to `__doc__` and D6.4 does not exclude it. It must still reach the
    dynamic-construct rule as MODULE_DEPS_SOURCE_UNINSPECTABLE at exit 2, not be
    quietly swallowed by the new exclusion."""
    source = f'f"""Roster for {{tenant}}. {_F10_PROSE}"""\n'
    report = _f10_run({"service.py": source})
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert "MODULE_DEPS_SOURCE_UNINSPECTABLE" in report.codes(), report.render()
    assert _f10_excluded_count(report) == _F10_SCAFFOLD_DOCSTRINGS, report.render()


def test_f10_sql_file_prose_is_not_excluded_by_the_docstring_rule():
    """D6.4 is a Python-AST-position rule. A `.sql` file has no docstring position, so
    the same bytes in a `.sql` file are still scanned and still FAIL -- the exclusion
    must not leak across source kinds."""
    report = _f10_run({"report.sql": _F10_PROSE + "\n"})
    assert report.status == FAIL, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    assert any("membership/report.sql" in v.detail for v in report.violations), report.render()


def test_f10_docstring_exclusion_does_not_suppress_a_cross_domain_python_import():
    """The import walk and the Constant walk share one `ast.walk` loop, so a change to
    the Constant branch could mask the other. A file that is nothing but an excluded
    docstring plus a real cross-domain import must still FAIL on the import."""
    source = (f'"""Membership roster service.\n\n{_F10_PROSE}\n"""\n'
              "from app.modules.billing.models import Invoice\n")

    def build(modules_dir):
        _md_module(modules_dir, "membership", {"service.py": source})
        _md_module(modules_dir, "billing", {"models.py": "class Invoice:\n    pass\n",
                                            "interface.py": "def p():\n    return None\n"})

    report = _md_run(_F10_MODULES, build)
    assert report.status == FAIL, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    assert any("import" in v.detail or "app.modules.billing.models" in v.detail
               for v in report.violations), report.render()


def test_f10_zero_exclusion_run_still_discloses_the_rule_and_its_residual():
    """The count/residual note is unconditional. A tree with no docstring anywhere must
    say `0 docstring position(s)` and label the count complete, so a reader can tell
    "nothing was excluded" apart from "something was excluded and not disclosed"."""
    def build(modules_dir):
        (modules_dir / "__init__.py").write_text("ROOT = 1\n")  # replace the scaffold's
        _md_module(modules_dir, "membership", {"__init__.py": "MEMBERSHIP = 1\n",
                                               "service.py": "LIMIT = 50\n"})
        _md_module(modules_dir, "billing", {"__init__.py": "BILLING = 1\n"})

    report = _md_run(_F10_MODULES, build)
    assert report.status == PASS, report.render()
    note = _f10_exclusion_note(report)
    assert "0 docstring position(s)" in note, note
    assert "the count is complete for this run" in note, note
    assert "NOT FINAL" not in note, note


def test_f10_exclusion_note_states_the_count_the_rule_and_the_doc_residual():
    """The disclosure's required content, asserted on the note itself: the exact
    excluded-position count, the structural definition of what was excluded, and the
    explicit residual that SQL reaching the database through `__doc__` is covered by
    nothing -- specifically NOT by the dynamic-construct rule."""
    report = _f10_assert_docstring_is_clean(
        f'"""Roster.\n\n{_F10_PROSE}\n"""\n', own_docstrings=1,
    )
    note = _f10_exclusion_note(report)
    assert f"{_F10_SCAFFOLD_DOCSTRINGS + 1} docstring position(s)" in note, note
    assert "module/class/function body[0] Expr Constant" in note, note
    # The residual is labelled as a residual and spelled out in full: a reader must be
    # able to see *what* is uncovered, not just that some caveat exists.
    assert ("RESIDUAL: a docstring is still a live runtime string reachable as "
            "`__doc__`") in note, note
    assert "through `__doc__` is now examined by nothing" in note, note
    assert "NOT covered by the dynamic-construct rule" in note, note
    assert "MODULE_DEPS_SOURCE_UNINSPECTABLE" in note, note
    assert "uncovered gap, not a fail-closed ERROR" in note, note
    assert "GATE2-R1-F10-D64-DOCSTRING-EXCLUSION-2026-10-05" in note, note
    # The preserved-scanning half of the claim is stated too, not just implied.
    assert "non-leading string statement" in note, note


def test_f10_exclusion_disclosure_reaches_both_cli_surfaces():
    """Driven through `main` so the text renderer and the `--json` serialiser are each
    exercised for real, and the process exit code is asserted rather than inferred.
    `GateReport.notes` feeds both, but that is the property under test, not an
    assumption to rely on."""
    def write_tree(root: Path):
        modules_dir = _md_tree(root)
        _md_module(modules_dir, "membership",
                   {"service.py": f'"""Roster.\n\n{_F10_PROSE}\n"""\n'})
        _md_module(modules_dir, "billing",
                   {"interface.py": "def preview_charge(member):\n    return None\n"})
        manifest_path = root / "module-manifest.json"
        _md_write_manifest(modules_dir, manifest_path, _F10_MODULES)
        return ["--gate", "module-deps", "--modules-dir", str(modules_dir),
                "--module-manifest", str(manifest_path)]

    expected = f"{_F10_SCAFFOLD_DOCSTRINGS + 1} docstring position(s)"
    with tempfile.TemporaryDirectory() as tmp:
        code, out = _cli(write_tree(Path(tmp)))
    assert code == 0, out
    assert "[module-deps] PASS" in out, out
    assert "ADR-011 D6.4 docstring exclusion" in out, out
    assert expected in out, out
    assert "__doc__" in out, out
    # The violation-line form specifically (`render` emits `CODE: subject - detail`);
    # the bare token also appears inside the disclosure note, by design.
    assert "CROSS_DOMAIN_SQL_IMPORT:" not in out, out

    with tempfile.TemporaryDirectory() as tmp:  # a fresh tree: `_md_tree` creates `app/`
        json_code, json_out = _cli(write_tree(Path(tmp)) + ["--json"])
    assert json_code == 0, json_out
    payload = json.loads(json_out)
    assert payload["status"] == PASS, payload
    assert payload["violations"] == [], payload
    disclosure = [n for n in payload["notes"] if "ADR-011 D6.4 docstring exclusion" in n]
    assert len(disclosure) == 1, payload
    assert expected in disclosure[0], disclosure
    assert "NOT covered by the dynamic-construct rule" in disclosure[0], disclosure


def test_f10_gate_input_error_path_still_carries_the_disclosure_as_a_lower_bound():
    """R1-F09's failure mode was a disclosure dropped specifically on an ERROR return.
    The D6.4 note must therefore survive the `GateInputError` path too -- and must mark
    its count NOT FINAL there, since that run never finished scanning.

    The label deliberately is not ADR-011 D5.5's PARTIAL/LOWER BOUND wording, which is
    reserved for the coverage disclosure's own different claim; that separation is
    asserted below and by
    `test_d5_absent_modules_dir_discloses_not_started_rather_than_nothing`."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        modules_dir = _md_tree(root)
        _md_module(modules_dir, "membership", {"service.py": "LIMIT = 50\n"})
        manifest_path = root / "module-manifest.json"
        _md_write_manifest(modules_dir, manifest_path, _F10_MODULES)
        # `billing` is declared but has no directory, which is only a note; an
        # undeclared *discovered* module is the GateInputError.
        (modules_dir / "payments").mkdir()
        (modules_dir / "payments" / "__init__.py").write_text('"""payments."""\n')
        report = run_module_deps_gate(modules_dir, manifest_path)
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, report.render()
    note = _f10_exclusion_note(report)
    assert "NOT FINAL" in note, note
    assert "aborted before the scan completed" in note, note
    assert "__doc__" in note, note
    # Kept out of the coverage disclosure's reserved vocabulary, in both directions.
    assert "LOWER BOUND" not in note, note
    assert "PARTIAL" not in note, note


def test_f10_docstring_constant_ids_keys_on_identity_not_on_text():
    """Direct unit test on the helper, pinning the property the integration tests can
    only observe indirectly: for a file whose docstring and whose later bare string
    statement are byte-identical, the returned set holds exactly the docstring node's
    `id()` and not the other's."""
    tree = _f10_ast.parse(
        f'def roster():\n    """{_F10_PROSE}"""\n    "{_F10_PROSE}"\n    return []\n'
    )
    func = tree.body[0]
    doc_node = func.body[0].value
    other_node = func.body[1].value
    assert doc_node.value == other_node.value, "fixture must use byte-identical text"
    ids = _docstring_constant_ids(tree)
    assert id(doc_node) in ids, ids
    assert id(other_node) not in ids, ids
    assert len(ids) == 1, ids


def test_f10_docstring_constant_ids_covers_the_four_positions_and_nothing_else():
    """The closed set, stated positively and negatively in one place: `Module`,
    `ClassDef`, `FunctionDef` and `AsyncFunctionDef` `body[0]` strings are collected;
    a bytes `body[0]`, an f-string `body[0]`, a non-leading string and a string in an
    expression position are not."""
    tree = _f10_ast.parse(
        '"""module doc"""\n'
        'class C:\n    """class doc"""\n\n'
        '    def m(self):\n        """method doc"""\n        return 1\n\n'
        'async def a():\n    """async doc"""\n    return 1\n\n'
        'def b():\n    b"""bytes first"""\n    return 1\n\n'
        'def c():\n    f"""fstring {x} first"""\n    return 1\n\n'
        'def d():\n    x = "expression position"\n    "non leading"\n    return x\n'
    )
    excluded = _docstring_constant_ids(tree)
    # Every `str` Constant in the file, partitioned by whether the helper excluded it.
    # Asserting on the *texts* rather than re-deriving the rule keeps this a check of
    # the outcome, not a second copy of the implementation.
    strings = [node for node in _f10_ast.walk(tree)
               if isinstance(node, _f10_ast.Constant) and isinstance(node.value, str)]
    withheld = sorted(n.value for n in strings if id(n) in excluded)
    scanned = sorted(n.value for n in strings if id(n) not in excluded)
    assert withheld == ["async doc", "class doc", "method doc", "module doc"], withheld
    # The f-string's two literal parts, the expression-position string and the
    # non-leading string all remain scanned.
    assert scanned == sorted([" first", "expression position", "fstring ",
                              "non leading"]), scanned
    # The `bytes` literal in `body[0]` is not a `str` Constant, so it is neither
    # withheld nor mistaken for a docstring -- Python does not bind it to `__doc__`.
    byte_nodes = [node for node in _f10_ast.walk(tree)
                  if isinstance(node, _f10_ast.Constant) and isinstance(node.value, bytes)]
    assert [n.value for n in byte_nodes] == [b"bytes first"], byte_nodes
    assert id(byte_nodes[0]) not in excluded, byte_nodes


def test_f10_d64_note_builder_labels_partial_and_complete_runs_differently():
    """The two labels must actually differ, so a partial count can never be read as a
    final figure (and vice versa), while the residual text is identical in both."""
    complete = _d64_docstring_note(7)
    partial = _d64_docstring_note(7, partial=True)
    assert "7 docstring position(s)" in complete and "7 docstring position(s)" in partial
    assert "the count is complete for this run" in complete, complete
    assert "NOT FINAL" not in complete, complete
    assert "NOT FINAL" in partial, partial
    assert "complete for this run" not in partial, partial
    assert "NOT covered by the dynamic-construct rule" in complete, complete
    assert "NOT covered by the dynamic-construct rule" in partial, partial
    # Neither label borrows the coverage disclosure's PARTIAL/LOWER BOUND vocabulary
    # (ADR-011 D5.5), which carries a different claim about a different pass.
    for note in (complete, partial):
        assert "LOWER BOUND" not in note, note
        assert "PARTIAL" not in note, note


def test_f10_exclusion_did_not_wire_cte_state_3_into_live_scanning():
    """Guard on the adjacent prohibition this increment must not disturb: ADR-011 D3.2
    state 3 (CTE-local names) is still NOT collected by the live scan, so a WITH-bound
    name in table position remains an unattributed ERROR rather than silently becoming
    clean. Asserted here because D6.4 touches the Constant branch that feeds
    `unattributed`, and a quiet widening would otherwise look like an improvement."""
    report = _f10_run({"cte.sql": "WITH scratch AS (SELECT 1) SELECT * FROM scratch\n"})
    assert report.status == ERROR, report.render()
    assert "MODULE_DEPS_TABLE_UNATTRIBUTED" in report.codes(), report.render()


def test_f10_exclusion_did_not_weaken_the_d63_backstop_for_executable_literals():
    """The other fail-closed behaviour that must survive: a non-docstring literal that
    implies a table position but yields no extractable identifier is still
    MODULE_DEPS_SOURCE_UNINSPECTABLE at exit 2."""
    report = _f10_run({"service.py": '"""Roster."""\n\nQ = "SELECT total FROM "\n'})
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert "MODULE_DEPS_SOURCE_UNINSPECTABLE" in report.codes(), report.render()


# --- R1-F11 (GATE2-R1-F11-D62-BYTES-SQL-2026-10-05): ADR-011 D6.2 bytes literals ---
#
# R1-F11's shape, in the reviewer's own words: `Q = b'SELECT a FROM bil_invoices'`
# came back clean, because the Constant branch tested `isinstance(node.value, str)`
# and a bytes literal fell off the end of the walk entirely. That is a false-clean
# verdict over an executable cross-domain query (psycopg accepts a `bytes` query
# string), which is the one direction this gate may never fail in.
#
# Every test below that asserts a bytes literal is CLEAN is paired with evidence from
# the same run that the literal was actually looked at -- the disclosure's
# decoded-and-scanned count -- so "no violation" can never be satisfied by a scanner
# that simply went back to skipping bytes.

import validate_architecture_gates as _f11_gates

_F11_MODULES = {
    "membership": _md_entry("MEM-01", ["mem_"], ["app.modules.membership.interface"]),
    "billing": _md_entry("BIL-02", ["bil_"], ["app.modules.billing.interface"]),
}

# The reviewer's reproducer payload, and its own-table twin. Held as bytes constants
# and rendered into fixture source through `repr` (see `_f11_bytes_source`), so the
# literal on disk and the bytes asserted about here cannot drift apart.
_F11_CROSS = b"SELECT a FROM bil_invoices"
_F11_OWN = b"SELECT a FROM mem_roster"
# Same statement with a trailing comment that is UTF-8 for `café` (two bytes for the
# accent) and, separately, latin-1 for the same word (one byte, invalid UTF-8).
_F11_UTF8 = b"SELECT a FROM bil_invoices -- caf\xc3\xa9"
_F11_LATIN1_ONLY = b"SELECT a FROM bil_invoices -- caf\xe9"


def _f11_bytes_source(payload, name="Q"):
    """Module source holding `payload` verbatim as a bytes literal, rendered through
    `repr` so the fixture written to disk is byte-for-byte the constant above -- the
    source stays pure ASCII (`repr` escapes every non-ASCII byte as `\\xNN`), which is
    what keeps these fixtures clear of R1-F07's separate non-UTF-8-*file* rule.
    `name=None` emits a bare expression statement instead of an assignment."""
    return f"{payload!r}\n" if name is None else f"{name} = {payload!r}\n"


def _f11_run(membership_files):
    def build(modules_dir):
        _md_module(modules_dir, "membership", membership_files)
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge(member):\n    return None\n",
        })

    return _md_run(_F11_MODULES, build)


def _f11_bytes_note(report):
    notes = [n for n in report.notes if "ADR-011 D6.2 bytes-literal SQL scan" in n]
    assert len(notes) == 1, report.render()
    return notes[0]


def _f11_counts(report):
    """`(decoded_and_scanned, undecodable)` parsed out of the disclosure note."""
    tail = _f11_bytes_note(report).split("ADR-011 D6.2 bytes-literal SQL scan: ", 1)[1]
    scanned = int(tail.split(" bytes literal(s) decoded and scanned", 1)[0])
    undecodable = int(tail.split("scanned, ", 1)[1].split(" undecodable", 1)[0])
    return scanned, undecodable


def test_f11_fixture_source_rendering_round_trips_the_exact_payload_bytes():
    """`_f11_bytes_source` is load-bearing for every fixture below, so its round trip
    is pinned first: the rendered source is pure ASCII (no non-UTF-8 *file*, which
    would trip R1-F07's unrelated rule instead) and its AST holds the payload bytes
    unchanged. Without this, a fixture could silently test a different byte string
    than the one the assertions name."""
    for payload in (_F11_CROSS, _F11_OWN, _F11_UTF8, _F11_LATIN1_ONLY):
        source = _f11_bytes_source(payload)
        source.encode("ascii")  # raises if the rendering leaked a raw non-ASCII byte
        node = _f10_ast.parse(source).body[0].value
        assert isinstance(node, _f10_ast.Constant), source
        assert node.value == payload, (node.value, payload)
    bare = _f11_bytes_source(_F11_CROSS, name=None)
    assert _f10_ast.parse(bare).body[0].value.value == _F11_CROSS, bare


def test_f11_cross_domain_sql_in_a_bytes_literal_is_no_longer_clean():
    """The headline case, the reviewer's exact reproducer: `Q = b'SELECT a FROM
    bil_invoices'` inside `membership` must be a FAIL CROSS_DOMAIN_SQL_IMPORT citing
    the literal's own line and the table `billing` owns -- not a clean verdict."""
    report = _f11_run({"service.py": _f11_bytes_source(_F11_CROSS)})
    assert report.status == FAIL, report.render()
    assert report.exit_code == 1, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    assert len(cross) == 1, report.render()
    assert cross[0].subject == "membership -> billing", cross[0]
    assert "bil_invoices" in cross[0].detail, cross[0]
    assert cross[0].detail.startswith("membership/service.py:1:"), cross[0]
    assert _f11_counts(report) == (1, 0), report.render()


def test_f11_own_table_bytes_literal_is_clean_and_demonstrably_scanned():
    """The own-table positive control. `b'SELECT a FROM mem_roster'` in `membership`
    is state 1 (owned by the importer) and must stay clean -- so the denial above
    comes from attribution, not from a blanket "a bytes literal is a violation".

    The disclosure's count is what makes this a real control rather than a restatement
    of the old skip: the run says it decoded and scanned exactly one bytes literal and
    still found nothing, which a scanner that had gone back to ignoring bytes could
    not report."""
    report = _f11_run({"service.py": _f11_bytes_source(_F11_OWN)})
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    assert report.codes() == set(), report.render()
    assert "membership/service.py" in report.checked, report.checked
    assert _f11_counts(report) == (1, 0), report.render()


def test_f11_bytes_and_str_literals_with_the_same_text_reach_the_same_verdict():
    """D6.2's actual claim: the bytes literal is decoded and fed to the *existing*
    scanner, so it cannot acquire its own parallel semantics. The same statement as
    `str` and as `bytes`, at the same line of two otherwise-identical trees, must
    yield the same code, the same subject and the same identifier."""
    text = _F11_CROSS.decode("utf-8")
    as_str = _f11_run({"service.py": f"Q = {text!r}\n"})
    as_bytes = _f11_run({"service.py": _f11_bytes_source(_F11_CROSS)})
    assert as_str.status == as_bytes.status == FAIL, (as_str.render(), as_bytes.render())
    assert as_str.codes() == as_bytes.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, \
        (as_str.render(), as_bytes.render())
    assert [(v.code, v.subject, v.detail) for v in as_str.violations] == \
        [(v.code, v.subject, v.detail) for v in as_bytes.violations], \
        (as_str.render(), as_bytes.render())
    # And only the bytes run reports a decoded literal, so the two really did travel
    # the two different branches rather than both landing on the `str` one.
    assert _f11_counts(as_str) == (0, 0), as_str.render()
    assert _f11_counts(as_bytes) == (1, 0), as_bytes.render()


def test_f11_utf8_bytes_literal_is_decoded_and_scanned():
    """A UTF-8 bytes literal decodes on the first codec. The fixture's accent is
    asserted to be genuine multi-byte UTF-8 whose latin-1 reading differs, so this is
    a real UTF-8 case rather than ASCII in disguise."""
    assert _F11_UTF8.decode("utf-8") != _F11_UTF8.decode("latin-1"), _F11_UTF8
    report = _f11_run({"service.py": _f11_bytes_source(_F11_UTF8)})
    assert report.status == FAIL, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    assert len(report.violations) == 1, report.render()
    assert "bil_invoices" in report.violations[0].detail, report.violations
    assert _f11_counts(report) == (1, 0), report.render()


def test_f11_latin1_only_bytes_literal_is_decoded_by_the_fallback_and_scanned():
    """The fallback's reason for existing: a byte sequence UTF-8 genuinely rejects
    (asserted here, not assumed) must still be decoded and scanned rather than
    dropped. Without the latin-1 second pass this literal would be undecodable and
    the run would be ERROR at exit 2; with it, the real cross-domain finding is
    reported."""
    try:
        _F11_LATIN1_ONLY.decode("utf-8")
    except UnicodeDecodeError:
        pass
    else:
        raise AssertionError("fixture must be undecodable as UTF-8 to test the fallback")

    report = _f11_run({"service.py": _f11_bytes_source(_F11_LATIN1_ONLY)})
    assert report.status == FAIL, report.render()
    assert report.exit_code == 1, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    assert len(report.violations) == 1, report.render()
    assert "bil_invoices" in report.violations[0].detail, report.violations
    assert _f11_counts(report) == (1, 0), report.render()


def test_f11_decode_prefers_utf8_and_falls_back_to_latin1_in_that_order():
    """Direct unit test on the helper, because the codec *order* is not observable
    end-to-end: this module's identifier lexer is ASCII-only, so a non-ASCII table
    name truncates to the same ASCII prefix under either reading. The order still
    matters -- it decides which characters an identifier is attributed from -- so it
    is pinned where it can be seen."""
    assert _f11_gates._BYTES_LITERAL_CODECS == ("utf-8", "latin-1"), \
        _f11_gates._BYTES_LITERAL_CODECS
    # Valid UTF-8 is read as UTF-8, never as the latin-1 mojibake of the same bytes.
    assert _f11_gates._decode_bytes_literal(_F11_UTF8) == _F11_UTF8.decode("utf-8")
    assert _f11_gates._decode_bytes_literal(_F11_UTF8) != _F11_UTF8.decode("latin-1")
    # Invalid UTF-8 falls through to latin-1 rather than returning None.
    assert _f11_gates._decode_bytes_literal(_F11_LATIN1_ONLY) == \
        _F11_LATIN1_ONLY.decode("latin-1")


def test_f11_latin1_fallback_is_total_over_every_byte_value():
    """Why the `None` branch is defensive rather than reachable: latin-1 maps all 256
    byte values, so with the pinned codec pair no `bytes` literal can be undecodable.
    Asserted over the whole byte range -- this is the fact that justifies not writing
    a fabricated "latin-1 rejected this" fixture anywhere in this section."""
    for value in range(256):
        assert _f11_gates._decode_bytes_literal(bytes([value])) is not None, value
    assert _f11_gates._decode_bytes_literal(bytes(range(256))) is not None
    assert _f11_gates._decode_bytes_literal(b"") == ""


def test_f11_undecodable_bytes_literal_is_uninspectable_error_not_a_silent_skip():
    """The D7 error path, exercised through a codec that *genuinely* rejects the input
    rather than by pretending latin-1 can: `_BYTES_LITERAL_CODECS` is narrowed to
    `("ascii",)` for the duration, which is the same substitution a future round would
    make for real if it narrowed the contract. The payload is unchanged, so the
    difference between this run and the one below is only whether the literal could be
    decoded.

    Undecodable must mean MODULE_DEPS_SOURCE_UNINSPECTABLE at exit 2 (D7.1 -- reducing
    it to statements/tokens was impossible), never a skipped literal, which is exactly
    the shape R1-F11 reported."""
    payload = _F11_CROSS + b"\xff"
    source = _f11_bytes_source(payload)
    try:
        payload.decode("ascii")
    except UnicodeDecodeError:
        pass
    else:
        raise AssertionError("payload must be undecodable as ASCII for this test")

    original = _f11_gates._BYTES_LITERAL_CODECS
    try:
        _f11_gates._BYTES_LITERAL_CODECS = ("ascii",)
        narrowed = _f11_run({"service.py": source})
    finally:
        _f11_gates._BYTES_LITERAL_CODECS = original
    assert narrowed.status == ERROR, narrowed.render()
    assert narrowed.exit_code == 2, narrowed.render()
    assert "MODULE_DEPS_SOURCE_UNINSPECTABLE" in narrowed.codes(), narrowed.render()
    uninspectable = [v for v in narrowed.violations
                     if v.code == "MODULE_DEPS_SOURCE_UNINSPECTABLE"]
    assert len(uninspectable) == 1, narrowed.render()
    assert uninspectable[0].subject == "membership/service.py:1", uninspectable[0]
    assert "could not be decoded" in uninspectable[0].detail, uninspectable[0]
    assert "['ascii']" in uninspectable[0].detail, uninspectable[0]
    assert "ADR-011 D6.2" in uninspectable[0].detail, uninspectable[0]
    assert _f11_counts(narrowed) == (0, 1), narrowed.render()

    # The control: with the real codec pair the very same payload is decodable, so the
    # ERROR above is attributable to the decode failure and nothing else -- and the
    # restored constant is confirmed to be back in place.
    assert _f11_gates._BYTES_LITERAL_CODECS == ("utf-8", "latin-1"), \
        _f11_gates._BYTES_LITERAL_CODECS
    restored = _f11_run({"service.py": source})
    assert restored.status == FAIL, restored.render()
    assert restored.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, restored.render()
    assert _f11_counts(restored) == (1, 0), restored.render()


def test_f11_bytes_literal_in_docstring_position_is_scanned_not_excluded():
    """D6.4's exclusion must not follow the scan into bytes. A bytes literal as a
    module's `body[0]` expression statement looks like a docstring and is not one --
    Python binds only a `str` `body[0]` to `__doc__` -- so it is executable text and
    must still FAIL. The D6.4 count in the same run proves it was not quietly folded
    into the docstring bucket: it stays at the scaffold baseline."""
    report = _f11_run({"service.py": _f11_bytes_source(_F11_CROSS, name=None)})
    assert report.status == FAIL, report.render()
    assert report.exit_code == 1, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    assert len(report.violations) == 1, report.render()
    assert "bil_invoices" in report.violations[0].detail, report.violations
    # `_f11_run` builds the same three-docstring scaffold `_f10_run` does.
    assert _f10_excluded_count(report) == _F10_SCAFFOLD_DOCSTRINGS, report.render()
    assert _f11_counts(report) == (1, 0), report.render()


def test_f11_non_sql_binary_payload_is_scanned_and_stays_clean():
    """Scanning bytes must not mean flagging bytes: an arbitrary binary payload with
    no trigger verb is decoded, scanned and found clean. This is also the robustness
    check on feeding non-text through the SQL scanner -- control bytes and all -- which
    must neither raise nor manufacture a finding."""
    report = _f11_run({"service.py": _f11_bytes_source(b"\x89PNG\r\n\x1a\n\x00\x01\xff")})
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    assert report.codes() == set(), report.render()
    assert _f11_counts(report) == (1, 0), report.render()


def test_f11_bytes_scan_preserves_the_live_cte_state_3_prohibition():
    """The adjacent prohibition this increment must not disturb, now reachable through
    the new branch: ADR-011 D3.2 state 3 (CTE-local names) is still NOT collected by
    the live scan, so a WITH-bound name in table position inside a *bytes* literal is
    an unattributed ERROR, exactly as it is in a `str` literal. A bytes path that
    quietly treated CTE names as clean would look like an improvement."""
    report = _f11_run({
        "service.py": _f11_bytes_source(b"WITH scratch AS (SELECT 1) SELECT * FROM scratch"),
    })
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert "MODULE_DEPS_TABLE_UNATTRIBUTED" in report.codes(), report.render()
    assert _f11_counts(report) == (1, 0), report.render()


def test_f11_bytes_scan_preserves_the_d63_backstop_and_dangling_keyword_rule():
    """The other fail-closed behaviour that must hold on the new branch: a bytes
    literal whose table name is concatenated in at runtime is still
    MODULE_DEPS_SOURCE_UNINSPECTABLE at exit 2, not a clean decoded literal."""
    report = _f11_run({"service.py": _f11_bytes_source(b"SELECT total FROM ")})
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert "MODULE_DEPS_SOURCE_UNINSPECTABLE" in report.codes(), report.render()
    assert _f11_counts(report) == (1, 0), report.render()


def test_f11_runtime_assembled_bytes_sql_still_fails_closed():
    """The fail-open this increment could plausibly have opened: now that a bytes
    literal is scanned on its own, a bytes query *assembled* at runtime must not
    become a set of individually-clean fragments.

    Both shapes land at MODULE_DEPS_SOURCE_UNINSPECTABLE, exit 2 -- verified by direct
    execution. Worth pinning because of *which* rule catches them: it is the
    dangling-FROM rule firing on the decoded fragment, not `_uninspectable_for_node`,
    whose `BinOp`/`%` operand test is `str`-only and therefore never saw these. If a
    future round makes the dangling-keyword rule narrower, these two shapes are the
    ones that would silently go clean."""
    for label, source in (
        ("concatenation", 'Q = b"SELECT a FROM " + b"bil_invoices"\n'),
        ("percent format", 'Q = b"SELECT a FROM %s" % tbl\n'),
    ):
        report = _f11_run({"service.py": source})
        assert report.status == ERROR, (label, report.render())
        assert report.exit_code == 2, (label, report.render())
        assert "MODULE_DEPS_SOURCE_UNINSPECTABLE" in report.codes(), (label, report.render())
        assert "PASS" not in report.render(), (label, report.render())


def test_f11_bytes_decode_fallback_did_not_leak_into_f07_source_file_reading():
    """The confusion this increment most plausibly introduces: D6.2's latin-1 fallback
    is for a bytes *literal* inside a decoded source file, and must not become a
    second decode pass for the *file* read. R1-F07 / D7.3 keeps a non-UTF-8 `.py` or
    `.sql` file as MODULE_DEPS_GATE_INPUT_INVALID ERROR -- unusable input, never a
    silent re-decode -- and both halves are re-asserted here against this section's
    own manifest so the guard sits next to the change that threatens it."""
    def build_py(modules_dir):
        _md_module(modules_dir, "membership", {})
        (modules_dir / "membership" / "latin.py").write_bytes(_LATIN1_COOKIE_SOURCE)
        _md_module(modules_dir, "billing", {"interface.py": "def p():\n    return None\n"})

    def build_sql(modules_dir):
        _md_module(modules_dir, "membership", {})
        (modules_dir / "membership" / "reports.sql").write_bytes(_NON_UTF8_SQL_SOURCE)
        _md_module(modules_dir, "billing", {"interface.py": "def p():\n    return None\n"})

    for label, build in (("py", build_py), ("sql", build_sql)):
        report = _md_run(_F11_MODULES, build)
        assert report.status == ERROR, (label, report.render())
        assert report.exit_code == 2, (label, report.render())
        assert report.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, (label, report.render())
        assert "PASS" not in report.render(), (label, report.render())


def test_f11_zero_bytes_literal_run_still_discloses_the_rule_and_its_residual():
    """The counts/residual note is unconditional. A tree with no bytes literal must say
    `0 bytes literal(s)` and label the counts complete, so a reader can tell "there
    were none" apart from "there were some and the run did not say"."""
    report = _f11_run({"service.py": 'Q = "SELECT a FROM mem_roster"\n'})
    assert report.status == PASS, report.render()
    assert _f11_counts(report) == (0, 0), report.render()
    note = _f11_bytes_note(report)
    assert "0 bytes literal(s) decoded and scanned, 0 undecodable" in note, note
    assert "the counts are complete for this run" in note, note
    assert "NOT FINAL" not in note, note


def test_f11_bytes_note_states_the_counts_the_order_the_str_only_exclusion_and_residual():
    """The disclosure's required content, asserted on the note itself: the two counts,
    the codec order, that an undecodable literal is ERROR rather than skipped, that
    D6.4's exclusion is str-only, and the latin-1 residual spelled out as a residual
    whose over-approximation runs in the safe direction."""
    report = _f11_run({"service.py": _f11_bytes_source(_F11_OWN)})
    note = _f11_bytes_note(report)
    assert "1 bytes literal(s) decoded and scanned, 0 undecodable" in note, note
    assert "MODULE_DEPS_SOURCE_UNINSPECTABLE at exit 2 rather than skipped" in note, note
    assert "Decode order is UTF-8 then latin-1" in note, note
    assert "docstring exclusion is deliberately NOT extended to bytes" in note, note
    assert "Python binds only a str body[0] to __doc__" in note, note
    assert "RESIDUAL: latin-1 never rejects input" in note, note
    assert "attributed from different characters than the ones actually sent" in note, note
    assert "non-text binary payload is decoded and scanned" in note, note
    assert "never toward a clean verdict" in note, note
    assert "GATE2-R1-F11-D62-BYTES-SQL-2026-10-05" in note, note
    # The R1-F11 regression this closes is named, so the note explains its own reason.
    assert "b'SELECT a FROM bil_invoices'" in note, note
    assert "(R1-F11)" in note, note
    # And the coverage note stops claiming the scan is string-literal-only.
    assert any("covers bytes literals as well as str" in n for n in report.notes), \
        report.render()


def test_f11_bytes_disclosure_reaches_both_cli_surfaces():
    """Driven through `main` so the text renderer and the `--json` serialiser are each
    exercised for real, and the exit code is asserted rather than inferred."""
    def write_tree(root):
        modules_dir = _md_tree(root)
        _md_module(modules_dir, "membership",
                   {"service.py": _f11_bytes_source(_F11_OWN)})
        _md_module(modules_dir, "billing",
                   {"interface.py": "def preview_charge(member):\n    return None\n"})
        manifest_path = root / "module-manifest.json"
        _md_write_manifest(modules_dir, manifest_path, _F11_MODULES)
        return ["--gate", "module-deps", "--modules-dir", str(modules_dir),
                "--module-manifest", str(manifest_path)]

    expected = "1 bytes literal(s) decoded and scanned, 0 undecodable"
    with tempfile.TemporaryDirectory() as tmp:
        code, out = _cli(write_tree(Path(tmp)))
    assert code == 0, out
    assert "[module-deps] PASS" in out, out
    assert "ADR-011 D6.2 bytes-literal SQL scan" in out, out
    assert expected in out, out
    assert "Decode order is UTF-8 then latin-1" in out, out
    # The violation-line form specifically (`render` emits `CODE: subject - detail`);
    # the bare token also appears inside the disclosure note, by design.
    assert "CROSS_DOMAIN_SQL_IMPORT:" not in out, out

    with tempfile.TemporaryDirectory() as tmp:  # a fresh tree: `_md_tree` creates `app/`
        json_code, json_out = _cli(write_tree(Path(tmp)) + ["--json"])
    assert json_code == 0, json_out
    payload = json.loads(json_out)
    assert payload["status"] == PASS, payload
    assert payload["violations"] == [], payload
    disclosure = [n for n in payload["notes"] if "ADR-011 D6.2 bytes-literal SQL scan" in n]
    assert len(disclosure) == 1, payload
    assert expected in disclosure[0], disclosure
    assert "RESIDUAL: latin-1 never rejects input" in disclosure[0], disclosure


def test_f11_gate_input_error_path_carries_the_bytes_disclosure_as_not_final():
    """R1-F09's failure mode was a disclosure dropped specifically on an ERROR return,
    so the D6.2 note must survive the `GateInputError` path and mark its counts NOT
    FINAL there -- that run never finished scanning, so a bare `0` would be a
    fabricated total. The label stays clear of ADR-011 D5.5's PARTIAL/LOWER BOUND
    vocabulary, which carries the coverage pass's own different claim."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        modules_dir = _md_tree(root)
        _md_module(modules_dir, "membership", {"service.py": "LIMIT = 50\n"})
        manifest_path = root / "module-manifest.json"
        _md_write_manifest(modules_dir, manifest_path, _F11_MODULES)
        # An undeclared *discovered* module is the GateInputError.
        (modules_dir / "payments").mkdir()
        (modules_dir / "payments" / "__init__.py").write_text('"""payments."""\n')
        report = run_module_deps_gate(modules_dir, manifest_path)
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, report.render()
    note = _f11_bytes_note(report)
    assert "NOT FINAL" in note, note
    assert "aborted before the scan completed" in note, note
    assert "RESIDUAL: latin-1 never rejects input" in note, note
    assert "LOWER BOUND" not in note, note
    assert "PARTIAL" not in note, note


def test_f11_d62_note_builder_labels_partial_and_complete_runs_differently():
    """The two labels must actually differ, so partial counts can never be read as
    final figures (and vice versa), while the residual text is identical in both."""
    complete = _f11_gates._d62_bytes_note(4, 2)
    partial = _f11_gates._d62_bytes_note(4, 2, partial=True)
    for note in (complete, partial):
        assert "4 bytes literal(s) decoded and scanned, 2 undecodable" in note, note
        assert "RESIDUAL: latin-1 never rejects input" in note, note
        # Neither label borrows the coverage disclosure's reserved vocabulary.
        assert "LOWER BOUND" not in note, note
        assert "PARTIAL" not in note, note
    assert "the counts are complete for this run" in complete, complete
    assert "NOT FINAL" not in complete, complete
    assert "NOT FINAL" in partial, partial
    assert "complete for this run" not in partial, partial


# --- R1-F12 / ADR-011 D8 (GATE2-R1-F12-D8-SQL-TRIGGER-COUNTER-2026-10-05) ---------
#
# R1-F12's shape on this dimension: the module-deps clean verdict disclosed how many
# files it opened but never whether its SQL scanner recognised a single SQL statement,
# so a tree of trivial assignments and a tree of real own-table queries produced
# indistinguishable clean reports. ADR-011 D8 requires a clean verdict to self-evidence
# the ownership-relevant inspection it claims.
#
# Two properties are therefore asserted in opposition throughout, because either one
# alone is trivially satisfiable: a run over real SQL must report NONZERO (so the
# counter is not hardwired to 0), and a run over no SQL must report ZERO (so it is not
# hardwired to a positive number, nor inflatable by prose, docstrings, f-strings or
# string volume). A counter that cannot say "nothing was inspected" is not evidence.

import validate_architecture_gates as _f12_gates

_F12_MODULES = {
    # R1-F13 / ADR-011 D2: a declared interface must now resolve to a real file in its
    # own module. Every fixture in the F12 families creates `membership/service.py` and
    # `billing/interface.py`, so membership declares `service` rather than a
    # never-created `interface`. This is a *fixture correction*, not a relaxation: the
    # declaration now names the file the fixture actually builds, which is exactly what
    # the rule requires. Pointing it at the existing file rather than adding a new one
    # is deliberate -- it keeps the D8 file/docstring/subject counts these families
    # assert in opposition on the same scaffold they were calibrated against, instead of
    # re-deriving every figure around an extra file. No fixture imports membership's
    # declared interface across a module boundary (billing's is the import target
    # throughout), so no approval decision changes.
    "membership": _md_entry("MEM-01", ["mem_"], ["app.modules.membership.service"]),
    "billing": _md_entry("BIL-02", ["bil_"], ["app.modules.billing.interface"]),
}

# Own-table (clean) and cross-domain (FAIL) statements over the prefixes above. Held as
# constants so a fixture's text and the verdict asserted about it cannot drift apart.
_F12_OWN = "SELECT a FROM mem_roster"
_F12_CROSS = "SELECT a FROM bil_invoices"
# Prose carrying a trigger verb, a table-position keyword and an own-table identifier:
# scanned it would count, excluded it cannot. Own-table deliberately, so the docstring
# tests below turn on the *count* rather than on a verdict difference.
_F12_PROSE = "Never select data from mem_roster directly; use the public interface."


def _f12_run(membership_files):
    """`_f10_run`'s scaffold under the `mem_`/`bil_` prefixes: three docstring-only
    `__init__.py` files, a `billing/interface.py` holding no string literal at all, and
    whatever `membership_files` supplies. Nothing in the scaffold carries a trigger
    verb, so every nonzero count below is attributable to the fixture under test."""
    def build(modules_dir):
        _md_module(modules_dir, "membership", membership_files)
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge(member):\n    return None\n",
        })

    return _md_run(_F12_MODULES, build)


def _f12_trigger_note(report):
    notes = [n for n in report.notes if "ADR-011 D8 SQL-trigger inspection" in n]
    assert len(notes) == 1, report.render()
    return notes[0]


def _f12_count(report):
    """The recognised-subject count parsed out of the disclosure note itself, so every
    assertion below reads the number a human reader of the report would read."""
    tail = _f12_trigger_note(report).split("ADR-011 D8 SQL-trigger inspection: ", 1)[1]
    return int(tail.split(" text subject(s) recognised", 1)[0])


def test_f12_empty_scaffold_control_recognises_no_sql_statement():
    """The baseline every count below is measured against: the shared scaffold carries
    no trigger verb anywhere, so it must report exactly 0. Without this control a
    nonzero count elsewhere could be scaffold noise rather than the fixture's own SQL."""
    report = _f12_run({"service.py": "LIMIT = 50\n"})
    assert report.status == PASS, report.render()
    assert _f12_count(report) == 0, report.render()


def test_f12_own_table_sql_literal_is_counted_as_an_inspected_subject():
    """The positive control, and the increment's reason to exist: a clean verdict over a
    real own-table query must now evidence that the scanner recognised and examined it.
    The verdict is unchanged (still PASS, no violation) -- only the disclosure is new."""
    report = _f12_run({"service.py": f'Q = "{_F12_OWN}"\n'})
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    assert report.violations == [], report.render()
    assert _f12_count(report) == 1, report.render()


def test_f12_trivial_assignment_pass_reports_zero_not_an_equivalent_positive_proof():
    """The negative control that makes the positive one mean something: a clean verdict
    over `X = 1` must report 0, not the count a real query earns. The two runs' verdicts
    are identical -- PASS, exit 0, no violation -- so the count is the *only* thing
    distinguishing "inspected real SQL" from "inspected none", which is precisely the
    self-evidence ADR-011 D8 asks the report to carry."""
    trivial = _f12_run({"service.py": "X = 1\n"})
    positive = _f12_run({"service.py": f'Q = "{_F12_OWN}"\n'})
    for report in (trivial, positive):
        assert report.status == PASS, report.render()
        assert report.exit_code == 0, report.render()
        assert report.violations == [], report.render()
    assert _f12_count(trivial) == 0, trivial.render()
    assert _f12_count(positive) == 1, positive.render()
    # And the zero run says plainly that it evidences nothing, rather than letting a
    # reader take a clean verdict over no SQL as a clean verdict over SQL.
    note = _f12_trigger_note(trivial)
    assert "0 text subject(s) recognised as a SQL statement" in note, note
    assert "evidences nothing about table ownership" in note, note


def test_f12_count_is_tied_to_trigger_recognition_not_to_string_volume():
    """The inflation control. A file full of strings that carry no trigger verb -- in
    quantity, including one long enough to dwarf a real query -- must still report 0.
    A counter that rose with string volume would be satisfiable by prose and so worth
    nothing as evidence."""
    source = (
        'A = "hello world"\n'
        'B = "membership roster report"\n'
        'C = "' + ("filler text " * 40) + '"\n'
        "D = 1\n"
    )
    report = _f12_run({"service.py": source})
    assert report.status == PASS, report.render()
    assert _f12_count(report) == 0, report.render()


def test_f12_excluded_docstring_is_not_counted_while_its_executable_twin_is():
    """F10's D6.4 exclusion, preserved and now measurable. The identical sentence --
    trigger verb, table-position keyword, real owned identifier -- is withheld in
    docstring position and scanned in a non-leading string statement. The count must
    follow that split exactly: 0 against 1, with the docstring run's own D6.4 count
    confirming the position really was excluded rather than simply absent.

    This is also the honesty check on the exclusion: a docstring must never be reported
    as inspected SQL, since D6.4's residual is that nothing examines it."""
    docstring_run = _f12_run({"service.py": f'"""{_F12_PROSE}"""\n'})
    assert docstring_run.status == PASS, docstring_run.render()
    assert _f12_count(docstring_run) == 0, docstring_run.render()
    assert _f10_excluded_count(docstring_run) == _F10_SCAFFOLD_DOCSTRINGS + 1, \
        docstring_run.render()

    twin_run = _f12_run({"service.py": f'X = 1\n"""{_F12_PROSE}"""\n'})
    assert twin_run.status == PASS, twin_run.render()
    assert _f12_count(twin_run) == 1, twin_run.render()
    assert _f10_excluded_count(twin_run) == _F10_SCAFFOLD_DOCSTRINGS, twin_run.render()


def test_f12_sql_file_text_is_a_counted_subject():
    """A `.sql` file is a scanner subject in its own right -- one unit of text, not one
    per literal -- so a single own-table statement in one file counts once."""
    report = _f12_run({"service.py": "X = 1\n", "queries.sql": f"{_F12_OWN};\n"})
    assert report.status == PASS, report.render()
    assert _f12_count(report) == 1, report.render()


def test_f12_decoded_bytes_literal_counts_and_an_undecodable_one_does_not():
    """F11's D6.2 treatment, preserved in both directions. A decoded bytes literal runs
    through the same scanner, so it counts exactly as the byte-identical str literal
    does. An *undecodable* one never reaches the scanner at all -- it is reported as
    MODULE_DEPS_SOURCE_UNINSPECTABLE -- so it must contribute 0 here and be visible only
    through D6.2's own undecodable count. Counting it would claim inspection that
    provably did not happen."""
    decoded = _f12_run({"service.py": f'Q = {_F12_OWN.encode()!r}\n'})
    assert decoded.status == PASS, decoded.render()
    assert _f12_count(decoded) == 1, decoded.render()
    assert _f12_count(decoded) == _f12_count(_f12_run({"service.py": f'Q = "{_F12_OWN}"\n'})), \
        decoded.render()

    payload = _F12_OWN.encode() + b"\xff"
    source = f"Q = {payload!r}\n"
    original = _f12_gates._BYTES_LITERAL_CODECS
    try:
        _f12_gates._BYTES_LITERAL_CODECS = ("ascii",)
        narrowed = _f12_run({"service.py": source})
    finally:
        _f12_gates._BYTES_LITERAL_CODECS = original
    assert _f12_gates._BYTES_LITERAL_CODECS == ("utf-8", "latin-1"), \
        _f12_gates._BYTES_LITERAL_CODECS
    assert narrowed.status == ERROR, narrowed.render()
    assert "MODULE_DEPS_SOURCE_UNINSPECTABLE" in narrowed.codes(), narrowed.render()
    assert _f12_count(narrowed) == 0, narrowed.render()
    # Control: the same payload under the real codec pair *is* decodable, so the 0 above
    # is attributable to the decode failure and nothing else.
    restored = _f12_run({"service.py": source})
    assert _f12_count(restored) == 1, restored.render()


def test_f12_fstring_is_counted_only_where_a_literal_fragment_really_triggered():
    """The truthfulness boundary that the first draft of this disclosure got wrong. An
    f-string's own `JoinedStr` node is never handed to the scanner -- it is refused by
    the fail-closed dynamic-construct rule -- but `ast.walk` yields each of its literal
    *fragments* as an ordinary `str` Constant, so a fragment carrying a trigger verb is
    genuinely scanned and must be counted as such.

    Both directions are asserted, since the disclosure has to be accurate in each: a
    fragment that triggered is counted (it is the very subject that produced the
    dangling-keyword ERROR, so claiming 0 would deny an inspection that demonstrably
    happened), and an interpolated-verb f-string whose fragments carry no trigger verb
    at all is counted 0 even though the run still fails closed -- there, claiming 1
    would assert an inspection that never happened."""
    triggered = _f12_run({"service.py": 'T = "mem_roster"\nQ = f"SELECT a FROM {T}"\n'})
    assert triggered.status == ERROR, triggered.render()
    assert triggered.exit_code == 2, triggered.render()
    assert "MODULE_DEPS_SOURCE_UNINSPECTABLE" in triggered.codes(), triggered.render()
    # The fragment `"SELECT a FROM "` is what the dangling-keyword rule fired on, so it
    # was unambiguously examined -- exactly one subject, not the whole f-string.
    assert any("not followed by an identifier" in v.detail
               for v in triggered.violations), triggered.render()
    assert _f12_count(triggered) == 1, triggered.render()

    # `FROM` is a table-position keyword but not a trigger verb, so the single fragment
    # `" a FROM mem_roster"` is not SQL-ish and no literal in this file triggers at all;
    # the ERROR comes from F06's interpolated-verb branch instead. The verb arrives as a
    # parameter rather than a `"SELECT"` literal precisely because that literal would
    # itself be a triggering subject and would make the 0 below unachievable.
    interpolated = _f12_run({
        "service.py": 'def q(verb):\n    return f"{verb} a FROM mem_roster"\n',
    })
    assert interpolated.status == ERROR, interpolated.render()
    assert interpolated.exit_code == 2, interpolated.render()
    assert "MODULE_DEPS_SOURCE_UNINSPECTABLE" in interpolated.codes(), interpolated.render()
    assert _f12_count(interpolated) == 0, interpolated.render()


def test_f12_recognised_but_unresolvable_statements_still_count_as_inspected():
    """The boundary the counter's definition turns on: it tracks statement *recognition*,
    so a subject the scanner recognised and then could not resolve was still inspected
    and still counts. Both shapes are asserted -- a trigger verb with no table position
    at all (`SELECT 1`, cleared by the D6.3 I-1 backstop and clean) and a dangling
    table-position keyword (ERROR). Neither verdict is changed by this increment; only
    the disclosure is."""
    no_table = _f12_run({"service.py": 'Q = "SELECT 1"\n'})
    assert no_table.status == PASS, no_table.render()
    assert no_table.violations == [], no_table.render()
    assert _f12_count(no_table) == 1, no_table.render()

    dangling = _f12_run({"service.py": 'Q = "SELECT a FROM "\n'})
    assert dangling.status == ERROR, dangling.render()
    assert dangling.exit_code == 2, dangling.render()
    assert "MODULE_DEPS_SOURCE_UNINSPECTABLE" in dangling.codes(), dangling.render()
    assert _f12_count(dangling) == 1, dangling.render()


def test_f12_mixed_error_run_keeps_both_the_partition_and_the_trigger_disclosure():
    """F09's D7.2 mixed report, preserved. A run carrying a FAIL-class violation and an
    ERROR-class finding together must still partition them *and* still disclose the
    trigger count -- the scan completed, so the count is a real total, not a lower
    figure. Dropping a disclosure on an ERROR return is R1-F09's own failure mode."""
    report = _f12_run({
        "service.py": f'Q = "{_F12_CROSS}"\nT = "x"\nR = f"SELECT a FROM {{T}}"\n',
    })
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT",
                              "MODULE_DEPS_SOURCE_UNINSPECTABLE"}, report.render()
    assert any("ADR-011 D7.2 partitioned report" in n for n in report.notes), report.render()
    note = _f12_trigger_note(report)
    # Two subjects, both real: the cross-domain literal, and the f-string's own
    # `"SELECT a FROM "` fragment that the dangling-keyword rule fired on.
    assert _f12_count(report) == 2, report.render()
    assert "2 text subject(s) recognised as a SQL statement" in note, note
    assert "the count is complete for this run" in note, note
    assert "NOT FINAL" not in note, note
    assert "NOT STARTED" not in note, note


def test_f12_abort_during_the_scan_labels_the_count_not_final():
    """An abort *inside* the per-file scan: the count is whatever real inspection had
    already established, so it must be labelled NOT FINAL rather than read as a total.
    `membership/a_query.py` sorts before the unparseable `membership/z_broken.py`, so a
    genuine subject is counted before the abort -- a 0 here would not discriminate."""
    report = _f12_run({
        "a_query.py": f'Q = "{_F12_OWN}"\n',
        "z_broken.py": "def broken(:\n",
    })
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, report.render()
    assert _f12_count(report) == 1, report.render()
    note = _f12_trigger_note(report)
    assert "NOT FINAL" in note, note
    assert "aborted during the per-file scan" in note, note
    assert "a minimum established by real inspection, not a total" in note, note
    assert "complete for this run" not in note, note
    assert "NOT STARTED" not in note, note
    # D5.5's reserved coverage vocabulary is not borrowed for this different claim.
    assert "LOWER BOUND" not in note, note
    assert "PARTIAL" not in note, note


def test_f12_abort_before_the_scan_labels_the_count_not_started_not_a_clean_zero():
    """An abort *upstream* of the per-file scan (here an absent --modules-dir): nothing
    was ever handed to the scanner, so the 0 must record that no inspection happened
    rather than that no SQL-trigger text exists. Collapsing this into the NOT FINAL
    label would make the two aborts indistinguishable, and collapsing it into the
    complete label would state a total this run never established."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        manifest_path = root / "module-manifest.json"
        manifest_path.write_text(json.dumps(_md_manifest(_F12_MODULES)))
        report = run_module_deps_gate(root / "app" / "modules", manifest_path)
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, report.render()
    assert "PASS" not in report.render(), report.render()
    note = _f12_trigger_note(report)
    assert "NOT STARTED" in note, note
    assert "aborted before the per-file scan" in note, note
    assert "never that no SQL-trigger text exists" in note, note
    assert "NOT FINAL" not in note, note
    assert "complete for this run" not in note, note
    # The coverage pass's own NOT_STARTED/PARTIAL vocabulary stays unborrowed, so the
    # two disclosures remain tellable apart (and `test_d5_absent_modules_dir_...`'s
    # assertions over every note keep holding).
    assert "NOT_STARTED" not in note, note
    assert "PARTIAL" not in note, note
    assert "LOWER BOUND" not in note, note


def test_f12_trigger_disclosure_reaches_both_cli_surfaces():
    """Driven through `main` so the text renderer and the `--json` serialiser are each
    exercised for real, with the exit code asserted rather than inferred."""
    def write_tree(root):
        modules_dir = _md_tree(root)
        _md_module(modules_dir, "membership", {"service.py": f'Q = "{_F12_OWN}"\n'})
        _md_module(modules_dir, "billing",
                   {"interface.py": "def preview_charge(member):\n    return None\n"})
        manifest_path = root / "module-manifest.json"
        _md_write_manifest(modules_dir, manifest_path, _F12_MODULES)
        return ["--gate", "module-deps", "--modules-dir", str(modules_dir),
                "--module-manifest", str(manifest_path)]

    expected = "1 text subject(s) recognised as a SQL statement"
    with tempfile.TemporaryDirectory() as tmp:
        code, out = _cli(write_tree(Path(tmp)))
    assert code == 0, out
    assert "[module-deps] PASS" in out, out
    assert "ADR-011 D8 SQL-trigger inspection" in out, out
    assert expected in out, out
    assert "the count is complete for this run" in out, out

    with tempfile.TemporaryDirectory() as tmp:  # a fresh tree: `_md_tree` creates `app/`
        json_code, json_out = _cli(write_tree(Path(tmp)) + ["--json"])
    assert json_code == 0, json_out
    payload = json.loads(json_out)
    assert payload["status"] == PASS, payload
    assert payload["violations"] == [], payload
    disclosure = [n for n in payload["notes"] if "ADR-011 D8 SQL-trigger inspection" in n]
    assert len(disclosure) == 1, payload
    assert expected in disclosure[0], disclosure
    assert "RESIDUAL: this counts recognised statements, not table references" in \
        disclosure[0], disclosure


def test_f12_d8_note_builder_scopes_are_distinct_and_an_unknown_scope_fails_closed():
    """The three labels must actually differ, so a partial or never-started count can
    never be read as a total (and vice versa), while the count and the residual text are
    identical across all three. An unrecognised scope raises rather than silently
    falling back to the most reassuring label -- a future caller that mislabels a run
    must break loudly, not under-disclose."""
    complete = _f12_gates._d8_trigger_note(7)
    partial = _f12_gates._d8_trigger_note(7, _f12_gates._D8_SCOPE_PARTIAL)
    not_started = _f12_gates._d8_trigger_note(0, _f12_gates._D8_SCOPE_NOT_STARTED)
    for note in (complete, partial, not_started):
        assert "RESIDUAL: this counts recognised statements, not table references" in note, note
        assert "GATE2-R1-F12-D8-SQL-TRIGGER-COUNTER-2026-10-05" in note, note
        # None of the three borrows the coverage disclosure's reserved vocabulary.
        assert "LOWER BOUND" not in note, note
        assert "PARTIAL" not in note, note
        assert "NOT_STARTED" not in note, note
    assert "7 text subject(s)" in complete, complete
    assert "7 text subject(s)" in partial, partial
    assert "the count is complete for this run" in complete, complete
    assert "NOT FINAL" not in complete, complete
    assert "NOT STARTED" not in complete, complete
    assert "NOT FINAL" in partial, partial
    assert "NOT STARTED" not in partial, partial
    assert "NOT STARTED" in not_started, not_started
    assert "NOT FINAL" not in not_started, not_started
    for note in (partial, not_started):
        assert "complete for this run" not in note, note
    try:
        _f12_gates._d8_trigger_note(0, "whatever")
    except ValueError as exc:
        assert "unknown ADR-011 D8 trigger-note scope" in str(exc), exc
    else:
        raise AssertionError("an unknown scope must raise rather than mislabel the count")


def test_f12_counter_did_not_wire_cte_state_3_into_live_scanning():
    """Scope guard, as every increment in this file carries: counting recognised
    statements must not have quietly wired D3.2 state 3 (CTE-local names) into the live
    scanning path. A `WITH`-bound name in table position is still an unattributed ERROR
    -- while the new count confirms the subject really was scanned, so the ERROR cannot
    be mistaken for a subject that was skipped. The clean run below re-confirms the
    report still declares state-3 collection unimplemented (that contract note is only
    emitted on the clean path)."""
    report = _f12_run({
        "service.py": 'Q = "WITH recent AS (SELECT 1) SELECT a FROM recent"\n',
    })
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert "MODULE_DEPS_TABLE_UNATTRIBUTED" in report.codes(), report.render()
    assert _f12_count(report) == 1, report.render()

    clean = _f12_run({"service.py": f'Q = "{_F12_OWN}"\n'})
    assert clean.status == PASS, clean.render()
    assert any("remains unimplemented" in n for n in clean.notes), clean.render()


# --- R1-F12 / ADR-011 D8 + D3.2 (GATE2-R1-F12-D8-TABLE-STATE-COUNTERS-2026-10-05) --
#
# The second R1-F12/D8 dimension. The statement-trigger counter above closed "did the
# scanner recognise any SQL at all"; it explicitly did *not* close "did the ownership
# decision run, and over what" -- `SELECT 1` and a ten-identifier statement both report
# one recognised subject. ADR-011 D8 requires "table references by D3.2 state (own /
# other / CTE / system / declared external)" on every run, and D3.2 state 6
# (unattributed) alongside them.
#
# The same opposed-pair discipline as the trigger section: a fixture that really
# reaches a state must report that state NONZERO (so no field is hardwired to 0), and a
# run that reaches no state must report ZERO across the board (so no field is hardwired
# positive, and the zeros are usable as "nothing was attributed"). Two further
# properties are specific to this increment and asserted directly, because getting
# either wrong would make the disclosure a lie rather than merely thin:
#
#   * states 1 and 2 must not be collapsed -- an own-table reference must never land in
#     the other-module count or vice versa;
#   * the CTE (state 3) count must be a *genuine* zero. Live state-3 wiring is
#     FORBIDDEN by the qualified U1/U2 B HOLD, so the test below proves the zero is the
#     unwired path (by showing the pure helper would have resolved the very name the
#     live scan calls unattributed) and that the report says so, rather than connecting
#     the helper to make the field look exercised.

_F12B_MODULES = {
    "membership": {
        "domain": "MEM-01",
        "owned_table_prefixes": ["mem_"],
        "public_interfaces": ["app.modules.membership.interface"],
        # ADR-011 D3.5/state 5: a concrete identifier no module owns, so it is a
        # declaration rather than an allow-list over another module's table (which
        # parse_module_manifest rejects outright).
        "external_table_references": ["audit_log"],
    },
    "billing": _md_entry("BIL-02", ["bil_"], ["app.modules.billing.interface"]),
}

_F12B_OWN = "SELECT a FROM mem_roster"            # D3.2 state 1
_F12B_OTHER = "SELECT a FROM bil_invoices"        # D3.2 state 2 — FAIL
_F12B_SYSTEM = "SELECT a FROM pg_class"           # D3.2 state 4
_F12B_EXTERNAL = "SELECT a FROM audit_log"        # D3.2 state 5
_F12B_UNATTRIBUTED = "SELECT a FROM nobody_owns"  # D3.2 state 6 — ERROR
# D3.2 state 3's shape: `recent` is bound by the WITH at depth 0, so a wired state-3
# collector would attribute it CTE-local. The live path has no collector wired.
_F12B_CTE = "WITH recent AS (SELECT 1) SELECT a FROM recent"

_F12B_ZERO = {"own": 0, "other": 0, "cte": 0, "system": 0, "external": 0,
              "unattributed": 0}


def _f12b_run(membership_files):
    """`_f12_run`'s scaffold under a manifest that additionally declares one
    `external_table_references` entry, so D3.2 state 5 is reachable at all. Nothing in
    the scaffold carries a trigger verb, so every nonzero figure below is attributable
    to the fixture under test."""
    def build(modules_dir):
        _md_module(modules_dir, "membership", membership_files)
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge(member):\n    return None\n",
        })

    return _md_run(_F12B_MODULES, build)


def _f12b_ref_note(report):
    notes = [n for n in report.notes if "ADR-011 D8 table-reference attribution" in n]
    assert len(notes) == 1, report.render()
    return notes[0]


def _f12b_counts(report):
    """The six per-state figures parsed out of the disclosure note itself, so every
    assertion below reads the numbers a human reader of the report would read -- never a
    separately recomputed figure that could agree with the code while the report lies."""
    note = _f12b_ref_note(report)
    labels = {
        "own": "own (D3.2 state 1) ",
        "other": "another module's (state 2, FAIL CROSS_DOMAIN_SQL_IMPORT) ",
        "cte": "CTE-local (state 3) ",
        "system": "reserved-system (state 4) ",
        "external": "declared-external (state 5) ",
        "unattributed": "unattributed (state 6, ERROR MODULE_DEPS_TABLE_UNATTRIBUTED) ",
    }
    counts = {}
    for key, label in labels.items():
        assert label in note, (key, note)
        counts[key] = int(note.split(label, 1)[1].split(",", 1)[0].split(";", 1)[0].strip())
    return counts


def _f12b_total(report):
    note = _f12b_ref_note(report)
    tail = note.split("ADR-011 D8 table-reference attribution: ", 1)[1]
    return int(tail.split(" table-position identifier reference(s)", 1)[0])


def test_f12b_positive_own_table_fixture_reports_a_nonzero_own_count():
    """The increment's reason to exist, and the one property a hardwired-zero counter
    could not satisfy: a clean verdict over a real own-table query must now evidence
    that D3 attribution ran and reached state 1. The verdict itself is unchanged."""
    report = _f12b_run({"service.py": f'Q = "{_F12B_OWN}"\n'})
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    assert report.violations == [], report.render()
    counts = _f12b_counts(report)
    assert counts["own"] == 1, report.render()
    assert counts == {**_F12B_ZERO, "own": 1}, report.render()
    assert _f12b_total(report) == 1, report.render()


def test_f12b_trivial_pass_reports_all_zero_counts_not_an_equivalent_positive_proof():
    """The negative control that makes the positive one mean something. `X = 1` and a
    real own-table query produce identical verdicts -- PASS, exit 0, no violation -- so
    the per-state counts are the only thing distinguishing "attributed real references"
    from "attributed none", which is the self-evidence ADR-011 D8 asks for. A counter
    that cannot report zero is not evidence of anything."""
    trivial = _f12b_run({"service.py": "X = 1\n"})
    positive = _f12b_run({"service.py": f'Q = "{_F12B_OWN}"\n'})
    for report in (trivial, positive):
        assert report.status == PASS, report.render()
        assert report.exit_code == 0, report.render()
        assert report.violations == [], report.render()
    assert _f12b_counts(trivial) == _F12B_ZERO, trivial.render()
    assert _f12b_total(trivial) == 0, trivial.render()
    assert _f12b_counts(positive)["own"] == 1, positive.render()
    # And the zero run says plainly that it evidences nothing about ownership, rather
    # than letting a reader take a clean verdict over no reference as one over SQL.
    note = _f12b_ref_note(trivial)
    assert "0 table-position identifier reference(s)" in note, note
    assert "evidences nothing about table ownership" in note, note
    # ADR-011 D6.7.5: the completed-scan label is a lower bound, never a completeness
    # claim for this dimension (GATE2-R2-N01-D67-D8-LOWER-BOUND-TRUTHFULNESS-2026-10-06).
    assert "the per-file scan ran to completion" in note, note
    assert "these counts are a lower bound and NOT a total" in note, note
    assert "the counts are complete for this run" not in note, note


def test_f12b_cross_domain_reference_counts_as_other_and_never_as_own():
    """States 1 and 2 must stay separate. They share one internal outcome constant and
    are told apart only by comparing the resolved owner to the scanning module, so a
    collapse here would report another module's table as the scanning module's own --
    silently inverting the exact distinction the gate exists to make, while the FAIL
    still went out and made the report look healthy."""
    report = _f12b_run({"service.py": f'Q = "{_F12B_OTHER}"\n'})
    assert report.status == FAIL, report.render()
    assert report.exit_code == 1, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    assert _f12b_counts(report) == {**_F12B_ZERO, "other": 1}, report.render()
    # One violation, one counted state-2 reference: the disclosure and the violation
    # list are two views of the same decision and may not disagree.
    assert len(report.violations) == 1, report.render()


def test_f12b_reserved_system_identifier_counts_as_system_and_stays_clean():
    """D3.2 state 4, reachable live: a `pg_`-prefixed identifier is a reserved system
    reference, counted and disclosed, and clean. The count must not land in `own` --
    the reserved check runs before ownership resolution precisely so it cannot."""
    report = _f12b_run({"service.py": f'Q = "{_F12B_SYSTEM}"\n'})
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    assert report.violations == [], report.render()
    assert _f12b_counts(report) == {**_F12B_ZERO, "system": 1}, report.render()


def test_f12b_declared_external_reference_counts_as_external_and_stays_clean():
    """D3.2 state 5, reachable live: an `external_table_references` entry of the
    *importing* module is clean and counted. The control below is what makes the count
    meaningful -- the identical statement from a module that did not declare the entry
    is unattributed (state 6, ERROR), so state 5 is attributable to the declaration and
    not to the identifier merely being unowned."""
    report = _f12b_run({"service.py": f'Q = "{_F12B_EXTERNAL}"\n'})
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    assert report.violations == [], report.render()
    assert _f12b_counts(report) == {**_F12B_ZERO, "external": 1}, report.render()

    def build(modules_dir):
        _md_module(modules_dir, "membership", {"service.py": "X = 1\n"})
        # `billing` declares nothing external, so the same identifier is state 6 there.
        _md_module(modules_dir, "billing", {"queries.py": f'Q = "{_F12B_EXTERNAL}"\n'})

    undeclared = _md_run(_F12B_MODULES, build)
    assert undeclared.status == ERROR, undeclared.render()
    assert "MODULE_DEPS_TABLE_UNATTRIBUTED" in undeclared.codes(), undeclared.render()
    assert _f12b_counts(undeclared) == {**_F12B_ZERO, "unattributed": 1}, \
        undeclared.render()


def test_f12b_unattributed_reference_counts_as_unattributed_and_still_errors():
    """D3.2 state 6: counted *and* still ERROR at exit 2. Counting an unattributed
    reference must not have turned it back into the benign note D9 forbids, and the
    count must not be silently folded into any clean state."""
    report = _f12b_run({"service.py": f'Q = "{_F12B_UNATTRIBUTED}"\n'})
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_TABLE_UNATTRIBUTED"}, report.render()
    assert _f12b_counts(report) == {**_F12B_ZERO, "unattributed": 1}, report.render()
    assert _f12b_total(report) == 1, report.render()


def test_f12b_cte_state_3_count_is_a_genuine_unreachable_zero_and_says_so():
    """The HOLD-compliance test, and the one place a counter could most easily become a
    lie. Live state-3 wiring is FORBIDDEN, so the CTE field must read 0 -- but a 0 that
    reads as "no CTE-bound reference occurred" would be false, since this fixture
    contains exactly one.

    Three things are therefore asserted together: the live run counts the WITH-bound
    name as unattributed (state 6, ERROR) and the CTE field stays 0; the pure, unwired
    helper *does* resolve that very name, proving the zero is the unwired path rather
    than an absent input; and the report discloses the limit in those terms instead of
    presenting the zero as an observation."""
    report = _f12b_run({"service.py": f'Q = "{_F12B_CTE}"\n'})
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert "MODULE_DEPS_TABLE_UNATTRIBUTED" in report.codes(), report.render()
    counts = _f12b_counts(report)
    assert counts["cte"] == 0, report.render()
    assert counts["unattributed"] == 1, report.render()
    assert counts == {**_F12B_ZERO, "unattributed": 1}, report.render()
    # The subject really was scanned, so the state-6 outcome cannot be mistaken for a
    # subject the scanner skipped.
    assert _f12_count(report) == 1, report.render()

    # The pure helper would have bound `recent` -- so the zero above is attributable to
    # the deliberate non-wiring, not to the fixture failing to contain a CTE.
    assert "recent" in _f12_gates._collect_cte_names(_F12B_CTE), _F12B_CTE

    note = _f12b_ref_note(report)
    assert "LIMIT -- CTE-local (state 3) is structurally unreachable" in note, note
    assert "records an unimplemented path, NOT an observation that no CTE-bound " \
           "reference occurred" in note, note
    assert "deliberately unconnected helper" in note, note
    # And the clean path still declares state-3 collection unimplemented.
    clean = _f12b_run({"service.py": f'Q = "{_F12B_OWN}"\n'})
    assert clean.status == PASS, clean.render()
    assert any("remains unimplemented" in n for n in clean.notes), clean.render()


def test_f12b_counts_occurrences_not_distinct_names():
    """The definition the figures turn on: extracted identifier *occurrences*. Two
    references to one table are two, not one -- a deduplicating counter would understate
    how much was attributed, and the note states this explicitly so the number is not
    misread as a distinct-table figure."""
    report = _f12b_run({
        "service.py": 'Q = "SELECT a FROM mem_roster JOIN mem_roster ON true"\n',
    })
    assert report.status == PASS, report.render()
    assert _f12b_counts(report) == {**_F12B_ZERO, "own": 2}, report.render()
    assert _f12b_total(report) == 2, report.render()
    # One subject, two references: the two D8 notes measure different things and the
    # pair is what makes that legible.
    assert _f12_count(report) == 1, report.render()
    note = _f12b_ref_note(report)
    assert "not distinct table names and not statements" in note, note


def test_f12b_triggered_statement_with_no_table_position_has_zero_references():
    """`SELECT 1` is recognised, examined and clean -- and contributes zero references,
    which is the truthful figure. Claiming a reference here would fabricate an
    attribution that never happened; the trigger note's 1 is what records that the
    scanner did look."""
    report = _f12b_run({"service.py": 'Q = "SELECT 1"\n'})
    assert report.status == PASS, report.render()
    assert report.violations == [], report.render()
    assert _f12b_counts(report) == _F12B_ZERO, report.render()
    assert _f12b_total(report) == 0, report.render()
    assert _f12_count(report) == 1, report.render()


def test_f12b_recognised_but_unresolvable_subject_contributes_zero_references():
    """A dangling table-position keyword: the subject was recognised and examined, the
    run fails closed as MODULE_DEPS_SOURCE_UNINSPECTABLE, and no identifier was
    extracted -- so every per-state figure stays 0. Counting the unresolved position as
    any state would attribute a table nobody resolved."""
    report = _f12b_run({"service.py": 'Q = "SELECT a FROM "\n'})
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert "MODULE_DEPS_SOURCE_UNINSPECTABLE" in report.codes(), report.render()
    assert _f12b_counts(report) == _F12B_ZERO, report.render()
    assert _f12_count(report) == 1, report.render()
    note = _f12b_ref_note(report)
    assert "MODULE_DEPS_SOURCE_UNINSPECTABLE instead" in note, note


def test_f12b_withheld_and_undecodable_text_contributes_zero_references():
    """Text the scanner never received must not appear as attributed. D6.4's excluded
    docstring position carries a real owned identifier and still counts 0, while its
    byte-identical executable twin counts 1 -- so the 0 is the exclusion, not an absent
    identifier. An undecodable bytes literal likewise contributes 0 and is visible only
    through D6.2's own undecodable count."""
    docstring_run = _f12b_run({"service.py": f'"""{_F12_PROSE}"""\n'})
    assert docstring_run.status == PASS, docstring_run.render()
    assert _f12b_counts(docstring_run) == _F12B_ZERO, docstring_run.render()

    twin_run = _f12b_run({"service.py": f'X = 1\n"""{_F12_PROSE}"""\n'})
    assert twin_run.status == PASS, twin_run.render()
    assert _f12b_counts(twin_run) == {**_F12B_ZERO, "own": 1}, twin_run.render()

    payload = _F12B_OWN.encode() + b"\xff"
    source = f"Q = {payload!r}\n"
    original = _f12_gates._BYTES_LITERAL_CODECS
    try:
        _f12_gates._BYTES_LITERAL_CODECS = ("ascii",)
        narrowed = _f12b_run({"service.py": source})
    finally:
        _f12_gates._BYTES_LITERAL_CODECS = original
    assert _f12_gates._BYTES_LITERAL_CODECS == ("utf-8", "latin-1"), \
        _f12_gates._BYTES_LITERAL_CODECS
    assert narrowed.status == ERROR, narrowed.render()
    assert "MODULE_DEPS_SOURCE_UNINSPECTABLE" in narrowed.codes(), narrowed.render()
    assert _f12b_counts(narrowed) == _F12B_ZERO, narrowed.render()
    # Control: the same payload under the real codec pair *is* decoded and attributed,
    # so the zero above is attributable to the decode failure and nothing else.
    restored = _f12b_run({"service.py": source})
    assert _f12b_counts(restored) == {**_F12B_ZERO, "own": 1}, restored.render()


def test_f12b_one_run_reports_every_live_reachable_state_at_once():
    """All five live-reachable states in a single run, so no field can be satisfied only
    in isolation and no state can be absorbing another's references. The totals must
    reconcile: five statements, five subjects, five references, one per state, with CTE
    still 0."""
    report = _f12b_run({"service.py": "\n".join([
        f'Q1 = "{_F12B_OWN}"',
        f'Q2 = "{_F12B_OTHER}"',
        f'Q3 = "{_F12B_SYSTEM}"',
        f'Q4 = "{_F12B_EXTERNAL}"',
        f'Q5 = "{_F12B_UNATTRIBUTED}"',
        "",
    ])})
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT",
                              "MODULE_DEPS_TABLE_UNATTRIBUTED"}, report.render()
    assert _f12b_counts(report) == {"own": 1, "other": 1, "cte": 0, "system": 1,
                                    "external": 1, "unattributed": 1}, report.render()
    assert _f12b_total(report) == 5, report.render()
    assert _f12_count(report) == 5, report.render()
    note = _f12b_ref_note(report)
    assert "5 table-position identifier reference(s)" in note, note
    # ADR-011 D6.7.5: completed scan => lower bound, not "complete for this run".
    assert "the per-file scan ran to completion" in note, note
    assert "these counts are a lower bound and NOT a total" in note, note
    assert "the counts are complete for this run" not in note, note
    assert "NOT FINAL" not in note, note
    assert "NOT STARTED" not in note, note


def test_f12b_mixed_error_run_keeps_the_partition_and_both_d8_disclosures():
    """F09's D7.2 mixed report, preserved. A run carrying a FAIL-class violation and an
    ERROR-class finding together must still partition them and still carry *both* D8
    disclosures, with the scan having completed so the attribution figures go out under
    the completed-scan label -- which, per ADR-011 D6.7.5, is a disclosed lower bound
    and not a total. Dropping a disclosure on an ERROR return is R1-F09's own failure
    mode."""
    report = _f12b_run({
        "service.py": f'Q = "{_F12B_OTHER}"\nT = "x"\nR = f"SELECT a FROM {{T}}"\n',
    })
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT",
                              "MODULE_DEPS_SOURCE_UNINSPECTABLE"}, report.render()
    assert any("ADR-011 D7.2 partitioned report" in n for n in report.notes), report.render()
    assert any("ADR-011 D8 SQL-trigger inspection" in n for n in report.notes), report.render()
    # The cross-domain literal is the only extracted reference; the f-string fragment
    # `"SELECT a FROM "` triggered but yielded none.
    assert _f12b_counts(report) == {**_F12B_ZERO, "other": 1}, report.render()
    assert _f12_count(report) == 2, report.render()
    # ADR-011 D6.7.5: the scan completed, so the figures are a disclosed lower bound
    # rather than the old (false) completeness claim.
    _mixed_note = _f12b_ref_note(report)
    assert "the per-file scan ran to completion" in _mixed_note, _mixed_note
    assert "these counts are a lower bound and NOT a total" in _mixed_note, _mixed_note
    assert "the counts are complete for this run" not in _mixed_note, _mixed_note


def test_f12b_abort_during_the_scan_labels_the_counts_not_final():
    """An abort *inside* the per-file scan: the figures are whatever real attribution had
    established, so they must be labelled NOT FINAL rather than read as totals.
    `membership/a_query.py` sorts before the unparseable `membership/z_broken.py`, so a
    genuine own-table reference is attributed before the abort -- an all-zero count here
    would not discriminate between the two abort shapes."""
    report = _f12b_run({
        "a_query.py": f'Q = "{_F12B_OWN}"\n',
        "z_broken.py": "def broken(:\n",
    })
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, report.render()
    assert _f12b_counts(report) == {**_F12B_ZERO, "own": 1}, report.render()
    note = _f12b_ref_note(report)
    assert "NOT FINAL" in note, note
    assert "aborted during the per-file scan" in note, note
    assert "a minimum established by real attribution, not a total" in note, note
    assert "complete for this run" not in note, note
    assert "NOT STARTED" not in note, note
    # D5.5's reserved coverage vocabulary stays unborrowed for this different claim.
    assert "LOWER BOUND" not in note, note
    assert "PARTIAL" not in note, note


def test_f12b_abort_before_the_scan_labels_the_counts_not_started_not_a_clean_zero():
    """An abort *upstream* of the per-file scan (an absent --modules-dir): nothing was
    ever attributed, so the zeros must record that no attribution happened rather than
    that the tree holds no table reference. Collapsing this into NOT FINAL would make the
    two aborts indistinguishable; collapsing it into the complete label would state a
    total this run never established -- the fabricated-total shape D5.5 exists to
    prevent, reproduced one disclosure over."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        manifest_path = root / "module-manifest.json"
        manifest_path.write_text(json.dumps(_md_manifest(_F12B_MODULES)))
        report = run_module_deps_gate(root / "app" / "modules", manifest_path)
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, report.render()
    assert "PASS" not in report.render(), report.render()
    assert _f12b_counts(report) == _F12B_ZERO, report.render()
    note = _f12b_ref_note(report)
    assert "NOT STARTED" in note, note
    assert "aborted before the per-file scan" in note, note
    assert "never that the tree holds no table reference" in note, note
    assert "NOT FINAL" not in note, note
    assert "complete for this run" not in note, note
    # The coverage pass's own vocabulary stays unborrowed, so `test_d5_absent_modules_
    # dir_discloses_not_started_rather_than_nothing`'s assertions over every note hold.
    assert "NOT_STARTED" not in note, note
    assert "PARTIAL" not in note, note
    assert "LOWER BOUND" not in note, note


def test_f12b_attribution_disclosure_reaches_both_cli_surfaces():
    """Driven through `main` so the text renderer and the `--json` serialiser are each
    exercised for real, with the exit code asserted rather than inferred. A disclosure
    that existed only on one surface would leave the other able to show a clean verdict
    with no evidence behind it."""
    def write_tree(root):
        modules_dir = _md_tree(root)
        _md_module(modules_dir, "membership", {"service.py": f'Q = "{_F12B_OWN}"\n'})
        _md_module(modules_dir, "billing",
                   {"interface.py": "def preview_charge(member):\n    return None\n"})
        manifest_path = root / "module-manifest.json"
        _md_write_manifest(modules_dir, manifest_path, _F12B_MODULES)
        return ["--gate", "module-deps", "--modules-dir", str(modules_dir),
                "--module-manifest", str(manifest_path)]

    expected = "1 table-position identifier reference(s) extracted and attributed"
    with tempfile.TemporaryDirectory() as tmp:
        code, out = _cli(write_tree(Path(tmp)))
    assert code == 0, out
    assert "[module-deps] PASS" in out, out
    assert "ADR-011 D8 table-reference attribution" in out, out
    assert expected in out, out
    assert "own (D3.2 state 1) 1" in out, out
    assert "CTE-local (state 3) 0" in out, out
    # ADR-011 D6.7.5, asserted on the note itself rather than on the whole stdout: the
    # other D8 notes legitimately still say "the counts are complete for this run", so a
    # substring check over `out` would pass even if this dimension reasserted it.
    cli_note = [line for line in out.splitlines()
                if "ADR-011 D8 table-reference attribution" in line]
    assert len(cli_note) == 1, out
    assert "the per-file scan ran to completion" in cli_note[0], cli_note
    assert "these counts are a lower bound and NOT a total" in cli_note[0], cli_note
    assert "the counts are complete for this run" not in cli_note[0], cli_note

    with tempfile.TemporaryDirectory() as tmp:  # a fresh tree: `_md_tree` creates `app/`
        json_code, json_out = _cli(write_tree(Path(tmp)) + ["--json"])
    assert json_code == 0, json_out
    payload = json.loads(json_out)
    assert payload["status"] == PASS, payload
    assert payload["violations"] == [], payload
    disclosure = [n for n in payload["notes"]
                  if "ADR-011 D8 table-reference attribution" in n]
    assert len(disclosure) == 1, payload
    assert expected in disclosure[0], disclosure
    assert "own (D3.2 state 1) 1" in disclosure[0], disclosure
    assert "LIMIT -- CTE-local (state 3) is structurally unreachable" in disclosure[0], \
        disclosure
    assert "RESIDUAL: these are not totals of every table reference in the tree" in \
        disclosure[0], disclosure


def test_f12b_note_builder_scopes_are_distinct_and_an_unknown_scope_fails_closed():
    """The three labels must actually differ, so none of the three shortfalls this
    dimension can have is readable as either of the others, while the figures and the
    residual text stay identical across all three. Per ADR-011 D6.7.5 no label -- the
    completed-scan one included -- may call these figures complete; what distinguishes
    them is *which* shortfall they name. An unrecognised scope raises rather than
    falling back to the most reassuring label -- a future caller that mislabels a run
    must break loudly instead of under-disclosing."""
    counts = _f12_gates._TableRefCounts(own=3, other=2, system=1, external=1,
                                        unattributed=4)
    assert counts.total == 11, counts
    complete = _f12_gates._d8_table_ref_note(counts)
    partial = _f12_gates._d8_table_ref_note(counts, _f12_gates._D8_SCOPE_PARTIAL)
    not_started = _f12_gates._d8_table_ref_note(_f12_gates._TableRefCounts(),
                                                _f12_gates._D8_SCOPE_NOT_STARTED)
    for note in (complete, partial, not_started):
        assert "RESIDUAL: these are not totals of every table reference in the tree" in \
            note, note
        assert "LIMIT -- CTE-local (state 3) is structurally unreachable" in note, note
        assert "GATE2-R1-F12-D8-TABLE-STATE-COUNTERS-2026-10-05" in note, note
        # None of the three borrows the coverage disclosure's reserved vocabulary.
        assert "LOWER BOUND" not in note, note
        assert "PARTIAL" not in note, note
        assert "NOT_STARTED" not in note, note
    for note in (complete, partial):
        assert "11 table-position identifier reference(s)" in note, note
        assert "own (D3.2 state 1) 3" in note, note
        assert "unattributed (state 6, ERROR MODULE_DEPS_TABLE_UNATTRIBUTED) 4" in note, note
    # ADR-011 D6.7.5 (GATE2-R2-N01-D67-D8-LOWER-BOUND-TRUTHFULNESS-2026-10-06): the
    # completed-scan branch may no longer assert completeness for this dimension. It
    # discloses the figures as a lower bound, and says which proof is missing.
    assert "the per-file scan ran to completion" in complete, complete
    assert "these counts are a lower bound and NOT a total" in complete, complete
    assert "no explicit ADR-011 D6.7.2 position-totality proof" in complete, complete
    assert "a completed FILE scan is not a proved complete TABLE-REFERENCE inventory" \
        in complete, complete
    assert "NOT FINAL" not in complete, complete
    assert "NOT STARTED" not in complete, complete
    assert "NOT FINAL" in partial, partial
    assert "NOT STARTED" not in partial, partial
    assert "NOT STARTED" in not_started, not_started
    assert "NOT FINAL" not in not_started, not_started
    assert "0 table-position identifier reference(s)" in not_started, not_started
    # No scope may claim completeness for this dimension any more -- the completed-scan
    # branch included, which is the whole point of the correction.
    for note in (complete, partial, not_started):
        assert "the counts are complete for this run" not in note, note
        assert "complete for this run" not in note, note
    # And the three still mean three different things: a shortfall in position
    # accounting only; that plus a file-coverage shortfall; and no attribution at all.
    assert len({complete, partial, not_started}) == 3
    assert "aborted during the per-file scan" in partial, partial
    assert "a minimum established by real attribution, not a total" in partial, partial
    assert "aborted during the per-file scan" not in complete, complete
    assert "aborted before the per-file scan" in not_started, not_started
    assert "no identifier was ever attributed" in not_started, not_started
    assert "aborted before the per-file scan" not in complete, complete
    assert "aborted" not in complete, complete
    try:
        _f12_gates._d8_table_ref_note(counts, "whatever")
    except ValueError as exc:
        assert "unknown ADR-011 D8 table-reference-note scope" in str(exc), exc
    else:
        raise AssertionError("an unknown scope must raise rather than mislabel the counts")


# --- R2-N01 / ADR-011 D6.7.5 -------------------------------------------------------
# (GATE2-R2-N01-D67-D8-LOWER-BOUND-TRUTHFULNESS-2026-10-06)
#
# The completed-scan branch of the table-reference attribution note used to assert "the
# counts are complete for this run" on PASS, FAIL and ERROR alike.
# `GATE2-R2-N01-D67-D8-RESIDUAL-ROOT-CAUSE-2026-10-06.md` executed the counterexample
# that makes that sentence affirmatively false: a two-file run of
# `SELECT a FROM mem_roster` plus a bare-verb statement finishes its per-file
# scan and reports own/other/unattributed 1/0/0 while the bare-verb table positions
# yield no position record at all. (That record used bare `TRUNCATE`; the test below
# uses bare `COPY` for the same property, since TRUNCATE has since gained a real
# signal source -- see that test's own docstring.) `_D8_SCOPE_COMPLETE` records that the *file*
# traversal finished; ADR-011 D6.7.5 forbids reading that as the D6.7.2
# position-totality proof these counters would need in order to be a total.
#
# The discipline below is text-level, because this defect is invisible to an exit code.
# Every status, exit code, violation code and D3.2 figure is pinned UNCHANGED -- this is
# a disclosure correction and may not move a single number or verdict -- and the only
# thing asserted as different is the sentence. Mutant M-E6 (reassert the unconditional
# "the counts are complete for this run" for the completed-scan branch) leaves all of
# those pinned values intact, so only an exact-text assertion can kill it, on both the
# `render()` surface and the `asdict()`/`--json` note surface.
#
# The lower-bound sentence is written out here as an independent literal rather than
# read back from the module, so a change to the source text fails this file instead of
# silently agreeing with itself.
_R2N01_D8_LOWER_BOUND = (
    "the per-file scan ran to completion, but these counts are a lower bound and NOT a "
    "total -- every figure counts attributed extracted identifiers only, and this run "
    "carries no explicit ADR-011 D6.7.2 position-totality proof that every table "
    "position in every scanned subject yielded an identifier that reached a D3.2 state, "
    "so a table position the extractor did not recognise contributes nothing here and "
    "its absence from these figures is never evidence that no such position exists (a "
    "completed FILE scan is not a proved complete TABLE-REFERENCE inventory)"
)
# The sentence D6.7.5 removes. Named once so the kill assertion reads as the rule.
_R2N01_D8_FORBIDDEN = "the counts are complete for this run"


def _r2n01_ref_note_json(report):
    """The table-reference note read off the `asdict()` surface `--json` serialises,
    rather than off `render()`. A disclosure that was corrected on one surface only
    would leave the other able to show the old completeness claim."""
    payload = json.loads(report.to_json())
    notes = [n for n in payload["notes"]
             if "ADR-011 D8 table-reference attribution" in n]
    assert len(notes) == 1, payload
    return notes[0]


def _r2n01_assert_lower_bound(report):
    """Both surfaces carry the exact ADR-011 D6.7.5 lower-bound sentence, and neither
    carries the forbidden completeness claim for this dimension.

    Asserted per-note rather than over the whole report: the other D8 dimensions
    legitimately still say "the counts are complete for this run" and are out of this
    increment's scope, so a substring check over `render()` would pass even if this
    dimension reasserted it -- which is exactly the M-E6 mutant."""
    text_note = _f12b_ref_note(report)
    json_note = _r2n01_ref_note_json(report)
    assert text_note == json_note, (text_note, json_note)
    for note in (text_note, json_note):
        assert _R2N01_D8_LOWER_BOUND in note, note
        assert _R2N01_D8_FORBIDDEN not in note, note
        assert "complete for this run" not in note, note
        # The lower bound is stated without borrowing ADR-011 D5.5's reserved coverage
        # vocabulary, as every D8 note in this file must.
        assert "LOWER BOUND" not in note, note
        assert "PARTIAL" not in note, note
        assert "NOT_STARTED" not in note, note
        # ...nor either abort label, which name file-coverage claims this scope does not
        # make. The three scopes stay semantically distinct.
        assert "NOT FINAL" not in note, note
        assert "NOT STARTED" not in note, note
    rendered = [line for line in report.render().splitlines()
                if "ADR-011 D8 table-reference attribution" in line]
    assert len(rendered) == 1, report.render()
    assert _R2N01_D8_FORBIDDEN not in rendered[0], rendered


def test_r2n01_d8_completed_scan_discloses_a_lower_bound_on_pass_fail_and_error():
    """ADR-011 D6.7.5 on all three verdicts the completed-scan scope can carry. The
    sentence was false on each of them identically -- it is appended after the scan on
    the clean, FAIL and ERROR paths alike -- so correcting it on the PASS path only
    would leave the two paths a reader is most likely to be reassured by untouched.

    Every status, exit code, violation code and D3.2 figure here is the pre-correction
    one, asserted so the increment is provably disclosure-only."""
    pass_report = _f12b_run({"service.py": f'Q = "{_F12B_OWN}"\n'})
    assert pass_report.status == PASS, pass_report.render()
    assert pass_report.exit_code == 0, pass_report.render()
    assert pass_report.violations == [], pass_report.render()
    assert _f12b_counts(pass_report) == {**_F12B_ZERO, "own": 1}, pass_report.render()
    assert _f12b_total(pass_report) == 1, pass_report.render()
    _r2n01_assert_lower_bound(pass_report)

    fail_report = _f12b_run({"service.py": f'Q = "{_F12B_OTHER}"\n'})
    assert fail_report.status == FAIL, fail_report.render()
    assert fail_report.exit_code == 1, fail_report.render()
    assert fail_report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, fail_report.render()
    assert _f12b_counts(fail_report) == {**_F12B_ZERO, "other": 1}, fail_report.render()
    assert _f12b_total(fail_report) == 1, fail_report.render()
    _r2n01_assert_lower_bound(fail_report)

    error_report = _f12b_run({"service.py": f'Q = "{_F12B_UNATTRIBUTED}"\n'})
    assert error_report.status == ERROR, error_report.render()
    assert error_report.exit_code == 2, error_report.render()
    assert error_report.codes() == {"MODULE_DEPS_TABLE_UNATTRIBUTED"}, \
        error_report.render()
    assert _f12b_counts(error_report) == {**_F12B_ZERO, "unattributed": 1}, \
        error_report.render()
    assert _f12b_total(error_report) == 1, error_report.render()
    _r2n01_assert_lower_bound(error_report)


def test_r2n01_d8_mixed_two_file_counterexample_no_longer_claims_complete_counts():
    """The executed counterexample from
    `GATE2-R2-N01-D67-D8-RESIDUAL-ROOT-CAUSE-2026-10-06.md`, pinned as a regression.

    `a.sql` contributes one cleanly attributed own-table reference; `b.sql`'s
    `GRANT SELECT ON ALL TABLES IN SCHEMA bil_private TO r` implies a table position
    and yields no position record, so it is refused as
    MODULE_DEPS_SOURCE_UNINSPECTABLE. The per-file scan still *completes* -- both
    files were read -- and the attribution figures come out 1/0/0, which the old
    sentence called complete for the run.

    The record's original counterexample used bare `TRUNCATE mem_t, bil_invoices`.
    `GATE2-R2-N01-D67-TRUNCATE-BARE-VERB-SIGNAL-2026-10-06` gave TRUNCATE a real
    signal source, so that statement now yields two attributed positions and is a
    CROSS_DOMAIN_SQL_IMPORT -- it is no longer an instance of the under-count this
    test is about. COPY likewise gained a signal source in the qualified D6.8
    increment, and `GRANT SELECT ON bil_invoices TO r` -- this fixture's second
    basis -- gained one in GATE2-R2-N01-D67-GRANT-REVOKE-ON-2026-10-06. Re-based
    here onto a live under-count rather than deleted or relaxed, per this
    docstring's own standing instruction: a GRANT whose object is `ALL TABLES IN
    SCHEMA` references *every* table in another domain's schema and still yields no
    position at all, so the under-count it leaves is both real and larger than the
    one it replaces. If a future increment resolves that form too, re-base again on
    the same terms.

    The non-vacuity control is the comparison at the end: the two-file run reports the
    SAME own=1 and total=1 as the one-file run, even though it contains further
    table positions. That identity is the proof the figures are not a total, and it is
    why the note may only call them a lower bound. The ERROR status refuses this tree,
    but refusing a tree does not turn an under-count into a total."""
    mixed = _f12b_run({"a.sql": f"{_F12B_OWN}\n",
                       "b.sql": "GRANT SELECT ON ALL TABLES IN SCHEMA bil_private"
                                " TO r\n"})
    assert mixed.status == ERROR, mixed.render()
    assert mixed.exit_code == 2, mixed.render()
    assert mixed.codes() == {"MODULE_DEPS_SOURCE_UNINSPECTABLE"}, mixed.render()
    assert _f12b_counts(mixed) == {**_F12B_ZERO, "own": 1}, mixed.render()
    assert _f12b_total(mixed) == 1, mixed.render()
    _r2n01_assert_lower_bound(mixed)

    only_a = _f12b_run({"a.sql": f"{_F12B_OWN}\n"})
    assert only_a.status == PASS, only_a.render()
    assert only_a.exit_code == 0, only_a.render()
    assert _f12b_counts(only_a) == _f12b_counts(mixed), (only_a.render(), mixed.render())
    assert _f12b_total(only_a) == _f12b_total(mixed), (only_a.render(), mixed.render())
    _r2n01_assert_lower_bound(only_a)


def test_f12b_an_unknown_attribution_state_fails_closed_rather_than_going_uncounted():
    """The counter branch is exhaustive over D3.2's states by construction, and must stay
    that way loudly. If a seventh state were ever introduced without a counter, an
    attributed reference would vanish from the disclosure while the run still reported a
    verdict -- a silent under-count, which is the direction this gate may never fail in.
    Exercised by substituting an attribution helper that returns an unknown state, and
    asserted all the way out to the CLI so the fail-closed exit 2 is observed rather
    than assumed."""
    original = _f12_gates.attribute_table_identifier

    def rogue(*args, **kwargs):
        return _f12_gates.AttributionOutcome("seventh-state", None, "injected")

    try:
        _f12_gates.attribute_table_identifier = rogue
        try:
            _f12b_run({"service.py": f'Q = "{_F12B_OWN}"\n'})
        except ValueError as exc:
            assert "unknown ADR-011 D3.2 attribution state" in str(exc), exc
            assert "seventh-state" in str(exc), exc
        else:
            raise AssertionError("an unknown attribution state must raise, not go uncounted")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            modules_dir = _md_tree(root)
            _md_module(modules_dir, "membership", {"service.py": f'Q = "{_F12B_OWN}"\n'})
            _md_module(modules_dir, "billing",
                       {"interface.py": "def preview_charge(member):\n    return None\n"})
            manifest_path = root / "module-manifest.json"
            _md_write_manifest(modules_dir, manifest_path, _F12B_MODULES)
            code, out = _cli(["--gate", "module-deps", "--modules-dir", str(modules_dir),
                              "--module-manifest", str(manifest_path)])
    finally:
        _f12_gates.attribute_table_identifier = original
    assert _f12_gates.attribute_table_identifier is original, \
        _f12_gates.attribute_table_identifier
    # ADR-011 D7.3's outermost funnel: exit 2, a report on stdout, and never a PASS.
    assert code == 2, out
    assert "MODULE_DEPS_GATE_INTERNAL_ERROR" in out, out
    assert "PASS" not in out, out
    # Control: with the real helper restored the same tree is a clean PASS, so the
    # exit 2 above is attributable to the injected state and nothing else.
    restored = _f12b_run({"service.py": f'Q = "{_F12B_OWN}"\n'})
    assert restored.status == PASS, restored.render()
    assert _f12b_counts(restored) == {**_F12B_ZERO, "own": 1}, restored.render()


def test_f12b_counters_changed_no_verdict_no_code_and_no_exit_code():
    """The regression guard this increment's "disclosure only" claim rests on. Each
    fixture's status, exit code and code set is asserted alongside its counts, so a
    counter that had quietly reclassified an outcome -- turning a state-6 ERROR into a
    note, or a state-2 FAIL into a clean own-table reference -- would fail here even
    though its own count looked plausible."""
    cases = [
        ("X = 1\n", PASS, 0, set(), _F12B_ZERO),
        (f'Q = "{_F12B_OWN}"\n', PASS, 0, set(), {**_F12B_ZERO, "own": 1}),
        (f'Q = "{_F12B_SYSTEM}"\n', PASS, 0, set(), {**_F12B_ZERO, "system": 1}),
        (f'Q = "{_F12B_EXTERNAL}"\n', PASS, 0, set(), {**_F12B_ZERO, "external": 1}),
        ('Q = "SELECT 1"\n', PASS, 0, set(), _F12B_ZERO),
        (f'Q = "{_F12B_OTHER}"\n', FAIL, 1, {"CROSS_DOMAIN_SQL_IMPORT"},
         {**_F12B_ZERO, "other": 1}),
        (f'Q = "{_F12B_UNATTRIBUTED}"\n', ERROR, 2, {"MODULE_DEPS_TABLE_UNATTRIBUTED"},
         {**_F12B_ZERO, "unattributed": 1}),
        (f'Q = "{_F12B_CTE}"\n', ERROR, 2, {"MODULE_DEPS_TABLE_UNATTRIBUTED"},
         {**_F12B_ZERO, "unattributed": 1}),
        ('Q = "SELECT a FROM "\n', ERROR, 2, {"MODULE_DEPS_SOURCE_UNINSPECTABLE"},
         _F12B_ZERO),
    ]
    for source, status, exit_code, codes, counts in cases:
        report = _f12b_run({"service.py": source})
        assert report.status == status, (source, report.render())
        assert report.exit_code == exit_code, (source, report.render())
        assert report.codes() == codes, (source, report.render())
        assert _f12b_counts(report) == counts, (source, report.render())
        # Every run carries the disclosure, whatever its verdict.
        assert len([n for n in report.notes
                    if "ADR-011 D8 table-reference attribution" in n]) == 1, \
            (source, report.render())


# --- R1-F12 / ADR-011 D8 (GATE2-R1-F12-D8-IMPORT-EDGE-COUNTERS-2026-10-05) --------
#
# D8's third and last counted dimension: "cross-module import edges resolved and
# approved". The two counters above measure SQL text only -- trigger recognition, and
# table-position identifiers by D3.2 state. Neither says anything about the *import*
# half of the gate, so a clean verdict over a tree whose modules import each other
# through declared interfaces and a clean verdict over a tree with no cross-module
# import at all stayed indistinguishable on exactly the dimension `_import_violation`
# decides.
#
# The same opposed-pair discipline the two sections above use, with one addition the
# two-figure shape makes necessary: `resolved` and `approved` must be independently
# demonstrable, so every fixture pins both. A pinned TSD §6.3 directed-allowed edge
# must report resolved NONZERO *and* approved NONZERO (neither figure hardwired to 0);
# its reverse edge must report resolved NONZERO and approved ZERO (so `approved` is not
# hardwired to `resolved`, and a denied edge is not quietly dropped from the
# denominator); and a trivial tree must report both ZERO (so neither is hardwired
# positive and the zeros are usable as "no edge was decided").
#
# The undeclared-target control is the one place a counter could most easily lie in the
# reassuring direction: that path fails closed at exit 2, and an edge whose target names
# no declared module never reached the decision at all, so neither figure may move.

import dataclasses as _f12c_dataclasses

_F12C_MODULES = {
    "membership": _md_entry("MEM-01", ["mem_"], ["app.modules.membership.interface"]),
    "billing": _md_entry("BIL-02", ["bil_"], ["app.modules.billing.interface"]),
}

# The two cross-module import shapes over the manifest above, held as constants so a
# fixture's text and the figures asserted about it cannot drift apart. MEM-01/BIL-02 is
# not a TSD §6.3 pinned pair, so the interface import is approved on its own terms and
# the internals import is denied on its own -- no pair rule is in play either way.
_F12C_APPROVED = "from app.modules.billing.interface import preview_charge\n"
_F12C_DENIED = "from app.modules.billing.models import Invoice\n"
# Excluded shapes: same-module, `_shared` as the target, and a path that never resolves
# under the modules root at all.
_F12C_SAME_MODULE = "from app.modules.membership.models import Member\n"
_F12C_SHARED_TARGET = "from app.modules._shared.helpers import helper\n"
_F12C_OUTSIDE_ROOT = "import os\nfrom app.other.thing import unrelated\n"
# Target under the modules root naming no declared module: ERROR, and no edge.
_F12C_UNDECLARED = "from app.modules.nosuch.thing import absent\n"

_F12C_ZERO = {"resolved": 0, "approved": 0, "denied": 0}


def _f12c_run(membership_files, extra=None):
    """`_f12_run`'s scaffold over the same `mem_`/`bil_` manifest: `billing` exposes an
    interface and an internal module, `membership` gets `membership_files`, and `extra`
    (a callable taking `modules_dir`) may add `_shared`/modules-root surface. Nothing in
    the scaffold performs a cross-module import, so every nonzero figure below is
    attributable to the fixture under test -- asserted directly by
    `test_f12c_empty_scaffold_control_resolves_no_cross_module_edge`."""
    def build(modules_dir):
        _md_module(modules_dir, "membership", membership_files)
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge(member):\n    return None\n",
            "models.py": "class Invoice:\n    pass\n",
        })
        if extra is not None:
            extra(modules_dir)

    return _md_run(_F12C_MODULES, build)


def _f12c_pair_run(membership_files, modules):
    """The §6.3 scaffold: `upstream`/`downstream` under caller-supplied pinned-pair
    domains, with the import under test in `membership_files` placed on whichever module
    the caller named the importer. Kept separate from `_f12c_run` so the pair rule is in
    play only where a test means it to be."""
    def build(modules_dir):
        for name, files in membership_files.items():
            _md_module(modules_dir, name, files)

    return _md_run(modules, build)


def _f12c_edge_note(report):
    notes = [n for n in report.notes if "ADR-011 D8 cross-module import edges" in n]
    assert len(notes) == 1, report.render()
    return notes[0]


def _f12c_counts(report):
    """The three figures parsed out of the disclosure note itself, so every assertion
    below reads the numbers a human reader of the report would read -- never a
    separately recomputed figure that could agree with the code while the report lies."""
    tail = _f12c_edge_note(report).split("ADR-011 D8 cross-module import edges: ", 1)[1]
    resolved = int(tail.split(" edge occurrence(s) resolved", 1)[0])
    approved = int(tail.split("dependency decision, ", 1)[1].split(" approved by it", 1)[0])
    denied = int(tail.split(" approved by it and ", 1)[1].split(" denied;", 1)[0])
    # The note's own arithmetic, checked where it is read: a denied figure that did not
    # reconcile would misreport the decision while both other numbers looked plausible.
    assert denied == resolved - approved, (resolved, approved, denied)
    return {"resolved": resolved, "approved": approved, "denied": denied}


def test_f12c_empty_scaffold_control_resolves_no_cross_module_edge():
    """The baseline every figure below is measured against: the shared scaffold performs
    no cross-module import, so it must report 0 resolved. Without this control a nonzero
    figure elsewhere could be scaffold noise rather than the fixture's own edge."""
    report = _f12c_run({"service.py": "LIMIT = 50\n"})
    assert report.status == PASS, report.render()
    assert _f12c_counts(report) == _F12C_ZERO, report.render()


def test_f12c_pinned_pair_allowed_direction_reports_nonzero_resolved_and_approved():
    """The increment's reason to exist, over the fixture ADR-011 D8 most needs it on: the
    one TSD §6.3 synchronous direction a pinned pair permits. A clean verdict here must
    now evidence that the cross-module import decision ran *and* that it approved the
    edge -- the two figures a hardwired-zero counter could not produce. Every pinned pair
    is exercised, not just the first, since the permitted direction is per-pair."""
    for from_dom, to_dom in _PINNED_PAIRS:
        modules = {
            "upstream": _md_entry(from_dom, ["upstream_"], ["app.modules.upstream.interface"]),
            "downstream": _md_entry(to_dom, ["downstream_"],
                                    ["app.modules.downstream.interface"]),
        }
        report = _f12c_pair_run({
            "upstream": {"service.py": "from app.modules.downstream.interface import call\n"},
            "downstream": {"interface.py": "def call():\n    return None\n"},
        }, modules)
        assert report.status == PASS, (from_dom, to_dom, report.render())
        assert report.exit_code == 0, (from_dom, to_dom, report.render())
        assert report.violations == [], (from_dom, to_dom, report.render())
        assert _f12c_counts(report) == {"resolved": 1, "approved": 1, "denied": 0}, \
            (from_dom, to_dom, report.render())


def test_f12c_pinned_pair_reverse_edge_is_resolved_but_never_approved():
    """The opposed half, and the property that makes `approved` mean something: the
    reverse direction of the same pinned pair is still resolved -- the decision really
    examined it -- and approved ZERO. An `approved` hardwired to `resolved` would report
    this denied edge as approved while the FAIL still went out and made the report look
    healthy; dropping it from `resolved` instead would hide the edge from the
    denominator. The violation and the exit status are unchanged."""
    for from_dom, to_dom in _PINNED_PAIRS:
        modules = {
            "upstream": _md_entry(from_dom, ["upstream_"], ["app.modules.upstream.interface"]),
            "downstream": _md_entry(to_dom, ["downstream_"],
                                    ["app.modules.downstream.interface"]),
        }
        report = _f12c_pair_run({
            "upstream": {"interface.py": "def call():\n    return None\n"},
            "downstream": {"service.py": "from app.modules.upstream.interface import call\n"},
        }, modules)
        assert report.status == FAIL, (from_dom, to_dom, report.render())
        assert report.exit_code == 1, (from_dom, to_dom, report.render())
        assert report.codes() == {"REVERSE_EDGE_NOT_EVENT_DRIVEN"}, \
            (from_dom, to_dom, report.render())
        assert _f12c_counts(report) == {"resolved": 1, "approved": 0, "denied": 1}, \
            (from_dom, to_dom, report.render())
        # One violation, one counted denied edge: the disclosure and the violation list
        # are two views of the same decision and may not disagree.
        assert len(report.violations) == 1, (from_dom, to_dom, report.render())


def test_f12c_trivial_pass_reports_zero_not_an_equivalent_positive_proof():
    """The negative control that makes the positive ones mean something. `X = 1` and an
    approved cross-module interface import produce identical verdicts -- PASS, exit 0, no
    violation -- so the edge figures are the only thing distinguishing "decided and
    approved a real edge" from "decided none", which is the self-evidence ADR-011 D8 asks
    for. A counter that cannot report zero is not evidence of anything."""
    trivial = _f12c_run({"service.py": "X = 1\n"})
    positive = _f12c_run({"service.py": _F12C_APPROVED})
    for report in (trivial, positive):
        assert report.status == PASS, report.render()
        assert report.exit_code == 0, report.render()
        assert report.violations == [], report.render()
    assert _f12c_counts(trivial) == _F12C_ZERO, trivial.render()
    assert _f12c_counts(positive) == {"resolved": 1, "approved": 1, "denied": 0}, \
        positive.render()
    note = _f12c_edge_note(trivial)
    assert "0 edge occurrence(s) resolved" in note, note
    assert "evidences nothing about import-edge discipline" in note, note
    assert "the counts are complete for this run" in note, note


def test_f12c_cross_domain_internal_import_is_resolved_and_denied():
    """A denied edge outside any pinned pair: importing another module's internals is
    resolved (the decision examined it) and not approved, with its existing FAIL
    CROSS_DOMAIN_SQL_IMPORT untouched. Counting it must not have turned a FAIL into an
    approval, and the approved figure must not absorb it."""
    report = _f12c_run({"service.py": _F12C_DENIED})
    assert report.status == FAIL, report.render()
    assert report.exit_code == 1, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    assert _f12c_counts(report) == {"resolved": 1, "approved": 0, "denied": 1}, \
        report.render()
    assert len(report.violations) == 1, report.render()


def test_f12c_shared_importer_depending_on_a_domain_module_is_resolved_and_denied():
    """`_shared` is domain-free, so its import of a domain module is denied even though
    the target path *is* that module's declared public interface -- the one shape where
    an approved-looking path must still count as denied. If the counter keyed on the
    interface match rather than on the decision's return, this edge would be reported
    approved while the FAIL went out beside it."""
    def extra(modules_dir):
        _md_module(modules_dir, "_shared", {"helpers.py": _F12C_APPROVED})

    report = _f12c_run({"service.py": "X = 1\n"}, extra=extra)
    assert report.status == FAIL, report.render()
    assert report.exit_code == 1, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    assert _f12c_counts(report) == {"resolved": 1, "approved": 0, "denied": 1}, \
        report.render()
    assert any("_shared" in v.detail for v in report.violations), report.render()


def test_f12c_root_importer_keeps_its_domain_free_decision_on_both_outcomes():
    """ADR-011 D4's reserved modules-root importer, counted under its *existing*
    decision and not a new one: a root file importing a declared public interface is
    approved (D4 allows it -- the §6.3 pair check is inapplicable, `_root` having no
    domain), and the same file importing module internals is denied. Both are resolved
    either way, so root-level edges are neither excluded from the denominator nor given
    a different rule because they came from `_root`."""
    def approved_root(modules_dir):
        (modules_dir / "conftest.py").write_text(_F12C_APPROVED)

    approved = _f12c_run({"service.py": "X = 1\n"}, extra=approved_root)
    assert approved.status == PASS, approved.render()
    assert approved.exit_code == 0, approved.render()
    assert approved.violations == [], approved.render()
    assert _f12c_counts(approved) == {"resolved": 1, "approved": 1, "denied": 0}, \
        approved.render()

    def denied_root(modules_dir):
        (modules_dir / "conftest.py").write_text(_F12C_DENIED)

    denied = _f12c_run({"service.py": "X = 1\n"}, extra=denied_root)
    assert denied.status == FAIL, denied.render()
    assert denied.exit_code == 1, denied.render()
    assert denied.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, denied.render()
    assert _f12c_counts(denied) == {"resolved": 1, "approved": 0, "denied": 1}, \
        denied.render()
    assert any("_root" in v.detail for v in denied.violations), denied.render()
    note = _f12c_edge_note(approved)
    assert "'_root'" in note, note


def test_f12c_same_module_shared_target_and_out_of_tree_imports_are_not_edges():
    """The three short-circuits that must stay out of both figures, each asserted
    separately so none can be satisfied by another's absence. A same-module import, an
    import of `_shared` as the target (always allowed, short-circuited before the
    decision) and an import that never resolves under the modules root are not
    cross-module edges the decision was asked about; folding any of them in would
    inflate `resolved` with occurrences nothing decided -- and inflate `approved` with
    approvals never granted, which is the direction that would make a clean verdict read
    as evidence of approved edges it never examined."""
    for label, source in (("same-module", _F12C_SAME_MODULE),
                          ("_shared target", _F12C_SHARED_TARGET),
                          ("outside the modules root", _F12C_OUTSIDE_ROOT)):
        report = _f12c_run({"service.py": source, "models.py": "class Member:\n    pass\n"})
        assert report.status == PASS, (label, report.render())
        assert report.exit_code == 0, (label, report.render())
        assert report.violations == [], (label, report.render())
        assert _f12c_counts(report) == _F12C_ZERO, (label, report.render())
    # All three together, plus one real edge: the real one is counted exactly once, so
    # the exclusions neither suppress it nor add to it.
    mixed = _f12c_run({
        "service.py": _F12C_SAME_MODULE + _F12C_SHARED_TARGET + _F12C_OUTSIDE_ROOT
        + _F12C_APPROVED,
        "models.py": "class Member:\n    pass\n",
    })
    assert mixed.status == PASS, mixed.render()
    assert _f12c_counts(mixed) == {"resolved": 1, "approved": 1, "denied": 0}, mixed.render()
    note = _f12c_edge_note(mixed)
    assert "EXCLUDED from both figures" in note, note


def test_f12c_undeclared_target_error_fabricates_no_approval_and_no_edge():
    """The fail-closed control, and the one place a counter could lie in the reassuring
    direction. An import target under the modules root that names no declared module is
    MODULE_DEPS_GATE_INPUT_INVALID at exit 2 -- it never resolved to a declared module,
    so the decision was never asked about it and *neither* figure may move. Counting it
    approved would manufacture an approval on precisely the path that fails closed;
    counting it resolved would claim a decision that never happened.

    The second half is what makes the first half more than an artefact of an empty run:
    an approved edge earlier in the same file is still counted, so the ERROR path
    discloses the edges really decided before it as a minimum rather than reporting
    nothing -- and the undeclared edge beside it still adds nothing."""
    bare = _f12c_run({"service.py": _F12C_UNDECLARED})
    assert bare.status == ERROR, bare.render()
    assert bare.exit_code == 2, bare.render()
    assert bare.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, bare.render()
    assert "PASS" not in bare.render(), bare.render()
    assert _f12c_counts(bare) == _F12C_ZERO, bare.render()

    after = _f12c_run({"service.py": _F12C_APPROVED + _F12C_UNDECLARED})
    assert after.status == ERROR, after.render()
    assert after.exit_code == 2, after.render()
    assert after.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, after.render()
    assert _f12c_counts(after) == {"resolved": 1, "approved": 1, "denied": 0}, after.render()
    note = _f12c_edge_note(after)
    assert "contributes to NEITHER figure" in note, note
    assert "fabricate an approval the decision logic never made" in note, note
    assert "NOT FINAL" in note, note


def test_f12c_counts_occurrences_not_distinct_importer_target_pairs():
    """The definition the figures turn on: edge *occurrences*. Two imports of the same
    interface are two, not one -- a deduplicating counter would understate how many edges
    the decision really approved, and on the denied side it would quietly agree with a
    violation list that has its own dedup discipline. Both directions are asserted,
    including the two-aliases-on-one-statement form, which is two occurrences from a
    single Import node."""
    approved_twice = _f12c_run({
        "service.py": _F12C_APPROVED + "from app.modules.billing.interface import other\n",
    })
    assert approved_twice.status == PASS, approved_twice.render()
    assert _f12c_counts(approved_twice) == {"resolved": 2, "approved": 2, "denied": 0}, \
        approved_twice.render()

    denied_twice = _f12c_run({
        "service.py": _F12C_DENIED + "from app.modules.billing.models import Other\n",
    })
    assert denied_twice.status == FAIL, denied_twice.render()
    assert denied_twice.exit_code == 1, denied_twice.render()
    assert _f12c_counts(denied_twice) == {"resolved": 2, "approved": 0, "denied": 2}, \
        denied_twice.render()

    one_statement = _f12c_run({
        "service.py": ("import app.modules.billing.interface, "
                       "app.modules.billing.interface\n"),
    })
    assert one_statement.status == PASS, one_statement.render()
    assert _f12c_counts(one_statement) == {"resolved": 2, "approved": 2, "denied": 0}, \
        one_statement.render()
    note = _f12c_edge_note(one_statement)
    assert "counted occurrences and not distinct (importer, target) pairs" in note, note


def test_f12c_one_run_reports_approved_and_denied_edges_together():
    """Both outcomes in a single run, so neither figure can be satisfied only in
    isolation and neither can be absorbing the other's edges. Three occurrences, one
    approved and two denied, with the totals reconciling and the run's FAIL unchanged."""
    report = _f12c_run({
        "service.py": _F12C_APPROVED + _F12C_DENIED,
        "repo.py": "from app.modules.billing.models import Other\n",
    })
    assert report.status == FAIL, report.render()
    assert report.exit_code == 1, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    assert _f12c_counts(report) == {"resolved": 3, "approved": 1, "denied": 2}, \
        report.render()
    note = _f12c_edge_note(report)
    assert "the counts are complete for this run" in note, note
    assert "NOT FINAL" not in note, note
    assert "NOT STARTED" not in note, note


def test_f12c_mixed_error_run_keeps_the_partition_and_every_d8_disclosure():
    """F09's D7.2 mixed report, preserved across this third disclosure. A run carrying a
    denied import edge (FAIL-class) and an unattributed table reference (ERROR-class)
    must still partition them, must carry all three D8 notes, and -- the scan having
    completed -- must label the edge figures a real total. Dropping a disclosure on an
    ERROR return is R1-F09's own failure mode, and the import-edge note is the newest
    thing that could be dropped there."""
    report = _f12c_run({
        "service.py": _F12C_DENIED,
        "queries.py": 'Q = "SELECT a FROM nobody_owns"\n',
    })
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT",
                              "MODULE_DEPS_TABLE_UNATTRIBUTED"}, report.render()
    assert any("ADR-011 D7.2 partitioned report" in n for n in report.notes), report.render()
    assert any("ADR-011 D8 SQL-trigger inspection" in n for n in report.notes), report.render()
    assert any("ADR-011 D8 table-reference attribution" in n for n in report.notes), \
        report.render()
    assert _f12c_counts(report) == {"resolved": 1, "approved": 0, "denied": 1}, \
        report.render()
    assert "the counts are complete for this run" in _f12c_edge_note(report), report.render()


def test_f12c_abort_during_the_scan_labels_the_counts_not_final():
    """An abort *inside* the per-file scan: the figures are whatever real decisions had
    been made, so they must be labelled NOT FINAL rather than read as totals.
    `membership/a_import.py` sorts before the unparseable `membership/z_broken.py`, so a
    genuine approved edge is decided before the abort -- an all-zero count here would not
    discriminate between the two abort shapes."""
    report = _f12c_run({
        "a_import.py": _F12C_APPROVED,
        "z_broken.py": "def broken(:\n",
    })
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, report.render()
    assert _f12c_counts(report) == {"resolved": 1, "approved": 1, "denied": 0}, \
        report.render()
    note = _f12c_edge_note(report)
    assert "NOT FINAL" in note, note
    assert "aborted during the per-file scan" in note, note
    assert "minima established by real decisions, not totals" in note, note
    assert "complete for this run" not in note, note
    assert "NOT STARTED" not in note, note
    # D5.5's reserved coverage vocabulary stays unborrowed for this different claim.
    assert "LOWER BOUND" not in note, note
    assert "PARTIAL" not in note, note


def test_f12c_abort_before_the_scan_labels_the_counts_not_started_not_a_clean_zero():
    """An abort *upstream* of the per-file scan (an absent --modules-dir): no edge was
    ever put to the decision, so the zeros must record that rather than that the tree
    holds no cross-module import. Collapsing this into NOT FINAL would make the two
    aborts indistinguishable; collapsing it into the complete label would state a total
    this run never established -- the fabricated-total shape D5.5 exists to prevent,
    reproduced one disclosure over."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        manifest_path = root / "module-manifest.json"
        manifest_path.write_text(json.dumps(_md_manifest(_F12C_MODULES)))
        report = run_module_deps_gate(root / "app" / "modules", manifest_path)
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, report.render()
    assert "PASS" not in report.render(), report.render()
    assert _f12c_counts(report) == _F12C_ZERO, report.render()
    note = _f12c_edge_note(report)
    assert "NOT STARTED" in note, note
    assert "aborted before the per-file scan" in note, note
    assert "never that the tree holds no cross-module import" in note, note
    assert "NOT FINAL" not in note, note
    assert "complete for this run" not in note, note
    # The coverage pass's own vocabulary stays unborrowed, so `test_d5_absent_modules_
    # dir_discloses_not_started_rather_than_nothing`'s assertions over every note hold.
    assert "NOT_STARTED" not in note, note
    assert "PARTIAL" not in note, note
    assert "LOWER BOUND" not in note, note


def test_f12c_edge_disclosure_reaches_both_cli_surfaces():
    """Driven through `main` so the text renderer and the `--json` serialiser are each
    exercised for real, with the exit code asserted rather than inferred. A disclosure
    that existed only on one surface would leave the other able to show a clean verdict
    with no evidence behind it. Both a PASS (approved edge) and a FAIL (denied edge) are
    driven, since the FAIL path is where a reader most needs the two figures to
    reconcile against the violation list."""
    def write_tree(root, membership_source):
        modules_dir = _md_tree(root)
        _md_module(modules_dir, "membership", {"service.py": membership_source})
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge(member):\n    return None\n",
            "models.py": "class Invoice:\n    pass\n",
        })
        manifest_path = root / "module-manifest.json"
        _md_write_manifest(modules_dir, manifest_path, _F12C_MODULES)
        return ["--gate", "module-deps", "--modules-dir", str(modules_dir),
                "--module-manifest", str(manifest_path)]

    approved_line = ("1 edge occurrence(s) resolved to a declared module and put to the "
                     "dependency decision, 1 approved by it and 0 denied")
    with tempfile.TemporaryDirectory() as tmp:
        code, out = _cli(write_tree(Path(tmp), _F12C_APPROVED))
    assert code == 0, out
    assert "[module-deps] PASS" in out, out
    assert "ADR-011 D8 cross-module import edges" in out, out
    assert approved_line in out, out
    assert "the counts are complete for this run" in out, out

    with tempfile.TemporaryDirectory() as tmp:  # a fresh tree: `_md_tree` creates `app/`
        json_code, json_out = _cli(write_tree(Path(tmp), _F12C_APPROVED) + ["--json"])
    assert json_code == 0, json_out
    payload = json.loads(json_out)
    assert payload["status"] == PASS, payload
    assert payload["violations"] == [], payload
    disclosure = [n for n in payload["notes"]
                  if "ADR-011 D8 cross-module import edges" in n]
    assert len(disclosure) == 1, payload
    assert approved_line in disclosure[0], disclosure
    assert "RESIDUAL: statically resolvable imports only" in disclosure[0], disclosure
    assert "gate 2 is architecture hygiene, not a security boundary" in disclosure[0], \
        disclosure

    denied_line = ("1 edge occurrence(s) resolved to a declared module and put to the "
                   "dependency decision, 0 approved by it and 1 denied")
    with tempfile.TemporaryDirectory() as tmp:
        fail_code, fail_out = _cli(write_tree(Path(tmp), _F12C_DENIED) + ["--json"])
    assert fail_code == 1, fail_out
    fail_payload = json.loads(fail_out)
    assert fail_payload["status"] == FAIL, fail_payload
    assert any(denied_line in n for n in fail_payload["notes"]), fail_payload


def test_f12c_note_builder_scopes_are_distinct_and_an_unknown_scope_fails_closed():
    """The three labels must actually differ, so a partial or never-decided pair of
    figures can never be read as totals (and vice versa), while the figures and the
    residual text stay identical across all three. An unrecognised scope raises rather
    than falling back to the most reassuring label -- a future caller that mislabels a
    run must break loudly instead of under-disclosing."""
    counts = _f12_gates._ImportEdgeCounts(resolved=5, approved=3)
    assert counts.denied == 2, counts
    complete = _f12_gates._d8_import_edge_note(counts)
    partial = _f12_gates._d8_import_edge_note(counts, _f12_gates._D8_SCOPE_PARTIAL)
    not_started = _f12_gates._d8_import_edge_note(_f12_gates._ImportEdgeCounts(),
                                                  _f12_gates._D8_SCOPE_NOT_STARTED)
    for note in (complete, partial, not_started):
        assert "RESIDUAL: statically resolvable imports only" in note, note
        assert "EXCLUDED from both figures" in note, note
        assert "GATE2-R1-F12-D8-IMPORT-EDGE-COUNTERS-2026-10-05" in note, note
        # None of the three borrows the coverage disclosure's reserved vocabulary.
        assert "LOWER BOUND" not in note, note
        assert "PARTIAL" not in note, note
        assert "NOT_STARTED" not in note, note
    for note in (complete, partial):
        assert "5 edge occurrence(s) resolved" in note, note
        assert "3 approved by it and 2 denied" in note, note
    assert "the counts are complete for this run" in complete, complete
    assert "NOT FINAL" not in complete, complete
    assert "NOT STARTED" not in complete, complete
    assert "NOT FINAL" in partial, partial
    assert "NOT STARTED" not in partial, partial
    assert "NOT STARTED" in not_started, not_started
    assert "NOT FINAL" not in not_started, not_started
    assert "0 edge occurrence(s) resolved" in not_started, not_started
    assert "0 approved by it and 0 denied" in not_started, not_started
    for note in (partial, not_started):
        assert "complete for this run" not in note, note
    try:
        _f12_gates._d8_import_edge_note(counts, "whatever")
    except ValueError as exc:
        assert "unknown ADR-011 D8 import-edge-note scope" in str(exc), exc
    else:
        raise AssertionError("an unknown scope must raise rather than mislabel the counts")


def test_f12c_denied_is_derived_so_the_two_figures_cannot_drift():
    """`denied` is a property over `resolved - approved`, never a third accumulator. A
    separately-incremented denied count could disagree with the pair -- reporting fewer
    denied edges than the decision refused, which is the under-disclosing direction --
    and there would be nothing in the report to reveal it."""
    counts = _f12_gates._ImportEdgeCounts()
    assert counts.denied == 0, counts
    counts.resolved += 1
    assert counts.denied == 1, counts  # resolved before the decision returned
    counts.approved += 1
    assert counts.denied == 0, counts
    assert "denied" not in {f.name for f in _f12c_dataclasses.fields(counts)}, counts


def test_f12c_counters_changed_no_verdict_no_code_and_no_exit_code():
    """The regression guard this increment's "disclosure only" claim rests on. Each
    fixture's status, exit code and code set is asserted alongside its figures, so a
    counter that had quietly reclassified an outcome -- turning a denied edge into an
    approved one, or an undeclared-target ERROR into a counted approval -- would fail
    here even though its own numbers looked plausible."""
    cases = [
        ("X = 1\n", PASS, 0, set(), _F12C_ZERO),
        (_F12C_SAME_MODULE, PASS, 0, set(), _F12C_ZERO),
        (_F12C_SHARED_TARGET, PASS, 0, set(), _F12C_ZERO),
        (_F12C_OUTSIDE_ROOT, PASS, 0, set(), _F12C_ZERO),
        (_F12C_APPROVED, PASS, 0, set(), {"resolved": 1, "approved": 1, "denied": 0}),
        (_F12C_DENIED, FAIL, 1, {"CROSS_DOMAIN_SQL_IMPORT"},
         {"resolved": 1, "approved": 0, "denied": 1}),
        (_F12C_UNDECLARED, ERROR, 2, {"MODULE_DEPS_GATE_INPUT_INVALID"}, _F12C_ZERO),
    ]
    for source, status, exit_code, codes, counts in cases:
        report = _f12c_run({"service.py": source,
                            "models.py": "class Member:\n    pass\n"})
        assert report.status == status, (source, report.render())
        assert report.exit_code == exit_code, (source, report.render())
        assert report.codes() == codes, (source, report.render())
        assert _f12c_counts(report) == counts, (source, report.render())
        # Every run carries the disclosure, whatever its verdict.
        assert len([n for n in report.notes
                    if "ADR-011 D8 cross-module import edges" in n]) == 1, \
            (source, report.render())


def test_f12c_counter_did_not_wire_cte_state_3_into_live_scanning():
    """Scope guard, as every increment in this file carries: counting import edges must
    not have quietly wired D3.2 state 3 (CTE-local names) into the live scanning path,
    nor disturbed the two SQL-side D8 counters. A `WITH`-bound name in table position is
    still an unattributed ERROR with a CTE count of 0, and a clean run still declares
    state-3 collection unimplemented."""
    report = _f12c_run({"service.py": f'Q = "{_F12B_CTE}"\n'})
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert "MODULE_DEPS_TABLE_UNATTRIBUTED" in report.codes(), report.render()
    assert _f12b_counts(report)["cte"] == 0, report.render()
    assert _f12c_counts(report) == _F12C_ZERO, report.render()

    clean = _f12c_run({"service.py": _F12C_APPROVED})
    assert clean.status == PASS, clean.render()
    assert any("remains unimplemented" in n for n in clean.notes), clean.render()
    # The SQL-side notes now point at this dimension instead of calling it unimplemented,
    # so a reader is not told twice that it is missing.
    assert not any("import-edge counters remain unimplemented" in n for n in clean.notes), \
        clean.render()
    assert any("GATE2-R1-F12-D8-IMPORT-EDGE-COUNTERS-2026-10-05" in n
               for n in clean.notes), clean.render()


# --- R1-F12 / ADR-011 D3.5 + D8 (GATE2-R1-F12-D8-EXTERNAL-NAMES-2026-10-05) -------
#
# D3.5's own disclosure obligation, which no counter above discharges: "Every declared
# entry is disclosed **by name**, with a count, in both text and `--json` output on every
# run **including PASS**" (D8: table references by state, "with declared external
# references listed **by name**").
#
# The section above counts state-5 *observations* -- identifiers in scanned SQL that
# resolved to a declaration. That is a different fact. A manifest can declare `audit_log`
# while nothing references it, and the state-5 count then reads 0 with the declaration
# nowhere on the report. So the central assertions here are pointedly about the two
# numbers NOT being each other: a declared-but-unreferenced entry must still be listed,
# and one declaration referenced twice must leave the inventory count at 1.
#
# The two directions a disclosure like this can lie, each with its own test:
#   * Under-disclosing by dedup. Two modules may legally declare the same unowned
#     identifier, and a listing keyed on the bare name would show one dependency where
#     there are two. Identity is the (module, name) pair, asserted across modules and
#     within one module's own list.
#   * A false zero. A run that aborted before any manifest parsed has no inventory, and an
#     empty listing there would assert the manifest declares nothing -- the fabricated-
#     total shape D5.5 exists to prevent. Four pre-parse abort shapes are asserted to read
#     UNKNOWN, including the D3.5 conflict that rejects the manifest *because of* an
#     external entry, where listing that entry would be maximally misleading.
#
# And the property that makes this dimension unlike the three counters: the inventory is a
# property of the parsed manifest, not of scan progress, so it stays COMPLETE through a
# mid-scan abort and through an ERROR-class return, and it is never labelled a minimum.

_F12D_EXTERNAL_A = "audit_log"                    # 1-part, owned by no module
_F12D_EXTERNAL_B = "legacy_schema.legacy_table"   # 2-part, schema owned by no module


def _f12d_entry(domain, prefix, module, ext_refs):
    return {
        "domain": domain,
        "owned_table_prefixes": [prefix],
        "public_interfaces": [f"app.modules.{module}.interface"],
        "external_table_references": list(ext_refs),
    }


# `membership` lists B before A on purpose: the disclosure must sort, so the listing is
# independent of manifest order rather than echoing it.
_F12D_MODULES = {
    "membership": _f12d_entry("MEM-01", "mem_", "membership",
                              [_F12D_EXTERNAL_B, _F12D_EXTERNAL_A]),
    "billing": _f12d_entry("BIL-02", "bil_", "billing", [_F12D_EXTERNAL_A]),
}
# The sorted (module, name) listing the manifest above must always produce.
_F12D_LISTED = ["billing:audit_log", "membership:audit_log",
                "membership:legacy_schema.legacy_table"]
_F12D_FULL = {"count": 3, "declaring": 2, "entries": _F12D_LISTED}

# The same two modules with no `external_table_references` at all: the trivial control.
_F12D_PLAIN_MODULES = {
    "membership": _md_entry("MEM-01", ["mem_"], ["app.modules.membership.interface"]),
    "billing": _md_entry("BIL-02", ["bil_"], ["app.modules.billing.interface"]),
}


def _f12d_run(membership_files, modules=None, manifest=None, write_manifest=True):
    """`_f12b_run`'s scaffold under `_F12D_MODULES` (or a caller-supplied `modules`).
    Nothing in the scaffold declares or references an external table, so every figure
    below is attributable to the manifest under test."""
    def build(modules_dir):
        _md_module(modules_dir, "membership", membership_files)
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge(member):\n    return None\n",
        })

    return _md_run(_F12D_MODULES if modules is None else modules, build,
                   manifest=manifest, write_manifest=write_manifest)


def _f12d_note(report):
    notes = [n for n in report.notes
             if "ADR-011 D3.5/D8 declared external_table_references inventory" in n]
    assert len(notes) == 1, report.render()
    return notes[0]


def _f12d_inventory(report):
    """The count, the declaring-module count and the listed `module:name` entries parsed
    out of the disclosure note itself, so every assertion below reads what a human reader
    of the report reads -- never a separately recomputed value that could agree with the
    code while the report lies. Returns `None` for the no-inventory (pre-parse) shape,
    which is the one case that must not be representable as a count.

    The note's own internal consistency is checked where it is read: a count that did not
    match its own listing, or a declaring-module figure that did not match the distinct
    modules in it, would misreport the manifest while every individual number looked
    plausible."""
    note = _f12d_note(report)
    tail = note.split("inventory: ", 1)[1]
    if tail.startswith("NOT STARTED"):
        return None
    count = int(tail.split(" declared entry/ies", 1)[0])
    declaring = int(tail.split(" across ", 1)[1].split(" declaring module(s)", 1)[0])
    listed = tail.split(" -- ", 1)[1].split(";", 1)[0].strip()
    entries = [] if listed == "none" else listed.split(", ")
    assert len(entries) == count, (entries, count)
    assert declaring == len({e.split(":", 1)[0] for e in entries}), (entries, declaring)
    return {"count": count, "declaring": declaring, "entries": entries}


def test_f12d_declared_entries_are_listed_by_name_with_a_count_on_a_pass():
    """The increment's reason to exist, on the run ADR-011 D3.5 names explicitly: a PASS.
    Nothing in this tree references either declared table, so the state-5 observation
    count is 0 and before this increment the two declarations appeared nowhere on the
    report at all. Both names, the count, and the declaring-module count must now be on
    the face of a clean verdict, with the verdict itself unchanged."""
    report = _f12d_run({"service.py": "LIMIT = 50\n"})
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    assert report.violations == [], report.render()
    assert _f12d_inventory(report) == _F12D_FULL, report.render()
    note = _f12d_note(report)
    assert "the inventory is complete for this run" in note, note
    assert "NOT STARTED" not in note, note
    assert "UNKNOWN" not in note, note
    # The declaration is disclosed although nothing observed it -- the whole point.
    assert _f12b_counts(report)["external"] == 0, report.render()


def test_f12d_trivial_manifest_reports_none_declared_not_an_absent_inventory():
    """The negative control that makes the positive one mean something, and the one shape
    that must not be confused with a pre-parse abort. A manifest declaring no external
    reference reports an explicit zero and `none`, which is a real observation about a
    manifest that was read -- distinct from the UNKNOWN shape below, where no manifest was
    read at all. A disclosure that cannot report zero is not evidence of anything."""
    report = _f12d_run({"service.py": "LIMIT = 50\n"}, modules=_F12D_PLAIN_MODULES)
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    assert report.violations == [], report.render()
    assert _f12d_inventory(report) == {"count": 0, "declaring": 0, "entries": []}, \
        report.render()
    note = _f12d_note(report)
    assert "0 declared entry/ies across 0 declaring module(s) -- none" in note, note
    assert "the inventory is complete for this run" in note, note
    assert "NOT STARTED" not in note, note
    assert "UNKNOWN" not in note, note


def test_f12d_one_name_declared_by_two_modules_is_listed_twice_by_pair_identity():
    """No dedup across modules. Two modules declaring the same unowned identifier is two
    declarations -- D3.5 forbids an entry *resolving to an owned prefix/schema*, not two
    modules naming the same unowned table -- and a listing keyed on the bare name would
    show one dependency where there are two, hiding which module holds the other."""
    modules = {
        "membership": _f12d_entry("MEM-01", "mem_", "membership", [_F12D_EXTERNAL_A]),
        "billing": _f12d_entry("BIL-02", "bil_", "billing", [_F12D_EXTERNAL_A]),
    }
    report = _f12d_run({"service.py": "X = 1\n"}, modules=modules)
    assert report.status == PASS, report.render()
    assert _f12d_inventory(report) == {
        "count": 2, "declaring": 2,
        "entries": ["billing:audit_log", "membership:audit_log"],
    }, report.render()
    note = _f12d_note(report)
    assert "identity is that PAIR, never the bare name" in note, note


def test_f12d_a_name_repeated_within_one_module_is_not_silently_deduplicated():
    """The other no-dedup direction, inside a single module's own list. The parser does not
    reject a repeated `external_table_references` value, so collapsing it here would make
    the report disagree with the manifest on disk -- and a reader reconciling the two would
    be told the manifest says something it does not."""
    modules = {
        "membership": _f12d_entry("MEM-01", "mem_", "membership",
                                  [_F12D_EXTERNAL_A, _F12D_EXTERNAL_A]),
        "billing": _md_entry("BIL-02", ["bil_"], ["app.modules.billing.interface"]),
    }
    report = _f12d_run({"service.py": "X = 1\n"}, modules=modules)
    assert report.status == PASS, report.render()
    assert _f12d_inventory(report) == {
        "count": 2, "declaring": 1,
        "entries": ["membership:audit_log", "membership:audit_log"],
    }, report.render()


def test_f12d_listing_is_byte_identical_under_a_different_manifest_key_order():
    """Determinism, asserted the only way that means anything: the same declarations in a
    different manifest order must produce a byte-identical note. A listing that echoed
    manifest order would make two reports of the same manifest diff spuriously, and a
    reader could not tell a reordering from a real change in what the tree may reach."""
    shuffled = {
        name: {**entry,
               "external_table_references": list(reversed(entry["external_table_references"]))}
        for name, entry in reversed(list(_F12D_MODULES.items()))
    }
    assert list(shuffled) != list(_F12D_MODULES), shuffled  # the fixture really differs
    forward = _f12d_run({"service.py": "X = 1\n"})
    reordered = _f12d_run({"service.py": "X = 1\n"}, modules=shuffled)
    for report in (forward, reordered):
        assert report.status == PASS, report.render()
    assert _f12d_note(forward) == _f12d_note(reordered), \
        (_f12d_note(forward), _f12d_note(reordered))
    assert _f12d_inventory(reordered) == _F12D_FULL, reordered.render()


def test_f12d_abort_before_a_valid_manifest_discloses_unknown_not_a_false_zero():
    """Four pre-parse abort shapes, each of which must disclose UNKNOWN rather than an
    empty inventory. `0 declared entry/ies ... none` here would assert that a manifest was
    read and declares nothing, which is the fabricated-total failure mode D5.5 exists to
    prevent, reproduced one disclosure over.

    The fourth case is the sharpest: the manifest is rejected *because of* an external
    entry (D3.5 -- `mem_roster` resolves to `membership`'s own `mem_` prefix), so a
    disclosure built from a half-parsed manifest would list exactly the entry that made
    the input invalid, presenting a rejected declaration as an accepted one."""
    conflicting = {
        "membership": _f12d_entry("MEM-01", "mem_", "membership", ["mem_roster"]),
        "billing": _md_entry("BIL-02", ["bil_"], ["app.modules.billing.interface"]),
    }
    cases = {
        "no manifest file": lambda: _f12d_run({"service.py": "X = 1\n"},
                                              write_manifest=False),
        "unsupported version": lambda: _f12d_run(
            {"service.py": "X = 1\n"},
            manifest={"version": 2, "modules": _F12D_MODULES}),
        "module entry not an object": lambda: _f12d_run(
            {"service.py": "X = 1\n"},
            manifest={"version": 1, "modules": {"membership": "nope"}}),
        "D3.5 conflict": lambda: _f12d_run({"service.py": "X = 1\n"},
                                           modules=conflicting),
    }
    for label, run in cases.items():
        report = run()
        assert report.status == ERROR, (label, report.render())
        assert report.exit_code == 2, (label, report.render())
        assert report.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, (label, report.render())
        assert "PASS" not in report.render(), (label, report.render())
        assert _f12d_inventory(report) is None, (label, report.render())
        note = _f12d_note(report)
        assert "NOT STARTED" in note, (label, note)
        assert "declaration count UNKNOWN" in note, (label, note)
        assert "declared name(s) UNKNOWN" in note, (label, note)
        assert "an empty inventory must not be inferred from it" in note, (label, note)
        for fabricated in ("0 declared entry/ies", "-- none", "complete for this run"):
            assert fabricated not in note, (label, fabricated, note)
        # No declared name is listed on a manifest that never became valid, least of all
        # the one that invalidated it.
        for name in (_F12D_EXTERNAL_A, _F12D_EXTERNAL_B, "mem_roster"):
            assert f":{name}" not in note, (label, name, note)
        # The coverage pass's reserved vocabulary stays unborrowed, as every D8 note does.
        for marker in ("NOT_STARTED", "PARTIAL", "LOWER BOUND"):
            assert marker not in note, (label, marker, note)


def test_f12d_an_absent_modules_dir_also_discloses_unknown():
    """The same UNKNOWN requirement on the abort that happens upstream of the manifest
    read entirely -- `_modules_root_package` raises first, so the manifest on disk is
    valid and still never parsed. Kept separate from the four cases above because it is
    the one shape where a valid manifest file exists and must *still* not be listed."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        manifest_path = root / "module-manifest.json"
        manifest_path.write_text(json.dumps(_md_manifest(_F12D_MODULES)))
        report = run_module_deps_gate(root / "app" / "modules", manifest_path)
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, report.render()
    assert "PASS" not in report.render(), report.render()
    assert _f12d_inventory(report) is None, report.render()
    note = _f12d_note(report)
    assert "aborted before a valid manifest was available" in note, note
    assert _F12D_EXTERNAL_A not in note, note


def test_f12d_an_error_after_the_manifest_parsed_keeps_the_complete_inventory():
    """The property that distinguishes this dimension from the three counters above: the
    inventory is a property of the parsed manifest, not of scan progress. All three
    post-parse failure shapes must carry the *complete* listing and the complete label --
    a mid-scan abort (unparseable file), an ERROR-class return (an unattributed table
    reference), and a FAIL (a cross-domain SQL reference). Labelling any of them a minimum
    would understate what the manifest declares; dropping the note is R1-F09's own
    failure mode."""
    mid_scan = _f12d_run({"a_ok.py": "X = 1\n", "z_broken.py": "def broken(:\n"})
    assert mid_scan.status == ERROR, mid_scan.render()
    assert mid_scan.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, mid_scan.render()

    error_class = _f12d_run({"queries.py": 'Q = "SELECT a FROM nobody_owns"\n'})
    assert error_class.status == ERROR, error_class.render()
    assert error_class.codes() == {"MODULE_DEPS_TABLE_UNATTRIBUTED"}, error_class.render()

    failing = _f12d_run({"queries.py": 'Q = "SELECT a FROM bil_invoices"\n'})
    assert failing.status == FAIL, failing.render()
    assert failing.exit_code == 1, failing.render()
    assert failing.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, failing.render()

    for label, report in (("mid-scan abort", mid_scan), ("ERROR-class", error_class),
                          ("FAIL", failing)):
        assert _f12d_inventory(report) == _F12D_FULL, (label, report.render())
        note = _f12d_note(report)
        assert "the inventory is complete for this run" in note, (label, note)
        assert "stays complete if the scan later ends in ERROR" in note, (label, note)
        assert "NOT STARTED" not in note, (label, note)
        assert "UNKNOWN" not in note, (label, note)
        assert "NOT FINAL" not in note, (label, note)


def test_f12d_the_inventory_is_not_the_observed_state_5_count():
    """The distinction the whole increment turns on, asserted in both directions so neither
    number can be standing in for the other. A declared entry nothing references leaves the
    state-5 observation at 0 while the inventory still lists it; one declaration referenced
    twice makes the observation 2 while the inventory count stays 1 for that module. If the
    new disclosure were derived from the scan (or the old count from the manifest), one of
    these two pairs would be impossible."""
    unreferenced = _f12d_run({"service.py": "X = 1\n"})
    assert unreferenced.status == PASS, unreferenced.render()
    assert _f12d_inventory(unreferenced) == _F12D_FULL, unreferenced.render()
    assert _f12b_counts(unreferenced)["external"] == 0, unreferenced.render()

    twice = _f12d_run({
        "queries.py": ('A = "SELECT a FROM audit_log"\n'
                       'B = "SELECT b FROM audit_log"\n'),
    })
    assert twice.status == PASS, twice.render()
    assert twice.violations == [], twice.render()
    assert _f12b_counts(twice)["external"] == 2, twice.render()
    # Two observations of one declaration: the inventory is unmoved by the scan.
    assert _f12d_inventory(twice) == _F12D_FULL, twice.render()
    note = _f12d_note(twice)
    assert "DECLARATION, NOT OBSERVATION" in note, note
    assert "a declared entry no statement references is normal" in note, note
    # And the state-5 counter's own note now points here instead of leaving a reader to
    # read the observation as the declaration inventory.
    ref_note = _f12b_ref_note(twice)
    assert "GATE2-R1-F12-D8-EXTERNAL-NAMES-2026-10-05" in ref_note, ref_note
    assert "counts identifiers OBSERVED in scanned SQL" in ref_note, ref_note


def test_f12d_inventory_reaches_both_cli_surfaces():
    """Driven through `main` so the text renderer and the `--json` serialiser are each
    exercised for real, with the exit code asserted rather than inferred. D3.5 requires the
    names on *both* surfaces; a disclosure present on only one would leave the other able
    to show a clean verdict with the declarations invisible."""
    def write_tree(root):
        modules_dir = _md_tree(root)
        _md_module(modules_dir, "membership", {"service.py": "LIMIT = 50\n"})
        _md_module(modules_dir, "billing", {
            "interface.py": "def preview_charge(member):\n    return None\n",
        })
        manifest_path = root / "module-manifest.json"
        _md_write_manifest(modules_dir, manifest_path, _F12D_MODULES)
        return ["--gate", "module-deps", "--modules-dir", str(modules_dir),
                "--module-manifest", str(manifest_path)]

    listing = ("3 declared entry/ies across 2 declaring module(s) -- "
               "billing:audit_log, membership:audit_log, "
               "membership:legacy_schema.legacy_table")
    with tempfile.TemporaryDirectory() as tmp:
        code, out = _cli(write_tree(Path(tmp)))
    assert code == 0, out
    assert "[module-deps] PASS" in out, out
    assert "ADR-011 D3.5/D8 declared external_table_references inventory" in out, out
    assert listing in out, out

    with tempfile.TemporaryDirectory() as tmp:  # a fresh tree: `_md_tree` creates `app/`
        json_code, json_out = _cli(write_tree(Path(tmp)) + ["--json"])
    assert json_code == 0, json_out
    payload = json.loads(json_out)
    assert payload["status"] == PASS, payload
    assert payload["violations"] == [], payload
    disclosure = [n for n in payload["notes"]
                  if "ADR-011 D3.5/D8 declared external_table_references inventory" in n]
    assert len(disclosure) == 1, payload
    assert listing in disclosure[0], disclosure
    assert "DECLARATION, NOT OBSERVATION" in disclosure[0], disclosure
    assert "gate 2 is architecture hygiene, not a security boundary" in disclosure[0], \
        disclosure


def test_f12d_builder_cannot_represent_no_manifest_as_a_count():
    """The note builder directly: `None` (no manifest parsed) and `()` (a manifest that
    declares nothing) must produce visibly different notes, while the rules text -- which
    is a property of D3.5 and not of one run -- is identical in both. The absent case is
    expressed by `None` rather than by a scope label on purpose: a mislabelled empty
    listing is the one way this disclosure could lie reassuringly, and passing `None` is
    the only way to produce the UNKNOWN shape."""
    absent = _f12_gates._d8_external_declaration_note(None)
    empty = _f12_gates._d8_external_declaration_note(())
    listed = _f12_gates._d8_external_declaration_note(
        (("billing", "audit_log"), ("membership", "audit_log")))
    for note in (absent, empty, listed):
        assert "DECLARATION, NOT OBSERVATION" in note, note
        assert "identity is that PAIR, never the bare name" in note, note
        assert "GATE2-R1-F12-D8-EXTERNAL-NAMES-2026-10-05" in note, note
        # None of the three borrows the coverage disclosure's reserved vocabulary, nor the
        # three counters' scan-progress labels, which make a claim this note does not.
        for marker in ("NOT_STARTED", "PARTIAL", "LOWER BOUND", "NOT FINAL"):
            assert marker not in note, (marker, note)
    assert "NOT STARTED" in absent, absent
    assert "UNKNOWN" in absent, absent
    assert "complete for this run" not in absent, absent
    assert "0 declared entry/ies" not in absent, absent
    for note in (empty, listed):
        assert "NOT STARTED" not in note, note
        assert "UNKNOWN" not in note, note
        assert "complete for this run" in note, note
    assert "0 declared entry/ies across 0 declaring module(s) -- none" in empty, empty
    assert ("2 declared entry/ies across 2 declaring module(s) -- billing:audit_log, "
            "membership:audit_log") in listed, listed


def test_f12d_inventory_builder_sorts_and_keeps_every_declaration():
    """`_declared_external_inventory` over hand-built entries: sorted by (module, name),
    every duplicate kept, and modules declaring nothing contributing nothing. Asserted on
    the pure function as well as through the report so a future caller cannot reintroduce
    dedup or manifest-order dependence without breaking here."""
    modules = {
        "membership": _attr_entry("membership", prefixes=["mem_"],
                                  ext_refs=["zz_other", "audit_log", "audit_log"]),
        "billing": _attr_entry("billing", prefixes=["bil_"], ext_refs=["audit_log"]),
        "access": _attr_entry("access", prefixes=["acc_"]),
    }
    assert _f12_gates._declared_external_inventory(modules) == (
        ("billing", "audit_log"),
        ("membership", "audit_log"),
        ("membership", "audit_log"),
        ("membership", "zz_other"),
    ), _f12_gates._declared_external_inventory(modules)
    # Insertion order must not matter.
    reordered = {name: modules[name] for name in ("membership", "access", "billing")}
    assert (_f12_gates._declared_external_inventory(reordered)
            == _f12_gates._declared_external_inventory(modules))
    # A manifest with no declarations anywhere is the empty inventory, never `None`.
    assert _f12_gates._declared_external_inventory(
        {"access": _attr_entry("access", prefixes=["acc_"])}) == ()


def test_f12d_disclosure_changed_no_verdict_no_code_and_no_exit_code():
    """The regression guard this increment's "disclosure only" claim rests on. Each fixture
    pins status, exit code and code set alongside its inventory, so a disclosure that had
    quietly reclassified an outcome -- or made a declared entry behave like an exemption,
    which is exactly what D3.5/D9 forbid -- would fail here even though its own listing
    looked plausible."""
    cases = [
        ("X = 1\n", PASS, 0, set(), _F12D_FULL),
        ('Q = "SELECT a FROM mem_roster"\n', PASS, 0, set(), _F12D_FULL),
        ('Q = "SELECT a FROM audit_log"\n', PASS, 0, set(), _F12D_FULL),
        ('Q = "SELECT a FROM bil_invoices"\n', FAIL, 1, {"CROSS_DOMAIN_SQL_IMPORT"},
         _F12D_FULL),
        ('Q = "SELECT a FROM nobody_owns"\n', ERROR, 2, {"MODULE_DEPS_TABLE_UNATTRIBUTED"},
         _F12D_FULL),
    ]
    for source, status, exit_code, codes, inventory in cases:
        report = _f12d_run({"queries.py": source})
        assert report.status == status, (source, report.render())
        assert report.exit_code == exit_code, (source, report.render())
        assert report.codes() == codes, (source, report.render())
        assert _f12d_inventory(report) == inventory, (source, report.render())
        # Every run carries the disclosure exactly once, whatever its verdict.
        assert len([n for n in report.notes
                    if "ADR-011 D3.5/D8 declared external_table_references inventory" in n]) == 1, \
            (source, report.render())


def test_f12d_disclosure_did_not_wire_cte_state_3_or_disturb_the_other_counters():
    """Scope guard, as every increment in this file carries: listing declarations must not
    have wired D3.2 state 3 into the live scanning path, nor moved the three counters
    beside it. A `WITH`-bound name is still an unattributed ERROR with a CTE count of 0,
    and a clean run still reports its own trigger, table-reference and import-edge
    figures."""
    report = _f12d_run({"service.py": f'Q = "{_F12B_CTE}"\n'})
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert "MODULE_DEPS_TABLE_UNATTRIBUTED" in report.codes(), report.render()
    assert _f12b_counts(report)["cte"] == 0, report.render()
    assert _f12d_inventory(report) == _F12D_FULL, report.render()

    clean = _f12d_run({"queries.py": 'Q = "SELECT a FROM audit_log"\n'})
    assert clean.status == PASS, clean.render()
    assert any("remains unimplemented" in n for n in clean.notes), clean.render()
    for marker in ("ADR-011 D8 SQL-trigger inspection",
                   "ADR-011 D8 table-reference attribution",
                   "ADR-011 D8 cross-module import edges"):
        assert len([n for n in clean.notes if marker in n]) == 1, (marker, clean.render())
    assert _f12c_counts(clean) == _F12C_ZERO, clean.render()


# --- R1-F12 / ADR-011 D6.3 + D8 (GATE2-R1-F12-D8-ZERO-TABLE-COUNTER-2026-10-05) ---
#
# The gap this increment closes is a conflation, not a missing number. On the report's
# two existing SQL surfaces a clean `SELECT 1` and a fail-closed
# `MODULE_DEPS_SOURCE_UNINSPECTABLE` refusal look identical: one recognised subject in
# the trigger note, zero attributed references in the table-reference note, either way.
# ADR-011 D6.3 says those are opposite outcomes -- a triggered subject with no table
# position at all is clean (an unqualified "triggered but zero references => ERROR"
# rule would flag the most common operational SQL in existence), while a subject that
# implies a table position it could not resolve is ERROR at exit 2.
#
# So the discipline here is opposition on the *classification*, not merely on zero
# versus nonzero. Every test below pins the clean figure together with the two
# unresolved figures, because a counter that rises on both classes would satisfy any
# "nonzero on SELECT 1" assertion while making the disclosure a lie in the reassuring
# direction -- the one direction this gate may never fail in. The partition is also
# reconciled against the two existing counters in the same run, so a figure that
# agreed with itself while disagreeing with the rest of the report fails here.

_F12E_CLEAN = "SELECT 1"                 # D6.3 clean zero-table: no table position
_F12E_CLEAN_FN = "SELECT now()"          # likewise, via a function call
_F12E_CLEAN_ANALYZE = "ANALYZE"          # likewise, a bare maintenance statement
_F12E_CLEAN_VACUUM = "VACUUM"            # likewise
_F12E_DANGLING = "SELECT a FROM "        # table position present, name unreachable
# TRUNCATE, COPY and the GRANT/REVOKE object-clause `ON` now each yield a
# recognised position even when targetless, so all three count as dangling rather
# than implied. The live bare-form I-1 backstop control is the GRANT/REVOKE `ON`
# form whose object is NOT a table target: `_has_bare_table_verb_form`'s
# GRANT/REVOKE disjunct is deliberately still unconditional
# (GATE2-R2-N01-D67-GRANT-REVOKE-ON-2026-10-06), so that form keeps exactly the
# implied-class I-1 refusal `GRANT SELECT ON` carried here before that increment --
# same class, same disjunct, same ERROR. Keep both classes exercised separately.
_F12E_DANGLING_COPY = "COPY"            # recognised COPY signal, no target
_F12E_DANGLING_GRANT_ON = "GRANT SELECT ON"   # recognised ON signal, no target
_F12E_IMPLIED = "GRANT USAGE ON SCHEMA mem_s TO r"   # D6.3 I-1 backstop
_F12E_DANGLING_TRUNCATE = "TRUNCATE"     # recognised TRUNCATE signal, no target

_F12E_ZERO = {"recognised": 0, "clean": 0, "unresolved": 0, "dangling": 0,
              "implied": 0, "with_tables": 0}

# Deliberately the table-state section's own scaffold and manifest rather than a fourth
# near-copy: the fixtures below need exactly what it already provides (a scaffold with no
# trigger verb anywhere, so every nonzero figure is the fixture's own, plus the `mem_`
# ownership and `audit_log` declaration the cross-check assertions reuse). Reusing it also
# means the partition and the counters it is reconciled against are measured over the
# identical tree, which is the whole point of those assertions.
_f12e_run = _f12b_run


def _f12e_note(report):
    notes = [n for n in report.notes
             if "ADR-011 D6.3/D8 zero-table triggered statements" in n]
    assert len(notes) == 1, report.render()
    return notes[0]


def _f12e_between(note, before, after):
    assert before in note, (before, note)
    tail = note.split(before, 1)[1]
    assert after in tail, (after, note)
    return int(tail.split(after, 1)[0].strip())


def _f12e_counts(report):
    """The six figures parsed out of the disclosure note itself, so every assertion below
    reads the numbers a human reader of the report would read -- never a separately
    recomputed figure that could agree with the code while the report lies."""
    note = _f12e_note(report)
    return {
        "recognised": _f12e_between(note, "zero-table triggered statements: of ",
                                    " recognised subject(s)"),
        "clean": _f12e_between(note, " recognised subject(s), ",
                               " carried no table position"),
        "unresolved": _f12e_between(
            note, "clean (SELECT 1, SELECT now(), a bare ANALYZE or VACUUM), ",
            " yielded no usable table identifier"),
        "dangling": _f12e_between(note, "and are ERROR -- ",
                                  " refused by the dangling-keyword rule"),
        "implied": _f12e_between(note, "refused by the dangling-keyword rule and ",
                                 " by the D6.3 I-1 backstop"),
        "with_tables": _f12e_between(note, "and the remaining ",
                                     " reduced to at least one"),
    }


def test_f12e_select_one_fixture_reports_a_nonzero_clean_zero_table_count():
    """The positive control and the increment's reason to exist: a clean verdict over
    `SELECT 1` must now evidence that the scanner examined a real statement and found no
    table position -- D6.3's clean case -- rather than leaving it indistinguishable from
    a refusal. The two unresolved figures must stay 0 in the same breath, since a
    counter that rose on both classes would satisfy the nonzero assertion while
    reporting a fail-closed refusal as a clean success."""
    report = _f12e_run({"service.py": f'Q = "{_F12E_CLEAN}"\n'})
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    assert report.violations == [], report.render()
    assert _f12e_counts(report) == {**_F12E_ZERO, "recognised": 1, "clean": 1}, \
        report.render()
    # The existing two counters' own view of the same subject, unchanged: recognised,
    # and attributed nothing -- which is exactly the pair the new figure disambiguates.
    assert _f12_count(report) == 1, report.render()
    assert _f12b_counts(report) == _F12B_ZERO, report.render()
    assert _f12b_total(report) == 0, report.render()


def test_f12e_every_table_free_statement_shape_counts_clean_not_unresolved():
    """D6.3 names more than one shape of table-free statement, and the rule is worthless
    if it holds for only the one in the note's own example. `SELECT now()` and the bare
    `ANALYZE`/`VACUUM` maintenance statements must each count clean on their own, so no
    shape is quietly landing in an ERROR class while the aggregate still looks right."""
    for label, text in (("function call", _F12E_CLEAN_FN),
                        ("bare ANALYZE", _F12E_CLEAN_ANALYZE),
                        ("bare VACUUM", _F12E_CLEAN_VACUUM)):
        report = _f12e_run({"service.py": f'Q = "{text}"\n'})
        assert report.status == PASS, (label, report.render())
        assert report.exit_code == 0, (label, report.render())
        assert report.violations == [], (label, report.render())
        assert _f12e_counts(report) == {**_F12E_ZERO, "recognised": 1, "clean": 1}, \
            (label, report.render())


def test_f12e_own_table_fixture_reports_a_zero_clean_count():
    """The negative control that makes the positive one mean something: a real own-table
    query is not a zero-table statement, so the clean figure must be 0 while the
    table-bearing figure is 1. Without this a counter hardwired positive -- or one
    incremented for every recognised subject -- would pass the test above."""
    report = _f12e_run({"service.py": f'Q = "{_F12B_OWN}"\n'})
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    assert report.violations == [], report.render()
    assert _f12e_counts(report) == {**_F12E_ZERO, "recognised": 1, "with_tables": 1}, \
        report.render()
    # And the reference really was attributed, so the table-bearing figure is not a
    # relabelling of an unexamined subject.
    assert _f12b_counts(report) == {**_F12B_ZERO, "own": 1}, report.render()
    assert _f12b_total(report) == 1, report.render()


def test_f12e_trivial_assignment_reports_zero_clean_rather_than_a_free_success():
    """The inflation control at the other end: a tree the trigger never fired on must
    report 0 everywhere, not a clean zero-table success. `X = 1` is genuinely
    uninspected -- the one shape the note's RESIDUAL calls out -- and a counter that
    credited it would turn "no SQL here" into "SQL examined and found table-free"."""
    report = _f12e_run({"service.py": "X = 1\n"})
    assert report.status == PASS, report.render()
    assert _f12e_counts(report) == _F12E_ZERO, report.render()
    assert _f12_count(report) == 0, report.render()
    note = _f12e_note(report)
    assert "of 0 recognised subject(s), 0 carried no table position" in note, note
    assert "genuinely uninspected rather than inspected-and-table-free" in note, note


def test_f12e_dangling_and_i1_backstop_subjects_never_inflate_the_clean_count():
    """The finding this increment exists to make impossible, asserted directly. A
    dangling table-position keyword and an I-1 backstop hit are both zero-extraction
    subjects, and both are ERROR at exit 2 -- so each must land in its own unresolved
    figure with the clean figure still 0. Each shape is run alone, because an aggregate
    over all three at once could hide one of them inside another's count."""
    cases = (
        ("dangling keyword", _F12E_DANGLING, {"dangling": 1}),
        # A bare-verb signal that now *is* recognised, so its unresolved position
        # lands in the dangling figure rather than the I-1 one. The classification
        # moved; the ERROR did not (GATE2-R2-N01-D67-TRUNCATE-BARE-VERB-SIGNAL-
        # 2026-10-06), which is the direction D6.7.2 requires.
        ("dangling TRUNCATE signal", _F12E_DANGLING_TRUNCATE, {"dangling": 1}),
        ("dangling COPY signal", _F12E_DANGLING_COPY, {"dangling": 1}),
        # Same move, same direction, for the last bare-verb family
        # (GATE2-R2-N01-D67-GRANT-REVOKE-ON-2026-10-06): a targetless GRANT object
        # clause is now a recognised-but-unresolved position, so it lands in the
        # dangling figure where it used to land in the I-1 one. The ERROR did not
        # move.
        ("dangling GRANT ... ON signal", _F12E_DANGLING_GRANT_ON, {"dangling": 1}),
        ("GRANT ... ON non-table object I-1", _F12E_IMPLIED, {"implied": 1}),
    )
    for label, text, expected in cases:
        report = _f12e_run({"service.py": f'Q = "{text}"\n'})
        # Verdict, code and exit code are the pre-increment ones, unchanged.
        assert report.status == ERROR, (label, report.render())
        assert report.exit_code == 2, (label, report.render())
        assert report.codes() == {"MODULE_DEPS_SOURCE_UNINSPECTABLE"}, \
            (label, report.render())
        assert "PASS" not in report.render(), (label, report.render())
        counts = _f12e_counts(report)
        assert counts["clean"] == 0, (label, report.render())
        assert counts["unresolved"] == 1, (label, report.render())
        assert counts == {**_F12E_ZERO, "recognised": 1, "unresolved": 1, **expected}, \
            (label, report.render())
        # And the report says plainly that these are not clean zero-table successes.
        note = _f12e_note(report)
        assert ("including every dangling-keyword and I-1 backstop case" in note), note
        assert "never be read as a clean zero-table success" in note, note


def test_f12e_the_two_unresolved_classes_are_told_apart_not_merged():
    """Both ERROR classes in one run, which is the only way to prove they are separate
    figures rather than one figure reported twice. A single `unresolved` counter would
    satisfy every assertion in the test above and still lose which of D6.3's two rules
    fired -- the distinction a reader needs to know whether the name was concatenated in
    or the statement shape itself was unresolvable."""
    report = _f12e_run({"service.py": "\n".join([
        f'A = "{_F12E_DANGLING}"',
        f'B = "{_F12E_IMPLIED}"',
        f'C = "{_F12E_CLEAN}"',
        "",
    ])})
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_SOURCE_UNINSPECTABLE"}, report.render()
    assert _f12e_counts(report) == {"recognised": 3, "clean": 1, "unresolved": 2,
                                    "dangling": 1, "implied": 1,
                                    "with_tables": 0}, report.render()
    # The clean subject in the same run is still counted clean: one unresolvable
    # statement elsewhere in a file must not retroactively taint it.
    assert _f12_count(report) == 3, report.render()
    assert _f12b_total(report) == 0, report.render()


def test_f12e_partition_reconciles_with_the_trigger_and_table_state_counts():
    """The reconciliation claim the note makes, tested rather than asserted in prose. One
    run carrying all four classes at once: the four figures must sum to the recognised
    count, that sum must equal the SQL-trigger note's own figure, and the table-bearing
    figure must be the subject count behind the table-reference note's identifier total.
    A counter incremented on the wrong return path would still look internally
    consistent here and would break this."""
    report = _f12e_run({"service.py": "\n".join([
        f'A = "{_F12E_CLEAN}"',          # clean
        f'B = "{_F12E_CLEAN_ANALYZE}"',  # clean
        f'C = "{_F12E_DANGLING}"',       # unresolved: dangling
        f'D = "{_F12E_IMPLIED}"',        # unresolved: non-table GRANT/ON, I-1 backstop
        f'E = "{_F12B_OWN}"',            # table-bearing, state 1
        f'F = "{_F12B_OTHER}"',          # table-bearing, state 2
        "",
    ])})
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT",
                              "MODULE_DEPS_SOURCE_UNINSPECTABLE"}, report.render()
    counts = _f12e_counts(report)
    assert counts == {"recognised": 6, "clean": 2, "unresolved": 2, "dangling": 1,
                      "implied": 1, "with_tables": 2}, report.render()
    # (a) the four figures partition the recognised count with no remainder
    assert (counts["clean"] + counts["dangling"] + counts["implied"]
            + counts["with_tables"]) == counts["recognised"], report.render()
    # (b) and that recognised count is the SQL-trigger note's own figure
    assert _f12_count(report) == counts["recognised"], report.render()
    # (c) and the table-bearing figure is the subject count behind the identifier total
    assert _f12b_counts(report) == {**_F12B_ZERO, "own": 1, "other": 1}, report.render()
    assert _f12b_total(report) == 2, report.render()
    assert _f12b_total(report) >= counts["with_tables"], report.render()


# --- GATE2-R1-F12-D8-STATEMENT-SUBJECTS-2026-10-06: per-statement D8 accounting -----
#
# The granularity limit the three tests above this comment used to pin -- "one .sql file
# is one subject, so `SELECT 1; SELECT now()` counts 1 clean and not 2" -- is what this
# increment removes. The figures are now literal per-statement accounting, cut at
# lexically certain top-level `;` boundaries, so the tests below assert the counts the
# superseded test asserted the *absence* of.
#
# Each is paired against a falsely-splitting implementation as much as against the
# pre-increment one: a splitter that cut on `";"` textually would satisfy the first two
# tests and break the three lexical-region tests, while a splitter that never cut would
# satisfy those three and break the first two. The decline test is the fail-closed half
# -- a segment carrying a table position with no trigger verb of its own must keep its
# ERROR rather than become a clean statement.
_F12E_SELECT_ID_OWN = "SELECT id FROM mem_roster"   # own-table, D3.2 state 1


def test_f12e_two_table_free_statements_in_one_sql_file_count_as_two_clean():
    """`SELECT 1; SELECT now()` is two statements and must now report 2 recognised /
    2 clean, where the pre-increment scanner reported 1/1. The trigger count is asserted
    alongside, because the zero-table partition is defined to sum to it -- a change that
    moved one figure without the other would make the two notes disagree."""
    report = _f12e_run({"queries.sql": f"{_F12E_CLEAN}; {_F12E_CLEAN_FN}"})
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    assert report.violations == [], report.render()
    assert _f12e_counts(report) == {**_F12E_ZERO, "recognised": 2, "clean": 2}, \
        report.render()
    assert _f12_count(report) == 2, report.render()
    # No table position anywhere, so the identifier note stays at a genuine zero.
    assert _f12b_counts(report) == _F12B_ZERO, report.render()

    # A trailing `;` and the newlines a real file carries change nothing: the empty/
    # whitespace segment after the final cut holds no trigger verb and no table
    # position, so it is dropped rather than counted as a third statement.
    terminated = _f12e_run({"queries.sql": f"{_F12E_CLEAN};\n{_F12E_CLEAN_FN};\n"})
    assert terminated.status == PASS, terminated.render()
    assert _f12e_counts(terminated) == {**_F12E_ZERO, "recognised": 2, "clean": 2}, \
        terminated.render()


def test_f12e_a_mixed_sql_file_counts_one_clean_statement_and_one_table_bearing():
    """`SELECT 1; SELECT id FROM mem_roster` must now report 2 recognised / 1 clean /
    1 table-bearing, where the pre-increment scanner reported 1/0/1 -- the table-bearing
    whole swallowing the clean statement. The identifier total stays 1: segmentation
    changes how subjects are counted, never how many identifier occurrences were
    extracted or which state they reached."""
    report = _f12e_run({"queries.sql": f"{_F12E_CLEAN}; {_F12E_SELECT_ID_OWN}"})
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    assert report.violations == [], report.render()
    assert _f12e_counts(report) == {**_F12E_ZERO, "recognised": 2, "clean": 1,
                                    "with_tables": 1}, report.render()
    assert _f12_count(report) == 2, report.render()
    assert _f12b_counts(report) == {**_F12B_ZERO, "own": 1}, report.render()
    assert _f12b_total(report) == 1, report.render()
    # The partition still sums to the trigger count, which is the claim the two notes
    # reconcile on and the one a mis-placed increment would break.
    counts = _f12e_counts(report)
    assert (counts["clean"] + counts["dangling"] + counts["implied"]
            + counts["with_tables"]) == counts["recognised"], report.render()


def test_f12e_a_semicolon_inside_a_quoted_literal_is_not_a_statement_boundary():
    """A `;` inside a single-quoted string literal, and one inside a double-quoted
    identifier, are data -- not boundaries. Each case is one statement, so a textual
    `";"` split would report 2 here and would also have cut a real identifier in half."""
    literal = _f12e_run({"queries.sql": "SELECT 'a;b' FROM mem_roster"})
    assert literal.status == PASS, literal.render()
    assert _f12e_counts(literal) == {**_F12E_ZERO, "recognised": 1, "with_tables": 1}, \
        literal.render()
    assert _f12b_counts(literal) == {**_F12B_ZERO, "own": 1}, literal.render()

    quoted_ident = _f12e_run({"queries.sql": 'SELECT a FROM "mem_od;d"'})
    assert quoted_ident.status == PASS, quoted_ident.render()
    assert _f12e_counts(quoted_ident) == {**_F12E_ZERO, "recognised": 1,
                                          "with_tables": 1}, quoted_ident.render()
    assert _f12b_counts(quoted_ident) == {**_F12B_ZERO, "own": 1}, quoted_ident.render()


def test_f12e_a_semicolon_inside_a_comment_is_not_a_statement_boundary():
    """A `;` inside a `--` line comment and one inside a `/* */` block comment are both
    skipped atomically, so neither cuts the statement that encloses it. Asserted as one
    clean statement each rather than two."""
    line = _f12e_run({"queries.sql": f"{_F12E_CLEAN} -- note; still the same statement\n"})
    assert line.status == PASS, line.render()
    assert _f12e_counts(line) == {**_F12E_ZERO, "recognised": 1, "clean": 1}, \
        line.render()

    block = _f12e_run({"queries.sql": f"{_F12E_CLEAN} /* note; still one */"})
    assert block.status == PASS, block.render()
    assert _f12e_counts(block) == {**_F12E_ZERO, "recognised": 1, "clean": 1}, \
        block.render()


def test_f12e_a_semicolon_inside_a_dollar_quoted_body_is_not_a_statement_boundary():
    """A PostgreSQL dollar-quoted body is exactly where `;` characters legitimately
    appear inside one statement, so the whole `$$ ... $$` region is skipped atomically
    and the statements inside it are never cut out as top-level subjects. One statement,
    counted once -- a textual split would report three."""
    report = _f12e_run({
        "queries.sql": "DO $$ BEGIN SELECT 1; SELECT 2; END $$",
    })
    assert report.status == PASS, report.render()
    assert report.violations == [], report.render()
    assert _f12e_counts(report) == {**_F12E_ZERO, "recognised": 1, "clean": 1}, \
        report.render()
    assert _f12_count(report) == 1, report.render()

    # Tagged form, and with a trailing top-level `;`: still one statement.
    tagged = _f12e_run({
        "queries.sql": "DO $fn$ BEGIN SELECT 1; SELECT 2; END $fn$;\n",
    })
    assert tagged.status == PASS, tagged.render()
    assert _f12e_counts(tagged) == {**_F12E_ZERO, "recognised": 1, "clean": 1}, \
        tagged.render()


def test_f12e_segmentation_declines_rather_than_losing_a_dangling_keyword_refusal():
    """The fail-closed half. A cut segment carrying a table position with no trigger verb
    of its own (`FROM`) would return early at the trigger if scanned alone, losing the
    dangling-keyword ERROR the pre-increment whole-text scan makes -- so segmentation is
    declined and the text stays the one coarse subject it was. ERROR at exit 2, counted
    as one unresolved subject and never as a clean statement, which is the direction this
    increment may never fail in."""
    report = _f12e_run({"queries.sql": f"{_F12E_CLEAN}; FROM\n"})
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_SOURCE_UNINSPECTABLE"}, report.render()
    assert "PASS" not in report.render(), report.render()
    assert _f12e_counts(report) == {**_F12E_ZERO, "recognised": 1, "unresolved": 1,
                                    "dangling": 1}, report.render()
    assert _f12_count(report) == 1, report.render()


def test_f12e_the_statement_granularity_limit_and_its_decline_rule_are_disclosed():
    """The granularity claim, pinned so the disclosure cannot drift from the behaviour.
    The note must now say the figures count SQL statements cut at lexically certain
    top-level semicolon boundaries, and must still disclose the decline rule -- the
    remaining limit -- rather than claiming unconditional statement segmentation."""
    note = _f12e_note(_f12e_run({"queries.sql": f"{_F12E_CLEAN}; {_F12E_CLEAN_FN}"}))
    assert "every figure here counts SQL STATEMENTS" in note, note
    assert "lexically certain top-level semicolon boundaries" in note, note
    assert "GATE2-R1-F12-D8-STATEMENT-SUBJECTS-2026-10-06" in note, note
    assert "contributes 10 to the clean figure rather than 1" in note, note
    assert "Where the cut is NOT lexically certain segmentation is DECLINED" in note, note
    assert "Every decline errs in the fail-closed direction" in note, note
    # The superseded claim must be gone, not merely supplemented.
    assert "implements no SQL-statement segmentation" not in note, note
    assert "real per-statement segmentation remains unimplemented" not in note, note


def test_f12e_abort_during_the_scan_labels_the_counts_not_final():
    """An abort *inside* the per-file scan: the figures are whatever real inspection had
    established, so they must be labelled NOT FINAL rather than read as totals.
    `membership/a_query.py` sorts before the unparseable `membership/z_broken.py`, so a
    genuine clean zero-table subject is counted before the abort -- an all-zero count
    here would not discriminate between the two abort shapes."""
    report = _f12e_run({
        "a_query.py": f'Q = "{_F12E_CLEAN}"\n',
        "z_broken.py": "def broken(:\n",
    })
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, report.render()
    assert _f12e_counts(report) == {**_F12E_ZERO, "recognised": 1, "clean": 1}, \
        report.render()
    note = _f12e_note(report)
    assert "NOT FINAL" in note, note
    assert "aborted during the per-file scan" in note, note
    assert "a minimum established by real inspection, not a total" in note, note
    assert "complete for this run" not in note, note
    assert "NOT STARTED" not in note, note
    # D5.5's reserved coverage vocabulary stays unborrowed for this different claim.
    assert "LOWER BOUND" not in note, note
    assert "PARTIAL" not in note, note


def test_f12e_abort_before_the_scan_labels_the_counts_not_started_not_a_clean_zero():
    """An abort *upstream* of the per-file scan (an absent --modules-dir): nothing was
    ever recognised, so the zeros must record that no inspection happened rather than
    that the tree holds no table-free statement. Collapsing this into NOT FINAL would
    make the two aborts indistinguishable; collapsing it into the complete label would
    state a total this run never established."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        manifest_path = root / "module-manifest.json"
        manifest_path.write_text(json.dumps(_md_manifest(_F12B_MODULES)))
        report = run_module_deps_gate(root / "app" / "modules", manifest_path)
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, report.render()
    assert "PASS" not in report.render(), report.render()
    assert _f12e_counts(report) == _F12E_ZERO, report.render()
    note = _f12e_note(report)
    assert "NOT STARTED" in note, note
    assert "aborted before the per-file scan" in note, note
    assert "never that the tree holds no zero-table statement" in note, note
    assert "NOT FINAL" not in note, note
    assert "complete for this run" not in note, note
    # The coverage pass's own vocabulary stays unborrowed, so the D5 absent-root test's
    # assertions over *every* note continue to hold with this note present.
    assert "NOT_STARTED" not in note, note
    assert "PARTIAL" not in note, note
    assert "LOWER BOUND" not in note, note


def test_f12e_zero_table_disclosure_reaches_both_cli_surfaces():
    """Driven through `main` so the text renderer and the `--json` serialiser are each
    exercised for real, with the exit code asserted rather than inferred. A disclosure
    that existed only on one surface would leave the other unable to tell a clean
    zero-table statement from a refusal."""
    def write_tree(root):
        modules_dir = _md_tree(root)
        _md_module(modules_dir, "membership", {"service.py": f'Q = "{_F12E_CLEAN}"\n'})
        _md_module(modules_dir, "billing",
                   {"interface.py": "def preview_charge(member):\n    return None\n"})
        manifest_path = root / "module-manifest.json"
        _md_write_manifest(modules_dir, manifest_path, _F12B_MODULES)
        return ["--gate", "module-deps", "--modules-dir", str(modules_dir),
                "--module-manifest", str(manifest_path)]

    expected = "of 1 recognised subject(s), 1 carried no table position at all and are clean"
    with tempfile.TemporaryDirectory() as tmp:
        code, out = _cli(write_tree(Path(tmp)))
    assert code == 0, out
    assert "[module-deps] PASS" in out, out
    assert "ADR-011 D6.3/D8 zero-table triggered statements" in out, out
    assert expected in out, out
    assert "the counts are complete for this run" in out, out

    with tempfile.TemporaryDirectory() as tmp:  # a fresh tree: `_md_tree` creates `app/`
        json_code, json_out = _cli(write_tree(Path(tmp)) + ["--json"])
    assert json_code == 0, json_out
    payload = json.loads(json_out)
    assert payload["status"] == PASS, payload
    assert payload["violations"] == [], payload
    disclosure = [n for n in payload["notes"]
                  if "ADR-011 D6.3/D8 zero-table triggered statements" in n]
    assert len(disclosure) == 1, payload
    assert expected in disclosure[0], disclosure
    assert "RECONCILIATION: the four figures partition" in disclosure[0], disclosure
    assert "LIMIT -- every figure here counts SQL STATEMENTS" in disclosure[0], disclosure
    assert "RESIDUAL: text the scanner never received" in disclosure[0], disclosure


def test_f12e_note_builder_scopes_are_distinct_and_an_unknown_scope_fails_closed():
    """The three labels must actually differ, so a partial or never-started set of
    figures can never be read as totals (and vice versa), while the figures, the limit
    and the residual stay identical across all three. An unrecognised scope raises rather
    than falling back to the most reassuring label -- a future caller that mislabels a
    run must break loudly instead of under-disclosing."""
    counts = _f12_gates._ZeroTableCounts(clean=3, dangling=2, implied=1, with_tables=4)
    assert counts.unresolved == 3, counts
    assert counts.recognised == 10, counts
    complete = _f12_gates._d8_zero_table_note(counts)
    partial = _f12_gates._d8_zero_table_note(counts, _f12_gates._D8_SCOPE_PARTIAL)
    not_started = _f12_gates._d8_zero_table_note(_f12_gates._ZeroTableCounts(),
                                                 _f12_gates._D8_SCOPE_NOT_STARTED)
    for note in (complete, partial, not_started):
        assert "LIMIT -- every figure here counts SQL STATEMENTS" in note, note
        assert "RESIDUAL: text the scanner never received" in note, note
        assert "GATE2-R1-F12-D8-ZERO-TABLE-COUNTER-2026-10-05" in note, note
        # None of the three borrows the coverage disclosure's reserved vocabulary, and
        # none of them ever prints a verdict token.
        assert "LOWER BOUND" not in note, note
        assert "PARTIAL" not in note, note
        assert "NOT_STARTED" not in note, note
        assert "PASS" not in note, note
    for note in (complete, partial):
        assert "of 10 recognised subject(s), 3 carried no table position" in note, note
        assert "3 yielded no usable table identifier and are ERROR" in note, note
        assert "2 refused by the dangling-keyword rule and 1 by the D6.3 I-1" in note, note
        assert "the remaining 4 reduced to at least one" in note, note
    assert "the counts are complete for this run" in complete, complete
    assert "NOT FINAL" not in complete, complete
    assert "NOT STARTED" not in complete, complete
    assert "NOT FINAL" in partial, partial
    assert "NOT STARTED" not in partial, partial
    assert "NOT STARTED" in not_started, not_started
    assert "NOT FINAL" not in not_started, not_started
    assert "of 0 recognised subject(s), 0 carried no table position" in not_started, \
        not_started
    for note in (partial, not_started):
        assert "complete for this run" not in note, note
    try:
        _f12_gates._d8_zero_table_note(counts, "whatever")
    except ValueError as exc:
        assert "unknown ADR-011 D6.3/D8 zero-table-note scope" in str(exc), exc
    else:
        raise AssertionError("an unknown scope must raise rather than mislabel the counts")


def test_f12e_counter_changed_no_verdict_no_code_and_no_exit_code():
    """The regression guard this increment's "disclosure only" claim rests on. Each
    fixture pins status, exit code and code set alongside its partition, so a counter
    that had quietly reclassified an outcome -- most dangerously, turning an I-1 backstop
    ERROR into a clean zero-table success -- would fail here even though its own figures
    looked plausible."""
    cases = [
        ("X = 1\n", PASS, 0, set(), _F12E_ZERO),
        (f'Q = "{_F12E_CLEAN}"\n', PASS, 0, set(),
         {**_F12E_ZERO, "recognised": 1, "clean": 1}),
        (f'Q = "{_F12B_OWN}"\n', PASS, 0, set(),
         {**_F12E_ZERO, "recognised": 1, "with_tables": 1}),
        (f'Q = "{_F12B_OTHER}"\n', FAIL, 1, {"CROSS_DOMAIN_SQL_IMPORT"},
         {**_F12E_ZERO, "recognised": 1, "with_tables": 1}),
        (f'Q = "{_F12B_UNATTRIBUTED}"\n', ERROR, 2, {"MODULE_DEPS_TABLE_UNATTRIBUTED"},
         {**_F12E_ZERO, "recognised": 1, "with_tables": 1}),
        (f'Q = "{_F12E_DANGLING}"\n', ERROR, 2, {"MODULE_DEPS_SOURCE_UNINSPECTABLE"},
         {**_F12E_ZERO, "recognised": 1, "unresolved": 1, "dangling": 1}),
        (f'Q = "{_F12E_IMPLIED}"\n', ERROR, 2, {"MODULE_DEPS_SOURCE_UNINSPECTABLE"},
         {**_F12E_ZERO, "recognised": 1, "unresolved": 1, "implied": 1}),
    ]
    for source, status, exit_code, codes, expected in cases:
        report = _f12e_run({"queries.py": source})
        assert report.status == status, (source, report.render())
        assert report.exit_code == exit_code, (source, report.render())
        assert report.codes() == codes, (source, report.render())
        assert _f12e_counts(report) == expected, (source, report.render())
        # Every run carries the disclosure exactly once, whatever its verdict.
        assert len([n for n in report.notes
                    if "ADR-011 D6.3/D8 zero-table triggered statements" in n]) == 1, \
            (source, report.render())


def test_f12e_counter_did_not_wire_cte_state_3_or_disturb_the_other_disclosures():
    """Scope guard, as every increment in this file carries: partitioning the recognised
    subjects must not have wired D3.2 state 3 into the live scanning path, nor moved the
    disclosures beside it. A `WITH`-bound name is still an unattributed ERROR with a CTE
    count of 0 -- and, being table-bearing, contributes nothing to the clean figure --
    and a clean run still carries each of the four existing D8/D3.5 notes exactly once."""
    report = _f12e_run({"service.py": f'Q = "{_F12B_CTE}"\n'})
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_TABLE_UNATTRIBUTED"}, report.render()
    assert _f12b_counts(report)["cte"] == 0, report.render()
    assert _f12e_counts(report) == {**_F12E_ZERO, "recognised": 1, "with_tables": 1}, \
        report.render()

    clean = _f12e_run({"service.py": f'Q = "{_F12E_CLEAN}"\n'})
    assert clean.status == PASS, clean.render()
    for marker in ("ADR-011 D8 SQL-trigger inspection",
                   "ADR-011 D8 table-reference attribution",
                   "ADR-011 D8 cross-module import edges",
                   "ADR-011 D3.5/D8 declared external_table_references inventory",
                   "ADR-011 D6.3/D8 zero-table triggered statements"):
        assert len([n for n in clean.notes if marker in n]) == 1, (marker, clean.render())
    assert _f12c_counts(clean) == _F12C_ZERO, clean.render()
    assert any("remains unimplemented" in n for n in clean.notes), clean.render()


# --- R1-F12 / ADR-011 D8 (GATE2-R1-F12-D8-FILE-COUNTS-2026-10-05) -----------------
#
# D8's own list opens with "files inspected, inert, pruned by reason, and at the
# modules-root". Three of those four already existed but ONLY on the clean path -- they
# are appended after the error-class return -- so both ERROR shapes this gate can take
# went out with no file accounting at all, which is the condition D8 forbids
# unqualified by outcome. "Pruned by reason" existed nowhere: the D5 pass counted one
# undifferentiated aggregate over its top-level listing, and the recursive scan walk
# counted nothing.
#
# The discipline below is opposition on the two conflations this increment refuses,
# because either one would make the disclosure a lie rather than merely thin:
#
#   * a tree pruned ONLY at the top level must report zero recursive prunes and vice
#     versa, so neither figure can be a sum of both traversals (they cover disjoint
#     territory, and summing them would claim a tree-wide total neither establishes);
#   * a run that aborts mid-scan must report attempted > inspected, so the figure a
#     clean verdict's self-evidence rests on can never be the count of files the scan
#     merely committed to opening.
#
# And the same three-way scope discipline every D8 note in this file carries: a
# pre-scan abort says NOT STARTED with UNKNOWN in the slots no pass reached, never a
# fabricated complete zero; a mid-scan abort says NOT FINAL with the figures it really
# established.

_F12F_SQL = "SELECT a FROM mem_roster"       # own table: inspected and clean
_F12F_UNATTRIBUTED = "SELECT a FROM nobody_owns"  # D3.2 state 6 -> error-class ERROR


def _f12f_run(build_extra=None, modules=None):
    """A clean two-module scaffold whose every figure is predictable -- membership and
    billing, two files each, one modules-root file, no inert file and no pruned entry --
    plus whatever `build_extra(modules_dir)` adds on top. Nothing in the scaffold is
    inert or pruned, so every nonzero inert/prune figure below is the fixture's own."""
    def build(modules_dir):
        _md_module(modules_dir, "membership", {"service.py": f'Q = "{_F12F_SQL}"\n'})
        _md_module(modules_dir, "billing",
                   {"interface.py": "def charge():\n    return None\n"})
        if build_extra is not None:
            build_extra(modules_dir)

    return _md_run(_F12_MODULES if modules is None else modules, build)


def _f12f_note(report):
    notes = [n for n in report.notes if "ADR-011 D8 file accounting" in n]
    assert len(notes) == 1, report.render()
    return notes[0]


def _f12f_slot(note, before, after):
    """One count slot read out of the note itself, returned VERBATIM rather than coerced
    to an int -- the whole point of several assertions below is to tell the string "0"
    apart from the string "UNKNOWN", which an int-returning helper could not express."""
    assert before in note, (before, note)
    tail = note.split(before, 1)[1]
    assert after in tail, (after, note)
    return tail.split(after, 1)[0].strip()


_F12F_WALK_MARKER = "; recursive module/_shared scan walk: "


def _f12f_pair(segment):
    """The two by-reason prune figures inside one traversal's segment of the note."""
    head, _, tail = segment.partition(" '__pycache__' and ")
    assert tail, segment
    return (head.strip(),
            tail.split(" dot-prefixed directory prune(s)", 1)[0].strip())


def _f12f_counts(report):
    """Every figure parsed out of the disclosure note itself, so each assertion reads
    the numbers a human reader of the report would read -- never a separately recomputed
    figure that could agree with the code while the report lies."""
    note = _f12f_note(report)
    top_segment = note.split("immediate children: ", 1)[1].split(_F12F_WALK_MARKER, 1)[0]
    walk_segment = note.split(_F12F_WALK_MARKER, 1)[1]
    top = _f12f_pair(top_segment)
    walk = _f12f_pair(walk_segment)
    return {
        "inspected": _f12f_slot(note, "ADR-011 D8 file accounting: ",
                                " file(s) INSPECTED"),
        "attempted": _f12f_slot(note, "own analysis; ", " ATTEMPTED"),
        "inert": _f12f_slot(note, "checked list; ", " INERT file(s)"),
        "root": _f12f_slot(note, "(.md/.txt/.gitkeep); ",
                           " file(s) AT THE MODULES ROOT"),
        "top_pycache": top[0], "top_dot": top[1],
        "walk_pycache": walk[0], "walk_dot": walk[1],
    }


def _f12f_prune_tree(modules_dir, top_pycache=False, top_dot=False,
                     walk_pycache=False, walk_dot=False):
    """A pruning fixture with each of the four (traversal, reason) combinations switched
    on independently, which is what lets the tests below assert that no figure is a sum
    of another's territory."""
    if top_pycache:
        (modules_dir / "__pycache__").mkdir()
        (modules_dir / "__pycache__" / "root.pyc").write_text("")
    if top_dot:
        (modules_dir / ".tox").mkdir()
        (modules_dir / ".tox" / "junk.py").write_text("x = 1\n")
    if walk_pycache:
        (modules_dir / "membership" / "__pycache__").mkdir()
        (modules_dir / "membership" / "__pycache__" / "service.pyc").write_text("")
    if walk_dot:
        (modules_dir / "membership" / ".mypy_cache").mkdir()
        (modules_dir / "membership" / ".mypy_cache" / "cache.py").write_text("y = 1\n")


def test_f12f_zero_case_reports_real_zeros_beside_a_nonzero_inspected_count():
    """The zero case, and the control that makes every positive test below mean
    something. A clean tree with no inert file and no pruned entry must report those as
    explicit zeros -- not as absent figures, and not as UNKNOWN -- while the inspected,
    attempted and modules-root figures are the real nonzero counts, so no slot is
    hardwired either way. The note must carry no UNKNOWN at all on a complete run."""
    report = _f12f_run()
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    assert report.violations == [], report.render()
    assert _f12f_counts(report) == {
        # membership/{__init__,service}.py + billing/{__init__,interface}.py + the
        # modules-root __init__.py: five files opened and fully analysed, none inert.
        "inspected": "5", "attempted": "5", "inert": "0", "root": "1",
        "top_pycache": "0", "top_dot": "0", "walk_pycache": "0", "walk_dot": "0",
    }, report.render()
    note = _f12f_note(report)
    assert "the file counts are complete for this run" in note, note
    assert "UNKNOWN" not in note, note
    assert "NOT FINAL" not in note, note
    assert "NOT STARTED" not in note, note


def test_f12f_ordinary_files_are_counted_inspected_inert_and_at_the_modules_root():
    """The positive control for the three figures that previously existed on the clean
    path only: an inert file of each recognised shape is counted and never scanned, a
    nested `.py`, a `.sql` file and a second modules-root file are each inspected, and
    the modules-root figure counts the root bucket rather than the whole tree."""
    def extra(modules_dir):
        mem = modules_dir / "membership"
        (mem / "queries.sql").write_text(f"{_F12F_SQL};\n")
        (mem / "README.md").write_text("# notes\n")
        (mem / "notes.txt").write_text("notes\n")
        (mem / ".gitkeep").write_text("")
        (mem / "sub").mkdir()
        (mem / "sub" / "helper.py").write_text("def helper():\n    return None\n")
        (modules_dir / "top.py").write_text("X = 1\n")

    report = _f12f_run(extra)
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    assert _f12f_counts(report) == {
        # the five baseline files + queries.sql + sub/helper.py + top.py
        "inspected": "8", "attempted": "8",
        # .md, .txt and .gitkeep -- every recognised inert shape, none of them scanned
        "inert": "3", "root": "2",
        "top_pycache": "0", "top_dot": "0", "walk_pycache": "0", "walk_dot": "0",
    }, report.render()
    # The clean path's own long-standing figures must still agree with the new note
    # rather than quietly diverge from it.
    assert any(n == "3 inert file(s)" for n in report.notes), report.render()
    assert any(n == "8 inspected file(s)" for n in report.notes), report.render()
    assert len(report.checked) == 8, report.render()


def test_f12f_each_prune_reason_is_counted_in_its_own_traversal_and_its_own_slot():
    """All four (traversal, reason) combinations at once: each figure must be nonzero
    and in its own slot. A single aggregate, or a pair that collapsed the two reasons,
    would be unable to produce this result."""
    report = _f12f_run(lambda d: _f12f_prune_tree(
        d, top_pycache=True, top_dot=True, walk_pycache=True, walk_dot=True))
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    counts = _f12f_counts(report)
    assert (counts["top_pycache"], counts["top_dot"]) == ("1", "1"), report.render()
    assert (counts["walk_pycache"], counts["walk_dot"]) == ("1", "1"), report.render()
    # A pruned directory is never descended into, so its contents reach no figure --
    # neither the inspected count nor the inert count, and not as a coverage ERROR.
    assert counts["inspected"] == "5", report.render()
    assert counts["inert"] == "0", report.render()
    assert report.violations == [], report.render()
    note = _f12f_note(report)
    assert "THE THREE PRUNE PAIRS ARE NEVER SUMMED" in note, note
    assert "a pruned directory's CONTENTS at any depth" in note, note


def test_f12f_one_reason_alone_leaves_the_other_reason_at_zero():
    """The reasons must not be collapsed. A tree pruned only for `__pycache__` reports
    zero dot-prefixed prunes in both traversals, and a tree pruned only for dot-prefixed
    directories reports zero `__pycache__` prunes -- which a single counter rendered
    twice, or a pair incremented together, could not do."""
    pycache_only = _f12f_run(lambda d: _f12f_prune_tree(
        d, top_pycache=True, walk_pycache=True))
    counts = _f12f_counts(pycache_only)
    assert (counts["top_pycache"], counts["top_dot"]) == ("1", "0"), \
        pycache_only.render()
    assert (counts["walk_pycache"], counts["walk_dot"]) == ("1", "0"), \
        pycache_only.render()

    dot_only = _f12f_run(lambda d: _f12f_prune_tree(d, top_dot=True, walk_dot=True))
    counts = _f12f_counts(dot_only)
    assert (counts["top_pycache"], counts["top_dot"]) == ("0", "1"), dot_only.render()
    assert (counts["walk_pycache"], counts["walk_dot"]) == ("0", "1"), dot_only.render()


def test_f12f_top_level_and_recursive_prunes_are_never_conflated():
    """The increment's central anti-conflation property, asserted in both directions. A
    tree pruned only at the top level must report zero recursive prunes, and a tree
    pruned only inside a module subtree must report zero top-level prunes. A figure that
    summed the two traversals -- or one that reported the D5 pass's aggregate in both
    slots -- would be nonzero in all four places on both fixtures."""
    top_only = _f12f_run(lambda d: _f12f_prune_tree(d, top_pycache=True, top_dot=True))
    counts = _f12f_counts(top_only)
    assert (counts["top_pycache"], counts["top_dot"]) == ("1", "1"), top_only.render()
    assert (counts["walk_pycache"], counts["walk_dot"]) == ("0", "0"), top_only.render()

    walk_only = _f12f_run(lambda d: _f12f_prune_tree(
        d, walk_pycache=True, walk_dot=True))
    counts = _f12f_counts(walk_only)
    assert (counts["top_pycache"], counts["top_dot"]) == ("0", "0"), walk_only.render()
    assert (counts["walk_pycache"], counts["walk_dot"]) == ("1", "1"), walk_only.render()


def test_f12f_top_level_split_reconciles_against_the_unchanged_d5_aggregate():
    """The by-reason split and the D5 coverage note's long-standing `pruned entries`
    aggregate must have one producer, so they cannot drift: the two reasons sum to the
    aggregate on the same run. The D5 note's own rendering is unchanged, which is what
    lets the existing D5 tests keep asserting it."""
    report = _f12f_run(lambda d: _f12f_prune_tree(
        d, top_pycache=True, top_dot=True, walk_pycache=True, walk_dot=True))
    counts = _f12f_counts(report)
    total = int(counts["top_pycache"]) + int(counts["top_dot"])
    assert total == 2, report.render()
    coverage = [n for n in report.notes if "coverage reconciliation (ADR-011 D5):" in n]
    assert len(coverage) == 1, report.render()
    assert f"{total} pruned entries" in coverage[0], coverage[0]
    # The recursive pair is deliberately NOT in that aggregate: the D5 pass never
    # visited those entries, so folding them in would overstate what it counted.
    assert "4 pruned" not in coverage[0], coverage[0]


def test_f12f_mixed_error_run_now_carries_the_file_accounting_it_used_to_drop():
    """The gap this increment closes on the error-class path. An unattributed identifier
    ends the run ERROR at exit 2 through the error-class return, which is appended to
    *before* the clean path's own figures -- so until now that report disclosed no file
    accounting whatsoever. The scan completed, so the counts are complete, and the
    verdict, code and exit status are untouched."""
    report = _f12f_run(lambda d: (d / "membership" / "q.py").write_text(
        f'Q = "{_F12F_UNATTRIBUTED}"\n'))
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_TABLE_UNATTRIBUTED"}, report.render()
    assert _f12f_counts(report) == {
        "inspected": "6", "attempted": "6", "inert": "0", "root": "1",
        "top_pycache": "0", "top_dot": "0", "walk_pycache": "0", "walk_dot": "0",
    }, report.render()
    note = _f12f_note(report)
    assert "the file counts are complete for this run" in note, note
    assert "UNKNOWN" not in note, note
    # An ERROR-class finding does not stop the scan, so attempted and inspected agree:
    # the divergence below is specifically the abort, never a mere fail-closed finding.
    assert "ATTEMPTED IS NOT INSPECTED" in note, note
    assert any("ADR-011 D7.2 partitioned report" in n for n in report.notes), \
        report.render()


def test_f12f_abort_during_the_scan_separates_attempted_from_inspected():
    """A mid-scan abort is the one shape where the two figures must differ, and the
    reason they are two fields. `membership/z_broken.py` sorts last within its module, so
    four real files are inspected and then one is opened without finishing: attempted
    must be exactly one more than inspected, and the label must say NOT FINAL rather than
    claim a total. Both figures really are minima -- the `_root` scan unit runs after
    every module, so the modules-root file is in neither -- while the modules-root FIGURE
    and both prune pairs were established by earlier passes and stay exact, which is the
    per-fact establishment state one scope label could not express."""
    report = _f12f_run(lambda d: (d / "membership" / "z_broken.py").write_text(
        "def broken(:\n"))
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, report.render()
    counts = _f12f_counts(report)
    assert counts["inspected"] == "4", report.render()
    assert counts["attempted"] == "5", report.render()
    assert int(counts["attempted"]) == int(counts["inspected"]) + 1, report.render()
    assert counts["inert"] == "0", report.render()
    assert counts["root"] == "1", report.render()
    note = _f12f_note(report)
    assert "NOT FINAL" in note, note
    assert "aborted during the per-file scan" in note, note
    assert "minima established by real traversal, not totals" in note, note
    assert "complete for this run" not in note, note
    assert "NOT STARTED" not in note, note
    assert "UNKNOWN" not in note, note
    # D5.5's reserved coverage vocabulary stays unborrowed for this different claim.
    assert "LOWER BOUND" not in note, note
    assert "PARTIAL" not in note, note


def test_f12f_abort_before_the_scan_reports_not_started_and_unknown_not_zeros():
    """An abort upstream of everything (an absent --modules-dir): no pass ran, so the
    modules-root figure and both prune pairs must read UNKNOWN rather than zero, and the
    inspected/attempted/inert zeros must be labelled as recording that no scan happened.
    A fabricated complete zero here would claim a tree with no file, no inert file and no
    pruned entry -- facts this run never established."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        manifest_path = root / "module-manifest.json"
        manifest_path.write_text(json.dumps(_md_manifest(_F12_MODULES)))
        report = run_module_deps_gate(root / "app" / "modules", manifest_path)
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, report.render()
    assert "PASS" not in report.render(), report.render()
    assert _f12f_counts(report) == {
        "inspected": "0", "attempted": "0", "inert": "0", "root": "UNKNOWN",
        "top_pycache": "UNKNOWN", "top_dot": "UNKNOWN",
        "walk_pycache": "UNKNOWN", "walk_dot": "UNKNOWN",
    }, report.render()
    note = _f12f_note(report)
    assert "NOT STARTED" in note, note
    assert "aborted before the per-file scan" in note, note
    assert "never that the tree holds no such file" in note, note
    assert "the top-level listing never ran" in note, note
    assert "no module or _shared walk ever ran" in note, note
    assert "NOT FINAL" not in note, note
    assert "complete for this run" not in note, note
    # The coverage pass's own vocabulary stays unborrowed, so the D5 absent-root test's
    # assertions over *every* note continue to hold with this note present.
    assert "NOT_STARTED" not in note, note
    assert "PARTIAL" not in note, note
    assert "LOWER BOUND" not in note, note


def test_f12f_abort_inside_the_coverage_pass_keeps_the_prunes_it_had_observed():
    """The third abort position, and the one a single scope label cannot describe. An
    unreadable namespace directory aborts the D5 pass itself: the per-file scan never
    began (so its figures are NOT STARTED zeros), but the module walk and the
    modules-root listing already ran, so their figures are real observations that must
    survive as a stated minimum rather than be discarded or reported as UNKNOWN. Same
    chmod skip discipline as the D5 partial test: return early rather than report a
    false green on a host that does not enforce mode 000."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        modules_dir = _md_tree(root)
        _d5_partial_build(modules_dir)
        # Observable work the abort must not erase: one top-level dot-directory prune
        # (`.cache` sorts before every other entry) and one recursive `__pycache__`
        # prune inside the already-walked membership subtree.
        (modules_dir / ".cache").mkdir()
        (modules_dir / ".cache" / "junk.py").write_text("x = 1\n")
        (modules_dir / "membership" / "__pycache__").mkdir()
        (modules_dir / "membership" / "__pycache__" / "service.pyc").write_text("")
        secret = modules_dir / "zz_secret"
        os.chmod(secret, 0o000)
        try:
            try:
                os.listdir(secret)
                return  # host does not enforce mode 000 -- skip, not a false green
            except PermissionError:
                pass
            manifest_path = root / "module-manifest.json"
            _md_write_manifest(modules_dir, manifest_path, _md_base_modules())
            report = run_module_deps_gate(modules_dir, manifest_path)
        finally:
            os.chmod(secret, 0o755)

    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, report.render()
    assert _f12f_counts(report) == {
        # the per-file scan never started
        "inspected": "0", "attempted": "0", "inert": "0",
        # ... but these three were established before the abort
        "root": "2", "top_pycache": "0", "top_dot": "1",
        "walk_pycache": "1", "walk_dot": "0",
    }, report.render()
    note = _f12f_note(report)
    assert "NOT STARTED" in note, note
    # Three minima now: the top-level listing's pair, the scan walk's pair, and the
    # namespace probe's own group -- `docs_only` was probed (1 inert file) before
    # `zz_secret` aborted the very pass the probe runs inside, so that group is a real
    # observation stated as a minimum, neither UNKNOWN nor a claimed total.
    assert note.count("at least this many") == 3, note
    assert "the top-level listing did not finish" in note, note
    assert "the walk did not finish" in note, note
    assert "UNKNOWN" not in note, note
    assert "complete for this run" not in note, note
    assert "LOWER BOUND" not in note, note


def test_f12f_file_accounting_reaches_both_cli_surfaces():
    """Driven through `main` so the text renderer and the `--json` serialiser are each
    exercised for real, with the exit code asserted rather than inferred. A disclosure
    present on only one surface would leave the other unable to tell an inspected tree
    from an unexamined one."""
    def write_tree(root):
        modules_dir = _md_tree(root)
        _md_module(modules_dir, "membership", {"service.py": f'Q = "{_F12F_SQL}"\n',
                                               "README.md": "# notes\n"})
        _md_module(modules_dir, "billing",
                   {"interface.py": "def charge():\n    return None\n"})
        _f12f_prune_tree(modules_dir, top_pycache=True, walk_dot=True)
        manifest_path = root / "module-manifest.json"
        _md_write_manifest(modules_dir, manifest_path, _F12_MODULES)
        return ["--gate", "module-deps", "--modules-dir", str(modules_dir),
                "--module-manifest", str(manifest_path)]

    expected = "5 file(s) INSPECTED"
    prunes = ("immediate children: 1 '__pycache__' and 0 dot-prefixed directory "
              "prune(s)")
    with tempfile.TemporaryDirectory() as tmp:
        code, out = _cli(write_tree(Path(tmp)))
    assert code == 0, out
    assert "[module-deps] PASS" in out, out
    assert "ADR-011 D8 file accounting" in out, out
    assert expected in out, out
    assert prunes in out, out
    assert "1 INERT file(s)" in out, out

    with tempfile.TemporaryDirectory() as tmp:  # a fresh tree: `_md_tree` creates `app/`
        json_code, json_out = _cli(write_tree(Path(tmp)) + ["--json"])
    assert json_code == 0, json_out
    payload = json.loads(json_out)
    assert payload["status"] == PASS, payload
    assert payload["violations"] == [], payload
    disclosure = [n for n in payload["notes"] if "ADR-011 D8 file accounting" in n]
    assert len(disclosure) == 1, payload
    assert expected in disclosure[0], disclosure
    assert prunes in disclosure[0], disclosure
    assert "scan walk: 0 '__pycache__' and 1 dot-prefixed" in disclosure[0], disclosure
    assert "THE THREE PRUNE PAIRS ARE NEVER SUMMED" in disclosure[0], disclosure
    assert "RECONCILIATION: inspected + inert" in disclosure[0], disclosure
    assert "RESIDUAL -- not counted by any figure here" in disclosure[0], disclosure


def test_f12f_note_builder_scopes_are_distinct_and_an_unknown_scope_fails_closed():
    """The three labels must actually differ, so a partial or never-started set of
    figures can never be read as totals (and vice versa), while the figures, the
    reconciliation and the residual stay identical across all three. The two
    establishment states that are independent of the scope are exercised directly: a
    `None` coverage object and an unstarted walk each render UNKNOWN rather than zero,
    whatever the scope says. An unrecognised scope raises rather than falling back to the
    most reassuring label."""
    acct = _f12_gates._FileAccounting(inert=2, attempted=7, inspected=6, root_files=3,
                                      walk_started=True, walk_pruned_pycache=4,
                                      walk_pruned_dot=5)
    coverage = _f12_gates._CoverageCounts(pruned_pycache=1, pruned_dot=2)
    assert coverage.pruned == 3, coverage
    complete = _f12_gates._d8_file_accounting_note(acct, coverage)
    partial = _f12_gates._d8_file_accounting_note(acct, coverage,
                                                  _f12_gates._D8_SCOPE_PARTIAL)
    not_started = _f12_gates._d8_file_accounting_note(
        _f12_gates._FileAccounting(), None, _f12_gates._D8_SCOPE_NOT_STARTED)
    for note in (complete, partial, not_started):
        assert "ATTEMPTED IS NOT INSPECTED" in note, note
        assert "THE THREE PRUNE PAIRS ARE NEVER SUMMED" in note, note
        assert "RESIDUAL -- not counted by any figure here" in note, note
        assert "GATE2-R1-F12-D8-FILE-COUNTS-2026-10-05" in note, note
        # None of the three borrows the coverage disclosure's reserved vocabulary, and
        # none of them ever prints a verdict token.
        assert "LOWER BOUND" not in note, note
        assert "PARTIAL" not in note, note
        assert "NOT_STARTED" not in note, note
        assert "PASS" not in note, note
    for note in (complete, partial):
        assert "6 file(s) INSPECTED" in note, note
        assert "7 ATTEMPTED" in note, note
        assert "2 INERT file(s)" in note, note
        assert "3 file(s) AT THE MODULES ROOT" in note, note
        assert "immediate children: 1 '__pycache__' and 2 dot-prefixed" in note, note
        assert "scan walk: 4 '__pycache__' and 5 dot-prefixed" in note, note
        assert "UNKNOWN" not in note, note
    assert "the file counts are complete for this run" in complete, complete
    assert "NOT FINAL" not in complete, complete
    assert "NOT STARTED" not in complete, complete
    assert "NOT FINAL" in partial, partial
    assert "NOT STARTED" not in partial, partial
    assert "NOT STARTED" in not_started, not_started
    assert "NOT FINAL" not in not_started, not_started
    assert "0 file(s) INSPECTED" in not_started, not_started
    assert "UNKNOWN file(s) AT THE MODULES ROOT" in not_started, not_started
    # Three traversals prune, so three UNKNOWN pairs on a run where no pass ran at all:
    # the D5 top-level listing, the recursive scan walk and the D5.2 namespace probe.
    assert not_started.count("UNKNOWN '__pycache__' and UNKNOWN dot-prefixed") == 3, \
        not_started
    assert "UNKNOWN inert file(s) across UNKNOWN probed director(y/ies)" in not_started, \
        not_started
    for note in (partial, not_started):
        assert "complete for this run" not in note, note
    # An established-but-unfinished pass states a minimum; it never claims UNKNOWN for
    # work it really did, and never claims a total it did not reach.
    minimum = _f12_gates._d8_file_accounting_note(acct, coverage,
                                                  _f12_gates._D8_SCOPE_NOT_STARTED)
    # Three such statements, one per pruning traversal: the namespace probe's figures are
    # a minimum for the same reason the other two are -- the pass carrying it stopped.
    assert minimum.count("at least this many") == 3, minimum
    assert "UNKNOWN" not in minimum, minimum
    try:
        _f12_gates._d8_file_accounting_note(acct, coverage, "whatever")
    except ValueError as exc:
        assert "unknown ADR-011 D8 file-accounting-note scope" in str(exc), exc
    else:
        raise AssertionError("an unknown scope must raise rather than mislabel the counts")


def test_f12f_walk_sink_changes_no_walk_decision_and_counting_is_all_it_does():
    """`_walk_module`'s new sink must be observation only: the file list it returns is
    identical with and without it, so no prune, inclusion or refusal decision reads the
    accounting object. Without this a counting change could quietly have altered the
    scan surface it reports on."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        modules_dir = _md_tree(root)
        _md_module(modules_dir, "membership", {"service.py": "X = 1\n",
                                               "README.md": "# notes\n",
                                               "sub/helper.py": "Y = 2\n"})
        _f12f_prune_tree(modules_dir, walk_pycache=True, walk_dot=True)
        mod_dir = modules_dir / "membership"
        plain = _f12_gates._walk_module(mod_dir)
        acct = _f12_gates._FileAccounting()
        counted = _f12_gates._walk_module(mod_dir, acct)
    assert plain == counted, (plain, counted)
    assert sorted(p.name for p in counted) == ["README.md", "__init__.py", "helper.py",
                                               "service.py"], counted
    assert acct.walk_started is True, acct
    assert (acct.walk_pruned_pycache, acct.walk_pruned_dot) == (1, 1), acct
    # Everything the per-file scan owns stays untouched by the walk.
    assert (acct.inspected, acct.attempted, acct.inert) == (0, 0, 0), acct
    assert acct.root_files is None, acct


def test_f12f_counters_changed_no_verdict_no_code_and_no_exit_code():
    """The regression guard this increment's "reporting only" claim rests on. Each
    fixture pins status, exit code and code set alongside its figures, so an accounting
    change that had quietly reclassified an outcome -- most dangerously, turning a pruned
    directory's contents into a coverage ERROR, or an inert file into a scanned one --
    fails here rather than in a module's certification."""
    cases = (
        ("clean", _f12f_run(), PASS, 0, set()),
        ("inert and pruned", _f12f_run(lambda d: (
            _f12f_prune_tree(d, top_dot=True, walk_pycache=True),
            (d / "membership" / "README.md").write_text("# notes\n"),
        )), PASS, 0, set()),
        ("cross-domain FAIL", _f12f_run(lambda d: (d / "membership" / "q.py").write_text(
            f'Q = "{_F12_CROSS}"\n')), FAIL, 1, {"CROSS_DOMAIN_SQL_IMPORT"}),
        ("unattributed ERROR", _f12f_run(lambda d: (d / "membership" / "q.py").write_text(
            f'Q = "{_F12F_UNATTRIBUTED}"\n')), ERROR, 2, {"MODULE_DEPS_TABLE_UNATTRIBUTED"}),
    )
    for label, report, status, exit_code, codes in cases:
        assert report.status == status, (label, report.render())
        assert report.exit_code == exit_code, (label, report.render())
        assert report.codes() == codes, (label, report.render())
        # Every run carries the disclosure exactly once, whatever its verdict.
        assert len([n for n in report.notes if "ADR-011 D8 file accounting" in n]) == 1, \
            (label, report.render())
        counts = _f12f_counts(report)
        assert counts["root"] == "1", (label, report.render())
        assert counts["inspected"] == counts["attempted"], (label, report.render())


def test_f12f_accounting_did_not_wire_cte_state_3_or_disturb_the_other_disclosures():
    """Scope guard, as every increment in this file carries: counting files must not have
    wired ADR-011 D3.2 state 3 into the live scanning path, nor moved the five
    disclosures beside it. A `WITH`-bound name is still an unattributed ERROR with a CTE
    count of 0, and a clean run still carries each existing D8/D3.5 note exactly once."""
    report = _f12b_run({"service.py": f'Q = "{_F12B_CTE}"\n'})
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_TABLE_UNATTRIBUTED"}, report.render()
    assert _f12b_counts(report)["cte"] == 0, report.render()
    assert len([n for n in report.notes if "ADR-011 D8 file accounting" in n]) == 1, \
        report.render()

    clean = _f12f_run()
    assert clean.status == PASS, clean.render()
    for marker in ("ADR-011 D8 SQL-trigger inspection",
                   "ADR-011 D8 table-reference attribution",
                   "ADR-011 D8 cross-module import edges",
                   "ADR-011 D3.5/D8 declared external_table_references inventory",
                   "ADR-011 D6.3/D8 zero-table triggered statements",
                   "ADR-011 D8 file accounting"):
        assert len([n for n in clean.notes if marker in n]) == 1, (marker, clean.render())
    assert any("remains unimplemented" in n for n in clean.notes), clean.render()
    # Statement segmentation landed in GATE2-R1-F12-D8-STATEMENT-SUBJECTS-2026-10-06, so
    # what must stay disclosed is its decline rule -- the remaining granularity limit --
    # rather than the superseded "no segmentation at all" claim.
    assert any("Where the cut is NOT lexically certain segmentation is DECLINED" in n
               for n in clean.notes), clean.render()
    assert not any("real per-statement segmentation remains unimplemented" in n
                   for n in clean.notes), clean.render()


# --- R1-F12 / ADR-011 D8 (GATE2-R1-F12-D8-NAMESPACE-FILE-PRUNE-COUNTS-2026-10-06) ---
#
# The increment above disclosed two pruning traversals and left a third out: the ADR-011
# D5.2 probe of a NON-discovered directory under --modules-dir. The deterministic
# inspection GATE2-R1-F12-D8-NAMESPACE-FILE-PRUNE-INSPECTION-2026-10-06.md reproduced
# the gap on a PASS run -- a fixture with one inert namespace file, one namespace
# `__pycache__` and one namespace dot-directory reported all four existing figures as 0,
# disclosed the probe's prunes nowhere, and surfaced its inert file only through the D5
# coverage note's own bucket.
#
# Each test below is written so that it could only pass against a real third group, and
# the family as a whole opposes the three ways this disclosure could lie instead of
# merely being thin:
#
#   * SUMMING. A namespace prune must never appear in the top-level pair, the recursive
#     pair, or the D5 note's `pruned entries` aggregate, and a namespace inert file must
#     never appear in the INERT figure -- so the "one reason alone" fixtures below set
#     exactly one (traversal, reason) switch at a time and pin every other slot at zero.
#   * THE SHORT CIRCUIT. The probe stops at its first non-inert file, so a directory's
#     figures are an observation up to that point. The ERROR fixture below is the one
#     where the D5 bucket credits nothing and this group is the only disclosure of the
#     inert file the probe really saw -- which is the whole reason the figure exists.
#   * STATE. "Never probed" (UNKNOWN), "probed nothing because the listing finished and
#     found no such directory" (an observed zero) and "stopped mid-pass" (a minimum) are
#     three different claims about the same zeros and must read differently.
#
# And the family's standing scope guard: counting is observation only -- same verdict,
# same code, same exit status, same inclusion decisions, and no CTE state-3 wiring.

_F12G_NS_MARKER = "; non-discovered-namespace probe: "


def _f12g_ns(report):
    """The namespace-probe group's five figures, parsed out of the disclosure note itself
    -- for the same reason `_f12f_counts` is, and returned VERBATIM rather than coerced:
    telling the string "0" apart from the string "UNKNOWN" is the point of several
    assertions below."""
    note = _f12f_note(report)
    assert _F12G_NS_MARKER in note, note
    segment = note.split(_F12G_NS_MARKER, 1)[1]
    pycache, dot = _f12f_pair(segment)
    return {
        "ns_pycache": pycache,
        "ns_dot": dot,
        "ns_inert": _f12f_slot(segment, "dot-prefixed directory prune(s), ",
                               " inert file(s) across"),
        "ns_probes": _f12f_slot(segment, " inert file(s) across ", " probed director"),
        "ns_short": _f12f_slot(segment, ", of which ",
                               " stopped at a first non-inert file"),
    }


_F12G_NS_ZERO = {"ns_pycache": "0", "ns_dot": "0", "ns_inert": "0", "ns_probes": "0",
                 "ns_short": "0"}


def _f12g_namespace(modules_dir, inert=False, pycache=False, dot=False,
                    non_inert=False, name="orphan"):
    """A non-discovered directory -- no `__init__.py`, so `_discover_modules` drops it and
    only the D5.2 probe ever walks it -- with each observable shape switched on
    independently. Nothing here is reachable by the module/`_shared` scan walk or by the
    top-level listing's own prune branch, which is what makes every nonzero figure below
    attributable to the probe alone."""
    ns = modules_dir / name
    ns.mkdir()
    if inert:
        (ns / "README.md").write_text("# notes\n")
    if pycache:
        (ns / "__pycache__").mkdir()
        (ns / "__pycache__" / "skip.pyc").write_text("")
    if dot:
        (ns / ".cache").mkdir()
        (ns / ".cache" / "skip.py").write_text("X = 1\n")
    if non_inert:
        # Sorts after README.md, so a probe over both counts the inert file first and
        # only then short-circuits on this one.
        (ns / "service.py").write_text("X = 1\n")
    return ns


def _f12g_d5_note(report):
    notes = [n for n in report.notes if "coverage reconciliation (ADR-011 D5):" in n]
    assert len(notes) == 1, report.render()
    return notes[0]


def test_f12g_namespace_only_inert_file_is_disclosed_in_its_own_figure():
    """The inspection's first unreported observation. A non-discovered directory holding
    one inert file and nothing else is a PASS whose INERT figure is 0 -- correctly, since
    no walk yielded that file -- and until this increment the D8 accounting said nothing
    about it at all. It must now read 1 inert file across 1 probed directory, in the
    probe's own group, while the INERT figure stays 0: the two are disjoint counts over
    disjoint territory and adding them is exactly what the note forbids."""
    report = _f12f_run(lambda d: _f12g_namespace(d, inert=True))
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    assert report.violations == [], report.render()
    assert _f12g_ns(report) == {**_F12G_NS_ZERO, "ns_inert": "1", "ns_probes": "1"}, \
        report.render()
    # Not folded into the walks' own figures, and the scan surface is unchanged.
    counts = _f12f_counts(report)
    assert counts["inert"] == "0", report.render()
    assert (counts["inspected"], counts["attempted"]) == ("5", "5"), report.render()
    assert (counts["top_pycache"], counts["top_dot"]) == ("0", "0"), report.render()
    assert (counts["walk_pycache"], counts["walk_dot"]) == ("0", "0"), report.render()
    note = _f12f_note(report)
    assert "1 probed directory, of which 0 stopped" in note, note
    assert "THE NON-DISCOVERED-NAMESPACE INERT FIGURE IS NOT PART OF THE INERT FIGURE" \
        in note, note
    assert "UNKNOWN" not in note, note
    # Single producer: the D5 coverage note's own inert-namespace bucket, whose rendering
    # this increment does not touch, reports the same file on this run.
    assert "1 inert file(s) in inert-only namespace directory/ies" in _f12g_d5_note(report)


def test_f12g_namespace_prunes_are_counted_by_reason_in_the_probe_s_own_pair():
    """The inspection's second and third unreported observations, each alone so neither
    reason can be collapsed into the other: a namespace `__pycache__` reports 1/0 and a
    namespace dot-directory reports 0/1, in the probe's pair and nowhere else. A pruned
    directory is still never descended into, so its contents reach no figure and raise no
    coverage ERROR."""
    pycache_only = _f12f_run(lambda d: _f12g_namespace(d, pycache=True))
    assert pycache_only.status == PASS, pycache_only.render()
    assert pycache_only.exit_code == 0, pycache_only.render()
    assert _f12g_ns(pycache_only) == {**_F12G_NS_ZERO, "ns_pycache": "1",
                                      "ns_probes": "1"}, pycache_only.render()

    dot_only = _f12f_run(lambda d: _f12g_namespace(d, dot=True))
    assert dot_only.status == PASS, dot_only.render()
    assert dot_only.exit_code == 0, dot_only.render()
    assert _f12g_ns(dot_only) == {**_F12G_NS_ZERO, "ns_dot": "1", "ns_probes": "1"}, \
        dot_only.render()

    for report in (pycache_only, dot_only):
        counts = _f12f_counts(report)
        # The namespace prune is in neither other pair, and the pruned directory's own
        # `.py`/`.pyc` content is inspected nowhere and unattributed nowhere.
        assert (counts["top_pycache"], counts["top_dot"]) == ("0", "0"), report.render()
        assert (counts["walk_pycache"], counts["walk_dot"]) == ("0", "0"), report.render()
        assert (counts["inspected"], counts["inert"]) == ("5", "0"), report.render()
        assert report.violations == [], report.render()
        # ... and not in the D5 pass's top-level aggregate either: that pass pruned no
        # immediate child of --modules-dir on these fixtures.
        assert "0 pruned entries" in _f12g_d5_note(report), _f12g_d5_note(report)


def test_f12g_all_three_traversals_prune_at_once_and_stay_in_their_own_slots():
    """The three-way anti-conflation property, all six (traversal, reason) figures nonzero
    in one run. A figure that summed any two traversals, or reported one traversal's pair
    in another's slot, cannot produce 1/1, 1/1, 1/1 here -- and the D5 note's own
    aggregate must still count its own two top-level prunes only, never the four it never
    saw."""
    report = _f12f_run(lambda d: (
        _f12f_prune_tree(d, top_pycache=True, top_dot=True,
                         walk_pycache=True, walk_dot=True),
        _f12g_namespace(d, pycache=True, dot=True, inert=True),
    ))
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    assert report.violations == [], report.render()
    counts = _f12f_counts(report)
    assert (counts["top_pycache"], counts["top_dot"]) == ("1", "1"), report.render()
    assert (counts["walk_pycache"], counts["walk_dot"]) == ("1", "1"), report.render()
    assert _f12g_ns(report) == {"ns_pycache": "1", "ns_dot": "1", "ns_inert": "1",
                               "ns_probes": "1", "ns_short": "0"}, report.render()
    assert (counts["inspected"], counts["inert"]) == ("5", "0"), report.render()
    assert "2 pruned entries" in _f12g_d5_note(report), _f12g_d5_note(report)
    note = _f12f_note(report)
    assert "THE THREE PRUNE PAIRS ARE NEVER SUMMED" in note, note
    assert "no file count exists behind any of the three prune pairs" in note, note


def test_f12g_short_circuited_probe_still_discloses_the_inert_it_had_counted():
    """The divergence that makes the probe's own inert figure load-bearing rather than a
    duplicate of the D5 bucket. A non-discovered directory holding both an inert file and
    a non-inert one is ERROR MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH, and the D5 pass
    credits that directory's inert files to nothing at all -- it counts them only for a
    directory with no non-inert file. The probe really did read that inert file, so this
    group discloses it, labelled as an observation up to the short-circuit point. The
    verdict, code and exit status are the pre-existing ones."""
    report = _f12f_run(lambda d: _f12g_namespace(d, inert=True, non_inert=True))
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH"}, report.render()
    assert _f12g_ns(report) == {**_F12G_NS_ZERO, "ns_inert": "1", "ns_probes": "1",
                                "ns_short": "1"}, report.render()
    # The D5 bucket is 0 on this run, so without this group the file would be disclosed
    # nowhere -- which is the gap the inspection recorded.
    assert "0 inert file(s) in inert-only namespace directory/ies" in _f12g_d5_note(report)
    note = _f12f_note(report)
    assert "1 probed directory, of which 1 stopped at a first non-inert file" in note, note
    assert "the file counts are complete for this run" in note, note
    assert "observations up to that point and never a subtree total" in note, note
    assert "UNKNOWN" not in note, note


def test_f12g_probe_that_aborted_is_still_disclosed_as_attempted_and_as_a_minimum():
    """The probe count is incremented BEFORE each probe runs, which is only observable
    when one of them aborts. Two non-discovered directories, the second holding a symlink
    the probe refuses (ADR-011 D5.3): the pass dies there, so the per-file scan never
    begins, yet the run must still disclose that TWO directories were probed -- the first
    completely (its inert file counted) and the second attempted -- and must label the
    whole group a minimum rather than a total. Counting after the call instead of before
    would silently drop the directory the run actually died in. No chmod here: the
    refusal is deterministic on every host."""
    def extra(modules_dir):
        _f12g_namespace(modules_dir, inert=True, name="orphan")
        broken = modules_dir / "zz_orphan_broken"   # sorts after `orphan`
        broken.mkdir()
        (broken / "link.py").symlink_to("README.md")

    report = _f12f_run(extra)
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_GATE_INPUT_INVALID"}, report.render()
    assert "symlinks are refused" in report.render(), report.render()
    assert "PASS" not in report.render(), report.render()
    assert _f12g_ns(report) == {**_F12G_NS_ZERO, "ns_inert": "1", "ns_probes": "2"}, \
        report.render()
    note = _f12f_note(report)
    assert "2 probed directories, of which 0 stopped" in note, note
    # The pass that carries the probe stopped, so the group is a stated minimum -- not a
    # total, and not the UNKNOWN a run that never probed anything would report.
    assert "the top-level listing did not finish" in note, note
    assert "NOT STARTED" in note, note        # the per-file scan, which never began
    assert note.count("at least this many") == 3, note
    assert "UNKNOWN" not in note, note
    # The per-file scan really did not run, which is what makes the figures above the
    # only disclosure of the namespace work this run performed.
    counts = _f12f_counts(report)
    assert (counts["inspected"], counts["attempted"]) == ("0", "0"), report.render()


def test_f12g_probe_group_separates_unknown_from_observed_zero_and_from_a_minimum():
    """The three establishment states, at the note builder, with the figures held fixed so
    only the state wording can differ. `coverage is None` is UNKNOWN -- the pass carrying
    the probe never ran. A pass that ran and reached no non-discovered directory reports
    observed zeros and says so. A pass that ran and did not finish reports what it had
    seen as a minimum. A single label for all three, or a zero-filled UNKNOWN, could not
    satisfy all four assertions."""
    acct = _f12_gates._FileAccounting(root_files=1, walk_started=True)
    never = _f12_gates._d8_file_accounting_note(
        acct, None, _f12_gates._D8_SCOPE_NOT_STARTED)
    assert ("UNKNOWN inert file(s) across UNKNOWN probed director(y/ies), of which "
            "UNKNOWN stopped at a first non-inert file") in never, never
    assert "no non-discovered directory was ever probed" in never, never

    looked = _f12_gates._d8_file_accounting_note(acct, _f12_gates._CoverageCounts())
    assert "0 inert file(s) across 0 probed directories, of which 0 stopped" in looked, \
        looked
    assert "reached no non-discovered directory at all" in looked, looked
    assert "observed zeros rather than figures no pass ever established" in looked, looked
    assert "UNKNOWN" not in looked, looked

    observed = _f12_gates._CoverageCounts(
        namespace_probes=2, namespace_probe_short_circuited=1, namespace_probe_inert=3,
        namespace_probe_pruned_pycache=1, namespace_probe_pruned_dot=2)
    complete = _f12_gates._d8_file_accounting_note(acct, observed)
    minimum = _f12_gates._d8_file_accounting_note(
        acct, observed, _f12_gates._D8_SCOPE_NOT_STARTED)
    figures = ("1 '__pycache__' and 2 dot-prefixed directory prune(s), 3 inert file(s) "
               "across 2 probed directories, of which 1 stopped at a first non-inert file")
    for note in (complete, minimum):
        assert f"{_F12G_NS_MARKER.lstrip('; ')}{figures}" in note, note
        assert "UNKNOWN" not in note, note
    assert "non-inert file (complete)" in complete, complete
    assert "the top-level listing did not finish" in minimum, minimum
    assert "counted nowhere here" in minimum, minimum
    assert "reached no non-discovered directory at all" not in minimum, minimum
    # The coverage pass's own reserved vocabulary stays unborrowed by this group too.
    for note in (never, looked, complete, minimum):
        assert "LOWER BOUND" not in note, note
        assert "NOT_STARTED" not in note, note
        assert "PASS" not in note, note


def test_f12g_probe_sink_changes_no_probe_decision_and_counting_is_all_it_does():
    """`_scan_namespace_subtree`'s new sink must be observation only: the tuple it returns
    is identical with and without one, on both the clean and the short-circuiting shape,
    so no prune, descend, inert or short-circuit decision reads the accounting object.
    And the sink writes only its own five fields -- the other traversals' counters, which
    this probe never establishes, stay at their defaults."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        modules_dir = _md_tree(root)
        clean_ns = _f12g_namespace(modules_dir, inert=True, pycache=True, dot=True,
                                   name="orphan")
        dirty_ns = _f12g_namespace(modules_dir, inert=True, non_inert=True,
                                   name="orphan_dirty")
        plain_clean = _f12_gates._scan_namespace_subtree(clean_ns)
        counts = _f12_gates._CoverageCounts()
        counted_clean = _f12_gates._scan_namespace_subtree(clean_ns, counts)
        plain_dirty = _f12_gates._scan_namespace_subtree(dirty_ns)
        counted_dirty = _f12_gates._scan_namespace_subtree(dirty_ns, counts)
    assert plain_clean == counted_clean == (1, None), (plain_clean, counted_clean)
    assert plain_dirty == counted_dirty, (plain_dirty, counted_dirty)
    assert counted_dirty[0] == 1, counted_dirty
    assert counted_dirty[1] is not None and counted_dirty[1].name == "service.py", \
        counted_dirty
    # Two probes' worth of observations, accumulated across both calls.
    assert (counts.namespace_probe_inert, counts.namespace_probe_pruned_pycache,
            counts.namespace_probe_pruned_dot) == (2, 1, 1), counts
    # Written only by the call site in `_reconcile_module_coverage`, never by the probe.
    assert (counts.namespace_probes, counts.namespace_probe_short_circuited) == (0, 0), \
        counts
    # Nothing belonging to the other two traversals, or to the D5 buckets, is touched.
    assert (counts.pruned_pycache, counts.pruned_dot, counts.pruned) == (0, 0, 0), counts
    assert (counts.modules, counts.shared, counts.root_files) == (0, 0, 0), counts
    assert (counts.namespace_inert, counts.recursive_eligible) == (0, 0), counts


def test_f12g_namespace_disclosure_reaches_both_cli_surfaces():
    """Driven through `main`, so the text renderer and the `--json` serialiser each carry
    the same namespace figures for real, with the exit code asserted rather than inferred.
    A group present on one surface only would leave the other unable to tell a probed tree
    from an unprobed one."""
    def write_tree(root):
        modules_dir = _md_tree(root)
        _md_module(modules_dir, "membership", {"service.py": f'Q = "{_F12F_SQL}"\n'})
        _md_module(modules_dir, "billing",
                   {"interface.py": "def charge():\n    return None\n"})
        _f12g_namespace(modules_dir, inert=True, pycache=True, dot=True)
        manifest_path = root / "module-manifest.json"
        _md_write_manifest(modules_dir, manifest_path, _F12_MODULES)
        return ["--gate", "module-deps", "--modules-dir", str(modules_dir),
                "--module-manifest", str(manifest_path)]

    expected = (f"{_F12G_NS_MARKER}1 '__pycache__' and 1 dot-prefixed directory "
                "prune(s), 1 inert file(s) across 1 probed directory, of which 0 "
                "stopped at a first non-inert file (complete)")
    with tempfile.TemporaryDirectory() as tmp:
        code, out = _cli(write_tree(Path(tmp)))
    assert code == 0, out
    assert "[module-deps] PASS" in out, out
    assert expected in out, out

    with tempfile.TemporaryDirectory() as tmp:  # a fresh tree: `_md_tree` creates `app/`
        json_code, json_out = _cli(write_tree(Path(tmp)) + ["--json"])
    assert json_code == 0, json_out
    payload = json.loads(json_out)
    assert payload["status"] == PASS, payload
    assert payload["violations"] == [], payload
    disclosure = [n for n in payload["notes"] if "ADR-011 D8 file accounting" in n]
    assert len(disclosure) == 1, payload
    assert expected in disclosure[0], disclosure
    # Both surfaces read the identical note object, so the figures cannot diverge.
    assert disclosure[0] in out, (disclosure[0], out)


def test_f12g_namespace_counting_changed_no_verdict_no_code_and_no_exit_code():
    """The regression guard this increment's "reporting only" claim rests on. Each fixture
    pins status, exit code and code set alongside its namespace figures, so a counting
    change that had quietly reclassified an outcome -- most dangerously, turning a pruned
    namespace directory's contents into a coverage ERROR, or an inert namespace file into
    a scanned one -- fails here rather than in a module's certification."""
    cases = (
        ("no namespace directory", _f12f_run(), PASS, 0, set(), _F12G_NS_ZERO),
        ("inert only", _f12f_run(lambda d: _f12g_namespace(d, inert=True)), PASS, 0,
         set(), {**_F12G_NS_ZERO, "ns_inert": "1", "ns_probes": "1"}),
        ("pruned only", _f12f_run(lambda d: _f12g_namespace(d, pycache=True, dot=True)),
         PASS, 0, set(), {**_F12G_NS_ZERO, "ns_pycache": "1", "ns_dot": "1",
                          "ns_probes": "1"}),
        ("empty namespace directory", _f12f_run(lambda d: _f12g_namespace(d)), PASS, 0,
         set(), {**_F12G_NS_ZERO, "ns_probes": "1"}),
        ("non-inert namespace file", _f12f_run(lambda d: _f12g_namespace(d,
                                                                        non_inert=True)),
         ERROR, 2, {"MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH"},
         {**_F12G_NS_ZERO, "ns_probes": "1", "ns_short": "1"}),
        ("cross-domain FAIL beside a namespace directory", _f12f_run(lambda d: (
            _f12g_namespace(d, inert=True),
            (d / "membership" / "q.py").write_text(f'Q = "{_F12_CROSS}"\n'),
        )), FAIL, 1, {"CROSS_DOMAIN_SQL_IMPORT"},
         {**_F12G_NS_ZERO, "ns_inert": "1", "ns_probes": "1"}),
    )
    for label, report, status, exit_code, codes, ns in cases:
        assert report.status == status, (label, report.render())
        assert report.exit_code == exit_code, (label, report.render())
        assert report.codes() == codes, (label, report.render())
        assert len([n for n in report.notes if "ADR-011 D8 file accounting" in n]) == 1, \
            (label, report.render())
        assert _f12g_ns(report) == ns, (label, report.render())
        # The walks' own figures are identical across every row: the namespace surface
        # changed none of them.
        counts = _f12f_counts(report)
        assert counts["inert"] == "0", (label, report.render())
        assert counts["root"] == "1", (label, report.render())
        assert (counts["top_pycache"], counts["top_dot"]) == ("0", "0"), \
            (label, report.render())
        assert (counts["walk_pycache"], counts["walk_dot"]) == ("0", "0"), \
            (label, report.render())


def test_f12g_namespace_counting_did_not_wire_cte_state_3_or_disturb_the_disclosures():
    """Scope guard, as every increment in this file carries: counting the namespace
    probe's files and prunes must not have wired ADR-011 D3.2 state 3 into the live
    scanning path, nor moved the disclosures beside it. A `WITH`-bound name is still an
    unattributed ERROR with a CTE count of 0, and a clean run with a probed namespace
    directory still carries each existing D8/D3.5 note exactly once."""
    report = _f12b_run({"service.py": f'Q = "{_F12B_CTE}"\n'})
    assert report.status == ERROR, report.render()
    assert report.exit_code == 2, report.render()
    assert report.codes() == {"MODULE_DEPS_TABLE_UNATTRIBUTED"}, report.render()
    assert _f12b_counts(report)["cte"] == 0, report.render()

    clean = _f12f_run(lambda d: _f12g_namespace(d, inert=True, pycache=True, dot=True))
    assert clean.status == PASS, clean.render()
    assert clean.exit_code == 0, clean.render()
    assert _f12b_counts(clean)["cte"] == 0, clean.render()
    for marker in ("ADR-011 D8 SQL-trigger inspection",
                   "ADR-011 D8 table-reference attribution",
                   "ADR-011 D8 cross-module import edges",
                   "ADR-011 D3.5/D8 declared external_table_references inventory",
                   "ADR-011 D6.3/D8 zero-table triggered statements",
                   "ADR-011 D8 file accounting",
                   "coverage reconciliation (ADR-011 D5):"):
        assert len([n for n in clean.notes if marker in n]) == 1, (marker, clean.render())


# --- R1-F13 / ADR-011 D2: every declared public_interfaces entry must exist ---------
# Round 1 case F: both modules declared non-existent interface paths, an import of one
# was *approved*, and the run was `exit=0 PASS`. A typo in an interface path therefore
# silently WIDENED the approved surface -- the inverse of the fail-closed posture every
# other manifest field already had. Each test below is paired so that neither half is
# trivially satisfiable: a positive control must still reach PASS (the rule is not
# "error on every interface"), and the negative must reach ERROR
# MODULE_DEPS_GATE_INPUT_INVALID at exit 2 (never FAIL, never PASS, never a note).

_F13_MODULES = {
    "membership": _md_entry("MEM-01", ["mem_"], ["app.modules.membership.interface"]),
    "billing": _md_entry("BIL-02", ["bil_"], ["app.modules.billing.interface"]),
}
# The import round 1 observed being approved against a non-existent interface.
_F13_IMPORT = "from app.modules.billing.interface import preview_charge\n"


def _f13_build(membership_files, billing_files):
    def build(modules_dir):
        _md_module(modules_dir, "membership", membership_files)
        _md_module(modules_dir, "billing", billing_files)

    return build


def _f13_run(membership_files, billing_files, modules=None):
    """Interface materialization is OFF throughout this family: the whole point is
    whether the declared file is really there, so the fixture states that itself."""
    return _md_run(_F13_MODULES if modules is None else modules,
                   _f13_build(membership_files, billing_files),
                   materialize_interfaces=False)


def test_f13_declared_interface_as_a_module_file_resolves_and_passes():
    # Positive control: both declared interfaces exist as `<name>.py`.
    report = _f13_run({"service.py": _F13_IMPORT, "interface.py": "X = 1\n"},
                      {"interface.py": "def preview_charge(m):\n    return None\n"})
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    assert report.codes() == set(), report.render()
    # the approved edge really was resolved and approved, so PASS is not vacuous here
    assert any("1 edge occurrence(s) resolved" in n and "1 approved" in n
               for n in report.notes), report.render()


def test_f13_declared_interface_as_a_package_init_resolves_and_passes():
    # The other form D2 names: `<path>/__init__.py` rather than `<path>.py`.
    def build(modules_dir):
        _md_module(modules_dir, "membership", {"service.py": _F13_IMPORT,
                                               "interface.py": "X = 1\n"})
        _md_module(modules_dir, "billing", {
            "interface/__init__.py": "def preview_charge(m):\n    return None\n",
        })

    report = _md_run(_F13_MODULES, build, materialize_interfaces=False)
    assert report.status == PASS, report.render()
    assert report.exit_code == 0, report.render()
    assert report.codes() == set(), report.render()


def test_f13_nested_declared_interface_resolves_under_its_own_module():
    modules = {
        "membership": _md_entry("MEM-01", ["mem_"], ["app.modules.membership.api.public"]),
        "billing": _md_entry("BIL-02", ["bil_"], ["app.modules.billing.interface"]),
    }
    report = _f13_run({"api/public.py": "X = 1\n"}, {"interface.py": "Y = 1\n"},
                      modules=modules)
    assert report.status == PASS, report.render()
    assert report.codes() == set(), report.render()


def test_f13_typo_in_a_declared_interface_narrows_rather_than_widens():
    """The round-1 reproducer, inverted. `interfcae.py` exists; the manifest declares
    `interface`. Before this rule the run was PASS with the import approved against a
    path naming nothing; now it is ERROR, and the offending entry is named."""
    report = _f13_run({"service.py": _F13_IMPORT, "interface.py": "X = 1\n"},
                      {"interfcae.py": "def preview_charge(m):\n    return None\n"})
    _assert_md_input_error(report, "typo'd billing interface")
    detail = " ".join(v.detail for v in report.violations)
    assert "'app.modules.billing.interface'" in detail, report.render()
    assert "interface.py or interface/__init__.py" in detail, report.render()
    assert "narrow the approved surface, never widen it" in detail, report.render()
    assert PASS not in report.render(), report.render()


def test_f13_round1_case_f_both_interfaces_absent_is_no_longer_exit_zero_pass():
    # Case F exactly: neither declared interface exists, and one of them is imported.
    report = _f13_run({"service.py": _F13_IMPORT}, {"models.py": "class Invoice:\n    pass\n"})
    _assert_md_input_error(report, "round-1 case F")
    assert report.exit_code == 2, report.render()
    # The widened approval is gone with it: no edge was approved on this run.
    assert not any("1 approved" in n for n in report.notes), report.render()


def test_f13_declared_interface_naming_a_bare_directory_is_error():
    # A directory with no `__init__.py` is not the package form D2 names, so it must
    # not resolve -- otherwise a PEP 420 namespace directory would count as an
    # interface and widen the surface by the back door.
    def build(modules_dir):
        _md_module(modules_dir, "membership", {"service.py": "X = 1\n",
                                               "interface.py": "Y = 1\n"})
        _md_module(modules_dir, "billing", {"models.py": "class I:\n    pass\n"})
        (modules_dir / "billing" / "interface").mkdir()
        (modules_dir / "billing" / "interface" / "notes.md").write_text("# notes\n")

    report = _md_run(_F13_MODULES, build, materialize_interfaces=False)
    _assert_md_input_error(report, "bare directory as interface")
    assert "'app.modules.billing.interface'" in " ".join(
        v.detail for v in report.violations), report.render()


def test_f13_symlinked_interface_file_is_refused_not_followed():
    def build(modules_dir):
        _md_module(modules_dir, "membership", {"service.py": "X = 1\n",
                                               "interface.py": "Y = 1\n"})
        _md_module(modules_dir, "billing", {"real.py": "def preview_charge(m):\n    return 1\n"})
        (modules_dir / "billing" / "interface.py").symlink_to(modules_dir / "billing" / "real.py")

    report = _md_run(_F13_MODULES, build, materialize_interfaces=False)
    _assert_md_input_error(report, "symlinked interface file")
    # Asserted against the *resolution's* own message, not merely the word "symlink":
    # `_walk_module` also refuses symlinks, so a run with this check removed still
    # fails closed by that other route. Naming the public_interfaces entry is what
    # discriminates D2 resolution refusing it from the walk refusing it later.
    detail = " ".join(v.detail for v in report.violations)
    assert "public_interfaces entry 'app.modules.billing.interface'" in detail, report.render()
    assert "is a symlink (refused)" in detail, report.render()
    assert PASS not in report.render(), report.render()


def test_f13_symlinked_intermediate_directory_is_refused_not_followed():
    """`os.lstat` declines to follow only the FINAL component, so a symlinked
    intermediate directory would otherwise let a declared interface resolve to a file
    outside the module -- or outside --modules-dir entirely -- and be counted approved.
    The walk is component-by-component precisely so this is refused."""
    modules = {
        "membership": _md_entry("MEM-01", ["mem_"], ["app.modules.membership.interface"]),
        "billing": _md_entry("BIL-02", ["bil_"], ["app.modules.billing.api.public"]),
    }

    def build(modules_dir):
        _md_module(modules_dir, "membership", {"service.py": "X = 1\n",
                                               "interface.py": "Y = 1\n"})
        _md_module(modules_dir, "billing", {"real/public.py": "Z = 1\n"})
        (modules_dir / "billing" / "api").symlink_to(
            modules_dir / "billing" / "real", target_is_directory=True)

    report = _md_run(modules, build, materialize_interfaces=False)
    _assert_md_input_error(report, "symlinked intermediate directory")
    detail = " ".join(v.detail for v in report.violations)
    assert "public_interfaces entry 'app.modules.billing.api.public'" in detail, report.render()
    assert "resolves through a symlink at" in detail, report.render()


def test_f13_declared_interface_is_resolved_in_its_own_module_only():
    """D2 says "inside that module's own directory". A path that would resolve if the
    search were allowed to wander -- billing declares `billing.interface` while only
    `membership/interface.py` exists -- must still be ERROR. The package-prefix check
    alone never caught this, because the prefix was already correct."""
    report = _f13_run({"interface.py": "X = 1\n"}, {"models.py": "class I:\n    pass\n"})
    _assert_md_input_error(report, "interface resolved outside its own module")
    assert "'app.modules.billing.interface'" in " ".join(
        v.detail for v in report.violations), report.render()


def test_f13_declared_but_absent_module_keeps_its_d56_note_and_does_not_error():
    """The one disclosed residual: existence is verified only for a module whose
    directory is actually present, so D5.6's "a manifest-declared-but-absent module
    remains a note, not an ERROR" survives. Asserted explicitly so a future change in
    either direction is a deliberate one."""
    def build(modules_dir):
        _md_module(modules_dir, "membership", {"service.py": "X = 1\n",
                                               "interface.py": "Y = 1\n"})

    report = _md_run(_F13_MODULES, build, materialize_interfaces=False)
    assert report.status == PASS, report.render()
    assert report.codes() == set(), report.render()
    assert any("manifest entries with no directory: ['billing']" in n
               for n in report.notes), report.render()


def test_f13_symlinked_module_directory_is_still_error_not_a_skipped_check():
    """The carve-out above skips existence validation for any module directory that is
    not a real directory, which includes a symlinked one. That is only safe because
    `_discover_modules` refuses a symlinked child outright, so the run is still ERROR
    exit 2 rather than a PASS with an unverified interface. Pinned here, because the
    carve-out's safety depends on it."""
    def build(modules_dir):
        _md_module(modules_dir, "membership", {"service.py": "X = 1\n",
                                               "interface.py": "Y = 1\n"})
        _md_module(modules_dir, "real_billing", {"interface.py": "Z = 1\n"})
        (modules_dir / "billing").symlink_to(modules_dir / "real_billing",
                                             target_is_directory=True)

    report = _md_run(_F13_MODULES, build, materialize_interfaces=False)
    _assert_md_input_error(report, "symlinked module directory")
    assert "symlinks are refused" in " ".join(
        v.detail for v in report.violations), report.render()
    assert PASS not in report.render(), report.render()


def test_f13_interface_existence_reaches_both_cli_surfaces():
    """Through the real `main()` argv path, so the operator-facing classification and
    exit code are measured rather than inferred: ERROR exit 2 under
    MODULE_DEPS_GATE_INPUT_INVALID in text, and the same code in `--json`."""
    def write_tree(root, billing_files):
        modules_dir = _md_tree(root)
        _md_module(modules_dir, "membership", {"service.py": _F13_IMPORT,
                                               "interface.py": "X = 1\n"})
        _md_module(modules_dir, "billing", billing_files)
        manifest_path = root / "module-manifest.json"
        manifest_path.write_text(json.dumps(_md_manifest(_F13_MODULES)))
        return ["--gate", "module-deps", "--modules-dir", str(modules_dir),
                "--module-manifest", str(manifest_path)]

    absent = {"interfcae.py": "def preview_charge(m):\n    return None\n"}
    present = {"interface.py": "def preview_charge(m):\n    return None\n"}

    with tempfile.TemporaryDirectory() as tmp:
        code, out = _cli(write_tree(Path(tmp), absent))
    assert code == 2, out
    assert "[module-deps] ERROR" in out, out
    assert "MODULE_DEPS_GATE_INPUT_INVALID" in out, out
    assert "'app.modules.billing.interface'" in out, out
    assert "does not resolve to an existing module file or package" in out, out
    assert "[module-deps] PASS" not in out, out

    with tempfile.TemporaryDirectory() as tmp:
        json_code, json_out = _cli(write_tree(Path(tmp), absent) + ["--json"])
    assert json_code == 2, json_out
    payload = json.loads(json_out)
    assert payload["status"] == ERROR, payload
    assert [v["code"] for v in payload["violations"]] == \
        ["MODULE_DEPS_GATE_INPUT_INVALID"], payload

    # Positive control on the identical argv path: the only difference is the filename.
    with tempfile.TemporaryDirectory() as tmp:
        ok_code, ok_out = _cli(write_tree(Path(tmp), present))
    assert ok_code == 0, ok_out
    assert "[module-deps] PASS" in ok_out, ok_out


def test_f13_parse_module_manifest_requires_the_modules_dir():
    """The signature guard. A `modules_dir=None` default would have made "the caller
    forgot to thread the tree" silently equivalent to "skip the existence check" --
    the fail-open shape this rule exists to close -- so the argument is required."""
    import inspect

    sig = inspect.signature(parse_module_manifest)
    param = sig.parameters["modules_dir"]
    assert param.default is inspect.Parameter.empty, sig
    assert sig.parameters["modules_dir"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD, sig
    assert "modules_dir" in inspect.signature(load_module_manifest).parameters
    assert inspect.signature(load_module_manifest).parameters["modules_dir"].default is \
        inspect.Parameter.empty


# --- ADR-011 D7.4 dedup + deterministic ordering (gate-2 R2-N03 / R1-F15 / R1-F20) ---
#
# Both end-to-end rows below are the round-3 reviewer's own reproducers, re-expressed as
# fixtures. Before this increment the first emitted two byte-identical violation rows and
# the second emitted in source order.


def test_d74_duplicate_identical_cross_domain_join_rows_collapse_to_one():
    """R2-N03 reproducer 1: `SELECT a FROM bil_invoices JOIN bil_invoices ON 1=1`.

    Both JOIN operands are the same other-module table in the same statement, so
    both produce the same `(code, subject, detail)` -- the `detail` prefix is the
    file:line `loc`, identical for every identifier in one literal. D7.4 collapses
    them to one emitted row.

    The D3.2 state-2 counter is asserted at **2** in the same breath: D7.4 is an
    emission-ordering rule, and the D8 attribution counters are accumulated by the
    scanner per identifier position, not read off the violation list. A "fix" that
    deduplicated by suppressing the second attribution instead would move this
    figure to 1 and fail here -- which is the real risk, since under-extraction is
    exactly what R2-N01 was."""
    report = _f12b_run(
        {"service.py": 'Q = "SELECT a FROM bil_invoices JOIN bil_invoices ON 1=1"\n'}
    )
    assert report.status == FAIL, report.render()
    assert report.exit_code == 1, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    assert len(cross) == 1, report.render()
    assert cross[0].subject == "membership -> billing", cross[0]
    assert "'bil_invoices'" in cross[0].detail, cross[0]
    counts = _f12b_counts(report)
    assert counts["other"] == 2, counts   # per-position attribution is NOT deduplicated
    assert counts["own"] == 0, counts


def test_d74_violation_rows_ordered_by_key_not_source_order():
    """R2-N03 reproducer 2: `bil_zeta` emitted before `bil_alpha`, ordered by
    `(code, subject, detail)` rather than by when the scanner found them.

    Both identifiers sit in **one** statement deliberately. `detail` opens with the
    file:line `loc`, so two separate literals would differ in their line number
    first and the key order would merely coincide with source order -- proving
    nothing. Within a single `loc` the keys differ only in the table name, so
    reverse-alphabetical source order (`zeta`, then `alpha`) and key order
    (`alpha`, then `zeta`) genuinely disagree, and only the latter may be emitted.

    Determinism is asserted as a repeat run over an independently built tree, so a
    result that happened to be stable only within one `os.scandir` yield order
    cannot pass."""
    files = {"service.py": 'Q = "SELECT a FROM bil_zeta, bil_alpha"\n'}
    report = _f12b_run(files)
    assert report.status == FAIL, report.render()
    assert report.codes() == {"CROSS_DOMAIN_SQL_IMPORT"}, report.render()
    cross = [v for v in report.violations if v.code == "CROSS_DOMAIN_SQL_IMPORT"]
    assert len(cross) == 2, report.render()
    assert [v.subject for v in cross] == ["membership -> billing"] * 2, cross
    assert "'bil_alpha'" in cross[0].detail, report.render()
    assert "'bil_zeta'" in cross[1].detail, report.render()
    assert cross[0].detail < cross[1].detail, cross
    # Same key, same order on a second, independently created tree.
    again = [v.detail for v in _f12b_run(files).violations]
    assert again == [v.detail for v in cross], again


def test_d74_dedupe_order_dedupes_and_orders_the_error_class_lists():
    """The `uninspectable` and `unattributed` lists at the narrowest level that
    exists: the one helper both are passed through. Reaching these two shapes
    end-to-end would need a fixture that also plants a second, unrelated
    uninspectable construct purely to force a duplicate, which tests the fixture
    rather than the rule.

    Input is duplicated **and** reverse-ordered in both lists. Output must be the
    distinct keys only, in `(code, subject, detail)` order."""
    uninspectable = [
        Violation("MODULE_DEPS_SOURCE_UNINSPECTABLE", "m/z.py:9", "f-string SQL"),
        Violation("MODULE_DEPS_SOURCE_UNINSPECTABLE", "m/a.py:1", "f-string SQL"),
        Violation("MODULE_DEPS_SOURCE_UNINSPECTABLE", "m/z.py:9", "f-string SQL"),
    ]
    ordered = _d74_dedupe_order(uninspectable)
    assert [v.subject for v in ordered] == ["m/a.py:1", "m/z.py:9"], ordered

    unattributed = [
        Violation("MODULE_DEPS_TABLE_UNATTRIBUTED", "m/s.py:2", "table 'zz': unowned"),
        Violation("MODULE_DEPS_TABLE_UNATTRIBUTED", "m/s.py:2", "table 'aa': unowned"),
        Violation("MODULE_DEPS_TABLE_UNATTRIBUTED", "m/s.py:2", "table 'zz': unowned"),
    ]
    ordered = _d74_dedupe_order(unattributed)
    assert [v.detail for v in ordered] == \
        ["table 'aa': unowned", "table 'zz': unowned"], ordered

    # Codes sort before subject/detail, so a mixed list never interleaves them --
    # which is what keeps D7.1's two disjoint ERROR codes separable in the report.
    mixed = _d74_dedupe_order(uninspectable + unattributed)
    assert [v.code for v in mixed] == ["MODULE_DEPS_SOURCE_UNINSPECTABLE"] * 2 + \
        ["MODULE_DEPS_TABLE_UNATTRIBUTED"] * 2, mixed
    assert _d74_dedupe_order([]) == []


def test_d74_dedupe_order_preserves_the_first_seen_row_within_a_key():
    """D7.4's "first-seen order preserved within a key" half.

    `Violation` is a frozen record whose three fields *are* the key, so duplicates
    compare equal and the only observable difference is object identity -- which is
    precisely why it is pinned: the retained row must be the first occurrence, so
    any future per-occurrence field on `Violation` is not silently overwritten by
    the last duplicate. Asserted with `is`, since `==` cannot see it.

    The coverage helper is checked alongside to pin that the two contracts stay
    **distinct**: `_dedupe_coverage_violations` keeps its own narrower last-seen,
    subject-only-ordered behaviour for the single coverage ERROR code, and this
    increment did not fold it into the general rule."""
    first = Violation("CROSS_DOMAIN_SQL_IMPORT", "membership -> billing", "x")
    later = Violation("CROSS_DOMAIN_SQL_IMPORT", "membership -> billing", "x")
    assert first == later and first is not later  # equal rows, distinct objects

    kept = _d74_dedupe_order([first, later])
    assert len(kept) == 1, kept
    assert kept[0] is first, "D7.4 must keep the first-seen row, not the last"

    cov_first = Violation("MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH", "pkg", "y")
    cov_later = Violation("MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH", "pkg", "y")
    cov_kept = _dedupe_coverage_violations([cov_first, cov_later])
    assert len(cov_kept) == 1, cov_kept
    assert cov_kept[0] is cov_later, "the coverage helper's last-seen contract is unchanged"


# --- screen-contract gate (TSD §24.1 gate 5; SCN-MOD001-012/013/110) ----------

# Real canonical Screen ID shapes, not the legacy synthetic `SCR-NNN` form.
# Gate check 8 regenerates the manifest from the canonical registry source, and
# the generator derives a row's surface from the ID prefix -- `SCR-` maps to
# backend/no-UI, which is never a manifest row at all, so no `SCR-NNN` row can
# be generated. `SCR-NNN` stays accepted by `_SCREEN_ID_RE` and by the manifest
# parser (see the `_SCREEN_ID_RE` tests and the malformed-document fixtures
# below, which still use it); it just cannot reach a source-bound PASS.
# `SCR1`'s surface is `SC_SURFACE` (`_sc_row`'s default); `SCR2`'s is Member, so
# a fixture carrying it passes `surface="Member"`.
SCR1 = "ADM-CC-01"
SCR2 = "MBR-01"
SC_OWNER = "MOD-020"
SC_WAVE = "W2"
SC_DOMAIN = "MBR-01"
SC_REGISTRY_MODULE = "Members"
SC_UNRESOLVED_REASON = "NO_TSD_OWNER_DOMAIN_IN_SOURCE_METADATA"
# Surface of a synthetic row; any of the five ADR-014 D2.3 targets will do.
SC_SURFACE = "Admin"

# --- source-bound fixtures (ADR-014 D2.1/D2.4, gate check 8) -----------------
# The gate regenerates the manifest from the canonical registry source and the
# EIP Appendix F module table and requires byte identity, so a synthetic run has
# to supply synthetic versions of *those* two inputs as well -- otherwise every
# fixture would be compared against the real 170-row tree. `_sc_run` therefore
# derives both from what the fixture asked for: a conforming fixture regenerates
# byte-identically, so PASS stays reachable (ADR-014 D1.3's fixture self-test
# needs a conforming fixture that passes), while every deliberate deviation now
# also drifts.
#
# One deliberate consequence: a `BOUND` row is no longer reachable as a PASS.
# ADR-014 D2.5 has the generator emit `UNBOUND` in every binding field until the
# owning module is implemented, so a BOUND row cannot regenerate from any source.
# The two former BOUND-PASS positives below are now source-drift negatives.

SC_SYS_ROWS = 8  # `build_canonical_rows` requires exactly the eight SYS-* rows

# The module table speaks EIP Appendix F's *module*-surface vocabulary, which
# the generator's `MODULE_SURFACE_MAP` translates into the five count-model
# surfaces -- all five here, so a synthetic owner can own a row on any surface.
SC_EIP_SURFACES = "Admin Web, Front Desk, Coach App, Member App, Internal SaaS Console"
# Fixed-width columns of the Appendix F module table, in `parse_module_table`'s
# header-token order. The header line is built from these same widths, so the
# column offsets it reads are exactly the ones the data rows were padded to.
_SC_EIP_COLUMNS = (
    ("**Module**", 14),
    ("**Wave**", 14),
    ("**TSD domain(s)**", 20),
    ("**UI / surface ownership**", 72),
    ("**Canonical screen mapping rule**", 36),
    ("**Ready-state requirement**", 0),  # last column, unpadded
)


def _sc_module_table_digest(eip_text):
    """`generated_from.eip_appendix_f_module_table_sha256` as the generator
    computes it (a digest of the parsed table, not of the file), so a conforming
    fixture declares the same provenance the regeneration will."""
    import generate_screen_contract_manifest as gen

    return gen.module_table_digest(gen.parse_module_table(eip_text))


def _sc_source_text(screen_ids, unresolved=()):
    """A `veyro-registry-data.js` body in the frozen export's exact 8-field row
    shape. A row carries a TSD domain code in its last field only when that
    screen is meant to resolve to an owner -- the real export carries none for
    any row, which is why the live tree's 170 rows are all UNRESOLVED."""
    unresolved = set(unresolved)
    rows = [f"  ['{sid}','{SC_REGISTRY_MODULE}','Synthetic','V1','OK','role','ar',"
            f"'{'-' if sid in unresolved else SC_DOMAIN}'],"
            for sid in screen_ids]
    rows += [f"  ['SYS-0{n}','Sys','Backend','V1','OK','role','ar','-'],"
             for n in range(1, SC_SYS_ROWS + 1)]
    return "export const R = [\n" + "\n".join(rows) + "\n];\n"


def _sc_eip_row(cells):
    line = ""
    for (_, width), text in zip(_SC_EIP_COLUMNS, cells):
        assert width == 0 or len(text) < width, (text, width)
        line += text if width == 0 else text.ljust(width)
    return line.rstrip()


def _sc_eip_text(owners=()):
    """A minimal EIP Appendix F module table in the mirror's own fixed-width
    layout. MOD-001 is always present and always Non-UI -- it owns zero
    canonical screens -- and each owning module carries the domain and surfaces
    that make the Appendix F rule resolve its rows to it."""
    dashes = " ".join("-" * 12 for _ in _SC_EIP_COLUMNS)
    lines = [
        "# Appendix F. Canonical Screen-to-Module Mapping",
        "",
        _sc_eip_row([token for token, _ in _SC_EIP_COLUMNS]),
        dashes,
        _sc_eip_row(["MOD-001", "Foundation", "Program gate", "Non-UI / none", "-", "-"]),
    ]
    lines += [_sc_eip_row([owner, SC_WAVE, SC_DOMAIN, SC_EIP_SURFACES, "-", "-"])
              for owner in owners]
    lines += [dashes, ""]
    return "\n".join(lines)


def _sc_row(screen_id, surface=SC_SURFACE, owner=SC_OWNER, bound=False, **overrides):
    """One ADR-014 D2 manifest row, in `_SCREEN_ROW_KEYS` order. `owner=None`
    builds the UNRESOLVED shape the generator actually emits today; `bound=True`
    builds the staged-binding-complete shape of a future owning module."""
    resolved = owner is not None
    row = {
        "screen_id": screen_id,
        "surface": surface,
        "registry_module": "Members",
        "owning_module": owner,
        "wave": SC_WAVE if resolved else None,
        "owner_domain": SC_DOMAIN if resolved else None,
        "owner_resolution": {
            "status": "RESOLVED" if resolved else "UNRESOLVED",
            "reason": None if resolved else SC_UNRESOLVED_REASON,
        },
        "binding_status": SCREEN_BOUND if bound else SCREEN_UNBOUND,
    }
    for name in SCREEN_BINDING_FIELDS:
        row[name] = f"bound:{name}" if bound else SCREEN_UNBOUND
    row.update(overrides)
    return row


def _sc_manifest(rows=(), *, registry_ids=None, module_screens=None,
                 source_sha256="a" * 64, eip_sha256="b" * 64, **overrides):
    """The generated manifest object. `registry_ids` is what the *registry* holds
    (the provenance digest is taken over those, not over the manifest's rows), so
    a count-mismatch fixture still carries honest provenance. `source_sha256` and
    `eip_sha256` default to well-shaped placeholders for the parser-only
    fixtures; `_sc_run` passes the real digests of the synthetic source and
    module table so a conforming fixture can regenerate byte-identically."""
    rows = list(rows)
    if registry_ids is None:
        registry_ids = [r["screen_id"] for r in rows]
    if module_screens is None:
        module_screens = {"MOD-001": []}
        for row in rows:
            if row["owning_module"]:
                module_screens.setdefault(row["owning_module"], []).append(row["screen_id"])
    manifest = {
        "version": 1,
        "generated_from": {
            "registry_source": _SCREEN_PROVENANCE_PATHS["registry_source"],
            "registry_source_sha256": source_sha256,
            "screen_registry_json": _SCREEN_PROVENANCE_PATHS["screen_registry_json"],
            "screen_registry_json_ids_sha256": hashlib.sha256(
                "\n".join(registry_ids).encode("utf-8")).hexdigest(),
            "eip_appendix_f_module_table":
                _SCREEN_PROVENANCE_PATHS["eip_appendix_f_module_table"],
            "eip_appendix_f_module_table_sha256": eip_sha256,
        },
        "counts": {
            "total": len(rows),
            "by_surface": {s: sum(1 for r in rows if r["surface"] == s) for s in SCREEN_SURFACES},
        },
        "module_screens": module_screens,
        "screens": rows,
    }
    manifest.update(overrides)
    return manifest


def _sc_contracts_text(rows=(), **kwargs):
    # `ensure_ascii=False` matches `render_manifest`, so a conforming fixture is
    # byte-identical to regeneration rather than merely equal as data.
    return json.dumps(_sc_manifest(rows, **kwargs), indent=2, ensure_ascii=False) + "\n"


def _sc_sources(ids, rows):
    """The synthetic generation sources for a fixture: a registry source whose
    rows are exactly the registry's Screen IDs (carrying a TSD domain code only
    for the rows the fixture means to resolve), and a module table holding
    MOD-001 plus whichever owners the fixture's rows name."""
    unresolved = [r["screen_id"] for r in rows if not r["owning_module"]]
    owners = list(dict.fromkeys(r["owning_module"] for r in rows if r["owning_module"]))
    return _sc_source_text(ids, unresolved), _sc_eip_text(owners)


import contextlib as _sc_contextlib
from unittest import mock as _sc_mock

import generate_screen_contract_manifest as _sc_gen


@_sc_contextlib.contextmanager
def _sc_expect_surfaces(surfaces):
    """Scope the generator's canonical EXPECTED_TOTAL / EXPECTED_BY_SURFACE to a
    small synthetic fixture. The gate reads them from the generator at call time,
    so the 170 / 85-16-19-35-15 absolutes stay the generator's own and are never
    restated in the gate; real-tree and disposable-copy tests do not use this."""
    surfaces = list(surfaces)
    with _sc_mock.patch.object(_sc_gen, "EXPECTED_TOTAL", len(surfaces)), \
            _sc_mock.patch.object(_sc_gen, "EXPECTED_BY_SURFACE",
                                  {s: surfaces.count(s) for s in _sc_gen.EXPECTED_BY_SURFACE}):
        yield


def _sc_expect_source(source_text):
    try:
        surfaces = [r.surface for r in _sc_gen.build_canonical_rows(source_text)]
    except _sc_gen.GenerationError:
        surfaces = []  # unparseable: the run ERRORs before the count check
    return _sc_expect_surfaces(surfaces)


def _sc_synthetic_single_admin(fn):
    """Decorator for direct-call tests built on the one-row `SCR1` fixture."""
    import functools

    @functools.wraps(fn)
    def wrapper(*a, **kw):
        with _sc_expect_surfaces([SC_SURFACE]):
            return fn(*a, **kw)
    return wrapper


def _sc_run(screens=None, rows=(), registry_raw=None, contracts_text=None,
            implemented=(), source_text=None, eip_text=None, **manifest_kwargs):
    ids = list(screens or [])
    rows = list(rows)
    synth_source, synth_eip = _sc_sources(ids, rows)
    source_text = synth_source if source_text is None else source_text
    eip_text = synth_eip if eip_text is None else eip_text
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reg_path = root / "screen-registry.json"
        reg_path.write_text(json.dumps(
            registry_raw if registry_raw is not None else {"version": 1, "screens": ids}
        ))
        source_path = root / "veyro-registry-data.js"
        source_path.write_text(source_text)
        eip_path = root / "EIP_MIRROR.md"
        eip_path.write_text(eip_text)
        contracts_path = root / "screen-contracts.yaml"
        contracts_path.write_text(
            contracts_text if contracts_text is not None
            else _sc_contracts_text(
                rows, registry_ids=ids,
                source_sha256=hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
                eip_sha256=_sc_module_table_digest(eip_text),
                **manifest_kwargs)
        )
        with _sc_expect_source(source_text):
            return run_screen_contract_gate(reg_path, contracts_path, frozenset(implemented),
                                            source_path, eip_path)


# --- positive controls. Note what a PASS here does and does not mean: ADR-014
# D2.6 stages per-row binding, so an UNBOUND row whose owner is not marked
# implemented does not block. The gate discloses the UNBOUND count in its notes
# on every run so a PASS can never be read as "binding proven". ---------------

def test_screen_contract_mapped_screen_passes():
    """SCN-MOD001-012: a canonical Screen ID carried as a conforming manifest row
    with a resolved owner passes."""
    report = _sc_run([SCR1], [_sc_row(SCR1)])
    assert report.status == PASS, report.render()
    assert report.checked == [SCR1]


def test_screen_contract_pass_discloses_staged_unbound_rows():
    report = _sc_run([SCR1], [_sc_row(SCR1)])
    assert report.status == PASS, report.render()
    notes = " ".join(report.notes)
    assert "1 of 1 manifest row(s) carry binding_status UNBOUND" in notes, notes
    assert "proves no binding" in notes, notes
    assert "0 of 1 row(s) carry owner_resolution UNRESOLVED" in notes, notes


def test_screen_contract_multiple_rows_pass():
    report = _sc_run([SCR1, SCR2], [_sc_row(SCR1), _sc_row(SCR2, surface="Member")])
    assert report.status == PASS, report.render()


def test_screen_contract_bound_row_is_source_drift_not_pass():
    """A BOUND row is accepted *structurally* (checks 1-7 only verify that the
    binding fields agree with `binding_status`; no repository artifact defines
    the bound-value grammar, which the notes must keep saying). Under check 8 it
    can no longer reach PASS: ADR-014 D2.5 has the generator emit UNBOUND in
    every binding field until the owning module is implemented, so no BOUND row
    regenerates from any source. Hand-written bindings fail closed."""
    report = _sc_run([SCR1], [_sc_row(SCR1, bound=True)])
    assert report.status == FAIL, report.render()
    assert "SCREEN_CONTRACT_SOURCE_DRIFT" in report.codes(), report.render()
    notes = " ".join(report.notes)
    assert "BOUND row(s) present" in notes, notes
    assert "recorded here, not verified" in notes, notes


# --- identity (FAIL) --------------------------------------------------------

def test_screen_contract_unmapped_id_fails_citing_id():
    """SCN-MOD001-013: a canonical Screen ID with no manifest row denies, citing it."""
    report = _sc_run([SCR1, SCR2], [_sc_row(SCR1)])
    assert report.status == FAIL, report.render()
    unmapped = [v for v in report.violations if v.code == "UNMAPPED_SCREEN_CONTRACT"]
    assert len(unmapped) == 1, report.render()
    assert unmapped[0].subject == SCR2


def test_screen_contract_count_mismatch_fails_citing_expected_and_actual():
    """SCN-MOD001-110: canonical registry count vs. generated manifest count."""
    report = _sc_run([SCR1, SCR2], [_sc_row(SCR1)])
    assert report.status == FAIL, report.render()
    mismatches = [v for v in report.violations if v.code == "SCREEN_CONTRACT_COUNT_MISMATCH"]
    assert len(mismatches) == 1, report.render()
    assert "expected 2" in mismatches[0].detail and "actual 1" in mismatches[0].detail


def test_screen_contract_extra_generated_row_is_count_mismatch_and_invented():
    """A generator emitting an extra row with no corresponding canonical screen
    must not vacuously pass merely because every canonical ID is mapped. The row
    is now also cited individually as invented (EIP Appendix F's
    forbidden-placeholder rule), which the count mismatch alone did not do, and
    as source drift, since the extra row is in no source."""
    report = _sc_run([SCR1], [_sc_row(SCR1), _sc_row(SCR2, surface="Member")])
    assert report.status == FAIL, report.render()
    assert report.codes() == {"SCREEN_CONTRACT_COUNT_MISMATCH",
                              "SCREEN_CONTRACT_CANONICAL_COUNT_MISMATCH",
                              "SCREEN_CONTRACT_INVENTED_SCREEN_ID",
                              "SCREEN_CONTRACT_SOURCE_DRIFT"}, report.render()
    invented = [v for v in report.violations if v.code == "SCREEN_CONTRACT_INVENTED_SCREEN_ID"]
    assert [v.subject for v in invented] == [SCR2], report.render()


def test_screen_contract_provenance_digest_mismatch_fails():
    """The manifest declares which registry's Screen IDs it was generated from.
    A manifest generated against a different registry must not be read as if it
    had been generated against this run's."""
    text = _sc_contracts_text([_sc_row(SCR1)], registry_ids=[SCR1, SCR2])
    report = _sc_run(screens=[SCR1], contracts_text=text)
    assert report.status == FAIL, report.render()
    assert "SCREEN_CONTRACT_PROVENANCE_MISMATCH" in report.codes(), report.render()
    mismatch = next(v for v in report.violations
                    if v.code == "SCREEN_CONTRACT_PROVENANCE_MISMATCH")
    assert "not generated from the registry it is being checked against" in mismatch.detail


def test_screen_contract_unresolved_owner_fails_citing_id():
    """ADR-014 D2.4: every row's owner must resolve now. The gate must fail
    closed rather than infer an owner -- inference is the hand assignment D2.4
    forbids -- and must cite each unresolved Screen ID."""
    report = _sc_run([SCR1, SCR2], [_sc_row(SCR1, owner=None), _sc_row(SCR2)])
    assert report.status == FAIL, report.render()
    unresolved = [v for v in report.violations if v.code == "SCREEN_CONTRACT_OWNER_UNRESOLVED"]
    assert [v.subject for v in unresolved] == [SCR1], report.render()
    assert "never guesses one" in unresolved[0].detail


def test_screen_contract_missing_mod_001_entry_fails():
    """ADR-014 D2.4 requires the explicit `"MOD-001": []` entry: MOD-001 owning
    zero canonical screens has to be stated, not left absent."""
    report = _sc_run([SCR1], [_sc_row(SCR1)], module_screens={SC_OWNER: [SCR1]})
    assert report.status == FAIL, report.render()
    assert "SCREEN_CONTRACT_MOD_001_ENTRY_INVALID" in report.codes(), report.render()


def test_screen_contract_module_index_mismatch_fails_citing_module():
    report = _sc_run([SCR1], [_sc_row(SCR1)],
                     module_screens={"MOD-001": [], SC_OWNER: []})
    assert report.status == FAIL, report.render()
    drift = [v for v in report.violations if v.code == "SCREEN_CONTRACT_MODULE_INDEX_MISMATCH"]
    assert [v.subject for v in drift] == [SC_OWNER], report.render()


def test_screen_contract_module_index_omitting_an_owner_fails():
    """An owner that appears on a row but nowhere in `module_screens` must be
    caught too, not only an owner whose listed IDs differ."""
    report = _sc_run([SCR1], [_sc_row(SCR1)], module_screens={"MOD-001": []})
    assert report.status == FAIL, report.render()
    drift = [v for v in report.violations if v.code == "SCREEN_CONTRACT_MODULE_INDEX_MISMATCH"]
    assert [v.subject for v in drift] == [SC_OWNER], report.render()


# --- ADR-014 D2.6 staged binding --------------------------------------------

def test_screen_contract_unbound_row_with_implemented_owner_fails():
    report = _sc_run([SCR1], [_sc_row(SCR1)], implemented=[SC_OWNER])
    assert report.status == FAIL, report.render()
    unbound = [v for v in report.violations if v.code == "SCREEN_CONTRACT_ROW_UNBOUND"]
    assert [v.subject for v in unbound] == [SCR1], report.render()
    assert "ADR-014 D2.6" in unbound[0].detail


def test_screen_contract_unbound_row_with_unimplemented_owner_is_staged():
    """The other half of D2.6: while the owning module is not marked implemented
    the row's binding check is staged, so it must not FAIL -- and the run must
    still disclose that nothing about binding was proven."""
    report = _sc_run([SCR1], [_sc_row(SCR1)], implemented=["MOD-099"])
    assert report.status == PASS, report.render()
    assert "SCREEN_CONTRACT_ROW_UNBOUND" not in report.codes(), report.render()
    assert "['MOD-099']" in " ".join(report.notes), report.notes


def test_screen_contract_bound_row_with_implemented_owner_is_source_drift_not_pass():
    """D2.6's satisfied half must not become a way in either: naming the owning
    module implemented clears `SCREEN_CONTRACT_ROW_UNBOUND`, but the bindings
    still have to come from the generator, so the row drifts instead of passing.
    Until the generator can emit a bound row for an implemented module, a
    hand-written binding is not proof of binding."""
    report = _sc_run([SCR1], [_sc_row(SCR1, bound=True)], implemented=[SC_OWNER])
    assert report.status == FAIL, report.render()
    assert report.codes() == {"SCREEN_CONTRACT_SOURCE_DRIFT"}, report.render()


def test_screen_contract_malformed_implemented_module_flag_is_error():
    report = _sc_run([SCR1], [_sc_row(SCR1)], implemented=["mod-020"])
    assert report.status == ERROR, report.render()
    assert report.codes() == {"SCREEN_CONTRACT_GATE_INPUT_INVALID"}


# --- vacuous / missing inputs -----------------------------------------------

def test_screen_contract_empty_registry_is_inconclusive_not_pass():
    """MOD-001 owns zero real screens (`REQUIREMENTS.md` §4) -- that disclosed
    fact must read as INCONCLUSIVE, never as a silent PASS."""
    report = _sc_run([], [])
    assert report.status == INCONCLUSIVE, report.render()
    assert report.exit_code == 2
    assert report.codes() == {"SCREEN_CONTRACT_GATE_VACUOUS"}


def test_screen_contract_empty_registry_with_generated_rows_is_count_mismatch():
    """Zero canonical screens is only vacuous when the generated manifest is also
    empty -- a nonempty manifest against zero canonical screens is a real
    mismatch, not a silent pass."""
    report = _sc_run([], [_sc_row(SCR1)])
    assert report.status == FAIL, report.render()
    assert report.codes() == {"SCREEN_CONTRACT_COUNT_MISMATCH",
                              "SCREEN_CONTRACT_CANONICAL_COUNT_MISMATCH",
                              "SCREEN_CONTRACT_INVENTED_SCREEN_ID",
                              "SCREEN_CONTRACT_SOURCE_DRIFT"}, report.render()


def test_screen_contract_missing_inputs_are_error():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert run_screen_contract_gate(root / "nope.json", root / "nope.yaml").status == ERROR
        reg = root / "screen-registry.json"
        reg.write_text(json.dumps({"version": 1, "screens": []}))
        assert run_screen_contract_gate(reg, root / "nope.yaml").status == ERROR


def test_screen_contract_malformed_registry_is_error_not_vacuous_pass():
    bad_registries = [
        {"version": 2, "screens": []},
        {"version": 1, "screens": [], "extra": 1},
        {"version": 1, "screens": "SCR-001"},
        {"version": 1, "screens": ["scr-001"]},
        {"version": 1, "screens": ["SCR-001", "SCR-001"]},
        "not an object",
        [],
    ]
    for raw in bad_registries:
        report = _sc_run(registry_raw=raw, rows=[])
        assert report.status == ERROR, (raw, report.render())
        assert report.codes() == {"SCREEN_CONTRACT_GATE_INPUT_INVALID"}, (raw, report.render())


def test_screen_contract_legacy_two_field_shape_is_rejected():
    """The pre-ADR-014 `id`/`target` form -- including the body that used to be
    the gate's one accepted PASS shape -- is no longer a second, weaker accepted
    shape for the same CI-blocking artifact. It cannot carry TSD Appendix F's
    mandatory fields, and a four-field synthetic subset reading as PASS was
    itself found to be a false-completeness affordance
    (`R04-GATE5-PARTIAL-CANONICAL-OUTPUT-DENIAL`)."""
    legacy = ("version: 1\nscreens:\n"
              "  - id: SCR-001\n    target: bff:members.profile_read\n")
    report = _sc_run(screens=[SCR1], contracts_text=legacy)
    assert report.status == ERROR, report.render()
    assert report.codes() == {"SCREEN_CONTRACT_GATE_INPUT_INVALID"}
    assert "unparseable manifest" in report.violations[0].detail


def test_screen_contract_malformed_contracts_file_is_error_not_vacuous_pass():
    """Every pre-ADR-014 body that was already refused stays refused (these are
    not JSON, so they never reach the manifest schema), alongside the real
    shape's own malformed cases."""
    bad_bodies = [
        "",
        "version: 2\nscreens:\n",
        "version: 1\n",
        "version: 1\nscreens:\n  - id: SCR-001\n",
        "version: 1\nscreens:\n- id: SCR-001\n  target: bff:a\n",
        "version: 1\nscreens:\n  - id: scr-001\n    target: bff:a\n",
        "version: 1\nscreens:\n  - id: SCR-001\n    target: rest:a\n",
        "version: 1\nscreens:\n  - id: SCR-001\n    target: bff:a\n  - id: SCR-001\n    target: bff:b\n",
        "version: 1\nscreens:\n  - id: SCR-001\n    target: bff:a\ntrailing garbage\n",
        "[]",
        "null",
        "{}",
        '{"version": 1, "screens": []}',
        json.dumps(_sc_manifest([_sc_row(SCR1)])) + "\ntrailing garbage\n",
        # duplicate JSON key: `json.loads` would silently keep the last one.
        ('{"version": 1, "version": 1, "generated_from": {}, "counts": {},'
         ' "module_screens": {}, "screens": []}'),
    ]
    for body in bad_bodies:
        report = _sc_run(screens=["SCR-001"], contracts_text=body)
        assert report.status == ERROR, (body, report.render())
        assert report.codes() == {"SCREEN_CONTRACT_GATE_INPUT_INVALID"}, (body, report.render())


def test_screen_contract_manifest_schema_deviations_are_error():
    """Schema/provenance deviations fail closed as ERROR: a row, a binding field
    or a provenance field is never dropped, defaulted, or read in whichever
    direction would pass."""
    row_without_a_binding_field = _sc_row(SCR1)
    del row_without_a_binding_field["masking_variant"]
    reordered = _sc_row(SCR1)
    reordered["screen_id"] = reordered.pop("screen_id")  # moves the key to the end
    bad_manifests = [
        # top level
        _sc_manifest([_sc_row(SCR1)], version=2),
        _sc_manifest([_sc_row(SCR1)], version=True),
        _sc_manifest([_sc_row(SCR1)], screens={}),
        # provenance
        _sc_manifest([_sc_row(SCR1)], generated_from={}),
        _sc_manifest([_sc_row(SCR1)], generated_from=dict(
            _sc_manifest()["generated_from"], registry_source="somewhere/else.js")),
        _sc_manifest([_sc_row(SCR1)], generated_from=dict(
            _sc_manifest()["generated_from"], registry_source_sha256="A" * 64)),
        _sc_manifest([_sc_row(SCR1)], generated_from=dict(
            _sc_manifest()["generated_from"], screen_registry_json_ids_sha256="deadbeef")),
        # counts disagreeing with the rows
        _sc_manifest([_sc_row(SCR1)], counts={"total": 2, "by_surface": {
            s: (1 if s == SC_SURFACE else 0) for s in SCREEN_SURFACES}}),
        _sc_manifest([_sc_row(SCR1)], counts={"total": 1, "by_surface": {
            s: 0 for s in SCREEN_SURFACES}}),
        _sc_manifest([_sc_row(SCR1)], counts={"total": 1}),
        # rows
        _sc_manifest([row_without_a_binding_field]),
        _sc_manifest([reordered]),
        _sc_manifest([_sc_row(SCR1), _sc_row(SCR1)]),
        _sc_manifest([_sc_row(SCR1, surface="Veyro Admin")]),
        _sc_manifest([_sc_row("scr-001")]),
        _sc_manifest([_sc_row(SCR1, registry_module="")]),
        # owner_resolution disagreeing with the ownership fields
        _sc_manifest([_sc_row(SCR1, owner=None, owning_module=SC_OWNER)]),
        _sc_manifest([_sc_row(SCR1, owner=None, owner_resolution={
            "status": "UNRESOLVED", "reason": None})]),
        _sc_manifest([_sc_row(SCR1, owning_module=None)]),
        _sc_manifest([_sc_row(SCR1, wave=None)]),
        _sc_manifest([_sc_row(SCR1, owner_domain=None)]),
        _sc_manifest([_sc_row(SCR1, owner_resolution={
            "status": "RESOLVED", "reason": "why"})]),
        _sc_manifest([_sc_row(SCR1, owner_resolution={"status": "PARTIAL", "reason": None})]),
        _sc_manifest([_sc_row(SCR1, owner_resolution={"status": "RESOLVED"})]),
        # binding fields disagreeing with binding_status
        _sc_manifest([_sc_row(SCR1, binding_status="PENDING")]),
        _sc_manifest([_sc_row(SCR1, route="bff:members.profile_read")]),
        _sc_manifest([_sc_row(SCR1, bound=True, route=SCREEN_UNBOUND)]),
        _sc_manifest([_sc_row(SCR1, bound=True, route="")]),
        _sc_manifest([_sc_row(SCR1, route=None)]),
        # module index
        _sc_manifest([_sc_row(SCR1)], module_screens={"mod-020": [SCR1]}),
        _sc_manifest([_sc_row(SCR1)], module_screens={"MOD-001": [], SC_OWNER: [SCR1, SCR1]}),
        _sc_manifest([_sc_row(SCR1)], module_screens={"MOD-001": [], SC_OWNER: "SCR-001"}),
        _sc_manifest([_sc_row(SCR1)], module_screens=[]),
    ]
    for manifest in bad_manifests:
        report = _sc_run(screens=[SCR1],
                         contracts_text=json.dumps(manifest, indent=2) + "\n")
        assert report.status == ERROR, (manifest, report.render())
        assert report.codes() == {"SCREEN_CONTRACT_GATE_INPUT_INVALID"}, (manifest, report.render())


def test_screen_contract_symlinked_inputs_are_error():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        real_reg = root / "real-registry.json"
        real_reg.write_text(json.dumps({"version": 1, "screens": []}))
        link_reg = root / "screen-registry.json"
        link_reg.symlink_to(real_reg)
        contracts = root / "screen-contracts.yaml"
        contracts.write_text(_sc_contracts_text([]))
        assert run_screen_contract_gate(link_reg, contracts).status == ERROR

        real_contracts = root / "real-contracts.yaml"
        real_contracts.write_text(_sc_contracts_text([]))
        link_contracts = root / "screen-contracts-link.yaml"
        link_contracts.symlink_to(real_contracts)
        reg2 = root / "registry2.json"
        reg2.write_text(json.dumps({"version": 1, "screens": []}))
        assert run_screen_contract_gate(reg2, link_contracts).status == ERROR


def test_screen_contract_parse_registry_rejects_bad_entries():
    try:
        parse_screen_registry({"version": 1, "screens": [1]})
    except GateInputError:
        pass
    else:
        raise AssertionError("accepted a non-string Screen ID")


def test_screen_contract_parse_contracts_rejects_bound_row_with_unbound_field():
    try:
        parse_screen_contracts(_sc_contracts_text(
            [_sc_row(SCR1, bound=True, primary_read_model=SCREEN_UNBOUND)]))
    except GateInputError:
        pass
    else:
        raise AssertionError("accepted a BOUND row still carrying an UNBOUND field")


def test_screen_contract_parse_contracts_accepts_the_generated_shape():
    manifest = parse_screen_contracts(_sc_contracts_text([_sc_row(SCR1)]))
    assert [r.screen_id for r in manifest.rows] == [SCR1]
    assert manifest.rows[0].owning_module == SC_OWNER
    assert manifest.rows[0].binding_status == SCREEN_UNBOUND
    assert manifest.module_screens == {"MOD-001": [], SC_OWNER: [SCR1]}


def test_screen_contract_row_keys_are_the_appendix_f_mandatory_set():
    """TSD Appendix F (`TSD_MIRROR.md:17344-17347`) mandatory fields: the gate's
    row contract must require all of them, so a manifest cannot omit one."""
    appendix_f = {
        "screen_id", "surface", "route", "primary_read_model", "queries", "commands",
        "realtime_channels", "permissions", "assurance", "masking_variant",
        "offline_mode", "expected_error_codes", "empty_state", "loading_state",
        "error_state", "owner_domain",
    }
    assert appendix_f <= set(_SCREEN_ROW_KEYS), appendix_f - set(_SCREEN_ROW_KEYS)


def test_screen_contract_constants_match_the_generator():
    """The gate restates the generator's manifest vocabulary rather than
    importing it, to keep its stdlib-only import surface. Pin the two together
    so they cannot drift apart silently."""
    sys.path.insert(0, str(TOOLS))
    import generate_screen_contract_manifest as gen

    assert tuple(gen.EXPECTED_BY_SURFACE) == SCREEN_SURFACES
    assert gen.BINDING_FIELDS == SCREEN_BINDING_FIELDS
    assert gen.ROW_KEYS == _SCREEN_ROW_KEYS
    assert gen.UNBOUND == SCREEN_UNBOUND
    assert gen.OWNER_STATUSES == SCREEN_OWNER_STATUSES
    assert _SCREEN_PROVENANCE_PATHS == {
        "registry_source": gen.SOURCE_REL,
        "screen_registry_json": gen.REGISTRY_REL,
        "eip_appendix_f_module_table": gen.EIP_REL,
    }
    # Check 8's two generation sources are the generator's own inputs, so the
    # gate cannot end up regenerating from a different pair of files than the
    # one the manifest declares.
    assert DEFAULT_SCREEN_SOURCE == gen.DEFAULT_SOURCE
    assert DEFAULT_SCREEN_EIP == gen.DEFAULT_EIP
    assert DEFAULT_SCREEN_REGISTRY == gen.DEFAULT_REGISTRY
    assert DEFAULT_SCREEN_CONTRACTS == gen.DEFAULT_MANIFEST


def test_screen_contract_reads_the_committed_generated_manifest():
    """The defect this repair closes: the committed canonical manifest
    (`contracts/ui/screen-contracts.yaml`, generated under ADR-014 D2) was
    reported as `SCREEN_CONTRACT_GATE_INPUT_INVALID` ERROR because the gate only
    accepted the obsolete two-line form. It must now parse, and its disclosed
    UNRESOLVED owners must read as FAIL -- never as ERROR and never as PASS."""
    assert DEFAULT_SCREEN_REGISTRY.is_file(), DEFAULT_SCREEN_REGISTRY
    assert DEFAULT_SCREEN_CONTRACTS.is_file(), DEFAULT_SCREEN_CONTRACTS
    report = run_screen_contract_gate(DEFAULT_SCREEN_REGISTRY, DEFAULT_SCREEN_CONTRACTS)
    assert report.status != ERROR, report.render()
    assert "SCREEN_CONTRACT_GATE_INPUT_INVALID" not in report.codes(), report.render()
    registered = json.loads(DEFAULT_SCREEN_REGISTRY.read_text())["screens"]
    assert report.checked == sorted(registered), report.render()
    manifest = parse_screen_contracts(DEFAULT_SCREEN_CONTRACTS.read_text())
    unresolved = [r.screen_id for r in manifest.rows if r.owner_status != "RESOLVED"]
    if unresolved:
        assert report.status == FAIL, report.render()
        cited = [v.subject for v in report.violations
                 if v.code == "SCREEN_CONTRACT_OWNER_UNRESOLVED"]
        assert cited == unresolved, (set(cited) ^ set(unresolved))
    # Check 8's positive control on the real tree: the committed manifest IS
    # what the generator regenerates from the canonical source and the Appendix
    # F module table, so source-binding costs no false FAIL here. The gate still
    # denies, on the disclosed unresolved owners alone.
    assert "SCREEN_CONTRACT_SOURCE_DRIFT" not in report.codes(), report.render()


# --- check 8: the manifest must regenerate from its sources (ADR-014 D2.1/D2.4)
# This is the defect the parser-only checks 1-7 could not see. --------------

def test_screen_contract_fabricated_resolved_owner_over_the_real_manifest_is_not_pass():
    """The exact fail-open this repair closes, pinned permanently.

    Take the committed 170-row manifest, leave its provenance block untouched,
    and give every row a fabricated but wholly self-consistent resolved owner
    (`MOD-020` / `W2` / `MBR-01`) with fabricated `BOUND` bindings and a
    coherent `module_screens` index. Checks 1-7 are then satisfied by
    construction -- the counts still agree with the rows, every Screen ID is
    still canonical and registered, the registry-ID digest still matches, no row
    is UNRESOLVED, the index still groups correctly, no row is a staged UNBOUND
    -- and the gate returned **PASS with zero violations**, while
    `generate_screen_contract_manifest.check_manifest` rejected the same
    document (`BINDING_FIELD_INVALID`, `OWNER_MISMATCH`, `MANIFEST_DRIFT`).

    The assertion is deliberately an exact code set: source drift must be the
    *only* thing that catches this, which is what makes it proof that checks 1-7
    alone are not sufficient assurance and that check 8 is load-bearing.

    The committed manifest is never written to: the mutation lives in a temp
    directory, and the real file's digest is asserted unchanged afterwards.
    """
    import generate_screen_contract_manifest as gen

    before = hashlib.sha256(DEFAULT_SCREEN_CONTRACTS.read_bytes()).hexdigest()
    real = json.loads(DEFAULT_SCREEN_CONTRACTS.read_text())
    assert len(real["screens"]) == 170, len(real["screens"])
    for row in real["screens"]:
        row["owning_module"] = SC_OWNER
        row["wave"] = SC_WAVE
        row["owner_domain"] = SC_DOMAIN
        row["owner_resolution"] = {"status": "RESOLVED", "reason": None}
        row["binding_status"] = SCREEN_BOUND
        for name in SCREEN_BINDING_FIELDS:
            row[name] = f"bound:{name}"
    real["module_screens"] = {m: [] for m in real["module_screens"]}
    real["module_screens"]["MOD-001"] = []
    real["module_screens"][SC_OWNER] = [r["screen_id"] for r in real["screens"]]
    mutated = json.dumps(real, indent=2, ensure_ascii=False) + "\n"

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "screen-contracts.yaml"
        path.write_text(mutated)
        report = run_screen_contract_gate(DEFAULT_SCREEN_REGISTRY, path)
        assert report.status != PASS, report.render()
        assert report.codes() == {"SCREEN_CONTRACT_SOURCE_DRIFT"}, report.render()

        # The gate and the canonical generator must now agree on this document;
        # them disagreeing is what the fail-open was.
        generator_report = gen.check_manifest(
            mutated,
            DEFAULT_SCREEN_SOURCE.read_text(encoding="utf-8"),
            gen.load_registry_ids(DEFAULT_SCREEN_REGISTRY),
            DEFAULT_SCREEN_EIP.read_text(encoding="utf-8"),
        )
        assert generator_report.state != "PASS", generator_report.state

    assert hashlib.sha256(DEFAULT_SCREEN_CONTRACTS.read_bytes()).hexdigest() == before


def test_screen_contract_fabricated_resolved_owner_on_a_synthetic_fixture_drifts():
    """The same shape as the fixture self-test ADR-014 D1.3 asks for: the
    manifest claims a resolved owner for a screen whose source row carries no
    TSD domain code, so the generator would emit UNRESOLVED for it. Nothing in
    the document itself is inconsistent -- only the source disagrees."""
    report = _sc_run([SCR1], [_sc_row(SCR1)],
                     source_text=_sc_source_text([SCR1], unresolved=[SCR1]))
    assert report.status == FAIL, report.render()
    assert report.codes() == {"SCREEN_CONTRACT_SOURCE_DRIFT"}, report.render()


def test_screen_contract_wrong_owner_for_the_appendix_f_rule_drifts():
    """An owner that is not what the Appendix F rule yields (its module table
    row owns no surface this screen is on) cannot be smuggled in by naming it
    consistently in every row field and in `module_screens`."""
    report = _sc_run([SCR1], [_sc_row(SCR1, owner="MOD-030")],
                     eip_text=_sc_eip_text([SC_OWNER]))
    assert report.status == FAIL, report.render()
    assert "SCREEN_CONTRACT_SOURCE_DRIFT" in report.codes(), report.render()


@_sc_synthetic_single_admin
def test_screen_contract_missing_or_symlinked_generation_sources_are_error():
    """The two generation sources are real inputs: absent or symlinked, the gate
    reports ERROR rather than falling back to judging the manifest on its own
    internal agreement -- which is the posture that passed fabricated owners."""
    rows = [_sc_row(SCR1)]
    source_text, eip_text = _sc_sources([SCR1], rows)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reg = root / "screen-registry.json"
        reg.write_text(json.dumps({"version": 1, "screens": [SCR1]}))
        contracts = root / "screen-contracts.yaml"
        contracts.write_text(_sc_contracts_text(
            rows, registry_ids=[SCR1],
            source_sha256=hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
            eip_sha256=_sc_module_table_digest(eip_text)))
        source = root / "veyro-registry-data.js"
        source.write_text(source_text)
        eip = root / "EIP_MIRROR.md"
        eip.write_text(eip_text)

        # control: with both sources present this is the conforming fixture
        assert run_screen_contract_gate(
            reg, contracts, frozenset(), source, eip).status == PASS

        for pair in ((root / "nope.js", eip), (source, root / "nope.md")):
            report = run_screen_contract_gate(reg, contracts, frozenset(), *pair)
            assert report.status == ERROR, (pair, report.render())
            assert report.codes() == {"SCREEN_CONTRACT_GATE_INPUT_INVALID"}, report.render()

        link_source = root / "source-link.js"
        link_source.symlink_to(source)
        assert run_screen_contract_gate(
            reg, contracts, frozenset(), link_source, eip).status == ERROR
        link_eip = root / "eip-link.md"
        link_eip.symlink_to(eip)
        assert run_screen_contract_gate(
            reg, contracts, frozenset(), source, link_eip).status == ERROR


def test_screen_contract_unparseable_generation_sources_are_error():
    """A source or module table the generator cannot parse is ERROR -- never a
    pass by skipping check 8, and never FAIL, which would misattribute a broken
    input to the manifest."""
    # The manifest text is built with placeholder provenance digests here: a
    # conforming one cannot be built against a source the generator refuses,
    # and the run never gets far enough for its digests to matter.
    conforming = _sc_contracts_text([_sc_row(SCR1)], registry_ids=[SCR1])
    for kwargs in ({"source_text": "not a registry export\n"},
                   {"source_text": "export const R = [\n  ['bad','row'],\n];\n"},
                   {"eip_text": "no Appendix F module table here\n"}):
        report = _sc_run([SCR1], contracts_text=conforming, **kwargs)
        assert report.status == ERROR, (kwargs, report.render())
        assert report.codes() == {"SCREEN_CONTRACT_GATE_INPUT_INVALID"}, report.render()
        assert "regenerate" in report.violations[0].detail, report.render()


# --- coordinated-mutation regressions (reviewer-proven gaps): disposable copies
# of the real source / registry / manifest, each regenerated consistently so that
# the inputs agree with one another and only an absolute or source-bound check
# can see the mutation. The committed files are never written. -----------------

def _sc_real_disposable(root):
    """Copy the real source and EIP mirror into `root`; return their paths and
    the source-derived canonical rows."""
    src = root / "veyro-registry-data.js"
    src.write_bytes(DEFAULT_SCREEN_SOURCE.read_bytes())
    eip = root / "EIP_MIRROR.md"
    eip.write_bytes(DEFAULT_SCREEN_EIP.read_bytes())
    return src, eip


def _sc_run_disposable(root, source_text, registry_ids, eip, manifest_bytes=None):
    """Regenerate the manifest against `registry_ids`, write registry and
    manifest, and run the gate. Returns (report, manifest_text)."""
    manifest_text = _sc_gen.generate_manifest_text(
        source_text, registry_ids, eip.read_text(encoding="utf-8"), enforce=False)
    reg = root / "screen-registry.json"
    reg.write_text(json.dumps({"version": 1, "screens": registry_ids}))
    contracts = root / "screen-contracts.yaml"
    contracts.write_bytes(manifest_text.encode("utf-8") if manifest_bytes is None
                          else manifest_bytes)
    src = root / "veyro-registry-data.js"
    return run_screen_contract_gate(reg, contracts, frozenset(), src, eip), manifest_text


def test_screen_contract_coordinated_deletion_of_a_canonical_row_fails_absolute_counts():
    """Delete one canonical V1 Admin row from the source, then regenerate the
    registry and manifest consistently. Source, registry and manifest now all
    agree on 169 rows, so the relative checks pass; only the absolute 170 and
    85/16/19/35/15 comparison against the source-derived rows sees it. It must
    be FAIL (not ERROR) and must not depend on `enforce=True` regeneration."""
    before = hashlib.sha256(DEFAULT_SCREEN_SOURCE.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src, eip = _sc_real_disposable(root)
        text = src.read_text(encoding="utf-8")
        victim = _sc_gen.build_canonical_rows(text)[0]
        assert victim.surface == "Admin", victim
        lines = text.splitlines(keepends=True)
        kept = [ln for ln in lines if not ln.lstrip().startswith(f"['{victim.screen_id}',")]
        assert len(kept) == len(lines) - 1
        text = "".join(kept)
        src.write_text(text, encoding="utf-8")
        ids = [r.screen_id for r in _sc_gen.build_canonical_rows(text)]
        assert len(ids) == 169
        report, _ = _sc_run_disposable(root, text, ids, eip)
        assert report.status == FAIL, report.render()
        codes = report.codes()
        assert "SCREEN_CONTRACT_SOURCE_COUNT_MISMATCH" in codes, report.render()
        assert "SCREEN_CONTRACT_CANONICAL_COUNT_MISMATCH" in codes, report.render()
        assert "SCREEN_CONTRACT_GATE_INPUT_INVALID" not in codes, report.render()
        detail = " ".join(v.detail for v in report.violations)
        assert "169" in detail and "170" in detail and "[84, 16, 19, 35, 15]" in detail, detail
        # the generator's own check reaches the same verdict on the same inputs
        generator_report = _sc_gen.check_manifest(
            (root / "screen-contracts.yaml").read_text(encoding="utf-8"), text, ids,
            eip.read_text(encoding="utf-8"))
        assert generator_report.state != "PASS", generator_report.state
    assert hashlib.sha256(DEFAULT_SCREEN_SOURCE.read_bytes()).hexdigest() == before


def test_screen_contract_reversed_registry_order_fails_source_binding():
    """Reverse the registry's ID order and regenerate the manifest against it:
    the manifest, registry digest and unresolved owners all stay self-consistent.
    Only binding the registry to the source-derived canonical order sees it."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src, eip = _sc_real_disposable(root)
        text = src.read_text(encoding="utf-8")
        ids = [r.screen_id for r in _sc_gen.build_canonical_rows(text)]
        assert len(ids) == 170
        report, _ = _sc_run_disposable(root, text, list(reversed(ids)), eip)
        assert report.status == FAIL, report.render()
        assert "SCREEN_CONTRACT_REGISTRY_SOURCE_MISMATCH" in report.codes(), report.render()
        assert "SCREEN_CONTRACT_GATE_INPUT_INVALID" not in report.codes(), report.render()
        # control: the unreversed registry raises no source-binding or count code
        control, _ = _sc_run_disposable(root, text, ids, eip)
        assert not {c for c in control.codes()
                    if c.endswith(("REGISTRY_SOURCE_MISMATCH", "COUNT_MISMATCH"))}, control.render()


def test_screen_contract_crlf_only_manifest_is_source_drift_with_true_disk_digest():
    """A manifest identical to regeneration except for CRLF line endings is not
    byte-identical. `read_text` normalizes newlines, so the gate used to pass the
    byte check and print the digest of the normalized text; it must compare raw
    bytes and report the true on-disk SHA-256."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src, eip = _sc_real_disposable(root)
        text = src.read_text(encoding="utf-8")
        ids = [r.screen_id for r in _sc_gen.build_canonical_rows(text)]
        _, manifest_text = _sc_run_disposable(root, text, ids, eip)
        crlf = manifest_text.replace("\n", "\r\n").encode("utf-8")
        assert crlf != manifest_text.encode("utf-8")
        report, _ = _sc_run_disposable(root, text, ids, eip, manifest_bytes=crlf)
        assert report.status == FAIL, report.render()
        drift = [v for v in report.violations if v.code == "SCREEN_CONTRACT_SOURCE_DRIFT"]
        assert len(drift) == 1, report.render()
        assert hashlib.sha256(crlf).hexdigest() in drift[0].detail, drift[0].detail
        assert "at line 1" in drift[0].detail, drift[0].detail
        # control: LF bytes are byte-identical, so no drift
        ok, _ = _sc_run_disposable(root, text, ids, eip)
        assert "SCREEN_CONTRACT_SOURCE_DRIFT" not in ok.codes(), ok.render()


# --- real canonical Screen ID shapes (R04-GATE5-CANONICAL-UX-INPUT-ADAPTER,
# 2026-10-09): `_SCREEN_ID_RE` must accept real V1 UI IDs from the frozen
# canonical export, not just the legacy synthetic `SCR-NNN` form. ------------

def test_screen_id_re_accepts_real_canonical_forms():
    for real_id in ("ADM-CC-01", "FD-01", "POS-07", "CCH-19", "MBR-35", "CON-01",
                     "ADM-SRCH-01", "ADM-AUTH-02"):
        assert _SCREEN_ID_RE.fullmatch(real_id), f"{real_id!r} must be a recognised Screen ID"


def test_screen_id_re_still_accepts_legacy_synthetic_form():
    assert _SCREEN_ID_RE.fullmatch("SCR-001")
    assert _SCREEN_ID_RE.fullmatch("SCR-002")


def test_screen_id_re_rejects_backend_only_sys_prefix():
    """SYS-* is backend-only/no-UI and must never be a valid Screen ID here —
    it is excluded from the canonical registry upstream, not merely unlisted."""
    assert not _SCREEN_ID_RE.fullmatch("SYS-01")


def test_screen_id_re_rejects_malformed_real_shaped_ids():
    for bad_id in ("adm-cc-01", "ADM-CC-001", "ADMCC-01", "FD-1", "fd-01",
                    "ADM-CC-01X", "ADM--01", "ADM-CC-"):
        assert not _SCREEN_ID_RE.fullmatch(bad_id), f"{bad_id!r} must not be a recognised Screen ID"


def test_screen_id_re_rejects_real_prefix_with_legacy_three_digit_width():
    """CON-017 and FD-001 are real-prefixed but at the legacy three-digit
    width; the synthetic alternative is narrowed to `SCR-` only, so these
    must not be accepted via either shape (R04-GATE5-REAL-PREFIX-WIDTH-DENIAL)."""
    for bad_id in ("CON-017", "FD-001"):
        assert not _SCREEN_ID_RE.fullmatch(bad_id), f"{bad_id!r} must not be a recognised Screen ID"


def test_screen_contract_real_canonical_id_mapped_screen_passes():
    """Positive control: a real canonical ID (`ADM-CC-01`), previously
    rejected by the parser with 'must be a list of Screen IDs', now passes
    the full gate when carried as a conforming manifest row."""
    real_id = "ADM-CC-01"
    report = _sc_run([real_id], [_sc_row(real_id)])
    assert report.status == PASS, report.render()
    assert report.checked == [real_id]


def test_screen_contract_mixed_real_ids_across_surfaces_pass():
    rows = [_sc_row("ADM-CC-01", surface="Admin"),
            _sc_row("FD-01", surface="Front Desk & POS"),
            _sc_row("POS-01", surface="Front Desk & POS"),
            _sc_row("CCH-01", surface="Coach"),
            _sc_row("MBR-01", surface="Member"),
            _sc_row("CON-01", surface="Internal SaaS Console")]
    ids = [r["screen_id"] for r in rows]
    report = _sc_run(ids, rows)
    assert report.status == PASS, report.render()
    assert sorted(report.checked) == sorted(ids)


def test_screen_contract_malformed_real_shaped_id_in_registry_is_error():
    report = _sc_run(registry_raw={"version": 1, "screens": ["adm-cc-01"]}, rows=[])
    assert report.status == ERROR, report.render()
    assert report.codes() == {"SCREEN_CONTRACT_GATE_INPUT_INVALID"}


def test_screen_contract_real_prefix_with_legacy_three_digit_width_in_registry_is_error():
    """CON-017 / FD-001: real prefix, legacy three-digit width -- must be
    rejected at gate-registry parsing, not silently accepted via the generic
    legacy shape (R04-GATE5-REAL-PREFIX-WIDTH-DENIAL)."""
    for bad_id in ("CON-017", "FD-001"):
        report = _sc_run(registry_raw={"version": 1, "screens": [bad_id]}, rows=[])
        assert report.status == ERROR, (bad_id, report.render())
        assert report.codes() == {"SCREEN_CONTRACT_GATE_INPUT_INVALID"}, (bad_id, report.render())


def test_screen_contract_duplicate_real_id_in_registry_is_error():
    report = _sc_run(registry_raw={"version": 1, "screens": ["ADM-CC-01", "ADM-CC-01"]}, rows=[])
    assert report.status == ERROR, report.render()
    assert report.codes() == {"SCREEN_CONTRACT_GATE_INPUT_INVALID"}


def test_screen_contract_gate_registered_as_implemented():
    assert "screen-contract" in IMPLEMENTED_GATES
    assert "screen-contract" not in DEFERRED_GATES


def test_screen_contract_cli_exit_codes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reg = root / "screen-registry.json"
        contracts = root / "screen-contracts.yaml"
        source = root / "veyro-registry-data.js"
        eip = root / "EIP_MIRROR.md"

        # The one-row fixture scopes the generator's canonical absolutes the same
        # way `_sc_expect_surfaces` does in-process.
        shim = ("import sys; sys.path.insert(0, sys.argv[1]); "
                "import generate_screen_contract_manifest as g; g.EXPECTED_TOTAL = 1; "
                "g.EXPECTED_BY_SURFACE = {s: int(s == 'Admin') for s in g.EXPECTED_BY_SURFACE}; "
                "import validate_architecture_gates as v; sys.exit(v.main(sys.argv[2:]))")

        def cli(*extra):
            return subprocess.run(
                [sys.executable, "-c", shim, str(TOOLS), "--gate",
                 "screen-contract", "--screen-registry", str(reg), "--screen-contracts",
                 str(contracts), "--screen-source", str(source), "--screen-eip", str(eip),
                 "--json", *extra],
                capture_output=True, text=True, check=False,
            )

        rows = [_sc_row(SCR1)]
        source_text, eip_text = _sc_sources([SCR1], rows)
        source.write_text(source_text)
        eip.write_text(eip_text)
        reg.write_text(json.dumps({"version": 1, "screens": [SCR1]}))
        contracts.write_text(_sc_contracts_text(
            rows, registry_ids=[SCR1],
            source_sha256=hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
            eip_sha256=_sc_module_table_digest(eip_text)))
        ok = cli()
        assert ok.returncode == 0, ok.stdout + ok.stderr
        assert json.loads(ok.stdout)["status"] == PASS

        # ADR-014 D2.6 through the CLI: the same inputs, with the owning module
        # named as implemented, must block.
        staged = cli("--screen-implemented-modules", SC_OWNER)
        assert staged.returncode == 1, staged.stdout + staged.stderr
        staged_body = json.loads(staged.stdout)
        assert staged_body["status"] == FAIL
        assert {v["code"] for v in staged_body["violations"]} == {"SCREEN_CONTRACT_ROW_UNBOUND"}

        contracts.write_text(_sc_contracts_text([], registry_ids=[SCR1]))
        bad = cli()
        assert bad.returncode == 1
        body = json.loads(bad.stdout)
        assert body["status"] == FAIL
        codes = {v["code"] for v in body["violations"]}
        assert codes == {"SCREEN_CONTRACT_COUNT_MISMATCH", "UNMAPPED_SCREEN_CONTRACT",
                         "SCREEN_CONTRACT_CANONICAL_COUNT_MISMATCH",
                         "SCREEN_CONTRACT_SOURCE_DRIFT"}


# --- domain-uniqueness gate (TSD §24.1 gate 6, ADR-013 P1-P5 plus the D4
# addendum's observed-prose increment, 2026-10-09) --

# Default nonempty placeholder passages for the D4 addendum's mandatory
# `slo_text`/`failure_text` fields (ADR-013 D4 addendum P-3: every domain
# must carry both, nonempty, or the whole document is INPUT_INVALID). Plain
# generic prose, deliberately inert: every pre-D4 test below defaults
# `slo_signals`/`failure_terms` to `()`, so D4(a)/(b) have no declared term
# to check or scan for against any other domain regardless of what this
# placeholder text says -- it exists only to satisfy the nonempty-input
# rule, not to participate in any comparison.
_DC_DEFAULT_SLO_TEXT = ("Standard synthetic SLI/SLO narrative passage.",)
_DC_DEFAULT_FAILURE_TEXT = ("Standard synthetic failure/degraded-behavior narrative passage.",)


def _dc_field(values, provenance="synthetic"):
    return {"value": list(values), "provenance": provenance}


def _dc_domain(*, entities=(), commands=(), published_events=(), runbook_ids=(),
               dependencies=(), slo_signals=(), failure_terms=(),
               slo_text=_DC_DEFAULT_SLO_TEXT, failure_text=_DC_DEFAULT_FAILURE_TEXT,
               slo_signals_provenance="synthetic", failure_terms_provenance="synthetic"):
    return {
        "entities": _dc_field(entities),
        "commands": _dc_field(commands),
        "published_events": _dc_field(published_events),
        "runbook_ids": _dc_field(runbook_ids),
        "dependencies": _dc_field(dependencies),
        "slo_signals": _dc_field(slo_signals, slo_signals_provenance),
        "failure_terms": _dc_field(failure_terms, failure_terms_provenance),
        "slo_text": _dc_field(slo_text),
        "failure_text": _dc_field(failure_text),
    }


def _du_run(domains, root: Path):
    """Write a disposable synthetic domain-contract document (no exception
    register -- its absence is a legal empty register) and run the gate."""
    contract = root / "domain-contract.json"
    contract.write_text(json.dumps({"domains": domains}))
    return run_domain_uniqueness_gate(contract, root / "shared-contract-exceptions.json", root)


def test_domain_uniqueness_gate_registered_as_implemented():
    assert "domain-uniqueness" in IMPLEMENTED_GATES
    assert "domain-uniqueness" not in DEFERRED_GATES


def test_domain_uniqueness_disjoint_domains_pass_all_six_dimensions():
    """SCN-MOD001-014 positive shape, now genuinely achievable: all six TSD
    §24.1 comparison dimensions are implemented (ADR-013 D1-D5 plus the D4
    addendum), and a disjoint fixture across every dimension -- including
    declared SLI/SLO signals and failure-vocabulary terms that each only
    occur in their own domain's prose -- reads a true PASS, not an ERROR.
    A PASS here is fixture-level evidence only (ADR-013 D4 addendum P-6)."""
    with tempfile.TemporaryDirectory() as tmp:
        domains = {
            "DOM-A": _dc_domain(entities=["Alpha"], commands=["a.create"], runbook_ids=["RB-A"],
                                published_events=["a.created"],
                                slo_signals=["alpha-latency"], failure_terms=["alpha-timeout"],
                                slo_text=["Alpha's SLO tracks alpha-latency."],
                                failure_text=["Alpha fails closed on alpha-timeout."]),
            "DOM-B": _dc_domain(entities=["Beta"], commands=["b.create"], runbook_ids=["RB-B"],
                                published_events=["b.created"],
                                slo_signals=["beta-latency"], failure_terms=["beta-timeout"],
                                slo_text=["Beta's SLO tracks beta-latency."],
                                failure_text=["Beta fails closed on beta-timeout."]),
        }
        report = _du_run(domains, Path(tmp))
    assert report.status == PASS, report.render()
    assert report.violations == []


def test_domain_uniqueness_identical_command_inventory_is_collision():
    """SCN-MOD001-015 P1: a byte-order difference must not conceal an
    identical command set (ADR-013 D2: compared as unordered sets)."""
    with tempfile.TemporaryDirectory() as tmp:
        domains = {
            "DOM-A": _dc_domain(commands=["x.create", "x.update"], runbook_ids=["RB-A"]),
            "DOM-B": _dc_domain(commands=["x.update", "x.create"], runbook_ids=["RB-B"]),
        }
        report = _du_run(domains, Path(tmp))
    assert report.status == FAIL, report.render()
    assert report.codes() == {"DOMAIN_CONTRACT_COLLISION"}
    violation = report.violations[0]
    assert {"DOM-A", "DOM-B"} == set(violation.subject.split("|"))
    assert "identical command inventory" in violation.detail


def test_domain_uniqueness_identical_entity_set_is_collision():
    """Gate-6 lead decision D3 §3: an identical normalized entity set across
    two domains fails `DOMAIN_CONTRACT_COLLISION`, mirroring P1's shape. A
    byte-order difference must not conceal the identical set (D2: compared
    as unordered sets, like commands)."""
    with tempfile.TemporaryDirectory() as tmp:
        domains = {
            "DOM-A": _dc_domain(entities=["Alpha", "Beta"], commands=["a.create"],
                                runbook_ids=["RB-A"]),
            "DOM-B": _dc_domain(entities=["Beta", "Alpha"], commands=["b.create"],
                                runbook_ids=["RB-B"]),
        }
        report = _du_run(domains, Path(tmp))
    assert report.status == FAIL, report.render()
    assert report.codes() == {"DOMAIN_CONTRACT_COLLISION"}
    violation = report.violations[0]
    assert {"DOM-A", "DOM-B"} == set(violation.subject.split("|"))
    assert "identical entity set" in violation.detail


def test_domain_uniqueness_entity_set_partial_overlap_does_not_collide():
    """Gate-6 lead decision D3 §3: "element-level overlaps are reported as
    inventory facts, never as a verdict" -- a shared entity alongside
    non-shared ones is a partial overlap, not an identical set, and must not
    fail this dimension (making overlap fail would fire on the TSD's own 14
    real cross-domain entity names, per the lead decision). This also
    exercises D3's reporting half directly: the shared element ("Beta")
    must be named in a deterministic note citing the pair, never silently
    dropped and never escalated into a violation."""
    with tempfile.TemporaryDirectory() as tmp:
        domains = {
            "DOM-A": _dc_domain(entities=["Alpha", "Beta"], commands=["a.create"],
                                runbook_ids=["RB-A"]),
            "DOM-B": _dc_domain(entities=["Beta", "Gamma"], commands=["b.create"],
                                runbook_ids=["RB-B"]),
        }
        report = _du_run(domains, Path(tmp))
    assert report.status == PASS, report.render()
    assert report.violations == []
    # D3's reporting half: the shared element ("Beta") must surface as a
    # deterministic inventory fact/note naming the pair, never a violation.
    overlap_notes = [n for n in report.notes if "entity-set partial overlap" in n]
    assert len(overlap_notes) == 1, report.render()
    assert {"DOM-A", "DOM-B"} == set(overlap_notes[0].split(" ", 1)[0].split("/"))
    assert "Beta" in overlap_notes[0]
    assert "Alpha" not in overlap_notes[0]
    assert "Gamma" not in overlap_notes[0]
    assert "DOMAIN_CONTRACT_COLLISION" not in report.codes()


def test_domain_uniqueness_disjoint_entity_sets_do_not_collide():
    """Negative control: wholly distinct entity sets must not fire the new
    dimension, and -- since the intersection is empty -- must not fabricate
    a partial-overlap fact either."""
    with tempfile.TemporaryDirectory() as tmp:
        domains = {
            "DOM-A": _dc_domain(entities=["Alpha"], commands=["a.create"], runbook_ids=["RB-A"]),
            "DOM-B": _dc_domain(entities=["Beta"], commands=["b.create"], runbook_ids=["RB-B"]),
        }
        report = _du_run(domains, Path(tmp))
    assert report.status == PASS, report.render()
    assert report.violations == []
    assert not any("entity-set partial overlap" in n for n in report.notes), report.render()


def test_domain_uniqueness_entity_set_collision_is_case_sensitive():
    """ADR-013 D2, carried into the entity-set dimension: 'Alpha' and 'alpha'
    are two distinct identifiers, not a collision, even though they are each
    the domain's entire (single-element) set. The case-distinct sets also
    have an empty intersection, so no partial-overlap fact is fabricated."""
    with tempfile.TemporaryDirectory() as tmp:
        domains = {
            "DOM-A": _dc_domain(entities=["Alpha"], commands=["a.create"], runbook_ids=["RB-A"]),
            "DOM-B": _dc_domain(entities=["alpha"], commands=["b.create"], runbook_ids=["RB-B"]),
        }
        report = _du_run(domains, Path(tmp))
    assert report.status == PASS, report.render()
    assert report.violations == []
    assert not any("entity-set partial overlap" in n for n in report.notes), report.render()


def test_domain_uniqueness_entity_set_terminal_period_normalization_detects_collision():
    """Same D2 terminal-period normalization applied to the entity-set
    dimension: 'Alpha' and 'Alpha.' must still compare equal."""
    with tempfile.TemporaryDirectory() as tmp:
        domains = {
            "DOM-A": _dc_domain(entities=["Alpha"], commands=["a.create"], runbook_ids=["RB-A"]),
            "DOM-B": _dc_domain(entities=["Alpha."], commands=["b.create"], runbook_ids=["RB-B"]),
        }
        report = _du_run(domains, Path(tmp))
    assert report.status == FAIL, report.render()
    assert report.codes() == {"DOMAIN_CONTRACT_COLLISION"}
    assert _command_inventory_digest(["Alpha"]) in report.violations[0].detail


def test_domain_uniqueness_entity_set_has_no_exception_route():
    """The qualified gate-6 dispatch forbids an entity exception/waiver (D5
    covers only command-inventory, runbook-id, and published-event): a
    register entry naming dimension 'entity-set' is malformed input and
    ERRORs before the comparison loop runs, so it can never silently clear a
    real identical-entity-set collision -- the collision is never even
    reached to be resolved or denied, because the malformed register itself
    stops the run first."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "knowledge" / "00-System").mkdir(parents=True)
        (root / "knowledge" / "00-System" / "OWNER_APPROVALS.md").write_text(
            "| OWN-001 | Approved shared exception SCE-001 | DOM-A/DOM-B entity-set "
            "| 2026-10-09 | ad hoc |\n")
        domains = {
            "DOM-A": _dc_domain(entities=["Alpha"], commands=["a.create"], runbook_ids=["RB-A"]),
            "DOM-B": _dc_domain(entities=["Alpha"], commands=["b.create"], runbook_ids=["RB-B"]),
        }
        exceptions = {"SCE-001": {"pair": ["DOM-A", "DOM-B"], "dimension": "entity-set",
                                  "artifact": "Alpha", "approval": "OWN-001"}}
        (root / "domain-contract.json").write_text(json.dumps({"domains": domains}))
        (root / "shared-contract-exceptions.json").write_text(json.dumps({"exceptions": exceptions}))
        report = run_domain_uniqueness_gate(root / "domain-contract.json",
                                            root / "shared-contract-exceptions.json", root)
    assert report.status == ERROR, report.render()
    assert report.codes() == {"DOMAIN_UNIQUENESS_GATE_INPUT_INVALID"}


def test_domain_uniqueness_reused_runbook_id_is_collision():
    """SCN-MOD001-015 P2: an identical RB-<DOMAIN> id reused across domains."""
    with tempfile.TemporaryDirectory() as tmp:
        domains = {
            "DOM-A": _dc_domain(commands=["a.create"], runbook_ids=["RB-SHARED"]),
            "DOM-B": _dc_domain(commands=["b.create"], runbook_ids=["RB-SHARED"]),
        }
        report = _du_run(domains, Path(tmp))
    assert report.status == FAIL, report.render()
    assert report.codes() == {"DOMAIN_CONTRACT_COLLISION"}
    assert "RB-SHARED" in report.violations[0].detail


def test_domain_uniqueness_runbook_id_reuse_is_case_sensitive():
    """ADR-013 D2: identifiers compare case-sensitively -- 'RB-A' and 'rb-a'
    are two distinct ids, not a collision."""
    with tempfile.TemporaryDirectory() as tmp:
        domains = {
            "DOM-A": _dc_domain(commands=["a.create"], runbook_ids=["RB-A"]),
            "DOM-B": _dc_domain(commands=["b.create"], runbook_ids=["rb-a"]),
        }
        report = _du_run(domains, Path(tmp))
    assert report.status == PASS, report.render()
    assert report.violations == []


def test_domain_uniqueness_reused_published_event_id_is_collision():
    """R04 gate-6 dispatch false-negative fixture, 2026-10-09: DOM-A and
    DOM-B both publish 'booking.created' with distinct commands/RB ids --
    gate-6 lead decision D3 (plan-backed) requires this to FAIL
    DOMAIN_CONTRACT_COLLISION."""
    with tempfile.TemporaryDirectory() as tmp:
        domains = {
            "DOM-A": _dc_domain(commands=["a.create"], runbook_ids=["RB-A"],
                                published_events=["booking.created"]),
            "DOM-B": _dc_domain(commands=["b.create"], runbook_ids=["RB-B"],
                                published_events=["booking.created"]),
        }
        report = _du_run(domains, Path(tmp))
    assert report.status == FAIL, report.render()
    assert report.codes() == {"DOMAIN_CONTRACT_COLLISION"}
    violation = report.violations[0]
    assert {"DOM-A", "DOM-B"} == set(violation.subject.split("|"))
    assert "booking.created" in violation.detail


def test_domain_uniqueness_disjoint_published_event_ids_do_not_collide():
    """Negative control: distinct published-event ids across domains must
    not fire this dimension, and -- with every other dimension disjoint
    too -- the aggregate reads a genuine PASS."""
    with tempfile.TemporaryDirectory() as tmp:
        domains = {
            "DOM-A": _dc_domain(commands=["a.create"], runbook_ids=["RB-A"],
                                published_events=["a.created"]),
            "DOM-B": _dc_domain(commands=["b.create"], runbook_ids=["RB-B"],
                                published_events=["b.created"]),
        }
        report = _du_run(domains, Path(tmp))
    assert report.status == PASS, report.render()
    assert report.violations == []


def test_domain_uniqueness_published_event_id_collision_is_case_sensitive():
    """ADR-013 D2: identifiers compare case-sensitively -- 'booking.created'
    and 'Booking.Created' are two distinct ids, not a collision."""
    with tempfile.TemporaryDirectory() as tmp:
        domains = {
            "DOM-A": _dc_domain(commands=["a.create"], runbook_ids=["RB-A"],
                                published_events=["booking.created"]),
            "DOM-B": _dc_domain(commands=["b.create"], runbook_ids=["RB-B"],
                                published_events=["Booking.Created"]),
        }
        report = _du_run(domains, Path(tmp))
    assert report.status == PASS, report.render()
    assert report.violations == []


def test_domain_uniqueness_terminal_period_normalization_detects_published_event_collision():
    """Same D2 terminal-period normalization applied to the published-event
    dimension: 'booking.created' and 'booking.created.' must still compare
    equal."""
    with tempfile.TemporaryDirectory() as tmp:
        domains = {
            "DOM-A": _dc_domain(commands=["a.create"], runbook_ids=["RB-A"],
                                published_events=["booking.created"]),
            "DOM-B": _dc_domain(commands=["b.create"], runbook_ids=["RB-B"],
                                published_events=["booking.created."]),
        }
        report = _du_run(domains, Path(tmp))
    assert report.status == FAIL, report.render()
    assert report.codes() == {"DOMAIN_CONTRACT_COLLISION"}
    assert "booking.created" in report.violations[0].detail


def test_domain_uniqueness_published_event_exception_resolves_exact_match():
    """R04-GATE6-EVENT-EXCEPTION-SOURCE-RECONCILIATION-2026-10-09.md / the
    matching implementation dispatch: a shared-contract exception naming the
    exact unordered pair, the 'published-event' dimension, this exact
    normalized event id, and an affirmative owner approval resolves only
    that one collision -- it is cited by exception id in notes, never a
    violation, and with every other dimension disjoint the aggregate reads a
    genuine PASS (fixture-level evidence only, ADR-013 D4 addendum P-6)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "knowledge" / "00-System").mkdir(parents=True)
        (root / "knowledge" / "00-System" / "OWNER_APPROVALS.md").write_text(
            "| OWN-001 | Approved shared exception SCE-001 | DOM-A/DOM-B published-event "
            "| 2026-10-09 | ad hoc |\n")
        domains = {
            "DOM-A": _dc_domain(commands=["a.create"], runbook_ids=["RB-A"],
                                published_events=["booking.created"]),
            "DOM-B": _dc_domain(commands=["b.create"], runbook_ids=["RB-B"],
                                published_events=["booking.created"]),
        }
        exceptions = {"SCE-001": {"pair": ["DOM-A", "DOM-B"], "dimension": "published-event",
                                  "artifact": "booking.created", "approval": "OWN-001"}}
        (root / "domain-contract.json").write_text(json.dumps({"domains": domains}))
        (root / "shared-contract-exceptions.json").write_text(json.dumps({"exceptions": exceptions}))
        report = run_domain_uniqueness_gate(root / "domain-contract.json",
                                            root / "shared-contract-exceptions.json", root)
    assert report.status == PASS, report.render()
    assert report.violations == []
    assert any("SCE-001" in note and "booking.created" in note for note in report.notes)


def test_domain_uniqueness_published_event_exception_wrong_event_id_does_not_resolve():
    """Negative control: an exception approved for a different event id must
    not clear this collision -- `_resolve_domain_collision`'s exact-artifact
    match, not a same-pair blanket waiver."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "knowledge" / "00-System").mkdir(parents=True)
        (root / "knowledge" / "00-System" / "OWNER_APPROVALS.md").write_text(
            "| OWN-001 | Approved shared exception SCE-001 | DOM-A/DOM-B published-event "
            "| 2026-10-09 | ad hoc |\n")
        domains = {
            "DOM-A": _dc_domain(commands=["a.create"], runbook_ids=["RB-A"],
                                published_events=["booking.created"]),
            "DOM-B": _dc_domain(commands=["b.create"], runbook_ids=["RB-B"],
                                published_events=["booking.created"]),
        }
        exceptions = {"SCE-001": {"pair": ["DOM-A", "DOM-B"], "dimension": "published-event",
                                  "artifact": "booking.cancelled", "approval": "OWN-001"}}
        (root / "domain-contract.json").write_text(json.dumps({"domains": domains}))
        (root / "shared-contract-exceptions.json").write_text(json.dumps({"exceptions": exceptions}))
        report = run_domain_uniqueness_gate(root / "domain-contract.json",
                                            root / "shared-contract-exceptions.json", root)
    assert report.status == FAIL, report.render()
    assert report.codes() == {"DOMAIN_CONTRACT_COLLISION"}
    assert "booking.created" in report.violations[0].detail


def test_domain_uniqueness_published_event_exception_wrong_dimension_does_not_resolve():
    """Negative control: an exception for the same pair and artifact value
    but dimension 'command-inventory' must not clear a published-event
    collision -- dimension is part of the exact-match tuple, not advisory."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "knowledge" / "00-System").mkdir(parents=True)
        (root / "knowledge" / "00-System" / "OWNER_APPROVALS.md").write_text(
            "| OWN-001 | Approved shared exception SCE-001 | DOM-A/DOM-B command-inventory "
            "| 2026-10-09 | ad hoc |\n")
        domains = {
            "DOM-A": _dc_domain(commands=["a.create"], runbook_ids=["RB-A"],
                                published_events=["booking.created"]),
            "DOM-B": _dc_domain(commands=["b.create"], runbook_ids=["RB-B"],
                                published_events=["booking.created"]),
        }
        exceptions = {"SCE-001": {"pair": ["DOM-A", "DOM-B"], "dimension": "command-inventory",
                                  "artifact": "booking.created", "approval": "OWN-001"}}
        (root / "domain-contract.json").write_text(json.dumps({"domains": domains}))
        (root / "shared-contract-exceptions.json").write_text(json.dumps({"exceptions": exceptions}))
        report = run_domain_uniqueness_gate(root / "domain-contract.json",
                                            root / "shared-contract-exceptions.json", root)
    assert report.status == FAIL, report.render()
    assert report.codes() == {"DOMAIN_CONTRACT_COLLISION"}
    assert "booking.created" in report.violations[0].detail


def test_domain_uniqueness_published_event_exception_denied_approval_is_error():
    """Fail-closed control for the new dimension's own wiring (not merely
    inherited from command-inventory's tests): a row whose Action-approved
    cell negates/denies the exception id must ERROR, never silently waive
    the collision -- ADR-013 D5's 'never an implicit waiver', exercised here
    through `resolve_domain_exception_approval`'s negation guard."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "knowledge" / "00-System").mkdir(parents=True)
        (root / "knowledge" / "00-System" / "OWNER_APPROVALS.md").write_text(
            "| OWN-001 | Denied shared exception SCE-001 | DOM-A/DOM-B published-event "
            "| 2026-10-09 | ad hoc |\n")
        domains = {
            "DOM-A": _dc_domain(commands=["a.create"], runbook_ids=["RB-A"],
                                published_events=["booking.created"]),
            "DOM-B": _dc_domain(commands=["b.create"], runbook_ids=["RB-B"],
                                published_events=["booking.created"]),
        }
        exceptions = {"SCE-001": {"pair": ["DOM-A", "DOM-B"], "dimension": "published-event",
                                  "artifact": "booking.created", "approval": "OWN-001"}}
        (root / "domain-contract.json").write_text(json.dumps({"domains": domains}))
        (root / "shared-contract-exceptions.json").write_text(json.dumps({"exceptions": exceptions}))
        report = run_domain_uniqueness_gate(root / "domain-contract.json",
                                            root / "shared-contract-exceptions.json", root)
    assert report.status == ERROR, report.render()
    assert report.codes() == {"DOMAIN_UNIQUENESS_GATE_INPUT_INVALID"}


def test_domain_uniqueness_terminal_period_normalization_detects_command_collision():
    """ADR-013 D2 reproduced false negative: 'a.create' and 'a.create.'
    differ only by a terminal period an extractor artifact adds, so without
    normalization the aggregate falls through to PASS instead of catching
    the real P1 collision -- R04-GATE6-D2-NORMALIZATION-DISPATCH-2026-10-09."""
    with tempfile.TemporaryDirectory() as tmp:
        domains = {
            "DOM-A": _dc_domain(commands=["a.create"], runbook_ids=["RB-A"]),
            "DOM-B": _dc_domain(commands=["a.create."], runbook_ids=["RB-B"]),
        }
        report = _du_run(domains, Path(tmp))
    assert report.status == FAIL, report.render()
    assert report.codes() == {"DOMAIN_CONTRACT_COLLISION"}
    assert "identical command inventory" in report.violations[0].detail


def test_domain_uniqueness_terminal_period_normalization_detects_runbook_collision():
    """Same D2 terminal-period normalization, P2 side."""
    with tempfile.TemporaryDirectory() as tmp:
        domains = {
            "DOM-A": _dc_domain(commands=["a.create"], runbook_ids=["RB-SHARED"]),
            "DOM-B": _dc_domain(commands=["b.create"], runbook_ids=["RB-SHARED."]),
        }
        report = _du_run(domains, Path(tmp))
    assert report.status == FAIL, report.render()
    assert report.codes() == {"DOMAIN_CONTRACT_COLLISION"}
    assert "RB-SHARED" in report.violations[0].detail


def test_domain_uniqueness_pandoc_escape_normalization_detects_command_collision():
    """ADR-013 D2: the TSD->markdown mirror conversion escapes '<' as '\\<';
    that escape must be removed before comparison so an escaped and an
    unescaped copy of the same command are read as identical."""
    with tempfile.TemporaryDirectory() as tmp:
        domains = {
            "DOM-A": _dc_domain(commands=["x.below\\<threshold"], runbook_ids=["RB-A"]),
            "DOM-B": _dc_domain(commands=["x.below<threshold"], runbook_ids=["RB-B"]),
        }
        report = _du_run(domains, Path(tmp))
    assert report.status == FAIL, report.render()
    assert report.codes() == {"DOMAIN_CONTRACT_COLLISION"}


def test_domain_uniqueness_whitespace_collapse_normalization_detects_command_collision():
    """ADR-013 D2: internal whitespace runs collapse to a single space before
    comparison."""
    with tempfile.TemporaryDirectory() as tmp:
        domains = {
            "DOM-A": _dc_domain(commands=["check  status"], runbook_ids=["RB-A"]),
            "DOM-B": _dc_domain(commands=["check status"], runbook_ids=["RB-B"]),
        }
        report = _du_run(domains, Path(tmp))
    assert report.status == FAIL, report.render()
    assert report.codes() == {"DOMAIN_CONTRACT_COLLISION"}


def test_domain_uniqueness_comma_list_split_normalization_detects_command_collision():
    """ADR-013 D2: a single comma-joined entry splits into separate items
    before comparison, so a domain whose extractor left two commands joined
    in one list element still collides with a domain that has them as two
    distinct elements."""
    with tempfile.TemporaryDirectory() as tmp:
        domains = {
            "DOM-A": _dc_domain(commands=["a.create, a.update"], runbook_ids=["RB-A"]),
            "DOM-B": _dc_domain(commands=["a.create", "a.update"], runbook_ids=["RB-B"]),
        }
        report = _du_run(domains, Path(tmp))
    assert report.status == FAIL, report.render()
    assert report.codes() == {"DOMAIN_CONTRACT_COLLISION"}


def test_domain_uniqueness_normalization_does_not_cause_false_collision():
    """Negative control: D2's fixed operations must not make genuinely
    distinct commands compare equal -- 'a.create' and 'a.created' differ by
    more than a terminal period or whitespace and must stay distinct."""
    with tempfile.TemporaryDirectory() as tmp:
        domains = {
            "DOM-A": _dc_domain(commands=["a.create"], runbook_ids=["RB-A"]),
            "DOM-B": _dc_domain(commands=["a.created"], runbook_ids=["RB-B"]),
        }
        report = _du_run(domains, Path(tmp))
    assert report.status == PASS, report.render()
    assert report.violations == []


def test_domain_uniqueness_command_inventory_collision_resolved_by_matching_exception():
    """SCN-MOD001-131 positive companion: an exact pair/dimension/artifact
    exception with a resolvable OWN-NNN approval clears the collision and is
    cited by id -- with every other dimension disjoint the aggregate reads a
    genuine PASS (fixture-level evidence only, ADR-013 D4 addendum P-6)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "knowledge" / "00-System").mkdir(parents=True)
        (root / "knowledge" / "00-System" / "OWNER_APPROVALS.md").write_text(
            "| OWN-001 | Approved shared exception SCE-001 | DOM-A/DOM-B command-inventory "
            "| 2026-10-09 | ADR-013 D5 |\n")
        domains = {
            "DOM-A": _dc_domain(commands=["x.create", "x.update"], runbook_ids=["RB-A"]),
            "DOM-B": _dc_domain(commands=["x.create", "x.update"], runbook_ids=["RB-B"]),
        }
        digest = _command_inventory_digest(["x.create", "x.update"])
        exceptions = {"SCE-001": {"pair": ["DOM-A", "DOM-B"], "dimension": "command-inventory",
                                  "artifact": digest, "approval": "OWN-001"}}
        (root / "domain-contract.json").write_text(json.dumps({"domains": domains}))
        (root / "shared-contract-exceptions.json").write_text(json.dumps({"exceptions": exceptions}))
        report = run_domain_uniqueness_gate(root / "domain-contract.json",
                                            root / "shared-contract-exceptions.json", root)
    assert report.status == PASS, report.render()
    assert report.violations == []
    assert any("SCE-001" in note for note in report.notes)


def test_domain_uniqueness_exception_approval_hyphenated_shared_contract_resolves_collision():
    """ADR-013/TSD use the hyphenated 'shared-contract exception' term; the
    parser's affirmative-action pattern must accept it the same as the
    space-separated 'shared exception' / 'shared contract exception' forms
    -- the false rejection reproduced in
    R04-GATE6-APPROVAL-ACTION-LOCAL-VERIFICATION-2026-10-09.md."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "knowledge" / "00-System").mkdir(parents=True)
        (root / "knowledge" / "00-System" / "OWNER_APPROVALS.md").write_text(
            "| OWN-001 | Approve shared-contract exception SCE-001 | DOM-A/DOM-B command-inventory "
            "| 2026-10-09 | ADR-013 D5 |\n")
        domains = {
            "DOM-A": _dc_domain(commands=["x.create", "x.update"], runbook_ids=["RB-A"]),
            "DOM-B": _dc_domain(commands=["x.create", "x.update"], runbook_ids=["RB-B"]),
        }
        digest = _command_inventory_digest(["x.create", "x.update"])
        exceptions = {"SCE-001": {"pair": ["DOM-A", "DOM-B"], "dimension": "command-inventory",
                                  "artifact": digest, "approval": "OWN-001"}}
        (root / "domain-contract.json").write_text(json.dumps({"domains": domains}))
        (root / "shared-contract-exceptions.json").write_text(json.dumps({"exceptions": exceptions}))
        report = run_domain_uniqueness_gate(root / "domain-contract.json",
                                            root / "shared-contract-exceptions.json", root)
    assert report.status == PASS, report.render()
    assert report.violations == []
    assert any("SCE-001" in note for note in report.notes)


def test_domain_uniqueness_exception_approval_denied_does_not_resolve_collision():
    """ADR-013 D3 (fixed defect): a row that *mentions* SCE-001 but whose
    Action approved cell denies it must not clear the collision -- the exact
    reproduction in R04-GATE6-P1P2-LOCAL-VERIFICATION-AND-DEFECTS-2026-10-09."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "knowledge" / "00-System").mkdir(parents=True)
        (root / "knowledge" / "00-System" / "OWNER_APPROVALS.md").write_text(
            "| OWN-001 | Denied shared exception SCE-001 | DOM-A/DOM-B command-inventory "
            "| 2026-10-09 | ADR-013 D5 |\n")
        domains = {
            "DOM-A": _dc_domain(commands=["x.create", "x.update"], runbook_ids=["RB-A"]),
            "DOM-B": _dc_domain(commands=["x.create", "x.update"], runbook_ids=["RB-B"]),
        }
        digest = _command_inventory_digest(["x.create", "x.update"])
        exceptions = {"SCE-001": {"pair": ["DOM-A", "DOM-B"], "dimension": "command-inventory",
                                  "artifact": digest, "approval": "OWN-001"}}
        (root / "domain-contract.json").write_text(json.dumps({"domains": domains}))
        (root / "shared-contract-exceptions.json").write_text(json.dumps({"exceptions": exceptions}))
        report = run_domain_uniqueness_gate(root / "domain-contract.json",
                                            root / "shared-contract-exceptions.json", root)
    assert report.status == ERROR, report.render()
    assert report.codes() == {"DOMAIN_UNIQUENESS_GATE_INPUT_INVALID"}


def test_domain_uniqueness_exception_approval_mention_only_does_not_resolve_collision():
    """A row whose Action approved cell says nothing about the exception --
    the id only appears in Scope/Evidence -- must not clear the collision;
    mention anywhere in the row is not the same as an affirmative Action."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "knowledge" / "00-System").mkdir(parents=True)
        (root / "knowledge" / "00-System" / "OWNER_APPROVALS.md").write_text(
            "| OWN-001 | Approved unrelated schema change | SCE-001 scope note "
            "| 2026-10-09 | mentions SCE-001 |\n")
        domains = {
            "DOM-A": _dc_domain(commands=["x.create", "x.update"], runbook_ids=["RB-A"]),
            "DOM-B": _dc_domain(commands=["x.create", "x.update"], runbook_ids=["RB-B"]),
        }
        digest = _command_inventory_digest(["x.create", "x.update"])
        exceptions = {"SCE-001": {"pair": ["DOM-A", "DOM-B"], "dimension": "command-inventory",
                                  "artifact": digest, "approval": "OWN-001"}}
        (root / "domain-contract.json").write_text(json.dumps({"domains": domains}))
        (root / "shared-contract-exceptions.json").write_text(json.dumps({"exceptions": exceptions}))
        report = run_domain_uniqueness_gate(root / "domain-contract.json",
                                            root / "shared-contract-exceptions.json", root)
    assert report.status == ERROR, report.render()
    assert report.codes() == {"DOMAIN_UNIQUENESS_GATE_INPUT_INVALID"}


def test_domain_uniqueness_exception_approval_wrong_id_does_not_resolve_collision():
    """An Action approved cell that affirmatively approves a *different*
    exception id (SCE-002) must not resolve SCE-001's collision -- the id
    bound in the exception register, not any approved id, is what counts."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "knowledge" / "00-System").mkdir(parents=True)
        (root / "knowledge" / "00-System" / "OWNER_APPROVALS.md").write_text(
            "| OWN-001 | Approved shared exception SCE-002 | DOM-A/DOM-B command-inventory "
            "| 2026-10-09 | ADR-013 D5 |\n")
        domains = {
            "DOM-A": _dc_domain(commands=["x.create", "x.update"], runbook_ids=["RB-A"]),
            "DOM-B": _dc_domain(commands=["x.create", "x.update"], runbook_ids=["RB-B"]),
        }
        digest = _command_inventory_digest(["x.create", "x.update"])
        exceptions = {"SCE-001": {"pair": ["DOM-A", "DOM-B"], "dimension": "command-inventory",
                                  "artifact": digest, "approval": "OWN-001"}}
        (root / "domain-contract.json").write_text(json.dumps({"domains": domains}))
        (root / "shared-contract-exceptions.json").write_text(json.dumps({"exceptions": exceptions}))
        report = run_domain_uniqueness_gate(root / "domain-contract.json",
                                            root / "shared-contract-exceptions.json", root)
    assert report.status == ERROR, report.render()
    assert report.codes() == {"DOMAIN_UNIQUENESS_GATE_INPUT_INVALID"}


def test_domain_uniqueness_exception_for_different_artifact_does_not_resolve_collision():
    """Mismatched exception: same pair/dimension, wrong artifact -- must not
    clear the real collision (ADR-013 D5: an entry "never covers ... another
    artifact")."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "knowledge" / "00-System").mkdir(parents=True)
        (root / "knowledge" / "00-System" / "OWNER_APPROVALS.md").write_text(
            "| OWN-001 | Approved shared exception SCE-001 | DOM-A/DOM-B command-inventory "
            "| 2026-10-09 | ADR-013 D5 |\n")
        domains = {
            "DOM-A": _dc_domain(commands=["x.create", "x.update"], runbook_ids=["RB-A"]),
            "DOM-B": _dc_domain(commands=["x.create", "x.update"], runbook_ids=["RB-B"]),
        }
        exceptions = {"SCE-001": {"pair": ["DOM-A", "DOM-B"], "dimension": "command-inventory",
                                  "artifact": "0" * 64, "approval": "OWN-001"}}
        (root / "domain-contract.json").write_text(json.dumps({"domains": domains}))
        (root / "shared-contract-exceptions.json").write_text(json.dumps({"exceptions": exceptions}))
        report = run_domain_uniqueness_gate(root / "domain-contract.json",
                                            root / "shared-contract-exceptions.json", root)
    assert report.status == FAIL, report.render()
    assert report.codes() == {"DOMAIN_CONTRACT_COLLISION"}


def test_domain_uniqueness_exception_for_different_pair_does_not_resolve_collision():
    """ADR-013 D5: an entry "never covers {A,C} or another artifact" --
    pinned here for the pair half, naming a third domain not in the
    colliding pair."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "knowledge" / "00-System").mkdir(parents=True)
        (root / "knowledge" / "00-System" / "OWNER_APPROVALS.md").write_text(
            "| OWN-001 | Approved shared exception SCE-001 | DOM-A/DOM-C command-inventory "
            "| 2026-10-09 | ADR-013 D5 |\n")
        domains = {
            "DOM-A": _dc_domain(commands=["x.create"], runbook_ids=["RB-A"]),
            "DOM-B": _dc_domain(commands=["x.create"], runbook_ids=["RB-B"]),
            "DOM-C": _dc_domain(commands=["z.create"], runbook_ids=["RB-C"]),
        }
        digest = _command_inventory_digest(["x.create"])
        exceptions = {"SCE-001": {"pair": ["DOM-A", "DOM-C"], "dimension": "command-inventory",
                                  "artifact": digest, "approval": "OWN-001"}}
        (root / "domain-contract.json").write_text(json.dumps({"domains": domains}))
        (root / "shared-contract-exceptions.json").write_text(json.dumps({"exceptions": exceptions}))
        report = run_domain_uniqueness_gate(root / "domain-contract.json",
                                            root / "shared-contract-exceptions.json", root)
    assert report.status == FAIL, report.render()
    assert report.codes() == {"DOMAIN_CONTRACT_COLLISION"}
    assert {"DOM-A", "DOM-B"} == set(report.violations[0].subject.split("|"))


def test_domain_uniqueness_exception_with_unresolvable_approval_is_error():
    """ADR-013 D5: "Malformed, duplicate, or unresolvable entries produce
    ERROR (exit 2), never an implicit waiver" -- an OWN-NNN citing no live
    row must not silently leave the collision merely unresolved."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "knowledge" / "00-System").mkdir(parents=True)
        (root / "knowledge" / "00-System" / "OWNER_APPROVALS.md").write_text("")
        domains = {
            "DOM-A": _dc_domain(commands=["x.create"], runbook_ids=["RB-A"]),
            "DOM-B": _dc_domain(commands=["x.create"], runbook_ids=["RB-B"]),
        }
        digest = _command_inventory_digest(["x.create"])
        exceptions = {"SCE-001": {"pair": ["DOM-A", "DOM-B"], "dimension": "command-inventory",
                                  "artifact": digest, "approval": "OWN-404"}}
        (root / "domain-contract.json").write_text(json.dumps({"domains": domains}))
        (root / "shared-contract-exceptions.json").write_text(json.dumps({"exceptions": exceptions}))
        report = run_domain_uniqueness_gate(root / "domain-contract.json",
                                            root / "shared-contract-exceptions.json", root)
    assert report.status == ERROR, report.render()
    assert report.codes() == {"DOMAIN_UNIQUENESS_GATE_INPUT_INVALID"}


def test_domain_uniqueness_malformed_exception_dimension_is_error():
    """ADR-013 D4/D5 plus the gate-6 lead decision's D5 extension: this
    increment's exceptions may only name 'command-inventory', 'runbook-id',
    or 'published-event' -- any other dimension (e.g. 'entities', one of
    the three TSD §24.1 dimensions this increment reads from the contract
    document but never compares, per `_DOMAIN_CONTRACT_FIELDS` vs
    `_IMPLEMENTED_DOMAIN_DIMENSIONS`) is malformed input, even when no
    collision would have fired."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "knowledge" / "00-System").mkdir(parents=True)
        (root / "knowledge" / "00-System" / "OWNER_APPROVALS.md").write_text(
            "| OWN-001 | Approved exception SCE-001 |\n")
        domains = {
            "DOM-A": _dc_domain(commands=["x.create"], runbook_ids=["RB-A"]),
            "DOM-B": _dc_domain(commands=["y.create"], runbook_ids=["RB-B"]),
        }
        exceptions = {"SCE-001": {"pair": ["DOM-A", "DOM-B"], "dimension": "entities",
                                  "artifact": "evt.x", "approval": "OWN-001"}}
        (root / "domain-contract.json").write_text(json.dumps({"domains": domains}))
        (root / "shared-contract-exceptions.json").write_text(json.dumps({"exceptions": exceptions}))
        report = run_domain_uniqueness_gate(root / "domain-contract.json",
                                            root / "shared-contract-exceptions.json", root)
    assert report.status == ERROR, report.render()
    assert report.codes() == {"DOMAIN_UNIQUENESS_GATE_INPUT_INVALID"}


def test_domain_uniqueness_missing_contract_document_is_error():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        report = run_domain_uniqueness_gate(root / "nope.json", root / "exceptions.json", root)
    assert report.status == ERROR, report.render()
    assert report.codes() == {"DOMAIN_UNIQUENESS_GATE_INPUT_INVALID"}


def test_domain_uniqueness_missing_exceptions_register_is_legal_empty_register():
    """ADR-013: "the live exception register is not populated here" -- its
    absence must not itself be an error."""
    with tempfile.TemporaryDirectory() as tmp:
        domains = {
            "DOM-A": _dc_domain(commands=["a.create"], runbook_ids=["RB-A"]),
            "DOM-B": _dc_domain(commands=["b.create"], runbook_ids=["RB-B"]),
        }
        report = _du_run(domains, Path(tmp))
    assert report.status == PASS, report.render()
    assert report.violations == []


def test_domain_uniqueness_field_missing_provenance_is_error():
    """ADR-013 D1: "a ... provenance-less required input is ERROR"."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bad_domain = _dc_domain(commands=["a.create"], runbook_ids=["RB-A"])
        bad_domain["commands"] = {"value": ["a.create"]}  # no provenance key
        domains = {"DOM-A": bad_domain,
                   "DOM-B": _dc_domain(commands=["b.create"], runbook_ids=["RB-B"])}
        report = _du_run(domains, root)
    assert report.status == ERROR, report.render()
    assert report.codes() == {"DOMAIN_UNIQUENESS_GATE_INPUT_INVALID"}


def test_domain_uniqueness_duplicate_domain_id_in_raw_json_is_error():
    """`_load_json`'s duplicate-key guard: two `domains` entries with the
    same literal key (silently last-wins in bare json.loads) must ERROR,
    never silently collapse to one domain (ADR-013 D1: "duplicate ...
    required input is ERROR")."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        a = json.dumps(_dc_domain(commands=["a.create"], runbook_ids=["RB-A"]))
        b = json.dumps(_dc_domain(commands=["b.create"], runbook_ids=["RB-B"]))
        (root / "domain-contract.json").write_text(f'{{"domains": {{"DOM-A": {a}, "DOM-A": {b}}}}}')
        report = run_domain_uniqueness_gate(root / "domain-contract.json",
                                            root / "exceptions.json", root)
    assert report.status == ERROR, report.render()
    assert report.codes() == {"DOMAIN_UNIQUENESS_GATE_INPUT_INVALID"}


def test_domain_uniqueness_duplicate_value_within_field_is_error():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bad_domain = _dc_domain(commands=["a.create", "a.create"], runbook_ids=["RB-A"])
        domains = {"DOM-A": bad_domain,
                   "DOM-B": _dc_domain(commands=["b.create"], runbook_ids=["RB-B"])}
        report = _du_run(domains, root)
    assert report.status == ERROR, report.render()
    assert report.codes() == {"DOMAIN_UNIQUENESS_GATE_INPUT_INVALID"}


def test_domain_uniqueness_cli_exit_codes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        contract = root / "domain-contract.json"
        exceptions_path = root / "shared-contract-exceptions.json"

        def cli():
            return subprocess.run(
                [sys.executable, str(TOOLS / "validate_architecture_gates.py"), "--gate",
                 "domain-uniqueness", "--domain-contract", str(contract),
                 "--domain-exceptions", str(exceptions_path),
                 "--domain-approval-root", str(root), "--json"],
                capture_output=True, text=True, check=False,
            )

        domains = {
            "DOM-A": _dc_domain(commands=["a.create"], runbook_ids=["RB-A"]),
            "DOM-B": _dc_domain(commands=["b.create"], runbook_ids=["RB-B"]),
        }
        contract.write_text(json.dumps({"domains": domains}))
        no_collision = cli()
        assert no_collision.returncode == 0, no_collision.stdout + no_collision.stderr
        body = json.loads(no_collision.stdout)
        assert body["status"] == PASS
        assert body["violations"] == []

        domains["DOM-B"]["runbook_ids"] = _dc_field(["RB-A"])
        contract.write_text(json.dumps({"domains": domains}))
        collision = cli()
        assert collision.returncode == 1, collision.stdout + collision.stderr
        body = json.loads(collision.stdout)
        assert body["status"] == FAIL
        assert body["violations"][0]["code"] == "DOMAIN_CONTRACT_COLLISION"

        contract.unlink()
        missing = cli()
        assert missing.returncode == 2, missing.stdout + missing.stderr
        body = json.loads(missing.stdout)
        assert body["status"] == ERROR
        assert body["violations"][0]["code"] == "DOMAIN_UNIQUENESS_GATE_INPUT_INVALID"


# --- domain-uniqueness D4(a)/(b): SLI/SLO-signal and failure-vocabulary
# ownership (ADR-013 D4 addendum P-1..P-6, 2026-10-09) ---

def test_domain_uniqueness_foreign_slo_signal_in_prose_is_collision():
    """ADR-013 D4 addendum / TSD §24.1's own worked example: a billing
    domain's SLO prose names booking's declared SLI/SLO signal
    'booking-capacity' -- D2 phrase matching (casefold, hyphen/space
    separator equivalence) must catch this even spelled with a space and
    different case, and billing has no dependency on booking."""
    with tempfile.TemporaryDirectory() as tmp:
        domains = {
            "DOM-BOOKING": _dc_domain(
                commands=["booking.create"], runbook_ids=["RB-BOOKING"],
                slo_signals=["booking-capacity"],
                slo_text=["Booking tracks booking-capacity across venues."]),
            "DOM-BILLING": _dc_domain(
                commands=["billing.create"], runbook_ids=["RB-BILLING"],
                slo_text=["Billing SLOs monitor Booking Capacity nightly."]),
        }
        report = _du_run(domains, Path(tmp))
    assert report.status == FAIL, report.render()
    assert report.codes() == {"DOMAIN_CONTRACT_COLLISION"}
    violation = report.violations[0]
    assert violation.subject == "DOM-BILLING|DOM-BOOKING"
    assert "booking-capacity" in violation.detail
    assert "slo_text" in violation.detail


def test_domain_uniqueness_foreign_failure_term_in_prose_is_collision():
    """D4(b) on the failure-vocabulary dimension, exercising D2's CamelCase
    split: DOM-PAYMENTS declares failure_terms=['payment-timeout'] and
    DOM-SUPPORT's failure prose spells it 'PaymentTimeout' (CamelCase, no
    separator character at all) -- D2 phrase matching must still catch it."""
    with tempfile.TemporaryDirectory() as tmp:
        domains = {
            "DOM-PAYMENTS": _dc_domain(
                commands=["payments.create"], runbook_ids=["RB-PAYMENTS"],
                failure_terms=["payment-timeout"],
                failure_text=["Payments fails closed on payment-timeout."]),
            "DOM-SUPPORT": _dc_domain(
                commands=["support.create"], runbook_ids=["RB-SUPPORT"],
                failure_text=["Support escalates on a PaymentTimeout event."]),
        }
        report = _du_run(domains, Path(tmp))
    assert report.status == FAIL, report.render()
    assert report.codes() == {"DOMAIN_CONTRACT_COLLISION"}
    violation = report.violations[0]
    assert violation.subject == "DOM-SUPPORT|DOM-PAYMENTS"
    assert "payment-timeout" in violation.detail
    assert "failure_text" in violation.detail


def test_domain_uniqueness_dependency_listed_exempts_foreign_signal():
    """ADR-013 D4 addendum P-5: explicitly listing the declaring domain in
    `dependencies` exempts the foreign-signal hit that would otherwise
    collide -- DOM-BILLING lists DOM-BOOKING in its own dependencies."""
    with tempfile.TemporaryDirectory() as tmp:
        domains = {
            "DOM-BOOKING": _dc_domain(
                commands=["booking.create"], runbook_ids=["RB-BOOKING"],
                slo_signals=["booking-capacity"],
                slo_text=["Booking tracks booking-capacity across venues."]),
            "DOM-BILLING": _dc_domain(
                commands=["billing.create"], runbook_ids=["RB-BILLING"],
                dependencies=["DOM-BOOKING"],
                slo_text=["Billing SLOs monitor booking-capacity nightly."]),
        }
        report = _du_run(domains, Path(tmp))
    assert report.status == PASS, report.render()
    assert report.violations == []


def test_domain_uniqueness_co_declared_term_exempts_foreign_term():
    """ADR-013 D4 addendum P-5 / disclosed residual: when the scanned domain
    also declares the exact same term itself, D4(b) reads it as locally
    owned by both and does not collide -- no duplicate-ownership fail
    predicate has been decided (gate-6 lead decision D4 residual). Exercised
    on the failure-vocabulary dimension to cover both prose fields across
    the two exemption mechanisms."""
    with tempfile.TemporaryDirectory() as tmp:
        domains = {
            "DOM-PAYMENTS": _dc_domain(
                commands=["payments.create"], runbook_ids=["RB-PAYMENTS"],
                failure_terms=["timeout-exceeded"],
                failure_text=["Payments fails closed on timeout-exceeded."]),
            "DOM-SUPPORT": _dc_domain(
                commands=["support.create"], runbook_ids=["RB-SUPPORT"],
                failure_terms=["timeout-exceeded"],
                failure_text=["Support also tracks timeout-exceeded directly."]),
        }
        report = _du_run(domains, Path(tmp))
    assert report.status == PASS, report.render()
    assert report.violations == []


def test_domain_uniqueness_prose_phrase_match_requires_contiguous_whole_phrase():
    """D2's phrase-matching rule requires a *contiguous* whole-phrase match
    -- the declared term's tokens appearing in the same passage but
    separated by other words must not be treated as an occurrence (no
    stemming, synonyms, or fuzzy/similarity scoring)."""
    with tempfile.TemporaryDirectory() as tmp:
        domains = {
            "DOM-BOOKING": _dc_domain(
                commands=["booking.create"], runbook_ids=["RB-BOOKING"],
                slo_signals=["booking-capacity"],
                slo_text=["Booking tracks booking-capacity across venues."]),
            "DOM-BILLING": _dc_domain(
                commands=["billing.create"], runbook_ids=["RB-BILLING"],
                slo_text=[("Billing's booking volume approaches its capacity "
                           "limit nightly.")]),
        }
        report = _du_run(domains, Path(tmp))
    assert report.status == PASS, report.render()
    assert report.violations == []


def test_domain_uniqueness_missing_prose_field_is_error():
    """ADR-013 D4 addendum P-2/P-3: a domain record missing `slo_text` (the
    pre-addendum seven-field shape) is invalid input -- there is no
    optional/partial fallback and no load-time repair."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        legacy = _dc_domain(commands=["a.create"], runbook_ids=["RB-A"])
        del legacy["slo_text"]
        domains = {"DOM-A": legacy,
                   "DOM-B": _dc_domain(commands=["b.create"], runbook_ids=["RB-B"])}
        report = _du_run(domains, root)
    assert report.status == ERROR, report.render()
    assert report.codes() == {"DOMAIN_UNIQUENESS_GATE_INPUT_INVALID"}


def test_domain_uniqueness_empty_prose_value_is_error():
    """ADR-013 D4 addendum P-3: an empty `value` list for `slo_text`/
    `failure_text` is invalid, even though the other seven fields may be
    empty -- an empty observation would make D4(b) vacuously clean and
    D4(a) unsatisfiable without a stated cause."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bad_domain = _dc_domain(commands=["a.create"], runbook_ids=["RB-A"], slo_text=[])
        domains = {"DOM-A": bad_domain,
                   "DOM-B": _dc_domain(commands=["b.create"], runbook_ids=["RB-B"])}
        report = _du_run(domains, root)
    assert report.status == ERROR, report.render()
    assert report.codes() == {"DOMAIN_UNIQUENESS_GATE_INPUT_INVALID"}


def test_domain_uniqueness_prose_field_wrong_shape_is_error():
    """A `failure_text` value that is not a list (e.g. a bare string) is
    malformed input, exactly like the existing shape check reused unchanged
    from every other field (ADR-013 D4 addendum P-1: identical field
    shape)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bad_domain = _dc_domain(commands=["a.create"], runbook_ids=["RB-A"])
        bad_domain["failure_text"] = {"value": "not-a-list", "provenance": "synthetic"}
        domains = {"DOM-A": bad_domain,
                   "DOM-B": _dc_domain(commands=["b.create"], runbook_ids=["RB-B"])}
        report = _du_run(domains, root)
    assert report.status == ERROR, report.render()
    assert report.codes() == {"DOMAIN_UNIQUENESS_GATE_INPUT_INVALID"}


def test_domain_uniqueness_declared_term_not_observed_in_own_prose_is_error():
    """D4(a) anti-invention check (ADR-013 D4 addendum P-5): a declared term
    whose declaring field's own provenance is not `synthetic` must actually
    occur in that domain's own prose. This is a validator-behavior test of
    the fail-closed code path only -- it does not assert that the source
    pointer used reflects any real TSD text (no fabricated non-synthetic
    pointer is authorized to manufacture a positive result; this fixture
    manufactures the ERROR, not a PASS)."""
    with tempfile.TemporaryDirectory() as tmp:
        bad_domain = _dc_domain(
            commands=["a.create"], runbook_ids=["RB-A"],
            slo_signals=["never-mentioned-signal"],
            slo_signals_provenance="TSD §10.1 line 1",
            slo_text=["This domain's SLO prose names an unrelated signal."])
        domains = {"DOM-A": bad_domain,
                   "DOM-B": _dc_domain(commands=["b.create"], runbook_ids=["RB-B"])}
        report = _du_run(domains, Path(tmp))
    assert report.status == FAIL, report.render()
    assert report.codes() == {"DOMAIN_CONTRACT_TERM_UNOBSERVED"}
    violation = report.violations[0]
    assert violation.subject == "DOM-A"
    assert "never-mentioned-signal" in violation.detail


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"ok  {name}")
    print(f"PASS — all {len(tests)} tests passed.")
