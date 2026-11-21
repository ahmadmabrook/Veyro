"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api, correlationId } from "@/lib/api";
import { moneyOf, parseAmount } from "@/lib/cash";

import { IDLE, type CashState } from "./state";

/**
 * Close a till. ADM-PAY-09, and COM-04-R05's discrepancy workflow.
 *
 * **`finance.cash.session` is routine and AAL 1**, which is what makes this a form rather
 * than a refusal: a front desk opens and closes a drawer every shift, and the catalogue
 * says a step-up between the two would make the till wrong instead of safe. What bounds the
 * permission is not a second factor but the two things the close does — the variance posts
 * to suspense and a case is opened — and a reviewer found that bound missing once: the
 * route took any account in the chart as the counterpart and cleared a member's receivable
 * with it. It takes a `suspense` account now, checked by kind.
 *
 * **The count is parsed here and the variance is the server's.** This action sends what was
 * counted; it never sends a variance, an expected figure or a reason for a difference it
 * computed itself. `close_cash_session` derives the expected figure from the drawer
 * account's own postings, which is the one number on this screen no caller may supply —
 * "adding it again here would have let a caller lower the expected figure and make a short
 * till balance, which is the caller-supplied-control shape every review in this build has
 * found."
 */
export async function closeDrawer(
  _previous: CashState,
  form: FormData,
): Promise<CashState> {
  const sessionId = String(form.get("session_id") ?? "");
  const entityId = String(form.get("legal_entity_id") ?? "");
  const suspenseId = String(form.get("suspense_account_id") ?? "");
  const currency = String(form.get("currency") ?? "");
  const typed = String(form.get("counted") ?? "").trim();
  const reason = String(form.get("reason") ?? "").trim();
  const echo = { counted: typed, reason };

  // **A drawer whose currency this build does not carry cannot be counted at all**, because
  // the two exponents it would be parsed with do not exist. Refusing is the only honest
  // answer; guessing two decimals would store the wrong number of minor units.
  const money = moneyOf(currency);
  if (money === null) return { ...IDLE, error: "cash.invalid", echo };

  const counted = parseAmount(typed, money);
  if (counted === null) return { ...IDLE, missing: { counted: true }, echo };

  // **The suspense account is where a variance lands, so without one there is no close.**
  // Saying which account is missing beats a 422 from the server, because the remedy is in
  // the chart rather than in this form.
  if (suspenseId === "") return { ...IDLE, error: "cash.needsSuspense", echo };

  try {
    await api(`/ledger/cash-sessions/${encodeURIComponent(sessionId)}/close`, {
      method: "POST",
      body: {
        counted_minor: counted,
        legal_entity_id: entityId,
        suspense_account_id: suspenseId,
        // Sent only when there is one. An empty string is not a reason and the schema
        // refuses it; `undefined` is the absence the server's own guard is written against.
        ...(reason === "" ? {} : { variance_reason: reason }),
        correlation_id: correlationId(),
      },
    });
    revalidatePath("/payments/cash");
    return { ...IDLE, message: "cash.closed" };
  } catch (error) {
    if (error instanceof ApiError && error.reason === "unreachable") {
      return { ...IDLE, error: "error.network", echo };
    }
    if (error instanceof ApiError && error.status === 429) {
      return { ...IDLE, error: "error.tooMany", echo };
    }
    // **A 422 here is almost always the one thing the module refuses**: a non-zero variance
    // with nothing written against it. "A till 2.00 down is noise; a till 2.00 down every
    // evening with nothing written is a pattern." So the field is named rather than the
    // form refused, because the remedy is a sentence the person at the till can write.
    if (error instanceof ApiError && (error.status === 400 || error.status === 422)) {
      return { ...IDLE, missing: { reason: true }, echo };
    }
    if (error instanceof ApiError && error.status === 409) {
      return { ...IDLE, error: "cash.conflict", echo };
    }
    return { ...IDLE, error: "cash.refused", echo };
  }
}
