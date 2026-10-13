# SCN-MOD001-070 synthetic ordering-lint execution — 2026-10-04

Status: EXECUTED, pending fresh independent security/scenario review. This is not a scenario PASS, R04/A2 remediation, or module certification.

Source: `SCENARIOS.md` SCN-MOD001-070 and GOV-01-R06; the static lint is `tools/validate_migration_ordering.py`, separate from the GOV-01-R02 migration-safety harness reviewed for BUG-049.

At 2026-10-04T11:49Z the orchestrator ran `backend/.venv/bin/python tools/tests/test_validate_migration_ordering.py`: **6/6 passed**, including `test_contract_without_switch_fails_closed` and the valid four-phase control. It then invoked the real CLI against a throwaway synthetic directory with `expand`, `migrate`, `contract` records for one `change_id`: exit **1**, output contained `OUT_OF_ORDER_PHASE` and named `0003_contract.yaml`. Adding the missing `switch` predecessor and moving `contract` to fourth produced exit **0** and the CLI's PASS line. No real migration or data was touched; the fixture directory was removed automatically.

These two observed CLI outcomes distinguish the rejected destructive out-of-order contract from the accepted ordered control. The execution has not been independently reviewed and does not promote SCN-MOD001-070. DOM-002 round 5 remains interrupted and non-resumable; its 4+4 historical counters are unchanged. R04/ADR-010 A2 and SCN-067 remain separately blocked. No commit/push.

---

## Amendment 2026-10-04 (round-1 finding R1-6)

The round-1 independent review
(`../security/SCN070-MIGRATION-ORDERING-LINT-SECURITY-REVIEW-ROUND1-2026-10-04.md`)
reproduced all three factual claims above verbatim and found **no
misstatement** — but found the record not re-runnable from its own text:
it named no literal command, no fixture path, no fixture contents, and no
captured stdout, so its load-bearing "named `0003_contract.yaml`" claim
could only be checked by reconstructing the fixture by inference. It also
found the paragraph above reads as more decisive than the controls were.
Both are corrected here. The narrative above is left intact rather than
rewritten, so the amendment is visibly an amendment.

### What the original controls did NOT cover (stated plainly)

At the time of the 11:49Z execution above, **no** control touched either:

- `check_ordering`'s start-phase guard — the branch that rejects a
  destructive `contract` with *none* of its predecessors present, which is
  the acceptance clause's own broadest reading. Mutant M3 removed it and
  the suite stayed 6/6 green **and** the CLI negative above still exited 1.
- `main()`'s exit code — the very "exit **1**" this record cites as its
  proof. Mutant M5 changed `return 1` to `return 0`; the CLI printed
  `BLOCKED` and exited 0, suite still green.

Both gaps are now closed and both mutants are now killed — see
`SCN070-ROUND1-REMEDIATION-2026-10-04.md`. That remediation is itself
**not** independently reviewed, so SCN-MOD001-070 stays **EXECUTED — NOT
PROMOTED** pending a fresh round-2 review.

### Literal, re-runnable commands and verbatim stdout

Fixture built at `/tmp/scn070_r1fix/` (throwaway, outside the repo;
deleted at closeout). Every record is byte-identical except `phase` and
`change_id`; this is the exact content of
`/tmp/scn070_r1fix/negative/0003_contract.yaml`:

```
---
change_id: add_widget_column
phase: contract
owner: jane@example.com
lock_impact: none
rollback_strategy: drop the new object
validation_query: SELECT 1
---

Synthetic fixture record — not a real migration.
```

Fixture tree (all synthetic, no real schema or data):

```
/tmp/scn070_r1fix/negative/0001_expand.yaml        change_id=add_widget_column phase=expand
/tmp/scn070_r1fix/negative/0002_migrate.yaml       change_id=add_widget_column phase=migrate
/tmp/scn070_r1fix/negative/0003_contract.yaml      change_id=add_widget_column phase=contract
/tmp/scn070_r1fix/ordered/0001_expand.yaml         change_id=add_widget_column phase=expand
/tmp/scn070_r1fix/ordered/0002_migrate.yaml        change_id=add_widget_column phase=migrate
/tmp/scn070_r1fix/ordered/0003_switch.yaml         change_id=add_widget_column phase=switch
/tmp/scn070_r1fix/ordered/0004_contract.yaml       change_id=add_widget_column phase=contract
/tmp/scn070_r1fix/lone_contract/0001_contract.yaml change_id=add_widget_column phase=contract
```

**Control 1 — the recorded negative** (contract missing only `switch`):

```
$ backend/.venv/bin/python tools/validate_migration_ordering.py \
    --records-dir /tmp/scn070_r1fix/negative
======================================================================
MOD-001 DATABASE-MIGRATION ORDERING + RECORD VALIDATOR
======================================================================

Records dir checked: /tmp/scn070_r1fix/negative

BLOCKED: 1 problem(s) found:
  - 0003_contract.yaml: OUT_OF_ORDER_PHASE — change_id 'add_widget_column' jumps to 'contract' without a preceding 'switch'
EXIT=1
```

**Control 2 — the ordered control** (full 4 phases, correct order):

```
$ backend/.venv/bin/python tools/validate_migration_ordering.py \
    --records-dir /tmp/scn070_r1fix/ordered
======================================================================
MOD-001 DATABASE-MIGRATION ORDERING + RECORD VALIDATOR
======================================================================

Records dir checked: /tmp/scn070_r1fix/ordered

PASS — every migration record is complete and phase-ordered correctly (or no records exist yet).
EXIT=0
```

**Control 3 — added by the R1-1 remediation**, the clause's broadest
reading: a destructive `contract` with no predecessors at all. This path
had no control at all at 11:49Z:

```
$ backend/.venv/bin/python tools/validate_migration_ordering.py \
    --records-dir /tmp/scn070_r1fix/lone_contract
======================================================================
MOD-001 DATABASE-MIGRATION ORDERING + RECORD VALIDATOR
======================================================================

Records dir checked: /tmp/scn070_r1fix/lone_contract

BLOCKED: 1 problem(s) found:
  - 0001_contract.yaml: OUT_OF_ORDER_PHASE — change_id 'add_widget_column' starts at 'contract' but must start with 'expand'
EXIT=1
```

**Unit suite** (same command as the original 11:49Z run; the count rose
from 6 to 18 under the R1-1/R1-2/R1-3/R1-4 remediation):

```
$ backend/.venv/bin/python tools/tests/test_validate_migration_ordering.py
PASS — all 18 tests passed (discovered dynamically, not hand-listed).
EXIT=0
```

The original record's claim that "the fixture directory was removed
automatically" was true of the 11:49Z run's own `tempfile`-based fixture
but unverifiable from the text. This amendment's fixture is instead at a
named, stated path, and its deletion is recorded explicitly in the
remediation record's integrity section.
