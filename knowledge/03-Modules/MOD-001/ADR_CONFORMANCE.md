---
doc: MOD-001_ADR_CONFORMANCE
status: LIVE — PLAN ONLY (no implementation exists to test conformance against yet)
module: MOD-001
updated: 2026-09-15 (added, Scenario Review round 4, P1-6)
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

**MOD-001's conformance obligation:** MOD-001 itself exposes no
product-facing API surface (it is Foundation/Control infrastructure —
`STATUS.md`'s own `SOFTWARE_ONLY: true`). Its conformance obligation is
narrower: any internal tooling API MOD-001 builds (e.g. a
capability-manifest query endpoint, if one is built rather than a pure
CLI tool) must itself follow ADR-004's shape if and when it exposes
HTTP — versioned, RFC 7807 error format, cursor pagination for any
list endpoint. **No such endpoint is currently planned** — MOD-001's
tools (`tools/validate_architecture_gates.py` etc.) are CLI/CI-invoked,
not HTTP APIs. Conformance state: **N/A — no API surface exists or is
planned. Re-evaluate if implementation introduces one.**

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
ADR-004 N/A-with-justification (above); ADR-015 PASS once
SCN-022/070/113/114 execute and pass for real — **not yet reached,
since implementation has not started.**
