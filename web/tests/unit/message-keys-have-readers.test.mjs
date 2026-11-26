import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

/**
 * Every message key is rendered somewhere, in both directions.
 *
 * **This is the catalogue's half of a finding the rules file records about tables.** The
 * project's most-repeated defect is a declared value nothing writes -- a status no service
 * sets, a grant no writer uses, a column implying a control nobody implemented. A message key
 * with no reader is the same shape in the one file that has 2,700 of them: it survives every
 * check this app has, because `MESSAGE_KEYS` compares the two catalogues *against each other*
 * and a key missing from neither is a key it is happy with.
 *
 * It matters for two reasons beyond dead weight. A key that stopped being rendered is usually
 * a sentence somebody removed from a screen, and the leftover is the only trace that the
 * screen used to say something -- so a reader greps the catalogue, finds the sentence, and
 * concludes the product says it. And an orphan is the thing a translator pays to translate
 * twice: 190 of them were removed in the pass that added this test, which is 380 strings
 * nobody could reach.
 *
 * **The file list is built with `readdirSync`, deliberately, and that is the bug this test was
 * written after.** The sweep that found those 190 used `git ls-files 'src/**' + '/*' + '.tsx'`,
 * and a git pathspec is a glob: `[zoneId]` in a dynamic route's path is a *character class*,
 * so every file under `src/app/access/[zoneId]/`, `src/app/people/[personId]/` and nine more
 * directories was silently excluded. Sixty-two keys were reported as orphans while being
 * rendered on a live screen, and `tsc` is what caught it. A recursive directory walk has no
 * glob semantics at all, which is why it is the only safe way to enumerate this app's files.
 */

const here = fileURLToPath(new URL(".", import.meta.url));
const root = join(here, "..", "..");
const CATALOGUE = join(root, "src", "i18n", "locale.ts");

/** Every source and test file, found by walking rather than by matching a pattern. */
function walk(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === ".next") continue;
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) walk(path, out);
    else if (/\.(ts|tsx|mjs|js)$/.test(entry) && path !== CATALOGUE) out.push(path);
  }
  return out;
}

const catalogue = readFileSync(CATALOGUE, "utf8");
const body = walk(join(root, "src"))
  .concat(walk(join(root, "tests")))
  .map((path) => readFileSync(path, "utf8"))
  .join("\n");

/**
 * A key reached through a template literal -- `` `staff.grant.${reach}` `` -- makes every key
 * under that prefix reachable without any of them appearing as a literal. Collecting the
 * prefixes is what keeps the check from reporting a whole family of live keys.
 */
const prefixes = [...body.matchAll(/`([a-zA-Z0-9_.]+)\.\$\{/g)].map((m) => m[1]);

const declared = [...catalogue.matchAll(/^ {4}"([a-zA-Z0-9_.]+)": /gm)].map((m) => m[1]);

/**
 * A key is referenced when it appears as a *whole* token, not as a substring.
 *
 * **`includes` was the first version and it missed a whole family.**
 * `attendanceReport.gapClassFill` is rendered nowhere; `attendanceReport.gapClassFillLabel`
 * is, and the first is a prefix of the second -- so the orphan read as referenced and its
 * 1,191 characters stayed in both catalogues. Every `…Title`/`…Why` and `…Label`/`…Body` pair
 * in this app has that shape, which is most of the gap notes, so the trap was aimed squarely
 * at the keys this sweep was written to find.
 */
const referenced = (key) =>
  new RegExp(`["'\`]${key.replace(/\./g, "\\.")}["'\`]`).test(body);

test("every declared message key has a reader", () => {
  const orphans = [...new Set(declared)].filter(
    (key) => !referenced(key) && !prefixes.some((p) => key.startsWith(`${p}.`)),
  );
  assert.deepEqual(
    orphans,
    [],
    `${orphans.length} message keys are declared and rendered nowhere. A key with no reader is `
      + `a sentence a reader will find in the catalogue and conclude the product says. Remove `
      + `it, or render it:\n  ${orphans.join("\n  ")}`,
  );
});

test("the file walk reaches a dynamic route, which a glob would not", () => {
  // The sixty-two false orphans all lived in bracketed directories. This asserts the walk
  // sees one, so the check above cannot pass by having looked at nothing.
  const walked = walk(join(root, "src")).map((path) => path.slice(root.length));
  assert.ok(
    walked.some((path) => path.includes("[") && path.includes("]")),
    "the walk found no bracketed dynamic-route file, so it is not reading this app",
  );
  assert.ok(walked.length > 100, `only ${walked.length} source files found`);
});

test("a key reached only through a template literal is not an orphan", () => {
  // `staff.grant.${grant.reach}` is the live instance. If prefix collection broke, this
  // family would be reported and the check would be unusable.
  assert.ok(prefixes.length > 0, "no template-literal key prefixes found at all");
  assert.ok(
    declared.some((key) => prefixes.some((p) => key.startsWith(`${p}.`))),
    "no declared key sits under a template-literal prefix, so that branch is untested",
  );
});
