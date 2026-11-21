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
CI. It carries 111 checks covering every track's tables -- MOD-004's hierarchy, MOD-005's `cfg_`,
MOD-015's `bil_`, MOD-007's and MOD-008's `iam`, MOD-009's `sec_`, MOD-010's `evt_`,
MOD-011's `ops_`, MOD-012's `int_`, MOD-013's `ntf_`, MOD-014's `ppl_`, MOD-016's `cat_`,
MOD-017's `mem_` and `fin_`, MOD-018's `led_`, MOD-019's `sch_`, MOD-020's `bkg_` and
MOD-021's `dev_` and MOD-022's `acc_` -- and **every one has been
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
