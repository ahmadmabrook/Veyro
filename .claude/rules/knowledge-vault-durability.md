---
scope: path
paths:
  - "knowledge/**"
  - "Notion:*"
---

# Rule: knowledge/ vault is durable authority, Notion is a mirror

- Any edit to project state (module status, decisions, defects, approvals) must land in `knowledge/` (Git-tracked) as the durable record.
- Notion may be updated for the same change, but only as a mirror — never as the first or only place a fact is recorded.
- If Notion and `knowledge/` ever disagree, `knowledge/` (and Git history) wins. Reconcile Notion to match, not the reverse.
- Never modify, rename, regenerate, or overwrite the 4 governing baseline artifacts recorded in `knowledge/00-System/PROJECT_INDEX.md`.
