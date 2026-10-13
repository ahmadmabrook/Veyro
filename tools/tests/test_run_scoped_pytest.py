"""
Synthetic refusal/argv tests for tools/run_scoped_pytest.py (MOD-001, M1-C-07).

Written as `unittest.TestCase` and verified with `python -m unittest`, not with
pytest: CAP-011 is `QUALIFIED — NOT APPROVED`, so this session may not invoke
pytest on any Veyro test, config, import or source. That constraint also shapes
*what* is tested here — every case either refuses before a process starts, or
asserts the argv/exit/version classification as pure data. No test starts
pytest, and no test points the runner at the real repository: each builds its
own repo-shaped tree under a fresh `mkdtemp` and passes it as `repo_root`.

What that leaves unverified, deliberately and on the record: the two
subprocess calls in `run()` (the `--version` probe and the pytest run itself)
are exercised by no test here, because exercising them would mean invoking
pytest. Their *inputs* (`Plan.argv`, `child_env`) and their *outputs*
(`classify_version`, `classify_exit`) are covered; the calls between them are
inspection-only until CAP-011 is independently approved.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run_scoped_pytest import (  # noqa: E402
    EXIT_DENIED,
    EXIT_OK,
    EXIT_TEST_FAILURES,
    EXPECTED_PYTEST_VERSION,
    SUITES,
    Denied,
    _canonical,
    ambient_denials,
    child_env,
    classify_exit,
    classify_version,
    plan,
)

BACKEND_LAYERS = ("unit", "component", "contract", "integration")
IDEMPOTENCY_REL = "tools/tests/test_validate_idempotency_contract.py"
# A clean environment for `plan()`: the real one may legitimately carry
# PYTEST_*/PYTHONPATH, which is exactly what the runner refuses, so the
# non-ambient cases must state their environment rather than inherit it.
CLEAN_ENV = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C.UTF-8"}


def build_tree(root: Path) -> None:
    """A repository-shaped synthetic tree holding every allowlisted suite."""
    (root / "backend").mkdir()
    (root / "backend" / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
    )
    for layer in BACKEND_LAYERS:
        suite = root / "backend" / "tests" / layer
        suite.mkdir(parents=True)
        (suite / "test_synthetic.py").write_text("def test_ok():\n    assert True\n")
    idempotency = root / IDEMPOTENCY_REL
    idempotency.parent.mkdir(parents=True)
    idempotency.write_text("def test_ok():\n    assert True\n")


class ScopedPytestRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        # `.resolve()` because macOS `/var` is itself a symlink to `/private/var`
        # and the runner refuses a path that does not canonicalise to itself.
        self.root = Path(tempfile.mkdtemp(prefix="veyro-m1c07-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        build_tree(self.root)

    def _plan(self, name: str, env: dict[str, str] | None = None):
        return plan(name, repo_root=self.root, env=env if env is not None else CLEAN_ENV)

    # --- the allowlist itself -------------------------------------------------

    def test_allowlist_is_exactly_the_five_reviewed_suites(self) -> None:
        """Table drift is the one way this tool could silently widen scope."""
        self.assertEqual(
            sorted(SUITES),
            [
                "backend-component",
                "backend-contract",
                "backend-integration",
                "backend-unit",
                "idempotency-contract",
            ],
        )
        for layer in BACKEND_LAYERS:
            suite = SUITES[f"backend-{layer}"]
            self.assertEqual(suite.target, f"backend/tests/{layer}")
            self.assertTrue(suite.is_dir)
            self.assertEqual(
                (suite.cwd, suite.config, suite.rootdir, suite.confcutdir),
                ("backend", "backend/pyproject.toml", "backend", "backend"),
            )
        idempotency = SUITES["idempotency-contract"]
        self.assertEqual(idempotency.target, IDEMPOTENCY_REL)
        self.assertFalse(idempotency.is_dir)
        self.assertEqual(idempotency.confcutdir, "tools/tests")

    def test_unknown_suite_is_refused(self) -> None:
        for name in ("backend-harness", "backend/tests/unit", "", "backend-e2e"):
            with self.assertRaises(Denied) as caught:
                self._plan(name)
            self.assertIn("unknown suite", str(caught.exception))

    # --- argv shape ----------------------------------------------------------

    def test_backend_argv_carries_the_explicit_config_root_confcutdir_and_no_cache(self) -> None:
        current = self._plan("backend-unit")
        argv = current.argv("/venv/bin/python")
        backend = self.root / "backend"
        self.assertEqual(
            argv,
            [
                "/venv/bin/python",
                "-E",
                "-s",
                "-B",
                "-m",
                "pytest",
                "-c",
                str(backend / "pyproject.toml"),
                f"--rootdir={backend}",
                f"--confcutdir={backend}",
                "-p",
                "no:cacheprovider",
                "-rs",
                str(backend / "tests" / "unit"),
            ],
        )
        self.assertEqual(current.cwd, backend)
        # The target is last and absolute, so nothing can be appended behind it
        # and no relative path is resolved against an inherited cwd.
        self.assertTrue(Path(argv[-1]).is_absolute())
        self.assertNotIn("/dev/null", argv)

    def test_idempotency_argv_targets_exactly_the_single_file(self) -> None:
        current = self._plan("idempotency-contract")
        argv = current.argv("/venv/bin/python")
        self.assertEqual(argv[-1], str(self.root / IDEMPOTENCY_REL))
        self.assertEqual(current.cwd, self.root)
        self.assertEqual(current.confcutdir, self.root / "tools" / "tests")
        self.assertEqual(current.config, self.root / "backend" / "pyproject.toml")
        self.assertEqual(current.collected_files, 1)

    def test_every_suite_plans_with_absolute_canonical_paths(self) -> None:
        for name in SUITES:
            current = self._plan(name)
            for path in (current.cwd, current.target, current.config,
                         current.rootdir, current.confcutdir):
                self.assertTrue(path.is_absolute(), f"{name}: {path}")
                self.assertEqual(path, path.resolve(), f"{name}: {path}")
                self.assertTrue(
                    path == self.root or self.root in path.parents, f"{name}: {path}"
                )

    # --- missing / empty suites ---------------------------------------------

    def test_missing_suite_directory_is_refused(self) -> None:
        shutil.rmtree(self.root / "backend" / "tests" / "contract")
        with self.assertRaises(Denied) as caught:
            self._plan("backend-contract")
        self.assertIn("missing directory", str(caught.exception))

    def test_missing_suite_file_is_refused(self) -> None:
        (self.root / IDEMPOTENCY_REL).unlink()
        with self.assertRaises(Denied) as caught:
            self._plan("idempotency-contract")
        self.assertIn("missing file", str(caught.exception))

    def test_suite_directory_with_no_test_file_is_refused(self) -> None:
        """A suite that collects nothing would otherwise pass by omission."""
        suite = self.root / "backend" / "tests" / "unit"
        (suite / "test_synthetic.py").unlink()
        (suite / "helper.py").write_text("VALUE = 1\n")
        with self.assertRaises(Denied) as caught:
            self._plan("backend-unit")
        self.assertIn("no test_*.py", str(caught.exception))

    def test_missing_config_is_refused(self) -> None:
        (self.root / "backend" / "pyproject.toml").unlink()
        with self.assertRaises(Denied) as caught:
            self._plan("backend-unit")
        self.assertIn("pyproject.toml", str(caught.exception))

    # --- symlink escape ------------------------------------------------------

    def test_symlinked_suite_directory_is_refused(self) -> None:
        """The drill's §4.1 finding: pytest executes whatever path it is given."""
        outside = self.root.parent / f"{self.root.name}-outside"
        outside.mkdir()
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        (outside / "test_evil.py").write_text("def test_evil():\n    assert False\n")
        suite = self.root / "backend" / "tests" / "unit"
        shutil.rmtree(suite)
        suite.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(Denied) as caught:
            self._plan("backend-unit")
        self.assertIn("symlink refused in the path to the suite", str(caught.exception))

    def test_symlinked_parent_in_the_path_to_the_suite_is_refused(self) -> None:
        outside = self.root.parent / f"{self.root.name}-tests"
        (outside / "unit").mkdir(parents=True)
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        (outside / "unit" / "test_evil.py").write_text("def test_evil():\n    assert False\n")
        tests = self.root / "backend" / "tests"
        shutil.rmtree(tests)
        tests.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(Denied) as caught:
            self._plan("backend-unit")
        self.assertIn("symlink refused in the path to the suite", str(caught.exception))

    def test_symlinked_test_file_inside_the_suite_is_refused(self) -> None:
        outside = self.root.parent / f"{self.root.name}-file"
        outside.mkdir()
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        planted = outside / "test_evil.py"
        planted.write_text("def test_evil():\n    assert False\n")
        (self.root / "backend" / "tests" / "unit" / "test_linked.py").symlink_to(planted)
        with self.assertRaises(Denied) as caught:
            self._plan("backend-unit")
        self.assertIn("symlink inside suite", str(caught.exception))

    def test_symlinked_subdirectory_inside_the_suite_is_refused(self) -> None:
        outside = self.root.parent / f"{self.root.name}-sub"
        outside.mkdir()
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        (outside / "test_evil.py").write_text("def test_evil():\n    assert False\n")
        (self.root / "backend" / "tests" / "unit" / "linked").symlink_to(
            outside, target_is_directory=True
        )
        with self.assertRaises(Denied) as caught:
            self._plan("backend-unit")
        self.assertIn("symlink inside suite", str(caught.exception))

    def test_canonical_refuses_traversal_and_absolute_components(self) -> None:
        """No table entry can reach outside the root even if one were edited."""
        for rel in ("../outside", "backend/../../outside", "/etc", "backend//tests", "./backend"):
            with self.assertRaises(Denied) as caught:
                _canonical(self.root, rel)
            self.assertIn("unsafe relative path", str(caught.exception))

    # --- ambient pytest overrides -------------------------------------------

    def test_ambient_pytest_variables_are_refused(self) -> None:
        """The drill's G4 control: PYTEST_ADDOPTS is honoured, so it must deny."""
        for name, value in (
            ("PYTEST_ADDOPTS", "-p decoyplugin"),
            ("PYTEST_PLUGINS", "decoyplugin"),
            ("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "0"),
            ("PYTEST_DEBUG", "1"),
        ):
            with self.subTest(variable=name):
                denials = ambient_denials({**CLEAN_ENV, name: value})
                self.assertEqual(len(denials), 1, denials)
                self.assertIn(name, denials[0])
                with self.assertRaises(Denied):
                    self._plan("backend-unit", env={**CLEAN_ENV, name: value})

    def test_ambient_pythonpath_is_refused(self) -> None:
        """The drill's G1 control: a PYTHONPATH `pytest11` entry point loads."""
        denials = ambient_denials({**CLEAN_ENV, "PYTHONPATH": "/tmp/sitedecoy"})
        self.assertEqual(len(denials), 1, denials)
        self.assertIn("PYTHONPATH", denials[0])
        with self.assertRaises(Denied):
            self._plan("backend-unit", env={**CLEAN_ENV, "PYTHONPATH": "/tmp/sitedecoy"})

    def test_clean_environment_produces_no_denial(self) -> None:
        self.assertEqual(ambient_denials(CLEAN_ENV), [])
        self.assertEqual(ambient_denials({**CLEAN_ENV, "PYTHONPATH": ""}), [])
        # Deliberately strict: even `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, which is
        # what the runner itself sets, is refused when it arrives from outside.
        # The runner builds the child environment from its own allowlist, so an
        # inherited one is evidence of a configured environment, not a help.
        self.assertEqual(
            len(ambient_denials({**CLEAN_ENV, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"})), 1
        )

    def test_child_environment_is_an_allowlist_with_autoload_off(self) -> None:
        child = child_env(
            {
                **CLEAN_ENV,
                "TMPDIR": "/tmp/x",
                "PYTEST_ADDOPTS": "-x",
                "PYTHONPATH": "/decoy",
                "AWS_SECRET_ACCESS_KEY": "EXAMPLE_NOT_A_REAL_KEY",
            }
        )
        self.assertEqual(child["PYTEST_DISABLE_PLUGIN_AUTOLOAD"], "1")
        self.assertEqual(
            sorted(child),
            ["HOME", "LANG", "PATH", "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "TMPDIR"],
        )
        for leaked in ("PYTEST_ADDOPTS", "PYTHONPATH", "AWS_SECRET_ACCESS_KEY"):
            self.assertNotIn(leaked, child)

    # --- exit and version classification ------------------------------------

    def test_exit_classification_treats_4_and_5_as_denials(self) -> None:
        self.assertEqual(classify_exit(0)[0], EXIT_OK)
        self.assertEqual(classify_exit(1)[0], EXIT_TEST_FAILURES)
        for rc in (2, 3, 4, 5, -9, 127):
            self.assertEqual(classify_exit(rc)[0], EXIT_DENIED, f"rc={rc}")

    def test_version_classification_binds_the_pinned_release(self) -> None:
        self.assertIsNone(classify_version(0, f"{EXPECTED_PYTEST_VERSION}\n"))
        self.assertIsNotNone(classify_version(0, "pytest 9.1.0\n"))
        self.assertIsNotNone(classify_version(0, "pytest 8.4.2\n"))
        self.assertIsNotNone(classify_version(1, f"{EXPECTED_PYTEST_VERSION}\n"))
        self.assertIsNotNone(classify_version(0, ""))

    # --- the real repository, inspected but never executed -------------------

    def test_real_suite_targets_exist_and_are_symlink_free(self) -> None:
        """Inspection only: no pytest is started against these paths."""
        repo = Path(__file__).resolve().parents[2]
        for name, suite in SUITES.items():
            target = repo / suite.target
            self.assertEqual(target.is_dir(), suite.is_dir, name)
            self.assertTrue(target.exists(), f"{name}: {suite.target}")
            self.assertFalse(target.is_symlink(), name)
            self.assertFalse((repo / suite.config).is_symlink(), name)


if __name__ == "__main__":
    unittest.main()
