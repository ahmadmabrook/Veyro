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
CI. It carries 72 checks covering every track's tables -- MOD-004's hierarchy, MOD-005's `cfg_`,
MOD-015's `bil_`, MOD-007's and MOD-008's `iam`, MOD-009's `sec_`, MOD-010's `evt_`,
MOD-011's `ops_`, MOD-012's `int_`, MOD-013's `ntf_`, MOD-014's `ppl_` and MOD-016's `cat_` --
and **every one has been run against a deliberate mutation of the protection it guards and
shown to fail**:

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

MOD-016 then did it again in the session that wrote the paragraph above. Closing the
"evidence with nobody's name on it" finding added `cat_prices_supersession_attributed`, which
fires on any row naming a replacement with no actor -- which is exactly what the existing
`cat_prices_not_self` case inserted. That case began passing on the new sibling, and the
second sweep caught it as the one real miss in 483 mutations. **Adding a constraint is a
change to every case that inserts a row the constraint can see, and the author of the
constraint is the last person who will notice.**

**And a "mutation" that changes nothing is not evidence either.** The same sweep reported
`GRANT UPDATE (revoked_by) ON cat_coupons` as uncaught; that column was already in the grant,
so the statement was a no-op and there was nothing for a check to catch. A generated mutation
list needs the already-true ones filtered out, or they read as gaps on every run.

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
the commonest shape in these schemas -- needs a case per side. This is not only about
equalities: MOD-016's `cat_price_resolutions_adds_up` is `final = list - discount`, and its
only case was the under-charging side, so weakening it to `final >= list - discount` passed
72/72 -- a stored receipt reading "10% off 450.00" that charges 900.00, in a table with no
UPDATE and no DELETE grant, on the one invariant that migration's own comment calls "the defect
nobody would spot by reading the number". A reviewer weakened eight of
MOD-013's to one-way implications and the suite reported 60/60 every time: a transactional
receipt could cite a marketing consent and make it read as used, a failed delivery could carry
a delivery time and read as delivered on a status page, a suppression could be released with a
blank reason (MOD-009's `coalesce` finding, in a module that had already paid for it once), and
an SMS notification could carry an email subject. Nothing was broken in the shipped schema; the
*evidence* was half of what its own preamble claimed. **So the sweep's mutations are
weakenings as well as drops**, one per conjunct and one per side of an equality.

**Sweep the schema, not the prefix.** Every `plt01` sweep in this file filtered on its own
module's `ppl_`/`ntf_`/`evt_` prefix, and the `iam` block never did -- check 28 reads the whole
schema, with the comment that says why. A reviewer created `plt01.member_contacts` holding
plaintext addresses, with no RLS, no policy, no tenant foreign key and DELETE held by both
runtime roles, and the suite reported all sixty-six checks passing. That is the same finding as
the partitioned table one paragraph down, escaping on the *name* instead of the `relkind`. There
is now one prefix-free sweep over all of `plt01` requiring ENABLE and FORCE RLS, exactly one
permissive policy and a tenant-registry foreign key, so a table nobody prefixed is caught by the
schema rather than by whoever remembers to add a sweep.

**A primary-key mutation needs `CASCADE`, or it never runs.** `ALTER TABLE ... DROP CONSTRAINT
<pkey>` fails at *mutation* time when a foreign key depends on it, so the suite goes red for a
reason that has nothing to do with the check under test and the sweep records a false catch.
MOD-016's sweep reported fifteen of those. The mutation is `DROP CONSTRAINT <pkey> CASCADE`,
which takes the dependent keys with it and actually exercises the assertion -- and it is the
same trap as the next paragraph, one level up: a protection that resists for a reason other
than the check is a protection with no evidence behind it.

**A primary-key check written as an inner join proves nothing about a table that has none.**
Checking that the first key column is `tenant_id` by joining `pg_index ... indisprimary` means a
table with no primary key contributes no row and is never flagged: thirteen of MOD-014's sixteen
were droppable with the suite reporting 66/66, and the three that resisted were saved by a
dependent foreign key rather than by a check -- which is this file's own MOD-004 trap verbatim.
Assert existence with a `NOT EXISTS`, then assert the shape.

**Nothing in this file had ever read `attnotnull`, in any module.** A `NOT NULL` is a constraint
like any other and it carries load the CHECKs beside it are written to assume: MOD-014's
`ppl_contact_points_normalized_not_blank` correctly has no `coalesce` *because* the column is
NOT NULL, so dropping the NOT NULL admitted a NULL dedup key that passed the not-blank check and
was distinct in the unique index -- unlimited duplicate addresses per person, and the detector
blind to all of them.

**And a hand-written list of the columns that matter is not the pin.** MOD-016's first version
of that pin named 37 (table, column) pairs it had reasoned about; a sweep then dropped NOT NULL
from all 120 of its non-key columns one at a time and **84 of them passed 72/72**. Two reasons
that matters more than "a NULL where a value was expected", and the second is the one nobody
would predict:

  * **A NOT NULL is what makes a sibling CHECK bite.** `cat_discount_approvals_amounts_sane`
    evaluates to NULL and therefore passes the moment `list_amount_minor` is nullable, so "an
    override cannot exceed the list price" stops being enforced -- and the service then raises
    on `int(None)` and answers 500.
  * **MATCH SIMPLE.** A NULL in *any* column of a composite foreign key skips the check
    entirely, so dropping NOT NULL from `cat_prices.price_book_id` or
    `cat_price_resolutions.price_id` silently switches off a tenant-carrying parent reference.
    The foreign-key *set* comparison cannot see it, because the key is still there.

So each module pins **every** NOT NULL on its tables, compared as a set in both directions
against the catalogue, exactly like the column lists and the grants.

**A `coalesce` case has to use NULL, not a blank string.** Every attributed-decision case in
this file tested `'  '`, which the constraint refuses either way -- so the `coalesce` the
comments call load-bearing was removable from three MOD-014 constraints with the suite green.
`length(btrim(NULL)) > 0` is NULL, the AND-branch is NULL, `false OR NULL` is NULL, and a CHECK
passes on NULL. The blank case proves the `btrim`; only the NULL case proves the `coalesce`.

**A compound CHECK that names a status domain cannot be tested, and neither can its
siblings.** MOD-014 wrote one constraint as `(status = 'active' AND a IS NULL AND b IS NULL) OR
(status = 'merged' AND a IS NOT NULL AND b IS NOT NULL)`, which is correct and means every
status value outside the two fails *it* as well as the domain CHECK beside it -- so the domain
CHECK and a third constraint on the same columns were both droppable with the suite reporting
66/66, their cases passing on this one's refusal. Split into `(a IS NULL) = (b IS NULL)` and
`(status = 'merged') = (b IS NOT NULL)`, each of the four is isolatable and each has a case per
side. The sweep is the only thing that finds this; a reader of the compound constraint has no
reason to suspect it.

**PostgreSQL evaluates a CHECK before the foreign-key trigger, so a case naming a parent that
does not exist proves the CHECK for the wrong reason.** Three MOD-014 cases referenced a person
that was never seeded: the CHECK under test fired first and the case passed, and it would have
kept passing with that CHECK dropped -- as a `foreign_key_violation` the handler does not catch,
which is a red suite with an unhelpful message rather than a named failure. Seed every parent a
case names.

**A new trigger invalidates existing cases the same way a new constraint does, and in the
other direction too.** MOD-013 added a BEFORE INSERT trigger pinning one category per template
key, which then fired first on an existing case that tested the unique index with a row
carrying the wrong category -- so that case began proving the trigger instead. Found by the
sweep, immediately, which is the only reason it is a footnote rather than a finding.

Two obligations named in the original rule are covered: check 10 asserts the runtime roles hold no
TRUNCATE, REFERENCES or (for `veyro_cp_app`) DELETE and that neither is a table owner that FORCE
RLS would exempt, and check 11 proves `app.tenant_id` does not survive its transaction onto a
reused pooled connection.

**A constraint that is subsumed by a sibling should be deleted, not tested harder.** MOD-016
carried both `cat_eligibility_rules_kind` (a domain over seven kinds) and
`operand_matches_kind` (a four-branch disjunction that names all seven and the operand each
takes). Every value that violates the domain violates the disjunction too, so the domain CHECK
had no isolating case and could not have one: the sweep caught its drop as uncaught, and the
repair was to remove it. One constraint that is the stronger statement beats two where the
weaker is permanently unprovable -- which is the same judgement as splitting MOD-014's compound
CHECK, arrived at from the other direction.

## Scope

Applies to `backend/migrations/`, `backend/app/db.py` and any service that reaches `plt01` or
`iam`. It does
not govern governance, workflow, runner, catalog or registry paths.
