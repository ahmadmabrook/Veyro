import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Banner } from "@/components/ds/banner";
import { Button } from "@/components/ds/button";
import { Field, visibleMessage } from "@/components/ds/field";

/**
 * The shared controls, tested for the properties the design system makes structural.
 *
 * These are the assertions a browser cannot make cheaply -- an attribute on one element, a
 * handler that does or does not fire -- while the Playwright suite covers what only a browser
 * can: computed colour, mirrored layout, real focus. Neither replaces the other, and the split
 * is deliberate rather than historical.
 *
 * **`src/components/controls.tsx` is gone.** It held a Button with two of seven variants, a
 * field that rendered a hint and an error at once, and an Alert -- three ad-hoc components
 * duplicating approved design-system families, which the directive of 2026-11-20 forbids. The
 * assertions below moved to the families that replaced them, and the two that could not move
 * are the ones worth naming: the old field's "associates the hint and the error, in that
 * order" asserted a behaviour §23 rules out, because the message slot "holds exactly one
 * message at a time, priority error > warning > success > description". It is now a test that
 * exactly one is shown.
 */

describe("Button", () => {
  it("is announced while busy and keeps its label", async () => {
    const onClick = vi.fn();
    render(<Button label="Signing in…" state="loading" onClick={onClick} />);
    const button = screen.getByRole("button");
    // `aria-busy` rather than only a visual change: without it a screen-reader user gets no
    // signal that the form is in flight, and presses again.
    expect(button).toHaveAttribute("aria-busy", "true");
    // The contract is explicit that loading never replaces the label with a spinner.
    expect(button).toHaveTextContent("Signing in…");
    await userEvent.click(button, { pointerEventsCheck: 0 });
    expect(onClick).toHaveBeenCalled();
  });

  it("keeps its label when it is merely disabled, and does not fire", async () => {
    const onClick = vi.fn();
    render(<Button label="Sign in" state="disabled" onClick={onClick} />);
    const button = screen.getByRole("button");
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent("Sign in");
    expect(button).not.toHaveAttribute("aria-busy");
    await userEvent.click(button, { pointerEventsCheck: 0 });
    expect(onClick).not.toHaveBeenCalled();
  });

  it("sets no outline of its own, because the focus ring is system-owned", () => {
    // Guardrail G4 makes the ring non-configurable so "a tenant cannot ship an unnavigable
    // product". A component that set its own would be a component that can remove it.
    render(<Button label="Save" />);
    expect(screen.getByRole("button").style.outline).toBe("");
  });
});

describe("Field", () => {
  it("uses a real label rather than a placeholder", () => {
    render(<Field id="email" name="email" label="Email or phone" />);
    const input = screen.getByLabelText("Email or phone");
    expect(input).toBeInstanceOf(HTMLInputElement);
    // A placeholder disappears on focus, fails at small sizes and is not a name to a screen
    // reader, so there is no placeholder-as-label path in this component at all.
    expect(input).not.toHaveAttribute("placeholder");
  });

  it("shows exactly one message, and the error outranks the description", () => {
    // §23: "Message slot holds exactly one message at a time, priority error > warning >
    // success > description." The component this replaced rendered both, so a field that was
    // explained *and* invalid said two things and the reader read the first.
    render(
      <Field
        id="tenant"
        name="tenant_id"
        label="Tenant ID"
        description="The tenant this sign-in belongs to."
        message={{ kind: "error", text: "Required." }}
      />,
    );
    const input = screen.getByLabelText("Tenant ID");
    expect(input).toHaveAttribute("aria-describedby", "tenant-message");
    expect(document.getElementById("tenant-message")).toHaveTextContent("Required.");
    expect(screen.queryByText("The tenant this sign-in belongs to.")).toBeNull();
    expect(input).toHaveAttribute("aria-invalid", "true");
  });

  it("falls back to the description when there is no message", () => {
    render(
      <Field id="tenant" name="tenant_id" label="Tenant ID" description="The tenant." />,
    );
    const input = screen.getByLabelText("Tenant ID");
    expect(input).not.toHaveAttribute("aria-invalid");
    expect(input.getAttribute("aria-describedby")).toBe("tenant-message");
    expect(document.getElementById("tenant-message")).toHaveTextContent("The tenant.");
  });

  it("ranks the four message kinds the way the source states", () => {
    const description = "A description.";
    expect(visibleMessage({ kind: "error", text: "e" }, description)?.kind).toBe("error");
    expect(visibleMessage({ kind: "warning", text: "w" }, description)?.kind).toBe("warning");
    expect(visibleMessage({ kind: "success", text: "s" }, description)?.kind).toBe("success");
    expect(visibleMessage(null, description)?.kind).toBe("description");
    expect(visibleMessage(null)).toBeNull();
  });

  it("marks whichever side is rarer, not always the required one", () => {
    // "Required is marked, optional is not -- whichever is rarer gets the mark." A form where
    // all but one field is required marks the optional one.
    const required = render(
      <Field id="a" name="a" label="Amount" required rarer="required" />,
    );
    expect(screen.getByText("*", { exact: false })).toBeTruthy();
    required.unmount();
    render(<Field id="b" name="b" label="Note" rarer="optional" />);
    expect(screen.getByText("(optional)", { exact: false })).toBeTruthy();
  });

  it("isolates a value whose direction is not the page's", () => {
    // "numbers, phone, currency and IDs are bidi-isolated" -- per field type, not per locale.
    render(<Field id="phone" name="phone" label="Member phone" type="phone" />);
    expect(screen.getByLabelText("Member phone")).toHaveAttribute("dir", "ltr");
  });

  it("asks for the right keyboard without the caller remembering to", () => {
    render(<Field id="amount" name="amount" label="Amount" type="currency" />);
    expect(screen.getByLabelText("Amount")).toHaveAttribute("inputmode", "decimal");
  });
});

describe("Banner — the component Alert became", () => {
  // **`Alert` is gone and these moved with it.** §29 specifies Banner, and the directive of
  // 2026-11-20 forbids an ad-hoc component that duplicates an approved one -- so the shim
  // that would have kept the old name was not written. The four assertions below are the
  // ones worth carrying: the role mapping, the severity mark surviving the border shorthand,
  // and the absence of a fill.
  it("announces a critical condition without moving focus", () => {
    render(<Banner severity="critical">Those details were not accepted.</Banner>);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Those details were not accepted.");
    expect(document.activeElement).toBe(document.body);
  });

  it("uses status rather than alert for information", () => {
    render(<Banner severity="info">This session holds no permissions yet.</Banner>);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("keeps the severity mark after the border shorthand", () => {
    // Inline style keys apply in insertion order, so a `border` shorthand written after
    // `borderInlineStart` silently resets it -- which is how the one thing distinguishing an
    // error from a notice disappeared from the rendered page while the token stayed correct.
    const { container } = render(<Banner severity="critical">Refused.</Banner>);
    const box = container.firstElementChild as HTMLElement;
    expect(box.style.borderInlineStart).toContain("3px");
    expect(box.style.borderInlineStart).toContain("--color-semantic-error");
  });

  it("carries no fill, because the severity scale says the thing once", () => {
    const { container } = render(<Banner severity="critical">Refused.</Banner>);
    const box = container.firstElementChild as HTMLElement;
    expect(box.style.background).toContain("--color-surface-default");
  });
});
