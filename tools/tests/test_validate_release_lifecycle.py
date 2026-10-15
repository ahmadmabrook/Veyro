"""Tests for tools/validate_release_lifecycle.py (GOV-01-R08; SCN-MOD001-108, 125).
Synthetic fixtures only."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import validate_release_lifecycle as v

TRAIN = "# T\n\n## Maintenance policy\n\nFixes for 12 weeks.\n\n## Customer-communication template\n\nSYNTHETIC template.\n"
PATH = {"new_release_id": "synthetic-2", "approval_ref": "SYNTHETIC-APPROVAL-1"}


def rec(stage, prev=None, **extra):
    d = {"release_id": "synthetic-1", "lifecycle_stage": stage}
    if prev:
        d["previous_lifecycle_stage"] = prev
    d.update(extra)
    return d


class TrainTests(unittest.TestCase):
    def test_complete_train_passes(self):
        self.assertEqual(v.check_train(TRAIN), [])

    def test_repo_release_train_passes(self):
        text = (TOOLS.parent / "RELEASE_TRAIN.md").read_text(encoding="utf-8")
        self.assertEqual(v.check_train(text), [])

    def test_each_missing_section_denied_by_name(self):
        for name in v.REQUIRED_SECTIONS:
            text = TRAIN.replace(f"## {name}", "## Other")
            self.assertEqual(v.check_train(text), [f"MISSING_SECTION: {name}"])

    def test_empty_section_denied(self):
        text = TRAIN.replace("Fixes for 12 weeks.", "")
        self.assertEqual(v.check_train(text), ["EMPTY_SECTION: Maintenance policy"])


class RecordTests(unittest.TestCase):
    def test_each_stage_accepted(self):
        for s in ("beta", "GA", "deprecated"):
            self.assertEqual(v.check_record(rec(s)), [])

    def test_beta_to_ga_and_ga_to_deprecated_pass(self):
        self.assertEqual(v.check_record(rec("GA", "beta")), [])
        self.assertEqual(v.check_record(rec("deprecated", "GA")), [])

    def test_missing_stage_denied(self):
        d = rec("beta")
        del d["lifecycle_stage"]
        self.assertIn("MISSING_LIFECYCLE_STAGE", v.check_record(d))

    def test_unknown_stage_denied(self):
        for s in ("removed", "ga", "", None):
            self.assertTrue(any(p.startswith("UNKNOWN_LIFECYCLE_STAGE") for p in v.check_record(rec(s))))

    def test_deprecated_to_beta_without_path_denied(self):
        out = v.check_record(rec("beta", "deprecated"))
        self.assertEqual(len(out), 1)
        self.assertIn("INVALID_TRANSITION: deprecated -> beta", out[0])

    def test_deprecated_to_beta_with_governed_path_passes(self):
        self.assertEqual(v.check_record(rec("beta", "deprecated", re_release_path=PATH)), [])

    def test_incomplete_path_denied(self):
        bad = {"new_release_id": "x", "approval_ref": " "}
        self.assertTrue(v.check_record(rec("beta", "deprecated", re_release_path=bad)))

    def test_re_release_path_same_as_release_id_denied(self):
        same_id = {"new_release_id": "synthetic-1", "approval_ref": "SYNTHETIC-APPROVAL-1"}
        out = v.check_record(rec("beta", "deprecated", re_release_path=same_id))
        self.assertEqual(len(out), 1)
        self.assertIn("INVALID_TRANSITION: deprecated -> beta", out[0])

    def test_re_release_path_unknown_key_denied(self):
        bad = dict(PATH, extra_field="x")
        out = v.check_record(rec("GA", "beta", re_release_path=bad))
        self.assertTrue(any("MALFORMED_RE_RELEASE_PATH" in p and "extra_field" in p for p in out))

    def test_re_release_path_unknown_key_denied_with_no_prior_stage(self):
        bad = dict(PATH, extra_field="x")
        out = v.check_record(rec("beta", re_release_path=bad))
        self.assertTrue(any("MALFORMED_RE_RELEASE_PATH" in p and "extra_field" in p for p in out))

    def test_re_release_path_missing_key_denied(self):
        bad = {"new_release_id": "synthetic-2"}
        out = v.check_record(rec("beta", re_release_path=bad))
        self.assertTrue(any("MALFORMED_RE_RELEASE_PATH" in p and "approval_ref" in p for p in out))

    def test_re_release_path_non_object_denied(self):
        out = v.check_record(rec("beta", re_release_path="not-an-object"))
        self.assertIn("MALFORMED_RE_RELEASE_PATH: must be an object", out)

    def test_well_formed_path_on_forward_move_still_passes(self):
        self.assertEqual(v.check_record(rec("GA", "beta", re_release_path=PATH)), [])

    def test_whitespace_approval_ref_on_forward_move_denied(self):
        bad = {"new_release_id": "synthetic-2", "approval_ref": " "}
        out = v.check_record(rec("GA", "beta", re_release_path=bad))
        self.assertTrue(any("MALFORMED_RE_RELEASE_PATH" in p and "approval_ref" in p for p in out))

    def test_whitespace_new_release_id_with_no_prior_stage_denied(self):
        bad = {"new_release_id": " ", "approval_ref": "SYNTHETIC-APPROVAL-1"}
        out = v.check_record(rec("beta", re_release_path=bad))
        self.assertTrue(any("MALFORMED_RE_RELEASE_PATH" in p and "new_release_id" in p for p in out))

    def test_well_formed_path_with_no_prior_stage_passes(self):
        self.assertEqual(v.check_record(rec("beta", re_release_path=PATH)), [])

    def test_forward_skip_denied_even_with_path(self):
        out = v.check_record(rec("deprecated", "beta", re_release_path=PATH))
        self.assertIn("skips a stage", out[0])

    def test_unknown_field_and_non_object_denied(self):
        self.assertIn("UNKNOWN_FIELD: extra", v.check_record(rec("beta", extra=1)))
        self.assertTrue(v.check_record([]))


class CliTests(unittest.TestCase):
    def run_cli(self, mode, content):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "in"
            p.write_text(content, encoding="utf-8")
            return subprocess.run([sys.executable, str(TOOLS / "validate_release_lifecycle.py"), mode, str(p)],
                                  capture_output=True, text=True, check=False)

    def test_exit_codes(self):
        self.assertEqual(self.run_cli("train", TRAIN).returncode, 0)
        r = self.run_cli("train", "# x\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("MISSING_SECTION: Maintenance policy", r.stdout)
        self.assertEqual(self.run_cli("record", json.dumps(rec("GA", "beta"))).returncode, 0)
        self.assertEqual(self.run_cli("record", json.dumps(rec("beta", "deprecated"))).returncode, 1)
        self.assertEqual(self.run_cli("record", "{not json").returncode, 1)


if __name__ == "__main__":
    unittest.main()
