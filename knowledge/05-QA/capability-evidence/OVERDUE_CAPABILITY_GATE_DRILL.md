---
doc: OVERDUE_CAPABILITY_GATE_DRILL
status: EXECUTED (2026-09-12) — SCN-MOD000-036
date: 2026-09-12
---

# SCN-MOD000-036 — Capability past next-review-due cannot satisfy a gate until re-evaluated

## What was missing when this scenario was authored

`CAPABILITY_REGISTRY.md` had no `next_review_due` column at all — the
scenario was blocked on a real, named tooling gap.

## What exists now

That gap has since been closed (independently of this scenario, as a
byproduct of later Phase 5/7/8 work): every one of the 7 registry rows
now carries a real `next_review_due` date, and
`knowledge/00-System/validate_capabilities.py` was extended with a
dedicated check (read directly this chunk, lines 176-183):

```python
# 5. next_review_due not in the past, unless exempted.
next_review_due = row.get("next_review_due", "")
if not exempt:
    m = re.match(r"(\d{4}-\d{2}-\d{2})", next_review_due)
    if not m:
        errors.append(f"{cid}: next_review_due '{next_review_due}' is not a parseable date and is not exempted.")
    elif m.group(1) < today:
        errors.append(f"{cid}: next_review_due {m.group(1)} is in the past (today: {today}) — cannot satisfy any gate until re-evaluated, per CAPABILITY_POLICY.md.")
```

Confirmed this is live logic in the validator's main per-capability loop
(not dead/unreachable code) — it runs unconditionally for every
manifest-referenced, non-exempt capability every time
`validate_capabilities.py` is invoked, which happens routinely
throughout this project (most recently as part of this same Phase 8
regression). ISO 8601 date strings (`YYYY-MM-DD`) compare correctly
under plain string `<` comparison, so `m.group(1) < today` is a correct
overdue check, not an approximation.

## Honest scope of this evidence

**No live failing trigger exists to demonstrate the error path firing**
— all 7 real capabilities currently have `next_review_due` dates in the
future (earliest: 2026-12-04), by design (each was dated 90 days from
its own approval). The validator's CLI does not accept a path override
to point it at a scratch/synthetic registry copy instead of the real
one, so a live "watch it actually block" demonstration against a
synthetic overdue row was not performed this chunk — doing so would
require either waiting for a real date to lapse or modifying the
validator's own interface, neither appropriate for this drill.

**What is proven, by direct code inspection rather than a live failing
run:** the mechanism this scenario's own precondition names as missing
now exists, is correctly wired into the main validation path, and
implements the exact fail-closed logic (`BLOCKED`-class error, not a
silent pass) the scenario's pass criteria require. This is
inspection-based verification of a real, reachable code path — not an
assertion that the gap doesn't exist, and not a claim of a live
demonstrated failure.

## Status: PASS (mechanism verified real and correct by direct code inspection; no live overdue case existed among the real capabilities to trigger it)
