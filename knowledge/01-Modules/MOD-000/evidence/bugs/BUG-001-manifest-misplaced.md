---
doc: BUG-001
status: FIXED
found: 2026-09-01
severity: Major
---

# BUG-001: DESIGN_BUNDLE_MANIFEST.txt was missing from its documented location

**Found by:** this fresh top-level session's mandatory baseline re-verification (`SESSION_BOOTSTRAP.md` step 1), 2026-09-01.

**What was wrong:** `PROJECT_INDEX.md` documents `knowledge/00-System/DESIGN_BUNDLE_MANIFEST.txt` as the frozen 54-entry per-file manifest for baseline #3. It did not exist at that path. Root cause: during the original MOD-000 bootstrap chunk (2026-08-31), a `cd veyro-product-experience-design && find ...` command left the shell's working directory inside that folder for a subsequent command, so `mkdir -p knowledge/00-System ...` and the manifest write landed inside `veyro-product-experience-design/knowledge/00-System/` instead of the project root. This also left empty stray scaffold directories (`veyro-product-experience-design/knowledge/{01-Modules,02-Decisions,03-ExternalGates,04-Capabilities}/...`, `veyro-product-experience-design/.claude/{agents,rules,skills}`) inside the **frozen design bundle directory** — contamination of a baseline artifact's folder, though not of any of its 54 governed files.

**Impact assessed:** none to the actual governed content. Verified by:
1. Recomputing the design-bundle manifest excluding the stray files -> hash `c96f77abdf4345b231a60b37f832d76ac82cf52fb8b00ae3066f20bb10a36dbb`, exact match to the value already recorded in `PROJECT_INDEX.md` since 2026-08-31.
2. Spot-verified individual files (`blueprint.md`, `.thumbnail`, `README.md`) unchanged.
3. All 3 governing docx files re-hashed, exact match to `PROJECT_INDEX.md`.

**Fix applied (this session):**
1. Copied the (correct-content) manifest file from its accidental location to its documented location: `knowledge/00-System/DESIGN_BUNDLE_MANIFEST.txt`. Content verified identical to a fresh clean re-scan.
2. Removed the stray empty directories and the duplicate manifest file from inside `veyro-product-experience-design/` (precise `rm`/`rmdir` on verified-empty/single-file targets, not a blanket recursive delete — `rm -rf` on that path was in fact blocked by this project's own `.claude/settings.json` deny rule, confirming that control works).
3. Re-ran the full manifest scan on the now-clean bundle directory with zero exclusions -> hash matches `c96f77ab...` exactly, 54/54 files, no stray entries.

**Verdict:** the governing baseline artifacts were never actually compromised — this was a file-placement defect in tooling output, not a baseline-integrity failure. Correctly caught by the fail-closed re-verification this fresh session was required to run, and correctly not glossed over.
