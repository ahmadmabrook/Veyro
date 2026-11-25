import { describe, expect, it } from "vitest";

import { MESSAGES, t } from "@/i18n/locale";
import {
  GRACE_KEY,
  RETRY_KEY,
  isDefaulted,
  restrictingStage,
  type DunningPolicy,
} from "@/lib/dunning";

/**
 * ADM-PAY-06's decisions, and the one state the canvas does not draw.
 *
 * The figures and the journey are the server's -- `collections.stages` produces them and
 * `test_commercial_domain.py` pins the arithmetic -- so what is here is what the screen decides
 * from them: whether a figure is a decision or the default, and which step the access grace
 * moves. Plus the catalogue, because every sentence on this screen is a key and a missing one
 * is a 500 on a rendered page rather than a blank.
 */

function policy(over: Partial<DunningPolicy> = {}): DunningPolicy {
  return {
    retry_attempts: 4,
    access_grace_days: 14,
    stages: [
      { stage: 1, days_after_due: 0, notification_key: "payment_failed",
        access_recommendation: "none" },
      { stage: 3, days_after_due: 7, notification_key: "payment_overdue_warning",
        access_recommendation: "warn" },
      { stage: 4, days_after_due: 14, notification_key: "payment_final_notice",
        access_recommendation: "restrict" },
    ],
    retry_attempts_band: [1, 20],
    access_grace_days_band: [8, 180],
    declared: [],
    account_terms_are_separate: true,
    not_settable: [],
    floor: [],
    ...over,
  };
}

describe("a default is not a decision", () => {
  it("reads an undeclared figure as the journey this build already ran", () => {
    // The same distinction MOD-005's board draws for `scope_type: "default"`: a tenant that
    // has configured nothing resolves to these figures, and only one of the two facts is
    // something to change.
    const fresh = policy();
    expect(isDefaulted(fresh, RETRY_KEY)).toBe(true);
    expect(isDefaulted(fresh, GRACE_KEY)).toBe(true);
  });

  it("reads a declared figure as a decision, even when it equals the default", () => {
    // The sharp case: four retries chosen on purpose is the same number and a different fact.
    const chosen = policy({ declared: [RETRY_KEY] });
    expect(isDefaulted(chosen, RETRY_KEY)).toBe(false);
    expect(isDefaulted(chosen, GRACE_KEY)).toBe(true);
  });
});

describe("which step the access grace moves", () => {
  it("finds the restricting step by what it recommends, not by its number", () => {
    // **Not `stages[3]`.** A reader counting rows to find it is a reader who will miscount the
    // day a step is added, and the access column is the fact the figure is about.
    expect(restrictingStage(policy())?.stage).toBe(4);
    expect(restrictingStage(policy())?.days_after_due).toBe(14);
  });

  it("has no restricting step where the server returned none", () => {
    // A journey with no `restrict` row is a shape this build does not produce, and a screen
    // that indexed into the list would render somebody else's step as the one being set.
    expect(restrictingStage(policy({ stages: [] }))).toBeUndefined();
  });
});

describe("every sentence on this screen exists in both catalogues", () => {
  it("has the Arabic for each key, because there is no fallback to English", () => {
    // `t` throws for a missing key rather than returning it, so a gap is a 500 on a rendered
    // page. The floor rules and the unsettable reasons are built from server codes, so their
    // keys are the ones a sweep over `text("literal")` would never see.
    const keys = Object.keys(MESSAGES.en).filter((key) => key.startsWith("dunning."));
    expect(keys.length).toBeGreaterThan(25);
    for (const key of keys) {
      for (const locale of ["en", "ar"] as const) {
        const entry = MESSAGES[locale][key as keyof typeof MESSAGES.en];
        expect(entry, `${locale} ${key}`).toBeDefined();
      }
    }
  });

  it("has a key for every floor rule and every absence the server names", () => {
    // **The server returns codes rather than sentences**, so these are the keys the screen
    // renders them through -- and a code with no key is the one failure that reaches a reader
    // as an error page rather than as a missing line.
    for (const rule of ["never_block_access_without_a_person",
                        "never_message_outside_business_hours",
                        "never_more_than_one_reminder_a_week",
                        "never_charge_a_removed_card"]) {
      expect(t("ar", `dunning.floor.${rule}` as keyof typeof MESSAGES.en)).toBeTruthy();
    }
    for (const setting of ["retry_hour", "draft_message_held_for_approval",
                           "exception_threshold"]) {
      expect(t("ar", `dunning.not_settable.${setting}` as keyof typeof MESSAGES.en))
        .toBeTruthy();
    }
    for (const waits of ["a_scheduled_dunning_run", "a_dispatcher",
                         "a_case_written_by_collections"]) {
      expect(t("ar", `dunning.waits.${waits}` as keyof typeof MESSAGES.en)).toBeTruthy();
    }
    for (const access of ["none", "warn", "restrict", "suspend"]) {
      expect(t("ar", `dunning.access.${access}` as keyof typeof MESSAGES.en)).toBeTruthy();
    }
  });
});
