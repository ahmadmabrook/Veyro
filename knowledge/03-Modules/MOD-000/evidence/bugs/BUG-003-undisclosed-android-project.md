---
doc: BUG-003
status: CLOSED — deleted per owner authorization
found: 2026-09-01
closed: 2026-09-01
severity: Major
found_by: veyro-scenario-reviewer (fresh context, Opus) during MOD-000 Scenario Catalog independent review
---

# BUG-003: Undisclosed Android project (`Veyro-Mobile/`) at repository root, disposition unknown

**What's wrong:** a complete, separate Android Studio project exists at `/Users/ahmadmabrouk/Desktop/Veyro/Veyro-Mobile/` — Gradle build files (`build.gradle.kts`, `settings.gradle.kts`, `gradlew`), `AndroidManifest.xml`, `app/` source tree, package name `com.example.veyro_couch`, plus IDE/build state (`.idea/`, `.gradle/`). All files are timestamped 2026-09-01 01:33 — concurrent with this fresh top-level session's start.

**Investigation performed:** reviewed every file this MOD-000 session chain (5 chunks across this and prior sessions) has created. None of it is Android/Kotlin/Gradle content — everything created by MOD-000 work lives under `knowledge/`, `.claude/`, and evidence subdirectories. No chunk's instructions or output reference creating an Android project. **Conclusion: this project's own MOD-000 work did not create `Veyro-Mobile/`.**

**Most likely explanation (unconfirmed):** the owner created it independently — e.g. via Android Studio's "New Project" wizard — around the same time this fresh session started, unrelated to Claude Code / MOD-000 work. The generic package name (`com.example.<name>`) is consistent with an IDE-generated template rather than deliberate Veyro product code.

**Why this matters for MOD-000:** SCN-MOD000-051 (MOD-001/product-implementation lock enforcement) originally asserted the repository contains "self-evidently" only control-plane/governance/baseline files. That assertion was false and has been corrected in the Scenario Catalog. Until this is dispositioned, MOD-000 cannot claim a clean, fully-audited repository root.

**What is NOT being done:** this file does not modify, move, or delete anything inside `Veyro-Mobile/` — it is not MOD-000's to alter without knowing whose it is and why it exists.

## Resolution (2026-09-01)

Owner confirmed directly: `Veyro-Mobile/` was an experimental/disposable project the owner created independently. It is **not** a governing baseline, **not** part of approved Veyro implementation scope, and **not** authoritative. Owner explicitly authorized inspection, relocation, or deletion — deletion selected as the cleanest option to prevent further contamination/confusion of the governed project area.

**Action taken:**
1. Captured a complete file manifest before deletion (52 files) — `knowledge/03-Modules/MOD-000/evidence/bugs/BUG-003-veyro-mobile-manifest-at-deletion.txt`.
2. Confirmed zero overlap with `knowledge/`, `.claude/`, or any MOD-000 evidence path (grep of the manifest against those path prefixes returned nothing) — deletion could not destroy any control-plane record.
3. Deleted the entire `Veyro-Mobile/` tree (files via `find -exec rm`, then empty dirs via `find -depth -type d -exec rmdir`, deliberately avoiding a blanket `rm -rf` per this project's own deny-pattern discipline).
4. Verified removal: `test -d Veyro-Mobile` confirms absent; `ls` of the project root now shows only `CLAUDE.md`, the 3 governing docx baselines, `knowledge/`, and `veyro-product-experience-design/`.

**Explicitly not treated as Veyro product implementation evidence** — its contents (an Android Studio template, package `com.example.veyro_couch`) were never product code for this project and are now gone; nothing from it is referenced anywhere in MOD-000 evidence.

**Cross-reference:** `knowledge/03-Modules/MOD-000/scenario-catalog/SCENARIO_CATALOG.md` SCN-MOD000-051 (repository-purity scenario — now genuinely satisfiable, since the one non-control-plane, non-baseline path is gone).

**Addendum (found during BUG-002 git-init work, same session):** two more IDE-session artifacts from the same experimental Android Studio activity were found directly at the project root — `.gradle/` and `.idea/` (both timestamped 01:30-01:31, same window as `Veyro-Mobile/`'s creation), left outside the `Veyro-Mobile/` folder itself. Not deleted (owner's authorization named `Veyro-Mobile/` specifically) but confirmed excluded from the new `.gitignore` so they cannot contaminate the Git-durable record regardless. Flagged here for completeness and owner awareness; harmless as configured.
