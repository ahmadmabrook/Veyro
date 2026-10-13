---
doc: M1-C-06-MYPY-SYNTHETIC-QUALIFICATION
module: MOD-001
date: 2026-10-09
type: IMPLEMENTATION evidence (stage-5 synthetic qualification drill + inventory/provenance)
requirement: GOV-01-R04, DC-19
related: CAP-012 (mypy 2.3.1), BUG-057, M1-C-06-TEST-TOOL-SCOPE-DECISION-2026-10-09, CAP-009, CAP-010, CAP-011
operation: d3beb424-457b-432d-9db0-cb6237218773
status: QUALIFIED (draft row) RECORDED — NOT AN APPROVAL
---

# M1-C-06 — CAP-012 mypy 2.3.1 synthetic qualification drill

## 1. What this is and is not

Per `M1-C-06-TEST-TOOL-SCOPE-DECISION-2026-10-09.md` Decision 1, mypy is a separate third-party
executable capability that needs its own exact-scope row and synthetic positive/negative drill. This
record is that drill plus an installed-tree inventory. It is **not** an approval: CAP-012 is
`QUALIFIED — NOT APPROVED`, `approved_by`/`approved_date` blank, `next_review_due` NOT SET,
`lifecycle_status` not ACTIVE, and no independent Opus determination has occurred or been dispatched.

mypy was **not** run against any Veyro source, test, config, directory or import. Every mypy run in this
record used a fresh OS-temp tree and an explicit synthetic config. pytest, Ruff, gitleaks and every network or
remote action were not used (the upstream-provenance gaps in §3 follow directly from that). No code or CI
changed; no scenario is PASSed; MOD-001 exit remains 0/8. The Veyro files that were *read as data* (not
type-checked): `backend/pyproject.toml`, `backend/requirements-dev.lock.txt`, and a `find`/`ls` listing of
`backend/app` (file counts and names only).

BUG-057 is unchanged: historical mypy use stays a disclosed gap, not retroactively authorised. Disclosure of an
existing artifact found during inventory: a repo-root `.mypy_cache/` (`3.13/` last written 2026-10-02, `3.14/`
last written 2026-10-09 09:45 +03 = 06:45 UTC, 34 files, self-ignoring) predates this operation (started
11:37 UTC); it is evidence of earlier unregistered mypy use, was only listed and stat'ed here, and was not
touched, deleted or consumed.

## 2. Installed version, pins and integrity (observed vs. pinned, kept distinct)

| Item | Value | Basis |
|---|---|---|
| Installed (observed) | `mypy 2.3.1 (compiled: yes)`, wheel tag `cp314-cp314-macosx_11_0_arm64`, in `backend/.venv` (Python 3.14.5, macOS arm64) | `python -I -m mypy --version`; `mypy-2.3.1.dist-info/WHEEL` |
| Declared pin | `mypy==2.3.1` | `backend/pyproject.toml` `[project.optional-dependencies].dev` (file SHA-256 `039332c96ab93d82de930d1c84e3351a160829604126868da3a2a8fdfdd40695`) |
| Lock pin | `mypy==2.3.1 --hash=sha256:192abaedf75da1bc0b1cef104927e70ec49c1ef0031cc4825c7ee10a438ed24d` | `backend/requirements-dev.lock.txt` line 14 (file SHA-256 `5b9383fe128cb1d7d8b8442c82fe305988980915140215f4a4f5e3adcbe2d698`) |
| Dependency closure (lock pins, installed in venv) | `ast-serialize 0.11.2` (`1844ed9a…e99fa4`), `librt 0.15.0` (`6c0eb900…522bf8`), `mypy_extensions 1.1.0` (`1be4cccd…f5505`), `pathspec 1.1.1` (`a00ce642…0b189`), `typing_extensions 4.16.0` (`481caa48…c2e8`) | lock lines; mypy `METADATA` `Requires-Dist` (typing_extensions, mypy_extensions, pathspec, librt, ast-serialize; `tomli` is python<3.11 only; `psutil`/`setuptools` are extras, not installed for this scope) |
| Installed-tree integrity | every hashed `RECORD` entry matches its file: mypy 1470 ok/0 mismatch/0 missing (332 unhashed rows); ast_serialize 11/0/0; librt 22/0/0; mypy_extensions 6/0/0; pathspec 37/0/0; typing_extensions 6/0/0 | `python -I` script (`/tmp`, SHA-256 `5bae2505a3cccc848ff6fe6b3ed5d7c60b2f1b1d7d79cb0ca4930844b4a13ba7`) |
| Declared license | `License-Expression: MIT`; `Requires-Python >=3.10`; bundled `mypy/typeshed/LICENSE` | `METADATA` (not compared to upstream) |
| Console entry points | `mypy`, `dmypy`, `mypyc`, `stubgen`, `stubtest` | `entry_points.txt`; scope uses only `python -m mypy` |

**Gaps, stated plainly.**

- The installed files were checked against their *own* `RECORD` only. The lock holds **one** hash per package,
  but mypy, ast-serialize and librt are **platform-specific compiled wheels**; no wheel file was available
  locally (the generator's scratch wheel directory is gone) and network access was out of bounds, so it is
  **unverified** which platform's wheel each lock hash names, and the installed macOS arm64 tree was **not**
  shown to derive from it. A CI install by those hashes on a different platform may therefore fail or pin the
  wrong artifact. This is unresolved here and is a stated dependency of CAP-012.
- No upstream provenance (PyPI JSON, GitHub release/tag, attestation) was fetched, so none is claimed beyond what
  the installed `METADATA` says. Unlike CAP-009/010/011 there is no recorded upstream signature check.
- The pin is not enforced by any CI workflow.

## 3. Boundaries observed

- Interpreter: `backend/.venv/bin/python` (3.14.5), always `python -I -m mypy` (isolated: no `PYTHON*` env, no
  user site, no cwd on `sys.path`).
- Environment per run: cleared dictionary, not inherited — only `PATH=/usr/bin:/bin`, `HOME=<TMP>/home`,
  `TMPDIR=<TMP>/tmpdir`, `NO_COLOR=1`, `LC_ALL`. `MYPYPATH` set only in the one deliberate control (A5).
- Fixtures: written by the driver into `mkdtemp(dir=$TMPDIR)` (`TMPDIR=/Users/ahmadmabrouk/.openclaw/tmp`, the
  process OS temp dir, outside the repo); non-sensitive synthetic text; no credentials, no member data, no Veyro
  import. 39 fixture files hashed before the runs and re-hashed after: none mutated. 4 key fixtures asserted
  non-empty before running. The driver lived in a separate directory (`/tmp/veyro-mypy-runner.75038`).
- No Veyro path was ever an argument, cwd, config or search path. Synthetic config reproduces the two values
  found in Veyro's `[tool.mypy]`: `python_version = "3.13"`, `strict = true` (the table has exactly these two
  keys; read via `tomllib`, nothing executed).
- **The disposable tree was removed** (driver printed `REMOVED`; `$TMPDIR/veyro-mypy-drill.*` does not exist).

## 4. Fixture summary (all synthetic; full per-file SHA-256 list is in the log, `fixture_hashes`)

| Fixture (under `<TMP>/work` unless noted) | Role |
|---|---|
| `pyproject.toml` = `[tool.mypy] python_version="3.13" strict=true` | the governed config (analogue of Veyro's) |
| `app_ok/` (`__init__`, `good.py`, `uses_dep.py` importing installed `typing_extensions`) | positive: 3 source files |
| `app_bad/bad.py` (`x: int = 'not an int'`, `f('s')`) | negative: real type errors |
| `app_untyped/u.py` (`def f(a)`) | proves `strict` is live |
| `app_syntax/s.py` (`def f(:`) | blocking syntax error |
| `app_vacuous/` (empty `__init__.py` only), `app_empty/` (empty dir) | vacuous/empty selection |
| `app_ignore/i.py` (`x: int = 'wrong'  # type: ignore`) | suppression limit |
| `mypy.ini` (cwd, `ignore_errors = True`), `<TMP>/home/.mypy.ini` (same) | DECOY ambient configs |
| `app_importoutside/`, `<TMP>/outside/outside_mod.py` | import reachable only via `MYPYPATH`/`mypy_path` |
| `app_importsibling/`, `cwdmod.py` (sibling of package root) | package-root-parent resolution |
| `<TMP>/outside/outside_pkg/o.py` (error), `app_link` -> symlink to it | out-of-root target / symlink |
| `<TMP>/plugins/decoy_plugin.py` (writes `PLUGIN_LOADED` marker on import), `cfg_plugin.toml` | plugin boundary |
| `cfg_mypypath.toml`, `cfg_ignore.toml`, `cfg_files.toml`, `cfg_nonstrict.toml` | config-key controls |

## 5. Commands and results

Governed form `G` (every governed run): `python -I -m mypy --config-file pyproject.toml --cache-dir=/dev/null --no-color-output <target>`,
cwd `<TMP>/work`, cleared env. Controls deliberately relax exactly one knob and exist to prove the corresponding
"NO" is not vacuous. **Pass 2: 36/36 expected outcomes; pass 1: 34/36** — both failures were *driver* defects, not tool
behaviour (F4b: my regex expected `Can't find module` but mypy says `Cannot find module`, rc 2 was correct; C1: I
copied the fixture package into the wrong layout so the cache-control run hit "Cannot read file", rc 2, though it
still wrote `.mypy_cache`). Both were fixed in `drill.py` and the whole drill re-run from a fresh tree; pass 1's
log is kept for transparency.

| Run | Invocation delta | Expected | Observed | Result |
|---|---|---|---|---|
| V | `--version` | `mypy 2.3.1` | rc 0, `mypy 2.3.1 (compiled: yes)` | PASS |
| P1 positive dir | `G app_ok` | rc 0 | rc 0, `Success: no issues found in 3 source files` | PASS |
| P2 positive pkg | `G -p app_ok` | rc 0 | rc 0, 3 source files | PASS |
| N1 real errors | `G app_bad` | rc 1 + report | rc 1, `Incompatible types in assignment` and `Argument 1 to "f"`, `Found 2 errors in 1 file` | PASS |
| N2 strict live | `G app_untyped` | rc 1 | rc 1, `Function is missing a type annotation` | PASS |
| N2c control | non-strict config | rc 0 | rc 0 (so N2 is caused by `strict`) | PASS |
| N3 syntax error | `G app_syntax` | rc 2 | rc 2, `Invalid syntax`, `errors prevented further checking` | PASS |
| F1 no target | `G` only | rc 2 | rc 2, `Missing target module, package, files, or command` | PASS |
| F2 empty dir | `G app_empty` | rc 2 | rc 2, `There are no .py[i] files in directory 'app_empty'` | PASS |
| F3 missing path | `G no_such_dir` | rc 2 | rc 2, `Cannot read file 'no_such_dir'` | PASS |
| F4 / F4b missing pkg / module | `-p no_such_pkg` / `-m no_such_mod` | rc 2 | rc 2, `Can't find package` / `Cannot find module` | PASS |
| F5 missing config | `--config-file nope.toml` | usage error | rc 2, `Cannot find config file 'nope.toml'` | PASS |
| F6 **vacuous target** | `G app_vacuous` | (limit) | **rc 0**, `no issues found in 1 source file` | PASS (limit confirmed) |
| F7 control: `files=` in config | `cfg_files.toml`, no target | (limit) | rc 0, 3 files checked — config can supply the selection | PASS (limit confirmed) |
| A1 control | no `--config-file`, decoy `mypy.ini` in cwd | decoy applies, error hidden | rc 0 | PASS |
| A2 governed | `G app_bad`, decoy present | rc 1 | rc 1 (decoy ignored) | PASS |
| A3 control | no config flag, `~/.mypy.ini` decoy | decoy applies | rc 0 | PASS |
| A4 governed | explicit config, user decoy present | rc 1 | rc 1 | PASS |
| A5 control | `MYPYPATH=<TMP>/outside` | outside module resolves | rc 0 | PASS |
| A6 governed | clean env | unresolved | rc 1, `import-not-found` for `outside_mod` | PASS |
| A7 control | config `mypy_path` | resolves | rc 0 | PASS |
| A8 control | config `[[overrides]] ignore_errors` | error hidden | rc 0 | PASS |
| A9 | `G app_importsibling` | (limit) | rc 0 — a module in the *package root's parent* resolves | PASS (limit confirmed) |
| PL1 control / PL2 governed / PL marker | `cfg_plugin.toml` vs `G` | plugin executes only in control | marker `True` in control, `False` governed, both rc 0 | PASS |
| E1 / E2 / E3 | absolute outside path / `../outside/outside_pkg` / symlink `app_link` | (limit) | all honoured, rc 1 with the outside file's error | PASS (limit confirmed) |
| E3b | `realpath(app_link)` | leaves root | `<TMP>/outside/outside_pkg` | PASS |
| S1 | `G app_ignore` | (limit) | **rc 0** — inline `# type: ignore` silences a real error | PASS (limit confirmed) |
| C1 control + marker | no `--cache-dir`, cwd with `gov.toml` | `.mypy_cache` created | rc 0, cache dir created | PASS |
| C2 governed side effects | all governed runs | none | no `.mypy_cache` outside the control tree; nothing written under `<TMP>/home` | PASS |
| FX | fixtures re-hashed | unmutated | 39 files, `mutated=[]`, pre-tree SHA-256 `44439f63021d71c3cd9ccde8348bc95db18d4b21a53314c5797920c34f3bda3c` | PASS |

Artifacts (kept in `/tmp/veyro-mypy-runner.75038`, outside the repo; contain only sanitised synthetic output):
`drill.py` SHA-256 `829a1075a18a5562d9768f4600c3b1760660d5bf61551f68b9754d1d26bfff3b`;
final log `drill-log.json` `40b1aa21f69297694d3dc5a7af4174d2c7b1196ca52e119a2fb6b6cb9c1aa70f`;
pass-1 log `drill-log-pass1.json` `6d1ab328263283a32da644a72f92342b32cc3a8bb2f79e60ca2096d83a4fd04a`.

## 6. Proposed exact future GOV-01-R04 type-check scope (INTENDED; nothing may run under it until APPROVED)

mypy 2.3.1, static analysis of **`backend/app` only**, via the project venv interpreter:
`env -i HOME=<confined> TMPDIR=<confined> PATH=/usr/bin:/bin NO_COLOR=1 backend/.venv/bin/python -I -m mypy
--config-file pyproject.toml --cache-dir=/dev/null --no-color-output app` with cwd = `backend`. Wrapper rules the
drill shows are *necessary* (each tied to a control or limit above):

1. **Config is only `backend/pyproject.toml` `[tool.mypy]`, and its key set must equal exactly
   `{python_version, strict}`.** Any additional key — `plugins` (executes code, PL1), `mypy_path` (A7), `files`
   (F7), `exclude`, `follow_imports`, `ignore_errors`, `[[tool.mypy.overrides]]` (A8) — fails the wrapper. Never
   rely on ambient config: the explicit `--config-file` is what defeats A1/A3.
2. **Target is one explicit path the wrapper has `realpath`-checked to equal `backend/app`** (E1–E3: mypy honours
   outside-root, `../` and symlinked targets). No target, empty dir, missing path/package and config-only selection
   are errors (F1–F5, F7).
3. **Exit code must be 0 *and* the wrapper must parse `Success: no issues found in N source files` with N equal to the
   expected count of `.py` files under `backend/app`** (F6: a vacuous target exits 0). Any other rc (1 errors, 2
   blocking/usage) fails.
4. **Cleared environment** (no `MYPYPATH`, no `MYPY_*`, confined `HOME`) and `--cache-dir=/dev/null` (A5/A6, C1/C2).
5. **Inline `# type: ignore` is not detectable from the exit code** (S1); `strict` enables `warn_unused_ignores`
   only for *unused* ignores. A separate reviewed control (e.g. count/forbid) is a dependency if the gate is to
   mean "no suppressed errors".
6. Exclusions (each requires a scope change + re-evaluation): `backend/tests`, `backend/migrations`, `tools/**`,
   anything outside `backend/app`; `dmypy`, `mypyc`, `stubgen`, `stubtest`, plugins, `--install-types`, network.

Inventory only (not read for content): `backend/app` has 23 `.py` files, 15 of them `__init__.py`, including a
`backend/app/modules/conftest.py`; this nested layout was **not** mirrored by a synthetic analogue beyond a flat
package, so namespace-package/`--explicit-package-bases` behaviour on the real layout is unevidenced.

## 7. Tool limitations (disclosed; not cured by this drill)

- **Not executed on Veyro code.** mypy is *static* (it does not import or run the code it checks, other than plugins),
  so its blast radius is smaller than pytest's, but it still parses attacker-influenced source with its compiled
  parser. This drill proves nothing about behaviour on the real `backend/app` layout, its third-party imports
  (e.g. `psycopg`), its conftest, or any type result there.
- **Suppression:** inline `# type: ignore`, per-module config and `ignore_errors` make a green result silent (S1, A8).
- **Vacuous pass:** a package of empty files exits 0 (F6).
- **Selection:** config-supplied `files=` selects targets with no CLI argument (F7); explicit outside targets run (E1–E3);
  modules in the package root's parent resolve implicitly (A9).
- **Plugins** execute arbitrary Python at config load (PL1); safe only because the key set is pinned.
- **Environment mismatch:** drilled on macOS arm64 / Python 3.14.5 with `python_version = "3.13"`; `requires-python`
  is `>=3.13` and no CI interpreter exists. Compiled-wheel platform pin problem in §2 is unresolved.
- **Provenance gaps:** no upstream signature/attestation/tag data gathered (network out of bounds); lock hash not tied to
  a platform artifact; installed tree verified against its own `RECORD` only; pin not enforced in CI.
- Small fixtures; no stubs packages, no `--install-types`, no daemon, no incremental cache correctness.
- A repo-root `.mypy_cache/` from earlier unregistered use exists (§1); BUG-057 stays OPEN.

## 8. Effect and determination

Stage-5 mechanical positive/negative evidence for mypy 2.3.1 **passed** for the hardened, synthetic-only invocation
above (36/36 in the final pass), with the limits stated. The scope could be stated exactly and qualified on a
synthetic analogue, so CAP-012 is registered as an exact-scope draft at **QUALIFIED — NOT APPROVED**; the
unresolved provenance/pin and real-layout gaps are explicit dependencies, not hidden. Stage 4 (independent Opus
`veyro-security-reviewer` determination, separate verdict from CAP-009/010/011) has not occurred; this record adds
no review entitlement and dispatches none. Per Decision 2 condition 1, CAP-012 now has drill evidence but is
excluded from any batch until separately authorised. `validate_capabilities.py` and
`tools/validate_capability_manifest.py` are expected to fail closed on CAP-012 (see the registry-update notes for
exact counts).

No real-tree, CI, GOV-01-R04 gate or scenario reliance on CAP-012 is authorised. No scenario is PASSed; MOD-001
exit remains 0/8.
