import { api } from "@/lib/api";

/**
 * MOD-014's reads, typed, and the one marker that matters.
 *
 * **`"***"` is a value, not an absence, and the difference is the whole point.** MOD-014's
 * masking replaces a field a caller may not read with `MASK = "***"` at every depth, and its
 * own rule is that "a redacted record still exists": telling a coach a member has no health
 * notes when they have three is worse than telling them there are three they cannot read. So
 * nothing here drops a masked value -- `isWithheld` marks it, and the surface renders it as
 * withheld rather than as blank.
 *
 * This is the only module in the build whose read path applies `Decision.mask`, which is why
 * the marker lives here and not in a component: a second surface onto MOD-014 has to make the
 * same distinction, and a copy of `"***"` in a JSX file is a copy that drifts.
 */

// **Re-exported from `@/lib/mask`, which imports nothing.** This module imports `@/lib/api`
// and therefore `next/headers`, so a client component that reaches it fails the build -- which
// is what FD-07's open form did through `@/lib/shift`. The marker's home is the pure module and
// the name stays reachable here, so the pages that already import it are untouched.
export { MASK, isWithheld } from "@/lib/mask";

export type ContactPoint = {
  contact_point_id: string;
  kind: string;
  value_raw: string;
  value_normalized: string;
  is_primary: boolean;
  verified_at: string | null;
};

export type PersonTag = {
  tag_id: string;
  tag_key: string;
  display_name: string;
  is_internal: boolean;
  applied_at: string;
};

export type CustomFieldValue = {
  field_key: string;
  display_name: string;
  value_type: string;
  sensitivity: string;
  value: string;
  redacted: boolean;
};

export type Relationship = {
  relationship_id: string;
  kind: string;
  from_person_id: string;
  to_person_id: string;
  started_on: string | null;
  ended_on: string | null;
};

export type Person = {
  person_id: string;
  legal_name: string;
  preferred_name: string | null;
  date_of_birth: string | null;
  merge_status: string;
  merged_into_person_id: string | null;
  version: number;
  is_minor: boolean;
  guardianship: string;
  contact_points: ContactPoint[];
  tags: PersonTag[];
  custom_fields: CustomFieldValue[];
  relationships: Relationship[];
};

export type Note = {
  note_id: string;
  note_class: string;
  body: string;
  recorded_at: string;
  recorded_by: string;
  withdrawn_at: string | null;
  withdraw_reason: string | null;
  visibility_class: string;
  redacted: boolean;
  redacted_because?: string | null;
};

export type TimelineEntry = {
  entry_id: string;
  event_id: string;
  event_type: string;
  occurred_at: string;
  aggregate_type: string;
  aggregate_id: string;
  summary: string;
  visibility_class: string;
};

export type MemberProfile = {
  lifecycle_state: string;
  state_changed_at: string;
  member_number: string | null;
  joined_on: string | null;
  version: number;
};

export type StaffProfile = {
  employment_state: string;
  job_title: string | null;
  location_id: string | null;
  started_on: string | null;
  ended_on: string | null;
  version: number;
};

export type Member360 = {
  person: Person;
  member_profile: MemberProfile | null;
  staff_profile: StaffProfile | null;
  notes: Note[];
  timeline: TimelineEntry[];
  consent_record_count: number;
  /** Every section names its source, and the absent ones say which module is missing. */
  sections: Record<string, string>;
};

export type DuplicateCandidate = {
  candidate_id: string;
  lower_person_id: string;
  higher_person_id: string;
  score: number;
  signals: string[];
  status: string;
  detected_at: string;
  decided_at: string | null;
  decision_reason: string | null;
};

/**
 * One person, masked — `GET /people/{id}`, which until now nothing in this app called.
 *
 * The Member 360 composes a member's whole record and is the right read for that page; a
 * staff record needs the name and nothing else, and the 360 would pull notes, a timeline and
 * three other modules' blocks to get it. The mask is applied by the server either way, which
 * is the property that matters: there is one place it has to be right.
 */
export function readPerson(personId: string): Promise<Person> {
  return api<Person>(`/people/${encodeURIComponent(personId)}`);
}

export function readMember360(personId: string): Promise<Member360> {
  return api<Member360>(`/people/${encodeURIComponent(personId)}/360`);
}

export function listDuplicateCandidates(): Promise<DuplicateCandidate[]> {
  return api<DuplicateCandidate[]>("/people/duplicates/all");
}

/**
 * Which sections of the 360 have a module behind them, and which do not.
 *
 * The server states this per section in prose. Splitting it here rather than in the page keeps
 * the rule in one place: a section whose text begins `unavailable:` is a module this build does
 * not have, and rendering it as an empty list would read as "none" -- which is the difference
 * between "this member has no outstanding balance" and "nothing here knows".
 */
export function splitSections(
  sections: Record<string, string>,
): { available: [string, string][]; unavailable: [string, string][] } {
  const entries = Object.entries(sections);
  return {
    available: entries.filter(([, source]) => !source.startsWith("unavailable:")),
    unavailable: entries
      .filter(([, source]) => source.startsWith("unavailable:"))
      .map(([name, source]) => [name, source.replace(/^unavailable:\s*/, "")] as [string, string]),
  };
}

/**
 * The sections the Member 360 page answers itself, from the modules MOD-014's projection
 * cannot read.
 *
 * **MOD-014's `sections` block describes the projection, not the page.** It says
 * "MOD-017 owns this and nothing here reads it" for membership, entitlements and finance --
 * true of the projection, and paragraph 1300 is why -- and the page composes all three by
 * calling each module's own routes through its own gate. So rendering that block unfiltered
 * put "membership: nothing here reads it" directly under a Membership tab full of
 * memberships, and "finance: nothing here reads it" under a table of invoices.
 *
 * That is the same defect as the stale "not built in this repository" list this screen
 * already paid for once: a confident wrong answer where a missing one would have been
 * honest, on the page somebody opens before talking to a member. The filter is the fix, and
 * the set is pinned to the tabs by a test -- a tab added without its section leaving this
 * list would re-create the contradiction, and a section removed from here with no tab behind
 * it would hide a real gap.
 */
export const COMPOSED_SECTIONS = ["membership", "entitlements", "finance"] as const;

export function splitComposed(
  unavailable: [string, string][],
): { composed: [string, string][]; absent: [string, string][] } {
  const here = new Set<string>(COMPOSED_SECTIONS);
  return {
    composed: unavailable.filter(([name]) => here.has(name)),
    absent: unavailable.filter(([name]) => !here.has(name)),
  };
}
