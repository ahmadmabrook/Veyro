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

test("the Latin scale is the thirteen tokens the design system publishes", () => {
  assert.equal(TOKEN_NAMES.length, 13);
  // The figure registers lead the scale, because the signature move is the numeral: a
  // quantity is the largest thing on the page, not a label above a heading.
  assert.deepEqual(TOKEN_NAMES.slice(0, 3), ["type.figure", "type.figureSm", "type.display"]);
  assert.equal(LATIN_SCALE["type.body"].sizePx, 16);
  assert.equal(LATIN_SCALE["type.body"].lineHeight, 1.45);
  assert.equal(LATIN_SCALE["type.data"].sizePx, 15);
  assert.equal(LATIN_SCALE["type.figure"].sizePx, 88);
  // **The scale runs 6.8x from the smallest token to the largest**, which is where the
  // hierarchy comes from in a flat world with no ornament to spend. A scale that ran 3x
  // would need something else to tell a figure from a footnote.
  const sizes = TOKEN_NAMES.map((n) => LATIN_SCALE[n].sizePx);
  assert.ok(Math.max(...sizes) / Math.min(...sizes) >= 6, "the scale has lost its range");
  // There is no eyebrow register. It was a 10px tracked token whose only use was the kicker
  // the craft floor bans, and which Arabic could never set because tracking breaks the joins.
  assert.ok(!TOKEN_NAMES.includes("type.eyebrow"));
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
  assert.equal(resolveType("type.body", "latin").lineHeight, 1.45);
  assert.equal(resolveType("type.body", "arabic").lineHeight, 1.6);
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

test("no Latin token sits under the floor the system sets for Arabic", () => {
  // **This used to assert that one did, and raising the scale is why it does not.**
  // `type.caption` was 11.5 and `type.label` 12, both under the 13px minimum this system
  // enforces for Arabic -- so the same screen set Latin under a bar it had set for itself,
  // and the test pinned the mechanism that rescued the Arabic half. The finding was never
  // "a token is under the floor"; it was that a floor applies to both scripts or it is not
  // a floor. Both are 13 now and the rescue has nothing to rescue.
  const under = TOKEN_NAMES.filter((n) => LATIN_SCALE[n].sizePx < ARABIC_SIZE_FLOOR);
  assert.deepEqual(under, [], `these set Latin below the Arabic floor: ${under.join(", ")}`);
  // The raise still works, and is still what would happen: asserted on the token that was
  // rescued, which now needs no rescuing and must therefore keep its own size.
  assert.equal(resolveType("type.label", "arabic").sizePx, 13);
  assert.equal(resolveType("type.label", "arabic").name, "type.label");
});

// --- rule 3: weight up one step -----------------------------------------------------------

test("Arabic steps emphasis weights up and leaves 400 alone", () => {
  assert.equal(arabicWeight(400), 400);
  assert.equal(arabicWeight(500), 600);
  assert.equal(arabicWeight(600), 600);
  // 700 does not step further: it is the top of the ramp, and 800 is a weight neither face
  // ships, so asking for it would ask for a font that does not arrive.
  assert.equal(arabicWeight(700), 700);
  // Cairo reads optically lighter at the same weight, so a 600 heading would look lighter
  // than its Latin counterpart rather than equal to it.
  assert.equal(resolveType("type.h2", "latin").weight, 600);
  assert.equal(resolveType("type.h2", "arabic").weight, 600);
  assert.equal(resolveType("type.h1", "latin").weight, 700);
  assert.equal(resolveType("type.h1", "arabic").weight, 700);
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

// --- rule 7: figures are Archivo, Arabic text is Cairo ------------------------------------

test("a figure token switches family in Arabic but keeps its tabular alignment", () => {
  const latin = resolveType("type.data", "latin");
  const arabic = resolveType("type.data", "arabic");
  assert.match(latin.family, /Archivo/);
  assert.match(arabic.family, /Cairo/);
  assert.equal(arabic.tabular, true, "the column must still align: tabular figures");
  // The monumental numeral is the same face as the table column, which is what makes the
  // signature move and the data grid read as one system rather than two.
  assert.match(resolveType("type.figure", "latin").family, /Archivo/);
  assert.equal(resolveType("type.figure", "latin").tabular, true);
});

test("a text token uses the text family in both scripts, and never the figure face", () => {
  assert.match(resolveType("type.body", "latin").family, /Barlow/);
  assert.match(resolveType("type.body", "arabic").family, /Cairo/);
  assert.equal(resolveType("type.body", "latin").tabular, false);
  // No token resolves to a monospace family: there is no mono role in this system.
  for (const name of TOKEN_NAMES) {
    for (const script of ["latin", "arabic"]) {
      assert.doesNotMatch(resolveType(name, script).family, /Mono|mono/, `${name} ${script}`);
    }
  }
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
    "Figures are Archivo, Arabic text is Cairo",
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
                        "Zero letter-spacing", "Figures are Archivo, Arabic text is Cairo"];
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
  // Touch and Spacious are the hand-operated ones and both clear 44px, which is the floor a
  // tap target needs. **The floor is asserted rather than the value**: the targets rose with
  // the type scale, and a test pinning 44 exactly would fail the next time they are
  // generous rather than the next time they are too small.
  for (const name of ["Touch", "Spacious"]) {
    assert.ok(DENSITY.find((d) => d.name === name).minTargetPx >= 44, name);
  }
  // Compact is a mouse-and-keyboard grid and is the one mode allowed under the tap floor.
  assert.ok(DENSITY.find((d) => d.name === "Compact").minTargetPx >= 32);
  assert.ok(DENSITY.find((d) => d.name === "Compact").minTargetPx < 44);
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
