# Target: `.claude/rules/` Appendix H.2 family-directory migration plan

Not a rule-content file — this is the exact command list to relocate
the 4 currently-loose `.claude/rules/*.md` files into their correct
Appendix H.2 family directories, per
`knowledge/03-Modules/MOD-001/IMPLEMENTATION.md` §1's own already-decided
disposition (the ADR-005-grounded "3 project-wide → `global/`, 1
surface-scoped → `admin/`" split). This plan does not re-litigate that
disposition — it only states the exact moves, to be executed by the
owner (this session cannot write to `.claude/` — see BUG-034).

## Current state (verified this session)

`.claude/rules/` is confirmed flat — 4 files directly under
`.claude/rules/*.md`, no family subdirectories exist yet:

- `.claude/rules/notion-mcp-scope-discipline.md`
- `.claude/rules/owner-reserved-restrictions.md`
- `.claude/rules/knowledge-vault-durability.md`
- `.claude/rules/admin-privileged-console-baseline.md`

## Exact `git mv` commands

Run from the repository root (`/Users/ahmadmabrouk/Desktop/Veyro`). `git
mv` creates the destination directory automatically — no separate
`mkdir` step is required.

```bash
git mv .claude/rules/notion-mcp-scope-discipline.md .claude/rules/global/notion-mcp-scope-discipline.md
git mv .claude/rules/owner-reserved-restrictions.md .claude/rules/global/owner-reserved-restrictions.md
git mv .claude/rules/knowledge-vault-durability.md .claude/rules/global/knowledge-vault-durability.md
git mv .claude/rules/admin-privileged-console-baseline.md .claude/rules/admin/admin-privileged-console-baseline.md
```

**Disposition, per `IMPLEMENTATION.md` §1 (already decided, restated
here only to bind the commands above, not to re-derive it):**

- `notion-mcp-scope-discipline.md`, `owner-reserved-restrictions.md`,
  `knowledge-vault-durability.md` are project-wide governance, not
  scoped to any one §4.3 surface, and move into the new `global/` family
  directory.
- `admin-privileged-console-baseline.md` is surface-scoped by its own
  text ("governs any future internal admin/support-console surface...
  binds forward to MOD-029") and by Appendix H.2's own family table,
  which places its subject under
  `admin/{components,forms-tables,permissions,privileged-console,rtl-a11y}.md`
  — it moves into the `admin/` family directory instead, distinct from
  the other 3.

## New content this migration should land alongside

Not part of the `git mv` list above (these are new files, not relocated
ones) — the 9 drafted rule files in this same patch directory belong at:

- `.claude/rules/infra/iac.md` ← `rules-infra-iac.md`
- `.claude/rules/infra/secrets.md` ← `rules-infra-secrets.md`
- `.claude/rules/infra/observability.md` ← `rules-infra-observability.md`
- `.claude/rules/infra/release.md` ← `rules-infra-release.md`
- `.claude/rules/backend/architecture.md` ← `rules-backend-architecture.md`
- `.claude/rules/backend/api.md` ← `rules-backend-api.md`
- `.claude/rules/backend/database.md` ← `rules-backend-database.md`
- `.claude/rules/backend/concurrency.md` ← `rules-backend-concurrency.md`
- `.claude/rules/backend/performance.md` ← `rules-backend-performance.md`

These should be added (`git add`) in the same commit as the 4 `git mv`
moves above, since all changes implement the same `IMPLEMENTATION.md`
§1 / `ADR-005` Decision 2 disposition together — splitting them across
multiple commits would leave an intermediate state where the
family-directory convention exists but the two families with real
required content (Infra/SRE/CI, Backend) are still empty, which is
exactly the pre-implementation condition ADR-005 requires closed before
`infra/**`, CI, or `backend/**` implementation work begins.

## The other 9 Appendix H.2 family directories

Per `IMPLEMENTATION.md` §1's own count, 11 Appendix H.2 families exist
in total for this project's rule tree. 2 of the 11 are `global/` and
`admin/`, both covered by the `git mv` moves above. 2 more (`backend/`,
`infra/`) get real content from this same patch. The remaining 7 are
the still-DEFERRED §4.3 surface families: `web`, `frontdesk-pos`,
`mobile`, `ios`, `android`, `edge`, `data-ai`.

**These 7 stay genuinely empty.** Git does not track empty directories,
so these 7 will simply **not exist as real directories** on disk until
the module that first activates each profile adds real rule content to
it. This is correct and expected, not an oversight to fix now — it is
the same precedent this project already established for
`.claude/skills/` (BUG-004: no Skill directory exists because no real
need has been found yet). A future session should not create empty
placeholder directories for these 7 families "for completeness" — that
would be exactly the "profile theater" `ADR-005` Decision 2 Part 1
rejects, applied to rule directories instead of code.

## Sequencing note

This migration (4 `git mv` + 9 new files across 2 families) should land
as one commit. It does not depend on anything else being done first —
the family-directory convention and the Infra/SRE/Backend rule content
are independent of the rest of MOD-001 implementation, and this is
explicitly the gating precondition for touching `infra/**`, CI, or
`backend/**` at all (`ADR-005` Decision 2: "Before implementation work
begins at infra/**, CI, or backend/**: the two profiles' agents and
rule families must exist with real content").

After applying, the owner (or a fresh session, once unblocked) should:
1. Confirm `.claude/rules/` now has `global/`, `admin/`, `backend/`,
   `infra/` subdirectories with the expected file counts (3, 1, 5, 4).
2. Update `knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml`'s
   `required_rule_ids: []` field to list the 9 new `RULE-<NNN>` IDs (IDs
   not yet assigned — this project has not needed RULE-ID assignment
   before now; assigning them is durable-state work for whichever
   session applies this patch, not part of the patch content itself).
3. Close `BUG-034` in `knowledge/05-QA/BUG_REGISTRY.md`, following the
   exact independent-verification pattern `BUG-029`/`BUG-030` used
   (byte-for-byte read-back match, commit integrity, local HEAD ==
   origin/main).
