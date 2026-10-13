"""Regression tests for evidence_integrity_check.py's path-resolution fixes
(2026-09-30 recovery: rules/ subdirectory resolution + RULE-<NNN> placeholder
classification). Run only via a governed invocation (see the __main__ block at
the bottom of this file); direct execution is refused.
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
    assert "knowledge/03-Modules/MOD-001/evidence" not in roots
    assert "knowledge/03-Modules/MOD-001/MOD-001.md" in roots


def test_mod001_only_newer_evidence_is_detected_not_false_clean(monkeypatch):
    # The active MOD-001.md is the sole operational Markdown; a newer commit
    # to it must be visible even though the module evidence tree is absent.
    mod001_file = "knowledge/03-Modules/MOD-001/MOD-001.md"
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


# OWN-008/ADR-009: deleted MOD-001 paths remain historical citations only.
import tempfile
import os
import threading
import unittest
from unittest import mock


class HistoricalGitBindingTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        (self.root / "knowledge").mkdir()
        patcher = mock.patch.object(eic, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _cite(self, rel):
        (self.root / "knowledge/citing.md").write_text(f"See `{rel}`.", encoding="utf-8")
        findings, absent = [], []
        eic.check_file_refs("knowledge/citing.md", findings, absent)
        return findings, absent

    def test_exact_pinned_historical_path_is_not_current_proof(self):
        rel = "knowledge/03-Modules/MOD-001/STATUS.md"
        self.assertIn(rel, eic.HISTORICAL_MOD001_BLOBS)
        findings, absent = self._cite(rel)
        self.assertEqual(findings, [])
        self.assertEqual(len(absent), 1)
        self.assertIn("no current gate authority", absent[0])

    def test_unknown_deleted_path_fails_closed(self):
        findings, absent = self._cite("knowledge/03-Modules/MOD-001/UNKNOWN-EVIDENCE.md")
        self.assertEqual(len(findings), 1)
        self.assertIn("BROKEN REFERENCE", findings[0])
        self.assertEqual(absent, [])

    def test_existing_path_is_not_misclassified_historical(self):
        rel = "knowledge/03-Modules/MOD-001/STATUS.md"
        target = self.root / rel
        target.parent.mkdir(parents=True)
        target.write_text("current", encoding="utf-8")
        findings, absent = self._cite(rel)
        self.assertEqual((findings, absent), ([], []))


class AbbreviatedHistoricalRefTest(unittest.TestCase):
    """Exact-three abbreviated `knowledge/.../` citations in the immutable
    SCN070-ROUND5-ROOTCAUSE-IMPLEMENTATION file (GOV-01-R01)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        (self.root / eic.ABBREV_TARGET_DIR).mkdir(parents=True)
        patcher = mock.patch.object(eic, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.names = sorted(rel.rsplit("/", 1)[-1] for _, rel in eic.ABBREVIATED_HISTORICAL_REFS)

    def _target(self, name):
        return self.root / eic.ABBREV_TARGET_DIR / name

    def _write_all_targets(self):
        for name in self.names:
            self._target(name).write_text("x", encoding="utf-8")

    def _cite(self, rels, source=None):
        source = source or eic.ABBREV_SOURCE
        src = self.root / source
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("".join(f"See `{r}`.\n" for r in rels), encoding="utf-8")
        findings, absent = [], []
        eic.check_file_refs(source, findings, absent)
        return findings, absent

    def test_mapping_is_exactly_the_three_declared_files(self):
        self.assertEqual(
            self.names,
            ["SCN070-R5-1-ASYMMETRIC-INJECTION-DRILL-2026-10-05.txt",
             "SCN070-ROUND3-REMEDIATION-2026-10-04.md",
             "scn070_ordering_lint_mutation_killcheck.py"],
        )
        self.assertEqual(len({s for s, _ in eic.ABBREVIATED_HISTORICAL_REFS}), 1)

    def test_positive_all_three_resolve_to_regular_targets(self):
        self._write_all_targets()
        findings, absent = self._cite([f"knowledge/.../{n}" for n in self.names])
        self.assertEqual(findings, [])
        self.assertEqual(len(absent), 3)

    def test_negative_unknown_abbreviated_name_fails(self):
        self._write_all_targets()
        (self.root / eic.ABBREV_TARGET_DIR / "other.md").write_text("x", encoding="utf-8")
        findings, absent = self._cite(["knowledge/.../other.md"])
        self.assertEqual(len(findings), 1)
        self.assertIn("BROKEN REFERENCE", findings[0])
        self.assertEqual(absent, [])

    def test_negative_known_name_cited_from_other_file_fails(self):
        self._write_all_targets()
        findings, absent = self._cite([f"knowledge/.../{self.names[0]}"], source="knowledge/other_citing.md")
        self.assertEqual(len(findings), 1)
        self.assertIn("BROKEN REFERENCE", findings[0])
        self.assertEqual(absent, [])

    def test_negative_missing_target_fails(self):
        self._write_all_targets()
        self._target(self.names[0]).unlink()
        findings, absent = self._cite([f"knowledge/.../{self.names[0]}"])
        self.assertEqual(len(findings), 1)
        self.assertIn("BROKEN HISTORICAL REFERENCE", findings[0])
        self.assertIn("missing", findings[0])
        self.assertEqual(absent, [])

    def test_negative_symlinked_target_fails_even_if_it_resolves(self):
        self._write_all_targets()
        real = self.root / "elsewhere.md"
        real.write_text("x", encoding="utf-8")
        self._target(self.names[0]).unlink()
        self._target(self.names[0]).symlink_to(real)
        findings, absent = self._cite([f"knowledge/.../{self.names[0]}"])
        self.assertEqual(len(findings), 1)
        self.assertIn("BROKEN HISTORICAL REFERENCE", findings[0])
        self.assertEqual(absent, [])

    def test_negative_symlinked_target_directory_fails(self):
        self._write_all_targets()
        real_dir = self.root / "real_dir"
        (self.root / eic.ABBREV_TARGET_DIR).rename(real_dir)
        (self.root / eic.ABBREV_TARGET_DIR).symlink_to(real_dir, target_is_directory=True)
        findings, _ = self._cite([f"knowledge/.../{self.names[0]}"])
        self.assertEqual(len(findings), 1)
        self.assertIn("symlink", findings[0])

    def test_negative_non_regular_target_fails(self):
        self._write_all_targets()
        self._target(self.names[0]).unlink()
        self._target(self.names[0]).mkdir()
        findings, _ = self._cite([f"knowledge/.../{self.names[0]}"])
        self.assertEqual(len(findings), 1)
        self.assertIn("BROKEN HISTORICAL REFERENCE", findings[0])

    def test_negative_fifo_target_fails_promptly(self):
        self._write_all_targets()
        self._target(self.names[0]).unlink()
        os.mkfifo(self._target(self.names[0]))
        out = {}
        t = threading.Thread(
            target=lambda: out.update(r=self._cite([f"knowledge/.../{self.names[0]}"])), daemon=True)
        t.start()
        t.join(5)
        self.assertFalse(t.is_alive(), "open() on FIFO blocked")
        findings, absent = out["r"]
        self.assertEqual(len(findings), 1)
        self.assertIn("BROKEN HISTORICAL REFERENCE", findings[0])
        self.assertIn("not a regular file", findings[0])
        self.assertEqual(absent, [])


if __name__ == "__main__":
    # Direct execution is refused: it must never launch pytest outside the
    # governed runner. Use the governed invocation instead (built-in unittest
    # cases only; the pytest-style tests run via the governed pytest runner).
    sys.stderr.write(
        "REFUSED: do not execute this file directly. Use a governed invocation, e.g. "
        "backend/.venv/bin/python -I -m unittest discover -s "
        f"{Path(__file__).resolve().parent} -p test_evidence_integrity_check.py\n"
    )
    raise SystemExit(2)
