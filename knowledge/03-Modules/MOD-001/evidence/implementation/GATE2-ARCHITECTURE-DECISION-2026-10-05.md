# Gate 2 (Module dependency/SQL lint) — Architecture Decision Record

- **Date:** 2026-10-05
- **Authoring role:** `veyro-lead` (architecture / critical-engineering decision role), dispatched fresh-context for a bounded adjudication.
- **Model ID (verbatim, as reported by this environment):** `claude-opus-5[1m]` ("Opus 5 (1M context)")
- **Work unit:** MOD-001 `GOV-01-R04`, TSD §24.1 gate 2; scenarios `SCN-MOD001-006 / -007 / -095 / -096`.
- **Scope:** four adjudications only (A/B/C/D below). This is a decision record, not an ADR, not an implementation, not a review.

## What this dispatch did NOT do (explicit)

- **No implementation.** No source, test, config, CI, or contract file was created or edited. The only file written is this record.
- **No review round.** No entry was claimed in `REVIEW_IN_FLIGHT.md`; no review verdict is expressed or implied here. The §6 judgment call in `GATE2-MODULE-DEPS-REPAIR-CHECKPOINT-2026-10-05.md` is *adjudicated as an architecture decision* below — that is an input to an independent review, **not** a substitute for one (DC-14: a session may never treat its own reasoning as reviewer approval).
- **No commit, stage, or push.** `tools/validate_architecture_gates.py` and its tests remain untracked WIP.
- **No scenario PASS/MET declaration.** `SCN-MOD001-006/-007/-095/-096` remain unpromoted.
- **No touch** of SCN-070, DOM-002, or the RLS/permission A2 gate work. No paid services, no real member data, no deploy.

---

## Verified excerpts (what this session actually read)

| Path | Line range | What it established |
|---|---|---|
| `knowledge/00-System/TSD_MIRROR.md` | 11600–11612 | Gate 2 normative text: modules "may reference only their owned table prefix/schema and approved read-model/application interfaces; cross-domain raw SQL/ORM imports fail CI"; §6.3 is the normative directed graph for the four pairs; reverse edge must stay event-driven. |
| `knowledge/00-System/TSD_MIRROR.md` | 1521–1574 | §6.3 pins exactly four pairs: COM-01→COM-03, REL-01→DAT-01, GRO-01→ENG-01, LIF-01→GOV-04, each with the reverse direction required event-driven. |
| `knowledge/00-System/TSD_MIRROR.md` | 2040–2130 | §9 aggregate-root ownership table. Names: Membership→COM-01, Booking→OPS-02, Ledger→COM-04, AccessDecision→OPS-03, BillingAccount/Invoice→COM-03 (owns "payment intents"), Order→COM-05. |
| `knowledge/03-Modules/MOD-001/REQUIREMENTS.md` | 234–290 | `GOV-01-R04` evidence obligation: "a deliberate-violation proof for each of the 6 TSD-defined architecture gates plus the 7th"; acceptance: each gate has "a passing valid-fixture proof AND a deliberate-violation fail-closed proof"; no gate bypassable at the CI-workflow-configuration layer. OUT of scope: "the actual domain contract/... test *content* for domains that don't exist yet — the gate exists and blocks on it; content is later modules' job." |
| `knowledge/00-System/DEVELOPMENT_CONSTITUTION.md` | 72–100 | DC-09 and DC-14 full text (quoted under verdict B). |
| `knowledge/03-Modules/MOD-001/IMPLEMENTATION.md` | 372–420 (+ grep over 372–538) | §4 fixture plan. Mission constraint stated in-line: "synthetic/test fixtures only, never destructive tests against real project baselines." Gate 2 row names valid + violation fixtures and the two violation codes. |
| `knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-MODULE-DEPS-REPAIR-CHECKPOINT-2026-10-05.md` | 93–185 | §5 limitations (no manifest; gate fails closed on defaults; 3 Ruff + 12 E501 findings, none on repair-authored lines), §6 the one open judgment call (same-module nested prefixes; duplicate-prefix side effect; gate 2's input contract not fixed by an ADR unlike gates 1/4 under ADR-010), §7 files changed, §8 next legal action. |
| `tools/validate_architecture_gates.py` | 155–230 | Gate 2 input contract docstring: `--modules-dir` default `backend/app/modules/`, `--module-manifest` default `contracts/modules/ownership.json`, "Neither flag offers a skip, exempt, or allowlist path"; manifest v1 shape; "A discovered module with no manifest entry is ERROR; a manifest entry with no directory is only a note"; `_shared` domain-free; `BIDIRECTIONAL_PAIRS` "pinned here and never manifest-configurable". |
| `tools/validate_architecture_gates.py` | 1390–1470 | `parse_module_manifest` strict validation + rule-7 overlap loop with the `if mod_a == mod_b: continue` narrowing. |
| `backend/app/modules/` | `ls`; `membership/__init__.py` full | Six scaffolds each contain only `__init__.py` + `tests/`. `membership/__init__.py` states: "Membership domain — empty scaffold. **Not yet claimed by an owning module.**" |
| `.claude/rules/backend/architecture.md` | grep hits (41, 95) | Rule references `app/modules/membership/`, `app/modules/booking/` as the layout; control 5 is the empty-scaffold carve-out cited by the scaffold docstrings. |

## Assumed, not verified (labeled as such, not researched further per dispatch bounds)

- EIP §4.3 / Appendix H exact text — not re-read this session.
- `ADR-010` (said to fix gates 1 and 4 input contracts) and `ADR-005` (surface-profile-activation gate) — contents taken from secondhand citation in the checkpoint and `REQUIREMENTS.md`.
- The 88/88 local test pass and the 3 remaining Ruff findings — taken as given from the dispatch and checkpoint §4/§5; not re-run.
- Whether any committed CI workflow currently invokes `--gate module-deps` with repo defaults. **Unverified and load-bearing for verdict A's CI consequence** — see A.4.
- The full `.claude/rules/backend/architecture.md` control-5 text (only grep hits read).
- The complete TSD §10 57-domain roster (only the §9 aggregate-root table window was read); no POS-specific or payment-specific domain code was located.
- `CURRENT_STATE.md` was grepped, not read; its output exceeded the readable budget. Governance state is therefore taken from `CURRENT_HANDOFF.md`'s head only.

---

## Verdict A — Authoring a gate-2 ownership manifest for the six scaffolds

**Verdict: NOT legal to author real-tree domain ownership now. Domain ownership for all six scaffolds stays DEFERRED. Gate 2 is ACCEPTED for `GOV-01-R04` on synthetic fixtures only.**
**Classification: the DEFERRAL is an ENGINEERING CHOICE. Any real-tree domain binding is an UNRESOLVED OWNER-RESERVED DECISION.**

Four grounds, in order of decisiveness:

**A.1 — The scaffolds disclaim ownership in their own source.** `backend/app/modules/membership/__init__.py` states the domain is "Not yet claimed by an owning module," and cites `.claude/rules/backend/architecture.md` control 5 for the proposition that an empty scaffold does not yet carry the modular-monolith boundary constraints. Authoring `contracts/modules/ownership.json` would assert exactly the claim the scaffold denies. An agent cannot resolve that contradiction in the project's favor (DC-14).

**A.2 — Two of six mappings cannot be grounded in any source I verified.** From TSD §9 (lines 2040–2130) the aggregate-root table grounds four mappings by name, and leaves two ungrounded:

| Scaffold | Proposed domain | Grounding | Status |
|---|---|---|---|
| `membership` | `COM-01` | TSD §9 line ~2059 "Membership / COM-01"; §10.12 header line 3632 | Groundable by name |
| `booking` | `OPS-02` | TSD §9 "Booking / OPS-02" | Groundable by name |
| `ledger` | `COM-04` | TSD §9 "Ledger / COM-04" | Groundable by name |
| `access` | `OPS-03` | TSD §9 "AccessDecision / OPS-03" | Groundable by name (aggregate root is `AccessDecision`, not `access`) |
| `payment` | `COM-03`? | TSD §9 shows COM-03 owning "payment intents", but the aggregate root is `BillingAccount/Invoice`; no domain is named "payment" | **ENGINEERING PROPOSAL — ungrounded** |
| `pos` | `COM-05`? | TSD §9 `Order / COM-05` covers cart/lines/fulfillment; nothing I read maps "pos"/point-of-sale to a domain code | **ENGINEERING PROPOSAL — ungrounded** |

**A.3 — A partial manifest is not a legal option.** The input contract (tool docstring, lines ~181–183) makes "a discovered module with no manifest entry" an ERROR. Declaring the four groundable mappings and omitting `payment`/`pos` therefore still fails the gate. The manifest is all-or-nothing across discovered modules, so it cannot be authored at all without deciding the two ungrounded bindings.

**A.4 — Nothing is actually lost.** `GOV-01-R04`'s own acceptance criteria (`REQUIREMENTS.md` 234–290) demand *a passing valid-fixture proof and a deliberate-violation fail-closed proof per gate* — not a real-tree pass — and `IMPLEMENTATION.md` §4 states the mission constraint as "synthetic/test fixtures only." `REQUIREMENTS.md` explicitly puts test *content* for "domains that don't exist yet" out of MOD-001's scope: "the gate exists and blocks on it; content is later modules' job." The six scaffolds own zero tables and contain zero non-test source, so any `owned_table_prefixes` value for them would be invented, not derived.

### How gate 2 is still ACCEPTED for GOV-01-R04 / SCN-006/007/095/096

Run the gate against synthetic fixture trees via its existing `--modules-dir` / `--module-manifest` flags (both already parameterised; no new skip path, no allowlist, no code change needed for this). Required evidence set, all fixture-scoped:

1. **Positive:** a synthetic tree whose module imports only its own package and a declared `public_interfaces` path, and whose SQL touches only its own `owned_table_prefixes` → PASS.
2. **Negative 1:** cross-domain raw SQL/ORM import → `CROSS_DOMAIN_SQL_IMPORT` naming both modules, both domains, resolved path, `relpath:lineno`.
3. **Negative 2:** the §6.3 reverse edge on one of the four pinned pairs (e.g. COM-03→COM-01) → `REVERSE_EDGE_NOT_EVENT_DRIVEN` citing the one permitted direction.
4. **Negative 3 (input fail-closed):** default real-tree invocation with no `contracts/modules/ownership.json` → `MODULE_DEPS_GATE_INPUT_INVALID`. This already reproduces (checkpoint §5 item 2) and is **the correct, evidenced fail-closed behaviour**, not a defect. Record it as a deliberate-violation proof in its own right.
5. Every evidence artifact must state **"fixture-scoped; real-tree domain ownership DEFERRED"** on its face. A gate-2 evidence file that reads as a real-tree pass would be a false evidence claim.

### What remains BLOCKED, and on what

- **Real-tree gate-2 activation** is BLOCKED on an owner decision binding each of the six scaffolds to a domain code and to owned table prefixes. Trigger for unblocking (either suffices): (a) explicit owner approval of the six bindings recorded in `knowledge/00-System/OWNER_APPROVALS.md`; or (b) the first real source file landing in a scaffold, at which point the module that authors that file owns the manifest entry for it (architecture.md control 5's own activation condition), and the question routes to that module, not MOD-001.
- **CI consequence (unverified premise — must be checked before any CI change).** If a committed workflow invokes `--gate module-deps` with repo defaults, CI is red today by design. The legal resolutions are: pin the CI step to the fixture tree with explicit flags *and* label it fixture-scoped, or hold the CI step unwired with the gap disclosed in `IMPLEMENTATION.md` §4. **Inventing a skip/exempt path is forbidden** — the tool's docstring states "Neither flag offers a skip, exempt, or allowlist path," and `GOV-01-R04` requires no gate be bypassable at the CI-workflow-configuration layer. Choosing between the two legal resolutions is an ENGINEERING CHOICE, deferred to the implementer dispatch after the premise is verified.

> **BLOCKED: OWNER_APPROVAL_REQUIRED** — binding `backend/app/modules/{membership,booking,payment,ledger,pos,access}` to domain codes and owned table prefixes in a committed `contracts/modules/ownership.json`. Category: *material architecture change* (`CLAUDE.md` owner-reserved item 4; `.claude/rules/global/owner-reserved-restrictions.md` item 4). The `payment` and `pos` bindings additionally lack any verified governing source.

## Verdict B — Does the manifest / input contract require an ADR under DC-09?

**Verdict: SPLIT. The fixture-scoped input contract is a MOD-001 implementation artifact and needs no owner approval; an ADR is nonetheless RECOMMENDED for parity with ADR-010. A committed real-tree `contracts/modules/ownership.json` requires BOTH an ADR and owner approval.**

DC-09 trigger text relied on, quoted verbatim from `DEVELOPMENT_CONSTITUTION.md` lines 74–79:

> "A material deviation from the governing EIP's specified structure, process, or scope requires an ADR (`knowledge/04-Decisions/ADR-<NNN>-*.md`) recorded **before** implementation, plus applicable owner approval where the deviation touches an owner-reserved category. A deviation discovered after the fact must still get an ADR, honestly labeled as retroactive — silence is never an acceptable resolution."

Applying it:

| Artifact | Is it a "material deviation"? | ADR? | Owner approval? | Classification |
|---|---|---|---|---|
| Gate-2 validator itself (`--gate module-deps`) | No — TSD §24.1 line 11604 specifies this gate; building it is conformance, not deviation | Not required | No | ENGINEERING CHOICE |
| Fixture-scoped input contract (manifest v1 schema, discovery rules, `BIDIRECTIONAL_PAIRS` pinning) as documented in the tool docstring + `IMPLEMENTATION.md` §4 | No — it implements the TSD's own "owned table prefix/schema" concept; it binds no real domain | Recommended, not required — see note | No | ENGINEERING CHOICE |
| Committed `contracts/modules/ownership.json` binding six real scaffolds to domains | **Yes** — asserts durable domain ownership the baselines do not assign and the scaffolds explicitly disclaim; touches architecture | **Required** | **Required** | OWNER-RESERVED |

Note on the recommendation: gates 1 and 4 have their input contracts fixed by ADR-010 (checkpoint §6, taken as given / assumed-not-verified). Gate 2's contract currently exists only as a tool docstring, which is why the checkpoint's own §6 says "there is no authority this session could have checked the intent against." An ADR fixing gate 2's input contract — **schema and semantics only, binding no real domain** — removes that ambiguity, is within this role's authority, and does not require owner approval because a CI lint's input schema is not material product/pricing/business/scope architecture. It was not authored in this dispatch (out of bounds); it is routed in verdict D.

## Verdict C — Nested and duplicate prefixes under the "owned" invariant

**Verdict: ACCEPT same-module nesting (the current narrowing is correct — do not revert). REJECT exact duplicate prefixes with a named input error. REJECT cross-module overlap, with no exception path.**
**Classification: ENGINEERING CHOICE.** This settles checkpoint §6's open judgment call as an architecture decision; it still requires independent code review before it is implemented or treated as closed.

Rule the gate should enforce, stated as three cases:

| Case | Disposition | Invariant rationale |
|---|---|---|
| One module declares nested prefixes (`cal_`, `cal_event_`) | **ACCEPT** | The invariant gate 2 protects is *unambiguous attribution of a table to exactly one owner* (TSD §24.1 line 11604: a module "may reference only their owned table prefix/schema"). When both prefixes resolve to the same module, attribution is unambiguous for every identifier under either prefix. Nesting is also the only shape under which the contract's own "longest matching `owned_table_prefixes`" resolution rule is reachable at all — a global overlap ban makes that documented rule dead code. The test's premise is sound; keep it and promote its in-file "ASSUMPTION" comment to a citation of this record. |
| Two different modules declare overlapping prefixes (`cal_` vs `cal_event_`) | **REJECT — `GateInputError`, no exception path** | Attribution becomes owner-dependent on resolution order; a cross-domain SQL reference could be silently attributed to the referencing module and escape `CROSS_DOMAIN_SQL_IMPORT`. That is a fail-open on the gate's primary invariant. Current behaviour; preserve exactly. |
| One module declares the **same prefix twice** (`["cal_", "cal_"]`) | **REJECT — named input error (new), e.g. `MODULE_DEPS_GATE_INPUT_INVALID: duplicate owned_table_prefixes entry`** | A duplicate carries zero ownership information and is never an intentional declaration — it is a malformed input. The rest of this input contract is deliberately closed and strict (unknown keys rejected, empty `owned_table_prefixes`/`public_interfaces` rejected, duplicate `domain` rejected, duplicate `owned_schemas` rejected). Silently tolerating one malformed shape inside an otherwise fail-closed validator is an inconsistency a future reader will read as permission. Duplicate `owned_schemas` is already an error for the same reason; prefixes should match. |

Why this is not a revert of the repair: the checkpoint's §6 offered the reviewer a binary (keep the narrowing, or revert it and delete the test). Both horns are wrong. The narrowing is correct on the ambiguity invariant; its disclosed side effect (duplicate acceptance, checkpoint §5/§6) is a *separate, small* input-validation gap that should be closed on its own terms rather than by restoring a check that kills a documented resolution rule.

## Verdict D — Next bounded action and independent assurance scope

**Verdict: one bounded implementer dispatch, then a gate-2-scoped independent code review, then scenario review. No gatekeeper involvement yet.**
**Classification: ENGINEERING CHOICE (sequencing). The owner-reserved item in verdict A is not in this path and does not block it.**

Next bounded action — single `veyro-implementer` dispatch, strictly these items and nothing else:

1. Implement verdict C's duplicate-prefix rejection in `parse_module_manifest` (`tools/validate_architecture_gates.py` ~1415–1456), with a test for the duplicate case and a test asserting same-module nesting still resolves by longest match. Update the input-contract docstring (lines ~175–177) to state all three cases explicitly.
2. Update the nested-prefix test's in-file "ASSUMPTION (documented, not independently confirmed)" comment to cite this record instead.
3. Clear the 3 remaining Ruff findings (`RUF100` ×2, `ISC004`) — style only. **Do not** mass-fix the 12 `E501` findings in the same diff; they are the interrupted session's lines and would bloat the review surface.
4. Author the fixture-scoped gate-2 evidence set from verdict A (items 1–5), each artifact labeled fixture-scoped.
5. Verify the unresolved premise in A.4 — whether any committed CI workflow invokes `--gate module-deps` with repo defaults — and report it. **Do not change CI in the same dispatch.**

Out of scope for that dispatch, explicitly: `contracts/modules/ownership.json` (owner-reserved, verdict A); the gate-2 input-contract ADR (lead's own next dispatch, verdict B); any scenario promotion; any commit.

Independent assurance that follows, in order:

| Order | Role | Artifacts in scope | Must settle |
|---|---|---|---|
| 1 | `veyro-code-reviewer` | `tools/validate_architecture_gates.py` (gate-2 code paths only: `parse_module_manifest`, `load_module_manifest`, discovery, import resolution, SQL scan, rule 7), `tools/tests/test_validate_architecture_gates.py` gate-2 tests, `GATE2-MODULE-DEPS-REPAIR-CHECKPOINT-2026-10-05.md` §6, and this record | Whether verdict C's three-case rule is correctly implemented and whether the repair's three fixes are sound. This record is an **input**, not an approval — the reviewer may dissent, and a dissent is adjudicated by a fresh lead dispatch, not by the implementer. |
| 2 | `veyro-scenario-reviewer` | `SCN-MOD001-006 / -007 / -095 / -096` against the fixture-scoped evidence set | Whether fixture-scoped positive + negative proofs satisfy each scenario's acceptance text, and whether the "real-tree DEFERRED" limitation is disclosed on the face of every artifact. Cannot start before review 1 closes. |
| 3 | `veyro-gatekeeper` | Not yet. | Gatekeeper certifies MOD-001 as a module, not a single gate. Invoke only when all seven architecture gates plus `GOV-01-R04`'s remaining pipeline stages have evidence. |

---

## Owner-reserved vs engineering split (summary)

**ENGINEERING CHOICES decided in this record:** (A) defer real-tree domain ownership and accept gate 2 fixture-scoped; (A.4) treat the missing-manifest fail-closed result as a legitimate negative proof; (B) the fixture-scoped input contract is a MOD-001 implementation artifact, with an ADR recommended for ADR-010 parity and authorable without owner approval; (C) accept same-module nesting, reject exact duplicates with a named error, reject cross-module overlap with no exception; (D) the sequencing and assurance scope above.

**UNRESOLVED OWNER-RESERVED DECISION — not decided here:**

> **BLOCKED: OWNER_APPROVAL_REQUIRED** — committing `contracts/modules/ownership.json` with domain-code and owned-table-prefix bindings for the six `backend/app/modules/` scaffolds. Restriction: *no material product, pricing, business, architecture, or scope change without explicit owner approval* (`.claude/rules/global/owner-reserved-restrictions.md` item 4; `CLAUDE.md` owner-reserved paragraph). Per DC-09 this also requires an ADR recorded before implementation. The `payment` and `pos` bindings are additionally ungrounded engineering proposals with no verified governing source. Nothing in MOD-001's `GOV-01-R04` acceptance criteria depends on this being unblocked.
