# R2-N03 D7.4 — bounded local code/test verification

Recorded: 2026-10-06T10:06:43.192542+00:00
Runner operation: `ac0158c4-da43-4644-8481-4268a0b885e3` (sole continuous-runner lease); guarded Opus remediation exit 0, one dispatch. Classification: `MANDATORY_NOW` — the attested round-3 replacement review identifies R2-N03 as a P2 ADR-011 D7.4 blocker. This is not a new independent review or a finding closure.

## Exact snapshot

- Source `tools/validate_architecture_gates.py` SHA-256 `5eeac45f72ff613404c4b1918c9adbdd430675c0c26101d69725dd5b50c2c924` (before `b53808a2f7b8197578c2361d3553826193b28712e049a4e37b4e7d7abfaa9736`).
- Tests `tools/tests/test_validate_architecture_gates.py` SHA-256 `eb0088fa53a11d4111763ca967351fe64e535a83e41ff8af1f342b58f19f076b` (before `ee1f68b961843ea7eb34834abde5fa6603394da81818139668d01323dd8f6090`).
- Both files were untracked in the pre-existing worktree, so `git diff` does not represent their changes. The guarded operation tracked these exact paths and recorded material code/test checkpoints. No other file is claimed as this increment.

## D7.4 increment and deterministic checks

The scanner now exact-key deduplicates each of `violations`, `uninspectable`, and `unattributed` by `(code, subject, detail)`, retaining the first row for a key and sorting emitted rows by that same tuple. It does not modify the distinct coverage-violation dedup contract, scan counters, status, exit code, or FAIL-then-ERROR partition. Four added tests cover duplicate JOIN rows while retaining two per-position attributions, key ordering opposed to source order, error-class list ordering/dedup, and first-seen identity.

- Independent local `backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -p no:randomly -q`: **547 passed**.
- Independent local `backend/.venv/bin/ruff check tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py`: **PASS**.
- Independent local `backend/.venv/bin/python -m py_compile` on both files: **PASS**.
- Guarded child additionally reported focused D7.4 **4 passed**, full file **547 passed**, and domain scaffold contract **2 passed**. The child smoke run without the required manifest returned the existing `MODULE_DEPS_GATE_INPUT_INVALID` exit 2, not a gate verdict.

## Remaining governed dependency

The round-3 replacement verdict remains **BLOCKED**; R2-N03 is locally fixed only, with no independent material-change judgment. R2-N04/R1-F16 P2 contract/docstring corrections remain, as do explicit R1-F19 and R2-N05/N06 currency/projection directives. R1-F14 is formally **OPEN**. Its previous 22/22 replay capture pins source `b53808a2f7b8197578c2361d3553826193b28712e049a4e37b4e7d7abfaa9736`, so this source change makes that capture stale for the current snapshot. A new current-hash F14 capture/replay and independent evidence-currency disposition are needed after blocker remediation. SCN-MOD001-007 security/scenario assurance, the U1/U2 B HOLD (no live CTE/state-3 wiring), the 13/14 formal original-finding count, and review counters are unchanged.
