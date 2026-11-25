/**
 * ADM-STF-03 · INVITE, rendered. ADR-0017.
 *
 * **The canvas is three fields, a sentence, a button and a pending list**, and the first
 * assertion here is about a field that must *not* be among them: a `display_name` was in the
 * first draft of this form and of `iam.invitations` until the canvas was read against it. The
 * canvas collects an address, a role and the clubs, and its pending list draws
 * `yasmin@nadi.jo` rather than a person -- so a name field would be one this app invented,
 * and a copy of somebody's name stored in the plane whose own authentication log deliberately
 * records none. Nothing structural would notice it coming back, which is why the pin is here
 * and in CHECK 116c.
 *
 * The browser spec drives the real routes; this layer is the one that renders a tree, so it
 * is where the states a reader is actually given live.
 */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  clubNames, missingFields, pendingCount, roleReach, stateKey,
  type Invitation,
} from "@/lib/invitations";

import { InviteForm } from "@/app/staff/invite/invite-form";

const CLUBS = [
  { location_id: "loc-1", location_name: "Khalda" },
  { location_id: "loc-2", location_name: "Sweifieh" },
];

const CATALOG = [
  { name: "people.person.read", action_class: "data_access" },
  { name: "membership.agreement.write", action_class: "financial" },
  { name: "finance.payment.take", action_class: "financial" },
  { name: "authz.break_glass", action_class: "privileged" },
];

const SALES = {
  role_key: "sales",
  display_name: "Sales",
  description: "Can see leads and members, sell memberships, and take payments.",
  permissions: ["people.person.read", "membership.agreement.write"],
};

const READER = {
  role_key: "reader",
  display_name: "Reader",
  description: null,
  permissions: ["people.person.read"],
};

function form(roles = [SALES, READER]) {
  return render(
    <InviteForm
      roles={roles} clubs={CLUBS} catalog={CATALOG} locale="en" numbering="latn" />,
  );
}

function invitation(over: Partial<Invitation> = {}): Invitation {
  return {
    invitation_id: "inv-1",
    email: "yasmin@nadi.jo",
    role_key: "sales",
    role_name: "Sales",
    expires_at: "2026-12-03T10:00:00+00:00",
    created_at: "2026-11-26T10:00:00+00:00",
    created_by: "id-1",
    state: "pending",
    days_left: 2,
    accepted_at: null,
    revoked_at: null,
    revoke_reason: null,
    supersedes_invitation_id: null,
    scopes: [
      { scope_type: "location", brand_id: null, location_id: "loc-1" },
      { scope_type: "location", brand_id: null, location_id: "loc-2" },
    ],
    ...over,
  };
}

describe("the invite form draws the canvas's fields and no others", () => {
  it("asks for an address, a role and where they work", () => {
    form();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Role")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Where they work" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Clubs" })).toBeInTheDocument();
  });

  it("asks for no name, because the invitation carries none", () => {
    const { container } = form();
    // By name, not by label: a field called `display_name` is the defect whatever its label
    // reads, and this is the assertion that would have caught it being added back.
    expect(container.querySelector('[name="display_name"]')).toBeNull();
    expect(screen.queryByLabelText("Name")).toBeNull();
    // Exactly the canvas's two typed fields plus the role select: a reader types an address
    // and chooses, and nothing else.
    expect(screen.getAllByRole("textbox")).toHaveLength(1);
    expect(screen.getAllByRole("combobox")).toHaveLength(1);
  });

  it("offers every role the tenant has, and none chosen to begin with", () => {
    form();
    const select = screen.getByLabelText("Role") as HTMLSelectElement;
    expect(select.value).toBe("");
    expect(within(select).getAllByRole("option").map((one) => one.textContent))
      .toEqual(["Choose a role", "Sales", "Reader"]);
  });

  it("states the expiry whatever role is chosen, and waits for one before the rest", () => {
    form();
    expect(screen.getByText("The link expires in 7 days.")).toBeInTheDocument();
    expect(
      screen.getByText("Choose a role and what it grants is shown here."),
    ).toBeInTheDocument();
  });
});

describe("the sentence under the form is the facts it is made of", () => {
  it("counts the financial permissions rather than asserting there are none", () => {
    const reach = roleReach(SALES, CATALOG);
    expect(reach.description).toBe(SALES.description);
    expect(reach.permissions).toBe(2);
    expect(reach.financial).toBe(1);
  });

  it("counts a privileged permission as financial, because both need a step-up", () => {
    expect(roleReach(
      { description: null, permissions: ["authz.break_glass"] }, CATALOG).financial,
    ).toBe(1);
  });

  it("says no financial administration only when that is true of the role", () => {
    expect(roleReach(READER, CATALOG).financial).toBe(0);
  });

  it("answers about nothing when no role is chosen", () => {
    expect(roleReach(null, CATALOG)).toEqual(
      { description: null, permissions: 0, financial: 0 });
  });

  it("falls back to a count where a tenant has written no description", () => {
    expect(roleReach(READER, CATALOG).description).toBeNull();
    expect(roleReach(READER, CATALOG).permissions).toBe(1);
  });
});

describe("what the form refuses to send", () => {
  it("needs an address that looks like one", () => {
    expect(missingFields("", "sales", ["loc-1"], false).email).toBe(true);
    expect(missingFields("kareem", "sales", ["loc-1"], false).email).toBe(true);
    expect(missingFields("kareem@nadi", "sales", ["loc-1"], false).email).toBe(true);
    expect(missingFields("kareem@nadi.jo", "sales", ["loc-1"], false).email)
      .toBeUndefined();
  });

  it("needs a role", () => {
    expect(missingFields("kareem@nadi.jo", "", ["loc-1"], false).role).toBe(true);
  });

  it("needs a club, because a role held at none grants nothing", () => {
    expect(missingFields("kareem@nadi.jo", "sales", [], false).clubs).toBe(true);
  });

  it("needs no club when the grant is tenant-wide", () => {
    expect(missingFields("kareem@nadi.jo", "sales", [], true)).toEqual({});
  });
});

describe("the pending list is the canvas's own", () => {
  it("counts the waiting ones and keeps the expired ones on screen", () => {
    const rows = [
      invitation(),
      invitation({ invitation_id: "inv-2", email: "omar.s@nadi.jo", state: "expired",
        days_left: 0 }),
    ];
    expect(pendingCount(rows)).toBe(1);
    expect(rows).toHaveLength(2);
  });

  it("reads each state as a word rather than a stored flag", () => {
    expect(stateKey(invitation())).toBe("invite.statePending");
    expect(stateKey(invitation({ state: "expired" }))).toBe("invite.stateExpired");
    expect(stateKey(invitation({ state: "accepted" }))).toBe("invite.stateAccepted");
    expect(stateKey(invitation({ state: "revoked" }))).toBe("invite.stateRevoked");
  });

  it("names the clubs an invitation is for", () => {
    expect(clubNames(invitation().scopes, CLUBS))
      .toEqual({ tenantWide: false, names: ["Khalda", "Sweifieh"] });
  });

  it("says tenant-wide rather than listing every club", () => {
    expect(clubNames(
      [{ scope_type: "tenant", brand_id: null, location_id: null }], CLUBS))
      .toEqual({ tenantWide: true, names: [] });
  });

  it("falls back to the id where a club is not in the picker's own list", () => {
    expect(clubNames(
      [{ scope_type: "location", brand_id: null, location_id: "loc-9" }], CLUBS).names)
      .toEqual(["loc-9"]);
  });
});
