# ADR-0013 — MOD-017: what a plan grants, and why a membership currently grants nothing

- ID: ADR-0013
- Status: ACCEPTED
- Decision-Key: mod017-what-a-plan-grants
- Covers: backend/app/commercial/, backend/migrations/tenant/, web/src/app/

**Dated 2026-11-25. Scope: ADM-MSH-06, and the producer COM-01-R03's model does not have.**
Authority is `knowledge/00-Decisions/OWNER-2026-11-13-full-engineering-delegation.md`, which
delegates ordinary product and architecture decisions. The sources are
`veyro-product-experience-design/` — ADM-MSH-06's canvas in Batch G and its registry line in
Batch A — and `backend/app/commercial/` as it stands.

## The hole

`mem_entitlement_policies` declares COM-01-R03's nine kinds of right, with carryover, counting
and a reservation TTL. `mem_entitlement_grants` carries everything a plan would need to hand
out: the policy, a quantity, a validity window, a brand and a location, a time-of-day band, the
membership it came from, and `source_kind = 'membership'`.

**Nothing writes a membership-sourced grant.** `grep -rn 'source_kind="membership"'` over
`backend/` returns three hits and all three are in `test_commercial_api.py`. The only writer in
the product is `POST /member-entitlements`, which a human calls by hand.

So in this build:

- Activating a membership grants nothing. A member with a live membership has no entitlements.
- Every Member 360's entitlements block is empty for every member unless somebody granted by
  hand.
- `change_membership_plan` says so in its own response: *"nothing maps a product to its
  entitlement policies, so the command cannot know which grants the plan being left gave"*.
- ADM-MSH-05's canvas promises "She gains all-clubs access and 2 PT sessions monthly" and the
  command does not do it.
- ADM-MSH-06 cannot be drawn at all, because its canvas leads with what a member loses.

This is the inverse of this build's most-repeated finding. A column implying a control nobody
implemented is one shape; a *model* with a consumer and no producer is this one, and it reads as
complete from every direction — the policies table has a writer, the grants table has a writer,
the balance read works, the reservation is atomic and under a lock. What is missing is the one
edge between a plan and the rights it sells, and nothing in the schema says so.

## What the canvas needs

ADM-MSH-06, verbatim:

> **Dana · Club+ to Club** — She loses: Access to Abdoun and Sweifieh · 2 monthly PT sessions ·
> her 4 unused PT credits expire on 1 Sep. Takes effect **1 September**, not today — she has
> paid for August at the higher rate and keeps it. New monthly: **JOD 55.00**.
> *[Use the credits first] [Downgrade from 1 Sep]*
>
> The loss is stated before the saving, and the credit expiry is the line that matters — a
> member who discovers it afterwards has been quietly charged for something they never got.

Three facts, and the build has one of them:

1. **What the plan being left grants** — "access to Abdoun and Sweifieh", "2 monthly PT
   sessions". Not built: there is no edge from a plan to a policy.
2. **The member's unused quantity and when it stops being usable** — "her 4 unused PT credits
   expire on 1 Sep". The quantity is built (`balance_of` over the insert-only ledger); the
   expiry *under a downgrade* is not, because nothing relates a grant to the plan that gave it.
3. **The effective date and the new figure** — built, in the slice that added `plan_change`.

## The decision

**D1 — The mapping is per variant, not per product.** A variant is a term length, and "2 PT
sessions monthly" is a figure per billing period: an annual variant of the same product
legitimately grants twenty-four where a monthly one grants two. Hanging the set off the product
would make that unexpressible and would force a second product for every term length, which is
the shape `mem_membership_terms`' one-set-per-product rule already makes awkward.

**D2 — It is MOD-017's table, not MOD-016's.** The policies are `mem_`; the grants are `mem_`;
the membership that cites them is `mem_`. MOD-016 owns what is *sold* and MOD-017 owns what is
*owed*, which is this module's own stated split ("`mem_` is what a member is entitled to;
`fin_` is what they owe"). A `cat_` table pointing at `mem_entitlement_policies` would put the
catalogue in the business of knowing what a right is.

**D3 — The row carries the scope, and the scope is what makes "all clubs" expressible.** A
grant has `brand_id`, `location_id` and a time-of-day band, and the canvas's distinction is
exactly those: "all-clubs access" is a `location_access` entitlement with no location, and
"access to Abdoun and Sweifieh" is two rows each naming one. So the mapping carries the same
four scope columns the grant does and copies them through — rather than a `scope` enum this
module would then have to interpret twice.

**D4 — A quantity is per period and the period is the terms'.** `mem_membership_terms` carries
`billing_period`, so "2 monthly PT sessions" is `quantity = 2` on a variant whose terms bill
monthly. The mapping does **not** carry its own period: two places stating when a quantity
refreshes is two places that can disagree about how many sessions a member has, which is this
build's most-repeated defect. A grant's `valid_to` comes from the membership's own period.

**D5 — Activation grants, in the activation's transaction.** A membership that exists with no
grants is a member who has paid and cannot train; a grant with no membership is a right nobody
is paying for. That is MOD-010's `append_event` argument applied to a right, so `_grant_plan`
takes the connection.

**D6 — A plan change revokes what the old plan gave and grants what the new one gives, and
both in one transaction.** `source_kind = 'membership'` with `source_id` naming the membership
is not enough to tell *which plan* gave a grant, because a membership outlives a plan change —
so the grant gains `from_variant_id`, which is how the downgrade knows what to withdraw. A
revocation is a status change with a reason, because `mem_entitlement_grants` has no DELETE
grant and "what could this member reach in August" is asked precisely when somebody disputes a
charge.

**D7 — A held reservation is not revoked.** Paragraph 1506's reservation is a booking somebody
made, and a downgrade that cancelled it would cancel a class the member has been told they are
in. The canvas's own answer is the *"Use the credits first"* button: the loss is disclosed, the
date is the next renewal, and what the member does with the remaining quantity before then is
theirs. So a revocation writes off the **unreserved** remainder and the ledger records it, which
is what makes "4 unused PT credits expire on 1 Sep" a figure rather than a threat.

**D8 — The mapping is editable and a published plan's grants are not retroactive.** Adding a
policy to a variant changes what the *next* member gets, and changes nothing for members
already on it: their grants were written at activation and the mapping is not re-read. That is
the same property that makes MOD-016's immutable price version safe, and it is the opposite of
what a reader might assume, so the surface says it.

## What this does not decide

- **Nothing grants on renewal.** A monthly plan granting two sessions a month needs the
  renewal that creates the next period, and that sweep is undriven for a reason MOD-017's gap
  list already records. Until it runs, activation grants the first period and nothing refreshes
  it. This ADR does not invent the cadence; it makes the grant exist.
- **Carryover is declared on the policy and nothing applies it.** `carryover_mode` and
  `carryover_limit` are read by nothing, and they are about what survives a *period boundary* —
  so they wait on the same renewal.
- **No entitlement is enforced at a door from the mapping.** MOD-022 reads a grant, which is
  correct and unchanged: the mapping decides what grants exist, not what a reader may do.
- **The money a write-off is worth is not posted.** Revoking an unused credit is a right the
  member paid for and did not use; whether that is breakage revenue is the accountant's
  judgement MOD-018's gap list already names, and this writes the ledger row rather than the
  journal.
