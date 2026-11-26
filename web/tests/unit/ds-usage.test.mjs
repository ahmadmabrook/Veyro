import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

/**
 * No screen hand-rolls a component the design system already approves.
 *
 * §8 of the owner directive of 2026-11-20: "Do not introduce new ad-hoc components that
 * duplicate approved design-system components." That is a rule a reviewer cannot hold in
 * their head across fifteen screens, so it is a sweep — and like every sweep in this
 * repository it runs **in both directions**: a file not on the list that hand-rolls one
 * fails, and a file on the list that no longer does fails too, so the backlog cannot quietly
 * stop shrinking while the exemption stays.
 *
 * **The lists below are a backlog, not a licence.** Each entry is a screen built before the
 * design system was read, and the number can only go down — removing the last entry of a
 * list is what retires its rule into an absolute one.
 */

const WEB = fileURLToPath(new URL("../../", import.meta.url));
const APP = join(WEB, "src/app");

/**
 * Screens that still render a raw `<table>` rather than `DataGrid`.
 *
 * DataGrid carries nine states, column priority, the restricted-cell rule, one composite tab
 * stop and the bp.xs list form. A hand-rolled table has none of those: every one of these
 * files renders a table with exactly one state, and on a phone its low-priority columns are
 * simply off the screen rather than collapsed into the primary cell.
 */
const RAW_TABLES = new Set([
  // **Empty, which is the point.** Every board is on DataGrid now, so this rule has stopped
  // being a backlog and become an absolute one: the next raw <table> in a screen fails here.
]);

/**
 * Screens that still group with a bare `.panel` rather than `Card`.
 *
 * **Empty, and the correction was not what it looked like.** The obvious migration was
 * panel → Card on all 64 sections; the right one was to stop boxing them at all. §31: a Card
 * is "meaningful grouping only", six kinds, and "a card that only draws a border around a
 * paragraph is deleted — 'cardification' of every screen is explicitly prohibited". Six
 * bordered boxes stacked down a report page *is* that anti-pattern at the scale of a surface.
 * A page section is a heading, its prose and its grid, separated by the type scale and the
 * shell's gutter; `Card` is kept for content that genuinely is one.
 */
const RAW_PANELS = new Set([]);

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else if (entry.endsWith(".tsx")) out.push(full);
  }
  return out;
}

const files = walk(APP).map((full) => ({
  path: full.slice(APP.length + 1),
  text: readFileSync(full, "utf8"),
}));

test("the app has screens to sweep", () => {
  // A sweep over an empty set passes vacuously, which is the failure this file exists against.
  assert.ok(files.length >= 15, `only ${files.length} screens found`);
});

test("no new screen hand-rolls a table where DataGrid exists", () => {
  const offenders = files
    .filter((f) => f.text.includes("<table") && !RAW_TABLES.has(f.path))
    .map((f) => f.path);
  assert.deepEqual(
    offenders,
    [],
    "these render a raw <table>; use DataGrid from @/components/ds/data-grid, or add the "
      + "file to RAW_TABLES with the reason it cannot yet",
  );
});

test("the raw-table backlog is empty, and stays honest if it is not", () => {
  const fixed = [...RAW_TABLES].filter((path) => {
    const file = files.find((f) => f.path === path);
    return file && !file.text.includes("<table");
  });
  assert.deepEqual(
    fixed,
    [],
    "these no longer hand-roll a table -- take them out of RAW_TABLES so the backlog is the "
      + "real one",
  );
  const gone = [...RAW_TABLES].filter((path) => !files.some((f) => f.path === path));
  assert.deepEqual(gone, [], "RAW_TABLES names files that do not exist");
});

test("no new screen groups with a bare panel where Card exists", () => {
  const offenders = files
    .filter((f) => f.text.includes('className="panel') && !RAW_PANELS.has(f.path))
    .map((f) => f.path);
  assert.deepEqual(
    offenders,
    [],
    "these use a bare .panel; use Card from @/components/ds/card with one of the six kinds, "
      + "or add the file to RAW_PANELS",
  );
});

test("a status badge carries the word in the reader's language", () => {
  // **The enum is the state; the word is a message key.** `VOCABULARY` is twenty English
  // words from the design source, and that closed set is what stops an engineer inventing
  // "Semi-active" -- it says nothing about which language the page is in. Rendering the enum
  // put "Denied" in Latin letters in the middle of an Arabic line on the first screen that
  // used this component.
  //
  // **No other check can see it.** `MESSAGE_KEYS` compares the two catalogues against each
  // other and is blind to a string that never became a key; an assertion about structure
  // matches either word. So the guard is structural and here, counted per badge rather than
  // per file for the reason the grid sweep above is.
  const offenders = files
    .filter((f) => {
      const badges = (f.text.match(/<StatusBadge\b/g) ?? []).length;
      const labelled = (f.text.match(/label=\{/g) ?? []).length;
      return badges > labelled;
    })
    .map((f) => f.path);
  assert.deepEqual(
    offenders,
    [],
    "these render a StatusBadge with no label; pass the localized word, because the status "
      + "enum is English and a page may not be",
  );
});

/**
 * The opening tag of each `<Name` in a file, attributes only.
 *
 * Depth-aware on `{}`, because a prop's value is an expression that may contain a `>` -- an
 * arrow function or a comparison -- and the first `>` in the raw text is then not the end of
 * the tag. A plain `indexOf(">")` is the shape that makes a sweep report an offender the app
 * does not have, which costs the same trust as missing one.
 */
function openingTags(text, name) {
  const tags = [];
  const needle = new RegExp(`<${name}\\b`, "g");
  let found;
  while ((found = needle.exec(text)) !== null) {
    let depth = 0;
    for (let i = found.index + found[0].length; i < text.length; i += 1) {
      const ch = text[i];
      if (ch === "{") depth += 1;
      else if (ch === "}") depth -= 1;
      else if (ch === ">" && depth === 0) {
        tags.push(text.slice(found.index, i));
        break;
      }
    }
  }
  return tags;
}

test("an optional field's mark is a word from the catalogue", () => {
  // **A mark is a word and an asterisk is not.** The field shell marks whichever side is
  // rarer in a form, and for the optional side that mark is prose -- which it hard-coded as
  // `" (optional)"` until now: Latin letters in the middle of an Arabic line, on the account
  // page, for as long as that field has existed.
  //
  // **Neither message check can see it**, which is why this is a sweep and not a test.
  // `MESSAGE_KEYS` compares the two catalogues against each other and a string that never
  // became a key is in neither; the per-plural-form sweep reads call sites of `fill`. So the
  // guard is structural, exactly as StatusBadge's label is above, and it is counted per
  // field rather than per file because one screen has several.
  const offenders = [];
  for (const file of files) {
    for (const tag of openingTags(file.text, "Field")) {
      if (!tag.includes('rarer="optional"')) continue;
      // A *required* field under `rarer="optional"` is not marked at all, so it needs no
      // word. That is most of this app: the two-field forms mark neither side.
      if (/\brequired\b/.test(tag)) continue;
      if (tag.includes("optionalLabel")) continue;
      offenders.push(`${file.path}: ${tag.split("\n")[0].trim()}`);
    }
  }
  assert.deepEqual(
    offenders,
    [],
    "these render an optional field with no `optionalLabel`; pass the localized word, "
      + "because the shell cannot invent one and an unmarked optional field is the quiet "
      + "half of the same defect",
  );
});

test("nothing imports the deleted ad-hoc control module", () => {
  const offenders = files
    .filter((f) => f.text.includes("@/components/controls"))
    .map((f) => f.path);
  assert.deepEqual(offenders, [], "controls.tsx is gone; its families are under ds/");
});

test("a grid under a heading points at it rather than repeating it", () => {
  // **A visually-hidden caption under a visible heading of the same words is the sentence
  // said twice**: invisible to a sighted reader, heard in full by a screen-reader user. The
  // hand-rolled tables all used `aria-labelledby` for exactly that reason, and the first
  // DataGrid migration dropped it on eight grids at once -- one e2e test caught one of them.
  // **Per grid, not per file.** The first version asked whether the *file* contained a
  // `labelledBy=` anywhere, so a page with three grids passed when one of them lost its
  // label -- which is exactly `/permissions`, and exactly what a mutation removing one
  // found: the sweep stayed green while the gate table named itself twice.
  //
  // **Counted rather than parsed**, because a `<DataGrid<SourceRow>` opening tag is a
  // TypeScript generic and `[^>]*>` stops at the generic's own `>` -- which reported a
  // correctly-labelled grid as an offender, a false finding from the check rather than from
  // the app. `labelledBy` is a prop of `DataGrid` and `CapabilityMatrix` and nothing else,
  // so the two counts have to agree.
  const offenders = files
    .filter((f) => {
      const grids = (f.text.match(/<DataGrid\b/g) ?? []).length
        + (f.text.match(/<CapabilityMatrix\b/g) ?? []).length;
      const labelled = (f.text.match(/labelledBy=/g) ?? []).length;
      return grids > labelled;
    })
    .map((f) => f.path);
  assert.deepEqual(
    offenders,
    [],
    "these render a DataGrid with no labelledBy; point it at the heading above it, or say "
      + "in a comment why this grid has no heading",
  );
});

test("a grid states its count, or says the page states it", () => {
  // **§25: "the count always states what is selected."** The slot used to fall back to
  // `rows.length`, so a grid that passed nothing rendered a bare numeral -- a stray
  // character to a reader who has not been told what it counts -- and every grid in the app
  // did exactly that for as long as the fallback existed.
  //
  // The fallback is gone, which turns the omission into silence rather than into the banned
  // character; this is what stops silence being the accident. Fourteen grids genuinely state
  // their count elsewhere -- twelve under a page header whose own figures line carries the
  // figure, the resolved board's sub-line, and the payments ledger's "N rows in this window"
  // -- and each says so with `countLabel={null}` rather than by leaving the prop off.
  //
  // **Counted rather than parsed**, for the reason the `labelledBy` sweep above records: a
  // `<DataGrid<SourceRow>` opening tag is a generic and `[^>]*>` stops at the wrong `>`.
  const offenders = files
    .filter((f) => {
      const grids = (f.text.match(/<DataGrid\b/g) ?? []).length;
      const counted = (f.text.match(/countLabel=/g) ?? []).length;
      return grids > counted;
    })
    .map((f) => f.path);
  assert.deepEqual(
    offenders,
    [],
    "these render a DataGrid with no countLabel; pass the whole phrase, or countLabel={null} "
      + "where the page already states the count",
  );
});

test("no screen paints its own severity colour", () => {
  // "One accent, spent once": semantic colour belongs to StatusBadge, Banner and the row
  // edge-mark. A page that reaches for `--color-semantic-error` directly is a page deciding
  // what counts as an error, which is the severity scale said twice and differently.
  const allowed = new Set(["access/[zoneId]/page.tsx"]);
  const offenders = files
    .filter((f) => /--color-semantic-(error|warning|success)/.test(f.text))
    .filter((f) => !allowed.has(f.path))
    .map((f) => f.path);
  assert.deepEqual(
    offenders,
    [],
    "these reference a semantic colour directly; the severity belongs to a DS component",
  );
});

/**
 * A class a component owns is not written by a screen.
 *
 * §8 of the direction contract bans a hand-rolled copy of an approved component, and the
 * copies this project keeps finding are not whole components -- they are a screen writing
 * the component's own class names onto its own markup. The members board did it with
 * `ds-page-head`; the reports index did it with `ds-notyet`, which put "Not here yet" on the
 * page twice with a rule between the two and rendered the component's heading `id` twice
 * over, so the second region was unreachable by name.
 *
 * **The tell is always the same and no other check sees it.** The class is defined, so the
 * undefined-class sweep passes; both copies render, so every assertion about text passes;
 * and the duplication is one line in a file nobody is reading. It is found by looking at the
 * page, which is the instrument this project relies on far too heavily for something a
 * substring can answer.
 */
const OWNED = [
  ["ds-notyet", "src/components/not-yet.tsx"],
  ["ds-page-head", "src/components/ds/page-header.tsx"],
  ["ds-metric", "src/components/ds/metric-cell.tsx"],
  ["ds-metric-row", "src/components/ds/metric-cell.tsx"],
  ["ds-metric-delta", "src/components/ds/delta.tsx"],
  ["ds-grid-table", "src/components/ds/data-grid.tsx"],
];

test("no screen writes a class its component owns", () => {
  const offences = [];
  for (const [cls, owner] of OWNED) {
    for (const { path, text } of files) {
      if (path.endsWith(owner.replace("src/", ""))) continue;
      // The exact class, not a longer one that merely starts with it.
      const re = new RegExp(`className="[^"]*\\b${cls}\\b[^"]*"`);
      if (re.test(text)) offences.push(`${path} writes .${cls}, which ${owner} owns`);
    }
  }
  assert.deepEqual(
    offences, [],
    `a screen is hand-rolling a component's markup:\n  ${offences.join("\n  ")}`,
  );
});

test("the owned-class list names classes that exist and components that own them", () => {
  // A list naming a class nothing defines, or a component that does not write it, is a sweep
  // that passes by looking at nothing -- the vacuity this file exists to prevent.
  const css = readFileSync(join(WEB, "src/app/globals.css"), "utf8");
  for (const [cls, owner] of OWNED) {
    assert.ok(css.includes(`.${cls}`), `.${cls} is not defined in globals.css`);
    const src = readFileSync(join(WEB, owner), "utf8");
    assert.ok(src.includes(cls), `${owner} does not write .${cls}, so it does not own it`);
  }
});
