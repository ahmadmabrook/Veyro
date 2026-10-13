# R1-F12 / ADR-011 D8 positive evidence-set reconciliation

Runner operation `4bbbb24c-3c9b-4ed9-b9a2-e3a03bd68759`; deterministic inspection only. The runner contract was refreshed and acknowledged at its required boundary. No implementation or review dispatch was made.

The original `GATE2-VERDICT-C-SCENARIO-EVIDENCE-2026-10-05.md` predates the D8 counters (it has no `D8` disclosure). Its fixture-scoped PASS claims cannot alone establish the later ADR-011 D8 non-vacuity obligation. The `/tmp/gate2-fixtures` positive trees referenced there still exist. Replaying their current gate 2 CLI with `--json` gave:

| Existing positive fixture | Exit / status | D8 SQL subjects | D3.2 own table references | Resolved / approved cross-module edges | Inspected files |
|---|---:|---:|---:|---:|---:|
| `/tmp/gate2-fixtures/positive` (`membership` own SQL) | 0 / PASS | 2 | 2 | 0 / 0 | 10 |
| `/tmp/gate2-fixtures/pairs/com01_com03/positive` (permitted direction) | 0 / PASS | 0 | 0 | 1 / 1 | 6 |

Invocation shape for each row: `backend/.venv/bin/python tools/validate_architecture_gates.py --gate module-deps --modules-dir <fixture>/app/modules --module-manifest <fixture>/<manifest>.json --json`. The manifests are `manifest-positive.json` for the first row and `manifest.json` for the second. Both returned an empty violation list. The counters show distinct, non-vacuous positive controls for the SQL ownership and approved-import paths; neither PASS is misrepresented as exercising the other path. The current D8 notes also disclose zero state-3 CTE attributions as *structurally unreachable*, not as a tested absence of CTE use, and delimit file/prune counts to the observed traversals.

This reconciles the **positive evidence-set obligation for R1-F12 at the local technical level**, alongside the previously verified D8 counter increments. It does not update the old scenario artifact, prove real-tree ownership, certify SCN-MOD001-006/095, establish universal scanner completeness, or close the formal round-1 finding. The qualified U1/U2 B HOLD remains in force: live CTE state-3 wiring is forbidden. R1-F12 remains formally OPEN pending the combined independent round-2 assurance and any resulting disposition. No full review is opened in this increment.
