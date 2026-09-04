---
doc: EXTERNAL_GATES
status: LIVE
updated: 2026-09-04 (created, Phase 5 F5-012)
---

# External Gates (index)

EIP Appendix D-named durable file. Individual gate records live as
separate files under `knowledge/03-ExternalGates/` (not inlined here) —
this file is the index `SESSION_BOOTSTRAP.md` step 3 points sessions to.

| Gate | Status | File |
|---|---|---|
| EIP internal status contradiction (front matter vs §21.1 body) | **BLOCKED: OWNER_APPROVAL_REQUIRED** for Phase 10 certification; non-blocking for Phases 4-9 | `knowledge/03-ExternalGates/EIP_STATUS_CONTRADICTION.md` |

Any session finding a new external gate (an owner-reserved decision point,
an unresolved contradiction in governing baselines, anything requiring
input this project cannot supply itself) must add a file under
`03-ExternalGates/` and a row here in the same commit.
