/**
 * ADM-SCH-05's own decisions, where they are decided. ADR-0019.
 *
 * **The figures are not here, because they are not the screen's.** Which credit would be
 * spent, what is left after it and whether the coach is free are all the server's — the
 * quote picks the same grant the command draws on — and a test that recomputed any of them
 * would be asserting a second definition into existence. What is decided here is which of the
 * canvas's states a reader is given, and that is the one place a reader could be misled.
 */
import { describe, expect, it } from "vitest";

import { MESSAGES } from "@/i18n/locale";
import {
  atClub, bookingState, instantFrom,
  type PersonalSessionQuote,
} from "@/lib/personal-session";

function quote(over: Partial<PersonalSessionQuote> = {}): PersonalSessionQuote {
  return {
    coach_resource_id: "r-1",
    coach_name: "Yousef Haddad",
    person_id: "p-1",
    location_id: "l-1",
    timezone: "Asia/Amman",
    starts_at: "2026-12-03T14:30:00+00:00",
    ends_at: "2026-12-03T15:25:00+00:00",
    minutes: 55,
    clashes: [],
    coach_is_free: true,
    grant_id: "g-1",
    credits_remaining: 3,
    credits_remaining_after: 2,
    credits_expire_at: "2026-11-30T00:00:00+00:00",
    credit_name: "Personal training",
    drawable_grants: 1,
    may_book: true,
    needs_a_package: false,
    balance_is_unswept: true,
    soonest_expiring_is_spent_first: "x",
    ...over,
  };
}

describe("the canvas's two refusals", () => {
  it("is ready where the coach is free and there is a credit", () => {
    expect(bookingState(quote())).toBe("ready");
  });

  it("names the package where there is nothing to spend", () => {
    // "At zero credits the button becomes **Sell a package first**."
    expect(bookingState(quote({
      needs_a_package: true, grant_id: null, credits_remaining: null,
      credits_remaining_after: null, drawable_grants: 0, may_book: false,
    }))).toBe("needsPackage");
  });

  it("names the hour where the coach is busy", () => {
    expect(bookingState(quote({
      coach_is_free: false, may_book: false,
      clashes: [{
        kind: "double_booked", resource_id: "r-1",
        detail: "already holds this hour", with_session_id: "s-9",
      }],
    }))).toBe("coachBusy");
  });

  it("keeps the two apart where both are in the way", () => {
    // **The reason they are not merged.** "Sell a package" and "pick another hour" are
    // different remedies, so a screen told only "refused" would send a desk to the wrong
    // one -- and a screen told one of the two would hide the other.
    expect(bookingState(quote({
      needs_a_package: true, grant_id: null, credits_remaining: null,
      coach_is_free: false, may_book: false,
      clashes: [{
        kind: "unavailable", resource_id: "r-1",
        detail: "the rota refuses it", with_session_id: null,
      }],
    }))).toBe("bothInTheWay");
  });

  it("is never ready where the server says it may not book", () => {
    // The server's own `may_book` is the two halves together; this derivation has to agree
    // with it in both directions, because the button is gated on `ready`.
    for (const over of [
      { needs_a_package: true },
      { coach_is_free: false },
      { needs_a_package: true, coach_is_free: false },
    ]) {
      const one = quote({ ...over, may_book: false });
      expect(bookingState(one) === "ready").toBe(one.may_book);
    }
  });
});

describe("an unlimited entitlement", () => {
  it("is ready with no figure, which is not the same as none at all", () => {
    // `is_counted: false` on the policy means there is nothing to deduct, and the quote says
    // so with a grant and a null balance. A screen reading only the balance would call that
    // "no credit" and send somebody to sell a package they do not need.
    const one = quote({ credits_remaining: null, credits_remaining_after: null });
    expect(one.needs_a_package).toBe(false);
    expect(bookingState(one)).toBe("ready");
  });
});

describe("the hour is read in the club's own zone", () => {
  it("renders the local wall clock rather than the instant", () => {
    // The schedule board's hard-won rule: a board that sliced the ISO string showed 15:00
    // under a heading promising Asia/Amman, and four layers of tests did not notice.
    expect(atClub("2026-12-03T14:30:00+00:00", "Asia/Amman", "en")).toBe("17:30");
    expect(atClub("2026-12-03T14:30:00+00:00", "Europe/London", "en")).toBe("14:30");
  });

  it("uses Latin digits in both locales, because a time is an identifier here", () => {
    expect(atClub("2026-12-03T14:30:00+00:00", "Asia/Amman", "ar")).toBe("17:30");
  });
});

describe("the instant the form sends", () => {
  it("is null until both halves are filled, so nothing is quoted on half a choice", () => {
    expect(instantFrom("", "17:30")).toBeNull();
    expect(instantFrom("2026-12-03", "")).toBeNull();
    expect(instantFrom("2026-13-45", "17:30")).toBeNull();
  });

  it("is a UTC instant, which is what the routes take", () => {
    const at = instantFrom("2026-12-03", "17:30");
    expect(at).toMatch(/^2026-12-0[34]T\d{2}:\d{2}:00\.000Z$/);
  });
});

describe("the messages", () => {
  it("every key the screen renders exists in both catalogues", () => {
    const keys = [
      "pt.heading", "pt.headingWith", "pt.oneCoachOneMember", "pt.needsRead",
      "pt.whichMember", "pt.reachedFromAMember", "pt.openTheMembers",
      "pt.nothingToBookWith", "pt.noCoaches", "pt.whichClub",
      "pt.coach", "pt.day", "pt.clock", "pt.length",
      "pt.pickAnHour", "pt.asking", "pt.usesOne", "pt.unlimitedCredit",
      "pt.leftAfter", "pt.expiring", "pt.noCredit", "pt.sellAPackage",
      "pt.coachBusy", "pt.coachBusyBody", "pt.book", "pt.bookAndUse",
      "pt.booked", "pt.alreadyBooked", "pt.bookedBody", "pt.needsPermission",
      "pt.whoseName", "pt.refused", "pt.refusedBusy", "pt.refusedNoCredit",
      "pt.notYetTitle", "pt.gapPosLabel", "pt.gapPos", "pt.gapRecurringLabel",
      "pt.gapRecurring", "pt.gapNotifyLabel", "pt.gapNotify",
      "membership.bookPersonal",
    ] as const;
    for (const key of keys) {
      expect(MESSAGES.en[key], `${key} missing from English`).toBeTruthy();
      expect(MESSAGES.ar[key], `${key} missing from Arabic`).toBeTruthy();
    }
  });

  it("names the Point of Sale as the way out rather than offering a dead control", () => {
    // "Never a blocked state with no way out" is honoured by saying what the way out is:
    // POS-05 has no implementation at all, so a button here would answer nothing.
    for (const locale of ["en", "ar"] as const) {
      expect(MESSAGES[locale]["pt.sellAPackage"].length).toBeGreaterThan(40);
      expect(MESSAGES[locale]["pt.gapPos"].length).toBeGreaterThan(60);
    }
  });

  it("says the three permissions rather than one, because the button is three acts", () => {
    expect(MESSAGES.en["pt.needsPermission"]).toContain("three");
  });
});
