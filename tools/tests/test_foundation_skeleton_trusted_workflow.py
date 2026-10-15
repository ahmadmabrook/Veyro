"""Tests for .github/workflows/foundation-skeleton-trusted.yml - the GOV-01-R04
candidate TRUSTED required-path status check for MOD-001's repository skeleton
(GOV-01-R01 / SCN-MOD001-003).

Deterministic and offline, the same two layers as this repo's other workflow
test files (e.g. test_foundation_skeleton_ci_workflow.py):

1. Static assertions over the committed workflow text - trigger, zero
   permissions, no action references, no secrets, no masking, no `${{ }}`
   inside any script body, and above all that the trusted decision is
   self-contained: the seven required paths and the checking logic both live
   in the workflow, and the candidate-writable
   `tools/validate_repo_skeleton.py` is never named in the executed body.
2. BEHAVIORAL execution of the workflow step's own extracted bash script
   against synthetic local Git objects (`file://` transport with
   `allowAnySHA1InWant`, mirroring how the real job fetches an exact SHA
   anonymously): a genuine green tree, and the negatives that matter -
   malformed SHAs/repo, an unfetchable commit, and a required path that is
   missing, a directory, a symlink, under a symlinked ancestor, under a
   gitlinked ancestor, or under an ancestor that is a regular file.

The divergence this candidate exists to create is pinned by two paired tests:
one tampered candidate commit turns the NONREQUIRED smoke check
(`foundation-skeleton-ci.yml`, read but never modified here) GREEN while
leaving this trusted check RED.

No network is touched. These are offline unit tests of the extracted script
body only; they prove nothing about a real `pull_request_target` run, which
cannot happen until this file lives on a published default branch.
"""
from __future__ import annotations

import ast
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

WORKFLOW_REL = ".github/workflows/foundation-skeleton-trusted.yml"
SMOKE_WORKFLOW_REL = ".github/workflows/foundation-skeleton-ci.yml"
VALIDATOR_REL = "tools/validate_repo_skeleton.py"

WORKFLOW = REPO / WORKFLOW_REL
SMOKE_WORKFLOW = REPO / SMOKE_WORKFLOW_REL
VALIDATOR = REPO / VALIDATOR_REL

# The seven paths the trusted definition must expect, independent of anything
# a candidate head ships. Asserted equal to both the workflow's own literal
# list and the committed validator's manifest.
EXPECTED_REQUIRED_PATHS = (
    "backend/pyproject.toml",
    "backend/app/__init__.py",
    "backend/app/modules/_shared/__init__.py",
    "backend/tests/unit/__init__.py",
    "backend/tests/component/__init__.py",
    "backend/tests/integration/__init__.py",
    "backend/tests/contract/__init__.py",
)

# `github.sha` stand-in: the trusted default-branch snapshot that would have
# supplied the workflow definition. Only logged by the script, but it must
# still be a well-formed 40-hex SHA or the job denies.
FAKE_TRUSTED_SHA = "1" * 40


def code_lines(path: Path) -> list[str]:
    return [
        ln
        for ln in path.read_text(encoding="utf-8").splitlines()
        if not ln.lstrip().startswith("#")
    ]


def extract_run_script(path: Path) -> str:
    """Return the single `run: |` block body from `path`, dedented.

    Indentation-based, no YAML dependency (none is available in this
    environment) - parses exactly the bytes CI would execute.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [i for i, ln in enumerate(lines) if re.fullmatch(r"\s*run: \|\s*", ln)]
    if len(starts) != 1:
        raise AssertionError(f"expected exactly one 'run: |' block in {path}, found {len(starts)}")
    start = starts[0]
    indent = len(lines[start]) - len(lines[start].lstrip())
    body: list[str] = []
    for ln in lines[start + 1:]:
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= indent:
            break
        body.append(ln)
    if not body:
        raise AssertionError(f"run block in {path} is empty")
    return textwrap.dedent("\n".join(body)) + "\n"


def script_code(path: Path) -> str:
    """The extracted run body with whole-line comments removed - the bytes
    that actually execute. Negative assertions ("no `git checkout`", "the
    candidate validator is never named") must be made against this, not
    against the body's own prose explaining why those constructs are absent."""
    body = extract_run_script(path).splitlines()
    return "\n".join(ln for ln in body if not ln.lstrip().startswith("#")) + "\n"


def workflow_required_paths() -> tuple[str, ...]:
    """The literal REQUIRED_PATHS tuple out of the workflow's own trusted
    Python body - parsed from the executed script, not from the YAML comments."""
    script = extract_run_script(WORKFLOW)
    match = re.search(r"REQUIRED_PATHS = \((?P<body>.*?)\)\n", script, re.DOTALL)
    if match is None:
        raise AssertionError("no REQUIRED_PATHS tuple in the workflow's executed body")
    return tuple(re.findall(r'"([^"]+)"', match.group("body")))


def validator_required_paths() -> tuple[str, ...]:
    """REQUIRED_PATHS out of the committed validator, via `ast` - read here
    only to prove the trusted duplicate is in sync. The workflow itself never
    reads this file."""
    tree = ast.parse(VALIDATOR.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "REQUIRED_PATHS" for t in node.targets
        ):
            return tuple(ast.literal_eval(node.value))
    raise AssertionError(f"no REQUIRED_PATHS assignment in {VALIDATOR_REL}")


class WorkflowShapeTests(unittest.TestCase):
    def setUp(self):
        self.code = "\n".join(code_lines(WORKFLOW))
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.script = extract_run_script(WORKFLOW)
        self.executed = script_code(WORKFLOW)

    def test_trigger_is_pull_request_target_on_main_only(self):
        self.assertRegex(self.code, r"(?m)^on:\s*$")
        self.assertRegex(self.code, r"(?m)^  pull_request_target:\s*$")
        self.assertRegex(self.code, r"(?m)^    types: \[opened, synchronize, reopened\]\s*$")
        self.assertRegex(self.code, r"(?m)^    branches:\s*$")
        self.assertRegex(self.code, r"(?m)^      - main\s*$")
        # A trusted gate must not be hand-triggerable, and must not be
        # skippable by touching no matching path.
        self.assertNotIn("workflow_dispatch", self.code)
        self.assertNotIn("paths:", self.code)
        self.assertNotIn("paths-ignore:", self.code)
        # Not the candidate-definition triggers: those would load this
        # definition from the PR head and defeat the whole trust split.
        self.assertNotRegex(self.code, r"(?m)^  pull_request:\s*$")
        self.assertNotRegex(self.code, r"(?m)^  push:\s*$")

    def test_zero_permissions_no_secrets_no_token(self):
        self.assertRegex(self.code, r"(?m)^permissions: \{\}$")
        self.assertNotIn("secrets.", self.code)
        self.assertNotIn("GITHUB_TOKEN", self.code)

    def test_no_action_references_and_no_masking(self):
        self.assertNotRegex(self.code, r"(?m)^\s*-?\s*uses:", "no action references")
        self.assertIn("set -euo pipefail", self.script)
        for masking in ("|| true", "|| :", "; true", "continue-on-error",
                        "if: always()", "set +e", "if:"):
            self.assertNotIn(masking, self.code, f"refused masking construct: {masking}")

    def test_job_and_check_name_differ_from_the_nonrequired_smoke_check(self):
        self.assertRegex(self.code, r"(?m)^name: foundation-skeleton-trusted\s*$")
        self.assertRegex(self.code, r"(?m)^    name: foundation-skeleton-trusted\s*$")
        self.assertNotIn("name: foundation-skeleton-ci", self.code)

    def test_runs_on_ubuntu_24_04_with_a_timeout(self):
        self.assertRegex(self.code, r"(?m)^\s*runs-on: ubuntu-24\.04\s*$")
        self.assertRegex(self.code, r"(?m)^\s*timeout-minutes: 10\s*$")

    def test_untrusted_values_reach_the_shell_only_through_env(self):
        self.assertRegex(
            self.code,
            r"(?m)^\s*HEAD_SHA: \$\{\{ github\.event\.pull_request\.head\.sha \}\}\s*$",
        )
        self.assertRegex(self.code, r"(?m)^\s*TRUSTED_SHA: \$\{\{ github\.sha \}\}\s*$")
        # The decisive property: no Actions expression anywhere inside the
        # executed body, so no candidate-controlled string is ever parsed as
        # shell.
        self.assertNotIn("${{", self.executed)

    def test_shas_and_repo_are_validated_before_any_fetch(self):
        self.assertIn('[[ "$REPO" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$', self.script)
        self.assertIn('[[ "${!var}" =~ ^[0-9a-f]{40}$ ]]', self.script)
        self.assertIn("for var in TRUSTED_SHA HEAD_SHA; do", self.script)

    def test_candidate_head_is_fetched_by_exact_sha_and_never_materialized(self):
        self.assertIn('git -C "$cand_git" fetch -q --no-tags --depth=1 origin "$HEAD_SHA"', self.script)
        self.assertIn('[[ "$fetched" == "$HEAD_SHA" ]]', self.script)
        self.assertIn('git -C "$cand_git" cat-file -e "$HEAD_SHA^{commit}"', self.script)
        # Nothing that would put candidate bytes on disk or on sys.path.
        for forbidden in ("git checkout", "--detach", "git archive", "tar ", "pip install"):
            self.assertNotIn(
                forbidden, self.executed, f"candidate tree must stay inert: {forbidden}"
            )

    def test_tree_listing_is_nul_delimited_through_a_file_not_a_substitution(self):
        self.assertIn(
            'git -C "$cand_git" ls-tree -r -t --full-tree -z "$HEAD_SHA" > "$work/entries.nul"',
            self.script,
        )
        self.assertNotIn('$(git -C "$cand_git" ls-tree', self.script)

    def test_python_heredoc_is_quoted_and_isolated(self):
        self.assertIn("""python3 -E -s - "$work/entries.nul" <<'PY'""", self.script)
        self.assertRegex(self.script, r"(?m)^PY\s*$")

    def test_trusted_body_never_names_the_candidate_writable_validator(self):
        # The whole point of the split: the head's own validator and its
        # REQUIRED_PATHS are not an input to this decision. Asserted against
        # the executed lines - the body's comments do name that file, to
        # explain that the trusted list is a duplicate of its manifest rather
        # than a read of it.
        self.assertNotIn("validate_repo_skeleton", self.executed)

    def test_required_paths_live_in_the_trusted_body_and_match_the_manifest(self):
        in_workflow = workflow_required_paths()
        self.assertEqual(in_workflow, EXPECTED_REQUIRED_PATHS)
        self.assertEqual(len(in_workflow), 7)
        # Sync check only - a drift here means the trusted duplicate needs
        # updating, not that the workflow should start reading that file.
        self.assertEqual(in_workflow, validator_required_paths())

    def test_checking_logic_screens_modes_and_types_explicitly(self):
        for needle in ('DIR_MODE = "040000"',
                       'FILE_MODES = ("100644", "100755")',
                       '"120000": "symlink"',
                       '"160000": "gitlink (submodule)"',
                       "ancestor is not a directory",
                       "is a directory, required to be a regular file",
                       "not a regular file",
                       ": missing"):
            self.assertIn(needle, self.script, f"missing explicit screen: {needle}")

    def test_limitations_are_stated_in_the_header(self):
        for needle in ("UNREVIEWED CANDIDATE",
                       "SAME-NAME CANDIDATE CHECK SPOOFING IS NOT SOLVED HERE",
                       "INSTALLATION ON A PUBLISHED DEFAULT BRANCH IS UNPROVEN",
                       "ANONYMOUS FORK-HEAD FETCH REACHABILITY IS UNPROVEN",
                       "THE HEAD TREE IS SCREENED, NOT THE MERGE RESULT",
                       "does not run at all",
                       "No branch protection is created, modified or requested"):
            self.assertIn(needle, " ".join(self.text.split()).replace(" # ", " "))

    def test_the_nonrequired_smoke_workflow_is_untouched_and_still_nonrequired_shaped(self):
        smoke = "\n".join(code_lines(SMOKE_WORKFLOW))
        self.assertRegex(smoke, r"(?m)^name: foundation-skeleton-ci\s*$")
        self.assertNotIn("pull_request_target", smoke)
        self.assertNotIn("foundation-skeleton-trusted", smoke)


class Fixture:
    """Synthetic local Git remote plus a runner for an extracted workflow
    script. `file://` transport with `allowAnySHA1InWant` mirrors the real
    job's anonymous exact-SHA fetch."""

    REPO_SLUG = "acme/widgets"

    def __init__(self, tmp: Path):
        self.tmp = tmp
        # The scripts build their URL as f"{SERVER_URL}/{REPO}.git", so the
        # fixture remote must sit at exactly that path for the slug above.
        self.origin = tmp / "remote" / f"{self.REPO_SLUG}.git"
        self.scripts: dict[str, Path] = {}
        for key, source in (("trusted", WORKFLOW), ("smoke", SMOKE_WORKFLOW)):
            path = tmp / f"job-{key}.sh"
            path.write_text(extract_run_script(source), encoding="utf-8")
            path.chmod(0o755)
            self.scripts[key] = path

    def _git(self, *args: str) -> str:
        return subprocess.run(
            ("git", "-C", str(self.origin), *args),
            check=True, capture_output=True, text=True,
        ).stdout.strip()

    def _write(self, rel: str, text: str = "x\n") -> Path:
        path = self.origin / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def init(self) -> None:
        self.origin.mkdir(parents=True)
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.email", "test@example.invalid")
        self._git("config", "user.name", "veyro test")
        self._git("config", "uploadpack.allowAnySHA1InWant", "true")
        self._git("config", "uploadpack.allowReachableSHA1InWant", "true")

    def _commit(self, message: str) -> str:
        self._git("add", "-A")
        self._git("commit", "-q", "--allow-empty", "-m", message)
        return self._git("rev-parse", "HEAD")

    def commit_skeleton(self, *, omit: tuple[str, ...] = ()) -> str:
        for rel in EXPECTED_REQUIRED_PATHS:
            if rel not in omit:
                self._write(rel)
        return self._commit("candidate head")

    def commit_with_executable_leaf(self, rel: str) -> str:
        self.commit_skeleton()
        (self.origin / rel).chmod(0o755)
        return self._commit("candidate head, executable leaf")

    def commit_with_directory_instead_of_file(self, rel: str) -> str:
        self.commit_skeleton(omit=(rel,))
        self._write(f"{rel}/placeholder", "stand-in\n")
        return self._commit("candidate head, directory where a file is required")

    def commit_with_symlink_at(self, rel: str, target: str = "/etc/passwd") -> str:
        omit = tuple(p for p in EXPECTED_REQUIRED_PATHS if p == rel or p.startswith(rel + "/"))
        self.commit_skeleton(omit=omit)
        path = self.origin / rel
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        elif path.exists() or path.is_symlink():
            path.unlink()
        path.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target, path)
        return self._commit(f"candidate head, symlink at {rel}")

    def commit_with_regular_file_ancestor(self, prefix: str) -> str:
        omit = tuple(p for p in EXPECTED_REQUIRED_PATHS if p.startswith(prefix + "/"))
        self.commit_skeleton(omit=omit)
        self._write(prefix, "not a directory\n")
        return self._commit(f"candidate head, regular file at {prefix}")

    def commit_with_gitlink_ancestor(self, prefix: str) -> str:
        """A mode-160000 submodule entry standing in for a required
        directory. Written through the index, which is the only way to get a
        gitlink without a real nested clone."""
        omit = tuple(p for p in EXPECTED_REQUIRED_PATHS if p.startswith(prefix + "/"))
        base = self.commit_skeleton(omit=omit)
        self._git("update-index", "--add", "--cacheinfo", f"160000,{base},{prefix}")
        self._git("commit", "-q", "-m", f"candidate head, gitlink at {prefix}")
        return self._git("rev-parse", "HEAD")

    def commit_tampered_candidate(self) -> str:
        """The candidate rewrites everything it controls: it drops the whole
        `backend/tests` subtree, guts its own validator's manifest, and
        replaces the nonrequired smoke workflow with an always-green stub.
        None of those files is an input to the trusted check."""
        kept = tuple(p for p in EXPECTED_REQUIRED_PATHS if not p.startswith("backend/tests/"))
        for rel in kept:
            self._write(rel)
        source = VALIDATOR.read_text(encoding="utf-8")
        start = source.index("REQUIRED_PATHS = [")
        end = source.index("\n]", start) + 2
        self._write(VALIDATOR_REL, source[:start] + "REQUIRED_PATHS = []" + source[end:])
        self._write(
            SMOKE_WORKFLOW_REL,
            "name: foundation-skeleton-ci\non:\n  pull_request:\njobs:\n"
            "  foundation-skeleton-ci:\n    runs-on: ubuntu-24.04\n    steps:\n"
            "      - run: echo green\n",
        )
        return self._commit("candidate head, tampered validator and smoke workflow")

    def run(
        self,
        head_sha: str,
        *,
        which: str = "trusted",
        repo: str | None = None,
        trusted_sha: str = FAKE_TRUSTED_SHA,
    ) -> subprocess.CompletedProcess:
        env = {
            "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""),
            "HOME": str(self.tmp),
            "RUNNER_TEMP": str(self.tmp / "runner-temp"),
            "SERVER_URL": f"file://{self.tmp / 'remote'}",
            "REPO": self.REPO_SLUG if repo is None else repo,
            "HEAD_SHA": head_sha,
            "TRUSTED_SHA": trusted_sha,
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        }
        os.makedirs(env["RUNNER_TEMP"], exist_ok=True)
        return subprocess.run(
            ["bash", str(self.scripts[which])],
            check=False, env=env, cwd=str(self.tmp),
            capture_output=True, text=True, timeout=180,
        )


class BehaviorTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="veyro-foundation-skeleton-trusted-")
        self.addCleanup(self._tmp.cleanup)
        self.fx = Fixture(Path(self._tmp.name))
        self.fx.init()

    def assertGreen(self, result: subprocess.CompletedProcess) -> None:
        self.assertEqual(
            result.returncode, 0,
            f"expected zero\nSTDOUT:{result.stdout}\nSTDERR:{result.stderr}",
        )

    def assertDenied(self, result: subprocess.CompletedProcess, *needles: str) -> None:
        self.assertNotEqual(
            result.returncode, 0,
            f"expected nonzero\nSTDOUT:{result.stdout}\nSTDERR:{result.stderr}",
        )
        output = result.stdout + result.stderr
        for needle in needles:
            self.assertIn(needle, output, f"STDOUT:{result.stdout}\nSTDERR:{result.stderr}")

    # --- positive ---

    def test_complete_skeleton_is_green(self):
        result = self.fx.run(self.fx.commit_skeleton())
        self.assertGreen(result)
        self.assertIn("Trusted required paths checked: 7", result.stdout)
        self.assertIn("foundation-skeleton-trusted: PASS", result.stdout)

    def test_executable_mode_leaf_is_accepted(self):
        result = self.fx.run(self.fx.commit_with_executable_leaf("backend/app/__init__.py"))
        self.assertGreen(result)
        self.assertIn("foundation-skeleton-trusted: PASS", result.stdout)

    # --- required-path negatives ---

    def test_missing_required_path_denies_by_name(self):
        head = self.fx.commit_skeleton(omit=("backend/tests/contract/__init__.py",))
        result = self.fx.run(head)
        self.assertDenied(
            result,
            "MISSING_REQUIRED_PATH",
            "backend/tests/contract/__init__.py -> backend/tests/contract: missing",
            "1 of 7",
        )

    def test_directory_standing_in_for_a_required_file_denies(self):
        head = self.fx.commit_with_directory_instead_of_file("backend/pyproject.toml")
        result = self.fx.run(head)
        self.assertDenied(
            result,
            "backend/pyproject.toml: is a directory, required to be a regular file",
        )

    def test_symlinked_required_file_denies(self):
        head = self.fx.commit_with_symlink_at("backend/app/__init__.py")
        result = self.fx.run(head)
        self.assertDenied(
            result,
            "backend/app/__init__.py: refused symlink (mode 120000)",
        )

    def test_symlinked_ancestor_denies_for_every_path_beneath_it(self):
        head = self.fx.commit_with_symlink_at("backend/tests")
        result = self.fx.run(head)
        self.assertDenied(
            result,
            "backend/tests: refused symlink (mode 120000)",
            "4 of 7",
        )

    def test_gitlinked_ancestor_denies(self):
        head = self.fx.commit_with_gitlink_ancestor("backend/tests")
        result = self.fx.run(head)
        self.assertDenied(
            result,
            "backend/tests: refused gitlink (submodule) (mode 160000)",
            "4 of 7",
        )

    def test_regular_file_ancestor_denies(self):
        head = self.fx.commit_with_regular_file_ancestor("backend/tests")
        result = self.fx.run(head)
        self.assertDenied(
            result,
            "backend/tests: ancestor is not a directory (mode 100644 type blob)",
        )

    def test_empty_tree_denies_on_all_seven(self):
        head = self.fx.commit_skeleton(omit=EXPECTED_REQUIRED_PATHS)
        result = self.fx.run(head)
        self.assertDenied(result, "backend: missing", "7 of 7")

    # --- input-validation negatives ---

    def test_non_hex_head_sha_denies(self):
        self.assertDenied(self.fx.run("refs/heads/attacker"), "is not a 40-hex commit sha")

    def test_short_hex_head_sha_denies(self):
        self.assertDenied(self.fx.run("abc123"), "is not a 40-hex commit sha")

    def test_malformed_trusted_sha_denies(self):
        head = self.fx.commit_skeleton()
        result = self.fx.run(head, trusted_sha="main")
        self.assertDenied(result, "TRUSTED_SHA 'main' is not a 40-hex commit sha")

    def test_malformed_repo_denies_before_any_fetch(self):
        head = self.fx.commit_skeleton()
        for repo in ("not-a-valid-repo-slug", "acme/..", "../widgets"):
            with self.subTest(repo=repo):
                result = self.fx.run(head, repo=repo)
                self.assertDenied(result, "is not a well-formed owner/name")

    def test_unfetchable_sha_denies(self):
        self.fx.commit_skeleton()
        result = self.fx.run("f" * 40)
        self.assertNotEqual(result.returncode, 0)

    # --- the divergence this candidate exists to create ---

    def test_candidate_tampering_cannot_turn_the_trusted_check_green(self):
        """The candidate guts its own `REQUIRED_PATHS` and stubs its own smoke
        workflow - the two moves that do turn the nonrequired smoke check
        green (next test). Neither is an input here, so the trusted check
        stays RED on the paths actually absent from the head tree."""
        head = self.fx.commit_tampered_candidate()
        result = self.fx.run(head)
        self.assertDenied(
            result,
            "MISSING_REQUIRED_PATH",
            "backend/tests: missing",
            "4 of 7",
        )
        self.assertNotIn("validate_repo_skeleton", result.stdout + result.stderr)

    def test_the_same_tampered_head_can_still_turn_the_smoke_check_green(self):
        """Paired with the test above, on the SAME commit: run through the
        real committed `foundation-skeleton-ci.yml` body, the tampered head is
        GREEN, because that check executes the candidate's own gutted
        validator. That is the smoke check's documented limitation and the
        reason this separate trusted check exists; it is not a defect being
        fixed in that file, which is untouched here."""
        head = self.fx.commit_tampered_candidate()
        smoke = self.fx.run(head, which="smoke")
        self.assertGreen(smoke)
        self.assertIn("Required paths checked: 0", smoke.stdout)
        self.assertIn("PASS", smoke.stdout)

        trusted = self.fx.run(head)
        self.assertNotEqual(
            trusted.returncode, 0,
            "trusted check must stay red on the exact head the smoke check passed",
        )


if __name__ == "__main__":
    unittest.main()
