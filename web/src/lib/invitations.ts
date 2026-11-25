/**
 * ADM-STF-03's types and the decisions over them. ADR-0017.
 *
 * **This module imports nothing**, because the invite form is a client component: a module
 * whose exports are pure while its top-level import reaches `@/lib/api` is still impure to a
 * bundler, and this build has five recorded instances of that taking every page in the app to
 * a 500 with `tsc` and the linter green. The reads live in `invitations-reads.ts`.
 */

/** The three shapes `role_assignments` admits, which an invitation's clubs become. */
export type ScopeType = "tenant" | "brand" | "location";

export type InvitationScope = {
  scope_type: ScopeType;
  brand_id: string | null;
  location_id: string | null;
};

export type InvitationState = "pending" | "accepted" | "revoked" | "expired";

export type Invitation = {
  invitation_id: string;
  email: string;
  role_key: string;
  role_name: string;
  expires_at: string;
  created_at: string;
  created_by: string;
  state: InvitationState;
  /** Whole days, rounded up, and zero for anything that is not pending. */
  days_left: number;
  accepted_at: string | null;
  revoked_at: string | null;
  revoke_reason: string | null;
  supersedes_invitation_id: string | null;
  scopes: InvitationScope[];
};

export type InvitationList = {
  invitations: Invitation[];
  count: number;
  as_of: string;
  sent: boolean;
  pending_is_derived: string;
};

export type InvitationMade = {
  invitation_id: string;
  /** Returned once and never stored: only its digest is in the table. */
  token: string;
  expires_at: string;
  created_at: string;
  email: string;
  role_key: string;
  sent: boolean;
  note: string;
};

/** The canvas's default, which the server applies and the screen states. */
export const EXPIRY_DAYS = 7;

/**
 * What a role lets somebody do, as the three facts the canvas's sentence is made of.
 *
 * The canvas writes it as prose — "Sales can see leads and members at those two clubs, sell
 * memberships, and take payments. No financial administration." — and two of those three are
 * derivable rather than written: the clubs are the picker's own answer, and **"no financial
 * administration" is the catalogue's `action_class`**, which is a checkable claim about the
 * role rather than a sentence somebody typed. The middle part is the role's own `description`,
 * which `iam.roles` carries and `create_role` writes; where a tenant has written none, the
 * count of permissions is the honest substitute.
 */
export function roleReach(
  role: { description: string | null; permissions: string[] } | null,
  catalog: { name: string; action_class: string }[],
): { description: string | null; permissions: number; financial: number } {
  if (role === null) return { description: null, permissions: 0, financial: 0 };
  const held = new Set(role.permissions);
  return {
    description: role.description,
    permissions: role.permissions.length,
    financial: catalog.filter(
      (one) => held.has(one.name)
        && (one.action_class === "financial" || one.action_class === "privileged"),
    ).length,
  };
}

/**
 * Whether the form can be sent, and what is missing when it cannot.
 *
 * **At least one club, because "no scope" is not "everywhere".** `permissions_of` lets a broad
 * assignment cover a narrow scope and never the reverse, so an assignment with no scope grants
 * nothing at all — which is the service's own refusal and one the screen can see for itself.
 */
export function missingFields(
  email: string, roleKey: string, clubs: readonly string[], tenantWide: boolean,
): { email?: true; role?: true; clubs?: true } {
  const missing: { email?: true; role?: true; clubs?: true } = {};
  // A shape check, not a validation: the server normalizes and the constraint refuses, and a
  // second address grammar here would be a rule two layers can disagree about.
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) missing.email = true;
  if (roleKey.length === 0) missing.role = true;
  if (!tenantWide && clubs.length === 0) missing.clubs = true;
  return missing;
}

/** The canvas's "2d left" and "expired", as a key rather than a sentence built here. */
export function stateKey(
  invitation: Invitation,
): "invite.statePending" | "invite.stateExpired" | "invite.stateAccepted"
  | "invite.stateRevoked" {
  switch (invitation.state) {
    case "accepted": return "invite.stateAccepted";
    case "revoked": return "invite.stateRevoked";
    case "expired": return "invite.stateExpired";
    default: return "invite.statePending";
  }
}

/**
 * Which invitations the canvas's "PENDING · 2" counts.
 *
 * **Expired ones are in the list and pending ones are the count**, which is what the canvas
 * draws: `omar.s@nadi.jo` reads "expired" with a Resend beside it, so it is on screen and is
 * not pending. The server returns both because neither is settled — an expired invitation
 * still holds its address, and the remedy is a resend.
 */
export function pendingCount(list: readonly Invitation[]): number {
  return list.filter((one) => one.state === "pending").length;
}

/** A club an invitation names, for the row's own line. */
export function clubNames(
  scopes: readonly InvitationScope[],
  locations: readonly { location_id: string; location_name: string }[],
): { tenantWide: boolean; names: string[] } {
  if (scopes.some((scope) => scope.scope_type === "tenant")) {
    return { tenantWide: true, names: [] };
  }
  const byId = new Map(locations.map((one) => [one.location_id, one.location_name]));
  return {
    tenantWide: false,
    names: scopes
      .flatMap((scope) => (scope.location_id === null ? [] : [scope.location_id]))
      .map((id) => byId.get(id) ?? id)
      .sort(),
  };
}
