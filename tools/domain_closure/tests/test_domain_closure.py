"""Deterministic tests for the local-domain-slice closure check.
Run: python3 -m unittest discover -s tools/domain_closure/tests -t tools/domain_closure

Every test builds its own temporary tree; the real repository is never written and is read only to
assert that whatever the lane roots currently hold passes the check and stays inside them. Each escape test is a file that would pass a
regex-based import scan of the kind the S0 closure used, and is caught here because the check reads
an AST instead: that is the reason this tool exists in this form, and the reason the tests are
written as escapes rather than as unit tests of the visitor.
"""
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import domain_closure as dc  # noqa: E402

REPO = HERE.parent.parent.parent
RECORD = "knowledge/00-Decisions/OWNER-2026-11-07-local-domain-slice-lane.md"


def _tracked(rel):
    import subprocess
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z", "--", rel],
                         capture_output=True, check=False)
    return out.returncode == 0 and out.stdout.strip(b"\0").decode() == rel

PURE = '''"""A pure slice."""
from __future__ import annotations

import re
from dataclasses import dataclass

_TENANT = re.compile(r"[0-9a-f]{8}", re.ASCII)
MAX = 16


@dataclass(frozen=True, slots=True)
class Scope:
    tenant_id: str


def parse(value: object) -> Scope:
    if type(value) is not str or _TENANT.fullmatch(value) is None:
        raise ValueError("bad")
    return Scope(tenant_id=value)
'''


class LaneCase(unittest.TestCase):
    """Base: build a tree with the lane record present and one slice file in it."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "knowledge/00-Decisions").mkdir(parents=True)
        (self.tmp / RECORD).write_text("# lane record\n", encoding="utf-8")
        # The temporary tree is not a git repository, so _owner_record_effective() is False there.
        # Tests that need an open lane pass lane_effective explicitly; the gating tests exercise
        # the real detector against the real repository.
        self.lane = self.tmp / dc.LANE_ROOTS[0]
        self.lane.mkdir(parents=True)

    def codes(self, source, name="slice.py", lane_effective=True, in_tests=False):
        base = self.tmp / (dc.TESTS_ROOT if in_tests else dc.LANE_ROOTS[0])
        base.mkdir(parents=True, exist_ok=True)
        for stale in list(base.glob("*.py")):
            stale.unlink()
        (base / name).write_text(source, encoding="utf-8")
        report = dc.check(self.tmp, lane_effective)
        result = sorted({v["code"] for v in report["violations"]})
        (base / name).unlink()
        return result


class TestPureCodePasses(LaneCase):
    def test_a_pure_slice_is_clean(self):
        self.assertEqual(self.codes(PURE), [])

    def test_every_allowed_import_is_accepted(self):
        for module in sorted(dc.ALLOWED_IMPORTS | dc.TESTS_ONLY_IMPORTS):
            source = f"import {module}\n" if module != "__future__" else \
                "from __future__ import annotations\n"
            in_tests = module in dc.TESTS_ONLY_IMPORTS
            name = "test_x.py" if in_tests else "slice.py"
            self.assertEqual(self.codes(source, name=name, in_tests=in_tests), [], module)

    def test_the_allowlist_is_only_what_a_domain_slice_needs(self):
        # Round four shrank this from thirty-two modules to four. Pinned, because every addition
        # brings that module's whole attribute surface, its lazily-bound submodules and its
        # process-wide mutable state inside the boundary -- which is how most of the fifteen
        # proved escapes got their vehicle.
        self.assertEqual(sorted(dc.ALLOWED_IMPORTS),
                         ["__future__", "dataclasses", "enum", "re"])
        self.assertEqual(sorted(dc.TESTS_ONLY_IMPORTS), ["unittest"])

    def test_allowed_and_forbidden_sets_do_not_overlap(self):
        self.assertEqual(dc.ALLOWED_IMPORTS & set(dc.FORBIDDEN_IMPORTS), set())

    def test_every_forbidden_import_carries_a_reason(self):
        for module, reason in dc.FORBIDDEN_IMPORTS.items():
            self.assertTrue(reason.strip(), module)


class TestImportClosure(LaneCase):
    def test_forbidden_import(self):
        for source in ("import os\n", "from os import path\n", "import os.path\n",
                       "from os.path import join\n"):
            self.assertEqual(self.codes(source), ["FORBIDDEN_IMPORT"], source)

    def test_database_drivers(self):
        for module in ("psycopg", "psycopg2", "psycopg_pool", "sqlite3", "sqlalchemy"):
            self.assertEqual(self.codes(f"import {module}\n"), ["FORBIDDEN_IMPORT"], module)

    def test_clock_and_randomness(self):
        for module in ("time", "random", "secrets", "uuid", "zoneinfo"):
            self.assertEqual(self.codes(f"import {module}\n"), ["FORBIDDEN_IMPORT"], module)

    def test_third_party_is_not_merely_unlisted_but_refused(self):
        self.assertEqual(self.codes("import requests\n"), ["IMPORT_NOT_ALLOWED"])

    def test_star_import_is_refused(self):
        # An earlier revision asserted this was PERMITTED, contradicting the test's own name. A
        # star import binds names this closure cannot enumerate, so every bare-name and attribute
        # rule loses track of what a later line refers to. Refusing it costs a slice nothing: it
        # can import the names it needs explicitly. This is a deliberate tightening, recorded
        # here rather than quietly flipped.
        self.assertEqual(self.codes("from re import *\n"), ["FORBIDDEN_IMPORT"])

    def test_aliased_forbidden_import_is_caught(self):
        self.assertEqual(self.codes("import os as _o\n"), ["FORBIDDEN_IMPORT"])

    def test_a_submodule_of_a_removed_package_is_refused(self):
        # This asserted `from collections.abc import Mapping` passed, which it did while
        # `collections` was admitted. The genuine-submodule branch it was guarding is now covered
        # directly by TestModuleReach.test_the_genuine_submodule_branch_is_still_live, because no
        # admitted module has a public submodule any more.
        self.assertEqual(self.codes("from collections.abc import Mapping\n"),
                         ["IMPORT_NOT_ALLOWED"])

    def test_relative_import_stays_inside_the_lane(self):
        self.assertEqual(self.codes("from . import sibling\n"), [])


class TestEscapesARegexWouldMiss(LaneCase):
    """The reason this check reads an AST. Each of these has no forbidden import statement."""

    def test_dynamic_import_via_import_dunder(self):
        self.assertEqual(self.codes("def f():\n    return __import__('os')\n"),
                         ["FORBIDDEN_BUILTIN"])

    def test_open_without_importing_anything(self):
        self.assertEqual(self.codes("def f():\n    return open('/etc/passwd').read()\n"),
                         ["FORBIDDEN_BUILTIN"])

    def test_eval_and_exec(self):
        for builtin in ("eval", "exec", "compile"):
            self.assertEqual(self.codes(f"def f(s):\n    return {builtin}(s)\n"),
                             ["FORBIDDEN_BUILTIN"], builtin)

    def test_getattr_reaches_an_attribute_without_naming_it(self):
        self.assertEqual(self.codes("def f(o, n):\n    return getattr(o, n)\n"),
                         ["FORBIDDEN_BUILTIN"])

    def test_setattr_and_delattr(self):
        for builtin in ("setattr", "delattr"):
            self.assertEqual(self.codes(f"def f(o):\n    return {builtin}(o, 'x', 1)\n"),
                             ["FORBIDDEN_BUILTIN"], builtin)

    def test_globals_reaches_module_state(self):
        for builtin in ("globals", "locals", "vars"):
            self.assertEqual(self.codes(f"def f():\n    return {builtin}()\n"),
                             ["FORBIDDEN_BUILTIN"], builtin)

    def test_print_is_a_side_effect(self):
        self.assertEqual(self.codes("def f():\n    print('x')\n"), ["FORBIDDEN_BUILTIN"])

    def test_function_globals_escape(self):
        self.assertEqual(self.codes("def f():\n    return f.__globals__['os']\n"),
                         ["DUNDER_ESCAPE"])

    def test_subclasses_escape(self):
        self.assertEqual(
            self.codes("def f():\n    return ().__class__.__bases__[0].__subclasses__()\n"),
            ["DUNDER_ESCAPE"])

    def test_builtins_escape(self):
        self.assertEqual(self.codes("def f(m):\n    return m.__builtins__\n"), ["DUNDER_ESCAPE"])

    def test_code_object_escape(self):
        self.assertEqual(self.codes("def f():\n    return f.__code__\n"), ["DUNDER_ESCAPE"])

    def test_loader_escape(self):
        self.assertEqual(self.codes("def f(m):\n    return m.__spec__\n"), ["DUNDER_ESCAPE"])


class TestReachEscapes(LaneCase):
    """Escapes an independent review proved against the first version of this check.

    All three passed `check` while obtaining a handle from which arbitrary I/O, a network
    connection, a subprocess, a clock read and entropy follow by ordinary CPython semantics. They
    contain no forbidden import statement, no forbidden `Name`, and no forbidden attribute spelled
    as an attribute. They were closed by banning the literal names `sys`, `os` and `modules` --
    three instances, not a class -- which a second review then walked around through the standard
    library's private aliases. See TestModuleReach for that, and the module docstring for which
    rules are property tests and which are still enumerations.
    """

    def test_allowlisted_module_reexporting_sys(self):
        # unittest.case.sys.modules["os"] reached every forbidden module through attributes alone.
        self.assertIn("ATTRIBUTE_REACH",
                      self.codes("import unittest\n\n\ndef f():\n"
                                 "    return unittest.case.sys.modules\n",
                                 name="test_a.py", in_tests=True))

    def test_string_target_reflection_to_a_dunder(self):
        # operator.attrgetter("__globals__")(fn)["__builtins__"] needed only operator and a def.
        # `operator` is no longer admitted at all, so this is now refused twice over. The dunder
        # string rule is asserted specifically because it is what caught the payload when the
        # vehicle WAS admitted, and the vehicle could be re-admitted by a future widening.
        codes = self.codes('import operator\n\n\ndef g():\n    pass\n\n\n'
                           'def f():\n    return operator.attrgetter("__globals__")(g)\n')
        self.assertIn("DUNDER_ESCAPE", codes)
        self.assertIn("IMPORT_NOT_ALLOWED", codes)

    def test_submodule_of_an_allowlisted_package(self):
        # `from unittest import mock` checked only `unittest`; mock.patch takes a string target.
        codes = self.codes("from unittest import mock\n", name="test_c.py", in_tests=True)
        self.assertIn("FORBIDDEN_IMPORT", codes)
        # Also MODULE_REACH now: `unittest` does not eagerly bind `mock`, so the resolver cannot
        # see what the name binds and fails closed instead of waving it through.
        self.assertIn("MODULE_REACH", codes)

    def test_the_name_guard_string_is_permitted(self):
        # Regression: the dunder-string rule caught `"__main__"`, which is a module name and the
        # one module-level guard the shape rule admits.
        self.assertEqual(self.codes("def f():\n    return 1\n\n\n"
                                    "if __name__ == '__main__':\n    pass\n"), [])

    def test_any_dunder_string_is_an_attribute_name(self):
        for literal in ("__globals__", "__builtins__", "__class__", "__reduce__", "__anything__"):
            self.assertIn("DUNDER_ESCAPE", self.codes(f'TBL = {{"{literal}": 1}}\n'), literal)

    def test_dunder_attributes_are_refused_as_a_class_not_by_enumeration(self):
        # The first version enumerated nine names and missed __reduce__ and __getattribute__.
        for attr in ("__reduce__", "__reduce_ex__", "__getattribute__", "__sizeof__",
                     "__format__", "__anything__"):
            self.assertEqual(self.codes(f"def f(o):\n    return o.{attr}\n"),
                             ["DUNDER_ESCAPE"], attr)

    def test_the_two_permitted_dunder_attributes(self):
        for attr in sorted(dc.ALLOWED_DUNDER_ATTRS):
            self.assertEqual(self.codes(f"def f(o):\n    return o.{attr}\n"), [], attr)

    def test_forbidden_module_names_are_refused_as_attributes(self):
        # On a plain parameter, so the rule is tested on its own rather than through whichever
        # module the allowlist happens to admit this week. `json` used to be the vehicle here.
        for attr in ("sys", "os", "socket", "subprocess", "time", "random", "importlib"):
            self.assertEqual(self.codes(f"def f(o):\n    return o.{attr}\n"),
                             ["ATTRIBUTE_REACH"], attr)

    def test_reach_primitives_are_refused_as_attributes(self):
        for attr in ("modules", "builtins", "attrgetter", "methodcaller", "itemgetter",
                     "getattr", "open", "eval", "globals", "vars"):
            self.assertEqual(self.codes(f"def f(o):\n    return o.{attr}\n"),
                             ["ATTRIBUTE_REACH"], attr)

    def test_re_compile_is_not_collateral(self):
        # Regression: unioning the whole builtin denylist into attribute names banned re.compile,
        # which is the first thing a real slice writes.
        self.assertEqual(self.codes('import re\n\n_P = re.compile(r"[a-f]{8}", re.ASCII)\n'), [])

    def test_hook_definitions_that_answer_for_a_refused_attribute(self):
        for name in sorted(dc.FORBIDDEN_DUNDER_DEFS):
            source = f"class C:\n    def {name}(self, *a):\n        return None\n"
            self.assertEqual(self.codes(source), ["DUNDER_ESCAPE"], name)

    def test_ordinary_dunder_definitions_are_allowed(self):
        source = ("from dataclasses import dataclass\n\n\n@dataclass\nclass C:\n"
                  "    x: int\n\n    def __post_init__(self) -> None:\n        pass\n\n"
                  "    def __eq__(self, o: object) -> bool:\n        return True\n\n"
                  "    def __hash__(self) -> int:\n        return 1\n")
        self.assertEqual(self.codes(source), [])

    def test_unittest_is_admitted_only_in_the_tests_root(self):
        self.assertEqual(self.codes("import unittest\n"), ["IMPORT_NOT_ALLOWED"])
        self.assertEqual(self.codes("import unittest\n", name="test_b.py", in_tests=True), [])


class TestModuleReach(LaneCase):
    """The standard library re-exports forbidden modules under names no denylist can anticipate.

    A second independent review proved six routes against the version that enumerated attribute
    names, including arbitrary code execution and an outbound TCP connection. The rule now resolves
    the module at check time and compares its own `__name__` to the path it was reached by: a
    genuine submodule names itself after that path, a re-export names what it actually is.
    """

    # Still admitted, so the module rule is what has to catch the re-export.
    REEXPORTS = {
        "enum": ("bltns", "builtins"),
        "re": ("functools", "functools"),
        "dataclasses": ("inspect", "inspect"),
    }
    # Round four shrank the allowlist from thirty-two modules to four, so these vehicles are now
    # refused one step earlier, at the import. They stay in the suite because the escape they
    # carried is the reason the module rule exists, and because re-admitting any of them would
    # silently restore the vehicle.
    REMOVED_VEHICLES = {
        "statistics": ("_random", "random"),
        "collections": ("_sys", "sys"),
        "calendar": ("datetime", "datetime"),
        "hashlib": ("_hashlib", "_hashlib"),
        "typing": ("operator", "operator"),
        # Not a re-export: `decimal` carried a *process-wide mutable context*, and
        # `decimal.getcontext().prec = 2` made one pure function return two answers for one input.
        # The record claims this route is closed by the allowlist's shortness, so the claim is
        # pinned here: re-admitting `decimal` restores the vehicle.
        "decimal": ("getcontext", "getcontext"),
    }

    def test_every_known_reexport_is_refused(self):
        for base, (attr, real) in sorted(self.REEXPORTS.items()):
            codes = self.codes(f"import {base}\n\n\ndef f():\n    return {base}.{attr}\n")
            self.assertIn("MODULE_REACH", codes, f"{base}.{attr} -> {real}")

    def test_the_removed_vehicles_are_refused_at_the_import(self):
        for base, (attr, real) in sorted(self.REMOVED_VEHICLES.items()):
            codes = self.codes(f"import {base}\n\n\ndef f():\n    return {base}.{attr}\n")
            self.assertIn("IMPORT_NOT_ALLOWED", codes, f"{base}.{attr} -> {real}")

    def test_the_detail_names_the_module_actually_reached(self):
        (self.tmp / dc.LANE_ROOTS[0]).mkdir(parents=True, exist_ok=True)
        (self.tmp / dc.LANE_ROOTS[0] / "slice.py").write_text(
            "import dataclasses\n\n\ndef f():\n    return dataclasses.inspect\n",
            encoding="utf-8")
        details = [v["detail"] for v in dc.check(self.tmp, True)["violations"]]
        self.assertTrue(any("'inspect'" in d for d in details), details)

    def test_an_alias_does_not_evade(self):
        self.assertIn("MODULE_REACH",
                      self.codes("import dataclasses as d\n\n\ndef f():\n    return d.inspect\n"))

    def test_a_chain_through_a_reexport_is_refused_at_the_first_hop(self):
        self.assertIn("MODULE_REACH",
                      self.codes("import dataclasses\n\n\ndef f():\n"
                                 "    return dataclasses.inspect.linecache\n"))

    def test_from_import_of_a_reexported_module_is_refused(self):
        self.assertIn("MODULE_REACH", self.codes("from dataclasses import inspect\n"))

    def test_the_genuine_submodule_branch_is_still_live(self):
        # The inverse guard: an earlier revision refused ANY module-valued attribute, which broke
        # `collections.abc.Mapping` -- ordinary pure code. With the allowlist down to four
        # modules, none of which has a public submodule, that branch can no longer be reached
        # through a lane file at all, so it is tested directly on the predicate. It is still
        # load-bearing: without it every module-valued attribute is refused again.
        import types as _t
        fake = _t.ModuleType("re.sub_thing")
        self.assertIsNone(dc._module_reach_problem("re.sub_thing", fake, False))

    def test_the_name_test_separates_the_two_cases(self):
        import types as _t
        for base, (attr, real) in sorted(self.REEXPORTS.items()):
            resolved = dc._resolve(f"{base}.{attr}")
            self.assertIsInstance(resolved, _t.ModuleType, f"{base}.{attr}")
            self.assertEqual(resolved.__name__, real)
            self.assertNotEqual(resolved.__name__, f"{base}.{attr}")

    def test_resolve_refuses_a_module_outside_the_allowlist(self):
        self.assertIsNone(dc._resolve("os"))
        self.assertIsNone(dc._resolve("socket.socket"))

    def test_an_unresolvable_path_fails_closed(self):
        # Round four, escape 12. `from json import tool` was unresolvable, because json.__init__
        # does not bind its `tool` submodule; the old resolver returned None for that and both
        # callers read None as "not a module, carry on", so the rule was skipped entirely and
        # `tool.argparse.FileType("w")` wrote a file while the tool reported PASS.
        self.assertIs(dc._resolve("re.no_such_attribute_exists"), dc.UNRESOLVED)
        self.assertIn("MODULE_REACH",
                      self.codes("from re import no_such_attribute_exists\n"))
        self.assertIn("MODULE_REACH",
                      self.codes("import re\n\n\ndef f():\n"
                                 "    return re.no_such_attribute_exists\n"))


class TestMutableModuleState(LaneCase):
    """The shape rules refuse module-level statements; they did not refuse shared mutable state."""

    def test_subscript_store_on_a_module_level_name(self):
        self.assertEqual(self.codes("CACHE: dict = {}\n\n\ndef put(k, v):\n    CACHE[k] = v\n"),
                         ["MUTABLE_MODULE_STATE"])

    def test_subscript_delete_on_a_module_level_name(self):
        self.assertEqual(self.codes("CACHE = {}\n\n\ndef drop(k):\n    del CACHE[k]\n"),
                         ["MUTABLE_MODULE_STATE"])

    def test_mutator_calls_on_a_module_level_name(self):
        for method in ("append", "extend", "update", "add", "pop", "clear", "sort"):
            source = f"SEEN = []\n\n\ndef add(x):\n    SEEN.{method}(x)\n"
            self.assertEqual(self.codes(source), ["MUTABLE_MODULE_STATE"], method)

    def test_tuple_and_starred_targets_are_module_level_too(self):
        """The spelling a review proved open: the collector saw only `ast.Name` targets.

        `CACHE, SEEN = {}, []` bound two module-level names that the rule could not see, so the
        same two mutations it refuses under `CACHE = {}` returned PASS. Nested and starred targets
        are pinned with it, because the gap was in unpacking rather than in tuples as such.
        """
        cases = (
            "CACHE, SEEN = {}, []\n\n\ndef put(k, v):\n    CACHE[k] = v\n",
            "SEEN, CACHE = [], {}\n\n\ndef add(x):\n    SEEN.append(x)\n",
            "A, (B, CACHE) = 1, (2, {})\n\n\ndef put(k, v):\n    CACHE[k] = v\n",
            "FIRST, *SEEN = [1, 2]\n\n\ndef add(x):\n    SEEN.append(x)\n",
        )
        for source in cases:
            self.assertEqual(self.codes(source), ["MUTABLE_MODULE_STATE"], source)

    def test_a_walrus_binding_is_module_level_too(self):
        """`X = (SEEN := [])` binds `SEEN` without `SEEN` ever being an assignment target.

        Found by a reviewer confirming the tuple-target fix, who declined to raise it because no
        claim said it was closed. Closed and pinned anyway: same class, four lines.
        """
        self.assertEqual(
            self.codes("X = (SEEN := [])\n\n\ndef add(v):\n    SEEN.append(v)\n"),
            ["MUTABLE_MODULE_STATE"])

    def test_a_walrus_inside_a_function_is_local_and_fine(self):
        """The false positive the first walrus fix introduced, pinned so it cannot come back.

        `ast.walk` descends into `def` bodies, where a walrus binds in the function's scope and not
        the module's, so an entirely pure function was reported as mutating module-level state.
        A rule that refuses correct code is worse than the gap it closed: it is what pressures the
        next author into weakening it.
        """
        source = ('def collect(values):\n'
                  '    if (seen := []) is not None:\n'
                  '        for value in values:\n'
                  '            seen.append(value)\n'
                  '    return seen\n')
        self.assertEqual(self.codes(source), [])

    def test_a_module_level_comprehension_walrus_is_module_level(self):
        """A comprehension is not a scope boundary for `:=`; it binds in the enclosing scope."""
        source = ('VALUES = [y for y in (1, 2) if (ACC := [y])]\n\n\n'
                  'def add(v):\n    ACC.append(v)\n')
        self.assertEqual(self.codes(source), ["MUTABLE_MODULE_STATE"])

    def test_a_local_mutable_is_fine(self):
        self.assertEqual(self.codes("def f(xs):\n    out = []\n    out.append(1)\n"
                                    "    return out\n"), [])

    def test_reading_a_module_level_mapping_is_fine(self):
        self.assertEqual(self.codes('_T = {"a": 1}\n\n\ndef f(k):\n    return _T.get(k)\n'), [])


class TestPurityOfShape(LaneCase):
    def test_async_is_refused(self):
        self.assertEqual(self.codes("async def f():\n    return 1\n"), ["ASYNC_NOT_ALLOWED"])

    def test_await_is_refused(self):
        # Caught by the rule rather than by a syntax error: `await` inside a comprehension parses
        # here, so relying on SyntaxError would have let it through.
        self.assertEqual(self.codes("def f(x):\n    return [await y for y in x]\n"),
                         ["ASYNC_NOT_ALLOWED"])

    def test_await_in_an_async_function_is_refused(self):
        self.assertEqual(self.codes("async def f(x):\n    return await x\n"),
                         ["ASYNC_NOT_ALLOWED"])

    def test_global_statement_is_refused(self):
        self.assertEqual(self.codes("Y = 0\n\n\ndef f():\n    global Y\n    Y = 1\n"),
                         ["MUTABLE_MODULE_STATE"])

    def test_nonlocal_statement_is_refused(self):
        source = "def outer():\n    x = 1\n\n    def inner():\n        nonlocal x\n        x = 2\n"
        self.assertEqual(self.codes(source), ["MUTABLE_MODULE_STATE"])

    def test_module_level_call_runs_at_import_time(self):
        self.assertEqual(self.codes("def f():\n    return 1\n\n\nf()\n"),
                         ["MODULE_LEVEL_WORK"])

    def test_module_level_loop_is_refused(self):
        self.assertEqual(self.codes("TOTAL = 0\nfor i in range(3):\n    TOTAL += i\n"),
                         ["MODULE_LEVEL_WORK"])

    def test_module_level_try_is_refused(self):
        self.assertEqual(self.codes("try:\n    import re\nexcept ImportError:\n    re = None\n"),
                         ["MODULE_LEVEL_WORK"])

    def test_module_level_conditional_other_than_name_guard_is_refused(self):
        self.assertEqual(self.codes("X = 1\nif X:\n    Y = 2\n"), ["MODULE_LEVEL_WORK"])

    def test_the_guard_must_be_exactly_name_equals_main(self):
        # An earlier version accepted any comparison whose left operand was `__name__`, so
        # `if __name__ != "zzz":` ran arbitrary work at import time.
        for test in ('__name__ != "zzz"', '__name__ == "zzz"', '__name__ in ("__main__",)',
                     '__name__ is None'):
            source = f"def f():\n    return 1\n\n\nif {test}:\n    X = f()\n"
            self.assertIn("MODULE_LEVEL_WORK", self.codes(source), test)

    def test_name_guard_is_allowed(self):
        self.assertEqual(self.codes("def f():\n    return 1\n\n\nif __name__ == '__main__':\n"
                                    "    pass\n"), [])

    def test_docstring_and_constants_are_allowed(self):
        self.assertEqual(self.codes('"""Doc."""\nMAX = 3\nNAME: str = "x"\n'), [])

    def test_a_file_that_does_not_parse_is_a_violation_not_a_pass(self):
        self.assertEqual(self.codes("def f(:\n"), ["SYNTAX"])


class TestLaneGating(LaneCase):
    def test_a_file_under_a_lane_root_before_the_lane_is_effective_is_refused(self):
        # Without this, the tool would report PASS on a pure file written before the lane was
        # authorized, and that PASS would read as authorization the tool cannot give.
        self.assertEqual(self.codes(PURE, lane_effective=False), ["LANE_NOT_EFFECTIVE"])

    def test_an_empty_lane_passes_either_way(self):
        for effective in (True, False):
            report = dc.check(self.tmp, effective)
            self.assertEqual(report["result"], "PASS")
            self.assertEqual(report["files_checked"], [])

    def test_a_non_python_file_in_a_lane_root_is_refused(self):
        (self.lane / "notes.md").write_text("notes\n", encoding="utf-8")
        report = dc.check(self.tmp, True)
        self.assertEqual([v["code"] for v in report["violations"]], ["NON_PYTHON_FILE"])

    def test_the_tests_root_is_inside_the_single_lane_root(self):
        # Round four, F5. There used to be two lane roots, backend/app/tenancy/domain and
        # backend/tests/domain, and no slice could write a test: the check permitted exactly the
        # import spelling that fails at runtime and refused the only one that works. Tests now
        # live inside the source package, so a test reaches its subject by `from ..x import y` --
        # one relative import inside one package, which the containment test already handles and
        # which agrees with runtime exactly.
        self.assertEqual(len(dc.LANE_ROOTS), 1)
        self.assertTrue(dc.TESTS_ROOT.startswith(dc.LANE_ROOTS[0] + "/"))
        base = self.tmp / dc.TESTS_ROOT
        base.mkdir(parents=True)
        (base / "test_slice.py").write_text("import os\n", encoding="utf-8")
        report = dc.check(self.tmp, True)
        self.assertEqual([v["file"] for v in report["violations"]],
                         [f"{dc.TESTS_ROOT}/test_slice.py"])

    def test_module_level_reach_is_refused(self):
        # Executed by a reviewer as a clock read at import time:
        # STARTED_AT = calendar.datetime.datetime.now()
        self.assertIn("MODULE_REACH",
                      self.codes("import dataclasses\n\nSTARTED = dataclasses.inspect\n"))

    def test_lane_roots_are_not_configurable(self):
        # Fixed in the module so a slice cannot widen its own scope. Pinned because making them a
        # parameter would quietly remove the boundary.
        self.assertEqual(dc.LANE_ROOTS, ("backend/app/tenancy/domain",))
        self.assertEqual(dc.TESTS_ROOT, "backend/app/tenancy/domain/tests")

    def test_the_pure_root_is_below_the_gated_s1_path(self):
        # backend/app/tenancy/ is an ADR-0002 D12 S1 path; the lane is a sub-root of it so code
        # needing PostgreSQL stays in the parent and stays gated.
        self.assertTrue(dc.LANE_ROOTS[0].startswith("backend/app/tenancy/"))
        self.assertNotEqual(dc.LANE_ROOTS[0], "backend/app/tenancy")

    def test_pycache_is_refused(self):
        # Round four, escape 15. This test previously ASSERTED the skip. A hash-based .pyc whose
        # flags word is 0b01 is "unchecked", and CPython loads it without validating the source,
        # so the planted module kept its advertised API -- a test suite saw nothing wrong -- while
        # writing a file and reading the wall clock from bytecode the tool never saw.
        cache = self.lane / "__pycache__"
        cache.mkdir()
        (cache / "slice.cpython-313.pyc").write_bytes(b"\x00")
        (self.lane / "slice.py").write_text(PURE, encoding="utf-8")
        report = dc.check(self.tmp, True)
        self.assertEqual([v["code"] for v in report["violations"]], ["PYCACHE_IN_LANE"])

    def test_an_irregular_file_is_refused(self):
        # The walk's triage had no else branch, so a node that was neither directory nor regular
        # file was silently dropped -- and a FIFO is importable.
        import os as _os
        _os.mkfifo(self.lane / "fifo_mod.py")
        report = dc.check(self.tmp, True)
        self.assertEqual([v["code"] for v in report["violations"]], ["IRREGULAR_FILE"])


class TestTheLaneIsActuallyUsable(LaneCase):
    """The one-root layout, pinned end to end rather than asserted in a document.

    Round four proved that with the tests at `backend/tests/domain/` a lane test could not import
    its subject by any spelling, so §3.3's "its unit tests are its whole evidence" rested on tests
    that could not be written. The fix was structural -- one root with the tests inside it -- and a
    later review observed that nothing in this suite pinned it: the runtime half had been verified
    by hand. These two tests close that, because a layout nobody exercises is the kind of thing
    that regresses silently.
    """

    def _usable_slice(self):
        """A source module and a test that imports it, laid out as a real slice must be."""
        source = ('"""Subject."""\nfrom __future__ import annotations\n\n\n'
                  'def double(value: int) -> int:\n    return value * 2\n')
        test = ('"""Its test."""\nfrom __future__ import annotations\n\nimport unittest\n\n'
                'from .. import subject\n\n\n'
                'class T(unittest.TestCase):\n'
                '    def test_double(self) -> None:\n'
                '        self.assertEqual(subject.double(3), 6)\n')
        lane = self.tmp / dc.LANE_ROOTS[0]
        tests = self.tmp / dc.TESTS_ROOT
        tests.mkdir(parents=True, exist_ok=True)
        (lane / "__init__.py").write_text('"""Lane package."""\n', encoding="utf-8")
        (tests / "__init__.py").write_text('"""Tests package."""\n', encoding="utf-8")
        (lane / "subject.py").write_text(source, encoding="utf-8")
        (tests / "test_subject.py").write_text(test, encoding="utf-8")
        # `backend/app/__init__.py` exists in the repository; `backend/app/tenancy/` has none and
        # works as a namespace portion, which is why a slice writes nothing outside the lane root.
        (self.tmp / "backend/app/__init__.py").write_text('"""App."""\n', encoding="utf-8")

    def test_a_real_slice_with_its_tests_passes_the_closure(self):
        self._usable_slice()
        report = dc.check(self.tmp, True)
        self.assertEqual(report["result"], "PASS", report.get("violations"))
        self.assertEqual(len(report["files_checked"]), 4)

    def test_the_lane_tests_run_under_the_invocation_ci_uses(self):
        """`from .. import subject` must resolve, under the exact command the CI step runs.

        The absolute spelling `from app.tenancy.domain import subject` also runs here but is
        refused by the closure check, and it binds whichever top-level `app` package is first on
        `sys.path`; the relative one cannot. That asymmetry is why a slice uses the relative form,
        and the closure check refusing the absolute form is a cost the lane record discloses.
        """
        import subprocess
        self._usable_slice()
        done = subprocess.run(
            [sys.executable, "-m", "unittest", "discover",
             "-s", str(Path(dc.TESTS_ROOT).relative_to("backend")), "-t", "."],
            cwd=str(self.tmp / "backend"), capture_output=True, check=False)
        self.assertEqual(done.returncode, 0,
                         done.stderr.decode("utf-8", "replace"))
        self.assertIn("Ran 1 test", done.stderr.decode("utf-8", "replace"))


class TestLaneContainment(LaneCase):
    """Escape ten and round three's finding 2: reaching code the lane walk never checks.

    Both were PASS results on earlier revisions and both were confirmed by execution, not by
    reading: the imported module read the process id and the wall clock in each case.
    """

    def test_relative_import_out_of_the_lane_is_refused(self):
        # `..` from backend/app/tenancy/domain/ is backend/app/tenancy/ -- the ADR-0002 D12-gated
        # S1 directory -- so this is the lane importing exactly the code it exists to keep gated.
        self.assertEqual(self.codes("from ..impure import do_it\n"), ["LANE_ESCAPE"])

    def test_relative_imports_climbing_out_are_refused(self):
        for source in ("from ...app.main import app\n",
                       "from .. import impure\n",
                       "from ....backend.app.main import app\n"):
            self.assertEqual(self.codes(source), ["LANE_ESCAPE"], source)

    def test_climbing_above_the_repository_root_is_refused(self):
        self.assertEqual(self.codes("from ........... import x\n"), ["LANE_ESCAPE"])

    def test_intra_lane_relative_imports_are_still_allowed(self):
        # The fix must not forbid relative imports as a class: every lane file is itself walked,
        # so an intra-lane import composes purity rather than escaping it.
        for source in ("from . import sibling\n",
                       "from .sibling import thing\n",
                       "from .sub.deeper import thing\n"):
            self.assertEqual(self.codes(source), [], source)

    def test_symlinked_directory_inside_a_lane_root_is_refused(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "evil.py").write_text("import os, time\n", encoding="utf-8")
        (self.lane / "ext").symlink_to(outside, target_is_directory=True)
        (self.lane / "slice.py").write_text("from .ext.evil import do\n", encoding="utf-8")
        report = dc.check(self.tmp, True)
        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("SYMLINK_IN_LANE", {v["code"] for v in report["violations"]})
        # The import target is LEXICALLY inside the lane, so no import rule objects to it; the
        # defect was that the walk never enumerated the file. Assert it is still not enumerated,
        # so a future change cannot "fix" this by silently following the link instead.
        self.assertNotIn(f"{dc.LANE_ROOTS[0]}/ext/evil.py", report["files_checked"])

    def test_symlinked_file_inside_a_lane_root_is_refused(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        target = outside / "evil.py"
        target.write_text("import os\n", encoding="utf-8")
        (self.lane / "linked.py").symlink_to(target)
        report = dc.check(self.tmp, True)
        self.assertEqual(sorted({v["code"] for v in report["violations"]}), ["SYMLINK_IN_LANE"])

    def test_a_symlinked_lane_root_is_refused(self):
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "x.py").write_text("import os\n", encoding="utf-8")
        shutil.rmtree(self.lane)
        self.lane.symlink_to(elsewhere, target_is_directory=True)
        report = dc.check(self.tmp, True)
        self.assertEqual(sorted({v["code"] for v in report["violations"]}), ["SYMLINK_IN_LANE"])


class TestAnnotationStrings(LaneCase):
    """Round three's finding 1: a string annotation is code this tool never parses.

    `def _rule() -> "print('...') or int"` with `typing.get_type_hints(_rule)` returned PASS and
    then executed the string's contents, because `get_type_hints` evaluates the annotation text
    against the function's `__globals__`, whose `__builtins__` is the whole builtins table. No
    forbidden import, bare name, attribute or dunder was involved.
    """

    def test_string_return_annotation_is_refused(self):
        source = ('import typing\n'
                  'def _rule() -> "print(1) or int":\n'
                  '    return 0\n'
                  'def resolve():\n'
                  '    return typing.get_type_hints(_rule)\n')
        self.assertIn("ANNOTATION_STRING", self.codes(source))

    def test_string_argument_and_variable_annotations_are_refused(self):
        self.assertEqual(self.codes('def f(x: "int") -> None:\n    return None\n'),
                         ["ANNOTATION_STRING"])
        self.assertEqual(self.codes('v: "int" = 1\n'), ["ANNOTATION_STRING"])

    def test_nested_string_annotation_is_refused(self):
        # get_type_hints resolves forward references inside generics, so a nested string is
        # evaluated as surely as a top-level one. Banning only the top-level form would leave
        # list["..."] open.
        self.assertEqual(
            self.codes('def f(x: list["print(1) or int"]) -> None:\n    return None\n'),
            ["ANNOTATION_STRING"])

    def test_expression_annotations_are_allowed(self):
        # The rule must not refuse ordinary typed domain code.
        source = ('from __future__ import annotations\n'
                  'def f(x: int, y: str | None = None) -> tuple[int, ...]:\n'
                  '    return (x,)\n')
        self.assertEqual(self.codes(source), [])


class TestRealRepository(unittest.TestCase):
    def test_the_real_repository_passes_the_closure_check(self):
        """Whatever the lane holds here, the check passes and the walk stayed inside the lane.

        This replaced an assertion that `files_checked` was empty. That one held only while no
        slice existed: it failed on the first published slice however pure that slice was, so
        wiring this suite into CI and then publishing a slice would have reddened `main` -- and the
        obvious way to go green again would have been the slice's own author deleting an assertion
        from the checker that judges the slice. `tools/domain_closure/` is not a controlled path,
        so nothing would have stopped that. These assertions hold before and after the first slice,
        and they narrow the gate rather than loosen it: a stray file outside the lane roots, or any
        violation at all, still fails.
        """
        report = dc.check(REPO, dc._owner_record_effective(REPO))
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["violations"], [])
        for path in report["files_checked"]:
            self.assertTrue(any(path.startswith(root + "/") for root in dc.LANE_ROOTS),
                            f"{path} is outside the lane roots {dc.LANE_ROOTS}")
        source = [p for p in report["files_checked"] if not p.startswith(dc.TESTS_ROOT + "/")]
        named = [p for p in report["files_checked"]
                 if p.startswith(dc.TESTS_ROOT + "/") and p.rsplit("/", 1)[-1].startswith("test")]
        if source and not named:
            self.fail("lane source exists with no test file under "
                      f"{dc.TESTS_ROOT}: the owner record's section 3.3 makes a slice's unit tests "
                      "its entire evidence, so source without tests is not a publishable slice")

    def test_an_uncommitted_draft_of_the_record_does_not_open_the_lane(self):
        """The detector requires the record to be tracked, not merely to exist on disk.

        This is a regression test for a real flaw: the first version returned True for any file
        present, so writing the draft would have opened the lane before it was attested, reviewed,
        published or CI-verified. The draft may or may not be on disk when this runs; what is
        asserted is the rule -- an untracked path is not effective.
        """
        self.assertFalse(dc._owner_record_effective(REPO) and not _tracked(dc.RECORD_PATH))

    def test_the_detector_agrees_with_git(self):
        import subprocess
        tracked = _tracked(dc.RECORD_PATH)
        self.assertEqual(dc._owner_record_effective(REPO), tracked)

    def test_the_result_discloses_what_effectiveness_was_not_verified(self):
        report = dc.check(REPO, dc._owner_record_effective(REPO))
        self.assertIn("does NOT verify", report["lane_effective_basis"])
        self.assertIn("attestation", report["lane_effective_basis"])


class TestCli(unittest.TestCase):
    def run_main(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = dc.main(argv)
        return code, json.loads(buf.getvalue())

    def test_check_on_the_repository_exits_zero(self):
        code, out = self.run_main(["check", "--root", str(REPO)])
        self.assertEqual((code, out["result"]), (0, "PASS"))

    def test_explain_lists_the_policy(self):
        code, out = self.run_main(["explain"])
        self.assertEqual(code, 0)
        self.assertIn("os", out["forbidden_imports"])
        self.assertIn("open", out["forbidden_builtins"])
        self.assertIn("sys", out["forbidden_attribute_names"])
        self.assertIn("unittest.mock", out["forbidden_module_paths"])
        self.assertEqual(out["allowed_dunder_strings"], ["__main__"])
        self.assertIn("re", out["allowed_imports"])

    def test_missing_root_is_malformed(self):
        code, out = self.run_main(["check", "--root", "/nonexistent-veyro-root"])
        self.assertEqual((code, out["result"]), (2, "MALFORMED"))

    def test_check_does_not_claim_a_pass_proves_purity(self):
        """The field used to be `purity_only` and asserted the file "performs no I/O".

        That is the inference the lane record forbids a slice reviewer from drawing, and the tool
        emitted it on every run -- so the test pinned the wrong thing and would have kept pinning
        it. It now asserts the honest wording and, explicitly, that the old overclaim is gone.
        """
        _, out = self.run_main(["check", "--root", str(REPO)])
        self.assertNotIn("purity_only", out)
        self.assertIn("no route these rules know of", out["pass_means"])
        self.assertIn("NOT evidence that the file performs no I/O", out["pass_means"])
        self.assertIn("tenant isolation", out["pass_means"])


if __name__ == "__main__":
    unittest.main()
