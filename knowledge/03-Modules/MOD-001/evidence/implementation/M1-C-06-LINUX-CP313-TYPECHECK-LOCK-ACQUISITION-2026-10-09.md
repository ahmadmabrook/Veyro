---
doc: M1-C-06-LINUX-CP313-TYPECHECK-LOCK-ACQUISITION
module: MOD-001
date: 2026-10-09
classification: MANDATORY_NOW — GOV-01-R04 type-check CI supply-chain prerequisite
status: LOCAL_LOCK_ACQUISITION_VERIFIED; no capability approval or CI result
---

# M1-C-06 — inert Linux cp313 wheel acquisition and additive lock

This is the corrected §3/§9 Step A of
`M1-C-06-MYPY-CI-LOCK-ARCHITECTURE-2026-10-09.md`, as amended by its §12 and
`M1-C-06-WHEEL-TAG-VERSION-ARCHITECTURE-2026-10-09.md`. The sole runner lease
was live; contract refresh was acknowledged; the M1-C-06 loop assessment was
`CLEAR`. This is local deterministic evidence only.

## Inputs and commands

- Python: `backend/.venv/bin/python` 3.14.5, pip 26.1.1, used only to
  cross-target download and to run the unchanged stdlib lock generator.
- Target: CPython 3.13, x86-64, `manylinux_2_17_x86_64`.
- Fresh constraints input directory:
  `/tmp/m1c06-typecheck-constraints.m88spumq`. Its only file had the five
  versions-only lines in the architecture record §3.4; no hashes or extras.
  It was not installed and is not an additional repository artifact.
- Fresh initially empty download directories:
  `/tmp/m1c06-typecheck-a.m8e89xq7` and
  `/tmp/m1c06-typecheck-b.9el4sbb9`, both outside the repository.
- For each directory, ran the architecture record §5 `pip download` command
  with `--only-binary=:all:`, the exact platform/ABI flags, explicit
  `https://pypi.org/simple`, cleared ambient index/constraint variables,
  `PIP_CONFIG_FILE=/dev/null`, and `-c` for the scratch constraints. The sole
  command-line requirement was `mypy==2.3.1`; dependency resolution remained
  enabled. Both independent invocations exited **0** and reported six wheels
  saved. No `pip install` was run.

## Acceptance checks

| Check | Observed result |
|---|---|
| AC-1 exits | A=0, B=0. |
| AC-2 filenames | Both directories contain exactly the six `.whl` names in the architecture record §6; no extra entry. |
| AC-3 binary/closure | No sdist, extracted file or seventh package. |
| AC-4 versions | `mypy` 2.3.1; `ast-serialize` 0.11.2; `librt` 0.15.0; `mypy-extensions` 1.1.0; `pathspec` 1.1.1; `typing-extensions` 4.16.0. Both name-set and version-set match the recorded CAP-012 closure. |
| AC-5 independent bytes | `sha256sum` over each six-file directory yielded byte-identical sorted manifests. Every filename/digest pair also matches the independently recorded PyPI metadata table in architecture §6. Manifest SHA-256: `7105f2d9fc552dbcf54bfafab3381b12eda778e07e2246b23a43f8ee2d0b1c22`. |
| AC-6 lock generator | `backend/.venv/bin/python -I tools/generate_requirements_lock.py generate <A> backend/requirements-typecheck-linux-x86_64-cp313.lock.txt` exited 0: six packages. Independent `check <B> <lock>` exited 0: every version and real-byte SHA-256 exact, no extra entries. |
| AC-7 unchanged inputs | Existing `backend/requirements-dev.lock.txt` remained SHA-256 `5b9383fe128cb1d7d8b8442c82fe305988980915140215f4a4f5e3adcbe2d698`; unchanged generator remained SHA-256 `c32436befe4204a0a89c1ace697e9b0bc1d4202ede2dda768cacc11830702b8c`. No wheel was extracted, imported, installed or executed. |

Generated additive files:

- `backend/requirements-typecheck-linux-x86_64-cp313.lock.txt` — SHA-256
  `2bb541f7b5ab832d3d63783a87b04ddbca7bc914f1ff81f662b429715bcb9725`.
- `backend/requirements-typecheck-linux-x86_64-cp313.wheels.sha256` —
  repository-resident copy of A's filename/hash manifest, SHA-256
  `7105f2d9fc552dbcf54bfafab3381b12eda778e07e2246b23a43f8ee2d0b1c22`.
  A and B's `/tmp` manifests compare identical. The repository file is
  currently **untracked**, not described here as committed.

The new lock's six versions match the existing macOS lock. Exactly the three
universal-wheel digests (`mypy-extensions`, `pathspec`, `typing-extensions`)
match; exactly the three compiled-wheel digests (`mypy`, `ast-serialize`,
`librt`) differ by platform, as expected. No digest was hand-transcribed into
the lock: the unchanged generator derived every digest from downloaded bytes.

## Boundary and next step

This closes only the **local inert-byte lock acquisition** substep. It does not
install or invoke mypy, approve CAP-012, execute CI, create a required status,
consume a reviewer, disposition any C06 scenario, or satisfy GOV-01-R04. The
CI workflow/target-scope and capability-assurance dependencies remain. R04
gate-2 F01-F14 stay 14/14 formally CLOSED; MOD-001 remains active.

Next legal C06 step: under the same lease, route ordinary CI/fixture authoring
to Sonnet after the material-boundary refresh, using this lock and the
architecture §4/§9 constraints. Do not claim a blocking gate from a local
lock check or a drill run.
