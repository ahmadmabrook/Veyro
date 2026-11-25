import { cache } from "react";

import type { Locale, Numbering } from "@/i18n/locale";
import { api, gate } from "@/lib/api";

/**
 * ADM-SET-07's display conventions, and the three decisions a screen makes from them.
 *
 * **The read is its own route with its own routine permission** -- ADR-0015 D1. The three
 * cheaper ways in are all closed: `/config/resolved` costs `config.definition.read`, which
 * means "see every configuration key" and is MOD-013's `GET /notifications/channels` finding
 * if it is granted so a page can choose its digits; `/auth/session` cannot answer, because
 * `veyro_iam_app` holds nothing in `plt01`; and `presentation()` is cookie-only, which is why
 * every page can call it.
 *
 * **`declared` is the field that makes the screen honest.** A tenant that has configured
 * nothing resolves to Latin digits and every language this build has catalogues for -- which
 * is exactly what every page renders today -- so a surface reading only the values could not
 * tell a default from a decision, and would present one as the other. MOD-005's own
 * configuration board had to learn the same thing about `scope_type: "default"`.
 */

export type DisplayConventions = {
  /** `latn` or `arab`. One rule per tenant: the canvas forbids deciding it per component. */
  numerals: Numbering;
  /** A subset of the catalogues this build has. Never empty: see `declared`. */
  languages_offered: string[];
  /** `levantine`. Derived from the region rather than configured -- ADR-0015 D5. */
  month_names: string;
  /**
   * The numeral system money always uses, whatever `numerals` says. A rule, not a setting.
   *
   * **A token rather than a sentence**, so the catalogue words the rule in the reader's own
   * language and `formatMoney`'s callers have a value to pass. ADR-0015 D6.
   */
  money_numerals: Numbering;
  /** The keys this tenant has actually published. Empty means every value above is a default. */
  declared: string[];
};

export const NUMERALS_KEY = "localization.numerals";
export const LANGUAGES_KEY = "localization.languages_offered";

export function readDisplayConventions(): Promise<DisplayConventions> {
  return api<DisplayConventions>("/config/display");
}

/** What every page falls back to: exactly what this build rendered before the setting existed. */
export const FALLBACK: DisplayConventions = {
  numerals: "latn",
  languages_offered: ["en", "ar"],
  month_names: "levantine",
  money_numerals: "latn",
  declared: [],
};

/**
 * The tenant's conventions for a page that renders figures -- one read per request.
 *
 * **ADR-0015 D7.** `presentation()` keeps its contract -- cookie-only, no request, callable
 * from the sign-in page -- and this is the separate reader. `cache` is React's per-request
 * memo, so the layout warms it and every component that asks shares one call: the honest cost
 * is one extra request per page render, which is the same order as the gate batch the layout
 * already makes.
 *
 * **Not a cookie, which is D8 and the canvas's own sentence.** One written at sign-in would be
 * request-free and would make "one rule per tenant, never mixed" false across readers for up to
 * a session's lifetime: two staff looking at the same screen would see different digits until
 * the older session expired. Nothing here invalidates a cookie across sessions.
 *
 * **Any failure is the fallback and the page says nothing** -- D2. A refused read, an
 * unreachable API and a tenant that has declared nothing all render what this build rendered
 * before the setting existed, so a missing grant changes what somebody sees rather than
 * whether a page works.
 *
 * **It asks the gate before it reads, and the first version did not** -- D9, corrected. The
 * argument for reading straight through was that `check` writes a denial to MOD-008's chain
 * itself, so a gate call would write the row a bare 403 writes anyway. That is false:
 * `/authz/check` passes `record_denial=False`, which the gating suite's own `UNGATED` note
 * says in as many words -- "it records no denial" -- because a page asking what it may draw is
 * not an access attempt. A `permit` is. So the ungated read wrote one `iam.audit_events` row
 * **per page view** for any reader whose tenant has not granted the permission, in a table with
 * no DELETE grant: navigation-driven growth, and the browser suite found it by rendering the
 * audit log and finding 25 screens of `config.display.read denied` where `role.assigned` had
 * been. Gating first costs a request and writes nothing.
 */
export const mayReadDisplay = cache(() => gate("config.display.read"));

export const conventions = cache(async (): Promise<DisplayConventions> => {
  if (!(await mayReadDisplay()).allowed) return FALLBACK;
  try {
    return await readDisplayConventions();
  } catch {
    return FALLBACK;
  }
});

/**
 * The numeral system a page's figures follow.
 *
 * The thing nearly every call site wants, so it does not have to remember that money is the
 * exception -- `MoneyValue` carries no `numbering` prop at all (D10) and the direct
 * `formatMoney` calls that remain pass the literal, which a sweep enforces.
 */
export async function numerals(): Promise<Numbering> {
  return (await conventions()).numerals;
}

/**
 * Whether a convention is a decision somebody made or the value a page falls back to.
 *
 * Rendering the value alone would make the two the same, which is the defect the configuration
 * board records for `scope_type: "default"`: "nobody set it" is a different fact from a tenant
 * that published the same value on purpose, and only one of them is something to change.
 */
export function isDefaulted(conventions: DisplayConventions, key: string): boolean {
  return !conventions.declared.includes(key);
}

/**
 * The language the preview renders in.
 *
 * **Arabic where Arabic is offered, whatever the reader's own language is.** The preview's
 * subject is the thing a reader has to *look* at to check -- whether `٢١ آب` is the form their
 * members read -- and that is a property of the Arabic surface. An English-locale owner
 * checking their tenant's Arabic rendering is the ordinary case; rendering the sample in
 * English for them would show them a sentence whose digits are the only thing that changes and
 * whose month name is the fact they cannot verify.
 *
 * **And a tenant that does not offer Arabic gets the sample in a language it offers**, because
 * a preview of a surface nobody will see demonstrates nothing. That state is not drawn on the
 * canvas -- its tenant offers both -- so it is a derivation rather than a rendering.
 */
export function previewLocale(conventions: DisplayConventions): Locale {
  return conventions.languages_offered.includes("ar") ? "ar" : "en";
}

/**
 * The sample date the preview renders, as a calendar date rather than an instant.
 *
 * **The canvas's own 21 August**, kept rather than derived from today's date for two reasons:
 * a preview whose figures move is a preview a reader cannot compare against the approved
 * drawing, and a month whose Levantine and standard Arabic names happen to coincide would
 * demonstrate nothing -- August is the sharpest of the twelve (`آب` against `أغسطس`), which is
 * why the canvas chose it.
 */
export const PREVIEW_DATE = "2026-08-21";

/** The canvas's own `JOD 55.00`, in minor units: MOD-015's rule, three for JOD. */
export const PREVIEW_AMOUNT_MINOR = 55_000;
export const PREVIEW_CURRENCY = "JOD";
