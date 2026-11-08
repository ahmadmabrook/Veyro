#!/usr/bin/env python3
"""Veyro local-domain-slice closure check (Python stdlib only, no network, never writes).

  domain_closure.py check --root R          every file under the lane roots must be pure
  domain_closure.py explain                 print the policy this tool enforces

Exit 0 = PASS, 1 = BLOCKED (stdout JSON lists violations), 2 = malformed input/usage (fail closed).

**What this is for.** It is the mechanical boundary of the local-domain-slice lane: the thing that
makes "pure domain logic, no I/O" a filter rather than only a promise an author makes in a commit
message. It is **not** what makes the lane defensible -- an earlier revision of this paragraph said
it was, and the lane's owner record withdrew that: what the supersession rests on is each slice's
unit tests, the independent exact-diff review of every slice, and the bar on citing a slice as
evidence of anything. See "This is a mistake filter, not a sandbox" below, which is the paragraph
to read before relying on a PASS. The lane itself is established by
`knowledge/00-Decisions/OWNER-2026-11-07-local-domain-slice-lane.md`; until that record is
published and effective, **no file may exist under the lane roots at all**, and this tool reports
any that do as a violation rather than checking them.

**One lane root**, fixed here rather than configurable, so a slice cannot widen its own scope:

    backend/app/tenancy/domain/**            pure domain logic
    backend/app/tenancy/domain/tests/**      its unit tests, inside the same root

`backend/app/tenancy/domain/` is deliberately a *sub*-root of the ADR-0002 D12 S1 path
`backend/app/tenancy/`. Code that needs PostgreSQL lives in the parent directory and stays gated by
D12 until the module is Ready and the manifest ACTIVE; this tool never looks there.

The tests live *inside* the source package rather than at `backend/tests/domain/`, which is where an
earlier version put them, because with two separate roots **the lane's tests could not import the
lane's source at all** -- a fourth review proved all three spellings fail: a repository-root
absolute import is refused by this check and raises `ModuleNotFoundError` under CI's own
`discover -s tests -t .`; a relative import is permitted by this check but raises `ImportError:
attempted relative import beyond top-level package`; and a backend-root absolute import runs but is
refused here. The first fix proposed for that was worse than the bug: mapping the repository-root
spelling onto the backend root fails *open*, because any foreign top-level `app` package earlier on
`sys.path` then binds and runs instead, and it hard-codes one CI invocation into the import graph.
One root with the tests inside it needs no mapping: `python3 -m unittest discover -s
app/tenancy/domain/tests -t .` from `backend/` imports the source as an ordinary sibling package.

**The closure, checked with `ast`, and what reading an AST does not buy on its own.** The S0
slice's closure was reviewed with the warning that a reviewer "must inspect reflection, frames,
match-class patterns, mock.patch string targets and dynamic imports as well as direct forbidden
imports". An earlier revision of this docstring claimed that using an AST rather than a regex
answered that warning. **It did not**, and an independent review proved three escapes against that
version, each of which contained no forbidden import statement, no forbidden bare name and no
forbidden attribute spelled as an attribute:

  * `unittest.case.sys.modules["os"]` -- an allow-listed module re-exporting a forbidden one, with
    the forbidden module reached through plain attributes and its name appearing only as a string;
  * `operator.attrgetter("__globals__")(fn)["__builtins__"]` -- a string-target reflection helper
    reaching a refused attribute, needing only `operator` and a local `def`;
  * `from unittest import mock` -- a submodule of an allow-listed package, where only the package
    name was being checked, and `mock.patch` takes a dotted string target.

A **second** review then proved six more against the fix for those three, because that fix banned
the literal names `sys`, `os` and `modules` -- three instances, not a class. The standard library
re-exports forbidden modules under names chosen by the standard library: `statistics._random` is
`random`, `collections._sys` is `sys`, `enum.bltns` is `builtins`, `calendar.datetime` is
`datetime`, `dataclasses.inspect` is `inspect`, `hashlib._hashlib` is `_hashlib`. The reviewer
executed arbitrary code execution, an outbound TCP connection, a file read, a clock read, entropy
consumption and `os.system` through them.

From any of those a handle is in hand, and arbitrary file access, a real network connection
including to PostgreSQL, a subprocess, a clock read and entropy follow by ordinary CPython
semantics.

**Which rules are property rules and which are still enumerations**, because an earlier revision of
this docstring claimed all of them refused "whole classes of reach rather than enumerated names"
while the load-bearing one was a name list. Property rules, which test the thing rather than its
spelling: MODULE_REACH resolves the module at check time and compares its own `__name__` to the
path it was reached by, so a re-export is refused however it is named while a genuine submodule
such as `collections.abc` passes; **two** of the three dunder rules -- the attribute rule and the string
rule -- refuse any `__dunder__` as a class, while the third is the ten-name FORBIDDEN_DUNDER_DEFS
list and belongs with the enumerations below; and
MUTABLE_MODULE_STATE tests whether a mutated name is module-level. Still enumerations, and
therefore still only as good as the list: FORBIDDEN_IMPORTS, FORBIDDEN_ATTR_NAMES, the reach
primitives, FORBIDDEN_BUILTINS, FORBIDDEN_DUNDER_DEFS and MUTATORS. The lesson is recorded rather
than quietly fixed, because the next author will be tempted to relax one of these rules to make a
slice compile, and the reason each exists is a working escape.

A file under a lane root passes only if all of the following hold.

  * Every `import` and `from ... import` names a module in ALLOWED_IMPORTS, matched on the
    top-level package. The list admits only modules that compute: no filesystem, no network, no
    clock, no randomness, no process, no database, no third-party.
  * A relative import must resolve to a path inside a lane root. An earlier version returned
    immediately for any relative import, with the comment "a relative import stays inside the
    lane" -- which is false: from `backend/app/tenancy/domain/`, `from ..impure import x` resolves
    to `backend/app/tenancy/`, the ADR-0002 D12-gated S1 directory, so the lane could import the
    very code it exists to keep gated. The target is now computed from the importing file's own
    position and `level` and must be lane-contained. A **star** relative import is refused. A
    **bare** one (`from . import sibling`, `module is None`) is *permitted* when lane-contained:
    it is how a slice imports a sibling and how a lane test imports its subject. Two revisions
    claimed here that it was refused, which was never true -- the flag that would have refused it
    sat after an unconditional `return`. A review caught the dead code and the claim; a second
    review caught that this sentence, six hundred lines from the code, had been left behind when
    the others were corrected. Recorded because that is the same defect one layer up: a document
    asserting a correction that was not made.
  * Every `from X import n` also checks `X.n` as a module path, so a submodule of an allow-listed
    package cannot enter unchecked. FORBIDDEN_MODULE_PATHS refuses such a path by name.
  * `unittest` is admitted only under `backend/app/tenancy/domain/tests/`. Domain source never
    needs it, and it
    re-exports `sys`.
  * No name in FORBIDDEN_BUILTINS is called or referenced: `open`, `eval`, `exec`, `compile`,
    `__import__`, `input`, `breakpoint`, `print`, `globals`, `locals`, `vars`, `getattr`,
    `setattr`, `delattr`. `getattr` and friends are refused because they are how a forbidden
    attribute is reached without naming it. `print` is refused because the S0 contract is that
    such code "logs nothing", and stdout is a side effect.
  * **No module reached through another module's attribute**, unless it is a genuine submodule
    whose own `__name__` equals the path it was reached by and whose top-level is allow-listed.
    This is the rule that closes the private-alias class, and it is checked by importing the
    allow-listed module rather than by matching its name.
  * **No attribute in FORBIDDEN_ATTR_NAMES**, which includes every forbidden module name, so
    `anything.sys`, `anything.os` and `anything.socket` are refused however they were reached; the
    reach primitives `modules`, `builtins`, `attrgetter`, `methodcaller`, `itemgetter`; and
    `getattr`, `setattr`, `delattr`, `globals`, `locals`, `vars`, `eval`, `exec`, `open`,
    `__import__` as attributes. Note that `compile` is deliberately **not** here: banning it as an
    attribute broke `re.compile`, which is the first thing a real slice writes.
  * **No `__dunder__` attribute at all**, except `__doc__` and `__name__`. A class rule, not a
    list: the enumerated list this replaced admitted `__reduce__` and `__getattribute__` because
    nobody had thought of them.
  * **No `__dunder__` string literal**, except `"__main__"` for the name guard. A dunder written as
    a string is how a string-target helper names an attribute the closure refuses.
  * **No definition of a dunder hook** in FORBIDDEN_DUNDER_DEFS -- `__getattr__`,
    `__getattribute__`, `__setattr__`, `__delattr__`, `__reduce__`, `__reduce_ex__`,
    `__init_subclass__`, `__set_name__`, `__mro_entries__`, `__class_getitem__` -- each of which
    would let an object answer for an attribute the closure refused, or re-enter class creation.
    Ordinary dunders a dataclass needs, such as `__post_init__`, `__eq__` and `__hash__`, are
    allowed.
  * No `async def`, `await`, `global` or `nonlocal` statement. The first two would need a runtime
    this lane does not have; the last two are mutable module state, and the lane's contract is that
    a slice keeps none. There is **no `yield` rule**: an earlier revision of this line claimed one
    ("`yield` into an event loop") and the code has never had it. A generator is pure, so the gap is
    harmless, but the claim was not -- it is the same defect as the bare-relative-import sentence,
    found the same way, by a reviewer reading the code instead of the list.
  * No module-level statement other than an import, a docstring, an assignment, a `pass`, a
    `def`/`class`, or an `if __name__ == "__main__"` guard written exactly that way. Module-level work runs at
    import time, which is a side effect of being imported. An assignment may call, because
    everything callable is inside the closure -- `_P = re.compile(...)` is ordinary -- but the
    guard comparison is exact: an earlier revision accepted any comparison whose left operand was
    `__name__`, so `if __name__ != "zzz":` ran arbitrary work at import time.
  * **No mutation of module-level state.** A subscript store or delete on a module-level name, or a
    mutator method called on one, is refused. `global` and `nonlocal` were already refused, but
    they are not how shared state is usually kept: a module-level `CACHE = {}` written by
    `CACHE[k] = v` inside a function persists across calls and passed every earlier rule.

**This is a mistake filter, not a sandbox. Read this paragraph before relying on a PASS.**

The check reads source files in this repository. Anyone who can write a file under the lane root
can also write *this file*: `tools/domain_closure/` is not a controlled path, so no ADR, no owner
record and no validator stands between an author and the rules that judge them. A boundary its own
subject can edit cannot resist a hostile author, and nothing in the lane's authorizing record rests
on the claim that it does. What it resists is an *ordinary author's mistake*: importing something
impure, reaching a forbidden module through an allowed one's attribute, writing a relative import
that leaves the lane, leaving a stale `.pyc` behind, keeping state in a module-level dict.

Four review rounds have proved escapes against four successive versions of this check, and in each
round the previous round's remedy supplied part of the next route -- most sharply in round four,
where the module rule that round two's property test had installed was found to **fail open**,
returning the same `None` for "not a module, carry on" as for "could not resolve", so an unresolved
path was read as permission. Of the proved routes, nearly all are deliberate constructions no domain
author would write by accident. The four that an ordinary author could have hit are the out-of-lane
relative import, the stale hash-based `.pyc` that ran while its `.py` passed, process-wide mutable
state inside an allow-listed stdlib module, and the import gap that made lane tests impossible.
Those four are closed. The counts themselves have drifted across revisions -- earlier text here and
in the authorizing record gives eleven, fifteen and seventeen for the same artifacts, because "an
escape" was never defined and a class demonstrated through six aliases is one route or six depending
on the counting. The disagreement is left on the record rather than resolved, because no decision
rests on the number, and a tally of closed escapes invites exactly the reading this paragraph
rejects: that a high score is evidence of safety.

So: a PASS means **no route these rules know of**, over files this walk enumerated. It is evidence
that an author did not make one of the mistakes the rules cover. It is not evidence that the file
performs no I/O, and a slice reviewer may not treat it as such -- the independent exact-diff review
of each slice is the control, and this check is the filter that keeps that review from spending
itself on mistakes a machine can catch. It means **nothing** about
whether the logic is correct, whether a tenant is isolated, whether a caller is authenticated or
authorized, or whether any database constraint exists. Tenant isolation is enforced by PostgreSQL
RLS, which this lane cannot write and does not evidence; a passing slice is not isolation evidence,
not a security pass, not Implementation Complete and not module acceptance. Those remain gated
where they were.

**A stronger control exists and is not built.** Every rule here reads source; none observes the
slice running. A `sys.addaudithook` refusing the `exec`, `compile`, `import`, `open`, socket and
subprocess events would catch by observation what these rules catch by anticipating a spelling, and
would have caught the annotation and import routes without anyone having to think of them. Its own
limit is that a clock read and entropy consumption raise no audit event. It is recorded in
`knowledge/03-Modules/MOD-004/PRE-PRODUCTION-BACKLOG.md` and not claimed here.
"""
from __future__ import annotations

import argparse
import ast
import importlib
import json
import re
import subprocess
import sys
import types
from pathlib import Path

LANE_ROOTS = ("backend/app/tenancy/domain",)
RECORD_PATH = "knowledge/00-Decisions/OWNER-2026-11-07-local-domain-slice-lane.md"

# Modules that compute and nothing else. Deliberately short; widening it is a change to the lane's
# boundary and belongs in a reviewed change to this file, not in a slice.
ALLOWED_IMPORTS = frozenset({"__future__", "dataclasses", "enum", "re"})
# Four modules, and `unittest` in the tests root. The previous list held thirty-two, and four
# review rounds proved escapes against four successive versions, and the allowlist's own breadth
# supplied the vehicle
# for most: `json.tool` re-exports `argparse`, whose `FileType` is `open` under another name;
# `typing.get_type_hints` evaluates annotation text against a module's globals; `decimal`'s
# context and `calendar`'s first-weekday are process-wide mutable state that made one function
# return two different answers for one input; `statistics`, `collections`, `hashlib` and
# `dataclasses` re-export forbidden modules under private aliases. Every one of those vehicles is
# gone now, because the slice this lane exists for imports exactly these four. Widening the list
# is a reviewed change to this file and should be read as re-opening a closed question: each
# addition brings that module's whole attribute surface, its lazily-imported submodules and its
# process-wide state inside the boundary.
# Named explicitly so a reader sees the intent, and so a violation reports the reason rather than
# only "not in the allowlist". `uuid` is here because uuid4 and getnode reach randomness and the
# network; the S0 slice parses UUIDs with a regex instead, and this lane follows it. `time`,
# `random` and `secrets` are here because a pure function may not read a clock or consume entropy.
FORBIDDEN_IMPORTS = {
    "asyncio": "an event loop is a runtime this lane does not have",
    "concurrent": "process and thread pools are not pure",
    "ctypes": "reaches native code outside the closure",
    "dbm": "filesystem database",
    "glob": "filesystem access",
    "http": "network access",
    "importlib": "dynamic import defeats a static closure",
    "io": "I/O",
    "logging": "writes, and the lane's contract is that a slice logs nothing",
    "multiprocessing": "starts processes",
    "os": "filesystem, environment and process access",
    "pathlib": "filesystem access",
    "pickle": "executes arbitrary code on load",
    "pkgutil": "dynamic import defeats a static closure",
    "psycopg": "database driver; the database half of this module is gated by ADR-0002 D12",
    "psycopg2": "database driver",
    "psycopg_pool": "database driver",
    "random": "a pure function may not consume randomness",
    "runpy": "dynamic execution",
    "secrets": "a pure function may not consume entropy",
    "select": "I/O multiplexing",
    "shelve": "filesystem database",
    "shutil": "filesystem access",
    "signal": "process control",
    "socket": "network access",
    "socketserver": "network access",
    "sqlalchemy": "third-party database library",
    "sqlite3": "database",
    "ssl": "network access",
    "subprocess": "starts processes",
    "sys": "interpreter and stream access",
    "tempfile": "filesystem access",
    "threading": "concurrency is not pure",
    "time": "a pure function may not read a clock",
    "urllib": "network access",
    "uuid": "uuid4 and getnode reach randomness and the network; parse UUIDs textually instead",
    "xmlrpc": "network access",
    "zoneinfo": "reads the system tz database from disk",
}
FORBIDDEN_BUILTINS = frozenset({
    "__import__", "breakpoint", "compile", "delattr", "eval", "exec", "getattr", "globals",
    "input", "locals", "open", "print", "setattr", "vars",
})
# A full dotted path that is refused even though its top-level package is allowed. `unittest.mock`
# is here because `mock.patch` takes a dotted string target, which is reflection by another name.
FORBIDDEN_MODULE_PATHS = {
    "unittest.mock": "mock.patch takes a dotted string target, which is reflection",
}
# `unittest` is needed by the tests root and by nothing in the source root, so it is admitted only
# there. It re-exports `sys` (as `unittest.case.sys`), which is why its reach is also closed below.
TESTS_ONLY_IMPORTS = frozenset({"unittest"})
TESTS_ROOT = "backend/app/tenancy/domain/tests"
# Attribute names refused outright. The forbidden module names are here because an allow-listed
# module can re-export a forbidden one -- `unittest.case.sys.modules["os"]` reached every forbidden
# module through attributes alone, with no import statement and no forbidden Name to see.
# Only the reach primitives, not all of FORBIDDEN_BUILTINS: unioning that set in banned
# `re.compile`, which is ordinary pure code and the first thing a real slice writes.
FORBIDDEN_ATTR_NAMES = frozenset(FORBIDDEN_IMPORTS) | frozenset({
    "modules", "builtins", "builtin", "attrgetter", "methodcaller", "itemgetter",
    "__import__", "delattr", "eval", "exec", "getattr", "globals", "locals", "open", "setattr",
    "vars",
})
# Dunder attributes are refused as a class, with a small allowlist, instead of by enumeration: an
# enumerated denylist missed `__reduce__`, `__getattribute__` and anything else not yet thought of.
ALLOWED_DUNDER_ATTRS = frozenset({"__doc__", "__name__"})
# `__main__` is a module name, not an attribute name, and `if __name__ == "__main__"` is the one
# module-level guard the shape rule admits -- so the dunder-string rule has to let it through.
ALLOWED_DUNDER_STRINGS = frozenset({"__main__"})
# Dunder names a slice may not define. Each is a hook that would let an object answer for an
# attribute the closure refused, or re-enter class creation.
FORBIDDEN_DUNDER_DEFS = frozenset({
    "__class_getitem__", "__delattr__", "__getattr__", "__getattribute__", "__init_subclass__",
    "__mro_entries__", "__reduce__", "__reduce_ex__", "__set_name__", "__setattr__",
})
_DUNDER = re.compile(r"^__\w+__$")


# Methods that mutate a container in place. Used to refuse mutation of module-level state, which
# is shared across every call and is the one kind of impurity the shape rules do not reach.
MUTATORS = frozenset({
    "append", "extend", "insert", "remove", "pop", "clear", "update", "setdefault", "add",
    "discard", "sort", "reverse", "popitem", "appendleft", "extendleft", "rotate",
})


class Malformed(Exception):
    """Usage or input error; always exit 2, never a PASS."""


UNRESOLVED = object()
"""Returned by `_resolve` when a dotted path under an allow-listed top-level cannot be resolved.

Distinct from a resolved non-module, because the two must be treated oppositely. An independent
review proved why: the previous version returned None both for "this is not a module, carry on"
and for "I could not resolve this", and both callers gated the module-reach rule on
`isinstance(resolved, types.ModuleType)`. So an unresolvable path meant *no check at all*.
`from json import tool` was unresolvable -- `json.__init__` does not bind its `tool` submodule --
so the binding was recorded unchecked, and `tool.argparse.FileType("w")` then wrote a file while
the tool reported PASS. Seven such submodules existed under the old allowlist. A rule that fails
open is weaker than the name list it replaced, because a name list cannot silently become empty.
"""


def _resolve(dotted: str) -> object | None:
    """Import an allow-listed module and walk a dotted path on it.

    Returns the object, None when the top-level is not admitted at all (the import rules have
    already refused it, so there is nothing to add), or UNRESOLVED when the path cannot be walked
    -- which the callers must treat as a violation, never as permission.
    """
    parts = dotted.split(".")
    top = parts[0]
    if top not in ALLOWED_IMPORTS and top not in TESTS_ONLY_IMPORTS:
        return None
    try:
        obj: object = importlib.import_module(top)
    except Exception:
        return UNRESOLVED
    for part in parts[1:]:
        try:
            obj = getattr(obj, part)
        except Exception:
            # Not necessarily absent: a submodule the package does not eagerly bind resolves only
            # after it is imported. Either way this check cannot see what the name will be, so it
            # refuses rather than guesses.
            return UNRESOLVED
    return obj


def _module_reach_problem(path: str, resolved: types.ModuleType,
                          in_tests_root: bool) -> str | None:
    """Why reaching this module through an attribute is refused, or None if it is a real submodule.

    A module's own ``__name__`` separates the two cases exactly, which is why this tests the
    property instead of the spelling. A genuine submodule names itself after the path it was
    reached by -- ``collections.abc.__name__`` is ``"collections.abc"`` -- while a re-export names
    the module it actually is: ``statistics._random`` is ``random``, ``collections._sys`` is
    ``sys``, ``enum.bltns`` is ``builtins``, ``calendar.datetime`` is ``datetime``,
    ``dataclasses.inspect`` is ``inspect``, ``hashlib._hashlib`` is ``_hashlib``. The standard
    library chooses those names, so no denylist could have contained them; an earlier revision of
    this file enumerated the public spellings and every private alias walked straight past it.
    """
    name = resolved.__name__
    if name != path:
        return (f"resolves to the module {name!r}, which {path.rsplit('.', 1)[0]} re-exports under "
                f"another name; import a module directly so the import rules apply to it")
    top = name.split(".")[0]
    if name in FORBIDDEN_MODULE_PATHS:
        return f"is {name}: {FORBIDDEN_MODULE_PATHS[name]}"
    if top in FORBIDDEN_IMPORTS:
        return f"is under {top}: {FORBIDDEN_IMPORTS[top]}"
    if top in TESTS_ONLY_IMPORTS and not in_tests_root:
        return f"is under {top}, which is admitted only beneath {TESTS_ROOT}/"
    if top not in ALLOWED_IMPORTS and top not in TESTS_ONLY_IMPORTS:
        return f"is under {top}, which is not in the lane's allowed-import closure"
    return None


def _dotted(node: ast.AST) -> str | None:
    """The dotted name of a pure Name/Attribute chain, or None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


class _Visitor(ast.NodeVisitor):
    def __init__(self, rel: str, module_level_names: frozenset[str]) -> None:
        self.rel = rel
        self.in_tests_root = rel.startswith(TESTS_ROOT + "/")
        self.module_level_names = module_level_names
        self.module_bindings: dict[str, str] = {}
        self.violations: list[dict] = []

    def flag(self, node: ast.AST, code: str, detail: str) -> None:
        self.violations.append({"file": self.rel, "line": getattr(node, "lineno", 0),
                                "code": code, "detail": detail})

    def _check_module(self, node: ast.AST, name: str) -> None:
        top = name.split(".")[0]
        if name in FORBIDDEN_MODULE_PATHS:
            self.flag(node, "FORBIDDEN_IMPORT", f"{name}: {FORBIDDEN_MODULE_PATHS[name]}")
            return
        if top in FORBIDDEN_IMPORTS:
            self.flag(node, "FORBIDDEN_IMPORT", f"{name}: {FORBIDDEN_IMPORTS[top]}")
            return
        if top in TESTS_ONLY_IMPORTS and not self.in_tests_root:
            self.flag(node, "IMPORT_NOT_ALLOWED",
                      f"{name} is admitted only under {TESTS_ROOT}/, not in domain source")
            return
        # The TESTS_ONLY clause matters: without it a tests-only module is refused here even
        # inside the tests root, having just passed the check above. It was invisible while
        # `unittest` sat in ALLOWED_IMPORTS as well, and shrinking that set exposed it.
        if top not in ALLOWED_IMPORTS and top not in TESTS_ONLY_IMPORTS:
            self.flag(node, "IMPORT_NOT_ALLOWED",
                      f"{name} is not in the lane's allowed-import closure")

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_module(node, alias.name)
            local = alias.asname or alias.name.split(".")[0]
            self.module_bindings[local] = alias.name if alias.asname else alias.name.split(".")[0]

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if any(alias.name == "*" for alias in node.names):
            self.flag(node, "FORBIDDEN_IMPORT",
                      "a star import binds names this closure cannot enumerate")
            return
        if node.level:
            problem = self._relative_target_problem(node)
            if problem:
                self.flag(node, "LANE_ESCAPE", problem)
            # An intra-lane target needs no further check here: every lane file is itself walked,
            # so the imported module's own purity is established by its own check. A *bare*
            # relative import (`from . import sibling`, `module is None`) reaches this branch too
            # and is permitted when lane-contained -- it is how a slice imports its own siblings,
            # and how a lane test imports its subject (`from .. import lifecycle`). An earlier
            # revision flagged it below this `return`, where the flag was unreachable, while the
            # docstring and the lane record both claimed bare relative imports were refused; a
            # review caught the dead code and the false claim together. The code was right and the
            # claims were wrong, so the claims changed and the dead flag is gone.
            return
        self._check_module(node, node.module)
        for alias in node.names:
            # `from unittest import mock` names a submodule, not an attribute of an allowed module,
            # so the dotted path has to be checked too: checking only `unittest` let it through.
            dotted = f"{node.module}.{alias.name}"
            self._check_module(node, dotted)
            # `from calendar import datetime` binds the datetime *module*, which no name list
            # could have predicted: the standard library chooses what it re-exports.
            resolved = _resolve(dotted)
            if resolved is UNRESOLVED:
                self.flag(node, "MODULE_REACH",
                          f"{dotted} cannot be resolved at check time, so this check cannot see "
                          f"what the name binds; a submodule a package does not eagerly bind "
                          f"resolves only once imported, and `from json import tool` reached "
                          f"argparse that way. Refused rather than assumed harmless")
            elif isinstance(resolved, types.ModuleType):
                # `from calendar import datetime` binds the datetime *module*. A genuine submodule
                # such as `from collections.abc import Mapping` is a different case and passes.
                problem = _module_reach_problem(dotted, resolved, self.in_tests_root)
                if problem:
                    self.flag(node, "MODULE_REACH", f"{dotted} {problem}")
                else:
                    self.module_bindings[alias.asname or alias.name] = dotted
            else:
                self.module_bindings[alias.asname or alias.name] = dotted

    def _relative_target_problem(self, node: ast.ImportFrom) -> str | None:
        """Whether a relative import resolves outside the lane roots.

        Lexical, on the repository-relative path, which is the right test for the *declared*
        target: `from ..impure import x` names a module outside the lane whatever the filesystem
        looks like. It is deliberately not the whole story -- a target that is lexically inside a
        lane root but reached through a symlinked directory is caught by the walk in `lane_files`,
        not here, because that defect is in what gets enumerated rather than in what is declared.
        """
        parts = self.rel.split("/")[:-1]          # the importing file's own directory
        climb = node.level - 1                    # `level` 1 is "this directory"
        if climb > len(parts):
            return f"climbs {climb} levels above the repository root"
        base = parts[:len(parts) - climb] if climb else parts
        target = "/".join(base + (node.module.split(".") if node.module else []))
        if not any(target == lane or target.startswith(lane + "/") for lane in LANE_ROOTS):
            shown = node.module or ""
            return (f"`from {'.' * node.level}{shown} import ...` resolves to {target!r}, which is "
                    f"outside the lane roots {list(LANE_ROOTS)}; a lane file may import only lane "
                    f"files and the allow-listed standard library")
        return None

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and node.id in FORBIDDEN_BUILTINS:
            self.flag(node, "FORBIDDEN_BUILTIN", node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if _DUNDER.match(node.attr) and node.attr not in ALLOWED_DUNDER_ATTRS:
            self.flag(node, "DUNDER_ESCAPE", node.attr)
        elif node.attr in FORBIDDEN_ATTR_NAMES:
            self.flag(node, "ATTRIBUTE_REACH",
                      f".{node.attr} reaches outside the closure through an allowed object")
        else:
            # The property rule. An attribute of an imported module that is itself a module is
            # refused whatever it is called, because the standard library re-exports forbidden
            # modules under names no denylist can anticipate: `statistics._random` is `random`,
            # `collections._sys` is `sys`, `enum.bltns` is `builtins`, `calendar.datetime` is
            # `datetime`, `dataclasses.inspect` is `inspect`. Each of those passed an enumerated
            # attribute denylist, and from any of them arbitrary I/O follows.
            base = _dotted(node.value)
            if base is not None:
                root = base.split(".")[0]
                bound = self.module_bindings.get(root)
                if bound is not None:
                    target = f"{bound}{base[len(root):]}.{node.attr}"
                    resolved = _resolve(target)
                    if resolved is UNRESOLVED:
                        self.flag(node, "MODULE_REACH",
                                  f"{base}.{node.attr} cannot be resolved at check time, so this "
                                  f"check cannot see what it binds; refused rather than assumed "
                                  f"harmless")
                    elif isinstance(resolved, types.ModuleType):
                        problem = _module_reach_problem(target, resolved, self.in_tests_root)
                        if problem:
                            self.flag(node, "MODULE_REACH", f"{base}.{node.attr} {problem}")
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            target = _dotted(node.value)
            if target and target.split(".")[0] in self.module_level_names:
                self.flag(node, "MUTABLE_MODULE_STATE",
                          f"{target} is module-level, so writing to it keeps state across calls")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr in MUTATORS:
            target = _dotted(node.func.value)
            if target and target.split(".")[0] in self.module_level_names:
                self.flag(node, "MUTABLE_MODULE_STATE",
                          f"{target}.{node.func.attr}() mutates module-level state")
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        # A dunder written as a string is how a string-target helper reaches an attribute the
        # closure refuses: `operator.attrgetter("__globals__")(fn)["__builtins__"]` needed no
        # forbidden import, no forbidden Name and no forbidden Attribute.
        if (isinstance(node.value, str) and _DUNDER.match(node.value)
                and node.value not in ALLOWED_DUNDER_STRINGS):
            self.flag(node, "DUNDER_ESCAPE", f"the string {node.value!r} is an attribute name")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name in FORBIDDEN_DUNDER_DEFS:
            self.flag(node, "DUNDER_ESCAPE",
                      f"defining {node.name} would let an object answer for a refused attribute")
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.flag(node, "ASYNC_NOT_ALLOWED", node.name)
        self.generic_visit(node)

    def visit_Await(self, node: ast.Await) -> None:
        self.flag(node, "ASYNC_NOT_ALLOWED", "await")
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> None:
        self.flag(node, "MUTABLE_MODULE_STATE", ", ".join(node.names))

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.flag(node, "MUTABLE_MODULE_STATE", ", ".join(node.names))


def _assigned_names(target: ast.expr) -> set[str]:
    """Every name an assignment target binds, unpacking tuple and list targets recursively.

    `a = ...` binds one name; `a, b = ...` binds two; `a, (b, c) = ...` binds three; `a[k] = ...`
    and `a.x = ...` bind none, since they mutate an existing object rather than binding a
    module-level name. Starred targets (`a, *rest = ...`) bind their inner name.
    """
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, ast.Starred):
        return _assigned_names(target.value)
    if isinstance(target, (ast.Tuple, ast.List)):
        found: set[str] = set()
        for element in target.elts:
            found.update(_assigned_names(element))
        return found
    return set()


def _walrus_names(node: ast.stmt) -> set[str]:
    """Names bound by a `:=` anywhere inside a module-level statement.

    `X = (SEEN := [])` binds `SEEN` at module level without `SEEN` ever being an assignment
    target, so the target walk above cannot see it and `SEEN.append(v)` passed every rule. A
    reviewer found this while confirming the tuple-target fix and declined to raise it, since no
    claim said it was closed. It is closed anyway: it is the same class as the tuple gap, four
    lines to cover, and leaving a known hole inside a rule just corrected is how the next false
    claim gets written.

    A plain `ast.walk` is wrong here, and it was the first attempt. It descends into `def`,
    `lambda` and `class` bodies, where a walrus binds in *that* scope and not at module level, so a
    pure slice holding `if (seen := []) is not None: ... seen.append(value)` entirely inside one
    function was reported as mutating module-level state. That is a false positive on ordinary pure
    code -- exactly the kind of refusal that pressures the next author into weakening a rule -- and
    it was caught by execution before review rather than by reading the diff.

    The fix is deliberately conservative: a statement that introduces a scope contributes nothing.
    A walrus in a module-level `def`'s decorator or default argument *does* bind module-globally and
    is therefore missed, which is noted rather than handled, because that is a contrived
    construction and the alternative is field-level surgery on a load-bearing rule for no
    author-hittable gain. Comprehensions are not scope boundaries for this purpose: a walrus inside
    a module-level comprehension binds in the enclosing module scope and is collected.
    """
    scope_boundaries = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
    if isinstance(node, scope_boundaries):
        return set()
    found: set[str] = set()
    pending: list[ast.AST] = [node]
    while pending:
        for child in ast.iter_child_nodes(pending.pop()):
            if isinstance(child, scope_boundaries):
                continue
            if isinstance(child, ast.NamedExpr) and isinstance(child.target, ast.Name):
                found.add(child.target.id)
            pending.append(child)
    return found


def _module_level_problem(node: ast.stmt) -> str | None:
    """Module-level work runs when the module is imported, which is a side effect."""
    # AsyncFunctionDef is listed so an `async def` reports ASYNC_NOT_ALLOWED alone rather than
    # also reporting MODULE_LEVEL_WORK; one violation, one reason.
    if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef,
                         ast.ClassDef, ast.AnnAssign, ast.Assign, ast.Expr, ast.Pass)):
        if isinstance(node, ast.Expr) and not isinstance(node.value, ast.Constant):
            return "a module-level expression runs at import time"
        return None
    if isinstance(node, ast.If):
        test = node.test
        # Exactly `__name__ == "__main__"`. An earlier version accepted any comparison whose left
        # operand was `__name__`, so `if __name__ != "zzz":` ran arbitrary work at import time.
        if (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name)
                and test.left.id == "__name__" and len(test.ops) == 1
                and isinstance(test.ops[0], ast.Eq) and len(test.comparators) == 1
                and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value == "__main__"):
            return None
        return ('a module-level conditional other than `if __name__ == "__main__"` runs at '
                "import time")
    return f"{type(node).__name__} at module level runs at import time"


def check_file(root: Path, rel: str) -> list[dict]:
    path = root / rel
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise Malformed(f"cannot read {rel}: {exc}") from None
    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError as exc:
        return [{"file": rel, "line": exc.lineno or 0, "code": "SYNTAX",
                 "detail": f"does not parse: {exc.msg}"}]
    module_level_names = set()
    for stmt in tree.body:
        targets = stmt.targets if isinstance(stmt, ast.Assign) else (
            [stmt.target] if isinstance(stmt, ast.AnnAssign) else [])
        for target in targets:
            # Tuple and list targets are unpacked, because an earlier revision collected only
            # `ast.Name` and a review proved the gap by execution: `CACHE, SEEN = {}, []` at module
            # level, then `CACHE[k] = v` and `SEEN.append(k)` inside a function, returned PASS
            # while the single-target spellings of the same two names were refused. That is shared
            # mutable state surviving across calls -- the class MUTABLE_MODULE_STATE exists to
            # refuse -- reachable by an ordinary spelling rather than a contrived one, so it is
            # closed in the collector instead of disclosed in the record.
            module_level_names.update(_assigned_names(target))
        module_level_names.update(_walrus_names(stmt))
    visitor = _Visitor(rel, frozenset(module_level_names))
    visitor.visit(tree)
    for node in tree.body:
        problem = _module_level_problem(node)
        if problem:
            visitor.flag(node, "MODULE_LEVEL_WORK", problem)
    for node, detail in _annotation_string_problems(tree):
        visitor.flag(node, "ANNOTATION_STRING", detail)
    return sorted(visitor.violations, key=lambda v: (v["line"], v["code"], v["detail"]))


def _annotations(node: ast.AST) -> list[ast.expr]:
    """Every annotation expression `node` carries, if it carries any."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        args = node.args
        out = [a.annotation
               for a in (*args.posonlyargs, *args.args, *args.kwonlyargs,
                         *(x for x in (args.vararg, args.kwarg) if x is not None))
               if a.annotation is not None]
        if node.returns is not None:
            out.append(node.returns)
        return out
    if isinstance(node, ast.AnnAssign):
        return [node.annotation]
    return []


def _annotation_string_problems(tree: ast.AST) -> list[tuple[ast.AST, str]]:
    """Refuse every string constant inside an annotation, as a class.

    An independent review proved arbitrary code execution through a string annotation and the tool
    returned PASS: `def _rule() -> "print('...') or int"` with `typing.get_type_hints(_rule)`,
    which `eval`s the annotation text against the function's `__globals__` -- whose
    `__builtins__` is the whole builtins table. There was no forbidden import, no forbidden bare
    name, no forbidden attribute and no dunder, because the payload was never code as far as the
    AST was concerned: `visit_Constant` inspected string constants only for dunder spellings, and
    nothing anywhere parsed an annotation string.

    The rule removes the input rather than chasing the evaluators. `typing.get_type_hints` and
    `functools.singledispatch` are two entry points and there is no reason to believe they are the
    only two, so banning them by name would be another enumeration of the kind that has failed
    here repeatedly. If no annotation contains a string, every annotation's content has already
    been parsed and checked as code by this tool, and an evaluator has nothing unchecked to reach.
    Nested strings are refused too, because `get_type_hints` resolves forward references inside
    generics: `list["print(1) or int"]` is evaluated as surely as the top-level form.

    Deliberately strict, with one known cost: `typing.Literal["x"]` is refused although it is pure
    and `typing` does not evaluate its arguments. A domain slice has `enum` for that, and relaxing
    this rule to admit `Literal` means re-deciding which evaluators resolve which nested strings --
    which is exactly the reasoning that produced the escape. Forward references do not need
    strings either: `from __future__ import annotations` makes every annotation lazy already.
    """
    out: list[tuple[ast.AST, str]] = []
    for node in ast.walk(tree):
        for annotation in _annotations(node):
            for sub in ast.walk(annotation):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    out.append((sub, "a string inside an annotation is text this tool never parses "
                                     "as code, and typing.get_type_hints evaluates it against the "
                                     "enclosing module's globals; write the annotation as an "
                                     "expression, with `from __future__ import annotations` if it "
                                     "is a forward reference"))
    return out


def lane_files(root: Path) -> tuple[list[str], list[dict]]:
    """Enumerate the lane's files, refusing symlinks rather than following or ignoring them.

    `Path.rglob` does not descend into a symlinked directory, so an earlier version silently
    omitted everything beneath one. An independent review proved the consequence: with
    `backend/app/tenancy/domain/ext` a symlink to a directory outside the lane, `ext/evil.py` was
    absent from `files_checked` and never purity-checked, while a lane file imported it as
    `from .ext.evil import do` -- an ordinary intra-lane relative import, lexically inside the
    lane root, so no import rule could object either. The hidden module read the process id and
    the wall clock and the tool still returned PASS.

    The defect was in the enumeration, not in the import rule, so the fix is here: any symlink met
    in the walk is refused -- a symlinked lane root, a symlinked directory inside one, or a
    symlinked file. Following it would take the check outside the lane, and ignoring it leaves an
    unchecked region that lane code can import. Refusing is the only answer that leaves no gap.
    """
    files: list[str] = []
    problems: list[dict] = []

    def refuse(rel: str, code: str, detail: str) -> None:
        problems.append({"file": rel, "line": 0, "code": code, "detail": detail})

    def walk(directory: Path) -> None:
        for candidate in sorted(directory.iterdir()):
            rel = candidate.relative_to(root).as_posix()
            if candidate.is_symlink():
                refuse(rel, "SYMLINK_IN_LANE",
                       "a symlink inside a lane root is refused: following it would take the "
                       "check outside the lane, and ignoring it would leave a region that is "
                       "never purity-checked but that lane code can import")
            elif candidate.name == "__pycache__":
                # Previously skipped unconditionally, and a test asserted the skip. A review
                # proved the consequence: a hash-based .pyc whose flags word is 0b01 is
                # "unchecked", and CPython loads it without validating the source, so the bytecode
                # the interpreter runs need not resemble the .py this tool reads. The planted
                # module kept its advertised API -- a test suite saw nothing wrong -- and wrote a
                # file and read the wall clock. Same defect as the symlinked directory: a region
                # that is never checked but can still be imported.
                refuse(rel, "PYCACHE_IN_LANE",
                       "a __pycache__ directory inside a lane root is refused: an unchecked "
                       "hash-based .pyc is loaded without validating its source, so the "
                       "bytecode that runs need not match the .py this tool reads")
            elif candidate.is_dir():
                walk(candidate)
            elif candidate.is_file():
                files.append(rel)
            else:
                # The triage previously had no else, so a node that was neither directory nor
                # regular file was silently dropped. A FIFO is importable: a reviewer imported one
                # fed by a concurrent writer. Refusing anything irregular closes that too.
                refuse(rel, "IRREGULAR_FILE",
                       "not a regular file or directory; a FIFO or device node can be "
                       "imported and would never be checked")

    for lane in LANE_ROOTS:
        base = root / lane
        if base.is_symlink():
            refuse(lane, "SYMLINK_IN_LANE", "a lane root may not itself be a symlink")
            continue
        if not base.is_dir():
            continue
        walk(base)
    return files, problems


def check(root: Path, lane_effective: bool, basis: str | None = None) -> dict:
    if not root.is_dir():
        raise Malformed(f"root not found: {root}")
    files, violations = lane_files(root)
    if not lane_effective:
        # Before the owner record is published and effective, the lane does not exist. A file under
        # a lane root is then unauthorized code, not code to be checked, and saying so is the
        # honest result -- a PASS here would read as authorization this tool cannot give.
        for rel in files:
            violations.append({"file": rel, "line": 0, "code": "LANE_NOT_EFFECTIVE",
                               "detail": "the local-domain-slice owner record is not published and "
                                         "effective, so no file may exist under a lane root"})
    else:
        for rel in files:
            if rel.endswith(".py"):
                violations.extend(check_file(root, rel))
            else:
                violations.append({"file": rel, "line": 0, "code": "NON_PYTHON_FILE",
                                   "detail": "a lane root holds Python sources only"})
    return {
        "result": "BLOCKED" if violations else "PASS",
        "lane_roots": list(LANE_ROOTS),
        "lane_effective": lane_effective,
        # The leading clause tracks the flag. It used to assert "the owner record is committed"
        # unconditionally, so on every real run so far -- where the record is an untracked draft --
        # the field explaining the basis stated the opposite of the value it explained. A review
        # caught it. The disclaimer half is the valuable half and is unchanged.
        "lane_effective_basis": (
            (basis if basis is not None else
             ("the caller asserted the lane is effective" if lane_effective else
              "the caller asserted the lane is not effective"))
            + "; this tool does NOT verify the record's independent review, its first-publication "
              "owner attestation or its publication, does NOT verify that the three commands sit "
              "in steps that actually run and that a failure of them actually gates -- a disabled "
              "step, an unreachable job, a string literal and a trailing-comment position all "
              "match without running, and a changed trigger, `continue-on-error: true` and a "
              "workflow that is not valid YAML at all match without gating -- and does NOT verify "
              "that any CI run of them was green on an exact SHA"),
        "files_checked": files,
        "violations": violations,
        # This field used to read "a PASS means the file performs no I/O and consumes no clock,
        # randomness, process or database" -- the exact inference the lane record forbids a slice
        # reviewer from drawing, emitted by the tool on every run. The record's §3.4 makes that
        # reviewer the control, so the tool was telling the control the opposite of its instruction.
        # Found by the record's obligation-1 review, which read the committed bytes rather than the
        # prose about them.
        "pass_means": ("no route these rules know of, over the files this walk enumerated: "
                       "evidence that an author did not make one of the mistakes the rules cover, "
                       "NOT evidence that the file performs no I/O, and never evidence of "
                       "correctness, tenant isolation, authentication, authorization, data "
                       "integrity or database integration"),
    }


def _owner_record_effective(root: Path) -> bool:
    """Whether the lane's owner record is in `HEAD`, which is the strongest test available here.

    Three versions of this function, each stricter. The first returned True for any file on disk,
    which an unpublished draft satisfies. The second required the path to be in the git **index**,
    and described that as committed -- it is not: `git add` of a forged record opened the lane while
    this tool asserted in its own output that the record was committed, and staging is the normal
    working state for running the change gate. An independent review demonstrated it. This version
    reads `HEAD`, which is the same standard `_ci_wiring_text` applies to the workflow, so the two
    halves of one sentence are no longer held to opposite standards.

    The revision is spelled `HEAD:./<path>`, which git resolves against the **caller's directory**,
    not against the repository top level. A review proved why the shorter `HEAD:<path>` was wrong:
    it ignored `--root` entirely whenever `--root` was a subdirectory, so an untracked subtree
    holding a lane file read an ancestor repository's commits, returned True, and had the basis
    assert that the record and the workflow were committed for a tree where neither existed. The
    pre-diff spelling did not have that hole, so it was a loosening introduced here rather than an
    old limit carried forward.

    Still weak, and reported as such in every result. The record's own effectiveness rule requires
    independent exact-subject review, a first-publication owner attestation written under admin
    authentication, non-force publication and a successful exact-SHA push CI run. **This tool
    verifies none of those four.** It verifies only that the record is not an uncommitted draft, so
    that the lane cannot be used before the record exists in history.
    """
    try:
        committed = subprocess.run(
            ["git", "-C", str(root), "cat-file", "-e", f"HEAD:./{RECORD_PATH}"],
            capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return committed.returncode == 0


WORKFLOW_PATH = ".github/workflows/veyro-foundation-ci.yml"
# The three commands the owner record's section 5.3 names, spelled as it spells them, so a workflow
# running section 5.3's literal command matches. An earlier revision folded `-B` into the third
# string, which made this tool report a workflow running section 5.3's own command as not containing
# section 5.3's commands. `-B` is required separately, below, and named as a strictening.
REQUIRED_CI_STEPS = (
    "tools/domain_closure/domain_closure.py check",
    "unittest discover -s tools/domain_closure/tests",
    "-m unittest discover -s app/tenancy/domain/tests",
)
# Suppressing bytecode on the lane's own test run is required beyond section 5.3, which does not
# mention it: without it that run writes __pycache__ into the lane and the closure check refuses it
# as PYCACHE_IN_LANE.
# A deliberately narrow allowlist of two spellings, not a survey of correct ones. Reviews proved
# both halves of why: `PYTHONDONTWRITEBYTECODE=0` matched an earlier, shorter entry and does **not**
# suppress, since CPython reads the value as the flag; and ` -Bm ` was unreachable, because the
# required step string is "-m unittest discover ...", which `python -Bm unittest discover` does not
# contain. Correct spellings this refuses -- clustered `-Bm`, the quoted `="1"` and
# `='1'`, and `=2`, `=yes`, `=true`, `=-1`, all of which do suppress -- close the lane rather than
# open it, so the over-refusal is fail-closed, and the list of them is not exhaustive. Of the
# variable's *value* spellings, none that fails to suppress matches: unset,
# empty, `0` and `00` all miss `=1`. That is the scoped claim; it is not a claim about any line, as
# ` -B ` would also match an unrelated `grep -B 2`, and a suppression applied to some other command
# on the same line would match too. The gate it guards is the lane's own test command, and a line
# that carries that command and a suppression spelling is the state this condition is for.
BYTECODE_SUPPRESSIONS = (" -B ", "PYTHONDONTWRITEBYTECODE=1")


def _ci_wiring_text(root: Path) -> str:
    """The **committed** workflow, comment lines dropped. Empty string if it cannot be read.

    Committed, not the working tree, because the sibling condition requires the owner record to be
    tracked for a stated reason -- "so that the lane cannot be used before the record exists in
    history" -- and reading one from history while reading the other from the working tree applies
    opposite standards to the two halves of one sentence. An independent review found the effect
    live: with this file's own wiring edit uncommitted and no CI run of it ever green, the tool
    reported the lane effective. A slice author with a local edit would have had an open lane.

    `HEAD:./<path>` for the same reason `_owner_record_effective` uses it: the revision resolves
    against the caller's directory, so a `--root` that is not the repository top level reads
    nothing and the lane closes.
    """
    try:
        shown = subprocess.run(["git", "-C", str(root), "show", f"HEAD:./{WORKFLOW_PATH}"],
                               capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    if shown.returncode != 0:
        return ""
    text = shown.stdout.decode("utf-8", "replace")
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def _ci_wiring_present(root: Path) -> bool:
    """Whether the committed workflow **text contains** all three section 5.3 commands.

    Read the verb: contains. This is a substring test over the committed file with **line-leading**
    comment lines dropped, and nothing more. Two independent reviews between them demonstrated eight
    states where the three commands are present and none of them gates: in a whole-line comment, in
    steps carrying `if: false`, in a second job carrying `if: false`, inside an `echo` in an
    unrelated step, in a trailing `#` comment on a `run:` line, under a trigger changed away from
    push-to-main, under `continue-on-error: true` on every step, and in a file that is not valid
    YAML at all. Dropping line-leading comments closes **one spelling of the first** and nothing
    else: an earlier revision of this paragraph claimed it closed "in a comment", and a trailing
    `#` comment on a `run:` line still matches. Of the last three, `continue-on-error` runs and
    has its failure ignored, so "steps that actually run" does not describe that failure at all; a
    changed trigger and invalid YAML keep the steps from running, which the reachability half does
    cover. The distinction is why the result string groups them as matching "without gating"
    rather than stretching the running clause over all three. The result string names all of this
    rather than claiming the checks run. `workflow_check.py` independently pins the push-to-main
    and read-only shape, and it is not this tool.

    Establishing that they actually run would need a YAML parser and a reachability judgment, and
    establishing that a run of them was green on an exact SHA would need the network, which this
    tool must not touch. That half of section 5.3 stays a human and CI obligation.
    """
    text = _ci_wiring_text(root)
    if not text or not all(step in text for step in REQUIRED_CI_STEPS):
        return False
    return _lane_test_run_suppresses_bytecode(text)


def _lane_test_run_suppresses_bytecode(text: str) -> bool:
    """Whether the line running the lane's own tests suppresses bytecode writing.

    Checked on that line rather than file-wide, so a `-B` somewhere else does not satisfy it.
    """
    lane_command = REQUIRED_CI_STEPS[2]
    lines = [line for line in text.splitlines() if lane_command in line]
    return bool(lines) and all(
        any(spelling in line for spelling in BYTECODE_SUPPRESSIONS) for line in lines)


def lane_effective(root: Path) -> tuple[bool, str]:
    """`(effective, why)` for the lane, by the two conditions this tool can actually check."""
    record = _owner_record_effective(root)
    wired = _ci_wiring_present(root)
    if record and wired:
        return True, ("the owner record is committed and the committed text of "
                      f"{WORKFLOW_PATH} contains all three section 5.3 commands, and every line "
                      "carrying the lane's own test command also carries a bytecode-suppression "
                      "flag")
    missing = []
    if not record:
        missing.append("the owner record is NOT committed")
    if not wired:
        text = _ci_wiring_text(root)
        if text and all(step in text for step in REQUIRED_CI_STEPS):
            missing.append(f"the committed text of {WORKFLOW_PATH} contains all three section 5.3 "
                           "commands but does not suppress bytecode writing on the lane's own test "
                           "run, which this tool requires beyond section 5.3 because the run would "
                           "otherwise write __pycache__ into the lane")
        else:
            missing.append(f"the committed text of {WORKFLOW_PATH} does not contain all three "
                           "section 5.3 commands")
    return False, (", and ".join(missing)
                   + "; the lane is closed, so any file under a lane root is a violation rather "
                     "than a subject")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Veyro local-domain-slice closure check.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_check = sub.add_parser("check", help="check every file under the lane roots")
    p_check.add_argument("--root", default=".")
    sub.add_parser("explain", help="print the enforced policy")

    args = parser.parse_args(argv)
    try:
        if args.command == "explain":
            out = {"result": "PASS", "command": "explain", "lane_roots": list(LANE_ROOTS),
                   "allowed_imports": sorted(ALLOWED_IMPORTS),
                   "forbidden_imports": FORBIDDEN_IMPORTS,
                   "forbidden_builtins": sorted(FORBIDDEN_BUILTINS),
                   "forbidden_attribute_names": sorted(FORBIDDEN_ATTR_NAMES),
                   "forbidden_module_paths": FORBIDDEN_MODULE_PATHS,
                   "tests_root": TESTS_ROOT,
                   "tests_only_imports": sorted(TESTS_ONLY_IMPORTS),
                   "pass_means": ("no route these rules know of, over the files this walk "
                                  "enumerated: evidence that an author did not make one of the "
                                  "mistakes the rules cover, not evidence that the file performs "
                                  "no I/O, and never evidence of isolation, authentication, "
                                  "authorization, integrity or database integration"),
                   "allowed_dunder_attributes": sorted(ALLOWED_DUNDER_ATTRS),
                   "allowed_dunder_strings": sorted(ALLOWED_DUNDER_STRINGS),
                   "forbidden_dunder_definitions": sorted(FORBIDDEN_DUNDER_DEFS),
                   "dunder_rule": ("any other __dunder__ attribute, string literal or hook "
                                   "definition is refused as a class")}
        else:
            root = Path(args.root)
            effective, why = lane_effective(root)
            out = {"command": "check", **check(root, effective, why)}
    except Malformed as exc:
        print(json.dumps({"result": "MALFORMED", "detail": str(exc)}, indent=1, sort_keys=True))
        return 2
    print(json.dumps(out, indent=1, sort_keys=True))
    return 1 if out["result"] == "BLOCKED" else 0


if __name__ == "__main__":
    sys.exit(main())
