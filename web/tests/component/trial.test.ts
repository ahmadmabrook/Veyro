import { describe, expect, test } from "vitest";

import { MESSAGES } from "@/i18n/locale";
import type { TrialCard } from "@/lib/leads";
import { engagementWord } from "@/lib/leads";
import { urgencyKey, usageSentence } from "@/lib/trial";

/**
 * ADM-CRM-05's sentence and its band word.
 *
 * **A builder that refuses an impossible card**, which this app has one recorded defect from:
 * a hand-written unit fixture encoding a state the server cannot produce put a dead branch
 * behind a green assertion for a whole commit. `ends_tomorrow` and `days_left` are two facts
 * the server derives from one window, so the combinations it cannot emit throw here.
 */
const CARD = (over: Partial<Extract<TrialCard, { on_trial: true }>> = {}) => {
  const card: Extract<TrialCard, { on_trial: true }> = {
    on_trial: true,
    lead_id: "l1",
    person_id: "p1",
    stage: "new",
    membership_id: "m1",
    starts_on: "2026-08-15",
    ends_on: "2026-08-21",
    trial_days: 7,
    visits: 4,
    classes: 4,
    day_of: 6,
    of_days: 7,
    days_left: 2,
    ends_tomorrow: true,
    engagement: "high",
    ...over,
  };
  // The server's own arithmetic: `ends_tomorrow` is exactly `days_left === 2`, because both
  // count today. A card claiming one without the other is a card no window produces.
  if (card.ends_tomorrow !== (card.days_left === 2)) {
    throw new Error("the server cannot emit ends_tomorrow out of step with days_left");
  }
  if (card.day_of > card.of_days) {
    throw new Error("a trial cannot be on a day past its own length");
  }
  return card;
};

describe("the trial card's one sentence", () => {
  test("the builder refuses a card the server cannot emit", () => {
    expect(() => CARD({ ends_tomorrow: false })).toThrow();
    expect(() => CARD({ days_left: 5 })).toThrow();
    expect(() => CARD({ day_of: 9 })).toThrow();
  });

  test("the canvas's own case is the conversion sentence", () => {
    // "She has used the trial more than most -- this is a conversion, not a chase."
    expect(usageSentence(CARD())).toBe("trial.usedItWell");
  });

  test("nobody having been in gets its own sentence rather than a softer one", () => {
    expect(usageSentence(CARD({ engagement: "none", visits: 0 })))
      .toBe("trial.notUsed");
  });

  test("the two middle bands share the sentence that asks what would help", () => {
    for (const band of ["light", "steady"]) {
      expect(usageSentence(CARD({ engagement: band }))).toBe("trial.usedItSome");
    }
  });

  test("the urgency line has three states and the server picks", () => {
    expect(urgencyKey(CARD())).toBe("trial.endsTomorrow");
    expect(urgencyKey(CARD({ ends_tomorrow: false, days_left: 1 })))
      .toBe("trial.endsToday");
    expect(urgencyKey(CARD({ ends_tomorrow: false, days_left: 4, day_of: 4 })))
      .toBe("trial.running");
  });

  test("every band has a word in both catalogues", () => {
    // **`MESSAGE_KEYS` is blind to a string that never became a key**, so the map is swept
    // here: a band rendered as its stored value is Latin letters in an Arabic line, which
    // this app has five recorded defects from.
    for (const band of ["none", "light", "steady", "high"]) {
      const key = engagementWord(band);
      expect(key).not.toBeNull();
      expect(MESSAGES.en[key!]).toBeTruthy();
      expect(MESSAGES.ar[key!]).toBeTruthy();
    }
    expect(engagementWord("whatever-the-server-grows")).toBeNull();
  });

  test("every sentence this module can return exists in both catalogues", () => {
    const keys = new Set<string>();
    for (const band of ["none", "light", "steady", "high"]) {
      keys.add(usageSentence(CARD({ engagement: band })));
    }
    keys.add(urgencyKey(CARD()));
    keys.add(urgencyKey(CARD({ ends_tomorrow: false, days_left: 1 })));
    keys.add(urgencyKey(CARD({ ends_tomorrow: false, days_left: 4, day_of: 4 })));
    for (const key of keys) {
      expect(MESSAGES.en[key as keyof typeof MESSAGES.en]).toBeTruthy();
      expect(MESSAGES.ar[key as keyof typeof MESSAGES.ar]).toBeTruthy();
    }
  });
});
