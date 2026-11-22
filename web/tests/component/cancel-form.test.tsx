import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CancelForm } from "@/app/people/[personId]/cancel-form";
import { IDLE, type CancelState } from "@/app/people/[personId]/cancel-state";

/**
 * ADM-MSH-07's form, rendered.
 *
 * **Three of these assert claims this screen's own comments make**, which is the point: a
 * docstring is not an assertion, and this repository has shipped a module docstring claiming
 * a posting the module never made. The claims are that the fee and the version travel as
 * hidden fields (without which the disclosure check is decoration and the write is
 * unguarded), that "Keep it" is a link rather than a second submit, and that the
 * confirmation states what was *recorded* rather than echoing the form.
 *
 * The success and failure states are here rather than in the browser suite for the login
 * form's reason, and a sharper one: a cancellation is one-way, so a browser test can take
 * each state exactly once per fixture and the state after it is unreachable for the rest of
 * the run.
 */

vi.mock("react-dom", async () => {
  const actual = await vi.importActual<typeof import("react-dom")>("react-dom");
  return { ...actual, useFormStatus: () => ({ pending: false }) };
});

vi.mock("react", async () => {
  const actual = await vi.importActual<typeof import("react")>("react");
  return {
    ...actual,
    useActionState: (_action: unknown, initial: CancelState) => [
      (globalThis as { __cancelState?: CancelState }).__cancelState ?? initial,
      () => {},
      false,
    ],
  };
});

const state = (over: Partial<CancelState> = {}) => {
  (globalThis as { __cancelState?: CancelState }).__cancelState = { ...IDLE, ...over };
};

const form = () => render(
  <CancelForm
    locale="en"
    personId="p-1"
    membershipId="m-1"
    feeMinor={12_000}
    currency="JOD"
    version={7}
    feeText="JOD 120.000"
    backHref="/people/p-1?tab=membership"
  />,
);

const hidden = (container: HTMLElement, name: string) =>
  container.querySelector<HTMLInputElement>(`input[type="hidden"][name="${name}"]`);

describe("ADM-MSH-07's form", () => {
  it("sends the fee it displayed and the version it read", () => {
    // **The disclosure check is only a control if the figure travels.** `cancel_membership`
    // compares what arrives against what it recomputes and refuses a mismatch, and a form
    // sending no fee is allowed -- the module permits a staff cancellation that discloses
    // nothing -- so an absent field would quietly turn this screen into one of those.
    state();
    const { container } = form();
    expect(hidden(container, "fee_minor")?.value).toBe("12000");
    expect(hidden(container, "version")?.value).toBe("7");
    expect(hidden(container, "currency")?.value).toBe("JOD");
    expect(hidden(container, "membership_id")?.value).toBe("m-1");
  });

  it("names the figure on the button, where the canvas puts the money", () => {
    state();
    form();
    expect(screen.getByRole("button", { name: /JOD 120\.000/ })).toBeTruthy();
  });

  it("offers the way out as a link and not a second submit", () => {
    // A `<button>` that did nothing, or a second submit, is how a destructive form gets
    // confirmed by somebody reaching for the exit.
    state();
    form();
    const keep = screen.getByRole("link", { name: "Keep it" });
    expect(keep.getAttribute("href")).toBe("/people/p-1?tab=membership");
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("asks for a reason and says so when one is missing", () => {
    state({ missing: { reason: true } });
    form();
    expect(screen.getByText("A cancellation states why.")).toBeTruthy();
  });

  it("states what was recorded rather than echoing the form", () => {
    // **The command returns the date it actually applied.** Echoing the request back is the
    // shape MOD-017's own repeat path was fixed for: a caller told its figure was accepted
    // when the recorded one was something else.
    state({
      message: "done",
      recorded: { accessEndsOn: "2026-09-07", feeMinor: 12_000, currency: "JOD" },
    });
    form();
    expect(screen.getByText("Cancelled. Access ends on 2026-09-07.")).toBeTruthy();
    // And the form is gone, so a second submit is not on screen after the one-way act.
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("renders a conflict as reload rather than as a refusal", () => {
    state({ error: "cancel.conflict" });
    form();
    expect(screen.getByText(/reload and look again/)).toBeTruthy();
  });
});
