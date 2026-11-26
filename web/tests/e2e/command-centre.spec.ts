import { readFileSync } from "node:fs";
import { join } from "node:path";

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { useDeskSession, useOwnerSession } from "./sign-in";

/**
 * The row whose *category chip* is this, not whose text mentions the word.
 *
 * `filter({ hasText: "MONEY" })` matched two rows: the compliance row's evidence says "the
 * money is collected". A locator that matches on body prose is coupled to copy it is not
 * testing -- the same trap as the positional cell locator this suite already records.
 */
function row(page: import("@playwright/test").Page, category: string) {
  return page.locator(".ds-attention")
    .filter({ has: page.locator(".ds-attention-category", { hasText: new RegExp(`^${category}$`, "i") }) });
}

/**
 * ADM-CC-01 … ADM-CC-05, the Command Center, in a real browser against a real backend.
 *
 * **What was at `/` before this was a session-and-permissions diagnostic**, and it passed its
 * own tests. That is the point of this file: every assertion here is about a *rendered value*
 * rather than a label, because this repository has already paid for the weaker kind. The
 * schedule board shipped `15:00` for an 18:00 class with 140 green assertions behind it, and
 * every one of them asserted that the timezone was *named* on the page.
 *
 * The fixture seeds all four queue classes deliberately — a payment in recovery, a rejected
 * filing, a membership expiring inside the week and three classes with no coach — because an
 * empty queue is a legitimate state (canvas 4) in which every assertion about a row passes
 * vacuously.
 */

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.describe("the Command Center", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/");
  });

  test("is the Command Center and not a session diagnostic", async ({ page }) => {
    // The two facts the old page led with. Neither belongs on the product's front door: the
    // identity and its assurance are on `/account`, the gate table is on `/permissions`.
    const body = await page.locator("main").innerText();
    expect(body).not.toContain("Signed in as");
    expect(body).not.toContain("Assurance level");
    // And the heading counts the queue rather than naming the app.
    await expect(page.getByRole("heading", { level: 1 }))
      .toContainText(/things? need you this morning/);
  });

  test("is at Compact density, which the design states for this screen", async ({ page }) => {
    // "CANVAS 1 · OWNER · ALL LOCATIONS · NORMAL OPERATIONAL DAY · 1440×900", and the
    // foundation audit: "Command Center runs Compact, Member 360 runs Default".
    const row = await page.evaluate(() => {
      const scope = document.querySelector("[data-density]");
      return scope ? getComputedStyle(scope).getPropertyValue("--density-row").trim() : null;
    });
    // **Read from the design source, never copied.** `shell-tokens.test.mjs` carries the
    // reason in full -- "four precision slips in this project were all caused by a number
    // being copied rather than referenced" -- and this assertion was one: it pinned 34px,
    // which stopped being Compact's row height when the density modes were rebuilt around a
    // larger type scale, and failed for the design having changed rather than the screen.
    // `process.cwd()` rather than `import.meta.url`: Playwright transpiles a spec to CJS, so
    // `import.meta` is a syntax error there and takes the whole run with it. The config's
    // directory is the cwd.
    const ds = JSON.parse(readFileSync(
      join(process.cwd(), "src/design/ds.json"), "utf8",
    )) as { DENSITY: string[][] };
    const compact = ds.DENSITY.find((mode) => mode[0] === "Compact");
    expect(compact, "Compact is not in the design source's density table").toBeDefined();
    const rows = compact?.[1];
    expect(row).toBe(`${String(rows).split("/")[0]?.trim()}px`);
  });

  test("renders four metric cells, and the fourth has no figure", async ({ page }) => {
    const metrics = page.locator(".ds-metric");
    // Four, or five when a tenant bills in two currencies: the collected cell is per
    // currency, which is the money rule rather than a layout choice.
    expect(await metrics.count()).toBeGreaterThanOrEqual(4);
    // **The fourth cell has a figure now, and this test asserted the gap rather than the
    // finding.** It pinned `data-freshness="unavailable"` on a LEAD CONVERSION cell whose
    // reason said Veyro is not tracking leads yet -- which stopped being true when `/leads`
    // shipped, so the product's front door was telling every owner it could not do something
    // it does. The cell reads from `crm.board` and carries a real count.
    //
    // What survives is the finding underneath: **no cell fabricates a figure.** A number here
    // is a measurement, an absent one carries a reason, and neither is ever a zero or an
    // em dash standing in for one. That is asserted over every cell rather than over the one
    // that happened to be unavailable, so it cannot go stale the next time a gap closes.
    const leads = metrics.filter({ hasText: /LEADS/i }).first();
    await expect(leads.locator(".ds-metric-value")).toHaveCount(1);
    for (const cell of await metrics.all()) {
      const unavailable =
        (await cell.getAttribute("data-freshness")) === "unavailable";
      if (unavailable) {
        await expect(cell.locator(".ds-metric-value")).toHaveCount(0);
        await expect(cell.locator(".ds-metric-unavailable")).not.toHaveText(/^\s*(0|—)\s*$/);
      } else {
        await expect(cell.locator(".ds-metric-value")).toHaveCount(1);
      }
    }
    await expect(metrics.first()).not.toContainText(/ADM-[A-Z]+|MOD-\d+/);
  });

  test("the collected figure has a comparison that is not a fabricated zero", async ({
    page,
  }) => {
    // `change_bp` is null with no baseline, and `0%` would read as "unchanged" — a confident
    // wrong answer about a month nobody can compare against.
    const collected = page.locator(".ds-metric").filter({ hasText: "COLLECTED" }).first();
    // **The finding is the absent zero, not the wording.** This pinned "compare against",
    // which was the tail of a seven-word statement of what is missing -- and that statement
    // used to lead, pushing the pace (the one figure a manager can act on) to the end of the
    // line. The pace leads now and the absence reads "first month on record". What has to
    // stay true is that nothing fabricates a change: no `0%`, and no delta arrow over a month
    // with no baseline.
    await expect(collected.locator(".ds-metric-value")).toContainText("JOD");
    const comparison = collected.locator(".ds-metric-comparison");
    await expect(comparison).toContainText("pace");
    await expect(comparison).not.toContainText("0%");
    await expect(collected.locator(".ds-metric-delta")).toHaveCount(0);
  });

  test("the queue carries all four classes the fixture seeded, in the design's order", async ({
    page,
  }) => {
    const rows = page.locator(".ds-attention");
    await expect(rows).toHaveCount(4);
    const categories = await page.locator(".ds-attention-category").allInnerTexts();
    expect(categories.map((c) => c.trim().toUpperCase())).toEqual([
      "MONEY", "COMPLIANCE", "RETENTION", "STAFFING",
    ]);
  });

  test("a headline states a fact, with its count agreeing in English", async ({ page }) => {
    // §38: "The headline is never a metric name — '6 payments failed' not 'Payment failure
    // rate'." And the plural agrees: the page rendered "1 payments are in recovery" before
    // the catalogue grew CLDR forms, which is a defect no label assertion could see.
    //
    // **Two, because ADM-PAY-05's fixture needs both halves of its distinction** — a debt
    // with a membership behind it and one without — so this now exercises the `other` form
    // where it used to exercise `one`. Both matter and only one can be seeded here; the
    // singular is proved in `tests/component/command-centre.test.ts`.
    await expect(row(page, "money").locator(".ds-attention-headline"))
      .toHaveText("2 payments are in recovery");
  });

  test("severity is never colour, and the field at the row's head carries kind", async ({
    page,
  }) => {
    // §38's contract: a signal carried only by colour is a colour-only signal. **This used
    // to assert a 3px severity edge and the property is now satisfied more strongly than the
    // edge satisfied it** -- the direction contract says the field at a row's head carries
    // "its kind", and keying it on severity made three of the four `color.category.*` tokens
    // unread while every row wore another category's declared colour (retention rendering
    // gold, which is money's). The field carries kind now, so severity has no colour channel
    // at all rather than a second one: it is the queue's worst-first order, the "2 critical"
    // in the head, and each headline stating the fact in words.
    //
    // So what is asserted is the property rather than the mechanism -- severity is readable
    // without colour, and no two categories share a field.
    const money = row(page, "money");
    await expect(money).toHaveAttribute("data-severity", "critical");
    await expect(money.locator(".ds-attention-category")).toHaveText(/MONEY/i);

    const fields = await page.locator(".ds-attention").evaluateAll((rows) =>
      rows.map((r) => ({
        category: r.getAttribute("data-category"),
        severity: r.getAttribute("data-severity"),
        field: getComputedStyle(
          r.querySelector(".ds-attention-category") as Element,
        ).backgroundColor,
      })),
    );
    // One field per kind, and no kind sharing another's.
    const byCategory = new Map(fields.map((f) => [f.category, f.field]));
    expect(byCategory.size).toBe(new Set(byCategory.values()).size);
    // And two rows of the same severity in different kinds do not match, which is what
    // proves the field is not keyed on severity.
    const critical = fields.filter((f) => f.severity === "critical");
    expect(critical.length).toBeGreaterThanOrEqual(2);
    expect(new Set(critical.map((f) => f.field)).size).toBe(critical.length);
  });

  test("staffing is a condensed row in the info tone, as the canvas draws it", async ({
    page,
  }) => {
    // ADM-CC-01's own component list: "AttentionRow ×5 (2 full, 2 condensed, 1 collapsed
    // group)". STAFFING and LEADS are the condensed pair, and the canvas draws STAFFING in
    // `info` **with eighteen members booked** -- so the severity is about what the item is,
    // not how many it touches. This screen escalated it to `critical` once anybody was
    // affected, which reads as a sensible rule and is not the one the design draws.
    const staffing = row(page, "staffing");
    await expect(staffing).toHaveAttribute("data-severity", "info");
    await expect(staffing).toHaveAttribute("data-density", "condensed");

    // One line: the chip, the headline and the action share a row rather than stacking.
    const chip = await staffing.locator(".ds-attention-category").boundingBox();
    const headline = await staffing.locator(".ds-attention-headline").boundingBox();
    expect(chip).not.toBeNull();
    expect(headline).not.toBeNull();
    expect(Math.abs((chip!.y + chip!.height / 2) - (headline!.y + headline!.height / 2)))
      .toBeLessThan(6);

    // **The explanation is still there, for anybody who needs more than a glance.** A
    // condensed row drops the paragraph from the page and keeps it as the row's accessible
    // description -- dropping it outright would be a headline with nowhere to go.
    const describedBy = await staffing.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    await expect(page.locator(`#${describedBy}`)).not.toBeEmpty();
  });

  test("the money figure sits at the logical end and names what it means", async ({ page }) => {
    const money = row(page, "money");
    await expect(money.locator(".ds-attention-money")).toContainText("at risk");
    await expect(money.locator(".ds-attention-money")).toContainText("JOD");
  });

  test("there is no interpretation panel, because there is no interpretation", async ({
    page,
  }) => {
    // **This asserted a withheld panel and now asserts its absence.** The panel rendered a
    // tracked kicker -- "VEYRO INTERPRETATION · NOT A CONFIRMED FIGURE" -- over a paragraph
    // explaining that no module in this build produces an interpretation. Both halves are
    // wrong for an operator's screen: the kicker is a banned pattern, and a reader does not
    // need to be told that an absent feature is absent. The engineering record moved to
    // `.impeccable/surfaces/admin.md`.
    await expect(page.locator(".ds-ai")).toHaveCount(0);
  });

  // **The G7 colour guarantee moved to the token layer**, where it does not need a panel.
  // This asserted the AI region's computed border on the Command Center, and that region is
  // no longer rendered here -- there is no interpretation in this build and an operator does
  // not need a panel saying so. The requirement is unchanged and is real: "a tenant brand on
  // an AI panel would make inference look like a first-party assertion", so `ai.600` is
  // system-owned in both themes and must not collide with the action colour or any status.
  // `tests/unit/contrast.test.mjs` asserts that now, in both themes rather than one.
  //
  // Worth recording about the test that was here: its second assertion was vacuous. It read
  // `--color-action-default`, a custom property nothing in this app ever defined, so
  // `getPropertyValue` returned the empty string and "the border is not the accent" was
  // trivially true on every run. The undefined-property sweep in `design:check` is what
  // would now catch that.

  test("only the last week bucket can be partial, and never more than one", async ({ page }) => {
    // "The last bar is a partial week and is marked, not extrapolated."
    //
    // **At most one, not exactly one**, and the difference is a day of the week. The week
    // starts Saturday, so on a Friday today *is* the bucket's last day and nothing is
    // outstanding -- the chart is correct and has no partial bar. The first version of this
    // test asserted exactly one and was true six days in seven, which is the green that
    // depends on when it ran rather than on the behaviour: the same shape as the fixture
    // whose freshness expired ten minutes after it was seeded. The invariant is that a
    // partial bucket can only ever be the last one.
    const bars = page.locator(".ds-bar");
    expect(await bars.count()).toBe(12);
    const partial = await bars.evaluateAll((els) =>
      els.map((el) => el.getAttribute("data-partial") === "true"));
    expect(partial.filter(Boolean).length).toBeLessThanOrEqual(1);
    expect(partial.slice(0, -1).every((p) => p === false)).toBe(true);
  });

  test("the chart axis reads as a day and a month, not an ISO date", async ({ page }) => {
    // An ISO date wrapped onto two lines in the narrowest column on the page, which is how
    // this was found — by looking at the rendered chart.
    const first = await page.locator(".ds-bar").first().locator("span").first().innerText();
    expect(first).toMatch(/^\d{1,2} \w{3,9}$/);
  });

  test("the pace is named beside the figure it is a pace for", async ({ page }) => {
    // A figure a manager could quote as collections is the one thing this must not produce,
    // and that requirement is unchanged. What changed is where it is met: the server's own
    // "straight-line projection ... must not be rendered as a total" paragraph was written
    // for an engineer and sat under the chart, two sections away from the number. The word
    // now sits in the collected figure's own comparison line, next to the amount.
    const collected = page.locator(".ds-metric").filter({ hasText: "COLLECTED" });
    await expect(collected).toContainText(/pace/i);
    await expect(page.locator("main")).not.toContainText("straight-line projection");
  });

  test("says the breakdown is by legal entity, in the operator's own language", async ({
    page,
  }) => {
    // The product fact is the same and the sentence is not: it used to explain the tenant
    // hierarchy and name `MOD-004` and `by_legal_entity` to a gym owner.
    await expect(page.locator("main")).toContainText("legal entity");
    await expect(page.locator("main")).toContainText(/issued the invoices/i);
    await expect(page.locator("main")).not.toContainText(/breaks this down by club/);
  });

  test("explains nothing about its own internals to an operator", async ({ page }) => {
    // **This asserted the gap table and now asserts that it is gone.** Seven notes written
    // for engineers sat on the product's front door, naming module and screen ids; they are
    // recorded in the surface brief instead. The honesty requirement they served is met where
    // it belongs -- a figure the build cannot derive carries a reason in the place the figure
    // would have been, which the fourth-metric test above asserts.
    const main = page.locator("#main");
    await expect(main.getByText("What this screen does not do yet")).toHaveCount(0);
    await expect(main).not.toContainText(/ADM-[A-Z]+-?\*?|MOD-\d+|by_legal_entity|pace_minor/);
  });

  test("has no axe violations", async ({ page }) => {
    const results = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(results.violations).toEqual([]);
  });

  test("does not scroll sideways at phone width", async ({ page }) => {
    // Seven of thirteen surfaces did, and a reader on a phone could not see that columns
    // existed. The metric row is the one deliberate exception and it is its own scroll
    // container, not the page's.
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/");
    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBe(0);
  });

  test("the queue never collapses, at any width", async ({ page }) => {
    // bp.md: "The attention queue never collapses — it is the reason the page exists."
    for (const width of [1600, 1400, 1000, 760, 375]) {
      await page.setViewportSize({ width, height: 900 });
      await expect(page.locator(".ds-attention")).toHaveCount(4);
      const hidden = await page.locator(".ds-attention").evaluateAll((els) =>
        els.filter((el) => getComputedStyle(el).display === "none").length);
      expect(hidden, `rows hidden at ${width}px`).toBe(0);
    }
  });
});

test.describe("the Command Center for a session that cannot see everything", () => {
  test("does not claim nothing needs you when a panel was refused", async ({ page }) => {
    // **The defect this exists for.** The desk session holds the schedule read and not the
    // money ones, so three of the four feeds are refused — and the first version told it
    // "Nothing needs you right now", which is a statement about the club made out of the
    // page's own permissions.
    await useDeskSession(page);
    await page.goto("/");
    const heading = await page.getByRole("heading", { level: 1 }).innerText();
    expect(heading).not.toBe("Nothing needs you right now");
    // And the body says what the heading is a statement about.
    await expect(page.locator("main")).toContainText("not a statement about the whole club");
  });
});
