import { describe, expect, it } from "vitest";

import { MESSAGE_KEYS } from "@/i18n/locale";
import {
  OVERRIDE_REASONS, SAY, isDeviceFault, isOverrideReason, latestRefusal, overrideKey,
  overrideOffer, overriddenSince, sayFor, type AccessDecision,
} from "@/lib/denial";

/**
 * FD-03's decisions: which refusal the screen is about, what a receptionist can say, and
 * what they are offered about the override.
 *
 * **Decisions rather than rendered branches.** Nineteen refusal codes and four override
 * states cannot be produced from a browser fixture -- a zone at capacity, a reader with a
 * wrong clock and a replayed credential each need a door this build cannot drive -- so the
 * states are constructed here.
 */

const decision = (over: Partial<AccessDecision> = {}): AccessDecision => ({
  decision_id: "d-1",
  point_id: "pt-1",
  zone_id: "z-1",
  person_id: "p-1",
  granted: false,
  code: "membership_inactive",
  public_reason: "please see the front desk",
  private_reason: null,
  // **The server's own field name.** It was `masked` here and in the type, and the server
  // has never sent that: the offer to read why a member was refused never rendered, and a
  // hand-written type over an untyped JSON response is invisible to every typecheck. Found
  // by a browser test asking for the link.
  reason_withheld: true,
  bucket: "policy",
  decided_at: "2026-11-22T04:07:00Z",
  ...over,
});

describe("which refusal the screen is about", () => {
  it("is the newest one, because a desk is holding the person now", () => {
    const rows = [
      decision({ decision_id: "old", decided_at: "2026-11-22T03:00:00Z" }),
      decision({ decision_id: "new", decided_at: "2026-11-22T04:07:00Z" }),
    ];
    expect(latestRefusal(rows)?.decision_id).toBe("new");
  });

  it("is never a grant, however recent", () => {
    // A member whose card worked an hour after it failed is not somebody to talk to, and a
    // screen that opened on a grant would explain nothing.
    const rows = [
      decision({ decision_id: "refused" }),
      decision({
        decision_id: "ok", granted: true, code: "granted",
        decided_at: "2026-11-22T05:00:00Z",
      }),
    ];
    expect(latestRefusal(rows)?.decision_id).toBe("refused");
  });

  it("is null where nothing was refused, rather than the first row", () => {
    expect(latestRefusal([decision({ granted: true, code: "granted" })])).toBeNull();
    expect(latestRefusal([])).toBeNull();
  });
});

describe("whether somebody already let them in", () => {
  const refusal = decision({ decided_at: "2026-11-22T04:07:00Z" });

  it("notices an override after the refusal", () => {
    // The override is "a decision in its own right rather than a flag on one", so the screen
    // has to read the log rather than the refusal to know it has been answered.
    const rows = [refusal, decision({
      decision_id: "over", granted: true, code: "granted_by_override",
      decided_at: "2026-11-22T04:09:00Z",
    })];
    expect(overriddenSince(rows, refusal)?.decision_id).toBe("over");
  });

  it("ignores one from before it, which answered a different refusal", () => {
    const rows = [refusal, decision({
      decision_id: "earlier", granted: true, code: "granted_by_override",
      decided_at: "2026-11-22T03:00:00Z",
    })];
    expect(overriddenSince(rows, refusal)).toBeNull();
  });

  it("ignores an ordinary grant, which is the door working rather than a decision", () => {
    const rows = [refusal, decision({
      decision_id: "ok", granted: true, code: "granted",
      decided_at: "2026-11-22T04:09:00Z",
    })];
    expect(overriddenSince(rows, refusal)).toBeNull();
  });
});

describe("what a receptionist can say", () => {
  it("has a sentence for every code this module writes", () => {
    // A reviewer grepped the writers of all twenty codes and found nineteen, so a map with
    // an entry for the twentieth would be a sentence nobody could ever read.
    for (const code of [
      "credential_unknown", "credential_revoked", "credential_expired",
      "credential_replayed", "credential_window", "reader_clock_unreliable",
      "outside_opening_hours", "zone_closed", "membership_inactive", "no_entitlement",
      "outstanding_balance", "age_restricted", "safety_hold", "anti_passback",
      "zone_at_capacity", "device_untrusted", "point_not_an_entry",
    ]) {
      expect(sayFor(code), code).not.toBeNull();
    }
  });

  it("has one for the code a restricted refusal carries outward", () => {
    // **The one a desk sees most.** `see_front_desk` is what the five restricted reasons
    // become for a session without the private read, and its sentence says that rather than
    // pretending to explain.
    expect(sayFor("see_front_desk")).toBe("denial.say.seeFrontDesk");
  });

  it("says nothing rather than guessing at a code it does not know", () => {
    // The page falls back to the module's own public reason, which is a sentence the module
    // wrote. Inventing one here would be a surface explaining a refusal it cannot read.
    expect(sayFor("something_new")).toBeNull();
  });

  it("every sentence it names exists in both languages", () => {
    for (const key of Object.values(SAY)) {
      expect(MESSAGE_KEYS, key).toContain(key);
    }
  });

  it("tells a door's fault from a member's, because the next sentence differs", () => {
    // A revoked card and a reader with a wrong clock are both "denied" and nothing else
    // about them is alike: one is a conversation with the member, the other with whoever
    // maintains the device.
    expect(isDeviceFault("reader_clock_unreliable")).toBe(true);
    expect(isDeviceFault("device_untrusted")).toBe(true);
    expect(isDeviceFault("membership_inactive")).toBe(false);
    expect(isDeviceFault("outstanding_balance")).toBe(false);
  });
});

describe("what the reader is offered about the override", () => {
  const gate = (allowed: boolean, verdict = "denied") => ({ allowed, verdict });

  it("offers the form to a session that may act", () => {
    expect(overrideOffer(gate(true), false)).toBe("form");
  });

  it("offers a step-up to one that could after a stronger sign-in", () => {
    expect(overrideOffer(gate(false, "needs_step_up"), false)).toBe("step_up");
  });

  it("offers neither where the gate said no", () => {
    // **"Never a locked control with no route."** The button is absent, which is the
    // canvas's own instruction; naming who to call is the half this build cannot do.
    expect(overrideOffer(gate(false, "denied"), false)).toBe("denied");
    expect(overrideOffer(gate(false, "gate_failed"), false)).toBe("denied");
  });

  it("says it is already done before it says anything about permission", () => {
    // Offering the button twice would admit somebody twice in the log, and offering a
    // step-up for work already finished sends a receptionist to find a recovery code for
    // nothing.
    expect(overrideOffer(gate(true), true)).toBe("already");
    expect(overrideOffer(gate(false, "needs_step_up"), true)).toBe("already");
    expect(overrideOffer(gate(false, "denied"), true)).toBe("already");
  });
});

describe("the three reasons the canvas names", () => {
  it("accepts exactly those three", () => {
    for (const reason of OVERRIDE_REASONS) expect(isOverrideReason(reason)).toBe(true);
    expect(isOverrideReason("because I said so")).toBe(false);
    expect(isOverrideReason("")).toBe(false);
  });

  it("names each of them in both languages", () => {
    for (const reason of OVERRIDE_REASONS) {
      expect(MESSAGE_KEYS, reason).toContain(`denial.reason.${reason}`);
    }
  });
});

describe("what the write is keyed on", () => {
  it("is the refusal, so the same press twice is one admission", () => {
    expect(overrideKey("d-1")).toBe("override-d-1");
  });

  it("is a different key for a later refusal, which was the defect", () => {
    // **The key was `(point, person, reason)`.** `override_access` answers a repeated key
    // from the row it already wrote, so a member refused today and admitted by hand, then
    // refused again tomorrow and admitted for the same reason, produced no second row: the
    // desk was told it had worked and the log showed one override for two admissions.
    expect(overrideKey("monday")).not.toBe(overrideKey("tuesday"));
  });

  it("does not change with the reason, so a second press cannot double the record", () => {
    // Two presses with two reasons would write two rows saying somebody was let in once.
    expect(overrideKey("d-1")).toBe(overrideKey("d-1"));
  });
});
