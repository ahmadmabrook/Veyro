/**
 * The design system's published contrast table, recomputed from the hexes.
 *
 * `ds.json`'s CONTRAST rows each carry a token, its hex and three measured ratios -- on
 * bone.0, bone.100 and bone.150. Those numbers are a control only if something recomputes
 * them, which is this file: 12 rows x 3 surfaces = 36 assertions against values the design
 * system printed rather than against values this code chose.
 *
 * **Two things the retired system needed and this one does not.** It carried a documented
 * discrepancy -- a token whose printed trio was one hundredth above what its own hex
 * produced, pinned so nobody smoothed it over with a tolerance -- and a documented *failure*,
 * `color.text.tertiary` on the third surface at 4.48:1, which the foundations excluded from
 * the CI allow-list. Both are gone: every ratio here was computed from the shipped hex before
 * it was written down, and tertiary clears AA on all three surfaces. The tests below assert
 * those absences rather than assuming them, because an exclusion that lapses quietly is how a
 * palette loses a control nobody notices.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import {
  AA_SMALL,
  LARGE_TEXT_PX,
  MEASURED_SURFACES,
  passesAA,
  ratioAt2dp,
} from "../../src/design/contrast.mjs";

const ds = JSON.parse(
  readFileSync(fileURLToPath(new URL("../../src/design/ds.json", import.meta.url)), "utf8"),
);
const primitive = Object.fromEntries(ds.PRIMITIVES);
/** The dark ramp is declared separately, because a theme is a remapping of layer 2. */
const DARK_ONLY = Object.fromEntries(ds.DARK_RAMP.map(([name, hex]) => [name, hex]));

/** CONTRAST rows are [label, hex, onBone0, onBone100, onBone150, note]. */
const rows = ds.CONTRAST.map(([label, hex, ...rest]) => ({
  label,
  hex,
  measured: rest.slice(0, 3).map((r) => Number(String(r).replace(":1", ""))),
  note: rest[3],
}));

test("the design system publishes a ratio for every text token on three surfaces", () => {
  assert.equal(rows.length, 12);
  for (const row of rows) {
    assert.equal(row.measured.length, 3, row.label);
    for (const m of row.measured) assert.ok(Number.isFinite(m), `${row.label}: ${m}`);
  }
});

test("every published ratio recomputes from the hex it names, with no discrepancy", () => {
  for (const row of rows) {
    MEASURED_SURFACES.forEach((surface, i) => {
      const computed = ratioAt2dp(row.hex, primitive[surface]);
      assert.equal(
        computed,
        row.measured[i],
        `${row.label} on ${surface}: the table prints ${row.measured[i]}:1 and the hexes give ${computed}:1`,
      );
    });
  }
});

test("ink.400 is the only entry that fails AA for small text, on every surface", () => {
  const failures = [];
  for (const row of rows) {
    MEASURED_SURFACES.forEach((surface, i) => {
      if (row.measured[i] < AA_SMALL) failures.push(`${row.label} on ${surface}`);
    });
  }
  // `ink.400` is declared a failure on all three surfaces by the design system itself --
  // "FAIL under 18.66px on every surface. Disabled controls and decoration only." Nothing
  // else in the table fails anywhere, so there is no excluded pairing and no allow-list
  // carve-out. If a fourth entry appears here, a text token has been lightened.
  assert.deepEqual(failures, [
    "ink.400 on bone.0",
    "ink.400 on bone.100",
    "ink.400 on bone.150",
  ]);
});

test("tertiary passes small text on all three surfaces, including the darkest", () => {
  // The retired tertiary failed on the third surface by 0.02 and was excluded from CI. This
  // one is 4.92:1 there, so the exclusion does not exist and must not come back.
  for (const surface of MEASURED_SURFACES) {
    assert.equal(
      passesAA(primitive["ink.500"], primitive[surface], { sizePx: 14 }),
      true,
      `${surface}: ${ratioAt2dp(primitive["ink.500"], primitive[surface])}`,
    );
  }
  assert.equal(ratioAt2dp(primitive["ink.500"], primitive["bone.150"]), 4.92);
});

test("ink.400 is legal above the large-text size and refused below it", () => {
  const fg = primitive["ink.400"];
  const bg = primitive["bone.0"];
  assert.equal(ratioAt2dp(fg, bg), 3.34);
  assert.equal(passesAA(fg, bg, { sizePx: 14 }), false, "small text must be refused");
  assert.equal(passesAA(fg, bg, { sizePx: LARGE_TEXT_PX }), true, "large text is permitted");
});

test("the ramp below ink.400 is never text, so it has no measured row", () => {
  const labelled = rows.map((r) => r.label).join(" ");
  for (const name of ["bone.200", "bone.150", "bone.100"]) {
    assert.ok(!labelled.includes(name), `${name} must not appear as a text token`);
  }
});

test("the action colour shares a hue with no status colour, which guardrail G2 demands", () => {
  // **This asserts a hue distance now, and that is the finding rather than a stronger
  // restatement of the old one.** The retired palette put the shell field and the success
  // state on the same green, so a saturated action would have made "you may press this" and
  // "this succeeded" the same signal -- and the only way out was an action with no hue at
  // all, which is why it was ink and why this test could only compare *lightness*. The
  // primary is #91338A, which shares a hue with nothing in the palette, so the action is the
  // brand itself and the distance that keeps it safe is measurable directly.
  for (const [action, statuses] of [
    [primitive["plum.500"], ["turf.600", "gold.600", "crimson.500", "steel.600", "ai.600"]],
    [primitive["plum.400"], ["turf.600", "gold.600", "crimson.500", "steel.600", "ai.600"]],
  ]) {
    for (const status of statuses) {
      assert.notEqual(action, primitive[status], status);
      assert.ok(
        hueDistance(action, primitive[status]) >= 45,
        `the action and ${status} are ${hueDistance(action, primitive[status])} degrees apart`,
      );
    }
  }
});

test("the AI colour is system-owned and collides with nothing, in both themes", () => {
  // **Guardrail G7, asserted where it does not need a panel to render.** "A tenant brand on
  // an AI panel would make inference look like a first-party assertion; Veyro is accountable
  // for what its AI says, so Veyro owns the colour it says it in." This used to be a browser
  // test reading the AI region's computed border on the Command Center -- a region that is no
  // longer rendered there -- and its second half was vacuous besides, comparing against a
  // custom property nothing defined.
  for (const [theme, ai, action, statuses] of [
    ["light", primitive["ai.600"], primitive["plum.500"],
      ["turf.600", "gold.600", "crimson.500", "steel.600"].map((n) => primitive[n])],
    ["dark", DARK_ONLY["ai.light"], primitive["plum.400"],
      ["turf.light", "gold.light", "crimson.light", "steel.light"]
        .map((n) => primitive[n] ?? DARK_ONLY[n])],
  ]) {
    assert.notEqual(ai, action, `${theme}: AI must not be the action colour`);
    for (const status of statuses) {
      assert.notEqual(ai, status, `${theme}: AI must not be a status colour`);
    }
  }
});

test("white on a filled semantic reaches AA, which filled badges depend on", () => {
  for (const [name, expected] of [
    ["turf.600", 6.81],
    ["gold.600", 5.89],
    ["crimson.500", 7.48],
    ["steel.600", 5.74],
    ["ai.600", 7.93],
    // The action is a saturated fill in both themes now rather than ink and bone, so it
    // belongs in the list that proves a filled block can carry its label.
    ["plum.500", 6.9],
    ["plum.400", 4.91],
  ]) {
    assert.equal(ratioAt2dp("#ffffff", primitive[name]), expected, name);
    assert.equal(passesAA("#ffffff", primitive[name], { sizePx: 12 }), true, name);
  }
});

test("a category field carries ink, not white, and reaches AA doing it", () => {
  // gold.400 is a field colour rather than a text colour: white on it is 2.04:1 and would be
  // unreadable, so the money field carries ink.900 at 9.43:1. A field that flipped to white
  // text would be the one pairing in the system that looks deliberate and fails.
  assert.equal(ratioAt2dp(primitive["ink.900"], primitive["gold.400"]), 9.43);
  assert.ok(ratioAt2dp("#ffffff", primitive["gold.400"]) < AA_SMALL, "white on gold must fail");
});

test("warning is the tightest semantic and must not be lightened", () => {
  const onBone0 = ratioAt2dp(primitive["gold.600"], primitive["bone.0"]);
  assert.equal(onBone0, 5.89);
  assert.ok(onBone0 >= AA_SMALL);
});

test("passesAA refuses to answer without a size", () => {
  assert.throws(
    () => passesAA(primitive["ink.500"], primitive["bone.150"]),
    /needs the rendered size/,
  );
});

/**
 * **The selected surface is a translucent overlay, and nothing in the table covers it.**
 *
 * The published rows measure every text token on three *opaque* grounds in the light theme.
 * `color.surface.selected` is not one: in dark it is `rgba(159,212,184,.14)`, which is not a
 * colour at all until it is composited over whatever it sits on. So a text token on a
 * selected row is a pairing the table has nothing to say about -- and in the retired palette
 * that gap hid a real failure, `text.tertiary` at 3.74:1 on the dark selected row, which no
 * sighted reader on a light screen would ever see.
 *
 * This composites both themes' selected surface over their own default and checks the text
 * tokens against the result. The failure it was written for is gone in this palette, which is
 * the point of still running it: the absence is asserted rather than assumed.
 */

/**
 * The angular distance between two hues, in degrees.
 *
 * Local to this file on purpose: `contrast.mjs` answers what a reader can *see against* a
 * ground, and this answers whether two colours are the same family. They are different
 * questions and the guardrail that needs this one is G2.
 */
function hueDistance(a, b) {
  const h = (hex) => {
    const [r, g, b2] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
    const max = Math.max(r, g, b2), min = Math.min(r, g, b2), d = max - min;
    if (d === 0) return 0;
    const deg = max === r ? ((g - b2) / d) % 6
      : max === g ? (b2 - r) / d + 2
        : (r - g) / d + 4;
    return (deg * 60 + 360) % 360;
  };
  const gap = Math.abs(h(a) - h(b));
  return Math.round(Math.min(gap, 360 - gap));
}

/** `rgba(r,g,b,a)` over an opaque hex, as the browser composites it. */
function over([r, g, b], alpha, hex) {
  const base = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  return "#" + [r, g, b]
    .map((c, i) => Math.round(c * alpha + base[i] * (1 - alpha))
      .toString(16).padStart(2, "0")).join("");
}

// `color.surface.selected` dark is plum.300 at 14%, over `color.surface.default` dark,
// which is the owner's #26202C.
const DARK_SELECTED = over([214, 133, 208], 0.14, "#26202c");
const LIGHT_SELECTED = primitive["plum.100"];

test("the dark selected ground composites to the value these assertions assume", () => {
  // Pinned, because every ratio below is measured against it: if the overlay or the surface
  // under it moves, this fires before the ratios do and names the cause.
  assert.equal(DARK_SELECTED, "#3f2e43");
});

test("every text token on a selected row reaches AA in both themes", () => {
  for (const [theme, ground, tokens] of [
    ["dark", DARK_SELECTED, { primary: "#faf7fa", secondary: "#dfd3e3", tertiary: "#c3afca" }],
    ["light", LIGHT_SELECTED, { primary: "#110d11", secondary: "#544554", tertiary: "#6d5b6d" }],
  ]) {
    for (const [role, hex] of Object.entries(tokens)) {
      assert.ok(
        passesAA(hex, ground, { sizePx: 11 }),
        `${theme} ${role} on the selected row is ${ratioAt2dp(hex, ground)}`,
      );
    }
  }
});

/**
 * **The shell field is a saturated ground, and the published table does not cover it either.**
 *
 * The three measured surfaces are the light theme's neutrals. The rail and the chrome are
 * `plum.800` in light and `aubergine.950` in dark, and every token that lands on them -- the
 * item text, the group heading, the count, the current item and its ground -- is a pairing
 * nothing in CONTRAST measures.
 *
 * It caught a real failure the hour the field shipped. The current item first took
 * `color.text.inverse`, which is bone in light and near-black in dark, so on the selected
 * ground it inverted to **1.94:1** in the dark theme -- invisible, and invisible in exactly the
 * way a light-screen reader never sees. `color.brand.field.selected.text` exists because of
 * it, and these assertions are what stop it coming back.
 */
test("every token that lands on the shell field reaches AA in both themes", () => {
  for (const [theme, field, selected, tokens] of [
    ["light", "plum.800", "plum.600", {
      text: "bone.50", muted: "plum.300", mark: "gold.400", selectedText: "bone.0",
    }],
    ["dark", "aubergine.950", "aubergine.700", {
      text: "mauve.200", muted: "mauve.300", mark: "gold.light", selectedText: "bone.50",
    }],
  ]) {
    for (const [role, name] of Object.entries(tokens)) {
      const ground = role === "selectedText" ? selected : field;
      const ratio = ratioAt2dp(primitive[name] ?? DARK_ONLY[name], primitive[ground] ?? DARK_ONLY[ground]);
      assert.ok(
        ratio >= AA_SMALL,
        `${theme} ${role} (${name}) on ${ground} is ${ratio}:1`,
      );
    }
  }
});

test("the selected item's text is declared per theme, not borrowed from text.inverse", () => {
  // **The hazard is demonstrated differently now, and the reason is worth reading.** This
  // used to prove itself through `color.text.inverse`, which was bone in light and a
  // near-black in dark: putting that second value on the dark selected ground gave 1.94:1,
  // so "the opposite of the text colour" was visibly the wrong token for a ground that is
  // dark in both themes. The action fill is a plum in both themes now, so `text.inverse` is
  // bone in both and that demonstration cannot run -- which is a changed *consequence*, not
  // a closed finding. The finding is that a dark-in-both-themes ground needs its own
  // declared pair, and the hazard is still right there in the dark ramp: its own darkest
  // member on its own selected ground is 1.42:1.
  assert.ok(
    ratioAt2dp(DARK_ONLY["aubergine.950"], DARK_ONLY["aubergine.700"]) < AA_SMALL,
    "the failure this token exists to prevent must still be a failure",
  );
  const declared = ds.SEMANTIC.find(([name]) => name === "color.brand.field.selected.text");
  assert.ok(declared, "the token must be declared");
  assert.deepEqual(declared.slice(1, 3), ["bone.0", "bone.50"]);
  // And both halves of the declared pair clear AA on the ground they are declared for,
  // which is the property the pair exists to hold.
  assert.ok(ratioAt2dp(primitive["bone.0"], primitive["plum.600"]) >= AA_SMALL);
  assert.ok(ratioAt2dp(primitive["bone.50"], DARK_ONLY["aubergine.700"]) >= AA_SMALL);
});

test("tertiary on the selected row is no longer the documented failure it was", () => {
  // The retired palette read 3.74:1 here and the app carried a rule -- "small text on
  // color.surface.selected uses text.secondary" -- to work around it. This palette clears AA
  // with tertiary in both themes, so the rule is not needed. Asserted rather than deleted:
  // the day somebody lightens the overlay or the mauve ramp, this is what notices.
  assert.ok(ratioAt2dp("#c3afca", DARK_SELECTED) >= AA_SMALL);
  assert.ok(ratioAt2dp("#6d5b6d", LIGHT_SELECTED) >= AA_SMALL);
});
