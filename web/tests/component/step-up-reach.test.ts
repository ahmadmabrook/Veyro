import { describe, expect, it } from "vitest";

import { STEP_UP_CEILING, stepUpVerdict } from "@/lib/step-up";

/**
 * Three answers, because `reachable` and "this page can get you there" came apart.
 *
 * For five modules `/auth/require/{class}` answered `reachable: false` for level 3, so one
 * boolean carried both facts and a page keyed on it was right by accident. WebAuthn
 * verification made it true, and `/auth/step-up` still takes a password or a recovery code --
 * so the same page began offering a field whose correct answer is refused.
 */
describe("what a step-up can raise", () => {
  it("says the session already clears the bar", () => {
    expect(stepUpVerdict({ step_up_required: false, reachable: true, required_aal: 3 }))
      .toBe("already_enough");
  });

  it("offers the field for a level the password or recovery path reaches", () => {
    expect(stepUpVerdict({ step_up_required: true, reachable: true, required_aal: 2 }))
      .toBe("can_raise");
  });

  it("names the passkey door for a level this endpoint cannot reach", () => {
    // The whole finding: reachable, and not reachable *from here*.
    expect(stepUpVerdict({ step_up_required: true, reachable: true, required_aal: 3 }))
      .toBe("needs_a_passkey_sign_in");
  });

  it("still handles a level no factor in the build reaches", () => {
    // Nothing answers this today -- every class is reachable now -- and the branch stays,
    // because `reachable` is computed from VERIFIABLE_FACTORS and a build that removed one
    // would want the honest answer rather than a field.
    expect(stepUpVerdict({ step_up_required: true, reachable: false, required_aal: 2 }))
      .toBe("needs_a_passkey_sign_in");
  });

  it("treats a missing required level as beyond this page, not within it", () => {
    // Fail toward naming the door. A build that stopped sending the field would otherwise
    // silently offer a credential prompt for every class.
    expect(stepUpVerdict({ step_up_required: true, reachable: true }))
      .toBe("needs_a_passkey_sign_in");
  });

  it("pins the ceiling to what the endpoint accepts", () => {
    // `complete_step_up` takes a password or a recovery code, and `policy.assurance_for`
    // caps either at 2. The day it verifies an assertion this becomes 3.
    expect(STEP_UP_CEILING).toBe(2);
  });
});
