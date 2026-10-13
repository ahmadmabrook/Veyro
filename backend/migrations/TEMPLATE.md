# Migration record template (GOV-01-R06, TSD §24.2)

Copy this file into `records/` as `NNNN_<change_id>_<phase>.yaml` (a
4-digit numeric prefix, sorted globally across all changes — the ordering
lint in `tools/validate_migration_ordering.py` reads records in filename
order) for every phase of every schema change. `phase` must be one of
`expand`, `migrate`, `switch`, `contract`, applied in that order per
`change_id`, per TSD §24.2: "Expand -> migrate/backfill -> switch
reads/writes -> contract. Destructive contract happens only after all
deployed versions stop using old shape."

```yaml
---
change_id: short_snake_case_name_shared_by_all_4_phase_files
phase: expand
owner: name@example.com
lock_impact: e.g. "CREATE INDEX CONCURRENTLY — no write lock" or "ACCESS EXCLUSIVE, ~200ms, run in low-traffic window"
rollback_strategy: exact command/procedure to undo this specific phase
validation_query: a query proving this phase's change is correct/complete
---

Free-text description of what this phase does and why. Not parsed by the
lint — for human reviewers.
```

All 6 fields above are required by `validate_migration_ordering.py`
(`change_id`, `phase`, plus TSD §24.2's 4 named record fields: `owner`,
`lock_impact`, `rollback_strategy`, `validation_query`) — a record
missing any of them, or using a `phase` value outside the 4 listed above,
fails closed (`MISSING_REQUIRED_FIELD`/`INVALID_PHASE`), naming the exact
file and field/value.

The filename must end in `.yaml` and the file must sit **directly** in
`records/` — not `.yml`, not `.md` (this template's own extension), and
not inside a subdirectory such as `records/2026q4/`. Any other file in
that tree fails closed as `UNRECOGNIZED_RECORD_FILE` naming its relative
path, rather than being silently skipped (hardened 2026-10-04 after the
SCN-MOD001-070 round-1 independent review proved all three spellings
previously let a genuinely out-of-order destructive record set pass with
exit 0). Only `.gitkeep` and `.DS_Store` are exempt.

Two authoring rules added 2026-10-04 after the round-2 independent review
found each one passing a destructive out-of-order record with exit 0:
declare every field **exactly once** — a repeated key (e.g. two `phase:`
lines) fails closed as `DUPLICATE_FRONT_MATTER_KEY` rather than silently
taking the last one, because the phase a reader sees must be the phase
enforced; and put no **symlink** inside `records/` — symlinks are not
followed, so anything beneath or behind one would go unchecked, and each is
reported as `SYMLINK_IN_RECORDS_TREE`. (A symlink *to* the whole records
directory, passed as `--records-dir`, is fine and still works.) A
`--records-dir` that exists but is not a directory fails closed as
`RECORDS_PATH_NOT_A_DIRECTORY`, with or without `--require-dir`.

Two further operational notes on the lint, same hardening pass:
`--require-dir` makes a missing/typo'd `--records-dir` fail closed
(`MISSING_RECORDS_DIR`) instead of passing vacuously — any future CI
wiring should pass it. And a pass that checked **zero** records now prints
a grep-able `NOTICE: ... vacuous pass` line, so an empty `records/` is
never mistaken for a pass over real records.

Large backfills (the `migrate` phase) must be online/resumable jobs with
progress and throttling, per TSD §24.2 — never a single deployment
transaction. Record that throttling approach in `lock_impact` for the
`migrate`-phase file.

No real product schema exists yet (MOD-001's own GOV-01-R06 scope is the
policy/tooling, not any actual migration), so `records/` is currently
empty aside from `.gitkeep` — the first real schema-owning module fills
it in.
