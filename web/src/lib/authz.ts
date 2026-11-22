import { api, correlationId } from "@/lib/api";

/**
 * MOD-008's reads, typed.
 *
 * **Every one of these takes a correlation id, on a GET.** That is MOD-008's convention rather
 * than an accident: the gate writes a *denial* to the hash-chained audit log itself, so a read
 * that is refused has to be joinable to the attempt that caused it. A surface that sent a
 * constant, or none, would make every refusal in the log indistinguishable from every other.
 *
 * Nothing here writes. Creating a role, granting one and deciding an approval are
 * `financial`-class permissions needing a stepped-up session, and each is a form of its own
 * rather than an inline control on a read page.
 */

export type Role = {
  role_id: string;
  role_key: string;
  display_name: string;
  description: string | null;
  /** A role this build defines rather than the tenant. Not editable from here. */
  builtin: boolean;
  version: number;
  permissions: string[];
};

export type Assignment = {
  assignment_id: string;
  role_key: string;
  scope_type: string;
  brand_id: string | null;
  location_id: string | null;
  granted_at: string;
  expires_at: string | null;
  revoked_at: string | null;
  revoked_reason: string | null;
  /**
   * Who granted it — an identity id, not a name.
   *
   * The schema calls this "the whole delegation record" and nothing had ever read it until
   * ADM-STF-02 needed the canvas's "Granted by Ziad · 4 Mar 2026". It stays an id here on
   * purpose: resolving it to a person needs `people.person.read` and the identity link, so
   * the attribution degrades to eight hex characters for a reader who may not see names
   * rather than leaking one under `authz.role.read`.
   */
  granted_by: string;
  /** The role's own display name, so a surface need not re-key `role_key`. */
  display_name: string | null;
  /**
   * Derived by the server, for MOD-018's reason: an assignment stops working when it expires
   * with nothing writing a row, so two timestamps left to each reader is a comparison every
   * reader has to get right — and the open-ended case, no expiry at all, is the one they get
   * wrong.
   */
  live: boolean;
};

export type AuditEntry = {
  sequence: number;
  category: string;
  action: string;
  outcome: string;
  actor_identity_id: string | null;
  resource_type: string | null;
  resource_id: string | null;
  detail: Record<string, unknown> | null;
  correlation_id: string;
  occurred_at: string;
};

/**
 * What the chain can say, and what it cannot.
 *
 * `verified` false names the first entry that disagrees with its link. **It detects editing,
 * not truncation**: an actor who deletes from the end *and* moves the head leaves a chain that
 * verifies, because every value the verifier compares lives in the database that actor already
 * controls. MOD-008 found that by tamper-testing rather than reasoning about it afterwards, and
 * closing it needs the head digest published somewhere the database cannot reach. The surface
 * says so beside the green answer, because a tick with no caveat is the more misleading of the
 * two.
 */
export type ChainVerdict = {
  verified: boolean;
  entries: number;
  problem: string | null;
  at: number | null;
};

export type EffectivePermissions = {
  identity_id: string;
  scope_type: string;
  brand_id: string | null;
  location_id: string | null;
  permissions: string[];
};

function withCorrelation(path: string, extra: Record<string, string> = {}): string {
  const query = new URLSearchParams({ correlation_id: correlationId(), ...extra });
  return `${path}?${query.toString()}`;
}

export function listRoles(): Promise<Role[]> {
  return api<Role[]>(withCorrelation("/authz/roles"));
}

export function listAssignments(identityId: string): Promise<Assignment[]> {
  return api<Assignment[]>(
    withCorrelation(`/authz/assignments/${encodeURIComponent(identityId)}`),
  );
}

export function readAudit(limit = 25): Promise<AuditEntry[]> {
  return api<AuditEntry[]>(withCorrelation("/authz/audit", { limit: String(limit) }));
}

export function verifyAudit(): Promise<ChainVerdict> {
  return api<ChainVerdict>(withCorrelation("/authz/audit/verify"));
}

/**
 * What an identity may do, from the evaluator's own rules.
 *
 * **The scope is derived by the server, and this is the one read where that matters most.**
 * MOD-008's review found a brand-scoped manager reaching another brand's location by sending
 * their own brand id beside it -- and the simulator *confirmed* the escalation, which is worse
 * than not having one. `resolve_scope` looks a location's brand up; this passes a location and
 * never a brand.
 */
export function simulate(
  identityId: string, locationId?: string, brandId?: string,
): Promise<EffectivePermissions> {
  return api<EffectivePermissions>(
    withCorrelation("/authz/simulate", {
      identity_id: identityId,
      // **A location's brand is derived, never sent beside it.** `resolve_scope` looks it up,
      // which is MOD-008's own "derive a scope, never accept one" -- a brand-scoped manager
      // reached another brand's location by sending their own brand id beside it, and the
      // simulator confirmed the escalation. So at most one of these travels.
      ...(locationId ? { location_id: locationId }
        : brandId ? { brand_id: brandId } : {}),
    }),
  );
}

/** Group a permission list by its leading domain, which is how a reader scans one. */
export function byDomain(permissions: string[]): [string, string[]][] {
  const groups = new Map<string, string[]>();
  for (const permission of permissions) {
    const domain = permission.split(".")[0] ?? permission;
    const list = groups.get(domain) ?? [];
    list.push(permission);
    groups.set(domain, list);
  }
  return [...groups.entries()]
    .map(([domain, list]) => [domain, list.sort()] as [string, string[]])
    .sort((a, b) => a[0].localeCompare(b[0]));
}

/**
 * The permission catalogue, and the matrix ADM-STF-04 draws from it.
 */

export type CatalogPermission = {
  name: string;
  description: string;
  category: string;
  action_class: string;
  required_aal: number;
};

export type PermissionCatalog = {
  permissions: CatalogPermission[];
  count: number;
  /** The highest assurance any session in this build can reach. */
  reachable_aal: number;
};

export function readCatalog(): Promise<PermissionCatalog> {
  return api("/authz/catalog");
}

export type Mark = "yes" | "partial" | "stepUp" | "no" | "unreachable";

/**
 * What a role's cell says for one permission.
 *
 * Four states, not the design's three, and the fourth is the one this build forced:
 *
 * - **yes** — the role holds it and an ordinary sign-in can exercise it.
 * - **stepUp** — the role holds it and using it needs a stronger sign-in. The design's
 *   middle mark is "can request approval", which MOD-008 has as a workflow and not as a
 *   per-role fact; this is the real third state here, and it is just as surprising: holding
 *   the permission is not enough.
 * - **unreachable** — the role holds it and *nobody* in this build can exercise it, because
 *   it needs assurance level 3, which a step-up cannot reach -- only a passkey sign-in. Break-glass
 *   support access and AI acting for a member are both this, deliberately. Collapsing it into
 *   `stepUp` would tell a reader to sign in more strongly for a door that does not open.
 * - **no** — the role does not hold it, "and is absent from their UI entirely", which is the
 *   design's own wording and this product's behaviour: the navigation is filtered by the gate.
 */
export function markFor(
  permission: CatalogPermission,
  heldByRole: boolean,
  reachableAal: number,
): Mark {
  if (!heldByRole) return "no";
  if (permission.required_aal > reachableAal) return "unreachable";
  return permission.required_aal > 1 ? "stepUp" : "yes";
}

/**
 * One module's worth of permissions, as a single mark for one role.
 *
 * **The default rows are modules, because 205 rows is the wall this screen was in a
 * different shape.** ADM-STF-04 draws about a dozen capabilities against nine roles, and a
 * dozen is what makes "nine roles, and what each may actually do" answerable at a glance.
 * This product's own coarse unit is the module -- `access`, `billing`, `booking` -- which is
 * also how its permission names are built and how its navigation is grouped.
 *
 * Three states, and the middle one is the honest summary: ● every permission in the module,
 * ◑ some of them, — none. Rendering "some" as either of the other two would be a lie about a
 * role, and it is the commonest case.
 *
 * The first rule written here was "show the rows the roles differ on", and it did not reduce
 * anything: with one role holding everything, every permission differs from the roles that
 * hold almost nothing. The rows have to be coarser, not fewer.
 */
export function moduleMark(
  module: string,
  permissions: CatalogPermission[],
  heldByRole: Set<string>,
): Mark {
  const inModule = permissions.filter((one) => one.name.startsWith(`${module}.`));
  if (inModule.length === 0) return "no";
  const held = inModule.filter((one) => heldByRole.has(one.name)).length;
  if (held === 0) return "no";
  return held === inModule.length ? "yes" : "partial";
}

/** Every module the catalogue has, in the order a permission name sorts. */
export function modulesOf(permissions: CatalogPermission[]): string[] {
  return [...new Set(permissions.map((one) => one.name.split(".")[0] ?? one.name))].sort();
}
