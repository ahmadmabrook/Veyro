# R04 gate-5 source authority — veyro-lead decision

Dispatch of record: `R04-GATE5-SOURCE-AUTHORITY-NARROW-DISPATCH-2026-10-09.md`.
Sole-runner operation `5248d59a-511f-4cfd-87c8-797e487c954c`, subgoal
`R04-GATE5-SOURCE-AUTHORITY-NARROW-DECISION`. Single narrow architecture
judgment; not a code/security/scenario review and not certification. One
writer only; no second writer or reviewer was created. The lead reported
rendering the decision from the pinned packet facts alone, with no source
re-read needed (no internal discrepancy appeared in the packet).

## 1. Decision — CONFORMING (intermediate only)

An explicit per-screen declaration **input** is a conforming intermediate
artifact. TSD Appendix F and EIP Appendix F constrain the **final manifest**
(full fields, generation from the canonical UX export, validation against
frontend routes / OpenAPI / AsyncAPI, 170-count equality) and forbid
**invented IDs and inferred routes**; they do not forbid a validation-only
staging artifact that records what is declared versus what has no authority.
It becomes NON-CONFORMING the moment it is treated as authority for routes or
API references.

Mandatory conditions, all of them:

- Every route/API cell carries a provenance pointer to an authoritative
  source. A cell with no such source is recorded as explicitly
  ABSENT/unresolved, never filled with a literal value — a declared literal
  without provenance is exactly the "inferred route" EIP Appendix F forbids.
- The artifact is non-promotable: it may not be transformed, copied, or
  renamed into `screen-contracts.yaml`, and it is not a gate-5 input of
  record.
- The gate continues to return `ERROR` / `SCREEN_CONTRACT_GATE_INPUT_INVALID`
  (not PASS) while any row lacks route or API authority. No PASS, no partial
  PASS, no waiver.
- Screen IDs and owner/domain remain sourced from their existing authorities
  (§2); the declaration file may not originate either.
- Status quo preserved: gate-2 F01–F14 remain formally CLOSED; MOD-001 exit
  remains 0/8.

## 2. Authority table

| Field | Authoritative source | Status |
|---|---|---|
| Screen IDs | `contracts/ui/screen-registry.json` — 170 unique UI IDs, frozen eight-field canonical UX export | PRESENT, authoritative |
| Owner / domain resolution | TSD Appendix B plus the module-domain mapping applied in MOD-001 `IMPLEMENTATION.md` §10; fail-closed on zero or ambiguous owners | PRESENT, authoritative |
| Routes | Authoritative frontend route registry | **ABSENT** — no artifact in the repository holds route authority; the frozen eight-field export used by §10 has no route field |
| API references | OpenAPI and AsyncAPI specifications | **ABSENT** — neither source exists |

## 3. Authority boundary — within technical engineering authority

Choosing the shape of a validation-only intermediate input, and choosing to
represent missing authority as explicit ABSENT rather than as a filled value,
is an engineering-contract choice. The pinned facts establish no new product
surface, no scope addition, and no change to committed architecture, so the
lead issued **no owner stop** — and none is inferred here.

Two boundary markers, recorded as limits rather than as a stop:

- Originating actual route values or API bindings would be deciding the
  frontend URL space and the API surface. That is product/architecture
  origination and would require owner action.
- Creating the authoritative frontend route registry or the OpenAPI/AsyncAPI
  specifications belongs to the modules that own those surfaces, not to a
  MOD-001 declaration file.

The lead's read is that this decision does not constitute an architecture
change and therefore does not require an ADR in `knowledge/04-Decisions/`; it
is an intermediate-artifact contract.

## 4. Next implementable increment (exactly one)

Extend the existing four-field mapping-input validator — still
validation-only, zero rows populated — to require a per-row provenance field
for route and API that must be either a resolvable pointer to an
authoritative source or the explicit literal
`ABSENT_NO_AUTHORITATIVE_SOURCE`, failing closed on any bare literal route or
API value. Nothing beyond that single provenance field: no manifest schema,
no row population.

## Attestation

- **Role:** `veyro-lead` — Opus-tier architecture/critical-engineering
  *decision* role, invoked via the Agent/Task tool for this narrow qualified
  judgment.
- **Model:** self-reported by the agent as `claude-opus-5` ("Opus 5"); the
  dispatch requested the Opus tier for the `veyro-lead` agent type.
- **Session identifier:** **UNQUALIFIED / ABSENT.** The lead stated that no
  session, agent, or invocation ID is exposed in its runtime context and
  explicitly declined to claim the dispatcher's operation IDs or invent a
  substitute. The only independently checkable handle is the harness-assigned
  subagent id returned with the Task result: `ac28987b622ca4eec`. That id is
  harness-side, not self-reported by the agent, and is recorded here as the
  sole verifiable attestation handle — it is not a substitute for a session
  identifier, which remains absent.

## Orchestrator verification and citation correction

After the guarded operation completed exit 0, `mr_verify.py` independently
checked the named `veyro-lead` Task transcript: **PASS, 4/4 turns
`claude-opus-5`**. The private transcript SHA-256 and parent-session/child-agent
handles are recorded without publishing raw transcript content in
`evidence/model-routing/MR-MOD-001-20261009-004.json`. This supersedes the
lead's in-flight statement that runtime attestation was unavailable; it does
not turn this architecture decision into a review. The module-execution-slice
authority referred to as “TSD Appendix B” in §2 is specifically **EIP
Appendix B** (`EIP_MIRROR.md` Appendix B, MOD-001 `IMPLEMENTATION.md` §10 step
4); the TSD has a different Appendix B. The table's route/API absence and
fail-closed conclusion are unchanged. The lead's owner-action boundary for
*originating product API/route semantics* is a limit, not a current owner stop
or a claim that every technical route spelling requires owner approval.

## Scope of this record

No product code, no tests, no canonical manifest, no invented route/API data,
no review or scenario promotion, and no owner stop by inference. The gate-5
PASS and the 170-row `screen-contracts.yaml` remain forbidden until
authoritative frontend route and OpenAPI/AsyncAPI sources exist.

Load-bearing inputs: this module's
`evidence/implementation/R04-GATE5-SOURCE-AUTHORITY-NARROW-DISPATCH-2026-10-09.md`,
`contracts/ui/screen-registry.json`, and MOD-001 `IMPLEMENTATION.md` §10.
