---
doc: EXTERNAL_GATES
status: LIVE
updated: 2026-09-13 (Phase 10 — EXT-01 CLOSED via owner adjudication OWN-002)
---

# External Gates (index)

EIP Appendix D-named durable file: "Durable mirror of §22.0: EXT IDs, gate
class(es), explicit Gated capability, owner, blocking modules/actions/waves,
evidence, status and last verification. Read every session; Notion is
re-synchronized from this file when divergent."

Detail records for each row live as separate files under
`knowledge/00-System/external-gates-evidence/` — this file is the index
`SESSION_BOOTSTRAP.md` step 3 points sessions to.

§22.0 itself governs product release-wave gates (fiscal integration, real
member/biometric data, physical hardware commissioning, production
capacity, etc.) — none of those apply yet, since MOD-000 is the
control-plane bootstrap and no product module has started. The one row
below is a control-plane-level gate (a governing-baseline internal
contradiction requiring owner adjudication), tracked using the same
schema for consistency.

| EXT ID | Gate class | Gated capability | Owner | Blocks | Evidence | Status | Last verified |
|---|---|---|---|---|---|---|---|
| EXT-01 | Governing-baseline integrity | N/A (not a product capability — the EIP's own front matter and §21.1 body self-contradict on the EIP's approval status) | Ahmad Mabrouk | Was: Phase 10 certification only (non-blocking for Phases 1-9) | `knowledge/00-System/external-gates-evidence/EIP_STATUS_CONTRADICTION.md`, `knowledge/00-System/OWNER_APPROVALS.md` (OWN-002) | **CLOSED (2026-09-13)** — owner adjudicated in favor of the front matter; §21.1's "candidate" language ruled a drafting inconsistency in the source document, not a live blocker | 2026-09-13 |

Any session finding a new external gate (an owner-reserved decision point,
an unresolved contradiction in governing baselines, a product release-wave
gate under §22.0, anything requiring input this project cannot supply
itself) must add a file under `knowledge/00-System/external-gates-evidence/`
and a row here (with the next `EXT-<NN>` ID) in the same commit.
