"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api, correlationId } from "@/lib/api";
import { moneyOf, parseAmount } from "@/lib/cash";

import { IDLE, type ShiftError, type ShiftState } from "./state";

type OpenedBody = {
  session_id: string;
  was_a_handover?: boolean;
  opening_expected_minor?: number | null;
  handover_variance_minor?: number | null;
  case_id?: string | null;
  repeated?: boolean;
};

/**
 * FD-07 · OPEN A SHIFT — "Open the shift".
 *
 * **The count is the only figure this sends.** There is no `opening_expected_minor` field on
 * the request: the ledger says what should be in the drawer and the person says what is
 * there, and a caller able to send both could make any handover balance -- which is the same
 * rule the close is built on and the reason the comparison, the posting and the attribution
 * are all the server's.
 *
 * **`float_source_account_id` is sent only when the drawer is empty.** A handover draws
 * nothing and the command refuses the field there rather than accepting and ignoring it, so
 * the form has to know which act it is performing -- derived from the same standing balance
 * the server derives it from, never from a flag of its own.
 *
 * **`finance.cash.session` is `configuration` with no financial class**, which is why this
 * screen has a working button where most of this app's writes have a reason for not having
 * one: a front desk opens a drawer every shift, and the catalogue says a step-up between the
 * two ends would make the till wrong rather than safe. What bounds it is that a difference
 * posts to suspense and opens a case.
 */
export async function openShift(
  _previous: ShiftState, form: FormData,
): Promise<ShiftState> {
  const typed = String(form.get("counted") ?? "").trim();
  const reason = String(form.get("reason") ?? "").trim();
  const currency = String(form.get("currency") ?? "");
  const echo = { counted: typed, reason };

  // A drawer whose currency this build does not carry cannot be counted at all: the two
  // exponents it would be parsed with do not exist, and guessing two decimals would store
  // the wrong number of minor units.
  const money = moneyOf(currency);
  if (money === null) return { ...IDLE, error: "deskShift.invalid", echo };
  const counted = parseAmount(typed, money);
  if (counted === null) return { ...IDLE, missing: { counted: true }, echo };

  const drawnOn = String(form.get("float_source_account_id") ?? "");
  const entity = String(form.get("legal_entity_id") ?? "");
  const suspense = String(form.get("suspense_account_id") ?? "");

  try {
    const opened = await api<OpenedBody>("/ledger/cash-sessions", {
      method: "POST",
      body: {
        location_id: String(form.get("location_id") ?? ""),
        cash_account_id: String(form.get("cash_account_id") ?? ""),
        drawer_label: String(form.get("drawer_label") ?? ""),
        currency,
        opening_float_minor: counted,
        ...(drawnOn === "" ? {} : { float_source_account_id: drawnOn }),
        ...(entity === "" ? {} : { legal_entity_id: entity }),
        ...(suspense === "" ? {} : { suspense_account_id: suspense }),
        ...(reason === "" ? {} : { handover_reason: reason }),
        // **Keyed on the drawer and the count**, so a double press opens one shift and the
        // second answer comes back from the row -- while a count the person corrected before
        // pressing again is a different key, which is what makes the retry converge rather
        // than hand back a figure nobody typed. A key compared on fewer fields than the
        // command takes is this build's most-repeated idempotency defect.
        idempotency_key: `desk-open-${String(form.get("cash_account_id") ?? "")}`
          + `-${counted}`,
        correlation_id: correlationId(),
      },
    });
    revalidatePath("/desk/shift");
    return {
      ...IDLE,
      opened: {
        sessionId: String(opened.session_id),
        wasHandover: opened.was_a_handover === true,
        expectedMinor: opened.opening_expected_minor ?? null,
        varianceMinor: opened.handover_variance_minor ?? null,
        caseId: opened.case_id ?? null,
        repeated: opened.repeated === true,
      },
    };
  } catch (error) {
    return { ...IDLE, error: reasonFor(error), echo, ...missingFor(error) };
  }
}

/**
 * Which refusal this was, in the words a desk can act on.
 *
 * **A flat "that was refused" sends a receptionist to retype a count when what is missing is
 * a sentence**, which is the whole reason these are told apart by code. The reason refusal is
 * matched on the service's own message rather than a code, because `check_handover` raises an
 * `InvalidRequest` carrying the prose -- and that prose is the figure the person needs.
 */
function reasonFor(error: unknown): ShiftError {
  if (!(error instanceof ApiError)) return "deskShift.refused";
  if (error.reason === "unreachable") return "error.network";
  if (error.status === 429) return "error.tooMany";
  if (error.status === 403) return "deskShift.needsStepUp";
  if (error.reason === "this_drawer_already_has_an_open_session") {
    return "deskShift.alreadyOpen";
  }
  if (error.reason === "this_drawer_already_holds_money_so_no_float_is_drawn") {
    return "deskShift.drawsNothing";
  }
  if (error.reason === "a_handover_that_does_not_balance_names_an_entity_and_suspense"
      || error.reason === "a_float_names_the_account_it_came_from_and_an_entity") {
    return "deskShift.needsAccounts";
  }
  if (typeof error.reason === "string" && error.reason.includes("states why")) {
    return "deskShift.needsReason";
  }
  return "deskShift.refused";
}

function missingFor(error: unknown): { missing?: ShiftState["missing"] } {
  if (error instanceof ApiError
      && typeof error.reason === "string" && error.reason.includes("states why")) {
    return { missing: { reason: true } };
  }
  return {};
}
