import { api } from "@/lib/api";

/**
 * MOD-018's reads, typed: the chart, the lock, the balances and the unanswered questions.
 *
 * **There is deliberately no journal read here, and no route to list one.** `finance.ledger
 * .read` is a narrow lateral read around `finance.invoice.read` -- `GET /ledger/journals/{id}`
 * returns an invoice's net, tax, gross, document number and the payer's `person_id` -- and the
 * module discloses that it stays a gap rather than a defect only because journal ids are not
 * enumerable from any route that permission reaches. A board that listed journals would close
 * the gap in the wrong direction, which is MOD-010's `events.event.read` finding. So this
 * surface shows aggregates and states, and never a journal.
 *
 * **Two of these reads did not exist until this board needed them.** The chart could not be
 * listed, and neither could the periods -- which means COM-04-R06's lock, the control that
 * decides whether a till can post at all, was unreadable: the only way to find out whether a
 * month was shut was to try to post into it and read the refusal.
 */

export type LedgerAccount = {
  account_id: string;
  account_code: string;
  account_kind: string;
  display_name: string;
  currency: string;
  brand_id: string | null;
  location_id: string | null;
  legal_entity_id: string | null;
  status: string;
  retired_at: string | null;
};

/**
 * A financial period and whether it will take a posting.
 *
 * `admits_trade` is derived by the server rather than by each reader, because `closing` is the
 * state that surprises: it admits the close's own entries and no trade at all, so a surface
 * reasoning from `status` alone gets the implication wrong in the one case that matters.
 */
export type LedgerPeriod = {
  period_id: string;
  legal_entity_id: string;
  period_key: string;
  starts_on: string;
  ends_on: string;
  status: string;
  closed_at: string | null;
  closed_by: string | null;
  reopened_at: string | null;
  reopened_by: string | null;
  reopen_reason: string | null;
  admits_trade: boolean;
};

export type TrialBalanceLine = {
  account_id: string;
  account_code: string;
  account_kind: string;
  account_class: string;
  status: string;
  debit_minor: number;
  credit_minor: number;
};

export type TrialBalance = {
  legal_entity_id: string;
  currency: string;
  as_of: string;
  lines: TrialBalanceLine[];
  debit_total_minor: number;
  credit_total_minor: number;
  /** Equal by construction, so a false here is a ledger that lost rows, not a rounding slip. */
  balanced: boolean;
  difference_minor: number;
};

export type ReconciliationCase = {
  case_id: string;
  legal_entity_id: string;
  case_kind: string;
  subject_kind: string;
  subject_ref: string;
  expected_minor: number;
  observed_minor: number;
  difference_minor: number;
  currency: string;
  detail: string;
  status: string;
  opened_on: string;
  age_days: number;
};

export type RecognitionDue = {
  schedule_id: string;
  basis: string;
  currency: string;
  source_kind: string;
  source_ref: string;
  recognised_minor: number;
  remaining_minor: number;
  /** Null for an `on_delivery` schedule: the count belongs to the module that delivers. */
  amount_due_minor: number | null;
  why?: string;
};

type Page<T> = { count: number; limit: number; truncated: boolean } & T;

export function listAccounts(): Promise<Page<{ accounts: LedgerAccount[] }>> {
  return api("/ledger/accounts");
}

export function listPeriods(
  legalEntityId?: string,
): Promise<Page<{ periods: LedgerPeriod[]; absence_means_never_opened: boolean }>> {
  const query = legalEntityId
    ? `?legal_entity_id=${encodeURIComponent(legalEntityId)}`
    : "";
  return api(`/ledger/periods${query}`);
}

export function readTrialBalance(
  legalEntityId: string,
  currency: string,
): Promise<TrialBalance> {
  return api(
    `/ledger/trial-balance?legal_entity_id=${encodeURIComponent(legalEntityId)}` +
      `&currency=${encodeURIComponent(currency)}`,
  );
}

export function listReconciliationCases(): Promise<{
  as_of: string;
  count: number;
  cases: ReconciliationCase[];
}> {
  return api("/ledger/reconciliation-cases");
}

export function listRecognitionDue(): Promise<{ as_of: string; due: RecognitionDue[] }> {
  return api("/ledger/recognition-due");
}

/**
 * Which periods need somebody, and which are merely shut.
 *
 * A `closing` period is work in progress -- an accountant entered it deliberately -- and a
 * `reopened` one is a filed month somebody had to unlock, which is the row a reviewer asks
 * about. `closed` is the resting state and is not an exception. Keeping those apart is the
 * same judgement MOD-021's fleet board makes about `maintenance` versus `offline`: a
 * deliberate state is not an incident, and listing it as one is how an alert channel gets
 * muted.
 */
export function periodsNeedingAttention(periods: LedgerPeriod[]): LedgerPeriod[] {
  return periods.filter((p) => p.status === "closing" || p.status === "reopened");
}

/**
 * The difference a trial balance reports, as a fact rather than a number.
 *
 * Every journal balances by a deferred constraint trigger, so the debits and credits of all of
 * them are equal by construction. A difference is therefore not a rounding question: it means
 * the ledger lost rows, and that is a different sentence from "these two columns differ".
 */
export function balanceVerdict(
  balance: TrialBalance,
): { kind: "balanced" | "lost_rows"; differenceMinor: number } {
  return balance.balanced
    ? { kind: "balanced", differenceMinor: 0 }
    : { kind: "lost_rows", differenceMinor: balance.difference_minor };
}

/**
 * Whether the trial balance has anything on it at all.
 *
 * A chart with accounts and no postings is a tenant mid-setup, which is an ordinary state --
 * `post_invoice` returns `ledger_skipped_because` rather than refusing, precisely so a tenant
 * that has not finished does not find its till has stopped working. A board that showed a page
 * of zeroes would hide that; one that said "nothing here" would imply something is wrong.
 */
export function hasPostings(balance: TrialBalance): boolean {
  return balance.debit_total_minor !== 0 || balance.credit_total_minor !== 0;
}
