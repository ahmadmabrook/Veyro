# R1-F12 / ADR-011 D8 namespace file/prune disclosure — deterministic inspection

Runner operation: `f7d2fd33-29c8-4915-8fac-03ddbe12811d`. This is one **inspection** outcome, not implementation, a review verdict, or scenario certification. The previous statement-level D8 increment remains verified and was not replayed. `ACTIVE_OPERATION.json` for that increment is `COMPLETED`, exit `0`; source/test SHA-256 are unchanged at `c9d8f177f302d5be897edce1c25c0b0003d9a06409e3afebc63b837c618b4777` and `a6397a9054bf8290c5673ecc44e93e45b27b1d6961a06abfddb13ee848a2579c`.

## Governing clause and inspected surface

ADR-011 D8 requires every run, including PASS, to disclose “files inspected, inert, pruned by reason, and at the modules-root.” D5.1 also assigns every path to a coverage bucket. Current `_scan_namespace_subtree` counts inert files in a non-discovered namespace for the D5 note but silently skips `__pycache__` and dot directories without sending by-reason prune counts to D8. `_d8_file_accounting_note` reports only the top-level D5 listing and the discovered-module/`_shared` scan walks; its residual expressly excludes the namespace probe. This leaves a literal, testable gap in full file/prune-surface disclosure; it does **not** show a scanner allow-list failure or warrant a verdict change.

## Reproducible local probe

Run from the repo root with `backend/.venv/bin/python` and `PYTHONPATH=tools/tests`:

```python
import test_validate_architecture_gates as t

def extra(root):
    ns = root / 'orphan'
    ns.mkdir()
    (ns / 'README.md').write_text('inert\n')
    (ns / '.cache').mkdir()
    (ns / '.cache' / 'skip.py').write_text('X = 1\n')
    (ns / '__pycache__').mkdir()
    (ns / '__pycache__' / 'skip.pyc').write_text('')

report = t._f12f_run(extra)
print(report.status, report.exit_code, report.codes())
print(t._f12f_counts(report))
for note in report.notes:
    if 'coverage reconciliation (ADR-011 D5)' in note:
        print(note)
```

Observed: `PASS 0 set()`; D8 counts `inspected=5`, `attempted=5`, `inert=0`, `root=1`, and **all four** reported top-level/scan-walk prune-by-reason counts `0`. The D5 coverage note on the same PASS reports `1 inert file(s) in inert-only namespace directory/ies`. The fixture also contains one namespace-probe `__pycache__` and one dot-directory pruned by that probe; D8 discloses neither count, only a prose residual saying such prunes are excluded. The D8 zeros are therefore scoped to its two named traversals, not complete file/prune-surface totals. The read-only probe made no source/test changes.

## Exact dependency

R1-F12 remains formally OPEN. A bounded code/test increment must reconcile namespace-probe inert and by-reason prune observations with D8's file accounting (including partial/ERROR labels and no double-counting across traversals), or a qualified ADR interpretation must explicitly decide that D8 excludes this surface. Then positive evidence-set reconciliation and combined independent round-2 assurance remain. No live CTE state-3 wiring under the U1/U2 B HOLD; no scenario PASS or review verdict is inferred.
