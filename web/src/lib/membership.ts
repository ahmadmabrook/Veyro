import { formatMoney } from "@/i18n/locale";
import { api } from "@/lib/api";
import type { FreezeAllowance } from "@/lib/freeze";

/**
 * MOD-017's reads, typed: what a member agreed to, what it entitles them to, and what they owe.
 *
 * **These routes did not exist until this surface needed them.** Every read MOD-017 shipped
 * took an id the caller already held, so nothing could answer "what memberships does this
 * person have" -- the same "a writer with no reader" gap `GET /brands` closed for MOD-004, and
 * the remedy was the same: routes on the server rather than inference in the client.
 *
 * **Nothing here carries a name, an address or a birth date, and that is deliberate on the
 * server's side rather than an omission on this one.** MOD-014 owns those columns and masks
 * them by class and by the reader's assurance. A membership list that carried the member's
 * legal name would be a lateral read path around `people.person.read` -- MOD-010's
 * `events.event.read` finding, where one routine permission returned another module's
 * restricted fields. So a page that wants both calls both modules, each through its own gate,
 * and this file is only half of that composition.
 *
 * **Three permissions, not one.** `membership.record.read`, `membership.entitlement.read` and
 * `finance.account.read` are separate, and a reader may hold any subset: a coach sees the
 * membership and not the money. Each block on the page asks its own gate, because an empty
 * block and a refused block are different facts and only one of them is about the member.
 */

/** The cached status, which answers "now". A dispute about a past date is `/as-of`. */
export type MembershipRow = {
  membership_id: string;
  person_id: string;
  membership_number: string;
  status: string;
  starts_on: string;
  ends_on: string | null;
  current_period_start: string | null;
  current_period_end: string | null;
  status_effective_on: string;
  agreement_id: string;
  /** From the agreement, which snapshots what was sold -- not today's price. */
  amount_minor: number;
  currency: string;
  minimum_term_ends_on: string | null;
  membership_kind: string;
  billing_period: string;
  is_off_peak: boolean;
};

export type LifecycleChange = {
  change_kind: string;
  from_status: string;
  to_status: string;
  effective_on: string;
  decided_at: string;
  reason: string;
  /**
   * True for a medical hold, for every reader. MOD-008 classifies health as
   * `biometric_sensitive`, which maps to an assurance level no session in this build can
   * reach, so the entry stays visible and the sentence does not -- the same dead end MOD-014
   * records for its own health classes.
   */
  reason_withheld: boolean;
};

export type MembershipDetail = Omit<
  MembershipRow,
  "amount_minor" | "currency" | "minimum_term_ends_on" | "membership_kind"
  | "billing_period" | "is_off_peak" | "agreement_id"
> & {
  version: number;
  agreement: {
    agreement_id: string;
    amount_minor: number;
    currency: string;
    starts_on: string;
    ends_on: string | null;
    minimum_term_ends_on: string | null;
    status: string;
    signed_at: string | null;
    signature_kind: string | null;
    price_resolution_id: string | null;
    contract_version_id: string;
  };
  terms: {
    membership_terms_id: string;
    contract_key: string;
    membership_kind: string;
    billing_period: string;
    installment_count: number | null;
    prepaid_days: number | null;
    is_off_peak: boolean;
    product_id: string;
  };
  history: LifecycleChange[];
};

export type EntitlementGrant = {
  grant_id: string;
  person_id: string;
  membership_id: string | null;
  is_counted: boolean;
  granted_quantity: number | null;
  valid_from: string;
  valid_to: string | null;
  status: string;
  source_kind: string;
  brand_id: string | null;
  location_id: string | null;
  usable_from_minute: number | null;
  usable_to_minute: number | null;
  policy_key: string;
  display_name: string;
  entitlement_type: string;
  /** Null for an uncounted grant -- "unlimited" is not a number and is not rendered as one. */
  balance: number | null;
  held: number | null;
};

export type BillingAccount = {
  billing_account_id: string;
  payer_person_id: string;
  account_kind: string;
  account_number: string;
  currency: string;
  legal_entity_id: string;
  status: string;
  payment_terms_days: number;
  closed_at: string | null;
};

export type InvoiceRow = {
  invoice_id: string;
  billing_account_id: string;
  payer_person_id: string;
  document_number: string;
  document_kind: string;
  net_minor: number;
  tax_minor: number;
  gross_minor: number;
  currency: string;
  issued_on: string;
  due_on: string;
  payment_status: string;
  fiscal_status: string;
  credits_invoice_id: string | null;
  paid_minor: number;
};

type Page<T> = { count: number; limit: number; truncated: boolean } & T;

export function listMemberships(personId: string): Promise<Page<{
  memberships: MembershipRow[];
}>> {
  return api(`/memberships?person_id=${encodeURIComponent(personId)}`);
}

export function readMembership(membershipId: string): Promise<MembershipDetail> {
  return api(`/memberships/${encodeURIComponent(membershipId)}`);
}

export function listGrants(personId: string): Promise<Page<{
  grants: EntitlementGrant[];
  /** The server says so rather than this page assuming it -- see `heldIsUnswept`. */
  balance_is_unswept: boolean;
}>> {
  return api(`/member-entitlements?person_id=${encodeURIComponent(personId)}`);
}

export function listAccounts(personId: string): Promise<Page<{
  accounts: BillingAccount[];
}>> {
  return api(`/finance/accounts?person_id=${encodeURIComponent(personId)}`);
}

export function listInvoices(personId: string): Promise<Page<{
  invoices: InvoiceRow[];
}>> {
  return api(`/finance/invoices?person_id=${encodeURIComponent(personId)}`);
}

/**
 * An amount in minor units, as a figure a reader can check against a receipt.
 *
 * **This delegates to `formatMoney` and does not do the arithmetic.** The first version of
 * this function divided by `Intl`'s own exponent and formatted with `Intl.NumberFormat`, which
 * was a *second* implementation of money rendering -- in the one place this repository already
 * has a cross-runtime parity test, because the design system requires numerals "applied
 * identically on screen, receipt, export and PDF" and a receipt is rendered by
 * `backend/app/l10n/conventions.py`. Two implementations pass their own tests forever while
 * drifting apart; `tests/unit/conventions-parity.test.mjs` exists precisely because only
 * comparing the two outputs catches that. Caught by reading the test directory, not by a
 * failure.
 *
 * **`latn`, because the numeral system is a tenant setting this build does not carry.** The
 * design intent is per tenant; every other figure on these surfaces is `formatInteger(...,
 * "latn")`, and picking Arabic-Indic here alone would make one column disagree with the
 * column beside it.
 *
 * **An unsupported currency falls back rather than throwing.** `formatMoney` knows JOD and USD
 * and raises for anything else, which is right for a receipt and wrong for a page: a tenant
 * trading in a third currency would get a 500 on a member's record rather than a figure it
 * cannot format prettily. The fallback shows the integer and the code, which is honest and
 * unmistakable.
 */
export function money(minor: number, currency: string): string {
  try {
    return formatMoney(minor, currency, "latn", "en");
  } catch {
    return `${minor} ${currency}`;
  }
}

/**
 * What is left on a grant, as a sentence rather than a number.
 *
 * Three facts and not one: an uncounted grant has no balance at all, a counted one has a
 * balance, and some of that balance may be held by a booking the member has not attended yet.
 * MOD-017's own note is that "you have two classes left" and "two of your classes are held"
 * are different answers to the same question, and a member asking gets both.
 */
export function remaining(grant: EntitlementGrant): {
  kind: "unlimited" | "counted";
  balance: number | null;
  held: number | null;
} {
  if (!grant.is_counted) return { kind: "unlimited", balance: null, held: null };
  return { kind: "counted", balance: grant.balance, held: grant.held };
}

/**
 * Whether an invoice still wants money, which is not the same as `payment_status !== "paid"`.
 *
 * `credited` and `written_off` are both settled: the first was corrected by a credit note and
 * the second was given up on. Treating either as outstanding would put a figure on a
 * collections screen that nobody is going to collect, which is how a dunning list stops being
 * read.
 */
const SETTLED = new Set(["paid", "credited", "written_off"]);

export function isOutstanding(invoice: InvoiceRow): boolean {
  return invoice.document_kind === "invoice" && !SETTLED.has(invoice.payment_status);
}

export function outstandingMinor(invoices: InvoiceRow[]): number {
  return invoices
    .filter(isOutstanding)
    .reduce((total, invoice) => total + invoice.gross_minor - invoice.paid_minor, 0);
}

/**
 * What is left of a membership's freeze allowance. ADM-MSH-03.
 *
 * **The figure the canvas puts in the consequence panel before the button**, and it was
 * unreadable until this route existed: `allowance_days_used_before` came back from the write
 * and from nothing else, so the only way to learn how much a member had spent was to spend
 * more of it. The seventh "a writer with no reader" in this build.
 */
export function readFreezeAllowance(membershipId: string): Promise<FreezeAllowance> {
  return api<FreezeAllowance>(
    `/memberships/${encodeURIComponent(membershipId)}/freeze-allowance`);
}
