"""Regression tests for evidence_integrity_check.py's path-resolution fixes
(2026-09-30 recovery: rules/ subdirectory resolution + RULE-<NNN> placeholder
classification). Run: backend/.venv/bin/python -m pytest <this file> -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import evidence_integrity_check as eic


def _check(text: str):
    """Write text to a throwaway file under ROOT, run check_file_refs, clean up."""
    tmp = eic.ROOT / "knowledge" / "_eic_test_scratch.md"
    tmp.write_text(text, encoding="utf-8")
    findings, expected_absent = [], []
    try:
        eic.check_file_refs(str(tmp.relative_to(eic.ROOT)), findings, expected_absent)
    finally:
        tmp.unlink()
    return findings, expected_absent


def test_positive_rule_file_resolves_via_subdirectory():
    # Real file lives at .claude/rules/global/knowledge-vault-durability.md.
    # A bare pre-reorg reference must resolve, not be flagged broken.
    findings, expected_absent = _check("See `.claude/rules/knowledge-vault-durability.md`.")
    assert findings == [], f"expected no broken-reference finding, got {findings}"
    assert expected_absent == []


def test_negative_unknown_rule_file_still_flagged():
    findings, _ = _check("See `.claude/rules/does-not-exist-anywhere.md`.")
    assert len(findings) == 1
    assert "does-not-exist-anywhere.md" in findings[0]
    assert "BROKEN REFERENCE" in findings[0]


def test_negative_ambiguous_basename_not_silently_resolved():
    # Two files share a basename under different subdirs -> must NOT
    # silently pick one; must still report broken (fail closed).
    a = eic.ROOT / ".claude/rules/global/_eic_dup_test.md"
    b = eic.ROOT / ".claude/rules/admin/_eic_dup_test.md"
    a.write_text("x", encoding="utf-8")
    b.write_text("x", encoding="utf-8")
    try:
        findings, _ = _check("See `.claude/rules/_eic_dup_test.md`.")
    finally:
        a.unlink()
        b.unlink()
    assert len(findings) == 1, f"ambiguous basename must fail closed, got {findings}"


def test_rule_nnn_placeholder_classified_expected_absent_not_broken():
    findings, expected_absent = _check(
        "See `knowledge/05-QA/capability-evidence/RULE-<NNN>/POSITIVE_NEGATIVE_EVAL_2026-09-25.md`."
    )
    assert findings == [], f"placeholder must not be a broken-reference finding, got {findings}"
    assert len(expected_absent) == 1
    assert "RULE-<NNN>" in expected_absent[0]


def test_discover_module_evidence_roots_includes_mod001():
    roots = eic.discover_module_evidence_roots()
    assert "knowledge/03-Modules/MOD-000/evidence" in roots
    assert "knowledge/03-Modules/MOD-001/evidence" in roots


def test_mod001_only_newer_evidence_is_detected_not_false_clean(monkeypatch):
    # A real file under MOD-001/evidence, faked with a far-future commit
    # date; MOD-000/evidence contributes nothing in this fake. Proves the
    # staleness scan actually looks at MOD-001, not just MOD-000.
    mod001_file = "knowledge/03-Modules/MOD-001/evidence/bugs/BUG-028-docx-read-capability-gap.md"
    assert (eic.ROOT / mod001_file).is_file(), "fixture file must be real"

    def fake_latest_commit_dates_under(rel_dir):
        if "MOD-001" in rel_dir:
            return {mod001_file: "2099-01-01"}
        return {}

    monkeypatch.setattr(eic, "latest_commit_dates_under", fake_latest_commit_dates_under)

    new_scope_date = eic.latest_date_across_roots(eic.discover_module_evidence_roots())
    assert new_scope_date == "2099-01-01", (
        f"scanning all MOD-*/evidence must surface the MOD-001-only future date, got {new_scope_date}"
    )

    # Old (pre-fix) behavior: only MOD-000/evidence was scanned. Same fake,
    # narrower scope -> the MOD-001 evidence is invisible -> false-clean.
    old_scope_date = eic.latest_date_across_roots(["knowledge/03-Modules/MOD-000/evidence"])
    assert old_scope_date == "0000-00-00", (
        "regression: MOD-000-only scope should NOT see MOD-001's newer evidence "
        f"(this is the false-clean bug being fixed), got {old_scope_date}"
    )


if __name__ == "__main__":
    # One test needs the pytest `monkeypatch` fixture -> delegate to pytest
    # rather than maintaining a second bespoke runner.
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
