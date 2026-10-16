# MOD-002 — Candidate Foundation Acceptance Certificate

**Status: APPROVED — FOUNDATION ONLY, ACTIVATION PENDING OWN EXACT-SHA CI.**

The final independent gatekeeper approved this certificate for Foundation/Control structural scope only: runner task `mod002-foundation-gatekeeper-remediation-review-20261016`, MR-MOD-002-20261016-030, resolved model `claude-opus-5-5`, route VERIFIED, DONE/APPROVED. The approval is conditioned on candidate certificate SHA256 `68a593b1d0cccd79c16ad504e18606741d63feb7ac368e305b9db9c58c398ed4`, which the operator recomputed and found matching. That hash identifies the reviewed candidate version; this activation version differs from it only by the status and evidence updates described here.

The approval is not operative yet. Still required, in order: exact activation diff independent review, direct non-force push to `main`, and that activation commit's own exact-SHA push-event Foundation CI `success`. No future SHA or run is recorded here, and no CI or operational acceptance is claimed for this activation candidate. No owner action is recorded or asserted.

## Scope
Foundation only, risk class Foundation/Control. MOD-002 (Product, Architecture, Data & AI Governance; EIP v2.0 §21.3; TSD GOV-02 §10.55, Tier 2, confidential, tenant-scoped, INV-GOV-02, RB-GOV-02) covers the smallest enforceable checks for:
1. Source-of-truth: pinned `PROJECT_INDEX.md` hash and four authority rows in `governance/registry.json`.
2. ADR and change control: ADR format, status, supersession and controlled-path checks under ADR-0001.
3. Requirement ownership and traceability: one owner per GOV-02-R01..R08 and path-existence checks of evidence.
4. Approved frozen baseline: frozen paths and `OWNER-*` records that no ADR may change.

Implemented by `governance/registry.json`, `knowledge/00-Decisions/ADR-0001-governance-foundation.md`, `tools/governance/governance_check.py`, its tests, and the static `check --root .` step in `.github/workflows/veyro-foundation-ci.yml`.

The classification in the registry is concept metadata only. Prerequisite MOD-001 is header ACCEPTED — FOUNDATION ONLY, conditional on its own activation commit's exact-SHA CI; this certificate does not re-certify MOD-001.

## FOUNDATION mechanism is not product PASS
This certificate attests a structural mechanism only. It does not attest, and must not be read as attesting:
- product PASS for any requirement;
- full lifecycle governance (discovery, beta, GA, deprecation);
- design-system, accessibility, RTL or white-label governance;
- data quality, lineage, access control or real data handling;
- AI governance (approval, risk, evaluation, model change, oversight, incident response);
- full traceability (strategy to domain, flow, screen, event, test, metric); the 170 screen contracts remain deferred per the MOD-001 owner timing decision;
- portfolio prioritization workflows.

## Requirement status (GOV-02-R01..R08)
All eight are owned by MOD-002, registry status FOUNDATION, `product_pass` false. FOUNDATION means mapped and in scope for this foundation. It is not PASS, and it is not DEFERRED: no owner record approves deferring any of them, so none is silently marked DEFERRED.

| Req | Structural mechanism now | Still open, not claimed |
|---|---|---|
| R01 | One owner per requirement, checked against the module catalog | Product-area ownership beyond these eight records |
| R02 | ADR format, status, supersession, change-control checks | Service-boundary and dependency review workflows |
| R03 | Registry statuses only | Lifecycle stages and transitions |
| R04 | Mapping only | All design-system and accessibility governance |
| R05 | GOV-02 classification fields as concept metadata | Quality, lineage, access, real data |
| R06 | `ai_system: none` recorded | All AI governance workflows |
| R07 | Requirement-to-evidence path existence | Full traceability chain |
| R08 | Mapping only | All portfolio workflows |

## Evidence

### Existing CI runs (operator-verified)
- Commit `e0d14c1446700b127a8db090fbc85a6533a22cbe` (`e0d14c1`): push run 38898650825. The operator re-verified it with authenticated `gh` as a completed `success` push event on that exact SHA. It carries the governance work and the S3 CI wiring.
- ADR acceptance commit `d30478809397e71bd2cff85782d661ecbf2f7498` (`d304788`): push run 38901659772. The operator re-verified it the same way: completed `success` push event on that exact SHA.
- Correction of the gatekeeper's evidence limitation: the final gatekeeper (CHANGES_REQUESTED) treated the e0d14c1 run as unverified and only observed the runner `ci.json` snapshot for d304788 without a live query. The operator's `gh` verification above supersedes that limitation for both runs. This drafter did not query GitHub.
- These runs cover those SHAs only. They say nothing about the future certificate activation commit, whose own run is a separate and still-missing requirement.

### Local evidence (as reported in the task, not operator-verified here)
- 114 local runner/dashboard tests passed.
- 71 governance tests passed (also recorded in MOD-002.md).
- Static governance check `check --root .`: PASS.
- These are local results. This drafter did not re-run them for this document.

### Independent reviews, as recorded in the repository
- MR-MOD-002-20261016-009: S1 validator and tests, `claude-opus-5-5`, route VERIFIED, APPROVED. Approves S1 only.
- MR-MOD-002-20261016-012: S2 change, APPROVED. S2 only.
- MR-MOD-002-20261016-024: ADR-0001 decision text; recorded in the ADR `Review` header as APPROVED. The header is format-checked only; the validator does not verify the review exists in the runner.
- MR-MOD-002-20261016-017: runner task `mod002-dashboard-full-candidate-opus-r4-20261016`, S3 candidate (r4 exact candidate), `claude-opus-5-5`, route VERIFIED, APPROVED. MOD-002.md now records this ID in this activation candidate; runner state also holds it.
- MR-MOD-002-20261016-026: exact-diff review of the ADR-0001 acceptance candidate, `claude-opus-5-5`, route VERIFIED, APPROVED. Per the gatekeeper, that reviewer could not recompute the file SHA.
- None of these is a final module review or a review of the activation diff.

### Final gatekeeper results
- Earlier: runner task `mod002-final-foundation-gatekeeper-20261016` (`claude-opus-5-5`) returned **CHANGES_REQUESTED**. It found the mechanism sufficient for a Foundation-only scope but requested the EIP §21.3 manual QA demonstration, the LF-01 scenario matrix, an itemized security baseline, and certificate evidence labeling and accuracy fixes.
- Final: runner task `mod002-foundation-gatekeeper-remediation-review-20261016`, **MR-MOD-002-20261016-030**, `claude-opus-5-5`, route VERIFIED, **DONE/APPROVED**. It reviewed the remediation of those requests, manually assessed the operator-executed QA receipt, and approved the narrow Foundation/Control structural scope only: source-of-truth, ADR/change control, requirement ownership/evidence paths and frozen baseline. GOV-02-R01..R08 stay FOUNDATION with `product_pass` false.
- This approval is not a product PASS, not a tenant, privacy, AI, runtime, production or member-data certification, and not an owner-reserved action. It is not a review of the activation diff.

### Pinned source excerpts
- EIP v2.0 Lean Foundation `.docx` SHA256 `b82e56f88a3b5cc5ba486fe8d10b2d04e8153ce227729e9ba6a92debe15d894f`, §21.3, paragraphs 1861-1895.
- TSD v1.4.2 Foundation Clarification `.docx` SHA256 `e0bef7cf2c42885fa35825343ff9b18bbf8fe4996ea72ac38a594752a8c69d33`, GOV-02 §10.55, paragraphs 3990-4041.
- Read-only extraction: `mission-runner/reviews/mod002-source-card-excerpt-20261016.md` (runner state, outside the repo). The gatekeeper read this excerpt, not the `.docx` binaries.

### Manual QA demonstration (EIP §21.3, paragraph 1877)
Executed by the OpenClaw operator, not by Claude. Full JSON receipt: `mission-runner/reviews/mod002-manual-qa-operator-execution-20261016.json`, observed 2026-10-16T12:48:49Z at repo HEAD `d304788`, validator SHA256 `fc57c47b1dec937bfa931075c1300e4fbd68aa62bd179f639434f18fd6d5e220`. The Opus final gatekeeper (MR-MOD-002-20261016-030) manually assessed this operator-executed receipt and approved the narrow Foundation scope. Claude did not execute these shell commands.

| # | Command (`python3 tools/governance/governance_check.py ...`) | stdin | Exit | Result / code |
|---|---|---|---|---|
| 1 | `check-change --root <repo> --decision ADR-0001` | `governance/registry.json` | 0 | PASS, no violations (ADR/change-control positive) |
| 2 | `check-change --root <repo> --decision ADR-0099` | `governance/registry.json` | 1 | BLOCKED `CONTROLLED_CHANGE_UNREFERENCED` (ADR-0099 is not an ADR in knowledge/00-Decisions) |
| 3 | `check-change --root <repo> --decision ADR-0001` | `PROJECT_INDEX.md` | 1 | BLOCKED `FROZEN_BASELINE_CHANGE` (owner approval required; `--decision` must be an `OWNER-*` record) |
| 4 | `check --root <temporary copy>` with only GOV-02-R02 owner changed to MOD-001 | none | 1 | BLOCKED `REQ_OWNER_MISMATCH` (`GOV-02-R02: MOD-001 != MOD-002`) |

Case 4 ran on a copy of the repo excluding `.git` and cache; the copy was discarded and the live repo was not modified. Cases 1-3 ran against the live repo.

### LF-01 scenario applicability matrix (EIP paragraph 1875)
Foundation scope: a stdlib-only static validator, a registry, ADR files and a CI step. "Test" names are in `tools/governance/tests/test_governance_check.py`. Mapped means a concrete foundation check exists; it is not product PASS. No category is blanket PASS.

| Cat | Status | Basis |
|---|---|---|
| HP | Mapped | `test_valid_fixture_passes`, `test_valid_supersession_passes`; manual QA case 1 |
| VAL | Mapped | `test_invalid_status_and_deferred_shape`, `test_bad_adr_filename_and_duplicate_header` |
| NEG | Mapped | Blocked fixture tests; manual QA cases 2-4 |
| BND | Mapped | `test_evidence_escape_absolute_missing`, `test_malformed_paths_exit_2` (path boundaries only) |
| AUTHN | OPEN | No runtime, identity or session exists; first implementing product module |
| AUTHZ | OPEN | No runtime permission model; only the static rule that frozen paths need an `OWNER-*` record (case 3) is proven, and that is not runtime authorization |
| TEN | OPEN | No tenant data or tenant-scoped store exists; tenant isolation tests belong to the module that owns tenant data |
| SEC | Mapped (static only) | `test_evidence_symlink_file_and_dir`, `test_adr_symlink`, `test_registry_symlink_rejected`, `test_deferral_missing_self_and_unrelated_approval`, `test_product_pass_never_implied` |
| PRIV | OPEN | Classification is registry concept metadata; no privacy enforcement or real data exists |
| CONC | OPEN | No concurrent writer or aggregate versioning exists; only the single-process validator |
| IDEM | Mapped | `test_output_is_deterministic`: repeated runs give identical output. No command idempotency exists |
| NET | OPEN | The validator makes no network calls and there is no service to fail; network failure modes belong to product modules |
| PART | OPEN | No distributed or multi-step write path exists, so partial-failure behavior is not exercised |
| REC | Mapped (limited) | Fail-closed handling: `test_unreadable_index_fails_closed_for_change`, `test_malformed_paths_exit_2`; two-commit forward/revert correction is a process rule, not a runtime recovery |
| LIFE | Mapped | ADR status and supersession: `test_broken_supersession`, `test_valid_supersession_passes`, `test_duplicate_accepted_decision_key`; not product lifecycle (R03 open) |
| DATA | Mapped (limited) | Registry/ADR/requirement record consistency; no data store or real data |
| INT | Mapped | Registry-to-catalog-to-ADR-to-index consistency (`REQ_OWNER_MISMATCH`, `CONTROLLED_CHANGE_UNREFERENCED`, `test_inconsistent_supersession_in_other_adr_blocks_change`) |
| OBS | Mapped (limited) | Deterministic structured JSON result with stable violation codes; no runtime logs or metrics |
| ALT (optional) | Not claimed | Optional category; no alternate-path evidence offered |
| OFF | N/A | No offline-capable client or surface exists |
| LOC | N/A | No user-facing text or locale surface; Screens: None |
| A11Y | N/A | No UI exists; accessibility governance (R04) is open |
| PERF | N/A | EIP load/performance is N/A for this module |
| MIG | N/A | No database or schema exists to migrate |
| DR | N/A | No persistent runtime store; Tier 2 continuity concerns the future control-plane store, which does not exist |

### Mandatory security baseline (EIP paragraph 1885)
These are static validator and repository checks. No runtime exists, so no runtime control is demonstrated.
1. **authN/authZ:** none implemented and none claimed. The only authorization-like rule is the static `OWNER-*` requirement for frozen-baseline changes (case 3). Runtime authN/authZ is OPEN for product modules.
2. **Tenant isolation:** not applicable to the foundation because no tenant data or store exists. Not claimed; OPEN for the first tenant-owning module.
3. **Input/output data exposure:** the validator reads repo files and prints only violation codes and paths. It rejects symlinks, absolute and escaping paths, and `.git` paths (per gatekeeper review of the validator and tests). No user or member data is processed.
4. **Secrets/dependency hygiene:** validator is stdlib-only with no third-party dependency and no network calls. The workflow uses `contents: read` and `persist-credentials: false` (per gatekeeper review). No dependency scanner or secret scanner is claimed.
5. **Sensitive logging:** output is deterministic JSON limited to codes and repo paths. No runtime logging exists, so logging controls are not demonstrated.
6. **Privacy classification:** registry holds GOV-02 classification (confidential, tenant-scoped) as concept metadata only; it is not enforced at field or resource level. OPEN.
7. **Abuse-negative scenarios:** static negative cases exist: symlinks, path escape, self-authorization (`test_deferral_missing_self_and_unrelated_approval`), `product_pass` claims, frozen-path edits, unknown ADR and owner mismatch. Runtime abuse scenarios are OPEN.
8. **Static versus runtime:** everything above is static validation of repository content plus CI. No service, database, AI platform or runtime enforcement exists.

## Unresolved gaps and conditions
1. An exact-diff independent review of the activation commit is pending.
2. Activation requires a non-force push to `main` and that commit's own exact-SHA Foundation push-event CI `success`. The e0d14c1 and d304788 runs do not satisfy this. The dashboard current-head guard withholds operational acceptance until the tree is clean, pushed and its run completes.
3. `MOD-002.md` header is `ACCEPTED — FOUNDATION ONLY, CONDITIONAL ON OWN EXACT-SHA PUSH CI` and its stale lines (ADR-0001 status, S3 CI, review IDs, gates, next action) are updated in this activation candidate. The header is conditional, not operational, until condition 2 is met.
4. `check-change` is not CI-enforced; it is an operator-run local pre-push step after ADR acceptance.
5. Authority row hashes are not re-verified by the validator; that stays with the runner's out-of-repo pin.
6. `baseline.owner_decision` anchors only that the EIP `.docx` and `PROJECT_INDEX.md` stay unmodified. It approves nothing else.
7. EIP §21.3 and TSD GOV-02 §10.55 are cited from the pinned read-only source excerpt and the `.docx` hashes listed under Evidence. This drafter did not recompute the hashes or open the `.docx` files. The Opus gatekeeper manually assessed the operator-executed QA receipt (MR-MOD-002-20261016-030).
8. Two macOS sandbox tests skip on Ubuntu (carried from MOD-001), so CI does not cover that path.

## Not authorized and not claimed
- No production, tenant-isolation, privacy, member-data, AI or platform certification.
- No DC-16 reserved action taken (`spend-paid-activation`, `production-promotion`, `material-product-business-change`, `real-member-data`); no owner approval is asserted.
- No database, control-plane store, AI platform, product surface or runtime enforcement exists.

## Activation condition
In order:
1. Final independent gatekeeper verdict approves this Foundation-only scope. Done: MR-MOD-002-20261016-030.
2. Local checks pass for the activation commit, including `check --root .`.
3. Exact-diff independent review of the activation commit approves.
4. Direct, non-force push to `main`.
5. That commit's own exact-SHA push-event Foundation CI completes `success`.

If step 5 fails or is cancelled, the status is not advanced, and any correction is a new forward or revert commit with no force-push and no history rewrite.
