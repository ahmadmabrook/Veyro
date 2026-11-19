#!/usr/bin/env node
/**
 * Break one protection at a time and check that the suite notices.
 *
 * **A test that still passes when you remove the thing it guards is not evidence.** That is the
 * backend's rule (`.claude/rules/backend/mod004-rls.md`) and there is no reason the browser half
 * should be held to a weaker one -- the web suite is newer, has no mutation history, and three
 * of its first thirty assertions failed for reasons that had nothing to do with the product.
 *
 * Each mutation edits a source file, runs only the test that names that protection, and expects
 * a FAILURE. A mutation whose test still passes is reported as a gap. The file is restored
 * afterwards whatever happens, including on a crash **and on a signal** -- the `finally` does
 * not run when the process is killed, and a sweep stopped halfway left a deleted line in
 * `access/[zoneId]/page.tsx` for an hour. What made it expensive to find is that the mutation
 * whose `to` is the empty string is a *deletion*, so searching the tree for the mutated text
 * cannot detect it: the next run of that one mutation reported "the anchor appears 0 times",
 * which is the only trace there was.
 *
 *   node tests/e2e/mutate.mjs            # all of them
 *   node tests/e2e/mutate.mjs focus      # only mutations whose id contains "focus"
 *
 * Needs the web app and the backend running, and `web/.env.e2e.local`.
 */

import { spawnSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

/**
 * `file` is relative to `web/`. `from` must appear exactly once -- a mutation that matched
 * nothing, or matched twice, is reported rather than run, because "the statement did not apply"
 * recorded as a catch is the false green this whole exercise exists to prevent.
 *
 * `runner` is `"playwright"` unless stated. `"vitest"` is for a protection whose test is a
 * component test rather than a browser one -- the device-label parity, where the whole point
 * of the test is that it needs no browser and no fixture.
 */
const MUTATIONS = [
  {
    id: "form-method",
    why: "the sign-in form must be a POST so credentials cannot reach a query string",
    file: "src/app/login/login-form.tsx",
    from: "<form action={formAction} noValidate",
    to: '<form action="/login" method="get" noValidate',
    grep: "the form is a POST|the served form is a POST",
  },
  {
    id: "session-httponly",
    why: "the bearer token must be unreadable from client JavaScript",
    file: "src/app/login/actions.ts",
    from: 'jar.set(SESSION_COOKIE, token, { httpOnly: true, sameSite: "strict", secure, path: "/" });',
    to: 'jar.set(SESSION_COOKIE, token, { httpOnly: false, sameSite: "strict", secure, path: "/" });',
    grep: "sets an httpOnly session",
  },
  {
    id: "refusal-detail",
    why: "a refusal must not distinguish a wrong password from an unknown address",
    file: "src/i18n/locale.ts",
    from: '"login.failed": "Those details were not accepted.",',
    to: '"login.failed": "No such account was found.",',
    grep: "refused without saying why",
  },
  {
    id: "field-errors",
    why: "an empty submission must name every missing field",
    file: "src/app/login/actions.ts",
    from: "  if (missing.tenant || missing.identifier || missing.password || missing.recovery) {\n    return { error: null, missing, ...echo };\n  }",
    to: "  if (missing.tenant || missing.identifier || missing.password || missing.recovery) {\n    return { error: null, missing: { tenant: false, identifier: false, password: false, recovery: false }, ...echo };\n  }",
    grep: "names every missing field",
  },
  {
    id: "gate-order",
    why: "an unreachable assurance level must not be offered as a step-up",
    file: "src/app/page.tsx",
    from: '  if (answer.allowed) return "gate.allowed";\n  if (!answer.reachable) return "gate.unreachable";\n  if (answer.step_up_required) return "gate.stepUp";',
    to: '  if (answer.allowed) return "gate.allowed";\n  if (answer.step_up_required) return "gate.stepUp";\n  if (!answer.reachable) return "gate.unreachable";',
    grep: "says it is unavailable",
  },
  {
    id: "bidi-isolation",
    why: "a Latin identifier inside Arabic text must carry its own direction",
    file: "src/app/page.tsx",
    from: '                  <span className="data" dir="ltr">',
    to: '                  <span className="data">',
    grep: "renders left-to-right",
  },
  {
    id: "table-name",
    why: "the permissions table must have an accessible name",
    file: "src/app/page.tsx",
    from: '        <table\n          aria-labelledby="permissions-heading"',
    to: "        <table\n",
    grep: "has an accessible name",
  },
  {
    id: "dark-focus-ring",
    why: "the focus ring must be visible in dark mode (guardrail G4)",
    file: "src/design/tokens.generated.css",
    from: "  --color-border-focus: var(--p-accent-light);",
    to: "",
    grep: "focus ring is visible on a field in the dark theme",
  },
  {
    id: "dark-input-surface",
    why: "a form field must not render on the light surface in dark mode",
    file: "src/design/tokens.generated.css",
    from: "  --color-surface-input: var(--p-dark-950);",
    to: "",
    grep: "dark theme remaps the field",
  },
  {
    id: "touch-target",
    why: "the primary control must reach the 44px touch minimum",
    file: "src/components/controls.tsx",
    from: '        minHeight: "44px",\n        padding: "var(--space-2) var(--space-4)",',
    to: '        minHeight: "28px",\n        padding: "0 var(--space-4)",',
    grep: "phone width",
  },
  {
    id: "label-association",
    why: "a validation message must be associated with its field, not merely adjacent",
    file: "src/components/controls.tsx",
    from: "        aria-describedby={described}",
    to: "",
    grep: "names every missing field",
  },
  {
    id: "muster-disclaimer",
    why: "paragraph 4180's disclaimer must be on every occupancy read",
    file: "src/app/access/[zoneId]/page.tsx",
    from: "      <Alert tone=\"info\">{occupancy.detail}</Alert>",
    to: "",
    grep: "disclaimer next to the number",
  },
  {
    id: "access-gaps-hidden",
    why: "a zone must say what it cannot do rather than reading as fully capable",
    file: "src/app/access/[zoneId]/page.tsx",
    from: "        {zone.access_gaps.length > 0 ? (",
    to: "        {false ? (",
    grep: "names what the zone cannot do",
  },
  {
    id: "no-policy-reads-blank",
    why: "a zone with no live policy must say so, not render an empty cell",
    file: "src/app/access/page.tsx",
    from: "                  {zone.live_policy_version === null ? (",
    to: "                  {false ? (",
    grep: "says in words when a zone has no live policy",
  },
  {
    id: "withheld-unmarked",
    why: "a discreet line must be marked as withheld, or it reads as the real reason",
    file: "src/app/access/[zoneId]/page.tsx",
    from: "        {decision.public_reason === DISCREET || isRestricted(decision.code) ? (",
    to: "        {false ? (",
    grep: "shows the discreet line the member saw",
  },
  {
    id: "bidi-clock-range",
    why: "a clock range inside Arabic text must carry its own direction",
    file: "src/app/access/[zoneId]/page.tsx",
    from: "        <span className=\"data\" dir=\"ltr\">\n          {hhmm(policy.opens_minute)}",
    to: "        <span className=\"data\">\n          {hhmm(policy.opens_minute)}",
    grep: "mirrors in Arabic",
  },
  {
    id: "signed-in-redirect",
    why: "a signed-in caller must not be served the sign-in form again",
    file: "src/app/login/page.tsx",
    from: '  if (await currentSession()) redirect("/");',
    to: "",
    grep: "already-signed-in caller",
  },
  {
    id: "device-label-parity",
    why: "the fixture's device label must equal the app's, or every sign-in is challenged and "
      + "the suite spends a single-use recovery code per run",
    file: "tests/e2e/device.mjs",
    from: 'return `web:${createHash("sha256")',
    to: 'return `browser:${createHash("sha256")',
    runner: "vitest",
    grep: "device label",
  },
];

const only = process.argv[2];
const chosen = only ? MUTATIONS.filter((m) => m.id.includes(only)) : MUTATIONS;

// Whatever is currently mutated, so a signal can put it back. One entry at a time, because
// the sweep is serial.
const inFlight = new Map();
function restoreEverything() {
  for (const [path, text] of inFlight) writeFileSync(path, text);
  inFlight.clear();
}
for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.on(signal, () => {
    restoreEverything();
    console.log(`\n${signal}: restored the tree and stopped`);
    process.exit(130);
  });
}
process.on("uncaughtException", (error) => {
  restoreEverything();
  throw error;
});

let caught = 0;
const gaps = [];
const notRun = [];

for (const mutation of chosen) {
  const path = join(web, mutation.file);
  const original = readFileSync(path, "utf8");
  const occurrences = original.split(mutation.from).length - 1;
  if (occurrences !== 1) {
    notRun.push(`${mutation.id}: the anchor appears ${occurrences} times, not once`);
    console.log(`SKIP  ${mutation.id} (anchor matched ${occurrences} times)`);
    continue;
  }

  inFlight.set(path, original);
  writeFileSync(path, original.replace(mutation.from, mutation.to));
  try {
    const run = mutation.runner === "vitest"
      ? spawnSync("npx", ["vitest", "run", "-t", mutation.grep],
                  { cwd: web, encoding: "utf8", timeout: 180_000 })
      : spawnSync("npx",
                  ["playwright", "test", "--grep", mutation.grep, "--reporter", "line"],
                  { cwd: web, encoding: "utf8", timeout: 180_000 });
    const output = `${run.stdout ?? ""}${run.stderr ?? ""}`;
    const ranSomething = !/No tests found|No test files found/.test(output)
      && !/Tests {2}no tests/.test(output);
    if (!ranSomething) {
      notRun.push(`${mutation.id}: --grep "${mutation.grep}" matched no test`);
      console.log(`SKIP  ${mutation.id} (grep matched no test)`);
    } else if (run.status !== 0) {
      caught += 1;
      console.log(`ok    ${mutation.id} -- caught`);
    } else {
      gaps.push(`${mutation.id}: ${mutation.why}`);
      console.log(`GAP   ${mutation.id} -- the suite stayed green`);
    }
  } finally {
    writeFileSync(path, original);
    inFlight.delete(path);
  }
}

console.log(
  `\n${caught}/${chosen.length} mutations caught` +
    (gaps.length ? `\n\nUNCAUGHT:\n  ${gaps.join("\n  ")}` : "") +
    (notRun.length ? `\n\nNOT RUN:\n  ${notRun.join("\n  ")}` : ""),
);
process.exit(gaps.length === 0 && notRun.length === 0 ? 0 : 1);
