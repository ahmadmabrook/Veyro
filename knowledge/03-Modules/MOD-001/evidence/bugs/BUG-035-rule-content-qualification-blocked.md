---
doc: BUG-035
status: CLOSED
module: MOD-001
severity: P1 (blocks treating `backend/**`/`infra/**`/CI rule content as qualified/reliable; does not block non-backend/infra/CI implementation work)
opened: 2026-09-19
closed: 2026-09-25 (Round 5 — independent fresh-context `veyro-security-reviewer` returned P0=0/P1=0, APPROVED, for all 9 rule files)
---

# BUG-035 — 9 new `backend/`/`infra/` Rule files: independent qualification review returned BLOCKED (P0=0, P1=4, P2=8, Editorial=7)

## Finding

Per `knowledge/00-System/CAPABILITY_POLICY.md` (governs "every Skill,
**Rule**, Plugin, MCP server, hook, or script"; a capability "cannot
become `ACTIVE` based only on a description or a successful install; it
must have passed [qualification] first"; "No capability may become
`APPROVED` solely from a Sonnet implementation run"), the 9 rule files
`BUG-034` delivered (`.claude/rules/backend/{architecture,api,database,concurrency,performance}.md`,
`.claude/rules/infra/{iac,secrets,observability,release}.md`) required
independent Opus qualification review before being treated as reliable
governance content. A fresh-context `veyro-security-reviewer` (Opus)
dispatch ran that review and returned:

**P0=0, P1=4, P2=8, Editorial=7 — verdict BLOCKED.**

Full record: `knowledge/03-Modules/MOD-001/evidence/model-routing/RULE_QUALIFICATION_REVIEW_2026-09-19.md`.

The 4 P1 findings:

1. **`infra/release.md` control 1** permits an "explicit, authenticated,
   audited manual override" rollback trigger path that its own cited
   authority (`IMPLEMENTATION.md` §3's Canary row: "not a
   manually-callable endpoint") explicitly forbids, with no cited source
   authorizing the carve-out — a security-relaxing addition introduced
   by rule text alone, which `EIP_MIRROR.md:20631-20639` and DC-09 both
   require an ADR for.
2. **The 5 backend files cover none of H.3's "transaction/idempotency/
   reconciliation" element**, despite `architecture.md`/`api.md` both
   quoting the exact EIP §4.3 row that names it (behind an elided
   ellipsis), and MOD-001 already owning
   `tools/validate_idempotency_contract.py` as a blocking CI gate.
3. **The 4 infra files (governing `.github/workflows/**`) have no
   third-party CI-Action supply-chain control** (pin/provenance review),
   despite `secrets.md` protecting exactly the tier-scoped secrets such
   an action would touch, and Appendix H.4's "Third-party/community/
   unknown → BLOCKED until independent approval" row applying directly.
4. **Stage-7 registration gap** — orchestrator-side, no re-authoring
   needed; closed as part of this bug's own filing (see "Registration"
   below).

## Decision

Per the reviewer's own disposition and this project's established
remediation pattern (fix, then a fresh independent re-review — never the
drafting session's or the finding session's own say-so): P1-1 through
P1-3 require re-authoring by the chartered surface agents
(`veyro-infra-sre-engineer` for P1-1/P1-3, `veyro-backend-engineer` for
P1-2), each producing corrected content the owner can apply the same way
`BUG-034`'s original patch was applied (`.claude/rules/**` remains
owner-gated — this is not new; the write-access problem `BUG-034` solved
was specifically about *creating* the files the first time, not a
standing exemption for future edits). A fresh independent qualification
review must then re-run before `review_status` may read `APPROVED`.

**Not remediated this session** — deliberately, per the mission's own
scope: "determine the next dependency-safe MOD-001 implementation
slice" (step 8) is a distinct instruction from "remediate every finding
this same turn," and re-authoring 3 files plus a third review round is
substantial work this session chose not to fold into an already-large
turn without being asked. This is recorded as a real, open, honestly
scoped follow-up, not silently deferred.

## Round 2 (2026-09-19) — owner applied a remediation patch; fresh independent re-review returned BLOCKED again, P0=0/P1=1

The owner applied a remediation patch (commit
`f74f4fba7720dfb60e1cfe5947e477611392d84e`) touching
`infra/release.md`, `infra/iac.md`, `backend/architecture.md`,
`backend/api.md`. A second, independent, fresh-context
`veyro-security-reviewer` (Opus, no memory of round 1 or of drafting the
patch) reviewed the current on-disk content of all 9 files from scratch.

**Verdict: P0=0, P1=1 — BLOCKED.** P1-1 (unauthorized manual rollback
override) and P1-2 (missing backend transaction/idempotency/
reconciliation coverage) are **genuinely closed** — independently
verified against the cited `EIP_MIRROR.md`/`TSD_MIRROR.md`/
`IMPLEMENTATION.md`/`REQUIREMENTS.md` sources, not just re-worded. P1-3
(third-party CI-Action supply chain) is **partially closed**: the
SHA-pinning requirement is correctly specified, but the same control
(`iac.md` control 5) introduces a **new** unauthorized trust carve-out —
self-granting trusted-publisher status to `actions/*`/`github/*` with no
`OWN-<NNN>` entry authorizing it, contradicting
`CAPABILITY_POLICY.md`'s "no exemption of any kind" clause for
third-party capabilities. Filed as **P1-A**. Full record:
`knowledge/03-Modules/MOD-001/evidence/model-routing/RULE_QUALIFICATION_REVIEW_ROUND2_2026-09-19.md`.

**Status: still OPEN.** `RULE-001` through `RULE-009` remain `BLOCKED`
(not `APPROVED`) in `CAPABILITY_REGISTRY.md` and
`module-capabilities.yaml`. Per this session's governing mission's
explicit "if and only if P0=0 and P1=0" gate, no registry row was
marked `APPROVED`, this bug was not closed, and no rule file was
re-authored this session (`.claude/rules/**` remains owner-gated
regardless). Closing P1-A requires either removing `iac.md` control 5's
trusted-publisher clause (every `uses:` reference needs both a SHA pin
and an `APPROVED CAP-<NNN>` row), or an ADR plus an `OWN-<NNN>` entry
explicitly authorizing specific trusted publishers, reconciled against
`CAPABILITY_POLICY.md`'s no-exemption clause — followed by a third
independent qualification review.

## Round 3 (2026-09-22) — owner closed P1-A; fresh independent re-review found P1-A genuinely closed but a new P1 (P1-Q, no stage-5 qualification evidence)

The owner applied a further remediation (commit
`d3ce17ad42978761a0294909509e772444d5352d`) touching only `infra/iac.md`
control 5, removing the round-2 `actions/*`/`github/*` trusted-publisher
carve-out entirely — every GitHub Action now requires the full
`CAPABILITY_POLICY.md` 9-stage lifecycle with no publisher exemption. A
third, independent, fresh-context `veyro-security-reviewer` (Opus, no
memory of rounds 1 or 2) reviewed all 9 files from scratch.

**Verdict: P0=0, P1=1 — BLOCKED.** P1-A is **genuinely closed** —
independently re-verified against `CAPABILITY_POLICY.md`'s verbatim "no
exemption of any kind" clause and `OWNER_APPROVALS.md` (no relevant
`OWN-<NNN>` entry exists). Round 2's other two closures (rollback
override, backend transaction/idempotency/reconciliation coverage) were
re-confirmed unregressed. **A new P1 was found: P1-Q** — none of the 9
rule files has the stage-5 positive/negative qualification-test evidence
`CAPABILITY_POLICY.md` requires before a Rule may become `ACTIVE`/
`APPROVED` (`knowledge/05-QA/capability-evidence/` has no `RULE-*`
subdirectory; the registry's `evidence` column cites only the three
content-qualification review documents, which are stage-4 evaluation,
not stage-5 test evidence). Independently confirmed by this orchestrating
session by direct directory listing and by re-reading
`CAPABILITY_POLICY.md` stages 5/6 verbatim, not taken on the subagent's
word. Full record:
`knowledge/03-Modules/MOD-001/evidence/model-routing/RULE_QUALIFICATION_REVIEW_ROUND3_2026-09-22.md`.

**Status: still OPEN.** `RULE-001` through `RULE-009` remain `BLOCKED`
(not `APPROVED`). Per this session's governing mission's explicit "if
and only if P0=0 and P1=0" gate, no registry row was marked `APPROVED`,
this bug was not closed, and no rule file was re-authored this session.
Closing P1-Q requires producing, for each of the 9 files: `paths:`
frontmatter, a recorded positive test and a recorded negative
(non-matching-path) test under
`knowledge/05-QA/capability-evidence/RULE-<NNN>/`, and an Opus
evaluation of that evidence — followed by a fourth independent
qualification review.

## Stage-5 evidence production (same day, 2026-09-22) — content-level evidence produced; path-scope test genuinely FAILS, confirmed as a real owner-gated blocker

Per round 3's explicit next-legally-allowed-action, a fresh
`veyro-test-author` (Sonnet) dispatch produced Stage-5 qualification
evidence for all 9 rule files under
`knowledge/05-QA/capability-evidence/RULE-<NNN>/POSITIVE_NEGATIVE_EVAL_2026-09-22.md`,
per `CAPABILITY_POLICY.md` stage 5 and EIP Appendix H.5
(`EIP_MIRROR.md` lines 20809-20825: "Every new Skill/Rule must have at
least one success-path eval and one failure/negative eval" plus,
Rule-specific, "A Rule change must be tested against representative
matching and non-matching paths so path scoping is correct").

**Content-level positive/negative evaluation: produced and sound.** For
each rule, a synthetic compliant fixture and a deliberately-violating
fixture were built and evaluated by literal textual reading against the
rule's own quoted control clause (no `backend/`/`infra/` code exists yet
to run a real CI gate against). An independent, fresh-context
`veyro-security-reviewer` (Opus) evaluated this evidence — not a round-4
content-qualification verdict on the 9 rule files themselves, which
stays deferred, but an assessment of whether the evidence itself was
sound, honest, and non-fabricated. **Two real defects were found and
fixed same session:**
1. **RULE-002's negative fixture originally contained a literal
   credential-shaped string** (a Stripe-live-key-format value and a
   plausible real password) — which would itself have violated
   `secrets.md` control 1 (never a plausible-looking real-shaped value,
   even in fixtures) had it been committed, and risked tripping this
   repo's own planned secret-scanning gate. Fixed by describing the
   violation's shape in prose instead of writing a matching literal.
2. **All 9 files' header/status line originally claimed `QUALIFIED`**,
   which `CAPABILITY_POLICY.md` defines as "tests ran and passed" — not
   earned, since the path-scope half of Stage 5 (below) is a FAIL, not a
   pass. Corrected to `PARTIAL` on all 9.

Additionally, RULE-001's evidence carried 3 accuracy errors the Opus
review caught (a misquote of `iac.md`'s fail-closed text, a miscount of
`OWNER_APPROVALS.md`'s rows — 4, not 5 — and a misattribution of an
observation to round 3 that round 3 never made) — all fixed same
session. The remaining 8 files' content-level evaluations were confirmed
sound with no defect.

**Path-scope qualification case: genuinely FAILS, confirmed real and
reproducible, not fabricated.** Independently verified by this
orchestrating session, the `veyro-test-author` run, and the `veyro-
security-reviewer` run, separately: none of the 9 rule files has
`paths:` YAML frontmatter (each opens with an HTML comment then a bare
`# Rule:` heading) — contrast `.claude/rules/global/knowledge-vault-durability.md`,
which does carry real `scope: path` / `paths: [...]` frontmatter. This
is directly, reproducibly observable: in at least three separate
sessions now (this evidence-production session, the independent Opus
review session, and the orchestrating session itself, across this and
the round-3 turn), all 9 rule files were present in context at the
start of `knowledge/`-only work, while the path-scoped
`knowledge-vault-durability.md` only appeared after a `knowledge/` file
was actually read. This means all 9 rule files load unconditionally
regardless of the working path — the exact "pollute unrelated contexts"
failure EIP H.5 exists to catch.

**This is a genuine, confirmed, owner-gated blocker, not something this
or any session can close on its own.** Adding `paths:` frontmatter means
editing the 9 files under `.claude/rules/**`, which `.claude/settings.json`
denies Edit/Write on to every session (the same protection class as
`BUG-029`/`BUG-030`/`BUG-034`). Per this task's own explicit instruction,
no such edit was attempted this session.

**Status: still OPEN, more precisely characterized than before.**
`RULE-001` through `RULE-009` remain `BLOCKED`, not `APPROVED`, not
`QUALIFIED`. What changed: P1-Q's original framing ("no stage-5 evidence
exists") is no longer accurate — content-level evidence now exists and
is sound. The blocking condition is now specifically and confirmedly:
**EIP H.5's path-scope test fails for all 9 files, and closing it
requires an owner-approved `paths:`-frontmatter patch to `.claude/rules/**`**
(mirroring how `BUG-034`/round-2/round-3's remediations were each
applied by the owner directly), followed by a fourth independent
qualification review. Full record: the 9
`knowledge/05-QA/capability-evidence/RULE-<NNN>/POSITIVE_NEGATIVE_EVAL_2026-09-22.md`
files.

## Registration (P1-4, closed as part of this filing)

RULE-001 through RULE-009 are registered in
`knowledge/00-System/CAPABILITY_REGISTRY.md` with `review_status: BLOCKED`
(not `APPROVED`) — `qualified_by` names the drafting agents (Sonnet),
`approved_by` is empty (qualification did not pass), `content_hash` uses
the 9 SHA-256 values the reviewer independently computed, `evidence`
points to `RULE_QUALIFICATION_REVIEW_2026-09-19.md`. This follows
`CAP-007`'s own precedent of registering a capability before it clears
qualification (`QUALIFIED`/`BLOCKED` states are real, trackable registry
states, not "not yet a row").

## What this bug does NOT block

Backend/**/infra/**/CI implementation is not attempted relying on these
rules while this bug is open. Other MOD-001 implementation work
(`tools/**`, `contracts/**`) is unaffected — the same boundary `BUG-034`
enforced for slice 1 continues to apply here, for a different underlying
reason (content quality rather than write access).

## Non-goals

This bug does not authorize weakening the qualification bar to make it
pass more easily (e.g. accepting the P1-1 manual-override carve-out
without an ADR, or treating the missing idempotency/transaction coverage
as out of scope without a recorded reason) — the fix is re-authoring the
content to actually meet the bar, not lowering the bar.

## Round 4 (2026-09-25) — owner's `paths:` frontmatter patch applied; fresh independent review finds the patch itself introduces 2 new P1 scope gaps plus 1 P1 stale-evidence gap; still BLOCKED

**Fresh-context, review-only session, no memory of rounds 1-3.** Bootstrap
re-verified before any action: `verify_baselines.py` PASS 4/4; local HEAD
== `origin/main` == the governed commit named in this round's mission,
`5ad7d3cbb67f0433031850b0e3180f7a4872cccc` ("fix: add path scope metadata
to MOD-001 rule family"); `git show 5ad7d3c` independently read and
confirmed to touch exactly the 9 rule files, inserting only a `scope:
path` / `paths:` YAML frontmatter block at line 1 of each (no body-text
change) — the owner-applied patch this bug's round-3 section named as
the next legally allowed action.

**Fresh `veyro-security-reviewer` (Opus, no memory of rounds 1-3)
dispatched** with the exact round-4 mission (verify frontmatter validity;
verify path bindings against the recorded Stage-5 evidence; verify
positive/negative fixture paths genuinely match/don't match; verify
Stage-5 evidence sufficiency; verify no regression of prior P1 closures;
verify no new P0/P1 from this specific patch).

**Verdict returned: P0=0, P1=3, P2=2, Editorial=2 — BLOCKED.** This
orchestrating session independently re-verified the load-bearing claims
rather than taking the subagent's report on trust:

1. **Frontmatter validity — PASS**, confirmed by direct read of all 9
   files: each opens with a well-formed `scope: path` / `paths: [...]`
   block, same shape as the pre-existing
   `.claude/rules/global/knowledge-vault-durability.md` example.
2. **SHA-256 hashes independently recomputed by this session** via
   `shasum -a 256` against all 9 files — exact match to the reviewer's
   9 reported values (see the registry update below).
3. **`actions/*`/`github/*` no-carve-out text in `iac.md` line 96
   independently re-confirmed present** ("Every action, regardless of
   publisher — including `actions/*`") — round 2's P1-A closure has not
   regressed.

**P1-1 — `infra/release.md`'s new path scope (`infra/**`,
`.github/workflows/**`) excludes the surface where its own qualified
negative fixture lives.** RULE-004's own Stage-5 evidence
(`knowledge/05-QA/capability-evidence/RULE-004/POSITIVE_NEGATIVE_EVAL_2026-09-22.md`
§3) qualifies control 1 (no manually-callable rollback trigger) against a
negative fixture at `app/main.py` — a backend HTTP route
(`knowledge/03-Modules/MOD-001/IMPLEMENTATION.md` line 426 independently
confirms `backend/app/main.py` as this project's canonical backend-surface
example path). No backend-scoped rule file (`RULE-005`..`009`) covers
rollback triggers — independently grepped, only `database.md` mentions
"rollback" and only in a migration context. Before this patch, `release.md`
loaded unconditionally on every path, so it accidentally covered this
backend-surface violation too; the patch that fixes EIP H.5's path-scope
test for `release.md` genuinely narrows its real protection away from the
exact violation its own qualification evidence names.

**P1-2 — `infra/secrets.md`'s new path scope (`infra/**`,
`.github/workflows/**`) is narrower than control 1's own repo-wide text**
("No secret is ever committed to the repository, in any form... whether
in source, config, fixtures, test data, or documentation" —
`secrets.md` line ~33, independently re-read). No other rule file covers
committed credentials outside `infra/**` — independently grepped for
"secret" across `.claude/rules/**`, only `secrets.md`/`iac.md`/`performance.md`
mention it, and `performance.md`'s reference is log-statement-scoped, not
credential-scoped. A hardcoded credential in `backend/**` config, a test
fixture, or a repo-root dotfile would load no rule under the new scope.
Separately and non-dispositively: RULE-002's own recorded positive/negative
fixtures target `infra/environments/qa/.env.example`, a dotfile segment;
this session could not confirm whether the harness's glob-matching
treats a leading-dot path segment as covered by `**` by default (many
glob implementations exclude dotfiles from `*`/`**` without an explicit
`dot: true` option) — an open, unresolved question this bug does not
close, flagged for whoever next verifies `.claude/rules/*.md` path-scope
enforcement mechanically (the same open item `CURRENT_STATE.md` already
carries: rule auto-loading is `BLOCKED/UNVERIFIED`).

**P1-3 — the 9 Stage-5 evidence files are now stale against the governed
commit.** All 9 `POSITIVE_NEGATIVE_EVAL_2026-09-22.md` files still bind to
commit `5aa5cc5b6b6d041372b83e043febf179d0460fa5` (pre-frontmatter-patch)
and still record §2's path-scope case as a directly-observed FAIL. Per
`CAPABILITY_POLICY.md` (a scope change routes back through stages 4-5),
this evidence needs a fresh run bound to `5ad7d3c`, now that a `paths:`
mechanism actually exists to exercise a real matching-vs-non-matching
test against (rather than recording `NOT EXECUTABLE`/`FAIL`-by-absence).
This is not this review's job to produce — `CAPABILITY_POLICY.md`'s own
role separation keeps the Opus reviewer from re-running the tests it is
evaluating.

**Prior P1 closures re-verified unregressed (round-4-specific spot
checks, this orchestrating session):** `iac.md`'s no-publisher-carve-out
text (line 96) confirmed present; `CAPABILITY_REGISTRY.md`/
`module-capabilities.yaml` row-to-file mapping confirmed unchanged and
correct.

**Disposition: per the mission's explicit "if and only if P0=0 and
P1=0" gate, the condition was not met.** `RULE-001` through `RULE-009`
were **not** marked `APPROVED`. `BUG-035` was **not** closed. No rule
file was re-authored (also structurally impossible this session —
`.claude/rules/**` remains owner-gated). No implementation slice was
started. MOD-002 was not started. MOD-001 was not marked approved.

**Next legally allowed action:** an owner decision on the two scope
questions P1-1/P1-2 raise (broaden `release.md`'s and `secrets.md`'s
`paths:` to include the backend surface / go `scope: global`, or accept
the narrower scope with a recorded reason), followed by a fresh
`veyro-test-author` re-run of all 9 Stage-5 evidence files bound to the
current commit (P1-3), followed by a fifth independent qualification
review before `RULE-001`..`009` may read `APPROVED` and `BUG-035` may
close. Not Code Review, not Manual QA, not Gatekeeper certification, not
MOD-002, not a further implementation slice.

Full record: `knowledge/03-Modules/MOD-001/evidence/model-routing/RULE_QUALIFICATION_REVIEW_ROUND4_2026-09-25.md`.

## Round 4 follow-up (2026-09-25, same day) — owner patch prepared for P1-1/P1-2

Per round 4's own "next legally allowed action," this follow-up turn
re-read `release.md`'s and `secrets.md`'s exact current bodies and
determined the minimal path-scope correction each one's own
already-approved control text requires — no rule body changed, no new
content authored, no Stage-5 re-run, no round 5 review. **`release.md`
needs `backend/**/*.py` added** (control 1's own named exposure
mechanisms — HTTP endpoint/CLI flag/webhook/manual override — plus its
own already-qualified Stage-5 negative fixture at `backend/app/main.py`
both require it; the positive fixture already sits inside the existing
`infra/**` scope, so this is additive only). **`secrets.md` needs
`scope: path`/`paths:` replaced with `scope: global`** (control 1's own
text — "in any form... source, config, fixtures, test data, or
documentation" — and control 3's own references to the repo-root
`.gitignore` and to non-infra evidence/fixture files are both
unconditionally repo-wide, matching the exact `scope: global`
convention `.claude/rules/global/owner-reserved-restrictions.md`
already uses). The exact patch content is prepared, not applied
(`.claude/rules/**` remains owner-gated), at
`knowledge/03-Modules/MOD-001/evidence/bugs/BUG-035-release-secrets-scope-patch/PATCH_PLAN.md`.
`RULE-001` through `RULE-009` remain `BLOCKED`; `BUG-035` remains
`OPEN`. No registry/status file was updated this turn — this is
patch-preparation only, not a new independent review round.

## Post-round-4 remediation (2026-09-25, same day) — owner applies the scope-correction patch, Stage-5 evidence re-run

The owner applied the prepared patch: commit `183acd535e6786f1edc1993a5ef6f13afd13a4ec`
added `backend/**/*.py` to `release.md`'s `paths:` and replaced
`secrets.md`'s `scope: path`/`paths:` with `scope: global`; a further
commit, `14d13376680cdeba9011f9b1d2d3e9ab1d7c2a7a`, corrected both
files' own H1 headings (which had briefly still read "(`infra/**`
binding)" after the scope change) to match. `veyro-test-author`
(Sonnet) re-ran Stage-5 evidence for all 9 rule files bound to
`14d1337`. An independent, fresh-context `veyro-security-reviewer`
(Opus) found `RULE-002`/`RULE-004`'s evidence still bound to the
now-superseded `183acd5` (the owner's `14d1337` commit landed
mid-session) — fixed directly by the orchestrating session, re-verified
against primary sources. All 9 Stage-5 evidence files were sound and
current as of `14d1337`. `RULE-001` through `RULE-009` remained
`BLOCKED`; `BUG-035` remained `OPEN` — an independent Round 5
qualification review was the next required step. Full detail:
`knowledge/00-System/CAPABILITY_REGISTRY.md`'s Qualification History
section, `knowledge/03-Modules/MOD-001/evidence/model-routing/RULE_QUALIFICATION_REVIEW_ROUND4_2026-09-25.md`'s
follow-up context.

## Round 5 (2026-09-25, same day) — independent qualification review: APPROVED, P0=0/P1=0 — CLOSED

A fresh-context `veyro-security-reviewer` (Opus, no memory of rounds
1-4, no participation in producing any Stage-5 evidence or prior
remediation) reviewed all 9 rule files and their Stage-5 evidence
against the full 8-point check list this project's Round 5 mission
specified.

**The reviewer's own bootstrap re-derivation caught a further HEAD
move the dispatch brief had not accounted for:** the true current
governed HEAD was `8e90680e8e8bcbd86e5136b6181371ac8161eee7` (this
repo's own prior session's evidence/registry commit, which added the
Stage-5 evidence and registry updates themselves and touched nothing
under `.claude/rules/**`), not `14d1337` as the dispatch brief stated —
independently re-derived via `git rev-parse`, not taken on trust.

**Findings:**
- `RULE-002`'s `scope: global` confirmed both correctly scoped (control
  1's repo-wide no-secret-commit invariant admits no narrower correct
  path list) and non-polluting under EIP H.5 (controls 2-3 are inert
  outside their own applicable contexts, same shape as this project's
  other global rules). `N/A (scope: global)` confirmed a valid Stage-5
  disposition.
- `RULE-004`'s added `backend/**/*.py` glob confirmed to reach its own
  qualified rollback-trigger fixture (`backend/app/main.py`) with no
  scope overshoot.
- All 7 prior-round P1 closures (manual-rollback-override carve-out;
  backend transaction/outbox/reconciliation/idempotency coverage;
  CI-Action supply-chain no-publisher-carve-out; rule registration;
  Stage-5 evidence existence; path metadata; stale evidence binding)
  re-confirmed genuinely closed, unregressed.
- The 2 carried-forward observations (whether `scope: global` fully
  satisfies H.5's non-pollution half; whether the rule-loader might
  match a non-root-anchored nested glob) were investigated and neither
  promoted to P1, for lack of a present, material, implementation-
  blocking defect to cite.
- **P2-1 (new):** 7 of the 9 Stage-5 evidence files (`RULE-001`,
  `003`, `005`, `006`, `007`, `008`, `009`) still named the superseded
  `183acd5` as "current governed HEAD" — stale the moment `8e90680`
  (which added those very files) was committed. Not P1: all 9 rule
  files are byte-for-byte identical across `183acd5`/`14d1337`/
  `8e90680`, independently re-confirmed by SHA-256. **Fixed by this
  orchestrating session** in the same 7 files, immediately after the
  review.
- P2-2 (`observability.md`'s `tools/**` validator-scope gap) and P2-3
  (`concurrency.md`'s raw-`.sql`-file gap), both carried from round 4,
  re-confirmed still present, still non-gating, left open as disclosed
  residuals.
- Editorial-1 (new): `iac.md`/`observability.md`'s H1 headings omit
  `.github/workflows/**` from their own label despite covering it —
  left open, non-blocking.

**Verdict: P0=0, P1=0 — APPROVED.**

**Disposition:** per the governing mission's "if and only if P0=0 and
P1=0" gate, the condition is **met**. `RULE-001` through `RULE-009` are
marked `APPROVED` and `ACTIVE` in `CAPABILITY_REGISTRY.md` and
`module-capabilities.yaml`. **`BUG-035` is CLOSED.** No rule file was
re-authored by any session (the four owner-applied patch commits were
the owner's own action throughout this bug's history). No
implementation slice was started as part of this closure. MOD-002 was
not started. MOD-001 was not marked approved — this closure clears one
named pre-implementation condition (`ADR-005` Decision 2) for
`backend/**`/`infra/**`/CI implementation specifically, it is not a
module certification.

Full record: `knowledge/03-Modules/MOD-001/evidence/model-routing/RULE_QUALIFICATION_REVIEW_ROUND5_2026-09-25.md`.
