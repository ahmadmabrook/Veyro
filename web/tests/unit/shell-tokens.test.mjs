import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

/**
 * The shell, the density modes and the breakpoints, checked against the design source.
 *
 * **This is the layer that was missing.** `ds.json` carried `LAYOUTS`, `DENSITY` and
 * `BREAKPOINTS` from the day it was extracted and nothing emitted them, so the Admin shell
 * specification — a 12-column grid, a 240px rail collapsing to 56, content capped at 1440, an
 * inspector of 380 widening to 480 — sat in the repository unimplemented while fifteen screens
 * shipped a horizontal strip over a 960px column.
 *
 * Every assertion here parses the number out of the design source's own sentence rather than
 * comparing against a number written in this file. The Foundations document gives the reason:
 * "four precision slips in this project were all caused by a number being copied rather than
 * referenced."
 */

const read = (name) => readFileSync(fileURLToPath(new URL(name, import.meta.url)), "utf8");
const contracts = JSON.parse(read("../../src/design/contracts.json"));
const css = read("../../src/design/tokens.generated.css");
const globals = read("../../src/app/globals.css");

/** Every `.tsx` under `src/`, which is every file that can name a class. */
function tsxFiles(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) out.push(...tsxFiles(path));
    else if (entry.endsWith(".tsx")) out.push(path);
  }
  return out;
}

const token = (name) => {
  const found = css.match(new RegExp(`--${name}:\\s*([^;]+);`));
  assert.ok(found, `${name} is not emitted`);
  return found[1].trim();
};

const admin = contracts.layouts.find((l) => l.surface === "Veyro Admin").specification;
const fromAdmin = (re) => {
  const found = admin.match(re);
  assert.ok(found, `the Admin layout no longer states ${re}`);
  return found[1];
};

test("the Admin shell tokens are the design source's own numbers", () => {
  assert.equal(token("shell-columns"), fromAdmin(/(\d+)-column/));
  assert.equal(token("shell-gutter"), `${fromAdmin(/(\d+)px gutter/)}px`);
  assert.equal(token("shell-rail"), `${fromAdmin(/Rail (\d+) expanded/)}px`);
  assert.equal(token("shell-rail-collapsed"), `${fromAdmin(/expanded \/ (\d+) collapsed/)}px`);
  assert.equal(token("shell-content-max"), `${fromAdmin(/Content max (\d+)/)}px`);
  assert.equal(token("shell-inspector"), `${fromAdmin(/Inspector (\d+) at bp\.lg/)}px`);
  assert.equal(token("shell-inspector-wide"), `${fromAdmin(/bp\.lg, (\d+) at bp\.xl/)}px`);
});

test("the shell is two panes and there is no third track", () => {
  // "Split view is list + inspector, never three columns." A third track in the stylesheet
  // would be the first step to a screen that has one.
  assert.match(admin, /never three columns/);
  const rules = globals.match(/\.ds-shell\[data-has-inspector="true"\] \.ds-shell-content \{[^}]*\}/g);
  assert.ok(rules, "the inspector layout rule is missing");
  for (const rule of rules) {
    const columns = rule.match(/grid-template-columns:\s*([^;]+);/);
    if (!columns) continue;
    const tracks = columns[1].split(")").filter((p) => p.includes("(") || p.includes("var"));
    assert.ok(tracks.length <= 2, `three or more tracks in: ${columns[1]}`);
  }
});

test("each density mode emits the row, control and step the source states", () => {
  for (const mode of contracts.density) {
    const [row, control] = mode.row_and_control.split("/").map((s) => parseInt(s.trim(), 10));
    // The selector is an attribute one rather than `:root`, so a screen can set a density on
    // its own wrapper -- which ADM-MEM-05 does, and which `:root[...]` silently did not do.
    const selector =
      mode.mode === "Default"
        ? ':root, \\[data-density="default"\\]'
        : `\\[data-density="${mode.mode.toLowerCase()}"\\]`;
    const block = css.match(new RegExp(`${selector} \\{([^}]*)\\}`));
    assert.ok(block, `${mode.mode} emits no density block`);
    assert.match(block[1], new RegExp(`--density-row:\\s*${row}px;`), mode.mode);
    assert.match(block[1], new RegExp(`--density-control:\\s*${control}px;`), mode.mode);
    assert.match(block[1], /--density-gap:\s*\d+px;/, mode.mode);
    assert.match(block[1], /--density-type-size:\s*[\d.]+px;/, mode.mode);
  }
});

test("density changes row height, spacing and type only -- nothing else moves", () => {
  // Patterns, CROSS: "Four modes changing row height, spacing step and type step only.
  // Colour, radius, anatomy and hierarchy are invariant." A density block that redefined a
  // colour or a radius would be a fifth theme wearing a density's name.
  const blocks = css.match(/\n\[data-density="[a-z]+"\] \{[^}]*\}/g) ?? [];
  assert.ok(blocks.length >= 3, "the density modes are not emitted");
  for (const block of blocks) {
    const declared = [...block.matchAll(/(--[a-z-]+):/g)].map((m) => m[1]);
    for (const name of declared) {
      assert.ok(
        name.startsWith("--density-"),
        `a density block declares ${name}, which is not row height, spacing or type`,
      );
    }
  }
});

test("the 44px touch floor is in the component layer, not in call sites", () => {
  // CROSS: "44px minimum in Touch and Spacious; 32px floor in Compact desktop where a pointer
  // is guaranteed." A floor each caller has to remember is a floor the sign-in button lost
  // the moment it stopped being a hand-rolled control -- it rendered at 36px on a phone, and
  // only a browser test noticed.
  assert.match(globals, /\(pointer: coarse\)/, "no pointer-based rule");
  const touch = globals.match(/\n\[data-density="touch"\] \.ds-button[^}]*\}/);
  assert.ok(touch, "touch density does not raise the button floor");
  assert.match(touch[0], /min-block-size: 44px/);
});

test("the touch floor matches a screen's own wrapper, not only the document", () => {
  // **The same defect the row height already had.** The generated token file was written
  // `:root[data-density=…]` once, which matches `<html>` and nothing else, so a screen
  // setting its density on a wrapper read as the default -- found by measuring the rendered
  // rows. This rule was left behind, and it matters more: 44px on Touch and Spacious is "the
  // minimum target, not a style", so a Front Desk screen got the type and the row height and
  // a 36px button under the finger it is designed for.
  assert.doesNotMatch(
    globals, /:root\[data-density="(touch|spacious)"\]/,
    "a density rule scoped to :root cannot be set by a screen");
});

test("the breakpoint tokens are the source's ranges", () => {
  for (const bp of contracts.breakpoints) {
    const from = bp.range.match(/^(\d+)/)[1];
    assert.equal(token(bp.name.replace(".", "-")), `${from}px`, bp.name);
  }
});

test("every media query in the app sits on a breakpoint boundary", () => {
  // **A media query cannot read a custom property**, so these are the one place in the app
  // where a design number is a literal -- which is exactly where a drift would be invisible.
  // The boundaries are the generated tokens: `min-width` at the breakpoint, `max-width` one
  // pixel below the next one up.
  const boundaries = new Set();
  const starts = contracts.breakpoints.map((bp) => parseInt(bp.range.match(/^(\d+)/)[1], 10));
  for (const start of starts) {
    boundaries.add(`min-${start}`);
    if (start > 0) boundaries.add(`max-${start - 1}`);
  }
  // 48rem is the pre-existing form-layout breakpoint, which predates the shell and is not a
  // design-system breakpoint; it is allowed by name rather than silently by unit.
  const allowedRem = new Set(["48rem"]);

  const queries = [...globals.matchAll(/@media \(((?:min|max)-width): ([^)]+)\)/g)];
  assert.ok(queries.length > 0, "no media queries found");
  for (const [, direction, value] of queries) {
    if (allowedRem.has(value.trim())) continue;
    const px = parseInt(value, 10);
    const key = `${direction.startsWith("min") ? "min" : "max"}-${px}`;
    assert.ok(
      boundaries.has(key),
      `@media (${direction}: ${value}) is not a breakpoint boundary. Known: ${[...boundaries].join(", ")}`,
    );
  }
});

test("every ds- class a screen writes is one the stylesheet defines", () => {
  // **`ds-card` was a class name with no rule behind it.** It appears in globals.css exactly
  // once, inside a `prefers-reduced-motion` block, and nowhere as a definition -- so two
  // screens asked for a card and got a loose stack of text. Found by looking at the rendered
  // page, which is this surface's standing lesson; nothing in four layers of assertions can
  // see a class that styles nothing, because the text and the structure are identical
  // either way.
  //
  // Scoped to `ds-` because that is the design system's own prefix: an undefined one is a
  // component this app thinks it has.
  const used = new Set();
  for (const file of tsxFiles(fileURLToPath(new URL("../../src", import.meta.url)))) {
    for (const [, value] of readFileSync(file, "utf8").matchAll(/className="([^"{}]+)"/g)) {
      for (const name of value.split(/\s+/)) {
        if (name.startsWith("ds-")) used.add(name);
      }
    }
  }
  const defined = new Set(
    [...globals.matchAll(/\.(ds-[a-z0-9-]+)/g)].map((m) => m[1]));
  const missing = [...used].filter((name) => !defined.has(name)).sort();
  assert.deepEqual(missing, [], "these ds- classes style nothing");
});
