"""Tests for tools/validate_mobile_ci_workflow.py (GOV-01-R07; SCN-MOD001-052/055/100/101/128).
Each test copies the real committed workflow into a temp root and mutates one thing."""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import validate_mobile_ci_workflow as v


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        shutil.copytree(REPO / "mobile", self.root / "mobile")
        (self.root / ".github/workflows").mkdir(parents=True)
        self.wf = self.root / v.WORKFLOW
        shutil.copy(REPO / v.WORKFLOW, self.wf)

    def edit(self, old: str, new: str):
        text = self.wf.read_text(encoding="utf-8")
        self.assertIn(old, text)
        self.wf.write_text(text.replace(old, new, 1), encoding="utf-8")


class PositiveTests(Base):
    def test_committed_workflow_passes(self):
        self.assertEqual(v.check(self.root), [])
        self.assertEqual(v.check(REPO), [])

    def test_common_code_change_triggers_android_and_ios_regression(self):  # SCN-052
        globs, jobs = v.parse(self.wf.read_text(encoding="utf-8"))
        hit = v.triggered_jobs(["mobile/shared/src/commonMain/Sync.kt"], globs, jobs)
        self.assertIn("android-regression", hit)
        self.assertIn("ios-regression", hit)

    def test_toolchain_matrix_change_triggers_all_four_dimensions(self):  # SCN-128
        globs, jobs = v.parse(self.wf.read_text(encoding="utf-8"))
        hit = v.triggered_jobs(["mobile/TOOLCHAIN_MATRIX.md"], globs, jobs)
        for j in ("android-build", "ios-build", "android-ui-qualification",
                  "android-accessibility-qualification", "android-performance-qualification"):
            self.assertIn(j, hit)

    def test_unrelated_path_triggers_nothing(self):
        globs, jobs = v.parse(self.wf.read_text(encoding="utf-8"))
        self.assertEqual(v.triggered_jobs(["backend/app/main.py"], globs, jobs), [])


class NegativeTests(Base):
    def test_stale_path_filter_denied(self):  # SCN-100
        self.edit("- 'mobile/**'", "- 'mobile/legacy/**'")
        out = v.check(self.root)
        self.assertTrue(any(d.startswith("TRIGGER_STALE: mobile/shared/build.gradle.kts") for d in out))
        self.assertIn("TRIGGER_MISSING: paths filter lacks 'mobile/**'", out)

    def test_missing_ios_build_job_denied(self):  # SCN-128 negative
        self.edit("  ios-build:", "  ios-compile:")
        self.assertEqual(v.check(self.root), ["JOB_MISSING: ios-build"])

    def test_android_runner_misassigned(self):  # SCN-101
        self.edit("android-regression:\n    name: android-regression\n    runs-on: ubuntu-24.04",
                  "android-regression:\n    name: android-regression\n    runs-on: windows-2022")
        self.assertEqual(v.check(self.root), ["RUNNER_MISASSIGNED: android-regression runs-on='windows-2022'"])

    def test_ios_macos_runner_denied(self):  # SCN-056
        self.edit("runs-on: ${{ vars.VEYRO_IOS_RUNNER_LABEL }}", "runs-on: macos-14")
        out = v.check(self.root)
        self.assertIn("IOS_RUNNER_COMMITTED: ios-build runs-on='macos-14'", out)
        self.assertTrue(any(d.startswith("FORBIDDEN_REFERENCE") for d in out))

    def test_secret_and_action_references_denied(self):
        self.edit("    steps:\n      - name: Placeholder (denies - no Android regression harness exists)",
                  "    steps:\n      - uses: actions/checkout@v4\n      - name: x\n        env:\n          K: ${{ secrets.K }}")
        out = v.check(self.root)
        self.assertEqual(sum(d.startswith("FORBIDDEN_REFERENCE") for d in out), 2)

    def test_missing_trigger_and_workflow_fail_closed(self):
        self.edit("    paths:\n", "    branches:\n")
        self.assertTrue(any(d.startswith("TRIGGER_MISSING: no pull_request") for d in v.check(self.root)))
        self.wf.unlink()
        self.assertTrue(v.check(self.root)[0].startswith("TRIGGER_MISSING: unreadable"))


if __name__ == "__main__":
    unittest.main()
