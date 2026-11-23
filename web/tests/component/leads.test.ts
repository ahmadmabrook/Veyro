import { describe, expect, test } from "vitest";

import { MESSAGES } from "@/i18n/locale";
import {
  BOARD_COLUMNS, CARDS_PER_COLUMN, columnCount, columnNote, interestWord, isLeadFilter,
  isLeadView, kindWord, metaLine, sinceLabel, stageWord, type LeadRow,
} from "@/lib/leads";

/**
 * ADM-CRM-01 and ADM-CRM-02's decisions, asserted against the canvas's own strings.
 *
 * The canvas writes its meta lines out -- "open day · 2d", "instagram · 4h", "called · 1d" --
 * so those are what is asserted rather than a restatement of the expression, which would pass
 * against any unit.
 */

const LEAD = (over: Partial<LeadRow> = {}): LeadRow => ({
  lead_id: "l1",
  person_id: "p1",
  stage: "new",
  source_id: "s1",
  source: "Sweifieh open day",
  owner_person_id: null,
  next_action: null,
  next_action_on: null,
  created_at: "2026-08-17T09:00:00Z",
  version: 1,
  last_touch_at: null,
  hours_since_contact: 48,
  going_cold: true,
  ...over,
});

describe("the board's five columns", () => {
  test("are the canvas's own, in its order", () => {
    expect(BOARD_COLUMNS).toEqual(["new", "contacted", "toured", "on_trial", "joined"]);
  });

  test("the On trial column carries its reason and no other does", () => {
    expect(columnNote("on_trial")).toBe("leads.onTrialEmpty");
    for (const stage of BOARD_COLUMNS.filter((one) => one !== "on_trial")) {
      expect(columnNote(stage)).toBeNull();
    }
  });

  test("a count goes through the one number path", () => {
    // Not `String(n)`: this app has one number formatter and a cross-runtime parity test
    // behind it, so a second one is the drift that test exists to catch.
    expect(columnCount(12)).toBe("12");
    expect(columnCount(1200)).toBe("1,200");
  });

  test("two cards a column, which is what the canvas draws", () => {
    expect(CARDS_PER_COLUMN).toBe(2);
  });
});

describe("the age label", () => {
  test("the canvas's two forms: hours below a day and days above it", () => {
    expect(sinceLabel("en", 4)).toBe("4h");
    expect(sinceLabel("en", 23)).toBe("23h");
    expect(sinceLabel("en", 24)).toBe("1d");
    expect(sinceLabel("en", 48)).toBe("2d");
  });

  test("under an hour is a word rather than a zero", () => {
    // "0h" reads as a measurement and is one nobody wants; the canvas has no such case, and
    // a lead touched a minute ago is "just now" in any product.
    expect(sinceLabel("en", 0)).toBe("just now");
  });

  test("the days are whole, because this app's number path throws for a fraction", () => {
    expect(sinceLabel("en", 59)).toBe("2d");
  });

  test("Arabic takes its own plural forms rather than the English ones", () => {
    expect(sinceLabel("ar", 2)).toBe("ساعتان");
    expect(sinceLabel("ar", 48)).toBe("يومان");
  });
});

describe("the meta line", () => {
  test("is the canvas's own shape", () => {
    expect(metaLine("en", LEAD({ hours_since_contact: 48 })))
      .toBe("Sweifieh open day · 2d");
    expect(metaLine("en", LEAD({ source: "Instagram", hours_since_contact: 4 })))
      .toBe("Instagram · 4h");
  });

  test("an unattributed lead says so rather than leaving the line half-empty", () => {
    // "Where did this come from" is the question ADM-RPT-03 is built on, so the absence is
    // the answer that matters most -- not a blank before a separator.
    expect(metaLine("en", LEAD({ source: null, hours_since_contact: 4 })))
      .toBe("no source recorded · 4h");
  });
});

describe("a stored vocabulary is never a label", () => {
  test("every stage, kind and interest the server can send has a word in both locales", () => {
    // **The defect this is written against has happened four times in this app**: a
    // `lifecycle_state` rendered as `lead`, a plan as `recurring`, a wallet kind and a
    // credential kind -- each Latin letters in the middle of an Arabic line. `MESSAGE_KEYS`
    // is structurally blind to it, because the string never became a key.
    const keys = [
      ...BOARD_COLUMNS.map(stageWord),
      ...["call", "message", "email", "visit", "tour", "note"].map(kindWord),
      ...["classes", "pt", "gym_only"].map(interestWord),
    ];
    for (const key of keys) {
      expect(key).not.toBeNull();
      expect(MESSAGES.en[key!]).toBeDefined();
      expect(MESSAGES.ar[key!]).toBeDefined();
    }
  });

  test("a value this build has no word for falls through rather than reading as other", () => {
    // The set is the server's and may grow: showing an ugly value is better than hiding a
    // stage somebody needs to see, which is the rule the members list settled.
    expect(stageWord("lost")).toBeNull();
    expect(kindWord("carrier_pigeon")).toBeNull();
    expect(interestWord("nutrition")).toBeNull();
  });
});

describe("the view and filter parameters", () => {
  test("only the two views and the three filters are accepted", () => {
    expect(isLeadView("board")).toBe(true);
    expect(isLeadView("table")).toBe(true);
    expect(isLeadView("kanban")).toBe(false);
    expect(isLeadView(undefined)).toBe(false);
    expect(isLeadFilter("going_cold")).toBe(true);
    expect(isLeadFilter("trial_ending")).toBe(false);
  });
});
