import { api } from "@/lib/api";

import type { AuthEvent, DeviceFact, SessionFact } from "@/lib/account";

/**
 * MOD-007's reads. **Separated from the decisions in `account.ts` because a client component
 * imports those.**
 *
 * This is the first page in the app with forms whose results render in place, so it is the
 * first client component -- and a client component importing a module that reaches
 * `next/headers` fails the build outright, because that API exists only on the server. The
 * web libraries had been mixing decisions with I/O everywhere and nothing noticed, since every
 * other page renders on the server and stays there.
 *
 * The split is the one the backend already makes in every module: `domain` decides and does no
 * I/O, `service` holds the transactions. Here `account.ts` decides what a session means and
 * this file fetches.
 */

/**
 * The sessions still open on this account, newest first and bounded.
 *
 * **`live_only`, because a member asking "where am I signed in" means the ones that work.**
 * A revoked or expired row is the evidence a sign-out happened, which is what somebody
 * investigating an account wants and not what somebody managing theirs does. The route had
 * neither the filter nor a bound until this page asked for them: `iam.sessions` has no DELETE
 * grant and a row is written on every sign-in *and* every rotation, so the unbounded read
 * returned every session an identity had ever held.
 */
export function listSessions(identityId: string, limit = 20): Promise<SessionFact[]> {
  return api(
    `/identities/${encodeURIComponent(identityId)}/sessions` +
      `?live_only=true&limit=${limit}`,
  );
}

export function listDevices(identityId: string): Promise<DeviceFact[]> {
  return api(`/identities/${encodeURIComponent(identityId)}/devices`);
}

/**
 * The caller's own authentication log, bounded to what a person reads.
 *
 * The route defaults to a hundred, which is a reasonable API default and the wrong page: an
 * account screen showing a hundred rows is scrolled past rather than read. Twenty is the
 * recent history somebody checks after a suspicious email, and the page says that is what it
 * asked for rather than implying it is everything.
 */
export function listAuthEvents(limit = 20): Promise<AuthEvent[]> {
  return api(`/auth/events?limit=${limit}`);
}
