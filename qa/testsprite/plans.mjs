/**
 * The TestSprite plans for the Admin UI, generated from the live fixture.
 *
 * **Generated rather than committed, because one field in them rotates.** The fixture's
 * identity and password are constants in `web/tests/e2e/fixture.mjs` -- `admin@veyro.invalid`
 * at an invalid TLD, with a throwaway password for a tenant that is recreated from scratch on
 * every run -- but the tenant id is a fresh uuid each time, and the sign-in form asks for it.
 * A plan with last week's tenant id in it is a test that fails for a reason that has nothing
 * to do with the product.
 *
 * So this reads `web/.env.e2e.local` (mode 600, gitignored) and writes the plans into a
 * scratch directory. What is committed is this file and whatever result the run produced.
 *
 * **A test created from a plan carries that tenant id for ever**, because a plan is static
 * text on TestSprite's side. So re-running the fixture invalidates every test already
 * created: they will reach the sign-in form and be refused by a tenant that no longer
 * exists, which looks exactly like a product defect. Regenerate and `--create` again after
 * any fixture run, and run the new ids.
 *
 * **What TestSprite is for here, and what it is not.** The owner's directive makes it a
 * mandatory independent layer, and the value is exactly that it is independent: these plans
 * are written in English against what a person would do, and the agent that executes them
 * has never seen this repository's selectors, its fixture or its assumptions. A Playwright
 * spec and the page it tests were written by the same hand on the same day. It does not
 * replace the browser suite, the component tests or the visual comparison -- a TestSprite
 * pass says a journey works, not that a screen matches its canvas.
 *
 *   node qa/testsprite/plans.mjs            # write the plans
 *   node qa/testsprite/plans.mjs --create   # and create them in the project
 *
 * **Two of the first four runs failed and one of them was a real finding.** The masked-field
 * journey asserted that the member's own name was readable; it is not, because an identity
 * field needs a stepped-up session and a name is one -- so the plan was wrong about the
 * product. What the tester did next is the finding: it clicked the withheld marker looking
 * for a way through, and on the members *list* there was none. The remedy existed only on a
 * member's record. That is the value of a layer that has not read this repository.
 *
 * Then, with the app running on :3000:
 *
 *   testsprite test run <id> --local 3000 --wait
 *
 * `--local` opens a tunnel for the run and points the runner at this machine's loopback.
 * The project's own target URL is `https://example.com` -- IANA's reserved documentation
 * domain, a deliberate placeholder -- because a project needs a publicly resolvable URL and
 * every run here overrides it with the tunnel. A run that forgot `--local` reaches a page
 * that is nobody's.
 */

import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const PROJECT = process.env.TESTSPRITE_PROJECT_ID ?? "6aad5672-2129-465b-950b-0b8e276c7300";
const ROOT = new URL("../../", import.meta.url).pathname;
const OUT = process.env.PLANS_OUT ?? "/tmp/claude-501/veyro-testsprite";

const env = Object.fromEntries(
  readFileSync(join(ROOT, "web/.env.e2e.local"), "utf8")
    .split("\n")
    .filter((line) => line.includes("=") && !line.startsWith("#"))
    .map((line) => [line.slice(0, line.indexOf("=")), line.slice(line.indexOf("=") + 1)]),
);

/**
 * Sign in as somebody.
 *
 * **Which identity a journey uses is part of the journey**, and getting that wrong is how
 * the reports-gate plan failed three times against a product that was right. Its
 * `description` quoted the canvas -- "A Club Manager opening this screen sees four reports,
 * not six" -- while its steps signed in as the owner, and the tester did exactly what the
 * description said: it checked the financial reports were absent, for a session holding
 * every permission in the catalogue, and reported them present.
 *
 * The description is not a comment. The agent reads it as the specification, which is the
 * point of writing plans in English, and a description that describes a different session
 * from the one the steps open is a plan that contradicts itself.
 */
const signInAs = (email, password) => [
  {
    type: "action",
    description:
      `Navigate to /login. Fill the field labelled "Tenant ID" with ` +
      `${env.VEYRO_E2E_TENANT_ID}, the field labelled "Email or phone" with ` +
      `${email}, and the field labelled "Password" with ${password}. ` +
      `Click the "Sign in" button.`,
  },
];

/** The owner: every permission in the catalogue. */
const signIn = signInAs(env.VEYRO_E2E_EMAIL, env.VEYRO_E2E_PASSWORD);

/** The front desk: `people.person.read` and nothing of the money modules. */
const signInAsDesk = signInAs(env.VEYRO_E2E_DESK_EMAIL, env.VEYRO_E2E_DESK_PASSWORD);

/**
 * The four journeys, chosen for what they prove that the in-repo suites cannot.
 *
 * Each one is a question a person would ask of the product, written without naming a CSS
 * class: the point of an independent layer is that it reads what is on the screen.
 */
const PLANS = [
  {
    // **ADM-STF-01's whole reason for existing, as a question a person would ask.** The
    // canvas's own footnote says the LAST SEEN column exists "so a departed employee with a
    // live login is visible rather than discovered", and the page composes three planes to
    // answer it. An independent agent reading the screen is the right check: the in-repo
    // spec and the page were written by the same hand on the same day, and the fixture seeds
    // one person in each of four standings precisely so the distinction is visible.
    name: "Somebody who has left the company but can still sign in is visible on the staff list",
    description:
      "The staff list exists to make one thing impossible to miss: an employee whose " +
      "employment has ended and whose login still works. This signs in as the owner and " +
      "reads the list. Names are deliberately hidden on an ordinary sign-in, so people are " +
      "identified by their job title and start date.",
    priority: "p1",
    planSteps: [
      ...signIn,
      { type: "action", description: "Navigate to /staff." },
      {
        type: "assertion",
        description:
          "Verify the page warns, above or around the table, that one person whose " +
          "employment has ended can still sign in, and says that ending employment does " +
          "not revoke anything. Verify the table has a row for a Sales person who started " +
          "on 2024-09-02 whose access reads that they have left and can still sign in, and " +
          "a separate row for a Coach who started on 2023-04-17 whose access reads only " +
          "that they have left. Verify those two rows say different things about access.",
      },
      {
        type: "assertion",
        description:
          "Verify the page offers no button to invite anybody, and explains that there is " +
          "no invitation in this build at all. Verify it also states that a club manager " +
          "seeing only their own club's staff is not true in this build.",
      },
    ],
  },
  {
    // ADM-STF-02, and specifically the half a single-scope read could not answer.
    name: "One person's record says what they can do that is dangerous, and where",
    description:
      "A staff record lists the permissions that are financial or privileged, what each " +
      "costs to use, which role carries it, and where it applies. Some of this person's " +
      "access is tenant-wide and one grant applies at a single club only; both must be " +
      "distinguishable. This signs in as the owner and opens the record of the Reception " +
      "person who started on 2025-01-06, from the staff list.",
    priority: "p1",
    planSteps: [
      ...signIn,
      { type: "action", description: "Navigate to /staff." },
      {
        type: "action",
        description:
          "Open the record of the person whose job title is Reception and whose start date " +
          "is 2025-01-06, by clicking their row's link in the Name column.",
      },
      {
        type: "assertion",
        description:
          "Verify the record shows a section listing what this person can do that is " +
          "dangerous. Verify at least one entry says it applies everywhere, and that the " +
          "entry about adding value to a member's wallet says it applies at a named club " +
          "rather than everywhere. Verify each entry also says it needs a stronger sign-in " +
          "and names the role it comes from.",
      },
      {
        type: "assertion",
        description:
          "Verify the record shows a section for grants beyond this person's role with at " +
          "least one entry naming who granted it and on what date. Verify the page states " +
          "that changing any of this needs a stronger sign-in and is recorded, and that " +
          "you cannot grant a permission you do not hold yourself. Verify there is no " +
          "button to save changes and no button to end access.",
      },
    ],
  },
  {
    name: "Signing in reaches the Command Center, not a session diagnostic",
    description:
      "The owner's directive opened with this screen being the wrong screen. It is a queue " +
      "of things needing attention with four figures above it, and it must not be a page " +
      "about the session.",
    priority: "p1",
    planSteps: [
      ...signIn,
      {
        type: "assertion",
        description:
          "Verify the page that loads after signing in has a heading about things needing " +
          "attention this morning, shows four labelled figures across the top (collected, " +
          "active members, visits today and lead conversion), and lists items to act on " +
          "with categories such as MONEY, COMPLIANCE, RETENTION and STAFFING. Verify it " +
          "does NOT show a list of the current session's permissions or session details.",
      },
    ],
  },
  {
    name: "A report a front-desk session cannot open is absent, not locked",
    description:
      "ADM-RPT-01's gate, tested as the canvas states it: a session without the money " +
      "permissions must not see the financial reports listed, and must not see them listed " +
      "and disabled either. This signs in as the front desk, which holds the person read " +
      "and nothing of the money modules.",
    priority: "p1",
    planSteps: [
      ...signInAsDesk,
      { type: "action", description: "Navigate to /reports." },
      {
        type: "assertion",
        description:
          "Verify the Revenue report is NOT listed on this page, and that no report is " +
          "shown greyed out, disabled or marked as locked. Verify the page still names the " +
          "reports the design lists that this build cannot produce at all — coaching, " +
          "leads and tax — each with a stated reason, and that it says the empty " +
          "list is about this session's own access.",
      },
    ],
  },
  {
    name: "The owner, who holds everything, is listed every built report",
    description:
      "The other half of the gate: a session that may open a report sees it as a link with " +
      "a one-line description, not greyed out.",
    priority: "p1",
    planSteps: [
      ...signIn,
      { type: "action", description: 'Open the "Reports" entry in the left navigation.' },
      {
        type: "assertion",
        description:
          "Verify the page lists a Revenue report, a Membership report and an Attendance " +
          "report, each as a clickable link with a one-line description, and that none is " +
          "greyed out or marked as locked.",
      },
    ],
  },
  {
    name: "The attendance report names the actionable hour in words",
    description:
      "ADM-RPT-04's own note is the requirement rather than a styling remark: the " +
      "conclusion is written in words beneath the chart, because a manager should not have " +
      "to interpret a heat strip to find the actionable hour. The club is in Amman, which " +
      "is three hours ahead of UTC, so the hours on this page are also the one place a " +
      "server that bucketed on the raw instant would be visibly wrong.",
    priority: "p1",
    planSteps: [
      ...signIn,
      { type: "action", description: 'Navigate to /reports and open the "Attendance" report.' },
      {
        type: "assertion",
        description:
          "Verify the page shows a bar chart of visits by hour with an axis running from " +
          "00:00 to 23:00, and that beneath the chart there is a sentence naming the " +
          "busiest window as 18:00 to 20:00 and the quietest hour that sees anybody as " +
          "07:00 with the percentage of the peak it runs at. Verify the page names the " +
          "club's own timezone (Asia/Amman). Verify the page states that every share on it " +
          "is a share of the busiest hour and never of a zone's capacity, and gives the " +
          "reason. Verify there is no Export button anywhere on the page.",
      },
      {
        type: "action",
        description:
          'Use the day-range controls on the page to switch from "All days" to "Sun–Thu".',
      },
      {
        type: "assertion",
        description:
          "Verify the chart and the figures reload for the narrower set of days, that the " +
          "chosen range is marked as the current one, and that no control on the page is " +
          "labelled \"Weekdays\" or \"Weekend\" — the page should instead say that nothing " +
          "in this build declares which days are a working week.",
      },
    ],
  },
  {
    name: "The revenue report separates collected from invoiced",
    description:
      "ADM-RPT-02's whole argument: a report showing one number labelled 'revenue' is why " +
      "operators cannot reconcile their own books.",
    priority: "p1",
    planSteps: [
      ...signIn,
      { type: "action", description: 'Navigate to /reports and open the "Revenue" report.' },
      {
        type: "assertion",
        description:
          "Verify the report shows four separate money figures labelled COLLECTED, " +
          "INVOICED, OUTSTANDING and REFUNDED, and that collected and invoiced are not the " +
          "same number. Verify there is a table breaking revenue down by source whose rows " +
          "name parts of the business (for example Memberships) and whose Total row equals " +
          "the sum of the rows above it.",
      },
    ],
  },
  {
    name: "A withheld field on a member's record is marked, never blank",
    description:
      "MOD-014 applies the gate's masked-field list and this surface renders it. An empty " +
      "cell is indistinguishable from 'there was nothing here', which is the one reading " +
      "that is always wrong.",
    priority: "p1",
    planSteps: [
      ...signIn,
      { type: "action", description: "Navigate to /members and open the first member in the list." },
      {
        type: "assertion",
        description:
          "Verify that any field the page is withholding is shown as withheld with a stated " +
          "reason — for example that it needs a stronger sign-in, or that nobody in this " +
          "build can read it — rather than being left blank or omitted. Members' names are " +
          "themselves withheld on this session and that is correct, so verify the page " +
          "offers a link to sign in more strongly rather than leaving the reader with no " +
          "way through.",
      },
    ],
  },
];

mkdirSync(OUT, { recursive: true });
const written = PLANS.map((plan, index) => {
  const file = join(OUT, `veyro-admin-${index + 1}.plan.json`);
  writeFileSync(file, `${JSON.stringify({ projectId: PROJECT, type: "frontend", ...plan }, null, 2)}\n`);
  return { file, name: plan.name };
});

for (const { file, name } of written) console.log(`${file}  ${name}`);

if (process.argv.includes("--create")) {
  for (const { file, name } of written) {
    const out = execFileSync("testsprite", ["test", "create", "--plan-from", file], {
      encoding: "utf8",
    });
    console.log(`created: ${name}\n${out.trim()}`);
  }
}
