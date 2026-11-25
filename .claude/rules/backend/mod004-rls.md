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
CI. It carries 114 checks covering every track's tables -- MOD-004's hierarchy, MOD-005's `cfg_`,
MOD-015's `bil_`, MOD-007's and MOD-008's `iam`, MOD-009's `sec_`, MOD-010's `evt_`,
MOD-011's `ops_`, MOD-012's `int_`, MOD-013's `ntf_`, MOD-014's `ppl_`, MOD-016's `cat_`,
MOD-017's `mem_` and `fin_`, MOD-018's `led_`, MOD-019's `sch_`, MOD-020's `bkg_` and
MOD-021's `dev_`, MOD-022's `acc_` and MOD-026's `tsk_` -- and **every one has been
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

**A case catches a weakening only if the weakened constraint ADMITS the row.** This is the
subtlest trap in the file and MOD-017 walked into it twice. `fin_invoice_lines_adds_up` is
`gross = net + tax`, and its case over-stated the gross -- which the loose `gross <= net + tax`
refuses just as surely as the equality does, so the suite stayed green and the weakening passed
with the case sitting right there looking correct. The case that bites is the one charging
*less* than the parts come to: the equality refuses it today and the weakened constraint lets it
through, which is what makes the RAISE fire. Same for `net = unit * quantity`, where the `>=`
weakening is caught only by a net that is *more* than the product. **So the question to ask of a
one-directional case is not "does this row violate the rule" but "which weakening would admit
this row"** -- and a pair of cases is right only when the two rows fall on opposite sides of the
equality, not merely when both are invalid.

**A deferred constraint trigger fires at COMMIT, so a case that rolls back never sees it.**
MOD-018's "a journal balances" rule is the one invariant the whole module rests on, and it
cannot be a CHECK: the sum is over the postings, which do not all exist until the last one is
inserted. So it is a `CREATE CONSTRAINT TRIGGER ... DEFERRABLE INITIALLY DEFERRED`, which the
isolation suite's own pattern -- insert the bad row, catch the exception, `ROLLBACK` -- cannot
observe at all, because the trigger runs at a commit that never happens. The case has to say
`SET CONSTRAINTS ALL IMMEDIATE` first, and then the insert raises where a reader expects it to.
A case written the ordinary way passes with the trigger dropped, which is the same false green
as every other paragraph here and arrives by a route none of them cover.

**A plpgsql branch is invisible to a generated constraint sweep, so every branch needs its
own probe and the probe count has to be asserted.** The mutation for a trigger's logic is
`CREATE OR REPLACE FUNCTION` with one branch deleted, which touches nothing in
`pg_constraint` and nothing a generated list of `ALTER TABLE` statements can reach.
MOD-018's balance trigger had five branches and four probes: a reviewer deleted the
mixed-currency branch, watched the suite report 84/84, and then committed a journal that
"balanced" by setting dollars against dinars. The structural answer is the one that scales --
each probe raises `CHECK nn FAILED` when the trigger does *not* refuse, and the block ends
`IF probe <> N THEN RAISE`, so a branch with no probe fails and a `SET CONSTRAINTS` that
silently did nothing fails too. A trigger whose existence is proved by its DROP is not a
trigger whose *logic* is proved.

**A trigger can subsume a CHECK's bound, and then the CHECK has no isolating case.**
MOD-018's banked-session trigger bounds an amount against what the till counted, and a count
is itself bounded at 1e12 -- so the hand-written ceiling on the same column became
unreachable, and its case began proving the trigger. Same judgement as a constraint subsumed
by a sibling: narrow the CHECK to the part that is still the primitive statement and say in a
comment where the rest went. **The sweep is the only thing that notices**, because the author
of the trigger has no reason to re-read a constraint that does not mention it.

**A biconditional between a status and its timestamp breaks the moment a state is re-entered.**
`(status IN ('closed','reopened')) = (closed_at IS NOT NULL)` reads as exactly right and made
the one edge out of `reopened` unsatisfiable: a period closed, reopened and closing again
legitimately keeps its close timestamp, so the UPDATE violated the CHECK, the route answered
500, and the lock could never be re-applied. The implication is the true half -- a closed
period has a close time -- and "a close time never disappears" is a different obligation that
only a trigger can see. Written as a biconditional, the two are one constraint and the
stronger half is wrong.

**The prefix-free sweep has to carry every control, not three of them.** Check 61b was added
after MOD-014's `member_contacts` finding and covered ENABLE+FORCE RLS, exactly one permissive
policy and a tenant-registry foreign key -- so a table satisfying those three with
`USING (true)`, DELETE, TRUNCATE and a PUBLIC grant read every tenant's rows and deleted them
with the suite green. The predicate shape, the privilege bans, the tenant-leading primary key
and the forbidden column names all lived in per-module checks, and a name matching no prefix
escaped all of them: a reviewer called the table `ledger_running_balances` and it also walked
past MOD-018's own two absence-sweeps. All of it is prefix-free now. **And compare the
predicate against the approved text rather than searching it**: the approved expression's own
second argument to `current_setting` is the literal `true`, so a sweep hunting for "true"
flags all 130 policies and one hunting for "app.tenant_id" passes anything that mentions it
beside an `OR true`.

**`SELECT ... FOR UPDATE` needs the UPDATE privilege**, so a row on an insert-only table
cannot be locked that way -- the statement fails with `permission denied for table`, at
runtime, on whichever path happens to need the lock. Where the serialisation is still needed,
`pg_advisory_xact_lock(hashtextextended(key, 0))` needs no table privilege and is what MOD-009
and MOD-018 both use.

**A unique index is not a constraint, and the mutation differs.** `ALTER TABLE ... DROP
CONSTRAINT <name>` fails with "constraint does not exist" for an index created by `CREATE UNIQUE
INDEX`, which is how every partial index in this build is written -- the `WHERE` clause is not
available on a constraint. The mutation is `DROP INDEX`, and a harness that generates only the
first form reports a protection as tested when the statement never ran.

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

**`length(btrim(x)) > 0` strips spaces and nothing else.** PostgreSQL's one-argument `btrim`
removes spaces, so every "states a reason" and "describes what it is for" control in this
build was satisfied by a single tab or a single newline -- 118 constraints across ten
migrations, every one of them written to refuse exactly that. The shape in use now is
`x ~ '[^[:space:]]'`: the value contains at least one character that is not whitespace, which
is also the clearer statement of intent, since nothing here ever wanted the *trimmed length*.
Found by a generator bug, not by reading: MOD-017's case generator wrapped a `'  '` literal
across lines, which turned it into a newline-plus-spaces literal, and that **passed** the
constraint it was written to violate.

**A status domain whose siblings all fire first is proved by an UPDATE, not an INSERT.**
`mem_memberships.status` is a domain over eight values, and every value but `pending` needs a
`status_change_id` -- a three-column reference including the membership's own id, which does
not exist until the row does. So every insert with an unknown status trips
`status_has_a_change` before the domain, and the domain has no isolating case available on
that path. Updating a row the suite already seeded violates the domain and nothing else. Three
of MOD-017's four status domains *were* isolatable on an insert once the sibling's fields were
set (a reservation carrying its settlement, an agreement carrying its signature, a dunning case
carrying neither a next action nor a closure), which is the ordinary repair; this is the one
where it is not available.

**A unique index a foreign key depends on cannot be dropped, so its mutation never runs.**
PostgreSQL refuses `DROP INDEX` while a composite foreign key needs that index, and the refusal
is an error from the mutation statement rather than a failure of any check -- which a naive
harness records as a catch. That is the `DROP CONSTRAINT <pkey>` trap one level over, where the
answer was `CASCADE`; here `CASCADE` would take the foreign key with it and test something
else, so the honest handling is to classify the mutation as not-run and say which index it was.
A sweep that reports those as caught is reporting the same false green the whole discipline
exists to prevent.

**`FOR SHARE` does not conflict with `FOR SHARE`.** A trigger that reads a parent row to
decide whether a child may be inserted has to take `FOR UPDATE`, not a share lock: two
inserters hold a share lock at once, neither sees the other's uncommitted row at READ
COMMITTED, and both commit. MOD-019's capacity trigger -- the whole of paragraph 4146's
Critical Control -- took `FOR SHARE`, and a reviewer put four places in a two-place class with
two ordinary transactions and no adversary. The service happened to be safe because it takes
`FOR UPDATE` on the session before counting; the trigger exists for the writer that is *not*
the service, which is the half that failed. **And no probe in this file could ever have seen
it**, because a single psql session cannot race itself: a lock needs a test on two
connections, which means a Python test, not an isolation check.

**When two controls refuse the same row, a probe proves whichever one answers -- so it has to
assert which.** Two of MOD-019's triggers open by refusing a row whose parent session does not
exist, which reads like the control and is not: the composite foreign key is, and the branch
merely fires first (a BEFORE INSERT trigger runs before the reference is checked) to answer in
a sentence instead of a constraint name. The probes inserted exactly that row, so dropping
either trigger was "caught" by the key and the sweep reported an error naming a constraint
rather than a named failure. The probe now handles `foreign_key_violation` separately and
raises its own `CHECK nn FAILED` naming the confusion, which is the only way the count
assertion can see the branch disappear.

**A probe whose own statement is refused by a sibling CHECK aborts the whole DO block, so one
bad probe hides every probe after it.** MOD-019's owner-role block moved a session's start
*past* its end, which `sch_sessions_ordered` refuses -- and `check_violation` is not caught by
`WHEN raise_exception`, so with the trigger branch deleted the block died on an unnamed error,
the three probes after it never ran, and the `IF probe <> N` assertion never evaluated. One
case gated the rest. Move the value in the direction that keeps every *other* rule satisfied.

**A conjunct that makes a sibling evaluable is load-bearing in a way nothing reads as.**
`restriction_kind NOT IN ('min_age','max_age') OR (value ~ '^[0-9]{1,3}$' AND value::integer
<= 120)` looks like a regex for shape plus a cast for the bound. Weakening it by removing the
regex showed otherwise: `'sixteen'::integer` *raises*, so the constraint was correct only
because PostgreSQL evaluated the left conjunct first -- which it does not promise. On the day
it did not, a typo at the front desk would answer 500 with `invalid input syntax for type
integer` instead of a clean refusal. The repair is to remove the dependency rather than
document it: a regex encoding 0 to 120 needs no cast and no evaluation order. **Any CHECK whose
right operand would raise on input its left operand excludes has this shape**, and only a
weakening mutation finds it.

**A blank case uses a tab, not spaces.** Every "states a reason" case in this file sent `'  '`,
which `btrim` strips -- so a reviewer restored `length(btrim(x)) > 0` on all eight of MOD-019's
not-blank constraints and only the definition pin objected. The whole point of the
`~ '[^[:space:]]'` rewrite was that spaces are not the only whitespace, and a case made of
spaces cannot tell the two forms apart.

**A harness that misclassifies a catch hides the one real gap among the noise.** MOD-019's
first sweep reported 749 of 757 mutations as MUTERR, because the worker looked for any `^ERROR`
in the three lines after the mutation and found the *check's own refusal* there. The opposite
misclassification -- reporting caught when the mutation never ran -- is the dangerous one and
this file already records it; this one is merely noisy, and it would have buried a genuine
MUTERR in 749 false ones. A classifier has to exclude `CHECK nn FAILED` before calling a
mutation failed. **And a fix script that aborts on an assertion leaves the fixes after it
unapplied**: four of MOD-019's own evidence repairs were lost that way and the same seven
mutations came back on the next pass, which is how it was noticed.

**Pin the rules themselves, not only the tables they sit on.** Every paragraph above is
about a behavioural case that turned out to prove nothing, and each was found by a mutation
sweep -- which is a thing a person runs, not a thing CI does. MOD-019 adds a second line of
evidence that runs on every build: check 91 compares the *text* of every CHECK, every index
and every trigger against a pinned set in both directions, plus an `md5` of each trigger
function's body. A drop, a weakening and a deleted plpgsql branch all change the text, so all
three fail in CI rather than at the next sweep. It does not replace the cases -- a pin says
the rule is still written down and only a case says it still bites, and one without the other
is how vacuous evidence happens -- but it closes the window between a regression landing and
somebody next running 750 mutations. The cost is deliberate: a legitimate schema change fails
the pin until it is regenerated, which is the moment a human reads the diff. It caught two of
MOD-019's own changes while they were being made.

**It also gives an unprovable constraint somewhere to live.** `sch_templates_status` is a
domain over three values, and every value outside them also violates `published_has_a_rule` on
an insert while the one-way trigger admits only two transitions on an update -- so no path
reaches an unknown status with that CHECK as the only thing in the way. Previously the choice
was to delete it (the rule two paragraphs down) or to let a case pass on a sibling. With a
definition pin there is a third option that is better than both: keep the primitive statement,
say in the migration that it has no behavioural case and why, and let the pin be its evidence.

**A trigger branch that a foreign key would also refuse is a message, not a control -- and its
probe has to know the difference.** Two of MOD-019's triggers open by refusing a row whose
parent session does not exist, which reads like the control and is not: the composite foreign
key is, and the branch merely fires first (a BEFORE INSERT trigger runs before the reference
is checked) to answer in a sentence rather than a constraint name. The probes inserted a row
naming a missing session, so dropping either trigger was "caught" by the key, and the sweep
reported the drop as an error with a misleading message rather than as a failure. The probe now
handles `foreign_key_violation` separately and names it, which is the only way the count
assertion can see the branch disappear. **The general form: when two controls refuse the same
row, a probe proves whichever one answers -- so it has to assert which.**

**A conjunct that makes a sibling evaluable is load-bearing in a way nothing reads as.**
`restriction_kind NOT IN ('min_age','max_age') OR (value ~ '^[0-9]{1,3}$' AND value::integer
<= 120)` looks like a regex for shape plus a cast for the bound. Weakening it by removing the
regex showed otherwise: `'sixteen'::integer` *raises*, so the constraint was correct only
because PostgreSQL evaluated the left conjunct first -- which it does not promise. On the day
it did not, a typo at the front desk would answer 500 with `invalid input syntax for type
integer` instead of a clean refusal. The repair is to remove the dependency rather than to
document it: a regex that encodes 0 to 120 needs no cast and no evaluation order. **Any CHECK
whose right operand would raise on input its left operand excludes has this shape**, and a
weakening mutation is what finds it.

**A self-referencing constraint needs the row's own id supplied.** `fin_invoices_not_self` and
`mem_agreements_not_self` had no isolating case for a reason that is obvious once stated and
invisible otherwise: with the key defaulted to `gen_random_uuid()` there is nothing for the
case to point at, so every attempt pointed at some other row and passed. The case sets the key
explicitly and references it; the foreign key resolves against the row being inserted, so the
only thing left to refuse is the constraint under test.

**A constraint that is subsumed by a sibling should be deleted, not tested harder.** MOD-016
carried both `cat_eligibility_rules_kind` (a domain over seven kinds) and
`operand_matches_kind` (a four-branch disjunction that names all seven and the operand each
takes). Every value that violates the domain violates the disjunction too, so the domain CHECK
had no isolating case and could not have one: the sweep caught its drop as uncaught, and the
repair was to remove it. One constraint that is the stronger statement beats two where the
weaker is permanently unprovable -- which is the same judgement as splitting MOD-014's compound
CHECK, arrived at from the other direction.

MOD-017 gave three more of the same kind, all of them arithmetic:
`fin_invoice_lines_net_not_negative` is implied by `net_minor = unit_net_minor * quantity`
with a positive quantity and a non-negative unit price; `fin_tax_records_taxable_not_negative`
is implied by `tax_minor >= 0` and `tax_minor <= taxable_minor`; and
`fin_tax_records_tax_sane` is implied by that second pair plus `taxable_minor <= 1e12`. Each
had a case, each case passed with the constraint dropped, and in each the row that violated it
necessarily violated one of the others. **The tell is worth naming: a bound on a *derived*
column is usually implied by the bounds on what it is derived from.** Delete it and keep the
primitive one, which is the constraint a reader can reason about.

## Scope

Applies to `backend/migrations/`, `backend/app/db.py` and any service that reaches `plt01` or
`iam`. It does
not govern governance, workflow, runner, catalog or registry paths.


**A constraint subsumed by a *trigger* loses its case the same way one subsumed by a sibling
CHECK does, and a trigger added for correspondence subsumes a whole family at once.**
MOD-020's review asked for two triggers relating a sanction and a fee to the booking they
cite -- member, session, state and the thresholds the booking snapshotted. Adding them made
six constraints unprovable in one change: every bound on a copied policy figure
(`policy_hours`, `policy_warn_after`, `policy_strike_after`, and the ordering between the last
two) is now implied by "it equals the policy's, which is itself bounded", so no row can reach
them. All four were deleted with a comment saying where the rest went -- which is the same
judgement as MOD-016's `cat_eligibility_rules_kind` and MOD-018's banked-session ceiling,
arrived at from a third direction. **The tell: a correspondence trigger makes every bound on
the column it relates derived, and a bound on a derived column is usually implied by the
bounds on what it is derived from.**

**And it invalidates every case that inserts a row the trigger can see, which for a
correspondence trigger is every case on the table.** Twelve cancellation and fourteen no-show
cases inserted against a booking that was still `booked`; the trigger now refuses that
outright, so all twenty-six began proving the trigger rather than the rule they named. The
repair is a seed row per *state* the trigger admits -- MOD-020 seeds a cancelled booking, a
no-show booking and a gym-released booking, each with no record of its own -- and the sweep is
the only thing that tells you how many cases moved.

**Nothing in this file had ever read `proconfig`, `prosecdef` or `tgenabled`, in 39,000
lines.** So two properties a migration asserts in as many words were verified by nothing: a
reviewer ran `ALTER FUNCTION ... RESET search_path` against "their `search_path` is pinned" and
`GRANT EXECUTE ON FUNCTION ... TO PUBLIC` against the migration's own closing `REVOKE ALL ...
FROM PUBLIC`, and the suite reported every check passing both times. `md5(prosrc)` cannot see
`proconfig`, so a definition pin is blind to it, and `ALTER TABLE ... DISABLE TRIGGER` leaves
the catalogue row in place so the pin is blind to that too. Each module's privilege check now
sweeps all three over its own functions and triggers -- and it caught the author's own two new
functions the moment they were added, which is the argument for sweeping rather than naming.

**A probe answered by a sibling branch *in the same function* is the hardest version of the
"two controls refuse the same row" trap.** MOD-020's appeal trigger refuses any update that
does not take an open appeal to a decided state, so a probe for the identity branch -- which
only changed what the appeal is about -- was answered by the branch above it, and the identity
branch was droppable with only the definition pin objecting. The probe has to satisfy every
*earlier* branch of the same function, not just every other constraint on the table. The same
module's booking trigger had the sibling-*trigger* version: `bkg_bookings_hold_matches` sorts
before `bkg_bookings_one_way`, so a probe that moved `hold_id` proved the wrong trigger
entirely.

**A test fixture that takes its own `today` from the local clock disagrees with a service that
takes it from UTC, for as long as the two dates differ.** Four of this repository's HTTP suites
used `date.today()` while every service uses `datetime.now(UTC)`, so east of UTC the fixtures
were a day ahead for the first hours of each night: a journal posted on the local date fell
outside a trial balance read as of the UTC date, and sixteen tests across two modules failed
for a reason that had nothing to do with either. **CI never saw it, because CI runs in UTC** --
which is the worst property a flake can have, since the green run is the one that proves
nothing. A fixture takes its clock from the same place the code under test does.

**A `NOT EXISTS` branch answers for the missing-parent branch above it, and only the message
tells them apart.** Three of MOD-021's trigger functions open by refusing a row whose parent
device does not exist and then ask `NOT EXISTS (SELECT ... WHERE device_id = NEW.device_id)`
-- which is true for a device that does not exist. So with the first branch deleted the row
is still refused, by the second, and a probe that counted any `raise_exception` was satisfied:
all three branches were droppable with only the definition pin objecting. This is the
"probe answered by a sibling branch in the same function" trap in its quietest form, because
nothing about either branch reads as overlapping -- one is about existence and the other about
capability. The probe has to assert the *message*, not the exception class, and raise its own
`CHECK nn FAILED` naming the confusion when the wrong branch answers. **The tell: a branch
that guards a lookup result is subsumed by any later branch whose predicate is also satisfied
by the lookup having failed.**

**And the same trap one level up, where the two branches are two different controls.**
MOD-021's unlock path has two refusals -- no live safety profile, and fewer than seven passing
commissioning tests -- and the probe for the first used a device that had neither, so it was
answered by the second and the first was droppable in silence. A probe needs a row that only
the branch under test refuses, which means the *fixture* has to carry one device per branch:
one commissioned and tested, one tested with no profile, one profiled with no tests. When two
controls can refuse the same row, it is not enough to assert which one answered; the row has
to be one the others admit.

**A trigger that reads a parent row to decide whether a child may be written must take
`FOR UPDATE`, and a plain read is weaker than `FOR SHARE`.** This file already records
MOD-019's share-lock finding; MOD-021 shipped three triggers that took no lock at all, and
one of them is the whole of paragraph 1953's revocation guarantee. Two ordinary transactions
at READ COMMITTED -- one bumping a device's revocation epoch, one inserting a policy snapshot
that reads it -- both committed, leaving a snapshot valid for twelve hours at an epoch the
device had already left. **The service was safe in all three cases**, because it locks the
row before it acts; the trigger is the half that holds for the writer that is *not* the
service, and that half did not hold. No isolation check can see this: it needs a test on two
connections.

**A bound measured between two columns the same writer supplies is not a bound.**
`expires_at - issued_at <= interval '60 seconds'` reads as "deliverable for a minute" and
means "deliverable for a minute, starting whenever the writer says" -- so an unlock parked
three days ahead satisfied every CHECK on the table and was openable for forty-five seconds
on the night it chose. The same shape made a policy snapshot's "bounded TTL" a seven-day
authorization nobody could withdraw. The repair is a bound against the server's clock, and it
has to be **one-sided**: `issued_at <= now() + interval '5 minutes'` is restore-safe, while a
lower bound would fail every existing row the next time the constraint is validated.
PostgreSQL does permit `now()` in a CHECK, which is the unusual part and the reason to say so
in the migration.

**A deferred constraint trigger is sometimes the only shape that lets the honest write order
exist.** MOD-021 relates each supersession pointer to the row's own device, and an immediate
check would have made rotation unwritable: the outgoing certificate has to point at a
successor that does not exist yet, because inserting first violates `one_active_per_device`
and a null pointer violates the pairing. The foreign key beside it is already
`DEFERRABLE INITIALLY DEFERRED` for exactly that reason, so the relational check is too --
and the probe then needs `SET CONSTRAINTS ALL IMMEDIATE`, which this file already records for
MOD-018's balance trigger. **When a BEFORE trigger's check fights the only order the service
can write in, the answer is usually to defer it rather than to reorder the service.**

**The prefix-free sweeps need the privilege bans and a shape, not only a name list.** Check
61b was hardened after MOD-014 and still let a reviewer create `plt01.edge_credentials` with
ENABLE+FORCE RLS, one correct policy, a tenant foreign key, a tenant-leading key, columns
named `key_material`, `cert_body` and `online_cached`, and `DELETE` granted to both runtime
roles -- 105/105 passed. Three causes, each general: the DELETE ban that `CLAUDE.md` states
absolutely lived only in per-module lists; `has_table_privilege` cannot see a column-scoped
`GRANT ... TO PUBLIC`, so `GRANT UPDATE (state) ON ... TO PUBLIC` was invisible to every
check in the file; and a forbidden-column-name list is whack-a-mole, so it needs patterns for
the *shape* beside the explicit names.


**A probe asserts the sentence, not the exception class, and the fixture carries a row per
branch.** MOD-022 has ten trigger functions and forty-four plpgsql branches, and the module
shipped with probes for a handful: a reviewer replaced five of the ten functions with
`BEGIN RETURN NEW; END` and the suite reported 109/109. Check 111 is one probe per branch, and
three things make it evidence rather than decoration -- each the answer to a trap this file
already records, met again in one module:

  * **the message.** A branch guarding a lookup result is subsumed by any later branch whose
    predicate is also satisfied by the lookup having failed, so a probe that counts any
    `raise_exception` proves whichever branch replies. Each probe names the sentence it
    expects and records a different one as a *confusion*, which fails the check.
  * **the row.** A BEFORE trigger runs before every CHECK on the table, so a probe whose row
    also violates a CHECK still passes with its branch deleted -- the CHECK answers instead.
    Each row here is the committed seed's own row with exactly one field moved, which is the
    same discipline the generated constraint cases use for the opposite reason.
  * **the fixture.** A probe needs a row that *only* the branch under test refuses, and for a
    one-way trigger that means a row in each state: a retired zone, a retired point, a revoked
    credential, a reconciled event and a reviewed unlock, plus a second door that is probed
    live and then retired because two branches need it both ways. The fixture statements run
    inside the same block, in order, and a fixture that is itself refused is reported as such
    rather than counted.

**And a branch mutation has to be encoded, not flattened.** The sweep carries each mutation on
one tab-separated line, and the first version replaced every newline in the function body with
a space -- which turns each `--` comment into one that swallows the rest of the definition. All
forty-four branch mutations were refused with "syntax error at end of input" and recorded as
not-run: the harness reporting a gap it had created, which is the same false green as every
other paragraph here arriving by a route none of them cover. Encode the newlines and decode
them at the psql boundary.

**A test that proves a volume bound by making the requests has a green that depends on how
fast the machine is.** `test_an_unparseable_identifier_still_gets_a_stable_key` makes
thirty-two login attempts and expects the thirty-first to be refused. Every refused login
deliberately costs one scrypt -- MOD-007's timing-attack defence, where a locked identity
answering in two milliseconds while everything else took fifty identified every registered
address in five requests -- so those thirty-two are slow, and on a slower runner they cross
the limiter's fixed-length window. The count resets, the budget is never reached inside one
window, and the 429 never arrives. **It passed locally and failed in CI**, which is the worst
property a flake can have, and it is the same family as the budget-consuming tests this file
already records: a green that depends on something other than the behaviour under test.

The fix is a clock seam -- `create_app(..., clock=time)`, frozen by the two test classes that
prove a volume bound. The requests stay real and the limiter stays real; only the window stops
moving underneath them. **And the seam has to be mutation-proven like anything else**: with
the limiter's `raise` removed, those tests fail, so freezing the clock did not make them
vacuous.

**A positional cell locator is a test coupled to a layout decision it does not care
about.** `row.getByRole("cell").nth(2)` was the public-reason cell on the door board until
that board moved to a grid whose columns are ordered by priority -- then it pointed at the
private reason, and a test about paragraph 1944's discreet line failed for a reason that has
nothing to do with the discreet line. Filter the cell by what it contains, or by a header
association; the index is a coincidence of the current layout and it is exactly what a design
migration changes.

**And an attribute's *order* is the same coincidence, in a test that reads served HTML.**
`no-js.spec.ts` found the sign-in form with `html.indexOf("<form noValidate")`, which worked
only while `noValidate` was the first attribute React emitted -- adding `id` to the element so
a sibling button could read its fields moved it, and both tests in the file failed with "the
served HTML must contain the sign-in form" against a page that plainly contained it. The
message is the worst part: it names a product defect the app does not have, which costs the
same trust as missing one. Locate by something the page states on purpose -- an id, a role, a
name -- and remember the page has other forms, so matching the wrong one is the failure worth
ruling out rather than the one worth risking.

**And the same migration can add a defect the ad-hoc one did not have, on every screen at
once.** The hand-rolled tables all named themselves with `aria-labelledby` pointing at the
heading above them, with a comment on one of them explaining why: a caption that repeats the
heading is the sentence said twice, invisible to a sighted reader and heard in full by a
screen-reader user. `DataGrid` rendered its own visually-hidden caption, so the first
migration put the duplication on eight grids in one change -- and exactly one e2e test, on one
page, noticed. The component takes `labelledBy` now, and a sweep requires every `<DataGrid>`
to pass it. **A shared component inherits a contract from each call site it replaces**, so
read what the thing being replaced does for accessibility before deleting it, not only what
it does visually.

**Replacing an ad-hoc component with the approved one can drop a contract the ad-hoc one
happened to satisfy.** `controls.tsx`'s button hard-coded `minHeight: 44px`, which met the
design system's touch-target floor by accident of one line. The design system's Button is
sized `sm | md | lg` at 28/36/44 and defaults to `md`, so the moment the sign-in form moved
to it the one control a member must hit before anything else works became 36px on a phone --
with the component *more* compliant in every other respect. The e2e assertion caught it; no
unit or component test could, because both halves were individually correct. **Before
deleting an ad-hoc component, read what it hard-codes**, and put each of those properties
somewhere in the replacement rather than assuming the richer API covers them. The floor now
lives in the component layer under `(pointer: coarse)`, which is where the source puts it:
accessibility, RTL and responsive behaviour belong to the component, "not in a screen spec",
because otherwise every new screen re-implements them.

**A string that never became a message key is invisible to the parity check, and the check
cannot be made to see it.** `MESSAGE_KEYS` compares the two catalogues against each other --
in both directions now -- so it catches a key present in one and missing from the other, and
is structurally blind to English prose held in a `Record<string, string>` in a library and
rendered straight to the page. MOD-013's board shipped eight decision reasons that way, so
the single most explanatory field on an Arabic page read in English while every heading,
caption and empty state around it was correct. **No assertion about structure can find this
and none did**: it was found by switching the language and looking at the page. The durable
answer is a test per module that asserts every key *that module maps to* exists in both
catalogues, which is the parity check run from the side the catalogue cannot see.

**A surface branch no fixture can reach is the same vacuity, one layer up, and it has now
happened four times in four modules.** `Alert`'s `warning` tone with no period in `closing`;
the promotion block with only a live promotion seeded; the legal-hold list rendering a
`Released` branch while the client asked only for live holds; the product verdict with only a
sellable product. Each was code that looked tested, had an assertion written for it, and
proved nothing -- the assertion passed because the branch never ran. It is MOD-020's "a
declared state nothing writes" finding arriving in a UI, and the remedy is the one this file
already states for constraint cases: **the fixture carries both members of the pair the
distinction is about.** One `closing` period beside an open one, one expired promotion beside
a live one, one released hold beside a preserving one. A board with one of each kind renders
and demonstrates nothing.

**And a redundant comparison in a client reads as a control exactly as a subsumed constraint
does.** A request queue sorted `overdue` first and then by deadline; the sweep reported the
first comparison as uncaught, correctly, because an overdue request is one whose due date has
passed and a not-overdue one is a date still to come -- so the date sort already orders them.
The remedy is the one this file records for a constraint subsumed by a sibling: delete it and
keep the primitive statement, rather than contriving a case that cannot exist.

**An unbounded read is not a defect until something renders it, and then it is two.** MOD-007's
`list_sessions` returned every session an identity had ever opened, which was invisible for as
long as the only caller was a test asserting that one of them was there. The first page to
render it was 13,542 pixels tall -- and the bigger half is that bounding it in the *client*
would have fixed the page and nothing else: the response still carries every device that person
has signed in from, which is a read of their whole login history served to answer "am I signed
in anywhere else". **The bound belongs where the rows are selected**, with the same two
properties every other listing read in this build has: a ceiling the server refuses above, and
a filter for the question actually being asked (`live_only`, here, because a revoked session is
not something a member can act on). This is the "a writer with no reader" gap from the other
side -- a read nobody rendered is a read nobody sized.

**A test that consumes a product budget provisions its own, and this is the fourth instance.**
A single-use recovery code spent on a device challenge; thirty logins a minute spent by a
`beforeEach`; five recovery failures that lock the path with nothing in the build to reset it;
and now minting recovery codes, which needs a step-up, which spends a recovery code. Each was
green on a fresh fixture and red on the second run, which is a green that depends on how many
times the suite has been run rather than on the behaviour under test. The fixture carries a
fourth identity for the reissue test for exactly this reason. **Running the suite twice in a
row is what finds these**, and nothing else does.

**A rate limit whose budget is not declared is not a rate limit, and the structural test has
to be mutation-proven too.** MOD-022's evaluate route named a budget `ratelimit.BUDGETS` did
not carry, and `decide` defaulted to allowing -- so the route read as limited and was not.
`decide` refuses an undeclared key now, and a test walks `main.py` with `ast` and asserts every
`rate_limit(limit_key=...)` names a declared one. A structural sweep that passes vacuously is
the thing it exists to prevent, so that test was run against a deliberately undeclared budget
and shown to fail before it was believed.


**`check_violation` does not say which constraint refused the row, so a case that counts it
proves whichever fires first.** This file records the "caught by a sibling" trap for MOD-012,
MOD-013, MOD-014, MOD-016 and MOD-020, and every one of those was found by a mutation sweep
afterwards -- which means the sweep is the only instrument and it runs when a person runs it.
There is a structural answer and MOD-022 is the first module to use it:

```sql
EXCEPTION
    WHEN check_violation THEN
        GET STACKED DIAGNOSTICS offender = CONSTRAINT_NAME;
        IF offender = 'the_rule_under_test' THEN probe := probe + 1;
        ELSE confused := array_append(confused, '... answered by ' || offender); END IF;
```

With that in place a case answered by a sibling fails **on a clean database**, in CI, rather
than at the next sweep. It found four more the moment it was added, two of them in cases a
careful reader had just written: a separation-of-duties case answered by the attribution CHECK
beside it, and a `granted = (code = ANY ...)` case answered by the code domain -- because the
shape reader moves the column the predicate *names*, and for a correspondence rule that column
is usually the wrong one to move. The same applies to `unique_violation`, where
`CONSTRAINT_NAME` is the index's own name.

**And then the row has to be able to reach the rule.** Fourteen of MOD-022's generated cases
were refused by a sibling because the sibling guards the same column from a different angle:
an attribution trio fires before the ordering rule it sits beside, a pairing fires before
either bound it permits, and a biconditional between a status and its timestamp fires before
the attribution that depends on it. The fix is per rule and small -- set the companion columns
the sibling demands -- but it is not derivable from the predicate under test, so it is written
down beside the case and the diagnostics above are what prove it was written correctly.

**A generated case block needs explicit begin and end markers.** Re-splicing a generator's
output into `isolation.sql` means choosing where the generated region ends, and choosing it by
reading the file deleted nineteen hand-written cases in one pass -- which nothing noticed,
because the suite's own count assertion was regenerated in the same step. The generator prints
`-- >>> GENERATED ... BEGIN` and `-- <<< ... END`, one splice script moves them, and it refuses
rather than guessing if either marker is missing or doubled.

**And a signal handler cannot catch SIGKILL, so an interrupted sweep has to be checked
for rather than trusted.** The web harness restores on SIGINT, SIGTERM and SIGHUP and was
still killed with a mutation in the tree -- `composeTree` returning `orphanLocations: []`,
which is a deliberate mutation and reads exactly like a developer's edit. The component
suite went red one test later for what looked like an unrelated reason. `git status` is the
check and it found it in seconds; the harness now also reports, on its next run, that an
anchor is missing *because the replacement text is present* rather than because the mutation
is stale, and prints the `git checkout` that puts it back. **After any interrupted sweep,
look at the diff before believing a failure.**

**A mutation harness must restore the tree on a signal, not only on an exception.** `finally`
does not run when the process is killed, and a web sweep stopped halfway left a deleted line in
a page for an hour -- the mutation whose replacement is the empty string, so searching the tree
for the mutated text could not find it. The only trace was the next run reporting "the anchor
appears 0 times", and in between a browser suite went green against a page missing the thing
one of its own tests is named after. Restore on SIGINT, SIGTERM and SIGHUP.

**A generated index mutation must filter `contype`, because a foreign key names the index it
reads.** `LEFT JOIN pg_constraint ON conindid = indexrelid` with no filter yields one row per
dependent key, each telling the harness to drop that foreign key from the *index's* table --
where it does not exist. Thirteen primary-key mutations were refused and recorded as not-run,
which is the harness manufacturing the gap it then reports. The same goes for widening a
numeric bound: the integer has to be the whole literal, or `'00:01:30'::interval` becomes
`1000000:01:30'::interval` and the statement never runs.


**The gate's "MOD-000 runner suite" step is minutes long and can hang, so a gate that has not
printed its verdict is not a gate that is failing.** Measured on this machine: the whole gate
finished in about eight minutes twice, and then that one step ran 49:49 at 9% CPU without
finishing, and alone under `timeout 300` it did not finish either. Its output is JSON about
`runner_alive` / `child_alive`, so it drives subprocesses and polls them -- which is the shape
that hangs when something it spawned does not exit. Two monitors armed on the verdict line
expired with no events, which reads exactly like a stuck watch rather than a stuck suite.

**What to do rather than skip the gate**: run its other eighteen steps individually -- each is
seconds and the loop is seven `tools/` commands plus eight `npm run` ones -- and say which ran.
That is honest where "I ran the gate" would not be, and it keeps the standard. And `pgrep -f`
plus `ps -o etime,%cpu` on the step's own process is what distinguishes slow from stuck in one
command; a log that has stopped growing says neither.

**`tools/local_ci.sh` and the browser suite cannot run at the same time.** The gate's last
step is `npm run build`, which writes `.next`, and the browser suite's `webServer` under `CI=1`
is `npm run start`, which *serves* `.next` -- so a gate started beside a running suite
overwrites the artefact the suite is being judged against, mid-run. Nothing errors in a way
that names the cause: the server keeps answering, from a mixture. Run one, then the other, and
if a long suite is in flight and the gate is wanted now, stop the gate rather than hoping the
build lands between tests.

**A suite that passes on a dev server and fails against the production build has not been
run.** `playwright.config.ts` says so in its own comment -- "a gate that only ever saw
`next dev` is a gate that has not seen the artefact" -- and this session proved it twice in
one afternoon. Two defects were invisible locally and red in CI:

  * **A colour-contrast failure in the dark theme**, on a translucent surface. The design's
    published contrast table measures every text token on three *opaque* grounds;
    `color.surface.selected` is `rgba(126,166,232,.16)` in dark, which is not a colour until
    it is composited over whatever it sits on, so a text token on a selected row is a pairing
    the table has nothing to say about. `text.tertiary` reads 3.74:1 there -- under AA, and
    invisible to anybody looking at a light screen. The remedy is both halves: secondary on a
    selected row, and a unit test that composites the overlay and checks every token against
    the result. **The published table is not the whole contrast surface, and an overlay is
    where it stops.**
  * **An assertion about the machine rather than about the app.**
    `document.fonts.check(<the whole declared family stack>)` also asks whether the browser
    has `system-ui` and `sans-serif`; a bare Linux runner answered no. The test's subject is
    that the face the body *uses* is loaded rather than merely named, which is the first
    family and nothing else.

**And a rate limit is a budget a test suite can spend.** MOD-011's `api.request` is 600 a
minute per identity and the browser suite spent it: three hundred tests in three minutes,
every one a page view with its gate batch and its reads. Six tests came back with the page
saying "something went wrong", in different places on every run -- the signature of a budget
rather than of a defect, and it was *only* reproducible against the production build, which
is faster than a dev server. Three things came out of it and all three were worth having:

  * **A 429 is not "something went wrong".** Every surface rendered `error.unexpected` for
    anything that was not a network failure, so a reader refused by the limiter was told the
    product had broken. It is the one refusal that is temporary and the reader's to act on.
  * **Batch the gate.** `/authz/checks` exists because the Command Center cost nineteen round
    trips; eight more pages were still asking one at a time.
  * **The budget is overridable in `local` and refused everywhere else.** Lowering the table's
    number to suit a test would be exactly the mistake that number's own comment names -- "a
    limit that trips during ordinary use is a limit somebody will raise to infinity rather
    than investigate" -- so the override is per process, bounded, and `config.load_settings`
    refuses it unless `VEYRO_ENV` is `local`.


**A local date and a UTC date are two frames, and a query that mixes them is wrong for a few
hours a day.** This file already records the fixture half of it -- "a test fixture that takes
its own `today` from the local clock disagrees with a service that takes it from UTC... CI
never saw it, because CI runs in UTC". The service half is worse, because CI *does* see it and
only sometimes: `visits_on` filtered on `(occurred_at AT TIME ZONE l.timezone)::date` and
compared it against `datetime.now(UTC).date()`, and `person_attendance` subtracted a UTC today
from a local last-entry date. Both agree for most of the day. In the hours after a club's local
date has turned over -- 23:17 UTC at a UTC+3 club -- the visit count read zero and the location
vanished from the response, and `days_since` answered **-1 days since** the member's last
visit. Both functions' own docstrings already stated the rule they broke.

**A single timezone makes the regression test flaky, which is what the bug was made of.** The
test that catches this uses two clubs: `Pacific/Kiritimati` (UTC+14, ahead of the UTC date
whenever the UTC hour is at least 10) and `Etc/GMT+12` (UTC-12, behind it whenever the hour is
under 12). The two windows cover the clock, so at every instant at least one club is on a
different date from UTC and the old code fails on it. Mutation-proven: restoring
`(now() AT TIME ZONE 'UTC')::date` fails four of them.


**A theory that explains a failure is not the cause of it.** A TestSprite journey failed three
times saying a report was missing for a session that held every permission. I read the page's
code, found a branch that *could* produce that symptom -- `gateAll` fails closed, so a dead
gate and a refusal reach the page identically -- fixed it, and wrote it up as the answer. It
failed again on the next run. The actual cause was in the test plan: its prose description
quoted the design's *Club Manager* scenario while its steps signed in as the owner, and the
agent followed the description. Reproducing it took one command -- sign in the way the failing
run signed in, and look -- and that was the step skipped. The fix was worth keeping and the
attribution was not. **Reproduce before diagnosing, and when a fix does not clear the failure,
the diagnosis is the first thing to doubt.**


**A vocabulary the backend stores is never a label, and the check that would catch it
cannot.** Four instances in one pass: `lifecycle_state` rendered `lead` on the members list's
filter chips and in every row; the membership plan rendered `recurring`, `monthly` and
`active`; the wallet rendered its four value kinds; a door visit rendered `nfc_card`. Each is
a column's value shown where a word belongs, and in the Arabic build each is Latin letters in
the middle of an Arabic line. **`MESSAGE_KEYS` is structurally blind to all of them**: it
compares the two catalogues against each other and cannot see a string that never became a
key. The durable answer is the one this file already records for the catalogue's own parity
-- a test per module asserting that every key *that module maps to* exists in both catalogues
-- plus the judgement that an unknown value falls through to its stored form rather than to
"other", because the screens that show these are the screens somebody filters and acts on.

**A shared helper inherits a contract from each call site it replaces.** Sweeping
twenty-five gate refusals onto one `gateMessage` put a page-level banner's sentence, full
stop and all, into the permissions matrix's status cells -- a dense grid whose cells are
labels. The same shape this file records for `DataGrid`'s caption and the design system's
Button touch target. Read what each site's own rendering does before replacing it, and
expect the shared version to need a second form.


**A backend started by hand is not the backend the browser suite is written against.**
`tests/e2e/serve.mjs` sets `VEYRO_API_REQUEST_BUDGET=20000` because MOD-011's `api.request`
budget is 600 a minute per identity and three hundred page views spend it — the override
exists precisely so a limiter that is correct in production does not decide which tests
pass. A uvicorn started from a shell without it looks identical, answers `/healthz` the
same, and then fails three consecutive specs in a burst at the limiter's window boundary:
the signature is a run of adjacent failures all timing out at the same duration, in
different places on every run. This repository already records the rule for a *test* that
spends a product budget; this is the same rule for the *harness*, and the tell is that the
failures move while the count stays about the same. Start the backend the way `serve.mjs`
does, or read its env block and match it.


**A suite that reads source files with `ast` is invalidated by an edit while it runs.**
`GateCoverageTests` and `test_id_validation` open `main.py` and parse it, so adding a route
mid-run changes what they assert against — the run is then testing a tree that did not exist
when it started, and a pass proves nothing about either version. The ordinary Python caching
intuition is wrong here: the module object is cached, the *file* is re-read. Finish the run,
or restart it after the edit; do not reason about which test the run has reached.

**Editing a spec file while the browser suite is running invalidates the run**, and the
failures it produces look like product defects. Playwright loads each spec as the worker
reaches it, so a file edited at minute two runs in its edited form at minute four while the
summary still counts the earlier files against the earlier tree — and the specs *after* the
edited one can fail for reasons no later run reproduces. Three failures chased that way in
one session each passed in isolation and in a clean run. This is the `ast`-suite rule one
layer out: **do not touch the tree while a suite is reading it**, and when a failure will
not reproduce, suspect the run before the product.


**A web server started before the change does not serve the change, and the suite will not
say so.** `playwright.config.ts` sets `reuseExistingServer: !process.env.CI`, which is the
right default for a developer's loop and wrong for the run that judges a new screen: a
`next-server` started two hours earlier answers every request from the build it was started
with. Nineteen of twenty-five staff tests failed as 30-second timeouts waiting for content
that was in the tree and not in the process — and the six that *passed* were the ones
asserting an **absence** (`toHaveCount(0)`), which is the worst possible split, because a
reader skimming the summary sees a product that renders nothing while correctly refusing to
draw the buttons it should not. This is the backend half's rule — "a backend started by hand
is not the backend the browser suite is written against" — one layer over, and the tell is the
same: adjacent failures all timing out at the same duration. **Judge a new surface with
`CI=1`** — and build first, because `CI=1` is only half of it.

**`npm run start` serves whatever `.next` is already on disk, so `CI=1` alone does not build
the change.** The config's `webServer` command is `npm run start` under CI and the CI workflow
runs `npm run build` as its own step; a local run that skips the build serves the previous
artefact, and a brand-new *route* then answers 404 while every existing page is fine. The
whole of a new spec file fails at once, which reads as a destroyed session or a broken
fixture and is neither. **The tells, and they are worth knowing together**: the file before it
is green, most of its tests fail at the `expect` timeout while one or two fail in a few
hundred milliseconds (a `toBe` against `undefined` needs no wait), and the surface's own data
is correct when read straight from the database. One `curl` of the page with the saved session
cookie settles it in a second — `http=404`.

**A fixture block spliced on an anchor lands in whatever function holds the anchor.** A
seed-staff block anchored on a comment inside `seedAccess` compiled, typechecked and then
threw `ReferenceError: ownerToken is not defined` at provision time — the enclosing function
calls that token `token`, because it *is* the stepped-up owner session. Harmless here because
it failed loudly and immediately; worth stating because the same splice landing on a name that
happens to exist in both scopes would have seeded the fixture with the wrong credential and
proved a permission the fixture could not obtain honestly.


**A layout whose width is a count will cross the phone breakpoint at somebody's tenant, and
the sweep finds it the day a fixture crosses it.** `/permissions` draws one matrix column per
role; adding a single role to the e2e fixture overflowed it by 125px, and the two causes are
both worth knowing because each looked already handled. The scroll wrapper had
`overflow-x: auto` and could not scroll, because `inline-size: 100%` plus the global
`table { display: block; max-width: 100% }` phone rule pinned the table box to the container
and let its columns overflow *the box* — so the wrapper saw a child its own width with nothing
to scroll. And once the table was free to grow, the wrapper was a genuine scroll container
(343 over 535) whose overflow **still** counted toward
`document.documentElement.scrollWidth`; `contain: layout` is the boundary that stops that, and
it is the right one of the three — `paint` clips the focus ring and `inline-size` does nothing.

Both were found by hiding one element at a time and re-measuring, which took three minutes and
replaced a chain of plausible theories (a sticky `thead`, a fixed rail, a flex item's
`min-width: auto`) each of which explained the symptom and none of which was the cause. **When
a layout number is wrong, bisect the DOM before reasoning about the engine** — it is the same
rule as "reproduce before diagnosing", applied to CSS.


**A component's docstring is a claim about the rendered page, and the stylesheet can falsify
it silently.** `DataGrid` has said from the start that "a droppable value is in the DOM twice
and visible once -- the stylesheet shows exactly one at any width", and below 600px it showed
both: `.ds-col-p2 { display: none }` is specificity (0,1,0) and the `.ds-grid-table td
{ display: block }` rule that turns the table into a list is (0,1,1) and comes after it, so
every priority-2 and priority-3 cell rendered beside the secondary fragment of the same value.
Twenty-one duplicated values on the members list, twenty-one on the payments ledger, on every
grid in the app, for as long as the collapse has existed.

**Nothing in four layers could see it.** An assertion about text matches either copy; a
component test renders without the media query; the phone sweep measures horizontal scroll,
and a duplicated value does not cause any. It was found by taking a screenshot at 375px and
reading it -- the same way the schedule board's wrong timezone was found, and the same lesson:
the stronger assertion costs the same to write. `phone.spec.ts` now asserts, on three grids,
that no cell carrying a droppable priority is still `display`-ed, which is the property the
docstring claims rather than a restatement of the rule that implements it.


**A masked value is not a masked row, and rendering the marker *instead of* the control makes
the screen a dead end.** The members list and the staff list both drew `<Withheld>` in place
of the link to the record, so on an ordinary sign-in -- where every identity field is masked,
which is the front desk's own credential -- not one row on either list could be opened. The
record behind the row is the page that explains the withholding and offers the step-up, so the
one way out of the mask was behind the mask.

**Found by an independent tester, for the second time against the same cell**: the first run
clicked the marker looking for a way through and found the members list had no step-up offer;
this one was told to open a record, found the cell unclickable, went looking for another way
and was blocked by a step-up it had no recovery code for. No test written here could see
either, because both assert that the marker is present -- which it was. The question to ask of
any masked cell is not "is the value hidden" but "what could the reader still do with this
row, and is it still possible".


**The browser sweep earns its place the same way the SQL one does, and it found all three
shapes in one run.** Six mutations against two new decision modules: four caught, one that
**never applied** (two spaces of indentation in the anchor rather than four, so a protection
the list claimed to cover had no evidence and the harness said so instead of counting it), and
one **uncaught and correct to be** — the guard it removed was subsumed by the line below it,
because a caller who may not read logins passes no reading either. That one was deleted rather
than tested harder, and its parameter with it: a parameter a function cannot act on is a claim
its signature makes and does not keep.

The last gap was **"a weakening is caught only if it admits the row"**, in a fixture rather
than in a SQL case. Dropping `|| seen.status === "active"` from the access rule changed
nothing, because the seeded leaver *has* a live session and the surviving half still answers
for them. The row that catches it is the leaver with **no** session whose account still works
— which is also the commonest real shape, and the fixture did not have one. Same question as
for a CHECK: not "does this row violate the rule" but "which weakening would admit this row".


**A plural message's unreachable CLDR form still has to carry every placeholder it is passed,
and deleting it fights the sweep that exists for it.** ADM-RPT-04's "there is another peak at
{hours}" sentence is rendered only where there *is* another peak hour, so Arabic's `zero`
category is unreachable by construction -- which is MOD-020's "a declared state nothing
writes" arriving in a message catalogue. The first fix deleted the form, and the plural parity
sweep caught it within the minute: a missing category falls back to `other`, which renders a
plural where Arabic wants a dual, so all six have to exist. And the honest-reading zero form,
"no other hour", is the one form `fill` refuses outright, because it cannot carry the `{hours}`
the call site passes. So the form exists, repeats `other`, and the test that exercises every
category says in a comment why zero is in the list and what it proves. **The general shape: a
message with a required non-`count` placeholder has to carry it in every form, including the
ones the page cannot reach.**

**Mutate the binding, not the SQL, when the control is a value flowing into a statement.**
Proving that an hourly histogram converts each instant in the *club's* zone means breaking the
conversion -- and replacing `AT TIME ZONE %s` with `AT TIME ZONE 'UTC'` in the query text
removes three placeholders, so the statement no longer matches its parameter tuple and the
mutation fails to run. A harness that reads that as a catch is recording a gap it created, and
one that reads it as a gap is reporting noise; this file already records both halves for
generated index and numeric-bound mutations. The clean mutation is one token at the variable
binding (`str(site[1])` to `"UTC"`), which keeps the statement well-formed and changes exactly
the fact under test.

**Resolve a report's window once and pass explicit dates.** The first version of
`visits_by_hour` computed its bounds in SQL twice, once in the hourly query and once in the
per-zone one -- MOD-018's "one module, two definitions of the same balance" waiting for the day
somebody edits one of them. The bounds come back from a single read now and the other two
queries take dates. A window that two queries derive independently is a chart whose total can
disagree with its own breakdown, which is the figure a reader checks the breakdown against.

**A hard-coded count of what is missing goes stale the hour something is built.** The reports
index's component test asserted `UNBUILT.length === 4`; building the attendance report made it
three and the test red for the right reason and the wrong shape. The property is that every one
of the canvas's six reports is *either* offered *or* explained -- `REPORTS.length +
UNBUILT.length === 6` -- which cannot go stale in either direction and fails only when a built
report is left in the "cannot report" list. That is the Member 360's "not built in this
repository" defect in an assertion rather than on a screen, and the per-item-list hazard this
file keeps finding one layer further in.


**Stopping a sweep through the agent harness does not reach the sweep's signal handlers, so
the diff check after one is mandatory rather than advisory.** `mutate.mjs` restores on SIGINT,
SIGTERM and SIGHUP and nothing can catch a SIGKILL -- which this file already records, from the
hour `composeTree` sat in the tree returning `orphanLocations: []`. It happened again, in the
same file and with the same mutation, when a sweep was stopped to apply an unrelated change:
`git status` showed `web/src/lib/organization.ts` modified among seventeen files this session
had genuinely edited, and one line of it was the mutation. **The tell is a file in the diff
that this session never touched**, and the mutation whose replacement is the empty string
leaves nothing to search the tree for. So: after any interrupted sweep, read the diff and
restore anything you did not write, before believing a result or a failure.

**And a sweep whose runner is `spawnSync` prints nothing until it finishes.** Node buffers
stdout to a pipe and flushes on an event-loop turn, and a loop of `spawnSync` calls never
yields one -- so a 116-mutation browser sweep looks hung for an hour and then dumps every line
at once. That is not a hang and not a reason to kill it; `ps` for the child process it is
currently running is what tells you it is alive. Worth knowing before stopping one, since
stopping one is what leaves a mutation behind.


**A mutation goes stale when the code around it improves, and the sweep is the only thing that
notices.** Running the browser sweep's two phone mutations while building an unrelated screen
returned **0/2 caught**. Nothing was broken: both named CSS rules that are still correct and
had simply stopped being provable by the assertion they were pointed at, because two earlier
fixes had made them redundant.

`table { display: block }` at phone width is what makes `overflow-x` apply to a table, and
breaking it used to overflow seven surfaces. It overflows none of them now -- every table in
the app is either a `DataGrid` whose columns drop by priority until it fits or a hand-rolled
one at `width: 100%` -- and a grid gets `display: block` from the 599px collapse rule anyway,
so the generic rule is reachable only on the four hand-rolled tables, **whose two tabs were
not in the phone sweep at all**. `.facts dd { overflow-wrap: anywhere }` was unprovable for
that reason plus one more: `contain: layout` on the matrix's scroll wrapper now stops an
overflowing descendant reaching the root, so a value too wide for its track is contained
before the document can see it.

Three things came out of fixing it, and they generalise past CSS:

  * **Measure what the mutation changes, do not reason about it.** Applying each one by hand
    and running the *whole* sideways-scroll sweep -- 36 surfaces, not the one the mutation
    named -- is what established that no page depended on either rule. The same probe found
    that `contain: layout` *is* load-bearing, and by exactly the 125px this file already
    records.
  * **Assert the property, not a consequence that has stopped following from it.** The
    collapse is directly measurable with `getComputedStyle`, so it is measured: a grid's table
    and cells compute `block` (or `none`, for a dropped column -- that is the other half of
    the collapse), and the matrix computes `table`, which is the exception the design makes
    for itself. Four mutations against those assertions are caught where two against the
    document's scroll width were not.
  * **A document-level assertion cannot see a contained overflow, and containment is the
    design's own answer.** "The bar scrolls inside itself rather than widening the page" is
    the intent, so `scrollWidth - clientWidth` on the root correctly reports zero while a
    table is far too wide. That assertion is still the right one for the defect it was written
    for; it is the wrong one for anything a scroll wrapper absorbs.


**Revoking a grant can strengthen a privacy declaration, and the registry notices both
ways.** MOD-009's reachability sweep is usually described as catching a *new* column nobody
declared, and it did that here for all four of `0017`'s. The other direction is the one worth
knowing: `sch_availability_windows.reason` was declared `write_once`, which the registry
requires a grant to stand behind — and revoking the unused `UPDATE (starts_at, ends_at,
reason)` made that declaration false, because the database now refuses the write outright.
`test_a_write_once_declaration_really_has_a_grant_behind_it` failed, and the repair was to
*strengthen* the declaration to `unreachable`. The registry is a statement about what the
privileges permit, so it moves whenever they do, in either direction. Related: a column that
is `unreachable` **and** carries a grant is only honest when the reason names the trigger that
makes it final — `sec_legal_holds.released_by`'s shape, and the test checks for the word.

**A foreign key to a table the role cannot read answers at the worst moment.**
`iam.auth_events.tenant_id` references the tenant registry, and `veyro_iam_app` holds no
USAGE on `plt01_platform` -- deliberately, that is the plane separation. So a login against
a tenant that does not exist hid every identity behind RLS, took the unknown-identifier
branch, and had its failure event refused by that key: a `ForeignKeyViolation` and a stack
trace out of an *unauthenticated* route, once per attempt. The service could not have
checked first; the database is the only thing in reach that knows. A `with
conn.transaction()` savepoint around the write turns the answer into a refusal without
poisoning the caller's transaction, and the refusal has to stay byte-identical to every
other failed login or it becomes an oracle about which tenants exist. **The general shape:
where a role is deliberately blind to a referenced table, every write that crosses that
reference is a 500 waiting for input the caller controls.**

**Completing a step-up revokes the session every other spec adopts, so one saved session
can be stepped up exactly once per run.** MOD-007 does not elevate a session in place: it
revokes the one it came from with `revoke_reason = 'stepped_up'` and opens a new one,
"because a session's lifetime follows what it can do and a level-2 window is twelve hours
rather than a fortnight". The new cookie lives in that browser context; the saved state file
still holds the old one. So the *next* test to adopt it is signed out, and so is every spec
that runs after that file. `step-up.spec.ts` never hit this because it sorts last; the first
spec to need a stepped-up session sorted first, and four of that spec's tests failed the
moment it existed -- as refusals, which read like a product defect rather than a harness one.
A spec that needs level 2 signs in for itself rather than adopting the shared cookie: a few
logins against MOD-011's thirty a minute, and nothing shared is spent.

**And "a form behind a financial permission cannot be built" was too strong.** Every absent
write form in this app was justified with "a button that answered 403 is worse than its
absence", which is true of a button that just fails and says nothing about one that offers
the step-up first -- which this app already does for *reads*, on a masked field. The honest
cost is one recovery code per twelve-hour window rather than one per act, and that is a
sentence a screen can say. The same shape as MOD-019's gap note claiming every scheduling
write was stepped-up when the one the design put a button on was routine: **a blanket reason
covering a dozen screens is worth re-deriving for each of them.**

**Run the lint after the last edit, not after the last edit you were thinking about.**
`ruff`, `mypy` and the suites are separate commands in this project precisely "so one failure
does not hide the rest", and that cuts both ways: a green run proves the tree as it was when
it ran. A fix to a *test* file made after the lint passed shipped a one-line import-order
error to CI, which the backend suite could not see and the local judgement never re-ran. The
cheap discipline is that the last thing done before a commit is the whole gate, in order, on
the tree being committed -- not whichever check the last change seemed to belong to.

**The frame a date is bucketed in is neither the runner's nor UTC -- it is the subject's,
and a test asserting a date takes it from there.** This file already records the
local-clock-versus-UTC flake and notes that CI never saw it "because CI runs in UTC". MOD-022
has a sharper version: `visits_on` buckets each event in *the club's own* timezone, so a
member training at two clubs has each visit on the date that club would put on it. Two tests
took `today` from `datetime.now(UTC).date()` and asserted against it, and every expected day
was one earlier than the club's for the three hours after 21:00 UTC. **CI would have failed
too** -- the frame that matters is Asia/Amman whoever runs the suite, so this is a
*time-of-day* flake rather than a machine-timezone one, and a green CI run proves nothing
about it. The same file already carries a test that knows this, written when CI found the
bug in the service; it sweeps several zones, and the two that broke used the default club and
a different read. Ask of any date assertion: *in whose zone is this figure computed*, and
take `today` from that zone.

**A currency with two exponents will be conflated by the first screen that takes a typed
amount.** JOD is *stored* in fils and *shown* with two decimals, and the conventions module
keeps two tables and says why -- "storage precision is what makes a proration exact and a
journal balance; display precision is what a receipt and a screen agree on". Every figure
rendered so far goes out through one formatter, so the distinction stayed in that module; the
first screen to read a number *in* is a cash count, where reading 135.50 as 13550 minor units
rather than 135500 posts the difference to suspense as a 121.95 shortfall -- on the one screen
whose whole subject is the difference between two numbers. The parse splits the string rather
than multiplying a float, for the ordinary reason, and scales between the two tables. The test
that matters is not "135.50 parses" but "135.50 minus the server's own expected figure is
2.50".

**A client component that imports a module reaching `next/headers` breaks the whole app's
build, and this is the second time.** The account page records the first, where putting its
decisions beside its fetchers made the *login* page answer 500. The cash screen's parse is
used in a client component and its read is not, so `cash.ts` holds the decisions and
`cash-reads.ts` the fetch -- the same `domain`/`service` split the backend makes. **The tell
is a build error naming a chain of `[Client Component Browser]` imports**, which does not
mention `next/headers` at all.

**A test that drives a one-way write provisions the thing it will consume, not the thing it
needs to exist.** Closing a cash drawer has no reopen -- correctly, since a till somebody
signed off and then re-opened is a till nobody can account for -- so a spec that closed the
fixture's own drawer passes once and fails ever after. The split that works: the *account* is
seeded by the fixture, because creating one is a stepped-up financial write and a browser
session is AAL 1; the *session* is opened by the spec on each run, because opening one is
routine. And a 409 from the one-open-per-drawer index is treated as a previous run's
interrupted drawer for this suite to finish, rather than as somebody else's failure.

**A gap note outlives its gap, and it goes stale in exactly one direction.** The schedule
board carried "nothing in this build reads a resource's availability" from the day it was
written; `/rota` is that read, and the sentence survived the change that made it false --
beside the chip that links to the view it denies. TestSprite, told to add a rota exception,
read it, concluded the capability was absent and never opened the page. That is the Member
360's "not built in this repository" defect one screen over, and it is the shape a repository
that documents its own gaps carefully will keep producing: **a gap list is a claim about the
product, so closing a gap means deleting its note in the same change**, and the assertion
worth leaving behind is the *absence* of the old sentence rather than the presence of the new
one.

**A write form needs its remedy before it needs its button, and "insert-only" is where to
look.** ADM-SCH-04's canvas draws "Add an exception" and the permission behind it is
deliberately routine -- `scheduling.availability.write` is `configuration` with no financial
class, because "a rota is edited by the people who run the floor". The table was
`GRANT SELECT, INSERT` and nothing else, so the button would have written a **permanent,
uncorrectable** row: a day off on the wrong date, a shift typed as 06:00 instead of 16:00, an
absence against the wrong coach, each with no remedy anywhere in the product. That is
MOD-013's "an irreversible act must not be declarable on a routine permission" arriving from
the other side -- not a control that permits too much, but a *remedy* that does not exist.
Insert-only is right for evidence and wrong for an operational statement somebody retypes, and
the question to ask before building any form is "what undoes this, and does it exist".

The answer is a withdrawal rather than a delete, for the reason the evidence tables already
give: "was this coach marked off on the fourteenth, and who said so" is asked precisely when
somebody was turned away, and a deleted row answers nothing.

**And a grant no service writes is the same shape as a column no service reads.** `0013`
granted `UPDATE (starts_at, ends_at, reason)` on that table to both runtime roles, with a
comment explaining that a rota is edited -- and nothing in the build ever wrote them. An
unattributed retime of the three values the table exists to state, with no column anywhere to
record that they moved, available to any writer for as long as the grant stood. MOD-016 found
exactly this in `cat_prices.effective_to` and took it out of the grant; this is the second
instance. **Grep the writers of every column in an UPDATE grant**: one with none is either a
gap to disclose or an unattributed edit path, and it is usually the second.

**A design-system component is correct in isolation and untested until a page renders it.**
`WeekGrid` has existed since ADM-SCH-01 and had no live caller, so its scroll wrapper had
`overflow-x: auto` and no containment boundary -- and the first page to draw a week scrolled
the whole document sideways by 95px at phone width, hiding its own right-hand edge. That is
verbatim the `/permissions` finding this file already records, in a component whose own
stylesheet comment explains why the table is 64rem wide. **And the property needs asserting
from both sides**, because the two wrong states are mutually invisible: with the boundary and
a table pinned to `inline-size: 100%` the document reports zero overflow and the region has
nothing to scroll, so the columns are clipped and unreachable while every assertion about text
still passes. One test says the page does not scroll; the other says the region does. A
mutation against either passes the other, which is how the first attempt at the second
mutation came back as a gap -- its grep named the wrong one of the pair.

**And "the region scrolls" is not that second property.** The first version asserted
`scrollWidth > clientWidth` on the wrapper, which reads like "the columns are reachable" and
is not: a table pinned to `inline-size: 100%` leaves its *cells* overflowing the box they sit
in, so the wrapper still reported 117px of scrollable width with every column squeezed and the
design's 64rem gone. The mutation that removes `min-inline-size` came back **uncaught** against
it. The subject is the table *box* -- `tableWidth > wrapper.clientWidth`, the table allowed to
grow, which is what `.ds-matrix-scroll`'s own comment already said one screen over. Found by
applying the mutation by hand and reading the three numbers, not by reasoning about the engine.

**A test can name the right property and point at the wrong row, and then the branch it exists
for has never rendered.** `/rota` has an "unconstrained" branch for a resource with no rota --
no grid, no open-hours figure -- and its e2e test was pointed at the fixture's stand-in, which
**has** a rota: a substitution is refused unless the replacement's week covers the class, so
the fixture had to give it one. The test therefore asserted "no rota binds" against a page
showing 112 open hours across a full grid, and the claim it was written to prove had never been
rendered at all. This file already records that a surface branch no fixture can reach is
vacuity one layer up, in four modules; the new part is that the fixture *did* carry both kinds
of resource and the test chose the wrong one, which no amount of re-reading the test would
show. **The fixture now seeds a third staff resource with nothing written against it**, which
is also the realistic shape: on the day a gym opens nobody has a rota.

**This app has one number-rendering path and a figure must be an integer in its unit.**
`formatInteger` throws `ConventionError("integer required")` for a fraction, deliberately:
`tests/unit/conventions-parity.test.mjs` spawns Python and compares the JavaScript conventions
against the backend's character for character, because a receipt is rendered by the backend and
two implementations pass their own tests forever while drifting apart. A new screen's hours
figure returned tenths, so the page answered **500 from inside `fill`** on every request -- in
the one place the figure is rendered, with the route and the data both correct. The fix is the
unit, not a second formatter: round to the whole hour and say on the screen that it is rounded,
because across a week that is immaterial and below an hour it is not. The invariant is pinned
for every input rather than for three somebody picked, since the throw is the contract.

**A connected client makes `verify_db.sh` skip the whole isolation proof, and the only tell is
its exit code.** The script drops and rebuilds the database, so PostgreSQL refuses while
anything else holds a session: `ERROR: database "veyro" is being accessed by other users /
DETAIL: There are 12 other sessions using the database`, and the script exits 3 having run no
check at all. The output is two lines rather than 111 passes, which is easy to skim past when
it is one of several commands in a chain and the next one is a 2,400-test suite that scrolls
for twelve minutes. **So read the exit code, not the absence of a failure** — the proof that
did not run looks nothing like the proof that passed, but it also looks nothing like a red.

The ordinary cause is a `uvicorn` left over from seeding the browser fixture, or a backend
suite still running: both hold pools. `pg_stat_activity` named by `datname` is what says which.
And `ps aux | grep -c "[u]vicorn"` is not the check — a pipeline counts its own `grep`, which
is the same shape as the `pgrep` loop that matches its own shell.


**A component that renders an anchor inherits the browser's defaults, and a stylesheet that
sets only the colour leaves the rest.** `Button` with an `href` is a real `<a>`; the global
`a` rule in this app sets `color` and nothing else, and only the `link` variant declared a
`text-decoration` of its own -- so **every non-link button with an `href` has rendered
underlined since the component existed**, which is the thing the design source forbids in as
many words: "a link styled as a button, and the inverse too". Nothing could see it. An
assertion about the accessible name matches either way; a component test renders without the
app's stylesheet; the phone sweep measures overflow; and axe has no rule about it. It was
found by photographing the running page beside its canvas and looking at the two buttons. The
general shape: **when a component swaps its element type on a prop, the new element's user-agent
styles are part of what that prop changed**, and the base style has to neutralise them rather
than relying on each variant to.

**A control can be marked without carrying a message, and conflating the two renders the
sentence twice.** The field shell's own rule is that "the message slot holds exactly one
message", and a screen whose explanation is an adjacent panel -- the canvas's shape for a
duplicate interruption -- has to mark the control *and* put the sentence somewhere else, or
the reader gets it under the field and again in the panel. `marked` plus `describedBy` is the
separation; a mark with neither would be worse than both, which is why the second is required
alongside the first.

**"Validate on blur, never on keystroke" applies to a disabled submit, not only to a message.**
A button that un-disables as the fields become acceptable is keystroke validation wearing a
different control, and it leaves a reader with a dead button and no sentence saying which
field is wrong. The submit stays reachable and the server action returns which field was
missing -- which is the "re-validate on submit" half of the same rule. A *hold* that is not
about the field's own validity, such as an interruption a person has to answer, is a different
thing and does belong on the button.

**Two copies of one comparison, found by the sweep rather than by reading.** A screen computed
"a match about this value that nobody has acknowledged" inline for its banner while the
decision module computed the same thing for its button; breaking one left the other intact and
the suite stayed green, so the mutation that named the protection came back uncaught. That is
this repository's "one module, two definitions of the same balance" in a surface, and the
remedy is the same one: one exported function that both the render and the decision read. **The
tell in a sweep is a mutation whose test asserts the rendered half while the mutation edits the
other half** -- so when a browser mutation comes back green, check that the line it broke is
the line the page actually reads.

**The browser mutation sweep needs the dev server, and judging the suite needs the built one.**
`next start` serves whatever `.next` is on disk, so a sweep that mutates a source file and runs
Playwright against a production server tests the *unmutated* bundle and reports every mutation
as a gap -- three came back uncaught that way before the cause was obvious. The dev server
compiles on demand, which is what makes the mutation visible. The reverse holds for the real
run: a suite that only ever saw `next dev` has not seen the artefact, which is already recorded
above. Two servers, two purposes, and using the wrong one is silent in both directions.

**Appending to a list in a file whose runner follows it truncates the runner.** A splice that
anchored on the file's last `];` deleted every line after the mutation array -- the loop, the
report and the exit code -- and the sweep then exited 0 with no output, which reads exactly
like "nothing to do". The tell was an empty log from a command that always prints; `wc -l`
before and after would have caught it in a second. Anchor on the *array's* end, not the file's.

**And the quieter version of that is landing in a sibling array.** The same splice, run again
against a file whose last `];` had since become `const notRun = [];`, put nine mutations into
the harness's own *diagnostics* list rather than into `MUTATIONS`: the file parsed, the runner
ran, the sweep reported `0/0 mutations caught` and exited 1 with nine lines under `NOT RUN`
describing mutations it had never attempted. Truncation at least produces an empty log;
this produces a plausible report about work that did not happen, which is the false green
this whole discipline is against, wearing the harness's own colours. The fix is the same
anchor and the check is `node -e` on the file counting `id:` keys **inside** the array the
splice claims to have edited -- so it is the array that is counted, not the file.

**And never `import` the sweep module to inspect it, which is the third time this session.**
`mutate.mjs` is a script: the mutation loop is top-level code, so `import("./tests/e2e/mutate.mjs")`
*runs it*, and a `2>/dev/null >/dev/null &` wrapper hides that completely while it edits
source files in the background. One of those left a mutation in a page and another in a
library, each found only by reading the diff **hunks**. Read it with `cat`, parse it with a
regex, count it with `node -e` on a string -- anything but `import`.

**And `tail -F` on a log a previous run wrote replays that run's tally as a current event.**
A watcher armed on two log paths, one of which did not exist yet and one of which was eleven
hours old from the morning's run, reported `521 passed (4.4m)` within seconds of a suite that
had been going for under a minute -- a complete, plausible, *wrong* result for the run in
hand, and the sort that would have been written into a commit message. The tells were that
the number did not match the test count the change should produce and that the live log had
fifty lines in it. The fix is a per-run filename, or truncating before watching; the habit is
to check the log's mtime before believing its last line, which `stat -f "%Sm"` answers in one
call. **A stale artefact read as current is the same failure as a stale fixture or a server
started before the change** -- this file records both -- and a watcher makes it quieter,
because the number arrives as a notification rather than as something you went and looked at.

**An assertion keyed on words a *correct* sentence also contains contradicts itself.** A test
for "this reader is offered no step-up" used `[title*="stronger sign-in"]` and expected zero --
and the sentence it required to be present reads "Reading one needs a permission rather than a
stronger sign-in", so the marker the test exists to assert was what made it fail. The property
is the *offer*, not the vocabulary: the step-up sentence's own distinctive clause, and the
absence of a link. That is the positional-locator trap in prose, and the tell is a test that
fails against a page a human would call correct -- so read the sentence the page renders before
rewriting the code it tests.

**An unscoped `getByText` on a phrase is a test coupled to that phrase being unique in the
document.** The account page asserted "the highest assurance this product has" at page level;
adding a sentence elsewhere on the same page about the same level made it match twice, and
Playwright's strict mode reported it as a failure *of the level assertion* -- a defect in the
thing under test, which it was not. Two lessons and both are cheap: scope the assertion to the
block whose claim it is, and treat the duplicate phrase as the finding, because the same
sentence twice on one page is the repetition the field shell's message-slot rule already bans
in the small. It is the positional-cell and attribute-order trap again, with text as the
coincidence.

**And a `section` filtered by a word is coupled to that word appearing in one section**, which
is the same trap one container out and the one that got past a suite whose own comment
predicted it. `operations.spec.ts` carries three notes saying to scope by the heading because
"two things answer the same locator"; the objectives test still used
`filter({ hasText: "Objectives" })`, and wiring a worker job called
`observability.evaluate_objectives` put that word in the *Scheduled jobs* section -- which
sorts first, so a test about the objectives block began asserting against the jobs block and
failed on a sentence rendered correctly a few hundred pixels below. **A job name, a row label
and a gap note are all things that put a section's word into a sibling**, so the heading is
the only stable handle. Scope by `filter({ has: getByRole("heading", { name }) })` and treat a
`hasText` section filter as a defect waiting for the next feature.

**And run the whole suite, not the test you wrote.** Both of those failures were mine and both
were found by CI rather than locally, because I ran the one grep'd test and its mutation and
pushed. The grep'd test passed for a reason that made it worse than useless: the new job had
recorded no run against the local fixture yet, so its row -- the row carrying the word that
broke the locator -- was not rendered at all. **A single-test run against a fixture that has
not seen the change is the weakest evidence available**, and it reads exactly like the
strongest.

**And a backend started before a *registry* change serves the old set, which looks like a
product defect in the new code.** This file records the route version of it -- a 404 the
surface renders as a permission problem -- and the registry version is quieter: `/ops/worker`
iterates `worker_registry.JOBS`, so a uvicorn started before a job was wired returns six where
seven are declared, and the board's own count test fails *against the correct expectation*.
**The tell is the direction**: CI saw seven and the local run saw six, which is a stale process
rather than a wrong test, because CI starts the backend from the commit. When a count differs
between CI and local in the direction of the change you just made, restart the process before
touching the assertion.

**A gap note can be a true sentence about one half of a feature, standing in front of the
other half.** MOD-013's digest bullet said closing a window needed the digest template format
the sources do not state -- which is true of *rendering a batch into a message*, the `sent`
state, and has nothing to do with marking an elapsed window `closed`. Behind it sat a declared
state nothing wrote, a `state` filter whose value could never be returned, and an
`UPDATE (state, closed_at)` grant no service used: three of this build's own recurring findings
in one row, invisible because the sentence covering them was accurate. MOD-011's objective
evaluation was the same shape with a weaker disguise -- "a judgement the registry would have to
invent: which objective is due", when every objective carries its own window. **So when a gap
note names a blocker, check that the blocker is in the way of the thing the note is about**: a
note that is right about *why something else* is missing reads exactly like a note that is
right about this.

**And the third reading of that question found no work at all, which is the cheapest outcome
and the easiest to miss.** MOD-018's gap bullet listed wallet expiry among its undriven sweeps
and said lapsed promotional value "is still spendable until somebody calls the expiry".
`wallet.balances` excludes it at read time on purpose -- its docstring argues that a balance
counting lapsed value until a worker removed it would be a balance a member could spend after
it expired -- and `plan_debit` goes through `balances`, so no debit reaches it.
`expiring_before`'s own docstring says it is "for telling a member, not for sweeping", and
there is no expire-the-value command for a job to call. **A gap note that invents a job costs
more than one that omits a job**: an omission is found by anybody looking for work, and an
invention is found only by somebody trying to do it -- and the shape of trying is to wire a
sweep against a function that says it is not for sweeping, to fix a defect the module had
already decided not to have. So the three questions to ask of a gap note are whether the
blocker it names is in the way, whether the consequence it claims is still true, and whether
the work it implies exists.

**A fourth reading of the same question found a defect the note had buried, which is the
opposite failure and the worst of the four.** MOD-017's bullet said nothing applies a
cancellation when its notice runs out, and named the consequence as a stale status cache --
true, and the mild half. The consequential half was unnamed: the *grants* were never revoked
either, so a member who cancelled with notice kept drawing entitlements after their membership
ended. That is `_revoke_grants`' own "access the member is no longer paying for" in the path
that survived the review which found it, and it survived because **the door was right**: the
access evaluator reads the membership's dates rather than its cached status and says so in a
comment, so every obvious probe of the defect comes back correct. `entitlements.usable` sees
only the grant. **So a gap note naming the consequence a reader can see is the one to distrust
most**: the cache is what somebody querying the table notices, and the grant is what a member
spends.


**A class name that styles nothing is invisible to every layer that is not a screenshot.**
`ds-card` appeared in `globals.css` exactly once, inside a `prefers-reduced-motion` block,
and nowhere as a definition -- so two screens asked for a card and rendered a loose stack of
text. The text is identical, the structure is identical, axe has nothing to say, and the
phone sweep measures overflow a missing border does not cause. A sweep for `ds-` classes the
stylesheet does not define found three more: a spinner with no animation, the field shell's
contextual-action slot, and the data grid's own wrapper. **A design system's prefix is a
promise that the component exists**, so an undefined one is a component the app thinks it has.

**A density rule scoped to `:root` can only ever be set on `<html>`.** The generated token
file learned this once -- a screen setting its own density on a wrapper read as the default
and rendered at the wrong row height, found by measuring -- and the 44px touch floor was left
behind in `globals.css`, which matters more: on Touch and Spacious that height is "the minimum
target, not a style". **And the browser test that looks like its proof is not.** The control
it measures is `size="lg"`, which `BUTTON_HEIGHT` makes 44px on its own, so the measurement
stays green whichever selector is live -- the mutation sweep said so by coming back uncaught,
which was the right answer and not a gap. The property is structural and the assertion that
proves it is structural.

**A mutation sweep with no runner for a test layer reports that layer's protections as gaps.**
`mutate.mjs` had `vitest` and `playwright` and nothing for `tests/unit/`, which runs on Node's
own test runner -- so a mutation pointed at one of its eighty-eight assertions came back
UNCAUGHT, because `vitest` does not collect those files and reported no failure rather than no
test.

**And neither of those runners can be asked whether its name pattern matched.** Node's runs
every file, filters every test out of each and reports `pass 9, fail 0`; vitest reports
`Tests 408 skipped` and exits 0. Both are indistinguishable from a real pass by the exit code
and from a real gap by the output, so a stale grep comes back UNCAUGHT -- which reads as a
protection with no evidence and is in fact a mutation that was never judged. **This is not
hypothetical**: renaming a test to make its case exercise the branch it names left its
mutation's grep behind, and two rounds were spent reading the branch before the cause was
obvious. The guard is the same static check the mutation text already gets -- the pattern has
to occur in the tests that runner reads -- and it was proved by pointing one at a name that
does not exist and watching it report NOT RUN. Playwright needs none: it says "No tests found"
and exits non-zero.

**A browser test that spends a one-way product state is green on a fresh fixture and red on
the second run**, which this file already records three times. FD-06's check-in is one-way by
design -- there is no un-check-in -- and the natural fix, having the test provision its own
member, is refused: `people.person.write` is financial class and a browser session at AAL 1
cannot reach it. So the fixture seeds ten members on that class and the suite spends one a
run, and every assertion is about *a* row the module would still accept rather than a named
one. **The rule generalises past budgets: when a test consumes state and cannot create it,
the fixture owes it enough for the number of consecutive runs the suite is expected to
survive** -- and the only way to know it does is to run it that many times.

**A backend started before a route existed serves a 404 the surface renders as a permission
problem.** `serve.mjs` prints the commit it started from and says a later route is not served
until it restarts, and that was paid three times in one session: the batched-names read came
back 404, the page's `catch` swallowed it, every row read "withheld", and the screen spent an
afternoon claiming a mask that was not there. The fix is both halves -- restart the backend
after adding a route, and make the surface say which of the two it is, because "we could not
ask" and "you may not see it" have different remedies and only one of them is about the
reader.


**A leftover mutation inside a file you also edited is invisible to "which files changed".**
This file already says to read the diff after an interrupted sweep, and that was done -- the
file list came back as nothing but files this session had touched, which is what the rule
says to look for, and the check passed. The mutation was in one of them: a stopped sweep had
left `{text("roster.capacityIsElsewhere")}` replaced with `{""}` in a page whose panel header
had been legitimately changed an hour earlier, so the file was expected in the list and the
hunk was never read. It surfaced forty minutes later as one browser test failing on a
sentence nobody had touched.

So the check is the **hunks**, not the names: `git diff | grep -E '^-[^-]'` over every
modified source, and every removed line has to be one you meant to remove. A mutation
replaces, so it always removes something; a mutation whose replacement is the empty string
removes a line and adds a blank one, which is why searching the tree for the mutated *text*
cannot find it either.

**And stopping a sweep through the agent harness does not run its signal handlers**, which
this file records -- here the stop came from `TaskStop`, so the `finally` never ran. The way
to not need the check is to not start one you intend to stop: an inspection script that
`import`s the sweep module *executes it*, because the mutation loop is top-level code.


**Seventeen stale anchors in one sweep, and three of them were hiding something.** A
repointing pass is bookkeeping right up until it is not. `gate-order` was aiming at
`gateVerdict` in `@/lib/api` while the cell it asserts is rendered by `describeGate` on
`/permissions`, which keeps its own short words -- so a live protection read as a gap.
`table-name`'s protection had **changed layers**: the hand-rolled table became a `DataGrid`,
which renders its own caption, so dropping `labelledBy` no longer removes the accessible
name -- it restores the duplication the prop exists to prevent, which a browser test cannot
see and a usage sweep can. And tightening that sweep from per-file to per-grid exposed its
own hole: it asked whether a *file* contained `labelledBy=` anywhere, so a page with three
grids passed with one of them unlabelled.

**The repointed check then produced a false finding of its own**, which is the other half of
the lesson. `/<DataGrid\b[^>]*>/` looks like it matches an opening tag and stops at the first
`>` -- which for `<DataGrid<SourceRow>` is the *generic's*, so a correctly-labelled grid was
reported as an offender. Counting `<DataGrid` against `labelledBy=` is exact here and parsing
was not. **A check that reports a defect the app does not have costs the same trust as one
that misses a defect it does**, and the only way to tell them apart is to go and look at the
thing it named.


**A branch subsumed by the next one is proved only by the input that breaks the invariant
behind the subsumption.** A device strip checks `state === "maintenance"` before it checks the
server's `blocks_operation`, and the branch below -- "anything not active is out of service"
-- answers a maintenance device anyway, so removing the first changed nothing and the sweep
said so. The branch is not redundant: it is a guard against the *server* disagreeing with
itself, because `blocks_operation` is `active` and `offline` together and a maintenance device
can never carry it. So the case that proves it is the contract being violated -- both set at
once -- and the comment has to say that is what it is, or the next reader deletes the branch
as dead. **Same shape as a trigger that exists for the writer that is not the service**: the
input is one the current producer cannot emit, and that is the point rather than the problem.

**Two screens over the same data can disagree on purpose, and then both have to say so.**
MOD-021's `blocks_operation` deliberately excludes a device that has *never* reported --
nobody can be paged about when it stopped -- so the fleet board says nothing has gone quiet.
A front desk's question is whether the reader works now, and an in-service scanner that never
checked in is exactly as unusable as one that died, so FD-08's strip calls it degraded and
names a fallback. The first attempt "fixed" the board's test to match the strip, which was
the wrong direction: the board was right. The resolution is a comment on each side naming the
other, because a reader who sees two screens disagree deserves to know it was deliberate.


**A test that asserts a gap has to be rewritten the day the gap closes, and that is the rule
working rather than the test being wrong.** WebAuthn verification made `AAL 3` reachable, and
three things in the tree said it was not: `test_finding_1b_the_highest_level_is_not_reachable
_without_hardware` asserted `reachable: false`, `GET /authz/permissions` returned the **literal**
`"reachable_aal": 2`, and `visibility.UNREACHABLE_CLASSES`' comment said health was "unreadable
in this build, by anybody". Only the first failed. The second is the one worth the paragraph: a
ceiling written down as a number goes stale the hour the factors change, and a ceiling derived
from `VERIFIABLE_FACTORS` cannot -- so the response computes it now, and the comment explaining
why the number was 2 is gone with it. The third was a comment on a constant nothing reads, which
no test can see at all.

The finding behind that regression test was never "level 3 is unreachable"; it was that a
step-up cannot be had by naming a factor. So the test keeps the assertion that still holds --
two real credentials, correctly presented, still refused for a privileged action -- and says in
its own docstring why the other assertion went. **Ask of any test that fails when a gap
closes: was it asserting the finding, or a consequence of the gap?** Deleting it loses the
finding; leaving it insists on a limitation the product no longer has.

**And the same question has to be asked of every *reader* of the field the gap was expressed
in, which is the half that reached CI.** `reachable` answered whether any factor in the build
meets a level; `/auth/step-up` can only ever reach 2. While level 3 was unreachable by
anybody those were the same sentence, so a page keyed on `reachable` alone was right by
coincidence -- and the hour WebAuthn verification made it true, that page started offering a
credential field whose correct answer is still refused, which is strictly worse than the
honest "nobody can do this here" it replaced. **One boolean answering two questions is right
only while the two agree, and closing a gap is exactly what pulls them apart**: so when a
capability lands, grep every reader of the flag that used to stand for its absence, not only
the tests that asserted it. The repair is a second fact rather than a cleverer branch -- here
a ceiling derived from what the endpoint accepts -- and the honest long-term shape is for the
endpoint to state its own reach, because a constant in one client is a fact that cannot be
checked against the server that owns it.

**And a window measured from when the fixture ran is a green that depends on how long ago that
was.** FD-06's check-in window opens an hour before a class and closes `checkin_grace_minutes`
after it starts, and the fixture seeded the class thirty minutes out with the default fifteen
minutes of grace -- so the two tests that press the button had a seventy-five minute life.
**CI never sees it**, because CI provisions immediately before the suite; a local re-run two
hours later fails in a way that reads exactly like a product regression, and it did, twice.
This is the sibling of "a test that asserts a freshness has to create it", with the twist that
here the spec *cannot* create it: moving a session is a stepped-up scheduling write and a
browser session is AAL 1. So the fixture carries it -- the class forty-five minutes out so the
window is already open when seeding finishes, and the grace at the constraint's own ceiling of
240 so it stays open for nearly five hours. **The number is a product value at its legitimate
limit rather than a test hook**, which is the difference between widening a fixture and
widening a control.


**A guard no mutation can trip is usually the weak form of what it meant, and the sweep is
what tells the two apart.** `design:coverage`'s new `work:` rule asked whether a reason named
a module that is built — anywhere in the paragraph. Every one of the sixteen satisfied it in
passing (MOD-013 as the seam a send stops at, MOD-022 as the precedent for refusing to name a
working week), so swapping the module the work was actually *in* left two more behind and the
check still passed. Two rounds went into the mutation before the cause was obvious, and the
cause was not the mutation: "mentions a module" is not "says where the work is", and the
sentence that says it is the first one. Reading the first sentence instead is both stronger
and provable, and the same mutation then fails. **So when a mutation will not trip a guard,
read the guard before rewriting the mutation** — the unprovable form and the weak form are
usually the same form.

**And a mutation is decisive only against an entry that admits it.** The condition "the first
sentence names no module" cannot be produced by stripping the module from a reason whose first
sentence names two: the surviving one satisfies the guard. That is this file's own "a case
catches a weakening only if the weakened constraint admits the row", applied one level out —
to *which entry* the mutation picks, not only to which direction it moves. Two of the sixteen
`work:` entries name exactly one module in their first sentence, and those are the two the
case has to use.

**A harness must check that the mutation applied, not that the anchor was found.** One
mutation in this sweep was mangled by shell quoting, so the script died at parse time, the
file was never written, the check passed against unmutated source, and the harness reported
UNCAUGHT — a gap it had manufactured, sitting in a list beside a real one. The anchor test
this file already prescribes does not cover it, because the anchor was present and the write
never happened. Compare the file's bytes before and after, and classify "unchanged" as NOT
RUN.


**A claimed gap is a claim to check before building on it.** `design:coverage`'s backlog entry
for ADM-MSH-07 said the cancellation fee had no reader and was learnable only by cancelling;
`GET /memberships/{id}/cancellation-preview` had existed since MOD-017 was built. I wrote a
second reader beside it and found the first one only when wiring the route. The real gap was
narrower and worse: the read quoted a *different product* from the one the design approved,
and nothing compared the two because no screen rendered either figure — so the module had two
inline copies of one fee expression, identical, agreeing for exactly as long as nobody edited
one. Adding the buy-out to one of them would have had the disclosure read quote a figure the
command then refused, which is the disclosure requirement defeated by the function that exists
to serve it. **The gap note was a sentence somebody wrote about the code, and the code was
three greps away.** Ask of any note that says a reader is missing: grep the route table before
writing one.

**A modified file this session never touched has a second cause, and it is not always a
leftover mutation.** This file already records the interrupted-sweep case — read the diff
hunks, because a mutation whose replacement is the empty string leaves nothing to search for.
The other cause is a *concurrent session* in the same working tree: two sessions in one
checkout both see each other's uncommitted work, and `git add -A` then commits whichever half
is further along under one message. The tell is the same and the remedy is different: read the
hunks, and if they are coherent work in the project's own voice rather than one mechanical
substitution, they are somebody else's and the commit stages explicit paths. Related, and
sharper: **a shared dev database and a shared port are shared state.** `verify_db.sh` drops
and rebuilds `veyro`, which destroys whatever fixture the other session was holding, and the
roles are cluster-wide so a second database in the same cluster cannot coexist. A second
container plus `PSQL="docker exec -i <name> psql -U postgres"` is the isolation that costs
nothing, and it is what the script's own `PSQL` override is for.


**"I cannot run it here" is not "it has not run."** ADM-MSH-07's note in `CLAUDE.md` said the
browser layer had not been run for the screen, because the local suite needs port 3000 and the
shared `.env.e2e.local` and another session's servers held both. CI builds the database, starts
the backend, installs Chromium and runs the whole browser suite on every push — so the sheet
had in fact rendered at 375px in a real browser and passed before the note was written. An
under-claimed gap is a stale gap note like any other and costs the same thing: it points the
next reader at work that is already done, and it makes the notes that *are* true harder to
trust. Before writing that a layer did not run, check where else it runs.

And the correction has a narrower finding inside it, which is the one worth keeping: the phone
sweep covers a *route list*, and a surface reachable only with a query string is exactly the
kind that gets left off one. `?tab=membership&cancel=1` had to be added by hand. The geometry
is now covered and the *content* is not — nothing in the browser suite reads the sheet's
figures off the page — which is a real distinction and the sort that a single sentence saying
"the browser layer covers this" would bury.


**A hand-written fixture for a pure function can encode a state the system cannot produce,
and then the test proves a branch nothing reaches.** This file already records the surface
version -- "a surface branch no fixture can reach is the same vacuity, one layer up", found
four times in four modules. The unit version is quieter and was found a fifth way.
ADM-MSH-07's `commitmentLine` has four answers; its component test reached the `held_to_term`
one with `leaving_early: true` beside `may_leave_early: false`, which the server **cannot
emit** -- where a contract forbids an early exit the lifecycle pushes the effective date *to*
the term end, so access never ends before it. The branch passed its assertion and was dead in
the product, and the member it describes was told their commitment "has been served" nine
months inside it.

Nothing in four layers could see it. The component test was green because the quote was
written by hand; the backend tests asserted the fields and not what a screen concluded from
them; the e2e fixture had no contract with a term at all, so the branch never rendered; and
the type system is happy with any combination of booleans.

**The remedy is a builder that refuses an impossible state**, which is the cheapest thing
that notices and is the same shape as the backend's `check_split` and `check_summary_fields`
running at import. Each implication the server's own arithmetic guarantees becomes a throw --
here three of them -- and one test proves the builder throws, because a guard nothing
exercises is a guard with no evidence. Written as `quote()` wrapping a raw builder, so every
existing case is checked without being rewritten.

**And the field that was misread is worth keeping rather than renaming.** `leaving_early`
answers "does access end before the term", which is what the buy-out is charged on;
`term_is_running` answers "is there a commitment at all". One boolean answering two questions
is right only while the two agree. This is the `reachable` lesson with one difference worth
noting: `reachable` was right by coincidence until a gap closed and pulled the two apart,
whereas this one was wrong for one of its callers from the first commit and invisible because
no fixture rendered the case where they differ. **So the pin is a test asserting the two
fields disagree**, on the contract where they do -- an assertion that they are equal, or a
comment saying they differ, would both have survived the defect.

**A derived fact the client cannot compute belongs on the response.** `term_is_running` needs
`today`, which is on no response, and a client comparing a date against its own clock counts
days in a frame this file records three defects from. MOD-016's `in_window` and MOD-018's
`admits_trade` are the precedents: the implication is the fact, and a reader deriving it from
two timestamps gets the open-ended case wrong.

**A mutation that comes back uncaught is sometimes pointing at a hole in the evidence rather
than at a redundant guard, and the two read alike.** Three mutations were written against
`term_is_running` and the third -- making a contract with *no* term report a running
commitment -- was uncaught. It was not redundant: `commitmentLine` guards on `ends_on` first,
so the sentence was safe, but `freezeOffer` reads the flag directly, so a rolling member
would have been offered a freeze that "leaves the commitment standing" about a commitment
that does not exist -- the defect that function's own docstring exists to prevent. The test
had asserted the field true twice and false once, never for the absent case. **Ask of an
uncaught mutation which reader is unguarded before concluding the guard is unnecessary.**

**A seed is a schema reader of last resort.** The fixture for those four contracts was
refused `409 this_product_already_has_membership_terms`: `mem_membership_terms` admits one
set per product, which no amount of reading the surface would have surfaced and which the
migration states plainly. Worth noting because the refusal also improved the fixture -- three
contracts on three products is what a gym actually sells, not three contracts on one.


**Piping a suite through `tail` throws away its exit code and can throw away its verdict, so
a green shell says nothing.** `python -m unittest ... 2>&1 | tail -6; echo $?` reports
**`tail`'s** status, which is 0 whether 2,500 tests passed or forty failed -- and the window
is the wrong place to look anyway: unittest writes `Ran N tests` and `OK` to stderr while
tests write their own notes to stdout, and stdout is block-buffered through a pipe, so the
buffered notes flush *after* the verdict and the last six lines can be three PERF timings
from a test that ran ten minutes earlier. That is exactly what one run of this repository's
backend suite produced: ruff's "All checks passed", mypy's "Success", three PERF lines, and
`[exited with code 0]`, with no verdict anywhere and nothing wrong-looking about it.

**The tell is an absence rather than an error**, which is what makes it worse than a crash:
there is no `OK`, no `FAILED`, no `Ran N tests`, and a reader who is looking for a failure
sees none and moves on. The same shape as `verify_db.sh` exiting 3 with no checks run -- the
proof that did not happen looks nothing like the proof that passed, and also nothing like a
red.

So redirect to a file and read the verdict out of it, or at minimum take
`${PIPESTATUS[0]}`. And `grep -E '^(OK|FAILED|Ran [0-9]+ tests)'` is the thing to assert on:
it fails loudly when the verdict is missing, where `tail` fails silently. This is the file's
own closing rule -- "state a PASS when a command produced it, naming the command" -- and the
failure mode is that a *pipeline* can produce a PASS the command did not.


**Rendering a page and grepping the HTML is a real verification layer, with one trap that
makes it lie in the safe-looking direction.** When the browser suite cannot run -- another
session holding port 3000, a config whose `webServer.url` is hard-coded -- a dev server on a
spare port plus `curl` with a real session cookie still proves the *content* of a screen,
which is the half a backend test cannot reach. It proves nothing about geometry, focus order
or the accessibility tree, so it supplements the browser layer and never replaces it.

The trap: **React writes `<!-- -->` between adjacent JSX expressions**, so a figure composed
of several -- `{code} {sign}{major}{minor}` -- is `JOD<!-- --> <!-- -->80<!-- -->.00` in the
markup and contiguous text in the DOM. Playwright reads the DOM and matches; a raw-HTML
`includes` does not, and reports a figure that is plainly on screen as absent. Strip
`<!--[^>]*-->` before matching, or the check reports defects the app does not have -- which
costs the same trust as missing one.

It earned its place immediately: of two mismatches it found, one was that trap and the other
was a genuine bug in a spec I was about to push. A member on a contract with no notice period
cancels *immediately*, so the sheet says "Access ends today." and not "Access ends on {date}"
-- two different messages, and the spec asserted the dated one. **The pair of messages is the
thing to look for**: where a screen picks between two sentences on a condition the fixture
happens to fix, an assertion on either one is an assertion about the fixture.


**Running the checks a doc lists is not running the checks CI runs, and the gap is eleven
steps wide.** `CLAUDE.md`'s "Running it" section names the database rebuild, ruff, mypy, the
two backend suites and the worker. The workflow runs those *and* the governance structural
check, the governance validator's own suite, the domain-closure check and its suite, the
runner and trusted-gate suites, the screen-contract identity check, and four more web steps
(`audit:ci`, `design:check`, `tokens:check`, `test:foundation`). A commit that passed
everything the doc listed went red on **both jobs at once**.

Both failures were real and both were mine. An ADR's status and scope written as prose on one
line parsed as **no header at all**, so four required headers were reported missing -- the
checker wants `- Key: value`. And `design:coverage` refused three backlog entries that said
MOD-026 was unbuilt, because `backend/app/tasks/` now exists: **the stale-excuse direction of
a check written in this same session, firing correctly on its author within the hour.** That
is the cheapest possible demonstration that the direction was worth building, and it is also
the reminder that a gap note becomes false the moment the gap closes, whoever wrote it.

`tools/local_ci.sh` is the answer, so "I ran the checks" and "I ran the checks CI runs" stop
being different claims. It omits only what needs Docker and the browser suite.

**And it runs Python with `-B`, which is not a detail.** The domain-closure check refuses a
`__pycache__` directory inside a lane root -- an unchecked hash-based `.pyc` is loaded without
validating its source, so the bytecode that runs need not match the `.py` the tool reads. CI's
backend step is `python -B -m unittest`, so CI never has one; an ordinary local run creates
twenty-three of them. The first version of the gate script therefore failed two steps on an
artefact of *itself*, which is the harness-manufactures-the-gap shape this file already
records for mutation sweeps, arriving from a direction none of those paragraphs cover.

**A process gate the owner removed still lives in the tooling until somebody meets it.**
`governance_check.py` required every `ACCEPTED` ADR to carry `Review: <id> APPROVED`, and
`OWNER-2026-11-13-full-engineering-delegation.md` §3 removes "the requirement of independent
exact-diff review before publishing an ordinary change. Review is applied where risk warrants
it -- see §4 -- not as a uniform ceremony." ADR-0009 is the first ADR written after the
delegation and so the first to hit it. **The two wrong ways out were tempting and both are
fabrication**: inventing a review id, or quietly deleting the check. The rule is narrowed
instead -- a review that *is* claimed must still be well-formed, so an ADR cannot assert one
in a shape nothing can resolve -- and that narrowing is mutation-proven, because a malformed
claim still returns `BLOCKED`. Nothing in §4's preserved list (isolation, authentication,
immutable audit, financial correctness, residency, retention, negative tests failing closed)
is touched by it.

Its own test suite then failed twice, which is the same lesson one layer down:
`test_accepted_without_review` asserted the ceremony, and a sibling
(`test_accepted_with_invalid_review`) carried the finding that actually matters. So the first
flipped to assert the permission and the second was left alone -- **was this test asserting
the finding, or a consequence of the gate?** -- and a third case that used an absent review
merely as a convenient way to make an ADR invalid had its *means* swapped for a malformed
claim, keeping its own assertion intact.


**A snapshot that a table-wide grant can rewrite is not a snapshot.** MOD-008's review found
that re-deriving an approval's terms at decision time let somebody holding
`authz.policy.write` switch separation of duties off for a request already in flight and then
approve their own. The fix was to snapshot the terms onto `iam.approval_requests`. It closed
the re-derivation and left the snapshot writable: the grant was `GRANT SELECT, INSERT, UPDATE`
on the whole table, so `separation_of_duties`, `requested_by`, `required_approvals`,
`required_permissions`, `amount_minor` and `expires_at` were all writable by the runtime role,
and the same attack works one step over. The service writes exactly two of those columns, in
one statement. That is MOD-016's `cat_prices.effective_to` for the third time -- **a granted
column no service writes is an unattributed edit path** -- and here it ran through the one
control an invariant names.

**The wider finding is that the whole `iam` plane is table-wide.** Fifteen tables, zero
column-scoped UPDATE grants, while every `plt01` module from MOD-005 onwards is column-scoped
and MOD-010 records that in its module the column-scoped grant *is* the integrity mechanism.
`iam` holds identities, sessions, credentials, roles, assignments, policies, approvals and the
audit chain. Narrowing the approval path is MOD-026's business because INV-AUT-02 is its
invariant; the other thirteen tables are MOD-008's and are named here rather than quietly
left.

**And `SELECT ... FOR UPDATE` does work under a column-scoped grant**, which this file
previously only recorded in the negative ("needs the UPDATE privilege", from a table with no
grant at all). Measured rather than reasoned about, and the reasoning would have got it wrong:
`has_table_privilege(role, tbl, 'UPDATE')` reads **false** after narrowing, so a check derived
from that would conclude the lock is unavailable. It is available, and a trigger that locks
its parent row still works.

**A new trigger refuses the seed before it refuses anything else.** Putting INV-AUT-02 in the
database made `verify_db.sh` fail at *seed* time: `isolation.sql` had exactly one identity per
tenant from MOD-008 onwards, so its approval was requested and decided by the same person with
`separation_of_duties = true` -- a row `approval.py` refuses and the invariant forbids. **The
suite had modelled a state the product cannot produce for as long as the table has existed**,
and nothing noticed because nothing in the schema said so. That is the same vacuity as a
hand-written unit fixture encoding an impossible quote, in SQL, in the module whose invariant
it is. The seed gets a second identity, which is what the browser fixture needed for MOD-022's
two-party publication and for the same reason.

**Then it invalidated a case, which is the rule this file already states, met by its author.**
CHECK 32's "one decision per approver per request" inserted a second decision by the
*requester*, so the new trigger fired before the unique index and that case began proving the
trigger -- leaving the index droppable in silence. Adding a constraint is a change to every
case that inserts a row it touches. Here the suite refused to start at all, which is the loud
version; the quiet version is a case that still passes and proves the wrong rule.


**A probe that proves a *permission* needs a handler as much as one that proves a refusal.**
Check 113's branch for "a policy that permits self-approval still may" was written as a bare
INSERT expected to succeed. When the trigger was wrong the block aborted with the *trigger's*
message, which a sweep cannot tell from an unrelated error -- it reported MUTERR for a
mutation that branch had correctly caught. Wrapping it so a failure raises `CHECK nn FAILED`
makes the catch visible. The asymmetry is easy to miss because every other probe in the file
is a refusal.

**And a mutation that keeps a branch count by firing unconditionally kills the seed.** Two
mutations against a trigger function kept a dummy `RAISE EXCEPTION` so the block's
`RAISE`-counting assertion would still balance -- and put it on the straight path, so every
row was refused and the suite died before any check ran. `IF false THEN RAISE ... END IF`
keeps the count and changes nothing else. Both came back MUTERR, which is the harness
classifying honestly rather than manufacturing a gap, and both were the sweep's author's
fault rather than the schema's.

**A new table's own CHECKs are not reached by probes written for its triggers.** The
delegation sweep caught the trigger branches and missed the ninety-day ceiling, the
not-self rule and the revocation attribution entirely: those are `check_violation` on the
table, and nothing in a block that only inserts *decisions* touches them. "A constraint
nobody has broken on purpose is a constraint nobody has tested" applies per constraint, not
per module, and the sweep is what says which.

**A block's own earlier rows become siblings for its later cases.** Four constraint cases
added to check 113 failed because an identity used as the recipient had, two probes earlier
in the same block, been made a delegator -- so the transitivity trigger answered before the
constraint under test. The usual form of this rule is about a *constraint* added later
invalidating existing cases; this is the same thing inside one block, where the state a probe
leaves behind is the state the next one starts from.


**A short literal searched across a response body is a coin flip against `gen_random_uuid()`,
and it broke `main`.** `test_the_workspace_returns_no_name_and_no_card_detail` asserted that a
money read leaks no card last-four by checking `assertNotIn("4417", response.text)`. Four
digits are four hex characters; a uuid carries thirty-two, so each one offers twenty-nine
places for a given four-character sequence to appear, at about one in 65,536 each. With a
dozen ids in a payload that is roughly one run in two hundred -- invisible locally, red in CI,
and it took the shape of a correct response being reported as a privacy leak.

This is the **collision** form of the rule this file already records three times for consumed
budgets: a green that depends on something other than the behaviour under test. The budget
version is found by running the suite twice; this one is found only by running it enough
times, which means CI finds it and you do not.

**The fix is not to lengthen the probe.** Walk the parsed response, skip anything matching a
uuid, and check the remaining strings and every key -- a field *named* `card_last4` is as much
a leak as a value. That keeps the assertion's whole reach (it still fails on a brand or a name
anywhere in the payload, nested or not) and removes the collision by construction. Proven by
injecting `"card_brand": "Visa"` into a case row and watching it fail, then restoring.

**And grep for siblings, because the pattern travels.** One more existed:
`assertNotIn("4500", read.text)` asserting that a product read returns no price. The field
names were the real test there anyway -- a price reaching that read arrives in one of them --
so the substring was never carrying the weight it appeared to.


**A trigger that re-judges a parent on every write turns a retired parent into a lock on the
row.** MOD-026's escalation guard is `BEFORE INSERT OR UPDATE` and re-read the queue each
time, so retiring that queue refused **every** later update to every clock pointing at it --
the settlement included, which is the one write that makes the record true. A target whose
escalation team was merged into another could therefore never be judged: it stayed `running`
for ever and the compliance read counted it as still in hand. The control is "a clock may not
be pointed at a dead bell"; what it did was "a clock pointed at a dead bell is frozen", and
the second is not a stricter version of the first. **The clause that fixes it was already in
the module's own sibling trigger**, written three files earlier -- `tsk_task_matches_its_case`
re-checks its parent only on an INSERT or when the pointer actually moves. So: a parent-status
guard belongs on the write that *sets* the pointer, and `TG_OP = 'UPDATE' AND NEW.x IS NOT
DISTINCT FROM OLD.x THEN RETURN NEW` is the shape.

**And a probe for a permission is what finds it.** Every other probe in a trigger block
asserts a refusal, and no number of refusal probes can see a guard that refuses too much --
nor can the `RAISE`-counting assertion, since nothing was added or removed. The case is the
ordinary write the module must still allow, wrapped so it fails under its own name.

**Run a trigger-branch block as the table owner, not as the service's role.** A branch that
guards a column outside every runtime role's UPDATE grant -- which is the ordinary shape for
"a target and its start do not move", where the grant exists precisely so the trigger never
has to speak -- is answered by the privilege layer under `veyro_cp_app`, so the probe proves
the grant and says nothing about the branch. The owner is the writer that branch exists for,
and a trigger that refuses the owner refuses everybody; FORCE RLS still applies, so the tenant
predicate is in force either way. A probe that comes back `insufficient_privilege` is a probe
with no evidence behind it and has to say so rather than counting.

**A mutation that deletes a `RAISE` is caught by the count, not by the probe.** Where a block
compares its probe count against the `RAISE EXCEPTION` count in the catalogue -- which is the
shape this file requires -- deleting a refusal fails that assertion, so the mutation proves
the counter and leaves the probe it was aimed at unproven. `IF false AND <condition> THEN`
keeps the count and removes the refusal, which is the mutation that actually tests the probe.
The opposite error is already recorded here: a dummy `RAISE` kept for the count and fired
unconditionally kills the seed, and the sweep reports MUTERR for a mutation it never ran.

**A state derived from a different pair of numbers than the figure beside it will contradict
it, and only the second reader notices.** MOD-026's SLA read returned `consumed_seconds` and
`remaining_seconds` computed from the business calendar *minus the pauses*, and a `state`
computed by comparing `now` against a due instant walked forward from the start -- which knows
nothing about the pause table. A clock stopped for a week read `breached` beside a
`remaining_seconds` well above zero, which makes the pause decorative on the one field anybody
acts on. The same expression measured the warning threshold as `(now - started) / (due -
started)`, wall-clock over wall-clock, in the module whose entire subject is that those are
not the same thing: a target opened at five on Friday is 80% of the way to a Monday deadline
by Sunday evening with no business second spent. **Both were invisible for as long as the only
reader was the read itself** -- the suite asserted `state` was one of three strings. Derive a
verdict from the numbers the response already carries, and when a second caller appears, check
that it would reach the same answer by the same route rather than writing it a second one.


**A check that validates a structured field cannot validate the prose beside it, and the
prose is what a reader believes.** `design:coverage` verifies that a backlog reason's
`MOD-0NN` names a real module and that the module has not landed -- the stale-excuse
direction, which this repository built on purpose and which has fired on its own author.
What it cannot see is the sentence next to the token: three MOD-026 reasons went on saying
the module had no service layer and no routes, and named slices as outstanding that had
since landed, for as long as the module id stayed correct. That is MOD-010's "the
restricted-field rule checks names, and a value can carry anything" in a governance check
rather than an event payload. So when a slice lands, re-read every reason that mentions it
rather than trusting the check that passed -- and prefer a reason that names *what is
missing*, drawn from the design, over one that names *which slice it is in*, which goes
stale by the calendar.


**A mutation harness that mutates the *database* has to restore it, and this one did not.**
Every sweep in this repository until now mutates a *file* and puts it back in a `finally` --
and this file already records that a SIGKILL defeats that, so read the diff afterwards. A
SQL sweep is different in a way nobody had hit: `verify_db.sh` applies `MUTATE` **after** the
build, nothing puts it back, and the harness simply moves on to the next mutation. So the
last mutation of the run sits in the development database when the sweep finishes, and every
suite run afterwards judges a schema nobody wrote. It cost a full backend suite: 2,648 tests
reported OK against a trigger branch the sweep had disabled, and the only reason it was
caught is that the run afterwards was being checked against the tree it would be committed
on. **The tells are nothing**: the suite is green, the checks pass, the diff is clean --
because the artefact is in the database rather than in the tree. So a database-mutating
sweep ends with one more clean rebuild, says it did, and says loudly when it could not;
and after any interrupted one, rebuild before believing a suite.

**And the sibling already did it.** `tests/sql/sweep_access.sh` rebuilds at the end of every
loop iteration, which is why MOD-022's sweep never left anything behind. That is the second
time in one session that the fix for a thing I had just written was already sitting in the
file next to it -- the other being an escalation trigger whose "re-check only when the
pointer moves" clause was in its own module's sibling, three files earlier. **Read the
nearest existing instance before writing a new one**: this repository's rules are mostly
recorded as prose, and prose is easy to agree with and hard to notice you have not applied.


**A hard-coded count that only CI can reach will be found by CI, and that is the deliberate
trade rather than a defect.** `operations.spec.ts` asserts the number of rows on the
scheduled-jobs board as a literal, and its own comment says why: "the count is a tripwire on
purpose ... wiring a job should bring somebody to this file". Slice 3c wired the tenth worker
job, ran the whole backend suite twice on a freshly rebuilt database, ran every non-Docker CI
step, and went red on that one line -- because the backend's own assertion derives from
`len(registry.JOBS)` and this is the only hard-coded count of it in the repository, so nothing
runnable locally could see it. **The judgement to make when a tripwire fires is which of the
two it is**: a stale count of something *missing* goes false the hour the thing is built and
should become a property (the reports index's `UNBUILT.length`, recorded above); a count of
something *present*, written as a literal with a stated reason, is a review prompt and the
right answer is to visit the file rather than to soften the check. Both look identical in a
red log, and only the comment beside the literal tells them apart -- which is the argument for
writing that comment when the literal goes in.


**A per-column clear has to answer every constraint the column sits under, and sometimes the
answer is that no clear belongs there at all.** This file already records that MOD-009's
tombstones are per-column "because every entry answers a real constraint" -- that is the
direction where a NULL would be refused and a tombstone is needed. MOD-026's `0024` found the
other direction. Three new subject columns on a case looked like `anonymize`, and the obvious
clear table would have NULLed `assignee_person_id`, `snoozed_by` and `snooze_reason` --
which `tsk_cases_snooze_attributed` refuses, because the five snooze columns are all-or-none.
And clearing all five would have been **worse than the refusal**: it un-defers the case,
moving it back into a queue somebody has to work, so the erasure would have changed what a
tenant has to do today. An erasure with an operational side effect is not a stronger erasure.
So the assignee clears and the two prose columns are declared `write_once` residue with that
reason on the row -- which is the registry being a statement about what the privileges and the
constraints *together* permit, rather than about what one would like to be true.

**And `anonymize` needs `clears` as well as a grant, which is a second thing the test
checks.** The declaration names the mechanism and the executor names the columns actually
overwritten, and a mechanism with an empty `clears` is a promise with nothing behind it:
`test_an_anonymize_declaration_names_columns_that_exist_and_can_be_cleared` is the one that
fires, with the column name in the message. Worth knowing because the grant half passes first,
so the failure arrives after the part that looked like the work.


**A static scan of SQL text cannot tell a constraint from a comment about one.**
`test_migration_shape` hunts for `length(btrim(x)) > 0`, the form this repository banned across
118 constraints, and `0024`'s header explains *why* it is banned — so the header quoted it and
the check reported the migration as an offender. A check that names a defect the schema does not
have costs the same trust as one that misses a defect it does. `sql_only` strips the `--`
comment portion of each line and not the whole line, so `CHECK (length(btrim(x)) > 0) -- note`
is still caught, and it tracks single-quoted literals because the replacement shape itself
carries a quoted regex. **Mutation-proven the long way round**: the first attempt replaced a
string that is not in the file, the file was unchanged, and the harness's own check for "did
the text already contain the banned form" was satisfied by the comment — so it reported a catch
that never happened. Compare the file's bytes.

**A hand-written type over an untyped JSON response is invisible to every typecheck, and the
tell is a fallback rendered everywhere.** `QueueRow.name` was the field this app read and
`display_name` is the field the route sends, so every queue on the task board rendered as the
fallback word "Queue" — `tsc` is happy, the lint is happy, and the page is wrong in a way no
assertion about a label can see. This is the `AccessDecision.masked` finding already recorded
here, met again in the same session that recorded it. **Read the response; do not name the
field.** And a fallback that appears on *every* row is the signature: a type that is wrong about
one field renders one wrong cell, and a type that is wrong about the field a whole column reads
renders the fallback down the column.

**Two definitions of one figure on a single screen, three times in one slice.** MOD-018's
"one module, two definitions of the same balance" is usually about two functions in a module;
ADM-TSK-01 produced it three times in one page, and all three were found by rendering the page
and reading it rather than by any assertion:

- **A chip counted work in hand and the table listed every status**, so the board read
  `Team · 7` over eight rows with one already done. The server grew the same restriction the
  chip uses (`in_hand`), rather than the client filtering what it was given — which is the
  members list's own finding, where summing the page was honest and still the wrong number.
- **Lateness was an instant on the server and a calendar day in the client.** The overdue
  filter is `due_at < now()`; the label bucketed by date on both sides, so a task due at nine
  this morning read "due today" at five in the afternoon beside an Overdue chip that counted
  it. **And the corrected rule needs a second message**: zero whole days late is "overdue" with
  no count, because "overdue 0 days" is not a sentence and English's plural rules pick `other`
  for 0.
- **A count under a grid and the same count in the sub-line above it.** §25 asks a grid to
  state its count and the canvas states it in the sub-line, so both is the sentence said twice
  — the rule the `DataGrid` caption and the field shell's message slot both already carry.

**A locator inside a `DataGrid` row resolves to two elements, and `.first()` picks the hidden
one.** Every droppable value is in the DOM twice and visible once; that is the component's
documented mechanism and `phone.spec.ts` asserts it. So a spec about *content* has to ask for
the cell (`getByRole("cell", { name })`), and five assertions in one new spec failed on this at
once — four as strict-mode violations, which are loud, and one as `Received: hidden`, which
reads like a product defect. The quiet one is the dangerous shape.

**`getByRole("button")` without a container asserts the app shell.** The language and theme
switches are buttons on every screen here, so a document-wide count on a read-only board
reported four where none of them belongs to the board — and a spec that asserted four would
then break the day the shell grew a fifth control, for a reason that has nothing to do with the
screen under test. Scope it to `main`.

**A branch that `in_hand` makes unreachable is not the branch that was worth keeping.** The
task list's checkbox was gated on "not settled", which the server-side filter made always true
— a branch no fixture can reach. The reachable case is a *blocked* task, which is in hand and
which `blocked -> done` refuses in the Python table and in the trigger alike: so the gate is
the status the state machine refuses, and the fixture seeds one. Same judgement as deleting a
constraint subsumed by a sibling, arrived at from the surface: when a filter makes a client-side
check vacuous, ask which case the *server* still refuses and gate on that one.


**A probe whose row survives its own mutation poisons the probes after it.** Check 113's
single-stage case pointed at a request other probes decide: with the branch disabled the
refused insert *landed*, and a later probe then hit `UNIQUE (tenant_id, request_id,
decided_by)` -- so the sweep reported "a check other than 113 answered" for a mutation that
branch had correctly caught. This is the "one bad probe aborts the block" trap from the other
side: there the probe's own statement was refused by a sibling, here it *succeeded* and
changed the state the next probe starts from. A probe for a refusal needs a subject nobody
else touches, because the world where its mutation is applied is a world where its row exists.

**And a constraint case needs a value no sibling rule claims, which depends on the mutated
world rather than the real one.** Two of the new request-stage cases used a permission already
held by another stage of the same request: correct today, because the ordinal CHECK fires
first -- and with that CHECK dropped the row was refused by the one-stage-per-permission rule
instead, so the case proved the sibling. The question to ask of a case is not "which rule
refuses this row" but "which rule refuses it once the rule under test is gone".

**A BEFORE trigger subsumes a range CHECK on the column it validates.** `stage_ordinal`
carried `CHECK (stage_ordinal BETWEEN 1 AND 8)` and the trigger refuses any ordinal the
request has not got -- which for a staged request means anything outside its own stages,
themselves bounded, and for a single-stage request means anything but 1. So the CHECK had no
isolating case and could not have one: the sweep reported its drop as uncaught and the probe
written for it was answered by the trigger's sentence. Deleted rather than tested harder,
which is MOD-016's judgement for a kind domain its operand constraint already named and
MOD-018's for a ceiling a trigger already bounded.

**An uncaught lock mutation is the one case where the honest answer is usually to remove the
lock.** `FOR UPDATE` on a parent row is this file's own prescription where a trigger reads it
to decide whether a child may be written -- and the prescription has a premise: that the
absence lets through something the lock would refuse. For MOD-026's stage guard neither reader
could move. `sequential` is outside every runtime role's UPDATE grant, and the earlier stages'
approvals come from an insert-only table, so two concurrent decisions at READ COMMITTED are
each fail-*closed* with respect to the other: without the lock a stage-2 decision racing the
stage-1 approval it depends on is **refused** rather than admitted. The lock would only have
made the guard more permissive under concurrency, which is the wrong direction for a guard. So
the rule has a companion: before adding `FOR UPDATE` to a trigger, name the column that can
move and the direction the race goes -- and if the unlocked answer is the stricter one, the
lock is decoration and a two-connection test would be proving nothing.

**PostgreSQL truncates a generated constraint name at 63 characters**, so a mutation naming
`approval_request_stages_request_id_required_permission_key` errors and is recorded as not
run -- the harness manufacturing the gap it then reports. Take the name from `pg_constraint`
rather than composing it.


**A pairwise consistency check is not a consistency check, and the third element is where it
breaks.** MOD-026's stage order was validated by comparing each new policy against each live
one for every permission they *share*: A before B beside B before C beside C before A passes
all three comparisons and cannot be satisfied together. Worse, the combination rule then
resolved it silently -- every permission's ordinal came out equal under `max`, so the result
fell back to the alphabet and one policy's stated order was quietly dropped. The fix is a cycle
check over the union of every ordering, and a topological sort (Kahn, with a sorted ready set
so the answer stays order-independent) rather than a per-key maximum. **Found by working the
cycle through on paper**, which is worth recording: the pairwise version passed every test that
existed when it was written, and the test that catches it had to be derived from the shape of
the rule rather than from a failure.


**Narrowing where a check applies opens a hole where it used to.** MOD-026's stages moved the
permission requirement from the policy to the stage, because charging the union to every
decider means each approver needs every stage's authority -- one person satisfying all of them,
the opposite of what a stage is for. The consequence nobody writes down is the other side: a
policy's own `required_permission` outside its stage list is then checked by *nothing*, so a
staged policy could name an authority nobody is ever asked for. Refused at the write, which is
a declared value nothing reads caught before it exists -- and the refusal caught two of the
slice's own test fixtures on its first run, which is the usual sign it was worth having. **When
a check narrows its scope, ask what the old scope covered that the new one does not.**


**A design record's claims about other modules are claims, and checking them is the point.**
ADR-0009 produced two findings that way and ADR-0010 produced a third: it said converting a
trial is `change_plan`, "which MOD-017 has". `change_plan` is **MOD-015's** -- the SaaS
subscription a tenant buys from Veyro -- and a member's membership has no plan change at all.
What it has is `upgrade` and `downgrade` in `lifecycle.EDGES`, declared as `active -> active`
with `_record_change` already taking the kind and `check_transition` already knowing the
statuses, and **nothing anywhere writes either**. Pulling that thread found that eight of
MOD-017's thirteen declared change kinds have no writer and its gap list said nothing about it.

Two rules fall out, and the second is the one worth carrying:

- **Grep the writers of every value a state machine declares**, not only the ones the module's
  own tests exercise. `grep -rhoE 'change_kind="[a-z_]+"' app/` answers it in one command, and
  five of thirteen came back.
- **A name that exists in one module is not the mechanism in another.** Two modules here both
  sell something on a recurring basis to different customers, so "plan change" is a phrase that
  resolves in both -- and a record written from the phrase rather than from the symbol put the
  wrong module's machinery into a build order. The check is the import path, not the word.

**And a declared value the privileges forbid is stronger than one nothing writes.** The
correction above was itself wrong once: having found `upgrade` declared and unwritten, the
record then said the conversion is an upgrade command somebody has to build. It is not
buildable. Moving a member between products would have to move
`mem_memberships.agreement_id` or `mem_agreements.variant_id`, and neither is in any runtime
role's UPDATE grant -- nor is `price_resolution_id`, nor `person_id`. The module's own premise
is that what the member agreed to does not move, which is what makes "what did they agree to a
year ago" answerable from the row. So two of its thirteen change kinds name an act its own
privilege layer rules out, and the remedy is to delete them rather than to widen a grant that
is load-bearing.

**And that reading was wrong too, for a reason worth more than either.** `has_column_privilege`
said `agreement_id` cannot move, so the act looked prohibited -- and the schema already carries
`mem_agreements.supersedes_agreement_id`, a self-referencing chain whose own comment says it is
"for an upgrade, downgrade or transfer". The immutable column is the chain's *root*, not a
prohibition: what a membership originally agreed to does not move, and what it is on now is
derived by walking forward. `create_agreement` takes the field and a route exposes it.

**What is actually missing is a reader, and its absence is a trap rather than a gap.** All five
readers of a membership's terms go straight to the root, so a superseding agreement written
through the route that exists leaves the freeze allowance, the cancellation fee, the notice
period and the early-termination buy-out all answering from the agreement the member left --
every figure the module discloses, silently wrong, with no adversary and one route call.

So the rule is **not** "ask whether the columns can move". It is: **when a declared state has
no writer, look for the column that would record it before concluding anything about why.** A
self-referencing pointer, a status, a supersession chain -- the schema often already carries
the mechanism, and three readings of this one went wrong by reasoning from what could not be
updated instead of looking for what had already been built. "A column implying a control nobody
implemented" has an inverse this repository had not met: a column implying a *model* nobody
reads, which is worse, because the write path exists and every reader disagrees with it.


**A reader that resolves correctly is not a reader its callers all go through, and the sweep is
what counts them.** MOD-017's supersession chain had eight readers of a membership's terms and
`current_agreement` closed five of them in one pass; the other three were SQL joins on
`m.agreement_id` in three listing queries, invisible to every test that exercised the five.
Nine mutations put one reader each back on the root, and **two came back uncaught, both real
evidence gaps rather than redundant guards**:

- **The read and the command resolve separately.** `preview_cancellation` and
  `cancel_membership` each resolve the agreement, and every assertion written for the fix was
  about the read -- so a command still on the root would have refused the preview's own
  disclosed figure as a mismatch, which is the disclosure requirement defeated by the pair of
  functions that exist to serve it. **A disclosure read and the command it discloses for are two
  readers**, and a test for one proves nothing about the other.
- **The guard was for a state nothing writes.** The walk filters `status <> 'void'` and no
  service function writes `void` -- so no route-level test can exercise the clause, and the
  sweep reporting it uncaught is reporting the absence of a *writer* rather than a redundant
  guard. The guard stays (the grant admits the write and the partial index carries the same
  predicate, so the two cannot drift) and its probe writes the status directly: **the probe for
  a guard that exists for the writer the service is not has to be that writer.** Pulling the
  thread found that `superseded` and `ended` have no writer either, so after an upgrade the
  superseded agreement still reads `active`.

**A partial unique index needs a case per direction, and the permission is the one a drop-only
case cannot see.** `mem_agreements_one_live_supersession` is `UNIQUE (tenant_id,
supersedes_agreement_id) WHERE ... status <> 'void'`. Dropping it is caught by the fork case;
removing the *partial clause* makes a legitimate insert fail -- a voided successor would
permanently occupy the slot its replacement needs -- and only an insert the index must **admit**
catches that. Two cases, two mutations, and the second mutation is `DROP INDEX` followed by
`CREATE UNIQUE INDEX` without the `WHERE`, because an index is not a constraint and `ALTER TABLE
... DROP CONSTRAINT` does not reach one.

**And a `status` a case sets has to satisfy the attribution constraint beside it.** Three rows
added for those cases carried `status = 'active'` with no signature columns, which
`mem_agreements_signed_is_signed` refuses -- so the fixture died before the block ran, and in the
quieter version the case would have been answered by that sibling. `GET STACKED DIAGNOSTICS` is
what distinguishes them, and it is as necessary for `unique_violation` as for `check_violation`.


**"Not void" is not "in force", and a chain walk that stops at the first lets a draft govern.**
MOD-017's supersession walk filtered `status <> 'void'`, which is the predicate `0025`'s index
carries and is right for *that* index -- it stops a fork. It is wrong for the walk: a **draft**
successor, written by one route call with nobody's signature, became the agreement every
disclosed figure answered from, which is strictly worse than the root it replaced because at
least the root was signed. A successor governs when the member has signed it **and** its own
start date has arrived, which are two facts the table already carries. **An index's predicate
and a reader's predicate answer different questions**, so sharing one between them is only safe
where the questions coincide, and "which row is the live successor" is not "may this row exist".

**And the start date is what lets a future-dated change need no job.** Once the walk compares
the successor's `starts_on` against the day it is asked, a downgrade effective at the next
renewal is invisible today and governing then, with nothing to catch it up -- MOD-018's "expiry
is evaluated rather than swept" and MOD-016's window read at resolution time, applied to which
contract a member is held to. The cost is that every reader has to take an as-of date; the
benefit is that the one lifecycle act this module used to refuse outright (a future-dated
freeze, refused because "a booked freeze that never takes effect is worse than one that cannot
be booked") becomes expressible for plan changes without a sweep.

**A command that derives its own kind cannot find its own retry by that kind.** `_recorded_change`
compares the recorded `change_kind` against the caller's, which is what stops a key reused
across two commands returning the other one's work. A plan change derives `upgrade` or
`downgrade` from the two prices, so it has nothing to compare until it has read them -- and by
then the agreement it signed on the first call is the live one, so deriving first refuses the
retry as "already on that agreement". The ordering has to be retry-first, which means the
lookup takes the *set* of kinds the command can produce and the discriminator moves to a field
that distinguishes two of them: here `to_agreement_id`, added by `0026` for this and for the
history, which could not say what an upgrade moved onto.

**A new column breaks three pins and that is the pins working.** `0026` added one nullable
column and a foreign key, and the module's foreign-key set, its column-list pin and its
NOT NULL pin are all compared as sets in both directions -- so the migration was refused three
times before it was accepted, each time naming exactly what had changed. Budget for that when
adding a column: the refusals are the cheap half, and the expensive half is the constraint
cases, because a biconditional needs one per side and only the side the weakened constraint
*admits* catches a weakening.


**A test cannot change PostgreSQL role, because no role is a member of any other.** That is
this file's rule 4 -- runtime roles "are members of no role (no `SET ROLE` path)" -- and it
means a fixture cannot borrow the owner's privileges to set up a state the service is not
allowed to write. MOD-027's cold-lead rule runs from `crm_leads.created_at`, which is outside
every runtime role's UPDATE grant on purpose (age is the column the design says matters, and a
lead whose age could be reset is a lead that never goes cold), so there is no way to age a lead
by writing to it. **Ask from a later moment instead**: the read takes an `at`, the service test
passes one, and the HTTP test asserts what a request can -- which is also why no *route* takes
an instant, since a caller-supplied "now" would decide which leads a manager is told are going
cold. MOD-020 split its settlement tests the same way and for the same reason.

**A sort is a rule, and a case proves it only if the two orders disagree.** MOD-027's lead list
is ordered oldest-*contact*-first because the canvas says a lead's value decays by the hour, and
the first test for it created the untouched lead first and touched the second -- where ordering
by `created_at` and ordering by last contact give the same answer. The mutation sweep reported
the ordering as uncaught, correctly: the case that bites touches the lead created *first*, so
the two keys fall on opposite sides. That is this file's "a case catches a weakening only if the
weakened rule admits the row", applied to an `ORDER BY`, and it is worth stating separately
because a sort has no constraint name to anchor a case to.

**The stale-excuse direction fires on a whole module the moment its package appears, and that
is the check working at its widest.** `design:coverage` refused eight screens at once when
`backend/app/crm/` was created -- every `MOD-027:` reason naming a module that now exists. The
remedy is not a token change: each reason has to say what is *left* in the module, which is a
different sentence per screen and is exactly the information a reader needs. Budget for it when
a new module's first slice lands, and read each reason rather than editing the prefix.


**A page must not render its own `<main>`, and nesting one costs *both* their landmark role.**
`layout.tsx` wraps every page in `<main id="main">`, so a page that renders another produces
invalid HTML — and Chrome then exposes neither as `main`, which means the screen renders
correctly and `main` is absent from the accessibility tree. Every assertion about text passes;
what fails is a locator scoped to `main`. Found by reading the tree out of a failing spec rather
than by any sweep, and the tell is that *some* assertions on the page pass while every one
scoped to the landmark does not. Scope a spec to `#main`, which is the layout's own, and give a
page's content a `div`.

**A masked value is a marker, not a null, and treating it as absent hides the remedy too.**
`GET /people/names` answers a field this session cannot read with the mask string, so
`found?.legal_name ?? null` yields `"***"` — which renders as though somebody were called that,
and makes a "some name is withheld" test false, which is how MOD-027's board lost the step-up
offer it needs. `isWithheld` is the test, the members list already used it, and the browser spec
is what caught it: the assertion that the step-up link is *present* is the one that fails, not
the one about the name. **When a read can mask, the surface's "is this withheld" check is a
function and never a null check.**

**A sweep that measures overflow cannot see a layout that is merely unreadable.** A five-column
CSS grid at 375px is 68px a column: it does not overflow, so the sideways-scroll sweep passes,
and the content wraps into a strip of broken words. The responsive behaviour belongs to the
component rather than the screen — §08 of the design source says so in as many words — so it is
a class with breakpoints, and the breakpoint-boundary sweep then checks the numbers are the
design's. **Overflow and legibility are two properties and only one of them has a sweep.**

**`getByRole(..., { name })` matches by substring, so "Age" finds "Stage".** Playwright's
accessible-name matching is a substring test for a string argument, and a column header that
names a superstring of another is the smallest possible form of the positional-locator trap:
the assertion passes against the wrong element until a second header makes it ambiguous. `exact:
true` for any name that is a substring of a sibling's.

**And never `import()` a sweep module to inspect it — this file says so, and it happened again.**
`node -e "import('./tests/e2e/mutate.mjs')"` *ran* the whole browser mutation sweep in the
background, which edits source files; `TaskStop` reaches none of the handlers, so it took a
direct `kill -TERM` to the node process and then a `git status` to find the leftover — a
one-line mutation in `permissions/page.tsx`, a file the session had never touched. The tell is
exactly the one already recorded: **a modified file you did not author.** Read it with `cat`,
check its syntax with `node --check`, count its entries with a regex — never by importing it.


**A native `required` refuses the whole form, and a form with two submits has one that does not
need it.** ADM-CRM-04 has a second button — "Add a lead for them", the canvas's own *"that
record would open instead of a second one being created"* — which opens a lead against a person
who already exists and therefore needs neither the name nor the phone. With `required` on those
inputs the browser refused the submit, showed its own bubble on an empty Name, and **fired no
submit event at all**: the server action never ran, nothing appeared in the dev log, and the
click reported success. It took a DOM probe to see it — a `submit` listener in `page.evaluate`
that never fired — and three wrong theories (the submitter's name/value, hydration, React's
form-action dispatch) before that.

**And the same constraint was hiding a message on the sibling screen.** ADM-MEM-10 carried
`required` on both its fields, so the browser always refused before the server could answer:
`missingFields` was unit-tested as a decision and `walkIn.nameNeeded` was **a branch nothing
could render**, which is this file's own "a surface branch no fixture can reach" in the one
place a reader is being told what they got wrong. `aria-required` keeps the announcement and
drops the refusal; the server validates and the message slot carries the sentence, which is
this app's own stated rule — *"validate on blur, never on keystroke; re-validate on submit"*. A
native bubble is the browser's version of a disabled submit: it stops the reader with a message
this app did not write, in a language it did not choose.

**A spec that creates a row and a sibling that counts rows are coupled through the fixture's
tenant.** The add-lead spec opens one lead per run and `leads.spec.ts` asserted `4 open leads`
and exactly four table rows, so adding the first spec turned the second red — in the shape of a
product regression. This is the consumable-state trap from the other side: not a budget the
test spends, but a total another test moves. The property worth holding is that each *seeded*
lead is drawn as its own link and that the figure comes from the board read rather than from the
page's rows, so the count is a floor and the shape is the assertion. A literal total is an
assertion about which other specs have run.

**A design-system component that hard-codes a word is invisible to both message-parity
checks.** The field shell rendered `" (optional)"` for the optional mark — Latin letters in the
middle of an Arabic line, live on the account page for as long as that field has existed.
`MESSAGE_KEYS` compares the two catalogues against each other and a string that never became a
key is in neither; the per-plural-form sweep reads call sites of `fill`. `StatusBadge` is the
precedent and the remedy is the same: the component takes the word, renders no mark without it,
and a usage sweep requires it wherever the branch is reachable — mutation-proven against the
one call site that had it. **The asterisk is why it survived**: the required mark is
punctuation, so half the API needed no catalogue and the half that did looked like the same
thing.

**A hand-rolled copy of an approved component is a hand-rolled copy of its class names too.**
The lead board wrote its own `ds-page-head` markup with the figures in `.muted` rather than
`.ds-page-figures`, which §8 of the directive of 2026-11-20 forbids outright — and the cost
showed up in a spec: an assertion written against the design system's own selector found
nothing on the one screen that had copied the component instead of using it. Replacing it with
`PageHeader` fixed the spec and the deviation at once.

**Clicking a visually-hidden checkbox is intercepted by its own label, which is the component
working.** `ChoiceChips` hides the control and draws the chip on the label, so Playwright's
`.check()` — which clicks the input — is refused by the face in front of it. `{ force: true }`
would skip the actionability check and hide real problems; the click a reader makes is on the
chip, and that is the one worth asserting, with the checkbox's own `toBeChecked` behind it.

**A probe assertion can pass on the text of its own debug output.** A temporary test asserted
`toContainText("error")` against a `<p>` dumping `JSON.stringify(state)` — which contains
`"error":null`, so it matched instantly and reported success for a submit that never happened.
Vacuous evidence in a throwaway probe is still vacuous evidence, and it cost one wrong
conclusion before the dev-server log settled it.

**The fixture's worker subprocess and the API it drives must point at the same database.**
`runWorkerTick` spawns `python -m app.worker` with `VEYRO_DATABASE_URL` defaulting to the
documented dev port; a backend started on a different one produces
`insert or update on "ops_metric_points" violates ... Key is not present in table "tenants"`
for a tenant that **is** present — because the tick is reading the other database. The message
names the right tenant and the wrong cause, which is what makes it expensive. The rule is the
one this file already states for a server started by hand, one layer down: read the harness's
own env block and match it, or point both halves at the documented default.


**A column whose readers already exist and whose writer is missing is a feature to adopt, not
a column to add.** MOD-027's trial needed a clock, and `mem_memberships.ends_on` was already
there -- in the UPDATE grant, written only by a cancellation, and honoured by *three* things a
trial needs: MOD-022 refuses a door on the membership's dates rather than its cached status,
`memberships.revoke_ended_grants` sweeps the grants of a membership whose `ends_on` has
passed, and a countdown is `ends_on` minus today. Deriving it at activation bought all three
and added no mechanism; a trial clock of MOD-027's own would have been a fourth definition of
when a trial ends, and the first time it disagreed the door and the screen would say different
things about one person.

This is the inverse of the finding this file records most often. "A column implying a control
nobody implemented" is a column with a writer and no reader; this is a column with *readers*
and no writer, and it looks identical in a grep. The question to ask of a new fact is not only
"where would I store this" but "what already reads a column of this shape" -- and the answer
was in MOD-017's own gap list, which says in as many words that the door reads the dates.

**`USING (tenant_id, ...)` is ambiguous the moment two joined tables carry `tenant_id`, which
in `plt01` is all of them.** `JOIN a USING (tenant_id, agreement_id) JOIN t USING (tenant_id,
membership_terms_id)` is `AmbiguousColumn` at runtime, not a planning error a reader would
spot -- so it reaches whichever test first exercises the query. Explicit single-column `ON`
clauses are what the module's existing walk-joins use, and they are safe for the reason the
composite keys exist in the first place: RLS bounds the tenant on every one of those tables, so
the tenant equality is already enforced rather than being the join's job.


**A mutation sweep's *restore* overwrites concurrent edits to the file it is mutating, which is
a third way to lose work to one.** This file already records two: a stopped sweep leaving a
mutation behind, and `import`ing a sweep module running it. The third is quieter and cost two
edits here: the harness captures `original = path.read_text()` before each mutation and writes
it back afterwards, so anything written to that file *between* a mutation's write and its
restore is replaced by a copy taken minutes earlier. `ruff` and `mypy` had just passed on the
edits; `grep` for the new symbols found them gone.

The tell is that *some* of a session's edits to one file survive and some do not -- the ones
made before the sweep started are in every `original` it captures, and the ones made during it
are not. So the check after a sweep is not only "is a mutation left behind" but "are my own
edits still there", and the rule in front of it is the one the suites already have: **do not
touch a file while a sweep is reading or writing it.** A sweep over `app/` means the whole
module is off limits until it finishes.

**And two writers of one cached fact is a gap to disclose, not a fix to half-make.** A
membership's `ends_on` is written by the activation, by a cancellation and now by a plan
change -- and a superseding agreement written straight through `POST /memberships/agreements`
records no lifecycle change and moves nothing, so after it the supersession chain says one
thing and the cached date says another: the board follows the new product while the door
expires on the old one. The honest shape is a test that asserts what actually happens with the
reason on it, because closing it is a decision (a lifecycle change on that route, or an end
date the door derives) rather than a line.


**A fixed weekday in a test fixture is a suite that fails one day in seven, and the fix was
already in the file.** MOD-019's default template runs "weekly on Tuesday at 18:00" from
tomorrow, and the booking window is `opens_hours_before`, which defaults to 168. Run on a
Tuesday, the first occurrence is eight days out, the window has not opened, and **twelve tests
across four classes** fail with `booking opens at ...` -- the product being exactly right and
the fixture asking for a session nobody could book yet. `next_weekday` has been in that file
since the module was built and its own docstring says "so a window is always open"; the default
template never used it.

This is the day-of-week form of the time-of-day flake this file already records, and it has the
same worst property: CI sees it on one day in seven and the green runs prove nothing about the
red one. **The expensive part was the attribution** -- the failures arrived in a run that also
carried an unrelated change, and the first instinct was to look at the change. A `git worktree
add /tmp/x HEAD` and the same suite against the same database reproduced them in forty seconds,
which is the cheapest decisive test available and the one to reach for first: *reproduce at HEAD
before diagnosing.*

**And the column the window is read from has no writer.** `sch_capacity_policies
.opens_hours_before` and `closes_minutes_before` have a default, a CHECK and a decision function
that takes both -- and `CapacityPolicyBody` carries neither, so OPS-01-R04's lead time is not
settable through any route and every tenant's booking window is exactly one week. That is this
file's recurring shape in its plainest form, found while fixing a test rather than by reading
the module.


**`npm run verify` is not the web gate, and a backend-shaped diff can still break the browser
suite.** The web CI job runs `audit:ci`, `design:check`, `tokens:check`, `test:foundation`,
`typecheck`, `test` **and** Playwright against a real backend; `verify` is the first six and
`tools/local_ci.sh` says in its own header that it omits the browser suite. A commit that
settled a schema question also deleted two message keys, and two browser tests asserted their
wording -- so `verify`, the full 2,858-test backend suite and every non-Docker CI step were
green on a change that turned `main` red. **The diff looked like SQL**, which is exactly why
the judgement was wrong: what the browser suite asserts is *strings on a page*, so the trigger
for running it is a touched message catalogue or a touched surface, not a touched module.

The rule in front of it is cheap: if the diff touches `web/src/i18n/`, any file under
`web/src/app/`, or any gap note a screen renders, the browser suite runs before the push. And
the second rule is the one this file already states and this commit needed twice over -- **a
test that asserts a gap has to be rewritten the day the gap closes, and the question is whether
it was asserting the finding or a consequence of it.** Both of these asserted the consequence:
the On-trial column's finding was that an empty column is drawn with its reason rather than
hidden, so the honest replacement asserts the column is drawn and **no longer explains
itself** -- an assertion on the absence, which cannot go stale in the direction the original
did.


**A screen specified inside another screen's card is invisible to a scan that keys on one id,
and the index then says the design does not exist.** `ADM-CRM-05` sat in
`screens.generated.json → coverage.unspecified_ids` beside two screens that really are
undrawn -- and its entire design was in the folder: a trial clock, four figures, a sentence and
a button. Batch F titles one card **`ADM-CRM-03 · LEAD PROFILE · ADM-CRM-05 · TRIAL
RUNNING`** -- two screens on one card, each with its own name -- and the extractor's title
pattern is *one or more ids, then the description*, so it took the ids before the first label
and left the second in the prose.

The fix is to collect every `·`-separated segment that is **exactly** an id, which is the shape
of a co-label, rather than every id anywhere in the title: a description may cross-reference
another screen ("ADM-MEM-11 exists because prevention is never perfect") and attributing that
card to the screen it mentions is the opposite error. **Exactly one screen moved**, which is
what made the change surgical rather than a re-reading of the folder -- and the generated
artefact's `--check` is what showed that, because it diffs the whole attribution rather than
the count.

The wider rule: **a coverage index is a claim about the design, and its blind spots are
shaped like the authoring conventions nobody wrote down.** "Unspecified" meant "my parser
found no card titled with this id", and the three screens it named were not the same kind of
thing. Before building to a gap the index reports, grep the design folder for the id.

**`.facts` takes one `<dd>` per `<dt>`, and a second one is a zero-width box.** The class is a
two-column grid whose items are the `dt` and the `dd` themselves, so three children
auto-place as `dt dd / dd …` and the trailing definition landed with **width 0 and height
5,687** -- `display: block`, `visibility: visible`, and a box no reader can see. Playwright
correctly called it hidden, which is how it was found; an assertion on the text alone would
have passed. The membership block already paid for the other half of this rule, where wrapping
each pair in a `<div>` made the div the grid item and put both labels on one row. Two facts
about one subject are two `dt`/`dd` pairs.

**Two fixtures counting the same ledger is the spec-coupling rule one layer down, and the
arithmetic fix re-breaks it.** ADM-CRM-05 needs four entries in a running trial to read `High
ENGAGEMENT`; ADM-RPT-04 pins the shape of a day -- a peak, a peak-tier neighbour beside it, a
middle tier and a quiet morning hour -- and there is exactly one access point in the browser
fixture. So the trialist's four 19:00 visits landed in the attendance chart: the peak moved
from ten to fourteen, the busiest window narrowed from two hours to one because 18:00 stopped
being peak-tier, and the quietest hour's share fell from 30% to 21%. **Six assertions red with
nothing wrong on either screen**, and the fixture's own stated demonstration -- "a peak, a
peak-tier neighbour, two busy hours and one quiet one" -- quietly destroyed.

This file already records the spec version: "a spec that creates a row and a sibling that counts
rows are coupled through the fixture's tenant". The fixture version is worse in one way, because
a spec's own row is visible in the spec and a sibling fixture's rows are not. And the obvious
repair is a trap: subtracting four from the evening seed makes the chart right today and re-breaks
it the day somebody changes the trial to three visits, **with a failure that names the report
rather than the trial**. So the relationship is declared rather than computed -- the chart's
intended evening total is stated once and the trial's own list is subtracted from it, so both
screens stay right whatever its length. **When two fixtures write the same ledger, the shared
figure is a constant one of them owns, not two literals that happen to agree.**

**A sweep whose baseline is red reports every mutation as caught.** Two backends were up on this
machine, 8000 against one database and 8001 against another, and the app defaults to 8000 -- so a
browser sweep run without `VEYRO_API_ORIGIN` drove a page whose fixture had never been seeded into
the database it was reading. Every assertion fails with or without the mutation, and a harness
that looks for a red records that as a catch: the run reported "5/7 caught" and had proved
nothing. Two commands settle it rather than any reasoning -- query each container for the
fixture's own id (`docker exec -i <container> psql -U postgres -d veyro -tAc`), then run the
*baseline* spec and require it green before believing a single number the sweep prints. **This is
the backend-started-by-hand rule with the failure pointed the other way**: there a stale server
made correct code look broken, here it made unproven code look proven, which is the direction
nobody checks.

**A mutation that cannot fail is evidence of nothing, and a client-side gate check is usually
one.** `trial-card-needs-all-three-reads` removed a page's own `mayVisits.allowed &&
mayBookings.allowed` guard before fetching a card composed from three modules. With the guard
gone the page attempts the request, the route refuses it on its own three `permit` calls, the
`.catch` returns null and the card is absent either way -- so the suite stayed green and the
sweep correctly reported UNCAUGHT. The guard is defence in depth: it avoids a request that
would be refused. The control is the route's permits, and a backend test is what proves them.
Deleted with the reason written down, which is the judgement this file already sets for a
constraint subsumed by a sibling -- **ask which reader is unguarded before concluding a guard is
unnecessary, and when the answer is "none", the mutation goes rather than the guard.**

**And "the replacement text is present" has a second cause the harness asserted away.** This
file records that a killed sweep leaves a file mutated and the only trace is a missing anchor,
so `mutate.mjs` reported a stale mutation as NOT RUN with "a previous run was killed before it
restored this file. Put it back with: git checkout". The file was pristine. ADR-0010 D7 had
*retired the protection into the mutation's own form* -- `columnNote` returns null now, which is
exactly what that mutation changed it to -- so the anchor was gone because the code it anchored
on was gone. Both readings leave an identical trace, a `to` that matches and a `from` that does
not, and the message sent me to `git checkout` a file nothing had touched. It names both now.
**A harness's own diagnosis of an absence is a claim like any other**, and the check is the one
this file already prescribes for a leftover: read the diff hunks, and if there are none, the
mutation is stale.

**A pinned count is symmetric whether or not its reason is.** `screen-coverage.test.mjs` pins
the extraction at "167 specified, 3 unspecified" and its comment warned that a *narrowed*
boundary rule would drop the count and fail there rather than be written into the compliance
ledger as a gap in the design. What happened was the opposite: the title rule *widened* -- it now
collects every `·`-separated segment that is exactly an id, so a card titled with two screens
attributes both -- and one screen moved from unspecified to specified. The tripwire fired
correctly and its stated reason covered one direction only. Both literals moved and the comment
now says so; the staleness-proof assertion beside them, that the three counts sum to the
registry's own V1 total, is what holds whatever they are. **A tripwire does not need its reason
to be symmetric to be useful -- either direction brings somebody to the file -- but a reason
written for one direction reads as a defect when the other one fires.**

**A permission case has a different reachability profile from a refusal case, and that is why
one is not a substitute for the other.** This file already says a permission probe is the only
thing that can see a guard refusing too much. ADR-0011's case showed the second half: a case
whose insert must *succeed* runs every constraint, every trigger and every foreign key on the
table, where a refusal case stops at whichever rule answers first. So the four existing refusal
cases on `mem_membership_terms` all name a product the seed does not have and pass anyway --
PostgreSQL evaluates a CHECK before the foreign-key trigger, so the reference is never reached
-- and the permission case failed on exactly that reference. Those four are weak rather than
wrong: with their own constraint dropped they raise `foreign_key_violation`, which their
`WHEN check_violation` handler does not catch, so the suite goes red with a misleading message
rather than passing silently. **Adding a permission case to a table is therefore a test of the
seed as much as of the constraint**, and it is worth doing for that alone.

**And a permission case needs the SQLSTATE in its message, or its own failure is unreadable.**
The first attempt avoided the missing product by moving the seeded row instead, and came back
`CHECK 78 FAILED: ... was refused by ` -- an empty constraint name, because `CONSTRAINT_NAME`
is blank for anything that is not a constraint violation. The cause was 42501,
`insufficient_privilege`: the block runs as a runtime role carrying `UPDATE (status, version)`
only, which is this file's own "run a trigger-branch block as the table owner" rule meeting a
column-scoped grant. `GET STACKED DIAGNOSTICS ... state = RETURNED_SQLSTATE` beside the
constraint name is what turns that into one readable line, and a permission case should report
both rather than assuming a constraint answered.

**A parameter with no caller is the writer-with-no-reader shape at a function's signature, and
this one was in the money path.** `catalog.resolve_price` has carried `store: bool = True`
since MOD-016 was built, with the receipt insert and the coupon redemption both inside its
`if store:` block -- and nothing in the app or the tests had ever passed `store=False`. So the
read `catalog.price.read` is described as granting ("See price books and what a sale would
cost") was implemented, correct, and unreachable, while the only route that could answer it
was the sale. This build's most-repeated finding is a column with a writer and no reader and
its inverse a column with readers and no writer; this is the third form. **The check is the
same one: grep the callers of every optional parameter, and a `bool` that nothing ever flips is
either dead or a feature nobody can use.**

**A conditional fallback in an assertion is a tautology, and it passes loudest when the key is
absent.** `self.assertEqual(body["k"] if "k" in body else expected, expected)` is green
whatever the response contains -- written to be tolerant of a field I was not sure the route
returned, which is exactly the case where the assertion has to fail. The mutation sweep cannot
see it either, because the assertion never fails. **If you do not know whether a response
carries a field, that is the thing to find out before writing the case**; and a defensive
`if key in` inside an `assertEqual` is a signal to go and look rather than a way to be safe.

**A docstring naming a permission the route never charges is caught by the structural check,
which is the argument for having one.** A new listing route was written with its own paragraph
explaining why `catalog.product.read` is the right gate for it, and no `permit` call at all.
`GateCoverageTests` reads `main.py` with `ast` and requires every route to ask the gate, scope
itself to the caller's own identity, or appear in `UNGATED` with a written reason -- so the
omission was a red suite within a minute. That is MOD-012's "a docstring is not an
attribution" met by a check rather than by a reviewer, and the second half of the same run
found the three new routes missing from the behavioural sweep, which is the other direction:
a route the sweep never calls is a route nothing proves is gated.

**Pydantic ignores an unknown field by default, so an absence in a request body is a
convention rather than a control.** A quote body is `ResolvePriceBody` minus four fields that
are sale decisions, and a caller sending `coupon_code` to it got a figure with the coupon *not*
applied -- a plausible number, which is worse than a refusal, because a till showing it while
believing the code had been taken has no way to notice. `model_config = ConfigDict(extra=
"forbid")` is what makes the four missing fields mean something; it is the only body in this
application that sets it, and the reason is written beside it. **Where a body's distinguishing
feature is what it does *not* accept, the default is wrong.**

**A test harness that does not inherit another's helpers will invent its body shapes, and
every invention is a 422.** A conversion-quote fixture built its own price book with
`book_key` and `unit_amount_minor`; the real fields are `price_book_key`, `display_name`,
`effective_from` and `amount_minor`, and seven tests failed identically before the cause was
obvious. Worse, the second attempt built a *second* price book beside the one the existing
membership helper already writes -- two books matching one variant at the same priority, which
makes the planner choose the figure, MOD-018's unordered-lookup finding reproduced in a
fixture. **Read the helper that already does it: `membership_product` writes the product, an
active book, a live price and the publication, because publishing refuses a product with no
live price and so has to.**

**A `WHEN raise_exception` handler swallows the case's own failure message, and then the case
can never fail.** A trigger that refuses with `RAISE EXCEPTION` is caught by
`WHEN raise_exception`, and so is the `RAISE EXCEPTION 'CHECK nn FAILED: ...'` the case raises
when the trigger does *not* fire -- so `WHEN raise_exception THEN probe := probe + 1` counts
the failure as a pass. Two trigger cases were written that way, and the sweep found them by
dropping the trigger and watching the suite stay green. The handler has to read
`MESSAGE_TEXT` and re-raise anything starting `CHECK nn FAILED`; a constraint case does not
have this problem, because `check_violation` and `raise_exception` are different conditions.

**A case whose row does not exist proves nothing, and an UPDATE is where that hides.** This
file records the INSERT form -- a case naming a parent the seed lacks is answered by the
foreign key. The UPDATE form is quieter: `UPDATE ... WHERE lead_id = '...'` against a table
with no matching row **succeeds**, affecting zero rows, so a case written to be refused passes
and reports a missing constraint that was there all along. Four interest cases were written
against a seed that has no interests. The fix is for the case to insert what it exercises, and
the tell is a case that passes the moment it is written.

**A mutation harness copied from another module keeps that module's check number.** The
lost-lead sweep was copied from MOD-017's and kept `wanted = entry[2] if len(entry) > 2 else
"CHECK 78"`, so twelve mutations this module's own CHECK 115 caught were reported MUTERR --
the harness manufacturing the gaps it then reports, which is the same shape as a generated
mutation that changes nothing. **A sweep's default is a per-module fact**, and the tell is a
run where almost everything is MUTERR and the message names a check from a different module.

**A guard whose precondition the test does not meet is invisible to the test.** `is_going_cold`
grew a `lost_at is not None: return False` clause, and the test asserted `going_cold` is false
for a lead marked lost -- which it was, because the lead had been created a second earlier and
nothing created a second ago is going cold. The mutation that deletes the guard came back
uncaught. The pair is what makes it evidence: at the same age, a *live* lead is cold, so the
test asks both from a later moment. **Ask of any "this is false" assertion what else would make
it false.**

**Two layers that raise the same exception type are told apart only by the message.** A service
checked its own vocabulary before writing, and the column's CHECK refuses the same value -- and
the handler turns `CheckViolation` into the same `InvalidRequest` the service raises. So a test
asserting `assertRaises(InvalidRequest)` passed with the service check disabled, and the
mutation was uncaught. What actually differs is what the caller is told: the four admissible
reasons, or the name of a constraint they cannot look up. **Where a check is defence in depth
behind an equivalent one, the assertion is on the message** -- or the check is redundant and
should go.

**A read that filters on a new nullable column has to be found in every caller, and one of
them will be the write.** Adding a withdrawal to an insert-only table meant `read_lead` had to
list live interests only -- which was obvious -- and `record_interests`' "what is already
held" read had to as well, which was not: counting withdrawn rows as held means a withdrawn
interest **blocks its own return**, so a lead who changed their mind back is told "already
recorded" and the profile keeps showing one interest. The remedy the column exists to provide,
defeated by the function that writes it. Found by the test written for the withdrawal, which
is the argument for testing the round trip rather than the act.


**A plural message's `count` must be the number, not a formatted one — and the branch that
proves it is the one no fixture reaches.** `fill` picks the CLDR form from `values.count` and
*then* formats it, so a call site passing `formatInteger(...)` passes a string and the page
answers 500 on every render of that branch. Three sites shipped that way and **two of them were
in screens already in production use**: ADM-MEM-10's and ADM-CRM-04's "Held by N other records"
line, reachable the moment one phone number is held by two people — which is the family line
`AUTO_MERGE_THRESHOLD = None` exists for and the whole reason those screens have an escape.
Neither had ever rendered, because the fixture seeded two *different* numbers.

Three things were needed and none alone is enough. The call sites pass the number. The
per-plural-form sweep in `tests/component/i18n.test.ts` now keeps each entry's *expression*
beside its name and refuses a `count` containing `formatInteger` — exact rather than a guess at
"numeric", because that is the only number-to-string path in the app — and it is
mutation-proven, since a sweep that cannot fail is the thing it exists to prevent. And the
fixture seeds one number held by two people, so the line renders in a browser. **The general
shape: when a runtime check is strict, the call sites it guards need a static sweep, because
the ones it would catch are exactly the branches nothing renders.**

**A `&&` chain whose earlier step fails leaves the previous run's log on disk.**
`npm run build > log && npx playwright test > log` — when the build fails on a type error, the
second redirect never happens, so `tail log` reports the *earlier* run, complete and plausible
and about code that no longer exists. Seven failures were read that way for a run that never
started. The tells are cheap and both were available: `web/.next/BUILD_ID` is absent after a
failed build, and the log's mtime predates the command. This is the stale-artefact rule this
file already records for `tail -F` on an old log, arriving through a shell operator instead:
**check the exit code of the step that was supposed to produce the artefact, and give each run
its own filename.**

**Counting elements inside a design-system component couples a screen's test to the
component's internals.** `form.locator("input, select")` found six where a reader sees two: the
acknowledgement travels as a hidden input, React's form action adds its own, and the field
shell renders more. The property is "the canvas's two fields and nothing else", which is
`getByRole("textbox")` and `getByRole("combobox")` — what a reader can type into. Same family
as the positional-cell and attribute-order traps: the number is a coincidence of the current
markup, and a shell change breaks the assertion for a reason that has nothing to do with the
screen.


**A guard whose siblings already cover every reachable case is a guard with no case, and the
sweep is the only thing that distinguishes it from one with a missing case.** MOD-019's
conflict dry run came back 4 of 15 caught, and the eleven split three ways, which is the
distinction worth having a name for:

- **Three were subsumed and were deleted.** `recurrence.check_rule` beside a `_parse_rule`
  that already calls it; a request body's `le=` beside the service's own ceiling, so no route
  could reach the service guard at all; and a filter skipping the conflicting coach, which the
  busy set, the rota check and the location filter each already exclude by every route a staff
  conflict can arrive by. For each, no case could be written because there is none.
- **Eight were cases that did not exist.** A coach at another site, a coach whose rota refuses
  the hour, a coach busy on *another* class, five coaches for the bound, equipment held and
  equipment elsewhere. Every one needed a fixture the first pass did not build.
- **And two needed a different assertion rather than a different fixture.** A count cannot see
  a walk that started in the past, because eight of the past is still eight -- so the read
  now returns the dates it examined and the test asserts those. And a margin mutation is
  invisible unless the *proposal* carries the margins: the existing hold is wide either way,
  so the case has to be a proposal whose own setup window is what overlaps.

**The tell for each is different and all three look identical in the sweep's output.** Ask, in
order: which reader is unguarded (none → delete it); which input would reach this guard alone
(none in the fixture → build it); and would the assertion I have change if the mutation
applied (no → assert the thing that moves). The third is the one that produces a green test
over a dead protection, which is this file's oldest subject.

**And a trigger keyed on a value nothing produces is the same defect in new code.** That dry
run offered alternatives only when a clash was `"busy"`, and `conflicts.py` raises
`double_booked`, `over_capacity` and `elsewhere` -- so the suggestion list was always empty.
MOD-012's board shipped exactly this (`live_critical`, where the column holds `critical`), and
in both cases the cause was taking the *prose* for the stored value. The tests caught it in
minutes because the list was asserted; a screen reading an empty list would have shown nothing
and looked like a tenant with no spare coaches.


**A blanket reason covering several screens is wrong about one of them for a reason the blanket
cannot express, and MOD-019's surface was wrong twice.** That gap bullet said all five
scheduling writes had no form because each is a stepped-up permission. The first correction was
that `scheduling.availability.write` is not one -- `configuration` with no financial class --
so ADM-SCH-04's "Add an exception" had been buildable all along. The second is the opposite
shape: ADM-SCH-03's three permissions *are* stepped-up and that was never the obstacle either,
because a step-up offered before the button is what two other screens already do. What was
actually in the way was a **read**: `preview_publish` takes a `template_id` and the create
screen has no template yet.

So the rule has a second clause. The first is the one already here: re-derive a blanket reason
per screen, because it is a claim about each of them. The second is sharper -- **when a screen's
reason names the write, check whether the read exists**. A form is a read and a write, and this
build's gap notes name the write every time because that is the half a permission has a name
for.

**And a component's hidden control bites every spec that drives it.** `ChoiceChips` draws the
chip on its label and hides the input, so `.check()` waits for an element that is never visible
and times out at thirty seconds -- which looks like a product defect and is a locator. Twice in
one session, on two screens. The click a reader makes is on the face: `.ds-choice-chip`.
`{ force: true }` would skip the actionability check and hide real problems, which is the wrong
remedy for the same symptom.

**A CI timeout is a red `main` that teaches a reader to skim past CI, so it is worth its own
note.** The foundation job's `timeout-minutes: 25` cut the run in its *last* step -- the
rollback rehearsal -- after the isolation suite, both linters, the backend tests, the container
build and its smoke had all passed. The run read `cancelled` rather than `failed`, on a commit
with nothing wrong in it, and the cause was that "Backend focused tests" had reached 22.5
minutes. The number is the symptom; `support.py` already names the cause -- "the HTTP path
spends a dozen scrypt hashes per tenant and that is most of the suite's wall-clock" -- and
`hash_secret` already takes its parameters while `verify_secret` reads them from the stored
record, so a lower cost factor in `local` is self-consistent and is the real fix. Headroom
first, so the gate works; the cost per tenant is its own change. **Check the job's duration
trend when a suite grows, not only its result.**


**Lowering a cost in a test means finding every reader of the constant, and one of them turns
the saving into a loss.** The scrypt work factor is settable now because half the backend
suite's wall-clock was hashing -- measured, 147 calls and 5.2 seconds of 10.2 in one file --
and the obvious change (a module-level factor that `hash_secret` reads) is not enough on its
own. `needs_rehash` compared the stored parameters against the *constant*, so every credential
the suite made would have read as weak: every successful password verification would revoke
its row and hash a replacement, which is an extra hash per login and a credential table
churning on every test. The question it asks is "weaker than what *this* process would store",
which is the effective parameters, not the deployed ones.

**The tell is a reader that compares against a default rather than against a value.** Grep the
constant, not the function: `hash_secret` was the obvious caller and `needs_rehash` was the one
that mattered.

**Two refusals, because one of them is a string in an environment.**
`config.load_settings` refuses the setting outside `local` and `secrets.use_cost_log2` bounds
it again -- and the band's floor lives in the crypto module rather than as a second pair of
literals in the config, which is why `config.py` imports it. The upper bound is deliberate
too: a knob that could *raise* the work factor is a setting that can make a tenant's logins
time out, so admitting one would give it a second purpose and a second argument.

**And a measurement before the change is what made the decision, not after.** Timing
`hash_secret` at three factors took one command and showed 33ms against 2ms; counting the calls
in one file took another and showed 51% of its wall-clock. This repository's own rule --
"measure what the mutation changes, do not reason about it" -- applies as much to a performance
claim as to a CSS one, and a suite-wide refactor justified by a guess is the expensive kind of
mistake.


**A client component that imports a module reaching `next/headers` breaks the whole app's
build — and the third instance was a *mixed* module rather than a reader.** The account page
and the cash screen both record this for a `*-reads` file; FD-07 hit it through
`@/lib/people.ts`, which holds `MASK` and `isWithheld` beside an `import { api }` at the top.
So importing a three-line pure predicate from it put `next/headers` in a client bundle, with
`typecheck` and `lint` both green: **`build` is the only step that sees it**, and the tell is an
error naming a chain of `[Client Component Browser]` imports that does not mention
`next/headers` at all. The marker's home is now a module that imports nothing, re-exported from
`people.ts` so the thirteen server pages are untouched and there is one definition. **The rule
to carry is wider than the fix**: before importing anything into a module a client component
reaches, read the *top* of the file, not its exports — a pure name in an impure module is still
impure to a bundler.

**A mutation against a hidden form field is invisible unless a test presses the form, so that
decision belongs in a library.** FD-07's open sends the safe on a funded open and nothing on a
handover -- the command refuses the field there -- and the conditional was inline in the JSX,
twice. The browser mutation that sent the safe on both came back uncaught: the spec asserts the
label and the button and deliberately never presses, because an open is state it cannot create.
Pressing is not the fix. `accountsFor` and `nameOf` are, and the extraction removed a duplicated
conditional and an inline closure as well. **A hidden input's value is a decision about what the
request says**, so it is testable in the same place every other decision is; asserting it
through the DOM would be the counting-a-component's-internals trap from the other side.

**A spec's own provisioning encodes an assumption about the product, and a model change
invalidates it.** ADM-PAY-09's cash spec opened its drawer with a float drawn from the safe --
correct for as long as every open was a funded one. After FD-07, that drawer still holds what
the close counted, so the *second* run's open is a handover and the safe is refused: the spec
took its "a previous run was interrupted" branch, matched no drawer and failed. Two findings in
one: the 409 handler conflated "a session is already open" with "the float was refused", and the
`97.50` literal was right only while the drawer was always funded with exactly 100.00. It reads
`/ledger/drawers` now and opens the way a desk does. **Found by running the suite twice**, which
is the rule this file already states for budgets and one-way state, here reaching a spec's setup
rather than its assertions.

**A test that reads a seeded minor-unit figure as a displayed one is the money-exponent defect
from the other side.** 17,500 fils is JOD **17.50**: the currency is stored with three decimals
and shown with two, which is the one conflation `@/lib/cash` exists to prevent. A browser
assertion of `175.00` against a fixture seeded at `17_500` fails for the right reason and reads
like a product defect — and the sibling assertion that typed `170.00` against a 17.50 drawer then
expected "Short by" when it was over. Take the displayed figure from the fixture's own minor
units, or assert a difference rather than a total.

**An `&&` chain whose build step fails can leave *no* log, which is the honest version of the
stale-log trap.** `npm run build > log && npx playwright test > log2` with a failing build never
creates `log2`, so a `grep` over it reports "No such file or directory" — loud, unlike the
recorded case where `tail` read the previous run's complete and plausible output. Both have the
same cause and the same check: look at the exit code of the step that was supposed to produce
the artefact, and at `web/.next/BUILD_ID`.

**A nav entry naming an icon that does not exist throws from the layout, and the first failure
you see is the auth setup.** `Icon` fails closed on an unknown name -- correctly, because a
silently missing icon is a rail item with a hole in it -- so `icon: "finance"` took down every
page including sign-in, and the browser suite reported the setup step failing rather than the
nav. The valid names are a closed set in `components/ds/icon.tsx`; read it rather than guessing
from the group name.


**A flake that fires for a fifth of the day leaves no mark on the fix for its siblings, so
the instrument is a static check rather than a better assertion.** `VisitTests`' own docstring
records two tests corrected from `datetime.now(UTC).date()` to the club's zone, and says in as
many words that CI would fail too because "the frame that matters is neither the runner's nor
UTC but the *club's*". A third test was written afterwards, missed it, and turned `main` red at
21:34 UTC with `visits_between` reading 2 of 3 — the entry seeded at `now()` was bucketed on the
club's own next day and fell outside a window whose end came from UTC. Every local run of that
test had been green, and always would be outside three hours a day.

**It is not a blanket ban, and the discriminator is what makes the guard honest.** Three tests
in that same class take `today` from UTC and are correct: one counts a *refused* presentation
(zero either way), one asserts a 422 for a half-stated window (the date is irrelevant), and one
asserts zero for a member with no entries. The unsafe thing is the *combination* — seeding an
entry, and asserting a count against a window built from a UTC date — so that is what
`VisitDateFrameTests` checks. A blanket rule would have forced three tests into a zone they do
not care about and buried the reason the fourth needs it.

**And it has to match the syntax tree, not the source text.** The first version flagged the
multi-zone regression test, whose *docstring* quotes `datetime.now(UTC).date()` while its code
never calls it — the same false positive `test_migration_shape` paid for with a banned
expression quoted in a comment. `ast` is precise here and the check asserts both directions: the
offending shape is caught, and a docstring that merely mentions it is not. Mutation-proven by
putting the UTC date back and watching it fire, and its three conditions are asserted reachable
before the sweep is believed, because a structural check that passes vacuously is the thing it
exists to prevent.


**A splice whose end anchor is absent falls through to the next one and eats everything
between, and a check that validates *claims* cannot see it.** Retiring FD-02's
`design:coverage` entry used `s.index('  "FD-07"', start)` as the end — and FD-07 had already
been retired to a *comment*, so there was no such key: the fallback anchor was `"FD-09"`, and
the splice deleted FD-07's own "was here and is built" note on the way. `design:coverage`
passed, because a comment is not one of the three shapes it checks; the full gate passed for
the same reason. It was found by reading `git diff | grep '^-[^-]'` afterwards, which is the
check this file already prescribes for a different cause.

Two rules, and the second is the general one. **Assert the end anchor exists before splicing to
it**, exactly as the text anchors are asserted — `s.index` raising is better than a silent
fallback, and a fallback anchor is the thing that makes it silent. And **a gate that validates
structured claims is blind to the prose beside them**, which this repository already records
for a backlog reason whose sentence went stale while its module id stayed right; here the prose
was not stale but deleted, and the only instrument that saw it was the diff.

**And a splice script that writes once at the end loses every substitution that worked when a
later one raises.** This file already records it — "several Python splice scripts asserted after
a partial edit and wrote nothing" — and I hit it again without noticing, because the retry
succeeded: a four-substitution `CLAUDE.md` script raised on its fourth, so the MOD-018 handover
bullet, the built-screen list and the Front Desk list were all discarded, and the fix-up script
only re-did the fourth. The most consequential documentation of that session's largest finding
was absent from `CLAUDE.md` for three commits, and nothing could see it: a gate checks
structured claims and prose is not one.

**One `write_text` per substitution**, each reporting whether its anchor matched, so a skip is
visible and never silent. The tell when it has happened is a `grep -c` for the new text coming
back `0` after a script that printed success — so grep for what was added rather than trusting
the exit code, which is also the cheapest check after any splice.

**A fourth form of the ill-formed mutation: one that names a symbol which does not exist.** A
sweep against MOD-017's price-impact read replaced `_LIVE_MEMBERSHIP` with `_ANY_MEMBERSHIP` to
prove the live predicate bites — and there is no such constant, so the suite failed with a
`NameError` and the mutation was reported CAUGHT for a reason that had nothing to do with the
count it was about. This file already records three forms (a statement the planner refuses, a
prefix mutation on a disjunction, a `RAISE` kept for the count and fired unconditionally); this
one is the easiest to write and the hardest to see, because the report says what you hoped.
**A replacement that introduces a name must be checked against the module**, and the honest
form here spells the predicate out inline with the same placeholder count.

**And a composite CTE's placeholder count is the sum of its parts, which a reader will
undercount.** `_walk_from(_LIVE_MEMBERSHIP)` takes *three* dates, not two: the seed predicate
has two and `_SUPERSESSION_STEP` carries a third for the `a.starts_on <= %s` that stops the walk
at an agreement which has not begun. psycopg says "the query has 7 placeholders but 6 parameters
were passed", which is clear — but only at runtime, so a read with no test fails in front of a
caller. Count the helper's own `%s` as well as the predicate's.

**A declared state the schema forbids, sitting beside a server fact a hand-written type
dropped.** `repriceable`'s third branch was `price_book_id === ""` — a NOT NULL uuid, so
`list_prices` cannot return it, which makes it this build's "a declared value nothing writes" in
a surface. What that branch was *reaching for* was already on the wire: that read has returned
`price_book_status` and `price_book_priority` since MOD-016 was built, and the hand-written
`PriceRow` declared neither, so the second of the three conditions that decide a sale's price
was thrown away. Both halves of the recurring finding in one place, and each hid the other: the
branch looked like the state was handled, and the missing fields meant the state that can
actually happen had nothing to detect it with.

**The state that was reachable is the one that matters, which is how to tell them apart.**
`create_price` never reads the book's status, so a price written into a draft or retired book is
accepted by the server and resolved by no sale — a price change that reports success and charges
nobody. So the question to ask of a surface branch is not "is this well-formed" but "which input
produces it", and when the answer is "none", ask what the branch was *for*: the answer is
usually a fact the read already carries.

**A case catches a weakening only if the two rules disagree on it, and that applies to an
ordering as much as to a CHECK.** `livePrices` compares an active book, then the priority, then
the book key. The case for the priority comparison used a high-priority book whose key also
sorted first, so disabling priority gave the same answer and the mutation came back uncaught —
correctly. The case that bites puts the keys and the priorities in opposite directions. A sort
has no constraint name to anchor a case to, so the only thing that finds this is the sweep.

**And the ordering has to be the server's, not a plausible one.** `choose_book`'s docstring says
why its last key is the book key: *"which is unique, so there is never a tie the planner gets to
break. A resolver whose answer depended on row order would fail the requirement in the way
nobody notices until two tills disagree."* The first version of `livePrices` ended on
`effective_from`, which ties for two books priced from the same date — the ordinary result of
adding a seasonal book beside a standing one, and what the e2e fixture happens to have. So the
answer came back to iteration order in the one place this build has a written rule against it.
Borrow the comparison from the function that owns it; a second ordering is a figure one screen
shows and the till disagrees with.

**An axe scan without the suite's tags runs a wider rule set and reports the app shell.** Every
other spec here calls `.withTags(["wcag2a","wcag2aa","wcag21a","wcag21aa"])`; a bare `analyze()`
adds axe's *best-practice* set, whose `region` rule ("all page content is contained by
landmarks") fired 127 times on the chrome — the language switch, the theme buttons, the avatar —
which sits above the landmarks by design. The finding reads exactly like a page-level
accessibility defect and is a convention mismatch. Matching the convention is right here; saying
in the spec *why* it was narrowed is what stops the next reader assuming it was narrowed to hide
something.

**A spec that asserts a stepped-up button becomes enabled is asserting the wrong end of the
sequence.** ADM-MSH-09's save is held by two different kinds of thing: five field-level refusals
a reader can clear, and `catalog.price.write` being financial class, which an AAL-1 session
cannot clear at all. Filling every field correctly and expecting `toBeEnabled` fails against a
page that is working. The honest assertion is that every field message is gone *and* the
remaining hold is the step-up the page offers — which is also the only shape a spec can take
without spending a recovery code per run.

**"One `write_text` per substitution" paid again, and the failure was invisible.** A four-part
script changing `main.py` asserted on its third substitution and wrote nothing, so the route's
`locale` parameter never landed — and the next two scripts in the same message succeeded, so the
output read as progress. `mypy` caught it (`Name "locale" is not defined`); nothing else would
have, because the docstring describing the parameter *was* written by a later script. The rule is
already in this file; the new part is that a partial failure can leave the **documentation** of a
change in place and the change itself absent, which is the one combination a reader cannot spot.

**A model with a consumer and no producer reads as complete from every direction.** This file
records "a column implying a control nobody implemented" and "a declared value nothing writes"
many times over. MOD-017 had the inverse and it hid for the whole life of the module:
`mem_entitlement_policies` declared COM-01-R03's nine kinds of right with carryover and a
reservation TTL, `mem_entitlement_grants` carried everything a plan needs to hand one out
including `source_kind = 'membership'`, the balance read worked, the reservation was atomic and
under a lock — and `grep -rn 'source_kind="membership"' backend/` returned three hits, all three
in a test file. One edge was missing, between a plan and the rights it sells, and **nothing in
the schema could say so**: every table had a writer, every constraint was right, every test
passed. The question that finds it is not "does this column have a writer" but "does this
*model* have a producer in the product" — and the grep is per `source_kind`, per status value,
per declared kind, not per table.

**A probe that depends on a sibling's committed state depends on the sibling passing.** Two
trigger probes in CHECK 78b re-dated a row an earlier case had withdrawn — and a PL/pgSQL
exception handler rolls back to the start of *its own* block, so when that earlier case failed
under a mutation the withdrawal was undone, both UPDATEs set `withdrawn_at` with no actor, and
the attribution CHECK answered instead of the trigger. The block then died on an unhandled
`check_violation` and the sweep reported **ten** mutations as MUTERR for one ordering. Each
probe now inserts and withdraws its own row. The general form is wider than triggers: a probe
that reads state another probe wrote is a probe whose result is conditional on that probe, and
the sweep is the only thing that makes the dependency visible.

**And a refusal case that *succeeds* under its mutation collides with the next one.** The same
block's five insert-refusal cases all targeted one (variant, policy, scope) slot. With the
quantity bound dropped, the zero-quantity case inserts — which is the behaviour the case exists
to catch — and then the next successful insert violates the live unique index, raising a
`unique_violation` no handler caught. One policy per insert-case is the fix. The tell in the
sweep output is a run of MUTERRs whose first entry is a drop of something unrelated to the
index.

**Arithmetic added to protect a property the ledger already guarantees is a defect, not
belt-and-braces.** `entitlements.SIGNS` makes `reserve` negative, so a grant's balance is
already net of what is held. `_revoke_plan_grants` subtracted the held quantity *again* to
protect the booking — and on a grant with one of two credits reserved it wrote off nothing,
leaving a **revoked** grant carrying a balance of one, which is precisely what `_revoke_grants`'
own comment says its movement exists to prevent: "the balance afterwards is zero by arithmetic
rather than by the status column saying so". The property held by construction all along.
**Found by the test written for the disclosure**, which is the argument for asserting the figure
a screen shows rather than the status a row carries.

**`fill` is strict in both directions, so a function returning a message key without its values
pushes a contract onto every call site.** `timingMessage` returned one of three keys and the
component passed `{on}` to all three — and "Takes effect today." has no `{on}`, which is an
error rather than an ignored extra: a 500 on the member's record. This is the plural-`count`
finding's sibling and it has the same remedy: return the key *and* the values, so the one
function that chose the message also owns what it needs.

**A required `correlation_id` the client does not send reaches a screen as an absence.** `api`
sets one on a body it builds and on the gate's own query and nowhere else, so a read whose route
declares `correlation_id: str` answers 422 — and a surface that catches a failed read to render
a block conditionally then renders *nothing*, with no message saying why. The picker appeared,
the consequence did not, and every assertion about the picker passed. When a new route takes a
correlation id, the read has to send it; when a read is wrapped in a `catch`, the absence it
produces is indistinguishable from "there is nothing to show".

**In a `switch`, a mutation that adds a clause is a no-op or a syntax error -- the mutation of
a branch is its own answer.** Both of this session's first two mutations against a four-verdict
decision were ill-formed in that one way, and the two failures look nothing alike: a duplicate
`case` label is *unreachable*, because the first match wins, so the sweep reported UNCAUGHT and
read as a protection with no evidence; a second `default:` makes the file unparseable, so vitest
collected nothing and printed `Tests  no tests`, which reads as a gap the harness created. The
fifth distinct form of "a mutation that changes nothing is not evidence" here, and the cheapest
guard is the shape rather than a check: **mutate the value a branch returns, never the clauses
around it.**

**`veyro-product-experience-design/project/veyro-screen.js` is the prototype and the
`Veyro V1 Batch *.dc.html` files are the deliverable, and the two differ on *which fields
exist*.** This file already records the softer version -- ADM-CRM-05's drawn fourth cell is
`ENGAGEMENT` while the prototype calls it `CONVERSION LIKELIHOOD`, and "the drawn canvas is the
deliverable". The harder version cost three wrong claims in twenty minutes while sizing
ADM-SET-07, each written down and nearly committed:

- The prototype's ADM-SET-07 draws six fields including **"Week starts · Saturday"**. The batch
  canvas is titled LOCALIZATION and has three concerns -- languages offered, numerals, month
  names -- and **no week field at all**. I had already put "the first day of the week is a
  tenant setting whose value is Saturday" into a backlog entry, two docstrings and `CLAUDE.md`
  before checking the authority.
- The prototype's ADM-SCH-04 draws a vertical list of seven rows, Monday to Sunday. The batch
  canvas is a seven-column week grid -- which is what this build renders -- so the built screen
  was right and my "correction" to it was wrong.
- Both of those were me *correcting* an earlier claim that was also wrong: the original
  docstring said "ADM-SCH-04 draws its columns SUN-SAT", and that canvas templates its day
  labels from `{{ days }}` and draws no literal day. The order it produced is right for a
  different canvas's reason -- ADM-SCH-03's `REPEATS · S M T W Th F S`.

**So: read the batch file for anything load-bearing, and read the prototype only where the
batch is silent -- never for whether a field exists.** `grep -rl '<ID>' veyro-product-
experience-design/` names every file that mentions a screen; the batch is the one whose name
begins "Veyro V1 Batch". And the wider rule, which is this build's own and was the thing I kept
skipping: **a citation is a claim.** The evidence a decision names has to be checked exactly as
hard as the decision, and a decision that is right for the wrong reason will be "corrected" into
a wrong one by the next reader -- who, here, was me.

**"Does this table carry a location" is not "can this be scoped", and I answered the first
twice while believing I had answered the second.** Sizing ADM-CC-02 I checked
`information_schema.columns` for `location_id` across the Command Center's five entities,
found it on `acc_zones` and `sch_sessions` only, and concluded a membership cannot be bounded
to a club -- then wrote that the money panels are therefore tenant-wide facts a club manager
should be refused. Both halves were wrong. `ppl_tenant_profiles.location_id` is "where in the
hierarchy this person belongs", one join away through the module that owns people, and FD-02's
lookup already reads it and calls it "the club, which is a filter on this module and the only
one it has". A second grep missed it as well, because the join and the projection sit on
different lines.

**The shape is the inverse of this build's most-repeated finding.** A column with a writer and
no reader is found by grepping the writer; a *relation* that lives in another module is found
only by asking which module owns the fact. So before concluding a figure cannot be scoped,
name the entity that owns the scope and look there -- not at the table the read starts from.
And the nullability is part of the answer rather than an afterthought: that column is optional
by design, "because a person may be known to the tenant before anybody decides which location
they belong to", so a club-bounded count excludes the unassigned and a board has to say so
rather than imply it.

**A boolean that answers "is this withheld" is not an answer to "what can the reader do about
it", and a shared sentence makes the second one wrong everywhere at once.** This file already
records the `reachable` version -- one field answering two questions is right only while the
two agree. The surface version is worse because it scales: sixteen marker sites across
thirteen files rendered one key for a masked name, and that key named a remedy -- a step-up -- which is
right for a reader holding the grant at too low an assurance and wrong for one who does not
hold it at all. The component was *built* for the distinction and its docstring names two
doors; the case it did not name is the reader who holds nothing, and every site passed the
first key to all three. **The question to ask of any "this is withheld / refused / unavailable"
marker is not whether it is accurate but whether the remedy beside it is one this reader has.**

Three corollaries, all paid here:

- **A grep for an attribute literal misses the same key inside an expression.** The sweep that
  found the sites searched `reason="member.withheldIdentity"` and came back clean while three
  of them spelled it `reason={cond ? ... : "member.withheldIdentity"}`. Search for the *value*,
  not the attribute form -- and in a repository where a design-system component takes a message
  key as a prop, that value is the only thing every site has in common.
- **The marker and the offer are two controls, and fixing one leaves the other.** Seven screens
  rendered the step-up link beside the sentence, each on its own condition, so the corrected
  sentence sat above a link that still cost a recovery code for nothing. **The count is what
  found both**: a browser assertion of `[title*="stronger sign-in"]` expecting 0 and receiving
  2, after an earlier one expecting 0 and receiving 5 -- one element is a banner and five are
  rows, so the number says which layer you have not fixed yet.
- **A remedy that is never available must not be offered at all.** The member record marked a
  contact point with the identity sentence, and `member.profile.read` is routine -- so a
  stronger sign-in could *never* lift that mask and the sentence was false in every case rather
  than in some. A marker shared across classes inherits the wrong remedy for all but one.
- **A fix that does not clear the symptom is a diagnosis to doubt.** I read five markers as the
  mask resolving at the tenant-wide default scope, changed the resolution to the caller's own
  scopes, rebuilt, and five markers remained -- because the cause was the missing permission.
  What settled it was reading the fixture's role and the permission's action class, which is
  two greps and needs no test at all. And the count was the tell I ignored: the banner is one
  element and five meant the rows, so the thing I had fixed was not the thing being counted.

**And a backend started before the edit is what made that loop longer than it needed to be.**
The process was 40 minutes older than `main.py`, with no `--reload`, so the run that reported
the five markers was testing code without the change -- which this file already records for
routes and for a registry, met again for a service function. `ps -o lstart=` against the file's
mtime is the check, and it costs one command.

**`nohup cmd &` inside a backgrounded tool call is not a background run.** The harness reports
the *wrapper's* exit, so a browser suite that was torn down after 30 of 711 tests came back
"completed (exit code 0)" with no summary in its log. The tells were both there and neither is
an error: a log whose last line is an ordinary pass, and an announced test count far above the
number of result lines. Let the harness own the process, and check that a suite log ends in a
tally before reading it as a result.

**A `psql` session as `postgres` bypasses RLS, so a tenant filter must be an explicit
`WHERE`.** A diagnostic query that set `app.tenant_id` and relied on the policy returned every
tenant's rows — thousands of them from the backend suite's own tenants — because a superuser is
exempt from row-level security entirely. The isolation suite never hits this because it
`SET LOCAL ROLE` to a runtime role first. For an ad-hoc read, name the tenant in the predicate.

**`None` and a default-constructed value are two different questions, and a helper that
answers only the second makes a new branch silently inert.** ADR-0014 gave `authz.check` a
"may this caller do this *anywhere*" path, keyed on the `scope` argument being absent — and
both `/authz/check` and `/authz/checks` passed `resolve_scope(None, None)`, which returns the
tenant-wide `Scope()` because that is the right answer for the permission simulator. So the
new branch never ran for the gate every surface in this app reads: `GET /staff` answered a
club manager "yes" while the rail answered "no", and the page rendered "Not permitted" over a
read that would have worked. **A screen refusing while its own read allows is the worse half
of the two**, and nothing in 46 authorization tests could see it, because no test had ever
asked the gate as a scoped caller. The guard is a test that asks `/authz/check` *and*
`/authz/checks` as one, plus a mutation that puts the unconditional resolve back.

**When a gate learns to say yes to a caller it used to refuse, every reader of `allowed` is a
page that may now render over a read that refuses.** The server's `permit` got an opt-in — a
route accepts a scoped caller only by passing `scoped=True` — and the client's `gate()` needed
the same information or the two layers disagree: `/members` drew its heading and its list read
answered 403, showing neither the rows nor the refusal. The remedy is to narrow the *client's*
`allowed` to the old meaning and carry the new one beside it as `allowed_anywhere`, so every
page behaves exactly as it did and the one page that filters opts in. That is the same
"default is what this build already did" reasoning as ADR-0011's billing anchor, applied to a
boolean that a hundred call sites read.

**A flag a route sets is a declaration, so check it with `ast`.** `permit(..., scoped=True)`
says "this route is safe for a scoped caller", and the only thing that makes it safe is
filtering on `gate.scopes`. A route that set the flag and ignored the answer would return every
club's rows to a caller who holds the action at one — the exact failure the opt-in exists to
prevent, arriving through the opt-in. `GateCoverageTests` requires a route passing it to
mention `scopes` in its body, **and a second test requires that at least one route does**,
because a structural check asserting an empty list proves nothing until it can see its
subjects at all.

**A 200 is the weaker of the two available assertions about a boundary.** The first version of
the club-manager test asserted that the staff list answered rather than refusing — which is
the finding, and says nothing about the bound. Two staff profiles, one at the caller's club and
one elsewhere, with the admin seeing both and the club manager seeing one, is what makes the
absence the gate's answer rather than a narrower query the test happened to send.

**And two of that sweep's mutations needed cases that did not exist, both for the same
reason.** Removing the permission filter from `scopes_holding` and removing the liveness check
both left the answer unchanged for a caller with *one* role at *one* club — the two rules agree
on that input. The cases that bite are a second role at a second club granting something else,
and a revoked assignment at a third: the shapes where the rules disagree. This is "a case
catches a weakening only if the two rules disagree on it" applied to a derivation rather than
a constraint, and the sweep is the only instrument that finds it.

**Hoisting a validator call into a helper passes every behavioural test and turns the id sweep
red, which is the sweep being per-route on purpose.** `test_id_validation` reads `main.py` with
`ast` and requires every id a route takes to reach a validator **in that route's own body** —
its first version matched field names against validator calls across the whole file, so a field
wrapped in one route read as wrapped in all of them and it reported zero. Moving two
`optional_uuid` calls into a shared `_named_scope` helper left the ids genuinely validated and
every test green except that one. The fix is to validate at the call site and pass the checked
values in; the alternative — exempting the routes — would be declaring that a uuid is not a
uuid.
