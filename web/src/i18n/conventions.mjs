/**
 * Locale, direction, numerals, bidi isolation and money, mirroring `backend/app/l10n/conventions.py`.
 *
 * **This is a mirror, and the mirroring is the point.** The design system's Arabic rules say
 * numerals are "chosen once per tenant and applied identically on screen, receipt, export and
 * PDF. Never mixed within a tenant, and never decided per component." A receipt is rendered by
 * the backend and a screen by this code, so two implementations that drift are the same defect
 * MOD-018 refuses for balances -- one truth with two definitions that can disagree -- except
 * here the disagreement is a member reading a different amount on their screen than on the
 * receipt in their hand.
 *
 * `tests/unit/conventions-parity.test.mjs` therefore runs the Python and this file over one
 * vector set and compares the output character by character. Keeping the two in step is not a
 * convention to remember; it is a test that fails.
 *
 * **Bidi isolation is mandatory, not cosmetic.** The foundations: "Money, phone numbers,
 * member IDs, card last-four, times and Latin lift names are each wrapped in an isolated run.
 * Without it JOD jumps to the wrong side of its amount -- a money-ambiguity defect, not a
 * typographic one."
 *
 * Dependency-free so it runs under `node --test` and imports unchanged into the React layer.
 */

/** The two locales the product ships. Anything else fails closed. */
export const LOCALES = ["ar", "en"];

/** Bidi isolate controls, built from code points rather than written as literals.

 * Writing them as literal characters is how this file first failed: U+2028 is a JavaScript
 * line terminator, so a regex literal containing one does not parse. Constructing every
 * invisible control from its code point is immune to that and is readable besides -- a reader
 * can see *which* control is meant without trusting their editor to render it.
 */
export const LRI = String.fromCodePoint(0x2066);
export const RLI = String.fromCodePoint(0x2067);
export const FSI = String.fromCodePoint(0x2068);
export const PDI = String.fromCodePoint(0x2069);

const ISOLATE_OPENERS = { rtl: RLI, ltr: LRI, auto: FSI };

/**
 * Embedding, override and isolate controls, which are stripped from untrusted text.
 *
 * U+202A-202E are the legacy embeddings and overrides; U+2066-2069 are the isolates. A member
 * name carrying one of these could close an isolate this code opened and re-order the text
 * around it, which is how a name becomes a way to move an amount.
 */
const BIDI_CONTROLS = (() => {
  const points = [];
  for (let c = 0x202a; c <= 0x202e; c++) points.push(c);
  for (let c = 0x2066; c <= 0x2069; c++) points.push(c);
  return points.map((c) => String.fromCodePoint(c)).join("");
})();
const STRIP_BIDI = new RegExp(`[${BIDI_CONTROLS}]`, "gu");
const ARABIC_DIGIT_RE = new RegExp(
  `[${String.fromCodePoint(0x0660)}-${String.fromCodePoint(0x0669)}]`,
  "gu",
);

/**
 * Unicode Cc, Zl and Zp: rejected rather than stripped.
 *
 * The backend's comment says why, and it is worth repeating here because the two must agree:
 * these cover every bidi paragraph separator (LF, CR, U+001C-001E, U+0085, U+2028, U+2029),
 * each of which terminates *every* open isolate rather than just one.
 */
const REJECTED_CONTROL_RANGES = [
  [0x0000, 0x001f],
  [0x007f, 0x009f],
  [0x2028, 0x2029],
];
const REJECTED_CONTROL = new RegExp(
  "[" +
    REJECTED_CONTROL_RANGES.map(
      ([lo, hi]) => `${String.fromCodePoint(lo)}-${String.fromCodePoint(hi)}`,
    ).join("") +
    "]",
  "u",
);

/** Fail-closed bounds, matching the backend's. */
export const MAX_UNTRUSTED_TEXT_CHARS = 256;
export const MAX_SAFE_MINOR_UNITS = Number.MAX_SAFE_INTEGER;

/**
 * ISO 4217 minor-unit exponents -- how an amount is **stored**. A JOD amount is a count of
 * fils, which is a thousandth. A closed table: anything else fails closed.
 */
export const CURRENCY_MINOR_UNITS = { JOD: 3, USD: 2 };

/**
 * How many decimals an amount is **shown** with, which is a different question and is the
 * design system's to answer:
 *
 * > "Always three-letter code plus two decimals, tabular figures, end-aligned. JOD is three
 * > decimals in banking and two in retail -- Veyro is a retail product and shows two
 * > everywhere, including exports, so a reconciliation never has to guess which convention a
 * > column used."
 *
 * All 206 JOD figures drawn across the design folder use two decimals and none uses three.
 * Using the storage exponent for display was the defect: every money figure on every screen
 * in this product read `JOD 52.200` where the design reads `JOD 52.20`.
 *
 * **The two tables are separate on purpose.** Storage precision is what makes a proration
 * exact and a journal balance; display precision is what a receipt and a screen agree on.
 */
export const CURRENCY_DISPLAY_DIGITS = { JOD: 2, USD: 2 };

const ARABIC_DIGITS = Array.from({ length: 10 }, (_, i) =>
  String.fromCodePoint(0x0660 + i),
).join("");
const ARABIC_THOUSANDS = String.fromCodePoint(0x066c);
const ARABIC_DECIMAL = String.fromCodePoint(0x066b);

export class ConventionError extends Error {}

/** Reject an unknown locale rather than falling back to English. */
export function parseLocale(tag) {
  const value = typeof tag === "string" ? tag.trim().toLowerCase() : "";
  if (!LOCALES.includes(value)) throw new ConventionError("unsupported locale");
  return value;
}

/** Arabic is RTL, English LTR. Direction is derived from the locale and never sent by a caller. */
export function direction(locale) {
  return parseLocale(locale) === "ar" ? "rtl" : "ltr";
}

/**
 * Make untrusted text safe to place inside an isolate, or reject it.
 *
 * **The error never echoes the input.** The backend's contract says so and this matches it: an
 * error message that quoted the offending string would put attacker-controlled text into a log
 * and, in a browser, possibly into a toast.
 */
export function sanitizeUntrusted(text) {
  if (typeof text !== "string") throw new ConventionError("text must be a string");
  if ([...text].length > MAX_UNTRUSTED_TEXT_CHARS) throw new ConventionError("text too long");
  if (REJECTED_CONTROL.test(text)) throw new ConventionError("text contains a control character");
  return text.replace(STRIP_BIDI, "");
}

/** Sanitize, then wrap in RLI/LRI/FSI … PDI. */
export function isolate(text, bidiDir) {
  const opener = ISOLATE_OPENERS[bidiDir];
  if (opener === undefined) throw new ConventionError("unsupported isolate direction");
  return `${opener}${sanitizeUntrusted(text)}${PDI}`;
}

function checkNumbering(numbering) {
  if (numbering !== "latn" && numbering !== "arab") {
    throw new ConventionError("unsupported numbering system");
  }
}

/** ASCII digits to U+0660-0669 and back, for the explicitly requested system. */
export function shapeDigits(text, numbering) {
  checkNumbering(numbering);
  if (numbering === "arab") {
    return text.replace(/[0-9]/g, (d) => ARABIC_DIGITS[Number(d)]);
  }
  return text.replace(ARABIC_DIGIT_RE, (d) => String(d.codePointAt(0) - 0x0660));
}

function requireInt(value) {
  if (typeof value !== "number" || !Number.isInteger(value)) {
    throw new ConventionError("integer required");
  }
  if (Math.abs(value) > MAX_SAFE_MINOR_UNITS) throw new ConventionError("integer out of range");
  return value;
}

/**
 * An integer with optional thousands grouping. **Numbering is never derived from locale.**
 *
 * The Arabic rule is that numerals are a tenant setting, so an Arabic-locale tenant may still
 * use Latin numerals and a tenant must not get Arabic-Indic digits merely because a string was
 * Arabic. Deriving it here would make the choice per-component, which the rule forbids.
 */
export function formatInteger(value, numbering, grouping = true) {
  checkNumbering(numbering);
  const number = requireInt(value);
  const magnitude = Math.abs(number);
  let body = grouping
    ? String(magnitude).replace(/\B(?=(\d{3})+(?!\d))/g, ",")
    : String(magnitude);
  if (numbering === "arab") {
    body = shapeDigits(body, "arab").replaceAll(",", ARABIC_THOUSANDS);
  }
  return number < 0 ? `-${body}` : body;
}

/**
 * An ISO code and an amount built from integer minor units, LTR-isolated inside Arabic text.
 *
 * Minor units because every amount in this product is an integer count of them -- MOD-015's
 * rule, which the whole money stack holds. There is no float anywhere in this function.
 */
/**
 * The parts of a money value, for the renderings that style them differently.
 *
 * **`MoneyValue`'s `aggregate` kind needs this**: "fils de-emphasised, never truncated", drawn
 * as `JOD 41,280 .00` with the decimals at 14px against the major part's 21px. One formatted
 * string cannot be styled in two sizes, and a component that re-split it on the decimal
 * separator would be parsing its own output -- which breaks the moment the separator is the
 * Arabic one.
 *
 * Same rounding, same table, same everything as `formatMoney`; that function is written in
 * terms of this one so the two can never disagree.
 */
export function moneyParts(amountMinor, currency, numbering) {
  const exponent = CURRENCY_MINOR_UNITS[currency];
  const digits = CURRENCY_DISPLAY_DIGITS[currency];
  if (exponent === undefined || digits === undefined) {
    throw new ConventionError("unsupported currency");
  }
  if (digits > exponent) throw new ConventionError("display precision exceeds stored precision");
  checkNumbering(numbering);
  const minorTotal = requireInt(amountMinor);
  const dropped = exponent - digits;
  let magnitude = Math.abs(minorTotal);
  if (dropped) {
    const scale = 10 ** dropped;
    magnitude = Math.floor((magnitude + Math.floor(scale / 2)) / scale);
  }
  const scale = 10 ** digits;
  return {
    code: currency,
    sign: minorTotal < 0 ? "-" : "",
    major: formatInteger(Math.floor(magnitude / scale), numbering),
    /** Already padded, and the separator with it: "٫٠٠" in Arabic numerals, ".00" in Latin. */
    minor: digits
      ? (numbering === "arab" ? ARABIC_DECIMAL : ".")
        + shapeDigits(String(magnitude % scale).padStart(digits, "0"), numbering)
      : "",
  };
}

export function formatMoney(amountMinor, currency, numbering, locale) {
  const { code, sign, major, minor } = moneyParts(amountMinor, currency, numbering);
  const text = `${code} ${sign}${major}${minor}`;
  return parseLocale(locale) === "ar" ? isolate(text, "ltr") : text;
}

/**
 * The CLDR cardinal category for a count, which decides which form of a message to render.
 *
 * **Arabic has six and English has two**, and that asymmetry is the reason this exists rather
 * than an `n === 1` check at a call site. ADM-CC-01's heading counts the queue -- "Three
 * things need you this morning" -- and a page that picked the plural form for every count
 * would render "2 أمور" where Arabic wants its dual, and "1 payments are in recovery" in
 * English, which is what the rendered page showed before this was written.
 *
 * **It mirrors `backend/app/l10n/messages.py:plural_category` exactly**, and
 * `tests/unit/conventions-parity.test.mjs` runs both over the same counts and compares. Two
 * implementations that each assert their own expectations pass forever while drifting apart;
 * the only thing that catches drift is running them side by side -- which is the argument this
 * file already carries for money and numerals.
 */
export function pluralCategory(locale, count) {
  const loc = parseLocale(locale);
  if (!Number.isSafeInteger(count)) throw new ConventionError("count must be an integer");
  if (count < 0) throw new ConventionError("count must not be negative");
  if (loc === "ar") {
    if (count === 0) return "zero";
    if (count === 1) return "one";
    if (count === 2) return "two";
    const remainder = count % 100;
    if (remainder >= 3 && remainder <= 10) return "few";
    if (remainder >= 11 && remainder <= 99) return "many";
    return "other";
  }
  return count === 1 ? "one" : "other";
}
