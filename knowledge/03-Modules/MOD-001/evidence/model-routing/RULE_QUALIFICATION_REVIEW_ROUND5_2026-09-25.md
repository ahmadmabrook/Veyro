---
doc: RULE_QUALIFICATION_REVIEW_ROUND5
status: LIVE
updated: 2026-09-25
---

# BUG-035 Round 5 — Independent Qualification Review (final gate)

**Governed HEAD reviewed:** `8e90680e8e8bcbd86e5136b6181371ac8161eee7`
(confirmed by this session's own `git rev-parse HEAD`/`git rev-parse
origin/main` before dispatch, and independently re-derived by the reviewer
itself rather than taken on trust from the dispatch brief — the brief
stated `14d1337`, which the reviewer correctly identified as one commit
stale; `8e90680` only added Stage-5 evidence/registry files and touched
nothing under `.claude/rules/**`, so all findings bound to `14d1337`
carry over unchanged).

**Reviewer/model:** `veyro-security-reviewer` (Opus tier per
`DEVELOPMENT_CONSTITUTION.md` model routing), fresh context, no memory of
rounds 1-4, no participation in producing any of the Stage-5 evidence or
prior remediations under review.

**Scope:** the 9-file rule family (`RULE-001` through `RULE-009`) and its
Stage-5 qualification evidence, per the 8-point check list in the
dispatch brief (metadata validity; `RULE-002` global-scope legitimacy;
`RULE-004` backend-scope correctness; Stage-5 evidence freshness;
positive/negative/path-scope sufficiency; re-confirmation of all prior
P1 closures a-g; disposition of the 2 carried-forward observations;
detection of any new P0/P1). Explicitly P0/P1 scoped — P2/Editorial
findings recorded but non-gating, consistent with rounds 1-4.

## Verdict

**APPROVED: P0=0, P1=0.** P2=3, Editorial=1 (all disclosed, non-blocking,
carried forward as residuals — see below).

## Findings

**P2-1 (new, fixed same session).** The evidence files for RULE-001,
RULE-003, RULE-005, RULE-006, RULE-007, RULE-008, and RULE-009 called
`183acd5` "current governed HEAD" — stale the moment `8e90680` (which
added those very files) was committed. Not P1: nothing that makes the
evidence stale *in substance* occurred (all 9 rule files are byte-for-byte
identical across `183acd5`/`14d1337`/`8e90680`, independently confirmed by
SHA-256 recomputation matching `CAPABILITY_REGISTRY.md`'s recorded
hashes). **Fixed by this orchestrating session** immediately after the
review, in the same 7 files, re-verified against primary sources
(`shasum -a 256`, direct file reads) — not taken on the reviewer's word
alone.

**P2-2 (carried from round 4, re-confirmed, not closed).**
`observability.md`'s control 1 governs every validator MOD-001 builds,
and those live under `tools/**`, outside this rule's `infra/**`/
`.github/workflows/**` paths — `RULE-003`'s own path-scope positive
fixture (`infra/ci/rls_lint_validator.py`) is not where the real RLS-lint
tool actually lives (`tools/validate_architecture_gates.py`). Kept P2 on
the same reasoning as round 4: EIP §4.3 scopes Infra/SRE to
"infra/**, CI and observability"; `IMPLEMENTATION.md` treats `tools/**`
as a known-infrastructure path with no assigned profile; and each
individual validator tool is already bound to its own control in
`IMPLEMENTATION.md` §3's "Failure evidence" column.

**P2-3 (carried from round 4, re-confirmed, not closed).**
`concurrency.md`'s body text says `backend/**` but its `paths:` frontmatter
is the narrower `backend/**/*.py`, missing raw `.sql` migration/schema
files. `database.md`'s own `backend/**` scope already covers schema files,
and this project's migrations are planned as Alembic `.py`, so this is a
narrow, disclosed residual, not a coverage gap with a live consequence
today.

**Editorial-1 (new, not fixed — non-blocking).** `iac.md` and
`observability.md`'s H1 headings still read "(`infra/**` binding)" and
omit `.github/workflows/**`, even though both rules' body text explicitly
covers CI workflow changes and their frontmatter includes that glob. A
label-completeness issue, not a scope contradiction (unlike the
round-4-follow-up H1/frontmatter defect that blocked round 4's own
evidence) — left as a disclosed residual per the review's own P0/P1-only
mandate.

## Check-by-check results

**1. Metadata validity/consistency:** PASS for all 9 files. YAML valid;
H1/frontmatter/body agree except Editorial-1 (label-completeness only)
and P2-3 (glob narrower than prose, disclosed).

**2. RULE-002 (`secrets.md`) global scope — ACCEPTED.** Tested against
EIP H.5's actual clause (`EIP_MIRROR.md` lines 20819-20821: "tested
against representative matching and non-matching paths so path scoping is
correct and does not pollute unrelated contexts"). Correctness: control 1
bans committed secrets "in source, config, fixtures, test data, or
documentation" — inherently repo-wide; no narrower path list would be
correct, and this project's own history (a near-miss credential-shaped
literal in a `knowledge/05-QA/` evidence file, 2026-09-22) demonstrates
the real need for unconditional coverage. Non-pollution: controls 2-3 are
inert outside their own applicable contexts, don't conflict with any
other rule, and the token cost is immaterial — the same shape as this
project's existing global rules (`owner-reserved-restrictions.md`,
`notion-mcp-scope-discipline.md`). `N/A (scope: global)` accepted as a
valid Stage-5 disposition — a global-scope rule has no non-matching path
by construction, so PASS/FAIL don't apply.

**3. RULE-004 (`release.md`) backend scope — CONFIRMED CORRECT, no
overshoot.** `backend/**/*.py` reaches the Stage-5-qualified rollback-
trigger fixture `backend/app/main.py` (`IMPLEMENTATION.md` lines 103-124,
426). No rollback/canary tooling is planned under `tools/**`, so no
under-scope gap. Controls loaded on backend Python add constraints only,
grant no privilege — not the kind of scope broadening `CAPABILITY_POLICY.md`
warns against.

**4. Stage-5 evidence freshness:** `RULE-002`/`RULE-004` bound to
`14d1337`, hashes match. `RULE-001`/`003`/`005`/`006`/`007`/`008`/`009`
were bound to `183acd5` (P2-1, now fixed) — content-identical at
`8e90680`, so not stale in substance, only in binding-statement text.

**5. Positive/negative/path-scope sufficiency:** all 9 files carry a
success-path eval and a negative eval; 8 of 9 carry matching/non-matching
path-scope cases (`RULE-004` has 3, covering all 3 globs), `RULE-002`
correctly records `N/A`. Live, this-session evidence the loader mechanism
is real: `secrets.md` (global scope) loaded unconditionally at session
start, while `knowledge-vault-durability.md` (`paths: knowledge/**`)
loaded only once a `knowledge/` file was actually read.

**6. Prior P1 closures — all 7 re-confirmed still closed, no
regression:**
- (a) Manual rollback override carve-out: `release.md` control 1 retains
  its "no carve-out of any kind, including an audited one" language.
- (b) Backend transaction/outbox/reconciliation/idempotency coverage:
  `architecture.md` control 7 and `api.md` control 8(a-f), citations
  checked against `EIP_MIRROR.md` lines 1270-1277 and
  `REQUIREMENTS.md` line 584.
- (c) CI Action supply-chain / no-publisher-carve-out: `iac.md` control 5
  requires SHA-pinned actions with an APPROVED capability row, no
  carve-out language present; `OWNER_APPROVALS.md` has no exempting entry.
- (d) Registration: all 9 rows present in `CAPABILITY_REGISTRY.md`, all
  hashes match current files.
- (e) Stage-5 evidence exists for all 9 (produced 2026-09-22, re-run
  2026-09-25).
- (f) Path metadata present and valid for all 9; round-4's 2 scope gaps
  (P1-1/P1-2) confirmed closed.
- (g) Stale evidence binding: `RULE-002`/`RULE-004` closed at `14d1337`;
  the remaining 7 files' binding-text staleness reclassified P2 (P2-1)
  and fixed same session — not a re-opening of (g), a distinct,
  lower-severity instance of the same class.

**7. Two carried observations — neither promoted to P1:**
- (a) `RULE-002` non-pollution: fully satisfied — see check 2 above.
- (b) Nested-glob matching (whether `infra/**`/`backend/**` could match a
  non-root-anchored nested directory of the same name): no rule-loader
  implementation exists in this repo to test directly — it is a Claude
  Code harness mechanism, external to this project. Standard glob
  semantics anchor a mid-pattern slash to the project root, so this
  should not occur; this session's own read access to files under
  `.claude/rules/infra/` and `.claude/rules/backend/` did not trigger
  either rule family loading, which is weak supporting (not conclusive)
  evidence. No nested `infra/` or `backend/` directory exists or is
  planned anywhere in `IMPLEMENTATION.md`'s layout, so even if the
  observation were true it has no present effect. Not promoted: no
  present, material, implementation-blocking defect to cite.

**8. New P0/P1 scan:** none found. No unqualified third-party capability
trust introduced; no real-looking secret literal in any of the 9 rule
files or their evidence; owner-reserved spend/production restrictions
independently covered by `release.md` control 3, `iac.md` control 4, and
the global owner-reserved rule; no declared rule-to-rule dependency
cycle (`capability_dependency_ids: []` for all 9).

## Disposition

Per the governing mission's "if and only if P0=0 and P1=0" gate: **met.**
`RULE-001` through `RULE-009` are approved by this review. The
orchestrating session applies the resulting registry/status updates
(`CAPABILITY_REGISTRY.md`, `module-capabilities.yaml`, `BUG_REGISTRY.md`,
`STATUS.md`, `CURRENT_STATE.md`, `CURRENT_HANDOFF.md`) in the same commit
as this file, per this project's established practice of a reviewer
reporting findings and the orchestrating session (not the reviewer)
owning durable-state writes.

P2-2 and P2-3 (both carried from round 4) and Editorial-1 (new) remain
open, disclosed, non-blocking residuals for a future remediation pass —
not required for `APPROVED`, per this review's explicit P0/P1-only
mandate.
