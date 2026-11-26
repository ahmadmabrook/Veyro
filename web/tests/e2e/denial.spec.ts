import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { signIn, useOwnerSession, useReaderSession } from "./sign-in";
import { stepUp } from "./step-up-helper";

/**
 * FD-03 · ACCESS DENIED · WHAT TO SAY AND DO.
 *
 * > "**His membership ended on 7 August** and the 14-day grace ran out five days ago. He was
 * > here three times a week for two years — worth asking whether something changed before you
 * > lead with the renewal." … "Without override authority the last button is absent and the
 * > panel names Ziad as the person to call. Never a locked control with no route."
 *
 * **The one screen in this product where what a receptionist may say is governed by a
 * permission**, and that is MOD-022 working rather than a gap: a refusal carries a public line
 * a door may display and the real reason behind `access.decision.read_reason`, which is
 * financial class. So the same refusal reads as two different sentences depending on how the
 * reader signed in, and both halves are asserted here — the second by actually stepping up,
 * because a claim that a reader can get past a step-up is only proved by getting past it.
 *
 * **Nothing in this file admits anybody.** An override is one-way: the decision log is
 * insert-only and nothing withdraws an admission, so a spec that pressed the button once a run
 * would consume a state nothing restores — the budget shape this repository has recorded four
 * times. `freeze.spec.ts` made the same call for the same reason. The fixture seeds an
 * already-answered refusal on the twin so that branch renders from real rows, and
 * `tests/component/denial.test.ts` constructs the rest.
 */

const creds = fixture();
/** A refusal nobody has answered. */
const AT = `/desk/denials/${creds.personId}`;
/** One somebody already let them in on, seeded rather than pressed. */
const ANSWERED = `/desk/denials/${creds.overriddenPersonId}`;

test.describe("a refusal at an ordinary sign-in", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(AT);
  });

  test("says the member was denied, and when", async ({ page }) => {
    const head = page.locator(".ds-page-head");
    // **The badge's word is localized and its state is not.** `StatusBadge` takes a closed
    // English vocabulary so an engineer cannot invent "Semi-active", and rendering that enum
    // is what would put a Latin word in the middle of an Arabic line -- the Arabic case is
    // asserted below.
    await expect(head).toContainText("Denied");
    // Masked at an ordinary sign-in: the legal name is an identity-class field, so the title
    // is the marker and the member number is what identifies the row.
    await expect(head).toContainText("Name withheld");
    await expect(head).toContainText("M-00042");
    // **Which door**, which the canvas heads the screen with: "Flex · Khalda · turnstile
    // 18:39". A decision carries a point id rather than a name, so the zone read is a fifth
    // gate -- and `doorOf` answers nothing rather than guessing, because a receptionist sent
    // to the wrong lane walks away from the person in front of them.
    await expect(head).toContainText("Main floor");
    await expect(head).toContainText("North turnstile");
  });

  test("gives the sentence the member was given, not the reason behind it", async ({
    page,
  }) => {
    // **The whole thesis of the screen.** The fixture's refusal is `no_entitlement`, one of
    // the five restricted codes, so a session without `access.decision.read_reason` is told
    // `see_front_desk` -- and `see_front_desk` is what the turnstile said too, which is why
    // the sentence here is about raising the session rather than about the membership.
    const say = page.locator(".ds-denial-say");
    await expect(say).toContainText("not one a door may display");
    // And the real reason is nowhere on the page, which is the control.
    await expect(page.locator("main")).not.toContainText("nothing that admits them here");
    await expect(page.locator("main")).not.toContainText("A pass or a class credit");
  });

  test("offers the step-up that would show why, because there is one behind it", async ({
    page,
  }) => {
    // `masked` is the module's own answer to whether it withheld a reason, so the offer
    // appears exactly where something is behind it rather than on every refusal.
    const link = page.getByRole("link", { name: /read why it was refused/ });
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute(
      "href", new RegExp(`action=access.decision.read_reason.*next=/desk/denials/${creds.personId}`));
  });

  test("reads their pattern, which is why the canvas puts it here", async ({ page }) => {
    // "He was here three times a week for two years -- worth asking whether something
    // changed before you lead with the renewal." A gap means nothing until you know what it
    // is a gap from.
    const block = page.locator("section").filter({ hasText: "Their pattern" });
    // **Exactly one day, not "today or one day".** The allowance was covering a fixture bug
    // rather than a real range: the seed subtracted whole days from a UTC instant while this
    // page counts them in the club's zone, so a run after 21:00 UTC produced "2 days ago"
    // and the allowance did not stretch that far anyway -- it just hid the smaller drift
    // until the larger one arrived. `clubLocalInstant` seeds the most recent visit on the
    // club's own yesterday at every hour of the run, so the figure is now one value.
    await expect(block).toContainText("Last in 1 day ago");
    // **Rounded, and the sentence says "about".** The fixture's fourteen entries over nine
    // weeks is about one and a half a week, and this app has one number-rendering path which
    // refuses a fraction outright -- `formatInteger` throws, which is a 500 rather than a
    // rounding bug, and it threw on this page until the figure was rounded.
    await expect(block).toContainText(/about \d+ times? a week/);
    await expect(block).toContainText("before you lead with the renewal");
  });

  test("offers the override as a step-up rather than a button that would answer 403",
    async ({ page }) => {
      const block = page.locator(".ds-denial-override");
      await expect(block).toContainText("needs a stronger sign-in");
      await expect(block.getByRole("link", { name: "Raise this session to override" }))
        .toBeVisible();
      // No form, because offering one that cannot submit is the thing being avoided.
      await expect(page.locator("form.ds-override-form")).toHaveCount(0);
    });

  test("names the three things it does not do, including two the canvas puts first",
    async ({ page }) => {
      // The canvas draws Renew · Day pass · Photo. Every one is a sale or an object store,
      // and a screen that drew the buttons would be offering a receptionist three controls
      // that do nothing.
      const gaps = page.locator(".ds-denial-gaps");
      await expect(gaps).toContainText("Renewing the membership");
      await expect(gaps).toContainText("Selling a day pass");
      await expect(gaps).toContainText("Showing their photo");
      // The sentence that explained *why* this gap exists has gone with the section that
      // held it: the names above are what a reader needs, and the reasoning is in
      // `contracts/ui/design-compliance.md`.
      // And the half of the canvas's own header line this screen does not carry, said here
      // rather than left to differ silently from the drawing.
      await expect(gaps).toContainText("Naming the club and the plan");
    });

  test("reads in Arabic, including the badge", async ({ page }) => {
    // **A vocabulary is never a label**, and this is the first screen in the app to render
    // one from the design system's closed English set. `MESSAGE_KEYS` compares the two
    // catalogues against each other and is structurally blind to a string that never became
    // a key, so the only thing that can see this is a page in the other language.
    await page.getByRole("button", { name: "العربية" }).click();
    await page.waitForURL(new RegExp(`/desk/denials/${creds.personId}`));
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.locator(".ds-page-head")).toContainText("ممنوع");
    await expect(page.locator(".ds-page-head")).not.toContainText("Denied");
    await expect(page.locator(".ds-denial-say")).toContainText("ارفع الجلسة");
  });

  for (const theme of ["light", "dark"] as const) {
    test(`no accessibility violations: ${theme}`, async ({ page }) => {
      if (theme === "dark") {
        await page.getByRole("button", { name: "Dark" }).click();
        await page.waitForURL(new RegExp(`/desk/denials/${creds.personId}`));
      }
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      expect(results.violations).toEqual([]);
    });
  }
});

test.describe("the same refusal, once the reader has stepped up", () => {
  /**
   * **A saved session can be stepped up once, and then it is gone.** MOD-007 revokes the
   * session a step-up came from and opens a new one, so a spec that stepped up the shared
   * cookie signs out every spec after it. Each test here signs in for itself.
   */
  test.beforeEach(async ({ page }) => {
    await signIn(page);
    await page.goto(AT);
    await page.getByRole("link", { name: /read why it was refused/ }).click();
    await stepUp(page);
  });

  test("says what actually happened, and names the member", async ({ page }) => {
    await expect(page).toHaveURL(new RegExp(`/desk/denials/${creds.personId}`));
    // The real code, which is the fact the split is about -- not merely the real prose.
    await expect(page.locator(".ds-denial-say")).toContainText("A pass or a class credit");
    // And the module's own private reason beneath it, which is where the detail lives.
    await expect(page.locator("main")).toContainText("nothing that admits them here");
    // Stepped up, the identity-class name is readable, so the title is the person.
    await expect(page.locator(".ds-page-head")).toContainText("Jane Member");
  });

  test("offers the form, with the three reasons the canvas names", async ({ page }) => {
    // **The assertion the whole pattern rests on**, and the reason this block steps up for
    // real: the claim is not "a form exists" but "a reader at an ordinary sign-in can reach
    // it", and the only way to know is to follow the offer and look.
    const form = page.locator("form.ds-override-form");
    await expect(form).toBeVisible();
    await expect(form.getByRole("radio", { name: "Renewing today" })).toBeChecked();
    await expect(form.getByRole("radio", { name: "Manager approved" })).toBeVisible();
    await expect(form.getByRole("radio", { name: "Resolving a dispute" })).toBeVisible();
    await expect(form.getByRole("button", { name: "Let them in, flag it" })).toBeVisible();
    // What it costs, above the button: "records your name, the reason, and appears in the
    // access log".
    await expect(page.locator(".ds-denial-override")).toContainText("appears in the access log");
  });

  test("meets the touch target floor this screen's density makes mandatory", async ({
    page,
  }) => {
    // A desk presses this while looking at a person rather than at the screen. 44px is "the
    // minimum target, not a style".
    const box = await page.locator("form.ds-override-form button").boundingBox();
    expect(box).not.toBeNull();
    expect(box!.height).toBeGreaterThanOrEqual(44);
  });
});

test.describe("a refusal somebody has already answered", () => {
  test("says so rather than offering the button again", async ({ page }) => {
    // **Offering it twice would admit the same person twice in an insert-only log**, and the
    // check comes before the permission one: a step-up for work already done sends a
    // receptionist to find a recovery code for nothing. Seeded by the fixture, so this
    // branch renders from a real row rather than only in a component test.
    await useOwnerSession(page);
    await page.goto(ANSWERED);
    const block = page.locator(".ds-denial-override");
    await expect(block).toContainText("already let them in");
    await expect(page.locator("form.ds-override-form")).toHaveCount(0);
    await expect(block.getByRole("link")).toHaveCount(0);
  });
});

test.describe("what a weaker credential is given", () => {
  test("a session without the decision read is refused the screen", async ({ page }) => {
    // The reader holds `access.zone.read` and not `access.decision.read`, which is the pair
    // that proves this gate rather than a sibling.
    await useReaderSession(page);
    await page.goto(AT);
    await expect(page.locator("main").getByRole("status")).toContainText(/not permitted/i);
    await expect(page.locator(".ds-denial-say")).toHaveCount(0);
  });
});

test.describe("a person with nothing refused", () => {
  test("is told there is nothing to explain, rather than shown an empty screen",
    async ({ page }) => {
      // A blank page here reads as "the product is broken", and a refusal panel with no
      // refusal in it reads as a refusal. The staff member has no credential at all.
      await useOwnerSession(page);
      await page.goto(`/desk/denials/${creds.staffWorkingPersonId}`);
      await expect(page.locator("main")).toContainText("nothing to explain");
    });

  test("an unknown or malformed person id is a message, not a 500", async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/desk/denials/11111111-1111-4111-8111-111111111111");
    await expect(page.locator("main")).toContainText("nothing to explain");
    // A malformed id is a 422 from the module rather than an empty history, so the page
    // says something went wrong rather than "nothing has been refused" -- which would be a
    // confident wrong answer about a person who may well have been.
    await page.goto("/desk/denials/not-a-uuid");
    await expect(page.locator("main").getByRole("alert")).toBeVisible();
  });
});
