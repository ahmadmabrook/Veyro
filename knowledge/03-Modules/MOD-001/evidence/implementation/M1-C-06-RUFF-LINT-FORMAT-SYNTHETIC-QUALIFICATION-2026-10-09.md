---
doc: M1-C-06-RUFF-LINT-FORMAT-SYNTHETIC-QUALIFICATION
module: MOD-001
date: 2026-10-09
type: IMPLEMENTATION evidence (stage-5 synthetic qualification drill)
requirement: GOV-01-R03, GOV-01-R04, DC-19
related: CAP-010 (Ruff 0.16.9), BUG-057, M1-C-06-TEST-TOOL-SCOPE-DECISION-2026-10-09
operation: 4d61c4e4-a7b5-4998-bddb-ee352222e8fe
status: QUALIFIED EXTENSION RECORDED — NOT AN APPROVAL
---

# M1-C-06 — CAP-010 Ruff lint/format synthetic qualification drill

## 1. What this is and is not

This record closes one gap: `CAPABILITY_REGISTRY.md`'s CAP-010 row said "No dedicated
synthetic drill exists for the lint/format role", and the test-tool scope decision
(Decision 1, "Ruff lint/format") said that if only the `S` role was evidenced, lint/format
sat outside CAP-010's exact scope. It adds CAP-010's stage-5 positive/negative evidence for
the **lint** (`ruff check`) and **format** (`ruff format --check`) invocation modes, run
only against fresh synthetic files.

It is **not** an approval. CAP-010 stays `QUALIFIED — NOT APPROVED`; `approved_by` and
`approved_date` stay blank, `next_review_due` stays invalid/unset, `lifecycle_status` is
not ACTIVE, and the independent Opus `veyro-security-reviewer` determination (stage 4)
remains PENDING and is not dispatched here. No real-tree Ruff use, CI use, or reliance of
any kind is authorised by this record. No scenario is PASSed. No product code changed.
BUG-057 stays OPEN. pytest and mypy are untouched (not invoked in this drill).

## 2. Boundaries observed

- Tool: `/Users/ahmadmabrouk/Desktop/Veyro/backend/.venv/bin/ruff` (the installed macOS
  build), the only Ruff on this host (not on PATH). The Veyro tree was never an argument
  to Ruff; the only paths passed were files under a fresh `mktemp -d` directory in the OS
  temp area. No Git index/history, no CI, no Veyro source file was scanned or formatted.
- Fixtures were written fresh by `printf` (exact bytes, hashes below); non-sensitive,
  synthetic, no credentials or member data.
- `--isolated` (ignores all `ruff.toml` / `pyproject.toml` / user config) and `--no-cache`
  were used on every invocation; both flags are accepted by `check` and `format` in 0.16.9.
  Because `--isolated` drops the repo's pinned `line-length = 100`, `format` was given
  `--line-length 100` explicitly to mirror the F19 pinned setting. Lint used
  `--select E,F` (pycodestyle errors + Pyflakes), chosen explicitly because `--isolated`
  means rule selection comes only from the command line.
- Checks ran with `check` / `format --check` / `format --diff` only. No `--fix`, no
  `--unsafe-fixes`, no in-place `format`. Post-run hashes confirm the fixtures were not
  rewritten.
- pytest and mypy were not invoked. The runner is plain Bash plus `shasum`/`sed`/`wc`;
  assertions are exit-code and rule-code reads. The runner script and raw log lived in
  `/tmp` (outside the repo) and are summarised here; the temp fixture directory was
  removed (`CLEANUP_OK`).

## 3. Pin check

| Item | Observed |
|---|---|
| `ruff --version` | `ruff 0.16.9` (script hard-fails if not exactly this string: `PIN_CHECK=PASS`) |
| Installed binary SHA-256 (local observation only) | `8b799e53434b026a3e80aef658c06c3c98f9fb4cfc4eae379a16313936509e57` |

The registry pin (PyPI Linux x64 wheel SHA-256 `a21713e6…bc728`) is a different artifact.
The installed macOS binary is **not** the pinned Linux CI artifact, and this hash records
what was run; it does not verify the registry pin.

## 4. Fixtures (all non-empty before any run: `NONEMPTY_OK` x4)

| File | Bytes | SHA-256 | Role |
|---|---|---|---|
| `lint_bad.py` | 69 | `6108f65fd5a97aa72c47332830b68aa6840dfdaf5e15faa776acb73ee83aaa62` | lint positive (unused import + unused local); style already canonical |
| `lint_good.py` | 42 | `3251dbf18617cd67c47707cb9bd1611dbac212ff0ee9814a75b8ce1f34b85aad` | lint negative / corrected counterpart |
| `fmt_bad.py` | 85 | `e2f5ae8181b984b38ac541a40e54cb4932dd6f66d1d4ace1f5823b4e4bb44572` | format positive (spacing + quote style malformed); lint-clean |
| `fmt_good.py` | 86 | `07537d0bf4a1b67565f913069a2fbd5376dfdb0a13af241becad0b158eb00f7c` | format negative / corrected counterpart |

Contents:

```python
# lint_bad.py            # lint_good.py
import os                # def total(values):
                         #     return sum(values)
def total(values):
    unused = 1
    return sum(values)

# fmt_bad.py                                  # fmt_good.py
def total( values ):                          # def total(values):
    result = {'a':1,'b':2}                    #     result = {"a": 1, "b": 2}
    return sum( values )+result['a']          #     return sum(values) + result["a"]
```

(`lint_bad.py` has two blank lines after `import os`, as on disk.) The files isolate the
two roles: the lint fixture is already formatted, and the format fixture is lint-clean, so
each tool's verdict cannot be explained by the other's concern.

## 5. Commands (exact flag sets)

```
ruff check  --isolated --no-cache --select E,F --output-format concise <explicit file(s)>
ruff format --check --isolated --no-cache --line-length 100 <explicit file(s)>
ruff format --diff  --isolated --no-cache --line-length 100 <explicit file>
```

Every run used explicit file paths (never `.` and never a directory, except the deliberate
vacuous-path probes in section 7), run from inside the temp directory.

## 6. Expected vs observed

| # | Drill | Expected | Observed | Result |
|---|---|---|---|---|
| 1 | lint `lint_bad.py` (positive) | rc 1; finds F401 + F841 | rc 1; `F401` line 1 col 8, `F841` line 5 col 5, "Found 2 errors" | PASS |
| 2 | lint `lint_good.py` (corrected negative) | rc 0, no findings | rc 0, "All checks passed!" | PASS |
| 3 | format --check `fmt_bad.py` (positive) | rc 1; would reformat | rc 1; "File would be reformatted", "1 file would be reformatted"; `--diff` rc 1, 11 diff lines | PASS |
| 4 | format --check `fmt_good.py` (corrected negative) | rc 0 | rc 0, "1 file already formatted" | PASS |
| 5 | cross-check: lint `fmt_bad.py`, `fmt_good.py` | rc 0 (lint blind to style) | rc 0, rc 0 | PASS |
| 6 | cross-check: format --check `lint_bad.py`, `lint_good.py` | rc 0 (format blind to lint) | rc 0, rc 0 | PASS |
| 7 | multi-file lint (4 explicit paths) | rc 1 from `lint_bad.py` only | rc 1; only the two `lint_bad.py` findings | PASS |
| 8 | multi-file format --check (4 explicit paths) | rc 1; exactly 1 file flagged | rc 1; "1 file would be reformatted, 3 files already formatted" | PASS |
| 9 | non-empty explicit paths | every fixture non-zero size before running | `NONEMPTY_OK` x4 | PASS |
| 10 | pinned version | exactly `ruff 0.16.9` | `ruff 0.16.9`, `PIN_CHECK=PASS` | PASS |
| 11 | check mode does not mutate inputs | post-run hashes equal section 4 | all four identical | PASS |

Sanitized return-code summary: lint `1,0,0,0` for `lint_bad, lint_good, fmt_bad, fmt_good`;
format --check `0,0,1,0` for the same order. Output above was sanitised by replacing the
temp root with `<TMP>`; only rule codes, file names and counts are relied on.

Overall: 11/11 expected outcomes observed. This is a pass of the stage-5 mechanical
positive/negative test for the lint and format roles, to be judged by the pending
independent Opus determination, not by this record.

## 7. Tool limitations (disclosed; not cured by this drill)

- **Vacuous pass on empty path set.** `ruff check <emptydir>` and `ruff format --check
  <emptydir>` both return rc 0 with only a "No Python files found" warning. A gate must
  assert the file set is non-empty before trusting rc 0 (drill row 9 does this itself).
- **Missing path behaves inconsistently between modes.** `ruff check` on a nonexistent file
  returns rc 1 with `E902`; `ruff format --check` returns rc 2 (io error). A wrapper must
  treat rc 2 as an error, not a style verdict, and not conflate it with rc 1.
- **`format --check` rc 1 means "would reformat"** and is indistinguishable by code alone
  from other rc 1 causes; the message text, or `--diff`, is what separates them.
- **Isolation drops project config.** `--isolated` ignores the repo's `ruff.toml`, so the
  repo's real rule selection and `line-length` are not exercised here (line length was
  passed by hand). The behaviour of Veyro's own config is not evidenced by this drill.
- **Rule coverage is two fixtures deep.** Only `E`/`F` codes `F401`, `F841` and a basic
  quote/spacing format difference were demonstrated; this is not a statement about Ruff
  rule coverage or formatter behaviour in general, nor about the cleanliness of the Veyro
  tree, which stays unknown and unclaimed.
- **Binary mismatch.** Drill ran on the installed macOS build, not the pinned Linux
  wheel. The pin is not enforced in any CI. No upstream signature or attestation verified.
- **`S` role unchanged.** The earlier `S` drill (`tools/tests/test_sast_ruff_qualification.py`,
  4/4) is not re-run or modified here; this record neither widens nor narrows it.

## 8. Effect on CAP-010

CAP-010's drafted scope item (a) (lint and `format --check` over Veyro Python) now has a
dedicated synthetic drill; the registry/manifest sentences claiming otherwise are updated
to cite this record. Scope text, `QUALIFIED — NOT APPROVED`, blank
`approved_by`/`approved_date`, invalid `next_review_due`, and the no
ACTIVE / real-tree / CI reliance rule are unchanged. Pre-existing unregistered Ruff use
remains a disclosed gap under BUG-057 and is not retroactively approved. This record adds
no review entitlement and does not dispatch a review.
