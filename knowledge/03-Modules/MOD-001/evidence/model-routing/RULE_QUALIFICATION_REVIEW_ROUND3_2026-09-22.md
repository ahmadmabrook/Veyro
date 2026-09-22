---
doc: RULE_QUALIFICATION_REVIEW_ROUND3
status: LIVE
module: MOD-001
reviewed: 2026-09-22
---

# Round 3 — independent qualification review of `RULE-001`..`RULE-009`

**Session type:** review-only, per explicit mission scope. No rule file
re-authored. No implementation slice started. MOD-002 not started.
MOD-001 not marked approved.

## Bootstrap re-verified fresh this session

- `git fetch` + `git status`: local HEAD == `origin/main` at
  `d3ce17ad42978761a0294909509e772444d5352d` ("fix: close remaining
  BUG-035 infra rule P1"), confirmed before any action.
- `verify_baselines.py`: PASS, 4/4 governing baseline hashes match
  `PROJECT_INDEX.md`.
- `CURRENT_STATE.md` front matter re-confirmed MOD-001
  `IMPLEMENTATION IN PROGRESS`; `BUG-035`'s own file re-confirmed
  `status: OPEN`; `CAPABILITY_REGISTRY.md` re-confirmed `RULE-001`
  through `RULE-009` all at `BLOCKED`.
- `git show d3ce17a --stat` confirmed the owner's round-3 patch touches
  **only** `.claude/rules/infra/iac.md` (+21/-18 lines), removing the
  round-2 `actions/*`/`github/*` trusted-publisher carve-out entirely.

## Dispatch

Fresh-context `veyro-security-reviewer` (Opus, no memory of rounds 1 or
2), briefed with the round-1/round-2 finding history and the exact
round-3 diff, instructed to re-ground every check in the cited
`EIP_MIRROR.md`/`TSD_MIRROR.md`/`IMPLEMENTATION.md`/`REQUIREMENTS.md`/
`CAPABILITY_POLICY.md` text directly rather than trust the rule files'
own quotations, and explicitly told not to expand into a general
rewrite or P2/editorial hunt.

## Verdict returned: P0=0, P1=1, P2=7, Editorial=3 — BLOCKED

**P1-A (round 2's finding) is genuinely CLOSED.** `iac.md` control 5 no
longer grants any publisher-based exemption — every GitHub Action,
"regardless of publisher — including `actions/*` and `github/*`", is
now required to clear the full `CAPABILITY_POLICY.md` 9-stage lifecycle
(independent Opus evaluation, positive/negative qualification, an
`APPROVED CAP-<NNN>` registry row) before a workflow referencing it may
merge, with no `OWN-<NNN>`/in-rule exemption of any kind. Cross-checked
directly against `CAPABILITY_POLICY.md` line 30's verbatim "no exemption
of any kind" clause and `OWNER_APPROVALS.md` (no relevant `OWN-<NNN>`
entry exists that the rule could be relying on). The rollback-override
(`release.md` control 1) and backend transaction/idempotency/
reconciliation coverage (`architecture.md` control 7 / `api.md` control
8) closures from round 2 were independently re-verified against their
primary sources and confirmed unregressed by the `iac.md`-only patch.

**A new P1 was found — P1-Q: no stage-5 qualification evidence exists
for any of the 9 rule files.** `CAPABILITY_POLICY.md` stage 5 requires a
recorded positive test (capability does the claimed thing on a synthetic
fixture) and negative test (correctly refuses/fails on an out-of-scope
input) before a capability may become `ACTIVE`/`APPROVED` — "Both
results recorded as evidence" in `knowledge/05-QA/capability-evidence/`.
Stage 6 states a Skill/Rule "cannot become `ACTIVE` based only on a
description... it must have passed stage 5 first." `skl-rule-id.schema.yaml`
applies this to `RULE-<NNN>` records by name.

Independently verified by this orchestrating session, not taken on the
subagent's word:
- `knowledge/05-QA/capability-evidence/` contains only `GOVERNANCE_DRILL/`
  and `CAP-001/`/`CAP-002/` subdirectories — no `RULE-*` evidence
  directory exists for any of the 9 files.
- `CAPABILITY_REGISTRY.md`'s `evidence` column for all 9 `RULE-<NNN>`
  rows cites only the three content-qualification review documents
  (`RULE_QUALIFICATION_REVIEW_2026-09-19.md`, `..._ROUND2_2026-09-19.md`,
  this file) — those are stage-4 independent-evaluation records, not
  stage-5 positive/negative test evidence.
- `BUG-035`'s own file (rounds 1 and 2) never raised or dismissed this
  gap — confirmed genuinely new to this round, not a re-litigation of a
  settled point.
- `shasum -a 256 .claude/rules/infra/iac.md` independently recomputed by
  this session: `c75409dce71febd0d40106a2a785840be3dc053f3700c2323cb8b5fd2561234c`
  — exact match to the reviewer's reported hash.

The reviewer also noted (P2, non-gating) that none of the 9 files
carries `paths:` frontmatter, which a path-scope positive/negative test
(EIP Appendix H.5) would also require — closing P1-Q's evidence gap
will need this addressed as part of the same fixture work, not as a
separate follow-up.

## Disposition

Per the mission's explicit "if and only if P0=0 and P1=0" gate, the
condition was **not** met (P1=1). `RULE-001` through `RULE-009` were
**not** marked `APPROVED`. `BUG-035` was **not** closed. No rule file
was re-authored (also structurally impossible this session —
`.claude/rules/**` remains owner-gated regardless). No further
implementation slice was started. MOD-002 was not started. MOD-001 was
not marked approved.

## Next legally allowed action

Produce and record, for each of `RULE-001`..`RULE-009`: (1) `paths:`
frontmatter (`backend/**` for the 5 backend files; `infra/**` plus
`.github/workflows/**` for the 4 infra files); (2) a positive test (the
rule's guidance is followed / its gate is checkable against a matching
synthetic case) and a negative test (a non-matching-path load check, per
EIP Appendix H.5), both recorded under
`knowledge/05-QA/capability-evidence/RULE-<NNN>/`; (3) an Opus
(`veyro-security-reviewer`) evaluation of that evidence, setting
`approved_by`/`approved_date`/a real `next_review_due` in
`CAPABILITY_REGISTRY.md`. Then, and only then, may `review_status` read
`APPROVED` and `BUG-035` close. Not Code Review, not Manual QA, not
Gatekeeper certification, not MOD-002, not a further implementation
slice.
