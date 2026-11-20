import type { MessageKey } from "@/i18n/locale";

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
 * The message key naming a lifecycle state.
 *
 * **A stored value is not a label**, and this list was rendered raw -- so an Arabic reader
 * saw `lead` in Latin letters in the middle of an Arabic page, on the filter chips and in
 * every row of the table. The parity check cannot see this: it compares the two catalogues
 * against each other and is blind to a string that never became a key, which is the finding
 * MOD-013's board already paid for. Found by switching the language and looking.
 *
 * **An unknown state falls through to its stored value rather than to "other".** The set is
 * MOD-014's and may grow; hiding which one it is on the screen that filters by it would be
 * worse than showing an untranslated word.
 */
export function stateName(state: string): MessageKey | null {
  const known: Record<string, MessageKey> = {
    lead: "members.stateLead",
    prospect: "members.stateProspect",
    active: "members.stateActive",
    paused: "members.statePaused",
    cancelled: "members.stateCancelled",
    former: "members.stateFormer",
  };
  return known[state] ?? null;
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
/**
 * The message key naming a membership kind, billing period or status.
 *
 * MOD-017's own vocabulary, rendered raw on the members list until somebody read the Arabic
 * page: `recurring`, `monthly` and `active` in Latin letters beside Arabic headings. One map
 * rather than three, because the three sets do not overlap and a reader does not care which
 * column a word came from.
 */
export function planName(stored: string): MessageKey | null {
  const known: Record<string, MessageKey> = {
    recurring: "plan.kindRecurring",
    prepaid: "plan.kindPrepaid",
    monthly: "plan.periodMonthly",
    quarterly: "plan.periodQuarterly",
    annual: "plan.periodAnnual",
    weekly: "plan.periodWeekly",
    pending: "plan.statusPending",
    active: "plan.statusActive",
    frozen: "plan.statusFrozen",
    grace: "plan.statusGrace",
    suspended: "plan.statusSuspended",
    cancelled: "plan.statusCancelled",
    expired: "plan.statusExpired",
    completed: "plan.statusCompleted",
  };
  return known[stored] ?? null;
}

/**
 * What this screen cannot do, as message keys.
 *
 * **Keys, not prose, which is what the Command Center's own `UNANSWERABLE` already is.**
 * This module held English sentences in a library and rendered them straight to the page, so
 * the Arabic build carried six English paragraphs under Arabic headings -- and the catalogue
 * parity check could not see it, because a string that never became a key is invisible to a
 * comparison between the two catalogues. Found by switching the language and looking, which
 * is the third time that has been the only thing that worked.
 */
export const UNANSWERABLE = {
  search: "members.whySearch",
  quickFilters: "members.whyQuickFilters",
  savedViews: "members.whySavedViews",
  bulkActions: "members.whyBulkActions",
  export: "members.whyExport",
  columns: "members.whyColumns",
} as const satisfies Record<string, MessageKey>;
