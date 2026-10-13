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

## 8. 2026-10-14 self-contained candidate, macOS cp314 matrix, and exact Linux CI

After independent Opus round 2 returned **BLOCKED** (session `f67eab06-bd75-4d84-844b-7c98fd1745f3`, transcript SHA-256 `386d5f6465e15e9944ee2fde7a6097fc6f890351e2ce428eba8c5c39ffbcb2c`), bounded Sonnet operation `M1C-R04-CAP012-DECOUPLE-MACOS-20261014` made `tools/run_scoped_mypy.py` self-contained: it owns `Denied` and `_canonical`, imports no CAP-011 symbol, and the canonical manifest CAP-012 dependency edge was removed. This section supersedes the earlier dependency and platform-gap descriptions in §5 and §7.4 for the **current candidate**, without retroactively altering the historical PR #6 evidence.

| Current local and PR #7 source file | SHA-256 |
| --- | --- |
| `tools/run_scoped_mypy.py` | `31b650acc68f16637fc758576b8ce64efc1332d3a617d621a699ec1e2ba16787` |
| `tools/tests/test_run_scoped_mypy.py` | `a7ae8db3134ba5af8695ea1a367f9eddec497c08a25fe7e600b6e313f0175c88` |
| `.github/workflows/typecheck-qualification-drill.yml` | `523b4c4a9d0ab35dbeed6c965c5c367d3d012b72cabc7ee31c6e4c5c76260a32` |
| `tools/tests/test_typecheck_qualification_drill_workflow.py` | `3e90f0742ecec949b6e0b2def154b588bd2459eccfa2a1a7633d78f98ea17fe0` |

The complete local macOS arm64 CPython 3.14.5 synthetic matrix and reproducible driver are retained in [MACOS_CP314_MATRIX_2026-10-14.txt](MACOS_CP314_MATRIX_2026-10-14.txt), SHA-256 `b10cfe29bf76fe53d25b764980aa7a72954d65fd21973238917a19c70663467b`. Independent orchestrator replay output SHA-256 `5de73c4e0d772c759a5aaf18c1ba3ee135e1bb4b2bd3e5b6e07f991731a4abcf`: script rc 0, positive rc 0, unchanged-cache control rc 0, seven targeted negatives each rc 2. It copied only the current wrapper into a disposable tree; no Veyro source was typechecked. Focused local tests on the changed candidate: wrapper **40/40 PASS**, workflow behavior **16/16 PASS**, workflow trust lint **ALLOW**.

Draft [PR #7](https://github.com/ahmadmabrook/Veyro/pull/7) isolates the same four files at exact head `0cb6b85ab17e686cd49224bcfe9db780b5e3d1a9`. Genuine [GitHub Actions run 38470072473](https://github.com/ahmadmabrook/Veyro/actions/runs/38470072473), job `115546563042`, completed **success** on that head; downloaded `gh run view --log` SHA-256 `18bef34533f9ab0d9b31e28771ffe6aa188a8aafe7ddb8f8512b95bfc33e7aec`. Its log prints the current wrapper SHA and observes positive rc 0, unchanged-cache control rc 0, seven fail-closed negatives rc 2, and `wrapper boundary proof observed: 1 positive, 1 control, 7 fail-closed negatives` on Linux x86_64 cp313. This replaces PR #6 as the changed-byte Linux synthetic qualification input. PR #5 is deliberately red and must not merge.

B5/B6 and N1–N3 have remediation **candidates**, not independent closure. N4 (`validate_capabilities.py` stale owner-deleted manifest path) remains OPEN. CAP-012 remains **QUALIFIED — NOT APPROVED**; the canonical manifest deliberately fails on its three unset approval fields. Neither matrix is a Veyro-source mypy test, required CI gate, GOV-01-R04 credit, or MOD-001 certification. Fresh claimed independent Opus determination on these exact bytes and evidence is required before any approval.

## 9. 2026-10-14 R3-B7 followed-import closure remediation candidate (supersedes §8 current-byte/status assertions)

Independent Opus round 3 (session `727426f7-5696-4874-9e0f-bec5a9d161a1`, resolved runtime `claude-opus-5`, transcript SHA-256 `9602115fb0f129d228704a30dea2b971c126766c1d1aa6bbd483548485a9c722`) returned **BLOCKED** on new R3-B7 P1: mypy follows imports beyond `backend/app`, but the prior wrapper anti-hiding scan did not. It reviewer-closed B5/B6/N4. N4 was repaired at `399ffa4`; §8's “N4 remains OPEN” describes its earlier snapshot only. The reviewer’s R3-N5 inference that the workflow is on `main` used local HEAD: remote `origin/main` `f85a17ba28cf55a209b0129ea8e9ceacc6a9edb9` has no such workflow (GitHub contents API 404). The prior §7.3 unmerged/remote-main assertion is accurate. No approval or gate credit follows from the review.

Bounded Sonnet operation `M1C-R04-CAP012-R3B7-CLOSURE-20261014` added a static, fail-closed traversal of in-repository Python import edges reachable from the explicit `backend/app` source set. The candidate applies the existing anti-hiding check and pre/post fingerprint to reached modules outside `app`, while preserving the fixed mypy argv and `app` source count. It does **not** claim to inspect installed third-party stubs or to be mypy's own parsed-file list; independent review must adjudicate closure equivalence. Exact local source commit `645b6871ecfc7ee6757abd8a24d5132361849b25`:

| File | SHA-256 |
| --- | --- |
| `tools/run_scoped_mypy.py` | `c56360eafff141a7db44a76d55b94395561472d80e4b454bd9dcd43570e4cbf7` |
| `tools/tests/test_run_scoped_mypy.py` | `3345f068371d35f2605e1f5b1a4d2b47c98a0dc47ab049b929346254d147350f` |
| `.github/workflows/typecheck-qualification-drill.yml` (unchanged) | `523b4c4a9d0ab35dbeed6c965c5c367d3d012b72cabc7ee31c6e4c5c76260a32` |

Independent orchestrator local verification: built-in focused unittest **57/57 PASS** (synthetic trees only), including followed-harness positive, hiding-directive denial, transitive imports and fail-closed negatives. Read-only `plan()` on current Veyro tree counted 25 explicit app `.py` files and returned a fingerprint; it did **not** start mypy. The worker's mutation control removed the closure call temporarily and observed 21 focused failures, then restored the final source bytes; this is a local test-control observation, not a CI gate.

The new [macOS cp314 raw matrix](MACOS_CP314_CLOSURE_MATRIX_2026-10-14.txt), SHA-256 `69de5ecad753a7eb3a44b34ee45a28a89dbd60cff681e409f21119b440de2dec`, records replay output SHA-256 `ccc33344ef34a874df6741be0d711f22409198f67bc233bdabdab71b34e64c6d`: workflow script rc 0, positive and unchanged-cache control rc 0, seven targeted negatives rc 2. It exercises the unchanged workflow's nine cases, **not** the new closure-specific test cases.

Draft [PR #7](https://github.com/ahmadmabrook/Veyro/pull/7) now has exact head `f5638e749f84d04f4047fc57d9643a94a10c427b`; [GitHub Actions run 38472870608](https://github.com/ahmadmabrook/Veyro/actions/runs/38472870608), job `115556164896`, succeeded on that head. Recovered `gh run view --log` SHA-256 `fd7e07288d02da1a8206f6d51b74d8024700172e7cf482b163ed8078c0617192` prints the wrapper hash and the same nine-case Linux cp313 outcomes. This is genuine CI execution of the changed wrapper bytes on synthetic fixtures, **not** a Linux CI test of R3-B7's new followed-import cases, Veyro-source mypy, or a required status check. PR #5 remains intentionally red and must not merge.

R3-B7 is a **locally tested candidate, not reviewer-closed**. CAP-012 remains **QUALIFIED — NOT APPROVED**; `approved_by`, `approved_date`, and `next_review_due` remain unset. Both canonical and registry validators continue to fail on those three fields. The exact follow-up is a bounded Linux CI execution of the new closure-specific synthetic tests (or a reviewer-supported reason it is unnecessary), reconciliation of current registry claim drift R3-N7, and fresh independent Opus determination before any capability approval. No real Veyro-source mypy, GOV-01-R04 gate or MOD-001 certification is claimed.

## 10. 2026-10-14 pinned Linux cp313 closure-specific synthetic CI (supersedes §9 CI-gap statement)

Bounded Sonnet operation `M1C-R04-CAP012-R3B7-LINUX-TESTS-20261014` (runner `4a3af2d2-ade4-4faa-a723-935b5a34982a`) added execution of the actual committed wrapper test module in the tokenless synthetic-only workflow. Local source commit `427e366`; workflow SHA-256 `a5be811c3a0e42e44fdaddaf5ae3c33ab4a18cfd9a6ebecd6c3e1ff0363756cd`, focused workflow-test SHA-256 `799554c5affb1c1e440078194194df522359d8bebef2c4474da1df422f82a966`. Independent orchestrator reran focused workflow tests **29/29 PASS**, workflow-trust lint **ALLOW**, and `git diff --check` PASS. These local checks confer no CI or gate credit.

Draft [PR #7](https://github.com/ahmadmabrook/Veyro/pull/7) exact head `49413ad8d4f688a36948be300bc142b7f72593fb` contains the same workflow/test bytes (isolated branch commit `49413ad`). Genuine [GitHub Actions run 38473895370](https://github.com/ahmadmabrook/Veyro/actions/runs/38473895370), job `115559642211`, completed **success** on that head. Recovered `gh run view --log` SHA-256 `24a84c5111cede2874fab2dd888643132317913dc9e126c09e841c51db152939` verifies the fetched head, current wrapper SHA-256 `c56360eafff141a7db44a76d55b94395561472d80e4b454bd9dcd43570e4cbf7`, current wrapper-test SHA-256 `3345f068371d35f2605e1f5b1a4d2b47c98a0dc47ab049b929346254d147350f`, the prior one-positive/one-control/seven-negative synthetic wrapper boundary, and **57/57 synthetic wrapper tests OK on pinned Linux cp313 with no skips**, including all **17** named followed-import closure positive/negative tests. The tests copy those two committed source files into a disposable repo-shaped tree; no Veyro application source was a mypy target. PR #5 remains intentionally red and must not merge.

This closes only §9's Linux CI **execution gap** for the new tests. It does **not** independently close R3-B7's implementation invariant or resolve mypy-parsed-closure equivalence. CAP-012 remains **QUALIFIED — NOT APPROVED**; its three approval fields remain unset, the canonical/registry validators must continue to fail on those fields, and no real-source mypy, required status-check gate, GOV-01-R04 or MOD-001 certification is claimed. Next: apply the convergence-policy pre-fourth-review analysis to the exact current snapshot, then claim one fresh independent Opus CAP-012 determination only if that analysis permits it.

## 11. 2026-10-14 round-4 PEP 561 fail-closed remediation candidate (supersedes §10 current-byte assertion)

Independent Opus round 4 **BLOCKED** CAP-012 (session `6826ebec-f9ce-4604-a235-cb3cbbf569a1`, runtime `claude-opus-5` verified in 77 assistant entries, transcript SHA-256 `c615ebc54d98208c6c30bcd67bffa1ac98bc1ffa8766588f8d6ed7f0c46367da`). The P1 counterexample was a top-level in-repo PEP 561 `backend/tests-stubs/` package: on a disposable fixture, a real error in `tests/__init__.py` produced mypy rc 1 without the stub package, then mypy rc 0 with clean `tests-stubs/*.pyi`, while the prior wrapper scanner ALLOWED. Orchestrator independently reproduced that differential. P2: uncaught non-`Denied` errors exited 1, indistinguishable by exit code from type errors. No Veyro source was typechecked.

Bounded Sonnet operation `M1C-R04-CAP012-R4-STUBSHADOW-20261014` (runner `1ec48ccc-ebed-41e1-b4b5-eaabfd307d86`) changed only `tools/run_scoped_mypy.py` and its synthetic test module; source commit `ae47d8c7a999f5a11309b6804f132ca7367ca270`, wrapper SHA-256 `1a5df02b6c0ddd69a90c46adb62c81e3adb0b2ba162484fa2180b14ec665399c`, test SHA-256 `c231b64e584fc3f3ee309996474cc897f501b257eb2f148602b2a3b20651036f`. `plan()` now fails closed on any top-level `backend/*-stubs` entry, including a broken symlink; the existing post-mypy `plan()` repeats that check. `main()` classifies other `Exception` as DENY rc 2, without catching `BaseException`. Independent orchestrator reran focused built-in unittest **68/68 PASS** (macOS cp314, synthetic fixtures only), compile and `git diff --check` PASS. The new synthetic regression proves mypy rc 1 control, mypy rc 0 on stub shadow, wrapper rc 2 for the shadow, and clean positive. No approval follows from local tests.

Draft [PR #7](https://github.com/ahmadmabrook/Veyro/pull/7) exact head `0e37ff013c6aab19bd1605d4bd44202a88396727` contains the same wrapper/test bytes (isolated branch commit `0e37ff0`). Genuine [GitHub Actions run 38476676543](https://github.com/ahmadmabrook/Veyro/actions/runs/38476676543), job `115568948423`, completed **success** on that head. Recovered `gh run view --log` SHA-256 `6c827a0199034a716fc13c98fdefa2ccfa016a7fad83a520cf0e87f789716bcb` prints both file hashes, the prior nine-case synthetic wrapper matrix, and **68/68 synthetic wrapper tests OK on pinned Linux cp313 with no skips**, including the PEP 561 shadow negative, exception-classification test, and 17 named followed-import closure cases. This is changed-byte Linux synthetic execution, **not** independent reviewer closure, Veyro-source mypy, required CI status check, GOV-01-R04 or MOD-001 certification.

CAP-012 remains **QUALIFIED — NOT APPROVED**; its three approval fields remain unset and both validators must continue to fail on exactly those fields. The P1/P2 changes are remediation candidates awaiting convergence-policy pre-fifth-review assessment and, if legal, one fresh independent Opus determination under the five-review absolute cap.

## 12. 2026-10-14 independent fifth-round bounded local approval (no GOV-01-R04 gate credit)

Fresh-context independent Opus review `M1C-R04-CAP012-OPUS-REVIEW-R5-20261014` returned terminal **APPROVED (BOUNDED) — LOCAL wrapper invocation only**, P0=0/P1=0. Session `d1a41f31-70cf-472a-87c0-e9458362a8df` has 55 assistant entries with runtime model `claude-opus-5`; transcript SHA-256 `fd237a81b500f3c5613e661b7fc64224256a36dca8b7f01bf27e26933f4b98a1`. The reviewer independently re-fetched draft PR #7 run `38476676543` on exact head `0e37ff013c6aab19bd1605d4bd44202a88396727` and reproduced the log SHA-256 `6c827a0199034a716fc13c98fdefa2ccfa016a7fad83a520cf0e87f789716bcb`, 68/68 synthetic Linux cp313 tests, no skips. It independently reran 68/68 synthetic tests locally on macOS cp314, including the real-mypy stub-shadow differential, and verified `plan()` on the real tree without starting mypy (25 app sources). The P1 followed-import/PEP 561 shadow finding R3-B7 and P2 exception-classification finding R4-N10 are reviewer-closed for wrapper SHA-256 `1a5df02b6c0ddd69a90c46adb62c81e3adb0b2ba162484fa2180b14ec665399c` only.

The reviewer required two P2 record/disclosure corrections in the same commit that records approval. R5-P2-1: registry scope now names the current wrapper/test commit/hashes and exact Linux run, replacing a stale 57-test candidate. R5-P2-2: registry explicitly discloses that an installed `<name>-stubs` distribution in the venv, matching a top-level in-repo backend package, could shadow followed source without wrapper denial; none was observed at review and the risk was **not reproduced**, so no false negative-test claim is made. The existing wrapper docstring accurately says installed third-party stubs are not policed; its reviewed bytes are unchanged. This qualified approval excludes unverified venv site-packages. Independently verify the current installed-tree hashes before the first local real-source invocation.

**Scope:** exact local `tools/run_scoped_mypy.py` wrapper and fixed `backend/app` invocation only, on a verified venv; no direct mypy, CI gate, alternate target/config/flags, or other mypy tool. No mypy was run on Veyro source during review. The synthetic CI is not a required status check; no GOV-01-R04 or MOD-001 requirement is certified. The canonical and registry capability validators must PASS on the recorded approval fields before reliance. This is the fifth and absolute-final normal independent CAP-012 review; no ordinary sixth review is authorized.
