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
    id: "nav-gate",
    why: "a navigation entry must be present exactly when following it would work",
    file: "src/app/layout.tsx",
    from: "{ href: \"/organization\", label: \"nav.organization\", allowed: organization.allowed },",
    to: "{ href: \"/organization\", label: \"nav.organization\", allowed: true },",
    grep: "gets no navigation entry",
  },
  {
    id: "org-empty-entity",
    why: "a tenant with no legal entity cannot be invoiced, so the page has to say so",
    file: "src/app/organization/page.tsx",
    from: "        <Alert tone=\"info\">{text(\"org.noEntities\")}</Alert>",
    to: "        <ul />",
    grep: "no legal entity rather than leaving a blank",
  },
  {
    id: "org-identifier-dir",
    why: "an IANA zone inside Arabic text reads as a different zone without dir=ltr",
    file: "src/app/organization/page.tsx",
    from: "                        <span className=\"data\" dir=\"ltr\">\n                          {location.timezone}",
    to: "                        <span className=\"data\">\n                          {location.timezone}",
    grep: "keeps the identifiers left-to-right",
  },
  {
    id: "org-tree-orphans",
    why: "a site whose brand is missing from the read must be shown, not dropped",
    file: "src/lib/organization.ts",
    from: "    orphanLocations: locations.filter((location) => !brandIds.has(location.brand_id)),",
    to: "    orphanLocations: [],",
    runner: "vitest",
    grep: "parent is missing",
  },
  {
    id: "member-mask-blank",
    why: "a withheld field must be marked, because a blank reads as 'there was nothing here'",
    file: "src/components/withheld.tsx",
    from: "        {t(locale, \"member.withheld\")}",
    to: "        {\"\"}",
    grep: "marks a masked identity field as withheld",
  },
  {
    id: "member-health-remedy",
    why: "a health field needs AAL 3, which nothing in this build reaches, so offering a "
      + "step-up would send somebody looking for a key the product cannot check",
    file: "src/app/people/[personId]/page.tsx",
    from: "                      ? \"member.withheldHealth\"\n                      : \"member.withheldIdentity\"",
    to: "                      ? \"member.withheldIdentity\"\n                      : \"member.withheldIdentity\"",
    grep: "cannot be read by anybody",
  },
  {
    id: "note-health-remedy",
    why: "a health note's body is unreadable by anybody in this build, like the field, and "
      + "the two branches are separate code with separate tests",
    file: "src/app/people/[personId]/page.tsx",
    from: "            ? \"member.withheldHealth\"\n            : \"member.withheldIdentity\"",
    to: "            ? \"member.withheldIdentity\"\n            : \"member.withheldIdentity\"",
    grep: "keeps a health note visible as a note",
  },
  {
    id: "member-sections-dropped",
    why: "a section with no module behind it must be named, not rendered as an empty list",
    file: "src/lib/people.ts",
    from: "    unavailable: entries\n      .filter(([, source]) => source.startsWith(\"unavailable:\"))",
    to: "    unavailable: ([] as [string, string][])\n      .filter(([, source]) => source.startsWith(\"unavailable:\"))",
    grep: "names the sections no module in this build can answer",
  },
  {
    id: "dedup-score-alone",
    why: "a duplicate score with no signals behind it is not something to destroy a record on",
    file: "src/app/people/page.tsx",
    from: "                    {candidate.signals.join(\", \")}",
    to: "                    {\"\"}",
    grep: "score and the signals behind it",
  },
  {
    id: "stepup-cookie",
    why: "MOD-007 revokes the session it steps up from, so not replacing the cookie is a "
      + "sign-out dressed as a success",
    file: "src/app/step-up/actions.ts",
    from: "    jar.set(SESSION_COOKIE, token, {",
    to: "    void jar; void ((_unused) => _unused)({",
    grep: "keeps the reader signed in",
  },
  {
    id: "stepup-open-redirect",
    why: "a `next` arrives in a link, so following it anywhere is an open redirect on the one "
      + "page where somebody has just typed a credential",
    file: "src/lib/navigation.ts",
    from: '  if (candidate.startsWith("//") || candidate.startsWith("/\\\\")) return HOME;',
    to: "  // guard removed",
    grep: "never to another host",
  },
  {
    id: "stepup-factor",
    why: "a password session cannot raise itself with another password, so asking for one is a "
      + "refusal the reader cannot act on",
    file: "src/app/step-up/page.tsx",
    from: '      ? "recovery_code"\n      : "password";',
    to: '      ? "password"\n      : "password";',
    grep: "asks for a recovery code",
  },
  {
    id: "stepup-unreachable",
    why: "level 3 needs a hardware authenticator this build cannot verify, so offering a field "
      + "sends somebody looking for a key the product cannot check",
    file: "src/app/step-up/page.tsx",
    from: "  if (!asked.reachable) {",
    to: "  if (false) {",
    grep: "a level nobody can reach",
  },
  {
    id: "member-stepup-offer",
    why: "naming a remedy and not offering it is the dead end MOD-007's own review records",
    file: "src/app/people/[personId]/page.tsx",
    from: "            {text(\"member.raiseSession\")}",
    to: "            {\"\"}",
    grep: "is offered where the refusal is",
  },
  {
    id: "perms-chain-caveat",
    why: "a hash chain that reports verified with no caveat is the more misleading of its two "
      + "answers: it detects editing, not truncation by somebody who moves the head",
    file: "src/app/permissions/page.tsx",
    from: "                {text(\"perms.chainCaveat\")}",
    to: "                {\"\"}",
    grep: "never without its caveat",
  },
  {
    id: "perms-audit-gate",
    why: "an empty audit table reads as 'nothing has been refused', which is a different fact "
      + "from 'you may not see what has been'",
    file: "src/app/permissions/page.tsx",
    from: "        {!mayAudit.allowed ? (",
    to: "        {false ? (",
    grep: "refused each block",
  },
  {
    id: "perms-permission-dir",
    why: "a permission name is an identifier, and the bidi algorithm reorders it inside an "
      + "Arabic page into a different string",
    file: "src/app/permissions/page.tsx",
    from: "                        <span className=\"data\" dir=\"ltr\">\n                          {entry.action}",
    to: "                        <span className=\"data\">\n                          {entry.action}",
    grep: "left-to-right inside an Arabic document",
  },
  {
    id: "perms-grant-is-not-a-session",
    why: "a permission listed is still refused when the action needs a stronger sign-in, which "
      + "is MOD-014's 'a grant is not a session' finding on a page that lists grants",
    file: "src/app/permissions/page.tsx",
    from: "          {text(\"perms.mineLead\")}",
    to: "          {\"\"}",
    grep: "at the scope the server derived",
  },
  {
    id: "fleet-attention-rule",
    why: "'needs somebody' is a device in service that has gone quiet, not every device that "
      + "is not online -- listing the others is how an alert channel gets muted",
    file: "src/app/fleet/page.tsx",
    from: "  const attention = new Set(fleet.needs_attention);",
    to: "  const attention = new Set(fleet.devices.filter((d) => d.reachability !== \"online\").map((d) => d.device_id));",
    grep: "an incident",
  },
  {
    id: "fleet-commissioning-denominator",
    why: "a list of only the missing tests cannot be told from a list of everything when "
      + "nothing is missing, and the question is what is left before the door can open",
    file: "src/app/fleet/[deviceId]/page.tsx",
    from: "            {commissioning(device.outstanding_tests).map(({ test, done }) => (",
    to: "            {commissioning(device.outstanding_tests).filter((entry) => !entry.done).map(({ test, done }) => (",
    grep: "nothing outstanding",
  },
  {
    id: "device-credential-disclosure",
    why: "no signature is verified anywhere in this build, and MOD-022 opens doors on that "
      + "identity -- a page that omits it presents a fingerprint as a key",
    file: "src/app/fleet/[deviceId]/page.tsx",
    from: "          {text(\"device.certificatesLead\")}",
    to: "          {\"\"}",
    grep: "not a key anything checks",
  },
  {
    id: "device-not-found",
    why: "a malformed id in a URL is a bad link, not a broken product",
    file: "src/app/fleet/[deviceId]/page.tsx",
    from: "    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) {",
    to: "    if (error instanceof ApiError && error.status === 404) {",
    grep: "malformed device id",
  },
  {
    id: "ops-backlog-explained",
    why: "a delivery nobody handles accumulates by design, and a number rendered bare lets "
      + "somebody conclude a consumer is reading it",
    file: "src/app/operations/page.tsx",
    // **The branch the fixture actually renders.** It subscribes a consumer, so the page
    // takes the `backlogUnexpected` arm -- and a mutation aimed at the arm nobody renders
    // changes nothing a reader sees, which the sweep would rightly report as uncaught. The
    // same trap as the fetch-guard-versus-rendering-guard one recorded below.
    from: "                  : text(\"ops.backlogUnexpected\")}",
    to: "                  : \"\"}",
    grep: "a delivery nobody handles is expected",
  },
  {
    id: "ops-relay-verdict",
    why: "the relay running is what makes a pending event transient rather than a fault, and "
      + "a page that never says so leaves the reader to guess which it is",
    file: "src/app/operations/page.tsx",
    from: "              ) : relay === \"running\" ? (",
    to: "              ) : false ? (",
    grep: "says the relay is running",
  },
  // No mutation for `ops.noRuns`, deliberately: it renders only for a job with no runs, and
  // the fixture's last step runs the worker, so every job has one and the string is
  // unreachable in the browser. A mutation nothing can catch is a gap to name rather than to
  // hide -- the decision behind the label is `relayVerdict`, which has eight cases in
  // `tests/component/operations-worker.test.ts`, and the e2e asserts the other direction:
  // after a real tick, no job reads as never run.
  {
    id: "ops-worker-run-proves-what",
    why: "a run is recorded by the worker itself, so a board that does not say so lets a "
      + "reader take it as proof the job's effect reached something outside the database",
    file: "src/app/operations/page.tsx",
    from: "                {jobs.worker_gaps.map((gap) => (",
    to: "                {([] as string[]).map((gap) => (",
    grep: "says a burst of runs after a restart is expected",
  },
  {
    id: "ops-deadletter-gate",
    why: "an empty dead-letter table somebody may not see reads as 'nothing is quarantined', "
      + "which is a different fact",
    file: "src/app/operations/page.tsx",
    // **The rendering guard, not the fetch guard.** The first version of this mutation
    // removed the condition on the *request* -- which changes nothing a reader sees, because
    // `Gated` still refuses, so the sweep reported it uncaught and was right to.
    from: "  if (!gate.allowed) {",
    to: "  if (false) {",
    grep: "refused each block rather than shown four empty ones",
  },
  {
    id: "ops-objective-honesty",
    why: "nothing evaluates an objective on a schedule, so an empty list is honest rather "
      + "than reassuring and the page has to say which",
    file: "src/i18n/locale.ts",
    from: "    \"ops.noObjectives\": \"No objective is defined. Nothing evaluates one on a schedule either, so an objective nobody runs raises no alert — which is why an empty list here is honest rather than reassuring.\",",
    to: "    \"ops.noObjectives\": \"No objective is defined.\",",
    grep: "raises no alert",
  },
  {
    id: "fleet-freshness-disclosure",
    why: "reachability is worked out when the page loads and nothing records it, so a board "
      + "that does not say so claims a freshness the product does not have",
    file: "src/i18n/locale.ts",
    from: "    \"fleet.lead\": \"Every device at this tenant, what it can do, and whether it is reachable. Reachability is worked out from the last report a device sent — nothing stores it and nothing asks a device for it, so this is what was true when the page was loaded. A scheduled sweep does announce a device in service that has gone quiet; it changes nothing on this board.\",",
    to: "    \"fleet.lead\": \"Every device at this tenant, what it can do, and whether it is reachable.\",",
    grep: "says reachability is worked out rather than stored",
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
