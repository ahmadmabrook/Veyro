---
doc: BUG-002
status: OPEN
found: 2026-09-01
severity: Blocker
found_by: veyro-scenario-reviewer (fresh context, Opus) during MOD-000 Scenario Catalog independent review
---

# BUG-002: No Git repository exists despite the durable-authority model assuming one

**What's wrong:** `PROJECT_INDEX.md`, `CLAUDE.md`, `.claude/rules/knowledge-vault-durability.md`, and `DEVELOPMENT_CONSTITUTION.md` all state "Git + `knowledge/` are the durable authority" / "Git history wins on divergence." No `.git/` directory exists anywhere under `/Users/ahmadmabrouk/Desktop/Veyro`. Confirmed directly: `git status` returns "fatal: not a git repository." The session environment has also reported "Is a git repository: false" since the very first MOD-000 chunk.

**Impact:** every claim of "Git-first," "version-controlled," or "recoverable via Git history" made across 5 chunks of MOD-000 work has been describing a control that does not exist. There is currently no way to: detect an unintended edit to a durable file, revert a bad change, or recover the vault if the working directory is lost. This is the same class of risk that produced BUG-001 (a stray file went undetected until a fresh session happened to re-derive a hash) — except broader, since it applies to every file in `knowledge/` and `.claude/`, not just one manifest.

**Why it wasn't caught earlier:** every prior chunk's baseline/config verification checked file *contents* (hashes, JSON syntax, hook firing) but never checked whether the containing directory was actually under version control. The fresh-session re-verification in chunk 5 re-hashed files but did not check for `.git/`.

**Fix (not applied in this chunk — flagged for owner/next chunk, not unilaterally decided):** initializing a Git repository here is a structural decision with real scope questions (should `Veyro-Mobile/` — see BUG-003 — be included or excluded; how should the 3 large docx baselines be stored, e.g. plain vs. Git LFS; what belongs in `.gitignore`). Recommend raising to the owner rather than deciding unilaterally mid-catalog-authoring-chunk. Once resolved: `git init`, commit the full `knowledge/`/`.claude/` tree and the 4 baseline artifacts (or reference them appropriately), verify a clone reproduces the vault byte-identically (see new `SCN-MOD000-053`).

**Cross-reference:** `knowledge/01-Modules/MOD-000/scenario-catalog/SCENARIO_CATALOG.md` SCN-MOD000-016, SCN-MOD000-053.
