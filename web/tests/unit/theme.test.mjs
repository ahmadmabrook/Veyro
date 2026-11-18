/**
 * The dark theme is a remapping of every semantic token, or it is not a theme.
 *
 * This file exists because the generator used to skip a dark declaration it could not resolve
 * and say nothing. Seven of twenty-nine tokens had no dark value and silently kept their light
 * one, so in dark mode form fields were near-white on a near-black page, the primary button
 * stayed ink.600 against it, and the focus ring -- which guardrail G4 makes non-configurable so
 * that "a tenant cannot ship an unnavigable product" -- was dark navy on near-black. The CSS was
 * valid, the tokens test passed, and the only way to find it was to look at a dark render.
 *
 * The tests below are the structural answer, and they are deliberately *sweeps* rather than
 * lists of the tokens that went wrong: a per-token list has to be edited whenever a token is
 * added, and that edit is the moment an unmapped one slips through.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const read = (name) =>
  readFileSync(fileURLToPath(new URL(`../../src/design/${name}`, import.meta.url)), "utf8");

const ds = JSON.parse(read("ds.json"));
const css = read("tokens.generated.css");

/** The text inside a `{ ... }` block whose selector contains `selector`. */
function blockFor(selector) {
  const at = css.indexOf(selector);
  assert.ok(at >= 0, `no block for ${selector}`);
  const open = css.indexOf("{", at);
  const close = css.indexOf("\n}", open);
  assert.ok(close > open, `unterminated block for ${selector}`);
  return css.slice(open + 1, close);
}

/** The custom-property names *declared* in a block, ignoring commented-out ones. */
function declarationsIn(block) {
  return new Set(
    block
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => !line.startsWith("/*"))
      .map((line) => /^(--[a-z0-9-]+)\s*:/.exec(line)?.[1])
      .filter(Boolean),
  );
}

const cssName = (token) => "--" + token.replace(/\./g, "-");
const semanticTokens = ds.SEMANTIC.map(([token]) => token);
const gapTokens = new Set((ds.DARK_GAPS ?? []).map(([token]) => token));

const lightBlock = blockFor(":root {");
const darkBlock = blockFor(':root[data-theme="dark"]');
const light = declarationsIn(lightBlock);
const dark = declarationsIn(darkBlock);

test("every semantic token is declared in the light block", () => {
  const missing = semanticTokens.filter((token) => !light.has(cssName(token)));
  assert.deepEqual(missing, [], `light block is missing ${missing.join(", ")}`);
});

test("every semantic token is remapped in the dark block, or declared a source gap", () => {
  const missing = semanticTokens.filter(
    (token) => !dark.has(cssName(token)) && !gapTokens.has(token),
  );
  assert.deepEqual(
    missing,
    [],
    `dark block is missing ${missing.join(", ")} -- those tokens would silently keep their ` +
      `light value, which is how form fields rendered white on black`,
  );
});

test("the dark block declares nothing the light block does not", () => {
  // A dark-only name is a second set of names, which the foundations forbid outright: "dark is
  // a remapping of the same token names -- never an inversion, and never a second set".
  const extra = [...dark].filter((name) => !light.has(name));
  assert.deepEqual(extra, [], `dark-only token(s): ${extra.join(", ")}`);
});

test("a declared dark gap names the unresolved reference and says why", () => {
  for (const [token, ref, why] of ds.DARK_GAPS ?? []) {
    const row = ds.SEMANTIC.find(([name]) => name === token);
    assert.ok(row, `DARK_GAPS names ${token}, which is not a semantic token`);
    assert.equal(
      String(row[2]).trim(),
      ref,
      `${token}'s dark value is ${row[2]}, but the gap claims ${ref} -- a stale exemption is ` +
        `worse than none, because it exempts whatever the value becomes`,
    );
    assert.ok(why.length > 80, `${token}'s gap needs a written reason, not a label`);
  }
});

test("every dark ramp entry cites where the pinned source states it", () => {
  // The source never collects the dark ramp into a ramp of its own: it states each value inline
  // in the dark column. Hoisting them is reading the source; the citation is what says so, and
  // an entry without one would be a value somebody chose.
  for (const [name, hex, source] of ds.DARK_RAMP ?? []) {
    assert.match(hex, /^#[0-9a-f]{6}$/, `${name} is not a flat hex`);
    assert.ok(
      source && source.length > 10,
      `${name} must cite the row of the design source it was quoted from`,
    );
  }
});

test("every dark ramp primitive is actually referenced by a semantic token", () => {
  // An unused primitive is a colour nobody decided to use, sitting in layer 1 where the next
  // component will reach for it. Layer 1 exists "so semantic tokens have somewhere to point".
  const referenced = new Set(
    ds.SEMANTIC.flatMap(([, lightRef, darkRef]) =>
      [lightRef, darkRef].map((ref) => String(ref).trim().split(/\s+/)[0]),
    ),
  );
  const unused = (ds.DARK_RAMP ?? []).map(([name]) => name).filter((name) => !referenced.has(name));
  assert.deepEqual(unused, [], `dark ramp entries nothing points at: ${unused.join(", ")}`);
});

test("the focus ring has a value in both themes", () => {
  // Guardrail G4 makes the focus ring system-owned and non-configurable. A ring that resolves
  // to the light accent on a dark field is one a keyboard user cannot see, which is the exact
  // outcome G4 exists to prevent -- so it gets its own named test rather than relying on the
  // sweep above to keep covering it.
  assert.ok(light.has("--color-border-focus"), "no light focus ring");
  assert.ok(dark.has("--color-border-focus"), "no dark focus ring");
  assert.notEqual(
    /--color-border-focus:\s*([^;]+);/.exec(lightBlock)?.[1]?.trim(),
    /--color-border-focus:\s*([^;]+);/.exec(darkBlock)?.[1]?.trim(),
    "the focus ring is the same value in both themes, so one of them is wrong",
  );
});
