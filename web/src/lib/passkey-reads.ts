import { api } from "@/lib/api";

import type { PasskeyFact } from "@/lib/passkey";

/**
 * The I/O half of the passkey surface. **Separate from `passkey.ts` because a client component
 * imports those decisions**, and a client component that reaches a module touching
 * `next/headers` fails the whole app's build -- which this repository has paid for once, when
 * the account page's first version made the *login* page answer 500.
 */

export function listPasskeys(identityId: string): Promise<PasskeyFact[]> {
  return api(`/identities/${encodeURIComponent(identityId)}/passkeys`);
}

export type OwnIdentity = {
  identity_id: string;
  display_name: string;
  email: string | null;
  phone: string | null;
  status: string;
  created_at: string;
};

/**
 * Who this session is.
 *
 * **It exists for the ceremony rather than for the page.** An authenticator shows `user.name`
 * when somebody later picks between credentials, and with no route returning the signed-in
 * person's own display name the only value available was the identity uuid.
 */
export function readOwnIdentity(identityId: string): Promise<OwnIdentity> {
  return api(`/identities/${encodeURIComponent(identityId)}`);
}
