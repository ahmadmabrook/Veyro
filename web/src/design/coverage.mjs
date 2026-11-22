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
 * A screen passes if one of three things is true:
 *
 *   1. **The inventory names it.** `contracts/ui/design-compliance.md` mentions its id, which
 *      is where a built screen's fidelity is argued.
 *   2. **It is a state of a screen that is built.** `STATE_OF` maps it to that screen's id,
 *      which must itself be accounted for — so a state cannot stand in for a missing screen.
 *   3. **`BLOCKED` gives a reason.** Not a status: a sentence naming what is missing, and
 *      every reason is checked against a closed set of causes, because "not built yet" is
 *      not a reason and is exactly what this check exists to refuse.
 *
 * Both directions, because this repository's own rule is that a check in one direction is
 * half a check: an entry for a screen that is now built fails too, so the list cannot carry
 * a stale excuse. That is the failure mode the schedule board shipped — a gap note that
 * outlived its gap by one change, which an independent tester then read and believed.
 */

import { readFileSync } from "node:fs";

const SCREENS = new URL("./screens.generated.json", import.meta.url).pathname;
const INVENTORY = new URL("../../../contracts/ui/design-compliance.md", import.meta.url)
  .pathname;

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
 * Why a screen is not built, in the words of what is actually missing.
 *
 * **Every reason names one of four causes**, and the check enforces that vocabulary:
 *
 *   - `module:` — it needs a backend module this repository does not have.
 *   - `owner-reserved:` — it moves real money, which the owner reserves and no form in this
 *     app may do. Naming what it would move is required.
 *   - `data:` — the backend exists and does not hold what the screen draws, so the screen as
 *     drawn would have invented columns. ADM-SCH-06 is the worked example.
 *   - `store:` — it needs an object store and a residency decision, both unmade.
 *
 * "Not built yet" is not a cause and there is deliberately no token for it.
 */
const BLOCKED = {
  "ADM-CC-07": "module: a resolution history needs a record of what was resolved and when, "
    + "which no module keeps -- the Command Center's queue is derived from live state",
  // **Thirteen screens were accounted for by a mention rather than a claim**, and these are
  // the seven Admin ones. `named` asked whether the inventory contained the id anywhere, so a
  // design-sources row, a cross-reference in another screen's "still open" list and a bold
  // paragraph arguing a screen is *not* built all read as coverage -- including ADM-SCH-06,
  // which this file's own docstring calls the worked example of `data:` and which had no
  // reason here at all.
  "ADM-CC-02": "data: the canvas is a club manager's Command Center, and what makes it that "
    + "screen is the scope -- 'the rail is generated from his role rather than greyed'. Both "
    + "`permit` and `held_permissions` resolve against the tenant-wide default scope, so a "
    + "brand- or location-scoped role is refused every read rather than shown its own club. "
    + "MOD-014 records that gap; until it closes, this screen is the owner's page with a "
    + "narrower rail, which is a different claim",
  "ADM-CC-06": "data: a side sheet holds per-item state -- what was resolved, by whom, when, "
    + "and what is still open on it -- and no module keeps a resolution record. The queue is "
    + "derived from live state, which is why ADM-CC-07 is blocked for the same reason",
  "ADM-CRM-01": "module: CRM. The pipeline, its stages and a lead's movement between them are "
    + "its, and `lifecycle_state` on a person is the only part of it here",
  "ADM-SCH-06": "data: the canvas draws name, capacity and equipment and says 'capacity here "
    + "is the ceiling every class inherits'. `sch_resources` has `quantity` -- how many of a "
    + "thing there are -- capacity lives on a template's own policy per class, and there is "
    + "no equipment column at all, so the screen as drawn would have one real column and two "
    + "invented ones",
  "ADM-STF-03": "module: there is no invitation in this build at all -- no table, no token, "
    + "no expiry, and nothing that sends. MOD-007's registration is open instead, so an "
    + "invitation is a mechanism rather than a form, and the message it ends in needs the "
    + "dispatcher MOD-013 does not have",
  "ADM-AUT-02": "module: automation",
  "ADM-RPT-05": "data: the gate is a written reason recorded and visible to the tenant, an "
    + "option to leave contact details out, and a step-up before the file is produced. "
    + "Nothing here exports anything, so the gate has nothing to stand in front of -- and a "
    + "button producing a file without that record would be the control removed rather than "
    + "the feature added",

  // The Front Desk surface, which `COVERED` reaches for the first time. Three are built;
  // these six are what is left, and each names what is actually missing rather than its
  // position in a queue.
  "FD-01": "owner-reserved: the canvas's live queue resolves at the door and its primary "
    + "action is 'Take JOD 55.00', with 'Send link instead' beside it -- a payment and a "
    + "message, and this build has no provider for either. The 40px face on every row needs "
    + "an object store as well, and what is left without those two is ADM-ACC-02's decision "
    + "log with FD-03 hanging off it, which both exist",
  "FD-02": "module: search. The canvas is 'name, phone, partial match, photo confirm' and "
    + "MOD-014 deliberately has none -- paragraph 4218's permission-aware index is ENG-01's, "
    + "and `GET /people/contact-match` is an exact match by design, because a mistyped digit "
    + "finding somebody else is worse than finding nobody. The 44px photo the canvas confirms "
    + "identity by needs an object store",
  "FD-04": "owner-reserved: 'Take 8.00 & open the gate'. There is no day-pass product, no "
    + "guest credential issuance and no payment provider, and the waiver version the canvas "
    + "stores with the record has no column -- MOD-009's consent documents are the nearest "
    + "thing and are not wired to a sale",
  "FD-05": "module: CRM. 'Creates a lead already in trial with the clock running, a "
    + "credential, and an app invitation by text. Yasmin picks it up on her pipeline within "
    + "the minute' -- the pipeline is ADM-CRM-01's, nothing starts a trial clock on a "
    + "membership, and the invitation by text needs the dispatcher MOD-013 does not have",
  "FD-07": "data: the count, the expected figure and the variance are built and are "
    + "`/payments/cash`. What this screen adds is the handover note, which the canvas argues "
    + "is the point of it -- 'part of the shift, not a WhatsApp message that leaves with the "
    + "person who wrote it' -- and no table holds one; the shift report it prints or emails "
    + "needs the same dispatcher",
  "FD-09": "client: the whole desk working with no connection is a service worker, state held "
    + "on the device and a queue of writes that survives the outage. This app is "
    + "server-rendered and has none of the three, and MOD-022's offline path is the "
    + "*reader's* -- a snapshot a turnstile decides against, not a browser's cache",
  "ADM-CRM-02": "module: CRM. There is no lead in this build",
  "ADM-CRM-03": "module: CRM",
  "ADM-CRM-04": "module: CRM",
  "ADM-CRM-06": "module: CRM",
  "ADM-CRM-07": "module: CRM",
  "ADM-MEM-08": "store: documents need an object store and a residency decision, the same "
    + "wall MOD-009's export and MOD-014's progress media hit",
  "ADM-MSH-01": "owner-reserved: selling a membership ends in taking a payment, which moves "
    + "real money, and there is no payment provider in this build",
  "ADM-MSH-02": "owner-reserved: the canvas's action is 'Take 795.60' after a price-change "
    + "disclosure. Renewing is taking a payment, and there is no provider here",
  "ADM-MSH-04": "owner-reserved: the canvas's action is 'Resume, take 30.19' -- a pro-rata "
    + "charge. The resume itself is built and the unused freeze days do return to the "
    + "allowance; the charge is the act the button names",
  "ADM-MSH-05": "owner-reserved: an upgrade is priced and charged on the spot, and the "
    + "proration MOD-017 computes ends in a payment nothing here can take",
  "ADM-MSH-06": "data: the canvas takes effect on a future date -- 'from 1 September, not "
    + "today, she has paid for August at the higher rate and keeps it' -- and `change_plan` "
    + "applies now. Nothing books a plan change for a later date, which is the same refusal "
    + "MOD-017 makes about a future-dated freeze",
  "ADM-MSH-07": "data: the canvas discloses a cancellation fee the member acknowledges and "
    + "then the notice period runs. Nothing here applies a cancellation when its notice "
    + "expires -- `membership_as_of` is the function that tells the truth",
  "ADM-MSH-09": "data: the canvas's whole argument is the blast radius -- '2,140 members are "
    + "on this plan, 890 are inside a fixed-term commitment and keep 55.00' -- and nothing "
    + "counts members per plan or splits them by commitment",
  "ADM-PAY-02": "owner-reserved: approving a refund moves money out, and MOD-017 requires "
    + "two people by design -- the approver may not be the requester",
  "ADM-PAY-04": "owner-reserved: taking a card is real money, and there is no payment "
    + "provider and no stored payment method in this build",
  "ADM-PAY-06": "data: the canvas configures the dunning policy in sentence form -- the "
    + "retry count, the hour it runs, the grace days, the exception threshold -- and none of "
    + "those is stored anywhere. `collections.py` decides from a fixed policy",
  "ADM-PAY-08": "owner-reserved: a refund moves money out, and MOD-017 requires two people "
    + "by design -- the approver may not be the requester",
  "ADM-SCH-03": "data: the canvas warns as the coach field changes -- 'Omar already has PT "
    + "at 19:00 Thursdays ... Dana and Yousef are both qualified and free' -- and `skills` "
    + "is the caller's word here, so 'qualified' is a fact nothing stores",
  "ADM-SCH-05": "data: a personal-training session is not a kind this build distinguishes "
    + "from a class -- a session comes from a template, and a template is a service and a "
    + "place",
  // **Read the canvas before writing the reason.** The first version of this entry said
  // "stepped-up", which is true of the permission and is not what blocks the screen. The
  // canvas's own rule is "cannot commit without choosing what the members get. A
  // cancellation that notifies nobody is the most damaging thing this screen could permit,
  // so the notification is the action rather than a follow-up" -- and it offers two
  // remedies, moving all eighteen to another session or crediting each of them. MOD-013
  // authors and never sends, and neither bulk remedy exists anywhere.
  "ADM-SCH-07": "module: a messaging provider, and a bulk transfer or bulk credit. The "
    + "canvas makes the notification the action and refuses to commit without choosing what "
    + "the members get; MOD-013 sends nothing and neither remedy is a built operation",
  "ADM-COM-03": "module: broadcast needs a segment, and PPL-01-R05's segments are unbuilt",
  "ADM-TSK-01": "module: tasks",
  "ADM-AUT-01": "module: automation",
  "ADM-AUT-03": "module: automation",
  "ADM-COM-01": "module: a messaging provider. MOD-013 authors and never sends, and there is "
    + "no inbound receiver at all -- a conversation needs both halves",
  "ADM-SET-03": "module: a tax engine and a JoFotara connector. MOD-017 records that a "
    + "document was fiscalized and takes the rate from the caller; nothing computes one",
  "ADM-SET-04": "module: a payment provider. Taking a card is owner-reserved and nothing "
    + "here stores a payment method",
  "ADM-SET-06": "store: branding assets need an object store and a residency decision, the "
    + "same wall MOD-009's export hits",
  "ADM-SET-07": "data: a tenant's locale, numeral system and first day of the week are not "
    + "settings this build carries -- the numeral system is latn everywhere and the "
    + "attendance report refuses to name a working week for the same reason",
  "ADM-AI-01": "module: there is no AI surface in this build, and MOD-008 classifies AI "
    + "acting for a member as privileged, which needs an assurance level nobody can reach",
  "ADM-SRCH-01": "module: search is ENG-01's, and a LIKE scan presented as search would be a "
    + "read path with no freshness contract and no permission pre-filter",
};

/**
 * **`stepped-up:` was a cause and is not one any more.** Twelve screens carried it, on the
 * reasoning that "a button that answered 403 is worse than its absence" -- which is true of
 * a button that just fails and says nothing about one that offers the step-up first, as this
 * app already did for a masked *read*. ADM-MSH-03 proved it: the figure bounding the act
 * reads on the routine permission, the act offers `/step-up` with `next` back, and the cost
 * is one recovery code per twelve-hour window rather than one per act.
 *
 * So the token is gone and every screen that carried it was re-derived against its own
 * canvas. Most turned out to be blocked by something real and quite different -- money this
 * build may not move, or a figure it does not hold -- and one, ADM-MEM-10, was blocked by
 * nothing at all and has to be built. **Removing a cause from this list is how that gets
 * found**, which is the argument for the list being short and for every entry naming a
 * thing rather than a permission.
 */
const CAUSES = ["module:", "owner-reserved:", "data:", "store:", "client:"];

/**
 * The surfaces this check holds to the standard.
 *
 * **Declared rather than derived, so adding one is a decision somebody makes.** A surface
 * joins this list when every specified screen on it can be honestly accounted for -- which
 * means writing six reasons, not changing a filter. `Member`, `Coach`, `Console`, `POS` and
 * `POS admin` are not here: the Console is blocked behind CON-16's hardware-key sign-in,
 * there is no mobile client and no POS, and a list of forty excuses written in an afternoon
 * would be the "not built yet" this check exists to refuse, spelled four ways.
 */
const COVERED = ["Admin", "Front desk"];

const screens = JSON.parse(readFileSync(SCREENS, "utf8"));
const rows = Array.isArray(screens) ? screens : (screens.screens ?? []);
const inventory = readFileSync(INVENTORY, "utf8");

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
 * argument belongs in `BLOCKED`, where the check can insist on a cause -- counting it here
 * would make "we wrote about why this is missing" indistinguishable from "we built it",
 * which is the distinction the whole file exists to keep.
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

const covered = rows.filter((row) => COVERED.includes(row.surface) && row.specified);
const uncovered = {};
for (const row of rows) {
  if (!row.specified || COVERED.includes(row.surface)) continue;
  uncovered[row.surface] = (uncovered[row.surface] ?? 0) + 1;
}

const problems = [];
const counted = { named: 0, state: 0, blocked: 0 };

for (const row of covered) {
  const id = row.id;
  if (named(id)) {
    // **Both directions**: an excuse for a screen the inventory now argues is a stale
    // excuse, and this repository has shipped exactly that failure once already.
    if (id in BLOCKED) {
      problems.push(
        `${id} is named in the inventory and still carries a BLOCKED reason. Remove it.`);
    }
    if (id in STATE_OF) {
      problems.push(
        `${id} is named in the inventory and still listed as a state of ${STATE_OF[id]}. `
        + "Remove it from STATE_OF.");
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
    if (!CAUSES.some((cause) => reason.startsWith(cause))) {
      problems.push(
        `${id}'s reason does not name a cause. It must begin with one of `
        + `${CAUSES.join(" ")} -- "not built yet" is not a reason.`);
    }
    counted.blocked += 1;
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
for (const id of Object.keys(BLOCKED)) {
  if (!ids.has(id)) {
    problems.push(`BLOCKED names ${id}, which is not a specified screen on a covered surface.`);
  }
}

if (problems.length > 0) {
  console.error("design:coverage FAILED\n  " + problems.join("\n  "));
  process.exit(1);
}

const outside = Object.entries(uncovered)
  .sort((a, b) => b[1] - a[1])
  .map(([surface, count]) => `${surface} ${count}`)
  .join(", ");
console.log(
  `design:coverage ok -- ${covered.length} specified screens on ${COVERED.join(" and ")}: `
  + `${counted.named} in the inventory, ${counted.state} states of those, ${counted.blocked} `
  + `blocked with a reason. Not covered: ${outside}`,
);
