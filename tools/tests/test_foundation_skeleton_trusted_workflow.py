"""Tests for .github/workflows/foundation-skeleton-trusted.yml - the GOV-01-R04
candidate TRUSTED required-path status check for MOD-001's repository skeleton
(GOV-01-R01 / SCN-MOD001-003).

Deterministic and offline, the same two layers as this repo's other workflow
test files (e.g. test_foundation_skeleton_ci_workflow.py):

1. Static assertions over the committed workflow text - trigger, zero
   permissions, no action references, no secrets, no masking, no `${{ }}`
   inside any script body, and that the trusted decision is self-contained:
   the seven required paths and the checking logic both live in the workflow,
   and the only read of `tools/validate_repo_skeleton.py` is from the TRUSTED
   commit, never from the candidate head.
2. BEHAVIORAL execution of the workflow step's own extracted bash script
   against synthetic local Git objects (`file://` transport with
   `allowAnySHA1InWant`, mirroring how the real job fetches an exact SHA
   anonymously): a genuine green tree, and the negatives that matter -
   malformed SHAs/repo, an unfetchable commit, and a required path that is
   missing, a directory, a symlink, under a symlinked ancestor, under a
   gitlinked ancestor, or under an ancestor that is a regular file.

BUG-074 adds a third thing to exercise: the job's runtime assertion that its
own trusted literal still equals `tools/validate_repo_skeleton.py`'s
REQUIRED_PATHS *at the trusted commit*. The fixture therefore pins a real
trusted commit (distinct from, and committed before, every candidate commit)
and the behavioral tests cover both directions - a desynced, missing,
malformed, non-literal, duplicated or symlinked trusted manifest denies; and
a candidate-side rewrite of that same file changes neither the sync nor the
screen.

BUG-074's residual adds a fourth: that assertion's AST layer is a static-shape
heuristic and cannot decide arbitrary Python semantics, so the job also pins
the SHA-256 of the exact trusted blob bytes to a literal digest in the
default-branch definition. The behavioral tests therefore also cover the drift
the AST layer provably cannot see - alias mutation, a `globals()` write, and a
comment-only edit - each of which must now deny on the digest while leaving
TRUSTED_MANIFEST_MUTABLE/_DESYNC silent, plus the exact committed source
passing, plus the fact that a candidate-only edit to that file reaches neither
the digest nor any other part of the decision.

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
import hashlib
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

# The repository's real committed validator. The fixture's trusted commit
# carries exactly these bytes, so the sync assertion is exercised against the
# manifest that actually ships, not a hand-written stand-in.
VALIDATOR_SOURCE = VALIDATOR.read_text(encoding="utf-8")
# The exact-source digest the workflow must pin: SHA-256 over the committed
# validator's bytes (NOT a git object id - no `blob <len>\0` prefix).
# Recomputed here from the real file, so a validator edit that does not come
# with a pin update fails this suite rather than silently desyncing CI.
EXPECTED_MANIFEST_SHA256 = hashlib.sha256(VALIDATOR.read_bytes()).hexdigest()


def manifest_literal(paths: tuple[str, ...]) -> str:
    body = "".join(f'    "{p}",\n' for p in paths)
    return f"REQUIRED_PATHS = [\n{body}]"


def validator_source_with(manifest: str) -> str:
    """The real validator with its REQUIRED_PATHS list literal swapped for
    `manifest` - used to build the trusted-manifest negatives."""
    start = VALIDATOR_SOURCE.index("REQUIRED_PATHS = [")
    end = VALIDATOR_SOURCE.index("\n]", start) + 2
    return VALIDATOR_SOURCE[:start] + manifest + VALIDATOR_SOURCE[end:]


# A trusted manifest that has grown an eighth required path while the
# workflow's own literal still names seven: the exact drift BUG-074 is about.
EIGHTH_PATH = "backend/tests/e2e/__init__.py"
EIGHT_PATH_VALIDATOR = validator_source_with(
    manifest_literal(EXPECTED_REQUIRED_PATHS + (EIGHTH_PATH,))
)
# A symlink target that is itself a syntactically valid, correctly-synced
# manifest: without the mode check, reading the symlink's blob content would
# sync cleanly, so this pins that the entry's MODE is what decides.
SYNCED_SYMLINK_TARGET = "REQUIRED_PATHS = [" + ", ".join(
    f'"{p}"' for p in EXPECTED_REQUIRED_PATHS
) + "]"

# Each tail below is appended to the UNCHANGED real validator, so the file
# still parses, still holds exactly ONE top-level literal
# `REQUIRED_PATHS = [...]`, and that literal is still exactly the workflow's
# seven paths - every assertion an assignment-only AST read makes about it
# holds. What the tail changes is the value the module would actually expose,
# which that read never sees, so the sync reports GREEN on a default-branch
# manifest that is in fact desynced. The job cannot decide the runtime value
# without executing the file, so the only honest answer is to refuse it:
# REQUIRED_PATHS must be bound exactly once, by one top-level literal
# assignment, and never rebound or mutated anywhere the AST can see it.
POST_ASSIGNMENT_MUTATIONS = {
    "aug_assign": 'REQUIRED_PATHS += ["backend/new_required.py"]',
    "append": 'REQUIRED_PATHS.append("backend/new_required.py")',
    "extend": 'REQUIRED_PATHS.extend(["backend/new_required.py"])',
    "insert": 'REQUIRED_PATHS.insert(0, "backend/new_required.py")',
    "remove": 'REQUIRED_PATHS.remove("backend/pyproject.toml")',
    "pop": "REQUIRED_PATHS.pop()",
    "clear": "REQUIRED_PATHS.clear()",
    "update": 'REQUIRED_PATHS.update(["backend/new_required.py"])',
    "sort": "REQUIRED_PATHS.sort()",
    "subscript_assign": 'REQUIRED_PATHS[0] = "backend/new_required.py"',
    "slice_assign": "REQUIRED_PATHS[:] = []",
    "subscript_aug_assign": 'REQUIRED_PATHS[0] += ".bak"',
    "subscript_delete": "del REQUIRED_PATHS[0]",
    "name_delete": "del REQUIRED_PATHS",
    # A second PLAIN top-level assignment is deliberately absent here: it is
    # already covered, by name and count, by the duplicate-assignment negative
    # below, which must keep reporting TRUSTED_MANIFEST_UNREADABLE/"found 2".
    "annotated_reassign": 'REQUIRED_PATHS: list = ["backend/new_required.py"]',
    "walrus_reassign": '_DECOY = (REQUIRED_PATHS := ["backend/new_required.py"])',
    "tuple_unpack_reassign": '(REQUIRED_PATHS, _OTHER) = (["backend/new_required.py"], 1)',
    "for_target_reassign": "for REQUIRED_PATHS in ([],):\n    pass",
    "conditional_reassign": 'if True:\n    REQUIRED_PATHS = ["backend/new_required.py"]',
    "global_rebind": (
        "def _grow():\n"
        "    global REQUIRED_PATHS\n"
        '    REQUIRED_PATHS = ["backend/new_required.py"]\n'
        "\n\n_grow()"
    ),
}

# The same class reached without any later statement at all: the sole binding
# of REQUIRED_PATHS is itself not a plain top-level literal assignment, so
# there is no static literal to hold the default branch to.
NON_PLAIN_SOLE_BINDINGS = {
    "annotated_only": 'REQUIRED_PATHS: list = [\n    "backend/pyproject.toml",\n]',
    "walrus_only": '_SEED = (REQUIRED_PATHS := ["backend/pyproject.toml"])',
    "conditional_only": 'if True:\n    REQUIRED_PATHS = ["backend/pyproject.toml"]',
}

# BUG-074 residual. Each tail below is appended to the UNCHANGED real
# validator and is INVISIBLE to the AST contract: the alias and `globals()`
# writes never put REQUIRED_PATHS itself in a Store/Del context nor attach a
# MUTATING_ATTRS call to that name, and the comment changes nothing
# executable at all. So every static check still passes - exactly one plain
# top-level literal, no AST-visible mutation, literal equal to the workflow's
# seven - while the first two ship a module that exposes eight paths. A static
# heuristic cannot close this; only exact-source bytes can, so each of these
# must deny on the pinned SHA-256 and must NOT be reported as a shape failure.
DIGEST_ONLY_DRIFT = {
    "alias_mutation": (
        "ALIAS = REQUIRED_PATHS\n"
        'ALIAS.append("backend/new_required.py")'
    ),
    "globals_mutation": 'globals()["REQUIRED_PATHS"].append("backend/new_required.py")',
    # The minimal case: a comment-only edit. Semantically identical, byte
    # different - the pin must not care which kind of drift it is.
    "comment_only": "# one comment-only byte change, nothing executable",
}


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
        self.assertIn(
            'python3 -E -s - "$work/manifest.entry" "$work/manifest.src.txt" '
            """"$work/entries.nul" <<'PY'""",
            self.script,
        )
        self.assertRegex(self.script, r"(?m)^PY\s*$")

    def test_the_validator_is_read_only_from_the_trusted_commit(self):
        # The head's own validator and its REQUIRED_PATHS are still not an
        # input to this decision. Since BUG-074 the file IS named in the
        # executed body - but only ever read out of the trusted object store
        # at the trusted SHA, so every executed line that names it must be
        # free of the candidate's repository and SHA.
        mentions = [ln for ln in self.executed.splitlines() if "validate_repo_skeleton" in ln]
        self.assertTrue(mentions, "the trusted manifest read must be present")
        for line in mentions:
            self.assertNotIn("cand_git", line, line)
            self.assertNotIn("HEAD_SHA", line, line)
        self.assertIn(
            'git -C "$trusted_git" ls-tree --full-tree -z "$TRUSTED_SHA" '
            "-- tools/validate_repo_skeleton.py",
            self.script,
        )
        self.assertIn(
            'git -C "$trusted_git" cat-file blob '
            '"$TRUSTED_SHA:tools/validate_repo_skeleton.py"',
            self.script,
        )
        # Read as text and parsed as a literal - never imported or executed.
        self.assertIn("ast.literal_eval(", self.executed)
        for forbidden in ("importlib", "__import__", "runpy", "exec(", "compile("):
            self.assertNotIn(forbidden, self.executed, f"trusted manifest stays inert: {forbidden}")

    def test_trusted_commit_is_fetched_by_exact_sha_into_its_own_object_store(self):
        self.assertIn('trusted_git="$work/trusted.git"', self.script)
        self.assertIn('git -C "$trusted_git" fetch -q --no-tags --depth=1 origin "$TRUSTED_SHA"',
                      self.script)
        self.assertIn('[[ "$trusted_fetched" == "$TRUSTED_SHA" ]]', self.script)
        self.assertIn('git -C "$trusted_git" cat-file -e "$TRUSTED_SHA^{commit}"', self.script)
        # Two separate object stores; the trusted read can never resolve
        # through candidate-fetched objects.
        self.assertNotEqual(
            re.search(r'trusted_git="([^"]+)"', self.script).group(1),
            re.search(r'cand_git="([^"]+)"', self.script).group(1),
        )

    def test_required_paths_live_in_the_trusted_body_and_match_the_manifest(self):
        in_workflow = workflow_required_paths()
        self.assertEqual(in_workflow, EXPECTED_REQUIRED_PATHS)
        self.assertEqual(len(in_workflow), 7)
        # Still a local duplicate, but no longer only a local one: the job
        # itself re-asserts this equality at runtime against the trusted
        # commit, and denies by these names if it does not hold.
        self.assertEqual(in_workflow, validator_required_paths())
        self.assertIn("TRUSTED_MANIFEST_DESYNC", self.script)
        self.assertIn("TRUSTED_MANIFEST_UNREADABLE", self.script)

    def test_the_sync_assertion_precedes_the_candidate_screen(self):
        # Ordering is the whole control: a desynced manifest must deny before
        # any candidate entry is judged, not after.
        sync = self.executed.index("TRUSTED_MANIFEST_DESYNC")
        screen = self.executed.index("MOD-001 TRUSTED REPOSITORY-SKELETON REQUIRED-PATH SCREEN")
        self.assertLess(sync, screen)
        self.assertLess(sync, self.executed.index("failures = ["))

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

    def test_the_static_literal_contract_is_enforced_in_the_trusted_body(self):
        # The contract that replaces "compare the first literal and hope":
        # every mutation channel the AST can see is refused by name, and the
        # refusal is part of the executed body, not of the header's prose.
        self.assertIn("TRUSTED_MANIFEST_MUTABLE", self.executed)
        for needle in ("ast.walk(module)", "ast.Store", "ast.Del", "ast.Subscript",
                       "ast.Attribute", "ast.Global", "ast.Nonlocal", "ast.ExceptHandler",
                       "ast.alias", "ast.arg", "MUTATING_ATTRS", "allowed_targets"):
            self.assertIn(needle, self.executed, f"missing mutation screen: {needle}")
        for attr in ("append", "extend", "insert", "remove", "pop", "clear",
                     "update", "sort", "reverse"):
            self.assertIn(f'"{attr}"', self.executed, f"unrefused in-place mutator: {attr}")
        # Decided entirely from the parsed tree: the trusted source is still
        # never run to find out what it would do.
        for forbidden in ("exec(", "eval(compile", "importlib", "__import__", "runpy"):
            self.assertNotIn(forbidden, self.executed, forbidden)

    def test_the_pinned_digest_is_the_committed_validator_exact_source_sha256(self):
        """The pin must be the SHA-256 of the real committed validator's
        bytes. Recomputed from the file here, so a default-branch validator
        edit without a matching pin update fails locally instead of turning
        the trusted check red only once it runs."""
        match = re.search(
            r'TRUSTED_MANIFEST_SHA256 = \(\s*"([0-9a-f]{64})"\s*\)', self.executed
        )
        self.assertIsNotNone(match, "no pinned exact-source digest in the executed body")
        self.assertEqual(match.group(1), EXPECTED_MANIFEST_SHA256)
        # Hashed in the trusted body itself, over the bytes read from the
        # trusted commit - and still without running them.
        self.assertIn("hashlib.sha256(manifest_bytes).hexdigest()", self.executed)
        self.assertIn("manifest_bytes = manifest_src.read_bytes()", self.executed)

    def test_the_digest_pin_denies_before_the_candidate_screen(self):
        """Ordering: the pin is the LAST trusted-manifest check (so a shape
        failure still reports which rule it broke, and the AST layer keeps
        constraining whatever source a future pin update points at) but still
        strictly before any candidate entry is judged."""
        pin = self.executed.index("TRUSTED_MANIFEST_DIGEST_MISMATCH")
        self.assertGreater(pin, self.executed.index("TRUSTED_MANIFEST_DESYNC"))
        self.assertLess(
            pin, self.executed.index("MOD-001 TRUSTED REPOSITORY-SKELETON REQUIRED-PATH SCREEN")
        )
        self.assertLess(pin, self.executed.index("failures = ["))

    def test_the_header_states_the_pin_guarantee_and_its_limit(self):
        prose = " ".join(self.text.split()).replace(" # ", " ")
        for needle in ("EXACT-SOURCE",
                       "TRUSTED_MANIFEST_DIGEST_MISMATCH",
                       "NOT a proof of arbitrary Python semantics",
                       "guarantees EXACT-SOURCE SYNC",
                       "REQUIRES an intentional update of the pinned digest",
                       "candidate-only change to that file cannot alter this job's decision"):
            self.assertIn(needle, prose, f"missing pin disclosure: {needle}")

    def test_the_mutation_contract_denies_before_the_literal_comparison(self):
        mutable = self.executed.index("TRUSTED_MANIFEST_MUTABLE")
        self.assertLess(mutable, self.executed.index("TRUSTED_MANIFEST_DESYNC"))
        self.assertLess(mutable, self.executed.index("ast.literal_eval("))

    def test_limitations_are_stated_in_the_header(self):
        for needle in ("UNREVIEWED CANDIDATE",
                       "SAME-NAME CANDIDATE CHECK SPOOFING IS NOT SOLVED HERE",
                       "INSTALLATION ON A PUBLISHED DEFAULT BRANCH IS UNPROVEN",
                       "ANONYMOUS FORK-HEAD FETCH REACHABILITY IS UNPROVEN",
                       "THE HEAD TREE IS SCREENED, NOT THE MERGE RESULT",
                       "THE SYNC ASSERTION TRUSTS THE ACTIONS CONTEXT FOR `github.sha`",
                       "does not run at all",
                       "No branch protection is created, modified or requested"):
            self.assertIn(needle, " ".join(self.text.split()).replace(" # ", " "))

    def test_the_header_claims_only_the_static_contract_and_states_its_residue(self):
        """The header must not describe the sync as a measurement of the
        validator's runtime value - it is a property of the source text - and
        must name the dynamic channels that stay open."""
        prose = " ".join(self.text.split()).replace(" # ", " ")
        for needle in ("STATIC-LITERAL CONTRACT",
                       "THE SYNC IS A STATIC-LITERAL CONTRACT, NOT A RUNTIME-VALUE PROOF",
                       "never executes, imports or evaluates the trusted validator",
                       "cannot observe the value `REQUIRED_PATHS` actually holds",
                       "mutation through an alias",
                       "writes through `globals()`",
                       "an in-place mutator whose name is not on the explicit list",
                       "mutation performed by a DIFFERENT module",
                       "a REVIEW obligation on any change to that file",
                       "TRUSTED_MANIFEST_MUTABLE"):
            self.assertIn(needle, prose, f"missing disclosure: {needle}")

    def test_the_nonrequired_smoke_workflow_is_untouched_and_still_nonrequired_shaped(self):
        smoke = "\n".join(code_lines(SMOKE_WORKFLOW))
        self.assertRegex(smoke, r"(?m)^name: foundation-skeleton-ci\s*$")
        self.assertNotIn("pull_request_target", smoke)
        self.assertNotIn("foundation-skeleton-trusted", smoke)


class Fixture:
    """Synthetic local Git remote plus a runner for an extracted workflow
    script. `file://` transport with `allowAnySHA1InWant` mirrors the real
    job's anonymous exact-SHA fetch, for both the trusted commit and the
    candidate head - which are two genuinely different commits here, as they
    are in a real run."""

    REPO_SLUG = "acme/widgets"

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.trusted_sha = ""
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
        # The trusted base-branch snapshot `github.sha` would name. Committed
        # first, so every candidate commit below is a LATER commit and nothing
        # a candidate writes can reach back into this one.
        self.trusted_sha = self.commit_trusted()

    def commit_trusted(self, source: str = VALIDATOR_SOURCE, *, omit: bool = False,
                       symlink_to: str | None = None, as_directory: bool = False) -> str:
        """Commit a trusted snapshot carrying `tools/validate_repo_skeleton.py`
        and return its SHA. `omit` drops the file entirely, `symlink_to`
        replaces it with a mode-120000 entry and `as_directory` stands a
        directory in its place, for the fail-closed cases."""
        path = self.origin / VALIDATOR_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        elif path.is_symlink() or path.exists():
            path.unlink()
        if symlink_to is not None:
            os.symlink(symlink_to, path)
        elif as_directory:
            self._write(f"{VALIDATOR_REL}/placeholder", "stand-in\n")
        elif not omit:
            path.write_text(source, encoding="utf-8")
        return self._commit("trusted base-branch snapshot")

    def _commit(self, message: str) -> str:
        self._git("add", "-A")
        self._git("commit", "-q", "--allow-empty", "-m", message)
        return self._git("rev-parse", "HEAD")

    def commit_skeleton(self, *, omit: tuple[str, ...] = ()) -> str:
        for rel in EXPECTED_REQUIRED_PATHS:
            if rel not in omit:
                self._write(rel)
        return self._commit("candidate head")

    def write_candidate_validator(self, source: str) -> None:
        """Rewrite the candidate's own copy of the validator, uncommitted; the
        next candidate commit carries it. Never an input to the trusted job."""
        self._write(VALIDATOR_REL, source)

    def commit_skeleton_with_validator(self, source: str) -> str:
        """A complete candidate skeleton whose own copy of the validator has
        been rewritten. Nothing about that copy is an input to this job."""
        self.write_candidate_validator(source)
        return self.commit_skeleton()

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

    def commit_with_duplicate_path_entry(self, rel: str) -> str:
        """An fsck-invalid tree holding TWO `ls-tree` records for `rel`: a
        denied 120000 symlink entry followed by an accepted 100644 regular
        blob entry - the exact order (symlink first, blob last) a last-wins
        dict assignment would resolve to PASS. Neither the index nor
        `git mktree` permits a duplicate/unsorted name, so the one directory
        holding the duplicate is built directly via `git hash-object
        --literally`; every ancestor above it up to the root is then rebuilt
        with that subtree's new sha substituted in via ordinary `git mktree`,
        otherwise unchanged. Confined to this fixture's own tmp git dir."""
        base = self.commit_skeleton()
        parent_dir, name = rel.rsplit("/", 1)
        reg_sha = self._git("rev-parse", f"{base}:{rel}")
        sym_sha = subprocess.run(
            ("git", "-C", str(self.origin), "hash-object", "-w", "--stdin"),
            input=b"/etc/passwd", check=True, capture_output=True,
        ).stdout.decode().strip()

        def tree_entries(tree_ish: str) -> list[tuple[str, str, str, str]]:
            out = []
            for line in self._git("ls-tree", tree_ish).splitlines():
                meta, entry_name = line.split("\t", 1)
                mode, otype, sha = meta.split(" ")
                out.append((mode, otype, sha, entry_name))
            return out

        body = b"".join(
            f"{mode} {name}".encode() + b"\0" + bytes.fromhex(sha)
            for mode, sha in (("120000", sym_sha), ("100644", reg_sha))
        )
        for mode, _otype, sha, entry_name in tree_entries(f"{base}:{parent_dir}"):
            if entry_name != name:
                body += f"{mode} {entry_name}".encode() + b"\0" + bytes.fromhex(sha)
        cur_sha = subprocess.run(
            ("git", "-C", str(self.origin), "hash-object", "-t", "tree",
             "--literally", "-w", "--stdin"),
            input=body, check=True, capture_output=True,
        ).stdout.decode().strip()

        cur_rel = parent_dir
        while True:
            up_rel, cur_name = cur_rel.rsplit("/", 1) if "/" in cur_rel else ("", cur_rel)
            lines = [
                f"{mode} {otype} {cur_sha if entry_name == cur_name else sha}\t{entry_name}"
                for mode, otype, sha, entry_name in
                tree_entries(f"{base}:{up_rel}" if up_rel else base)
            ]
            cur_sha = subprocess.run(
                ("git", "-C", str(self.origin), "mktree"),
                input="\n".join(lines) + "\n",
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            if not up_rel:
                break
            cur_rel = up_rel

        new_head = subprocess.run(
            ("git", "-C", str(self.origin), "commit-tree", cur_sha, "-p", base,
             "-m", f"candidate head, duplicate ls-tree record for {rel}"),
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        self._git("update-ref", "refs/heads/main", new_head)
        return new_head

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
        trusted_sha: str | None = None,
    ) -> subprocess.CompletedProcess:
        env = {
            "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""),
            "HOME": str(self.tmp),
            "RUNNER_TEMP": str(self.tmp / "runner-temp"),
            "SERVER_URL": f"file://{self.tmp / 'remote'}",
            "REPO": self.REPO_SLUG if repo is None else repo,
            "HEAD_SHA": head_sha,
            "TRUSTED_SHA": self.trusted_sha if trusted_sha is None else trusted_sha,
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
        self.assertIn("trusted manifest sync OK: 7 required path(s) agree", result.stdout)
        # The trusted commit carries the exact committed validator bytes, so
        # the exact-source pin is satisfied by the real source that ships.
        self.assertIn(
            f"trusted manifest digest OK: sha256 {EXPECTED_MANIFEST_SHA256}", result.stdout
        )
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

    def test_duplicate_ls_tree_record_for_a_required_leaf_denies(self):
        """fsck-invalid tree: a denied 120000 symlink record and an accepted
        100644 blob record for the SAME required path, symlink first. A
        last-wins dict assignment over the ls-tree listing would read the
        later, accepted record and PASS; the fix must deny on the repeated
        key itself, before either record is judged."""
        head = self.fx.commit_with_duplicate_path_entry("backend/app/__init__.py")
        result = self.fx.run(head)
        self.assertDenied(
            result,
            "DUPLICATE_PATH_RECORD",
            "backend/app/__init__.py",
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

    def test_unfetchable_trusted_sha_denies(self):
        head = self.fx.commit_skeleton()
        result = self.fx.run(head, trusted_sha="e" * 40)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("foundation-skeleton-trusted: PASS", result.stdout)

    # --- trusted-manifest sync negatives (BUG-074) ---

    SCREEN_BANNER = "MOD-001 TRUSTED REPOSITORY-SKELETON REQUIRED-PATH SCREEN"

    def assertDeniedBeforeScreening(self, result, *needles: str) -> None:
        """A trusted-manifest failure must deny before a single candidate
        entry is judged - so neither the screen's banner nor its verdict may
        appear in the output."""
        self.assertDenied(result, *needles)
        self.assertNotIn(self.SCREEN_BANNER, result.stdout)
        self.assertNotIn("MISSING_REQUIRED_PATH", result.stdout + result.stderr)

    def test_trusted_manifest_with_an_eighth_path_denies_on_a_green_candidate_tree(self):
        """The drift BUG-074 exists for: the trusted validator grows an eighth
        required path while this workflow's literal still names seven. The
        candidate tree holds all seven and would otherwise screen GREEN, so
        the deny can only come from the sync assertion."""
        trusted = self.fx.commit_trusted(EIGHT_PATH_VALIDATOR)
        head = self.fx.commit_skeleton()
        result = self.fx.run(head, trusted_sha=trusted)
        self.assertDeniedBeforeScreening(result, "TRUSTED_MANIFEST_DESYNC", EIGHTH_PATH)
        # Same candidate head, correctly-synced trusted commit: green. The
        # candidate tree was never the problem.
        self.assertGreen(self.fx.run(head))

    def test_trusted_manifest_missing_denies(self):
        trusted = self.fx.commit_trusted(omit=True)
        head = self.fx.commit_skeleton()
        self.assertDeniedBeforeScreening(
            self.fx.run(head, trusted_sha=trusted),
            "no readable blob at tools/validate_repo_skeleton.py",
        )

    def test_trusted_manifest_that_does_not_parse_denies(self):
        trusted = self.fx.commit_trusted("def broken(:\n    pass\n")
        head = self.fx.commit_skeleton()
        self.assertDeniedBeforeScreening(
            self.fx.run(head, trusted_sha=trusted),
            "TRUSTED_MANIFEST_UNREADABLE",
            "does not parse as Python",
        )

    def test_trusted_manifest_that_is_not_a_literal_denies(self):
        trusted = self.fx.commit_trusted(
            validator_source_with("REQUIRED_PATHS = _discover_required_paths()")
        )
        head = self.fx.commit_skeleton()
        self.assertDeniedBeforeScreening(
            self.fx.run(head, trusted_sha=trusted),
            "TRUSTED_MANIFEST_UNREADABLE",
            "is not a literal",
        )

    def test_duplicate_trusted_manifest_assignment_denies(self):
        """Two top-level REQUIRED_PATHS assignments: the first is correct and
        the second is not, so a first-wins or last-wins read would disagree
        about whether this is synced. Neither is allowed to decide."""
        trusted = self.fx.commit_trusted(
            VALIDATOR_SOURCE + "\n" + manifest_literal((EIGHTH_PATH,)) + "\n"
        )
        head = self.fx.commit_skeleton()
        self.assertDeniedBeforeScreening(
            self.fx.run(head, trusted_sha=trusted),
            "TRUSTED_MANIFEST_UNREADABLE",
            "found 2",
        )

    def test_trusted_manifest_mutated_after_its_literal_denies(self):
        """The reproduced bypass: the trusted validator keeps its ordinary
        seven-path top-level literal - so a first-assignment-only read finds
        exactly one assignment, literal, equal to the workflow's list, and
        reports a clean sync - and then changes it. Every one of these ships a
        runtime manifest the workflow's literal does not match, on a candidate
        tree that holds all seven paths and would otherwise screen GREEN, so a
        PASS here would be a falsely green trusted required check."""
        head = self.fx.commit_skeleton()
        for label, tail in POST_ASSIGNMENT_MUTATIONS.items():
            with self.subTest(mutation=label):
                trusted = self.fx.commit_trusted(VALIDATOR_SOURCE + "\n" + tail + "\n")
                self.assertDeniedBeforeScreening(
                    self.fx.run(head, trusted_sha=trusted),
                    "TRUSTED_MANIFEST_MUTABLE",
                    "REQUIRED_PATHS",
                )

    def test_trusted_manifest_whose_sole_binding_is_not_a_plain_literal_denies(self):
        """No later statement at all - the single binding is annotated,
        conditional or an assignment expression. Each is a shape the static
        literal contract cannot hold the default branch to, so each is refused
        rather than read as if it were a plain top-level literal."""
        head = self.fx.commit_skeleton()
        for label, binding in NON_PLAIN_SOLE_BINDINGS.items():
            with self.subTest(binding=label):
                trusted = self.fx.commit_trusted(validator_source_with(binding))
                self.assertDeniedBeforeScreening(
                    self.fx.run(head, trusted_sha=trusted),
                    "TRUSTED_MANIFEST_MUTABLE",
                    "REQUIRED_PATHS",
                )

    def test_a_mutation_free_trusted_manifest_that_merely_reads_it_passes_the_ast_contract(self):
        """The AST guard must refuse mutation, not ordinary use: reading
        REQUIRED_PATHS, iterating it, and binding other names from it are not
        shape violations, so none of TRUSTED_MANIFEST_MUTABLE/_UNREADABLE/
        _DESYNC may fire.

        This source used to be asserted GREEN. Under the exact-source pin it
        is not, and cannot be: it is not the reviewed bytes. That is the
        intended strengthening - the pin denies drift the shape rules were
        never able to judge - so what is asserted here is the narrower
        property the shape rules own, plus the pin catching the drift."""
        trusted = self.fx.commit_trusted(
            VALIDATOR_SOURCE
            + "\n_COUNT = len(REQUIRED_PATHS)\n"
            + "_SORTED = sorted(REQUIRED_PATHS)\n"
            + "_FIRST = REQUIRED_PATHS[0]\n"
            + "_JOINED = ', '.join(REQUIRED_PATHS)\n"
            + "for _rel in REQUIRED_PATHS:\n    _LAST = _rel\n"
        )
        head = self.fx.commit_skeleton()
        result = self.fx.run(head, trusted_sha=trusted)
        self.assertDeniedBeforeScreening(result, "TRUSTED_MANIFEST_DIGEST_MISMATCH")
        output = result.stdout + result.stderr
        for shape_failure in ("TRUSTED_MANIFEST_MUTABLE", "TRUSTED_MANIFEST_UNREADABLE",
                              "TRUSTED_MANIFEST_DESYNC"):
            self.assertNotIn(shape_failure, output, shape_failure)
        # No "OK" line is printed for a job that denies: the sync and digest
        # confirmations are emitted only once every trusted-manifest check has
        # passed, so a denial never carries a partial pass claim.
        self.assertNotIn("trusted manifest sync OK", result.stdout)

    # --- exact-source digest pin (BUG-074 residual) ---

    def test_ast_invisible_trusted_manifest_drift_denies_on_the_pinned_digest(self):
        """The residual bypass, reproduced: a trusted validator that keeps its
        plain seven-path top-level literal and mutates it through an alias or
        `globals()` passes every static check - one literal, no AST-visible
        rebinding or mutation, literal equal to the workflow's seven - on a
        candidate tree that holds all seven paths, which would be a falsely
        green trusted required check. A comment-only edit is the same class
        with no semantic change at all. Each must deny on the exact-source
        digest, before any candidate entry is judged, and must NOT be
        misreported as a shape failure."""
        head = self.fx.commit_skeleton()
        for label, tail in DIGEST_ONLY_DRIFT.items():
            with self.subTest(drift=label):
                trusted = self.fx.commit_trusted(VALIDATOR_SOURCE + "\n" + tail + "\n")
                result = self.fx.run(head, trusted_sha=trusted)
                self.assertDeniedBeforeScreening(
                    result,
                    "TRUSTED_MANIFEST_DIGEST_MISMATCH",
                    f"pinned {EXPECTED_MANIFEST_SHA256}",
                )
                output = result.stdout + result.stderr
                self.assertNotIn("TRUSTED_MANIFEST_MUTABLE", output)
                self.assertNotIn("TRUSTED_MANIFEST_DESYNC", output)
                # Same candidate head, reviewed trusted bytes: green. The
                # candidate tree was never the problem.
                self.assertGreen(self.fx.run(head))

    def test_candidate_only_validator_edit_cannot_affect_the_trusted_digest(self):
        """The candidate rewrites its own copy of the validator - including
        the alias mutation that the digest refuses on the trusted side. The
        trusted commit still carries the reviewed bytes, so the pin reports
        the pinned digest and the job is green: the candidate copy is never
        read, hashed or consulted."""
        head = self.fx.commit_skeleton_with_validator(
            EIGHT_PATH_VALIDATOR
            + "\nALIAS = REQUIRED_PATHS\nALIAS.append('backend/new_required.py')\n"
        )
        result = self.fx.run(head)
        self.assertGreen(result)
        self.assertIn(
            f"trusted manifest digest OK: sha256 {EXPECTED_MANIFEST_SHA256}", result.stdout
        )
        self.assertNotIn("TRUSTED_MANIFEST_DIGEST_MISMATCH", result.stdout + result.stderr)

    def test_symlinked_trusted_manifest_denies_even_when_its_target_text_would_sync(self):
        """A mode-120000 entry whose blob content - the link target - is a
        correctly-synced manifest. Reading content alone would PASS; the entry
        must be refused on its mode."""
        trusted = self.fx.commit_trusted(symlink_to=SYNCED_SYMLINK_TARGET)
        head = self.fx.commit_skeleton()
        self.assertDeniedBeforeScreening(
            self.fx.run(head, trusted_sha=trusted),
            "TRUSTED_MANIFEST_UNREADABLE",
            "not a regular file (mode 120000 type blob)",
        )

    def test_directory_standing_in_for_the_trusted_manifest_denies(self):
        trusted = self.fx.commit_trusted(as_directory=True)
        head = self.fx.commit_skeleton()
        self.assertDeniedBeforeScreening(
            self.fx.run(head, trusted_sha=trusted),
            "no readable blob at tools/validate_repo_skeleton.py",
        )

    def test_duplicate_tree_record_for_the_trusted_manifest_denies(self):
        """An fsck-invalid trusted tree holding TWO records for the manifest
        path - a 120000 symlink and a 100644 blob. Resolving either one would
        be a guess about which manifest the default branch really ships."""
        head = self.fx.commit_skeleton()
        trusted = self.fx.commit_with_duplicate_path_entry(VALIDATOR_REL)
        self.assertDeniedBeforeScreening(
            self.fx.run(head, trusted_sha=trusted),
            "TRUSTED_MANIFEST_UNREADABLE",
            "exactly one tree entry",
            "found 2",
        )

    # --- the candidate's own copy of the validator is still not an input ---

    def test_candidate_validator_rewrite_cannot_force_a_sync_denial(self):
        """The candidate ships an eighth required path in ITS validator. The
        trusted commit still says seven, the candidate tree holds those seven,
        and the job is green: the candidate's copy was never read."""
        head = self.fx.commit_skeleton_with_validator(EIGHT_PATH_VALIDATOR)
        result = self.fx.run(head)
        self.assertGreen(result)
        self.assertIn("trusted manifest sync OK", result.stdout)

    def test_candidate_validator_rewrite_cannot_mask_a_screen_denial(self):
        """The mirror case: the candidate guts its own manifest AND drops a
        required path. The sync still passes (it reads the trusted commit) and
        the screen still denies on the path actually missing from the head."""
        self.fx.write_candidate_validator(validator_source_with("REQUIRED_PATHS = []"))
        head = self.fx.commit_skeleton(omit=("backend/tests/contract/__init__.py",))
        result = self.fx.run(head)
        self.assertDenied(result, "MISSING_REQUIRED_PATH", "1 of 7")
        self.assertIn("trusted manifest sync OK", result.stdout)
        self.assertNotIn("TRUSTED_MANIFEST", result.stderr)

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
        # The candidate's gutted validator is neither read nor reported on:
        # the only lines naming that file are the sync and the exact-source
        # pin against the TRUSTED commit, both of which passed on the
        # untouched manifest there.
        mentions = [
            line for line in (result.stdout + result.stderr).splitlines()
            if "validate_repo_skeleton" in line
        ]
        self.assertEqual(
            mentions,
            ["trusted manifest sync OK: 7 required path(s) agree with "
             "tools/validate_repo_skeleton.py at the trusted commit",
             "trusted manifest digest OK: sha256 "
             f"{EXPECTED_MANIFEST_SHA256} matches the pinned exact-source "
             "digest for tools/validate_repo_skeleton.py"],
        )

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
