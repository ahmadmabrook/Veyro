import { api, correlationId } from "@/lib/api";
import type { Assignment, CatalogPermission, Role } from "@/lib/authz";
import type { MessageKey } from "@/i18n/locale";

/**
 * ADM-STF-01 and ADM-STF-02: the team, and one person's access.
 *
 * **Three planes, three permissions, and that is why the judgements are here.** A staff
 * profile is MOD-014's under `veyro_cp_app`; the role is MOD-008's and the login is MOD-007's,
 * both under `veyro_iam_app`, which holds nothing in `plt01`. So no query can answer the
 * design's four columns and the surface composes them — exactly as the Member 360 composes
 * membership and money onto a person, and for the stronger reason that a reader may hold any
 * subset of the three. "Nobody has a role" and "you may not see who does" are different
 * facts, and only the composing layer knows which one it is looking at.
 *
 * Pure, because most of these states are unreachable from one fixture. `standingOf` has six
 * answers and a seeded tenant renders two of them; `splitRole`'s tie-breaks need four
 * assignments on one person. That is the surface-branch vacuity this repository has shipped
 * four times, and the remedy is the one it already uses: the classification is a function and
 * the page renders what it returns.
 */

export type StaffRow = {
  person_id: string;
  legal_name: string;
  preferred_name: string | null;
  staff_profile_id: string;
  job_title: string | null;
  employment_state: string;
  started_on: string | null;
  ended_on: string | null;
  location_id: string | null;
  location_name: string | null;
  version: number;
  /** The handle the role and login composition is made with. Null means no login exists. */
  identity_id: string | null;
};

export type StaffList = {
  staff: StaffRow[];
  matching: number;
  total: number;
  by_state: Record<string, number>;
  limit: number;
  states: string[];
  columns_this_module_cannot_answer: Record<string, string>;
  invited_is_not_a_state_here: string;
  certifications_are_not_recorded: string;
  the_location_filter_is_not_a_boundary: string;
};

export type StaffProfile = {
  staff_profile_id: string;
  person_id: string;
  job_title: string | null;
  employment_state: string;
  started_on: string | null;
  ended_on: string | null;
  location_id: string | null;
  location_name: string | null;
  version: number;
  updated_at: string;
  identity_id: string | null;
  the_home_location_is_not_the_scope: string;
};

export type LastSeen = {
  identity_id: string;
  status: string;
  last_seen_at: string | null;
  live_sessions: number;
  no_device_or_address_is_returned: string;
};

export function readStaff(
  params: { employment_state?: string; location_id?: string; limit?: number } = {},
): Promise<StaffList> {
  const query = new URLSearchParams();
  if (params.employment_state) query.set("employment_state", params.employment_state);
  if (params.location_id) query.set("location_id", params.location_id);
  query.set("limit", String(params.limit ?? 50));
  return api(`/staff?${query.toString()}`);
}

export function readStaffProfile(personId: string): Promise<StaffProfile> {
  return api(`/staff/${personId}`);
}

/**
 * The role each of several identities holds, in one request.
 *
 * **Batched because a list has fifty rows.** Asking per row is fifty round trips against
 * MOD-011's 600-a-minute `api.request` budget, which the browser suite has already tripped
 * once — the reason `/authz/checks` exists. An empty list asks nothing at all rather than
 * sending a request whose answer is known.
 */
export async function readAssignments(
  identityIds: string[],
): Promise<Map<string, Assignment[]>> {
  if (identityIds.length === 0) return new Map();
  const query = new URLSearchParams({ correlation_id: correlationId() });
  for (const id of identityIds) query.append("identity_id", id);
  const body: { assignments: Record<string, Assignment[]> } =
    await api(`/authz/assignments?${query.toString()}`);
  return new Map(Object.entries(body.assignments));
}

export async function readLastSeen(identityIds: string[]): Promise<Map<string, LastSeen>> {
  if (identityIds.length === 0) return new Map();
  const query = new URLSearchParams({ correlation_id: correlationId() });
  for (const id of identityIds) query.append("identity_id", id);
  const body: { identities: Record<string, LastSeen> } =
    await api(`/identities/last-seen?${query.toString()}`);
  return new Map(Object.entries(body.identities));
}

/**
 * The employment vocabulary, as words.
 *
 * `active`, `suspended` and `ended` are column values, and a stored value rendered where a
 * label belongs is Latin letters mid-line in the Arabic build — the mistake this repository
 * made four times in one pass and which `MESSAGE_KEYS` is structurally blind to, because it
 * compares the two catalogues against each other and cannot see a string that never became a
 * key. An unmapped value falls through to its raw form rather than to "other": the set is the
 * schema's and this is a screen somebody filters and acts on.
 */
export function stateName(state: string): MessageKey | null {
  switch (state) {
    case "active":
      return "staff.state.active";
    case "suspended":
      return "staff.state.suspended";
    case "ended":
      return "staff.state.ended";
    default:
      return null;
  }
}

/**
 * Where a staff member stands, as a combination of employment and access.
 *
 * **The design states the column's purpose and it is a control, not a timestamp**: "Last seen
 * exists so a departed employee with a live login is visible rather than discovered." So the
 * useful answer is the pair, and `endedWithAccess` is the one that needs somebody today.
 *
 * Six answers because the pair has six meanings, and three of them are ordinary rather than
 * wrong:
 *
 * - **working** — employed, has a login, has used it.
 * - **workingNeverUsed** — employed with a login nobody has signed in with. An onboarding
 *   that stalled, which reads identically to a working account on a column showing only a
 *   date.
 * - **workingNoLogin** — employed with no identity link at all. Not a defect: a cleaner on
 *   the payroll needs no account, and MOD-014's link is the only thing relating the planes.
 * - **endedWithAccess** — **the finding.** Employment ended and something still opens.
 * - **ended** — employment ended and nothing does, which is the state a leaver should be in.
 * - **unknown** — this reader holds `people.person.read` and not `identity.identity.read`,
 *   so the access half is not theirs to see. Rendering it as `ended` would tell an owner a
 *   departed employee has no access when nobody has checked.
 */
export type Standing =
  | "working"
  | "workingNeverUsed"
  | "workingNoLogin"
  | "endedWithAccess"
  | "ended"
  | "unknown";

export function standingOf(
  row: Pick<StaffRow, "employment_state" | "identity_id">,
  seen: LastSeen | null,
): Standing {
  const employed = row.employment_state !== "ended";
  if (row.identity_id === null) return employed ? "workingNoLogin" : "ended";
  // **One guard, not two.** The first version also took a `mayReadLogins` flag and refused
  // on it -- and the mutation sweep showed that branch was unreachable, because a caller who
  // may not look passes no `seen` either, so the next line already answers. That is this
  // repository's own "a control subsumed by its sibling" finding, and the remedy is the one
  // it records: delete the redundant statement rather than contrive a case for it. A
  // parameter the function cannot act on is a claim its signature makes and does not keep.
  // **No row for a linked identity is not "no access".** `ppl_identity_links` carries no
  // foreign key into `iam` — the planes are separate and MOD-014 says a stale link is
  // possible — so an id that answers nothing may be a link to an identity that is gone, or
  // one in a tenant this read could not reach. Either way nobody has checked.
  if (seen === null) return "unknown";
  const live = seen.live_sessions > 0 || seen.status === "active";
  if (!employed) return live ? "endedWithAccess" : "ended";
  if (seen.last_seen_at === null) return "workingNeverUsed";
  return "working";
}

export function standingName(standing: Standing): MessageKey {
  return `staff.standing.${standing}` as MessageKey;
}

/**
 * How loudly a standing is drawn.
 *
 * Only one of the six is a fault, and saying so is the whole point: a board that coloured
 * every non-ideal state would bury the one that needs somebody. `workingNeverUsed` is a
 * warning because a stalled onboarding is somebody who cannot do their job; the rest are
 * ordinary.
 */
export function standingSeverity(standing: Standing): "critical" | "attention" | null {
  if (standing === "endedWithAccess") return "critical";
  if (standing === "workingNeverUsed") return "attention";
  return null;
}

/** The rows whose access does not match their employment. The design's warning box. */
export function accessFindings(
  rows: StaffRow[],
  seen: Map<string, LastSeen> | null,
): StaffRow[] {
  if (seen === null) return [];
  return rows.filter(
    (row) => standingOf(row, seen.get(row.identity_id ?? "") ?? null) === "endedWithAccess",
  );
}

/**
 * Which assignment is the job, and which are beyond it.
 *
 * **ADM-STF-02's two halves need a baseline and this build's baseline is the role.** The
 * canvas draws `ROLE: Reception` and under it `INDIVIDUAL GRANTS · BEYOND HER ROLE` with an
 * attribution on each. There are no per-identity grants here — a permission comes from a role
 * and a role is held through an assignment — so "beyond her role" is the person's *additional*
 * assignments, each of which carries `granted_by` and `granted_at` by schema. That is the
 * canvas's line exactly, and it is a fact rather than a reconstruction.
 *
 * **The primary is the broadest scope, earliest granted.** The job is the widest thing
 * somebody was hired to do and a narrow extra grant is the exception; ordering has to be total
 * or the screen's two halves change between reads, which is MOD-018's `chart_for` finding.
 * Revoked and expired assignments are not in either half: `live` is derived by the server
 * precisely so every reader does not have to compare two timestamps and get the open-ended
 * case wrong.
 */
const SCOPE_BREADTH: Record<string, number> = { tenant: 3, brand: 2, location: 1 };

export function splitRole(assignments: Assignment[]): {
  primary: Assignment | null;
  beyond: Assignment[];
  lapsed: Assignment[];
} {
  const live = assignments.filter((one) => one.live);
  const lapsed = assignments.filter((one) => !one.live);
  const ordered = [...live].sort((a, b) => {
    const breadth = (SCOPE_BREADTH[b.scope_type] ?? 0) - (SCOPE_BREADTH[a.scope_type] ?? 0);
    if (breadth !== 0) return breadth;
    const when = a.granted_at.localeCompare(b.granted_at);
    if (when !== 0) return when;
    // Total, so two assignments granted in the same transaction order the same way twice.
    return a.assignment_id.localeCompare(b.assignment_id);
  });
  const [primary, ...beyond] = ordered;
  return { primary: primary ?? null, beyond, lapsed };
}

/**
 * The CLUBS row: where a person's live assignments reach.
 *
 * **Not the staff profile's own location.** That column is where somebody works and the
 * profile read says so in as many words; what they may *reach* is their assignments' scopes,
 * which is the authority every gate decision is actually made against. Rendering the home
 * location under a heading the design uses for reach would be the confident wrong answer.
 *
 * A tenant-scoped assignment outranks every named one, because it already covers them: a
 * chip list showing "Khalda, Abdoun" beside a tenant-wide grant would understate it.
 */
export type Reach =
  | { kind: "tenant" }
  | { kind: "named"; brands: string[]; locations: string[] }
  | { kind: "none" };

export function reachOf(assignments: Assignment[]): Reach {
  const live = assignments.filter((one) => one.live);
  if (live.length === 0) return { kind: "none" };
  if (live.some((one) => one.scope_type === "tenant")) return { kind: "tenant" };
  const brands = [...new Set(live.flatMap((one) => one.brand_id ? [one.brand_id] : []))];
  const locations = [
    ...new Set(live.flatMap((one) => one.location_id ? [one.location_id] : [])),
  ];
  return { kind: "named", brands: brands.sort(), locations: locations.sort() };
}

/**
 * The permissions worth putting on a staff record, and what each costs to use.
 *
 * **`action_class` is the catalogue's own judgement about danger** and it is written per
 * permission rather than derived, because each one is a decision — a wrong `routine` is a real
 * defect and a test caught one. So "which of this person's permissions matter" needs no new
 * rule: it is the held set filtered to `financial` and `privileged`, which is the same
 * distinction `permit` charges a step-up for.
 *
 * **`unreachable` is the third state, and the canvas has no mark for it.** A `privileged`
 * permission needs assurance level 3, which needs a hardware authenticator MOD-007 cannot
 * verify — so break-glass support access and an AI acting for a member are granted, recorded,
 * and exercisable by nobody in this build. Drawing those as held would tell an owner somebody
 * can do something no session can.
 */
export type GrantReach = "usable" | "needsStepUp" | "unreachable";

export type SensitiveGrant = {
  permission: CatalogPermission;
  reach: GrantReach;
  /** The live assignments whose role carries it — the canvas's "Granted by … · date". */
  carriers: Assignment[];
  /** The scopes it is actually held at. Never empty: a grant held nowhere is not held. */
  scopes: ScopeRef[];
};

/**
 * One scope to ask the permission simulator about.
 *
 * **The simulator answers about a scope, and asking only about the default one hides exactly
 * the grants this block exists to show.** `authz.permissions_of` lets a broad assignment cover
 * a narrow scope and never the reverse, so a location-scoped role contributes *nothing* at the
 * tenant-wide default -- and a narrow grant is what "beyond her role" usually is. The first
 * version of this page asked once, at the default scope, and the fixture's own
 * location-scoped refund grant was missing from the list while every tenant-wide one was
 * there. **Found by reading the rendered page**, which is how four of this surface's defects
 * have been found.
 *
 * So the page asks once per distinct scope among the person's live assignments -- bounded by
 * the assignment count, and the only honest answer to "what can this person do, anywhere".
 * MOD-014's standing gap, that a narrowly scoped role cannot use that module at all, is this
 * same finding one module over.
 */
export type ScopeRef = {
  /** Stable and comparable: `"tenant"`, `"brand:<id>"` or `"location:<id>"`. */
  key: string;
  kind: "tenant" | "brand" | "location";
  id: string | null;
};

export function scopesToSimulate(assignments: Assignment[]): ScopeRef[] {
  const out = new Map<string, ScopeRef>();
  for (const one of assignments) {
    if (!one.live) continue;
    if (one.scope_type === "tenant") {
      out.set("tenant", { key: "tenant", kind: "tenant", id: null });
    } else if (one.scope_type === "brand" && one.brand_id) {
      out.set(`brand:${one.brand_id}`,
              { key: `brand:${one.brand_id}`, kind: "brand", id: one.brand_id });
    } else if (one.scope_type === "location" && one.location_id) {
      out.set(`location:${one.location_id}`,
              { key: `location:${one.location_id}`, kind: "location", id: one.location_id });
    }
  }
  // Tenant first, then brands, then locations, each in key order -- so two reads of one
  // record agree. By rank rather than by a chain of ternaries: the first version answered 1
  // for both `compare(brand, location)` and `compare(location, brand)`, which is not a
  // comparator at all and whose result depends on the engine's sort.
  const rank = { tenant: 0, brand: 1, location: 2 } as const;
  return [...out.values()].sort((a, b) =>
    rank[a.kind] - rank[b.kind] || a.key.localeCompare(b.key));
}

export function grantReach(
  permission: CatalogPermission,
  reachableAal: number,
): GrantReach {
  if (permission.required_aal > reachableAal) return "unreachable";
  return permission.required_aal > 1 ? "needsStepUp" : "usable";
}

export function sensitiveGrants(
  heldByScope: { scope: ScopeRef; permissions: string[] }[],
  catalog: CatalogPermission[],
  reachableAal: number,
  assignments: Assignment[],
  roles: Role[],
): SensitiveGrant[] {
  const where = new Map<string, ScopeRef[]>();
  for (const { scope, permissions } of heldByScope) {
    for (const name of permissions) {
      const at = where.get(name) ?? [];
      if (!at.some((one) => one.key === scope.key)) at.push(scope);
      where.set(name, at);
    }
  }
  const byKey = new Map(roles.map((role) => [role.role_key, role]));
  const live = assignments.filter((one) => one.live);
  return catalog
    .filter((one) => where.has(one.name))
    .filter((one) => one.action_class === "financial" || one.action_class === "privileged")
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((permission) => ({
      permission,
      reach: grantReach(permission, reachableAal),
      carriers: live.filter(
        (one) => byKey.get(one.role_key)?.permissions.includes(permission.name) ?? false,
      ),
      scopes: where.get(permission.name) ?? [],
    }));
}

/**
 * Why there are no unticked rows, said once so the page can say it.
 *
 * The canvas draws `☐ Override access denials` and `☐ Export member data` beside the ticked
 * one, which implies a known candidate set a person is measured against. There is none here:
 * a permission exists if a role carries it, and every role is the tenant's own, so the
 * "capabilities somebody could have" is the whole 200-entry catalogue. Rendering two of those
 * as the interesting absences would be inventing the product's own idea of a sensitive
 * capability, which is the one thing the delegation does not cover.
 */
export const NO_UNTICKED_ROWS = "staff.grants.whyNoUnticked" satisfies MessageKey;

/**
 * The keys this module maps to, for the parity test.
 *
 * `MESSAGE_KEYS` compares the two catalogues against each other and is blind to a key a
 * module maps to that exists in neither — so each module asserts its own, which is the parity
 * check run from the side the catalogue cannot see.
 */
export function keysInPlay(): MessageKey[] {
  const standings: Standing[] = [
    "working", "workingNeverUsed", "workingNoLogin", "endedWithAccess", "ended", "unknown",
  ];
  return [
    ...standings.map(standingName),
    ...["active", "suspended", "ended"].map((s) => stateName(s)!),
    NO_UNTICKED_ROWS,
    "staff.reach.tenant", "staff.reach.none",
    "staff.grantEverywhere", "staff.notApplicableNoLogin", "staff.catalogueIsEnglish",
    "staff.restricted", "staff.unanswered",
    "staff.grant.usable", "staff.grant.needsStepUp", "staff.grant.unreachable",
  ];
}
