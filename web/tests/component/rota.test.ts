import { describe, expect, it } from "vitest";

import { MESSAGES, type MessageKey } from "@/i18n/locale";
import { monthDayLabel, shiftWeek } from "@/lib/scheduling";
import {
  anyRota,
  CELL_LABEL,
  CELL_MARK,
  cellState,
  hourLabel,
  hourSpan,
  hours,
  minutesOf,
  type CellState,
  type ResourceWeek,
  type RotaDay,
  type RotaSession,
} from "@/lib/rota";

/**
 * ADM-SCH-04's surface decisions. What a rota says and whether a booking collides with it is
 * the server's and is tested in `tests/test_scheduling_domain.py`; what is here is what a
 * grid cell shows, which is the one place a reader could be misled.
 */

function day(overrides: Partial<RotaDay> = {}): RotaDay {
  return {
    date: "2026-08-20",
    weekday: 3,
    rota_binds: true,
    open_minutes: 8 * 60,
    open_spans: [{ starts_at: "09:00", ends_at: "17:00" }],
    windows: [{
      kind: "working", timezone: "Asia/Amman", starts_at: "09:00", ends_at: "17:00",
      recurring: true, reason: null, reason_masked: false,
    }],
    booked_minutes: 0,
    ...overrides,
  };
}

function session(overrides: Partial<RotaSession> = {}): RotaSession {
  return {
    session_id: "s-1",
    label: "Evening yoga flow",
    local_date: "2026-08-20",
    starts_at_local: "17:30",
    ends_at_local: "18:30",
    minutes: 60,
    quantity: 1,
    conflicts_with_availability: false,
    conflict_reason: null,
    ...overrides,
  };
}

function week(overrides: Partial<ResourceWeek> = {}): ResourceWeek {
  return {
    resource_id: "r-1", resource_code: "COACH-1", resource_kind: "staff",
    display_name: "Dana Coach", quantity: 1, status: "active",
    location_id: "l-1", location_name: "Downtown", timezone: "Asia/Amman",
    weeks: 1, window: { first_day: "2026-08-17", last_day: "2026-08-23" },
    days: [day()], sessions: [],
    open_minutes: 8 * 60, booked_minutes: 0, conflicts: 0,
    an_unconstrained_resource_has_no_open_hours: "x",
    a_booking_is_never_dropped: "x",
    times_are_the_resources_own_zone: "x",
    a_time_off_reason_is_masked: "x",
    a_session_kind_is_not_recorded: "x",
    ...overrides,
  };
}

describe("a wall clock", () => {
  it("compares as minutes from midnight", () => {
    expect(minutesOf("00:00")).toBe(0);
    expect(minutesOf("09:30")).toBe(570);
    expect(minutesOf("23:59")).toBe(1439);
  });

  it("labels an hour padded and 24-hour", () => {
    // The axis is a clock, not prose: "6 AM" under a column whose other end reads "22:00" is
    // the defect, and one of the two locales would give that from `Intl`.
    expect(hourLabel(0)).toBe("00:00");
    expect(hourLabel(9)).toBe("09:00");
    expect(hourLabel(18)).toBe("18:00");
  });
});

describe("the hours the grid draws", () => {
  it("spans everything the week touches, rota and bookings alike", () => {
    const span = hourSpan(week({
      days: [day({ open_spans: [{ starts_at: "09:00", ends_at: "17:00" }] })],
      sessions: [session({ starts_at_local: "19:00", ends_at_local: "20:00" })],
    }));
    expect(span).toEqual({ first: 9, last: 19 });
  });

  it("ends on the row the last thing occupies, not the one after it", () => {
    // A window ending at 17:00 needs no 17:00 row; one ending at 17:30 does.
    expect(hourSpan(week({
      days: [day({ windows: [{
        kind: "working", timezone: "Asia/Amman", starts_at: "09:00", ends_at: "17:00",
        recurring: true, reason: null, reason_masked: false,
      }] })],
      sessions: [],
    }))).toEqual({ first: 9, last: 16 });
  });

  it("is null where there is nothing at all to draw", () => {
    // So the page shows an empty state rather than twenty-four rows of "not working" for a
    // room nobody wrote a rota for.
    expect(hourSpan(week({
      days: [day({ rota_binds: false, open_minutes: null, open_spans: [], windows: [] })],
      sessions: [],
    }))).toBeNull();
  });
});

describe("what a cell is", () => {
  const state = (d: RotaDay, hour: number, sessions: RotaSession[] = []): CellState =>
    cellState(d, hour, sessions);

  it("is open inside the rota and closed outside it", () => {
    expect(state(day(), 10)).toBe("open");
    expect(state(day(), 7)).toBe("closed");
    expect(state(day(), 20)).toBe("closed");
  });

  it("is an exception where a break or a day off removes the time", () => {
    const withBreak = day({
      open_spans: [{ starts_at: "09:00", ends_at: "12:00" },
                   { starts_at: "13:00", ends_at: "17:00" }],
      windows: [
        { kind: "working", timezone: "Asia/Amman", starts_at: "09:00", ends_at: "17:00",
          recurring: true, reason: null, reason_masked: false },
        { kind: "break", timezone: "Asia/Amman", starts_at: "12:00", ends_at: "13:00",
          recurring: true, reason: null, reason_masked: false },
      ],
    });
    expect(state(withBreak, 12)).toBe("exception");
    expect(state(withBreak, 11)).toBe("open");
    expect(state(withBreak, 13)).toBe("open");
  });

  it("is booked where a session overlaps the hour, at either end", () => {
    const one = [session({ starts_at_local: "17:30", ends_at_local: "18:30" })];
    expect(state(day({ open_spans: [{ starts_at: "09:00", ends_at: "21:00" }] }), 17, one))
      .toBe("booked");
    expect(state(day({ open_spans: [{ starts_at: "09:00", ends_at: "21:00" }] }), 18, one))
      .toBe("booked");
    expect(state(day({ open_spans: [{ starts_at: "09:00", ends_at: "21:00" }] }), 19, one))
      .toBe("open");
  });

  it("only counts sessions on that day", () => {
    // Hour 10, which is inside the default 09:00-17:00 rota -- picking 17 asked about an
    // hour the rota does not cover, so the answer was correctly "closed" either way and the
    // test proved nothing about the date filter.
    const elsewhere = [session({ local_date: "2026-08-21",
                                 starts_at_local: "10:00", ends_at_local: "11:00" })];
    expect(state(day(), 10, elsewhere)).toBe("open");
    expect(state(day({ date: "2026-08-21" }), 10, elsewhere)).toBe("booked");
  });

  it("shows BOTH where a booking sits inside an exception", () => {
    // **The canvas's own requirement and the reason this screen exists**: "His 17:30 with
    // Hala sits inside it, so the grid shows both and the booking is flagged rather than
    // silently honoured or silently dropped." A booking that quietly won over the exception,
    // or an exception that hid the booking, would each be one of the two failures named.
    const off = day({
      open_spans: [],
      windows: [
        { kind: "working", timezone: "Asia/Amman", starts_at: "09:00", ends_at: "21:00",
          recurring: true, reason: null, reason_masked: false },
        { kind: "time_off", timezone: "Asia/Amman", starts_at: "12:00", ends_at: "22:00",
          recurring: false, reason: null, reason_masked: true },
      ],
    });
    const clash = [session({
      starts_at_local: "17:30", ends_at_local: "18:30",
      conflicts_with_availability: true,
      conflict_reason: "time off from 12:00 to 22:00 overlaps this session",
    })];
    expect(state(off, 17, clash)).toBe("bookedConflict");
    // And the hours around it are still the exception, not silently open.
    expect(state(off, 13, [])).toBe("exception");
  });

  it("prefers the conflict where two sessions share an hour and one clashes", () => {
    const both = [
      session({ session_id: "a", starts_at_local: "17:00", ends_at_local: "17:30" }),
      session({ session_id: "b", starts_at_local: "17:30", ends_at_local: "18:00",
                conflicts_with_availability: true, conflict_reason: "time off" }),
    ];
    expect(state(day({ open_spans: [{ starts_at: "09:00", ends_at: "21:00" }] }), 17, both))
      .toBe("bookedConflict");
  });
});

describe("the week-of label", () => {
  it("is the day and the month, as the canvas writes it", () => {
    // ADM-SCH-04's sub-line reads "Week of 17 August", not an ISO date -- the full range is
    // in the heading above it.
    expect(monthDayLabel("2026-08-17", "en")).toBe("17 August");
  });

  it("reads the date it was given, whatever zone the host is in", () => {
    // A bare `YYYY-MM-DD` parses as UTC midnight, so the formatter is pinned to UTC. Without
    // that pin a host west of UTC renders the day before for part of every day -- which is
    // `weekDays`' own subtlety, and the reason this sits beside it.
    expect(monthDayLabel("2026-01-01", "en")).toBe("1 January");
    expect(monthDayLabel("2026-12-31", "en")).toBe("31 December");
  });

  it("is Arabic in Arabic, because a month is a word", () => {
    const arabic = monthDayLabel("2026-08-17", "ar");
    expect(arabic).not.toBe(monthDayLabel("2026-08-17", "en"));
    expect(arabic).toMatch(/\p{Script=Arabic}/u);
  });
});

describe("moving between weeks", () => {
  it("shifts by whole weeks and reads the date it was given", () => {
    // **The screen had no way to leave the week it opened on**, which TestSprite found: the
    // question this grid answers is almost always about a week that is not this one, and the
    // canvas's own example is an exception agreed three weeks before the day it covers.
    expect(shiftWeek("2026-11-22", 1)).toBe("2026-11-29");
    expect(shiftWeek("2026-11-22", -1)).toBe("2026-11-15");
    expect(shiftWeek("2026-11-22", 0)).toBe("2026-11-22");
  });

  it("crosses a month, a year and a clock change without losing a day", () => {
    // Date arithmetic in UTC on a date-only string, which is `weekDays`' own reasoning: in
    // the host's zone this gives six days or eight on the two nights a year it shifts.
    expect(shiftWeek("2026-12-28", 1)).toBe("2027-01-04");
    expect(shiftWeek("2027-01-04", -1)).toBe("2026-12-28");
    expect(shiftWeek("2026-03-26", 1)).toBe("2026-04-02");
    expect(shiftWeek("2026-10-29", 1)).toBe("2026-11-05");
  });
});

describe("the hours figure", () => {
  it("is always a whole number, which is what the only formatter accepts", () => {
    // **This app has no decimal formatter and that is deliberate**: `formatInteger` throws
    // `ConventionError("integer required")` for a fraction, so a tenths figure answered 500
    // from inside `fill` on every request to this page. The guard is the contract, so the
    // test is the contract -- and the invariant has to hold for every input rather than for
    // the three somebody picked.
    for (const minutes of [0, 1, 29, 30, 31, 59, 60, 90, 95, 480, 1337, 2041]) {
      expect(Number.isInteger(hours(minutes)), `${minutes} minutes`).toBe(true);
    }
    expect(hours(60)).toBe(1);
    expect(hours(90)).toBe(2);
    expect(hours(0)).toBe(0);
  });

  it("is two numbers, because a session outside the rota makes the ratio exceed one", () => {
    const over = week({ open_minutes: 60, booked_minutes: 240 });
    expect(hours(over.booked_minutes)).toBeGreaterThan(hours(over.open_minutes ?? 0));
  });
});

describe("whether the grid is worth drawing", () => {
  it("is false when no day in the week has a rota that binds", () => {
    expect(anyRota(week({
      days: [day({ rota_binds: false }), day({ rota_binds: false })],
    }))).toBe(false);
  });

  it("is true when any day binds, even one", () => {
    expect(anyRota(week({
      days: [day({ rota_binds: false }), day({ rota_binds: true })],
    }))).toBe(true);
  });
});

describe("the catalogue", () => {
  const KEYS: MessageKey[] = [
    "rota.heading", "rota.title", "rota.whichResource", "rota.timezone", "rota.weekOf",
    "rota.hoursBooked", "rota.hoursBookedNoRota", "rota.gridTitle",
    "rota.legend", "rota.conflictsTitle", "rota.noConflicts", "rota.conflictLead",
    "rota.noRotaTitle", "rota.noRotaBody", "rota.nothingToDraw", "rota.reasonMasked",
    "rota.reasonMaskedWhy", "rota.gapsTitle", "rota.gapKindLabel", "rota.gapKind",
    "rota.gapExceptionLabel", "rota.gapException", "rota.gapHourLabel", "rota.gapHour",
    "rota.pickResourceInLink", "rota.noResources", "rota.refusedWhy", "schedule.coaches",
    "rota.whichWeek", "rota.previousWeek", "rota.thisWeek", "rota.nextWeek",
  ];

  it("every key this screen renders exists in both catalogues", () => {
    // `MESSAGE_KEYS` compares the two catalogues against each other and is blind to a string
    // that never became a key, so this is the parity check run from the side it cannot see.
    for (const key of [...KEYS, ...Object.values(CELL_LABEL)]) {
      expect(MESSAGES.en[key], `${key} missing from English`).toBeTruthy();
      expect(MESSAGES.ar[key], `${key} missing from Arabic`).toBeTruthy();
    }
  });

  it("the two states the canvas marks have one, and the quiet two do not", () => {
    // ADM-SCH-04 writes PT or CLS in a booked cell and OFF in an exception, and leaves the
    // quiet states blank -- which is the same statement as "working hours are the
    // background". A mark in all ninety cells would leave the grid with no figure and ground.
    expect(CELL_MARK.closed).toBeNull();
    expect(CELL_MARK.open).toBeNull();
    expect(CELL_MARK.exception).toBeTruthy();
    expect(CELL_MARK.booked).toBeTruthy();
    // A refused booking is still a booking, so it carries the same mark; what distinguishes
    // it is the edge and its accessible name, which says the rota refuses it.
    expect(CELL_MARK.bookedConflict).toBe(CELL_MARK.booked);
    for (const key of Object.values(CELL_MARK)) {
      if (key === null) continue;
      expect(MESSAGES.en[key], `${key} missing from English`).toBeTruthy();
      expect(MESSAGES.ar[key], `${key} missing from Arabic`).toBeTruthy();
    }
  });

  it("every cell state has a label, so no fill is unexplained", () => {
    const states: CellState[] =
      ["closed", "open", "exception", "booked", "bookedConflict"];
    for (const state of states) {
      expect(CELL_LABEL[state]).toBeTruthy();
    }
    expect(Object.keys(CELL_LABEL).sort()).toEqual([...states].sort());
  });

  it("the refusal names the permission, as the sibling screens do", () => {
    for (const locale of ["en", "ar"] as const) {
      expect(MESSAGES[locale]["rota.refusedWhy"])
        .toContain("scheduling.schedule.read");
    }
  });

  it("says the exception form is unblocked rather than refused", () => {
    // `scheduling.availability.write` is the one scheduling permission that is routine
    // rather than stepped-up, and the catalogue says why. So the missing form is the next
    // piece of work, not a button that would answer 403 -- which is the reason every other
    // write form in this app is absent.
    expect(MESSAGES.en["rota.gapException"]).toContain("routine");
    expect(MESSAGES.en["rota.gapException"]).toContain("not a refusal");
  });
});
