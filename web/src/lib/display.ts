import type { Locale, Numbering } from "@/i18n/locale";
import { api } from "@/lib/api";

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
