"""
Synthetic positive/negative tests for tools/run_scoped_mypy.py (MOD-001, GOV-01-R04).

Written as `unittest.TestCase`; run with the project venv interpreter. CAP-012 is
`QUALIFIED — NOT APPROVED`: these cases prove the wrapper's refusals and result
classification, not a mypy gate. Every tree is a disposable repo-shaped fixture
under the OS temp directory; no Veyro source is read or type-checked. The
`Executed*` cases start the real mypy from the project venv against those
fixtures only, and are skipped (loudly) if that venv is absent.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import run_scoped_mypy as w  # noqa: E402
from run_scoped_mypy import Denied  # noqa: E402

VENV_PYTHON = Path(__file__).resolve().parents[2] / "backend" / ".venv" / "bin" / "python"
CLEAN_ENV = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C.UTF-8"}
GOOD_PYPROJECT = '[tool.mypy]\npython_version = "3.13"\nstrict = true\n'
CLEAN_MODULE = "def add(a: int, b: int) -> int:\n    return a + b\n"


def build_tree(root: Path, pyproject: str = GOOD_PYPROJECT) -> Path:
    """Repo-shaped synthetic tree with a nested, typed `backend/app` package."""
    app = root / "backend" / "app"
    (app / "core").mkdir(parents=True)
    (root / "backend" / "pyproject.toml").write_text(pyproject)
    (app / "__init__.py").write_text("")
    (app / "core" / "__init__.py").write_text("")
    (app / "core" / "math.py").write_text(CLEAN_MODULE)
    return app


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        digest.update(str(path.relative_to(root)).encode())
        if path.is_file() and not path.is_symlink():
            digest.update(path.read_bytes())
    return digest.hexdigest()


class Base(unittest.TestCase):
    def setUp(self) -> None:
        # resolve(): macOS /var is a symlink to /private/var and the wrapper
        # refuses a path that does not canonicalise to itself.
        self.root = Path(tempfile.mkdtemp(prefix="veyro-gov01r04-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.app = build_tree(self.root)
        # Plan-only cases never start the interpreter; a synthetic venv layout suffices.
        self.fake_python = self.root / "fakevenv" / "bin" / "python"
        self.fake_python.parent.mkdir(parents=True)
        self.fake_python.write_text("#!/bin/sh\n")
        self.fake_python.chmod(0o755)
        (self.fake_python.parent.parent / "pyvenv.cfg").write_text("home = /x\n")

    def plan(self, env=None, python=None):
        return w.plan(self.root, python or self.fake_python, env if env is not None else CLEAN_ENV)

    def write_config(self, text: str) -> None:
        (self.root / "backend" / "pyproject.toml").write_text(text)

    def assertDenied(self, fragment: str, **kwargs) -> None:
        with self.assertRaises(Denied) as caught:
            self.plan(**kwargs)
        self.assertIn(fragment, str(caught.exception))


class PlanPositiveTest(Base):
    def test_exact_argv_cwd_and_count(self) -> None:
        current = self.plan()
        self.assertEqual(current.expected_sources, 3)
        self.assertEqual(current.cwd, self.root / "backend")
        self.assertEqual(
            current.argv(),
            [str(self.fake_python), "-I", "-m", "mypy", "--config-file", "pyproject.toml",
             "--cache-dir=/dev/null", "--no-color-output", "app"],
        )
        joined = " ".join(current.argv())
        for forbidden in ("plugin", "install-types", "--cache-dir=.", "MYPY"):
            self.assertNotIn(forbidden, joined)

    def test_child_env_is_exactly_three_confined_variables(self) -> None:
        env = w.child_env(Path("/h"), Path("/t"))
        self.assertEqual(env, {"PATH": "/usr/bin:/bin", "HOME": "/h", "TMPDIR": "/t"})

    def test_ignore_text_in_a_string_or_docstring_is_not_a_hiding_comment(self) -> None:
        (self.app / "core" / "doc.py").write_text(
            '"""Mentions # type: ignore and mypy: ignore-errors in prose."""\n'
            'X = "# type: ignore"\n'
        )
        self.assertEqual(self.plan().expected_sources, 4)

    def test_pycache_without_py_files_is_ignored(self) -> None:
        (self.app / "__pycache__").mkdir()
        (self.app / "__pycache__" / "x.cpython-313.pyc").write_bytes(b"\0")
        self.assertEqual(self.plan().expected_sources, 3)


class PlanRefusalTest(Base):
    def test_scope_missing_or_symlinked(self) -> None:
        shutil.rmtree(self.app)
        self.assertDenied("backend/app")

    def test_symlinked_app_dir_refused(self) -> None:
        real = self.root / "elsewhere"
        self.app.rename(real)
        self.app.symlink_to(real)
        self.assertDenied("symlink refused")

    def test_symlinked_backend_refused(self) -> None:
        (self.root / "backend").rename(self.root / "backend_real")
        (self.root / "backend").symlink_to(self.root / "backend_real")
        self.assertDenied("symlink refused")

    def test_symlinked_file_and_dir_inside_app_refused(self) -> None:
        outside = self.root / "outside.py"
        outside.write_text(CLEAN_MODULE)
        (self.app / "link.py").symlink_to(outside)
        self.assertDenied("symlink inside backend/app")
        (self.app / "link.py").unlink()
        (self.app / "linkdir").symlink_to(self.root / "backend")
        self.assertDenied("symlinked directory")

    def test_empty_tree_refused(self) -> None:
        shutil.rmtree(self.app)
        self.app.mkdir()
        self.assertDenied("no .py file")

    def test_stub_and_skipped_directory_sources_refused(self) -> None:
        (self.app / "core" / "math.pyi").write_text("def add(a: int, b: int) -> int: ...\n")
        self.assertDenied("stub file")
        (self.app / "core" / "math.pyi").unlink()
        for hidden in (".hidden", "site-packages", "node_modules"):
            (self.app / hidden).mkdir()
            (self.app / hidden / "m.py").write_text(CLEAN_MODULE)
            self.assertDenied("directory mypy skips")
            shutil.rmtree(self.app / hidden)

    def test_error_hiding_constructs_refused(self) -> None:
        cases = {
            "inline ignore": "x: int = 'a'  # type: ignore\n",
            "coded ignore": "x: int = 'a'  # type:ignore[assignment]\n",
            "after other comment": "x: int = 'a'  # noqa  # type: ignore\n",
            "file ignore-errors": "# mypy: ignore-errors\nx: int = 'a'\n",
            "inline config": "# mypy: disallow-untyped-defs=False\n",
            "no_type_check": "from typing import no_type_check\n@no_type_check\ndef f(a): ...\n",
        }
        for label, body in cases.items():
            with self.subTest(label):
                (self.app / "bad.py").write_text(body)
                self.assertDenied("bad.py")
        (self.app / "bad.py").write_text("def broken(:\n  '''unterminated\n")
        self.assertDenied("cannot tokenize")

    def test_config_must_be_exactly_the_two_expected_keys(self) -> None:
        extra = {
            "plugins": 'plugins = ["evil.plugin"]',
            "mypy_path": 'mypy_path = "../x"',
            "files": 'files = ["../x"]',
            "exclude": 'exclude = ["app"]',
            "follow_imports": 'follow_imports = "skip"',
            "ignore_errors": "ignore_errors = true",
            "python_executable": 'python_executable = "/bin/x"',
            "cache_dir": 'cache_dir = ".mypy_cache"',
        }
        for key, line in extra.items():
            with self.subTest(key):
                self.write_config(GOOD_PYPROJECT + line + "\n")
                self.assertDenied("keys are")
        with self.subTest("overrides"):
            self.write_config(GOOD_PYPROJECT + '[[tool.mypy.overrides]]\nmodule = "app.*"\nignore_errors = true\n')
            self.assertDenied("keys are")

    def test_config_missing_keys_wrong_values_or_unparseable(self) -> None:
        bad = {
            "no table": '[tool.ruff]\nline-length = 100\n',
            "no strict": '[tool.mypy]\npython_version = "3.13"\n',
            "no version": "[tool.mypy]\nstrict = true\n",
            "old version": '[tool.mypy]\npython_version = "3.12"\nstrict = true\n',
            "float version": "[tool.mypy]\npython_version = 3.13\nstrict = true\n",
            "strict false": '[tool.mypy]\npython_version = "3.13"\nstrict = false\n',
            "strict int": '[tool.mypy]\npython_version = "3.13"\nstrict = 1\n',
            "bad toml": "[tool.mypy\n",
        }
        for label, text in bad.items():
            with self.subTest(label):
                self.write_config(text)
                with self.assertRaises(Denied):
                    self.plan()
        (self.root / "backend" / "pyproject.toml").unlink()
        self.assertDenied("pyproject.toml")

    def test_ambient_mypy_and_pythonpath_refused(self) -> None:
        for name in ("MYPYPATH", "MYPY_CACHE_DIR", "MYPY_FORCE_COLOR", "PYTHONPATH"):
            with self.subTest(name):
                self.assertDenied(name, env={**CLEAN_ENV, name: "/somewhere"})
        self.assertEqual(self.plan(env={**CLEAN_ENV, "PYTHONPATH": ""}).expected_sources, 3)

    def test_interpreter_must_be_an_executable_venv_file(self) -> None:
        self.assertDenied("interpreter", python=self.root / "nope" / "python")
        (self.fake_python.parent.parent / "pyvenv.cfg").unlink()
        self.assertDenied("pyvenv.cfg")
        self.fake_python.chmod(0o644)
        self.assertDenied("interpreter")


class CacheSideEffectTest(Base):
    """Pre-existing `.mypy_cache` dirs are tolerated only if the run leaves them untouched.

    The mypy subprocess is replaced by a stub that optionally mutates the fixture and
    reports the exact success line; mypy is never invoked here.
    """

    OK = "Success: no issues found in 3 source files\n"

    def locations(self) -> dict[str, Path]:
        return {"root": self.root / ".mypy_cache", "backend": self.root / "backend" / ".mypy_cache"}

    def seed(self, where: Path) -> None:
        (where / "3.13").mkdir(parents=True)
        (where / "3.13" / "app.meta.json").write_text("{}")

    def run_with(self, effect=None) -> int:
        def fake_run(*args, **kwargs):
            if effect is not None:
                effect()
            return mock.Mock(returncode=0, stdout=self.OK, stderr="")

        with mock.patch.object(w, "_probe"), mock.patch.object(w.subprocess, "run", side_effect=fake_run), \
                mock.patch("sys.stdout"), mock.patch("sys.stderr"):
            return w.run(self.root, self.fake_python)

    def test_no_cache_anywhere_passes(self) -> None:
        self.assertEqual(self.run_with(), w.EXIT_OK)

    def test_unchanged_preexisting_caches_pass(self) -> None:
        for where in self.locations().values():
            self.seed(where)
        before = tree_digest(self.root)
        self.assertEqual(self.run_with(), w.EXIT_OK)
        self.assertEqual(tree_digest(self.root), before)

    def test_each_preexisting_location_alone_passes(self) -> None:
        for name, where in self.locations().items():
            with self.subTest(name):
                self.seed(where)
                self.assertEqual(self.run_with(), w.EXIT_OK)
                shutil.rmtree(where)

    def test_newly_created_cache_denied_in_each_location(self) -> None:
        for name, where in self.locations().items():
            with self.subTest(name):
                with self.assertRaises(Denied) as caught:
                    self.run_with(lambda where=where: self.seed(where))
                self.assertIn(".mypy_cache", str(caught.exception))
                shutil.rmtree(where)

    def test_modified_preexisting_cache_denied_in_each_location(self) -> None:
        effects = {
            "new file": lambda d: (d / "3.13" / "new.json").write_text("{}"),
            "rewritten file": lambda d: (d / "3.13" / "app.meta.json").write_text('{"a": 1}'),
            "deleted file": lambda d: (d / "3.13" / "app.meta.json").unlink(),
            "new directory": lambda d: (d / "3.14").mkdir(),
            "removed cache": lambda d: shutil.rmtree(d),
        }
        for name, where in self.locations().items():
            for label, effect in effects.items():
                with self.subTest(f"{name}: {label}"):
                    self.seed(where)
                    with self.assertRaises(Denied) as caught:
                        self.run_with(lambda where=where, effect=effect: effect(where))
                    self.assertIn(".mypy_cache", str(caught.exception))
                    shutil.rmtree(where, ignore_errors=True)

    def test_cache_replaced_by_symlink_denied(self) -> None:
        where = self.locations()["backend"]
        self.seed(where)
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()

        def swap() -> None:
            shutil.rmtree(where)
            where.symlink_to(elsewhere)

        with self.assertRaises(Denied):
            self.run_with(swap)


class ClassifyResultTest(unittest.TestCase):
    def test_only_exact_success_line_with_exact_count_passes(self) -> None:
        ok = "Success: no issues found in 3 source files\n"
        self.assertEqual(w.classify_result(0, ok, "", 3)[0], w.EXIT_OK)
        self.assertEqual(
            w.classify_result(0, "Success: no issues found in 1 source file\n", "", 1)[0], w.EXIT_OK
        )

    def test_everything_else_is_not_a_pass(self) -> None:
        ok = "Success: no issues found in 3 source files\n"
        cases = {
            "fewer sources": (0, "Success: no issues found in 2 source files\n", "", 3),
            "more sources": (0, "Success: no issues found in 4 source files\n", "", 3),
            "no output": (0, "", "", 3),
            "extra line": (0, "note: something\n" + ok, "", 3),
            "stderr noise": (0, ok, "warning\n", 3),
            "singular for plural": (0, "Success: no issues found in 3 source file\n", "", 3),
            "plural for one": (0, "Success: no issues found in 1 source files\n", "", 1),
            "syntax error rc 2": (2, "", "x.py:1: error: invalid syntax\n", 3),
            "crash rc 130": (130, "", "", 3),
            "negative rc": (-9, "", "", 3),
        }
        for label, (rc, out, err, n) in cases.items():
            with self.subTest(label):
                self.assertEqual(w.classify_result(rc, out, err, n)[0], w.EXIT_DENIED)

    def test_rc_1_is_type_errors_not_denial(self) -> None:
        self.assertEqual(w.classify_result(1, "Found 2 errors in 1 file\n", "", 3)[0], w.EXIT_TYPE_ERRORS)


@unittest.skipUnless(VENV_PYTHON.is_file(), f"project venv python absent: {VENV_PYTHON}")
class ExecutedAgainstSyntheticFixturesTest(Base):
    """Real mypy, real wrapper, synthetic tree outside the repository only."""

    def setUp(self) -> None:
        super().setUp()
        self.assertNotIn(Path(__file__).resolve().parents[2], self.root.parents)
        self.fake_python = VENV_PYTHON
        patch = mock.patch.dict(os.environ)
        patch.start()
        self.addCleanup(patch.stop)
        for name in [n for n in os.environ if n == "MYPYPATH" or n.startswith(("MYPY_", "PYTEST_"))]:
            os.environ.pop(name)

    def run_wrapper(self) -> int:
        with mock.patch("sys.stdout"), mock.patch("sys.stderr"):
            try:
                return w.run(self.root, VENV_PYTHON)
            except Denied:
                return w.EXIT_DENIED

    def test_positive_clean_strict_package_passes_with_exact_count(self) -> None:
        before = tree_digest(self.root)
        self.assertEqual(self.run_wrapper(), w.EXIT_OK)
        self.assertEqual(tree_digest(self.root), before, "fixture mutated")
        self.assertFalse((self.root / "backend" / ".mypy_cache").exists())
        self.assertFalse((self.root / ".mypy_cache").exists())

    def test_positive_preexisting_root_and_backend_caches_do_not_deny(self) -> None:
        for where in (self.root / ".mypy_cache", self.root / "backend" / ".mypy_cache"):
            (where / "3.13").mkdir(parents=True)
            (where / "3.13" / "keep.json").write_text("{}")
        before = tree_digest(self.root)
        self.assertEqual(self.run_wrapper(), w.EXIT_OK)
        self.assertEqual(tree_digest(self.root), before, "pre-existing caches or fixture mutated")

    def test_negative_type_error_is_exit_1(self) -> None:
        (self.app / "core" / "bad.py").write_text("def f(a: int) -> str:\n    return a\n")
        self.assertEqual(self.run_wrapper(), w.EXIT_TYPE_ERRORS)

    def test_negative_strict_is_live(self) -> None:
        (self.app / "core" / "untyped.py").write_text("def f(a):\n    return a\n")
        self.assertEqual(self.run_wrapper(), w.EXIT_TYPE_ERRORS)

    def test_negative_syntax_error_is_denied_not_ok(self) -> None:
        (self.app / "core" / "syn.py").write_text("def f(:\n    pass\n")
        self.assertEqual(self.run_wrapper(), w.EXIT_DENIED)

    def test_decoy_ambient_configs_do_not_relax_the_check(self) -> None:
        (self.root / "backend" / "mypy.ini").write_text("[mypy]\nignore_errors = True\n")
        (self.root / "backend" / "setup.cfg").write_text("[mypy]\nignore_errors = True\n")
        home = self.root / "decoyhome"
        home.mkdir()
        (home / ".mypy.ini").write_text("[mypy]\nignore_errors = True\n")
        (self.app / "core" / "bad.py").write_text("def f(a: int) -> str:\n    return a\n")
        with mock.patch.dict(os.environ, {"HOME": str(home)}):
            self.assertEqual(self.run_wrapper(), w.EXIT_TYPE_ERRORS)

    def test_plugin_in_config_is_refused_before_it_can_execute(self) -> None:
        marker = self.root / "PLUGIN_RAN"
        (self.root / "backend" / "evil_plugin.py").write_text(
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('ran')\n"
            "def plugin(version):\n    from mypy.plugin import Plugin\n    return Plugin\n"
        )
        self.write_config(GOOD_PYPROJECT + 'plugins = ["evil_plugin"]\n')
        self.assertEqual(self.run_wrapper(), w.EXIT_DENIED)
        self.assertFalse(marker.exists(), "plugin executed")

    def test_ambient_mypypath_refused_before_run(self) -> None:
        with mock.patch.dict(os.environ, {"MYPYPATH": str(self.root)}):
            self.assertEqual(self.run_wrapper(), w.EXIT_DENIED)

    def test_imports_escaping_app_still_surface_their_errors(self) -> None:
        """Documents mypy's follow-imports: an outside module's errors are reported, not hidden."""
        (self.root / "backend" / "migrations").mkdir()
        (self.root / "backend" / "migrations" / "__init__.py").write_text("X: int = 'a'\n")
        (self.app / "core" / "uses.py").write_text("from migrations import X\n\nY: int = X\n")
        self.assertEqual(self.run_wrapper(), w.EXIT_TYPE_ERRORS)

    def test_probe_rejects_a_non_venv_or_non_isolated_interpreter(self) -> None:
        current = w.plan(self.root, VENV_PYTHON, CLEAN_ENV)
        for stdout in ("0 1\n", "1 0\n", ""):
            fake = mock.Mock(returncode=0, stdout=stdout, stderr="")
            with self.subTest(stdout), mock.patch.object(w.subprocess, "run", return_value=fake):
                with self.assertRaises(Denied):
                    w._probe(current, {})

    def test_probe_rejects_an_unpinned_mypy(self) -> None:
        current = w.plan(self.root, VENV_PYTHON, CLEAN_ENV)
        replies = [mock.Mock(returncode=0, stdout="1 1\n"), mock.Mock(returncode=0, stdout="mypy 2.3.2 (compiled: yes)\n")]
        with mock.patch.object(w.subprocess, "run", side_effect=replies):
            with self.assertRaises(Denied):
                w._probe(current, {})


if __name__ == "__main__":
    unittest.main()
