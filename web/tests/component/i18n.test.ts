import { describe, expect, it } from "vitest";

import {
  DEFAULT_LOCALE,
  LOCALES,
  MESSAGES,
  MESSAGE_KEYS,
  MissingMessageError,
  asLocale,
  direction,
  formatInteger,
  formatMoney,
  isolate,
  script,
  t,
} from "@/i18n/locale";
import { parseLocaleStrict, parseThemeStrict, safeLocale, safeTheme } from "@/lib/preferences";

/**
 * The typed locale surface and the preference narrowing.
 *
 * The formatting rules themselves are proven byte-identical to `backend/app/l10n/conventions.py`
 * by `tests/unit/conventions-parity.test.mjs`, which spawns Python and compares. What is tested
 * here is the layer above it: the catalogue, the fail-closed lookup, and the two places an
 * untrusted string becomes a `lang`, a `dir` or a `data-theme` attribute.
 */

describe("the message catalogue", () => {
  it("covers every key in both locales", () => {
    for (const locale of LOCALES) {
      const missing = MESSAGE_KEYS.filter((key) => !(key in MESSAGES[locale]));
      expect(missing, `${locale} is missing ${missing.join(", ")}`).toEqual([]);
    }
  });

  it("has no key in one locale that is in no other", () => {
    // **Both directions.** `MESSAGE_KEYS` is the English catalogue's own keys, so the check
    // above sees an English key missing from Arabic and is blind to the reverse -- and an
    // Arabic-only key is a translation nothing renders, which reads as a translated interface
    // to anything counting keys. Found by adding one by accident and watching this file stay
    // green; it is the same both-directions rule the id sweep and the worker's name list are
    // built on.
    const english = new Set(Object.keys(MESSAGES.en));
    for (const locale of LOCALES) {
      const extra = Object.keys(MESSAGES[locale]).filter((key) => !english.has(key));
      expect(extra, `${locale} has ${extra.join(", ")} and English does not`).toEqual([]);
    }
  });

  it("has no key whose Arabic is the English string", () => {
    // A copied English value is the half-translated interface the catalogue exists to prevent,
    // and it reads as "translated" to anything counting keys. Identifiers and numerals would be
    // legitimate exceptions; there are none in this catalogue, so the rule is absolute here.
    //
    // **The compiler already proves this**, which is the better half of the answer: `MESSAGES`
    // is `as const`, so the two catalogues have disjoint literal-union types and `tsc` rejects
    // the comparison outright with "no overlap" unless the values are widened. The runtime
    // check stays because the day somebody drops the `as const` -- or builds a catalogue from
    // data rather than literals -- the compile-time proof silently stops being made.
    const ar: Record<string, string> = MESSAGES.ar;
    const en: Record<string, string> = MESSAGES.en;
    const copied = MESSAGE_KEYS.filter((key) => ar[key] === en[key]);
    expect(copied, `untranslated: ${copied.join(", ")}`).toEqual([]);
  });

  it("throws for a missing key rather than falling back to English", () => {
    // "Quietly sending English to somebody who asked for Arabic is worse than refusing" --
    // MOD-013's rule for notifications, and the same holds on a screen. A fallback makes a gap
    // ship; a throw makes it fail a test.
    expect(() => t("ar", "nope" as never)).toThrow(MissingMessageError);
  });

  it("resolves a real key in both locales", () => {
    expect(t("en", "login.title")).toBe("Sign in");
    expect(t("ar", "login.title")).toBe("تسجيل الدخول");
  });
});

describe("locale facts are derived, never accepted", () => {
  it("derives direction and script from the locale", () => {
    expect(direction("ar")).toBe("rtl");
    expect(direction("en")).toBe("ltr");
    expect(script("ar")).toBe("arabic");
    expect(script("en")).toBe("latin");
  });

  it("fails closed on an unknown tag", () => {
    expect(() => asLocale("fr")).toThrow();
    expect(() => asLocale(undefined)).toThrow();
  });
});

describe("preference cookies", () => {
  it("fall back to the default when unreadable, rather than throwing", () => {
    // `asLocale` is right to throw at an API boundary and wrong in a layout: a stale cookie
    // would otherwise make every page 500 instead of rendering in the default language.
    expect(safeLocale("fr")).toBe(DEFAULT_LOCALE);
    expect(safeLocale(undefined)).toBe(DEFAULT_LOCALE);
    expect(safeLocale("ar")).toBe("ar");
    expect(safeTheme("neon")).toBe("light");
    expect(safeTheme("dark")).toBe("dark");
  });

  it("refuse to store anything outside the closed set", () => {
    // The write path is separate from the read path because this cookie is echoed into `lang`,
    // `dir` and `data-theme` on `<html>`. A cookie that could hold any string would be an
    // attribute-injection sink one `document.cookie` away.
    expect(parseLocaleStrict("ar")).toBe("ar");
    expect(parseLocaleStrict("en")).toBe("en");
    expect(parseLocaleStrict('en" onload="alert(1)')).toBeNull();
    expect(parseLocaleStrict("")).toBeNull();
    expect(parseLocaleStrict(null)).toBeNull();
    expect(parseThemeStrict("dark")).toBe("dark");
    expect(parseThemeStrict("dark; --x: y")).toBeNull();
  });
});

describe("numerals and money", () => {
  it("formats integers in the tenant's numbering, not the locale's", () => {
    // The numbering system is a tenant setting chosen once, never derived from the language:
    // an Arabic-reading tenant that bills in Latin numerals must not have its invoices change
    // script because somebody switched the interface.
    expect(formatInteger(1234, "latn")).toBe("1,234");
    expect(formatInteger(1234, "arab")).toBe("١٬٢٣٤");
  });

  it("isolates money so the currency cannot jump sides in Arabic", () => {
    // Without the isolate, JOD lands on the wrong side of its amount -- a money-ambiguity
    // defect rather than a typographic one.
    const amount = formatMoney(4500, "JOD", "latn", "ar");
    expect(amount).toContain("⁦"); // LRI
    expect(amount).toContain("⁩"); // PDI
  });

  it("wraps a run in the direction it is given", () => {
    expect(isolate("ACME Ltd", "ltr")).toBe("⁦ACME Ltd⁩");
  });
});
