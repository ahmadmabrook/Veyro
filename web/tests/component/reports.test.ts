import { describe, expect, it } from "vitest";

import { MESSAGES } from "@/i18n/locale";
import { UNREACHED } from "@/lib/api";
import { REPORTS, UNBUILT, change, sourceName } from "@/lib/reports";

describe("the reports index", () => {
  it("names a permission and a canvas for every report it offers", () => {
    for (const report of REPORTS) {
      expect(report.permission).toMatch(/^[a-z]+\.[a-z_]+\.[a-z_]+$/);
      expect(report.screen).toMatch(/^ADM-RPT-\d\d$/);
      expect(MESSAGES.en[report.name]).toBeTruthy();
      expect(MESSAGES.ar[report.name]).toBeTruthy();
      expect(MESSAGES.en[report.summary]).toBeTruthy();
      expect(MESSAGES.ar[report.summary]).toBeTruthy();
    }
  });

  it("gives every report the design lists and this build lacks a reason, in both languages", () => {
    // An absent module is a different absence from a refused permission. If these were
    // simply missing they would read as four more grants to go and ask for.
    expect(UNBUILT.length).toBe(4);
    for (const entry of UNBUILT) {
      for (const key of [entry.name, entry.why]) {
        expect(MESSAGES.en[key], `${key} missing from English`).toBeTruthy();
        expect(MESSAGES.ar[key], `${key} missing from Arabic`).toBeTruthy();
      }
    }
  });
});

describe("UNREACHED", () => {
  it("separates a gate that said no from a gate that did not answer", () => {
    // **The defect this exists for.** `gateAll` fails closed, which is right for access: an
    // unreachable gate is not permission. But the index then said "No report here is open to
    // this session -- that is about your own access", which is a confident wrong answer when
    // the request simply failed. TestSprite reported the Revenue report absent for an owner
    // holding every permission in the catalogue, twice, and the page had no way to tell six
    // refusals from six failures.
    expect(UNREACHED.has("unreachable")).toBe(true);
    expect(UNREACHED.has("gate_unreachable")).toBe(true);
    // The gate speaking is not a failure, and must not be reported as one.
    expect(UNREACHED.has("forbidden")).toBe(false);
    expect(UNREACHED.has("step_up_required")).toBe(false);
  });

  it("has a message of its own, so the two states cannot render the same words", () => {
    for (const key of ["reports.gateUnreachable", "reports.noneOpen"] as const) {
      expect(MESSAGES.en[key]).toBeTruthy();
      expect(MESSAGES.ar[key]).toBeTruthy();
    }
    expect(MESSAGES.en["reports.gateUnreachable"])
      .not.toBe(MESSAGES.en["reports.noneOpen"]);
  });
});

describe("change", () => {
  it("is null where there is nothing to compare against, which is not zero", () => {
    // "0.0%" claims a month that matched its predecessor exactly.
    expect(change(null)).toBeNull();
  });

  it("signs a fall with a minus sign rather than a hyphen, and leans the right way", () => {
    expect(change(-780)).toEqual({ text: "−7.8%", tone: "down" });
    expect(change(788)).toEqual({ text: "+7.9%", tone: "up" });
  });
});

describe("sourceName", () => {
  it("names each of the catalogue's own product types in both languages", () => {
    for (const type of [
      "membership", "service", "session_credit", "class_credit",
      "retail_sku", "subscription_addon", "event", "gift_card", "unattributed",
    ]) {
      const key = sourceName(type);
      expect(key, `${type} has no name`).not.toBeNull();
      expect(MESSAGES.en[key!]).toBeTruthy();
      expect(MESSAGES.ar[key!]).toBeTruthy();
    }
  });

  it("returns null for a type added later rather than calling it other", () => {
    // This is a revenue table: the whole point is knowing what earned the money.
    expect(sourceName("day_pass")).toBeNull();
  });
});
