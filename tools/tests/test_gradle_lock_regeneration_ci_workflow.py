#!/usr/bin/env python3
"""
Focused static + offline-behavioral tests for
`.github/workflows/gradle-lock-regeneration-ci.yml` (MOD-001, GOV-01-R04,
BUG-076 Gradle lock-completeness REGENERATION DIAGNOSTIC).

These are local tests of a workflow that has never run. They are not evidence
about any CI run, not OSV-gate evidence and carry no gate credit.

Standard library only; no network in the default run; no Gradle download in the
default run. No YAML parser exists in this project's venv, so the workflow text
is parsed line-wise (the same approach `test_permission_gate_d1_workflow.py`
and `test_typecheck_required_candidate_workflow.py` already take).

Three layers, deliberately not a mirror of the implementation:

 1. `audit(text)` encodes the POLICY this diagnostic must satisfy: the
    unprivileged shape (`pull_request` + a diagnostic-only feature-branch
    push, `permissions: {}`, no `uses:`, no secrets/GITHUB_TOKEN, env-only
    expressions from a closed allowlist), the exact-head binding and 40-hex
    screen, the pinned official Gradle 8.14 URL and SHA-256 verified BEFORE
    any unzip or execution, the four regular lock blobs, the baseline captured
    outside the checkout and re-verified, the `--write-locks` invocation, the
    byte-for-byte compare, the absence of destructive/outbound commands, and
    the honesty disclosures. The committed file must audit clean AND each of
    fifteen deliberate tampers must be flagged.
 2. BEHAVIORAL execution of the workflow's own extracted bash script, offline,
    against a synthetic `file://` git remote and a synthetic Gradle
    "distribution" zip whose launcher is a stub driven by inert data committed
    at the head. This exercises what no text reading can: that a wrong
    distribution digest denies before anything is unpacked or executed, that a
    non-40-hex head denies before any fetch, that a lock mismatch / missing
    lock / symlinked lock / nonzero Gradle exit each fail, and that a build
    which rewrites the comparison baseline is caught.
 3. MUTANTS of the committed script are executed to show each control is
    load-bearing: with the digest comparison, the `cmp` compare, the lock-mode
    screen, the 40-hex screen or the baseline re-verification removed, an input
    the committed script rejects becomes green. A mutant that still fails
    would mean the corresponding test proves nothing.

Layer 4 is opt-in and NOT part of the default run: with
`VEYRO_GRADLE_REAL=1`, the same script runs with the REAL official Gradle 8.14
distribution (digest-pinned, read from the local trial directory over
`file://`) over a disposable copy of the real `mobile/` tree, and reproduces
BUG-076's local negative - deleting `com.android.tools.ddms:ddmlib:31.11.1`
from `mobile/shared/gradle.lockfile` must come back as a byte mismatch. It is
opt-in because it needs a JDK, an Android SDK and network/cache access, i.e.
exactly the environment coupling that keeps this workflow a diagnostic.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))
from validate_workflow_trust import evaluate_workflow_text  # noqa: E402

WORKFLOW_REL = ".github/workflows/gradle-lock-regeneration-ci.yml"
WORKFLOW = REPO / WORKFLOW_REL
OSV_WORKFLOW_REL = ".github/workflows/dependency-vulnerability-gate.yml"

OFFICIAL_URL = "https://services.gradle.org/distributions/gradle-8.14-bin.zip"
OFFICIAL_SHA256 = "61ad310d3c7d3e5da131b76bbf22b5a4c0786e9d892dae8c1658d4b484de3caa"

LOCKS = (
    "mobile/androidApp/buildscript-gradle.lockfile",
    "mobile/androidApp/gradle.lockfile",
    "mobile/shared/buildscript-gradle.lockfile",
    "mobile/shared/gradle.lockfile",
)

EXPECTED_TRIGGERS = {"pull_request", "push"}
FORBIDDEN_TRIGGERS = (
    "pull_request_target", "workflow_dispatch", "schedule", "workflow_run",
    "workflow_call", "repository_dispatch", "release", "issue_comment",
    "merge_group", "deployment", "deployment_status",
)
ALLOWED_EXPRESSIONS = {
    "github.event_name",
    "github.event.pull_request.head.sha",
    "github.ref",
    "github.sha",
    "github.server_url",
    "github.repository",
}
# Anything that would act on the world rather than observe it.
FORBIDDEN_COMMAND_PATTERNS = (
    r"\bgit\b[^\n]*\bpush\b", r"\bgit\b[^\n]*\bcommit\b", r"\bgit\b[^\n]*\btag\b",
    r"\bgh\s", r"\bdocker\b", r"\bterraform\b", r"\baws\s", r"\bgcloud\b",
    r"\bkubectl\b", r"npm\s+publish", r"\bssh\s", r"\bscp\s", r"curl\s+-X",
    r"Authorization:", r"GITHUB_OUTPUT", r"GITHUB_ENV",
)
REQUIRED_DISCLOSURES = (
    "NONREQUIRED",
    "no gate credit",
    "NOT a required check",
    "candidate-controlled",
    "Gradle may not resolve every future configuration",
    "No model assurance and no independent security review",
    "EXITED 0",
    "byte-for-byte",
)

# Offline stub "distribution" markers.
STUB_MARKER = "VEYRO-TEST-STUB-GRADLE-RAN"
ARGS_MARKER = "VEYRO-TEST-STUB-ARGS:"

# Opt-in real-Gradle layer.
TRIAL = Path("/tmp/veyro-gradle-trial-20261015")
REAL_DIST = TRIAL / "gradle-8.14-bin.zip"
REAL_SDK = TRIAL / "toolchain" / "android-sdk"
MISSING_COORDINATE = "com.android.tools.ddms:ddmlib:31.11.1"

STUB_GRADLE = f"""#!/bin/sh
# Offline stand-in for the Gradle launcher. Prints a marker so a test can prove
# whether it ran at all, echoes its argv so the invocation shape is checked
# behaviorally, and delegates any lock mutation to an inert directive committed
# at the synthetic head.
echo "{STUB_MARKER}" >&2
if [ "$1" = "--version" ]; then
  echo "------------------------------------------------------------"
  echo "Gradle 8.14"
  echo "------------------------------------------------------------"
  exit 0
fi
echo "{ARGS_MARKER} $*"
proj=''
prev=''
for a in "$@"; do
  if [ "$prev" = "-p" ]; then proj="$a"; fi
  prev="$a"
done
if [ -z "$proj" ]; then echo "stub: missing -p" >&2; exit 97; fi
if [ -f "$proj/.veyro-stub-directive" ]; then
  sh "$proj/.veyro-stub-directive" "$proj"
  exit $?
fi
exit 0
"""

# Directives run as `sh directive <project-dir>` by the stub launcher.
DIRECTIVE_APPEND = (
    '#!/bin/sh\n'
    'echo "com.example:regenerated:1.0=runtimeClasspath" >> "$1/shared/gradle.lockfile"\n'
)
DIRECTIVE_NONZERO = '#!/bin/sh\nexit 3\n'
DIRECTIVE_DELETE = '#!/bin/sh\nrm -f "$1/shared/gradle.lockfile"\n'
DIRECTIVE_SYMLINK = (
    '#!/bin/sh\n'
    'rm -f "$1/shared/gradle.lockfile"\n'
    'ln -s buildscript-gradle.lockfile "$1/shared/gradle.lockfile"\n'
)
# Rewrites the captured comparison baseline to match its own mutated lock: the
# exact move that would turn a truncated lock green if the baseline were taken
# on trust after the build.
DIRECTIVE_POISON_BASELINE = (
    '#!/bin/sh\n'
    'echo "com.example:regenerated:1.0=runtimeClasspath" >> "$1/shared/gradle.lockfile"\n'
    'cp "$1/shared/gradle.lockfile" "$1/../../original-locks/mobile__shared__gradle.lockfile"\n'
)

LOCK_TEMPLATE = (
    "# This is a Gradle generated file for dependency locking.\n"
    "# Manual edits can break the build and are not advised.\n"
    "com.example:{slug}:1.0=runtimeClasspath\n"
    "empty=testCompileClasspath\n"
)


# --------------------------------------------------------------------------- #
# parsing helpers
# --------------------------------------------------------------------------- #
def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def code_lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]


def extract_run_script(text: str) -> str:
    """Return the single `run: |` block body, dedented - the exact bytes CI runs."""
    lines = text.splitlines()
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


def push_branches(text: str) -> list[str]:
    """The branch patterns under `push: branches:` - and only those."""
    lines = code_lines(text)
    try:
        start = next(i for i, ln in enumerate(lines) if re.fullmatch(r"  push\s*:\s*", ln))
    except StopIteration:
        return []
    branches: list[str] = []
    in_branches = False
    for ln in lines[start + 1:]:
        if ln.strip() and not ln.startswith("    "):
            break
        if re.fullmatch(r"    branches\s*:\s*", ln):
            in_branches = True
            continue
        if in_branches:
            match = re.fullmatch(r"      - '(.+)'", ln)
            if match is None:
                break
            branches.append(match.group(1))
    return branches


def trigger_keys(text: str) -> list[str]:
    """Keys declared under the single top-level `on:` block."""
    lines = code_lines(text)
    try:
        start = next(i for i, ln in enumerate(lines) if re.fullmatch(r"on\s*:\s*", ln))
    except StopIteration:
        return []
    keys: list[str] = []
    for ln in lines[start + 1:]:
        if not ln.strip():
            continue
        if not ln.startswith(" "):
            break
        match = re.fullmatch(r"  ([A-Za-z_][A-Za-z0-9_]*)\s*:\s*", ln)
        if match:
            keys.append(match.group(1))
    return keys


def env_values(text: str) -> dict[str, str]:
    """The step's `env:` mapping, as literal text (expressions included)."""
    values: dict[str, str] = {}
    for ln in code_lines(text):
        match = re.fullmatch(r"\s{10}([A-Z_][A-Z0-9_]*): (.+)", ln)
        if match:
            values[match.group(1)] = match.group(2).strip()
    return values


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# layer 1: the policy
# --------------------------------------------------------------------------- #
def audit(text: str) -> list[str]:
    """Return the sorted violation codes for a workflow text. Empty == clean."""
    bad: set[str] = set()
    code = "\n".join(code_lines(text))
    try:
        script = extract_run_script(text)
    except AssertionError:
        return ["UNEXTRACTABLE_RUN_BLOCK"]
    # Shell comments inside the run block document the policy; they must never
    # be able to satisfy a check about executed code.
    script_code = "\n".join(ln for ln in script.splitlines()
                            if not ln.lstrip().startswith("#"))

    def pos(needle: str) -> int:
        return script_code.find(needle)

    def need(needle: str, violation: str) -> None:
        if needle not in script_code:
            bad.add(violation)

    # --- identity and trigger shape ---
    if "name: gradle-lock-regeneration-diagnostic" not in code:
        bad.add("WORKFLOW_NAME")
    if set(trigger_keys(text)) != EXPECTED_TRIGGERS:
        bad.add("TRIGGERS")
    for forbidden in FORBIDDEN_TRIGGERS:
        if re.search(rf"^  {re.escape(forbidden)}\s*:", code, re.MULTILINE):
            bad.add("FORBIDDEN_TRIGGER")
    if push_branches(text) != ["diagnostic/gradle-lock-regeneration/**"]:
        bad.add("PUSH_BRANCH_SCOPE")

    # --- unprivileged shape ---
    if re.findall(r"^permissions: \{\}$", code, re.MULTILINE) != ["permissions: {}"]:
        bad.add("PERMISSIONS")
    if len(re.findall(r"permissions\s*:", code)) != 1:
        bad.add("PERMISSIONS")
    if re.search(r"\buses\s*:", code):
        bad.add("USES_ACTION")
    if "secrets." in code or "secrets[" in code or "GITHUB_TOKEN" in code:
        bad.add("SECRETS_REFERENCE")
    for expression in re.findall(r"\$\{\{(.+?)\}\}", code, re.DOTALL):
        for reference in re.findall(
            r"\b(?:github|env|secrets|vars|inputs|needs|steps|job|runner)\.[A-Za-z_][A-Za-z0-9_.]*",
            expression,
        ):
            if reference not in ALLOWED_EXPRESSIONS:
                bad.add("EXPRESSION_ALLOWLIST")
    if "${{" in script:
        bad.add("EXPRESSION_IN_SCRIPT")

    # --- one job, one step ---
    if len(re.findall(r"^jobs:$", code, re.MULTILINE)) != 1:
        bad.add("JOB_STRUCTURE")
    if len(re.findall(r"^\s+- name: .+", code, re.MULTILINE)) != 1:
        bad.add("JOB_STRUCTURE")
    if len(re.findall(r"^\s+shell: bash$", code, re.MULTILINE)) != 1:
        bad.add("JOB_STRUCTURE")
    job_name = re.search(r"^    name: (.+)$", code, re.MULTILINE)
    if job_name is None or "NONREQUIRED DIAGNOSTIC" not in job_name.group(1):
        bad.add("CHECK_NAME_DISCLOSURE")

    # --- exact-head binding ---
    env = env_values(text)
    if env.get("HEAD_SHA") != (
        "${{ github.event_name == 'pull_request' "
        "&& github.event.pull_request.head.sha || github.sha }}"
    ):
        bad.add("HEAD_SHA_BINDING")
    if env.get("REPO_URL") != "${{ github.server_url }}/${{ github.repository }}.git":
        bad.add("REPO_URL_BINDING")
    need('[[ "$HEAD_SHA" =~ ^[0-9a-f]{40}$ ]]', "HEAD_SHA_40HEX")
    need('fetch -q --no-tags --depth=1 "$REPO_URL" "$HEAD_SHA"', "EXACT_HEAD_FETCH")
    need('rev-parse HEAD)" == "$HEAD_SHA"', "CHECKOUT_SHA_CHECK")
    need('work="$RUNNER_TEMP/head"', "CHECKOUT_IN_RUNNER_TEMP")
    if 'pull_request) ;;' not in script or "refs/heads/diagnostic/gradle-lock-regeneration/" not in script:
        bad.add("EVENT_SCREEN")

    # --- pinned, verified distribution ---
    if env.get("GRADLE_URL") != OFFICIAL_URL:
        bad.add("GRADLE_URL_PIN")
    if env.get("GRADLE_SHA256") != OFFICIAL_SHA256:
        bad.add("GRADLE_SHA256_PIN")
    need('[[ "$GRADLE_SHA256" =~ ^[0-9a-f]{64}$ ]]', "GRADLE_SHA256_64HEX")
    need('[[ "$got" == "$GRADLE_SHA256" ]]', "DIST_DIGEST_COMPARE")
    verify_at = pos('[[ "$got" == "$GRADLE_SHA256" ]]')
    unzip_at = pos("unzip -q")
    exec_at = pos('"$gradle_bin"')
    if -1 in (verify_at, unzip_at, exec_at) or not verify_at < unzip_at < exec_at:
        bad.add("DIGEST_BEFORE_UNZIP_AND_EXEC")
    need("grep -qxF 'Gradle 8.14'", "LAUNCHER_VERSION_CHECK")

    # --- four regular lock blobs, baseline outside the checkout ---
    declared = re.findall(r"^\s+(mobile/\S+lockfile)$", script_code, re.MULTILINE)
    if tuple(declared) != LOCKS:
        bad.add("LOCK_SET")
    need('[[ "$meta" =~ ^100644\\ blob\\ [0-9a-f]{40}$ ]]', "LOCK_BLOB_MODE_SCREEN")
    need('[[ -f "$path" && ! -L "$path" ]] || deny', "LOCK_REGULAR_FILE_SCREEN")
    if 'orig="$RUNNER_TEMP/original-locks"' not in script:
        bad.add("BASELINE_OUTSIDE_CHECKOUT")
    need('cp -- "$path" "$orig/${rel//\\//__}"', "BASELINE_CAPTURE")
    need('orig_sha+=("$digest")', "BASELINE_DIGEST_RECORDED")
    need('[[ "$now" == "${orig_sha[$i]}" ]]', "BASELINE_REVERIFIED")

    # --- the discriminating invocation ---
    invocation = " ".join(script_code.split())
    for fragment in (
        '"$gradle_bin" -p "$work/mobile" :shared:dependencies :androidApp:dependencies',
        "--write-locks",
        "--no-daemon",
    ):
        if fragment not in invocation:
            bad.add("WRITE_LOCKS_INVOCATION")
    need('|| fail "Gradle lock regeneration exited nonzero"', "NONZERO_GRADLE_FAILS")

    # --- byte-for-byte comparison ---
    need('cmp -s -- "$base" "$path"', "BYTE_COMPARE")
    need("GRADLE_LOCK_MISMATCH", "MISMATCH_REPORTED")
    need("GRADLE_LOCK_SUMMARY", "STRUCTURED_SUMMARY")
    need('[[ "$mismatched" -eq 0 ]]', "MISMATCH_FAILS_JOB")
    need('|| fail "$rel is missing or irregular after regeneration"', "POST_RUN_LOCK_SCREEN")

    # --- nothing destructive or outbound ---
    for pattern in FORBIDDEN_COMMAND_PATTERNS:
        if re.search(pattern, script_code):
            bad.add("FORBIDDEN_COMMAND")

    # --- honesty ---
    for phrase in REQUIRED_DISCLOSURES:
        if phrase not in text:
            bad.add("DISCLOSURE")

    return sorted(bad)


class PolicyAuditTests(unittest.TestCase):
    def setUp(self):
        self.text = workflow_text()

    def test_committed_workflow_audits_clean(self):
        self.assertEqual(audit(self.text), [])

    def test_each_tamper_is_flagged(self):
        tampers: tuple[tuple[str, str, str, str], ...] = (
            # (label, old, new, expected code)
            ("privileged trigger", "  pull_request:\n", "  pull_request_target:\n",
             "FORBIDDEN_TRIGGER"),
            ("default-branch push", "      - 'diagnostic/gradle-lock-regeneration/**'",
             "      - 'main'", "PUSH_BRANCH_SCOPE"),
            ("token scopes", "\npermissions: {}\n", "\npermissions:\n  contents: read\n",
             "PERMISSIONS"),
            ("an action", "        shell: bash", "        uses: actions/checkout@v4",
             "USES_ACTION"),
            ("a secret", "          GRADLE_URL: ", "          TOKEN: ${{ secrets.NPM_TOKEN }}\n          GRADLE_URL: ",
             "SECRETS_REFERENCE"),
            ("base-sha binding", "github.event.pull_request.head.sha || github.sha",
             "github.event.pull_request.base.sha || github.sha", "HEAD_SHA_BINDING"),
            ("no 40-hex screen", '[[ "$HEAD_SHA" =~ ^[0-9a-f]{40}$ ]]',
             '[[ -n "$HEAD_SHA" ]]', "HEAD_SHA_40HEX"),
            ("branch-ref fetch", 'fetch -q --no-tags --depth=1 "$REPO_URL" "$HEAD_SHA"',
             'fetch -q --no-tags --depth=1 "$REPO_URL" HEAD', "EXACT_HEAD_FETCH"),
            ("unpinned distribution url",
             "GRADLE_URL: https://services.gradle.org/distributions/gradle-8.14-bin.zip",
             "GRADLE_URL: https://example.invalid/gradle.zip", "GRADLE_URL_PIN"),
            ("wrong digest pin", OFFICIAL_SHA256, "0" * 64, "GRADLE_SHA256_PIN"),
            ("no digest compare", '[[ "$got" == "$GRADLE_SHA256" ]]',
             '[[ -n "$got" ]]', "DIST_DIGEST_COMPARE"),
            ("three locks", "            mobile/shared/gradle.lockfile\n", "",
             "LOCK_SET"),
            ("no baseline re-verify", '[[ "$now" == "${orig_sha[$i]}" ]]',
             '[[ -n "$now" ]]', "BASELINE_REVERIFIED"),
            ("plain dependencies run", "            --write-locks --no-daemon \\",
             "            --no-daemon \\", "WRITE_LOCKS_INVOCATION"),
            ("no byte compare", 'cmp -s -- "$base" "$path"', "true", "BYTE_COMPARE"),
            ("mismatch tolerated", '[[ "$mismatched" -eq 0 ]]', '[[ "$mismatched" -ge 0 ]]',
             "MISMATCH_FAILS_JOB"),
            ("pushes a fix", 'echo "GRADLE_WRITE_LOCKS_EXIT_ZERO: ok"',
             'git -C "$work" push origin HEAD:refs/heads/autofix', "FORBIDDEN_COMMAND"),
            ("required-check framing",
             "    name: gradle-lock-regeneration-diagnostic (NONREQUIRED DIAGNOSTIC - no gate credit)",
             "    name: gradle-lock-regeneration", "CHECK_NAME_DISCLOSURE"),
            ("dropped disclosure", "Gradle may not resolve every future configuration",
             "Gradle resolves every configuration", "DISCLOSURE"),
        )
        for label, old, new, expected in tampers:
            with self.subTest(tamper=label):
                self.assertIn(old, self.text, f"tamper anchor missing: {label}")
                mutated = self.text.replace(old, new, 1)
                self.assertNotEqual(mutated, self.text)
                self.assertIn(expected, audit(mutated))

    def test_run_script_is_valid_bash(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "step.sh"
            script.write_text(extract_run_script(self.text), encoding="utf-8")
            result = subprocess.run(["bash", "-n", str(script)],
                                    check=False, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_yaml_block_structure_is_well_formed(self):
        """No PyYAML here, so assert the structural invariants a parse would give."""
        lines = self.text.splitlines()
        self.assertEqual(sum(1 for ln in lines if re.fullmatch(r"jobs:\s*", ln)), 1)
        self.assertEqual(sum(1 for ln in lines if re.fullmatch(r"on\s*:\s*", ln)), 1)
        self.assertEqual(sum(1 for ln in lines if re.fullmatch(r"\s*steps:\s*", ln)), 1)
        run_idx = [i for i, ln in enumerate(lines) if re.fullmatch(r"\s*run: \|\s*", ln)]
        self.assertEqual(len(run_idx), 1)
        first = lines[run_idx[0] + 1]
        body_indent = len(first) - len(first.lstrip())
        self.assertGreater(body_indent,
                           len(lines[run_idx[0]]) - len(lines[run_idx[0]].lstrip()))
        # The block scalar must run to the end of the file: nothing after it may
        # dedent back to a shallower non-blank line (which would silently move
        # shell text into YAML).
        for ln in lines[run_idx[0] + 1:]:
            if ln.strip():
                self.assertGreaterEqual(len(ln) - len(ln.lstrip()), body_indent,
                                        f"block scalar ends early at {ln!r}")

    def test_standing_workflow_trust_lint_allows_this_file(self):
        self.assertEqual(evaluate_workflow_text(self.text, name=WORKFLOW_REL), [])

    def test_the_four_lock_files_exist_in_the_repository_as_regular_files(self):
        for rel in LOCKS:
            path = REPO / rel
            with self.subTest(lock=rel):
                self.assertTrue(path.is_file() and not path.is_symlink(), rel)

    def test_pinned_digest_matches_the_official_distribution_bytes(self):
        if not REAL_DIST.is_file():
            self.skipTest(f"{REAL_DIST} not available on this host")
        self.assertEqual(sha256_file(REAL_DIST), OFFICIAL_SHA256)

    def test_trusted_osv_workflow_still_treats_pr_bytes_as_inert(self):
        """The candidate Gradle execution must stay OUT of the privileged gate."""
        osv = (REPO / OSV_WORKFLOW_REL).read_text(encoding="utf-8")
        osv_code = "\n".join(code_lines(osv))
        self.assertIn("pull_request_target", osv_code)
        for fragment in ("--write-locks", ":shared:dependencies",
                         ":androidApp:dependencies", "gradle-8.14-bin.zip"):
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, osv_code)
        # ... and this diagnostic must not be wired into it.
        self.assertNotIn("gradle-lock-regeneration", osv_code)


# --------------------------------------------------------------------------- #
# layers 2-3: behavioral harness (offline)
# --------------------------------------------------------------------------- #
class Harness:
    """A synthetic `file://` remote, a stub Gradle distribution, and a runner
    for the workflow's own extracted bash script."""

    def __init__(self, tmp: Path, script: str | None = None):
        self.tmp = tmp
        self.origin = tmp / "origin"
        self.runner_temp = tmp / "runner-temp"
        self.runner_temp.mkdir(parents=True)
        self.bin = tmp / "bin"
        self.bin.mkdir()
        if shutil.which("sha256sum") is None:  # macOS hosts
            shim = self.bin / "sha256sum"
            shim.write_text('#!/bin/sh\nexec shasum -a 256 "$@"\n', encoding="utf-8")
            shim.chmod(0o755)
        self.script = tmp / "step.sh"
        self.script.write_text(script if script is not None
                               else extract_run_script(workflow_text()), encoding="utf-8")

    # --- synthetic remote ---
    def _git(self, *args: str) -> str:
        return subprocess.run(("git", "-C", str(self.origin), *args),
                              check=True, capture_output=True, text=True).stdout.strip()

    def _write(self, rel: str, text: str) -> None:
        path = self.origin / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def build_head(self, *, directive: str | None = None,
                   omit: tuple[str, ...] = (),
                   symlinks: dict[str, str] | None = None,
                   mobile_tree: Path | None = None,
                   edits: dict[str, str] | None = None) -> str:
        self.origin.mkdir(parents=True)
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.email", "test@example.invalid")
        self._git("config", "user.name", "veyro test")
        self._git("config", "uploadpack.allowAnySHA1InWant", "true")
        self._git("config", "uploadpack.allowReachableSHA1InWant", "true")
        if mobile_tree is not None:
            shutil.copytree(mobile_tree, self.origin / "mobile",
                            ignore=shutil.ignore_patterns("build", ".gradle", ".kotlin"),
                            symlinks=True)
        else:
            for rel in LOCKS:
                if rel in omit:
                    continue
                self._write(rel, LOCK_TEMPLATE.format(slug=rel.replace("/", "-")))
        for rel, text in (edits or {}).items():
            self._write(rel, text)
        for rel, target in (symlinks or {}).items():
            path = self.origin / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() or path.is_symlink():
                path.unlink()
            os.symlink(target, path)
        if directive is not None:
            self._write("mobile/.veyro-stub-directive", directive)
        self._git("add", "-A")
        self._git("commit", "-qm", "synthetic head")
        return self._git("rev-parse", "HEAD")

    # --- stub distribution ---
    def stub_dist(self) -> tuple[str, str]:
        path = self.tmp / "stub-gradle-8.14-bin.zip"
        with zipfile.ZipFile(path, "w") as archive:
            info = zipfile.ZipInfo("gradle-8.14/bin/gradle")
            info.external_attr = (0o100755 << 16)
            archive.writestr(info, STUB_GRADLE)
        return f"file://{path}", sha256_file(path)

    # --- run ---
    def run(self, head_sha: str, *, event: str = "pull_request",
            ref: str = "refs/pull/7/merge", url: str | None = None,
            digest: str | None = None, env_extra: dict[str, str] | None = None,
            timeout: int = 300) -> subprocess.CompletedProcess:
        if url is None or digest is None:
            default_url, default_digest = self.stub_dist()
            url = url or default_url
            digest = digest or default_digest
        env = {
            "PATH": f"{self.bin}:{os.environ.get('PATH', '')}",
            "HOME": str(self.tmp),
            "RUNNER_TEMP": str(self.runner_temp),
            "EVENT_NAME": event,
            "REF": ref,
            "HEAD_SHA": head_sha,
            "REPO_URL": f"file://{self.origin}",
            "GRADLE_URL": url,
            "GRADLE_SHA256": digest,
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        }
        env.update(env_extra or {})
        return subprocess.run(["bash", str(self.script)], check=False, env=env,
                              cwd=str(self.tmp), capture_output=True, text=True,
                              timeout=timeout)


class _BehaviorBase(unittest.TestCase):
    script: str | None = None

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="veyro-gradle-lock-")
        self.addCleanup(self._tmp.cleanup)
        self.fx = Harness(Path(self._tmp.name), script=self.script)

    @staticmethod
    def out(result: subprocess.CompletedProcess) -> str:
        return result.stdout + result.stderr

    def assertFailed(self, result, needle: str) -> None:
        combined = self.out(result)
        self.assertNotEqual(result.returncode, 0,
                            f"expected nonzero\n{combined}")
        self.assertIn(needle, combined)

    def assertGreen(self, result) -> None:
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("GRADLE_LOCK_REGENERATION_DIAGNOSTIC_CLEAN", result.stdout)


class ScreenBehaviorTests(_BehaviorBase):
    """Input screens, executed - not read."""

    def test_non_hex_head_sha_denies_before_any_fetch(self):
        self.fx.build_head()
        result = self.fx.run("not-a-sha")
        self.assertFailed(result, "DENY: head sha is not 40-hex")
        self.assertFalse((self.fx.runner_temp / "head").exists(),
                         "nothing may be fetched before the sha screen")

    def test_uppercase_head_sha_is_denied(self):
        head = self.fx.build_head()
        self.assertFailed(self.fx.run(head.upper()), "head sha is not 40-hex")

    def test_unknown_event_is_denied(self):
        head = self.fx.build_head()
        self.assertFailed(self.fx.run(head, event="pull_request_target"),
                          "is neither pull_request nor push")

    def test_push_outside_the_diagnostic_branch_space_is_denied(self):
        head = self.fx.build_head()
        self.assertFailed(self.fx.run(head, event="push", ref="refs/heads/main"),
                          "is not a diagnostic/gradle-lock-regeneration/** branch")

    def test_push_on_a_diagnostic_branch_runs(self):
        head = self.fx.build_head()
        self.assertGreen(self.fx.run(
            head, event="push",
            ref="refs/heads/diagnostic/gradle-lock-regeneration/probe"))

    def test_wrong_distribution_digest_denies_before_unzip_or_execution(self):
        head = self.fx.build_head()
        url, _ = self.fx.stub_dist()
        result = self.fx.run(head, url=url, digest="0" * 64)
        self.assertFailed(result, "DENY: Gradle distribution sha256")
        self.assertNotIn(STUB_MARKER, self.out(result),
                         "no byte of the distribution may execute before the digest check")
        self.assertFalse(any((self.fx.runner_temp / "gradle-toolchain").rglob("*")),
                         "nothing may be unpacked before the digest check")

    def test_missing_lock_at_head_is_denied(self):
        head = self.fx.build_head(omit=("mobile/shared/gradle.lockfile",))
        self.assertFailed(self.fx.run(head),
                          "mobile/shared/gradle.lockfile is absent")

    def test_symlinked_lock_at_head_is_denied(self):
        head = self.fx.build_head(
            symlinks={"mobile/shared/gradle.lockfile": "buildscript-gradle.lockfile"})
        result = self.fx.run(head)
        self.assertFailed(result, "is not a regular lock blob")
        self.assertNotIn(ARGS_MARKER, self.out(result),
                         "no build may run once an input lock is irregular")


class RegenerationBehaviorTests(_BehaviorBase):
    """The comparison itself, driven through the stub launcher."""

    def test_unchanged_locks_are_green_and_the_invocation_shape_is_the_discriminating_one(self):
        head = self.fx.build_head()
        result = self.fx.run(head)
        self.assertGreen(result)
        self.assertIn(STUB_MARKER, self.out(result))
        args = next(ln for ln in result.stdout.splitlines() if ARGS_MARKER in ln)
        for fragment in (":shared:dependencies", ":androidApp:dependencies",
                         "--write-locks", "--no-daemon", "-p "):
            self.assertIn(fragment, args)
        for rel in LOCKS:
            self.assertIn(f"GRADLE_LOCK_MATCH: {rel}", result.stdout)
        self.assertIn("GRADLE_LOCK_SUMMARY: checked=4 mismatched=0", result.stdout)

    def test_a_regenerated_coordinate_fails_the_job(self):
        head = self.fx.build_head(directive=DIRECTIVE_APPEND)
        result = self.fx.run(head)
        self.assertFailed(result, "GRADLE_LOCK_MISMATCH: mobile/shared/gradle.lockfile")
        self.assertIn("GRADLE_LOCK_SUMMARY: checked=4 mismatched=1", result.stdout)
        self.assertIn("com.example:regenerated:1.0", result.stdout)
        self.assertNotIn("DIAGNOSTIC_CLEAN", result.stdout)

    def test_nonzero_gradle_exit_fails_the_job(self):
        head = self.fx.build_head(directive=DIRECTIVE_NONZERO)
        self.assertFailed(self.fx.run(head),
                          "FAIL: Gradle lock regeneration exited nonzero")

    def test_a_lock_deleted_by_the_build_fails_the_job(self):
        head = self.fx.build_head(directive=DIRECTIVE_DELETE)
        self.assertFailed(self.fx.run(head),
                          "mobile/shared/gradle.lockfile is missing or irregular")

    def test_a_lock_replaced_by_a_symlink_during_the_build_fails_the_job(self):
        head = self.fx.build_head(directive=DIRECTIVE_SYMLINK)
        self.assertFailed(self.fx.run(head),
                          "mobile/shared/gradle.lockfile is missing or irregular")

    def test_a_build_that_rewrites_the_comparison_baseline_is_caught(self):
        head = self.fx.build_head(directive=DIRECTIVE_POISON_BASELINE)
        result = self.fx.run(head)
        self.assertFailed(result, "comparison baseline for mobile/shared/gradle.lockfile changed")
        self.assertNotIn("DIAGNOSTIC_CLEAN", result.stdout)


# --------------------------------------------------------------------------- #
# layer 3: mutants - each control must be load-bearing
# --------------------------------------------------------------------------- #
def mutate(old: str, new: str) -> str:
    script = extract_run_script(workflow_text())
    if old not in script:
        raise AssertionError(f"mutation anchor missing from the committed script: {old!r}")
    return script.replace(old, new, 1)


class MutantTests(unittest.TestCase):
    """Run a mutated copy of the committed script and show the input the
    committed script rejects becomes green. If a mutant still failed, the
    corresponding behavioral test would be proving nothing."""

    def _harness(self, script: str) -> Harness:
        tmp = tempfile.TemporaryDirectory(prefix="veyro-gradle-lock-mutant-")
        self.addCleanup(tmp.cleanup)
        return Harness(Path(tmp.name), script=script)

    def test_removing_the_digest_check_accepts_an_unverified_distribution(self):
        fx = self._harness(mutate('"$got" == "$GRADLE_SHA256"', '-n "$got"'))
        head = fx.build_head()
        url, _ = fx.stub_dist()
        result = fx.run(head, url=url, digest="0" * 64)
        self.assertEqual(result.returncode, 0,
                         "mutant must accept the unverified distribution: "
                         + result.stdout + result.stderr)
        self.assertIn(STUB_MARKER, result.stdout + result.stderr)

    def test_removing_the_byte_compare_accepts_a_regenerated_coordinate(self):
        fx = self._harness(mutate('if cmp -s -- "$base" "$path"; then', "if true; then"))
        head = fx.build_head(directive=DIRECTIVE_APPEND)
        result = fx.run(head)
        self.assertEqual(result.returncode, 0,
                         "mutant must go green on a mismatch: " + result.stdout + result.stderr)
        self.assertIn("GRADLE_LOCK_SUMMARY: checked=4 mismatched=0", result.stdout)

    def test_removing_the_lock_mode_screen_lets_a_symlinked_lock_reach_the_build(self):
        """The pre-build screen is what stops an irregular lock input from ever
        being handed to Gradle. (A second, independent post-regeneration screen
        still catches this mutant afterwards - that is defence in depth, not a
        reason to believe the first screen is inert.)"""
        script = mutate('"$meta" =~ ^100644\\ blob\\ [0-9a-f]{40}$', '-n "$meta"')
        script = script.replace('-f "$path" && ! -L "$path"', '-e "$path"', 1)
        fx = self._harness(script)
        head = fx.build_head(
            symlinks={"mobile/shared/gradle.lockfile": "buildscript-gradle.lockfile"})
        combined = (lambda r: r.stdout + r.stderr)(fx.run(head))
        self.assertIn(ARGS_MARKER, combined,
                      "mutant must get as far as invoking the build: " + combined)
        self.assertNotIn("is not a regular lock blob", combined)

    def test_removing_the_baseline_reverification_accepts_a_poisoned_baseline(self):
        fx = self._harness(mutate('"$now" == "${orig_sha[$i]}"', '-n "$now"'))
        head = fx.build_head(directive=DIRECTIVE_POISON_BASELINE)
        result = fx.run(head)
        self.assertEqual(result.returncode, 0,
                         "mutant must be fooled by the rewritten baseline: "
                         + result.stdout + result.stderr)
        self.assertIn("GRADLE_LOCK_SUMMARY: checked=4 mismatched=0", result.stdout)

    def test_removing_the_40_hex_screen_lets_an_unvalidated_ref_reach_the_fetch(self):
        fx = self._harness(mutate('"$HEAD_SHA" =~ ^[0-9a-f]{40}$', '-n "$HEAD_SHA"'))
        head = fx.build_head()
        result = fx.run("refs/heads/main")
        combined = result.stdout + result.stderr
        self.assertNotIn("head sha is not 40-hex", combined)
        self.assertTrue((fx.runner_temp / "head").exists(),
                        "mutant must get as far as initializing the work tree")
        self.assertNotEqual(head, "")


# --------------------------------------------------------------------------- #
# layer 4 (opt-in): the real Gradle 8.14 negative
# --------------------------------------------------------------------------- #
def _real_gradle_reason() -> str | None:
    if os.environ.get("VEYRO_GRADLE_REAL") != "1":
        return "set VEYRO_GRADLE_REAL=1 to run the real Gradle layer"
    if not REAL_DIST.is_file():
        return f"{REAL_DIST} is not available"
    if not REAL_SDK.is_dir():
        return f"{REAL_SDK} is not available"
    return None


@unittest.skipIf(_real_gradle_reason() is not None, _real_gradle_reason() or "")
class RealGradleTests(unittest.TestCase):
    """Executes the committed script with the REAL digest-pinned Gradle 8.14
    distribution over a disposable copy of the real `mobile/` tree.

    Not offline and not deterministic (dependency resolution needs the Gradle
    cache or the network, plus a JDK and an Android SDK) - which is precisely
    the environment coupling that keeps this workflow a diagnostic rather than
    a gate. Opt-in only.
    """

    def _run(self, *, edits: dict[str, str] | None = None, timeout: int = 1800):
        tmp = tempfile.TemporaryDirectory(prefix="veyro-gradle-lock-real-")
        self.addCleanup(tmp.cleanup)
        fx = Harness(Path(tmp.name))
        head = fx.build_head(mobile_tree=REPO / "mobile", edits=edits)
        env_extra = {
            "ANDROID_HOME": str(REAL_SDK),
            "ANDROID_SDK_ROOT": str(REAL_SDK),
            "GRADLE_USER_HOME": os.environ.get(
                "VEYRO_GRADLE_USER_HOME", str(Path.home() / ".gradle")),
        }
        if os.environ.get("JAVA_HOME"):
            env_extra["JAVA_HOME"] = os.environ["JAVA_HOME"]
        return fx.run(head, url=f"file://{REAL_DIST}", digest=OFFICIAL_SHA256,
                      env_extra=env_extra, timeout=timeout)

    def test_committed_locks_regenerate_byte_identically(self):
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stdout[-6000:] + result.stderr[-6000:])
        self.assertIn("GRADLE_LOCK_SUMMARY: checked=4 mismatched=0", result.stdout)

    def test_bug076_missing_coordinate_comes_back_as_a_byte_mismatch(self):
        original = (REPO / "mobile/shared/gradle.lockfile").read_text(encoding="utf-8")
        truncated = "".join(ln for ln in original.splitlines(keepends=True)
                            if not ln.startswith(MISSING_COORDINATE + "="))
        self.assertNotEqual(original, truncated,
                            f"{MISSING_COORDINATE} is no longer in the committed lock")
        result = self._run(edits={"mobile/shared/gradle.lockfile": truncated})
        tail = result.stdout[-6000:] + result.stderr[-6000:]
        self.assertNotEqual(result.returncode, 0, tail)
        self.assertIn("GRADLE_LOCK_MISMATCH: mobile/shared/gradle.lockfile", result.stdout)
        self.assertIn(MISSING_COORDINATE, result.stdout)


if __name__ == "__main__":
    unittest.main()
