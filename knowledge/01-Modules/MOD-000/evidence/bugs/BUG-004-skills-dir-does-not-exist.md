---
doc: BUG-004
status: FIXED
found: 2026-09-01
severity: Minor
found_by: Phase 1 deterministic execution, SCN-MOD000-093
---

# BUG-004: `.claude/skills/` directory does not exist; `CURRENT_STATE.md` implied it did

**What's wrong:** `CURRENT_STATE.md` (chunk 3 onward) stated "`.claude/skills/` intentionally empty — no gap found yet requiring a project-scoped skill," which reads as "the directory exists and is empty." Actual on-disk state: `.claude/skills/` was never created (`ls .claude/` shows only `agents/`, `rules/`, `settings.json`, `settings.local.json`). Git doesn't track empty directories, so even if a `mkdir` had been run in an earlier chunk without a placeholder file, it would not have persisted through any commit.

**Impact:** cosmetic/documentation-accuracy only — no scenario or process actually depended on the directory existing, and the substantive claim ("no Skill has been needed yet") remains true. Found via SCN-MOD000-093's real execution (`ls .claude/skills` -> "No such file or directory"), not assumed.

**Fix:** corrected `CURRENT_STATE.md` wording to accurately describe the state as "no `.claude/skills/` directory exists yet — none has been needed" rather than implying an empty-but-present directory. Not creating an empty placeholder directory for its own sake (nothing to put in it yet; per `CAPABILITY_POLICY.md`, Skills are created only when a real, justified gap exists).
