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

- **"The trial becomes the membership" is MOD-017's `upgrade`, which is a declared change
  kind nothing writes — and finding that out is what checking this record produced.** The first
  draft of this paragraph said the conversion is `change_plan` "which MOD-017 has". It does
  not: `change_plan` is **MOD-015's**, the SaaS subscription a tenant buys from Veyro, and a
  member's membership has no plan change at all. `lifecycle.EDGES` declares `upgrade` and
  `downgrade` as `active -> active`, `_record_change` already takes the kind and
  `check_transition` already knows the statuses — and no service function, route or job writes
  either. So converting a trial is **MOD-017's work, not MOD-027's**: an upgrade command on
  the same membership id, which is what makes ADM-CRM-06's "same ID, no re-entry" true. Eight
  of thirteen change kinds are in that state and MOD-017's gap list now says so.
- **"Expiry with no conversion moves the record to lost with reason 'trial lapsed'"** is a
  sweep over memberships whose term ended with no change — and `memberships.revoke_ended_grants`
  is already the worker job that revokes an ended membership's grants on the same predicate.
  The lost-lead write is MOD-027's and the grant revocation is MOD-017's; they are two jobs on
  one fact and the ADR should say which owns which.

**What this needs from MOD-017 that it has not got**, checked rather than assumed:

- **An upgrade command**, above. The declared kind is there and nothing writes it.
- **Nothing else.** A 7-day trial is a `membership` product with a term, and `PRODUCT_TYPES`
  carries `membership` already -- so the trial product is configuration rather than a
  capability gap, which is what FD-05's own gap note says. `GET /people/contact-match` is
  built. `memberships.revoke_ended_grants` is a worker job on the term-end predicate. Each of
  those four was a claim in this record's first draft and each was verified against the code;
  the one that was wrong is the one above.

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
