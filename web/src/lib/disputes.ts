import { api } from "@/lib/api";
import type { MessageKey } from "@/i18n/locale";

/**
 * ADM-PAY-10's chargebacks, and the evidence a gym answers one with.
 *
 * > The check-in record is the strongest evidence a gym has and Veyro assembles it
 * > automatically. Accepting the loss is a real option and is recorded as a decision, not a
 * > lapse.
 *
 * **The deadline is the screen.** "Evidence due 26 August · 7 days" and "Missing the
 * deadline forfeits the amount automatically" are the two lines the canvas puts in a red
 * box, and the figure behind them is `collections.evidence_window` — computed on the server
 * so a surface cannot produce a second answer by subtracting two dates.
 */

export type Dispute = {
  dispute_id: string;
  payment_id: string;
  provider_case_ref: string;
  dispute_kind: string;
  reason_code: string;
  amount_minor: number;
  currency: string;
  opened_on: string;
  respond_due_on: string;
  status: string;
  response_ref: string | null;
  responded_at: string | null;
  outcome: string | null;
  closed_at: string | null;
  /** The payer, as an id. No name comes out of a money read. */
  payer_person_id: string;
  paid_at: string;
  method: string;
  invoice_id: string | null;
  document_number: string | null;
  fiscal_status: string | null;
  fiscal_ack_ref: string | null;
  membership_id: string | null;
  /** When the invoice was issued, which is the start of what it billed for. */
  billed_on: string | null;
  days_remaining: number;
  window_has_closed: boolean;
  days_given: number;
};

export type DisputeList = {
  disputes: Dispute[];
  count: number;
  limit: number;
  truncated: boolean;
  as_of: string;
  at_stake: { currency: string; amount_minor: number }[];
  at_stake_is_undecided_only: string;
  the_amount_is_held_by_the_acquirer: string;
  evidence_is_assembled_by_the_caller: string;
};

export type AttendanceWindow = {
  person_id: string;
  since: string;
  until: string;
  entries: number;
  days_attended: number;
  days: { on: string; location_name: string; entries: number }[];
  entries_not_decisions: string;
  each_day_is_local_to_its_door: string;
};

export function readDisputes(params: { status?: string; limit?: number } = {}):
Promise<DisputeList> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  query.set("limit", String(params.limit ?? 50));
  return api(`/finance/disputes?${query.toString()}`);
}

export function readAttendanceWindow(
  personId: string, since: string, until: string,
): Promise<AttendanceWindow> {
  const query = new URLSearchParams({ person_id: personId, since, until });
  return api(`/access/attendance/window?${query.toString()}`);
}

/**
 * How urgent the deadline is.
 *
 * Three states and not a gradient, because the actions differ: a closed window means the
 * response can no longer be sent and the exposure is the full amount; a week or less is the
 * canvas's red box; more than that is a date to note. `days_given` is carried by the read
 * for the same reason the module states — "three days left" means something different out
 * of thirty than out of four — and a surface that coloured on a fraction would call a
 * four-day scheme window comfortable on its second day.
 */
export type Urgency = "closed" | "pressing" | "noted";

export const PRESSING_DAYS = 7;

export function urgency(dispute: Dispute): Urgency {
  if (dispute.window_has_closed) return "closed";
  return dispute.days_remaining <= PRESSING_DAYS ? "pressing" : "noted";
}

/** A dispute still to be decided is exposure; one already won or lost is settled money. */
export function undecided(dispute: Dispute): boolean {
  return dispute.status === "open" || dispute.status === "responded";
}

export function statusName(status: string): MessageKey | null {
  switch (status) {
    case "open":
      return "dispute.status.open";
    case "responded":
      return "dispute.status.responded";
    case "won":
      return "dispute.status.won";
    case "lost":
      return "dispute.status.lost";
    case "withdrawn":
      return "dispute.status.withdrawn";
    default:
      return null;
  }
}

export function kindName(kind: string): MessageKey | null {
  switch (kind) {
    case "chargeback":
      return "dispute.kind.chargeback";
    case "retrieval":
      return "dispute.kind.retrieval";
    case "pre_arbitration":
      return "dispute.kind.preArbitration";
    default:
      return null;
  }
}

/**
 * The scheme's reason, as a sentence.
 *
 * The canvas renders one — "claiming the service was not received" — and a reason code shown
 * raw is a stored value where a sentence belongs, which in Arabic is Latin letters mid-line.
 * An unmapped code falls through to the code, because the set is a scheme's and not this
 * build's: showing an unfamiliar code is better than hiding why the money is being taken.
 */
export function reasonName(code: string): MessageKey | null {
  switch (code) {
    case "product_not_received":
      return "dispute.reason.notReceived";
    case "product_unacceptable":
      return "dispute.reason.unacceptable";
    case "fraudulent":
      return "dispute.reason.fraudulent";
    case "duplicate":
      return "dispute.reason.duplicate";
    case "subscription_canceled":
      return "dispute.reason.cancelled";
    case "credit_not_processed":
      return "dispute.reason.creditNotProcessed";
    case "unrecognized":
      return "dispute.reason.unrecognised";
    default:
      return null;
  }
}

/**
 * One line of the canvas's "EVIDENCE VEYRO CAN ASSEMBLE" list.
 *
 * `have` is the ☑/☐ the canvas draws, and the third state is the one it does not have: a
 * piece of evidence this *reader* may not see. A refused permission rendered as ☐ would tell
 * an accountant the gym cannot prove something it can.
 */
export type EvidenceState = "have" | "missing" | "refused";

export type Evidence = {
  key: string;
  state: EvidenceState;
  label: MessageKey;
  detail?: string;
  note?: MessageKey;
};

/**
 * What this build can put in front of a scheme, from what the reads came back with.
 *
 * **Pure, because the states have to be provable.** A fixture renders one case, and the
 * three states here are the point: ☑ is the canvas's, ☐ is "we do not have this", and
 * `refused` is "you may not see whether we have this" — which the canvas has no mark for
 * because it assumes a reader who can see everything. Rendering a refusal as ☐ would tell
 * an accountant the gym cannot prove attendance it can prove, which is the worst sentence
 * this screen could say. Leaving the classification in the page would make two of the three
 * reachable only by signing in as somebody the fixture does not have.
 *
 * The order is the canvas's, which is also the order of usefulness: the check-in record
 * first, because it is the one a gym has and a card issuer does not.
 */
export function evidenceFrom(
  dispute: Pick<Dispute, "billed_on" | "membership_id" | "document_number"
    | "fiscal_ack_ref" | "fiscal_status">,
  found: {
    mayAttendance: boolean;
    attendance: AttendanceWindow | null;
    mayMembership: boolean;
    signedAt: string | null;
    signatureKind: string | null;
    membershipRead: boolean;
  },
): Evidence[] {
  const out: Evidence[] = [];

  // **The billed period.** No invoice behind the payment means no period to count over,
  // which is a different answer from the member not having come.
  if (dispute.billed_on === null) {
    out.push({ key: "attendance", state: "missing", label: "dispute.ev.attendance",
               note: "dispute.ev.noPeriod" });
  } else if (!found.mayAttendance || found.attendance === null) {
    out.push({ key: "attendance", state: "refused", label: "dispute.ev.attendance",
               note: "dispute.ev.attendanceRefused" });
  } else {
    out.push({
      key: "attendance",
      state: found.attendance.entries > 0 ? "have" : "missing",
      label: "dispute.ev.attendance",
      detail: `${found.attendance.entries} · ${found.attendance.since} — `
        + `${found.attendance.until}`,
    });
  }

  if (dispute.membership_id === null) {
    out.push({ key: "contract", state: "missing", label: "dispute.ev.contract",
               note: "dispute.ev.noMembership" });
  } else if (!found.mayMembership || !found.membershipRead) {
    out.push({ key: "contract", state: "refused", label: "dispute.ev.contract",
               note: "dispute.ev.contractRefused" });
  } else if (found.signedAt === null) {
    // An agreement that exists and was never signed is the one piece of this a scheme
    // would ask about, so it is marked rather than omitted.
    out.push({ key: "contract", state: "missing", label: "dispute.ev.contract",
               note: "dispute.ev.unsigned" });
  } else {
    out.push({ key: "contract", state: "have", label: "dispute.ev.contract",
               detail: `${found.signatureKind ?? ""} · ${found.signedAt.slice(0, 10)}` });
  }

  // The invoice and its fiscal acknowledgement ride on the dispute read itself, so there
  // is no permission to refuse and no third state.
  //
  // **The two halves are not the same evidence, and only one of them is always there.**
  // The canvas's line is "Invoice and JoFotara reference": the document is the gym's own
  // record and the acknowledgement is a tax authority's confirmation that it was filed.
  // An invoice whose filing was *rejected* has only the first half — and ticking that line
  // as though both were held would put an accountant in front of a scheme expecting a
  // reference that does not exist. Found by looking at a fixture whose filing had been
  // rejected and seeing a tick beside it.
  if (dispute.document_number === null) {
    out.push({ key: "invoice", state: "missing", label: "dispute.ev.invoice",
               note: "dispute.ev.noInvoice" });
  } else if (dispute.fiscal_ack_ref) {
    out.push({ key: "invoice", state: "have", label: "dispute.ev.invoice",
               detail: `${dispute.document_number} · ${dispute.fiscal_ack_ref}` });
  } else {
    out.push({
      key: "invoice", state: "have", label: "dispute.ev.invoice",
      detail: dispute.document_number,
      note: dispute.fiscal_status === "rejected"
        ? "dispute.ev.filingRejected"
        : "dispute.ev.notFiled",
    });
  }

  // The canvas's one unticked line, and it stays unticked whatever the reads say: nothing
  // in this build holds a written statement.
  out.push({ key: "statement", state: "missing", label: "dispute.ev.statement",
             note: "dispute.ev.statementIsYours" });
  return out;
}
