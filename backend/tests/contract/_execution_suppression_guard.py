"""Shared execution-suppression guard for Slice-7's test-harness
self-protection (GOV-01-R02, BUG-050 round 15: R15-1/R15-2/R15-3/R15-4).

Round 14 added a single, per-file, per-test AST self-check
(`test_critical_negative_tests_are_not_suppressed`) that only ran as one
more collected pytest item. Round 15 found that shape itself has the
same defect it was built to catch: skipping, redefining, or rebinding
*that one test* reopens everything it was protecting, fully green, with
`ruff`/`mypy --strict` both clean (R15-1); its suppressing-marker match
was shape-bound to the literal `pytest.mark.*` attribute chain, so
`from pytest import mark` and `import pytest as pt` both escaped it
(R15-2); the companion inventory file's own two guard functions had the
identical, unprotected gap (R15-3); and a module-level `pytestmark`
assignment skips every test in the file at once — including whatever
would otherwise have caught it — without tripping any per-function
check at all (R15-4).

This module is the one mechanism all four findings share: resolve
`pytest`'s bound name(s) and `mark`'s bound name(s) from the file's own
`Import`/`ImportFrom` nodes instead of assuming the literal spelling
(closes R15-2), and check the whole module's suppression surface — not
just one test function's — in one pass (closes R15-4, since a
module-level `pytestmark` is visible in `tree.body` regardless of
whether any test runs). Each caller imports this module and invokes
`assert_execution_not_suppressed` **eagerly, at its own module level**
(not only from inside a test function): that call is ordinary Python
executed once, unconditionally, when pytest imports the file for
collection, before pytest's own skip/xfail/deselection machinery has any
say — so suppressing a *test* (R15-1's shapes, applied to any watched
name including this mechanism's own callers) cannot prevent the check
itself from running, the same way it could when the check was only
reachable as a collected test item. A failure here surfaces as a
collection error for the whole file, which is a louder, more honest
signal than a single failed test among many passing ones.

What this still cannot see, by design (unchanged from round 14's own
disclosure): a `conftest.py`-level skip (lives in a different file this
module does not and should not parse), a collection-time `pytest.skip()`
call reached conditionally inside a test body, or deselection via
`-k`/`-m` at invocation time. Nor can it defend against an edit to its
own `watched_names` argument at the call site — the same irreducible
limit the companion file's own NF-7 already discloses for its `DOMAINS`
tuple: no test-level or import-time check can defend its own expectation
set from an editor of the file that states it. Round 15's own §12 names
the full fix for the first three (a `pytest_sessionfinish` hook verifying
each watched test actually reported `passed`, a genuine execution
witness) and explicitly leaves adopting it as a scoping judgment for a
later round — see BUG-050's round-15 remediation section for why this
round chose the bounded, static, import-time mechanism below instead.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SUPPRESSING_MARKS = frozenset({"skip", "xfail", "skipif"})


def _resolve_pytest_aliases(tree: ast.Module) -> tuple[set[str], set[str]]:
    """Return (pytest-module aliases, mark-submodule aliases) actually
    bound in this file, from its own `Import`/`ImportFrom` nodes — so
    `import pytest as pt` and `from pytest import mark` are recognized
    as pytest's own marker namespace rather than only the literal
    `pytest.mark` spelling (R15-2)."""
    pytest_aliases = {"pytest"}
    mark_aliases: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "pytest":
                    pytest_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "pytest":
            for alias in node.names:
                if alias.name == "mark":
                    mark_aliases.add(alias.asname or alias.name)
    return pytest_aliases, mark_aliases


def _suppressing_mark_name(
    expr: ast.expr, pytest_aliases: set[str], mark_aliases: set[str]
) -> str | None:
    """If `expr` is a (possibly-called) reference to one of pytest's own
    skip/xfail/skipif marks, resolved through either `<pytest-alias>.mark.X`
    or `<mark-alias>.X`, return the mark name (`"skip"`, `"xfail"`, or
    `"skipif"`); otherwise `None`."""
    target = expr.func if isinstance(expr, ast.Call) else expr
    if not (isinstance(target, ast.Attribute) and target.attr in _SUPPRESSING_MARKS):
        return None
    value = target.value
    if isinstance(value, ast.Name) and value.id in mark_aliases:
        return target.attr
    if (
        isinstance(value, ast.Attribute)
        and value.attr == "mark"
        and isinstance(value.value, ast.Name)
        and value.value.id in pytest_aliases
    ):
        return target.attr
    return None


def assert_execution_not_suppressed(file_path: Path, watched_names: frozenset[str]) -> None:
    """Parse `file_path`'s own source and assert that every name in
    `watched_names` is: defined exactly once at module level, never
    rebound after definition, carries no suppressing marker (alias-aware,
    R15-2), and is not silently suppressed en masse by a module-level
    `pytestmark` assignment (R15-4, checked once for the whole file,
    not per watched name). Call this eagerly at module level in the
    caller, not only from inside a test function (see module docstring)."""
    tree = ast.parse(file_path.read_text())
    pytest_aliases, mark_aliases = _resolve_pytest_aliases(tree)

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not (isinstance(target, ast.Name) and target.id == "pytestmark"):
                continue
            marks = node.value.elts if isinstance(node.value, ast.List) else [node.value]
            hit = [
                name
                for mark_expr in marks
                if (name := _suppressing_mark_name(mark_expr, pytest_aliases, mark_aliases))
            ]
            assert not hit, (
                f"module-level `pytestmark` in {file_path.name} applies a suppressing "
                f"marker to every test in the file: {hit}"
            )

    module_level_defs: dict[str, list[ast.FunctionDef]] = {}
    module_level_rebinds: dict[str, int] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in watched_names:
            module_level_defs.setdefault(node.name, []).append(node)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in watched_names:
                    module_level_rebinds[target.id] = module_level_rebinds.get(target.id, 0) + 1

    missing = watched_names - set(module_level_defs)
    assert not missing, (
        f"watched test(s) not found at module level in {file_path.name}: {sorted(missing)}"
    )

    redefined = {name: len(defs) for name, defs in module_level_defs.items() if len(defs) > 1}
    assert not redefined, (
        f"watched test(s) redefined more than once in {file_path.name}: {redefined}"
    )

    assert not module_level_rebinds, (
        f"watched test(s) rebound to another value after definition in {file_path.name}: "
        f"{sorted(module_level_rebinds)}"
    )

    suppressed: dict[str, list[str]] = {}
    for name, defs in module_level_defs.items():
        (func,) = defs
        for decorator in func.decorator_list:
            mark_name = _suppressing_mark_name(decorator, pytest_aliases, mark_aliases)
            if mark_name:
                suppressed.setdefault(name, []).append(mark_name)

    assert not suppressed, (
        f"watched test(s) carry a suppressing marker in {file_path.name}: {suppressed}"
    )
