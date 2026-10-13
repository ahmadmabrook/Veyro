---
doc: M1-C-06-SYNTHETIC-TYPECHECK-CI-AUTHORING
module: MOD-001
date: 2026-10-09
classification: MANDATORY_NOW — GOV-01-R04 type-check CI supply-chain prerequisite
status: AUTHORED_NOT_RUN; no CI result, no capability approval
role: veyro-infra-sre-engineer (Sonnet)
---

# M1-C-06 — synthetic-only type-check qualification drill: authoring record

Implements `M1-C-06-MYPY-CI-LOCK-ARCHITECTURE-2026-10-09.md` §9 Step B (with the
§12 correction) using the additive lock recorded in
`M1-C-06-LINUX-CP313-TYPECHECK-LOCK-ACQUISITION-2026-10-09.md`. Authoring only:
no wheel was downloaded, nothing was installed, mypy was never invoked, nothing
was pushed, no PR was opened, no protection changed.

Note: the repository has no `AGENTS.md`; the root `CLAUDE.md`, the rules under
`.claude/rules/**` and the architecture record were the governing instructions.

## Artifact

`.github/workflows/typecheck-qualification-drill.yml` (SHA-256
`d8a18538938d86fa0d0efd17bea4b1414fb728100cabe15d7ede836661756f5e` at authoring
time; untracked). Reuses `tools/assert_ci_python313.py` and its existing tests
unchanged.

## §9 Step B mapping

| Req | Authored as |
|---|---|
| B1 shape | `on: pull_request`; `permissions: {}`; `runs-on: ubuntu-24.04`; `timeout-minutes: 15`; zero action references; zero secret references; no `if:`/`continue-on-error`; only `HEAD_SHA`/`REPO_URL` enter via `env:`, no expression interpolation in any script body. No required-status claim. Tokenless fetch pattern copied from `r03-failure-drill.yml`. |
| B2 interpreter | Candidates: `command -v python3.13`, `/usr/bin/` and `/usr/local/bin/` `python3.13`, `/opt/hostedtoolcache/Python/3.13.*/x64/bin/python3.13`. Each is run under `-I tools/assert_ci_python313.py`; first ALLOW wins; none ⇒ exit 1, explicitly no fallback to default `python3`. Path and full `sys.version` are printed by the script. Venv interpreter is re-asserted. |
| B3 lock guard | Denies unless the Linux lock exists, is not a symlink, and is a regular file; prints its SHA-256. |
| B4 install | venv from asserted interpreter, bundled pip never upgraded, `pip --version` printed; `--require-hashes --only-binary=:all: --no-deps --index-url https://pypi.org/simple --no-cache-dir --no-input --disable-pip-version-check`; all `PIP_*` unset and `PIP_CONFIG_FILE=/dev/null`; installed set printed with `pip list --format=freeze`. |
| B5 positive | One mypy call, on a two-file fixture written by the job into `mktemp -d` under `$RUNNER_TEMP`: `env -i … python -I -m mypy --config-file pyproject.toml --cache-dir=/dev/null --no-color-output synthetic_pkg`, cwd the fixture dir, config `python_version="3.13"`, `strict=true`. Asserts rc 0 and an exact-line match for `Success: no issues found in 2 source files`. No Veyro path appears as target, cwd, config or search path. |
| B6 negative 1 | Embedded stdlib snippet derives the macOS mypy requirement from `backend/requirements-dev.lock.txt` (read-only) and requires the version to equal, and the digest to differ from, the Linux lock's; writes `mypy==… --hash=…` to a disposable file; same install flags into a disposable venv; asserts rc≠0, a `do not match the hashes` / `No matching distribution` diagnostic, and that `mypy` is not importable afterward. No digest is typed by hand. |
| B7 negative 2 | Runs the assertion under the runner's default `command -v python3`; asserts rc≠0 and exact `RESULT: DENY`. If a future image's default were 3.13/linux-x86_64 this step would go red, which is the fail-closed outcome. |
| B8 red-job control | **Not authored** (needs a separate disposable run; see dependencies). |
| B9 local-equivalent | Already exists (`tools/assert_ci_python313.py` + `tools/tests/test_assert_ci_python313.py`), unchanged. |
| B10 observations | Live values are not yet observable; fields listed below. |

## Local static observations (this host: macOS, Python 3.14.5)

- Workflow parsed with Ruby `YAML.load_file` (PyYAML absent): top-level
  `permissions: {}`, trigger `pull_request`, one job, eight steps.
- Each of the eight `run:` bodies extracted and passed `bash -n`: all rc 0.
- No `${{` inside any `run:` body; grep for `uses:`, `secrets.`,
  `continue-on-error`, `always()`, `if:` found nothing; no trailing whitespace.
- The embedded digest-derivation snippet was run locally against the real locks
  (text parsing only): output `mypy==2.3.1 --hash=sha256:192abaedf75d…438ed24d`
  with Linux digest `1c80fbc405ed…dfdd5226` — the derived value equals the
  macOS digest the architecture record names.
- `python -I tools/assert_ci_python313.py` on this host: `RESULT: DENY`
  (expected on macOS/3.14); not CI evidence.
- `backend/requirements-dev.lock.txt` SHA-256 still
  `5b9383fe128cb1d7d8b8442c82fe305988980915140215f4a4f5e3adcbe2d698`; no
  prohibited file was edited.

## Remaining live dependencies (not satisfied here)

1. A disposable same-repository branch and PR to execute the workflow
   (not covered by the SCN-020 live authorization). Until then no run exists.
   This also requires the new workflow, lock, manifest and assert script to be
   committed on that branch; they are currently untracked.
2. Observations to be recorded from that run: resolved interpreter path and
   `sys.version`, the four assertion outcomes, pip version, materialized
   wheel filenames, mypy rc and success line, and the two negative outcomes.
3. B8 red-job control: one disposable run with an assertion inverted, to show
   the job goes red with no suppression.
4. Unverified assumptions the first run may falsify: that the 24.04 image
   exposes a CPython 3.13 at one of the searched paths (otherwise the job
   correctly denies and a different governed route is needed — no `apt`, no
   setup action); that the installed pip's hash-failure text matches the
   asserted regex; that the repository is public so the tokenless fetch works.
5. `mypy` real-code target scope (§6) is deliberately unauthored.

## Not claimed

No CI execution, no required status check, no GOV-01-R04 closure, no scenario
disposition (SCN-MOD001-030/031 remain NOT EXECUTED), no CAP-012 change —
QUALIFIED, NOT APPROVED. No reviewer consumed; no review entitlement created.
MOD-001 exit 0/8 unchanged.

## Same-day additive-lock reconciliation (2026-10-09)

The Linux cp313 lock was subsequently expanded from six to thirteen wheels for
the declared `backend/app` import closure. The workflow already reads that
stage-scoped lock by path, so its bytes remain unchanged (SHA-256
`d8a18538938d86fa0d0efd17bea4b1414fb728100cabe15d7ede836661756f5e`);
the expanded lock is SHA-256
`5e7596d408190a6103ffe1e3988f1c88ea33a34306302cc7de6f0570340e95de`.
The separate [imported-closure evidence](M1-C-06-LINUX-CP313-IMPORTED-CLOSURE-2026-10-09.md)
records the independent wheel-byte checks. Local deterministic readback:
the workflow has eight steps, one synthetic-only mypy invocation, no `uses:` or
`secrets.` reference and no suppression; Ruby YAML parsing and `bash -n` on
all eight run bodies pass. The stdlib interpreter-assertion suite passes
14/14, and the four governing baseline hashes match. None of those checks is
a Linux CI run or an independent CAP-012 determination.

Step B8's deliberate red-job probe and B10's runner observations still need
an authorized disposable same-repository CI run. The SCN-020 sacrificial
authorization does not extend to this C06 workflow. CAP-012 remains QUALIFIED,
NOT APPROVED; no Veyro source is type-checked and no scenario or gate is PASS.
