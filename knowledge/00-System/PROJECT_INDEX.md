---
doc: PROJECT_INDEX
status: LIVE
last_verified: 2026-08-31
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

| # | Artifact | Path | SHA-256 | Bytes | Verified |
|---|----------|------|---------|-------|----------|
| 1 | Master Product Blueprint | `Gym_OS_Master_Product_Blueprint_v1_English.docx` | `80f4b381df26919b358b3e64e209c67beba2ba9224c0f4df3951d3b179d426ef` | 198614 | 2026-08-31 |
| 2 | Technical System Design v1.4.1 | `Veyro_Technical_System_Design_v1.4.1_English_FINAL.docx` | `0d41c8a1231e5c8680c96a44b3ccc02c4f42cf8984c84d04bf9b60378cc158e8` | 1113596 | 2026-08-31 |
| 3 | Design bundle (170-screen UX baseline) | `veyro-product-experience-design/` | manifest hash below | 54 files, 2.9M | 2026-08-31 |
| 4 | Engineering Implementation Plan v1.4.1 | `Veyro_Engineering_Implementation_Plan_v1.4.1_English_FINAL_APPROVED_GOVERNING_BASELINE.docx` | `e5b5ec3b08859e27da3689dc3b54d17ea766cba5bf4c4e0007239baa920866b6` | 277994 | 2026-08-31 |

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

- **MOD-000** — Engineering execution control plane bootstrap (in progress). See [`knowledge/01-Modules/MOD-000/`](../01-Modules/MOD-000/).
- MOD-001 and all product implementation: **locked** until MOD-000 passes all mandatory gates.

## Durable Authority Rule

Git + this Obsidian-compatible `knowledge/` vault are the durable authority. Notion is a live operational mirror. On divergence, reconcile Notion to Git/knowledge state — never the reverse.
