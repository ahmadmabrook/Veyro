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
    from: '          tabIndex={0}\n          aria-labelledby="permissions-heading"',
    to: "          tabIndex={0}\n",
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
    id: "schedule-reason-marked",
    why: "a withheld reason rendered as an empty cell is indistinguishable from one nobody "
      + "wrote, and an absent entry says nothing changed -- which is a different fact",
    file: "src/app/schedule/[sessionId]/page.tsx",
    from: "                  {change.reason_masked ? (",
    to: "                  {false ? (",
    grep: "sees a change's reason withheld rather than absent",
  },
  {
    id: "schedule-step-up-only-when-a-remedy",
    why: "offering a step-up to a session that does not hold the permission at any assurance "
      + "sends somebody looking for a second factor that would change nothing",
    file: "src/app/schedule/[sessionId]/page.tsx",
    from: "                {mayChange.step_up_required ? (",
    to: "                {true ? (",
    grep: "sees a change's reason withheld rather than absent",
  },
  {
    id: "schedule-held-is-not-a-counter",
    why: "there is no held_count anywhere in MOD-019 and the absence is swept for, so a "
      + "reader who takes these for stored counters is reasoning about a mechanism that "
      + "does not exist",
    file: "src/app/schedule/page.tsx",
    from: "            {text(\"schedule.heldExplained\")}",
    to: "            {\"\"}",
    grep: "says what Taken and Free are",
  },
  {
    id: "schedule-former-resources-kept-apart",
    why: "a substituted instructor's hold is kept rather than deleted, and one list with a "
      + "flag puts a coach who was sent home back on the roster",
    file: "src/app/schedule/[sessionId]/page.tsx",
    from: "          <Resources list={session.former_resources} timezone={session.timezone} />",
    to: "          <Resources list={[]} timezone={session.timezone} />",
    grep: "shows what a session used to hold",
  },
  {
    id: "member-two-reasons",
    why: "four of the sections named here belong to modules that have since been built, so a "
      + "reader who takes 'this projection does not read it' for 'the product does not have "
      + "it' has been told the wrong thing about their own build",
    file: "src/app/people/[personId]/page.tsx",
    from: "          {text(\"member.unavailableWhy\")}",
    to: "          {\"\"}",
    grep: "does not call a module that exists one that was never built",
  },
  {
    id: "fleet-count-labelled",
    why: "a bare number after a timestamp reads as part of it, and the count is the only "
      + "thing on that line which is not a time",
    file: "src/app/fleet/page.tsx",
    from: "          {text(\"fleet.counted\")}",
    to: "          {\"\"}",
    grep: "labels the count and the clock",
  },
  {
    id: "utc-is-marked",
    why: "an instant with no zone was merely ambiguous while every screen rendered one that "
      + "way, and became misleading the day the schedule board started converting",
    file: "src/lib/time.ts",
    from: "  return `${instant.slice(0, 10)} ${instant.slice(11, 16)} UTC`;",
    to: "  return `${instant.slice(0, 10)} ${instant.slice(11, 16)}`;",
    grep: "labels the count and the clock",
  },
  {
    id: "schedule-local-time",
    why: "MOD-019 stores a UTC instant and the local facts it came from because neither is "
      + "derivable from the other, so slicing the ISO string shows a class at 18:00 in Amman "
      + "as 15:00 under a heading promising the site's own timezone",
    file: "src/lib/time.ts",
    from: "      time: new Intl.DateTimeFormat(\"en-GB\", {",
    to: "      time: ((x) => ({ format: () => instant.slice(11, 16) }))(new Intl.DateTimeFormat(\"en-GB\", {",
    grep: "renders every session in the site's timezone",
  },
  {
    id: "phone-table-scrolls-inside-itself",
    why: "a page that scrolls sideways hides its own right-hand edge, so a column a reader "
      + "cannot see reads as a column that does not exist",
    file: "src/app/globals.css",
    from: "  table {\n    display: block;",
    to: "  table.not-a-table {\n    display: block;",
    grep: "the operations board does not scroll sideways",
  },
  {
    id: "phone-facts-can-shrink",
    why: "a grid track's implicit minimum is min-content, so a value with no break "
      + "opportunity -- a comma-separated list of dotted permission names -- makes the column "
      + "wider than the page and nothing about the container can stop it",
    file: "src/app/globals.css",
    from: ".facts dd {\n  overflow-wrap: anywhere;\n}",
    to: ".facts dd {\n  overflow-wrap: normal;\n}",
    grep: "the permissions page does not scroll sideways",
  },
  {
    id: "config-unset-is-a-sentence",
    why: "an unset key reads back as its own default, which is indistinguishable from a "
      + "tenant that published the same value unless the scope is rendered",
    file: "src/app/configuration/page.tsx",
    from: "        {isUnset(resolved) ? (",
    to: "        {false ? (",
    grep: "says nobody set the key nobody set",
  },
  {
    id: "config-flag-reason",
    why: "`off` could be a kill switch, a flag nobody enabled, or a rule that sent this "
      + "subject to the control arm, and an operator in an incident needs to know which",
    file: "src/app/configuration/page.tsx",
    from: "      <td style={cell}>{text(label[reason])}</td>",
    to: "      <td style={cell}>{\"\"}</td>",
    grep: "says why a flag is off",
  },
  {
    id: "config-kill-switch-marked",
    why: "a kill switch outranks every targeting rule and is somebody's deliberate stop, "
      + "which is the one flag state worth an alarm rather than a row",
    file: "src/app/configuration/page.tsx",
    from: "              <Alert tone=\"error\">{text(\"config.killSwitchEngaged\")}</Alert>",
    to: "              <></>",
    grep: "marks a kill switch",
  },
  {
    id: "config-flags-are-per-subject",
    why: "there is no route that lists flags without evaluating them, so a flag missing from "
      + "the board is not a flag that is absent",
    file: "src/app/configuration/page.tsx",
    from: "              {text(\"config.noFlagList\")}",
    to: "              {\"\"}",
    grep: "no route that lists flags",
  },
  {
    id: "config-flag-block-gated-on-its-own",
    why: "the flag read is its own permission, so a reader may hold the registry read and "
      + "not it -- and an empty flag board reads as a tenant with no flags",
    file: "src/app/configuration/page.tsx",
    from: "        {!mayFlags.allowed ? (",
    to: "        {false ? (",
    grep: "is refused both blocks",
  },
  {
    id: "roster-gated-on-its-own",
    why: "the roster belongs to MOD-020 and the seats to MOD-019, so a reader may hold one "
      + "permission and not the other -- and 'nobody is booked' is a different fact from "
      + "'you may not see who is'",
    file: "src/app/schedule/[sessionId]/page.tsx",
    from: "        {!mayRoster.allowed ? (",
    to: "        {false ? (",
    grep: "is refused the roster, because it belongs to another module",
  },
  {
    id: "roster-seats-are-the-schedules",
    why: "there is no roster table and no cached total, so a reader who counted the rows "
      + "would disagree with the seat count the first time a hold had no booking behind it",
    file: "src/app/schedule/[sessionId]/page.tsx",
    from: "              {text(\"roster.capacityIsElsewhere\")}",
    to: "              {\"\"}",
    grep: "says whose seats they are",
  },
  {
    id: "roster-not-checked-in-is-a-sentence",
    why: "a check-in is recorded rather than performed, so a blank cell reads as a missing "
      + "value where the fact is that nobody has claimed one",
    file: "src/i18n/locale.ts",
    from: "    \"roster.notCheckedIn\": \"not yet\",",
    to: "    \"roster.notCheckedIn\": \"\",",
    grep: "says whose seats they are",
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
    id: "integrations-obligations-bind-critical",
    why: "the check was keyed on `live_critical`, which the column never holds, so every "
      + "install reported the written obligations did not apply -- including one carrying "
      + "traffic without its exit plan",
    file: "src/lib/integrations.ts",
    from: 'export const OBLIGED_CRITICALITY = "critical";',
    to: 'export const OBLIGED_CRITICALITY = "live_critical";',
    runner: "vitest",
    grep: "the value the column actually holds",
  },
  {
    id: "integrations-page-asks-the-library",
    why: "the page re-derived the criticality comparison for its own cell while the library "
      + "answered the banner, so fixing one left the other wrong -- the banner named an "
      + "install carrying traffic without its obligations while the row said they did not "
      + "apply",
    file: "src/app/integrations/page.tsx",
    from: "                        {!obligationsApply(install) ? (",
    to: '                        {install.criticality !== "live_critical" ? (',
    grep: "names the critical install missing a written obligation",
  },
  {
    id: "integrations-counts-are-reported-not-observed",
    why: "nothing in this build calls a provider, so a record count is a caller's word -- "
      + "and a number with no caveat reads as data that moved",
    file: "src/lib/integrations.ts",
    from: "  return run.records_read > 0 || run.records_written > 0;",
    to: "  return false;",
    grep: "counts were reported rather than observed",
  },
  {
    id: "integrations-dead-run-needs-somebody",
    why: "a failed run retries itself; a dead one burned its budget and needs an attributed "
      + "release before it goes back in front of a provider",
    file: "src/lib/integrations.ts",
    from: '  return run.status === "dead";',
    to: '  return run.status === "failed";',
    runner: "vitest",
    grep: "dead and not merely failed",
  },
  {
    id: "notify-reason-is-a-sentence",
    why: "`no_preference_stops_it` tells a reader nothing they can act on -- 'a rule id is "
      + "not a reason', which MOD-005's board learned about flags",
    file: "src/lib/notifications.ts",
    from: "  return REASON_KEYS[reason] ?? null;",
    to: "  return null;",
    grep: "decision reason as a sentence",
  },
  {
    id: "notify-says-nothing-sends",
    why: "every notification sits at `requested` for ever because no dispatcher exists, and "
      + "a board rendering that as a queue making progress claims an outbound path there is "
      + "none of",
    file: "src/app/notifications/page.tsx",
    from: '        <Alert tone="warning">{text("notify.nothingSends")}</Alert>',
    to: "        {null}",
    grep: "leads with the fact that nothing sends",
  },
  {
    id: "notify-only-an-unsubscribe-can-be-lifted",
    why: "a bounce is the channel's judgement about deliverability, and a tenant that could "
      + "clear one would be choosing to keep sending to an address that rejected them",
    file: "src/lib/notifications.ts",
    from: '  return suppression.reason === "unsubscribed";',
    to: "  return true;",
    runner: "vitest",
    grep: "true only for an unsubscribe",
  },
  {
    id: "notify-suppressed-is-not-waiting",
    why: "a suppression is a decision the module made and recorded a reason for; counting it "
      + "as waiting would inflate the one number on the page that means nothing sends",
    file: "src/lib/notifications.ts",
    from: '  if (notification.status === "suppressed") return "decided";',
    to: '  if (notification.status === "suppressed") return "no_dispatcher";',
    runner: "vitest",
    grep: "suppressed message decided",
  },
  {
    id: "privacy-residue-is-grouped",
    why: "371 rows of column names is a wall rather than a disclosure, and the grouping is "
      + "what makes the shape of what survives legible at all",
    file: "src/lib/privacy.ts",
    from: "    const prefix = entry.table.includes(\"_\")",
    to: "    const prefix = false",
    runner: "playwright",
    grep: "groups the residue by area",
  },
  {
    id: "privacy-emphasis-is-not-asterisks",
    why: "the registry's reasons were written where `**` is emphasis, in a Python module a "
      + "developer reads -- printed literally they are punctuation nobody wrote for a reader",
    file: "src/components/prose.tsx",
    from: "        segment.kind === \"strong\" ? (",
    to: "        false ? (",
    grep: "emphasis as emphasis",
  },
  {
    id: "privacy-live-hold-is-told-from-a-released-one",
    why: "releasing a hold is the single act that un-blocks destruction of preserved "
      + "evidence, so a board that showed only live holds would hide the one with the most "
      + "consequence attached",
    file: "src/lib/privacy.ts",
    from: '  return api("/privacy/legal-holds?include_released=true");',
    to: '  return api("/privacy/legal-holds");',
    grep: "live legal hold from a released one",
  },
  {
    id: "privacy-queue-is-ordered-by-deadline",
    why: "a regulator-facing deadline is the one number on that screen with a consequence "
      + "attached, and a queue in insertion order buries the request already past it",
    file: "src/lib/privacy.ts",
    from: "    .sort((a, b) => a.due_at.localeCompare(b.due_at));",
    to: "    .sort((a, b) => b.due_at.localeCompare(a.due_at));",
    grep: "overdue request first",
  },
  {
    id: "privacy-says-nothing-sweeps",
    why: "the retention decision exists and no job calls it, so a list of policies with no "
      + "such sentence reads as a schedule that runs",
    file: "src/app/privacy/page.tsx",
    from: '            {text("privacy.nothingSweeps")}',
    to: "            {null}",
    grep: "nothing deletes on the retention schedule",
  },
  {
    id: "catalog-promotion-needs-window-and-status",
    why: "nothing retires a promotion when its window closes, so a board showing the status "
      + "alone says a campaign is running when it ended in February",
    file: "src/lib/catalog.ts",
    from: '  return promotion.status === "active" && promotion.in_window;',
    to: '  return promotion.status === "active";',
    runner: "vitest",
    grep: "needs both the status and the window",
  },
  {
    id: "catalog-percent-is-not-basis-points",
    why: "1000 basis points is ten percent, and rendering the stored number is off by a "
      + "hundred -- the units mistake this build's money rules exist to prevent",
    file: "src/lib/catalog.ts",
    from: "    return { kind: \"percent\", percent: promotion.percent_bp / 100 };",
    to: "    return { kind: \"percent\", percent: promotion.percent_bp };",
    runner: "vitest",
    grep: "converts basis points",
  },
  {
    id: "catalog-sellable-needs-an-active-book",
    why: "a price in its window in a book nobody activated prices nothing, so a published "
      + "product with only that price is a till that cannot sell it",
    file: "src/lib/catalog.ts",
    from: '      p.price_book_status === "active" &&',
    to: "",
    runner: "vitest",
    grep: "price whose book was never activated",
  },
  {
    id: "catalog-says-a-row-is-not-the-resolved-price",
    why: "three things decide what a sale costs and a stored row answers one -- a figure "
      + "without that sentence reads as a promise only the sale can make",
    file: "src/app/catalog/page.tsx",
    from: '              {text("catalog.notThePrice")}',
    to: "              {null}",
    grep: "is not the resolved price",
  },
  {
    id: "finance-closing-period-takes-no-trade",
    why: "`closing` is the state that surprises -- it admits the close's own entries and no "
      + "trade at all -- so a board reasoning from the status alone gets the one case that "
      + "matters wrong",
    file: "src/lib/ledger.ts",
    from: '  return periods.filter((p) => p.status === "closing" || p.status === "reopened");',
    to: '  return periods.filter((p) => p.status === "reopened");',
    runner: "vitest",
    grep: "names a closing period",
  },
  {
    id: "finance-unbalanced-is-lost-rows",
    why: "every journal balances by a constraint the database enforces, so a difference means "
      + "rows are missing rather than rounded -- a surface that said 'these columns differ' "
      + "would send somebody looking for the wrong thing",
    file: "src/lib/ledger.ts",
    // **The first version of this mutation was a no-op**, which the sweep reported as a gap:
    // it inserted a branch guarded by `difference_minor === 0`, and the test's own case has a
    // difference of -4500, so nothing changed. A mutation that changes nothing is not
    // evidence -- the trap the backend rules file names, met here in the web half.
    from: '    : { kind: "lost_rows", differenceMinor: balance.difference_minor };',
    to: '    : { kind: "balanced", differenceMinor: 0 };',
    runner: "vitest",
    grep: "calls an unbalanced ledger lost rows",
  },
  {
    id: "finance-names-the-legal-entity",
    why: "a trial balance is per legal entity and per currency, and the block's own sentence "
      + "says so -- rendering only the currency is the defect that sentence warns about",
    file: "src/app/finance/page.tsx",
    from: "                  ?.registered_name ?? (",
    to: "                  ?.nothing_here ?? (",
    grep: "names the legal entity",
  },
  {
    id: "finance-marks-a-retired-account",
    why: "a retired account stays on the trial balance because a retired account with a "
      + "balance is the row somebody needs to notice -- unmarked, it reads as a live one",
    file: "src/app/finance/page.tsx",
    from: '                            : ` · ${text("finance.retired")}`}',
    to: "                            : ``}",
    grep: "marks a retired account",
  },
  {
    id: "finance-closing-is-named-as-needing-somebody",
    why: "an accountant who began a close has deliberately stopped that entity's postings, "
      + "and the banner is the only place the product says so",
    file: "src/app/finance/page.tsx",
    from: "        {attention.length > 0 ? (",
    to: "        {false ? (",
    grep: "middle of closing",
  },
  {
    id: "finance-absence-is-not-open",
    why: "the lock is enforced per period row, so a month with no row has never been opened "
      + "-- a board that implied the absent months were open would say the opposite of true",
    file: "src/app/finance/page.tsx",
    from: '            {text("finance.absenceMeansNeverOpened")}',
    to: "            {null}",
    grep: "has never been opened",
  },
  {
    id: "membership-blocks-ask-their-own-gate",
    why: "three permissions, three blocks -- a reader may hold the person read and none of "
      + "MOD-017, and 'this member has no invoices' is a different fact from 'you may not "
      + "see them'",
    file: "src/components/membership-panels.tsx",
    from: "  if (allowed) return <>{children}</>;",
    to: "  if (true) return <>{children}</>;",
    grep: "is told each block is refused",
  },
  {
    id: "membership-money-uses-the-currency-exponent",
    why: "an amount is an integer count of minor units and JOD has three of them, so a "
      + "hard-coded /100 renders 45.000 dinars as 450.00 -- and every assertion about the "
      + "word 'price' passes either way",
    file: "src/lib/membership.ts",
    from: '    return formatMoney(minor, currency, "latn", "en");',
    to: "    return `${(minor / 100).toFixed(2)} ${currency}`;",
    grep: "renders the agreed price",
  },
  {
    id: "membership-credit-note-is-not-outstanding",
    why: "a credit note is stored positive and is a reduction, so counting one as outstanding "
      + "moves the total the wrong way by twice its value",
    file: "src/lib/membership.ts",
    from: '  return invoice.document_kind === "invoice" && !SETTLED.has(invoice.payment_status);',
    to: "  return !SETTLED.has(invoice.payment_status);",
    runner: "vitest",
    grep: "never counts a credit note",
  },
  {
    id: "membership-facts-are-label-and-value-rows",
    why: "`.facts` is a two-column grid whose items are the dt and dd themselves, so a div "
      + "around each pair is valid HTML that puts both labels on one row with their values "
      + "beneath -- a rendering defect no assertion about the text can see",
    file: "src/components/membership-panels.tsx",
    from: '        <dt className="muted">{text("membership.accounts")}</dt>',
    to: '        <div><dt className="muted">{text("membership.accounts")}</dt></div>\n'
      + '        <div><dt className="muted">{text("membership.outstanding")}</dt></div>',
    grep: "label and value, not side by side",
  },
  {
    id: "membership-two-numbers-disclosed",
    why: "two human-facing member numbers from two modules sit on one page with nothing "
      + "relating them, and a front desk asking for 'your membership number' can be handed "
      + "either",
    file: "src/components/membership-panels.tsx",
    from: '        {text("membership.twoNumbers")}',
    to: "        {null}",
    grep: "two member numbers on this page",
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
