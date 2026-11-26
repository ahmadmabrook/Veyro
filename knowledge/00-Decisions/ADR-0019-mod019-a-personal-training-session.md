# ADR-0019 — MOD-019: a personal-training session, and the inner join that would hide it

- ID: ADR-0019
- Status: ACCEPTED
- Decision-Key: mod019-personal-session
- Covers: backend/migrations/tenant/, backend/app/scheduling/, backend/app/booking/, backend/app/main.py, web/src/

**Dated 2026-11-26. Scope: ADM-SCH-05.** Authority is
`knowledge/00-Decisions/OWNER-2026-11-13-full-engineering-delegation.md`, which delegates
ordinary product and architecture decisions. The source is the drawn canvas in
`veyro-product-experience-design/project/Veyro V1 Batch I Scheduling and Access.dc.html`, read
in the batch file rather than in `veyro-screen.js` — ADR-0015's finding.

## The canvas

> **ADM-SCH-05 · SCHEDULE PT** — Book Yousef with Hala
> `WHEN  Thu 17:30` · `LENGTH  55 min`
> Uses **1 of her 3 remaining credits**. Two left after this, expiring 30 November.
> `[Book · use 1 credit]`
> At zero credits the button becomes **Sell a package first** and opens POS-05 with Hala and
> Yousef pre-filled. Never a blocked state with no way out.

Five facts, and four of them already exist in this build. A coach is a `staff` resource with a
`person_id`; a member is a `ppl_persons` row; the credits and their expiry are MOD-017's
`mem_entitlement_grants`, read by `entitlements.balance_of` and `expiring_before`; and drawing
one is `reserve_entitlement`, which is atomic under `SELECT ... FOR UPDATE` on the grant. **None
of that has ever been exercised from a surface.**

The fifth is the one the module does not have: **a session that is one member rather than a
roster.** ADM-SCH-04's own gap note says so in as many words — *"a class and a
personal-training session are one state because nothing records a session kind"* — and it says
it about the coach's week grid, which is the clue that settles the model below.

## What a personal-training session has to be

**It has to be a `sch_sessions` row**, not a table beside it. The reasoning is not aesthetic:

- The design draws PT **on the coach's rota grid** (ADM-SCH-04), so it has to hold the coach's
  time — and a resource is held through `sch_session_resources`, which references
  `sch_sessions`.
- `_held_over`, the reader every conflict decision is made from, reads
  `sch_session_resources` joined to `sch_sessions`. A PT booking in a separate table would be
  **invisible to the class generator**, so a coach teaching PT at 17:30 would be assigned a
  class at 17:30 with nothing objecting. That is the module's own review finding — a coach
  left holdable when they should not be — arriving from the other side.
- Extending the conflict reader to a second source would be two definitions of "is this coach
  free", which is this build's most-repeated finding and which `conflicts.py` exists to have
  one of.

So the question is not *whether* it is a session but *what it cites*. `template_id`, `rule_id`
and `policy_id` are `NOT NULL` with foreign keys, and a PT booking comes from none of them: a
person picked an instant.

**Two shapes were rejected before the one below.** A template per coach with a one-off rule per
booking makes `rule_id` honest and abuses the publish machinery — `sch_templates.live_rule_id`
points at *one* live rule and version numbers would climb per booking. A template per booking is
worse: template codes are unique and insert-only, so a tenant would accumulate one dead template
per PT session for ever.

## Decisions

**D1. A session states its kind, and a class cites a template while a personal session cites
none.** `sch_sessions.session_kind` over `('class', 'personal')`, defaulting to `class`;
`template_id`, `rule_id` and `policy_id` become nullable with a biconditional CHECK against the
kind — a class names all three, a personal session names none. The default is what this build
already did, which is load-bearing rather than cautious: every session already generated keeps
its three references and no reader of an existing row changes verdict. ADR-0011's reasoning
about the billing anchor, applied to a discriminator.

**D2. Six inner joins become LEFT joins, and that is the defect this slice is most likely to
ship.** `JOIN plt01.sch_templates t ON t.template_id = s.template_id` appears six times — the
calendar, the session detail, the roster read, the rota grid's held sessions, `_held_over` and
the conflict preview — each to get `t.display_name`. **An inner join on a nullable column
silently drops the row**, so a PT session would vanish from the schedule, from the coach's week
*and from the conflict reader* — the last of which means a coach could be double-booked with
nothing objecting. That is the `LEFT JOIN` finding MOD-018 paid for pointed the other way: there
a predicate in an `ON` clause failed to filter, here an `ON` clause filters something out. Every
one of the six is converted and the browser and HTTP layers each assert a PT session is present
where a class is.

**D3. No name is stored on the session.** A PT session's label is its kind plus its attendee,
and the attendee is already the single `sch_capacity_holds.person_id` that MOD-020's roster read
returns through its own gate. A `display_name` on the session holding "PT · Hala Barakat" would
be a copy of a person's name in MOD-019 — which is exactly the finding ADR-0017 D11 made about
`iam.invitations` the same day, and the surface renders "Personal training" with the member from
the gated read instead.

**D4. One coach, one slot, and the lock is on the coach's resource row.** A partial unique index
cannot express it: the coach is named in `sch_session_resources`, a different table from the
session. So the command takes `SELECT ... FOR UPDATE` on the `sch_resources` row for that coach
before counting what it holds — measured rather than assumed, because that table's UPDATE grant
is column-scoped and `has_table_privilege(..., 'UPDATE')` reads false while the lock still
works. The idempotency key is the caller's, which is this build's standard for a command.

**D5. The credit is drawn in the transaction that creates the session, and `reserve_entitlement`
did *not* already take a connection.** MOD-010's `append_event` argument applied to a booking: a
session with no credit drawn is a free PT session, and a credit drawn with no session is a member
charged for nothing. This decision first said the connection-taking form existed; it did not, and
the claim was three greps away — which is this repository's own rule about a citation being a
claim, met by the record that states it. `reserve_entitlement_on` is the extraction, and
`reserve_entitlement` now delegates to it so there is one body rather than two.

**The sweep could not be folded in with it**, which is the half worth knowing.
`reserve_entitlement`'s own docstring argues at length why the lapsed-hold sweep commits in a
transaction of its own: in the same one as a refused draw it is rolled back, and the usual reason
a member is short *is* holds that lapsed, so each attempt freed the quantity, refused on the
balance it had read before freeing it, and rolled the freeing back — a member with three lapsed
holds was refused for ever. So `book_personal_session` sweeps first, in its own transaction, and
the draw runs inside the one that writes the session. It is the first time anything on a surface
has drawn an entitlement, which is the capability MOD-017 built and nothing used.

**D6. At zero credits the button says what to do instead, and what it opens does not exist.**
The canvas is explicit — *"never a blocked state with no way out"* — and POS-05 is unbuilt, so
the screen names selling a package as the next step and says where it would happen rather than
offering a dead control. That is this build's own rule about a locked control with no route, and
it is the one part of the canvas this slice cannot draw.

**D7. Every reader of the three nullable columns answers `None` rather than the word "None".**
`str(row[0])` on a nullable column is the string `"None"` — which is not a uuid, is not the
absence, and reaches a screen as a template nobody can open. Five reads carried it and two were
worse than cosmetic: `_session`'s `policy_id` reached `WHERE policy_id = %s` as a value
PostgreSQL cannot cast, so every path through it would have answered 500 rather than finding no
policy. The two readers that look a policy up already handled its absence, because both were
written to fall back when no row comes back.

**The event payload carries `template_id: null` and no new field.** "Came from no template" *is*
the kind, so it is derivable — and `evt_outbox` is the one store no erasure reaches, where a
payload field nothing needs is one more thing in it. MOD-012's rule about not inventing an event
name, applied to a field.

**D8. A personal session is refused by MOD-020's `_evaluate`, which all three of its callers
reach.** Every decision in `create_booking` is about a *class*: the booking window and the
restrictions come from `sch_capacity_policies`, which a personal session cites none of, and the
quota, the waitlist and the no-show consequence are all about a roster. Its single place is taken
by `book_personal_session` through MOD-019's own `take_hold_on`, so a second caller reaching that
path would otherwise be refused `full` — a true answer to the wrong question.

**In `_evaluate` rather than in the command**, because a guard in one of the three is "a control
consulted on one path and not its sibling", which four modules in this build have paid for. And
the *read* is the one that matters: a surface asking whether a member may book gets
`session_not_bookable` with a sentence, rather than a `Conflict` it has to parse.

**D9. The grant is derived from the member, soonest-expiring first, and no caller may name
one.** `reserve_entitlement` reserves against the *grant's* own `person_id`, so a command taking
both a member and a grant id would let a desk train one person on another's credit — with the
reservation recorded against the payer, which is this build's most-repeated finding.
`drawable_credits_on` picks it, and the quote names the same one so a screen cannot quote a
credit the draw would not take.

**Soonest-expiring is the member's interest rather than the tenant's.** MOD-018's wallet spend
order makes the same argument: spending the value that would otherwise lapse is what a member
would choose, and spending an open-ended credit ahead of a dated one quietly destroys the dated
one. A grant with no expiry sorts last.

**And `entitlements.usable` decides rather than a `WHERE` clause**, so the list cannot offer a
grant the draw refuses — the one-module-two-definitions shape, on the figure a screen puts in
front of somebody.

**D10. The credit is judged at the hour it buys, not at the moment somebody asks.**
`entitlements.usable` takes the club's local minute, and both the quote and the draw derived
it from *now* — so an off-peak package was usable whenever the receptionist happened to type
inside its window, which makes “off-peak” a statement about the desk rather than about the
session. The validity window has the same shape and is the half a member would notice: a
credit expiring on Friday could pay for a session the following Tuesday, after there was
anything left to spend.

`drawable_credits_on` already took the moment from its caller, so the quote needed one
argument. The draw needed a second: `reserve_entitlement_on` takes `usable_at` beside `at`,
because the two are different facts — the hold is taken now, so `held_at` and the
reservation’s own TTL stay on `at`, and only the windows move. The default is the old
behaviour, which is ADR-0011’s billing-anchor reasoning applied to a moment: every caller
written before this one had the two instants equal and none of them moves.

**It also removed the quote’s `at` parameter**, which had no other reader once the credit
stopped being judged at it — nothing in that read is about now.

**Found by a time-of-day flake**, which is the only way it could have been: the off-peak test
ran at 07:40 local, inside the 06:00–12:00 window it was written to be outside, and had
passed every earlier run. The fifth shape of this build’s date-frame finding, and the first
about *which event* a rule is judged at rather than about which zone.

**D11. A clash is worded from its kind, and the server’s `detail` never reaches a reader.**
`conflicts.py` composes `staff 86807d78-62ea-… is already held by Evening yoga flow`, which
is written for the generator and read by a developer; the busy-coach banner rendered it, so a
receptionist was shown a uuid. Two things are wrong and only one is cosmetic: an id is not a
sentence, and the string is English prose composed on the server, which an Arabic reader can
never be shown — ADR-0015’s own finding from the writing side.

ADM-SCH-03 had already solved it: its conflict check returns a `resource_name` and the screen
words the *kind* through `conflictWord`, falling through to the detail only for a kind the
catalogue does not know. This screen reads the same function rather than inventing a second
wording, because two wordings for one conflict kind is the duplication this build finds most
often. An unknown kind falls through to a written sentence instead of the diagnostic.

## What this does not do

**It does not sell the package.** POS-05 is the Point of Sale surface, which has no
implementation at all, and taking money is the payment provider besides. The screen names it.

**It does not recur.** A standing weekly PT slot is a template with a rule, which is what the
class machinery already is; this is one booking at one instant. Whether a tenant wants the
former is a product question nobody has asked.

**It does not price the session.** What a PT credit is worth is MOD-016's and MOD-017's, and a
session drawn against a grant has already been paid for — which is the whole point of the credit.
A PT session sold at the door is POS-05's.
