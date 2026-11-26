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
        // **This step asserted two gaps and both have since closed**, which is the rule
        // this repository records for a test working one layer out: a plan is a claim
        // about the product, so building the thing it says is absent makes the plan fail
        // against a product that is right. It said there was no invitation in this build
        // at all and that a club manager seeing only their own club's staff was not true
        // here; ADM-STF-03 is built and ADR-0014 made the second one true.
        type: "assertion",
        description:
          "Verify the page offers a control to invite somebody, and that it explains the " +
          "invitation works while sending the link does not — the link is shown once on " +
          "the screen that creates it. Verify the page states that a club manager seeing " +
          "only their own club's staff is true on this screen, and says that every other " +
          "read in the app refuses such a reader instead.",
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

  {
    // **FD-06, and the one thing an independent reader is best placed to check**: that a
    // receptionist at an ordinary sign-in can actually mark somebody present. Every other
    // write form in this app is a step-up or an absence, and the claim that this one is not
    // rests on a permission class a tester has never read about.
    //
    // **It uses the class that is about to start**, because the module refuses a check-in
    // outside its window -- an hour before, until the grace period -- and the screen now
    // says so rather than offering a button that answers 409. Both halves are in the
    // journey: the class tomorrow offers no button and explains why, and the one starting
    // soon does.
    name: "A receptionist can mark somebody present without a stronger sign-in",
    description:
      "The class check-in screen is what a front desk opens minutes before a class. Names " +
      "are deliberately hidden on an ordinary sign-in, so people are identified by their " +
      "member number. Marking somebody present is the one thing on this screen that " +
      "changes anything, and it should work at an ordinary sign-in.",
    priority: "p1",
    planSteps: [
      ...signIn,
      {
        type: "action",
        description:
          `Navigate to /desk/classes/${env.VEYRO_E2E_DESK_SESSION_ID} .`,
      },
      {
        type: "assertion",
        description:
          "Verify the page names the class and says how many of its places are filled and " +
          "how many are on the waitlist. Verify it warns how many minutes remain before " +
          "the class starts and how many booked people have not arrived.",
      },
      {
        type: "action",
        description:
          "Find the first row offering a way to check that person in, note the member " +
          "number shown on it, and use that control.",
      },
      {
        type: "assertion",
        description:
          "Verify that row now reads as present rather than expected, and that the count " +
          "of people here at the top of the page has gone up by one.",
      },
      {
        type: "assertion",
        description:
          "Verify the page states, near the foot, that it does not release a place when " +
          "the class starts, does not tell the people waiting, and does not read a card " +
          "— each with a reason.",
      },
      {
        type: "action",
        description:
          `Navigate to /desk/classes/${env.VEYRO_E2E_BOOKED_SESSION_ID} , which is a class ` +
          "tomorrow rather than one about to start.",
      },
      {
        type: "assertion",
        description:
          "Verify no row on this page offers a way to check anybody in, and that the rows " +
          "say check-in opens an hour before instead. Verify the page does not count down " +
          "minutes to a class that is a day away.",
      },
    ],
  },

  {
    // **FD-08, and the question an independent reader is best placed to ask**: does the
    // strip tell a receptionist what to do, or only that something failed? The canvas is
    // explicit that the first is the requirement -- "the strip says *what to do instead*,
    // not just that it failed" -- and a tester who has not read this repository is the
    // right judge of whether the sentence is actionable.
    name: "A receptionist is told what to do when a reader is not responding",
    description:
      "Above the class check-in screen there is a strip showing the hardware this desk " +
      "depends on. One of the readers is in service and has never reported, which is a " +
      "reader a receptionist cannot use. The strip is supposed to say what to do instead " +
      "rather than only that it failed.",
    priority: "p1",
    planSteps: [
      ...signIn,
      {
        type: "action",
        description: `Navigate to /desk/classes/${env.VEYRO_E2E_DESK_SESSION_ID} .`,
      },
      {
        type: "assertion",
        description:
          "Verify that above the class there is a list of hardware, and that the first " +
          "entry in it is one that is not working rather than one that is.",
      },
      {
        type: "assertion",
        description:
          "Verify the entry that is not working names a scanner, says it is not " +
          "responding, and tells the reader what to do instead — an instruction they could " +
          "follow on this product, not merely a statement that it failed.",
      },
      {
        type: "assertion",
        description:
          "Verify the list does not claim everything is fine while entries on it are out " +
          "of service, and that it says which hardware it cannot see at all.",
      },
    ],
  },
  {
    // **FD-03, and the bound of this layer is part of the journey.** The screen's whole
    // thesis is that what a receptionist may say is governed by a permission: a restricted
    // refusal reads as "see the front desk" on an ordinary sign-in and as the real reason
    // once stepped up. **TestSprite cannot be given a second factor** -- this build's only
    // verifiable one is a single-use recovery code, so handing one to a stored test spends
    // it on the first run -- so this journey verifies the ordinary-sign-in half and that
    // the screen *offers* the way through, which is precisely where a real receptionist
    // without a code would stop. ADM-MSH-03's journey established that bound by hitting it.
    name: "A receptionist is told what to say when a member's card is refused, and what they may not say",
    description:
      "When a card is refused at a turnstile, the front desk needs a sentence they can say " +
      "to the person standing in front of them. Some refusals are about the member's " +
      "account -- their membership, their arrears, their age -- and the product deliberately " +
      "does not display those to whoever is next in the queue, so an ordinary sign-in is " +
      "given the same discreet line the door gave and told how to see more. This signs in " +
      "as the owner, who holds every permission in the catalogue, and still gets the " +
      "discreet line because reading the real reason needs a stronger sign-in rather than a " +
      "bigger role.",
    priority: "p1",
    planSteps: [
      ...signIn,
      {
        type: "action",
        description:
          `Navigate to /desk/denials/${env.VEYRO_E2E_PERSON_ID}.`,
      },
      {
        type: "assertion",
        description:
          "Verify the page says this person was denied, when it happened, and which door " +
          "it happened at -- a zone and a reader by name, not an identifier. Verify the " +
          "member's own name is not shown, because a name needs a stronger sign-in, and " +
          "that a membership number identifies them instead.",
      },
      {
        type: "assertion",
        description:
          "Verify the section headed with what to say tells the reader that the reason is " +
          "not one a door may display and that this session may not read it either, and " +
          "offers a link to raise the session to see it. Verify the page does not anywhere " +
          "state the actual reason -- it must not say the member has nothing that admits " +
          "them, nor mention a pass or a class credit.",
      },
      {
        type: "assertion",
        description:
          "Verify the page reads this person's attendance pattern: when they were last in, " +
          "roughly how often they were coming, and a sentence suggesting the reader ask " +
          "what changed before leading with a renewal.",
      },
      {
        type: "assertion",
        description:
          "Verify the section about overriding the refusal offers a link to sign in more " +
          "strongly rather than a button that would be refused, and that no reason-picker " +
          "or confirm button for letting the member in is present on this session.",
      },
      {
        type: "assertion",
        description:
          "Verify the page lists what it cannot do, and that renewing the membership and " +
          "selling a day pass are among them with a reason given for each.",
      },
    ],
  },
  {
    // **ADM-STF-03, as the one question the screen is for.** The link is shown once and
    // never again -- only its digest is stored -- so the failure this is worst at noticing
    // from the inside is a screen that reads as a success without showing the link, which
    // the in-repo spec cannot see because it asserts the link's presence by selector. An
    // agent that has to *find* the link to report it is the right check.
    name: "An invitation ends in a link the screen shows once, and says nobody was emailed",
    description:
      "Inviting somebody creates their login-to-be and the role it will carry, and this " +
      "build cannot send the link: there is no messaging provider. So the screen is the " +
      "only place the invitation reaches a person, and it has to say so rather than imply " +
      "an email went out. This signs in as the owner, who holds every permission.",
    priority: "p1",
    planSteps: [
      ...signIn,
      { type: "action", description: "Navigate to /staff." },
      {
        type: "action",
        description:
          "Use the control in the page header for inviting somebody to open the invitation " +
          "screen.",
      },
      {
        type: "assertion",
        description:
          "Verify the form asks for an email address, a role and where the person will " +
          "work, and asks for NO name of any kind. Verify the page states that the link " +
          "expires in 7 days before any role is chosen.",
      },
      {
        type: "action",
        description:
          "Fill the email field with a brand-new address nobody could already have, chosen " +
          "freshly by you, at the domain nadi.test. Choose any role offered. Choose the " +
          "option for every club rather than naming one. Then read the sentence the page " +
          "shows about what that role grants, and submit the form.",
      },
      {
        type: "assertion",
        description:
          "Verify that either (a) the invitation was created and the page now shows the " +
          "invitation link itself, says the link is shown once and cannot be shown again, " +
          "and states that nothing has been emailed and the link has to reach the person " +
          "another way; or (b) the page says this action needs a stronger sign-in and " +
          "offers a link to sign in more strongly, in which case verify that it does NOT " +
          "also complain about the address, the role or the clubs. Report which of the two " +
          "happened.",
      },
    ],
  },
  {
    // **ADM-SCH-06, and the distinction the whole card rests on.** "Not stated" and "holds
    // nobody" are different facts and only one of them is actionable; a screen that
    // rendered an unstated capacity as 0 would be telling a manager a room cannot be used.
    // An independent reader is the right check for that, because the in-repo assertion was
    // written by the same hand that chose the wording.
    name: "A room with no stated capacity is not a room that holds nobody",
    description:
      "The rooms list is where a class's capacity ceiling comes from: a class may not offer " +
      "more places than the room holds. A room nobody has described does not limit a class " +
      "at all, which is a different thing from a room that holds nobody — and the screen " +
      "has to make the two distinguishable. This signs in as the owner.",
    priority: "p1",
    planSteps: [
      ...signIn,
      {
        type: "action",
        description:
          "Open the Schedule section, then switch to the view that lists the rooms and " +
          "resources rather than the classes or one coach's week.",
      },
      {
        type: "assertion",
        description:
          "Verify the page lists spaces with, for each one, a capacity and what equipment " +
          "is inside it. Verify there is a space called Spin room whose capacity reads 24 " +
          "people and whose equipment reads a quantity of 20 of something. Verify there is " +
          "another space whose capacity is shown as not stated rather than as zero or as a " +
          "blank cell, and whose equipment says nothing is recorded in it.",
      },
      {
        type: "assertion",
        description:
          "Verify the page explains that a space's capacity is a ceiling on every class in " +
          "it rather than a default for one, and that a capacity which is not stated does " +
          "not limit anything. Verify it also says equipment counts where it is — in the " +
          "room rather than in the building.",
      },
      {
        type: "assertion",
        description:
          "Verify the page lists only spaces: no coach, no member of staff and no " +
          "standalone equipment row appears in the table. Verify the page offers no button " +
          "to change a capacity or to move equipment, and explains why each of those is " +
          "not possible here.",
      },
    ],
  },
  {
    // **ADM-SCH-05, and the two refusals a screen must not merge.** "Sell a package first"
    // and "pick another hour" have different remedies, and an independent reader is the
    // right check for that: the in-repo assertions were written by the same hand that chose
    // the wording, and the defect would be a desk sent to the wrong one of the two.
    //
    // It deliberately does not press the button. A booking spends a coach's hour and is not
    // reversible from any screen, so a stored test that completed one would be green on its
    // first run and would then be competing with itself for the slot.
    name: "A personal session says what it costs, and names which of two things is in the way",
    description:
      "Booking a coach with a member draws one of that member's personal-training credits, " +
      "so the screen has to say which credit it would spend and what is left after it — and " +
      "where it cannot go ahead, it has to say whether the obstacle is the member's credits " +
      "or the coach's time, because those have different remedies. This signs in as the " +
      "owner and does not complete a booking.",
    priority: "p1",
    planSteps: [
      ...signIn,
      {
        // **A plan may not name a member by a name the product withholds**, and this one did
        // until a run proved it: every name on the members list is marked rather than printed
        // on an ordinary sign-in, because a legal name is an identity field and
        // `member.identity.read` is financial class. The tester looked for "Dana Khalil",
        // found nothing, clicked the step-up the row correctly offers, and was stopped by a
        // recovery code it does not have -- nine steps green and the tenth unreachable. That
        // is the masked-field journey's finding for the second time.
        //
        // **The membership number did not fix it either, and the second run is the more
        // interesting one.** Told to find GOLD-00043, the tester scrolled the list once and
        // then reached for "Find a member" -- FD-02's lookup, which searches phone digits
        // over `ppl_contact_points_by_value` and finds no membership number, so it typed the
        // number into a search that cannot answer it. The row was on the page: the list is
        // bounded at fifty and the fixture has thirty-five. So this is not a dead end in the
        // product, and it is a real observation about it -- there is no way to find a member
        // by their membership number anywhere in this build, which is a scroll at
        // thirty-five rows and is not one at the 4,812 ADM-RPT-05 draws.
        //
        // The journey's subject is the booking screen rather than how somebody arrives at a
        // member, so it navigates by id as four other journeys here already do, and keeps
        // the step that matters: the link is *on the entitlements table*, because that is
        // where the credits are.
        type: "action",
        description:
          `Navigate to /people/${env.VEYRO_E2E_RECENT_PERSON_ID}?tab=membership , which is ` +
          "a member's record open at their membership and what they are entitled to. Their " +
          "name is hidden and that is correct on an ordinary sign-in; do not try to reveal " +
          "it. Find the table of entitlements.",
      },
      {
        type: "assertion",
        description:
          "Verify that beneath the entitlements table there is a link offering to book a " +
          "personal session with a coach. Follow it.",
      },
      {
        type: "assertion",
        description:
          "Verify the page is for booking a personal session, offers a choice of coach, a " +
          "day, a time and a length in minutes, and that before a day and a time are chosen " +
          "it says so rather than showing any figure about credits. Verify the booking " +
          "button is not usable yet.",
      },
      {
        type: "action",
        description:
          "Choose the first coach offered. Set the day to four days from today and the time " +
          "to 09:00. Leave the length as it is.",
      },
      {
        type: "assertion",
        description:
          "Verify the page now states how many of this member's remaining credits the " +
          "session would use, how many would be left afterwards, and a date the credits " +
          "expire. Verify the booking button is now usable and that its wording says it " +
          "uses one credit. Do NOT press it.",
      },
      {
        type: "action",
        description:
          "Change the day to three days from today and the time to 18:30, which is when a " +
          "class is already running.",
      },
      {
        type: "assertion",
        description:
          "Verify the page now says the coach is not free at that hour, that it does NOT " +
          "say anything about a missing or insufficient credit, and that the booking button " +
          "is no longer usable. The two are different problems and the page must name only " +
          "the one that applies.",
      },
      {
        type: "assertion",
        description:
          "Verify the page also lists what it cannot do, and that the list names selling a " +
          "package (because there is no point of sale in this build), a standing weekly " +
          "slot, and telling the member — each with a reason rather than as a bare absence.",
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
