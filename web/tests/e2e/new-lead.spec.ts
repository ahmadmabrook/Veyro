import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { signIn, useDeskSession, useOwnerSession, useReaderSession } from "./sign-in";
import { stepUp } from "./step-up-helper";

/**
 * ADM-CRM-04 · ADD LEAD — "New lead. Name and phone are enough. Everything else can wait."
 *
 * **The number on the fixture's cold lead**, which is the one match this screen has a
 * deterministic answer for: that person already *has* a lead, so "Add a lead for them" returns
 * theirs rather than opening a second — the canvas's own "that record would open instead of a
 * second one being created", and a state no fresh number can reach. A test pointed at the
 * seeded member instead would create a lead on its first run and find one on every run after
 * it, which is the consumable-state trap this repository has paid for four times.
 */
const LEAD_HOLDER = "+962 79 000 0101";

/** The seeded member's number: a person with a record and no lead. */
const MEMBER = "+962 79 000 0042";
/**
 * One number held by two people, which no fixture had until FD-05 needed it.
 *
 * **Its absence hid a live 500 on this screen.** The "also held by N other records" line
 * passed a *formatted* count to a plural message, and `fill` picks the form from a number and
 * formats it itself -- so the page answered "This page couldn't load" the first time a family
 * shared a number. The branch had never rendered, because the two seeded numbers belong to one
 * person each: a surface branch no fixture can reach, in its quietest form. The per-plural-form
 * sweep refuses the shape statically now; this renders it.
 */
const FAMILY_LINE = "+962 79 000 0044";

/** A number no run has used, so the clear path is clear and stays clear. */
const fresh = () => `+962 79 2${String(Date.now()).slice(-6)}`;

test.describe("the add-lead form at an ordinary sign-in", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/leads/new");
  });

  test("is reachable from the pipeline, which specified the button and had none",
    async ({ page }) => {
      // **The live ADM-CRM-01 screen draws `prim('Add a lead')`** in its header row and this
      // app rendered nothing there — ADM-MEM-05's missing "Add member" a second time, with
      // the same consequence: this screen is the only way to open a lead from a cold start.
      await page.goto("/leads");
      const add = page.getByRole("link", { name: "Add a lead" });
      await expect(add).toBeVisible();
      await add.click();
      await expect(page).toHaveURL(/\/leads\/new$/);
      await expect(page.getByRole("heading", { name: "New lead" })).toBeVisible();
    });

  test("renders the canvas's own instruction under the title", async ({ page }) => {
    // **The one screen where a sub-line is not the prose `PageHeader` bans.** Its rule came
    // from the data canvases and ADM-MEM-10's canvas obeys it; this one draws a sentence that
    // is the form's instruction rather than a description of the screen.
    await expect(page.locator(".ds-page-figures"))
      .toContainText("Name and phone are enough");
  });

  test("says nothing was found, which is the state this canvas draws", async ({ page }) => {
    // ADM-MEM-10 draws this panel saying a record exists; ADM-CRM-04 draws it saying none
    // does. The treatment is the same in both, which is what makes it a detection region
    // rather than a severity signal — so the clear verdict is rendered in the attention ink
    // as drawn rather than recoloured into reassurance.
    const form = page.locator("form.ds-walk-in-form");
    await form.getByLabel("Phone").fill(fresh());
    const panel = page.locator(".ds-walk-in-detection");
    await expect(panel).toContainText("No existing record");
    await expect(panel).toContainText("Checked as you typed against members and leads");
    await expect(panel).toContainText("that record would open instead of a second one");
  });

  test("counts the other records on a number a family shares", async ({ page }) => {
    const form = page.locator("form.ds-walk-in-form");
    await form.getByLabel("Phone").fill(FAMILY_LINE);
    const panel = page.locator(".ds-walk-in-detection");
    await expect(panel).toContainText("This number already has a record");
    // Two people hold it, so one *other* record beyond the one named.
    await expect(panel).toContainText("Held by 1 other record");
  });

  test("finds the record a number already belongs to, and offers three answers",
    async ({ page }) => {
      const form = page.locator("form.ds-walk-in-form");
      await form.getByLabel("Phone").fill(LEAD_HOLDER);
      const panel = page.locator(".ds-walk-in-detection");
      await expect(panel).toContainText("This number already has a record");
      // **The name is withheld and the line still identifies the record.** `legal_name` is
      // identity-class, so a sales desk's password session gets the marker -- and the read
      // returns the mask *string*, so a line that printed it would read as somebody called
      // `***`. The member number and the date are not identity-class and stay.
      await expect(panel).toContainText("Withheld");
      await expect(panel).not.toContainText("***");
      await expect(panel).toContainText(/known since|joined/);
      // Open the person — what the canvas's sentence means for a reader who is checking.
      await expect(panel.getByRole("link", { name: "Open that record" })).toBeVisible();
      // The sentence as a command, which only this screen can offer: a lead against the
      // person who is already there, one write and no second record.
      await expect(panel.getByRole("button", { name: "Add a lead for them" })).toBeVisible();
      // And ADM-MEM-10's escape, because this canvas draws no match state of its own and a
      // shared family line is the ordinary case paragraph 10200 wants a human for.
      await expect(panel.getByRole("button", { name: "Different person" })).toBeVisible();
    });

  test("opens the lead that already exists rather than a second one", async ({ page }) => {
    // **The canvas's behaviour, end to end.** The fixture's cold lead has a lead already, so
    // `POST /crm/leads` returns theirs and the form says which of the two things happened —
    // a form that said "the lead is open" for a record somebody else opened last week would
    // be telling a desk they did something they did not do.
    const form = page.locator("form.ds-walk-in-form");
    await form.getByLabel("Phone").fill(LEAD_HOLDER);
    const panel = page.locator(".ds-walk-in-detection");
    await expect(panel).toContainText("This number already has a record");
    await panel.getByRole("button", { name: "Add a lead for them" }).click();

    await expect(page.getByText("That person already had a lead")).toBeVisible();
    await expect(page.getByText("rather than creating a second one")).toBeVisible();
    const open = page.getByRole("link", { name: "Open the lead" });
    await expect(open).toBeVisible();
    await open.click();
    await expect(page).toHaveURL(/\/leads\/[0-9a-f-]{36}/);
  });

  test("holds the create and says the match path is still open to it", async ({ page }) => {
    // **At this assurance the create is disabled whatever the check says**, because
    // `people.person.write` is financial class — and `crm.lead.write` is routine, so the one
    // thing this reader can do is the thing the check found for them. A screen that said only
    // "needs a stronger sign-in" would send somebody away from a control that works.
    const form = page.locator("form.ds-walk-in-form");
    await form.getByLabel("Name").fill("Rana Sabbagh");
    await form.getByLabel("Phone").fill(MEMBER);
    await expect(page.locator(".ds-walk-in-detection"))
      .toContainText("This number already has a record");
    await expect(form.getByRole("button", { name: "Save lead" })).toBeDisabled();
    await expect(form).toContainText("needs a stronger sign-in");
    await expect(form).toContainText("opening a lead against them is still open to you");
  });

  test("acknowledges one number and not the next one", async ({ page }) => {
    // The acknowledgement is the value, not a flag: "Different person" answers *this* number,
    // and a dismissal that carried over would hide the interruption for whatever is typed
    // next — which takes two seeded numbers to show.
    const form = page.locator("form.ds-walk-in-form");
    const panel = page.locator(".ds-walk-in-detection");
    await form.getByLabel("Phone").fill(LEAD_HOLDER);
    await expect(panel).toContainText("This number already has a record");
    await page.getByRole("button", { name: "Different person" }).click();
    await expect(panel).not.toContainText("This number already has a record");
    await expect(page.locator('.ds-field-control[data-message="warning"]')).toHaveCount(0);

    await form.getByLabel("Phone").fill(MEMBER);
    await expect(panel).toContainText("This number already has a record");
    await expect(page.locator('.ds-field-control[data-message="warning"]')).toHaveCount(1);
  });

  test("draws the canvas's two optional fields, and marks them as optional",
    async ({ page }) => {
      // `SOURCE · OPTIONAL` is the tenant's own rows rather than free text, because
      // ADM-RPT-03 groups conversions by it; `INTEREST · OPTIONAL` is three chips.
      const source = page.getByLabel(/Source/);
      await expect(source).toBeVisible();
      await expect(source.locator("option", { hasText: "Sweifieh open day" }))
        .toHaveCount(1);
      await expect(page.getByText("Source (optional)")).toBeVisible();

      // **Both marks render the same shape**, which they did not: the chip group said
      // "Interest optional" beside "Source (optional)" until somebody read the page. The
      // canvas draws `SOURCE · OPTIONAL` and `INTEREST · OPTIONAL` with one treatment, so
      // two spellings of one meaning on one screen is a deviation however small it looks.
      const group = page.getByRole("group", { name: /^Interest \(optional\)/ });
      await expect(group.getByRole("checkbox")).toHaveCount(3);
      await expect(group.getByRole("checkbox", { name: "Classes" })).toBeVisible();
      await expect(group.getByRole("checkbox", { name: "PT" })).toBeVisible();
      await expect(group.getByRole("checkbox", { name: "Gym only" })).toBeVisible();
      // Said before the choice rather than left to a 422, because this app's validation
      // handler deliberately names no field.
      await expect(group).toContainText("Gym only is not combined with the other two");
    });

  test("names the four things it does not do, and why", async ({ page }) => {
    const gaps = page.locator("section.page-section").filter({
      has: page.getByRole("heading", { name: "What this screen does not do yet" }),
    });
    await expect(gaps.getByRole("term").filter({ hasText: "Starting a trial" }))
      .toBeVisible();
    await expect(gaps.getByRole("term").filter({ hasText: "Assigning the lead" }))
      .toBeVisible();

    // **This asserted "nothing in this build marks a product as a trial", and ADR-0010 D7
    // made that false.** It was the *reason* under the old state rather than the finding:
    // what this panel is for is that each gap says what the form does not do and why, and
    // the trial gap is now a flow with a screen of its own rather than a product this build
    // cannot express. So the assertion is the reason that holds -- and the absence of the
    // one that does not, which is the direction that cannot go stale the next time a gap
    // closes behind it.
    await expect(gaps).toContainText("an agreement, a signature and an activation");
    await expect(gaps).not.toContainText("marks a product as a trial");
  });

  test("no accessibility violations, with the interruption on screen", async ({ page }) => {
    // **With the panel rendered**, because that is where this screen's own colour is: an axe
    // run against the empty form would never evaluate the one pairing it introduces — and the
    // chip group's hidden control is the other thing only a rendered tree can judge.
    await page.locator("form.ds-walk-in-form").getByLabel("Phone").fill(LEAD_HOLDER);
    await expect(page.locator(".ds-walk-in-detection"))
      .toContainText("This number already has a record");
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(results.violations).toEqual([]);
  });
});

test.describe("opening a lead for somebody new, once the reader has stepped up", () => {
  /**
   * **Signing in for itself rather than adopting the shared cookie.** A step-up revokes the
   * session it came from, and the new cookie lives in this browser context only — so a spec
   * that stepped up the saved session would sign out every spec that runs after it.
   */
  test("creates a person and a lead, and says neither was sold anything",
    async ({ page }) => {
      await signIn(page);
      await page.goto("/leads/new");
      await page.getByRole("link", { name: "Raise this session to create records" }).click();
      await stepUp(page);

      const form = page.locator("form.ds-walk-in-form");
      await expect(form.getByLabel("Name")).toBeVisible();

      // **The app's own sentence, which a native `required` made unreachable.** The fields
      // carry `aria-required` and no native constraint, because this form has a second submit
      // that needs neither -- so an empty submit reaches the server, which answers, and the
      // message slot carries the refusal in the reader's language rather than the browser's.
      await form.getByRole("button", { name: "Save lead" }).click();
      await expect(form).toContainText("A record needs a name.");

      await form.getByLabel("Name").fill("Lead Created");
      await form.getByLabel("Phone").fill(fresh());
      // **Click the chip, not the checkbox.** The control is visually hidden and the face is
      // what a reader taps, so `.check()` on the input is intercepted by its own label --
      // which is the component working rather than a defect, and the click a person makes is
      // the one worth asserting.
      const interest = form.getByRole("group", { name: /Interest/ });
      await interest.getByText("Classes", { exact: true }).click();
      await expect(interest.getByRole("checkbox", { name: "Classes" })).toBeChecked();

      const save = form.getByRole("button", { name: "Save lead" });
      await expect(save).toBeEnabled();

      // **The interruption holds a session that CAN act**, which is the only place the
      // enabling half is observable: at AAL 1 the button is disabled whatever the check says,
      // so a spec that asserted it there would prove the permission and not the hold.
      await form.getByLabel("Phone").fill(LEAD_HOLDER);
      await expect(page.locator(".ds-walk-in-detection"))
        .toContainText("This number already has a record");
      await expect(save).toBeDisabled();
      await page.getByRole("button", { name: "Different person" }).click();
      await expect(save).toBeEnabled();

      // Back to a number nobody holds, so the record this test creates is its own.
      await form.getByLabel("Phone").fill(fresh());
      await expect(save).toBeEnabled();
      await save.click();

      await expect(page.getByText("The lead is open")).toBeVisible();
      await expect(page.getByText("Nothing has been sold")).toBeVisible();
      const open = page.getByRole("link", { name: "Open the lead" });
      await expect(open).toBeVisible();
      await open.click();
      await expect(page).toHaveURL(/\/leads\/[0-9a-f-]{36}/);
    });
});

test.describe("what each weaker credential is given", () => {
  test("a session without the read is refused the screen, not given a form with no check",
    async ({ page }) => {
      // Without `people.person.read` there is no duplicate check, and a lead created with no
      // check is a duplicate in the membership and the door log afterwards — because "the
      // lead ID becomes the member ID". So the page refuses rather than degrading into one.
      await useReaderSession(page);
      await page.goto("/leads/new");
      await expect(page.locator("form.ds-walk-in-form")).toHaveCount(0);
      await expect(page.getByRole("heading", { name: "New lead" })).toBeVisible();
    });

  test("a front desk gets the check and neither write", async ({ page }) => {
    // **The desk holds `people.person.read` and nothing else**, so the check works, the
    // create is `denied` rather than `needs_step_up` — a step-up cannot grant a permission
    // nobody holds — and "Add a lead for them" is absent, because `crm.lead.write` is a
    // permission this role does not have either. A button that answered 403 is worse than its
    // absence.
    await useDeskSession(page);
    await page.goto("/leads/new");
    const form = page.locator("form.ds-walk-in-form");
    await form.getByLabel("Phone").fill(LEAD_HOLDER);
    const panel = page.locator(".ds-walk-in-detection");
    await expect(panel).toContainText("This number already has a record");
    await expect(panel.getByRole("button", { name: "Add a lead for them" })).toHaveCount(0);
    await expect(panel.getByRole("link", { name: "Open that record" })).toBeVisible();
    await expect(form.getByRole("button", { name: "Save lead" })).toBeDisabled();
    await expect(form).toContainText("not something this session may do");
  });

  test("and the pipeline offers it no Add a lead button at all", async ({ page }) => {
    await useDeskSession(page);
    await page.goto("/leads");
    await expect(page.getByRole("link", { name: "Add a lead" })).toHaveCount(0);
  });
});
