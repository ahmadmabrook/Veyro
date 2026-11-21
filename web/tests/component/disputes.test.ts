import { describe, expect, it } from "vitest";

import { MESSAGES } from "@/i18n/locale";
import {
  evidenceFrom,
  kindName,
  reasonName,
  statusName,
  undecided,
  urgency,
  type AttendanceWindow,
  type Dispute,
} from "@/lib/disputes";

/**
 * ADM-PAY-10's judgements, tested where they are made.
 *
 * **The three evidence states are the reason this is a function rather than inline JSX.**
 * A fixture renders one case, so two of the three would otherwise be reachable only by
 * signing in as somebody the fixture does not have — the surface-branch vacuity this
 * repository has shipped four times. The one that matters most is `refused`: rendering a
 * permission refusal as ☐ tells an accountant the gym cannot prove attendance it can prove,
 * which is the worst sentence this screen could say.
 */

function dispute(over: Partial<Dispute> = {}): Dispute {
  return {
    dispute_id: "d1",
    payment_id: "p1",
    provider_case_ref: "ACME-CASE-40118",
    dispute_kind: "chargeback",
    reason_code: "product_not_received",
    amount_minor: 7800,
    currency: "JOD",
    opened_on: "2026-06-02",
    respond_due_on: "2026-08-26",
    status: "open",
    response_ref: null,
    responded_at: null,
    outcome: null,
    closed_at: null,
    payer_person_id: "per1",
    paid_at: "2026-06-02T09:00:00+00:00",
    method: "card",
    invoice_id: "i1",
    document_number: "INV-19102",
    fiscal_status: "accepted",
    fiscal_ack_ref: "JF-88213",
    membership_id: "m1",
    billed_on: "2026-05-01",
    days_remaining: 7,
    window_has_closed: false,
    days_given: 85,
    ...over,
  };
}

function window(entries: number): AttendanceWindow {
  return {
    person_id: "per1", since: "2026-05-01", until: "2026-06-02",
    entries, days_attended: entries, days: [],
    entries_not_decisions: "", each_day_is_local_to_its_door: "",
  };
}

const held = {
  mayAttendance: true, attendance: window(11),
  mayMembership: true, membershipRead: true,
  signedAt: "2026-03-01T10:00:00+00:00", signatureKind: "click_through",
};

const by = (lines: ReturnType<typeof evidenceFrom>, key: string) =>
  lines.find((l) => l.key === key)!;

describe("the evidence a dispute is answered with", () => {
  it("is the canvas's four lines, in the canvas's order", () => {
    const lines = evidenceFrom(dispute(), held);
    expect(lines.map((l) => l.key))
      .toEqual(["attendance", "contract", "invoice", "statement"]);
  });

  it("ticks the three Veyro can assemble and leaves the statement to the operator", () => {
    const lines = evidenceFrom(dispute(), held);
    expect(by(lines, "attendance").state).toBe("have");
    expect(by(lines, "attendance").detail).toContain("11");
    expect(by(lines, "contract").state).toBe("have");
    expect(by(lines, "invoice").detail).toContain("INV-19102");
    expect(by(lines, "invoice").detail).toContain("JF-88213");
    // "☐ Written statement · you add this" — and it stays unticked whatever the reads say,
    // because nothing in this build holds one.
    expect(by(lines, "statement").state).toBe("missing");
    expect(by(lines, "statement").note).toBe("dispute.ev.statementIsYours");
  });

  it("tells a refusal from an absence, which the canvas has no mark for", () => {
    // **The important one.** A reader without `access.decision.read` must not be told the
    // gym has no check-in record: it may well have one, and this is the line the whole
    // case rests on.
    const lines = evidenceFrom(dispute(), { ...held, mayAttendance: false, attendance: null });
    expect(by(lines, "attendance").state).toBe("refused");
    expect(by(lines, "attendance").note).toBe("dispute.ev.attendanceRefused");
    const contract = evidenceFrom(
      dispute(), { ...held, mayMembership: false, membershipRead: false });
    expect(by(contract, "contract").state).toBe("refused");
  });

  it("says a member really did not come, which is different again", () => {
    const lines = evidenceFrom(dispute(), { ...held, attendance: window(0) });
    expect(by(lines, "attendance").state).toBe("missing");
    // And it carries no excuse note: this one *is* about the gym's case.
    expect(by(lines, "attendance").note).toBeUndefined();
  });

  it("says when there is no period to count over at all", () => {
    // A payment with no invoice behind it has no billed period, which is a different
    // answer from the member not having come — and rendering it as "0 check-ins" would be
    // the gym's own evidence read as a fact against it.
    const lines = evidenceFrom(dispute({ billed_on: null }), held);
    expect(by(lines, "attendance").state).toBe("missing");
    expect(by(lines, "attendance").note).toBe("dispute.ev.noPeriod");
  });

  it("marks an agreement that exists and was never signed", () => {
    // The one piece of this a scheme would ask about, so it is marked rather than omitted.
    const lines = evidenceFrom(dispute(), { ...held, signedAt: null });
    expect(by(lines, "contract").state).toBe("missing");
    expect(by(lines, "contract").note).toBe("dispute.ev.unsigned");
  });

  it("says when the invoice cites no membership", () => {
    const lines = evidenceFrom(dispute({ membership_id: null }), held);
    expect(by(lines, "contract").state).toBe("missing");
    expect(by(lines, "contract").note).toBe("dispute.ev.noMembership");
  });

  it("does not tick a rejected fiscal filing as though it were a reference", () => {
    // **The canvas's line is "Invoice and JoFotara reference"**, and the two halves are
    // different evidence: the document is the gym's own record and the acknowledgement is
    // a tax authority confirming it was filed. Ticking both when only the first is held
    // puts an accountant in front of a scheme expecting a reference that does not exist.
    // Found by looking at a fixture whose filing had been rejected.
    const rejected = evidenceFrom(
      dispute({ fiscal_ack_ref: null, fiscal_status: "rejected" }), held);
    expect(by(rejected, "invoice").state).toBe("have");
    expect(by(rejected, "invoice").detail).toBe("INV-19102");
    expect(by(rejected, "invoice").note).toBe("dispute.ev.filingRejected");
    // Unfiled is a different sentence from rejected: one has not happened yet.
    const pending = evidenceFrom(
      dispute({ fiscal_ack_ref: null, fiscal_status: "pending" }), held);
    expect(by(pending, "invoice").note).toBe("dispute.ev.notFiled");
    // And an acknowledged one cites both, with no note at all.
    expect(by(evidenceFrom(dispute(), held), "invoice").note).toBeUndefined();
  });
});

describe("how urgent the deadline is", () => {
  it("is three states, not a gradient, because the actions differ", () => {
    expect(urgency(dispute({ days_remaining: 7 }))).toBe("pressing");
    expect(urgency(dispute({ days_remaining: 30 }))).toBe("noted");
    expect(urgency(dispute({ days_remaining: -3, window_has_closed: true })))
      .toBe("closed");
  });

  it("does not colour on a fraction of the window given", () => {
    // `days_given` is carried so a reader knows that "three days left" means something
    // different out of thirty than out of four — and a surface colouring on the fraction
    // would call a four-day scheme window comfortable on its second day.
    expect(urgency(dispute({ days_remaining: 2, days_given: 4 }))).toBe("pressing");
  });
});

describe("what counts as exposure", () => {
  it("is the undecided ones, because a decided dispute is settled money", () => {
    expect(undecided(dispute({ status: "open" }))).toBe(true);
    expect(undecided(dispute({ status: "responded" }))).toBe(true);
    for (const settled of ["won", "lost", "withdrawn"]) {
      expect(undecided(dispute({ status: settled }))).toBe(false);
    }
  });
});

describe("the catalogue, from the side the parity check cannot see", () => {
  const statuses = ["open", "responded", "won", "lost", "withdrawn"];
  const kinds = ["chargeback", "retrieval", "pre_arbitration"];
  const reasons = [
    "product_not_received", "product_unacceptable", "fraudulent", "duplicate",
    "subscription_canceled", "credit_not_processed", "unrecognized",
  ];
  const mapped = [
    ...statuses.map(statusName), ...kinds.map(kindName), ...reasons.map(reasonName),
    ...evidenceFrom(dispute(), held).flatMap((l) => [l.label, l.note]),
    ...evidenceFrom(dispute({ billed_on: null, membership_id: null,
      document_number: null }), { ...held, mayAttendance: false, attendance: null })
      .flatMap((l) => [l.label, l.note]),
  ].filter((k): k is NonNullable<typeof k> => k !== null && k !== undefined);

  it("maps every declared value rather than leaking it to the page", () => {
    expect([...statuses.map(statusName), ...kinds.map(kindName),
      ...reasons.map(reasonName)].filter((k) => k === null)).toEqual([]);
  });

  it("has every key it maps to in both locales", () => {
    for (const key of mapped) {
      expect(MESSAGES.en, `en is missing ${key}`).toHaveProperty(key);
      expect(MESSAGES.ar, `ar is missing ${key}`).toHaveProperty(key);
    }
    // And the three state labels, which are visually-hidden text rather than a mark.
    for (const state of ["have", "missing", "refused"]) {
      expect(MESSAGES.en).toHaveProperty(`dispute.state.${state}`);
      expect(MESSAGES.ar).toHaveProperty(`dispute.state.${state}`);
    }
  });
});
