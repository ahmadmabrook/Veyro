#!/usr/bin/env python3
"""
Tests for `tools/generate_screen_contract_manifest.py` (TSD §24.1 gate 5
manifest generator + identity check; ADR-014 D2).

* Real-input tests: the Appendix F module table parses; the committed
  `contracts/ui/screen-contracts.yaml` is byte-identical to regeneration; the
  real identity check reports FAIL (`OWNER_UNRESOLVED` for all 170 screens —
  the registry carries no TSD `owner_domain`) and never PASS/NOT_APPLICABLE.
* Synthetic fixtures (built here, never real data): a conforming 170-row
  registry source + Appendix-F-shaped module table whose rows carry an
  explicit TSD domain code, which resolves to exactly one module -> PASS; and
  deliberate violations -> FAIL/ERROR.

Run with pytest.
"""
import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
import generate_screen_contract_manifest as g

# --- synthetic fixture builders ----------------------------------------------------


def _row(screen_id, module="Fixture", phase="V1", status="DONE", note="x"):
    return f"['{screen_id}','{module}','name','{phase}','{status}','All','N/A','{note}'],"


def make_source(*, domain_for=None, extra_rows=(), drop_one_admin=False):
    """170 V1 UI rows (85/16/19/35/15) + 8 SYS rows. `domain_for` maps a
    surface-prefix to the TSD domain code placed in the row's note field."""
    domain_for = domain_for or {"ADM": "PPL-01", "FD": "PPL-01", "POS": "PPL-01",
                                "CCH": "PPL-01", "MBR": "PPL-01", "CON": "PLT-01"}
    ids = ([f"ADM-AA-{i:02d}" for i in range(1, 86)] + [f"FD-{i:02d}" for i in range(1, 10)]
           + [f"POS-{i:02d}" for i in range(1, 8)] + [f"CCH-{i:02d}" for i in range(1, 20)]
           + [f"MBR-{i:02d}" for i in range(1, 36)] + [f"CON-{i:02d}" for i in range(1, 16)])
    if drop_one_admin:
        ids.remove("ADM-AA-85")
    lines = [_row(i, note=domain_for.get(i.split("-")[0], "x")) for i in ids]
    lines += [_row(f"SYS-{i:02d}", module="System", status="NO-UI") for i in range(1, 9)]
    lines += list(extra_rows)
    return "// fixture\nexport const R = [\n" + "\n".join(lines) + "\n];\n"


def make_eip(*, duplicate_ppl01=False, bad_surface=None):
    """An Appendix-F-shaped fixed-width module table."""
    hdr = "  **Module**   **Wave**     **TSD         **UI /        **Canonical      **Ready-state"
    cols = [hdr.index(t) for t in ("**Module**", "**Wave**", "**TSD", "**UI /", "**Canonical", "**Ready-state")]
    sep = "  ------------ ------------ ------------- ------------- ---------------- -------------------------"

    def line(mod, wave, dom, surf):
        out = " " * 200
        for pos, text in zip(cols[:4], (mod, wave, dom, surf)):
            out = out[:pos] + text + out[pos + len(text):]
        return out.rstrip()

    mods = [("MOD-000", "Foundation", "Program gate", "Non-UI / none"),
            ("MOD-001", "Foundation", "GOV-01", "Internal SaaS"),
            ("MOD-004", "Foundation", "PLT-01", "Internal SaaS"),
            ("MOD-014", "Foundation", "PPL-01", bad_surface or "Admin Web,")]
    body = [sep, hdr, sep]
    for mod, wave, dom, surf in mods:
        body.append(line(mod, wave, dom, surf))
        if mod == "MOD-014" and not bad_surface:
            for extra in ("Coach App,", "Member App,", "Front Desk"):
                body.append(line("", "", "", extra))
        if mod in ("MOD-001", "MOD-004"):
            body.append(line("", "", "", "Console," if mod == "MOD-004" else "Console"))
            if mod == "MOD-004":
                body.append(line("", "", "", "Admin Web"))
        body.append("")
    if duplicate_ppl01:
        body.append(line("MOD-034", "V1 GA", "PPL-01", "Admin Web,"))
        for extra in ("Coach App,", "Member App,", "Front Desk"):
            body.append(line("", "", "", extra))
        body.append("")
    body.append(sep)
    return "# Appendix F. Canonical Screen-to-Module Mapping\n\n" + "\n".join(body) + "\n"


def ids_of(source):
    return [r.screen_id for r in g.build_canonical_rows(source)]


@pytest.fixture()
def conforming():
    source, eip = make_source(), make_eip()
    registry = ids_of(source)
    text = g.generate_manifest_text(source, registry, eip)
    return source, registry, eip, text


def codes(report):
    return {v.code for v in report.violations}


def mutate(text, fn):
    m = json.loads(text)
    fn(m)
    return g.render_manifest(m)


# --- real inputs --------------------------------------------------------------------


def test_real_module_table_parses():
    modules = g.parse_module_table(g.DEFAULT_EIP.read_text(encoding="utf-8"))
    assert len(modules) == 75 and list(modules)[:2] == ["MOD-000", "MOD-001"]
    assert modules["MOD-001"].domains == ("GOV-01",)
    assert modules["MOD-001"].surfaces == ("Internal SaaS Console",)
    assert modules["MOD-000"].domains == () and modules["MOD-000"].surfaces == ()
    assert modules["MOD-017"].domains == ("COM-01", "COM-03")
    # post-V1 portals are dropped from the surface set, never invented as screens
    assert modules["MOD-007"].surfaces == ("Admin",)


def test_real_source_yields_170_with_expected_split():
    rows = g.build_canonical_rows(g.DEFAULT_SOURCE.read_text(encoding="utf-8"))
    g.verify_counts(rows)
    assert len(rows) == 170
    assert g.surface_counts([r.surface for r in rows]) == g.EXPECTED_BY_SURFACE
    assert [r.screen_id for r in rows] == g.load_registry_ids(g.DEFAULT_REGISTRY)
    assert not any(r.screen_id.startswith("SYS-") for r in rows)


def test_real_registry_rows_carry_no_tsd_owner_domain():
    """The premise behind the real FAIL: no source field is a TSD domain code."""
    modules = g.parse_module_table(g.DEFAULT_EIP.read_text(encoding="utf-8"))
    rows = g.build_canonical_rows(g.DEFAULT_SOURCE.read_text(encoding="utf-8"))
    assert all(g.source_owner_domain(r, modules) is None for r in rows)


def test_committed_manifest_matches_regeneration_and_check_fails_honestly():
    source = g.DEFAULT_SOURCE.read_text(encoding="utf-8")
    eip = g.DEFAULT_EIP.read_text(encoding="utf-8")
    registry = g.load_registry_ids(g.DEFAULT_REGISTRY)
    committed = g.DEFAULT_MANIFEST.read_text(encoding="utf-8")
    assert committed == g.generate_manifest_text(source, registry, eip)
    report = g.check_manifest(committed, source, registry, eip)
    assert report.state == g.FAIL
    assert codes(report) == {"OWNER_UNRESOLVED"}
    assert len(report.violations[0].subjects) == 170
    manifest = json.loads(committed)
    assert manifest["module_screens"]["MOD-001"] == []
    assert all(r["owning_module"] is None and r["binding_status"] == "UNBOUND" for r in manifest["screens"])
    assert manifest["counts"]["by_surface"] == g.EXPECTED_BY_SURFACE


def test_generation_is_deterministic():
    source = g.DEFAULT_SOURCE.read_text(encoding="utf-8")
    eip = g.DEFAULT_EIP.read_text(encoding="utf-8")
    registry = g.load_registry_ids(g.DEFAULT_REGISTRY)
    assert g.generate_manifest_text(source, registry, eip) == g.generate_manifest_text(source, registry, eip)


# --- conforming fixture -------------------------------------------------------------


def test_conforming_fixture_passes(conforming):
    source, registry, eip, text = conforming
    manifest = json.loads(text)
    assert len(manifest["screens"]) == 170
    assert manifest["module_screens"]["MOD-001"] == []
    assert len(manifest["module_screens"]["MOD-014"]) == 155
    assert len(manifest["module_screens"]["MOD-004"]) == 15
    assert manifest["screens"][0]["owning_module"] == "MOD-014"
    assert manifest["screens"][0]["wave"] == "Foundation"
    report = g.check_manifest(text, source, registry, eip)
    assert report.state == g.PASS and not report.violations
    assert g.NOT_APPLICABLE not in g.EXIT_CODE and g.EXIT_CODE[report.state] == 0


# --- deliberate violations ----------------------------------------------------------


def test_count_mismatch_fails(conforming):
    source, registry, eip, text = conforming

    def drop(m):
        m["screens"].pop()
    report = g.check_manifest(mutate(text, drop), source, registry, eip)
    assert report.state == g.FAIL and {"COUNT_MISMATCH", "MISSING_SCREEN_ID"} <= codes(report)


def test_source_count_deviation_fails_check_but_errors_generation():
    source = make_source(drop_one_admin=True)
    registry = ids_of(source)
    eip = make_eip()
    with pytest.raises(g.GenerationError):
        g.generate_manifest_text(source, registry, eip)
    text = g.generate_manifest_text(source, registry, eip, enforce=False)
    report = g.check_manifest(text, source, registry, eip)
    assert report.state == g.FAIL and {"SOURCE_COUNT_MISMATCH", "COUNT_MISMATCH"} <= codes(report)


def test_invented_screen_id_fails(conforming):
    source, registry, eip, text = conforming

    def invent(m):
        m["screens"][0]["screen_id"] = "ADM-ZZ-99"
    report = g.check_manifest(mutate(text, invent), source, registry, eip)
    assert report.state == g.FAIL
    assert "INVENTED_SCREEN_ID" in codes(report)
    assert next(v for v in report.violations if v.code == "INVENTED_SCREEN_ID").subjects == ["ADM-ZZ-99"]


def test_unknown_surface_label_is_error_in_manifest(conforming):
    source, registry, eip, text = conforming

    def relabel(m):
        m["screens"][0]["surface"] = "Veyro Admin"  # registry label, not the EIP vocabulary
    report = g.check_manifest(mutate(text, relabel), source, registry, eip)
    assert report.state == g.ERROR and g.EXIT_CODE[report.state] == 2


def test_unknown_surface_label_is_error_in_source_mapping():
    with pytest.raises(g.GenerationError, match="unknown surface label"):
        g.map_surface_label("Veyro Partner")
    with pytest.raises(g.GenerationError, match="unknown surface label"):
        g.build_canonical_rows(make_source(), label_of=lambda i: "Veyro Partner")
    # unknown ID prefix falls to the backend label without SYS- -> ERROR, not a silent exclusion
    with pytest.raises(g.GenerationError):
        g.build_canonical_rows(make_source(extra_rows=[_row("XYZ-01")]))


def test_unresolvable_owner_fails_listing_ids():
    source = make_source(domain_for={"ADM": "PPL-01", "FD": "PPL-01", "POS": "PPL-01",
                                     "CCH": "PPL-01", "MBR": "PPL-01"})  # CON rows carry no domain
    registry, eip = ids_of(source), make_eip()
    text = g.generate_manifest_text(source, registry, eip)
    report = g.check_manifest(text, source, registry, eip)
    assert report.state == g.FAIL
    unresolved = next(v for v in report.violations if v.code == "OWNER_UNRESOLVED")
    assert unresolved.subjects == [f"CON-{i:02d}" for i in range(1, 16)]


def test_ambiguous_owner_fails(conforming):
    source, registry, _, text = conforming
    ambiguous_eip = make_eip(duplicate_ppl01=True)
    report = g.check_manifest(text, source, registry, ambiguous_eip)
    assert report.state == g.FAIL and "OWNER_AMBIGUOUS" in codes(report)
    # generation itself records the ambiguity as UNRESOLVED instead of picking a module
    regenerated = json.loads(g.generate_manifest_text(source, registry, ambiguous_eip))
    first = regenerated["screens"][0]
    assert first["owning_module"] is None and first["owner_resolution"]["reason"] == "OWNER_MATCHES_2_MODULES"


def test_owner_not_matching_rule_fails(conforming):
    source, registry, eip, text = conforming

    def reassign(m):
        m["screens"][0]["owning_module"] = "MOD-004"  # Admin screen, PPL-01 domain: not MOD-004's
    report = g.check_manifest(mutate(text, reassign), source, registry, eip)
    assert report.state == g.FAIL and "OWNER_MISMATCH" in codes(report)


def test_unbound_row_with_implemented_owner_fails(conforming):
    source, registry, eip, text = conforming
    report = g.check_manifest(text, source, registry, eip, frozenset({"MOD-014"}))
    assert report.state == g.FAIL
    flagged = next(v for v in report.violations if v.code == "UNBOUND_ROW_OWNER_IMPLEMENTED")
    assert len(flagged.subjects) == 155
    # an unrelated implemented module does not trip it
    assert g.check_manifest(text, source, registry, eip, frozenset({"MOD-001"})).state == g.PASS


def test_drift_from_regeneration_fails(conforming):
    source, registry, eip, text = conforming
    report = g.check_manifest(text.replace('"Fixture"', '"Edited"', 1), source, registry, eip)
    assert report.state == g.FAIL and codes(report) == {"MANIFEST_DRIFT"}
    assert g.check_manifest(text + "\n", source, registry, eip).state == g.FAIL


def test_mod_001_entry_must_be_present_and_empty(conforming):
    source, registry, eip, text = conforming
    report = g.check_manifest(mutate(text, lambda m: m["module_screens"].pop("MOD-001")),
                              source, registry, eip)
    assert report.state == g.FAIL and "MOD_001_ENTRY_INVALID" in codes(report)
    report = g.check_manifest(mutate(text, lambda m: m["module_screens"].__setitem__("MOD-001", ["CON-01"])),
                              source, registry, eip)
    assert report.state == g.FAIL and {"MOD_001_ENTRY_INVALID", "MODULE_INDEX_MISMATCH"} <= codes(report)


def test_invented_binding_value_fails(conforming):
    source, registry, eip, text = conforming
    report = g.check_manifest(mutate(text, lambda m: m["screens"][3].__setitem__("route", "/members")),
                              source, registry, eip)
    assert report.state == g.FAIL and "BINDING_FIELD_INVALID" in codes(report)
    report = g.check_manifest(mutate(text, lambda m: m["screens"][3].__setitem__("commands", "")),
                              source, registry, eip)
    assert report.state == g.FAIL and "BINDING_FIELD_INVALID" in codes(report)


def test_registry_json_mismatch_fails(conforming):
    source, registry, eip, text = conforming
    report = g.check_manifest(text, source, registry[:-1] + ["ADM-ZZ-99"], eip)
    assert report.state == g.FAIL and "REGISTRY_JSON_MISMATCH" in codes(report)


def test_unparseable_or_missing_inputs_are_error(conforming):
    source, registry, eip, text = conforming
    assert g.check_manifest("not json", source, registry, eip).state == g.ERROR
    assert g.check_manifest(text, source, registry, "no table here").state == g.ERROR
    assert g.check_manifest(text, "no rows", registry, eip).state == g.ERROR
    with pytest.raises(g.GenerationError, match="unknown surface name"):
        g.parse_module_table(make_eip(bad_surface="Holo Deck"))


# --- CLI ----------------------------------------------------------------------------


def _write_inputs(tmp_path, source, eip):
    (tmp_path / "src.js").write_text(source, encoding="utf-8")
    (tmp_path / "eip.md").write_text(eip, encoding="utf-8")
    (tmp_path / "reg.json").write_text(json.dumps({"version": 1, "screens": ids_of(source)}), encoding="utf-8")
    return ["--source", str(tmp_path / "src.js"), "--eip", str(tmp_path / "eip.md"),
            "--registry", str(tmp_path / "reg.json"), "--manifest", str(tmp_path / "m.yaml")]


def test_cli_generate_then_check_exit_codes(tmp_path, capsys):
    args = _write_inputs(tmp_path, make_source(), make_eip())
    assert g.main(["generate", *args]) == 0
    assert g.main(["check", *args]) == 0
    out = capsys.readouterr().out
    assert "gate 5 screen-contract identity: PASS" in out and "NOT_APPLICABLE is never a valid result" in out
    assert g.main(["check", *args, "--implemented-modules", "MOD-014"]) == 1
    (tmp_path / "m.yaml").write_text("{", encoding="utf-8")
    assert g.main(["check", *args]) == 2
    (tmp_path / "m.yaml").unlink()
    assert g.main(["check", *args]) == 2


def test_cli_real_check_exits_1_with_fail_report(capsys):
    assert g.main(["check"]) == 1
    out = capsys.readouterr().out
    assert "state=FAIL" in out and "OWNER_UNRESOLVED [170]" in out and "ADM-CC-01" in out and "CON-17" in out
