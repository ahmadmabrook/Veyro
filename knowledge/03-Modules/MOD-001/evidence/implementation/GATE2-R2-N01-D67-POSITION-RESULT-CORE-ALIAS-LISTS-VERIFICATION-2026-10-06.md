# R2-N01 / R1-F01 — bounded D6.7.2 position-result core and FROM alias lists

Operation `b29ea7ad-25fd-4068-a74c-bbe16da49323`, guarded Sonnet implementation, completed exit 0. One bounded code/test increment; no review, scenario certification, domain ownership, or live CTE state-3 change. U1/U2 B HOLD remains. R1-F01 and R2-N01 are formally OPEN; round 2 remains BLOCKED.

## Changed surface and local proof

- `tools/validate_architecture_gates.py`: introduced a per-recognized-position result carrying signal/offset and exactly one of identifier or unresolved reason. The live scanner consumes this stream; an unresolved position refuses `MODULE_DEPS_SOURCE_UNINSPECTABLE` even after another identifier resolved. FROM comma continuations now step across bare and `AS` aliases without treating JOIN `USING (id)` as a table signal. This is a bounded core, not proof that the signal vocabulary and all list forms are complete.
- `tools/tests/test_validate_architecture_gates.py`: seven new focused tests and position-stream/mutation controls. The guarded operation ran mutation drills and restored the source after each: removing alias continuation, greedily consuming aliases across clauses, removing the position either/or invariant, and reinstating the statement-level partial-extraction guard were killed. One attempted alternate mutant was behaviorally equivalent and is not counted as a kill.
- Independent post-exit run: `487 passed` in the focused gate file; Ruff on both files PASS; compileall on both files PASS. The implementer also ran the tools-plus-scaffold-contract selection (`562 passed`), and direct-run mode (`487 passed`).
- Final source SHA-256 `6cc82d76f02812344c85d8376b134b6031ac8157d6ad4d69aeff49fbbb610ea0`; test SHA-256 `d56e8c6c6ebb578e05e94345c817e2a79c22132543b2f15f579c4cde5429312a`.

Independent end-to-end fixture rerun through `_f12b_run` and the emitted D8 counts:

| Case | Surface | Status/exit | Diagnostic count | D8 own / other / unattributed |
| --- | --- | --- | --- | --- |
| N8 bare alias cross-domain | `.py`, `.sql` | FAIL/1 each | 1 `CROSS_DOMAIN_SQL_IMPORT` each | 1 / 1 / 0 |
| N9 AS alias cross-domain | `.py`, `.sql` | FAIL/1 each | 1 `CROSS_DOMAIN_SQL_IMPORT` each | 1 / 1 / 0 |
| P2 plain FROM list | `.sql` | FAIL/1 | 1 cross-domain | 1 / 1 / 0 |
| Own-table bare-alias list | `.sql` | PASS/0 | none | 2 / 0 / 0 |
| Unresolved second position after clean first | `.sql` | ERROR/2 | 1 `MODULE_DEPS_SOURCE_UNINSPECTABLE` | 0 / 0 / 0 (early refusal; not a completeness proof) |
| N3 REFERENCES; N4 DELETE USING | `.sql` | FAIL/1 each | 1 cross-domain each | 1 / 1 / 0 |
| P4 JOIN USING (id) | `.sql` | PASS/0 | none | 2 / 0 / 0 |
| N6 ONLY | `.sql` | ERROR/2 | 1 `MODULE_DEPS_TABLE_UNATTRIBUTED` | 1 / 0 / 1 — **still wrong attribution** |

## Remaining exact dependency

D6.7.2's record stream is now present for recognized signals and the N8/N9 alias-list false-PASS is locally fixed. R1-F01 is **not closed**: D6.7.3 list continuation for JOIN/INTO/UPDATE/TABLE/USING/REFERENCES/ONLY and correct ONLY attribution remain; the full N1–N10/P1–P5/M-E1–M-E7 corpus has not been completed; D6.7.5's unconditional D8 “counts are complete for this run” wording remains false when positions are unrecognized; the module docstring at `tools/validate_architecture_gates.py:249-257` still claims unowned identifiers are merely noted, contrary to D3.2; independent assurance and scenario gates remain unpassed. The real-tree module-deps command cannot certify these fixture-scoped claims while `contracts/modules/ownership.json` is absent under the owner-reserved domain-binding gate. No owner-bound decision is inferred from this.

Next bounded increment should address one structurally related remaining D6.7.3 position family or D6.7.5 truthful disclosure after a refreshed checkpoint; no full review while code/test blockers remain. Do not replay N8/N9 or infer R2 PASS.
