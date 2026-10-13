---
doc: CAP-012_QUALIFICATION_RECORD
capability: CAP-012 (mypy 2.3.1)
status: QUALIFIED — NOT APPROVED
recorded: 2026-10-13
operation: M1C-R04-CAP012-QUALIFICATION-RECORD-20261013
location_authority: OWN-008 / ADR-009 (approved `knowledge/05-QA/capability-evidence/` record; no MOD-001 `evidence/` tree)
---

# CAP-012 (mypy 2.3.1) — current qualification record

**This record approves nothing.** It supplies the current durable positive/negative evidence the
fresh Opus determination (`46e0e47b-351c-4464-ab1d-ecc7942c0cb9`, BLOCKED B1/B2/B4/B5/B6) found
missing. CAP-012 stays `QUALIFIED — NOT APPROVED`; `approved_by` and `next_review_due` are unset
and are assigned only by a fresh independent determination. No Veyro source was type-checked. Not a
GOV-01-R04 type-check gate, not MOD-001 credit. It supersedes, for current purposes, the deleted
`M1-C-06-MYPY-SYNTHETIC-QUALIFICATION-2026-10-09` report (owner-deleted; it has no current credit).

## 1. Artifact set and provenance (reproduced 2026-10-13)

Two locks, two platforms, one `mypy==2.3.1` release. Both are 13/14-line hash locks of **real
PyPI wheels**; the earlier registry claim of "one lock hash per compiled package, platform
unverified" is closed (see §6).

| Lock (SHA-256 of the file) | Platform / interpreter | Entries |
| --- | --- | --- |
| `backend/requirements-typecheck-linux-x86_64-cp313.lock.txt` `5e7596d408190a6103ffe1e3988f1c88ea33a34306302cc7de6f0570340e95de` | Linux x86_64, CPython 3.13 — the lock the CI drill installs | 13 |
| `backend/requirements-dev.lock.txt` `5b9383fe128cb1d7d8b8442c82fe305988980915140215f4a4f5e3adcbe2d698` | macOS arm64, CPython 3.14 — local venv | 14 (13 + `ruff`) |

Compiled wheels (the three mypy-closure packages with platform-specific bytes, plus psycopg-binary):

| Package | Linux cp313 wheel SHA-256 | macOS cp314 wheel SHA-256 |
| --- | --- | --- |
| mypy 2.3.1 | `1c80fbc405ed8020f5ff3802dc18cf060197bcdd3fbdd6a26ef2fd34dfdd5226` (`cp313-…-manylinux2014_x86_64…manylinux_2_28_x86_64`) | `192abaedf75da1bc0b1cef104927e70ec49c1ef0031cc4825c7ee10a438ed24d` |
| ast-serialize 0.11.2 | `a7004ba572f09be34342ccb98dcd4bad5707d3d81adc8cb4c3f685d2a2c51bbc` (`cp39-abi3-manylinux_2_17_x86_64`) | `1844ed9a487fb3de7325c52ddb33f2918b66b65cd54d3f8d83d23785ffe99fa4` |
| librt 0.15.0 | `234d8d394721fa0d786af15ebf1f3fb7f3ed82fd1cd0cde45c2f247b5d4281d2` (`cp313-…-manylinux2014_x86_64…`) | `6c0eb900c0e91f4aebe680845242e614f1864edfd44106380d0752ac29522bf8` |

Pure-Python closure (`py3-none-any`, identical on both platforms): mypy_extensions 1.1.0
`1be4cccd…f5505`, pathspec 1.1.1 `a00ce642…0b189`, typing_extensions 4.16.0 `481caa48…c2e8`.
The Linux lock additionally carries pytest 9.1.1, pluggy 1.6.0, iniconfig **2.3.1**, packaging 26.3,
pygments 2.21.0, psycopg 3.3.6, psycopg-binary 3.3.6 (the macOS lock pins iniconfig **2.3.0** — a
known, non-behaviour-affecting divergence recorded under CAP-011). The full Linux wheel list with
filenames is `backend/requirements-typecheck-linux-x86_64-cp313.wheels.sha256`
(`78177a9b5e86bd72e31a710b4d692a069b2979797f0aaf610d4e7d8b68ec5c4b`).

No upstream signature/attestation verification was performed for any wheel; provenance here means
"PyPI-served bytes equal the lock hash", not "origin attested".

## 2. Local reproducible checks (this operation; disposable dir `mktemp -d /tmp/cap012-qual.*`, host macOS arm64, CPython 3.14.5)

Network use: read-only fetches from `pypi.org` into the disposable directory; no spend, no
credential, no Veyro file executed. Commands run from the repository root with `backend/.venv/bin/python`
(`PIP_CONFIG_FILE=/dev/null`):

| # | Check | Command (abridged) | Outcome |
| --- | --- | --- | --- |
| P1 | Linux lock byte-provenance | `pip download --require-hashes --only-binary=:all: --no-deps --python-version 3.13 --implementation cp --abi cp313 --abi abi3 --abi none --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 -r <linux lock>` then `tools/generate_requirements_lock.py check <dir> <linux lock>` | downloaded 13/13 under hash enforcement; `check` **PASS — 13 packages**, every version and SHA-256 exact, no extras |
| P2 | macOS lock byte-provenance | `pip download --require-hashes --only-binary=:all: --no-deps -r backend/requirements-dev.lock.txt` then `check` | downloaded 14/14; `check` **PASS — 14 packages** |
| P3 | Installed macOS tree derives from the pinned wheel | compare each downloaded wheel's `RECORD` hashes with `backend/.venv` site-packages | mypy 1463 match / 0 mismatch / 0 missing; librt 20/0/0; ast_serialize 9/0/0 (closes the earlier "installed tree not shown to derive from the lock" gap for these three; this is the pinned **wheel**, installed locally, not proof the installer used it) |
| N1 | Tampered digest refused | same download as P1 with the first lock digest replaced by 64 zeros (driver asserts the file differs) | pip **rc=1**, `THESE PACKAGES DO NOT MATCH THE HASHES`, no `ast_serialize` wheel written |
| N2 | macOS digest on Linux target refused | `mypy==2.3.1 --hash=sha256:192abaed…` fetched for cp313 manylinux | pip **rc=1**, hash-mismatch diagnostic |
| W | Wrapper synthetic suite | `backend/.venv/bin/python -B tools/tests/test_run_scoped_mypy.py` | **35 tests OK** (real mypy against disposable synthetic trees only) |
| D | CI-drill workflow static/behaviour tests | `… -B tools/tests/test_typecheck_qualification_drill_workflow.py` | **16 tests OK** |
| C | CAP-011 dependency tests | `… -B tools/tests/test_run_scoped_pytest.py` | **21 tests OK** (working tree carries uncommitted edits to this test file; see §7) |

Driver defect disclosed: a first N1 attempt used BSD `sed` with a GNU-only address, produced an
unchanged file and "succeeded" at downloading. It was discarded as an invalid control; N1 above is the
re-run with an asserted difference and is the only N1 credited.

## 3. Live Linux cp313 synthetic CI execution (exact identities)

| Item | Value |
| --- | --- |
| Draft PR | [#6](https://github.com/ahmadmabrook/Veyro/pull/6), base `main`, branch `cap012-wrapper-ci-20261013`, **OPEN, draft, unmerged** (re-read 2026-10-13) |
| PR head | `cd436dff05e1c6ae45562f3c8777e2c3ef7f1925` |
| PR file set (7) | `.github/workflows/typecheck-qualification-drill.yml`, `backend/requirements-typecheck-linux-x86_64-cp313.lock.txt`, `tools/assert_ci_python313.py`, `tools/run_scoped_mypy.py`, `tools/run_scoped_pytest.py`, `tools/tests/test_run_scoped_mypy.py`, `tools/tests/test_typecheck_qualification_drill_workflow.py` |
| Run / job | GitHub Actions run `38466202028`, job `115533512478` (`typecheck-qualification-drill`, `ubuntu-24.04`), event `pull_request`, created 2026-10-13T20:52:02Z, conclusion **success** |
| Job log | `gh run view 38466202028 --job 115533512478 --log` → 644 lines, SHA-256 `9054dfdd32be14689c40c064a93a7dba8654b3fe2e76e23eb03d6a488669ccf1` (**re-downloaded and re-hashed this operation; equals the previously indexed value**). `gh run view <run> --log` without `--job` returned HTTP 502 from the jobs API on this attempt (transient); use the `--job` form. |
| Interpreter | `/opt/hostedtoolcache/Python/3.13.16/x64/bin/python3.13`; `version_is_3_13: PASS (3, 13)`, `platform_is_linux_x86_64: PASS 'linux-x86_64'` |
| Install | hash-enforced `pip install --require-hashes --only-binary=:all: --no-deps` of the 13-entry Linux lock; `pip list` shows exactly those 13 plus pip 26.2.1 |
| Lock hash in CI | `5e7596d4…e95de` (equals §1) |

**File bytes at PR head equal the working tree** (computed via `git show cd436dff…:<path>`; the earlier
B3 "wrapper absent from CI head" finding is thus closed for this head):

| File | SHA-256 |
| --- | --- |
| `tools/run_scoped_mypy.py` | `338b70e01613f10c35676ee8060c7c8b0a986f5a681556a5d55cc40b65a95a20` (also printed by the CI log) |
| `tools/run_scoped_pytest.py` (CAP-011 dependency) | `626210e6f5c7385e7a4e7b1a07bfcf784494eb2fd014616f745da23f0abb88cb` (also printed by the CI log) |
| `tools/tests/test_run_scoped_mypy.py` | `b6cee2e98aca6598440a62fe504ff2d0ff0b660db07b8e09e1ca35a16c5db933` |
| `.github/workflows/typecheck-qualification-drill.yml` | `41fd95fd0b115db420e3cca00514b899e47cf30858289aedbfb34612377dafde` |
| `tools/tests/test_typecheck_qualification_drill_workflow.py` | `00475a7a38dda8cbcbbae9c63d02859f65dbdd83b5848a239e54bf4ce5d2dd70` |
| `tools/assert_ci_python313.py` | `ea51c067d5d75ff2ba1bb7602e37a0a5c88f9908a18c40d957d65b825a4a3d9c` |

What the run proved (all on job-created synthetic fixtures under `RUNNER_TEMP`; the real
`backend/app` is never a mypy target; only two wrapper files are copied into disposable trees):

- Positive: mypy against a 2-file synthetic package, rc 0, exact line `Success: no issues found in 2 source files`.
- Negative 1: macOS mypy digest vs the Linux lock → install refused, mypy not importable.
- Negative 2: non-3.13 interpreter (3.12 observed) denied with `version_is_3_13: FAIL`.
- Wrapper boundary (the **actual** `run_scoped_mypy.py`, pinned cp313 venv): positive rc 0; control `c5-cache-preexisting` rc 0; seven fail-closed negatives each rc 2 with its targeted diagnostic — `n1-symlink`, `n2-config-key`, `n3-mypypath`, `n4-cache-created`, `n5-cache-mutated`, `n6-count-mismatch`, `n7-vacuous`. Final line: `wrapper boundary proof observed: 1 positive, 1 control, 7 fail-closed negatives`.

Prior related runs (context only, not repeated here): PR #4 head `01ea3e8b382acbdd036ff5e60cd829831a27e372` run `38461696023`
(success, log `cd8b6eee33ffde792afc607e37057c5787618ed6de250ab7f20708d3630ab3d9`); PR #5 head `87a34a300578d82a7941a77c43f14a216ec3453e` run `38462384172` (**intentionally red**,
log `b47bd430d4fce16cc4486aef68b7564f878afa947a95d56c0b89ccd644a24815`, must not merge). Neither PR contained the wrapper.

## 4. Platform coverage — live vs local (B6)

| Evidence | Platform | Interpreter | Kind |
| --- | --- | --- | --- |
| §3 CI run | Linux x86_64 (ubuntu-24.04) | CPython 3.13.16 | **Live execution** of mypy + the wrapper, synthetic fixtures |
| §2 W/D/C suites, P1–P3, N1–N2 | macOS arm64 (Darwin) | CPython 3.14.5 | Local execution of the wrapper tests and **artifact inspection** (wheels, `RECORD`, hashes) — not Linux execution |

Declared scope uses `python_version = "3.13"` for mypy semantics on both. The local venv is 3.14.5, so
the wrapper's `backend/.venv` interpreter on a developer machine is a different build
(`cp314`, macOS wheel) from the one CI proved (`cp313`, Linux wheel). **Neither platform has run mypy
against the real `backend/app`.** Local macOS cp314 wrapper behaviour is evidenced only by the
synthetic unit suite; the CI wrapper proof is Linux cp313 only.

## 5. Dependency on CAP-011 (B5)

`tools/run_scoped_mypy.py` line 80 does `from run_scoped_pytest import Denied, _canonical`. CAP-012's
scoped runner therefore executes CAP-011's wrapper code (symlink-refusing path canonicaliser and the
`Denied` exception). `contracts/engineering/module-capabilities.yaml` now declares
`CAP-012 depends_on CAP-011` in `capability_dependency_ids` (the schema-supported edge form that
`tools/validate_capability_manifest.py` parses; no cycle). CAP-011 is `APPROVED (BOUNDED) — LOCAL
wrapper scope only; CI NOT APPROVED` and its approval is for the pytest invocation shape, **not** for
this reuse. Whether CAP-012's reuse of that module is within CAP-011's bounded scope is a question for
the independent determination; it is not resolved here. Any change to `run_scoped_pytest.py`
(currently `626210e6…abb88cb`) changes CAP-012's enforcement behaviour.

## 6. Closure map for the BLOCKED findings

| Finding | Status after this record |
| --- | --- |
| B1 evidence points at deleted files | Registry evidence cell re-pointed to this record + current live files (the deleted paths are named only as historical, no credit). |
| B2 qualification predates wrapper / Linux artifact / provenance | §1–§3: wrapper, Linux lock, wheel provenance (P1/P2/N1/N2), live Linux run. |
| B3 wrapper absent from CI head | Closed in prior unit; re-verified here (§3 byte table). |
| B4 stale provenance / 13-package set / evidence path | Registry install-set, provenance and evidence cells corrected to observed bytes; "unresolved platform wheel" claim removed. |
| B5 undeclared CAP-011 dependency | Declared in the canonical manifest (§5). Scope-fit question left to the reviewer. |
| B6 Linux cp313 vs macOS cp314 | Distinguished explicitly (§4); **not eliminated** — the gap is documented, not closed. |

## 7. Remaining gaps and checks (none closed here)

1. No fresh independent Opus determination exists after these corrections; `approved_by`, approval date and `next_review_due` are unset by design. The manifest validator still fails with exactly the three CAP-012 approval errors.
2. No mypy run on any Veyro source (`backend/app` or otherwise) on any platform; the wrapper's real-tree behaviour (nested layout, the repository's actual `# type: ignore` / `# mypy:` / `no_type_check` occurrences, real file count) is unexercised.
3. CI evidence is a `pull_request` run on an **unmerged draft** PR head. The workflow is not on `main`, not a required status check, and not a GOV-01-R04 non-bypassable gate.
4. macOS cp314 wrapper behaviour is covered by the synthetic unit suite only; no live macOS or cp314 run of the CI drill exists, and no Linux run of the real macOS-installed tree.
5. The CI proof runs the wrapper beside a venv reached through a symlink (`backend/.venv`); the wrapper's interpreter probe is the only check that this is the pinned venv. Wheel `RECORD` comparison (P3) was run on macOS only.
6. Upstream signatures/attestations unverified; Linux CI wheels are hash-pinned to PyPI-served bytes only. psycopg/psycopg-binary are in the lock but unused by the drill.
7. `tools/tests/test_run_scoped_pytest.py` has uncommitted working-tree edits (21 tests OK locally); CAP-012's CI proof used the committed `run_scoped_pytest.py` bytes at `626210e6…`, which are unchanged in the working tree.
8. `knowledge/05-QA/capability-evidence/INDEX.md` is stale for CAP-009–CAP-012 and was deliberately not edited in this bounded unit.
9. mypy cache, plugin, `--install-types` and network behaviour remain "no flag passed / no config that enables it", not sandboxed. `cast`/`Any` soft-hiding is not policed.
10. BUG-057 (pre-existing unregistered mypy use, repo-root `.mypy_cache/`) is unaffected.

## 8. 2026-10-14 self-contained candidate and macOS cp314 matrix (supersedes §5 dependency and §7.4 local-execution gap only)

After independent Opus round 2 returned **BLOCKED** (session `f67eab06-bd75-4d84-844b-7c98fd1745f3`, transcript SHA-256 `386d5f6465e15e9944ee2fde7a6097fc6f890351e2ce428eba8c5c39ffbcb2c`), Sonnet operation `M1C-R04-CAP012-DECOUPLE-MACOS-20261014` made `tools/run_scoped_mypy.py` self-contained: it now owns `Denied` and `_canonical` and imports no CAP-011 symbol. The canonical manifest dependency edge was removed only after the import and tests changed. The current wrapper SHA-256 is `2970a9ad0434db791cdbef3532c6acbbe661fedbbcfe23c54323941d5546388d`; focused test SHA-256 `a7ae8db3134ba5af8695ea1a367f9eddec497c08a25fe7e600b6e313f0175c88`; revised synthetic workflow SHA-256 `d004cce28ef7a8c1ff8c77b228dc8e6c05682c93a4bc830f4476c4df55fbf793`. N1/N2/N3 stale claims were corrected in those files and the registry. These changed bytes have **not yet run in Linux CI**; PR #6 and §3 remain proof of the earlier CAP-011-dependent version, not this candidate.

The full local macOS arm64 CPython 3.14 matrix output and its reproducible driver are retained in [MACOS_CP314_MATRIX_2026-10-14.txt](MACOS_CP314_MATRIX_2026-10-14.txt), SHA-256 `2bb0ab1d812dba925c684800933521a7b7059385dd285b478f3eb3b074538fe0`. It extracts the current workflow's wrapper-boundary script, copies **only** the current wrapper into a disposable tree, uses the pinned local venv, and deletes the tree. Independent orchestrator replay returned script rc 0: positive rc 0, unchanged-cache control rc 0, and each of the seven targeted negatives rc 2; final observed line was `wrapper boundary proof observed: 1 positive, 1 control, 7 fail-closed negatives`. No Veyro source was typechecked. Focused local tests after the self-contained change: wrapper **40/40 PASS**; workflow behavior **16/16 PASS**; CAP-011 **21/21 PASS**. These are qualification candidates, **not** B5/B6 closure or CAP-012 approval; a fresh Linux run on the revised bytes and independent Opus determination remain mandatory. N4's owner-deleted-path registry validator remains unresolved, and the canonical manifest intentionally still fails the three CAP-012 approval fields.
