/**
 * What a step-up can actually raise a session to.
 *
 * **`reachable` and "this page can get you there" are two different facts, and they came
 * apart the hour WebAuthn verification landed.** `/auth/require/{class}` answers `reachable`
 * from `VERIFIABLE_FACTORS`: for five modules it was false for level 3, because a privileged
 * action needs a hardware authenticator and nothing checked a signature. It is true now. But
 * `/auth/step-up` takes a password or a recovery code -- `complete_step_up` accepts nothing
 * else -- and `policy.assurance_for` caps either at 2, so the route to level 3 is signing in
 * at `/auth/passkey/login` rather than raising the session you are holding.
 *
 * So a page keyed on `reachable` alone now offers a field that cannot succeed. That is worse
 * than the gap it replaced: the old answer was "nobody can do this here", which was true and
 * final, and the new one would be a credential prompt whose correct answer is still refused.
 * **A control with no route is this app's standing complaint about a button that answers 403**,
 * and the remedy is the same -- say which door it is and point at it.
 *
 * The ceiling is a constant rather than a second read because it is a property of the
 * endpoint's own signature: the day `complete_step_up` verifies an assertion, this becomes 3
 * and the branch below stops firing, which is the one change that should move it.
 */

/** The highest assurance `/auth/step-up` can reach, from the factors it accepts. */
export const STEP_UP_CEILING = 2;

/**
 * Three answers, because they are three different facts with three different remedies:
 * the session already clears the bar, this page can raise it, or the level exists and is
 * reached by a different door.
 */
export type StepUpVerdict = "already_enough" | "can_raise" | "needs_a_passkey_sign_in";

export function stepUpVerdict(asked: {
  step_up_required: boolean;
  reachable: boolean;
  required_aal?: number;
}): StepUpVerdict {
  if (!asked.step_up_required) return "already_enough";
  // **An absent `required_aal` is treated as beyond this page**, not as within it. The field
  // has been on the response since MOD-007 was built; a build that stopped sending it would
  // otherwise silently offer the field for every class, and a prompt that cannot succeed is
  // the failure this module exists to prevent. Fail toward saying which door it is.
  const needed = typeof asked.required_aal === "number" ? asked.required_aal : Infinity;
  if (!asked.reachable || needed > STEP_UP_CEILING) return "needs_a_passkey_sign_in";
  return "can_raise";
}
