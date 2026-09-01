---
doc: BUG-002
status: CLOSED — Git repository initialized and verified
found: 2026-09-01
closed: 2026-09-01
severity: Blocker
found_by: veyro-scenario-reviewer (fresh context, Opus) during MOD-000 Scenario Catalog independent review
---

# BUG-002: No Git repository exists despite the durable-authority model assuming one

**What's wrong:** `PROJECT_INDEX.md`, `CLAUDE.md`, `.claude/rules/knowledge-vault-durability.md`, and `DEVELOPMENT_CONSTITUTION.md` all state "Git + `knowledge/` are the durable authority" / "Git history wins on divergence." No `.git/` directory exists anywhere under `/Users/ahmadmabrouk/Desktop/Veyro`. Confirmed directly: `git status` returns "fatal: not a git repository." The session environment has also reported "Is a git repository: false" since the very first MOD-000 chunk.

**Impact:** every claim of "Git-first," "version-controlled," or "recoverable via Git history" made across 5 chunks of MOD-000 work has been describing a control that does not exist. There is currently no way to: detect an unintended edit to a durable file, revert a bad change, or recover the vault if the working directory is lost. This is the same class of risk that produced BUG-001 (a stray file went undetected until a fresh session happened to re-derive a hash) — except broader, since it applies to every file in `knowledge/` and `.claude/`, not just one manifest.

**Why it wasn't caught earlier:** every prior chunk's baseline/config verification checked file *contents* (hashes, JSON syntax, hook firing) but never checked whether the containing directory was actually under version control. The fresh-session re-verification in chunk 5 re-hashed files but did not check for `.git/`.

## Resolution (2026-09-01)

Owner authorized resolution directly, including deletion of `Veyro-Mobile/` (BUG-003) which removed the scope ambiguity that previously blocked `git init`. Executed:

1. `git init` at the Veyro project root — no prior repository existed.
2. `.gitignore` authored before any `git add`, covering secrets/credentials, IDE/editor state, build artifacts, simulator/device artifacts, generated temp files, and the one local Claude Code override file (`.claude/settings.local.json`) — while explicitly never ignoring the 4 governing baselines, `knowledge/`, or `.claude/agents|rules|settings.json`.
3. All 4 baseline hashes re-verified immediately before staging — exact match to `PROJECT_INDEX.md`, confirming zero baseline alteration from the git-init process itself.
4. Working tree validated (103 files staged, grepped for secret/cache patterns, none found) before the first commit.
5. Initial governed commit created: **`3e6d88fa03ad4569c6e34be57efa72b612fff77f`**.
6. Clone-and-verify: cloned to a scratch path, re-hashed all 4 baselines in the clone — exact match, confirming genuine recoverability.

No remote added, no push performed, no GitHub/GitLab/Azure repository created — per explicit instruction.

Full evidence: `knowledge/01-Modules/MOD-000/evidence/durability/GIT_RECOVERY_PROOF.md`.

**Cross-reference:** `knowledge/01-Modules/MOD-000/scenario-catalog/SCENARIO_CATALOG.md` SCN-MOD000-016, SCN-MOD000-053 (both now PASS, evidence-backed).
