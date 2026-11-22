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
    // **ADM-SCH-04's central claim, asked as a question rather than restated as a test.**
    // The canvas: "Thursday afternoon is an exception -- he asked for it off three weeks
    // ago. His 17:30 with Hala sits inside it, so the grid shows both and the booking is
    // flagged rather than silently honoured or silently dropped." Both failures it names are
    // silent, which is exactly what an in-repo assertion written by the same hand on the
    // same day is worst at noticing: a grid that dropped the booking and a grid that drew it
    // as ordinary would each look correct to somebody who already knew what to expect.
    name: "A booking inside a coach's time off is shown and flagged, not quietly dropped",
    description:
      "Reducing a coach's availability must never delete a booking that already exists, " +
      "because the member on the other end has been told a time. The week grid has to show " +
      "the exception and the booking that falls inside it at once, and mark the clash.",
    priority: "p0",
    planSteps: [
      ...signIn,
      {
        type: "action",
        description:
          "Open the Schedule section and switch to the view that shows one coach's " +
          "availability for a week, rather than the list of classes.",
      },
      {
        type: "assertion",
        description:
          "Verify the week is a grid of days against hours, that the hours the coach is " +
          "available are visibly distinguishable from the hours they are not, and that the " +
          "grid is legible as mostly free when only a few hours are booked -- a grid where " +
          "nearly every cell looks the same shade is a failure, because the whole purpose " +
          "is to see at a glance when somebody can work.",
      },
      {
        type: "action",
        description:
          "Find a week in which this coach has time off. The page opens on the current " +
          "week, which may be empty, so use the page's own controls to move between weeks " +
          "and look at the next two or three weeks until you find one with time off in it. " +
          "If no week has any, try a different coach.",
      },
      {
        type: "assertion",
        description:
          "On the week you found, locate the day where the coach has time off and a " +
          "booking falls inside that time off. Verify BOTH are visible: the time off is " +
          "marked as an exception, and the " +
          "booking inside it is still shown and is marked differently from an ordinary " +
          "booking. Verify the page also lists that clash in words somewhere beneath the " +
          "grid, naming the session, so a reader does not have to spot a single marked " +
          "cell among ninety. A page that showed only the time off, or only the booking, " +
          "or drew the clashing booking the same as any other, is a failure.",
      },
      {
        type: "assertion",
        description:
          "Verify every time on this page is stated in one timezone and that the page says " +
          "which timezone that is.",
      },
    ],
  },
  {
    // **The one write in this app that is not a member acting on their own account**, and
    // the reason it took a migration: the table was insert-only, so the button the design
    // draws would have written a permanent, uncorrectable row on a routine permission. An
    // agent that adds one and cannot take it back is reporting exactly that defect.
    //
    // It writes on a far-future week no other journey or spec reads, and the journey's own
    // last act is to withdraw it -- a rota has no delete, so anything left behind is
    // residue. A withdrawn row is returned by no read.
    name: "A rota exception can be added and then taken back",
    description:
      "Reducing a coach's availability has to be correctable. A day off entered on the " +
      "wrong date, or a shift typed wrongly, must have a remedy in the product rather " +
      "than standing for ever.",
    priority: "p0",
    planSteps: [
      ...signIn,
      {
        type: "action",
        description:
          "Open the Schedule section, switch to the view showing one coach's availability " +
          "for a week, and move forward to the week beginning 15 March 2027.",
      },
      {
        type: "action",
        description:
          "Using the form on that page, add an exception on 17 March 2027 from 13:00 to " +
          "17:00, giving a short reason such as 'a dentist appointment'.",
      },
      {
        type: "assertion",
        description:
          "Verify the exception now appears on the page: it is listed with its date, its " +
          "hours and its reason, and the week grid itself shows those hours marked as an " +
          "exception rather than as ordinary available time. A page that accepted the " +
          "entry but still shows the old week is a failure.",
      },
      {
        type: "action",
        description:
          "Now take that same exception back, using whatever control the page offers for " +
          "removing or withdrawing it, giving a reason such as 'entered on the wrong day'.",
      },
      {
        type: "assertion",
        description:
          "Verify it is gone: no longer listed, and the grid shows those hours as " +
          "available again. **If the page offers no way at all to take back an exception " +
          "once added, that is a failure** — a rota that can only grow is the defect this " +
          "journey exists to catch.",
      },
    ],
  },
  {
    // **ADM-PAY-09's own stated control, asked as a question.** The canvas: "The expected
    // figure is shown *before* the count is entered. Hiding it would be a fraud control;
    // showing it is an accuracy control, and accuracy is the more common problem." An agent
    // that has not read this repository is the right reader for that: it either finds the
    // figure before it types, or it does not.
    name: "A till can be counted against a figure the screen showed first",
    description:
      "Closing a cash drawer is comparing what is in it against what the ledger says " +
      "should be. The expected figure has to be legible before anything is counted, and a " +
      "difference has to be explainable rather than merely refused.",
    priority: "p0",
    planSteps: [
      ...signIn,
      {
        type: "action",
        description:
          "Find the screen for cash drawers or the cash till, starting from the Payments " +
          "section.",
      },
      {
        type: "assertion",
        description:
          "Before typing anything, verify the screen already states what should be in the " +
          "drawer, and that the figure is broken down into the parts that make it up (an " +
          "opening amount, money taken, money paid out) in a way that visibly adds up to " +
          "it. A screen that only revealed the expected amount after a count was entered " +
          "would be a failure.",
      },
      {
        type: "action",
        description:
          "Enter a counted amount that is deliberately LESS than the expected figure, by " +
          "a small amount such as two and a half.",
      },
      {
        type: "assertion",
        description:
          "Verify the screen says the drawer is short, states by how much, and that the " +
          "amount it names is the actual difference between the two figures rather than " +
          "something wildly larger or smaller. Verify it also asks for an explanation at " +
          "this point, before anything has been submitted.",
      },
      {
        type: "action",
        description:
          "Now change the counted amount to exactly the expected figure.",
      },
      {
        type: "assertion",
        description:
          "Verify the screen no longer reports a difference and no longer asks for an " +
          "explanation.",
      },
    ],
  },
  {
    // **ADM-MSH-03, and the claim worth an outside reader is the route rather than the
    // form.** Every absent write form in this app was justified with "a button that
    // answered 403 is worse than its absence"; this one offers the stronger sign-in
    // instead. Whether that is actually a way through is not something the people who
    // built it can judge -- TestSprite found the last two dead ends on this product by
    // trying to get somewhere and failing.
    name: "A member's freeze can be reached from an ordinary sign-in",
    description:
      "Freezing a membership changes what somebody is charged, so it needs a stronger " +
      "sign-in. A reader who starts without one must be able to see what it would cost " +
      "without signing in more strongly, and must be offered a way through rather than a " +
      "dead end. What is behind the stronger sign-in is out of reach here: the only " +
      "verifiable second factor in this build is a single-use recovery code.",
    priority: "p0",
    planSteps: [
      ...signIn,
      {
        type: "action",
        description:
          "Open the Members section, open the first member in the list, and go to the " +
          "tab about their membership.",
      },
      {
        type: "assertion",
        description:
          "Verify the page already says how much of this membership's annual freeze " +
          "allowance has been used, and over what period, WITHOUT asking for a stronger " +
          "sign-in first. A screen that hid that figure would make somebody sign in more " +
          "strongly just to find out whether it was worth doing.",
      },
      {
        type: "assertion",
        description:
          "Verify the page offers a way to act rather than a dead end: if freezing needs a " +
          "stronger sign-in, there is a visible link or button to do that, and the page " +
          "says in words why it is needed. A page that simply refused, or showed a button " +
          "that would fail, is the failure this journey is about.",
      },
      {
        type: "action",
        description:
          "Follow that offer as far as you can. **Stop when it asks for a credential you " +
          "were not given** — this build's only verifiable second factor is a single-use " +
          "recovery code, and you have none; that is a known limitation and not a defect " +
          "to report.",
      },
      {
        type: "assertion",
        description:
          "Verify that what it asked you for is stated plainly — which credential, and " +
          "why — rather than a generic refusal or an error. A reader who cannot proceed " +
          "should at least know exactly what they need.",
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
  {
    // **ADM-MEM-10, and the one question an independent reader is best placed to ask**: does
    // the screen actually stop somebody creating a second record for a person who is already
    // in the system? The canvas's own footnote is the claim -- "preventing the duplicate
    // costs one screen" -- and the in-repo spec and the page were written by the same hand
    // on the same day. A tester who has read neither types a number and sees what happens.
    //
    // **It stops at the step-up, deliberately.** Creating a person is a financial-class
    // permission and the only second factor this build can verify is a single-use recovery
    // code, which no stored plan can be given: handing one to a test spends it on the first
    // run. So the journey asserts everything up to the wall and says where the wall is --
    // the same bound ADM-MSH-03's journey established.
    name: "Adding a walk-in who already has a record is interrupted before anything is saved",
    description:
      "A front desk is adding somebody who walked in. The screen checks the phone number " +
      "as it is typed and, if that number already belongs to a record, says so and offers " +
      "to open it instead of creating a second one. Names are deliberately hidden on an " +
      "ordinary sign-in, so the existing record is identified by its member number and " +
      "when the person joined.",
    priority: "p1",
    planSteps: [
      ...signIn,
      { type: "action", description: "Navigate to /members." },
      {
        type: "assertion",
        description:
          'Verify the page offers a way to add a member, and follow it. Verify the page ' +
          'that opens is headed "New member \u00b7 walk-in" and asks for a name and a phone.',
      },
      {
        type: "action",
        description:
          'In the field labelled "Phone", type +962 79 000 0042. Wait two seconds.',
      },
      {
        type: "assertion",
        description:
          "Verify the page says this number already has a record, identifies that record " +
          "by a member number and the month it joined, and warns that continuing would " +
          "create a second record for the same person. Verify it offers both to open that " +
          "record and to say this is a different person. Verify the button that creates " +
          "the record cannot be used while that warning is on screen.",
      },
      {
        type: "action",
        description: 'Clear the phone field and type +962 79 555 1234 instead. Wait two seconds.',
      },
      {
        type: "assertion",
        description:
          "Verify the warning about an existing record is gone, because no record holds " +
          "that number. Verify the page still explains that creating a person needs a " +
          "stronger sign-in than this session has, and offers a link to raise the session " +
          "rather than a button that would be refused.",
      },
      {
        type: "assertion",
        description:
          "Verify the page states, near the foot, that it does not yet sell a membership, " +
          "record an emergency contact or capture a waiver, and gives a reason for each.",
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
