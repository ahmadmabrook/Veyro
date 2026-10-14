#!/usr/bin/env python3
"""
Unit tests for `tools/validate_route_registry_count.py` -- the release-stage
frontend route-registry V1 count-equality lint (ADR-014 D2.7; EIP Appendix
F). Synthetic fixtures only; the one real-tree test asserts the committed
zero-row registry is an explicit FAIL at release, never a PASS.

Run directly (`python3 tools/tests/test_validate_route_registry_count.py`)
or with pytest.
"""
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
from generate_screen_registry import DEFAULT_SOURCE, build_registry
from validate_route_registry_count import (
    DEFAULT_ROUTE_REGISTRY,
    APPROVED_SOURCE_SHA256,
    DEFAULT_SCREEN_REGISTRY,
    EXPECTED_V1_COUNT,
    check_counts,
    main,
)


def _write(tmp: Path, name: str, key: str, values: list[str]) -> Path:
    path = tmp / name
    path.write_text(json.dumps({"version": 1, key: values}), encoding="utf-8")
    return path


def _run(screens: list[str], routes: list[str], *extra: str) -> int:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        s = _write(tmp, "screens.json", "screens", screens)
        r = _write(tmp, "routes.json", "routes", routes)
        return main(["--screen-registry", str(s), "--route-registry", str(r), *extra])


# Canonical IDs re-derived from the frozen source by the canonical generator.
SCREENS_170 = build_registry(DEFAULT_SOURCE.read_text(encoding="utf-8"))["screens"]
ROUTES_170 = [f"/syn/{i}" for i in range(EXPECTED_V1_COUNT)]


def test_conforming_fixture_passes_at_release():
    assert _run(SCREENS_170, ROUTES_170) == 0


def test_count_mismatch_fails_at_release():
    assert _run(SCREENS_170, ROUTES_170[:-1]) == 1
    assert _run(SCREENS_170, ROUTES_170 + ["/syn/extra"]) == 1


def test_empty_route_registry_fails_at_release():
    assert _run(SCREENS_170, []) == 1
    assert [c for c, _ in check_counts(170, 0)] == ["ROUTE_REGISTRY_EMPTY"]


def test_vacuous_equal_counts_not_a_pass():
    assert _run([], []) == 1
    codes = [c for c, _ in check_counts(0, 0)]
    assert "CANONICAL_COUNT_MISMATCH" in codes and "ROUTE_REGISTRY_EMPTY" in codes


def test_canonical_count_not_170_fails_even_when_equal():
    assert _run(SCREENS_170[:-1], ROUTES_170[:-1]) == 1


def test_canonical_fixture_is_170():
    assert len(SCREENS_170) == EXPECTED_V1_COUNT


def test_fabricated_170_ids_with_170_routes_fail_at_release(capsys):
    fake = [f"FAKE-{i:03d}" for i in range(EXPECTED_V1_COUNT)]
    assert _run(fake, ROUTES_170) == 1
    assert "SCREEN_REGISTRY_SOURCE_MISMATCH" in capsys.readouterr().err


def test_one_substituted_id_fails_at_release(capsys):
    swapped = SCREENS_170[:-1] + ["ADM-ZZ-99"]
    assert _run(swapped, ROUTES_170) == 1
    assert "SCREEN_REGISTRY_SOURCE_MISMATCH" in capsys.readouterr().err


def test_reordered_ids_fail_at_release(capsys):
    assert _run(list(reversed(SCREENS_170)), ROUTES_170) == 1
    err = capsys.readouterr().err
    assert "SCREEN_REGISTRY_SOURCE_MISMATCH" in err and "different order" in err


def test_fabricated_ids_not_a_pass_at_pre_release(capsys):
    fake = [f"FAKE-{i:03d}" for i in range(EXPECTED_V1_COUNT)]
    assert _run(fake, ROUTES_170, "--stage", "pre-release") == 3
    out = capsys.readouterr().out
    assert "would-fail: SCREEN_REGISTRY_SOURCE_MISMATCH" in out and "PASS (" not in out


def _run_with_source(source: Path) -> int:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        s = _write(tmp, "screens.json", "screens", SCREENS_170)
        r = _write(tmp, "routes.json", "routes", ROUTES_170)
        return main(["--screen-registry", str(s), "--route-registry", str(r),
                     "--source", str(source)])


def test_missing_source_exits_2():
    with tempfile.TemporaryDirectory() as d:
        assert _run_with_source(Path(d) / "absent.js") == 2


def test_symlinked_source_exits_2():
    with tempfile.TemporaryDirectory() as d:
        link = Path(d) / "link.js"
        os.symlink(DEFAULT_SOURCE, link)
        assert _run_with_source(link) == 2


def test_unreadable_source_exits_2():
    with tempfile.TemporaryDirectory() as d:
        bad = Path(d) / "bad.js"
        bad.write_bytes(b"\xff\xfe\x00 not utf-8 \x80")
        assert _run_with_source(bad) == 2


def test_malformed_source_exits_2():
    with tempfile.TemporaryDirectory() as d:
        bad = Path(d) / "bad.js"
        bad.write_text("export const R = [\n  ['only','three','fields'],\n];\n", encoding="utf-8")
        assert _run_with_source(bad) == 2


def test_pinned_digest_matches_frozen_source():
    assert hashlib.sha256(DEFAULT_SOURCE.read_bytes()).hexdigest() == APPROVED_SOURCE_SHA256
    assert APPROVED_SOURCE_SHA256 == "0736902dfb285cb57e2f370c0918df0b8f2aeeefbd24b3e5198fa03ed185b8f5"


def test_mutated_source_is_rejected_by_digest_pin(capsys):
    """A source with a changed V1 ID is not the approved export: exit 2."""
    text = DEFAULT_SOURCE.read_text(encoding="utf-8")
    assert "'ADM-CC-01'" in text
    with tempfile.TemporaryDirectory() as d:
        mutated = Path(d) / "mutated.js"
        mutated.write_text(text.replace("'ADM-CC-01'", "'ADM-CC-98'", 1), encoding="utf-8")
        assert _run_with_source(mutated) == 2
    assert "SOURCE_DIGEST_MISMATCH" in capsys.readouterr().err


def test_aligned_fabricated_source_registry_and_routes_are_denied(capsys):
    """Fabricated shape-valid source + matching 170 IDs + 170 routes must not
    pass via `--source` (the registry==source check alone would accept it)."""
    fabricated = DEFAULT_SOURCE.read_text(encoding="utf-8").replace("'ADM-CC-", "'ADM-QQ-")
    fake_ids = build_registry(fabricated)["screens"]
    assert len(fake_ids) == EXPECTED_V1_COUNT and fake_ids != SCREENS_170
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        src = tmp / "fabricated.js"
        src.write_text(fabricated, encoding="utf-8")
        s = _write(tmp, "screens.json", "screens", fake_ids)
        r = _write(tmp, "routes.json", "routes", ROUTES_170)
        for stage in ("release", "pre-release"):
            assert main(["--screen-registry", str(s), "--route-registry", str(r),
                         "--source", str(src), "--stage", stage]) == 2
    captured = capsys.readouterr()
    assert "SOURCE_DIGEST_MISMATCH" in captured.err and "PASS" not in captured.out


def test_pre_release_reports_but_does_not_enforce(capsys):
    assert _run(SCREENS_170, [], "--stage", "pre-release") == 3
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "ROUTE_COUNT_STATE=NOT_ENFORCED reason=PRE_RELEASE_STAGE"
    assert "NOT ENFORCED" in out and "not a PASS" in out and "PASS (" not in out


def test_pre_release_never_exits_zero_even_when_counts_conform(capsys):
    assert _run(SCREENS_170, ROUTES_170, "--stage", "pre-release") == 3
    assert "ROUTE_COUNT_STATE=NOT_ENFORCED" in capsys.readouterr().out


def test_canonical_count_diagnostic_reports_source_count_not_registry_count(capsys):
    """A 169-row registry must not make the 'canonical' count read 169."""
    assert _run(SCREENS_170[:-1], ROUTES_170) == 1
    err = capsys.readouterr().err
    assert "SCREEN_REGISTRY_SOURCE_MISMATCH" in err
    assert "CANONICAL_COUNT_MISMATCH" not in err
    assert "canonical V1 screens=170, screen-registry rows=169" in err
    assert "canonical V1 Screen ID count (from the pinned source) is 169" in check_counts(169, 169)[0][1]


def test_malformed_inputs_exit_2():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        s = _write(tmp, "screens.json", "screens", SCREENS_170)
        dup = _write(tmp, "routes.json", "routes", ["/a", "/a"])
        assert main(["--screen-registry", str(s), "--route-registry", str(dup)]) == 2
        assert main(["--screen-registry", str(s), "--route-registry", str(tmp / "missing.json")]) == 2


def test_real_tree_zero_row_registry_fails_at_release(capsys):
    assert main(["--screen-registry", str(DEFAULT_SCREEN_REGISTRY),
                 "--route-registry", str(DEFAULT_ROUTE_REGISTRY)]) == 1
    err = capsys.readouterr().err
    assert "ROUTE_REGISTRY_EMPTY" in err and "ROUTE COUNT FAIL" in err


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
