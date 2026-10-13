# GATE2-R1-D6 one-pass pure CTE scopes — bounded verification (2026-10-05)

**Scope:** MOD-001 / GOV-01-R04 gate 2; fixture-scoped; real-tree domain ownership DEFERRED (ADR-011). Covered child scenarios SCN-MOD001-006/007/095/096 remain NOT EXECUTED and unpromoted. This is local implementation evidence, not independent assurance or certification.

## Change and route

Named veyro-lead/Opus qualification `GATE2-R1-D6-CTE-STATEMENT-SCOPE-LEAD-QUALIFICATION-2026-10-05.md` BLOCKED live wiring and selected one pure one-pass helper as the next bounded increment. A foreground Task routed implementation to registered `veyro-implementer`, requested `sonnet`; matching child transcript `/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/6466c557-1c9e-4626-bc42-08720e09ec6d/subagents/agent-aa0039f87472127ba.jsonl` (`agentId aa0039f87472127ba`, sidechain) independently passed `mr_verify.py` **56/56 `claude-sonnet-5` turns**. Guarded operation `7e85e9d3-f3ff-4e73-8631-3164182a0935` completed with exit 0 and two verified material checkpoints, one per changed file. No second Claude phase was launched.

`_cte_scopes(text)` now emits segment text and local binding sets from one lexical cursor. It shares the existing quote/comment/dollar skips and `_parse_cte_binding_list` cursor jump with depth-zero semicolon cuts. There is no `_split_sql_statements` function and no second `_collect_cte_names(segment)` walk. `tools/validate_architecture_gates.py` and its focused test file are the only product files in this increment; both were pre-existing untracked WIP and remain uncommitted. `_scan_sql_text` has no `_cte_scopes` call, so state 3 remains unwired.

## Deterministic verification

- Focused gate tool suite: **214/214 PASS** (200 prior + 14 new direct scope tests), observed 2.1954s.
- Ruff on both files: **PASS**, observed 0.0636s.
- AST confirmed helper present, no splitter, no live scanner reference. Direct non-terminator semicolon probe declined both segment binding sets; `py_compile` PASS, observed 0.1417s.
- Governing baseline hashes: **4/4 MATCH**, observed 0.0777s before dispatch.
- Source SHA-256: `3e05a5108061cd1bf56a27a6e9d1896df3793ec6b9df919664a7cd692d16ed5d`. Test SHA-256: `89c3b9853dd3f809918d26fc4f6b71f6bed401f502f76f33de9e57e8391e6bdc`.
- Previous independently verified source/test hashes were `f3be4466b437b1cc47e3ce4bf7fb0ad2dfdfa87475eb105450934570b4068e9b` / `70357b8d8c4273a836332bbdb8cb39c153a5b18e01aa7f94421af8ee889c6a88`.

## Open gate

This pure helper does **not** prove that a lexer-only state-3 recognizer cannot create an absolute false clean relative to the current empty-set live baseline. Named-lead BLOCKED disposition and the qualification hold remain. The lead called for repository-resident T1–T9/property corpus and then a fresh ADR-011 D3.2/D9 risk judgment before any `_scan_sql_text` wiring. Round-1 code review remains BLOCKED P0=1/P1=7/P2=6/P3=7; review round and scenario counters did not advance. No scenario PASS is inferred from 214 passing helper tests.
