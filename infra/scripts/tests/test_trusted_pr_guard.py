"""Focused, local Git-object tests; these do not claim live branch protection."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


GUARD = Path(__file__).resolve().parents[1] / "trusted-pr-guard.sh"


class TrustedPRGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.write("README.md", "base\n")
        self.write(".github/workflows/ci.yml", "name: CI\n")
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.fork = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("checkout", "-qb", "candidate")

    def git(self, *args):
        return subprocess.run(
            ["git", *args], cwd=self.repo, text=True, capture_output=True, check=True
        )

    def write(self, name, content):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def candidate(self, name, content):
        self.write(name, content)
        self.git("add", "-A")
        self.git("commit", "-qm", "candidate change")
        head = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("checkout", "-q", "main")
        # The base adds the guard after the candidate forked. A stale PR must
        # not be mistaken for a candidate deletion of this base-owned file.
        self.write("infra/scripts/trusted-pr-guard.sh", GUARD.read_text())
        self.git("add", "-A")
        self.git("commit", "-qm", "install trusted guard")
        base = self.git("rev-parse", "HEAD").stdout.strip()
        env = dict(os.environ, BASE_SHA=base, HEAD_SHA=head)
        return subprocess.run(
            ["bash", str(GUARD)], cwd=self.repo, env=env, text=True, capture_output=True
        )

    def test_stale_ordinary_pr_passes(self):
        result = self.candidate("backend/app.py", "value = 1\n")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_changed_existing_workflow_fails(self):
        result = self.candidate(".github/workflows/ci.yml", "name: bypass\n")
        self.assertNotEqual(result.returncode, 0)

    def test_added_sibling_workflow_fails(self):
        result = self.candidate(".github/workflows/spoof.yml", "name: spoof\n")
        self.assertNotEqual(result.returncode, 0)

    def test_added_local_action_fails(self):
        result = self.candidate(".github/actions/spoof/action.yml", "name: spoof\n")
        self.assertNotEqual(result.returncode, 0)

    def test_guard_edit_fails(self):
        result = self.candidate("infra/scripts/trusted-pr-guard.sh", "exit 0\n")
        self.assertNotEqual(result.returncode, 0)

    def test_github_codeowners_fails(self):
        result = self.candidate(".github/CODEOWNERS", "x = 1\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("protected", result.stderr)

    def test_github_other_file_fails(self):
        result = self.candidate(".github/dependabot.yml", "x = 1\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("protected", result.stderr)

    def test_github_nested_file_fails(self):
        result = self.candidate(".github/ISSUE_TEMPLATE/bug.md", "x = 1\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("protected", result.stderr)

    def test_root_codeowners_fails(self):
        result = self.candidate("CODEOWNERS", "x = 1\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("protected", result.stderr)

    def test_docs_codeowners_fails(self):
        result = self.candidate("docs/CODEOWNERS", "x = 1\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("protected", result.stderr)

    def test_review_gate_script_fails(self):
        result = self.candidate("infra/scripts/opus_review_gate.py", "x = 1\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("protected", result.stderr)

    def test_review_gate_tests_fails(self):
        result = self.candidate("infra/scripts/tests/test_opus_review_gate.py", "x = 1\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("protected", result.stderr)

    def test_whitespace_error_fails(self):
        result = self.candidate("backend/app.py", "value = 1  \n")
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
