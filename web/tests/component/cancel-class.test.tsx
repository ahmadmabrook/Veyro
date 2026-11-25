import { describe, expect, it } from "vitest";

import { MESSAGES, fill, t, type MessageKey } from "@/i18n/locale";
import {
  CANCELLATION_REASONS, missingFields, noticeDays, noticeKey, offerable,
} from "@/lib/cancel-class";

/**
 * ADM-SCH-07's decisions, and every sentence it renders.
 *
 * The allocation and the credit window are the server's -- `plan_moves` and `credit_expires`
 * are pinned by `tests/test_booking_domain.py` and by 21 Python mutations -- so what is here
 * is what the screen decides from them, plus the catalogue: a key the Arabic side is missing,
 * or a placeholder one form drops, is a 500 on a rendered page rather than a blank, and the
 * parity checks are blind to a message nobody renders.
 */

describe("ADM-SCH-07's notice", () => {
  it("counts whole days in one frame", () => {
    // Both dates come from the club's own zone, which is the point: this build has three
    // recorded defects from a date computed in one frame and compared against another.
    expect(noticeDays("2026-11-26", "2026-11-25")).toBe(1);
    expect(noticeDays("2026-11-25", "2026-11-25")).toBe(0);
    expect(noticeDays("2026-12-05", "2026-11-25")).toBe(10);
  });

  it("survives a clock change, because it compares calendar dates", () => {
    // Britain's spring forward is 29 March 2026: a day that is 23 real hours long is still
    // one calendar day to the member being told about it.
    expect(noticeDays("2026-03-29", "2026-03-28")).toBe(1);
    expect(noticeDays("2026-10-26", "2026-10-25")).toBe(1);
  });

  it("gives a class in the past its own sentence rather than a negative count", () => {
    expect(noticeKey(-2)).toBe("cancelClass.noticePast");
    expect(noticeKey(0)).toBe("cancelClass.noticeToday");
    expect(noticeKey(1)).toBe("cancelClass.noticeTomorrow");
    expect(noticeKey(2)).toBe("cancelClass.noticeDays");
  });

  it("never renders a negative day count", () => {
    // The guard is the key, not the arithmetic: `cancelClass.noticeDays` takes a count and
    // "This is in -2 days" is not a sentence. MOD-019 admits cancelling a session whose time
    // has gone -- the status is what it turns on, not the clock.
    for (const days of [-30, -1]) {
      expect(noticeKey(days)).toBe("cancelClass.noticePast");
    }
  });
});

describe("ADM-SCH-07's required remedy", () => {
  it("is the canvas's own REQUIRED", () => {
    expect(missingFields("", "")).toEqual({ remedy: true });
  });

  it("asks for a destination only for a move", () => {
    expect(missingFields("move", "")).toEqual({ destination: true });
    expect(missingFields("move", "s1")).toEqual({});
    expect(missingFields("credit", "")).toEqual({});
  });
});

describe("ADM-SCH-07's destination list", () => {
  it("leaves out the class being cancelled", () => {
    expect(offerable({ session_id: "a", status: "scheduled" }, "a")).toBe(false);
    expect(offerable({ session_id: "b", status: "scheduled" }, "a")).toBe(true);
  });

  it("leaves out a class that cannot take anybody", () => {
    // The command refuses a cancelled destination, and a control the screen can see for
    // itself is one it should not make a reader discover.
    for (const status of ["cancelled", "completed"]) {
      expect(offerable({ session_id: "b", status }, "a")).toBe(false);
    }
  });
});

describe("ADM-SCH-07's catalogue", () => {
  const KEYS: MessageKey[] = [
    "cancelClass.open", "cancelClass.keepIt", "cancelClass.why",
    "cancelClass.whyGoesIntoTheMessage", "cancelClass.whyChoose",
    "cancelClass.whyNeeded", "cancelClass.whyUnstated",
    "cancelClass.remedyMove", "cancelClass.remedyCredit", "cancelClass.remedyNeeded",
    "cancelClass.moveTo", "cancelClass.moveToChoose", "cancelClass.moveToNeeded",
    "cancelClass.chooseFirst", "cancelClass.reading", "cancelClass.creditUnavailable",
    "cancelClass.theyWillReceive", "cancelClass.eachLanguage",
    "cancelClass.findACoach", "cancelClass.raise",
    "cancelClass.refused", "cancelClass.conflict", "cancelClass.noCredit",
    "cancelClass.twoCredits", "cancelClass.needsStepUp",
    "cancelClass.doneTitle", "cancelClass.nobodyTold", "cancelClass.backToSession",
    "cancelClass.noticePast", "cancelClass.noticeToday", "cancelClass.noticeTomorrow",
  ];

  it("has every plain sentence in both languages", () => {
    for (const key of KEYS) {
      for (const locale of ["en", "ar"] as const) {
        expect(t(locale, key).length, `${locale} ${key}`).toBeGreaterThan(0);
      }
    }
  });

  it("has a label for each of MOD-019's six declared reasons", () => {
    // A vocabulary the backend stores is never a label -- five instances in this build, the
    // last of them the design system's own badge. So every code the select offers has a word.
    for (const code of CANCELLATION_REASONS) {
      for (const locale of ["en", "ar"] as const) {
        expect(t(locale, `cancelClass.reason.${code}` as MessageKey).length,
          `${locale} ${code}`).toBeGreaterThan(0);
      }
    }
  });

  it("renders every plural form in both languages", () => {
    // Arabic has six categories and a missing one falls back to `other`, which renders a
    // plural where Arabic wants a dual. These counts reach all six.
    const plural: MessageKey[] = [
      "cancelClass.noticeDays", "cancelClass.whatTheyGet", "cancelClass.wouldChoose",
      "cancelClass.someIneligible", "cancelClass.someAlreadyThere",
      "cancelClass.eachLanguageWaitlist", "cancelClass.commit", "cancelClass.doneMoved",
      "cancelClass.doneCredited", "cancelClass.doneMustChoose",
    ];
    for (const key of plural) {
      for (const locale of ["en", "ar"] as const) {
        for (const count of [0, 1, 2, 3, 11, 100]) {
          expect(fill(locale, key, { count }, "latn").length,
            `${locale} ${key} ${count}`).toBeGreaterThan(0);
        }
      }
    }
  });

  it("renders the two message bodies and the two-count sentences", () => {
    for (const locale of ["en", "ar"] as const) {
      expect(fill(locale, "cancelClass.messageMove", {
        name: "Spin", why: "no coach", day: "2026-11-27", time: "19:00",
      }).length).toBeGreaterThan(0);
      expect(fill(locale, "cancelClass.messageCredit", {
        name: "Spin", why: "no coach", days: 30,
      }, "latn").length).toBeGreaterThan(0);
      expect(fill(locale, "cancelClass.counts",
        { booked: 18, waiting: 3 }, "latn").length).toBeGreaterThan(0);
      expect(fill(locale, "cancelClass.doneCounts",
        { released: 18, waiting: 3 }, "latn").length).toBeGreaterThan(0);
      expect(fill(locale, "cancelClass.title", { name: "Spin" }).length)
        .toBeGreaterThan(0);
      expect(fill(locale, "cancelClass.creditEach", { days: 30 }, "latn").length)
        .toBeGreaterThan(0);
      expect(fill(locale, "cancelClass.moveWithCoach",
        { coach: "Dana", free: 6 }, "latn").length).toBeGreaterThan(0);
      expect(fill(locale, "cancelClass.moveNoCoach", { free: 6 }, "latn").length)
        .toBeGreaterThan(0);
    }
  });

  it("states the canvas's own figures", () => {
    // "6 places free · 12 would need to choose another" and "within 30 days", in the words a
    // reader sees -- the numbers are the server's and these are the sentences around them.
    expect(fill("en", "cancelClass.moveWithCoach", { coach: "Dana", free: 6 }, "latn"))
      .toContain("6");
    expect(fill("en", "cancelClass.wouldChoose", { count: 12 }, "latn")).toContain("12");
    expect(fill("en", "cancelClass.creditEach", { days: 30 }, "latn")).toContain("30");
  });

  it("names the notification as the one thing the screen cannot do", () => {
    // The canvas calls the notification the action rather than a follow-up, and the command
    // sends nothing -- so the sentence has to say so rather than let a reader assume.
    for (const locale of ["en", "ar"] as const) {
      expect(t(locale, "cancelClass.nobodyTold").length).toBeGreaterThan(20);
    }
  });

  it("has no Arabic-only key, which the parity check cannot see from the English side", () => {
    const en = Object.keys(MESSAGES.en).filter((key) => key.startsWith("cancelClass."));
    const ar = Object.keys(MESSAGES.ar).filter((key) => key.startsWith("cancelClass."));
    expect(ar.sort()).toEqual(en.sort());
  });
});
