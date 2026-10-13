# M1-C-06 — gitleaks stage-5 synthetic qualification drill (2026-10-09)

Status: **STEP-A DRILL MATERIAL PRODUCED. Not a qualification, registration, or approval.**
Operation `3b67d286-52c0-4c69-8570-50e98de38b10`, subgoal
`M1-C-06-GITLEAKS-SYNTHETIC-QUALIFICATION`, execution role `IMPLEMENTATION`
(`claude-sonnet-5-5`). Implements §7 item 1 and "Step A" of
`M1-C-06-CAP-ORDERING-PLAN-DECISION-2026-10-09.md`.

## Scope and boundary

- Files written: `tools/tests/test_gitleaks_qualification.py` (SHA-256
  `45d459be9ab1523f32f156406f1e29d996f4738145b294bac94a241cbc66688c`) and this note. Nothing
  else changed: no registry, BUG_REGISTRY, CI/workflow, scenario status, plan, or remote edit.
- gitleaks `8.30.1` (`/opt/homebrew/bin/gitleaks`, Homebrew; MIT per installed LICENSE) ran **only**
  as `gitleaks dir` over pytest `tmp_path` directories, with `cwd` set to a tmp dir. It was not run
  against the Veyro tree, the Git index, or Git history, and `gitleaks git` / `--staged` was not
  invoked.
- The planted value is a fake GitHub-PAT-shaped string labelled `EXAMPLE_NOT_A_REAL_KEY`, joined
  from fragments at runtime so the test source holds no complete credential-shaped literal
  (`.claude/rules/infra/secrets.md` control 1). It is redacted (`--redact=100`) and the test asserts
  it appears in neither the report nor stdout/stderr.

## Drill results

Command: `backend/.venv/bin/python -m pytest tools/tests/test_gitleaks_qualification.py -q -p no:cacheprovider`
→ **6 passed in 0.15s**. `ruff check` and `ruff format --check` on the file: PASS.

| Check | Observed |
|---|---|
| Version pin | `gitleaks version` = `8.30.1` |
| Non-vacuity | both fixture files exist and are non-empty before any scan |
| Positive | planted dir → exit 42 (the test's `--exit-code`), exactly 1 finding, `RuleID` `github-pat`, file `planted_fixture.py`, value redacted |
| Clean negative | companion dir (env-var read, no literal) → exit 0, empty findings |
| Malformed config | unparseable TOML via `--config` → nonzero exit, not 0 and not 42, no findings (probed outside the repo: exit 1) |
| Missing target | nonexistent path → nonzero exit, not 0 and not 42, no findings (probed: exit 1) |

Using a non-default leak exit code (42) is what separates "leak found" from "gitleaks failed" —
a runtime error exits 1 and cannot be mistaken for a detection or a clean pass.

## Not claimed

- No stage 4 (independent source/provenance evaluation), stage 6, or stage 7; no CAP-009 row;
  `review_status` stays unassigned and `approved_by` empty. This is step-A material awaiting the
  single Opus `veyro-security-reviewer` determination.
- Not covered: upstream-license/release provenance, the pinned linux release-asset SHA-256 (CI
  executes the linux asset; the local arm64 binary is not a substitute), rule coverage beyond
  `github-pat`, archive/decode-depth behaviour, and any CI execution.
- The pre-existing unregistered-use gap (gitleaks previously run with `git --staged`, SCN-020
  notes) is unchanged and still belongs to BUG-057; not filed here.
- SCN-MOD001-029, 094, 134, 135, 136 and the 13 C06 scenarios remain **NOT EXECUTED**; no
  GOV-01-R03/R04 criterion is closed; no paid service, real secret, or member data involved.
