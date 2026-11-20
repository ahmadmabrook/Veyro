import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Banner } from "@/components/ds/banner";
import { BUTTON_HEIGHT, Button, requiredSize } from "@/components/ds/button";
import { Card } from "@/components/ds/card";
import { DataGrid, MoneyCell, type Column } from "@/components/ds/data-grid";
import {
  SEVERITY, StatusBadge, VOCABULARY, rollUp,
} from "@/components/ds/status-badge";

import contracts from "@/design/contracts.json";

/**
 * The design system's own contracts, asserted where they are implemented.
 *
 * **Every assertion here is traceable to a sentence in `veyro-product-experience-design/`**,
 * carried into `contracts.json` by `src/design/extract.mjs` and pinned by digest. Where a rule
 * is a row in the extracted data, the test reads the data rather than a literal — the
 * Foundations document is explicit that "four precision slips in this project were all caused
 * by a number being copied rather than referenced", and the discipline is the same for a rule.
 */

describe("Button — §22, §66", () => {
  it("implements every variant the source states, and no others", () => {
    const stated = contracts.stated_apis.Button.variant;
    for (const variant of stated) {
      const { unmount } = render(
        <Button label={`Do ${variant}`} variant={variant as "primary"} />,
      );
      expect(screen.getByText(`Do ${variant}`)).toBeTruthy();
      unmount();
    }
    expect(stated).toHaveLength(7);
  });

  it("maps its three sizes to the heights the source gives", () => {
    expect(BUTTON_HEIGHT).toEqual(contracts.stated_apis.Button.sizes_px);
  });

  it("keeps the label while loading, and marks itself busy", () => {
    // "Loading sets aria-busy and keeps the label -- never replaced by a spinner alone."
    render(<Button label="Send payment links" state="loading" />);
    const button = screen.getByRole("button", { name: /Send payment links/ });
    expect(button.getAttribute("aria-busy")).toBe("true");
    expect(within(button).getByText("Send payment links")).toBeTruthy();
  });

  it("gives an icon-only button an accessible name", () => {
    // "An accessible name in both languages even when icon-only."
    render(<Button label="More actions" variant="icon" icon={<span>⋯</span>} />);
    expect(screen.getByRole("button", { name: "More actions" })).toBeTruthy();
  });

  it("renders an anchor for href rather than a button pretending to be a link", () => {
    // "Never a link styled as a button" -- and the inverse is the same mistake.
    render(<Button label="View invoice" href="/invoices/1" variant="link" />);
    const link = screen.getByRole("link", { name: "View invoice" });
    expect(link.tagName).toBe("A");
    expect(link.getAttribute("role")).toBeNull();
  });

  it("forces lg at the densities where 44px is mandatory", () => {
    // "lg is mandatory in Touch and Spacious density -- it is the 44px minimum target, not a
    // stylistic option." And "sm is Compact-only".
    expect(requiredSize("touch", "sm")).toBe("lg");
    expect(requiredSize("spacious", "md")).toBe("lg");
    expect(requiredSize("default", "sm")).toBe("md");
    expect(requiredSize("compact", "sm")).toBe("sm");
    expect(BUTTON_HEIGHT[requiredSize("touch", "sm")]).toBe(44);
  });
});

describe("StatusBadge — §30", () => {
  it("knows a severity for every status in every vocabulary, and no others", () => {
    const all = Object.values(VOCABULARY).flat();
    for (const status of all) expect(SEVERITY[status], status).toBeTruthy();
    // The map holds nothing the vocabularies do not: a severity for a status the component
    // cannot render is a status somebody meant to add and did not.
    for (const status of Object.keys(SEVERITY)) expect(all).toContain(status);
  });

  it("has four severities and success is not one of them", () => {
    // "Four steps, not five -- 'success' is not a severity, it is the neutral case."
    const used = new Set(Object.values(SEVERITY));
    expect([...used].sort()).toEqual(["attention", "critical", "info", "neutral"]);
    expect(SEVERITY.Paid).toBe("neutral");
    expect(SEVERITY.Active).toBe("neutral");
    expect(SEVERITY.Confirmed).toBe("neutral");
  });

  it("carries its label, because colour alone is a defect at any density", () => {
    render(<StatusBadge status="Overdue" />);
    expect(screen.getByText("Overdue")).toBeTruthy();
  });

  it("keeps the full text in the accessible name when the label abbreviates", () => {
    // "Label may abbreviate at Compact but never disappear. Full text in the accessible name
    // regardless."
    render(<StatusBadge status="Partially refunded" abbreviated="Part. refunded" />);
    expect(screen.getByLabelText("Partially refunded")).toBeTruthy();
    expect(screen.getByText("Part. refunded")).toBeTruthy();
  });

  it("rolls a row up to its worst severity", () => {
    expect(rollUp(["Paid", "Overdue"])).toBe("critical");
    expect(rollUp(["Paid", "Trial"])).toBe("info");
    expect(rollUp(["Paid"])).toBe("neutral");
    expect(rollUp([])).toBeNull();
  });
});

describe("Banner — §29", () => {
  it("is an alert only when critical", () => {
    // "role=status for info and success, role=alert only for critical. Never both -- an alert
    // interrupts, and most banners should not."
    const { unmount } = render(<Banner severity="critical">Payments are not processing</Banner>);
    expect(screen.getByRole("alert")).toBeTruthy();
    unmount();
    render(<Banner severity="info">A default value is in use</Banner>);
    expect(screen.getByRole("status")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("refuses to be dismissible while a critical condition holds", () => {
    // Not a caller's choice: "Critical banners are not dismissible while the condition holds."
    render(
      <Banner severity="critical" dismissible>
        The provider has been unreachable since 09:14
      </Banner>,
    );
    expect(screen.queryByRole("button", { name: "Dismiss" })).toBeNull();
  });
});

describe("Card — §31", () => {
  it("records which of the six kinds it is", () => {
    // "A card that only draws a border around a paragraph is deleted." `kind` is required, so
    // a caller has to answer which one -- and if none fits, it is not a card.
    const { container } = render(<Card kind="summary">Twelve invoices</Card>);
    expect(container.querySelector(".ds-card-summary")).toBeTruthy();
  });
});

describe("DataGrid — §25", () => {
  type Row = { id: string; member: string; balance: string; plan: string };
  const rows: Row[] = [
    { id: "1", member: "Ahmad Nabulsi", balance: "55.000", plan: "Club" },
    { id: "2", member: "Lina Haddad", balance: "0.000", plan: "Flex" },
  ];
  const columns: Column<Row>[] = [
    { header: "Member", kind: "person", priority: 1, render: (r) => r.member },
    { header: "Plan", kind: "text", priority: 2, render: (r) => r.plan },
    {
      header: "Balance",
      kind: "money",
      priority: 3,
      render: (r) => <MoneyCell formatted={r.balance} currency="JOD" />,
      restricted: (r) => r.id === "2",
    },
  ];
  const grid = (state?: Parameters<typeof DataGrid<Row>>[0]["state"]) =>
    render(
      state
        ? <DataGrid caption="Members" columns={columns} rows={rows} rowKey={(r) => r.id} state={state} />
        : <DataGrid caption="Members" columns={columns} rows={rows} rowKey={(r) => r.id} />,
    );

  it("renders a restricted cell as a word, never blank and never zero", () => {
    // "A blank money cell reads as JOD 0.00 and that is a financial misstatement."
    grid();
    const restricted = screen.getAllByText("restricted");
    expect(restricted.length).toBeGreaterThan(0);
    expect(screen.queryByText("0.000")).toBeNull();
  });

  it("declares a priority per column so the collapse is a rule, not a measurement", () => {
    const { container } = grid();
    expect(container.querySelectorAll(".ds-col-p1").length).toBeGreaterThan(0);
    expect(container.querySelectorAll(".ds-col-p2").length).toBeGreaterThan(0);
    expect(container.querySelectorAll(".ds-col-p3").length).toBeGreaterThan(0);
  });

  it("moves a dropped column into the primary cell rather than losing it", () => {
    // "Low-priority columns collapse into the primary cell as a secondary line."
    const { container } = grid();
    const secondary = container.querySelector(".ds-row-secondary");
    expect(secondary).toBeTruthy();
    expect(within(secondary as HTMLElement).getByText("Plan")).toBeTruthy();
  });

  it("loads as skeleton rows with a count, never a centred spinner", () => {
    // "Skeleton rows at the real row height, header already solid, count as 'loading…'.
    // Never a centred spinner -- layout must not jump when data lands."
    const { container } = grid({ kind: "loading", rows: 3 });
    expect(container.querySelectorAll(".ds-skeleton").length).toBeGreaterThan(0);
    expect(screen.getByText("loading…")).toBeTruthy();
    expect(container.querySelector(".ds-spinner")).toBeNull();
    // The header is already solid while loading.
    expect(screen.getByText("Member")).toBeTruthy();
  });

  it("tells three empties apart, because implying absence is a lie", () => {
    const permission = render(
      <DataGrid
        caption="Members"
        columns={columns}
        rows={[]}
        rowKey={(r) => r.id}
        state={{ kind: "empty-permission", because: "You do not have access to members at Abdoun." }}
      />,
    );
    expect(screen.getByText(/do not have access/)).toBeTruthy();
    permission.unmount();

    const filtered = render(
      <DataGrid
        caption="Members"
        columns={columns}
        rows={[]}
        rowKey={(r) => r.id}
        state={{ kind: "empty-filtered", filters: ["Club+", "Khalda"] }}
      />,
    );
    expect(screen.getByText(/Club\+ · Khalda/)).toBeTruthy();
    filtered.unmount();

    render(
      <DataGrid
        caption="Members"
        columns={columns}
        rows={[]}
        rowKey={(r) => r.id}
        state={{ kind: "empty-first-use", explains: "No members yet — import your existing list." }}
      />,
    );
    expect(screen.getByText(/No members yet/)).toBeTruthy();
  });

  it("keeps the rows when something failed, rather than replacing them with an error page", () => {
    // "Keeps whatever loaded, states what failed and offers retry."
    grid({ kind: "error", failed: "Retail figures could not be loaded." });
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText("Ahmad Nabulsi")).toBeTruthy();
  });

  it("reads money with its kind", () => {
    // "Money is read with its kind because a bare number is ambiguous."
    render(<MoneyCell formatted="55.000" currency="JOD" />);
    expect(screen.getByLabelText("55.000 JOD")).toBeTruthy();
  });

  it("is one tab stop, not one per row", () => {
    // "Fourteen rows must not cost fourteen tab stops."
    const { container } = grid();
    const table = container.querySelector("table");
    expect(table?.getAttribute("tabindex")).toBe("0");
    expect(container.querySelectorAll("tr[tabindex]").length).toBe(0);
  });
});
