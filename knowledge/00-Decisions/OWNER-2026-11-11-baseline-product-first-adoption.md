# Owner decision — adopt the product-first baseline revisions of the EIP and TSD

- Covers: Veyro_Engineering_Implementation_Plan_v2.0_Lean_Foundation.docx, Veyro_Technical_System_Design_v1.4.2_Foundation_Clarification.docx, PROJECT_INDEX.md

**Status: OWNER-DIRECTED DECISION; NOT OPERATIONALLY EFFECTIVE until this exact record receives
independent exact-subject Opus review, first-publication owner attestation under the rule in force,
non-force publication, and successful exact-SHA push CI.** Until all four are done nothing in it is
granted, and once done it validates nothing taken before. It is not module acceptance, not a Ready
judgment, not a capability activation, not a Scenario Review PASS, not a product PASS, and it
approves no DC-16 reserved action.

**`Covers` lists exactly the three frozen paths this record authorizes changing, and nothing else.**
An `OWNER-*` record's `Covers` is read only against the **frozen** set;
`tools/governance/governance_check.py` resolves a controlled path through
`CONTROLLED_CHANGE_UNREFERENCED`, which requires an ADR and rejects an `OWNER-*` stem. So
`governance/registry.json`, which §5's commit 2 also carries, is **not** covered here and is
authorized instead by ADR-0001, whose `Covers` already lists `governance/`; no new ADR is created.
No `Actions` header is present: this record approves no `spend-paid-activation`,
`production-promotion`, `material-product-business-change` or `real-member-data`, and
`governance/registry.json` `reserved_actions` is unchanged and unnarrowed.

## 1. Owner source

The directive is the owner's, given directly in the Claude Code session on 2026-11-11 and relayed
to this record by the orchestrating session. It is not checked here against an original message,
and no chat message ID is exposed or invented. The operative statements, quoted:

1. "I confirm my decision as the project owner: local product implementation and testing across
   MOD-004 through MOD-074 must not be blocked by acceptance of preceding modules."
2. "The updated Engineering Implementation Plan and Technical System Design express my intended
   development policy."
3. "Proceed with the existing baseline-adoption workflow."
4. "Once the updated baselines are formally effective, reconcile the conflicting module-lock
   instructions and extend the development lane using the authorized ADR mechanism."
5. "Continue independently authorized MOD-004 product work in the meantime. Do not restart
   previously completed reviews or create unrelated governance tasks."

A second message in the same session, sent after the orchestrating session put §5's publication
hazard to the owner, adds the statements §5 now implements:

6. "I do not authorize intentionally publishing a failing commit to main."
7. "Keep main green throughout the baseline adoption process."
8. "Find the smallest valid, authorized way to atomically adopt the updated baselines and reconcile
   PROJECT_INDEX.md with governance/registry.json without an intentionally failing main commit."
9. "If the existing validators make that impossible, identify the exact conflicting rules and
   prepare the minimal necessary correction through the authorized change process. Do not bypass
   checks, falsify evidence, or weaken product security."
10. "Preserve both DOCX files byte-for-byte and keep all existing product commits intact."
11. "After successful baseline adoption, eliminate the obsolete local-development restrictions
    consistently across the repository and resume actual product development, including MOD-005
    through MOD-074."
12. "Consolidate any remaining owner-authenticated action into one precise request. Do not restart
    completed reviews or create unnecessary governance loops."

**Statement 9's condition did not arise.** The validators do not make an atomic green adoption
impossible, so no validator correction is necessary and none is proposed. §5 sets out why, and the
reasoning is the part of this record most worth attacking on review.

The same message states: "Do not treat this message as a substitute for any required authenticated
attestation." That instruction is honoured — §6's attestation is a separate act, and this record is
not effective without it.

## 2. What this record authorizes

Exactly one thing: replacing the bytes of the two baseline documents named in `Covers` with the
owner-edited revisions already present in the owner's working tree, and re-pinning their SHA-256
rows in `PROJECT_INDEX.md` to match. The bytes are identified by hash so that this authorization
cannot drift onto different content:

| Path | Currently pinned | Authorized replacement |
|---|---|---|
| `Veyro_Engineering_Implementation_Plan_v2.0_Lean_Foundation.docx` | `b82e56f88a3b5cc5ba486fe8d10b2d04e8153ce227729e9ba6a92debe15d894f` | `4c77b460a23ec0ade1b7b289ed645d52bb34f9087f4c2cb337e5c2d7fdbd3f38` |
| `Veyro_Technical_System_Design_v1.4.2_Foundation_Clarification.docx` | `e0bef7cf2c42885fa35825343ff9b18bbf8fe4996ea72ac38a594752a8c69d33` | `16ae089bb4d59c8a125a3667440c0a42c3c25924eb882e2d004e0c4dc9f4370b` |

`Gym_OS_Master_Product_Blueprint_v1_English.docx` and `veyro-product-experience-design/` are
**not** covered and are not changed. Any content other than the two hashes above is outside this
authorization and needs a new record.

## 3. What the adopted revisions change, as measured

Stated so that the owner attests to a described change rather than to an opaque pair of hashes. The
orchestrating session extracted both revisions and diffed them: **28 changed hunks in the EIP, 5 in
the TSD, every one process, gate or lifecycle text.** No domain fact changes; specifically, no TSD
hunk touches ¶741-783 (§7.3 data isolation, §7.5 placement and relocation) or ¶1194-1245 (§10.1
PLT-01), so no MOD-004 tenancy statement is altered by this adoption.

What the revisions do:

- Replace the EIP's `NON-NEGOTIABLE DEVELOPMENT GATE` header with a `PRODUCT DEVELOPMENT OVERRIDE`
  and a `DEVELOPMENT AND RELEASE SEPARATION` paragraph, and add a `MODULE UNLOCK` paragraph to the
  §8 unlock rule.
- Restate DC-01 from "One active implementation module" to "One primary acceptance module", and
  change Implementation/QA WIP-1 to acceptance/integration WIP-1.
- Move DC-02 Ready, DC-03 Scenario Catalog and DC-09 ADR-before-implementation from preconditions
  of implementation to preconditions of acceptance or release.
- Change roughly sixty module rows from `LOCKED / Not started` to
  `NOT STARTED / LOCAL DEVELOPMENT ALLOWED; acceptance pending`.
- Loosen the §4.2 capability-resolution bound from "at most two external candidates and one custom
  project Skill/Rule creation attempt per capability gap" to a risk-proportionate formulation.
- Move NEW-02's baseline-hash verification from "before implementation; mismatch fails closed" to
  "before release of changes that depend on the baseline; mismatch blocks only affected changes".
- Rewrite the session start and end checklists to drop the document-review and inventory steps.
- In the TSD: add a `PRODUCT-FIRST ARCHITECTURE POLICY` header, narrow the change rule to material
  changes affecting deployed contracts, narrow the audit instructions from whole-document to
  change-scoped, move the CMP-iOS qualification deadline from "before feature-scale mobile
  implementation" to "before mobile release qualification", and narrow the PLT-02 critical-controls
  sentence and its INV-PLT-02 restatement to production change control.

What the revisions leave unchanged, verified in the edited bytes: DC-16's four owner-reserved
actions; the REVISION PRECEDENCE sentence preserving the tenant, financial, security, external,
owner-reserved and production release gates; DC-10's evidence-over-assertion rule; and every domain
contract, invariant and release-gate requirement.

**The revisions' own words on their standing are preserved and not improved upon.** Both documents
keep the sentence "Original v1.4.1 historical independent-audit results in this document do not
certify this revision. Full executable certification must occur after clean rebuild." The EIP's new
override paragraph itself ends "This section expresses the desired owner policy; effectiveness in
the live repository still requires the established baseline adoption procedure" — this record is
that procedure, and adopting the bytes makes the policy effective without making the documents
independently certified.

## 4. What this record does not do

The list is not closed, and an item's absence is not permission.

- **It does not reconcile the module locks, does not extend the development lane, and does not
  itself remove any obsolete local-development restriction elsewhere in the repository.** The
  owner's statements 4 and 11 sequence all of that **after** the baselines are formally effective,
  by the authorized ADR mechanism. `OWNER-2026-11-07-local-domain-slice-lane.md` §5.4 delegates adding a
  lane root for another module to an accepted ADR citing ADR-0001 with its own review, and says no
  new owner record is needed per module. That same record's §6 states "MOD-005 stays locked until
  MOD-004 is accepted", which the adopted EIP's `MODULE UNLOCK` paragraph addresses for local
  implementation only. Resolving that tension is the ADR's work, on the record of both documents as
  they then stand; this record neither performs it nor prejudges it.
- **It makes no module Ready and accepts no module.** MOD-004 is not Ready and is not accepted;
  MOD-001, MOD-002 and MOD-003 stay conditional Foundation-scope acceptances with
  `GOV-02-R01..R08` at `product_pass: false`; MOD-000 stays accepted.
- **It activates no capability and closes no blocker.** `contracts/engineering/module-capabilities.yaml`
  stays PROVISIONAL with `gate_eligible: false` and the same four OPEN blockers:
  `BLK-CAP-POSTGRES17-PSYCOPG-POOL-RUNTIME`, `BLK-SKL-MIGRATION-LINT`, `BLK-RULE-QUALIFICATION`,
  `BLK-CON04-PRIVILEGED-CONSOLE-REVIEW`. Those are technical qualification work, and no baseline
  wording closes them.
- **It authorizes no capability pull, install, dependency or spend.**
  `OWNER-2026-11-06-mod004-cap-and-implementation-authorization.md` §2 is untouched, its condition 1
  stays assessed NOT MET on four limbs, and the no-third-party-dependency bar on `tools/`,
  `backend/app/l10n/` and the S0 slice stands.
- **It does not weaken a security or correctness invariant.** Tenant isolation and RLS,
  authentication and AAL-3, immutable audit, financial integrity, residency and retention, and
  independent review of substantive product code remain binding at their actual risk boundary. The
  adopted revisions move *when* local implementation may begin; they do not move what acceptance or
  release requires.
- **It does not retroactively validate anything.** Every historical review outcome stands as
  recorded, including the four `CHANGES_REQUESTED` reviews in the MOD-004 D16 lineage and the
  lane's own preserved outcomes. Nothing published before this record becomes authorized by it.
- **It approves no DC-16 action.** `spend-paid-activation`, `production-promotion`,
  `material-product-business-change` and `real-member-data` stay owner-reserved and are not
  exercised here.

## 5. Sequencing: two commits, both green

**An earlier revision of this section said one knowingly red commit on `main` was unavoidable, and
put that to the owner as a choice. That claim was wrong**, and the owner's statements 6 to 8
rejected the choice rather than answering it. The correction below needs no validator change, no
exception and no bypass, and it is recorded in this form because the mistaken claim had already
reached the owner.

**Why the red window looked unavoidable.** `PROJECT_INDEX.md` is frozen while
`governance/registry.json` is controlled, and `check --root .` raises `INDEX_DRIFT` whenever the
index's bytes and the registry's `index.sha256` disagree — so the two must move together or some
published state is red. The apparent bar was the rule that a change "mixing frozen and controlled
paths is BLOCKED (one decision cannot be both): split it, no path goes unchecked."

**Why it is not.** Read against the code, that is not a rule about commits. `check_change` has no
notion of a commit: it classifies the paths piped to it on stdin and runs two independent blocks,
one requiring `--decision` to be an `OWNER-*` stem whose `Covers` lists every frozen path, the
other requiring it to be an ACCEPTED ADR covering every controlled path. A mixed pipe fails only
because a single `--decision` cannot be both at once — the docstring's "one decision cannot be
both" is that emergent consequence, not a per-commit prohibition. Nothing forbids one commit from
carrying both classes, checked in two runs over disjoint path sets, and **every path is then
examined under a decision that genuinely covers it**, which is what "no path goes unchecked"
requires. It is strictly more checking than a mixed pipe, which examines nothing and only ever
returns BLOCKED. ADR-0001 is the controlled authority and already exists: its `Covers` lists
`governance/`, so no new ADR is created here.

**Two commits, both green. Only the attestation in §6 is the owner's.**

1. **This record alone**, published under §6. Adding an owner record drifts nothing, so `main`
   stays green.
2. **The baseline change, atomically**: both `.docx` restored from the preserved copies, both
   re-pinned rows in `PROJECT_INDEX.md`, and `governance/registry.json`'s `index.sha256`, in one
   commit. `INDEX_DRIFT` therefore never exists in any published state. Citing this record inside
   its own commit would return `CHANGE_SELF_AUTHORIZING`, which is why commit 1 is separate.

Commit 2's checks, each with its negative control, so that no `PASS` is cited without evidence it
could have failed:

- the three frozen paths with `--decision OWNER-2026-11-11-baseline-product-first-adoption` → PASS;
  the same pipe with `--decision ADR-0001` → BLOCKED, `FROZEN_BASELINE_CHANGE`.
- `governance/registry.json` with `--decision ADR-0001` → PASS; the same pipe with this record's own
  stem → BLOCKED, `CONTROLLED_CHANGE_UNREFERENCED`.

**Measured before publication, not predicted.** The orchestrating session built the exact atomic
state on a clone outside the repository and ran it: all four `PROJECT_INDEX.md` rows bind to their
live bytes; `check --root .` PASS with no `INDEX_DRIFT`; both gate runs PASS and both negative
controls BLOCKED; and `compileall`, `workflow_check`, the governance suite (110), the trusted-gate
suite (169), the domain-closure suite (114), the lane closure check and the screen-contract identity
check all green. `PROJECT_INDEX.md`'s new sha256 is
`8d5cb82fd1e04b89e6c9c9d68671f8899247d856c1d7630a524342e9917295a7`, which is the value commit 2
writes into `governance/registry.json`.

**What is deliberately not updated, and why that is not stale evidence.**
`contracts/engineering/module-capabilities.yaml`'s `source.eip_docx_sha256` and ADR-0002's Context
both record the EIP bytes those documents were derived from when they were written. `eip_docx_sha256`
occurs nowhere but the manifest itself, so nothing validates it, and both references remain
historically accurate as provenance. Rewriting them would misstate what their authors read.

**A fact that bears on what the re-pin is worth.** CI's "MOD-001 product source-binding negative
check" only asserts that `tools/governance/source_baseline.py` *refuses* correctly — `NOT_PINNED` at
exit 1, and two refusals to pin at exit 2 — against a temporary unpinned file. It never positively
verifies the four baselines against `PROJECT_INDEX.md`. So the agreement between the documents and
their pins is kept by the `CLAUDE.md` discipline of verifying before deriving work, not by a gate.
Committing new document bytes without the re-pin would leave CI green while silently breaking the
binding, which is why commit 2 carries all four paths together and why the positive verification
above was run by hand.

## 6. Publication and proof — the one manual step

**Obligation 0.** Every other change in the working tree is committed and pushed first, and the two
edited `.docx` are preserved outside the repository and the pinned bytes restored in the tree, so
that the tree holds nothing but this record when obligation 4 runs. `tree_state_problem` requires
that HEAD and the index differ only by this one added path **and that every tracked working file
match its index blob byte for byte**, and `check_first_publication` additionally requires
`git status --porcelain --untracked-files=all` to hold exactly one entry, staged `A `. A tracked
modification anywhere — including the owner's own `.docx` edits — returns
`FIRST_PUBLISH_BLOCKED`. The preserved copies are restored in step 2 of §5 and their SHA-256
re-verified against §2's table before that commit.

Then five obligations, in order; a later one does not substitute for an earlier one. **Only
obligation 2 is the owner's**; the rest are the orchestrating session's.

1. Independent exact-subject Opus review of the exact bytes of this file.
2. **The owner's single manual action.** Once the reviewed bytes are final, the owner writes the
   first-publication attestation outside the repository: a JSON object with exactly the keys
   `schema`, `owner_id`, `source`, `owner_choice_quote`, `source_prompt_message_id`, `record_path`,
   `record_sha256` and `expected_head`, all strings, with `schema` = `veyro.owner-attestation/1`,
   `owner_id` = `gateway-owner`, `source` = `owner:direct:admin-attested`, `record_path` =
   `knowledge/00-Decisions/OWNER-2026-11-11-baseline-product-first-adoption.md`, `record_sha256` the
   SHA-256 of this file's exact bytes, and `expected_head` the then-current `HEAD`. The file must be
   owned by uid 0 and writable by neither group nor others, so it is written under admin
   authentication. `owner_choice_quote` and `source_prompt_message_id` must be the owner's own; an
   agent never supplies or infers them, which is why this step cannot be delegated.
3. The local checks in `CLAUDE.md`, each as a separate command, with real output reported.
4. `check-change` in first-publication mode: this record staged as the **only** change in an
   otherwise clean tree, its path piped on stdin, `--decision
   OWNER-2026-11-11-baseline-product-first-adoption` and `--first-publish-owner-attestation <file
   outside the repository>`. Any result other than PASS stops publication.
5. One commit containing only this file, a non-force push to `main`, and a completed `success`
   push-event CI run on that exact SHA. Then §5's commit 2, with its own review, its own two gate
   runs and negative controls, and its own exact-SHA CI.

The attestation is an operator-held statement, not cryptographic proof of the owner's message, and
a PASS records that statement and nothing stronger. Any later change to these bytes voids the
review and the attestation and repeats both.

## Not claimed

- Not module acceptance, not module Ready, not a capability activation, not a Scenario Review PASS,
  not a Gatekeeper verdict, not a security PASS, not a product PASS, not manual-QA or TestSprite
  evidence.
- Not independent certification of either adopted revision. Both documents' own STATUS line says
  the historical audit results do not certify them, and that sentence survives this adoption.
- Not a reconciliation of the module-lock instructions and not a lane extension; both are
  sequenced after effectiveness, by ADR, per the owner's statement 4.
- Not closure of any manifest blocker, and no CAP, SKL or RULE evidence ID.
- Not a finding that `OWNER-2026-11-06` §2 condition 1 is met; it is assessed NOT MET on four limbs
  and this record does not revisit it.
- Not authority for any path outside `Covers`.
