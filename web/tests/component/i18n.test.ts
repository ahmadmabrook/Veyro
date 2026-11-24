import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

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
    // A plural key's value is an object of CLDR forms, so the comparison is over its forms
    // rather than over the value -- an Arabic `other` copied from English is the same defect
    // one level down, and comparing the objects by identity would miss every one of them.
    const ar: Record<string, string | Record<string, string>> = MESSAGES.ar;
    const en: Record<string, string | Record<string, string>> = MESSAGES.en;
    const sameText = (key: string): boolean => {
      const a = ar[key];
      const e = en[key];
      if (typeof a === "string" || typeof e === "string") return a === e;
      if (a === undefined || e === undefined) return false;
      return Object.keys(e).some((form) => a[form] !== undefined && a[form] === e[form]);
    };
    const copied = MESSAGE_KEYS.filter(sameText);
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

describe("a message is text, not an escape sequence", () => {
  /**
   * **Found by looking at a page, twice removed from anything a test could see.** A message
   * written through a generator came out carrying a literal `“` -- two characters and
   * four digits where a quotation mark was meant -- and rendered exactly that way on the
   * messages board. Every existing check passed: the key is in both catalogues, the plural
   * forms match, the parity test compares key sets, and `“` is a perfectly ordinary
   * string as far as any of them are concerned.
   *
   * A catalogue entry is read by a person. A backslash-escape in it is never intentional --
   * TypeScript interprets the real ones at parse time, so anything that survives into the
   * value is one that was escaped twice.
   */
  it("carries no literal backslash escape in either locale", () => {
    const offenders: string[] = [];
    for (const locale of ["en", "ar"] as const) {
      for (const key of MESSAGE_KEYS) {
        const entry = MESSAGES[locale][key];
        const values = typeof entry === "string" ? [entry] : Object.values(entry);
        for (const value of values) {
          if (/\\[unrt]/.test(value)) offenders.push(`${locale}:${key}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});

/**
 * **A placeholder is a contract between a message and its call site, and nothing checked it.**
 *
 * `fill` is strict in both directions at runtime -- it throws for a placeholder with no value
 * and for a value with no placeholder -- so every mismatch is a 500 on a rendered page. What
 * there was no check for is the mismatch *existing*, and it arrived the way these always do:
 * a placeholder renamed across the catalogue to suit one new message, which took six others
 * with it. `cc.retentionTitle` is "{count} memberships expire within {days} days" and became
 * "within {count} days" -- two different numbers collapsed into one, and the Command Center
 * answered an error boundary for every reader.
 *
 * Nothing in four layers could see it. The key is in both catalogues, the plural forms match,
 * the parity test compares key *sets*, and a renamed placeholder is an ordinary string. **It
 * was found by signing in**, which is the same sentence this repository has written about a
 * timezone, a badge and a duplicated grid cell.
 */
describe("a placeholder is a contract", () => {
  /** The `{names}` a template mentions, across every plural form of it. */
  function placeholders(entry: string | Record<string, string>): Set<string> {
    const texts = typeof entry === "string" ? [entry] : Object.values(entry);
    const found = new Set<string>();
    for (const text of texts) {
      for (const m of text.matchAll(/\{(\w+)\}/g)) found.add(m[1]!);
    }
    return found;
  }

  it("names the same values in both languages", () => {
    // **A form in one language naming a placeholder the other does not is a throw only that
    // language's readers get**, and `MESSAGE_KEYS` compares key sets rather than text. The
    // one exception is `count`, which selects the plural form and may legitimately not appear
    // in a form that spells the numeral out -- "one membership expires" has no numeral at all.
    const offenders: string[] = [];
    for (const key of MESSAGE_KEYS) {
      const en = placeholders(MESSAGES.en[key]);
      const ar = placeholders(MESSAGES.ar[key]);
      en.delete("count");
      ar.delete("count");
      const onlyEn = [...en].filter((name) => !ar.has(name));
      const onlyAr = [...ar].filter((name) => !en.has(name));
      if (onlyEn.length || onlyAr.length) {
        offenders.push(`${key}: en-only ${onlyEn.join()} / ar-only ${onlyAr.join()}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  /** Blank out string literals and comments, so a comma or a colon inside one is not read. */
  function strip(body: string): string {
    return body
      .replace(/\/\*[\s\S]*?\*\//g, " ")
      .replace(/\/\/[^\n]*/g, " ")
      .replace(/"(?:[^"\\]|\\.)*"/g, '""')
      .replace(/'(?:[^'\\]|\\.)*'/g, "''")
      .replace(/`(?:[^`\\]|\\.)*`/g, "``");
  }

  /** Split an object literal's body at its own commas, ignoring nested ones. */
  function entries(body: string): string[] {
    const out: string[] = [];
    let depth = 0;
    let token = "";
    for (const ch of body) {
      if ("{([".includes(ch)) depth += 1;
      else if ("})]".includes(ch)) depth -= 1;
      if (depth === 0 && ch === ",") { out.push(token); token = ""; } else token += ch;
    }
    if (token.trim()) out.push(token);
    return out;
  }

  /** Where this entry's own colon is, or -1 for a shorthand like `{ count }`. */
  function depthZeroColon(entry: string): number {
    let depth = 0;
    for (let i = 0; i < entry.length; i += 1) {
      const ch = entry[i]!;
      if ("{([".includes(ch)) depth += 1;
      else if ("})]".includes(ch)) depth -= 1;
      else if (depth === 0 && ch === ":") return i;
    }
    return -1;
  }

  /**
   * Every `fill(locale, "a.key", { … })` in the app, with the names it passes.
   *
   * **Only the sites a reader can judge.** A computed key, a spread, or anything that is not a
   * plain object literal is skipped and counted: a check that reported a defect the app does
   * not have costs the same trust as one that misses a defect it does, and this repository has
   * paid that once already for a regex that stopped at a TypeScript generic's `>`.
   */
  function fillSites(): {
    key: string; names: string[]; values: Record<string, string>;
    where: string;
  }[] {
    const out: {
      key: string; names: string[]; values: Record<string, string>; where: string;
    }[] = [];
    const walk = (dir: string) => {
      for (const name of readdirSync(dir)) {
        const path = join(dir, name);
        if (statSync(path).isDirectory()) {
          walk(path);
        } else if (/\.tsx?$/.test(name)) {
          const text = readFileSync(path, "utf8");
          for (const m of text.matchAll(/\bfill\(\s*\w+\s*,\s*"([\w.]+)"\s*,\s*\{/g)) {
            const open = m.index! + m[0].length - 1;
            let depth = 0;
            let end = open;
            for (let i = open; i < text.length; i += 1) {
              if (text[i] === "{") depth += 1;
              else if (text[i] === "}") {
                depth -= 1;
                if (depth === 0) { end = i; break; }
              }
            }
            const body = strip(text.slice(open + 1, end));
            if (body.includes("...")) continue; // not judgeable; see the docstring
            // **An entry's name is what sits before its colon, and the first version read
            // what sat after.** `fill(locale, "stepUp.about", { action: about })` reported
            // `{about}` as a value the message does not name -- a false finding from the
            // check rather than from the app, which is the one failure mode a sweep must not
            // have. So the body is split at depth-0 commas and each entry is judged whole.
            const parsed = entries(body).map((entry) => {
              const colon = depthZeroColon(entry);
              const name = (colon < 0 ? entry : entry.slice(0, colon)).trim();
              // The *expression*, kept beside the name: a plural `count` has to be a number
              // and the one way this app turns a number into a string is `formatInteger`.
              const value = colon < 0 ? name : entry.slice(colon + 1).trim();
              return { name, value };
            }).filter((entry) => /^\w+$/.test(entry.name));
            const names = parsed.map((entry) => entry.name);
            const values = Object.fromEntries(
              parsed.map((entry) => [entry.name, entry.value]));
            out.push({ key: m[1]!, names, values, where: path });
          }
        }
      }
    };
    walk("src");
    return out;
  }

  it("is honoured by every call site that passes a literal key", () => {
    const sites = fillSites();
    // A guard against the sweep passing vacuously, which is what a regex that matches
    // nothing does. Every screen that renders a number goes through `fill`.
    expect(sites.length).toBeGreaterThan(40);

    const offenders: string[] = [];
    for (const site of sites) {
      if (!(MESSAGE_KEYS as readonly string[]).includes(site.key)) {
        offenders.push(`${site.where}: ${site.key} is not a message key`);
        continue;
      }
      const entry = MESSAGES.en[site.key as (typeof MESSAGE_KEYS)[number]];
      const plural = typeof entry !== "string";
      for (const locale of LOCALES) {
        const message = MESSAGES[locale][site.key as (typeof MESSAGE_KEYS)[number]];
        // **Per plural form, not over their union.** `fill` picks one form from the count
        // and validates the call against *that* text, so a value the picked form does not
        // name throws for exactly the counts that pick it -- which is how the Command Center
        // broke: `{days}` was renamed in the `one` form only, the `other` form still named
        // it, and a union-of-forms check saw nothing. **The sweep is what found that**: the
        // mutation reproducing the real defect came back uncaught against the first version
        // of this very test.
        const forms = typeof message === "string"
          ? { "": message } : (message as Record<string, string>);
        for (const [form, text] of Object.entries(forms)) {
          const wanted = new Set(
            [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1] as string));
          const where = form ? `${locale}:${form}` : locale;
          for (const name of wanted) {
            if (name === "count") continue;
            if (!site.names.includes(name)) {
              offenders.push(`${site.where}: ${site.key} (${where}) needs {${name}}`);
            }
          }
          for (const name of site.names) {
            if (name === "count") continue;
            if (!wanted.has(name)) {
              offenders.push(`${site.where}: ${site.key} (${where}) has no {${name}}`);
            }
          }
        }
      }
      // A plural message picks its form from `count`, so a site that omits it throws at the
      // first render whatever the text says.
      if (plural && !site.names.includes("count")) {
        offenders.push(`${site.where}: ${site.key} is plural and needs a numeric count`);
      }
      // **And a `count` that has already been formatted is the same throw**, which is the
      // half this sweep could not see until FD-05 hit it. `fill` picks the plural form from
      // a *number* and formats it itself; a site passing `formatInteger(...)` passes a
      // string, so the page answers 500 on every render of that branch. **Two shipped
      // screens had it** -- ADM-MEM-10's and ADM-CRM-04's "also held by N other records",
      // reachable the moment one phone number is held by two people, which is the family
      // line those screens exist for. Neither branch had ever rendered, because the fixture
      // seeded two *different* numbers: a surface branch no fixture can reach, in its
      // quietest form. `formatInteger` is the only number-to-string path in this app, so
      // naming it is exact rather than a guess at what "numeric" means.
      if (plural && (site.values["count"] ?? "").includes("formatInteger")) {
        offenders.push(
          `${site.where}: ${site.key} passes a formatted count; `
          + "`fill` needs the number and formats it itself");
      }
    }
    expect([...new Set(offenders)]).toEqual([]);
  });
});
