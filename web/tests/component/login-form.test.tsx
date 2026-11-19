import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/app/login/login-form";
import { SIGN_IN_IDLE, type SignInState } from "@/app/login/state";

/**
 * The sign-in form's four states, rendered.
 *
 * **The challenge state is here rather than in the browser suite, and the reason is the
 * product working.** MOD-007 challenges a login from a device it has not seen and then
 * *confirms* that device, so a browser is challenged exactly once per fixture -- which means
 * an end-to-end test of the challenge path passes or fails depending on whether some earlier
 * test in the run happened to burn it. A mutation sweep showed that precisely: deleting the
 * recovery field entirely left the E2E suite green, because by then the device was trusted.
 *
 * A component test has no such ordering. It renders the state the server returns and asserts
 * what the reader is given, which is the half that must never regress: a form that says a
 * recovery code is needed and offers nowhere to type one is the defect this field was added
 * for, and it is the same dead end MOD-007's own review records one layer down.
 */

vi.mock("react-dom", async () => {
  const actual = await vi.importActual<typeof import("react-dom")>("react-dom");
  // `useFormStatus` reads from a form React has taken over; outside a server-action render
  // there is none, so it is stubbed to the state the form starts in.
  return { ...actual, useFormStatus: () => ({ pending: false }) };
});

vi.mock("react", async () => {
  const actual = await vi.importActual<typeof import("react")>("react");
  return {
    ...actual,
    // `useActionState` needs a server action; the test supplies the state directly, which is
    // what lets each of the four states be rendered on demand.
    useActionState: (_action: unknown, initial: SignInState) => [
      (globalThis as { __signInState?: SignInState }).__signInState ?? initial,
      () => {},
      false,
    ],
  };
});

function renderWith(state: SignInState) {
  (globalThis as { __signInState?: SignInState }).__signInState = state;
  return render(<LoginForm locale="en" />);
}

describe("the sign-in form", () => {
  it("asks for a password when there is no challenge", () => {
    renderWith(SIGN_IN_IDLE);
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.queryByLabelText("Recovery code")).toBeNull();
  });

  it("offers somewhere to answer a challenge, and stops asking for the password", () => {
    renderWith({
      ...SIGN_IN_IDLE,
      error: "login.challenge",
      challenge: "a-one-use-nonce",
    });
    const recovery = screen.getByLabelText("Recovery code");
    expect(recovery).toBeInTheDocument();
    // **The password field goes away.** MOD-007 has already taken it; asking again after a
    // security prompt is the habit a phishing page relies on.
    expect(screen.queryByLabelText("Password")).toBeNull();
    // The nonce rides in a hidden field, so the second act knows which challenge it answers.
    expect(document.querySelector('input[name="challenge"]')).toHaveValue("a-one-use-nonce");
    expect(screen.getByRole("button", { name: "Continue" })).toBeInTheDocument();
  });

  it("renders a challenge as information, not as an error", () => {
    renderWith({ ...SIGN_IN_IDLE, error: "login.challenge", challenge: "nonce" });
    // A sign-in that can still succeed is not a refusal, and `role="alert"` would interrupt
    // a screen-reader user with one.
    expect(screen.getByRole("status")).toHaveTextContent("needs a recovery code");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("renders a refusal as an error that is announced", () => {
    renderWith({ ...SIGN_IN_IDLE, error: "login.failed" });
    expect(screen.getByRole("alert")).toHaveTextContent("were not accepted");
  });

  it("names every empty field and keeps the tenant and identifier", () => {
    renderWith({
      ...SIGN_IN_IDLE,
      missing: { tenant: false, identifier: false, password: true, recovery: false },
      tenantId: "11111111-1111-4111-8111-111111111111",
      identifier: "jane@example.test",
    });
    expect(screen.getByLabelText("Tenant ID")).toHaveValue(
      "11111111-1111-4111-8111-111111111111",
    );
    expect(screen.getByLabelText("Email or phone")).toHaveValue("jane@example.test");
    expect(screen.getByLabelText("Password")).toHaveAttribute("aria-invalid", "true");
    // And the password itself is never echoed back.
    expect(screen.getByLabelText("Password")).toHaveValue("");
  });
});
