import type { MessageKey } from "@/i18n/locale";

/**
 * The sign-in form's state, in its own module.
 *
 * **Not in `actions.ts`, because a `"use server"` module may only export async functions.** A
 * constant exported beside the action compiles, type-checks and builds, and then arrives at the
 * client as `undefined` -- so `useActionState`'s initial value was undefined and the form threw
 * `Cannot read properties of undefined` on its first render. Nothing warned; the failure was a
 * 500 on the page itself. A type-only export survives (it is erased), which is what makes the
 * mistake easy: the types line up perfectly and the value is gone.
 */
export type SignInError = Extract<
  MessageKey,
  "login.failed" | "login.challenge" | "login.tooMany" | "error.network" | "error.unexpected"
>;

export type SignInState = {
  /** A message key the form resolves in the reader's own locale. Never a server string. */
  error: SignInError | null;
  missing: { tenant: boolean; identifier: boolean; password: boolean; recovery: boolean };
  /** Echoed so a refused attempt does not clear a field nobody mistyped. Never the password. */
  tenantId: string;
  identifier: string;
  /**
   * **The nonce MOD-007 returns when it challenges a login**, carried so the form can offer
   * somewhere to answer it.
   *
   * The first version of this page rendered "this sign-in needs a recovery code" and gave the
   * reader no field to type one in -- which is, exactly, the defect MOD-007's own review
   * records: "there was no endpoint to answer one at all, so it was unanswerable by an honest
   * user and free to skip for an attacker." The endpoint exists; the surface did not use it,
   * which is the same dead end one layer up. Found by signing in from a browser after the
   * fixture had signed in from a script, which is two devices and exactly what triggers it.
   *
   * It is not a secret -- it is a one-use nonce bound to the identity and the device -- so a
   * hidden field is the right place for it. The recovery code the reader types never goes
   * anywhere but the request body.
   */
  challenge: string | null;
};

export const SIGN_IN_IDLE: SignInState = {
  error: null,
  missing: { tenant: false, identifier: false, password: false, recovery: false },
  tenantId: "",
  identifier: "",
  challenge: null,
};
