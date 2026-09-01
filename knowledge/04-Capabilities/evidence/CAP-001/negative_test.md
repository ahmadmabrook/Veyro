---
capability: CAP-001 Notion MCP
test: negative
date: 2026-08-31
---

# CAP-001 Negative Test

Steps: attempted to create a page in the Modules database with `Status: "NotARealStatusValue_XYZ"` (not a valid select option).

Result: **PASS**. Notion API rejected the write with `400 validation_error`, exact reason given ("Invalid select value ... must be one of ..."), no row created, no partial/corrupted write. Fail-safe, not silent no-op.

Combined with `positive_test.md` (PASS): CAP-001 qualification complete. Registry updated to `APPROVED`.
