# R04 gate 6 — source/normalization decision (veyro-lead)

Dispatch of record: `R04-GATE6-SOURCE-NORMALIZATION-DISPATCH-2026-10-09.md`, sole runner operation `a116cba7-bd69-4509-af8d-e93dfb9aea00`. This is one bounded architecture decision. It is not a code or security review, not an implementation, and not a scenario or module verdict. No code, test, tool, registry, inventory, or control-state file was written. No agent was dispatched. MOD-001 exit stays 0/8, gate-2 F01-F14 stays 14/14 CLOSED, and SCN-014/015/131 stay NOT EXECUTED.

Attestation: role `veyro-lead`; model Opus (`claude-opus-5-5`, "Opus 5.5"); session `CLAUDE_CODE_SESSION_ID=d1dfb568-242c-445d-ab0b-2ef82a85e8b2`, read from this process's environment. I did not verify that identifier against any external ledger.

Sources used: TSD §24.1 (`knowledge/00-System/TSD_MIRROR.md` lines 11643-11653), MOD-001 `REQUIREMENTS.md` GOV-01-R04 (lines 254-266), `IMPLEMENTATION.md` §4 gate-6 row and residual (lines 387-419), `SCENARIOS.md` SCN-014/015/131, and TSD §10.1 read in full. To size each field's shape, I ran a throwaway read-only extraction over all 57 §10 sections (mirror sha256 `292f4335…cf6db`). Nothing from it was persisted, and it is not a checker. `TSD_MIRROR.md` is a derived mirror and not one of the four hash-pinned baselines. Any later extraction must pin the mirror hash and disclose that its fidelity to the TSD docx has not been re-verified here.

## 1. What the source actually states

TSD §24.1 states four predicates that decide pass or fail:

| # | Dimension | Source-stated predicate |
|---|---|---|
| P1 | Command inventory | Identical inventories across two domains fail unless an approved shared-contract exception exists. |
| P2 | Runbook ID | A reused `RB-<DOMAIN>` ID across two domains fails unless an approved shared-contract exception exists. |
| P3 | SLI/SLO | Each domain may name only signals it owns or that belong to an explicitly documented dependency. A foreign signal fails. |
| P4 | Failure/degraded text | Checked by the same ownership rule as P3. |

For the authoritative-entity set and the published-event set, the TSD says only that CI "compares" them. It states no fail predicate. The MOD-001 plan, not the TSD, adds a fail condition for "publishing an identical event ID/name" (§4 row, SCN-015). That condition binds MOD-001 as plan authority and must be labelled plan-backed, never TSD-backed. Neither source defines what an entity-set "collision" is.

The TSD also names no approver for shared-contract exceptions and no record format for them. The register path `contracts/SHARED_CONTRACT_EXCEPTIONS.md` comes from the MOD-001 plan, and that file does not exist.

## 2. Source-backed values versus absent product facts

Every §10 section carries labelled lists that can be extracted verbatim:

- **Authoritative entities:** a table cell with a comma-separated list.
- **Commands:** a "Command inventory:" line, ending before the standard ". Every command declares…" sentence.
- **Published events:** a "Published events:" line.
- **Dependencies:** a "Blueprint dependencies" cell with domain IDs. The one non-ID value is PLT-01's "Platform foundation".
- **Runbook ID:** in the "Tests/runbook:" line. Each of the 57 sections names exactly one `RB-<its own ID>`.

These values are source-backed. The source has internal inconsistencies that an extractor must surface, not resolve:

- **Entities, two representations:** the summary cell and the "Authoritative entities/tables are…" line disagree for PLT-03 (`PlanEntitlement` vs `EntitlementGrant`) and COM-01 (`MemberEntitlementGrant`, `EntitlementReservation` vs `Entitlement`). B2B-01 and B2B-02 use "Authoritative aggregates are…" instead. No source text says which representation wins.
- **Events, two representations:** in 12 domains the "Key events" cell is a strict subset of the "Published events:" line. §24.1 says "published-event sets", so the canonical event value is the "Published events:" line. That choice is label-matched, not inferred.
- **Cross-domain overlaps already present in the TSD:** 14 entity names each appear in two domains (e.g. `ApprovalRequest` in AUT-02 and IAM-03, `Incident` in COA-05 and REL-01). Four published events each appear in two domains: `approval.requested`, `device.offline`, `content.reported`, `build.completed`. All 57 command inventories are distinct and all 57 RB-IDs are unique, so P1 and P2 do not fire on the baseline.

Product facts that are absent from the TSD:

- Any SLI/SLO signal name. The SLI/SLO lines are prose, and many are word-for-word identical boilerplate.
- Any failure-vocabulary term list. 40 of 57 failure lines are identical boilerplate, and there are only 9 distinct texts in total.
- Any mapping from a signal or term to its owning domain.
- Any approved shared-contract exception.
- Which entity representation is canonical where the two disagree.

## 3. Decision — canonical input and normalization boundary

**D1. Validator input.** The gate reads one machine-readable domain-contract document and never parses TSD prose. The document has one record per domain with these fields: `domain_id`, `entities[]`, `commands[]`, `published_events[]`, `runbook_ids[]`, `dependencies[]` (domain IDs only), `slo_signals[]`, `failure_terms[]`. Every value carries a provenance pointer: the TSD section and line span, or `synthetic` for fixtures. A value with no provenance is invalid input and produces ERROR, not a blank. This follows the gate-5 rule that no value is invented and an unknown value is recorded as absent. The plan places real-domain content out of MOD-001 scope (REQUIREMENTS lines 254-257), so MOD-001 exercises this document with synthetic fixtures only.

**D2. Normalization is lexical only and fixed.** The allowed operations are:

- Remove Pandoc escapes (`\<` becomes `<`).
- Collapse whitespace.
- Split comma lists, trim each item, and strip the terminal period.

Comparison rules:

- **Entities, commands, events, RB-IDs:** compared as exact, case-sensitive identifiers.
- **Inventories:** compared as sets, so order is irrelevant. This is disclosed as the reading of "identical inventory".
- **Term occurrence in prose:** casefold the text, treat `- _ . /` and whitespace as equivalent separators, split CamelCase, and require a contiguous whole-phrase match.

Explicitly excluded: stemming, plural folding, synonyms, translation, fuzzy or similarity scoring, and any judgment that a term is "generic". Widening normalization is a reviewed code change, never a change on the input side.

**D3. Predicates and labels.**

- **P1/P2:** as stated in §1, each resolvable only by an exception.
- **Published event:** an identical event ID in two domains fails `DOMAIN_CONTRACT_COLLISION`. Labelled plan-backed.
- **Entity set:** only an identical normalized set fails, mirroring the stated shape of P1. Element-level overlaps are reported as inventory facts, never as a verdict. Making element overlap fail would fire on 14 real TSD names. That is a stricter architecture reading, so it needs its own ADR first.
- **Intra-domain disagreement:** any domain whose two in-source representations disagree is ERROR `DOMAIN_CONTRACT_SOURCE_INCONSISTENT` (exit 2). It is never auto-resolved.

**D4. Making free-form SLO and failure text checkable.** I tested lexical matching of prose against other domains' entity and command identifiers on the real §10 text. It produced 87 ownership hits (63 SLO, 24 failure), almost all on generic words that happen to be single-word entity names: `Policy`, `Target`, `SLA`, `Command`, `Evidence`, `Risk`. If matching is made case-sensitive to suppress those, it no longer catches the TSD's own example (lowercase "booking-capacity"). So entity-derived matching is not a truthful mechanism, and choosing which words count as generic would be invented semantics.

The only truthful mechanism is a declared-term model:

- `slo_signals[]` and `failure_terms[]` are explicit per-domain declarations of owned terms.
- **(a) Anti-invention check:** each declared term must occur, under D2 phrase matching, in that domain's own TSD SLI/SLO or failure text, or carry `synthetic` provenance.
- **(b) Ownership check:** the domain's SLO and failure text is scanned for D2 phrase matches against every other domain's declared terms. A match fails unless the term is also owned by the domain itself or by one of its `dependencies[]`.

With this model the TSD's example is reproduced mechanically. A billing domain's SLO text matches booking's declared `booking-capacity`, booking is not a billing dependency, so it fails. Disclosed residual: enforcement reaches only terms some domain has declared. A foreign concept expressed in undeclared or synonymous wording passes. That limit is in the source, and stating it is not a safety claim. The term declarations are product facts absent from the TSD. They are authored synthetically for MOD-001 and by the owning modules or an approved authority for real domains, never derived by the gate.

**D5. Pair-specific exception register.** Each entry has these fields:

- `exception_id` in the form `SCE-NNN`.
- An unordered domain pair `{A,B}`.
- A `dimension`: `command-inventory`, `runbook-id`, or the plan-backed `published-event`.
- The exact colliding artifact: the RB-ID, the event ID, or the sha256 of the sorted canonical command inventory.
- An approval reference `OWN-NNN` that resolves to exactly one live `OWNER_APPROVALS.md` row.

An entry resolves a collision only for that exact pair, dimension, and artifact. It never covers `{A,C}` or another artifact. A resolved pass cites the `exception_id`, as SCN-131 requires.

Because the TSD names no approver, binding approval to an owner row is the fail-closed choice. It reuses the gate-3 resolution pattern and authorizes nothing by itself. Malformed, duplicate, or unresolvable entries produce ERROR (exit 2). Fixtures use a disposable synthetic register only (SCN-131). Creating or populating the live register is not part of this decision.

## 4. Gaps that remain fail-closed

| Gap | Missing dependency | Smallest legal step |
|---|---|---|
| Real-domain contract document | No machine-readable domain inventory exists under `contracts/`, and populating one is out of scope here. | A later, separately dispatched extraction increment: verbatim structured fields only, with provenance, emitting ERROR for the inconsistent entity fields (PLT-03, COM-01, and the B2B-01/02 phrasing). |
| Canonical entity reading for PLT-03 and COM-01 | No text says which representation wins. The baseline cannot be edited. | ADR proposal plus an owner decision. Until then the gate reports ERROR for those domains. |
| Real SLO and failure term ownership | Absent from the TSD. | Declarations by owning modules or an approved authority. Out of MOD-001 scope. |
| Exceptions for the 4 real event overlaps | No approval exists. | Owner-approval rows. These only matter once the real document exists. |
| ADR for D1-D5 | Not written: this dispatch allows exactly one file. | The parent routes an ADR in `knowledge/04-Decisions/`. No product, pricing, business, or scope change is proposed, so no owner-approval entry is required for D1-D5 themselves. |

## 5. Next bounded increment (veyro-implementer, synthetic only)

Implement `tools/validate_architecture_gates.py --gate domain-uniqueness` against the D1 document schema and a disposable synthetic D5 register. Enforce only P1 and P2 plus pair-specific exception resolution. This covers SCN-131's deny and pass and SCN-015's RB-ID and command-inventory cases.

The four remaining dimensions return ERROR `DOMAIN_DIMENSION_NOT_IMPLEMENTED` (exit 2), never PASS, so no partial gate can read as a full gate. Provenance-less input and an unresolvable `OWN-NNN` produce ERROR.

Out of scope for this increment: real §10 extraction, a live register, independent review, and any scenario or module promotion.

## Orchestrator verification addendum (not a second decision)

The guarded operation completed exit 0. Independent `mr_verify.py` checked the actual named `veyro-lead` child transcript: **PASS, 38/38 turns `claude-opus-5-5`**; private transcript hash and parent/child handles are in `evidence/model-routing/MR-MOD-001-20261009-005.json`. The opening sentence "No agent was dispatched" refers only to the lead child not dispatching another agent; the parent did dispatch this one lead Task. No independent reviewer was dispatched.

**Source-accuracy hold on §4's owner-call inference:** TSD §10.3/§10.12 summary cells and realization notes do conflict lexically, but TSD P0-02 (mirror line 164), accepted ADR-008/ADR-018 (lines 764 and 833), and §15.2 (lines 10509-10516) explicitly distinguish PLT-03 `PlanEntitlement` from COM-01 `MemberEntitlementGrant`. Thus "no text says which representation wins" and an owner decision for those terms are **not established**. The remaining `EntitlementReservation`/`Entitlement` representation still needs technical reconciliation. This addendum does not choose a canonical machine inventory or issue a gate verdict; a bounded governing-source reconciliation is required before treating §4's owner-call row as binding. Synthetic-only P1/P2 planning remains non-promotable, and gate 6 remains ERROR.
