#!/usr/bin/env python3
"""
Unit tests for `tools/generate_screen_contracts.py` -- the explicit
mapping-input validator for TSD §24.1 gate 5's `screen-contracts.yaml`
(MOD-001 `IMPLEMENTATION.md` §10 steps 4-6, EIP Appendix F). This tool is
validation-only (subgoal R04-GATE5-PARTIAL-CANONICAL-OUTPUT-DENIAL,
2026-10-09): it has no code path that writes or renders the canonical
`contracts/ui/screen-contracts.yaml` shape, and a complete mapping-input
is reported only as `SOURCE INPUT SHAPE VALID`, never a gate/manifest
PASS.

Per-row provenance (subgoal R04-GATE5-PROVENANCE-INPUT-VALIDATOR,
2026-10-09, following the R04 gate-5 source-authority lead decision): every
row now also carries a `provenance` object with `route`/`target`
components. Since this repository has no authoritative frontend route
registry, OpenAPI, or AsyncAPI source, the validator can only ever accept
the literal `ABSENT_NO_AUTHORITATIVE_SOURCE` as a well-formed provenance
value -- and even that is deliberately NOT treated as success, so a
fully-covered, otherwise-unambiguous mapping-input still fails closed
("absent unresolved" control below). Any other provenance string is a
purported pointer this tool cannot verify and is rejected outright
("bare-literal denial" control below).

Absence pairing (subgoal R04-GATE5-ABSENT-VALUE-CORRECTION, 2026-10-09,
correcting a residual from the provenance-input validator above): `route`
and `target` are each nullable and must pair exactly with their own
`provenance` component. When `provenance.<field>` is the literal
`ABSENT_NO_AUTHORITATIVE_SOURCE`, `<field>` itself must be `null` --
never a populated literal, which is exactly the "inferred route" EIP
Appendix F forbids for a cell with no authoritative source. A row that
pairs a populated literal with ABSENT provenance fails closed
(`ABSENT_PROVENANCE_VALUE_POPULATED`), checked independently for `route`
and for `target`.

Negative controls (ID/count/missing/extra/duplicate/ambiguous, unchanged
in kind from the prior revision): a missing per-screen binding, an
unknown/extra Screen ID, an incomplete row, a malformed target, a
duplicate row, and a pair of conflicting ("ambiguous") rows for the same
Screen ID each fail closed citing the offending Screen ID (or row index).

Assurance control: running against the real, committed 170-ID canonical
registry with no mapping-input coverage fails closed citing every single
one of the 170 IDs as `MISSING_SCREEN_BINDING` -- never a silently
materialized placeholder-completed manifest.

CLI controls: no mapping-input -- complete or not -- ever produces a
canonical output file (there is no `--output` option at all); attempting
to pass `--output` is rejected by argparse itself.

Run directly (`python3 tools/tests/test_generate_screen_contracts.py`) or
with pytest.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
from generate_screen_contracts import (
    DEFAULT_SCREEN_REGISTRY,
    PROVENANCE_ABSENT,
    MappingInputError,
    load_mapping_input,
    load_screen_registry,
    validate_mappings,
)

REGISTRY_2 = ["CON-01", "CON-02"]
ABSENT_PROVENANCE = {"route": PROVENANCE_ABSENT, "target": PROVENANCE_ABSENT}
# ABSENT provenance pairs with a null route/target -- see the module
# docstring's "Absence pairing" note and ABSENT_PROVENANCE_VALUE_POPULATED.
ROW_1 = {"screen_id": "CON-01", "owner_module": "mod_console",
         "route": None, "target": None,
         "provenance": dict(ABSENT_PROVENANCE)}
ROW_2 = {"screen_id": "CON-02", "owner_module": "mod_console",
         "route": None, "target": None,
         "provenance": dict(ABSENT_PROVENANCE)}


def _codes(violations):
    return {v.code for v in violations}


def _violations_for(canonical, mappings):
    violations, _ = validate_mappings(canonical, mappings)
    return violations


def _by_code(violations, code):
    return [v for v in violations if v.code == code]


# --- provenance controls -----------------------------------------------

def test_absent_provenance_is_well_formed_but_still_fails_closed():
    """The sole literal this tool accepts in place of a real resolvable
    pointer must not be mistaken for success: a structurally complete,
    unambiguous mapping-input covering every canonical Screen ID with
    explicit ABSENT provenance still fails closed on every route/target
    component, never reporting SOURCE INPUT SHAPE VALID coverage."""
    violations, target_by_id = validate_mappings(REGISTRY_2, [ROW_1, ROW_2])
    unresolved = _by_code(violations, "PROVENANCE_UNRESOLVED")
    assert len(unresolved) == 4  # 2 rows x {route, target}
    assert {v.subject for v in unresolved} == {"CON-01", "CON-02"}
    assert _by_code(violations, "UNVERIFIABLE_PROVENANCE_POINTER") == []
    assert _by_code(violations, "ABSENT_PROVENANCE_VALUE_POPULATED") == []
    assert _by_code(violations, "MISSING_SCREEN_BINDING") == []
    # The diagnostic target map is still populated -- it is an aid, not a
    # success gate -- but `violations` is non-empty, so no caller may treat
    # this as route/API coverage. Both rows correctly pair ABSENT provenance
    # with a null target, so the map holds null, never an invented target.
    assert target_by_id == {"CON-01": None, "CON-02": None}
    assert violations  # never zero-violation for a row with real provenance


def test_bare_literal_provenance_pointer_is_rejected():
    """A nominal-looking pointer string (anything other than the literal
    ABSENT_NO_AUTHORITATIVE_SOURCE) must never be accepted as authoritative
    -- this repository has no route registry/OpenAPI/AsyncAPI source to
    verify it against, so it is rejected, not trusted at face value."""
    row = dict(ROW_1, route="/console/overview",
               provenance={"route": "contracts/ui/routes.json#CON-01",
                           "target": PROVENANCE_ABSENT})
    violations = _violations_for(REGISTRY_2, [row, ROW_2])
    unverifiable = _by_code(violations, "UNVERIFIABLE_PROVENANCE_POINTER")
    assert len(unverifiable) == 1
    assert unverifiable[0].subject == "CON-01"
    assert "contracts/ui/routes.json#CON-01" in unverifiable[0].detail
    assert _by_code(violations, "ABSENT_PROVENANCE_VALUE_POPULATED") == []
    # The companion target component, left ABSENT, is still its own
    # distinct (fail-closed) finding, not silently folded into the denial.
    assert any(v.code == "PROVENANCE_UNRESOLVED" and v.subject == "CON-01"
               for v in violations)


def test_both_bare_literal_provenance_components_are_each_rejected():
    row = dict(ROW_1, provenance={"route": "/console/overview",
                                   "target": "bff:console.overview_read"})
    violations = _violations_for(["CON-01"], [row])
    unverifiable = _by_code(violations, "UNVERIFIABLE_PROVENANCE_POINTER")
    assert len(unverifiable) == 2
    assert {v.subject for v in unverifiable} == {"CON-01"}
    assert _by_code(violations, "PROVENANCE_UNRESOLVED") == []
    assert _by_code(violations, "ABSENT_PROVENANCE_VALUE_POPULATED") == []


def test_route_literal_paired_with_absent_provenance_is_denied():
    """The corrected bug: a cell with no authoritative source must be
    absent (null), never filled with a literal value -- a populated
    `route` paired with ABSENT `provenance.route` is exactly the
    "inferred route" EIP Appendix F forbids, and must fail closed citing
    the screen ID and the `route` field specifically."""
    row = dict(ROW_1, route="/console/overview")  # provenance.route stays ABSENT
    violations = _violations_for(REGISTRY_2, [row, ROW_2])
    denied = _by_code(violations, "ABSENT_PROVENANCE_VALUE_POPULATED")
    assert len(denied) == 1
    assert denied[0].subject == "CON-01"
    assert "route" in denied[0].detail
    assert "/console/overview" in denied[0].detail


def test_target_literal_paired_with_absent_provenance_is_denied():
    """Same correction, independently for `target`."""
    row = dict(ROW_1, target="bff:console.overview_read")  # provenance.target stays ABSENT
    violations = _violations_for(REGISTRY_2, [row, ROW_2])
    denied = _by_code(violations, "ABSENT_PROVENANCE_VALUE_POPULATED")
    assert len(denied) == 1
    assert denied[0].subject == "CON-01"
    assert "target" in denied[0].detail
    assert "bff:console.overview_read" in denied[0].detail


def test_null_route_and_target_with_absent_provenance_is_the_only_accepted_pairing():
    """The positive control for the fix: null route/target paired with
    ABSENT provenance is structurally accepted (no INCOMPLETE_MAPPING_ROW
    or ABSENT_PROVENANCE_VALUE_POPULATED) -- it still fails closed via
    PROVENANCE_UNRESOLVED, never SOURCE INPUT SHAPE VALID coverage."""
    violations = _violations_for(["CON-01"], [ROW_1])
    assert _by_code(violations, "INCOMPLETE_MAPPING_ROW") == []
    assert _by_code(violations, "ABSENT_PROVENANCE_VALUE_POPULATED") == []
    assert _codes(violations) == {"PROVENANCE_UNRESOLVED"}


def test_target_literal_paired_with_absent_provenance_never_escapes_into_target_map():
    """The corrected residual (R04-GATE5-ABSENT-VALUE-LOCAL-RECONCILIATION,
    2026-10-09): a `target` literal paired with ABSENT provenance still
    reaches `by_id` (it carries ABSENT_PROVENANCE_VALUE_POPULATED, not an
    early-continue code), but it must never surface in the in-memory
    diagnostic target map -- the map may only ever hold `None` for an
    unverified target."""
    row = dict(ROW_1, target="bff:console.overview_read")  # provenance.target stays ABSENT
    violations, target_by_id = validate_mappings(["CON-01"], [row])
    assert _by_code(violations, "ABSENT_PROVENANCE_VALUE_POPULATED")
    assert target_by_id == {"CON-01": None}


def test_target_literal_with_unverifiable_pointer_never_escapes_into_target_map():
    """Same correction for the other path to a populated-but-unverified
    target: a literal `target` whose provenance is a purported (not ABSENT)
    pointer is still unverifiable and must not escape into the target map
    either."""
    row = dict(ROW_1, target="bff:console.overview_read",
               provenance={"route": PROVENANCE_ABSENT,
                           "target": "contracts/api/openapi.yaml#CON-01"})
    violations, target_by_id = validate_mappings(["CON-01"], [row])
    assert _by_code(violations, "UNVERIFIABLE_PROVENANCE_POINTER")
    assert target_by_id == {"CON-01": None}


def test_missing_provenance_field_is_incomplete_row():
    """`provenance` is one of the required row fields -- omitting it
    entirely must be caught as a structural defect, not treated as an
    implicit ABSENT."""
    row = {k: v for k, v in ROW_1.items() if k != "provenance"}
    violations = _violations_for(REGISTRY_2, [row, ROW_2])
    incomplete = _by_code(violations, "INCOMPLETE_MAPPING_ROW")
    assert len(incomplete) == 1
    assert incomplete[0].subject == "CON-01"


def test_provenance_missing_a_component_is_incomplete_row():
    row = dict(ROW_1, provenance={"route": PROVENANCE_ABSENT})  # target component missing
    violations = _violations_for(REGISTRY_2, [row, ROW_2])
    assert "INCOMPLETE_MAPPING_ROW" in _codes(violations)


def test_provenance_blank_component_is_incomplete_row():
    row = dict(ROW_1, provenance={"route": "   ", "target": PROVENANCE_ABSENT})
    violations = _violations_for(REGISTRY_2, [row, ROW_2])
    assert "INCOMPLETE_MAPPING_ROW" in _codes(violations)


def test_provenance_not_an_object_is_incomplete_row():
    row = dict(ROW_1, provenance=PROVENANCE_ABSENT)
    violations = _violations_for(REGISTRY_2, [row, ROW_2])
    assert "INCOMPLETE_MAPPING_ROW" in _codes(violations)


# --- negative controls: fail-closed on each documented condition -----------

def test_missing_screen_binding_cites_the_uncovered_id():
    violations = _violations_for(REGISTRY_2, [ROW_1])
    missing = _by_code(violations, "MISSING_SCREEN_BINDING")
    assert len(missing) == 1
    assert missing[0].subject == "CON-02"


def test_unknown_screen_id_cites_the_extra_id():
    extra_row = dict(ROW_1, screen_id="CON-99")
    violations = _violations_for(REGISTRY_2, [ROW_1, ROW_2, extra_row])
    unknown = _by_code(violations, "UNKNOWN_SCREEN_ID")
    assert len(unknown) == 1
    assert unknown[0].subject == "CON-99"


def test_incomplete_row_missing_field_cites_screen_id_when_present():
    incomplete = {"screen_id": "CON-01", "owner_module": "mod_console",
                  "route": "/console/overview"}  # target, provenance missing
    violations = _violations_for(REGISTRY_2, [incomplete, ROW_2])
    incomplete_v = _by_code(violations, "INCOMPLETE_MAPPING_ROW")
    assert len(incomplete_v) == 1
    assert incomplete_v[0].subject == "CON-01"


def test_incomplete_row_with_no_screen_id_cites_row_index():
    incomplete = {"owner_module": "mod_console", "route": "/console/overview",
                  "target": "bff:console.overview_read"}  # screen_id, provenance missing
    violations = _violations_for(REGISTRY_2, [incomplete, ROW_2])
    incomplete_v = _by_code(violations, "INCOMPLETE_MAPPING_ROW")
    assert len(incomplete_v) == 1
    assert incomplete_v[0].subject == "mappings[0]"


def test_blank_owner_module_is_incomplete_row():
    row = dict(ROW_1, owner_module="   ")
    violations = _violations_for(REGISTRY_2, [row, ROW_2])
    assert "INCOMPLETE_MAPPING_ROW" in _codes(violations)


def test_route_without_leading_slash_is_incomplete_row():
    row = dict(ROW_1, route="console/overview")
    violations = _violations_for(REGISTRY_2, [row, ROW_2])
    assert "INCOMPLETE_MAPPING_ROW" in _codes(violations)


def test_malformed_target_cites_id_as_invalid_target():
    row = dict(ROW_1, target="https://example.com/overview")
    violations = _violations_for(REGISTRY_2, [row, ROW_2])
    invalid = _by_code(violations, "INVALID_TARGET")
    assert len(invalid) == 1
    assert invalid[0].subject == "CON-01"


def test_duplicate_identical_rows_cite_the_id():
    violations = _violations_for(["CON-01"], [ROW_1, dict(ROW_1)])
    duplicate = _by_code(violations, "DUPLICATE_MAPPING_ID")
    assert len(duplicate) == 1
    assert duplicate[0].subject == "CON-01"
    assert "AMBIGUOUS_MAPPING_ID" not in _codes(violations)


def test_ambiguous_conflicting_rows_cite_the_id():
    conflicting = dict(ROW_1, owner_module="mod_billing", target="bff:billing.overview_read")
    violations = _violations_for(["CON-01"], [ROW_1, conflicting])
    ambiguous = _by_code(violations, "AMBIGUOUS_MAPPING_ID")
    assert len(ambiguous) == 1
    assert ambiguous[0].subject == "CON-01"
    assert "DUPLICATE_MAPPING_ID" not in _codes(violations)


def test_violations_present_means_target_map_is_incomplete():
    """When violations exist, the diagnostic target map (an in-memory aid
    only -- see `validate_mappings` docstring) still reflects every row
    that reached the registry, never a rendered or written manifest."""
    violations, target_by_id = validate_mappings(REGISTRY_2, [ROW_1])
    assert violations
    assert target_by_id == {"CON-01": None}


# --- whole-file input validation --------------------------------------------

def test_load_screen_registry_rejects_wrong_shape():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "screen-registry.json"
        path.write_text(json.dumps({"version": 1, "screens": ["CON-01", "CON-01"]}))
        try:
            load_screen_registry(path)
        except MappingInputError as exc:
            assert "duplicate" in str(exc).lower()
        else:
            raise AssertionError("accepted a registry with a duplicate Screen ID")


def test_load_mapping_input_rejects_wrong_top_level_shape():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "mapping-input.json"
        path.write_text(json.dumps({"version": 1, "rows": []}))  # wrong key
        try:
            load_mapping_input(path)
        except MappingInputError as exc:
            assert "mapping-input" in str(exc)
        else:
            raise AssertionError("accepted a mapping-input file with the wrong top-level shape")


def test_load_mapping_input_rejects_missing_file():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            load_mapping_input(Path(tmp) / "nope.json")
        except MappingInputError as exc:
            assert "not found" in str(exc)
        else:
            raise AssertionError("accepted a nonexistent mapping-input file")


# --- assurance control: the real 170-screen registry, no fabricated rows ---

def test_real_committed_registry_with_no_mapping_fails_closed_citing_every_id():
    """The repository has no authoritative owner/route/API binding source
    yet (see module docstring); running against the real canonical
    registry with zero mapping coverage must deny, citing all 170 IDs --
    never silently materialize a 170-row placeholder manifest."""
    canonical = load_screen_registry(DEFAULT_SCREEN_REGISTRY)
    assert len(canonical) == 170
    violations, target_by_id = validate_mappings(canonical, [])
    assert target_by_id == {}
    assert _codes(violations) == {"MISSING_SCREEN_BINDING"}
    assert len(violations) == 170
    assert {v.subject for v in violations} == set(canonical)


def test_real_committed_registry_with_partial_mapping_still_fails_closed():
    """Even the one declared row -- well-formed, unambiguous, explicit
    ABSENT provenance -- does not count as route/API coverage: it still
    contributes its own PROVENANCE_UNRESOLVED findings rather than a pass,
    alongside MISSING_SCREEN_BINDING for the other 169 IDs."""
    canonical = load_screen_registry(DEFAULT_SCREEN_REGISTRY)
    one_id = canonical[0]
    row = {"screen_id": one_id, "owner_module": "mod_example",
           "route": None, "target": None,
           "provenance": dict(ABSENT_PROVENANCE)}
    violations, target_by_id = validate_mappings(canonical, [row])
    assert target_by_id == {one_id: None}
    assert _by_code(violations, "ABSENT_PROVENANCE_VALUE_POPULATED") == []
    missing = _by_code(violations, "MISSING_SCREEN_BINDING")
    assert len(missing) == 169
    assert one_id not in {v.subject for v in missing}
    unresolved = _by_code(violations, "PROVENANCE_UNRESOLVED")
    assert len(unresolved) == 2
    assert {v.subject for v in unresolved} == {one_id}
    assert len(violations) == 171


# --- CLI ----------------------------------------------------------------

def _write_mapping_input(path: Path, rows: list[dict]) -> None:
    path.write_text(json.dumps({"version": 1, "mappings": rows}))


def _write_registry(path: Path, screens: list[str]) -> None:
    path.write_text(json.dumps({"version": 1, "screens": screens}))


def test_cli_fully_covered_but_absent_provenance_still_fails_closed_and_writes_no_file():
    """Full, unambiguous Screen ID coverage with only the accepted ABSENT
    provenance literal must still deny -- SOURCE INPUT SHAPE VALID must
    never appear when route/API authority is unestablished -- and no
    canonical file may be written regardless."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reg = root / "screen-registry.json"
        mapping = root / "mapping-input.json"
        _write_registry(reg, REGISTRY_2)
        _write_mapping_input(mapping, [ROW_1, ROW_2])
        result = subprocess.run(
            [sys.executable, str(TOOLS / "generate_screen_contracts.py"),
             "--screen-registry", str(reg), "--mapping-input", str(mapping)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 2, result.stdout + result.stderr
        assert "SOURCE INPUT SHAPE VALID" not in result.stdout
        assert result.stderr.count("PROVENANCE_UNRESOLVED") == 4
        assert {p.name for p in root.iterdir()} == {reg.name, mapping.name}


def test_cli_rejects_bare_literal_provenance_pointer():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reg = root / "screen-registry.json"
        mapping = root / "mapping-input.json"
        out = root / "screen-contracts.yaml"
        bad_row = dict(ROW_1, provenance={"route": "contracts/ui/routes.json#CON-01",
                                           "target": PROVENANCE_ABSENT})
        _write_registry(reg, REGISTRY_2)
        _write_mapping_input(mapping, [bad_row, ROW_2])
        result = subprocess.run(
            [sys.executable, str(TOOLS / "generate_screen_contracts.py"),
             "--screen-registry", str(reg), "--mapping-input", str(mapping)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 2, result.stdout + result.stderr
        assert "UNVERIFIABLE_PROVENANCE_POINTER" in result.stderr
        assert "CON-01" in result.stderr
        assert not out.exists()


def test_cli_rejects_route_literal_paired_with_absent_provenance():
    """End-to-end CLI control for the corrected bug: a populated `route`
    paired with ABSENT `provenance.route` must deny through the CLI entry
    point too, not only through the library function."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reg = root / "screen-registry.json"
        mapping = root / "mapping-input.json"
        out = root / "screen-contracts.yaml"
        bad_row = dict(ROW_1, route="/console/overview")  # provenance.route stays ABSENT
        _write_registry(reg, REGISTRY_2)
        _write_mapping_input(mapping, [bad_row, ROW_2])
        result = subprocess.run(
            [sys.executable, str(TOOLS / "generate_screen_contracts.py"),
             "--screen-registry", str(reg), "--mapping-input", str(mapping)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 2, result.stdout + result.stderr
        assert "ABSENT_PROVENANCE_VALUE_POPULATED" in result.stderr
        assert "CON-01" in result.stderr
        assert not out.exists()


def test_cli_fails_closed_without_writing_any_file_when_binding_missing():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reg = root / "screen-registry.json"
        mapping = root / "mapping-input.json"
        _write_registry(reg, REGISTRY_2)
        _write_mapping_input(mapping, [ROW_1])
        result = subprocess.run(
            [sys.executable, str(TOOLS / "generate_screen_contracts.py"),
             "--screen-registry", str(reg), "--mapping-input", str(mapping)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 2, result.stdout + result.stderr
        assert "MISSING_SCREEN_BINDING" in result.stderr
        assert "CON-02" in result.stderr
        assert {p.name for p in root.iterdir()} == {reg.name, mapping.name}


def test_cli_rejects_output_flag_and_writes_no_canonical_file():
    """There is no `--output` option on this validation-only tool --
    attempting it must be rejected by argparse itself (not silently
    accepted/ignored), and no canonical output may appear anywhere."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reg = root / "screen-registry.json"
        mapping = root / "mapping-input.json"
        out = root / "screen-contracts.yaml"
        _write_registry(reg, REGISTRY_2)
        _write_mapping_input(mapping, [ROW_1, ROW_2])
        result = subprocess.run(
            [sys.executable, str(TOOLS / "generate_screen_contracts.py"),
             "--screen-registry", str(reg), "--mapping-input", str(mapping),
             "--output", str(out)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode != 0, result.stdout + result.stderr
        assert "unrecognized arguments" in result.stderr
        assert "--output" in result.stderr
        assert not out.exists()


def test_cli_requires_explicit_mapping_input_flag():
    """No default mapping-input path exists -- omitting the flag must be a
    CLI usage error, never a silent read of some assumed default file."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reg = root / "screen-registry.json"
        _write_registry(reg, REGISTRY_2)
        result = subprocess.run(
            [sys.executable, str(TOOLS / "generate_screen_contracts.py"),
             "--screen-registry", str(reg)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode != 0
        assert "mapping-input" in result.stderr


def test_cli_fails_closed_on_missing_mapping_input_file():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reg = root / "screen-registry.json"
        _write_registry(reg, REGISTRY_2)
        result = subprocess.run(
            [sys.executable, str(TOOLS / "generate_screen_contracts.py"),
             "--screen-registry", str(reg),
             "--mapping-input", str(root / "nope.json")],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 2, result.stdout + result.stderr
        assert {p.name for p in root.iterdir()} == {reg.name}


def test_cli_real_registry_with_empty_mapping_input_fails_closed_without_output():
    """End-to-end assurance: invoking the real CLI against the real,
    committed 170-screen registry with an empty mapping-input denies and
    writes nothing -- the fail-closed behaviour holds through the CLI
    entry point, not only through the library functions."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mapping = root / "mapping-input.json"
        _write_mapping_input(mapping, [])
        result = subprocess.run(
            [sys.executable, str(TOOLS / "generate_screen_contracts.py"),
             "--mapping-input", str(mapping)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 2, result.stdout + result.stderr
        assert result.stderr.count("MISSING_SCREEN_BINDING") == 170
        assert {p.name for p in root.iterdir()} == {mapping.name}


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"ok  {name}")
    print(f"PASS — all {len(tests)} tests passed.")
