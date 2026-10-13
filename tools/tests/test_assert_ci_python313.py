#!/usr/bin/env python3
"""
Unit test for tools/assert_ci_python313.py (MOD-001, M1-C-06 B2/B9).

Pure-function positive/negative cases with injected values; no live
interpreter dependence except the final subprocess exit-code check, which
only asserts the exit code agrees with the host's own live verdict.
"""

import subprocess
import sys
import sysconfig
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import assert_ci_python313 as mod  # noqa: E402

GOOD = ("cpython", (3, 13, 5, "final", 0), "linux-x86_64", 2**63 - 1)


def run(*args):
    return mod.check_interpreter(*args)


def failed(results):
    return {name for name, passed, _ in results if not passed}


class CheckInterpreterTests(unittest.TestCase):
    def test_all_good_allows(self):
        self.assertTrue(mod.all_passed(run(*GOOD)))

    def test_platform_prefix_variant_allows(self):
        self.assertTrue(mod.all_passed(run(GOOD[0], GOOD[1], "linux-x86_64-extra", GOOD[3])))

    def test_pypy_denied(self):
        self.assertEqual(failed(run("pypy", *GOOD[1:])), {"implementation_is_cpython"})

    def test_python_312_denied(self):
        self.assertEqual(failed(run(GOOD[0], (3, 12, 1), GOOD[2], GOOD[3])), {"version_is_3_13"})

    def test_python_314_denied(self):
        self.assertEqual(failed(run(GOOD[0], (3, 14, 5), GOOD[2], GOOD[3])), {"version_is_3_13"})

    def test_macos_denied(self):
        self.assertEqual(
            failed(run(GOOD[0], GOOD[1], "macosx-14.0-arm64", GOOD[3])),
            {"platform_is_linux_x86_64"},
        )

    def test_linux_aarch64_denied(self):
        self.assertEqual(
            failed(run(GOOD[0], GOOD[1], "linux-aarch64", GOOD[3])),
            {"platform_is_linux_x86_64"},
        )

    def test_32_bit_denied(self):
        self.assertEqual(failed(run(GOOD[0], GOOD[1], GOOD[2], 2**31 - 1)), {"is_64_bit"})

    def test_maxsize_boundary_denied(self):
        self.assertEqual(failed(run(GOOD[0], GOOD[1], GOOD[2], 2**32)), {"is_64_bit"})

    def test_malformed_inputs_denied_not_raised(self):
        results = run(None, None, None, None)
        self.assertEqual(len(results), 4)
        self.assertFalse(mod.all_passed(results))
        self.assertEqual(len(failed(results)), 4)

    def test_bool_maxsize_denied(self):
        self.assertEqual(failed(run(GOOD[0], GOOD[1], GOOD[2], True)), {"is_64_bit"})

    def test_empty_results_denied(self):
        self.assertFalse(mod.all_passed([]))

    def test_every_check_reported_without_short_circuit(self):
        self.assertEqual(len(run("pypy", (3, 12), "macosx", 1)), 4)
        self.assertEqual(len(failed(run("pypy", (3, 12), "macosx", 1))), 4)


class LiveMainTests(unittest.TestCase):
    def test_exit_code_matches_live_verdict(self):
        live = mod.all_passed(
            mod.check_interpreter(
                sys.implementation.name,
                sys.version_info,
                sysconfig.get_platform(),
                sys.maxsize,
            )
        )
        proc = subprocess.run(
            [sys.executable, "-I", str(TOOLS / "assert_ci_python313.py")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0 if live else 1)
        self.assertIn(sys.executable, proc.stdout)
        self.assertIn("RESULT: " + ("ALLOW" if live else "DENY"), proc.stdout)


if __name__ == "__main__":
    unittest.main()
