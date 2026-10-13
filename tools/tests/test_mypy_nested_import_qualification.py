"""
Synthetic-only CAP-012 qualification drill: nested-layout mypy import probe
(MOD-001, M1-C-06; governing question is
knowledge/03-Modules/MOD-001/evidence/implementation/
M1-C-06-TYPECHECK-TARGET-CLOSURE-ARCHITECTURE-2026-10-09.md §10).

This is a qualification-drill fixture, not CI evidence and not a capability
approval: CAP-012 (mypy) is QUALIFIED NOT APPROVED, so mypy is only ever
pointed at a throwaway synthetic tree built under an OS temp directory outside
the repository. No Veyro source is copied, read or type-checked.

Synthetic analogue of the real nested `backend/app` layout:

    <root>/app/__init__.py
    <root>/app/modules/__init__.py
    <root>/app/modules/conftest.py          imports tests.harness.mod
    <root>/app/modules/_shared/__init__.py
    <root>/app/modules/mod_{a..f}/__init__.py
    <root>/app/modules/mod_{a..f}/tests/__init__.py
    <root>/app/modules/mod_{a..f}/tests/test_scaffold.py
    <root>/tests/harness/__init__.py
    <root>/tests/harness/mod.py             one deliberate typed return error
    <root>/tests/__init__.py                variant A only (absent in variant B)

The exact intended CAP-012 invocation is run from cwd <root>, with the
project venv interpreter, a cleared environment, confined HOME/TMPDIR and
only `python_version`/`strict` in the config:

    python -I -m mypy --config-file pyproject.toml --cache-dir=/dev/null \
        --no-color-output app

Per variant the drill records rc, the reported source-file count N (it is not
assumed that followed imports contribute to N), the class of the harness
defect (followed-import type error / unresolved import / other) and the
diagnostic with the temp root normalised away.

Run `python tools/tests/test_mypy_nested_import_qualification.py` to print
the observations as JSON (used for the evidence record).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VENV_PYTHON = REPO_ROOT / "backend" / ".venv" / "bin" / "python"

MODULE_NAMES = ("mod_a", "mod_b", "mod_c", "mod_d", "mod_e", "mod_f")

CONFIG = 'python_version = "3.13"\nstrict = true\n'

# The unmistakable deliberate defect: declared int, returns str.
HARNESS_SOURCE = """\
def harness_value() -> int:
    return "DELIBERATE_HARNESS_TYPE_ERROR"
"""

CONFTEST_SOURCE = """\
from tests.harness.mod import harness_value


def conftest_value() -> int:
    return harness_value()
"""

TEST_MODULE_SOURCE = """\
def test_scaffold() -> None:
    assert True
"""

DELIBERATE_MARKER = "DELIBERATE_HARNESS_TYPE_ERROR"
ERROR_CLASSES = ("followed-import-type-error", "unresolved-import", "other", "none")


def repo_cache_snapshot() -> tuple[int, int]:
    """(file count, newest mtime_ns) of the pre-existing repo-root .mypy_cache."""
    cache = REPO_ROOT / ".mypy_cache"
    stats = [p.stat() for p in cache.rglob("*") if p.is_file()] if cache.exists() else []
    return len(stats), max((st.st_mtime_ns for st in stats), default=0)


def build_tree(root: Path, *, root_tests_init: bool) -> None:
    (root / "pyproject.toml").write_text("[tool.mypy]\n" + CONFIG)
    app = root / "app"
    modules = app / "modules"
    (modules / "_shared").mkdir(parents=True)
    (app / "__init__.py").write_text("")
    (modules / "__init__.py").write_text("")
    (modules / "_shared" / "__init__.py").write_text("")
    (modules / "conftest.py").write_text(CONFTEST_SOURCE)
    for name in MODULE_NAMES:
        tests_dir = modules / name / "tests"
        tests_dir.mkdir(parents=True)
        (modules / name / "__init__.py").write_text("")
        (tests_dir / "__init__.py").write_text("")
        (tests_dir / "test_scaffold.py").write_text(TEST_MODULE_SOURCE)
    harness = root / "tests" / "harness"
    harness.mkdir(parents=True)
    (harness / "__init__.py").write_text("")
    (harness / "mod.py").write_text(HARNESS_SOURCE)
    if root_tests_init:
        (root / "tests" / "__init__.py").write_text("")


def classify(output: str) -> str:
    lines = [ln for ln in output.splitlines() if ": error:" in ln]
    if not lines:
        return "none"
    if any("[import-not-found]" in ln or "[import-untyped]" in ln for ln in lines):
        return "unresolved-import"
    if any(
        ln.startswith("tests/harness/mod.py:") and "[return-value]" in ln
        for ln in lines
    ):
        return "followed-import-type-error"
    return "other"


def parse_n(output: str) -> int | None:
    m = re.search(r"no issues found in (\d+) source files?", output) or re.search(
        r"\(checked (\d+) source files?\)", output
    )
    return int(m.group(1)) if m else None


def run_variant(*, root_tests_init: bool) -> dict[str, object]:
    base = Path(os.path.realpath(tempfile.mkdtemp(prefix="veyro-mypy-nested-")))
    try:
        root = base / "tree"
        home = base / "home"
        tmp = base / "tmp"
        root.mkdir()
        home.mkdir()
        tmp.mkdir()
        build_tree(root, root_tests_init=root_tests_init)
        expected_app_files = sum(1 for _ in (root / "app").rglob("*.py"))
        # Cleared environment: no MYPYPATH / MYPY_*, confined HOME and TMPDIR.
        env = {"HOME": str(home), "TMPDIR": str(tmp), "PATH": "/usr/bin:/bin"}
        argv = [
            str(VENV_PYTHON),
            "-I",
            "-m",
            "mypy",
            "--config-file",
            "pyproject.toml",
            "--cache-dir=/dev/null",
            "--no-color-output",
            "app",
        ]
        proc = subprocess.run(
            argv, cwd=root, env=env, capture_output=True, text=True, timeout=300
        )
        out = (proc.stdout + proc.stderr).replace(str(base), "<temp>")
        return {
            "variant": "A" if root_tests_init else "B",
            "root_tests_init_present": root_tests_init,
            "returncode": proc.returncode,
            "expected_app_py_files": expected_app_files,
            "reported_n": parse_n(out),
            "harness_error_class": classify(out),
            "deliberate_marker_line_in_output": any(
                "tests/harness/mod.py" in ln for ln in out.splitlines()
            ),
            "output": out.strip().splitlines(),
        }
    finally:
        shutil.rmtree(base, ignore_errors=True)


@pytest.fixture(scope="module")
def observations() -> dict[str, dict[str, object]]:
    if not VENV_PYTHON.exists():
        pytest.fail("backend/.venv interpreter not found; install is out of scope")
    return {"A": run_variant(root_tests_init=True), "B": run_variant(root_tests_init=False)}


@pytest.mark.parametrize("variant", ["A", "B"])
def test_invocation_ran_and_is_classified(observations, variant) -> None:
    obs = observations[variant]
    # rc 2 would mean mypy could not run at all (usage/crash), not an outcome.
    assert obs["returncode"] in (0, 1), obs["output"]
    assert obs["harness_error_class"] in ERROR_CLASSES
    assert obs["reported_n"] is not None, obs["output"]


@pytest.mark.parametrize("variant", ["A", "B"])
def test_fixture_is_not_vacuous(observations, variant) -> None:
    assert observations[variant]["expected_app_py_files"] == 22


def test_variants_differ_only_by_root_tests_init(observations) -> None:
    assert observations["A"]["root_tests_init_present"] is True
    assert observations["B"]["root_tests_init_present"] is False


@pytest.mark.parametrize("variant", ["A", "B"])
def test_observed_outcome_2026_10_09(observations, variant) -> None:
    # Pins the observation recorded in M1-C-06-MYPY-NESTED-IMPORT-SYNTHETIC-
    # 2026-10-09.md (darwin arm64, backend/.venv Python 3.14.5, mypy 2.3.1).
    # Synthetic fixtures only; says nothing about real Veyro source or Linux CI.
    obs = observations[variant]
    assert obs["returncode"] == 1
    assert obs["reported_n"] == obs["expected_app_py_files"] == 22
    assert obs["harness_error_class"] == "followed-import-type-error"


def test_repo_mypy_cache_untouched() -> None:
    # A repo-root .mypy_cache pre-exists (disclosed, unregistered earlier use);
    # the drill must neither add to nor modify it.
    before = repo_cache_snapshot()
    run_variant(root_tests_init=True)
    assert repo_cache_snapshot() == before


def test_temp_trees_are_removed() -> None:
    before = {p for p in Path(tempfile.gettempdir()).glob("veyro-mypy-nested-*")}
    run_variant(root_tests_init=True)
    after = {p for p in Path(tempfile.gettempdir()).glob("veyro-mypy-nested-*")}
    assert after <= before


if __name__ == "__main__":
    print(
        json.dumps(
            [run_variant(root_tests_init=True), run_variant(root_tests_init=False)],
            indent=2,
        )
    )
