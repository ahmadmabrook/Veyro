import { describe, expect, it } from "vitest";

import { shapeDigits } from "@/i18n/conventions.mjs";
import { monthDay, DateFormatError } from "@/i18n/dates";
import { fill, formatMoney, isolate, MESSAGES, t } from "@/i18n/locale";
import {
  LANGUAGES_KEY,
  NUMERALS_KEY,
  PREVIEW_AMOUNT_MINOR,
  PREVIEW_CURRENCY,
  PREVIEW_DATE,
  isDefaulted,
  previewLocale,
  type DisplayConventions,
} from "@/lib/display";

/**
 * ADM-SET-07's three decisions, tested where they are made, and the preview end to end.
 *
 * **The canvas's own sentence is the assertion.** `تنتهي عضويتك في ٢١ آب · المبلغ JOD 55.00` is
 * four claims at once -- the Levantine month name, Arabic-Indic digits on the date, Latin
 * digits on the money, and the two isolated from each other -- so rendering it through the
 * product's own functions and comparing the string is the only test that covers all four.
 */

function conventions(over: Partial<DisplayConventions> = {}): DisplayConventions {
  return {
    numerals: "latn",
    languages_offered: ["en", "ar"],
    month_names: "levantine",
    money_numerals: "latn",
    declared: [],
    ...over,
  };
}

describe("the month name comes from the region, not the language", () => {
  it("renders the Levantine set that Jordanian members read", () => {
    // `آب` is the whole reason the tag is `ar-JO`: plain `ar` gives the Egyptian-influenced
    // `أغسطس`, which is a different word for the same month and not the one the canvas draws.
    expect(monthDay("2026-08-21", "ar", "arab")).toContain("آب");
    expect(monthDay("2026-08-21", "ar", "arab")).not.toContain("أغسطس");
  });

  it("forces the numbering rather than letting the regional tag decide it", () => {
    // **`ar-JO` resolves to `arab` by default**, so a tag alone would make the digits follow
    // the language -- which is exactly what `formatInteger`'s contract forbids: "a tenant must
    // not get Arabic-Indic digits merely because a string was Arabic". A `latn` tenant reading
    // Arabic gets Latin digits beside an Arabic month name, and that pair is the proof.
    expect(monthDay("2026-08-21", "ar", "latn")).toBe("21 آب");
    expect(monthDay("2026-08-21", "ar", "arab")).toBe("٢١ آب");
  });

  it("normalises in both directions, which is why the forced tag is for a third locale", () => {
    // **The premise behind `monthDay`'s `-u-nu-latn`, found by a mutation rather than by a
    // reader.** `shapeDigits`' `latn` branch converts U+0660-0669 *back* to ASCII, so
    // removing the forced tag produces the identical string here and the sweep reported it
    // uncaught -- correctly. The guard is for a locale whose default digits this function
    // does not know how to undo, which this build does not have, so this asserts the fact
    // the redundancy rests on instead of pretending there is a case for the guard.
    expect(shapeDigits("٢١", "latn")).toBe("21");
    expect(shapeDigits("21", "arab")).toBe("٢١");
    // Persian's `arabext` is the shape a third locale would arrive in, and it passes through
    // untouched -- which is the whole reason the formatter is not allowed to emit it.
    expect(shapeDigits("\u06F2\u06F1", "latn")).toBe("\u06F2\u06F1");
  });

  it("gives an English reader the English month under the tenant's digits", () => {
    expect(monthDay("2026-08-21", "en", "latn")).toBe("21 August");
    expect(monthDay("2026-08-21", "en", "arab")).toBe("٢١ August");
  });

  it("renders the day the date names, in every runtime zone", () => {
    // `new Date("2026-08-21")` is UTC midnight, so formatting it in the runtime's own zone
    // renders the 20th anywhere west of Greenwich. Three defects here have come from that
    // frame, and the first of the month is where it shows.
    expect(monthDay("2026-01-01", "en", "latn")).toBe("1 January");
    expect(monthDay("2026-12-31", "en", "latn")).toBe("31 December");
  });

  it("refuses anything that is not a calendar date", () => {
    // An instant has a zone and a day and a month in a sentence has neither, so taking one
    // would be inviting a caller to slice an ISO string -- which is how the schedule board
    // rendered a UTC wall time under a heading promising the site's own.
    for (const bad of ["2026-08-21T10:00:00Z", "2026-8-21", "21/08/2026", "", "not a date"]) {
      expect(() => monthDay(bad, "en", "latn")).toThrow(DateFormatError);
    }
  });
});

describe("the preview, as the canvas draws it", () => {
  const sentence = (numerals: "latn" | "arab") =>
    fill("ar", "localization.previewSentence", {
      on: isolate(monthDay(PREVIEW_DATE, "ar", numerals), "auto"),
      amount: formatMoney(PREVIEW_AMOUNT_MINOR, PREVIEW_CURRENCY, "latn", "ar"),
    });

  it("is the canvas's own string for a tenant on Arabic-Indic digits", () => {
    // Bidi controls stripped, because the canvas expresses the isolation as CSS and this app
    // expresses it as characters: the same property, so the comparison is of the text.
    const plain = sentence("arab").replace(/[⁦-⁩]/g, "");
    expect(plain).toBe("تنتهي عضويتك في ٢١ آب · المبلغ JOD 55.00");
  });

  it("keeps money in Latin digits while the date follows the tenant", () => {
    // The one thing on the screen a reader cannot verify any other way: the two run under
    // different rules and the canvas says why -- "that is the form on your invoices and
    // JoFotara submissions".
    expect(sentence("arab")).toContain("٢١");
    expect(sentence("arab")).toContain("JOD 55.00");
    expect(sentence("arab")).not.toContain("٥٥");
  });

  it("isolates both figures, so neither re-orders the Arabic around it", () => {
    // Without it `JOD` jumps to the wrong side of its amount, which the conventions module
    // calls "a money-ambiguity defect, not a typographic one".
    const built = sentence("latn");
    expect(built).toMatch(/[⁦-⁨]/);
    expect(built.match(/⁩/g)?.length).toBe(2);
  });
});

describe("which language the preview renders in", () => {
  it("is Arabic wherever Arabic is offered, whatever the reader's own language is", () => {
    // An English-locale owner checking their tenant's Arabic rendering is the ordinary case.
    expect(previewLocale(conventions())).toBe("ar");
    expect(previewLocale(conventions({ languages_offered: ["ar"] }))).toBe("ar");
  });

  it("is English where Arabic is not offered", () => {
    // A preview of a surface nobody will see demonstrates nothing. Not drawn on the canvas,
    // whose tenant offers both.
    expect(previewLocale(conventions({ languages_offered: ["en"] }))).toBe("en");
  });
});

describe("a default is not a decision", () => {
  it("reads an undeclared key as defaulted", () => {
    // A tenant that has configured nothing resolves to Latin digits and every catalogue this
    // build has, which is what every page renders today -- so the values alone cannot tell it
    // from a tenant that chose them.
    const fresh = conventions();
    expect(isDefaulted(fresh, NUMERALS_KEY)).toBe(true);
    expect(isDefaulted(fresh, LANGUAGES_KEY)).toBe(true);
  });

  it("reads a declared key as a decision, even when the value is the default's", () => {
    // The sharp case: `latn` declared on purpose is the same value and a different fact.
    const chosen = conventions({ declared: [NUMERALS_KEY] });
    expect(isDefaulted(chosen, NUMERALS_KEY)).toBe(false);
    expect(isDefaulted(chosen, LANGUAGES_KEY)).toBe(true);
  });
});

describe("every message this screen renders exists in both catalogues", () => {
  it("has the Arabic for each key, because there is no fallback to English", () => {
    // `t` throws for a missing key rather than returning it, so a gap is a 500 on a rendered
    // page -- and `MESSAGE_KEYS` compares the two catalogues against each other, which is
    // blind to a string that never became a key. This asserts the keys the screen uses.
    const keys = Object.keys(MESSAGES.en)
      .filter((key) => key.startsWith("localization.") || key === "nav.localization");
    expect(keys.length).toBeGreaterThan(10);
    for (const key of keys) {
      for (const locale of ["en", "ar"] as const) {
        const entry = MESSAGES[locale][key as keyof typeof MESSAGES.en];
        expect(entry, `${locale} ${key}`).toBeDefined();
        if (typeof entry === "string") {
          expect(entry.length, `${locale} ${key}`).toBeGreaterThan(0);
        }
      }
    }
  });

  it("names a numeral system in words, because the chips are only samples", () => {
    // The samples `0123` and `٠١٢٣` read aloud as digits either way, so the figures line is
    // where the system is named -- and in the reader's own language.
    expect(t("en", "localization.latn")).toBe("Latin digits");
    expect(t("ar", "localization.arab")).not.toMatch(/[A-Za-z]/);
  });
});
