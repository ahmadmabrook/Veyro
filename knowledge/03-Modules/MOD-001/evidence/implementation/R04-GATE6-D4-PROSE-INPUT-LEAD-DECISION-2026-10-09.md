# R04 gate 6 — D4 observed-prose input contract decision (veyro-lead)

Dispatch of record: `R04-GATE6-D4-PROSE-INPUT-DECISION-DISPATCH-2026-10-09.md`, sole runner operation `9be8fd06-4ccd-410d-aa5d-477427198502`. Boundary of record: `R04-GATE6-D4-PROSE-INPUT-BOUNDARY-2026-10-09.md`; scope review `R04-GATE6-D4-SCOPE-REVIEW-2026-10-09.md`. This is one bounded technical architecture/input-contract decision. It is not a review, an implementation, or a scenario, gate, or module verdict. I wrote no code, test, ADR, registry, counter, or control-state file, and I dispatched no agent. Gate 6 aggregate stays ERROR. SCN-MOD001-014/015/131 stay NOT EXECUTED. MOD-001 exit stays 0/8. R04 gate-2 F01-F14 stays 14/14 CLOSED.

## Attestation

- **Role:** `veyro-lead`, making an architecture/input-contract decision.
- **Model:** invoked as Opus 5.5, model ID `claude-opus-5-5`.
- **Session:** this process's environment reports `CLAUDE_CODE_SESSION_ID=5081843d-509a-4d43-bb9a-8486d601a885`. I have not verified it against any external ledger.
- **Repository HEAD at decision time:** `e481b814a80923849dddfe7a49319112aae7b023`.
- **TSD mirror:** `knowledge/00-System/TSD_MIRROR.md`, re-hashed this session as sha256 `292f4335588bfe1e35e72719835ccab318dbe548e7eb520870eb879922bcf6db`. This matches the hash pinned by the prior gate-6 lead decisions. The mirror is derived, not a hash-pinned baseline, and I did not re-verify its fidelity to the TSD docx.

## 1. Grounding (directly read this session)

| # | Source | Location | Fact relied on |
|---|---|---|---|
| G1 | TSD §24.1 | mirror lines 11643-11653 | Each domain's SLI/SLO "may name only signals owned by that domain or an explicitly documented dependency". A foreign signal such as booking-capacity in a billing SLO fails. Failure/degraded-behavior text is checked by the same ownership rule. No shared-contract exception clause is attached to these two dimensions. |
| G2 | Gate-6 lead decision D1 | `R04-GATE6-SOURCE-NORMALIZATION-LEAD-DECISION-2026-10-09.md` line 50 | The validator reads one machine-readable document, never parses TSD prose, and requires provenance (a source pointer or `synthetic`) on every value. Missing provenance is ERROR. MOD-001 uses synthetic fixtures only. |
| G3 | Same, D2 | lines 52-64 | Term occurrence in prose is matched by casefold, `- _ . /`/whitespace separator equivalence, CamelCase split, and contiguous whole-phrase match. Stemming, synonyms, fuzzy matching, and "generic word" judgments are excluded. |
| G4 | Same, D4 | lines 73-81 | `slo_signals[]`/`failure_terms[]` are owned-term declarations. (a) Each declared term must occur in the domain's own SLI/SLO or failure text unless it carries `synthetic` provenance. (b) The domain's SLO and failure text is scanned for other domains' declared terms, and a match fails unless the term is owned by the domain itself or by one of its `dependencies[]`. |
| G5 | Same, §2 | lines 42-43 | Every §10 domain carries SLI/SLO prose and failure prose (often boilerplate). The text exists for every domain. Term ownership does not. |
| G6 | ADR-013 Decision 1 and 4 | `knowledge/04-Decisions/ADR-013-gate6-synthetic-domain-contract-input.md` lines 20, 23 | The first increment's exact field list. Malformed, absent, duplicate, or provenance-less input is ERROR/exit 2. The aggregate stays ERROR/`DOMAIN_DIMENSION_NOT_IMPLEMENTED` while any dimension is unimplemented, and a component success is never a full PASS. |
| G7 | Current validator | `tools/validate_architecture_gates.py` lines 2183-2186, 2223-2276 | `_DOMAIN_CONTRACT_FIELDS` is an exact 7-tuple. Each field has the shape `{"value": [nonempty str, ...], "provenance": nonempty str}`, enforced by `_domain_contract_field`. Provenance is recorded per field, not per element. Any added or missing field raises `GateInputError` (ERROR). |
| G8 | MOD-001 GOV-01-R04 | `REQUIREMENTS.md` lines 234-266 | The lint compares SLI/SLO signals and failure vocabulary across domains. Real-domain content is out of MOD-001 scope. |
| G9 | SCN-MOD001-014 / 015 / 131 | `SCENARIOS.md` lines 573-592, 593-610, 1056-1080 | 014: a disjoint positive across all six dimensions, including SLI/SLO names and failure vocabulary. 015: an independent `DOMAIN_CONTRACT_COLLISION` for a "foreign-signal SLO" (booking-capacity in a billing SLO). 131: P1/P2 exception only, with no SLO/failure role. All fixtures are synthetic. |

**The gap, confirmed.** G4(a) and G4(b) operate on two distinct inputs: owned declarations, and the domain's own SLO/failure text. G2/G6/G7 supply only the declarations. If SCN-015's foreign signal were placed in billing's `slo_signals`, billing would *declare* ownership of it and G4(b) would exempt it. That is the conflation the boundary record identified. If the validator read the TSD to get the text, it would violate G2. The sources therefore support a lawful technical decision: an additive input field carrying the text as supplied data. That is consistent with G2's "machine-readable document, never parse TSD prose", because the validator applies G3 matching to strings it is handed and never locates or extracts them from any TSD artifact.

## 2. Decision

### P-1. Exact schema addition (additive; no existing field changed)

Add exactly two fields to each domain record, alongside the existing seven:

- `slo_text`: the domain's observed SLI/SLO prose.
- `failure_text`: the domain's observed failure/degraded-behavior prose.

Each new field uses **the identical existing field shape** (G7), so `_domain_contract_field` validates it unchanged:

```json
"slo_text":     {"value": ["<prose passage>", ...], "provenance": "synthetic" | "<source pointer>"},
"failure_text": {"value": ["<prose passage>", ...], "provenance": "synthetic" | "<source pointer>"}
```

Each `value` element is one opaque prose passage (a nonempty string). The full record field set becomes exactly `entities, commands, published_events, runbook_ids, dependencies, slo_signals, failure_terms, slo_text, failure_text`. The meaning, shape, and validation of `slo_signals`, `failure_terms`, and the other five existing fields are unchanged. They remain the owned-term declarations of G4.

The two new fields add **one rule beyond the shared shape**: `value` must be non-empty (see P-3). This rule applies only to the two `*_text` fields. The existing seven fields keep their current "may be empty" rule.

### P-2. How observed prose is told apart from owned declarations, and what provenance means

1. **The distinction is structural, by field name, and nothing else.** `slo_signals`/`failure_terms` are declarations (G4). `slo_text`/`failure_text` are observations. The validator never infers ownership from the prose fields. A string in `*_text` creates no ownership for any domain, and a string in `slo_signals`/`failure_terms` is never scanned as prose. This closes the conflation route: a foreign term written into billing's `slo_text` stays an observation and remains subject to G4(b).
2. **Provenance is per field, with the same representation as the existing fields** (G7). It is either the literal `synthetic` or a nonempty source-pointer string. MOD-001 fixtures use `synthetic` only (G2, G8).
3. **The validator never dereferences a source pointer.** It does not open, hash-check, or extract from the TSD, the mirror, or any other document named in `provenance`. A pointer is recorded, opaque metadata. Its truthfulness is the responsibility of whatever later, separately dispatched extraction increment produces real values. That increment is out of MOD-001 scope (G8 and gap table row 1 in G2's decision).
4. **G4(a)'s `synthetic` carve-out is keyed only on the declaration field's provenance** (`slo_signals`/`failure_terms`), exactly as G4 states. The prose field's provenance plays no part in it. This decision does not alter G4(a).

### P-3. Absent-input behavior (fail-closed)

All of the following are `DOMAIN_UNIQUENESS_GATE_INPUT_INVALID` ERROR, exit 2. None is ever treated as "no prose, therefore no foreign term":

- **Document absent, symlinked, or unreadable.** This is existing behavior, unchanged.
- **A domain record missing `slo_text` or `failure_text`.** The exact-field-set check extends to the 9-field set. A 7-field document is therefore invalid. Tolerating it would not be a compatible fallback, because it would let the P3/P4 scans run over nothing.
- **A `*_text` field whose `value` is an empty list.** The reason: an empty observation would make G4(b) vacuously clean and G4(a) unsatisfiable without a stated cause. G5 records that every §10 domain carries both texts, so emptiness is a defect in the input, not a source fact. A fixture that wants "no foreign vocabulary" supplies prose that simply contains none.

There is no partial or optional mode. The decision does not allow some domains to carry prose while others do not.

### P-4. Malformed-input behavior (fail-closed)

The following are `DOMAIN_UNIQUENESS_GATE_INPUT_INVALID` ERROR, exit 2, and the whole document is rejected before any P1-P4 comparison runs (current `GateInputError` abort semantics, G7):

- a `*_text` field that is not an object with exactly `value` and `provenance`;
- a non-list `value`;
- any element that is not a string, or is blank or whitespace-only;
- a duplicate passage within one field (the existing case-sensitive duplicate rule);
- blank or non-string `provenance`;
- an unknown extra field on a record.

No passage is truncated, normalized at load time, or repaired. G3 normalization happens only at match time.

### P-5. Comparison binding (pinned to G4, not extended)

This decision supplies inputs only. For the later code operation, the literal G4 binding is:

- **G4(a):** each term in `slo_signals` must phrase-match (G3) some passage in the same domain's `slo_text`, and each term in `failure_terms` must phrase-match some passage in `failure_text`, unless the declaring field's provenance is `synthetic`.
- **G4(b):** every passage in a domain's `slo_text` and `failure_text` is phrase-matched (G3) against every *other* domain's declared terms (`slo_signals` ∪ `failure_terms`). A hit fails as `DOMAIN_CONTRACT_COLLISION` unless that term is also declared by the scanned domain itself or by a domain listed in its `dependencies[]`. A dependency that names a domain absent from the document contributes no declared terms, so it cannot exempt anything. A hit in `slo_text` is reported under the SLI/SLO dimension and a hit in `failure_text` under the failure-vocabulary dimension, naming both domains, the term, and the field.
- **No exceptions.** No shared-contract exception may waive P3/P4. G1 attaches the exception clause only to command inventories and RB-IDs, and the D5 dimension tuple is not widened by this decision.

Pairing each text only with the same-kind declarations in (b) (SLO text against `slo_signals` only) would be a narrowing of G4(b), not an input question. It is **not** decided here.

### P-6. ERROR persistence

- **Until P3/P4 comparison code is implemented and reviewed,** the aggregate keeps returning ERROR/`DOMAIN_DIMENSION_NOT_IMPLEMENTED` (exit 2), as ADR-013 Decision 4 requires (G6). It does so even when a document carries valid `*_text` fields. Accepting the new fields is not implementing the dimensions.
- **The live gate stays ERROR in all cases.** No real 57-domain document exists at the default path `contracts/domains/domain-contract.json`, and this decision creates none. The live run therefore stays ERROR on absent input, independent of dimension completeness.
- **Any future aggregate PASS on synthetic fixtures** (the SCN-014 shape) is fixture-level evidence only. It is not a live gate PASS and does not promote any scenario.
- **Nothing here produces PASS, waives D5, or populates a registry.**

## 3. Owner-reservation classification

This is a technical lint-input method within `veyro-lead` authority. It edits no baseline. It changes no product entity, ownership, or business rule, and it asserts no real-domain term ownership. Prose values and declarations remain synthetic for MOD-001, and any real values would be authored by owning modules or an approved authority (G4, G2 gap table). It changes no pricing or scope. No `OWNER_APPROVAL_REQUIRED` criterion is met, and no owner stop is raised.

## 4. Residual limits and open dependencies

1. **ADR-013 reconciliation is required before code.** ADR-013 Decision 1 lists the field set exactly. A bounded ADR addendum must adopt P-1 through P-6 before the validator's `_DOMAIN_CONTRACT_FIELDS` changes. This file does not edit ADR-013. Per the dispatch, that is a separate operation.
2. **Fixture migration.** Every existing 7-field synthetic fixture and test becomes INPUT_INVALID under P-3. The later code operation must migrate them in the same change, so that no P1/P2 control is silently lost.
3. **G4(a) is vacuous for MOD-001 fixtures.** All MOD-001 declarations carry `synthetic` provenance, so G4's own carve-out exempts them. G4(a) therefore cannot be exercised by synthetic fixtures unless a fixture uses a non-`synthetic` pointer. That would be a fabricated source pointer, and it is not authorized here. SCN-014/015 do not name an (a) case. This residual is disclosed, not resolved.
4. **Co-declaration evasion.** If two domains both declare the same term, each is "owner" under G4(b), and the foreign-term scan is defeated. G4 states no fail predicate for duplicate ownership. Adding one is a separate architecture decision. The SCN-015 fixture must not co-declare the foreign term.
5. **Inherited G4 limit.** Enforcement reaches only declared terms. Undeclared or synonymous foreign wording passes.
6. **Synthetic document at the live path.** The validator does not refuse a document of `synthetic`-provenance values placed at the default live path. That gap is pre-existing and spans all fields, not only the two added here. It is recorded for the ADR reconciliation and not decided in this prose-only scope.
7. **Real prose values.** The verbatim §10 SLO/failure text with true source pointers depends on the out-of-scope real-domain extraction increment, which is unbuilt.
8. **Provenance granularity.** G2 says "every value carries a provenance pointer". The implementation (G7) and this decision use per-field provenance. This is consistent with current code and is disclosed.

## 5. Next bounded action now legally available

The parent may route the ADR-013 addendum adopting P-1 through P-6. After that, a bounded `veyro-implementer` code operation may add the two fields, the non-empty rule, the fixture migration, and the G4(a)/(b) comparisons, with deny and positive controls (SCN-015's foreign-signal case and SCN-014's disjoint case on synthetic input). Independent assurance must follow before any scenario credit. The live gate remains ERROR throughout.
