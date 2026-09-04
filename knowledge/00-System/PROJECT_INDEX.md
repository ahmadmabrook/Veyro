---
doc: PROJECT_INDEX
status: LIVE
last_verified: 2026-09-01
---

# Veyro — Project Index (Durable Baseline Bindings)

This file is the durable, Git-backed source of truth for which artifacts govern this project and what they hash to. Notion mirrors this; on divergence, this file (and Git history) wins.

## Governing Baseline Precedence (confirmed by owner 2026-08-31)

1. **Master Product Blueprint** — `Gym_OS_Master_Product_Blueprint_v1_English.docx`
2. **Technical System Design v1.4.1** — `Veyro_Technical_System_Design_v1.4.1_English_FINAL.docx`
3. **Approved Claude Design / 170-screen UX baseline** — `veyro-product-experience-design/` (bundle, frozen)
4. **Engineering Implementation Plan v1.4.1** — `Veyro_Engineering_Implementation_Plan_v1.4.1_English_FINAL_APPROVED_GOVERNING_BASELINE.docx`

Lower-numbered documents override higher-numbered ones on conflict. None of these four artifacts may be modified, renamed, regenerated, normalized, or overwritten by any agent or automation. They are read-only inputs.

## Baseline Identities and SHA-256 Hashes

| # | Artifact | Governing identity (per EIP §21.1 / §17-ish PROJECT_INDEX binding requirement) | Path | SHA-256 | Bytes | Verified |
|---|----------|---|------|---------|-------|----------|
| 1 | Master Product Blueprint | **VEYRO-MPB-1.0** | `Gym_OS_Master_Product_Blueprint_v1_English.docx` | `80f4b381df26919b358b3e64e209c67beba2ba9224c0f4df3951d3b179d426ef` | 198614 | 2026-08-31 |
| 2 | Technical System Design | **Veyro TSD v1.4.1** (EIP names this version identity; no separate coded document ID is given in the EIP text beyond the version string itself) | `Veyro_Technical_System_Design_v1.4.1_English_FINAL.docx` | `0d41c8a1231e5c8680c96a44b3ccc02c4f42cf8984c84d04bf9b60378cc158e8` | 1113596 | 2026-08-31 |
| 3 | Design bundle (170-screen UX baseline) | **VEYRO-UX-V1-170-APPROVED** | `veyro-product-experience-design/` | manifest hash below | 54 files, 2.9M | 2026-08-31 |
| 4 | Engineering Implementation Plan | **VEYRO-EIP-1.4.1-20260827** (currently promoted governing EIP — see contradiction note below) | `Veyro_Engineering_Implementation_Plan_v1.4.1_English_FINAL_APPROVED_GOVERNING_BASELINE.docx` | `e5b5ec3b08859e27da3689dc3b54d17ea766cba5bf4c4e0007239baa920866b6` | 277994 | 2026-08-31 |

**Identity binding added 2026-09-01** per EIP §21.1's explicit requirement ("PROJECT_INDEX/SESSION_BOOTSTRAP must bind VEYRO-MPB-1.0, TSD v1.4.1, VEYRO-UX-V1-170-APPROVED and the promoted governing EIP identity to cryptographic hashes") and its Notion-registry analogue (EIP line ~8559: "MUST record the exact governing artifact identity and cryptographic content hash... for VEYRO-MPB-1.0, Veyro TSD v1.4.1, VEYRO-UX-V1-170-APPROVED, and the currently promoted governing EIP... The governing EIP entry MUST identify VEYRO-EIP-1.4.1-20260827 and bind the exact content hash of this promoted artifact; any missing, ambiguous or mismatched identity/hash stops implementation until reconciled."). This closes the gap independent review round 3 found (D-6/N-2): identities were previously bound by filename+hash only, not by their EIP-coded identity strings. See `knowledge/00-System/external-gates-evidence/EIP_STATUS_CONTRADICTION.md` for the separate, real internal EIP contradiction about VEYRO-EIP-1.4.1-20260827's approval status (front matter says approved/final; §21.1 body still calls it "this candidate").

### Design bundle manifest (artifact #3)

Deterministic manifest method: `find . -type f ! -name '.DS_Store' | sort`, each file SHA-256'd, concatenated as `<hash>  <relpath>\n`, then the manifest file itself SHA-256'd.

- **Manifest hash (bundle identity):** `c96f77abdf4345b231a60b37f832d76ac82cf52fb8b00ae3066f20bb10a36dbb`
- **Per-file manifest:** [`DESIGN_BUNDLE_MANIFEST.txt`](DESIGN_BUNDLE_MANIFEST.txt) (54 entries, frozen alongside this index)
- **Cross-check:** `project/uploads/Gym_OS_Master_Product_Blueprint_v1_English.docx` inside the bundle hashes identically to baseline #1 root copy (`80f4b381...`) — confirms the bundle carries a consistent, non-diverged copy of the Blueprint.
- **Primary entry point per bundle README:** `project/Veyro Product Experience.dc.html`
- **Bundle nature:** Claude Design handoff bundle — HTML/CSS/JS prototypes (`.dc.html` artboards), a markdown mirror of the Blueprint (`project/blueprint.md`), a screen registry (`Veyro Screen Registry.dc.html`, `veyro-registry-data.js`, `veyro-screen.js`), design-system docs, audit/completion-report artboards, and one upload. No ambiguity, no duplicate candidates found at project root.

## Precedence Ambiguity — Resolved

The task instructions contained two orderings for artifact #3 vs #4 (numbered list vs. precedence-order section). Owner confirmed on 2026-08-31: **precedence-order section is authoritative** — design bundle ranks above EIP. Recorded here so no future session re-litigates this.

## Active Module

- **MOD-000** — Engineering execution control plane bootstrap (in progress). See [`knowledge/03-Modules/MOD-000/`](../01-Modules/MOD-000/).
- MOD-001 and all product implementation: **locked** until MOD-000 passes all mandatory gates.

## Durable Authority Rule

Git + this Obsidian-compatible `knowledge/` vault are the durable authority. Notion is a live operational mirror. On divergence, reconcile Notion to Git/knowledge state — never the reverse.

**Git repository status (2026-09-01):** initialized this date (resolves BUG-002 — no repository existed prior to this). Initial governed commit: `3e6d88fa03ad4569c6e34be57efa72b612fff77f`. Baseline hashes re-verified as unchanged immediately before this commit; clone-and-verify drill confirmed the vault is genuinely recoverable from Git alone. Full evidence: `knowledge/03-Modules/MOD-000/evidence/durability/GIT_RECOVERY_PROOF.md`. This durable-authority claim is now evidence-backed, not aspirational.

**GitHub remote (governed backup/collaboration mirror, 2026-09-01):** private repository `ahmadmabrook/Veyro` (`https://github.com/ahmadmabrook/Veyro.git`), branch `main` tracking `origin/main`. Pushed commit `3e6d88fa03ad4569c6e34be57efa72b612fff77f` verified identical across local HEAD, `git ls-remote`, `origin/main`, and a fresh independent clone (including a baseline-hash re-check inside that clone). No Actions/deployments/secrets/packages/releases configured. GitHub is a mirror, same governance tier as Notion — Git + `knowledge/` (local) remain the engineering authority. Full evidence: `knowledge/03-Modules/MOD-000/evidence/durability/GITHUB_REMOTE_PROOF.md`.
