/**
 * The type scale, and the nine Arabic rules that change it.
 *
 * **Arabic is not Latin with a different font.** The foundations state nine rules, and five of
 * them alter a resolved token rather than its rendering: the line-height gains 0.15, the size
 * has a 13px floor, the weight steps up, tracking is dropped, and mono has no Arabic. A
 * component that applied the Latin token to Arabic text would not look slightly wrong -- it
 * would be unreadable at `type.caption` and broken at the joins wherever tracking applied.
 *
 * So resolution is a function of the token *and* the script, and there is no way to ask for a
 * token without saying which. `resolve(name)` does not exist on purpose.
 *
 * Dependency-free: runs under `node --test`, imports unchanged into the React layer.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const ds = JSON.parse(
  readFileSync(fileURLToPath(new URL("./ds.json", import.meta.url)), "utf8"),
);

/** The two scripts the product sets type in. */
export const SCRIPTS = ["latin", "arabic"];

/**
 * Arabic never renders below this, in px.
 *
 * "A caption that cannot be read is not a caption." `type.caption` is 11 and `type.eyebrow`
 * is 10, so both are raised -- which is also why they are declared Latin-only.
 */
export const ARABIC_SIZE_FLOOR = 13;

/** Arabic gains this much line-height at every size. */
export const ARABIC_LINE_HEIGHT_BONUS = 0.15;

/**
 * The tokens the foundations declare Latin-only.
 *
 * `type.caption` is Latin-only because its 11px is under the floor; `type.eyebrow` because it
 * carries 0.09em of tracking *and* sits under the floor, and "any token carrying a track value
 * drops it in Arabic, which is why type.eyebrow has no Arabic form and uses type.label
 * instead."
 */
export const LATIN_ONLY = { "type.caption": null, "type.eyebrow": "type.label" };

/** Mono has no Arabic: "IBM Plex Mono has no Arabic." */
export const FAMILIES = {
  latin: { sans: "'IBM Plex Sans'", mono: "'IBM Plex Mono'" },
  arabic: { sans: "'IBM Plex Sans Arabic'", mono: "'IBM Plex Sans Arabic'" },
};

/** The tokens set in mono. `type.data` is the tabular column that makes money align. */
export const MONO_TOKENS = new Set(["type.data", "type.eyebrow"]);

export class TypeError_ extends Error {}

/** `'34 / 1.10'` to `{ sizePx: 34, lineHeight: 1.1 }`. */
function parseSize(spec) {
  const m = /^\s*([\d.]+)\s*\/\s*([\d.]+)\s*$/.exec(spec);
  if (!m) throw new TypeError_(`unreadable size spec: ${spec}`);
  return { sizePx: Number(m[1]), lineHeight: Number(m[2]) };
}

/** The Latin scale exactly as the design system publishes it. */
export const LATIN_SCALE = Object.fromEntries(
  ds.TYPE_SCALE.map(([name, size, weight, tracking, use]) => {
    const { sizePx, lineHeight } = parseSize(size);
    return [name, { name, sizePx, lineHeight, weight: Number(weight), tracking, use }];
  }),
);

/** Every token name, in the design system's own order. */
export const TOKEN_NAMES = ds.TYPE_SCALE.map(([name]) => name);

/**
 * Arabic steps the weight up where Latin emphasises.
 *
 * "Where Latin uses 400, Arabic uses 400; where Latin uses 450 or 500, Arabic uses 500; where
 * Latin uses 500 for emphasis, Arabic uses 600." The scale's own weights are 400 and 500, and
 * every 500 in it is an emphasis weight -- a heading, a label, a mono value -- so 500 becomes
 * 600 and 400 stays.
 */
export function arabicWeight(latinWeight) {
  if (latinWeight <= 400) return latinWeight;
  if (latinWeight === 450) return 500;
  return 600;
}

/**
 * Resolve a type token for a script. **The script is required.**
 *
 * Returns the substituted token name when the foundations redirect one, so a caller can see
 * that it asked for `type.eyebrow` in Arabic and got `type.label` -- rather than silently
 * receiving different values under the name it asked for.
 */
export function resolveType(name, script) {
  if (!SCRIPTS.includes(script)) {
    throw new TypeError_(`unsupported script: ${script}. Arabic and Latin resolve differently`);
  }
  const latin = LATIN_SCALE[name];
  if (!latin) throw new TypeError_(`unknown type token: ${name}`);
  if (script === "latin") {
    return {
      ...latin,
      resolvedFrom: name,
      family: MONO_TOKENS.has(name) ? FAMILIES.latin.mono : FAMILIES.latin.sans,
    };
  }
  // Arabic. A redirected token resolves through its substitute, so the substitute's own rules
  // apply rather than this token's.
  if (name in LATIN_ONLY) {
    const substitute = LATIN_ONLY[name];
    if (substitute) return { ...resolveType(substitute, "arabic"), resolvedFrom: name };
  }
  const base = LATIN_SCALE[name];
  return {
    name,
    resolvedFrom: name,
    sizePx: Math.max(ARABIC_SIZE_FLOOR, base.sizePx),
    lineHeight: Math.round((base.lineHeight + ARABIC_LINE_HEIGHT_BONUS) * 100) / 100,
    weight: arabicWeight(base.weight),
    // "Never apply tracking to Arabic -- it breaks the joins."
    tracking: "0",
    // "Mono is Latin-only ... a mono column in an Arabic table switches family but keeps its
    // alignment and width", which is why the family changes and `fontVariantNumeric` does not.
    family: FAMILIES.arabic.sans,
    tabular: MONO_TOKENS.has(name),
    use: base.use,
  };
}

/** The nine Arabic rules, as data, so a test can assert each one is implemented. */
export const ARABIC_RULES = ds.ARABIC_RULES.map(([rule, why]) => ({ rule, why }));

/** The four density modes. Front Desk and Kiosk are never user-selectable. */
export const DENSITY = ds.DENSITY.map(([name, rowHeight, typeStep, baseSize, target, use]) => ({
  name,
  rowHeight,
  typeStep,
  baseSizePx: Number(String(baseSize).replace("px", "")),
  minTargetPx: Number(String(target).replace("px", "")),
  use,
}));

/** The five breakpoints, with the behaviour each one changes. */
export const BREAKPOINTS = ds.BREAKPOINTS.map(([name, range, behaviour]) => ({
  name,
  range,
  behaviour,
}));
