import { describe, expect, it } from "vitest";

import { needsAttention, occupancy, type ScheduledSession } from "@/lib/scheduling";
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
    status: "scheduled", dst_adjusted: false, ...over,
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
