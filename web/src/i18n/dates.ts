import { shapeDigits } from "./conventions.mjs";
import type { Locale, Numbering } from "./locale";

/**
 * A calendar date's day and month, in the reader's language and the tenant's numerals.
 *
 * **Why this exists at all.** ADM-SET-07's preview is `تنتهي عضويتك في ٢١ آب`, and nothing in
 * this build could render it: `time.ts` reads *instants* -- a session in its site's zone, a
 * device report in UTC -- and formats them as ISO, which is the right answer for a log line
 * and the wrong one for a sentence a member reads. `formatInteger` and `formatMoney` carry the
 * numeral half and neither knows a month name.
 *
 * **The month names come from the region, not from the language**, which is the whole reason
 * the tag is `ar-JO` rather than `ar`: Jordan uses the Levantine set, so August is `آب`, while
 * plain `ar` resolves to the Egyptian-influenced `أغسطس`. The canvas states it as a
 * consequence rather than a control -- "Month names follow the Levantine set — آب, تموز —
 * because that is what Jordanian members read" -- in the same way CON-04 derives the week
 * start from the region. ADR-0015 D5.
 *
 * **`REGION` is a constant because this build provisions one region, and that is a limitation
 * rather than a fact.** CON-04 makes the region the irreversible choice a tenant is created
 * with -- "Jordan sets data residency, JOD as the currency, the JoFotara tax adapter, Arabic as
 * an available language, and a Sunday week start" -- and nothing in `plt01` records it, so
 * there is nothing to read. The day a second region is provisioned this takes the region as an
 * argument and `availability.week_from`'s own Sunday constant moves with it.
 *
 * **The numbering is forced to `latn` in the tag and shaped afterwards.** `ar-JO` resolves to
 * the `arab` numbering system *by default*, so a tag alone would make the digits follow the
 * language -- precisely what `formatInteger`'s own contract forbids: "numerals are a tenant
 * setting, so an Arabic-locale tenant may still use Latin numerals and a tenant must not get
 * Arabic-Indic digits merely because a string was Arabic". The tag decides the month name and
 * `shapeDigits` decides the digits, through the same function every other figure goes through.
 *
 * **And within this build's two locales that forcing is redundant, which a mutation found
 * rather than a reader.** `shapeDigits` is bidirectional -- its `latn` branch converts
 * U+0660-0669 back to ASCII -- so removing `-u-nu-latn` produces the identical string and the
 * sweep reported it uncaught, correctly. It is kept because it is what a *third* locale would
 * need: `shapeDigits` knows two digit sets and ICU knows many, so Persian's `arabext`
 * (U+06F0-06F9) would survive the normalisation and reach a `latn` tenant's page. Forcing the
 * tag means the formatter never emits a digit `shapeDigits` cannot handle, rather than relying
 * on it to undo one. No case can exist until a third locale does, so there is no mutation for
 * it and the premise it rests on is asserted instead.
 *
 * **It takes a calendar date rather than an instant, and so has no zone to state.** A day and
 * a month in a sentence is a date somebody was told, not a moment -- `ends_on` is a `date`
 * column for the same reason. `timeZone: "UTC"` is therefore about parsing rather than about
 * display: `new Date("2026-08-21")` is UTC midnight, and formatting it in the runtime's own
 * zone renders the 20th anywhere west of Greenwich. Three defects in this repository have come
 * from that frame.
 *
 * **There is no backend twin, and that is a gap rather than an omission.** `locale.ts` says in
 * its own header that it adds no formatting of its own, "because a second implementation is
 * the thing the parity test exists to prevent" -- and this is formatting, so it deliberately
 * does not live there. It cannot be in `conventions.mjs` either, because that module is
 * compared character for character against `backend/app/l10n/conventions.py` and Python's
 * standard library has no CLDR month names: a twin needs `babel`, which would be this
 * repository's second dependency ever. Nothing in the backend renders a month name today. The
 * day a receipt or a notification does -- the canvas's own rule is "applied identically on
 * screen, receipt and export" -- that twin and the dependency are the work, and this module
 * moves into the parity pair.
 */
const REGION: Record<Locale, string> = { ar: "ar-JO", en: "en-GB" };

export class DateFormatError extends Error {}

/** A `YYYY-MM-DD` calendar date as `21 آب` / `21 August`, with the tenant's digits. */
export function monthDay(date: string, locale: Locale, numbering: Numbering): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) throw new DateFormatError("calendar date required");
  const at = new Date(`${date}T00:00:00Z`);
  if (Number.isNaN(at.getTime())) throw new DateFormatError("calendar date required");
  const latin = new Intl.DateTimeFormat(`${REGION[locale]}-u-nu-latn`, {
    day: "numeric",
    month: "long",
    timeZone: "UTC",
  }).format(at);
  return shapeDigits(latin, numbering) as string;
}
