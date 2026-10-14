"""Tests for .github/workflows/foundation-skeleton-ci.yml (GOV-01-R04 candidate,
M1-C-08; real-validator wiring for GOV-01-R01/SCN-MOD001-003).

Deterministic and offline, same two layers as this repo's other workflow test
files (e.g. test_dependency_vulnerability_gate_workflow.py):

1. Static assertions over the committed workflow text - events, permissions,
   SHA resolution, no action references, no secrets, no masking.
2. BEHAVIORAL execution of the workflow step's own extracted bash script
   against a synthetic local git remote (`file://` transport with
   `allowAnySHA1InWant`, exactly mirroring how the real job fetches an exact
   SHA anonymously), proving the required negatives: malformed sha/repo,
   an unfetchable (effectively "wrong") commit, and an absent or symlinked
   validator - plus a real green run using the actual committed validator
   bytes copied into the fixture commit.

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

WORKFLOW_REL = ".github/workflows/foundation-skeleton-ci.yml"
VALIDATOR_REL = "tools/validate_repo_skeleton.py"

WORKFLOW = REPO / WORKFLOW_REL
VALIDATOR = REPO / VALIDATOR_REL


def code_lines() -> list[str]:
    return [
        ln
        for ln in WORKFLOW.read_text(encoding="utf-8").splitlines()
        if not ln.lstrip().startswith("#")
    ]


def extract_run_script() -> str:
    """Return the single `run: |` block body from the workflow, dedented.

    Indentation-based, no YAML dependency (none is available in this
    environment) - parses exactly the bytes CI would execute.
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
        # Never the trusted/candidate-split trigger - nothing here needs it.
        self.assertNotIn("pull_request_target", self.code)
        self.assertNotIn("workflow_dispatch", self.code)
        self.assertNotIn("paths:", self.code)
        self.assertNotIn("paths-ignore:", self.code)

    def test_head_sha_resolves_push_vs_pull_request_via_actions_expression(self):
        # Resolved by the Actions expression evaluator before the shell ever
        # runs - never spliced together from untrusted text inside the script.
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

    def test_validator_path_is_screened_before_execution(self):
        self.assertRegex(self.code, rf'(?m)^\s*validator_rel="{re.escape(VALIDATOR_REL)}"\s*$')
        self.assertIn("100644|100755", self.code)
        self.assertIn('deny "head $HEAD_SHA has no $validator_rel"', self.code)
        self.assertIn("symlink/gitlink/irregular", self.code)
        self.assertIn('[[ -f "$head_dir/$validator_rel" && ! -L "$head_dir/$validator_rel" ]]', self.code)

    def test_execution_runs_the_fetched_heads_own_validator_copy(self):
        self.assertIn('python3 "$head_dir/$validator_rel"', self.code)
        # No --root override and no path belonging to the runner's own
        # checkout of this repository.
        self.assertNotIn("--root", self.code)

    def test_interpreter_version_is_asserted_before_execution(self):
        self.assertIn("sys.version_info >= (3, 10)", self.code)

    def test_real_validator_exists_at_the_declared_path(self):
        self.assertTrue(VALIDATOR.is_file())

    def test_not_claimed_disclosure_is_present(self):
        for needle in ("NOT claimed", "source file grants no CI result", "PUBLIC", "UNREVIEWED CANDIDATE"):
            self.assertIn(needle, self.text)


class Fixture:
    """A synthetic local git remote plus a runner for the workflow's own
    extracted bash script. `file://` transport with `allowAnySHA1InWant`
    mirrors the real job's anonymous exact-SHA fetch."""

    REPO_SLUG = "acme/widgets"

    def __init__(self, tmp: Path):
        self.tmp = tmp
        # repo_url = f"{SERVER_URL}/{REPO}.git" in the real script, so the
        # fixture remote must live at exactly that path for the slug above.
        self.origin = tmp / "remote" / f"{self.REPO_SLUG}.git"
        self.script = tmp / "job.sh"
        self.script.write_text(extract_run_script(), encoding="utf-8")
        self.script.chmod(0o755)

    def _git(self, *args: str) -> str:
        return subprocess.run(
            ("git", "-C", str(self.origin), *args),
            check=True, capture_output=True, text=True,
        ).stdout.strip()

    def _write(self, rel: str, text: str) -> None:
        path = self.origin / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def init(self) -> None:
        self.origin.mkdir(parents=True)
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.email", "test@example.invalid")
        self._git("config", "user.name", "veyro test")
        self._git("config", "uploadpack.allowAnySHA1InWant", "true")
        self._git("config", "uploadpack.allowReachableSHA1InWant", "true")

    def commit_with_real_validator(self, *, required_paths: tuple[str, ...] = ("x.txt",)) -> str:
        """A commit carrying the real, unmodified validator plus the given
        (dummy) required-looking paths, so the extracted script's own
        execution step runs genuine validator bytes, not a stub."""
        shutil.copyfile(VALIDATOR, self._ensure(VALIDATOR_REL))
        for rel in required_paths:
            self._write(rel, "x\n")
        self._git("add", "-A")
        self._git("commit", "-q", "--allow-empty", "-m", "candidate head")
        return self._git("rev-parse", "HEAD")

    def commit_without_validator(self) -> str:
        self._write("README.md", "no validator here\n")
        self._git("add", "-A")
        self._git("commit", "-q", "--allow-empty", "-m", "candidate head, no validator")
        return self._git("rev-parse", "HEAD")

    def commit_with_symlinked_validator(self) -> str:
        path = self._ensure(VALIDATOR_REL)
        if path.exists() or path.is_symlink():
            path.unlink()
        os.symlink("/etc/passwd", path)
        self._git("add", "-A")
        self._git("commit", "-q", "--allow-empty", "-m", "candidate head, symlinked validator")
        return self._git("rev-parse", "HEAD")

    def _ensure(self, rel: str) -> Path:
        path = self.origin / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

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
        self._tmp = tempfile.TemporaryDirectory(prefix="veyro-foundation-skeleton-ci-")
        self.addCleanup(self._tmp.cleanup)
        self.fx = Fixture(Path(self._tmp.name))
        self.fx.init()

    def assertDenied(self, result: subprocess.CompletedProcess, needle: str) -> None:
        self.assertNotEqual(result.returncode, 0, f"expected nonzero\nSTDOUT:{result.stdout}\nSTDERR:{result.stderr}")
        self.assertIn(needle, result.stdout + result.stderr)

    def test_clean_candidate_with_real_validator_and_all_paths_is_green(self):
        head = self.fx.commit_with_real_validator(
            required_paths=(
                "backend/pyproject.toml",
                "backend/app/__init__.py",
                "backend/app/modules/_shared/__init__.py",
                "backend/tests/unit/__init__.py",
                "backend/tests/component/__init__.py",
                "backend/tests/integration/__init__.py",
                "backend/tests/contract/__init__.py",
            )
        )
        result = self.fx.run(head)
        self.assertEqual(result.returncode, 0, f"STDOUT:{result.stdout}\nSTDERR:{result.stderr}")
        self.assertIn("PASS", result.stdout)

    def test_real_validator_denies_on_a_missing_required_path(self):
        head = self.fx.commit_with_real_validator(required_paths=("x.txt",))
        result = self.fx.run(head)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("MISSING_REQUIRED_PATH", result.stdout)

    def test_non_hex_head_sha_denies(self):
        result = self.fx.run("refs/heads/attacker")
        self.assertDenied(result, "is not a 40-hex commit sha")

    def test_short_hex_head_sha_denies(self):
        result = self.fx.run("abc123")
        self.assertDenied(result, "is not a 40-hex commit sha")

    def test_malformed_repo_denies_before_any_fetch(self):
        head = self.fx.commit_with_real_validator()
        result = self.fx.run(head, repo="not-a-valid-repo-slug")
        self.assertDenied(result, "is not a well-formed owner/name")

    def test_dot_segment_repo_denies_before_any_fetch(self):
        head = self.fx.commit_with_real_validator()
        for repo in ("acme/..", "../widgets"):
            with self.subTest(repo=repo):
                result = self.fx.run(head, repo=repo)
                self.assertDenied(result, "is not a well-formed owner/name")

    def test_unfetchable_sha_denies(self):
        self.fx.commit_with_real_validator()
        bogus = "f" * 40
        result = self.fx.run(bogus)
        self.assertNotEqual(result.returncode, 0)

    def test_absent_validator_denies_by_name(self):
        head = self.fx.commit_without_validator()
        result = self.fx.run(head)
        self.assertDenied(result, f"has no {VALIDATOR_REL}")

    def test_symlinked_validator_denies(self):
        head = self.fx.commit_with_symlinked_validator()
        result = self.fx.run(head)
        self.assertDenied(result, "symlink/gitlink/irregular")


if __name__ == "__main__":
    unittest.main()
