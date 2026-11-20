/**
 * The design system's published contrast table, recomputed from the hexes.
 *
 * `ds.json`'s CONTRAST rows each carry a token, its hex and three measured ratios -- on
 * warm.0, warm.100 and warm.150. Those numbers are a control only if something recomputes
 * them, which is this file: 9 rows x 3 surfaces = 27 assertions against values the design
 * system printed rather than against values this code chose.
 *
 * It also pins the one documented failure. `color.text.tertiary` on `warm.150` is 4.48:1,
 * under AA by 0.02, and the foundations say that pairing "is excluded from the CI allow-list".
 * A test that let it quietly become 4.5 would be a test that let the exclusion lapse.
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

/** CONTRAST rows are [label, hex, onWarm0, onWarm100, onWarm150, note]. */
const rows = ds.CONTRAST.map(([label, hex, ...rest]) => ({
  label,
  hex,
  measured: rest.slice(0, 3).map((r) => Number(String(r).replace(":1", ""))),
  note: rest[3],
}));

test("the design system publishes a ratio for every text token on three surfaces", () => {
  assert.equal(rows.length, 9);
  for (const row of rows) {
    assert.equal(row.measured.length, 3, row.label);
    for (const m of row.measured) assert.ok(Number.isFinite(m), `${row.label}: ${m}`);
  }
});

/**
 * **The one row where the design system's table and its own hex disagree.**
 *
 * Eight of the nine tokens recompute to the printed hundredth. `color.semantic.ai` does not:
 * `#4a3d7a` gives 9.30 / 8.39 / 7.74 and the table prints 9.31 / 8.40 / 7.75 -- high by
 * exactly 0.01 on all three surfaces, which is systematic rather than rounding noise. A
 * search over the indigo neighbourhood finds no hex that produces the printed trio *and*
 * equals `#4a3d7a`; the printed values correspond to a slightly darker colour, so the table
 * was computed from a shade that is not the one shipped.
 *
 * It is a documentation discrepancy and not an accessibility defect: 9.30, 8.39 and 7.74 all
 * clear AAA for small text, so every claim the foundations make about this token still holds.
 * It is pinned here rather than smoothed over with a tolerance, because a blanket tolerance
 * would also hide a future change that mattered. If somebody corrects either the hex or the
 * table, this fires and a human reads the diff.
 */
const DOCUMENTED_DISCREPANCY = {
  "color.semantic.ai · ai.600": { printed: [9.31, 8.4, 7.75], computed: [9.3, 8.39, 7.74] },
};

test("every published ratio recomputes from the hex it names", () => {
  for (const row of rows) {
    const known = DOCUMENTED_DISCREPANCY[row.label];
    MEASURED_SURFACES.forEach((surface, i) => {
      const computed = ratioAt2dp(row.hex, primitive[surface]);
      const expected = known ? known.computed[i] : row.measured[i];
      assert.equal(
        computed,
        expected,
        `${row.label} on ${surface}: expected ${expected}:1 from the hexes, got ${computed}:1`,
      );
    });
  }
});

test("the ai.600 discrepancy is still exactly one hundredth and still passes AAA", () => {
  const row = rows.find((r) => r.label in DOCUMENTED_DISCREPANCY);
  assert.ok(row, "the ai token must still be in the table");
  const known = DOCUMENTED_DISCREPANCY[row.label];
  assert.deepEqual(row.measured, known.printed, "the printed table changed");
  MEASURED_SURFACES.forEach((surface, i) => {
    const computed = ratioAt2dp(row.hex, primitive[surface]);
    assert.equal(computed, known.computed[i], surface);
    assert.equal(
      Math.round((known.printed[i] - computed) * 100) / 100,
      0.01,
      `${surface}: the gap is no longer one hundredth`,
    );
    // The point of recording it rather than fixing it: nothing about the token's claims moves.
    assert.ok(computed >= 7, `${surface}: ai.600 must still clear AAA for small text`);
  });
});

test("the one excluded pairing is still the only one that fails AA for small text", () => {
  const failures = [];
  for (const row of rows) {
    MEASURED_SURFACES.forEach((surface, i) => {
      if (row.measured[i] < AA_SMALL) failures.push(`${row.label} on ${surface}`);
    });
  }
  // `warm.500` is declared a failure on all three surfaces by the DS itself -- "FAIL under
  // 18.66px on every surface. Large text, disabled controls and decoration only." The
  // tertiary-on-warm.150 row is the fourth, and it is the one the CI allow-list excludes.
  assert.deepEqual(failures, [
    "color.text.tertiary · warm.600 on warm.150",
    "warm.500 on warm.0",
    "warm.500 on warm.100",
    "warm.500 on warm.150",
  ]);
});

test("text.tertiary on warm.150 is legal above the large-text size and not below it", () => {
  const fg = primitive["warm.600"];
  const bg = primitive["warm.150"];
  assert.equal(ratioAt2dp(fg, bg), 4.48);
  assert.equal(passesAA(fg, bg, { sizePx: 14 }), false, "small text must be refused");
  assert.equal(passesAA(fg, bg, { sizePx: LARGE_TEXT_PX }), true, "large text is permitted");
});

test("text.tertiary passes small text on the two surfaces the DS allows it on", () => {
  for (const surface of ["warm.0", "warm.100"]) {
    assert.equal(
      passesAA(primitive["warm.600"], primitive[surface], { sizePx: 14 }),
      true,
      surface,
    );
  }
});

test("warm.400 and lighter are never text, so they are not in the table at all", () => {
  // "warm.400 and lighter are never text." The table stops at warm.500, which is itself
  // large-text-only -- so a token below it has no measured row to pass.
  const labelled = rows.map((r) => r.label).join(" ");
  for (const name of ["warm.400", "warm.300", "warm.200"]) {
    assert.ok(!labelled.includes(name), `${name} must not appear as a text token`);
  }
});

test("action and success are separated by hue, which the DS rejected sharing", () => {
  // "Action and success sharing a green was an accessibility defect, not a stylistic choice."
  // The check is that the two are not near-identical, not that they are any particular hue.
  const action = primitive["ink.600"];
  const success = primitive["success.600"];
  assert.notEqual(action, success);
  const distance = Math.abs(ratioAt2dp(action, "#ffffff") - ratioAt2dp(success, "#ffffff"));
  assert.ok(distance > 1, `action and success are too close in lightness: ${distance}`);
});

test("white on a filled semantic reaches AA, which filled badges depend on", () => {
  // The DS prints these as white-on-fill: success 7.64, warning 5.89, error 7.70, ai 9.38.
  for (const [name, expected] of [
    ["success.600", 7.64],
    ["warning.600", 5.89],
    ["error.600", 7.7],
    ["ai.600", 9.38],
    ["ink.600", 10.21],
  ]) {
    assert.equal(ratioAt2dp("#ffffff", primitive[name]), expected, name);
    assert.equal(passesAA("#ffffff", primitive[name], { sizePx: 12 }), true, name);
  }
});

test("warning is the tightest semantic and must not be lightened", () => {
  // "Pass. The tightest semantic -- do not lighten." A regression here is a real a11y loss,
  // so the floor is asserted rather than left as prose.
  const onWarm0 = ratioAt2dp(primitive["warning.600"], primitive["warm.0"]);
  assert.equal(onWarm0, 5.84);
  assert.ok(onWarm0 >= AA_SMALL);
});

test("passesAA refuses to answer without a size", () => {
  assert.throws(
    () => passesAA(primitive["warm.600"], primitive["warm.150"]),
    /needs the rendered size/,
  );
});

/**
 * **The selected surface is a translucent overlay, and nothing in the table covers it.**
 *
 * The design's contrast rows measure every text token on `warm.0`, `warm.100` and
 * `warm.150` -- three opaque grounds in the light theme. `color.surface.selected` is
 * neither: in light it is `ink.50`, and in dark it is `rgba(126,166,232,.16)`, which is not
 * a colour at all until it is composited over whatever it sits on. So a text token on a
 * selected row is a pairing the published table has nothing to say about, and the member
 * queue's sub-line found that out the hard way: `text.tertiary` reads 3.74:1 on the dark
 * selected row, under AA, and a sighted reader on a light screen never sees it.
 *
 * This composites both themes' selected surface over their own default and checks every
 * text token against the result, which is the half the table cannot carry because the
 * answer depends on what the overlay is over.
 */

/** `rgba(r,g,b,a)` over an opaque hex, as the browser composites it. */
function over([r, g, b], alpha, hex) {
  const base = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  return "#" + [r, g, b]
    .map((c, i) => Math.round(c * alpha + base[i] * (1 - alpha))
      .toString(16).padStart(2, "0")).join("");
}

const DARK_SELECTED = over([126, 166, 232], 0.16, "#211f1c");
const LIGHT_SELECTED = "#e8edf6";

test("small text on a selected row reaches AA in both themes", () => {
  // Secondary, not tertiary: tertiary is the contrast floor on an *opaque* surface, and the
  // selected overlay lifts the ground enough to take it under AA in the dark theme. The
  // rule the app follows is "small text on color.surface.selected uses text.secondary", and
  // this is what makes it a rule rather than a habit.
  for (const [theme, ground, secondary] of [
    ["dark", DARK_SELECTED, "#b8b3aa"],
    ["light", LIGHT_SELECTED, "#57544d"],
  ]) {
    assert.ok(
      passesAA(secondary, ground, { sizePx: 11 }),
      `${theme}: secondary on the selected row is ${ratioAt2dp(secondary, ground)}`,
    );
  }
});

test("tertiary on the dark selected row is under AA, which is why the rule exists", () => {
  // **The documented failure, pinned like the DS's own one.** A change that made this pass
  // would mean the palette moved, and the rule above would quietly stop being necessary --
  // which is a thing somebody should notice rather than discover.
  assert.ok(
    !passesAA("#928d84", DARK_SELECTED, { sizePx: 11 }),
    `tertiary on the dark selected row is ${ratioAt2dp("#928d84", DARK_SELECTED)}`,
  );
});
