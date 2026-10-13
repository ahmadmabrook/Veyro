"""Tests for tools/generate_changelog.py (GOV-01-R08; SCN-MOD001-107).
Synthetic temp-Git-history fixtures only."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import generate_changelog as g

ENV = {
    "GIT_AUTHOR_NAME": "Synthetic", "GIT_AUTHOR_EMAIL": "synthetic@example.invalid",
    "GIT_COMMITTER_NAME": "Synthetic", "GIT_COMMITTER_EMAIL": "synthetic@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
}


class Repo:
    def __init__(self, root: Path):
        self.root = root
        self.n = 0
        self.git("init", "-q", "-b", "main")
        self.commit("initial")
        self.git("tag", "train-2026.01")

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(self.root), *args], env=ENV, check=True,
            capture_output=True, text=True,
        ).stdout

    def commit(self, subject: str) -> None:
        self.n += 1
        (self.root / f"f{self.n}.txt").write_text(str(self.n))
        self.git("add", "-A")
        self.git("commit", "-q", "-m", subject)

    def merge_pr(self, number: int, title: str, subject: str | None = None) -> None:
        self.git("checkout", "-q", "-b", f"pr{number}")
        self.commit(f"work for {number}")
        self.git("checkout", "-q", "main")
        subj = subject or f"Merge pull request #{number} from synthetic/pr{number}"
        self.git("merge", "--no-ff", "-q", f"pr{number}", "-m", subj, "-m", title)


class GenerateChangelogTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Repo(Path(self._tmp.name))

    def gen(self, **kw):
        args = {"repo": self.repo.root, "from_ref": "train-2026.01", "to_ref": "main", "release_id": "train-2026.02"}
        args.update(kw)
        return g.generate(**args)

    def test_qualifying_merged_prs_produce_entry(self):
        self.repo.merge_pr(7, "feat(auth): add login")
        self.repo.merge_pr(8, "docs: tweak readme")
        self.repo.merge_pr(9, "fix: close leak")
        self.assertEqual(
            self.gen(),
            "## train-2026.02 (train-2026.01..main)\n\n"
            "- feat(auth): add login (#7)\n- fix: close leak (#9)\n",
        )

    def test_squash_merge_is_derived_from_subject(self):
        self.repo.commit("feat: squashed thing (#12)")
        self.repo.commit("direct commit with no pr")
        self.assertIn("- feat: squashed thing (#12)\n", self.gen())

    def test_commits_after_to_ref_are_excluded(self):
        self.repo.merge_pr(7, "feat: in range")
        self.repo.git("tag", "train-2026.02")
        self.repo.merge_pr(8, "feat: later")
        out = self.gen(to_ref="train-2026.02")
        self.assertIn("#7", out)
        self.assertNotIn("#8", out)

    def test_empty_release_produces_no_entry(self):
        self.repo.merge_pr(5, "chore: bump")
        self.repo.merge_pr(6, "ci: tweak workflow")
        self.assertEqual(self.gen(), "")

    def test_range_with_only_direct_commits_produces_no_entry(self):
        self.repo.commit("direct commit")
        self.assertEqual(self.gen(), "")

    def test_empty_release_cli_writes_nothing(self):
        self.repo.merge_pr(5, "chore: bump")
        out = Path(self._tmp.name) / "out" / "CHANGELOG.md"
        out.parent.mkdir()
        rc = g.main(["--repo", str(self.repo.root), "--from-ref", "train-2026.01",
                     "--to-ref", "main", "--release-id", "train-2026.02", "--output", str(out)])
        self.assertEqual(rc, 0)
        self.assertFalse(out.exists())

    def test_cli_output_appends_and_rejects_duplicate_release(self):
        self.repo.merge_pr(7, "feat: a")
        out = Path(self._tmp.name) / "out" / "CHANGELOG.md"
        out.parent.mkdir()
        argv = ["--repo", str(self.repo.root), "--from-ref", "train-2026.01",
                "--to-ref", "main", "--release-id", "train-2026.02", "--output", str(out)]
        self.assertEqual(g.main(argv), 0)
        self.assertEqual(out.read_text(), "## train-2026.02 (train-2026.01..main)\n\n- feat: a (#7)\n")
        self.assertEqual(g.main(argv), 1)

    def test_malformed_pr_merge_subject_fails_closed(self):
        self.repo.merge_pr(7, "feat: x", subject="Merge pull request seven from synthetic/pr7")
        with self.assertRaisesRegex(g.ChangelogError, "malformed PR merge"):
            self.gen()

    def test_empty_pr_title_fails_closed(self):
        self.repo.merge_pr(7, " ")
        with self.assertRaisesRegex(g.ChangelogError, "empty title"):
            self.gen()

    def test_non_pr_merge_fails_closed(self):
        self.repo.merge_pr(7, "feat: x", subject="Merge branch 'pr7'")
        with self.assertRaisesRegex(g.ChangelogError, "non-PR merge"):
            self.gen()

    def test_duplicate_pr_number_fails_closed(self):
        self.repo.merge_pr(7, "feat: a")
        self.repo.commit("feat: again (#7)")
        with self.assertRaisesRegex(g.ChangelogError, "duplicate"):
            self.gen()

    def test_bad_inputs_fail_closed(self):
        self.repo.merge_pr(7, "feat: a")
        for kw in (
            {"release_id": "v1"}, {"from_ref": "nope"}, {"to_ref": "--all"},
            {"from_ref": ""}, {"to_ref": "train-2026.01"}, {"repo": self.repo.root / "missing"},
        ):
            with self.subTest(kw=kw), self.assertRaises(g.ChangelogError):
                self.gen(**kw)

    def test_from_ref_not_ancestor_fails_closed(self):
        self.repo.git("checkout", "-q", "-b", "side", "train-2026.01")
        self.repo.commit("side work")
        self.repo.git("checkout", "-q", "main")
        self.repo.merge_pr(7, "feat: a")
        with self.assertRaisesRegex(g.ChangelogError, "not an ancestor"):
            self.gen(from_ref="side")

    def test_cli_malformed_returns_1(self):
        rc = g.main(["--repo", str(self.repo.root), "--from-ref", "nope",
                     "--to-ref", "main", "--release-id", "train-2026.02"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
