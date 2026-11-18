import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Alert, Button, Field } from "@/components/controls";

/**
 * The shared controls, tested for the properties the design system makes structural.
 *
 * These are the assertions a browser cannot make cheaply -- an attribute on one element, a
 * handler that does or does not fire -- while the Playwright suite covers what only a browser
 * can: computed colour, mirrored layout, real focus. Neither replaces the other, and the split
 * is deliberate rather than historical.
 */

describe("Button", () => {
  it("is disabled and announced while busy", async () => {
    const onClick = vi.fn();
    render(
      <Button busy busyLabel="Signing in…" onClick={onClick}>
        Sign in
      </Button>,
    );
    const button = screen.getByRole("button");
    expect(button).toBeDisabled();
    // `aria-busy` rather than only a visual change: without it a screen-reader user gets no
    // signal that the form is in flight, and presses again.
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button).toHaveTextContent("Signing in…");

    await userEvent.click(button, { pointerEventsCheck: 0 });
    expect(onClick).not.toHaveBeenCalled();
  });

  it("keeps its label when it is merely disabled", () => {
    render(
      <Button disabled busyLabel="Signing in…">
        Sign in
      </Button>,
    );
    expect(screen.getByRole("button")).toHaveTextContent("Sign in");
    expect(screen.getByRole("button")).not.toHaveAttribute("aria-busy");
  });

  it("sets no outline of its own, because the focus ring is system-owned", () => {
    // Guardrail G4 makes the ring non-configurable so "a tenant cannot ship an unnavigable
    // product". A component that set its own would be a component that can remove it.
    render(<Button>Save</Button>);
    expect(screen.getByRole("button").style.outline).toBe("");
  });
});

describe("Field", () => {
  it("uses a real label rather than a placeholder", () => {
    render(<Field id="email" label="Email or phone" />);
    const input = screen.getByLabelText("Email or phone");
    expect(input).toBeInstanceOf(HTMLInputElement);
    // A placeholder disappears on focus, fails at small sizes and is not a name to a screen
    // reader, so there is no placeholder-as-label path in this component at all.
    expect(input).not.toHaveAttribute("placeholder");
  });

  it("associates the hint and the error with the input, in that order", () => {
    render(<Field id="tenant" label="Tenant ID" hint="The tenant." error="Required." />);
    const input = screen.getByLabelText("Tenant ID");
    const described = (input.getAttribute("aria-describedby") ?? "").split(" ");
    expect(described).toEqual(["tenant-hint", "tenant-error"]);
    expect(document.getElementById("tenant-hint")).toHaveTextContent("The tenant.");
    expect(document.getElementById("tenant-error")).toHaveTextContent("Required.");
    expect(input).toHaveAttribute("aria-invalid", "true");
  });

  it("is not marked invalid when it has no error", () => {
    render(<Field id="tenant" label="Tenant ID" hint="The tenant." />);
    const input = screen.getByLabelText("Tenant ID");
    expect(input).not.toHaveAttribute("aria-invalid");
    expect(input.getAttribute("aria-describedby")).toBe("tenant-hint");
  });
});

describe("Alert", () => {
  it("announces an error without moving focus", () => {
    render(<Alert tone="error">Those details were not accepted.</Alert>);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Those details were not accepted.");
    expect(document.activeElement).toBe(document.body);
  });

  it("uses status rather than alert for information", () => {
    render(<Alert tone="info">This session holds no permissions yet.</Alert>);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("keeps the severity mark after the border shorthand", () => {
    // Inline style keys apply in insertion order, so a `border` shorthand written after
    // `borderInlineStart` silently resets it -- which is how the one thing distinguishing an
    // error from a notice disappeared from the rendered page while the token stayed correct.
    const { container } = render(<Alert tone="error">Refused.</Alert>);
    const box = container.firstElementChild as HTMLElement;
    expect(box.style.borderInlineStart).toContain("3px");
    expect(box.style.borderInlineStart).toContain("--color-semantic-error");
  });

  it("carries no fill, because the severity scale says the thing once", () => {
    const { container } = render(<Alert tone="error">Refused.</Alert>);
    const box = container.firstElementChild as HTMLElement;
    expect(box.style.background).toContain("--color-surface-default");
  });
});
