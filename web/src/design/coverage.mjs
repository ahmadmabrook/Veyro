#!/usr/bin/env node
/**
 * Every specified screen on a covered surface is accounted for, or a reason is written down.
 *
 * **This exists because an audit by hand reported 44 missing screens and most of that was
 * wrong.** Some of the 44 are *states* of screens that are built — the Command Center's
 * quiet day, the Member 360's three variants — which is a labelling gap rather than a build
 * gap. Some are built and were never named in the inventory. Some need modules this
 * repository does not have. And some are genuinely next. A list that mixes those four is a
 * list nobody can act on, and re-deriving it by hand produced a different answer each time.
 *
 * So it is a check rather than a note, in the shape this repository already uses for the
 * same problem one layer down: `GateCoverageTests.UNGATED` requires every ungated route to
 * appear in a list with a reason somebody wrote, and says that adding to it is meant to be
 * uncomfortable. The same applies here.
 *
 * A screen passes if one of four things is true:
 *
 *   1. **The inventory names it.** `contracts/ui/design-compliance.md` claims a route for
 *      its id, which is where a built screen's fidelity is argued.
 *   2. **It is a state of a screen that is built.** `STATE_OF` maps it to that screen's id,
 *      which must itself be accounted for — so a state cannot stand in for a missing screen.
 *   3. **`BLOCKED` names something external.** One of the seven things that have to arrive
 *      from outside this repository, or one of the owner's reserved actions.
 *   4. **`BACKLOG` names where the work lives.** It is not built, it is not blocked, and the
 *      entry says which module owns it — so the answer to "why not yet" is a dependency or a
 *      priority, never a judgement nobody has made.
 *
 * Both directions, because this repository's own rule is that a check in one direction is
 * half a check: an entry for a screen that is now built fails too, so no list can carry a
 * stale excuse. That is the failure mode the schedule board shipped — a gap note that
 * outlived its gap by one change, which an independent tester then read and believed.
 *
 * **The split between 3 and 4 is new and it is the point of this file.** It admitted five
 * causes until now — `module:`, `owner-reserved:`, `data:`, `store:`, `client:` — and three
 * of those name work this session is delegated to do, so a screen could sit in a blocked
 * list while nothing outside the repository was missing. Thirty-three of the forty-five did.
 * `CLAUDE.md`'s rule is that a blocker is external or it is not a blocker; this is the
 * mechanical form of it, and it could not be done by deleting the three loose tokens alone,
 * because the screens they covered would then have had nowhere to be declared.
 */

import { existsSync, readFileSync } from "node:fs";

const SCREENS = new URL("./screens.generated.json", import.meta.url).pathname;
const INVENTORY = new URL("../../../contracts/ui/design-compliance.md", import.meta.url)
  .pathname;
const CATALOGUE = new URL("../../../tools/mission_runner/module_catalog.json", import.meta.url)
  .pathname;
const BACKEND = new URL("../../../backend/app/", import.meta.url).pathname;

/**
 * A screen that is one *state* of another, drawn separately because the design draws the
 * states separately. Rendering the state is the built screen's job; naming it here is what
 * stops the count reading as a missing screen.
 */
const STATE_OF = {
  "ADM-CC-03": "ADM-CC-01",
  "ADM-CC-04": "ADM-CC-01",
  "ADM-CC-05": "ADM-CC-01",
  "ADM-MEM-02": "ADM-MEM-01",
  "ADM-MEM-03": "ADM-MEM-01",
  "ADM-MEM-04": "ADM-MEM-01",
};

/**
 * Where a module lives when it is built, for every module these two surfaces' screens name.
 *
 * **This is what makes "a module owns it" checkable.** The old list said `module: CRM`,
 * which names nothing a check can look up: not an id in the catalogue, not a directory, not
 * a wave, not a dependency. A `MOD-0NN` prefix is all three — the id has to be in
 * `module_catalog.json`, and the package has to be *absent* from `backend/app/`, because a
 * backlog entry for a module that has since landed is the stale excuse this file exists to
 * refuse. A `work:` entry is the mirror: every module it names has to be present, or the
 * screen is waiting on a module rather than on work inside one.
 *
 * The package name for an unbuilt module is this check's reading of where it will go, in the
 * convention the eighteen built ones follow (one lowercase domain word). If it lands
 * somewhere else the entry fails and somebody re-derives it, which is the intended
 * discomfort rather than a defect — and the inventory check behind it catches the same
 * moment from the other side, since building the screens means claiming their routes.
 */
const PACKAGE = {
  "MOD-004": "tenancy",
  "MOD-005": "configuration",
  "MOD-007": "identity",
  "MOD-008": "authorization",
  "MOD-009": "privacy",
  "MOD-010": "events",
  "MOD-011": "observability",
  "MOD-012": "integrations",
  "MOD-013": "notifications",
  "MOD-014": "people",
  "MOD-015": "billing",
  "MOD-016": "catalog",
  "MOD-017": "commercial",
  "MOD-018": "ledger",
  "MOD-019": "scheduling",
  "MOD-020": "booking",
  "MOD-021": "devices",
  "MOD-022": "access",
  "MOD-026": "tasks",
  "MOD-027": "crm",
  "MOD-057": "analytics",
  "MOD-058": "ai",
  "MOD-059": "search",
  "MOD-055": "automation",
};

/**
 * Something outside this repository has to arrive before the screen can exist as drawn.
 *
 * **Every reason names one of eight things, and seven of them are `CLAUDE.md`'s list of
 * external blockers in full.** The eighth is the owner's reserved actions, which are the
 * other kind of thing this session cannot obtain.
 *
 *   - `payments:`   a payment provider in test mode, and its keys placed by the owner.
 *   - `messaging:`  a messaging provider for email and SMS.
 *   - `store:`      an object store, and the residency decision that goes with it.
 *   - `vault:`      a key vault.
 *   - `identity:`   an identity provider for OIDC/SAML federation.
 *   - `hardware:`   door hardware and readers.
 *   - `retention:`  the retention policy, which is the owner's to set.
 *   - `owner-reserved:` one of `governance/registry.json`'s four reserved actions.
 *
 * **Four of the eight are used by no screen here, and that is a finding rather than dead
 * vocabulary.** `vault:`, `identity:`, `hardware:` and `retention:` block *modules* — the
 * Console's sign-in, a device's certificate, MOD-009's sweep — and none of them is the
 * decisive act of an Admin or Front Desk screen. `owner-reserved:` is unused for a sharper
 * reason: a refund or a sale in a provider's test mode moves no real money, so what blocks
 * those screens is the provider arriving, not the owner's permission to spend. The set is
 * declared whole anyway, so a reader can hold it against the rules file rather than against
 * whichever causes this surface happens to need.
 *
 * **And `messaging:` is unused, which changes a priority.** Every screen here that would
 * send a message — the staff invitation, the broadcast, the class cancellation, the shift
 * report — needs work done first, so it is in `BACKLOG` and the provider is named as the
 * seam. A messaging provider is on no Admin or Front Desk screen's critical path.
 */
const BLOCKED = {
  "FD-01": "payments: the canvas's live queue resolves at the door and its primary action is "
    + "'Take JOD 55.00', with 'Send link instead' beside it -- a payment and a message, and "
    + "this build has no provider for either. The 40px face on every row needs an object "
    + "store as well, and what is left without those two is ADM-ACC-02's decision log with "
    + "FD-03 hanging off it, which both exist",
  "FD-04": "payments: 'Take 8.00 & open the gate'. The charge is the act the button names, "
    + "and behind it two pieces are this session's: MOD-016's `PRODUCT_TYPES` already carries "
    + "`session_credit` and `service`, so a day-pass product is configuration rather than a "
    + "capability gap, and the waiver version the canvas stores with the record has no column "
    + "-- MOD-009's consent documents are the nearest thing and are not wired to a sale",
  "ADM-MSH-01": "payments: selling a membership ends in taking a payment. MOD-016 resolves "
    + "the price and MOD-017 writes the agreement, so the sales half of this surface is what "
    + "a provider in test mode clears",
  "ADM-MSH-02": "payments: the canvas's action is 'Take 795.60' after a price-change "
    + "disclosure. Renewing is taking a payment, and there is no provider here",
  "ADM-MSH-04": "payments: the canvas's action is 'Resume, take 30.19' -- a pro-rata charge. "
    + "The resume itself is built and the unused freeze days do return to the allowance; the "
    + "charge is the act the button names",
  "ADM-MSH-05": "payments: an upgrade is priced and charged on the spot, and the proration "
    + "MOD-017 computes ends in a payment nothing here can take",
  "ADM-PAY-02": "payments: approving a refund pays money out. The two-party approval is "
    + "built and MOD-017 requires that the approver is not the requester; what is missing is "
    + "the provider that would settle it",
  "ADM-PAY-04": "payments: taking a card is real money, and there is no payment provider and "
    + "no stored payment method in this build",
  "ADM-PAY-08": "payments: a partial refund pays money out, through the same two-party "
    + "approval and the same provider that is not here",
  "ADM-SET-04": "payments: the canvas configures CliQ and card acceptance, which needs a "
    + "provider to configure and a stored payment method to hold",
  "ADM-MEM-08": "store: documents need an object store and a residency decision, the same "
    + "wall MOD-009's export and MOD-014's progress media hit",
  "ADM-SET-06": "store: branding assets need an object store and a residency decision, the "
    + "same wall MOD-009's export hits",
};

/**
 * It is not built, nothing external is missing, and this says where the work lives.
 *
 * **"Not built yet" is still not a reason**, which is why there are only three forms an
 * entry may take and each one is checked against the repository rather than read:
 *
 *   - `MOD-0NN:` — that module owns the screen and is unbuilt. The id must be in the
 *     catalogue and its package must be absent, and the reason says what the module's own
 *     dependency chain is waiting for, because that chain *is* the "why not yet".
 *   - `work:` — a module that exists does not yet do what the screen draws. The reason names
 *     at least one built module and what has to be written in it.
 *   - `client:` — work in this app with no backend module behind it. Exactly one screen, and
 *     it is a service worker, which `CLAUDE.md` names as weeks of work and still work.
 *
 * The thing that is *not* allowed here is any of the eight external causes: a screen whose
 * work is undone is not blocked by the provider waiting at the end of it. That is the
 * distinction the five-token version could not make, and it is enforced by the two
 * vocabularies being disjoint.
 */
const BACKLOG = {
  // MOD-026 is the shortest chain of the five and the one three screens here wait on: its
  // own dependencies, MOD-008 and MOD-013, are both built, so it is buildable now and what
  // keeps it unbuilt is the order of the work rather than anything in the way.
  "ADM-CC-06": "MOD-026: a side sheet holds per-item state -- what was resolved, by whom, "
    + "when, and what is still open on it -- and no module keeps a resolution record. A "
    + "resolvable item with an owner and an SLA is MOD-026's case; the Command Center's "
    + "queue is derived from live state, which is why ADM-CC-07 waits on the same module",
  "ADM-CC-07": "MOD-026: a resolved history is a list of cases that were closed, and a case "
    + "is MOD-026's. The queue this screen would be the history of is derived from live "
    + "state, so there is nothing to list yet",
  "ADM-TSK-01": "MOD-026: tasks. Its dependencies MOD-008 and MOD-013 are both built, so "
    + "this is the next Pilot-wave module with nothing in front of it",
  // MOD-027's own dependency chain runs through MOD-026, so the seven CRM screens are two
  // modules deep rather than one. The pipeline, a lead, its stages and the unified inbox are
  // all its; `lifecycle_state` on a MOD-014 person is the only part of any of it here.
  "ADM-CRM-01": "MOD-027: the pipeline, its stages and a lead's movement between them. "
    + "MOD-027 depends on MOD-026, which is unbuilt, so this is two modules deep; "
    + "`lifecycle_state` on a MOD-014 person is the only part of a lead that exists here",
  "ADM-CRM-02": "MOD-027: there is no lead in this build to list",
  "ADM-CRM-03": "MOD-027: a lead's profile, its activity and its owner",
  "ADM-CRM-04": "MOD-027: adding a lead writes the record MOD-027 owns. MOD-014's "
    + "`create_person` writes a person, which is the half that exists",
  "ADM-CRM-06": "MOD-027: converting a trial needs a trial, and no MOD-017 membership state "
    + "starts a clock on one",
  "ADM-CRM-07": "MOD-027: a lost reason is a field on a lead",
  "ADM-COM-01": "MOD-027: a WhatsApp thread is the unified inbox MOD-027's objective names, "
    + "and it needs both halves -- MOD-013 authors a message and sends nothing, and MOD-012 "
    + "has no inbound receiver, which is where the messaging provider and the vault that "
    + "verifies a callback signature are the seam this work stops at",
  "FD-05": "MOD-027: 'Creates a lead already in trial with the clock running, a credential, "
    + "and an app invitation by text. Yasmin picks it up on her pipeline within the minute' "
    + "-- the pipeline and the lead are MOD-027's, nothing starts a trial clock on a MOD-017 "
    + "membership, and the invitation by text is where MOD-013's missing dispatcher is the "
    + "seam rather than the blocker",
  // MOD-055 depends on MOD-026 too, so automation sits behind tasks for the same reason CRM
  // does -- an automation's actions are approvals and cases.
  "ADM-AUT-01": "MOD-055: automation, which depends on MOD-010 (built) and MOD-026 (not), so "
    + "it is behind tasks in the chain rather than waiting on anything outside",
  "ADM-AUT-02": "MOD-055: the builder is the authoring surface for the bounded actions, "
    + "retries and loop protection MOD-055's objective names",
  "ADM-AUT-03": "MOD-055: a run history needs runs, and nothing runs an automation",
  "ADM-AI-01": "MOD-058: 'Why Veyro said PT revenue fell JOD 1,840 -- full derivation' is a "
    + "stored insight with its source records and each one's contribution. MOD-058 depends "
    + "on MOD-057, which is unbuilt, so the derivation has no read model to derive from. "
    + "MOD-008 classifies AI acting for a member as privileged, which is level 3 and is "
    + "reachable now that a passkey assertion is verified -- so the assurance level is no "
    + "longer part of why this screen is missing",
  "ADM-SRCH-01": "MOD-059: PostgreSQL FTS and pg_trgm behind a command bar. It depends on "
    + "MOD-057, and MOD-014 refuses a LIKE scan presented as search because that is a read "
    + "path with no freshness contract and no permission pre-filter",
  // `work:` -- a built module does not yet do what the screen draws. Each names the module
  // and what has to be written in it.
  "ADM-CC-02": "work: MOD-008's `permit` and MOD-014's `held_permissions` both resolve "
    + "against the tenant-wide default scope, so a brand- or location-scoped role is refused "
    + "every read rather than shown its own club -- and what makes this screen the club "
    + "manager's is the scope: 'the rail is generated from his role rather than greyed'. "
    + "MOD-014 records the gap; closing it is scope resolution in the gate",
  "ADM-SCH-06": "work: MOD-019. The canvas draws name, capacity and equipment and says "
    + "'capacity here is the ceiling every class inherits'. `sch_resources` has `quantity` "
    + "-- how many of a thing there are -- capacity lives on a template's own policy per "
    + "class, and there is no equipment column at all, so the screen needs two columns "
    + "written before it has anything but the name to draw",
  "ADM-SCH-03": "work: MOD-019. Creating a template and publishing it are built and have no "
    + "form; what the canvas adds is the warning as the coach field changes -- 'Omar already "
    + "has PT at 19:00 Thursdays ... Dana and Yousef are both qualified and free'. The "
    + "conflict half is `conflicts.detect`, and 'qualified' needs a skill, which `skills` "
    + "leaves as the caller's word because nothing stores one",
  "ADM-SCH-05": "work: MOD-019 does not distinguish a personal-training session from a class "
    + "-- a session comes from a template, and a template is a service and a place. A PT "
    + "kind, and a booking that is one member rather than a roster, is what this needs",
  "ADM-SCH-07": "work: MOD-019 cancels a session and MOD-019's impact assessment already "
    + "counts the members affected. The canvas refuses to commit without choosing what they "
    + "get -- moving all eighteen to another session, or crediting each of them -- and "
    + "neither bulk remedy is a built operation in MOD-019 or MOD-020. MOD-013's dispatcher "
    + "is the seam the notification stops at, behind both",
  "ADM-MSH-06": "work: MOD-017's `change_plan` applies now, and the canvas takes effect on a "
    + "future date -- 'from 1 September, not today, she has paid for August at the higher "
    + "rate and keeps it'. A booked change needs a row and a job to apply it, which is the "
    + "same shape as the future-dated freeze MOD-017 refuses, and the worker runtime that "
    + "refusal was written without now exists",
  "ADM-MSH-09": "work: MOD-016 holds the plan and MOD-017 the agreements, and nothing counts "
    + "members per plan or splits them by commitment -- which is the canvas's whole argument: "
    + "'2,140 members are on this plan, 890 are inside a fixed-term commitment and keep "
    + "55.00'. A published price is immutable by privilege, so re-pricing is a new version "
    + "and the count is what tells somebody what that costs",
  "ADM-PAY-06": "work: MOD-017's `collections.py` decides from a fixed policy, and the canvas "
    + "configures it in sentence form -- the retry count, the hour it runs, the grace days, "
    + "the exception threshold. None of those is stored anywhere; MOD-005's typed "
    + "configuration registry is where a tenant-settable one would live",
  "ADM-STF-03": "work: MOD-007's registration is open, so there is no invitation in this "
    + "build at all -- no table, no token, no expiry, and nothing that accepts one. The role "
    + "and the clubs the canvas picks are MOD-008's assignment with its scope, which exists; "
    + "the record, its seven-day expiry and the accept are what has to be written, and "
    + "MOD-013's dispatcher is the seam the send at the end stops at",
  "ADM-RPT-05": "work: MOD-009 and MOD-008. The gate is a written reason recorded and "
    + "visible to the tenant, an option to leave contact details out, and a step-up before "
    + "the file is produced -- and nothing here exports anything, so the gate has nothing to "
    + "stand in front of. A button producing a file without that record would be the control "
    + "removed rather than the feature added, so the export and its recorded reason are one "
    + "piece of work",
  "ADM-SET-03": "work: MOD-017 takes a tax rate per line and MOD-016's tax category carries "
    + "no percentage, so the tax number and the 16% the canvas states have no column. The "
    + "JoFotara half is a MOD-012 definition and install nobody has registered -- the "
    + "submission counts the canvas shows are `int_connector_runs`, and 'Test connection' is "
    + "the `validated` state MOD-012 records as a claim by a named party. A live submission "
    + "needs an account at JoFotara, which is the seam this work stops at",
  "ADM-SET-07": "work: MOD-005. A tenant's languages, numeral system and first day of the "
    + "week are not settings this build carries -- the numeral system is latn everywhere, "
    + "and MOD-022's attendance report refuses to name a working week for the same reason. "
    + "MOD-005's typed registry with brand and location inheritance is where they go",
  "ADM-COM-03": "work: MOD-014 has no segments -- PPL-01-R05 names them beside tags and "
    + "custom fields, and a segment is a saved query this module has no language for, so "
    + "tags are the static half. MOD-013's dispatcher is the seam the send stops at, behind "
    + "that",
  "FD-02": "work: MOD-014. 'Name, phone, partial match, photo confirm' -- "
    + "`GET /people/contact-match` is the exact-match half and is deliberately exact, "
    + "because a mistyped digit finding somebody else is worse than finding nobody. A gated, "
    + "masked read by name over `ppl_contact_points_by_value` is this module's own work "
    + "rather than MOD-059's index; the 44px photo the canvas confirms identity by is where "
    + "the object store is the seam",
  "FD-07": "work: MOD-018. The count, the expected figure and the variance are built and are "
    + "`/payments/cash`, down to the three lines that add up to the figure by construction. "
    + "What this screen adds is the handover note, which the canvas argues is the point of it "
    + "-- 'part of the shift, not a WhatsApp message that leaves with the person who wrote "
    + "it' -- and no table holds one. The shift report it prints or emails is where MOD-013's "
    + "dispatcher is the seam",
  "FD-09": "client: the whole desk working with no connection is a service worker, state "
    + "held on the device and a queue of writes that survives the outage. This app is "
    + "server-rendered and has none of the three, and MOD-022's offline path is the "
    + "*reader's* -- a snapshot a turnstile decides against, not a browser's cache. Weeks of "
    + "work, and still work",
};

const EXTERNAL = [
  "payments:", "messaging:", "store:", "vault:", "identity:", "hardware:", "retention:",
  "owner-reserved:",
];

/**
 * The surfaces this check holds to the standard.
 *
 * **Declared rather than derived, so adding one is a decision somebody makes.** A surface
 * joins this list when every specified screen on it can be honestly accounted for -- which
 * means writing the reasons, not changing a filter. `Member`, `Coach`, `Console`, `POS` and
 * `POS admin` are not here: the Console is blocked behind CON-16's hardware-key sign-in,
 * there is no mobile client and no POS, and a list of forty excuses written in an afternoon
 * would be the "not built yet" this check exists to refuse, spelled four ways.
 */
const COVERED = ["Admin", "Front desk"];

const screens = JSON.parse(readFileSync(SCREENS, "utf8"));
const rows = Array.isArray(screens) ? screens : (screens.screens ?? []);
const inventory = readFileSync(INVENTORY, "utf8");
const catalogue = new Set(JSON.parse(readFileSync(CATALOGUE, "utf8")).map((m) => m.id));

/**
 * The screen ids the inventory *claims a route for*.
 *
 * **A mention anywhere in the file is not a claim**, and the first version counted one: the
 * file also tabulates the design sources, so `| `Veyro HF Front Desk and POS` | FD-01,
 * POS-01 |` made FD-01 read as built, and a sentence explaining that FD-02 is drawn in Batch
 * M did the same for FD-02. Two screens nobody has built passed a check written to find
 * exactly that -- the same false-coverage shape as a sweep whose filter excludes the thing it
 * is looking for.
 *
 * What a claim looks like is one of the three shapes this document commits in: a fidelity
 * table row, where the screen sits in the design column beside the route it was built at
 * (`| `/desk/classes/{id}` | FD-06 Class check-in | **built** … |`), and a section heading
 * that argues a screen's fidelity (`## ADM-STF-01 · ADM-STF-02 -- the team, and who can
 * still open the product`), and a per-screen bullet carrying the route in backticks, which
 * is how the five reports are argued one by one under a heading that names only the first and
 * the last. None of the three false claims above is any of those shapes.
 *
 * **A prose paragraph is deliberately not a claim**, even when it names the screen: the
 * document also argues, in bold, that `ADM-SCH-06` and `ADM-RPT-05` are *not* built. That
 * argument belongs in a list where the check can insist on a cause -- counting it here would
 * make "we wrote about why this is missing" indistinguishable from "we built it", which is
 * the distinction the whole file exists to keep.
 *
 * **The id pattern allows four letters in the middle segment.** It allowed three, which
 * silently excluded `ADM-AUTH-01` and `ADM-AUTH-02` -- so the sign-in and the step-up, both
 * built and both in the table, were reported as missing. A pattern that cannot match an id
 * is a check that reports a defect the app does not have, which costs the same trust as one
 * that misses a defect it does.
 */
const ID = /\b(?:ADM|FD|POS|CCH|MBR|CON)-[A-Z]{0,4}-?\d+\b/g;
const CLAIMED = new Set();
for (const line of inventory.split("\n")) {
  let claims = null;
  if (line.startsWith("#")) {
    claims = line;
  } else if (line.startsWith("|")) {
    const cells = line.split("|");
    if (cells.length >= 5) claims = cells[2];
  } else if (/`\/[^`]*`/.test(line)) {
    // A per-screen bullet: `- **ADM-RPT-02 · revenue** -- `/reports/revenue`, over a new …`.
    // The route in backticks is what makes it a claim rather than an argument about a gap --
    // the section heading above those five names only the first and the last of them.
    claims = line;
  }
  if (claims === null) continue;
  for (const id of claims.matchAll(ID)) CLAIMED.add(id[0]);
}

const named = (id) => CLAIMED.has(id);
const built = (mod) => existsSync(BACKEND + PACKAGE[mod]);
const MOD = /\bMOD-\d{3}\b/g;

const covered = rows.filter((row) => COVERED.includes(row.surface) && row.specified);
const uncovered = {};
for (const row of rows) {
  if (!row.specified || COVERED.includes(row.surface)) continue;
  uncovered[row.surface] = (uncovered[row.surface] ?? 0) + 1;
}

const problems = [];
const counted = { named: 0, state: 0, blocked: 0, backlog: 0 };
const why = { blocked: {}, backlog: {} };

/** Every module id a reason names has to be one this check can look up. */
const mapped = (id, reason) => {
  for (const [mod] of reason.matchAll(MOD)) {
    if (!(mod in PACKAGE)) {
      problems.push(
        `${id}'s reason names ${mod}, which is not in PACKAGE. Add it with the package it `
        + "creates when it is built, so the claim about it can be checked.");
    }
  }
};

for (const row of covered) {
  const id = row.id;
  const elsewhere = [
    id in BLOCKED ? "a BLOCKED reason" : null,
    id in BACKLOG ? "a BACKLOG reason" : null,
    id in STATE_OF ? `a state of ${STATE_OF[id]}` : null,
  ].filter(Boolean);

  // One list each, so a screen cannot be blocked and backlogged at once -- which is the
  // ambiguity the single list allowed, read from the other side.
  if (elsewhere.length > 1) {
    problems.push(`${id} carries ${elsewhere.join(" and ")}. It belongs in one list.`);
  }

  if (named(id)) {
    // **Both directions**: an excuse for a screen the inventory now claims is a stale
    // excuse, and this repository has shipped exactly that failure once already.
    for (const where of elsewhere) {
      problems.push(`${id} is named in the inventory and still carries ${where}. Remove it.`);
    }
    counted.named += 1;
    continue;
  }
  if (id in STATE_OF) {
    const parent = STATE_OF[id];
    if (!named(parent)) {
      problems.push(
        `${id} is a state of ${parent}, which is not named in the inventory either. `
        + "A state cannot stand in for a screen nobody built.");
    }
    counted.state += 1;
    continue;
  }
  if (id in BLOCKED) {
    const reason = BLOCKED[id];
    const cause = EXTERNAL.find((c) => reason.startsWith(c));
    if (cause === undefined) {
      problems.push(
        `${id}'s BLOCKED reason does not name an external cause. It must begin with one of `
        + `${EXTERNAL.join(" ")} -- a blocker is external or it is not a blocker, and `
        + "work this session can do belongs in BACKLOG.");
    }
    mapped(id, reason);
    why.blocked[cause ?? "?"] = (why.blocked[cause ?? "?"] ?? 0) + 1;
    counted.blocked += 1;
    continue;
  }
  if (id in BACKLOG) {
    const reason = BACKLOG[id];
    const external = EXTERNAL.find((c) => reason.startsWith(c));
    if (external !== undefined) {
      problems.push(
        `${id}'s BACKLOG reason begins with ${external}, which is an external cause. `
        + "Move it to BLOCKED, or say which module the work is in.");
    }
    mapped(id, reason);
    let kind = null;
    const owner = reason.match(/^(MOD-\d{3}):/);
    if (owner !== null) {
      kind = owner[1];
      if (!catalogue.has(kind)) {
        problems.push(`${id} names ${kind}, which is not a module in the catalogue.`);
      } else if (built(kind)) {
        // The stale half: the module landed and the screen still reads as waiting for it.
        problems.push(
          `${id} waits on ${kind}, whose package backend/app/${PACKAGE[kind]}/ exists. `
          + "The module is built -- build the screen, or say what work is left in it.");
      }
    } else if (reason.startsWith("work:")) {
      kind = "work:";
      // **The first sentence, not the paragraph**, and the sweep is what settled that. The
      // first version asked whether a built module was named anywhere in the reason, which
      // every one of these satisfies in passing -- MOD-013 as the seam a send stops at,
      // MOD-022 as the precedent for refusing to name a working week -- so no mutation could
      // trip it: swapping the module the work is *in* left two more behind and the check
      // still passed. A guard that cannot be broken on purpose is not evidence, and here the
      // unprovable form was also the weak one: "mentions a module" is not "says where the
      // work is". The first sentence is where it says that, so that is what is read, and
      // every module in it has to be built -- one that is not means the screen is waiting on
      // a module rather than on work inside one, and belongs under that module's id.
      const sentence = reason.split(/(?<=\.)\s/)[0];
      const here = [...sentence.matchAll(MOD)].map(([mod]) => mod);
      if (here.length === 0) {
        problems.push(
          `${id}'s reason says work: and its first sentence names no module. Say which `
          + "module the work is in, or name the unbuilt module that owns the screen instead.");
      }
      for (const mod of here) {
        if (mod in PACKAGE && !built(mod)) {
          problems.push(
            `${id} puts the work in ${mod}, which is not built -- backend/app/`
            + `${PACKAGE[mod]}/ does not exist. A screen waiting on a module belongs under `
            + "that module's id, not under work:.");
        }
      }
    } else if (reason.startsWith("client:")) {
      kind = "client:";
    } else {
      problems.push(
        `${id}'s BACKLOG reason does not say where the work lives. It must begin with a `
        + "MOD-0NN the catalogue knows, or work:, or client:.");
    }
    why.backlog[kind ?? "?"] = (why.backlog[kind ?? "?"] ?? 0) + 1;
    counted.backlog += 1;
    continue;
  }
  problems.push(
    `${id} (${row.name}) is specified, is not in the inventory, is not a state of a built `
    + "screen, and has no reason. Build it, or write down what is missing.");
}

// And the lists cannot name screens the design does not specify, which is how a list rots
// quietly: an id that was renamed upstream would sit here for ever looking like coverage.
const ids = new Set(covered.map((row) => row.id));
for (const [id, parent] of Object.entries(STATE_OF)) {
  if (!ids.has(id)) {
    problems.push(`STATE_OF names ${id}, which is not a specified screen on a covered surface.`);
  }
  if (!ids.has(parent) && !named(parent)) {
    problems.push(`STATE_OF points ${id} at ${parent}, which is not a specified screen.`);
  }
}
for (const [list, entries] of [["BLOCKED", BLOCKED], ["BACKLOG", BACKLOG]]) {
  for (const id of Object.keys(entries)) {
    if (!ids.has(id)) {
      problems.push(`${list} names ${id}, which is not a specified screen on a covered surface.`);
    }
  }
}
// PACKAGE is a claim about the catalogue, so it is checked against it rather than trusted.
for (const mod of Object.keys(PACKAGE)) {
  if (!catalogue.has(mod)) {
    problems.push(`PACKAGE names ${mod}, which is not a module in the catalogue.`);
  }
}

if (problems.length > 0) {
  console.error("design:coverage FAILED\n  " + problems.join("\n  "));
  process.exit(1);
}

const tally = (counts) => Object.entries(counts)
  .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
  .map(([key, count]) => `${key.replace(/:$/, "")} ${count}`)
  .join(", ");
const outside = Object.entries(uncovered)
  .sort((a, b) => b[1] - a[1])
  .map(([surface, count]) => `${surface} ${count}`)
  .join(", ");
console.log(
  `design:coverage ok -- ${covered.length} specified screens on ${COVERED.join(" and ")}: `
  + `${counted.named} in the inventory, ${counted.state} states of those, ${counted.blocked} `
  + `blocked on something external, ${counted.backlog} in the backlog.\n`
  + `  blocked: ${tally(why.blocked)}\n`
  + `  backlog: ${tally(why.backlog)}\n`
  + `  not covered: ${outside}`,
);
