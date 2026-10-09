#!/usr/bin/env python3
"""
Unit tests for `tools/generate_screen_registry.py` — the bounded canonical
UX input adapter for TSD §24.1 gate 5 (MOD-001, GOV-01-R04,
`R04-GATE5-CANONICAL-UX-INPUT-ADAPTER`).

Positive controls: the real frozen source parses to exactly 170 V1 UI
Screen IDs split ADM 85 / FD+POS 16 / CCH 19 / MBR 35 / CON 15, excluding
the eight backend-only `SYS-*` V1 rows; the result is accepted by
the committed `validate_screen_source_inputs.load_screen_registry` unchanged.

Negative controls: a malformed source-row shape, a wrong total/surface
split, a duplicate Screen ID, and a malformed real-shaped Screen ID each
fail closed with `SourceFormatError` — never a silently-dropped row or a
materialized-but-wrong registry.

Run directly (`python3 tools/tests/test_generate_screen_registry.py`) or
with pytest.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
from generate_screen_registry import (
    DEFAULT_SOURCE,
    EXPECTED_BY_SURFACE,
    EXPECTED_TOTAL,
    SourceFormatError,
    build_registry,
    parse_source_rows,
    select_v1_ui_ids,
    verify_projection,
)
from validate_screen_source_inputs import SourceInputError, load_screen_registry

_HEADER = "// header comment\nexport const R = [\n"
_FOOTER = "\n];\n"


def _row(id_, phase="V1", module="M", name="N", status="GAP", roles="-", ar="N/A", note="n"):
    return f"['{id_}','{module}','{name}','{phase}','{status}','{roles}','{ar}','{note}'],"


def _source(rows: list[str]) -> str:
    return _HEADER + "\n".join(rows) + _FOOTER


def test_real_source_yields_exactly_170_with_the_documented_surface_split():
    """Positive control: the real frozen source, parsed for real."""
    text = DEFAULT_SOURCE.read_text(encoding="utf-8")
    registry = build_registry(text)
    assert registry["version"] == 1
    screens = registry["screens"]
    assert len(screens) == EXPECTED_TOTAL == 170
    assert len(set(screens)) == len(screens), "generator must not emit duplicates"
    counts = {"ADM": 0, "FD+POS": 0, "CCH": 0, "MBR": 0, "CON": 0}
    for screen_id in screens:
        prefix = screen_id.split("-", 1)[0]
        counts["FD+POS" if prefix in ("FD", "POS") else prefix] += 1
    assert counts == EXPECTED_BY_SURFACE == {"ADM": 85, "FD+POS": 16, "CCH": 19, "MBR": 35, "CON": 15}
    assert not any(s.startswith("SYS-") for s in screens)


def test_real_source_excludes_exactly_eight_backend_only_sys_rows():
    text = DEFAULT_SOURCE.read_text(encoding="utf-8")
    rows = parse_source_rows(text)
    sys_v1 = [r for r in rows if r[0].startswith("SYS-") and r[3] == "V1"]
    assert len(sys_v1) == 8, sys_v1


def test_real_generated_registry_is_accepted_by_the_gate_parser():
    """The real-ID gate input control: the generator's own serialized output,
    loaded by the committed `validate_screen_source_inputs.load_screen_registry`
    unmodified."""
    text = DEFAULT_SOURCE.read_text(encoding="utf-8")
    registry = build_registry(text)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "screen-registry.json"
        path.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        screens = load_screen_registry(path)
    assert screens == registry["screens"]
    assert "ADM-CC-01" in screens
    assert "FD-01" in screens
    assert "CON-01" in screens


def test_gate_loader_rejects_duplicate_and_malformed_registries():
    """Strict negative controls against the same committed loader."""
    bad_payloads = [
        {"version": 1, "screens": ["FD-01", "FD-01"]},  # duplicate
        {"version": 2, "screens": ["FD-01"]},  # wrong version
        {"version": 1, "screens": ["FD-01"], "extra": 1},  # extra key
        {"version": 1, "screens": ["FD-01", ""]},  # empty id
        {"version": 1, "screens": "FD-01"},  # not a list
    ]
    with tempfile.TemporaryDirectory() as tmp:
        for i, payload in enumerate(bad_payloads):
            path = Path(tmp) / f"bad-{i}.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            try:
                load_screen_registry(path)
            except SourceInputError:
                pass
            else:
                raise AssertionError(f"loader accepted malformed registry: {payload!r}")


def test_committed_registry_artifact_matches_live_generation():
    """The checked-in `contracts/ui/screen-registry.json` must not drift
    from what the generator currently produces against the frozen source."""
    committed_path = TOOLS.parent / "contracts" / "ui" / "screen-registry.json"
    committed = json.loads(committed_path.read_text(encoding="utf-8"))
    text = DEFAULT_SOURCE.read_text(encoding="utf-8")
    assert committed == build_registry(text)
    expected_bytes = (json.dumps(build_registry(text), indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    assert committed_path.read_bytes() == expected_bytes


def _minimal_valid_rows(n_adm=85, n_fdpos=16, n_cch=19, n_mbr=35, n_con=15, n_sys=8):
    rows = []
    for i in range(1, n_adm + 1):
        rows.append(_row(f"ADM-CC-{i:02d}"))
    for i in range(1, n_fdpos + 1):
        rows.append(_row(f"FD-{i:02d}" if i <= n_fdpos // 2 else f"POS-{i:02d}"))
    for i in range(1, n_cch + 1):
        rows.append(_row(f"CCH-{i:02d}"))
    for i in range(1, n_mbr + 1):
        rows.append(_row(f"MBR-{i:02d}"))
    for i in range(1, n_con + 1):
        rows.append(_row(f"CON-{i:02d}"))
    for i in range(1, n_sys + 1):
        rows.append(_row(f"SYS-{i:02d}"))
    return rows


def test_well_formed_synthetic_source_with_correct_split_passes():
    registry = build_registry(_source(_minimal_valid_rows()))
    assert len(registry["screens"]) == 170


def test_v1_5_v2_ent_rows_are_excluded_from_the_projection():
    rows = _minimal_valid_rows() + [_row("ADM-CC-99", phase="V1.5"), _row("MBR-99", phase="V2")]
    registry = build_registry(_source(rows))
    assert "ADM-CC-99" not in registry["screens"]
    assert "MBR-99" not in registry["screens"]
    assert len(registry["screens"]) == 170


def test_source_missing_start_marker_is_source_format_error():
    try:
        parse_source_rows("no marker here\n];\n")
    except SourceFormatError as exc:
        assert "export const R" in str(exc)
    else:
        raise AssertionError("accepted a source with no R array start marker")


def test_source_missing_end_marker_is_source_format_error():
    try:
        parse_source_rows(_HEADER + _row("ADM-CC-01"))
    except SourceFormatError as exc:
        assert "];" in str(exc)
    else:
        raise AssertionError("accepted a source with no closing marker")


def test_malformed_row_shape_is_source_format_error_citing_line():
    bad_rows = [
        "['ADM-CC-01','M','N','V1','GAP','-','N/A'],",  # only 7 fields
        '["ADM-CC-01","M","N","V1","GAP","-","N/A","n"],',  # double-quoted, not single
        "['ADM-CC-01','M','N','V1','GAP','-','N/A','n']",  # missing trailing comma is fine, but malformed otherwise below
        "ADM-CC-01,M,N,V1,GAP,-,N/A,n",  # no brackets/quotes at all
    ]
    for bad in bad_rows[:2] + bad_rows[3:]:
        try:
            parse_source_rows(_source([bad]))
        except SourceFormatError as exc:
            assert "row" in str(exc) or "does not match" in str(exc)
        else:
            raise AssertionError(f"accepted malformed row: {bad!r}")


def test_unknown_prefix_is_source_format_error_with_id_and_reason():
    rows = _minimal_valid_rows() + [_row("XYZ-01")]
    try:
        select_v1_ui_ids(parse_source_rows(_source(rows)))
    except SourceFormatError as exc:
        assert "XYZ-01" in str(exc)
        assert "unknown prefix" in str(exc)
    else:
        raise AssertionError("accepted an unrecognised Screen ID prefix")


def test_malformed_real_shaped_id_is_source_format_error():
    """A real-surface prefix with the wrong internal shape (lowercase,
    wrong digit width, missing hyphen) must still deny, not pass through."""
    for bad_id in ("adm-cc-01", "ADM-CC-001", "ADMCC-01", "FD-1", "CON-017x"):
        rows = _minimal_valid_rows()
        rows[0] = _row(bad_id)
        try:
            select_v1_ui_ids(parse_source_rows(_source(rows)))
        except SourceFormatError as exc:
            assert bad_id in str(exc) or "shape" in str(exc)
        else:
            raise AssertionError(f"accepted malformed real-shaped id: {bad_id!r}")


def test_duplicate_screen_id_is_source_format_error():
    rows = _minimal_valid_rows()
    rows.append(_row(rows[0].split("'")[1]))  # repeat the first row's id verbatim
    try:
        select_v1_ui_ids(parse_source_rows(_source(rows)))
    except SourceFormatError as exc:
        assert "duplicate" in str(exc).lower()
    else:
        raise AssertionError("accepted a duplicate Screen ID")


def test_wrong_backend_only_count_is_source_format_error():
    rows = _minimal_valid_rows(n_sys=7)  # one short of the documented 8
    try:
        select_v1_ui_ids(parse_source_rows(_source(rows)))
    except SourceFormatError as exc:
        assert "backend-only" in str(exc)
    else:
        raise AssertionError("accepted a source with the wrong SYS-* backend-only count")


def test_wrong_total_count_is_source_format_error():
    rows = _minimal_valid_rows(n_con=14)  # one short of the documented 170 total
    try:
        build_registry(_source(rows))
    except SourceFormatError as exc:
        assert "170" in str(exc) or "expected" in str(exc)
    else:
        raise AssertionError("accepted a projection with the wrong total count")


def test_wrong_surface_split_with_correct_total_is_source_format_error():
    """Same total (170) but the wrong per-surface distribution — the count
    check alone must not be enough to pass."""
    rows = _minimal_valid_rows(n_con=14) + [_row("MBR-36")]  # shifts one CON into MBR
    registry_ids = select_v1_ui_ids(parse_source_rows(_source(rows)))
    assert len(registry_ids) == 170
    try:
        verify_projection(registry_ids)
    except SourceFormatError as exc:
        assert "split" in str(exc)
    else:
        raise AssertionError("accepted the right total with the wrong five-surface split")


def test_cli_writes_registry_file_and_exits_zero():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "screen-registry.json"
        result = subprocess.run(
            [sys.executable, str(TOOLS / "generate_screen_registry.py"), "--output", str(out)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        written = json.loads(out.read_text())
        assert written["version"] == 1
        assert len(written["screens"]) == 170


def test_cli_fails_closed_on_malformed_source():
    with tempfile.TemporaryDirectory() as tmp:
        bad_source = Path(tmp) / "bad-registry-data.js"
        bad_source.write_text(_HEADER + "not a valid row\n" + _FOOTER)
        out = Path(tmp) / "screen-registry.json"
        result = subprocess.run(
            [sys.executable, str(TOOLS / "generate_screen_registry.py"),
             "--source", str(bad_source), "--output", str(out)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 2, result.stdout + result.stderr
        assert not out.exists(), "a failed generation must not write a partial/wrong output file"


def test_cli_fails_closed_on_missing_source():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "screen-registry.json"
        result = subprocess.run(
            [sys.executable, str(TOOLS / "generate_screen_registry.py"),
             "--source", str(Path(tmp) / "nope.js"), "--output", str(out)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 2, result.stdout + result.stderr
        assert not out.exists()


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"ok  {name}")
    print(f"PASS — all {len(tests)} tests passed.")
