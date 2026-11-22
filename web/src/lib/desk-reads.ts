import { api } from "@/lib/api";

import type { NamedPerson, Roster } from "@/lib/desk";

/**
 * The I/O half of FD-06, apart from the decisions for the reason every other screen here
 * keeps them apart: `@/lib/api` reaches `next/headers`, and a client component that imports
 * it fails the whole app's build.
 */

export function readRoster(sessionId: string): Promise<Roster> {
  return api<Roster>(`/booking/sessions/${encodeURIComponent(sessionId)}/roster`);
}

/**
 * The names for a roster, in one request.
 *
 * **Not one per row**, which is the round-trip problem the staff list paid for once: a class
 * of eighteen plus a waitlist of three is twenty-one requests against MOD-011's per-identity
 * budget, on the screen a receptionist opens between two people.
 */
export async function readNames(
  personIds: string[],
): Promise<Map<string, NamedPerson>> {
  const wanted = [...new Set(personIds)];
  if (wanted.length === 0) return new Map();
  const query = wanted.map((one) => `person_id=${encodeURIComponent(one)}`).join("&");
  const found = await api<{ people: NamedPerson[] }>(`/people/names?${query}`);
  return new Map(found.people.map((person) => [person.person_id, person]));
}
