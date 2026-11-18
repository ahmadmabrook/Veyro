/**
 * The type scale, and one test per Arabic rule that changes a resolved token.
 *
 * The foundations state nine Arabic rules. Five of them are implementable in token
 * resolution and each has a test below; the other four are container, review and italics
 * rules that a component or a review has to honour, and the last test asserts that all nine
 * are still *present* so none can quietly disappear from the data this module reads.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  ARABIC_LINE_HEIGHT_BONUS,
  ARABIC_RULES,
  ARABIC_SIZE_FLOOR,
  BREAKPOINTS,
  DENSITY,
  LATIN_SCALE,
  TOKEN_NAMES,
  arabicWeight,
  resolveType,
} from "../../src/design/type.mjs";

test("the Latin scale is the twelve tokens the design system publishes", () => {
  assert.equal(TOKEN_NAMES.length, 12);
  assert.deepEqual(TOKEN_NAMES.slice(0, 3), ["type.display", "type.h1", "type.h2"]);
  assert.equal(LATIN_SCALE["type.body"].sizePx, 14);
  assert.equal(LATIN_SCALE["type.body"].lineHeight, 1.6);
  assert.equal(LATIN_SCALE["type.data"].sizePx, 13);
  assert.equal(LATIN_SCALE["type.display"].sizePx, 34);
});

test("resolution refuses to answer without a script", () => {
  assert.throws(() => resolveType("type.body", undefined), /unsupported script/);
  assert.throws(() => resolveType("type.body", "hebrew"), /unsupported script/);
});

test("an unknown token is refused rather than defaulted", () => {
  assert.throws(() => resolveType("type.enormous", "latin"), /unknown type token/);
});

// --- rule 1: line height +0.15 ------------------------------------------------------------

test("Arabic gains 0.15 line-height at every size", () => {
  for (const name of TOKEN_NAMES) {
    const latin = resolveType(name, "latin");
    const arabic = resolveType(name, "arabic");
    if (arabic.resolvedFrom !== arabic.name) continue; // redirected tokens follow their substitute
    assert.equal(
      arabic.lineHeight,
      Math.round((latin.lineHeight + ARABIC_LINE_HEIGHT_BONUS) * 100) / 100,
      name,
    );
  }
  // The foundations' own worked example: body is 1.60 Latin and 1.75 Arabic.
  assert.equal(resolveType("type.body", "latin").lineHeight, 1.6);
  assert.equal(resolveType("type.body", "arabic").lineHeight, 1.75);
});

// --- rule 2: size floor 13px --------------------------------------------------------------

test("no Arabic token renders below the 13px floor", () => {
  for (const name of TOKEN_NAMES) {
    assert.ok(
      resolveType(name, "arabic").sizePx >= ARABIC_SIZE_FLOOR,
      `${name} resolves below the Arabic floor`,
    );
  }
});

test("the two tokens under the floor are Latin-only and are handled, not shrunk", () => {
  // type.caption is 11 and has no Arabic substitute: it resolves up to the floor.
  assert.equal(LATIN_SCALE["type.caption"].sizePx, 11);
  assert.equal(resolveType("type.caption", "arabic").sizePx, 13);
  // type.eyebrow is 10 *and* tracked, so the foundations redirect it to type.label entirely.
  assert.equal(LATIN_SCALE["type.eyebrow"].sizePx, 10);
  const eyebrow = resolveType("type.eyebrow", "arabic");
  assert.equal(eyebrow.name, "type.label", "eyebrow has no Arabic form; it uses type.label");
  assert.equal(eyebrow.resolvedFrom, "type.eyebrow", "the caller can see the substitution");
  assert.equal(eyebrow.sizePx, 13);
});

// --- rule 3: weight up one step -----------------------------------------------------------

test("Arabic steps emphasis weights up and leaves 400 alone", () => {
  assert.equal(arabicWeight(400), 400);
  assert.equal(arabicWeight(450), 500);
  assert.equal(arabicWeight(500), 600);
  // Plex Sans Arabic reads optically lighter at the same weight, so a 500 heading would look
  // lighter than its Latin counterpart rather than equal to it.
  assert.equal(resolveType("type.h1", "latin").weight, 500);
  assert.equal(resolveType("type.h1", "arabic").weight, 600);
  assert.equal(resolveType("type.body", "latin").weight, 400);
  assert.equal(resolveType("type.body", "arabic").weight, 400);
});

// --- rule 4: zero letter-spacing ----------------------------------------------------------

test("no Arabic token carries tracking, because tracking breaks the joins", () => {
  for (const name of TOKEN_NAMES) {
    assert.equal(resolveType(name, "arabic").tracking, "0", name);
  }
  // Several Latin tokens genuinely do carry it, so the rule is removing something real.
  const tracked = TOKEN_NAMES.filter((n) => {
    const t = resolveType(n, "latin").tracking;
    return t !== "0" && t !== 0;
  });
  assert.ok(tracked.length >= 5, `expected tracked Latin tokens, found ${tracked.length}`);
});

// --- rule 7: mono is Latin-only -----------------------------------------------------------

test("a mono token switches family in Arabic but keeps its tabular alignment", () => {
  const latin = resolveType("type.data", "latin");
  const arabic = resolveType("type.data", "arabic");
  assert.match(latin.family, /Plex Mono/);
  assert.match(arabic.family, /Plex Sans Arabic/);
  assert.equal(arabic.tabular, true, "the column must still align: tabular figures");
});

test("a non-mono token uses the sans family in both scripts", () => {
  assert.match(resolveType("type.body", "latin").family, /Plex Sans'/);
  assert.match(resolveType("type.body", "arabic").family, /Plex Sans Arabic/);
});

// --- the rules that components and reviews have to carry ----------------------------------

test("all nine Arabic rules are present in the data this module reads", () => {
  assert.equal(ARABIC_RULES.length, 9);
  const headings = ARABIC_RULES.map((r) => r.rule);
  for (const expected of [
    "Line height +0.15",
    "Size floor 13px",
    "Weight up one step",
    "Zero letter-spacing",
    "No italics",
    "Containers sized for Arabic",
    "Mono is Latin-only",
    "Numerals are a tenant setting",
    "Bidi isolation is mandatory",
  ]) {
    assert.ok(headings.includes(expected), `missing Arabic rule: ${expected}`);
  }
});

test("the four rules this module cannot enforce are the ones a component must", () => {
  // Stated as a test so the division is explicit rather than assumed: italics, container
  // width, the tenant numeral setting and bidi isolation are enforced elsewhere -- the first
  // two by components and review, the last two by `src/i18n/conventions.mjs`, which has its
  // own parity suite against the backend.
  const enforcedHere = ["Line height +0.15", "Size floor 13px", "Weight up one step",
                        "Zero letter-spacing", "Mono is Latin-only"];
  const elsewhere = ARABIC_RULES.map((r) => r.rule).filter((r) => !enforcedHere.includes(r));
  assert.deepEqual(elsewhere, [
    "No italics",
    "Containers sized for Arabic",
    "Numerals are a tenant setting",
    "Bidi isolation is mandatory",
  ]);
});

// --- density and breakpoints --------------------------------------------------------------

test("the four density modes carry a minimum target size", () => {
  assert.equal(DENSITY.length, 4);
  assert.deepEqual(DENSITY.map((d) => d.name), ["Compact", "Default", "Touch", "Spacious"]);
  // Touch and Spacious are the hand-operated ones and both reach 44px, which is the floor a
  // tap target needs. Compact is a mouse-and-keyboard grid at 32.
  assert.equal(DENSITY.find((d) => d.name === "Touch").minTargetPx, 44);
  assert.equal(DENSITY.find((d) => d.name === "Spacious").minTargetPx, 44);
  assert.equal(DENSITY.find((d) => d.name === "Compact").minTargetPx, 32);
});

test("Front Desk and Kiosk density is not user-selectable, and the data says so", () => {
  const touch = DENSITY.find((d) => d.name === "Touch");
  assert.match(touch.use, /Never user-selectable on Front Desk or Kiosk/);
});

test("the five breakpoints are present with their behaviours", () => {
  assert.equal(BREAKPOINTS.length, 5);
  assert.deepEqual(BREAKPOINTS.map((b) => b.name), ["bp.xs", "bp.sm", "bp.md", "bp.lg", "bp.xl"]);
  // The xs rule is a real product constraint, not a layout preference: "Tables become
  // drill-down lists, never shrunken grids."
  assert.match(BREAKPOINTS[0].behaviour, /never shrunken grids/);
});
