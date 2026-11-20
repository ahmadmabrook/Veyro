import { api } from "@/lib/api";

/**
 * ADM-PAY-03 · INVOICE DETAIL — "One invoice, and its life".
 *
 * **The reads existed and the screen did not.** `GET /finance/invoices/{id}/history` was
 * built with a docstring that names this canvas by id and says what it is for -- "ADM-PAY-03's
 * middle section" -- and nothing has ever rendered it. That is the "a writer with no reader"
 * shape this module already paid for, in reverse: a read nobody renders is a read nobody
 * sized, and until a page asked for it the only way to see an invoice's life was a `psql`
 * session.
 */

export type InvoiceLine = {
  line_number: number;
  description: string;
  quantity: number;
  unit_net_minor: number;
  net_minor: number;
  tax_rate_bp: number;
  tax_minor: number;
  gross_minor: number;
};

export type CreditNote = {
  invoice_id: string;
  document_number: string;
  gross_minor: number;
  currency: string;
  issued_on: string;
};

export type InvoiceDetail = {
  invoice_id: string;
  billing_account_id: string;
  payer_person_id: string;
  document_number: string;
  document_kind: string;
  serial: number;
  /** Positive once a due date has passed on an unsettled document, else 0. */
  days_late: number;
  net_minor: number;
  tax_minor: number;
  gross_minor: number;
  currency: string;
  issued_on: string;
  due_on: string;
  payment_status: string;
  paid_at: string | null;
  paid_minor: number;
  refunded_minor: number;
  credited_minor: number;
  /** The document this one credits, where it is itself a credit note. */
  credits_invoice_id: string | null;
  credit_notes: CreditNote[];
  fiscal_status: string;
  fiscal_acknowledged: boolean;
  fiscal_ack_ref: string | null;
  fiscal_acked_at: string | null;
  fiscal_exemption_reason: string | null;
  lines: InvoiceLine[];
};

export type InvoiceEvent = {
  kind: "issued" | "payment_intent" | "payment" | "refund" | "dunning" | "dispute";
  at: string;
  amount_minor?: number;
  currency?: string;
  status?: string;
  method?: string;
  stage?: number;
  attempts?: number;
  access_recommendation?: string;
  next_action_on?: string | null;
  dispute_kind?: string;
  reason_code?: string;
  opened_on?: string;
  respond_due_on?: string;
  detail?: string | null;
};

export type InvoiceHistory = {
  invoice_id: string;
  document_number: string;
  events: InvoiceEvent[];
  /**
   * The scheme's deadline on a dispute still waiting for a response.
   *
   * **Lifted out of the events by the server**, deliberately: a banner is about one deadline,
   * and a client scanning a timeline for the earliest open dispute would be deriving
   * something the server already knows. MOD-016's `in_window` judgement, one module over.
   */
  evidence_due_on: string | null;
  immutable_because: string;
};

export function readInvoice(invoiceId: string): Promise<InvoiceDetail> {
  return api(`/finance/invoices/${encodeURIComponent(invoiceId)}`);
}

export function readInvoiceHistory(invoiceId: string): Promise<InvoiceHistory> {
  return api(`/finance/invoices/${encodeURIComponent(invoiceId)}/history`);
}

/**
 * The status band: what this document is, in one phrase.
 *
 * ADM-PAY-03 draws `UNPAID · 2 DAYS LATE` beside the number, and the canvas's own state list
 * names five more. **Lateness is a second fact and not a status**: `unpaid` and `unpaid, two
 * days late` are different things to a reader, and `days_late` is the server's own arithmetic
 * over the due date rather than a subtraction this page would do a second time.
 */
export function band(invoice: InvoiceDetail): {
  key: "invoice.bandPaid" | "invoice.bandUnpaid" | "invoice.bandPartPaid"
  | "invoice.bandOverdue" | "invoice.bandCredited" | "invoice.bandWrittenOff";
  tone: "critical" | "warning" | "neutral" | "success";
} {
  switch (invoice.payment_status) {
    case "paid":
      // **A green badge here, and nowhere in a list.** ADM-PAY-03's own state note is
      // "Paid — status badge in success", and ADM-MEM-01's is "No green badges". Both are
      // right: a member's record sits among records where a green badge dilutes the overdue
      // one, and an invoice's own state is what this screen is about.
      return { key: "invoice.bandPaid", tone: "success" };
    case "credited":
      return { key: "invoice.bandCredited", tone: "neutral" };
    case "written_off":
      return { key: "invoice.bandWrittenOff", tone: "warning" };
    case "part_paid":
      return {
        key: invoice.days_late > 0 ? "invoice.bandOverdue" : "invoice.bandPartPaid",
        tone: invoice.days_late > 0 ? "critical" : "warning",
      };
    default:
      return invoice.days_late > 0
        ? { key: "invoice.bandOverdue", tone: "critical" }
        : { key: "invoice.bandUnpaid", tone: "warning" };
  }
}

/**
 * Which message explains the fiscal state, and whether it is a problem.
 *
 * **"Not submitted" is correct rather than a failure**, which is the canvas's whole point:
 * "Jordan requires submission of the settled transaction. An unpaid invoice has nothing to
 * report yet." A page that coloured every unfiled document would teach an operator to ignore
 * the one that was actually rejected.
 */
export function fiscal(invoice: InvoiceDetail): {
  key: "invoice.fiscalPending" | "invoice.fiscalSubmitted" | "invoice.fiscalAccepted"
  | "invoice.fiscalRejected" | "invoice.fiscalNotRequired";
  needsSomebody: boolean;
} {
  switch (invoice.fiscal_status) {
    case "accepted":
      return { key: "invoice.fiscalAccepted", needsSomebody: false };
    case "submitted":
      return { key: "invoice.fiscalSubmitted", needsSomebody: false };
    case "rejected":
      return { key: "invoice.fiscalRejected", needsSomebody: true };
    case "not_required":
      return { key: "invoice.fiscalNotRequired", needsSomebody: false };
    default:
      return { key: "invoice.fiscalPending", needsSomebody: false };
  }
}

/** What a timeline row is, as a message key. One per `kind` the server emits. */
export function eventTitle(event: InvoiceEvent): string {
  return `invoice.event.${event.kind}`;
}
