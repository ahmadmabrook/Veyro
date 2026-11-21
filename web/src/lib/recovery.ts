import { api } from "@/lib/api";
import type { MessageKey } from "@/i18n/locale";

/**
 * ADM-PAY-05's recovery workspace: the failed payments as one decision.
 *
 * > **Why this is a workspace and not a list:** the six are one decision, not six. Reviewing
 * > each individually is available but is the slower path, and the batch action is the
 * > default because the recommended treatment is identical for all six.
 *
 * That argument is only true once the set has been **sorted**, which is why the read behind
 * this is new rather than the dunning listing reused: a batch mixing a member who needs a new
 * card with a member whose membership ended is six decisions wearing one button. The sort
 * lives in `collections.recovery_treatment` on the server, where the retry budget and the
 * failure classes already are.
 */

/** What a case wants next. Three values, from the server's own closed set. */
export type Treatment = "retry" | "link" | "review";

export type RecoveryCase = {
  case_id: string;
  invoice_id: string;
  stage: number;
  dunning_attempts: number;
  access_recommendation: string;
  next_action_on: string | null;
  opened_on: string;
  document_number: string;
  currency: string;
  outstanding_minor: number;
  due_on: string;
  /**
   * The payer, as an id.
   *
   * **No name comes out of this read.** `finance.dunning.read` is tenant-wide money, so a
   * name here would be a lateral read path around `people.person.read` — the same rule the
   * payments ledger follows, and the page composes names the same way.
   */
  payer_person_id: string;
  /** A declared code, never the provider's prose. */
  failure_code: string | null;
  failure_class: "retryable" | "permanent" | "needs_member_action" | "unknown_cause";
  /** The instrument's *kind* and nothing else about it: there is no card data in this build. */
  method: string | null;
  charges_presented: number;
  failed_at: string | null;
  membership_id: string | null;
  membership_status: string | null;
  membership_number: string | null;
  treatment: Treatment;
  treatment_reason: string;
  may_retry: boolean;
  /** Which message the *stage* would send. The sender does not choose it. */
  notification_key: string;
};

export type RecoveryWorkspace = {
  cases: RecoveryCase[];
  count: number;
  limit: number;
  truncated: boolean;
  at_risk: { currency: string; amount_minor: number }[];
  by_treatment: Record<Treatment, number>;
  all_retries_exhausted: boolean;
  access_recommendations: string[];
  no_access_blocked: boolean;
  at_risk_is_outstanding: string;
  nothing_here_sends: string;
  no_card_detail_exists: string;
};

export type PublishedTemplate = {
  template_id: string;
  template_key: string;
  version: number;
  category: string;
  channel: string;
  locale: string;
  subject: string | null;
  body: string;
  variables: string[];
  category_decides_whether_an_optout_stops_it: string;
  locale_is_per_template: string;
};

export function readRecovery(limit = 50): Promise<RecoveryWorkspace> {
  return api(`/finance/recovery?limit=${limit}`);
}

export function readPublishedTemplate(
  templateKey: string,
  locale?: string,
): Promise<PublishedTemplate> {
  const query = new URLSearchParams({ template_key: templateKey });
  if (locale) query.set("locale", locale);
  return api(`/notifications/templates/published?${query.toString()}`);
}

/**
 * The treatment as a word, and the reason under it as a sentence.
 *
 * **A stored value is never a label** — this repository has shipped that four times in one
 * pass, each one Latin letters in the middle of an Arabic line. And an unknown value falls
 * through to its raw form rather than to "other", because the set is the server's and may
 * grow: showing an ugly word is better than hiding a decision somebody has to act on.
 */
export function treatmentName(treatment: string): MessageKey | null {
  switch (treatment) {
    case "link":
      return "recovery.treatment.link";
    case "review":
      return "recovery.treatment.review";
    case "retry":
      return "recovery.treatment.retry";
    default:
      return null;
  }
}

export function reasonName(reason: string): MessageKey | null {
  switch (reason) {
    case "member_action_needed":
      return "recovery.why.memberAction";
    case "retries_exhausted":
      return "recovery.why.retriesExhausted";
    case "retries_remain":
      return "recovery.why.retriesRemain";
    case "failure_is_permanent":
      return "recovery.why.permanent";
    case "membership_ended":
      return "recovery.why.membershipEnded";
    case "membership_frozen":
      return "recovery.why.membershipFrozen";
    case "no_membership_cited":
      return "recovery.why.noMembership";
    case "cause_unknown":
      return "recovery.why.causeUnknown";
    default:
      return null;
  }
}

/**
 * The failure code as a word.
 *
 * The declared set is `collections.FAILURE_CLASSES`, and a code outside it is `unknown_cause`
 * on the server — so an unmapped code here is a provider the build has not seen, which the
 * reader should be shown rather than told is "other".
 */
export function failureName(code: string | null): MessageKey | null {
  switch (code) {
    case "card_expired":
      return "recovery.failure.cardExpired";
    case "insufficient_funds":
      return "recovery.failure.insufficientFunds";
    case "authentication_required":
      return "recovery.failure.authenticationRequired";
    case "incorrect_details":
      return "recovery.failure.incorrectDetails";
    case "limit_exceeded":
      return "recovery.failure.limitExceeded";
    case "issuer_unavailable":
      return "recovery.failure.issuerUnavailable";
    case "processing_error":
      return "recovery.failure.processingError";
    case "rate_limited":
      return "recovery.failure.rateLimited";
    case "card_stolen":
      return "recovery.failure.cardStolen";
    case "card_lost":
      return "recovery.failure.cardLost";
    case "do_not_honour_final":
      return "recovery.failure.doNotHonour";
    case "mandate_revoked":
      return "recovery.failure.mandateRevoked";
    case "account_closed":
      return "recovery.failure.accountClosed";
    case null:
      return "recovery.failure.none";
    default:
      return null;
  }
}

/**
 * Which `AttentionRow`/grid severity a treatment carries.
 *
 * `review` is the design's amber `review first`; `link` is its neutral `link ready`. `retry`
 * is neither — the system is still working on it, and marking it would put a row in front of
 * somebody who has nothing to do about it.
 */
export function treatmentSeverity(treatment: Treatment): "attention" | null {
  return treatment === "review" ? "attention" : null;
}

/**
 * Which notification keys the set would send, each once.
 *
 * The design previews one message because its six cases are all at stage 1. A set spanning
 * two stages would send two different messages, and a preview showing only the first would
 * be a claim about what the other members receive.
 */
export function keysInPlay(workspace: RecoveryWorkspace): string[] {
  return [...new Set(workspace.cases.map((one) => one.notification_key))].sort();
}

/**
 * Whether the set in front of the reader really is one decision.
 *
 * The canvas's closing note is the screen's whole argument — "the six are one decision, not
 * six … the batch action is the default because the recommended treatment is identical for
 * all six" — and it is a **claim**, true only when the treatments agree. A page that printed
 * it unconditionally would be inviting one batch action over a set where it does the wrong
 * thing to some rows.
 *
 * It lives here rather than inline in the page for the reason the integrations board
 * learned: the same comparison written twice leaves a cell disagreeing with the banner above
 * it. And it lives here rather than on the server because it is a sentence about the screen,
 * not a fact about the money — the server already returns the counts it is computed from.
 */
export type BatchVerdict =
  | { kind: "one_decision"; treatment: Treatment; count: number }
  | { kind: "mixed"; link: number; review: number; retry: number }
  | { kind: "empty" };

export function batchVerdict(workspace: RecoveryWorkspace): BatchVerdict {
  const { link, review, retry } = workspace.by_treatment;
  if (workspace.count === 0) return { kind: "empty" };
  const present = ([
    ["link", link], ["review", review], ["retry", retry],
  ] as const).filter(([, n]) => n > 0);
  if (present.length === 1) {
    const [treatment, count] = present[0]!;
    return { kind: "one_decision", treatment, count };
  }
  return { kind: "mixed", link, review, retry };
}

/**
 * The payment instrument, as a word.
 *
 * `card`, `bank_transfer`, `cash` and `wallet` are column values, and a column value
 * rendered where a word belongs is Latin letters in the middle of an Arabic line — the
 * defect this app shipped four times in one pass. An unmapped method falls through to its
 * stored form, because the set is MOD-017's and a reader chasing a payment needs to see
 * what it was attempted on even when this map has not caught up.
 */
export function methodName(method: string | null): MessageKey | null {
  switch (method) {
    case "card":
      return "recovery.method.card";
    case "bank_transfer":
      return "recovery.method.bankTransfer";
    case "direct_debit":
      return "recovery.method.directDebit";
    case "cash":
      return "recovery.method.cash";
    case "wallet":
      return "recovery.method.wallet";
    case "gift_card":
      return "recovery.method.giftCard";
    case "other":
      return "recovery.method.other";
    case null:
      return "recovery.method.none";
    default:
      return null;
  }
}
