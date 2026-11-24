import { api } from "@/lib/api";

import type { Drawers } from "@/lib/shift";

/**
 * FD-07's reads, kept apart from its decisions.
 *
 * `@/lib/api` reaches `next/headers`, so anything importing it is server-only -- and the
 * count typed on this screen is parsed in a client component. `@/lib/shift` is the module
 * that component can import because this file is the one that cannot. The account page
 * learned that the hard way: putting the decisions beside the fetchers made the *login* page
 * answer 500.
 */
export function readDrawers(locationId: string): Promise<Drawers> {
  return api<Drawers>(
    `/ledger/drawers?location_id=${encodeURIComponent(locationId)}`);
}

export type ChartAccount = {
  account_id: string;
  account_code: string;
  account_kind: string;
  display_name: string;
  currency: string;
  status: string;
  legal_entity_id: string | null;
  location_id: string | null;
};

export function readChart(): Promise<{ accounts: ChartAccount[] }> {
  return api<{ accounts: ChartAccount[] }>("/ledger/accounts?status=active&limit=200");
}

export type LegalEntity = { legal_entity_id: string; registered_name: string };

export function readLegalEntities(): Promise<LegalEntity[]> {
  return api<LegalEntity[]>("/legal-entities");
}

export type PersonLink = { identity_id: string; person_id: string };

/**
 * Which person each of these identities signs in as.
 *
 * **`opened_by` and `closed_by` are MOD-007 identities**, and "HANDED OVER FROM KAREEM" is a
 * name -- so the chain is identity, then person, then `/people/names`. The link read is new:
 * nothing in the build resolved identities to people in bulk, and a screen rendering an actor
 * is exactly what needs it.
 */
export function readPeopleOfIdentities(
  identityIds: readonly string[],
): Promise<{ count: number; people: PersonLink[] }> {
  const query = identityIds
    .map((id) => `identity_id=${encodeURIComponent(id)}`).join("&");
  return api<{ count: number; people: PersonLink[] }>(`/people/by-identity?${query}`);
}
