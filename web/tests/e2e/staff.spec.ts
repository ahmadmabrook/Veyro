import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useDeskSession, useOwnerSession } from "./sign-in";

/**
 * ADM-STF-01 · STAFF LIST · COMPACT, and ADM-STF-02 · STAFF PROFILE.
 *
 * > A Club Manager sees only their own club's staff. **Last seen exists so a departed
 * > employee with a live login is visible rather than discovered.**
 *
 * **That sentence is the screen.** `ppl_staff_profiles` had no reader at all before this, so
 * the first assertion is simply that a tenant's team can be listed — and the rest are about
 * the pair the design says the column is for, which is composed from three planes under three
 * permissions and so can only be put together by the page.
 *
 * The fixture seeds four standings on purpose: working, ended-with-a-live-login,
 * properly-offboarded and on-the-payroll-with-no-login. With fewer, every assertion about
 * telling them apart would pass against a board that could not.
 */

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.describe("the staff list", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/staff");
  });

  test("lists the team, which nothing could do before", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: /The team/, level: 1 }),
    ).toBeVisible();
    // **Located by job title, because every name here is withheld.** `legal_name` is an
    // identity field and the fixture's browser session is level 1, which is the useful level
    // to test at and the members list's own behaviour. Asserting the names would have been
    // asserting a step-up this session has not made.
    const grid = page.getByRole("table");
    await expect(grid.getByRole("row").filter({ hasText: "Reception" })).toBeVisible();
    await expect(grid.getByRole("row").filter({ hasText: "Spin coach" })).toBeVisible();
    await expect(page.getByText("Withheld").first()).toBeVisible();
    await expect(page.getByRole("link", { name: /Raise this session/ })).toBeVisible();
  });

  test("the header does not disagree with the table under it", async ({ page }) => {
    // The first version led with the active count under the words "people on the team" while
    // the grid's own footer said four, so the page disagreed with itself by two. Both numbers
    // now, which is the distinction the members list makes for the same reason.
    const figures = page.locator(".ds-page-figures");
    await expect(figures).toContainText("2 working");
    await expect(figures).toContainText("5 people on record");
  });

  test("leads with the finding, not with a certification nobody recorded", async ({ page }) => {
    // The canvas's amber box is a certification expiry and there is no certification
    // anywhere in this build. What its own footnote names is this, and this is real.
    const alarm = page.getByText(/employment has ended can still sign in/).first();
    await expect(alarm).toBeVisible();
    // Two of them, and they are different shapes: one has a live session and one never
    // signed in at all. The second is why the rule reads the identity's status as well.
    await expect(alarm).toContainText("2 people");
    await expect(page.getByText(/revokes nothing/)).toBeVisible();
  });

  test("tells the four standings apart", async ({ page }) => {
    const grid = page.getByRole("table");
    // **By start date, because "Coach" is a substring of "Spin coach".** A job title is not a
    // key and the names are withheld on this session; the four start dates are distinct.
    const row = (startedOn: string) => grid.getByRole("row").filter({ hasText: startedOn });
    await expect(row("2025-01-06")).toContainText("Working");
    await expect(row("2024-09-02")).toContainText("Left, can still sign in");
    await expect(row("2023-04-17")).toContainText("Left");
    await expect(row("2023-04-17")).not.toContainText("can still sign in");
    // **The leaver with no session whose account still works**, which is the commonest real
    // shape and the one a rule counting only live sessions gets wrong: the password still
    // opens the product tomorrow. Nothing in this build had suspended the identity.
    await expect(row("2022-06-14")).toContainText("Left, can still sign in");
    // **Not a fault**: a person on the payroll with no account is ordinary, and the column
    // says which of the two "no date" cases it is.
    await expect(row("2026-02-10")).toContainText("No login");
  });

  test("a person with no login gets a reason, not two blank cells", async ({ page }) => {
    // An empty cell reads as a fact about the person, which is this build's grids' own rule
    // — and printing "no login" in the Role column beside "No login" in Access was the same
    // sentence twice answering two different questions.
    const row = page.getByRole("table").getByRole("row").filter({ hasText: "2026-02-10" });
    await expect(row.locator('[title*="a role is held by a login"]').first()).toBeAttached();
    await expect(row).not.toContainText("no login");
  });

  test("shows the role and the clubs a role reaches, not the club they sit at", async ({
    page,
  }) => {
    const row = page.getByRole("table").getByRole("row").filter({ hasText: "Reception" });
    // Her tenant-wide publisher role outranks the location-scoped one, so the reach is every
    // club while her staff profile's own location is the site she works at.
    await expect(row).toContainText("Publisher");
    await expect(row).toContainText("Every club");
    await expect(row).toContainText("Downtown");
  });

  test("names the grant beyond the role on the list, in a count", async ({ page }) => {
    const row = page.getByRole("table").getByRole("row").filter({ hasText: "Reception" });
    await expect(row).toContainText(/1 grant beyond it/);
  });

  test("counts the tenant on the chips, and filters by one", async ({ page }) => {
    const bar = page.getByRole("navigation", { name: /Filter the team/ });
    await expect(bar.getByRole("link", { name: /Working · 2/ })).toBeVisible();
    await expect(bar.getByRole("link", { name: /Left · 3/ })).toBeVisible();
    await bar.getByRole("link", { name: /^Left · / }).click();
    await expect(page).toHaveURL(/state=ended/);
    const grid = page.getByRole("table");
    await expect(grid.getByRole("row").filter({ hasText: "Sales" })).toBeVisible();
    await expect(grid.getByRole("row").filter({ hasText: "Reception" })).toHaveCount(0);
  });

  // **Both of these asserted a gap that has closed**, which is the rule this repository
  // records working: ADM-STF-03 is built, so "no invitation in this build" is a sentence the
  // product was *returning to a reader* and two tests were holding on the screen. The
  // question each time is whether the test asserted the finding or a consequence of it.
  //
  // The finding here was never "there is no button": it was that a control the design draws
  // must not be a dead one. So these assert the control exists and leads where it says, and
  // that the old sentence is **gone** -- an assertion on the new wording alone would not
  // notice a revert, which is the direction the last one of these came from.
  test("draws the Invite control the design puts in its header", async ({ page }) => {
    const invite = page.getByRole("link", { name: /^Invite someone/i });
    await expect(invite).toBeVisible();
    await expect(invite).toHaveAttribute("href", "/staff/invite");
    const notYet = page.locator("section").filter({ hasText: "What this screen cannot do" });
    await expect(notYet).not.toContainText("no invitation in this build");
    await expect(notYet).toContainText("Inviting works and sending does not");
    await expect(notYet).toContainText("Certifications");
  });

  test("the chip row still carries no Invited chip, and for its own reason", async ({
    page,
  }) => {
    // Unchanged by ADM-STF-03 and not for the reason the old note gave: a chip reading
    // `Invited · 0` would say nobody has been invited rather than pointing at the list that
    // holds them, which is on the invite screen.
    const bar = page.getByRole("navigation", { name: /Filter the team/ });
    await expect(bar.getByRole("link", { name: /Invited/ })).toHaveCount(0);
  });

  test("the club-scoping sentence says it is true here, because it is", async ({ page }) => {
    // ADR-0014: the gate answers *where*, and `GET /staff` is the one route that acts on it.
    // The old sentence said every check resolves tenant-wide, which stopped being true the
    // hour that landed -- false, and rendered, on the screen the ADR was built for.
    const notYet = page.locator("section").filter({ hasText: "What this screen cannot do" });
    await expect(notYet).not.toContainText("Not true here");
    await expect(notYet).toContainText("True here, and on this screen only");
  });

  test("a reader who cannot see logins is told so rather than told it is clean", async ({
    page,
  }) => {
    // The desk session holds `people.person.read` and nothing of MOD-007 or MOD-008, which is
    // the subset that makes this provable: the list renders and the access half does not.
    await useDeskSession(page);
    await page.goto("/staff");
    await expect(page.getByRole("table")).toBeVisible();
    await expect(page.getByText(/whether they can still sign in is not visible/))
      .toBeVisible();
    const row = page.getByRole("table").getByRole("row").filter({ hasText: "Sales" });
    await expect(row).toContainText("Not checked");
    // And the two columns the desk cannot answer say so rather than rendering empty.
    await expect(row).toContainText("not yours to see");
  });

  test("the whole screen reads in Arabic", async ({ page }) => {
    await page.getByRole("button", { name: "العربية" }).click();
    await page.waitForFunction(() => document.documentElement.dir === "rtl");
    await page.goto("/staff");
    const main = page.locator("main");
    // The employment vocabulary, the standing and the reach are all stored values or derived
    // enumerations, and a stored value rendered as a label is Latin letters mid-line.
    await expect(main).toContainText("على العمل");
    await expect(main).toContainText("ترك العمل، وما يزال يستطيع الدخول");
    await expect(main).toContainText("كل الأندية");
    for (const english of [
      "Working", "Left, can still sign in", "Every club", "No login",
    ]) {
      await expect(main).not.toContainText(english);
    }
  });

  test("no accessibility violations", async ({ page }) => {
    const result = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(result.violations).toEqual([]);
  });
});

test.describe("one person's access", () => {
  test("renders the role, the reach and what is beyond it", async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(`/staff/${fixture().staffWorkingPersonId}`);
    // **One h1, which is the record anatomy.** The first version drew a page title and the
    // person's name as two level-1 headings; axe does not flag that and a screen reader reads
    // two documents. `/people/{id}` has used `RecordHeader` alone from the start.
    await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
    // The job title is the heading when the name is withheld, so the subline starts at the
    // site: printing it in both places is the sentence said twice.
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Reception");
    await expect(page.getByText(/Downtown · since 2025-01-06/)).toBeVisible();

    const beyond = page.locator("section").filter({ hasText: "Beyond their role" });
    await expect(beyond).toContainText("Till refunds");
    // The canvas's attribution line, which `granted_by` had never been read for.
    await expect(beyond).toContainText(/granted by [0-9a-f]{8} on \d{4}-\d{2}-\d{2}/);
    // And the role is its display name, not the stored key beside it: the first version put
    // `publisher_1795251559775` on screen next to the word "Publisher".
    await expect(page.getByText(/publisher_\d+/)).toHaveCount(0);
  });

  test("lists what they can do that is dangerous, with what it costs", async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(`/staff/${fixture().staffWorkingPersonId}`);
    const block = page.locator("section")
      .filter({ hasText: "What they can do that is dangerous" });
    // **The location-scoped grant, which asking the simulator once could not see.** A
    // location-scoped assignment contributes nothing at the tenant-wide default scope, so
    // this permission was simply absent from the block that exists to show it — and the
    // narrow grant is exactly what "beyond their role" means. Found by reading the page.
    await expect(block).toContainText("Add value to a member's wallet");
    await expect(block).toContainText("via Till refunds");
    await expect(block).toContainText("at Downtown");
    // And a tenant-wide one says so rather than listing every site.
    await expect(block).toContainText("Approve a member refund somebody else requested");
    await expect(block).toContainText("everywhere");
    await expect(block).toContainText("needs a stronger sign-in");
  });

  test("the level-3 note is absent when no grant is unusable", async ({ page }) => {
    // A sentence about nothing. The note renders only where a grant is actually unreachable,
    // which is the surface-branch vacuity this repository keeps finding, inverted: an
    // explanation that always renders explains a row that may not be there.
    await useOwnerSession(page);
    await page.goto(`/staff/${fixture().staffWorkingPersonId}`);
    await expect(page.getByText(/needs assurance level 3/)).toHaveCount(0);
  });

  test("says why there are no unticked rows rather than inventing two", async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(`/staff/${fixture().staffWorkingPersonId}`);
    await expect(page.getByText(/no unticked rows/)).toBeVisible();
    await expect(page.getByText(/inventing the product/)).toBeVisible();
  });

  test("renders the tier-four notice, because all three of its claims are true", async ({
    page,
  }) => {
    await useOwnerSession(page);
    await page.goto(`/staff/${fixture().staffWorkingPersonId}`);
    await expect(page.getByText(/hash-chained audit log naming both people/)).toBeVisible();
    await expect(
      page.getByText("You cannot grant a permission you do not hold yourself."),
    ).toBeVisible();
  });

  test("draws neither button and says what each would need", async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(`/staff/${fixture().staffWorkingPersonId}`);
    await expect(page.getByRole("button", { name: /Save changes/i })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /End access/i })).toHaveCount(0);
    const notYet = page.locator("section").filter({ hasText: "What this screen cannot do" });
    await expect(notYet).toContainText("stepped-up financial permission");
    await expect(notYet).toContainText("written reason");
  });

  test("leads a departed employee's record with the access they still have", async ({
    page,
  }) => {
    await useOwnerSession(page);
    await page.goto(`/staff/${fixture().staffEndedWithAccessPersonId}`);
    await expect(page.getByText("EMPLOYMENT ENDED")).toBeVisible();
    await expect(page.getByText(/employment has ended and they can still sign in/))
      .toBeVisible();
  });

  test("a properly offboarded leaver has no alarm on it", async ({ page }) => {
    // The other member of the pair, and it was unreachable before the identity status could
    // be written at all: four controls read the column and nothing set it.
    await useOwnerSession(page);
    await page.goto(`/staff/${fixture().staffOffboardedPersonId}`);
    await expect(page.getByText("EMPLOYMENT ENDED")).toBeVisible();
    await expect(page.getByText(/can still sign in/)).toHaveCount(0);
  });

  test("a person with no login says so rather than saying they have no role", async ({
    page,
  }) => {
    await useOwnerSession(page);
    await page.goto(`/staff/${fixture().staffNoLoginPersonId}`);
    await expect(page.getByText("no login").first()).toBeVisible();
    await expect(page.getByText("Spin coach")).toBeVisible();
  });

  test("links to the person record, which is a different screen", async ({ page }) => {
    await useOwnerSession(page);
    const who = fixture().staffWorkingPersonId;
    await page.goto(`/staff/${who}`);
    await page.getByRole("link", { name: /Open their person record/ }).click();
    await expect(page).toHaveURL(new RegExp(`/people/${who}$`));
  });

  test("no accessibility violations on the record", async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(`/staff/${fixture().staffWorkingPersonId}`);
    const result = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(result.violations).toEqual([]);
  });
});

test.describe("the rail", () => {
  test("carries the staff section the design names", async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/");
    await page.getByRole("link", { name: "Staff & coaches" }).click();
    await expect(page).toHaveURL(/\/staff$/);
  });
});
