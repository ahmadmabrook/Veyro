# M1-C-06 — CAP-012 synthetic nested-layout mypy import drill (§10 two-variant probe)

Date: 2026-10-09 · Operation `5c793dcc-3c33-48d8-b09c-ff6d238d695e` · Sonnet (`claude-sonnet-5-5`), IMPLEMENTATION role.

**Scope and status.** CAP-012 qualification-drill work on **synthetic fixtures only**, as
permitted by `CAPABILITY_POLICY.md` for unapproved capabilities. CAP-012 remains
**QUALIFIED — NOT APPROVED**. No Veyro file was copied, read as a mypy target, or
type-checked. No install, download, lock/CI/pyproject/registry/plan/scenario edit, no
review dispatch, no scenario or gate PASS. This proves nothing about real Veyro source,
Linux, or CI.

Governing question: `M1-C-06-TYPECHECK-TARGET-CLOSURE-ARCHITECTURE-2026-10-09.md` §10.

## 1. Artifact

`tools/tests/test_mypy_nested_import_qualification.py`
sha256 `674a3decb0fd4fe46194680969dff18fa410d6c9351852cc4ff956dcfc5ecdc5`.

It builds the tree under `tempfile.mkdtemp` (OS temp, outside the repo; `realpath`'d),
runs mypy, and removes the tree in a `finally`. Run as a script it prints the
observations as JSON; under pytest it makes 9 checks (9 passed), including repo-root
`.mypy_cache` snapshot unchanged and no leftover temp trees.

Synthetic layout (22 `.py` files under `app/`):
`app/__init__.py`, `app/modules/__init__.py`, `app/modules/conftest.py`
(`from tests.harness.mod import harness_value`), `app/modules/_shared/__init__.py`,
six packages `mod_a..mod_f` each with `__init__.py`, `tests/__init__.py`,
`tests/test_scaffold.py`; sibling `<temp>/tests/harness/__init__.py` and
`<temp>/tests/harness/mod.py` whose `harness_value() -> int` returns a `str`
(deliberate). `<temp>/pyproject.toml` contains only `python_version = "3.13"` and
`strict = true`. The two variants differ **only** in `<temp>/tests/__init__.py`
(A present, B absent); `tests/harness/__init__.py` exists in both.

## 2. Command shape (both variants)

cwd `<temp>/tree`; interpreter `backend/.venv/bin/python` (Python 3.14.5, mypy 2.3.1
compiled, darwin arm64);

```
python -I -m mypy --config-file pyproject.toml --cache-dir=/dev/null --no-color-output app
```

Environment cleared to `HOME=<temp>/home`, `TMPDIR=<temp>/tmp`, `PATH=/usr/bin:/bin`;
no `MYPYPATH`, no `MYPY_*`; no cache written (`/dev/null`).

## 3. Observed results (path-normalised; produced by the script above)

| | A: `tests/__init__.py` present | B: `tests/__init__.py` absent |
|---|---|---|
| rc | 1 | 1 |
| files under `app/` | 22 | 22 |
| reported N | 22 (`checked 22 source files`) | 22 (`checked 22 source files`) |
| harness defect surfaced as | followed-import type error | followed-import type error |
| unresolved-import errors | none | none |

Diagnostic, identical in both variants:

```
tests/harness/mod.py:2: error: Incompatible return value type (got "str", expected "int")  [return-value]
Found 1 error in 1 file (checked 22 source files)
```

Observations stated precisely, without inference:
- The reported N equals the number of `.py` files passed under the `app` target (22);
  the followed-import file `tests/harness/mod.py` (and `tests/harness/__init__.py`) did
  **not** add to N in this run. That is an observation of this mypy build, not an assumed rule.
- Only one error was reported; there were no import-not-found errors for `tests.harness.mod`
  in either variant, and no "found twice under different module names" error despite
  six nested `tests` packages beside a top-level `tests`.
- Both invocations executed (rc 1 is the deliberate type error; rc 2 would have meant mypy
  could not run). No invocation failed to run.

## 4. Branch conclusion against §10

**"Resolves (either variant)" branch holds on this synthetic fixture:** under the exact
CAP-012 CLI the sibling `tests.harness.*` module was resolved and followed via the
implicit source root (cwd) in both A and B, and its type defect surfaces as an ordinary
followed-import type error, not an unresolved import. Neither `mypy_path`/`MYPYPATH`,
suppression nor harness relocation was needed in the synthetic drill. Per §10 the
consequence on this branch is that harness type errors would be ordinary Veyro-code
failures routed by slice; the actual N (22 of 22 direct files) is recorded above and
was not assumed.

This is a branch indication for a synthetic analogue only, not a decision, approval, or
change of any gate state.

## 5. Remaining unknowns (not covered by this drill)

- The real `backend/app` tree (23 files), real `backend/tests/harness` layout, and whether
  real `tests.harness.postgres` / `tenant_context` resolve identically: untested; no mypy
  has run on any Veyro path.
- Third-party imports of the real closure (`psycopg`, `pytest`) and whether they resolve
  or error under strict mode: untested here (synthetic fixtures import none).
- Linux cp313 / CI interpreter behaviour: drilled only on darwin arm64, Python 3.14.5 with
  `python_version = "3.13"`; Linux/locked-wheel behaviour unverified.
- Real strict-mode error classes in `_shared/tenant_context.py` and the 23-file tree: unknown.
- Synthetic `tests.harness` has an `__init__.py` in both variants; a harness without it
  was not drilled (out of the two-variant scope).
- A pre-existing repo-root `.mypy_cache/` (disclosed unregistered earlier use) exists; the
  drill did not modify it (snapshot test), but this does not cure that disclosed gap.
- CAP-012 independent security determination still pending; no reliance created.
