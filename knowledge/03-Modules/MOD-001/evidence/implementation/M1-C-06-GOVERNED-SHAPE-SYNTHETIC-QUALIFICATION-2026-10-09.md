# M1-C-06 governed-shape synthetic qualification (CAP-009 gitleaks, CAP-010 Ruff S608) — 2026-10-09

Implementation evidence (Sonnet) for the determination's §6.3 items 2–3 and §7.4 items 1, 3. It is **not** an approval, a scenario result, a CI result, or a real-tree scan. Independent Opus extension is still required before any real-tree use.

## Isolation
All scanner targets and cwd were disposable pytest `tmp_path` trees outside the repo. Neither scanner touched Veyro files, index, history or CI. Credential-shaped value: runtime-assembled `EXAMPLE_NOT_A_REAL_KEY` placeholder, redacted 100%, asserted absent from report/streams. Ruff read the repo configs via `--config` only (config read, never a target). Ruff `check`/`format --check` was also run on the two new test files themselves (C10-1 met per the identity note); `--select S` was not run on any Veyro file.

## Artifacts
- gitleaks: upstream `gitleaks_8.30.1_darwin_arm64.tar.gz` downloaded to disposable temp, SHA-256 `b40ab0ae…aeb6a5` verified **before** extraction; contained binary SHA-256 `ba52fb1b…bc0e84f`, `version` = 8.30.1. Tests take it from `$VEYRO_GITLEAKS_BIN` and fail closed unless its SHA-256 equals that pin (Homebrew binary `052d1882…c771422` verified to fail: 7 failed).
- Ruff: `backend/.venv/bin/ruff` 0.16.9, SHA-256 `8b799e53…509e57` (pinned in the test; fails closed otherwise).

## Files (new; existing reviewed drills left unchanged)
- `tools/tests/test_gitleaks_governed_qualification.py` sha256 `cb82662f75bb9327408e6a1d0d7deb4d7f1390055d3199f1c154557b0f8a5725`
- `tools/tests/test_ruff_s608_governed_qualification.py` sha256 `0d431e3a0b368acf88be25557c373b6f9a12fe705e0cfec9a67aaf7dfbef35fe`

## Commands and results
```
export VEYRO_GITLEAKS_BIN=<disposable>/x/gitleaks
backend/.venv/bin/python -m pytest -p no:cacheprovider tools/tests/test_gitleaks_governed_qualification.py tools/tests/test_ruff_s608_governed_qualification.py -q
```
Run twice: `28 passed` both times (12 gitleaks + 16 Ruff). `ruff check` and `ruff format --check` on both files: clean. Wrong binary (Homebrew): `7 failed, 5 passed` (hash mismatch → fail closed).

## Findings
**gitleaks** (default shape rc 0/0 findings vs governed rc 42/1 `github-pat`, each with an unsuppressed control showing the fixture is a real detection):
| Surface | Default | Governed |
|---|---|---|
| inline `gitleaks:allow` | suppressed | detected (`--ignore-gitleaks-allow`) |
| `.gitleaksignore` in cwd | suppressed | detected (`-i <empty dir>`) |
| `--baseline-path` | suppressed | detected (flag never passed) |
| `.gitleaksignore` at **target root** | suppressed | **no safe flag**: `-i <empty dir>` does not disable it → wrapper **refuses** (`GovernedScanRefused`) rather than pass. Ignore files in subdirectories were not honoured. |

Also observed: gitleaks reports no scanned-file count, so non-vacuity is wrapper-side (≥1 non-empty file, directory target) not tool-side; single-file targets are refused by the wrapper. `--max-decode-depth` default is **5** in this binary (determination §3 says 0); archive depth default 0. Missing target and malformed config exit 1 (neither 0 nor 42).

**Ruff S608** (real config via `--config ruff.toml` and `--config backend/pyproject.toml`, both parametrized; no `--isolated`): `# noqa: S608` → rc 0 by default; `--ignore-noqa` → rc 1 `S608`. Bad config → rc 2, finding → rc 1 (distinct). Syntax error → rc 1 `invalid-syntax` (wrapper distinguishes from S608). **Ruff limits found:** empty directory and *missing* target both return **rc 0, no findings** (warning only) — vacuous pass; compensating wrapper check (`--show-files` must list ≥1 file and every explicit target must yield a checked file, targets must exist/non-empty) refuses all such cases. A gitignored tree reached by directory discovery is skipped (wrapper refuses); an explicitly named file is still checked. A guard test asserts the repo configs contain only `line-length`/`target-version` (determination §7.2 premise).

## Chosen governed invocations (proposed, unapproved)
- gitleaks: `gitleaks dir --no-banner --no-color --redact=100 --exit-code 42 --report-format json --report-path <temp outside repo> --ignore-gitleaks-allow -i <empty dir> <dir target>`; cwd outside repo; no `--baseline-path`; pre-checks: target is a directory with ≥1 non-empty file and no root `.gitleaksignore`; binary SHA-256 pin; exit contract 0 clean / 42 leak / other = error.
- Ruff: `ruff check --config <ruff.toml|backend/pyproject.toml> --no-cache --no-fix --select S --ignore-noqa --output-format json <explicit targets>`, preceded by the `--show-files` non-vacuity pre-check; exit 0 clean / 1 findings (code-classified) / 2 error; never `--fix`, `--unsafe-fixes`, `--add-noqa`, in-place format.

## Limits and what remains unapproved
One rule per tool (`github-pat`, `S608`); no archive/encoded-secret coverage; Ruff S is pattern-based. The chosen shapes are wrapper-dependent: the wrapper exists only in these tests, not as a committed gate tool. Registry statuses, manifest, workflows/CI, scenarios, reviewer claim, C05 untouched. Real-tree/Git index/history/CI scanning and `--select S` on Veyro files remain **unapproved** pending independent extension; no scenario PASS is claimed; BUG-057 unchanged.
