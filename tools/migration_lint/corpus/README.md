# ADR-0002 D5 mutation corpus

Lint fixture data. **Not S1 migrations**, not a schema proposal and not a naming decision: the
MOD-004 table and column names are undecided (`knowledge/03-Modules/MOD-004/MOD-004.md` records
that "names and columns are decided by ADR review"), and nothing here is applied to any database.
These files exist so `migration_lint.py corpus` can prove each rule in `RULES` actually fires, and
that none of them fires on a legitimate migration.

Layout:

- `baseline/tenant/`, `baseline/platform/` — must lint clean. This is what stops an
  always-failing lint from passing its own corpus. It has earned its keep twice: it caught a
  policy-predicate check that read masked text, where the `'app.tenant_id'` literal the predicate
  must name had been blanked out, and a dynamic-SQL rule that fired on
  `REVOKE EXECUTE ON FUNCTIONS`.
- `baseline/tests/` — stands in for the runtime-role negative-test tree
  (`backend/tests/integration/tenancy/**`, which does not exist yet). The `NEGATIVE_TESTS` rule
  looks here for a file naming both a new tenant table and a runtime role. That is a mention
  check, not proof a test exists or fails closed; see the module docstring's stated limits.
- `mutations/<EXPECTED>/<track>/*.sql` — deliberately failing migrations. `<EXPECTED>` is the rule
  names the files must produce, joined by `+`; the first is the rule the mutation targets. **Each
  file is judged on its own**, so several files in one directory are several spellings of the same
  violation and every one has to be caught. That is deliberate: an earlier version OR-ed the
  findings across a directory, so one canonical spelling qualified a rule, and an independent
  review then demonstrated sixteen working evasions of rules that had passed qualification exactly
  that way. A second review found thirteen more against the remediation, including three complete
  tenant-isolation bypasses — `OR 1=1` in a policy predicate, `WITH GRANT OPTION` hiding the
  grantee from four grant rules at once, and an unprotected table in a third schema. Where a rule
  had such a hole, its directory now carries the alternative spellings.
- `nearmiss/tenant/`, `nearmiss/platform/` — legitimate migrations that must lint clean. Without
  these the corpus only ever proves that rules fire, never that they stay quiet on valid SQL, so
  every false positive is unguarded. Every case here was a real false positive at some point:
  `UNIQUE (tenant_id, …)` as the tenant-leading index, a separate `CREATE INDEX`, `ADD PRIMARY KEY`
  written beside another clause, `GRANT REFERENCES (tenant_id) … TO veyro_cp_migrator`, a
  `REVOKE`-only default-privilege entry, the approved `SET LOCAL` / `set_config(…, true)` forms, a
  view over a set-returning function, a single-quoted function body with no DDL in it, a tenant
  table in a schema other than `plt01`, a tenant predicate narrowed by further conjuncts — and
  **ADR-0002 D3's prescribed predicate itself**,
  `tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid`. That last one is why the
  tree exists. An earlier policy check rejected it, because the `true` in it is `current_setting`'s
  *missing_ok* argument rather than a permissive constant, and the whole corpus had quietly adopted
  a different predicate to get past the lint — so the fixtures encoded a deviation from the ADR and
  nothing noticed. The fixtures now use D3's form.

What this corpus does **not** establish: the ADR-0002 D5 live catalog assertions, which need a
running PostgreSQL. `BLK-CAP-POSTGRES17-PSYCOPG-POOL-RUNTIME` is OPEN, so
`BLK-SKL-MIGRATION-LINT` is **not** closed by this corpus passing, and no SKL evidence ID follows
from it. `SCN-MOD-004-101..104` are not PASSed: no real migration exists to lint. A corpus PASS
says the rules behave as written on the spellings collected here — it does not say the collection
is complete, and the module docstring's limits list is the floor of what is missing, not the
ceiling.
