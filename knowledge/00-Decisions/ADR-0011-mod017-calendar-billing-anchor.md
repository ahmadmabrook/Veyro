# ADR-0011 — MOD-017: the billing anchor, and the part-month the design charges for

- ID: ADR-0011
- Status: ACCEPTED
- Decision-Key: mod017-calendar-billing-anchor
- Covers: backend/app/commercial/, backend/migrations/tenant/

**Dated 2026-11-24. Scope: MOD-017 (COM-01), the first billing period and what it costs.**
Authority is `knowledge/00-Decisions/OWNER-2026-11-13-full-engineering-delegation.md`, which
delegates ordinary product and architecture decisions. The sources are
`veyro-product-experience-design/` — ADM-CRM-06's convert card and ADM-MSH-04's spec line —
and `backend/app/commercial/lifecycle.py` as it stands.

## What the design requires and this build does not do

ADM-CRM-06 draws a conversion in four lines:

> Club · monthly · JOD 55.00 / **Pro-rata to 31 Aug · JOD 21.29** / Then 55.00 from 1 Sep

Three facts are in that, and the third is the one the arithmetic confirms. The boundary is
**31 August**, the recurring charge starts on **1 September**, and 21.29 is `55.00 × 12/31` —
twelve days remaining in a thirty-one-day August. There is no other reading: if the period were
anchored on the day she converts, the boundary would be some day in September and the first
charge would be the full 55.00 with nothing to prorate.

`lifecycle.renewal_period` tiles from whatever the previous period's end was, and
`activate_membership` sets the first period to `starts_on` through `starts_on + 1 month - 1
day`. So a membership sold on 20 August bills 20 Aug–19 Sep, then 20 Sep–19 Oct, and **the
design's figure is not expressible**. ADM-MSH-04's spec line — "the pro-rata charge for the
remaining part-month and the restored renewal date" — uses the same word for a resume, which
either anchoring gives; ADM-CRM-06 is the one that pins it, because it states both the boundary
and the number.

**This is work rather than a blocker.** Nothing outside the repository has to arrive: it is a
schema decision and a pure arithmetic function, both delegated.

## The decision

**D1. The anchor is declared per contract, on `mem_membership_terms`, and defaults to what
this build already does.** A new `billing_anchor` admits `agreement_start` and `calendar`.
`agreement_start` is the default and is today's behaviour exactly, so every membership already
sold keeps the periods it was sold on — the module's premise is that a contract's figures do
not move, and silently re-anchoring live memberships would move every renewal date in the
product. It lives on the terms rather than the agreement because it is a property of what is
being sold: a gym bills its monthly memberships one way for everybody, and two members on one
contract with different anchors is a difference nobody chose.

**D2. Only the *first* period moves, and `renewal_period` is untouched.** Under `calendar` the
first period runs from `starts_on` to the end of the calendar unit containing it; after that,
the existing rule — the next period starts the day after the last one ended — lands on calendar
boundaries by itself. 20 Aug → 20–31 Aug, then 1–30 Sep, then 1–31 Oct. A monthly, quarterly
and annual contract each tile correctly with no second tiling rule, which matters because a
second one is a pair of dates that can disagree about when a member is billed.

**D3. `calendar` is refused for `weekly`, and for `one_off`.** A week has no calendar boundary
this build can name: whether a week begins on Sunday or Monday is exactly the fact ADM-RPT-04
refuses to assert, because no table or configuration key in this build records a working week —
and inventing one here to anchor a billing period would be inventing product in the place it
costs money. `one_off` has no renewal to anchor. Both are a CHECK rather than a convention, so
the refusal is the database's.

**D4. The first charge is prorated over the full calendar unit, not over the short period.**
21.29 is twelve days over thirty-one, not twelve over twelve. The denominator is what a full
period of that contract costs; the numerator is the days the member actually gets. The existing
`prorated_amount` is actual-days-over-actual-days and is the one expression both this and
`plan_change` read, because MOD-016 shipped a second rounding rule once and a reviewer found
it.

**D5. A short first period is disclosed, never inferred.** The read that answers "what does
this cost" returns the part-period amount, the recurring amount, the boundary date and the date
the recurring amount starts — four fields, because the design's own note says confusing the
pro-rata amount with the recurring amount "is the most common membership-sale complaint in the
industry". A screen that printed one number would be the complaint.

## What this does not decide

- **Nothing takes the money.** The payment provider is owner-reserved and external; what is
  built is the arithmetic and the disclosure, which must be correct whatever the provider is.
- **No invoice is issued for a part-period.** `issue_invoice` exists and nothing here calls it,
  for the same reason: the charge is disclosed and recorded against the change.
- **A mid-period anchor change is not expressible**, deliberately. Moving a live membership
  from one anchor to the other would re-date every future renewal, so the anchor is final on a
  published contract and a different anchor is a different contract.
