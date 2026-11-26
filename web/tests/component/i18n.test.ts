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

  it("has no plural message written as a string", () => {
    // **A plural message here is an object of CLDR forms**, and written as ICU's brace-pipe
    // string -- `{one=...|other=...}` -- it is a *plain* message whose text happens to
    // contain braces. `fill` substitutes the `{of}` inside it and returns the rest verbatim,
    // so the page renders the template: the reader sees every form at once, separated by
    // pipes. ADM-SCH-05 shipped two of them.
    //
    // **Four layers could not see it and the fifth was a person looking at the page.** Both
    // catalogues had the key, so the parity check passed. The per-form sweep read the entry
    // as a string with one placeholder, which is exactly what the call site supplied, so it
    // passed. The numerals sweep filters on plural keys and this was not one, so it passed.
    // And the browser assertion was `toContainText("Uses 1 of the member's 2 remaining
    // credits")`, which the raw template *contains* -- a substring assertion cannot tell a
    // rendered plural from its own unrendered template, because the template holds every
    // form's text. An independent tester reading the screen is what found it.
    //
    // The syntax never occurs in prose, so the ban is exact rather than a heuristic.
    const offenders: string[] = [];
    for (const locale of LOCALES) {
      const catalogue = MESSAGES[locale] as Record<string, string | Record<string, string>>;
      for (const key of MESSAGE_KEYS) {
        const entry = catalogue[key];
        const texts = typeof entry === "string" ? [entry] : Object.values(entry ?? {});
        for (const text of texts) {
          if (/\{\w+=/.test(text)) offenders.push(`${locale}:${key}`);
        }
      }
    }
    expect(offenders, "a plural message is an object of forms, not a brace-pipe string")
      .toEqual([]);
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

describe("the catalogue speaks the operator's language", () => {
  it("no message names a module, a screen id, a route or a database identifier", () => {
    // **The directive is explicit**: backend module names, UUIDs and diagnostic text do not
    // belong in normal product UI. Twenty-four messages named one -- `MOD-022`, `ADM-POS-01`,
    // `resolve_price`, `payment_method_ref`, `ntf_preferences` -- and every one of them was
    // rendered on a screen a gym owner, a club manager or a receptionist opens. Those are
    // true and useful engineering records; they belong in the repository, and the product
    // fact each carried was rewritten in the reader's own language instead.
    //
    // `snake_case` catches a table or column name and a Python function; the id patterns catch
    // a module or a design-canvas screen. A real English word with an underscore in it would
    // be a false positive, and there are none -- the catalogue is prose.
    const banned = [
      /\bMOD-\d+/,
      /\bADM-[A-Z]{2,4}-?\*?\d*/,
      /\b(?:FD|CON|POS|IAM|PLT|SEC|DAT|REL|ECO|ENG|PPL|COM|OPS|HW|ACC|AUT)-\d+/,
      /\b[a-z]+_[a-z_]+\b/,
      /\b(?:GET|POST|PATCH|DELETE) \//,
      // A requirement id and a specification paragraph are the same kind of reference: true,
      // useful to whoever maintains Veyro, and unlookupable by the person reading the screen.
      /\b(?:ENG|PPL|COM|OPS|PLT|SEC|DAT|REL|ECO|HW|ACC|AUT|IAM)-\d+(?:-R\d+)?/,
      /\b[Pp]aragraph \d+/,
    ];
    const offenders: string[] = [];
    for (const locale of ["en", "ar"] as const) {
      for (const [key, value] of Object.entries(MESSAGES[locale])) {
        const forms: string[] =
          typeof value === "string" ? [value] : (Object.values(value) as string[]);
        for (const form of forms) {
          const hit = banned.find((r) => r.test(form));
          if (hit) offenders.push(`${locale}:${key} (${hit.source})`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});

describe("digits never live in the catalogue", () => {
  it("no message in either locale contains an Arabic-Indic digit", () => {
    // **A digit inside message text escapes every numerals sweep this app has.** The others
    // read `fill` call sites and `formatInteger` literals; a figure typed into the catalogue
    // is neither, so it renders whatever the translator typed regardless of the tenant's
    // `localization.numerals` setting. Two Arabic messages carried Arabic-Indic digits --
    // "٣٠ يومًا" and "٧ أيام" -- and rendered them beside "JOD 72.20", "8" and "0" in Latin on
    // the same screen, which `ARABIC_RULES` forbids in as many words: "Never mixed within a
    // tenant, and never decided per component."
    //
    // The rule this encodes: a quantity reaches a message as a *value*, through `fill`, which
    // formats it in the tenant's own system. A number that is part of the sentence rather
    // than data -- there are none here -- would have to be declared.
    const offenders: string[] = [];
    for (const locale of ["en", "ar"] as const) {
      for (const [key, value] of Object.entries(MESSAGES[locale])) {
        const forms: string[] =
          typeof value === "string" ? [value] : (Object.values(value) as string[]);
        for (const form of forms) {
          if (/[\u0660-\u0669\u06f0-\u06f9]/.test(form)) offenders.push(`${locale}:${key}`);
        }
      }
    }
    expect(offenders).toEqual([]);
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
    /** Whatever follows the values object up to the call's own close: the numbering, or "". */
    tail: string;
    where: string;
  }[] {
    const out: {
      key: string; names: string[]; values: Record<string, string>; tail: string;
      where: string;
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
            // **The fourth argument, which is the numbering.** `fill` defaults it to `latn`,
            // so a plural site that omits it renders Latin digits whatever the tenant chose --
            // which is the half ADR-0015 had to enumerate: 82 sites across 34 files, found by
            // this sweep rather than by reading. Read from the close of the values object to
            // the close of the call, so a nested object or call in the argument is included.
            let after = end + 1;
            let callDepth = 1;
            for (let i = end + 1; i < text.length; i += 1) {
              if ("([{".includes(text[i]!)) callDepth += 1;
              else if (")]}".includes(text[i]!)) {
                callDepth -= 1;
                if (callDepth === 0) { after = i; break; }
              }
            }
            const tail = strip(text.slice(end + 1, after)).trim().replace(/^,/, "").trim();
            out.push({ key: m[1]!, names, values, tail, where: path });
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
      // **And the inverse: a `count` that reaches nothing.** `fill` exempts `count` from the
      // unexpected-value throw, because a plural form may legitimately drop the numeral --
      // so a count passed to a message that is neither plural nor spells `{count}` is
      // silently discarded, and the author believes a form is being selected when one
      // sentence is being rendered for every number. That is the brace-pipe defect's other
      // half: the catalogue sweep catches the plural written with pipes, this catches the
      // one written as plain prose. A plain message that *does* name `{count}` is ordinary
      // and is seven of this catalogue's own.
      if (!plural && site.names.includes("count")
          && !(entry as string).includes("{count}")) {
        offenders.push(
          `${site.where}: ${site.key} is not plural and names no {count}, `
          + "so the count it is passed reaches nothing");
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

  /**
   * ADR-0015's own sweep: the tenant's numeral setting reaches every figure, or it reaches
   * none of them.
   *
   * **"One rule per tenant, never mixed and never decided per component"** is the canvas's own
   * sentence, which makes this an all-or-nothing property rather than a per-screen choice: a
   * page whose counts follow the setting beside a rail figure that does not is exactly the
   * mixing it forbids. So the enforcement has to be a sweep, and the sweep is what gave the
   * real number -- 82 plural `fill` sites across 34 files, on top of the 81 inline
   * `formatInteger` ones, where a gap note had said "seventeen call sites".
   *
   * **`fill` defaults its numbering to `latn`**, which is right for the many messages that
   * carry no figure and wrong for every plural one: a plural message renders its `count`, so
   * omitting the argument renders Latin digits whatever the tenant chose. The catalogue knows
   * which keys are plural, so the subject of this check is exact rather than a guess at which
   * values are numeric.
   */
  it("passes the tenant's numerals at every plural call site", () => {
    const offenders = fillSites()
      .filter((site) => typeof MESSAGES[DEFAULT_LOCALE][
        site.key as keyof typeof MESSAGES.en] === "object")
      .filter((site) => site.tail === "")
      .map((site) => `${site.where}: ${site.key} renders a count in Latin digits`);
    expect([...new Set(offenders)]).toEqual([]);
  });

  /**
   * And the figures that deliberately do *not* follow the setting, each declared.
   *
   * Three kinds, and the rule is the distinction between them:
   *
   * - **A quantity follows the tenant** -- something counted, measured or totalled.
   * - **An identifier does not** -- a version, a chain sequence number, an assurance level, a
   *   sort key: something a reader cites, quotes or types back. Shaping those would make
   *   somebody translate digits to read a reference.
   * - **Money does not either**, by the canvas's own exception: "Money keeps Latin digits with
   *   its code, because that is the form on your invoices and JoFotara submissions." That one
   *   is structural rather than declared -- `MoneyValue` carries no numbering prop at all
   *   (ADR-0015 D10) -- so what is left here is the one place money is rendered as an integer.
   *
   * The list is the uncomfortable half, as `GateCoverageTests.UNGATED` is: adding to it is a
   * claim that a figure is not a quantity, and the reason has to be in the code beside it.
   */
  it("declares every figure that deliberately keeps Latin digits", () => {
    const LATIN_BY_DESIGN = [
      // Versions: a reader cites "v3", and a tenant's own `cfg_values` version is a reference.
      "src/app/configuration/page.tsx",
      "src/app/access/page.tsx",
      "src/app/integrations/page.tsx",
      "src/app/notifications/page.tsx",
      // The audit chain's sequence number, which is the chain's own reference.
      "src/app/permissions/page.tsx",
      // Sort keys an operator types back: a merchandising rank and a price book's priority.
      "src/app/catalog/page.tsx",
      // An assurance level, which is cited the way a version is.
      "src/app/account/account-view.tsx",
      // Minor units of money rendered as an integer, which the canvas exempts outright.
      "src/app/access/[zoneId]/page.tsx",
    ];
    const offenders: string[] = [];
    const walk = (dir: string) => {
      for (const name of readdirSync(dir)) {
        const path = join(dir, name);
        if (statSync(path).isDirectory()) walk(path);
        else if (/\.tsx?$/.test(name)) {
          const text = readFileSync(path, "utf8");
          const n = [...text.matchAll(/formatInteger\([^()]*,\s*"latn"\s*\)/g)].length;
          if (n > 0 && !LATIN_BY_DESIGN.includes(path)) {
            offenders.push(`${path}: ${n} figure(s) hard-code Latin digits`);
          }
        }
      }
    };
    walk("src");
    expect(offenders).toEqual([]);
    // **Both directions**, so a declaration that stops being true fails too: a file that no
    // longer renders a Latin-by-design figure is a stale exemption, which is the shape this
    // repository's id sweep and `design:coverage` both check for.
    const stale = LATIN_BY_DESIGN.filter(
      (path) => !/formatInteger\([^()]*,\s*"latn"\s*\)/.test(readFileSync(path, "utf8")));
    expect(stale).toEqual([]);
  });
});
