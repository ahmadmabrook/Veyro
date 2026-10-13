#!/usr/bin/env python3
"""
Focused unit tests for knowledge/00-System/validate_capabilities.py manifest
reading (MOD-001 GOV-01-R04, OWN-008/ADR-009 canonical manifest location).

Standard library only; isolated tempfile fixtures. Run with
`python3 tools/tests/test_validate_capabilities.py` or pytest.
"""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "validate_capabilities",
    Path(__file__).resolve().parents[2] / "knowledge/00-System/validate_capabilities.py",
)
vc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(vc)

MOD1 = (
    "module_id: MOD-001\n"
    "required_tool_ids:\n"
    "  - id: CAP-004\n    purpose: x\n"
    "  - id: CAP-012   # comment\n    purpose: y\n"
    "missing_capability_blockers:\n"
    "  - id: BLOCKER-CAP-099\n    detail: mentions CAP-077 in prose\n"
)
MOD0 = "capabilities:\n  - capability_id: CAP-001\n  - capability_id: CAP-002\n"


class ParseTests(unittest.TestCase):
    def test_required_tool_ids_block_only(self):
        self.assertEqual(vc.parse_manifest_capability_ids(MOD1), ["CAP-004", "CAP-012"])

    def test_legacy_capability_id_shape_retained(self):
        self.assertEqual(vc.parse_manifest_capability_ids(MOD0), ["CAP-001", "CAP-002"])

    def test_duplicates_preserved(self):
        text = "required_tool_ids:\n  - id: CAP-004\n  - id: CAP-004\n"
        self.assertEqual(vc.parse_manifest_capability_ids(text), ["CAP-004", "CAP-004"])

    def test_configured_manifests(self):
        rel = [m.relative_to(vc.ROOT).as_posix() for m in vc.MANIFESTS]
        self.assertEqual(rel, [
            "knowledge/03-Modules/MOD-000/evidence/module-capabilities.yaml",
            "contracts/engineering/module-capabilities.yaml",
        ])


class ReadManifestTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.path = self.root / "contracts/engineering/module-capabilities.yaml"
        self.path.parent.mkdir(parents=True)

    def read(self, path=None):
        return vc.read_manifest(path or self.path, self.root)

    def test_valid_manifest(self):
        self.path.write_text(MOD1, encoding="utf-8")
        text, reason = self.read()
        self.assertEqual(text, MOD1)
        self.assertIsNone(reason)

    def test_absent(self):
        text, reason = self.read()
        self.assertIsNone(text)
        self.assertIn("does not exist", reason)

    def test_directory(self):
        self.path.mkdir()
        text, reason = self.read()
        self.assertIsNone(text)
        self.assertIn("not a regular file", reason)

    def test_symlinked_file(self):
        target = self.root / "real.yaml"
        target.write_text(MOD1, encoding="utf-8")
        self.path.symlink_to(target)
        text, reason = self.read()
        self.assertIsNone(text)
        self.assertIn("symlink", reason)

    def test_symlinked_parent_directory(self):
        real = self.root / "elsewhere"
        real.mkdir()
        (real / "module-capabilities.yaml").write_text(MOD1, encoding="utf-8")
        link = self.root / "linked"
        link.symlink_to(real)
        text, reason = self.read(link / "module-capabilities.yaml")
        self.assertIsNone(text)
        self.assertIn("symlink", reason)

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                     "permission bits not enforced")
    def test_unreadable(self):
        self.path.write_text(MOD1, encoding="utf-8")
        self.path.chmod(0)
        self.addCleanup(self.path.chmod, 0o600)
        text, reason = self.read()
        self.assertIsNone(text)
        self.assertIn("unreadable", reason)

    def test_invalid_utf8(self):
        self.path.write_bytes(MOD1.encode() + b"\xff\xfe")
        text, reason = self.read()
        self.assertIsNone(text)
        self.assertIn("UTF-8", reason)

    def test_nul_bytes(self):
        self.path.write_text(MOD1 + "\x00", encoding="utf-8")
        text, reason = self.read()
        self.assertIsNone(text)
        self.assertIn("NUL", reason)

    def test_empty_and_whitespace(self):
        for body in ("", "  \n\n"):
            self.path.write_text(body, encoding="utf-8")
            text, reason = self.read()
            self.assertIsNone(text)
            self.assertIn("empty", reason)

    def test_no_dependencies_is_malformed(self):
        # Unrecognized shape would otherwise validate zero IDs -> false PASS.
        self.path.write_text("module_id: MOD-001\nrequired_tool_ids: []\n", encoding="utf-8")
        text, reason = self.read()
        self.assertIsNone(text)
        self.assertIn("no capability dependencies", reason)

    def test_outside_root(self):
        text, reason = vc.read_manifest(Path("/etc/hosts"), self.root)
        self.assertIsNone(text)
        self.assertIn("outside", reason)


if __name__ == "__main__":
    unittest.main()
