"use client";

import { useActionState, useState } from "react";

import { Banner } from "@/components/ds/banner";
import { Button } from "@/components/ds/button";
import { Field } from "@/components/ds/field";
import { fill, formatMoney, t, type Locale, type MessageKey, type Numbering } from "@/i18n/locale";
import { moneyOf, parseAmount } from "@/lib/cash";
import { direction, riseState, type Impact, type PriceRow } from "@/lib/plans";

import { writePrice } from "./actions";
import { IDLE, type PriceState } from "./state";

/**
 * ADM-MSH-09's price change, with the blast radius stated before it is saved.
 *
 * **The disclosure appears as the figure is typed, which is the canvas's own requirement**:
 * "the affected count is computed *before* the change is saved, not reported after". The count
 * itself is the server's — it walks the supersession chain and splits the members a commitment
 * protects from the ones who move — so this component does not compute it; what it does is
 * refuse to let the write happen until somebody has been shown it and typed the figure back.
 *
 * **Five refusals, each with its own sentence**, because a disabled button with no reason is
 * the control nobody can act on: not an amount, the same amount, no effective date, a date in
 * the past, and the confirmation not yet given.
 */
export function PriceForm({
  locale, numbering, plan, current, impact, today, canWrite, stepUpHref,
}: {
  locale: Locale;
  numbering: Numbering;
  /** `name` is the product's, from `planName` -- not the variant's. */
  plan: { variant_id: string; name: string };
  current: PriceRow;
  impact: Impact | null;
  today: string;
  canWrite: boolean;
  /** Where to send a session that could step up, or `null` when nothing would help. */
  stepUpHref: string | null;
}) {
  const [state, action, pending] = useActionState<PriceState, FormData>(
    writePrice, IDLE);
  const [typedAmount, setTypedAmount] = useState(state.echo.amount ?? "");
  const [from, setFrom] = useState(state.echo.from ?? "");
  const [confirm, setConfirm] = useState(state.echo.confirm ?? "");
  const text = (key: MessageKey) => t(locale, key);

  const rise = riseState({
    typedAmount, effectiveFrom: from, typedConfirmation: confirm,
    current, today,
  });
  const money = moneyOf(current.currency);
  const proposed = money === null ? null : parseAmount(typedAmount, money);
  const amount = (minor: number) =>
    // `latn`, not the tenant's: ADM-SET-07's money exception, which is why this form
    // takes the numeral system for its counts and dates and does not use it here.
    formatMoney(minor, current.currency, "latn", locale);

  return (
    <form action={action} className="ds-cash-form">
      <input type="hidden" name="variant_id" value={plan.variant_id} />
      <input type="hidden" name="price_book_id" value={current.price_book_id} />
      <input type="hidden" name="currency" value={current.currency} />
      <input type="hidden" name="was_minor" value={String(current.amount_minor)} />

      <p className="muted" style={{ margin: 0 }}>
        {fill(locale, "plans.currentlyAt",
          { amount: amount(current.amount_minor) }, numbering)}
      </p>

      <Field
        id="price-amount" name="amount" type="currency" required rarer="optional"
        label={text("plans.newPrice")}
        prefix={current.currency}
        defaultValue={state.echo.amount ?? ""}
        message={rise.kind === "notAnAmount"
          ? { kind: "error", text: text("plans.notAnAmount") }
          : rise.kind === "unchanged"
            ? { kind: "error", text: text("plans.unchanged") }
            : null}
      >
        <input
          id="price-amount" name="amount" className="ds-field-input"
          inputMode="decimal" autoComplete="off" dir="ltr" aria-required="true"
          defaultValue={state.echo.amount ?? ""}
          onChange={(event) => setTypedAmount(event.target.value)}
        />
      </Field>

      {/* **The blast radius, the moment there is a figure to state it about.** Three counts and
          two dates, all the server's: the split is what makes the total meaningful, because a
          published version is immutable and every agreement already signed keeps its figure. */}
      {proposed !== null && proposed !== current.amount_minor ? (
        impact === null ? (
          <Banner severity="attention" title={text("plans.noCount")}>
            {text("plans.noCountWhat")}
          </Banner>
        ) : (
          <div className="ds-cash-variance" data-direction="over"
            data-testid="blast-radius">
            <p className="ds-cash-variance-head">
              <span>
                {fill(locale,
                  direction(proposed, current) === "rise"
                    ? "plans.raisingFromTo" : "plans.cuttingFromTo",
                  { plan: plan.name,
                    was: amount(current.amount_minor),
                    now: amount(proposed) }, numbering)}
              </span>
            </p>
            <p style={{ margin: 0 }}>
              {fill(locale, "plans.onThisPlan",
                { count: impact.on_this_plan }, numbering)}
            </p>
            {impact.inside_a_commitment > 0 ? (
              <p style={{ margin: 0 }}>
                {fill(locale, "plans.insideACommitment", {
                  count: impact.inside_a_commitment,
                  amount: amount(current.amount_minor),
                }, numbering)}
                {impact.earliest_commitment_ends_on !== null ? (
                  <>
                    {" "}
                    {fill(locale, "plans.firstCommitmentEnds",
                      { on: impact.earliest_commitment_ends_on }, numbering)}
                  </>
                ) : null}
              </p>
            ) : null}
            <p style={{ margin: 0 }}>
              {impact.move_at_renewal === 0
                ? text("plans.nobodyMoves")
                : fill(locale, "plans.moveAtRenewal", {
                  count: impact.move_at_renewal,
                }, numbering)}
              {impact.earliest_move_on !== null ? (
                <>
                  {" "}
                  {fill(locale, "plans.earliestOn",
                    { on: impact.earliest_move_on }, numbering)}
                </>
              ) : null}
            </p>
          </div>
        )
      ) : null}

      <Field
        id="price-from" name="effective_from" type="date" required rarer="optional"
        label={text("plans.effectiveFrom")}
        description={text("plans.effectiveFromWhy")}
        defaultValue={state.echo.from ?? ""}
        message={rise.kind === "dateInThePast"
          ? { kind: "error", text: text("plans.datePast") }
          : rise.kind === "needsDate" && typedAmount.trim() !== ""
            ? { kind: "error", text: text("plans.needsDate") }
            : null}
      >
        <input
          id="price-from" name="effective_from" type="date"
          className="ds-field-input" aria-required="true" min={today}
          defaultValue={state.echo.from ?? ""}
          onChange={(event) => setFrom(event.target.value)}
        />
      </Field>

      {/* **The canvas's own control**: `type "58.00" to confirm`. Tier 3, which is what makes a
          price rise different from every other write in Admin -- and it is checked in the
          action as well, because a control only the browser enforces is not one. */}
      {rise.kind === "needsConfirmation" || rise.kind === "ready" ? (
        <Field
          id="price-confirm" name="confirm" type="currency" required rarer="optional"
          label={fill(locale, "plans.typeToConfirm",
            { amount: amount(proposed ?? 0) }, numbering)}
          prefix={current.currency}
          defaultValue={state.echo.confirm ?? ""}
          message={rise.kind === "needsConfirmation" && confirm.trim() !== ""
            ? { kind: "error", text: text("plans.confirmMismatch") }
            : null}
        >
          <input
            id="price-confirm" name="confirm" className="ds-field-input"
            inputMode="decimal" autoComplete="off" dir="ltr" aria-required="true"
            defaultValue={state.echo.confirm ?? ""}
            onChange={(event) => setConfirm(event.target.value)}
          />
        </Field>
      ) : (
        <input type="hidden" name="confirm" value="" />
      )}

      {!canWrite ? (
        <p className="muted" style={{ margin: 0 }}>
          {text("plans.needsWrite")}
          {stepUpHref !== null ? (
            <>
              {" "}
              <a href={stepUpHref}>{text("member.raiseSession")}</a>
            </>
          ) : null}
        </p>
      ) : null}

      <Button
        type="submit" variant="primary" size="lg"
        label={text("plans.savePrice")}
        state={pending ? "loading"
          : !canWrite || rise.kind !== "ready" ? "disabled" : "default"}
      />

      {state.error !== null ? (
        <Banner severity="critical">{text(state.error)}</Banner>
      ) : state.priced !== null ? (
        <Banner severity="info">
          {fill(locale, "plans.priced", {
            was: amount(state.priced.wasMinor),
            now: amount(state.priced.amountMinor),
            on: state.priced.effectiveFrom,
          }, numbering)}
        </Banner>
      ) : null}
    </form>
  );
}
