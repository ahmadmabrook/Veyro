---
doc: MOD-001_ADR_CONFORMANCE
status: LIVE — PLAN ONLY (no implementation exists to test conformance against yet)
module: MOD-001
updated: 2026-09-19 (Scenario Review round 14, P0-2 — ADR-004's
conformance obligation corrected: this module does plan a real HTTP
surface, `backend/app/version_negotiation.py` and
`crash_remote_config_intake.py`, contradicting this file's prior
N/A-with-justification claim; conformance state changed to PLANNED,
not yet proven)
---

# MOD-001 — Appendix I ADR Conformance

Appendix I (`knowledge/00-System/EIP_MIRROR.md` lines 21020-21122) maps
two accepted TSD ADRs to MOD-001, each requiring "Module spec +
tests/QA + `ADR_CONFORMANCE.md` + §18 ADR conformance PASS." This file
is that record.

## ADR-004 — REST/JSON + OpenAPI with surface BFFs

**Namespace disambiguation (added, Scenario Review round 13, P2-7):**
this "ADR-004" is the EIP/TSD Appendix I's own architecture-decision
identifier (`EIP_MIRROR.md` lines 21028-21033), a numbering space
internal to the governing baseline documents. It is a different
identifier from this project's own `knowledge/04-Decisions/ADR-004-orchestrating-session-model-tier.md`
(a local project decision about MOD-000's orchestrating-session model
tier), which shares the number by coincidence of two independent
numbering schemes, not by relation. `tools/validate_adr_conformance.py`
must key on the EIP/Appendix-I identifier when checking this file's
conformance claims, never the local `knowledge/04-Decisions/` file of
the same number — flagged here so a future implementation session
doesn't conflate the two.

**Accepted position** (`EIP_MIRROR.md` lines 21028-21033): "Versioned
REST command/query APIs, cursor pagination, RFC 7807 errors and
surface-specific composed read endpoints."

**MOD-001's conformance obligation (corrected, Scenario Review round 14,
P0-2 — the prior text below was false: it claimed no HTTP endpoint was
planned, contradicting this module's own `IMPLEMENTATION.md` §1/§12,
which commits two real backend endpoints):** MOD-001 owns no
product-facing *screens* (`STATUS.md`'s own `SOFTWARE_ONLY: true`, and
`REQUIREMENTS.md` §4's "zero real screens"), but it does own a real,
committed HTTP API surface: `backend/app/version_negotiation.py`
(min-version/optional-vs-forced-update/kill-switch enforcement,
`IMPLEMENTATION.md` §12, proven by `SCN-MOD001-115`) and
`backend/app/crash_remote_config_intake.py` (crash-report ingestion and
remote-config fetch endpoints, `IMPLEMENTATION.md` §12, proven by
`SCN-MOD001-117`) are both "real, executable synthetic endpoints," not
CLI tools. These ARE MOD-001's ADR-004 conformance obligation, directly:
each must be versioned, use RFC 7807 error bodies, and — since neither
exposes a list endpoint (both are single-resource check/intake
endpoints, not collection endpoints) — cursor pagination is disclosed
as not applicable to this module's own two endpoints, not silently
omitted. `tools/validate_architecture_gates.py` and this module's other
CLI tools remain out of ADR-004's scope, as originally stated; the
correction is that the module is not endpoint-free. **Conformance
state: PLANNED, not yet proven** — same disposition as ADR-015 below,
proving evidence provided by `SCN-MOD001-119`(a) once implementation
begins and it executes for real.

## ADR-015 — Backward-compatible expand/migrate/contract schema evolution

**Accepted position** (`EIP_MIRROR.md` lines 21117-21122): "No
destructive schema change is deployed in the same release that stops
reading the old shape."

**MOD-001's conformance obligation:** direct and central — this is
exactly what GOV-01-R06's migration-safety harness exists to enforce
(TSD §24.2, `TSD_MIRROR.md` lines 11655-11669). The migration-safety
lint (`IMPLEMENTATION.md` §4 gate context; `SCENARIOS.md` SCN-022/070/
113/114) mechanically enforces the expand→migrate/backfill→switch→
contract ordering ADR-015 requires, and rejects a destructive
(contract-phase) migration deployed before its expand+backfill+switch
predecessors have run (SCN-070). **Conformance state: PLANNED, not yet
proven** — the harness is designed but not implemented; SCN-022/070/
113/114 will provide the proving evidence once implementation begins
and they execute for real.

## §18 ADR conformance PASS

Per the Appendix I "Evidence" column ("accepted-with-gate ADRs require
the corresponding external evidence"), neither ADR here is
"accepted-with-gate" (both are marked plain "Accepted"), so no external
gate/evidence beyond this document and the mapped scenarios' own
execution applies. §18 conformance PASS for MOD-001 is therefore:
**ADR-004 PASS once `SCN-MOD001-119`(a) executes and proves
`version_negotiation.py`/`crash_remote_config_intake.py` conform for
real (corrected, Scenario Review round 14, P0-2 — was wrongly stated as
already-satisfied "N/A-with-justification"); ADR-015 PASS once
SCN-022/070/113/114 execute and pass for real** — **neither reached
yet, since implementation has not started.**
