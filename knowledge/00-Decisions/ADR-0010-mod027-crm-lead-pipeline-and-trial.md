# ADR-0010 — MOD-027: the lead pipeline, the trial, and the one record behind all three

- ID: ADR-0010
- Status: ACCEPTED
- Decision-Key: mod027-crm-lead-pipeline-and-trial
- Covers: backend/app/crm/, backend/migrations/tenant/, web/src/app/leads/, web/src/app/desk/

**Dated 2026-11-23. Scope: MOD-027, "CRM + Unified Inbox Pilot".** The header block above is
the form `tools/governance/governance_check.py` parses, written that way because ADR-0009's
first draft put the same facts in prose on one line and no header was parsed at all. Authority
is `knowledge/00-Decisions/OWNER-2026-11-13-full-engineering-delegation.md`; the sources are
`veyro-product-experience-design/` (the HF CRM canvas, which is the one CRM screen the design
has drawn, plus the registry rows for ADM-CRM-01..07), the two `.docx` baselines and
`tools/mission_runner/module_catalog.json`.

## The requirements

MOD-027 is "CRM + Unified Inbox Pilot" and depends on MOD-013, MOD-014 and MOD-026 — **all
three are built**, so nothing here waits on another module of ours. Its seven Admin screens are
ADM-CRM-01 (lead pipeline, the one the design has drawn), 02 (lead list, a table view of the
same data), 03 (lead profile), 04 (add lead), 05 (trial in progress), 06 (convert trial) and
07 (lost lead).

## D1 — A lead, a trialist and a member are one `ppl_persons` row

The canvas is unusually explicit and it is a structural requirement rather than a preference:

> **WHAT THE TRIAL CREATES.** A real member record from the start — access pass, app login,
> class booking rights, and a 7-day clock. Nothing is re-entered when she converts: the trial
> becomes the membership, so her check-ins, her spin attendance and her coach's first note all
> carry forward.
>
> This is the duplicate-data-entry fix from Phase 6, made structural: a lead, a trialist and a
> member are one record at three stages, never three records.

So MOD-027 does **not** own a person. `ppl_member_profiles.lifecycle_state` already admits
`lead` and `prospect`, and MOD-014 owns the name, the contact points and the duplicate
detection. What MOD-027 owns is the pipeline: where in it this person is, who owns them, where
they came from, what the next action is, and why they were lost.

**And the duplicate check ADM-CRM-04 requires already exists.** "Phone-based duplicate
detection surfaces existing leads and members before creating" is `GET /people/contact-match`,
built for ADM-MEM-10 — normalized by the write's own function, masked like every other read in
MOD-014, and filtered to `merge_status = 'active'`.

## D2 — A trial is a membership, not a CRM state

"A real member record from the start — access pass, app login, class booking rights" is only
true if the ordinary readers treat it as live: MOD-022's door reads the membership's own dates,
`entitlements.usable` reads the grant's. A `trial` status in `mem_memberships` would mean every
one of those readers has to learn a new value — MOD-022, MOD-020, MOD-017's own lifecycle and
the status cache — which is the "a declared state nothing writes" finding inverted into "a new
state everything must now handle".

So a trial is an **`active` membership on a trial product with a short term**, and what marks
it as a trial is the agreement's own terms rather than a status. Two things follow:

- **"The trial becomes the membership" is a new agreement on the same person, and the
  membership id does not survive — which took two corrections to get right and is the reason
  this record is worth having.** The first draft said the conversion is `change_plan`, "which
  MOD-017 has". It does not: `change_plan` is **MOD-015's**, the SaaS subscription a tenant
  buys from Veyro. The second draft said it is MOD-017's `upgrade`, a declared `active ->
  active` change kind nothing writes. That is true about the kind and wrong about the
  mechanism: moving a member between products would have to move
  `mem_memberships.agreement_id` or `mem_agreements.variant_id`, and **neither is in any
  runtime role's UPDATE grant** — nor `price_resolution_id`, nor `person_id`. What the member
  agreed to does not move, which is MOD-017's own premise and what makes "what did they agree
  to a year ago" answerable from the row.

  So a conversion is `create_agreement` and `activate_membership` on the **same person**, with
  the trial membership expired — both of which exist. **And that is what makes the canvas's
  "nothing is re-entered" true**: every item it lists as carrying forward is person-scoped —
  "her check-ins, her spin attendance and her coach's first note" are MOD-022 decisions,
  MOD-020 bookings and MOD-014 notes, all keyed on the person. The id that matters is the
  person's, not the membership's, which is also exactly what "a lead, a trialist and a member
  are one record at three stages" says. ADM-CRM-06's "same ID" reads as the person.

  **And the third reading is that an upgrade is buildable after all, which makes the second
  reading wrong as well.** `mem_agreements.supersedes_agreement_id` exists -- "which agreement
  this one replaces, for an upgrade, downgrade or transfer ... so the chain answers what did
  this member have in March" -- `create_agreement` takes it and a route exposes it. What is
  missing is a *reader*: all five readers of a membership's terms go to
  `mem_memberships.agreement_id`, the chain's root, so a superseding agreement written today
  leaves the freeze allowance, the cancellation fee, the notice period and the buy-out all
  answering from the agreement the member left. MOD-017's gap list carries that now.

  **None of which changes what a conversion is here.** A trial and a membership are different
  *products* sold on different terms, and the canvas's "nothing is re-entered" is satisfied by
  the person: her check-ins, her attendance and her coach's note are MOD-022, MOD-020 and
  MOD-014 rows keyed on `person_id`. Whether MOD-027 converts by superseding the trial's
  agreement or by selling a fresh membership is a decision for its slice 2, and it is better
  made once MOD-017's chain has a reader -- so this record names the dependency rather than
  guessing which side of it the conversion lands on.
- **"Expiry with no conversion moves the record to lost with reason 'trial lapsed'"** is a
  sweep over memberships whose term ended with no change — and `memberships.revoke_ended_grants`
  is already the worker job that revokes an ended membership's grants on the same predicate.
  The lost-lead write is MOD-027's and the grant revocation is MOD-017's; they are two jobs on
  one fact and the ADR should say which owns which.

**What this needs from MOD-017 that it has not got**, checked rather than assumed:

- **A reader for the supersession chain**, which is one definition used by five call sites and
  is MOD-017's work. Slice 2 waits on it rather than working around it.
- **Nothing else.** `create_agreement` and `activate_membership` exist; a 7-day trial is a
  `membership` product with a term and `PRODUCT_TYPES` carries `membership` already, so the
  trial product is configuration rather than a capability gap -- which is what FD-05's own gap
  note says. `GET /people/contact-match` is built. `memberships.revoke_ended_grants` is a
  worker job on the term-end predicate.
- **Every claim here was checked against the code and the first three readings of one of them
  were wrong**, which is the argument for the checking rather than against it: `change_plan`
  resolved in the wrong module, then `agreement_id`'s immutability looked like a prohibition
  rather than a root, and only the third pass found the chain the schema already carries and
  the readers that ignore it. A design record is a set of claims about other people's code.

## D3 — The pipeline is five columns and the stage is derived where it can be

The canvas draws New, Contacted, Toured, On trial, Joined. Three of those are facts MOD-027
records (contacted, toured) and two are facts other modules already own:

- **On trial** is "this person has an active membership on a trial product", which MOD-017
  answers.
- **Joined** is "this person has an active membership that is not a trial", likewise.

So the stored stage is the *sales* stage and the last two are derived. A stored `on trial`
would be a second definition of whether somebody has a membership, which is MOD-018's
one-module-two-definitions finding and would go stale the moment a trial lapsed.

## D4 — Lost is reversible, which is the opposite of MOD-026's case

> **ADM-CRM-07.** Reason picker with a free-text note. Feeds the source-effectiveness report.
> Reopenable — a lost lead is not deleted, and re-contact after 90 days is a supported flow
> rather than a new record.

MOD-026's case moves forward only and a problem that returns is a new case citing the old.
A lead is the opposite and the design says so: the same person is re-contacted, and a new
record would defeat D1. So a lost lead is a *state with a reason and an attribution* that can
be left, and the history is the touchpoint timeline rather than a chain of records.

## D5 — The AI suggestion is a record and a permission, and the text is the external half

The canvas draws `AITreatment(ai.600)` with "VEYRO SUGGESTS · YOU SEND IT" and a rationale
("From her open-day notes and this club's conversion history"). Three parts, and only one of
them is external:

- **`ai.action.invoke` is already in the catalogue and is `privileged`**, which needs AAL 3 —
  reachable since WebAuthn verification landed. So the permission half is built.
- **The record** — what was suggested, on what evidence, who sent it and whether they edited it
  — is MOD-027's and is work. A suggestion nobody can account for is this build's own
  fabricated-evidence shape.
- **The text** needs a model, which is a third-party account. That is an eighth external
  blocker and the isolation rules' list says there are seven — so either the list grows with a
  stated reason or this feature is built to the seam with a local, deterministic suggester and
  the model named as what would replace it. The seam is the honest half either way.

**And "YOU SEND IT" is load-bearing**: nothing here sends, because MOD-013 has no provider. So
the suggestion is drafted, recorded and handed to a person — which is the same half-built-
nothing rule MOD-013 already follows.

## D6 — The unified inbox is half blocked and the half that is not is the conversation record

MOD-027's title is "CRM + Unified Inbox Pilot". Receiving a WhatsApp message needs the
messaging provider — external blocker 2 — and sending one does too. What is not blocked is the
**conversation**: a thread per person, its touchpoints, who owns it, and what was said by whom.
MOD-013 authors and settles a message and sends nothing; a conversation record that cites
MOD-013's notifications is work, and the inbound half is the seam.

## Build order

1. **The lead and its pipeline** (ADM-CRM-01, 02, 03, 04): the schema, the stage machine, the
   touchpoint timeline, the owner, the source, the next action, and the duplicate check at the
   door. Nothing in it depends on the trial. **Landed**: four `crm_` tables, `app/crm/`, five
   permissions, twelve routes, isolation check 115, and the screens still owed -- see
   `CLAUDE.md`'s MOD-027 section. Two things in this record were corrected by building it: the
   `lost` stage is not in the schema's stage domain -- **and slice 3 did not put it there
   either, which D8 explains: it is a fact beside the stage, because the pipeline runs forward
   only and a reopening would need the backwards edge D3 rules out**; and `gym_only` is
   refused in combination with another interest, which D3 did not consider and which the words
   themselves require.
2. **The trial** (ADM-CRM-05, 06): the trial product, the clock derived from the agreement, the
   conversion through MOD-017's `change_membership_plan` -- **not `change_plan`, which is
   MOD-015's SaaS subscription**, and which the first draft of this record named -- and the
   lapse sweep. **The decision in front of it**: what marks a product as a trial. Neither
   `cat_products.product_type` nor `mem_membership_terms.membership_kind` carries such a value,
   so "an active membership on a trial product" is not yet expressible, and slice 1's board
   returns an empty `On trial` column that says so. `change_membership_plan` is built.
   **Landed, except FD-05.** D7 is what marks a product as a trial, ADM-CRM-05 and 06 are
   drawn, and the Front Desk half of the same slice is the walk-in — two fields and a button
   that starts the trial at the desk. Its coverage reason said the obstacle was that "nothing
   marks a product as a trial yet", which D7 settled, so the entry outlived its own blocker;
   D12 is what it needs instead.
3. **Lost and reopen** (ADM-CRM-07). **Landed**: `0030`, the four columns beside the stage,
   the interest withdrawal, the screen and the table's `Lost` chip. **This item used to end
   "plus the source-effectiveness read ADM-RPT-06 draws", and there is no ADM-RPT-06.** The
   registry has five report screens and none of them is it; ADM-CRM-07's own footnote sends
   the reason to ADM-RPT-03, which is the *membership* report -- it draws "WHY THE 23 LEFT"
   and says "Reasons come from ADM-MSH-07's required field", so its subject is members
   cancelling rather than leads who never joined. **So the reason feeds nothing in this build
   and the destination is undrawn.** Two cross-references in this record have now named
   something that does not exist -- `change_plan` for `change_membership_plan`, and this --
   and both were found by trying to build against them.
4. **The conversation record**, to the seam, with the provider named.

## D8 — Lost is a fact beside the stage, not a value in it

**This corrects a prediction in this record.** The slice-1 note says "the `lost` stage is *not*
in the schema's stage domain ... slice 3 is what writes it", which assumed `lost` would become a
sixth stage. Building slice 3 shows it should not, and the reason is in D3 one section earlier:
**the pipeline runs forward only, and the design gives no affordance for going back.** That rule
exists because "a tour that fell through is a *touchpoint* saying so" and a backwards move
"would make `Toured · 6` a count nobody can reconstruct" — and `lost` as a stage needs exactly
that backwards edge the moment a lead is reopened, which D4 requires. A prediction about a
mechanism is a claim like any other.

So `crm_leads` gains four nullable columns — `lost_at`, `lost_reason`, `lost_detail`,
`lost_by` — all-or-none by constraint, and `stage` is untouched. Three things fall out of it:

- **Reopening is exact.** The lead resumes at the stage they were at, because that stage never
  moved; and the next touchpoint advances it, since `record_touchpoint` already does. A stage
  value would have had to choose where a reopened lead lands, and any choice is a number
  somebody cannot reconstruct.
- **`EDGES` is unchanged**, so there is one stage machine and it still refuses every backwards
  move. Two encodings of "where is this lead" that could disagree is MOD-020's waitlist edge;
  a *position* and a *liveness* are different facts, which is why MOD-017 keeps membership,
  billing and access state apart rather than folding them together.
- **The board excludes a lost lead rather than drawing a sixth column**, which is what the
  canvas shows: ADM-CRM-01 draws five columns and ADM-CRM-07 is a side sheet. And a lost lead
  is **not counted as going cold**: nobody has failed to ring them, they said no.

## D9 — The reason is a closed four with one free-text escape

> **ADM-CRM-07.** "Why did Omar Zaid not join?" — Too expensive / Joined somewhere else /
> Location or hours / No longer responding — and "Which gym, if he said…".

**Closed, because a group-by needs a closed set.** The registry note is "Structured reason,
feeds retention analytics", and free text would make any such report a group-by over typos —
MOD-026's queue finding and MOD-027's own source finding.

**And the report the canvas names is not that report**, which building this found. ADM-CRM-07's
footnote says "The reason feeds source effectiveness in ADM-RPT-03"; ADM-RPT-03 is the
membership report, whose own canvas draws "WHY THE 23 LEFT" and states "Reasons come from
ADM-MSH-07's required field" — members cancelling, not leads who never joined. So no drawn
screen consumes a lost-lead reason, and the vocabulary stands on the group-by rather than on a
destination. **What ADM-RPT-03 does want is this same shape one module over**: its chart is
blocked because `mem_lifecycle_changes.reason` is free prose, which that screen already
records — so a structured cancellation reason on MOD-017 is the work that unblocks it, and
slice 3 is the worked example of what it looks like.

The four are declared in
`app/crm/pipeline.py` with a CHECK behind them and the Python-against-SQL agreement test
MOD-026 established.

**In code rather than in a tenant's own table, which is the opposite call from `crm_sources`.**
A source is a club's own open day and belongs to that club; a lost reason is a category of
market behaviour, and a per-tenant set would make any such report's columns vary by tenant
with nothing able to say which set is the product's. A fifth reason is a product decision.

**There is no "Other", and the detail is the escape.** The canvas draws four and no catch-all;
"No longer responding" is the one that absorbs a lead who simply stopped. `lost_detail` is
nullable free text for the canvas's own "which gym, if he said" and is admitted for any reason,
because a salesperson who learns something true should be able to write it down.

## D10 — Ninety days is advisory on a read, never a lock on a write

> Reopenable, and re-contact after 90 days is a supported flow rather than a fresh record.

The emphasis in that sentence is on **"rather than a fresh record"** — the point is that
re-contact does not duplicate the person, which D1 already enforces by index. The ninety days
is when re-contacting becomes *appropriate*, not when it becomes *permitted*.

So reopening is always allowed and the read says which lost leads have passed ninety days.
Locking the write for ninety days would make a lead marked lost by mistake uncorrectable for a
quarter on a routine permission, which is MOD-013's "an irreversible act must not be declarable
on a routine permission" — and this slice is the one that owes the same remedy for
`crm_lead_interests`.

## D11 — The interest withdrawal this slice owes

`crm_lead_interests` carries `GRANT SELECT, INSERT` and nothing else, so an interest recorded by
mistake has no remedy anywhere in the product — a routine permission whose every act is
permanent, which is MOD-019's rota finding in a smaller place. `0017`'s shape is the precedent:
withdrawal columns with an attribution constraint and a one-way trigger, **not a delete**,
because "was this lead ever interested in PT" is asked precisely when somebody has changed
their mind.

## D7 — What marks a product as a trial, and where the clock lives

**Amendment, after slice 1; built as slice 2.** D3 derives the board's last two columns from
MOD-017 -- *"On trial is 'this person has an active membership on a trial product', which
MOD-017 answers"* -- and nothing in this build could tell a trial product from a real one, so
that column was drawn empty with the reason on it. This settles it, and the decision is two
parts because checking the code found the second one.

**`mem_membership_terms.trial_days`, nullable, 1 to 90.** Three things it is not, each refused
for a stated reason:

- **Not a `PRODUCT_TYPES` value.** COM-02-R01 names eight and a trial is not a ninth kind of
  thing to sell: a 7-day trial of a membership is a membership. Adding one would make every
  reader of that vocabulary -- the catalogue, the bundle fulfilment kinds, the entitlement
  rule -- answer about a taxonomy the requirement does not have.
- **Not an eleventh `membership_kind`.** `0011`'s own comment says "COM-01-R01 in full. An
  eleventh shape is a product decision, not a migration", and a shape *decides which lifecycle
  edges exist and how the billing schedule is built*. A trial has the edges of whatever it is
  sold as; what makes it a trial is orthogonal to its shape.
- **Not a boolean beside a length.** MOD-017's `early_termination_months` is the precedent: one
  nullable integer rather than a flag and a count, because two columns can disagree and this
  build has created that defect on purpose once. `NULL` is "not a trial"; **0 is refused**,
  unlike `early_termination_months` where zero is a real product -- a zero-day trial is not a
  thing a gym sells, so admitting it would be a declared value nothing can mean.

It sits on the terms rather than the product because `mem_membership_terms` is already 1:1 with
a product (`UNIQUE (tenant_id, product_id)`) and is where the contract *shape* lives, beside
`billing_period`, `installment_count` and `prepaid_days`. So "a trial product" and "a product
whose terms declare a trial length" are the same row, and no join has to choose between them.

**And the length in days is a fact nothing else can carry**, which is what makes this one
column rather than a flag. The term fields are months (`minimum_term_months`) and
`prepaid_days` is bound to `membership_kind = 'prepaid'` by a biconditional -- a trial is not a
prepayment, because nothing was paid. This record's own earlier line said the length "lives on
the agreement, so it is configuration"; that is true of the *actual* end and false of the
*offered* one, and the offered one is what ADM-CRM-01's "Start a 7-day trial" button needs. A
length typed at the desk is two receptionists giving two different trials.

**The second part is that the clock is `mem_memberships.ends_on`, which already exists and is
already read.** `activate_membership` inserts the membership with `ends_on` NULL and nothing
derives it; the column is written only by a cancellation. Setting it at activation from
`trial_days` buys three behaviours that are already built:

- **The door refuses after it ends.** MOD-022 reads the membership's dates rather than its
  cached status, which MOD-017's gap list records in as many words.
- **The grants are revoked.** `memberships.revoke_ended_grants` is a worker job on the
  `ends_on` predicate, which is also the sweep this ADR's D4 says owns the MOD-017 half of a
  lapsed trial.
- **"2 DAYS LEFT" is derived.** ADM-CRM-05's countdown is `ends_on` minus today in the club's
  own zone, with no second definition of when a trial ends.

A trial clock of MOD-027's own would be a fourth copy of "when does this end", and the first
time it disagreed with `ends_on` the door and the screen would say different things about the
same person.

**What this does not settle** is whether a conversion supersedes the trial's agreement or sells
a fresh one -- the question D2 left for slice 2, which is now answerable because MOD-017's
supersession chain has its reader (eight of them, which is the dependency this record named and
the only one it had).

## D12 — The walk-in trial is one route over four writes, resumable rather than atomic

FD-05 is "two fields and a start: name and phone. Creates a lead already in trial state with
the clock running. Everything else is captured later by the sales team — a person standing at a
desk will not complete a form." Its canvas draws `NAME`, `PHONE` and **Start her trial now**,
over the sentence that settles the architecture: "the record is the same record she converts
on."

So one press has to produce four facts — a person, a lead, a signed agreement on a trial
product, and an activation that sets `ends_on` — across MOD-014, MOD-027, MOD-016 and MOD-017.
Six decisions, and two of them are refusals.

**One route, four transactions, and the response says which it performed.** The obvious shape
is one transaction, which this repository reaches for whenever a control and the state it
bounds have to commit together: `append_event`, `post_journal`, `take_hold_on`,
`issue_command_on`. **None of these four is a control over another's state.** Each is an
independent fact, each partial outcome is a *less complete* record rather than an
unreconcilable one, and each already has a screen: a person with no lead is what ADM-MEM-10
produces, a lead at `new` is the board's first column, and a signed agreement nobody activated
is `activate_membership`'s own retry path. What makes a retry converge is that **every step
keys on the person** — the contact match resolves them, `crm_leads_one_per_person` hands back
the lead, and `live_trial` hands back the trial — so pressing the button twice produces one
of each. MOD-009's "an interrupted erasure resumes" is the precedent, and the response names
each step as `created` or `existing` rather than implying atomicity it does not have. The
atomic version needs `_on` variants of `create_person`, `create_lead`, `create_agreement` and
`activate_membership`; that is the right shape the day one of them becomes a control over
another's state, and today it would be four core money functions refactored to buy a property
nothing needs.

**And building it narrowed that fourth read.** `resumable_agreement`'s first version also
required no membership to point at the row, with a `LEFT JOIN` for it; `activate_membership`
sets the agreement to `active` in the transaction that writes the membership, so the status
filter already excludes every activated agreement and the extra clause proved nothing. The
mutation sweep said so by coming back uncaught, and the judgement is this repository's own for
a constraint subsumed by a sibling: delete it and keep the primitive statement rather than
contrive a case that cannot exist.

**Both refusals happen before anything is written, and the first version broke that.** The
plan was resolved *after* the person was created, so a tenant publishing two trial plans got a
person, a lead and a touchpoint written on every refused press — and the second press was then
refused for the *duplicate* rather than for the plan, which is the wrong answer to the wrong
question. A control that commits anything before it refuses is not a control; found by a test
that pressed the button twice, and the ordering now has an assertion of its own.

**The phone is the key, and a match is refused rather than reused.** MOD-014's `AUTO_MERGE_
THRESHOLD` is `None` because two siblings at one address with one family line is the ordinary
case, so a command that silently reused whoever already held the number would be making the
merge decision paragraph 10200 reserves for a person. It refuses, naming the match, and the
screen offers ADM-MEM-10's own two escapes — start the trial on that record, or say it is
somebody else. That refusal is also what makes the retry converge: the second attempt finds
the person the first one created and the desk is shown them by name.

**The figure is quoted, never supplied.** `catalog.quote_price` exists and does not store, so
the agreement's amount is the trial plan's own live price rather than a number a till sent —
"a cited authority is the authority, or it is decoration beside the figure", which is the
finding `create_agreement` was fixed for. A trial is usually free and zero is a figure like
any other.

**The plan is derived where there is one and named where there is not.** Two fields is the
canvas, so the command resolves the tenant's published trial plan itself; a tenant with two of
them is a case the canvas does not draw, and the command refuses with both named rather than
choosing — which is MOD-018's unordered-lookup finding applied to which product somebody is
sold. A picker that appears only in that case is `/rota`'s "no rota binds" judgement: a state
the drawing does not have, rendered honestly rather than guessed at.

**The touchpoint is a `visit` and its prose is the client's.** A walk-in visited, so the
timeline entry is the record of what happened, and `stage_from_touchpoint` then moves the lead
`new → contacted` — which is what keeps the board's count and the profile's timeline from
disagreeing, D3's own reason for making the first two moves facts rather than buttons. The
*summary* comes from the caller because a sentence this service wrote would be the first
non-human prose in a column every other row of which a salesperson typed, stored in whichever
language it was written in whatever language the desk was using. The stage matters later rather
than now: the board shows a trialist in `On trial` whatever their stage says, so `contacted` is
where they land when the trial lapses.

**Two of the canvas's three promises are not kept, and the screen says which.** "Creates a lead
already in trial with the clock running, a credential, and an app invitation by text" — the
first is the whole of what is ours. A credential needs somewhere for the member to show it and
this build has no mobile client and nothing that could text one; the invitation is the
messaging provider, which is external blocker 2. Neither is a reason to withhold the trial,
which is the part a desk is standing there to do.

## What this record does not decide

- **Which AI provider**, or whether the model is an eighth external blocker. Stated above as a
  question for whoever writes slice 4 rather than settled here.
- **The trial's length** was listed here and is decided in D7: the *offered* length is
  `mem_membership_terms.trial_days` and the *actual* end is `mem_memberships.ends_on`. The line
  this replaced said the length "lives on the agreement, so it is configuration", which is
  right about the end and wrong about the offer -- and the offer is what a button saying
  "Start a 7-day trial" has to read.
- **Whether a lead has a member number.** MOD-017 and MOD-014 already carry two human-facing
  numbers with nothing relating them, and adding a third before that is resolved would make it
  worse.
