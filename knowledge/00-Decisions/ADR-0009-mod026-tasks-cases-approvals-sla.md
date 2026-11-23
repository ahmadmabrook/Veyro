# ADR-0009 — MOD-026: where tasks, cases, approvals and SLA clocks live

- ID: ADR-0009
- Status: ACCEPTED
- Decision-Key: mod026-tasks-cases-approvals-sla
- Covers: backend/migrations/tenant/0019_tasks_and_cases.sql, backend/app/tasks/, backend/tests/test_tasks_domain.py, backend/tests/mutate_tasks_domain.py

**Dated 2026-11-23. Scope: MOD-026, TSD scope AUT-02.** The header block above is the form
`tools/governance/governance_check.py` parses; the first draft of this record wrote the same
facts as prose on one line, so **no header was parsed at all** and four required ones were
reported missing. CI caught it, which is the finding worth carrying: the local gate
`CLAUDE.md` describes under "Running it" is the backend checks and the web suite, and CI runs
two more steps on top -- this structural check and `design:coverage`. Running what the file
lists is not running what CI runs.

Authority: `OWNER-2026-11-13-full-engineering-delegation.md`. Ordinary architecture decisions
are delegated to the session; this record exists because two of these decisions are not
derivable from the sources and one of them says a requirement is **already partly built
somewhere else**, which is the kind of claim a later reader must be able to check rather than
take on trust.

## The requirements

AUT-02, seven Critical requirements, all V1 GA:

| id | requirement |
|---|---|
| AUT-02-R01 | Tasks linked to member, lead, tenant, invoice, incident, device, booking, asset or workflow. |
| AUT-02-R02 | Assignee, team queue, priority, due date, checklist, evidence, dependency and status. |
| AUT-02-R03 | Case container for multi-step problems with communication, timeline, documents and resolution reason. |
| AUT-02-R04 | Approval policies for refunds, discounts, price overrides, payroll, access exceptions, data export and deletion. |
| AUT-02-R05 | Sequential, parallel, quorum and amount-based approvals with delegation and expiry. |
| AUT-02-R06 | SLA clocks, business hours, pause reasons, breach warning and escalation routes. |
| AUT-02-R07 | Workload, aging, bottleneck, outcome and compliance reporting. |

Invariant INV-AUT-02: *"Approvers cannot approve their own restricted actions unless explicit
emergency policy applies. SLA calculation is time-zone and business-calendar aware."*

## D1 — There is one approval engine, and it is MOD-008's

**MOD-008 already implements most of R04 and R05.** `iam.approval_policies` carries `action`,
`threshold_minor`, `required_permission`, `required_approvals`, `separation_of_duties` and a
`retired_at`; `iam.approval_requests` snapshots those terms when a request is made and carries
`amount_minor`, `currency` and `expires_at`; `iam.approval_decisions` records who decided what
and why. So of R05's five named behaviours, **quorum** (`required_approvals`), **amount-based**
(`threshold_minor`) and **expiry** (`expires_at`) are built and tested.

**Two claims in the first draft of this record were wrong, and checking them is what produced
the two findings below.**

**R04's seven action classes are six.** `action` is a permission-shaped string, so a policy is
expressible for any permission the catalogue declares -- and five of the seven are there:
`finance.refund.approve`, `catalog.discount.approve`, `catalog.price.write`,
`finance.export.run`, and `access.decision.override` beside `access.emergency.unlock` for
access exceptions. Deletion is MOD-009's privacy surface. **Payroll is not a permission,
because there is no payroll module in this build at all** -- so a policy naming it would be a
policy for an action nothing can perform, which is the "declared value nothing writes" shape
this repository has found in five modules. The six that exist get the catalogue; payroll is
disclosed as waiting on the module that owns the action, which is work rather than a blocker
and is not MOD-026's.

**And INV-AUT-02's separation of duties is enforced in Python only.** The first draft of this
record said a CHECK forbids approving one's own request. There is no such CHECK:
`iam.approval_decisions` carries exactly one, on the `decision` domain, plus a
`UNIQUE (tenant_id, request_id, decided_by)` that stops one person pressing the button twice.
The rule itself lives in `app/authorization/service.py`, which is correct and is the *service*
-- and this repository's standing premise is that the schema is the half that holds when the
service is wrong. It cannot be a CHECK, because `requested_by` is on the parent row and a
CHECK cannot see another table; it is a trigger, which is the `sec_legal_holds` and MOD-018
precedent. **Writing it is the first job of slice 2**, because MOD-026 is the module whose
named invariant that rule is, and a module cannot claim an invariant whose only enforcement is
a layer it does not own.

**And the trigger must be conditional, which is the part that would have been got wrong.**
`approval.py:106` reads `if policy.separation_of_duties and decided_by == requested_by`, so a
policy may legitimately permit self-approval -- which is also what INV-AUT-02's own "unless
explicit emergency policy applies" provides for. A trigger refusing it outright would make the
database and the service disagree, which is this build's MOD-020 waitlist shape; a trigger
*re-deriving* the policy would reintroduce MOD-008's own blocking defect, where somebody
holding `authz.policy.write` switched separation of duties off for a request already in flight
and then approved it. So the trigger reads the **snapshotted** `separation_of_duties` on the
`approval_requests` row -- the column is already there for exactly this reason -- and takes
`FOR UPDATE` on it, because a trigger that reads a parent row to decide whether a child may be
written has to lock it: MOD-019 shipped `FOR SHARE` and MOD-021 shipped three with no lock at
all.

**So MOD-026 does not build a second one.** Two approval engines in one product is this
repository's own "one module, two definitions of the same balance" at its worst: two tables
able to disagree about whether a refund was approved, with nothing able to say which is the
answer. The decision is therefore the uncomfortable one — MOD-026 *extends* `iam` rather than
mirroring it in `plt01`, which means this module spans two planes, as MOD-012 does.

What MOD-026 adds, and only this:

- **Stages**, which is R05's "sequential, parallel". A policy gains an ordered list of stages;
  a stage is a required-permission set plus a quorum, and two stages at the same ordinal are
  parallel. One stage reproduces today's behaviour exactly, so nothing already approved
  changes meaning.
- **Delegation**, which is R05's remaining word. A delegation is a row, not a column: who
  delegated what to whom, between which instants, and it is revocable. A delegated approval
  records both identities, because "who actually decided" and "on whose authority" are two
  facts and INV-AUT-02 is about the first.
- **R04's action classes as a declared catalogue**, so a tenant cannot invent an approval class
  the product has no permission for -- which is also how the payroll gap stays visible rather
  than becoming a policy nobody can exercise.
- **INV-AUT-02's separation of duties, in the database**, as a trigger. See below: it is
  currently service-only.

**What this forecloses:** a task in `plt01` cannot carry a foreign key to an approval in
`iam`. `veyro_cp_app` holds nothing in `iam` and `veyro_iam_app` holds nothing in `plt01`, by
design, and no role is a member of another. The reference is therefore an id with no key
behind it — the same seam `ppl_identity_links` already is, and it is named as a gap rather
than wished away.

## D2 — A task's subject is an open vocabulary with closed members

R01 names nine link targets and **three of them do not exist in this build**: a lead is
MOD-027's (unbuilt), an asset has no module at all, and a workflow is MOD-055's (unbuilt).

A `kind` + `id` pair with a CHECK over the nine names is the only shape that can be written
today without either inventing those modules or dropping the requirement. For the six that do
exist the kind is resolvable and the service verifies the row is in the tenant; for the three
that do not, the row records a claim and says so. That is MOD-016's `order_reference`
precedent, and the reason it is acceptable there is the reason it is acceptable here: the
alternative is a column that cannot be written until three other modules land.

**Not a free-text kind.** A caller able to name its own kind would make "how many tasks are
about invoices" unanswerable, and the restricted-field rule MOD-010 enforces on event payloads
applies to a discriminator for the same reason.

## D3 — Business hours are this module's own table, and that is the one new fact the build needs

INV-AUT-02 requires SLA arithmetic to be "time-zone and business-calendar aware", and
**nothing in this repository records when a club is open.** MOD-022's attendance report says so
in as many words and refuses to derive it: MOD-019's `sch_availability_windows` is a
*resource's* rota, so reading a site's opening hours out of it would be inventing product.

So MOD-026 owns a business calendar: per location, a weekly pattern plus dated exceptions, read
in the location's own timezone — which `plt01.locations.timezone` already carries and which
MOD-019 already reads every rota window in. Two consequences worth stating before anybody
depends on them:

- **A location with no calendar has no business hours, which is not the same as being closed
  all week.** MOD-019 paid for this exact distinction twice: an empty rota meant "never
  available" in its first version and nothing could be scheduled in a tenant at all. An SLA
  against a location with no calendar runs on wall-clock elapsed time and the response says so,
  because a clock that never advances is a breach that never fires.
- **It is a calendar, not opening hours for the public.** Nothing here claims the doors are
  open to members at those times; it says when the people who answer a task are at work. The
  day somebody wants public opening hours, that is a different column and probably a different
  owner, and conflating them would be the `member_number` mistake again.

## D4 — An SLA clock is derived, never stored as a countdown

A stored "minutes remaining" is a second copy of the truth that goes stale between writes, and
this repository has refused that shape four times: MOD-018 stores no balance, MOD-019 stores no
`held_count`, MOD-016 derives `in_window`, MOD-022 derives occupancy from events. So an SLA
clock is `(target, started_at, the pause rows, the calendar)` and the remaining time is a
function of those and `now()`. A pause is a row with a reason and an actor, because "why did
this clock stop" is asked precisely when a target was missed.

**The consequence is stated rather than discovered:** a breach is a *computed* state, so
nothing fires at the moment it happens. An escalation needs the worker runtime to evaluate it,
and that job is MOD-026's own work rather than a blocker — the cadence decision is the one
MOD-011's objective evaluation already answered for itself, and the same reasoning applies:
announce on a window floored to the clock's own target so a breach is announced once rather
than once per tick.

## D5 — Build order, and why the slices are these

Four slices, each shippable on its own and each with its own isolation checks and mutation
sweep. The order follows what the next thing needs rather than the requirement numbering:

1. **The calendar, tasks and cases** (R01, R02, R03). Nothing depends on approvals, and the
   calendar is needed by the SLA slice. A task with a due date is useful before any SLA exists.
2. **Approval stages and delegation** (R04, R05), extending `iam`.
3. **SLA clocks, pauses, breach warning and escalation** (R06), plus the worker job.
4. **The reporting read** (R07) and the three screens ADM-TSK-01, ADM-CC-06 and ADM-CC-07.

**A half-written migration is worse than none**, so each slice lands whole: schema, privileges,
isolation checks run against deliberate mutations, domain functions with no I/O, the service,
the routes through `permit`, and the tests. The standard is the one the owner directive of
2026-11-18 sets — the whole stack, not the backend — so slice 4 is part of the module and not
an afterthought.

## What this record does not decide

- **Nothing here is an external blocker.** A task, a case, an approval stage, a calendar and an
  SLA clock are all work. Payroll approvals are the one requirement fragment that waits on
  another module rather than on another party, which is also work and is not this module's. The one seam is R03's "documents", which needs the object store the
  isolation rules already name beside regions and keys; a case will carry a document
  *reference* and the upload is that provider's, which is the same half-built-nothing rule
  MOD-012 applies to `vault_ref`.
- **Notification of an escalation is MOD-013's**, which authors a message and sends nothing.
  An escalation route therefore ends in a notification request, and the module will not claim
  anybody was told.
