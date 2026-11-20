/**
 * What the account page's four actions can say back.
 *
 * **Recovery codes are the one result that is not a message.** They are shown once and never
 * again -- MOD-007 stores only a hash -- so they travel back through the action's return and
 * are rendered once, and the page says plainly that reloading will not show them again. They
 * are never written to a cookie, a URL or storage.
 */
export type AccountState = {
  /** A message key, so the result is translated like everything else on these surfaces. */
  message: "account.revoked" | "account.trusted" | "account.codesIssued" | null;
  error: "account.refused" | "account.needsStepUp" | "error.network" | null;
  /** Rendered once, then gone. Never persisted anywhere by this app. */
  codes: string[];
  /**
   * The revoke killed the session that made the request, so this browser is signed out.
   *
   * Revoking a device revokes every session on it, and the device a member is reading this
   * page in is on the list like any other -- so the most consequential button here can end
   * the session that pressed it. The action asks the server whether it still has one rather
   * than trusting a hidden field, and the page it returns to is the sign-in page.
   */
  signedOut?: boolean;
};

export const IDLE: AccountState = { message: null, error: null, codes: [] };
