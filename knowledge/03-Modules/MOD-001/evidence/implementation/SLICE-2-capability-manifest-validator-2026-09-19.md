---
doc: MOD-001_IMPLEMENTATION_SLICE_2
status: LIVE
module: MOD-001
updated: 2026-09-19
---

# MOD-001 implementation slice 2 — `tools/validate_capability_manifest.py`

## What this slice is

The second MOD-001 implementation slice, per `REQUIREMENTS.md` §3's
"Capability-governance validation gates" obligation: "Validate
`.claude/agents`/`.claude/rules`/`.claude/skills`/`module-capabilities.yaml`;
reject cyclic capability dependencies, overdue lifecycle reviews,
manifests missing mandatory privileged-surface Rules... Reuses MOD-000's
`validate_capabilities.py`/`CAPABILITY_REGISTRY.md` pattern — extend,
don't duplicate."

**Why this slice second:** it lives under `tools/**` (known-infrastructure
path, unaffected by `BUG-035`'s backend/infra qualification block),
extends a proven MOD-000 pattern, and directly benefits from this same
session's own RULE-001..009 registration work (the tool's first real
test case is validating the exact manifest this session just edited).

## Governing requirement

`REQUIREMENTS.md` §3, "Capability-governance validation gates" row, tied
to GOV-01-R04.

## Routing

`veyro-implementer` (Sonnet, explicit `model: sonnet`) — routine
implementation under `tools/**`, not a critical slice, not backend/infra
surface work. Matches `MODEL_ROUTE.md`'s existing routing table, same as
slice 1.

## Deliverable

`tools/validate_capability_manifest.py`. Generalizes
`knowledge/00-System/validate_capabilities.py` (MOD-000's manifest→CAP-only
validator) to work against **any** module's manifest, solving a real
schema-divergence problem found during authoring: MOD-000's manifest uses
a flat `- capability_id: CAP-NNN` list; MOD-001's manifest (this session's
own edits) has no such field at all — it references IDs through
`required_rule_ids` (structured `{id, path, status}` objects),
`capability_evidence_ids`, and `missing_capability_blockers` (both free
text). A literal port would silently validate zero IDs against MOD-001's
manifest (false PASS). The tool instead discovers `CAP-`/`RULE-`/`SKL-`
ID tokens by scanning the manifest's raw text, then separately identifies
genuine *declarations* (an `id:`/`capability_id:` property line inside a
YAML list-item) for duplicate-detection purposes, so an incidental prose
mention (e.g. "RULE-001 through RULE-009 — see...") doesn't misfire as a
duplicate declaration.

Also implements the two `REQUIREMENTS.md` §3 checks
`validate_capabilities.py` doesn't have: cyclic capability-dependency
detection (`CAPABILITY_POLICY.md`'s "Dependency-cycle prohibition") via
DFS over `capability_dependency_ids`, currently a structural no-op
against both real manifests (both declare `[]`); and a mandatory
privileged-surface-Rule check tied to
`.claude/rules/admin/admin-privileged-console-baseline.md`, currently a
structural no-op since neither MOD-000 nor MOD-001 activates the Admin
Web/privileged-console surface.

## Independent verification this session performed (orchestrating session, not the authoring agent's own say-so)

I read the full 608-line script and independently re-traced its core
logic against real data, separately from the authoring agent's own
trace:

- Confirmed `find_structural_declarations` correctly matches MOD-000's
  `- capability_id: CAP-NNN` shape and MOD-001's `- id: RULE-NNN` shape,
  and correctly does NOT match `required_agent_roles`' `- role: <name>`
  entries (agents are not CAP-registry capabilities per `ADR-005`'s own
  "Governance note" — no false-positive declaration risk there).
- Hand-counted the pipe-delimited cells in one of this session's own new
  `CAPABILITY_REGISTRY.md` rows (RULE-001) against `REGISTRY_COLUMNS`'s
  15 fields — exact match, no stray `|` characters inside any cell that
  would desynchronize the split.
- Confirmed `discover_manifest_ids`'s word-boundary regex correctly
  extracts `RULE-001` from `capability_evidence_ids`'s "RULE-001 through
  RULE-009" phrasing but correctly does NOT extract a spurious `RULE-009`
  from `missing_capability_blockers`'s "RULE-001..009" phrasing (no
  `RULE-` prefix immediately before the second `009`) — a real, if minor,
  asymmetry that doesn't affect correctness since all 9 real IDs are
  already discovered via `required_rule_ids`'s own structured entries.
- **Found and independently confirmed one real, disclosed imprecision**
  (the authoring agent flagged this itself, transparently, rather than
  me finding it unprompted): check 4 (`approved_by` must be non-empty and
  not start with `"N/A"`) does not fire against this session's own
  `"— (qualification did not pass...)"` sentinel value in the 9 new RULE
  rows, since `"—"` is non-empty and doesn't start with `"N/A"`. This is
  an inherited assumption from the ported original (which only
  anticipated a real name or an `"N/A"` exemption marker, not a third
  "not yet applicable" sentinel). **Does not change the overall FAIL
  verdict** for MOD-001's manifest — check 3 (`review_status` must
  contain "approved") already correctly fails all 9 rows on its own —
  but is a real precision gap in check 4 specifically, worth fixing in a
  future pass rather than silently treating as closed.

## Manual trace of all 3 required cases (no execution — see residual below)

1. **MOD-000 real manifest → expected PASS.** All 7 `CAP-NNN` entries
   structurally declared once each; all 7 registered and `APPROVED`
   (CAP-003/004 via the first-party exemption text, confirmed matching
   `_EXEMPTION_RE`); `approved_by`/`next_review_due` both satisfied for
   all 7; `capability_dependency_ids` absent → cyclic check no-ops; no
   Admin Web/privileged-console activation text anywhere → mandatory-rule
   check no-ops. **Traced: 0 errors, PASS.**
2. **MOD-001 real manifest → expected FAIL, citing all 9 RULE IDs.** All
   9 `RULE-NNN` entries structurally declared once each (0 duplicates,
   correctly excluding the incidental prose mentions); all 9 registered
   but `review_status` reads `BLOCKED`, not `APPROVED` → check 3 fires
   for all 9; `next_review_due` reads non-date prose → check 5 also fires
   for all 9 (check 4 does not fire, per the disclosed imprecision
   above); `capability_dependency_ids: []` → cyclic no-op; no admin
   surface activated → mandatory-rule no-op. **Traced: 18 errors (9 IDs
   × 2 findings each), FAIL** — correctly refuses to treat `BUG-035`-
   blocked content as usable.
3. **Synthetic 2-node cycle fixture (scratch text, never written under
   `knowledge/`)** — `CAP-010 depends_on CAP-011`, `CAP-011 depends_on
   CAP-010`. Hand-traced `parse_dependency_edges` → `{"CAP-010":
   {"CAP-011"}, "CAP-011": {"CAP-010"}}` → `find_cycle`'s DFS visits
   CAP-010 (gray) → CAP-011 (gray) → back-edge to CAP-010 → returns
   `["CAP-010", "CAP-011", "CAP-010"]`. Confirmed against a negative
   control (a 3-node chain, no back-edge) that the same DFS correctly
   returns no cycle.

## Disclosed execution residual — NOT fabricated test-pass evidence

**This script has not been executed**, for the identical reason as slice
1: `.claude/security/bash_guard.py`'s `python3` family only executes 7
pre-existing, SHA-256-pinned scripts; this new script is not on that
list, and the guard file is itself owner-gated. Directly confirmed
(`python3 tools/validate_capability_manifest.py ...` and `python3 -m
py_compile ...` both denied `DISALLOWED_FLAG_OR_SHAPE`). This is the same
precedented, accepted residual as `BUG-025` and this session's own slice
1 — no new bug filed for the same recurring architectural gap. What is
claimed: the logic was hand-traced by two independent readers (the
authoring agent, then this orchestrating session separately) against all
3 required cases, with one real, disclosed precision gap found (check 4's
`"—"` sentinel) that does not change either manifest's overall verdict.
What is NOT claimed: that any test was executed, or that a live run
wouldn't surface something this trace missed.

## Traceability

- Requirement: `REQUIREMENTS.md` §3, "Capability-governance validation
  gates" (GOV-01-R04).
- Model route: `veyro-implementer`/Sonnet, explicit `model: sonnet`. No
  critical-slice or surface-profile role required.
- Commit: recorded in this slice's own commit (see `CURRENT_HANDOFF.md`
  for the SHA).
