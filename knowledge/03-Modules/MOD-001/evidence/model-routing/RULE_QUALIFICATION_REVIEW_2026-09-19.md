---
doc: MOD-001_RULE_QUALIFICATION_REVIEW
status: LIVE
module: MOD-001
updated: 2026-09-19
---

# Independent qualification review of the 9 new `backend/`/`infra/` Rule files

## Context

Per `knowledge/00-System/CAPABILITY_POLICY.md` ("Governs every Skill,
**Rule**, Plugin, MCP server, hook, or script") and its "Model-routing
interaction" section (binding): a capability's `review_status` may not
read `APPROVED` without an Opus assurance role independently evaluating
the evidence in a fresh context — "No capability may become `APPROVED`
solely from a Sonnet implementation run." The 9 rule files were drafted
by Sonnet-tier `veyro-infra-sre-engineer`/`veyro-backend-engineer`
dispatches and reviewed only by the same (Sonnet) orchestrating session
before being handed to the owner — that is `qualified_by`, not
`approved_by`. This is the required independent step.

## What was verified before dispatching the review

1. **BUG-034 patch applied correctly, byte-for-byte.** All 4 `git mv`
   moves confirmed as pure renames (`git log -1 --stat` on commit
   `3632764e44522376277d96441bee847d148843fa` shows 0 insertions/0
   deletions on all 4). All 9 new files read from their applied
   `.claude/rules/{backend,infra}/` locations and compared against this
   session's own `knowledge/03-Modules/MOD-001/evidence/bugs/BUG-034-patch/`
   drafts — content identical (the reviewer independently confirmed this
   a second way, via SHA-256 hashing both copies; see its verdict below).
2. **Rule-family structure matches the migration plan exactly.**
   `.claude/rules/` now has exactly 4 subdirectories: `global/` (3
   files), `admin/` (1 file), `backend/` (5 files), `infra/` (4 files).
   The other 7 Appendix H.2 families remain absent (correct — see
   `BUG-034-patch/migration-plan.md`'s own "stays empty" note).
3. **A front-matter deviation suspected, then disproven.** This session
   initially flagged that 2 of the 4 migrated files
   (`owner-reserved-restrictions.md`, `knowledge-vault-durability.md`)
   carry `scope:`/`paths:` YAML front matter the other 2 don't. The
   independent reviewer checked `git log -1 --stat` directly and found
   this front matter **pre-existed the migration** (0 insertions on the
   rename) — it was simply not visible via this session's earlier
   `CLAUDE.md`-embedded reads of those files. **No finding — retracted.**

## Independent review — `veyro-security-reviewer` (Opus, fresh context)

Dispatched to review all 9 files for: citation accuracy (spot-checking
cited `EIP_MIRROR.md`/`TSD_MIRROR.md` line ranges directly), H.3's
anti-vague-slogan requirement (every control must be falsifiable),
internal consistency against `IMPLEMENTATION.md`/`ADR-005`, and style
conformance against the project's established rule-file template.

**Positive test (citation accuracy): PASS on every citation checked.**
14 citations independently verified by reading the cited ranges
directly — all load-bearing ones (the H.3 Infra/SRE quote, the `DOM-002`
quote, the RLS/module-dependency/permission-lint quotes, the §24.2
4-field migration-record requirement, all 7 violation codes) confirmed
verbatim-exact or accurate.

**Supply-chain integrity check (reviewer's own initiative): PASS.** All
9 applied files SHA-256-hashed against this session's reviewed drafts —
byte-identical, all 9 pairs. No unreviewed content was introduced by the
owner's application.

**Both scope checks this session specifically asked about: PASS.**
`database.md`'s scope note correctly excludes the RLS harness's own
critical-slice logic (owned by `veyro-critical-engineer` per ADR-005
Decision 1). `performance.md` correctly refuses to invent an
application-scale load budget. No file invents a production environment.

### P1 findings (4) — qualification-blocking, per this project's own established bar (CAP-007 Round 3 precedent: BLOCKED at P1>0)

- **P1-1** — `infra/release.md` control 1 permits a manually-callable
  rollback override path that its own cited authority
  (`IMPLEMENTATION.md` §3's Canary row) explicitly forbids ("not a
  manually-callable endpoint"). No cited source authorizes the carve-out;
  it is a new security-relevant escape hatch introduced by rule text
  alone, which `EIP_MIRROR.md:20631-20639`'s "a Rule may not lower
  higher-precedence constraints" and DC-09 both require an ADR for.
- **P1-2** — the backend family (5 files) covers none of Appendix
  H.3's "transaction/idempotency/reconciliation" element, despite
  `architecture.md`/`api.md` both quoting the exact EIP §4.3 row that
  names it, behind an elided ellipsis. MOD-001 already owns
  `tools/validate_idempotency_contract.py` as a blocking CI gate with no
  corresponding authoring-time rule.
- **P1-3** — the infra family (4 files, governing `.github/workflows/**`)
  has no control binding third-party CI Action supply-chain trust (pin/
  provenance review), despite `secrets.md` protecting exactly the
  tier-scoped secrets such an action would have access to, and Appendix
  H.4's "Third-party/community/unknown → BLOCKED until independent
  approval" row applying directly to this surface.
- **P1-4** — stage-7 registration gap: all 9 files are unregistered in
  `CAPABILITY_REGISTRY.md` — orchestrator-side, no re-authoring needed
  (see "Disposition" below).

### P2 (8) and Editorial (7)

Full text preserved in this session's own transcript record (not
duplicated here in full to avoid the exact restatement-drift species
this project's own `SCENARIOS.md`/`CURRENT_HANDOFF.md` have repeatedly
flagged) — summary: citation-sourcing gaps in the 4 infra files (no
mirror line ranges — P2-2), a misattributed source citation
(`release.md` control 3 — P2-3), two unfalsifiable "structured logging"
phrasings with no named format/validator (`observability.md`/
`performance.md` — P2-4), an undefined "non-trivial row count" threshold
(`database.md` control 8 — P2-5), an invented "exactly one" constraint
in `api.md` control 6 that disagrees with `architecture.md`'s own wording
of the same rule (P2-6), no machine-readable path-scope front matter on
any of the 9 new files, unlike 2 of the 4 pre-existing rule files
(P2-7), and a spliced/misattributed quotation in `iac.md` control 2
(P2-8). Editorial: the patch-wrapper HTML comment retained at line 1 of
all 9 files; the 4 infra files missing a dated provenance line the 5
backend files carry; a mis-tagged "(verbatim)" paraphrase; a
tense-altered `IAM-002` quote; a path missing its `backend/` prefix; an
unenumerated "or an equivalent alias" in `iac.md` control 4 (fails
closed, not a pass-path defect); `release.md`'s header over-claiming
"cost tags/budgets" coverage its body doesn't fully deliver.

### Verdict

**P0=0, P1=4, P2=8, Editorial=7 — BLOCKED.**

Per this project's own established qualification bar (`CAPABILITY_POLICY.md`
stage 6; CAP-007's own Round 3 precedent, which returned BLOCKED at
P0=0/P1=3 and only APPROVED after a fourth round reached P0=0/P1=0), this
does not qualify as `APPROVED`. P1-1 through P1-3 require re-authoring by
the chartered surface agents (`veyro-infra-sre-engineer` for P1-1/P1-3,
`veyro-backend-engineer` for P1-2) followed by a fresh independent
qualification review — not by the orchestrating session, not by the
agents that drafted the original content. P1-4 does not require
re-authoring.

## Disposition

- **`BUG-034` (the capability gap — no guard-compliant path to author
  `.claude/rules/backend/**`/`infra/**` content) is CLOSED.** Its own
  stated closure criteria (byte-for-byte read-back match, commit
  integrity, local HEAD == origin/main) are all independently satisfied
  — verified twice, by this session and by the reviewer's own SHA-256
  check. The guard/write-access problem BUG-034 named is genuinely
  resolved.
- **A new, distinct finding — `BUG-035` — is filed for the P1 content
  defects** found by this independent review. This is not the same
  defect BUG-034 named (BUG-034 was "cannot write here at all";
  BUG-035 is "the content that was written has real gaps"), matching
  this project's own established pattern of filing related-but-distinct
  defects separately rather than folding a newly-discovered problem into
  an already-closed bug's scope (the exact `BUG-030`→`BUG-031`→`BUG-032`
  precedent).
- **RULE-001 through RULE-009 are registered in `CAPABILITY_REGISTRY.md`
  with `review_status: BLOCKED`**, not `APPROVED` — `qualified_by` names
  the drafting agents (Sonnet), `approved_by` is left empty (qualification
  did not pass), `content_hash` uses the 9 SHA-256 values the reviewer
  independently computed. This follows `CAP-007`'s own precedent of
  registering a capability before it clears qualification, so the
  registry reflects real state rather than omitting the row entirely
  until a later, cleaner moment.
- **Backend/**/infra/**/CI implementation does not proceed relying on
  these rules as qualified** until `BUG-035` closes. The next MOD-001
  implementation slice this session selects stays outside
  `backend/**`/`infra/**`/CI, the same boundary `BUG-034` enforced for
  slice 1.
