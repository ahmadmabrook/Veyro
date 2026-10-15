"""Tests for .github/workflows/release-lifecycle-ci.yml (GOV-01-R08 candidate).

NONREQUIRED candidate smoke workflow - this test file is local implementation
evidence only; it grants no R08, CI, independent-review, or module credit.

Same two layers as `test_foundation_skeleton_ci_workflow.py`:

1. Static assertions over the committed workflow text - events, permissions,
   SHA resolution, no action references, no secrets, no masking, all five
   required paths named and screened, the three ordered invocations, the
   NOT-claimed disclosure.
2. BEHAVIORAL execution of the workflow step's own extracted bash script
   against a synthetic local git remote (`file://` transport with
   `allowAnySHA1InWant`), proving the required negatives plus a real green
   run using the actual committed bytes of all five R08 files.

No network is touched.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent

WORKFLOW_REL = ".github/workflows/release-lifecycle-ci.yml"
REQUIRED_RELS = (
    "RELEASE_TRAIN.md",
    "tools/validate_release_lifecycle.py",
    "tools/tests/test_validate_release_lifecycle.py",
    "tools/generate_changelog.py",
    "tools/tests/test_generate_changelog.py",
)

WORKFLOW = REPO / WORKFLOW_REL


def code_lines() -> list[str]:
    return [
        ln
        for ln in WORKFLOW.read_text(encoding="utf-8").splitlines()
        if not ln.lstrip().startswith("#")
    ]


def extract_run_script() -> str:
    """Return the single `run: |` block body from the workflow, dedented.

    Indentation-based, no YAML dependency - parses exactly the bytes CI
    would execute. Mirrors the foundation-skeleton-ci test's own approach.
    """
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    starts = [i for i, ln in enumerate(lines) if re.fullmatch(r"\s*run: \|\s*", ln)]
    if len(starts) != 1:
        raise AssertionError(f"expected exactly one 'run: |' block, found {len(starts)}")
    start = starts[0]
    indent = len(lines[start]) - len(lines[start].lstrip())
    body: list[str] = []
    for ln in lines[start + 1:]:
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= indent:
            break
        body.append(ln)
    if not body:
        raise AssertionError("run block is empty")
    return textwrap.dedent("\n".join(body)) + "\n"


class WorkflowShapeTests(unittest.TestCase):
    def setUp(self):
        self.code = "\n".join(code_lines())
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_events_are_feature_branch_push_and_pull_request_only(self):
        self.assertRegex(self.code, r"(?m)^on:\s*$")
        self.assertRegex(self.code, r"(?m)^  push:\s*$")
        self.assertRegex(self.code, r"(?m)^    branches-ignore:\s*$")
        self.assertRegex(self.code, r"(?m)^      - main\s*$")
        self.assertRegex(self.code, r"(?m)^  pull_request:\s*$")
        self.assertNotIn("pull_request_target", self.code)
        self.assertNotIn("workflow_dispatch", self.code)
        self.assertNotIn("paths:", self.code)
        self.assertNotIn("paths-ignore:", self.code)

    def test_head_sha_resolves_push_vs_pull_request_via_actions_expression(self):
        self.assertRegex(
            self.code,
            r"(?m)^\s*HEAD_SHA: \$\{\{ github\.event_name == 'pull_request' "
            r"&& github\.event\.pull_request\.head\.sha \|\| github\.sha \}\}\s*$",
        )

    def test_no_actions_no_secrets_no_token_permissions_no_masking(self):
        self.assertNotRegex(self.code, r"^\s*-?\s*uses:", "no action references")
        self.assertNotIn("secrets.", self.code)
        self.assertRegex(self.code, r"(?m)^permissions: \{\}$")
        self.assertIn("set -euo pipefail", self.code)
        for masking in ("|| true", "|| :", "; true", "continue-on-error", "if: always()", "set +e"):
            self.assertNotIn(masking, self.code)

    def test_runs_on_ubuntu_24_04(self):
        self.assertRegex(self.code, r"(?m)^\s*runs-on: ubuntu-24\.04\s*$")

    def test_sha_and_repo_are_validated_before_use(self):
        self.assertIn('[[ "$REPO" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$ && "${REPO#*/}" != "." && "${REPO#*/}" != ".." ]]', self.code)
        self.assertIn('[[ "$HEAD_SHA" =~ ^[0-9a-f]{40}$ ]]', self.code)

    def test_fetch_is_tokenless_exact_sha_into_runner_temp(self):
        self.assertIn('${RUNNER_TEMP:?RUNNER_TEMP is required}', self.code)
        self.assertIn('git -C "$head_dir" fetch -q --no-tags --depth=1 origin "$HEAD_SHA"', self.code)
        self.assertIn('git -C "$head_dir" checkout -q --detach FETCH_HEAD', self.code)
        self.assertNotIn("GITHUB_TOKEN", self.code)

    def test_checkout_is_verified_against_the_requested_sha(self):
        self.assertIn('actual_sha="$(git -C "$head_dir" rev-parse HEAD)"', self.code)
        self.assertIn('[[ "$actual_sha" == "$HEAD_SHA" ]]', self.code)

    def test_all_five_required_paths_are_named_and_screened(self):
        for rel in REQUIRED_RELS:
            self.assertIn(f'"{rel}"', self.code)
        self.assertIn("100644|100755", self.code)
        self.assertIn('deny "head $HEAD_SHA has no $rel"', self.code)
        self.assertIn("symlink/gitlink/irregular", self.code)
        self.assertIn('[[ -f "$head_dir/$rel" && ! -L "$head_dir/$rel" ]]', self.code)

    def test_no_root_override_and_no_runner_own_checkout_path(self):
        self.assertNotIn("--root", self.code)

    def test_interpreter_version_is_asserted_before_execution(self):
        self.assertIn("sys.version_info >= (3, 10)", self.code)

    def test_three_invocations_present_in_order(self):
        expected = [
            'python3 "$head_dir/tools/validate_release_lifecycle.py" train "$head_dir/RELEASE_TRAIN.md"',
            'python3 "$head_dir/tools/tests/test_validate_release_lifecycle.py"',
            'python3 "$head_dir/tools/tests/test_generate_changelog.py"',
        ]
        positions = [self.code.index(line) for line in expected]
        self.assertEqual(positions, sorted(positions))

    def test_real_required_files_exist_at_the_declared_paths(self):
        for rel in REQUIRED_RELS:
            self.assertTrue((REPO / rel).is_file(), f"missing {rel}")

    def test_not_claimed_disclosure_is_present(self):
        for needle in (
            "NOT claimed",
            "No live CI run, no required-status check",
            "NONREQUIRED CANDIDATE",
            "grants no GOV-01-R08",
        ):
            self.assertIn(needle, self.text)


class Fixture:
    """A synthetic local git remote plus a runner for the workflow's own
    extracted bash script. `file://` transport with `allowAnySHA1InWant`
    mirrors the real job's anonymous exact-SHA fetch."""

    REPO_SLUG = "acme/widgets"

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.origin = tmp / "remote" / f"{self.REPO_SLUG}.git"
        self.script = tmp / "job.sh"
        self.script.write_text(extract_run_script(), encoding="utf-8")
        self.script.chmod(0o755)

    def _git(self, *args: str) -> str:
        return subprocess.run(
            ("git", "-C", str(self.origin), *args),
            check=True, capture_output=True, text=True,
        ).stdout.strip()

    def _write_text(self, rel: str, text: str) -> None:
        path = self._ensure(rel)
        path.write_text(text, encoding="utf-8")

    def _ensure(self, rel: str) -> Path:
        path = self.origin / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def init(self) -> None:
        self.origin.mkdir(parents=True)
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.email", "test@example.invalid")
        self._git("config", "user.name", "veyro test")
        self._git("config", "uploadpack.allowAnySHA1InWant", "true")
        self._git("config", "uploadpack.allowReachableSHA1InWant", "true")

    def _copy_all_real_files(self) -> None:
        for rel in REQUIRED_RELS:
            shutil.copyfile(REPO / rel, self._ensure(rel))

    def commit_clean(self) -> str:
        """All five required files, real unmodified bytes."""
        self._copy_all_real_files()
        self._git("add", "-A")
        self._git("commit", "-q", "--allow-empty", "-m", "candidate head")
        return self._git("rev-parse", "HEAD")

    def commit_missing(self, missing_rel: str) -> str:
        for rel in REQUIRED_RELS:
            if rel != missing_rel:
                shutil.copyfile(REPO / rel, self._ensure(rel))
        self._git("add", "-A")
        self._git("commit", "-q", "--allow-empty", "-m", f"candidate head, missing {missing_rel}")
        return self._git("rev-parse", "HEAD")

    def commit_with_symlinked(self, symlink_rel: str) -> str:
        self._copy_all_real_files()
        path = self.origin / symlink_rel
        path.unlink()
        os.symlink("/etc/passwd", path)
        self._git("add", "-A")
        self._git("commit", "-q", "--allow-empty", "-m", f"candidate head, symlinked {symlink_rel}")
        return self._git("rev-parse", "HEAD")

    def commit_with_broken_train(self) -> str:
        """All five real files, but RELEASE_TRAIN.md's 'Maintenance policy'
        heading is dropped - proves this job runs the real validator, not a
        stub, by producing that validator's own MISSING_SECTION wording."""
        self._copy_all_real_files()
        train = self.origin / "RELEASE_TRAIN.md"
        text = train.read_text(encoding="utf-8")
        broken = text.replace("## Maintenance policy", "## Something Else")
        self.assertion_guard(broken != text)
        train.write_text(broken, encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-q", "--allow-empty", "-m", "candidate head, broken RELEASE_TRAIN.md")
        return self._git("rev-parse", "HEAD")

    @staticmethod
    def assertion_guard(ok: bool) -> None:
        if not ok:
            raise AssertionError("fixture setup did not actually change the file")

    def run(self, head_sha: str, *, repo: str | None = None) -> subprocess.CompletedProcess:
        env = {
            "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""),
            "HOME": str(self.tmp),
            "RUNNER_TEMP": str(self.tmp / "runner-temp"),
            "SERVER_URL": f"file://{self.tmp / 'remote'}",
            "REPO": self.REPO_SLUG if repo is None else repo,
            "HEAD_SHA": head_sha,
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        }
        os.makedirs(env["RUNNER_TEMP"], exist_ok=True)
        return subprocess.run(
            ["bash", str(self.script)],
            check=False, env=env, cwd=str(self.tmp),
            capture_output=True, text=True, timeout=180,
        )


class BehaviorTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="veyro-release-lifecycle-ci-")
        self.addCleanup(self._tmp.cleanup)
        self.fx = Fixture(Path(self._tmp.name))
        self.fx.init()

    def assertDenied(self, result: subprocess.CompletedProcess, needle: str) -> None:
        self.assertNotEqual(result.returncode, 0, f"expected nonzero\nSTDOUT:{result.stdout}\nSTDERR:{result.stderr}")
        self.assertIn(needle, result.stdout + result.stderr)

    def test_clean_candidate_runs_validator_and_both_suites_green(self):
        head = self.fx.commit_clean()
        result = self.fx.run(head)
        self.assertEqual(result.returncode, 0, f"STDOUT:{result.stdout}\nSTDERR:{result.stderr}")
        combined = result.stdout + result.stderr
        self.assertIn("PASS", result.stdout)
        # Both unittest suites ran: each prints its own "OK" summary.
        self.assertGreaterEqual(combined.count("OK"), 2, combined)
        self.assertIn("tools/validate_release_lifecycle.py train", combined)
        self.assertIn("tools/tests/test_validate_release_lifecycle.py", combined)
        self.assertIn("tools/tests/test_generate_changelog.py", combined)

    def test_missing_required_file_denies_by_name(self):
        for rel in REQUIRED_RELS:
            with self.subTest(rel=rel):
                fx = Fixture(Path(tempfile.mkdtemp(prefix="veyro-rlc-missing-")))
                fx.init()
                head = fx.commit_missing(rel)
                result = fx.run(head)
                self.assertDenied(result, f"has no {rel}")

    def test_symlinked_required_file_denies(self):
        for rel in REQUIRED_RELS:
            with self.subTest(rel=rel):
                fx = Fixture(Path(tempfile.mkdtemp(prefix="veyro-rlc-symlink-")))
                fx.init()
                head = fx.commit_with_symlinked(rel)
                result = fx.run(head)
                self.assertDenied(result, "symlink/gitlink/irregular")

    def test_non_hex_head_sha_denies(self):
        result = self.fx.run("refs/heads/attacker")
        self.assertDenied(result, "is not a 40-hex commit sha")

    def test_short_hex_head_sha_denies(self):
        result = self.fx.run("abc123")
        self.assertDenied(result, "is not a 40-hex commit sha")

    def test_malformed_repo_denies_before_any_fetch(self):
        head = self.fx.commit_clean()
        result = self.fx.run(head, repo="not-a-valid-repo-slug")
        self.assertDenied(result, "is not a well-formed owner/name")

    def test_dot_segment_repo_denies_before_any_fetch(self):
        head = self.fx.commit_clean()
        for repo in ("acme/..", "../widgets"):
            with self.subTest(repo=repo):
                result = self.fx.run(head, repo=repo)
                self.assertDenied(result, "is not a well-formed owner/name")

    def test_unfetchable_sha_denies(self):
        self.fx.commit_clean()
        bogus = "f" * 40
        result = self.fx.run(bogus)
        self.assertNotEqual(result.returncode, 0)

    def test_broken_release_train_denies_with_real_validators_own_wording(self):
        head = self.fx.commit_with_broken_train()
        result = self.fx.run(head)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("MISSING_SECTION: Maintenance policy", result.stdout)


if __name__ == "__main__":
    unittest.main()
