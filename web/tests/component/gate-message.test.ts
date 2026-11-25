import { describe, expect, it } from "vitest";

import { MESSAGES } from "@/i18n/locale";
import { gateMessage, gateVerdict, UNREACHED, type GateAnswer } from "@/lib/api";

/**
 * **A refusal and a failure are different facts, and this app told the first story about
 * four of them.** `gate` and `gateAll` fail closed -- an unreachable gate is not permission,
 * which is right for access and does not change -- so a transport failure reaches a page in
 * exactly the shape of a refusal. Twenty-three places then rendered "Not permitted", which
 * reports a fault as a statement about the reader's access: somebody who believes it goes
 * and asks for a grant they already hold.
 */
const answer = (over: Partial<GateAnswer>): GateAnswer => ({
  action: "finance.revenue.read",
  allowed: false,
  reason: "forbidden",
  step_up_required: false,
  required_aal: null,
  reachable: true,
  // ADR-0014. `tenant_wide: true` is the ordinary caller: every page in this app assumed one
  // and the gate's `allowed` is narrowed to that case, so a builder that defaulted it false
  // would be testing a reader this app has never had.
  tenant_wide: true,
  scopes: [],
  allowed_anywhere: false,
  masked_fields: [],
  ...over,
});

describe("gateVerdict", () => {
  it("calls a request that got no answer a failure, not a refusal", () => {
    for (const reason of UNREACHED) {
      expect(gateVerdict(answer({ reason })), reason).toBe("gate_failed");
    }
  });

  it("calls the gate saying no a refusal", () => {
    expect(gateVerdict(answer({ reason: "forbidden" }))).toBe("denied");
  });

  it("separates a level a step-up cannot reach from one it would", () => {
    // `member.health.read` is `biometric_sensitive`, which maps to AAL 3, and `/auth/step-up`
    // takes a password or a recovery code: neither gets past 2. MOD-008 computes `reachable`
    // from those two factors, so this verdict means "a different door", not "no door".
    expect(gateVerdict(answer({ reachable: false, required_aal: 3 })))
      .toBe("unreachable_level");
    expect(gateVerdict(answer({ step_up_required: true, required_aal: 2 })))
      .toBe("needs_step_up");
  });

  it("reads the failure before the assurance, because a failure knows neither", () => {
    // A failed request carries whatever defaults the client filled in. Judging it on those
    // would report a dead gate as "not available in this build".
    expect(gateVerdict(answer({ reason: "unreachable", reachable: false })))
      .toBe("gate_failed");
  });
});

describe("gateMessage", () => {
  it("gives each of the four states its own words, in both languages", () => {
    const keys = new Set(
      [
        answer({ reason: "unreachable" }),
        answer({ reachable: false }),
        answer({ step_up_required: true }),
        answer({ reason: "forbidden" }),
      ].map(gateMessage),
    );
    // Four states, four distinct messages: any two sharing one is the defect returning.
    expect(keys.size).toBe(4);
    for (const key of keys) {
      expect(MESSAGES.en[key], `${key} missing from English`).toBeTruthy();
      expect(MESSAGES.ar[key], `${key} missing from Arabic`).toBeTruthy();
    }
  });

  it("does not say 'not permitted' when nothing refused anything", () => {
    // The sentence the defect produced, asserted against directly.
    const failed = gateMessage(answer({ reason: "unreachable" }));
    expect(failed).toBe("gate.failed");
    expect(MESSAGES.en[failed]).not.toMatch(/not permitted/i);
    expect(MESSAGES.en[failed]).toMatch(/not a limit on your access/i);
  });
});
