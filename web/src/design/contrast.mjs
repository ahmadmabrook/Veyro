/**
 * WCAG 2.1 relative luminance and contrast, and the design system's own allow-list.
 *
 * **This exists to check the design system rather than to decorate it.** `ds.json`'s CONTRAST
 * table publishes a measured ratio for every text token on three surfaces, and one of those
 * rows records a *failure*: `color.text.tertiary` on `warm.150` is 4.48:1, which is under 4.5
 * by 0.02, so that pairing is large-text-only and the foundations say in as many words that it
 * "is excluded from the CI allow-list". A table of ratios nothing recomputes is a claim; the
 * tests beside this file recompute all 27 of them from the hexes.
 *
 * The foundations also say why the numbers are printed with their basis: "7.64 (error.600 as
 * text on warm.0) and 7.70 (white on error.600) are different measurements, and an unlabelled
 * ratio is not a control." So `ratio` takes a foreground and a background in that order and
 * never guesses which way round a pairing was measured.
 *
 * Dependency-free on purpose: it runs under `node --test` with nothing installed.
 */

/** WCAG's small-text threshold. 4.5:1 for anything below the large-text size. */
export const AA_SMALL = 4.5;
/** WCAG's large-text threshold, which the DS reaches at 18.66px or 14px bold. */
export const AA_LARGE = 3;
/** AAA for small text, which `color.text.primary` meets on all three surfaces. */
export const AAA_SMALL = 7;

/**
 * The size at or above which WCAG's large-text thresholds apply, in px.
 *
 * The foundations quote 18.66px twice -- "warm.600 is the lightest neutral permitted for text
 * below 18.66px" and "warm.500 FAIL under 18.66px" -- which is 14pt at 96dpi. It is spelled
 * out here because the Arabic rules raise some sizes and a reader has to be able to see which
 * threshold a resolved token lands under.
 */
export const LARGE_TEXT_PX = 18.66;

/** `#rrggbb` to a `[r, g, b]` triple of 0-255 integers. */
export function parseHex(hex) {
  const m = /^#([0-9a-fA-F]{6})$/.exec(String(hex).trim());
  if (!m) throw new Error(`not a six-digit hex colour: ${hex}`);
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff];
}

/** WCAG 2.1 relative luminance. */
export function luminance(hex) {
  const channel = (v) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  const [r, g, b] = parseHex(hex).map(channel);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/**
 * The contrast ratio of a foreground against a background, 1:1 to 21:1.
 *
 * Symmetric by construction -- WCAG's formula is -- which is exactly why the *label* matters:
 * white-on-error.600 and error.600-on-warm.0 are two different pairings that happen to sit
 * close together, and the DS prints both so neither can be mistaken for the other.
 */
export function ratio(foreground, background) {
  const a = luminance(foreground);
  const b = luminance(background);
  const [hi, lo] = a > b ? [a, b] : [b, a];
  return (hi + 0.05) / (lo + 0.05);
}

/** Rounded to two decimals, which is how the foundations print every ratio. */
export function ratioAt2dp(foreground, background) {
  return Math.round(ratio(foreground, background) * 100) / 100;
}

/**
 * Whether a pairing passes AA at a given rendered size.
 *
 * **Size is a required argument.** The one pairing the DS excludes fails by 0.02 and is legal
 * above 18.66px, so a helper that answered without knowing the size would have to either
 * forbid a legal use or permit an illegal one.
 */
export function passesAA(foreground, background, { sizePx, bold = false } = {}) {
  if (typeof sizePx !== "number" || !Number.isFinite(sizePx)) {
    throw new Error("passesAA needs the rendered size in px: a threshold depends on it");
  }
  const large = sizePx >= LARGE_TEXT_PX || (bold && sizePx >= 14);
  return ratio(foreground, background) >= (large ? AA_LARGE : AA_SMALL);
}

/**
 * The three surfaces the DS measures every text token against, in its own column order.
 *
 * `warm.150` is third and is the one that catches `color.text.tertiary`. The foundations found
 * that pairing with this matrix "rather than the ramp being trusted", which is the whole
 * argument for keeping the surfaces as data.
 */
export const MEASURED_SURFACES = ["bone.0", "bone.100", "bone.150"];
