"""Tests for .github/workflows/permission-gate-d1.yml (MOD-001, GOV-01-R04 -
ADR-014 D1 four-state CI disposition of TSD §24.1 gate 4, permission lint).

Deterministic and offline. Three layers:

1. Static assertions over the committed workflow text - the trust-boundary
   shape ADR-014 D1 and the OSV-gate precedent require (trusted default-branch
   definition, trusted executables AND trusted self-test fixtures, inert
   candidate contracts, no masking, stable required-check name).
2. BEHAVIORAL execution of the workflow step's own bash script against a
   synthetic local git remote, with a STUB adapter planted in the trusted
   snapshot so every exit code and report shape can be driven deterministically
   without a network. This layer proves the three things a file-level reading
   cannot: that the bytes which execute come from the trusted snapshot, that a
   candidate edit to any gate byte cannot produce green, and that only a fully
   qualified NOT_APPLICABLE/4 is non-blocking.
3. BEHAVIORAL execution of the same script with the REAL adapter, the REAL
   shared gate module and the REAL committed self-test fixtures in the trusted
   snapshot, over real candidate contract inputs. This is what proves the
   whole job - gate run plus D1 condition 3's in-process fixture self-test -
   actually runs in ONE job, which is the thing the prior bounded
   implementation could not claim because nothing invoked the adapter.

No network is touched: `file://` transport with `allowAnySHA1InWant` mirrors
how the real job fetches an exact SHA anonymously from the public repository.
`python3` is shimmed onto PATH so the runner-version assertion in the script
sees this interpreter rather than the host default.

Parent decision: knowledge/04-Decisions/
ADR-014-vacuous-gate-ci-disposition-and-screen-contract-staged-binding.md (D1)
"""
from __future__ import annotations

import json
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
sys.path.insert(0, str(TOOLS))
from validate_permission_gate_d1 import (
    D1_EXIT_CODES,
    NOT_APPLICABLE,
    REASON_REAL_OPERATIONS_CONFORM,
    REASON_ZERO_REAL_OPERATIONS,
    VIOLATION_CODE,
)
from validate_workflow_trust import evaluate_workflow_text

WORKFLOW_REL = ".github/workflows/permission-gate-d1.yml"
ADAPTER_REL = "tools/validate_permission_gate_d1.py"
GATES_REL = "tools/validate_architecture_gates.py"
FIXTURE_REL = "tools/fixtures/permission-gate-d1"
REGISTRY_REL = "contracts/permissions/registry.json"
OPENAPI_REL = "contracts/openapi"

FIXTURE_FILES = (
    f"{FIXTURE_REL}/conforming/registry.json",
    f"{FIXTURE_REL}/conforming/openapi/api.json",
    f"{FIXTURE_REL}/violating/registry.json",
    f"{FIXTURE_REL}/violating/openapi/api.json",
)
TRUSTED_SET = (WORKFLOW_REL, ADAPTER_REL, GATES_REL) + FIXTURE_FILES

WORKFLOW = REPO / WORKFLOW_REL

# Printed to stderr by the stub planted in the TRUSTED snapshot. Its presence
# is the positive proof the executed bytes came from the trusted snapshot.
TRUSTED_MARKER = "VEYRO-TEST-TRUSTED-ADAPTER-RAN"
# Printed by the stub planted at the CANDIDATE head. Its absence everywhere is
# the negative proof candidate code is never executed.
CANDIDATE_MARKER = "VEYRO-TEST-CANDIDATE-ADAPTER-RAN"

# Trusted stub adapter: deterministic, offline, stdlib-only. It echoes the
# three paths it was handed (so a test can prove --fixture-dir points into the
# TRUSTED tree and the inputs point into the CANDIDATE tree) and then emits
# whatever the candidate registry's `_stub` directive asks for. Driving the
# report through candidate DATA is deliberate: it keeps the stub itself fixed
# while every disposition case varies only inert bytes.
TRUSTED_STUB = f'''#!/usr/bin/env python3
import json
import sys

print("{TRUSTED_MARKER}", file=sys.stderr)
args = sys.argv[1:]


def opt(name):
    return args[args.index(name) + 1] if name in args else "<absent>"


registry = opt("--registry")
print("stub registry " + registry, file=sys.stderr)
print("stub openapi " + opt("--openapi-dir"), file=sys.stderr)
print("stub fixtures " + opt("--fixture-dir"), file=sys.stderr)

with open(registry, encoding="utf-8") as handle:
    directive = json.load(handle)["_stub"]
emit = directive.get("emit")
if emit is not None:
    sys.stdout.write(emit if isinstance(emit, str) else json.dumps(emit))
raise SystemExit(directive["exit"])
'''

# Malicious candidate stub: always a qualified-looking green. This is exactly
# the suppression a `pull_request` trigger or a `$head/...` invocation permits.
CANDIDATE_STUB = f'''#!/usr/bin/env python3
import sys

print("{CANDIDATE_MARKER}", file=sys.stderr)
sys.stdout.write({json.dumps(json.dumps({
    "state": "NOT_APPLICABLE",
    "reason": "ZERO_REAL_OPERATIONS",
    "real_operations": 0,
    "self_test": {
        "satisfied": True,
        "conforming_status": "PASS",
        "violating_status": "FAIL",
        "violating_codes": ["UNREGISTERED_PERMISSION"],
    },
}))})
raise SystemExit(4)
'''

PLACEHOLDER_GATES = "# placeholder for the shared architecture-gate module\n"
PLACEHOLDER_FIXTURE = '{"version": 2, "permissions": {}}\n'

EMPTY_REGISTRY_TEXT = '{"version": 2, "permissions": {}}\n'


def qualified_na(**overrides) -> dict:
    """The exact report shape ADR-014 D1 licenses as non-blocking."""
    report = {
        "state": NOT_APPLICABLE,
        "reason": REASON_ZERO_REAL_OPERATIONS,
        "real_operations": 0,
        "gate_status": "INCONCLUSIVE",
        "gate_codes": ["PERMISSION_GATE_VACUOUS"],
        "self_test": {
            "satisfied": True,
            "conforming_status": "PASS",
            "violating_status": "FAIL",
            "violating_codes": [VIOLATION_CODE],
            "detail": "stub",
        },
        "notes": [],
    }
    self_test = overrides.pop("self_test", None)
    report.update(overrides)
    if self_test is not None:
        report["self_test"].update(self_test)
    return report


def qualified_pass(**overrides) -> dict:
    report = qualified_na()
    report.update({
        "state": "PASS",
        "reason": REASON_REAL_OPERATIONS_CONFORM,
        "real_operations": 2,
        "gate_status": "PASS",
        "gate_codes": [],
    })
    self_test = overrides.pop("self_test", None)
    report.update(overrides)
    if self_test is not None:
        report["self_test"].update(self_test)
    return report


def directive(exit_code: int, emit) -> str:
    """Candidate registry bytes that steer the trusted stub."""
    return json.dumps({"_stub": {"exit": exit_code, "emit": emit}})


def code_lines() -> list[str]:
    return [
        ln
        for ln in WORKFLOW.read_text(encoding="utf-8").splitlines()
        if not ln.lstrip().startswith("#")
    ]


def extract_run_script() -> str:
    """Return the single `run: |` block body from the workflow, dedented.

    Indentation-based, so the test needs no YAML dependency (none is installed
    in this environment) and parses exactly the bytes CI would execute.
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


def extract_verifier_source() -> str:
    """Return the step-6 heredoc body - the trusted disposition verifier."""
    script = extract_run_script()
    opener = "<<'PY'\n"
    start = script.index(opener) + len(opener)
    end = script.index("\nPY\n", start)
    return script[start:end] + "\n"


# --- layer 1: static shape -----------------------------------------------------


class WorkflowShapeTests(unittest.TestCase):
    def setUp(self):
        self.code = "\n".join(code_lines())
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_trusted_executables_and_fixtures_resolve_from_the_trusted_snapshot(self):
        self.assertRegex(
            self.code,
            r'(?m)^\s*python3 -I "\$trusted/\$adapter_rel" \\\s*$',
            "the adapter must execute from the trusted snapshot",
        )
        self.assertRegex(self.code, r'(?m)^\s*--fixture-dir "\$trusted/\$fixture_rel" \\\s*$')
        self.assertRegex(self.code, r'(?m)^\s*--registry "\$cand/\$registry_rel" \\\s*$')
        self.assertRegex(self.code, r'(?m)^\s*--openapi-dir "\$cand/\$openapi_rel" \\\s*$')
        # Candidate bytes must never supply an executable or a fixture.
        self.assertNotIn('"$cand/$adapter_rel"', self.code)
        self.assertNotIn('"$cand/$fixture_rel"', self.code)
        self.assertNotIn("$head/", self.code)

    def test_declared_path_variables_match_the_repository(self):
        for var, rel in (("adapter_rel", ADAPTER_REL), ("gates_rel", GATES_REL),
                         ("fixture_rel", FIXTURE_REL), ("registry_rel", REGISTRY_REL),
                         ("openapi_rel", OPENAPI_REL), ("workflow", WORKFLOW_REL)):
            with self.subTest(var=var):
                self.assertRegex(self.code, rf'(?m)^\s*{var}="{re.escape(rel)}"\s*$')
        for rel in TRUSTED_SET + (REGISTRY_REL,):
            with self.subTest(path=rel):
                self.assertTrue((REPO / rel).is_file(), f"{rel} is missing from the working tree")
        self.assertTrue((REPO / OPENAPI_REL).is_dir())

    def test_trusted_sha_anchors_the_executables(self):
        self.assertRegex(self.code, r"(?m)^\s*TRUSTED_SHA: \$\{\{ github\.sha \}\}\s*$")
        self.assertIn('git -C "$trusted" fetch -q --no-tags --depth=1 origin "$TRUSTED_SHA"',
                      self.code)
        self.assertIn('[[ "$(git -C "$trusted" rev-parse HEAD)" == "$TRUSTED_SHA" ]]', self.code)
        self.assertRegex(self.code,
                         r"(?m)^\s*HEAD_SHA: \$\{\{ github\.event\.pull_request\.head\.sha \}\}\s*$")

    def test_event_is_pull_request_target_on_the_default_branch_only(self):
        self.assertRegex(self.code, r"(?m)^on:\s*$")
        self.assertRegex(self.code, r"(?m)^  pull_request_target:\s*$")
        self.assertNotRegex(self.code, r"(?m)^  pull_request:\s*$")
        self.assertRegex(self.code, r"(?m)^      - main\s*$")
        self.assertNotIn("paths:", self.code)
        self.assertNotIn("paths-ignore:", self.code)
        self.assertNotIn("workflow_dispatch", self.code)
        self.assertNotIn("schedule:", self.code)
        self.assertNotIn("workflow_run:", self.code)

    def test_tamper_check_covers_every_trusted_byte_including_the_fixtures(self):
        for rel in TRUSTED_SET:
            with self.subTest(path=rel):
                self.assertIn(rel.replace(FIXTURE_REL, "$fixture_rel")
                              if rel.startswith(FIXTURE_REL) else rel,
                              self.code)
        self.assertIn('for f in $trusted_set; do', self.code)
        self.assertIn('cmp -s - "$trusted/$f"', self.code)
        self.assertIn("the gate's own bytes must come from the reviewed default branch",
                      self.code)

    def test_candidate_inputs_are_screened_and_materialized_as_inert_data(self):
        self.assertIn('require_regular_blob "$registry_rel"', self.code)
        self.assertIn('require_regular_blob "$entry"', self.code)
        self.assertIn("refused head tree entry mode $mode at '$1' (symlink/gitlink/irregular)",
                      self.code)
        self.assertIn('[[ ! -L "$cand/$registry_rel" ]] || deny', self.code)
        self.assertIn('[[ "$openapi_count" -gt 0 ]]', self.code)

    def test_required_status_name_is_stable(self):
        self.assertRegex(self.code, r"(?m)^name: permission-gate-d1\s*$")
        self.assertRegex(self.code, r"(?m)^    name: permission-gate-d1\s*$")
        self.assertRegex(self.code, r"(?m)^  permission-gate-d1:\s*$")

    def test_no_actions_no_secrets_no_token_permissions_no_masking(self):
        self.assertNotRegex(self.code, r"^\s*-?\s*uses:", "no action references")
        self.assertNotIn("secrets.", self.code)
        self.assertRegex(self.code, r"(?m)^permissions: \{\}$")
        self.assertIn("set -euo pipefail", self.code)
        for masking in ("|| true", "|| :", "; true", "continue-on-error",
                        "if: always()", "set +e"):
            with self.subTest(masking=masking):
                self.assertNotIn(masking, self.code)
        # The one tolerated nonzero capture records the code, never discards it.
        self.assertIn("|| rc=$?", self.code)

    def test_disposition_verifier_is_the_last_command_of_the_last_step(self):
        self.assertTrue(extract_run_script().rstrip().endswith("PY"))
        self.assertEqual(self.code.count("<<'PY'"), 1)

    def test_workflow_exit_map_matches_the_adapter_contract(self):
        source = extract_verifier_source()
        match = re.search(r"STATE_EXIT = (\{[^}]*\})", source)
        self.assertIsNotNone(match, "the verifier must declare an explicit state/exit map")
        declared = json.loads(match.group(1).replace("'", '"'))
        self.assertEqual(declared, D1_EXIT_CODES)
        self.assertIn(f'VIOLATION_CODE = "{VIOLATION_CODE}"', source)

    def test_verifier_rejects_a_boolean_masquerading_as_a_count(self):
        source = extract_verifier_source()
        self.assertIn("isinstance(value, int) and not isinstance(value, bool)", source)

    def test_verifier_compiles_and_is_import_free(self):
        source = extract_verifier_source()
        compile(source, "<verifier>", "exec")
        self.assertNotIn("subprocess", source)
        for line in source.splitlines():
            if line.startswith("import "):
                self.assertIn(line.strip(), ("import json", "import sys"))

    def test_not_applicable_is_never_described_as_a_pass(self):
        self.assertIn("NOT a gate-4 PASS", self.text)
        self.assertIn("NOT architecture-gate credit", self.text)
        self.assertIn("unqualified NOT_APPLICABLE is never non-blocking", self.code)

    def test_inertness_and_activation_preconditions_are_disclosed(self):
        for needle in ("INERT: authored locally, never committed to a",
                       "Activation preconditions",
                       "UNVERIFIED DEPENDENCY, anonymous fetch",
                       "UNVERIFIED DEPENDENCY, fork-PR fetch",
                       "Same-name candidate check-run spoofing is NOT solved here",
                       "every open PR must rebase",
                       "temporarily remove"):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.text)

    def test_known_limitations_are_disclosed_not_implied_away(self):
        for needle in ("All seven are\n#     UNTRACKED local candidates today",
                       "EVERY pull request that edits any\n#     architecture gate fails it",
                       "is not a repo-wide\n#     inventory of API surfaces",
                       "duplicate-`ADR-009`-record approval-resolution defect",
                       "C05 aggregate that must consume the\n#     four states"):
            with self.subTest(needle=needle[:40]):
                self.assertIn(needle, self.text)

    def test_standing_workflow_trust_lint_allows_this_file(self):
        self.assertEqual(evaluate_workflow_text(self.text, name=WORKFLOW_REL), [])

    def test_run_script_is_valid_bash(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "gate.sh"
            script.write_text(extract_run_script(), encoding="utf-8")
            result = subprocess.run(["bash", "-n", str(script)],
                                    check=False, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_workflow_yaml_block_structure_is_well_formed(self):
        """No PyYAML in this environment, so assert the structural invariants a
        parse would otherwise give: one job, one step, one run block, and a
        heredoc whose terminator sits at the block-scalar indent."""
        lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
        self.assertEqual(sum(1 for ln in lines if re.fullmatch(r"jobs:\s*", ln)), 1)
        self.assertEqual(sum(1 for ln in lines if re.fullmatch(r"\s*steps:\s*", ln)), 1)
        self.assertEqual(sum(1 for ln in lines if re.fullmatch(r"\s*- name: .+", ln)), 1)
        run_idx = [i for i, ln in enumerate(lines) if re.fullmatch(r"\s*run: \|\s*", ln)]
        self.assertEqual(len(run_idx), 1)
        body_indent = len(lines[run_idx[0] + 1]) - len(lines[run_idx[0] + 1].lstrip())
        terminators = [ln for ln in lines if ln.rstrip() and ln.strip() == "PY"]
        self.assertEqual(len(terminators), 1)
        self.assertEqual(len(terminators[0]) - len(terminators[0].lstrip()), body_indent)
        # Every non-blank line of the block scalar is at least as indented as
        # its first line, or YAML would end the scalar early.
        for ln in lines[run_idx[0] + 1:]:
            if not ln.strip():
                continue
            if (len(ln) - len(ln.lstrip())) < body_indent:
                break
        else:
            return
        self.assertEqual(ln.strip(), "", f"block scalar ends early at {ln!r}")


# --- behavioral harness --------------------------------------------------------


class GateFixture:
    """A synthetic local remote with a trusted default-branch commit and a
    candidate head commit, plus a runner for the workflow's own bash script."""

    def __init__(self, tmp: Path, *, real: bool = False):
        self.tmp = tmp
        self.real = real
        self.origin = tmp / "origin"
        self.script = tmp / "gate.sh"
        self.script.write_text(extract_run_script(), encoding="utf-8")
        self.script.chmod(0o755)
        self.bin = tmp / "bin"
        self.bin.mkdir()
        # The script asserts `python3` is 3.11+. The host default may be older,
        # so pin the interpreter running these tests onto PATH.
        os.symlink(sys.executable, self.bin / "python3")

    def _git(self, *args: str) -> str:
        return subprocess.run(
            ("git", "-C", str(self.origin), *args),
            check=True, capture_output=True, text=True,
        ).stdout.strip()

    def _ensure(self, rel: str) -> Path:
        path = self.origin / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _write(self, rel: str, text: str) -> None:
        self._ensure(rel).write_text(text, encoding="utf-8")

    def build_trusted(self) -> str:
        self.origin.mkdir(parents=True)
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.email", "test@example.invalid")
        self._git("config", "user.name", "veyro test")
        self._git("config", "uploadpack.allowAnySHA1InWant", "true")
        self._git("config", "uploadpack.allowReachableSHA1InWant", "true")
        shutil.copyfile(WORKFLOW, self._ensure(WORKFLOW_REL))
        if self.real:
            shutil.copyfile(REPO / ADAPTER_REL, self._ensure(ADAPTER_REL))
            shutil.copyfile(REPO / GATES_REL, self._ensure(GATES_REL))
            for rel in FIXTURE_FILES:
                shutil.copyfile(REPO / rel, self._ensure(rel))
            self._write(REGISTRY_REL, EMPTY_REGISTRY_TEXT)
        else:
            self._write(ADAPTER_REL, TRUSTED_STUB)
            self._write(GATES_REL, PLACEHOLDER_GATES)
            for rel in FIXTURE_FILES:
                self._write(rel, PLACEHOLDER_FIXTURE)
            self._write(REGISTRY_REL, directive(D1_EXIT_CODES[NOT_APPLICABLE],
                                                qualified_na()))
        self._write(f"{OPENAPI_REL}/.gitkeep", "")
        self._git("add", "-A")
        self._git("commit", "-qm", "trusted default-branch snapshot")
        return self._git("rev-parse", "HEAD")

    def build_candidate(self, *, registry: str | None = None,
                        adapter_text: str | None = None,
                        gates_text: str | None = None,
                        fixture_edit: tuple[str, str] | None = None,
                        workflow_suffix: str = "",
                        drop: tuple[str, ...] = (),
                        openapi: dict[str, str] | None = None,
                        extra_files: dict[str, str] | None = None,
                        symlinks: dict[str, str] | None = None,
                        gitlinks: tuple[str, ...] = ()) -> str:
        if registry is not None:
            self._write(REGISTRY_REL, registry)
        if adapter_text is not None:
            self._write(ADAPTER_REL, adapter_text)
        if gates_text is not None:
            self._write(GATES_REL, gates_text)
        if fixture_edit is not None:
            self._write(*fixture_edit)
        for rel, text in (openapi or {}).items():
            self._write(f"{OPENAPI_REL}/{rel}", text)
        for rel, text in (extra_files or {}).items():
            self._write(rel, text)
        for rel in drop:
            self._git("rm", "-q", "-f", rel)
        for rel, target in (symlinks or {}).items():
            path = self._ensure(rel)
            if path.exists() or path.is_symlink():
                path.unlink()
            os.symlink(target, path)
        if workflow_suffix:
            path = self.origin / WORKFLOW_REL
            path.write_text(path.read_text(encoding="utf-8") + workflow_suffix,
                            encoding="utf-8")
        self._git("add", "-A")
        for rel in gitlinks:
            self._git("update-index", "--add", "--cacheinfo",
                      f"160000,{self._git('rev-parse', 'HEAD')},{rel}")
        self._git("commit", "-q", "--allow-empty", "-m", "candidate head")
        return self._git("rev-parse", "HEAD")

    def run(self, trusted_sha: str, head_sha: str, *,
            path_prefix: Path | None = None) -> subprocess.CompletedProcess:
        env = {
            "PATH": f"{path_prefix or self.bin}:{os.environ.get('PATH', '')}",
            "HOME": str(self.tmp),
            "REPO_URL": f"file://{self.origin}",
            "TRUSTED_SHA": trusted_sha,
            "HEAD_SHA": head_sha,
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        }
        return subprocess.run(
            ["bash", str(self.script)],
            check=False, env=env, cwd=str(self.tmp),
            capture_output=True, text=True, timeout=300,
        )


class _BehaviorBase(unittest.TestCase):
    real = False

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="veyro-pgd1-")
        self.addCleanup(self._tmp.cleanup)
        self.fx = GateFixture(Path(self._tmp.name), real=self.real)
        self.trusted = self.fx.build_trusted()

    def assertDenied(self, result, needle: str) -> None:
        combined = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0,
                            f"expected nonzero\nSTDOUT:{result.stdout}\nSTDERR:{result.stderr}")
        self.assertIn(needle, combined)
        self.assertNotIn(CANDIDATE_MARKER, combined, "candidate code must never execute")

    def assertGreen(self, result) -> None:
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn(CANDIDATE_MARKER, result.stdout + result.stderr)


# --- layer 2: stub-driven trust boundary and disposition -----------------------


class DispositionBehaviorTests(_BehaviorBase):
    """Every exit code and report shape, driven through the trusted stub."""

    def test_qualified_not_applicable_is_non_blocking_and_labelled(self):
        head = self.fx.build_candidate(
            registry=directive(4, qualified_na()))
        result = self.fx.run(self.trusted, head)
        self.assertGreen(result)
        self.assertIn(TRUSTED_MARKER, result.stderr)
        self.assertIn("PERMISSION_GATE_D1_STATE=NOT_APPLICABLE "
                      "reason=ZERO_REAL_OPERATIONS real_operations=0", result.stdout)
        self.assertIn("NON-BLOCKING under ADR-014 D1 conditions 1-3", result.stdout)
        self.assertIn("NOT a gate-4 PASS", result.stdout)

    def test_self_test_fixtures_are_taken_from_the_trusted_snapshot(self):
        head = self.fx.build_candidate(registry=directive(4, qualified_na()))
        result = self.fx.run(self.trusted, head)
        self.assertGreen(result)
        self.assertRegex(result.stderr, rf"stub fixtures \S*/trusted/{re.escape(FIXTURE_REL)}\b")
        self.assertRegex(result.stderr, rf"stub registry \S*/candidate/{re.escape(REGISTRY_REL)}\b")
        self.assertRegex(result.stderr, rf"stub openapi \S*/candidate/{re.escape(OPENAPI_REL)}\b")

    def test_pass_is_green(self):
        head = self.fx.build_candidate(registry=directive(0, qualified_pass()))
        result = self.fx.run(self.trusted, head)
        self.assertGreen(result)
        self.assertIn("PERMISSION_GATE_D1_STATE=PASS reason=REAL_OPERATIONS_CONFORM "
                      "real_operations=2", result.stdout)

    def test_fail_blocks(self):
        head = self.fx.build_candidate(registry=directive(
            1, {"state": "FAIL", "reason": "GATE_VIOLATIONS", "real_operations": 3,
                "self_test": {"satisfied": True}}))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "gate 4 reported FAIL")

    def test_error_blocks(self):
        head = self.fx.build_candidate(registry=directive(
            2, {"state": "ERROR", "reason": "GATE_INPUT_ERROR", "real_operations": 0,
                "self_test": {"satisfied": False}}))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "gate 4 reported ERROR")

    def test_not_applicable_without_the_self_test_blocks(self):
        head = self.fx.build_candidate(registry=directive(
            4, qualified_na(self_test={"satisfied": False})))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "self_test.satisfied is not true")

    def test_not_applicable_whose_violating_fixture_did_not_fail_blocks(self):
        head = self.fx.build_candidate(registry=directive(
            4, qualified_na(self_test={"violating_status": "PASS"})))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "self_test.violating_status is 'PASS', expected FAIL")

    def test_not_applicable_whose_conforming_fixture_did_not_pass_blocks(self):
        head = self.fx.build_candidate(registry=directive(
            4, qualified_na(self_test={"conforming_status": "ERROR"})))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "self_test.conforming_status is 'ERROR', expected PASS")

    def test_not_applicable_without_the_permission_code_blocks(self):
        head = self.fx.build_candidate(registry=directive(
            4, qualified_na(self_test={"violating_codes": ["PERMISSION_GATE_VACUOUS"]})))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, f"self_test.violating_codes does not cite {VIOLATION_CODE}")

    def test_not_applicable_with_a_wrong_reason_blocks(self):
        head = self.fx.build_candidate(registry=directive(
            4, qualified_na(reason="SELF_TEST_NOT_SATISFIED")))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "expected ZERO_REAL_OPERATIONS")

    def test_not_applicable_with_real_items_in_scope_blocks(self):
        head = self.fx.build_candidate(registry=directive(
            4, qualified_na(real_operations=5)))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "real_operations is 5, expected 0")

    def test_not_applicable_with_a_boolean_count_blocks(self):
        """JSON `false` must not read as the integer 0."""
        head = self.fx.build_candidate(registry=directive(
            4, qualified_na(real_operations=False)))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "real_operations is False, expected 0")

    def test_pass_without_a_satisfied_self_test_blocks(self):
        head = self.fx.build_candidate(registry=directive(
            0, qualified_pass(self_test={"satisfied": False})))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "unqualified PASS")

    def test_pass_with_zero_real_operations_blocks(self):
        head = self.fx.build_candidate(registry=directive(
            0, qualified_pass(real_operations=0)))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "real_operations is 0, expected at least 1")

    def test_exit_code_contradicting_the_reported_state_blocks(self):
        head = self.fx.build_candidate(registry=directive(0, qualified_na()))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "adapter exit 0 contradicts reported state NOT_APPLICABLE")

    def test_zero_exit_with_a_state_outside_the_four_blocks(self):
        head = self.fx.build_candidate(registry=directive(
            0, qualified_na(state="SKIPPED")))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "outside the ADR-014 D1 four-state set")

    def test_unknown_exit_code_blocks(self):
        head = self.fx.build_candidate(registry=directive(3, qualified_na()))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "adapter exit 3 contradicts reported state NOT_APPLICABLE")

    def test_missing_report_blocks(self):
        head = self.fx.build_candidate(registry=directive(0, None))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "the adapter produced no report")

    def test_empty_report_blocks(self):
        head = self.fx.build_candidate(registry=directive(4, ""))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "the adapter produced no report")

    def test_malformed_non_json_report_blocks(self):
        head = self.fx.build_candidate(registry=directive(4, "NOT JSON AT ALL"))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "adapter report is unreadable or not JSON")

    def test_json_scalar_report_blocks(self):
        head = self.fx.build_candidate(registry=directive(4, "4"))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "adapter report is not a JSON object")

    def test_report_without_a_self_test_object_blocks(self):
        report = qualified_na()
        report.pop("self_test")
        head = self.fx.build_candidate(registry=directive(4, report))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "carries no self_test object")


class TamperBehaviorTests(_BehaviorBase):
    """A candidate must not be able to supply, weaken, or delete a gate byte."""

    def _green_registry(self) -> str:
        return directive(4, qualified_na())

    def test_candidate_adapter_edit_cannot_produce_green(self):
        head = self.fx.build_candidate(registry=self._green_registry(),
                                       adapter_text=CANDIDATE_STUB)
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, f"candidate changed {ADAPTER_REL}")

    def test_candidate_adapter_deletion_cannot_produce_green(self):
        head = self.fx.build_candidate(registry=self._green_registry(),
                                       drop=(ADAPTER_REL,))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, f"has no {ADAPTER_REL}")

    def test_candidate_shared_gate_module_edit_cannot_produce_green(self):
        head = self.fx.build_candidate(registry=self._green_registry(),
                                       gates_text="# weakened\n")
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, f"candidate changed {GATES_REL}")

    def test_candidate_workflow_edit_cannot_produce_green(self):
        head = self.fx.build_candidate(registry=self._green_registry(),
                                       workflow_suffix="\n# candidate tampering\n")
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, f"candidate changed {WORKFLOW_REL}")

    def test_candidate_workflow_deletion_cannot_produce_green(self):
        head = self.fx.build_candidate(registry=self._green_registry(),
                                       drop=(WORKFLOW_REL,))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, f"has no {WORKFLOW_REL}")

    def test_candidate_cannot_neuter_the_violating_self_test_fixture(self):
        head = self.fx.build_candidate(
            registry=self._green_registry(),
            fixture_edit=(f"{FIXTURE_REL}/violating/openapi/api.json", "{}\n"))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, f"candidate changed {FIXTURE_REL}/violating/openapi/api.json")

    def test_candidate_cannot_delete_a_self_test_fixture(self):
        head = self.fx.build_candidate(
            registry=self._green_registry(),
            drop=(f"{FIXTURE_REL}/conforming/registry.json",))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, f"has no {FIXTURE_REL}/conforming/registry.json")

    def test_candidate_symlinked_registry_is_refused(self):
        head = self.fx.build_candidate(registry=self._green_registry(),
                                       symlinks={REGISTRY_REL: "/etc/passwd"})
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "refused head tree entry mode 120000")

    def test_candidate_gitlink_under_the_openapi_root_is_refused(self):
        head = self.fx.build_candidate(registry=self._green_registry(),
                                       gitlinks=(f"{OPENAPI_REL}/vendored",))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "refused head tree entry mode 160000")

    def test_candidate_deleting_the_registry_is_refused(self):
        head = self.fx.build_candidate(drop=(REGISTRY_REL,))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, f"has no {REGISTRY_REL}")

    def test_candidate_deleting_the_openapi_root_is_refused(self):
        head = self.fx.build_candidate(registry=self._green_registry(),
                                       drop=(f"{OPENAPI_REL}/.gitkeep",))
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "ADR-014 D1 condition 1 requires the OpenAPI input to exist")

    def test_trusted_fixture_tree_is_exempt_from_the_shadowing_check(self):
        """The fixtures live under their own `openapi/` directory. If 3a did
        not exempt the four pinned paths the gate would deny every PR."""
        head = self.fx.build_candidate(registry=self._green_registry())
        result = self.fx.run(self.trusted, head)
        self.assertGreen(result)
        self.assertNotIn("unscanned OpenAPI directory entry", result.stderr)

    def test_unpinned_extra_file_under_the_fixture_root_is_refused(self):
        head = self.fx.build_candidate(
            registry=self._green_registry(),
            extra_files={f"{FIXTURE_REL}/extra/openapi/planted.json": "{}\n"})
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "unexpected self-test fixture entry "
                                  f"'{FIXTURE_REL}/extra/openapi/planted.json'")

    def test_shadow_openapi_directory_is_refused(self):
        head = self.fx.build_candidate(
            registry=self._green_registry(),
            extra_files={"backend/openapi/service.json": "{}\n"})
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "unscanned OpenAPI directory entry 'backend/openapi/service.json'")

    def test_top_level_shadow_openapi_directory_is_refused(self):
        head = self.fx.build_candidate(
            registry=self._green_registry(),
            extra_files={"openapi/service.json": "{}\n"})
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "unscanned OpenAPI directory entry 'openapi/service.json'")

    def test_shadow_permission_registry_is_refused(self):
        head = self.fx.build_candidate(
            registry=self._green_registry(),
            extra_files={"backend/permissions/registry.json": "{}\n"})
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result,
                          "shadow permission registry 'backend/permissions/registry.json'")

    def test_non_hex_shas_are_refused(self):
        head = self.fx.build_candidate(registry=self._green_registry())
        for bad_trusted, bad_head, name in (("not-a-sha", head, "TRUSTED_SHA"),
                                            (self.trusted, "HEAD", "HEAD_SHA")):
            with self.subTest(var=name):
                result = self.fx.run(bad_trusted, bad_head)
                self.assertDenied(result, f"{name} is not a 40-hex commit sha")

    def test_old_runner_python_is_refused(self):
        """The version guard must deny rather than fall through to a run."""
        shim = Path(self._tmp.name) / "oldbin"
        shim.mkdir()
        probe = shim / "python3"
        probe.write_text(
            "#!/bin/sh\n"
            'case "$*" in *version_info*) exit 1 ;; esac\n'
            f'exec "{sys.executable}" "$@"\n',
            encoding="utf-8")
        probe.chmod(0o755)
        head = self.fx.build_candidate(registry=self._green_registry())
        result = self.fx.run(self.trusted, head, path_prefix=shim)
        self.assertDenied(result, "runner python3 is older than 3.11")


# --- layer 3: the real adapter, real gate module, real fixtures ----------------


class RealAdapterBehaviorTests(_BehaviorBase):
    """One job, real bytes: gate 4 over candidate contracts PLUS D1 condition
    3's in-process fixture self-test, dispositioned by the committed verifier."""

    real = True

    CONFORMING_DOC = (REPO / FIXTURE_REL / "conforming" / "openapi" / "api.json")
    CONFORMING_REGISTRY = (REPO / FIXTURE_REL / "conforming" / "registry.json")
    VIOLATING_DOC = (REPO / FIXTURE_REL / "violating" / "openapi" / "api.json")

    def test_committed_skeletons_are_a_qualified_non_blocking_not_applicable(self):
        head = self.fx.build_candidate()
        result = self.fx.run(self.trusted, head)
        self.assertGreen(result)
        self.assertIn("PERMISSION_GATE_D1_STATE=NOT_APPLICABLE "
                      "reason=ZERO_REAL_OPERATIONS real_operations=0", result.stdout)
        self.assertIn("NON-BLOCKING under ADR-014 D1 conditions 1-3", result.stdout)
        # The raw adapter report proves the self-test ran in this same job.
        self.assertIn('"conforming_status": "PASS"', result.stdout)
        self.assertIn('"violating_status": "FAIL"', result.stdout)
        self.assertIn(f'"{VIOLATION_CODE}"', result.stdout)

    def test_real_conforming_operation_is_a_pass(self):
        head = self.fx.build_candidate(
            registry=self.CONFORMING_REGISTRY.read_text(encoding="utf-8"),
            openapi={"api.json": self.CONFORMING_DOC.read_text(encoding="utf-8")})
        result = self.fx.run(self.trusted, head)
        self.assertGreen(result)
        self.assertIn("PERMISSION_GATE_D1_STATE=PASS reason=REAL_OPERATIONS_CONFORM "
                      "real_operations=1", result.stdout)

    def test_real_unregistered_permission_blocks(self):
        head = self.fx.build_candidate(
            registry=self.CONFORMING_REGISTRY.read_text(encoding="utf-8"),
            openapi={"api.json": self.VIOLATING_DOC.read_text(encoding="utf-8")})
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "gate 4 reported FAIL")
        self.assertIn(VIOLATION_CODE, result.stdout)

    def test_real_unparseable_registry_is_an_error_not_a_vacuous_pass(self):
        head = self.fx.build_candidate(registry="{ this is not json\n")
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "gate 4 reported ERROR")
        self.assertNotIn("NON-BLOCKING", result.stdout)

    def test_real_non_json_openapi_document_is_an_error(self):
        head = self.fx.build_candidate(openapi={"notes.md": "# not a contract\n"})
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, "gate 4 reported ERROR")

    def test_real_adapter_edit_by_the_candidate_is_refused_before_execution(self):
        head = self.fx.build_candidate(adapter_text=CANDIDATE_STUB)
        result = self.fx.run(self.trusted, head)
        self.assertDenied(result, f"candidate changed {ADAPTER_REL}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
