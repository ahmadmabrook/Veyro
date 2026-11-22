"use client";

import { useSyncExternalStore } from "react";

import { available } from "@/lib/passkey";

/**
 * Whether this browser can run a WebAuthn ceremony, read in a way that survives hydration.
 *
 * **Not `useState` and not an effect.** `available()` reads `window`, so computing it during
 * render gives `false` on the server and `true` on the client -- a hydration mismatch, which
 * React answers by discarding the subtree. Setting it from an effect works and the linter
 * refuses it, correctly: a value computable from the environment is not state. The third
 * argument of `useSyncExternalStore` is the *server* snapshot, which is precisely this
 * question, and the subscribe is a no-op because the answer cannot change inside a session.
 *
 * **Its own module because two screens ask it** -- the account page's enrolment and the
 * sign-in page's button -- and two copies of one question is two answers the day either
 * moves, which is the rule this repository applies to a balance and to a retry curve.
 */
const NEVER_CHANGES = () => () => {};

export function useCeremonyAvailable(): boolean {
  return useSyncExternalStore(NEVER_CHANGES, available, () => false);
}
