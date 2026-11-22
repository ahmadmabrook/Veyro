import { describe, expect, it } from "vitest";

import {
  COUNTDOWN_WINDOW_MINUTES, checkinWindow, deskOrder, hasStarted, mayCheckIn, minutesUntil,
  nameOf, notHere, presence, rowState, waiting,
  type NamedPerson, type Roster, type RosterBooking,
} from "@/lib/desk";

/**
 * FD-06's decisions. Three counts over the same rows, one order, and one sentence that is
 * only true inside a window.
 *
 * **Decisions rather than rendered branches**, which this repository has a rule for: a
 * surface branch no fixture can reach is vacuity one layer up, and two of these cannot be
 * reached from the browser fixture at all — settling a class has no route by design, so a
 * roster with a no-show or a released booking on it is a state the e2e suite cannot
 * construct. It is constructible here.
 */

const booking = (over: Partial<RosterBooking> = {}): RosterBooking => ({
  booking_id: "b-1",
  person_id: "p-1",
  state: "booked",
  source_kind: "front_desk",
  checked_in_at: null,
  booked_at: "2026-11-20T10:00:00Z",
  prior_no_shows: 0,
  // The window the module itself computes: an hour before the session, until the grace.
  checkin_opens_at: "2026-11-22T15:00:00Z",
  checkin_closes_at: "2026-11-22T16:15:00Z",
  ...over,
});

/** Inside the window the fixture booking declares. */
const DURING = new Date("2026-11-22T15:56:00Z");

const roster = (bookings: RosterBooking[], over: Partial<Roster> = {}): Roster => ({
  session_id: "s-1", status: "published", starts_at: "2026-11-22T16:00:00Z",
  capacity: 12, overbook_places: 6, places: 18, held: bookings.length,
  free: 18 - bookings.length, bookings, waitlist: [], ...over,
});

describe("the three counts the header carries", () => {
  it("counts who is here against the session's places, not the roster's length", () => {
    // "12 of 18 here" — a class with six free seats is twelve of eighteen, not twelve of
    // twelve. The places come from MOD-019's session because this module owns no capacity,
    // so the figure a coach reads is the one that refuses the nineteenth booking.
    const r = roster([
      booking({ booking_id: "a", checked_in_at: "2026-11-22T15:55:00Z" }),
      booking({ booking_id: "b" }),
    ]);
    expect(presence(r)).toEqual({ here: 1, places: 18 });
  });

  it("counts who is still expected, which is not everybody who is absent", () => {
    // A settled no-show and a booking the gym released are both "not here" in English and
    // neither is somebody a desk is waiting for.
    const r = roster([
      booking({ booking_id: "a", checked_in_at: "2026-11-22T15:55:00Z" }),
      booking({ booking_id: "b" }),
      booking({ booking_id: "c", state: "no_show" }),
      booking({ booking_id: "d", state: "session_cancelled" }),
    ]);
    expect(notHere(r).map((b) => b.booking_id)).toEqual(["b"]);
  });

  it("counts the queue, which is a different list entirely", () => {
    const r = roster([], { waitlist: [
      { entry_id: "w1", person_id: "p2", state: "waiting", position: 1,
        offer_expires_at: null },
      { entry_id: "w2", person_id: "p3", state: "offered", position: 2,
        offer_expires_at: "2026-11-22T15:50:00Z" },
      { entry_id: "w3", person_id: "p4", state: "expired", position: 3,
        offer_expires_at: "2026-11-22T15:00:00Z" },
    ] });
    // An expired offer is not somebody waiting: their turn came and went.
    expect(waiting(r).map((e) => e.entry_id)).toEqual(["w1", "w2"]);
  });
});

describe("the countdown", () => {
  const start = "2026-11-22T16:00:00Z";

  it("says the minutes inside the window the sentence is true in", () => {
    expect(minutesUntil(start, new Date("2026-11-22T15:56:00Z"))).toBe(4);
    expect(minutesUntil(start, new Date("2026-11-22T14:30:00Z")))
      .toBe(COUNTDOWN_WINDOW_MINUTES);
  });

  it("says nothing about a class tomorrow", () => {
    // **The defect this is written against.** The first version printed "2,266 minutes to
    // go" for a class the next evening: arithmetic that is correct and a sentence that is
    // absurd. Found by opening the page, which no assertion about text could have done.
    expect(minutesUntil(start, new Date("2026-11-21T02:14:00Z"))).toBeNull();
    expect(minutesUntil(start, new Date("2026-11-22T14:29:00Z"))).toBeNull();
  });

  it("says nothing once it has started, because that is a different sentence", () => {
    expect(minutesUntil(start, new Date("2026-11-22T16:11:00Z"))).toBeNull();
    expect(hasStarted(start, new Date("2026-11-22T16:11:00Z"))).toBe(true);
    expect(hasStarted(start, new Date("2026-11-22T15:59:00Z"))).toBe(false);
  });

  it("answers null rather than NaN for an instant it cannot read", () => {
    expect(minutesUntil("not-an-instant", new Date())).toBeNull();
    expect(hasStarted("not-an-instant", new Date())).toBe(false);
  });
});

describe("what a row says", () => {
  it("is here once somebody marked them present", () => {
    expect(rowState(booking({ checked_in_at: "2026-11-22T15:55:00Z" }))).toBe("here");
    expect(rowState(booking({ state: "attended" }))).toBe("here");
  });

  it("keeps a gym cancellation apart from a no-show", () => {
    // **MOD-020's worst shipped defect was exactly this collapse**: `released` and
    // `session_cancelled` were declared and nothing wrote them, so every member of a
    // cancelled class was recorded absent with a fee and a strike. A roster that rendered
    // them alike would put that reading back on the screen.
    expect(rowState(booking({ state: "no_show" }))).toBe("absent");
    expect(rowState(booking({ state: "session_cancelled" }))).toBe("released");
    expect(rowState(booking({ state: "released" }))).toBe("released");
  });

  it("offers the button only where the module would take it", () => {
    expect(mayCheckIn(booking(), DURING)).toBe(true);
    expect(mayCheckIn(booking({ checked_in_at: "2026-11-22T15:55:00Z" }), DURING))
      .toBe(false);
    for (const state of ["attended", "no_show", "cancelled", "released"]) {
      expect(mayCheckIn(booking({ state }), DURING), state).toBe(false);
    }
  });

  it("withholds it outside the window, which is the other half of the refusal", () => {
    // **The defect a browser test found.** The first version considered only the state, so
    // a desk opening tomorrow's class was offered a button that answered 409 -- this
    // build's own "a button that answered 403 is worse than its absence", in the one place
    // the refusal arrives as prose under a row.
    expect(mayCheckIn(booking(), new Date("2026-11-21T20:00:00Z"))).toBe(false);
    expect(mayCheckIn(booking(), new Date("2026-11-22T17:00:00Z"))).toBe(false);
  });

  it("names which side of the window it is, because the sentences differ", () => {
    expect(checkinWindow(booking(), new Date("2026-11-21T20:00:00Z"))).toBe("early");
    expect(checkinWindow(booking(), DURING)).toBe("open");
    expect(checkinWindow(booking(), new Date("2026-11-22T17:00:00Z"))).toBe("closed");
  });

  it("treats a window it cannot read as closed, not open", () => {
    // Failing toward offering a control the module will refuse is the direction the whole
    // function exists to avoid.
    expect(checkinWindow(booking({ checkin_opens_at: "nope" }), DURING)).toBe("closed");
    expect(checkinWindow(booking({ checkin_closes_at: "nope" }), DURING)).toBe("closed");
  });
});

describe("the order a desk reads the roster in", () => {
  it("puts the people who have not arrived first", () => {
    // Not booking order, which is what the read returns. Four minutes from the start a
    // receptionist is looking for who is missing; the ones in the room are the rows they
    // want out of the way.
    const rows = deskOrder([
      booking({ booking_id: "here", checked_in_at: "2026-11-22T15:55:00Z" }),
      booking({ booking_id: "absent", state: "no_show" }),
      booking({ booking_id: "waiting" }),
    ]);
    expect(rows.map((b) => b.booking_id)).toEqual(["waiting", "here", "absent"]);
  });

  it("keeps booking order inside a group, which is the only order the module has", () => {
    const rows = deskOrder([
      booking({ booking_id: "second", booked_at: "2026-11-20T12:00:00Z" }),
      booking({ booking_id: "first", booked_at: "2026-11-20T09:00:00Z" }),
    ]);
    expect(rows.map((b) => b.booking_id)).toEqual(["first", "second"]);
  });

  it("does not reorder the caller's array", () => {
    const given = [booking({ booking_id: "a", state: "no_show" }),
                   booking({ booking_id: "b" })];
    deskOrder(given);
    expect(given.map((b) => b.booking_id)).toEqual(["a", "b"]);
  });
});

describe("the name on a row", () => {
  const person = (over: Partial<NamedPerson> = {}): NamedPerson => ({
    person_id: "p-1", legal_name: "Hala Barakat", preferred_name: null,
    lifecycle_state: "active", member_number: "M-00042", ...over,
  });

  it("prefers what the member calls themselves", () => {
    expect(nameOf(person({ preferred_name: "Hala" }))).toBe("Hala");
  });

  it("is null when the mask withheld it, so the row renders the marker", () => {
    // The mask is MOD-014's and arrives as the marker string. A screen that printed it
    // literally would show `***` where a name belongs.
    expect(nameOf(person({ legal_name: "***", preferred_name: null }))).toBeNull();
  });

  it("is null for somebody the batch did not answer about", () => {
    // Not the same fact as withheld, and the page says which: a read that failed is not a
    // permission the reader lacks.
    expect(nameOf(undefined)).toBeNull();
  });
});
