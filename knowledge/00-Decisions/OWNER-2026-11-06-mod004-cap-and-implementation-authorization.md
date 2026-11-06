# Owner decision — MOD-004 CAP envelope, pre-pull disposition and S1 implementation authorization

**Status: OWNER-DIRECTED DECISION; NOT OPERATIONALLY EFFECTIVE until this exact record receives independent exact-subject Opus review, first-publication owner attestation under the rule in force, non-force publication, and successful exact-SHA push CI.** Until all four are done nothing in it is granted, and once done it validates nothing taken before. It is not module acceptance, not a Ready judgment, not a Scenario Review PASS, not a product PASS, and it approves no DC-16 reserved action.

**No `Covers` or `Actions` header is present, deliberately.** No `Actions`, because this record approves no `spend-paid-activation`, `production-promotion`, `material-product-business-change` or `real-member-data`; the owner's words are "subject to existing subscription limits and no additional paid spending", so §1's envelope is an internal orchestration budget inside an existing subscription, not paid activation. `governance/registry.json` `reserved_actions` is unchanged and unnarrowed. No `Covers`, because an `OWNER-*` record's `Covers` is read only against the **frozen** set: `tools/governance/governance_check.py` resolves a controlled path through `CONTROLLED_CHANGE_UNREFERENCED`, which requires an ADR, and piping `.github/workflows/veyro-foundation-ci.yml` with this record's own stem returns `BLOCKED` / `CONTROLLED_CHANGE_UNREFERENCED` with the detail that the stem "is not an ADR in knowledge/00-Decisions". A `Covers` list here would therefore have been inert for every path this record discusses, while reading like a permission. **Changes to controlled paths under this record still need an accepted ADR**; see §5.

## Owner source

The directive is the owner's, given directly in the Claude Code session on 2026-11-06 and relayed to this record by the orchestrating session; it is not checked here against an original message, and no chat message ID is exposed or invented. The operative statements, quoted:

1. "Approved: 180 minutes / 400,000 tokens as the internal CAP envelope, subject to existing subscription limits and no additional paid spending."
2. "From now on, select reasonable internal engineering budgets and operational parameters autonomously. Do not ask me to choose between options you can evaluate yourself."
3. "Prepare the required owner-attestation record and request only the indispensable manual authentication step."
4. "Once authenticated, resume MOD-004 product implementation immediately and continue autonomously. Do not stop for routine decisions or unnecessary review cycles."
5. "My absolute priority remains completing the product, from MOD-004 through MOD-074."

The owner also said the orchestrating session may modify any file and change any policy so as to continue without returning with questions. From the same owner's earlier standing directive of 2026-11-06 (its date is as relayed and is not verifiable from the repository), two clauses bind this record and are quoted in full: "Do not falsely claim that a governance restriction has been lifted when it remains legally or procedurally effective. If an owner-reserved decision must be changed, follow the already established owner-authenticated publication mechanism rather than bypassing its controls." And: "Never initiate additional paid spending without my explicit approval."

This record therefore does not treat the blanket statement as authority over the items under "Reserved and unchanged". Where it does supersede a live reservation, it says so in the open, quotes the reservation, and states what is being accepted, so that the owner's attestation of these bytes is an informed one. **§2 is the one place it does that. Read §2 before attesting.**

## 1. CAP envelope

For the single gap `BLK-CAP-POSTGRES17-PSYCOPG-POOL-RUNTIME` and the one fixed candidate set recorded in `contracts/engineering/capability-records/CAP-001-mod004-d123a-prepull.md` and `mod004-d123a-wheel-lock.txt`, the Capability Manager may use a prospective envelope of **at most 180 active orchestration minutes and 400,000 model tokens**.

"Active orchestration minutes" is the unit the prior envelope used, carried forward by this record; the owner's words were "180 minutes", and the conversion to the metered unit is this record's, not the owner's.

Controls, carried forward unchanged from `OWNER-2026-10-19-mod004-cap-budget-exception.md`:

1. The envelope is incremental and separately metered from this record's effective start. Historical use stays recorded as historical use, including the portions recorded UNKNOWN. **No counter is reset.** The prior 45-minute / 50,000-token envelope stays recorded as exhausted.
2. Before the first qualification action, record the effective publication SHA and CI evidence, the start time, and zero new-envelope use, separately from the unchanged historical counters.
3. Count all gap-specific active orchestration time and model tokens against it, evidence gathering and review included. Unknown new usage is **not** treated as zero.
4. The first newly exhausted limit immediately stops qualification work, returns the gap to `BLOCKED: CAPABILITY_GAP` and escalates to the Opus lead. No renewal, rollover, silent reset or second candidate set is authorized.
5. If telemetry is unavailable or new usage cannot be reconciled, **stop rather than presume remaining budget.**
6. **No new custom Skill or Rule creation attempt is authorized.** `BLK-RULE-QUALIFICATION` has its creation cap reached under both the per-gap and the per-rule counting readings, and this record grants no reset and no additional creation attempt. Distinct and **not** barred: *qualifying* the two rules that already exist, which is the path-scope tests, runtime-negative tests and independent review its `qualification_state` names. Qualification is not creation.

## 2. Pre-pull disposition — this record supersedes a live owner reservation, in the open

**What is being superseded.** `OWNER-2026-11-05-delegation-activation-and-exception-closure.md`, under "What is reserved and nondelegable", states: "**Pre-pull security approval.** The owner's decision is outstanding. The Opus review of the pre-pull dossier is recorded as approving document accuracy only, not the pre-pull security gate." `OWNER-2026-10-29-minimal-local-runner-architecture.md` adds that "no CAP task is eligible without a new owner envelope and the outstanding pre-pull/security decisions", and `OWNER-2026-10-19-mod004-cap-budget-exception.md` that "a pre-pull security approval is a separate decision supported by its own evidence."

**This record supersedes that reservation, for this one candidate set and this one scope only**, and delegates the pre-pull security decision to the orchestrating Claude Code session. The owner's statements 2 and 4 are the authority. This is stated here rather than inferred quietly, because an independent review of an earlier draft found that burying it would leave the owner attesting to a delegation the record did not disclose.

**What is being accepted, stated plainly.** CAP-001 §4 records, as supplied and reviewer-unverified assertions, that for the pinned `postgres:17` image a read-only OSV/Debian-tracker pass over the SBOM gave **139 OPEN Debian bookworm CVEs** (85 unassigned urgency, 53 unimportant, 1 low) with incomplete mapping; that publisher signature status and exact package licence closure are OPEN; that OpenSSL **3.5.8 is affected by 13 CVEs fixed in 3.5.9, including HIGH CVE-2026-84782 (DTLS)**, with whether the wheel embeds 3.5.8 UNKNOWN; that bundled libpq 18.6, MIT Kerberos 1.22.2 and OpenLDAP 2.6.14 CVE status is UNKNOWN; that LGPL-3.0 obligations are unassessed; and that psycopg wheel cryptographic provenance is absent/unverified. **Zero vulnerabilities is not claimed by this record and no safety pass is asserted.**

**The scope that makes that acceptable, and the limit of it.** CAP-001 itself frames the judgment as one of "applicability and risk for loopback-only synthetic qualification". The authorization here is exactly that and no more: a local, loopback-only qualification container holding synthetic fixtures, with no network listener reachable off the host, no real member data, no production or staging use, and no promotion of these artifacts to any deployed environment. **Production or deployed use of this image or these wheels is not authorized by this record and remains a DC-16 `production-promotion` matter reserved to the owner.** If any of the three preceding sentences stops being true of how the artifacts are used, this disposition no longer covers that use.

**Conditions, none waived.** The delegated decision may be exercised only when:

1. CAP-001 blockers **B2, B3, B4 and B6** are closed by evidence actually produced and recorded: free-runtime terms; image provenance, licence closure and CVE applicability; wheel and transitive hashes re-checked against PyPI; and the `psycopg-binary` bundled-library inventory with its CVE status and LGPL-3.0 obligations.
2. **B5** keeps its meaning: an independent Opus reviewer performs its own fetch verification of B3 and B4 rather than reading the Capability Manager's summary. A reviewer that cannot fetch says so and approves nothing.
3. **B1** (CAP owner) is recorded as the orchestrating Claude Code session. That session is an accountable owner only in the sense of being the sole repository writer and the party that produced the evidence; it is not a legal or organizational owner, and the owner remains the accountable party for the capability's presence in the project.
4. **B7** (D4.3 driver and database selection) is an engineering decision and is delegated, but ADR-0002 excludes D4.3 from its accepted scope, so recording the selection is an **ADR amendment on a controlled path** and needs an accepted ADR citing ADR-0001 plus its own independent review. See §5.
5. **The qualification runtime must be Colima.** The Docker Desktop context must not be used for any part of this work. At the time of this record `colima` 0.10.3 is installed at `/opt/homebrew/bin/colima` and `colima status` reports it is not running, while `docker context show` reports `desktop-linux`, i.e. Docker Desktop, whose licence is not unconditionally free. Confirm the active context is Colima before any pull. This keeps the work inside the owner's "no additional paid spending" instruction; Docker Desktop would put it next to `spend-paid-activation`, which stays reserved.
6. **The qualification interpreter is pinned by path.** The lock targets `cp313` / macOS arm64; on this machine `python3` is 3.14.5 and `/opt/homebrew/bin/python3.13` is 3.13.13, the version CAP-001 names. Use the explicit 3.13 path, in an isolated virtual environment.

**Pull authority.** ADR-0002 D12.3a is the only pre-existing exception to the install and pull bar, and it is recorded "[INFERENCE / ENGINEERING DECISION; CONDITIONAL; NOT IN FORCE until its conditions are met]", taking effect only after its own bound exact-diff Opus APPROVED review and exact-SHA push CI. The sole in-repo evidence that those conditions were met is CAP-001's own line labelled "(runner-supplied, UNVERIFIED from this sandbox)", and its three identifiers — the review id, the commit and the CI run — appear nowhere in the repository except that line. **This record therefore does not rely on D12.3a and makes no finding that it is in force.** The pull authority is this record's own, in its own words, limited to: the four pinned requirements at their pinned hashes under `--require-hashes --only-binary=:all:`, plus the `postgres:17` image, into the isolated local qualification environment described above. Four wheels and one image. No other package, no extras, no managed or cloud PostgreSQL, no account creation, no paid tier. Nothing is pulled until conditions 1-6 and the remaining CAP-001 §6 execution controls hold.

## 3. Capability manifest activation

Once §2 is exercised and its evidence independently reviewed, the orchestrating session may activate the MOD-004 row of `contracts/engineering/module-capabilities.yaml`, **scoped to the backend/data profile for the S1 slice only**, on all of the following and not before:

1. `BLK-CAP-POSTGRES17-PSYCOPG-POOL-RUNTIME` closed by the §2 evidence, with a real CAP evidence ID.
2. `BLK-SKL-MIGRATION-LINT` closed by a migration-lint tool that exists, is qualified by the ADR-0002 D5 mutation corpus, and has an independent review, with a real SKL evidence ID. An SKL ID may not be recorded before the tool and its corpus exist.
3. `BLK-RULE-QUALIFICATION` closed by *qualifying* RULE-001 and RULE-002 — matching and non-matching path-scope tests, runtime-negative tests, independent review — per §1.6. No new rule is created.
4. `BLK-CON04-PRIVILEGED-CONSOLE-REVIEW` **stays OPEN and is not closed by this record.** It gates the CON-04 Internal SaaS Console surface, which does not exist and is not built in S1. The activated row therefore selects the **backend/data profile only**, does **not** select the Internal SaaS Console profile, and authorizes no console or UI code. The row must say so on its face, in the manner of the S0 precedent's `ACTIVE_FOR_S0_ONLY`.

An ACTIVE row, or any evidence ID, written ahead of the evidence it names is a false record and is forbidden. Activation needs its own independent review.

## 4. Ready, and what Ready here does and does not mean

The Ready judgment against EIP ¶749-750 — "Dependencies satisfy the permitted §18 dependency state; scope/requirements/screens identified; module spec drafted; environment/tool access available" — is delegated for the **S1 backend/data slice**, on the criteria genuinely being met and on an independent Opus review saying so. Ready is a criteria check, not acceptance.

**The open preconditions, named rather than left implicit.** ADR-0002 lists unmet prerequisites (a)-(h), and its checklist item 8 requires the D14 screen-ownership mapping to be reviewed "before Ready is judged"; the ¶8740 justification review of 2026-11-02 returned CHANGES_REQUESTED, and two of its matters — finding **F3** and the **ADM-SET-06** domain-authority conflict — are owner actions this record reserves at "Reserved and unchanged". Those two are not closed here and are not closable by an agent.

**The resolution, and its limit.** The S1 slice is backend and database only: roles, schemas, RLS, the two platform tables, the two D6.3 functions, migrations, the tenancy primitive and their tests. It touches no screen, no route, no UI surface and no screen contract. The screen-ownership mapping, finding F3 and the ADM-SET-06 conflict bear on UI-bearing work and on Scenario Review, not on whether this backend slice's environment and spec are in place. ADR-0002 checklist item 8 is an engineering checklist item of that ADR, not an EIP ¶749-750 criterion, and this record supersedes it **only** to the extent of permitting a Ready-for-S1 judgment for the backend/data slice. It stays in force, unsuperseded, for every UI-bearing MOD-004 screen and for Scenario Review. **No CON-04, ADM-SET-01, ADM-SET-02 or ADM-SET-06 work may proceed on this record**, and a Ready-for-S1 judgment is not module Ready.

Where an EIP ¶749-750 criterion is itself unmet, no judgment may be issued: in particular "environment/tool access available" is unmet until §2 and §3 are done.

## 5. S1 implementation authorization

The owner's instruction "resume MOD-004 product implementation immediately" is code authorization for the MOD-004 S1 slice beyond the published S0 slice. **It takes effect once §3 activation and the §4 Ready-for-S1 judgment have been reached, each with its own independent review — not before.** This record makes no standing supersession of ADR-0002 D12's requirement of Ready plus an ACTIVE manifest: §3 and §4 are how that requirement is satisfied, not set aside. D12 stands and may not be cited as relaxed.

Within that, the orchestrating session may write, test and publish the S1 PostgreSQL isolation core in exactly:

- `backend/app/tenancy/**`
- `backend/tests/integration/tenancy/**`
- `backend/migrations/**` and `infra/db/**`
- the migration-lint tool required by §3.2

`backend/tests/**` is **not** authorized. The S1 test path in ADR-0002 and in the manifest's `repo_paths_surfaces` is `backend/tests/integration/tenancy/**`, and the wider glob would reach `backend/tests/test_tenancy_s0.py`, whose S0 one-write limit is consumed, and the MOD-001 and l10n tests. No second S0 write is authorized by this record or anything in it.

**Controlled paths still need an ADR.** Two changes S1 needs fall outside the list above and are **not** authorized by this record: adding a PostgreSQL service to `.github/workflows/veyro-foundation-ci.yml`, and declaring the selected driver in `backend/requirements*.txt` / `backend/requirements*.lock`. The first is a CONTROLLED path; the second carries the D4.3 selection of §2.4 and, under ADR-0002 D12.3a control 5, may not change during qualification, so it comes after qualification completes. Each needs an accepted ADR citing ADR-0001 for the ADR file itself, with its own independent review and the `check-change` gate run and shown. Until the workflow change lands, S1 integration tests are local-only and CI does not cover them, which must be stated plainly wherever S1 evidence is reported rather than left to look like coverage.

**Scenario Review stays blocked** by the Appendix F ¶8741 count/route/contract lint, which is unmet because the frozen source registry supplies no contract data. OWNER-Q2 is not answered here. The basis for implementing while it is blocked is **not** ¶8741's last sentence, which speaks of missing IDs and covers Ready and qualification artifacts rather than product implementation: it is EIP ¶755-758, under which Scenario Review precedes **Implementation Complete**. ADR-0002's unmet prerequisite (f) reads it as preceding S1 implementation and marks that reading an [INFERENCE]; **this record supersedes (f) for MOD-004 S1 only**, on the owner's statement 4, and leaves it otherwise in force. Consequently **Implementation Complete, Scenario PASS and module acceptance may not be claimed while Scenario Review is blocked**, however much S1 code exists.

**OWNER-Q1 is not answered here.** Its recorded default stands: no interim platform access log in S1. S1 remains nondestructive synthetic-fixture operations only, with no support or break-glass path, and the MOD-008 immutable audit stays required before any destructive or break-glass path.

## 6. Standing delegation of internal parameters

Selecting internal engineering budgets, timeouts, orchestration parameters, task ordering, review depth and testing approach is delegated to the orchestrating session, per the owner's statement 2. This reaches internal operating parameters only. It does not enlarge §1's envelope, create a second CAP envelope, grant a DC-16 action, touch a frozen path, authorize a controlled-path change, or reach anything under "Reserved and unchanged".

Two explicit limits. **Attempt allowances**: the delegation does not reach any attempt, correction-cycle, review-slot or budget count that a pinned source or a published record fixes — the D16 count, the §1.6 rule-creation cap and the consumed S0 one-write and one-review limits among them. Where two limits apply the smaller governs. **Testing approach**: the delegation reaches sequencing and depth, not coverage obligations. It does not reach the EIP §9.1 scenario and QA set, the ADR-0002 D6.6 and D9 isolation tests, or the release-gate evidence, none of which may be reduced.

Review depth is delegated above a floor that is **not** delegated: one independent Opus exact-diff review before publishing any product code change, plus independent review of the §2 evidence, the §3 activation and the §4 Ready judgment. Below that floor, frequency is the orchestrating session's call, per the owner's "Do not stop for routine decisions or unnecessary review cycles".

## 7. CLAUDE.md must be reconciled

On publication, `CLAUDE.md` states three things this record changes: "Add no third-party dependency", "Do not pull or install PostgreSQL, `psycopg` or `psycopg_pool`", and that MOD-004 code beyond the S0 slice needs Ready and an ACTIVE manifest. The first two are changed by §2 within §2's scope; the third is satisfied through §3 and §4 rather than removed. `CLAUDE.md` must be updated in its own reviewed change once this record is effective, so that the next session reads neither a prohibition that no longer holds nor a permission wider than §2 and §5 give. It must not be edited without review.

## Reserved and unchanged

The list is not closed, and an item's absence is not delegation of it.

- **The four DC-16 reserved actions** — `spend-paid-activation`, `production-promotion`, `material-product-business-change`, `real-member-data`. "No additional paid spending" is explicit, and `production-promotion` expressly covers any deployed use of the §2 artifacts. `reserved_actions` is not narrowed.
- **Module acceptance, for MOD-004 and every module, and the MOD-005 unlock.** An agent never decides module acceptance. MOD-005 stays locked until MOD-004 is accepted. MOD-001, MOD-002 and MOD-003 stay conditional Foundation-scope acceptances; `GOV-02-R01..R08` keep `product_pass: false`.
- **All UI-bearing MOD-004 work**: CON-04, ADM-SET-01, ADM-SET-02, ADM-SET-06, the D14 screen-ownership mapping review, finding **F3** and making the pinned extracts reachable, and the **ADM-SET-06** domain-authority conflict (ADR-0002 D15.10 Q1's V2 handoff and Q2). `BLK-CON04-PRIVILEGED-CONSOLE-REVIEW` stays OPEN.
- **The frozen baseline** — `PROJECT_INDEX.md`, the three `.docx` files, `veyro-product-experience-design/` — and every `OWNER-*` path.
- **Publication of any `OWNER-*` record**, including this one: an admin-authenticated act on the owner's machine. The attestation checks in `governance_check.py` are not weakened, narrowed or bypassed by this record or by the change that publishes it.
- **Amending ADR-0001**, and weakening the validator's Reserved-Action, Owner-Approval, frozen-path, self-authorization or first-publication checks.
- **Product security**, binding and unchanged: tenant isolation and RLS, authentication and AAL-3, immutable audit, financial integrity, residency and retention, independent product review, validation at trust boundaries that fails closed, and negative tests that actually fail closed. No test is deleted or weakened because it fails.
- **Regions, data-residency policy and KMS keys; retention durations, deletion approvers and quorum; hierarchy cardinalities, brand separation extent and template contents** where the Blueprint is silent.
- **Whether the two D16 correction cycles survive the 2026-10-30 infrastructure failure.** Not resolved, not re-counted. No root is renamed to obtain a consumed attempt.
- **Credential administration, worker identity and sudoers.**
- **The retired runner.** Not restarted, repaired, rebuilt or replaced by a new scheduler, broker, dispatcher or approval framework. Claude Code stays the sole repository writer. GitHub Actions stays CI/CD only and authorizes nothing. The runner-era lanes recorded SPENT stay spent.
- **The consumed S0 one-write and one-review limits**, and every other consumed limit.

## Preserved

Historical review outcomes stand and are never rewritten, softened, superseded or reinterpreted by this record: the D16 lineage's recorded `CHANGES_REQUESTED` reviews, the two screen-ownership `CHANGES_REQUESTED` reviews, the 2026-11-02 ¶8740 justification review with findings F1-F8, the two `CHANGES_REQUESTED` reviews recorded during the 2026-11-05 authentication migration, and the `CHANGES_REQUESTED` review of this record's own earlier draft. The 2026-10-30 D16 dispatch stays recorded as consumed on `attempts: 1 / max_attempts: 1`, failed on an infrastructure fault, producing a draft that was never reviewed and is not an approval.

No third-party dependency beyond the four pinned wheels and the one pinned image of §2 is added, and those are confined to the isolated local qualification environment: §2 is not authority to add them to `backend/requirements*.lock`, which §5 governs. The preserved evidence trees — `/Library/Application Support/Veyro/**`, `~/Library/Application Support/Veyro/**`, `/Users/Shared/veyroworker/**` and `~/Veyro-Migration-Archive-*/**` — stay byte-for-byte intact and read-only.

## Publication and proof

Five obligations, in order; a later one does not substitute for an earlier one.

1. Independent exact-subject Opus review of the exact bytes of this file.
2. The first-publication attestation, written by the owner outside the repository once the reviewed bytes are final: owned by uid 0, writable by neither group nor others, carrying the owner's own `owner_choice_quote` and a non-empty `source_prompt_message_id`, and binding this record's path, its exact SHA-256 and the current `HEAD`. Any later change to these bytes voids the review and the attestation and repeats both.
3. The local checks in `CLAUDE.md`, each as a separate command, with real output reported.
4. `check-change` in first-publication mode: this record staged as the only change in an otherwise clean tree, its path piped on stdin, `--decision OWNER-2026-11-06-mod004-cap-and-implementation-authorization` and `--first-publish-owner-attestation <file outside the repository>`. Any result other than PASS stops publication.
5. One commit containing only this file, a non-force push to `main`, and a completed `success` push-event CI run on that exact SHA.

The attestation is an operator-held statement, not cryptographic proof of the owner's message, and a PASS records that statement and nothing stronger.

## Not claimed

- Not module acceptance, not module Ready, not a Scenario Review PASS, not a Gatekeeper verdict, not a security PASS, not a product PASS, not manual-QA or TestSprite evidence.
- Not an Appendix F ¶8741 lint PASS, and not an answer to OWNER-Q1, OWNER-Q2 or ADR-0002 D15.10 Q1-Q8.
- Not a capability activation in itself: it authorizes one, on evidence, under §3, scoped to the backend/data profile.
- Not a supply-chain or security certification, not a safety pass, and not a verified-evidence finding for any CAP-001 blocker. Zero vulnerabilities is not claimed.
- Not a finding that ADR-0002 D12.3a is in force, and not authority for any pull beyond §2's own terms.
- Not authorization for any UI-bearing MOD-004 work, nor for any controlled-path change.
- Not approval of any DC-16 reserved action, and not authority over any frozen path.
- Supersedes no review outcome and resets no counter. The three supersessions it does make — the pre-pull security reservation in §2, ADR-0002 checklist item 8 for the S1 Ready judgment in §4, and ADR-0002 unmet prerequisite (f) for S1 in §5 — are stated in those sections and are limited to what they say.
