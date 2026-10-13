"""Tests for tools/validate_toolchain_matrix.py (GOV-01-R07; SCN-MOD001-127).
Synthetic fixtures only: each test copies the real committed mobile/ config into a
temp root and mutates one thing."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import validate_toolchain_matrix as v

SECOND_KMP = 'plugins {\n    kotlin("multiplatform") version "2.2.20"\n}\nversion = "0.2.0-synthetic"\n'


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        shutil.copytree(REPO / "mobile", self.root / "mobile")
        self.matrix = self.root / "mobile" / "TOOLCHAIN_MATRIX.md"

    def edit(self, path: Path, old: str, new: str):
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new), encoding="utf-8")


class PositiveTests(Base):
    def test_fixture_copy_passes(self):
        self.assertEqual(v.check(self.root), [])

    def test_committed_repo_passes(self):
        self.assertEqual(v.check(REPO), [])

    def test_cli_exit_codes(self):
        run = lambda: subprocess.run([sys.executable, str(TOOLS / "validate_toolchain_matrix.py"), "--root", str(self.root)],
                                     capture_output=True, text=True, check=False)
        ok = run()
        self.assertEqual((ok.returncode, ok.stdout.startswith("PASS")), (0, True))
        self.edit(self.matrix, "| gradle | 8.14 |", "| gradle | 8.13 |")
        bad = run()
        self.assertEqual(bad.returncode, 1)
        self.assertIn("TOOLCHAIN_DRIFT: gradle", bad.stdout)


class DriftTests(Base):  # SCN-127(a)
    def test_matrix_gradle_diverges_from_config(self):
        self.edit(self.matrix, "| gradle | 8.14 |", "| gradle | 8.13 |")
        out = v.check(self.root)
        self.assertEqual(sum(d.startswith("TOOLCHAIN_DRIFT: gradle") for d in out), 2)  # both stubs cited
        self.assertTrue(any("mobile/shared/build.gradle.kts=8.14" in d for d in out))
        self.assertTrue(any("mobile/androidApp/build.gradle.kts=8.14" in d for d in out))

    def test_config_diverges_from_matrix(self):
        self.edit(self.root / "mobile/androidApp/build.gradle.kts",
                  'id("com.android.application") version "8.11.1"', 'id("com.android.application") version "8.10.0"')
        self.assertEqual(v.check(self.root),
                         ["TOOLCHAIN_DRIFT: agp matrix=8.11.1 mobile/androidApp/build.gradle.kts=8.10.0"])

    def test_pin_only_in_a_comment_is_missing(self):
        self.edit(self.root / "mobile/shared/build.gradle.kts",
                  'id("org.jetbrains.compose") version "1.9.0"', '// id("org.jetbrains.compose") version "1.9.0"')
        self.assertEqual(v.check(self.root), ["CONFIG_PIN_MISSING: no committed Gradle config pins 'compose_multiplatform'"])

    def test_matrix_missing_pin_fails_closed(self):
        self.edit(self.matrix, "| xcode | 16.4 |\n", "")
        self.assertEqual(v.check(self.root), ["MATRIX_INVALID: toolchain_pins is missing a version for 'xcode'"])


class WhitelabelTests(Base):  # SCN-127(b)
    def test_missing_brand_row_denied(self):
        text = self.matrix.read_text(encoding="utf-8")
        self.matrix.write_text("\n".join(l for l in text.splitlines() if not l.startswith("| syntheticBrandB")) + "\n",
                               encoding="utf-8")
        self.assertEqual(v.check(self.root), ["WHITELABEL_BRAND_MISSING: syntheticBrandB"])

    def test_missing_section_denies_every_brand(self):
        self.edit(self.matrix, "## whitelabel_release_metadata", "## renamed_section")
        self.assertEqual(v.check(self.root),
                         ["WHITELABEL_BRAND_MISSING: syntheticBrandA", "WHITELABEL_BRAND_MISSING: syntheticBrandB"])

    def test_empty_field_and_package_drift(self):
        self.edit(self.matrix, "| NOT_PUBLISHED_SYNTHETIC |\n| syntheticBrandB", "|  |\n| syntheticBrandB")
        self.edit(self.matrix, "app.veyro.synthetic.brandb", "app.veyro.synthetic.other")
        self.assertEqual(v.check(self.root), [
            "WHITELABEL_FIELD_MISSING: syntheticBrandA.store_status",
            ("WHITELABEL_DRIFT: syntheticBrandB bundle_package_id matrix=app.veyro.synthetic.other "
             "config=app.veyro.synthetic.brandb")])


class SharedModuleTests(Base):  # SCN-127(c)
    def test_missing_module_version_denied(self):
        extra = self.root / "mobile" / "featureKit"
        extra.mkdir()
        (extra / "build.gradle.kts").write_text(SECOND_KMP, encoding="utf-8")
        self.assertEqual(v.check(self.root), ["SHARED_MODULE_VERSION_MISSING: mobile/featureKit"])

    def test_declared_second_module_passes(self):
        extra = self.root / "mobile" / "featureKit"
        extra.mkdir()
        (extra / "build.gradle.kts").write_text(SECOND_KMP, encoding="utf-8")
        self.edit(self.matrix, "| mobile/shared | 0.1.0-synthetic |\n",
                  "| mobile/shared | 0.1.0-synthetic |\n| mobile/featureKit | 0.2.0-synthetic |\n")
        self.assertEqual(v.check(self.root), [])

    def test_matrix_module_without_committed_config_denied(self):
        self.edit(self.matrix, "| mobile/shared | 0.1.0-synthetic |\n",
                  "| mobile/shared | 0.1.0-synthetic |\n| mobile/ghost | 0.2.0-synthetic |\n")
        self.assertEqual(v.check(self.root), [
            "SHARED_MODULE_CONFIG_MISSING: mobile/ghost has a matrix version but no committed KMP build.gradle.kts"])

    def test_module_version_drift(self):
        self.edit(self.matrix, "| mobile/shared | 0.1.0-synthetic |", "| mobile/shared | 9.9.9 |")
        self.assertEqual(v.check(self.root), ["SHARED_MODULE_VERSION_DRIFT: mobile/shared matrix=9.9.9 config=0.1.0-synthetic"])


class FailClosedTests(Base):
    def test_missing_matrix(self):
        self.matrix.unlink()
        self.assertTrue(v.check(self.root)[0].startswith("MATRIX_INVALID: unreadable input"))

    def test_no_config(self):
        (self.root / "mobile/shared/build.gradle.kts").unlink()
        (self.root / "mobile/androidApp/build.gradle.kts").unlink()
        self.assertTrue(v.check(self.root)[0].startswith("MATRIX_INVALID: no mobile"))


if __name__ == "__main__":
    unittest.main()
