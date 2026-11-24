import { api } from "@/lib/api";

import type { Lookup } from "@/lib/lookup";

/**
 * FD-02's read, kept apart from its decisions.
 *
 * `@/lib/api` reaches `next/headers`, so anything importing it is server-only. This screen is
 * server-rendered throughout — a scanner emits characters and an Enter, which is a form submit
 * — so nothing here crosses into a client bundle; the split is kept anyway, because the
 * account page and the cash screen both record what happens when it is not.
 */
export function readLookup(query: string, limit = 5): Promise<Lookup> {
  return api<Lookup>(
    `/people/lookup?q=${encodeURIComponent(query)}&limit=${limit}`);
}

/**
 * **There is deliberately no membership read here, and the reason is a finding rather than a
 * choice.** The canvas prints `Club · Sweifieh · ···4180`, and "Club" is a product's display
 * name. `GET /memberships` carries the membership, its number, its status and its dates and
 * not the product it was sold on; `GET /memberships/{id}` adds the agreement and the terms,
 * including `terms.product_id` -- and the *name* behind that id is `GET /catalog/products/{id}`.
 * So the plan costs three requests per match, on a screen somebody uses with a person waiting.
 *
 * `terms.membership_kind` and `terms.billing_period` are two requests away and are "recurring"
 * and "monthly" -- a stored vocabulary rather than the plan a member would recognise, and
 * rendering one as the other is the enum-as-label defect this build has recorded five times.
 *
 * So the plan is named as absent on the screen. The club is not: `location_id` is on the
 * lookup row and the names come from one hierarchy read for every match rather than one each.
 */
