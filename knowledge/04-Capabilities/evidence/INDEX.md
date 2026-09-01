---
doc: CAPABILITY_EVIDENCE_INDEX
status: LIVE
updated: 2026-08-31
---

# Capability Evidence Index

One subfolder per capability id (`CAP-NNN/`), containing `positive_test.md` and `negative_test.md` once run. Empty until qualification drill executes.

| capability id | positive test | negative test | status |
|---|---|---|---|
| CAP-001 Notion MCP | PASS (`CAP-001/positive_test.md`) | PASS (`CAP-001/negative_test.md`) | **APPROVED** |
| CAP-002 TestSprite CLI | PASS, offline scope (`CAP-002/positive_test.md`) | PASS (`CAP-002/negative_test.md`) | **APPROVED (offline scope only)** — live execution BLOCKED pending owner credit-spend approval, see `SCOPE_NOTE.md` |

Update this table, and add the corresponding `CAP-NNN/` folder with test evidence, whenever a qualification test runs. Cross-link from `CAPABILITY_REGISTRY.md`'s `evidence` column.
