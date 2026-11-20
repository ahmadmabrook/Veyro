import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import test from "node:test";

/**
 * Every permission this app names exists in MOD-008's catalogue.
 *
 * **A gate asking about a permission that does not exist renders as a refusal.**
 * `authz.check` answers an action it has never heard by finding no assignment that grants it,
 * which is indistinguishable from a real denial -- so a misspelled or invented name makes a
 * page say "you do not hold this" to a reader who holds everything, with nothing anywhere
 * saying otherwise.
 *
 * The Member 360's metric row did exactly that: it asked for `finance.invoice.read`, which
 * has never existed (the catalogue's `finance.account.read` covers "a member billing account,
 * its invoices and its schedule"), and the OUTSTANDING cell told the owner of the tenant that
 * they lacked a permission. It was found by looking at the rendered page, which is the only
 * thing that could have found it -- typecheck, lint and every test passed.
 *
 * `/authz/checks` now refuses an undeclared action with a 422 rather than denying it, so the
 * same mistake fails loudly at runtime. This test is the other half: it fails at build time,
 * before anybody renders anything. Both directions matter for the same reason the message
 * catalogue's parity check needed both -- but only one direction is checkable here, because a
 * catalogue permission no screen uses is ordinary rather than a defect.
 */

const ROOT = new URL("../../src/", import.meta.url).pathname;

function sources(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...sources(full));
    else if (/\.tsx?$/.test(entry)) out.push(full);
  }
  return out;
}

/**
 * Every permission-shaped string the app passes to the gate.
 *
 * It matches `gate("x.y")`, `gateAll([...])` entries and `permission: "x.y"` properties --
 * the three shapes the app uses. A name assembled at runtime would escape this, which is why
 * there are none: a permission is a literal everywhere in this codebase, exactly so a sweep
 * can see it.
 */
function named() {
  const found = new Map();
  for (const file of sources(ROOT)) {
    const text = readFileSync(file, "utf8");
    for (const match of text.matchAll(/\bgate\(\s*"([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)"/g)) {
      found.set(match[1], file);
    }
    for (const block of text.matchAll(/\bgateAll\(\s*\[([\s\S]*?)\]/g)) {
      for (const one of block[1].matchAll(/"([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)"/g)) {
        found.set(one[1], file);
      }
    }
  }
  return found;
}

function catalogue() {
  const script =
    "import sys, json; sys.path.insert(0, 'ROOT');"
    + " from app.authorization.catalog import PERMISSIONS;"
    + " print(json.dumps(sorted(PERMISSIONS)))";
  const backend = new URL("../../../backend/", import.meta.url).pathname;
  for (const exe of ["python3", "python"]) {
    const run = spawnSync(exe, ["-I", "-c", script.replace("ROOT", backend)],
      { encoding: "utf8" });
    if (run.status === 0) return new Set(JSON.parse(run.stdout));
  }
  return null;
}

const declared = catalogue();

test("the backend catalogue is reachable, or the gap is named", { skip: !declared }, () => {
  assert.ok(declared, "python3 with the backend on sys.path is needed for this check");
});

test("every permission this app asks the gate about is declared", { skip: !declared }, () => {
  const asked = named();
  assert.ok(asked.size > 20, `expected the app to gate on many permissions, saw ${asked.size}`);
  const undeclared = [...asked].filter(([name]) => !declared.has(name));
  assert.deepEqual(
    undeclared.map(([name, file]) => `${name} (${path.relative(ROOT, file)})`),
    [],
    "a gate naming a permission the catalogue does not declare renders as a refusal",
  );
});
