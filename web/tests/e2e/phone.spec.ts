import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useOwnerSession } from "./sign-in";

/**
 * No surface scrolls sideways on a phone.
 *
 * **Seven of thirteen pages did, and no test in four layers noticed**, because every
 * assertion in this suite is about text and structure and all of them pass at any width. A
 * page that scrolls sideways hides its own right-hand edge: on the schedule board "Free" and
 * "Status" were simply off the screen, and nothing in the product said so.
 *
 * The fix is two CSS rules -- a table scrolls inside itself, and a label/value grid collapses
 * and is allowed to shrink -- but the rules are not the evidence. This is: every surface, at
 * the narrowest width the design system claims to support, asserted to have no horizontal
 * scroll at all.
 */

const creds = fixture();
const PHONE = { width: 375, height: 812 };

const surfaces: [string, string][] = [
  ["the overview", "/"],
  ["the schedule board", "/schedule"],
  ["a session", `/schedule/${creds.bookedSessionId}`],
  ["the configuration board", "/configuration"],
  ["the operations board", "/operations"],
  ["the fleet board", "/fleet"],
  ["a device", `/fleet/${creds.deviceId}`],
  ["the organization", "/organization"],
  ["the door board", "/access"],
  ["a zone", `/access/${creds.zoneId}`],
  ["the permissions page", "/permissions"],
  ["the people list", "/people"],
  ["a member", `/people/${creds.personId}`],
];

test.describe("at phone width", () => {
  test.use({ viewport: PHONE });

  for (const [name, path] of surfaces) {
    test(`${name} does not scroll sideways`, async ({ page }) => {
      await useOwnerSession(page);
      await page.goto(path);
      const overflow = await page.evaluate(() => ({
        by:
          document.documentElement.scrollWidth - document.documentElement.clientWidth,
      }));
      expect(overflow.by, `${path} overflows by ${overflow.by}px`).toBeLessThanOrEqual(0);
    });
  }

  test("a table that scrolls inside itself is still reachable from a keyboard", async ({
    page,
  }) => {
    // The rule that makes a table scroll is also the rule that creates a scrollable region,
    // and axe requires one to be focusable. Running the check at this width is the point:
    // every other axe run in this suite is at desktop width, where no table scrolls at all.
    await useOwnerSession(page);
    await page.goto("/operations");
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(results.violations).toEqual([]);
  });
});
