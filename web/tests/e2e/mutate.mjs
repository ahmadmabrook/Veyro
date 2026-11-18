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
 * afterwards whatever happens, including on a crash.
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
    from: "  if (missing.tenant || missing.identifier || missing.password) {\n    return { error: null, missing, ...echo };\n  }",
    to: "  if (missing.tenant || missing.identifier || missing.password) {\n    return { error: null, missing: { tenant: false, identifier: false, password: false }, ...echo };\n  }",
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
    id: "signed-in-redirect",
    why: "a signed-in caller must not be served the sign-in form again",
    file: "src/app/login/page.tsx",
    from: '  if (await currentSession()) redirect("/");',
    to: "",
    grep: "already-signed-in caller",
  },
];

const only = process.argv[2];
const chosen = only ? MUTATIONS.filter((m) => m.id.includes(only)) : MUTATIONS;

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

  writeFileSync(path, original.replace(mutation.from, mutation.to));
  try {
    const run = spawnSync(
      "npx",
      ["playwright", "test", "--grep", mutation.grep, "--reporter", "line"],
      { cwd: web, encoding: "utf8", timeout: 180_000 },
    );
    const output = `${run.stdout ?? ""}${run.stderr ?? ""}`;
    const ranSomething = !/No tests found/.test(output);
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
  }
}

console.log(
  `\n${caught}/${chosen.length} mutations caught` +
    (gaps.length ? `\n\nUNCAUGHT:\n  ${gaps.join("\n  ")}` : "") +
    (notRun.length ? `\n\nNOT RUN:\n  ${notRun.join("\n  ")}` : ""),
);
process.exit(gaps.length === 0 && notRun.length === 0 ? 0 : 1);
