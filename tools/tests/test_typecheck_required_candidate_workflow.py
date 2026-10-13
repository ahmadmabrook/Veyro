#!/usr/bin/env python3
"""
Focused static + behavioral tests for
.github/workflows/typecheck-required-candidate.yml (MOD-001, GOV-01-R04
required type-check CI CANDIDATE; local tests only, never evidence about a CI
run and no gate credit).

Standard library only; no network, no mypy, no Veyro source is type-checked.
No YAML parser is available in the project venv, so the workflow text is
parsed line-wise. The tests do not just mirror the file:

  1. `audit(text)` encodes the policy (inert trigger, no PR activation, no
     secrets/actions/permissions, no direct mypy, one hash-enforced install,
     env-only expressions, pinned hashes equal to the committed files). The
     committed workflow must audit clean AND each deliberate tamper/drift of
     it (PR trigger, dispatch, wildcard/default branch, stale pin, action
     reference, secret, interpolation into a script body, direct mypy,
     weakened install, rc 1/rc 2 treated as success) must be flagged.
  2. The guard step and the final wrapper step are EXECUTED under bash with
     stubs: wrong event/ref/sha is denied; a wrong pin is denied; wrapper rc
     0 with the exact success text passes, while rc 1, rc 2, other codes, rc 0
     without the success text and rc 0 with a DENY line all fail.
  3. The candidate branch named in the trigger must not exist in this
     repository (no accidental activation).
"""
import hashlib
import os
import re
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "typecheck-required-candidate.yml"

CANDIDATE_BRANCH = "candidate-only/typecheck-required-never-created"
WRAPPER_SHA256 = "1a5df02b6c0ddd69a90c46adb62c81e3adb0b2ba162484fa2180b14ec665399c"
PINS = {
    "WRAPPER_SHA256": ("tools/run_scoped_mypy.py", WRAPPER_SHA256),
    "ASSERT_SHA256": ("tools/assert_ci_python313.py", None),
    "LOCK_SHA256": ("backend/requirements-typecheck-linux-x86_64-cp313.lock.txt", None),
}
ALLOWED_EXPRESSIONS = {
    "github.event_name", "github.ref", "github.sha", "github.server_url", "github.repository",
}
FORBIDDEN_TRIGGERS = {
    "pull_request", "pull_request_target", "workflow_dispatch", "schedule", "workflow_run",
    "workflow_call", "repository_dispatch", "release", "issue_comment", "merge_group",
}


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def code_lines(text):
    """Lines with full-line comments removed (header prose mentions forbidden words)."""
    return [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]


def trigger_block(text):
    lines = code_lines(text)
    out, inside = [], False
    for ln in lines:
        if re.match(r"^on:\s*$", ln):
            inside = True
            continue
        if inside and re.match(r"^\S", ln):
            break
        if inside:
            out.append(ln)
    return out


def steps(text):
    """[(name, env_lines, run_script)] in order."""
    lines = code_lines(text)
    found, cur = [], None
    for ln in lines:
        m = re.match(r"^      - name: (.*)$", ln)
        if m:
            cur = {"name": m.group(1), "body": []}
            found.append(cur)
        elif cur is not None:
            cur["body"].append(ln)
    result = []
    for step in found:
        body = step["body"]
        run, env, mode = [], [], None
        for ln in body:
            if re.match(r"^        run: \|\s*$", ln):
                mode = "run"
            elif re.match(r"^        env:\s*$", ln):
                mode = "env"
            elif re.match(r"^        \S", ln):
                mode = None
            elif mode == "run":
                run.append(ln[10:] if ln.startswith(" " * 10) else ln.strip())
            elif mode == "env":
                env.append(ln)
        result.append((step["name"], env, "\n".join(run) + "\n"))
    return result


def audit(text):
    """Return a list of policy violations (empty means the candidate is sound)."""
    bad = []
    code = "\n".join(code_lines(text))
    joined = re.sub(r"\\\n\s*", " ", code)  # shell line continuations folded

    # --- inert trigger --------------------------------------------------
    tb = trigger_block(text)
    keys = [m.group(1) for ln in tb if (m := re.match(r"^  ([A-Za-z_]+):", ln))]
    if keys != ["push"]:
        bad.append(f"trigger keys are {keys}, expected exactly ['push']")
    if set(keys) & FORBIDDEN_TRIGGERS:
        bad.append("forbidden trigger present")
    for word in FORBIDDEN_TRIGGERS:
        if re.search(rf"(^|\s){word}\s*:", "\n".join(tb)):
            bad.append(f"forbidden trigger {word}")
    if re.search(r"^on:[ \t]*\S", code, re.MULTILINE):
        bad.append("inline/non-block on: form")
    branches = [m.group(1).strip().strip("'\"") for ln in tb if (m := re.match(r"^\s+- (.+)$", ln))]
    if branches != [CANDIDATE_BRANCH]:
        bad.append(f"branches are {branches}, expected only the candidate-only branch")
    if any(k in "\n".join(tb) for k in ("paths", "tags", "branches-ignore", "*")):
        bad.append("trigger uses wildcard/tags/paths/ignore")
    if "main" in branches or "master" in branches:
        bad.append("default branch is a trigger")

    # --- no authority ---------------------------------------------------
    if not re.search(r"^permissions: \{\}\s*$", code, re.MULTILINE):
        bad.append("top-level permissions: {} missing")
    if len(re.findall(r"\bpermissions\s*:", code)) != 1:
        bad.append("extra permissions key")
    for pat, why in ((r"\bsecrets\.", "secret reference"), (r"GITHUB_TOKEN", "token reference"),
                     (r"^\s*-?\s*uses\s*:", "action reference"), (r"id-token", "oidc permission"),
                     (r"\bcontainer\s*:|\bservices\s*:", "container/services"),
                     (r"upload-artifact|download-artifact|actions/cache", "artifact/cache action"),
                     (r"\b(curl|wget)\b", "ad-hoc download"),
                     (r"\bgit\s+(clone|pull)\b|--branch\b|refs/heads/(main|master)\b.*fetch", "ref drift"),
                     (r"\bFETCH_HEAD\b.*\b(main|master)\b", "ref drift")):
        if re.search(pat, code, re.MULTILINE):
            bad.append(why)

    # --- expressions only in env, from the allowlist --------------------
    for ln in code_lines(text):
        for expr in re.findall(r"\$\{\{\s*(.*?)\s*\}\}", ln):
            if expr not in ALLOWED_EXPRESSIONS:
                bad.append(f"expression not allowlisted: {expr}")
            if not re.match(r"^          [A-Z_]+: \$\{\{ [a-z_.]+ \}\}(/\$\{\{ [a-z_.]+ \}\}\.git)?$", ln) \
               and not re.match(r"^          [A-Z_]+: \$\{\{ [a-z_.]+ \}\}.*$", ln):
                bad.append(f"expression outside an env mapping: {ln.strip()}")
    for name, _env, script in steps(text):
        if "${{" in script:
            bad.append(f"expression interpolated into script body of '{name}'")

    # --- exact head fetch, no drift ------------------------------------
    for needle in ('[[ "$HEAD_SHA" =~ ^[0-9a-f]{40}$ ]]', "fetch -q --no-tags --depth=1",
                   'rev-parse HEAD)" == "$HEAD_SHA"', 'refs/heads/' + CANDIDATE_BRANCH,
                   '"$EVENT_NAME" == "push"'):
        if needle not in code:
            bad.append(f"fetch/ref guard missing: {needle}")

    # --- pinned hashes equal the committed files -------------------------
    for env_name, (rel, fixed) in PINS.items():
        m = re.search(rf"^\s+{env_name}: ([0-9a-f]{{64}})\s*$", code, re.MULTILINE)
        actual = sha256_of(REPO / rel)
        if not m:
            bad.append(f"{env_name} pin missing")
        elif m.group(1) != actual:
            bad.append(f"{env_name} pin {m.group(1)} != committed {rel} {actual}")
        if fixed and (not m or m.group(1) != fixed):
            bad.append(f"{env_name} is not the CAP-012 approved value")

    # --- install: exactly one, hash-enforced, lock only -------------------
    installs = re.findall(r"pip install\b", code)
    if len(installs) != 1:
        bad.append(f"expected exactly one pip install, found {len(installs)}")
    for flag in ("--require-hashes", "--only-binary=:all:", "--no-deps", '-r "$lock"', "--no-cache-dir"):
        if flag not in code:
            bad.append(f"install flag missing: {flag}")
    if re.search(r"pip install[^\n]*(--upgrade|-U\b|--pre\b|--extra-index-url|--find-links|-e\b|--no-verify)", joined):
        bad.append("weakened install flag")

    # --- never mypy directly; the wrapper is the only entry ---------------
    if re.search(r"-m\s+mypy\b|\bmypy\s+(--|app|backend)|bin/mypy", code):
        bad.append("direct mypy invocation")
    if code.count('tools/run_scoped_mypy.py"') < 1 or "-I \"$head/tools/run_scoped_mypy.py\"" not in code:
        bad.append("wrapper not invoked isolated from the fetched head")

    # --- rc handling: only 0 passes --------------------------------------
    if not re.search(r"^\s+0\) ;;\s*$", code, re.MULTILINE):
        bad.append("rc 0 arm missing")
    for arm in ("1)", "2)", "*)"):
        m = re.search(rf"^\s+{re.escape(arm)} .*$", code, re.MULTILINE)
        if not m or "exit 1" not in m.group(0):
            bad.append(f"rc arm {arm} does not exit 1")

    # --- claims wording ---------------------------------------------------
    if "NO GATE CREDIT" not in text:
        bad.append("no-gate-credit wording missing")
    return bad


def tamper(text, old, new, count=1):
    assert old in text, f"tamper anchor absent: {old!r}"
    return text.replace(old, new, count)


class FakeBash:
    """Run an extracted step script under bash with a scratch RUNNER_TEMP."""

    @staticmethod
    def run(script, env, cwd):
        full = {"PATH": os.environ["PATH"], "HOME": str(cwd)}
        full.update(env)
        return subprocess.run(["bash", "-c", script], env=full, cwd=cwd, capture_output=True,
                              text=True, timeout=60)


def step_script(name_prefix):
    for name, _env, script in steps(WORKFLOW.read_text(encoding="utf-8")):
        if name.startswith(name_prefix):
            return script
    raise AssertionError(f"step not found: {name_prefix}")


class AuditPolicyTest(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_committed_candidate_audits_clean(self):
        self.assertEqual(audit(self.text), [])

    def test_pinned_wrapper_is_the_cap012_approved_hash(self):
        self.assertEqual(sha256_of(REPO / "tools/run_scoped_mypy.py"), WRAPPER_SHA256)

    def test_tampers_are_flagged(self):
        t = self.text
        cases = {
            "pull_request trigger": tamper(t, "on:\n  push:", "on:\n  pull_request:\n  push:"),
            "workflow_dispatch": tamper(t, "on:\n  push:", "on:\n  workflow_dispatch:\n  push:"),
            "default branch": tamper(t, f"      - {CANDIDATE_BRANCH}", "      - main"),
            "wildcard branch": tamper(t, f"      - {CANDIDATE_BRANCH}", f"      - {CANDIDATE_BRANCH}\n      - '**'"),
            "extra branch": tamper(t, f"      - {CANDIDATE_BRANCH}", f"      - {CANDIDATE_BRANCH}\n      - other"),
            "stale wrapper pin": tamper(t, WRAPPER_SHA256, "0" * 64),
            "stale lock pin": tamper(t, re.search(r"LOCK_SHA256: ([0-9a-f]{64})", t).group(1), "1" * 64),
            "action reference": tamper(t, "    steps:\n", "    steps:\n      - uses: actions/checkout@v4\n"),
            "secret reference": tamper(t, "HEAD_SHA: ${{ github.sha }}", "HEAD_SHA: ${{ secrets.X }}"),
            "broad permissions": tamper(t, "\npermissions: {}\n", "\npermissions: write-all\n"),
            "pr head sha expr": tamper(t, "HEAD_SHA: ${{ github.sha }}",
                                       "HEAD_SHA: ${{ github.event.pull_request.head.sha }}"),
            "interpolation into script": tamper(t, 'echo "pinned head sha: $HEAD_SHA"',
                                                'echo "pinned head sha: ${{ github.head_ref }}"'),
            "direct mypy": tamper(t, '"$venv/bin/python" -I "$head/tools/run_scoped_mypy.py"',
                                  '"$venv/bin/python" -m mypy backend/app'),
            "dropped hash enforcement": tamper(t, "            --require-hashes --only-binary", "            --only-binary"),
            "extra index": tamper(t, "--no-deps \\\n", "--no-deps --extra-index-url https://example.invalid/simple \\\n"),
            "rc2 accepted": re.sub(r"(\n\s+2\) )echo [^\n]*", r"\1;;", t),
            "rc1 accepted": re.sub(r"(\n\s+1\) )echo [^\n]*", r"\1;;", t),
            "default rc accepted": re.sub(r"(\n\s+\*\) )echo [^\n]*", r"\1;;", t),
            "no-gate wording dropped": t.replace("NO GATE CREDIT", "gate"),
        }
        for label, mutated in cases.items():
            with self.subTest(label):
                self.assertNotEqual(mutated, t, "tamper was a no-op")
                self.assertNotEqual(audit(mutated), [], f"tamper not detected: {label}")

    def test_candidate_branch_does_not_exist(self):
        if shutil.which("git") is None:
            self.skipTest("git unavailable")
        out = subprocess.run(["git", "for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes",
                              "refs/tags"], cwd=REPO, capture_output=True, text=True)
        if out.returncode != 0:
            self.skipTest("not a git checkout")
        for ref in out.stdout.split():
            self.assertNotIn("typecheck-required", ref, f"candidate ref exists: {ref}")


class GuardStepsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tcrc-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.script = step_script("Deny unless candidate-only ref")

    def _env(self, **kw):
        base = {"EVENT_NAME": "push", "REF": f"refs/heads/{CANDIDATE_BRANCH}", "HEAD_SHA": "a" * 40,
                "REPO_URL": "file:///nonexistent-repo.git", "RUNNER_TEMP": str(self.tmp)}
        base.update(kw)
        return base

    def test_wrong_event_ref_or_sha_is_denied_before_any_fetch(self):
        for label, env, msg in (
            ("pull_request event", {"EVENT_NAME": "pull_request"}, "event is not push"),
            ("workflow_dispatch event", {"EVENT_NAME": "workflow_dispatch"}, "event is not push"),
            ("main ref", {"REF": "refs/heads/main"}, "not the candidate-only branch"),
            ("pr merge ref", {"REF": "refs/pull/7/merge"}, "not the candidate-only branch"),
            ("prefix-only ref", {"REF": f"refs/heads/{CANDIDATE_BRANCH}-x"}, "not the candidate-only branch"),
            ("short sha", {"HEAD_SHA": "abc123"}, "not 40-hex"),
            ("branch name as sha", {"HEAD_SHA": "main"}, "not 40-hex"),
        ):
            with self.subTest(label):
                r = FakeBash.run(self.script, self._env(**env), self.tmp)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(msg, r.stderr)
                self.assertFalse((self.tmp / "head").exists(), "fetch started despite a denial")

    def test_exact_sha_fetch_succeeds_and_other_sha_fails(self):
        if shutil.which("git") is None:
            self.skipTest("git unavailable")
        repo = self.tmp / "src"
        repo.mkdir()
        g = lambda *a: subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True)
        g("init", "-q")
        g("config", "user.email", "t@example.invalid")
        g("config", "user.name", "t")
        g("config", "uploadpack.allowAnySHA1InWant", "true")
        (repo / "f").write_text("x")
        g("add", "f")
        g("commit", "-q", "-m", "one")
        sha = g("rev-parse", "HEAD").stdout.strip()
        r = FakeBash.run(self.script, self._env(HEAD_SHA=sha, REPO_URL=f"file://{repo}"), self.tmp)
        if r.returncode != 0 and "not our ref" in r.stderr:
            self.skipTest("local git transport refuses fetch by sha")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"pinned head sha: {sha}", r.stdout)
        self.assertIn("NO GATE CREDIT", r.stdout)
        shutil.rmtree(self.tmp / "head")
        r = FakeBash.run(self.script, self._env(HEAD_SHA="b" * 40, REPO_URL=f"file://{repo}"), self.tmp)
        self.assertNotEqual(r.returncode, 0)


@unittest.skipUnless(shutil.which("bash"), "bash required")
class PinGuardStepTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tcrc-pin-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        head = self.tmp / "head"
        for rel, _ in PINS.values():
            dest = head / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / rel, dest)
        (head / "backend/app").mkdir(parents=True, exist_ok=True)
        (head / "backend/pyproject.toml").write_text("[tool.mypy]\n")
        # sha256sum may be absent (macOS); provide an equivalent shim when so.
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        if shutil.which("sha256sum") is None:
            shim = self.bin / "sha256sum"
            shim.write_text('#!/bin/bash\nexec shasum -a 256 "$@"\n')
            shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
        self.script = step_script("Guard pinned inputs")

    def _run(self, **over):
        env = {"RUNNER_TEMP": str(self.tmp), "PATH": f"{self.bin}:{os.environ['PATH']}",
               "WRAPPER_SHA256": WRAPPER_SHA256, "ASSERT_SHA256": sha256_of(REPO / PINS["ASSERT_SHA256"][0]),
               "LOCK_SHA256": sha256_of(REPO / PINS["LOCK_SHA256"][0])}
        env.update(over)
        return FakeBash.run(self.script, env, self.tmp)

    def test_matching_pins_pass(self):
        r = self._run()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_drifted_wrapper_bytes_are_denied(self):
        with open(self.tmp / "head/tools/run_scoped_mypy.py", "ab") as fh:
            fh.write(b"# drift\n")
        r = self._run()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("sha256", r.stderr)

    def test_wrong_pin_values_and_symlinks_are_denied(self):
        for var in PINS:
            with self.subTest(var):
                self.assertNotEqual(self._run(**{var: "0" * 64}).returncode, 0)
        wrapper = self.tmp / "head/tools/run_scoped_mypy.py"
        real = self.tmp / "real_wrapper.py"
        shutil.copy2(wrapper, real)
        wrapper.unlink()
        wrapper.symlink_to(real)
        r = self._run()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("symlink", r.stderr)

    def test_committed_venv_dir_or_missing_lock_is_denied(self):
        (self.tmp / "head/backend/.venv").mkdir()
        self.assertNotEqual(self._run().returncode, 0)
        shutil.rmtree(self.tmp / "head/backend/.venv")
        (self.tmp / "head" / PINS["LOCK_SHA256"][0]).unlink()
        self.assertNotEqual(self._run().returncode, 0)


@unittest.skipUnless(shutil.which("bash"), "bash required")
class WrapperStepOutcomeTest(unittest.TestCase):
    """Run the real final-step script against a stub interpreter standing in for the wrapper run."""

    SUCCESS = ('{"plan": "json"}\nSuccess: no issues found in 25 source files\n'
               "run_scoped_mypy: rc=0 — no type errors\n")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tcrc-wrap-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "head/backend/app").mkdir(parents=True)
        (self.tmp / "head/tools").mkdir(parents=True)
        (self.tmp / "venv-typecheck/bin").mkdir(parents=True)
        self.script = step_script("Scoped wrapper on the fetched backend/app")

    def _stub(self, rc, output):
        stub = self.tmp / "venv-typecheck/bin/python"
        (self.tmp / "payload.txt").write_text(output, encoding="utf-8")
        stub.write_text(f'#!/bin/bash\ncat "{self.tmp}/payload.txt"\nexit {rc}\n')
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
        link = self.tmp / "head/backend/.venv"
        if link.is_symlink():
            link.unlink()

    def _run(self, rc, output):
        self._stub(rc, output)
        return FakeBash.run(self.script, {"RUNNER_TEMP": str(self.tmp)}, self.tmp)

    def test_rc0_with_exact_success_passes(self):
        r = self._run(0, self.SUCCESS)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("NO GATE CREDIT", r.stdout)
        self.assertTrue((self.tmp / "head/backend/.venv").is_symlink())

    def test_rc1_type_errors_fail(self):
        r = self._run(1, "app/x.py:1: error: boom\nFound 1 error in 1 file\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("rc 1", r.stderr)

    def test_rc2_denial_fails(self):
        r = self._run(2, "DENY: scope\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("rc 2", r.stderr)

    def test_other_codes_fail(self):
        for rc in (3, 127, 255):
            with self.subTest(rc=rc):
                self.assertNotEqual(self._run(rc, self.SUCCESS).returncode, 0)

    def test_rc0_without_exact_success_text_fails(self):
        for label, out in (
            ("empty", ""),
            ("zero files", "Success: no issues found in 0 source files\nrun_scoped_mypy: rc=0 — ok\n"),
            ("no marker", "Success: no issues found in 25 source files\n"),
            ("no success line", "run_scoped_mypy: rc=0 — ok\n"),
            ("DENY line present", self.SUCCESS + "DENY: something\n"),
        ):
            with self.subTest(label):
                self.assertNotEqual(self._run(0, out).returncode, 0)


if __name__ == "__main__":
    unittest.main()
