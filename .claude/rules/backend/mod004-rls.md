# Tenant isolation rule (control-plane tables)

Every table in `plt01` obeys this, whichever module owns it. It began as MOD-004's rule and now
also governs MOD-005's `cfg_*` and MOD-015's `bil_*` tables in `plt01`, and MOD-007's tables in
the `iam` schema, whose policies name `veyro_iam_app` instead. A later module's tables are covered
the same way.

## Authority

`knowledge/00-Decisions/OWNER-2026-11-13-full-engineering-delegation.md` delegates ordinary
engineering decisions to the session, so nothing here gates implementation on a capability
manifest, a Module Ready finding, a Scenario Review or an owner approval. Those gates are removed,
not quietly ignored -- §3 of that record lists them.

What survives is the technical content below, because it is product requirement rather than
process: isolation that fails closed, least privilege, and negative tests that actually fail when
the protection is removed. `knowledge/00-Decisions/ADR-0002-mod004-control-plane-isolation.md`
remains the design source for the role names, the GUC name and the policy shape; change those
through an ADR so the lint, the migrations and the pool configuration keep agreeing.

## Rules
1. **Explicit tenant context.** Every request or worker command opens an explicit transaction and sets `app.tenant_id`, `app.actor_id`, `app.correlation_id` transaction-locally (`SET LOCAL`, or `set_config(name, value, true)`) through the single approved tenancy primitive (D4.1-D4.2). Refuse autocommit and non-UUID values.
2. **No session-level context.** Do not use `SET app.*`, `SET SESSION`, `ALTER ROLE/DATABASE ... SET app.*` or `set_config(..., false)`. PostgreSQL does not reject these; the ban rests on lint, the primitive and reuse tests. Pool reset is defence in depth only, and `pg_db_role_setting` must hold no `app.*` entry (D4.2, D5).
3. **Fail closed.** Every tenant table has `tenant_id UUID NOT NULL`, `ENABLE` and `FORCE ROW LEVEL SECURITY`, no PUBLIC grant, and a policy with `USING` and `WITH CHECK` on `tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid` (D2, D3). Missing or invalid context may error or return zero rows, never unrestricted rows. No `OR true`, role-membership bypass or unrestricted-returning function in a tenant policy.
4. **Non-owner runtime roles.** Runtime and worker roles (`veyro_cp_app`, `veyro_cp_worker`) are LOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOBYPASSRLS, own no tenant table, and are members of no role (no `SET ROLE` path). DDL runs as a separate non-runtime owner (D1, D6.5). Role names are ADR proposals; do not rename without an ADR change.
5. **Least privilege.** No TRUNCATE or REFERENCES grant to runtime roles; no PUBLIC privilege on schemas, tables, sequences or functions; views are `security_invoker = true` or banned; history and outbox are insert/select only (D2.4, D5, D6.2).
6. **platform_scope is function-only (D6).** Platform tables sit in `plt01_platform` with no RLS and no policy, no runtime-role grant and no USAGE for runtime roles. Runtime access is only through the closed D6.3 allowlist (`provision_tenant`, `resolve_placement`); adding a function, including any cross-tenant list or read, needs an ADR change and review ID. SECURITY DEFINER functions need an allowlist entry, pinned `search_path`, no dynamic SQL and no PUBLIC EXECUTE.
7. **No cross-tenant leakage.** Cache keys, search and read models, object-storage paths, events/jobs/queues, telemetry and AI/retrieval context must carry tenant scope and must not combine data across tenants (MOD-004 release-gate layers; TSD §7.3). Only the PostgreSQL layer is mapped in S1; the other layers are OPEN, so do not build or claim them from this rule.
8. **No invention.** Do not invent product behavior or owner policy: regions, keys, retention, hierarchy cardinalities, plan tiers, spend and real-member-data handling are owner-reserved. Placement stays `UNASSIGNED` in S1. Unsupported commands, events or tables are source gaps to raise, not to fill (D8.3).
9. **Synthetic data, local only.** Tests use generated UUIDs and synthetic tenants in a local container, run as the actual runtime role with no application tenant filter (D9). No real data, managed cloud or production target.
10. **Report only what ran.** State a PASS when a command produced it, naming the command. A test that exists is not a test that passed, and a green run on another commit proves nothing about this one.

## Verification evidence

`backend/tests/sql/isolation.sql` is the live half, run by `backend/scripts/verify_db.sh` and by
CI. It carries 60 checks covering every track's tables -- MOD-004's hierarchy, MOD-005's `cfg_`,
MOD-015's `bil_`, MOD-007's and MOD-008's `iam`, MOD-009's `sec_`, MOD-010's `evt_`,
MOD-011's `ops_`, MOD-012's `int_` and MOD-013's `ntf_` -- and **every one has been
run against a deliberate mutation of the protection it guards and shown to fail**:

```bash
MUTATE="ALTER TABLE plt01.organizations NO FORCE ROW LEVEL SECURITY;" backend/scripts/verify_db.sh
```

A new tenant table earns its checks the same way. A check that still passes when its protection is
removed is not evidence, and this suite has already caught one of those: an early "the app role
cannot DELETE" test passed only because a foreign key refused the delete first.

**Mutate the catalogue, not a table you happened to name.** A sweep proves the tables it names
and nothing else. MOD-009's first version probed FORCE RLS on two of its nine tables and ran
sixteen mutations against them, all caught -- and an independent reviewer then removed FORCE from
a third table and watched the suite report every check passing while the migrator read every
tenant's legal holds. Seven of nine tables had no evidence behind them. Checks 17, 22, 28, 33, 39
and 44 assert over `pg_class` and `pg_policies` for exactly this reason, each with a
minimum-count guard so the sweep cannot pass vacuously: a per-table list has to be edited
whenever a module adds a table, and that edit is the moment an unprotected one slips through.

**A sweep that filters `relkind = 'r'` is not a sweep of the schema.** A partitioned table is
`relkind = 'p'`: it holds no storage of its own and is what rows are addressed through, so the
filter -- copied forward through nine modules from the comment explaining why indexes have to
be excluded -- made every catalogue sweep blind to one. A reviewer created
`plt01.ntf_contacts ... PARTITION BY LIST (tenant_id)` holding plaintext email addresses, with
no RLS, no policy, no tenant foreign key and DELETE granted to both runtime roles, read it from
another tenant's context and from no context at all, and the suite reported 60/60. It escaped
the RLS sweep, the column-list pin and the DELETE/TRUNCATE/REFERENCES ban at once. Every sweep
in the file now reads `relkind IN ('r', 'p')`.

**The same holds one level in, for column grants.** MOD-010's first version of check 42 proved
its column-scoped UPDATE grants against a hand-written list of column names, and a reviewer
widened ten different grants while the suite reported every check passing -- including UPDATE on
`evt_outbox.event_type` for the relay role, which re-routes a committed event to a different
consumer set. Checks 42 and 47 now compare the whole column list per table **and per role**
against the catalogue, read through `has_column_privilege` over `pg_attribute` rather than
`information_schema.column_privileges`: those views are filtered to what the current user can
see, so a check running as one role proves nothing about the other and the comparison passes
vacuously for half the roles it claims to cover. The ACL bans need the same treatment --
`pg_class.relacl` holds table-level grants only, so a column-level `GRANT ... TO PUBLIC` is
invisible to a check that reads only it.

**And a role that holds a grant gets a seat.** Every behavioural assertion is written as some
role, and a role nobody sits as is a role nothing is proved about. PostgreSQL combines permissive
policies with OR, so a second policy naming an unexercised role leaves the module's own policy
intact and every predicate comparison true while that role reads every tenant. MOD-010's review
found this for `veyro_cp_worker` on `evt_` tables; the fix was scoped to `evt_` tables, and
MOD-011 granted the worker identical access to eight more and inherited it -- a reviewer opened
all eight with the suite still reporting 48/48. Each module's isolation block now seats every
role that holds a grant on its tables, under another tenant's context and under none, and
asserts exactly one permissive policy per table.

**A constraint nobody has broken on purpose is a constraint nobody has tested, and that has to
mean the table rather than the sample.** MOD-011's check 48 proved twelve CHECKs and three
indexes and said in its preamble that each had been broken and watched to fail -- true of those
fifteen, false of the module: a reviewer dropped 24 of the remaining ones individually and the
suite reported 48/48 every time, including four of the five on a table with no constraint
evidence at all. The same for parent references: seven of eight tenant-registry foreign keys
were droppable in silence because one table's case had been written and the rest asserted.

**A schema change means re-running the mutation sweep, not re-reading the cases.** MOD-012 added
one constraint to close a review finding, and it fired on every row three existing cases insert
-- so three constraints became droppable in silence between one review round and the next, in a
module whose own sweep had been clean an hour earlier. The sweep is the only thing that sees
this; a reader of the new constraint has no reason to look at cases that do not mention it.

**And a case that passes because a *sibling* constraint fired first proves nothing about the one
it names.** Three of MOD-012's constraint cases did exactly that -- a run with an unknown status
also tripped the "a finished run is not running" check, a definition with an unknown status also
tripped "a published version has a publication date", and a third collided with a seeded row on a
unique index before reaching the constraint under test. All three looked correct and all three
passed with their own constraint dropped. The mutation sweep is the only thing that finds this:
set every *other* column so that the row violates exactly one rule.

MOD-013's sweep found four more of these in one module: three siblings firing first, and one
case that inserted a duplicate row and so tested the *primary key* rather than the unique
constraint it named. Three modules in a row have shipped this shape past a careful read, which
is the argument for the sweep rather than for reading harder.

**And a case proves the constraint it names only in the direction it exercises.** Dropping a
constraint is caught; *editing* one is a different mutation, and an equality -- `(A) = (B)`,
the commonest shape in these schemas -- needs a case per side. A reviewer weakened eight of
MOD-013's to one-way implications and the suite reported 60/60 every time: a transactional
receipt could cite a marketing consent and make it read as used, a failed delivery could carry
a delivery time and read as delivered on a status page, a suppression could be released with a
blank reason (MOD-009's `coalesce` finding, in a module that had already paid for it once), and
an SMS notification could carry an email subject. Nothing was broken in the shipped schema; the
*evidence* was half of what its own preamble claimed. **So the sweep's mutations are
weakenings as well as drops**, one per conjunct and one per side of an equality.

**A new trigger invalidates existing cases the same way a new constraint does, and in the
other direction too.** MOD-013 added a BEFORE INSERT trigger pinning one category per template
key, which then fired first on an existing case that tested the unique index with a row
carrying the wrong category -- so that case began proving the trigger instead. Found by the
sweep, immediately, which is the only reason it is a footnote rather than a finding.

Two obligations named in the original rule are covered: check 10 asserts the runtime roles hold no
TRUNCATE, REFERENCES or (for `veyro_cp_app`) DELETE and that neither is a table owner that FORCE
RLS would exempt, and check 11 proves `app.tenant_id` does not survive its transaction onto a
reused pooled connection.

## Scope

Applies to `backend/migrations/`, `backend/app/db.py` and any service that reaches `plt01` or
`iam`. It does
not govern governance, workflow, runner, catalog or registry paths.
