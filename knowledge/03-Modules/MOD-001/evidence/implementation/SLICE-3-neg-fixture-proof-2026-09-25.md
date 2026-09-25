---
doc: MOD-001_IMPLEMENTATION_SLICE_3_NEG_FIXTURE_PROOF
status: LIVE
module: MOD-001
updated: 2026-09-25
---

# MOD-001 implementation slice 3 — GOV-01-R01 NEG-evidence attempt (deliberately-broken fixture)

## What this slice is

Per `REQUIREMENTS.md` GOV-01-R01's evidence obligation, this slice
authored the four pyramid-layer scaffold-liveness fixtures (HP evidence)
and attempted to produce the companion NEG evidence: proof that the
pytest harness "correctly fails/blocks on a broken fixture." This
document records the NEG-evidence attempt honestly, per the governing
instruction not to claim PASS for anything not actually observed.

## HP fixtures created (for traceability, not this doc's main subject)

- `backend/tests/unit/test_scaffold_live.py`
- `backend/tests/component/test_scaffold_live.py`
- `backend/tests/integration/test_scaffold_live.py`
- `backend/tests/contract/test_scaffold_live.py`

Each contains one trivial passing assertion (`assert 1 + 1 == 2`) and a
one-line docstring marking it as a scaffold-liveness proof, not product
test content. **These have not been executed either**, for the identical
guard-scope reason documented below — see "Related residual" at the end.

## NEG-evidence attempt

### Step 1 — temporary broken fixture

Wrote a temporary file, never under `backend/tests/` and never
git-tracked, to the session scratch directory:

`/private/tmp/claude-501/-Users-ahmadmabrouk-Desktop-Veyro/1a574947-e9c5-4023-90af-c5b073540fb8/scratchpad/test_deliberately_broken.py`

containing exactly:

```python
def test_deliberately_broken():
    assert 1 == 2
```

### Step 2 — attempted execution

Four distinct attempts were made to invoke pytest via `python3`, to
confirm the denial was structural (any `python3` invocation of this
shape) rather than an artifact of one specific flag combination:

1. `python3 -m pytest --version`
2. `python3 -m pytest backend/tests`
3. `python3 --version`
4. `python3 -m pytest /private/tmp/claude-501/-Users-ahmadmabrouk-Desktop-Veyro/1a574947-e9c5-4023-90af-c5b073540fb8/scratchpad/test_deliberately_broken.py -v`

**Every attempt was denied, verbatim identical text each time:**

```
PreToolUse:Bash hook error: BLOCKED: DISALLOWED_FLAG_OR_SHAPE — python3 did not match its allowlisted read-only shape
```

### Root cause (confirmed by direct code inspection, `.claude/security/bash_guard.py`)

`_READONLY_DISPATCH["python3"]` routes to `_python_readonly`, which only
`_allow`s a `python3 <script>` invocation when the script path is one of
7 SHA-256-pinned entries in `_ALLOWED_PYTHON_SCRIPTS` (lines 538-553).
`pytest` is not a recognized command family at all (absent from
`_READONLY_DISPATCH`), and no form of `python3 -m pytest ...` can match
`_python_readonly`'s single-script-path allowlist shape regardless of
target file. This is a **structural** denial, not specific to the
deliberately-broken fixture — the same denial fires for a legitimate
`python3 -m pytest --version` probe with no fixture involved at all.

### Step 3 — cleanup attempt

Per instruction, attempted to delete the temporary broken fixture after
the run attempts:

- `rm <path>` → `BLOCKED: UNKNOWN_COMMAND — 'rm' is not an allowlisted command`
- `unlink <path>` → `BLOCKED: UNKNOWN_COMMAND — 'unlink' is not an allowlisted command`

Both denied by the same command-allowlist restriction (`rm`/`unlink` are
simply not in the guard's Class A/B command families at all — this is
not CAP-007-specific, the guard has no delete primitive whatsoever).
Per the governing instruction not to fight or route around a guard
denial (and specifically not to use `dangerouslyDisableSandbox` to
bypass it — that would be exactly the workaround this task asked not to
attempt), no further deletion attempt was made.

**Disposition of the temp file:** it remains at the path above, inside
the session-specific scratch directory. This directory is explicitly
outside the project and outside git per the environment's own
description ("isolated from the project"); it was never written under
`backend/tests/` or any other git-tracked path, and `git status` (run
separately as part of normal repo hygiene) does not show it. The
"never lands in backend/tests/ or anywhere git-tracked" requirement is
satisfied by construction (it was never written there), independent of
whether the file could also be actively deleted.

## Honest verdict

**NEG evidence was NOT obtained. This is BLOCKED, not PASS.**

No pytest execution — against the deliberately-broken fixture, or
against anything else — was actually observed in this environment. The
guard denies the invocation shape before pytest ever runs, so there is
no captured pytest failure output to point to. What is claimed: four
independent denial attempts, all returning identical, verbatim guard
text, confirming this is a structural gap in `bash_guard.py`'s
`python3` allowlist (which recognizes 7 pinned validator scripts and no
general-purpose interpreter or test-runner invocation), not a fixable
flag/argument mistake on this session's part. What is NOT claimed: that
pytest works, that it fails correctly on broken fixtures, or that the 4
HP scaffold-liveness files pass when actually run — none of that was
observed, only authored and hand-traced.

## Related residual

This is the same class of gap disclosed in
`evidence/implementation/SLICE-1-baseline-binding-validator-2026-09-19.md`
and `SLICE-2-capability-manifest-validator-2026-09-19.md` (both: "This
script has not been executed... `.claude/security/bash_guard.py`'s
`python3` family only executes 7 pre-existing, SHA-256-pinned scripts"),
and matches `BUG-025`'s disclosed residual pattern in
`knowledge/05-QA/BUG_REGISTRY.md` line 39 ("not yet on `bash_guard.py`'s
trusted-script allowlist, so this session cannot invoke it live —
confirmed by direct attempt (`DISALLOWED_FLAG_OR_SHAPE`); runnable by
the owner/a human terminal today"). No new bug is filed here for the
same recurring, already-tracked architectural gap; this document exists
so GOV-01-R01's NEG-evidence obligation has an honest, dated record
rather than a fabricated pass.

## Traceability

- Requirement: `REQUIREMENTS.md` GOV-01-R01, evidence obligation
  ("a passing run of each layer's harness... proof that harness
  correctly fails/blocks on a broken fixture").
- Scenario: `SCENARIOS.md` Group A (SCN-MOD001-001/002/003 cover the
  repository-skeleton NEG/VAL shape at the bootstrap-script level; this
  document covers the pytest-harness-level NEG evidence GOV-01-R01's own
  evidence-obligations text separately calls for).
- Guard: `.claude/security/bash_guard.py`, `_python_readonly` /
  `_ALLOWED_PYTHON_SCRIPTS` (lines 538-591).
