# ADR-0010 — MOD-027: the lead pipeline, the trial, and the one record behind all three

- ID: ADR-0010
- Status: ACCEPTED
- Decision-Key: mod027-crm-lead-pipeline-and-trial
- Covers: backend/app/crm/, backend/migrations/tenant/, web/src/app/leads/

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
   door. Nothing in it depends on the trial.
2. **The trial** (ADM-CRM-05, 06): the trial product, the clock derived from the agreement, the
   conversion through `change_plan`, and the lapse sweep.
3. **Lost and reopen** (ADM-CRM-07) plus the source-effectiveness read ADM-RPT-06 draws.
4. **The conversation record**, to the seam, with the provider named.

## What this record does not decide

- **Which AI provider**, or whether the model is an eighth external blocker. Stated above as a
  question for whoever writes slice 4 rather than settled here.
- **The trial's length.** The canvas draws seven days and that is a tenant's decision; the term
  lives on the agreement, so it is configuration.
- **Whether a lead has a member number.** MOD-017 and MOD-014 already carry two human-facing
  numbers with nothing relating them, and adding a third before that is resolved would make it
  worse.
