---
doc: M1-C-06-PYTEST-TARGET-SCOPE-SYNTHETIC
module: MOD-001
date: 2026-10-09
type: IMPLEMENTATION evidence (synthetic analogue of the intended Veyro backend/tests invocation shape)
requirement: GOV-01-R01, GOV-01-R04, DC-19
related: CAP-011 (pytest 9.1.1), BUG-057, M1-C-06-PYTEST-SYNTHETIC-QUALIFICATION-2026-10-09
operation: 7fa75e8b-afef-4f35-a938-9d24b4b9bc1b
status: SYNTHETIC ANALOGUE RECORDED — NOT AN APPROVAL
---

# M1-C-06 — CAP-011 pytest intended-scope synthetic analogue

## 1. What this is and is not

Follow-on to `M1-C-06-PYTEST-SYNTHETIC-QUALIFICATION-2026-10-09.md`, which only drilled loose
files with `-c /dev/null`. This record drills a **project-shaped** synthetic tree
(`[tool.pytest.ini_options]`, `testpaths = ["tests"]`, `tests/conftest.py` fixture) to qualify the
invocation shape intended for a later Veyro `backend/tests` run. pytest was **not** run on any
Veyro file, import, test, config or directory: every argument, cwd, config, rootdir, HOME and
TMPDIR was under one fresh OS-temp tree (`$TMPDIR` = `/Users/ahmadmabrouk/.openclaw/tmp`, outside
the repo), which the runner removed (`TMP removed: YES`). No mypy/Ruff/gitleaks, no product-code
edit, no reviewer dispatch, no scenario promotion, no remote action. CAP-011 stays
`QUALIFIED — NOT APPROVED`; this adds no approval and no review entitlement.

## 2. Setup (`<TMP>` = the per-run `mktemp -d`; runner script lived in a separate `/tmp` dir)

- Interpreter: `/Users/ahmadmabrouk/Desktop/Veyro/backend/.venv/bin/python` (pytest 9.1.1, Python
  3.14.5, macOS arm64), invoked `-m pytest`, cwd `<TMP>/proj` (the rootdir) unless noted.
- Clean environment via `env -i HOME=<TMP>/home TMPDIR=<TMP>/tmp PATH=/usr/bin:/bin LANG=C.UTF-8
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<TMP>/sitedecoy PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`;
  `PYTEST_*` variables in the clean env other than that one: **0** (`PYTEST_ADDOPTS`/`PYTEST_PLUGINS`
  unset). `PYTHONPATH` deliberately exposes a decoy `pytest11` entry-point plugin so that the
  autoload-off result is non-vacuous (control G1).
- Base command (every governed run):
  `python -m pytest -c <TMP>/proj/pyproject.toml --rootdir=<TMP>/proj --confcutdir=<TMP>/proj -p no:cacheprovider [args] <explicit path>`
- Runner `drill.sh` SHA-256 `672f78e6aa33fa3fe52dd909955ad6da94629cc467c1e8622e5f6da442e224f7`
  (in `/tmp`, outside repo); full log (579 lines) `43189b60ccbffd2be801bda80325d9fee421261e0a8e4c999119e24d6f89f78c`.

Fixture SHA-256 (pre-run == post-run, `fixtures unmutated: YES`; 15 files, non-empty). Files that
embed the per-run temp path in a marker write (marked †) hash differently each run:

| File (under `<TMP>`) | SHA-256 | Role |
|---|---|---|
| `proj/pyproject.toml` | `9572539cdb1834b5bb4d817111d83de260b7d718995fc2794f82f5a6b01de7b8` | project-like config, `testpaths=["tests"]` |
| `proj/tests/conftest.py` † | `3b6d2b8162b0ee873e07ffc05334353a9ab2c3f9485399faf80db1cc5db77c21` | `synthetic_value` fixture (returns 42) + load marker |
| `proj/tests/test_synthetic_pass.py` | `1eb081e560e6a90cd2bacdd3c6a735b57f6f66ad6eb965dcd2cc06570c9ae3cf` | 2 passing tests (one uses the fixture) |
| `proj/tests/test_synthetic_fail.py` | `481e0519203ef8c57f732475c5f948e8ce55f762fac1376f52d3c0c1fe5df180` | `assert 1 + 1 == 3` |
| `proj/other/test_not_in_testpaths.py` | `87f89efaa87b92d7a72ba869e0570a569c602d3e6e5da873cb75735ed2d086b9` | in-project but outside `testpaths`; `assert False` |
| `pytest.ini` (parent decoy) | `fc418bccca6a5ba8269e2ccc40c5f896cc83af0cb9100e1b3aebdd9b507bc352` | `addopts = -x -p decoyplugin_nonexistent` |
| `conftest.py` (parent decoy) † | `ebca1847a538c9f21cf182677a096bb9febcb365588cc98b71b5f939ac98c690` | writes `parent_conftest.LOADED` |
| `outside/conftest.py` † | `4679f6e8251aaf5477a42d55b2b04c01f21fada30015728589bb6273ec5f1e1e` | writes `outside_conftest.LOADED` |
| `outside/test_outside_decoy.py` | `614cb9a2784b836dd2ed0f36a7d9ebd447d6028b8320b3e9a8e804b35cd73b07` | `assert False` |
| `sitedecoy/decoyplug.py` † (+ `.dist-info/entry_points.txt` `0ff7a0ff…c6dcdc`, `METADATA` `894d9f61…d35d379`) | `bdaf616a51a7c659d9743040543e09d72620328fc67862a165d11c97b70cdbc2` | `[pytest11]` plugin, writes `autoload_plugin.LOADED` |
| `nopath_proj/{pyproject.toml,test_stray_in_cwd.py,stray/test_stray_sub.py}` | `0f792d73…c72`, `e90e9a5f…c53b`, `19de0c5f…2b6` | testpaths names a missing dir; stray failing tests in cwd |

## 3. Results (sanitised return codes; every row matched its expectation)

| Run | Args (after base) | rc | Observed |
|---|---|---|---|
| A0 | `--version` | 0 | `pytest 9.1.1` |
| B1 positive | `<TMP>/proj/tests/test_synthetic_pass.py` | 0 | `rootdir: <TMP>/proj`, `configfile: pyproject.toml`, `collected 2 items`, `2 passed`; fixture test `test_fixture_executes` PASSED (fixture ran); only marker: in-root `proj_tests_conftest.LOADED` |
| C1 negative | `.../test_synthetic_fail.py` | 1 | `E assert (1 + 1) == 3`, `1 failed` |
| C2 mixed | `<TMP>/proj/tests` | 1 | `collected 3 items`, `1 failed, 2 passed`; `other/` and `outside/` not collected |
| D1/D2 testpaths | none (`--collect-only -q` / run) | 0 / 1 | `testpaths: tests`, 3 items, same 1 failed 2 passed; collect-only 0 (my first expectation of 1 was wrong; the tool is right) |
| E1 empty dir | `<TMP>/proj/empty` | 5 | `collected 0 items`, `no tests ran` |
| E2 missing path | `.../tests/does_not_exist.py` | 4 | `ERROR: file or directory not found` |
| E3 over-filtered | `-k nomatchxyz .../test_synthetic_pass.py` | 5 | `2 deselected` |
| E4 no path, cwd≠rootdir | none (cwd `<TMP>/proj/empty`) | 5 | testpaths ignored when cwd≠rootdir; nothing collected |
| F1b boundary | `--collect-only -q <TMP>/proj/tests` | 0 | no `outside`/`other` node id |
| F2 plugin inventory | `--trace-config --collect-only -q` | 0 | 29 registered module plugins; the only non-`_pytest` module is the in-root `tests/conftest.py`; no decoy/third-party mention; `active plugins:` empty |
| G1 control | autoload **on** | 0 | `autoload_plugin.LOADED` → the decoy entry point is live, so F2/B-series "not loaded" is non-vacuous |
| G2 control | `--confcutdir=<TMP>` | 0 | `parent_conftest.LOADED` → ancestor conftest is live when confcutdir is widened |
| G3 control | `-c <TMP>/pytest.ini` | 1 | decoy `addopts` honoured (`decoyplugin_nonexistent`) |
| G4 control | `PYTEST_ADDOPTS=-p decoyplugin_nonexistent` | 1 | env addopts honoured → env must be clean |

Throughout the governed runs (A–F2, H2) the parent `conftest.py`, parent `pytest.ini`, `outside/conftest.py`
and the decoy plugin were never loaded except where a row says otherwise.

## 4. Findings that bound the scope (kept as limitations, not hidden)

1. **KNOWN LIMIT — explicit outside path is honoured (F1, F3).** `pytest ... <TMP>/outside` and
   `<TMP>/proj/tests/../../outside` both returned rc 1, collected the decoy test and **executed
   `outside/conftest.py`**, despite `--rootdir`/`--confcutdir`. `--confcutdir` only stops *ancestor
   discovery above it*; it is not an argument-path allowlist. The discovery boundary is therefore
   enforced only by the caller: any wrapper/CI step must `realpath`-check each path argument to be
   under the intended tests root before invoking pytest. That wrapper does not exist and is not
   qualified here.
2. **FAIL-OPEN EDGE — `testpaths` fallback to cwd (H1).** With `testpaths = ["tests"]` naming a
   missing directory and **no path argument**, pytest (rc 1, 1 warning) collected stray tests from
   cwd and its subdirectories. So a missing/renamed `tests/` would silently widen the run. An
   explicit path argument (H2: missing explicit path → rc 4) removes this. Intended rule: always
   pass an explicit path; never rely on `testpaths` alone.
3. **rc 4/5 are not "ok"** (E1–E4): a gate must treat 4 and 5 as errors and require a collected count
   above zero.
4. **Env/config knobs are live** (G2–G4): ancestor conftest/ini/`PYTEST_ADDOPTS` all change behaviour
   when not suppressed, so the clean-env + `-c` + `--rootdir` + `--confcutdir` + plugin-autoload-off
   set is load-bearing, not decoration.

## 5. Side effects (all clean)

No `.pytest_cache` anywhere in `<TMP>` (0) or `/dev` (`NO`); temp `HOME` and `TMPDIR` empty after the
runs (0 entries each); no new files beyond the 15 fixtures (bytecode writing disabled); fixtures
byte-identical; repo `git status --porcelain` hash identical before/after
(`238bc39e672e1ce33c6d2fb477a3bf282032a72d5992826ec64da2b3a4559f91` at start); `TMP removed: YES`. No
credentials, network call by the harness, or customer data (fixtures are literal asserts). Absence
of network egress by pytest itself was not instrumented — it rests on the fixtures importing nothing.

## 6. Limitations (what this does NOT show)

- pytest runs whatever code it is pointed at; nothing here says Veyro's tests/conftest/imports,
  the Docker/Colima/Postgres harness (CAP-008), or any network/DB test is safe. Those need their own
  review of the code, fixtures being synthetic only, and no real member data.
- Only the venv's macOS arm64 / Python 3.14.5 was exercised; CI interpreter (>=3.13) and runner
  unevidenced. Unchanged from the first record: attestation signature unverified, tag unsigned,
  installed tree not proven to come from the pinned wheel, **CI hash-pin install not yet enforced**.
- Fixtures cover plain asserts and one function-scope fixture; not parametrisation, markers,
  async, xdist, plugins, `-p`, `pytest.ini`-in-tests variants or symlinked paths.
- Approval, an independent Opus determination, a path-allowlist wrapper, a CI workflow that installs
  by the `requirements-dev.lock.txt` hashes and CI review all remain **open dependencies**.

## 7. Determination

The synthetic analogue is **sufficient to narrow the drafted CAP-011 scope to the intended future
local/CI Veyro `backend/tests` invocation shape** with the bounded rules in §3–§4, and insufficient
for any reliance now. Real-tree or CI use stays prohibited until an independent verdict, APPROVED
registry fields, a validated path-allowlist wrapper and hash-pinned CI install exist. No scenario is
PASSed; MOD-001 exit remains 0/8.

## 8. Scope-correction process note (disclosure)

The first scripted edit of `CAPABILITY_REGISTRY.md` matched CAP-009's identical "Drafted scope" marker and
deleted CAP-010 plus parts of the CAP-009/CAP-011 rows (`validate_capabilities.py` then reported
CAP-010/CAP-011 UNREGISTERED). It was caught by that validator before finishing. The rows were rebuilt
from verbatim copies in the 2026-10-09 session transcripts (CAP-009 3779 chars, CAP-010 4871 chars, the
original CAP-011 5259 chars, each 15 cells; CAP-009's surviving prefix matched byte-for-byte), then the
CAP-011 scope cell alone was replaced. Only the CAP-011 scope, status-wording and evidence cells differ
from the pre-edit rows; CAP-009/CAP-010 are textually unchanged. Validator is back to the intended 9
approval-field errors (CAP-009/010/011 x not approved, no `approved_by`, no valid `next_review_due`).
Orchestrator reconciliation after worker exit corrected a stale CAP-009 BUG-057 sentence to its
pre-dispatch OPEN wording. Replacing only the current CAP-011 row with the recovered pre-dispatch
CAP-011 row reconstructed a full-registry SHA-256 of
`31ea5af9a65cc9d8c22b7e83c4f8945f17da8fcc1b92fc06d8718c34747c9cae`, exactly matching the
guard's pre-dispatch tracked-file hash. Thus CAP-011 is the sole registry-row delta; CAP-009,
CAP-010 and all other registry bytes match the pre-dispatch snapshot. The earlier tentative
Notion-mirror comparison is superseded by this exact local snapshot reconciliation.
