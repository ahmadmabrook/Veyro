import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Chrome, RailGroup, RailItem } from "@/components/ds/chrome";
import { ICON_NAMES, Icon, mirrors } from "@/components/ds/icon";
import { MoneyValue } from "@/components/ds/money-value";
import { PageHeader } from "@/components/ds/page-header";

/**
 * The chrome, the rail, the icons and MoneyValue — the four pieces the drawn canvases have
 * and this app did not.
 *
 * **None of this was caught by a test, because none of it existed to be caught.** The app
 * rendered in the system face under a stylesheet that named IBM Plex, with a flat rail of
 * fifteen links, no icons, no counts, no groups and no chrome bar at all. A comparison with
 * the design was the only thing that could have found it, and that is what found it.
 */

describe("Icon — §15", () => {
  it("draws on a 24 grid at a 1.5px stroke, whatever size it is asked for", () => {
    // "1.5px stroke on a 24px grid, optically corrected at 16px rather than scaled."
    const { container } = render(<Icon name="members" size={16} />);
    const svg = container.querySelector("svg")!;
    expect(svg.getAttribute("viewBox")).toBe("0 0 24 24");
    expect(svg.getAttribute("stroke-width")).toBe("1.5");
    expect(svg.getAttribute("width")).toBe("16");
  });

  it("is never in the accessibility tree", () => {
    // "Icons never carry meaning alone — every status icon ships with its label, so an
    // icon-only status is a defect, not a density choice." There is no prop to change this.
    const { container } = render(<Icon name="payments" />);
    expect(container.querySelector("svg")!.getAttribute("aria-hidden")).toBe("true");
  });

  it("declares which icons mirror in RTL and which never do", () => {
    // §15's two lists, as data. The design folder ships no icon manifest, so this is it.
    expect(mirrors("chevron-end")).toBe(true);
    expect(mirrors("arrow-end")).toBe(true);
    // "NEVER MIRRORS — clock · search · checkmark · media play · QR · logos · numerals"
    expect(mirrors("search")).toBe(false);
    expect(mirrors("scheduling")).toBe(false);
  });

  it("refuses a name it has no path for, rather than drawing an empty box", () => {
    expect(() => render(<Icon name={"no-such-icon" as never} />)).toThrow(/no icon named/);
  });

  it("carries every icon the rail asks for", () => {
    for (const name of [
      "command-center", "scheduling", "doors", "devices",
      "members", "staff", "permissions",
      "payments", "point-of-sale",
      "messages", "integrations",
      "organization", "configuration", "privacy", "operations", "account",
    ]) {
      expect(ICON_NAMES, `the rail needs ${name}`).toContain(name);
    }
  });
});

describe("the global chrome — §21", () => {
  it("renders the mark, the tenant and the scope", () => {
    render(<Chrome mark="V" organization="Nadi Group" scope="All locations">x</Chrome>);
    expect(screen.getByText("Nadi Group")).toBeTruthy();
    expect(screen.getByText("All locations")).toBeTruthy();
  });

  it("does not make the scope a control, because there is nothing to switch to", () => {
    // Every `permit` call in this build is tenant-wide -- MOD-014 records it as its own gap.
    // A menu offering to narrow the scope would be offering something the gate cannot do,
    // and the caret is the affordance that makes it look like one.
    const { container } = render(
      <Chrome mark="V" organization="Nadi Group" scope="All locations">x</Chrome>);
    expect(container.querySelector("button")).toBeNull();
    expect(container.querySelector(".ds-chrome-scope")!.tagName).toBe("SPAN");
  });
});

describe("the rail", () => {
  it("nests its items under the group, rather than putting a heading between them", () => {
    // A `<li role="presentation">` between list items is axe's `only-listitems`, and a
    // screen reader then counts the headings in the list's length. Found by axe the moment
    // the grouped rail shipped.
    const { container } = render(
      <ul>
        <RailGroup id="g" label="Operate">
          {/* A plain anchor: this test is about the list structure, and `next/link` would
              drag the router in for nothing. */}
          <li><span><RailItem icon="command-center" label="Command Center" /></span></li>
        </RailGroup>
      </ul>,
    );
    const section = container.querySelector(".ds-rail-section")!;
    expect(section.tagName).toBe("LI");
    const nested = section.querySelector("ul")!;
    expect(nested.getAttribute("aria-labelledby")).toBe("g");
    expect([...nested.children].every((child) => child.tagName === "LI")).toBe(true);
  });

  it("renders a count beside an item that has one, and nothing where there is none", () => {
    const { container, rerender } = render(
      <RailItem icon="members" label="Members" count="4,812" />);
    expect(container.querySelector(".ds-rail-count")!.textContent).toBe("4,812");
    rerender(<RailItem icon="doors" label="Doors" />);
    expect(container.querySelector(".ds-rail-count")).toBeNull();
  });
});

describe("MoneyValue — §39", () => {
  it("splits the fils for the aggregate kind, and never drops them", () => {
    // "aggregate · fils de-emphasised, never truncated" — `JOD 41,280 .00`.
    const { container } = render(
      <MoneyValue kind="aggregate" amountMinor={41_280_000} currency="JOD" />);
    expect(container.textContent).toBe("JOD 41,280.00");
    expect(container.querySelector(".ds-money-minor")!.textContent).toBe(".00");
  });

  it("keeps the figure in the accessibility tree", () => {
    // The first version hid it with `aria-hidden` and restated it in an `aria-label`, which
    // axe refuses on a role-less element -- so the figure was in the tree nowhere at all.
    const { container } = render(
      <MoneyValue kind="neutral" amountMinor={5_220} currency="JOD" />);
    const span = container.querySelector(".ds-money")!;
    expect(span.getAttribute("aria-hidden")).toBeNull();
    expect(span.getAttribute("aria-label")).toBeNull();
    expect(span.textContent).toBe("JOD 5.22");
  });

  it("makes a refund's sign explicit, never colour-only", () => {
    const { container } = render(
      <MoneyValue kind="refunded" amountMinor={2_800} currency="JOD" />);
    expect(container.textContent).toContain("−");
  });

  it("shows a word where a figure is withheld, never a blank and never a zero", () => {
    // "restricted · no permission · never blank, never zero" — the grid's own note calls a
    // blank money cell a financial misstatement.
    const { container } = render(
      <MoneyValue kind="restricted" restrictedLabel="Withheld" />);
    expect(container.textContent).toBe("Withheld");
  });

  it("uses an em-dash for not-applicable, which is distinct from zero", () => {
    const { container } = render(<MoneyValue kind="notApplicable" />);
    expect(container.textContent).toBe("—");
  });

  it("refuses a figure-bearing kind with no figure", () => {
    expect(() => render(<MoneyValue kind="owed" />)).toThrow(/needs an amount/);
  });
});

describe("PageHeader", () => {
  it("renders a title and its figures, and nothing where there are none", () => {
    const { container, rerender } = render(
      <PageHeader title="Members" figures={<>4,812 active</>} />);
    expect(container.querySelector(".ds-page-figures")!.textContent).toBe("4,812 active");
    // A screen with nothing to count says nothing here. An invented sentence would be the
    // prose this component exists to remove.
    rerender(<PageHeader title="Doors" />);
    expect(container.querySelector(".ds-page-figures")).toBeNull();
  });
});
