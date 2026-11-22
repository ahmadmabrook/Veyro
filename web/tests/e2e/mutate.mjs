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
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
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
 * of the test is that it needs no browser and no fixture. `"node"` is the foundation layer,
 * `tests/unit/`, which runs on Node's own test runner: it had no runner here until a
 * mutation was pointed at one of its assertions and came back uncaught, because `vitest`
 * does not collect those files and so reported no failure rather than no test.
 */
const MUTATIONS = [
  {
    id: "dispute-rejected-filing",
    why: "an invoice whose fiscal filing was rejected has only half the evidence the canvas's"
      + " line names, and ticking both puts an accountant in front of a scheme expecting a"
      + " reference that does not exist",
    file: "src/lib/disputes.ts",
    from: '      note: dispute.fiscal_status === "rejected"\n'
      + '        ? "dispute.ev.filingRejected"\n'
      + '        : "dispute.ev.notFiled",',
    to: '      note: undefined,',
    grep: "does not tick a rejected fiscal filing",
    runner: "vitest",
  },
  {
    id: "dispute-refusal-as-absence",
    why: "a permission refusal rendered as an absence tells an accountant the gym cannot"
      + " prove attendance it can prove, which is the worst sentence this screen could say",
    file: "src/lib/disputes.ts",
    from: '    out.push({ key: "attendance", state: "refused", label: "dispute.ev.attendance",\n'
      + '               note: "dispute.ev.attendanceRefused" });',
    to: '    out.push({ key: "attendance", state: "missing", label: "dispute.ev.attendance",\n'
      + '               note: "dispute.ev.attendanceRefused" });',
    grep: "tells a refusal from an absence",
    runner: "vitest",
  },
  {
    id: "dispute-statement-ticked",
    why: "nothing in this build holds a written statement, and ticking the line would be a"
      + " piece of evidence claimed that does not exist",
    file: "src/lib/disputes.ts",
    from: '  out.push({ key: "statement", state: "missing", label: "dispute.ev.statement",\n'
      + '             note: "dispute.ev.statementIsYours" });',
    to: '  out.push({ key: "statement", state: "have", label: "dispute.ev.statement",\n'
      + '             note: "dispute.ev.statementIsYours" });',
    grep: "leaves the written statement to the operator",
  },
  {
    id: "recovery-unsorted",
    why: "the workspace's whole argument is that the set is sorted; a page that called every"
      + " case one decision would invite one batch action over rows it does the wrong thing to",
    file: "src/lib/recovery.ts",
    from: "  if (present.length === 1) {",
    to: "  if (present.length >= 1) {",
    grep: "says these are NOT one decision",
  },
  {
    id: "recovery-card-detail",
    why: "there is no card brand and no last four in this build, and a row implying one"
      + " would be the fabricated-evidence shape in the place paragraph 1597 is about",
    file: "src/app/payments/recovery/page.tsx",
    from: '{failure === null\n                            ? one.failure_code\n'
      + '                            : text(failure)}',
    to: '{"Card expired \u00b7 Visa \u00b7\u00b7\u00b74417"}',
    grep: "the card detail the canvas draws is absent",
  },
  {
    id: "recovery-rendered-preview",
    why: "the preview is the template as authored; a filled example would read as a message"
      + " that exists, and the one value this build cannot supply is the payment link",
    file: "src/app/payments/recovery/page.tsx",
    from: '        <p className="ds-message" dir="auto">{template.body}</p>',
    to: '        <p className="ds-message" dir="auto">'
      + '{template.body.replace(/\\{\\{ link \\}\\}/, "veyro.link/p/8k2m")}</p>',
    grep: "previews the real template",
  },
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
    // **Repointed: the matrix moved to `/permissions` and kept its own short words.**
    // `describeGate` is the one that renders this cell -- `gateVerdict` in `@/lib/api`
    // answers the page-level banners -- and the order is load-bearing in both: an
    // insufficient assurance always sets `step_up_required`, and `reachable` is what tells
    // a level nobody can reach from one a stronger sign-in opens. Aiming at `api.ts`
    // reported this as a gap, which is the tell: a mutation whose test asserts the rendered
    // half while the mutation edits the other half.
    file: "src/app/permissions/page.tsx",
    from: '  if (!answer.reachable) return "gate.unreachable";\n  if (answer.step_up_required) return "gate.stepUp";',
    to: '  if (answer.step_up_required) return "gate.stepUp";\n  if (!answer.reachable) return "gate.unreachable";',
    grep: "says it is unavailable",
  },
  {
    id: "bidi-isolation",
    why: "a Latin identifier inside Arabic text must carry its own direction",
    // Repointed: the gate table moved to `/permissions` with the design migration.
    file: "src/app/permissions/page.tsx",
    from: '              render: (answer) => <span className="data" dir="ltr">{answer.action}</span>,',
    to: '              render: (answer) => <span className="data">{answer.action}</span>,',
    grep: "renders left-to-right",
  },
  {
    id: "table-name",
    why: "the permissions table must have an accessible name",
    // **Repointed, and the protection moved layers with it.** The hand-rolled table became
    // a `DataGrid`, which renders its own visually-hidden caption -- so dropping
    // `labelledBy` no longer removes the name, it restores the duplication the prop exists
    // to prevent: the heading said twice, invisible to a sighted reader and heard in full
    // by a screen-reader user. What catches it is the usage sweep rather than the browser.
    file: "src/app/permissions/page.tsx",
    from: '          labelledBy="gate-heading"',
    to: "",
    runner: "node",
    grep: "points at it rather than repeating it",
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
    why: "lg is mandatory at Touch and Spacious density -- the source calls 44px the minimum "
      + "target, not a stylistic option",
    file: "src/components/ds/button.tsx",
    from: '  if ((TOUCH_DENSITIES as readonly string[]).includes(density)) return "lg";',
    to: '  if (false) return "lg";',
    runner: "vitest",
    grep: "forces lg at the densities",
  },
  {
    id: "label-association",
    why: "a validation message must be associated with its field, not merely adjacent -- the "
      + "contract says the error text is referenced by the field and read on focus",
    file: "src/components/ds/field.tsx",
    from: "              aria-describedby={messageId}\n              aria-invalid={invalid || undefined}\n              required={required}\n              className=\"ds-field-input\"\n            />\n          )\n        )}",
    to: "              aria-invalid={invalid || undefined}\n              required={required}\n              className=\"ds-field-input\"\n            />\n          )\n        )}",
    grep: "names every missing field",
  },
  {
    id: "muster-disclaimer",
    why: "paragraph 4180's disclaimer must be on every occupancy read",
    file: "src/app/access/[zoneId]/page.tsx",
    from: "      <Banner severity=\"info\">{occupancy.detail}</Banner>",
    to: "",
    grep: "disclaimer next to the number",
  },
  {
    id: "access-gaps-hidden",
    why: "a zone must say what it cannot do rather than reading as fully capable",
    file: "src/app/access/[zoneId]/page.tsx",
    // Repointed: the anchor went stale when the code around it moved.
    from: "      {zone.access_gaps.length > 0 ? (",
    to: "        {false ? (",
    grep: "names what the zone cannot do",
  },
  {
    id: "no-policy-reads-blank",
    why: "a zone with no live policy must say so, not render an empty cell",
    file: "src/app/access/page.tsx",
    // **Repointed: the anchor went stale when this board moved to `DataGrid`.** The sweep is
    // the only thing that notices, and it reports it as NOT RUN rather than as a catch --
    // which is the right way round, because a mutation that cannot apply is a protection
    // with no evidence rather than one that passed.
    from: "                zone.live_policy_version === null ? (",
    to: "                false ? (",
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
    // Repointed: the anchor went stale when the code around it moved.
    from: "{ href: \"/organization\", label: \"nav.organization\", allowed: organization.allowed,",
    to: "{ href: \"/organization\", label: \"nav.organization\", allowed: true },",
    grep: "gets no navigation entry",
  },
  {
    id: "org-empty-entity",
    why: "a tenant with no legal entity cannot be invoiced, so the page has to say so",
    file: "src/app/organization/page.tsx",
    from: "        <Banner severity=\"info\">{text(\"org.noEntities\")}</Banner>",
    to: "        <ul />",
    grep: "no legal entity rather than leaving a blank",
  },
  {
    id: "org-identifier-dir",
    why: "an IANA zone inside Arabic text reads as a different zone without dir=ltr",
    file: "src/app/organization/page.tsx",
    // Repointed: the anchor went stale when the code around it moved.
    from: "                      <span className=\"data\" dir=\"ltr\">{location.timezone}</span>",
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
    // Repointed: the anchor went stale when the code around it moved.
    from: "                        ? \"member.withheldHealth\"\n                        : \"member.withheldIdentity\"",
    to: "                        ? \"member.withheldIdentity\"\n                        : \"member.withheldIdentity\"",
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
    // Repointed: the anchor went stale when the code around it moved.
    from: "                render: (candidate) => candidate.signals.join(\", \"),",
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
    // Repointed: the anchor went stale when the code around it moved.
    from: "                      <span className=\"data\" dir=\"ltr\">{entry.action}</span>",
    to: "                      <span className=\"data\">{entry.action}</span>",
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
    // Repointed: the anchor went stale when the code around it moved.
    from: "            <p className=\"muted\" style={{ margin: 0 }}>{text(\"member.unavailableWhy\")}</p>",
    to: "            <p className=\"muted\" style={{ margin: 0 }}>{\"\"}</p>",
    grep: "does not call a module that exists one that was never built",
  },
  {
    id: "fleet-count-labelled",
    why: "a bare number after a timestamp reads as part of it, and the count is the only "
      + "thing on that line which is not a time",
    file: "src/app/fleet/page.tsx",
    // Repointed, and **the occurrence matters**: `fleet.counted` is on this page twice and
    // the footer's is the one the test reads, because the header's count has its own label
    // beside it. An anchor that matched both was reported as ambiguous rather than run,
    // which is the harness refusing to guess.
    from: "          <span className=\"data\">{formatInteger(fleet.count, \"latn\")}</span>{\" \"}\n          {text(\"fleet.counted\")}",
    to: "          <span className=\"data\">{formatInteger(fleet.count, \"latn\")}</span>{\" \"}\n          {\"\"}",
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
    // **Re-pointed, because the document-level assertion stopped being able to prove this.**
    // Breaking the rule used to make seven surfaces overflow; it now makes none of them,
    // because every table here is either a `DataGrid` whose columns drop by priority until
    // it fits or a hand-rolled one at `width: 100%`. The rule is still correct and is
    // redundant on every page that exists, so the mutation came back uncaught -- a protection
    // nothing could prove. The collapse itself is directly measurable, so that is what is
    // measured now -- and it has to be measured on a *hand-rolled* table: a grid gets
    // `display: block` from the 599px collapse rule and the matrix is exempt, so pointing
    // this at a grid was still uncaught for a second reason.
    grep: "a hand-rolled table collapses as the design states",
  },
  {
    // **The live document-level protection, replacing one that nothing could prove.** This
    // slot held `.facts dd { overflow-wrap: anywhere }` against the same assertion, and that
    // came back uncaught for the reason one rule up plus one more: `contain: layout` on the
    // matrix's scroll wrapper now stops an overflowing descendant reaching the root at all,
    // so a value too wide for its track is contained before the document can see it. The
    // wrapper is what the assertion can still prove -- removing it overflows `/permissions`
    // by exactly the 125px the rules file records.
    id: "phone-matrix-overflow-is-contained",
    why: "the matrix scrolls inside its own wrapper and an overflowing descendant still "
      + "contributed to the document's scrollable area until `contain: layout` bounded it, "
      + "which is the one of the three containments that does not clip the focus ring",
    file: "src/app/globals.css",
    // Repointed: `contain: layout` is on two boxes now -- the matrix's scroll wrapper and
    // the week grid's, which learned the same lesson later. The anchor carries the line
    // after it so it names the matrix's.
    from: "  contain: layout;\n  border: 1px solid var(--color-border-default);",
    to: "  border: 1px solid var(--color-border-default);",
    grep: "the permissions page does not scroll sideways",
  },
  {
    // The matrix is the design's own exception -- "a column dropped from a matrix is a
    // comparison a reader gets wrong" -- so it keeps table layout where a grid collapses.
    // `display: block` on it is what let its sticky header escape to the document root.
    id: "phone-matrix-keeps-table-layout",
    why: "a matrix that collapsed like a grid would drop columns a reader is comparing, and "
      + "`display: block` on it is what used to send its sticky header to the document root",
    file: "src/app/globals.css",
    from: "  .ds-matrix {\n    display: table;",
    to: "  .ds-matrix {\n    display: block;",
    grep: "the capability matrix collapses as the design states",
  },
  {
    id: "phone-grid-cells-leave-table-layout",
    why: "a cell still in table layout is the collapse not having happened, and the priority "
      + "columns then render beside their own secondary fragment -- which is what every grid "
      + "in this app did below 600px for as long as the collapse existed",
    file: "src/app/globals.css",
    from: "  .ds-grid-table td {\n    display: block;",
    to: "  .ds-grid-table td.nope {\n    display: block;",
    grep: "its cells collapses as the design states",
  },
  {
    id: "config-unset-is-a-sentence",
    why: "an unset key reads back as its own default, which is indistinguishable from a "
      + "tenant that published the same value unless the scope is rendered",
    file: "src/app/configuration/page.tsx",
    // Repointed: the anchor went stale when the code around it moved.
    from: "                    return isUnset(entry) ? (",
    to: "                    return false ? (",
    grep: "says nobody set the key nobody set",
  },
  {
    id: "config-flag-reason",
    why: "`off` could be a kill switch, a flag nobody enabled, or a rule that sent this "
      + "subject to the control arm, and an operator in an incident needs to know which",
    file: "src/app/configuration/page.tsx",
    // Repointed: the anchor went stale when the code around it moved.
    from: "                  render: ([, decision]) => text(FLAG_REASON[flagReason(decision)]),",
    to: "                  render: () => \"\",",
    grep: "says why a flag is off",
  },
  {
    id: "config-kill-switch-marked",
    why: "a kill switch outranks every targeting rule and is somebody's deliberate stop, "
      + "which is the one flag state worth an alarm rather than a row",
    file: "src/app/configuration/page.tsx",
    from: "              <Banner severity=\"critical\">{text(\"config.killSwitchEngaged\")}</Banner>",
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
    id: "members-mask-printed-raw",
    why: "a masked name is marked and explained, not printed as three asterisks -- the same "
      + "fact rendered as a glitch",
    file: "src/app/members/page.tsx",
    from: "                    {isWithheld(row.preferred_name ?? row.legal_name) ? (",
    to: "                    {false ? (",
    grep: "marks a withheld name",
  },
  {
    id: "members-total-is-the-match",
    why: "a filtered list that reports only its own length implies the records that did not "
      + "match do not exist",
    file: "src/app/members/page.tsx",
    from: '          <span className="data">{formatInteger(page.total, "latn")}</span>{" "}',
    to: '          <span className="data">{formatInteger(page.matching, "latn")}</span>{" "}',
    grep: "keeps the tenant's total",
  },
  {
    id: "account-own-revoke-leaves-a-dead-page",
    why: "revoking your own device ends the session that pressed the button, so a success "
      + "message returns to a page with no session to render it -- the reader sees nothing "
      + "and is thrown to sign-in later with no explanation",
    file: "src/app/account/actions.ts",
    from: "      signedOut: (await currentSession()) === null,",
    to: "      signedOut: false,",
    grep: "signs you out here",
  },
  {
    id: "account-this-browser-unmarked",
    why: "revoking the device you are reading the page in signs you out and locks this "
      + "browser out for good, so the one device that must be marked is that one",
    file: "src/lib/account.ts",
    from: "  const mine = sessions.find((s) => s.session_id === sessionId);",
    to: "  const mine = sessions.find(() => false);",
    grep: "marks the browser it is reading from",
  },
  {
    id: "account-revoke-warning-deleted",
    why: "a revoked device is refused at the next sign-in rather than challenged, in the same "
      + "words a wrong password gets -- so the cost has to be said before the button, because "
      + "nothing afterwards can say it",
    file: "src/app/account/account-view.tsx",
    from: "                    {text(\"account.revokingThisSignsYouOut\")}",
    to: "                    {null}",
    grep: "marks the browser it is reading from",
  },
  {
    id: "account-codes-need-a-step-up",
    why: "minting codes takes the current password or a stepped-up session and nothing else, "
      + "so a button offered to a level-1 session offers an action the server refuses",
    file: "src/lib/account.ts",
    from: "  return aal >= 2;",
    to: "  return true;",
    grep: "offers no reissue button",
  },
  {
    id: "account-session-is-live-needs-both",
    why: "a session is live only if it is neither revoked nor expired -- checking the flag "
      + "alone lists a fortnight-old session as still open",
    file: "src/lib/account.ts",
    from: "  return session.revoked_at === null && session.expires_at > nowIso;",
    to: "  return session.revoked_at === null;",
    runner: "vitest",
    grep: "not revoked, and not expired",
  },
  {
    id: "account-codes-are-shown-once",
    why: "only a hash is kept, so a batch exists in one HTTP response -- a page that did not "
      + "say so would imply they can be fetched again",
    file: "src/app/account/account-view.tsx",
    from: '            <Banner severity="attention">{text("account.codesShownOnce")}</Banner>',
    to: "            {null}",
    grep: "shows the batch once",
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
    // Repointed: the anchor went stale when the code around it moved.
    from: "                    return !obligationsApply(install) ? (",
    to: '                    return install.criticality !== "live_critical" ? (',
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
    from: '        <Banner severity="attention">{text("notify.nothingSends")}</Banner>',
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
    why: "375 rows of column names is a wall rather than a disclosure, and the grouping is "
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
    // Repointed: the anchor went stale when the code around it moved.
    from: '                          {line.status === "active" ? "" : ` · ${text("finance.retired")}`}',
    to: '                          {line.status === "active" ? "" : ``}',
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
    // Repointed: the anchor went stale when the code around it moved.
    from: "  if (answer.allowed) return <>{children}</>;",
    to: "  if (true) return <>{children}</>;",
    grep: "is told each block is refused",
  },
  {
    id: "membership-money-uses-the-currency-exponent",
    why: "an amount is an integer count of minor units and JOD has three of them, so a "
      + "hard-coded /100 renders 45.000 dinars as 450.00 -- and every assertion about the "
      + "word 'price' passes either way",
    // **Repointed: the membership price moved to `MoneyValue` and this still broke the
    // helper beside it.** `money()` is live on the Command Center and the cash board, so the
    // mutation applied cleanly and the row it is asserted against was rendered by something
    // else -- reported as UNCAUGHT, which reads as a gap and was a stale aim. That is this
    // file's own tell: a mutation whose test asserts the rendered half while the mutation
    // edits the other half.
    file: "src/components/ds/money-value.tsx",
    from: "  const { code, sign, major, minor } = rawParts(amountMinor, currency, numbering);",
    to: '  const code = currency, sign = amountMinor < 0 ? "-" : "",\n'
      + '    major = String(Math.trunc(Math.abs(amountMinor) / 100)),\n'
      + '    minor = `.${String(Math.abs(amountMinor) % 100).padStart(2, "0")}`;',
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
    id: "staff-unknown-is-not-no-access",
    why: "a reader who may not see logins, and a permitted read that answered nothing, are "
      + "both 'nobody looked' -- and 'checked and clean' is the one answer that is always "
      + "wrong about a departed employee's access",
    file: "src/lib/staff.ts",
    from: '  if (seen === null) return "unknown";',
    to: "",
    grep: "cannot see logins is told so",
  },
  {
    id: "staff-ended-with-access-is-the-finding",
    why: "an active identity is access whether or not a session is live -- the password "
      + "still works, so the next sign-in opens the product, and reading only the session "
      + "count would call a departed employee clean",
    file: "src/lib/staff.ts",
    from: '  const live = seen.live_sessions > 0 || seen.status === "active";',
    to: "  const live = seen.live_sessions > 0;",
    grep: "four standings apart",
  },
  {
    id: "staff-reach-is-not-the-home-club",
    why: "a tenant-scoped assignment already covers every named one, so rendering the named "
      + "scopes beside it understates what somebody can reach",
    file: "src/lib/staff.ts",
    from: '  if (live.some((one) => one.scope_type === "tenant")) return { kind: "tenant" };',
    to: "",
    grep: "clubs a role reaches",
  },
  {
    id: "staff-primary-role-is-the-broadest",
    why: "which assignment is the job decides both halves of ADM-STF-02, and an unordered "
      + "answer makes the planner the author -- the two halves would change between reads",
    file: "src/lib/staff.ts",
    from: "    const breadth = (SCOPE_BREADTH[b.scope_type] ?? 0) "
      + "- (SCOPE_BREADTH[a.scope_type] ?? 0);\n    if (breadth !== 0) return breadth;",
    to: "",
    runner: "vitest",
    grep: "broadest scope",
  },
  {
    id: "staff-lapsed-assignment-carries-nothing",
    why: "a revoked role must not be credited with the permission it used to carry, which "
      + "is what the whole sensitive-grants block is read for",
    file: "src/lib/staff.ts",
    from: "  const live = assignments.filter((one) => one.live);\n  return catalog",
    to: "  const live = assignments;\n  return catalog",
    runner: "vitest",
    grep: "lapsed assignment",
  },
  {
    id: "staff-unreachable-grant-is-marked",
    why: "a privileged permission needs assurance level 3, which nobody in this build can "
      + "reach, so drawing it as held says somebody can do something no session can",
    file: "src/lib/staff.ts",
    from: '  if (permission.required_aal > reachableAal) return "unreachable";',
    to: "",
    runner: "vitest",
    grep: "nobody in this build can use",
  },
  {
    id: "rota-shows-both-a-booking-and-its-exception",
    why: "the canvas's own requirement and the reason the screen exists: a booking inside a "
      + "day off is flagged rather than silently honoured or silently dropped, because the "
      + "member on the other end has already been told a time",
    file: "src/lib/rota.ts",
    from: `    return here.some((one) => one.conflicts_with_availability)
      ? "bookedConflict"
      : "booked";`,
    to: '    return "booked";',
    runner: "vitest",
    grep: "shows BOTH where a booking sits inside an exception",
  },
  {
    id: "rota-an-exception-is-not-quietly-open",
    why: "an hour a break or a day off removes must not read as available, or the grid is "
      + "the rota lying about who is working",
    file: "src/lib/rota.ts",
    from: "  if (removed) return \"exception\";",
    to: "",
    runner: "vitest",
    grep: "is an exception where a break or a day off removes the time",
  },
  {
    id: "rota-a-cell-counts-only-its-own-day",
    why: "a session on Friday marking Tuesday's cell booked would make every column the "
      + "same, and the grid is addressed by day and hour together",
    file: "src/lib/rota.ts",
    from: "    (one) => one.local_date === day.date\n      && overlaps(",
    to: "    (one) => overlaps(",
    runner: "vitest",
    grep: "only counts sessions on that day",
  },
  {
    id: "rota-nothing-to-draw-is-not-a-grid",
    why: "twenty-four rows of \"not working\" for a room nobody wrote a rota for reads as a "
      + "studio that can never be booked, which is the opposite of true",
    file: "src/lib/rota.ts",
    from: "  if (edges.length === 0) return null;",
    to: "  if (edges.length === 0) return { first: 0, last: 23 };",
    runner: "vitest",
    grep: "is null where there is nothing at all to draw",
  },
  {
    id: "freeze-both-ends-of-the-span-are-counted",
    why: "`freeze_membership` stores `planned_ends_on = starts_on + days - 1`, so a freeze "
      + "from the first to the first is one day -- treating the pair as exclusive spends "
      + "somebody's annual allowance a day at a time, in the direction nobody checks",
    file: "src/lib/freeze.ts",
    from: "  return span + 1;",
    to: "  return span;",
    runner: "vitest",
    grep: "counts both ends",
  },
  {
    id: "freeze-the-start-window-is-named-before-the-allowance",
    why: "the order of refusals is the server's, so a form that checked the allowance first "
      + "would tell somebody to shorten a freeze whose date the server was going to refuse "
      + "anyway -- two wrong instructions for one mistake",
    file: "src/lib/freeze.ts",
    from: '  if (!startIsAllowed(from, allowance.may_start_between)) {\n    return "freeze.startOutsideWindow";\n  }',
    to: "",
    runner: "vitest",
    grep: "names the start window before the allowance",
  },
  {
    id: "freeze-a-step-up-is-offered-rather-than-a-button-that-fails",
    why: "every other write form in this app is absent because a button that answered 403 "
      + "is worse than its absence; what makes this one buildable is the offer, so a block "
      + "that rendered the form regardless would be the thing the whole rule is against",
    file: "src/components/membership-panels.tsx",
    from: '      ) : affordance === "form" ? (',
    to: '      ) : true ? (',
    runner: "playwright",
    grep: "offers the step-up rather than a button",
  },
  {
    id: "freeze-a-contract-that-forbids-it-gets-no-step-up",
    why: "a step-up cannot grant what `check_freeze` refuses outright, so offering one for a "
      + "contract with no allowance sends somebody to find a second factor that changes "
      + "nothing -- the member record's own rule about a health field, applied to a write",
    // **Moved from the component to the decision, because the branch was unreachable.**
    // The fixture's contract allows thirty days, so the component's no-allowance path never
    // rendered and deleting it passed a green suite. A decision is testable where a rendered
    // branch is not, which is the remedy the rules file states for this exact shape.
    file: "src/lib/freeze.ts",
    from: '  if (!allowance.allows_freezing) return "no_allowance";',
    to: "",
    runner: "vitest",
    grep: "offers neither where the contract forbids freezing",
  },
  {
    id: "cash-the-count-is-scaled-to-the-stored-minor-units",
    why: "JOD is stored in fils and shown with two decimals, so reading a 135.50 count as "
      + "13550 makes it 13.55 and posts a 121.95 shortfall to suspense -- on the one screen "
      + "whose entire job is the difference between two numbers",
    file: "src/lib/cash.ts",
    from: "  return shown * 10 ** (storageDigits - displayDigits);",
    to: "  return shown;",
    runner: "vitest",
    grep: "scales what is shown to what is stored",
  },
  {
    id: "cash-the-expected-figure-is-shown-before-the-count",
    why: "the canvas is explicit that this is an accuracy control rather than a fraud one, "
      + "and a screen that revealed the figure after the count would be a different control "
      + "with the same layout",
    file: "src/app/payments/cash/page.tsx",
    from: '          <dt className="ds-cash-total">{text("cash.expected")}</dt>',
    to: '          <dt className="ds-cash-total">{""}</dt>',
    runner: "playwright",
    grep: "shows the expected figure before anything is counted",
  },
  {
    id: "cash-a-difference-asks-for-a-sentence-before-the-submit",
    why: "the reason is a field somebody fills while looking at the difference, not a "
      + "refusal they discover by pressing a button -- and this build demands one for any "
      + "difference at all, which is stricter than the canvas's 2.00 threshold",
    file: "src/app/payments/cash/close-form.tsx",
    from: "  const out = gap !== null && gap !== 0;",
    to: "  const out = false;",
    runner: "playwright",
    grep: "the variance appears as the count is typed",
  },
  {
    id: "rota-the-form-is-gated-on-the-write-not-the-read",
    why: "every other write surface in this app is absent because a button that answered "
      + "403 is worse than its absence, so a form rendered for a reader who may not change "
      + "a rota is the thing that principle exists to prevent",
    file: "src/app/rota/page.tsx",
    from: '  const mayWrite = (await gate("scheduling.availability.write")).allowed;',
    to: "  const mayWrite = true;",
    runner: "playwright",
    grep: "a reader who may not change a rota is given no form at all",
  },
  {
    id: "rota-an-empty-field-is-named-by-the-server",
    why: "the browser refuses an empty required field first, so the server-side check is "
      + "reached only by a client that is not a browser -- and it is the one that matters, "
      + "because `window_kind = 'time_off'` carries a schema constraint that a missing "
      + "reason violates with a 500-shaped message rather than a named field",
    file: "src/app/rota/actions.ts",
    from: "  if (Object.keys(missing).length > 0) return { ...IDLE, missing, echo };",
    to: "",
    runner: "playwright",
    grep: "names the field it needs rather than refusing the whole form",
  },
  {
    id: "rota-a-write-the-page-does-not-show-is-a-reader-misled",
    why: "a write whose own page still shows the old rota tells a reader the product did "
      + "not work, and the next thing they do is write it again",
    file: "src/app/rota/actions.ts",
    from: '    revalidatePath("/rota");\n    return { ...IDLE, message: "rota.added" };',
    to: '    return { ...IDLE, message: "rota.added" };',
    runner: "playwright",
    grep: "writes a day off, shows it on the grid, and takes it back",
  },
  {
    id: "rota-the-week-grid-is-contained-not-pinned",
    why: "a scroller with `contain: layout` around a table pinned to its container reports "
      + "zero document overflow and has nothing to scroll, so the columns are clipped and "
      + "unreachable while every assertion about text still passes -- the state that shipped "
      + "on /permissions, and the reason this property is asserted from both sides",
    file: "src/app/globals.css",
    from: "  min-inline-size: 64rem;\n  table-layout: fixed;",
    to: "  table-layout: fixed;",
    runner: "playwright",
    grep: "the week grid really scrolls inside itself",
  },
  {
    id: "rota-the-week-grid-does-not-push-the-page-sideways",
    why: "a week grid is 64rem wide by design and a genuine scroll container's overflow still "
      + "reaches the document root, so without the containment boundary the page scrolled "
      + "sideways by 95px at phone width and hid its own right-hand edge",
    file: "src/app/globals.css",
    from: "at a time and re-measuring, not by reading the stylesheet. */\n  contain: layout;",
    to: "at a time and re-measuring, not by reading the stylesheet. */",
    runner: "playwright",
    // **The pair of properties is caught by a pair of tests, and this grep was first pointed
    // at the wrong one of them.** Removing the boundary leaves the region scrolling exactly as
    // before -- that test stayed green and the sweep reported a gap. The test that sees this is
    // the sideways sweep, which is the whole reason both sides are asserted.
    grep: "the availability grid does not scroll sideways",
  },
  {
    id: "attendance-hour-axis-is-a-clock",
    why: "the axis is the one place a 12-hour form would put \"6 AM\" under a heading whose "
      + "other end reads 22:00, and ADM-RPT-04's whole output is an hour",
    file: "src/lib/reports.ts",
    from: 'return `${String(hour).padStart(2, "0")}:00`;',
    to: "return `${hour}:00`;",
    runner: "vitest",
    grep: "padded 24-hour",
  },
  {
    id: "attendance-empty-hour-is-a-mark",
    why: "an hour nobody came in must be drawn at the baseline: an absent bar and a bar "
      + "nobody can see are the same to a reader, and \"nothing before seven\" is a reading "
      + "this chart exists for",
    file: "src/lib/reports.ts",
    from: "  return Math.max(2, Math.round((entries / peak) * 100));",
    to: "  return Math.round((entries / peak) * 100);",
    runner: "vitest",
    grep: "empty hour as a mark",
  },
  {
    id: "attendance-no-peak-is-not-zero-per-cent",
    why: "nobody came in at all is a club that was shut; rendering 0% would read as "
      + "\"this hour is quiet\", which is MOD-011's empty-window rule in a report",
    file: "src/lib/reports.ts",
    from: "  return bp === null ? null : Math.round(bp / 100);",
    to: "  return Math.round((bp ?? 0) / 100);",
    runner: "vitest",
    grep: "no percentage where there is no peak",
  },
  {
    id: "attendance-sunday-is-six",
    why: "0 is Monday in MOD-019's rota numbering, so a Sun-Thu range written as 0-4 is "
      + "Mon-Fri -- a whole day of the chart, silently",
    file: "src/lib/reports.ts",
    from: '{ key: "sun-thu", label: "attendanceReport.sunThu", days: [6, 0, 1, 2, 3] }',
    to: '{ key: "sun-thu", label: "attendanceReport.sunThu", days: [0, 1, 2, 3, 4] }',
    runner: "vitest",
    grep: "five days and differ",
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
  {
    id: "ds-button-href-underlined",
    why: "`href` renders a real anchor and the global `a` rule sets only the colour, so every "
      + "non-link button with one rendered underlined -- a button that looks like a link, "
      + "which the source forbids in as many words",
    file: "src/components/ds/button.tsx",
    from: '    textDecoration: "none",',
    to: "",
    runner: "vitest",
    grep: "not underlined when",
  },
  {
    id: "ds-field-mark-needs-a-message",
    why: "a control marked only by its message slot cannot be marked by a panel beside it, "
      + "so the sentence ends up rendered twice under one field",
    file: "src/components/ds/field.tsx",
    from: '      <div className="ds-field-control" data-message={marked ?? shown?.kind}>',
    to: '      <div className="ds-field-control" data-message={shown?.kind}>',
    runner: "vitest",
    grep: "marks the control and puts nothing",
  },
  {
    id: "desk-button-outside-the-window",
    why: "`may_check_in` refuses outside the check-in window, so a button offered for a class "
      + "tomorrow answers 409 -- a button that answered 403 is worse than its absence",
    file: "src/lib/desk.ts",
    from: '  return checkinWindow(booking, now) === "open";',
    to: "  return true;",
    runner: "vitest",
    grep: "withholds it outside the window",
  },
  {
    id: "desk-unreadable-window-reads-open",
    why: "failing toward offering a control the module will refuse is the direction the whole "
      + "function exists to avoid",
    file: "src/lib/desk.ts",
    from: '  if (Number.isNaN(opens) || Number.isNaN(closes)) return "closed";',
    to: '  if (false) return "closed";',
    runner: "vitest",
    grep: "treats a window it cannot read as closed",
  },
  {
    id: "desk-countdown-has-no-window",
    why: "'2,266 minutes to go' for a class tomorrow is arithmetic that is correct and a "
      + "sentence that is absurd, and only looking at the page can see it",
    file: "src/lib/desk.ts",
    from: "  if (minutes < 0 || minutes > COUNTDOWN_WINDOW_MINUTES) return null;",
    to: "  if (minutes < 0) return null;",
    runner: "vitest",
    grep: "says nothing about a class tomorrow",
  },
  {
    id: "desk-release-reads-as-absence",
    why: "MOD-020's worst shipped defect was exactly this collapse: every member of a "
      + "cancelled class recorded absent, with a fee and a strike",
    file: "src/lib/desk.ts",
    from: '  if (booking.state === "released" || booking.state === "session_cancelled") {\n    return "released";\n  }',
    to: '  if (false) {\n    return "released";\n  }',
    runner: "vitest",
    grep: "keeps a gym cancellation apart",
  },
  {
    id: "desk-order-is-booking-order",
    why: "four minutes from the start a receptionist is looking for who has not arrived, and "
      + "the rows they want out of the way are the ones already in the room",
    file: "src/lib/desk.ts",
    from: "    const byGroup = GROUP[rowState(a)] - GROUP[rowState(b)];",
    to: "    const byGroup = 0;",
    runner: "vitest",
    grep: "puts the people who have not arrived first",
  },
  {
    id: "desk-presence-counts-the-roster",
    why: "a class with six free seats is twelve of eighteen, not twelve of twelve -- the "
      + "denominator is MOD-019's capacity and the roster has no cached total",
    file: "src/lib/desk.ts",
    from: "    places: roster.places,",
    to: "    places: roster.bookings.length,",
    runner: "vitest",
    grep: "counts who is here against the session",
  },
  {
    id: "ds-touch-floor-scoped-to-root",
    why: "44px on Touch is the minimum target rather than a style, and a rule matching only "
      + "`<html>` leaves a screen that sets its own density with a 36px button",
    file: "src/app/globals.css",
    from: '[data-density="touch"] .ds-button,\n[data-density="spacious"] .ds-button {',
    to: ':root[data-density="touch"] .ds-button,\n:root[data-density="spacious"] .ds-button {',
    // **Not the browser test, which measures a button that is `lg` anyway.** `BUTTON_HEIGHT`
    // makes `lg` 44px by itself, so FD-06's control clears the floor whichever selector is
    // live -- the sweep said so by coming back uncaught, which is the right answer and not a
    // gap. The property this rule carries is that a *screen* can set the density at all, and
    // the structural assertion is what proves it.
    runner: "node",
    grep: "matches a screen.s own wrapper",
  },
  {
    id: "walk-in-stale-answer-lands",
    why: "a reply about a number the desk has already edited would mark a clear number as "
      + "duplicated, or clear a duplicated one -- the race the derivation exists to make "
      + "impossible rather than guard",
    file: "src/lib/walk-in.ts",
    from: '  if (answer === null || answer.value !== value) return { kind: "checking", value };',
    to: '  if (answer === null) return { kind: "checking", value };',
    runner: "vitest",
    grep: "checking until an answer about THIS value",
  },
  {
    id: "walk-in-failed-check-reads-as-clear",
    why: "a check the server could not be asked is not a check that passed, and treating the "
      + "two alike turns a network blip into a silent duplicate",
    file: "src/lib/walk-in.ts",
    from: '  if (state.kind === "failed") {\n    return isAbout(state, value) && acknowledgedValue === value;\n  }',
    to: "  if (state.kind === \"failed\") return true;",
    runner: "vitest",
    grep: "holds a check that could not run",
  },
  {
    id: "walk-in-dismissal-outlives-its-number",
    why: "'different person' answers one number, and a dismissal that survived an edit would "
      + "hide the interruption for whatever is typed next",
    file: "src/lib/walk-in.ts",
    from: "  if (acknowledgedValue === value) return null;",
    to: "  if (acknowledgedValue !== null) return null;",
    runner: "playwright",
    grep: "acknowledges one number and not the next one",
  },
  {
    id: "walk-in-field-is-not-marked",
    why: "the border is how the field itself says the number it holds is already somebody's, "
      + "and a panel below with an unmarked control above it leaves the eye in the wrong place",
    file: "src/app/members/new/walk-in-form.tsx",
    from: '        marked={duplicate !== null && !state.missing.phone ? "warning" : undefined}',
    to: "        marked={undefined}",
    runner: "playwright",
    grep: "acknowledges one number and not the next one",
  },
  {
    id: "walk-in-add-member-shown-to-a-denied-reader",
    why: "a button that answers 403 is worse than its absence, and gateVerdict is what tells "
      + "'a stronger sign-in would open this' from 'you may not'",
    file: "src/app/members/page.tsx",
    from: '  const addMember = gateVerdict(mayWrite) === "denied" ? undefined : (',
    to: "  const addMember = (",
    runner: "playwright",
    grep: "no Add member button at all",
  },
];

const only = process.argv[2];
/**
 * Whether any `tests/unit/` file names a test matching this pattern.
 *
 * The pattern is a regex, because that is what `--test-name-pattern` takes.
 */
function unitTestsMention(grep) {
  const dir = join(web, "tests/unit");
  const pattern = new RegExp(grep);
  for (const entry of readdirSync(dir)) {
    if (!entry.endsWith(".mjs")) continue;
    if (pattern.test(readFileSync(join(dir, entry), "utf8"))) return true;
  }
  return false;
}

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
    // **Is this a stale definition or a mutation a killed run left behind?** The handlers
    // above restore on SIGINT, SIGTERM and SIGHUP, and none of them can catch a SIGKILL --
    // so an interrupted sweep can leave a file mutated, and the only trace is this anchor
    // going missing. That reads as "somebody edited the component" and sent me looking in
    // the wrong place for ten minutes, with a red component suite in between. Say which it
    // is, and say how to put it back.
    const leftBehind = mutation.to !== "" && original.includes(mutation.to);
    const because = leftBehind
      ? `the replacement text is present, so a previous run was killed before it restored `
        + `this file. Put it back with: git checkout ${mutation.file}`
      : `the anchor appears ${occurrences} times, not once`;
    notRun.push(`${mutation.id}: ${because}`);
    console.log(`SKIP  ${mutation.id} (${leftBehind ? "LEFT MUTATED" : `anchor matched ${occurrences} times`})`);
    continue;
  }

  inFlight.set(path, original);
  writeFileSync(path, original.replace(mutation.from, mutation.to));
  try {
    const run = mutation.runner === "vitest"
      ? spawnSync("npx", ["vitest", "run", "-t", mutation.grep],
                  { cwd: web, encoding: "utf8", timeout: 180_000 })
      // **The foundation layer had no runner here at all**, so none of its assertions had
      // ever been mutation-proven through this harness -- found by pointing a mutation at
      // one and watching it come back uncaught, because `vitest` does not collect
      // `tests/unit/` and reported no failure rather than no test. `--test-name-pattern` is
      // Node's own `-t`.
      : mutation.runner === "node"
      ? spawnSync("node",
                  ["--test", "--test-name-pattern", mutation.grep, "tests/unit/"],
                  { cwd: web, encoding: "utf8", timeout: 180_000 })
      : spawnSync("npx",
                  ["playwright", "test", "--grep", mutation.grep, "--reporter", "line"],
                  { cwd: web, encoding: "utf8", timeout: 180_000 });
    const output = `${run.stdout ?? ""}${run.stderr ?? ""}`;
    // **Node's runner cannot be asked whether its pattern matched.** With a name pattern
    // that matches nothing it still runs every file, filters every test out of each, and
    // reports `pass 9, fail 0` -- so a stale grep is indistinguishable from a real pass by
    // the exit code and from a real gap by the output. Proved by pointing one at a name that
    // does not exist and watching it come back UNCAUGHT rather than SKIP. The answer is the
    // same static check the mutation text already gets: the pattern has to occur in the test
    // sources, or the mutation is reported as not run.
    const matched = mutation.runner !== "node" || unitTestsMention(mutation.grep);
    const ranSomething = matched
      && !/No tests found|No test files found/.test(output)
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
