#!/usr/bin/env python3
"""
Unit tests for `tools/validate_screen_source_inputs.py` -- the explicit
full per-screen Appendix F source-declaration validator for TSD §24.1
gate 5's `screen-contracts.yaml` (MOD-001 `IMPLEMENTATION.md` §10, EIP
Appendix F), per `R04-GATE5-FULL-SOURCE-CONTRACT-SELECTION-2026-10-09.md`'s
minimum next bounded work unit.

This tool is validation-only: it has no code path that writes or renders
the canonical `contracts/ui/screen-contracts.yaml` shape, and a complete
declaration set is reported only as `SOURCE INPUT SHAPE VALID`, never a
gate/manifest PASS.

Covers the three SCN-MOD001-118 cases directly (synthetic fixtures only,
never real bindings): (a) a normal row with a single clear owning module
and fully resolved route/API provenance resolves correctly; (b) a row
whose `screen_id` prefix matches no known UI surface fails closed naming
the id and "unknown prefix"; (c) a multi-domain row resolves to the
primary mutation/route contract's owner, never the secondary reference.

Run directly (`python3 tools/tests/test_validate_screen_source_inputs.py`)
or with pytest.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
from validate_screen_source_inputs import (
    DEFAULT_API_AUTHORITY,
    DEFAULT_ROUTE_AUTHORITY,
    DEFAULT_SCREEN_REGISTRY,
    PROVENANCE_ABSENT,
    SourceInputError,
    load_api_authority,
    load_declarations,
    load_route_authority,
    load_screen_registry,
    validate_declarations,
)

REGISTRY_2 = ["CON-01", "CON-02"]


def _row(screen_id="CON-01", owner_domain="Console", owner_module="mod_console", **overrides):
    row = {
        "screen_id": screen_id,
        "surface": "Console",
        "owner_domain": owner_domain,
        "owner_module": owner_module,
        "secondary_domains": [],
        "ownership_provenance": "EIP_APPENDIX_B:Console",
        "route": None,
        "route_provenance": PROVENANCE_ABSENT,
        "primary_read_model": None,
        "queries": [],
        "commands": [],
        "realtime_channels": [],
        "permissions": [],
        "assurance": "standard",
        "masking_variant": "none",
        "offline_mode": "unsupported",
        "expected_error_codes": [],
        "states": {"empty": "No data", "loading": "Loading", "error": "Retry"},
        "api_provenance": PROVENANCE_ABSENT,
    }
    row.update(overrides)
    return row


def _codes(violations):
    return {v.code for v in violations}


def _violations_for(canonical, declarations, route_authority=frozenset(), api_authority=frozenset()):
    violations, _ = validate_declarations(canonical, declarations, set(route_authority), set(api_authority))
    return violations


def _by_code(violations, code):
    return [v for v in violations if v.code == code]


# --- SCN-MOD001-118 (a)/(b)/(c) ------------------------------------------

def test_case_a_fully_resolved_row_is_shape_valid():
    """A normal row with a single clear owning module, and route/API
    provenance resolved against the supplied authority inputs, validates
    with zero violations and resolves ownership correctly."""
    row = _row(route="/console/overview", route_provenance="FRONTEND_ROUTE_REGISTRY",
               primary_read_model="console_overview_read",
               queries=["bff:console.overview_read"], api_provenance="OPENAPI_SPEC")
    violations, resolved = validate_declarations(
        ["CON-01"], [row],
        route_authority={"/console/overview"},
        api_authority={"bff:console.overview_read"},
    )
    assert violations == []
    assert resolved == {"CON-01": {"owner_domain": "Console", "owner_module": "mod_console"}}


def test_case_b_unknown_surface_prefix_cites_the_id():
    """A row whose screen_id prefix matches no known UI surface fails
    closed naming the specific id and the unknown-prefix reason."""
    row = _row(screen_id="ZZZ-01", owner_domain="Console")
    violations = _violations_for(["ZZZ-01"], [row])
    unknown = _by_code(violations, "UNKNOWN_SURFACE_PREFIX")
    assert len(unknown) == 1
    assert unknown[0].subject == "ZZZ-01"
    assert "unknown prefix" in unknown[0].detail


def test_case_c_multidomain_resolves_to_primary_not_secondary():
    """A multi-domain row resolves to the primary mutation/route contract's
    owning module -- the secondary domain is never promoted to owner. Route/
    API provenance stay ABSENT here (irrelevant to the ownership question),
    so PROVENANCE_UNRESOLVED is expected but no ownership/surface finding."""
    row = _row(screen_id="ADM-XX-01", owner_domain="Membership", owner_module="mod_membership",
               secondary_domains=["Payments"])
    violations, resolved = validate_declarations(["ADM-XX-01"], [row], set(), set())
    assert _codes(violations) == {"PROVENANCE_UNRESOLVED"}
    assert resolved == {"ADM-XX-01": {"owner_domain": "Membership", "owner_module": "mod_membership"}}
    assert "Payments" not in resolved["ADM-XX-01"].values()


def test_owner_domain_in_secondary_domains_is_incomplete_row():
    row = _row(secondary_domains=["Console"])  # owner_domain is also "Console"
    violations = _violations_for(["CON-01"], [row])
    assert "INCOMPLETE_DECLARATION_ROW" in _codes(violations)


# --- ownership provenance -------------------------------------------------

def test_ownership_provenance_absent_is_rejected():
    row = _row(ownership_provenance=PROVENANCE_ABSENT)
    violations = _violations_for(["CON-01"], [row])
    absent = _by_code(violations, "OWNERSHIP_PROVENANCE_ABSENT")
    assert len(absent) == 1
    assert absent[0].subject == "CON-01"


# --- route provenance pairing/verification --------------------------------

def test_absent_route_and_api_provenance_is_well_formed_but_still_fails_closed():
    """The default fixture row (both route and API provenance ABSENT)
    is structurally sound but still fails closed on both components --
    an honest gap declaration is never treated as coverage."""
    row1, row2 = _row(screen_id="CON-01"), _row(screen_id="CON-02")
    violations, resolved = validate_declarations(REGISTRY_2, [row1, row2], set(), set())
    unresolved = _by_code(violations, "PROVENANCE_UNRESOLVED")
    assert len(unresolved) == 4  # 2 rows x {route, api}
    assert {v.subject for v in unresolved} == {"CON-01", "CON-02"}
    assert _by_code(violations, "UNVERIFIABLE_PROVENANCE_POINTER") == []
    assert _by_code(violations, "ABSENT_PROVENANCE_VALUE_POPULATED") == []
    assert resolved == {
        "CON-01": {"owner_domain": "Console", "owner_module": "mod_console"},
        "CON-02": {"owner_domain": "Console", "owner_module": "mod_console"},
    }


def test_route_literal_paired_with_absent_provenance_is_denied():
    row = _row(route="/console/overview")  # route_provenance stays ABSENT
    violations = _violations_for(["CON-01"], [row])
    denied = _by_code(violations, "ABSENT_PROVENANCE_VALUE_POPULATED")
    assert len(denied) == 1
    assert denied[0].subject == "CON-01"
    assert "/console/overview" in denied[0].detail


def test_route_provenance_populated_but_route_null_is_incomplete():
    row = _row(route_provenance="FRONTEND_ROUTE_REGISTRY")  # route stays None
    violations = _violations_for(["CON-01"], [row])
    incomplete = _by_code(violations, "INCOMPLETE_DECLARATION_ROW")
    assert len(incomplete) == 1
    assert incomplete[0].subject == "CON-01"


def test_route_not_in_supplied_authority_is_unverifiable():
    row = _row(route="/console/overview", route_provenance="FRONTEND_ROUTE_REGISTRY")
    violations = _violations_for(["CON-01"], [row], route_authority={"/console/other"})
    unverifiable = _by_code(violations, "UNVERIFIABLE_PROVENANCE_POINTER")
    assert len(unverifiable) == 1
    assert unverifiable[0].subject == "CON-01"
    assert "/console/overview" in unverifiable[0].detail


def test_route_with_no_authority_supplied_at_all_is_unverifiable():
    row = _row(route="/console/overview", route_provenance="FRONTEND_ROUTE_REGISTRY")
    violations = _violations_for(["CON-01"], [row])  # no route_authority kwarg -> empty set
    assert "UNVERIFIABLE_PROVENANCE_POINTER" in _codes(violations)


def test_route_in_supplied_authority_resolves_with_no_violation():
    row = _row(route="/console/overview", route_provenance="FRONTEND_ROUTE_REGISTRY")
    violations = _violations_for(["CON-01"], [row], route_authority={"/console/overview"})
    route_related = [v for v in violations if v.subject == "CON-01" and "route" in v.detail.lower()]
    assert not any(v.code == "UNVERIFIABLE_PROVENANCE_POINTER" for v in route_related)


# --- API bundle provenance pairing/verification ---------------------------

def test_api_bundle_literal_paired_with_absent_provenance_is_denied():
    row = _row(queries=["bff:console.overview_read"])  # api_provenance stays ABSENT
    violations = _violations_for(["CON-01"], [row])
    denied = _by_code(violations, "ABSENT_PROVENANCE_VALUE_POPULATED")
    assert len(denied) == 1
    assert denied[0].subject == "CON-01"


def test_api_provenance_populated_but_bundle_empty_is_incomplete():
    row = _row(api_provenance="OPENAPI_SPEC")  # bundle fields all stay empty/None
    violations = _violations_for(["CON-01"], [row])
    incomplete = _by_code(violations, "INCOMPLETE_DECLARATION_ROW")
    assert len(incomplete) == 1
    assert incomplete[0].subject == "CON-01"


def test_api_bundle_entry_not_in_supplied_authority_is_unverifiable():
    row = _row(commands=["command:console.update"], api_provenance="OPENAPI_SPEC")
    violations = _violations_for(["CON-01"], [row], api_authority={"command:console.other"})
    unverifiable = _by_code(violations, "UNVERIFIABLE_PROVENANCE_POINTER")
    assert len(unverifiable) == 1
    assert "command:console.update" in unverifiable[0].detail


def test_api_bundle_entries_in_supplied_authority_resolve_with_no_violation():
    row = _row(queries=["bff:console.overview_read"], realtime_channels=["channel:console.updates"],
               api_provenance="OPENAPI_SPEC")
    violations = _violations_for(
        ["CON-01"], [row],
        api_authority={"bff:console.overview_read", "channel:console.updates"},
    )
    assert _by_code(violations, "UNVERIFIABLE_PROVENANCE_POINTER") == []


# --- structural/negative controls -----------------------------------------

def test_missing_screen_declaration_cites_the_uncovered_id():
    violations = _violations_for(REGISTRY_2, [_row(screen_id="CON-01")])
    missing = _by_code(violations, "MISSING_SCREEN_DECLARATION")
    assert len(missing) == 1
    assert missing[0].subject == "CON-02"


def test_unknown_screen_id_cites_the_extra_id():
    extra_row = _row(screen_id="CON-99")
    violations = _violations_for(REGISTRY_2, [_row(screen_id="CON-01"), _row(screen_id="CON-02"), extra_row])
    unknown = _by_code(violations, "UNKNOWN_SCREEN_ID")
    assert len(unknown) == 1
    assert unknown[0].subject == "CON-99"


def test_incomplete_row_missing_field_cites_screen_id_when_present():
    incomplete = {"screen_id": "CON-01", "owner_module": "mod_console"}  # most fields missing
    violations = _violations_for(REGISTRY_2, [incomplete, _row(screen_id="CON-02")])
    incomplete_v = _by_code(violations, "INCOMPLETE_DECLARATION_ROW")
    assert len(incomplete_v) == 1
    assert incomplete_v[0].subject == "CON-01"


def test_incomplete_row_with_no_screen_id_cites_row_index():
    incomplete = {"owner_module": "mod_console"}
    violations = _violations_for(REGISTRY_2, [incomplete, _row(screen_id="CON-02")])
    incomplete_v = _by_code(violations, "INCOMPLETE_DECLARATION_ROW")
    assert len(incomplete_v) == 1
    assert incomplete_v[0].subject == "declarations[0]"


def test_blank_owner_module_is_incomplete_row():
    row = _row(owner_module="   ")
    assert "INCOMPLETE_DECLARATION_ROW" in _codes(_violations_for(["CON-01"], [row]))


def test_route_without_leading_slash_is_incomplete_row():
    row = _row(route="console/overview", route_provenance="X")
    assert "INCOMPLETE_DECLARATION_ROW" in _codes(_violations_for(["CON-01"], [row]))


def test_states_missing_key_is_incomplete_row():
    row = _row(states={"empty": "No data", "loading": "Loading"})  # "error" missing
    assert "INCOMPLETE_DECLARATION_ROW" in _codes(_violations_for(["CON-01"], [row]))


def test_duplicate_identical_rows_cite_the_id():
    row = _row()
    violations = _violations_for(["CON-01"], [row, dict(row)])
    duplicate = _by_code(violations, "DUPLICATE_DECLARATION_ID")
    assert len(duplicate) == 1
    assert duplicate[0].subject == "CON-01"
    assert "CONFLICTING_DECLARATION_ID" not in _codes(violations)


def test_conflicting_rows_cite_the_id():
    row = _row()
    conflicting = _row(owner_module="mod_billing")
    violations = _violations_for(["CON-01"], [row, conflicting])
    ambiguous = _by_code(violations, "CONFLICTING_DECLARATION_ID")
    assert len(ambiguous) == 1
    assert ambiguous[0].subject == "CON-01"
    assert "DUPLICATE_DECLARATION_ID" not in _codes(violations)


# --- whole-file input validation ------------------------------------------

def test_load_screen_registry_rejects_wrong_shape():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "screen-registry.json"
        path.write_text(json.dumps({"version": 1, "screens": ["CON-01", "CON-01"]}))
        try:
            load_screen_registry(path)
        except SourceInputError as exc:
            assert "duplicate" in str(exc).lower()
        else:
            raise AssertionError("accepted a registry with a duplicate Screen ID")


def test_load_declarations_rejects_wrong_top_level_shape():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "declarations.json"
        path.write_text(json.dumps({"version": 1, "rows": []}))  # wrong key
        try:
            load_declarations(path)
        except SourceInputError as exc:
            assert "declarations" in str(exc)
        else:
            raise AssertionError("accepted a declarations file with the wrong top-level shape")


def test_load_declarations_rejects_missing_file():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            load_declarations(Path(tmp) / "nope.json")
        except SourceInputError as exc:
            assert "not found" in str(exc)
        else:
            raise AssertionError("accepted a nonexistent declarations file")


def test_load_route_authority_rejects_duplicate_entries():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "routes.json"
        path.write_text(json.dumps({"version": 1, "routes": ["/a", "/a"]}))
        try:
            load_route_authority(path)
        except SourceInputError as exc:
            assert "duplicate" in str(exc).lower()
        else:
            raise AssertionError("accepted a route-authority input with duplicate entries")


def test_load_api_authority_returns_empty_set_when_path_is_none():
    assert load_api_authority(None) == set()


def test_load_route_authority_returns_empty_set_when_path_is_none():
    assert load_route_authority(None) == set()


# --- assurance control: the real 170-screen registry, no fabricated rows --

def test_real_committed_registry_with_no_declarations_fails_closed_citing_every_id():
    """The repository has no authoritative owner/route/API declaration
    source yet; running against the real canonical registry with zero
    declaration coverage must deny, citing all 170 IDs -- never silently
    materialize a 170-row placeholder manifest."""
    canonical = load_screen_registry(DEFAULT_SCREEN_REGISTRY)
    assert len(canonical) == 170
    violations, resolved = validate_declarations(canonical, [], set(), set())
    assert resolved == {}
    assert _codes(violations) == {"MISSING_SCREEN_DECLARATION"}
    assert len(violations) == 170
    assert {v.subject for v in violations} == set(canonical)


# --- CLI -------------------------------------------------------------------

def _write(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj))


def test_cli_fully_resolved_declarations_report_shape_valid():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reg, decl = root / "screen-registry.json", root / "declarations.json"
        routes, apis = root / "routes.json", root / "apis.json"
        _write(reg, {"version": 1, "screens": ["CON-01"]})
        row = _row(route="/console/overview", route_provenance="FRONTEND_ROUTE_REGISTRY",
                   primary_read_model="console_overview_read",
                   queries=["bff:console.overview_read"], api_provenance="OPENAPI_SPEC")
        _write(decl, {"version": 1, "declarations": [row]})
        _write(routes, {"version": 1, "routes": ["/console/overview"]})
        _write(apis, {"version": 1, "operations": ["bff:console.overview_read"]})
        result = subprocess.run(
            [sys.executable, str(TOOLS / "validate_screen_source_inputs.py"),
             "--screen-registry", str(reg), "--declarations", str(decl),
             "--route-authority", str(routes), "--api-authority", str(apis)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "SOURCE INPUT SHAPE VALID" in result.stdout
        assert "gate-5/manifest PASS" in result.stdout


def test_cli_without_authority_flags_is_unverifiable():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reg, decl = root / "screen-registry.json", root / "declarations.json"
        _write(reg, {"version": 1, "screens": ["CON-01"]})
        row = _row(route="/console/overview", route_provenance="FRONTEND_ROUTE_REGISTRY")
        _write(decl, {"version": 1, "declarations": [row]})
        result = subprocess.run(
            [sys.executable, str(TOOLS / "validate_screen_source_inputs.py"),
             "--screen-registry", str(reg), "--declarations", str(decl)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 2, result.stdout + result.stderr
        assert "UNVERIFIABLE_PROVENANCE_POINTER" in result.stderr
        assert "SOURCE INPUT SHAPE VALID" not in result.stdout


def test_committed_authority_registries_load_as_empty_sets():
    assert DEFAULT_ROUTE_AUTHORITY.is_file() and DEFAULT_API_AUTHORITY.is_file()
    assert load_route_authority(DEFAULT_ROUTE_AUTHORITY) == set()
    assert load_api_authority(DEFAULT_API_AUTHORITY) == set()


def test_cli_default_authorities_leave_route_and_api_pointers_unverifiable():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reg, decl = root / "screen-registry.json", root / "declarations.json"
        _write(reg, {"version": 1, "screens": ["CON-01"]})
        row = _row(route="/console/overview", route_provenance="FRONTEND_ROUTE_REGISTRY",
                   primary_read_model="console_overview_read",
                   queries=["bff:console.overview_read"], api_provenance="OPENAPI_SPEC")
        _write(decl, {"version": 1, "declarations": [row]})
        result = subprocess.run(
            [sys.executable, str(TOOLS / "validate_screen_source_inputs.py"),
             "--screen-registry", str(reg), "--declarations", str(decl)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 2, result.stdout + result.stderr
        assert "route '/console/overview' does not appear" in result.stderr
        assert "queries entry 'bff:console.overview_read' does not appear" in result.stderr
        assert "SOURCE INPUT SHAPE VALID" not in result.stdout


def test_cli_requires_explicit_declarations_flag():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reg = root / "screen-registry.json"
        _write(reg, {"version": 1, "screens": ["CON-01"]})
        result = subprocess.run(
            [sys.executable, str(TOOLS / "validate_screen_source_inputs.py"),
             "--screen-registry", str(reg)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 2
        assert "declarations" in result.stderr.lower()


def test_cli_rejects_output_flag_and_writes_no_canonical_file():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reg, decl = root / "screen-registry.json", root / "declarations.json"
        out = root / "screen-contracts.yaml"
        _write(reg, {"version": 1, "screens": ["CON-01"]})
        _write(decl, {"version": 1, "declarations": [_row()]})
        result = subprocess.run(
            [sys.executable, str(TOOLS / "validate_screen_source_inputs.py"),
             "--screen-registry", str(reg), "--declarations", str(decl),
             "--output", str(out)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode != 0
        assert "unrecognized arguments" in result.stderr
        assert not out.exists()


def test_cli_real_registry_with_empty_declarations_fails_closed_without_output():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        decl = root / "declarations.json"
        _write(decl, {"version": 1, "declarations": []})
        result = subprocess.run(
            [sys.executable, str(TOOLS / "validate_screen_source_inputs.py"),
             "--declarations", str(decl)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 2, result.stdout + result.stderr
        assert result.stderr.count("MISSING_SCREEN_DECLARATION") == 170
        assert {p.name for p in root.iterdir()} == {decl.name}


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"ok  {name}")
    print(f"PASS — all {len(tests)} tests passed.")
