#!/usr/bin/env python3
"""
Focused behavioral tests for two assertions in
.github/workflows/typecheck-qualification-drill.yml (MOD-001, CAP-012
synthetic Linux CI drill; authored-only, no live run exists).

Synthetic only: no network, no mypy, no Veyro source is type-checked. Each
test extracts the real step script from the workflow text (no YAML parser is
available in the project venv) so a regression in the workflow itself fails
here:

  1. Negative proof 1's diagnostic grep must match what real pip prints for a
     hash mismatch. pip emits "THESE PACKAGES DO NOT MATCH THE HASHES ..." in
     upper case; a case-sensitive grep false-reds the drill on a correct
     refusal. Exercised against genuine pip output (offline, synthetic wheel).
  2. Negative proof 2 must stay deterministic if the runner's default
     python3 becomes 3.13: it must fall through to another non-3.13
     interpreter, and fail closed (never pass) if none resolves. Exercised
     with stub interpreters on an isolated PATH.

Run with the project venv interpreter. A local run is NOT evidence about
GitHub-hosted runner behaviour (host bash and pip versions differ).
"""

import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "typecheck-qualification-drill.yml"
BASH = "/bin/bash"


def step_script(name_prefix):
    """Return the dedented `run: |` body of the step whose name starts with prefix."""
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    start = next(
        i for i, ln in enumerate(lines) if ln.strip().startswith(f"- name: {name_prefix}")
    )
    run = next(i for i in range(start, len(lines)) if lines[i].strip() == "run: |")
    body = []
    for ln in lines[run + 1 :]:
        if ln.strip() and not ln.startswith(" " * 10):
            break
        body.append(ln)
    return textwrap.dedent("\n".join(body)) + "\n"


def make_stub(path, version, allow):
    """Stub interpreter: answers the -c version query, and the assertion script."""
    verdict = (
        'echo "version_is_3_13: PASS"; echo "RESULT: ALLOW"; exit 0'
        if allow
        else 'echo "version_is_3_13: FAIL (observed=%s)"; echo "RESULT: DENY"; exit 1' % version
    )
    path.write_text(
        '#!/bin/bash\n'
        'if [[ "$*" == *"-c"* ]]; then echo "%s"; exit 0; fi\n'
        '%s\n' % (version, verdict)
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class NegativeOneDiagnosticTests(unittest.TestCase):
    def test_grep_matches_real_pip_hash_mismatch_output(self):
        script = step_script("Negative proof 1")
        match = re.search(r"grep (-[A-Za-z]+) '([^']*do not match the hashes[^']*)' >/dev/null", script, re.I)
        self.assertIsNotNone(match, "diagnostic grep not found in workflow step")
        flags, pattern = match.groups()

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            wheel = tmp / "probe_pkg-1.0-py3-none-any.whl"
            with zipfile.ZipFile(wheel, "w") as z:
                z.writestr("probe_pkg/__init__.py", "")
                z.writestr(
                    "probe_pkg-1.0.dist-info/METADATA",
                    "Metadata-Version: 2.1\nName: probe-pkg\nVersion: 1.0\n",
                )
                z.writestr(
                    "probe_pkg-1.0.dist-info/WHEEL",
                    "Wheel-Version: 1.0\nGenerator: t\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
                )
                z.writestr("probe_pkg-1.0.dist-info/RECORD", "")
            req = tmp / "req.txt"
            req.write_text("probe-pkg==1.0 --hash=sha256:" + "0" * 64 + "\n")
            env = {k: v for k, v in os.environ.items() if not k.startswith("PIP_")}
            env["PIP_CONFIG_FILE"] = os.devnull
            proc = subprocess.run(
                [
                    sys.executable, "-m", "pip", "install", "--require-hashes",
                    "--only-binary=:all:", "--no-deps", "--no-index",
                    "--find-links", str(tmp), "--no-cache-dir", "--no-input",
                    "--disable-pip-version-check", "--target", str(tmp / "t"),
                    "-r", str(req),
                ],
                capture_output=True, text=True, env=env, cwd=tmp,
            )
            if "hash" not in (proc.stdout + proc.stderr).lower():
                self.skipTest("pip unavailable in this interpreter: " + proc.stderr[:200])
            self.assertNotEqual(proc.returncode, 0)
            out = proc.stdout + proc.stderr
            grep = subprocess.run(
                ["grep", flags, pattern], input=out, capture_output=True, text=True
            )
            self.assertEqual(grep.returncode, 0, "workflow grep misses real pip output:\n" + out)


class NegativeTwoDeterminismTests(unittest.TestCase):
    def run_step(self, stubs):
        """stubs: {command_name: (reported_version, assertion_allows)}."""
        script = step_script("Negative proof 2")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            bindir, tools = tmp / "bin", tmp / "tools"
            bindir.mkdir()
            tools.mkdir()
            os.symlink(shutil.which("grep"), tools / "grep")
            for name, (version, allow) in stubs.items():
                make_stub(bindir / name, version, allow)
            (tmp / "head" / "tools").mkdir(parents=True)
            (tmp / "head" / "tools" / "assert_ci_python313.py").write_text("")
            env = {"PATH": f"{bindir}:{tools}", "RUNNER_TEMP": str(tmp)}
            return subprocess.run(
                [BASH, "-c", script], capture_output=True, text=True, env=env, cwd=tmp
            )

    def test_default_non_313_python_is_used_and_denied(self):
        proc = self.run_step({"python3": ("3.12", False)})
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("negative interpreter:", proc.stdout)

    def test_default_python_becoming_313_falls_through_to_non_313(self):
        proc = self.run_step({"python3": ("3.13", True), "python3.12": ("3.12", False)})
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("skip", proc.stdout)
        self.assertRegex(proc.stdout, r"negative interpreter: \S*python3\.12 ")

    def test_only_313_available_fails_closed(self):
        proc = self.run_step({"python3": ("3.13", True)})
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("no resolvable non-3.13 python", proc.stderr)

    def test_no_interpreter_at_all_fails_closed(self):
        proc = self.run_step({})
        self.assertNotEqual(proc.returncode, 0)

    def test_non_313_that_wrongly_allows_is_denied(self):
        proc = self.run_step({"python3": ("3.12", True)})
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("unexpectedly satisfies", proc.stderr)


if __name__ == "__main__":
    unittest.main()
