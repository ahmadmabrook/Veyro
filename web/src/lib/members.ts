/**
 * ADM-MEM-05, the members list — its decisions, and an honest account of its gaps.
 *
 * **This is the first screen in this app built from the design rather than from a module.**
 * Everything before it was composed from whatever a backend module's routes could answer, and
 * the design was read afterwards if at all. The specification is in
 * `src/design/screens.generated.json`, extracted and pinned:
 *
 * > ADM-MEM-05 · MEMBERS LIST · CM, RECEP · COMPACT · 1440
 * > 4,812 rows, and the three you need
 *
 * Seven columns — MEMBER, PLAN, CLUB, BALANCE, RENEWS, LAST VISIT, STATE — a search field,
 * three quick filters with counts, a saved-view control, a bounded bulk selection, an export
 * behind an approval, and a scale rule: "Nothing on this screen enumerates the full set…
 * There is no state where 4,812 rows render."
 *
 * **Two of the seven columns belong to MOD-014 and two more are composable.** PLAN and RENEWS
 * come from MOD-017's own list route, indexed by person — one extra call for the page, not
 * one per row, which is what the Member 360 already does and what paragraph 1300 permits: it
 * bars a cross-domain *join*, not a surface that asks twice. BALANCE, CLUB and LAST VISIT
 * have no read in this build at all, and `UNANSWERABLE` names each with the reason, because a
 * column rendered empty reads as a fact about the member rather than about the product.
 */

export type MemberRow = {
  person_id: string;
  legal_name: string;
  preferred_name: string | null;
  date_of_birth: string | null;
  lifecycle_state: string | null;
  member_number: string | null;
  joined_on: string | null;
};

export type MembersPage = {
  people: MemberRow[];
  matching: number;
  total: number;
  limit: number;
  /** Per lifecycle state over the whole tenant. Every key sums into `total`. */
  by_state: Record<string, number>;
  columns_this_module_cannot_answer: Record<string, string>;
  search_is_not_available_because: string;
};

export type MembershipRow = {
  membership_id: string;
  person_id: string;
  status: string;
  membership_kind: string;
  billing_period: string;
  current_period_end: string | null;
  ends_on: string | null;
};

/** The lifecycle states MOD-014 owns, which is the one filter this screen can really apply. */
export const LIFECYCLE_STATES = [
  "lead",
  "prospect",
  "active",
  "paused",
  "cancelled",
  "former",
] as const;

export type LifecycleState = (typeof LIFECYCLE_STATES)[number];

export function isLifecycleState(value: string | undefined): value is LifecycleState {
  return value !== undefined && (LIFECYCLE_STATES as readonly string[]).includes(value);
}

/**
 * The membership each person on the page holds, indexed once.
 *
 * **One call for the page rather than one per row.** Fifty rows against a per-person route is
 * fifty round trips for a table, which is the shape that makes a list unusable at the scale
 * the design is explicitly about. A person with two memberships keeps the newest, because the
 * list route orders by creation and the column is "what are they on now".
 */
export function membershipsByPerson(
  memberships: MembershipRow[],
): Map<string, MembershipRow> {
  const index = new Map<string, MembershipRow>();
  for (const membership of memberships) {
    if (!index.has(membership.person_id)) index.set(membership.person_id, membership);
  }
  return index;
}

/**
 * The subtitle the design states: "4,812 active · 312 expired · 68 frozen · all locations".
 *
 * **Counted over the tenant, which took a backend read.** The design's own sub-line is
 * "4,812 active · 312 expired · 68 frozen · all locations" -- a statement about the business,
 * under a heading that says "all locations". The first version counted the loaded page and
 * said so in a caption, which was honest and was still the wrong number on the screen;
 * `GET /people` now returns a grouped count and this orders it for rendering.
 *
 * **A person with no member profile counts as `none` rather than vanishing**, so the parts
 * sum to the total. A sub-line whose figures did not add up would send a reader looking for
 * the ones it left out.
 */
export function stateCounts(byState: Record<string, number>): {
  state: string;
  count: number;
}[] {
  return Object.entries(byState)
    .map(([state, count]) => ({ state, count }))
    .sort((a, b) => b.count - a.count || a.state.localeCompare(b.state));
}

/** What the design specifies that this build cannot do, each with the reason. */
export const UNANSWERABLE = {
  search:
    "Paragraph 4218 puts a permission-aware search index with a mandatory query pre-filter "
    + "in ENG-01, which is not built. A LIKE scan presented as search is a read path with no "
    + "freshness contract and no pre-filter.",
  quickFilters:
    "Owes money, Expiring and Not visited 30d each count over another module's data; a "
    + "server-side filter across modules would be the cross-domain join paragraph 1300 bars.",
  savedViews: "A saved view is filters plus columns plus sort, named — and nothing stores one.",
  bulkActions:
    "Send message, Send payment links and Add to segment: nothing in this build sends a "
    + "message, there is no payment link, and segments are PPL-01-R05's unbuilt half.",
  export: "There is no export route, and the design puts this one behind an approval.",
  columns: "CLUB, BALANCE and LAST VISIT have no read in this build.",
} as const;
