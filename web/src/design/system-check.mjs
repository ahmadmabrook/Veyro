#!/usr/bin/env node
/**
 * The new design system's own structural checks.
 *
 * **What this replaces.** `design:check` used to run `extract.mjs --check`, `screens.mjs
 * --check` and `coverage.mjs`, all three of which read
 * `veyro-product-experience-design/project/*.dc.html` and failed when the implementation
 * drifted from those canvases. That design is deprecated, so a gate enforcing fidelity to it
 * would hold the product to the look it was told to replace. The extractors still exist and
 * the data they produced is still pinned -- the status vocabulary, the screen registry and
 * the shell numbers are product facts now, not visual ones -- but nothing re-derives them
 * from the retired source on every build.
 *
 * **What it checks instead.** Four mechanical properties of the system in `ds.json`, each
 * chosen because it caught something real while the redesign was being built, and each
 * provable by breaking it:
 *
 *   1. Every custom property a stylesheet or component reads is defined somewhere. Fifteen
 *      were not, eleven of them genuinely broken: `--color-action-default` (the current nav
 *      item's colour, so it inherited), `--radius-input`, `--color-focus-ring`, and six
 *      `--p-warm-*` primitives from the retired ramp.
 *   2. No component reaches a layer-1 `--p-*` primitive. The generator has said from the
 *      start that "layer 2 is the only colour layer components are allowed to consume" and
 *      that a theme is a remapping of layer 2 rather than a rewrite of layer 1 -- and six
 *      avatars and marks reached past it anyway, which is why they lost their colour
 *      entirely when the ramp was replaced.
 *   3. Every `ds-*` class a component asks for is defined in the stylesheet. A class that
 *      styles nothing is invisible to every other layer: the text and the structure are
 *      identical either way, so only a sweep sees it.
 *   4. Nothing sets a monospace family. This world has no mono role -- monospace is for code,
 *      not for "technical" -- and tabular alignment is a font feature both faces ship.
 *
 * Run it: `npm run design:check`.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("..", import.meta.url));

/**
 * Properties set at runtime rather than in a stylesheet, with the reason each one is.
 *
 * An allow-list of three, not a tolerance: every other name has to be defined in CSS. These
 * are declared rather than pattern-matched so that adding a fourth is a decision somebody
 * writes down.
 */
const RUNTIME_PROPERTIES = new Map([
  ["--font-text", "set by next/font on <html>; see layout.tsx"],
  ["--font-figure", "set by next/font on <html>; see layout.tsx"],
  ["--font-arabic", "set by next/font on <html>; see layout.tsx"],
]);

function walk(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry.startsWith(".")) continue;
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) walk(path, out);
    else if (/\.(css|tsx|ts)$/.test(entry)) out.push(path);
  }
  return out;
}

const files = walk(SRC);
const read = new Map(files.map((f) => [f, readFileSync(f, "utf8")]));
const rel = (f) => f.slice(SRC.length);
const failures = [];

// --- 1. every custom property resolves -----------------------------------------------------

const defined = new Set();
for (const [file, text] of read) {
  if (!file.endsWith(".css")) continue;
  for (const m of text.matchAll(/(--[a-zA-Z0-9-]+)\s*:/g)) defined.add(m[1]);
}

const used = new Map();
for (const [file, text] of read) {
  for (const m of text.matchAll(/var\((--[a-zA-Z0-9-]+)/g)) {
    if (!used.has(m[1])) used.set(m[1], new Set());
    used.get(m[1]).add(rel(file));
  }
}

for (const [name, where] of [...used].sort()) {
  if (defined.has(name) || RUNTIME_PROPERTIES.has(name)) continue;
  failures.push(
    `undefined custom property ${name}\n    used in ${[...where].sort().join(", ")}\n` +
      `    define it in ds.json and regenerate, or declare it in RUNTIME_PROPERTIES with a reason`,
  );
}

// A stale allow-list is the other direction, and it fails too: a runtime property that has
// since been defined in CSS is an entry nobody needs, and an entry nothing uses is a note
// about a property that is gone.
for (const [name, why] of RUNTIME_PROPERTIES) {
  if (!used.has(name)) failures.push(`RUNTIME_PROPERTIES names ${name}, which nothing uses (${why})`);
}

// --- 2. no component reaches layer 1 -------------------------------------------------------

for (const [file, text] of read) {
  // `globals.css` is the component layer too, but the stylesheet is where the theme's own
  // plumbing lives, so a primitive is permitted there only inside a declaration that defines
  // another custom property. Anywhere a value is set directly, it has to be a layer-2 token.
  for (const m of text.matchAll(/var\((--p-[a-zA-Z0-9-]+)\)/g)) {
    const before = text.slice(Math.max(0, m.index - 120), m.index);
    const line = before.slice(before.lastIndexOf("\n") + 1);
    if (/^\s*--[a-zA-Z0-9-]+\s*:/.test(line)) continue;
    failures.push(
      `${rel(file)} reads the layer-1 primitive ${m[1]} directly\n` +
        `    layer 2 is the only colour layer components consume, so a theme stays a remapping`,
    );
  }
}

// --- 3. every ds- class is styled -----------------------------------------------------------

const styled = new Set();
for (const [file, text] of read) {
  if (!file.endsWith(".css")) continue;
  for (const m of text.matchAll(/\.(ds-[a-zA-Z0-9-]+)/g)) styled.add(m[1]);
}

/**
 * **Comments are stripped first, and a name may be a prefix.** Both of those are corrections
 * the check needed on its first run, and both are the same failure: reporting a defect the
 * app does not have costs the same trust as missing one.
 *
 * Comments, because this codebase explains its own history in prose -- two findings were a
 * class named in a comment about why it no longer exists, and one was a reference to the
 * filename `ds-usage.test.mjs`. A prefix, because several classes are built from a template
 * literal: `ds-col-p${priority}` and `ds-badge-${severity}` put `ds-col-p` and `ds-badge` in
 * the source while what ships is `ds-col-p2` and `ds-badge-critical`.
 */
const withoutComments = (text) =>
  text.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/(^|[^:])\/\/[^\n]*/g, "$1");

const asked = new Map();
for (const [file, text] of read) {
  if (file.endsWith(".css")) continue;
  for (const m of withoutComments(text).matchAll(/\b(ds-[a-z][a-zA-Z0-9-]*)\b/g)) {
    if (!asked.has(m[1])) asked.set(m[1], new Set());
    asked.get(m[1]).add(rel(file));
  }
}

const styledList = [...styled];
for (const [name, where] of [...asked].sort()) {
  if (styled.has(name)) continue;
  // A template literal's constant head: `ds-col-p` ships as `ds-col-p2`.
  if (styledList.some((s) => s.startsWith(name))) continue;
  failures.push(
    `${name} styles nothing\n    asked for in ${[...where].sort().join(", ")}\n` +
      `    a design-system prefix is a promise the component exists`,
  );
}

// --- 4. no monospace --------------------------------------------------------------------------

for (const [file, text] of read) {
  for (const m of text.matchAll(/font-family:[^;}]*\b(mono(space)?|ui-monospace)\b/gi)) {
    failures.push(
      `${rel(file)} sets a monospace family: ${m[0].trim().slice(0, 70)}\n` +
        `    this world has no mono role; tabular alignment is font-variant-numeric`,
    );
  }
}

// --- report ------------------------------------------------------------------------------

if (failures.length) {
  console.error(`design:check found ${failures.length} problem(s):\n`);
  for (const f of failures) console.error(`  - ${f}\n`);
  process.exit(1);
}

console.log(
  `ok design system: ${defined.size} properties defined, ${used.size} read, ` +
    `${styled.size} classes styled, ${asked.size} asked for, no layer-1 reach, no monospace`,
);
