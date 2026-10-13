# R1-F05 `getattr(importlib, ...)` — bounded verification

- Work unit: MOD-001 / GOV-01-R04 gate 2. Runner operation `73d69539-ffac-4eba-991a-258d8b70eafb`, subgoal `R1-F05-GETATTR-IMPORT-BYPASS`, one code checkpoint and one test checkpoint. This record concerns only the `getattr`-receiver portion of original finding R1-F05. The previously verified imported-callable and `builtins.__import__` clauses were preserved, not rewritten.

## Reproduced gap (pre-change)

Against the unmodified source (`91a6318c…`), seven distinct shapes were confirmed silent exit-0 **PASS**: `getattr(importlib, 'import_module')(...)`; `getattr(importlib, '__import__')(...)`; the deferred two-step `_load = getattr(importlib, 'import_module')` / `_load(...)`; `import importlib as il` + `getattr(il, 'import_module')(...)`; the plain `import importlib as il` + `il.import_module(...)` attribute call; `getattr(builtins, '__import__')(...)`; and a non-constant attribute argument `getattr(importlib, _attr)(...)`. The structural cause is that the receiver sits behind a *call*, which neither the `ast.Name` nor the `ast.Attribute` branch of `_is_dynamic_import_call` can see, and that the attribute branch keyed on the literal receiver spelling `importlib` rather than on an actual `import importlib [as ...]` binding. Both benign controls (an unrelated local receiver, and a real-`importlib` non-import attribute) already passed and must keep passing.

## Change

- `_importlib_module_bindings(tree)` added, same shape as the existing `_builtins_module_bindings`: names bound to the stdlib `importlib` module by `import importlib`, `import importlib as <alias>`, or `import importlib.<sub>` (which binds the top-level name). `import importlib.util as <alias>` is deliberately excluded — that alias is the submodule, which carries no `import_module`/`__import__`.
- `_is_importlib_receiver` keeps the literal name `importlib` as a receiver unconditionally, so alias recognition can only widen the ERROR set and the already-verified literal coverage cannot regress.
- `_is_dynamic_import_getattr` flags the `getattr` **retrieval** itself, so the deferred two-step form is caught without dataflow. A non-constant attribute argument on a dynamic-import receiver is a finding (statically unresolvable → fail closed). A shadowed local `getattr` can only over-approximate toward ERROR.
- The `getattr(...)(...)` application is not double-counted: the enclosing call's `func` is a `Call`, which matches no branch, so exactly one violation is reported (asserted directly in the test).
- Violation message and the module docstring's rule-6 paragraph updated to state the widened closed set; `importlib_names` is resolved once per file alongside the two existing binding sets, before the node walk.

## Verification

- All seven bypass shapes now report `MODULE_DEPS_SOURCE_UNINSPECTABLE` at **ERROR, exit 2**; both benign controls still **PASS** with zero violations.
- Three throwaway reversal drills, each run against a copy and each discriminating exactly as intended: neutering the `getattr` clause failed only the new positive test; making the clause receiver-agnostic failed only the new benign-control test; dropping alias recognition failed only the alias cases. The four pre-existing rule-6 dynamic-import tests passed under all three drills, confirming the new tests are not merely restating old coverage. Throwaway copies were deleted, not merged.
- `backend/.venv/bin/python tools/tests/test_validate_architecture_gates.py` → **254/254 PASS** (252 before; +2 new tests). `backend/.venv/bin/ruff check` on both files **PASS**. `python -m py_compile` on both files **PASS**.
- The live `backend/app/modules/` tree contains no `import importlib`, `getattr(importlib, ...)` or `getattr(builtins, ...)` occurrence, so no real-tree source is newly flagged. Gate 2 is still not wired to that tree (no manifest on disk); this was a source grep, not a live gate run.
- SHA-256 after change: source `5d2f545aff4fe3bb51eca62395670e68a3e0c5456c0d5077db6b69b97748e3a7`; tests `512fc6c2da3aa5e342fd368a07cb5e3b32a0f7b0e938dcdc520982b2cf0088d0`. Both files remain untracked in git, as in the prior gate-2 rounds.

## Residuals — **F05 is NOT closed**

- `exec`/`eval`-based import construction is untouched and still a silent PASS; it was explicitly out of this increment's scope and needs its own bounded verification.
- Variable-receiver indirection beyond the `getattr` retrieval itself (e.g. `m = importlib` then `m.import_module(...)`, or passing the module as a function argument) is not covered — no dataflow analysis exists here.
- All three binding sets remain file-wide rather than lexically scoped, so lexical shadowing over-approximates toward ERROR. This is the fail-closed direction but is an over-approximation a reviewer should see stated.
- This is local implementer verification, not an independent review verdict. No R1-F06, no D6, no CTE state-3 wiring, no review dispatch, no scenario promotion, no certification occurred. Combined round-2 assurance for F05 still requires the `exec`-import increment first.
