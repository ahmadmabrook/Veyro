import { describe, expect, it } from "vitest";

import {
  DETECTION_MIN_DIGITS,
  detectionFor,
  digitsIn,
  holdReason,
  interruption,
  isAbout,
  knownFrom,
  mayCreate,
  missingFields,
  recognitionParts,
  worthChecking,
  type ContactMatch,
  type DetectionAnswerFor,
  type MatchResult,
} from "@/lib/walk-in";
import { monthYearLabel } from "@/lib/time";

/**
 * ADM-MEM-10's decisions. What a duplicate means and what it costs is the server's; what is
 * here is when to ask, what to do with an answer, and when the button is held.
 *
 * **Decisions rather than a rendered branch, which this repository has a rule for.** A
 * surface branch no fixture can reach is vacuity one layer up, and it has happened four times
 * in four modules — the freeze form's "this contract allows no freezing" was the fourth, and
 * extracting `affordanceFor` is what made every branch of it testable. The same shape here:
 * `detectionFor` and `mayCreate` are the whole behaviour, and a browser test cannot reach the
 * failed-check state at all without taking the backend down.
 */

const match = (over: Partial<ContactMatch> = {}): ContactMatch => ({
  person_id: "p-1",
  legal_name: "Hala Barakat",
  preferred_name: null,
  known_since: "2025-02-11",
  lifecycle_state: "active",
  member_number: "M-03918",
  joined_on: "2025-02-11",
  is_primary: true,
  ...over,
});

const result = (count = 1, over: Partial<ContactMatch> = {}): MatchResult => ({
  matches: [match(over)], count, more: false,
});

describe("when the check is worth running", () => {
  it("counts digits and nothing else, because spelling is the server's rule", () => {
    // The whole module's premise: `normalize_contact` is MOD-007's normalizer and it is what
    // the write stores and the match compares. A rule here would be a second one, which is
    // the shape MOD-011's review found in a limiter.
    expect(digitsIn("+962 79 662 4180")).toBe(12);
    expect(digitsIn("(079) 662-4180")).toBe(10);
    expect(digitsIn("not a number")).toBe(0);
  });

  it("waits for a number somebody could have finished typing", () => {
    expect(worthChecking("07966")).toBe(false);
    expect(worthChecking("0796624")).toBe(true);
    expect(DETECTION_MIN_DIGITS).toBe(7);
  });

  it("is about length and not about format", () => {
    // Seven digits spelled any way is seven digits. A format rule here would withhold the
    // check from exactly the spellings the normalizer exists to collapse.
    expect(worthChecking("+962 79 662 4180")).toBe(true);
    expect(worthChecking("962-79-662-4180")).toBe(true);
  });
});

describe("the state derived from what is in the field", () => {
  it("is idle when the field is empty and too short while it is being typed", () => {
    expect(detectionFor("", null).kind).toBe("idle");
    expect(detectionFor("079", null).kind).toBe("tooShort");
  });

  it("is checking until an answer about THIS value arrives", () => {
    const stale: DetectionAnswerFor = { value: "0796624180", outcome: "clear" };
    expect(detectionFor("0796624180", stale).kind).toBe("clear");
    // **The race, made impossible rather than guarded.** The first version stored the state
    // and compared each reply against a ref; miss that guard and a clear number reads as
    // duplicated, or worse, a duplicated one reads as clear. An answer carries the value it
    // was about, so it is simply not the answer to any other.
    expect(detectionFor("0796624181", stale).kind).toBe("checking");
  });

  it("keeps a match and a failure apart, because their remedies differ", () => {
    const found: DetectionAnswerFor = {
      value: "0796624180", outcome: "match", result: result(),
    };
    expect(detectionFor("0796624180", found).kind).toBe("found");
    expect(detectionFor("0796624180", { value: "0796624180", outcome: "unknown" }).kind)
      .toBe("failed");
  });

  it("answers about the trimmed value only", () => {
    expect(isAbout(detectionFor("0796624180", null), "0796624180")).toBe(true);
    expect(isAbout({ kind: "idle" }, "")).toBe(false);
  });
});

describe("the interruption to show", () => {
  /**
   * **One function, because there were two.** The form computed "a match about this value
   * that nobody has acknowledged" inline for the banner while `mayCreate` computed it again
   * for the button, and the browser mutation sweep found it the first time it ran: breaking
   * the comparison in one left the other intact. Both read it here now.
   */
  const A = "0796624180";
  const B = "0796624181";
  const found = (value: string): DetectionAnswerFor =>
    ({ value, outcome: "match", result: result() });

  it("shows a match nobody has answered about", () => {
    expect(interruption(detectionFor(A, found(A)), null, A)).not.toBeNull();
  });

  it("goes away once somebody answers about that value", () => {
    expect(interruption(detectionFor(A, found(A)), A, A)).toBeNull();
  });

  it("comes back for the next number, which is the whole point of keying it", () => {
    // An acknowledgement of one number that hid the interruption for another would be worse
    // than no acknowledgement at all.
    expect(interruption(detectionFor(B, found(B)), A, B)).not.toBeNull();
  });

  it("is nothing while the answer is about some other value", () => {
    expect(interruption(detectionFor(B, found(A)), null, B)).toBeNull();
  });
});

describe("whether the record may be created", () => {
  const found = (value = "0796624180"): DetectionAnswerFor =>
    ({ value, outcome: "match", result: result() });

  it("waits while a check is in flight", () => {
    expect(mayCreate({ kind: "checking", value: "x" }, null, "x")).toBe(false);
    expect(holdReason({ kind: "checking", value: "x" }, null, "x")).toBe("checking");
  });

  it("goes ahead when the number is free", () => {
    expect(mayCreate({ kind: "clear", value: "x" }, null, "x")).toBe(true);
    expect(holdReason({ kind: "clear", value: "x" }, null, "x")).toBeNull();
  });

  it("holds on a match until somebody says it is a different person", () => {
    // **A duplicate interrupts rather than blocks.** Two records for one person is sometimes
    // right — a shared family line is the ordinary case — and paragraph 10200 requires a
    // human to decide rather than a threshold.
    const state = detectionFor("0796624180", found());
    expect(mayCreate(state, null, "0796624180")).toBe(false);
    expect(holdReason(state, null, "0796624180")).toBe("duplicate");
    expect(mayCreate(state, "0796624180", "0796624180")).toBe(true);
  });

  it("withdraws the acknowledgement when the number changes", () => {
    // **The defect this is written against.** "Different person" answers *this* number; a
    // dismissal that survived an edit would be a dismissal of a different one, and the next
    // thing typed would go in with the banner hidden.
    //
    // **Derived the way the form derives it**, which is the whole state and not a handmade
    // one: with the field holding a new number, the old answer is not an answer about it, so
    // the state is `checking` and the button waits. A test that built a `found` state about
    // a value the field no longer holds would be asserting against a state this screen
    // cannot produce.
    const stale = detectionFor("0796624181", found());
    expect(stale.kind).toBe("checking");
    expect(mayCreate(stale, "0796624180", "0796624181")).toBe(false);
  });

  it("holds a check that could not run, and says so differently", () => {
    // "We do not know" and "it is free" are different facts. Treating an unreachable check as
    // clear turns a network blip into a silent duplicate, which is "a control consulted once
    // is a control with a window" in a surface.
    const failed = detectionFor("0796624180", { value: "0796624180", outcome: "unknown" });
    expect(mayCreate(failed, null, "0796624180")).toBe(false);
    expect(holdReason(failed, null, "0796624180")).toBe("unknown");
    // And it is the same escape hatch, because there is nothing else a person can do.
    expect(mayCreate(failed, "0796624180", "0796624180")).toBe(true);
  });
});

describe("the fields a walk-in needs", () => {
  it("wants a name and a usable number", () => {
    expect(missingFields({ name: "", phone: "0796624180" })).toEqual({ name: true });
    expect(missingFields({ name: "  ", phone: "0796624180" })).toEqual({ name: true });
    expect(missingFields({ name: "Hala", phone: "079" })).toEqual({ phone: true });
    expect(missingFields({ name: "Hala", phone: "0796624180" })).toEqual({});
  });

  it("does not want an email or a birth date", () => {
    // A walk-in who gives neither is the ordinary case, and refusing them would send them
    // away. `POST /people` requires neither either.
    expect(missingFields({ name: "Hala", phone: "0796624180" })).toEqual({});
  });
});

describe("how a matched record is recognised", () => {
  it("names what this module holds and not what it does not", () => {
    // The canvas writes "· Club · Sweifieh · joined Feb 2025", and the plan is MOD-017's
    // while a home club is a concept no module in this build has. The read says so rather
    // than letting a surface render an empty part as a fact.
    expect(recognitionParts(match())).toEqual(["M-03918"]);
    expect(recognitionParts(match({ member_number: null }))).toEqual([]);
  });

  it("falls back to when the record was known, not to nothing", () => {
    expect(knownFrom(match())).toBe("2025-02-11");
    expect(knownFrom(match({ joined_on: null }))).toBe("2025-02-11");
    expect(knownFrom(match({ joined_on: null, known_since: "2024-12-30" })))
      .toBe("2024-12-30");
  });

  it("writes the date as the canvas does, in both locales", () => {
    expect(monthYearLabel("2025-02-11", "en")).toBe("Feb 2025");
    // Arabic gets Arabic, which is the whole reason a stored vocabulary is never a label.
    expect(monthYearLabel("2025-02-11", "ar")).not.toBe("Feb 2025");
  });

  it("is UTC-pinned, so the first of a month is not the month before", () => {
    // `monthDayLabel`'s own subtlety: a bare YYYY-MM-DD parses as UTC midnight, so a
    // formatter in the host's zone renders a date west of UTC as the previous month for part
    // of every first-of-the-month.
    expect(monthYearLabel("2025-03-01", "en")).toBe("Mar 2025");
    expect(monthYearLabel("2025-01-01", "en")).toBe("Jan 2025");
  });

  it("returns a value it cannot parse rather than Invalid Date", () => {
    expect(monthYearLabel("not-a-date", "en")).toBe("not-a-date");
  });
});
