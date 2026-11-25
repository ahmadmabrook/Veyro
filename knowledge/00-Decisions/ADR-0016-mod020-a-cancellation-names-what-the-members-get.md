# ADR-0016 — MOD-020: a cancellation names what the members get

- ID: ADR-0016
- Status: ACCEPTED
- Decision-Key: mod020-cancellation-remedy
- Covers: backend/migrations/tenant/, backend/app/booking/, backend/app/scheduling/, backend/app/commercial/, backend/app/main.py, web/src/

**Dated 2026-11-25. Scope: ADM-SCH-07.** Authority is
`knowledge/00-Decisions/OWNER-2026-11-13-full-engineering-delegation.md`, which delegates
ordinary product and architecture decisions. The source is the drawn canvas in
`veyro-product-experience-design/project/Veyro V1 Batch I Scheduling and Access.dc.html`,
read in the batch file rather than in `veyro-screen.js` — ADR-0015's own finding, where the
prototype and the deliverable disagreed about which fields exist.

## The canvas

> **ADM-SCH-07 · CANCEL A CLASS · 18 PEOPLE AFFECTED** — "Cancel Spin, Thursday 19:00 / 18
> booked, 3 on the waitlist. This is tomorrow." · **WHY · GOES INTO THE MESSAGE** "No coach
> available ▾" · **WHAT THE 18 GET · REQUIRED**: "Move them to Friday 19:00 — Dana is on · 6
> places free · 12 would need to choose another" or "Give each a class credit — Usable on any
> class within 30 days" · **They will receive** "Thursday's 19:00 spin is cancelled — we could
> not cover the class. We have held you a place on Friday at 19:00 with Dana. Reply if that
> doesn't work and we'll credit you instead." · "Sent in each member's language. The 3 on the
> waitlist get a shorter version." · Buttons "Cancel & notify 21" / "Find a coach instead" ·
> *"Cannot commit without choosing what the members get. A cancellation that notifies nobody is
> the most damaging thing this screen could permit, so the notification is the action rather
> than a follow-up."*

## What already exists, checked rather than assumed

`cancel_session` (MOD-019) cancels the session and releases every hold on it, in the
transaction that cancels. `settle_session_bookings` (MOD-020) already writes `released`
bookings and `session_cancelled` cancellation rows with no fee and no credit forfeit — the
defect a reviewer found and the module's own worst. `mem_entitlement_grants_source_kind`
already admits `'goodwill'` and `mem_entitlement_policies_type` already admits
`'class_credit'`, so the credit remedy needs no new vocabulary. `scheduling.take_hold_on` and
`scheduling.check_eligibility_on` are already connection-taking.

Three things it does *not* have, each found by reading the schema against the canvas:

- **MOD-020 has no "move a booking" operation at all.** Its decision modules are `appeals`,
  `attendance`, `consequence`, `denial`, `policy` and `waitlist`.
- **`mem_entitlement_grants` has no idempotency key and no unique rule beyond its primary
  key.** Eighteen grants in one retried command would double-grant every member.
- **`lapsed` is a declared waitlist state nothing in the build writes**, which `CLAUDE.md`
  records as "a `lapsed` entry is still never swept" — and the gap it leaves is this screen's:
  cancelling a session leaves its waitlist entries reading `waiting` for a class that will
  never run, and an `offered` entry reading as an offer whose hold `cancel_session` has
  already released.

## Decisions

**D1. The remedy is required, so the screen's route is not `cancel_session`.** The canvas is
explicit — "Cannot commit without choosing what the members get" — so a route that cancelled
and let the remedy be a later call would permit exactly the state the canvas forbids. A new
command takes the remedy and refuses without one. It lives in MOD-020, because paragraph 4145
puts the member's reservation on this side of the line and the session on MOD-019's, and
because MOD-020 already imports `scheduling`.

**D2. One transaction, because this is one plane and one role.** Every write is in `plt01`
under `veyro_cp_app` — the session, the holds, the bookings, the waitlist, the grants — so the
cancellation and the remedy commit together. That is the opposite call from ADR-0010 D12's
walk-in, and the difference is the reason: that command spans `iam`, where nothing can share a
transaction, and every partial outcome there is a *less complete record that already has a
screen*. Here a cancellation that committed with the credits rolled back is eighteen members
with a cancelled class and nothing — the harm the canvas's own last sentence names.

**D3. A move is not a new booking, and is not re-evaluated against the member's quota.** The
member already held a place; re-running `create_booking`'s denial evaluation would refuse the
members whose weekly quota *the cancelled class itself* consumed, which is the product
punishing somebody for a class the gym called off. What is still evaluated is the destination's
own capacity — MOD-019's `take_hold_on`, under its `FOR UPDATE` count and its fit trigger,
which is paragraph 4142 and the one thing that cannot be borrowed — and the destination's own
eligibility, because it is a different session with its own restrictions and a 14-year-old must
not be moved onto an 18+ class. Both helpers are already connection-taking, which is what
makes D2 affordable.

**D4. Earliest booking first, and the shortfall is disclosed rather than resolved.** The canvas
states the arithmetic: "6 places free · 12 would need to choose another". The order is
`ORDER BY booked_at`, which is `settle_session_bookings`' own order and the waitlist's position
rule. Everyone who does not fit is reported as having to choose another class; nobody is
quietly given a credit instead. The manager chose "move them", and silently doing something
else to two thirds of them is the confident wrong answer this build keeps finding — and it
would make the drawn message, which says a place has been held, false for twelve of eighteen
people.

**D5. A member already booked on the destination is reported, not refused.** `bkg_bookings`
carries a partial unique index for one live booking per member per session, so somebody who
booked both classes would make the whole command fail — and booking both is the ordinary case
rather than an edge. They are reported as already there, their place on the destination
untouched.

**D6. The credit is a `goodwill` grant with a thirty-day window, and the policy is derived.**
"Usable on any class within 30 days" is the canvas's own figure. The policy comes from the
tenant's own `entitlement_type = 'class_credit'` row; where a tenant has none, or more than
one, the command refuses and names it — ADR-0010 D12's precedent for the trial plan, because a
remedy granted against a policy nobody declared is a right nothing can draw. This gives
`goodwill` its first writer.

**D7. The idempotency is structural rather than a caller's key.** A partial unique index on
`mem_entitlement_grants (tenant_id, person_id, policy_id, source_id)` where the source kind is
`goodwill` and the source is named: one goodwill grant per person per source, which for a
cancelled class is "a member gets one credit for one cancelled class". Keyed on the source
rather than on a caller-supplied string because that is what the data means, and because a
command that grants eighteen rights has to be safe to retry by construction rather than by the
client remembering a key. A free-standing goodwill gesture with no source is outside the index,
deliberately: a tenant may legitimately give the same person two unrelated gestures.

**D8. `moved` is a booking source kind and the new booking names what it replaced.**
`bkg_bookings.source_kind`'s own stated purpose is how the member came to be booked, and its
comment says `waitlist` is separate from `member` "because a promotion is a different
conversation and a report of how a class filled needs it" — a member moved off a cancelled
class is a different conversation again. The pointer is a self-reference with a biconditional
behind it, so a `moved` booking cannot fail to say what it came from and nothing else can claim
it did.

**D9. Cancelling a session lapses its waitlist entries.** A waitlist entry is not a place, so
there is nothing to move and no credit is owed; what is owed is that the entry stops reading as
live. This is the same shape as the `released` booking defect a reviewer found in this module,
one table over, and it gives `lapsed` its first writer.

**D10. The message is not rendered by the server.** "Sent in each member's language" is the
canvas's own requirement, and the server has no message catalogue — `conventions.py` is numeral
shaping, not prose. So the command returns the facts a message is made of (the reason code, the
destination, what each member got) and the screen renders *one* preview in the reader's own
language, which is what the canvas draws under "They will receive". Prose on the wire in a
bilingual product is a field an Arabic reader can never be shown, which is ADR-0015 D6's
finding; per-member localisation is MOD-013's `locale` parameter rather than this command's.

**D11. Nothing is authored into `ntf_notifications`, and the reason is a permission rather than
a cost.** `request_notification` requires an address digest per recipient; nothing in this build
binds one from a person record, and a scheduling command that read eighteen members' contact
points to compute one would be a lateral read path around `member.contact.read` — MOD-010's
`events.event.read` finding, in a command whose caller holds `scheduling.session.change` and
need not hold anything about a member's address. The seam is MOD-013's own named gap ("nothing
wires the two together yet"); the send is external blocker 2, the messaging provider. The
command reports who is to be told, which is what a dispatcher consumes, and the screen says the
message is drafted rather than sent.

**D12. The route charges the permissions the chosen remedy uses and no others.**
`scheduling.session.change` (financial) and `booking.waitlist.manage` always;
`booking.booking.act_for_another` for a move; `membership.entitlement.grant` (financial) for a
credit. Charging all four whatever was chosen would make the screen demand a financial
permission for an act the request does not perform, and the route choosing from the body is
MOD-009's `consent_subject` precedent.

## What this does not do

**It does not send anything** — D11. **It does not find a coach**: the canvas's second button
is ADM-SCH-03's conflict check, which is built, so the screen links to it rather than
reimplementing it. **It does not move a member who does not fit, or choose for them**: D4.
