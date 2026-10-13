# R1-F07 SQL decode increment — local verification (2026-10-05)

- Work unit: GOV-01-R04 gate 2; operation `ff56c8f9-25a9-4896-aa4f-e20a0b4ed5b4`.
- Prior Python decode increment preserved. This increment routed `.sql` source reads through the shared fail-closed read/decode helper. A non-UTF-8 SQL fixture now yields `MODULE_DEPS_GATE_INPUT_INVALID`, GateReport ERROR and exit 2 in text and `--json`; a valid UTF-8 non-ASCII SQL control remains PASS and appears in `checked`.
- Guarded Claude operation: COMPLETED, exit 0, material code and test checkpoints recorded. Focused file: 268 passed (worker). Independent local tools suite: **341 passed**; Ruff: PASS; `py_compile`: PASS.
- Verified source SHA-256: `d27fe7f9aefe52dd3731cfbaacd567187d9c45440f38402ec4441b18ca9753a8`; tests SHA-256: `2d77a72667e1353bfccaabad20b258ad1989aa09f0f2b9c35c051373009ec7b6`.
- Scope: fixture-scoped; real-tree domain ownership **DEFERRED**. No CTE state-3 wiring, scenario promotion, combined review, or new assurance verdict.
- Residual: ADR-011 D7.3 also requires every read/decode path to use one conversion helper and an outermost fail-closed `main` funnel with minimal text/JSON emission for unexpected exceptions. The ADR/owner-approval reads in `resolve_approval` remain bare `read_text`; no outermost funnel was added in this bounded increment. R1-F07 remains formally OPEN pending that separate bounded code/test verification, then combined independent round-2 assurance.
