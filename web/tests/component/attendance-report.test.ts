import { describe, expect, it } from "vitest";

import { MESSAGES, fill, type MessageKey } from "@/i18n/locale";
import {
  barHeightPercent,
  dayRange,
  DAY_RANGES,
  DEFAULT_RANGE,
  hourLabel,
  sharePercent,
} from "@/lib/reports";

/**
 * ADM-RPT-04's surface decisions. The arithmetic the conclusion rests on is the server's and
 * is tested in `tests/test_access_domain.py`; what is here is what the page itself decides.
 */
describe("the day ranges", () => {
  it("names which days rather than what they mean to a business", () => {
    // **No chip says "Weekdays".** A working week is Sunday to Thursday in the market this
    // product is built for and Monday to Friday in the one its design language comes from,
    // and nothing in this build declares either -- so a chip claiming one would be the
    // surface inventing a market convention and presenting it as the product's.
    for (const range of DAY_RANGES) {
      const label = MESSAGES.en[range.label] as string;
      expect(label.toLowerCase()).not.toContain("weekday");
      expect(label.toLowerCase()).not.toContain("weekend");
      expect(label.toLowerCase()).not.toContain("working");
    }
  });

  it("every range names real days, in MOD-019's own 0-is-Monday numbering", () => {
    for (const range of DAY_RANGES) {
      expect(range.days.length).toBeGreaterThan(0);
      for (const day of range.days) {
        expect(Number.isInteger(day)).toBe(true);
        expect(day).toBeGreaterThanOrEqual(0);
        expect(day).toBeLessThanOrEqual(6);
      }
      expect(new Set(range.days).size).toBe(range.days.length);
    }
  });

  it("the two working-week ranges are five days and differ, which is the whole point", () => {
    const sunThu = DAY_RANGES.find((range) => range.key === "sun-thu");
    const monFri = DAY_RANGES.find((range) => range.key === "mon-fri");
    expect(sunThu?.days.length).toBe(5);
    expect(monFri?.days.length).toBe(5);
    expect([...(sunThu?.days ?? [])].sort()).not.toEqual([...(monFri?.days ?? [])].sort());
    // Sunday is 6 in this numbering, which is the half an author used to 0-is-Sunday gets
    // wrong -- and getting it wrong moves a whole day of the chart.
    expect(sunThu?.days).toContain(6);
    expect(monFri?.days).not.toContain(6);
  });

  it("an unknown or absent range falls back to every day rather than to nothing", () => {
    expect(dayRange(undefined)).toBe(DEFAULT_RANGE);
    expect(dayRange("not-a-range")).toBe(DEFAULT_RANGE);
    expect(dayRange("sun-thu").key).toBe("sun-thu");
    expect(DEFAULT_RANGE.days.length).toBe(7);
  });

  it("every label is in both catalogues", () => {
    for (const range of DAY_RANGES) {
      expect(MESSAGES.en[range.label], `${range.label} missing from English`).toBeTruthy();
      expect(MESSAGES.ar[range.label], `${range.label} missing from Arabic`).toBeTruthy();
    }
  });
});

describe("the axis labels", () => {
  it("are padded 24-hour wall-clock times", () => {
    expect(hourLabel(0)).toBe("00:00");
    expect(hourLabel(6)).toBe("06:00");
    expect(hourLabel(18)).toBe("18:00");
    expect(hourLabel(23)).toBe("23:00");
  });

  it("do not go through Intl, because one of the two locales would give a 12-hour form", () => {
    // "6 AM" under a heading whose other end reads "22:00" is the defect. The axis is a
    // clock rather than prose, so it is formatted rather than localised.
    for (let hour = 0; hour < 24; hour += 1) {
      expect(hourLabel(hour)).toMatch(/^\d\d:00$/);
    }
  });
});

describe("the shares", () => {
  it("round basis points to whole percentages", () => {
    expect(sharePercent(10_000)).toBe(100);
    expect(sharePercent(4_100)).toBe(41);
    expect(sharePercent(0)).toBe(0);
  });

  it("have no percentage where there is no peak, which is not zero per cent", () => {
    // Nobody came in at all, which is a club that was shut. Rendering 0% would read as
    // "this hour is quiet" -- MOD-011's "an empty window is not a pass", in a report.
    expect(sharePercent(null)).toBeNull();
  });
});

describe("the bars", () => {
  it("are heights against the busiest hour", () => {
    expect(barHeightPercent(10, 10)).toBe(100);
    expect(barHeightPercent(5, 10)).toBe(50);
  });

  it("draw an empty hour as a mark rather than as nothing", () => {
    // The weekbar chart's rule: an absent bar and a bar nobody can see are the same to a
    // reader, and "nothing happens before seven" is a reading this chart exists for.
    expect(barHeightPercent(0, 10)).toBe(2);
    expect(barHeightPercent(1, 400)).toBe(2);
  });

  it("collapse to nothing only when there is no peak at all", () => {
    expect(barHeightPercent(0, 0)).toBe(0);
  });
});

describe("the conclusion and the refusals", () => {
  const KEYS: MessageKey[] = [
    "attendanceReport.heading",
    "attendanceReport.chartTitle",
    "attendanceReport.timezone",
    "attendanceReport.visits",
    "attendanceReport.busiest",
    "attendanceReport.quietest",
    "attendanceReport.daysCounted",
    "attendanceReport.nobodyCame",
    "attendanceReport.nobodyCameAtAll",
    "attendanceReport.conclusion",
    "attendanceReport.notCapacity",
    "attendanceReport.noOpeningHours",
    "attendanceReport.presentations",
    "attendanceReport.weekendNotDeclared",
    "attendanceReport.pickSiteInLink",
    "attendanceReport.noLocation",
    "attendanceReport.gapsTitle",
    "attendanceReport.gapClassFillLabel",
    "attendanceReport.gapClassFill",
    "attendanceReport.gapCapacityLabel",
    "attendanceReport.gapCapacity",
    "attendanceReport.gapExportLabel",
    "attendanceReport.gapExport",
    "attendanceReport.site",
    "attendanceReport.daysLabel",
    "attendanceReport.zoneLabel",
    "attendanceReport.wholeClub",
    "attendanceReport.title",
    "attendanceReport.refusedWhy",
    "attendanceReport.retiredZone",
  ];

  it("every key this screen renders exists in both catalogues", () => {
    // **The parity check cannot see this and no assertion about structure can.**
    // `MESSAGE_KEYS` compares the two catalogues against each other, so it is blind to
    // English prose held in a library and rendered straight to the page -- which is how
    // MOD-013's board shipped eight decision reasons in English on an Arabic screen. The
    // rule this repository drew from it is a test per module, asserting that every key
    // *that module maps to* exists in both.
    for (const key of KEYS) {
      expect(MESSAGES.en[key], `${key} missing from English`).toBeTruthy();
      expect(MESSAGES.ar[key], `${key} missing from Arabic`).toBeTruthy();
    }
  });

  it("the conclusion names the window, the peak and the quiet hour in both languages", () => {
    for (const locale of ["en", "ar"] as const) {
      const sentence = fill(locale, "attendanceReport.conclusion", {
        from: "18:00", to: "20:00", peak: 42, quiet: "07:00", percent: 41,
      });
      expect(sentence).toContain("18:00");
      expect(sentence).toContain("20:00");
      expect(sentence).toContain("07:00");
      expect(sentence).toContain("41");
      expect(sentence).toContain("42");
    }
  });

  it("the second-peak sentence has every Arabic plural form it can select", () => {
    // Arabic has six CLDR categories and a missing one throws rather than falling through,
    // which is the right failure and a failure all the same on a page nobody tested in it.
    //
    // **Zero is included and the Arabic zero form repeats `other` on purpose.** The page
    // renders this sentence only where `other_peak_hours` is non-empty, so that category
    // is unreachable -- and the first attempt deleted it for exactly that reason, which
    // the plural parity sweep caught: a missing form falls back to `other` and renders a
    // plural where Arabic wants a dual, so every one of the six has to exist. A zero form
    // reading "no other hour" would also be the one form `fill` refuses, because it could
    // not carry the hours it is passed.
    for (const count of [0, 1, 2, 3, 11, 100]) {
      for (const locale of ["en", "ar"] as const) {
        expect(fill(locale, "attendanceReport.anotherPeak", {
          hours: "07:00", count,
        })).toBeTruthy();
      }
    }
  });

  it("the metric comparisons have every plural form too", () => {
    for (const count of [0, 1, 2, 3, 11, 100]) {
      for (const locale of ["en", "ar"] as const) {
        expect(fill(locale, "attendanceReport.inTheBusiestHour", { count })).toBeTruthy();
        expect(fill(locale, "attendanceReport.overWeeks", { count })).toBeTruthy();
      }
    }
  });

  it("the conclusion's first sentence is emphasised in both languages", () => {
    // The canvas sets it in bold. `Prose` reads `**`, so the emphasis is the translator's
    // rather than the layout's -- and a locale whose markers went missing would render one
    // flat paragraph where the design puts the finding first.
    for (const locale of ["en", "ar"] as const) {
      const template = MESSAGES[locale]["attendanceReport.conclusion"] as string;
      expect(template.startsWith("**")).toBe(true);
      expect(template.split("**").length).toBe(3);
    }
  });

  it("a plain denial names the permission, which the generic gate line cannot", () => {
    // Both sibling reports say "This report needs <permission>" -- the actionable sentence.
    // `gateMessage` cannot say it: its job is to keep a transport failure, an unreachable
    // assurance level and a step-up apart from a denial, so the denial gets this one and
    // the other three keep theirs.
    for (const locale of ["en", "ar"] as const) {
      expect(MESSAGES[locale]["attendanceReport.refusedWhy"])
        .toContain("access.zone.read");
    }
  });

  it("the capacity refusal says what it refuses, in both languages", () => {
    // The canvas writes "94% of floor capacity" and this build will not. A note that said
    // only "shares are relative" would leave a reader to work out which claim is missing.
    expect(MESSAGES.en["attendanceReport.notCapacity"]).toContain("capacity");
    expect(MESSAGES.en["attendanceReport.notCapacity"]).toContain("arrivals");
    expect(MESSAGES.ar["attendanceReport.notCapacity"]).toContain("94%");
  });
});
