import type { MessageKey } from "@/i18n/locale";

/**
 * The step-up form's state, in its own module for `login/state.ts`'s reason: a `"use server"`
 * module may export async functions and nothing else, so a constant beside the action arrives
 * at the client as `undefined`.
 */
export type StepUpError = Extract<
  MessageKey,
  "stepUp.failed" | "stepUp.tooMany" | "stepUp.unreachable" | "error.network" | "error.unexpected"
>;

/** The second factor this session can actually present. Derived from the server, never guessed. */
export type SecondFactor = "recovery_code" | "password";

export type StepUpState = {
  error: StepUpError | null;
  /** The field was left empty. Rendered beside the field, so it is correct with no JavaScript. */
  missing: boolean;
};

export const STEP_UP_IDLE: StepUpState = { error: null, missing: false };
