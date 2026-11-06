# Owner decision — internal CAP execution is unmetered; no further envelope approvals

**Status: OWNER-DIRECTED DECISION; NOT OPERATIONALLY EFFECTIVE until this exact record receives independent exact-subject Opus review, first-publication owner attestation under the rule in force, non-force publication, and successful exact-SHA push CI.** Until all four are done nothing in it is granted, and once done it validates nothing taken before. It is not module acceptance, not a Ready judgment, not a capability activation, not a Scenario Review or product PASS, and it approves no DC-16 reserved action.

**No `Covers` or `Actions` header is present, deliberately.** No `Actions`, because this record approves no reserved action: it removes an internal orchestration ceiling, not a spending control, and `governance/registry.json` `reserved_actions` is unchanged and unnarrowed. No `Covers`, because the record **edits no file**. It supersedes clauses of other records prospectively by its own authority; superseding is not editing, so it needs no path coverage, and every `OWNER-*` path stays frozen.

## Owner source

The directive is the owner's, given directly in the Claude Code session on 2026-11-06 and relayed to this record by the orchestrating session; it is not checked here against an original message, and no chat message ID is exposed or invented. The operative statements, quoted:

1. "I permanently authorize unlimited INTERNAL CAP orchestration minutes, model tokens, implementation attempts, and routine engineering review consumption for Veyro product development."
2. "I do not want to approve additional CAP envelopes ever again. The internal CAP budget must no longer be a stop condition for product development."
3. "Replace internal CAP token and time ceilings with: INTERNAL_CAP_MODE = UNMETERED … This is a policy concept, not a requirement to invent a configuration key."
4. "Do not delete, reset, rewrite, or disguise past CAP usage or exhausted envelopes. Keep historical records as evidence of past execution. Make the new policy explicitly prospective … Do not fabricate unused budgets or retrospectively alter previous outcomes."
5. "Unlimited INTERNAL CAP is not permission to incur unlimited financial charges … Do not purchase additional API credits, subscriptions, cloud resources, or paid services without separate explicit authorization. Actual provider rate limits and session restrictions remain applicable. Do not misrepresent those limits as removable project restrictions."
6. "Do not create replacement mechanisms that simply rename the same approval requirement."
7. "Preserve authorization checks, meaningful security controls, and truthful product acceptance evidence."
8. "If a historical owner-reserved rule requires an authenticated owner amendment, prepare the complete replacement decision and its exact-byte attestation workflow as a single indispensable personal action. Do not silently bypass the effective owner-authentication mechanism."
9. "Update the necessary canonical project instructions, ADRs, owner policies, module plans, CAP documents, validation logic, and tests. Make only the changes required to eliminate internal CAP exhaustion as a future development blocker."

Statement 8 is why this record exists in this form rather than as a self-applied change: the clauses below sit in published `OWNER-*` records, which ADR-0001 decision 5 reserves to the owner, so an authenticated owner act is the only valid route. It is also the last such act this policy requires.

## 1. The policy

**`INTERNAL_CAP_MODE = UNMETERED`.** For every remaining Veyro module, MOD-004 through MOD-074, internal CAP orchestration minutes, model tokens, qualification attempts and routine engineering review consumption are **unmetered and are not a stop condition**. No internal resource ceiling blocks product development, and no internal resource replenishment requires an owner decision.

This is a policy concept. **No configuration key is created and no code changes**, because none is needed. Verified rather than assumed: nothing in `tools/` or `.github/workflows/` compares CAP minutes or tokens against a limit. What exists there is unrelated — `veyro-foundation-ci.yml` has a CI job `timeout-minutes`, `tools/mission_runner/control.py` has a document-size budget for status output, and `tools/mission_runner/runner.py` has token *telemetry* for model-routing verdicts plus the retired runner's per-task `max_attempts` and wall-clock `timeout`. None of those is a CAP ceiling, so none is touched. The validator is not touched, no test is changed, and no new mechanism is introduced.

**Measurement may continue for visibility and must not gate anything.** Recording what a piece of work cost remains useful and is encouraged; a recorded figure is now an observation, never a limit, never a trigger for an owner request, and never a reason to stop.

## 2. What is superseded, prospectively and exactly

Each clause below is superseded **from this record's effective date forward only**. The text stays in its record, unedited, and stays true of the period it governed. This list is exhaustive of what this record supersedes.

1. **`OWNER-2026-11-06-mod004-cap-and-implementation-authorization.md` §1** — the ceiling of "at most 180 active orchestration minutes and 400,000 model tokens", together with control 4 ("The first newly exhausted limit immediately stops qualification work, returns the gap to `BLOCKED: CAPABILITY_GAP` and escalates … No renewal, rollover, silent reset or second candidate set is authorized") and control 5 ("stop rather than presume remaining budget"), **to the extent those operate as a stop condition or as a requirement for a further owner envelope.** Controls 1, 2 and 3, which require honest and separate recording of use, survive as measurement obligations with no gate attached. Control 6, barring new custom Skill or Rule creation, is untouched. **The "or second candidate set" bar inside that quotation is NOT superseded**: a second candidate set is a scope limit, not a resource ceiling, and it stays in force even though it would "stop" work on a second candidate.
2. **`OWNER-2026-10-19-mod004-cap-budget-exception.md`** — the ceiling of "at most 45 active orchestration minutes and 50,000 model tokens" and "The first newly exhausted limit immediately stops further qualification work and returns the gap to `BLOCKED: CAPABILITY_GAP` and Opus-lead escalation." Its "Quality gates retained" paragraph is untouched.
3. **`OWNER-2026-10-29-minimal-local-runner-architecture.md`** — the envelope half of "no CAP task is eligible without a new owner envelope and the outstanding pre-pull/security decisions." **Only the envelope half.** The pre-pull and security half is not touched here; it was addressed, on its own disclosed terms, by §2 of the 2026-11-06 authorization record, and whatever that section did or did not settle is unchanged by this one.
4. **`OWNER-2026-11-05-delegation-activation-and-exception-closure.md`**, the "What is reserved and nondelegable" item reading "**A new CAP envelope.** The owner personally stating a new metered figure in active orchestration minutes and model tokens, as the one prior envelope did … This record resets, qualifies and grants no CAP budget." **That reservation is superseded in full**, because it is precisely the recurring-approval dependency statements 1, 2 and 6 remove. Nothing else in that record's reserved list is touched: every other item there — the DC-16 actions, pre-pull security approval, further custom Rule creation, the frozen baseline, owner-record publication, module acceptance, the D16 count and the rest — stays reserved exactly as written.
5. **`OWNER-2026-10-19-mod004-s0-only.md`** — from "MOD-004 CAP qualification stays PAUSED and BLOCKED. The one-time 50,000-token envelope is exhausted; no additional budget, candidate, image/wheel pull or install, accounting remediation, review retry or D12.3a use is authorized": the **PAUSED-and-BLOCKED work stoppage** and the **"no additional budget"** bar. **Only those two.** The bars on an additional *candidate*, on image/wheel pull or install, on accounting remediation, on review retry and on D12.3a use are **not** superseded here; the pull and install question was addressed by §2 of the 2026-11-06 authorization record on its own terms, and the others are scope limits rather than resource ceilings and stay in force.
6. **`contracts/engineering/module-capabilities.yaml`** — `default_orchestration_budget_minutes: 45` and `token_budget_when_observable: 50000` cease to be ceilings and stand as historical record. **The file is not edited by this record**, because those fields cite EIP ¶601, ¶607 and ¶11821, which are frozen pinned text: the EIP is not edited, and its paragraphs keep saying what they say. What is superseded is their enforcement as an internal stop condition in this project, which is an owner policy choice and not a claim about the pinned source.

**The recorded overruns stand as history and are not forgiven, reset or recharacterised.** `knowledge/03-Modules/MOD-004/CAP-ENVELOPE.md` records 427,621 tokens charged against 400,000; `OWNER-2026-10-19-mod004-cap-budget-exception.md` records the 45-minute dimension and `OWNER-2026-10-19-mod004-s0-only.md` records the 50,000-token envelope exhausted; earlier attempt use for the CAP gap stays UNKNOWN, not zero. All of that remains exactly as written, and this record does not say those limits were met or were sufficient.

**What is lifted, stated precisely.** The **exhaustion-driven work stoppage** is lifted prospectively: work may resume, and no internal resource figure may stop it again. **The gap remains `BLOCKED: CAPABILITY_GAP`.** That state is not only the exhaustion stop — it is also the manifest's `result_if_unresolved` for four OPEN blockers, and this record closes none of them. B3 and B6 keep their recorded open items, B7 is open with the ADR-0006 draft's three blocking findings unremediated, and `BLK-CON04-PRIVILEGED-CONSOLE-REVIEW` is untouched. Resuming work is what changes; the blockers close only on evidence, under §3 of the 2026-11-06 authorization record.

## 3. What is NOT superseded, and why

The owner asked for only the changes required. These were examined and deliberately left in force, because none of them blocks MOD-004 and each does real work.

- **`max_custom_creation_attempts_per_gap: 1` for `BLK-RULE-QUALIFICATION`, recorded as reached.** It caps the *creation* of new custom Rules. That blocker closes by **qualifying** the two Rules that already exist — path-scope tests, runtime-negative tests, independent review — and qualification is not capped by anything. So the cap is not a blocker, and removing it would loosen a quality control for no gain. No new custom Rule creation is authorized.
- **`max_external_candidate_evaluations_per_gap: 2`.** This is a per-gap field across all four gaps, and the manifest records usage as null, meaning unknown rather than zero, for the CAP, SKL and CON-04 gaps. It is still not a blocker on the S1 path: the CAP gap's candidate set is fixed and selected, the migration-lint tool for the SKL gap is built in-house rather than evaluated as an external candidate, the RULE gap closes by qualification, and CON-04 is outside S1. Left in force.
- **Whether the two D16 correction cycles survive the 2026-10-30 infrastructure failure.** A design-lineage question about a recorded failure, not an internal resource budget, and not on the MOD-004 S1 path. It stays owner-reserved and unresolved, and no root may be renamed to obtain a consumed attempt.
- **The consumed S0 one-write and one-review limits.** Scope limits on a specific published slice, not resource budgets. No second S0 write is authorized.

## 4. No replacement approval mechanism

Per statement 6, this record creates no successor envelope, no renewal procedure, no periodic resource review, no spend checkpoint, no attempt allowance and no "qualification checkpoint" needing owner sign-off — nothing that reproduces the removed requirement under another name. **After this record is effective, no internal CAP renewal requires the owner's participation, ever.** With §2.4 superseded, no published record reserves a CAP envelope to the owner; an agent must not ask for one, and must not invent a gate that has the same effect.

The orchestrating session chooses technical approaches, qualification sequencing, testing strategy and reasonable resource consumption autonomously, and selects its own next task — **on the existing limits of that delegation, which this record does not widen.** "Next task" keeps the meaning `OWNER-2026-11-05` gives it: a task, lane or budget that a record closes, exhausts, reserves or leaves ambiguous is not eligible, save where §2 above has now superseded the exhaustion. "Testing strategy" keeps the limit §6 of the 2026-11-06 authorization record gives it: it reaches sequencing and depth, **not coverage obligations**, and does not reach the EIP §9.1 scenario and QA set, the ADR-0002 D6.6 and D9 isolation tests, or the release-gate evidence.

## 5. Real spending controls, unchanged

Unlimited internal execution is not unlimited money, and the distinction is the point of this section.

- **The four DC-16 reserved actions stay reserved**: `spend-paid-activation`, `production-promotion`, `material-product-business-change`, `real-member-data`. `reserved_actions` is unchanged.
- **No purchase of API credits, subscriptions, cloud resources, managed databases, paid tiers or any paid service**, without separate explicit owner authorization. Work continues on the owner's existing Claude subscription and the resources already available.
- **Provider and platform limits are real and are not removable by any project record.** Claude plan usage limits, rate limits, context windows and session limits constrain what can actually be done, and this record does not touch them. **Misrepresenting any of them as a project restriction this policy lifts is forbidden.** When one of them stops work, the honest report is that a provider or session limit stopped it — not that a budget was exhausted, and not that it can be waived.

## 6. Reconciliation required, because the ceilings are also stated outside the owner records

The first-publication lane permits only this one new file in its commit, so nothing else can be corrected here. But the ceilings and the stop state are recorded in several live documents, and **an agent reads some of those before it reads any owner record**. Left alone, they would keep CAP exhaustion alive as a development blocker in exactly the places that matter most. Each of the following must be reconciled prospectively, in its own reviewed change, once this record is effective, preserving every historical figure and the recorded overrun as history:

1. **`CLAUDE.md`** (its "Product security and testing" section), which states that per `OWNER-2026-10-29` "no CAP task is eligible without a new owner envelope … no CAP budget was reset". This is the most important one: it is the instruction file a session reads first.
2. **`knowledge/03-Modules/MOD-004/CAP-ENVELOPE.md`**, which states the 180/400,000 ceiling as granted, restates the stop rule, is headed "STOPPED — token limit exhausted", records the gap `BLOCKED: CAPABILITY_GAP`, and describes what "a new envelope" would buy and that it is the owner's own act. Its ledger, its 427,621-of-400,000 figure and its metering-limits disclosure are history and **must be preserved**; what changes is that the stoppage no longer applies.
3. **`knowledge/03-Modules/MOD-004/REQUIREMENTS.md`**, which quotes the `OWNER-2026-10-29` envelope clause as live and lists "A new CAP envelope in metered active orchestration minutes and model tokens" first among the owner-reserved items.
4. **`contracts/engineering/mod004-s0-scenario-qa.md`**, which states that "the MOD-004 CAP budget is exhausted and the module stays blocked".
5. **`contracts/engineering/module-capabilities.yaml`**, whose two budget fields are superseded as ceilings by §2.6 and should be annotated as historical rather than deleted, since they cite frozen EIP paragraphs.

None of these may be edited without review, and none may be edited in a way that deletes, resets or disguises a historical figure. Where a document records what was spent or that a limit was passed, that record stays.

## 7. Preserved, unchanged

- **Product security**, binding: tenant isolation and RLS, authentication and AAL-3, immutable audit, financial integrity, residency and retention, independent product review, validation at trust boundaries that fails closed, and negative tests that actually fail closed. **No test is deleted or weakened because it fails, and no material security or correctness finding may be waived to end a review.**
- **Truthful acceptance evidence.** No gate is recorded as passed that did not pass. Module acceptance stays owner-reserved, an agent never decides it, MOD-005 stays locked until MOD-004 is accepted, and MOD-001, MOD-002 and MOD-003 stay conditional Foundation-scope acceptances with `GOV-02-R01..R08` at `product_pass: false`.
- **Capability activation still requires evidence**, under §3 of the 2026-11-06 authorization record: all four blockers closed by evidence actually produced, with independent review, and no ACTIVE row or evidence ID written ahead of what it names. Unmetered execution makes the work affordable; it does not make it done.
- **Authorization checks.** ADR-0001 is unamended. The validator's Reserved-Action, Owner-Approval, frozen-path, self-authorization and first-publication checks are **not weakened, narrowed or bypassed**, by this record or by the change that publishes it. Publication of any `OWNER-*` record remains an admin-authenticated owner act.
- **The frozen baseline** — `PROJECT_INDEX.md`, the three `.docx` files, `veyro-product-experience-design/` — and every `OWNER-*` path.
- **Historical review outcomes** stand and are never rewritten, softened or reinterpreted: the D16 lineage's `CHANGES_REQUESTED` reviews, the two screen-ownership reviews, the 2026-11-02 ¶8740 review with F1-F8, the two 2026-11-05 migration reviews, the ADR-0006 draft's `CHANGES_REQUESTED` with its three blocking findings, and the `CHANGES_REQUESTED` on this record's own earlier draft. Remediating any of them is ordinary work, not a budget question.
- **The retired runner** is not restarted, repaired, rebuilt or replaced. Claude Code stays the sole repository writer. GitHub Actions stays CI/CD only and authorizes nothing.
- **Preserved evidence trees** — `/Library/Application Support/Veyro/**`, `~/Library/Application Support/Veyro/**`, `/Users/Shared/veyroworker/**`, `~/Veyro-Migration-Archive-*/**` — stay byte-for-byte intact and read-only.
- **No third-party dependency** beyond what §2 of the 2026-11-06 authorization record scopes, on that record's own terms.

## Publication and proof

Five obligations, in order; a later one does not substitute for an earlier one.

1. Independent exact-subject Opus review of the exact bytes of this file.
2. The first-publication attestation, written by the owner outside the repository once the reviewed bytes are final: owned by uid 0, writable by neither group nor others, carrying the owner's own `owner_choice_quote` and a non-empty `source_prompt_message_id`, and binding this record's path, its exact SHA-256 and the current `HEAD`. Any later change to these bytes voids the review and the attestation and repeats both.
3. The local checks in `CLAUDE.md`, each as a separate command, with real output reported.
4. `check-change` in first-publication mode: this record staged as the only change in an otherwise clean tree, its path piped on stdin, `--decision OWNER-2026-11-06-internal-cap-unmetered` and `--first-publish-owner-attestation <file outside the repository>`. Any result other than PASS stops publication.
5. One commit containing only this file, a non-force push to `main`, and a completed `success` push-event CI run on that exact SHA.

The attestation is an operator-held statement, not cryptographic proof of the owner's message, and a PASS records that statement and nothing stronger.

## Not claimed

- Not module acceptance, not a Ready judgment, not a capability activation, not a Scenario Review PASS, not a product or security PASS, not a CI result.
- Not a claim that any past budget was sufficient, met, or unexhausted, and not a reset of any counter.
- Not closure of any CAP blocker, and **not a change to the gap's `BLOCKED: CAPABILITY_GAP` state**, which rests on four OPEN blockers this record does not close. What is lifted is the exhaustion-driven work stoppage.
- Not permission to spend money, purchase any service, or exceed provider limits, and not a claim that provider or session limits can be waived.
- Not authorization for UI-bearing MOD-004 work, nor for any controlled-path change, nor for a lockfile change.
- Not an answer to OWNER-Q1, OWNER-Q2 or ADR-0002 D15.10 Q1-Q8, and not a resolution of the D16 correction-cycle question.
- Supersedes no review outcome; the supersessions in §2 are of resource ceilings and the recurring-approval dependency only, and are listed there exhaustively.
