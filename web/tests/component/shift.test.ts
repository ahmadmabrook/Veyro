import { describe, expect, it } from "vitest";

import {
  accountsFor, actFor, countOwes, handoverCase, mayPress, nameOf, type Drawer,
} from "@/lib/shift";

/**
 * FD-07's three acts and four handover sentences.
 *
 * **A builder that refuses a state the server cannot produce**, which is the lesson
 * ADM-MSH-07 paid for: its `commitmentLine` reached a branch with a hand-written quote the
 * lifecycle cannot emit, so the branch passed its assertion and was dead in the product. Here
 * the server's own invariant is that an open session and a standing balance of zero can
 * coexist (a drawer funded with nothing) while a `handed_over` naming a figure implies that
 * shift closed -- so `drawer` throws on the combinations `GET /ledger/drawers` cannot answer
 * with, and one test proves it throws.
 */

function drawer(over: Partial<Drawer> = {}): Drawer {
  const one: Drawer = {
    cash_account_id: "acct-1",
    drawer_label: "front",
    currency: "JOD",
    expected_minor: 0,
    open_session: null,
    handed_over: null,
    ...over,
  };
  // A handover record whose own close is half-recorded is refused by the schema's
  // all-or-none close attribution, so a fixture carrying one would be testing a row the
  // database cannot hold.
  const left = one.handed_over;
  if (left !== null) {
    const parts = [left.counted_minor, left.closed_at, left.closed_by];
    const set = parts.filter((part) => part !== null).length;
    if (set !== 0 && set !== parts.length) {
      throw new Error(
        "led_cash_sessions_close_attributed: a close records both figures, its actor and "
        + "its correlation, or none of them");
    }
  }
  return one;
}

function handedOver(over: Partial<Drawer["handed_over"] & object> = {}) {
  return {
    session_id: "sess-0",
    counted_minor: 7000,
    closed_at: "2026-11-24T13:04:00+00:00",
    closed_by: "identity-1",
    handover_note: null,
    drawer_label: "front",
    location_id: "loc-1",
    ...over,
  };
}

describe("which act a drawer is waiting for", () => {
  it("is a close when a shift is open, whatever the balance says", () => {
    expect(actFor(drawer({
      expected_minor: 5000,
      open_session: {
        session_id: "s-1", opened_at: "2026-11-24T13:00:00+00:00",
        opened_by: "identity-1", opening_float_minor: 5000,
      },
    }))).toBe("close");
  });

  it("is a handover when the drawer still holds money", () => {
    expect(actFor(drawer({ expected_minor: 5000 }))).toBe("handover");
  });

  it("is a funding when the drawer holds nothing", () => {
    // **The distinction the whole slice is about.** An empty drawer has to be funded from
    // the safe; a drawer that already holds money is handed over and nothing is drawn, which
    // is what stops the float being posted twice.
    expect(actFor(drawer({ expected_minor: 0 }))).toBe("fund");
  });

  it("is a handover for a drawer that has gone negative", () => {
    // Fail-toward-surfacing: a negative balance means something is already wrong, and a
    // handover shows it as a difference rather than funding over it.
    expect(actFor(drawer({ expected_minor: -500 }))).toBe("handover");
  });
});

describe("what the handover panel says", () => {
  it("names who left what, when, which is the canvas's own line", () => {
    const left = handoverCase(drawer({
      expected_minor: 5000, handed_over: handedOver(),
    }));
    expect(left).toEqual({
      kind: "left", counted: 5000, at: "2026-11-24T13:04:00+00:00", by: "identity-1",
    });
  });

  it("quotes the drawer's balance rather than the last count", () => {
    // **They differ whenever the takings were not all banked**, and what the next person is
    // counting is the money that is there -- which is also what the command compares
    // against. A screen showing the closing count would show a figure the button is not
    // measured by, which is the two-definitions shape this build keeps finding.
    const left = handoverCase(drawer({
      expected_minor: 5000, handed_over: handedOver({ counted_minor: 7000 }),
    }));
    expect(left.kind === "left" && left.counted).toBe(5000);
  });

  it("says the drawer was emptied when the last shift banked everything", () => {
    expect(handoverCase(drawer({
      expected_minor: 0, handed_over: handedOver(),
    }))).toEqual({ kind: "emptied" });
  });

  it("says nobody accounts for the money when a journal put it there", () => {
    // Reachable with no adversary: a journal posted straight to a till account leaves a
    // balance with no shift behind it.
    expect(handoverCase(drawer({ expected_minor: 3000 })))
      .toEqual({ kind: "unattributed", standing: 3000 });
  });

  it("says nothing has been counted here yet for a drawer with no history", () => {
    expect(handoverCase(drawer({ expected_minor: 0 }))).toEqual({ kind: "first" });
  });

  it("refuses a half-recorded close rather than drawing one", () => {
    // The schema's close attribution is all-or-none, so this combination is a row the
    // database cannot hold -- and a fixture carrying one would prove a branch nothing
    // reaches.
    expect(() => drawer({
      expected_minor: 5000,
      handed_over: handedOver({ closed_by: null }),
    })).toThrow(/close_attributed/);
  });
});

describe("what a count still owes", () => {
  const over = drawer({ expected_minor: 5000, handed_over: handedOver() });

  it("owes nothing before anything is typed", () => {
    expect(countOwes(over, null))
      .toEqual({ gap: null, needsReason: false, needsPosting: false });
  });

  it("owes nothing when the count agrees", () => {
    expect(countOwes(over, 5000))
      .toEqual({ gap: 0, needsReason: false, needsPosting: false });
  });

  it("owes a reason and a posting when the count is short", () => {
    expect(countOwes(over, 4500))
      .toEqual({ gap: -500, needsReason: true, needsPosting: true });
  });

  it("owes them when the count is over, which a one-sided rule would miss", () => {
    expect(countOwes(over, 5500))
      .toEqual({ gap: 500, needsReason: true, needsPosting: true });
  });

  it("owes a posting and no reason when a float is being drawn", () => {
    // **Funding an empty drawer is not a comparison.** The money is being put in, so what
    // the posting needs is the account it comes from rather than an explanation -- and
    // demanding a reason here is exactly what the first draft of the migration's constraint
    // did, which refused every ordinary first open.
    expect(countOwes(drawer({ expected_minor: 0 }), 5000))
      .toEqual({ gap: null, needsReason: false, needsPosting: true });
  });

  it("owes nothing for a float of nothing", () => {
    expect(countOwes(drawer({ expected_minor: 0 }), 0))
      .toEqual({ gap: null, needsReason: false, needsPosting: false });
  });
});

describe("whether the press can be made", () => {
  const over = drawer({ expected_minor: 5000, handed_over: handedOver() });

  it("can be when the count agrees and nothing is owed", () => {
    expect(mayPress(countOwes(over, 5000), { reason: "", hasPosting: false })).toBe(true);
  });

  it("cannot be when a short count has no reason", () => {
    expect(mayPress(countOwes(over, 4500), { reason: "", hasPosting: true })).toBe(false);
    expect(mayPress(countOwes(over, 4500), { reason: "  ", hasPosting: true })).toBe(false);
  });

  it("cannot be when the posting has nowhere to go", () => {
    // Two refusals with different remedies: a missing reason is the person's to type and a
    // chart this session may not read is not, which is why they are separate facts.
    expect(mayPress(countOwes(over, 4500), { reason: "a reason", hasPosting: false }))
      .toBe(false);
  });

  it("can be when a short count has both", () => {
    expect(mayPress(countOwes(over, 4500), { reason: "a reason", hasPosting: true }))
      .toBe(true);
  });
});


describe("which account each posting field carries", () => {
  const chart = { safe: "safe-1", suspense: "suspense-1" };

  it("draws from the safe only when the drawer is being funded", () => {
    expect(accountsFor("fund", chart))
      .toEqual({ floatSource: "safe-1", suspense: "" });
  });

  it("sends no account to draw from on a handover", () => {
    // **The command refuses the field here rather than ignoring it**, so a form that sent it
    // would make the ordinary handover unpressable -- which is the defect this slice closes,
    // arriving from the surface. A hidden field no test presses is a decision nothing sees,
    // which is why it lives in the library.
    expect(accountsFor("handover", chart))
      .toEqual({ floatSource: "", suspense: "suspense-1" });
  });

  it("sends no suspense account when a float is being drawn", () => {
    // A funded open has no difference to post, so suspense would be a field validated and
    // thrown away -- MOD-012's `release_run` shape in a request body.
    expect(accountsFor("fund", chart).suspense).toBe("");
  });

  it("sends the suspense account on a close, where a variance posts", () => {
    expect(accountsFor("close", chart))
      .toEqual({ floatSource: "", suspense: "suspense-1" });
  });
});


describe("whose name goes on an actor", () => {
  const links = [{ identity_id: "id-1", person_id: "p-1" }];

  it("is the person's name when it can be read", () => {
    expect(nameOf("id-1", links, new Map([["p-1", { legal_name: "Kareem Haddad" }]])))
      .toBe("Kareem Haddad");
  });

  it("is nobody for an identity with no person", () => {
    // **The ordinary staff case.** Staff hold permissions and do not have to be anybody in
    // particular, so the surface says "a staff member" rather than drawing a blank.
    expect(nameOf("id-2", links, new Map([["p-1", { legal_name: "Kareem" }]]))).toBeNull();
  });

  it("is nobody for a name this session may not read", () => {
    // **A withheld value is a marker, not a name.** Rendering it would put three asterisks
    // where a person belongs -- MOD-027's board paid for exactly that, and this branch is
    // unreachable from the browser suite because the fixture's drawer actors are linked to
    // no person at all.
    expect(nameOf("id-1", links, new Map([["p-1", { legal_name: "***" }]]))).toBeNull();
  });

  it("is nobody for a person with no recorded name", () => {
    expect(nameOf("id-1", links, new Map([["p-1", { legal_name: null }]]))).toBeNull();
  });
});
