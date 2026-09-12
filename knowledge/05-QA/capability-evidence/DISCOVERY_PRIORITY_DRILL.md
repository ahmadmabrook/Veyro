---
doc: DISCOVERY_PRIORITY_DRILL
status: EXECUTED (2026-09-12) — SCN-MOD000-092
date: 2026-09-12
---

# SCN-MOD000-092 — Capability discovery follows EIP source-priority order

## Synthetic gap

For this drill: "MOD-000 needs a way to validate that a YAML file
(`module-capabilities.yaml`) is syntactically well-formed before other
tooling reads it." A plausible, real-shaped gap of the kind MOD-000
actually has faced (this exact need arose organically for
`validate_capabilities.py`).

## Discovery walked in EIP §4.2's exact declared order

1. **Built-in/approved Claude capability** — checked first. The Claude
   Code harness's own Bash/Python execution (CAP-004, first-party
   exemption) can run Python's standard-library `yaml`/`json` parsing
   directly. **Resolved at stage 1** — a built-in capability
   (Python's own standard library, invoked through the already-approved
   CAP-004 Bash/Python execution capability) is sufficient. Stages 2-5
   were not needed and were not skipped-to prematurely.

2. **Veyro project Skill/Rule already reviewed** — not reached, since
   stage 1 resolved the gap. (For contrast: if the gap had instead been
   "enforce a Veyro-specific YAML schema shape," stage 2 would apply —
   check `.claude/rules/` and any registered project Skill first, before
   reaching for a third-party or custom-built solution.)

3. **Organization-approved/official marketplace capability** — not
   reached.

4. **Independently reviewed third-party capability** — not reached.

5. **Custom Veyro capability created in-repo** — not reached, though
   this is in fact exactly how `verify_baselines.py`,
   `validate_capabilities.py`, `validate_catalog.py`,
   `evidence_integrity_check.py`, `resolution_bound.py`, and
   `mr_verify.py` were all actually built — each only after the built-in/
   Skill/marketplace/third-party stages were checked and found
   insufficient for that tool's specific, narrow purpose (a real,
   already-executed instance of this exact priority order, not merely a
   synthetic one).

## Provenance recorded

This drill's outcome (stage 1, built-in capability, CAP-004) is
recorded here. The real precedent it mirrors — every one of the 6
custom tools named above — has its own provenance recorded in
`CAPABILITY_REGISTRY.md` and/or its own evidence file, each noting why a
lower-priority (stage 5, custom-build) resolution was reached only after
the higher-priority stages didn't fit.

## Result vs. pass criteria

Pass criteria: priority order respected, provenance recorded, no
lower-priority source used while a higher-priority one would have
sufficed. **Confirmed** — the synthetic gap resolved at stage 1 without
skipping ahead, and this project's own real capability-build history
(6 custom tools) independently corroborates the order was followed for
real, not just in this synthetic walkthrough.

## Status: PASS
