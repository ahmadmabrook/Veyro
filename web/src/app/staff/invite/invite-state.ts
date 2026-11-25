/**
 * What ADM-STF-03's three writes can say back.
 *
 * Types only, so the client component can import it — the split five modules in this build
 * record, the last of which took every page in the app to a 500 with `tsc` green.
 */
import type { InvitationMade } from "@/lib/invitations";

export type InviteState = {
  message: "sent" | "resent" | "withdrawn" | null;
  /**
   * A refusal the form could see for itself, or one only the server could.
   *
   * `invite.taken` and `invite.hasIdentity` are their own values because the next step
   * differs and a reader can act on both: withdraw the live one, or grant the role to the
   * identity that already exists. `invite.cannotGrant` is the escalation rule, whose next
   * step is somebody else doing it. Everything else shares one sentence, which is
   * ADM-MSH-07's reasoning about not declaring a value a reader cannot use.
   */
  error: "invite.refused" | "invite.taken" | "invite.hasIdentity"
    | "invite.cannotGrant" | "invite.needsStepUp" | "invite.settled"
    | "error.network" | "error.tooMany" | null;
  missing: { email?: true; role?: true; clubs?: true; reason?: true };
  echo: { email?: string; roleKey?: string };
  /**
   * The link, which exists in one HTTP response and nowhere else.
   *
   * **Rendered in place rather than redirected to**, which is the account page's recovery
   * codes exactly: only the digest is stored, so carrying the plaintext through a redirect
   * would mean writing a bearer credential into a query string or a cookie to survive one.
   */
  made: InvitationMade | null;
};

export const IDLE: InviteState = {
  message: null, error: null, missing: {}, echo: {}, made: null,
};
