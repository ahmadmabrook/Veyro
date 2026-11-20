/**
 * MOD-007's reads, typed: this session, the devices it came from, the other sessions open on
 * this account, and what the authentication log says happened.
 *
 * **Every one of these is scoped to the caller's own identity by the route, not by this
 * module.** `owned(session, identity_id)` refuses anything that is not the session's own with
 * a 404 -- which is also why those routes need no permission: there is nothing to authorize
 * when the only readable subject is yourself. MOD-007's review found the opposite shipped,
 * where password changes, recovery-code issuing and session listing were open to anyone
 * holding the tenant UUID.
 *
 * **The fetchers live in `account-reads.ts`.** This module holds types and decisions and
 * imports nothing, because the account page is the first client component in this app and a
 * client component that reaches a module touching `next/headers` fails the build. The split
 * is the one the backend makes between `domain` and `service`.
 *
 * **A session token never passes through here.** MOD-007 stores a session only as a SHA-256
 * digest, so there is nothing to render even if a page wanted to, and the list identifies a
 * session by its id, its device and when it was last seen.
 */

export type SessionFact = {
  session_id: string;
  device_id: string | null;
  aal: number;
  factors: string[];
  issued_at: string;
  expires_at: string;
  last_seen_at: string | null;
  revoked_at: string | null;
  revoke_reason: string | null;
};

export type DeviceFact = {
  device_id: string;
  label: string;
  platform: string | null;
  trusted: boolean;
  /** Confirmed by a login that needed no challenge, or by one whose challenge was answered. */
  confirmed: boolean;
  first_seen_at: string;
  last_seen_at: string;
  revoked_at: string | null;
  revoked_reason: string | null;
};

export type AuthEvent = {
  identity_id: string | null;
  kind: string;
  outcome: string;
  factor: string | null;
  reason: string | null;
  occurred_at: string;
};

/**
 * Whether a session is still usable, which is two facts rather than one.
 *
 * Revoked is explicit and expiry is a comparison, and a board that showed only the first would
 * list a fortnight-old session as live. The expiry is compared against the server's own clock
 * through the string, not the browser's: both are ISO-8601 in UTC, and lexical comparison of
 * those is chronological -- which avoids a timezone question the browser would otherwise
 * answer differently from the server that issued it.
 */
export function sessionIsLive(session: SessionFact, nowIso: string): boolean {
  return session.revoked_at === null && session.expires_at > nowIso;
}

/**
 * How much a session can do, said as the thing it decides rather than as a number.
 *
 * Level 1 is a password; level 2 is a second factor and is what every financial action needs;
 * level 3 needs a hardware authenticator MOD-007 cannot verify, so nothing in this build
 * reaches it. Rendering "3" as an option a reader might aim for would send them looking for a
 * key the product cannot check.
 */
export function assuranceMeans(aal: number): "password" | "stepped_up" | "unreachable" {
  if (aal >= 3) return "unreachable";
  if (aal >= 2) return "stepped_up";
  return "password";
}

/**
 * Whether this session may mint new recovery codes.
 *
 * **Issuing codes needs real proof, not a session cookie.** `_issue_codes_in_tx` takes the
 * current password or a stepped-up session and nothing else -- and deliberately *not* the
 * recovery allowance that `set_password` has, because MOD-007's second review found a stolen
 * recovery session minting ten fresh codes with no password, and those codes surviving the
 * owner's own password reset. A page that offered the button to a level-1 session would be
 * offering an action the server will refuse.
 */
export function mayIssueRecoveryCodes(aal: number): boolean {
  return aal >= 2;
}

/**
 * The device the session reading this page came from, or null when it is not on the list.
 *
 * **It has to be marked, because revoking it is the one irreversible button on this page.**
 * `_authenticate_in_tx` refuses a revoked device at login outright -- it records
 * `device.readmission_refused` and answers the same 401 as a wrong password -- and the
 * fingerprint this app sends is derived from the tenant and the identifier, so the next
 * attempt produces the same value and is refused again. Revoking the device you are reading
 * this in therefore signs you out at once and locks this browser out for good, and the member
 * cannot tell afterwards why they are being refused.
 *
 * Null is a real answer rather than an error: the session list is filtered to live sessions
 * and bounded, and a session can carry no device at all.
 */
export function currentDeviceId(sessions: SessionFact[], sessionId: string): string | null {
  const mine = sessions.find((s) => s.session_id === sessionId);
  return mine?.device_id ?? null;
}

/**
 * A device a member would want to look twice at.
 *
 * Unconfirmed means a login from it was challenged and the challenge was never answered --
 * which is what an attacker holding the password looks like, and what a member who gave up
 * halfway also looks like. The page says which fact it is rather than calling it suspicious.
 */
export function needsAttention(device: DeviceFact): boolean {
  return device.revoked_at === null && !device.confirmed;
}
