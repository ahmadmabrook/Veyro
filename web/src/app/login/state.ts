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
  missing: { tenant: boolean; identifier: boolean; password: boolean };
  /** Echoed so a refused attempt does not clear a field nobody mistyped. Never the password. */
  tenantId: string;
  identifier: string;
};

export const SIGN_IN_IDLE: SignInState = {
  error: null,
  missing: { tenant: false, identifier: false, password: false },
  tenantId: "",
  identifier: "",
};
