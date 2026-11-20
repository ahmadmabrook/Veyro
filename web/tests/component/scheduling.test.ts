import { describe, expect, it } from "vitest";

import {
  needsAttention,
  occupancy,
  weekDays,
  weekRows,
  weekSummary,
  type ScheduledSession,
} from "@/lib/scheduling";
import { inZone } from "@/lib/time";

/**
 * Reading an instant in the site's own timezone, which is the whole of MOD-019's difficulty.
 *
 * **The module stores a UTC instant and the local facts it came from because neither is
 * derivable from the other.** A surface that slices the ISO string renders the UTC wall time:
 * the first version of the schedule board showed a class at 18:00 in Amman as `15:00`, under a
 * heading promising the site's own timezone, and 140 passing browser tests did not notice
 * because every one of them asserted the timezone's *name* was on the page.
 */

describe("an instant in the site's zone", () => {
  // 15:00 UTC is 18:00 in Amman (UTC+3) and 10:00 in New York (UTC-5) on this date.
  const instant = "2026-11-20T15:00:00+00:00";

  it("converts rather than slicing the string", () => {
    expect(inZone(instant, "Asia/Amman")).toEqual({
      date: "2026-11-20", time: "18:00", zone: "Asia/Amman",
    });
    expect(inZone(instant, "America/New_York").time).toBe("10:00");
  });

  it("moves the date when the zone does", () => {
    // 22:00 UTC is the next morning in Sydney, which is the case a date sliced off the ISO
    // string gets wrong twice: wrong time and wrong day.
    expect(inZone("2026-11-20T22:00:00+00:00", "Australia/Sydney")).toMatchObject({
      date: "2026-11-21", time: "09:00",
    });
  });

  it("renders midnight as 00:00 rather than 24:00", () => {
    // `en-GB` with `hour12: false` gives `24:00` for midnight in some engines; `h23` is what
    // makes it `00:00`, which is the only spelling a reader expects on a schedule.
    expect(inZone("2026-11-20T21:00:00+00:00", "Asia/Amman")).toEqual({
      date: "2026-11-21", time: "00:00", zone: "Asia/Amman",
    });
  });

  it("falls back to UTC and says UTC, rather than to a plausible wrong time", () => {
    // MOD-004 validates a location's timezone when it is created, so this is a failure nobody
    // should see -- and a time that looks local but is not is worse than one that is obviously
    // foreign.
    expect(inZone(instant, "Not/AZone")).toEqual({
      date: "2026-11-20", time: "15:00", zone: "UTC",
    });
  });
});

describe("how full a session is", () => {
  const session = (over: Partial<ScheduledSession> = {}): ScheduledSession => ({
    session_id: "s", template_id: "t", display_name: "Evening yoga flow",
    starts_at: "2026-11-20T15:00:00+00:00", ends_at: "2026-11-20T16:00:00+00:00",
    local_date: "2026-11-20", capacity: 12, places: 12, held: 0, free: 12,
    status: "scheduled", dst_adjusted: false, staff: "Omar Haddad", ...over,
  });

  it("takes the module's own free count rather than subtracting", () => {
    // `held` can exceed `places` when overbooking was declared and then reduced, and MOD-019
    // clamps at zero -- a surface that recomputed `places - held` would render a negative.
    expect(occupancy(session({ held: 14, places: 12, free: 0 }))).toEqual({
      held: 14, places: 12, free: 0, full: true,
    });
  });

  it("marks a session a clock change moved, and nothing else", () => {
    // A full class is ordinary and a cancelled one is a decision somebody made. An occurrence
    // stepped forward because its local time did not exist that day is a session whose members
    // were told a time that is not when it happens.
    expect(needsAttention(session({ dst_adjusted: true }))).toBe(true);
    expect(needsAttention(session({ dst_adjusted: true, status: "cancelled" }))).toBe(false);
    expect(needsAttention(session({ free: 0 }))).toBe(false);
    expect(needsAttention(session({ status: "cancelled" }))).toBe(false);
  });
});

describe("ADM-SCH-01's week grid", () => {
  const session = (over: Partial<ScheduledSession> & { local_date: string }):
    ScheduledSession => ({
    session_id: `s-${over.local_date}-${over.starts_at ?? ""}`,
    template_id: "t", display_name: "Evening yoga flow",
    starts_at: `${over.local_date}T15:00:00+00:00`,
    ends_at: `${over.local_date}T16:00:00+00:00`,
    capacity: 12, places: 12, held: 0, free: 12,
    status: "scheduled", dst_adjusted: false, staff: "Omar Haddad", ...over,
  });

  describe("the seven days", () => {
    it("walks seven local dates from the first", () => {
      const days = weekDays("2026-11-20", "en", "2026-11-20");
      expect(days).toHaveLength(7);
      expect(days.map((d) => d.date)).toEqual([
        "2026-11-20", "2026-11-21", "2026-11-22",
        "2026-11-23", "2026-11-24", "2026-11-25", "2026-11-26",
      ]);
    });

    it("marks the site's own today and no other column", () => {
      const days = weekDays("2026-11-20", "en", "2026-11-23");
      expect(days.filter((d) => d.today).map((d) => d.date)).toEqual(["2026-11-23"]);
    });

    it("marks nothing when the site's today is outside the week", () => {
      // A board showing next week has no today in it, and marking the first column would be
      // a claim about where the reader is standing.
      expect(weekDays("2026-11-20", "en", "2026-12-01").some((d) => d.today)).toBe(false);
    });

    it("still spans seven days across a clock change", () => {
      // The dates come from the site's own calendar and the walk is in UTC, so a spring
      // forward cannot make the week six days or eight. Europe/London shifts on 29 March.
      const days = weekDays("2026-03-26", "en", "2026-03-26");
      expect(days.map((d) => d.date)).toEqual([
        "2026-03-26", "2026-03-27", "2026-03-28",
        "2026-03-29", "2026-03-30", "2026-03-31", "2026-04-01",
      ]);
    });
  });

  describe("the grid", () => {
    const days = weekDays("2026-11-20", "en", "2026-11-20");
    const at = (s: ScheduledSession) => s.starts_at.slice(11, 16);

    it("puts a session in its own day's column and its own time's row", () => {
      const rows = weekRows([session({ local_date: "2026-11-22" })], days, at);
      expect(rows).toHaveLength(1);
      expect(rows[0]!.time).toBe("15:00");
      // Index 2 is 22 November, the third of the seven.
      expect(rows[0]!.cells.map((c) => c === null)).toEqual([
        true, true, false, true, true, true, true,
      ]);
    });

    it("keeps both classes when two run in one slot", () => {
      // A gym with two studios runs two at six o'clock, and `publishing.assess` shipped the
      // version that kept one -- a dict keyed on the start instant, where which class
      // vanished depended on row order.
      const rows = weekRows([
        session({ local_date: "2026-11-22", display_name: "Yoga" }),
        session({ local_date: "2026-11-22", display_name: "Pilates", session_id: "s2" }),
      ], days, at);
      expect(rows[0]!.cells[2]).toHaveLength(2);
      expect(rows[0]!.cells[2]!.map((s) => s.display_name)).toEqual(["Yoga", "Pilates"]);
    });

    it("orders the rows by time", () => {
      const rows = weekRows([
        session({ local_date: "2026-11-20", starts_at: "2026-11-20T16:00:00+00:00" }),
        session({ local_date: "2026-11-20", starts_at: "2026-11-20T06:00:00+00:00" }),
      ], days, at);
      expect(rows.map((r) => r.time)).toEqual(["06:00", "16:00"]);
    });

    it("drops a session outside the seven days rather than forcing it into an edge", () => {
      const rows = weekRows([session({ local_date: "2026-12-25" })], days, at);
      expect(rows).toEqual([]);
    });
  });

  describe("the header's three figures", () => {
    it("counts classes and the ones with no coach", () => {
      const summary = weekSummary([
        session({ local_date: "2026-11-20" }),
        session({ local_date: "2026-11-21", staff: null }),
        session({ local_date: "2026-11-22", staff: null }),
      ]);
      expect(summary.classes).toBe(3);
      expect(summary.unstaffed).toBe(2);
    });

    it("leaves a cancelled class out of both", () => {
      // A cancelled class needs no coach and is not a class in the week's count.
      const summary = weekSummary([
        session({ local_date: "2026-11-20" }),
        session({ local_date: "2026-11-21", staff: null, status: "cancelled" }),
      ]);
      expect(summary.classes).toBe(1);
      expect(summary.unstaffed).toBe(0);
    });

    it("averages fill over places, not over classes", () => {
      // A 1-of-2 class and a 9-of-18 class are both 50%, and so is the week; a mean of the
      // per-class percentages would say the same here and diverge the moment they differ.
      const summary = weekSummary([
        session({ local_date: "2026-11-20", places: 2, held: 1 }),
        session({ local_date: "2026-11-21", places: 18, held: 9 }),
      ]);
      expect(summary.averageFillPercent).toBe(50);
    });

    it("reports no average rather than nought percent for an empty week", () => {
      // "0% fill" is a claim about a week, and a week with nothing in it has not made one.
      expect(weekSummary([]).averageFillPercent).toBeNull();
    });
  });
});
