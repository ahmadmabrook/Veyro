---
doc: M1-C-06-PYTEST-SYNTHETIC-QUALIFICATION
module: MOD-001
date: 2026-10-09
type: IMPLEMENTATION evidence (stage-5 synthetic qualification drill + provenance)
requirement: GOV-01-R01, GOV-01-R04, DC-19
related: CAP-011 (pytest 9.1.1), BUG-057, M1-C-06-TEST-TOOL-SCOPE-DECISION-2026-10-09, CAP-009, CAP-010
operation: d77d0542-a80c-45aa-a5ab-271b318a1b09
status: QUALIFIED (draft row) RECORDED — NOT AN APPROVAL
---

# M1-C-06 — CAP-011 pytest 9.1.1 synthetic qualification drill

## 1. What this is and is not

Per `M1-C-06-TEST-TOOL-SCOPE-DECISION-2026-10-09.md` Decision 1, pytest is a separate third-party
executable capability needing its own exact-scope row and synthetic positive/negative drill. This
record is that drill plus provenance. It is **not** an approval: CAP-011 is `QUALIFIED — NOT
APPROVED`, `approved_by`/`approved_date` blank, `next_review_due` unset, `lifecycle_status` not
ACTIVE, and no independent Opus determination has occurred or been dispatched. pytest was **not**
run on any Veyro test, import, conftest or config in this operation. mypy, Ruff and gitleaks were
not invoked. No code changed, no scenario PASSed, no remote action beyond read-only metadata
fetches (PyPI JSON/provenance, GitHub API reads, one wheel download hashed then deleted).

BUG-057 is unchanged in status: historical pytest use on project test files stays a disclosed gap,
not retroactively authorised.

## 2. Observed installed version vs CI artifact pin (kept distinct)

| Item | Value | Basis |
|---|---|---|
| Installed (observed) | `pytest 9.1.1`, `pluggy 1.6.0`, `iniconfig 2.3.0`, `packaging 26.3`, `pygments 2.21.0` in `backend/.venv` (Python 3.14.5, macOS arm64, `/opt/homebrew` base) | `python -m pytest --version` -> `pytest 9.1.1`; `*.dist-info/METADATA` |
| Declared pin | `pytest==9.1.1` | `backend/pyproject.toml` line 14 (`[project.optional-dependencies].dev`) |
| Lock pin | `pytest==9.1.1 --hash=sha256:37a86b45efb9a47a61a36449063e8e18d0cab3161329fc099eb21783169c4f0c` | `backend/requirements-dev.lock.txt` line 30 |
| Selected CI artifact (pure-Python, platform-independent) | wheel `pytest-9.1.1-py3-none-any.whl`, 386536 bytes, SHA-256 `37a86b45efb9a47a61a36449063e8e18d0cab3161329fc099eb21783169c4f0c` | PyPI JSON `urls[].digests.sha256`; lock; **and** locally computed by downloading the wheel to a disposable temp dir, hashing, deleting (`WHEEL_DIR_REMOVED`). Three-way match. |
| Dependency wheels (lock vs PyPI digest) | pluggy 1.6.0 `e920276d…d4746` (20538 B); iniconfig 2.3.0 `f631c04d…fbf12` (7484 B); packaging 26.3 `d7193f7c…cd1c` (129956 B); pygments 2.21.0 `2363c69b…137d9` (1250147 B) | each lock hash equals the PyPI wheel digest. Not downloaded locally. |
| Installed-tree integrity | every hashed `RECORD` entry matches the installed file: pytest 92 ok/0 mismatch/0 missing; pluggy 15/0/0; iniconfig 11/0/0; packaging 30/0/0; pygments 351/0/0 (unhashed `RECORD` rows are `.pyc`/`RECORD` itself) | `python -I` script over `site-packages` |

Honest limit: the installed files were verified against their own `RECORD`, and the wheel digest
equals lock = PyPI, but the *installed* tree was not shown to derive from that exact wheel (no
install log / pip cache evidence inspected). The CI pin is the wheel digest; **no CI workflow
installs by that hash yet**, so the pin is not enforced anywhere.

## 3. Official-source provenance (read-only)

- PyPI project `pytest` 9.1.1: `license_expression` MIT, `requires_python >=3.10`, not yanked, no
  PyPI-listed vulnerabilities, wheel uploaded 2026-06-19T10:58:31Z; sdist
  `pytest-9.1.1.tar.gz` SHA-256 `1088fbde8f2b49d95a549a195707afa7a76a3ce9bcadc26b6d71f0ffda5fe313`.
- Source `github.com/pytest-dev/pytest`: release `9.1.1` (not draft, not prerelease, **immutable**
  per release API), published 2026-06-19T10:58:55Z, assets = wheel + sdist. Tag `9.1.1` is an
  annotated tag object `32afde46…` -> commit `cf470ec0bf7eb89cd97dd56df4859eae5db46447`; GitHub
  reports the tag as **unsigned** (`verified: false, reason: unsigned`). Repo license detected MIT.
  Installed `licenses/LICENSE` SHA-256 `ca836a5f9ecca3b2f350230faa20a48fb8b145653b5568d784862df864706b9b`
  (not compared byte-for-byte to upstream).
- PyPI publish attestation exists for the wheel (`/integrity/.../provenance`, version 1, one
  bundle, publisher kind GitHub, repository `pytest-dev/pytest`, workflow `deploy.yml`, environment
  `deploy`). The in-toto statement subject digest equals the wheel SHA-256 above. The embedded
  Sigstore certificate (valid 2026-06-19 10:58:29–11:08:29 UTC, OIDC issuer
  `token.actions.githubusercontent.com`) names workflow
  `pytest-dev/pytest/.github/workflows/deploy.yml@refs/heads/release-9.1.1`, commit
  `cf470ec0…` (matches the tag's commit) and run `…/actions/runs/27820747470/attempts/1`.
- **The attestation signature, certificate chain and transparency-log entry were NOT
  cryptographically verified**: no `sigstore`/`pypi-attestations` tooling is installed and none
  was installed (that would be another unqualified third-party tool). Only the statement and
  certificate fields were decoded. No signature or approval is claimed or invented.
- Installed `pytest11` entry points (third-party pytest plugins) in the venv: **none** (`[]`).

## 4. Boundaries observed

- Interpreter: `/Users/ahmadmabrouk/Desktop/Veyro/backend/.venv/bin/python` (symlink to
  `python3.14`, 3.14.5; `shasum` of the symlink-resolved file path `…/bin/python`:
  `2477b47fa3ae65b9574eb18a15edb364e96948eaa1875ad3f1c80d780efc9c12`, an observation of what ran,
  not a pin). Invoked as `python -m pytest`.
- Fixtures: freshly written by `printf` into `mktemp -d "$TMPDIR/veyro-pytest-drill[2].XXXXXX"`
  (`TMPDIR=/Users/ahmadmabrouk/.openclaw/tmp` on this host — the process's OS temp dir, outside the
  repo). Non-sensitive synthetic content, no credentials, no member data, no Veyro imports. Runner
  scripts lived in a separate `mktemp -d /tmp/veyro-pytest-runner.*` directory, not the fixture dir.
- Every run: cwd = the temp `sub/` directory, explicit absolute temp test paths, `-c /dev/null`,
  `--confcutdir=<temp sub>`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, `PYTEST_ADDOPTS`/`PYTEST_PLUGINS`
  unset (only one `PYTEST_*` variable in the environment: confirmed `ENV_PYTEST_VARS: 1`).
- No Veyro path was ever an argument; no Veyro file was read by the runs.
- Pass 2 adds `--rootdir=<temp sub>` and `-p no:cacheprovider` (see §6 finding). These two flags
  are an addition to the requested flag set, made for a reason disclosed below, not a silent change.

## 5. Fixtures (non-empty before any run: `NONEMPTY_OK` x4 in each pass)

| File (temp) | Bytes | SHA-256 | Role |
|---|---|---|---|
| `sub/test_positive.py` | 88 | `c37b3bb5eaf0938d0a810e8cd2f5c782fa7b9eb8f6e07c87b6ce6aa8bf71f33b` | positive: two passing tests |
| `sub/test_negative.py` | 53 | `481e0519203ef8c57f732475c5f948e8ce55f762fac1376f52d3c0c1fe5df180` | negative: `assert 1 + 1 == 3` |
| `pytest.ini` (parent, decoy) | 61 | `e769418046ed73fb5199775f734c328b9865de282fb5212f992dfc110c832255` | decoy config: `addopts = -x --maxfail=1 -p decoyplugin_nonexistent` |
| `conftest.py` (parent, decoy) | 69 | `e4c2169422b826eea7c12fca9f827e35823c548397388036eebb3bedffe6bad1` | decoy: writes `conftest.py.LOADED` marker if imported |

```python
# test_positive.py                      # test_negative.py
def test_add():                         def test_deliberate_failure():
    assert 1 + 1 == 2                       assert 1 + 1 == 3

def test_str():
    assert "ab".upper() == "AB"
```

The decoy `pytest.ini` and `conftest.py` sit in the parent of `sub/` precisely so that a run that
wrongly discovers ancestor configuration would be visibly perturbed.

Post-run SHA-256 of all four files equals the table (in both passes): fixtures not mutated.
Runner/log hashes (files in `/tmp`, outside the repo, summarised here): `drill.sh`
`0edfd334334351160b00f0787c29365f010cf45f540d7a776e00ba9af95062c8`, `drill_v2.sh`
`eaeb77ebe9a04a2a511975ad0736e29a56f9ff3eca6de6abcdbd5200e6773a70`, pass-1 log
`fb3b462632ec29126747013872e80f9bd21ed164feffb98ec3c38a3736e1cea2`, pass-2 log
`b014aa4774fc5b4a801a3968ef3ee480fbe2dc5706f37f013acf5d7fef649127`.

## 6. Pass 1 — exact requested invocation

```
python -m pytest -c /dev/null --confcutdir=<TMP>/sub <TMP>/sub/<file(s)>      (cwd=<TMP>/sub)
```

| Run | Expected | Observed (sanitised `<TMP>`) | Result |
|---|---|---|---|
| `--version` | `pytest 9.1.1` | rc 0, `pytest 9.1.1` | PASS |
| positive | rc 0 | rc 0, `collected 2 items`, `2 passed` | PASS |
| negative | rc nonzero, assertion report | rc 1, `E assert (1 + 1) == 3`, `1 failed` | PASS |
| both | rc 1, 2 passed 1 failed | rc 1, `1 failed, 2 passed` | PASS |
| empty dir | rc 5 | rc 5, `collected 0 items` | PASS |
| missing path | rc 4 | rc 4, `ERROR: file or directory not found` | PASS |
| `-k` deselects all | rc 5 | rc 5, `2 deselected` | PASS |

Decoy `conftest.py` not imported (`DECOY_LOADED=NO`); decoy `pytest.ini` not applied; temp dir
removed (`CLEANUP_OK`).

**Finding (disclosed side effect, not a result failure):** with `-c /dev/null` pytest took the
config file's directory as `rootdir`, printing `rootdir: /dev`, `configfile: null`, node ids shown
as `../../../../../../dev`, and it **attempted to create `/dev/.pytest_cache`** (cacheprovider
`PytestCacheWarning: could not create cache path /dev/.pytest_cache/...: Operation not permitted`,
macOS blocked it; `DEV_CACHE_PRESENT=NO` confirmed in pass 2). The assertion verdicts and exit
codes were still correct, but the requested flag set alone makes pytest try to write outside the
temp area and mangles node ids. That is why pass 2 exists and why the CAP-011 scope specifies the
hardened flags.

## 7. Pass 2 — hardened invocation (`--rootdir=<TMP>/sub -p no:cacheprovider` added)

```
python -m pytest -c /dev/null --rootdir=<TMP>/sub --confcutdir=<TMP>/sub -p no:cacheprovider <TMP>/sub/<file(s)>
```

| # | Run | Expected | Observed | Result |
|---|---|---|---|---|
| B1 | positive | rc 0 | rc 0, `rootdir: <TMP>/sub`, `collected 2 items`, `2 passed`, no warnings | PASS |
| B2 | negative | rc nonzero + report | rc 1, `E assert (1 + 1) == 3`, `FAILED test_negative.py::test_deliberate_failure`, `1 failed` | PASS |
| B3 | both | rc 1 | rc 1, `1 failed, 2 passed` | PASS |
| B4 | empty dir | rc 5 | rc 5, `no tests ran` | PASS |
| B5 | missing path | rc 4 | rc 4, `file or directory not found` | PASS |
| B6 | `-k` deselects all | rc 5 | rc 5, `2 deselected` | PASS |
| B7 | `--trace-config` plugin inventory | only built-ins, empty `active plugins:` | 35 `PLUGIN registered` lines, all `_pytest.*` built-in modules plus Config/Session/terminal/logging/fixture objects; `active plugins:` empty; no third-party module | PASS |
| — | nonempty fixtures | 4 x `NONEMPTY_OK` + `collected N>0` for B1/B2 | yes | PASS |
| — | decoy isolation (B1–B7) | `conftest.py.LOADED` absent | `DECOY_CONFTEST_LOADED=NO` | PASS |
| C1 | control: `--confcutdir=<TMP>` (decoy allowed) | decoy conftest IS imported (proves B-series "NO" is not vacuous) | rc 0, `CONTROL_DECOY_CONFTEST_LOADED=YES` | PASS |
| C2 | control: `-c <TMP>/pytest.ini` | decoy `addopts` honoured: bogus `-p` plugin errors | rc 1, `ImportError: Error importing plugin "decoyplugin_nonexistent"` | PASS |
| — | no cache written | no `.pytest_cache` in temp or `/dev` | `PYTEST_CACHE_PRESENT=NO`, `DEV_CACHE_PRESENT=NO` | PASS |
| — | fixtures unmutated, cleanup | hashes equal §5 | equal; `CLEANUP_OK` | PASS |

Only artefacts written inside the temp tree besides the decoy marker: `__pycache__/*.pyc`
(assertion-rewrite caches). The C1/C2 controls deliberately relax one isolation knob each, on the
same synthetic files, within the temp tree; they are not part of the CAP-011 invocation shape.

Overall: pass 1 7/7, pass 2 all expected outcomes (B1–B7, C1–C2, isolation, cache, cleanup) observed.

## 8. Tool limitations (disclosed; not cured by this drill)

- **Exit codes:** rc 0 pass, 1 test failures, 4 usage/path error, 5 nothing collected (also reached
  by `-k` deselecting everything). A gate must treat 4/5 as errors, not "no failures", and should
  assert a nonzero collected count; pytest itself will not fail an empty/over-filtered selection
  with rc 0 but wrapper code might.
- **`-c /dev/null` pitfall (§6):** rootdir becomes `/dev` and cacheprovider tries to write there
  unless `--rootdir` and `-p no:cacheprovider` are also given.
- **Arbitrary code execution:** pytest imports and runs the code in the files it is pointed at, and
  any `conftest.py`/plugin/`pyproject` reachable by discovery. Its safety on real code depends on the
  code, not the tool; this drill proves nothing about running it on Veyro tests, Veyro's
  `[tool.pytest.ini_options]` (`testpaths = ["tests"]`), Veyro conftests, the Docker/Colima fixtures
  (CAP-008) or any network/DB test. Those uses are **out of CAP-011's drafted scope**.
- **Environment mismatch:** drill ran on the installed macOS arm64 / Python 3.14.5 venv;
  `requires-python` is `>=3.13` and CI is not defined. The wheel is pure-Python so the artifact is
  platform-independent, but behaviour on the CI interpreter is unevidenced.
- **Provenance gaps:** attestation signature/chain unverified (no tooling, none installed); git tag
  unsigned; installed tree not proven to derive from the pinned wheel; pin not CI-enforced; four
  dependency wheels checked by PyPI digest only.
- **Two small fixtures:** demonstrates exit-code and report semantics for plain assert tests; does not
  cover fixtures, parametrization, markers, async, xdist or any plugin (none installed).
- **mypy** is a separate capability and untouched.

## 9. Effect and determination

Determination for this operation: stage-5 mechanical positive/negative evidence for pytest 9.1.1
**passed** for the hardened, synthetic-only invocation, and provenance was gathered to the extent the
sources allow, with the gaps above stated. CAP-011 is therefore registered as an exact-scope draft at
**QUALIFIED — NOT APPROVED**. Stage 4 (independent Opus `veyro-security-reviewer` determination)
has not occurred; this record adds no review entitlement and dispatches none. Per the scope
decision's Decision 2 condition 1, CAP-011 now has drill evidence but is excluded from any batch
until the owner/dispatch authorises one; mypy still has none.

After registration, `backend/.venv/bin/python knowledge/00-System/validate_capabilities.py` evaluates CAP-011 and
reports `FAIL` with 9 errors (3 each for CAP-009/010/011: CAPABILITY_NOT_APPROVED, empty `approved_by`,
unparseable `next_review_due`) — the intended fail-closed hold; it was 6 before this row.

No real-tree, CI, GOV-01-R01/R04 gate or scenario reliance on CAP-011 is authorised by this record.
No scenario is PASSed; MOD-001 exit remains 0/8.
