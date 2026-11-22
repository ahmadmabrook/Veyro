#!/usr/bin/env node
/**
 * Every specified Admin screen is accounted for, or a reason is written down.
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
const CAUSES = ["module:", "owner-reserved:", "data:", "store:"];

const screens = JSON.parse(readFileSync(SCREENS, "utf8"));
const rows = Array.isArray(screens) ? screens : (screens.screens ?? []);
const inventory = readFileSync(INVENTORY, "utf8");

const admin = rows.filter((row) => row.surface === "Admin" && row.specified);
const named = (id) => inventory.includes(id);

const problems = [];
const counted = { named: 0, state: 0, blocked: 0 };

for (const row of admin) {
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
const ids = new Set(admin.map((row) => row.id));
for (const [id, parent] of Object.entries(STATE_OF)) {
  if (!ids.has(id)) problems.push(`STATE_OF names ${id}, which is not a specified Admin screen.`);
  if (!ids.has(parent) && !named(parent)) {
    problems.push(`STATE_OF points ${id} at ${parent}, which is not a specified screen.`);
  }
}
for (const id of Object.keys(BLOCKED)) {
  if (!ids.has(id)) problems.push(`BLOCKED names ${id}, which is not a specified Admin screen.`);
}

if (problems.length > 0) {
  console.error("design:coverage FAILED\n  " + problems.join("\n  "));
  process.exit(1);
}

console.log(
  `design:coverage ok -- ${admin.length} specified Admin screens: ${counted.named} in the `
  + `inventory, ${counted.state} states of those, ${counted.blocked} blocked with a reason`,
);
