/**
 * The generated token artefacts, and the layer discipline the foundations insist on.
 *
 * The generator has a `--check` mode; this runs it, so a hand-edited `tokens.generated.css`
 * fails here as well as in CI. Proven to bite: appending a comment to the CSS makes
 * `--check` report STALE.
 */

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import {
  PRIMITIVES,
  RADIUS,
  SEMANTIC,
  SPACE,
  SPACE_SCALE,
} from "../../src/design/tokens.generated.mjs";

const design = (name) => fileURLToPath(new URL(`../../src/design/${name}`, import.meta.url));
const css = readFileSync(design("tokens.generated.css"), "utf8");
const ds = JSON.parse(readFileSync(design("ds.json"), "utf8"));

test("the generated artefacts are in sync with ds.json", () => {
  const r = spawnSync(process.execPath, [design("generate.mjs"), "--check"], {
    encoding: "utf8",
  });
  assert.equal(r.status, 0, `generator reports the artefacts are stale:\n${r.stderr}${r.stdout}`);
});

test("every semantic token the design system declares reaches the CSS", () => {
  for (const [token] of ds.SEMANTIC) {
    const name = "--" + token.replace(/\./g, "-");
    // `color.surface.raised` is "warm.0 + e1" -- a primitive plus an elevation -- and the
    // generator reports it as needing a composite rule rather than inventing a hex. Every
    // other token must be present.
    if (token === "color.surface.raised") continue;
    assert.ok(css.includes(`${name}:`), `missing from the CSS: ${name}`);
  }
});

test("dark is a remapping of the same token names, not a second set", () => {
  // "Light and dark are two mappings of one token set -- never an inversion, and never a
  // second set of names." So every name the dark block defines must also exist in light.
  // **Each block is bounded by its own braces.** Slicing to end-of-file read the type
  // `:root` that follows the dark block as part of it, and the test reported a remapping
  // failure that was really its own parsing. A test that mis-reads the artefact is worse
  // than no test, because the failure points at the wrong file.
  const darkNames = declarationsIn(css, '[data-theme="dark"]');
  const lightNames = new Set(blocksFor(css, ":root").flat());
  assert.ok(darkNames.length >= 20, `expected a full dark mapping, found ${darkNames.length}`);
  for (const name of darkNames) {
    assert.ok(lightNames.has(name), `${name} exists only in dark, which makes it a second set`);
  }
});

test("the dark block remaps no primitive, because a theme is a layer-2 remapping", () => {
  const redefined = declarationsIn(css, '[data-theme="dark"]').filter((n) =>
    n.startsWith("--p-"),
  );
  assert.deepEqual(redefined, [], "dark must not rewrite layer 1");
});

test("the spacing scale is exactly the eleven values the DS ships, in order", () => {
  // Read from the ordered array rather than from the map: a JavaScript object sorts
  // integer-like keys numerically, so `space.05` comes last out of `Object.values` and the
  // scale reads 4,8,...,64,2. The generator exports both for that reason.
  assert.deepEqual(SPACE_SCALE.map(([, px]) => px), [2, 4, 8, 12, 16, 20, 24, 32, 40, 48, 64]);
  assert.deepEqual(SPACE_SCALE.map(([name]) => name),
                   ["05", "1", "2", "3", "4", "5", "6", "8", "10", "12", "16"]);
  // "No value outside this scale ships. space.05 is the single exception" -- it exists for a
  // hairline nudge, which is why 2 is in the scale at all.
  assert.equal(SPACE["05"], 2);
  for (const px of SPACE_SCALE.map(([, px]) => px)) {
    assert.ok(px === 2 || px % 4 === 0, `${px} is off the 4px rhythm`);
  }
});

test("a pressable radius is larger than a card radius, which is the DS's own inversion", () => {
  // "radius.button is larger than radius.card, which looks wrong in a list and is right on
  // screen." Containers and data stay sharp; anything pressable gets an affordance cue.
  assert.ok(parseInt(RADIUS.button, 10) > parseInt(RADIUS.card, 10));
  assert.ok(parseInt(RADIUS.card, 10) <= 2, "data must stay sharp");
});

test("the primitive ramps are the twenty-two the design system publishes", () => {
  // The *light* ramp is the one the source publishes as a ramp, and it is exactly 22. The
  // generated `PRIMITIVES` map also carries the dark ramp, which the source states inline in
  // the dark column rather than collecting anywhere -- so this counts the two separately. The
  // first version counted the map and therefore conflated them, which would have let a dark
  // entry quietly take a light one's place.
  assert.equal(ds.PRIMITIVES.length, 22);
  assert.equal(PRIMITIVES["ink.600"], "#1b4079");
  assert.equal(PRIMITIVES["ai.600"], "#4a3d7a");
  assert.equal(Object.keys(PRIMITIVES).length, ds.PRIMITIVES.length + ds.DARK_RAMP.length);
  for (const hex of Object.values(PRIMITIVES)) {
    assert.match(hex, /^#[0-9a-f]{6}$/, hex);
  }
});

test("the AI hue is not brand-configurable, and the guardrails still say so", () => {
  // G7 locks ai.600 because the AI panel's border carries "this is interpretation, not
  // confirmed fact" -- under a tenant accent, machine inference would read as a first-party
  // assertion. The token must exist and the guardrail must still be present in the data.
  assert.ok(SEMANTIC["color.semantic.ai"], "the AI token must exist");
  const guardrails = ds.GUARDRAILS.map((g) => g.join(" ")).join("\n");
  assert.match(guardrails, /focus ring is system-owned/, "G4 must still be declared");
  assert.equal(ds.GUARDRAILS.length, 7);
});

test("every semantic token carries the use the design system wrote for it", () => {
  // A token with no stated use is one a component will apply by guesswork.
  for (const [name, entry] of Object.entries(SEMANTIC)) {
    assert.ok(entry.use && entry.use.length > 8, `${name} has no stated use`);
    assert.equal(entry.css, `var(--${name.replace(/\./g, "-")})`);
  }
});

/** The custom-property names declared inside the first block whose selector contains `sel`. */
function declarationsIn(source, sel) {
  const start = source.indexOf(sel);
  assert.notEqual(start, -1, `no block with selector containing ${sel}`);
  const open = source.indexOf("{", start);
  const close = source.indexOf("\n}", open);
  assert.ok(open !== -1 && close !== -1, `unbalanced block for ${sel}`);
  const body = source.slice(open + 1, close);
  return [...body.matchAll(/^\s*(--[a-z0-9-]+):/gm)].map((m) => m[1]);
}

/** Every block whose selector is exactly `sel`, as lists of declared names. */
function blocksFor(source, sel) {
  const out = [];
  const re = new RegExp(`^${sel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")} \\{$`, "gm");
  for (const m of source.matchAll(re)) {
    const open = source.indexOf("{", m.index);
    const close = source.indexOf("\n}", open);
    const body = source.slice(open + 1, close);
    out.push([...body.matchAll(/^\s*(--[a-z0-9-]+):/gm)].map((x) => x[1]));
  }
  assert.ok(out.length >= 1, `no block for ${sel}`);
  return out;
}
