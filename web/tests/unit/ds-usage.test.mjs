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
  "access/[zoneId]/page.tsx",
  "access/page.tsx",
  "account/account-view.tsx",
  "catalog/page.tsx",
  "configuration/page.tsx",
  "finance/page.tsx",
  "fleet/page.tsx",
  "integrations/page.tsx",
  "notifications/page.tsx",
  "operations/page.tsx",
  "organization/page.tsx",
  "page.tsx",
  "people/page.tsx",
  "permissions/page.tsx",
  "privacy/page.tsx",
  "schedule/[sessionId]/page.tsx",
  "schedule/page.tsx",
]);

/**
 * Screens that still group with a bare `.panel` rather than `Card`.
 *
 * `Card` requires a `kind` over the six the source names, which is what makes
 * "cardification" an argument somebody has to make at the call site rather than a default.
 */
const RAW_PANELS = new Set([
  ...RAW_TABLES,
  "account/page.tsx",
  // These two have no table of their own -- their tables live in a shared panel component --
  // and they do still group with a bare .panel, which is why they are here and not above.
  "fleet/[deviceId]/page.tsx",
  "login/login-form.tsx",
  "people/[personId]/page.tsx",
  "step-up/step-up-form.tsx",
]);

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

test("the raw-table backlog has not gone stale", () => {
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

test("nothing imports the deleted ad-hoc control module", () => {
  const offenders = files
    .filter((f) => f.text.includes("@/components/controls"))
    .map((f) => f.path);
  assert.deepEqual(offenders, [], "controls.tsx is gone; its families are under ds/");
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
