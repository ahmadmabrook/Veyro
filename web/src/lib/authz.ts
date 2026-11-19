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
export function simulate(identityId: string, locationId?: string): Promise<EffectivePermissions> {
  return api<EffectivePermissions>(
    withCorrelation("/authz/simulate", {
      identity_id: identityId,
      ...(locationId ? { location_id: locationId } : {}),
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
