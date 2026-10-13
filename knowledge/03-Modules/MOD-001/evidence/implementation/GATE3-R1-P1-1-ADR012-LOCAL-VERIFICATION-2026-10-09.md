# Gate-3 R1 P1-1 ADR-012 local verification (not independent assurance)

- Observed: 2026-10-09T00:34:31.029796+00:00; sole runner operation `5c113e83-2074-4bbc-be56-8b5ca1f178d7`. Guarded implementation `COMPLETED`/exit 0; no second writer or reviewer, no commit/push, no scenario promotion.
- Classification: `MANDATORY_NOW`. TSD §24.1 gate 3 / Required SCN-MOD001-019 and independent gate-3 R1 P1-1 require unregistered code-referenced events not to yield green. The prior dynamic-callee and cross-file re-export false PASS were concrete P1 blockers, legally non-deferable. Decided input contract: `knowledge/04-Decisions/ADR-012-gate3-event-emitter-static-input-contract.md`.
- Changed only `tools/validate_architecture_gates.py`, `tools/tests/test_validate_architecture_gates.py` and `knowledge/03-Modules/MOD-001/IMPLEMENTATION.md` row 3. Workflow, scan scope, other rows, gate-2 U1/U2 B HOLD and all review counters unchanged. The two validator files remain untracked from pre-existing work; this operation did not stage/commit them.

## Deterministic execution

- `backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q` with `PYTHONDONTWRITEBYTECODE=1`: **551/551 PASS** (orchestrator rerun after worker completion).
- Scoped Ruff: **PASS**; compileall on the two Python files: **PASS**; `git diff --check`: **PASS**; governing baseline verifier: **4/4 MATCH**.
- Disposable, secret-free fixture replay (not in repository): (1) legitimate canonical call plus `a.py` `from veyro.bus import emit_event as publish` and `b.py` re-exported `publish("veyro.missing")` → ERROR/exit 2, `EVENT_EMITTER_UNINSPECTABLE` at `a.py:1`, legitimate `checked` retained; (2) `publish = identity(emit_event); publish("veyro.missing")` beside legitimate call → ERROR/exit 2, `EVENT_EMITTER_UNINSPECTABLE`; (3) `emit_event("veyro.missing"); publish = emit_event` beside legitimate call → ERROR/exit 2 with both `UNREGISTERED_EVENT_CONTRACT` and `EVENT_EMITTER_UNINSPECTABLE` retained.
- Real repository tree: event-contract gate remains `INCONCLUSIVE`/`EVENT_CONTRACT_GATE_VACUOUS`/exit 2 because no live emitter reference exists; this is neither PASS nor gate-3 certification.

## ADR-012 step-5 disposable mutants

Each single mutation was made in a fresh disposable `/tmp` copy of validator+tests, not in this repository. `pytest -k event_contract -x -q` exited 1 for **7/7** independently; unmodified same file passed 551/551. These are targeted local regression checks, not an independent review.

| Mutant | Killed by observed assertion |
| --- | --- |
| D2 remove Load filter | escaped-emitter test: canonical Store target wrongly ERROR |
| D2a filter Name only, not Attribute | escaped-emitter test: Attribute Store wrongly ERROR |
| D3a treat NamedExpr as reference/callee | alias test: walrus double-counted/extra contract finding |
| D4 disable import-rename ERROR | alias test: renamed import erroneously accepted |
| D5 disable exact-string dynamic reference | escaped-emitter test: dynamic string reference erroneously accepted |
| D6 downgrade escape report ERROR→FAIL | alias test: status/exit polarity wrong |
| D8 skip non-callee per-reference accounting, leave valid direct call | alias test: existing escape denial lost (vacuity alone insufficient) |

## Snapshot and disposition

| File | SHA-256 |
| --- | --- |
| `tools/validate_architecture_gates.py` | `c2f06b0ee9659fe4a4e9bcb591ed3e832801c8747c19a39f7387b0d73f886aa1` |
| `tools/tests/test_validate_architecture_gates.py` | `61b0da661fdeb539596fc5db175d779a7c317878b77933a901afb70c68c65f0e` |
| `knowledge/03-Modules/MOD-001/IMPLEMENTATION.md` | `9965dc175d3fd2f39d9263c94f9fd871967860585e4f1dbe6165d2d8872e2118` |

P1-1 is **LOCALLY_FIXED/DETERMINISTICALLY_VERIFIED, AWAITING REQUIRED INDEPENDENT ASSURANCE**. This is not formal gate-3 closure: the one owner-authorized qualified gate-3 review was consumed by its BLOCKED P1=2/P2=4 report on an earlier snapshot; there is no automatic retry. P1-2 and P2-1..P2-4 remain open; SCN-008/019/130 and SCN-020 are not promoted; MOD-001 mandatory exit remains 0/8. R04 gate-2 R1-F01..F14 remain 14/14 formally CLOSED. At the material code/governing-row boundary, contract refresh is required before the next distinct P1-2 action.
