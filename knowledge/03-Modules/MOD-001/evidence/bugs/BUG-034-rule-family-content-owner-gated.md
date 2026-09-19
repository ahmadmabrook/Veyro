---
doc: BUG-034
status: CLOSED
module: MOD-001
severity: P1 (blocked touching `backend/**`, `infra/**`, or CI per ADR-005 Decision 2's binding pre-implementation condition; did not block non-backend/infra/CI implementation work, which is why MOD-001 implementation slice 1 could still start the same session this bug was filed)
opened: 2026-09-19
closed: 2026-09-19
---

# BUG-034 — No guard-compliant path to author `.claude/rules/backend/**`/`infra/**` content (ADR-005 pre-implementation condition)

## Finding

`ADR-005` (`knowledge/04-Decisions/ADR-005-mod001-critical-slice-and-surface-profile-routing.md`,
Decision 2, "Timing" section) states a binding pre-implementation
condition: **"Before implementation work begins at `infra/**`, CI, or
`backend/**`: the two profiles' agents and rule families must exist with
real content."** The two profile agents (`veyro-infra-sre-engineer.md`,
`veyro-backend-engineer.md`) already exist (closed via `BUG-029`/`BUG-030`).
The rule-family content does not — `knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml`'s
own `required_rule_ids: []` field says so directly: "backend/ and infra/
rule families need real content before implementation per ADR-005, not
yet authored."

This session (MOD-001 implementation start) confirmed directly, not
assumed:

- `.claude/rules/` is currently flat — 4 loose files
  (`notion-mcp-scope-discipline.md`, `owner-reserved-restrictions.md`,
  `knowledge-vault-durability.md`, `admin-privileged-console-baseline.md`),
  no family subdirectories exist yet. `IMPLEMENTATION.md` §1 already
  plans the disposition (3 → `global/`, 1 → `admin/`) and 9 new real
  content files across the two activated families (`backend/`: 5 files;
  `infra/`: 4 files) — see `migration-plan.md` in this bug's own
  `BUG-034-patch/` evidence directory.
- `.claude/settings.json`'s `permissions.deny` list contains
  `Edit(.claude/rules/**)` and `Write(.claude/rules/**)` (confirmed by
  direct read, lines 135-136) — the identical protection class `BUG-029`/
  `BUG-030` found for `.claude/agents/**`.
- `.claude/security/bash_guard.py`'s `PROTECTED_PATH_FRAGMENTS` includes
  the literal string `.claude` (confirmed by direct read, line 132),
  which its `_is_protected_path` substring+normalized-prefix check
  applies to every Class-B mutation family's path argument — so even a
  Bash-level `git mv`/`mkdir` targeting `.claude/rules/**` is denied,
  not just the Edit/Write tools.

This is the same capability-gap species as `BUG-028` (no guard-compliant
docx read path) and `BUG-029`/`BUG-030` (no guard-compliant
`.claude/agents/**` write path), applied to `.claude/rules/**`. It is a
correct, intentional protection — rule files are exactly the kind of
security/governance-relevant, tamper-sensitive content this project's
`.claude/` protection scheme exists to guard, and no session should be
able to silently create or alter its own governing rule set.

## Decision

Per the `BUG-028`/`BUG-029`/`BUG-030` precedent, this is routed to the
owner rather than worked around. The exact patch content is prepared in
full below (not bypassed, not partially applied):

- **4 `git mv` commands** relocating the existing loose files into
  `global/`/`admin/` family directories.
- **9 new rule files**, each meeting Appendix H.3's content standard,
  each with full source citations back to the owner-produced EIP/TSD
  mirrors and MOD-001's own planning documents — drafted by the exact
  chartered agents ADR-005 names for this content
  (`veyro-infra-sre-engineer` for the 4 `infra/` files,
  `veyro-backend-engineer` for the 5 `backend/` files), independently
  reviewed by this orchestrating session before inclusion here.

All patch content lives at
`knowledge/03-Modules/MOD-001/evidence/bugs/BUG-034-patch/` in this same
directory, one file per target (filenames spell out their eventual
`.claude/rules/` destination in a leading HTML comment; see
`migration-plan.md` there for the exact mapping and `git mv` commands),
and was also sent directly to the owner as a combined file via
`SendUserFile` for easy one-shot review/copy.

**Files (10 total, all under `BUG-034-patch/`):**

1. `migration-plan.md` — the 4 `git mv` commands + full disposition
   rationale + the "other 9 families stay empty" note.
2. `rules-infra-iac.md` → `.claude/rules/infra/iac.md`
3. `rules-infra-secrets.md` → `.claude/rules/infra/secrets.md`
4. `rules-infra-observability.md` → `.claude/rules/infra/observability.md`
5. `rules-infra-release.md` → `.claude/rules/infra/release.md`
6. `rules-backend-architecture.md` → `.claude/rules/backend/architecture.md`
7. `rules-backend-api.md` → `.claude/rules/backend/api.md`
8. `rules-backend-database.md` → `.claude/rules/backend/database.md`
9. `rules-backend-concurrency.md` → `.claude/rules/backend/concurrency.md`
10. `rules-backend-performance.md` → `.claude/rules/backend/performance.md`

## What the owner needs to do

1. Run the 4 `git mv` commands in `migration-plan.md`.
2. Copy files 2-10 above to their target paths (strip the leading
   `<!-- Target path... -->` comment line from each when copying, or
   leave it — it is a valid HTML comment and does no harm either way,
   but the established project convention in `admin-privileged-console-baseline.md`
   does not carry one, so stripping it keeps the style consistent).
3. Commit both the moves and the new files together, per
   `migration-plan.md`'s own sequencing note (one commit, not split).
4. This session (or the next one) then independently verifies —
   byte-for-byte read-back match against this bug's own patch content,
   commit integrity, local HEAD == origin/main — before closing this
   bug, exactly as `BUG-029`/`BUG-030` were closed.

## Non-goals

This bug does not authorize, and no session should attempt, editing
`.claude/settings.json` or `.claude/security/bash_guard.py` to remove or
narrow the `.claude/rules/**` deny rule — that protection is correct and
should stay in force. The fix is an owner action outside the guard, not
a guard change.

## What this bug does NOT block

Per its own severity note: MOD-001 implementation work outside
`backend/**`/`infra/**`/CI (e.g. `tools/**`, `contracts/**` — both
known-infrastructure paths per `module-capabilities.yaml`) is unaffected
and proceeded this same session — see
`knowledge/03-Modules/MOD-001/evidence/implementation/SLICE-1-baseline-binding-validator-2026-09-19.md`.

## Closure (2026-09-19)

**CLOSED.** The owner applied the patch outside this guarded session
(commit `3632764e44522376277d96441bee847d148843fa`). This session
independently verified, not merely trusted:

- `git log -1 --stat` on the owner's commit confirms all 4 `git mv`
  moves as pure renames (0 insertions/0 deletions each) — the migration
  introduced no unreviewed content changes to the 4 existing files.
- All 9 new files read back from their applied `.claude/rules/{backend,infra}/`
  locations and compared against this session's own
  `knowledge/03-Modules/MOD-001/evidence/bugs/BUG-034-patch/` drafts —
  byte-identical. Independently re-confirmed a second way by a
  fresh-context `veyro-security-reviewer` (Opus) dispatch, which
  SHA-256-hashed both copies of all 9 files and found every pair
  byte-identical.
- Rule-family directory structure matches the migration plan exactly:
  `global/` (3 files), `admin/` (1 file), `backend/` (5 files),
  `infra/` (4 files); the other 7 Appendix H.2 families correctly remain
  absent.
- Local HEAD == `origin/main` == `3632764e44522376277d96441bee847d148843fa`
  confirmed at the start of this verification.

**This closes BUG-034's own narrow, originally-filed scope: the
capability gap (no guard-compliant write path to `.claude/rules/backend/**`/
`infra/**`) is genuinely resolved.** A separate, newly-discovered defect
class — the applied content itself has P1-severity qualification
findings (transaction/idempotency coverage missing from the backend
family, an unauthorized security-relaxing carve-out in one infra file, no
third-party CI-Action supply-chain control) — is **not** folded into this
bug's closure. It is filed separately as `BUG-035`
(`knowledge/03-Modules/MOD-001/evidence/bugs/BUG-035-rule-content-qualification-blocked.md`),
following this project's own established pattern of not conflating a
newly-found, distinct defect with an already-closed bug's scope (the
`BUG-030`→`BUG-031`→`BUG-032` precedent). Full qualification-review
record: `knowledge/03-Modules/MOD-001/evidence/model-routing/RULE_QUALIFICATION_REVIEW_2026-09-19.md`.
