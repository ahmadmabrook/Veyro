import { api } from "@/lib/api";

import { livePrices, type Impact, type Plan, type PriceRow } from "@/lib/plans";

/**
 * ADM-MSH-09's three reads, kept apart from its decisions.
 *
 * `@/lib/api` reaches `next/headers`, so anything importing it is server-only — and the typed
 * confirmation this screen requires is parsed in a client component. `@/lib/plans` is the
 * module that component can import because this file is the one that cannot.
 */

type PlanRow = {
  product_id: string;
  variant_id: string;
  display_name: string;
  product_name: string | null;
  product_key: string;
  billing_period: string;
  is_a_trial_product: boolean;
};

/** How many plans the table draws. A gym sells a handful; the bound is the server's. */
export const PLAN_PAGE = 24;

export async function readPlans(locale: string): Promise<PlanRow[]> {
  // **The reader's locale, because the read has no fallback.** `sellable_plans` joins
  // `cat_product_texts` on the locale asked for and answers `null` rather than another
  // language's name -- `list_products`' own rule -- so asking in English for an Arabic reader
  // would show every product's name in English, and asking in Arabic for a tenant that has
  // not translated them shows every key. Both are honest and only one is what was asked.
  const body = await api<{ plans: PlanRow[] }>(
    `/memberships/plans?trials=include&locale=${encodeURIComponent(locale)}`
    + `&limit=${PLAN_PAGE}`);
  return body.plans;
}

export async function readPrices(): Promise<PriceRow[]> {
  const body = await api<{ prices: PriceRow[] }>("/catalog/prices?limit=200");
  return body.prices;
}

export function readImpact(variantId: string): Promise<Impact> {
  return api<Impact>(
    `/catalog/variants/${encodeURIComponent(variantId)}/price-impact`);
}

/**
 * The table's rows: a plan, its live price, and how many members a rise would reach.
 *
 * **The count is one request per plan, which is a cost this screen can pay and FD-02 could
 * not.** ADM-MSH-09 is owner-only and settings-shaped — nobody is standing at a desk waiting
 * — so N requests for N plans is the honest shape rather than a batch route invented for a
 * table of six. The page says so.
 *
 * **A plan with no live price keeps its row.** It is exactly the plan an owner needs to notice:
 * a published product with no price in force is one the till cannot sell, which MOD-016's own
 * gap list records as reachable with nothing changing a status.
 */
export async function readPlanTable(
  { withImpact, locale }: { withImpact: boolean; locale: string },
): Promise<Plan[]> {
  const [plans, prices] = await Promise.all([readPlans(locale), readPrices()]);
  const live = livePrices(prices);
  const rows = plans.map((plan) => ({
    ...plan,
    price: live.get(plan.variant_id) ?? null,
    impact: null as Impact | null,
  }));
  if (!withImpact) return rows;
  const counts = await Promise.all(
    rows.map((row) => readImpact(row.variant_id).catch(() => null)));
  return rows.map((row, at) => ({ ...row, impact: counts[at] ?? null }));
}
