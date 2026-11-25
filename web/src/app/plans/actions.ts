"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api, correlationId } from "@/lib/api";
import { moneyOf, parseAmount } from "@/lib/cash";
import { confirms } from "@/lib/plans";

import { IDLE, type PriceError, type PriceState } from "./state";

/**
 * ADM-MSH-09 — write a new price version. COM-02-R02.
 *
 * **A new version, never an edit**, and that is the module's own property rather than this
 * action's caution: `cat_prices` carries UPDATE on the four supersession columns and nothing
 * else, so "an order resolved last March re-derives to the same figure a year later because
 * the row it read cannot have changed". Re-pricing is `POST /catalog/prices`.
 *
 * **The confirmation is checked here as well as in the form.** The client decides whether to
 * enable a button and a server action is the thing that writes — so a submit that arrived
 * without the typed figure, from a form rendered before JavaScript ran or from anywhere else,
 * is refused rather than trusted. The canvas's control is "type 58.00 to confirm" and a
 * control only the browser enforces is a control.
 *
 * **`catalog.price.write` is financial class**, so an ordinary password session cannot press
 * this and the page offers the step-up first — ADM-MSH-03's precedent, and the honest cost is
 * one recovery code per twelve-hour window rather than one per act.
 */
export async function writePrice(
  _previous: PriceState, form: FormData,
): Promise<PriceState> {
  const amount = String(form.get("amount") ?? "").trim();
  const from = String(form.get("effective_from") ?? "").trim();
  const confirm = String(form.get("confirm") ?? "").trim();
  const currency = String(form.get("currency") ?? "");
  const wasMinor = Number(form.get("was_minor") ?? "");
  const echo = { amount, from, confirm };

  const money = moneyOf(currency);
  if (money === null) return { ...IDLE, error: "plans.notAnAmount", echo };
  const amountMinor = parseAmount(amount, money);
  if (amountMinor === null) return { ...IDLE, error: "plans.notAnAmount", echo };
  if (!confirms(confirm, { amountMinor, currency })) {
    return { ...IDLE, error: "plans.refused", echo };
  }
  const bookId = String(form.get("price_book_id") ?? "");

  try {
    const priced = await api<{ price_id: string }>("/catalog/prices", {
      method: "POST",
      body: {
        price_book_id: bookId,
        variant_id: String(form.get("variant_id") ?? ""),
        amount_minor: amountMinor,
        effective_from: from,
        correlation_id: correlationId(),
      },
    });
    revalidatePath("/plans");
    return {
      ...IDLE,
      priced: {
        priceId: String(priced.price_id),
        amountMinor,
        currency,
        effectiveFrom: from,
        wasMinor: Number.isInteger(wasMinor) ? wasMinor : amountMinor,
      },
    };
  } catch (error) {
    return { ...IDLE, error: reasonFor(error), echo };
  }
}

function reasonFor(error: unknown): PriceError {
  if (!(error instanceof ApiError)) return "plans.refused";
  if (error.reason === "unreachable") return "error.network";
  if (error.status === 429) return "error.tooMany";
  if (error.status === 403) return "plans.needsStepUp";
  return "plans.refused";
}
